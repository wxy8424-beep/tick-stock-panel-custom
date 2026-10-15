"""Provider-neutral frozen membership contracts; no directory loader or producer."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.market_session import market_from_symbol
from app.services.momentum_snapshots import Digest, Label, State, canonical, digest

InstrumentType = Literal[
    "COMMON_STOCK", "ADR", "ETF", "REIT", "PREFERRED", "WARRANT", "RIGHTS", "BOND", "FUND", "OTHER", "UNKNOWN",
]
Count = Annotated[int, Field(strict=True, ge=0)]


class MomentumUniverseIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    universe_id: Label
    universe_version: Label
    content_hash: Digest
    market: Literal["HK", "US"]

    @field_validator("universe_id", "universe_version")
    @classmethod
    def exact_label(cls, value):
        if value.lower() in {"*", "latest", "current", "unknown", "blocked"}:
            raise ValueError("exact_universe_identity_required")
        return value


class MomentumUniverseMember(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    symbol: Label
    market: Literal["HK", "US"]
    instrument_type: InstrumentType
    membership_status: Literal["INCLUDED", "EXCLUDED", "UNRESOLVED"]
    effective_from: AwareDatetime
    effective_to: AwareDatetime | None
    evidence_reference: Label | None
    reason: Label | None

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value):
        # No suffix, class-share, HK padding or provider alias inference.
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("effective_from", "effective_to")
    @classmethod
    def utc_times(cls, value):
        return value.astimezone(UTC) if value is not None else None

    @model_validator(mode="after")
    def validate_member(self):
        if market_from_symbol(self.symbol) != self.market:
            raise ValueError("member_symbol_market_conflict")
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("member_effective_period_invalid")
        if self.membership_status != "INCLUDED" and self.reason is None:
            raise ValueError("membership_decision_reason_required")
        return self


class ExclusionRules(BaseModel):
    """Explicit exclusions only; no expression language or implicit provider eligibility."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    symbols: tuple[Label, ...] = ()
    instrument_types: tuple[InstrumentType, ...] = ()

    @field_validator("symbols", mode="before")
    @classmethod
    def normalized_symbols(cls, value):
        if isinstance(value, (tuple, list)):
            return tuple(MomentumUniverseMember.normalize_symbol(symbol) for symbol in value)
        return value


class MomentumUniverseDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    contract_version: Literal["momentum-universe-v1"] = "momentum-universe-v1"
    universe_id: Label
    universe_version: Label
    market: Literal["HK", "US"]
    universe_type: Literal["MARKET_WIDE", "CUSTOM", "WATCHLIST", "INDEX_CONSTITUENTS"]
    effective_from: AwareDatetime
    effective_to: AwareDatetime | None
    generated_at: AwareDatetime
    available_at: AwareDatetime | None
    stored_at: AwareDatetime | None = None
    source: Label | None
    source_kind: Literal["DIRECTORY", "CUSTOM", "WATCHLIST", "DYNAMIC_CANDIDATES", "DISPLAY_SET", "INDEX_CONSTITUENTS"]
    source_version: Label | None
    source_references: tuple[Label, ...]
    membership_vintage: Label | None
    availability_evidence: Label | None
    allowed_instrument_types: tuple[InstrumentType, ...]
    exclusion_rules: ExclusionRules
    members: tuple[MomentumUniverseMember, ...]
    expected_count: Count | None
    effective_count: Count
    missing_count: Count | None
    excluded_count: Count
    coverage_evidence: Label | None
    pit_status: State
    status: State
    blockers: tuple[Label, ...] = ()
    warnings: tuple[Label, ...] = ()

    @field_validator("universe_id", "universe_version")
    @classmethod
    def exact_label(cls, value):
        return MomentumUniverseIdentity.exact_label(value)

    @field_validator("effective_from", "effective_to", "generated_at", "available_at", "stored_at")
    @classmethod
    def utc_times(cls, value):
        return value.astimezone(UTC) if value is not None else None

    @model_validator(mode="after")
    def validate_membership(self):
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("universe_effective_period_invalid")
        if self.available_at is not None and self.available_at < self.generated_at:
            raise ValueError("universe_available_before_generation")
        if self.stored_at is not None and (
            self.stored_at < self.generated_at
            or (self.available_at is not None and self.stored_at < self.available_at)
        ):
            raise ValueError("universe_stored_before_availability")
        if self.universe_type == "MARKET_WIDE" and self.source_kind != "DIRECTORY":
            raise ValueError("market_wide_requires_directory")
        if self.universe_type in {"WATCHLIST", "INDEX_CONSTITUENTS"} and self.source_kind != self.universe_type:
            raise ValueError("universe_source_scope_conflict")
        if not self.allowed_instrument_types or len(set(self.allowed_instrument_types)) != len(self.allowed_instrument_types):
            raise ValueError("allowed_instrument_types_required_unique")
        symbols = [member.symbol for member in self.members]
        if len(symbols) != len(set(symbols)):
            raise ValueError("duplicate_member")
        if any(member.market != self.market for member in self.members):
            raise ValueError("member_market_conflict")
        if any(market_from_symbol(symbol) != self.market for symbol in self.exclusion_rules.symbols):
            raise ValueError("excluded_symbol_market_conflict")
        # A frozen membership is stable throughout its declared effective interval.
        # Membership changes require another explicit version/interval, not an implicit daily filter.
        if any(member.effective_from > self.effective_from or (
            member.effective_to is not None and (
                self.effective_to is None or member.effective_to < self.effective_to
            )
        ) for member in self.members):
            raise ValueError("member_effective_period_incomplete")
        for member in self.members:
            if member.membership_status == "INCLUDED" and (
                member.instrument_type == "UNKNOWN"
                or member.instrument_type not in self.allowed_instrument_types
                or member.instrument_type in self.exclusion_rules.instrument_types
                or member.symbol in self.exclusion_rules.symbols
            ):
                raise ValueError("ineligible_member")
        included = sum(member.membership_status == "INCLUDED" for member in self.members)
        excluded = sum(member.membership_status == "EXCLUDED" for member in self.members)
        if included != self.effective_count or excluded != self.excluded_count:
            raise ValueError("coverage_count_conflict")
        if self.expected_count is None:
            if self.missing_count is not None or "expected_count_unknown" not in self.warnings or self.status == "READY":
                raise ValueError("expected_count_unknown")
        elif self.missing_count is None or self.expected_count != len(self.members) + self.missing_count:
            raise ValueError("coverage_count_conflict")
        def known(value):
            return value is not None and value.lower() not in {"unknown", "blocked", "unverified", "latest", "current", "*"}

        missing_evidence = any(not known(member.evidence_reference) for member in self.members)
        if missing_evidence and (self.status == "READY" or "membership_evidence_missing" not in self.blockers):
            raise ValueError("membership_evidence_missing")
        if self.pit_status == "READY" and (
            self.available_at is None or not known(self.membership_vintage)
            or not known(self.availability_evidence) or not self.source_references
            or not all(known(ref) for ref in self.source_references)
        ):
            raise ValueError("pit_evidence_incomplete")
        if self.status == "READY" and (
            self.pit_status != "READY" or not known(self.source) or not known(self.source_version)
            or not known(self.coverage_evidence) or not self.effective_count
            or self.missing_count != 0 or self.unresolved_count or self.blockers
        ):
            raise ValueError("ready_universe_evidence_incomplete")
        return self

    @property
    def unresolved_count(self) -> int:
        return sum(member.membership_status == "UNRESOLVED" for member in self.members)

    def canonical_payload(self) -> str:
        data = self.model_dump(mode="json", exclude={"stored_at"})
        for key in ("source_references", "allowed_instrument_types", "blockers", "warnings"):
            data[key] = sorted(set(data[key]))
        for key in ("symbols", "instrument_types"):
            data["exclusion_rules"][key] = sorted(set(data["exclusion_rules"][key]))
        data["members"].sort(key=lambda member: member["symbol"])
        return canonical(data)

    @property
    def content_hash(self) -> str:
        return digest(json.loads(self.canonical_payload()))

    @property
    def identity(self) -> MomentumUniverseIdentity:
        return MomentumUniverseIdentity(universe_id=self.universe_id, universe_version=self.universe_version,
                                        content_hash=self.content_hash, market=self.market)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json") | {"content_hash": self.content_hash, "unresolved_count": self.unresolved_count}


class MomentumUniverseStore:
    """Exact, append-only artifacts. No startup initialization, latest or directory fallback."""

    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "user_data" / "momentum_universes.sqlite3"

    def save(self, universe: MomentumUniverseDefinition) -> MomentumUniverseDefinition:
        universe = MomentumUniverseDefinition.model_validate_json(universe.model_dump_json())
        now = datetime.now(UTC)
        if universe.generated_at > now or (universe.available_at is not None and universe.available_at > now):
            raise ValueError("future_universe")
        payload = universe.canonical_payload()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE IF NOT EXISTS universes (
                universe_id TEXT NOT NULL, version TEXT NOT NULL, content_hash TEXT NOT NULL,
                market TEXT NOT NULL, universe_type TEXT NOT NULL, payload TEXT NOT NULL,
                stored_at TEXT NOT NULL, PRIMARY KEY(universe_id, version))""")
            db.execute("CREATE INDEX IF NOT EXISTS momentum_universe_exact ON universes(universe_id, version, content_hash, market)")
            scope = db.execute("SELECT market, universe_type FROM universes WHERE universe_id=? LIMIT 1", (universe.universe_id,)).fetchone()
            if scope and scope != (universe.market, universe.universe_type):
                raise ValueError("universe_scope_conflict")
            found = db.execute("SELECT content_hash, payload, stored_at FROM universes WHERE universe_id=? AND version=?",
                               (universe.universe_id, universe.universe_version)).fetchone()
            if found:
                if found[0] != universe.content_hash or found[1] != payload:
                    raise ValueError("immutable_universe_conflict")
                return self._decode(universe.identity, found[1], found[2])
            db.execute("INSERT INTO universes VALUES (?,?,?,?,?,?,?)", (
                universe.universe_id, universe.universe_version, universe.content_hash, universe.market,
                universe.universe_type, payload, now.isoformat()))
        return self._decode(universe.identity, payload, now.isoformat())

    @staticmethod
    def _decode(identity: MomentumUniverseIdentity, payload: str, stored_at: str) -> MomentumUniverseDefinition:
        record = MomentumUniverseDefinition.model_validate(json.loads(payload) | {"stored_at": stored_at})
        if record.identity != identity:
            raise ValueError("universe_payload_identity_conflict")
        return record

    def get_by_identity(self, identity: MomentumUniverseIdentity) -> MomentumUniverseDefinition | None:
        identity = MomentumUniverseIdentity.model_validate(identity.model_dump())
        if not self.path.exists():
            return None
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            row = db.execute("""SELECT payload, stored_at FROM universes
                WHERE universe_id=? AND version=? AND content_hash=? AND market=?""",
                (identity.universe_id, identity.universe_version, identity.content_hash, identity.market)).fetchone()
        return self._decode(identity, *row) if row else None

    def query_exact(self, identity: MomentumUniverseIdentity, *, effective_at: datetime, as_of: datetime) -> dict:
        """Resolve exact membership for an effective instant and a separate knowledge cutoff."""
        if effective_at.utcoffset() is None or as_of.utcoffset() is None:
            raise ValueError("aware_query_time_required")
        record = self.get_by_identity(identity)
        if record is None:
            return {"status": "UNAVAILABLE", "blocker": "universe_exact_identity_missing", "universe": None}
        if (effective_at < record.effective_from
            or (record.effective_to is not None and effective_at >= record.effective_to)
            or record.generated_at > as_of or record.stored_at > as_of
            or (record.available_at is not None and record.available_at > as_of)):
            return {"status": "UNAVAILABLE", "blocker": "universe_not_effective_or_known_at_requested_time", "universe": None}
        if record.available_at is None or record.pit_status != "READY":
            return {"status": "BLOCKED", "blocker": "universe_historical_availability_unverified", "universe": None}
        return {"status": record.status, "blocker": record.blockers[0] if record.blockers else None, "universe": record}
