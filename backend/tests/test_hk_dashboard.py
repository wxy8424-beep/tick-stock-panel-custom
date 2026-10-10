from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.hk_dashboard import router
from app.services.hk_dashboard_service import HKDashboardService, validate_symbol, window_ranking


class FakeProvider:
    def __init__(self):
        self.calls = []
        self.fail = set()

    def dashboard_request(self, kind, method, *args, **kwargs):
        self.calls.append((kind, method, args, kwargs))
        if method in self.fail:
            raise RuntimeError("fake-access-token-do-not-leak authentication")
        if method == "top_movers":
            stock = SimpleNamespace(symbol="700.HK", market="HK", name="腾讯", change="0.02", last_done="500", labels=["异动"])
            return SimpleNamespace(events=[SimpleNamespace(stock=stock, timestamp="2026-10-08T10:00:00+08:00", alert_reason="真实事件", alert_type=1)])
        if method == "quote":
            return [SimpleNamespace(symbol=s, last_done=Decimal(500), prev_close=Decimal(490), open=Decimal(492),
                       high=Decimal(505), low=Decimal(489), turnover=Decimal(100000),
                       timestamp=datetime(2026, 10, 8, 2, tzinfo=UTC)) for s in args[0]]
        if method == "static_info":
            return [SimpleNamespace(symbol=s, name_cn="腾讯", name_en="Tencent", currency="HKD", exchange="SEHK",
                       lot_size=100, total_shares=10000, circulating_shares=9000,
                       eps=Decimal(10), eps_ttm=Decimal(11), bps=Decimal(20)) for s in args[0]]
        if method == "capital_flow":
            return [SimpleNamespace(inflow=Decimal(12), timestamp=datetime(2026, 10, 8, 1, 30 + i, tzinfo=UTC)) for i in range(30)]
        if method == "dividend_detail":
            return SimpleNamespace(list=[SimpleNamespace(symbol=args[0], desc="每股派息5 HKD", ex_date="2026-05-01",
                               payment_date="2026-05-10", record_date="2026-05-02")])
        raise AssertionError(method)


def service(provider=None, clock=None):
    provider = provider or FakeProvider()
    return HKDashboardService(lambda: provider, clock=clock or (lambda: datetime(2026, 10, 8, 8, 1, tzinfo=UTC))), provider


@pytest.mark.parametrize("symbol", ["600519.SH", "AAPL.US", "ABC.UNKNOWN", "foo.HK", "700.HK\n"])
def test_reject_non_hk_symbols(symbol):
    with pytest.raises(ValueError):
        validate_symbol(symbol)


def test_mapping_and_partial_failure_are_secret_safe():
    svc, provider = service()
    provider.fail.add("dividend_detail")
    result = svc.get("700.HK", [])
    assert result["daily_stocks"]["data"][0]["change_pct"] == pytest.approx(10 / 490)
    assert result["fundamentals"]["data"]["currency"] == "HKD"
    assert result["capital_flow"]["data"][0]["inflow"] == 12
    assert result["movers"]["data"][0]["change_pct"] == .02
    assert result["move_reasons"]["data"][0]["reason"] == "真实事件"
    assert result["dividends"]["status"] == "error"
    assert "fake-access-token" not in str(result)
    assert result["industry_flow"]["mode"] == "UNAVAILABLE"
    assert result["daily_etfs"]["status"] == "unavailable"
    assert result["market"]["calendar_status"] == "covered"
    assert not any("trade" in method for _, method, _, _ in provider.calls)


def test_dividends_keep_official_descriptions_and_dates():
    svc, _ = service()
    result = svc.get("700.HK", [])
    assert result["dividends"]["data"][0] == {"symbol": "700.HK", "description": "每股派息5 HKD",
                                               "ex_date": "2026-05-01", "payment_date": "2026-05-10", "record_date": "2026-05-02"}


def test_unavailable_credentials_do_not_crash_other_sections():
    def missing():
        raise ValueError("missing credential configuration")
    result = HKDashboardService(missing).get(None, [])
    assert result["movers"]["status"] == "unavailable"
    assert result["block_trades"]["status"] == "unavailable"


def test_cache_ttl_bound_and_registry_reload():
    now = [0.0]
    first = FakeProvider()
    current = [first]
    svc = HKDashboardService(lambda: current[0], monotonic=lambda: now[0])
    svc.get("700.HK", [])
    calls = len(first.calls)
    svc.get("700.HK", [])
    assert len(first.calls) == calls
    now[0] = 61
    svc.get("700.HK", [])
    assert len(first.calls) > calls
    assert sum(method == "static_info" for _, method, _, _ in first.calls) == 2
    current[0] = FakeProvider()
    svc.get("700.HK", [])
    assert current[0].calls
    assert len(svc.cache) <= 128


def test_window_requires_same_day_complete_sequence_and_finished_clock():
    lines = [{"timestamp": int(datetime(2026, 10, 8, 1, 30 + i, tzinfo=UTC).timestamp() * 1000), "inflow": 10} for i in range(30)]
    before = datetime(2026, 10, 8, 1, 50, tzinfo=UTC)
    after = datetime(2026, 10, 8, 2, 1, tzinfo=UTC)
    assert window_ranking({"700.HK": lines}, before, "morning")["status"] == "empty"
    assert window_ranking({"700.HK": lines[:-1]}, after, "morning")["data"] == []
    assert window_ranking({"700.HK": lines}, after, "morning")["data"][0]["net_inflow"] == 300
    assert window_ranking({"700.HK": lines}, after, "closing")["data"] == []


def test_api_accepts_only_hk_and_returns_partial_sections(monkeypatch):
    svc, _ = service()
    monkeypatch.setattr("app.api.hk_dashboard.service", svc)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        assert client.get("/api/dashboard/hk?symbol=AAPL.US").status_code == 422
        response = client.get("/api/dashboard/hk?symbol=700.HK")
        assert response.status_code == 200
        assert response.json()["focus_symbol"] == "700.HK"


def test_provider_only_constructs_allowlisted_read_contexts_and_releases(monkeypatch):
    from app.plugins.longbridge import provider as module

    created = []

    class Context:
        def __init__(self, config):
            created.append(self)

        def quote(self, symbols):
            return symbols

        def top_movers(self, **kwargs):
            return kwargs

        def dividend_detail(self, symbol):
            return symbol

    sdk = SimpleNamespace(Config=SimpleNamespace(from_apikey=lambda *args, **kwargs: object()),
                          QuoteContext=Context, MarketContext=Context, FundamentalContext=Context)
    monkeypatch.setattr(module, "_sdk", lambda: sdk)
    monkeypatch.setattr(module, "_credentials", lambda: ("fake-key", "fake-secret", "fake-token"))
    provider = module.LongbridgeProvider()
    for _ in range(2):
        provider.dashboard_request("quote", "quote", ["700.HK"])
        provider.dashboard_request("market", "top_movers", markets=["HK"])
        provider.dashboard_request("fundamental", "dividend_detail", "700.HK")
    assert len(created) == 3
    with pytest.raises(ValueError):
        provider.dashboard_request("trade", "place_order")
    provider.close()
    assert not provider._dashboard_contexts
    assert provider._context is None


def test_credentials_missing_never_constructs_dashboard_context(monkeypatch):
    from app.plugins.longbridge import provider as module

    monkeypatch.setattr(module, "_credentials", lambda: ("", "", ""))
    monkeypatch.setattr(module, "_sdk", lambda: pytest.fail("SDK must not initialize without credentials"))
    with pytest.raises(ValueError):
        module.LongbridgeProvider().dashboard_request("market", "top_movers", markets=["HK"])


def test_empty_and_other_market_movers_cannot_pollute_hk_candidates():
    class Mixed(FakeProvider):
        def dashboard_request(self, kind, method, *args, **kwargs):
            if method == "top_movers":
                return SimpleNamespace(events=[SimpleNamespace(stock=SimpleNamespace(symbol="AAPL.US", market="US"))])
            return super().dashboard_request(kind, method, *args, **kwargs)

    svc, provider = service(Mixed())
    response = svc.get(None, [{"symbol": "600519.SH", "market": "CN"}])
    assert response["daily_stocks"]["status"] == "empty"
    assert response["focus_symbol"] is None
    assert not any(method == "quote" for _, method, _, _ in provider.calls)
