# Hidden CN panels: page activity boundary v1

Task: T-2026-10-19-A14, Agent A / MAINLINE, 2026-10-19.

Repository: `D:\娱乐\codex\lianghua\tick-stock-panel-main`.
Baseline: `main`, `f56d025d91ef47250ccacd02174fe14fe6489222`.
Initial worktree and index were clean. This task leaves five unstaged candidates;
it does not stage, commit, push or synchronize Git.

## Observed ownership and change

`Monitor` delegates to `MonitorMarkets`; `AbnormalMoves` delegates to
`AbnormalMarkets`. Each existing market wrapper retains visited CN content in a
hidden container and passes `active=false` while HK/US is selected. Neither
wrapper nor any Preview contract/fixture is changed.

Previously the monitor alerts/rules queries did not use that activity flag;
rule metadata queries could also run while hidden. The abnormal root did not
pass activity to its auction, intraday or deviation children. The deviation
response effect persisted results regardless of selected market.

The minimum repair is confined to those two extension files:

| Page-owned query | Enable condition | Subscription condition |
| --- | --- | --- |
| Monitor alerts and rules | `active` | `active` |
| Rule group metadata and watchlist | `active && hasGroupRules` | `active` |
| Rule security names | `active && allSymbols.length > 0` | `active` |
| Monitor extension-field dialog schema | existing `open` | `open` (already includes root activity) |
| Auction benchmark | `active` | `active` |
| Intraday abnormal rows | `active` | `active` |
| Deviation overview | `active && enabled` | `active` |
| Deviation watchlist | `active && watchlistOnly` | `active` |

Hidden page polling returns `false`. Active CN intervals remain the existing
10s/120s monitor and 60s/300s abnormal schedules. Deviation's disabled switch
has no interval. Refresh/retry callbacks also check activity because an explicit
`refetch()` bypasses Query's `enabled` condition. Deviation's enable toggle and
response persistence effect are guarded by activity.

## Subscription, retries and in-flight responses

The installed TanStack React Query is 5.104.1. Its `subscribed:false` option
removes only this component's observer, clearing its interval. In query-core,
removing the last observer calls `cancelRetry()` for a request that has not
consumed AbortSignal. Thus a retry already waiting in backoff is stopped too;
`enabled:false` alone would not establish that guarantee. Original retry
configuration is retained, including auction's `retry:1`.

The affected API calls do not forward Query's AbortSignal. **No HTTP cancellation
is implemented or claimed.** An already dispatched request may finish and fill
the Query cache. Tests demonstrate this explicitly. While CN is inactive, that
result cannot cause the deviation view's `abnormal_last_result` write or start
rule metadata requests. Returning to CN resubscribes, uses normal Query
freshness/refetch behavior and can accept/persist an available cached result.

React components, CN tab/filter/search/editor-open state and user enable state
remain mounted. No cache clear/reset/invalidation is introduced in product code.
Query's ordinary garbage collection is unchanged; this is not a promise of
permanent cache retention.

## Shared services remain independent

`useQuoteStatus`, `usePreferences`, `useCustomSignalNames`, Layout, global alerts,
QueryClient defaults and persistence are unchanged. A shared Query may still
fetch when another active consumer needs it, including when its key matches a
hidden page's key. Tests include both an independent polling query and a real
same-key QueryObserver. Disabling the page is not a global kill switch.

Existing CN mutation semantics and already submitted mutations are unchanged.
RuleEditor and other dialogs retain their existing root `active && open` gate;
their shared implementations are outside this repair. Existing confirmation
reset timers are local UI state timers, not data refresh, and remain unchanged.
This task does not establish zero requests, zero persistence or zero notifications
for the whole host application.

## Offline temporal evidence

The two existing page test files retain all prior assertions. Twelve additional
cases use real isolated QueryClients, fake time, mocked local API promises and
storage spies. Shared status hooks and dialogs remain the existing test doubles;
this is not a real-service end-to-end test.

Coverage includes:

- CN initially fetches and polls (counters increase before hiding).
- CN to HK and CN to US stop page polling; invalidation adds no page requests.
- Hidden intraday refresh does not bypass the activity gate.
- Late rules resolve into cache without starting hidden dependent queries;
  after CN metadata loads, hiding and invalidating leaves those counts unchanged.
- Late deviation responses enter cache but do not persist while hidden.
- Deviation overview/watchlist polling, filters and storage resume on CN return.
- Late failed requests and already scheduled retries stop when the page leaves.
- Independent polling and same-key shared observers continue normally.
- Existing CN view/search/editor and direct HK/US fixture isolation assertions remain.

First targeted run: **32 PASS / 1 FAIL**, exit 1, 4.89s wall time. The new late-rule
test supplied rules without the required `conditions` array and rendering failed
at `r.conditions.length`. Only that synthetic test response was completed with
`conditions:[]`; product validation and existing assertions were not weakened.
An intermediate targeted run then passed 34 cases. After expanding deviation
coverage, 36 cases passed. Final targeted run after strengthening metadata
invalidation coverage: **36 PASS**, exit 0, 3.77s wall time.

## Commands actually executed this task

Run from `frontend`; durations below are wall times measured with PowerShell
Stopwatch, not summed parallel worker time.

| Check | Command / scope | Actual result | Exit | Seconds |
| --- | --- | --- | --- | --- |
| Final targeted | `node node_modules/vitest/vitest.mjs run src/pages/MonitorPreview.test.tsx src/pages/AbnormalPreview.test.tsx` | 36 PASS | 0 | 3.77 |
| Related | same runner, the two pages plus `AnomalyMonitoring.test.tsx`, `AnomalyMonitoringPreview.test.tsx`, `MarketSwitcher.integration.test.tsx`, `MarketSwitcher.test.tsx`, `WatchlistPreview.test.tsx`, `RegimePreview.test.tsx` | 122 PASS / 8 files | 0 | 6.20 |
| Full Vitest | discover all `src/**/*.test.{ts,tsx}` / `*.spec.{ts,tsx}` with `rg --files`; run all 54 Vitest files, routing the two `node:test` files to node separately | 550 PASS / 54 files | 0 | 12.85 |
| Native node | `node --test src/components/DimensionMembersDialog.test.ts src/lib/neighborPrefetch.test.ts` | 5 PASS | 0 | 0.94 |
| TypeScript | `node node_modules/typescript/bin/tsc -b` | PASS | 0 | 29.50 |
| Production build | `node node_modules/vite/bin/vite.js build` | PASS | 0 | 18.39 |

Full suite ran on the final product source; the subsequent test-only strengthening
of metadata assertions was followed by the final targeted run above. Existing
React Router future-flag warnings and Vite's large-chunk advisory remain visible.
No tests are excluded to conceal a failure; native-node cases are run by their
own runner. No dependency or build configuration was modified.

Final static handoff checks executed: `git diff --check` PASS,
`git diff --cached --check` PASS, index empty, exact five-file scope PASS.
Complete product/test diff and this document reviewed. High-confidence private
key, GitHub token, OpenAI-style key and literal credential assignment patterns
found **0 matches** across all five candidates. This pattern scan is not proof
that every possible secret encoding is absent.

## Limits and handoff

- Browser acceptance: **NOT EXECUTED**. No real Edge session was launched this
  round. Offline fake-time tests and a successful build are not browser evidence.
- Production validation: **NOT VERIFIED**. No real provider, quote, signal,
  model or production database was accessed; no backend tests or services run.
- No detector, delivery algorithm, production event schema, Provider, frozen
  Momentum contract, shared service or other Agent worktree was modified.
- Longbridge Volume/VR20, split-only price basis, finality, PIT/vintage and
  Universe production blockers retain their existing status.
- Remaining follow-up: human review of these candidates; if desired, controlled
  real-browser network/timing validation before a separately authorized Git close.
