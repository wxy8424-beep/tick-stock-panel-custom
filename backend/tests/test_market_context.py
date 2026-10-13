"""Isolated archived fixtures only; no provider, credentials or production writes."""
import json
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.anomalies import router
from app.services.historical_enrichment import HistoricalEnrichmentWorker
from app.services.market_context import (
    BENCHMARKS,
    MarketContextService,
    MarketContextStore,
    classify,
    enrich_market_response,
)
from tests.test_anomaly_engine import START, append, warmup


def fixture(tmp_path, market="US", benchmark_change="0.018", points=None):
    clock = START if market == "US" else datetime(2026, 10, 9, 2, tzinfo=UTC)
    symbol = "AAPL.US" if market == "US" else "600519.SH"
    archive, engine, at = warmup(tmp_path, symbol=symbol, clock=clock)
    event = engine.run_once(at, start_from_latest=False)["events"][-1]
    for point in points if points is not None else range(0, 301, 30):
        price = 100 * (1 + Decimal(benchmark_change) * Decimal(point) / 300)
        append(archive, point, price, symbol=BENCHMARKS[market][0], clock=clock)
    return MarketContextService(tmp_path), event, archive, at


@pytest.mark.parametrize("market", ["CN", "US"])
def test_same_window_relative_evidence_and_source(tmp_path, market):
    service, event, archive, _ = fixture(tmp_path, market)
    before = archive.path.read_bytes()
    result = service.context(event)
    assert result["status"] == "available" and result["context_class"] == "market_aligned"
    assert Decimal(result["stock_change_pct"]) == Decimal("0.022")
    assert Decimal(result["benchmark_change_pct"]) == Decimal("0.018")
    assert Decimal(result["relative_move_pct"]) == Decimal("0.004")
    assert result["source"] == "longbridge" and result["benchmark_symbol"] == BENCHMARKS[market][0]
    assert result["window_start"] == event["window_start"] and result["window_end"] == event["window_end"]
    assert archive.path.read_bytes() == before
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("stock,benchmark,relation,category", [
    (".03", ".027", "same", "market_aligned"), (".032", ".011", "same", "idiosyncratic"),
    (".03", "-.01", "opposite", "market_opposed"), ("-.03", ".01", "opposite", "market_opposed"),
    ("-.03", "-.027", "same", "market_aligned"), (".02", ".013", "same", "mixed"),
    (".02", "0", "neutral", "idiosyncratic"), (".01", ".02", "same", "mixed"),
])
def test_deterministic_classification(stock, benchmark, relation, category):
    assert classify(Decimal(stock), Decimal(benchmark)) == (relation, category)


def test_hk_is_explicit_unsupported_not_invented_hsi():
    result = MarketContextService("unused").context({"event_id": "a", "market": "HK", "symbol": "700.HK"})
    assert result["status"] == "unsupported" and result["benchmark_symbol"] is None


@pytest.mark.parametrize("points,blocker", [([], "benchmark_boundary_missing"), ([0, 300], "benchmark_sparse_history"),
                                         ([0, 30, 60, 90, 120, 150, 180, 210, 240], "benchmark_boundary_stale")])
def test_missing_sparse_stale_boundaries(tmp_path, points, blocker):
    service, event, _, _ = fixture(tmp_path, points=points)
    assert service.context(event)["blocker"] == blocker


def mutate(archive, assignment, params=()):
    with closing(__import__("sqlite3").connect(archive.path)) as db, db:
        db.execute("UPDATE market_snapshots SET " + assignment + " WHERE symbol='.SPX.US'", params)


@pytest.mark.parametrize("assignment,blocker", [
    ("market_session_state='closed'", "benchmark_session_unconfirmed"),
    ("market_session_diagnostic='calendar_provider_conflict'", "benchmark_session_unconfirmed"),
    ("quality_state='invalid'", "benchmark_quality_unreliable"),
    ("warnings='[\"timestamp_future\"]'", "benchmark_quality_unreliable"),
    ("receive_timestamp=receive_timestamp+121000", "benchmark_timestamp_or_freshness_invalid"),
    ("price='0'", "market_context_evidence_invalid"),
])
def test_quality_session_and_price_gates(tmp_path, assignment, blocker):
    service, event, archive, _ = fixture(tmp_path)
    mutate(archive, assignment)
    # Allow delayed receipt to be in the event-known interval to specifically test staleness.
    if "121000" in assignment:
        event["detected_at"] = "2026-10-09T14:08:00Z"
    assert service.context(event)["blocker"] == blocker


def test_no_future_quote_or_late_receive(tmp_path):
    service, event, archive, _ = fixture(tmp_path)
    before = service.context(event)
    append(archive, 301, 900, symbol=".SPX.US")
    append(archive, 305, 1, symbol=".SPX.US")
    assert service.context(event)["relative_move_pct"] == before["relative_move_pct"]
    assert service.context(event)["current_observation"] == before["current_observation"]
    assert service.context(event)["current_observation"]["quote_timestamp"] == int(datetime.fromisoformat(event["window_end"]).timestamp() * 1000)


def test_same_timestamp_conflict_and_tolerance(tmp_path):
    service, event, archive, _ = fixture(tmp_path)
    append(archive, 300, 150, symbol=".SPX.US")
    assert service.context(event)["blocker"] == "benchmark_same_timestamp_conflict"


def test_closed_calendar_and_stock_identity(tmp_path):
    service, event, archive, _ = fixture(tmp_path)
    event["market"] = "CN"
    assert service.context(event)["blocker"] == "event_market_conflict"
    event["market"] = "US"
    mutate(archive, "provider='other' WHERE id=(SELECT MAX(id) FROM market_snapshots) AND symbol='.SPX.US' --")
    assert service.context(event)["blocker"] == "benchmark_source_conflict"


def test_persistence_worker_api_and_failure_isolation(tmp_path, monkeypatch):
    service, event, _, _ = fixture(tmp_path)
    events_before = (tmp_path / "user_data" / "anomaly_engine.sqlite3").read_bytes()
    worker = HistoricalEnrichmentWorker(tmp_path, service)
    worker.tick()
    assert worker.health()["processed"] >= 1
    result = service.store.read_many([event["event_id"]])[event["event_id"]]
    assert result["status"] == "available"
    assert enrich_market_response(tmp_path, {"rows": [event]})["rows"][0]["evidence"]["market_context"] == result
    worker.tick()
    assert worker.health()["processed"] == 0
    app = FastAPI()
    app.include_router(router)
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    with TestClient(app) as client:
        assert client.get("/api/intraday/anomalies/market-contexts", params={"event_id": event["event_id"]}).json()["contexts"][event["event_id"]] == result
        assert client.get("/api/intraday/anomalies/recent").json()["rows"][-1]["evidence"]["market_context"]["status"] == "available"
        assert client.get("/api/intraday/anomalies/market-contexts", params=[("event_id", "a")] * 101).status_code == 422
    assert (tmp_path / "user_data" / "anomaly_engine.sqlite3").read_bytes() == events_before
    monkeypatch.setattr(MarketContextStore, "read_many", lambda self, _: (_ for _ in ()).throw(OSError("private text")))
    assert enrich_market_response(tmp_path, {"rows": [event]})["rows"][0]["evidence"]["market_context"]["blocker"] == "market_context_storage_unavailable"


def test_old_event_absent_sidecar_does_not_create_storage(tmp_path):
    result = enrich_market_response(tmp_path, {"rows": [{"event_id": "old", "market": "US", "evidence": {}}]})
    assert result["rows"][0]["evidence"]["market_context"]["status"] == "unknown"
    assert not MarketContextStore(tmp_path).path.exists()
