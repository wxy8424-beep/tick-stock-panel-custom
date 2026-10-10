"""Derived health view; contract metadata remains the only capability authority."""
from datetime import UTC, datetime

from app.data_providers.contracts import CAPABILITY_STATUSES, MARKETS
from app.market_session import market_from_symbol

LABELS = {
    "supported": "可用", "contract_blocked": "契约阻塞", "empty": "无数据",
    "unsupported": "暂不支持", "unavailable": "运行时不可用", "entitlement_denied": "运行时不可用",
}
MESSAGES = {
    "candlestick_volume_unit_evidence_missing": "日K成交量缺少市场与端点对应的官方单位证据,不能安全转换",
    "minute_candlestick_volume_unit_evidence_missing": "分钟K成交量缺少市场与端点对应的官方单位证据,不能安全转换",
    "depth_volume_unit_evidence_missing": "盘口挂单量缺少市场与端点对应的官方单位证据,不能安全转换",
    "report_period_timestamp_unit_unverified": "报告期时间戳单位、编码及时区证据不足,不能安全生成报告期日期",
    "representative_financial_response_empty": "已验证代表标的当前无财务数据",
    "no_independent_adjustment_factor_series": "无独立除权因子序列",
    "no_safe_full_market_bulk_minute_contract": "无可靠全市场批量分钟契约",
    "upstream_available": "上游请求成功,仍需满足数据契约",
    "empty_response": "请求成功,当前标的无数据",
    "sdk_method_unavailable": "当前SDK不支持此请求方法",
    "sdk_missing": "SDK未安装或无法加载",
    "financial_context_unavailable": "行情上下文初始化失败",
    "financial_authentication_unavailable": "当前认证不可用",
    "financial_permission_denied": "当前请求权限不足",
    "financial_market_entitlement_unavailable": "当前市场数据权限不可用",
    "financial_market_unavailable": "当前接口不支持该市场请求",
    "financial_rate_limited": "接口限流,请稍后再试",
    "financial_network_unavailable": "当前网络连接不可用",
    "financial_upstream_error": "上游接口返回错误",
    "financial_sdk_exception": "SDK请求异常",
    "financial_parse_error": "响应适配失败,不能安全使用",
    "not_checked": "本进程尚无诊断记录",
    "diagnostic_unknown": "诊断状态尚未确认",
}


def runtime_snapshot(symbol: str, result: dict, dataset: str) -> dict:
    """Whitelist codes only; never copy raw SDK messages, rows or error objects."""
    if dataset == "financial":
        code = result.get("diagnostic", {}).get("reason", "diagnostic_unknown")
    else:
        code = {
            "success": "upstream_available", "empty": "empty_response", "method_missing": "sdk_method_unavailable",
            "sdk_missing": "sdk_missing", "authentication": "financial_authentication_unavailable",
            "entitlement_denied": "financial_market_entitlement_unavailable", "network": "financial_network_unavailable",
            "sdk_exception": "financial_sdk_exception", "response_shape_mismatch": "financial_parse_error",
        }.get(result.get("request_status"), "diagnostic_unknown")
    code = code if isinstance(code, str) and code in MESSAGES else "diagnostic_unknown"
    availability = "available" if code == "upstream_available" else "empty" if code == "empty_response" else "unavailable"
    market = market_from_symbol(symbol)
    # Symbol is optional display context; never accept arbitrary text as metadata.
    safe_symbol = symbol if market in MARKETS and len(symbol) <= 32 and symbol.isascii() and all(c.isalnum() or c == "." for c in symbol) else None
    return {"availability": availability, "diagnostic_code": code, "message": MESSAGES[code],
            "last_checked": datetime.now(UTC).isoformat(), "symbol": safe_symbol}


def build_health(metadata: dict, datasets, snapshots: dict, available: bool) -> dict:
    result = {}
    for dataset, markets in metadata.items():
        result[dataset] = {}
        for market in MARKETS:
            entry = markets.get(market, {})
            status = entry.get("status")
            status = status if status in CAPABILITY_STATUSES else "contract_blocked"
            reason = entry.get("reason")
            reason = reason if isinstance(reason, str) and reason in MESSAGES else None
            runtime = dict(snapshots.get((dataset, market)) or {
                "availability": "not_checked", "diagnostic_code": "not_checked", "message": MESSAGES["not_checked"],
                "last_checked": None, "symbol": None,
            })
            result[dataset][market] = {
                "provider": "longbridge", "market": market, "capability": dataset,
                "status": status, "status_label": LABELS[status], "reason": reason,
                "message": MESSAGES.get(reason, "" if status == "supported" else "能力契约尚未满足"),
                "usable": status == "supported" and dataset in datasets and available and runtime["availability"] not in {"unavailable", "empty"} and runtime.get("runtime_status", "healthy") == "healthy",
                "runtime": runtime,
            }
    return result
