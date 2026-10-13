"""Independent asynchronous event-context consumer, never on the quote/detection thread."""
import json
import threading
from contextlib import closing
from datetime import UTC, datetime

from app.market_session import get_market_session
from app.services.anomaly_engine import AnomalyStore
from app.services.historical_baseline import HistoricalBaselineService, unknown_context


class HistoricalEnrichmentWorker:
    def __init__(self, data_dir, service=None):
        self.service = service or HistoricalBaselineService(data_dir)
        self.events = AnomalyStore(data_dir)
        self._stop = threading.Event()
        self._thread = None
        self._health = {"state": "not_started", "processed": 0}
        self._lock = threading.Lock()

    def health(self):
        with self._lock:
            return dict(self._health)

    def tick(self):
        try:
            with closing(self.service.store.connect()) as db:
                cursor = db.execute("SELECT sequence,event_id FROM enrichment_cursor WHERE singleton=1").fetchone()
            page = self.events.incremental(cursor[0] if cursor else 0, cursor[1] if cursor else None, limit=5)
            for event in page["rows"]:
                if self._stop.is_set():
                    break
                try:
                    timestamp = event["evidence"]["current"]["quote_timestamp"]
                    evaluation_date = get_market_session(event["market"], datetime.fromtimestamp(timestamp / 1000, UTC)).local_datetime.date()
                    context = self.service.context(event, evaluation_date)
                except Exception:
                    context = self.service.failure_context(event) if hasattr(self.service, "failure_context") else unknown_context("historical_enrichment_failed")
                # Context and consumer cursor advance together; original event is never updated.
                with closing(self.service.store.connect()) as db, db:
                    db.execute("INSERT OR REPLACE INTO contexts VALUES (?,?)", (event["event_id"], json.dumps(context, allow_nan=False)))
                    db.execute("INSERT OR REPLACE INTO enrichment_cursor VALUES (1,?,?)", (event["store_id"], event["event_id"]))
            with self._lock:
                self._health = {"state": "observing", "processed": len(page["rows"])}
        except Exception:
            with self._lock:
                self._health = {"state": "unavailable", "processed": 0, "blocker": "historical_context_storage_or_cursor_unavailable"}

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name=getattr(self.service, "worker_name", "anomaly-history-enrichment"), daemon=True)
            self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(3)

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
