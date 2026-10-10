from copy import deepcopy
from threading import Lock
from types import SimpleNamespace

import polars as pl
import pytest

from app.data_providers.contracts import dataset_status, validate_quantity_units
from app.plugins.longbridge.provider import LongbridgeProvider
from app.plugins.longbridge.quantity import REASONS


@pytest.fixture
def probe(monkeypatch):
    calls = []
    context = SimpleNamespace(
        history_candlesticks_by_offset=lambda *args: calls.append(args) or [SimpleNamespace(volume=12345)],
        depth=lambda *args: calls.append(args) or SimpleNamespace(
            asks=[SimpleNamespace(volume=12345)], bids=[SimpleNamespace(volume=67890)],
        ),
    )
    # No installed SDK, credentials or network are used by automated tests.
    monkeypatch.setattr("app.plugins.longbridge.provider._sdk", lambda: SimpleNamespace(
        Period=SimpleNamespace(Day="day", Min_1="minute"), AdjustType=SimpleNamespace(NoAdjust="raw"),
    ))
    provider = LongbridgeProvider()
    provider._lock = Lock()
    provider._context = context
    return provider, context, calls


@pytest.mark.parametrize("symbol", ["600519.SH", "700.HK", "AAPL.US"])
@pytest.mark.parametrize("dataset", list(REASONS))
def test_integer_observations_never_unlock_any_market_or_endpoint(probe, symbol, dataset):
    provider, _, calls = probe
    before = deepcopy(provider.market_capabilities)
    result = provider.probe_quantity_contract(symbol, dataset)
    assert result["status"] == "CONTRACT_BLOCKED"
    assert result["request_status"] == "success"
    assert result["quantity_unit"] == "unknown"
    assert result["reason"] == REASONS[dataset]
    assert result["volume_type"] == "int"
    assert "volume" not in result and "lot_size" not in result
    assert provider.market_capabilities == before
    assert set(provider.config.datasets) == {"realtime"}
    assert dataset_status(provider, dataset, result["market"])["status"] == "contract_blocked"
    assert calls == ([(symbol,)] if dataset == "depth5" else [
        (symbol, "day" if dataset == "daily" else "minute", "raw", False, 2),
    ])


@pytest.mark.parametrize("response,status", [
    ([], "empty"), (None, "response_shape_mismatch"),
    ([SimpleNamespace(volume="123")], "response_shape_mismatch"),
    ([SimpleNamespace(volume=True)], "response_shape_mismatch"),
    ([SimpleNamespace(volume=-1)], "response_shape_mismatch"),
    ([SimpleNamespace(turnover=123, lot_size=100)], "response_shape_mismatch"),
])
def test_no_inference_from_turnover_lot_or_malformed_candles(probe, response, status):
    provider, context, _ = probe
    context.history_candlesticks_by_offset = lambda *args: response
    result = provider.probe_quantity_contract("700.HK", "daily")
    assert result["request_status"] == status
    assert result["status"] == ("EMPTY" if status == "empty" else "CONTRACT_BLOCKED")
    assert provider.market_capabilities["daily"]["HK"]["status"] == "contract_blocked"


def test_empty_depth_and_missing_side_are_distinct(probe):
    provider, context, _ = probe
    context.depth = lambda symbol: SimpleNamespace(asks=[], bids=[])
    assert provider.probe_quantity_contract("700.HK", "depth5")["status"] == "EMPTY"
    context.depth = lambda symbol: SimpleNamespace(asks=[])
    assert provider.probe_quantity_contract("700.HK", "depth5")["request_status"] == "response_shape_mismatch"


def test_missing_method_does_not_unlock_other_markets(probe):
    provider, context, _ = probe
    context.depth = None
    result = provider.probe_quantity_contract("AAPL.US", "depth5")
    assert result["status"] == "SDK_UNSUPPORTED"
    assert result["request_status"] == "method_missing"
    assert all(row["status"] == "contract_blocked" for row in provider.market_capabilities["depth5"].values())


@pytest.mark.parametrize("code,message,category", [
    (301604, "private SDK exception marker", "entitlement_denied"),
    (401003, "private SDK exception marker", "authentication"),
    (None, "network timeout", "network"),
    (None, "unrecognized SDK failure", "sdk_exception"),
])
def test_failures_are_sanitized_and_isolated(probe, code, message, category):
    provider, context, _ = probe
    def fail(*args):
        error = RuntimeError(message)
        error.code = code
        raise error
    context.depth = fail
    result = provider.probe_quantity_contract("600519.SH", "depth5")
    assert result["request_status"] == category
    assert result["status"] == "CONTRACT_BLOCKED"
    assert message not in str(result)
    assert provider.probe_quantity_contract("AAPL.US", "daily")["request_status"] == "success"


@pytest.mark.parametrize("symbol,dataset", [("ABC.UNKNOWN", "daily"), ("700.HK", "trade"), ("700.HK", "full_minute")])
def test_invalid_probe_never_creates_context(probe, symbol, dataset):
    provider, _, calls = probe
    with pytest.raises(ValueError, match="unsupported_quantity_probe"):
        provider.probe_quantity_contract(symbol, dataset)
    assert calls == []


@pytest.mark.parametrize("unit", ["unknown", "shares", "board_lots", "contracts"])
def test_diagnostic_quantities_cannot_enter_legacy_normalizers(unit):
    from app.data_providers.custom.provider import GenericHTTPProvider
    from app.data_providers.normalizer import normalize_daily
    from app.services.kline_sync import _normalize_daily, _normalize_minute

    frame = pl.DataFrame({"symbol": ["700.HK"], "volume": [12345], "quantity_unit": [unit]})
    for normalize in (normalize_daily, _normalize_daily, _normalize_minute, GenericHTTPProvider._normalize_minute):
        with pytest.raises(ValueError, match="quantity_unit_"):
            normalize(frame)
    with pytest.raises(ValueError, match="quantity_unit_"):
        validate_quantity_units({"bid_volumes": [12345], "quantity_unit": unit})
    assert frame["volume"].item() == 12345


@pytest.mark.parametrize("market", ["CN", "HK", "US"])
def test_settings_matrix_cannot_route_blocked_datasets(monkeypatch, market):
    from app.data_providers import custom
    from app.data_providers.capabilities import build_capability_matrix

    provider = LongbridgeProvider()
    monkeypatch.setattr(custom, "list_sources", lambda: [])
    monkeypatch.setattr(custom, "list_plugins", lambda: [{
        "name": "longbridge", "datasets": ["realtime"], "available": True,
        "market_capabilities": provider.market_capabilities,
    }])
    matrix = build_capability_matrix({"daily_data_provider": "longbridge"}, market=market)
    daily = next(item for item in matrix["capabilities"] if item["id"] == "daily")
    assert not daily["usable"]
    assert dataset_status(provider, "realtime", market)["status"] == "supported"
    assert provider.market_capabilities["financial"]["HK"]["reason"] == "report_period_timestamp_unit_unverified"
    assert provider.market_capabilities["financial"]["CN"]["status"] == "empty"
    assert provider.market_capabilities["financial"]["US"]["status"] == "contract_blocked"
    assert dataset_status(provider, "adj_factor", market)["status"] == "unsupported"
    assert dataset_status(provider, "full_minute", market)["status"] == "unsupported"
