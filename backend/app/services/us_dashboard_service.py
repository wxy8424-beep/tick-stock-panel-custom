"""Independent US read model for the 13 CN layout slots, never CN data.

SDK contract: https://longbridge.github.io/openapi/python/reference_all/
Breadth explicitly reports coverage of the provider's available securities.
OptionVolumeStats only has call_volume/put_volume; no OI or invented score.
"""
from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
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
    if not re.fullmatch(r"[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)*-?\.US", symbol):
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
    def __init__(self, provider_getter=_provider, *, clock=None, monotonic=time.monotonic, universe_enabled=False):
        self.provider_getter = provider_getter
        self.clock = clock or (lambda: datetime.now(UTC))
        self.monotonic = monotonic
        self.cache: OrderedDict = OrderedDict()
        self.lock = threading.RLock()
        self.provider = None
        self.universe_enabled = universe_enabled
        self.universe_lock = threading.Lock()
        self.universe_stop = threading.Event()
        self.universe_thread = None
        self.universe_snapshot = None
        self.universe_provider = None
        self.universe_symbols = ()
        self.universe_rejected = 0
        self.universe_checked_at = 0
        self.universe_status = "loading"
        self.universe_error = None

    def close(self):
        self.universe_stop.set()
        if self.universe_thread:
            self.universe_thread.join(timeout=3)

    def _ensure_universe_worker(self):
        if not self.universe_enabled:
            return
        with self.universe_lock:
            if self.universe_thread is None and not self.universe_stop.is_set():
                self.universe_thread = threading.Thread(target=self._universe_loop, name="us-quote-universe", daemon=True)
                self.universe_thread.start()

    def _universe_loop(self):
        while not self.universe_stop.is_set():
            self.refresh_universe()
            interval = 30 if get_market_session("US", self.clock()).is_regular_session else 300
            if self.universe_stop.wait(interval):
                break

    def refresh_universe(self):
        """One bounded sweep; network outside state locks, publish once after all batches.

        Missing/failed quotes never borrow older rows into the new sweep. A total
        failure retains the previous snapshot, visibly stale, until recovery.
        """
        started = self.clock().isoformat()
        try:
            provider = self.provider_getter()
            with self.universe_lock:
                if provider is not self.universe_provider:
                    self.universe_provider = provider
                    self.universe_symbols = ()
                    self.universe_snapshot = None
                    self.universe_rejected = 0
                symbols = self.universe_symbols
                self.universe_status = "refreshing" if self.universe_snapshot else "loading"
                due = not symbols or self.monotonic() - self.universe_checked_at >= 86400
            if due:
                raw = provider.get_realtime_universe("US")
                if not raw or len(raw) > 100000:
                    raise ValueError("invalid US universe response")
                symbols = tuple(dict.fromkeys(s for s in raw if _is_us(s)))
                if not symbols:
                    raise ValueError("invalid US universe response")
                with self.universe_lock:
                    self.universe_symbols = symbols
                    self.universe_rejected = sum(not _is_us(s) for s in raw)
                    self.universe_checked_at = self.monotonic()
            rows = {}
            failed_batches = 0
            errors = set()
            for offset in range(0, len(symbols), 500):
                if self.universe_stop.is_set():
                    return
                chunk = symbols[offset:offset + 500]
                try:
                    quotes = provider.get_realtime(list(chunk))
                    for row in quotes:
                        if row.get("symbol") not in chunk or row.get("market") != "US":
                            continue
                        price = number(row.get("last_price"))
                        timestamp = number(row.get("timestamp"))
                        if price is None or price <= 0 or timestamp is None or timestamp <= 0:
                            continue
                        if datetime.fromtimestamp(timestamp / 1000, UTC) > self.clock() + timedelta(minutes=2):
                            continue
                        rows[row["symbol"]] = {**row, "close": price}
                    if not quotes:
                        failed_batches += 1
                except Exception as error:
                    failed_batches += 1
                    errors.add(error_category(error))
                # Bound shared-provider pressure; interruptible during shutdown.
                if offset + 500 < len(symbols) and self.universe_stop.wait(.25):
                    return
            if self.universe_stop.is_set() or self.provider_getter() is not provider:
                return
            finished = self.clock().isoformat()
            zone = get_market_session("US", self.clock()).timezone
            dates = {r["symbol"]: datetime.fromtimestamp(r["timestamp"] / 1000, zone).date() for r in rows.values()}
            latest_date = max(dates.values(), default=None)
            eligible = [r for r in rows.values() if dates[r["symbol"]] == latest_date]
            coverage = {"coverage": "Longbridge 美股可用证券清单(含ETF等; 非全部普通股市场保证)",
                        "requested": len(symbols), "received": len(rows), "failed": len(symbols) - len(rows),
                        "rejected_symbols": self.universe_rejected,
                        "statistics_date": latest_date.isoformat() if latest_date else None,
                        "statistics_received": len(eligible), "stale_quote_count": len(rows) - len(eligible),
                        "failed_batches": failed_batches, "started_at": started, "completed_at": finished,
                        "duration_s": (datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds(),
                        "quote_min_timestamp": min((r["timestamp"] for r in rows.values()), default=None),
                        "quote_max_timestamp": max((r["timestamp"] for r in rows.values()), default=None),
                        "scope": "provider_universe", "exchange_complete": False}
            with self.universe_lock:
                if rows:
                    self.universe_snapshot = (eligible, coverage)
                self.universe_status = "ready" if len(rows) == len(symbols) and not self.universe_rejected else "partial" if rows else "stale"
                self.universe_error = ",".join(sorted(errors)) or None
        except Exception as error:
            with self.universe_lock:
                self.universe_status = "stale" if self.universe_snapshot else "unavailable"
                self.universe_error = error_category(error)

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
        self._ensure_universe_worker()
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

        if self.universe_enabled:
            with self.universe_lock:
                snapshot = self.universe_snapshot if provider is self.universe_provider else None
                status, error = self.universe_status, self.universe_error
                count = len(self.universe_symbols) if provider is self.universe_provider else 0
            rows, coverage = snapshot if snapshot else ([], {
                "coverage": "Longbridge 美股证券清单后台采集中", "requested": count,
                "received": 0, "failed": 0, "scope": "provider_universe", "exchange_complete": False,
            })
            result["sample"] = {**coverage, "status": status, "error": error, "stale": status == "stale"}
            quoted = section(rows, updated_at=coverage.get("completed_at"), source="Longbridge · 美股证券批量快照")

        if quoted["status"] == "error":
            for key in ("kpi", "distribution", "gainers", "losers", "turnover"):
                result[key] = dict(quoted)
        else:
            def derived(data):
                source = "Longbridge · 已覆盖证券派生(统计范围见覆盖信息)" if self.universe_enabled else "Longbridge · 当前可获取样本派生 · 非全市场"
                return section(data, mode="DERIVED", source=source, updated_at=quoted["updated_at"])

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
            result["gainers"] = derived(sorted((row for row in rows if row["change_pct"] is not None and row["change_pct"] > 0), key=lambda row: row["change_pct"], reverse=True)[:20])
            result["losers"] = derived(sorted((row for row in rows if row["change_pct"] is not None and row["change_pct"] < 0), key=lambda row: row["change_pct"])[:20])
            result["turnover"] = derived(sorted((row for row in rows if row["amount"] is not None and (not self.universe_enabled or row.get("currency") == "USD")), key=lambda row: row["amount"], reverse=True)[:20])

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
