"""Financial availability, not unit evidence; one paced read per fixed symbol."""
import json
import time
from importlib.metadata import version

from app.market_session import market_from_symbol
from app.plugins.longbridge.provider import LongbridgeProvider


def main() -> int:
    provider = LongbridgeProvider()
    results = []
    try:
        for index, symbol in enumerate(("AAPL.US", "NVDA.US", "700.HK", "600519.SH")):
            if index:
                time.sleep(3)  # Avoid bursting the financial API; no automatic retry.
            summary = provider.probe_financial_contract(symbol)
            results.append({"symbol": symbol, "market": market_from_symbol(symbol),
                            "contract_status": summary["status"], "blocker_reason": summary["reason"],
                            **summary.get("diagnostic", {}),
                            "available_statements": summary.get("available_statements", []),
                            "currencies": summary.get("currencies", [])})
        # Classified upstream failures are valid diagnostics, not claims of support.
        passed = all(row.get("context_status") == "ready" and row.get("method_exists") is True
                     and row.get("failure_stage") != "adapter" for row in results)
        print(json.dumps({"sdk_version": version("longbridge"), "results": results,
                         "overall": "PASS" if passed else "FAIL"}, ensure_ascii=False, indent=2))
        return 0 if passed else 1
    finally:
        provider.close()


if __name__ == "__main__":
    raise SystemExit(main())
