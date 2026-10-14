"""Canonical CN/US configuration; materialize once before application workers start."""
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.services.evidence_execution import (
    EvidenceExecutionResolver,
    PolicyExecutionBinding,
    TradingCalendarBindings,
    TradingCalendarContract,
)
from app.services.evidence_policy import EvidencePolicy, EvidencePolicyStore


@dataclass(frozen=True)
class ProductionReference:
    market: str
    policy_id: str
    policy_version: str
    calendar_id: str
    calendar_version: str
    calendar_content_hash: str
    effective_from: str
    effective_to: str


PRODUCTION_REFERENCES = (
    ProductionReference("CN", "anomaly-intelligence-cn", "v1", "cn-cash-equity-official", "2026-v1",
        "62c1d558ab30fd3c171754ac17954614358a1d9c70ffb158b60fa4a54b8acc86",
        "2026-01-01T00:00:00+08:00", "2027-01-01T00:00:00+08:00"),
    ProductionReference("US", "anomaly-intelligence-us", "v1", "us-cash-equity-official", "2026-v1",
        "cfb976ea41ff8037ab0dd5225f061dcb960976cd404bcd10eae2bb74a1084d76",
        "2026-01-01T00:00:00-05:00", "2027-01-01T00:00:00-05:00"),
)


def production_bindings() -> tuple[PolicyExecutionBinding, ...]:
    """Validate exact source artifacts; never substitute a version or hash."""
    bindings = []
    for ref in PRODUCTION_REFERENCES:
        calendar = TradingCalendarContract.from_canonical(ref.market)
        if (calendar.calendar_id, calendar.version, calendar.content_hash) != (
                ref.calendar_id, ref.calendar_version, ref.calendar_content_hash):
            raise ValueError("production_calendar_identity_conflict")
        zone = ZoneInfo(calendar.timezone)
        first = datetime.combine(calendar.coverage_start, time.min, zone)
        exclusive_end = datetime.combine(calendar.coverage_end + timedelta(days=1), time.min, zone)
        policy = EvidencePolicy(policy_id=ref.policy_id, version=ref.policy_version, status="ACTIVE",
            market=ref.market, scope_type="MARKET_WIDE", symbol_scope=(),
            effective_from=ref.effective_from, effective_to=ref.effective_to,
            event_types=("rapid_price_move", "intraday_breakout", "volatility_expansion"),
            event_time_source="window_end", knowledge_cutoff_source="detected_at",
            trading_calendar=ref.calendar_id, definition_id=None, universe_id=None,
            snapshot_date_rule="previous_completed_trading_day", normalization_version=None,
            required_factor_versions=(), allow_atr_display=True, allow_move_atr_ratio=True,
            require_price_scale_verified=True, benchmark_required=True,
            benchmark_selection_mode="existing_event_market_context_no_substitution",
            required_evidence=("market",), optional_evidence=("historical",))
        if not first <= policy.effective_from < policy.effective_to <= exclusive_end:
            raise ValueError("production_policy_calendar_coverage_conflict")
        bindings.append(PolicyExecutionBinding(policy_id=policy.policy_id, policy_version=policy.version,
            policy=policy, calendar_id=ref.calendar_id, calendar_version=ref.calendar_version,
            calendar_content_hash=ref.calendar_content_hash, factors=()))
    return tuple(bindings)


def bootstrap_production_evidence(data_dir: Path) -> EvidenceExecutionResolver:
    bindings = production_bindings()
    calendars = TradingCalendarBindings()
    execution = EvidenceExecutionResolver(calendars)
    for binding in bindings:
        calendars.register(TradingCalendarContract.from_canonical(binding.policy.market))
        execution.register(binding)
        if execution.resolve(binding.policy)["status"] != "READY":
            raise ValueError("production_execution_binding_conflict")
    store = EvidencePolicyStore(data_dir)
    existing = {(item.policy_id, item.version): item for item in store.list_policies()}
    # Check both records before any writes. Store.save also checks under its write lock.
    for binding in bindings:
        previous = existing.get((binding.policy_id, binding.policy_version))
        if previous is not None and previous != binding.policy:
            raise ValueError("immutable_policy_version_conflict")
    for binding in bindings:
        store.save(binding.policy)
    return execution
