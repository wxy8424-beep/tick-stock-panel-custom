"""Frozen evidence in temporary storage; never produce or backfill live results."""
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.factor_snapshots import router
from app.factors.registry import get_engine_factor
from app.services import factor_snapshots as module
from app.services.factor_snapshots import FactorSnapshot, FactorSnapshotBuilder, FactorSnapshotStore

NOW = datetime(2026, 9, 15, 13, tzinfo=UTC)
DAY = date(2026, 9, 14)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz is None else NOW.astimezone(tz)
    monkeypatch.setattr(module, "datetime", Clock)


def inputs():
    factor = {"output_column": "ma5", "direction": "high", "weight": 1.0, "period": 5,
              "registry": get_engine_factor("ma").to_dict(), "valid_count": 1, "minimum": 10.0, "maximum": 10.0}
    result = {"as_of": DAY.isoformat(), "history_start": "2026-09-01", "method": "rank",
              "mode": "research", "compatibility_backend": None, "price_basis": "as_provided",
              "aggregation": "equal_weight_complete_case", "factors": [factor],
              "rows": [{"symbol": "AAPL.US", "status": "scored", "total_score": 0.5,
                        "factors": {"ma5": {"value": 10.0, "score": 0.5}}}]}
    registry = {"engine_version": "fixture-engine-v1", "factor_registry_version": "fixture-registry-v1",
                "normalization_version": "fixture-rank-v1", "factors": [deepcopy(factor)]}
    universe = {"universe_id": "fixture-universe-1", "members": ["AAPL.US"],
                "as_of_date": DAY.isoformat(), "available_at": (NOW - timedelta(hours=10)).isoformat(),
                "evidence_reference": "fixture-universe-evidence-1"}
    provenance = {"source": "isolated-fixture", "input_reference": "fixture-input-1",
                  "adjustment_method": "fixture-none", "input_latest_date": DAY,
                  "input_available_at": NOW - timedelta(hours=10), "availability_evidence": "fixture-proof-1",
                  "source_vintage": "fixture-vintage-1", "pit_status": "verified"}
    return result, registry, universe, provenance


def build():
    result, registry, universe, provenance = inputs()
    return FactorSnapshotBuilder().build(result, registry, universe, symbol="AAPL.US",
                                        run_id="fixture-run-1", definition_id="fixture-definition-1", provenance=provenance)


def query(store, **changes):
    params = {"snapshot_date": DAY, "definition_id": "fixture-definition-1", "as_of_time": NOW}
    return store.query("AAPL.US", **(params | changes))


def test_serialization_deep_freeze_and_no_recalculation(monkeypatch):
    from app.factors.engine import MarketFactorEngine

    def forbidden(*args, **kwargs):
        pytest.fail("builder must not execute factor engine")
    monkeypatch.setattr(MarketFactorEngine, "compute", forbidden)
    result, registry, universe, provenance = inputs()
    before = deepcopy((result, registry, universe, provenance))
    snapshot = FactorSnapshotBuilder().build(result, registry, universe, symbol="AAPL.US",
        run_id="run", definition_id="definition", provenance=provenance)["snapshot"]
    assert FactorSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot
    assert (result, registry, universe, provenance) == before
    result["rows"][0]["factors"]["ma5"]["value"] = 999
    registry["factors"][0]["registry"]["version"] = 999
    assert snapshot.factor_values[0].value == 10
    assert snapshot.to_dict()["calculation_metadata"]["factors"][0]["registry"]["version"] == 1
    with pytest.raises(ValidationError):
        snapshot.total_score = 0.9
    with pytest.raises(ValidationError):
        snapshot.factor_values[0].value = 999


def test_append_only_idempotent_store_and_readonly_queries(tmp_path):
    store = FactorSnapshotStore(tmp_path)
    assert query(store)["status"] == "UNAVAILABLE"
    assert not store.path.exists()
    snapshot = build()["snapshot"]
    store.save(snapshot)
    store.save(snapshot)
    content = store.path.read_bytes()
    assert query(store)["snapshot"]["snapshot_id"] == snapshot.snapshot_id
    assert store.path.read_bytes() == content
    assert query(store, definition_id="other")["status"] == "UNAVAILABLE"
    assert query(store, snapshot_date=DAY - timedelta(days=1))["status"] == "UNAVAILABLE"
    changed = snapshot.model_copy(update={"run_id": "different-run"})
    with pytest.raises(ValueError, match="immutable_snapshot_conflict"):
        store.save(changed)
    assert store.path.read_bytes() == content


def test_as_of_filter_and_no_retroactive_availability(tmp_path, monkeypatch):
    store = FactorSnapshotStore(tmp_path)
    snapshot = build()["snapshot"]
    store.save(snapshot)
    assert query(store, as_of_time=NOW - timedelta(microseconds=1))["status"] == "UNAVAILABLE"
    assert query(store)["status"] == "READY"
    assert snapshot.available_at == snapshot.generated_at == NOW
    future = snapshot.model_copy(update={"snapshot_id": "future", "generated_at": NOW + timedelta(days=1),
                                         "available_at": NOW + timedelta(days=1)})
    with pytest.raises(ValueError, match="future_snapshot"):
        store.save(future)
    with pytest.raises(ValueError, match="aware_as_of_time_required"):
        query(store, as_of_time=NOW.replace(tzinfo=None))
    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW + timedelta(hours=2)
    monkeypatch.setattr(module, "datetime", Later)
    delayed = snapshot.model_copy(update={"snapshot_id": "delayed"})
    delayed_store = FactorSnapshotStore(tmp_path / "delayed")
    delayed_store.save(delayed)
    assert query(delayed_store)["status"] == "UNAVAILABLE"
    assert query(delayed_store, as_of_time=NOW + timedelta(hours=2))["status"] == "READY"


@pytest.mark.parametrize("key", ["engine_version", "factor_registry_version", "normalization_version", "factors"])
def test_missing_versions_block_without_snapshot(key):
    result, registry, universe, provenance = inputs()
    registry.pop(key)
    response = FactorSnapshotBuilder().build(result, registry, universe, symbol="AAPL.US",
        run_id="run", definition_id="definition", provenance=provenance)
    assert response == {"status": "BLOCKED", "blocker": "version_metadata_missing", "snapshot": None}


@pytest.mark.parametrize("change", [
    {"pit_status": "unknown"}, {"source": ""}, {"source_vintage": ""},
    {"source": "UNKNOWN"}, {"source_vintage": "unverified"},
    {"input_latest_date": DAY + timedelta(days=1)}, {"input_available_at": NOW + timedelta(seconds=1)},
])
def test_provenance_and_future_inputs_fail_closed(change):
    result, registry, universe, provenance = inputs()
    response = FactorSnapshotBuilder().build(result, registry, universe, symbol="AAPL.US",
        run_id="run", definition_id="definition", provenance=provenance | change)
    assert response["status"] == "BLOCKED" and response["snapshot"] is None


def test_universe_and_version_conflict():
    result, registry, universe, provenance = inputs()
    registry["factors"][0]["registry"]["version"] = 2
    response = FactorSnapshotBuilder().build(result, registry, universe, symbol="AAPL.US",
        run_id="run", definition_id="definition", provenance=provenance)
    assert response["blocker"] == "factor_version_conflict"
    registry["factors"] = deepcopy(result["factors"])
    universe["members"] = ["NVDA.US"]
    response = FactorSnapshotBuilder().build(result, registry, universe, symbol="AAPL.US",
        run_id="run", definition_id="definition", provenance=provenance)
    assert response["blocker"] == "score_universe_conflict"


def test_unknown_versions_and_universe_availability_do_not_become_ready():
    result, registry, universe, provenance = inputs()
    registry["engine_version"] = "unknown"
    builder = FactorSnapshotBuilder()
    assert builder.build(result, registry, universe, symbol="AAPL.US", run_id="r",
        definition_id="d", provenance=provenance)["blocker"] == "version_metadata_unverified"
    registry["engine_version"] = "fixture-engine-v1"
    universe["available_at"] = (NOW + timedelta(days=1)).isoformat()
    assert builder.build(result, registry, universe, symbol="AAPL.US", run_id="r",
        definition_id="d", provenance=provenance)["blocker"] == "universe_availability_unverified"


def test_actual_versions_and_normalization_are_preserved():
    snapshot = build()["snapshot"]
    assert snapshot.engine_version == "fixture-engine-v1"
    assert snapshot.factor_registry_version == "fixture-registry-v1"
    assert snapshot.normalization[0].version == "fixture-rank-v1"
    assert snapshot.normalization[0].valid_count == 1
    assert snapshot.normalization[0].min_value == snapshot.normalization[0].max_value == 10
    assert snapshot.universe_size == 1 and snapshot.universe_members == ("AAPL.US",)
    assert snapshot.to_dict()["calculation_metadata"]["score_cohort"][0]["total_score"] == 0.5


def test_api_readonly_missing_invalid_time_and_ready(tmp_path):
    app = FastAPI()
    app.include_router(router)
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    client = TestClient(app)
    params = {"snapshot_date": DAY.isoformat(), "definition_id": "fixture-definition-1", "as_of_time": NOW.isoformat()}
    url = "/api/factor-snapshots/AAPL.US"
    assert client.get(url, params=params).json()["status"] == "UNAVAILABLE"
    store = FactorSnapshotStore(tmp_path)
    assert not store.path.exists()
    store.save(build()["snapshot"])
    content = store.path.read_bytes()
    response = client.get(url, params=params).json()
    assert response["status"] == "READY" and response["scores"]["total_score"] == 0.5
    assert client.get(url, params=params | {"as_of_time": (NOW - timedelta(seconds=1)).isoformat()}).json()["status"] == "UNAVAILABLE"
    assert client.get(url, params=params | {"as_of_time": "2026-09-15T13:00:00"}).status_code == 422
    assert client.get(url, params={"as_of_time": NOW.isoformat()}).status_code == 422
    assert store.path.read_bytes() == content
