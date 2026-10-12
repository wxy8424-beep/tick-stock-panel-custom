"""Explicit offline historical strategy research; no broker or live execution."""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import date

import polars as pl

from app.data_providers.historical import HistoricalDailyProvider, get_historical_provider
from app.market_session import market_from_symbol
from app.services.portfolio_analytics import PortfolioAnalytics
from app.services.strategy_research import StrategyDefinition, StrategyResearchRunner


class _HistoryBlockedError(ValueError):
    pass


class HistoricalResearchHistory:
    """Adapter to existing DailyHistory with explicit calendar and read bounds.

    Every read has its own end bound. Revised overlapping prices fail closed;
    transport timestamps are excluded from deterministic result fingerprints.
    """

    def __init__(self, providers: Mapping[str, HistoricalDailyProvider], dates: tuple[date, ...]):
        self.providers, self.dates = providers, dates
        self.purpose = "signal"
        self.blockers, self.reads = [], []
        self._observations = {}
        self.currency = None

    def _block(self, symbol, start, end, code):
        self.blockers.append({"symbol": symbol, "start": start.isoformat(), "end": end.isoformat(), "code": code})
        raise _HistoryBlockedError(code)

    def get_daily_asset(self, asset_type, symbol, start, end, columns=None):
        if asset_type != "stock" or type(start) is not date or type(end) is not date or start > end:
            raise ValueError("explicit stock Date query required")
        if not self.dates or start < self.dates[0] or end > self.dates[-1]:
            self._block(symbol, start, end, "history_read_outside_grid")
        market = market_from_symbol(symbol)
        provider = self.providers.get(market)
        if provider is None:
            self._block(symbol, start, end, "historical_provider_missing")
        try:
            result = provider.fetch_daily(symbol, start, end, price_mode="raw")
        except Exception:
            self._block(symbol, start, end, "historical_provider_error")
        self.reads.append({"symbol": symbol, "start": start.isoformat(), "end": end.isoformat(),
                           "purpose": self.purpose, "price_mode": "raw", "source": result.source,
                           "diagnostics": sorted({item["code"] for item in result.diagnostics})})
        if result.status != "completed":
            self._block(symbol, start, end, "historical_" + result.status)
        if result.price_mode != "raw":
            self._block(symbol, start, end, "historical_price_mode_conflict")
        frame = result.frame
        required = {"symbol", "market", "trading_date", "open", "high", "low", "close",
                    "currency", "source", "adjustment_method"}
        if (not required <= set(frame.columns) or frame.schema["trading_date"] != pl.Date
                or frame.is_empty() or any(not frame.schema[key].is_numeric() for key in ("open", "high", "low", "close"))):
            self._block(symbol, start, end, "history_schema_or_empty")
        expected = [day for day in self.dates if start <= day <= end]
        if frame["trading_date"].to_list() != expected:
            self._block(symbol, start, end, "historical_dates_incomplete_or_conflicting")
        method = "none" if market == "CN" else "yfinance_auto_adjust_false"
        for row in frame.to_dicts():
            if (row["symbol"] != symbol or row["market"] != market or row["source"] != result.source
                    or row["adjustment_method"] != method or result.symbol != symbol or result.market != market):
                self._block(symbol, start, end, "historical_semantics_conflict")
            prices = tuple(row[key] for key in ("open", "high", "low", "close"))
            if (any(value is None or not math.isfinite(value) or value <= 0 for value in prices)
                    or not row["low"] <= min(row["open"], row["close"]) <= max(row["open"], row["close"]) <= row["high"]):
                self._block(symbol, start, end, "historical_invalid_price")
            currency = row["currency"]
            if not isinstance(currency, str) or not currency:
                self._block(symbol, start, end, "historical_currency_unknown")
            if self.currency is not None and self.currency != currency:
                self._block(symbol, start, end, "historical_currency_conflict")
            self.currency = currency
            key = (symbol, row["trading_date"])
            observation = (result.source, method, currency, *prices)
            if key in self._observations and self._observations[key] != observation:
                self._block(symbol, start, end, "historical_revision_during_run")
            self._observations[key] = observation
        frame = frame.rename({"trading_date": "date"})
        return frame.select(columns or ["symbol", "date", "open", "high", "low", "close"])

    def fingerprint(self) -> str:
        values = [(symbol, day.isoformat(), *values)
                  for (symbol, day), values in sorted(self._observations.items())]
        return hashlib.sha256(json.dumps(values, allow_nan=False).encode()).hexdigest()


class HistoricalStrategyResearch:
    """Compose unchanged proposal generation and interval buy-and-hold analytics.

    Signals observed at close become target allocations at the NEXT supplied
    session close. Prior holdings earn that close's return. Target allocations
    earn returns only afterwards, without orders/fees/quantity assumptions.
    """

    def run(self, definition: StrategyDefinition, *, session_dates: tuple[date, ...],
            history_start: date, history_dates: tuple[date, ...] | None = None,
            providers: Mapping[str, HistoricalDailyProvider] | None = None) -> dict:
        definition = StrategyDefinition.model_validate(definition.model_dump())
        if (type(history_start) is not date or len(session_dates) > 1000
                or any(type(day) is not date for day in session_dates)
                or tuple(sorted(set(session_dates))) != session_dates
                or (session_dates and history_start > session_dates[0])):
            raise ValueError("ordered unique research Dates and prior history_start required")
        result = {"kind": "historical_strategy_research_v1", "status": "blocked",
                  "strategy_definition": definition.model_dump(mode="json"), "strategy_result": None,
                  "rebalance_events": [], "portfolio_value_series": [], "daily_return": [],
                  "summary": {"initial_value": None, "final_value": None, "total_return": None},
                  "blockers": [], "source_reads": [], "input_fingerprint": None,
                  "pit": {"capable": False, "state": "not_established",
                          "warnings": ["current_revision_history_not_pit", "universe_survivorship_risk",
                                       "publication_times_not_available"]},
                  "assumptions": {"execution": "next_supplied_session_close_research_only",
                                  "holding": "long_only_buy_and_hold_between_rebalance_dates",
                                  "value_unit": "normalized_price_index_initial_1",
                                  "return_basis": "price_only_no_dividend_cash_fees_fx_or_share_actions",
                                  "calendar": "caller_verified_complete_history_grid",
                                  "history_mode": "source_base_ohlc_raw_request"}}
        if not session_dates or not definition.universe:
            result["status"] = "empty"
            return result
        if history_dates is None:
            result["blockers"].append({"code": "complete_history_calendar_required"})
            return result
        if (len(history_dates) > 10000 or any(type(day) is not date for day in history_dates)
                or tuple(sorted(set(history_dates))) != history_dates or not history_dates
                or history_dates[0] != history_start or history_dates[-1] != session_dates[-1]
                or tuple(day for day in history_dates if day >= session_dates[0]) != session_dates):
            raise ValueError("complete ordered history_dates must match warmup start and research session suffix")
        markets = {market_from_symbol(symbol) for symbol in definition.universe}
        if len(markets) != 1 or not markets <= {"CN", "US"}:
            result["blockers"].append({"code": "single_cn_or_us_market_required"})
            return result
        market = next(iter(markets))
        if definition.price_basis == "qfq":
            result["blockers"].append({"code": "pit_adjusted_history_unavailable"})
            return result
        if market == "US":
            result["pit"]["warnings"].append("yahoo_split_revision_and_as_traded_raw_unresolved")
            if definition.price_basis == "raw":
                result["blockers"].append({"code": "us_as_traded_raw_unavailable"})
                return result
        history = HistoricalResearchHistory(
            providers if providers is not None else {market: get_historical_provider(market)}, history_dates)
        proposals = StrategyResearchRunner().run(definition, history, session_dates=session_dates,
                                                  history_start=history_start)
        result["strategy_result"] = proposals
        result["blockers"].extend(history.blockers)
        if proposals["execution_status"] != "completed":
            result["blockers"].append({"code": "strategy_candidates_incomplete"})
            result["source_reads"] = history.reads
            return result
        schedule = []
        for event in proposals["events"]:
            signal = date.fromisoformat(event["event_date"])
            index = session_dates.index(signal) + 1
            effective = session_dates[index] if index < len(session_dates) else None
            usable = effective is not None and index < len(session_dates) - 1
            execution = {"signal_date": signal.isoformat(), "effective_date": effective.isoformat() if effective else None,
                         "status": "scheduled" if usable else "deferred", "reason": None if usable else "no_holding_interval",
                         "selected_symbols": event["portfolio_candidate"]["selected_symbols"],
                         "target_weights": event["portfolio_candidate"]["weights"]}
            result["rebalance_events"].append(execution)
            if usable:
                schedule.append((effective, event["portfolio_candidate"]))
        if not schedule:
            result["blockers"].append({"code": "insufficient_holding_dates"})
            result["source_reads"] = history.reads
            return result
        history.purpose = "valuation"
        # Cash before the first delayed allocation is an explicit model, never
        # a substitute for missing prices. Every holding interval must validate.
        values = {day: 1.0 for day in session_dates if day < schedule[0][0]}
        carry = 1.0
        for index, (start, candidate) in enumerate(schedule):
            end = schedule[index + 1][0] if index + 1 < len(schedule) else session_dates[-1]
            grid = tuple(day for day in session_dates if start <= day <= end)
            analysis = PortfolioAnalytics().analyze(candidate, history, start=start, end=end, expected_dates=grid)
            if not analysis["daily_return"] or history.blockers:
                result["blockers"].extend(history.blockers or analysis["blockers"])
                result["source_reads"] = history.reads
                return result
            for row in analysis["daily_return"]:
                value = carry * row["nav"]
                if not math.isfinite(value) or value <= 0:
                    result["blockers"].append({"code": "portfolio_value_arithmetic_unavailable"})
                    result["source_reads"] = history.reads
                    return result
                values[date.fromisoformat(row["date"])] = value
            carry = values[end]
        ordered = [values[day] for day in session_dates]
        returns = [None] + [ordered[i] / ordered[i - 1] - 1 for i in range(1, len(ordered))]
        if any(value is not None and not math.isfinite(value) for value in returns):
            result["blockers"].append({"code": "return_arithmetic_unavailable"})
            return result
        result.update(status="completed", source_reads=history.reads, input_fingerprint=history.fingerprint(),
                      portfolio_value_series=[{"trading_date": day.isoformat(), "value": value}
                                              for day, value in zip(session_dates, ordered, strict=True)],
                      daily_return=[{"trading_date": day.isoformat(), "value": value}
                                    for day, value in zip(session_dates, returns, strict=True)],
                      summary={"initial_value": ordered[0], "final_value": ordered[-1],
                               "total_return": ordered[-1] / ordered[0] - 1,
                               "valuation_days": len(ordered), "applied_events": len(schedule),
                               "currency": history.currency})
        for event in result["rebalance_events"]:
            if event["status"] == "scheduled":
                event["status"] = "applied"
        return result
