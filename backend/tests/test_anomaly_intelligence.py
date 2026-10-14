"""Isolated contract fixtures; never production policy, snapshot or event injection."""
import json
import sqlite3
from contextlib import closing
from copy import deepcopy
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.anomaly_intelligence import router
from app.services import factor_snapshots
from app.services.anomaly_engine import AnomalyStore
from app.services.anomaly_intelligence import AnomalyEvidenceCollector, AnomalyIntelligenceStore
from app.services.anomaly_intelligence_worker import AnomalyIntelligenceWorker
from app.services.evidence_execution import (
    EvidenceExecutionResolver,
    PolicyExecutionBinding,
    TradingCalendarBindings,
)
from app.services.evidence_policy import EvidencePolicyStore
from app.services.factor_snapshots import FactorSnapshotBuilder
from tests.test_evidence_execution import calendar, factor
from tests.test_evidence_policy import policy
from tests.test_factor_snapshots import inputs
from tests.test_market_context import fixture as market_fixture


def setup(tmp_path, monkeypatch, *, selected=("historical", "market", "factors")):
    service, event, _, _ = market_fixture(tmp_path)
    market = service.context(event)
    with closing(service.store.connect()) as db, db:
        db.execute("INSERT INTO contexts VALUES (?,?)", (event["event_id"], json.dumps(market)))
    calendars = TradingCalendarBindings()
    calendars.register(calendar())
    execution = EvidenceExecutionResolver(calendars)
    chosen = policy(required_evidence=list(selected), optional_evidence=[], universe_id="fixture-universe-1")
    execution.register(PolicyExecutionBinding(policy_id=chosen.policy_id, policy_version=chosen.version,
        policy=chosen, calendar_id=chosen.trading_calendar, calendar_version="1", factors=(factor(),)))
    EvidencePolicyStore(tmp_path).save(chosen)
    collector = AnomalyEvidenceCollector(tmp_path, execution=execution)
    historical = {"symbol": "AAPL.US", "market": "US", "status": "available", "blocker": None,
        "atr14": "5.4", "reference_close": "100", "move_absolute": "2.2", "move_atr_ratio": None,
        "source": "isolated-fixture", "adjustment_method": "fixture-none", "baseline_version": "fixture-v1",
        "as_of_date": "2026-10-09", "lookback_end": "2026-10-08", "pit_capable": True,
        "bars": [{"date": "2026-10-08", "close": 100}], "availability_evidence": "fixture-proof",
        "source_vintage": "fixture-vintage", "input_available_at": "2026-10-08T21:00:00Z"}
    with closing(collector.history.connect()) as db, db:
        db.execute("INSERT INTO contexts VALUES (?,?)", (event["event_id"], json.dumps(historical)))

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            now = datetime(2026, 10, 9, 12, tzinfo=UTC)
            return now if tz is None else now.astimezone(tz)
    monkeypatch.setattr(factor_snapshots, "datetime", Clock)
    scores, metadata, universe, provenance = inputs()
    scores["as_of"] = "2026-10-08"
    universe.update(as_of_date="2026-10-08", available_at="2026-10-08T21:00:00+00:00")
    provenance.update(input_latest_date=date(2026, 10, 8), input_available_at=datetime(2026, 10, 8, 21, tzinfo=UTC))
    result = FactorSnapshotBuilder().build(scores, metadata, universe, provenance=provenance, symbol="AAPL.US",
                                         run_id="fixture-run", definition_id=chosen.definition_id)
    assert result["status"] == "READY"
    collector.factors.save(result["snapshot"])
    return collector, event, historical, market, result["snapshot"]


def set_context(store, event, raw):
    with closing(store.connect()) as db, db:
        db.execute("UPDATE contexts SET payload=? WHERE event_id=?", (json.dumps(raw), event["event_id"]))


def test_complete_aggregation_no_calculation_or_mutation(tmp_path, monkeypatch):
    collector, event, _, _, _ = setup(tmp_path, monkeypatch)
    from app.factors.engine import MarketFactorEngine
    monkeypatch.setattr(MarketFactorEngine, "compute", lambda *a, **k: pytest.fail("no calculation"))
    original = deepcopy(event)
    files = [collector.history.path, collector.markets.path, collector.factors.path, collector.archive.path]
    before = [path.read_bytes() for path in files]
    record = collector.collect(event)
    assert record.status == "READY"
    assert record.factor.to_dict()["factor_score"] == 0.5
    assert record.market_evidence.to_dict()["relative_move_pct"] == "0.004"
    assert event == original and before == [path.read_bytes() for path in files]
    json.dumps(record.to_dict(), allow_nan=False)


def test_no_policy_and_conflicting_policy(tmp_path, monkeypatch):
    collector, event, *_ = setup(tmp_path, monkeypatch)
    with sqlite3.connect(collector.policies.store.path) as db:
        db.execute("DELETE FROM policies")
    assert collector.collect(event).blockers == ("no_applicable_evidence_policy",)
    store = EvidencePolicyStore(tmp_path)
    store.save(policy())
    store.save(policy(version="v2"))
    assert collector.collect(event).blockers == ("multiple_matching_policies",)


def test_unknown_execution_calendar(tmp_path, monkeypatch):
    collector, event, *_ = setup(tmp_path, monkeypatch)
    collector.execution.calendars = TradingCalendarBindings()
    assert collector.collect(event).blockers == ("calendar_binding_missing",)


def test_retrospective_history_and_null_ratio(tmp_path, monkeypatch):
    collector, event, history, *_ = setup(tmp_path, monkeypatch)
    history.update(pit_capable=False, blocker="event_baseline_price_scale_unverified", move_atr_ratio="0.4")
    set_context(collector.history, event, history)
    record = collector.collect(event)
    assert record.status == "PARTIAL"
    value = record.historical.to_dict()
    assert value["status"] == "PARTIAL" and value["atr14"] == "5.4"
    assert value["move_atr_ratio"] is None and value["blocker"] == "event_baseline_price_scale_unverified"


def test_no_future_historical_bars(tmp_path, monkeypatch):
    collector, event, history, *_ = setup(tmp_path, monkeypatch)
    history["bars"].append({"date": "2026-10-09", "close": 100})
    set_context(collector.history, event, history)
    assert collector.collect(event).historical.status == "BLOCKED"


@pytest.mark.parametrize("field", ["window_start", "window_end", "market"])
def test_market_mismatch_rejected(tmp_path, monkeypatch, field):
    collector, event, _, market, _ = setup(tmp_path, monkeypatch)
    market[field] = "HK" if field == "market" else "2026-10-09T14:06:00Z"
    set_context(collector.markets, event, market)
    assert collector.collect(event).market_evidence.status == "BLOCKED"


def test_future_market_observation_rejected(tmp_path, monkeypatch):
    collector, event, _, market, _ = setup(tmp_path, monkeypatch)
    market["observations"][-1]["quote_timestamp"] += 60000
    set_context(collector.markets, event, market)
    assert collector.collect(event).market_evidence.status == "BLOCKED"


@pytest.mark.parametrize("column", ["available_at", "generated_at", "stored_at"])
def test_factor_store_future_time_rejected(tmp_path, monkeypatch, column):
    collector, event, *_ = setup(tmp_path, monkeypatch)
    with sqlite3.connect(collector.factors.path) as db:
        db.execute(f"UPDATE snapshots SET {column}=?", (datetime(2026, 10, 10, tzinfo=UTC).timestamp(),))
    record = collector.collect(event)
    assert record.factor.status == "UNAVAILABLE" and record.status == "PARTIAL"


@pytest.mark.parametrize("field,value", [("definition_id", "wrong"), ("snapshot_date", "2026-10-07")])
def test_no_definition_or_older_date_fallback(tmp_path, monkeypatch, field, value):
    collector, event, *_ = setup(tmp_path, monkeypatch)
    with sqlite3.connect(collector.factors.path) as db:
        db.execute(f"UPDATE snapshots SET {field}=?", (value,))
    assert collector.collect(event).factor.status == "UNAVAILABLE"


@pytest.mark.parametrize("kind", ["universe", "component", "version", "parameters", "normalization"])
def test_factor_identity_mismatch_blocks(tmp_path, monkeypatch, kind):
    collector, event, *_ = setup(tmp_path, monkeypatch)
    actual = collector.factors.query("AAPL.US", snapshot_date=date(2026, 10, 8),
        definition_id="fixture-definition", as_of_time=datetime(2026, 10, 9, 15, tzinfo=UTC))
    snapshot = actual["snapshot"]
    if kind == "universe":
        snapshot["universe_id"] = "other"
    elif kind == "component":
        snapshot["calculation_metadata"]["factors"][0]["output_column"] = "ma20"
    elif kind == "version":
        snapshot["calculation_metadata"]["factors"][0]["registry"]["version"] = 2
    elif kind == "parameters":
        snapshot["calculation_metadata"]["factors"][0]["period"] = None
    else:
        snapshot["normalization"][0]["version"] = "other"
    monkeypatch.setattr(collector.factors, "query", lambda *a, **kw: actual)
    assert collector.collect(event).factor.status == "BLOCKED"


def test_missing_evidence_is_unavailable(tmp_path, monkeypatch):
    collector, event, *_ = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(collector.history, "read_many", lambda ids: {})
    monkeypatch.setattr(collector.markets, "read_many", lambda ids: {})
    monkeypatch.setattr(collector.factors, "query", lambda *a, **kw: {"status": "UNAVAILABLE", "blocker": "missing"})
    assert collector.collect(event).status == "UNAVAILABLE"


def test_store_idempotency_and_conflict(tmp_path, monkeypatch):
    collector, event, *_ = setup(tmp_path, monkeypatch)
    store = AnomalyIntelligenceStore(tmp_path)
    record = collector.collect(event)
    assert store.save(record)["status"] == "SAVED"
    assert store.save(collector.collect(event))["status"] == "SAVED"
    assert store.get(event["event_id"]) == record
    assert len(store.list_recent()) == 1
    conflict = record.model_copy(update={"policy_version": "conflict"})
    assert store.save(conflict)["status"] == "BLOCKED"
    assert store.get(event["event_id"]) == record


def test_consumer_failure_and_duplicate_isolation(tmp_path, monkeypatch):
    collector, _event, *_ = setup(tmp_path, monkeypatch)
    worker = AnomalyIntelligenceWorker(tmp_path, collector=collector)
    before = AnomalyStore(tmp_path).incremental(0, None)
    original = collector.collect
    monkeypatch.setattr(collector, "collect", lambda event: (_ for _ in ()).throw(ValueError("fixture")))
    worker.tick()
    assert worker.health()["state"] == "unavailable"
    assert AnomalyStore(tmp_path).incremental(0, None) == before
    monkeypatch.setattr(collector, "collect", original)
    worker.tick()
    worker.tick()
    assert worker.health()["state"] == "observing"
    assert len(worker.store.list_recent()) == len(before["rows"])
    assert AnomalyStore(tmp_path).incremental(0, None) == before


@pytest.mark.parametrize("state", ["READY", "PARTIAL", "UNAVAILABLE", "BLOCKED"])
def test_api_stored_status_and_event_404(tmp_path, monkeypatch, state):
    collector, event, *_ = setup(tmp_path, monkeypatch)
    record = collector.collect(event).model_copy(update={"status": state})
    AnomalyIntelligenceStore(tmp_path).save(record)
    app = FastAPI()
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    app.include_router(router)
    with TestClient(app) as client:
        response = client.get(f"/api/anomalies/{event['event_id']}/intelligence")
        assert response.status_code == 200 and response.json()["status"] == state
        assert client.get(f"/api/anomalies/{'0' * 64}/intelligence").status_code == 404


def test_api_no_default_policy_no_write(tmp_path):
    service, event, *_ = market_fixture(tmp_path)
    app = FastAPI()
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    app.include_router(router)
    before = service.archive.path.read_bytes()
    with TestClient(app) as client:
        response = client.get(f"/api/anomalies/{event['event_id']}/intelligence")
    assert response.json()["blockers"] == ["no_applicable_evidence_policy"]
    assert not AnomalyIntelligenceStore(tmp_path).path.exists()
    assert service.archive.path.read_bytes() == before


def test_missing_execution_binding(tmp_path, monkeypatch):
    collector, event, *_ = setup(tmp_path, monkeypatch)
    collector.execution = EvidenceExecutionResolver(TradingCalendarBindings())
    assert collector.collect(event).blockers == ("execution_binding_missing",)


def test_event_future_window_blocks_before_any_collection(tmp_path, monkeypatch):
    collector, event, *_ = setup(tmp_path, monkeypatch)
    event["window_end"] = "2026-10-09T15:00:00Z"
    monkeypatch.setattr(collector.factors, "query", lambda *a, **kw: pytest.fail("must not read evidence"))
    assert collector.collect(event).blockers == ("event_window_time_conflict",)


def test_missing_market_context_keeps_other_evidence(tmp_path, monkeypatch):
    collector, event, *_ = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(collector.markets, "read_many", lambda ids: {})
    record = collector.collect(event)
    assert record.status == "PARTIAL" and record.market_evidence.status == "UNAVAILABLE"


def test_source_unavailable_status_preserved(tmp_path, monkeypatch):
    collector, event, _, market, _ = setup(tmp_path, monkeypatch)
    market.update(status="unsupported", blocker="market_benchmark_unverified")
    set_context(collector.markets, event, market)
    value = collector.collect(event).market_evidence.to_dict()
    assert value["status"] == "UNAVAILABLE" and value["source_status"] == "unsupported"
    assert value["blocker"] == value["source_blocker"] == "market_benchmark_unverified"


def test_symbol_identity_verified_via_archive(tmp_path, monkeypatch):
    collector, event, _, market, _ = setup(tmp_path, monkeypatch)
    with sqlite3.connect(collector.archive.path) as db:
        db.execute("UPDATE market_snapshots SET symbol='NVDA.US' WHERE id=?", (market["stock_current"]["snapshot_id"],))
    assert collector.collect(event).market_evidence.to_dict()["blocker"] == "market_stock_identity_unverified"


def test_factor_missing_optional_is_partial(tmp_path, monkeypatch):
    collector, event, *_ = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(collector.factors, "query", lambda *a, **kw: {"status": "UNAVAILABLE", "blocker": "missing"})
    result = collector.collect(event)
    assert result.status == "PARTIAL" and result.factor.status == "UNAVAILABLE"


def test_factor_future_payload_rejected_even_with_invalid_adapter(tmp_path, monkeypatch):
    collector, event, *_ = setup(tmp_path, monkeypatch)
    result = collector.factors.query("AAPL.US", snapshot_date=date(2026, 10, 8), definition_id="fixture-definition",
                                    as_of_time=datetime(2026, 10, 9, 15, tzinfo=UTC))
    result["snapshot"]["available_at"] = "2026-10-10T00:00:00Z"
    monkeypatch.setattr(collector.factors, "query", lambda *a, **kw: result)
    assert collector.collect(event).factor.to_dict()["blocker"] == "factor_snapshot_future"


def test_consumer_lifecycle_independent(tmp_path, monkeypatch):
    from app.services.anomaly_worker import AnomalyWorker
    from app.services.historical_enrichment import HistoricalEnrichmentWorker

    monkeypatch.setattr(HistoricalEnrichmentWorker, "start", lambda self: None)
    monkeypatch.setattr(HistoricalEnrichmentWorker, "close", lambda self: None)
    monkeypatch.setattr(AnomalyWorker, "_run", lambda self: self._stop.wait())
    monkeypatch.setattr(AnomalyIntelligenceWorker, "_run", lambda self: self._stop.wait())
    worker = AnomalyWorker(tmp_path)
    worker.start()
    assert worker._intelligence_worker._thread.is_alive()
    worker.close()
    assert not worker._intelligence_worker._thread.is_alive()


@pytest.mark.parametrize("retrospective,expected", [(False, "READY"), (True, "PARTIAL")])
def test_disabled_factor_not_queried_or_blocked(tmp_path, monkeypatch, retrospective, expected):
    from tests.test_evidence_policy import disabled_policy

    collector, event, history, *_ = setup(tmp_path, monkeypatch)
    # Only isolated fixture policy data is replaced, never production configuration.
    with sqlite3.connect(collector.policies.store.path) as db:
        db.execute("DELETE FROM policies")
    chosen = disabled_policy()
    EvidencePolicyStore(tmp_path).save(chosen)
    execution = EvidenceExecutionResolver(collector.execution.calendars)
    execution.register(PolicyExecutionBinding(policy_id=chosen.policy_id, policy_version=chosen.version,
        policy=chosen, calendar_id=chosen.trading_calendar, calendar_version="1", factors=()))
    collector.execution = execution
    monkeypatch.setattr(collector.factors, "query", lambda *a, **kw: pytest.fail("disabled must not query snapshots"))
    if retrospective:
        history.update(pit_capable=False, blocker="event_baseline_price_scale_unverified")
        set_context(collector.history, event, history)
    record = collector.collect(event)
    assert record.status == expected
    assert record.factor.status == "NOT_SELECTED" and record.factor.blocker is None
    assert record.factor.to_dict()["total_score"] is None
    assert not any("factor" in code for code in record.blockers)
    store = AnomalyIntelligenceStore(tmp_path)
    store.save(record)
    assert store.get(event["event_id"]).factor.status == "NOT_SELECTED"


def test_api_pending_disabled_factor_not_unavailable(tmp_path, monkeypatch):
    from tests.test_evidence_policy import disabled_policy

    _collector, event, *_ = setup(tmp_path, monkeypatch)
    store = EvidencePolicyStore(tmp_path)
    with sqlite3.connect(store.path) as db:
        db.execute("DELETE FROM policies")
    store.save(disabled_policy())
    app = FastAPI()
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    app.include_router(router)
    with TestClient(app) as client:
        response = client.get(f"/api/anomalies/{event['event_id']}/intelligence")
    assert response.status_code == 200
    assert response.json()["factor"] == {"status": "NOT_SELECTED", "blocker": None, "total_score": None}
    assert not AnomalyIntelligenceStore(tmp_path).path.exists()
