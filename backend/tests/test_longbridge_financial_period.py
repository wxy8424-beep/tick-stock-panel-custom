from datetime import date
from types import SimpleNamespace

import pytest

from app.plugins.longbridge.financial import (
    assess_financial_contract,
    financial_candidates,
    financial_rows_ready,
    inspect_period_end,
)
from app.plugins.longbridge.provider import LongbridgeProvider
from app.plugins.longbridge.quantity import quantity_capabilities


def report(value):
    return SimpleNamespace(list={"IS": {"indicators": [{"currency": "HKD", "accounts": [
        {"field": "OperatingRevenue", "values": [{
            "fp_end": value, "period": "2026-06-30", "year": 2026, "value": "123.45",
            "announcement_date": "2026-08-01",
        }]},
    ]}]}})


@pytest.mark.parametrize("value", [
    "1782748800", "1782748800000", "20260630", "2026-06-30", "2026-W27-2",
    "Q2 2026", "0", "-1", "NaN", "not-a-date",
])
def test_date_looking_strings_do_not_establish_encoding(value):
    result = inspect_period_end(value)
    assert result["reason"] == "report_period_timestamp_unit_unverified"
    assert result["period_end"] is None
    assert result["unit"] == result["encoding"] == result["timezone"] == "unverified"
    rows = financial_candidates("700.HK", report(value))
    assert rows[0]["source_fp_end"] == value
    assert rows[0]["period_end"] is None and rows[0]["announce_date"] is None
    assert not financial_rows_ready(rows)


@pytest.mark.parametrize("value", [None, "", "  "])
def test_missing_period_is_explicit_and_not_filled_from_quarter(value):
    assert inspect_period_end(value)["reason"] == "financial_period_end_missing"
    rows = financial_candidates("700.HK", report(value))
    assert rows[0]["period_end"] is None
    summary = assess_financial_contract("700.HK", report(value))
    assert summary["period_end_evidence"]["blockers"] == ["financial_period_end_missing"]


@pytest.mark.parametrize("value", [1782748800, 1782748800.0, True, [], {}, date(2026, 6, 30)])
def test_schema_type_mismatch_fails_closed_without_guessing(value):
    assert inspect_period_end(value)["reason"] == "financial_period_end_type_invalid"
    with pytest.raises(ValueError, match="financial_period_end_type_invalid"):
        financial_candidates("700.HK", report(value))


@pytest.mark.parametrize("timezone", ["UTC", "Asia/Hong_Kong", "America/New_York"])
def test_timezone_cannot_turn_unverified_source_into_iso(monkeypatch, timezone):
    monkeypatch.setenv("TZ", timezone)
    # Also forbid all date-class use: no implicit local/UTC parsing is permitted.
    monkeypatch.setattr("app.plugins.longbridge.financial.date", None)
    summary = assess_financial_contract("700.HK", report("1782748800"))
    assert summary["status"] == "contract_blocked"
    assert summary["unresolved_required_fields"] == ["period_end"]
    assert summary["period_end_evidence"]["conversion_performed"] is False
    assert summary["period_end_evidence"]["source_types"] == ["string"]


def test_safe_summary_has_no_raw_value_or_fabricated_announcement():
    sample = "fake-sensitive-diagnostic-marker"
    summary = assess_financial_contract("700.HK", report(sample))
    assert sample not in str(summary)
    assert "announcement_date" not in summary
    assert "announce_date" in summary["missing_optional_fields"]
    assert "source_fp_end" not in summary


def test_provider_returns_fixed_period_type_blocker(monkeypatch):
    provider = LongbridgeProvider()
    monkeypatch.setattr(provider, "dashboard_request", lambda *args: report({"unexpected": "shape"}))
    result = provider.probe_financial_contract("700.HK")
    assert result == {"status": "contract_blocked", "reason": "financial_period_end_type_invalid", "sdk_available": True}


@pytest.mark.parametrize("value", ["20260630", "2026-W27-2", "2026-06-30T00:00:00", "2026-02-30"])
def test_readiness_requires_exact_iso_date_not_alternative_iso_forms(value):
    assert not financial_rows_ready([{"symbol": "700.HK", "period_end": value}])


def test_capability_scope_and_quantity_realtime_are_unchanged():
    provider = LongbridgeProvider()
    metadata = provider.market_capabilities
    for dataset, entries in quantity_capabilities().items():
        assert metadata[dataset] == entries
    assert all(row["status"] == "supported" for row in metadata["realtime"].values())
    assert metadata["financial"]["HK"]["reason"] == "report_period_timestamp_unit_unverified"
    assert metadata["financial"]["CN"]["status"] == "empty"
    assert metadata["financial"]["US"]["status"] == "unavailable"
    assert metadata["financial"]["US"]["sdk_available"] is True
    assert set(provider.config.datasets) == {"realtime"}
