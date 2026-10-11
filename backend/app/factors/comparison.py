"""Read-only semantic comparison; not used by production factor consumers."""
from __future__ import annotations

import math
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import date

import polars as pl

from app.factors.engine import CompatibilityBackend, DailyHistory, FactorRequest, MarketFactorEngine


def _factor(name: str) -> tuple[FactorRequest, list[str]]:
    """Only the five audited price-factor families; reuse engine definitions."""
    if not isinstance(name, str):
        raise ValueError("factor name must be a string")
    name = name.lower()
    component = name if name in {"macd_dif", "macd_dea", "macd_hist"} else None
    if component:
        request = FactorRequest("macd")
    elif name in {"ma", "ema", "macd", "rsi", "atr"}:
        request = FactorRequest(name)
    elif match := re.fullmatch(r"(ma|ema|rsi|atr)_?(\d+)", name):
        request = FactorRequest(match[1], int(match[2]))
    else:
        raise ValueError("comparison supports MA, EMA, MACD, RSI and ATR only")
    columns = list(request.definition()[0])
    return request, [component] if component else columns


@dataclass(frozen=True)
class FactorComparisonResult:
    payload: dict

    def to_dict(self) -> dict:
        return deepcopy(self.payload)


class FactorComparison:
    """Compare identical observed bars, with explicit history and tolerances.

    No writes, providers, strategy execution or snapshot/daily reconstruction.
    Reasons describe audited policy differences, not inferred exchange events.
    """

    def compare(self, history: pl.DataFrame, symbol: str, start: date, end: date,
                factor_name: str, *, compatibility_backend: CompatibilityBackend,
                history_start: date | None = None, price_basis: str = "as_provided",
                relative_tolerance: float = 1e-6, absolute_tolerance: float = 1e-10) -> FactorComparisonResult:
        request, columns = _factor(factor_name)
        history_start = start if history_start is None else history_start
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol must be a nonempty string")
        if not history_start <= start <= end:
            raise ValueError("invalid comparison date range")
        for tolerance in (relative_tolerance, absolute_tolerance):
            if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)):
                raise ValueError("tolerances must be finite nonnegative numbers")
            if not math.isfinite(tolerance) or tolerance < 0:
                raise ValueError("tolerances must be finite nonnegative numbers")
        engine = MarketFactorEngine()
        engine._validate_mode("backtest_compat", compatibility_backend)
        work = history
        if not work.is_empty():
            if not {"symbol", "date"} <= set(work.columns) or work.schema["date"] != pl.Date:
                raise ValueError("comparison requires symbol and Date columns")
            work = work.filter((pl.col("symbol") == symbol) & pl.col("date").is_between(history_start, end))
        research = engine.compute(work, (request,), price_basis=price_basis)
        _, minimum, required = request.definition()
        missing_columns = [column for column in required
                           if column not in work.columns or not work.schema[column].is_numeric()]
        compat = None
        # Empty input is a valid empty comparison even if its schema is absent.
        if work.is_empty() or not missing_columns:
            compat = engine.compute(work, (request,), price_basis=price_basis,
                                    mode="backtest_compat", compatibility_backend=compatibility_backend)
        research_rows = research.frame.to_dicts()
        compat_rows = compat.frame.to_dicts() if compat is not None else []
        input_rows = work.sort("symbol", "date").to_dicts() if not work.is_empty() else []
        rows = []
        segment_bars, previous_invalid = 0, False
        recursive = request.kind in {"ema", "macd", "rsi", "atr"}
        for index, (source, strict) in enumerate(zip(input_rows, research_rows, strict=True)):
            invalid = [column for column in required if not self._positive(source.get(column))]
            if (request.kind == "atr" and not invalid
                    and not source["low"] <= source["close"] <= source["high"]):
                invalid.append("ohlc_relationship")
            if invalid:
                segment_bars = 0
            else:
                segment_bars += 1
            compatible = compat_rows[index] if compat is not None else {}
            if start <= source["date"] <= end:
                for column in columns:
                    left, right = strict[column], compatible.get(column)
                    status = "unavailable" if compat is None else self._status(
                        left, right, relative_tolerance, absolute_tolerance,
                    )
                    reasons = []
                    if status == "unavailable" or (invalid and status != "equal"):
                        reasons.append("missing_data")
                    elif status == "different":
                        if left is None and right is not None and segment_bars < minimum:
                            reasons.append("warmup")
                        if previous_invalid:
                            reasons.append("gap_handling")
                            if recursive and left is not None and right is not None:
                                reasons.append("initialization")
                        if not reasons:
                            # E.g. backend precision differences: not a new seed policy.
                            reasons.append("unknown")
                    difference = left - right if left is not None and right is not None else None
                    overflow = difference is not None and not math.isfinite(difference)
                    rows.append({
                        "symbol": symbol, "date": source["date"].isoformat(), "factor": column,
                        "research": left, "backtest_compat": right,
                        "difference": None if overflow else difference,
                        "status": status, "difference_reason": reasons[0] if reasons else None,
                        "difference_reasons": reasons,
                        "evidence": {"invalid_inputs": invalid, "segment_bars": segment_bars,
                                     "research_minimum_bars": minimum,
                                     "previous_invalid_observation": previous_invalid,
                                     "recursive_factor": recursive,
                                     "difference_overflow": overflow},
                    })
            previous_invalid |= bool(invalid)
        return FactorComparisonResult({
            "symbol": symbol, "start": start.isoformat(), "end": end.isoformat(),
            "history_start": history_start.isoformat(), "factor_name": factor_name,
            "compatibility_backend": compatibility_backend, "price_basis": price_basis,
            "difference_direction": "research_minus_backtest_compat",
            "relative_tolerance": relative_tolerance, "absolute_tolerance": absolute_tolerance,
            "status": "empty" if not rows else "unavailable" if compat is None else "compared",
            "compatibility_error": "missing_numeric_price_columns" if compat is None else None,
            "missing_columns": missing_columns if compat is None else [],
            "summary": {state: sum(row["status"] == state for row in rows)
                        for state in ("equal", "within_tolerance", "different", "unavailable")},
            "rows": rows,
        })

    @staticmethod
    def _positive(value) -> bool:
        try:
            return value is not None and math.isfinite(value) and value > 0
        except (TypeError, ValueError, OverflowError):
            return False

    @staticmethod
    def _status(left, right, relative_tolerance, absolute_tolerance):
        if left == right:
            return "equal"
        if left is None or right is None:
            return "different"
        if math.isclose(left, right, rel_tol=relative_tolerance, abs_tol=absolute_tolerance):
            return "within_tolerance"
        return "different"

    def from_history(self, repository: DailyHistory, asset_type: str, symbol: str,
                     start: date, end: date, factor_name: str, *,
                     compatibility_backend: CompatibilityBackend,
                     history_start: date | None = None, **options) -> FactorComparisonResult:
        """One existing history read shared by both modes; no source switching."""
        if asset_type not in {"stock", "etf", "index"}:
            raise ValueError("unknown asset type")
        # Validate all options before asking the supplied history reader for data.
        self.compare(pl.DataFrame(), symbol, start, end, factor_name,
                     compatibility_backend=compatibility_backend,
                     history_start=history_start, **options)
        history_start = start if history_start is None else history_start
        frame = repository.get_daily_asset(asset_type, symbol, history_start, end,
                                           columns=["symbol", "date", "close", "high", "low"])
        return self.compare(frame, symbol, start, end, factor_name,
                            compatibility_backend=compatibility_backend,
                            history_start=history_start, **options)
