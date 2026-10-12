"""Bounded archive consumer, fully independent of quote/provider threads."""
import logging
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from app.services.anomaly_engine import AnomalyEngine

logger = logging.getLogger(__name__)


class AnomalyWorker:
    def __init__(self, data_dir: Path):
        self.engine = AnomalyEngine(data_dir)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = None
        self._last_warning = 0.0
        self._health = {"state": "not_started", "processed": 0, "checkpoint": None, "diagnostics": []}

    def health(self) -> dict:
        with self._lock:
            return {**self._health, "diagnostics": [dict(item) for item in self._health["diagnostics"]],
                    "volatility_expansion": {"status": "unsupported", "reason": "snapshot_cadence_not_authoritative"},
                    "volume_spike": {"status": "unsupported", "reason": "longbridge_volume_unit_unverified"},
                    "rule_version": self.engine.policy.version}

    def tick(self, as_of: datetime) -> dict:
        try:
            result = self.engine.run_once(as_of, limit=100)
        except Exception:
            result = {"processed": 0, "checkpoint": None,
                      "diagnostics": [{"state": "unknown", "reason": "anomaly_worker_failed"}]}
        failed = result["checkpoint"] is None
        with self._lock:
            self._health = {"state": "unavailable" if failed else "observing",
                            "processed": result["processed"], "checkpoint": result["checkpoint"],
                            "diagnostics": result["diagnostics"]}
        if failed and time.monotonic() - self._last_warning >= 30:
            logger.warning("异动观察不可用. 实时行情链路不受影响. 详情见异动 health diagnostic")
            self._last_warning = time.monotonic()
        return result

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="archive-anomaly-observer")
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            self.tick(datetime.now(UTC))
            self._stop.wait(1)

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                logger.warning("异动观察停止超时. 不终止其它进程")
