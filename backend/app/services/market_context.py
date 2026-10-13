"""Explanatory event-window context, exclusively from already archived observations."""
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

from app.market_session import get_market_session, market_from_symbol
from app.services.anomaly_engine import PRICE_ONLY_UNKNOWN, ArchiveInput, _milliseconds, _number
from app.services.index_const import CORE_INDEX_NAMES
from app.services.us_dashboard_service import INDEX_SYMBOLS

VERSION = "market-context-v1"
# Reuse established symbols. HK has no verified HSI feed in the current checkout.
BENCHMARKS = {"CN": (next(iter(CORE_INDEX_NAMES)), "上证指数"),
              "US": (INDEX_SYMBOLS[0], "标普500"), "HK": None}
US_AVAILABLE_INDICES = INDEX_SYMBOLS[:2]  # IXIC exists; no metadata-driven automatic choice in v1.
POLICY = {"boundary_tolerance_ms": 30000, "max_gap_ms": 120000,
          "aligned_relative_limit": "0.005", "independent_relative_min": "0.01"}


def unknown_market_context(event=None, blocker="enrichment_pending", status="unknown"):
    event = event or {}
    benchmark = BENCHMARKS.get(event.get("market"))
    return {"event_id": event.get("event_id"), "market": event.get("market"),
            "benchmark_symbol": benchmark[0] if benchmark else None,
            "benchmark_name": benchmark[1] if benchmark else None,
            "benchmark_change_pct": None, "stock_change_pct": None, "relative_move_pct": None,
            "direction_relation": "unknown", "context_class": "unknown",
            "observed_at": datetime.now(UTC).isoformat(), "source": None,
            "status": status, "blocker": blocker, "context_version": VERSION, "policy": dict(POLICY)}


class MarketContextStore:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / "user_data" / "anomaly_market_context.sqlite3"

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=1)
        db.execute("CREATE TABLE IF NOT EXISTS contexts (event_id TEXT PRIMARY KEY,payload TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS enrichment_cursor (singleton INTEGER PRIMARY KEY,sequence INTEGER NOT NULL,event_id TEXT)")
        return db

    def read_many(self, ids):
        if len(ids) > 200:
            raise ValueError("bounded context query required")
        if not ids or not self.path.exists():
            return {}
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='contexts'").fetchone():
                return {}
            return {key: json.loads(payload) for key, payload in db.execute(
                f"SELECT event_id,payload FROM contexts WHERE event_id IN ({','.join('?' for _ in ids)})", ids)}


def _time(value):
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(parsed, datetime) or parsed.utcoffset() is None:
        raise ValueError("event_time_unknown")
    return int(parsed.timestamp() * 1000)


def classify(stock, benchmark):
    relative = stock - benchmark
    if stock * benchmark < 0:
        return "opposite", "market_opposed"
    same = stock * benchmark > 0
    if same and abs(relative) <= Decimal(POLICY["aligned_relative_limit"]):
        return "same", "market_aligned"
    if abs(stock) > abs(benchmark) and abs(relative) >= Decimal(POLICY["independent_relative_min"]):
        return "same" if same else "neutral", "idiosyncratic"
    return "same" if same else "neutral", "mixed"


class MarketContextService:
    worker_name = "anomaly-market-enrichment"

    def __init__(self, data_dir):
        self.archive = ArchiveInput(data_dir)
        self.store = MarketContextStore(data_dir)

    def failure_context(self, event):
        return unknown_market_context(event, "market_enrichment_failed")

    def _observations(self, symbol, market, start, end, detected):
        # Read bounded archived window only. Both quote and receive clocks obey no-lookahead.
        return self.archive.read("""SELECT * FROM market_snapshots WHERE symbol=? AND market=?
            AND receive_timestamp<=? AND receive_timestamp>=? AND CAST(quote_timestamp AS REAL)>=?
            AND CAST(quote_timestamp AS REAL)<=? ORDER BY CAST(quote_timestamp AS REAL),id LIMIT 1001""",
                                 (symbol, market, detected, start - POLICY["boundary_tolerance_ms"], start - POLICY["boundary_tolerance_ms"], end))

    def _validate(self, row, market, detected):
        price = _number(row["price"])
        quote = _milliseconds(row["quote_timestamp"])
        received = row["receive_timestamp"]
        if received > detected or quote > received or received - quote > 120000:
            raise ValueError("benchmark_timestamp_or_freshness_invalid")
        warnings = set(json.loads(row["warnings"]))
        if row["quality_state"] not in {"valid", "unknown"} or warnings - PRICE_ONLY_UNKNOWN:
            raise ValueError("benchmark_quality_unreliable")
        if row["quality_state"] == "unknown" and not warnings:
            raise ValueError("benchmark_quality_unknown")
        if row["market_session_state"] != "regular" or row.get("market_session_diagnostic"):
            raise ValueError("benchmark_session_unconfirmed")
        session = get_market_session(market, datetime.fromtimestamp(quote / 1000, UTC))
        if session.session_state != "regular" or session.diagnostic_code:
            raise ValueError("benchmark_session_unconfirmed")
        return {"snapshot_id": row["id"], "price": str(price), "quote_timestamp": quote,
                "receive_timestamp": received, "provider": row["provider"],
                "quality_state": row["quality_state"], "warnings": sorted(warnings)}

    def context(self, event, evaluation_date=None):
        result = unknown_market_context(event)
        if not result["benchmark_symbol"]:
            return {**result, "status": "unsupported", "blocker": "market_benchmark_unverified"}
        try:
            if market_from_symbol(event["symbol"]) != event["market"]:
                raise ValueError("event_market_conflict")
            start, end, detected = (_time(event[key]) for key in ("window_start", "window_end", "detected_at"))
            if not 0 < start < end <= detected:
                raise ValueError("event_window_invalid")
            current = event["evidence"]["current"]
            baseline = event["evidence"]["baseline"]
            if len(baseline) != 1 or _milliseconds(current["quote_timestamp"]) != end or _milliseconds(baseline[0]["quote_timestamp"]) != start:
                raise ValueError("stock_window_evidence_mismatch")
            stock = (_number(current["price"]) - _number(baseline[0]["price"])) / _number(baseline[0]["price"])
            if abs(stock - Decimal(str(event["change_pct"]))) > Decimal("1e-12"):
                raise ValueError("stock_change_evidence_mismatch")
            rows = self._observations(result["benchmark_symbol"], event["market"], start, end, detected)
            if len(rows) > 1000:
                raise ValueError("benchmark_history_truncated")
            previous = [row for row in rows if _milliseconds(row["quote_timestamp"]) <= start]
            latest = [row for row in rows if _milliseconds(row["quote_timestamp"]) <= end]
            if not previous or not latest:
                raise ValueError("benchmark_boundary_missing")
            first, last = previous[-1], latest[-1]
            if start - _milliseconds(first["quote_timestamp"]) > POLICY["boundary_tolerance_ms"] or end - _milliseconds(last["quote_timestamp"]) > POLICY["boundary_tolerance_ms"]:
                raise ValueError("benchmark_boundary_stale")
            selected = [row for row in rows if _milliseconds(row["quote_timestamp"]) >= _milliseconds(first["quote_timestamp"])]
            observations = [self._validate(row, event["market"], detected) for row in selected]
            for left, right in pairwise(observations):
                gap = right["quote_timestamp"] - left["quote_timestamp"]
                if gap == 0 and (Decimal(left["price"]) != Decimal(right["price"]) or left["provider"] != right["provider"]):
                    raise ValueError("benchmark_same_timestamp_conflict")
                if gap > POLICY["max_gap_ms"]:
                    raise ValueError("benchmark_sparse_history")
            if observations[0]["quote_timestamp"] == observations[-1]["quote_timestamp"]:
                raise ValueError("benchmark_insufficient_history")
            if len({row["provider"] for row in observations}) != 1:
                raise ValueError("benchmark_source_conflict")
            benchmark = (Decimal(observations[-1]["price"]) - Decimal(observations[0]["price"])) / Decimal(observations[0]["price"])
            relation, category = classify(stock, benchmark)
            return {**result, "status": "available", "blocker": None, "source": observations[0]["provider"],
                    "stock_change_pct": str(stock), "benchmark_change_pct": str(benchmark),
                    "relative_move_pct": str(stock - benchmark), "direction_relation": relation, "context_class": category,
                    "window_start": event["window_start"], "window_end": event["window_end"],
                    "baseline_observation": observations[0], "current_observation": observations[-1],
                    "observations": observations, "stock_baseline": baseline[0], "stock_current": current,
                    "interpretation": "direction_and_magnitude_comparison_not_causal_explanation"}
        except ValueError as exc:
            safe = str(exc) if str(exc).startswith(("benchmark_", "stock_", "event_")) else "market_context_evidence_invalid"
            return {**result, "status": "unavailable", "blocker": safe}
        except Exception:
            return {**result, "status": "unknown", "blocker": "market_context_storage_or_evidence_unavailable"}


def enrich_market_response(data_dir, page):
    rows = page.get("rows", [])
    try:
        values = MarketContextStore(data_dir).read_many([row["event_id"] for row in rows])
        blocker = "enrichment_pending"
    except Exception:
        values, blocker = {}, "market_context_storage_unavailable"
    return {**page, "rows": [{**row, "evidence": {**row.get("evidence", {}),
            "market_context": values.get(row["event_id"], unknown_market_context(row, blocker))}} for row in rows]}
