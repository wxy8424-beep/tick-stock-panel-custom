"""Synthetic test-only evidence. Never vendor facts, production rows or fetching."""
from datetime import datetime, timedelta
from itertools import pairwise

import pytest
from pydantic import ValidationError
from test_momentum_engine import fixture_inputs

from app.services import momentum_engine as engine
from app.services.momentum_calculation_contracts import (
    calculation_with_trend_v1_1,
    candidate_calculation_v1,
    candidate_technical_profile_v1,
    technical_profile_v1_1,
    technical_profile_v1_2,
)
from app.services.momentum_input_gate import (
    MomentumDailyInput,
    MomentumGateRequest,
    MomentumInputGateContract,
    open_gated_input,
    validate_momentum_daily_input,
    validate_momentum_history_window,
)


def gate_fixture(market="US", extended=True):
    data, calculation, profile, calendar, universe, cohort = fixture_inputs(extended, market)
    gate = MomentumInputGateContract()
    identity = data.identity.model_copy(update={"input_contract_id": gate.contract_id, "input_contract_version": gate.version})
    request = MomentumGateRequest(identity=identity, calculation=calculation, calendar=calendar, universe=universe,
        generated_at=data.generated_at, knowledge_cutoff=data.knowledge_cutoff,
        evaluation_boundary=data.knowledge_cutoff, mode="SYNTHETIC_TEST")
    rows = tuple(MomentumDailyInput(symbol=identity.symbol, market=market, instrument_type="COMMON_STOCK",
        trading_date=bar.trading_date, timezone=calendar.timezone, timestamp=engine._close(calendar, bar.trading_date),
        knowledge_cutoff=request.knowledge_cutoff, available_at=bar.available_at, fetched_at=request.generated_at,
        calendar_id=calendar.calendar_id, calendar_version=calendar.version, calendar_content_hash=calendar.content_hash,
        open=bar.close, high=bar.high, low=bar.close * .99, close=bar.close,
        prev_close=data.bars[index - 1].close if index else None,
        price_basis="SPLIT_ADJUSTED_PRICE_ONLY", adjustment_method="SPLIT_ONLY", adjustment_version="synthetic-actions-v1",
        price_basis_reference="synthetic-split-only-evidence", volume=bar.volume, turnover=None,
        volume_unit="synthetic-comparable-shares", volume_semantics="COMPARABLE_CORPORATE_ACTION_QUANTITY",
        quantity_reference="synthetic-quantity-proof", currency="USD" if market == "US" else "HKD",
        bar_final=True, finality_source="synthetic-finality-source", finality_reference=bar.finality_reference,
        finality_verified_at=engine._close(calendar, bar.trading_date) + timedelta(minutes=1),
        source="synthetic-test-only", source_version="synthetic-v1", source_vintage=data.source_vintage,
        vintage_reference="synthetic-vintage-proof", availability_reference="synthetic-availability-proof",
        input_reference=bar.evidence_reference, data_kind="DAILY_OHLCV", origin="SYNTHETIC_TEST")
        for index, bar in enumerate(data.bars))
    cohort = cohort.model_copy(update={"input_contract_id": gate.contract_id, "input_contract_version": gate.version})
    return rows, request, profile, cohort


def altered(row, **changes):
    return row.model_dump() | changes


@pytest.mark.parametrize("market", ["HK", "US"])
def test_daily_and_complete_exact_window_ready(market):
    rows, request, *_ = gate_fixture(market)
    daily = validate_momentum_daily_input(rows[-1], request)
    assert daily.overall_status == "READY"
    with pytest.raises(ValueError, match="not_ready"):
        daily.accepted_input()
    result = validate_momentum_history_window(rows, request)
    assert result.overall_status == "READY" and not result.blockers
    assert result.production_execution == "BLOCKED"
    assert result.accepted_input().validated_input.identity.market == market


@pytest.mark.parametrize("changes,reason", [
    ({"market": "HK"}, "symbol_market_identity_conflict"),
    ({"symbol": "OTHER.US"}, "symbol_market_identity_conflict"),
    ({"instrument_type": "ETF"}, "instrument_not_eligible"),
    ({"instrument_type": "UNKNOWN"}, "instrument_not_eligible"),
    ({"calendar_version": "wrong"}, "calendar_binding_conflict"),
    ({"calendar_content_hash": "f" * 64}, "calendar_binding_conflict"),
    ({"session_index": -1}, "invalid_or_future_session"),
    ({"timezone": "UTC"}, "calendar_binding_conflict"),
    ({"high": 1}, "ohlc_missing_or_inconsistent"),
    ({"low": 9999}, "ohlc_missing_or_inconsistent"),
    ({"open": None}, "ohlc_missing_or_inconsistent"),
    ({"close": 0}, "ohlc_missing_or_inconsistent"),
    ({"price_basis": "RAW"}, "split_only_price_basis_unproven"),
    ({"price_basis": "OTHER_ADJUSTED"}, "split_only_price_basis_unproven"),
    ({"price_basis_reference": None}, "split_only_price_basis_unproven"),
    ({"adjustment_method": "UNKNOWN"}, "adjustment_semantics_unproven"),
    ({"adjustment_version": None}, "adjustment_semantics_unproven"),
    ({"volume_unit": "UNKNOWN"}, "quantity_semantics_unproven"),
    ({"volume_semantics": "RAW_QUANTITY"}, "quantity_semantics_unproven"),
    ({"quantity_reference": None}, "quantity_semantics_unproven"),
    ({"currency": None}, "quantity_semantics_unproven"),
    ({"volume": None}, "volume_missing_or_invalid"),
    ({"volume": -1}, "volume_missing_or_invalid"),
    ({"bar_final": None}, "completed_daily_finality_unproven"),
    ({"bar_final": False}, "completed_daily_finality_unproven"),
    ({"finality_reference": None}, "completed_daily_finality_unproven"),
    ({"finality_verified_at": None}, "completed_daily_finality_unproven"),
    ({"available_at": None}, "historical_availability_unproven_or_future"),
    ({"availability_reference": None}, "historical_availability_unproven_or_future"),
    ({"source": None}, "source_identity_missing"),
    ({"source_version": None}, "source_identity_missing"),
    ({"input_reference": None}, "source_identity_missing"),
    ({"source_vintage": None}, "historical_vintage_unproven"),
    ({"vintage_reference": None}, "historical_vintage_unproven"),
    ({"data_kind": "INTRADAY_SNAPSHOT"}, "archive_or_research_not_daily_input"),
    ({"data_kind": "RESEARCH_DAILY"}, "archive_or_research_not_daily_input"),
    ({"origin": "RESEARCH"}, "data_origin_cannot_be_promoted"),
    ({"overall_status": "BLOCKED", "blockers": ("supplier_unproven",)}, "declared_input_quality_not_ready"),
])
def test_daily_blocks_unproven_or_invalid_contract(changes, reason):
    rows, request, *_ = gate_fixture()
    result = validate_momentum_daily_input(altered(rows[-1], **changes), request)
    assert result.overall_status == "BLOCKED" and reason in result.blockers
    assert result.validated_input is None


@pytest.mark.parametrize("field,value", [("close", float("nan")), ("volume", float("inf")), ("open", True),
    ("available_at", datetime(2026, 9, 16)), ("timestamp", datetime(2026, 9, 16)),
    ("finality_verified_at", datetime(2026, 9, 16)), ("knowledge_cutoff", datetime(2026, 9, 16))])
def test_invalid_typed_or_naive_input_returns_sanitized_block(field, value):
    rows, request, *_ = gate_fixture()
    result = validate_momentum_daily_input(altered(rows[-1], **{field: value}), request)
    assert result.overall_status == "BLOCKED" and "invalid_typed_daily_input" in result.blockers


def test_future_or_intraday_availability_and_finality_blocked():
    rows, request, *_ = gate_fixture()
    row = rows[-1]
    for change in ({"available_at": request.knowledge_cutoff + timedelta(seconds=1)},
                   {"finality_verified_at": request.knowledge_cutoff + timedelta(seconds=1)},
                   {"available_at": row.timestamp - timedelta(seconds=1)},
                   {"timestamp": row.timestamp - timedelta(hours=1)}):
        assert validate_momentum_daily_input(altered(row, **change), request).overall_status == "BLOCKED"
    early = request.model_copy(update={"knowledge_cutoff": row.timestamp - timedelta(minutes=1),
        "evaluation_boundary": row.timestamp - timedelta(minutes=1)})
    assert validate_momentum_daily_input(row, early).overall_status == "BLOCKED"


def test_fetched_at_never_substitutes_for_availability_or_vintage():
    rows, request, *_ = gate_fixture()
    row = altered(rows[-1], available_at=None, source_vintage=None, fetched_at=request.generated_at)
    result = validate_momentum_daily_input(row, request)
    assert "historical_availability_unproven_or_future" in result.blockers
    assert "historical_vintage_unproven" in result.blockers


def test_cutoff_must_not_exceed_explicit_decision_boundary():
    rows, request, *_ = gate_fixture()
    request = request.model_copy(update={"evaluation_boundary": request.knowledge_cutoff - timedelta(seconds=1)})
    assert "knowledge_cutoff_after_required_boundary" in validate_momentum_history_window(rows, request).blockers


def test_missing_duplicate_and_ordered_session_contract():
    rows, request, *_ = gate_fixture()
    result = validate_momentum_history_window((*rows[:-3], *rows[-2:]), request)
    assert result.overall_status == "PARTIAL" and "missing_required_session" in result.blockers
    assert "previous_close_basis_conflict" not in result.blockers
    duplicate = validate_momentum_history_window((*rows, rows[-1]), request)
    assert duplicate.overall_status == "BLOCKED" and "unordered_or_duplicate_session" in duplicate.blockers
    assert validate_momentum_history_window(tuple(reversed(rows)), request).overall_status == "BLOCKED"


def test_weekends_and_holidays_are_not_missing_sessions():
    rows, request, *_ = gate_fixture()
    assert any((b.trading_date - a.trading_date).days > 1 for a, b in pairwise(rows))
    assert validate_momentum_history_window(rows, request).overall_status == "READY"


def test_window_requirements_are_exact_no_automatic_shortening():
    rows, request, *_ = gate_fixture()
    result = validate_momentum_history_window(rows[-21:], request)
    checks = {check.key: check.status for check in result.checks}
    assert checks["window:volume_ratio_20"] == checks["window:volatility_20"] == "READY"
    assert checks["window:volatility_trend_status"] == checks["window:breakout_60"] == "PARTIAL"
    assert result.overall_status == "PARTIAL"
    twenty = validate_momentum_history_window(rows[-20:], request)
    assert next(check for check in twenty.checks if check.key == "window:volume_ratio_20").status == "PARTIAL"
    with pytest.raises(ValueError, match="not_ready"):
        twenty.accepted_input()


def test_vr20_zero_denominator_is_null_with_reason():
    rows, request, *_ = gate_fixture()
    changed = tuple(row.model_copy(update={"volume": 0}) for row in rows[:-1]) + rows[-1:]
    result = validate_momentum_history_window(changed, request)
    check = next(check for check in result.checks if check.key == "vr20_denominator")
    assert check.status == "UNAVAILABLE" and check.value is None
    assert check.reason == "volume_ratio_20_denominator_zero" and result.overall_status == "PARTIAL"


@pytest.mark.parametrize("field,value", [("source", "another-source"), ("volume_unit", "another-unit"),
    ("source_vintage", "another-vintage"), ("currency", "another-currency"), ("adjustment_version", "another-version")])
def test_mixed_history_basis_blocked(field, value):
    rows, request, *_ = gate_fixture()
    mixed = (*rows[:-1], rows[-1].model_copy(update={field: value}))
    assert "mixed_source_price_quantity_or_vintage" in validate_momentum_history_window(mixed, request).blockers


def test_no_history_unavailable():
    _, request, *_ = gate_fixture()
    result = validate_momentum_history_window((), request)
    assert result.overall_status == "UNAVAILABLE" and result.validated_input is None


@pytest.mark.parametrize("mode", ["PRODUCTION", "RESEARCH"])
def test_no_fixture_or_research_promotion_to_production(mode):
    rows, request, *_ = gate_fixture()
    request = request.model_copy(update={"mode": mode})
    result = validate_momentum_history_window(tuple(row.model_copy(update={"origin": mode}) for row in rows), request)
    assert result.overall_status == "BLOCKED" and result.production_execution == "BLOCKED"
    with pytest.raises(ValueError, match="not_ready"):
        result.accepted_input()


@pytest.mark.parametrize("market", ["HK", "US"])
def test_engine_accepts_only_gate_validated_input_and_preserves_math(market):
    rows, request, profile, cohort = gate_fixture(market)
    accepted = validate_momentum_history_window(rows, request).accepted_input()
    result = engine.calculate_momentum(inputs=(accepted,), calculation=request.calculation, profile=profile,
        calendar=request.calendar, universe=request.universe, cohort=cohort)
    reference = engine._calculate_momentum(inputs=(open_gated_input(accepted, request.calculation, request.calendar),), calculation=request.calculation,
        profile=profile, calendar=request.calendar, universe=request.universe, cohort=cohort)
    assert result == reference and result.production_execution == "BLOCKED"
    assert engine.calculate_metrics(accepted, request.calculation, request.calendar) == result.metrics[0]


def test_raw_ready_declarations_rejected_before_math(monkeypatch):
    data, calculation, profile, calendar, universe, cohort = fixture_inputs()
    def forbidden(*args, **kwargs):
        pytest.fail("raw input must be rejected before arithmetic")
    monkeypatch.setattr(engine, "_calculate_metrics", forbidden)
    with pytest.raises(ValueError, match="gate_required"):
        engine.calculate_metrics(data, calculation, calendar)
    with pytest.raises(ValueError, match="gate_required"):
        engine.calculate_momentum(inputs=(data,), calculation=calculation, profile=profile,
            calendar=calendar, universe=universe, cohort=cohort)


def test_tampered_receipt_or_engine_projection_is_revalidated():
    rows, request, *_ = gate_fixture()
    accepted = validate_momentum_history_window(rows, request).accepted_input()
    changed = accepted.model_copy(update={"validation_hash": "f" * 64})
    with pytest.raises(ValueError, match="validation_conflict"):
        engine.calculate_metrics(changed, request.calculation, request.calendar)
    projected = accepted.validated_input.model_copy(update={"source_vintage": "forged"})
    with pytest.raises(ValueError, match="validation_conflict"):
        engine.calculate_metrics(accepted.model_copy(update={"validated_input": projected}), request.calculation, request.calendar)
    rows = (*accepted.rows[:-1], accepted.rows[-1].model_copy(update={"price_basis": "RAW"}))
    with pytest.raises(ValueError, match="validation_conflict"):
        engine.calculate_metrics(accepted.model_copy(update={"rows": rows}), request.calculation, request.calendar)


def test_gate_canonical_identity_and_result_determinism():
    contract = MomentumInputGateContract()
    assert MomentumInputGateContract.model_validate(dict(reversed(list(contract.model_dump().items())))).content_hash == contract.content_hash
    rows, request, *_ = gate_fixture()
    a = validate_momentum_history_window(rows, request)
    b = validate_momentum_history_window(tuple(dict(reversed(list(row.model_dump().items()))) for row in rows), request)
    assert a.validation_hash == b.validation_hash and a == b
    with pytest.raises(ValidationError):
        rows[0].close = 3


def test_all_existing_calculation_and_profile_hashes_unchanged():
    old, new = candidate_calculation_v1(), calculation_with_trend_v1_1()
    assert old.content_hash == "05acb22677f4fc9148916ba5c7b1c012ea15c556befbaa51a422bfa5d21e6a09"
    assert candidate_technical_profile_v1(old).content_hash == "be55cfbab6d46a03797b883922209b9e7d2afb2d63893830d0ddb922d7e1c35c"
    assert technical_profile_v1_1(old).content_hash == "03701dc8d08cb15c9640c11df3ad5c47fcc6ced812172860612046da02ca0369"
    assert new.content_hash == "790212a4fd6ac7f3c50f2941a1eb51e192ebd873ac3c796cc07a0dd12460e7de"
    assert technical_profile_v1_2(new).content_hash == "8c48c32df331939908af76363e697827eda83de41639b80767e160be22d0832f"


@pytest.mark.parametrize("field,value,reason", [
    ("calculation_version", "v99", "input_or_calculation_identity_conflict"),
    ("input_contract_version", "v99", "input_or_calculation_identity_conflict"),
    ("score_profile_version", "v99", "score_profile_identity_conflict"),
    ("universe_content_hash", "f" * 64, "universe_identity_or_quality_unproven"),
])
def test_request_exact_identities_required(field, value, reason):
    rows, request, *_ = gate_fixture()
    identity = request.identity.model_copy(update={field: value})
    result = validate_momentum_history_window(rows, request.model_copy(update={"identity": identity}))
    assert result.overall_status == "BLOCKED" and reason in result.blockers


def test_whole_target_day_universe_policy_matches_existing_score_contract():
    rows, request, *_ = gate_fixture()
    from datetime import UTC
    # Universe is active by the close but not by the start of the target day.
    effective = datetime(2026, 9, 16, 15, tzinfo=UTC)
    members = tuple(member.model_copy(update={"effective_from": effective}) for member in request.universe.members)
    universe = request.universe.model_copy(update={"effective_from": effective, "members": members})
    identity = request.identity.model_copy(update={"universe_content_hash": universe.content_hash})
    result = validate_momentum_history_window(rows, request.model_copy(update={"identity": identity, "universe": universe}))
    assert "universe_not_effective_for_entire_target_date" in result.blockers


def test_legacy_calculation_can_use_gate_without_score_upgrade():
    rows, request, profile, cohort = gate_fixture(extended=False)
    accepted = validate_momentum_history_window(rows, request).accepted_input()
    result = engine.calculate_momentum(inputs=(accepted,), calculation=request.calculation, profile=profile,
        calendar=request.calendar, universe=request.universe, cohort=cohort)
    assert result.snapshots[0].snapshot_version == "momentum-snapshot-v1"
    assert result.snapshots[0].score_profile_version == "v1.1"


def test_gate_provenance_and_warnings_reach_engine_candidate():
    rows, request, profile, cohort = gate_fixture()
    rows = (*rows[:-1], rows[-1].model_copy(update={"warnings": ("synthetic-optional-turnover-missing",)}))
    result = validate_momentum_history_window(rows, request)
    candidate = engine.calculate_momentum(inputs=(result.accepted_input(),), calculation=request.calculation,
        profile=profile, calendar=request.calendar, universe=request.universe, cohort=cohort).snapshots[0]
    assert candidate.adjustment_method == "SPLIT_ONLY"
    assert f"momentum-gate:{result.validation_hash}" in candidate.input_references
    assert "synthetic-optional-turnover-missing" in candidate.warnings
    assert "synthetic_test_only_not_production" in candidate.warnings


def test_blocked_second_input_rejects_whole_batch_before_math(monkeypatch):
    rows, request, profile, cohort = gate_fixture()
    accepted = validate_momentum_history_window(rows, request).accepted_input()
    bad_rows = (*rows[:-1], rows[-1].model_copy(update={"volume_semantics": "UNKNOWN"}))
    blocked = validate_momentum_history_window(bad_rows, request)
    assert blocked.overall_status == "BLOCKED"
    # Even a receipt edited to claim this blocked result's actual hash cannot pass.
    forged = accepted.model_copy(update={"rows": bad_rows, "validation_hash": blocked.validation_hash})
    def forbidden(*args, **kwargs):
        pytest.fail("batch must fail Gate before evaluating even its first candidate")
    monkeypatch.setattr(engine, "_calculate_metrics", forbidden)
    with pytest.raises(ValueError, match="validation_conflict"):
        engine.calculate_momentum(inputs=(accepted, forged), calculation=request.calculation, profile=profile,
            calendar=request.calendar, universe=request.universe, cohort=cohort)
