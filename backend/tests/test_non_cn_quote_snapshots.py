"""港美基础快照读写及领域隔离, 不调用真实数据源。"""
from concurrent.futures import ThreadPoolExecutor

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.services.quote_service as qs_module
from app.api.intraday import router
from app.services.quote_service import QuoteService


def _record(symbol, price=10.0, **fields):
    return {"symbol": symbol, "last_price": price, "timestamp": 1000000, **fields}


def _process(qs, rows):
    return qs._process_full_market_records(rows, t0=0.0, now_ts=0.0)


@pytest.fixture
def service(monkeypatch):
    qs = QuoteService()

    def forbidden(*args, **kwargs):
        pytest.fail("non-CN 快照触发 CN 领域逻辑")

    # 缓存和读取不能靠 CN 日历、定版、写盘或 enriched 工作。
    for name in ("_flush_live_enriched", "_evaluate_monitors", "_build_daily",
                 "_update_volume_delta", "_broadcast_quote_updated", "get_enriched_today"):
        monkeypatch.setattr(qs, name, forbidden)
    for name in ("cn_today", "cn_now", "_persist_last_fetch"):
        monkeypatch.setattr(qs_module, name, forbidden)
    return qs


def test_partial_updates_preserve_other_market_and_empty_batch(service):
    _process(service, [_record("700.HK"), _record("AAPL.US")])
    _process(service, [_record("700.HK", 11.0, timestamp=1000001)])
    _process(service, [])
    rows = {r["symbol"]: r for r in service.get_non_cn_quotes()}
    assert rows["700.HK"]["last_price"] == 11.0
    assert rows["AAPL.US"]["last_price"] == 10.0
    _process(service, [_record("AAPL.US", 12.0, timestamp=1000002)])
    assert service.get_non_cn_quotes(["700.HK"])[0]["last_price"] == 11.0


def test_contract_and_age_do_not_guess_units_or_currency(service, monkeypatch):
    monkeypatch.setattr(qs_module.time, "time", lambda: 1005.0)
    _process(service, [
        _record("700.HK", volume=5000, name="腾讯", currency="HKD", change_pct=0.02),
        _record("AAPL.US", timestamp=None),
    ])
    hk, us = service.get_non_cn_quotes()
    assert hk["market"] == "HK" and hk["currency"] == "HKD"
    assert hk["volume"] is None and hk["volume_unit"] == "unsupported"
    assert hk["age_ms"] == 5000 and hk["change_pct"] == 0.02
    assert us["market"] == "US" and us["currency"] is None
    assert us["timestamp"] is None and us["age_ms"] is None
    assert us["prev_close"] is None and us["amount"] is None
    assert not {"turnover_rate", "limit_up_price", "ma5", "macd"} & hk.keys()


@pytest.mark.parametrize("bad", [
    _record("700.HK", "bad"), _record("700.HK", float("nan")),
    _record("700.HK", True), _record("700.HK", 0),
    _record("700.HK", timestamp="bad"), _record("700.HK", amount=float("inf")),
    _record("700.HK", market="US"), _record("ABC.UNKNOWN"), None,
])
def test_bad_row_cannot_clear_cache_or_block_valid_row(service, bad):
    _process(service, [_record("700.HK")])
    _process(service, [bad, _record("AAPL.US")])
    assert {r["symbol"] for r in service.get_non_cn_quotes()} == {"700.HK", "AAPL.US"}
    assert service.get_non_cn_quotes(["700.HK"])[0]["last_price"] == 10.0


def test_older_quote_does_not_replace_latest_and_reads_are_copies(service):
    row = _record("700.HK", 11.0, timestamp=1000002)
    _process(service, [row])
    row["last_price"] = 99.0
    _process(service, [_record("700.HK", 9.0, timestamp=1000001)])
    result = service.get_non_cn_quotes(["700.HK"])
    assert result[0]["last_price"] == 11.0
    result[0]["last_price"] = 88.0
    assert service.get_non_cn_quotes(["700.HK"])[0]["last_price"] == 11.0
    assert service.get_non_cn_quotes(["ABC.UNKNOWN", "600519.SH"]) == []


def test_concurrent_upserts_and_reads_retain_all_symbols(service):
    def update(i):
        symbol = f"{i}.HK" if i % 2 else f"STOCK{i}.US"
        _process(service, [_record(symbol)])
        return service.get_non_cn_quotes([symbol])[0]["symbol"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        symbols = list(pool.map(update, range(1, 41)))
    assert {r["symbol"] for r in service.get_non_cn_quotes()} == set(symbols)


def test_existing_cn_compat_is_unchanged_and_cn_is_not_cached(monkeypatch):
    qs = QuoteService()
    monkeypatch.setattr(qs, "get_enriched_today", lambda: (
        pl.DataFrame({"symbol": ["600519.SH"], "close": [10.0], "change_pct": [0.01]}), None,
    ))
    expected = qs.get_quotes_compat().to_dicts()
    app = FastAPI()
    app.include_router(router)
    app.state.quote_service = qs
    with TestClient(app) as client:
        result = client.get("/api/intraday/quotes", params={"symbols": "600519.SH"})
    assert result.status_code == 200 and result.json()["rows"] == expected
    assert qs.get_non_cn_quotes() == []


def test_api_reads_foreign_without_enriched(service):
    _process(service, [_record("700.HK"), _record("AAPL.US")])
    app = FastAPI()
    app.include_router(router)
    app.state.quote_service = service
    with TestClient(app) as client:
        response = client.get("/api/intraday/quotes", params={"symbols": "700.HK,AAPL.US"})
        assert response.status_code == 200
        assert {r["symbol"] for r in response.json()["rows"]} == {"700.HK", "AAPL.US"}
        assert client.get("/api/intraday/quotes", params={"symbols": "ABC.UNKNOWN"}).json()["rows"] == []


def test_api_without_service_returns_empty():
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        assert client.get("/api/intraday/quotes").json() == {"rows": [], "count": 0}
