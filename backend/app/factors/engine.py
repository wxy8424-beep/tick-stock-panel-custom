"""Stateless history-factor facade over the existing shared indicator pipeline."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol

import polars as pl

from app.indicators.pipeline import compute_indicators


class DailyHistory(Protocol):
    def get_daily_asset(self, asset_type: str, symbol: str, start: date, end: date,
                        columns: list[str] | None = None) -> pl.DataFrame: ...


@dataclass(frozen=True)
class FactorRequest:
    kind: str
    period: int | None = None

    def definition(self) -> tuple[dict[str, str], int, tuple[str, ...]]:
        """Output -> shared source column, minimum bars, required prices."""
        if not isinstance(self.kind, str) or not self.kind:
            raise ValueError("factor kind must be a nonempty string")
        kind = self.kind.lower()
        default = {"ma": 20, "ema": 20, "macd": None, "rsi": 14,
                   "roc": 20, "atr": 14, "volatility": 20}
        if kind not in default:
            raise ValueError("factor unavailable; volume-dependent factors are not supported")
        period = default[kind] if self.period is None else self.period
        if period is not None and (isinstance(period, bool) or not isinstance(period, int)):
            raise ValueError("period must be an integer")
        allowed = {"ma": (5, 10, 20, 30, 60), "ema": (5, 10, 20, 30, 60),
                   "roc": (5, 10, 20, 30, 60), "rsi": (6, 14, 24),
                   "atr": (14,), "volatility": (20,), "macd": (None,)}
        if period not in allowed[kind]:
            raise ValueError("period unavailable in the existing shared implementation")
        if kind == "macd":
            return {name: name for name in ("macd_dif", "macd_dea", "macd_hist")}, 34, ("close",)
        if kind in {"ma", "ema"}:
            name = f"{kind}{period}"
            return {name: name}, period, ("close",)
        if kind == "roc":
            return {f"roc_{period}": f"momentum_{period}d"}, period + 1, ("close",)
        if kind == "volatility":
            return {"annual_vol_20d": "annual_vol_20d"}, 21, ("close",)
        if kind == "atr":
            return {"atr_14": "atr_14"}, 14, ("close", "high", "low")
        return {f"rsi_{period}": f"rsi_{period}"}, period + 1, ("close",)


DEFAULT_FACTORS = tuple(FactorRequest(kind) for kind in
                        ("ma", "ema", "macd", "rsi", "roc", "atr", "volatility"))


@dataclass(frozen=True)
class FactorResult:
    frame: pl.DataFrame
    factors: tuple[dict, ...]
    price_basis: str

    def to_dict(self) -> dict:
        rows = self.frame.to_dicts()
        for row in rows:
            row["date"] = row["date"].isoformat()
        return {"rows": rows, "factors": deepcopy(list(self.factors)),
                "price_basis": self.price_basis, "uses_volume": False}


class MarketFactorEngine:
    """No provider, calendar, cache, storage writes or trade dependencies.

    Input dates are observed daily bars, not fabricated business-day indexes.
    Invalid price rows break recursive history; windows never bridge unknown gaps.
    Price adjustment/currency semantics are supplied by the caller, never guessed.
    """

    def compute(self, history: pl.DataFrame, requests: tuple[FactorRequest, ...] = DEFAULT_FACTORS,
                *, price_basis: Literal["as_provided", "raw", "qfq"] = "as_provided") -> FactorResult:
        if price_basis not in {"as_provided", "raw", "qfq"}:
            raise ValueError("unknown price basis")
        definitions = [(request, *request.definition()) for request in requests]
        outputs = [column for _, mapping, _, _ in definitions for column in mapping]
        if len(outputs) != len(set(outputs)):
            raise ValueError("duplicate factor request")
        if history.is_empty():
            frame = pl.DataFrame(schema={"symbol": pl.String, "date": pl.Date,
                                         **dict.fromkeys(outputs, pl.Float64)})
            return self._result(frame, definitions, price_basis, "empty_history")
        if not {"symbol", "date"} <= set(history.columns) or history.schema["date"] != pl.Date:
            raise ValueError("daily history requires symbol and Date columns")
        if history.schema["symbol"] != pl.String:
            raise ValueError("symbol must be a string column")
        if history.filter(pl.col("symbol").is_null() | (pl.col("symbol") == "") | pl.col("date").is_null()).height:
            raise ValueError("null history keys")
        if history.select(pl.struct("symbol", "date").is_duplicated().any()).item():
            raise ValueError("duplicate history keys")
        prices = []
        for column in ("close", "high", "low"):
            if column not in history.columns or not history.schema[column].is_numeric():
                prices.append(pl.lit(None, dtype=pl.Float64).alias(column))
            else:
                number = pl.col(column).cast(pl.Float64)
                prices.append(pl.when(number.is_finite() & (number > 0)).then(number).alias(column))
        work = history.select("symbol", "date", *prices).sort("symbol", "date")
        result = work.select("symbol", "date")
        # Only two dependency groups: close-only and OHLC-required ATR. Missing
        # high/low cannot suppress otherwise valid close-only factors.
        for required in (("close",), ("close", "high", "low")):
            selected = [item for item in definitions if item[3] == required]
            if not selected:
                continue
            mapping = {target: source for _, fields, _, _ in selected for target, source in fields.items()}
            valid = pl.all_horizontal(pl.col(column).is_not_null() for column in required)
            if len(required) > 1:
                valid &= (pl.col("high") >= pl.col("low")) & pl.col("close").is_between(pl.col("low"), pl.col("high"))
            segmented = work.with_columns((~valid).cast(pl.Int64).cum_sum().over("symbol").alias("_segment"))
            segments = segmented.filter(valid).partition_by(["symbol", "_segment"], maintain_order=True)
            calculated = []
            for segment in segments:
                frame = compute_indicators(segment.drop("_segment"), needed=set(mapping.values()), assume_sorted=True)
                frame = frame.with_columns(pl.int_range(1, pl.len() + 1).alias("_bars"))
                values = []
                for _, fields, minimum, _ in selected:
                    for target, source in fields.items():
                        value = pl.col(source).cast(pl.Float64)
                        values.append(pl.when((pl.col("_bars") >= minimum) & value.is_finite()).then(value).alias(target))
                calculated.append(frame.select("symbol", "date", *values))
            if calculated:
                result = result.join(pl.concat(calculated), on=["symbol", "date"], how="left")
            else:
                result = result.with_columns(pl.lit(None, dtype=pl.Float64).alias(column) for column in mapping)
        result = result.select("symbol", "date", *outputs).sort("symbol", "date")
        return self._result(result, definitions, price_basis, "insufficient_or_invalid_history")

    @staticmethod
    def _result(frame, definitions, price_basis, reason):
        metadata = []
        for request, mapping, minimum, _ in definitions:
            counts = [frame[column].len() - frame[column].null_count() for column in mapping]
            state = "available" if counts and min(counts) else "unavailable"
            metadata.append({"kind": request.kind.lower(), "columns": list(mapping),
                             "warmup_bars": minimum, "state": state,
                             "reason": None if state == "available" else reason})
        return FactorResult(frame, tuple(metadata), price_basis)

    def from_history(self, repository: DailyHistory, asset_type: str, symbol: str,
                     start: date, end: date, requests: tuple[FactorRequest, ...] = DEFAULT_FACTORS,
                     *, history_start: date | None = None, price_basis="as_provided") -> FactorResult:
        """Read existing daily API only; caller specifies extra warmup history.

        No calendar-day heuristic for a trading-bar window. Repositories may lack
        HK/US history: empty input remains unavailable, not a provider fallback.
        """
        if asset_type not in {"stock", "etf", "index"}:
            raise ValueError("unknown asset type")
        history_start = start if history_start is None else history_start
        if not history_start <= start <= end:
            raise ValueError("invalid history range")
        for request in requests:
            request.definition()
        frame = repository.get_daily_asset(asset_type, symbol, history_start, end,
                                           columns=["symbol", "date", "close", "high", "low"])
        if not frame.is_empty():
            # Do not trust out-of-range or other-symbol rows from a cache/API.
            frame = frame.filter((pl.col("symbol") == symbol) & pl.col("date").is_between(history_start, end))
        result = self.compute(frame, requests, price_basis=price_basis)
        trimmed = result.frame.filter(pl.col("date").is_between(start, end))
        definitions = [(request, *request.definition()) for request in requests]
        return self._result(trimmed, definitions, price_basis, "no_usable_history_in_range")
