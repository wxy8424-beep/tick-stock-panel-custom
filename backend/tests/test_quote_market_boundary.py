"""实时入口的市场隔离行为; 不依赖行情权限或网络。"""
from datetime import datetime, time

import polars as pl
import pytest

import app.services.quote_service as qs_module
from app.market_time import CN_TZ, cn_today
from app.services.quote_service import QuoteService
from app.tickflow.repository import DataStore, KlineRepository


def _record(symbol, timestamp=None, **metadata):
    return {
        "symbol": symbol, "last_price": 10.1, "prev_close": 10.0,
        "open": 10.0, "high": 10.2, "low": 9.9,
        "volume": 1000.0, "amount": 101000.0,
        "timestamp": timestamp or _boundary(), **metadata,
    }


def _boundary():
    return int(datetime.combine(cn_today(), time(15), tzinfo=CN_TZ).timestamp() * 1000)


@pytest.fixture
def service(tmp_path, monkeypatch):
    repo = KlineRepository(DataStore(tmp_path))
    qs = QuoteService()
    qs._repo = repo
    events = {"enriched": [], "monitors": [], "volume": [], "broadcast": []}
    monkeypatch.setattr(qs_module, "_persist_last_fetch", lambda ms: None)
    monkeypatch.setattr(qs, "_cleanup_day_scoped_state", lambda: None)
    monkeypatch.setattr(qs, "_update_volume_delta", lambda rows, ts: events["volume"].extend(rows))
    monkeypatch.setattr(qs, "_broadcast_quote_updated", lambda: events["broadcast"].append(True))

    def enriched(df, extra=None, asset_type="stock", merge=False):
        events["enriched"].append((asset_type, sorted(df["symbol"].to_list()), merge))
        if merge:
            repo.merge_live_enriched_asset(asset_type, df)
        else:
            repo.flush_live_enriched_asset(asset_type, df)

    monkeypatch.setattr(qs, "_flush_live_enriched", enriched)
    monkeypatch.setattr(qs, "_evaluate_monitors", lambda df, extra: events["monitors"].append(df))
    return qs, repo, events


def _fetch(service, monkeypatch, rows, final=False):
    qs, _, _ = service
    monkeypatch.setattr(
        qs, "_fetch_full_market_quotes",
        lambda final_boundary_ms=None: qs._process_full_market_records(
            rows, t0=0.0, now_ts=0.0, final_boundary_ms=final_boundary_ms,
        ),
    )
    return qs._fetch_quotes(final=final, final_boundary_ms=_boundary() if final else None)


@pytest.mark.parametrize("symbol", ["700.HK", "AAPL.US", "ABC.UNKNOWN", "ABC.SH", "12345.SZ", None])
@pytest.mark.parametrize("final", [False, True])
def test_non_cn_only_preserves_cn_state(service, monkeypatch, caplog, symbol, final):
    qs, repo, events = service
    seed = QuoteService._build_daily([_record("600519.SH")])
    repo.flush_live_daily(seed)
    repo.flush_live_enriched(seed)
    qs._fetched_at = 123.0
    qs._last_final_confirmed = True  # 上一轮成功不能让本轮非 CN 快照冒充成功。
    qs._index_quotes_cache = pl.DataFrame({"symbol": ["000001.SH"]})
    daily_path = repo.store.data_dir / "kline_daily" / f"date={cn_today()}" / "part.parquet"
    before = daily_path.read_bytes()

    with caplog.at_level("DEBUG", logger=qs_module.__name__):
        assert _fetch(service, monkeypatch, [_record(symbol)], final) is False

    assert daily_path.read_bytes() == before
    assert repo.get_enriched_latest()[0]["symbol"].to_list() == ["600519.SH"]
    assert qs._index_quotes_cache["symbol"].to_list() == ["000001.SH"]
    assert qs._fetched_at == 123.0
    assert events == {"enriched": [], "monitors": [], "volume": [], "broadcast": []}
    if final:
        assert qs._last_final_confirmed is False
    assert caplog.records


@pytest.mark.parametrize("foreign", [[], [_record("700.HK"), _record("AAPL.US")]])
def test_cn_stock_etf_index_keep_existing_paths(service, monkeypatch, foreign):
    qs, repo, events = service
    monkeypatch.setattr(repo, "get_etf_instruments", lambda: pl.DataFrame({"symbol": ["510300.SH"]}))
    cn = [_record("600519.SH", market="CN", exchange="SH"), _record("430047.BJ"),
          _record("000001.SZ"), _record("510300.SH"), _record("000001.SH")]
    assert _fetch(service, monkeypatch, cn + foreign, final=True) is True
    assert qs._last_final_confirmed is True
    stocks = {"600519.SH", "430047.BJ", "000001.SZ"}
    assert set(repo.get_enriched_latest()[0]["symbol"]) == stocks
    assert repo.get_enriched_latest_asset("etf")[0]["symbol"].to_list() == ["510300.SH"]
    assert repo.get_enriched_latest_asset("index")[0]["symbol"].to_list() == ["000001.SH"]
    assert qs.get_index_quotes()["symbol"].to_list() == ["000001.SH"]
    assert len(events["monitors"]) == 1
    assert set(events["monitors"][0]["symbol"]) == stocks
    assert {row["symbol"] for row in events["volume"]} == stocks
    assert sorted(events["enriched"]) == [
        ("etf", ["510300.SH"], False), ("index", ["000001.SH"], True),
        ("stock", sorted(stocks), False),
    ]
    for path in repo.store.data_dir.glob("kline*_daily/date=*/part.parquet"):
        assert not set(pl.read_parquet(path)["symbol"]) & {"700.HK", "AAPL.US"}


@pytest.mark.parametrize("symbol", ["700.HK", "AAPL.US", "ABC.UNKNOWN"])
def test_foreign_timestamp_cannot_confirm_stale_cn(service, monkeypatch, symbol):
    qs, repo, events = service
    rows = [_record("600519.SH", _boundary() - 60000), _record(symbol, _boundary() + 60000)]
    _fetch(service, monkeypatch, rows, final=True)
    assert qs._last_final_confirmed is False
    assert not list((repo.store.data_dir / "kline_daily").rglob("*.parquet"))
    assert events["enriched"] == events["monitors"] == events["volume"] == []


@pytest.mark.parametrize("metadata", [
    {"market": "HK"}, {"market": "US"}, {"market": "UNKNOWN"},
    {"market": []}, {"region": "US"}, {"exchange": "SZ"},
])
def test_conflicting_cn_metadata_fails_closed(service, monkeypatch, caplog, metadata):
    qs, _, events = service
    with caplog.at_level("WARNING", logger=qs_module.__name__):
        assert _fetch(service, monkeypatch, [_record("600519.SH", **metadata)], final=True) is False
    assert qs._last_final_confirmed is False
    assert events["enriched"] == events["monitors"] == []
    assert "市场" in caplog.text


def test_rejected_record_does_not_abort_valid_cn_batch(service, monkeypatch):
    _, repo, events = service
    rows = [None, {"symbol": []}, _record("600519.SH", market="US"), _record("000001.SZ")]
    assert _fetch(service, monkeypatch, rows) is True
    assert repo.get_enriched_latest()[0]["symbol"].to_list() == ["000001.SZ"]
    assert events["monitors"][0]["symbol"].to_list() == ["000001.SZ"]
