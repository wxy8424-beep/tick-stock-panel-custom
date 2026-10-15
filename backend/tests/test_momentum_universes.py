"""Universe contracts use isolated fixture membership, never live directories."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.services import momentum_universes as module
from app.services.momentum_snapshots import MomentumIdentity
from app.services.momentum_universes import (
    ExclusionRules,
    MomentumUniverseDefinition,
    MomentumUniverseIdentity,
    MomentumUniverseMember,
    MomentumUniverseStore,
)

NOW = datetime(2026, 9, 16, 12, tzinfo=UTC)
START = NOW - timedelta(days=5)
END = NOW + timedelta(days=5)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz is None else NOW.astimezone(tz)
    monkeypatch.setattr(module, "datetime", Clock)


def member(symbol="AAPL.US", **changes):
    return MomentumUniverseMember.model_validate(dict(
        symbol=symbol, market="US", instrument_type="COMMON_STOCK", membership_status="INCLUDED",
        effective_from=START, effective_to=END, evidence_reference="fixture-security-evidence", reason=None,
    ) | changes)


def universe(**changes):
    return MomentumUniverseDefinition.model_validate(dict(
        universe_id="fixture-us-common", universe_version="v1", market="US", universe_type="CUSTOM",
        effective_from=START, effective_to=END, generated_at=NOW - timedelta(hours=2),
        available_at=None, source="isolated-fixture", source_kind="CUSTOM", source_version="fixture-v1",
        source_references=("fixture-directory-ref",), membership_vintage=None, availability_evidence=None,
        allowed_instrument_types=("COMMON_STOCK",), exclusion_rules=ExclusionRules(instrument_types=("ETF",)),
        members=(member(), member("SPY.US", instrument_type="ETF", membership_status="EXCLUDED", reason="etf_excluded")),
        expected_count=2, effective_count=1, excluded_count=1, missing_count=0,
        coverage_evidence="fixture-coverage-ref", pit_status="BLOCKED", status="PARTIAL",
        blockers=("historical_membership_vintage_unknown",), warnings=(),
    ) | changes)


def ready(**changes):
    return universe(**(dict(available_at=NOW - timedelta(hours=1), membership_vintage="fixture-vintage-v1",
                           availability_evidence="fixture-availability-ref", pit_status="READY",
                           status="READY", blockers=()) | changes))


def test_hash_order_and_serialization():
    record = universe()
    reordered = universe(members=tuple(reversed(record.members)))
    assert record.content_hash == reordered.content_hash
    assert record.canonical_payload() == reordered.canonical_payload()
    assert MomentumUniverseDefinition.model_validate_json(record.model_dump_json()) == record
    assert record.to_dict()["content_hash"] == record.content_hash
    assert record.identity.content_hash == record.content_hash


@pytest.mark.parametrize("changes", [
    {"members": (member("MSFT.US"), member("SPY.US", instrument_type="ETF", membership_status="EXCLUDED", reason="etf_excluded"))},
    {"members": (member(instrument_type="ADR"), member("SPY.US", instrument_type="ETF", membership_status="EXCLUDED", reason="etf_excluded")), "allowed_instrument_types": ("COMMON_STOCK", "ADR")},
    {"exclusion_rules": ExclusionRules(symbols=("NVDA.US",), instrument_types=("ETF",))},
    {"allowed_instrument_types": ("COMMON_STOCK", "ADR")},
    {"source_version": "fixture-v2"},
    {"effective_to": END - timedelta(days=1)},
])
def test_semantic_change_changes_hash(changes):
    assert universe(**changes).content_hash != universe().content_hash


def test_store_immutable_idempotent_and_revision(tmp_path):
    store = MomentumUniverseStore(tmp_path)
    original = universe()
    saved = store.save(original)
    assert saved.stored_at == NOW
    assert saved.content_hash == original.content_hash
    before = store.path.read_bytes()
    assert store.save(original) == saved
    assert store.save(saved) == saved
    assert store.get_by_identity(saved.identity) == saved
    assert store.path.read_bytes() == before
    revised = universe(universe_version="v2", source_version="fixture-v2")
    store.save(revised)
    assert store.get_by_identity(original.identity) == saved
    assert store.get_by_identity(revised.identity).universe_version == "v2"
    with pytest.raises(ValueError, match="immutable_universe_conflict"):
        store.save(universe(source_version="different-content-same-version"))
    assert store.get_by_identity(original.identity) == saved
    with pytest.raises(ValidationError):
        saved.members[0].instrument_type = "ETF"


@pytest.mark.parametrize("field,value", [("universe_id", "missing"), ("universe_version", "v999"),
                                        ("content_hash", "a" * 64), ("market", "HK")])
def test_exact_identity_no_fallback(tmp_path, field, value):
    store = MomentumUniverseStore(tmp_path)
    record = ready()
    store.save(record)
    requested = MomentumUniverseIdentity.model_validate(record.identity.model_dump() | {field: value})
    assert store.get_by_identity(requested) is None
    assert store.query_exact(requested, effective_at=NOW, as_of=NOW)["status"] == "UNAVAILABLE"


def test_hk_us_isolation_and_id_cannot_change_market(tmp_path):
    store = MomentumUniverseStore(tmp_path)
    us = ready()
    hk = ready(universe_id="fixture-hk-common", market="HK", members=(member("700.HK", market="HK"),),
               expected_count=1, excluded_count=0)
    store.save(us)
    store.save(hk)
    assert us.content_hash != hk.content_hash
    assert store.query_exact(hk.identity, effective_at=NOW, as_of=NOW)["universe"].market == "HK"
    with pytest.raises(ValueError, match="universe_scope_conflict"):
        store.save(ready(universe_id=us.universe_id, universe_version="v2", market="HK",
                         members=hk.members, expected_count=1, excluded_count=0))
    with pytest.raises(ValidationError, match="member_market_conflict"):
        universe(members=hk.members, expected_count=1, excluded_count=0)


def test_watchlist_and_dynamic_sets_not_market_wide(tmp_path):
    watch = universe(universe_type="WATCHLIST", source_kind="WATCHLIST")
    assert watch.content_hash != universe().content_hash
    with pytest.raises(ValidationError, match="market_wide_requires_directory"):
        universe(universe_type="MARKET_WIDE", source_kind="WATCHLIST")
    for kind in ("DYNAMIC_CANDIDATES", "DISPLAY_SET", "CUSTOM"):
        with pytest.raises(ValidationError, match="market_wide_requires_directory"):
            universe(universe_type="MARKET_WIDE", source_kind=kind)
    store = MomentumUniverseStore(tmp_path)
    store.save(watch)
    with pytest.raises(ValueError, match="universe_scope_conflict"):
        store.save(universe(universe_version="v2"))


@pytest.mark.parametrize("instrument", ["COMMON_STOCK", "ADR", "ETF", "REIT", "PREFERRED", "WARRANT", "RIGHTS", "BOND", "FUND", "OTHER", "UNKNOWN"])
def test_instrument_types_explicit_and_not_inferred(instrument):
    value = member(instrument_type=instrument, membership_status="UNRESOLVED", reason="fixture-unverified")
    assert value.instrument_type == instrument
    if instrument != "COMMON_STOCK":
        with pytest.raises(ValidationError, match="ineligible_member"):
            universe(members=(member(instrument_type=instrument),), expected_count=1, excluded_count=0)


def test_missing_evidence_and_unknown_instrument_not_ready():
    missing = universe(members=(member(evidence_reference=None),), expected_count=1, excluded_count=0,
                       blockers=("membership_evidence_missing",))
    assert missing.status == "PARTIAL"
    with pytest.raises(ValidationError, match="membership_evidence_missing"):
        ready(members=missing.members, expected_count=1, excluded_count=0)
    unresolved = member(instrument_type="UNKNOWN", membership_status="UNRESOLVED", reason="instrument_unverified")
    partial = universe(members=(unresolved,), effective_count=0, excluded_count=0, expected_count=1)
    assert partial.unresolved_count == 1
    with pytest.raises(ValidationError):
        ready(members=partial.members, effective_count=0, excluded_count=0, expected_count=1)


def test_coverage_unknown_and_count_consistency():
    record = universe(expected_count=None, missing_count=None, warnings=("expected_count_unknown",))
    assert record.expected_count is None
    with pytest.raises(ValidationError, match="expected_count_unknown"):
        universe(expected_count=None, missing_count=None)
    with pytest.raises(ValidationError):
        ready(expected_count=None, missing_count=None, warnings=("expected_count_unknown",))
    with pytest.raises(ValidationError, match="coverage_count_conflict"):
        universe(missing_count=1)
    with pytest.raises(ValidationError, match="coverage_count_conflict"):
        universe(effective_count=2)
    partial = universe(expected_count=3, missing_count=1)
    assert partial.status == "PARTIAL"
    with pytest.raises(ValidationError):
        ready(expected_count=3, missing_count=1)


def test_effective_time_separate_from_knowledge_and_first_storage(tmp_path):
    store = MomentumUniverseStore(tmp_path)
    record = ready()
    store.save(record)
    assert store.query_exact(record.identity, effective_at=START, as_of=NOW)["status"] == "READY"
    assert store.query_exact(record.identity, effective_at=END, as_of=NOW)["status"] == "UNAVAILABLE"
    assert store.query_exact(record.identity, effective_at=START - timedelta(seconds=1), as_of=NOW)["status"] == "UNAVAILABLE"
    # Effective in the past is not evidence that this system knew the membership then.
    assert store.query_exact(record.identity, effective_at=START, as_of=NOW - timedelta(seconds=1))["status"] == "UNAVAILABLE"
    assert store.query_exact(record.identity, effective_at=START, as_of=START)["status"] == "UNAVAILABLE"
    assert store.query_exact(record.identity, effective_at=NOW, as_of=NOW)["universe"].stored_at == NOW


def test_unknown_availability_cannot_be_strict_pit(tmp_path):
    store = MomentumUniverseStore(tmp_path)
    record = universe()
    store.save(record)
    assert store.get_by_identity(record.identity).available_at is None
    assert store.query_exact(record.identity, effective_at=NOW, as_of=NOW)["status"] == "BLOCKED"
    with pytest.raises(ValidationError, match="pit_evidence_incomplete"):
        universe(pit_status="READY")


@pytest.mark.parametrize("field", ["effective_from", "effective_to", "generated_at", "available_at", "stored_at"])
def test_naive_times_rejected(field):
    with pytest.raises(ValidationError):
        universe(**{field: datetime(2026, 9, 16)})
    with pytest.raises(ValidationError):
        member(effective_from=datetime(2026, 9, 16))


def test_normalized_utc_and_store_owned_timestamp(tmp_path):
    record = universe(generated_at=(NOW - timedelta(hours=2)).astimezone(timezone(timedelta(hours=8))),
                      stored_at=NOW - timedelta(minutes=1))
    assert record.content_hash == universe().content_hash
    saved = MomentumUniverseStore(tmp_path).save(record)
    assert saved.generated_at.utcoffset() == timedelta(0)
    assert saved.stored_at == NOW


def test_duplicate_members_intervals_and_exclusions_rejected():
    with pytest.raises(ValidationError, match="duplicate_member"):
        universe(members=(member(), member()), effective_count=2, excluded_count=0)
    with pytest.raises(ValidationError, match="member_effective_period_incomplete"):
        universe(members=(member(effective_from=START + timedelta(days=1)),), expected_count=1, excluded_count=0)
    with pytest.raises(ValidationError, match="ineligible_member"):
        universe(exclusion_rules=ExclusionRules(symbols=("AAPL.US",)))


def test_empty_store_non_creating_and_readonly_queries(tmp_path):
    store = MomentumUniverseStore(tmp_path)
    record = ready()
    assert store.get_by_identity(record.identity) is None
    assert store.query_exact(record.identity, effective_at=NOW, as_of=NOW)["status"] == "UNAVAILABLE"
    assert not store.path.exists()
    store.save(record)
    before = store.path.read_bytes()
    store.query_exact(record.identity, effective_at=NOW, as_of=NOW)
    assert before == store.path.read_bytes()
    with pytest.raises(ValueError, match="aware_query_time_required"):
        store.query_exact(record.identity, effective_at=datetime(2026, 9, 16), as_of=NOW)


def test_snapshot_identity_binding_is_explicit_and_exact():
    record = ready()
    snapshot_identity = MomentumIdentity(symbol="AAPL.US", market="US", trading_date=NOW.date(),
        input_contract_id="fixture-input", input_contract_version="v1", calculation_version="fixture-calc",
        calendar_id="fixture-cal", calendar_version="v1", calendar_content_hash="a" * 64,
        universe_id=record.universe_id, universe_version=record.universe_version,
        universe_content_hash=record.content_hash, score_profile_id=None, score_profile_version=None)
    assert snapshot_identity.universe_content_hash == record.identity.content_hash


def test_concurrent_insert_idempotency_and_corruption(tmp_path):
    store = MomentumUniverseStore(tmp_path)
    record = universe()
    with ThreadPoolExecutor(max_workers=4) as pool:
        saved = list(pool.map(lambda _: store.save(record), range(4)))
    assert all(item == saved[0] for item in saved)
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE universes SET payload=replace(payload, 'isolated-fixture', 'corrupted')")
    with pytest.raises(ValueError, match="universe_payload_identity_conflict"):
        store.get_by_identity(record.identity)


def test_canonical_symbol_handling_and_normalized_duplicates():
    normalized = member(" aapl.us ")
    assert normalized.symbol == "AAPL.US"
    assert normalized == member()
    with pytest.raises(ValidationError, match="duplicate_member"):
        universe(members=(normalized, member()), effective_count=2, excluded_count=0)
    with pytest.raises(ValidationError, match="ineligible_member"):
        universe(exclusion_rules=ExclusionRules(symbols=(" aapl.us ",)))
    # HK source aliases are not invented or merged on a display-name guess.
    assert member("0700.HK", market="HK").symbol == "0700.HK"
    with pytest.raises(ValidationError, match="member_symbol_market_conflict"):
        member("700.HK")


@pytest.mark.parametrize("evidence", [None, "UNKNOWN", "unverified"])
def test_missing_member_evidence_cannot_claim_ready(evidence):
    with pytest.raises(ValidationError, match="membership_evidence_missing"):
        ready(members=(member(evidence_reference=evidence),), expected_count=1, excluded_count=0)


@pytest.mark.parametrize("field", ["generated_at", "available_at"])
def test_future_artifact_rejected_without_db(tmp_path, field):
    store = MomentumUniverseStore(tmp_path)
    with pytest.raises(ValueError, match="future_universe"):
        store.save(universe(**{field: NOW + timedelta(days=1)}))
    assert not store.path.exists()


@pytest.mark.parametrize("value", ["*", "latest", "current", "UNKNOWN"])
def test_exact_version_required(value):
    with pytest.raises(ValidationError, match="exact_universe_identity_required"):
        universe(universe_version=value)


def test_missing_version_and_wrong_hash_cannot_be_requested():
    with pytest.raises(ValidationError):
        MomentumUniverseIdentity(universe_id="fixture", market="US", content_hash="a" * 64)
    with pytest.raises(ValidationError):
        MomentumUniverseIdentity(universe_id="fixture", universe_version="v1", market="US", content_hash="bad-hash")


def test_ready_coverage_and_non_pit_artifacts_stay_separate(tmp_path):
    store = MomentumUniverseStore(tmp_path)
    partial = ready(expected_count=3, missing_count=1, status="PARTIAL")
    store.save(partial)
    assert store.query_exact(partial.identity, effective_at=NOW, as_of=NOW)["status"] == "PARTIAL"
    nonpit = universe(universe_version="v2", available_at=NOW - timedelta(hours=1))
    store.save(nonpit)
    assert store.query_exact(nonpit.identity, effective_at=NOW, as_of=NOW)["status"] == "BLOCKED"


def test_explicit_market_wide_and_index_scopes_are_declarations_only():
    broad = ready(universe_id="fixture-market-wide", universe_type="MARKET_WIDE", source_kind="DIRECTORY")
    index = ready(universe_id="fixture-index", universe_type="INDEX_CONSTITUENTS", source_kind="INDEX_CONSTITUENTS")
    assert broad.content_hash != index.content_hash
    with pytest.raises(ValidationError, match="universe_source_scope_conflict"):
        universe(universe_type="INDEX_CONSTITUENTS", source_kind="WATCHLIST")


def test_ready_requires_coverage_and_vintage_proof():
    for changes in ({"coverage_evidence": None}, {"source_version": None}, {"source": "UNKNOWN"},
                    {"source_references": ("UNKNOWN",)}, {"membership_vintage": None},
                    {"availability_evidence": None}):
        with pytest.raises(ValidationError):
            ready(**changes)


def test_empty_artifact_can_be_unavailable_but_not_ready(tmp_path):
    record = universe(members=(), expected_count=0, effective_count=0, excluded_count=0,
                      missing_count=0, status="UNAVAILABLE")
    store = MomentumUniverseStore(tmp_path)
    assert store.save(record).status == "UNAVAILABLE"
    with pytest.raises(ValidationError, match="ready_universe_evidence_incomplete"):
        ready(members=(), expected_count=0, effective_count=0, excluded_count=0)
