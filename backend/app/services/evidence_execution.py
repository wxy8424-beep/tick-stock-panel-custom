"""Explicit execution bindings only; no current-calendar fallback or evidence collection."""
import hashlib
import json
from datetime import date, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, StrictInt, model_validator

from app.factors.engine import FactorRequest
from app.factors.registry import get_engine_factor
from app.market_calendar import CALENDARS, MARKET_TIMEZONES, SessionRules
from app.services.evidence_policy import EvidencePolicy, PolicyModel


class CalendarContent(PolicyModel):
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
    session: SessionRules
    half_days: tuple[date, ...]
    early_close: time | None
    source_family: str = Field(min_length=1)
    source_updated_on: date

    @model_validator(mode="after")
    def validate_schedule(self):
        zone = ZoneInfo(self.timezone)
        if zone.key != MARKET_TIMEZONES[self.market]:
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
               for day in self.holidays + self.additional_trading_days + self.half_days):
            raise ValueError("calendar_day_outside_coverage")
        if (len(set(self.half_days)) != len(self.half_days) or set(self.half_days) & set(self.holidays)
                or any(day.weekday() not in self.trading_weekdays and day not in self.additional_trading_days
                       for day in self.half_days)):
            raise ValueError("invalid_half_day")
        if self.half_days and self.early_close is None:
            raise ValueError("half_day_close_required")
        if self.early_close is not None and (self.early_close.tzinfo is not None or not any(
                start < self.early_close <= end for start, end in self.session.regular_windows)):
            raise ValueError("invalid_early_close")
        if any(not value.strip() or value.strip().lower() in {"latest", "current", "unknown", "default", "*"}
               for value in (self.calendar_id, self.version, *self.source)):
            raise ValueError("explicit_calendar_metadata_required")
        return self

    def canonical_payload(self) -> dict:
        # ID/version label the artifact; the hash describes its complete content.
        payload = self.model_dump(mode="json", exclude={"calendar_id", "version", "content_hash"})
        for key in ("source", "holidays", "half_days", "additional_trading_days", "trading_weekdays"):
            payload[key] = sorted(payload[key])
        return payload

    def canonical_json(self) -> str:
        return json.dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def calculated_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


class TradingCalendarContract(CalendarContent):
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify_hash(self):
        if self.content_hash != self.calculated_hash():
            raise ValueError("calendar_content_hash_mismatch")
        return self

    def metadata(self) -> dict:
        return {"calendar_id": self.calendar_id, "version": self.version, "content_hash": self.content_hash,
                "coverage_start": self.coverage_start.isoformat(), "coverage_end": self.coverage_end.isoformat(),
                "source": list(self.source), "last_updated": self.source_updated_on.isoformat()}

    @classmethod
    def freeze(cls, **payload):
        content = CalendarContent.model_validate(payload)
        return cls(**content.model_dump(), content_hash=content.calculated_hash())

    @classmethod
    def from_canonical(cls, market: str):
        """Explicitly freeze the single source; never called as resolution fallback."""
        item = CALENDARS[market]
        return cls.freeze(calendar_id=item.calendar_id, version=item.version, market=item.market,
            timezone=item.timezone, source=item.sources, source_family="official_exchange",
            source_updated_on=item.last_updated, effective_from=item.coverage_start,
            effective_to=item.coverage_end, coverage_start=item.coverage_start, coverage_end=item.coverage_end,
            trading_weekdays=item.trading_weekdays, holidays=tuple(item.holidays),
            additional_trading_days=tuple(item.additional_trading_days),
            half_days=tuple(item.half_days), early_close=item.early_close,
            session=item.session)


class TradingCalendarBindings:
    def __init__(self):
        self._versions: dict[tuple[str, str], TradingCalendarContract] = {}

    def register(self, calendar: TradingCalendarContract) -> None:
        calendar = TradingCalendarContract.model_validate_json(calendar.model_dump_json())
        key = (calendar.calendar_id, calendar.version)
        existing = self._versions.get(key)
        if existing is not None:
            if existing.content_hash != calendar.content_hash:
                raise ValueError("immutable_calendar_version_conflict")
            return
        self._versions[key] = calendar

    def get(self, market: str, calendar_id: str, version: str,
            content_hash: str | None = None) -> TradingCalendarContract | None:
        item = self._versions.get((calendar_id, version))
        return item if (item is not None and item.market == market
                        and (content_hash is None or item.content_hash == content_hash)) else None

    def resolve_previous_trading_day(self, *, market: str, calendar_id: str,
                                     version: str, date: date, content_hash: str) -> dict:
        item = self.get(market, calendar_id, version, content_hash)
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
                        "calendar_id": item.calendar_id, "version": item.version,
                        "content_hash": item.content_hash, "source": list(item.source)}
        return {"status": "BLOCKED", "blocker": "previous_day_outside_calendar_coverage"}

    def resolve_session(self, *, market: str, calendar_id: str, version: str, content_hash: str, now) -> dict:
        from app.market_session import get_calendar_session

        item = self.get(market, calendar_id, version, content_hash)
        if item is None:
            return {"status": "BLOCKED", "blocker": "calendar_binding_missing"}
        result = get_calendar_session(item, now)
        if result.calendar_status != "covered":
            return {"status": "BLOCKED", "blocker": "calendar_date_outside_coverage"}
        return {"status": "READY", "blocker": None, "session": result.public_metadata()}


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
    calendar_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    factors: tuple[FactorIdentityContract, ...]

    @model_validator(mode="after")
    def validate_policy_identity(self):
        if (self.policy_id, self.policy_version) != (self.policy.policy_id, self.policy.version):
            raise ValueError("execution_policy_identity_conflict")
        names = [item.registry_key for item in self.factors]
        if len(names) != len(set(names)):
            raise ValueError("ambiguous_factor_binding")
        if self.policy.factor_enabled:
            expected = {(item.name, item.version) for item in self.policy.required_factor_versions}
            actual = {(item.registry_key, str(item.version)) for item in self.factors}
            if not self.factors or expected != actual:
                raise ValueError("policy_factor_identity_conflict")
        elif self.factors:
            raise ValueError("disabled_factor_binding_must_be_empty")
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
        calendar = self.calendars.get(policy.market, binding.calendar_id, binding.calendar_version,
                                      binding.calendar_content_hash)
        if calendar is None:
            return {"status": "BLOCKED", "blocker": "calendar_binding_missing"}
        # Definition checks only; never execute Engine.compute or collect snapshots.
        try:
            if policy.factor_enabled:
                for identity in binding.factors:
                    FactorIdentityContract.model_validate_json(identity.model_dump_json())
        except ValueError:
            return {"status": "BLOCKED", "blocker": "factor_registry_version_unavailable"}
        return {"status": "READY", "blocker": None, "policy_id": policy.policy_id,
                "policy_version": policy.version, "calendar_binding": calendar.model_dump(mode="json"),
                "factor_branch": "ENABLED" if policy.factor_enabled else "NOT_SELECTED",
                "factor_identity_binding": [item.model_dump(mode="json") for item in binding.factors]}
