"""Isolated production configuration tests; never inject production events/evidence."""
import asyncio
import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_market_context import fixture as market_fixture

from app.services import anomaly_intelligence_production as production
from app.services.anomaly_intelligence import AnomalyEvidenceCollector
from app.services.evidence_execution import TradingCalendarBindings, TradingCalendarContract
from app.services.evidence_policy import EvidencePolicy, EvidencePolicyResolver, EvidencePolicyStore


def event(market="US", **changes):
    return {"symbol": {"US": "NVDA.US", "CN": "000002.SZ", "HK": "700.HK"}[market],
            "market": market, "event_type": "rapid_price_move", "detected_at": "2026-10-09T15:00:00Z"} | changes


@pytest.mark.parametrize("market", ["CN", "US"])
def test_manifest_scope_evidence_and_exact_binding(tmp_path, market):
    execution = production.bootstrap_production_evidence(tmp_path)
    rules = EvidencePolicyResolver(EvidencePolicyStore(tmp_path)).resolve(event(market))
    assert rules["status"] == "READY"
    chosen = EvidencePolicy.model_validate(rules["selection_rules"])
    assert chosen.policy_id == f"anomaly-intelligence-{market.lower()}" and chosen.version == "v1"
    assert chosen.scope_type == "MARKET_WIDE" and chosen.symbol_scope == ()
    assert chosen.required_evidence == ("market",) and chosen.optional_evidence == ("historical",)
    assert not chosen.factor_enabled and chosen.required_factor_versions == ()
    assert chosen.definition_id is chosen.universe_id is chosen.normalization_version is None
    bound = execution.resolve(chosen)
    assert bound["factor_branch"] == "NOT_SELECTED" and bound["factor_identity_binding"] == []
    ref = next(ref for ref in production.PRODUCTION_REFERENCES if ref.market == market)
    assert (bound["calendar_binding"]["calendar_id"], bound["calendar_binding"]["version"],
            bound["calendar_binding"]["content_hash"]) == (ref.calendar_id, ref.calendar_version, ref.calendar_content_hash)
    assert EvidencePolicyResolver(EvidencePolicyStore(tmp_path)).resolve(event("HK"))["blocker"] == "no_matching_policy"


@pytest.mark.parametrize("market", ["CN", "US"])
@pytest.mark.parametrize("boundary,expected", [("effective_from", "READY"), ("effective_to", "BLOCKED")])
def test_half_open_effective_period(tmp_path, market, boundary, expected):
    production.bootstrap_production_evidence(tmp_path)
    chosen = next(b.policy for b in production.production_bindings() if b.policy.market == market)
    result = EvidencePolicyResolver(EvidencePolicyStore(tmp_path)).resolve(event(market, detected_at=getattr(chosen, boundary)))
    assert result["status"] == expected


def test_materialization_idempotent_and_payload_unchanged(tmp_path):
    production.bootstrap_production_evidence(tmp_path)
    store = EvidencePolicyStore(tmp_path)
    with sqlite3.connect(store.path) as db:
        before = db.execute("SELECT * FROM policies ORDER BY policy_id").fetchall()
    production.bootstrap_production_evidence(tmp_path)
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT * FROM policies ORDER BY policy_id").fetchall() == before
    assert len(before) == 2


def test_conflicting_existing_version_not_overwritten_or_partially_installed(tmp_path):
    chosen = production.production_bindings()[1].policy
    changed = EvidencePolicy.model_validate(chosen.to_dict() | {"allow_atr_display": False, "allow_move_atr_ratio": False})
    store = EvidencePolicyStore(tmp_path)
    store.save(changed)
    with pytest.raises(ValueError, match="immutable_policy_version_conflict"):
        production.bootstrap_production_evidence(tmp_path)
    assert store.list_policies() == (changed,)


@pytest.mark.parametrize("changes,reason", [
    ({"calendar_content_hash": "0" * 64}, "production_calendar_identity_conflict"),
    ({"calendar_version": "future-v2"}, "production_calendar_identity_conflict"),
    ({"effective_to": "2027-01-02T00:00:00+08:00"}, "production_policy_calendar_coverage_conflict"),
    ({"effective_from": "2025-12-31T00:00:00+08:00"}, "production_policy_calendar_coverage_conflict"),
])
def test_bad_manifest_fails_before_db_write(tmp_path, monkeypatch, changes, reason):
    refs = production.PRODUCTION_REFERENCES
    monkeypatch.setattr(production, "PRODUCTION_REFERENCES", (replace(refs[0], **changes), refs[1]))
    with pytest.raises(ValueError, match=reason):
        production.bootstrap_production_evidence(tmp_path)
    assert not EvidencePolicyStore(tmp_path).path.exists()


def test_calendar_registry_conflict_rejected(tmp_path, monkeypatch):
    register = TradingCalendarBindings.register

    def conflicting(self, item):
        altered = TradingCalendarContract.freeze(**(item.model_dump(exclude={"content_hash"}) | {"holidays": []}))
        register(self, altered)
        register(self, item)

    monkeypatch.setattr(TradingCalendarBindings, "register", conflicting)
    with pytest.raises(ValueError, match="immutable_calendar_version_conflict"):
        production.bootstrap_production_evidence(tmp_path)
    assert not EvidencePolicyStore(tmp_path).path.exists()


def test_symbol_specific_overlap_and_newer_version_never_selected_implicitly(tmp_path):
    production.bootstrap_production_evidence(tmp_path)
    store = EvidencePolicyStore(tmp_path)
    chosen = production.production_bindings()[1].policy
    store.save(EvidencePolicy.model_validate(chosen.to_dict() | {"version": "v2", "scope_type": "SYMBOLS",
                                                               "symbol_scope": ["NVDA.US"]}))
    resolver = EvidencePolicyResolver(store)
    assert resolver.resolve(event())["blocker"] == "multiple_matching_policies"
    assert resolver.resolve(event(symbol="AAPL.US"))["version"] == "v1"


@pytest.mark.parametrize("market", ["CN", "US"])
@pytest.mark.parametrize("market_ready,strict_pit,expected", [
    (True, True, "READY"), (True, False, "PARTIAL"), (False, False, "PARTIAL"),
])
def test_fixture_e2e_existing_aggregation_semantics(tmp_path, monkeypatch, market, market_ready, strict_pit, expected):
    execution = production.bootstrap_production_evidence(tmp_path)
    service, original, _, _ = market_fixture(tmp_path, market)
    context = service.context(original)
    with closing(service.store.connect()) as db, db:
        db.execute("INSERT INTO contexts VALUES (?,?)", (original["event_id"], json.dumps(context)))
    collector = AnomalyEvidenceCollector(tmp_path, execution=execution)
    history = {"symbol": original["symbol"], "market": market, "status": "available", "atr14": "5.4",
        "reference_close": "100", "move_absolute": "2.2", "move_atr_ratio": None, "pit_capable": strict_pit,
        "as_of_date": "2026-10-09", "lookback_end": "2026-10-08", "bars": [{"date": "2026-10-08"}],
        "source": "isolated_fixture", "adjustment_method": "fixture-none", "baseline_version": "fixture-v1",
        "availability_evidence": "fixture-proof", "source_vintage": "fixture-vintage",
        "input_available_at": "2026-10-08T00:00:00Z", "price_scale_verified": strict_pit}
    monkeypatch.setattr(collector.history, "read_many", lambda ids: {original["event_id"]: history})
    if not market_ready:
        monkeypatch.setattr(collector.markets, "read_many", lambda ids: {})
    monkeypatch.setattr(collector.factors, "query", lambda *a, **kw: pytest.fail("disabled factor queried"))
    result = collector.collect(original)
    assert result.status == expected
    assert result.factor.status == "NOT_SELECTED" and result.factor.to_dict()["total_score"] is None
    assert result.historical.to_dict()["move_atr_ratio"] is None
    assert not any("factor" in blocker for blocker in result.blockers)
    assert result.market_evidence.status == ("READY" if market_ready else "UNAVAILABLE")


@pytest.mark.parametrize("conflict", [False, True])
def test_lifespan_bootstrap_before_repository_and_workers(tmp_path, monkeypatch, conflict):
    from app import main as main_module
    from app.services import auth

    monkeypatch.setattr(auth, "bootstrap_from_env", lambda: None)
    monkeypatch.setattr(main_module, "DataStore", lambda: SimpleNamespace(data_dir=tmp_path))
    if conflict:
        chosen = production.production_bindings()[0].policy
        EvidencePolicyStore(tmp_path).save(EvidencePolicy.model_validate(chosen.to_dict() | {"status": "INACTIVE"}))

    def after_bootstrap(store):
        assert not conflict
        assert len(EvidencePolicyStore(store.data_dir).list_policies()) == 2
        raise RuntimeError("stop_after_bootstrap_before_workers")

    monkeypatch.setattr(main_module, "KlineRepository", after_bootstrap)

    async def run():
        async with main_module._application_lifespan(SimpleNamespace(state=SimpleNamespace())):
            pytest.fail("must stop before workers")

    with pytest.raises(ValueError if conflict else RuntimeError,
                       match="immutable_policy_version_conflict" if conflict else "stop_after_bootstrap_before_workers"):
        asyncio.run(run())


def test_worker_receives_bootstrapped_execution(tmp_path, monkeypatch):
    from app.services.anomaly_intelligence_worker import AnomalyIntelligenceWorker
    from app.services.anomaly_worker import AnomalyWorker
    from app.services.historical_enrichment import HistoricalEnrichmentWorker

    execution = production.bootstrap_production_evidence(tmp_path)
    monkeypatch.setattr(AnomalyWorker, "_run", lambda self: self._stop.wait())
    monkeypatch.setattr(AnomalyIntelligenceWorker, "_run", lambda self: self._stop.wait())
    monkeypatch.setattr(HistoricalEnrichmentWorker, "start", lambda self: None)
    monkeypatch.setattr(HistoricalEnrichmentWorker, "close", lambda self: None)
    worker = AnomalyWorker(tmp_path, intelligence_execution=execution)
    try:
        worker.start()
        assert worker._intelligence_worker.collector.execution is execution
        assert worker._intelligence_worker._thread.is_alive()
    finally:
        worker.close()
    assert not worker._intelligence_worker._thread.is_alive()
