# Market Data Quality Layer

## Scope and compatibility

The reusable pure validator `app.data_providers.quote_quality` is connected to
Longbridge `get_realtime()` for CN/HK/US. It does not add fields to quote records,
change their routing, persist data, request extra SDK data or alter capability
declarations. No daily/minute/depth/financial capability or unit is enabled.

This stage is **observational**: existing normalization still rejects malformed
quotes; newly detected quality issues are reported, without silently rewriting,
filling or dropping previously accepted quotes. Consumers must inspect quality
before relying on a flagged quote. It is not a new ingestion permission gate.

L3 is necessary for standardization/health wiring; existing L1/L2 extension hooks
cannot observe this boundary. Core changes are limited to Provider observations
and an additive realtime_health field. No frontend change or database migration.

## Validation

- Prices must be numeric, finite, positive. Missing values are unknown. Existing
  OHLC/previous-close zeros may be no-trade placeholders: unknown, not invented
  prices. No arbitrary jump, exchange limit or absolute price thresholds.
- With available positive values, high >= low and low <= open/last_price <= high.
  Inconsistent OHLC is invalid. prev_close need not be inside today's range.
- Standard volume must be numeric, finite and nonnegative; zero is valid.
  Unit names reuse `contracts.QUANTITY_UNITS`; missing/unknown units stay unknown.
  Provider-native volume is checked only for numeric sign/finite validity; this
  is not unit evidence. No shares/board-lot inference or /100 conversion.
- Longbridge standard volume remains null, with CN unverified / HK-US unsupported.
  Thus an otherwise normal Longbridge quote generally has quality unknown until
  the volume contract is independently established. Raw volume is not serialized.
- Standard timestamp is Unix milliseconds only. No heuristic seconds-to-ms fix.
  Missing is unknown; invalid/out-of-range/future timestamp invalid. Future event
  latency is null, not negative or clamped to zero. SDK datetime normalization,
  including the existing local-naive SDK semantics, is unchanged.
- Existing market_session resolver supplies state. Unknown market/calendar or
  conflict is explicitly unknown; security halts never become market signals.
- During regular, event age >120s yields quality stale. This does not mean the
  network connection failed or the quote is fabricated. Outside regular an old
  closing snapshot is not stale solely due to elapsed nontrading time.
- Closed/holiday with a recent event (<=120s) whose event-time resolver also says
  closed/holiday produces a warning. Exact regular close snapshots are not falsely
  warned. This is suspicion, not proof of an invalid trade or extended-session
  permission. No overnight/session capability is enabled.

## Output

`provider_health.realtime[market].runtime.quality` is additive:

| Field | Meaning |
| --- | --- |
| state | valid / unknown / warning / stale / invalid |
| warnings | Fixed codes only; no raw payload, exception or credential |
| observed_at | Aware receipt/aggregation ISO time; null if not observed |
| latency_ms | Quote event age at observed_at, **not** network RTT |
| quote_count | Number of evaluated/parse-rejected quotes in this market's latest request |
| counts | Per-state counts; optional for no-data/unavailable views |

Summary priority: known invalid > stale > warning > unknown > valid. An unknown
volume check is retained in warnings even when another known defect dominates;
only complete supported checks can yield valid. Maximum known event age is used,
aligned across all batch receipt clocks; null means no reliable event age.

Only a bounded latest-request summary lives inside the existing observation per
market. No per-symbol persistent cache or raw response is retained. Mixed-batch
defects remain visible without erasing successful markets or declaring the whole
provider unsupported. Empty/network/parse paths do not manufacture valid quality;
provider unavailable => unknown, provider_unavailable, no fake observed time.
If a quality check itself fails, normalized quotes remain available and quality
is unknown with quality_check_unknown; raw errors are never returned/logged.

Reception health still applies its existing 120s received_at freshness and
market-state semantics. It is distinct from event quality: a fresh response can
contain a stale/invalid quote; runtime healthy does **not** imply quality valid.
This preserves provider contract and existing health consumers. Quantity and
financial blockers stay authoritative; quality cannot unlock capabilities.

Quality is a diagnostic at **observed_at**, not a continuously updated latency
meter. Health reads do not make network calls or recalculate historical quality.
Old observations lacking quality serialize as unknown. Existing response fields
remain unchanged, and old consumers can ignore this extra nested object.

## Verification

Mock tests cover normal/invalid/missing prices, OHLC, volume/raw volume/unit,
stale and future timestamps, closed snapshots, uncovered calendar, market
isolation, partial failures, unavailable provider, quality-error isolation and
old response serialization. Real smoke is read-only, using existing local
credentials without outputting them; no trade context/account/order API.

2026-10-11 acceptance: related targeted 262 PASS; quality-only 34 PASS after two
equivalent Ruff conditional simplifications; backend full 2960 passed / 6 skipped
/ 0 failed (existing warnings retained); touched-file Ruff zero violations.
Frontend unchanged, tests/build NOT RUN.

Real smoke at 2026-10-11T02:02:14 UTC: 600519.SH / 700.HK / AAPL.US all present,
market closed, realtime contract supported, quality unknown with only
volume_unknown / volume_unit_unknown. Observed time and nonnegative event latency
serialized correctly. No stale label forced onto weekend historical snapshots;
no price/OHLC/future-timestamp defects found in these three samples. Smoke PASS
means the integration worked; it does not mean the unknown volume contract passed.
