"""Definition fixtures only: never calculate a metric, score, percentile or tier."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.services.momentum_calculation_contracts import (
    COMPARISON_KEYS,
    CalculationIdentity,
    MetricReference,
    MissingInputContract,
    MomentumCalculationDefinition,
    MomentumCalculationStore,
    MomentumRankingCohort,
    MomentumScoreProfile,
    ScoreProfileIdentity,
    candidate_calculation_v1,
    candidate_technical_profile_v1,
)
from app.services.momentum_universes import MomentumUniverseIdentity


def reference(calculation, key):
    metric = next(metric for metric in calculation.metrics if metric.metric_key == key)
    return MetricReference(metric_key=key, metric_version=metric.metric_version, content_hash=metric.content_hash)


def defined_fixture_profile(calculation):
    """Explicit test-only choices; NOT the missing production scoring decisions."""
    data = candidate_technical_profile_v1(calculation).model_dump()
    choices = {"price_strength": "return_5d", "volume_strength": "volume_ratio_20",
               "breakout": "breakout_20", "volatility_quality": "volatility_20"}
    data["score_profile_id"] = "fixture-technical"
    for component in data["components"]:
        component.update(metrics=(reference(calculation, choices[component["component_key"]]),),
                         aggregation="IDENTITY", direction="LOW" if component["component_key"] == "volatility_quality" else "HIGH",
                         definition_blockers=())
    data["required_metrics"] = tuple(reference(calculation, key) for key in (*choices.values(), "change_pct"))
    data["normalization"].update(version="fixture-percentile-v1", formula_semantics="(average_ordinal_rank - 1)/(N - 1)",
                                  singleton_policy="NEUTRAL_0_5")
    data["ranking"]["rank_method"] = "COMPETITION"
    data["definition_blockers"] = ()
    return MomentumScoreProfile.model_validate(data)


def cohort(calculation, profile):
    return MomentumRankingCohort(market="US", trading_date="2026-09-15",
        universe=MomentumUniverseIdentity(universe_id="fixture-us", universe_version="v1", content_hash="a" * 64, market="US"),
        input_contract_id="fixture-input", input_contract_version="v1",
        calculation=calculation.identity, score_profile=profile.identity)


def test_calculation_deterministic_order_and_round_trip():
    calculation = candidate_calculation_v1()
    data = calculation.model_dump(mode="json")
    data = dict(reversed(list(data.items())))
    data["metrics"].reverse()
    assert MomentumCalculationDefinition.model_validate(data).content_hash == calculation.content_hash
    assert MomentumCalculationDefinition.model_validate_json(calculation.model_dump_json()) == calculation
    assert calculation.definition_status == "DEFINED"
    assert calculation.execution_eligibility == "BLOCKED"
    assert calculation.to_dict()["definition_status"] == "DEFINED"
    assert all(metric["content_hash"] for metric in calculation.to_dict()["metrics"])


@pytest.mark.parametrize("change", [
    {"formula_semantics": "fixture alternative formula metadata"},
    {"required_history_sessions": 99},
    {"price_basis_requirement": "NOT_REQUIRED"},
    {"metric_version": "fixture-v2"},
    {"required_inputs": ("close", "high")},
])
def test_metric_semantics_and_dependency_changes_hash(change):
    calculation = candidate_calculation_v1()
    data = calculation.model_dump()
    data["metrics"][0].update(change)
    changed = MomentumCalculationDefinition.model_validate(data)
    assert changed.metrics[0].content_hash != calculation.metrics[0].content_hash
    assert changed.content_hash != calculation.content_hash


def test_frozen_session_math_metadata():
    metrics = {metric.metric_key: metric for metric in candidate_calculation_v1().metrics}
    assert metrics["return_3d"].required_history_sessions == 4
    assert metrics["return_5d"].required_history_sessions == 6
    assert metrics["return_10d"].required_history_sessions == 11
    assert "C_D / C_(D-5) - 1" in metrics["return_5d"].formula_semantics
    assert metrics["breakout_60"].required_history_sessions == 61
    assert metrics["breakout_60"].required_inputs == ("close", "high")
    assert "C_D > max" in metrics["breakout_20"].formula_semantics
    assert "H_D > max" in metrics["high_break_20"].formula_semantics
    volatility = metrics["volatility_20"]
    assert volatility.required_history_sessions == 21
    assert "ddof=1" in volatility.formula_semantics and "not annualized" in volatility.formula_semantics
    assert metrics["volume_ratio_20"].required_history_sessions == 21
    assert "exclude D" in metrics["volume_ratio_20"].formula_semantics
    assert metrics["consecutive_up_days"].required_history_sessions is None
    assert metrics["volatility_status"].output_type == "QUALITY_STATUS"


def test_vr20_defined_is_not_executable():
    calculation = candidate_calculation_v1()
    vr20 = next(metric for metric in calculation.metrics if metric.metric_key == "volume_ratio_20")
    assert vr20.definition_status == "DEFINED"
    assert vr20.volume_semantics_requirement == "COMPARABLE_CORPORATE_ACTION_QUANTITY"
    assert calculation.execution_eligibility == "BLOCKED"
    with pytest.raises(ValidationError):
        MomentumCalculationDefinition.model_validate(calculation.model_dump() | {"execution_eligibility": "READY"})


def test_missing_input_contract_null_and_no_fill():
    calculation = candidate_calculation_v1()
    original = calculation.metrics[0].missing_input
    assert original.result_value is None and original.missing_status == "UNAVAILABLE"
    assert original.invalid_contract_status == "BLOCKED" and original.partial_input_status == "PARTIAL"
    for field in ("fill_zero", "forward_fill", "backward_fill", "skip_sessions", "switch_provider", "switch_adjustment", "shorten_lookback"):
        with pytest.raises(ValidationError):
            MissingInputContract.model_validate(original.model_dump() | {field: True})
    changed = calculation.model_dump()
    changed["metrics"][0]["missing_input"]["missing_status"] = "BLOCKED"
    assert MomentumCalculationDefinition.model_validate(changed).content_hash != calculation.content_hash


def test_technical_candidate_weights_and_unresolved_definition():
    profile = candidate_technical_profile_v1(candidate_calculation_v1())
    assert {component.component_key: component.weight_bps for component in profile.components} == {
        "price_strength": 4000, "volume_strength": 2500, "breakout": 2000, "volatility_quality": 1500}
    assert profile.definition_status == "BLOCKED"
    assert profile.execution_eligibility == "BLOCKED"
    assert profile.normalization.formula_semantics is None
    assert profile.ranking.rank_method is None
    with pytest.raises(ValidationError, match="requires_blockers"):
        MomentumScoreProfile.model_validate(profile.model_dump() | {"definition_blockers": ()})
    with pytest.raises(ValidationError):
        MomentumScoreProfile.model_validate(profile.model_dump() | {"execution_eligibility": "READY"})


def test_score_profile_deterministic_hash():
    profile = defined_fixture_profile(candidate_calculation_v1())
    data = dict(reversed(list(profile.model_dump().items())))
    data["components"] = tuple(reversed(data["components"]))
    data["required_metrics"] = tuple(reversed(data["required_metrics"]))
    assert MomentumScoreProfile.model_validate(data).content_hash == profile.content_hash
    assert MomentumScoreProfile.model_validate_json(profile.model_dump_json()) == profile
    assert profile.definition_status == "DEFINED" and profile.execution_eligibility == "BLOCKED"
    assert profile.to_dict()["definition_status"] == "DEFINED"


@pytest.mark.parametrize("change", ["weight", "normalization", "tier", "rank", "missing"])
def test_profile_semantic_changes_hash(change):
    profile = defined_fixture_profile(candidate_calculation_v1())
    data = profile.model_dump()
    if change == "weight":
        data["components"][0]["weight_bps"] += 1
        data["components"][1]["weight_bps"] -= 1
    elif change == "normalization":
        data["normalization"]["singleton_policy"] = "BLOCKED"
    elif change == "tier":
        data["tiers"]["t1_bps"] = 600
    elif change == "rank":
        data["ranking"]["rank_method"] = "DENSE"
    else:
        data["missing_required_status"] = "BLOCKED"
    assert MomentumScoreProfile.model_validate(data).content_hash != profile.content_hash


@pytest.mark.parametrize("field,value", [("redistribute_weights", True), ("missing_as_zero", True),
                                        ("mean_available_components", True), ("missing_required_score", 0),
                                        ("fallback_profile", "momentum-price-only-v1")])
def test_missing_components_do_not_enable_fallback(field, value):
    profile = defined_fixture_profile(candidate_calculation_v1())
    assert profile.missing_required_score is None
    with pytest.raises(ValidationError):
        MomentumScoreProfile.model_validate(profile.model_dump() | {field: value})


def test_weights_and_metric_identity_contracts():
    profile = defined_fixture_profile(candidate_calculation_v1())
    data = profile.model_dump()
    data["components"][0]["weight_bps"] = 1
    with pytest.raises(ValidationError, match="weights_must_sum"):
        MomentumScoreProfile.model_validate(data)
    data = profile.model_dump()
    data["required_metrics"] = ()
    with pytest.raises(ValidationError, match="must_be_required"):
        MomentumScoreProfile.model_validate(data)


def test_store_empty_idempotent_collision_and_revision(tmp_path):
    store = MomentumCalculationStore(tmp_path)
    calculation = candidate_calculation_v1()
    profile = defined_fixture_profile(calculation)
    assert store.get_calculation(calculation.identity) is None
    assert store.get_score_profile(profile.identity) is None
    assert not store.path.exists()
    with pytest.raises(ValueError, match="calculation_dependency_missing"):
        store.save(profile)
    assert not store.path.exists()
    store.save(calculation)
    store.save(profile)
    before = store.path.read_bytes()
    store.save(calculation)
    store.save(profile)
    assert before == store.path.read_bytes()
    assert store.get_calculation(calculation.identity).identity == calculation.identity
    assert store.get_score_profile(profile.identity).identity == profile.identity
    data = calculation.model_dump()
    data["metrics"][0]["formula_semantics"] = "fixture changed semantic content"
    changed = MomentumCalculationDefinition.model_validate(data)
    with pytest.raises(ValueError, match="semantic_collision"):
        store.save(changed)
    changed = MomentumCalculationDefinition.model_validate(data | {"calculation_version": "v2"})
    store.save(changed)
    assert store.get_calculation(calculation.identity) is not None
    assert store.get_calculation(changed.identity) is not None


def test_exact_profile_dependency_and_cohort_resolution(tmp_path):
    store = MomentumCalculationStore(tmp_path)
    calculation = candidate_calculation_v1()
    profile = defined_fixture_profile(calculation)
    store.save(calculation)
    store.save(profile)
    group = cohort(calculation, profile)
    assert store.resolve_cohort_contracts(group)["binding_status"] == "EXACT"
    assert store.resolve_cohort_contracts(group)["execution_eligibility"] == "BLOCKED"
    wrong = CalculationIdentity.model_validate(calculation.identity.model_dump() | {"content_hash": "b" * 64})
    group = MomentumRankingCohort.model_validate(group.model_dump() | {"calculation": wrong})
    assert store.resolve_cohort_contracts(group)["binding_status"] == "BLOCKED"
    data = profile.model_dump()
    data["required_metrics"][0]["content_hash"] = "c" * 64
    # Preserve declaration consistency to exercise stored calculation-to-metric binding.
    for component in data["components"]:
        if component["metrics"][0]["metric_key"] == data["required_metrics"][0]["metric_key"]:
            component["metrics"][0]["content_hash"] = "c" * 64
    with pytest.raises(ValueError, match="exact_metric_dependency_conflict"):
        store.save(MomentumScoreProfile.model_validate(data))


@pytest.mark.parametrize("dimension", ["market", "trading_date", "universe", "input_contract_id", "input_contract_version", "calculation", "score_profile"])
def test_ranking_requires_every_exact_cohort_dimension(dimension):
    calculation = candidate_calculation_v1()
    data = cohort(calculation, defined_fixture_profile(calculation)).model_dump()
    data.pop(dimension)
    with pytest.raises(ValidationError):
        MomentumRankingCohort.model_validate(data)


def test_no_cross_market_or_missing_comparison_dimensions():
    calculation = candidate_calculation_v1()
    profile = defined_fixture_profile(calculation)
    with pytest.raises(ValidationError, match="market_conflict"):
        MomentumRankingCohort.model_validate(cohort(calculation, profile).model_dump() | {"market": "HK"})
    data = profile.model_dump()
    data["ranking"]["exact_comparison_keys"] = tuple(key for key in COMPARISON_KEYS if key != "universe_content_hash")
    with pytest.raises(ValidationError, match="ranking_dimensions_required"):
        MomentumScoreProfile.model_validate(data)
    assert profile.ranking.symbol_tiebreak == "DISPLAY_ONLY_NEVER_SCORE_OR_RANK"
    assert profile.tiers.same_score_same_tier
    assert profile.tiers.t1_bps == 500 and profile.tiers.t2_bps == 2000


@pytest.mark.parametrize("version", ["latest", "nearest", "v999"])
def test_no_latest_or_price_only_auto_selection(tmp_path, version):
    calculation = candidate_calculation_v1()
    profile = defined_fixture_profile(calculation)
    store = MomentumCalculationStore(tmp_path)
    store.save(calculation)
    store.save(profile)
    if version == "latest":
        with pytest.raises(ValidationError):
            CalculationIdentity.model_validate(calculation.identity.model_dump() | {"calculation_version": version})
    else:
        assert store.get_calculation(CalculationIdentity.model_validate(calculation.identity.model_dump() | {"calculation_version": version})) is None
    requested = ScoreProfileIdentity(score_profile_id="momentum-price-only-v1", score_profile_version="v1", content_hash=profile.content_hash)
    assert store.get_score_profile(requested) is None


def test_concurrent_insert_and_aware_storage_time(tmp_path):
    store = MomentumCalculationStore(tmp_path)
    calculation = candidate_calculation_v1()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: store.save(calculation), range(4)))
    with sqlite3.connect(store.path) as db:
        rows = db.execute("SELECT stored_at FROM definitions").fetchall()
    assert len(rows) == 1 and datetime.fromisoformat(rows[0][0]).utcoffset() == UTC.utcoffset(None)
    with pytest.raises(ValidationError):
        calculation.metrics[0].formula_semantics = "changed"
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE definitions SET payload=replace(payload, 'momentum-daily', 'tampered')")
    with pytest.raises(ValueError, match="hash_conflict"):
        store.get_calculation(calculation.identity)


def test_metadata_never_calls_an_engine(monkeypatch):
    from app.factors.engine import MarketFactorEngine

    def forbidden(*args, **kwargs):
        pytest.fail("contract metadata must not calculate")
    monkeypatch.setattr(MarketFactorEngine, "compute", forbidden)
    calculation = candidate_calculation_v1()
    assert len(calculation.metrics) == 12
    assert candidate_technical_profile_v1(calculation).execution_eligibility == "BLOCKED"
    assert json.loads(calculation.canonical_payload())["metrics"]


def test_independently_selected_price_only_fixture_still_execution_blocked(tmp_path):
    calculation = candidate_calculation_v1()
    data = defined_fixture_profile(calculation).model_dump()
    data["score_profile_id"] = "fixture-price-only"
    component = data["components"][0]
    component["weight_bps"] = 10000
    data["components"] = (component,)
    data["required_metrics"] = (reference(calculation, "return_5d"), reference(calculation, "change_pct"))
    price_only = MomentumScoreProfile.model_validate(data)
    assert price_only.definition_status == "DEFINED"
    assert price_only.execution_eligibility == "BLOCKED"
    assert price_only.identity != defined_fixture_profile(calculation).identity
    store = MomentumCalculationStore(tmp_path)
    store.save(calculation)
    store.save(price_only)
    assert store.get_score_profile(defined_fixture_profile(calculation).identity) is None


def test_profile_semantic_collision_and_read_only_metadata_queries(tmp_path):
    calculation = candidate_calculation_v1()
    profile = defined_fixture_profile(calculation)
    store = MomentumCalculationStore(tmp_path)
    store.save(calculation)
    store.save(profile)
    data = profile.model_dump()
    data["tiers"]["t1_bps"] = 600
    with pytest.raises(ValueError, match="semantic_collision"):
        store.save(MomentumScoreProfile.model_validate(data))
    before = store.path.read_bytes()
    assert store.get_score_profile(profile.identity).tiers.t1_bps == 500
    assert store.resolve_cohort_contracts(cohort(calculation, profile))["binding_status"] == "EXACT"
    assert store.path.read_bytes() == before
