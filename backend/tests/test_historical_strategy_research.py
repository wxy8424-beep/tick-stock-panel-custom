"""Fixed historical provider fixtures: offline strategy/valuation integration."""
import json
from datetime import UTC, date, datetime, timedelta

import polars as pl
import pytest

from app.data_providers.historical import HISTORICAL_SCHEMA, HistoricalDailyResult
from app.services.historical_strategy_research import (
    HistoricalResearchHistory,
    HistoricalStrategyResearch,
)
from app.services.strategy_research import StrategyDefinition, StrategyResearchStore

DAYS = tuple(date(2026, 6, 1) + timedelta(days=i) for i in range(12) if i not in (5, 6))
SESSIONS = DAYS[4:]


def definition(**changes):
    fields = dict(strategy_id="historical-1", name="历史研究", universe=("600519.SH", "300750.SZ"),
                  factors=[{"name": "ma", "period": 5}], portfolio_rules={"top_n": 1},
                  rebalance_frequency="daily", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    return StrategyDefinition(**(fields | changes))


class Provider:
    def __init__(self, *, missing=None, error=False, status="completed", revision=False,
                 corruption=None, prices=None, currency=None):
        self.missing, self.error, self.status, self.revision = missing, error, status, revision
        self.corruption, self.prices, self.currency = corruption, prices, currency
        self.calls = []

    def fetch_daily(self, symbol, start, end, price_mode):
        self.calls.append((symbol, start, end, price_mode))
        if self.error:
            raise RuntimeError("private credential message")
        market = "US" if symbol.endswith(".US") else "CN"
        method = "none" if market == "CN" else "yfinance_auto_adjust_false"
        rows = []
        for index, day in enumerate(DAYS):
            if not start <= day <= end or day == self.missing:
                continue
            close = self.prices[symbol][index] if self.prices else float(index + (20 if symbol.startswith("300") else 10))
            if self.revision and len(self.calls) > 2:
                close += 1
            rows.append({"symbol": symbol, "market": market, "trading_date": day, "open": close,
                         "high": close, "low": close, "close": close, "source": "fixed_fixture",
                         "currency": self.currency or ("CNY" if market == "CN" else "USD"),
                         "adjustment_method": method, "volume": None, "volume_unit": "unknown"})
        if rows and self.corruption:
            if self.corruption == "duplicate":
                rows.append(dict(rows[-1]))
            elif self.corruption == "extra_future":
                rows.append(dict(rows[-1], trading_date=end + timedelta(days=1)))
            else:
                rows[0].update(self.corruption)
        return HistoricalDailyResult(symbol, market, price_mode, "fixed_fixture",
                                     pl.DataFrame(rows, schema=HISTORICAL_SCHEMA), self.status, ())


def run(model=None, provider=None, **changes):
    arguments = dict(session_dates=SESSIONS, history_start=DAYS[0], history_dates=DAYS,
                     providers={"CN": provider or Provider(), "US": provider or Provider()})
    return HistoricalStrategyResearch().run(model or definition(), **(arguments | changes))


def test_fixed_input_reproducible_ordered_and_persistable():
    result = run()
    assert result["status"] == "completed"
    assert result == run()
    assert result["summary"]["initial_value"] == 1
    assert result["summary"]["final_value"] == pytest.approx(29 / 25)
    assert result["summary"]["total_return"] == pytest.approx(29 / 25 - 1)
    assert [row["trading_date"] for row in result["portfolio_value_series"]] == [day.isoformat() for day in SESSIONS]
    assert result["daily_return"][0]["value"] is None
    assert result["daily_return"][1]["value"] == 0  # Cash until next session close.
    assert result["pit"]["capable"] is False
    json.dumps(result, allow_nan=False)


def test_signal_to_next_close_delay_cannot_earn_execution_day_jump():
    prices = {"600519.SH": [10., 11., 12., 13., 14., 1000., 1010., 1020., 1030., 1040.]}
    result = run(definition(universe=("600519.SH",)), Provider(prices=prices))
    values = [row["value"] for row in result["portfolio_value_series"]]
    assert values[:2] == [1, 1]
    assert values[2] == pytest.approx(1.01)
    first = result["rebalance_events"][0]
    assert first["signal_date"] == SESSIONS[0].isoformat()
    assert first["effective_date"] == SESSIONS[1].isoformat()
    assert first["status"] == "applied"
    assert result["rebalance_events"][-1]["status"] == "deferred"


def test_weekly_buy_and_hold_drift_not_daily_equal_weight_rebalancing():
    prices = {"600519.SH": [10.] * 5 + [10., 20., 30., 40., 50.],
              "300750.SZ": [10.] * 10}
    result = run(definition(rebalance_frequency="monthly", portfolio_rules={"top_n": 2}), Provider(prices=prices))
    assert result["summary"]["applied_events"] == 1
    assert result["summary"]["final_value"] == pytest.approx(0.5 * 5 + 0.5 * 1)
    assert [row["value"] for row in result["portfolio_value_series"]] == pytest.approx([1, 1, 1.5, 2, 2.5, 3])


def test_rebalance_preserves_nav_and_prior_holdings_earn_boundary_return():
    # MA5 switches from first stock to second on June 8. New allocation starts
    # June 9 close; the OLD allocation owns the June 8 -> June 9 return.
    prices = {"600519.SH": [30., 30., 30., 30., 30., 10., 20., 40., 80., 160.],
              "300750.SZ": [10., 10., 10., 10., 10., 200., 100., 100., 100., 100.]}
    result = run(provider=Provider(prices=prices))
    assert result["status"] == "completed"
    values = [row["value"] for row in result["portfolio_value_series"]]
    assert values[:3] == pytest.approx([1, 1, 2])
    assert values[3] == pytest.approx(2)
    assert result["rebalance_events"][1]["selected_symbols"] == ["300750.SZ"]


def test_signal_history_reads_bounded_at_signal_day_and_no_read_beyond_horizon():
    provider = Provider()
    result = run(provider=provider)
    reads = result["source_reads"]
    signal_reads = [item for item in reads if item["purpose"] == "signal"]
    assert [item["end"] for item in signal_reads] == [day.isoformat() for day in SESSIONS for _ in range(2)]
    assert all(call[2] <= SESSIONS[-1] and call[3] == "raw" for call in provider.calls)
    assert all(item["end"] <= SESSIONS[-1].isoformat() for item in reads)


def test_changing_future_bars_cannot_change_earlier_signal_or_nav():
    base = {"600519.SH": [10. + i for i in range(10)], "300750.SZ": [20. + i for i in range(10)]}
    altered = {symbol: [*values[:-1], 9999.] for symbol, values in base.items()}
    first, second = run(provider=Provider(prices=base)), run(provider=Provider(prices=altered))
    assert first["strategy_result"]["events"][:-1] == second["strategy_result"]["events"][:-1]
    assert first["portfolio_value_series"][:-1] == second["portfolio_value_series"][:-1]


@pytest.mark.parametrize("provider,code", [
    (Provider(status="empty"), "historical_empty"),
    (Provider(error=True), "historical_provider_error"),
    (Provider(missing=DAYS[2]), "historical_dates_incomplete_or_conflicting"),
    (Provider(corruption="duplicate"), "historical_dates_incomplete_or_conflicting"),
    (Provider(corruption="extra_future"), "historical_dates_incomplete_or_conflicting"),
    (Provider(corruption={"close": None}), "historical_invalid_price"),
    (Provider(corruption={"close": 0}), "historical_invalid_price"),
    (Provider(corruption={"close": float("inf")}), "historical_invalid_price"),
    (Provider(corruption={"adjustment_method": "akshare_qfq"}), "historical_semantics_conflict"),
    (Provider(corruption={"currency": None}), "historical_currency_unknown"),
    (Provider(revision=True), "historical_revision_during_run"),
])
def test_bad_history_blocks_without_filling_or_fake_values(provider, code):
    result = run(provider=provider)
    assert result["status"] == "blocked"
    assert result["portfolio_value_series"] == [] and result["daily_return"] == []
    assert result["summary"]["total_return"] is None
    assert code in {item["code"] for item in result["blockers"]}
    assert "private credential" not in json.dumps(result)


def test_missing_valuation_bar_only_blocks_whole_performance():
    class MissingValuation(Provider):
        def fetch_daily(self, symbol, start, end, price_mode):
            self.missing = start if start > DAYS[0] else None
            return super().fetch_daily(symbol, start, end, price_mode)

    result = run(provider=MissingValuation())
    assert result["strategy_result"]["execution_status"] == "completed"
    assert result["status"] == "blocked" and result["portfolio_value_series"] == []
    assert any(item["code"] == "historical_dates_incomplete_or_conflicting" for item in result["blockers"])
    assert all(item["status"] != "applied" for item in result["rebalance_events"])


@pytest.mark.parametrize("changes,code", [
    ({"universe": ("600519.SH", "AAPL.US")}, "single_cn_or_us_market_required"),
    ({"universe": ("700.HK",)}, "single_cn_or_us_market_required"),
    ({"price_basis": "qfq"}, "pit_adjusted_history_unavailable"),
    ({"universe": ("AAPL.US",), "price_basis": "raw"}, "us_as_traded_raw_unavailable"),
])
def test_unsupported_semantics_block_before_provider_read(changes, code):
    provider = Provider()
    result = run(definition(**changes), provider)
    assert result["blockers"] == [{"code": code}]
    assert provider.calls == []


def test_us_as_provided_explicit_non_pit_volume_independent():
    result = run(definition(universe=("AAPL.US",)))
    assert result["status"] == "completed" and result["summary"]["currency"] == "USD"
    assert "yahoo_split_revision_and_as_traded_raw_unresolved" in result["pit"]["warnings"]


def test_calendar_missing_empty_and_invalid_inputs():
    assert run(history_dates=None)["blockers"] == [{"code": "complete_history_calendar_required"}]
    assert run(session_dates=())["status"] == "empty"
    assert run(definition(universe=()))["status"] == "empty"
    for days in (DAYS[::-1], DAYS[:-1], (*DAYS, DAYS[-1])):
        with pytest.raises(ValueError):
            run(history_dates=days)


def test_too_short_holding_range_no_synthetic_returns():
    result = run(session_dates=(DAYS[-1],))
    assert result["status"] == "blocked" and result["summary"]["total_return"] is None
    assert result["blockers"] == [{"code": "insufficient_holding_dates"}]


def test_existing_store_explicit_historical_execute_save_query_and_old_execute(tmp_path):
    store = StrategyResearchStore(tmp_path)
    store.save_definition(definition())
    result = store.execute_historical("historical-1", providers={"CN": Provider()},
                                      session_dates=SESSIONS, history_start=DAYS[0], history_dates=DAYS)
    assert store.get_results("historical-1") == [result]
    assert store.get_definition("historical-1") == definition()
    assert result["kind"] == "historical_strategy_research_v1"
    old = store.execute("historical-1", HistoricalResearchHistory({"CN": Provider()}, DAYS),
                        session_dates=SESSIONS, history_start=DAYS[0])
    assert old["result_summary"]["returns"] is None
    assert store.get_results("historical-1") == [old, result]
    with pytest.raises(KeyError):
        store.execute_historical("missing", providers={})
