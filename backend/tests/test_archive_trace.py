"""Trace fixtures only: isolated SQLite, mocked SDK, no production requests/data."""
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.plugins.longbridge.provider import LongbridgeProvider
from app.services import archive_trace as tr
from app.services.quote_service import QuoteService
from app.services.snapshot_archive import SnapshotWriter

NOW = datetime(2026, 10, 14, 14, tzinfo=UTC)
SYMBOLS = ("000001.SH", ".SPX.US", "AAPL.US", "700.HK")


def quote(symbol, **changes):
    return SimpleNamespace(**{**dict(symbol=symbol, last_done=100, prev_close=99, open=99,
                                    high=101, low=98, turnover=1000, timestamp=NOW), **changes})


def provider(monkeypatch, response=None):
    instance = LongbridgeProvider(clock=lambda: NOW)
    calls = []

    def pull(symbols):
        calls.append(list(symbols))
        if isinstance(response, Exception):
            raise response
        return [quote(s) for s in symbols] if response is None else response

    instance._context = SimpleNamespace(quote=pull, static_info=lambda symbols: [])
    monkeypatch.setattr(instance, "_refresh_market_state", lambda: None)
    return instance, calls


@pytest.fixture
def observed(monkeypatch):
    records = []
    observer = tr.TraceObserver(SYMBOLS, sink=records.append)
    monkeypatch.setattr(tr, "_observer", observer)
    yield observer, records
    observer.close()


def drain(observed):
    observer, records = observed
    observer._queue.join()
    return records


@pytest.mark.parametrize("symbol", SYMBOLS)
def test_request_through_committed_sqlite_lifecycle(tmp_path, monkeypatch, observed, symbol):
    p, calls = provider(monkeypatch)
    with tr.trace_origin("quote_service_poll"):
        rows = p.get_realtime([symbol])
    before = dict(rows[0])
    service = QuoteService()
    service.set_repo(SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path)))
    service._archive_records(rows, "longbridge")
    service._snapshot_writer.close()
    records = drain(observed)
    assert calls == [[symbol]]  # Trace never requests an extra symbol.
    assert rows[0] == before and "trace_id" not in rows[0]
    assert len({r["trace_id"] for r in records}) == 1
    assert len({r["request_id"] for r in records}) == 1
    assert [r["stage_sequence"] for r in records] == list(range(1, len(records) + 1))
    assert all(r["origin"] == "quote_service_poll" for r in records)
    status = tr.stage_status(records, records[0]["trace_id"])
    assert all(status[stage] == "PASS" for stage in tr.STAGES[:-1])
    assert status["REJECTED"] == "UNKNOWN"
    stored = service._snapshot_writer.archive.query()
    assert len(stored) == 1 and stored[0]["symbol"] == symbol
    assert stored[0]["provider"] == "longbridge" and stored[0]["volume"] is None
    assert "trace_id" not in stored[0]
    persisted = records[-1]
    assert persisted["stage"] == "PERSISTED"
    assert persisted["persistence_reference"] == {"ordinal": 0, "committed_count": 1}
    assert persisted["writer_batch_id"] == records[-2]["writer_batch_id"]


def test_per_request_per_symbol_identity(monkeypatch, observed):
    p, _ = provider(monkeypatch)
    p.get_realtime(["AAPL.US", ".SPX.US"])
    p.get_realtime(["AAPL.US"])
    requested = [r for r in drain(observed) if r["stage"] == "REQUESTED"]
    assert len({r["trace_id"] for r in requested}) == 3
    assert requested[0]["request_id"] == requested[1]["request_id"]
    assert requested[0]["request_id"] != requested[2]["request_id"]


def test_dashboard_preserves_bypass_and_missing_stage_unknown(tmp_path, monkeypatch, observed):
    p, calls = provider(monkeypatch)
    result = p.dashboard_request("quote", "quote", [".SPX.US"])
    assert result[0].symbol == ".SPX.US" and calls == [[".SPX.US"]]
    records = drain(observed)
    assert [r["stage"] for r in records] == ["REQUESTED", "PROVIDER_RECEIVED"]
    assert records[0]["origin"] == "dashboard_quote"
    assert tr.stage_status(records, records[0]["trace_id"])["WRITER_ATTEMPTED"] == "UNKNOWN"
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("response,reason", [
    (RuntimeError("SENSITIVE_SENTINEL"), "request_failed_unclassified"),
    ({"SENSITIVE_SENTINEL": True}, "response_shape_invalid"),
    ([], "response_symbol_missing"),
    ([quote("AAPL.US", last_done=-1)], "normalization_failed"),
])
def test_provider_reject_reason_and_safe_fields(monkeypatch, observed, caplog, response, reason):
    p, _ = provider(monkeypatch, response)
    assert p.get_realtime(["AAPL.US"]) == []
    records = drain(observed)
    assert any(r["stage"] == "REJECTED" and r["reason_code"] == reason for r in records)
    assert "SENSITIVE_SENTINEL" not in json.dumps(records) + caplog.text
    assert all("last_price" not in r and "response" not in r for r in records)


@pytest.mark.parametrize("reason", ["queue_full", "writer_closed_or_batch_limit", "prepare_failed"])
def test_writer_known_rejection_does_not_change_outcome(tmp_path, monkeypatch, observed, reason):
    p, _ = provider(monkeypatch)
    rows = p.get_realtime(["AAPL.US"])
    writer = SnapshotWriter(tmp_path)
    if reason == "queue_full":
        monkeypatch.setattr(writer._queue, "full", lambda: True)
    elif reason == "writer_closed_or_batch_limit":
        writer.close()
    else:
        def fail(*args):
            raise ValueError("SENSITIVE_SENTINEL")
        monkeypatch.setattr(writer.archive, "prepare", fail)
    if reason == "prepare_failed":
        with pytest.raises(ValueError, match="SENSITIVE_SENTINEL"):
            writer.submit(rows, NOW, "longbridge")
    else:
        assert writer.submit(rows, NOW, "longbridge") is False
    writer.close()
    records = drain(observed)
    assert records[-1]["stage"] == "REJECTED" and records[-1]["reason_code"] == reason
    assert "SENSITIVE_SENTINEL" not in json.dumps(records)
    assert not writer.archive.path.exists()


def test_queue_race_rejection(tmp_path, monkeypatch, observed):
    p, _ = provider(monkeypatch)
    rows = p.get_realtime(["AAPL.US"])
    writer = SnapshotWriter(tmp_path)

    def full(*args):
        raise tr.queue.Full

    monkeypatch.setattr(writer._queue, "put_nowait", full)
    assert not writer.submit(rows, NOW, "longbridge")
    assert drain(observed)[-1]["reason_code"] == "queue_full"
    writer.close()


def test_filtered_item_not_misattributed_by_position(tmp_path, monkeypatch, observed):
    p, _ = provider(monkeypatch)
    rows = p.get_realtime([".SPX.US", "AAPL.US"])
    rows[0]["symbol"] = "invalid"  # Isolated fixture exercises the existing prepare skip.
    writer = SnapshotWriter(tmp_path)
    writer.submit(rows, NOW, "longbridge")
    writer.close()
    records = drain(observed)
    persisted = [r for r in records if r["stage"] == "PERSISTED"]
    assert len(persisted) == 1 and persisted[0]["symbol"] == "AAPL.US"
    assert persisted[0]["persistence_reference"]["ordinal"] == 0
    assert any(r["symbol"] == ".SPX.US" and r["reason_code"] == "archive_symbol_invalid" for r in records)


def test_write_error_does_not_claim_no_commit_or_persist(tmp_path, monkeypatch, observed):
    p, _ = provider(monkeypatch)
    rows = p.get_realtime(["AAPL.US"])
    writer = SnapshotWriter(tmp_path)

    def fail(*args):
        raise RuntimeError("SENSITIVE_SENTINEL")

    monkeypatch.setattr(writer.archive, "_write", fail)
    assert writer.submit(rows, NOW, "longbridge")
    writer.close()
    records = drain(observed)
    assert tr.stage_status(records, records[0]["trace_id"])["PERSISTED"] == "UNKNOWN"
    assert not any(r["stage"] == "REJECTED" for r in records)


def test_persist_only_after_write_returns(tmp_path, monkeypatch, observed):
    p, _ = provider(monkeypatch)
    writer = SnapshotWriter(tmp_path)
    original = writer.archive._write

    def write(batch):
        assert not any(r["stage"] == "PERSISTED" for r in drain(observed))
        result = original(batch)
        assert writer.archive.query()[0]["symbol"] == "AAPL.US"
        return result

    monkeypatch.setattr(writer.archive, "_write", write)
    writer.submit(p.get_realtime(["AAPL.US"]), NOW, "longbridge")
    writer.close()
    assert drain(observed)[-1]["stage"] == "PERSISTED"


def test_disabled_or_nonmember_preserves_plain_list(monkeypatch, observed):
    p, _ = provider(monkeypatch)
    assert type(p.get_realtime(["NVDA.US"])) is list
    assert not drain(observed)
    disabled = tr.TraceObserver()
    monkeypatch.setattr(tr, "_observer", disabled)
    assert type(p.get_realtime(["AAPL.US"])) is list
    assert not drain(observed)
    disabled.close()


def test_no_archive_dependency_is_explicit_not_persisted(monkeypatch, observed):
    p, _ = provider(monkeypatch)
    QuoteService()._archive_records(p.get_realtime(["AAPL.US"]), "longbridge")
    assert drain(observed)[-1]["reason_code"] == "archive_dependency_missing"


def test_diagnostic_sink_failure_isolated(tmp_path, monkeypatch):
    def fail(record):
        raise RuntimeError("SENSITIVE_SENTINEL")
    observer = tr.TraceObserver(["AAPL.US"], sink=fail)
    monkeypatch.setattr(tr, "_observer", observer)
    p, calls = provider(monkeypatch)
    writer = SnapshotWriter(tmp_path)
    try:
        assert writer.submit(p.get_realtime(["AAPL.US"]), NOW, "longbridge")
        writer.close()
        assert writer.archive.query()[0]["symbol"] == "AAPL.US"
        assert calls == [["AAPL.US"]]
    finally:
        observer.close()
    assert observer.dropped > 0


def test_diagnostic_queue_full_never_changes_business_result(tmp_path, monkeypatch, observed):
    def full(record):
        raise tr.queue.Full
    monkeypatch.setattr(observed[0]._queue, "put_nowait", full)
    p, _ = provider(monkeypatch)
    writer = SnapshotWriter(tmp_path)
    assert writer.submit(p.get_realtime(["AAPL.US"]), NOW, "longbridge")
    writer.close()
    assert writer.archive.query()[0]["symbol"] == "AAPL.US"
    assert not drain(observed) and observed[0].dropped > 0


def test_scope_rejects_wildcard_and_sensitive_string():
    observer = tr.TraceObserver(["*", "", "secret=SECRET_VALUE", "AAPL.US"])
    try:
        assert observer.symbols == {"AAPL.US"}
    finally:
        observer.close()


def test_natural_poll_origin_and_no_extra_request(tmp_path, monkeypatch, observed):
    from app.data_providers import custom
    from app.services import preferences

    p, calls = provider(monkeypatch)
    monkeypatch.setattr(p, "configured_symbols", lambda: ["AAPL.US"])
    monkeypatch.setattr(preferences, "get_realtime_data_provider", lambda: "longbridge")
    monkeypatch.setattr(custom, "provider_has_dataset", lambda *args: True)
    monkeypatch.setattr(custom, "get_provider", lambda name: p)
    service = QuoteService()
    service.set_repo(SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path)))
    monkeypatch.setattr(service, "_should_poll_for_market", lambda market: market == "US")
    assert service._poll_non_cn_quotes()
    service._snapshot_writer.close()
    records = drain(observed)
    assert calls == [["AAPL.US"]]
    assert records[-1]["stage"] == "PERSISTED"
    assert all(r["origin"] == "quote_service_poll" for r in records)


def test_default_log_sink_never_serializes_payload(monkeypatch, caplog):
    caplog.set_level("INFO", logger="app.services.archive_trace")
    observer = tr.TraceObserver(["AAPL.US"])
    monkeypatch.setattr(tr, "_observer", observer)
    p, _ = provider(monkeypatch, [quote("AAPL.US", extra="SENSITIVE_SENTINEL")])
    try:
        p.get_realtime(["AAPL.US"])
    finally:
        observer.close()
    assert "archive_trace" in caplog.text and "PROVIDER_RECEIVED" in caplog.text
    assert "SENSITIVE_SENTINEL" not in caplog.text
    assert "last_done" not in caplog.text


def test_trace_enabled_does_not_change_prepared_business_values(monkeypatch, observed):
    from app.services.snapshot_archive import SnapshotArchive

    p, _ = provider(monkeypatch, [quote("AAPL.US", timestamp=NOW.replace(year=2025))])
    rows = p.get_realtime(["AAPL.US"])
    traced = SnapshotArchive.prepare(rows, NOW, "longbridge")
    plain = SnapshotArchive.prepare(list(rows), NOW, "longbridge")
    assert traced == plain
    assert len(traced) == 1  # Existing stale/quality behavior is untouched.
    assert rows[0]["volume"] is None
