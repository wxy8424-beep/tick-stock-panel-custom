"""实时行情的市场时钟, 不提供交易日历或 CN final 状态。

regular 表示工作日时钟窗口, 不是交易日确认。HK/US 尚无权威假日日历;
CN 的实际轮询继续由 QuoteService 原有交易日探针门控。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

_ZONES = {"CN": "Asia/Shanghai", "HK": "Asia/Hong_Kong", "US": "America/New_York"}
_WINDOWS = {
    "CN": ((time(9, 30), time(11, 30)), (time(13), time(15))),
    "HK": ((time(9, 30), time(12)), (time(13), time(16))),
    "US": ((time(9, 30), time(16)),),
}
_SUFFIX_MARKETS = {"SH": "CN", "SZ": "CN", "BJ": "CN", "HK": "HK", "US": "US"}


def market_from_symbol(symbol: object) -> str | None:
    """复用实时入口的证券格式边界; 声明冲突仍由记录入口校验。"""
    if not isinstance(symbol, str) or "." not in symbol:
        return None
    code, _, suffix = symbol.rpartition(".")
    market = _SUFFIX_MARKETS.get(suffix)
    if not code or market is None:
        return None
    if market == "CN" and not (len(code) == 6 and code.isascii() and code.isdigit()):
        return None
    return market


@dataclass(frozen=True)
class MarketSession:
    market: str
    timezone: ZoneInfo
    local_datetime: datetime
    session_state: str
    # clock 模型不调用探针, 不把工作日误称为确认交易日。
    calendar_status: str = "unknown"
    confirmed_trading_day: bool | None = None

    @property
    def local_date(self) -> date:
        return self.local_datetime.date()

    @property
    def is_regular_session(self) -> bool:
        return self.session_state == "regular"


def get_market_session(market: str, now: datetime | None = None) -> MarketSession:
    """按一个绝对时刻计算市场时钟。拒绝 naive 时间, 不依赖机器本地时区。

    端点包含语义与原 CN continuous session 一致; CN final 的专属半开窗口
    不在本模型中改变。盘前/盘后只描述状态, 不授权 regular 轮询。
    """
    if market not in _ZONES:
        raise ValueError(f"unsupported market: {market}")
    now = now if now is not None else datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include timezone")
    zone = ZoneInfo(_ZONES[market])
    local = now.astimezone(zone)
    clock = local.time()
    windows = _WINDOWS[market]
    state = "closed"
    if local.weekday() < 5:
        if any(start <= clock <= end for start, end in windows):
            state = "regular"
        elif clock < windows[0][0]:
            state = "pre_open"
        elif windows[0][1] < clock < windows[-1][0]:
            state = "break"
    return MarketSession(market, zone, local, state)
