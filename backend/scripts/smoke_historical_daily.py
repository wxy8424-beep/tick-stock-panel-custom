"""Explicit real-network Daily smoke; no secrets, persistence or trading."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.data_providers.historical import get_historical_provider


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="explicitly allow real read-only source requests")
    parser.add_argument("--market", choices=("CN", "US"), help="limit a follow-up smoke to one market")
    args = parser.parse_args()
    if not args.run:
        parser.error("pass --run for the explicit real read-only smoke")
    cases = (("CN", "600519.SH", date(2024, 6, 3), date(2024, 6, 14)),
             ("CN", "300750.SZ", date(2024, 6, 3), date(2024, 6, 14)),
             ("US", "AAPL.US", date(2024, 5, 6), date(2024, 5, 17)),
             ("US", "NVDA.US", date(2024, 6, 3), date(2024, 6, 14)))
    success = True
    for market, symbol, start, end in cases:
        if args.market and market != args.market:
            continue
        result = get_historical_provider(market).fetch_daily(symbol, start, end, "adjusted")
        rows = result.to_dict()["rows"]
        dates = [row["trading_date"] for row in rows]
        valid_raw = bool(rows) and all(
            all(row[key] is not None and row[key] > 0 for key in ("open", "high", "low", "close"))
            and row["low"] <= min(row["open"], row["close"]) <= max(row["open"], row["close"]) <= row["high"]
            for row in rows)
        valid_adjusted = bool(rows) and all(
            all(row[f"adjusted_{key}"] is not None for key in ("open", "high", "low", "close"))
            and row["adjusted_low"] <= min(row["adjusted_open"], row["adjusted_close"])
            <= max(row["adjusted_open"], row["adjusted_close"]) <= row["adjusted_high"] for row in rows)
        passed = result.status == "completed" and valid_raw and valid_adjusted
        passed = passed and dates == sorted(set(dates)) and all(start.isoformat() <= day <= end.isoformat() for day in dates)
        success = success and passed
        print(json.dumps({"symbol": symbol, "market": market, "status": result.status,
                          "smoke": "PASS" if passed else "EMPTY" if result.status == "empty" else "FAIL",
                          "requested_range": [start.isoformat(), end.isoformat()], "row_count": len(rows),
                          "returned_range": [dates[0], dates[-1]] if dates else None,
                          "sorted_unique": dates == sorted(set(dates)),
                          "raw_ohlc_valid": valid_raw, "adjusted_ohlc_valid": valid_adjusted,
                          "raw_method": sorted({row["adjustment_method"] for row in rows}),
                          "adjusted_method": sorted({row["adjusted_adjustment_method"] for row in rows if row["adjusted_adjustment_method"]}),
                          "volume_units": sorted({row["volume_unit"] for row in rows}),
                          "volume_null_count": sum(row["volume"] is None for row in rows),
                          "currencies": sorted({row["currency"] for row in rows if row["currency"]}),
                          "source": result.source, "diagnostics": list(result.diagnostics),
                          "action_rows": [{"trading_date": row["trading_date"], "dividend": row["dividend"],
                                           "split": row["split"], "close": row["close"],
                                           "adjusted_close": row["adjusted_close"]}
                                          for row in rows if row["dividend"] or row["split"]],
                          "action_window_prices": [{"trading_date": row["trading_date"], "close": row["close"],
                                                    "adjusted_close": row["adjusted_close"]}
                                                   for row in rows if any(item["dividend"] or item["split"] for item in rows)],
                          "adjustment_difference_dates": [row["trading_date"] for row in rows
                              if row["adjusted_close"] is not None and row["close"] != row["adjusted_close"]]},
                         allow_nan=False, ensure_ascii=False))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
