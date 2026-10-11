"""Research proposals use real public factor/portfolio computations, not trades."""
import json
from datetime import UTC, date, datetime, timedelta

import polars as pl
import pytest

from app.services.strategy_research import (
    StrategyDefinition,
    StrategyResearchRunner,
    StrategyResearchStore,
)

START = date(2026, 1, 1)
DAYS = tuple(START + timedelta(days=index) for index in range(10))


def definition(**changes):
    values = dict(strategy_id="study-1", name="策略研究", universe=("AAPL.US", "NVDA.US"),
                  factors=[{"name": "ma", "period": 5}], portfolio_rules={"top_n": 1},
                  rebalance_frequency="daily", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    return StrategyDefinition(**(values | changes))


class History:
    def __init__(self, missing=None, error=False):
        self.missing, self.error, self.calls = missing, error, []

    def get_daily_asset(self, asset_type, symbol, start, end, columns=None):
        self.calls.append((symbol, start, end))
        if self.error:
            raise RuntimeError("private repository information")
        if symbol == self.missing:
            return pl.DataFrame()
        return pl.DataFrame({"symbol": [symbol] * len(DAYS), "date": DAYS,
                             "close": [float(index + (10 if symbol == "AAPL.US" else 20))
                                       for index in range(len(DAYS))]})


def run(model=None, history=None, days=DAYS[4:]):
    return StrategyResearchRunner().run(model or definition(), history or History(),
                                        session_dates=days, history_start=START)


def test_candidates_reproducible_with_existing_factor_and_portfolio_rules():
    history = History()
    result = run(history=history)
    assert result == run()
    assert result["execution_status"] == "completed"
    assert result["result_summary"] == {"event_count": 6, "candidate_count": 6, "blocked_count": 0,
                                        "returns": None, "returns_status": "not_evaluated_v1"}
    for event in result["events"]:
        candidate = event["portfolio_candidate"]
        assert event["kind"] == "research_rebalance_proposal"
        assert candidate["selected_symbols"] == ["NVDA.US"]
        assert candidate["weights"] == {"NVDA.US": 1}
        assert candidate["source_scores"]["as_of"] == event["event_date"]
    assert all(end <= DAYS[-1] for _, _, end in history.calls)
    assert json.loads(json.dumps(result, allow_nan=False)) == result


@pytest.mark.parametrize("frequency,days,expected", [
    ("daily", (date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 12)), 3),
    ("weekly", (date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 12)), 2),
    ("monthly", (date(2026, 1, 5), date(2026, 1, 6), date(2026, 2, 2)), 2),
])
def test_frequency_first_supplied_session_not_synthetic_calendar(frequency, days, expected):
    result = run(definition(rebalance_frequency=frequency), days=days)
    assert len(result["events"]) == expected
    assert result["events"][0]["event_date"] == days[0].isoformat()
    assert all(date.fromisoformat(event["event_date"]) in days for event in result["events"])


def test_missing_history_blocks_whole_event_without_survivor_selection():
    result = run(history=History(missing="NVDA.US"))
    assert result["execution_status"] == "blocked"
    assert all(event["portfolio_candidate"] is None for event in result["events"])
    assert result["events"][0]["blockers"] == [
        {"symbol": "NVDA.US", "factor": "ma5", "reason": "no_quote_on_as_of"}]
    assert result["result_summary"]["returns"] is None


def test_warmup_records_partial_execution_without_fake_returns():
    result = run(days=DAYS)
    assert result["execution_status"] == "partial"
    assert result["result_summary"]["blocked_count"] == 4
    assert result["result_summary"]["candidate_count"] == 6
    assert result["events"][0]["blockers"][0]["reason"] == "insufficient_or_invalid_history"


def test_repository_failure_sanitized_and_saved_as_blocker(tmp_path):
    store = StrategyResearchStore(tmp_path)
    store.save_definition(definition())
    result = store.execute("study-1", History(error=True), session_dates=DAYS[4:], history_start=START)
    assert result["execution_status"] == "blocked"
    assert result["events"][0]["blockers"][0]["reason"] == "history_or_calculation_error"
    assert "private repository" not in json.dumps(result)
    assert store.get_results("study-1") == [result]


@pytest.mark.parametrize("model,days", [(definition(), ()), (definition(universe=()), DAYS)])
def test_empty_inputs_explicit(model, days):
    result = run(model, days=days)
    assert result["execution_status"] == "empty"
    assert result["result_summary"]["candidate_count"] == 0
    assert result["result_summary"]["returns"] is None


@pytest.mark.parametrize("changes", [
    {"universe": ("UNKNOWN",)}, {"universe": ("AAPL.US", "AAPL.US")},
    {"factors": [{"name": "unknown"}]}, {"factors": [{"name": "macd"}]},
    {"factors": [{"name": "ma", "period": 3}]},
    {"factors": [{"name": "ma"}, {"name": "MA"}]},
    {"mode": "backtest_compat"}, {"rebalance_frequency": "hourly"},
    {"portfolio_rules": {"top_n": 0}}, {"broker": "not_allowed"},
])
def test_definition_rejects_invalid_contracts(changes):
    with pytest.raises(ValueError):
        definition(**changes)


@pytest.mark.parametrize("days", [(DAYS[5], DAYS[4]), (DAYS[4], DAYS[4]),
                                   ("2026-01-05",), (date(2025, 12, 31),)])
def test_invalid_dates_do_not_write_results(tmp_path, days):
    store = StrategyResearchStore(tmp_path)
    store.save_definition(definition())
    with pytest.raises(ValueError):
        store.execute("study-1", History(), session_dates=days, history_start=START)
    assert store.get_results("study-1") == []


def test_store_definition_immutable_results_separate_and_queries_readonly(tmp_path):
    store = StrategyResearchStore(tmp_path)
    assert store.get_definition("study-1") is None
    assert store.get_results("study-1") == []
    assert not store.path.exists()
    with pytest.raises(KeyError):
        store.execute("unknown", History(), session_dates=DAYS[4:], history_start=START)
    assert not store.path.exists()
    store.save_definition(definition())
    store.save_definition(definition())
    assert store.get_definition("study-1") == definition()
    with pytest.raises(ValueError, match="overwritten"):
        store.save_definition(definition(name="changed"))
    first = store.execute("study-1", History(), session_dates=DAYS[4:], history_start=START)
    second = store.execute("study-1", History(), session_dates=DAYS[-1:], history_start=START)
    assert store.get_results("study-1") == [second, first]
    assert store.get_results("study-1", limit=1) == [second]
    for invalid in (0, 101, True):
        with pytest.raises(ValueError):
            store.get_results("study-1", limit=invalid)
    assert store.get_definition("study-1") == definition()


def test_explicit_compat_mode_reuses_engine():
    result = run(definition(mode="backtest_compat", compatibility_backend="polars"))
    assert result["execution_status"] == "completed"
    assert result["events"][0]["factor_scores"]["mode"] == "backtest_compat"
