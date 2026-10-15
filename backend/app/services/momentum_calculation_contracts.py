"""Momentum-only definition metadata. No expressions are evaluated or inputs fetched."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.momentum_snapshots import Digest, Label, canonical, digest
from app.services.momentum_universes import MomentumUniverseIdentity

MetricKey = Literal[
    "change_pct", "consecutive_up_days", "return_3d", "return_5d", "return_10d",
    "breakout_20", "breakout_60", "high_break_20", "high_break_60",
    "volatility_20", "volatility_status", "volume_ratio_20",
]
COMPARISON_KEYS = (
    "market", "trading_date", "universe_id", "universe_version", "universe_content_hash",
    "input_contract_id", "input_contract_version", "calculation_id", "calculation_version",
    "calculation_content_hash", "score_profile_id", "score_profile_version", "score_profile_content_hash",
)


def exact_label(value: str) -> str:
    if value.lower() in {"latest", "current", "*", "unknown", "blocked", "default"}:
        raise ValueError("exact_contract_identity_required")
    return value


class MissingInputContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    result_value: None = None
    missing_status: Literal["UNAVAILABLE", "BLOCKED"]
    missing_reason: Label
    invalid_contract_status: Literal["BLOCKED"] = "BLOCKED"
    invalid_contract_reason: Label
    partial_input_status: Literal["PARTIAL"] = "PARTIAL"
    fill_zero: Literal[False] = False
    forward_fill: Literal[False] = False
    backward_fill: Literal[False] = False
    skip_sessions: Literal[False] = False
    switch_provider: Literal[False] = False
    switch_adjustment: Literal[False] = False
    shorten_lookback: Literal[False] = False


class MomentumMetricDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    metric_key: MetricKey
    metric_version: Label
    formula_semantics: Label
    required_inputs: tuple[Label, ...] = Field(min_length=1)
    required_history_sessions: Annotated[int, Field(strict=True, ge=1)] | None
    history_rule: Label
    price_basis_requirement: Literal["SPLIT_ADJUSTED_PRICE_ONLY", "NOT_REQUIRED"]
    volume_semantics_requirement: Literal["COMPARABLE_CORPORATE_ACTION_QUANTITY", "NOT_REQUIRED"]
    calendar_requirement: Literal["EXACT_IMMUTABLE_SESSION_SEQUENCE"]
    finality_requirement: Literal["COMPLETED_FINAL_DAILY_SESSIONS"]
    pit_requirement: Literal["INPUT_KNOWN_BY_KNOWLEDGE_CUTOFF"]
    output_type: Literal["FRACTION", "COUNT", "BOOLEAN", "NON_ANNUALIZED_LOG_STD", "QUALITY_STATUS", "RATIO"]
    nullable: Literal[True] = True
    missing_input: MissingInputContract
    definition_blockers: tuple[Label, ...] = ()

    @field_validator("metric_version")
    @classmethod
    def exact(cls, value):
        return exact_label(value)

    @property
    def definition_status(self) -> str:
        return "BLOCKED" if self.definition_blockers else "DEFINED"

    @property
    def content_hash(self) -> str:
        data = self.model_dump(mode="json")
        data["required_inputs"] = sorted(set(data["required_inputs"]))
        data["definition_blockers"] = sorted(set(data["definition_blockers"]))
        return digest(data)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json") | {"content_hash": self.content_hash, "definition_status": self.definition_status}


class CalculationIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    calculation_id: Label
    calculation_version: Label
    content_hash: Digest

    @field_validator("calculation_id", "calculation_version")
    @classmethod
    def exact(cls, value):
        return exact_label(value)


class MetricReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    metric_key: MetricKey
    metric_version: Label
    content_hash: Digest

    @field_validator("metric_version")
    @classmethod
    def exact(cls, value):
        return exact_label(value)


class MomentumCalculationDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    contract_version: Literal["momentum-calculation-contract-v1"] = "momentum-calculation-contract-v1"
    calculation_id: Label
    calculation_version: Label
    metrics: tuple[MomentumMetricDefinition, ...] = Field(min_length=1)
    execution_eligibility: Literal["BLOCKED"] = "BLOCKED"
    execution_blockers: tuple[Label, ...] = Field(min_length=1)

    @field_validator("calculation_id", "calculation_version")
    @classmethod
    def exact(cls, value):
        return exact_label(value)

    @model_validator(mode="after")
    def validate_definition(self):
        keys = [metric.metric_key for metric in self.metrics]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate_metric_definition")
        return self

    def canonical_payload(self) -> str:
        data = self.model_dump(mode="json")
        data["execution_blockers"] = sorted(set(data["execution_blockers"]))
        for metric in data["metrics"]:
            for key in ("required_inputs", "definition_blockers"):
                metric[key] = sorted(set(metric[key]))
        data["metrics"].sort(key=lambda metric: metric["metric_key"])
        return canonical(data)

    @property
    def content_hash(self) -> str:
        return digest(json.loads(self.canonical_payload()))

    @property
    def identity(self) -> CalculationIdentity:
        return CalculationIdentity(calculation_id=self.calculation_id, calculation_version=self.calculation_version,
                                   content_hash=self.content_hash)

    @property
    def definition_status(self) -> str:
        return "DEFINED" if all(metric.definition_status == "DEFINED" for metric in self.metrics) else "BLOCKED"

    def to_dict(self) -> dict:
        return self.model_dump(mode="json") | {"content_hash": self.content_hash, "definition_status": self.definition_status,
                                               "metrics": [metric.to_dict() for metric in self.metrics]}


class NormalizationContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: Label
    method: Literal["SAME_UNIVERSE_PERCENTILE"] = "SAME_UNIVERSE_PERCENTILE"
    ties: Literal["AVERAGE_ORDINAL_MID_RANK"] = "AVERAGE_ORDINAL_MID_RANK"
    formula_semantics: Label | None
    singleton_policy: Literal["NEUTRAL_0_5", "BLOCKED"] | None
    incomplete_universe: Literal["BLOCKED", "PARTIAL_WITH_COVERAGE_WARNING"]


class ScoreComponent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    component_key: Label
    weight_bps: Annotated[int, Field(strict=True, ge=1, le=10000)]
    metrics: tuple[MetricReference, ...]
    aggregation: Literal["IDENTITY", "MEAN_OF_PERCENTILES"] | None
    direction: Literal["HIGH", "LOW"] | None
    eligibility_requirement: Literal["ALL_REFERENCED_METRICS_READY"] = "ALL_REFERENCED_METRICS_READY"
    definition_blockers: tuple[Label, ...]


class TierContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    eligibility: Literal["change_pct > 0 AND return_5d > 0"] = "change_pct > 0 AND return_5d > 0"
    t1_bps: Annotated[int, Field(strict=True, ge=1, le=10000)]
    t2_bps: Annotated[int, Field(strict=True, ge=1, le=10000)]
    boundary_formula: Literal["ceil(valid_candidate_count * threshold_bps / 10000)"] = "ceil(valid_candidate_count * threshold_bps / 10000)"
    remaining_eligible: Literal["T3"] = "T3"
    same_score_same_tier: Literal[True] = True

    @model_validator(mode="after")
    def ordered(self):
        if self.t1_bps >= self.t2_bps:
            raise ValueError("tier_thresholds_not_ordered")
        return self


class RankingContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    exact_comparison_keys: tuple[Label, ...]
    score_order: Literal["DESCENDING"] = "DESCENDING"
    rank_method: Literal["COMPETITION", "DENSE"] | None
    symbol_tiebreak: Literal["DISPLAY_ONLY_NEVER_SCORE_OR_RANK"] = "DISPLAY_ONLY_NEVER_SCORE_OR_RANK"

    @model_validator(mode="after")
    def exact_dimensions(self):
        if len(set(self.exact_comparison_keys)) != len(self.exact_comparison_keys) or set(self.exact_comparison_keys) != set(COMPARISON_KEYS):
            raise ValueError("exact_ranking_dimensions_required")
        return self


class ScoreProfileIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    score_profile_id: Label
    score_profile_version: Label
    content_hash: Digest

    @field_validator("score_profile_id", "score_profile_version")
    @classmethod
    def exact(cls, value):
        return exact_label(value)


class MomentumRankingCohort(BaseModel):
    """Future comparison identity only; no candidate selection, percentile or ranking."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    market: Literal["HK", "US"]
    trading_date: date
    universe: MomentumUniverseIdentity
    input_contract_id: Label
    input_contract_version: Label
    calculation: CalculationIdentity
    score_profile: ScoreProfileIdentity

    @field_validator("input_contract_id", "input_contract_version")
    @classmethod
    def exact(cls, value):
        return exact_label(value)

    @model_validator(mode="after")
    def market_binding(self):
        if self.market != self.universe.market:
            raise ValueError("ranking_universe_market_conflict")
        return self


class MomentumScoreProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    contract_version: Literal["momentum-score-profile-v1"] = "momentum-score-profile-v1"
    score_profile_id: Label
    score_profile_version: Label
    calculation: CalculationIdentity
    components: tuple[ScoreComponent, ...] = Field(min_length=1)
    normalization: NormalizationContract
    required_metrics: tuple[MetricReference, ...]
    optional_metrics: tuple[MetricReference, ...]
    missing_required_score: None = None
    missing_required_status: Literal["UNAVAILABLE", "BLOCKED"]
    missing_required_reason: Label
    redistribute_weights: Literal[False] = False
    missing_as_zero: Literal[False] = False
    mean_available_components: Literal[False] = False
    fallback_profile: None = None
    tiers: TierContract
    ranking: RankingContract
    definition_blockers: tuple[Label, ...]
    execution_eligibility: Literal["BLOCKED"] = "BLOCKED"
    execution_blockers: tuple[Label, ...] = Field(min_length=1)

    @field_validator("score_profile_id", "score_profile_version")
    @classmethod
    def exact(cls, value):
        return exact_label(value)

    @model_validator(mode="after")
    def validate_profile(self):
        keys = [component.component_key for component in self.components]
        if len(keys) != len(set(keys)) or sum(component.weight_bps for component in self.components) != 10000:
            raise ValueError("score_weights_must_sum_10000_unique_components")
        refs = [ref.metric_key for ref in (*self.required_metrics, *self.optional_metrics)]
        if len(refs) != len(set(refs)):
            raise ValueError("duplicate_or_conflicting_metric_requirements")
        required = {ref.metric_key: ref for ref in self.required_metrics}
        for component in self.components:
            if len({ref.metric_key for ref in component.metrics}) != len(component.metrics):
                raise ValueError("duplicate_component_metric_dependency")
            if component.aggregation == "IDENTITY" and len(component.metrics) != 1:
                raise ValueError("identity_component_requires_single_metric")
            if component.metrics and any(required.get(ref.metric_key) != ref for ref in component.metrics):
                raise ValueError("scoring_metrics_must_be_required_exact_references")
        unresolved = (
            self.normalization.formula_semantics is None or self.normalization.singleton_policy is None
            or self.ranking.rank_method is None or not self.required_metrics
            or any(not component.metrics or component.aggregation is None or component.direction is None
                   or component.definition_blockers for component in self.components)
        )
        if unresolved and not self.definition_blockers:
            raise ValueError("unresolved_score_definition_requires_blockers")
        if not self.definition_blockers and not {"change_pct", "return_5d"} <= set(required):
            raise ValueError("tier_eligibility_metric_requirements_missing")
        return self

    @property
    def definition_status(self) -> str:
        return "BLOCKED" if self.definition_blockers else "DEFINED"

    def canonical_payload(self) -> str:
        data = self.model_dump(mode="json")
        for key in ("required_metrics", "optional_metrics"):
            data[key].sort(key=lambda ref: ref["metric_key"])
        for component in data["components"]:
            component["metrics"].sort(key=lambda ref: ref["metric_key"])
            component["definition_blockers"] = sorted(set(component["definition_blockers"]))
        data["components"].sort(key=lambda component: component["component_key"])
        data["ranking"]["exact_comparison_keys"] = sorted(data["ranking"]["exact_comparison_keys"])
        for key in ("definition_blockers", "execution_blockers"):
            data[key] = sorted(set(data[key]))
        return canonical(data)

    @property
    def content_hash(self) -> str:
        return digest(json.loads(self.canonical_payload()))

    @property
    def identity(self) -> ScoreProfileIdentity:
        return ScoreProfileIdentity(score_profile_id=self.score_profile_id, score_profile_version=self.score_profile_version,
                                    content_hash=self.content_hash)

    def to_dict(self) -> dict:
        return self.model_dump(mode="json") | {"content_hash": self.content_hash, "definition_status": self.definition_status}


def candidate_calculation_v1() -> MomentumCalculationDefinition:
    """Explicit opt-in metadata factory; never called during startup or calculation."""
    missing = MissingInputContract(missing_status="UNAVAILABLE", missing_reason="required_input_or_session_missing",
                                   invalid_contract_reason="input_semantics_unverified_or_conflicting")
    metrics = []
    specs = [("change_pct", 2, ("close",), "FRACTION", "C_D / C_(D-1) - 1"),
             ("consecutive_up_days", None, ("close",), "COUNT",
              "maximal trailing run of close(s) > close(previous_session(s)); stop at first non-increase; missing boundary/history yields null"),
             ("volatility_20", 21, ("close",), "NON_ANNUALIZED_LOG_STD",
              "sample standard deviation (ddof=1) of 20 log(close(s)/close(previous_session(s))) observations ending D; not annualized"),
             ("volatility_status", 21, ("volatility_20",), "QUALITY_STATUS",
              "propagate volatility_20 quality status; not a low/high volatility classification"),
             ("volume_ratio_20", 21, ("volume",), "RATIO", "V_D / mean(V_(D-20), ..., V_(D-1)); exclude D")]
    for n in (3, 5, 10):
        specs.append((f"return_{n}d", n + 1, ("close",), "FRACTION", f"C_D / C_(D-{n}) - 1; {n} exact trading-session intervals"))
    for n in (20, 60):
        specs.extend([
            (f"breakout_{n}", n + 1, ("close", "high"), "BOOLEAN", f"C_D > max(H_(D-1), ..., H_(D-{n})); exclude D"),
            (f"high_break_{n}", n + 1, ("high",), "BOOLEAN", f"H_D > max(H_(D-1), ..., H_(D-{n})); exclude D"),
        ])
    for key, sessions, inputs, output, formula in specs:
        metrics.append(MomentumMetricDefinition(
            metric_key=key, metric_version="v1", formula_semantics=formula,
            required_inputs=inputs, required_history_sessions=sessions,
            history_rule="contiguous exact completed sessions; no missing-session skipping; positive price/divisor required",
            price_basis_requirement="NOT_REQUIRED" if key == "volume_ratio_20" else "SPLIT_ADJUSTED_PRICE_ONLY",
            volume_semantics_requirement="COMPARABLE_CORPORATE_ACTION_QUANTITY" if key == "volume_ratio_20" else "NOT_REQUIRED",
            calendar_requirement="EXACT_IMMUTABLE_SESSION_SEQUENCE", finality_requirement="COMPLETED_FINAL_DAILY_SESSIONS",
            pit_requirement="INPUT_KNOWN_BY_KNOWLEDGE_CUTOFF", output_type=output, missing_input=missing))
    return MomentumCalculationDefinition(calculation_id="momentum-daily", calculation_version="v1", metrics=tuple(metrics),
        execution_blockers=("production_input_contract_unverified", "production_calculation_engine_absent"))


def candidate_technical_profile_v1(calculation: MomentumCalculationDefinition) -> MomentumScoreProfile:
    """Known weights only; missing design decisions stay explicit, never guessed."""
    return MomentumScoreProfile(
        score_profile_id="momentum-technical-v1", score_profile_version="v1", calculation=calculation.identity,
        components=tuple(ScoreComponent(component_key=key, weight_bps=weight, metrics=(), aggregation=None, direction=None,
                                       definition_blockers=("component_metric_mapping_and_transform_unresolved",))
                         for key, weight in (("price_strength", 4000), ("volume_strength", 2500), ("breakout", 2000), ("volatility_quality", 1500))),
        normalization=NormalizationContract(version="percentile-candidate-v1", formula_semantics=None,
                                              singleton_policy=None, incomplete_universe="BLOCKED"),
        required_metrics=(), optional_metrics=(), tiers=TierContract(t1_bps=500, t2_bps=2000),
        missing_required_status="UNAVAILABLE", missing_required_reason="required_scoring_component_unavailable",
        ranking=RankingContract(exact_comparison_keys=COMPARISON_KEYS, rank_method=None),
        definition_blockers=("component_metric_mapping_and_transform_unresolved", "percentile_formula_and_singleton_unresolved", "ranking_tie_method_unresolved"),
        execution_blockers=("score_definition_incomplete", "production_input_contract_unverified", "production_score_engine_absent"))


class MomentumCalculationStore:
    """One dedicated append-only metadata database, no startup materialization."""

    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "user_data" / "momentum_calculation_contracts.sqlite3"

    def _read(self, kind: str, object_id: str, version: str, content_hash: str):
        if not self.path.exists():
            return None
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            row = db.execute("SELECT payload FROM definitions WHERE kind=? AND object_id=? AND version=? AND content_hash=?",
                             (kind, object_id, version, content_hash)).fetchone()
        if not row:
            return None
        model = MomentumCalculationDefinition if kind == "calculation" else MomentumScoreProfile
        artifact = model.model_validate_json(row[0])
        if artifact.content_hash != content_hash:
            raise ValueError("contract_payload_hash_conflict")
        return artifact

    def get_calculation(self, identity: CalculationIdentity) -> MomentumCalculationDefinition | None:
        identity = CalculationIdentity.model_validate(identity.model_dump())
        result = self._read("calculation", identity.calculation_id, identity.calculation_version, identity.content_hash)
        if result is not None and result.identity != identity:
            raise ValueError("contract_payload_identity_conflict")
        return result

    def get_score_profile(self, identity: ScoreProfileIdentity) -> MomentumScoreProfile | None:
        identity = ScoreProfileIdentity.model_validate(identity.model_dump())
        result = self._read("profile", identity.score_profile_id, identity.score_profile_version, identity.content_hash)
        if result is not None and result.identity != identity:
            raise ValueError("contract_payload_identity_conflict")
        return result

    def resolve_cohort_contracts(self, cohort: MomentumRankingCohort) -> dict:
        cohort = MomentumRankingCohort.model_validate_json(cohort.model_dump_json())
        calculation = self.get_calculation(cohort.calculation)
        profile = self.get_score_profile(cohort.score_profile)
        if calculation is None or profile is None or profile.calculation != cohort.calculation:
            return {"binding_status": "BLOCKED", "blocker": "exact_calculation_or_profile_binding_missing"}
        return {"binding_status": "EXACT", "definition_status": profile.definition_status if calculation.definition_status == "DEFINED" else "BLOCKED",
                "execution_eligibility": "BLOCKED", "calculation": calculation, "score_profile": profile}

    def save(self, artifact: MomentumCalculationDefinition | MomentumScoreProfile) -> None:
        profile = isinstance(artifact, MomentumScoreProfile)
        model = MomentumScoreProfile if profile else MomentumCalculationDefinition
        artifact = model.model_validate_json(artifact.model_dump_json())
        if profile:
            calculation = self.get_calculation(artifact.calculation)
            if calculation is None:
                raise ValueError("exact_calculation_dependency_missing")
            available = {metric.metric_key: MetricReference(metric_key=metric.metric_key, metric_version=metric.metric_version,
                                                          content_hash=metric.content_hash) for metric in calculation.metrics}
            if any(available.get(ref.metric_key) != ref for ref in (*artifact.required_metrics, *artifact.optional_metrics)):
                raise ValueError("exact_metric_dependency_conflict")
        kind = "profile" if profile else "calculation"
        identity = artifact.identity
        object_id = identity.score_profile_id if profile else identity.calculation_id
        version = identity.score_profile_version if profile else identity.calculation_version
        payload = artifact.canonical_payload()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""CREATE TABLE IF NOT EXISTS definitions (
                kind TEXT NOT NULL, object_id TEXT NOT NULL, version TEXT NOT NULL,
                content_hash TEXT NOT NULL, payload TEXT NOT NULL, stored_at TEXT NOT NULL,
                PRIMARY KEY(kind, object_id, version))""")
            found = db.execute("SELECT content_hash, payload FROM definitions WHERE kind=? AND object_id=? AND version=?",
                               (kind, object_id, version)).fetchone()
            if found:
                if found != (artifact.content_hash, payload):
                    raise ValueError("immutable_contract_semantic_collision")
                return
            db.execute("INSERT INTO definitions VALUES (?,?,?,?,?,?)", (kind, object_id, version, artifact.content_hash,
                                                                       payload, datetime.now(UTC).isoformat()))
