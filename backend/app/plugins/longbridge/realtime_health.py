"""Cached snapshot diagnostics; never infer a socket state or request SDK data."""
from datetime import UTC, datetime
from typing import TypedDict

from app.market_session import get_market_session

# Several normal 30s polling cycles; reception health, not exchange tick latency.
FRESHNESS_SECONDS = 120
ERROR_CODES = {
    "authentication": "realtime_authentication_failed",
    "quote_permission": "realtime_permission_denied",
    "symbol": "realtime_symbol_error",
    "network": "realtime_network_error",
    "invalid_response_fields": "realtime_parse_error",
}
MESSAGES = {
    "realtime_healthy": "正常",
    "realtime_stale": "数据延迟",
    "realtime_no_data": "无最近数据",
    "market_closed": "非正常交易时段,不要求新快照",
    "market_state_unknown": "市场状态未确认",
    "context_unavailable": "行情上下文不可用",
    "realtime_authentication_failed": "当前认证不可用",
    "realtime_permission_denied": "当前行情权限不足",
    "realtime_symbol_error": "当前标的行情不可用",
    "realtime_network_error": "最近行情请求网络异常",
    "realtime_parse_error": "最近行情响应字段无效",
    "realtime_sdk_error": "最近行情请求异常",
}


class Observation(TypedDict, total=False):
    received_at: datetime
    event_at: datetime
    checked_at: datetime
    error_code: str | None
    context_failed: bool


def evaluate(market: str, observation: Observation, now: datetime,
             context_initialized: bool, available: bool) -> dict:
    """One evaluation clock; raw errors and credentials cannot enter this view."""
    received = observation.get("received_at")
    event = observation.get("event_at")
    try:
        session = get_market_session(market, now)
        market_state = session.session_state
        calendar_status = session.calendar_status
    except (ValueError, KeyError, OSError):
        market_state, calendar_status = "unknown", "unknown"
    error = observation.get("error_code")
    error = error if error in MESSAGES else None
    if not available or observation.get("context_failed"):
        status, code = "unavailable", "context_unavailable"
    elif market_state not in {"regular", "closed", "pre_open", "break"}:
        status, code = "unknown", "market_state_unknown"
    elif received is None:
        status, code = ("unavailable", error) if error else ("no_data", "realtime_no_data")
    elif market_state != "regular":
        status, code = "healthy", "market_closed"
    elif (now - received).total_seconds() < 0:
        status, code = "unknown", "market_state_unknown"
    elif (now - received).total_seconds() > FRESHNESS_SECONDS:
        status, code = "stale", "realtime_stale"
    else:
        status, code = "healthy", "realtime_healthy"
    return {
        "availability": "available" if status == "healthy" else "unavailable" if status == "unavailable" else "not_checked",
        "runtime_status": status, "diagnostic_code": code, "message": MESSAGES[code],
        "last_checked": observation["checked_at"].isoformat() if observation.get("checked_at") else None,
        "symbol": None, "last_received_at": received.isoformat() if received else None,
        "last_event_at": event.isoformat() if event else None, "evaluated_at": now.isoformat(),
        "market_state": market_state, "calendar_status": calendar_status,
        "context_initialized": context_initialized, "subscription_state": "not_used_snapshot",
        # No public SDK socket/reconnect observer: unknown is deliberate.
        "connection_state": "unknown", "reconnect_state": "unobservable",
        "last_error_code": error, "freshness_threshold_seconds": FRESHNESS_SECONDS,
    }


def utc_now() -> datetime:
    return datetime.now(UTC)
