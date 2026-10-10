"""Offline official 2026 cash-equity calendars; no network or rolling inference."""
from dataclasses import dataclass
from datetime import date, time, timedelta


def _dates(*values: str) -> frozenset[date]:
    return frozenset(date.fromisoformat(value) for value in values)


def _range(start: str, end: str) -> frozenset[date]:
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    return frozenset(first + timedelta(days=i) for i in range((last - first).days + 1))


@dataclass(frozen=True)
class Calendar:
    holidays: frozenset[date]
    half_days: frozenset[date]
    early_close: time | None
    sources: tuple[str, ...]
    coverage_start: date = date(2026, 1, 1)
    coverage_end: date = date(2026, 12, 31)
    last_updated: date = date(2026, 10, 10)

    def metadata(self) -> dict:
        return {
            "calendar_year": 2026, "coverage_start": self.coverage_start.isoformat(),
            "coverage_end": self.coverage_end.isoformat(), "source": list(self.sources),
            "last_updated": self.last_updated.isoformat(),
        }


CALENDARS = {
    "CN": Calendar(
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
        _dates("2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
               "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
               "2026-11-26", "2026-12-25"),
        _dates("2026-11-27", "2026-12-24"), time(13), (
            "https://www.nyse.com/trade/hours-calendars",
            "https://www.nasdaq.com/market-activity/stock-market-holiday-schedule",
        ),
    ),
}
