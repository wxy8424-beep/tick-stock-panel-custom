"""Mock-only CN source routing and contract tests; no SDK/network in unit tests."""
from datetime import date
from http.client import RemoteDisconnected
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from app.data_providers.baostock_daily import BaoStockDailyProvider, CNHistoricalProvider
from app.data_providers.historical import AKShareDailyProvider, _DataError
from app.services.historical_baseline import HistoricalBaselineService
from scripts.smoke_historical_baseline import smoke_symbol
from tests.test_historical_daily import END, START, cn_client, cn_frame


def bao_rows(days=("2026-06-08", "2026-06-10"), code="sh.600519"):
    return [{"date": day, "code": code, "open": "10", "high": "12", "low": "9", "close": "11",
             "tradestatus": "1", "adjustflag": "3"} for day in days]


def routed(error=None, rows=None):
    client = cn_client()
    if error is not None:
        client.stock_zh_a_hist.side_effect = error
    reader = Mock(return_value=bao_rows() if rows is None else rows)
    return CNHistoricalProvider(AKShareDailyProvider(client), BaoStockDailyProvider(reader)), client, reader


def test_primary_success_never_calls_fallback():
    provider, _, reader = routed()
    result = provider.fetch_daily("600519.SH", START, END)
    assert result.status == "completed" and result.source.endswith("/eastmoney")
    reader.assert_not_called()


@pytest.mark.parametrize("error,classification", [
    (requests.ConnectionError(RemoteDisconnected("sensitive upstream text")), "upstream_reset"),
    (requests.Timeout("sensitive text"), "timeout"),
    (requests.exceptions.SSLError("sensitive text"), "tls_error"),
])
def test_transport_fallback_provenance_and_none(error, classification):
    provider, _, reader = routed(error)
    result = provider.fetch_daily("600519.SH", START, END)
    assert result.status == "completed" and result.source == "baostock"
    assert result.frame["source"].to_list() == ["baostock"] * 2
    assert result.frame["adjustment_method"].to_list() == ["none"] * 2
    assert result.frame["adjusted_close"].null_count() == 2
    assert result.frame["volume"].null_count() == 2
    assert result.frame["volume_unit"].to_list() == ["unknown"] * 2
    assert any(item.get("classification") == classification for item in result.diagnostics)
    assert any(item["code"] == "fallback_used" for item in result.diagnostics)
    assert "sensitive" not in str(result.to_dict())
    reader.assert_called_once_with("sh.600519", START, END)


@pytest.mark.parametrize("error", [ValueError("parse"), KeyError("programming"), RuntimeError("programming")])
def test_nontransport_exceptions_do_not_fallback(error):
    provider, _, reader = routed(error)
    assert provider.fetch_daily("600519.SH", START, END).status == "unavailable"
    reader.assert_not_called()


@pytest.mark.parametrize("data", [cn_frame().drop(columns="日期"), cn_frame().assign(最高=1), cn_frame().assign(开盘="bad")])
def test_schema_numeric_ohlc_errors_do_not_fallback(data):
    provider, client, reader = routed()
    client.stock_zh_a_hist.side_effect = [data]
    assert provider.fetch_daily("600519.SH", START, END).status == "unavailable"
    reader.assert_not_called()


def test_invalid_symbol_request_qfq_empty_never_fallback():
    provider, _, reader = routed(requests.ConnectionError("transport"))
    assert provider.fetch_daily("700.HK", START, END).status == "blocked"
    with pytest.raises(ValueError):
        provider.fetch_daily("600519.SH", END, START)
    assert provider.fetch_daily("600519.SH", START, END, "adjusted").status == "unavailable"
    reader.assert_not_called()
    with pytest.raises(ValueError):
        BaoStockDailyProvider(reader).fetch_daily("600519.SH", START, END, "adjusted")


def test_fallback_failure_retains_both_sources():
    provider, _, reader = routed(requests.ConnectionError("primary secret"))
    reader.side_effect = TimeoutError("fallback secret")
    result = provider.fetch_daily("600519.SH", START, END)
    assert result.status == "unavailable" and result.frame.is_empty()
    assert {item["source"] for item in result.diagnostics} == {"akshare.stock_zh_a_hist/eastmoney", "baostock"}
    assert "secret" not in str(result.to_dict())


@pytest.mark.parametrize("field,value", [("code", "sz.300750"), ("adjustflag", "2"), ("tradestatus", "unknown"), ("high", "8")])
def test_baostock_contract_conflicts_block(field, value):
    rows = bao_rows()
    rows[0][field] = value
    result = BaoStockDailyProvider(Mock(return_value=rows)).fetch_daily("600519.SH", START, END)
    assert result.status == "unavailable" and result.frame.is_empty()


def test_suspension_not_fabricated_and_duplicates_block():
    rows = bao_rows()
    rows[0]["tradestatus"] = "0"
    result = BaoStockDailyProvider(Mock(return_value=rows)).fetch_daily("600519.SH", START, END)
    assert result.frame["trading_date"].to_list() == [END]
    rows = bao_rows() * 2
    assert BaoStockDailyProvider(Mock(return_value=rows)).fetch_daily("600519.SH", START, END).status == "unavailable"


def test_fallback_baseline_pit_cache_and_context(tmp_path):
    days = [f"2026-06-{day:02d}" for day in (1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 15, 16, 17, 18, 22, 23, 24, 25, 26, 29, 30)]
    provider, client, reader = routed(requests.ConnectionError(RemoteDisconnected("private")), bao_rows(days))
    evaluation = date(2026, 6, 29)
    # Simulate provider over-returning D/D+1 after source normalization, to prove service gating.
    actual = provider.fetch_daily("600519.SH", date(2026, 6, 1), date(2026, 6, 30))
    proxy = SimpleNamespace(fetch_daily=Mock(return_value=actual))
    service = HistoricalBaselineService(tmp_path, provider_factory=lambda _: proxy)
    result = service.baseline("600519.SH", evaluation)
    assert result["status"] == "available" and result["source"] == "baostock"
    assert result["lookback_end"] < evaluation.isoformat() and float(result["atr14"]) > 0
    assert service.baseline("600519.SH", evaluation) == result and proxy.fetch_daily.call_count == 1
    assert any(item["code"] == "fallback_used" for item in result["provider_diagnostics"])
    context = service.context({"symbol": "600519.SH", "market": "CN", "change_value": "4"}, evaluation)
    assert context["move_atr_ratio"] is None and context["blocker"] == "event_baseline_price_scale_unverified"
    assert reader.call_count == client.stock_zh_a_hist.call_count == 1


def test_failed_fallback_baseline_cached_and_isolated(tmp_path):
    provider, _, reader = routed(requests.ConnectionError("source"))
    reader.side_effect = _DataError("baostock_query_unavailable")
    service = HistoricalBaselineService(tmp_path, provider_factory=lambda _: provider)
    result = service.baseline("600519.SH", END)
    assert result["status"] == "unavailable" and result["source"] == "baostock"
    assert service.baseline("600519.SH", END) == result and reader.call_count == 1
    assert any(item["code"] == "fallback_attempt" for item in result["provider_diagnostics"])


def test_fallback_smoke_fixture_contract(tmp_path):
    days = [f"2026-06-{day:02d}" for day in (1, 2, 3, 4, 5, 8, 9, 10, 11, 12, 15, 16, 17, 18, 22, 23, 24, 25, 26, 29, 30)]
    provider, _, _ = routed(requests.ConnectionError("source"), bao_rows(days))
    report = smoke_symbol("600519.SH", date(2026, 6, 30), tmp_path, lambda _: provider)
    assert report["status"] == "PASS" and report["source"] == "baostock"
    assert report["source_attempts"] and report["cache"]["provider_calls"] == 1
