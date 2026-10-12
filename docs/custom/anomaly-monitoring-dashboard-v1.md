# Anomaly Monitoring Dashboard v1

## Entry and scope

`/anomalies` is registered by the existing `damon` frontend extension. The sidebar entry
is “实时异动流”, distinct from the existing A-share `/abnormal` page. No existing market
Dashboard or detection rule is replaced. All symbols, severity, direction, first-trigger/
escalation, metrics and evidence come from the backend. Percent formatting converts the
declared fraction to a display percent; it does not calculate anomalies.

## Data and attention

Existing quote streaming is SSE, with no anomaly-event push contract. v1 uses the shared
API client and TanStack Query. Reliability v1 now bootstraps recent once, then reads
incremental events and health every 3 seconds while visible.
Only an opened evidence panel polls its symbol's episode records. Queries are not persisted
in localStorage. Initial load/refresh restores recent events quietly; historical HIGH events
are not re-announced. A per-mount event-ID ledger deduplicates subsequent results.

LOW has one short entrance animation. MEDIUM has a finite highlight/translation. Newly
received HIGH first-trigger or backend escalation gets a gold page notice and finite card
emphasis; sustained never generates a notice. Notices expire after 8 seconds or manual
dismissal. Clicking one clears display filters and locates/expands the actual event.
No infinite pulse, audio, system notification, mail, mobile push or AI explanation exists.
CSS disables animation for prefers-reduced-motion. Alert eligibility is isolated in the
presentation module so future channels can reuse it without recomputing detection.

## Evidence and filtering

The event card shows market/symbol/type/direction/severity/status, local display time,
window, fractional change formatted as percent, observed price and evidence sample count.
Expanded evidence includes baseline/current prices, threshold, true window endpoints,
rule/version, quality warning codes, baseline scope, maximum gap, episode state and the
complete raw event JSON. Event-time market gating belongs to the backend; the event schema
does not contain a separate captured session-state field. Current market states come only
from the additive `health.market_sessions` resolver output, not browser clock inference.

Market/severity/type/symbol filters affect only the loaded display. Counters explicitly
describe loaded events, not a global total. The newest 100 events bootstrap history; older
records are available via backward pagination. Incremental delivery catches subsequent
backlog without jumping to latest 100. Unread persistence is intentionally deferred.

CN “查看个股” reuses StockPreviewDialog. There is no confirmed equivalent HK/US detail
route, so v1 does not send foreign symbols into the CN analysis/dialog path.

## Health and limitations

Missing/not-started health remains unknown, errors/unavailable are explicit, unknown
diagnostics or market conflicts are degraded, all closed markets show history-only status.
Observing with reliable state is labeled connection/observation status, never “verified
live anomalies”. Volume and volatility capabilities remain unsupported. Real intraday
trigger validation is still pending. Empty history is a quiet state, not a fabricated demo.

Test fixtures exist only in frontend tests and an external browser QA interception script;
no fixture is stored in runtime SQLite or returned by the production API.
Validation covers mapping/filtering, HIGH first/escalation/dedup, evidence, empty/closed/
degraded/API failure, refresh, finite/reduced motion, and 1920/1440/390px without overflow.
Frontend ESLint cannot run in this checkout because the existing script references a
missing eslint dependency; this phase does not change dependency files to repair that baseline.
The existing build's large-chunk warning remains.

For local QA, official `dev.ps1 -BackendPort 3318 -FrontendPort 3311` runs in a PTY.
Noninteractive execution hits Console.KeyAvailable's invalid handle. The launcher also
automatically kills occupied target ports: future runs must verify ownership/free ports
outside the sandbox before invoking it. No launcher modification is included in this phase.

## Reliability & Live Validation v1 (2026-10-12)

### Audited delivery risk

The prior page repeatedly replaced its recent page with only the latest 100 rows, so a burst
of 101+ events or sleeping tab could definitely skip intermediate events. Events already
have deterministic hashed event IDs and SQLite AUTOINCREMENT insertion IDs. Presentation
is detected_at descending with store_id descending as tie-breaker; delivery must not use
detected_at alone. Concurrent timestamp collisions are expected and do not merge events.

### Incremental contract

`GET /api/intraday/anomalies/incremental?after_id=0&limit=100` starts at sequence zero.
Positive after_id requires after_event_id matching the immutable anchor at that exact ID.
The hard limit is 200; default is 100. Response contains ascending insertion-sequence rows,
next_cursor {sequence,event_id}, has_more, latest_sequence and latest_event_detected_at.
The latter is maximum detected_at, not an inferred event time. Each page uses a read-only
SQLite transaction so rows and server watermark refer to the same database view. Inserts
after that view are fetched by the next request. Empty pages retain the input cursor.
Invalid parameters return 422; missing/changed anchors return 409. Database replacement or
anchor deletion is never silently treated as caught-up. Sequence is meaningful within its
event database; event-ID anchoring detects replacement rather than assuming global sequence.

Existing recent filters, ordering, backward cursor and episodes remain unchanged. Recent
adds resume_cursor for its newest returned row; absent/empty old responses can bootstrap at
zero. The dashboard uses the unfiltered recent page so all markets share one delivery stream.
Health adds read-only delivery metadata, plus worker total/per-market archive processing and
evaluation-attempt counters and last tick time. These counters reset on worker restart;
they are diagnostics, not new rules or evidence of successful anomaly triggers.

### Recovery and attention

One controller owns one in-flight round. Timer/focus/visibility triggers reuse that promise,
so requests cannot overlap and late responses from an unmounted controller are ignored.
Accepted pages advance the cursor only after contract checks; partial-success pages remain
consumed if a later page fails. Each round drains at most 10 pages (1000 events), publishes
each page immediately, then continues from that exact cursor next round if still behind.
HTTP failure preserves cursor and seen IDs; recovery/focus/resume drains backlog. A 409 stops
automatic retry and asks for refresh. Refresh bootstraps current history silently, as before;
cursor is page-lifetime state, not localStorage. It does not re-alert old HIGH events.

HIGH attention is still determined solely by backend first_trigger/escalation and event-ID
deduplication. Page-by-page callbacks preserve every eligible notice even when React batches
multiple responses; sustained/duplicates remain silent. Events are retained in the page's
memory plus existing SQLite history. Very long sessions with huge event volume may consume
memory; virtualization/retention is not introduced here. A consumer cannot recover events
actually deleted upstream; an invalid anchor is reported explicitly instead of hiding loss.

UI delivery diagnostics show engine health separately from API reachability, last successful
read, consumed sequence, backend sequence and latest server event time. A newer health
watermark displays lag/catching-up. Unreachable API/unknown watermark never asserts that
delivery is healthy. No time-delay metric is guessed from event time: a quiet market having
an old last event is not proof of broken transport. Caught-up means a confirmed snapshot
watermark, not a guarantee that no newer event can arrive immediately afterward.

### Repeatable read-only live observation

With official Dev services running on verified free ports:

```powershell
cd backend
uv run --frozen python scripts/smoke_anomaly_live.py --base-url http://127.0.0.1:3318 --market US --seconds 30
```

Only loopback HTTP is accepted. The harness reads health, existing Longbridge snapshot
archive and incremental event API. It never creates QuoteContext/TradeContext, injects
snapshots/events or changes thresholds. The running application's existing provider handles
quotes. Closed markets return NOT RUN - MARKET CLOSED; unknown/conflict returns NOT RUN.
No fresh regular Longbridge samples, no observed per-market processing/evaluation, worker
failure or incomplete bounded API catch-up return BLOCKED. Healthy flow without actual
triggers returns LIVE PIPELINE HEALTHY / NO REAL ANOMALY OBSERVED. Evaluation counts are
attempts; they do not prove every window had enough evidence. Frontend visibility is checked
separately in a browser and is never inferred by the CLI.

Actual 2026-10-12 US observation, target 15 seconds: regular session, AAPL.US fresh Longbridge
quote timestamp 1791818379000 and receipt 1791818379275; archive checkpoint 3930 -> 3932,
US consumed +2, evaluation attempts +8, generated/API-visible events 0. Result:
LIVE PIPELINE HEALTHY / NO REAL ANOMALY OBSERVED. Real browser before fixtures confirmed
0 visible events and consumed/backend sequences 0/0, caught up. This does **not** close the
pending real-trigger SQLite -> API -> HIGH frontend attention validation.

Final closure observation (2026-10-12, 15 seconds): initial request was BLOCKED because
temporary Dev services had exited; verified free 3311/3318 were restarted with official Dev.
US remained regular; AAPL.US quote timestamp 1791819936000, receipt 1791819935954;
checkpoint 4019 -> 4021, US consumed +2, evaluation attempts +8, consumed Longbridge
snapshot ID 4021, generated/API-visible events 0, cursor {sequence:0,event_id:null}.
The stricter harness returned LIVE PIPELINE HEALTHY / NO REAL ANOMALY OBSERVED.
This sample's quote clock is 46ms ahead of receipt; existing fail-closed timestamp gates
are unchanged. Healthy pipeline here means observed transport/consumption/attempts, not
proof this sample qualified for detection, or that an actual HIGH alert was generated.

Mock tests separately cover same-time events, 301-row backend/501-row frontend backlog,
inserts during pagination, cursor invalidation, single-flight/late response safety, network
recovery and simulated sleep/resume. Browser fixtures remain interception-only. Frontend
17 targeted/175 full Vitest plus 5 node:test, backend47 targeted/3315 full +6 skipped,
production build and touched Python Ruff pass. Existing missing ESLint remains recorded;
no build/toolchain/dependency changes. Default 1%/2%/4% rapid thresholds and 0.5% breakout,
episode rules, Longbridge, archive schema and research modules remain unchanged.
