"""Opt-in public historical reads; all cache/fixture writes use a temporary directory."""
import argparse
import hashlib
import json
import math
import sys
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.anomalies import router
from app.data_providers.historical import get_historical_provider
from app.market_session import market_from_symbol
from app.services.anomaly_engine import AnomalyStore
from app.services.historical_baseline import (
    BASELINE_VERSION,
    DEFAULT_METHOD,
    HistoricalBaselineService,
)
from app.services.historical_enrichment import HistoricalEnrichmentWorker


class CoverEvaluationDate:
    """Real fetch deliberately covers D; service must exclude D before computing."""

    def __init__(self, provider, evaluation_date):
        self.provider = provider
        self.evaluation_date = evaluation_date
        self.calls = 0
        self.response = None

    def fetch_daily(self, symbol, start, end, mode):
        self.calls += 1
        self.response = self.provider.fetch_daily(symbol, start, self.evaluation_date, mode)
        return self.response


def validate_baseline(result, evaluation_date):
    bars = result["bars"]
    dates = [row["date"] for row in bars]
    checks = {
        "available": result["status"] == "available",
        "nonempty": bool(bars),
        "ordered_unique": dates == sorted(set(dates)),
        "strictly_before_evaluation": bool(dates) and max(dates) < evaluation_date.isoformat(),
        "atr14_positive_finite": positive(result["atr14"]),
        "reference_close_positive_finite": positive(result["reference_close"]),
        "warmup": result["observations"] >= 14,
        "bounds": bool(dates) and result["lookback_start"] == dates[0] and result["lookback_end"] == dates[-1],
        "ohlc": bool(bars) and all(
            all(positive(row[key]) for key in ("open", "high", "low", "close"))
            and row["low"] <= min(row["open"], row["close"]) <= max(row["open"], row["close"]) <= row["high"]
            for row in bars
        ),
    }
    return checks


def positive(value):
    return value is not None and math.isfinite(float(value)) and float(value) > 0


def fixture_integration(data_dir, service, symbol, evaluation_date):
    """Isolated synthetic event, never a claim that a real anomaly occurred."""
    events = AnomalyStore(data_dir)
    event_id = hashlib.sha256(symbol.encode()).hexdigest()
    event = {"event_id": event_id, "episode_id": "b" * 64, "symbol": symbol,
             "market": market_from_symbol(symbol), "event_type": "rapid_price_move",
             "severity": "high", "status": "first_trigger", "change_value": "4.1",
             "evidence": {"current": {"quote_timestamp": int(datetime.combine(
                 evaluation_date, datetime.min.time(), UTC).replace(hour=14).timestamp() * 1000)}}}
    with closing(events.connect()) as db, db:
        db.execute("INSERT INTO anomaly_events(event_id,episode_id,symbol,market,event_type,severity,detected_at,payload) VALUES (?,?,?,?,?,?,?,?)",
                   (event_id, event["episode_id"], symbol, event["market"], event["event_type"], "high", 1000, json.dumps(event)))
    before = events.path.read_bytes()
    HistoricalEnrichmentWorker(data_dir, service).tick()
    app = FastAPI()
    app.include_router(router)
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=data_dir))
    with TestClient(app) as client:
        response = client.get("/api/intraday/anomalies/historical-context", params={"event_id": event_id})
        recent = client.get("/api/intraday/anomalies/recent").json()
    context = response.json()
    overlay = next(row for row in recent["rows"] if row["event_id"] == event_id)["evidence"]["historical_context"]
    passed = (response.status_code == 200 and context == overlay
              and context["blocker"] == "event_baseline_price_scale_unverified"
              and context["move_atr_ratio"] is None and context["atr14"] is not None
              and events.path.read_bytes() == before)
    return {"kind": "FIXTURE CONTRACT VALIDATION", "status": "PASS" if passed else "FAIL",
            "context_status": context["status"], "blocker": context["blocker"],
            "production_event_inserted": False, "original_event_unchanged": events.path.read_bytes() == before}


def smoke_symbol(symbol, evaluation_date, data_dir, provider_factory=get_historical_provider):
    market = market_from_symbol(symbol)
    method = DEFAULT_METHOD[market]
    counted = CoverEvaluationDate(provider_factory(market), evaluation_date)
    service = HistoricalBaselineService(data_dir, provider_factory=lambda _: counted)
    first = service.baseline(symbol, evaluation_date)
    second = service.baseline(symbol, evaluation_date)
    checks = validate_baseline(first, evaluation_date)
    checks["source"] = counted.response is not None and first["source"] == counted.response.source
    checks["adjustment_method"] = first["adjustment_method"] == method
    checks["cache"] = counted.calls == 1 and first == second
    codes = sorted({item["code"] for item in counted.response.diagnostics}) if counted.response else []
    schema_issue = any(code in {"response_shape_mismatch", "security_metadata_mismatch", "currency_schema_unknown"} for code in codes)
    report = {"symbol": symbol, "evaluation_date": evaluation_date.isoformat(),
              "status": "PASS" if all(checks.values()) else "BLOCKED", "checks": checks,
              "provider_status": counted.response.status if counted.response else "unavailable",
              "provider_diagnostic_codes": codes, "schema_issue": schema_issue,
              "source_attempts": [item for item in first.get("provider_diagnostics", [])
                                  if item["code"] in {"primary_attempt", "fallback_attempt", "fallback_used"}],
              **{key: first[key] for key in ("source", "adjustment_method", "lookback_start", "lookback_end",
                                            "atr14", "reference_close", "observations", "blocker")},
              "service_as_of_date_is_evaluation_date": first["as_of_date"],
              "prior_completed_as_of_date": first["lookback_end"],
              "ohlc_samples": first["bars"][:1] + first["bars"][-1:],
              "provider_fetch_end": evaluation_date.isoformat(),
              "provider_returned_evaluation_bar": counted.response is not None and not counted.response.frame.is_empty()
                  and evaluation_date in counted.response.frame["trading_date"].to_list(),
              "cache": {"key": hashlib.sha256(json.dumps((symbol, evaluation_date.isoformat(), method, BASELINE_VERSION)).encode()).hexdigest(),
                        "first": "miss", "second": "hit", "provider_calls": counted.calls,
                        "result_equal": first == second, "successful_baseline_cached": first["status"] == "available"},
              "price_scale_compatibility": "unverified", "move_atr_ratio": None,
              "ratio_blocker": "event_baseline_price_scale_unverified", "source_level_pit": False}
    if report["status"] == "PASS":
        report["integration"] = fixture_integration(data_dir, service, symbol, evaluation_date)
        if report["integration"]["status"] != "PASS":
            report["status"] = "FAIL"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation-date", required=True, type=date.fromisoformat)
    args = parser.parse_args()
    success = True
    with TemporaryDirectory(prefix="historical-baseline-smoke-") as directory:
        for symbol in ("600519.SH", "300750.SZ", "AAPL.US", "NVDA.US"):
            result = smoke_symbol(symbol, args.evaluation_date, Path(directory) / symbol)
            print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)
            success &= result["status"] == "PASS"
            if result["schema_issue"]:
                break
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
