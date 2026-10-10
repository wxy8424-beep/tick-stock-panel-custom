"""Confirmed FinancialReports fields only; report timestamp units remain unverified."""
from decimal import Decimal, InvalidOperation

FIELDS = {
    "IS": {"OperatingRevenue": "revenue", "NetProfit": "net_income"},
    "BS": {"TotalAssets": "total_assets", "TotalLiability": "total_liabilities", "BPS": "bps"},
    "CF": {
        "NetOperateCashFlow": "net_operating_cash_flow",
        "NetInvestCashFlow": "net_investing_cash_flow",
        "NetFinanceCashFlow": "net_financing_cash_flow",
    },
}


def decimal_value(value):
    if value is None or value == "":
        return None
    # Float input is not an authoritative decimal representation.
    if isinstance(value, (float, bool)):
        raise ValueError("invalid_financial_number")
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("invalid_financial_number") from None
    if not result.is_finite():
        raise ValueError("invalid_financial_number")
    return result


def financial_candidates(symbol: str, response) -> list[dict]:
    """Produce mapping candidates, NOT persistence-ready financial dataset rows.

    fp_end is upstream report-period-end timestamp, not announcement date.
    No seconds/milliseconds contract is established, so required period_end stays null.
    """
    reports = response.get("list", {}) if isinstance(response, dict) else getattr(response, "list", {})
    if not isinstance(reports, dict):
        raise ValueError("financial_response_shape_mismatch")
    rows = {}
    for kind, mapping in FIELDS.items():
        for indicator in (reports.get(kind) or {}).get("indicators", []):
            currency = indicator.get("currency")
            for account in indicator.get("accounts", []):
                target = mapping.get(account.get("field"))
                if target is None or account.get("percent"):
                    continue
                for value in account.get("values", []):
                    key = (kind, currency, value.get("year"), value.get("period"), value.get("fp_end"))
                    row = rows.setdefault(key, {
                        "symbol": symbol, "statement": kind, "currency": currency,
                        "fiscal_year": value.get("year"), "source_period": value.get("period"),
                        "source_fp_end": value.get("fp_end"), "period_end": None, "announce_date": None,
                    })
                    row[target] = decimal_value(value.get("value"))
    return list(rows.values())


def financial_rows_ready(rows: list[dict]) -> bool:
    return bool(rows) and all(row.get("symbol") and row.get("period_end") is not None for row in rows)


def market_capabilities() -> dict:
    result = {}
    for dataset, status, reason in (
        ("realtime", "supported", None),
        ("daily", "contract_blocked", "quantity_unit_unknown"),
        ("minute", "contract_blocked", "quantity_unit_unknown"),
        ("depth5", "contract_blocked", "quantity_unit_unknown"),
        ("adj_factor", "unsupported", "no_independent_adjustment_factor_series"),
        ("full_minute", "unsupported", "no_safe_full_market_bulk_minute_contract"),
    ):
        result[dataset] = {
            market: {"status": status, "reason": reason, "quantity_unit": "unknown"}
            for market in ("CN", "HK", "US")
        }
    result["financial"] = {
        "CN": {"status": "empty", "reason": "representative_financial_response_empty", "sdk_available": True},
        "HK": {"status": "contract_blocked", "reason": "report_period_timestamp_unit_unverified", "sdk_available": True},
        "US": {"status": "unavailable", "reason": "requires_us_token_or_market_context", "sdk_available": True},
    }
    return result
