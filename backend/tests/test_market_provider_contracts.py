from types import SimpleNamespace

import polars as pl
import pytest

from app.data_providers.contracts import dataset_status, validate_quantity_units


def provider(metadata=None):
    value = SimpleNamespace(config=SimpleNamespace(datasets={"daily": None}))
    if metadata is not None:
        value.market_capabilities = metadata
    return value


def test_legacy_dataset_routing_is_unchanged():
    assert dataset_status(provider(), "daily")["status"] == "supported"
    assert dataset_status(provider(), "daily", "CN")["status"] == "supported"


def test_partial_support_requires_explicit_market():
    value = provider({"daily": {
        "HK": {"status": "supported"},
        "CN": {"status": "contract_blocked", "reason": "quantity_unit_unknown"},
        "US": {"status": "unavailable", "reason": "requires_us_token_or_market_context"},
    }})
    assert dataset_status(value, "daily", "HK")["status"] == "supported"
    assert dataset_status(value, "daily")["reason"] == "market_required"
    assert dataset_status(value, "daily", "US")["status"] == "unavailable"
    assert dataset_status(value, "daily", "UNKNOWN")["status"] != "supported"


@pytest.mark.parametrize("unit,reason", [
    ("unknown", "quantity_unit_unknown"),
    (None, "quantity_unit_unknown"),
    ("shares", "quantity_unit_incompatible"),
    ("board_lots", "quantity_unit_incompatible"),
    ("contracts", "quantity_unit_incompatible"),
])
def test_explicit_unsafe_units_fail_closed(unit, reason):
    with pytest.raises(ValueError, match=reason):
        validate_quantity_units(pl.DataFrame({"volume": [1234], "quantity_unit": [unit]}))


def test_legacy_units_never_change_numeric_values():
    for data in ({"volume": [1234]}, {"volume": [1234], "quantity_unit": ["legacy_100_shares"]}):
        frame = pl.DataFrame(data)
        validate_quantity_units(frame)
        assert frame["volume"].item() == 1234


def test_minute_metadata_survives_without_changing_volume():
    from app.data_providers.custom.provider import GenericHTTPProvider

    frame = pl.DataFrame({"symbol": ["600519.SH"], "volume": [1234],
        "market": ["CN"], "timezone": ["Asia/Shanghai"], "currency": ["CNY"],
        "quantity_unit": ["legacy_100_shares"]})
    result = GenericHTTPProvider._normalize_minute(frame)
    assert result.to_dicts() == frame.with_columns(pl.col("volume").cast(pl.Float64)).to_dicts()


def test_matrix_partial_source_requires_market(monkeypatch):
    from app.data_providers import custom
    from app.data_providers.capabilities import build_capability_matrix

    monkeypatch.setattr(custom, "list_sources", lambda: [])
    monkeypatch.setattr(custom, "list_plugins", lambda: [{
        "name": "partial", "datasets": ["daily"], "available": True,
        "market_capabilities": {"daily": {"HK": {"status": "supported"}}},
    }])
    current = {"daily_data_provider": "partial"}
    def daily(market):
        return next(item for item in build_capability_matrix(current, market=market)["capabilities"] if item["id"] == "daily")
    assert not daily(None)["usable"]
    assert daily("HK")["usable"]
