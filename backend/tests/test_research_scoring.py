"""Research scoring numerical contracts; real Factor Engine, no production path."""
import json
from datetime import date, timedelta

import polars as pl
import pytest

from app.factors.research_scoring import FactorScoringEngine, ScoringFactor

START = date(2026, 1, 1)
AS_OF = START + timedelta(days=79)
SYMBOLS = ("AAPL.US", "NVDA.US", "SPY.US")
DEFAULT_FACTORS = (ScoringFactor("ma", 5),)


class History:
    def __init__(self, *, missing=(), failures=(), count=80, constant=None):
        self.missing, self.failures = missing, failures
        self.count, self.constant = count, constant
        self.calls = []

    def get_daily_asset(self, asset_type, symbol, start, end, columns=None):
        self.calls.append((asset_type, symbol, start, end))
        if symbol in self.failures:
            raise RuntimeError("private-history-error")
        if symbol in self.missing:
            return pl.DataFrame()
        index = SYMBOLS.index(symbol) if symbol in SYMBOLS else 0
        values = ([self.constant] * self.count if self.constant is not None
                  else [(i + 10 * (index + 1)) * (index + 1) for i in range(self.count)])
        return pl.DataFrame({"symbol": [symbol] * self.count,
                             "date": [START + timedelta(days=i) for i in range(self.count)],
                             "close": values, "high": [v + 1 for v in values],
                             "low": [v - 1 for v in values]})


def score(history=None, symbols=SYMBOLS, factors=DEFAULT_FACTORS, **kwargs):
    return FactorScoringEngine().score(history or History(), symbols, factors,
                                      as_of=AS_OF, history_start=START, **kwargs)


@pytest.mark.parametrize("method,values,expected", [
    ("rank", [1, 1, 3], [0.25, 0.25, 1]),
    ("rank", [-4, 0, 4], [0, 0.5, 1]),
    ("normalization", [1, 1, 3], [0, 0, 1]),
    ("normalization", [-4, 0, 4], [0, 0.5, 1]),
    ("normalization", [10, 12, 20], [0, 0.2, 1]),
    ("normalization", [-1e308, 0, 1e308], [0, 0.5, 1]),
    ("rank", [5], [0.5]), ("normalization", [5, 5], [0.5, 0.5]),
])
def test_scaling_known_reference_and_reverse(method, values, expected):
    assert FactorScoringEngine._scores(values, method, "high") == pytest.approx(expected)
    assert FactorScoringEngine._scores(values, method, "low") == pytest.approx([1 - value for value in expected])


@pytest.mark.parametrize("method", ["rank", "normalization"])
def test_single_factor_values_and_explainable_scores(method):
    result = score(method=method)
    assert result["status"] == "completed"
    assert [row["factors"]["ma5"]["value"] for row in result["rows"]] == [87, 194, 321]
    expected = [0, 0.5, 1] if method == "rank" else [0, 107 / 234, 1]
    assert [row["total_score"] for row in result["rows"]] == pytest.approx(expected)
    assert result["factors"][0]["valid_count"] == 3
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    assert score(method=method) == result  # No clock/UUID/random input.


def test_multifactor_equal_weights_and_direction():
    result = score(factors=(ScoringFactor("ma", 5), ScoringFactor("roc", 5)))
    assert [row["factors"]["roc_5"]["score"] for row in result["rows"]] == [1, 0.5, 0]
    assert [row["total_score"] for row in result["rows"]] == [0.5, 0.5, 0.5]
    assert all(factor["weight"] == 0.5 for factor in result["factors"])
    reversed_result = score(factors=(ScoringFactor("ma", 5, direction="low"), ScoringFactor("roc", 5)))
    assert [row["total_score"] for row in reversed_result["rows"]] == [1, 0.5, 0]


def test_missing_and_failure_do_not_fill_or_leak():
    result = score(History(missing=("NVDA.US",), failures=("SPY.US",)))
    assert result["status"] == "partial"
    assert result["rows"][0]["total_score"] == 0.5
    assert all(row["total_score"] is None for row in result["rows"][1:])
    assert result["rows"][1]["factors"]["ma5"]["reason"] == "no_quote_on_as_of"
    assert result["rows"][2]["factors"]["ma5"]["reason"] == "history_or_calculation_error"
    assert "private-history-error" not in str(result)


def test_missing_factor_does_not_renormalize_weight():
    # MA5 ready, RSI14 not warmed up. Never silently give MA full weight.
    result = FactorScoringEngine().score(History(count=5), SYMBOLS,
                                         (ScoringFactor("ma", 5), ScoringFactor("rsi")),
                                         as_of=START + timedelta(days=4), history_start=START)
    assert result["status"] == "unavailable"
    assert all(row["factors"]["ma5"]["score"] is not None for row in result["rows"])
    assert all(row["total_score"] is None for row in result["rows"])


def test_stale_symbol_does_not_use_previous_date():
    result = score(History(count=79))
    assert result["status"] == "unavailable"
    assert all(row["factors"]["ma5"]["value"] is None for row in result["rows"])


def test_empty_symbols_history_and_constant_cross_section():
    assert score(symbols=())["status"] == "empty"
    assert score(symbols=())["rows"] == []
    assert score(History(missing=SYMBOLS))["status"] == "unavailable"
    constant = score(History(constant=10.0))
    assert [row["total_score"] for row in constant["rows"]] == [0.5] * 3
    assert constant["factors"][0]["score_state"] == "neutral"


def test_macd_component_is_explicit_and_modes_pass_through():
    factors = (ScoringFactor("MACD", component="macd_hist"),)
    result = score(factors=factors, mode="backtest_compat", compatibility_backend="matrix")
    assert result["mode"] == "backtest_compat"
    assert result["compatibility_backend"] == "matrix"
    assert result["factors"][0]["output_column"] == "macd_hist"
    assert all("macd_hist" in row["factors"] for row in result["rows"])


def test_cross_market_no_currency_conversion():
    result = score(symbols=("AAPL.US", "700.HK"))
    assert result["warnings"] == ["cross_market_no_currency_adjustment"]
    assert result["factors"][0]["registry"]["name"] == "ma"


@pytest.mark.parametrize("factor", [ScoringFactor("unknown"), ScoringFactor("ma", 9),
                                    ScoringFactor("macd"), ScoringFactor("macd", component="OI"),
                                    ScoringFactor("rsi", direction="guess")])
def test_invalid_factor_rejected_before_history_reads(factor):
    history = History()
    with pytest.raises(ValueError):
        score(history, factors=(factor,))
    assert history.calls == []


@pytest.mark.parametrize("kwargs", [
    {"symbols": ("ABC.UNKNOWN",)}, {"symbols": ("AAPL.US", "AAPL.US")},
    {"factors": ()}, {"factors": (ScoringFactor("ma", 5), ScoringFactor("ma", 20))},
    {"method": "ai"}, {"mode": "backtest_compat"}, {"compatibility_backend": "matrix"},
    {"price_basis": "guessed"},
])
def test_invalid_request_rejected(kwargs):
    with pytest.raises(ValueError):
        score(**kwargs)


def test_invalid_range():
    with pytest.raises(ValueError):
        FactorScoringEngine().score(History(), SYMBOLS, (ScoringFactor("ma"),),
                                    as_of=START, history_start=AS_OF)
