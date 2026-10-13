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
        self._processed_total = 0
        self._evaluations_total = 0
        self._generated_total = 0
        self._processed_by_market = {market: 0 for market in ("CN", "HK", "US")}
        self._evaluations_by_market = {market: 0 for market in ("CN", "HK", "US")}
        self._history_worker = None
        self._market_worker = None
        self._data_dir = data_dir

    def health(self) -> dict:
        with self._lock:
            return {**self._health, "diagnostics": [dict(item) for item in self._health["diagnostics"]],
                    "processed_total": self._processed_total, "evaluations_total": self._evaluations_total,
                    "generated_total": self._generated_total,
                    "processed_by_market": dict(self._processed_by_market),
                    "evaluations_by_market": dict(self._evaluations_by_market),
                    "historical_enrichment": self._history_worker.health() if self._history_worker else {"state": "not_started"},
                    "market_enrichment": self._market_worker.health() if self._market_worker else {"state": "not_started"},
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
            self._processed_total += result["processed"]
            # Each processed row assesses every configured rule once; volatility is diagnostic-only.
            self._evaluations_total += result["processed"] * len(self.engine.policy.rules)
            self._generated_total += len(result.get("events", []))
            for market, count in result.get("processed_by_market", {}).items():
                self._processed_by_market[market] += count
                self._evaluations_by_market[market] += count * len(self.engine.policy.rules)
            self._health = {"state": "unavailable" if failed else "observing",
                            "processed": result["processed"], "checkpoint": result["checkpoint"],
                            "last_tick_at": as_of.isoformat(),
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
        try:
            from app.services.historical_enrichment import HistoricalEnrichmentWorker

            self._history_worker = HistoricalEnrichmentWorker(self._data_dir)
            self._history_worker.start()
        except Exception:
            logger.warning("历史上下文不可用. 原异动观察继续运行")
        try:
            from app.services.historical_enrichment import HistoricalEnrichmentWorker
            from app.services.market_context import MarketContextService

            self._market_worker = HistoricalEnrichmentWorker(self._data_dir, MarketContextService(self._data_dir))
            self._market_worker.start()
        except Exception:
            logger.warning("市场上下文不可用. 原异动观察继续运行")

    def _run(self):
        while not self._stop.is_set():
            self.tick(datetime.now(UTC))
            self._stop.wait(1)

    def close(self) -> None:
        self._stop.set()
        if self._history_worker is not None:
            self._history_worker.close()
        if self._market_worker is not None:
            self._market_worker.close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                logger.warning("异动观察停止超时. 不终止其它进程")
