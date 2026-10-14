"""Canonical artifacts are frozen copies, never production policy installation."""
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from test_evidence_execution import binding, calendar
from test_evidence_policy import policy

from app.market_calendar import CALENDARS
from app.market_session import MarketRuntimeSignal, get_calendar_session, get_market_session
from app.services.evidence_execution import (
    EvidenceExecutionResolver,
    TradingCalendarBindings,
    TradingCalendarContract,
)

REVIEWED_HASHES = {
    "CN": "62c1d558ab30fd3c171754ac17954614358a1d9c70ffb158b60fa4a54b8acc86",
    "US": "cfb976ea41ff8037ab0dd5225f061dcb960976cd404bcd10eae2bb74a1084d76",
    "HK": "945fbd11e669fc27d1c76712969871a7151d854da1547f6c05fd71a4fa733b91",
}


@pytest.mark.parametrize("market", ["CN", "US", "HK"])
def test_canonical_artifact_identity_and_single_source(market):
    item = TradingCalendarContract.from_canonical(market)
    source = CALENDARS[market]
    assert item.calendar_id == source.calendar_id and item.version == "2026-v1"
    assert item.content_hash == item.calculated_hash()
    assert item.content_hash == REVIEWED_HASHES[market]
    assert item.session == source.session and set(item.half_days) == source.half_days
    assert item.early_close == source.early_close
    assert item.coverage_start == date(2026, 1, 1) and item.coverage_end == date(2026, 12, 31)
    assert TradingCalendarContract.model_validate_json(item.model_dump_json()) == item


def test_canonical_order_and_version_label_independence():
    first = calendar(holidays=["2026-09-07", "2026-12-25"], source=["b", "a"])
    payload = dict(reversed(list(first.model_dump(exclude={"content_hash"}).items())))
    payload.update(holidays=list(reversed(payload["holidays"])), source=["a", "b"], trading_weekdays=[4, 3, 2, 1, 0])
    second = TradingCalendarContract.freeze(**payload)
    assert first.canonical_json() == second.canonical_json()
    assert first.content_hash == second.content_hash
    assert calendar(version="2").content_hash == calendar().content_hash
    registry = TradingCalendarBindings()
    registry.register(first)
    registry.register(second)


@pytest.mark.parametrize("change", [
    {"holidays": []}, {"half_days": ["2026-11-27"], "early_close": "13:00"},
    {"early_close": "14:00"}, {"coverage_end": "2026-12-30"},
    {"source": ["different-official-reference"]}, {"source_family": "different-family"},
    {"additional_trading_days": ["2026-10-10"]}, {"trading_weekdays": [0, 1, 2, 3]},
])
def test_behavior_and_provenance_changes_change_hash(change):
    assert calendar(**change).content_hash != calendar().content_hash


@pytest.mark.parametrize("field,value", [
    ("regular_windows", [["09:31", "16:00"]]), ("pre_open_start", "05:00"),
    ("post_market_end", "19:00"), ("half_day_post_market_end", "16:00"),
    ("closing_auction_minutes", 10), ("overnight_unverified_from", "2026-12-07"),
    ("overnight_before", "03:00"), ("overnight_after", "22:00"),
])
def test_session_fields_are_frozen_content(field, value):
    item = calendar()
    session = item.session.model_dump(mode="json") | {field: value}
    assert calendar(session=session).content_hash != item.content_hash


def test_hash_tampering_and_legacy_payload_rejected():
    payload = calendar().model_dump(mode="json")
    with pytest.raises(ValidationError, match="calendar_content_hash_mismatch"):
        TradingCalendarContract.model_validate(payload | {"content_hash": "0" * 64})
    for field in ("content_hash", "session", "half_days", "early_close", "source_family"):
        legacy = payload.copy()
        legacy.pop(field)
        with pytest.raises(ValidationError):
            TradingCalendarContract.model_validate(legacy)
    with pytest.raises(ValidationError):
        calendar(timezone="UTC")


def test_half_day_membership_changes_hash_with_same_close():
    first = calendar(half_days=["2026-11-27"], early_close="13:00")
    second = calendar(half_days=["2026-12-24"], early_close="13:00")
    assert first.content_hash != second.content_hash


def test_execution_hash_mismatch_and_no_latest_selection():
    registry = TradingCalendarBindings()
    registry.register(calendar(version="2"))
    resolver = EvidenceExecutionResolver(registry)
    resolver.register(binding())
    assert resolver.resolve(policy())["status"] == "BLOCKED"
    registry.register(calendar())
    assert resolver.resolve(policy())["status"] == "READY"
    other = EvidenceExecutionResolver(registry)
    other.register(binding(calendar_content_hash="0" * 64))
    assert other.resolve(policy())["status"] == "BLOCKED"


@pytest.mark.parametrize("market,day,clock,state", [
    ("CN", "2026-10-08", "12:00", "break"), ("CN", "2026-10-01", "10:00", "holiday"),
    ("US", "2026-11-27", "13:01", "post_market"), ("US", "2026-12-07", "02:00", "unknown"),
    ("HK", "2026-12-24", "12:01", "post_market"), ("HK", "2026-12-24", "13:00", "closed"),
])
def test_replay_does_not_consult_runtime_or_current_calendar(monkeypatch, market, day, clock, state):
    item = TradingCalendarContract.from_canonical(market)
    now = datetime.fromisoformat(f"{day}T{clock}").replace(tzinfo=ZoneInfo(item.timezone))
    expected = get_market_session(market, now, runtime_signal=MarketRuntimeSignal(market, "unknown", now, "fixture"))
    assert expected.runtime_status == "unknown"
    monkeypatch.setitem(CALENDARS, market, None)
    registry = TradingCalendarBindings()
    registry.register(item)
    result = registry.resolve_session(market=market, calendar_id=item.calendar_id, version=item.version,
                                     content_hash=item.content_hash, now=now)
    assert result["session"]["session_state"] == state
    assert result["session"]["runtime_status"] == "unavailable"
    assert result["session"]["calendar_coverage"]["content_hash"] == item.content_hash
    assert get_calendar_session(item, now).half_day == (day in {str(d) for d in item.half_days})


def test_half_day_is_previous_session_and_hash_coverage_gates():
    item = TradingCalendarContract.from_canonical("US")
    registry = TradingCalendarBindings()
    registry.register(item)
    args = dict(market="US", calendar_id=item.calendar_id, version=item.version, content_hash=item.content_hash)
    assert registry.resolve_previous_trading_day(**args, date=date(2026, 11, 30))["previous_trading_day"] == "2026-11-27"
    for changes in ({"version": "missing"}, {"content_hash": "0" * 64}, {"date": date(2027, 1, 1)}):
        assert registry.resolve_previous_trading_day(**(args | {"date": date(2026, 10, 9)} | changes))["status"] == "BLOCKED"
    parsed = json.loads(item.canonical_json())
    assert parsed["session"]["regular_windows"] == [["09:30:00", "16:00:00"]]
