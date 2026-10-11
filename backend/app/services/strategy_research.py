"""Offline strategy research proposals; never orders or live rebalancing."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.factors.engine import CalculationMode, CompatibilityBackend, DailyHistory
from app.factors.research_scoring import FactorScoringEngine, ScoringFactor
from app.services.research_portfolios import PortfolioBuilder, PortfolioDefinition, Selection


class ResearchFactor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str = Field(min_length=1, max_length=128)
    period: int | None = Field(default=None, strict=True)
    component: str | None = Field(default=None, max_length=128)
    direction: Literal["high", "low"] = "high"

    def scoring_factor(self) -> ScoringFactor:
        return ScoringFactor(self.name, self.period, self.component, self.direction)


class StrategyDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    strategy_id: str = Field(default_factory=lambda: str(uuid4()), pattern=r"^[A-Za-z0-9_-]{1,128}$")
    name: str = Field(min_length=1, max_length=200)
    universe: tuple[str, ...] = Field(max_length=100)
    factors: tuple[ResearchFactor, ...] = Field(min_length=1, max_length=7)
    portfolio_rules: Selection
    rebalance_frequency: Literal["daily", "weekly", "monthly"]
    scoring_method: Literal["rank", "normalization"] = "rank"
    mode: CalculationMode = "research"
    compatibility_backend: CompatibilityBackend | None = None
    price_basis: Literal["as_provided", "raw", "qfq"] = "as_provided"
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_inputs(self):
        PortfolioDefinition(name=self.name, symbols=self.universe, selection=self.portfolio_rules)
        # Public scorer validates registry, factor parameters and semantic mode,
        # even with an empty universe. It performs no history/provider reads.
        FactorScoringEngine().score(None, (), tuple(item.scoring_factor() for item in self.factors),
                                    as_of=date(2000, 1, 1), history_start=date(2000, 1, 1),
                                    method=self.scoring_method, mode=self.mode,
                                    compatibility_backend=self.compatibility_backend,
                                    price_basis=self.price_basis)
        return self


class StrategyResearchRunner:
    """Explicit dates only; select the first supplied session in each period.

    Supplied dates must be independently verified by the caller. No calendar
    inference, execution prices, returns, scheduled work or production changes.
    Missing scores block the whole event, avoiding silent survivor selection.
    """

    def run(self, definition: StrategyDefinition, repository: DailyHistory, *,
            session_dates: tuple[date, ...], history_start: date) -> dict:
        definition = StrategyDefinition.model_validate(definition.model_dump())
        if (type(history_start) is not date or len(session_dates) > 1000
                or any(type(day) is not date for day in session_dates)
                or tuple(sorted(set(session_dates))) != session_dates
                or (session_dates and history_start > session_dates[0])):
            raise ValueError("ordered unique Date sessions (maximum 1000) and prior history_start required")
        periods, dates = set(), []
        for day in session_dates:
            period = (day if definition.rebalance_frequency == "daily" else
                      day.isocalendar()[:2] if definition.rebalance_frequency == "weekly" else
                      (day.year, day.month))
            if period not in periods:
                periods.add(period)
                dates.append(day)
        events = []
        for day in dates:
            scores = FactorScoringEngine().score(
                repository, definition.universe, tuple(item.scoring_factor() for item in definition.factors),
                as_of=day, history_start=history_start, method=definition.scoring_method,
                mode=definition.mode, compatibility_backend=definition.compatibility_backend,
                price_basis=definition.price_basis,
            )
            blockers = [{"symbol": row["symbol"], "factor": column, "reason": value["reason"]}
                        for row in scores["rows"] for column, value in row["factors"].items()
                        if value["score"] is None]
            candidate = None
            if not blockers and definition.universe:
                candidate = PortfolioBuilder().build(PortfolioDefinition(
                    portfolio_id=str(uuid5(NAMESPACE_URL, f"strategy:{definition.strategy_id}:{day.isoformat()}")),
                    name=definition.name, symbols=definition.universe, selection=definition.portfolio_rules,
                    created_at=definition.created_at,
                ), scores)
            events.append({"event_date": day.isoformat(), "kind": "research_rebalance_proposal",
                           "status": "blocked" if blockers else "candidate" if candidate else "empty",
                           "blockers": blockers, "factor_scores": scores, "portfolio_candidate": candidate})
        generated = sum(event["status"] == "candidate" for event in events)
        blocked = sum(event["status"] == "blocked" for event in events)
        status = "empty" if not events or not definition.universe else (
            "completed" if not blocked else "partial" if generated else "blocked")
        return {"strategy_definition": definition.model_dump(mode="json"), "execution_status": status,
                "session_dates": [day.isoformat() for day in session_dates],
                "history_start": history_start.isoformat(), "events": events,
                "result_summary": {"event_count": len(events), "candidate_count": generated,
                                   "blocked_count": blocked, "returns": None,
                                   "returns_status": "not_evaluated_v1"},
                "assumptions": {"schedule": "first_supplied_session_per_period",
                                "session_calendar": "caller_verified",
                                "history": "caller_supplied_not_frozen_by_framework",
                                "execution": "research_only_no_trades"}}


class StrategyResearchStore:
    """Independent local SQLite definition/result store with read-only queries."""

    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "user_data" / "research_strategies.sqlite3"

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("CREATE TABLE IF NOT EXISTS strategy_definitions (strategy_id TEXT PRIMARY KEY, definition TEXT NOT NULL)")
        db.execute("""CREATE TABLE IF NOT EXISTS strategy_results (
            id INTEGER PRIMARY KEY, strategy_id TEXT NOT NULL REFERENCES strategy_definitions(strategy_id),
            result TEXT NOT NULL)""")
        db.execute("CREATE INDEX IF NOT EXISTS strategy_results_lookup ON strategy_results(strategy_id, id DESC)")
        return db

    def save_definition(self, definition: StrategyDefinition) -> None:
        definition = StrategyDefinition.model_validate(definition.model_dump())
        payload = definition.model_dump_json()
        with closing(self._connect()) as db, db:
            existing = db.execute("SELECT definition FROM strategy_definitions WHERE strategy_id=?",
                                  (definition.strategy_id,)).fetchone()
            if existing and existing[0] != payload:
                raise ValueError("strategy definition cannot be overwritten")
            if not existing:
                db.execute("INSERT INTO strategy_definitions VALUES (?, ?)", (definition.strategy_id, payload))

    def execute(self, strategy_id: str, repository: DailyHistory, *,
                session_dates: tuple[date, ...], history_start: date) -> dict:
        definition = self.get_definition(strategy_id)
        if definition is None:
            raise KeyError("unknown research strategy")
        # Validation/calculation precedes writes. Unexpected errors never persist
        # a successful run, and their messages are not saved.
        result = StrategyResearchRunner().run(definition, repository,
                                             session_dates=session_dates, history_start=history_start)
        payload = json.dumps(result, allow_nan=False)
        with closing(self._connect()) as db, db:
            db.execute("INSERT INTO strategy_results(strategy_id, result) VALUES (?, ?)", (strategy_id, payload))
        return result

    def _query(self, sql: str, params: tuple) -> list:
        if not self.path.exists():
            return []
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            return db.execute(sql, params).fetchall()

    def get_definition(self, strategy_id: str) -> StrategyDefinition | None:
        rows = self._query("SELECT definition FROM strategy_definitions WHERE strategy_id=?", (strategy_id,))
        return StrategyDefinition.model_validate_json(rows[0][0]) if rows else None

    def get_results(self, strategy_id: str, *, limit: int = 20) -> list[dict]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        return [json.loads(row[0]) for row in self._query(
            "SELECT result FROM strategy_results WHERE strategy_id=? ORDER BY id DESC LIMIT ?", (strategy_id, limit))]
