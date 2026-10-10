from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.plugins.longbridge.financial import (
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
