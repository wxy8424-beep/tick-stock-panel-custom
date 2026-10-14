"""Opt-in, bounded diagnostics. Never a quote router or archive eligibility gate."""
from __future__ import annotations

import atexit
import itertools
import json
import logging
import os
import queue
import re
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from uuid import uuid4

from app.market_session import market_from_symbol

STAGES = ("REQUESTED", "PROVIDER_RECEIVED", "NORMALIZED", "QUOTESERVICE_ACCEPTED",
          "WRITER_ATTEMPTED", "PERSISTED", "REJECTED")
REASONS = {"none", "request_failed_unclassified", "response_symbol_missing",
           "response_shape_invalid", "normalization_failed", "archive_dependency_missing",
           "archive_symbol_invalid", "writer_closed_or_batch_limit", "queue_full", "prepare_failed"}
ORIGINS = {"provider_realtime", "quote_service_poll", "quote_service_fetch", "dashboard_quote"}
_origin = ContextVar("archive_trace_origin", default="provider_realtime")
_symbol = re.compile(r"[.A-Z0-9][A-Z0-9.-]{0,63}\.(?:US|SH|SZ|BJ|HK)\Z")
logger = logging.getLogger(__name__)


def _now():
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _log(record):
    logger.info("archive_trace %s", json.dumps(record, sort_keys=True, separators=(",", ":")))


class TraceObserver:
    """Queue-only emission on caller threads. Sink errors/drops never reach business code."""

    def __init__(self, symbols=(), *, sink=_log, capacity=1024):
        # No wildcard, empty-list fallback, environment dump or automatic subscription.
        self.symbols = frozenset(s for s in symbols if isinstance(s, str) and _symbol.fullmatch(s))
        self._sink = sink
        self._queue = queue.Queue(maxsize=capacity)
        self._closing = threading.Event()
        self.dropped = 0
        self._thread = None
        if self.symbols:
            self._thread = threading.Thread(target=self._run, name="archive-trace", daemon=True)
            self._thread.start()

    def emit(self, record):
        try:
            if self._closing.is_set():
                return
            self._queue.put_nowait(record)
        except Exception:
            self.dropped += 1

    def _run(self):
        while not self._closing.is_set() or not self._queue.empty():
            try:
                record = self._queue.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                self._sink(record)
            except Exception:
                self.dropped += 1
            finally:
                self._queue.task_done()

    def close(self):
        self._closing.set()
        if self._thread is not None:
            self._thread.join(timeout=2)


class Trace:
    def __init__(self, observer, request_id, symbol, origin):
        self.observer = observer
        self.identity = {"trace_version": "benchmark-archive-trace/v1", "trace_id": uuid4().hex,
                         "request_id": request_id, "symbol": symbol, "market": market_from_symbol(symbol),
                         "source": "longbridge", "created_at": _now(), "origin": origin}
        self._sequence = itertools.count(1)

    def stage(self, stage, *, reason="none", rejected_at=None, queue_outcome=None,
              batch_id=None, ordinal=None, count=None):
        try:
            if stage not in STAGES or reason not in REASONS:
                return
            record = {**self.identity, "stage": stage, "stage_timestamp": _now(),
                      "stage_sequence": next(self._sequence), "reason_code": reason,
                      "status": "FAIL" if stage == "REJECTED" else "PASS",
                      "rejected_at_stage": rejected_at if rejected_at in STAGES[:-1] else None}
            if stage == "REQUESTED":
                record["method"] = "quote"
            if stage == "PROVIDER_RECEIVED":
                record["provider_quote_at"] = None  # Deliberately no SDK object inspection here.
            if stage == "NORMALIZED":
                record["normalizer"] = "longbridge_realtime"
            if stage == "QUOTESERVICE_ACCEPTED":
                record["consumer"] = "quote_service_archive"
            if stage == "WRITER_ATTEMPTED" and queue_outcome is None:
                queue_outcome = "UNKNOWN"
            if queue_outcome in {"ENQUEUED", "REJECTED", "UNKNOWN"}:
                record["queue_outcome"] = queue_outcome
            if isinstance(batch_id, str) and re.fullmatch(r"[0-9a-f]{32}", batch_id):
                record["writer_batch_id"] = batch_id
            if stage == "PERSISTED" and isinstance(ordinal, int) and isinstance(count, int):
                record["persistence_reference"] = {"ordinal": ordinal, "committed_count": count}
            self.observer.emit(record)
        except Exception:
            pass


class TraceRows(list):
    """Business list contents unchanged; identities are never inserted into row dicts."""

    def __init__(self, rows, traces):
        super().__init__(rows)
        self.traces = traces


class TraceBatch(list):
    def __init__(self, values, traces):
        super().__init__(values)
        self.traces = traces
        self.batch_id = uuid4().hex


def traced_rows(rows, traces):
    try:
        selected = {id(row): traces[id(row)] for row in rows if id(row) in traces}
        return TraceRows(rows, selected) if selected else rows
    except Exception:
        return rows


def traced_batch(values, traces):
    try:
        return TraceBatch(values, traces) if any(traces) else values
    except Exception:
        return values


def row_trace(rows, row):
    try:
        # Sidecar retains the original row reference: no symbol/time/positional guessing.
        entry = rows.traces.get(id(row)) if isinstance(rows, TraceRows) else None
        return entry[1] if entry is not None and entry[0] is row else None
    except Exception:
        return None


def record_rows(rows, stage, *, reason="none", rejected_at=None):
    try:
        if not isinstance(rows, TraceRows):
            return
        for row in rows:
            trace = row_trace(rows, row)
            if trace:
                trace.stage(stage, reason=reason, rejected_at=rejected_at)
    except Exception:
        pass


def batch_stage(batch, stage, *, reason="none", queue_outcome=None):
    try:
        if not isinstance(batch, TraceBatch):
            return
        for ordinal, trace in enumerate(batch.traces):
            if trace:
                trace.stage(stage, reason=reason,
                            rejected_at="WRITER_ATTEMPTED" if stage == "REJECTED" else None,
                            queue_outcome=queue_outcome, batch_id=batch.batch_id,
                            ordinal=ordinal, count=len(batch))
    except Exception:
        pass


class RequestTrace:
    def __init__(self, symbols, origin=None):
        self.traces = {}
        self.seen = set()
        try:
            observer = _observer
            origin = origin or _origin.get()
            if origin not in ORIGINS:
                return
            if not observer.symbols:
                return
            request_id = uuid4().hex
            for symbol in symbols:
                if symbol in observer.symbols:
                    trace = Trace(observer, request_id, symbol, origin)
                    self.traces[symbol] = trace
                    trace.stage("REQUESTED")
        except Exception:
            self.traces = {}

    def received(self, symbol):
        trace = self.traces.get(symbol) if isinstance(symbol, str) else None
        if trace:
            self.seen.add(symbol)
            trace.stage("PROVIDER_RECEIVED")

    def normalized(self, symbol):
        trace = self.traces.get(symbol) if isinstance(symbol, str) else None
        if trace:
            trace.stage("NORMALIZED")
        return trace

    def reject(self, reason, boundary, symbol=None):
        traces = self.traces.values() if symbol is None else [self.traces.get(symbol)]
        for trace in traces:
            if trace:
                trace.stage("REJECTED", reason=reason, rejected_at=boundary)

    def missing(self):
        for symbol in self.traces.keys() - self.seen:
            self.reject("response_symbol_missing", "PROVIDER_RECEIVED", symbol)


@contextmanager
def request_trace(symbols, *, origin=None):
    trace = RequestTrace(symbols, origin or _origin.get())
    try:
        yield trace
    except BaseException:
        trace.reject("request_failed_unclassified", "PROVIDER_RECEIVED")
        raise


@contextmanager
def trace_origin(origin):
    token = _origin.set(origin if origin in ORIGINS else "provider_realtime")
    try:
        yield
    finally:
        _origin.reset(token)


def stage_status(records, trace_id):
    """Missing/dropped observations remain UNKNOWN, never synthetic rejection."""
    result = dict.fromkeys(STAGES, "UNKNOWN")
    for record in records:
        if record.get("trace_id") == trace_id and record.get("stage") in result:
            result[record["stage"]] = record["status"]
    return result


# Explicit diagnostic scope only. This environment setting never changes requested symbols.
_observer = TraceObserver(os.environ.get("TSP_ARCHIVE_TRACE_SYMBOLS", "").split(",")[:32])
atexit.register(_observer.close)
