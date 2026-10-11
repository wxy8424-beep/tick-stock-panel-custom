"""Explicit research-only top-N portfolios from existing factor scores."""
from __future__ import annotations

import json
import math
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from app.factors.engine import CalculationMode, CompatibilityBackend
from app.market_session import market_from_symbol


class Selection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    top_n: int = Field(ge=1, le=100, strict=True)
    weighting: Literal["equal"] = "equal"


class PortfolioDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    portfolio_id: str = Field(default_factory=lambda: str(uuid4()), pattern=r"^[A-Za-z0-9_-]{1,128}$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    symbols: tuple[str, ...] = Field(max_length=100)
    selection: Selection
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def universe(self):
        if len(set(self.symbols)) != len(self.symbols) or any(
            market_from_symbol(symbol) is None or len(symbol) > 128 for symbol in self.symbols
        ):
            raise ValueError("unique known-market symbols required")
        return self


class FactorValue(BaseModel):
    model_config = ConfigDict(extra="ignore")
    value: FiniteFloat | None = Field(strict=True)
    score: FiniteFloat | None = Field(ge=0, le=1, strict=True)
    reason: Literal["no_quote_on_as_of", "insufficient_or_invalid_history", "history_or_calculation_error"] | None = None


class ScoreRow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    symbol: str = Field(max_length=128)
    factors: dict[str, FactorValue]
    total_score: FiniteFloat | None = Field(ge=0, le=1, strict=True)
    status: Literal["scored", "unavailable"]

    @model_validator(mode="after")
    def consistent(self):
        if not self.factors or len(self.factors) > 7 or any(len(name) > 128 for name in self.factors):
            raise ValueError("factor score details required")
        available = all(item.score is not None and item.value is not None for item in self.factors.values())
        if (self.status == "scored") != (self.total_score is not None) or available != (self.total_score is not None):
            raise ValueError("inconsistent score availability")
        if available and not math.isclose(self.total_score,
                                         math.fsum(item.score for item in self.factors.values()) / len(self.factors),
                                         rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("total score must match existing equal-weight factor scores")
        return self


class ScoreFactor(BaseModel):
    model_config = ConfigDict(extra="ignore")
    output_column: str = Field(min_length=1, max_length=128)
    direction: Literal["high", "low"]
    weight: FiniteFloat = Field(gt=0, le=1, strict=True)
    period: int | None = None


class ScoreInput(BaseModel):
    """Allowlisted snapshot of FactorScoringEngine's output, no arbitrary payloads."""
    model_config = ConfigDict(extra="ignore")
    as_of: date
    history_start: date
    method: Literal["rank", "normalization"]
    mode: CalculationMode
    compatibility_backend: CompatibilityBackend | None = None
    price_basis: Literal["as_provided", "raw", "qfq"]
    aggregation: Literal["equal_weight_complete_case"]
    factors: tuple[ScoreFactor, ...] = Field(min_length=1, max_length=7)
    rows: tuple[ScoreRow, ...] = Field(max_length=100)

    @model_validator(mode="after")
    def consistent(self):
        if self.history_start > self.as_of or (self.mode == "backtest_compat") != (self.compatibility_backend is not None):
            raise ValueError("invalid score date range or semantic mode")
        columns = {item.output_column for item in self.factors}
        if len(columns) != len(self.factors) or any(set(row.factors) != columns for row in self.rows):
            raise ValueError("factor detail columns must match score metadata")
        if any(not math.isclose(item.weight, 1 / len(self.factors), abs_tol=1e-12) for item in self.factors):
            raise ValueError("v1 requires existing equal-weight score aggregation")
        symbols = [row.symbol for row in self.rows]
        if len(set(symbols)) != len(symbols) or any(market_from_symbol(symbol) is None for symbol in symbols):
            raise ValueError("duplicate or unknown score symbol")
        return self


class PortfolioBuilder:
    """Pure construction: no repository/provider, orders, capital or rebalancing."""

    def build(self, definition: PortfolioDefinition, factor_scores: dict) -> dict:
        definition = PortfolioDefinition.model_validate(definition.model_dump())
        source = ScoreInput.model_validate(factor_scores)
        scores = {row.symbol: row for row in source.rows}
        candidates = [scores[symbol] for symbol in definition.symbols
                      if symbol in scores and scores[symbol].status == "scored"]
        candidates.sort(key=lambda row: (-row.total_score, row.symbol))
        selected = candidates[:definition.selection.top_n]
        selected_symbols = [row.symbol for row in selected]
        excluded = [{"symbol": symbol, "reason": "missing_score" if symbol not in scores else
                     "unavailable_score" if scores[symbol].status != "scored" else "outside_top_n"}
                    for symbol in sorted(definition.symbols) if symbol not in selected_symbols]
        means = {}
        for factor in source.factors:
            items = [row.factors[factor.output_column] for row in selected]
            means[factor.output_column] = {
                "mean_value": math.fsum(item.value / len(items) for item in items) if items else None,
                "mean_score": math.fsum(item.score for item in items) / len(items) if items else None,
            }
        markets = {market_from_symbol(symbol) for symbol in definition.symbols}
        warnings = []
        if len(markets) > 1:
            warnings.append("cross_market_no_currency_adjustment")
        if set(scores) != set(definition.symbols):
            warnings.append("score_universe_differs_from_portfolio")
        return {"portfolio_id": definition.portfolio_id, "status": "completed" if selected else "empty",
                "selection": definition.selection.model_dump(), "selected_symbols": selected_symbols,
                "weights": {row.symbol: 1 / len(selected) for row in selected},
                "score_summary": {"requested_count": len(definition.symbols), "eligible_count": len(candidates),
                                  "selected_count": len(selected),
                                  "mean_total_score": math.fsum(row.total_score for row in selected) / len(selected) if selected else None,
                                  "factors": means},
                "excluded": excluded, "warnings": warnings,
                "source_scores": source.model_dump(mode="json")}


class PortfolioStore:
    """Local definitions/results are separate; query never creates storage."""

    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "user_data" / "research_portfolios.sqlite3"

    def save(self, definition: PortfolioDefinition, factor_scores: dict) -> dict:
        # Build/validate before IO, and persist definition plus result atomically.
        result = PortfolioBuilder().build(definition, factor_scores)
        definition_json = PortfolioDefinition.model_validate(definition.model_dump()).model_dump_json()
        result_json = json.dumps(result, allow_nan=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("CREATE TABLE IF NOT EXISTS portfolio_definitions (portfolio_id TEXT PRIMARY KEY, definition TEXT NOT NULL)")
            db.execute("""CREATE TABLE IF NOT EXISTS portfolio_results (
                id INTEGER PRIMARY KEY, portfolio_id TEXT NOT NULL REFERENCES portfolio_definitions(portfolio_id),
                result TEXT NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS portfolio_results_lookup ON portfolio_results(portfolio_id, id DESC)")
            existing = db.execute("SELECT definition FROM portfolio_definitions WHERE portfolio_id=?", (definition.portfolio_id,)).fetchone()
            if existing and existing[0] != definition_json:
                raise ValueError("portfolio definition cannot be overwritten")
            if not existing:
                db.execute("INSERT INTO portfolio_definitions VALUES (?, ?)", (definition.portfolio_id, definition_json))
            db.execute("INSERT INTO portfolio_results(portfolio_id, result) VALUES (?, ?)",
                       (definition.portfolio_id, result_json))
        return result

    def _query(self, sql: str, params: tuple) -> list:
        if not self.path.exists():
            return []
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            return db.execute(sql, params).fetchall()

    def get_definition(self, portfolio_id: str) -> PortfolioDefinition | None:
        rows = self._query("SELECT definition FROM portfolio_definitions WHERE portfolio_id=?", (portfolio_id,))
        return PortfolioDefinition.model_validate_json(rows[0][0]) if rows else None

    def get_results(self, portfolio_id: str, *, limit: int = 20) -> list[dict]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        return [json.loads(row[0]) for row in self._query(
            "SELECT result FROM portfolio_results WHERE portfolio_id=? ORDER BY id DESC LIMIT ?",
            (portfolio_id, limit),
        )]
