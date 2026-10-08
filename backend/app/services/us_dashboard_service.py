"""Independent US read model for the 13 CN layout slots, never CN data.

SDK contract: https://longbridge.github.io/openapi/python/reference_all/
Breadth is an explicitly limited observed sample, never US market breadth.
OptionVolumeStats only has call_volume/put_volume; no OI or invented score.
"""
from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict
from datetime import UTC, datetime
from statistics import median

from app.market_session import get_market_session
from app.plugins.longbridge.provider import error_category
from app.services.hk_dashboard_service import number, section, stamp, unavailable

CORE_SAMPLE = ("AAPL.US", "NVDA.US", "MSFT.US", "AMZN.US", "META.US", "TSLA.US")
INDEX_SYMBOLS = (".SPX.US", ".IXIC.US", ".DJI.US")
SLOTS = ("indices", "kpi", "distribution", "radar", "trend", "ladder", "concept-rank",
         "industry-rank", "monitor", "gainers", "losers", "turnover", "activity")
LIMIT = 40


class OptionDataUnavailableError(Exception):
    """A symbol-specific OpenAPI refusal, not a missing SDK capability."""


def validate_symbol(symbol: str) -> str:
    if not re.fullmatch(r"[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)*\.US", symbol):
        raise ValueError("invalid US stock symbol")
    return symbol


def _is_us(symbol) -> bool:
    try:
        validate_symbol(symbol)
        return True
    except (TypeError, ValueError):
        return False


def _provider():
    from app.data_providers.custom import get_provider

    return get_provider("longbridge")


def sample_stats(rows):
    """Only successful positive-price quotes with a valid previous close."""
    values = [row["change_pct"] for row in rows if row["change_pct"] is not None]
    amounts = [row["amount"] for row in rows if row["amount"] is not None and row.get("currency") == "USD"]
    total = len(values)
    return {"total": total, "up": sum(value > 0 for value in values),
            "flat": sum(value == 0 for value in values), "down": sum(value < 0 for value in values),
            "up_pct": sum(value > 0 for value in values) / total * 100 if total else None,
            "strong_up": sum(value >= .03 for value in values), "strong_down": sum(value <= -.03 for value in values),
            "avg_pct": sum(values) / total if total else None, "median_pct": median(values) if total else None,
            "amount_total": sum(amounts) if amounts else None, "amount_count": len(amounts)}


class USDashboardService:
    def __init__(self, provider_getter=_provider, *, clock=None, monotonic=time.monotonic):
        self.provider_getter = provider_getter
        self.clock = clock or (lambda: datetime.now(UTC))
        self.monotonic = monotonic
        self.cache: OrderedDict = OrderedDict()
        self.lock = threading.RLock()
        self.provider = None

    def _read(self, key, ttl, source, load, mode="LIVE"):
        cached = self.cache.get(key)
        if cached and self.monotonic() - cached[0] < ttl:
            self.cache.move_to_end(key)
            return cached[1]
        try:
            value = section(load(), source=source, mode=mode, updated_at=self.clock().isoformat())
        except OptionDataUnavailableError:
            value = unavailable("该标的暂无期权成交量数据")
        except Exception as error:
            value = section(status="error", source=source, mode=mode, error=error_category(error))
        self.cache[key] = (self.monotonic(), value)
        while len(self.cache) > 128:
            self.cache.popitem(last=False)
        return value

    def get(self, symbol, snapshots):
        if symbol is not None:
            validate_symbol(symbol)
        with self.lock:
            return self._get(symbol, snapshots)

    def _get(self, symbol, snapshots):
        now = self.clock()
        session = get_market_session("US", now)
        result = {"market": {"code": "US", "timezone": "America/New_York",
                             "local_time": session.local_datetime.isoformat(),
                             "session_state": session.session_state, "calendar_status": session.calendar_status},
                  "updated_at": now.isoformat(), "focus_symbol": symbol, "focus_quote": None,
                  "sample": {"coverage": "六只代表股票及当前异动/已获取标的 · 最多40只 · 非全美股市场", "requested": 0, "received": 0}}
        result.update({
            "radar": unavailable("暂无经过验证的美股情绪雷达数据源"),
            "trend": unavailable("暂无完整同口径样本历史均线及新高低数据"),
            "concept-rank": unavailable("暂无可靠美股概念分类数据源"),
            "industry-rank": unavailable("暂无已验证的美股行业行情排行数据源"),
        })
        try:
            provider = self.provider_getter()
            if provider is not self.provider:
                self.provider = provider
                self.cache.clear()
        except Exception:
            for key in SLOTS:
                result.setdefault(key, unavailable("Longbridge SDK或凭证未配置/不可用"))
            return result

        def call(kind, method, *args, **kwargs):
            return provider.dashboard_request(kind, method, *args, **kwargs)

        def movers():
            output = []
            for event in call("market", "top_movers", markets=["US"], limit=20).events:
                stock = event.stock
                if _is_us(stock.symbol) and stock.market == "US":
                    output.append({"symbol": stock.symbol, "name": stock.name, "close": number(stock.last_done),
                                   "change_pct": number(stock.change), "timestamp": stamp(event.timestamp),
                                   "reason": event.alert_reason, "alert_type": event.alert_type, "labels": list(stock.labels)})
            return output[:20]

        events = self._read(("movers",), 30, "Longbridge · 美股当前20条异动事件", movers)
        candidates = list(dict.fromkeys([*CORE_SAMPLE, *(row["symbol"] for row in events["data"] or []),
                                        *(row["symbol"] for row in snapshots if row.get("market") == "US" and _is_us(row.get("symbol")))]))[:LIMIT]
        if symbol and symbol not in candidates:
            candidates = [symbol, *candidates][:LIMIT]
        result["sample"]["requested"] = len(candidates)

        def metadata():
            return {info.symbol: {"name": info.name_cn or info.name_en or info.symbol, "currency": info.currency}
                    for info in call("quote", "static_info", candidates) if info.symbol in candidates}

        names = self._read(("names", tuple(candidates)), 1800, "Longbridge static_info", metadata, "DAILY")["data"] or {}

        def quotes(symbols):
            output = []
            seen = set()
            for quote in call("quote", "quote", list(symbols)):
                if quote.symbol not in symbols or quote.symbol in seen:
                    continue
                price, previous = number(quote.last_done), number(quote.prev_close)
                if price is None or price <= 0:
                    continue
                seen.add(quote.symbol)
                output.append({"symbol": quote.symbol, "market": "US", **names.get(quote.symbol, {}), "close": price,
                               "change_pct": (price - previous) / previous if previous and previous > 0 else None,
                               "open": number(quote.open), "high": number(quote.high), "low": number(quote.low),
                               "amount": number(quote.turnover), "timestamp": stamp(quote.timestamp)})
            return output

        result["indices"] = self._read(("indices",), 30, "Longbridge · 官方指数报价", lambda: quotes(INDEX_SYMBOLS))
        quoted = self._read(("quotes", tuple(candidates)), 30, "Longbridge · 有限观察样本报价", lambda: quotes(candidates))
        rows = quoted["data"] or []
        result["sample"]["received"] = len(rows)
        focus = symbol or (rows[0]["symbol"] if rows else None)
        result["focus_symbol"] = focus
        result["focus_quote"] = next((row for row in rows if row["symbol"] == focus), None)
        for row in events["data"] or []:
            row_name = names.get(row["symbol"], {}).get("name")
            if row_name:
                row["name"] = row_name
        result["monitor"] = events
        result["activity"] = events

        if quoted["status"] == "error":
            for key in ("kpi", "distribution", "gainers", "losers", "turnover"):
                result[key] = dict(quoted)
        else:
            def derived(data):
                return section(data, mode="DERIVED", source="Longbridge · 当前可获取样本派生 · 非全市场", updated_at=quoted["updated_at"])

            stats = sample_stats(rows)
            result["kpi"] = derived(stats if stats["total"] else None)
            bounds = (-.07, -.05, -.03, 0, .03, .05, .07)
            counts = [0] * 8
            for row in rows:
                pct = row["change_pct"]
                if pct is not None:
                    counts[sum(pct >= bound for bound in bounds)] += 1
            labels = ("<-7%", "-7~-5%", "-5~-3%", "-3~0%", "0~3%", "3~5%", "5~7%", "≥7%")
            result["distribution"] = derived({"breadth": stats, "bins": [{"label": label, "count": count} for label, count in zip(labels, counts, strict=True)]} if stats["total"] else None)
            result["gainers"] = derived(sorted((row for row in rows if row["change_pct"] is not None and row["change_pct"] > 0), key=lambda row: row["change_pct"], reverse=True))
            result["losers"] = derived(sorted((row for row in rows if row["change_pct"] is not None and row["change_pct"] < 0), key=lambda row: row["change_pct"]))
            result["turnover"] = derived(sorted((row for row in rows if row["amount"] is not None), key=lambda row: row["amount"], reverse=True))

        def options():
            try:
                value = call("quote", "option_volume", focus)
            except Exception as error:
                if type(error).__name__ == "OpenApiException":
                    raise OptionDataUnavailableError from None
                raise
            # SDK OptionVolumeStats is an object; dict support is only an adapter.
            def field(name):
                return value.get(name) if isinstance(value, dict) else getattr(value, name, None)

            if field("symbol") != focus:
                raise ValueError("invalid symbol response")
            calls, puts = number(field("call_volume")), number(field("put_volume"))
            if (calls is not None and calls < 0) or (puts is not None and puts < 0):
                raise ValueError("invalid volume response")
            return {"symbol": focus, "call_volume": calls, "put_volume": puts,
                    "put_call_ratio": puts / calls if calls is not None and calls > 0 and puts is not None else None,
                    "put_call_ratio_mode": "DERIVED"}

        result["ladder"] = self._read(("options", focus), 60, "Longbridge · 期权成交量 · 比率为派生", options) if focus else section([], error="暂无焦点股票")
        return result
