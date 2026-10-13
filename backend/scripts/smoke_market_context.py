"""Read-only existing archive/event evidence. Never fetch or insert production events."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.anomaly_engine import AnomalyStore
from app.services.market_context import BENCHMARKS, MarketContextService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parents[2] / "data")
    args = parser.parse_args()
    service = MarketContextService(args.data_dir)
    for market, benchmark in BENCHMARKS.items():
        rows = service.archive.read("SELECT COUNT(*) AS samples,MAX(receive_timestamp) AS latest_receive FROM market_snapshots WHERE symbol=? AND market=?",
                                    (benchmark[0], market)) if benchmark else []
        print(json.dumps({"kind": "REAL ARCHIVE COVERAGE", "market": market,
                          "benchmark": benchmark[0] if benchmark else None, "coverage": rows}, allow_nan=False))
    events = AnomalyStore(args.data_dir).query(limit=5)["rows"]
    if not events:
        print(json.dumps({"kind": "REAL MARKET CONTEXT SMOKE", "status": "NOT RUN",
                          "reason": "no_real_anomaly_event", "production_events_inserted": 0}))
    for event in events:
        context = service.context(event)
        print(json.dumps({"kind": "REAL MARKET CONTEXT SMOKE", "symbol": event["symbol"],
                          "event_id": event["event_id"], **{key: context[key] for key in (
                              "status", "blocker", "benchmark_symbol", "source", "stock_change_pct",
                              "benchmark_change_pct", "relative_move_pct", "context_class")}}, allow_nan=False))


if __name__ == "__main__":
    main()
