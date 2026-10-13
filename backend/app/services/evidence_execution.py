"""Explicit execution bindings only; no current-calendar fallback or evidence collection."""
from datetime import date, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, StrictInt, model_validator

from app.factors.engine import FactorRequest
from app.factors.registry import get_engine_factor
from app.services.evidence_policy import EvidencePolicy, PolicyModel


class TradingCalendarContract(PolicyModel):
    calendar_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    market: Literal["CN", "HK", "US"]
    timezone: str = Field(min_length=1)
    source: tuple[str, ...] = Field(min_length=1)
    effective_from: date
    effective_to: date
    coverage_start: date
    coverage_end: date
    # Freeze the actual schedule, not a pointer to the current global calendar.
    trading_weekdays: tuple[StrictInt, ...] = Field(min_length=1)
    holidays: tuple[date, ...]
    additional_trading_days: tuple[date, ...]

    @model_validator(mode="after")
    def validate_schedule(self):
        ZoneInfo(self.timezone)
        if self.timezone != {"CN": "Asia/Shanghai", "HK": "Asia/Hong_Kong", "US": "America/New_York"}[self.market]:
            raise ValueError("calendar_market_timezone_conflict")
        if not self.effective_from <= self.coverage_start <= self.coverage_end <= self.effective_to:
            raise ValueError("calendar_period_conflict")
        if (len(set(self.trading_weekdays)) != len(self.trading_weekdays)
                or any(isinstance(day, bool) or not 0 <= day <= 6 for day in self.trading_weekdays)):
            raise ValueError("calendar_weekdays_invalid")
        if (len(set(self.holidays)) != len(self.holidays)
                or len(set(self.additional_trading_days)) != len(self.additional_trading_days)
                or set(self.holidays) & set(self.additional_trading_days)):
            raise ValueError("calendar_day_conflict")
        if any(not self.coverage_start <= day <= self.coverage_end
               for day in self.holidays + self.additional_trading_days):
            raise ValueError("calendar_day_outside_coverage")
        if any(not value.strip() or value.lower() in {"latest", "unknown", "default"}
               for value in (self.calendar_id, self.version, *self.source)):
            raise ValueError("explicit_calendar_metadata_required")
        return self


class TradingCalendarBindings:
    def __init__(self):
        self._versions: dict[tuple[str, str], TradingCalendarContract] = {}

    def register(self, calendar: TradingCalendarContract) -> None:
        calendar = TradingCalendarContract.model_validate_json(calendar.model_dump_json())
        key = (calendar.calendar_id, calendar.version)
        existing = self._versions.get(key)
        if existing is not None and existing != calendar:
            raise ValueError("immutable_calendar_version_conflict")
        self._versions[key] = calendar

    def get(self, market: str, calendar_id: str, version: str) -> TradingCalendarContract | None:
        item = self._versions.get((calendar_id, version))
        return item if item is not None and item.market == market else None

    def resolve_previous_trading_day(self, *, market: str, calendar_id: str,
                                     version: str, date: date) -> dict:
        item = self.get(market, calendar_id, version)
        if item is None:
            return {"status": "BLOCKED", "blocker": "calendar_binding_missing"}
        if type(date) is not type(item.coverage_start) or not item.coverage_start <= date <= item.coverage_end:
            return {"status": "BLOCKED", "blocker": "calendar_date_outside_coverage"}
        day = date
        while day > item.coverage_start:
            day -= timedelta(days=1)
            if day in item.additional_trading_days or (
                    day.weekday() in item.trading_weekdays and day not in item.holidays):
                return {"status": "READY", "blocker": None, "previous_trading_day": day.isoformat(),
                        "calendar_id": item.calendar_id, "version": item.version, "source": list(item.source)}
        return {"status": "BLOCKED", "blocker": "previous_day_outside_calendar_coverage"}


class FactorParameters(PolicyModel):
    period: int | None = Field(strict=True)


class FactorIdentityContract(PolicyModel):
    registry_namespace: Literal["market_factor_engine"]
    registry_key: str = Field(min_length=1)
    version: int = Field(ge=1, strict=True)
    parameters: FactorParameters
    output_component: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self):
        metadata = get_engine_factor(self.registry_key)
        if metadata is None or metadata.name != self.registry_key or metadata.version != self.version:
            raise ValueError("exact_registry_identity_unavailable")
        # Null may not silently invoke today's default period for old evidence.
        if self.registry_key != "macd" and self.parameters.period is None:
            raise ValueError("resolved_period_required")
        outputs, _, _ = FactorRequest(self.registry_key, self.parameters.period).definition()
        if self.output_component not in outputs:
            raise ValueError("factor_output_identity_conflict")
        return self


class PolicyExecutionBinding(PolicyModel):
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    # Exact serialized policy pins every field, not merely the mutable caller object.
    policy: EvidencePolicy
    calendar_id: str = Field(min_length=1)
    calendar_version: str = Field(min_length=1)
    factors: tuple[FactorIdentityContract, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_policy_identity(self):
        if (self.policy_id, self.policy_version) != (self.policy.policy_id, self.policy.version):
            raise ValueError("execution_policy_identity_conflict")
        names = [item.registry_key for item in self.factors]
        if len(names) != len(set(names)):
            raise ValueError("ambiguous_factor_binding")
        expected = {(item.name, item.version) for item in self.policy.required_factor_versions}
        actual = {(item.registry_key, str(item.version)) for item in self.factors}
        if expected != actual:
            raise ValueError("policy_factor_identity_conflict")
        if self.calendar_id != self.policy.trading_calendar:
            raise ValueError("policy_calendar_identity_conflict")
        return self


class EvidenceExecutionResolver:
    """Explicit startup registration; no production bindings are installed here."""

    def __init__(self, calendars: TradingCalendarBindings):
        self.calendars = calendars
        self._bindings: dict[tuple[str, str], PolicyExecutionBinding] = {}

    def register(self, binding: PolicyExecutionBinding) -> None:
        binding = PolicyExecutionBinding.model_validate_json(binding.model_dump_json())
        key = (binding.policy_id, binding.policy_version)
        previous = self._bindings.get(key)
        if previous is not None and previous != binding:
            raise ValueError("immutable_execution_binding_conflict")
        self._bindings[key] = binding

    def resolve(self, policy: EvidencePolicy) -> dict:
        binding = self._bindings.get((policy.policy_id, policy.version))
        if binding is None:
            return {"status": "BLOCKED", "blocker": "execution_binding_missing"}
        if binding.policy != policy or policy.status != "ACTIVE":
            return {"status": "BLOCKED", "blocker": "execution_policy_conflict"}
        calendar = self.calendars.get(policy.market, binding.calendar_id, binding.calendar_version)
        if calendar is None:
            return {"status": "BLOCKED", "blocker": "calendar_binding_missing"}
        # Definition checks only; never execute Engine.compute or collect snapshots.
        try:
            for identity in binding.factors:
                FactorIdentityContract.model_validate_json(identity.model_dump_json())
        except ValueError:
            return {"status": "BLOCKED", "blocker": "factor_registry_version_unavailable"}
        return {"status": "READY", "blocker": None, "policy_id": policy.policy_id,
                "policy_version": policy.version, "calendar_binding": calendar.model_dump(mode="json"),
                "factor_identity_binding": [item.model_dump(mode="json") for item in binding.factors]}
