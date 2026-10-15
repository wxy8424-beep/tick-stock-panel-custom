"""Immutable, provider-neutral containers; no calculations, producer or startup hooks."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    field_validator,
    model_validator,
)

State = Literal["READY", "PARTIAL", "UNAVAILABLE", "BLOCKED"]
Label = Annotated[str, Field(min_length=1, pattern=r"^\S(?:.*\S)?$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
CONTRACT_BINDING_FIELDS = frozenset({"calculation_id", "calculation_content_hash", "score_profile_content_hash"})


def canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: dict) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


class MomentumIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    symbol: Label
    market: Literal["HK", "US"]
    trading_date: date
    input_contract_id: Label
    input_contract_version: Label
    calculation_version: Label
    # Additive exact bindings. Missing legacy fields never imply an exact contract.
    calculation_id: Label | None = None
    calculation_content_hash: Digest | None = None
    score_profile_content_hash: Digest | None = None
    calendar_id: Label
    calendar_version: Label
    calendar_content_hash: Digest
    universe_id: Label
    universe_version: Label
    universe_content_hash: Digest
    # Both null means NOT_SELECTED; no separate switch or implicit default profile.
    score_profile_id: Label | None
    score_profile_version: Label | None

    @model_validator(mode="after")
    def profile_pair(self):
        if (self.score_profile_id is None) != (self.score_profile_version is None):
            raise ValueError("score_profile_identity_incomplete")
        if (self.calculation_id is None) != (self.calculation_content_hash is None):
            raise ValueError("calculation_identity_incomplete")
        if self.calculation_id is not None:
            if (self.score_profile_id is None) != (self.score_profile_content_hash is None):
                raise ValueError("exact_score_profile_hash_required")
        elif self.score_profile_content_hash is not None:
            raise ValueError("exact_calculation_binding_required")
        for key in ("input_contract_id", "input_contract_version", "calculation_version",
                    "calendar_id", "calendar_version", "universe_id", "universe_version",
                    "score_profile_id", "score_profile_version", "calculation_id"):
            value = getattr(self, key)
            if value is not None and value.lower() in {"*", "latest", "current", "unknown", "blocked"}:
                raise ValueError("exact_identity_required")
        return self

    @property
    def logical_key(self) -> str:
        data = self.model_dump(mode="json")
        return digest({key: data[key] for key in MomentumIdentity.model_fields
                       if key not in CONTRACT_BINDING_FIELDS or data[key] is not None})

    @property
    def contract_binding_status(self) -> Literal["EXACT", "LEGACY_INCOMPLETE"]:
        return "EXACT" if self.calculation_id is not None else "LEGACY_INCOMPLETE"


class MetricEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    metric: Label
    status: State
    blockers: tuple[Label, ...] = ()
    warnings: tuple[Label, ...] = ()
    evidence_refs: tuple[Label, ...] = ()


class MomentumSnapshotRecord(MomentumIdentity):
    snapshot_version: Literal["momentum-snapshot-v1"] = "momentum-snapshot-v1"
    session_timestamp: AwareDatetime | None
    generated_at: AwareDatetime
    available_at: AwareDatetime | None
    knowledge_cutoff: AwareDatetime | None
    # Assigned once by the store; excluded from deterministic identity.
    stored_at: AwareDatetime | None = None
    source: Label | None
    provider: Label | None
    input_references: tuple[Label, ...]
    adjustment_method: Label | None
    price_basis: Label | None
    volume_unit: Label | None
    source_vintage: Label | None
    source_revision: Label | None
    pit_status: State
    overall_status: State
    blockers: tuple[Label, ...] = ()
    warnings: tuple[Label, ...] = ()
    metric_statuses: tuple[MetricEvidence, ...]
    close: FiniteFloat | None = None
    change_pct: FiniteFloat | None = None
    consecutive_up_days: Annotated[int, Field(strict=True, ge=0)] | None = None
    return_3d: FiniteFloat | None = None
    return_5d: FiniteFloat | None = None
    return_10d: FiniteFloat | None = None
    breakout_20: bool | None = None
    breakout_60: bool | None = None
    high_break_20: bool | None = None
    high_break_60: bool | None = None
    volatility_20: FiniteFloat | None = None
    volatility_status: State | None = None
    volume: FiniteFloat | None = None
    turnover: FiniteFloat | None = None
    volume_ratio_20: FiniteFloat | None = None
    strength_score: FiniteFloat | None = None
    rank: Annotated[int, Field(strict=True, ge=1)] | None = None
    tier: Label | None = None
    classifications: tuple[Label, ...] | None = None

    @field_validator("session_timestamp", "generated_at", "available_at", "knowledge_cutoff", "stored_at")
    @classmethod
    def utc_times(cls, value):
        return value.astimezone(UTC) if value is not None else None

    @model_validator(mode="after")
    def validate_envelope(self):
        if self.available_at is not None and self.available_at < self.generated_at:
            raise ValueError("snapshot_available_before_generation")
        for value in (self.session_timestamp, self.knowledge_cutoff):
            if value is not None and value > self.generated_at:
                raise ValueError("future_input_time")
        def known(value):
            return value is not None and value.upper() not in {"UNKNOWN", "BLOCKED", "UNVERIFIED"}

        if self.stored_at is not None and (
            self.stored_at < self.generated_at
            or (self.available_at is not None and self.stored_at < self.available_at)
        ):
            raise ValueError("stored_before_snapshot_available")
        if self.pit_status == "READY" and (
            self.available_at is None or self.knowledge_cutoff is None
            or not known(self.source_vintage) or not self.input_references
        ):
            raise ValueError("pit_evidence_incomplete")
        if self.overall_status == "READY" and (
            not known(self.price_basis) or self.pit_status != "READY"
        ):
            raise ValueError("ready_envelope_incomplete")
        price_metrics = {"close", "change_pct", "consecutive_up_days", "return_3d", "return_5d", "return_10d",
                         "breakout_20", "breakout_60", "high_break_20", "high_break_60", "volatility_20"}
        metrics = price_metrics | {"volume", "turnover", "volume_ratio_20", "strength_score", "rank", "tier", "classifications"}
        names = [item.metric for item in self.metric_statuses]
        if len(set(names)) != len(names) or not set(names) <= metrics:
            raise ValueError("invalid_metric_statuses")
        states = {item.metric: item for item in self.metric_statuses}
        for name in metrics:
            value = getattr(self, name)
            item = states.get(name)
            if value is not None and item is None:
                raise ValueError("metric_status_required")
            if item is not None and item.status == "READY":
                if value is None or not item.evidence_refs or item.blockers:
                    raise ValueError("ready_metric_evidence_incomplete")
                if name in price_metrics and not known(self.price_basis):
                    raise ValueError("metric_price_basis_unknown")
                if name in {"volume", "volume_ratio_20"} and not known(self.volume_unit):
                    raise ValueError("metric_volume_unit_unknown")
            if self.score_profile_id is None and name in {"strength_score", "rank", "tier"} and value is not None:
                raise ValueError("score_profile_not_selected")
        return self

    def canonical_payload(self) -> str:
        data = self.model_dump(mode="json", exclude={"stored_at"})
        # Preserve hashes of frozen v1 payloads that predate exact contract fields.
        for key in CONTRACT_BINDING_FIELDS:
            if data[key] is None:
                data.pop(key)
        # Status entries and reference sets are order independent.
        data["input_references"] = sorted(set(data["input_references"]))
        for key in ("blockers", "warnings"):
            data[key] = sorted(set(data[key]))
        for item in data["metric_statuses"]:
            for key in ("blockers", "warnings", "evidence_refs"):
                item[key] = sorted(set(item[key]))
        data["metric_statuses"].sort(key=lambda item: item["metric"])
        return canonical(data)

    @property
    def revision(self) -> str:
        return hashlib.sha256(self.canonical_payload().encode("utf-8")).hexdigest()

    @property
    def snapshot_id(self) -> str:
        return f"momentum-v1:{self.logical_key}:{self.revision}"

    def to_dict(self) -> dict:
        return self.model_dump(mode="json") | {
            "snapshot_id": self.snapshot_id, "logical_key": self.logical_key, "revision": self.revision,
            "contract_binding_status": self.contract_binding_status,
        }


class MomentumSnapshotStore:
    """Append-only side store. Exact queries return all matching revisions, never latest."""

    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "user_data" / "momentum_snapshots.sqlite3"

    def save(self, snapshot: MomentumSnapshotRecord) -> MomentumSnapshotRecord:
        snapshot = MomentumSnapshotRecord.model_validate_json(snapshot.model_dump_json())
        now = datetime.now(UTC)
        if snapshot.generated_at > now or (snapshot.available_at is not None and snapshot.available_at > now):
            raise ValueError("future_snapshot")
        payload = snapshot.canonical_payload()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            # Serialize the immutable check + insert, including first initialization.
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id TEXT PRIMARY KEY, logical_key TEXT NOT NULL, revision TEXT NOT NULL,
                generated_at REAL NOT NULL, available_at REAL, stored_at TEXT NOT NULL,
                stored_epoch REAL NOT NULL, payload TEXT NOT NULL,
                UNIQUE(logical_key, revision))""")
            db.execute("CREATE INDEX IF NOT EXISTS momentum_exact ON snapshots(logical_key, generated_at, available_at, stored_epoch)")
            found = db.execute("SELECT payload, stored_at FROM snapshots WHERE snapshot_id=?", (snapshot.snapshot_id,)).fetchone()
            if found:
                if found[0] != payload:
                    raise ValueError("immutable_snapshot_conflict")
                return self._decode(snapshot.snapshot_id, *found)
            db.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?)", (
                snapshot.snapshot_id, snapshot.logical_key, snapshot.revision,
                snapshot.generated_at.timestamp(),
                snapshot.available_at.timestamp() if snapshot.available_at is not None else None,
                now.isoformat(), now.timestamp(), payload))
        return self._decode(snapshot.snapshot_id, payload, now.isoformat())

    @staticmethod
    def _decode(snapshot_id: str, payload: str, stored_at: str) -> MomentumSnapshotRecord:
        record = MomentumSnapshotRecord.model_validate(json.loads(payload) | {"stored_at": stored_at})
        if record.snapshot_id != snapshot_id:
            raise ValueError("snapshot_identity_payload_conflict")
        return record

    def get_by_snapshot_id(self, snapshot_id: str) -> MomentumSnapshotRecord | None:
        if not self.path.exists():
            return None
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            row = db.execute("SELECT payload, stored_at FROM snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone()
        return self._decode(snapshot_id, *row) if row else None

    def query_exact(self, identity: MomentumIdentity, *, as_of: datetime | None = None) -> tuple[MomentumSnapshotRecord, ...]:
        identity = MomentumIdentity.model_validate(identity.model_dump())
        if as_of is not None and as_of.utcoffset() is None:
            raise ValueError("aware_as_of_required")
        if not self.path.exists():
            return ()
        sql = "SELECT snapshot_id, payload, stored_at FROM snapshots WHERE logical_key=?"
        args: list = [identity.logical_key]
        if as_of is not None:
            sql += " AND generated_at<=? AND available_at<=? AND stored_epoch<=?"
            args.extend([as_of.timestamp()] * 3)
        sql += " ORDER BY snapshot_id"
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            rows = db.execute(sql, args).fetchall()
        records = tuple(self._decode(*row) for row in rows)
        if any(record.logical_key != identity.logical_key or (
            as_of is not None and (
                record.generated_at > as_of or record.available_at is None
                or record.available_at > as_of or record.stored_at > as_of
            )
        ) for record in records):
            raise ValueError("snapshot_index_payload_conflict")
        return records
