"""Consumption-layer history, independent of Provider contracts and CN Parquet."""
from __future__ import annotations

import json
import logging
import queue
import sqlite3
import threading
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.data_providers.contracts import QUANTITY_UNITS
from app.data_providers.quote_quality import validate_quote
from app.market_session import get_market_session, market_from_symbol
from app.services.archive_trace import batch_stage, record_rows, row_trace, traced_batch

logger = logging.getLogger(__name__)
MAX_BATCH = 20_000


def _milliseconds(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include timezone")
    return int(value.timestamp() * 1000)


def _number(value) -> str | None:
    """Keep decimal text without unit conversion; never persist arbitrary payloads."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal, str)):
        return None
    text = str(value)
    if len(text) > 128:
        return None
    try:
        return text if Decimal(text).is_finite() else None
    except InvalidOperation:
        return None


def _provider_time(value) -> str | None:
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        _milliseconds(result)
        return result.astimezone(UTC).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


class SnapshotArchive:
    """Additive SQLite table. Reads do not create files/tables or contact providers."""

    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "user_data" / "market_snapshots.sqlite3"

    def append(self, rows: list[dict], received_at: datetime, provider: str) -> int:
        return self._write(self.prepare(rows, received_at, provider))

    @staticmethod
    def prepare(rows: list[dict], received_at: datetime, provider: str) -> list[tuple]:
        received_ms = _milliseconds(received_at)
        if len(rows) > MAX_BATCH:
            raise ValueError("snapshot batch too large")
        values = []
        traces = []
        for row in rows:
            symbol = row.get("symbol") if isinstance(row, dict) else None
            market = market_from_symbol(symbol)
            if market is None or len(symbol) > 128:
                trace = row_trace(rows, row)
                if trace:
                    trace.stage("REJECTED", reason="archive_symbol_invalid", rejected_at="WRITER_ATTEMPTED")
                continue
            # Old providers may omit market; only the established symbol resolver
            # supplies it. Explicit conflicts remain unknown quality, not hidden.
            try:
                quality = validate_quote({"market": market, **row}, received_at)
            except Exception:
                quality = {"state": "unknown", "warnings": ["quality_check_unknown"],
                           "observed_at": received_at.isoformat(), "latency_ms": None}
            session = get_market_session(market, received_at)
            unit = row.get("volume_unit")
            values.append((symbol, market, provider, _number(row.get("last_price")),
                           _number(row.get("volume")), _number(row.get("timestamp")),
                           received_ms, quality["state"], json.dumps(quality["warnings"]),
                           session.session_state, _provider_time(row.get("provider_observed_at")),
                           quality["observed_at"], quality["latency_ms"],
                           unit if isinstance(unit, str) and unit in QUANTITY_UNITS else "unknown",
                           session.diagnostic_code))
            traces.append(row_trace(rows, row))
        return traced_batch(values, traces)

    def _write(self, values: list[tuple]) -> int:
        if not values:
            return 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=1)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS market_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, market TEXT NOT NULL,
                provider TEXT NOT NULL, price TEXT, volume TEXT, quote_timestamp TEXT,
                receive_timestamp INTEGER NOT NULL, quality_state TEXT NOT NULL,
                warnings TEXT NOT NULL, market_session_state TEXT NOT NULL,
                provider_observed_at TEXT, quality_observed_at TEXT NOT NULL, latency_ms INTEGER,
                volume_unit TEXT NOT NULL, market_session_diagnostic TEXT
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS snapshots_symbol_time ON market_snapshots(symbol, receive_timestamp DESC, id DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS snapshots_time ON market_snapshots(receive_timestamp DESC, id DESC)")
            db.executemany("""INSERT INTO market_snapshots
                (symbol, market, provider, price, volume, quote_timestamp, receive_timestamp,
                 quality_state, warnings, market_session_state, provider_observed_at,
                 quality_observed_at, latency_ms, volume_unit, market_session_diagnostic)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", values)
        return len(values)

    def query(self, *, symbol: str | None = None, market: str | None = None,
              limit: int = 100, before_id: int | None = None, latest: bool = False) -> list[dict]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        if market is not None and market not in {"CN", "HK", "US"}:
            raise ValueError("unknown market")
        if not self.path.exists():
            return []
        filters, params = [], []
        for name, value in (("symbol", symbol), ("market", market)):
            if value is not None:
                filters.append(f"{name} = ?")
                params.append(value)
        if before_id is not None:
            filters.append("id < ?")
            params.append(before_id)
        where = " WHERE " + " AND ".join(filters) if filters else ""
        # id is insertion order; receipt times are retained without pretending
        # they are necessarily monotonic across wall-clock corrections.
        sql = "SELECT * FROM market_snapshots" + where
        if latest:
            sql = "SELECT * FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY id DESC) AS rank FROM market_snapshots" + where + ") WHERE rank = 1"
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
            db.row_factory = sqlite3.Row
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='market_snapshots'").fetchone()
            if exists is None:
                return []
            result = [dict(row) for row in db.execute(sql + " ORDER BY id DESC LIMIT ?", [*params, limit])]
        for row in result:
            row.pop("rank", None)
            row["warnings"] = json.loads(row["warnings"])
        return result

    def cleanup(self, before: datetime) -> int:
        """Explicit opt-in deletion from this table only; never automatic pruning."""
        cutoff = _milliseconds(before)
        if not self.path.exists():
            return 0
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=rw", uri=True, timeout=1)) as db, db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='market_snapshots'").fetchone() is None:
                return 0
            return db.execute("DELETE FROM market_snapshots WHERE receive_timestamp < ?", (cutoff,)).rowcount


class SnapshotWriter:
    """Four pending batches; no unbounded queue or disk IO in the quote thread."""

    def __init__(self, data_dir: Path):
        self.archive = SnapshotArchive(data_dir)
        self._queue = queue.Queue(maxsize=4)
        self._lock = threading.Lock()
        self._closing = threading.Event()
        self._thread = None

    def submit(self, rows: list[dict], received_at: datetime, provider: str) -> bool:
        if not rows:
            return True
        record_rows(rows, "WRITER_ATTEMPTED")
        with self._lock:
            if self._closing.is_set() or len(rows) > MAX_BATCH:
                record_rows(rows, "REJECTED", reason="writer_closed_or_batch_limit",
                            rejected_at="WRITER_ATTEMPTED")
                logger.warning("快照归档未接收: 已关闭或批次超限")
                return False
            if self._queue.full():
                record_rows(rows, "REJECTED", reason="queue_full", rejected_at="WRITER_ATTEMPTED")
                logger.warning("快照归档未接收: 队列已满")
                return False
            # Capture quality/session now, not after a delayed disk write.
            try:
                batch = self.archive.prepare(rows, received_at, provider)
            except Exception:
                record_rows(rows, "REJECTED", reason="prepare_failed", rejected_at="WRITER_ATTEMPTED")
                raise
            try:
                self._queue.put_nowait(batch)
            except queue.Full:
                batch_stage(batch, "REJECTED", reason="queue_full")
                logger.warning("快照归档未接收: 队列已满")
                return False
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="snapshot-archive", daemon=True)
                self._thread.start()
        return True

    def _run(self):
        while not self._closing.is_set() or not self._queue.empty():
            try:
                batch = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                batch_stage(batch, "WRITER_ATTEMPTED", queue_outcome="ENQUEUED")
                self.archive._write(batch)
                # _write returns only after SQLite's transaction context committed.
                batch_stage(batch, "PERSISTED")
            except Exception:
                # No raw error message or quote payload in logs.
                logger.warning("快照归档批次写入失败, 行情链路保持运行")
            finally:
                self._queue.task_done()

    def close(self):
        with self._lock:
            self._closing.set()
            worker = self._thread
        if worker is not None:
            worker.join(timeout=10)
            if worker.is_alive():
                logger.warning("快照归档关闭超时, 仍有待写入批次")
