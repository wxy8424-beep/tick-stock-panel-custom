"""Harness tests use only HTTP fixtures, separated from actual live validation."""
import io
import json
from datetime import UTC, datetime

import pytest

from scripts import smoke_anomaly_live as smoke


@pytest.mark.parametrize("state,expected", [("closed", "NOT RUN - MARKET CLOSED"), ("unknown", "NOT RUN - MARKET UNKNOWN OR CONFLICT")])
def test_no_live_claim_for_closed_or_unknown(monkeypatch, state, expected):
    monkeypatch.setattr(smoke, "urlopen", lambda *args, **kwargs: io.BytesIO(json.dumps({"market_sessions": {"US": {"session_state": state}}}).encode()))
    assert smoke.observe("http://localhost:3018", "US", 1)["status"] == expected


@pytest.mark.parametrize("fresh", [True, False])
def test_real_pipeline_criteria_without_fabricating_anomaly(monkeypatch, fresh):
    calls = 0
    now = int(datetime.now(UTC).timestamp() * 1000)

    def read(url, **kwargs):
        nonlocal calls
        if url.endswith("/health"):
            calls += 1
            value = {"state": "observing", "market_sessions": {"US": {"session_state": "regular"}},
                     "processed_by_market": {"US": 0 if calls == 1 else 2},
                     "evaluations_by_market": {"US": 0 if calls == 1 else 8}, "checkpoint": calls}
        elif "/snapshots/" in url:
            value = {"rows": [{"id": 2, "symbol": "AAPL.US", "provider": "longbridge", "market_session_state": "regular", "quote_timestamp": now if fresh else now - 300000, "receive_timestamp": now}]}
        elif "/recent" in url:
            value = {"rows": [], "resume_cursor": {"sequence": 0, "event_id": None}}
        else:
            value = {"rows": [], "has_more": False, "next_cursor": {"sequence": 0, "event_id": None}}
        return io.BytesIO(json.dumps(value).encode())

    monkeypatch.setattr(smoke, "urlopen", read)
    clock = iter([0, 2])
    monkeypatch.setattr(smoke.time, "monotonic", lambda: next(clock))
    result = smoke.observe("http://localhost:3018", "US", 1)
    assert result["status"] == ("LIVE PIPELINE HEALTHY" if fresh else "BLOCKED")
    assert result["anomaly_observation"] == "NO REAL ANOMALY OBSERVED"
    assert result["generated_event_count"] == 0
    assert result["frontend_visibility"].startswith("NOT VERIFIED")
