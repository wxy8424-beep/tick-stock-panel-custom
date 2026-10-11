"""Deterministic numerical references; no providers, credentials or trading."""
import json
import math
import statistics
from datetime import date, timedelta

import polars as pl
import pytest

from app.factors.engine import FactorRequest, MarketFactorEngine
from app.indicators.pipeline import compute_indicators


def bars(prices=None, symbol="AAPL.US"):
    prices = [10.0 + i for i in range(80)] if prices is None else prices
    return pl.DataFrame({"symbol": [symbol] * len(prices),
                         "date": [date(2026, 1, 1) + timedelta(days=i) for i in range(len(prices))],
                         "close": prices,
                         "high": [value + 1 if value is not None else None for value in prices],
                         "low": [value - 1 if value is not None else None for value in prices]},
                        schema_overrides={"close": pl.Float64, "high": pl.Float64, "low": pl.Float64})


def ewm(values, alpha):
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1 - alpha) * result[-1])
    return result


def test_ma_ema_roc_independent_numeric_references():
    source = bars()
    result = MarketFactorEngine().compute(source, tuple(FactorRequest(kind, 5) for kind in ("ma", "ema", "roc")))
    values = result.frame
    assert values["ma5"][4] == 12
    assert values["ema5"][4] == pytest.approx(ewm(source["close"].to_list(), 2 / 6)[4])
    assert values["roc_5"][5] == pytest.approx(0.5)  # decimal, not 50 percent
    assert values["ma5"].head(4).null_count() == 4
    assert values["ema5"].head(4).null_count() == 4
    assert values["roc_5"].head(5).null_count() == 5


def test_macd_and_rsi_independent_numeric_references():
    prices = [20 + i / 5 + (i % 5) for i in range(80)]
    result = MarketFactorEngine().compute(bars(prices), (FactorRequest("macd"), FactorRequest("rsi"))).frame
    dif = [a - b for a, b in zip(ewm(prices, 2 / 13), ewm(prices, 2 / 27), strict=True)]
    dea = ewm(dif, 2 / 10)
    gains = [0] + [max(prices[i] - prices[i - 1], 0) for i in range(1, len(prices))]
    losses = [0] + [max(prices[i - 1] - prices[i], 0) for i in range(1, len(prices))]
    gain, loss = ewm(gains, 1 / 14), ewm(losses, 1 / 14)
    for i in range(33, len(prices)):
        assert result["macd_dif"][i] == pytest.approx(dif[i])
        assert result["macd_dea"][i] == pytest.approx(dea[i])
        assert result["macd_hist"][i] == pytest.approx(2 * (dif[i] - dea[i]))
        assert result["rsi_14"][i] == pytest.approx(100 - 100 / (1 + gain[i] / loss[i]))
    assert result["macd_hist"].head(33).null_count() == 33
    assert result["rsi_14"].head(14).null_count() == 14


def test_atr_and_volatility_independent_numeric_references():
    prices = [20 + i / 5 + i % 5 for i in range(80)]
    result = MarketFactorEngine().compute(bars(prices), (FactorRequest("atr"), FactorRequest("volatility"))).frame
    ranges = [2] + [max(2, abs(prices[i] + 1 - prices[i - 1]), abs(prices[i] - 1 - prices[i - 1]))
                    for i in range(1, len(prices))]
    atr = ewm(ranges, 1 / 14)
    returns = [prices[i] / prices[i - 1] - 1 for i in range(1, len(prices))]
    assert result["atr_14"][13] == pytest.approx(atr[13])
    assert result["annual_vol_20d"][20] == pytest.approx(statistics.stdev(returns[:20]) * math.sqrt(252))
    assert result["annual_vol_20d"].head(20).null_count() == 20


def test_shared_pipeline_values_unchanged_after_facade_warmup():
    source = bars()
    before = source.clone()
    result = MarketFactorEngine().compute(source)
    legacy = compute_indicators(source, needed={"ma20", "ema20", "macd_hist", "rsi_14",
                                               "momentum_20d", "atr_14", "annual_vol_20d"})
    for metadata in result.factors:
        for column in metadata["columns"]:
            reference = "momentum_20d" if column == "roc_20" else column
            start = metadata["warmup_bars"] - 1
            assert result.frame[column].slice(start).to_list() == pytest.approx(legacy[reference].slice(start).to_list())
    assert source.equals(before)


def test_empty_and_insufficient_history_have_stable_serialization():
    engine = MarketFactorEngine()
    empty = engine.compute(pl.DataFrame()).to_dict()
    assert empty["rows"] == [] and all(factor["state"] == "unavailable" for factor in empty["factors"])
    short = engine.compute(bars([10, 11]))
    assert all(short.frame[column].null_count() == 2 for column in short.frame.columns[2:])
    assert all(factor["state"] == "unavailable" for factor in short.factors)
    serialized = json.loads(json.dumps(short.to_dict(), allow_nan=False))
    assert serialized["rows"][0]["date"] == "2026-01-01"
    assert serialized["rows"][0]["ma20"] is None and serialized["uses_volume"] is False
    serialized["factors"][0]["columns"].append("mutated")
    assert "mutated" not in short.factors[0]["columns"]


@pytest.mark.parametrize("bad", [None, 0.0, -1.0, float("nan"), float("inf")])
def test_invalid_prices_break_history_without_bridging(bad):
    source = bars([10.0] * 8 + [bad] + [20.0] * 8)
    result = MarketFactorEngine().compute(source, (FactorRequest("ma", 5), FactorRequest("ema", 5), FactorRequest("roc", 5))).frame
    assert result["ma5"][7] == 10
    assert result["ma5"].slice(8, 5).null_count() == 5
    assert result["ma5"][13] == 20
    assert result["ema5"][13] == 20
    assert result["roc_5"].slice(8, 6).null_count() == 6
    assert result["roc_5"][14] == 0
    json.dumps(MarketFactorEngine().compute(source).to_dict(), allow_nan=False)


def test_missing_ohlc_disables_only_atr_and_no_volume_dependency():
    source = bars().drop("high", "low")
    engine = MarketFactorEngine()
    result = engine.compute(source)
    assert result.frame["atr_14"].null_count() == source.height
    assert result.frame["ma20"][-1] is not None
    assert result.frame["rsi_14"][-1] is not None
    poisoned_volume = source.with_columns(pl.lit("unverified-unit-payload").alias("volume"))
    assert engine.compute(poisoned_volume).frame.equals(result.frame)
    with pytest.raises(ValueError, match="volume-dependent"):
        engine.compute(source, (FactorRequest("vwap"),))


def test_symbols_independent_sorting_and_no_lookahead():
    engine = MarketFactorEngine()
    first, second = bars(), bars([200 + i * 2 for i in range(80)], "700.HK")
    combined = pl.concat([second.reverse(), first.reverse()])
    result = engine.compute(combined).frame
    assert result.filter(pl.col("symbol") == "AAPL.US").equals(engine.compute(first).frame)
    assert result.filter(pl.col("symbol") == "700.HK").equals(engine.compute(second).frame)
    prefix = engine.compute(first.head(40)).frame
    assert prefix.equals(engine.compute(first).frame.head(40))


def test_flat_downward_and_large_prices_are_finite_or_null():
    engine = MarketFactorEngine()
    for prices in ([10.0] * 80, [100.0 - i for i in range(80)], [1e300] * 80):
        result = engine.compute(bars(prices))
        json.dumps(result.to_dict(), allow_nan=False)
    flat = engine.compute(bars([10.0] * 80)).frame
    assert flat["rsi_14"][-1] == 0  # existing RSI zero-gain convention, no new formula
    assert flat["annual_vol_20d"][-1] == 0


@pytest.mark.parametrize("requests", [(FactorRequest("ma", 7),), (FactorRequest("ema", True),),
                                       (FactorRequest("macd", 12),), (FactorRequest("rsi", 1),),
                                       (FactorRequest("ma"), FactorRequest("ma"))])
def test_invalid_or_duplicate_requests_fail_closed(requests):
    with pytest.raises(ValueError):
        MarketFactorEngine().compute(bars(), requests)


def test_duplicate_dates_bad_keys_and_price_basis_fail_closed():
    engine = MarketFactorEngine()
    with pytest.raises(ValueError, match="duplicate history"):
        engine.compute(pl.concat([bars().head(1)] * 2))
    with pytest.raises(ValueError, match="Date columns"):
        engine.compute(bars().drop("date"))
    with pytest.raises(ValueError, match="price basis"):
        engine.compute(bars(), price_basis="guessed")
    no_close = engine.compute(bars().drop("close"))
    assert all(item["state"] == "unavailable" for item in no_close.factors)


def test_history_api_existing_interface_and_explicit_warmup_only():
    calls = []
    source = bars()

    class Repository:
        def get_daily_asset(self, *args, **kwargs):
            calls.append((args, kwargs))
            return pl.concat([source, bars(symbol="700.HK")])

    start, end = date(2026, 2, 1), date(2026, 2, 10)
    engine = MarketFactorEngine()
    result = engine.from_history(Repository(), "stock", "AAPL.US", start, end,
                                 history_start=date(2026, 1, 1), price_basis="qfq")
    assert calls[0] == (("stock", "AAPL.US", date(2026, 1, 1), end),
                        {"columns": ["symbol", "date", "close", "high", "low"]})
    assert result.frame.height == 10 and result.frame["symbol"].unique().to_list() == ["AAPL.US"]
    assert result.frame["ma20"][0] == 31.5
    assert result.to_dict()["price_basis"] == "qfq"
    short = engine.from_history(Repository(), "stock", "AAPL.US", start, end)
    assert short.frame["ma20"].null_count() == 10
    empty = engine.from_history(Repository(), "stock", "EMPTY.US", start, end)
    assert empty.frame.is_empty() and all(item["state"] == "unavailable" for item in empty.factors)
    with pytest.raises(ValueError, match="asset type"):
        engine.from_history(Repository(), "future", "AAPL.US", start, end)
