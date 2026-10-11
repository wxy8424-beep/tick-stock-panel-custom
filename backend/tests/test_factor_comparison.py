"""Fixed-input evidence for read-only semantic diagnostics."""
import json
from datetime import date, timedelta

import polars as pl
import pytest

from app.factors.comparison import FactorComparison
from app.factors.engine import FactorRequest, MarketFactorEngine

START = date(2026, 1, 1)


def bars(prices=None, symbol="600519.SH"):
    prices = [20.0 + i / 5 + i % 3 for i in range(80)] if prices is None else prices
    return pl.DataFrame({
        "symbol": [symbol] * len(prices),
        "date": [START + timedelta(days=i) for i in range(len(prices))],
        "close": prices,
        "high": [None if p is None else p + 1 for p in prices],
        "low": [None if p is None else p - 1 for p in prices],
    }, schema_overrides={"close": pl.Float64, "high": pl.Float64, "low": pl.Float64})


def compare(source, name="EMA5", backend="polars", **options):
    return FactorComparison().compare(source, "600519.SH", START, START + timedelta(days=79),
                                      name, compatibility_backend=backend, **options).to_dict()


@pytest.mark.parametrize("name,factor_request", [
    ("MA5", FactorRequest("ma", 5)), ("EMA20", FactorRequest("ema", 20)),
    ("MACD", FactorRequest("macd")), ("rsi_6", FactorRequest("rsi", 6)),
    ("atr_14", FactorRequest("atr", 14)),
])
@pytest.mark.parametrize("backend", ["polars", "matrix"])
def test_deterministic_results_are_actual_engine_outputs(name, factor_request, backend):
    source = bars()
    before = source.clone()
    result = compare(source, name, backend)
    assert result == compare(source.reverse(), name, backend)
    research = MarketFactorEngine().compute(source, (factor_request,)).frame
    compatible = MarketFactorEngine().compute(source, (factor_request,), mode="backtest_compat",
                                              compatibility_backend=backend).frame
    for row in result["rows"]:
        index = (date.fromisoformat(row["date"]) - START).days
        assert row["research"] == research[row["factor"]][index]
        assert row["backtest_compat"] == compatible[row["factor"]][index]
        if row["difference"] is not None:
            assert row["difference"] == row["research"] - row["backtest_compat"]
    assert source.equals(before)
    json.dumps(result, allow_nan=False)


def test_warmup_is_not_initialization_or_missing_data():
    result = compare(bars([10.0, 11.0]), "EMA5")
    assert result["summary"]["different"] == 2
    for row in result["rows"]:
        assert row["difference_reasons"] == ["warmup"]
        assert row["research"] is None and row["backtest_compat"] is not None
        assert row["difference"] is None
    ma = compare(bars([10.0, 11.0]), "MA5")
    assert all(row["status"] == "equal" and row["difference_reason"] is None for row in ma["rows"])


def test_missing_price_and_ohlc_relationship_explained_without_zero_fill():
    source = bars([10.0] * 20 + [0.0] + [20.0] * 20)
    row = compare(source)["rows"][20]
    assert row["difference_reason"] == "missing_data"
    assert row["evidence"]["invalid_inputs"] == ["close"]
    assert row["research"] is None and row["difference"] is None
    inconsistent = bars().with_columns(pl.lit(1.0).alias("high"))
    atr = compare(inconsistent, "ATR")["rows"][20]
    assert atr["difference_reason"] == "missing_data"
    assert atr["evidence"]["invalid_inputs"] == ["ohlc_relationship"]


@pytest.mark.parametrize("backend", ["polars", "matrix"])
def test_gap_and_recursive_initialization_evidence(backend):
    source = bars([10.0 + i for i in range(10)] + [None] + [21.0 + i for i in range(29)])
    rows = compare(source, "EMA5", backend)["rows"]
    assert rows[11]["difference_reasons"] == ["warmup", "gap_handling"]
    assert rows[15]["difference_reasons"] == ["gap_handling", "initialization"]
    assert rows[15]["evidence"]["segment_bars"] == 5
    assert rows[15]["evidence"]["previous_invalid_observation"] is True
    assert rows[15]["difference"] != 0
    if backend == "matrix":
        ma = compare(source, "MA5", backend)["rows"][11]
        assert ma["difference_reasons"] == ["warmup", "gap_handling"]
        assert ma["evidence"]["recursive_factor"] is False


def test_precision_is_not_falsely_labeled_initialization():
    source = bars([10.1234567 + i / 17 for i in range(80)])
    result = compare(source, "EMA5", "matrix", relative_tolerance=0, absolute_tolerance=0)
    late = [row for row in result["rows"] if row["evidence"]["segment_bars"] >= 5
            and row["status"] == "different"]
    assert late and all(row["difference_reasons"] == ["unknown"] for row in late)
    tolerant = compare(source, "EMA5", "matrix")
    assert any(row["status"] == "within_tolerance" for row in tolerant["rows"])
    assert all(row["difference_reason"] is None for row in tolerant["rows"]
               if row["status"] == "within_tolerance")


def test_empty_missing_columns_and_missing_symbol_are_safe():
    result = compare(pl.DataFrame())
    assert result["status"] == "empty" and result["rows"] == []
    assert all(count == 0 for count in result["summary"].values())
    assert compare(bars(symbol="AAPL.US"))["status"] == "empty"
    missing = compare(bars().drop("high"), "ATR")
    assert missing["status"] == "unavailable"
    assert missing["missing_columns"] == ["high"]
    assert all(row["status"] == "unavailable" and row["difference_reason"] == "missing_data"
               for row in missing["rows"])
    assert all(row["difference"] is None for row in missing["rows"])
    json.dumps(missing, allow_nan=False)


def test_explicit_warmup_range_prefix_and_symbol_filter():
    source = pl.concat([bars(), bars(symbol="700.HK")]).reverse()
    start, end = START + timedelta(days=30), START + timedelta(days=39)
    tool = FactorComparison()
    result = tool.compare(source, "600519.SH", start, end, "MACD",
                          compatibility_backend="polars", history_start=START).to_dict()
    reference = compare(bars().head(40), "MACD")
    assert result["rows"] == [row for row in reference["rows"] if row["date"] >= start.isoformat()]
    assert len(result["rows"]) == 30  # 10 bars, three MACD components
    component = tool.compare(source, "600519.SH", start, end, "macd_hist",
                             compatibility_backend="polars", history_start=START).to_dict()
    assert component["rows"] == [row for row in result["rows"] if row["factor"] == "macd_hist"]


def test_repository_read_once_and_serialization_isolation():
    calls = []

    class Repository:
        def get_daily_asset(self, *args, **kwargs):
            calls.append((args, kwargs))
            return bars()

    result = FactorComparison().from_history(Repository(), "stock", "600519.SH", START,
                                             START + timedelta(days=30), "EMA5",
                                             compatibility_backend="polars")
    assert len(calls) == 1
    assert calls[0][1]["columns"] == ["symbol", "date", "close", "high", "low"]
    payload = result.to_dict()
    payload["rows"][0]["evidence"]["invalid_inputs"].append("mutated")
    assert "mutated" not in result.to_dict()["rows"][0]["evidence"]["invalid_inputs"]


@pytest.mark.parametrize("options", [
    {"factor_name": "ROC"}, {"factor_name": "MA7"}, {"compatibility_backend": "guess"},
    {"relative_tolerance": -1}, {"absolute_tolerance": float("nan")},
    {"symbol": ""}, {"end": START - timedelta(days=1)},
])
def test_invalid_requests_fail_before_repository_read(options):
    class Repository:
        def get_daily_asset(self, *args, **kwargs):
            pytest.fail("invalid comparison must not read repository")

    args = {"symbol": "600519.SH", "start": START, "end": START,
            "factor_name": "EMA5", "compatibility_backend": "polars", **options}
    with pytest.raises(ValueError):
        FactorComparison().from_history(Repository(), "stock", **args)
