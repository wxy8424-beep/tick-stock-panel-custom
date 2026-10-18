# HK/US Stock Analysis Read-only Preview v1

Task: T-2026-10-18-A05 implementation / T-2026-10-18-A06 acceptance closure.
Date: 2026-10-18. Main baseline: `344bff477fe29820eadf7898416606c484701b2f`.

## Source audit and smallest safe boundary

`frontend/src/custom/stock-analysis/extension.tsx` registers `/stock-analysis`
through its existing extension manifest. Originally its exported page directly
mounted all CN hooks. The initial symbol is empty; `useLastStock('stock-analysis')`
reads `last_stock:stock-analysis` from localStorage in its state initializer and
a mount effect restores that symbol/name. Choosing a security calls remember,
which writes the same key. URL symbol/report/run parameters are not the CN
selection contract and are not a source of Preview identity.

The page's mount effect calls `stockAnalysisStore.loadHistory()` and GET
`/api/stock-analysis/reports`. Although the page comment describes deduplication,
the actual loadHistory implementation itself unconditionally requests the list;
the Preview must prevent mounting, not depend on that comment. HistorySidebar
subscribes to the global report store. It can open reports or delete them through
the existing DELETE endpoint and toast. Those original behaviors are unchanged.

After selection, StockAnalysisBoard mounts Query observers for klineDaily(symbol,
250) with `['kline', symbol, '']` and stockAnalysisLevels(symbol, 250) using the
existing QK.stockLevels. The latter backend endpoint reads enriched daily data
through the repository and computes price levels and indicator series. Neither
query belongs in a synthetic Preview. StockFinancialSearch registers an instrument
search Query hook even when its empty-input request is disabled. LastStockChip
can restore a previous selection. StockPreviewDialog is a lazy shell; an active
symbol mounts its production detail tree. PriceAlertDialog, when opened, queries
levels, preferences and monitor rules; its mutations save/toggle/delete monitor
rules, invalidate Query cache and emit toasts. No such component is reused here.

The original analysis action checks findTodayReport and then calls startAnalysis.
The global store sends POST `/api/stock-analysis/analyze`, consumes the NDJSON AI
stream and automatically POSTs the completed report to `/api/stock-analysis/reports`.
The backend stock_analyzer reads daily/enriched history, technical and limit-up
signal fields, financial tables, optional paper-position context, and constructs
the AI prompt. A stock/index search option or an existing API does not establish
HK/US data compatibility. No financial, AI, paper-position or provider path was
executed for this Preview.

The only original market UI was PageHeader's default CN-only MarketSwitcherBar.
It could not prevent the CN hooks from mounting. This is a narrow L3 entry change:
StockAnalysis now renders StockAnalysisMarkets, which reads the existing URL
`market=CN|HK|US` convention before rendering ChinaStockAnalysis or FixtureAnalysis.
The original CN component body is preserved except for that reviewed rename and
replacement of the default market bar with the same controlled shared bar. No
existing slot can stop parent mount effects, so L1 configuration or L2 toolbar
injection alone would not provide isolation. The registration and route are intact.

## Independent display contract and fixtures

Dedicated contract, Presentation, fixture, page test and this document accompany
the single entry edit: six candidate files. No shared component, Layout, API,
QueryClient, provider, backend, frozen Momentum contract or database is changed.
The historical `custom/damon` frontend namespace is within the main worktree;
this task does not operate the separate Damon AI worktree.

Each market owns two authored examples: `fixture-stock-HK-A/B` and
`fixture-stock-US-A/B`, with unmistakably synthetic symbols `SYNTH-A/B.HK/US`,
names, synthetic exchange and SYNTHETIC_SAMPLE security type. HKD and USD remain
separate. These are not copied company records or real listing identities.

The common existing Preview provenance is reused: PREVIEW, synthetic-fixture,
data_mode=preview, is_production=false, is_investment_signal=false,
fixture_only=true and synthetic=true. Runtime validation rejects opposite markets,
non-synthetic identities, mismatched currency/evidence, extra fields, nonfinite
numbers, nonnumeric parameters, duplicate records and missing null reasons.
Execution is always BLOCKED, irrespective of sample completeness.

Displayed fields: identity/name/English name/market/currency/exchange/security
type; fixed last/change/changePercent/open/high/low/previousClose; authored MA20;
source, evidence, blockers and warnings. Change percent uses explicit percentage
points. No metric, OHLC history, score or research result is computed from quotes.
MA20 is a standalone synthetic display value, not proof of twenty source sessions.
There is no chart/history download or invented AI research report.

US sample B's last/change/changePercent are null. Sample B MA20 is null in each
market. volume_ratio_20 is null. Sector, industry, price_basis, volume_unit,
available_at, source_vintage and production_report are always null with explicit
reasons. Unknown is not zero; generated_at is not upstream availability.
Trading date is fixed `2026-09-16`; generated_at is authored
`2026-09-17T09:00:00Z`, not current service health or a candle publication time.

## Interaction and execution isolation

Search, accessible shared three-state table sorting and detail selection are
local state. Market-keyed remount resets selection/search/sort across HK/US and
when returning to CN. Unrelated URL parameters are retained, but real-looking
symbol/report/run parameters cannot load production objects in Preview.

HK/US never mounts ChinaStockAnalysis, StockAnalysisBoard, HistorySidebar,
StockFinancialSearch, StockPreviewDialog, PriceAlertDialog or AnalysisKChart.
It does not call useLastStock, report-store hooks/actions, Query hooks, API client,
fetch, EventSource, storage mutations or notification helpers. No hidden CN
business component is mounted underneath the display. Twelve visible native
disabled buttons explain that AI, report generation/save, reminders, watchlist,
monitor writes, refresh, subscriptions, downloads, financial sync, trading and
production evaluation/scoring cannot execute. There are no success callbacks.

Visible declaration: **演示个股分析｜合成数据｜只读｜非生产研究｜不构成投资建议**.
Subtitle: Synthetic Data / Read-only / Not production research. Error, loading
and empty states retain the declaration and disabled actions; no real fallback.

Preview-own isolation means business requests=0, storage writes=0 and
notifications=0 when the actual page is mounted independently on HK/US.
This is not a whole-application zero-side-effect promise. Layout still mounts
global alert consumers, Query persistence, StockAnalysisHost and bubbles. An
already active CN task may continue through its existing global store when
leaving CN; Preview does not start it, cancel it, clear reports or disable host
functionality. Production behavior of warmed profiles/tasks is not validated.

## A05 historical validation (not A06 reruns)

- Targeted: 25 PASS, exit 0, 2.88s.
- Related: 87 PASS / 6 files, exit 0, 4.18s.
- Complete Vitest: 459 PASS / 51 files, exit 0, 10.34s.
- Native node:test: 5 PASS, exit 0, 0.55s.
- TypeScript: PASS, exit 0, 17.22s. Vite production build: PASS, exit 0, 16.97s.
- CN source reversal comparison: exact match to the baseline after undoing only
  the reviewed shell, import and market-bar substitutions.

Real Edge history is deliberately not rewritten as a successful clean run:

1. First launch could not establish CDP; exit 1 after 20.28s; zero checkpoints.
2. Authorized real Edge executed desktop 1440x1000 and narrow 390x844 checks:
   **30 PASS / 1 FAIL**, exit 1, 41.82s, five actual screenshots. Both isolated
   markets had zero own requests/writes/notifications and no CN component tree.
   Layout/switch/reload/keyboard sorting checks passed. Page console had no error.
   The failed combined error checkpoint included three driver-layer CDP
   `Invalid InterceptionId` errors from Fetch interception callbacks; these are
   not Runtime.exceptionThrown page exceptions. Original report is retained as
   `frontend/.vite/stock-analysis-A05-20261018/browser-attempt2-results.json`.
3. The driver was adjusted only to preserve interception-protocol warnings
   separately from page exceptions. The requested rerun was **NOT EXECUTED**:
   automatic approval review returned `stream disconnected before completion`.
   No retry or bypass occurred, and no product code/assertion was changed.

Local ignored QA scripts, logs, reports and screenshots remain under
`frontend/.vite/stock-analysis-A05-20261018/`; these are acceptance artifacts,
not source market data and not candidates for Git.

## A06 acceptance closure

Initial A06 checks confirmed main, expected baseline, exactly five un-staged
implementation candidates and an empty index. This document is the sixth planned
candidate. Product candidates are retained for review, not rewritten.

### A06 browser attempt: NOT EXECUTED

A dedicated ignored A06 QA directory preserves a copy of the A05 driver and
isolated entry, without overwriting A05 evidence. The local driver now prepares
native Tab/Enter CN -> HK and Tab/Space HK -> US switching, followed by return to
CN, as well as the existing direct/reload/desktop/narrow/action checks. These
changes are preparation, **not executed browser evidence**.

The single requested authorized run was rejected before process creation because
automatic approval review failed with `stream disconnected before completion`
(transport/network response decoding failure). This was not a determination that
the action was unsafe. The command was NOT EXECUTED: no A06 Edge process, new
checkpoint result or screenshot was produced. Approval was not retried; no alternate
launch, permission bypass, account/config change or production call was attempted.
Per the A06 instruction, browser work stopped and pure local checks continued.

Whether Invalid InterceptionId would recur in A06 is NOT VERIFIED, not a claimed
absence. A05's three original protocol errors and 30/1 result remain intact. There
is no evidence of a newly confirmed product defect, but A06 native keyboard market
switching and a clean browser rerun remain outstanding. Browser acceptance for
this round is **NOT EXECUTED**; the prior acceptance remains PARTIAL.

### A06 final source review

All five implementation candidates retained exactly their initial A06 SHA256
hashes. No product source, fixture or test was edited to obtain passing results.
The only additional candidate is this document. The ignored source-review helper
reverses precisely the reviewed ReactNode import, market wrapper/child rename,
controlled bar and import additions; the result matches the complete HEAD source.
The StockAnalysisBoard/HistorySidebar/modal/helpers/manifest tail matches directly.

- Entry: branching precedes useLastStock, loadHistory, search Query and all CN
  business children. CN's original mount effects, selection/query/action handlers
  remain unchanged within its child; leaving the market unmounts that child by
  design and returning remounts its original effects. No active global CN task is
  canceled, restarted or impersonated by Preview.
- Contract: a small display schema, exact properties and synthetic provenance,
  matching identity/market/currency/evidence, finite numbers and required null
  reasons. Unknown production fields and VR20 cannot be replaced by guessed values
  or execution READY. It is not a backend schema or a production input validator.
- Presentation: local state and pure shared sorting; native controls and disabled
  actions without execution handlers. No Query/API/store/notification/persistence
  consumer. No hidden production component. Local title padding changes only the
  Preview; no Layout/shared MarketSwitcher change.
- Fixture: distinct market identities and authored values, fixed dates, explicit
  currencies, reasons and supplier blockers. No real company/data claims, computed
  score, synthetic historical archive or production repository writes.
- Tests: real original page handlers and useLastStock exercise initial history,
  query arguments, selection storage, same-day confirmation, report view/delete,
  analysis dispatch and reminder/detail mounting with controlled substitutes.
  HK/US assertions require every business hook/action/API spy, Storage mutation,
  fetch/EventSource and notification spy to remain untouched. Substitute CN
  components are explicitly described, not claimed as end-to-end execution proof.
  Source review and the historical unmocked page-boundary browser component tree
  provide separate support for non-mounting; mocks alone are not the whole proof.
  No existing CN test or assertion was removed or weakened.

**Final diff review: PASS**, within these source/offline boundaries; no P1/P2 found.

### A06 local checks actually executed

Commands run from frontend using installed runner binaries; no dependency install,
thread override, skipped failing case or product-configuration change:

| Command | Result | Exit | Wall seconds |
| --- | --- | --- | --- |
| `node node_modules/vitest/vitest.mjs run src/pages/StockAnalysisPreview.test.tsx` | 25 PASS | 0 | 4.70 |
| Same runner with StockAnalysisPreview, FinancialPreview, SignalPreview, MarketSwitcher integration, MarketSwitcher and StockDataTable test files | 87 PASS / 6 files | 0 | 6.36 |
| Same runner with every discovered Vitest test path, explicitly supplied as arguments | 459 PASS / 51 files | 0 | 14.89 |
| `node --test src/components/DimensionMembersDialog.test.ts src/lib/neighborPrefetch.test.ts` | 5 PASS | 0 | 0.60 |
| `node node_modules/typescript/bin/tsc -b` | PASS | 0 | 26.66 |
| `node node_modules/vite/bin/vite.js build` | PASS; Vite 16.48s | 0 | 17.42 |
| `node .vite/stock-analysis-A06-20261018/source-review.mjs` | exact CN reversal and business-tail comparison PASS | 0 | 0.49 command wall |

Discovery used `rg --files src` with test/spec .ts/.tsx globs. The two files
importing node:test were assigned to the native runner, and every other discovered
test to Vitest; all 53 files ran on their appropriate runner, with no failing test
excluded. Existing React Router future notices and Vite large-chunk warning remain.
Logs and source-review.json are in the ignored A06 QA directory.

`git diff --check`, full six-file source/document review, explicit candidate-list
comparison and high-confidence secret-pattern scan passed. The secret scan checks
private-key headers, GitHub/OpenAI-style tokens and long literal credential
assignments; zero hits. It does not prove absence of every conceivable secret.
Untracked candidates were also checked for trailing whitespace. Exactly six
planned candidates; no unexpected seventh file or database/config/dependency file.
QA artifacts were confirmed ignored. No staged change; HEAD/branch unchanged.

### A06 disposition

- CN compatibility: **PASS**, source comparison and controlled offline actions.
- HK Preview isolation: **PASS**, source/offline checks plus A05 scoped browser
  evidence; this is not a new A06 browser pass or a whole-host guarantee.
- US Preview isolation: **PASS**, with the same evidence boundary.
- Market switching: **PASS** for offline remount/history/URL behavior and the
  recorded A05 browser mouse switching; A06 native keyboard switching NOT EXECUTED.
- Browser acceptance: **NOT EXECUTED** this round, approval transport blocked.
- Final diff review / sensitive scan / exact six-file scope: **PASS**.
- Production validation: **NOT VERIFIED**.

Local review can proceed. Recommend closing the outstanding A06 real Edge/native
keyboard acceptance after approval transport recovers before an unconditional Git
closure recommendation. No staging, commit or push is performed in this task.

## Remaining production boundaries

**Production validation: NOT VERIFIED.** Synthetic acceptance does not validate
real HK/US quotes, research, AI execution, report persistence or alert delivery.
Longbridge Volume/VR20, split-only price basis, historical PIT/vintage and formal
Universe remain BLOCKED. Daily finality remains PARTIAL; corporate actions remain
UNKNOWN. No supplier blocker is promoted by a valid display fixture.

No Git staging, commit, push or synchronization is authorized in A06. Human review
must precede any subsequent Git closure. No other page is developed in this task.
