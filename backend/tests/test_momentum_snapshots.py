"""Isolated fixture artifacts only; no provider or production database access."""
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.services import momentum_snapshots as module
from app.services.momentum_snapshots import (
    MetricEvidence,
    MomentumIdentity,
    MomentumSnapshotRecord,
    MomentumSnapshotStore,
)

NOW = datetime(2026, 9, 16, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz is None else NOW.astimezone(tz)
    monkeypatch.setattr(module, "datetime", Clock)


def fixture_record(**changes):
    return MomentumSnapshotRecord.model_validate(dict(
        symbol="AAPL.US", market="US", trading_date=date(2026, 9, 14),
        input_contract_id="fixture-input", input_contract_version="v1", calculation_version="fixture-v1",
        calendar_id="fixture-calendar", calendar_version="v1", calendar_content_hash="a" * 64,
        universe_id="fixture-universe", universe_version="v1", universe_content_hash="b" * 64,
        score_profile_id=None, score_profile_version=None,
        session_timestamp=NOW - timedelta(days=1), generated_at=NOW - timedelta(hours=1),
        available_at=None, knowledge_cutoff=None, source="isolated-fixture", provider=None,
        input_references=("fixture-ref",), adjustment_method=None, price_basis=None, volume_unit=None,
        source_vintage=None, source_revision=None, pit_status="BLOCKED", overall_status="BLOCKED",
        blockers=("input_contract_unverified",), metric_statuses=(
            MetricEvidence(metric="volume_ratio_20", status="BLOCKED", blockers=("volume_unit_unknown",)),
            MetricEvidence(metric="strength_score", status="UNAVAILABLE"),
        ),
    ) | changes)


def identity(record):
    return MomentumIdentity.model_validate({key: getattr(record, key) for key in MomentumIdentity.model_fields})


def test_empty_read_is_non_creating(tmp_path):
    store = MomentumSnapshotStore(tmp_path)
    assert store.get_by_snapshot_id("missing") is None
    assert store.query_exact(identity(fixture_record()), as_of=NOW) == ()
    assert not store.path.exists()
    assert not (tmp_path / "user_data").exists()


def test_immutable_round_trip_and_idempotent_insert(tmp_path):
    store = MomentumSnapshotStore(tmp_path)
    original = fixture_record()
    saved = store.save(original)
    assert saved.stored_at == NOW
    assert saved.snapshot_id == original.snapshot_id
    content = store.path.read_bytes()
    assert store.save(original) == saved
    assert store.save(saved) == saved
    assert store.path.read_bytes() == content
    assert store.get_by_snapshot_id(saved.snapshot_id) == saved
    assert MomentumSnapshotRecord.model_validate_json(saved.model_dump_json()) == saved
    with pytest.raises(ValidationError):
        saved.price_basis = "invented"
    with pytest.raises(ValidationError):
        saved.metric_statuses[0].status = "READY"


def test_identity_and_revision_are_deterministic(tmp_path):
    record = fixture_record()
    reordered = fixture_record(metric_statuses=tuple(reversed(record.metric_statuses)))
    assert record.snapshot_id == reordered.snapshot_id
    assert record.snapshot_id == fixture_record().snapshot_id
    changed = fixture_record(source_revision="fixture-r2")
    assert changed.logical_key == record.logical_key
    assert changed.revision != record.revision
    store = MomentumSnapshotStore(tmp_path)
    store.save(record)
    store.save(changed)
    assert len(store.query_exact(identity(record))) == 2
    assert store.get_by_snapshot_id(record.snapshot_id).source_revision is None
    assert store.get_by_snapshot_id(changed.snapshot_id).source_revision == "fixture-r2"


def test_changed_results_never_overwrite_same_logical_calculation(tmp_path):
    record = fixture_record()
    revised = fixture_record(close=123, metric_statuses=(*record.metric_statuses,
        MetricEvidence(metric="close", status="PARTIAL", warnings=("price_basis_unknown",)),))
    store = MomentumSnapshotStore(tmp_path)
    store.save(record)
    store.save(revised)
    assert record.logical_key == revised.logical_key
    assert record.snapshot_id != revised.snapshot_id
    assert len(store.query_exact(identity(record))) == 2
    assert store.get_by_snapshot_id(record.snapshot_id).close is None


@pytest.mark.parametrize("field,value", [
    ("calendar_id", "other"), ("calendar_version", "v2"), ("calendar_content_hash", "c" * 64),
    ("universe_id", "other"), ("universe_version", "v2"), ("universe_content_hash", "c" * 64),
    ("input_contract_id", "other"), ("input_contract_version", "v2"),
    ("calculation_version", "v2"), ("market", "HK"), ("symbol", "MSFT.US"),
    ("trading_date", date(2026, 9, 13)),
])
def test_exact_identity_never_falls_back(tmp_path, field, value):
    record = fixture_record()
    store = MomentumSnapshotStore(tmp_path)
    store.save(record)
    changed = identity(record).model_dump() | {field: value}
    assert store.query_exact(MomentumIdentity.model_validate(changed)) == ()


def test_exact_score_profile_pair(tmp_path):
    record = fixture_record()
    store = MomentumSnapshotStore(tmp_path)
    store.save(record)
    other = identity(record).model_dump() | {"score_profile_id": "fixture-score", "score_profile_version": "v1"}
    assert store.query_exact(MomentumIdentity.model_validate(other)) == ()
    with pytest.raises(ValidationError, match="score_profile_identity_incomplete"):
        fixture_record(score_profile_id="profile")
    with pytest.raises(ValidationError, match="score_profile_not_selected"):
        fixture_record(strength_score=0.5, metric_statuses=(MetricEvidence(metric="strength_score", status="PARTIAL"),))


@pytest.mark.parametrize("field", ["calendar_id", "calendar_version", "calendar_content_hash",
                                  "universe_id", "universe_version", "universe_content_hash",
                                  "input_contract_id", "input_contract_version"])
def test_required_identity_cannot_be_omitted(field):
    data = fixture_record().model_dump()
    data.pop(field)
    with pytest.raises(ValidationError):
        MomentumSnapshotRecord.model_validate(data)


def test_null_unknown_evidence_stays_blocked_and_statuses_independent(tmp_path):
    record = fixture_record(
        close=100, price_basis="fixture-split-only",
        metric_statuses=(*fixture_record().metric_statuses,
            MetricEvidence(metric="close", status="READY", evidence_refs=("fixture-ref",)),),
        overall_status="PARTIAL",
    )
    store = MomentumSnapshotStore(tmp_path)
    saved = store.save(record)
    assert saved.overall_status == "PARTIAL"  # Explicit; not max/min of metric statuses.
    assert {item.metric: item.status for item in saved.metric_statuses} == {
        "close": "READY", "volume_ratio_20": "BLOCKED", "strength_score": "UNAVAILABLE"}
    assert saved.volume_unit is None and saved.available_at is None
    assert store.query_exact(identity(record), as_of=NOW) == ()
    with pytest.raises(ValidationError, match="metric_price_basis_unknown"):
        fixture_record(close=100, metric_statuses=(MetricEvidence(metric="close", status="READY", evidence_refs=("ref",)),))
    with pytest.raises(ValidationError, match="ready_envelope_incomplete"):
        fixture_record(overall_status="READY")
    with pytest.raises(ValidationError, match="pit_evidence_incomplete"):
        fixture_record(pit_status="READY")


def test_unknown_volume_cannot_claim_ready_ratio():
    with pytest.raises(ValidationError, match="metric_volume_unit_unknown"):
        fixture_record(price_basis="fixture-split-only", volume_ratio_20=2,
                       metric_statuses=(MetricEvidence(metric="volume_ratio_20", status="READY", evidence_refs=("ref",)),))


@pytest.mark.parametrize("field", ["session_timestamp", "generated_at", "available_at", "knowledge_cutoff", "stored_at"])
def test_naive_timestamp_rejected(field):
    with pytest.raises(ValidationError):
        fixture_record(**{field: datetime(2026, 9, 14)})


def test_aware_offsets_normalized_and_hash_identical(tmp_path):
    record = fixture_record()
    shifted = fixture_record(generated_at=record.generated_at.astimezone(timezone(timedelta(hours=8))))
    assert shifted.generated_at.utcoffset() == timedelta(0)
    assert shifted.snapshot_id == record.snapshot_id
    saved = MomentumSnapshotStore(tmp_path).save(shifted)
    assert saved.stored_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize("future_field", ["generated_at", "available_at", "stored_at"])
def test_as_of_three_time_gates(tmp_path, future_field):
    record = fixture_record(available_at=NOW - timedelta(minutes=30))
    if future_field == "generated_at":
        record = fixture_record(generated_at=NOW - timedelta(minutes=5), available_at=NOW - timedelta(minutes=1))
    elif future_field == "available_at":
        record = fixture_record(available_at=NOW - timedelta(minutes=1))
    store = MomentumSnapshotStore(tmp_path)
    store.save(record)
    cutoff = NOW - timedelta(minutes=10) if future_field != "stored_at" else NOW - timedelta(seconds=1)
    assert store.query_exact(identity(record), as_of=cutoff) == ()
    assert len(store.query_exact(identity(record), as_of=NOW)) == 1
    with pytest.raises(ValueError, match="aware_as_of_required"):
        store.query_exact(identity(record), as_of=datetime(2026, 9, 16))


def test_future_save_rejected_without_creating_db(tmp_path):
    store = MomentumSnapshotStore(tmp_path)
    with pytest.raises(ValueError, match="future_snapshot"):
        store.save(fixture_record(available_at=NOW + timedelta(days=1)))
    assert not store.path.exists()


def test_payload_tamper_detected(tmp_path):
    store = MomentumSnapshotStore(tmp_path)
    record = store.save(fixture_record())
    # Corruption fixture, never an application update operation.
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE snapshots SET payload=replace(payload, 'isolated-fixture', 'tampered')")
    with pytest.raises(ValueError, match="snapshot_identity_payload_conflict"):
        store.get_by_snapshot_id(record.snapshot_id)
    with pytest.raises(ValueError, match="immutable_snapshot_conflict"):
        store.save(fixture_record())


def test_concurrent_same_insert_idempotent(tmp_path):
    store = MomentumSnapshotStore(tmp_path)
    record = fixture_record()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: store.save(record), range(4)))
    assert all(result == results[0] for result in results)
    assert len(store.query_exact(identity(record))) == 1


@pytest.mark.parametrize("value", ["*", "latest", "current", "UNKNOWN", "BLOCKED"])
def test_implicit_identity_labels_rejected(value):
    with pytest.raises(ValidationError, match="exact_identity_required"):
        fixture_record(calendar_version=value)


def test_explicit_ready_fixture_and_null_price_guard(tmp_path):
    data = dict(price_basis="fixture-split-only", available_at=NOW - timedelta(minutes=30),
                knowledge_cutoff=NOW - timedelta(days=1), source_vintage="fixture-v1",
                pit_status="READY", overall_status="READY", blockers=(),
                close=100, metric_statuses=(MetricEvidence(metric="close", status="READY", evidence_refs=("fixture-ref",)),))
    record = fixture_record(**data)
    store = MomentumSnapshotStore(tmp_path)
    saved = store.save(record)
    assert store.query_exact(identity(record), as_of=NOW) == (saved,)
    assert saved.to_dict()["snapshot_id"] == saved.snapshot_id
    assert saved.to_dict()["stored_at"].endswith("Z")
    with pytest.raises(ValidationError):
        fixture_record(**(data | {"price_basis": None}))


@pytest.mark.parametrize("changes", [
    {"close": float("nan")}, {"volume": float("inf")},
    {"metric_statuses": (MetricEvidence(metric="unknown", status="BLOCKED"),)},
    {"metric_statuses": (MetricEvidence(metric="close", status="BLOCKED"),) * 2},
    {"close": 100},
    {"close": 100, "metric_statuses": (MetricEvidence(metric="close", status="READY"),)},
])
def test_invalid_values_or_metric_metadata_rejected(changes):
    with pytest.raises(ValidationError):
        fixture_record(**changes)


def test_stored_at_is_store_owned_and_not_hashed(tmp_path):
    record = fixture_record()
    supplied = fixture_record(stored_at=NOW - timedelta(minutes=1))
    assert supplied.snapshot_id == record.snapshot_id
    saved = MomentumSnapshotStore(tmp_path).save(supplied)
    assert saved.stored_at == NOW


def test_read_queries_do_not_write(tmp_path):
    store = MomentumSnapshotStore(tmp_path)
    record = store.save(fixture_record())
    before = store.path.read_bytes()
    assert store.get_by_snapshot_id(record.snapshot_id) == record
    assert store.query_exact(identity(record)) == (record,)
    assert store.path.read_bytes() == before
