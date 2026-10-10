"""Endpoint-specific unit evidence; successful reads are not evidence of units.

Reviewed SDK 5.2.0 and official docs on 2026-10-10. Volume is an integer,
but no market-specific shares/lot contract was established for these endpoints.
See docs/custom/longbridge-quantity-unit-evidence.md. No scaling or persistence.
"""
from __future__ import annotations

from app.data_providers.contracts import MARKETS
from app.market_session import market_from_symbol

REASONS = {
    "daily": "candlestick_volume_unit_evidence_missing",
    "minute": "minute_candlestick_volume_unit_evidence_missing",
    "depth5": "depth_volume_unit_evidence_missing",
}


def quantity_capabilities() -> dict:
    return {
        dataset: {
            market: {"status": "contract_blocked", "reason": reason, "quantity_unit": "unknown"}
            for market in MARKETS
        }
        for dataset, reason in REASONS.items()
    }


def _summarize(response, dataset: str) -> dict:
    if dataset == "depth5":
        asks = getattr(response, "asks", None)
        bids = getattr(response, "bids", None)
        if not isinstance(asks, (list, tuple)) or not isinstance(bids, (list, tuple)):
            return {"request_status": "response_shape_mismatch"}
        rows = [*asks, *bids]
    elif isinstance(response, (list, tuple)):
        rows = response
    else:
        return {"request_status": "response_shape_mismatch"}
    if not rows:
        return {"request_status": "empty", "rows": 0}
    # Inspect public attributes only; neither values nor response repr are exposed.
    if any(type(getattr(row, "volume", None)) is not int or row.volume < 0 for row in rows):
        return {"request_status": "response_shape_mismatch", "rows": len(rows)}
    return {"request_status": "success", "rows": len(rows), "volume_type": "int"}


def probe_quantity_contract(provider, symbol: str, dataset: str) -> dict:
    """Finite read-only QuoteContext calls, disconnected from dataset routing.

    Uses the provider's existing context/lock. Missing methods, permissions, empty
    data and malformed responses remain distinct from the unit contract blocker.
    Never checks static_info/lot_size or guesses units from numeric observations.
    """
    if dataset not in REASONS or market_from_symbol(symbol) not in MARKETS:
        raise ValueError("unsupported_quantity_probe")
    result = {
        "symbol": symbol, "market": market_from_symbol(symbol), "dataset": dataset,
        "status": "CONTRACT_BLOCKED", "quantity_unit": "unknown", "reason": REASONS[dataset],
        "method": "depth" if dataset == "depth5" else "history_candlesticks_by_offset",
    }
    try:
        with provider._lock:
            context = provider._get_context()
            method = getattr(context, result["method"], None)
            if not callable(method):
                return {**result, "status": "SDK_UNSUPPORTED", "request_status": "method_missing"}
            if dataset == "depth5":
                response = method(symbol)
            else:
                from app.plugins.longbridge.provider import _sdk

                sdk = _sdk()
                period = sdk.Period.Day if dataset == "daily" else sdk.Period.Min_1
                response = method(symbol, period, sdk.AdjustType.NoAdjust, False, 2)
        summary = _summarize(response, dataset)
        if summary["request_status"] == "empty":
            result["status"] = "EMPTY"
        return {**result, **summary}
    except ImportError:
        return {**result, "status": "SDK_UNSUPPORTED", "request_status": "sdk_missing"}
    except Exception as error:
        from app.plugins.longbridge.provider import error_category

        category = error_category(error)
        code = getattr(error, "code", None)
        reason = "entitlement_denied" if code == 301604 or category == "quote_permission" else {
            "network": "network", "authentication": "authentication", "symbol": "symbol",
        }.get(category, "sdk_exception")
        return {**result, "request_status": reason}
