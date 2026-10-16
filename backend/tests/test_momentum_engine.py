"""Private arithmetic core fixtures, not public Gate-approved or production inputs."""
import math
import statistics
from datetime import UTC, date, datetime, time, timedelta

import pytest
from pydantic import ValidationError
from test_momentum_snapshots import fixture_record
from test_momentum_universes import member, ready

from app.services.evidence_execution import TradingCalendarContract
from app.services.momentum_calculation_contracts import (
    MomentumCalculationDefinition,
    MomentumCalculationStore,
    MomentumRankingCohort,
    calculation_with_trend_v1_1,
    candidate_calculation_v1,
    candidate_technical_profile_v1,
    technical_profile_v1_1,
    technical_profile_v1_2,
)
from app.services.momentum_engine import (
    DailyBar,
    MomentumTrendSnapshotCandidate,
    ValidatedDailyInput,
    VolatilityTrendResult,
    volatility_trend,
)
from app.services.momentum_engine import (
    _calculate_metrics as calculate_metrics,
)
from app.services.momentum_engine import (
    _calculate_momentum as calculate_momentum,
)
from app.services.momentum_snapshots import (
    MetricEvidence,
    MomentumIdentity,
    MomentumSnapshotRecord,
    MomentumSnapshotStore,
)


def fixture_inputs(extended=True, market="US"):
    calculation = calculation_with_trend_v1_1() if extended else candidate_calculation_v1()
    profile = technical_profile_v1_2(calculation) if extended else technical_profile_v1_1(calculation)
    calendar = TradingCalendarContract.from_canonical(market)
    symbol = "AAPL.US" if market == "US" else "700.HK"
    universe = ready(market=market, members=(member(symbol, market=market),), expected_count=1,
                     effective_count=1, excluded_count=0)
    cohort = MomentumRankingCohort(market=market, trading_date=date(2026, 9, 16), universe=universe.identity,
        input_contract_id="synthetic-input", input_contract_version="v1", calculation=calculation.identity,
        score_profile=profile.identity)
    days = []
    day = date(2026, 1, 1)
    while day <= cohort.trading_date:
        if day.weekday() in calendar.trading_weekdays and day not in calendar.holidays:
            days.append(day)
        day += timedelta(days=1)
    days = days[-80:]
    bars = tuple(DailyBar(trading_date=day, close=100 + max(index - 1, 0), high=101 + max(index - 1, 0),
        volume=200 if index == 79 else 100, available_at=datetime.combine(day, time(23), UTC),
        finality_status="READY", finality_reference="synthetic-finality", evidence_reference=f"synthetic-bar-{day}")
        for index, day in enumerate(days))
    identity = MomentumIdentity(symbol=symbol, market=market, trading_date=cohort.trading_date,
        input_contract_id=cohort.input_contract_id, input_contract_version=cohort.input_contract_version,
        calculation_id=calculation.calculation_id, calculation_version=calculation.calculation_version,
        calculation_content_hash=calculation.content_hash, calendar_id=calendar.calendar_id,
        calendar_version=calendar.version, calendar_content_hash=calendar.content_hash,
        universe_id=universe.universe_id, universe_version=universe.universe_version, universe_content_hash=universe.content_hash,
        score_profile_id=profile.score_profile_id, score_profile_version=profile.score_profile_version,
        score_profile_content_hash=profile.content_hash)
    data = ValidatedDailyInput(identity=identity, bars=bars, generated_at=datetime(2026, 9, 17, tzinfo=UTC),
        knowledge_cutoff=datetime(2026, 9, 16, 23, 30, tzinfo=UTC), source="synthetic-test-only",
        input_references=("synthetic-contract-proof",), price_basis="SPLIT_ADJUSTED_PRICE_ONLY", price_status="READY",
        volume_unit="synthetic-shares-comparable", quantity_status="READY", pit_status="READY", source_vintage="synthetic-vintage")
    return data, calculation, profile, calendar, universe, cohort


def metrics(data=None, **changes):
    original, calculation, _, calendar, _, _ = fixture_inputs()
    data = original if data is None else data
    return {r.identity.metric_key: r for r in calculate_metrics(data.model_copy(update=changes), calculation, calendar)}


@pytest.mark.parametrize("n", [3, 5, 10])
def test_exact_session_returns(n):
    data, *_ = fixture_inputs()
    result = metrics(data)[f"return_{n}d"]
    assert result.value == pytest.approx(data.bars[-1].close / data.bars[-n - 1].close - 1)
    assert result.evidence.status == "READY"


def test_change_and_consecutive_termination():
    data, *_ = fixture_inputs()
    result = metrics(data)
    assert result["consecutive_up_days"].value == 78
    assert result["change_pct"].value == pytest.approx(178 / 177 - 1)
    for end in (177, 176):
        changed = (*data.bars[:-1], data.bars[-1].model_copy(update={"close": end}))
        assert metrics(data, bars=changed)["consecutive_up_days"].value == 0


def test_missing_session_not_skipped_and_insufficient_history():
    data, *_ = fixture_inputs()
    missing = data.bars[:-3] + data.bars[-2:]
    assert metrics(data, bars=missing)["return_3d"].value is None
    assert metrics(data, bars=missing)["consecutive_up_days"].value is None
    assert "required_session_bar_missing" in metrics(data, bars=missing)["return_3d"].evidence.blockers
    assert metrics(data, bars=data.bars[-3:])["return_3d"].value is None


def test_volume_excludes_today_and_zero_missing_blocked():
    data, *_ = fixture_inputs()
    assert metrics(data)["volume_ratio_20"].value == 2
    bars = tuple(bar.model_copy(update={"volume": 0}) for bar in data.bars[:-1]) + data.bars[-1:]
    assert "volume_denominator_zero" in metrics(data, bars=bars)["volume_ratio_20"].evidence.blockers
    bars = (*data.bars[:-2], data.bars[-2].model_copy(update={"volume": None}), data.bars[-1])
    assert metrics(data, bars=bars)["volume_ratio_20"].value is None
    blocked = metrics(data, quantity_status="BLOCKED")["volume_ratio_20"]
    assert blocked.value is None and blocked.evidence.status == "BLOCKED"


@pytest.mark.parametrize("key", ["breakout_20", "breakout_60", "high_break_20", "high_break_60"])
def test_breakout_strict_high_window_excludes_current(key):
    data, *_ = fixture_inputs()
    prior_high = max(bar.high for bar in data.bars[-61:-1])
    high = key.startswith("high_break")
    field = "high" if high else "close"
    for value, expected in ((prior_high + 1, True), (prior_high, False), (prior_high - 1, False)):
        last = data.bars[-1].model_copy(update={field: value})
        assert metrics(data, bars=(*data.bars[:-1], last))[key].value is expected
    assert metrics(data, bars=data.bars[-20:])[key].value is None


def test_sigma_sample_std_nonannualized():
    data, *_ = fixture_inputs()
    closes = [bar.close for bar in data.bars[-21:]]
    returns = [math.log(closes[i + 1] / closes[i]) for i in range(20)]
    result = metrics(data)["volatility_20"]
    assert result.value == statistics.stdev(returns)
    assert result.value != statistics.pstdev(returns)
    assert metrics(data)["volatility_status"].value == "READY"


@pytest.mark.parametrize("current,previous,expected", [(2, 1, "EXPANDING"), (1, 2, "CONTRACTING"), (1, 1, "UNCHANGED"),
    (1.0000000000000002, 1, "EXPANDING")])
def test_trend_strict_no_tolerance(current, previous, expected):
    result = volatility_trend(current, previous, current_status="READY", previous_status="READY",
                              evidence_refs=("synthetic-sigma",), sessions_complete=True)
    assert result.value == expected and result.evidence.status == "READY"


@pytest.mark.parametrize("current,previous,complete,reason", [(None, 1, True, "current_sigma_missing"),
    (1, None, True, "previous_sigma_missing"), (1, 1, False, "trend_required_session_missing")])
def test_missing_trend_never_unchanged(current, previous, complete, reason):
    result = volatility_trend(current, previous, current_status="READY", previous_status="READY",
                              evidence_refs=("synthetic-sigma",), sessions_complete=complete)
    assert result.value is None and reason in result.evidence.blockers


@pytest.mark.parametrize("kind,expected", [("expanding", "EXPANDING"), ("contracting", "CONTRACTING"), ("unchanged", "UNCHANGED")])
def test_trend_from_two_contiguous_sigma_windows(kind, expected):
    data, *_ = fixture_inputs()
    bars = list(data.bars[-22:])
    for index, bar in enumerate(bars):
        close = 200 if (kind == "expanding" and index == 21) or (kind == "contracting" and index == 0) else 100
        bars[index] = bar.model_copy(update={"close": close})
    result = metrics(data, bars=tuple(bars))
    assert result["volatility_trend_status"].value == expected
    assert result["volatility_status"].value == "READY"


def test_21_sessions_sigma_ready_but_trend_unavailable():
    data, *_ = fixture_inputs()
    result = metrics(data, bars=data.bars[-21:])
    assert result["volatility_20"].evidence.status == "READY"
    assert result["volatility_status"].value == "READY"
    assert result["volatility_trend_status"].value is None
    assert "previous_sigma_missing" in result["volatility_trend_status"].evidence.blockers


@pytest.mark.parametrize("changes", [{"price_basis": "UNKNOWN"}, {"price_status": "BLOCKED"},
    {"pit_status": "BLOCKED"}, {"source_vintage": None}])
def test_unproven_inputs_not_upgraded(changes):
    result = metrics(**changes)
    assert result["return_5d"].value is None and result["return_5d"].evidence.status == "BLOCKED"
    assert result["volatility_status"].value == "BLOCKED"
    assert result["volatility_trend_status"].value is None


def test_quality_and_trend_enum_separation():
    with pytest.raises(ValidationError):
        VolatilityTrendResult(value="READY", evidence=MetricEvidence(metric="volatility_trend_status", status="READY", evidence_refs=("fixture",)))
    with pytest.raises(ValidationError):
        fixture_record(volatility_status="EXPANDING")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_input_rejected(value):
    data, *_ = fixture_inputs()
    payload = data.bars[0].model_dump() | {"close": value}
    with pytest.raises(ValidationError):
        DailyBar.model_validate(payload)


def test_naive_availability_and_generated_time_rejected():
    data, *_ = fixture_inputs()
    with pytest.raises(ValidationError):
        DailyBar.model_validate(data.bars[0].model_dump() | {"available_at": datetime(2026, 9, 16)})
    with pytest.raises(ValidationError):
        ValidatedDailyInput.model_validate(data.model_dump() | {"generated_at": datetime(2026, 9, 17)})


@pytest.mark.parametrize("field", ["calendar_content_hash", "calendar_version", "calculation_id", "calculation_content_hash"])
def test_wrong_identity_rejected(field):
    data, calculation, _, calendar, *_ = fixture_inputs()
    altered = data.identity.model_copy(update={field: "f" * 64 if "hash" in field else "wrong"})
    with pytest.raises(ValueError, match="binding_required"):
        calculate_metrics(data.model_copy(update={"identity": altered}), calculation, calendar)


def test_finality_and_future_availability_gates():
    data, *_ = fixture_inputs()
    for changes in ({"finality_status": "PARTIAL"}, {"available_at": None},
                    {"available_at": datetime(2026, 9, 18, tzinfo=UTC)}):
        bars = (*data.bars[:-1], data.bars[-1].model_copy(update=changes))
        result = metrics(data, bars=bars)["change_pct"]
        assert result.value is None and result.evidence.status == "BLOCKED"


def test_versions_golden_hashes_and_exact_store(tmp_path):
    old = candidate_calculation_v1()
    assert old.content_hash == "05acb22677f4fc9148916ba5c7b1c012ea15c556befbaa51a422bfa5d21e6a09"
    assert candidate_technical_profile_v1(old).content_hash == "be55cfbab6d46a03797b883922209b9e7d2afb2d63893830d0ddb922d7e1c35c"
    assert technical_profile_v1_1(old).content_hash == "03701dc8d08cb15c9640c11df3ad5c47fcc6ced812172860612046da02ca0369"
    new = calculation_with_trend_v1_1()
    assert new.content_hash != old.content_hash
    assert new.metrics[:-1] == old.metrics
    payload = new.model_dump()
    payload["metrics"] = tuple(reversed(payload["metrics"]))
    assert MomentumCalculationDefinition.model_validate(payload).content_hash == new.content_hash
    store = MomentumCalculationStore(tmp_path)
    for artifact in (old, technical_profile_v1_1(old), new, technical_profile_v1_2(new)):
        store.save(artifact)
    assert store.get_calculation(old.identity).identity == old.identity
    assert store.get_calculation(new.identity).identity == new.identity


def run(extended=True, market="US", **changes):
    data, calculation, profile, calendar, universe, cohort = fixture_inputs(extended, market)
    data = data.model_copy(update=changes)
    return calculate_momentum(inputs=(data,), calculation=calculation, profile=profile,
        calendar=calendar, universe=universe, cohort=cohort)


@pytest.mark.parametrize("market", ["HK", "US"])
def test_end_to_end_fixture_and_new_snapshot_binding(market):
    base, extended = run(False, market), run(True, market)
    a, b = base.snapshots[0], extended.snapshots[0]
    assert type(a) is MomentumSnapshotRecord and isinstance(b, MomentumTrendSnapshotCandidate)
    assert a.calculation_version == "v1" and b.calculation_version == "v1.1"
    assert a.snapshot_id != b.snapshot_id and a.logical_key != b.logical_key
    assert b.volatility_status == "READY" and b.volatility_trend_status in {"EXPANDING", "CONTRACTING", "UNCHANGED"}
    assert a.strength_score == b.strength_score and a.rank == b.rank and a.tier == b.tier
    assert extended.scoring.scores == base.scoring.scores
    assert extended.production_execution == "BLOCKED"
    assert extended.expected_count == extended.valid_count == 1 and extended.excluded_count == 0
    assert MomentumTrendSnapshotCandidate.model_validate_json(b.model_dump_json()).snapshot_id == b.snapshot_id
    with pytest.raises(ValidationError):
        MomentumSnapshotRecord.model_validate(b.model_dump())


def test_no_old_snapshot_store_write_path_added(tmp_path):
    snapshot = run().snapshots[0]
    store = MomentumSnapshotStore(tmp_path)
    with pytest.raises(ValidationError):
        store.save(snapshot)
    assert not store.path.exists()


def test_blocked_volume_no_reweight_or_score():
    result = run(quantity_status="BLOCKED")
    snapshot = result.snapshots[0]
    assert snapshot.volume_ratio_20 is None and snapshot.strength_score is None and snapshot.rank is None
    assert snapshot.overall_status == "BLOCKED"
    assert result.valid_count == 0 and result.excluded_count == 1


def test_mixed_profile_rejected():
    data, calculation, _profile, calendar, universe, cohort = fixture_inputs()
    wrong = technical_profile_v1_1(candidate_calculation_v1())
    with pytest.raises(ValueError, match="binding_conflict"):
        calculate_momentum(inputs=(data,), calculation=calculation, profile=wrong, calendar=calendar, universe=universe, cohort=cohort)


def test_missing_vintage_downgrades_candidate_without_relabeling_availability():
    result = run(source_vintage=None)
    assert result.snapshots[0].pit_status == "BLOCKED"
    assert result.snapshots[0].overall_status == "BLOCKED"
    assert result.snapshots[0].strength_score is None
    assert result.snapshots[0].available_at is None


def test_extreme_finite_prices_return_explicit_nonfinite_result():
    data, *_ = fixture_inputs()
    bars = (*data.bars[:-2], data.bars[-2].model_copy(update={"close": 1e-308}), data.bars[-1].model_copy(update={"close": 1e308}))
    result = metrics(data, bars=bars)
    assert result["change_pct"].value is None
    assert result["change_pct"].evidence.status == "BLOCKED"
    assert result["volatility_20"].value is None


def test_evidence_refs_cover_used_window_and_finality_only():
    data, *_ = fixture_inputs()
    result = metrics(data)["return_3d"]
    assert "synthetic-finality" in result.evidence.evidence_refs
    assert data.bars[-4].evidence_reference in result.evidence.evidence_refs
    assert data.bars[-5].evidence_reference not in result.evidence.evidence_refs


def test_trend_does_not_affect_score_eligibility():
    data, calculation, profile, calendar, universe, cohort = fixture_inputs()
    # D-21 close belongs only to the previous sigma window. Its high remains
    # available for B60; all nine scoring inputs can still be READY.
    bars = list(data.bars)
    bars[-22] = bars[-22].model_copy(update={"close": None})
    series = data.model_copy(update={"bars": tuple(bars)})
    result = calculate_momentum(inputs=(series,), calculation=calculation, profile=profile,
        calendar=calendar, universe=universe, cohort=cohort)
    assert result.valid_count == 1 and result.snapshots[0].strength_score is not None
    assert result.snapshots[0].volatility_trend_status is None
    assert result.snapshots[0].volatility_status == "READY"


def test_wrong_market_and_non_session_bar_rejected():
    data, calculation, _, calendar, *_ = fixture_inputs()
    with pytest.raises(ValidationError, match="symbol_market_conflict"):
        ValidatedDailyInput.model_validate(data.model_dump() | {"identity": data.identity.model_dump() | {"market": "HK"}})
    future = data.bars[-1].model_copy(update={"trading_date": date(2026, 9, 17)})
    with pytest.raises(ValueError, match="non_session_or_future_bar"):
        calculate_metrics(data.model_copy(update={"bars": (*data.bars, future)}), calculation, calendar)


def test_previous_sigma_availability_not_masked_by_current_sigma_ready():
    data, calculation, profile, calendar, universe, cohort = fixture_inputs()
    bars = list(data.bars)
    bars[-22] = bars[-22].model_copy(update={"available_at": None})
    result = calculate_momentum(inputs=(data.model_copy(update={"bars": tuple(bars)}),), calculation=calculation,
        profile=profile, calendar=calendar, universe=universe, cohort=cohort)
    snapshot = result.snapshots[0]
    assert snapshot.volatility_status == "READY" and snapshot.volatility_trend_status is None
    assert snapshot.pit_status == "BLOCKED" and snapshot.available_at is None
    assert "input_availability_unproven" in snapshot.blockers
