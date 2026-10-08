"""三个固定标的的只读验证; 不输出价格或凭证。"""
from __future__ import annotations

import json
from datetime import UTC, datetime

from app.market_session import market_from_symbol
from app.plugins.longbridge.provider import LongbridgeProvider

SYMBOLS = ["600519.SH", "700.HK", "AAPL.US"]


def main() -> int:
    provider = LongbridgeProvider()
    try:
        rows = {row["symbol"]: row for row in provider.get_realtime(SYMBOLS)}
        now_ms = datetime.now(UTC).timestamp() * 1000
        result = []
        for symbol in SYMBOLS:
            row = rows.get(symbol, {})
            timestamp = row.get("timestamp")
            reasonable = bool(timestamp and 946684800000 <= timestamp <= now_ms + 300000)
            success = bool(row.get("last_price") and reasonable and row.get("currency"))
            reasons = sorted({error["reason"] for error in provider.last_errors})
            result.append({
                "symbol": symbol, "market": market_from_symbol(symbol), "success": success,
                "last_price_present": row.get("last_price") is not None,
                "timestamp_reasonable": reasonable, "currency_present": bool(row.get("currency")),
                "data_time_utc": datetime.fromtimestamp(timestamp / 1000, UTC).isoformat() if reasonable else None,
                "failure_reason": None if success else reasons or ["missing_or_invalid_response"],
            })
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if all(row["success"] for row in result) else 1
    finally:
        provider.close()


if __name__ == "__main__":
    raise SystemExit(main())
