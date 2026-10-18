# HK/US Signal Definition Preview v1

Date: 2026-10-18. Main baseline: `dd0f04e20236ae1c9d7dc76dce5d3f0a80a33372`.

## Audit and architecture

`custom/signals/extension.tsx` registers `/signals`. Original `SignalsBody` loads the global custom-signals/options APIs, toggles/saves/deletes definitions and mounts the real CustomSignalDialog. Opening that dialog checks AI availability; it can generate definitions using AI and save them. SignalTriggerActions can create or link definitions from strategy/backtest consumers. Backend saves modify user definition JSON and invalidate signal/strategy/repository caches; even list loading can create a directory. These components must never mount in Preview.

The smallest safe boundary is a narrow L3 page-entry change: a URL `market` branch before CN child hooks. Existing configuration/toolbar slots cannot prevent mounting. No registry, route path, API client, backend, global Layout or shared table change. `SignalsBody`, dialog, highlight, conditions, toggle/delete/save behavior remain original. The CN shell only receives market controls. This historical `custom/damon` namespace is inside main, not the Damon AI worktree.

## Independent read-only contract

Six planned files: existing signals extension; new `custom/damon/signal-preview/{contract.ts,Presentation.tsx}`; `tests/fixtures/signal_preview/index.ts`; `src/pages/SignalPreview.test.tsx`; this document.

HK and US each allocate four fixed, separate `fixture-signal-{market}-{n}` definitions. `fixture_version=preview-v1`, trading_date `2026-09-16`, generated_at `2026-09-17T09:00:00Z` are authored sample identities/times, not observed runtime data. No CN definitions or production IDs are copied. The fixture import follows existing frontend Preview conventions and has no provider or API imports.

Provenance reuses IndexPreviewProvenance: PREVIEW / synthetic-fixture / preview / is_production=false / is_investment_signal=false / fixture_only=true / synthetic=true.

Conditions are a separate display DTO: left/op/right plus explicit session offsets and reasons. AND only. Right values distinguish finite numeric constants from field references. A small display-only vocabulary is not a production field registry. Missing/unsupported fields are null with reasons; no expression compilation, interpretation, evaluation, fallback, OR or guessed offsets. READY only means sample structure complete; execution remains BLOCKED. production_version, last_trigger_at, trigger_count and production_binding are always null with reasons. There is no hit rate or real effect statistic.

Runtime validation rejects unexpected schema properties, mixed identity/markets, production flags/IDs, mismatched evidence, duplicate IDs, invalid dates, missing reasons, invalid types/operators/offsets, nonfinite parameters, incomplete READY samples and production execution readiness. Failure renders the existing ErrorState, never a production fallback.

## Interaction and isolation

URL `market` defaults CN and preserves other parameters. Market-keyed remount resets filters/selection/detail/errors. HK/US ignore real highlight/id/edit/run parameters; no production object restoration. No persistence of local UI state. Search, direction/timeframe/quality filters, shared three-state accessible sorting, details and fixed provenance work locally. Conditions use a plain read-only table rather than the editable production ConditionEditor.

All seven side-effect operations (save/edit/toggle/delete/AI/register/evaluate) are genuinely disabled with an explanation, including empty/error/loading states; no placeholder success callbacks. No SignalsBody, CustomSignalDialog or SignalTriggerActions in HK/US. Preview has no Query hooks, API client, fetch/EventSource, notification or storage writes. Host Layout behavior is separate and is not modified to hide requests.

Visible declaration:

> 演示信号定义｜合成数据｜非生产配置｜不评估条件、不产生真实信号｜不构成投资建议

## Validation

All results below were actually executed for this task; earlier Factor Preview results are not substituted for this page's validation.

- Initial page/contract targeted run: 30 PASS. Additional explicit negative cases increased this to **36 PASS**, executed again in both related and complete runs.
- Related run: **80 PASS / 6 files**: SignalPreview, FactorPreview, StrategyPreview, ConditionEditor, StockDataTable, MarketSwitcher integration. CN tests use the real SignalsBody and CustomSignalDialog with API/query/mutation substitutes; test edits/saves original conditions, toggle, two-step delete and highlight. No assertion in an existing test was modified.
- Complete Vitest: **434 PASS / 50 files**. `pnpm exec vitest run --exclude src/components/DimensionMembersDialog.test.ts --exclude src/lib/neighborPrefetch.test.ts`.
- Native Node: **5 PASS**. `node --test src/components/DimensionMembersDialog.test.ts src/lib/neighborPrefetch.test.ts`. These files use node:test, not Vitest; neither was omitted from its appropriate runner.
- Final `pnpm build` (`tsc -b && vite build`): **PASS**, including the added negative test cases. Existing React Router future notices and Vite large-chunk warning remain.
- CN source comparison: after removing only the reviewed market shell rename/control injection, the original component body and all subsequent business functions are an exact textual match to HEAD. Production signal types, API, consumers and backend files have no diff.
- Diff/format/sensitive scan and final exact six-file scope review: PASS. No staging was performed; the index is empty. No credentials, databases, dependency manifests or generated files enter the candidate list.

### Real Edge: whole application and page boundary are separate evidence

Actual Microsoft Edge **154.0.4258.62**, headless native CDP, actual React frontend and existing Tailwind; dark theme, **1440x1000** and **390x844**. Both runs use fresh QA profiles, a loopback server with synthetic API responses, no backend proxy and blocked external page requests. No actual backend/provider/model/database is contacted.

Whole-app evidence: `frontend/.vite/signals-browser-qa-20261018/{run.mjs,results.json}` and **13 actual screenshots**. **48 checkpoints: 46 PASS, 2 FAIL**. Do not relabel this run as all-pass:

- Direct HK/US URLs containing real-looking highlight/id/edit/run values do not restore production objects. Market switches/reload/back, search, all filters, sorting, actual native Tab/Enter/Space, aria-sort, detail/missing reasons, empty state and the controlled real error component work. All seven production action buttons are disabled. Native Enter/Space each advance sorting once; mouse clears the tri-state.
- HK/US runtime component inspection excludes ChinaSignals, SignalsBody, CustomSignalDialog and SignalTriggerActions. Original CN list/highlight and actual edit dialog render using synthetic API input; cancel and leaving CN unmount the dialog. Browser does not save/toggle/delete real definitions; those paths are covered offline with substitutes.
- At 390px, heading left=56 and fixed menu right=46 for both markets; document scrollWidth=390. The wide shared table scrolls inside its own container. Desktop uses original 20px header padding. Desktop, narrow, keyboard focus and CN dialog screenshots were inspected.
- Both failed assertions required *all whole-app storage writes* to be zero. Captured stacks show one `tf-query-cache` setItem per market through TanStack's sync-storage persister. This is the existing host `main.tsx` PersistQueryClientProvider / `lib/queryPersist.ts`, not a Preview write.
- The whole-app log also contains **six synthetic GET /api/custom-signals requests across HK/US-labelled navigation phases**. Existing Layout mounts AlertToastContainer, which invokes useCustomSignalNames and queries the global definitions. It remains mounted even though the page's CN signal body is absent. The host cache whitelist includes custom-signals. These requests are reported, not hidden or silently counted as zero. No field-options request from HK/US and no non-GET API request were observed; page/console errors were zero. Host code was deliberately not modified.

To test the required *Preview itself* boundary independently, the supplemental harness mounts the **actual exported Signals page** under BrowserRouter, without Layout/AlertToast/persistent Query provider, and exercises the same production-looking URLs, search/filter/detail/disabled buttons and native keyboard sorting. This is not a replacement claim for whole-app behavior.

Final page-boundary evidence: `frontend/.vite/signals-browser-component-final-20261018/`, **10 PASS / 0 FAIL**, **2 screenshots**, **zero API requests including GET**, zero local/session Storage mutations and notifications, zero page/console errors. Both market runs kept all six candidate file hashes unchanged. The first supplemental probe captured the same 10 passing observations but its driver stalled during shutdown and was interrupted (exit 1); its artifacts remain in `signals-browser-component-20261018/`. Only QA-driver bounded close/connection cleanup was corrected before the final exit-0 run; no product code or assertion was changed to suppress a failure. Owned browser/server processes were stopped.

Conclusion: scoped Preview isolation is verified by source, offline spies and actual page-boundary browser observation. **The whole host application is not request-free or persistence-free on HK/US routes.** If a future task requires that stronger boundary, it needs separate authorization to audit/redesign host global consumers; this task does not do so.

Browser harnesses/screenshots stay in ignored local QA directories, not production data or the candidate commit. Light theme, physical touch devices, actual supplier-failure recovery, real provider/model/database/condition evaluation and production signal execution: **NOT RUN**. The error screenshot is controlled component-state evidence, not a real supplier outage.

## Remaining boundaries

No production signal producer, schema change or market-scoping of the global definition API. Existing consumers remain untouched. Longbridge Volume/VR20, split-only price basis, PIT/vintage and real Universe remain BLOCKED; Daily finality PARTIAL and corporate actions UNKNOWN remain unchanged. Preview does not establish production readiness. No staging, commit or remote operation; retain candidates for human review.

## T-2026-10-18-A03: causal acceptance closure (2026-10-18)

Agent A / MAINLINE. This section records a new run; the preceding 46 PASS / 2 FAIL
whole-application result and 10 PASS page-boundary result remain historical,
unchanged evidence. The two whole-app zero-storage assertions are not relabeled
PASS, removed or weakened.

### Protected candidate and comparison design

Initial repository root is the main worktree, branch `main`, HEAD
`dd0f04e20236ae1c9d7dc76dce5d3f0a80a33372`, with exactly the six planned
uncommitted files and an empty index. Five source/test file hashes match the
previous page-boundary browser artifact. The document hash differs from that
artifact's earlier document snapshot; that artifact alone cannot establish an
exact match for the subsequently completed document. Existing text was retained;
this section is appended. No product source or test was changed in A03.

Actual Edge **155.0.4283.62** ran through native CDP with a separate QA profile,
fresh incognito browser contexts, synthetic loopback HTTP responses, a Vite
configuration with no backend proxy, and blocked external page requests. No real
backend, model, provider, signal service or production database was used.

Four arms were tested:

1. **Baseline**: `git show HEAD:frontend/src/custom/signals/extension.tsx` served
   from memory, preserving the original CN page even on HK/US-labelled URLs.
2. **Candidate**: the actual current six-file candidate; no production hook edits.
3. **Host-only control**: baseline Signals body replaced in memory by an inert
   URL-aware element, retaining the real Layout, alert consumer, Query provider
   and persister. This is an ablation control, not a shipping alternative.
4. **Page boundary**: actual exported candidate Signals under BrowserRouter,
   without Layout, alert consumers or Query/persistence provider; HK/US only.

Common read-only in-memory probes subscribe to QueryCache and wrap persistClient,
fetch and Storage methods, forwarding original arguments/return values. They
capture event sequence, performance.now, Query key/type/action/observer count,
persisted query keys, storage area/key and call stacks. CDP separately captures
network initiators/async stacks. A render probe captures the useCustomSignalNames
caller. No query invalidation, cache mutation, persistence suppression or fake
zero-request response is introduced by the probes. Instrumentation has timing
overhead, so absolute latency is not a production performance measurement.

Each arm ran twice; baseline/candidate execution order was reversed in round 2.
There were **24 isolated contexts and 64 phase snapshots**. Each phase observes
2.7 seconds after the expected page mounts, exceeding the persister's 2-second
throttle for these fixed quick responses. Cases include fresh HK/US open,
same-context refresh, and CN -> HK -> US -> CN URL navigation. Since baseline has
no enabled HK/US switch, the matched navigation uses history/popstate in both
arms; candidate additionally exercises its actual market buttons through DOM
clicks in the real browser, twice. This is not a renewed native pointer/keyboard
or visual-layout acceptance run.

Local reproducible evidence (ignored QA artifacts):

- `frontend/.vite/signals-causal-A03-20261018/run.mjs`, `component.jsx`:
  synthetic browser driver and isolated page entry.
- `results.json`: complete per-document events, request initiators, raw stacks,
  snapshots, errors, blocked destinations and before/after candidate hashes.
- `analyze.mjs`, `analysis.json`: per-phase deltas (not cumulative counts confused
  with new writes), comparisons and **22 passing causal/boundary checks**.
- `source-review.mjs`, `source-review.json`: exact CN-source reversal comparison.
- `run-final2.log` and runner-specific test/build logs.

All six file hashes were unchanged throughout the completed browser experiment.
The only subsequent candidate edit is this documentation section. The earlier
driver failures are preserved separately: sandbox CDP unavailable (40.14s), page
versus browser CDP endpoint mismatch (16.56s), then an ASI boundary error in the
memory-only main.tsx probe (54.71s). All exited 1 without completing comparison;
none is counted as an acceptance pass. Fixes only affected ignored driver code.

### Observed causal results

Both repetitions produced the following per-phase counts:

| Phase | Baseline | Candidate | Host-only control |
| --- | --- | --- | --- |
| Cold HK/US: actual GET `/api/custom-signals` | 1 | 1 | 1 |
| Cold HK/US: GET field options | 1 | 0 | 0 |
| Cold HK/US: each of `tf-ext-pages-seed`, `monitor_last_seen_total`, `tf-query-cache` | 1 each | 1 each | 1 each |
| Cold HK/US: persistClient requests before throttle | 23 | 21 | 21 |
| Cold HK/US: settled custom-signals observers | 2 | 1 | 1 |
| HK/US refresh: custom-signals/options GET | 0 / 0 | 0 / 0 | 0 / 0 |
| HK/US refresh: cache writes / other storage writes | 1 / 0 | 1 / 0 | 1 / 0 |
| HK/US refresh: persistClient requests | 7 | 7 | 7 |
| CN initial: custom-signals/options GET | 1 / 1 | 1 / 1 | 1 / 0 |
| Each short-window market switch/return: new fetches, storage writes, persistence requests | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |

The actual candidate button sequence agrees with its matched history navigation.
Candidate observer count is **2 -> 1 -> 1 -> 2**, baseline stays 2, control stays
1. This confirms a real subscription change; it would be incorrect to claim
the market boundary has no indirect cache/subscription effect. In this observed
window it changes observer events and removes two initial persistence requests,
without causing additional storage writes or signal GETs.

Persisted key content also differs intentionally: fresh candidate HK/US and
control omit `custom-signals-options`; baseline includes it. Both retain host
`custom-signals`, settings, preferences and capability-matrix keys. After CN has
loaded options, the shared host cache can retain that CN key on an HK/US route;
that is not a new Preview request, nor a globally market-partitioned cache claim.

Observed call chains:

- `Layout -> AlertToastContainer -> useCustomSignalNames -> QueryObserver /
  customSignalsList -> api.request -> fetch`. The actual render stack identifies
  AlertToastContainer, the candidate has one signal observer, its CN body is absent,
  and the host-only control still fetches once. Therefore remaining GETs are not
  inferred solely from unchanged host source. All responses were synthetic;
  the frontend GETs really occurred and are not reported as zero.
- `QueryCache added/updated -> persistQueryClientSave -> wrapped original
  persistClient -> sync-storage persister throttle -> Storage.setItem`.
  Dependency source `query-persist-client-core/src/persist.ts` subscribes to
  added/removed/updated, not observerAdded/observerRemoved alone. Thus changing
  subscriptions need not create a cache write.
- `tf-ext-pages-seed` comes from Layout's existing seed effect;
  `monitor_last_seen_total` from Layout -> monitorBadge.setCurrentTotal ->
  writeSeen. These additional cold-profile writes were not part of the earlier
  post-interaction zero-write assertions, but are explicitly recorded here.

Example **candidate round 1 cold HK**, milliseconds since that document's time
origin: custom-signals added 1690.5; observerAdded 1897.4; updated/fetch 1897.5;
fetch invocation 1897.6; updated/success 1965.3; cache setItem 3881.0.
Seed and monitor writes occurred at 1953.4 and 2008.8. The sample is a real
instrumented browser timeline, not a trading timestamp or a fixed latency promise.
Raw events and persistClient invocation stacks preserve the complete ordering.

### Verdict and limits

- **PASS, within the measured scenarios**: causal attribution of the observed
  persistence writes and remaining signal GET to existing host consumers;
  candidate causes no additional observed request/write count. Host ablation and
  matched baseline observations support the source chain.
- **PASS**: page-boundary arm has zero fetches, local/session storage mutations,
  notifications/audio/speech, across both markets and refresh in both rounds.
  Candidate HK/US does not mount ChinaSignals, SignalsBody, CustomSignalDialog or
  SignalTriggerActions; it has zero field-options requests in those phases.
- **FAIL for the stronger whole-application-zero-write requirement**: it remains
  false. The historical 46/2 result stands. New causal checks answer attribution,
  not a replacement or relaxation of those assertions. No host capability was
  disabled or changed to obtain green results.
- **PASS for current CN offline compatibility**: source review reproduces the
  exact HEAD file after reversing only the reviewed market shell; SignalsBody
  and all following business functions are textually identical. CN targeted
  tests exercise highlight, list/options, original editor/save, toggle and
  two-step delete with substitutes. Browser CN initial GET counts match baseline.
- **NOT VERIFIED**: all possible timing interleavings, stale/GC windows beyond
  this short run, offline/reconnect behavior, long-lived warmed user profiles,
  real supplier outages, real production services or execution. Existing host
  requests/persistence remain enabled. No global no-side-effect guarantee follows.

There were zero page/protocol errors and zero non-GET requests to the synthetic
API server. Existing update checks attempted external requests (32 across all
whole-app arms); CDP blocked them. They are retained in the evidence rather than
described as no attempted requests. No production data path was used.

No product fix was necessary or made. The expected removal of CN observers and
options from HK/US does not justify rewriting host alert or persistence logic.

### A03 regression checks actually executed

`pnpm exec vitest ...` first exited 1 before starting Vitest because the available
pnpm wrapper attempted dependency installation/removal and aborted without a TTY
(`ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY`, wall 3.82s). No CI override, purge
confirmation, reinstall or dependency/configuration change was performed.
The existing installed runner binaries were then invoked directly:

| Command from frontend | Result | exit | wall seconds |
| --- | --- | --- | --- |
| `node node_modules/vitest/vitest.mjs run src/pages/SignalPreview.test.tsx` | 36 PASS; Vitest 19.62s | 0 | 22.48 |
| Same runner with SignalPreview, FactorPreview, StrategyPreview, ConditionEditor, StockDataTable, MarketSwitcher integration and MarketSwitcher component test files | 84 PASS / 7 files; 4.53s | 0 | 5.47 |
| `node node_modules/vitest/vitest.mjs run --exclude src/components/DimensionMembersDialog.test.ts --exclude src/lib/neighborPrefetch.test.ts` | 434 PASS / 50 files; 11.43s | 0 | 12.35 |
| `node --test src/components/DimensionMembersDialog.test.ts src/lib/neighborPrefetch.test.ts` | 5 PASS | 0 | 0.60 |
| `node node_modules/typescript/bin/tsc -b` | PASS | 0 | 26.57 |
| `node node_modules/vite/bin/vite.js build` | PASS; build 18.09s | 0 | 19.00 |
| `node .vite/signals-causal-A03-20261018/run.mjs` (completed real Edge run) | 24 contexts / 64 snapshots, no page errors | 0 | 232.06 |
| `node .vite/signals-causal-A03-20261018/analyze.mjs` | 22 causal/boundary checks PASS | 0 | recorded in local command output |
| `node .vite/signals-causal-A03-20261018/source-review.mjs` | exact CN comparison PASS | 0 | recorded in local command output |

The two excluded Vitest paths are native node:test files and were run with their
correct runner above; no failing Vitest case was excluded. Existing Router future
notices and Vite large-chunk warning remain. No baseline assertions were edited.
Full visual/keyboard acceptance from the old 46/2 run was not rerun as such;
no shared UI component or layout was changed. A03 adds causal browser evidence,
not new visual screenshots or production validation.

### Next mainline page selection (planning only)

| Candidate | Actual dependency / effect boundary | Cost and risk |
| --- | --- | --- |
| Individual stock analysis | `custom/stock-analysis/extension.tsx`: useLastStock, mount-time loadHistory, klineDaily/stockAnalysisLevels, price-alert dialog, history and AI actions. `stockAnalysisStore.ts` streams analysis, then saves a report; backend stock_analysis exposes analyze/reports POST and DELETE. | Medium isolation risk, smallest single page boundary. Reuse financial/indices read-only selection, provenance and pure chart presentation only after checking its props. No real report store or dialog in Preview. |
| Concept/industry analysis | Two separate large extensions, extDataList/rows, marketSnapshot aggregation, local field preferences, extDataPullRun mutations, RPS/rotation and member dialogs. | Medium/high scope and taxonomy risk. Both market membership and metrics need independent authored fixtures; CN classifications cannot be relabeled HK/US. |
| Backtest read-only Preview | Backtest -> StrategyBacktest / RobustnessValidation -> optimizer/walkforward; research candidates mutate/publish strategy config, reconnect restores tasks, results persist to storage. | Highest state/execution isolation and regression cost; old factor/mining redirects and router state also need explicit guards. |

**Unique first choice: individual stock analysis `/stock-analysis` read-only
HK/US Preview.** It offers a useful per-security inspection screen with a smaller
entry boundary than two taxonomy pages or the task-restoring backtest workbench.
This is a sequencing decision, not a production-readiness claim.

Minimal next task, requiring a separate instruction before coding:

1. Branch at StockAnalysis entry before useLastStock/loadHistory and all CN hooks;
   preserve the CN child exactly. Do not change the globally mounted analysis host.
2. Add dedicated Preview contract, separate fixed HK/US fixtures, Presentation,
   page tests and documentation (one entry edit plus five dedicated files).
3. Use fixture-only selection, dated price/chart samples and authored level
   descriptions; unknown adjustment/volume/PIT/report fields stay null with reasons.
   No generated AI report, computed production indicator or investment conclusion.
4. Do not mount StockFinancialSearch, production StockPreviewDialog,
   PriceAlertDialog or CN report actions in Preview. Analysis, report save/delete,
   notification and refresh actions remain disabled; no last-stock persistence.
5. Test CN selection/history/editor compatibility with substitutes, malicious
   URL/local-storage identities, HK/US remount isolation, null reasons and zero
   page-owned calls/writes. Explicitly distinguish an already active CN global
   task from a new Preview-triggered task; do not disable host behavior to hide it.
6. Repeat real Edge page-boundary plus host-aware comparison, desktop/narrow,
   then affected/full frontend checks. All existing supplier blockers remain.

No next-page implementation, staging, commit, push or Git synchronization occurs
in A03. Only this existing candidate document is extended; five source/test
candidates remain intact, and local QA artifacts stay ignored for human review.
