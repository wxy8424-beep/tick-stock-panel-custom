"""Offline official 2026 cash-equity calendars; no network or rolling inference."""
from dataclasses import dataclass
from datetime import date, time, timedelta

from pydantic import BaseModel, ConfigDict, model_validator

MARKET_TIMEZONES = {"CN": "Asia/Shanghai", "HK": "Asia/Hong_Kong", "US": "America/New_York"}


class SessionRules(BaseModel):
    """Frozen parameters of the existing cash-equity clock algorithm."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    regular_windows: tuple[tuple[time, time], ...]
    pre_open_start: time
    post_market_end: time | None
    half_day_post_market_end: time | None
    closing_auction_minutes: int | None
    overnight_unverified_from: date | None
    overnight_before: time | None
    overnight_after: time | None
    # This version pins inclusive regular endpoints and the existing state precedence.
    algorithm: str

    @model_validator(mode="after")
    def validate_rules(self):
        if self.algorithm != "cash-equity-clock-v1":
            raise ValueError("unknown_session_algorithm")
        if not self.regular_windows or any(a >= b for a, b in self.regular_windows):
            raise ValueError("invalid_session_windows")
        if any(a[1] >= b[0] for a, b in zip(self.regular_windows, self.regular_windows[1:], strict=False)):
            raise ValueError("overlapping_session_windows")
        clocks = [self.pre_open_start, self.post_market_end, self.half_day_post_market_end,
                  self.overnight_before, self.overnight_after,
                  *(clock for window in self.regular_windows for clock in window)]
        if any(clock.tzinfo is not None for clock in clocks if clock is not None):
            raise ValueError("session_requires_local_wall_time")
        overnight = (self.overnight_unverified_from, self.overnight_before, self.overnight_after)
        if any(value is not None for value in overnight) and not all(value is not None for value in overnight):
            raise ValueError("incomplete_overnight_boundary")
        if self.closing_auction_minutes is not None and not 0 < self.closing_auction_minutes < 60:
            raise ValueError("invalid_auction_window")
        return self


def _session(windows, *, pre="00:00", post=None, half_post=None, auction=None, overnight=None):
    return SessionRules(regular_windows=windows, pre_open_start=pre, post_market_end=post,
        half_day_post_market_end=half_post, closing_auction_minutes=auction,
        overnight_unverified_from=overnight, overnight_before="04:00" if overnight else None,
        overnight_after="21:00" if overnight else None, algorithm="cash-equity-clock-v1")


def _dates(*values: str) -> frozenset[date]:
    return frozenset(date.fromisoformat(value) for value in values)


def _range(start: str, end: str) -> frozenset[date]:
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    return frozenset(first + timedelta(days=i) for i in range((last - first).days + 1))


@dataclass(frozen=True)
class Calendar:
    market: str
    calendar_id: str
    version: str
    timezone: str
    session: SessionRules
    holidays: frozenset[date]
    half_days: frozenset[date]
    early_close: time | None
    sources: tuple[str, ...]
    coverage_start: date = date(2026, 1, 1)
    coverage_end: date = date(2026, 12, 31)
    last_updated: date = date(2026, 10, 10)
    trading_weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    additional_trading_days: frozenset[date] = frozenset()

    def metadata(self) -> dict:
        return {
            "calendar_year": 2026, "coverage_start": self.coverage_start.isoformat(),
            "coverage_end": self.coverage_end.isoformat(), "source": list(self.sources),
            "last_updated": self.last_updated.isoformat(),
        }


CALENDARS = {
    "CN": Calendar(
        "CN", "cn-cash-equity-official", "2026-v1", MARKET_TIMEZONES["CN"],
        _session((("09:30", "11:30"), ("13:00", "15:00"))),
        frozenset().union(*(_range(a, b) for a, b in (
            ("2026-01-01", "2026-01-03"), ("2026-02-15", "2026-02-23"),
            ("2026-04-04", "2026-04-06"), ("2026-05-01", "2026-05-05"),
            ("2026-06-19", "2026-06-21"), ("2026-09-25", "2026-09-27"),
            ("2026-10-01", "2026-10-07"),
        ))), frozenset(), None, (
            "https://www.sse.com.cn/disclosure/dealinstruc/closed/",
            "https://www.szse.cn/disclosure/notice/general/t20251222_618087.html",
            "https://www.bse.cn/important_news/200027428.html",
        ),
    ),
    "HK": Calendar(
        "HK", "hk-cash-equity-official", "2026-v1", MARKET_TIMEZONES["HK"],
        _session((("09:30", "12:00"), ("13:00", "16:00")), auction=10),
        _dates("2026-01-01", "2026-02-17", "2026-02-18", "2026-02-19",
               "2026-04-03", "2026-04-06", "2026-04-07", "2026-05-01",
               "2026-05-25", "2026-06-19", "2026-07-01", "2026-10-01",
               "2026-10-19", "2026-12-25", "2026-12-26"),
        _dates("2026-02-16", "2026-12-24", "2026-12-31"), time(12), (
            "https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/"
            "Participant-and-Members-Circulars/SEHK/2025/ce_SEHK_CT_075_2025.pdf",
        ),
    ),
    "US": Calendar(
        "US", "us-cash-equity-official", "2026-v1", MARKET_TIMEZONES["US"],
        _session((("09:30", "16:00"),), pre="04:00", post="20:00", half_post="17:00",
                 overnight="2026-12-06"),
        _dates("2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
               "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
               "2026-11-26", "2026-12-25"),
        _dates("2026-11-27", "2026-12-24"), time(13), (
            "https://www.nyse.com/trade/hours-calendars",
            "https://www.nasdaq.com/market-activity/stock-market-holiday-schedule",
        ),
    ),
}
