"""实时入口的市场隔离行为; 不依赖行情权限或网络。"""
from datetime import UTC, date, datetime, time
from types import SimpleNamespace

import polars as pl
import pytest

import app.services.quote_service as qs_module
from app.market_time import CN_TZ
from app.services.quote_service import QuoteService
from app.tickflow.repository import DataStore, KlineRepository

DAY = date(2026, 9, 16)


def _record(symbol, timestamp=None, **metadata):
    return {
        "symbol": symbol, "last_price": 10.1, "prev_close": 10.0,
        "open": 10.0, "high": 10.2, "low": 9.9,
        "volume": 1000.0, "amount": 101000.0,
        "timestamp": timestamp or _boundary(), **metadata,
    }


def _boundary():
    return int(datetime.combine(DAY, time(15), tzinfo=CN_TZ).timestamp() * 1000)


@pytest.fixture
def service(tmp_path, monkeypatch):
    repo = KlineRepository(DataStore(tmp_path))
    qs = QuoteService()
    qs._repo = repo
    events = {"enriched": [], "monitors": [], "volume": [], "broadcast": []}
    monkeypatch.setattr(qs_module, "cn_today", lambda: DAY)
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
    daily_path = repo.store.data_dir / "kline_daily" / f"date={DAY}" / "part.parquet"
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


@pytest.mark.parametrize("currency", ["USD", "HKD", "UNKNOWN", "", [], {}, True, 123])
def test_explicit_incompatible_cn_currency_cannot_write_or_confirm(
    service, monkeypatch, caplog, currency,
):
    qs, repo, events = service
    with caplog.at_level("WARNING", logger=qs_module.__name__):
        assert _fetch(service, monkeypatch, [
            _record("600519.SH", market="CN", currency=currency),
        ], final=True) is False
    assert qs._last_final_confirmed is False
    assert qs._fetched_at == 0
    assert events == {"enriched": [], "monitors": [], "volume": [], "broadcast": []}
    assert not list(repo.store.data_dir.glob("kline*_daily/date=*/*.parquet"))
    assert "currency" in caplog.text


def test_conflicting_currency_timestamp_cannot_confirm_other_stale_cn(service, monkeypatch):
    qs, repo, events = service
    assert _fetch(service, monkeypatch, [
        _record("000001.SZ", _boundary() - 60_000),
        _record("600519.SH", _boundary() + 60_000, currency="USD"),
    ], final=True) is True  # CN display freshness updates; final confirmation does not.
    assert qs._last_final_confirmed is False
    assert not list(repo.store.data_dir.glob("kline*_daily/date=*/*.parquet"))
    assert events["enriched"] == events["monitors"] == events["volume"] == []


@pytest.mark.parametrize("currency", [None, "CNY", " cny "])
def test_compatible_or_legacy_cn_currency_preserves_values(service, monkeypatch, currency):
    qs, repo, events = service
    cn = _record("600519.SH", currency=currency)
    expected = qs._build_daily([cn])
    assert _fetch(service, monkeypatch, [cn, _record("700.HK", currency="HKD"),
                                        _record("AAPL.US", currency="USD")], final=True)
    actual = pl.read_parquet(repo.store.data_dir / "kline_daily" / f"date={DAY}" / "part.parquet")
    assert actual.equals(expected)
    assert events["monitors"][0].equals(expected)
    assert qs._last_final_confirmed is True
    assert {r["market"] for r in qs.get_non_cn_quotes()} == {"HK", "US"}


def test_tickflow_adapter_preserves_identity_metadata_before_guard(service, monkeypatch):
    from app.services import preferences
    from app.tickflow import client

    qs, _, events = service
    row = _record("600519.SH", market="CN", currency="USD", timezone="UTC")
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "tickflow")
    monkeypatch.setattr(preferences, "get_realtime_pull_stock", lambda: True)
    monkeypatch.setattr(preferences, "get_realtime_pull_etf", lambda: False)
    fake = SimpleNamespace(quotes=SimpleNamespace(
        get_by_universes=lambda **kwargs: [row], get=lambda **kwargs: [],
    ))
    monkeypatch.setattr(client, "get_paid_realtime_client", lambda: fake)
    archived = []
    monkeypatch.setattr(qs, "_archive_records", lambda rows, provider: archived.extend(rows))
    assert qs._fetch_quotes(final=True, final_boundary_ms=_boundary()) is False
    assert archived[0]["currency"] == "USD"
    assert archived[0]["timezone"] == "UTC"
    assert qs._last_final_confirmed is False
    assert events["enriched"] == events["monitors"] == events["volume"] == []


def test_duplicate_cn_rows_keep_existing_semantics_and_foreign_does_not_add_rows(service, monkeypatch):
    qs, repo, events = service
    cn = [_record("600519.SH"), _record("600519.SH")]
    expected = qs._build_daily(cn)
    assert _fetch(service, monkeypatch, [*cn, _record("AAPL.US"), _record("AAPL.US")])
    actual = pl.read_parquet(repo.store.data_dir / "kline_daily" / f"date={DAY}" / "part.parquet")
    assert actual.equals(expected)  # No new deduplication or winner selection in this change.
    assert events["monitors"][0].equals(expected)
    assert len(qs.get_non_cn_quotes()) == 1


def test_cn_date_uses_beijing_day_and_foreign_midnight_cannot_supply_cn_bar(service, monkeypatch):
    qs, repo, events = service
    # 16:00 UTC is the next Beijing day. Keep the original CN date filter.
    old = int(datetime(2026, 9, 15, 15, 59, tzinfo=UTC).timestamp() * 1000)
    current = int(datetime(2026, 9, 15, 16, 0, tzinfo=UTC).timestamp() * 1000)
    future = int(datetime(2026, 9, 16, 16, 0, tzinfo=UTC).timestamp() * 1000)
    rows = [_record("600519.SH", old), _record("000001.SZ", current),
            _record("430047.BJ", future), _record("AAPL.US", future)]
    assert _fetch(service, monkeypatch, rows)
    actual = pl.read_parquet(repo.store.data_dir / "kline_daily" / f"date={DAY}" / "part.parquet")
    assert actual["symbol"].to_list() == ["000001.SZ"]
    assert actual["date"].to_list() == [DAY]
    assert events["monitors"][0].equals(actual)
    assert qs.get_non_cn_quotes()[0]["symbol"] == "AAPL.US"


def test_archive_remains_independent_market_history_in_temporary_sqlite(tmp_path):
    from app.services.snapshot_archive import SnapshotArchive

    archive = SnapshotArchive(tmp_path)
    rows = [_record("600519.SH", currency="CNY"), _record("700.HK", currency="HKD"),
            _record("AAPL.US", currency="USD"), _record("ABC.UNKNOWN")]
    received = datetime.combine(DAY, time(15, 1), tzinfo=CN_TZ).astimezone(UTC)
    assert archive.append(rows, received, "fixture-provider") == 3
    for market, symbol in [("CN", "600519.SH"), ("HK", "700.HK"), ("US", "AAPL.US")]:
        assert [r["symbol"] for r in archive.query(market=market)] == [symbol]
    assert archive.path.is_relative_to(tmp_path)
