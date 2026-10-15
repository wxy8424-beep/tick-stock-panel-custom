"""Explicit isolated arithmetic fixtures, not production ranking or provider proof."""
from dataclasses import replace
from fractions import Fraction

import pytest
from pydantic import ValidationError
from test_momentum_universes import member, ready

from app.services.momentum_calculation_contracts import (
    MomentumCalculationStore,
    MomentumRankingCohort,
    MomentumScoreProfile,
    candidate_calculation_v1,
    candidate_technical_profile_v1,
    technical_profile_v1_1,
)
from app.services.momentum_score_semantics import (
    BREAKOUT_POINTS,
    COMPONENT_WEIGHTS,
    PERCENTILE_METRICS,
    SCORING_METRICS,
    ScoreCandidate,
    assign_tiers,
    breakout_strength,
    competition_ranks,
    final_strength,
    percentile_scores,
    price_strength,
    rational,
    validate_score_semantics,
    volume_strength,
)


def inputs():
    calculation = candidate_calculation_v1()
    profile = technical_profile_v1_1(calculation)
    universe = ready(members=(member(), member("MSFT.US"), member("NVDA.US")),
                     expected_count=3, effective_count=3, excluded_count=0)
    cohort = MomentumRankingCohort(market="US", trading_date="2026-09-16", universe=universe.identity,
        input_contract_id="fixture-input", input_contract_version="v1", calculation=calculation.identity, score_profile=profile.identity)
    candidates = []
    for index, symbol in enumerate(("AAPL.US", "MSFT.US", "NVDA.US"), 1):
        values = {key: index / 10 for key in PERCENTILE_METRICS} | dict.fromkeys(BREAKOUT_POINTS, True) | {"change_pct": 0.01}
        candidates.append(ScoreCandidate(symbol, cohort, values, dict.fromkeys((*SCORING_METRICS, "change_pct"), "READY"), True))
    return dict(cohort=cohort, profile=profile, universe=universe, candidates=tuple(candidates))


def test_percentile_unique_ascending_descending():
    values = {"z": 3, "a": 1, "b": 2}
    assert percentile_scores(values) == {"a": 0, "b": 50, "z": 100}
    assert percentile_scores(values, descending=True) == {"a": 100, "b": 50, "z": 0}


@pytest.mark.parametrize("values,expected", [
    ({"a": 1, "b": 2, "c": 2, "d": 3}, {"a": 0, "b": 50, "c": 50, "d": 100}),
    ({"a": 1, "b": 1, "c": 3}, {"a": 25, "b": 25, "c": 100}),
    ({"a": 1, "b": 1}, {"a": 50, "b": 50}),
    ({"a": 12}, {"a": 50}),
    ({}, {}),
])
def test_percentile_ties_equal_singleton_empty(values, expected):
    assert percentile_scores(values) == expected
    assert percentile_scores(values, descending=True) == {key: 100 - value for key, value in expected.items()}
    assert percentile_scores(dict(reversed(list(values.items())))) == expected


def test_percentile_exact_rational_no_library_rounding():
    result = percentile_scores({str(i): i for i in range(4)})
    assert result["1"] == Fraction(100, 3)
    assert all(isinstance(value, Fraction) for value in result.values())


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, "1"])
def test_invalid_numeric_rejected(value):
    with pytest.raises(ValueError, match="finite_numeric"):
        rational(value)


@pytest.mark.parametrize("key,expected", [("return_3d", 25), ("return_5d", 35), ("return_10d", 40)])
def test_price_mapping_internal_weights(key, expected):
    values = dict.fromkeys(("return_3d", "return_5d", "return_10d"), 0) | {key: 100}
    assert price_strength(values) == expected
    assert price_strength(values | {key: None}) is None


def test_price_and_volume_no_fallback():
    assert price_strength({"return_3d": 100, "return_5d": 50, "return_10d": 0}) == Fraction(85, 2)
    assert price_strength({"return_3d": 100}) is None
    assert volume_strength({"volume_ratio_20": 75}) == 75
    assert volume_strength({"turnover": 100, "volume": 100}) is None


@pytest.mark.parametrize("key,points", list(BREAKOUT_POINTS.items()))
def test_breakout_points_and_missing(key, points):
    values = dict.fromkeys(BREAKOUT_POINTS, False) | {key: True}
    assert breakout_strength(values) == points
    assert breakout_strength(values | {key: None}) is None


def test_breakout_boolean_extremes_and_strict_type():
    assert breakout_strength(dict.fromkeys(BREAKOUT_POINTS, False)) == 0
    assert breakout_strength(dict.fromkeys(BREAKOUT_POINTS, True)) == 100
    with pytest.raises(ValueError, match="boolean_required"):
        breakout_strength(dict.fromkeys(BREAKOUT_POINTS, 1))


@pytest.mark.parametrize("key,weight", list(COMPONENT_WEIGHTS.items()))
def test_final_weights_and_no_redistribution(key, weight):
    values = dict.fromkeys(COMPONENT_WEIGHTS, 0) | {key: 100}
    assert final_strength(values) == weight
    assert final_strength(values | {key: None}) is None
    values.pop(key)
    assert final_strength(values) is None


@pytest.mark.parametrize("score", [0, 25, 50, 100])
def test_final_range(score):
    assert final_strength(dict.fromkeys(COMPONENT_WEIGHTS, score)) == score


def test_out_of_range_component_rejected():
    with pytest.raises(ValueError, match="out_of_range"):
        final_strength(dict.fromkeys(COMPONENT_WEIGHTS, 101))


def test_competition_rank_ties_and_display_only_symbol():
    assert competition_ranks({"d": 90, "z": 95, "b": 95, "a": 100, "x": None}) == {"a": 1, "b": 2, "z": 2, "d": 4}
    assert competition_ranks({"changed": 95, "other": 95}) == {"changed": 1, "other": 1}


def tiers(scores, changes=None, returns=None):
    return assign_tiers(scores, changes if changes is not None else dict.fromkeys(scores, 1),
                        returns if returns is not None else dict.fromkeys(scores, 1))


def test_small_n_one_two_and_no_forced_t2():
    assert tiers({"a": 50}) == {"a": "T1"}
    assert tiers({"a": 100, "b": 50}) == {"a": "T1", "b": "T3"}
    assert tiers({"a": 50, "b": 50}) == {"a": "T1", "b": "T1"}
    assert tiers({}) == {}


def test_tier_boundaries_and_tie_expansion():
    scores = {str(i): 100 - i for i in range(100)}
    result = tiers(scores)
    assert sum(value == "T1" for value in result.values()) == 5
    assert sum(value == "T2" for value in result.values()) == 15
    assert result["4"] == "T1" and result["5"] == "T2"
    assert result["19"] == "T2" and result["20"] == "T3"
    tied = scores | {"5": scores["4"], "6": scores["4"], "20": scores["19"]}
    result = tiers(tied)
    assert result["6"] == "T1" and result["20"] == "T2"


@pytest.mark.parametrize("change,ret", [(0, 1), (-1, 1), (None, 1), (1, 0), (1, -1), (1, None)])
def test_tier_eligibility(change, ret):
    assert tiers({"a": 50}, {"a": change}, {"a": ret}) == {}


def test_tier_subset_distinct_from_rank_cohort():
    scores = {"a": 100, "b": 90, "c": 80}
    assert competition_ranks(scores)["b"] == 2
    assert tiers(scores, {"a": 0, "b": 1, "c": 1}) == {"b": "T1", "c": "T3"}


def test_same_frozen_cohort_and_volatility_direction():
    data = inputs()
    result = validate_score_semantics(**data)
    assert result.scoring_symbols == ("AAPL.US", "MSFT.US", "NVDA.US")
    assert all(set(values) == set(result.scoring_symbols) for values in result.percentiles.values())
    assert result.percentiles["return_3d"]["AAPL.US"] == 0
    assert result.percentiles["volatility_20"]["AAPL.US"] == 100
    assert result.components["AAPL.US"]["volatility_quality"] == 100
    assert result.scores == {"AAPL.US": 35, "MSFT.US": 60, "NVDA.US": 85}
    assert result.execution_eligibility == "BLOCKED"
    assert result.warnings == ()
    reordered = data | {"candidates": tuple(reversed(data["candidates"]))}
    assert validate_score_semantics(**reordered) == result


@pytest.mark.parametrize("key", SCORING_METRICS)
def test_incomplete_excluded_before_all_percentiles(key):
    data = inputs()
    first, *rest = data["candidates"]
    first = replace(first, values=first.values | {key: None})
    result = validate_score_semantics(**(data | {"candidates": (first, *rest)}))
    assert result.scoring_symbols == ("MSFT.US", "NVDA.US")
    assert all(set(values) == {"MSFT.US", "NVDA.US"} for values in result.percentiles.values())
    assert result.percentiles["return_3d"]["MSFT.US"] == 0
    assert result.percentiles["volatility_20"]["MSFT.US"] == 100
    assert "scoring_coverage_incomplete_no_complete_market_ranking" in result.warnings


@pytest.mark.parametrize("change", [None, float("nan"), True])
def test_change_pct_missing_or_invalid_only_disables_tier(change):
    data = inputs()
    first, *rest = data["candidates"]
    first = replace(first, values=first.values | {"change_pct": change, "consecutive_up_days": 999})
    result = validate_score_semantics(**(data | {"candidates": (first, *rest)}))
    assert result.scores["AAPL.US"] == 35 and result.ranks["AAPL.US"] == 3
    assert "AAPL.US" not in result.tiers
    assert "tier_eligibility_input_missing" in result.warnings


@pytest.mark.parametrize("status", ["PARTIAL", "UNAVAILABLE", "BLOCKED"])
def test_non_ready_scoring_metric_excluded(status):
    data = inputs()
    first, *rest = data["candidates"]
    first = replace(first, metric_statuses=first.metric_statuses | {"volume_ratio_20": status})
    assert "AAPL.US" in validate_score_semantics(**(data | {"candidates": (first, *rest)})).excluded


def test_contract_failure_and_missing_candidates_visible():
    data = inputs()
    first = replace(data["candidates"][0], input_contract_satisfied=False)
    result = validate_score_semantics(**(data | {"candidates": (first,)}))
    assert result.scores == {} and result.ranks == {} and result.tiers == {}
    assert set(result.excluded) == {"AAPL.US", "MSFT.US", "NVDA.US"}


@pytest.mark.parametrize("dimension", ["universe", "input_contract_version", "calculation", "score_profile", "market"])
def test_candidate_exact_identity_isolation(dimension):
    data = inputs()
    first, *rest = data["candidates"]
    payload = first.cohort.model_dump()
    if dimension == "universe":
        payload[dimension]["universe_version"] = "v2"
    elif dimension == "calculation":
        payload[dimension]["content_hash"] = "f" * 64
    elif dimension == "score_profile":
        payload[dimension]["score_profile_version"] = "v9"
    elif dimension == "market":
        payload["market"] = payload["universe"]["market"] = "HK"
    else:
        payload[dimension] = "v2"
    first = replace(first, cohort=MomentumRankingCohort.model_validate(payload))
    with pytest.raises(ValueError, match="exact_candidate_cohort_conflict"):
        validate_score_semantics(**(data | {"candidates": (first, *rest)}))


def test_unknown_universe_and_incomplete_universe_blocked():
    data = inputs()
    other = data["universe"].model_copy(update={"universe_version": "v2"})
    with pytest.raises(ValueError, match="exact_universe_conflict"):
        validate_score_semantics(**(data | {"universe": other}))
    partial = data["universe"].model_copy(update={"status": "PARTIAL"})
    cohort = data["cohort"].model_copy(update={"universe": partial.identity})
    with pytest.raises(ValueError, match="incomplete_or_unverified"):
        validate_score_semantics(**(data | {"universe": partial, "cohort": cohort}))


def test_profile_determinism_and_frozen_legacy_hashes():
    calculation = candidate_calculation_v1()
    old = candidate_technical_profile_v1(calculation)
    new = technical_profile_v1_1(calculation)
    assert calculation.content_hash == "05acb22677f4fc9148916ba5c7b1c012ea15c556befbaa51a422bfa5d21e6a09"
    assert old.content_hash == "be55cfbab6d46a03797b883922209b9e7d2afb2d63893830d0ddb922d7e1c35c"
    assert old.definition_status == "BLOCKED" and new.definition_status == "DEFINED"
    assert old.content_hash != new.content_hash
    payload = new.model_dump(mode="json")
    payload["components"].reverse()
    payload["required_metrics"].reverse()
    payload["technical_semantics"]["price_weights_bps"].reverse()
    payload["technical_semantics"]["breakout_points"].reverse()
    assert MomentumScoreProfile.model_validate(dict(reversed(list(payload.items())))).content_hash == new.content_hash
    assert new.execution_eligibility == "BLOCKED"


def test_hash_tracks_new_math_and_tier_thresholds():
    profile = technical_profile_v1_1(candidate_calculation_v1())
    data = profile.model_dump()
    data["technical_semantics"]["price_weights_bps"] = (("return_3d", 3000), ("return_5d", 3000), ("return_10d", 4000))
    assert MomentumScoreProfile.model_validate(data).content_hash != profile.content_hash
    data = profile.model_dump()
    data["tiers"]["t1_bps"] = 600
    assert MomentumScoreProfile.model_validate(data).content_hash != profile.content_hash


def test_new_profile_exact_immutable_store_and_no_fallback(tmp_path):
    calculation = candidate_calculation_v1()
    old, new = candidate_technical_profile_v1(calculation), technical_profile_v1_1(calculation)
    store = MomentumCalculationStore(tmp_path)
    for artifact in (calculation, old, new, new):
        store.save(artifact)
    assert store.get_score_profile(old.identity).canonical_payload() == old.canonical_payload()
    assert store.get_score_profile(new.identity).canonical_payload() == new.canonical_payload()
    assert store.get_score_profile(new.identity.model_copy(update={"score_profile_version": "v0"})) is None
    changed = new.model_dump()
    changed["tiers"]["t1_bps"] = 600
    with pytest.raises(ValueError, match="semantic_collision"):
        store.save(MomentumScoreProfile.model_validate(changed))
    assert store.get_score_profile(new.identity).canonical_payload() == new.canonical_payload()


def test_helpers_reject_old_or_other_profile_no_auto_selection():
    data = inputs()
    old = candidate_technical_profile_v1(candidate_calculation_v1())
    with pytest.raises(ValueError, match="no_fallback"):
        validate_score_semantics(**(data | {"profile": old}))
    altered = data["profile"].model_copy(update={"score_profile_id": "fixture-price-only"})
    with pytest.raises(ValueError, match="no_fallback"):
        validate_score_semantics(**(data | {"profile": altered}))


def test_new_component_metadata_cannot_be_omitted():
    data = technical_profile_v1_1(candidate_calculation_v1()).model_dump()
    data["technical_semantics"] = None
    with pytest.raises(ValidationError, match="semantics_required"):
        MomentumScoreProfile.model_validate(data)


def test_profile_metadata_matches_pure_helper_constants():
    profile = technical_profile_v1_1(candidate_calculation_v1())
    assert dict(profile.technical_semantics.price_weights_bps) == {"return_3d": 2500, "return_5d": 3500, "return_10d": 4000}
    assert dict(profile.technical_semantics.breakout_points) == BREAKOUT_POINTS
    assert {component.component_key: component.weight_bps for component in profile.components} == {
        key: weight * 100 for key, weight in COMPONENT_WEIGHTS.items()}
    assert sum(component.weight_bps for component in profile.components) == 10000
    assert profile.redistribute_weights is False and profile.fallback_profile is None


@pytest.mark.parametrize("value", [-1, float("nan"), True])
def test_invalid_quantity_excluded_without_altering_cohort_math(value):
    data = inputs()
    first, *rest = data["candidates"]
    first = replace(first, values=first.values | {"volume_ratio_20": value})
    result = validate_score_semantics(**(data | {"candidates": (first, *rest)}))
    assert result.excluded["AAPL.US"] == ("volume_ratio_20_invalid_value",)
    assert all(set(values) == {"MSFT.US", "NVDA.US"} for values in result.percentiles.values())


def test_duplicate_or_nonmember_rejected():
    data = inputs()
    with pytest.raises(ValueError, match="ineligible_or_duplicate"):
        validate_score_semantics(**(data | {"candidates": (data["candidates"][0],) * 2}))
    other = replace(data["candidates"][0], symbol="OTHER.US")
    with pytest.raises(ValueError, match="ineligible_or_duplicate"):
        validate_score_semantics(**(data | {"candidates": (other,)}))


def test_cohort_calculation_profile_and_effective_time_are_exact():
    data = inputs()
    wrong = data["cohort"].model_copy(update={"calculation": data["cohort"].calculation.model_copy(update={"content_hash": "f" * 64})})
    with pytest.raises(ValueError, match="calculation_profile_conflict"):
        validate_score_semantics(**(data | {"cohort": wrong}))
    from datetime import date

    outside = data["cohort"].model_copy(update={"trading_date": date(2026, 10, 1)})
    with pytest.raises(ValueError, match="effective_period"):
        validate_score_semantics(**(data | {"cohort": outside}))


def test_snapshot_exact_profile_binding_compatible():
    from test_momentum_snapshots import fixture_record

    # The existing Snapshot identity carries ID/version/hash, without resolving defaults.
    record = fixture_record()
    data = record.model_dump()
    profile = technical_profile_v1_1(candidate_calculation_v1())
    data.update(calculation_id=profile.calculation.calculation_id,
                calculation_version=profile.calculation.calculation_version,
                calculation_content_hash=profile.calculation.content_hash,
                score_profile_id=profile.score_profile_id,
                score_profile_version=profile.score_profile_version,
                score_profile_content_hash=profile.content_hash)
    from app.services.momentum_snapshots import MomentumSnapshotRecord

    upgraded = MomentumSnapshotRecord.model_validate(data)
    assert upgraded.score_profile_content_hash == profile.content_hash
