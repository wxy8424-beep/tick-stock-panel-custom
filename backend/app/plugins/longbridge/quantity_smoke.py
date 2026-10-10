"""Explicit read-only diagnostic; print summaries, never credentials/raw responses."""
import json
from importlib.metadata import version

from app.plugins.longbridge.provider import LongbridgeProvider
from app.plugins.longbridge.quantity import REASONS


def main() -> int:
    provider = LongbridgeProvider()
    try:
        results = [
            provider.probe_quantity_contract(symbol, dataset)
            for symbol in ("600519.SH", "700.HK", "AAPL.US")
            for dataset in REASONS
        ]
        print(json.dumps({"sdk_version": version("longbridge"), "results": results}, ensure_ascii=False, indent=2))
        return 1 if any(row["request_status"] in {
            "authentication", "network", "sdk_exception", "response_shape_mismatch", "sdk_missing", "method_missing",
        } for row in results) else 0
    finally:
        provider.close()


if __name__ == "__main__":
    raise SystemExit(main())
