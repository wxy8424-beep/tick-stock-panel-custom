"""Mock-only source contract tests, with no network or production consumers."""
import json
from collections import UserDict
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import polars as pl
import pytest

from app.data_providers.historical import (
    AKShareDailyProvider,
    YFinanceDailyProvider,
    get_historical_provider,
)

START, END = date(2026, 6, 8), date(2026, 6, 10)


def cn_frame(days=("2026-06-10", "2026-06-08"), price=10):
    return pd.DataFrame([{"日期": day, "股票代码": "600519", "开盘": price,
                         "收盘": price + 1, "最高": price + 2, "最低": price - 1,
                         "成交量": 12345} for day in days])


def us_frame(days=("2026-06-10", "2026-06-08"), price=10):
    frame = pd.DataFrame({"Open": price, "High": price + 2, "Low": price - 1, "Close": price + 1,
                          "Adj Close": 8, "Volume": 12345, "Dividends": 0.2, "Stock Splits": 0},
                         index=pd.DatetimeIndex(days, name="Date", tz="America/New_York"))
    return frame


def cn_client(raw=None, adjusted=None):
    raw = cn_frame() if raw is None else raw
    adjusted = cn_frame(price=8) if adjusted is None else adjusted
    return SimpleNamespace(stock_zh_a_hist=Mock(side_effect=[raw, adjusted]))


def us_client(raw=None, adjusted=None, **meta):
    raw = us_frame() if raw is None else raw
    adjusted = us_frame(price=7) if adjusted is None else adjusted
    return SimpleNamespace(history=Mock(side_effect=[raw, adjusted]), get_history_metadata=Mock(return_value={
        "symbol": "AAPL", "instrumentType": "EQUITY", "exchangeTimezoneName": "America/New_York",
        "currency": "USD", **meta}))


def codes(result):
    return {item["code"] for item in result.diagnostics}


def test_cn_raw_qfq_sorted_separate_no_volume_conversion():
    client = cn_client()
    result = AKShareDailyProvider(client).fetch_daily("600519.SH", START, END, "adjusted")
    assert result.status == "completed"
    assert result.frame["trading_date"].to_list() == [START, END]
    row = result.frame.row(0, named=True)
    assert (row["close"], row["adjusted_close"]) == (11, 9)
    assert row["adjustment_method"] == "none"
    assert row["adjusted_adjustment_method"] == "akshare_qfq"
    assert row["volume"] == 12345
    assert row["volume_unit"] == "akshare_lots"
    assert row["currency"] == "CNY"
    assert row["observed_at"] is None and row["fetched_at"].tzinfo is not None
    calls = client.stock_zh_a_hist.call_args_list
    assert [call.kwargs["adjust"] for call in calls] == ["", "qfq"]
    assert calls[0].kwargs == dict(symbol="600519", period="daily", start_date="20260608",
                                  end_date="20260610", adjust="", timeout=15)
    assert json.loads(json.dumps(result.to_dict(), allow_nan=False))["rows"][0]["trading_date"] == START.isoformat()


def test_cn_sz_mapping_and_raw_only():
    frame = cn_frame()
    frame["股票代码"] = "300750"
    client = cn_client(frame)
    result = AKShareDailyProvider(client).fetch_daily("300750.SZ", START, END)
    assert result.status == "completed"
    assert client.stock_zh_a_hist.call_args.kwargs["symbol"] == "300750"
    assert client.stock_zh_a_hist.call_count == 1
    assert result.frame["adjusted_close"].null_count() == 2
    assert result.frame["adjusted_adjustment_method"].null_count() == 2


def test_us_explicit_parameters_source_results_not_manual_adjustment():
    client = us_client()
    factory = Mock(return_value=client)
    result = YFinanceDailyProvider(factory).fetch_daily("AAPL.US", START, END, "adjusted")
    assert result.status == "completed"
    factory.assert_called_once_with("AAPL")
    assert [call.kwargs["auto_adjust"] for call in client.history.call_args_list] == [False, True]
    parameters = client.history.call_args_list[0].kwargs
    assert parameters == dict(start="2026-06-08", end="2026-06-11", interval="1d", auto_adjust=False,
                              back_adjust=False, actions=True, repair=False, keepna=True, rounding=False,
                              prepost=False, timeout=15, raise_errors=True)
    row = result.frame.row(0, named=True)
    assert row["adjusted_open"] == 7  # Source returned 7, not 10*(8/11).
    assert row["close"] == 11 and row["source_adjusted_close"] == 8
    assert row["adjustment_method"] == "yfinance_auto_adjust_false"
    assert row["adjusted_adjustment_method"] == "yfinance_auto_adjust"
    assert row["volume"] == 12345 and row["volume_unit"] == "unknown"
    assert row["currency"] == "USD"
    assert row["dividend"] == 0.2 and row["split"] == 0
    assert codes(result) == {"volume_unit_unknown", "as_traded_raw_not_established",
                             "sdk_may_deduplicate_source_dates"}


@pytest.mark.parametrize("symbol", ["700.HK", "AAPL.US", "510300.SH", "000001.SH", "600519.SZ", "430047.BJ"])
def test_cn_rejects_wrong_market_index_etf_and_exchange(symbol):
    client = cn_client()
    result = AKShareDailyProvider(client).fetch_daily(symbol, START, END)
    assert result.status == "blocked" and result.frame.is_empty()
    client.stock_zh_a_hist.assert_not_called()


@pytest.mark.parametrize("symbol", ["700.HK", "600519.SH", "AAPL", "^SPX.US", "BRK.B.US", "aapl.US"])
def test_us_symbol_boundary(symbol):
    factory = Mock()
    result = YFinanceDailyProvider(factory).fetch_daily(symbol, START, END)
    assert result.status == "blocked"
    factory.assert_not_called()


@pytest.mark.parametrize("days,expected", [
    (("2026-06-08", "2026-06-08"), "duplicate_trading_date"),
    (("2026-06-07",), "out_of_range_trading_date"),
    (("2026-06-13",), "non_trading_date"),
    (("2026-06-19",), "non_trading_date"),
])
def test_dates_fail_closed_without_arbitrary_dedup_or_calendar_fill(days, expected):
    end = date(2026, 6, 19) if expected == "non_trading_date" else END
    result = AKShareDailyProvider(cn_client(cn_frame(days))).fetch_daily("600519.SH", START, end)
    assert result.status == "unavailable" and result.frame.is_empty()
    assert expected in codes(result)


@pytest.mark.parametrize("column,value,expected", [
    ("收盘", -1, "invalid_raw_price"), ("最高", 9, "invalid_ohlc"),
    ("成交量", -1, "invalid_volume"), ("开盘", float("inf"), "invalid_numeric"),
    ("最低", "not a price", "invalid_numeric"), ("股票代码", "300750", "symbol_mismatch"),
])
def test_invalid_source_values_block(column, value, expected):
    frame = cn_frame()
    frame[column] = value
    result = AKShareDailyProvider(cn_client(frame)).fetch_daily("600519.SH", START, END)
    assert result.frame.is_empty() and expected in codes(result)


def test_null_prices_and_volume_retained_no_forward_fill():
    frame = cn_frame()
    frame["开盘"] = float("nan")
    frame["成交量"] = None
    result = AKShareDailyProvider(cn_client(frame)).fetch_daily("600519.SH", START, END)
    assert result.status == "partial"
    assert result.frame.height == 2  # Missing June 9 is not manufactured.
    assert result.frame["open"].null_count() == 2 and result.frame["volume"].null_count() == 2
    json.dumps(result.to_dict(), allow_nan=False)


def test_yfinance_ambiguous_zero_volume_becomes_null_without_unit_guess():
    frame = us_frame()
    frame["Volume"] = 0
    result = YFinanceDailyProvider(Mock(return_value=us_client(frame))).fetch_daily("AAPL.US", START, END)
    assert result.frame["volume"].null_count() == 2
    assert "sdk_zero_volume_ambiguous" in codes(result)
    assert result.frame["volume_unit"].unique().to_list() == ["unknown"]


@pytest.mark.parametrize("change,expected", [
    ({"symbol": "NVDA"}, "security_metadata_mismatch"),
    ({"instrumentType": "ETF"}, "security_metadata_mismatch"),
    ({"exchangeTimezoneName": "Asia/Hong_Kong"}, "security_metadata_mismatch"),
    ({"currency": "not known"}, "currency_schema_unknown"),
])
def test_us_metadata_conflicts_block(change, expected):
    result = YFinanceDailyProvider(Mock(return_value=us_client(**change))).fetch_daily("AAPL.US", START, END)
    assert result.frame.is_empty() and expected in codes(result)


def test_unknown_currency_not_guessed_from_us_suffix():
    result = YFinanceDailyProvider(Mock(return_value=us_client(currency=None))).fetch_daily("AAPL.US", START, END)
    assert result.status == "partial" and "currency_unknown" in codes(result)
    assert result.frame["currency"].null_count() == 2


def test_sdk_history_metadata_mapping_object_supported():
    client = us_client()
    client.get_history_metadata.return_value = UserDict(client.get_history_metadata.return_value)
    result = YFinanceDailyProvider(Mock(return_value=client)).fetch_daily("AAPL.US", START, END, "adjusted")
    assert result.status == "completed" and result.frame["currency"].to_list() == ["USD", "USD"]


@pytest.mark.parametrize("index", [
    pd.DatetimeIndex(["2026-06-08"], name="Datetime", tz="America/New_York"),
    pd.DatetimeIndex(["2026-06-08"], name="Date"),
    pd.DatetimeIndex(["2026-06-08 12:30"], name="Date", tz="America/New_York"),
    pd.DatetimeIndex(["2026-06-08"], name="Date", tz="UTC"),
])
def test_daily_date_label_must_have_verified_local_schema(index):
    frame = us_frame(days=("2026-06-08",))
    frame.index = index
    result = YFinanceDailyProvider(Mock(return_value=us_client(frame))).fetch_daily("AAPL.US", START, END)
    assert result.frame.is_empty() and "trading_date_schema_unknown" in codes(result)


def test_adjusted_error_does_not_discard_valid_raw_or_fabricate_adjusted():
    client = cn_client()
    client.stock_zh_a_hist.side_effect = [cn_frame(), TimeoutError("SECRET response")]
    result = AKShareDailyProvider(client).fetch_daily("600519.SH", START, END, "adjusted")
    assert result.status == "partial" and result.frame.height == 2
    assert result.frame["adjusted_close"].null_count() == 2
    assert "network_timeout" in codes(result) and "SECRET" not in json.dumps(result.to_dict())


def test_adjusted_mismatched_dates_remain_null_not_forward_filled():
    result = AKShareDailyProvider(cn_client(adjusted=cn_frame(days=("2026-06-08",)))).fetch_daily(
        "600519.SH", START, END, "adjusted")
    assert result.status == "partial" and "raw_adjusted_dates_mismatch" in codes(result)
    assert result.frame["adjusted_close"].to_list() == [11, None]


def test_documented_negative_qfq_preserved_but_not_research_ready():
    result = AKShareDailyProvider(cn_client(adjusted=cn_frame(price=-10))).fetch_daily(
        "600519.SH", START, END, "adjusted")
    assert result.status == "partial" and "non_positive_adjusted_price" in codes(result)
    assert result.frame["close"].to_list() == [11, 11]
    assert result.frame["adjusted_close"].to_list() == [-9, -9]


def test_unknown_historical_calendar_is_diagnostic_not_guessed_holiday():
    frame = cn_frame(days=("2024-06-03",))
    result = AKShareDailyProvider(cn_client(frame)).fetch_daily("600519.SH", date(2024, 6, 3), date(2024, 6, 4))
    assert result.status == "completed"
    assert codes(result) == {"calendar_coverage_unknown"}


def test_current_daily_bar_marked_not_final():
    from datetime import UTC, datetime

    from app.data_providers import historical
    original = historical.datetime

    class Clock(original):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 10, 2, tzinfo=UTC)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(historical, "datetime", Clock)
        result = AKShareDailyProvider(cn_client()).fetch_daily("600519.SH", START, END)
    assert result.status == "partial" and "daily_bar_not_final" in codes(result)


@pytest.mark.parametrize("value,expected", [(pd.DataFrame(), "empty"), ("bad response", "unavailable")])
def test_empty_and_wrong_shape_explicit(value, expected):
    result = AKShareDailyProvider(cn_client(value)).fetch_daily("600519.SH", START, END)
    assert result.status == expected and result.frame.schema["trading_date"] == pl.Date


def test_source_error_diagnostic_no_secret_message():
    client = cn_client()
    client.stock_zh_a_hist.side_effect = RuntimeError("token=SECRET")
    result = AKShareDailyProvider(client).fetch_daily("600519.SH", START, END)
    assert result.status == "unavailable" and codes(result) == {"source_api_error"}
    assert "SECRET" not in json.dumps(result.to_dict())


def test_no_sdk_import_on_factory_or_invalid_request(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "akshare", None)
    provider = get_historical_provider("CN")
    result = provider.fetch_daily("600519.SH", START, END)
    assert codes(result) == {"sdk_missing"}
    with pytest.raises(ValueError):
        get_historical_provider("HK")


@pytest.mark.parametrize("start,end,mode", [(END, START, "raw"), ("2026-06-08", END, "raw"),
                                           (START, END, "qfq"), (START, date.max, "raw")])
def test_invalid_request_raises_before_network(start, end, mode):
    client = cn_client()
    with pytest.raises(ValueError):
        AKShareDailyProvider(client).fetch_daily("600519.SH", start, end, mode)
    client.stock_zh_a_hist.assert_not_called()


def test_production_registry_not_changed():
    from app.data_providers.registry import get_provider
    for name in ("akshare", "yfinance", "historical"):
        with pytest.raises(ValueError):
            get_provider(name)
