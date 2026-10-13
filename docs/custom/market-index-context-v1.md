# Market / Index Context Anomaly v1

Market Context is explanatory enrichment, not an anomaly detector. It does not change
thresholds, severity, episodes, cooldown, deduplication, escalation or notification frequency.
Direction/magnitude correspondence is not evidence of market causality or investment advice.

## Existing feeds and benchmark mapping

`market_context.BENCHMARKS` centrally references established symbol definitions:

| Market | Default benchmark | Boundary |
| --- | --- | --- |
| CN | 000001.SH / 上证指数, from CORE_INDEX_NAMES | Consume existing archived index observations only |
| US | .SPX.US / 标普500, from USDashboardService INDEX_SYMBOLS | SPX is explicit default, not a claim all stocks track SPX |
| HK | none | HSI.HK has no verified feed in this checkout; unsupported |

Existing US Dashboard also supports .IXIC.US and .DJI.US. No reliable stock metadata selects
Nasdaq automatically, so v1 does not infer a growth/sector benchmark. Dashboard quote reads
do not themselves archive US index samples. **A working live index card does not guarantee
anomaly-window archived observations**: missing archive data produces unavailable. This stage
does not add an index source, fetch, subscription or new polling loop, nor manufacture history.

## Architecture and persistence

Immutable event -> independent enrichment consumer -> local side store -> read-only API -> UI.
Reuse HistoricalEnrichmentWorker's bounded serial pagination, independent durable cursor,
thread lifecycle and transactional context+cursor save. Market enrichment has its own instance,
so slow historical source requests do not delay it. Its service never accesses a provider.
`data/user_data/anomaly_market_context.sqlite3` holds contexts keyed by event_id and the cursor;
the original event payload and Snapshot Archive schema are untouched. Stores are runtime data,
not Git artifacts. Write/read errors degrade context and health, not original event delivery.

Optional evidence.market_context is overlaid on recent/incremental reads. Bounded GET
`/api/intraday/anomalies/market-contexts?event_id=...` supports 1..100 IDs, each max64 characters.
GET never computes context, fetches quotes or creates an absent sidecar. Older event models
accept missing context; new optional model field defaults to null.

## Window alignment and evidence

Use the original event's actual baseline/current price timestamps (window_start/window_end),
not the nominal rule duration or the latest index price. Stock movement is recomputed from
immutable SnapshotRef prices and checked against event.change_pct. Different-market symbols,
misaligned evidence or unknown timestamps fail closed.

Select archive observations with quote_timestamp <= each boundary and receive_timestamp <=
event.detected_at. The latest predecessor can be at most 30 seconds old. Both boundaries must
have different timestamps; no interpolation/forward fill. Retain all observations between the
selected boundaries; any gap >120 seconds, conflicting equal-timestamp prices/providers,
mixed sources or >1000 observations produces unavailable. Queries are read-only, symbol/market
and receive-time bounded. Future quote and post-detection receipt rows cannot enter evidence.

Each used price must be finite/positive; quote <= receipt, receipt latency <=120 seconds,
archived and resolver session both confirmed regular, no session diagnostic/conflict.
Unknown quantity/optional OHLC warnings alone do not disqualify trustworthy price-only data;
unknown price/time/session or other quality warnings do. Volume is never used or converted.
Processing later during a closed session does not invalidate an earlier confirmed-regular
event window merely because wall-clock time changed.

## Ratios and deterministic classification

All change_pct fields are fractions: 0.011 = 1.1%. Decimal arithmetic:

`relative_move_pct = stock_window_change_pct - benchmark_window_change_pct`.

POLICY is saved in evidence and centrally defines:

- Opposite nonzero signs: market_opposed.
- Same nonzero signs and absolute relative difference <=0.005: market_aligned.
- Otherwise stock absolute move > benchmark absolute move and relative difference >=0.01:
  idiosyncratic (including a flat benchmark).
- Otherwise mixed; unavailable evidence remains unknown.

These contextual 0.5/1 percentage-point thresholds do not modify detector thresholds and
are not beta adjustment, statistical residuals or probabilities. Downside idiosyncratic
does not mean a favorable trade. Preserve stock/benchmark/relative values, source, version,
policy, window, stock SnapshotRefs, baseline/current index observations and all used samples
so figures and classification can be recomputed. observed_at is enrichment time, not quote time.

## Dashboard and limits

Cards add a muted same-window index/relative sentence below original severity/type/change.
Expanded evidence shows benchmark, window returns, classification, source/version and raw
backend context evidence. Unavailable shows 市场背景暂不可用 with a blocker, never a fake zero.
Visible IDs are batched (max100); pending context refreshes every3 seconds; expanded older
events query one ID through the same batch contract. Alerts retain their existing semantics.

No beta, industry benchmarks, sector classification, correlation, PCA, ML, news, AI, trading
or browser notifications. Archived sample coverage can be sparse/missing; no source-level
market-causality claim or guarantee of historical exchange completeness is made.

## Acceptance and real archive limits (2026-10-13)

Recovery started on main/d0f1ccf0e0c1953281f6801f0250fb85533a971a with the fourteen
candidate files intact and unstaged. Previously completed results, supplied in the recovery
handoff, were retained without rerunning: backend targeted 80 PASS; backend full
3381 passed / 6 skipped / 0 failed, exit 0; frontend targeted 13 PASS and full 182 PASS;
changed Python production/test files Ruff 0 remaining.

This recovery executed the existing node:test command (DimensionMembersDialog and
neighborPrefetch): **5 passed / 0 failed, exit 0**. `pnpm build` (tsc + Vite) **PASS, exit 0**;
Vite retained its chunk >500 kB warning (ECharts about 1,035 kB), with no toolchain change.
`ruff check scripts/smoke_market_context.py` **PASS, exit 0**.

### REAL ARCHIVE VALIDATION

The smoke's existing default data directory was independently checked against the configured
backend data directory and matched. Only existing Snapshot Archive and event reads were
performed; no provider/network quote fetch, index subscription, new polling loop, production
event insertion, benchmark backfill or context persistence occurred.

| Market | Implemented benchmark | Real snapshots | First / last quote and receipt | Source / quality / session | 1m / 5m / 15m coverage | Real context result |
| --- | --- | --- | --- | --- | --- | --- |
| US | .SPX.US | 0 | null / null | no samples | insufficient for all | UNAVAILABLE — INSUFFICIENT BENCHMARK ARCHIVE |
| CN | 000001.SH | 0 | null / null | no samples | insufficient for all | UNAVAILABLE — INSUFFICIENT BENCHMARK ARCHIVE |
| HK | none | not applicable | not applicable | not applicable | unsupported | UNSUPPORTED; HSI archive/realtime integration unverified |

Neither US nor CN had a legal window with both baseline observation <=window_start and
current observation <=window_end. No current quote or future observation was substituted.
This is a valid evidence-unavailable result, not a code failure or proof of real-data support.
There were no real anomaly events available to inspect. Hash/existence checks confirmed the
production archive, original event store, market-context sidecar and their WAL files stayed
unchanged across the read-only archive validation. Existing HK anomaly behavior is unchanged.

### FIXTURE EVENT CONTRACT VALIDATION

Explicit isolated test/dev fixtures in a temporary directory validated both US and CN:
fixture anomaly event -> Market Context enrichment worker -> independent side store keyed
by event_id -> batch market-context API -> recent anomaly API evidence overlay. Both **PASS**.
Fixture event-store and fixture Snapshot Archive bytes remained unchanged by enrichment.
Production events inserted: **0**. Fixture labels/source values are synthetic provenance,
not a real quote or anomaly observation.

Both fixtures had stock change 0.022, benchmark change 0.018, relative_move_pct=0.004
and deterministic class market_aligned. US window was 2026-10-09 14:00..14:05 UTC; CN
02:00..02:05 UTC. Baseline/current benchmark observations matched those exact boundaries,
with eleven 30-second observations and 100 ms receipt latency, source label longbridge.
Only optional volume warnings were present; regular session and price/time gates passed.
All used quotes were <=window_end and receipts <=event.detected_at. Evidence retained symbol,
source, version/policy, stock SnapshotRefs, window, both benchmark boundary observations and
the intervening observations, enabling recomputation. This fixture result does not establish
real US/CN archive-window coverage or production anomaly/UI observation.

Final diff/credential review covers only these fourteen stage files. Runtime databases,
logs/cache/build output, real smoke output and fixture runtime databases are excluded from Git.
Fixture builders remain in test code, outside production execution paths. Detector
threshold/severity/dedup/cooldown/escalation and Longbridge, Snapshot Archive and Historical
Provider contracts were not changed. Real benchmark coverage and real anomaly context
observation remain follow-up work; this stage does not start collection to manufacture them.
