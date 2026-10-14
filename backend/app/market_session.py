"""Unified cash-equity session resolver: official offline calendar + scoped signals.

No SDK/network calls. Calendar states describe scheduled sessions, not individual
security availability; CN final processing remains a separate ingestion contract.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from threading import RLock
from zoneinfo import ZoneInfo

from app.market_calendar import CALENDARS

_ZONES = {market: calendar.timezone for market, calendar in CALENDARS.items()}
_SUFFIX_MARKETS = {"SH": "CN", "SZ": "CN", "BJ": "CN", "HK": "HK", "US": "US"}
_STATES = {"pre_open", "regular", "break", "post_market", "closed", "holiday", "unknown"}
_SIGNALS: dict[str, MarketRuntimeSignal] = {}
_SIGNAL_LOCK = RLock()


@dataclass(frozen=True)
class MarketRuntimeSignal:
    """Only verified market-level semantics; never raw SDK codes/security halts."""

    market: str
    state: str
    checked_at: datetime
    source: str
    scope: str = "market"
    ttl_seconds: int = 120

    def __post_init__(self):
        if (self.market not in _ZONES or self.state not in _STATES
                or self.scope != "market" or not self.source or self.ttl_seconds <= 0):
            raise ValueError("invalid market-level runtime signal")
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise ValueError("checked_at must include timezone")


def cache_market_signal(signal: MarketRuntimeSignal) -> None:
    """Feed only an independently verified status mapping, never quote absence."""
    with _SIGNAL_LOCK:
        previous = _SIGNALS.get(signal.market)
        if previous is None or signal.checked_at >= previous.checked_at:
            _SIGNALS[signal.market] = signal


def clear_market_signals() -> None:
    with _SIGNAL_LOCK:
        _SIGNALS.clear()


def remove_market_signals(source: str) -> None:
    """Remove only this publisher's observations on unavailability/shutdown."""
    with _SIGNAL_LOCK:
        for market, signal in list(_SIGNALS.items()):
            if signal.source == source:
                del _SIGNALS[market]


def replace_market_signals(source: str, signals: list[MarketRuntimeSignal]) -> None:
    """Publish one provider response atomically, including missing-market removal."""
    if any(signal.source != source for signal in signals):
        raise ValueError("runtime signal source mismatch")
    with _SIGNAL_LOCK:
        remove_market_signals(source)
        for signal in signals:
            cache_market_signal(signal)


def market_from_symbol(symbol: object) -> str | None:
    """复用实时入口的证券格式边界; 声明冲突仍由记录入口校验。"""
    if not isinstance(symbol, str) or "." not in symbol:
        return None
    code, _, suffix = symbol.rpartition(".")
    market = _SUFFIX_MARKETS.get(suffix)
    if not code or market is None:
        return None
    if market == "CN" and not (len(code) == 6 and code.isascii() and code.isdigit()):
        return None
    return market


@dataclass(frozen=True)
class MarketSession:
    market: str
    timezone: ZoneInfo
    local_datetime: datetime
    session_state: str
    calendar_status: str = "unknown"
    confirmed_trading_day: bool | None = None
    half_day: bool = False
    early_close: str | None = None
    session_detail: str | None = None
    state_source: str = "official_calendar"
    runtime_status: str = "unavailable"
    diagnostic_code: str | None = None
    runtime_observed_at: datetime | None = None
    calendar_metadata_json: str | None = None

    @property
    def local_date(self) -> date:
        return self.local_datetime.date()

    @property
    def is_regular_session(self) -> bool:
        return self.session_state == "regular"

    def public_metadata(self) -> dict:
        return {
            "code": self.market, "timezone": self.timezone.key,
            "local_time": self.local_datetime.isoformat(), "session_state": self.session_state,
            "calendar_status": self.calendar_status, "confirmed_trading_day": self.confirmed_trading_day,
            "calendar_coverage": (json.loads(self.calendar_metadata_json) if self.calendar_metadata_json
                                  else CALENDARS[self.market].metadata()),
            "half_day": self.half_day, "early_close": self.early_close,
            "session_detail": self.session_detail, "state_source": self.state_source,
            "runtime_status": self.runtime_status, "diagnostic_code": self.diagnostic_code,
            "runtime_observed_at": self.runtime_observed_at.isoformat() if self.runtime_observed_at else None,
        }


def get_market_session(market: str, now: datetime | None = None,
                       *, runtime_signal: MarketRuntimeSignal | None = None) -> MarketSession:
    """按一个绝对时刻计算市场时钟。拒绝 naive 时间, 不依赖机器本地时区。

    端点包含语义与原 CN continuous session 一致; CN final 的专属半开窗口
    不在本模型中改变。盘前/盘后只描述状态, 不授权 regular 轮询。
    """
    if market not in _ZONES:
        raise ValueError(f"unsupported market: {market}")
    now = now if now is not None else datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include timezone")
    result = get_calendar_session(CALENDARS[market], now)
    state = result.session_state
    if runtime_signal is None:
        with _SIGNAL_LOCK:
            runtime_signal = _SIGNALS.get(market)
    if runtime_signal is None:
        return result
    if runtime_signal.market != market:
        raise ValueError("runtime signal market mismatch")
    age = now - runtime_signal.checked_at
    if age < timedelta(0) or age > timedelta(seconds=runtime_signal.ttl_seconds):
        return replace(result, runtime_status="expired", diagnostic_code="provider_status_expired",
                       runtime_observed_at=runtime_signal.checked_at)
    provider_state = runtime_signal.state
    conflict = provider_state != state and provider_state != "unknown"
    if provider_state == "closed" and state == "holiday":
        return replace(result, runtime_status="verified", runtime_observed_at=runtime_signal.checked_at)
    # Explicit temporary closure wins. An opening signal cannot undo an official
    # holiday or validate an uncovered date; conflicting active states fail closed.
    chosen = provider_state if provider_state in {"closed", "holiday", "break", "unknown"} else state
    if conflict and provider_state not in {"closed", "holiday", "break"}:
        chosen = "unknown"
    return replace(result, session_state=chosen, state_source=runtime_signal.source,
                   runtime_observed_at=runtime_signal.checked_at,
                   runtime_status="verified" if provider_state != "unknown" else "unknown",
                   diagnostic_code="calendar_provider_conflict" if conflict else
                   "provider_status_unknown" if provider_state == "unknown" else result.diagnostic_code)


def get_calendar_session(calendar, now: datetime) -> MarketSession:
    """Replay one explicit frozen calendar; no global calendar or runtime signal reads."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include timezone")
    market = calendar.market
    rules = calendar.session
    zone = ZoneInfo(calendar.timezone)
    local = now.astimezone(zone)
    clock, day = local.time(), local.date()
    covered = calendar.coverage_start <= day <= calendar.coverage_end
    half_day = covered and day in calendar.half_days
    end = calendar.early_close if half_day else rules.regular_windows[-1][1]
    windows = tuple((start, min(close, end)) for start, close in rules.regular_windows if start <= end)
    state = "closed"
    detail = None
    trading_day = None if not covered else (day in calendar.additional_trading_days or (
        day.weekday() in calendar.trading_weekdays and day not in calendar.holidays))
    if not covered:
        state = "unknown"
    elif day in calendar.holidays:
        state = "holiday"
    elif trading_day:
        if any(start <= clock <= end for start, end in windows):
            state = "regular"
        elif rules.pre_open_start <= clock < windows[0][0]:
            state = "pre_open"
        elif windows[0][1] < clock < windows[-1][0]:
            state = "break"
        elif (rules.half_day_post_market_end if half_day else rules.post_market_end) is not None and (
                end < clock < (rules.half_day_post_market_end if half_day else rules.post_market_end)):
            state = "post_market"
        elif rules.closing_auction_minutes is not None and end < clock < (
                datetime.combine(day, end) + timedelta(minutes=rules.closing_auction_minutes)).time():
            state, detail = "post_market", "closing_auction_window"
        # Announced Nasdaq overnight launch remains outside this day-session contract.
        # Do not label a potentially active overnight venue "closed" after launch date.
    if (covered and rules.overnight_unverified_from is not None and day >= rules.overnight_unverified_from
            and (clock < rules.overnight_before or clock >= rules.overnight_after)):
        state, detail = "unknown", "overnight_session_unverified"
    result = MarketSession(
        market, zone, local, state, "covered" if covered else "out_of_coverage", trading_day,
        half_day, end.isoformat(timespec="minutes") if half_day else None, detail,
        diagnostic_code=None if covered else "calendar_out_of_coverage",
        calendar_metadata_json=json.dumps(calendar.metadata(), sort_keys=True),
    )
    return result
