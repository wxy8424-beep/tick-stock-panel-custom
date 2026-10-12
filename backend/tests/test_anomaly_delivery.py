"""Delivery fixtures stay in isolated temporary SQLite; never production data."""
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.anomalies import router
from app.services.anomaly_engine import AnomalyStore, StaleAnomalyCursorError


def seed(store, first, count):
    with closing(store.connect()) as db, db:
        for number in range(first, first + count):
            payload = {"event_id": f"{number:064x}", "episode_id": "test-episode", "symbol": "AAPL.US", "market": "US",
                       "event_type": "rapid_price_move", "severity": "high", "status": "first_trigger", "detected_at": "2026-10-09T14:05:00Z"}
            db.execute("INSERT INTO anomaly_events(event_id,episode_id,symbol,market,event_type,severity,detected_at,payload) VALUES (?,?,?,?,?,?,?,?)",
                       (payload["event_id"], payload["episode_id"], payload["symbol"], "US", payload["event_type"], "high",
                        int(datetime(2026, 10, 9, 14, 5, tzinfo=UTC).timestamp() * 1000), json.dumps(payload)))


def test_same_timestamp_backlog_and_concurrent_insert_no_loss(tmp_path):
    store = AnomalyStore(tmp_path)
    seed(store, 1, 251)
    first = store.incremental(0, None)
    assert [row["store_id"] for row in first["rows"]] == list(range(1, 101))
    assert first["has_more"] and first["latest_sequence"] == 251
    seed(store, 252, 50)  # New inserts between HTTP pages.
    seen = first["rows"]
    cursor = first["next_cursor"]
    while True:
        page = store.incremental(cursor["sequence"], cursor["event_id"])
        seen.extend(page["rows"])
        cursor = page["next_cursor"]
        if not page["has_more"]:
            break
    assert [row["store_id"] for row in seen] == list(range(1, 302))
    assert len({row["event_id"] for row in seen}) == 301
    assert store.incremental(cursor["sequence"], cursor["event_id"])["rows"] == []


def test_recent_restore_anchor_and_readonly_compatibility(tmp_path):
    store = AnomalyStore(tmp_path)
    seed(store, 1, 150)
    before = store.path.read_bytes()
    recent = store.query(limit=100)
    assert [row["store_id"] for row in recent["rows"]] == list(range(150, 50, -1))
    assert recent["next_before_id"] == 51
    assert recent["resume_cursor"] == {"sequence": 150, "event_id": f"{150:064x}"}
    assert store.query(before_id=51)["rows"][0]["store_id"] == 50
    assert store.delivery_state()["latest_sequence"] == 150
    assert store.path.read_bytes() == before


@pytest.mark.parametrize("sequence,anchor", [(1, "bad"), (999, "bad")])
def test_stale_cursor_fails_explicitly(tmp_path, sequence, anchor):
    store = AnomalyStore(tmp_path)
    seed(store, 1, 1)
    with pytest.raises(StaleAnomalyCursorError):
        store.incremental(sequence, anchor)


def test_deleted_anchor_and_empty_archive(tmp_path):
    store = AnomalyStore(tmp_path)
    assert store.incremental(0, None)["next_cursor"]["sequence"] == 0
    assert not store.path.exists()
    seed(store, 1, 2)
    with sqlite3.connect(store.path) as db:
        db.execute("DELETE FROM anomaly_events WHERE id=1")
    with pytest.raises(StaleAnomalyCursorError):
        store.incremental(1, f"{1:064x}")


def test_api_hard_limits_cursor_errors_and_compatibility(tmp_path):
    store = AnomalyStore(tmp_path)
    seed(store, 1, 201)
    app = FastAPI()
    app.include_router(router)
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    client = TestClient(app)
    page = client.get("/api/intraday/anomalies/incremental").json()
    assert len(page["rows"]) == 100 and page["has_more"]
    cursor = page["next_cursor"]
    next_page = client.get("/api/intraday/anomalies/incremental", params={"after_id": cursor["sequence"], "after_event_id": cursor["event_id"]}).json()
    assert next_page["rows"][0]["store_id"] == 101
    for params in ({"after_id": -1}, {"limit": 201}, {"after_id": 1}):
        assert client.get("/api/intraday/anomalies/incremental", params=params).status_code == 422
    assert client.get("/api/intraday/anomalies/incremental?after_id=999&after_event_id=bad").status_code == 409
    assert len(client.get("/api/intraday/anomalies/recent").json()["rows"]) == 100
    assert client.get("/api/intraday/anomalies/health").json()["delivery"]["latest_sequence"] == 201
