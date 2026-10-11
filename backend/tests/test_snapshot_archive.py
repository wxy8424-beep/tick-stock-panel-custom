"""Archive integration uses isolated SQLite and mock quotes only."""
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.intraday import router
from app.market_session import clear_market_signals
from app.services.quote_service import QuoteService
from app.services.snapshot_archive import MAX_BATCH, SnapshotArchive, SnapshotWriter

NOW = datetime(2026, 10, 9, 14, tzinfo=UTC)


def quote(symbol="AAPL.US", **extra):
    return {"symbol": symbol, "market": "US", "last_price": Decimal("100.1234567890123456789"),
            "prev_close": 99, "open": 99, "high": 101, "low": 98, "volume": None,
            "volume_unit": "unsupported", "timestamp": int(NOW.timestamp() * 1000), **extra}


@pytest.fixture(autouse=True)
def signals():
    clear_market_signals()
    yield
    clear_market_signals()


def test_insert_query_decimal_and_null_volume(tmp_path):
    archive = SnapshotArchive(tmp_path)
    row = quote(provider_observed_at=NOW.isoformat(), secret="never stored")
    assert archive.append([row], NOW + timedelta(seconds=1), "longbridge") == 1
    result = archive.query()[0]
    assert result["symbol"] == "AAPL.US" and result["market"] == "US"
    assert result["provider"] == "longbridge"
    assert result["price"] == "100.1234567890123456789"
    assert result["volume"] is None and row["volume"] is None
    assert result["quote_timestamp"] == str(int(NOW.timestamp() * 1000))
    assert result["receive_timestamp"] == int(NOW.timestamp() * 1000) + 1000
    assert result["provider_observed_at"] == NOW.isoformat()
    assert result["quality_observed_at"] == (NOW + timedelta(seconds=1)).isoformat()
    assert result["quality_state"] == "unknown" and "volume_unknown" in result["warnings"]
    assert result["market_session_state"] == "regular" and result["latency_ms"] == 1000
    assert "never stored" not in json.dumps(result, allow_nan=False)


def test_latest_history_pagination_and_market_isolation(tmp_path):
    archive = SnapshotArchive(tmp_path)
    archive.append([quote(), quote("700.HK", market="HK")], NOW, "longbridge")
    archive.append([quote(last_price=-1)], NOW, "longbridge")
    us = archive.query(market="US", latest=True)
    assert len(us) == 1 and us[0]["quality_state"] == "invalid"
    assert us[0]["price"] == "-1"
    history = archive.query(symbol="AAPL.US", limit=1)
    older = archive.query(symbol="AAPL.US", before_id=history[0]["id"])
    assert len(older) == 1 and older[0]["quality_state"] == "unknown"
    assert archive.query(symbol="' OR 1=1 --") == []
    assert archive.query(symbol="600519.SH") == []


def test_cleanup_only_explicit_cutoff_and_archive_table(tmp_path):
    archive = SnapshotArchive(tmp_path)
    archive.append([quote()], NOW - timedelta(days=1), "old")
    archive.append([quote()], NOW, "new")
    with sqlite3.connect(archive.path) as db:
        db.execute("CREATE TABLE unrelated (value TEXT)")
        db.execute("INSERT INTO unrelated VALUES ('preserve')")
    assert archive.cleanup(NOW) == 1
    assert len(archive.query()) == 1 and archive.query()[0]["provider"] == "new"
    with sqlite3.connect(archive.path) as db:
        assert db.execute("SELECT value FROM unrelated").fetchone()[0] == "preserve"
    assert archive.cleanup(NOW) == 0


def test_read_only_empty_and_preexisting_database(tmp_path):
    archive = SnapshotArchive(tmp_path)
    assert archive.query() == [] and archive.cleanup(NOW) == 0
    assert not archive.path.parent.exists()
    archive.path.parent.mkdir(parents=True)
    with sqlite3.connect(archive.path) as db:
        db.execute("CREATE TABLE old_table (id INTEGER)")
    before = archive.path.read_bytes()
    assert archive.query() == []
    assert before == archive.path.read_bytes()
    archive.append([quote()], NOW, "old-provider")
    assert archive.query()[0]["provider_observed_at"] is None
    with sqlite3.connect(archive.path) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='old_table'").fetchone()


def test_missing_market_legacy_and_no_guessed_volume_unit(tmp_path):
    row = quote("600519.SH", volume=0, timestamp=int((NOW - timedelta(hours=1)).timestamp() * 1000))
    row.pop("market")
    archive = SnapshotArchive(tmp_path)
    archive.append([row], NOW, "legacy")
    result = archive.query()[0]
    assert result["market"] == "CN" and result["volume"] == "0"
    assert result["quality_state"] == "unknown"
    assert "volume_unit_unknown" in result["warnings"]
    assert "market" not in row


def test_invalid_missing_values_and_unknown_market(tmp_path):
    archive = SnapshotArchive(tmp_path)
    row = quote(last_price=float("nan"), volume="not numeric", timestamp=None)
    assert archive.append([row, quote("ABC.UNKNOWN"), None], NOW, "mock") == 1
    result = archive.query()[0]
    assert result["price"] is None and result["volume"] is None
    assert result["quality_state"] == "invalid"
    assert result["quote_timestamp"] is None
    assert result["provider_observed_at"] is None
    archive.append([quote(market="HK")], NOW, "mock")
    assert "quote_market_unknown" in archive.query()[0]["warnings"]


@pytest.mark.parametrize("filters", [{"limit": 0}, {"limit": 1001}, {"market": "UNKNOWN"}])
def test_query_limits(tmp_path, filters):
    with pytest.raises(ValueError):
        SnapshotArchive(tmp_path).query(**filters)


def test_naive_timestamp_rejected_and_batch_limit(tmp_path):
    archive = SnapshotArchive(tmp_path)
    with pytest.raises(ValueError):
        archive.append([quote()], NOW.replace(tzinfo=None), "mock")
    with pytest.raises(ValueError):
        archive.append([quote()] * (MAX_BATCH + 1), NOW, "mock")
    assert not archive.path.exists()


def test_writer_copies_rows_and_flushes_on_close(tmp_path):
    writer = SnapshotWriter(tmp_path)
    row = quote()
    assert writer.submit([row], NOW, "mock")
    row["last_price"] = 999
    writer.close()
    assert writer.archive.query()[0]["price"] == "100.1234567890123456789"
    assert not writer.submit([quote()], NOW, "mock")
    assert not writer._thread.is_alive()


def test_writer_failure_isolated_and_no_payload_logged(tmp_path, monkeypatch, caplog):
    writer = SnapshotWriter(tmp_path)

    def fail(*args):
        raise RuntimeError("sensitive-request-content")

    monkeypatch.setattr(writer.archive, "_write", fail)
    assert writer.submit([quote()], NOW, "mock")
    writer.close()
    assert "sensitive-request-content" not in caplog.text
    assert "写入失败" in caplog.text


def test_atomic_batch_failure_preserves_preexisting_history(tmp_path):
    archive = SnapshotArchive(tmp_path)
    archive.append([quote()], NOW, "original")
    good = archive.prepare([quote()], NOW, "new")[0]
    bad = (*good[:2], None, *good[3:])  # provider NOT NULL; force transaction rollback
    with pytest.raises(sqlite3.IntegrityError):
        archive._write([good, bad])
    assert len(archive.query()) == 1 and archive.query()[0]["provider"] == "original"


def test_cleanup_does_not_reuse_history_cursor_ids(tmp_path):
    archive = SnapshotArchive(tmp_path)
    archive.append([quote()], NOW, "mock")
    cursor = archive.query()[0]["id"]
    assert archive.cleanup(NOW + timedelta(seconds=1)) == 1
    archive.append([quote()], NOW + timedelta(seconds=2), "mock")
    assert archive.query()[0]["id"] > cursor
    assert archive.query(before_id=cursor) == []


def test_queue_is_bounded_and_warns_on_overflow(tmp_path, caplog):
    writer = SnapshotWriter(tmp_path)
    # Deterministic stalled writer without spawning or blocking a real thread.
    writer._thread = SimpleNamespace(join=lambda **kwargs: None, is_alive=lambda: False)
    for _ in range(4):
        assert writer.submit([quote()], NOW, "mock")
    assert not writer.submit([quote()], NOW, "mock")
    assert writer._queue.qsize() == 4 and "队列已满" in caplog.text
    assert not writer.submit([quote()] * (MAX_BATCH + 1), NOW, "mock")
    writer.close()
    assert not writer.archive.path.exists()


def test_quote_service_archives_before_non_cn_filter_and_failure_isolation(tmp_path, monkeypatch):
    from app.data_providers import custom
    from app.services import preferences

    service = QuoteService()
    service.set_repo(SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path)))
    rows = [quote(last_price=-1), quote("700.HK", market="HK", last_price=100.0)]
    provider = SimpleNamespace(realtime_snapshot_scope="symbols", get_realtime_for_markets=lambda markets: rows)
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "mock")
    monkeypatch.setattr(custom, "provider_has_dataset", lambda *args: True)
    monkeypatch.setattr(custom, "get_provider", lambda name: provider)
    monkeypatch.setattr(service, "_should_poll_for_market", lambda market: True)
    assert service._poll_non_cn_quotes()
    service.stop()
    result = SnapshotArchive(tmp_path).query()
    assert len(result) == 2 and result[1]["quality_state"] == "invalid"
    assert len(service.get_non_cn_quotes()) == 1
    monkeypatch.setattr(service, "_snapshot_writer", SimpleNamespace(submit=lambda *args: (_ for _ in ()).throw(RuntimeError())))
    assert service._poll_non_cn_quotes()


def test_readonly_api_limits_serialization_and_no_live_fetch(tmp_path, monkeypatch):
    archive = SnapshotArchive(tmp_path)
    archive.append([quote()], NOW, "longbridge")
    app = FastAPI()
    app.include_router(router)
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    before = archive.path.read_bytes()
    client = TestClient(app)
    latest = client.get("/api/intraday/snapshots/recent?market=US")
    assert latest.status_code == 200 and latest.json()["count"] == 1
    assert latest.json()["rows"][0]["volume"] is None
    assert client.get("/api/intraday/snapshots/quality?symbol=AAPL.US").json()["count"] == 1
    assert client.get("/api/intraday/snapshots/quality?market=HK").json()["count"] == 0
    assert client.get("/api/intraday/snapshots/quality?limit=1001").status_code == 422
    assert client.get("/api/intraday/snapshots/recent?market=UNKNOWN").status_code == 422
    assert archive.path.read_bytes() == before

    def fail(*args, **kwargs):
        raise RuntimeError("sensitive-request-content")

    monkeypatch.setattr(SnapshotArchive, "query", fail)
    response = client.get("/api/intraday/snapshots/quality")
    assert response.status_code == 503 and "sensitive-request-content" not in response.text
