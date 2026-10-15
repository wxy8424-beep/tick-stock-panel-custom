"""Additive contract references must preserve pre-extension frozen snapshot identities."""
import hashlib
import json
import sqlite3
from datetime import datetime

import pytest
from pydantic import ValidationError
from test_momentum_snapshots import NOW, fixture_record, identity

from app.services import momentum_snapshots as snapshots
from app.services.momentum_calculation_contracts import (
    CalculationIdentity,
    MomentumCalculationStore,
    ScoreProfileIdentity,
    candidate_calculation_v1,
    candidate_technical_profile_v1,
)
from app.services.momentum_snapshots import (
    MomentumIdentity,
    MomentumSnapshotRecord,
    MomentumSnapshotStore,
)

NEW_FIELDS = {"calculation_id", "calculation_content_hash", "score_profile_content_hash"}
OLD_IDENTITY_FIELDS = (
    "symbol", "market", "trading_date", "input_contract_id", "input_contract_version", "calculation_version",
    "calendar_id", "calendar_version", "calendar_content_hash", "universe_id", "universe_version",
    "universe_content_hash", "score_profile_id", "score_profile_version",
)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz is None else NOW.astimezone(tz)
    monkeypatch.setattr(snapshots, "datetime", Clock)


def legacy_payload():
    data = fixture_record().model_dump(mode="json", exclude={"stored_at", *NEW_FIELDS})
    data["metric_statuses"].sort(key=lambda item: item["metric"])
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    key = hashlib.sha256(json.dumps({key: data[key] for key in OLD_IDENTITY_FIELDS},
                                   sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    revision = hashlib.sha256(payload.encode()).hexdigest()
    return payload, key, revision


def test_legacy_payload_hash_identity_and_round_trip_unchanged():
    payload, key, revision = legacy_payload()
    record = MomentumSnapshotRecord.model_validate_json(payload)
    assert record.logical_key == key
    assert record.revision == revision
    assert record.snapshot_id == f"momentum-v1:{key}:{revision}"
    assert record.contract_binding_status == "LEGACY_INCOMPLETE"
    assert record.to_dict()["contract_binding_status"] == "LEGACY_INCOMPLETE"
    assert record.canonical_payload() == payload
    assert MomentumSnapshotRecord.model_validate_json(record.model_dump_json()).snapshot_id == record.snapshot_id


def test_old_database_is_readable_and_never_rewritten(tmp_path):
    store = MomentumSnapshotStore(tmp_path)
    store.path.parent.mkdir(parents=True)
    payload, key, revision = legacy_payload()
    snapshot_id = f"momentum-v1:{key}:{revision}"
    with sqlite3.connect(store.path) as db:
        db.execute("""CREATE TABLE snapshots (
            snapshot_id TEXT PRIMARY KEY, logical_key TEXT NOT NULL, revision TEXT NOT NULL,
            generated_at REAL NOT NULL, available_at REAL, stored_at TEXT NOT NULL,
            stored_epoch REAL NOT NULL, payload TEXT NOT NULL, UNIQUE(logical_key, revision))""")
        db.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?)", (
            snapshot_id, key, revision, fixture_record().generated_at.timestamp(), None,
            NOW.isoformat(), NOW.timestamp(), payload))
    before = store.path.read_bytes()
    record = store.get_by_snapshot_id(snapshot_id)
    assert record.contract_binding_status == "LEGACY_INCOMPLETE"
    assert store.query_exact(identity(record)) == (record,)
    assert store.path.read_bytes() == before
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT payload FROM snapshots").fetchone()[0] == payload


def test_new_exact_binding_resolves_and_never_falls_back_to_legacy(tmp_path):
    calculation = candidate_calculation_v1()
    profile = candidate_technical_profile_v1(calculation)
    definitions = MomentumCalculationStore(tmp_path)
    definitions.save(calculation)
    definitions.save(profile)
    record = fixture_record(calculation_version=calculation.calculation_version,
                            calculation_id=calculation.calculation_id, calculation_content_hash=calculation.content_hash,
                            score_profile_id=profile.score_profile_id, score_profile_version=profile.score_profile_version,
                            score_profile_content_hash=profile.content_hash)
    assert record.contract_binding_status == "EXACT"
    assert definitions.get_calculation(CalculationIdentity(calculation_id=record.calculation_id,
        calculation_version=record.calculation_version, content_hash=record.calculation_content_hash)).identity == calculation.identity
    assert definitions.get_score_profile(ScoreProfileIdentity(score_profile_id=record.score_profile_id,
        score_profile_version=record.score_profile_version, content_hash=record.score_profile_content_hash)).identity == profile.identity
    # Exact binding is not a claim that this blocked profile/data is executable.
    assert record.overall_status == "BLOCKED" and profile.execution_eligibility == "BLOCKED"
    store = MomentumSnapshotStore(tmp_path)
    store.save(fixture_record())
    assert store.query_exact(identity(record)) == ()
    store.save(record)
    assert len(store.query_exact(identity(record))) == 1
    assert len(store.query_exact(identity(fixture_record()))) == 1


@pytest.mark.parametrize("changes", [
    {"calculation_id": "fixture-calc"},
    {"calculation_content_hash": "a" * 64},
    {"score_profile_content_hash": "a" * 64},
    {"calculation_id": "fixture-calc", "calculation_content_hash": "a" * 64,
     "score_profile_id": "profile", "score_profile_version": "v1"},
    {"calculation_id": "fixture-calc", "calculation_content_hash": "a" * 64, "score_profile_content_hash": "b" * 64},
])
def test_incomplete_new_bindings_rejected(changes):
    with pytest.raises(ValidationError):
        fixture_record(**changes)


def test_exact_disabled_profile_and_content_hashes_affect_identity():
    record = fixture_record(calculation_id="fixture-calc", calculation_content_hash="a" * 64)
    assert record.contract_binding_status == "EXACT"
    assert record.score_profile_id is None and record.score_profile_content_hash is None
    for change in ({"calculation_id": "other"}, {"calculation_content_hash": "b" * 64}):
        other = MomentumIdentity.model_validate(identity(record).model_dump() | change)
        assert other.logical_key != record.logical_key


def test_legacy_selected_score_profile_remains_readable():
    record = fixture_record(score_profile_id="fixture-old-profile", score_profile_version="v1")
    assert record.contract_binding_status == "LEGACY_INCOMPLETE"
    assert record.score_profile_content_hash is None
    exact = fixture_record(calculation_id="fixture-calc", calculation_content_hash="a" * 64,
                           score_profile_id="fixture-old-profile", score_profile_version="v1", score_profile_content_hash="b" * 64)
    other = fixture_record(calculation_id="fixture-calc", calculation_content_hash="a" * 64,
                           score_profile_id="fixture-old-profile", score_profile_version="v1", score_profile_content_hash="c" * 64)
    assert exact.logical_key != other.logical_key
