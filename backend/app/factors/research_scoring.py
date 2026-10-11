"""Read-only cross-sectional research scores, separate from strategy scoring."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

import polars as pl

from app.factors.engine import (
    CalculationMode,
    CompatibilityBackend,
    DailyHistory,
    FactorRequest,
    MarketFactorEngine,
)
from app.factors.registry import get_engine_factor
from app.market_session import market_from_symbol


@dataclass(frozen=True)
class ScoringFactor:
    name: str
    period: int | None = None
    component: str | None = None
    direction: Literal["high", "low"] = "high"

    def definition(self) -> tuple[FactorRequest, str]:
        metadata = get_engine_factor(self.name)
        if metadata is None:
            raise ValueError("unknown registered factor")
        if self.direction not in {"high", "low"}:
            raise ValueError("unknown score direction")
        request = FactorRequest(metadata.name, self.period)
        outputs, _, _ = request.definition()
        if self.component is None:
            if len(outputs) != 1:
                raise ValueError("multi-output factor requires explicit component")
            column = next(iter(outputs))
        else:
            column = self.component
            if column not in outputs:
                raise ValueError("component not in factor outputs")
        return request, column


class FactorScoringEngine:
    """No writes, experiment runs, strategy scores, provider fallback or trades.

    A single as_of date is required; previous-date values never fill missing rows.
    Equal weights require all requested scores, with null composite otherwise.
    """

    def score(self, repository: DailyHistory, symbols: tuple[str, ...],
              factors: tuple[ScoringFactor, ...], *, as_of: date, history_start: date,
              method: Literal["rank", "normalization"] = "rank",
              mode: CalculationMode = "research",
              compatibility_backend: CompatibilityBackend | None = None,
              price_basis: Literal["as_provided", "raw", "qfq"] = "as_provided") -> dict:
        if method not in {"rank", "normalization"}:
            raise ValueError("unknown scoring method")
        if type(as_of) is not date or type(history_start) is not date or history_start > as_of:
            raise ValueError("explicit ordered Date history range required")
        if len(symbols) > 100 or len(set(symbols)) != len(symbols) or any(
            market_from_symbol(symbol) is None or len(symbol) > 128 for symbol in symbols
        ):
            raise ValueError("symbols must be unique known-market securities (maximum 100)")
        if not 1 <= len(factors) <= 7:
            raise ValueError("select between one and seven factor families")
        definitions = [factor.definition() for factor in factors]
        requests = tuple(request for request, _ in definitions)
        if len({request.kind for request in requests}) != len(requests):
            raise ValueError("duplicate factor family")
        # Validate through the public Engine even for empty symbol inputs. This
        # checks semantic mode/backend/price basis without calculating data.
        engine = MarketFactorEngine()
        engine.compute(pl.DataFrame(), requests, mode=mode,
                       compatibility_backend=compatibility_backend, price_basis=price_basis)
        rows = []
        for symbol in symbols:
            row = {"symbol": symbol, "factors": {}, "total_score": None, "status": "unavailable"}
            data, reason = None, "no_quote_on_as_of"
            try:
                result = engine.from_history(repository, "stock", symbol, as_of, as_of, requests,
                                             history_start=history_start, mode=mode,
                                             compatibility_backend=compatibility_backend, price_basis=price_basis)
                if not result.frame.is_empty():
                    data = result.frame.row(0, named=True)
                    reason = "insufficient_or_invalid_history"
            except Exception:
                # Do not leak repository paths, raw exceptions or credentials.
                reason = "history_or_calculation_error"
            for _, column in definitions:
                value = data.get(column) if data else None
                valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                row["factors"][column] = {"value": value if valid else None, "score": None,
                                          "reason": None if valid else reason}
            rows.append(row)
        metadata = []
        for factor, (request, column) in zip(factors, definitions, strict=True):
            valid_rows = [row for row in rows if row["factors"][column]["value"] is not None]
            values = [row["factors"][column]["value"] for row in valid_rows]
            scores = self._scores(values, method, factor.direction)
            for row, score in zip(valid_rows, scores, strict=True):
                row["factors"][column]["score"] = score
            metadata.append({"registry": get_engine_factor(request.kind).to_dict(),
                             "period": factor.period, "output_column": column,
                             "direction": factor.direction, "weight": 1 / len(factors),
                             "valid_count": len(values), "minimum": min(values) if values else None,
                             "maximum": max(values) if values else None,
                             "score_state": "unavailable" if not values else
                             "neutral" if min(values) == max(values) else method})
        for row in rows:
            scores = [value["score"] for value in row["factors"].values()]
            if all(score is not None for score in scores):
                row.update(total_score=math.fsum(scores) / len(scores), status="scored")
        scored = sum(row["status"] == "scored" for row in rows)
        markets = {market_from_symbol(symbol) for symbol in symbols}
        return {"as_of": as_of.isoformat(), "history_start": history_start.isoformat(),
                "method": method, "mode": mode, "compatibility_backend": compatibility_backend,
                "price_basis": price_basis, "aggregation": "equal_weight_complete_case",
                "status": "empty" if not rows else "completed" if scored == len(rows)
                else "unavailable" if not scored else "partial",
                "warnings": ["cross_market_no_currency_adjustment"] if len(markets) > 1 else [],
                "factors": metadata, "rows": rows}

    @staticmethod
    def _scores(values: list[float], method: str, direction: str) -> list[float]:
        if not values:
            return []
        if min(values) == max(values):
            return [0.5] * len(values)
        if method == "rank":
            ranks = pl.Series(values).rank(method="average").to_list()
            scores = [(rank - 1) / (len(values) - 1) for rank in ranks]
        else:
            # Decimal avoids finite input subtraction overflowing to inf. This
            # is score scaling only, not a change to Factor Engine calculations.
            numbers = [Decimal(str(value)) for value in values]
            low, high = min(numbers), max(numbers)
            scores = [float((value - low) / (high - low)) for value in numbers]
        return [1 - score for score in scores] if direction == "low" else scores
