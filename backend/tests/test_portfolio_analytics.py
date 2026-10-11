"""Independent price/NAV references; no provider, trades or calendar guesses."""
import json
import math
import statistics
from copy import deepcopy
from datetime import date, timedelta

import polars as pl
import pytest

from app.services.portfolio_analytics import PortfolioAnalytics

DAYS = tuple(date(2026, 1, 1) + timedelta(days=i) for i in range(4))


def portfolio(symbols=("AAPL.US", "NVDA.US")):
    return {"selected_symbols": list(symbols), "weights": {symbol: 1 / len(symbols) for symbol in symbols},
            "source_scores": {"as_of": "2025-12-31"}, "score_summary": {"mean_total_score": 0.75}}


class History:
    def __init__(self, values=None, days=DAYS):
        self.values = values or {"AAPL.US": [100.0, 120, 90, 110], "NVDA.US": [100.0] * 4}
        self.days, self.calls = days, []

    def get_daily_asset(self, asset_type, symbol, start, end, columns=None):
        self.calls.append(symbol)
        values = self.values.get(symbol)
        if isinstance(values, Exception):
            raise values
        if values is None:
            return pl.DataFrame()
        return pl.DataFrame({"symbol": [symbol] * len(values), "date": self.days,
                             "close": values}, schema_overrides={"close": pl.Float64})


def analyze(source=None, history=None, **kwargs):
    return PortfolioAnalytics().analyze(portfolio() if source is None else source,
                                        history or History(), start=DAYS[0], end=DAYS[-1],
                                        expected_dates=kwargs.pop("expected_dates", DAYS), **kwargs)


def test_returns_risk_and_weight_drift_independent_reference():
    source = portfolio()
    before = deepcopy(source)
    result = analyze(source, periods_per_year=4)
    nav = [1, 1.1, 0.95, 1.05]
    daily = [nav[i] / nav[i - 1] - 1 for i in range(1, 4)]
    assert result["status"] == "completed"
    assert result["total_return"] == pytest.approx(0.05)
    assert result["annualized_return"] == pytest.approx(1.05 ** (4 / 3) - 1)
    assert result["volatility"] == pytest.approx(statistics.stdev(daily) * 2)
    assert result["sharpe_ratio"] == pytest.approx(statistics.mean(daily) / statistics.stdev(daily) * 2)
    assert result["max_drawdown"] == pytest.approx(0.95 / 1.1 - 1)
    assert result["daily_return"][0]["return"] is None
    assert [row["nav"] for row in result["daily_return"]] == pytest.approx(nav)
    assert result["positions"][0]["end_weight"] == pytest.approx(0.55 / 1.05)
    assert result["weights"] == source["weights"]
    assert result["factor_score_summary"] == source["score_summary"]
    assert source == before
    assert result == analyze(source, periods_per_year=4)
    assert json.loads(json.dumps(result, allow_nan=False)) == result


def test_annual_risk_free_conversion():
    result = analyze(periods_per_year=4, annual_risk_free_rate=0.04)
    returns = [row["return"] for row in result["daily_return"]][1:]
    rf = 1.04 ** 0.25 - 1
    assert result["sharpe_ratio"] == pytest.approx((statistics.mean(returns) - rf) / statistics.stdev(returns) * 2)


def test_flat_prices_zero_risk_sharpe_unknown():
    result = analyze(history=History({symbol: [100.0] * 4 for symbol in portfolio()["selected_symbols"]}))
    assert result["total_return"] == 0
    assert result["annualized_return"] == 0
    assert result["volatility"] == 0
    assert result["max_drawdown"] == 0
    assert result["sharpe_ratio"] is None
    assert result["status"] == "partial"
    assert {row["code"] for row in result["blockers"]} == {"zero_volatility_sharpe_undefined"}


@pytest.mark.parametrize("value", [None, 0.0, -1.0, float("nan"), float("inf")])
def test_bad_price_blocks_entire_portfolio_without_reweighting(value):
    result = analyze(history=History({"AAPL.US": [100.0, value, 90, 110], "NVDA.US": [100.0] * 4}))
    assert result["status"] == "blocked"
    assert result["total_return"] is None
    assert result["daily_return"] == []
    assert result["weights"] == portfolio()["weights"]
    assert result["blockers"][0]["code"] == "invalid_price"


def test_history_empty_and_errors_are_sanitized():
    result = analyze(history=History({"AAPL.US": RuntimeError("private-do-not-store")}))
    assert {row["code"] for row in result["blockers"]} == {"history_empty", "history_read_error"}
    assert "private-do-not-store" not in str(result)


def test_missing_or_duplicate_dates_block_no_forward_fill():
    result = analyze(history=History({"AAPL.US": [100.0, 90, 110], "NVDA.US": [100.0] * 3},
                                    days=(DAYS[0], DAYS[2], DAYS[3])))
    assert result["blockers"][0]["missing_dates"] == [DAYS[1].isoformat()]
    assert result["total_return"] is None
    duplicate = analyze(history=History(days=(DAYS[0], DAYS[1], DAYS[1], DAYS[3])))
    assert all(row["code"] == "duplicate_price_date" for row in duplicate["blockers"])


def test_unknown_dates_selection_and_cross_market_fail_closed():
    history = History()
    assert analyze(history=history, expected_dates=None)["blockers"][0]["code"] == "expected_dates_unknown"
    assert history.calls == []
    source = portfolio()
    source["source_scores"]["as_of"] = "2026-01-02"
    assert analyze(source)["blockers"][0]["code"] == "selection_after_analysis_start"
    source["source_scores"] = {}
    assert analyze(source)["blockers"][0]["code"] == "selection_date_unknown"
    assert analyze(portfolio(("AAPL.US", "700.HK")))["blockers"][0]["code"] == "mixed_market_fx_unresolved"


def test_empty_and_insufficient_prices_explicit():
    assert analyze(portfolio(()))["status"] == "empty"
    assert analyze(expected_dates=(DAYS[0],))["blockers"][0]["code"] == "insufficient_price_dates"
    result = analyze(history=History({"AAPL.US": [100.0, 110], "NVDA.US": [100.0] * 2}, days=(DAYS[0], DAYS[3])),
                     expected_dates=(DAYS[0], DAYS[3]))
    assert result["total_return"] == pytest.approx(0.05)
    assert result["volatility"] is None
    assert result["blockers"][0]["code"] == "insufficient_returns_for_risk"


def test_extreme_ratio_does_not_serialize_inf():
    result = analyze(history=History({"AAPL.US": [1e-308, 1e308, 100, 100], "NVDA.US": [100.0] * 4}))
    assert result["status"] == "blocked"
    assert result["blockers"][0]["code"] == "price_arithmetic_unavailable"
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("kwargs", [{"periods_per_year": 0}, {"periods_per_year": True},
                                    {"annual_risk_free_rate": -1}, {"annual_risk_free_rate": math.inf},
                                    {"expected_dates": DAYS[::-1]}])
def test_invalid_parameters(kwargs):
    with pytest.raises(ValueError):
        analyze(**kwargs)


def test_invalid_weights():
    source = portfolio()
    source["weights"]["AAPL.US"] = 0.2
    with pytest.raises(ValueError):
        analyze(source)
