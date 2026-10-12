"""Read-only live observation. Never inject snapshots/events or alter thresholds."""
import argparse
import json
import time
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen


def observe(base: str, market: str, seconds: int) -> dict:
    def read(path):
        with urlopen(base.rstrip("/") + path, timeout=30) as response:
            return json.load(response)

    first = read("/api/intraday/anomalies/health")
    session = first.get("market_sessions", {}).get(market, {})
    result = {"market": market, "market_state": session, "observation_seconds": seconds,
              "frontend_visibility": "NOT VERIFIED - use browser delivery diagnostics", "read_only": True}
    if session.get("session_state") != "regular" or session.get("diagnostic_code"):
        return {**result, "status": "NOT RUN - MARKET CLOSED" if session.get("session_state") in {"closed", "holiday", "break", "pre_open", "post_market"} else "NOT RUN - MARKET UNKNOWN OR CONFLICT"}
    history = read("/api/intraday/anomalies/recent?limit=1")
    cursor = history.get("resume_cursor", {"sequence": 0, "event_id": None})
    snapshots = []
    generated = []
    last = first
    deadline = time.monotonic() + seconds
    while True:
        snapshots = read("/api/intraday/snapshots/recent?" + urlencode({"market": market, "limit": 1000}))["rows"]
        last = read("/api/intraday/anomalies/health")
        params = {"after_id": cursor["sequence"], "limit": 200}
        if cursor["event_id"]:
            params["after_event_id"] = cursor["event_id"]
        # Explicitly bounded: pending backlog is reported, never silently skipped.
        for _ in range(10):
            page = read("/api/intraday/anomalies/incremental?" + urlencode(params))
            generated.extend(page["rows"])
            cursor = page["next_cursor"]
            params["after_id"] = cursor["sequence"]
            if cursor["event_id"]:
                params["after_event_id"] = cursor["event_id"]
            if not page["has_more"]:
                break
        if time.monotonic() >= deadline:
            break
        time.sleep(min(3, max(0, deadline - time.monotonic())))
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    reliable = [row for row in snapshots if row.get("provider") == "longbridge"
                and row.get("market_session_state") == "regular" and not row.get("market_session_diagnostic")
                and row.get("quote_timestamp") is not None and row.get("receive_timestamp") is not None
                and 0 <= now_ms - int(row["quote_timestamp"]) <= 120000
                and 0 <= now_ms - int(row["receive_timestamp"]) <= 120000]
    consumed = [row for row in reliable if first.get("checkpoint") is not None and last.get("checkpoint") is not None
                and first["checkpoint"] < row.get("id", -1) <= last["checkpoint"]]
    processed = last.get("processed_by_market", {}).get(market, 0) - first.get("processed_by_market", {}).get(market, 0)
    evaluations = last.get("evaluations_by_market", {}).get(market, 0) - first.get("evaluations_by_market", {}).get(market, 0)
    reasons = []
    if not reliable:
        reasons.append("no_fresh_regular_longbridge_snapshots")
    if processed <= 0 or evaluations <= 0:
        reasons.append("no_observed_archive_consumption_or_evaluation")
    if not consumed:
        reasons.append("no_fresh_longbridge_snapshot_consumed_in_window")
    if last.get("state") != "observing":
        reasons.append("engine_not_observing")
    latest_session = last.get("market_sessions", {}).get(market, {})
    if latest_session.get("session_state") != "regular" or latest_session.get("diagnostic_code"):
        reasons.append("market_changed_or_conflicted_during_observation")
    if page["has_more"]:
        reasons.append("api_backlog_not_caught_up")
    events = [row for row in generated if row["market"] == market]
    return {**result, "status": "BLOCKED" if reasons else "LIVE PIPELINE HEALTHY",
            "anomaly_observation": "REAL ANOMALY OBSERVED" if events else "NO REAL ANOMALY OBSERVED",
            "blockers": reasons, "symbols_observed": sorted({row["symbol"] for row in reliable}),
            "snapshot_timestamps": [{"symbol": row["symbol"], "quote_timestamp": row["quote_timestamp"], "receive_timestamp": row["receive_timestamp"]} for row in reliable[:10]],
            "archive_consumption": {"processed_delta": processed, "checkpoint_start": first.get("checkpoint"), "checkpoint_end": last.get("checkpoint")},
            "evaluation_attempts_delta": evaluations, "generated_event_count": len(events),
            "consumed_longbridge_snapshot_ids": [row["id"] for row in consumed],
            "api_visible_event_ids": [row["event_id"] for row in events], "api_cursor": cursor,
            "diagnostics": last.get("diagnostics", [])[-10:]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:3018")
    parser.add_argument("--market", choices=("CN", "HK", "US"), default="US")
    parser.add_argument("--seconds", type=int, default=30)
    args = parser.parse_args()
    parsed = urlparse(args.base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.username or parsed.password or not 1 <= args.seconds <= 300:
        parser.error("loopback HTTP only, seconds must be 1..300")
    try:
        result = observe(args.base_url, args.market, args.seconds)
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError, TypeError):
        result = {"status": "BLOCKED", "reason": "api_unavailable_or_response_invalid", "read_only": True}
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
