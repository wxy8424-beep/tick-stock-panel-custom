from types import SimpleNamespace

import pytest

from app.plugins.longbridge.health import build_health, runtime_snapshot
from app.plugins.longbridge.provider import LongbridgeProvider


def test_health_matrix_is_derived_from_authoritative_contract():
    provider = LongbridgeProvider()
    matrix = provider.provider_health()
    for market in ("CN", "HK", "US"):
        assert matrix["realtime"][market]["status"] == "supported"
        assert not matrix["realtime"][market]["usable"]
        assert matrix["realtime"][market]["runtime"]["runtime_status"] == "no_data"
        for dataset in ("daily", "minute", "depth5"):
            entry = matrix[dataset][market]
            assert entry["status"] == "contract_blocked" and not entry["usable"]
            assert entry["reason"] == provider.market_capabilities[dataset][market]["reason"]
            assert "官方单位证据" in entry["message"]
        assert matrix["financial"][market]["status"] == ("empty" if market == "CN" else "contract_blocked")
        assert not matrix["financial"][market]["usable"]
        assert matrix["financial"][market]["runtime"]["availability"] == "not_checked"


@pytest.mark.parametrize("code,availability", [
    ("upstream_available", "available"), ("empty_response", "empty"),
    ("financial_rate_limited", "unavailable"), ("financial_permission_denied", "unavailable"),
    ("sdk_method_unavailable", "unavailable"), ("financial_parse_error", "unavailable"),
    ("fake-secret-marker", "unavailable"),
])
def test_runtime_does_not_override_contract_or_leak_errors(code, availability):
    provider = LongbridgeProvider()
    provider._remember_health("AAPL.US", "financial", {"diagnostic": {"reason": code, "message": "fake-secret-marker"}})
    entry = provider.provider_health()["financial"]["US"]
    assert entry["status"] == "contract_blocked" and not entry["usable"]
    assert entry["runtime"]["availability"] == availability
    assert entry["runtime"]["last_checked"] is not None
    assert "fake-secret-marker" not in str(entry)
    assert entry["runtime"]["diagnostic_code"] == (code if code != "fake-secret-marker" else "diagnostic_unknown")


def test_financial_probe_updates_same_instance_snapshot_without_page_requests(monkeypatch):
    provider = LongbridgeProvider()
    calls = []
    def request(symbol):
        calls.append(symbol)
        return SimpleNamespace(list={})
    monkeypatch.setattr(provider, "_get_dashboard_context", lambda kind: SimpleNamespace(financial_report=request))
    provider.probe_financial_contract("600519.SH")
    for _ in range(3):
        entry = provider.provider_health()["financial"]["CN"]
        assert entry["runtime"]["availability"] == "empty"
    assert calls == ["600519.SH"]
    provider.close()
    assert provider.provider_health()["financial"]["CN"]["runtime"]["availability"] == "not_checked"


@pytest.mark.parametrize("request_status,code", [
    ("success", "upstream_available"), ("method_missing", "sdk_method_unavailable"),
    ("sdk_missing", "sdk_missing"), ("entitlement_denied", "financial_market_entitlement_unavailable"),
    ("empty", "empty_response"), ("network", "financial_network_unavailable"),
])
def test_quantity_diagnostic_normalization_keeps_nine_blockers(request_status, code):
    provider = LongbridgeProvider()
    provider._remember_health("700.HK", "daily", {"request_status": request_status})
    entry = provider.provider_health()["daily"]["HK"]
    assert entry["runtime"]["diagnostic_code"] == code
    assert entry["status"] == "contract_blocked" and not entry["usable"]


def test_missing_provider_cannot_be_usable():
    assert not LongbridgeProvider().provider_health(available=False)["realtime"]["US"]["usable"]


def test_unknown_metadata_fails_closed_and_redacts_reason():
    matrix = build_health({"daily": {"US": {"status": "fake-secret-marker", "reason": "fake-secret-marker"}}}, {"daily"}, {}, True)
    assert matrix["daily"]["US"]["status"] == "contract_blocked"
    assert not matrix["daily"]["US"]["usable"]
    assert "fake-secret-marker" not in str(matrix)
    assert runtime_snapshot("not-a-symbol", {}, "financial")["symbol"] is None


def test_existing_settings_response_adds_optional_health_without_calls(monkeypatch):
    from app.api.settings import list_data_sources
    from app.data_providers.custom import loader

    provider = LongbridgeProvider()
    monkeypatch.setattr(loader, "_PROVIDERS", {"longbridge": provider})
    monkeypatch.setattr(loader, "_PLUGIN_STATUS", {"longbridge": {"name": "longbridge", "available": True}, "legacy": {"name": "legacy", "available": False}})
    monkeypatch.setattr(provider, "_get_dashboard_context", lambda *args: pytest.fail("settings must not call SDK"))
    response = list_data_sources()
    entries = {item["name"]: item for item in response["plugins"]}
    assert entries["longbridge"]["market_capabilities"] == provider.market_capabilities
    assert entries["longbridge"]["provider_health"]["financial"]["US"]["status"] == "contract_blocked"
    assert "provider_health" not in entries["legacy"]
