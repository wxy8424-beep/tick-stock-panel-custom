"""Independent bounded best-effort consumer of committed events."""
import threading
from contextlib import closing

from app.services.anomaly_engine import AnomalyStore
from app.services.anomaly_intelligence import AnomalyEvidenceCollector, AnomalyIntelligenceStore


class AnomalyIntelligenceWorker:
    def __init__(self, data_dir, *, collector=None):
        self.collector = collector or AnomalyEvidenceCollector(data_dir)
        self.store = AnomalyIntelligenceStore(data_dir)
        self.events = AnomalyStore(data_dir)
        self._stop = threading.Event()
        self._thread = None
        self._health = {"state": "not_started"}
        self._lock = threading.Lock()

    def health(self):
        with self._lock:
            return dict(self._health)

    def tick(self):
        try:
            with closing(self.store.connect()) as db:
                cursor = db.execute("SELECT sequence,event_id FROM consumer_cursor WHERE singleton=1").fetchone()
            page = self.events.incremental(cursor[0] if cursor else 0, cursor[1] if cursor else None, limit=5)
            count = 0
            for event in page["rows"]:
                if self._stop.is_set():
                    break
                # A duplicate resume must use its immutable existing record, not newer sidecars.
                record = self.store.get(event["event_id"]) or self.collector.collect(event)
                result = self.store.save(record, sequence=event["store_id"])
                if result["status"] == "BLOCKED":
                    raise ValueError("intelligence_identity_conflict")
                count += 1
            health = {"state": "observing", "processed": count}
        except Exception:
            # Cursor is not advanced on failure; original delivery database is never written.
            health = {"state": "unavailable", "blocker": "intelligence_enrichment_or_cursor_unavailable"}
        with self._lock:
            self._health = health

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="anomaly-intelligence-enrichment", daemon=True)
            self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(3)

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
