"""Prior completed Daily evidence, computed by the existing research factor engine."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import polars as pl

from app.data_providers.historical import get_historical_provider
from app.factors.engine import FactorRequest, MarketFactorEngine
from app.market_session import get_market_session, market_from_symbol

METHODS = {"CN": {"none": "raw", "akshare_qfq": "adjusted"},
           "US": {"yfinance_auto_adjust_false": "raw", "yfinance_auto_adjust": "adjusted"}}
SOURCES = {"CN": "akshare.stock_zh_a_hist/eastmoney", "US": "yfinance.Ticker.history/yahoo"}
DEFAULT_METHOD = {"CN": "none", "US": "yfinance_auto_adjust_false"}
BASELINE_VERSION = "historical-baseline-v1"


class HistoricalContextStore:
    """Separate runtime sidecar. Immutable anomaly payloads and sequence stay untouched."""

    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "user_data" / "anomaly_historical_context.sqlite3"

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=1)
        db.execute("CREATE TABLE IF NOT EXISTS baselines (cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS contexts (event_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS enrichment_cursor (singleton INTEGER PRIMARY KEY, sequence INTEGER NOT NULL, event_id TEXT)")
        return db

    def reserve(self, key: str, pending: dict) -> tuple[dict, bool]:
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            found = db.execute("SELECT payload FROM baselines WHERE cache_key=?", (key,)).fetchone()
            if found:
                return json.loads(found[0]), False
            db.execute("INSERT INTO baselines VALUES (?,?)", (key, json.dumps(pending)))
        return pending, True

    def save_baseline(self, key: str, result: dict):
        with closing(self.connect()) as db, db:
            db.execute("UPDATE baselines SET payload=? WHERE cache_key=?", (json.dumps(result, allow_nan=False), key))

    def read_many(self, event_ids: list[str]) -> dict[str, dict]:
        if not event_ids or not self.path.exists():
            return {}
        if len(event_ids) > 200:
            raise ValueError("bounded context query required")
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='contexts'").fetchone():
                return {}
            placeholders = ",".join("?" for _ in event_ids)
            return {key: json.loads(value) for key, value in db.execute(f"SELECT event_id,payload FROM contexts WHERE event_id IN ({placeholders})", event_ids)}


def unknown_context(blocker="enrichment_pending") -> dict:
    return {"status": "unknown", "blocker": blocker, "atr14": None, "move_absolute": None,
            "move_atr_ratio": None, "baseline_as_of": None, "observations": None,
            "source": None, "adjustment_method": None, "baseline_version": BASELINE_VERSION}


class HistoricalBaselineService:
    def __init__(self, data_dir: Path, *, provider_factory=get_historical_provider,
                 factor_engine=None, version=BASELINE_VERSION):
        self.store = HistoricalContextStore(data_dir)
        self.provider_factory = provider_factory
        self.engine = factor_engine or MarketFactorEngine()
        self.version = version

    def baseline(self, symbol: str, evaluation_date: date, adjustment_method: str | None = None) -> dict:
        if type(evaluation_date) is not date:
            raise ValueError("explicit evaluation Date required")
        market = market_from_symbol(symbol)
        method = adjustment_method or DEFAULT_METHOD.get(market)
        result = {"symbol": symbol, "market": market, "atr14": None, "reference_close": None,
                  "lookback_start": None, "lookback_end": None, "observations": 0,
                  "as_of_date": evaluation_date.isoformat(), "source": SOURCES.get(market),
                  "adjustment_method": method, "baseline_version": self.version,
                  "status": "unknown", "blocker": "baseline_pending", "bars": [],
                  "fetched_at": None, "pit_capable": False, "pit_blocker": "source_vintage_unverified",
                  "calculation": {"engine": "MarketFactorEngine", "mode": "research", "factor": "atr", "period": 14,
                                  "price_basis": "as_provided", "version": self.version},
                  "daily_volatility_status": "unsupported_annualized_factor_not_daily"}
        if market not in METHODS:
            return {**result, "status": "unsupported", "blocker": "historical_market_unsupported"}
        if evaluation_date > get_market_session(market, datetime.now(UTC)).local_datetime.date():
            return {**result, "status": "unknown", "blocker": "evaluation_date_in_future"}
        if method not in METHODS[market]:
            return {**result, "status": "unsupported", "blocker": "adjustment_method_unsupported"}
        key = hashlib.sha256(json.dumps((symbol, evaluation_date.isoformat(), method, self.version)).encode()).hexdigest()
        try:
            existing, reserved = self.store.reserve(key, result)
            if not reserved:
                return {**existing, "status": "unavailable", "blocker": "baseline_cache_pending_or_interrupted"} if existing.get("blocker") == "baseline_pending" else existing
        except Exception:
            return {**result, "status": "unavailable", "blocker": "baseline_cache_unavailable"}
        try:
            start, end = evaluation_date - timedelta(days=120), evaluation_date - timedelta(days=1)
            supplied = self.provider_factory(market).fetch_daily(symbol, start, end, METHODS[market][method])
            if supplied.status not in {"ok", "partial"} or supplied.frame.is_empty():
                result.update(status="unavailable", blocker="historical_provider_empty_or_unavailable")
            else:
                result = self._calculate(result, supplied, start, evaluation_date, method)
        except Exception:
            result.update(status="unavailable", blocker="historical_provider_or_calculation_failed")
        try:
            self.store.save_baseline(key, result)
        except Exception:
            return {**result, "status": "unavailable", "blocker": "baseline_cache_write_failed", "atr14": None}
        return result

    def _calculate(self, result, supplied, start, evaluation_date, method):
        if supplied.symbol != result["symbol"] or supplied.market != result["market"] or supplied.source != result["source"]:
            return {**result, "status": "unavailable", "blocker": "historical_identity_conflict"}
        frame = supplied.frame
        if frame.schema.get("trading_date") != pl.Date:
            return {**result, "status": "unknown", "blocker": "historical_date_schema_unknown"}
        # Critical gate precedes factor calculation even if provider leaks D/D+1.
        frame = frame.filter((pl.col("trading_date") >= start) & (pl.col("trading_date") < evaluation_date)).sort("trading_date")
        if frame.is_empty():
            return {**result, "status": "unavailable", "blocker": "no_completed_history"}
        adjusted = METHODS[result["market"]][method] == "adjusted"
        columns = {key: f"adjusted_{key}" if adjusted else key for key in ("open", "high", "low", "close")}
        method_column = "adjusted_adjustment_method" if adjusted else "adjustment_method"
        if frame.select(pl.col("trading_date").is_duplicated().any()).item():
            return {**result, "status": "unknown", "blocker": "historical_duplicate_date"}
        bars = []
        for row in frame.to_dicts():
            if row["symbol"] != result["symbol"] or row["market"] != result["market"] or row[method_column] != method or row["source"] != result["source"]:
                return {**result, "status": "unknown", "blocker": "historical_semantics_conflict"}
            values = {key: row[column] for key, column in columns.items()}
            if any(value is None or isinstance(value, bool) or not math.isfinite(value) or value <= 0 for value in values.values()):
                return {**result, "status": "unknown", "blocker": "historical_price_missing_or_invalid"}
            if not values["low"] <= min(values["open"], values["close"]) <= max(values["open"], values["close"]) <= values["high"]:
                return {**result, "status": "unknown", "blocker": "historical_ohlc_invalid"}
            bars.append({"date": row["trading_date"].isoformat(), **values})
        result.update(bars=bars, observations=len(bars), lookback_start=bars[0]["date"], lookback_end=bars[-1]["date"],
                      reference_close=str(bars[-1]["close"]), fetched_at=datetime.now(UTC).isoformat())
        history = pl.DataFrame([{"symbol": result["symbol"], "date": date.fromisoformat(row["date"]), **{key: row[key] for key in columns}} for row in bars])
        computed = self.engine.compute(history, (FactorRequest("atr", 14),), price_basis="as_provided", mode="research")
        atr = computed.frame["atr_14"][-1]
        if atr is None:
            return {**result, "status": "unavailable", "blocker": "insufficient_atr_history"}
        if not math.isfinite(atr) or atr <= 0:
            return {**result, "status": "unknown", "blocker": "atr_invalid_or_zero"}
        return {**result, "atr14": str(atr), "status": "available", "blocker": None}

    def context(self, event: dict, evaluation_date: date, adjustment_method: str | None = None) -> dict:
        baseline = self.baseline(event["symbol"], evaluation_date, adjustment_method)
        context = {**baseline, "baseline_as_of": baseline["lookback_end"], "move_absolute": None, "move_atr_ratio": None}
        if event.get("market") != baseline["market"]:
            return {**context, "status": "unknown", "blocker": "event_market_conflict"}
        try:
            move = abs(Decimal(str(event["change_value"])))
            if not move.is_finite():
                raise ValueError("nonfinite move")
            context["move_absolute"] = str(move)
            if baseline["status"] == "available":
                if baseline["adjustment_method"] not in DEFAULT_METHOD.values():
                    context.update(status="unsupported", blocker="adjusted_baseline_realtime_price_basis_unverified")
                else:
                    context["move_atr_ratio"] = str(move / Decimal(baseline["atr14"]))
        except Exception:
            context.update(status="unknown", blocker="event_move_invalid", move_atr_ratio=None)
        return context


def enrich_response(data_dir: Path, page: dict) -> dict:
    """Read-only batch overlay; no provider calls or mutation of source payloads."""
    rows = page.get("rows", [])
    try:
        values = HistoricalContextStore(data_dir).read_many([row["event_id"] for row in rows])
        blocker = "enrichment_pending"
    except Exception:
        values, blocker = {}, "context_storage_unavailable"
    return {**page, "rows": [{**row, "evidence": {**row.get("evidence", {}),
             "historical_context": values.get(row["event_id"], unknown_context(blocker))}} for row in rows]}
