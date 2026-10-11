"""Deterministic top-N research portfolios and isolated local persistence."""
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta

import polars as pl
import pytest

from app.factors.research_scoring import FactorScoringEngine, ScoringFactor
from app.services.research_portfolios import PortfolioBuilder, PortfolioDefinition, PortfolioStore

SYMBOLS = ("AAPL.US", "NVDA.US", "SPY.US")


def definition(**changes):
    fields = dict(portfolio_id="study-1", name="等权研究", symbols=SYMBOLS,
                  selection={"top_n": 2}, created_at=datetime(2026, 1, 1, tzinfo=UTC))
    return PortfolioDefinition(**(fields | changes))


def scores(values=(0.5, 0.9, 0.9)):
    return {"as_of": "2026-03-21", "history_start": "2026-01-01", "method": "rank",
            "mode": "research", "price_basis": "as_provided", "aggregation": "equal_weight_complete_case",
            "factors": [{"output_column": "ma5", "direction": "high", "weight": 1, "period": 5}],
            "rows": [{"symbol": symbol, "status": "scored" if value is not None else "unavailable",
                      "total_score": value, "factors": {"ma5": {"value": 10.0 if value is not None else None,
                                                                "score": value}}}
                     for symbol, value in zip(SYMBOLS, values, strict=True)]}


def test_top_n_ties_weights_summary_and_determinism():
    source = scores()
    before = deepcopy(source)
    result = PortfolioBuilder().build(definition(), source)
    assert result["selected_symbols"] == ["NVDA.US", "SPY.US"]
    assert result["weights"] == {"NVDA.US": 0.5, "SPY.US": 0.5}
    assert sum(result["weights"].values()) == pytest.approx(1)
    assert result["score_summary"]["mean_total_score"] == pytest.approx(0.9)
    assert result["score_summary"]["factors"]["ma5"]["mean_value"] == 10
    assert result["excluded"] == [{"symbol": "AAPL.US", "reason": "outside_top_n"}]
    assert PortfolioBuilder().build(definition(), source) == result
    source["rows"].reverse()
    assert PortfolioBuilder().build(definition(), source)["selected_symbols"] == result["selected_symbols"]
    assert before["rows"][0]["symbol"] == "AAPL.US"


@pytest.mark.parametrize("top_n,expected", [(1, 1), (2, 2), (10, 3)])
def test_top_n_uses_actual_selected_count(top_n, expected):
    result = PortfolioBuilder().build(definition(selection={"top_n": top_n}), scores())
    assert len(result["selected_symbols"]) == expected
    assert all(weight == pytest.approx(1 / expected) for weight in result["weights"].values())


def test_missing_and_unavailable_scores_are_excluded():
    source = scores((0.5, None, None))
    source["rows"].pop()
    result = PortfolioBuilder().build(definition(), source)
    assert result["selected_symbols"] == ["AAPL.US"]
    assert result["weights"] == {"AAPL.US": 1}
    assert result["excluded"] == [{"symbol": "NVDA.US", "reason": "unavailable_score"},
                                   {"symbol": "SPY.US", "reason": "missing_score"}]
    assert "score_universe_differs_from_portfolio" in result["warnings"]


@pytest.mark.parametrize("symbols", [SYMBOLS, ()])
def test_empty_portfolio_is_explicit(symbols):
    result = PortfolioBuilder().build(definition(symbols=symbols), scores((None, None, None)))
    assert result["status"] == "empty"
    assert result["weights"] == {}
    assert result["selected_symbols"] == []
    assert result["score_summary"]["mean_total_score"] is None
    assert result["score_summary"]["factors"]["ma5"]["mean_score"] is None


def test_source_superset_is_not_rescored():
    result = PortfolioBuilder().build(definition(symbols=("AAPL.US",)), scores())
    assert result["selected_symbols"] == ["AAPL.US"]
    assert result["source_scores"]["rows"][0]["total_score"] == 0.5
    assert "score_universe_differs_from_portfolio" in result["warnings"]


def test_atomic_definition_result_save_and_read_only_queries(tmp_path):
    store, spec = PortfolioStore(tmp_path), definition()
    assert store.get_definition("missing") is None
    assert store.get_results("missing") == []
    assert not store.path.exists()
    result = store.save(spec, scores())
    assert store.get_definition(spec.portfolio_id) == spec
    assert store.get_results(spec.portfolio_id) == [result]
    result["weights"].clear()
    assert store.get_results(spec.portfolio_id)[0]["weights"]
    store.save(spec, scores((0.9, 0.5, 0.1)))
    assert len(store.get_results(spec.portfolio_id)) == 2
    assert store.get_results(spec.portfolio_id, limit=1)[0]["selected_symbols"] == ["AAPL.US", "NVDA.US"]
    with pytest.raises(ValueError, match="cannot be overwritten"):
        store.save(definition(name="replacement"), scores())
    assert store.get_definition(spec.portfolio_id).name == spec.name
    assert len(store.get_results(spec.portfolio_id)) == 2


def test_invalid_scores_fail_before_storage_and_arbitrary_fields_not_saved(tmp_path):
    store = PortfolioStore(tmp_path)
    source = scores()
    source["rows"][0]["total_score"] = float("nan")
    with pytest.raises(ValueError):
        store.save(definition(), source)
    assert not store.path.exists()
    source = scores()
    source["access_token"] = "dummy-not-for-storage"
    source["rows"][0]["debug_payload"] = "dummy-not-for-storage"
    result = store.save(definition(), source)
    assert "dummy-not-for-storage" not in str(result)
    assert "dummy-not-for-storage" not in str(store.get_results("study-1"))


@pytest.mark.parametrize("change", [
    {"selection": {"top_n": 0}}, {"selection": {"top_n": True}},
    {"selection": {"top_n": 2, "weighting": "optimized"}},
    {"symbols": ("AAPL.US", "AAPL.US")}, {"symbols": ("ABC.UNKNOWN",)},
    {"created_at": "2026-01-01T00:00:00"},
])
def test_invalid_definition(change):
    with pytest.raises(ValueError):
        definition(**change)


@pytest.mark.parametrize("value", [float("inf"), float("nan"), -0.1, 1.1, True])
def test_invalid_total_score_rejected(value):
    source = scores()
    source["rows"][0]["total_score"] = value
    with pytest.raises(ValueError):
        PortfolioBuilder().build(definition(), source)


def test_duplicate_or_inconsistent_score_rows_rejected():
    source = scores()
    source["rows"].append(source["rows"][0])
    with pytest.raises(ValueError):
        PortfolioBuilder().build(definition(), source)
    source = scores()
    source["rows"][0]["factors"]["ma5"]["score"] = 0.1
    with pytest.raises(ValueError):
        PortfolioBuilder().build(definition(), source)


def test_real_scoring_engine_output_is_consumed_without_changes():
    class History:
        def get_daily_asset(self, asset_type, symbol, start, end, columns=None):
            offset = SYMBOLS.index(symbol) * 10
            return pl.DataFrame({"symbol": [symbol] * 20,
                                 "date": [date(2026, 1, 1) + timedelta(days=i) for i in range(20)],
                                 "close": [float(10 + i + offset) for i in range(20)]})

    source = FactorScoringEngine().score(History(), SYMBOLS, (ScoringFactor("ma", 5),),
                                         as_of=date(2026, 1, 20), history_start=date(2026, 1, 1))
    before = deepcopy(source)
    result = PortfolioBuilder().build(definition(), source)
    assert result["selected_symbols"] == ["SPY.US", "NVDA.US"]
    assert result["source_scores"]["as_of"] == "2026-01-20"
    assert source == before


def test_cross_market_warning_and_bad_query_limit(tmp_path):
    source = scores()
    source["rows"][0]["symbol"] = "700.HK"
    spec = definition(symbols=("700.HK", "NVDA.US", "SPY.US"))
    assert "cross_market_no_currency_adjustment" in PortfolioBuilder().build(spec, source)["warnings"]
    for limit in (0, 101, True):
        with pytest.raises(ValueError):
            PortfolioStore(tmp_path).get_results("missing", limit=limit)
