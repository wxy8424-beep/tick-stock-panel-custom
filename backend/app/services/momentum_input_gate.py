"""Immutable Daily evidence validation. No fetching, fallback, persistence or producer."""
from __future__ import annotations

from datetime import UTC, date, datetime, time
from itertools import pairwise
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    FiniteFloat,
    StrictBool,
    StrictInt,
    ValidationError,
    field_validator,
)

from app.market_session import market_from_symbol
from app.services.evidence_execution import TradingCalendarContract
from app.services.momentum_calculation_contracts import (
    MomentumCalculationDefinition,
    calculation_with_trend_v1_1,
    candidate_calculation_v1,
    technical_profile_v1_1,
    technical_profile_v1_2,
)
from app.services.momentum_engine import DailyBar, ValidatedDailyInput, _close, _sessions
from app.services.momentum_snapshots import Digest, Label, MomentumIdentity, State, digest
from app.services.momentum_universes import InstrumentType, MomentumUniverseDefinition


class GateModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MomentumInputGateContract(GateModel):
    contract_id: Literal["momentum-daily-input-gate"] = "momentum-daily-input-gate"
    version: Literal["v1"] = "v1"
    production_enabled: Literal[False] = False
    rules: tuple[str, ...] = (
        "exact_calculation_calendar_universe_and_input_contract_identity",
        "included_member_and_exact_instrument_eligibility_at_target_date",
        "exact_selected_profile_and_whole_target_date_universe_effective_period",
        "strict_order_unique_complete_exact_sessions_no_fill_skip_or_fallback",
        "finite_positive_consistent_OHLC_and_nonnegative_quantity",
        "split_only_adjustment_with_version_and_evidence",
        "comparable_volume_with_unit_currency_and_evidence_no_intraday_volume",
        "explicit_completed_finality_after_exact_session_close",
        "availability_and_vintage_evidence_separate_from_fetched_at",
        "knowledge_cutoff_not_after_evaluation_boundary_or_generation",
        "same_source_version_vintage_price_and_quantity_basis_across_window",
        "fixed_metric_lookbacks_from_exact_calculation_and_proven_up_run_boundary",
        "no_rows_UNAVAILABLE_invalid_or_unproven_BLOCKED_incomplete_PARTIAL_complete_READY",
        "only_READY_full_window_can_issue_revalidated_engine_input",
        "preserve_adjustment_warnings_and_receipt_hash_in_engine_provenance",
        "synthetic_only_v1_research_and_production_never_promoted",
    )

    @property
    def content_hash(self):
        return digest(self.model_dump(mode="json"))


class MomentumDailyInput(GateModel):
    symbol: Label
    market: Literal["HK", "US"]
    instrument_type: InstrumentType
    trading_date: date
    timezone: Label
    timestamp: AwareDatetime | None
    knowledge_cutoff: AwareDatetime
    available_at: AwareDatetime | None
    fetched_at: AwareDatetime | None
    calendar_id: Label
    calendar_version: Label
    calendar_content_hash: Digest
    session_index: StrictInt | None = None
    open: FiniteFloat | None
    high: FiniteFloat | None
    low: FiniteFloat | None
    close: FiniteFloat | None
    prev_close: FiniteFloat | None = None
    price_basis: Literal["RAW", "SPLIT_ADJUSTED_PRICE_ONLY", "OTHER_ADJUSTED", "UNKNOWN"] | None
    adjustment_method: Label | None
    adjustment_version: Label | None
    price_basis_reference: Label | None
    volume: FiniteFloat | None
    turnover: FiniteFloat | None = None
    volume_unit: Label | None
    volume_semantics: Literal["COMPARABLE_CORPORATE_ACTION_QUANTITY", "RAW_QUANTITY", "UNKNOWN"] | None
    quantity_reference: Label | None
    currency: Label | None
    bar_final: StrictBool | None
    finality_source: Label | None
    finality_reference: Label | None
    finality_verified_at: AwareDatetime | None
    source: Label | None
    source_version: Label | None
    source_vintage: Label | None
    vintage_reference: Label | None
    availability_reference: Label | None
    input_reference: Label | None
    data_kind: Literal["DAILY_OHLCV", "INTRADAY_SNAPSHOT", "RESEARCH_DAILY"]
    origin: Literal["SYNTHETIC_TEST", "RESEARCH", "PRODUCTION"]
    overall_status: State | None = None
    blockers: tuple[Label, ...] = ()
    warnings: tuple[Label, ...] = ()

    @field_validator("timestamp", "knowledge_cutoff", "available_at", "fetched_at", "finality_verified_at")
    @classmethod
    def utc(cls, value):
        return value.astimezone(UTC) if value is not None else None

    @field_validator("open", "high", "low", "close", "prev_close", "volume", "turnover", mode="before")
    @classmethod
    def no_numeric_boolean(cls, value):
        if isinstance(value, bool):
            raise ValueError("numeric_boolean_not_allowed")
        return value


class MomentumGateRequest(GateModel):
    identity: MomentumIdentity
    calculation: MomentumCalculationDefinition
    calendar: TradingCalendarContract
    universe: MomentumUniverseDefinition
    generated_at: AwareDatetime
    knowledge_cutoff: AwareDatetime
    evaluation_boundary: AwareDatetime
    mode: Literal["SYNTHETIC_TEST", "RESEARCH", "PRODUCTION"]

    @field_validator("generated_at", "knowledge_cutoff", "evaluation_boundary")
    @classmethod
    def utc(cls, value):
        return value.astimezone(UTC)


class GateCheck(GateModel):
    key: Label
    status: State
    reason: Label | None = None
    evidence_refs: tuple[Label, ...] = ()
    # Validation never emits a substitute metric value.
    value: None = None


class MomentumGateAcceptedInput(GateModel):
    """Replayable receipt, NOT a trusted boolean or a security/authentication token."""
    request: MomentumGateRequest
    rows: tuple[MomentumDailyInput, ...]
    validated_input: ValidatedDailyInput
    gate_content_hash: Digest
    validation_hash: Digest


class MomentumGateResult(GateModel):
    overall_status: State
    checks: tuple[GateCheck, ...]
    blockers: tuple[Label, ...]
    warnings: tuple[Label, ...]
    request: MomentumGateRequest
    rows: tuple[MomentumDailyInput, ...]
    validated_input: ValidatedDailyInput | None = None
    scope: Literal["DAILY", "HISTORY"]
    production_execution: Literal["BLOCKED"] = "BLOCKED"
    gate_content_hash: Digest

    @property
    def validation_hash(self):
        return digest(self.model_dump(mode="json"))

    def accepted_input(self) -> MomentumGateAcceptedInput:
        if self.scope != "HISTORY" or self.overall_status != "READY" or self.validated_input is None:
            raise ValueError("momentum_input_gate_not_ready")
        return MomentumGateAcceptedInput(request=self.request, rows=self.rows, validated_input=self.validated_input,
            gate_content_hash=self.gate_content_hash, validation_hash=self.validation_hash)


def _known(value):
    return value is not None and value.upper() not in {"UNKNOWN", "UNVERIFIED", "BLOCKED", "LATEST", "CURRENT", "DEFAULT", "*"}


def _check(key, condition, reason, refs=(), failed="BLOCKED"):
    return GateCheck(key=key, status="READY" if condition else failed, reason=None if condition else reason,
                     evidence_refs=tuple(sorted({ref for ref in refs if _known(ref)})))


def _request_checks(request):
    i, c, u, definition = request.identity, request.calendar, request.universe, request.calculation
    gate = MomentumInputGateContract()
    known_calculations = (candidate_calculation_v1().identity, calculation_with_trend_v1_1().identity)
    profile = technical_profile_v1_1(candidate_calculation_v1()) if definition.identity == known_calculations[0] else technical_profile_v1_2(calculation_with_trend_v1_1())
    member = next((member for member in u.members if member.symbol == i.symbol), None)
    checks = [
        _check("request_identity", definition.identity in known_calculations
            and (i.calculation_id, i.calculation_version, i.calculation_content_hash) == (
                definition.calculation_id, definition.calculation_version, definition.content_hash)
            and (i.input_contract_id, i.input_contract_version) == (gate.contract_id, gate.version), "input_or_calculation_identity_conflict"),
        _check("request_calendar", (i.market, i.calendar_id, i.calendar_version, i.calendar_content_hash) == (
            c.market, c.calendar_id, c.version, c.content_hash), "calendar_identity_conflict", (c.content_hash,)),
        _check("request_profile", (i.score_profile_id, i.score_profile_version, i.score_profile_content_hash) == (
            profile.score_profile_id, profile.score_profile_version, profile.content_hash), "score_profile_identity_conflict", (profile.content_hash,)),
        _check("request_universe", u.status == "READY" and (i.market, i.universe_id, i.universe_version, i.universe_content_hash) == (
            u.market, u.universe_id, u.universe_version, u.content_hash), "universe_identity_or_quality_unproven", (u.content_hash,)),
        _check("request_time", request.knowledge_cutoff <= request.evaluation_boundary <= request.generated_at,
               "knowledge_cutoff_after_required_boundary"),
        _check("universe_pit", u.available_at is not None and u.available_at <= request.knowledge_cutoff,
               "universe_availability_unproven"),
        _check("mode", request.mode == "SYNTHETIC_TEST", "production_contract_not_installed" if request.mode == "PRODUCTION" else "research_not_production_input"),
        _check("membership", member is not None and member.membership_status == "INCLUDED", "member_not_eligible"),
    ]
    target_close = _close(c, i.trading_date) if c.coverage_start <= i.trading_date <= c.coverage_end else None
    checks.append(_check("target_session", target_close is not None and i.trading_date in _sessions(c, i.trading_date)
        and target_close <= request.knowledge_cutoff, "target_not_completed_exact_session"))
    # Ranking identity is for target D, not a claim of membership on all lookback dates.
    day_start = datetime.combine(i.trading_date, time.min, ZoneInfo(c.timezone))
    day_end = datetime.combine(i.trading_date, time.max, ZoneInfo(c.timezone))
    checks.append(_check("membership_effective", u.effective_from <= day_start
        and (u.effective_to is None or day_end < u.effective_to), "universe_not_effective_for_entire_target_date"))
    return checks


def _daily_checks(row, request):
    c, identity = request.calendar, request.identity
    member = next((member for member in request.universe.members if member.symbol == identity.symbol), None)
    sessions = _sessions(c, min(row.trading_date, c.coverage_end))
    is_session = c.coverage_start <= row.trading_date <= c.coverage_end and row.trading_date in sessions
    close = _close(c, row.trading_date) if is_session else None
    numbers = (row.open, row.high, row.low, row.close)
    refs = (row.input_reference,)
    ohlc = all(value is not None and value > 0 for value in numbers)
    if ohlc:
        ohlc = row.low <= min(row.open, row.close) <= max(row.open, row.close) <= row.high
    return [
        _check("identity", row.symbol == identity.symbol and row.market == identity.market
            and market_from_symbol(row.symbol) == row.market, "symbol_market_identity_conflict", refs),
        _check("instrument", member is not None and row.instrument_type != "UNKNOWN"
            and row.instrument_type == member.instrument_type and row.instrument_type in request.universe.allowed_instrument_types
            and row.instrument_type not in request.universe.exclusion_rules.instrument_types,
            "instrument_not_eligible", (member.evidence_reference,) if member else ()),
        _check("calendar", (row.calendar_id, row.calendar_version, row.calendar_content_hash, row.timezone) == (
            c.calendar_id, c.version, c.content_hash, c.timezone), "calendar_binding_conflict", (c.content_hash,)),
        _check("session", is_session and row.trading_date <= identity.trading_date
            and (row.session_index is None or row.session_index == len(sessions) - 1), "invalid_or_future_session"),
        _check("timestamp", close is not None and row.timestamp == close, "session_timestamp_unproven"),
        _check("ohlc", ohlc, "ohlc_missing_or_inconsistent", refs),
        _check("prev_close", row.prev_close is None or row.prev_close > 0, "invalid_previous_close", refs),
        _check("price_basis", row.price_basis == "SPLIT_ADJUSTED_PRICE_ONLY" and _known(row.price_basis_reference),
            "split_only_price_basis_unproven", (row.price_basis_reference,)),
        _check("adjustment", row.adjustment_method == "SPLIT_ONLY" and _known(row.adjustment_version),
            "adjustment_semantics_unproven", (row.price_basis_reference,)),
        _check("volume", row.volume is not None and row.volume >= 0 and (row.turnover is None or row.turnover >= 0),
            "volume_missing_or_invalid", refs),
        _check("quantity", _known(row.volume_unit) and row.volume_semantics == "COMPARABLE_CORPORATE_ACTION_QUANTITY"
            and _known(row.quantity_reference) and _known(row.currency), "quantity_semantics_unproven", (row.quantity_reference,)),
        _check("finality", close is not None and row.bar_final is True and _known(row.finality_source)
            and _known(row.finality_reference) and row.finality_verified_at is not None
            and close <= row.finality_verified_at <= request.knowledge_cutoff, "completed_daily_finality_unproven", (row.finality_reference,)),
        _check("cutoff", row.knowledge_cutoff == request.knowledge_cutoff, "mixed_knowledge_cutoff"),
        _check("availability", close is not None and row.available_at is not None
            and close <= row.available_at <= request.knowledge_cutoff and _known(row.availability_reference),
            "historical_availability_unproven_or_future", (row.availability_reference,)),
        _check("fetched_at", row.fetched_at is None or row.fetched_at <= request.generated_at, "future_fetch_observation"),
        _check("provenance", all(_known(value) for value in (row.source, row.source_version, row.input_reference)), "source_identity_missing", refs),
        _check("vintage", _known(row.source_vintage) and _known(row.vintage_reference), "historical_vintage_unproven", (row.vintage_reference,)),
        _check("daily_kind", row.data_kind == "DAILY_OHLCV", "archive_or_research_not_daily_input"),
        _check("origin", row.origin == request.mode, "data_origin_cannot_be_promoted"),
        _check("declared_quality", row.overall_status in (None, "READY") and not row.blockers,
            "declared_input_quality_not_ready", refs),
    ]


def _parse(rows):
    parsed, errors = [], []
    for index, row in enumerate(rows):
        try:
            parsed.append(MomentumDailyInput.model_validate(row.model_dump() if isinstance(row, MomentumDailyInput) else row))
        except ValidationError:
            # Do not return original payloads, raw errors or sensitive exception text.
            errors.append(GateCheck(key=f"row_{index}_schema", status="BLOCKED", reason="invalid_typed_daily_input"))
    return tuple(parsed), errors


def _result(request, rows, checks, scope):
    statuses = {check.status for check in checks}
    status = "BLOCKED" if "BLOCKED" in statuses else "UNAVAILABLE" if not rows else "PARTIAL" if statuses & {"PARTIAL", "UNAVAILABLE"} else "READY"
    validated = None
    warnings = tuple(sorted({warning for row in rows for warning in row.warnings}
        | ({"synthetic_test_only_not_production"} if request.mode == "SYNTHETIC_TEST" else set())))
    if status == "READY" and scope == "HISTORY":
        last = rows[-1]
        references = tuple(sorted({ref for row in rows for ref in (row.input_reference, row.price_basis_reference,
            row.quantity_reference, row.finality_reference, row.availability_reference, row.vintage_reference)}))
        validated = ValidatedDailyInput(identity=request.identity, bars=tuple(DailyBar(
            trading_date=row.trading_date, open=row.open, high=row.high, low=row.low, close=row.close,
            volume=row.volume, turnover=row.turnover, available_at=row.available_at, finality_status="READY",
            finality_reference=row.finality_reference, evidence_reference=row.input_reference) for row in rows),
            generated_at=request.generated_at, knowledge_cutoff=request.knowledge_cutoff, source=last.source,
            input_references=references, price_basis=last.price_basis, price_status="READY", volume_unit=last.volume_unit,
            quantity_status="READY", pit_status="READY", source_vintage=last.source_vintage,
            adjustment_method=last.adjustment_method, warnings=warnings)
    return MomentumGateResult(overall_status=status, checks=tuple(checks), blockers=tuple(sorted({
        check.reason for check in checks if check.reason is not None and check.status != "READY"}
        | {reason for row in rows for reason in row.blockers})),
        warnings=warnings, request=request, rows=rows,
        validated_input=validated, scope=scope, gate_content_hash=MomentumInputGateContract().content_hash)


def validate_momentum_daily_input(row: MomentumDailyInput | dict, request: MomentumGateRequest) -> MomentumGateResult:
    request = MomentumGateRequest.model_validate_json(request.model_dump_json())
    rows, errors = _parse((row,))
    checks = _request_checks(request) + errors
    if rows:
        checks.extend(_daily_checks(rows[0], request))
    return _result(request, rows, checks, "DAILY")


def validate_momentum_history_window(rows: tuple[MomentumDailyInput | dict, ...], request: MomentumGateRequest) -> MomentumGateResult:
    request = MomentumGateRequest.model_validate_json(request.model_dump_json())
    parsed, errors = _parse(rows)
    checks = _request_checks(request) + errors
    if not rows:
        checks.append(GateCheck(key="history", status="UNAVAILABLE", reason="daily_history_unavailable"))
        return _result(request, parsed, checks, "HISTORY")
    for index, row in enumerate(parsed):
        checks.extend(check.model_copy(update={"key": f"row_{index}:{check.key}"}) for check in _daily_checks(row, request))
    dates = [row.trading_date for row in parsed]
    checks.append(_check("order", all(a < b for a, b in pairwise(dates)), "unordered_or_duplicate_session"))
    if not parsed:
        return _result(request, parsed, checks, "HISTORY")
    metadata = [(row.source, row.source_version, row.source_vintage, row.price_basis, row.adjustment_method,
        row.adjustment_version, row.volume_unit, row.volume_semantics, row.currency) for row in parsed]
    checks.append(_check("consistent_basis", len(set(metadata)) == 1, "mixed_source_price_quantity_or_vintage"))
    sessions = _sessions(request.calendar, min(request.identity.trading_date, request.calendar.coverage_end))
    date_set = set(dates)
    if dates and sessions:
        submitted_expected = {day for day in sessions if day >= dates[0]}
        checks.append(_check("history_contiguity", date_set == submitted_expected,
                             "missing_required_session", failed="PARTIAL"))
    for definition in request.calculation.metrics:
        count = definition.required_history_sessions
        if count is not None:
            complete = len(sessions) >= count and set(sessions[-count:]) <= date_set
        else:
            # A data-dependent up-run requires an observed equality/down boundary.
            by_day = {row.trading_date: row for row in parsed}
            complete = False
            for previous, current in zip(reversed(sessions[:-1]), reversed(sessions[1:]), strict=False):
                if previous not in by_day or current not in by_day or by_day[previous].close is None or by_day[current].close is None:
                    break
                if by_day[current].close <= by_day[previous].close:
                    complete = True
                    break
        checks.append(_check(f"window:{definition.metric_key}", complete, f"{definition.metric_key}_history_incomplete", failed="PARTIAL"))
    by_day = {row.trading_date: row for row in parsed}
    vr_days = sessions[-21:]
    if len(vr_days) == 21 and all(day in by_day and by_day[day].volume is not None for day in vr_days):
        checks.append(_check("vr20_denominator", any(by_day[day].volume > 0 for day in vr_days[:-1]),
                             "volume_ratio_20_denominator_zero", failed="UNAVAILABLE"))
    positions = {day: index for index, day in enumerate(sessions)}
    for previous, current in pairwise(parsed):
        if (current.prev_close is not None and previous.trading_date in positions and current.trading_date in positions
                and positions[current.trading_date] == positions[previous.trading_date] + 1):
            checks.append(_check(f"prev_close:{current.trading_date}", current.prev_close == previous.close,
                                 "previous_close_basis_conflict", (current.input_reference,)))
    return _result(request, parsed, checks, "HISTORY")


def open_gated_input(value, calculation, calendar, universe=None) -> ValidatedDailyInput:
    """Re-run evidence checks; a forged/stale READY flag, hash or edited payload fails."""
    if not isinstance(value, MomentumGateAcceptedInput):
        raise ValueError("momentum_input_gate_required")
    value = MomentumGateAcceptedInput.model_validate_json(value.model_dump_json())
    if value.gate_content_hash != MomentumInputGateContract().content_hash:
        raise ValueError("momentum_input_gate_contract_conflict")
    request = value.request
    if request.calculation.identity != calculation.identity or request.calendar != calendar or (
        universe is not None and request.universe != universe
    ):
        raise ValueError("momentum_input_gate_context_conflict")
    result = validate_momentum_history_window(value.rows, request)
    if result.overall_status != "READY" or result.validation_hash != value.validation_hash or result.validated_input != value.validated_input:
        raise ValueError("momentum_input_gate_validation_conflict")
    return result.validated_input.model_copy(update={"input_references": tuple(sorted({
        *result.validated_input.input_references, f"momentum-gate:{result.validation_hash}"}))})
