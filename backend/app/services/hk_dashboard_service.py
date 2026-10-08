"""HK-only read aggregation; no CN repository, monitor, strategy or final sync.

SDK 5.2.0 fields: https://longbridge.github.io/openapi/python/reference_all/
Window flow sums use the official CLI's per-minute net-inflow contract:
https://open.longbridge.com/docs/cli/market-data/capital
Incomplete/currently unfinished windows are never ranked as zero.
"""
from __future__ import annotations

import math
import re
import threading
import time
from collections import OrderedDict
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.market_session import get_market_session
from app.plugins.longbridge.provider import error_category

HK = ZoneInfo("Asia/Hong_Kong")
LIMIT = 20


def validate_symbol(symbol: str) -> str:
    if not re.fullmatch(r"[0-9]{1,5}\.HK", symbol):
        raise ValueError("invalid HK symbol")
    return symbol


def number(value):
    if value is None or isinstance(value, bool):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def stamp(value) -> int:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None:
            raise ValueError("event timestamp lacks timezone")
    # Installed SDK uses datetime.fromtimestamp(epoch), preserving local/fold.
    return int(value.timestamp() * 1000)


def section(data=None, *, mode="LIVE", source="Longbridge", status=None, error=None, updated_at=None):
    return {"status": status or ("ok" if data else "empty"), "mode": mode,
            "source": source, "updated_at": updated_at, "data": data, "error": error}


def unavailable(reason):
    return section(mode="UNAVAILABLE", source="无已确认的可靠数据源", status="unavailable", error=reason)


def window_ranking(flows: dict, now: datetime, window: str) -> dict:
    local = now.astimezone(HK)
    start, end = (570, 600) if window == "morning" else (930, 960)
    label = "09:30-10:00" if window == "morning" else "15:30-16:00"
    rows = []
    if local.hour * 60 + local.minute < end:
        return section([], mode="DERIVED", source="Longbridge capital_flow · 分钟净流入求和",
                       error=f"{'早盘' if window == 'morning' else '尾盘'}窗口尚未完成")
    for symbol, lines in flows.items():
        minutes = {}
        for line in lines:
            dt = datetime.fromtimestamp(line["timestamp"] / 1000, HK)
            minute = dt.hour * 60 + dt.minute
            if dt.date() == local.date() and start <= minute < end and line["inflow"] is not None:
                minutes[minute] = line["inflow"]
        # Fail closed on holes, stale dates, duplicate minute observations or sparse samples.
        if len(minutes) == end - start:
            rows.append({"symbol": symbol, "net_inflow": sum(minutes.values()), "window": label})
    rows.sort(key=lambda row: row["net_inflow"], reverse=True)
    return section(rows, mode="DERIVED", source="Longbridge capital_flow · 分钟净流入求和",
                   error=None if rows else "暂无完整同日窗口资金流数据")


def _provider():
    from app.data_providers.custom import get_provider

    return get_provider("longbridge")


class HKDashboardService:
    def __init__(self, provider_getter=_provider, *, clock=None, monotonic=time.monotonic):
        self.provider_getter = provider_getter
        self.clock = clock or (lambda: datetime.now(UTC))
        self.monotonic = monotonic
        self.cache: OrderedDict = OrderedDict()
        self.lock = threading.RLock()
        self.provider = None

    def _read(self, key, ttl, mode, source, load):
        cached = self.cache.get(key)
        if cached and self.monotonic() - cached[0] < ttl:
            self.cache.move_to_end(key)
            return cached[1]
        try:
            result = section(load(), mode=mode, source=source, updated_at=self.clock().isoformat())
        except Exception as error:
            category = error_category(error)
            result = section(mode=mode, source=source, status="error", error=category)
        self.cache[key] = (self.monotonic(), result)
        while len(self.cache) > 128:
            self.cache.popitem(last=False)
        return result

    def get(self, symbol: str | None, snapshots: list[dict]) -> dict:
        if symbol is not None:
            validate_symbol(symbol)
        with self.lock:
            return self._get(symbol, snapshots)

    def _get(self, symbol, snapshots):
        now = self.clock()
        session = get_market_session("HK", now)
        result = {"market": {"code": "HK", "timezone": "Asia/Hong_Kong",
                             "local_time": session.local_datetime.isoformat(),
                             "session_state": session.session_state, "calendar_status": session.calendar_status},
                  "updated_at": now.isoformat(), "focus_symbol": symbol}
        result.update({
            "industry_flow": unavailable("暂无可靠行业资金流数据源;行业排行不等于资金流"),
            "concept_flow": unavailable("暂无可靠港股概念分类、成分及资金流数据源"),
            "block_trades": unavailable("暂无可靠港股大宗交易数据源;普通逐笔不等于大宗交易"),
            "daily_etfs": unavailable("当前候选集合尚无可靠 HK ETF 类型识别;不按名称猜测或宣称全市场"),
        })
        try:
            provider = self.provider_getter()
            if provider is not self.provider:
                self.cache.clear()
                self.provider = provider
        except Exception:
            for name in ("daily_stocks", "capital_flow", "fundamentals", "dividends", "movers", "move_reasons", "morning_accumulation", "closing_accumulation"):
                result[name] = unavailable("Longbridge SDK 或凭证未配置/不可用")
            return result

        def call(kind, method, *args, **kwargs):
            return provider.dashboard_request(kind, method, *args, **kwargs)

        def movers():
            rows = []
            for event in call("market", "top_movers", markets=["HK"], limit=LIMIT).events:
                stock = event.stock
                if not re.fullmatch(r"[0-9]{1,5}\.HK", stock.symbol) or stock.market != "HK":
                    continue
                rows.append({"symbol": stock.symbol, "name": stock.name, "last_price": number(stock.last_done),
                             "change_pct": number(stock.change), "timestamp": stamp(event.timestamp),
                             "reason": event.alert_reason, "alert_type": event.alert_type, "labels": list(stock.labels)})
            return rows[:LIMIT]

        result["movers"] = self._read(("movers",), 30, "LIVE", "Longbridge MarketContext.top_movers(HK)", movers)
        result["move_reasons"] = result["movers"]
        candidates = list(dict.fromkeys([
            *(row["symbol"] for row in result["movers"]["data"] or []),
            *(row["symbol"] for row in snapshots if re.fullmatch(r"[0-9]{1,5}\.HK", row.get("symbol", "")) and row.get("market") == "HK"),
        ]))[:LIMIT]
        if symbol and symbol not in candidates:
            candidates = [symbol, *candidates][:LIMIT]

        def metadata():
            return {info.symbol: {"name": info.name_cn or info.name_en, "currency": info.currency}
                    for info in call("quote", "static_info", candidates) if info.symbol in candidates} if candidates else {}

        names = self._read(("metadata", tuple(candidates)), 1800, "DAILY", "Longbridge static_info", metadata)["data"] or {}

        def quotes():
            output = []
            for quote in call("quote", "quote", candidates) if candidates else []:
                if quote.symbol not in candidates:
                    continue
                price, previous = number(quote.last_done), number(quote.prev_close)
                output.append({"symbol": quote.symbol, "market": "HK", **names.get(quote.symbol, {}), "last_price": price,
                               "change_pct": (price - previous) / previous if price is not None and previous and previous > 0 else None,
                               "open": number(quote.open), "high": number(quote.high), "low": number(quote.low),
                               "amount": number(quote.turnover), "timestamp": stamp(quote.timestamp)})
            return output

        result["daily_stocks"] = self._read(("quotes", tuple(candidates)), 30, "LIVE", "Longbridge quote · 当前榜单/已获取标的,最多20只,非全港股", quotes)
        # Existing snapshots are reliable fallback only; never read CN enriched.
        if result["daily_stocks"]["status"] == "error":
            fallback = [dict(row) for row in snapshots if row.get("symbol") in candidates and row.get("market") == "HK"]
            if fallback:
                result["daily_stocks"] = section(fallback, source="已有 HK realtime snapshot cache", error="quote请求失败;显示缓存时间")
        rows = result["daily_stocks"]["data"] or []
        focus = symbol or (rows[0]["symbol"] if rows else None)
        result["focus_symbol"] = focus
        if not focus:
            for name in ("capital_flow", "fundamentals", "dividends"):
                result[name] = section([], error="暂无焦点股票")
        else:
            def fundamentals():
                values = call("quote", "static_info", [focus])
                info = next((value for value in values if value.symbol == focus), None)
                if info is None:
                    return None
                return {"symbol": focus, "name": info.name_cn or info.name_en, "exchange": info.exchange,
                        "currency": info.currency, **{field: number(getattr(info, field, None)) for field in
                        ("lot_size", "total_shares", "circulating_shares", "eps", "eps_ttm", "bps")}}

            result["fundamentals"] = self._read(("static", focus), 3600, "DAILY", "Longbridge QuoteContext.static_info", fundamentals)

            def dividends():
                return [{"symbol": item.symbol, "description": item.desc, "ex_date": item.ex_date,
                         "record_date": item.record_date, "payment_date": item.payment_date}
                        for item in call("fundamental", "dividend_detail", focus).list if item.symbol == focus][:20]

            result["dividends"] = self._read(("dividends", focus), 21600, "DAILY", "Longbridge FundamentalContext.dividend_detail", dividends)

        flows = {}
        for candidate in candidates:
            def flow(s=candidate):
                return [{"timestamp": stamp(line.timestamp), "inflow": number(line.inflow)}
                        for line in call("quote", "capital_flow", s)][:1000]

            value = self._read(("flow", candidate, session.local_date.isoformat()), 60, "LIVE", "Longbridge QuoteContext.capital_flow", flow)
            flows[candidate] = value["data"] or []
            if candidate == focus:
                result["capital_flow"] = value
        if "capital_flow" not in result:
            result["capital_flow"] = section([], error="暂无资金流数据")
        result["morning_accumulation"] = window_ranking(flows, now, "morning")
        result["closing_accumulation"] = window_ranking(flows, now, "closing")
        return result
