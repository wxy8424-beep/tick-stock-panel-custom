"""Pure technical-v1.1 arithmetic on explicitly supplied inputs, never a producer.

Fractions preserve mathematical ties. Decimal-text conversion defines numeric
input identity; no score rounding, provider access, scheduling or persistence.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from fractions import Fraction
from zoneinfo import ZoneInfo

from app.services.momentum_calculation_contracts import (
    MomentumRankingCohort,
    MomentumScoreProfile,
    calculation_with_trend_v1_1,
    candidate_calculation_v1,
    technical_profile_v1_1,
    technical_profile_v1_2,
)
from app.services.momentum_universes import MomentumUniverseDefinition

Number = int | float | Decimal | Fraction
PRICE_WEIGHTS = {"return_3d": 25, "return_5d": 35, "return_10d": 40}
BREAKOUT_POINTS = {"breakout_20": 25, "breakout_60": 25, "high_break_20": 20, "high_break_60": 30}
PERCENTILE_METRICS = (*PRICE_WEIGHTS, "volume_ratio_20", "volatility_20")
SCORING_METRICS = (*PERCENTILE_METRICS, *BREAKOUT_POINTS)
COMPONENT_WEIGHTS = {"price_strength": 40, "volume_strength": 25, "breakout": 20, "volatility_quality": 15}


def rational(value: Number) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal, Fraction)):
        raise ValueError("finite_numeric_input_required")
    try:
        return value if isinstance(value, Fraction) else Fraction(str(value))
    except (ValueError, OverflowError, ZeroDivisionError) as exc:
        raise ValueError("finite_numeric_input_required") from exc


def percentile_scores(values: Mapping[str, Number], *, descending: bool = False) -> dict[str, Fraction]:
    """Endpoint mid-rank, neutral singleton; missing inputs must be excluded first."""
    numeric = {key: rational(value) for key, value in values.items()}
    count = len(numeric)
    frequencies = Counter(numeric.values())
    by_value = {}
    lower = 0
    for value in sorted(frequencies):
        equal = frequencies[value]
        score = Fraction(50) if count == 1 else 100 * (lower + Fraction(equal - 1, 2)) / (count - 1)
        by_value[value] = 100 - score if descending else score
        lower += equal
    return {key: by_value[numeric[key]] for key in sorted(numeric)}


def _weighted_required(values: Mapping[str, Number | None], weights: Mapping[str, int]) -> Fraction | None:
    if any(values.get(key) is None for key in weights):
        return None
    numeric = {key: rational(values[key]) for key in weights}
    if any(not 0 <= value <= 100 for value in numeric.values()):
        raise ValueError("component_score_out_of_range")
    return sum((numeric[key] * weight for key, weight in weights.items()), Fraction()) / 100


def price_strength(percentiles: Mapping[str, Number | None]) -> Fraction | None:
    return _weighted_required(percentiles, PRICE_WEIGHTS)


def volume_strength(percentiles: Mapping[str, Number | None]) -> Fraction | None:
    return _weighted_required(percentiles, {"volume_ratio_20": 100})


def breakout_strength(values: Mapping[str, bool | None]) -> Fraction | None:
    if any(values.get(key) is None for key in BREAKOUT_POINTS):
        return None
    if any(type(values[key]) is not bool for key in BREAKOUT_POINTS):
        raise ValueError("breakout_boolean_required")
    return Fraction(sum(points for key, points in BREAKOUT_POINTS.items() if values[key]))


def final_strength(components: Mapping[str, Number | None]) -> Fraction | None:
    return _weighted_required(components, COMPONENT_WEIGHTS)


def competition_ranks(scores: Mapping[str, Number | None]) -> dict[str, int]:
    ordered = sorted(((symbol, rational(value)) for symbol, value in scores.items() if value is not None),
                     key=lambda item: (-item[1], item[0]))
    result = {}
    previous = None
    rank = 0
    for position, (symbol, score) in enumerate(ordered, 1):
        if score != previous:
            rank = position
        result[symbol] = rank
        previous = score
    return result


def assign_tiers(scores: Mapping[str, Number | None], change_pct: Mapping[str, Number | None],
                 return_5d: Mapping[str, Number | None]) -> dict[str, str]:
    """Separate tier subset; competition rank puts a whole boundary tie above it."""
    eligible = {symbol: score for symbol, score in scores.items() if score is not None
                and change_pct.get(symbol) is not None and return_5d.get(symbol) is not None
                and rational(change_pct[symbol]) > 0 and rational(return_5d[symbol]) > 0}
    ranks = competition_ranks(eligible)
    count = len(eligible)
    t1, t2 = (count * 5 + 99) // 100, (count * 20 + 99) // 100
    return {symbol: "T1" if rank <= t1 else "T2" if rank <= t2 else "T3" for symbol, rank in ranks.items()}


@dataclass(frozen=True)
class ScoreCandidate:
    """Caller-supplied evidence, not verification of a real provider or PIT claim."""
    symbol: str
    cohort: MomentumRankingCohort
    values: Mapping[str, Number | bool | None]
    metric_statuses: Mapping[str, str]
    input_contract_satisfied: bool


@dataclass(frozen=True)
class ScoreSemanticsResult:
    cohort: MomentumRankingCohort
    scoring_symbols: tuple[str, ...]
    excluded: dict[str, tuple[str, ...]]
    percentiles: dict[str, dict[str, Fraction]]
    components: dict[str, dict[str, Fraction]]
    scores: dict[str, Fraction]
    ranks: dict[str, int]
    tiers: dict[str, str]
    warnings: tuple[str, ...]
    # Always BLOCKED: arithmetic validation is not production execution approval.
    execution_eligibility: str = "BLOCKED"


def validate_score_semantics(*, cohort: MomentumRankingCohort, profile: MomentumScoreProfile,
                             universe: MomentumUniverseDefinition,
                             candidates: tuple[ScoreCandidate, ...]) -> ScoreSemanticsResult:
    """Pure fixture/caller-input validation. Freeze one cohort before any math.

    Identity/config conflicts raise explicitly. Unavailable candidates are excluded
    with coverage warnings; never substitute a provider/profile or metric.
    """
    cohort = MomentumRankingCohort.model_validate_json(cohort.model_dump_json())
    universe = MomentumUniverseDefinition.model_validate_json(universe.model_dump_json())
    profile = MomentumScoreProfile.model_validate_json(profile.model_dump_json())
    supported = (technical_profile_v1_1(candidate_calculation_v1()).identity,
                 technical_profile_v1_2(calculation_with_trend_v1_1()).identity)
    if profile.identity not in supported:
        raise ValueError("exact_technical_v1_1_profile_required_no_fallback")
    if cohort.score_profile != profile.identity or cohort.calculation != profile.calculation:
        raise ValueError("exact_calculation_profile_conflict")
    if cohort.universe != universe.identity:
        raise ValueError("exact_universe_conflict")
    if universe.status != "READY":
        raise ValueError("incomplete_or_unverified_universe_blocked")
    # Dates are checked in each market's official timezone, not the host timezone.
    zone = ZoneInfo("Asia/Hong_Kong" if cohort.market == "HK" else "America/New_York")
    start = universe.effective_from.astimezone(zone).date()
    end = universe.effective_to.astimezone(zone).date() if universe.effective_to else None
    # Conservative date-only check: do not assume an intraday interval covers D.
    day_start = datetime.combine(cohort.trading_date, time.min, zone)
    day_end = datetime.combine(cohort.trading_date, time.max, zone)
    if cohort.trading_date < start or (end is not None and cohort.trading_date > end) or (
        day_start < universe.effective_from or (universe.effective_to is not None and day_end >= universe.effective_to)
    ):
        raise ValueError("universe_effective_period_does_not_cover_trading_date")
    included = {member.symbol for member in universe.members if member.membership_status == "INCLUDED"}
    supplied = set()
    eligible = {}
    excluded = {}
    for candidate in candidates:
        if candidate.cohort != cohort:
            raise ValueError("exact_candidate_cohort_conflict")
        if candidate.symbol not in included or candidate.symbol in supplied:
            raise ValueError("ineligible_or_duplicate_candidate")
        supplied.add(candidate.symbol)
        reasons = []
        if candidate.input_contract_satisfied is not True:
            reasons.append("input_contract_not_satisfied")
        for key in SCORING_METRICS:
            value = candidate.values.get(key)
            if candidate.metric_statuses.get(key) != "READY" or value is None:
                reasons.append(f"{key}_not_ready")
                continue
            if key in BREAKOUT_POINTS:
                valid = type(value) is bool
            else:
                try:
                    numeric = rational(value)
                    valid = numeric >= 0 if key in {"volume_ratio_20", "volatility_20"} else numeric >= -1
                except ValueError:
                    valid = False
            if not valid:
                reasons.append(f"{key}_invalid_value")
        if reasons:
            excluded[candidate.symbol] = tuple(reasons)
        else:
            eligible[candidate.symbol] = candidate
    for symbol in sorted(included - supplied):
        excluded[symbol] = ("candidate_not_supplied",)
    # No metric-specific cohort, nor post-percentile removal, is allowed below.
    percentiles = {key: percentile_scores({symbol: candidate.values[key] for symbol, candidate in eligible.items()},
                                        descending=key == "volatility_20") for key in PERCENTILE_METRICS}
    components = {}
    scores = {}
    for symbol in sorted(eligible):
        values = {key: percentiles[key][symbol] for key in PERCENTILE_METRICS}
        components[symbol] = dict(price_strength=price_strength(values), volume_strength=volume_strength(values),
                                  breakout=breakout_strength(eligible[symbol].values), volatility_quality=values["volatility_20"])
        scores[symbol] = final_strength(components[symbol])
    # change_pct has no influence on scoring eligibility or percentile cohort.
    changes = {}
    for symbol, candidate in eligible.items():
        change = candidate.values.get("change_pct") if candidate.metric_statuses.get("change_pct") == "READY" else None
        try:
            changes[symbol] = rational(change) if change is not None else None
        except ValueError:
            changes[symbol] = None
    tiers = assign_tiers(scores, changes, {symbol: candidate.values["return_5d"] for symbol, candidate in eligible.items()})
    warnings = ["scoring_coverage_incomplete_no_complete_market_ranking"] if excluded else []
    if any(changes[symbol] is None for symbol in eligible):
        warnings.append("tier_eligibility_input_missing")
    return ScoreSemanticsResult(cohort, tuple(sorted(eligible)), excluded, percentiles, components, scores,
                                competition_ranks(scores), tiers, tuple(warnings))
