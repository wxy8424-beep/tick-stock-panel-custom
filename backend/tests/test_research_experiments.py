"""Local experiment lifecycle over real Engine, isolated deterministic history."""
from datetime import UTC, date, datetime, timedelta

import polars as pl
import pytest

from app.factors.engine import FactorRequest, MarketFactorEngine
from app.services.research_experiments import (
    ExperimentDefinition,
    ExperimentRunner,
    ExperimentStore,
)
from app.services.snapshot_archive import SnapshotArchive


def definition(**changes):
    values = dict(experiment_id="test-exp", name="价格因子研究", symbols=["AAPL.US", "700.HK"],
                  factors=["MA", "rsi"], parameters={"periods": {"ma": 5}},
                  date_range={"start": "2026-01-01", "end": "2026-03-21"})
    return ExperimentDefinition(**(values | changes))


class History:
    def __init__(self, failures=(), empty=()):
        self.calls = []
        self.failures = failures
        self.empty = empty

    def get_daily_asset(self, asset_type, symbol, start, end, columns=None):
        self.calls.append((asset_type, symbol, start, end, columns))
        if symbol in self.failures:
            raise RuntimeError("do-not-persist-sensitive-error")
        if symbol in self.empty:
            return pl.DataFrame()
        return pl.DataFrame({"symbol": [symbol] * 80,
                             "date": [date(2026, 1, 1) + timedelta(days=i) for i in range(80)],
                             "close": [10.0 + i for i in range(80)],
                             "high": [11.0 + i for i in range(80)],
                             "low": [9.0 + i for i in range(80)]})


def test_create_save_query_and_duplicate_does_not_overwrite(tmp_path):
    store = ExperimentStore(tmp_path)
    original = definition()
    assert not store.path.exists()
    assert store.get_definition("absent") is None
    assert store.get_results("absent") == []
    assert not store.path.exists()  # Queries never initialize runtime storage.
    assert store.create(original) == original
    assert store.get_definition(original.experiment_id) == original
    with pytest.raises(ValueError, match="already exists"):
        store.create(definition(name="replacement"))
    assert store.get_definition(original.experiment_id).name == original.name
    assert store.get_results(original.experiment_id) == []


@pytest.mark.parametrize("mode,backend", [("research", None), ("backtest_compat", "polars"),
                                         ("backtest_compat", "matrix")])
def test_execute_save_query_matches_engine(tmp_path, mode, backend):
    store, history = ExperimentStore(tmp_path), History()
    original = definition(parameters={"periods": {"ma": 5}, "mode": mode,
                                      "compatibility_backend": backend})
    store.create(original)
    result = ExperimentRunner(store, history).execute(original.experiment_id)
    assert result["status"] == "completed"
    assert len(history.calls) == 2
    assert all(call[0] == "stock" for call in history.calls)
    assert [entry["symbol"] for entry in result["symbols"]] == list(original.symbols)
    first = result["symbols"][0]
    expected = MarketFactorEngine().from_history(
        History(), "stock", "AAPL.US", original.date_range.start, original.date_range.end,
        (FactorRequest("ma", 5), FactorRequest("rsi")), mode=mode, compatibility_backend=backend,
    ).to_dict()
    assert first["data"] == expected
    assert result["factor_metadata"][0]["name"] == "ma"
    assert store.get_results(original.experiment_id) == [result]
    result["symbols"].clear()
    assert len(store.get_results(original.experiment_id)[0]["symbols"]) == 2
    second = ExperimentRunner(store, history).execute(original.experiment_id)
    assert second["run_id"] != store.get_results(original.experiment_id)[1]["run_id"]
    assert store.get_results(original.experiment_id, limit=1) == [second]


@pytest.mark.parametrize("failures,empty,status", [
    (("AAPL.US",), (), "partial"), (("AAPL.US", "700.HK"), (), "failed"),
    ((), ("AAPL.US", "700.HK"), "empty"), ((), ("700.HK",), "completed"),
])
def test_failures_empty_and_error_sanitization(tmp_path, failures, empty, status):
    store = ExperimentStore(tmp_path)
    store.create(definition())
    result = ExperimentRunner(store, History(failures, empty)).execute("test-exp")
    assert result["status"] == status
    assert "do-not-persist-sensitive-error" not in str(store.get_results("test-exp"))
    for entry in result["symbols"]:
        if entry["symbol"] in failures:
            assert entry["data"] is None
            assert entry["error"] == "history_or_calculation_error"
        elif entry["symbol"] in empty:
            assert entry["status"] == "empty"
            assert entry["data"]["rows"] == []


def test_archive_is_read_only_context_not_factor_input(tmp_path):
    archive = SnapshotArchive(tmp_path)
    archive.append([{"symbol": "AAPL.US", "last_price": 999999, "volume": None,
                     "timestamp": 1767268800000}], datetime(2026, 1, 1, 12, tzinfo=UTC), "test")
    before = archive.query(symbol="AAPL.US")
    store = ExperimentStore(tmp_path)
    store.create(definition())
    result = ExperimentRunner(store, History(), archive).execute("test-exp")
    first = result["symbols"][0]
    assert first["latest_snapshot"]["price"] == "999999"
    assert first["latest_snapshot"]["volume"] is None
    assert first["data"]["rows"][4]["ma5"] == 12  # History, not quote price.
    assert result["symbols"][1]["snapshot_status"] == "empty"
    assert archive.query(symbol="AAPL.US") == before


def test_archive_error_does_not_lose_factor_results(tmp_path):
    class UnavailableArchive:
        def query(self, **kwargs):
            raise RuntimeError("secret-context")

    store = ExperimentStore(tmp_path)
    store.create(definition())
    result = ExperimentRunner(store, History(), UnavailableArchive()).execute("test-exp")
    assert result["status"] == "completed"
    assert all(row["snapshot_status"] == "unavailable" for row in result["symbols"])
    assert "secret-context" not in str(result)


@pytest.mark.parametrize("changes", [
    {"symbols": []}, {"symbols": ["ABC.UNKNOWN"]}, {"symbols": ["AAPL.US", "AAPL.US"]},
    {"factors": ["volume"]}, {"factors": ["MA", "ma"]},
    {"parameters": {"periods": {"ma": 9}}}, {"parameters": {"periods": {"ema": 5}}},
    {"parameters": {"mode": "backtest_compat"}},
    {"parameters": {"compatibility_backend": "matrix"}},
    {"parameters": {"access_token": "not-allowed"}},
    {"parameters": {"history_start": "2026-02-01"}},
    {"date_range": {"start": "2026-03-21", "end": "2026-01-01"}},
    {"created_at": "2026-01-01T00:00:00"}, {"experiment_id": "../file"},
])
def test_invalid_definition_is_rejected(changes):
    with pytest.raises(ValueError):
        definition(**changes)


def test_nested_parameters_revalidated_before_save(tmp_path):
    spec = definition()
    spec.parameters.periods["ma"] = 9
    store = ExperimentStore(tmp_path)
    with pytest.raises(ValueError):
        store.create(spec)
    assert not store.path.exists()


def test_missing_experiment_and_invalid_query_limit(tmp_path):
    store = ExperimentStore(tmp_path)
    with pytest.raises(KeyError, match="not found"):
        ExperimentRunner(store, History()).execute("absent")
    for limit in (0, 101, True):
        with pytest.raises(ValueError):
            store.get_results("absent", limit=limit)
    assert not store.path.exists()


def test_explicit_history_start_and_date_trim(tmp_path):
    store, history = ExperimentStore(tmp_path), History()
    store.create(definition(date_range={"start": "2026-02-01", "end": "2026-02-03"},
                            parameters={"history_start": "2026-01-01"}))
    result = ExperimentRunner(store, history).execute("test-exp")
    assert history.calls[0][2] == date(2026, 1, 1)
    assert [row["date"] for row in result["symbols"][0]["data"]["rows"]] == [
        "2026-02-01", "2026-02-02", "2026-02-03"]
