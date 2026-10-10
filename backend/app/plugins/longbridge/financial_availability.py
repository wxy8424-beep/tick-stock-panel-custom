"""Internal read-only diagnostics; no raw errors, inferred dates or public enums."""
from app.market_session import market_from_symbol
from app.plugins.longbridge.financial import assess_financial_contract, financial_candidates


def classify_failure(error: Exception, stage: str) -> dict:
    # Code meanings: https://open.longbridge.com/zh-CN/docs/error-codes
    code = getattr(error, "code", None)
    code = code if type(code) is int and 0 <= code <= 999999 else None
    message = str(error).lower()  # Match only; never return or log exception text.
    if isinstance(error, ImportError):
        reason = "sdk_missing"
    elif code in {429001, 429002}:
        reason = "financial_rate_limited"
    elif code == 403205:
        reason = "financial_permission_denied"
    elif code in {401003, 403201, 403203} or any(s in message for s in (
        "unauthorized", "invalid token", "token expired", "credential", "signature", "us token",
    )):
        reason = "financial_authentication_unavailable"
    elif any(s in message for s in ("entitlement", "subscription", "package")):
        reason = "financial_market_entitlement_unavailable"
    elif any(s in message for s in ("permission", "access denied", "forbidden")):
        reason = "financial_permission_denied"
    elif any(s in message for s in ("unsupported market", "market not supported")):
        reason = "financial_market_unavailable"
    elif any(s in message for s in ("timeout", "connect", "dns", "network", "socket")):
        reason = "financial_network_unavailable"
    elif stage == "context":
        reason = "financial_context_unavailable"
    elif type(error).__name__ == "OpenApiException":
        reason = "financial_upstream_error"
    else:
        reason = "financial_sdk_exception"
    exception_type = type(error).__name__
    safe_type = exception_type if exception_type in {
        "OpenApiException", "ImportError", "ModuleNotFoundError", "RuntimeError", "ValueError",
        "TypeError", "AttributeError", "TimeoutError", "ConnectionError", "OSError",
    } else "OtherException"
    return {"reason": reason, "exception_class": safe_type, "error_code": code}


def probe_financial(provider, symbol: str) -> dict:
    market = market_from_symbol(symbol)
    if market is None:
        return {"status": "unsupported", "reason": "unknown_market"}
    diagnostic = {
        "context_status": "not_started", "method": "financial_report", "method_exists": None,
        "request_status": "not_entered", "response_shape": None, "row_count": None,
        "failure_stage": None,
    }
    with provider._lock:
        try:
            context = provider._get_dashboard_context("fundamental")
        except Exception as error:
            diagnostic.update(classify_failure(error, "context"), context_status="failed", failure_stage="context")
            return {"status": "unavailable", "reason": diagnostic["reason"],
                    "sdk_available": not isinstance(error, ImportError), "diagnostic": diagnostic}
        diagnostic["context_status"] = "ready"
        method = getattr(context, "financial_report", None)
        diagnostic["method_exists"] = callable(method)
        if not callable(method):
            diagnostic.update(reason="sdk_method_unavailable", failure_stage="method")
            return {"status": "unsupported", "reason": "sdk_method_unavailable", "sdk_available": True, "diagnostic": diagnostic}
        diagnostic["request_status"] = "entered_sdk"
        try:
            response = method(symbol)
        except Exception as error:
            diagnostic.update(classify_failure(error, "request"), request_status="sdk_raised", failure_stage="request")
            return {"status": "unavailable", "reason": diagnostic["reason"], "sdk_available": True, "diagnostic": diagnostic}
    diagnostic["request_status"] = "returned"
    # Only known type labels; supplier/class names are not arbitrary output strings.
    diagnostic["response_shape"] = "FinancialReports" if type(response).__name__ == "FinancialReports" else "dict" if isinstance(response, dict) else "object"
    try:
        summary = assess_financial_contract(symbol, response)
        diagnostic["row_count"] = len(financial_candidates(symbol, response))
    except (ValueError, TypeError, AttributeError, KeyError) as error:
        reason = "financial_period_end_type_invalid" if error.args == ("financial_period_end_type_invalid",) else "financial_response_shape_mismatch"
        diagnostic.update(reason="financial_parse_error", failure_stage="adapter")
        return {"status": "contract_blocked", "reason": reason, "sdk_available": True, "diagnostic": diagnostic}
    diagnostic["reason"] = "empty_response" if summary["status"] == "empty" else "upstream_available"
    return {**summary, "diagnostic": diagnostic}
