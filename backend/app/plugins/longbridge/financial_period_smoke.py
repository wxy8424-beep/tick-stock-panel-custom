"""Read-only financial period evidence; never infer units from sample dates."""
import json
from importlib.metadata import version

from app.plugins.longbridge.provider import LongbridgeProvider


def main() -> int:
    provider = LongbridgeProvider()
    try:
        rows = [
            {"symbol": symbol, **provider.probe_financial_contract(symbol)}
            for symbol in ("600519.SH", "700.HK", "AAPL.US", "NVDA.US")
        ]
        expected = ("empty", "contract_blocked", "contract_blocked", "contract_blocked")
        passed = all(row["status"] == status and row.get("reason") != "financial_network_unavailable"
                     for row, status in zip(rows, expected, strict=True))
        hk = rows[1]
        passed = passed and hk.get("available_statements") == ["BS", "CF", "IS"]
        evidence = hk.get("period_end_evidence", {})
        passed = passed and evidence.get("source_types") == ["string"] and evidence.get("conversion_performed") is False
        print(json.dumps({"sdk_version": version("longbridge"), "results": rows,
                         "overall": "PASS" if passed else "FAIL"}, ensure_ascii=False, indent=2))
        return 0 if passed else 1
    finally:
        provider.close()


if __name__ == "__main__":
    raise SystemExit(main())
