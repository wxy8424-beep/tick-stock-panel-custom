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

CalculationMode = Literal["research", "backtest_compat"]
CompatibilityBackend = Literal["polars", "matrix"]


@dataclass(frozen=True)
class FactorResult:
    frame: pl.DataFrame
    factors: tuple[dict, ...]
    price_basis: str
    mode: CalculationMode = "research"
    compatibility_backend: CompatibilityBackend | None = None

    def to_dict(self) -> dict:
        rows = self.frame.to_dicts()
        for row in rows:
            row["date"] = row["date"].isoformat()
        return {"rows": rows, "factors": deepcopy(list(self.factors)),
                "price_basis": self.price_basis, "uses_volume": False,
                "mode": self.mode, "compatibility_backend": self.compatibility_backend}


class MarketFactorEngine:
    """No provider, calendar, cache, storage writes or trade dependencies.

    Input dates are observed daily bars, not fabricated business-day indexes.
    Invalid price rows break recursive history; windows never bridge unknown gaps.
    Price adjustment/currency semantics are supplied by the caller, never guessed.
    """

    def compute(self, history: pl.DataFrame, requests: tuple[FactorRequest, ...] = DEFAULT_FACTORS,
                *, price_basis: Literal["as_provided", "raw", "qfq"] = "as_provided",
                mode: CalculationMode = "research",
                compatibility_backend: CompatibilityBackend | None = None) -> FactorResult:
        self._validate_mode(mode, compatibility_backend)
        if price_basis not in {"as_provided", "raw", "qfq"}:
            raise ValueError("unknown price basis")
        definitions = [(request, *request.definition()) for request in requests]
        outputs = [column for _, mapping, _, _ in definitions for column in mapping]
        if len(outputs) != len(set(outputs)):
            raise ValueError("duplicate factor request")
        if history.is_empty():
            frame = pl.DataFrame(schema={"symbol": pl.String, "date": pl.Date,
                                         **dict.fromkeys(outputs, pl.Float64)})
            return self._result(frame, definitions, price_basis, "empty_history", mode, compatibility_backend)
        if not {"symbol", "date"} <= set(history.columns) or history.schema["date"] != pl.Date:
            raise ValueError("daily history requires symbol and Date columns")
        if history.schema["symbol"] != pl.String:
            raise ValueError("symbol must be a string column")
        if history.filter(pl.col("symbol").is_null() | (pl.col("symbol") == "") | pl.col("date").is_null()).height:
            raise ValueError("null history keys")
        if history.select(pl.struct("symbol", "date").is_duplicated().any()).item():
            raise ValueError("duplicate history keys")
        if mode == "backtest_compat":
            # Preserve legacy input prices, seeds and missing-observation policy;
            # research sanitization/segmentation must not run before this branch.
            frame = self._compatibility_frame(history, definitions, compatibility_backend)
            return self._result(frame, definitions, price_basis, "insufficient_or_invalid_history",
                                mode, compatibility_backend)
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
    def _result(frame, definitions, price_basis, reason, mode="research", compatibility_backend=None):
        metadata = []
        for request, mapping, minimum, _ in definitions:
            counts = [frame[column].len() - frame[column].null_count() for column in mapping]
            state = "available" if counts and min(counts) else "unavailable"
            metadata.append({"kind": request.kind.lower(), "columns": list(mapping),
                             "warmup_bars": minimum,
                             "warmup_policy": "strict" if mode == "research" else "legacy_backend",
                             "state": state,
                             "reason": None if state == "available" else reason})
        return FactorResult(frame, tuple(metadata), price_basis, mode, compatibility_backend)

    @staticmethod
    def _validate_mode(mode, backend):
        if mode not in {"research", "backtest_compat"}:
            raise ValueError("unknown calculation mode")
        if mode == "research" and backend is not None:
            raise ValueError("research mode cannot select a compatibility backend")
        if mode == "backtest_compat" and backend not in {"polars", "matrix"}:
            raise ValueError("backtest_compat requires explicit polars or matrix backend")

    @staticmethod
    def _compatibility_frame(history, definitions, backend):
        mapping = {target: source for _, fields, _, _ in definitions for target, source in fields.items()}
        if not mapping:
            return history.select("symbol", "date").sort("symbol", "date")
        required = {column for _, _, _, columns in definitions for column in columns}
        for column in required:
            if column not in history.columns or not history.schema[column].is_numeric():
                raise ValueError(f"legacy compatibility requires numeric {column}")
        work = history.select("symbol", "date", *sorted(required)).sort("symbol", "date")
        if backend == "polars":
            frame = compute_indicators(work, needed=set(mapping.values()), assume_sorted=True)
        else:
            frame = MarketFactorEngine._matrix_compatibility(work, mapping)
        # BacktestEngine.load_panel_for_backtest normalizes nonfinite outputs.
        # Do not change finite values or mask seeded early results.
        values = []
        for target, source in mapping.items():
            value = pl.col(source).cast(pl.Float64)
            values.append(pl.when(value.is_finite()).then(value).alias(target))
        return frame.select("symbol", "date", *values)

    @staticmethod
    def _matrix_compatibility(work, mapping):
        """Reuse legacy effective-observation kernels; never construct trade data."""
        import numpy as np

        from app.backtest.matrix import MarketDataMatrix, matrix_feature

        symbols = tuple(work["symbol"].unique().sort().to_list())
        dates = work["date"].unique().sort().to_numpy()
        time_ids = np.searchsorted(dates, work["date"].to_numpy())
        asset_ids = np.searchsorted(symbols, work["symbol"].to_numpy())
        shape = (len(dates), len(symbols))

        def price(column):
            values = np.full(shape, np.nan, dtype=np.float32)
            if column in work.columns:
                values[time_ids, asset_ids] = work[column].cast(pl.Float32).to_numpy()
            values.flags.writeable = False
            return values

        unknown = price("_absent")
        disabled = np.zeros(shape, dtype=bool)
        disabled.flags.writeable = False
        market = MarketDataMatrix(
            timestamps=dates.astype("datetime64[ms]").astype(np.int64),
            timestamp_labels=tuple(str(day) for day in dates),
            session_ids=np.arange(len(dates), dtype=np.int32), symbols=symbols,
            names=tuple("" for _ in symbols), open=unknown, high=price("high"),
            low=price("low"), close=price("close"), volume=unknown,
            tradable=disabled, limit_up_locked=disabled, limit_down_locked=disabled, fields={},
        )
        # Volume stays NaN and no tradability/return simulation is performed.
        return work.select("symbol", "date").with_columns(
            pl.Series(source, matrix_feature(market, source)[time_ids, asset_ids])
            for source in set(mapping.values())
        )

    def from_history(self, repository: DailyHistory, asset_type: str, symbol: str,
                     start: date, end: date, requests: tuple[FactorRequest, ...] = DEFAULT_FACTORS,
                     *, history_start: date | None = None, price_basis="as_provided",
                     mode: CalculationMode = "research",
                     compatibility_backend: CompatibilityBackend | None = None) -> FactorResult:
        """Read existing daily API only; caller specifies extra warmup history.

        No calendar-day heuristic for a trading-bar window. Repositories may lack
        HK/US history: empty input remains unavailable, not a provider fallback.
        """
        if asset_type not in {"stock", "etf", "index"}:
            raise ValueError("unknown asset type")
        self._validate_mode(mode, compatibility_backend)
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
        result = self.compute(frame, requests, price_basis=price_basis, mode=mode,
                              compatibility_backend=compatibility_backend)
        trimmed = result.frame.filter(pl.col("date").is_between(start, end))
        definitions = [(request, *request.definition()) for request in requests]
        return self._result(trimmed, definitions, price_basis, "no_usable_history_in_range",
                            mode, compatibility_backend)
