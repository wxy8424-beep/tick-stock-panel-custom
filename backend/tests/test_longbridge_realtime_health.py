"""Fake clocks and SDK snapshots only; no credentials, network or sleeps."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.market_session import (
    MarketRuntimeSignal,
    cache_market_signal,
    clear_market_signals,
    get_market_session,
)
from app.plugins.longbridge import provider as lb
from app.plugins.longbridge import realtime_health as health


@pytest.fixture
def runtime(monkeypatch):
    now = [datetime(2026, 10, 9, 14, tzinfo=UTC)]
    context = SimpleNamespace()
    calls = []

    def quote(symbols):
        calls.append(symbols)
        return [SimpleNamespace(symbol=s, last_done=100, prev_close=99, open=99,
                                high=101, low=98, turnover=1000,
                                timestamp=now[0] - timedelta(days=1)) for s in symbols]

    context.quote = quote
    context.static_info = lambda symbols: []
    created = []
    def create(config):
        created.append(context)
        return context
    monkeypatch.setattr(lb, "_credentials", lambda: ("fake-key", "fake-secret", "fake-token"))
    monkeypatch.setattr(lb, "_sdk", lambda: SimpleNamespace(
        Config=SimpleNamespace(from_apikey=lambda *args, **kwargs: object()), QuoteContext=create))
    monkeypatch.setattr(health, "get_market_session", lambda *args: SimpleNamespace(session_state="regular", calendar_status="unknown"))
    return lb.LongbridgeProvider(clock=lambda: now[0]), now, context, calls, created


def entry(provider, market="US"):
    return provider.provider_health()["realtime"][market]


def test_provider_health_uses_cached_market_signal_and_keeps_contract(runtime, monkeypatch):
    provider, now, *_ = runtime
    monkeypatch.setattr(health, "get_market_session", get_market_session)
    provider.get_realtime(["AAPL.US"])
    assert entry(provider)["runtime"]["calendar_status"] == "covered"
    assert entry(provider)["runtime"]["market_state"] == "regular"
    try:
        cache_market_signal(MarketRuntimeSignal("US", "closed", now[0], "verified_provider"))
        result = entry(provider)
        assert result["status"] == "supported"
        assert result["runtime"]["diagnostic_code"] == "market_state_unknown"
        assert result["runtime"]["market_diagnostic_code"] == "calendar_provider_conflict"
        assert result["runtime"]["calendar_coverage"]["calendar_year"] == 2026
        now[0] += timedelta(seconds=121)
        assert entry(provider)["runtime"]["runtime_status"] == "stale"
        assert not entry(provider)["usable"]
    finally:
        clear_market_signals()


def test_first_and_repeated_receipts_keep_event_time_distinct(runtime):
    provider, now, _, calls, created = runtime
    assert entry(provider)["runtime"]["runtime_status"] == "no_data"
    provider.get_realtime(["AAPL.US", "AAPL.US"])
    first = entry(provider)["runtime"]
    assert first["last_received_at"] == now[0].isoformat()
    assert first["last_event_at"] == (now[0] - timedelta(days=1)).isoformat()
    assert first["runtime_status"] == "healthy"
    assert first["subscription_state"] == "not_used_snapshot"
    assert first["reconnect_state"] == "unobservable"
    now[0] += timedelta(seconds=10)
    provider.get_realtime(["AAPL.US"])
    assert entry(provider)["runtime"]["last_received_at"] == now[0].isoformat()
    assert calls == [["AAPL.US"], ["AAPL.US"]] and len(created) == 1


@pytest.mark.parametrize("state,age,status,code", [
    ("regular", 120, "healthy", "realtime_healthy"),
    ("regular", 121, "stale", "realtime_stale"),
    ("closed", 5000, "healthy", "market_closed"),
    ("pre_open", 5000, "healthy", "market_closed"),
    ("break", 5000, "healthy", "market_closed"),
    ("unknown", 1, "unknown", "market_state_unknown"),
    ("regular", -1, "unknown", "market_state_unknown"),
])
def test_freshness_session_and_clock_rules(runtime, monkeypatch, state, age, status, code):
    provider, now, *_ = runtime
    provider.get_realtime(["AAPL.US"])
    now[0] += timedelta(seconds=age)
    monkeypatch.setattr(health, "get_market_session", lambda *args: SimpleNamespace(session_state=state, calendar_status="unknown"))
    result = entry(provider)
    assert result["status"] == "supported"
    assert result["runtime"]["runtime_status"] == status
    assert result["runtime"]["diagnostic_code"] == code
    assert result["usable"] == (status == "healthy")
    assert result["runtime"]["evaluated_at"] == now[0].isoformat()


def test_missing_context_redacts_and_retries_only_next_explicit_call(runtime, monkeypatch, caplog):
    provider, _, _, _, created = runtime
    monkeypatch.setattr(lb, "_credentials", lambda: ("", "", ""))
    assert provider.get_realtime(["AAPL.US"]) == []
    result = entry(provider)["runtime"]
    assert result["runtime_status"] == "unavailable"
    assert result["diagnostic_code"] == "context_unavailable"
    assert result["last_error_code"] == "realtime_authentication_failed"
    assert not created
    monkeypatch.setattr(lb, "_credentials", lambda: ("fake-key", "fake-secret", "fake-token"))
    provider.get_realtime(["AAPL.US"])
    assert entry(provider)["runtime"]["runtime_status"] == "healthy"
    assert len(created) == 1 and "fake-secret" not in caplog.text


@pytest.mark.parametrize("payload", [None, [], object(), [object()]])
def test_empty_or_malformed_response_isolated(runtime, monkeypatch, payload):
    provider, _, context, *_ = runtime
    monkeypatch.setattr(context, "quote", lambda symbols: payload)
    assert provider.get_realtime(["AAPL.US"]) == []
    assert entry(provider)["runtime"]["last_received_at"] is None
    assert entry(provider)["status"] == "supported"


def test_single_symbol_error_retains_other_market_and_recent_valid_receipt(runtime, monkeypatch):
    provider, now, context, *_ = runtime
    provider.get_realtime(["AAPL.US", "700.HK"])
    before = entry(provider)["runtime"]["last_received_at"]
    def failed(symbols):
        raise RuntimeError("network fake-secret-marker")
    monkeypatch.setattr(context, "quote", failed)
    now[0] += timedelta(seconds=10)
    provider.get_realtime(["BAD.US"])
    assert entry(provider)["runtime"]["runtime_status"] == "healthy"
    assert entry(provider)["runtime"]["last_received_at"] == before
    assert entry(provider)["runtime"]["last_error_code"] == "realtime_network_error"
    assert entry(provider, "HK")["runtime"]["last_error_code"] is None
    assert "fake-secret-marker" not in str(provider.provider_health())
    now[0] += timedelta(seconds=121)
    assert entry(provider)["runtime"]["runtime_status"] == "stale"


def test_partial_batches_keep_success_and_independent_markets(runtime, monkeypatch):
    provider, _, context, _, _ = runtime
    original = context.quote
    count = [0]
    def quote(symbols):
        count[0] += 1
        if count[0] == 2:
            raise RuntimeError("network failure")
        return original(symbols)
    monkeypatch.setattr(context, "quote", quote)
    rows = provider.get_realtime([*[f"S{i}.US" for i in range(500)], "700.HK"])
    assert len(rows) == 500 and count[0] == 2
    assert entry(provider)["runtime"]["runtime_status"] == "healthy"
    assert entry(provider, "HK")["runtime"]["runtime_status"] == "unavailable"
    assert entry(provider, "CN")["runtime"]["runtime_status"] == "no_data"


def test_cleanup_clears_health_and_releases_context(runtime):
    provider, _, _, _, created = runtime
    provider.get_realtime(["600519.SH", "700.HK", "AAPL.US"])
    provider.close()
    provider.close()
    assert provider._context is None and provider._metadata == {} and provider.last_errors == []
    for market in ("CN", "HK", "US"):
        assert entry(provider, market)["runtime"]["last_received_at"] is None
        assert not entry(provider, market)["runtime"]["context_initialized"]
    provider.get_realtime(["AAPL.US"])
    assert len(created) == 2


def test_health_reads_never_request_sdk_and_keep_blockers(runtime, monkeypatch):
    provider, _, context, *_ = runtime
    provider.get_realtime(["AAPL.US"])
    monkeypatch.setattr(context, "quote", lambda symbols: pytest.fail("health requested SDK"))
    for _ in range(3):
        matrix = provider.provider_health()
        assert matrix["realtime"]["US"]["runtime"]["runtime_status"] == "healthy"
        assert matrix["financial"]["US"]["status"] == "contract_blocked"
        assert matrix["daily"]["US"]["status"] == "contract_blocked"
    assert entry(provider)["runtime"]["connection_state"] == "unknown"
    assert not provider.provider_health(available=False)["realtime"]["US"]["usable"]


def test_parser_exception_cannot_kill_other_symbols_or_markets(runtime, monkeypatch, caplog):
    provider, _, context, *_ = runtime
    good = context.quote(["AAPL.US"])[0]
    class Broken:
        symbol = "700.HK"
        @property
        def last_done(self):
            raise RuntimeError("fake-secret-marker")
    monkeypatch.setattr(context, "quote", lambda symbols: [Broken(), good])
    assert [row["symbol"] for row in provider.get_realtime(["700.HK", "AAPL.US"])] == ["AAPL.US"]
    assert entry(provider)["runtime"]["last_error_code"] is None
    assert entry(provider, "HK")["runtime"]["last_error_code"] == "realtime_parse_error"
    assert "fake-secret-marker" not in caplog.text + str(provider.provider_health())
