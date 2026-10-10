"""Mock-only market signals; no security status, credentials or network."""
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.market_session import clear_market_signals, get_market_session
from app.plugins.longbridge.market_state import parse_market_status
from app.plugins.longbridge.provider import LongbridgeProvider
from app.plugins.longbridge.realtime_health import evaluate

NOW = datetime(2026, 10, 8, 14, tzinfo=UTC)


def response(market="US", code=202):
    return SimpleNamespace(market_time=[SimpleNamespace(market=market, trade_status=code, delay_trade_status=204)])


@pytest.fixture(autouse=True)
def isolated():
    clear_market_signals()
    yield
    clear_market_signals()


@pytest.mark.parametrize("market,code,state", [
    ("CN", 105, "regular"), ("HK", 106, "break"), ("HK", 108, "closed"),
    ("HK", 102, "pre_open"), ("HK", 107, "post_market"), ("HK", 121, "closed"),
    ("CN", 122, "closed"), ("CN", 123, "break"), ("CN", 101, "pre_open"),
    ("US", 201, "pre_open"), ("US", 202, "regular"), ("US", 203, "post_market"),
    ("US", 204, "closed"), ("US", 206, "pre_open"),
])
def test_official_subset(market, code, state):
    signal, = parse_market_status(response(market, code), NOW)
    assert signal.state == state and signal.market == market
    assert signal.checked_at == NOW and signal.ttl_seconds == 120


@pytest.mark.parametrize("code", [-1, 0, 207, 209, 210, 205, 1004, 1010, 2001, 99999, "202", True])
def test_unknown_special_and_security_codes_never_claim_open_or_closed(code):
    assert parse_market_status(response(code=code), NOW)[0].state == "unknown"


def test_security_quote_and_session_schedule_are_not_market_envelopes():
    for value in [SimpleNamespace(symbol="AAPL.US", trade_status=1004),
                  [SimpleNamespace(trade_status=204)], SimpleNamespace(sessions=[])]:
        with pytest.raises(ValueError):
            parse_market_status(value, NOW)
    assert get_market_session("US", NOW).is_regular_session
    assert parse_market_status(response("SG", 105), NOW) == []
    assert parse_market_status(response("HK", 202), NOW)[0].state == "unknown"
    with pytest.raises(ValueError):
        parse_market_status(response(), NOW.replace(tzinfo=None))


def test_duplicate_market_rows_fail_closed():
    assert parse_market_status(SimpleNamespace(market_time=response().market_time * 2), NOW)[0].state == "unknown"


def provider_fixture(monkeypatch, payload):
    clock = [NOW]
    provider = LongbridgeProvider(clock=lambda: clock[0])
    calls = []
    def request():
        calls.append(True)
        if isinstance(payload[0], Exception):
            raise payload[0]
        return payload[0]
    monkeypatch.setattr(provider, "_get_dashboard_context", lambda kind: SimpleNamespace(market_status=request))
    return provider, clock, calls


def test_refresh_throttle_expiry_unavailability_and_close(monkeypatch):
    payload = [response(code=204)]
    provider, clock, calls = provider_fixture(monkeypatch, payload)
    provider._refresh_market_state()
    assert get_market_session("US", clock[0]).session_state == "closed"
    assert get_market_session("HK", clock[0]).runtime_status == "unavailable"
    provider._refresh_market_state()
    assert len(calls) == 1
    clock[0] += timedelta(seconds=121)
    session = get_market_session("US", clock[0])
    assert session.is_regular_session and session.runtime_status == "expired"
    payload[0] = RuntimeError("fake private error must not be serialized")
    provider._refresh_market_state()
    assert get_market_session("US", clock[0]).runtime_status == "unavailable"
    assert provider._market_state_diagnostic == "market_signal_unavailable"
    payload[0] = response(code=204)
    clock[0] += timedelta(seconds=60)
    provider._refresh_market_state()
    provider.close()
    assert get_market_session("US", clock[0]).is_regular_session


@pytest.mark.parametrize("day,code,state,diagnostic", [
    ("2026-10-08", 202, "regular", None),
    ("2026-10-08", 204, "closed", "calendar_provider_conflict"),
    ("2026-11-26", 202, "unknown", "calendar_provider_conflict"),
    ("2026-11-26", 204, "holiday", None),
    ("2027-01-04", 202, "unknown", "calendar_provider_conflict"),
    ("2027-01-04", 204, "closed", "calendar_provider_conflict"),
    ("2027-01-04", 99999, "unknown", "provider_status_unknown"),
])
def test_precedence_and_health(monkeypatch, day, code, state, diagnostic):
    provider, clock, _ = provider_fixture(monkeypatch, [response(code=code)])
    clock[0] = datetime.fromisoformat(day + "T15:00:00+00:00")
    provider._refresh_market_state()
    session = get_market_session("US", clock[0])
    assert session.session_state == state and session.diagnostic_code == diagnostic
    view = evaluate("US", {"received_at": clock[0]}, clock[0], True, True)
    assert view["runtime_status"] == ("unknown" if diagnostic else "healthy")
    assert view["runtime_observed_at"] == clock[0].isoformat()


def test_provider_health_serialization_and_contract_unchanged(monkeypatch):
    provider, clock, _ = provider_fixture(monkeypatch, [response(code=204)])
    provider._refresh_market_state()
    provider._context = object()
    provider._realtime_observations["US"] = {"received_at": clock[0]}
    view = provider.provider_health()
    entry = view["realtime"]["US"]
    assert entry["status"] == "supported" and not entry["usable"]
    assert entry["runtime"]["market_signal_diagnostic"] == "market_signal_observed"
    assert entry["runtime"]["market_state"] == "closed"
    assert "private" not in json.dumps(view)


def test_security_halt_cannot_publish_even_when_quoted(monkeypatch):
    provider, clock, _ = provider_fixture(monkeypatch, [SimpleNamespace(symbol="AAPL.US", trade_status=1004)])
    provider._refresh_market_state()
    assert get_market_session("US", clock[0]).is_regular_session
    assert provider._market_state_diagnostic == "market_signal_unavailable"
