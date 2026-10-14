"""Fixture-only binding checks, no evidence reads or production registration."""
from datetime import date

import pytest
from pydantic import ValidationError
from test_evidence_policy import disabled_policy, policy

from app.services.evidence_execution import (
    EvidenceExecutionResolver,
    FactorIdentityContract,
    PolicyExecutionBinding,
    TradingCalendarBindings,
    TradingCalendarContract,
)


def calendar(**changes):
    return TradingCalendarContract.model_validate({
        "calendar_id": "fixture-calendar-v1", "version": "1", "market": "US",
        "timezone": "America/New_York", "source": ["isolated-fixture"],
        "effective_from": "2026-01-01", "effective_to": "2026-12-31",
        "coverage_start": "2026-01-01", "coverage_end": "2026-12-31",
        "trading_weekdays": [0, 1, 2, 3, 4], "holidays": ["2026-09-07"],
        "additional_trading_days": [],
    } | changes)


def factor(**changes):
    return FactorIdentityContract.model_validate({"registry_namespace": "market_factor_engine",
        "registry_key": "ma", "version": 1, "parameters": {"period": 5}, "output_component": "ma5"} | changes)


def binding(**changes):
    return PolicyExecutionBinding.model_validate({"policy_id": "fixture-policy", "policy_version": "v1",
        "policy": policy(), "calendar_id": "fixture-calendar-v1", "calendar_version": "1",
        "factors": [factor()]} | changes)


def test_market_wide_scope_pinned_in_exact_execution_binding():
    calendars = TradingCalendarBindings()
    calendars.register(calendar())
    resolver = EvidenceExecutionResolver(calendars)
    chosen = policy(scope_type="MARKET_WIDE", symbol_scope=[])
    resolver.register(binding(policy=chosen))
    assert resolver.resolve(chosen)["status"] == "READY"
    assert resolver.resolve(policy())["status"] == "BLOCKED"


def test_disabled_factor_execution_skips_identity_resolution(monkeypatch):
    from app.services import evidence_execution

    calendars = TradingCalendarBindings()
    calendars.register(calendar())
    chosen = disabled_policy()
    item = binding(policy=chosen, factors=[])
    assert PolicyExecutionBinding.model_validate_json(item.model_dump_json()) == item
    monkeypatch.setattr(evidence_execution, "get_engine_factor", lambda key: pytest.fail("disabled must not resolve factor"))
    resolver = EvidenceExecutionResolver(calendars)
    resolver.register(item)
    result = resolver.resolve(chosen)
    assert result["status"] == "READY" and result["factor_branch"] == "NOT_SELECTED"
    assert result["factor_identity_binding"] == []


def test_disabled_rejects_dummy_binding_enabled_rejects_empty_binding():
    with pytest.raises(ValidationError):
        binding(policy=disabled_policy(), factors=[factor()])
    with pytest.raises(ValidationError):
        binding(factors=[])


def test_calendar_immutable_version_and_serialization():
    registry = TradingCalendarBindings()
    item = calendar()
    registry.register(item)
    registry.register(item)
    assert TradingCalendarContract.model_validate_json(item.model_dump_json()) == item
    with pytest.raises(ValueError, match="immutable_calendar_version_conflict"):
        registry.register(calendar(holidays=[]))
    with pytest.raises(ValidationError):
        item.version = "2"
    registry.register(calendar(version="2", holidays=[]))
    assert registry.get("US", item.calendar_id, "1") == item


@pytest.mark.parametrize("day,previous", [("2026-09-08", "2026-09-04"),
    ("2026-09-07", "2026-09-04"), ("2026-09-06", "2026-09-04"), ("2026-09-09", "2026-09-08")])
def test_previous_day_uses_frozen_schedule(day, previous, monkeypatch):
    from app.market_calendar import CALENDARS

    registry = TradingCalendarBindings()
    registry.register(calendar())
    monkeypatch.setitem(CALENDARS, "US", None)
    result = registry.resolve_previous_trading_day(market="US", calendar_id="fixture-calendar-v1",
                                                  version="1", date=date.fromisoformat(day))
    assert result["previous_trading_day"] == previous


@pytest.mark.parametrize("changes", [{"calendar_id": "unknown"}, {"version": "2"},
    {"market": "HK"}, {"date": date(2025, 12, 31)}, {"date": date(2026, 1, 1)}])
def test_unknown_or_outside_coverage_blocks(changes):
    registry = TradingCalendarBindings()
    registry.register(calendar())
    assert registry.resolve_previous_trading_day(**({"market": "US", "calendar_id": "fixture-calendar-v1",
        "version": "1", "date": date(2026, 9, 8)} | changes))["status"] == "BLOCKED"


@pytest.mark.parametrize("changes", [{"registry_key": "ma5"}, {"registry_key": "MA"},
    {"output_component": "ma"}, {"output_component": "ma20"}, {"version": 2},
    {"parameters": {"period": None}}, {"registry_namespace": "legacy_factor_columns"}])
def test_factor_identity_never_fuzzy_or_default(changes):
    with pytest.raises(ValidationError):
        factor(**changes)


def test_factor_exact_parameters_and_macd_component():
    assert factor().output_component == "ma5"
    assert factor(registry_key="macd", parameters={"period": None}, output_component="macd_dif").version == 1


def test_policy_execution_missing_then_exact_binding(monkeypatch):
    from app.factors.engine import MarketFactorEngine

    monkeypatch.setattr(MarketFactorEngine, "compute", lambda *a, **k: pytest.fail("no calculation allowed"))
    calendars = TradingCalendarBindings()
    resolver = EvidenceExecutionResolver(calendars)
    assert resolver.resolve(policy())["blocker"] == "execution_binding_missing"
    item = binding()
    resolver.register(item)
    assert resolver.resolve(policy())["blocker"] == "calendar_binding_missing"
    calendars.register(calendar())
    result = resolver.resolve(policy())
    assert result["status"] == "READY"
    assert result["calendar_binding"]["version"] == "1"
    assert result["factor_identity_binding"][0]["parameters"] == {"period": 5}
    assert resolver.resolve(policy(universe_id="different"))["blocker"] == "execution_policy_conflict"


def test_execution_binding_immutable_and_factor_requirement_exact():
    resolver = EvidenceExecutionResolver(TradingCalendarBindings())
    resolver.register(binding())
    resolver.register(binding())
    with pytest.raises(ValueError, match="immutable_execution_binding_conflict"):
        resolver.register(binding(calendar_version="2"))
    with pytest.raises(ValidationError):
        binding(policy=policy(required_factor_versions=[{"name": "ma5", "version": "1"}]))
    with pytest.raises(ValidationError):
        binding(factors=[factor(), factor()])


def test_registry_version_drift_blocks(monkeypatch):
    from app.services import evidence_execution

    calendars = TradingCalendarBindings()
    calendars.register(calendar())
    resolver = EvidenceExecutionResolver(calendars)
    resolver.register(binding())
    monkeypatch.setattr(evidence_execution, "get_engine_factor", lambda name: None)
    assert resolver.resolve(policy())["blocker"] == "factor_registry_version_unavailable"


@pytest.mark.parametrize("changes", [{"timezone": "Asia/Shanghai"},
    {"trading_weekdays": [True]}, {"additional_trading_days": ["2026-09-07"]},
    {"holidays": ["2025-12-31"]}, {"coverage_end": "2027-01-01"}])
def test_calendar_metadata_conflict_rejected(changes):
    with pytest.raises(ValidationError):
        calendar(**changes)
