"""Price-only buy-and-hold research analytics; no execution or rebalancing."""
from __future__ import annotations

import math
import statistics
from copy import deepcopy
from datetime import date

import polars as pl

from app.factors.engine import DailyHistory
from app.market_session import market_from_symbol


class PortfolioAnalytics:
    def analyze(self, portfolio: dict, repository: DailyHistory, *, start: date, end: date,
                expected_dates: tuple[date, ...] | None = None,
                periods_per_year: int = 252, annual_risk_free_rate: float = 0.0) -> dict:
        if type(start) is not date or type(end) is not date or start > end:
            raise ValueError("ordered Date range required")
        if isinstance(periods_per_year, bool) or not isinstance(periods_per_year, int) or not 1 <= periods_per_year <= 366:
            raise ValueError("explicit positive annualization frequency required")
        if isinstance(annual_risk_free_rate, bool) or not isinstance(annual_risk_free_rate, (int, float)) or not math.isfinite(annual_risk_free_rate) or annual_risk_free_rate <= -1:
            raise ValueError("finite annual risk-free rate greater than -1 required")
        symbols = tuple(portfolio.get("selected_symbols", ()))
        weights = portfolio.get("weights", {})
        if len(symbols) > 100 or len(set(symbols)) != len(symbols) or set(symbols) != set(weights):
            raise ValueError("selected symbols must match unique weights")
        if any(market_from_symbol(symbol) is None for symbol in symbols) or any(
            isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight)
            or not 0 < weight <= 1 for weight in weights.values()
        ) or (symbols and not math.isclose(math.fsum(weights.values()), 1, rel_tol=0, abs_tol=1e-12)):
            raise ValueError("known symbols and positive weights summing to one required")
        if expected_dates is not None and (
            any(type(day) is not date or not start <= day <= end for day in expected_dates)
            or tuple(sorted(set(expected_dates))) != tuple(expected_dates)
        ):
            raise ValueError("expected dates must be unique ordered Dates in range")
        result = {"status": "blocked", "weights": dict(weights),
                  "positions": [{"symbol": symbol, "initial_weight": weights[symbol]} for symbol in symbols],
                  "factor_score_summary": deepcopy(portfolio.get("score_summary", {})),
                  "start": start.isoformat(), "end": end.isoformat(),
                  "assumptions": {"model": "buy_and_hold", "price_basis": "as_provided",
                                  "return_basis": "price_only_no_dividends_fees_or_fx",
                                  "periods_per_year": periods_per_year,
                                  "annual_risk_free_rate": annual_risk_free_rate,
                                  "volatility_ddof": 1, "calendar_source": "caller_expected_dates"},
                  "total_return": None, "daily_return": [], "annualized_return": None,
                  "volatility": None, "max_drawdown": None, "sharpe_ratio": None,
                  "blockers": []}
        if not symbols:
            result.update(status="empty", blockers=[{"code": "empty_portfolio"}])
            return result
        if expected_dates is None:
            result["blockers"].append({"code": "expected_dates_unknown"})
            return result
        if len(expected_dates) < 2:
            result["blockers"].append({"code": "insufficient_price_dates"})
            return result
        source_date = portfolio.get("source_scores", {}).get("as_of")
        try:
            score_date = date.fromisoformat(source_date)
        except (TypeError, ValueError):
            result["blockers"].append({"code": "selection_date_unknown"})
            return result
        if score_date > expected_dates[0]:
            result["blockers"].append({"code": "selection_after_analysis_start"})
            return result
        if len({market_from_symbol(symbol) for symbol in symbols}) > 1:
            result["blockers"].append({"code": "mixed_market_fx_unresolved"})
            return result
        prices = {}
        for symbol in symbols:
            try:
                frame = repository.get_daily_asset("stock", symbol, start, end, columns=["symbol", "date", "close"])
                if frame.is_empty():
                    result["blockers"].append({"symbol": symbol, "code": "history_empty"})
                    continue
                if not {"symbol", "date", "close"} <= set(frame.columns) or frame.schema["date"] != pl.Date or not frame.schema["close"].is_numeric():
                    result["blockers"].append({"symbol": symbol, "code": "history_schema_unknown"})
                    continue
                frame = frame.filter((pl.col("symbol") == symbol) & pl.col("date").is_between(start, end)).sort("date")
                days = frame["date"].to_list()
                if len(days) != len(set(days)):
                    result["blockers"].append({"symbol": symbol, "code": "duplicate_price_date"})
                    continue
                if days != list(expected_dates):
                    result["blockers"].append({"symbol": symbol, "code": "price_dates_incomplete_or_conflicting",
                                               "missing_dates": [day.isoformat() for day in expected_dates if day not in days]})
                    continue
                values = frame["close"].to_list()
                if any(value is None or not math.isfinite(value) or value <= 0 for value in values):
                    result["blockers"].append({"symbol": symbol, "code": "invalid_price"})
                    continue
                prices[symbol] = values
            except Exception:
                result["blockers"].append({"symbol": symbol, "code": "history_read_error"})
        if result["blockers"]:
            return result
        try:
            relative = {symbol: [value / prices[symbol][0] for value in prices[symbol]] for symbol in symbols}
            if any(not math.isfinite(value) or value <= 0 for values in relative.values() for value in values):
                raise ValueError("nonfinite relative price")
            nav = [math.fsum(weights[symbol] * relative[symbol][i] for symbol in symbols)
                   for i in range(len(expected_dates))]
            if any(not math.isfinite(value) or value <= 0 for value in nav):
                raise ValueError("nonfinite normalized NAV")
            daily = [nav[i] / nav[i - 1] - 1 for i in range(1, len(nav))]
            if any(not math.isfinite(value) for value in daily):
                raise ValueError("nonfinite returns")
        except (ValueError, OverflowError, ZeroDivisionError):
            result["blockers"].append({"code": "price_arithmetic_unavailable"})
            return result
        result.update(status="completed", total_return=nav[-1] / nav[0] - 1)
        result["daily_return"] = [{"date": day.isoformat(), "nav": value,
                                   "return": None if i == 0 else daily[i - 1]}
                                  for i, (day, value) in enumerate(zip(expected_dates, nav, strict=True))]
        peak, drawdown = nav[0], 0.0
        for value in nav:
            peak = max(peak, value)
            drawdown = min(drawdown, value / peak - 1)
        result["max_drawdown"] = drawdown  # Signed decimal drawdown, not percent.
        try:
            annual = math.expm1(math.log(nav[-1] / nav[0]) * periods_per_year / len(daily))
            if not math.isfinite(annual):
                raise OverflowError
            result["annualized_return"] = annual
        except (OverflowError, ValueError):
            result["blockers"].append({"code": "annualized_return_unavailable"})
        if len(daily) < 2:
            result["blockers"].append({"code": "insufficient_returns_for_risk"})
        else:
            deviation = statistics.stdev(daily)
            volatility = deviation * math.sqrt(periods_per_year)
            if math.isfinite(volatility):
                result["volatility"] = volatility
            else:
                result["blockers"].append({"code": "volatility_arithmetic_unavailable"})
            if deviation > 0:
                risk_free = math.expm1(math.log1p(annual_risk_free_rate) / periods_per_year)
                sharpe = (statistics.mean(daily) - risk_free) / deviation * math.sqrt(periods_per_year)
                if math.isfinite(sharpe):
                    result["sharpe_ratio"] = sharpe
                else:
                    result["blockers"].append({"code": "sharpe_arithmetic_unavailable"})
            else:
                result["blockers"].append({"code": "zero_volatility_sharpe_undefined"})
        for position in result["positions"]:
            symbol = position["symbol"]
            position.update(start_price=prices[symbol][0], end_price=prices[symbol][-1],
                            price_return=relative[symbol][-1] - 1,
                            end_weight=weights[symbol] * relative[symbol][-1] / nav[-1])
        if result["blockers"]:
            result["status"] = "partial"
        return result
