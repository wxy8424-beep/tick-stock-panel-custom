"""Opt-in Daily research queries; never registered in production synchronization.

Raw source OHLC and independently fetched adjusted OHLC remain separate.
No quantity conversion, adjustment-factor construction or repository writes.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

import polars as pl

from app.market_calendar import CALENDARS
from app.market_session import market_from_symbol

PriceMode = Literal["raw", "adjusted"]
PRICES = ("open", "high", "low", "close")
HISTORICAL_SCHEMA = {
    "symbol": pl.String, "market": pl.String, "trading_date": pl.Date,
    **dict.fromkeys(PRICES, pl.Float64),
    **dict.fromkeys((f"adjusted_{key}" for key in PRICES), pl.Float64),
    "source_adjusted_close": pl.Float64,
    "adjustment_method": pl.String, "adjusted_adjustment_method": pl.String,
    "volume": pl.Float64, "volume_unit": pl.String, "currency": pl.String,
    "source": pl.String, "fetched_at": pl.Datetime("us", "UTC"),
    "observed_at": pl.Datetime("us", "UTC"),
    "dividend": pl.Float64, "split": pl.Float64,
}


@dataclass(frozen=True)
class HistoricalDailyResult:
    symbol: str
    market: str
    price_mode: PriceMode
    source: str
    frame: pl.DataFrame
    status: str
    diagnostics: tuple[dict, ...]

    def to_dict(self) -> dict:
        # Dates and observation times remain explicit, not epoch guesses.
        rows = [{key: value.isoformat() if isinstance(value, (date, datetime)) else value
                 for key, value in row.items()} for row in self.frame.to_dicts()]
        return {"symbol": self.symbol, "market": self.market, "price_mode": self.price_mode,
                "source": self.source, "status": self.status,
                "diagnostics": [dict(item) for item in self.diagnostics], "rows": rows}


class HistoricalDailyProvider(Protocol):
    def fetch_daily(self, symbol: str, start_date: date, end_date: date,
                    price_mode: PriceMode = "raw") -> HistoricalDailyResult: ...


class _DataError(ValueError):
    pass


def _number(value) -> float | None:
    if value is None or str(value) in {"", "nan", "NaN", "<NA>", "NaT"}:
        return None
    if isinstance(value, bool):
        raise _DataError("invalid_numeric")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _DataError("invalid_numeric") from exc
    if not math.isfinite(number):
        raise _DataError("invalid_numeric")
    return number


def _failure(exc: Exception) -> str:
    # Fixed categories only: no response bodies, raw URLs, paths or secrets.
    if isinstance(exc, _DataError):
        return str(exc)
    name = type(exc).__name__.lower()
    if isinstance(exc, ImportError):
        return "sdk_missing"
    if "timeout" in name:
        return "network_timeout"
    if any(word in name for word in ("connection", "ssl", "curl")):
        return "network_error"
    if "ratelimit" in name:
        return "rate_limited"
    return "source_api_error"


def _normalize(frame, market: str, symbol: str, start: date, end: date, *,
               columns: dict[str, str], indexed: bool, adjusted: bool) -> tuple[dict, list[dict]]:
    """Validate source trading-date labels; never derive dates from epoch ticks."""
    import pandas as pd

    if not isinstance(frame, pd.DataFrame):
        raise _DataError("response_shape_mismatch")
    if frame.empty:
        return {}, []
    required = set(columns.values()) | (set() if indexed else {"日期", "股票代码"})
    if not required.issubset(frame.columns) or frame.columns.has_duplicates:
        raise _DataError("response_shape_mismatch")
    if indexed and (not isinstance(frame.index, pd.DatetimeIndex) or frame.index.name != "Date"
                    or frame.index.tz is None or str(frame.index.tz) != "America/New_York"):
        raise _DataError("trading_date_schema_unknown")
    result, diagnostics = {}, []
    calendar = CALENDARS[market]
    for label, item in frame.iterrows():
        if indexed:
            if pd.isna(label) or label != label.normalize():
                raise _DataError("trading_date_schema_unknown")
            day = label.date()  # SDK 1d Date index is already exchange-local midnight.
        else:
            value = item["日期"]
            if type(value) is date:
                day = value
            elif isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                try:
                    day = date.fromisoformat(value)
                except ValueError as exc:
                    raise _DataError("invalid_trading_date") from exc
            else:
                raise _DataError("trading_date_schema_unknown")
            if str(item["股票代码"]) != symbol.partition(".")[0]:
                raise _DataError("symbol_mismatch")
        if not start <= day <= end:
            raise _DataError("out_of_range_trading_date")
        if day in result:
            raise _DataError("duplicate_trading_date")
        if day.weekday() >= 5 or (calendar.coverage_start <= day <= calendar.coverage_end
                                 and day in calendar.holidays):
            raise _DataError("non_trading_date")
        if not calendar.coverage_start <= day <= calendar.coverage_end:
            diagnostics.append({"code": "calendar_coverage_unknown", "trading_date": day.isoformat()})
        values = {key: _number(item[column]) for key, column in columns.items()}
        prices = [values[key] for key in PRICES]
        if any(value is None for value in prices):
            diagnostics.append({"code": "missing_price", "trading_date": day.isoformat()})
        if any(value is not None and value <= 0 for value in prices):
            if not adjusted:
                raise _DataError("invalid_raw_price")
            diagnostics.append({"code": "non_positive_adjusted_price", "trading_date": day.isoformat()})
        low, high = values["low"], values["high"]
        if ((low is not None and high is not None and low > high)
                or any(value is not None and ((low is not None and value < low)
                       or (high is not None and value > high)) for value in (values["open"], values["close"]))):
            raise _DataError("invalid_ohlc")
        if "volume" in values and values["volume"] is not None and values["volume"] < 0:
            raise _DataError("invalid_volume")
        # SDK fills unknown Volume with 0. Do not represent ambiguous zero as a
        # verified observation, even with keepna=True. No shares/lot inference.
        if indexed and values.get("volume") == 0:
            values["volume"] = None
            diagnostics.append({"code": "sdk_zero_volume_ambiguous", "trading_date": day.isoformat()})
        for column, key in (("Adj Close", "source_adjusted_close"), ("Dividends", "dividend"), ("Stock Splits", "split")):
            if indexed:
                values[key] = _number(item[column]) if column in frame.columns else None
        result[day] = values
    return result, diagnostics


class _HistoricalProvider:
    market: str
    source: str
    raw_method: str
    adjusted_method: str
    volume_unit: str

    def _ticker(self, symbol: str) -> str:
        raise NotImplementedError

    def _read(self, ticker: str, start: date, end: date, adjusted: bool):
        raise NotImplementedError

    def fetch_daily(self, symbol: str, start_date: date, end_date: date,
                    price_mode: PriceMode = "raw") -> HistoricalDailyResult:
        if (type(start_date) is not date or type(end_date) is not date
                or not start_date <= end_date < date.max or price_mode not in {"raw", "adjusted"}):
            raise ValueError("explicit ordered Date range and raw/adjusted price mode required")
        diagnostics = []

        def result(rows, status):
            return HistoricalDailyResult(symbol, self.market, price_mode, self.source,
                                         pl.DataFrame(rows, schema=HISTORICAL_SCHEMA), status, tuple(diagnostics))

        try:
            ticker = self._ticker(symbol)
        except _DataError as exc:
            diagnostics.append({"code": str(exc), "mode": "request"})
            return result([], "blocked")
        observed = datetime.now(UTC)
        raw, adjusted_rows, currency = {}, {}, None
        for adjusted in (False, True) if price_mode == "adjusted" else (False,):
            mode = "adjusted" if adjusted else "raw"
            try:
                frame, current_currency, columns, indexed = self._read(ticker, start_date, end_date, adjusted)
                data, issues = _normalize(frame, self.market, symbol, start_date, end_date,
                                          columns=columns, indexed=indexed, adjusted=adjusted)
                diagnostics.extend(dict(item, mode=mode) for item in issues)
                if adjusted:
                    adjusted_rows = data
                    if current_currency != currency:
                        raise _DataError("currency_conflict")
                else:
                    raw, currency = data, current_currency
                if not data:
                    diagnostics.append({"code": "empty_response", "mode": mode})
            except Exception as exc:
                if adjusted:
                    adjusted_rows = {}
                diagnostics.append({"code": _failure(exc), "mode": mode})
            if not adjusted and not raw:
                return result([], "empty" if diagnostics[-1]["code"] == "empty_response" else "unavailable")
        fetched = datetime.now(UTC)
        if currency is None:
            diagnostics.append({"code": "currency_unknown", "mode": "raw"})
        if self.volume_unit == "unknown":
            diagnostics.append({"code": "volume_unit_unknown", "mode": "raw"})
        if self.market == "US":
            diagnostics.extend(({"code": "as_traded_raw_not_established", "mode": "raw"},
                                {"code": "sdk_may_deduplicate_source_dates", "mode": "raw"}))
        if price_mode == "adjusted" and set(raw) != set(adjusted_rows):
            diagnostics.append({"code": "raw_adjusted_dates_mismatch", "mode": "adjusted"})
        rows = []
        for day, values in sorted(raw.items()):
            adjusted_values = adjusted_rows.get(day, {})
            if day >= fetched.astimezone(ZoneInfo("Asia/Shanghai" if self.market == "CN" else "America/New_York")).date():
                diagnostics.append({"code": "daily_bar_not_final", "mode": "raw", "trading_date": day.isoformat()})
            rows.append({"symbol": symbol, "market": self.market, "trading_date": day,
                         **{key: values[key] for key in PRICES},
                         **{f"adjusted_{key}": adjusted_values.get(key) for key in PRICES},
                         "source_adjusted_close": values.get("source_adjusted_close"),
                         "adjustment_method": self.raw_method,
                         "adjusted_adjustment_method": self.adjusted_method if day in adjusted_rows else None,
                         "volume": values["volume"], "volume_unit": self.volume_unit,
                         "currency": currency, "source": self.source, "fetched_at": fetched,
                         "observed_at": None, "dividend": values.get("dividend"), "split": values.get("split")})
        # Fetch timing is transport metadata, not a claimed provider observation.
        if fetched < observed:
            diagnostics.append({"code": "local_clock_regressed", "mode": "request"})
        material = {"missing_price", "non_positive_adjusted_price", "currency_unknown", "daily_bar_not_final",
                    "raw_adjusted_dates_mismatch", "currency_conflict", "sdk_missing", "source_api_error",
                    "response_shape_mismatch", "network_error", "network_timeout", "rate_limited"}
        status = "partial" if any(item["code"] in material or (
            item["mode"] == "adjusted" and item["code"] not in {"calendar_coverage_unknown"})
            for item in diagnostics) else "completed"
        return result(rows, status)


class AKShareDailyProvider(_HistoricalProvider):
    market, source = "CN", "akshare.stock_zh_a_hist/eastmoney"
    raw_method, adjusted_method, volume_unit = "none", "akshare_qfq", "akshare_lots"

    def __init__(self, client=None):
        self.client = client

    def _ticker(self, symbol: str) -> str:
        if market_from_symbol(symbol) != "CN":
            raise _DataError("unsupported_market")
        code, suffix = symbol.split(".")
        if not ((suffix == "SH" and code.startswith(("600", "601", "603", "605", "688", "689")))
                or (suffix == "SZ" and code.startswith(("000", "001", "002", "003", "300", "301")))):
            raise _DataError("unsupported_cn_security")
        return code

    def _read(self, ticker, start, end, adjusted):
        if self.client is None:
            import akshare
            self.client = akshare
        frame = self.client.stock_zh_a_hist(symbol=ticker, period="daily", start_date=start.strftime("%Y%m%d"),
                                          end_date=end.strftime("%Y%m%d"), adjust="qfq" if adjusted else "", timeout=15)
        return frame, "CNY", {"open": "开盘", "high": "最高", "low": "最低", "close": "收盘", "volume": "成交量"}, False


class YFinanceDailyProvider(_HistoricalProvider):
    market, source = "US", "yfinance.Ticker.history/yahoo"
    raw_method = "yfinance_auto_adjust_false"
    adjusted_method, volume_unit = "yfinance_auto_adjust", "unknown"

    def __init__(self, ticker_factory=None):
        self.ticker_factory = ticker_factory
        self._ticker_cache = {}

    def _ticker(self, symbol: str) -> str:
        if market_from_symbol(symbol) != "US":
            raise _DataError("unsupported_market")
        ticker = symbol.removesuffix(".US")
        if not re.fullmatch(r"[A-Z][A-Z0-9-]{0,19}", ticker):
            raise _DataError("unsupported_us_symbol_format")
        return ticker

    def _read(self, ticker, start, end, adjusted):
        if self.ticker_factory is None:
            import yfinance
            self.ticker_factory = yfinance.Ticker
        if ticker not in self._ticker_cache:
            self._ticker_cache[ticker] = self.ticker_factory(ticker)
        client = self._ticker_cache[ticker]
        frame = client.history(start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                               interval="1d", auto_adjust=adjusted, back_adjust=False,
                               actions=True, repair=False, keepna=True, rounding=False,
                               prepost=False, timeout=15, raise_errors=True)
        metadata = client.get_history_metadata()
        if (not isinstance(metadata, Mapping) or metadata.get("symbol") != ticker
                or metadata.get("instrumentType") != "EQUITY"
                or metadata.get("exchangeTimezoneName") != "America/New_York"):
            raise _DataError("security_metadata_mismatch")
        currency = metadata.get("currency")
        if currency is not None and (not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency)):
            raise _DataError("currency_schema_unknown")
        return frame, currency, {key: key.title() for key in (*PRICES, "volume")}, True


def get_historical_provider(market: str) -> HistoricalDailyProvider:
    """Explicit research factory, not the production registry/get_provider."""
    if market == "CN":
        return AKShareDailyProvider()
    if market == "US":
        return YFinanceDailyProvider()
    raise ValueError("historical v1 supports CN/US only")
