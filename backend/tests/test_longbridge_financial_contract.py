from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.plugins.longbridge.financial import (
    assess_financial_contract,
    decimal_value,
    financial_candidates,
    financial_rows_ready,
)
from app.plugins.longbridge.provider import LongbridgeProvider


def test_financial_mapping_is_decimal_and_cannot_be_persisted_without_period_contract():
    reports = {}
    for kind, fields in {
        "IS": ["OperatingRevenue", "NetProfit", "EPS"],
        "BS": ["TotalAssets", "TotalLiability", "BPS"],
        "CF": ["NetOperateCashFlow", "NetInvestCashFlow", "NetFinanceCashFlow"],
    }.items():
        reports[kind] = {"indicators": [{"currency": "HKD", "accounts": [
            {"field": field, "values": [{"year": 2026, "period": "Q2 2026",
                "fp_end": "1782748800", "value": "123456.789", "yoy": "17.03", "ratio": "0.2"}]}
            for field in fields
        ]}]}
    rows = financial_candidates("700.HK", SimpleNamespace(list=reports))
    assert len(rows) == 3
    assert rows[0]["revenue"] == Decimal("123456.789")
    assert rows[1]["bps"] == Decimal("123456.789")
    assert rows[2]["net_operating_cash_flow"] == Decimal("123456.789")
    assert all(row["currency"] == "HKD" and row["announce_date"] is None for row in rows)
    assert all(row["period_end"] is None for row in rows)
    assert not financial_rows_ready(rows)
    assert all(not ({"basic_eps", "diluted_eps", "yoy", "ratio"} & row.keys()) for row in rows)


def test_empty_reports_are_empty_not_zero():
    assert financial_candidates("600519.SH", SimpleNamespace(list={})) == []
    assert decimal_value("") is None
    assert decimal_value(None) is None
    with pytest.raises(ValueError, match="invalid_financial_number"):
        decimal_value(0.1)


def test_capabilities_do_not_claim_unsafe_financial_support():
    provider = LongbridgeProvider()
    metadata = provider.market_capabilities
    assert metadata["financial"]["CN"]["status"] == "empty"
    assert metadata["financial"]["HK"]["status"] == "contract_blocked"
    assert metadata["financial"]["US"]["status"] == "unavailable"
    assert metadata["financial"]["US"]["sdk_available"] is True
    assert metadata["financial"]["US"]["reason"] == "requires_us_token_or_market_context"
    assert set(provider.config.datasets) == {"realtime"}
    for dataset in ("daily", "minute", "depth5"):
        assert all(item["status"] == "contract_blocked" for item in metadata[dataset].values())


@pytest.mark.parametrize("value", ["", None])
def test_hk_missing_amount_is_null_without_zero_filling(value):
    response = SimpleNamespace(list={"IS": {"indicators": [{"currency": "HKD", "accounts": [
        {"field": "OperatingRevenue", "values": [{"value": value, "fp_end": "1782748800"}]},
    ]}]}})
    row = financial_candidates("700.HK", response)[0]
    assert row["revenue"] is None
    assert row["net_income"] is None
    assert row["announce_date"] is None
    assert row["period_end"] is None


def test_contract_assessment_never_uses_period_label_as_date():
    response = SimpleNamespace(list={"IS": {"indicators": [{"currency": "HKD", "accounts": [
        {"field": "OperatingRevenue", "values": [{
            "period": "2026-06-30", "fp_end": "1782748800", "value": "123.000000001",
        }]},
    ]}]}})
    result = assess_financial_contract("700.HK", response)
    assert result["status"] == "contract_blocked"
    assert result["reason"] == "report_period_timestamp_unit_unverified"
    assert result["unresolved_required_fields"] == ["period_end"]
    assert result["currencies"] == ["HKD"]
    assert result["mapped_fields"] == ["revenue"]
    assert "source_fp_end" not in result
    assert "value" not in result


def test_missing_response_shape_is_not_treated_as_cn_empty():
    with pytest.raises(ValueError, match="financial_response_shape_mismatch"):
        financial_candidates("600519.SH", object())


def test_percent_flag_does_not_trigger_implicit_scaling():
    reports = {"IS": {"indicators": [{"currency": "HKD", "accounts": [
        {"field": "OperatingRevenue", "percent": True, "values": [{"value": "12.3"}]},
    ]}]}}
    assert financial_candidates("700.HK", SimpleNamespace(list=reports)) == []


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "bad", True])
def test_invalid_financial_numbers_are_rejected(number):
    with pytest.raises(ValueError, match="invalid_financial_number"):
        decimal_value(number)


def test_probe_uses_only_fundamental_report_and_returns_safe_summary(monkeypatch):
    provider = LongbridgeProvider()
    calls = []
    def request(kind, method, symbol):
        calls.append((kind, method, symbol))
        return SimpleNamespace(list={})
    monkeypatch.setattr(provider, "dashboard_request", request)
    result = provider.probe_financial_contract("600519.SH")
    assert result["status"] == "empty"
    assert calls == [("fundamental", "financial_report", "600519.SH")]
    assert set(provider.config.datasets) == {"realtime"}


def test_us_context_error_is_sanitized_not_sdk_unsupported(monkeypatch):
    provider = LongbridgeProvider()
    def request(*args):
        raise RuntimeError("sample-secret-token rejected by context")
    monkeypatch.setattr(provider, "dashboard_request", request)
    result = provider.probe_financial_contract("AAPL.US")
    assert result["status"] == "unavailable"
    assert result["reason"] == "requires_us_token_or_market_context"
    assert result["sdk_available"] is True
    assert "sample-secret-token" not in str(result)


def test_probe_unknown_market_does_not_call_sdk(monkeypatch):
    provider = LongbridgeProvider()
    monkeypatch.setattr(provider, "dashboard_request", lambda *args: pytest.fail("SDK must not be called"))
    assert provider.probe_financial_contract("ABC.UNKNOWN")["status"] == "unsupported"


@pytest.mark.parametrize("period", [None, 1782748800, "1782748800", "2026-02-30"])
def test_report_readiness_requires_real_iso_period(period):
    assert not financial_rows_ready([{"symbol": "700.HK", "period_end": period}])


def test_legacy_iso_report_without_announcement_remains_valid():
    assert financial_rows_ready([{"symbol": "600519.SH", "period_end": "2026-06-30"}])


def test_currency_is_preserved_not_guessed_from_hk_symbol():
    response = {"list": {"BS": {"indicators": [{"currency": "USD", "accounts": [
        {"field": "TotalAssets", "values": [{"value": "0.12345678901234567890123456789"}]},
    ]}]}}}
    row = financial_candidates("700.HK", response)[0]
    assert row["currency"] == "USD"
    assert row["total_assets"] == Decimal("0.12345678901234567890123456789")
    assert row["total_liabilities"] is None


def test_present_report_with_unmapped_eps_is_blocked_not_empty():
    response = {"list": {"IS": {"indicators": [{"accounts": [
        {"field": "EPS", "values": [{"value": "1.2"}]},
    ]}]}}}
    assert assess_financial_contract("700.HK", response)["status"] == "contract_blocked"
