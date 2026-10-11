"""Market data quality uses mock quotes/clocks, never live accounts or network."""
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.data_providers.quote_quality import aggregate_quality, quality_view, validate_quote
from app.market_session import clear_market_signals
from app.plugins.longbridge import provider as lb
from app.plugins.longbridge.realtime_health import evaluate

NOW = datetime(2026, 10, 9, 14, tzinfo=UTC)


@pytest.fixture(autouse=True)
def signals():
    clear_market_signals()
    yield
    clear_market_signals()


def row(**changes):
    result = {"symbol": "AAPL.US", "market": "US", "last_price": 100,
              "prev_close": 99, "open": 99, "high": 101, "low": 98,
              "volume": 1000, "volume_unit": "shares", "timestamp": int(NOW.timestamp() * 1000)}
    result.update(changes)
    return result


def test_normal_quote_not_mutated_and_safe_json():
    source = row()
    before = source.copy()
    result = validate_quote(source, NOW + timedelta(seconds=1))
    assert source == before
    assert result == {"state": "valid", "warnings": [], "observed_at": (NOW + timedelta(seconds=1)).isoformat(),
                      "latency_ms": 1000}
    assert json.loads(json.dumps(result, allow_nan=False)) == result


@pytest.mark.parametrize("value", [-1, 0, float("nan"), float("inf"), True, "100", Decimal("NaN")])
def test_bad_price(value):
    result = validate_quote(row(last_price=value), NOW)
    assert result["state"] == "invalid" and "last_price_invalid" in result["warnings"]


@pytest.mark.parametrize("changes", [{"high": 97}, {"low": 102}, {"open": 110}, {"last_price": 110}])
def test_ohlc_relationships(changes):
    assert "ohlc_inconsistent" in validate_quote(row(**changes), NOW)["warnings"]


def test_missing_zero_ohlc_and_volume_stay_unknown():
    result = validate_quote(row(open=0, high=0, low=None, volume=None, volume_unit="unsupported"), NOW)
    assert result["state"] == "unknown"
    assert {"open_unknown", "high_unknown", "low_unknown", "volume_unknown", "volume_unit_unknown"} <= set(result["warnings"])
    assert validate_quote(row(volume=0), NOW)["state"] == "valid"
    assert validate_quote(row(volume_unit="legacy_100_shares"), NOW)["state"] == "valid"


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True, "1000"])
def test_bad_volume_and_raw_provider_volume(value):
    assert "volume_invalid" in validate_quote(row(volume=value), NOW)["warnings"]
    result = validate_quote(row(volume=None, volume_unit="unverified"), NOW, provider_volume=value)
    assert result["state"] == "invalid" and "provider_volume_invalid" in result["warnings"]


@pytest.mark.parametrize("timestamp", [0, -1, float("nan"), float("inf"), True, "invalid", 10 ** 1000])
def test_bad_timestamp_safe(timestamp):
    report = validate_quote(row(timestamp=timestamp), NOW)
    assert report["state"] == "invalid" and report["latency_ms"] is None
    assert "timestamp_invalid" in report["warnings"]


def test_future_timestamp_not_negative_latency_or_clock_guess():
    report = validate_quote(row(timestamp=int((NOW + timedelta(seconds=1)).timestamp() * 1000)), NOW)
    assert report["state"] == "invalid"
    assert report["latency_ms"] is None and "timestamp_future" in report["warnings"]
    with pytest.raises(ValueError):
        validate_quote(row(), NOW.replace(tzinfo=None))
    assert validate_quote(row(timestamp=Decimal(str(int(NOW.timestamp() * 1000)))), NOW)["state"] == "valid"


def test_event_age_distinct_from_receipt_freshness():
    report = validate_quote(row(timestamp=int((NOW - timedelta(seconds=121)).timestamp() * 1000)), NOW)
    assert report["state"] == "stale" and report["latency_ms"] == 121000
    result = evaluate("US", {"received_at": NOW, "quality": report}, NOW, True, True)
    assert result["runtime_status"] == "healthy"  # reception health stays backward compatible
    assert result["quality"]["state"] == "stale"


def test_closed_snapshot_not_stale_but_new_closed_event_warned():
    closed = datetime(2026, 10, 10, 14, tzinfo=UTC)
    historical = validate_quote(row(), closed)
    assert historical["state"] == "valid" and historical["warnings"] == []
    recent = validate_quote(row(timestamp=int(closed.timestamp() * 1000)), closed)
    assert recent["state"] == "warning" and "quote_during_closed_market" in recent["warnings"]
    # Exact normal close belongs to the regular window; no false closed warning.
    end = datetime(2026, 10, 9, 20, tzinfo=UTC)
    later = validate_quote(row(timestamp=int(end.timestamp() * 1000)), end + timedelta(seconds=10))
    assert "quote_during_closed_market" not in later["warnings"]


def test_unknown_market_or_calendar_and_null_timestamp_do_not_become_valid():
    for changes in [{"market": "HK"}, {"symbol": "ABC.UNKNOWN"}, {"timestamp": None}, {"last_price": None}]:
        assert validate_quote(row(**changes), NOW)["state"] == "unknown"
    uncovered = datetime(2027, 1, 4, 14, tzinfo=UTC)
    assert validate_quote(row(timestamp=int(uncovered.timestamp() * 1000)), uncovered)["state"] == "unknown"


def test_aggregate_batch_clocks_and_partial_invalid_remain_visible():
    first = validate_quote(row(), NOW)
    second = validate_quote(row(high=97), NOW + timedelta(seconds=2))
    summary = aggregate_quality([first, second], NOW + timedelta(seconds=3))
    assert summary["state"] == "invalid" and summary["counts"]["invalid"] == 1
    assert summary["quote_count"] == 2 and summary["latency_ms"] == 3000
    assert summary["observed_at"] == (NOW + timedelta(seconds=3)).isoformat()


def test_unavailable_no_data_and_old_observation_serialization():
    old = {"received_at": NOW, "checked_at": NOW}
    result = evaluate("US", old, NOW, True, True)
    assert result["runtime_status"] == "healthy" and result["last_received_at"] == NOW.isoformat()
    assert result["quality"]["state"] == "unknown" and result["quality"]["observed_at"] is None
    unknown = evaluate("US", {**old, "quality": validate_quote(row(), NOW)}, NOW, True, False)
    assert unknown["runtime_status"] == "unavailable"
    assert unknown["quality"]["state"] == "unknown"
    assert unknown["quality"]["warnings"] == ["provider_unavailable"]
    assert quality_view(None, True)["latency_ms"] is None
    json.dumps(result, allow_nan=False)


@pytest.fixture
def provider(monkeypatch):
    def quotes(symbols):
        return [SimpleNamespace(symbol=s, last_done=100, prev_close=99, open=99,
                                high=101, low=98, turnover=1000, volume=100,
                                timestamp=NOW) for s in symbols]
    context = SimpleNamespace(quote=quotes, static_info=lambda symbols: [])
    monkeypatch.setattr(lb, "_credentials", lambda: ("mock-key", "mock-secret", "mock-token"))
    monkeypatch.setattr(lb, "_sdk", lambda: SimpleNamespace(
        Config=SimpleNamespace(from_apikey=lambda *args, **kwargs: object()),
        QuoteContext=lambda config: context))
    return lb.LongbridgeProvider(clock=lambda: NOW), context


def test_provider_output_contract_quality_and_market_isolation(provider, monkeypatch):
    service, context = provider
    original = context.quote
    def quotes(symbols):
        values = original(symbols)
        values[0].high = 90
        return values
    monkeypatch.setattr(context, "quote", quotes)
    rows = service.get_realtime(["AAPL.US", "700.HK"])
    assert len(rows) == 2 and all("quality" not in value for value in rows)
    assert all(value["volume"] is None for value in rows)
    view = service.provider_health()
    assert view["realtime"]["US"]["status"] == "supported"
    assert view["realtime"]["US"]["runtime"]["quality"]["state"] == "invalid"
    assert "ohlc_inconsistent" in view["realtime"]["US"]["runtime"]["quality"]["warnings"]
    assert view["realtime"]["HK"]["runtime"]["quality"]["state"] != "invalid"
    assert view["realtime"]["CN"]["runtime"]["quality"]["state"] == "unknown"
    for dataset in ("daily", "minute", "depth5", "financial"):
        assert view[dataset]["US"]["status"] == "contract_blocked"
    encoded = json.dumps(view, allow_nan=False)
    assert "mock-secret" not in encoded and "mock-token" not in encoded
    service.close()
    assert service.provider_health()["realtime"]["US"]["runtime"]["quality"]["observed_at"] is None


def test_parser_rejection_and_failed_call_never_fabricate_quality(provider, monkeypatch):
    service, context = provider
    original = context.quote
    def bad(symbols):
        values = original(symbols)
        values[0].last_done = -1
        return values
    monkeypatch.setattr(context, "quote", bad)
    assert service.get_realtime(["AAPL.US"]) == []
    view = service.provider_health()["realtime"]["US"]["runtime"]
    assert view["quality"]["state"] == "invalid" and view["last_received_at"] is None
    monkeypatch.setattr(context, "quote", lambda symbols: [])
    service.get_realtime(["AAPL.US"])
    assert service.provider_health()["realtime"]["US"]["runtime"]["quality"]["state"] == "unknown"


def test_optional_quality_failure_keeps_quote_and_redacts(provider, monkeypatch):
    service, _ = provider
    def broken(*args, **kwargs):
        raise RuntimeError("mock-secret-private-payload")
    monkeypatch.setattr(lb, "validate_quote", broken)
    assert len(service.get_realtime(["AAPL.US"])) == 1
    quality = service.provider_health()["realtime"]["US"]["runtime"]["quality"]
    assert quality["state"] == "unknown" and quality["warnings"] == ["quality_check_unknown"]
    assert "mock-secret" not in json.dumps(service.provider_health())
