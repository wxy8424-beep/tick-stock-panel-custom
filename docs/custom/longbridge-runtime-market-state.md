# Longbridge runtime market-state signal integration

## Evidence (2026-10-10, installed SDK 5.2.0)

- Python `openapi.pyi`: `MarketContext.market_status()` takes no arguments and
  returns `MarketStatusResponse.market_time: list[MarketTimeItem]`. Each item has
  `market`, integer `trade_status/sub_status`, string `timestamp`, and delayed
  counterparts. The live field is `trade_status`, never `delay_trade_status`.
- [Official market endpoint](https://open.longbridge.com/zh-CN/docs/market/market-status)
  identifies exchange-level open/close status. Its current example takes a symbol;
  the installed signature takes precedence. No symbol argument is passed.
- [Official Rust SDK 5.2.0 market enum](https://docs.rs/longbridge/5.2.0/longbridge/market/types/enum.TradeStatus.html)
  supplies the numeric semantics missing from Python's raw integer annotations.
  This is `market::types::TradeStatus`, **not** Python `openapi.TradeStatus`.
- Python `openapi.TradeStatus` belongs to security quotes (Normal, Halted,
  Delisted, Fuse, Suspend etc.). A quote's status, missing quote or suspension
  never enters the market adapter. No callable `trading_status` or
  `security_status` was found in the installed public stub.
- `QuoteContext.trading_session()` gives a schedule (`MarketTradingSession`,
  time intervals and TradeSession); `trading_days()` gives dates/half days.
  Neither proves a temporary live closure. Quote TradeSession identifies a
  security quote's regular/pre/post/overnight session, not all-market status.

## Conservative mapping

Only items inside the market_time envelope are eligible. Cash codes only apply
to CN/HK; US codes only apply to US. Bool, strings and unrecognized codes become
unknown. Duplicate rows for a market become unknown; unsupported markets ignored.

| Market | Official codes | Resolver state |
| --- | --- | --- |
| CN/HK | 101 clearing before open, 102 opening auction | pre_open |
| CN/HK | 105 regular trading | regular |
| CN/HK | 106 midday break, 123 temporary intraday break | break |
| CN/HK | 107 closing auction | post_market |
| CN/HK | 108 closed, 121 half-day closed, 122 not opened | closed |
| US | 201 pre-market, 206 clearing plus pre-market | pre_open |
| US | 202 regular trading | regular |
| US | 203 post-market | post_market |
| US | 204 closed | closed |

Other codes stay unknown even if documented: dark sessions, security-specific
statuses, 103 VIX break, 120 fixed-price session, 205 halt, 207 overnight,
209/210 aliases and future codes do not authorize regular trading. No sub_status
semantics are inferred. No overnight capability is enabled.

## Publisher and precedence

The existing Longbridge Provider reuses its lazy read-only MarketContext under
the existing SDK lock. It checks market status on realtime requests, at most once
per 60 seconds. There is no new worker, subscription or network call in resolver
or provider_health reads. No trade/account/order API is used.

`observed_at` is the timezone-aware local successful-response receipt clock,
stored as the existing signal's `checked_at`, serialized as
`runtime_observed_at`. It is not a security event timestamp. The SDK's market
timestamp is described as current market time, not proven last-state-change time;
we do not infer its unit or use it to manufacture freshness.

Signals expire after 120 seconds. If no realtime polling occurs, status expires
and official calendar scheduling resumes, allowing the next normal polling
window. This is an observed provider response, not an independent continuous
exchange heartbeat or a guarantee against provider-side cached responses.

- Explicit fresh market closed overrides calendar regular (halts polling).
- Calendar holiday plus provider closed preserves holiday, without false conflict.
- Provider active state conflicting with calendar, including holiday/uncovered
  date, becomes unknown with `calendar_provider_conflict`; it cannot open a holiday.
- Explicit closed/break can stop activity; schedule disagreement remains a conflict.
- Fresh unknown code remains unknown, not calendar healthy.
- Unavailable/malformed response removes this source's cached observations and
  falls back to calendar. Missing markets also fall back independently.
- Expired or future observations fall back to calendar with
  `runtime_status=expired`, `provider_status_expired`. An uncovered calendar
  still stays unknown. Expired closure cannot persist forever.
- No security signal can override market state. CN/HK/US keys are independent.

Response publication is atomic. Shutdown releases SDK references and clears
this source's signal. No signals or credentials are persisted. The runtime source
is the current registry Longbridge instance; no second resolver is introduced.

## Health and contracts

Effective regular still uses 120-second quote receipt freshness; nonregular
closed/holiday/lunch do not turn old quotes stale. Any current conflict/unknown
is never healthy, even if a safe closure wins for polling. Context errors and
no-receipt behavior remain unchanged. provider_health adds optional observation
and fixed diagnostic fields; no raw exception, request or credential is serialized.

Realtime stays SUPPORTED independently of runtime usability. Quantity and
financial contracts, calendar dates and daily/minute/depth/financial capability
declarations are unchanged. Frontend is unchanged.

The precedence here supersedes the prior calendar-stage rule that made an expired
signal unknown until explicitly cleared; this stage requires calendar fallback.

## Verification

2026-10-10: targeted 305 passed; backend full 2926 passed / 6 skipped / 0 failed;
all seven touched Python files Ruff PASS (zero violations). Frontend unchanged,
so frontend tests/build not run. Only a test import alias was renamed after the
full run; no production behavior changed afterwards.

Real read-only smoke at 2026-10-10T14:26:56 UTC using installed 5.2.0:
600519.SH, 700.HK, AAPL.US quotes present; all three resolved closed,
source=longbridge.market_status, runtime=verified, health=healthy, realtime
contract=supported. All PASS. It was a weekend; live temporary closure and
calendar conflicts are validated by mocks, not claimed as observed exchange events.
