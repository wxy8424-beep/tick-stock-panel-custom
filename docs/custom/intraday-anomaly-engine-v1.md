# Intraday Anomaly Engine v1

## Boundary and architecture

This is read-only price observation, not a recommendation, prediction or trade trigger.
The existing Longbridge quote, quality, market-session and snapshot contracts are unchanged.
The independent worker reads committed `market_snapshots.sqlite3` rows and writes only
`data/user_data/anomaly_engine.sqlite3`. Quote and archive writer threads do not compute anomalies.
The existing extension registers query routes; a small application lifecycle hook starts/stops
the worker. No SSE, frontend, SDK, provider, factor or strategy changes are included.

## Rules and evidence

Default rapid-price windows are 1/5/15 minutes with fractional thresholds 0.01/0.02/0.04.
The baseline is the last valid snapshot at or before the actual quote-time boundary,
within 30 seconds. No future baseline, forward fill, timestamp sorting or duplicate repair
is performed. Gaps over 120 seconds within a rapid window reject evaluation.
Both quote-time and evaluation-time market sessions must be confirmed regular; archived
session diagnostics, unknown/conflict, invalid/stale quality and delayed quotes reject alerts.
The current quote must be no more than 120 seconds old and quote time must not exceed receipt.

Price-only calculations permit unknown quality only for the explicit missing-volume/OHLC
warning whitelist; unrelated unknown quality remains unknown. This does not promote overall
quote quality to valid. Security halt warnings reject the affected security, not the market.
Markets and symbols are independently keyed; only Longbridge archive records are accepted.

Breakout compares price against prior archived regular-session prices for the same local day,
excluding the current point. It requires at least three prior valid samples and a 0.005
fractional break. Its scope is **observed archive prices**, not a claimed exchange-wide
intraday high/low. History is bounded to 1000 prior rows; truncation makes breakout unknown.
Duplicate/out-of-order points and a stale final observation gap reject breakout. Earlier
gaps are reported in evidence; archive observations cannot prove uninterrupted full-day coverage.

Severity is low at threshold, medium at 1.5 times threshold, high at twice threshold.
Validated immutable policies are injectable; a content-derived version namespaces all state.
Events preserve Decimal metrics, source, rule/version, timestamps, baseline/current snapshot
IDs, sample count, maximum gap and severity multiples. JSON numeric metrics serialize as strings.
`change_pct` is a fraction, not percentage points.

## Unsupported observations

Volatility expansion is explicitly unsupported: provider polling is variable, quote timestamps
are not guaranteed fixed-cadence samples and the bounded archive queue may drop overflow.
The initial local AAPL.US cadence audit found no samples. No authoritative cadence has been
established, so no realized-volatility event is fabricated.
Volume spike is unsupported. Volume is never converted, inferred or used in these rules;
evidence reports `volume_used=false` and `unsupported_unit_unverified`.

## Durable episodes and failures

The key is symbol, market, rule/version and direction. First trigger creates an episode/event.
Continued same or lower severity updates episode status to sustained without another event.
Severity above the episode peak creates an escalation event within the same episode.
A valid below-threshold/opposite-direction observation resolves the previous direction.
New triggers wait 120 seconds from resolution; unknown input does not constitute recovery.
An active episode expires after 180 seconds without a qualifying update; subsequent eligible
data creates a new episode. No wall-clock reminder loop or external notifications are present.

Events, episodes and archive cursor commit in one SQLite transaction. Failures roll back all
three and surface fixed diagnostics without raw paths or secrets. A first worker start skips
historical alert replay by checkpointing the latest row; it can still use archived same-day
baseline evidence. Restarts resume the durable cursor, preserving deduplication.
The worker polls every second with at most 100 rows. Large universes may outpace consumption;
old rows fail freshness rather than creating retrospective live alerts. Worker health exposes
processed count, checkpoint, rule version and bounded diagnostics. Failures are best effort
and do not affect quote delivery. Event storage has no automatic retention deletion in v1.

## Read-only API

- `GET /api/intraday/anomalies/recent`: optional symbol, market, event_type, severity,
  aware start/end, `before_id` and limit (1..200). Newest insertion first, continuation cursor.
- `GET /api/intraday/anomalies/episodes?symbol=...`: bounded durable episode state.
- `GET /api/intraday/anomalies/health`: worker/unsupported-rule diagnostics.

Queries do not fetch quotes, run rules, create absent databases or mutate archives.
They reuse existing application authentication. Storage failure returns a sanitized 503.
Tests use local synthetic fixtures only and cover actual timestamps, quality/session gates,
market isolation, restart/dedup/escalation/recovery, rollback, serialization and queries.
Runtime SQLite files are excluded from Git; Git does not back up this local event history.
Dashboard event rendering and notifications require a separate task.
