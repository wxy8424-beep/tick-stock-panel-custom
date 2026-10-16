"""Pure Daily calculation on caller-validated evidence. No IO or production producer."""
from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from typing import TYPE_CHECKING, Literal
from zoneinfo import ZoneInfo

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    FiniteFloat,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from app.market_session import market_from_symbol
from app.services.evidence_execution import TradingCalendarContract
from app.services.momentum_calculation_contracts import (
    MetricReference,
    MomentumCalculationDefinition,
    MomentumRankingCohort,
    MomentumScoreProfile,
    calculation_with_trend_v1_1,
    candidate_calculation_v1,
    technical_profile_v1_2,
)
from app.services.momentum_score_semantics import (
    ScoreCandidate,
    ScoreSemanticsResult,
    rational,
    validate_score_semantics,
)
from app.services.momentum_snapshots import (
    Label,
    MetricEvidence,
    MomentumIdentity,
    MomentumSnapshotRecord,
    State,
    canonical,
)
from app.services.momentum_universes import MomentumUniverseDefinition

if TYPE_CHECKING:
    from app.services.momentum_input_gate import MomentumGateAcceptedInput

Trend = Literal["EXPANDING", "CONTRACTING", "UNCHANGED"]


class DailyBar(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    trading_date: date
    open: FiniteFloat | None = None
    high: FiniteFloat | None = None
    low: FiniteFloat | None = None
    close: FiniteFloat | None = None
    volume: FiniteFloat | None = None
    turnover: FiniteFloat | None = None
    available_at: AwareDatetime | None
    finality_status: State
    finality_reference: Label | None
    evidence_reference: Label

    @field_validator("open", "high", "low", "close", "volume", "turnover", mode="before")
    @classmethod
    def reject_numeric_boolean(cls, value):
        if isinstance(value, bool):
            raise ValueError("numeric_boolean_not_allowed")
        return value

    @field_validator("available_at")
    @classmethod
    def utc(cls, value):
        return value.astimezone(UTC) if value else None


class ValidatedDailyInput(BaseModel):
    """Evidence declarations, not a provider adapter or proof of vendor facts."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    identity: MomentumIdentity
    bars: tuple[DailyBar, ...]
    generated_at: AwareDatetime
    knowledge_cutoff: AwareDatetime
    source: Label
    input_references: tuple[Label, ...]
    price_basis: Literal["SPLIT_ADJUSTED_PRICE_ONLY", "UNKNOWN"] | None
    price_status: State
    volume_unit: Label | None
    quantity_status: State
    pit_status: State
    source_vintage: Label | None
    adjustment_method: Label | None = None
    warnings: tuple[Label, ...] = ()

    @field_validator("generated_at", "knowledge_cutoff")
    @classmethod
    def utc(cls, value):
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_input(self):
        if self.knowledge_cutoff > self.generated_at:
            raise ValueError("future_knowledge_cutoff")
        if market_from_symbol(self.identity.symbol) != self.identity.market:
            raise ValueError("symbol_market_conflict")
        dates = [bar.trading_date for bar in self.bars]
        if len(dates) != len(set(dates)):
            raise ValueError("duplicate_daily_session")
        return self


class MetricResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    identity: MetricReference
    value: StrictBool | StrictInt | FiniteFloat | State | Trend | None
    evidence: MetricEvidence

    @model_validator(mode="after")
    def validate_result(self):
        if self.identity.metric_key != self.evidence.metric:
            raise ValueError("metric_evidence_identity_conflict")
        if self.evidence.status == "READY" and (self.value is None or self.evidence.blockers or not self.evidence.evidence_refs):
            raise ValueError("ready_metric_requires_value_and_evidence")
        return self


class VolatilityTrendResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    value: Trend | None
    evidence: MetricEvidence

    @model_validator(mode="after")
    def separate_quality(self):
        if self.evidence.metric != "volatility_trend_status":
            raise ValueError("trend_evidence_key_required")
        if self.evidence.status == "READY":
            if self.value is None or self.evidence.blockers or not self.evidence.evidence_refs:
                raise ValueError("trend_ready_evidence_incomplete")
        elif self.value is not None:
            raise ValueError("trend_requires_ready_sigma_quality")
        return self


def volatility_trend(current: float | None, previous: float | None, *, current_status: State,
                     previous_status: State, evidence_refs: tuple[str, ...], sessions_complete: bool) -> VolatilityTrendResult:
    reasons = []
    status = "UNAVAILABLE"
    if not sessions_complete:
        reasons.append("trend_required_session_missing")
    if current is None:
        reasons.append("current_sigma_missing")
    if previous is None:
        reasons.append("previous_sigma_missing")
    if current_status != "READY" or previous_status != "READY":
        reasons.append("sigma_quality_not_ready")
        status = "BLOCKED" if "BLOCKED" in (current_status, previous_status) else "PARTIAL" if "PARTIAL" in (current_status, previous_status) else "UNAVAILABLE"
    if current is not None and (isinstance(current, bool) or not math.isfinite(current) or current < 0):
        reasons.append("current_sigma_invalid")
        status = "BLOCKED"
    if previous is not None and (isinstance(previous, bool) or not math.isfinite(previous) or previous < 0):
        reasons.append("previous_sigma_invalid")
        status = "BLOCKED"
    if not evidence_refs:
        reasons.append("sigma_evidence_missing")
        status = "BLOCKED"
    value = None if reasons else "EXPANDING" if current > previous else "CONTRACTING" if current < previous else "UNCHANGED"
    return VolatilityTrendResult(value=value, evidence=MetricEvidence(metric="volatility_trend_status",
        status=status if reasons else "READY", blockers=tuple(reasons), evidence_refs=evidence_refs))


class MomentumTrendSnapshotCandidate(MomentumSnapshotRecord):
    """New schema only, intentionally unsupported by the v1 production Store."""
    snapshot_version: Literal["momentum-snapshot-v2"] = "momentum-snapshot-v2"
    volatility_trend_status: Trend | None
    volatility_trend_evidence: MetricEvidence

    @model_validator(mode="after")
    def exact_trend_binding(self):
        calculation = calculation_with_trend_v1_1()
        if (self.calculation_id, self.calculation_version, self.calculation_content_hash) != (
            calculation.calculation_id, calculation.calculation_version, calculation.content_hash
        ):
            raise ValueError("trend_snapshot_requires_exact_extended_calculation")
        VolatilityTrendResult(value=self.volatility_trend_status, evidence=self.volatility_trend_evidence)
        if self.volatility_trend_status is not None and (
            self.volatility_status != "READY" or self.volatility_20 is None or self.volatility_20 < 0
            or not any(item.metric == "volatility_20" and item.status == "READY" for item in self.metric_statuses)
        ):
            raise ValueError("trend_requires_ready_current_sigma")
        if self.score_profile_id is not None:
            profile = technical_profile_v1_2(calculation)
            if (self.score_profile_id, self.score_profile_version, self.score_profile_content_hash) != (
                profile.score_profile_id, profile.score_profile_version, profile.content_hash
            ):
                raise ValueError("trend_snapshot_score_profile_conflict")
        return self

    def canonical_payload(self) -> str:
        data = json.loads(super().canonical_payload())
        for key in ("blockers", "warnings", "evidence_refs"):
            data["volatility_trend_evidence"][key] = sorted(set(data["volatility_trend_evidence"][key]))
        return canonical(data)

    @property
    def snapshot_id(self) -> str:
        return f"momentum-v2:{self.logical_key}:{self.revision}"


def _known(value):
    return value is not None and value.upper() not in {"UNKNOWN", "BLOCKED", "UNVERIFIED", "LATEST", "CURRENT", "*"}


def _finite_float(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except OverflowError:
        return None


def _sessions(calendar, end):
    result = []
    day = calendar.coverage_start
    while day <= end:
        if day in calendar.additional_trading_days or (day.weekday() in calendar.trading_weekdays and day not in calendar.holidays):
            result.append(day)
        day += timedelta(days=1)
    return result


def _close(calendar, day):
    clock = calendar.early_close if day in calendar.half_days else calendar.session.regular_windows[-1][1]
    return datetime.combine(day, clock, ZoneInfo(calendar.timezone)).astimezone(UTC)


def _calculate_metrics(data: ValidatedDailyInput, calculation: MomentumCalculationDefinition,
                      calendar: TradingCalendarContract) -> tuple[MetricResult, ...]:
    """No IO. Missing dates remain holes in the exact immutable session sequence."""
    data = ValidatedDailyInput.model_validate_json(data.model_dump_json())
    calculation = MomentumCalculationDefinition.model_validate_json(calculation.model_dump_json())
    calendar = TradingCalendarContract.model_validate_json(calendar.model_dump_json())
    supported = (candidate_calculation_v1().identity, calculation_with_trend_v1_1().identity)
    identity = data.identity
    if calculation.identity not in supported or (identity.calculation_id, identity.calculation_version, identity.calculation_content_hash) != (
        calculation.calculation_id, calculation.calculation_version, calculation.content_hash
    ):
        raise ValueError("exact_calculation_binding_required")
    if (identity.market, identity.calendar_id, identity.calendar_version, identity.calendar_content_hash) != (
        calendar.market, calendar.calendar_id, calendar.version, calendar.content_hash
    ):
        raise ValueError("exact_calendar_binding_required")
    if not calendar.coverage_start <= identity.trading_date <= calendar.coverage_end:
        raise ValueError("event_outside_calendar_coverage")
    sessions = _sessions(calendar, identity.trading_date)
    if not sessions or sessions[-1] != identity.trading_date:
        raise ValueError("event_is_not_trading_session")
    bars = {bar.trading_date: bar for bar in data.bars}
    session_set = set(sessions)
    if any(day not in session_set for day in bars):
        raise ValueError("non_session_or_future_bar")
    metric_refs = set(data.input_references)

    def window(count, price=True, offset=0):
        if price and (data.price_basis != "SPLIT_ADJUSTED_PRICE_ONLY" or data.price_status != "READY"):
            return [], "BLOCKED", "price_basis_contract_unsatisfied"
        if not price and (data.quantity_status != "READY" or not _known(data.volume_unit)):
            return [], "BLOCKED", "volume_quantity_contract_unsatisfied"
        if data.pit_status != "READY" or not _known(data.source_vintage) or not data.input_references:
            return [], "BLOCKED", "pit_contract_unsatisfied"
        end = len(sessions) - offset
        if end < count:
            return [], "UNAVAILABLE", "insufficient_calendar_history"
        days = sessions[end - count:end]
        if any(day not in bars for day in days):
            return [], "UNAVAILABLE", "required_session_bar_missing"
        selected = [bars[day] for day in days]
        for bar in selected:
            close_time = _close(calendar, bar.trading_date)
            if close_time > data.knowledge_cutoff or bar.finality_status != "READY" or not _known(bar.finality_reference):
                return [], "BLOCKED", "completed_final_session_unproven"
            if bar.available_at is None or not close_time <= bar.available_at <= data.knowledge_cutoff:
                return [], "BLOCKED", "bar_availability_unproven_or_future"
        metric_refs.update(bar.evidence_reference for bar in selected)
        metric_refs.update(bar.finality_reference for bar in selected)
        return selected, "READY", None

    def sigma(offset=0):
        selected, state, reason = window(21, offset=offset)
        if state != "READY":
            return None, state, reason
        closes = [bar.close for bar in selected]
        if any(value is None or value <= 0 for value in closes):
            return None, "UNAVAILABLE", "positive_close_required"
        ratios = [b / a for a, b in pairwise(closes)]
        if any(not math.isfinite(ratio) or ratio <= 0 for ratio in ratios):
            return None, "BLOCKED", "nonfinite_log_return_input"
        returns = [math.log(ratio) for ratio in ratios]
        return statistics.stdev(returns), "READY", None

    results = []
    for definition in calculation.metrics:
        metric_refs = set(data.input_references)
        key = definition.metric_key
        value, state, reason = None, "UNAVAILABLE", None
        if key == "volatility_trend_status":
            current, cs, _ = sigma()
            previous, ps, _ = sigma(1)
            trend = volatility_trend(current, previous, current_status=cs, previous_status=ps,
                evidence_refs=tuple(sorted(metric_refs)), sessions_complete=len(sessions) >= 22 and all(day in bars for day in sessions[-22:]))
            value, state = trend.value, trend.evidence.status
            evidence = trend.evidence
        else:
            count = definition.required_history_sessions or 2
            selected, state, reason = window(count, price=key != "volume_ratio_20")
            if key == "volatility_status":
                # Independent QUALITY_STATUS, never a trend enum.
                _, state, reason = sigma()
                value = state
            elif key == "volatility_20":
                value, state, reason = sigma()
            elif state == "READY":
                if key == "consecutive_up_days":
                    value = 0
                    for offset in range(len(sessions) - 1):
                        selected, state, reason = window(2, offset=offset)
                        if state != "READY":
                            value = None
                            break
                        a, b = selected[0].close, selected[1].close
                        if a is None or b is None or min(a, b) <= 0:
                            value, state, reason = None, "UNAVAILABLE", "positive_close_required"
                            break
                        if b <= a:
                            break
                        value += 1
                    else:
                        value, state, reason = None, "UNAVAILABLE", "consecutive_run_boundary_unproven"
                elif key == "volume_ratio_20":
                    volumes = [bar.volume for bar in selected]
                    if any(v is None or v < 0 for v in volumes):
                        state, reason = "UNAVAILABLE", "volume_observation_missing_or_invalid"
                    elif sum(rational(v) for v in volumes[:-1]) == 0:
                        state, reason = "UNAVAILABLE", "volume_denominator_zero"
                    else:
                        value = _finite_float(rational(volumes[-1]) * 20 / sum(rational(v) for v in volumes[:-1]))
                        if value is None:
                            state, reason = "BLOCKED", "nonfinite_calculation_result"
                elif key.startswith(("breakout_", "high_break_")):
                    highs = [bar.high for bar in selected[:-1]]
                    current = selected[-1].high if key.startswith("high_break_") else selected[-1].close
                    if current is None or current <= 0 or any(h is None or h <= 0 for h in highs):
                        state, reason = "UNAVAILABLE", "positive_price_or_high_required"
                    else:
                        value = current > max(highs)
                else:
                    closes = [bar.close for bar in selected]
                    if any(v is None or v <= 0 for v in closes):
                        state, reason = "UNAVAILABLE", "positive_close_required"
                    else:
                        value = _finite_float(rational(closes[-1]) / rational(closes[0]) - 1)
                        if value is None:
                            state, reason = "BLOCKED", "nonfinite_calculation_result"
            if isinstance(value, float) and not math.isfinite(value):
                value, state, reason = None, "BLOCKED", "nonfinite_calculation_result"
            evidence = MetricEvidence(metric=key, status=state, blockers=(reason,) if reason else (), evidence_refs=tuple(sorted(metric_refs)))
        result = MetricResult(identity=MetricReference(metric_key=key, metric_version=definition.metric_version,
            content_hash=definition.content_hash), value=value, evidence=evidence)
        results.append(result)
    return tuple(results)


@dataclass(frozen=True)
class MomentumEngineResult:
    snapshots: tuple[MomentumSnapshotRecord | MomentumTrendSnapshotCandidate, ...]
    metrics: tuple[tuple[MetricResult, ...], ...]
    scoring: ScoreSemanticsResult
    expected_count: int
    valid_count: int
    excluded_count: int
    production_execution: str = "BLOCKED"


def _calculate_momentum(*, inputs: tuple[ValidatedDailyInput, ...], calculation: MomentumCalculationDefinition,
                       profile: MomentumScoreProfile, calendar: TradingCalendarContract,
                       universe: MomentumUniverseDefinition, cohort: MomentumRankingCohort) -> MomentumEngineResult:
    """Explicit batch calculation, not an orchestrator, registry or Store writer."""
    if profile.calculation != calculation.identity or cohort.calculation != calculation.identity or cohort.score_profile != profile.identity:
        raise ValueError("exact_score_calculation_binding_conflict")
    metrics = tuple(_calculate_metrics(item, calculation, calendar) for item in inputs)
    candidates = []
    for data, values in zip(inputs, metrics, strict=True):
        identity = data.identity
        if (identity.market, identity.trading_date, identity.input_contract_id, identity.input_contract_version,
            identity.universe_id, identity.universe_version, identity.universe_content_hash,
            identity.score_profile_id, identity.score_profile_version, identity.score_profile_content_hash) != (
            cohort.market, cohort.trading_date, cohort.input_contract_id, cohort.input_contract_version,
            cohort.universe.universe_id, cohort.universe.universe_version, cohort.universe.content_hash,
            profile.score_profile_id, profile.score_profile_version, profile.content_hash
        ):
            raise ValueError("exact_input_cohort_binding_conflict")
        candidates.append(ScoreCandidate(identity.symbol, cohort, {r.identity.metric_key: r.value for r in values},
                         {r.identity.metric_key: r.evidence.status for r in values}, True))
    scoring = validate_score_semantics(cohort=cohort, profile=profile, universe=universe, candidates=tuple(candidates))
    snapshots = []
    for data, values in zip(inputs, metrics, strict=True):
        symbol = data.identity.symbol
        mapping = {r.identity.metric_key: r for r in values}
        selected = {key: result.value for key, result in mapping.items() if key != "volatility_trend_status"}
        evidence = [result.evidence for key, result in mapping.items() if key not in {"volatility_status", "volatility_trend_status"}]
        for key, lookup in (("strength_score", scoring.scores), ("rank", scoring.ranks), ("tier", scoring.tiers)):
            selected[key] = float(lookup[symbol]) if key == "strength_score" and symbol in lookup else lookup.get(symbol)
            evidence.append(MetricEvidence(metric=key, status="READY" if symbol in lookup else "UNAVAILABLE",
                blockers=() if symbol in lookup else ("required_scoring_or_tier_inputs_unavailable",), evidence_refs=data.input_references))
        # Explicit policy: any contract-blocked metric blocks this candidate;
        # otherwise complete output is READY, partial metrics are PARTIAL, none UNAVAILABLE.
        states = [result.evidence.status for result in values]
        overall = "BLOCKED" if "BLOCKED" in states else "READY" if all(state == "READY" for state in states) and symbol in scoring.scores else "PARTIAL" if "READY" in states else "UNAVAILABLE"
        if overall == "READY" and (scoring.warnings or symbol not in scoring.tiers):
            overall = "PARTIAL"
        availability_known = (data.pit_status == "READY" and _known(data.source_vintage) and bool(data.input_references)
            and all(bar.available_at is not None and _close(calendar, bar.trading_date) <= bar.available_at <= data.knowledge_cutoff
                    for bar in data.bars))
        pit_status = data.pit_status if data.pit_status != "READY" or availability_known else "BLOCKED"
        if pit_status != "READY" and overall == "READY":
            overall = "BLOCKED"
        payload = data.identity.model_dump() | selected | dict(
            session_timestamp=_close(calendar, data.identity.trading_date), generated_at=data.generated_at,
            available_at=data.generated_at if availability_known else None,
            knowledge_cutoff=data.knowledge_cutoff, source=data.source, provider=None,
            input_references=data.input_references, adjustment_method=data.adjustment_method, price_basis=data.price_basis,
            volume_unit=data.volume_unit, source_vintage=data.source_vintage, source_revision=None,
            pit_status=pit_status,
            overall_status=overall, metric_statuses=tuple(evidence),
            blockers=tuple(sorted({reason for result in values for reason in result.evidence.blockers}
                | ({"input_availability_unproven"} if not availability_known else set()))),
            warnings=tuple(sorted(set(scoring.warnings) | set(data.warnings))))
        if calculation.calculation_version == "v1.1":
            trend = mapping["volatility_trend_status"]
            snapshots.append(MomentumTrendSnapshotCandidate(**payload, volatility_trend_status=trend.value,
                volatility_trend_evidence=trend.evidence))
        else:
            snapshots.append(MomentumSnapshotRecord(**payload))
    return MomentumEngineResult(tuple(snapshots), metrics, scoring, universe.effective_count,
                                len(scoring.scoring_symbols), len(scoring.excluded))


def calculate_metrics(data: MomentumGateAcceptedInput, calculation: MomentumCalculationDefinition,
                      calendar: TradingCalendarContract) -> tuple[MetricResult, ...]:
    """Public entry: receipt/evidence is revalidated before any metric arithmetic."""
    from app.services.momentum_input_gate import open_gated_input

    return _calculate_metrics(open_gated_input(data, calculation, calendar), calculation, calendar)


def calculate_momentum(*, inputs: tuple[MomentumGateAcceptedInput, ...], calculation: MomentumCalculationDefinition,
                       profile: MomentumScoreProfile, calendar: TradingCalendarContract,
                       universe: MomentumUniverseDefinition, cohort: MomentumRankingCohort) -> MomentumEngineResult:
    """Public batch boundary. Reject the entire batch before math if any Gate fails."""
    from app.services.momentum_input_gate import open_gated_input

    if not inputs:
        raise ValueError("momentum_input_gate_required")
    validated = tuple(open_gated_input(value, calculation, calendar, universe) for value in inputs)
    return _calculate_momentum(inputs=validated, calculation=calculation, profile=profile,
                              calendar=calendar, universe=universe, cohort=cohort)
