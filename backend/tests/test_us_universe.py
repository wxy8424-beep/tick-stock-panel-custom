from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event

import pytest

from app.services.us_dashboard_service import USDashboardService
from tests.test_us_dashboard import FakeProvider


class UniverseProvider(FakeProvider):
    def __init__(self, size=1001):
        super().__init__()
        self.symbols = [f"S{i}.US" for i in range(size)]
        self.batches = []
        self.list_calls = 0
        self.fail_batches = set()

    def get_realtime_universe(self, market):
        assert market == "US"
        self.list_calls += 1
        return self.symbols

    def get_realtime(self, symbols):
        self.batches.append(symbols)
        if symbols[0] in self.fail_batches:
            raise RuntimeError("fake-token network timeout")
        return [{"symbol": s, "market": "US", "last_price": 102, "change_pct": .02,
                 "amount": 1000, "currency": "USD", "timestamp": 1791468000000}
                for s in symbols]


def service(provider):
    svc = USDashboardService(lambda: provider, universe_enabled=True,
                             clock=lambda: datetime(2026, 10, 8, 14, tzinfo=UTC))
    # Exercise one deterministic sweep, without network or background scheduling.
    svc._ensure_universe_worker = lambda: None
    return svc


@pytest.mark.parametrize("size,batches", [(500, 1), (501, 2), (1001, 3)])
def test_universe_chunks_and_shared_read_snapshot(size, batches):
    provider = UniverseProvider(size)
    svc = service(provider)
    svc.refresh_universe()
    result = svc.get("AAPL.US", [])
    assert len(provider.batches) == batches
    assert max(map(len, provider.batches)) <= 500
    assert result["sample"]["requested"] == size
    assert result["sample"]["received"] == size
    assert result["sample"]["status"] == "ready"
    assert result["sample"]["exchange_complete"] is False
    assert result["kpi"]["data"]["total"] == size
    assert sum(bin["count"] for bin in result["distribution"]["data"]["bins"]) == size
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(lambda _: svc.get("AAPL.US", []), range(5)))
    assert len(provider.batches) == batches
    svc.close()


def test_failed_batch_isolated_and_previous_rows_not_mixed():
    provider = UniverseProvider()
    svc = service(provider)
    svc.refresh_universe()
    provider.fail_batches.add("S500.US")
    svc.refresh_universe()
    result = svc.get("AAPL.US", [])
    assert result["sample"]["received"] == 501
    assert result["sample"]["failed"] == 500
    assert result["sample"]["failed_batches"] == 1
    assert result["sample"]["status"] == "partial"
    assert result["kpi"]["data"]["total"] == 501
    assert "fake-token" not in str(result)
    assert provider.list_calls == 1


def test_all_failed_retains_last_snapshot_explicitly_stale():
    provider = UniverseProvider(1)
    svc = service(provider)
    svc.refresh_universe()
    provider.fail_batches.add("S0.US")
    svc.refresh_universe()
    result = svc.get("AAPL.US", [])
    assert result["sample"]["stale"] is True
    assert result["sample"]["status"] == "stale"
    assert result["kpi"]["data"]["total"] == 1


def test_market_guard_dedup_and_unrecognized_list_codes_visible():
    provider = UniverseProvider(0)
    provider.symbols = ["AAPL.US", "AAPL.US", "DCOM-.US", "700.HK", "600519.SH", "BAD.UNKNOWN"]
    svc = service(provider)
    svc.refresh_universe()
    result = svc.get(None, [])
    assert provider.batches == [["AAPL.US", "DCOM-.US"]]
    assert result["sample"]["requested"] == 2
    assert result["sample"]["rejected_symbols"] == 3
    assert result["sample"]["status"] == "partial"


def test_provider_reload_drops_old_universe_snapshot():
    providers = [UniverseProvider(2)]
    svc = service(providers[0])
    svc.provider_getter = lambda: providers[0]
    svc.refresh_universe()
    providers[0] = UniverseProvider(3)
    result = svc.get(None, [])
    assert result["sample"]["received"] == 0
    svc.refresh_universe()
    assert svc.get(None, [])["sample"]["received"] == 3


def test_loading_does_not_present_small_sample_as_universe():
    svc = service(UniverseProvider())
    result = svc.get(None, [])
    assert result["sample"]["status"] == "loading"
    assert result["sample"]["received"] == 0
    assert result["kpi"]["data"] is None
    assert result["indices"]["status"] == "ok"


def test_shutdown_interrupts_sweep_and_no_partial_publish():
    provider = UniverseProvider(501)
    svc = service(provider)
    original = provider.get_realtime

    def stop_after_batch(symbols):
        rows = original(symbols)
        svc.universe_stop.set()
        return rows

    provider.get_realtime = stop_after_batch
    svc.refresh_universe()
    assert len(provider.batches) == 1
    assert svc.universe_snapshot is None


def test_old_quotes_excluded_from_latest_date_statistics_without_faking_coverage():
    provider = UniverseProvider(2)
    original = provider.get_realtime

    def different_dates(symbols):
        rows = original(symbols)
        rows[0]["timestamp"] -= 86400000
        return rows

    provider.get_realtime = different_dates
    svc = service(provider)
    svc.refresh_universe()
    result = svc.get(None, [])
    assert result["sample"]["received"] == 2
    assert result["sample"]["statistics_received"] == 1
    assert result["sample"]["stale_quote_count"] == 1
    assert result["sample"]["statistics_date"] == "2026-10-08"
    assert result["kpi"]["data"]["total"] == 1


def test_only_one_worker_created_for_many_readers():
    provider = UniverseProvider(1)
    svc = USDashboardService(lambda: provider, universe_enabled=True)
    reached = Event()
    svc.refresh_universe = reached.set
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(lambda _: svc._ensure_universe_worker(), range(20)))
    assert reached.wait(1)
    thread = svc.universe_thread
    svc.close()
    assert not thread.is_alive()
