"""Compatibility checks against unchanged production backtest calculators."""
import json
from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from app.backtest.factor import FactorBacktestService
from app.backtest.matrix import build_market_data_matrix, matrix_feature
from app.factors.engine import DEFAULT_FACTORS, FactorRequest, MarketFactorEngine


def history(prices, symbol="600519.SH"):
    return pl.DataFrame({
        "symbol": [symbol] * len(prices),
        "date": [date(2026, 1, 1) + timedelta(days=i) for i in range(len(prices))],
        "close": prices,
        "open": prices,
        "volume": [None] * len(prices),
        "high": [None if p is None else p + 1 for p in prices],
        "low": [None if p is None else p - 1 for p in prices],
    }, schema_overrides={"close": pl.Float64, "open": pl.Float64,
                         "volume": pl.Float64, "high": pl.Float64, "low": pl.Float64})


def requests():
    return tuple(FactorRequest(kind, period) for kind, periods in (
        ("ma", (5, 10, 20, 30, 60)), ("ema", (5, 10, 20, 30, 60)),
        ("roc", (5, 10, 20, 30, 60)), ("rsi", (6, 14, 24)),
        ("macd", (None,)), ("atr", (14,)), ("volatility", (20,)),
    ) for period in periods)


def mappings(selected):
    return {target: source for request in selected for target, source in request.definition()[0].items()}


def finite(values):
    return [float(value) if value is not None and np.isfinite(value) else None for value in values]


@pytest.mark.parametrize("prices", [
    [], [10.0], [10.0, 11.0], [10.0] * 80,
    [100.0 - i * 0.3 + i % 3 for i in range(80)],
    [10.0 + i for i in range(10)] + [None] + [20.0 + i for i in range(70)],
    [None] * 3 + [10.0 + i for i in range(75)],
    [10.0 + i for i in range(20)] + [None, None],
    [10.0] * 20 + [0.0, -1.0, float("nan"), float("inf")] + [20.0] * 40,
])
@pytest.mark.parametrize("backend", ["polars", "matrix"])
def test_compatibility_equals_production_backend(prices, backend):
    source = history(prices)
    before = source.clone()
    selected = requests()
    result = MarketFactorEngine().compute(source, selected, mode="backtest_compat",
                                         compatibility_backend=backend)
    if prices:
        if backend == "polars":
            reference = FactorBacktestService._compute_missing_factors(
                source, set(mappings(selected).values()), assume_sorted=True,
            )
            for target, column in mappings(selected).items():
                assert result.frame[target].to_list() == finite(reference[column].to_list())
        else:
            # Production matrix encoder, including its float32 projection.
            market = build_market_data_matrix(source)
            for target, column in mappings(selected).items():
                assert result.frame[target].to_list() == finite(matrix_feature(market, column)[:, 0])
    else:
        assert result.frame.is_empty()
    assert source.equals(before)
    assert result.mode == "backtest_compat" and result.compatibility_backend == backend
    assert all(item["warmup_policy"] == "legacy_backend" for item in result.factors)
    json.dumps(result.to_dict(), allow_nan=False)


def test_research_default_unchanged_and_compatibility_seed_policy():
    source = history([10.0 + i for i in range(40)])
    engine = MarketFactorEngine()
    default = engine.compute(source)
    explicit = engine.compute(source, mode="research")
    assert default.to_dict() == explicit.to_dict()
    assert default.compatibility_backend is None
    for backend in ("polars", "matrix"):
        compat = engine.compute(source, mode="backtest_compat", compatibility_backend=backend)
        assert compat.frame["ema20"][0] == 10
        assert compat.frame["macd_hist"][0] == 0
        assert compat.frame["rsi_14"][0] == 0
        assert compat.frame["atr_14"][0] == 2
        assert all(default.frame[name][0] is None for name in ("ema20", "macd_hist", "rsi_14", "atr_14"))


def test_gap_policies_remain_distinct():
    source = history([10.0 + i for i in range(10)] + [None] + [21.0 + i for i in range(29)])
    engine = MarketFactorEngine()
    selected = (FactorRequest("ema", 5), FactorRequest("ma", 5))
    research = engine.compute(source, selected).frame
    polars = engine.compute(source, selected, mode="backtest_compat", compatibility_backend="polars").frame
    matrix = engine.compute(source, selected, mode="backtest_compat", compatibility_backend="matrix").frame
    assert research["ema5"].slice(10, 5).null_count() == 5
    assert polars["ema5"][15] != research["ema5"][15]
    assert matrix["ma5"][11] is not None  # effective bars bridge missing observations
    assert polars["ma5"][11] is None and research["ma5"][11] is None


@pytest.mark.parametrize("backend", ["polars", "matrix"])
def test_multi_symbol_sparse_dates_prefix_and_volume_independence(backend):
    a = history([10.0 + i for i in range(80)])
    b = history([200.0 + i for i in range(80)], "AAPL.US").filter(pl.col("date").dt.day() % 3 != 0)
    source = pl.concat([a, b]).reverse()
    engine = MarketFactorEngine()
    kwargs = {"mode": "backtest_compat", "compatibility_backend": backend}
    result = engine.compute(source, **kwargs)
    assert result.frame.height == source.height
    for symbol in ("600519.SH", "AAPL.US"):
        assert result.frame.filter(pl.col("symbol") == symbol).equals(
            engine.compute(source.filter(pl.col("symbol") == symbol), **kwargs).frame,
        )
    cutoff = date(2026, 2, 10)
    assert result.frame.filter(pl.col("date") <= cutoff).equals(
        engine.compute(source.filter(pl.col("date") <= cutoff), **kwargs).frame,
    )
    poisoned = source.with_columns(pl.lit("unknown-volume-unit").alias("volume"))
    assert result.frame.equals(engine.compute(poisoned, **kwargs).frame)


@pytest.mark.parametrize("mode,backend", [("unknown", None), ("research", "polars"),
                                         ("backtest_compat", None), ("backtest_compat", "guess")])
def test_unknown_or_ambiguous_mode_fails_before_history_read(mode, backend):
    class Repository:
        def get_daily_asset(self, *args, **kwargs):
            pytest.fail("invalid mode must not read history")

    engine = MarketFactorEngine()
    with pytest.raises(ValueError):
        engine.compute(pl.DataFrame(), mode=mode, compatibility_backend=backend)
    with pytest.raises(ValueError):
        engine.from_history(Repository(), "stock", "AAPL.US", date(2026, 1, 1), date(2026, 2, 1),
                            mode=mode, compatibility_backend=backend)


@pytest.mark.parametrize("backend", ["polars", "matrix"])
def test_history_wrapper_preserves_mode_and_warmup_range(backend):
    source = history([10.0 + i for i in range(80)])

    class Repository:
        def get_daily_asset(self, *args, **kwargs):
            return source

    engine = MarketFactorEngine()
    start, end = date(2026, 2, 1), date(2026, 2, 10)
    kwargs = {"mode": "backtest_compat", "compatibility_backend": backend}
    result = engine.from_history(Repository(), "stock", "600519.SH", start, end,
                                 history_start=date(2026, 1, 1), **kwargs)
    expected = engine.compute(source.filter(pl.col("date") <= end), **kwargs).frame.filter(pl.col("date") >= start)
    assert result.frame.equals(expected)
    assert result.to_dict()["compatibility_backend"] == backend
    assert result.to_dict()["mode"] == "backtest_compat"


def test_research_missing_prices_stay_null_compatibility_missing_columns_fail_explicitly():
    source = history([10.0] * 40).drop("high", "low")
    engine = MarketFactorEngine()
    result = engine.compute(source)
    assert result.frame["atr_14"].null_count() == 40
    for backend in ("polars", "matrix"):
        with pytest.raises(ValueError, match="numeric"):
            engine.compute(source, DEFAULT_FACTORS, mode="backtest_compat", compatibility_backend=backend)
