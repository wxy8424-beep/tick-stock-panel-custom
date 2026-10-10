from types import SimpleNamespace

import pytest

from app.plugins.longbridge.financial_availability import classify_failure
from app.plugins.longbridge.provider import LongbridgeProvider


class OpenApiException(Exception):  # noqa: N818 -- match the official SDK exception name
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@pytest.mark.parametrize("code,message,reason", [
    (401003, "hidden", "financial_authentication_unavailable"),
    (403201, "hidden", "financial_authentication_unavailable"),
    (403203, "hidden", "financial_authentication_unavailable"),
    (403205, "hidden", "financial_permission_denied"),
    (429001, "hidden", "financial_rate_limited"),
    (429002, "hidden", "financial_rate_limited"),
    (500000, "hidden", "financial_upstream_error"),
    (None, "entitlement denied", "financial_market_entitlement_unavailable"),
    (None, "permission denied", "financial_permission_denied"),
    (None, "US token required", "financial_authentication_unavailable"),
    (None, "unsupported market", "financial_market_unavailable"),
    (None, "network timeout", "financial_network_unavailable"),
])
def test_classifier_has_deterministic_safe_codes(code, message, reason):
    result = classify_failure(OpenApiException(code, message + " fake-secret-marker"), "request")
    assert result["reason"] == reason
    assert "fake-secret-marker" not in str(result)
    assert result["error_code"] == code


@pytest.mark.parametrize("stage,reason", [("context", "financial_context_unavailable"), ("request", "financial_sdk_exception")])
def test_unclassified_failure_preserves_layer(stage, reason):
    assert classify_failure(RuntimeError("hidden"), stage)["reason"] == reason


def setup_context(monkeypatch, method):
    provider = LongbridgeProvider()
    monkeypatch.setattr(provider, "_get_dashboard_context", lambda kind: SimpleNamespace(financial_report=method))
    return provider


@pytest.mark.parametrize("symbol", ["600519.SH", "700.HK", "AAPL.US", "NVDA.US"])
def test_empty_is_successful_request_not_unsupported(monkeypatch, symbol):
    provider = setup_context(monkeypatch, lambda symbol: SimpleNamespace(list={}))
    result = provider.probe_financial_contract(symbol)
    assert result["status"] == "empty"
    assert result["diagnostic"]["request_status"] == "returned"
    assert result["diagnostic"]["row_count"] == 0
    assert result["diagnostic"]["reason"] == "empty_response"


@pytest.mark.parametrize("symbol", ["700.HK", "AAPL.US", "NVDA.US"])
def test_successful_upstream_is_contract_blocked_not_supported(monkeypatch, symbol):
    reports = {"IS": {"indicators": [{"currency": "USD", "accounts": [{
        "field": "OperatingRevenue", "values": [{"value": "1.234", "fp_end": "fake-period"}],
    }]}]}}
    provider = setup_context(monkeypatch, lambda symbol: SimpleNamespace(list=reports))
    result = provider.probe_financial_contract(symbol)
    assert result["status"] == "contract_blocked"
    assert result["reason"] == "report_period_timestamp_unit_unverified"
    assert result["diagnostic"]["reason"] == "upstream_available"
    assert result["diagnostic"]["row_count"] == 1
    assert "announce_date" in result["missing_optional_fields"]
    assert "fake-period" not in str(result)


def test_missing_method_is_only_unsupported_case(monkeypatch):
    provider = setup_context(monkeypatch, None)
    result = provider.probe_financial_contract("AAPL.US")
    assert result["status"] == "unsupported"
    assert result["reason"] == "sdk_method_unavailable"
    assert result["diagnostic"]["request_status"] == "not_entered"


@pytest.mark.parametrize("error,reason", [
    (ImportError("fake-secret-marker"), "sdk_missing"),
    (RuntimeError("fake-secret-marker"), "financial_context_unavailable"),
    (OpenApiException(401003, "fake-secret-marker"), "financial_authentication_unavailable"),
])
def test_context_errors_cannot_claim_request_sent(monkeypatch, error, reason):
    provider = LongbridgeProvider()
    def fail(kind):
        raise error
    monkeypatch.setattr(provider, "_get_dashboard_context", fail)
    result = provider.probe_financial_contract("AAPL.US")
    assert result["status"] == "unavailable" and result["reason"] == reason
    assert result["diagnostic"]["request_status"] == "not_entered"
    assert result["diagnostic"]["context_status"] == "failed"
    assert "fake-secret-marker" not in str(result)


def test_api_error_is_not_empty_or_sdk_unsupported(monkeypatch):
    calls = []
    def request(symbol):
        calls.append(symbol)
        raise OpenApiException(429002, "fake-secret-marker")
    provider = setup_context(monkeypatch, request)
    result = provider.probe_financial_contract("NVDA.US")
    assert calls == ["NVDA.US"]
    assert result["status"] == "unavailable"
    assert result["diagnostic"]["failure_stage"] == "request"
    assert result["diagnostic"]["error_code"] == 429002
    assert "fake-secret-marker" not in str(result)


def test_parse_failure_is_not_upstream_unavailable(monkeypatch):
    provider = setup_context(monkeypatch, lambda symbol: object())
    result = provider.probe_financial_contract("AAPL.US")
    assert result["status"] == "contract_blocked"
    assert result["diagnostic"]["reason"] == "financial_parse_error"
    assert result["diagnostic"]["failure_stage"] == "adapter"
    assert result["diagnostic"]["request_status"] == "returned"


def test_exception_metadata_cannot_leak_arbitrary_attributes():
    error = type("fake_secret_class", (Exception,), {})("fake-secret-marker")
    error.code = "fake-secret-marker"
    result = classify_failure(error, "request")
    assert result["error_code"] is None
    assert result["exception_class"] == "OtherException"
    assert "fake-secret" not in str(result)


def test_probe_reuses_dashboard_context_and_never_changes_capabilities(monkeypatch):
    provider = LongbridgeProvider()
    calls = []
    context = SimpleNamespace(financial_report=lambda symbol: calls.append(symbol) or SimpleNamespace(list={}))
    provider._dashboard_contexts["fundamental"] = context
    monkeypatch.setattr("app.plugins.longbridge.provider._sdk", lambda: pytest.fail("context must be reused"))
    metadata = provider.market_capabilities
    for symbol in ("AAPL.US", "NVDA.US"):
        assert provider.probe_financial_contract(symbol)["status"] == "empty"
    assert calls == ["AAPL.US", "NVDA.US"]
    assert provider.market_capabilities == metadata
    assert all(entry["status"] == "supported" for entry in metadata["realtime"].values())
    for dataset in ("daily", "minute", "depth5"):
        assert all(entry["status"] == "contract_blocked" for entry in metadata[dataset].values())
    assert set(provider.config.datasets) == {"realtime"}
    provider.close()
    assert provider._dashboard_contexts == {}


def test_same_readonly_context_still_serves_existing_dashboard(monkeypatch):
    provider = LongbridgeProvider()
    provider._dashboard_contexts["fundamental"] = SimpleNamespace(dividend_detail=lambda symbol: [symbol])
    monkeypatch.setattr("app.plugins.longbridge.provider._sdk", lambda: pytest.fail("no reinitialization"))
    assert provider.dashboard_request("fundamental", "dividend_detail", "700.HK") == ["700.HK"]
    with pytest.raises(ValueError, match="unsupported read-only"):
        provider.dashboard_request("fundamental", "unknown_method", "700.HK")
