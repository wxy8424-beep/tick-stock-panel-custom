"""Read-only family metadata must not alter legacy consumers or computation."""
import json
from dataclasses import FrozenInstanceError

import pytest

from app.factors.engine import DEFAULT_FACTORS, FactorRequest, MarketFactorEngine
from app.factors.registry import engine_factors, factor_columns_view, get_engine_factor


@pytest.mark.parametrize("name", ["ma", "ema", "macd", "rsi", "atr", "roc", "volatility"])
def test_family_lookup_and_serialization(name):
    spec = get_engine_factor(name.upper())
    assert spec is not None
    assert spec.name == name
    assert spec.category and spec.description
    assert spec.version == 1
    assert spec.supported_modes == ("research", "backtest_compat")
    payload = spec.to_dict()
    assert json.loads(json.dumps(payload)) == payload
    assert {parameter["name"] for parameter in payload["parameters"]} == (
        {"compatibility_backend"} if name == "macd" else {"period", "compatibility_backend"}
    )
    assert all(parameter["default"] is None for parameter in payload["parameters"])


@pytest.mark.parametrize("name", ["unknown", "ma20", "", None, 42])
def test_unknown_family_is_explicit(name):
    assert get_engine_factor(name) is None


def test_registry_is_read_only_and_serialization_is_detached():
    spec = get_engine_factor("ma")
    with pytest.raises(FrozenInstanceError):
        spec.name = "changed"
    with pytest.raises(FrozenInstanceError):
        spec.parameters[0].name = "changed"
    payload = spec.to_dict()
    payload["parameters"][0]["name"] = "changed"
    payload["supported_modes"].clear()
    assert spec.to_dict()["parameters"][0]["name"] == "period"
    assert get_engine_factor("ma").supported_modes == ("research", "backtest_compat")


def test_reading_metadata_does_not_compute_or_mutate_catalog(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("registry must not execute calculations")

    before = factor_columns_view()
    monkeypatch.setattr(MarketFactorEngine, "compute", forbidden)
    monkeypatch.setattr(FactorRequest, "definition", forbidden)
    assert tuple(spec.name for spec in engine_factors()) == tuple(
        request.kind for request in DEFAULT_FACTORS
    )
    assert factor_columns_view() == before
