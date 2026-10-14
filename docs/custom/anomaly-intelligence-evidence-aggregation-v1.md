# Anomaly Intelligence Evidence Aggregation v1

## Architecture

Committed immutable Anomaly Event -> independent best-effort consumer -> Evidence Policy
Resolver -> Evidence Execution Resolver -> existing evidence -> separate Intelligence SQLite.
Only AnomalyWorker start/close lifecycle is extended. Its detection tick, alerts, event schema,
thresholds, severity, episodes and delivery remain unchanged. No provider, news, LLM or indicator
calculations occur. This is evidence aggregation, not causality, forecast or advice.

## Policy / execution

No default production policy, calendar version, identity binding or snapshot is installed.
Absent policy yields BLOCKED / no_applicable_evidence_policy. Overlapping policies or missing
execution binding fail closed. Tests register explicit isolated fixtures only. The collector
accepts an explicitly configured EvidenceExecutionResolver; default runtime has empty bindings.
Future production registration must be authorized separately, not inferred from current metadata.

## Historical

Existing context is read by event_id only. Identity and evaluation date are checked; all bars
must precede the event-window market date. ATR/reference/move are copied, never calculated.
Policy may allow retrospective ATR display; pit_capable=false means PARTIAL at best.
Strict READY requires source vintage, availability evidence and input_available_at no later than
detected_at. Existing Historical source-level PIT remains unproven.
Price-scale compatibility remains unproven. move_atr_ratio stays null unless the existing context
explicitly verifies scale, policy permits it and no price-scale blocker remains; no ratio is derived.
Original source status/blocker and complete context provenance are retained separately.

## Market

Read existing Market Context by event_id. Verify event ID/market/window and stock snapshot refs.
Current source has no top-level symbol; verify its stock refs against the archive's exact IDs and
symbol/market. Verify benchmark observation IDs/market/symbol/timestamps against existing archive.
Quote timestamps cannot exceed window_end; receive times cannot exceed detected_at. Existing
30-second baseline boundary tolerance is retained. Queries are bounded to 1000 observations.
No benchmark substitution, live request or return/window recalculation. Unavailable stays unavailable.

## Factor

Policy and execution binding pin definition, calendar ID/version, universe and exact factor
key/version/resolved-period/component. Frozen calendar determines the exact previous completed
trading date from window_end in its timezone. Query FactorSnapshotStore with that date/definition
and as_of_time=detected_at. No latest query or earlier-date fallback.
The existing Store enforces generated_at/available_at/stored_at <= cutoff. The collector additionally
checks symbol/market/date/definition/universe membership, input availability, output-column set,
registry version/parameters/component and normalization version/direction. It never recomputes.
Real Factor Snapshot producer is not yet installed: missing snapshot is legitimate UNAVAILABLE.
Parameters stored as null for a periodic family do not match an explicit resolved-period binding.

## States

Each section retains READY/PARTIAL/UNAVAILABLE/BLOCKED plus original source_status/source_blocker.
Policy/execution conflict or required evidence BLOCKED -> overall BLOCKED.
All selected required/optional sections READY -> READY.
At least one READY/PARTIAL section with remaining missing/partial evidence -> PARTIAL.
No usable evidence with clear selection -> UNAVAILABLE. Required missing evidence never becomes READY.
Unselected evidence is marked not_selected_by_policy. Missing context/value is never filled with zero.

## Persistence / consumer

Independent `data/user_data/anomaly_intelligence.sqlite3` contains records and its own cursor.
event_id is unique; records freeze their first collected view. Same semantic content is idempotent
(new UUID/generated_at do not create a semantic conflict). Different policy/version/evidence
content returns BLOCKED / intelligence_identity_conflict and preserves the original.
Record and cursor commit together. Bounded five-event pages use existing incremental event reads.
Worker exceptions retain cursor and report unavailable; original persistence/delivery is unaffected.
Restart reuses already frozen records, so later-arriving contexts do not silently upgrade them.
Refresh/versioned re-aggregation is deliberately out of scope. get/list_recent use read-only SQLite;
recent list is capped at 200 and indexed. No existing database schema is changed.

## API / UI

GET `/api/anomalies/{event_id}/intelligence` returns structured sections, policy/execution,
blockers, generated_at and version. Event absent -> 404; storage unavailable -> 503.
Existing event without collection -> UNAVAILABLE (or BLOCKED when policy does not resolve).
GET never calculates, writes or contacts providers. Existing anomaly endpoints are unchanged.
Details UI adds a small Intelligence Context section with explicit evidence states, source PIT
warning, null ratio, factor availability and human-readable blocker labels. No generated explanation.

## Validation boundary

Fixture contract validation uses only isolated temporary event/context/snapshot/policy databases.
It can prove complete READY, missing/partial/blocked states, PIT gates, immutable storage and failure
isolation, but cannot prove production evidence exists or that supplied provenance is authoritative.
Real validation reads only already present local records. No injected production events, fake factor
snapshots, default policy or relaxed thresholds. Lack of real policy/snapshot/context is reported
BLOCKED/UNAVAILABLE, never manufactured into a successful evidence result.

Local read-only acceptance on 2026-10-14 found an existing event database with zero events,
no Policy database and no Factor Snapshot database. Outcome: UNAVAILABLE - NO EXISTING LOCAL
EVENTS. No production Intelligence database was created. This is not real-event READY validation;
the full success path remains isolated fixture contract validation only.

## Remaining limitations

- No production policy/execution manifest or factor producer is created by this task.
- Historical source PIT/price scale remain unresolved; retrospective evidence is explicitly partial.
- Source provenance checks validate recorded metadata, not independent provider authenticity.
- First-collected view is frozen; later evidence requires an explicit future versioned-refresh design.
- Existing default-thread backtest worker timing open-loop is not fixed by this layer; constrained
  POLARS_MAX_THREADS=1 full regression, if needed, is a test environment condition only.
