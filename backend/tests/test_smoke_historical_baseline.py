"""Harness regression uses fixtures exclusively, never third-party network calls."""
from datetime import timedelta

import pytest

from scripts.smoke_historical_baseline import smoke_symbol
from tests.test_historical_baseline import D, Provider, frame


@pytest.mark.parametrize("symbol,market", [("600519.SH", "CN"), ("AAPL.US", "US")])
def test_harness_real_contract_and_fixture_overlay(tmp_path, symbol, market):
    days = [D - timedelta(days=i) for i in range(50, -2, -1)]
    provider = Provider(frame(symbol, market, days))
    report = smoke_symbol(symbol, D, tmp_path, lambda _: provider)
    assert report["status"] == "PASS" and all(report["checks"].values())
    assert report["provider_returned_evaluation_bar"]
    assert report["prior_completed_as_of_date"] < D.isoformat()
    assert report["service_as_of_date_is_evaluation_date"] == D.isoformat()
    assert report["cache"]["successful_baseline_cached"] and len(provider.calls) == 1
    assert provider.calls[0][2] == D
    assert report["move_atr_ratio"] is None and report["integration"]["status"] == "PASS"
    assert report["integration"]["production_event_inserted"] is False


def test_failed_fetch_is_not_successful_cache_evidence(tmp_path):
    provider = Provider(fail=True)
    report = smoke_symbol("AAPL.US", D, tmp_path, lambda _: provider)
    assert report["status"] == "BLOCKED" and len(provider.calls) == 1
    assert report["cache"]["result_equal"] and not report["cache"]["successful_baseline_cached"]
    assert "integration" not in report
