"""CN Daily/none fallback only; isolated SDK process avoids its global socket state."""
from __future__ import annotations

import io
import json
import subprocess
import sys
from contextlib import redirect_stdout
from dataclasses import replace

from app.data_providers.historical import AKShareDailyProvider, _DataError, _HistoricalProvider

FIELDS = ("date", "code", "open", "high", "low", "close", "tradestatus", "adjustflag")
TRANSPORT_FAILURES = {"network_error", "network_timeout", "http_unavailable"}


def _sdk_rows(ticker, start, end):
    import baostock as bs

    logged_in = False
    try:
        with redirect_stdout(io.StringIO()):
            login = bs.login()
            logged_in = login.error_code == "0"
            if not logged_in:
                return {"error": "baostock_login_unavailable"}
            result = bs.query_history_k_data_plus(ticker, ",".join(FIELDS),
                                                 start_date=start, end_date=end, frequency="d", adjustflag="3")
            if result.error_code != "0":
                return {"error": "baostock_query_unavailable"}
            if result.fields != list(FIELDS):
                return {"error": "response_shape_mismatch"}
            rows = []
            while result.error_code == "0" and result.next():
                rows.append(dict(zip(result.fields, result.get_row_data(), strict=True)))
                if len(rows) >= 10000:
                    return {"error": "baostock_bounded_query_required"}
            if result.error_code != "0":
                return {"error": "baostock_query_unavailable"}
            return {"rows": rows}
    except Exception:
        return {"error": "baostock_sdk_failure"}
    finally:
        if logged_in:
            with redirect_stdout(io.StringIO()):
                bs.logout()


def _read_isolated(ticker, start, end):
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "app.data_providers.baostock_daily", ticker, start.isoformat(), end.isoformat()],
            capture_output=True, text=True, encoding="utf-8", timeout=40, check=True,
        )
    except subprocess.TimeoutExpired:
        raise TimeoutError("baostock request deadline") from None
    except (subprocess.CalledProcessError, OSError):
        raise _DataError("baostock_process_unavailable") from None
    try:
        payload = json.loads(completed.stdout)
    except (ValueError, TypeError):
        raise _DataError("response_shape_mismatch") from None
    if not isinstance(payload, dict):
        raise _DataError("response_shape_mismatch")
    if "error" in payload:
        allowed = {"baostock_login_unavailable", "baostock_query_unavailable", "baostock_bounded_query_required",
                   "baostock_sdk_failure", "response_shape_mismatch"}
        raise _DataError(payload["error"] if payload["error"] in allowed else "response_shape_mismatch")
    return payload.get("rows")


class BaoStockDailyProvider(_HistoricalProvider):
    market, source = "CN", "baostock"
    raw_method, adjusted_method, volume_unit = "none", None, "unknown"

    def __init__(self, reader=_read_isolated):
        self.reader = reader

    def _ticker(self, symbol):
        code = AKShareDailyProvider()._ticker(symbol)
        return f"{symbol.split('.')[1].lower()}.{code}"

    def fetch_daily(self, symbol, start_date, end_date, price_mode="raw"):
        if price_mode == "adjusted":
            raise ValueError("BaoStock fallback supports Daily/none only")
        return super().fetch_daily(symbol, start_date, end_date, price_mode)

    def _read(self, ticker, start, end, adjusted):
        import pandas as pd

        rows = self.reader(ticker, start, end)
        if not isinstance(rows, list) or any(not isinstance(row, dict) or set(row) != set(FIELDS) for row in rows):
            raise _DataError("response_shape_mismatch")
        selected = []
        seen = set()
        for row in rows:
            if row["code"] != ticker or row["adjustflag"] != "3" or row["tradestatus"] not in {"0", "1"}:
                raise _DataError("baostock_semantics_conflict")
            if row["date"] in seen:
                raise _DataError("duplicate_trading_date")
            seen.add(row["date"])
            # Suspended records are not completed trading bars; never fill their prices.
            if row["tradestatus"] == "1":
                selected.append({"日期": row["date"], "股票代码": ticker.split(".")[1],
                                 **{key: row[key] for key in ("open", "high", "low", "close")}})
        return pd.DataFrame(selected), "CNY", {key: key for key in ("open", "high", "low", "close")}, False


class CNHistoricalProvider:
    """Two explicit sources; semantic/schema/programming failures never trigger failover."""

    def __init__(self, primary=None, fallback=None):
        self.primary = primary if primary is not None else AKShareDailyProvider()
        self.fallback = fallback if fallback is not None else BaoStockDailyProvider()

    def fetch_daily(self, symbol, start_date, end_date, price_mode="raw"):
        primary = self.primary.fetch_daily(symbol, start_date, end_date, price_mode)
        if (price_mode != "raw" or primary.status != "unavailable" or not primary.frame.is_empty()
                or not primary.diagnostics or any(item["code"] not in TRANSPORT_FAILURES for item in primary.diagnostics)):
            return primary
        fallback = self.fallback.fetch_daily(symbol, start_date, end_date, price_mode)
        primary_codes = [item.get("classification", item["code"]) for item in primary.diagnostics]
        diagnostics = (
            *({**item, "source": primary.source} for item in primary.diagnostics),
            {"code": "primary_attempt", "source": primary.source, "result": primary_codes},
            {"code": "fallback_attempt", "source": fallback.source, "result": fallback.status},
            {"code": "fallback_used", "source": fallback.source, "scope": "CN_daily_none"},
            *({**item, "source": fallback.source} for item in fallback.diagnostics),
        )
        return replace(fallback, diagnostics=diagnostics,
                       status=fallback.status if fallback.status in {"completed", "partial"} and not fallback.frame.is_empty() else "unavailable")


if __name__ == "__main__":
    print(json.dumps(_sdk_rows(*sys.argv[1:]), allow_nan=False))
