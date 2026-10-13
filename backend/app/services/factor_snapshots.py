"""Freeze existing research scores. No factor calculations or consumer integration."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from app.market_session import get_market_session, market_from_symbol
from app.services.research_portfolios import ScoreInput

SNAPSHOT_VERSION = "factor-snapshot-v1"


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FactorValue(FrozenModel):
    name: str
    value: FiniteFloat | None
    score: FiniteFloat | None = Field(ge=0, le=1)


class Normalization(FrozenModel):
    factor: str
    method: Literal["rank", "normalization"]
    version: str = Field(min_length=1)
    direction: Literal["high", "low"]
    valid_count: int = Field(ge=1)
    min_value: FiniteFloat
    max_value: FiniteFloat


class FactorSnapshot(FrozenModel):
    snapshot_id: str
    run_id: str = Field(min_length=1)
    definition_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    market: Literal["CN", "HK", "US"]
    as_of_date: date
    generated_at: AwareDatetime
    available_at: AwareDatetime
    timezone: str
    factor_registry_version: str = Field(min_length=1)
    engine_version: str = Field(min_length=1)
    snapshot_version: Literal["factor-snapshot-v1"] = SNAPSHOT_VERSION
    universe_id: str = Field(min_length=1)
    universe_hash: str
    universe_size: int = Field(ge=1, le=100)
    universe_members: tuple[str, ...]
    normalization: tuple[Normalization, ...]
    factor_values: tuple[FactorValue, ...]
    total_score: FiniteFloat | None = Field(ge=0, le=1)
    status: Literal["READY", "UNAVAILABLE", "BLOCKED"]
    blocker: str | None
    source: str = Field(min_length=1)
    input_reference: str = Field(min_length=1)
    adjustment_method: str = Field(min_length=1)
    input_latest_date: date
    input_available_at: AwareDatetime
    availability_evidence: str = Field(min_length=1)
    source_vintage: str = Field(min_length=1)
    calculation_metadata_json: str

    @model_validator(mode="after")
    def validate_evidence(self):
        labels = (self.source, self.input_reference, self.source_vintage, self.availability_evidence,
                  self.adjustment_method, self.engine_version, self.factor_registry_version)
        if any(value.strip().lower() in {"", "unknown", "unverified", "latest", "unsupported"} for value in labels):
            raise ValueError("evidence_metadata_unverified")
        if market_from_symbol(self.symbol) != self.market:
            raise ValueError("snapshot_market_conflict")
        zone = get_market_session(self.market, self.generated_at).timezone.key
        if self.timezone != zone or self.available_at < self.generated_at:
            raise ValueError("snapshot_time_conflict")
        if self.input_available_at > self.generated_at or self.input_latest_date > self.as_of_date:
            raise ValueError("future_input")
        if self.as_of_date >= self.generated_at.astimezone(ZoneInfo(zone)).date():
            raise ValueError("daily_input_not_prior_completed_day")
        members = tuple(sorted(self.universe_members))
        digest = hashlib.sha256(json.dumps(members, separators=(",", ":")).encode()).hexdigest()
        if (len(set(members)) != len(members) or self.universe_size != len(members)
                or self.symbol not in members or self.universe_hash != digest):
            raise ValueError("universe_conflict")
        columns = [item.name for item in self.factor_values]
        if not columns or len(set(columns)) != len(columns) or set(columns) != {item.factor for item in self.normalization}:
            raise ValueError("factor_metadata_conflict")
        metadata = json.loads(self.calculation_metadata_json)
        if not isinstance(metadata, dict) or not metadata.get("factors") or not metadata.get("universe_evidence"):
            raise ValueError("calculation_metadata_missing")
        if any(item.valid_count > self.universe_size or item.min_value > item.max_value for item in self.normalization):
            raise ValueError("normalization_evidence_conflict")
        complete = self.total_score is not None and all(item.value is not None and item.score is not None for item in self.factor_values)
        if (self.status == "READY") != complete or (self.status == "READY") != (self.blocker is None):
            raise ValueError("snapshot_status_conflict")
        if complete and not math.isclose(self.total_score,
                math.fsum(item.score for item in self.factor_values) / len(self.factor_values), abs_tol=1e-12, rel_tol=1e-12):
            raise ValueError("snapshot_score_conflict")
        return self

    def to_dict(self) -> dict:
        result = self.model_dump(mode="json")
        result["calculation_metadata"] = json.loads(result.pop("calculation_metadata_json"))
        result["factor_scores"] = {item.name: item.score for item in self.factor_values}
        return result


class FactorSnapshotBuilder:
    """Caller supplies verified provenance and calculation-time versions, never latest metadata.

    Missing metadata yields BLOCKED, with no fabricated snapshot. Generation and
    availability begin now; old research runs cannot become backdated evidence.
    """

    def build(self, result: dict, registry_metadata: dict, universe_metadata: dict,
              *, symbol: str, run_id: str, definition_id: str, provenance: dict) -> dict:
        try:
            required = ("engine_version", "factor_registry_version", "normalization_version", "factors")
            if any(not registry_metadata.get(key) for key in required):
                return {"status": "BLOCKED", "blocker": "version_metadata_missing", "snapshot": None}
            if any(str(registry_metadata[key]).strip().lower() in {"unknown", "unverified", "latest", ""}
                   for key in required[:3]):
                return {"status": "BLOCKED", "blocker": "version_metadata_unverified", "snapshot": None}
            if provenance.get("pit_status") != "verified":
                return {"status": "BLOCKED", "blocker": "input_availability_unverified", "snapshot": None}
            scores = ScoreInput.model_validate(result)
            members = tuple(sorted(universe_metadata["members"]))
            universe_date = date.fromisoformat(str(universe_metadata["as_of_date"]))
            universe_available = datetime.fromisoformat(str(universe_metadata["available_at"]))
            now = datetime.now(UTC)
            if (universe_date != scores.as_of or universe_available.tzinfo is None
                    or universe_available > now or not universe_metadata.get("evidence_reference")):
                return {"status": "BLOCKED", "blocker": "universe_availability_unverified", "snapshot": None}
            if set(members) != {row.symbol for row in scores.rows}:
                return {"status": "BLOCKED", "blocker": "score_universe_conflict", "snapshot": None}
            original = {item["output_column"]: item for item in result["factors"]}
            supplied = {item["output_column"]: item for item in registry_metadata["factors"]}
            if set(original) != set(supplied) or any(
                item.get("registry") != supplied[column].get("registry")
                or not isinstance(supplied[column].get("registry", {}).get("version"), int)
                or supplied[column]["registry"]["version"] < 1 for column, item in original.items()
            ):
                return {"status": "BLOCKED", "blocker": "factor_version_conflict", "snapshot": None}
            row = next((item for item in scores.rows if item.symbol == symbol), None)
            if row is None:
                return {"status": "UNAVAILABLE", "blocker": "symbol_result_missing", "snapshot": None}
            normalizations = tuple(Normalization(
                factor=item.output_column, method=scores.method,
                version=registry_metadata["normalization_version"], direction=item.direction,
                valid_count=original[item.output_column]["valid_count"],
                min_value=original[item.output_column]["minimum"], max_value=original[item.output_column]["maximum"],
            ) for item in scores.factors)
            market = market_from_symbol(symbol)
            snapshot = FactorSnapshot(
                snapshot_id=str(uuid4()), run_id=run_id, definition_id=definition_id,
                symbol=symbol, market=market, as_of_date=scores.as_of,
                generated_at=now, available_at=now, timezone=get_market_session(market, now).timezone.key,
                factor_registry_version=registry_metadata["factor_registry_version"],
                engine_version=registry_metadata["engine_version"], universe_id=universe_metadata["universe_id"],
                universe_members=members, universe_size=len(members),
                universe_hash=hashlib.sha256(json.dumps(members, separators=(",", ":")).encode()).hexdigest(),
                normalization=normalizations, factor_values=tuple(FactorValue(name=key, value=value.value, score=value.score)
                    for key, value in row.factors.items()), total_score=row.total_score,
                status="READY" if row.status == "scored" else "UNAVAILABLE",
                blocker=None if row.status == "scored" else "factor_values_unavailable",
                source=provenance["source"], input_reference=provenance["input_reference"],
                adjustment_method=provenance["adjustment_method"], input_latest_date=provenance["input_latest_date"],
                input_available_at=provenance["input_available_at"], availability_evidence=provenance["availability_evidence"],
                source_vintage=provenance["source_vintage"], calculation_metadata_json=json.dumps({
                    "mode": scores.mode, "compatibility_backend": scores.compatibility_backend,
                    "price_basis": scores.price_basis, "history_start": scores.history_start.isoformat(),
                    "aggregation": scores.aggregation, "factors": result["factors"],
                    "universe_evidence": {"as_of_date": universe_date.isoformat(),
                        "available_at": universe_available.isoformat(), "reference": universe_metadata["evidence_reference"]},
                    "score_cohort": [item.model_dump(mode="json") for item in scores.rows],
                }, allow_nan=False, sort_keys=True),
            )
            return {"status": snapshot.status, "blocker": snapshot.blocker, "snapshot": snapshot}
        except Exception:
            return {"status": "BLOCKED", "blocker": "snapshot_metadata_or_evidence_invalid", "snapshot": None}


class FactorSnapshotStore:
    """Append-only evidence. GET opens mode=ro; originals and research databases untouched."""

    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "user_data" / "factor_snapshots.sqlite3"

    def save(self, snapshot: FactorSnapshot) -> None:
        snapshot = FactorSnapshot.model_validate_json(snapshot.model_dump_json())
        now = datetime.now(UTC)
        if snapshot.generated_at > now or snapshot.available_at > now:
            raise ValueError("future_snapshot")
        payload = snapshot.model_dump_json()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, snapshot_date TEXT NOT NULL,
                definition_id TEXT NOT NULL, available_at REAL NOT NULL, generated_at REAL NOT NULL,
                stored_at REAL NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS snapshot_lookup ON snapshots(symbol,definition_id,snapshot_date,available_at)")
            found = db.execute("SELECT payload FROM snapshots WHERE snapshot_id=?", (snapshot.snapshot_id,)).fetchone()
            if found:
                if found[0] != payload:
                    raise ValueError("immutable_snapshot_conflict")
                return
            db.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?)", (
                snapshot.snapshot_id, snapshot.symbol, snapshot.as_of_date.isoformat(), snapshot.definition_id,
                snapshot.available_at.timestamp(), snapshot.generated_at.timestamp(), now.timestamp(), snapshot.status, payload))

    def query(self, symbol: str, *, snapshot_date: date, definition_id: str, as_of_time: datetime) -> dict:
        if as_of_time.tzinfo is None or as_of_time.utcoffset() is None:
            raise ValueError("aware_as_of_time_required")
        if not self.path.exists():
            return {"status": "UNAVAILABLE", "blocker": "snapshot_not_available_at_requested_time"}
        cutoff = as_of_time.timestamp()
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            found = db.execute("""SELECT payload FROM snapshots WHERE symbol=? AND snapshot_date=?
                AND definition_id=? AND status='READY' AND available_at<=? AND generated_at<=? AND stored_at<=?
                ORDER BY available_at DESC, stored_at DESC, snapshot_id DESC LIMIT 1""",
                (symbol, snapshot_date.isoformat(), definition_id, cutoff, cutoff, cutoff)).fetchone()
        if not found:
            return {"status": "UNAVAILABLE", "blocker": "snapshot_not_available_at_requested_time"}
        snapshot = FactorSnapshot.model_validate_json(found[0])
        if (snapshot.symbol != symbol or snapshot.as_of_date != snapshot_date
                or snapshot.definition_id != definition_id or snapshot.status != "READY"
                or snapshot.generated_at > as_of_time or snapshot.available_at > as_of_time):
            return {"status": "UNAVAILABLE", "blocker": "snapshot_index_payload_conflict"}
        return {"status": "READY", "snapshot": snapshot.to_dict(),
                "factors": [item.model_dump(mode="json") for item in snapshot.factor_values],
                "scores": {"factor_scores": {item.name: item.score for item in snapshot.factor_values}, "total_score": snapshot.total_score},
                "provenance": {"source": snapshot.source, "input_reference": snapshot.input_reference,
                               "adjustment_method": snapshot.adjustment_method, "availability_evidence": snapshot.availability_evidence}}
