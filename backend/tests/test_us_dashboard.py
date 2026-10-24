from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as N

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.us_dashboard import router
from app.services.us_dashboard_service import INDEX_SYMBOLS, SLOTS, USDashboardService


class FakeProvider:
    def __init__(self):
        self.calls = []
        self.fail = set()
        self.call_volume = 200
        self.put_volume = 100

    def dashboard_request(self, kind, method, *args, **kwargs):
        self.calls.append((kind, method, args, kwargs))
        if method in self.fail or (method == "quote" and tuple(args[0]) == INDEX_SYMBOLS and "indices" in self.fail):
            raise RuntimeError("fake-access-token authentication")
        if method == "top_movers":
            return N(events=[N(stock=N(symbol=s, market=m, name="Official English", last_done=102,
                                      change=.02, labels=["Media"]), timestamp="2026-10-08T14:00:00Z",
                               alert_reason="Volatility exceeds 20-day avg", alert_type=1)
                             for s, m in [("AAPL.US", "US"), ("700.HK", "HK"), ("MSFT.US", "CN")]])
        if method == "static_info":
            return [N(symbol=s, name_cn="官方中文", name_en="Official English", currency="USD") for s in args[0]]
        if method == "quote":
            rows = [N(symbol=s, last_done=102 if i % 2 == 0 else 98, prev_close=100, open=100,
                      high=103, low=97, turnover=1000 + i,
                      timestamp=datetime(2026, 10, 8, 14, tzinfo=UTC)) for i, s in enumerate(args[0])]
            return [*rows, rows[0], N(symbol="700.HK")]
        if method == "option_volume":
            return N(symbol=args[0], call_volume=self.call_volume, put_volume=self.put_volume)
        pytest.fail(f"unexpected SDK method {method}")


def service(provider=None, monotonic=lambda: 0):
    provider = provider or FakeProvider()
    return USDashboardService(lambda: provider, clock=lambda: datetime(2026, 10, 8, 14, tzinfo=UTC),
                              monotonic=monotonic), provider


@pytest.mark.parametrize("symbol", ["600519.SH", "700.HK", "AAPL", "aapl.US", "AAPL.US\n", ".SPX.US", "ABC.UNKNOWN"])
def test_reject_invalid_market_before_sdk(symbol):
    svc, provider = service()
    with pytest.raises(ValueError):
        svc.get(symbol, [])
    assert not provider.calls


def test_thirteen_slots_true_sample_and_us_isolation():
    svc, provider = service()
    result = svc.get("AAPL.US", [{"symbol": "600519.SH", "market": "CN"},
                                {"symbol": "700.HK", "market": "HK"}, {"symbol": "GOOG.US", "market": "US"}])
    assert all(key in result for key in SLOTS)
    assert result["sample"]["received"] == 7
    assert result["kpi"]["data"]["total"] == 7
    assert sum(row["count"] for row in result["distribution"]["data"]["bins"]) == 7
    assert result["focus_quote"]["change_pct"] == pytest.approx(.02)
    assert result["focus_quote"]["name"] == "官方中文"
    assert result["focus_quote"]["timestamp"] == 1791468000000
    assert result["focus_quote"]["currency"] == "USD"
    assert len(result["monitor"]["data"]) == 1
    assert result["market"]["session_state"] == "regular"
    assert result["market"]["calendar_status"] == "covered"
    for key in ("radar", "trend", "concept-rank", "industry-rank"):
        assert result[key]["mode"] == "UNAVAILABLE"
    assert result["ladder"]["data"] == {"symbol": "AAPL.US", "call_volume": 200,
                                         "put_volume": 100, "put_call_ratio": .5, "put_call_ratio_mode": "DERIVED"}
    assert "open_interest" not in str(result)
    for _, method, args, _ in provider.calls:
        if method in {"quote", "static_info"}:
            assert all(s.endswith(".US") for s in args[0])
    assert all(method in {"quote", "static_info", "top_movers", "option_volume"}
               for _, method, _, _ in provider.calls)


@pytest.mark.parametrize("method,affected", [("option_volume", "ladder"), ("indices", "indices"),
                                           ("top_movers", "monitor"), ("quote", "kpi")])
def test_partial_failure_preserves_other_sections_and_redacts(method, affected):
    svc, provider = service()
    provider.fail.add(method)
    result = svc.get("AAPL.US", [])
    assert result[affected]["status"] == "error"
    assert "fake-access-token" not in str(result)
    if method != "quote":
        assert result["kpi"]["status"] == "ok"
    if method != "option_volume":
        assert result["ladder"]["status"] == "ok"


def test_unconfirmed_currency_never_becomes_usd_amount():
    svc, provider = service()
    provider.fail.add("static_info")
    result = svc.get(None, [])
    assert result["kpi"]["data"]["amount_total"] is None
    assert result["kpi"]["data"]["amount_count"] == 0
    assert result["gainers"]["status"] == "ok"


def test_zero_option_calls_has_no_invented_ratio():
    svc, provider = service()
    provider.call_volume = 0
    assert svc.get("AAPL.US", [])["ladder"]["data"]["put_call_ratio"] is None


@pytest.mark.parametrize("value", [N(symbol="AAPL.US", call_volume=929378, put_volume=497170),
                                 {"symbol": "AAPL.US", "call_volume": 929378, "put_volume": 497170}])
def test_option_object_and_dict_contract_without_oi(value):
    class Provider(FakeProvider):
        def dashboard_request(self, kind, method, *args, **kwargs):
            return value if method == "option_volume" else super().dashboard_request(kind, method, *args, **kwargs)
    svc, _ = service(Provider())
    result = svc.get("AAPL.US", [])["ladder"]["data"]
    assert result["call_volume"] == 929378
    assert result["put_volume"] == 497170
    assert result["put_call_ratio"] == pytest.approx(497170 / 929378)
    assert result["put_call_ratio_mode"] == "DERIVED"
    assert set(result) == {"symbol", "call_volume", "put_volume", "put_call_ratio", "put_call_ratio_mode"}


@pytest.mark.parametrize("missing", ["call_volume", "put_volume"])
def test_missing_option_field_is_null_not_zero(missing):
    class Provider(FakeProvider):
        def dashboard_request(self, kind, method, *args, **kwargs):
            if method == "option_volume":
                return N(**{key: value for key, value in {"symbol": args[0], "call_volume": 200,
                                                          "put_volume": 100}.items() if key != missing})
            return super().dashboard_request(kind, method, *args, **kwargs)
    svc, _ = service(Provider())
    result = svc.get("AAPL.US", [])["ladder"]["data"]
    assert result[missing] is None
    assert result["put_call_ratio"] is None


def test_symbol_specific_openapi_refusal_does_not_replace_focus_or_crash_dashboard():
    class OpenApiException(Exception):  # noqa: N818 - exact SDK exception name
        pass
    class Provider(FakeProvider):
        def dashboard_request(self, kind, method, *args, **kwargs):
            if method == "option_volume" and args[0] == "SPY.US":
                self.calls.append((kind, method, args, kwargs))
                raise OpenApiException("fake-access-token must not leak")
            return super().dashboard_request(kind, method, *args, **kwargs)
    svc, provider = service(Provider())
    result = svc.get("SPY.US", [])
    assert result["ladder"]["status"] == "unavailable"
    assert result["ladder"]["mode"] == "UNAVAILABLE"
    assert result["ladder"]["data"] is None
    assert result["ladder"]["error"] == "该标的暂无期权成交量数据"
    assert result["focus_symbol"] == "SPY.US"
    assert result["kpi"]["status"] == "ok"
    assert [args[0] for _, method, args, _ in provider.calls if method == "option_volume"] == ["SPY.US"]
    assert "fake-access-token" not in str(result)
    assert svc.get("AAPL.US", [])["ladder"]["status"] == "ok"


def test_cache_expiration_and_provider_reload():
    tick = [0]
    providers = [FakeProvider()]
    svc = USDashboardService(lambda: providers[0], monotonic=lambda: tick[0])
    svc.get("AAPL.US", [])
    calls = len(providers[0].calls)
    svc.get("AAPL.US", [])
    assert len(providers[0].calls) == calls
    tick[0] = 31
    svc.get("AAPL.US", [])
    assert len(providers[0].calls) > calls
    assert sum(method == "static_info" for _, method, _, _ in providers[0].calls) == 1
    providers[0] = FakeProvider()
    svc.get("AAPL.US", [])
    assert providers[0].calls
    for i in range(130):
        svc._read(("test", i), 1, "mock", lambda: [])
    assert len(svc.cache) == 128


def test_missing_provider_keeps_all_slots_unavailable():
    def missing():
        raise RuntimeError("fake-access-token")
    result = USDashboardService(missing).get(None, [])
    assert all(result[key]["status"] == "unavailable" for key in SLOTS)
    assert "fake-access-token" not in str(result)


def test_api_validates_before_provider_and_has_no_cn_write_path(monkeypatch):
    svc, _ = service()
    monkeypatch.setattr("app.api.us_dashboard.service", svc)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        assert client.get("/api/dashboard/us?symbol=700.HK").status_code == 422
        response = client.get("/api/dashboard/us?symbol=AAPL.US")
    assert response.status_code == 200
    assert response.json()["focus_symbol"] == "AAPL.US"
    assert response.json()["focus_quote_metadata"]["symbol"] == "AAPL.US"


def test_focus_metadata_matches_quote_without_new_provider_requests():
    svc, provider = service()
    result = svc.get("AAPL.US", [])
    assert result["focus_quote_metadata"] == {
        "symbol": "AAPL.US", "status": "available",
        "source": "Longbridge · 有限观察样本报价", "source_reason": None,
        "acquired_at": "2026-10-08T14:00:00+00:00", "acquired_at_reason": None,
        "reason": None,
    }
    assert [method for _, method, _, _ in provider.calls] == [
        "top_movers", "static_info", "quote", "quote", "option_volume",
    ]


def test_focus_metadata_retains_cached_acquisition_and_expiry_failure_is_not_success():
    tick = [0]
    svc, provider = service(monotonic=lambda: tick[0])
    origin = datetime(2026, 10, 8, 14, tzinfo=UTC)
    svc.clock = lambda: origin + timedelta(seconds=tick[0])
    first = svc.get("AAPL.US", [])
    tick[0] = 10
    cached = svc.get("AAPL.US", [])
    assert cached["updated_at"] != first["updated_at"]
    assert cached["focus_quote_metadata"] == first["focus_quote_metadata"]
    tick[0] = 31
    provider.fail.add("quote")
    failed = svc.get("AAPL.US", [])
    metadata = failed["focus_quote_metadata"]
    assert metadata["status"] == "error"
    assert failed["focus_quote"] is None
    assert metadata["source"] is metadata["acquired_at"] is None
    assert metadata["source_reason"] and metadata["acquired_at_reason"] and metadata["reason"]
    assert "fake-access-token" not in str(failed)
    provider.fail.clear()
    tick[0] = 62
    assert svc.get("AAPL.US", [])["focus_quote_metadata"]["acquired_at"] != first["focus_quote_metadata"]["acquired_at"]


@pytest.mark.parametrize("empty_all", [False, True])
def test_missing_focus_quote_keeps_metadata_null_and_does_not_borrow_another_symbol(empty_all):
    class Provider(FakeProvider):
        def dashboard_request(self, kind, method, *args, **kwargs):
            rows = super().dashboard_request(kind, method, *args, **kwargs)
            if method == "quote":
                return [] if empty_all else [row for row in rows if row.symbol != "AAPL.US"]
            return rows
    svc, _ = service(Provider())
    result = svc.get("AAPL.US", [])
    metadata = result["focus_quote_metadata"]
    assert result["focus_quote"] is None
    assert metadata["symbol"] == "AAPL.US" and metadata["status"] == "empty"
    assert metadata["source"] is metadata["acquired_at"] is None
    assert metadata["source_reason"] and metadata["acquired_at_reason"] and metadata["reason"]


@pytest.mark.parametrize("symbol", [None, "AAPL.US"])
def test_missing_provider_metadata_is_unavailable_and_redacted(symbol):
    def missing():
        raise RuntimeError("fake-access-token")
    result = USDashboardService(missing).get(symbol, [])
    metadata = result["focus_quote_metadata"]
    assert metadata["symbol"] == result["focus_symbol"] == symbol
    assert metadata["status"] == "unavailable"
    assert metadata["source"] is metadata["acquired_at"] is None
    assert metadata["source_reason"] and metadata["acquired_at_reason"] and metadata["reason"]
    assert "fake-access-token" not in str(metadata)


def test_metadata_survives_name_failure_but_is_rebuilt_on_provider_replacement():
    providers = [FakeProvider()]
    providers[0].fail.add("static_info")
    svc = USDashboardService(lambda: providers[0], clock=lambda: datetime(2026, 10, 8, 14, tzinfo=UTC))
    first = svc.get(None, [])
    assert first["focus_quote_metadata"]["symbol"] == first["focus_quote"]["symbol"]
    assert first["focus_quote_metadata"]["status"] == "available"
    assert "currency" not in first["focus_quote"]
    providers[0] = FakeProvider()
    svc.clock = lambda: datetime(2026, 10, 8, 15, tzinfo=UTC)
    second = svc.get("AAPL.US", [])
    assert second["focus_quote_metadata"]["acquired_at"] == "2026-10-08T15:00:00+00:00"
    assert second["focus_quote"]["currency"] == "USD"
    assert len(providers[0].calls) == 5


@pytest.mark.parametrize("quote_fails", [False, True])
def test_universe_state_cannot_replace_focus_metadata(quote_fails):
    svc, provider = service()
    if quote_fails:
        provider.fail.add("quote")
    svc.universe_enabled = True
    # No worker or real provider: isolate the existing published-universe branch.
    svc._ensure_universe_worker = lambda: None
    svc.universe_provider = provider
    svc.universe_snapshot = ([{"symbol": "NVDA.US", "close": 999, "change_pct": .1, "amount": 2}],
                             {"completed_at": "2020-01-01T00:00:00Z", "requested": 1, "received": 1})
    svc.universe_status = "stale"
    result = svc.get("AAPL.US", [])
    metadata = result["focus_quote_metadata"]
    assert metadata["symbol"] == "AAPL.US"
    assert metadata["status"] == ("error" if quote_fails else "available")
    assert metadata["acquired_at"] == (None if quote_fails else "2026-10-08T14:00:00+00:00")
    assert result["sample"]["completed_at"] == "2020-01-01T00:00:00Z"
