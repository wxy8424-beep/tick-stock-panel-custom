"""Confirmed FinancialReports fields only; report timestamp units remain unverified."""
from datetime import date
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


def inspect_period_end(value) -> dict:
    """Inspect wire type only; no date parsing without encoding/timezone evidence.

    Official FinancialValue schema says optional string report-period-end timestamp.
    SDK 5.2.0 preserves raw JSON. Neither numeric length nor date-looking text proves
    an encoding, epoch unit, or business timezone. No original value is returned.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        reason = "financial_period_end_missing"
        source_type = "null" if value is None else "string"
    elif not isinstance(value, str):
        reason = "financial_period_end_type_invalid"
        source_type = "non_string"
    else:
        reason = "report_period_timestamp_unit_unverified"
        source_type = "string"
    return {
        "status": "contract_blocked", "reason": reason, "source_type": source_type,
        "encoding": "unverified", "unit": "unverified", "timezone": "unverified",
        "period_end": None,
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
    reports = response.get("list") if isinstance(response, dict) else getattr(response, "list", None)
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
                    source_end = value.get("fp_end")
                    if inspect_period_end(source_end)["reason"] == "financial_period_end_type_invalid":
                        raise ValueError("financial_period_end_type_invalid")
                    key = (kind, currency, value.get("year"), value.get("period"), source_end)
                    row = rows.setdefault(key, {
                        "symbol": symbol, "statement": kind, "currency": currency,
                        "fiscal_year": value.get("year"), "source_period": value.get("period"),
                        "source_fp_end": value.get("fp_end"), "period_end": None, "announce_date": None,
                        **dict.fromkeys(mapping.values()),
                    })
                    row[target] = decimal_value(value.get("value"))
    return list(rows.values())


def financial_rows_ready(rows: list[dict]) -> bool:
    if not rows:
        return False
    for row in rows:
        if not row.get("symbol") or not isinstance(row.get("period_end"), str):
            return False
        try:
            if date.fromisoformat(row["period_end"]).isoformat() != row["period_end"]:
                return False
        except ValueError:
            return False
    return True


def assess_financial_contract(symbol: str, response) -> dict:
    """Only a safe summary. Candidates remain disconnected from persistence/routing.

    Existing project history requires symbol + ISO period_end; announcement date,
    EPS and indicator values are nullable. Source timestamp unit is not established.
    """
    rows = financial_candidates(symbol, response)
    reports = response.get("list") if isinstance(response, dict) else response.list
    if not reports:
        return {"status": "empty", "reason": "representative_financial_response_empty", "sdk_available": True}
    fields = sorted({
        name for row in rows for mapping in FIELDS.values() for name in mapping.values()
        if row.get(name) is not None
    })
    period_evidence = [inspect_period_end(row["source_fp_end"]) for row in rows]
    return {
        "status": "contract_blocked",
        "reason": "report_period_timestamp_unit_unverified" if rows else "financial_fields_unmapped",
        "sdk_available": True,
        "required_fields": ["symbol", "period_end"],
        "unresolved_required_fields": ["period_end"],
        "currencies": sorted({row["currency"] for row in rows if row.get("currency")}),
        "available_statements": sorted({row["statement"] for row in rows}),
        "mapped_fields": fields,
        "missing_optional_fields": ["announce_date", "basic_eps", "diluted_eps", "yoy", "ratio"],
        "period_end_evidence": {
            "source_field": "fp_end", "semantic": "report_period_end_timestamp",
            "encoding": "unverified", "unit": "unverified", "timezone": "unverified",
            "source_types": sorted({item["source_type"] for item in period_evidence}),
            "blockers": sorted({item["reason"] for item in period_evidence}),
            "conversion_performed": False,
        },
    }


def market_capabilities() -> dict:
    from app.plugins.longbridge.quantity import quantity_capabilities

    result = {}
    for dataset, status, reason in (
        ("realtime", "supported", None),
        ("adj_factor", "unsupported", "no_independent_adjustment_factor_series"),
        ("full_minute", "unsupported", "no_safe_full_market_bulk_minute_contract"),
    ):
        result[dataset] = {
            market: {"status": status, "reason": reason, "quantity_unit": "unknown"}
            for market in ("CN", "HK", "US")
        }
    result.update(quantity_capabilities())
    result["financial"] = {
        "CN": {"status": "empty", "reason": "representative_financial_response_empty", "sdk_available": True},
        "HK": {"status": "contract_blocked", "reason": "report_period_timestamp_unit_unverified", "sdk_available": True},
        "US": {"status": "contract_blocked", "reason": "report_period_timestamp_unit_unverified", "sdk_available": True},
    }
    return result
