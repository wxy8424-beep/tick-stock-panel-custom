"""实时市场时钟、DST 和 CN 专属调度边界。"""
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import app.services.quote_service as qs_module
from app.market_session import get_market_session, market_from_symbol
from app.market_time import in_continuous_session
from app.services.quote_service import QuoteService


@pytest.mark.parametrize(("market", "clock", "state"), [
    ("CN", "09:29", "pre_open"), ("CN", "09:30", "regular"),
    ("CN", "11:30", "regular"), ("CN", "11:31", "break"),
    ("CN", "13:00", "regular"), ("CN", "15:00", "regular"),
    ("CN", "15:01", "closed"),
    ("HK", "09:29", "pre_open"), ("HK", "09:30", "regular"),
    ("HK", "12:00", "regular"), ("HK", "12:01", "break"),
    ("HK", "13:00", "regular"), ("HK", "16:00", "regular"),
    ("HK", "16:01", "post_market"),
    ("US", "09:29", "pre_open"), ("US", "09:30", "regular"),
    ("US", "16:00", "regular"), ("US", "16:01", "post_market"),
])
def test_clock_boundaries(market, clock, state):
    zones = {"CN": "Asia/Shanghai", "HK": "Asia/Hong_Kong", "US": "America/New_York"}
    hour, minute = map(int, clock.split(":"))
    local = datetime(2026, 8, 26, hour, minute, tzinfo=ZoneInfo(zones[market]))
    result = get_market_session(market, local.astimezone(UTC))
    assert result.timezone.key == zones[market]
    assert result.local_datetime == local and result.local_date == local.date()
    assert result.session_state == state
    assert result.is_regular_session is (state == "regular")
    assert result.calendar_status == "covered" and result.confirmed_trading_day is True
    if market == "CN":
        assert result.is_regular_session == in_continuous_session(local)


@pytest.mark.parametrize("market", ["CN", "HK", "US"])
def test_weekend_is_closed_without_claiming_calendar_confirmation(market):
    zone = get_market_session(market).timezone
    local = datetime(2026, 8, 29, 10, tzinfo=zone)
    result = get_market_session(market, local)
    assert result.session_state == "closed" and not result.is_regular_session
    assert result.calendar_status == "covered" and result.confirmed_trading_day is False


@pytest.mark.parametrize(("day", "utc_hour", "offset"), [(15, 14, -5), (15, 13, -4)])
def test_new_york_winter_and_summer_dst(day, utc_hour, offset):
    month = 1 if offset == -5 else 7
    utc = datetime(2026, month, day, utc_hour, 30, tzinfo=UTC)
    result = get_market_session("US", utc)
    assert result.local_datetime.hour == 9 and result.local_datetime.minute == 30
    assert result.local_datetime.utcoffset() == timedelta(hours=offset)
    assert result.is_regular_session


def test_simultaneous_markets_and_local_dates_are_independent():
    utc = datetime(2026, 7, 15, 15, tzinfo=UTC)
    assert {m: get_market_session(m, utc).session_state for m in ("CN", "HK", "US")} == {
        "CN": "closed", "HK": "closed", "US": "regular",
    }
    assert get_market_session("US", utc).local_datetime.hour == 11
    next_day = datetime(2026, 7, 15, 17, tzinfo=UTC)
    assert get_market_session("CN", next_day).local_date.day == 16
    assert get_market_session("US", next_day).local_date.day == 15
    # 港股收盘比 A 股晚, 同一瞬间也能独立判断。
    utc = datetime(2026, 7, 15, 7, 30, tzinfo=UTC)
    assert not get_market_session("CN", utc).is_regular_session
    assert get_market_session("HK", utc).is_regular_session


@pytest.mark.parametrize(("symbol", "market"), [
    ("600519.SH", "CN"), ("000001.SZ", "CN"), ("430047.BJ", "CN"),
    ("700.HK", "HK"), ("AAPL.US", "US"), ("ABC.UNKNOWN", None),
    ("ABC.SH", None), ("\uff11\uff12\uff13\uff14\uff15\uff16.SH", None), (None, None),
])
def test_symbol_market_uses_existing_safe_boundary(symbol, market):
    assert market_from_symbol(symbol) == market
    groups = QuoteService._partition_realtime_records([{"symbol": symbol}])
    assert [m for m, rows in groups.items() if rows] == ([market] if market else [])


def test_unknown_market_and_naive_clock_rejected():
    with pytest.raises(ValueError, match="market"):
        get_market_session("UNKNOWN")
    with pytest.raises(ValueError, match="timezone"):
        get_market_session("US", datetime(2026, 7, 15, 10))


def test_service_foreign_poll_readiness_does_not_use_cn_phase_or_calendar(monkeypatch):
    qs = QuoteService()
    utc = datetime(2026, 7, 15, 15, tzinfo=UTC)
    monkeypatch.setattr(qs, "get_market_session", lambda market: get_market_session(market, utc))

    def forbidden(*args):
        pytest.fail("HK/US readiness entered CN phase, final or calendar")

    for name in ("_market_phase", "_holiday_gate", "_final_sync_key"):
        monkeypatch.setattr(qs, name, forbidden)
    assert qs._should_poll_for_market("US")
    assert not qs._should_poll_for_market("HK")
    assert not qs._should_poll_for_market("UNKNOWN")
    assert qs._final_sync_done == set() and qs._last_final_confirmed is None


def test_service_cn_final_and_holiday_guard_unchanged(monkeypatch):
    qs = QuoteService()
    monkeypatch.setattr(qs, "_holiday_gate", lambda: True)
    monkeypatch.setattr(qs_module, "cn_now", lambda: datetime(
        2026, 8, 26, 11, 30, tzinfo=ZoneInfo("Asia/Shanghai"),
    ))
    assert qs._market_phase() == "morning_final"
    assert qs.get_market_session("CN", qs_module.cn_now()).is_regular_session
    assert qs._should_poll_for_market("CN", cn_phase="morning")
    assert qs._should_poll_for_market("CN", cn_phase="morning_final")
    qs._final_sync_done.add(qs._final_sync_key("morning_final"))
    assert not qs._should_poll_for_market("CN", cn_phase="morning_final")
    monkeypatch.setattr(qs, "_holiday_gate", lambda: False)
    assert not qs._should_poll_for_market("CN", cn_phase="morning")
    assert not qs._should_poll_for_market("CN", cn_phase="close_final")


@pytest.mark.parametrize(("market", "hour", "minute", "state"), [
    ("CN", 11, 30, "break"), ("CN", 15, 0, "closed"),
    ("HK", 12, 0, "break"), ("HK", 16, 0, "post_market"),
    ("US", 16, 0, "post_market"),
])
def test_session_end_does_not_include_following_seconds(market, hour, minute, state):
    zone = get_market_session(market).timezone
    result = get_market_session(market, datetime(2026, 8, 26, hour, minute, 1, tzinfo=zone))
    assert result.session_state == state


def test_foreign_regular_does_not_start_cn_fetch_in_poll_loop(monkeypatch):
    qs = QuoteService()
    qs._running = qs._enabled = True
    utc = datetime(2026, 7, 15, 15, tzinfo=UTC)
    monkeypatch.setattr(qs, "get_market_session", lambda market: get_market_session(market, utc))
    monkeypatch.setattr(qs, "_market_phase", lambda: "closed")
    monkeypatch.setattr(qs, "_holiday_gate", lambda: True)

    def fetch_forbidden(**kwargs):
        pytest.fail("US regular triggered a CN fetch/final")

    monkeypatch.setattr(qs, "_fetch_quotes", fetch_forbidden)
    monkeypatch.setattr(qs_module.time, "sleep", lambda seconds: setattr(qs, "_running", False))
    assert qs._should_poll_for_market("US")
    qs._poll_loop()
    assert qs._final_sync_done == set() and qs._last_final_confirmed is None
