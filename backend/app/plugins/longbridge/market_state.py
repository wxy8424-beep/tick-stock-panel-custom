"""MarketContext-only mapping, pinned to official Rust longbridge 5.2.0.

https://docs.rs/longbridge/5.2.0/longbridge/market/types/enum.TradeStatus.html
Python openapi.TradeStatus is a SECURITY enum and must never enter this adapter.
"""
from datetime import datetime

from app.market_session import MarketRuntimeSignal

SOURCE = "longbridge.market_status"
REFRESH_SECONDS = 60
TTL_SECONDS = 120
# Conservative subset: exclude security/special, overnight and ambiguous aliases.
_CASH = {101: "pre_open", 102: "pre_open", 105: "regular", 106: "break",
         107: "post_market", 108: "closed", 121: "closed", 122: "closed", 123: "break"}
_US = {201: "pre_open", 202: "regular", 203: "post_market", 204: "closed", 206: "pre_open"}


def parse_market_status(response, observed_at: datetime) -> list[MarketRuntimeSignal]:
    """Accept only the SDK market_time envelope, never a security quote/list.

    observed_at is the aware local receipt clock, not quote event time or the
    undocumented market timestamp's update age. Delayed fields are not used.
    Duplicate/malformed supported-market rows fail closed for that market.
    """
    items = getattr(response, "market_time", None)
    if not isinstance(items, (list, tuple)):
        raise ValueError("invalid market status envelope")
    states = {}
    for item in items:
        market = str(getattr(item, "market", "")).removeprefix("Market.")
        if market not in {"CN", "HK", "US"}:
            continue
        code = getattr(item, "trade_status", None)
        table = _US if market == "US" else _CASH
        state = table.get(code, "unknown") if type(code) is int else "unknown"
        states[market] = "unknown" if market in states else state
    return [MarketRuntimeSignal(market, state, observed_at, SOURCE, ttl_seconds=TTL_SECONDS)
            for market, state in states.items()]
