"""SDK 完全 mock; 不读取真实凭证、不联网、不创建交易上下文。"""
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.plugins.longbridge import provider as lb
from app.services.quote_service import QuoteService


def quote(symbol, **changes):
    fields = dict(symbol=symbol, last_done=Decimal("110"), prev_close=Decimal("100"),
                  open=Decimal("101"), high=Decimal("112"), low=Decimal("99"),
                  turnover=Decimal("1200.5"), volume=12345,
                  timestamp=datetime(2026, 10, 8, 10, tzinfo=timezone(timedelta(hours=8))))
    fields.update(changes)
    return SimpleNamespace(**fields)


@pytest.fixture(autouse=True)
def sdk(monkeypatch):
    class Context:
        def __init__(self, config):
            contexts.append(self)
            self.calls = []
            self.static_calls = []
            self.fail_batch = None
            self.fail_metadata = False

        def quote(self, symbols):
            self.calls.append(list(symbols))
            if len(self.calls) == self.fail_batch:
                raise RuntimeError("network failure FAKE_SECRET_SENTINEL")
            return [quote(s) for s in symbols]

        def static_info(self, symbols):
            self.static_calls.append(list(symbols))
            if self.fail_metadata:
                raise RuntimeError("permission FAKE_SECRET_SENTINEL")
            # 故意与市场默认币种不同, 证明没有按后缀猜币种。
            return [SimpleNamespace(symbol=s, currency="EUR", name_cn="", name_en="Mock")
                    for s in symbols]

    contexts = []
    config_calls = []

    def config(*args, **kwargs):
        config_calls.append(kwargs)
        return object()

    mock = SimpleNamespace(Config=SimpleNamespace(from_apikey=config), QuoteContext=Context)
    monkeypatch.setattr(lb, "_credentials", lambda: ("mock-key", "mock-secret", "mock-token"))
    monkeypatch.setattr(lb, "_sdk", lambda: mock)
    return contexts, config_calls


@pytest.mark.parametrize("count,batches", [(500, 1), (501, 2), (1001, 3)])
def test_batch_limits(sdk, count, batches):
    provider = lb.LongbridgeProvider()
    rows = provider.get_realtime([f"TEST{i}.US" for i in range(count)])
    assert len(rows) == count
    context = sdk[0][0]
    assert len(context.calls) == batches
    assert all(len(chunk) <= 500 for chunk in context.calls + context.static_calls)


@pytest.mark.parametrize("symbol,market,unit", [
    ("600519.SH", "CN", "unverified"), ("700.HK", "HK", "unsupported"),
    ("AAPL.US", "US", "unsupported"),
])
def test_field_contract(sdk, symbol, market, unit):
    row = lb.LongbridgeProvider().get_realtime([symbol])[0]
    assert row["market"] == market and row["symbol"] == symbol
    assert row["last_price"] == 110 and row["prev_close"] == 100
    assert (row["open"], row["high"], row["low"], row["amount"]) == (101, 112, 99, 1200.5)
    assert row["change_pct"] == pytest.approx(0.1)
    assert row["timestamp"] == int(datetime(2026, 10, 8, 2, tzinfo=UTC).timestamp() * 1000)
    assert row["currency"] == "EUR"
    assert row["volume"] is None and row["volume_unit"] == unit


def test_lazy_reuse_metadata_cache_and_close(sdk):
    provider = lb.LongbridgeProvider()
    assert not sdk[0]
    provider.get_realtime(["700.HK"])
    provider.get_realtime(["700.HK", "AAPL.US"])
    assert len(sdk[0]) == 1
    assert sdk[0][0].static_calls == [["700.HK"], ["AAPL.US"]]
    assert sdk[1] == [{"enable_print_quote_packages": False, "enable_overnight": False}]
    provider.close()
    assert provider._context is None and provider._metadata == {}


def test_partial_batch_failure_does_not_leak(sdk, caplog):
    provider = lb.LongbridgeProvider()
    provider._get_context().fail_batch = 2
    rows = provider.get_realtime([f"TEST{i}.US" for i in range(1001)])
    assert len(rows) == 501
    assert rows[-1]["symbol"] == "TEST1000.US"
    assert provider.last_errors == [{"stage": "quote", "batch": 1, "reason": "network"}]
    assert "FAKE_SECRET_SENTINEL" not in caplog.text


def test_metadata_failure_keeps_snapshots_and_retries(sdk, caplog):
    provider = lb.LongbridgeProvider()
    context = provider._get_context()
    context.fail_metadata = True
    assert provider.get_realtime(["700.HK"])[0]["currency"] is None
    context.fail_metadata = False
    assert provider.get_realtime(["700.HK"])[0]["currency"] == "EUR"
    assert len(context.static_calls) == 2
    assert "FAKE_SECRET_SENTINEL" not in caplog.text


def test_missing_credentials_unavailable_and_fetch_soft_failure(monkeypatch, sdk):
    monkeypatch.setattr(lb, "_credentials", lambda: ("", "", ""))
    assert lb.availability()[0] is False
    provider = lb.LongbridgeProvider()
    assert provider.get_realtime(["700.HK"]) == []
    assert provider.last_errors[0]["reason"] == "authentication"
    assert not sdk[0]


def test_missing_sdk_unavailable(monkeypatch):
    def missing():
        raise ImportError("not installed")
    monkeypatch.setattr(lb, "_sdk", missing)
    assert lb.availability()[0] is False


@pytest.mark.parametrize("changes", [
    {"last_done": Decimal("NaN")}, {"last_done": False},
    {"timestamp": "invalid"}, {"symbol": "ABC.UNKNOWN"},
])
def test_invalid_response_isolated(monkeypatch, sdk, changes):
    provider = lb.LongbridgeProvider()
    context = provider._get_context()
    invalid = quote("700.HK")
    invalid.__dict__.update(changes)
    monkeypatch.setattr(context, "quote", lambda symbols: [invalid, quote("AAPL.US")])
    assert [r["symbol"] for r in provider.get_realtime(["700.HK", "AAPL.US"])] == ["AAPL.US"]


@pytest.mark.parametrize("previous", [None, Decimal(0)])
def test_missing_previous_close_no_division(previous):
    provider = lb.LongbridgeProvider()
    assert provider._normalize(quote("700.HK", prev_close=previous))["change_pct"] is None


@pytest.mark.parametrize("symbol", ["600519.SH", "700.HK", "AAPL.US"])
def test_sdk_local_naive_timestamp_round_trip(symbol):
    epoch = 1791442800
    # 精确复现已核验 SDK v5.2.0 from_timestamp(..., None) 的转换。
    sdk_timestamp = datetime.fromtimestamp(epoch)
    row = lb.LongbridgeProvider()._normalize(quote(symbol, timestamp=sdk_timestamp))
    assert row["timestamp"] == epoch * 1000


def route(monkeypatch, provider):
    from app.data_providers import custom
    from app.services import preferences
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "longbridge")
    monkeypatch.setattr(custom, "provider_has_dataset", lambda name, dataset: dataset == "realtime")
    monkeypatch.setattr(custom, "get_provider", lambda name: provider)
    monkeypatch.setattr(provider, "configured_symbols", lambda: ["600519.SH", "700.HK", "AAPL.US"])
    return QuoteService()


def forbid_cn(monkeypatch, service):
    def forbidden(*args, **kwargs):
        pytest.fail("Longbridge 未确认成交量触发 CN pipeline")
    for method in ("_build_daily", "_flush_live_enriched", "_evaluate_monitors",
                   "_update_volume_delta", "_broadcast_quote_updated"):
        monkeypatch.setattr(service, method, forbidden)


def test_mixed_provider_cn_fail_closed_and_foreign_cache(monkeypatch):
    provider = lb.LongbridgeProvider()
    service = route(monkeypatch, provider)
    forbid_cn(monkeypatch, service)
    service._last_final_confirmed = True
    before = service._fetched_at
    assert service._fetch_full_market_quotes(final_boundary_ms=1) is None
    assert service._last_final_confirmed is False
    assert service._fetched_at == before
    assert {r["symbol"] for r in service.get_non_cn_quotes()} == {"700.HK", "AAPL.US"}


@pytest.mark.parametrize("market,symbol", [("HK", "700.HK"), ("US", "AAPL.US")])
def test_foreign_poll_independent_of_cn(monkeypatch, market, symbol, sdk):
    provider = lb.LongbridgeProvider()
    service = route(monkeypatch, provider)
    forbid_cn(monkeypatch, service)
    monkeypatch.setattr(service, "_should_poll_for_market", lambda m: m == market)
    service._poll_non_cn_quotes()
    assert sdk[0][0].calls == [[symbol]]
    assert [r["symbol"] for r in service.get_non_cn_quotes()] == [symbol]


def test_closed_foreign_sessions_skip_context(monkeypatch, sdk):
    provider = lb.LongbridgeProvider()
    service = route(monkeypatch, provider)
    monkeypatch.setattr(service, "_should_poll_for_market", lambda m: False)
    service._poll_non_cn_quotes()
    assert not sdk[0]


def test_only_realtime_capability():
    provider = lb.LongbridgeProvider()
    assert set(provider.config.datasets) == {"realtime"}
    assert provider.test_dataset("daily")["rows"] == 0
    assert provider.get_realtime(["ABC.UNKNOWN"]) == []
    # mock SDK 无交易/订阅入口; 所有成功请求已在上面的测试实际执行。
    assert not hasattr(lb._sdk(), "TradeContext")
    assert not hasattr(provider, "subscribe")


def test_unavailable_plugin_does_not_crash_loader(monkeypatch):
    import yaml

    from app.data_providers.custom import loader

    manifest = yaml.safe_load((loader.plugins_dir() / "longbridge" / "plugin.yaml").read_text("utf-8"))
    monkeypatch.setattr(loader, "_PROVIDERS", {})
    monkeypatch.setattr(loader, "_PLUGIN_STATUS", {})
    monkeypatch.setattr(lb, "_credentials", lambda: ("", "", ""))
    loader._register_one_plugin(manifest)
    assert "longbridge" not in loader._PROVIDERS
    assert loader._PLUGIN_STATUS["longbridge"]["available"] is False


def test_poll_loop_scoped_source_never_checks_cn_final(monkeypatch):
    provider = lb.LongbridgeProvider()
    service = route(monkeypatch, provider)
    forbid_cn(monkeypatch, service)
    service._running = service._enabled = True

    def session(market):
        assert market != "CN"
        service._running = False
        return market == "US"

    def forbidden():
        pytest.fail("港美轮询调用 CN phase")

    monkeypatch.setattr(service, "_should_poll_for_market", session)
    monkeypatch.setattr(service, "_market_phase", forbidden)
    service._poll_loop()
    assert [r["symbol"] for r in service.get_non_cn_quotes()] == ["AAPL.US"]
