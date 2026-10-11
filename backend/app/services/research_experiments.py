"""Explicit local research runs; no production consumers or strategy execution."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.factors.engine import (
    CalculationMode,
    CompatibilityBackend,
    DailyHistory,
    FactorRequest,
    MarketFactorEngine,
)
from app.factors.registry import get_engine_factor
from app.market_session import market_from_symbol
from app.services.snapshot_archive import SnapshotArchive


class DateRange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    start: date
    end: date

    @model_validator(mode="after")
    def ordered(self):
        if self.start > self.end:
            raise ValueError("invalid date range")
        return self


class ExperimentParameters(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    periods: dict[str, int] = Field(default_factory=dict)
    mode: CalculationMode = "research"
    compatibility_backend: CompatibilityBackend | None = None
    history_start: date | None = None
    price_basis: Literal["as_provided", "raw", "qfq"] = "as_provided"

    @model_validator(mode="after")
    def semantic_mode(self):
        if (self.mode == "backtest_compat") != (self.compatibility_backend is not None):
            raise ValueError("compatibility backend required only for backtest_compat")
        return self


class ExperimentDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    experiment_id: str = Field(default_factory=lambda: str(uuid4()), pattern=r"^[A-Za-z0-9_-]{1,128}$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    symbols: tuple[str, ...] = Field(min_length=1, max_length=100)
    factors: tuple[str, ...] = Field(min_length=1, max_length=7)
    parameters: ExperimentParameters = Field(default_factory=ExperimentParameters)
    date_range: DateRange
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def supported(self):
        if len(set(self.symbols)) != len(self.symbols) or any(
            len(symbol) > 128 or market_from_symbol(symbol) is None for symbol in self.symbols
        ):
            raise ValueError("symbols must be unique known-market securities")
        names = [name.lower() for name in self.factors]
        if len(set(names)) != len(names) or any(get_engine_factor(name) is None for name in names):
            raise ValueError("factors must be unique registered families")
        if not set(self.parameters.periods) <= set(names):
            raise ValueError("period parameter must reference a selected canonical factor")
        if self.parameters.history_start is not None and self.parameters.history_start > self.date_range.start:
            raise ValueError("history_start must not follow start")
        for name in names:
            FactorRequest(name, self.parameters.periods.get(name)).definition()
        return self


class ExperimentStore:
    """Separate immutable definitions and append-only run results.

    Queries open mode=ro and never create the database. Only explicit create/run
    writes research_experiments.sqlite3; the snapshot schema remains untouched.
    """

    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "user_data" / "research_experiments.sqlite3"

    def _connect_write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("CREATE TABLE IF NOT EXISTS experiments (experiment_id TEXT PRIMARY KEY, definition TEXT NOT NULL)")
        db.execute("""CREATE TABLE IF NOT EXISTS experiment_runs (
            run_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
            result TEXT NOT NULL, created_at TEXT NOT NULL)""")
        db.execute("CREATE INDEX IF NOT EXISTS experiment_runs_lookup ON experiment_runs(experiment_id, created_at DESC)")
        return db

    def create(self, definition: ExperimentDefinition) -> ExperimentDefinition:
        # Revalidate even frozen models: their nested period mapping may have
        # been mutated by a caller. Persist a detached validated definition.
        copy = ExperimentDefinition.model_validate(definition.model_dump())
        with closing(self._connect_write()) as db, db:
            try:
                db.execute("INSERT INTO experiments VALUES (?, ?)",
                           (copy.experiment_id, copy.model_dump_json()))
            except sqlite3.IntegrityError:
                raise ValueError("experiment already exists") from None
        return copy

    def _query(self, sql: str, params: tuple) -> list:
        if not self.path.exists():
            return []
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            return db.execute(sql, params).fetchall()

    def get_definition(self, experiment_id: str) -> ExperimentDefinition | None:
        rows = self._query("SELECT definition FROM experiments WHERE experiment_id=?", (experiment_id,))
        return ExperimentDefinition.model_validate_json(rows[0][0]) if rows else None

    def get_results(self, experiment_id: str, *, limit: int = 20) -> list[dict]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        rows = self._query(
            "SELECT result FROM experiment_runs WHERE experiment_id=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (experiment_id, limit),
        )
        return [json.loads(row[0]) for row in rows]

    def _save_result(self, result: dict) -> None:
        payload = json.dumps(result, allow_nan=False)
        with closing(self._connect_write()) as db, db:
            db.execute("INSERT INTO experiment_runs VALUES (?, ?, ?, ?)",
                       (result["run_id"], result["experiment_id"], payload, result["started_at"]))


class ExperimentRunner:
    """Synchronous, explicit stock-history factor execution; no trading/backtest.

    Reuses the same daily repository interface available to BacktestEngine.
    Snapshot diagnostics are supplementary and never reconstructed into OHLC.
    """

    def __init__(self, store: ExperimentStore, repository: DailyHistory,
                 archive: SnapshotArchive | None = None):
        self.store = store
        self.repository = repository
        self.archive = archive

    def execute(self, experiment_id: str) -> dict:
        definition = self.store.get_definition(experiment_id)
        if definition is None:
            raise KeyError("experiment not found")
        params = definition.parameters
        requests = tuple(FactorRequest(name.lower(), params.periods.get(name.lower()))
                         for name in definition.factors)
        started = datetime.now(UTC).isoformat()
        outputs = []
        for symbol in definition.symbols:
            entry = {"symbol": symbol, "status": "failed", "data": None,
                     "error": None, "latest_snapshot": None, "snapshot_status": "not_requested"}
            try:
                data = MarketFactorEngine().from_history(
                    self.repository, "stock", symbol, definition.date_range.start,
                    definition.date_range.end, requests, history_start=params.history_start,
                    price_basis=params.price_basis, mode=params.mode,
                    compatibility_backend=params.compatibility_backend,
                )
                entry.update(status="completed" if not data.frame.is_empty() else "empty", data=data.to_dict())
            except Exception:
                # Repository errors may include paths/credentials. Never store
                # raw exception strings, tracebacks or provider payloads.
                entry["error"] = "history_or_calculation_error"
            if self.archive is not None:
                try:
                    snapshots = self.archive.query(symbol=symbol, limit=1, latest=True)
                    entry.update(latest_snapshot=snapshots[0] if snapshots else None,
                                 snapshot_status="available" if snapshots else "empty")
                except Exception:
                    entry["snapshot_status"] = "unavailable"
            outputs.append(entry)
        states = {entry["status"] for entry in outputs}
        status = ("failed" if states == {"failed"} else "partial" if "failed" in states
                  else "empty" if states == {"empty"} else "completed")
        result = {
            "run_id": str(uuid4()), "experiment_id": experiment_id,
            "started_at": started, "finished_at": datetime.now(UTC).isoformat(),
            "status": status, "definition": definition.model_dump(mode="json"),
            "factor_metadata": [get_engine_factor(request.kind).to_dict() for request in requests],
            "symbols": outputs,
        }
        self.store._save_result(result)
        return result
