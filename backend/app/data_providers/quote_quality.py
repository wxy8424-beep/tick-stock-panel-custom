"""Observational quote validation; no capability, unit conversion or row mutation."""
import math
from datetime import UTC, datetime
from decimal import Decimal

from app.data_providers.contracts import QUANTITY_UNITS
from app.market_session import get_market_session, market_from_symbol

EVENT_FRESHNESS_SECONDS = 120
_SEVERITY = {"valid": 0, "unknown": 1, "warning": 2, "stale": 3, "invalid": 4}


def _finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        return value if math.isfinite(value) else None
    except (ValueError, OverflowError):
        return None


def validate_quote(row: dict, observed_at: datetime, *, provider_volume=None) -> dict:
    """Validate standard Unix-ms timestamps; latency means event age, not network RTT.

    Missing/unsupported units remain unknown. No price jump or turnover-based
    volume heuristics. Market session is the existing resolver, never local time.
    """
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must include timezone")
    state, warnings = "valid", []

    def note(code, severity="unknown"):
        nonlocal state
        warnings.append(code)
        if _SEVERITY[severity] > _SEVERITY[state]:
            state = severity

    market = market_from_symbol(row.get("symbol"))
    if market is None or row.get("market") != market:
        note("quote_market_unknown")
        session = None
    else:
        session = get_market_session(market, observed_at)
        if session.session_state == "unknown" or session.diagnostic_code == "calendar_provider_conflict":
            note("quote_market_unknown")

    prices = {}
    for field in ("last_price", "prev_close", "open", "high", "low"):
        raw = row.get(field)
        value = _finite(raw)
        # OHLC/previous zero can be a no-trade placeholder, not a proven price.
        if raw is None or (field != "last_price" and value == 0):
            note(f"{field}_unknown")
        elif value is None or value <= 0:
            note(f"{field}_invalid", "invalid")
        else:
            prices[field] = value
    high, low = prices.get("high"), prices.get("low")
    if (high is not None and low is not None
            and (high < low or any(not low <= prices[field] <= high
                                  for field in ("open", "last_price") if field in prices))):
        note("ohlc_inconsistent", "invalid")
    # Standard volume only: null unsupported/unverified must not become zero/shares.
    volume = row.get("volume")
    value = _finite(volume)
    if volume is None:
        note("volume_unknown")
    elif value is None or value < 0:
        note("volume_invalid", "invalid")
    if row.get("volume_unit") not in QUANTITY_UNITS - {"unknown"}:
        note("volume_unit_unknown")
    if provider_volume is not None:
        raw_volume = _finite(provider_volume)
        if raw_volume is None or raw_volume < 0:
            note("provider_volume_invalid", "invalid")

    event = None
    raw = row.get("timestamp")
    timestamp = _finite(raw)
    if raw is None:
        note("timestamp_unknown")
    elif timestamp is None or timestamp <= 0:
        note("timestamp_invalid", "invalid")
    else:
        try:
            event = datetime.fromtimestamp(float(timestamp) / 1000, UTC)
        except (ValueError, OverflowError, OSError):
            note("timestamp_invalid", "invalid")
    latency = None
    if event is not None:
        delay = (observed_at - event).total_seconds()
        if delay < 0:
            note("timestamp_future", "invalid")
        else:
            latency = round(delay * 1000)
            if session is not None:
                if session.session_state == "regular" and delay > EVENT_FRESHNESS_SECONDS:
                    note("quote_event_stale", "stale")
                # Historical closing snapshots are valid. A *recent* event in
                # a closed window is suspicious, not proof of a bad trade.
                elif (session.session_state in {"closed", "holiday"}
                      and delay <= EVENT_FRESHNESS_SECONDS
                      and get_market_session(market, event).session_state in {"closed", "holiday"}):
                    note("quote_during_closed_market", "warning")
    return {"state": state, "warnings": warnings, "observed_at": observed_at.isoformat(),
            "latency_ms": latency}


def aggregate_quality(reports: list[dict], observed_at: datetime) -> dict:
    """Bounded per-market summary; no symbols, raw values or credentials retained."""
    if not reports:
        return {"state": "unknown", "warnings": ["quote_not_observed"],
                "observed_at": None, "latency_ms": None, "quote_count": 0}
    counts = {key: sum(report["state"] == key for report in reports) for key in _SEVERITY}
    ages = []
    for report in reports:
        if report["latency_ms"] is not None:
            # Align all batch receipt clocks to the final aggregation clock.
            receipt = datetime.fromisoformat(report["observed_at"])
            ages.append(report["latency_ms"] + round((observed_at - receipt).total_seconds() * 1000))
    return {"state": max((report["state"] for report in reports), key=_SEVERITY.get),
            "warnings": sorted({code for report in reports for code in report["warnings"]}),
            "observed_at": observed_at.isoformat(), "latency_ms": max(ages) if ages else None,
            "quote_count": len(reports), "counts": counts}


def quality_view(report: dict | None, available: bool) -> dict:
    """Additive health view; reception freshness and quote quality stay distinct."""
    if not available:
        return {"state": "unknown", "warnings": ["provider_unavailable"],
                "observed_at": None, "latency_ms": None, "quote_count": 0}
    if report is None:
        return aggregate_quality([], datetime.now(UTC))
    return {**report, "warnings": list(report["warnings"]), "counts": dict(report.get("counts", {}))}
