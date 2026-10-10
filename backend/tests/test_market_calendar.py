"""Offline exchange dates, runtime precedence and health share one resolver."""
from datetime import UTC, datetime, timedelta

import pytest

from app.market_calendar import CALENDARS
from app.market_session import (
    MarketRuntimeSignal,
    cache_market_signal,
    clear_market_signals,
    get_market_session,
)
from app.plugins.longbridge.realtime_health import evaluate
from app.services.quote_service import QuoteService


def at(market, day, clock="10:00"):
    zone = get_market_session(market).timezone
    return datetime.fromisoformat(f"{day}T{clock}").replace(tzinfo=zone)


@pytest.fixture(autouse=True)
def isolated_signal_cache():
    clear_market_signals()
    yield
    clear_market_signals()


@pytest.mark.parametrize("market,day", [
    ("CN", "2026-02-23"), ("CN", "2026-05-05"), ("CN", "2026-10-07"),
    ("HK", "2026-04-07"), ("HK", "2026-10-19"),
    ("US", "2026-07-03"), ("US", "2026-11-26"),
])
def test_official_holidays_never_become_regular(market, day):
    session = get_market_session(market, at(market, day))
    assert session.session_state == "holiday"
    assert session.confirmed_trading_day is False
    assert not session.is_regular_session


@pytest.mark.parametrize("market", ["CN", "HK", "US"])
@pytest.mark.parametrize("day", ["2025-12-31", "2027-01-04", "2027-01-02"])
def test_uncovered_weekday_or_weekend_is_unknown(market, day):
    session = get_market_session(market, at(market, day))
    assert session.session_state == "unknown"
    assert session.confirmed_trading_day is None
    assert session.calendar_status == "out_of_coverage"
    assert session.diagnostic_code == "calendar_out_of_coverage"


def test_coverage_is_auditable_and_not_a_live_market_claim():
    metadata = get_market_session("HK", at("HK", "2026-10-08")).public_metadata()
    assert metadata["runtime_status"] == "unavailable"
    assert metadata["state_source"] == "official_calendar"
    for calendar in CALENDARS.values():
        view = calendar.metadata()
        assert view["calendar_year"] == 2026
        assert view["coverage_start"] == "2026-01-01"
        assert view["coverage_end"] == "2026-12-31"
        assert view["source"] and view["last_updated"]


@pytest.mark.parametrize("day", ["2026-02-16", "2026-12-24", "2026-12-31"])
def test_hk_half_day_has_no_afternoon_or_lunch(day):
    session = get_market_session("HK", at("HK", day, "11:00"))
    assert session.is_regular_session and session.half_day
    assert session.early_close == "12:00"
    assert get_market_session("HK", at("HK", day, "12:01")).session_detail == "closing_auction_window"
    assert get_market_session("HK", at("HK", day, "12:10")).session_state == "closed"
    assert get_market_session("HK", at("HK", day, "13:30")).session_state == "closed"


@pytest.mark.parametrize("day", ["2026-11-27", "2026-12-24"])
def test_us_early_close_and_late_session(day):
    session = get_market_session("US", at("US", day, "12:59"))
    assert session.is_regular_session and session.early_close == "13:00"
    assert get_market_session("US", at("US", day, "13:00:01")).session_state == "post_market"
    assert get_market_session("US", at("US", day, "17:00")).session_state == "closed"


@pytest.mark.parametrize("clock,state", [("03:59", "closed"), ("04:00", "pre_open"),
                                         ("09:30", "regular"), ("16:01", "post_market"),
                                         ("20:00", "closed")])
def test_us_day_session(clock, state):
    assert get_market_session("US", at("US", "2026-10-08", clock)).session_state == state


@pytest.mark.parametrize("day,clock", [("2026-12-06", "21:00"), ("2026-12-07", "02:00")])
def test_announced_unverified_overnight_never_claims_closed(day, clock):
    result = get_market_session("US", at("US", day, clock))
    assert result.session_state == "unknown"
    assert result.session_detail == "overnight_session_unverified"


@pytest.mark.parametrize("month,day,hour", [(3, 6, 14), (3, 9, 13), (10, 30, 13), (11, 2, 14)])
def test_dst_transition_adjacent_trading_days(month, day, hour):
    session = get_market_session("US", datetime(2026, month, day, hour, 30, tzinfo=UTC))
    assert session.local_datetime.hour == 9 and session.is_regular_session


def test_confirmed_closure_overrides_schedule_and_reports_conflict():
    now = at("HK", "2026-10-08")
    cache_market_signal(MarketRuntimeSignal("HK", "closed", now, "verified_provider"))
    result = get_market_session("HK", now)
    assert result.session_state == "closed"
    assert result.diagnostic_code == "calendar_provider_conflict"
    assert get_market_session("CN", now).is_regular_session


@pytest.mark.parametrize("state", ["regular", "unknown"])
def test_provider_cannot_silently_open_official_holiday(state):
    now = at("US", "2026-11-26")
    signal = MarketRuntimeSignal("US", state, now, "verified_provider")
    session = get_market_session("US", now, runtime_signal=signal)
    assert session.session_state == "unknown"
    assert session.diagnostic_code == ("calendar_provider_conflict" if state == "regular" else "provider_status_unknown")


def test_signal_expiry_future_timestamp_and_out_of_order_cache():
    now = at("US", "2026-10-08")
    signal = MarketRuntimeSignal("US", "closed", now, "verified_provider")
    cache_market_signal(signal)
    cache_market_signal(MarketRuntimeSignal("US", "regular", now - timedelta(seconds=1), "verified_provider"))
    assert get_market_session("US", now).session_state == "closed"
    for clock in [now - timedelta(seconds=1), now + timedelta(seconds=121)]:
        assert get_market_session("US", clock).diagnostic_code == "provider_status_expired"
        assert get_market_session("US", clock).is_regular_session


def test_security_halt_and_raw_integer_codes_cannot_become_market_signals():
    now = at("US", "2026-10-08")
    for kwargs in [{"scope": "security"}, {"state": "Halted"}, {"state": 0}]:
        values = {"market": "US", "state": "closed", "checked_at": now, "source": "verified_provider"}
        values.update(kwargs)
        with pytest.raises(ValueError):
            MarketRuntimeSignal(**values)
    assert get_market_session("US", now).is_regular_session


@pytest.mark.parametrize("market,day,clock,state", [
    ("CN", "2026-10-08", "10:00", "regular"),
    ("CN", "2026-10-08", "12:00", "break"),
    ("HK", "2026-10-08", "12:30", "break"),
    ("US", "2026-10-08", "08:00", "pre_open"),
    ("US", "2026-10-08", "17:00", "post_market"),
    ("US", "2026-11-26", "10:00", "holiday"),
    ("US", "2026-10-10", "10:00", "closed"),
    ("US", "2027-01-04", "10:00", "unknown"),
])
def test_health_uses_authoritative_session_without_network(market, day, clock, state):
    now = at(market, day, clock)
    result = evaluate(market, {"received_at": now - timedelta(hours=1)}, now, True, True)
    assert result["market_state"] == state
    assert result["runtime_status"] == ("stale" if state == "regular" else "unknown" if state == "unknown" else "healthy")
    assert result["calendar_coverage"]["calendar_year"] == 2026


def test_cn_calendar_stops_ingestion_without_touching_final_boundaries(monkeypatch):
    monkeypatch.setattr("app.services.quote_service.cn_now", lambda: at("CN", "2026-10-01"))
    monkeypatch.setattr("app.services.trading_day.is_trading_day", lambda: True)
    service = QuoteService()
    assert not service._should_poll_for_phase("morning")
    assert not service._should_poll_for_phase("close_final")
    assert service._final_sync_done == set()
    assert not service._is_continuous_trading()
    assert service.status()["market"]["session_state"] == "holiday"


def test_temporary_cn_closure_stops_polling_but_normal_after_close_allows_final(monkeypatch):
    now = at("CN", "2026-10-08")
    monkeypatch.setattr("app.services.quote_service.cn_now", lambda: now)
    monkeypatch.setattr("app.services.trading_day.is_trading_day", lambda: True)
    cache_market_signal(MarketRuntimeSignal("CN", "closed", now, "verified_provider"))
    assert not QuoteService()._should_poll_for_phase("morning")
    clear_market_signals()
    now = at("CN", "2026-10-08", "15:01")
    assert QuoteService()._should_poll_for_phase("close_final")
