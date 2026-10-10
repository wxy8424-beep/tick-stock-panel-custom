"""官方 quote 批量快照, 不提供历史、盘口或交易能力。

引用: https://open.longbridge.com/zh-CN/docs/quote/pull/quote
币种来自 static_info, 不从市场猜测。CN volume 单位未确认时明确不支持;
QuoteService 必须 fail closed, 不能把 None 填零后写入 CN daily。
"""
from __future__ import annotations

import importlib
import logging
import math
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.market_session import market_from_symbol

logger = logging.getLogger(__name__)
_ENV_NAMES = ("LONGBRIDGE_APP_KEY", "LONGBRIDGE_APP_SECRET", "LONGBRIDGE_ACCESS_TOKEN")
MAX_SYMBOLS = 500


def _credentials() -> tuple[str, ...]:
    from dotenv import dotenv_values

    from app import secrets_store
    from app.config import _ENV_FILE

    stored = secrets_store.load()
    fields = tuple(name.lower() for name in _ENV_NAMES)
    if any(field in stored for field in fields):
        # 不把部分本地 bundle 与旧环境变量拼在一起。
        return tuple(str(stored.get(field) or "").strip() for field in fields)
    values = dotenv_values(_ENV_FILE)
    return tuple(str(os.environ.get(key) or values.get(key) or "").strip() for key in _ENV_NAMES)


def credential_status() -> dict:
    from app import secrets_store

    key, secret, token = _credentials()
    try:
        _sdk()
        sdk_available = True
    except Exception:
        sdk_available = False
    return {
        "app_key_masked": secrets_store.mask(key),
        "app_secret_configured": bool(secret), "access_token_configured": bool(token),
        "status": "sdk_missing" if not sdk_available else "available" if all((key, secret, token)) else "unconfigured",
    }


def probe_credentials(credentials: tuple[str, ...]) -> tuple[bool, str]:
    """只探候选 bundle, 不读取/覆盖现有凭证; 固定错误分类。"""
    if len(credentials) != 3 or not all(credentials):
        return False, "unconfigured"
    try:
        sdk = _sdk()
    except Exception:
        return False, "sdk_missing"
    context = None
    try:
        config = sdk.Config.from_apikey(
            *credentials, enable_print_quote_packages=False, enable_overnight=False,
        )
        context = sdk.QuoteContext(config)
        rows = context.quote(["700.HK"])
        if not rows or not any(row.symbol == "700.HK" and _number(row.last_done) > 0 for row in rows):
            return False, "sdk_or_response"
        return True, "available"
    except Exception as error:
        return False, error_category(error)
    finally:
        context = None


def _sdk():
    return importlib.import_module("longbridge.openapi")


def availability() -> tuple[bool, str]:
    """只检查安装和凭证存在, 不创建 context、不探测账户或行情权限。"""
    try:
        _sdk()
        if not all(_credentials()):
            return False, "缺少 Longbridge 三项环境凭证"
        return True, "ok"
    except Exception:
        return False, "Longbridge SDK 或本地凭证配置不可用"


def error_category(error: Exception) -> str:
    """仅返回固定分类, 不把 SDK exception/请求内容写入日志或 API。"""
    code = getattr(error, "code", None)
    if code in {401003, 403201, 403203, 403205}:
        return "authentication"
    message = str(error).lower()
    if any(word in message for word in ("token", "credential", "unauthorized", "signature")):
        return "authentication"
    if any(word in message for word in ("permission", "package", "entitlement", "access denied")):
        return "quote_permission"
    if any(word in message for word in ("symbol", "security not found")):
        return "symbol"
    if any(word in message for word in ("connect", "timeout", "dns", "network", "socket")):
        return "network"
    return "sdk_or_response"


def _number(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("invalid numeric field")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("non-finite numeric field")
    return result


@dataclass
class _Config:
    name: str = "longbridge"
    display_name: str = "Longbridge"
    datasets: dict = field(default_factory=lambda: {"realtime": None})
    path: None = None


class LongbridgeProvider:
    name = "longbridge"
    builtin = True
    # 数据源是按码请求, 不能冒充全市场成功或覆盖完整 CN 分区。
    realtime_snapshot_scope = "symbols"
    cn_volume_supported = False

    @property
    def market_capabilities(self) -> dict:
        from app.plugins.longbridge.financial import market_capabilities

        return market_capabilities()

    def __init__(self):
        self.config = _Config()
        self._lock = threading.Lock()
        self._context = None
        self._dashboard_contexts: dict[str, object] = {}
        self._metadata: dict[str, dict] = {}
        self.last_errors: list[dict] = []

    def close(self) -> None:
        with self._lock:
            # SDK 5.2.0 无公开 close; 最后一个 Python 引用释放 Rust context。
            self._context = None
            self._dashboard_contexts.clear()
            self._metadata.clear()

    def _get_context(self):
        if self._context is None:
            credentials = _credentials()
            if not all(credentials):
                raise ValueError("missing credential configuration")
            sdk = _sdk()
            config = sdk.Config.from_apikey(
                *credentials, enable_print_quote_packages=False, enable_overnight=False,
            )
            self._context = sdk.QuoteContext(config)
        return self._context

    def dashboard_request(self, kind: str, method: str, *args, **kwargs):
        """Allowlisted read-only Dashboard calls; reuse credentials and contexts.

        These are not TSP datasets: the plugin remains realtime-only.
        The existing lock serializes SDK calls with realtime polling.
        """
        allowed = {
            "quote": {"quote", "static_info", "capital_flow", "option_volume"},
            "market": {"top_movers"},
            "fundamental": {"dividend_detail", "financial_report"},
        }
        if method not in allowed.get(kind, set()):
            raise ValueError("unsupported read-only dashboard method")
        with self._lock:
            if kind == "quote":
                context = self._get_context()
            else:
                if kind not in self._dashboard_contexts:
                    credentials = _credentials()
                    if not all(credentials):
                        raise ValueError("missing credential configuration")
                    sdk = _sdk()
                    config = sdk.Config.from_apikey(
                        *credentials, enable_print_quote_packages=False, enable_overnight=False,
                    )
                    context_type = sdk.MarketContext if kind == "market" else sdk.FundamentalContext
                    self._dashboard_contexts[kind] = context_type(config)
                context = self._dashboard_contexts[kind]
            return getattr(context, method)(*args, **kwargs)

    def probe_financial_contract(self, symbol: str) -> dict:
        """Read-only financial report contract check, not an enabled financial dataset.

        Returns fixed classifications and field names only, never raw SDK errors/data.
        Does not update capability declarations or write candidates to any repository.
        """
        from app.plugins.longbridge.financial import assess_financial_contract

        market = market_from_symbol(symbol)
        if market is None:
            return {"status": "unsupported", "reason": "unknown_market"}
        try:
            response = self.dashboard_request("fundamental", "financial_report", symbol)
        except ImportError:
            return {"status": "unavailable", "reason": "sdk_missing", "sdk_available": False}
        except Exception as error:
            category = error_category(error)
            reason = "financial_network_unavailable" if category == "network" else (
                "requires_us_token_or_market_context" if market == "US" else "financial_request_unavailable"
            )
            return {"status": "unavailable", "reason": reason, "sdk_available": True}
        try:
            return assess_financial_contract(symbol, response)
        except ValueError as error:
            reason = "financial_period_end_type_invalid" if error.args == ("financial_period_end_type_invalid",) else "financial_response_shape_mismatch"
            return {"status": "contract_blocked", "reason": reason, "sdk_available": True}
        except (TypeError, AttributeError, KeyError):
            return {"status": "contract_blocked", "reason": "financial_response_shape_mismatch", "sdk_available": True}

    def probe_quantity_contract(self, symbol: str, dataset: str) -> dict:
        from app.plugins.longbridge.quantity import probe_quantity_contract

        return probe_quantity_contract(self, symbol, dataset)

    @staticmethod
    def configured_symbols() -> list[str]:
        from app.services import preferences, watchlist

        configured = preferences.load().get("longbridge_realtime_symbols", [])
        if not isinstance(configured, list):
            configured = []
        symbols = [*configured, *(row["symbol"] for row in watchlist.list_symbols())]
        return list(dict.fromkeys(s for s in symbols if market_from_symbol(s) is not None))

    def get_realtime_universe(self, market: str) -> list[str]:
        """Official available securities, not an exchange-completeness guarantee."""
        if market != "US":
            raise ValueError("unsupported universe market")
        with self._lock:
            return [row.symbol for row in self._get_context().security_list(_sdk().Market.US)]

    def _normalize(self, quote) -> dict:
        symbol = quote.symbol
        market = market_from_symbol(symbol)
        if market is None:
            raise ValueError("unsupported symbol")
        price = _number(quote.last_done)
        if price is None or price <= 0:
            raise ValueError("invalid last price")
        previous = _number(quote.prev_close)
        timestamp = quote.timestamp
        if not isinstance(timestamp, datetime):
            raise ValueError("timestamp must be an SDK datetime")
        # SDK v5.2.0 python/src/time.rs 使用 from_timestamp(epoch, None):
        # 返回本机 local naive datetime (含 fold), timestamp() 是对应逆变换。
        # aware datetime 同样按绝对时间转换; 不按 CN/HK/US 后缀猜时区。
        timestamp_ms = int(timestamp.timestamp() * 1000)
        if timestamp_ms <= 0:
            raise ValueError("invalid timestamp")
        metadata = self._metadata.get(symbol, {})
        return {
            "symbol": symbol, "market": market, "last_price": price,
            "prev_close": previous, "open": _number(quote.open),
            "high": _number(quote.high), "low": _number(quote.low),
            "amount": _number(quote.turnover),
            "change_pct": (price - previous) / previous if previous and previous > 0 else None,
            "timestamp": timestamp_ms, "currency": metadata.get("currency"),
            "name": metadata.get("name"), "volume": None,
            "volume_unit": "unverified" if market == "CN" else "unsupported",
        }

    def get_realtime(self, symbols: list[str] | None = None) -> list[dict]:
        """批次失败隔离, 返回成功报价; 不输出异常原文或重试到其他数据源。"""
        symbols = self.configured_symbols() if symbols is None else symbols
        wanted = list(dict.fromkeys(s for s in symbols if market_from_symbol(s) is not None))
        if not wanted:
            return []
        rows: dict[str, dict] = {}
        with self._lock:
            self.last_errors = []
            try:
                context = self._get_context()
            except Exception as error:
                self.last_errors.append({"stage": "context", "reason": error_category(error)})
                logger.warning("Longbridge context unavailable: %s", self.last_errors[-1]["reason"])
                return []
            for offset in range(0, len(wanted), MAX_SYMBOLS):
                chunk = wanted[offset:offset + MAX_SYMBOLS]
                try:
                    quotes = context.quote(chunk)
                except Exception as error:
                    self.last_errors.append({"stage": "quote", "batch": offset // MAX_SYMBOLS,
                                             "reason": error_category(error)})
                    logger.warning("Longbridge quote batch failed: %s", self.last_errors[-1]["reason"])
                    continue
                missing = [s for s in chunk if s not in self._metadata]
                if missing:
                    try:
                        for info in context.static_info(missing):
                            if info.symbol in missing:
                                currency = info.currency
                                self._metadata[info.symbol] = {
                                    "currency": currency if isinstance(currency, str) and currency else None,
                                    "name": info.name_cn or info.name_en or None,
                                }
                    except Exception as error:
                        self.last_errors.append({"stage": "metadata", "batch": offset // MAX_SYMBOLS,
                                                 "reason": error_category(error)})
                        logger.warning("Longbridge metadata unavailable: %s", self.last_errors[-1]["reason"])
                rejected = 0
                for quote in quotes or []:
                    try:
                        if quote.symbol not in chunk:
                            raise ValueError("unexpected symbol")
                        row = self._normalize(quote)
                        rows[row["symbol"]] = row
                    except (AttributeError, ValueError, TypeError, OverflowError, OSError):
                        rejected += 1
                if rejected:
                    self.last_errors.append({"stage": "rows", "batch": offset // MAX_SYMBOLS,
                                             "rejected": rejected, "reason": "invalid_response_fields"})
                    logger.debug("Longbridge quote batch rejected %d invalid rows", rejected)
        return list(rows.values())

    def get_realtime_for_markets(self, markets: list[str]) -> list[dict]:
        symbols = [s for s in self.configured_symbols() if market_from_symbol(s) in markets]
        return self.get_realtime(symbols)

    def test_dataset(self, dataset: str, symbols=None) -> dict:
        if dataset != "realtime":
            return {"provider": self.name, "dataset": dataset, "rows": 0,
                    "error": "仅提供 realtime"}
        rows = self.get_realtime(symbols)
        return {"provider": self.name, "dataset": dataset, "rows": len(rows),
                "columns": list(rows[0]) if rows else [], "preview": rows[:5],
                "errors": list(self.last_errors)}
