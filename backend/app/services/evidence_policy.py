"""Explicit immutable policy definitions; no evidence reads or production wiring."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.market_session import market_from_symbol

EvidenceKind = Literal["historical", "market", "factors"]
EventKind = Literal["rapid_price_move", "intraday_breakout", "volatility_expansion"]


class PolicyModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FactorVersion(PolicyModel):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)


class EvidencePolicy(PolicyModel):
    policy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: Literal["ACTIVE", "INACTIVE"]
    effective_from: AwareDatetime
    effective_to: AwareDatetime | None
    market: Literal["CN", "HK", "US"]
    # Missing discriminator preserves the meaning of legacy finite lists.
    scope_type: Literal["SYMBOLS", "MARKET_WIDE"] = "SYMBOLS"
    symbol_scope: tuple[str, ...]
    event_types: tuple[EventKind, ...] = Field(min_length=1)
    event_time_source: Literal["window_end"]
    knowledge_cutoff_source: Literal["detected_at"]
    trading_calendar: str = Field(min_length=1)
    definition_id: str | None = Field(min_length=1)
    universe_id: str | None = Field(min_length=1)
    snapshot_date_rule: Literal["previous_completed_trading_day"]
    normalization_version: str | None = Field(min_length=1)
    required_factor_versions: tuple[FactorVersion, ...]
    allow_atr_display: bool = Field(strict=True)
    allow_move_atr_ratio: bool = Field(strict=True)
    require_price_scale_verified: bool = Field(strict=True)
    benchmark_required: bool = Field(strict=True)
    benchmark_selection_mode: Literal["existing_event_market_context_no_substitution"]
    required_evidence: tuple[EvidenceKind, ...]
    optional_evidence: tuple[EvidenceKind, ...]

    @property
    def factor_enabled(self) -> bool:
        return "factors" in self.required_evidence + self.optional_evidence

    @model_validator(mode="after")
    def validate_contract(self):
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("invalid_effective_period")
        if self.scope_type == "SYMBOLS" and not self.symbol_scope:
            raise ValueError("explicit_symbols_required")
        if self.scope_type == "MARKET_WIDE" and self.symbol_scope:
            raise ValueError("market_wide_symbols_must_be_empty")
        if any(market_from_symbol(symbol) != self.market for symbol in self.symbol_scope):
            raise ValueError("policy_symbol_market_conflict")
        factors = [item.name for item in self.required_factor_versions]
        for values in (self.symbol_scope, self.event_types, factors,
                       self.required_evidence + self.optional_evidence):
            if len(values) != len(set(values)):
                raise ValueError("duplicate_or_conflicting_scope")
        evidence = set(self.required_evidence + self.optional_evidence)
        if not evidence:
            raise ValueError("evidence_requirements_missing")
        if self.factor_enabled and (self.definition_id is None or self.universe_id is None
                                    or self.normalization_version is None or not self.required_factor_versions):
            raise ValueError("enabled_factor_metadata_required")
        if self.allow_move_atr_ratio and (not self.require_price_scale_verified or not self.allow_atr_display):
            raise ValueError("ratio_requires_verified_price_scale_and_atr")
        if (self.allow_atr_display or self.allow_move_atr_ratio) and "historical" not in evidence:
            raise ValueError("historical_requirement_missing")
        if self.benchmark_required and "market" not in self.required_evidence:
            raise ValueError("benchmark_requires_market_evidence")
        labels = (self.policy_id, self.version, self.trading_calendar, self.definition_id,
                  self.universe_id, self.normalization_version,
                  *(item.version for item in self.required_factor_versions))
        if any(value.strip().lower() in {"", "unknown", "latest", "default", "unverified", "*"}
               for value in labels if value is not None):
            raise ValueError("explicit_metadata_required")
        return self

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")


class EvidencePolicyStore:
    """Administrative append-only save; queries open SQLite in read-only mode."""

    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "user_data" / "evidence_policies.sqlite3"

    def save(self, policy: EvidencePolicy) -> None:
        policy = EvidencePolicy.model_validate_json(policy.model_dump_json())
        payload = policy.model_dump_json()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS policies (
                policy_id TEXT NOT NULL, version TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(policy_id,version))""")
            found = db.execute("SELECT payload FROM policies WHERE policy_id=? AND version=?",
                               (policy.policy_id, policy.version)).fetchone()
            if found:
                if EvidencePolicy.model_validate_json(found[0]) != policy:
                    raise ValueError("immutable_policy_version_conflict")
                return
            db.execute("INSERT INTO policies VALUES (?,?,?)", (policy.policy_id, policy.version, payload))

    def list_policies(self) -> tuple[EvidencePolicy, ...]:
        if not self.path.exists():
            return ()
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            rows = db.execute("SELECT payload FROM policies ORDER BY policy_id,version").fetchall()
        return tuple(EvidencePolicy.model_validate_json(row[0]) for row in rows)

    def get(self, policy_id: str, version: str) -> EvidencePolicy | None:
        return next((item for item in self.list_policies()
                     if item.policy_id == policy_id and item.version == version), None)


class PolicyEvent(PolicyModel):
    symbol: str = Field(min_length=1)
    market: Literal["CN", "HK", "US"]
    event_type: EventKind
    detected_at: AwareDatetime


class EvidencePolicyResolver:
    def __init__(self, store: EvidencePolicyStore):
        self.store = store

    def resolve(self, event: dict) -> dict:
        try:
            # Read only the declared matching fields; leave the original event untouched.
            identity = PolicyEvent.model_validate({key: event[key] for key in PolicyEvent.model_fields})
            if market_from_symbol(identity.symbol) != identity.market:
                return {"status": "BLOCKED", "blocker": "event_market_conflict"}
        except (KeyError, TypeError, ValueError):
            return {"status": "BLOCKED", "blocker": "event_identity_or_time_invalid"}
        try:
            matches = [item for item in self.store.list_policies()
                       if item.status == "ACTIVE" and item.market == identity.market
                       and (item.scope_type == "MARKET_WIDE" or identity.symbol in item.symbol_scope)
                       and identity.event_type in item.event_types
                       and item.effective_from <= identity.detected_at
                       and (item.effective_to is None or identity.detected_at < item.effective_to)]
        except (sqlite3.Error, OSError, ValueError):
            return {"status": "BLOCKED", "blocker": "policy_store_unavailable_or_invalid"}
        if not matches:
            return {"status": "BLOCKED", "blocker": "no_matching_policy"}
        if len(matches) != 1:
            return {"status": "BLOCKED", "blocker": "multiple_matching_policies"}
        policy = matches[0]
        return {"status": "READY", "blocker": None, "policy_id": policy.policy_id,
                "version": policy.version, "selection_rules": policy.to_dict()}
