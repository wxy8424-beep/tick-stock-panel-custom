"""Temporal evidence, durable episodes and safe local-only API tests."""
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.anomalies import router
from app.market_session import clear_market_signals, get_market_session
from app.services.anomaly_engine import AnomalyEngine, AnomalyPolicy, Rule
from app.services.anomaly_worker import AnomalyWorker
from app.services.snapshot_archive import SnapshotArchive

START = datetime(2026, 10, 9, 14, tzinfo=UTC)


@pytest.fixture(autouse=True)
def signals():
    clear_market_signals()
    yield
    clear_market_signals()


def policy(seconds=300, threshold="0.02", **changes):
    return AnomalyPolicy(rules=(Rule(rule_id=f"rapid_move_{seconds}s", event_type="rapid_price_move",
                                    window_seconds=seconds, threshold=threshold),), **changes)


def append(archive, seconds, price, *, symbol="AAPL.US", provider="longbridge", clock=START):
    at = clock + timedelta(seconds=seconds)
    market = "CN" if symbol.endswith((".SH", ".SZ", ".BJ")) else symbol.rsplit(".", 1)[-1]
    price = Decimal(str(price))
    archive.append([{"symbol": symbol, "market": market, "last_price": price, "prev_close": price,
                     "open": price, "high": price + 1, "low": price - 1, "volume": None,
                     "volume_unit": "unsupported", "timestamp": int(at.timestamp() * 1000)}],
                   at + timedelta(milliseconds=100), provider)
    return at + timedelta(milliseconds=100)


def warmup(tmp_path, seconds=300, final=Decimal("102.2"), chosen_policy=None, symbol="AAPL.US", clock=START):
    archive = SnapshotArchive(tmp_path)
    for point in range(0, seconds, 30):
        append(archive, point, 100, symbol=symbol, clock=clock)
    at = append(archive, seconds, final, symbol=symbol, clock=clock)
    engine = AnomalyEngine(tmp_path, chosen_policy or policy(seconds))
    return archive, engine, at


@pytest.mark.parametrize("seconds,change", [(60, "0.012"), (300, "0.022"), (900, "0.045")])
def test_real_timestamp_windows_rise_with_boundary_evidence(tmp_path, seconds, change):
    archive, engine, at = warmup(tmp_path, seconds, 100 * (1 + Decimal(change)),
                                policy(seconds, "0.01" if seconds == 60 else "0.02" if seconds == 300 else "0.04"))
    before = archive.path.read_bytes()
    result = engine.run_once(at, start_from_latest=False)
    event = result["events"][-1]
    assert event["event_type"] == "rapid_price_move" and event["direction"] == "up"
    assert Decimal(event["change_pct"]) == Decimal(change)
    assert datetime.fromisoformat(event["window_start"]) == START
    assert datetime.fromisoformat(event["window_end"]) == START + timedelta(seconds=seconds)
    assert event["evidence"]["baseline"][0]["snapshot_id"] == 1
    assert event["evidence"]["volume_used"] is False
    assert event["evidence"]["volume_status"] == "unsupported_unit_unverified"
    assert archive.path.read_bytes() == before
    json.dumps(event, allow_nan=False)


def test_drop(tmp_path):
    _, engine, at = warmup(tmp_path, final=Decimal("97.8"))
    event = engine.run_once(at, start_from_latest=False)["events"][-1]
    assert event["direction"] == "down" and Decimal(event["change_pct"]) == Decimal("-0.022")


@pytest.mark.parametrize("price,severity", [("102", "low"), ("102.999", "low"), ("103", "medium"),
                                           ("103.999", "medium"), ("104", "high")])
def test_threshold_and_severity_boundaries(tmp_path, price, severity):
    _, engine, at = warmup(tmp_path, final=Decimal(price))
    event = engine.run_once(at, start_from_latest=False)["events"][-1]
    assert event["severity"] == severity
    assert event["threshold"] == "0.02" and event["status"] == "first_trigger"


def test_under_threshold_no_event(tmp_path):
    _, engine, at = warmup(tmp_path, final=Decimal("101.999"))
    assert engine.run_once(at, start_from_latest=False)["events"] == []


def test_sustained_escalation_and_restart_dedup(tmp_path):
    archive, engine, at = warmup(tmp_path)
    first = engine.run_once(at, start_from_latest=False)["events"][-1]
    at = append(archive, 330, "102.4")
    engine = AnomalyEngine(tmp_path, policy())  # Real SQLite episode survives a fresh process object.
    second = engine.run_once(at)
    assert second["events"] == []
    assert any(item["state"] == "sustained" for item in second["diagnostics"])
    assert engine.store.episodes("AAPL.US")[0]["status"] == "sustained"
    at = append(archive, 360, "104.3")
    escalation = AnomalyEngine(tmp_path, policy()).run_once(at)["events"][-1]
    assert escalation["severity"] == "high" and escalation["status"] == "escalation"
    assert escalation["episode_id"] == first["episode_id"] and escalation["event_id"] != first["event_id"]
    assert AnomalyEngine(tmp_path, policy()).run_once(at)["events"] == []
    assert len(engine.store.query()["rows"]) == 2


def test_normal_resolution_cooldown_and_independent_retrigger(tmp_path):
    archive, engine, at = warmup(tmp_path)
    first = engine.run_once(at, start_from_latest=False)["events"][-1]
    at = append(archive, 330, 100)
    assert engine.run_once(at)["events"] == []
    assert engine.store.episodes("AAPL.US")[0]["active"] is False
    at = append(archive, 360, 103)
    assert engine.run_once(at)["events"] == []
    for seconds in (390, 420):
        at = append(archive, seconds, 103)
        assert engine.run_once(at)["events"] == []
    at = append(archive, 450, 103)
    later = engine.run_once(at)["events"][-1]
    assert later["status"] == "first_trigger" and later["episode_id"] != first["episode_id"]


@pytest.mark.parametrize("final,direction", [("102", "up"), ("98", "down")])
def test_breakout_baseline_excludes_current_point(tmp_path, final, direction):
    chosen = AnomalyPolicy(rules=(Rule(rule_id="breakout", event_type="intraday_breakout", window_seconds=900, threshold="0.005"),))
    archive = SnapshotArchive(tmp_path)
    for seconds, value in ((0, "100"), (30, "100.1"), (60, "99.9")):
        append(archive, seconds, value)
    at = append(archive, 90, final)
    event = AnomalyEngine(tmp_path, chosen).run_once(at, start_from_latest=False)["events"][-1]
    assert event["event_type"] == "intraday_breakout" and event["direction"] == direction
    assert Decimal(event["baseline_value"]) == Decimal("100.1" if direction == "up" else "99.9")
    assert event["evidence"]["baseline"][0]["snapshot_id"] < event["evidence"]["current"]["snapshot_id"]


@pytest.mark.parametrize("corruption,reason", [
    ({"price": None}, "snapshot_numeric_unknown"),
    ({"price": "-1"}, "snapshot_numeric_unknown"),
    ({"quality_state": "invalid"}, "price_quality_unknown"),
    ({"quality_state": "stale"}, "price_quality_unknown"),
    ({"warnings": '["quote_market_unknown"]'}, "price_quality_unknown"),
    ({"market_session_diagnostic": "calendar_provider_conflict"}, "snapshot_session_unknown"),
    ({"provider": "other"}, "snapshot_identity_conflict"),
])
def test_quality_session_and_identity_gate_no_fake_anomaly(tmp_path, corruption, reason):
    archive, engine, at = warmup(tmp_path)
    with sqlite3.connect(archive.path) as db:
        for field, value in corruption.items():
            db.execute(f"UPDATE market_snapshots SET {field}=? WHERE id=(SELECT MAX(id) FROM market_snapshots)", (value,))
    result = engine.run_once(at, start_from_latest=False)
    assert result["events"] == []
    assert any(item["reason"] == reason for item in result["diagnostics"])


@pytest.mark.parametrize("mode", ["duplicate", "out_of_order", "future"])
def test_timestamp_anomalies_not_sorted_or_deduplicated_away(tmp_path, mode):
    archive, engine, at = warmup(tmp_path)
    last = archive.query(limit=1)[0]
    timestamp = int(last["quote_timestamp"])
    with sqlite3.connect(archive.path) as db:
        if mode == "duplicate":
            db.execute("UPDATE market_snapshots SET quote_timestamp=? WHERE id=?", (str(timestamp), last["id"] - 1))
        elif mode == "out_of_order":
            db.execute("UPDATE market_snapshots SET quote_timestamp=? WHERE id=?", (str(timestamp - 60000), last["id"]))
        else:
            db.execute("UPDATE market_snapshots SET quote_timestamp=? WHERE id=?", (str(timestamp + 1000), last["id"]))
    result = engine.run_once(at, start_from_latest=False)
    assert result["events"] == []
    assert any(item["state"] == "unknown" for item in result["diagnostics"])


def test_missing_boundary_sparse_history_and_stale_current(tmp_path):
    archive = SnapshotArchive(tmp_path)
    append(archive, 270, 100)
    at = append(archive, 300, 105)
    result = AnomalyEngine(tmp_path, policy()).run_once(at, start_from_latest=False)
    assert result["events"] == [] and any(item["reason"] == "window_boundary_missing" for item in result["diagnostics"])
    other = tmp_path / "sparse"
    archive = SnapshotArchive(other)
    for seconds in (0, 150, 300):
        at = append(archive, seconds, 100 if seconds < 300 else 105)
    engine = AnomalyEngine(other, policy())
    result = engine.run_once(at, start_from_latest=False)
    assert result["events"] == [] and any(item["reason"] == "sparse_snapshot_history" for item in result["diagnostics"])
    _, engine, at = warmup(tmp_path / "stale")
    result = engine.run_once(at + timedelta(seconds=121), start_from_latest=False)
    assert result["events"] == [] and any(item["reason"] == "latest_snapshot_stale" for item in result["diagnostics"])


def test_closed_unknown_calendar_and_security_halt_is_local(tmp_path):
    archive, engine, at = warmup(tmp_path)
    result = engine.run_once(at + timedelta(days=1), start_from_latest=False)
    assert result["events"] == [] and any(item["reason"] == "market_not_confirmed_regular" for item in result["diagnostics"])
    _, engine, at = warmup(tmp_path / "outside", clock=START.replace(year=2025))
    assert engine.run_once(at, start_from_latest=False)["events"] == []
    archive, engine, at = warmup(tmp_path / "halt")
    with sqlite3.connect(archive.path) as db:
        db.execute("UPDATE market_snapshots SET warnings='[\"security_halt\"]'")
    assert engine.run_once(at, start_from_latest=False)["events"] == []
    assert get_market_session("US", at).is_regular_session


def test_no_future_received_baseline_and_source_bytes_preserved(tmp_path):
    archive, engine, at = warmup(tmp_path)
    before = archive.path.read_bytes()
    current = archive.query(limit=1)[0]
    append(archive, 330, 999)
    future = engine.assess(current, at)
    event = next(item for item in future if item.get("state") == "triggered")
    assert event["baseline"].quote_timestamp <= int(current["quote_timestamp"]) - 300000
    assert event["observation"].price == Decimal("102.2")
    # Detection itself does not mutate source data, separately from this explicit append.
    snapshot = archive.path.read_bytes()
    engine.run_once(at, start_from_latest=False)
    assert snapshot == archive.path.read_bytes() and before != snapshot


def test_store_failure_isolation_and_unsupported_volatility(tmp_path, monkeypatch):
    _, engine, at = warmup(tmp_path)
    result = engine.run_once(at, start_from_latest=False)
    assert any(item["state"] == "unsupported" and item["reason"] == "snapshot_cadence_not_authoritative" for item in result["diagnostics"])

    def fail():
        raise sqlite3.OperationalError("private database path")

    monkeypatch.setattr(engine.store, "connect", fail)
    result = engine.run_once(at)
    assert result["processed"] == 0 and result["events"] == []
    assert result["diagnostics"][0]["reason"] == "anomaly_storage_or_input_unavailable"
    assert "private database path" not in json.dumps(result)
    worker = AnomalyWorker(tmp_path)
    worker.engine = engine
    worker.tick(at)
    assert worker.health()["state"] == "unavailable"


def test_fresh_worker_no_unbounded_historical_alert_replay(tmp_path):
    archive, engine, at = warmup(tmp_path)
    assert engine.run_once(at)["events"] == []
    at = append(archive, 330, 103)
    assert len(engine.run_once(at)["events"]) == 1


def test_readonly_api_filter_cursor_evidence_and_episode(tmp_path):
    archive, engine, at = warmup(tmp_path)
    engine.run_once(at, start_from_latest=False)
    at = append(archive, 330, 105)
    engine.run_once(at)
    app = FastAPI()
    app.include_router(router)
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    client = TestClient(app)
    source_before, events_before = archive.path.read_bytes(), engine.store.path.read_bytes()
    page = client.get("/api/intraday/anomalies/recent?limit=1").json()
    assert page["rows"][0]["severity"] == "high" and page["rows"][0]["status"] == "escalation"
    assert page["rows"][0]["evidence"]["volume_used"] is False
    assert page["next_before_id"] is not None
    older = client.get(f"/api/intraday/anomalies/recent?before_id={page['next_before_id']}").json()
    assert older["rows"][0]["status"] == "first_trigger"
    assert len(client.get("/api/intraday/anomalies/recent?severity=low&market=US&event_type=rapid_price_move").json()["rows"]) == 1
    assert client.get("/api/intraday/anomalies/recent?symbol=700.HK").json()["rows"] == []
    assert client.get("/api/intraday/anomalies/episodes?symbol=AAPL.US").json()["rows"][0]["peak_severity"] == "high"
    assert client.get("/api/intraday/anomalies/recent?limit=201").status_code == 422
    assert client.get("/api/intraday/anomalies/recent?severity=urgent").status_code == 422
    assert client.get("/api/intraday/anomalies/recent?start=2026-10-09T00:00:00").status_code == 422
    assert client.get("/api/intraday/anomalies/recent?start=2026-10-10T00:00:00Z&end=2026-10-09T00:00:00Z").status_code == 422
    assert source_before == archive.path.read_bytes() and events_before == engine.store.path.read_bytes()


def test_read_queries_empty_do_not_create_database(tmp_path):
    engine = AnomalyEngine(tmp_path)
    assert engine.store.query()["rows"] == [] and engine.store.episodes("AAPL.US") == []
    assert not engine.store.path.exists() and not engine.input.path.exists()


def test_health_includes_authoritative_market_sessions_without_worker(tmp_path):
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get("/api/intraday/anomalies/health")
    assert response.status_code == 200
    result = response.json()
    assert result["state"] == "not_started"
    assert datetime.fromisoformat(result["observed_at"]).tzinfo is not None
    assert set(result["market_sessions"]) == {"CN", "HK", "US"}
    for market, actual in result["market_sessions"].items():
        expected = get_market_session(market, datetime.fromisoformat(result["observed_at"]))
        assert actual == {"session_state": expected.session_state, "diagnostic_code": expected.diagnostic_code}


@pytest.mark.parametrize("symbol,clock", [
    ("600519.SH", datetime(2026, 10, 9, 2, tzinfo=UTC)),
    ("700.HK", datetime(2026, 10, 9, 2, tzinfo=UTC)),
    ("AAPL.US", START),
])
def test_markets_are_independent(tmp_path, symbol, clock):
    archive, engine, at = warmup(tmp_path, symbol=symbol, clock=clock)
    append(archive, 330, 900, symbol="NVDA.US", clock=clock)
    result = engine.run_once(at, start_from_latest=False)
    assert len(result["events"]) == 1
    assert result["events"][0]["symbol"] == symbol
    assert result["events"][0]["market"] == ("CN" if symbol.endswith(".SH") else symbol.rsplit(".", 1)[-1])


def test_event_and_cursor_rollback_together(tmp_path, monkeypatch):
    _, engine, at = warmup(tmp_path)
    original = engine._apply

    def fail_after_insert(db, current, assessment, as_of):
        result = original(db, current, assessment, as_of)
        if result[0] is not None:
            raise sqlite3.OperationalError("injected write failure")
        return result

    monkeypatch.setattr(engine, "_apply", fail_after_insert)
    result = engine.run_once(at, start_from_latest=False)
    assert result["checkpoint"] is None and result["events"] == []
    assert engine.store.query()["rows"] == []
    with sqlite3.connect(engine.store.path) as db:
        assert db.execute("SELECT COUNT(*) FROM anomaly_cursors").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM anomaly_episodes").fetchone()[0] == 0
    monkeypatch.setattr(engine, "_apply", original)
    assert len(engine.run_once(at, start_from_latest=False)["events"]) == 1


def test_policy_versions_and_boundary_tolerance(tmp_path):
    assert policy().version != policy(threshold="0.03").version
    archive = SnapshotArchive(tmp_path)
    for seconds in (0, 30, 60):
        append(archive, seconds, 100)
    at = append(archive, 90, 103)
    engine = AnomalyEngine(tmp_path, policy(60))
    event = engine.run_once(at, start_from_latest=False)["events"][-1]
    assert event["evidence"]["baseline"][0]["quote_timestamp"] == int((START + timedelta(seconds=30)).timestamp() * 1000)
