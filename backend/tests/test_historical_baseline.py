"""Daily context uses local provider fixtures; no SDK/network/account dependency."""
import json
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.anomalies import router
from app.data_providers.historical import HistoricalDailyResult
from app.factors.engine import FactorRequest, MarketFactorEngine
from app.services.anomaly_engine import AnomalyEvent, AnomalyStore
from app.services.historical_baseline import (
    SOURCES,
    HistoricalBaselineService,
    HistoricalContextStore,
    enrich_response,
)
from app.services.historical_enrichment import HistoricalEnrichmentWorker

D = date(2026, 10, 9)


def frame(symbol, market, days=None):
    days = days if days is not None else [D - timedelta(days=i) for i in range(50, 0, -1) if (D - timedelta(days=i)).weekday() < 5]
    method = "none" if market == "CN" else "yfinance_auto_adjust_false"
    adjusted_method = "akshare_qfq" if market == "CN" else "yfinance_auto_adjust"
    return pl.DataFrame([{"symbol": symbol, "market": market, "trading_date": day,
                         "open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0,
                         "adjusted_open": 50.0, "adjusted_high": 51.0, "adjusted_low": 49.0, "adjusted_close": 50.0,
                         "source": SOURCES[market], "adjustment_method": method, "adjusted_adjustment_method": adjusted_method}
                        for day in days])


class Provider:
    def __init__(self, chosen=None, fail=False):
        self.calls = []
        self.chosen = chosen
        self.fail = fail

    def fetch_daily(self, symbol, start, end, mode):
        self.calls.append((symbol, start, end, mode))
        if self.fail:
            raise RuntimeError("private upstream authorization text")
        market = "CN" if symbol.endswith(".SH") else "US"
        return HistoricalDailyResult(symbol, market, mode, SOURCES[market], self.chosen if self.chosen is not None else frame(symbol, market), "ok", ())


def service(tmp_path, provider=None, engine=None, version="test-v1"):
    provider = provider or Provider()
    return HistoricalBaselineService(tmp_path, provider_factory=lambda _: provider, factor_engine=engine, version=version), provider


@pytest.mark.parametrize("symbol,method", [("600519.SH", "none"), ("AAPL.US", "yfinance_auto_adjust_false")])
def test_cn_us_baseline_reuses_atr_and_provenance(tmp_path, symbol, method):
    baseline, provider = service(tmp_path)
    result = baseline.baseline(symbol, D)
    assert result["status"] == "available" and result["adjustment_method"] == method
    assert result["as_of_date"] == D.isoformat() and result["lookback_end"] < D.isoformat()
    assert provider.calls[0][2] == D - timedelta(days=1)
    data = frame(symbol, "CN" if symbol.endswith(".SH") else "US").rename({"trading_date": "date"})
    expected = MarketFactorEngine().compute(data, (FactorRequest("atr", 14),), mode="research").frame["atr_14"][-1]
    assert float(result["atr14"]) == expected
    assert result["observations"] == data.height
    assert result["pit_capable"] is False
    assert result["bars"][-1]["date"] == result["lookback_end"]
    json.dumps(result, allow_nan=False)


def test_pit_provider_d_and_future_rows_are_cut_before_factor(tmp_path):
    days = [D - timedelta(days=2), D - timedelta(days=1), D, D + timedelta(days=1)]
    data = frame("AAPL.US", "US", days)

    class Spy(MarketFactorEngine):
        dates = ()

        def compute(self, history, *args, **kwargs):
            self.dates = history["date"].to_list()
            return super().compute(history, *args, **kwargs)

    spy = Spy()
    baseline, _ = service(tmp_path, Provider(data), spy)
    result = baseline.baseline("AAPL.US", D)
    assert spy.dates == days[:2]
    assert [row["date"] for row in result["bars"]] == [value.isoformat() for value in days[:2]]
    assert result["observations"] == 2 and result["atr14"] is None
    assert result["blocker"] == "insufficient_atr_history"


def test_hk_unsupported_never_calls_provider(tmp_path):
    baseline, provider = service(tmp_path)
    result = baseline.context({"symbol": "700.HK", "market": "HK", "change_value": "-4.1"}, D)
    assert result["status"] == "unsupported" and result["atr14"] is None
    assert result["move_atr_ratio"] is None and provider.calls == []


def test_ratio_is_absolute_and_recomputable(tmp_path):
    baseline, _ = service(tmp_path)
    result = baseline.context({"symbol": "AAPL.US", "market": "US", "change_value": "-4.1"}, D)
    assert result["status"] == "available" and result["move_absolute"] == "4.1"
    assert float(result["move_atr_ratio"]) == pytest.approx(4.1 / float(result["atr14"]))


def test_cache_survives_restart_and_isolates_symbol_date_mode_version(tmp_path):
    baseline, provider = service(tmp_path)
    success = baseline.baseline("AAPL.US", D)
    assert baseline.baseline("AAPL.US", D) == success
    again, _ = service(tmp_path, provider)
    assert again.baseline("AAPL.US", D) == success and len(provider.calls) == 1
    baseline.baseline("NVDA.US", D)
    baseline.baseline("AAPL.US", D - timedelta(days=1))
    adjusted = baseline.baseline("AAPL.US", D, "yfinance_auto_adjust")
    service(tmp_path, provider, version="test-v2")[0].baseline("AAPL.US", D)
    assert len(provider.calls) == 5
    assert adjusted["adjustment_method"] == "yfinance_auto_adjust"
    assert float(adjusted["atr14"]) != float(success["atr14"])
    result = baseline.context({"symbol": "AAPL.US", "market": "US", "change_value": "4.1"}, D, "yfinance_auto_adjust")
    assert result["move_atr_ratio"] is None and result["blocker"] == "adjusted_baseline_realtime_price_basis_unverified"


def test_failure_cached_separately_and_never_leaks_raw_error(tmp_path):
    baseline, provider = service(tmp_path, Provider(fail=True))
    failed = baseline.baseline("AAPL.US", D)
    assert failed["status"] == "unavailable" and failed["atr14"] is None
    assert "authorization" not in json.dumps(failed)
    provider.fail = False
    assert baseline.baseline("AAPL.US", D) == failed and len(provider.calls) == 1
    assert baseline.baseline("NVDA.US", D)["status"] == "available"


def test_cn_adjusted_is_separate_and_not_silently_used_for_raw_move(tmp_path):
    baseline, provider = service(tmp_path)
    raw = baseline.baseline("600519.SH", D)
    adjusted = baseline.baseline("600519.SH", D, "akshare_qfq")
    assert raw["adjustment_method"] == "none" and adjusted["adjustment_method"] == "akshare_qfq"
    assert len(provider.calls) == 2
    context = baseline.context({"symbol": "600519.SH", "market": "CN", "change_value": "4"}, D, "akshare_qfq")
    assert context["atr14"] is not None and context["move_atr_ratio"] is None
    assert context["status"] == "unsupported"


def test_cache_failure_prevents_uncached_network_retries(tmp_path, monkeypatch):
    baseline, provider = service(tmp_path)

    def fail(*args):
        raise OSError("private path")

    monkeypatch.setattr(baseline.store, "reserve", fail)
    result = baseline.baseline("AAPL.US", D)
    assert result["blocker"] == "baseline_cache_unavailable" and provider.calls == []


def test_future_evaluation_and_missing_price_fail_closed(tmp_path):
    baseline, provider = service(tmp_path)
    result = baseline.baseline("AAPL.US", date(2099, 1, 1))
    assert result["blocker"] == "evaluation_date_in_future" and not provider.calls
    data = frame("AAPL.US", "US").with_columns(pl.lit(None, dtype=pl.Float64).alias("close"))
    baseline, _ = service(tmp_path, Provider(data))
    assert baseline.baseline("AAPL.US", D)["blocker"] == "historical_price_missing_or_invalid"


@pytest.mark.parametrize("atr", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_or_zero_atr_never_produces_ratio(tmp_path, atr):
    engine = SimpleNamespace(compute=lambda *args, **kwargs: SimpleNamespace(frame=pl.DataFrame({"atr_14": [atr]})))
    baseline, _ = service(tmp_path, engine=engine)
    result = baseline.context({"symbol": "AAPL.US", "market": "US", "change_value": "4"}, D)
    assert result["status"] == "unknown" and result["atr14"] is None and result["move_atr_ratio"] is None


def test_context_worker_failure_does_not_mutate_event_or_sequence(tmp_path):
    events = AnomalyStore(tmp_path)
    event = {"event_id": "a" * 64, "episode_id": "b" * 64, "symbol": "AAPL.US", "market": "US",
             "event_type": "rapid_price_move", "severity": "high", "status": "first_trigger", "change_value": "4",
             "evidence": {"current": {"quote_timestamp": int(datetime(2026, 10, 9, 14, tzinfo=UTC).timestamp() * 1000)}}}
    with closing(events.connect()) as db, db:
        db.execute("INSERT INTO anomaly_events(event_id,episode_id,symbol,market,event_type,severity,detected_at,payload) VALUES (?,?,?,?,?,?,?,?)",
                   (event["event_id"], event["episode_id"], event["symbol"], "US", "rapid_price_move", "high", 1000, json.dumps(event)))
    before = events.path.read_bytes()
    baseline, _ = service(tmp_path, Provider(fail=True))
    worker = HistoricalEnrichmentWorker(tmp_path, baseline)
    worker.tick()
    context = baseline.store.read_many([event["event_id"]])[event["event_id"]]
    assert context["status"] == "unavailable" and context["move_atr_ratio"] is None
    assert events.path.read_bytes() == before
    assert events.query()["rows"][0]["status"] == "first_trigger"
    assert events.delivery_state()["latest_sequence"] == 1
    worker.tick()
    assert worker.health()["processed"] == 0
    page = enrich_response(tmp_path, events.query())
    assert page["rows"][0]["evidence"]["historical_context"] == context
    assert events.path.read_bytes() == before


def test_readonly_api_context_absent_storage_and_hard_limits(tmp_path):
    app = FastAPI()
    app.include_router(router)
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    client = TestClient(app)
    result = client.get("/api/intraday/anomalies/historical-context?event_id=abc").json()
    assert result["status"] == "unknown" and result["atr14"] is None
    assert client.get("/api/intraday/anomalies/historical-contexts", params=[("event_id", "abc")]).json()["contexts"]["abc"] == result
    assert not HistoricalContextStore(tmp_path).path.exists()
    assert client.get("/api/intraday/anomalies/historical-contexts", params=[("event_id", "a")] * 101).status_code == 422


def test_original_event_model_accepts_optional_context_and_missing_field(tmp_path):
    # Reuse a real mock-produced event from the existing detection test fixture.
    from tests.test_anomaly_engine import warmup

    _, engine, at = warmup(tmp_path)
    event = engine.run_once(at, start_from_latest=False)["events"][-1]
    event["evidence"].pop("historical_context", None)
    original = AnomalyEvent.model_validate(event)
    assert original.evidence.historical_context is None
    event["evidence"]["historical_context"] = {"status": "unavailable", "atr14": None}
    assert AnomalyEvent.model_validate(event).evidence.historical_context["status"] == "unavailable"
