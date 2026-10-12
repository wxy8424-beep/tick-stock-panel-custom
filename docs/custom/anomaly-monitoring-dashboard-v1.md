# Anomaly Monitoring Dashboard v1

## Entry and scope

`/anomalies` is registered by the existing `damon` frontend extension. The sidebar entry
is “实时异动流”, distinct from the existing A-share `/abnormal` page. No existing market
Dashboard or detection rule is replaced. All symbols, severity, direction, first-trigger/
escalation, metrics and evidence come from the backend. Percent formatting converts the
declared fraction to a display percent; it does not calculate anomalies.

## Data and attention

Existing quote streaming is SSE, with no anomaly-event push contract. v1 uses the shared
API client and TanStack Query, polling recent and health every 3 seconds while visible.
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
describe loaded events, not a global total. The newest 100 events are polled; older records
are available via cursor pagination. v1 does not guarantee catching every attention notice
if more than 100 events arrive between polls or the tab is suspended. History remains in
SQLite and can be loaded separately. Unread persistence is intentionally deferred.

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
