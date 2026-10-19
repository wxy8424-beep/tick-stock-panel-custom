# HK/US Backtest read-only Preview v1

Task: T-2026-10-19-A10 · Agent A / MAINLINE · 2026-10-19.
Baseline: main, `b5f79d17b9647d0625b560c38859b2060be40f66`, initially clean index and worktree.

## Source audit and candidate selection

Audit uses current source, not completion titles. Each of the eight existing pages below already has its own market dispatch, local Presentation, fixture and `*Preview.test.tsx`. Adding another implementation would duplicate completed work. All dispatches can gate CN child mounting; their existing production paths remain outside this change. Estimates include entry, DTO, Presentation, fixture, tests and documentation for a new page; existing completed pages need **zero** files for this task.

| Candidate / actual entry | CN mounts, requests and effects | Storage / polling / actions | Existing isolation / cost / decision |
| --- | --- | --- | --- |
| 自选: `src/pages/Watchlist.tsx` | ChinaWatchlist → list/groups, enriched, daily/minute batches; child instrument search | Query cache, localStorage column preferences, effects and delay timer; add/remove/clear/reorder/group mutations | WatchlistMarkets before ChinaWatchlist; watchlist-preview + WatchlistPreview tests; complete, 0 files, no new scope |
| 指数: `src/pages/Indices.tsx` | ChinaIndices → indexQuotes, indexDaily, indexMinute; selected date/symbol effects | Query cache; syncIndexDaily mutation; fixed CN index/date contract | IndexMarkets + index-preview + IndicesPreview / Indices tests; complete. Lowest-risk reserve **if** a specific missing requirement appears, not another implementation now |
| 复盘: `src/custom/review/extension.tsx` | ChinaReview → overviewMarket(asOf), reports, channel/mode queries; streaming report effect | Query cache, schedule/update/delete, auto reportSave after stream completion, date-specific dragon-tiger detail | ReviewMarkets + review-preview + ReviewPreview tests; complete, 0 files; higher write risk |
| 监控: `src/custom/monitor/extension.tsx` | ChinaMonitor → alerts/rules; rule dialogs query groups/list/custom signal names/schema | Query cache, 10/120s alert polling, confirmation timer; alert clear/delete, monitor rule save/delete, realtime config changes | MonitorMarkets + monitor-preview + MonitorPreview tests; complete, 0 files; worker/alert actions are production-bound |
| 异动: `src/custom/abnormal/extension.tsx` | ChinaAbnormal → abnormalIntraday / abnormalOverview / watchlist; auction child benchmark | Cached historical display, localStorage historical calculation metadata, market-hours-dependent polling; existing rule navigation and intraday refresh | AbnormalMarkets + abnormal-preview + AbnormalPreview tests; complete, 0 files; CN auction/threshold contract is not HK/US detection evidence |
| 数据: `src/pages/Data.tsx` | ChinaData → coverage/jobs/active job, data sources/settings/status; visibility and active-job effects | Query cache, page preferences, progress/timer behavior; pipeline run/cancel, clear, schedule, ext config mutations, daily sync | DataMarkets + data-preview + DataPreview tests; complete, 0 files; persistence/refresh actions must remain gated |
| 财务: `src/custom/financials/extension.tsx` | ChinaFinancials → capabilities/matrix, useFinancialStatus/Sync, search/detail/history | Query cache, last-stock storage; 3s polling while sync active; table/full sync, CN financial detail and AI descendants | FinancialMarkets + financial-preview + FinancialPreview tests; complete, 0 files; currency/report/availability semantics remain independent |
| 策略: `src/pages/Screener.tsx` | ChinaScreener → factors/strategies, status, signal/minute batches, dialogs; multiple effects | Query cache and saved columns; minute status polling, task timers; screener run, reload, watchlist, monitor/config mutations | StrategyMarkets + strategy-preview + StrategyPreview tests; complete, 0 files; actual `/screener` entry, not an invented `/strategy` route |
| 回测: `src/pages/Backtest.tsx` | Originally no market dispatch. StrategyBacktest mounts factor columns/library, screener strategies, selected strategy, custom signal options, data status; RobustnessValidation mounts optimizer/walk-forward | Query cache + storage drafts; reconnect effects, task registry GET/adoption, SSE and retries; start/stop, save config/candidate, regime recompute, dialog mutations | **Unique unfinished safe candidate**: insert dispatch before all CN hooks. Six files, moderate audit/test cost, small product entry diff |

Actual supporting sources inspected: `router.tsx`, `components/MarketSwitcher.tsx`, `components/PageHeader.tsx`, shared table/sort and readonly UI; `pages/backtest/{StrategyBacktest,RobustnessValidation,StrategyOptimizer,StrategyWalkForward,ResearchCandidatesDialog}.tsx`; `lib/{backtestTask,optimizerTask,walkforwardTask,taskRegistry,useFinancials,useSharedQueries}.ts`; existing Signal/Factor/Stock Preview contracts, Presentations, fixtures and tests.

Second candidate: indices only as a future, explicitly scoped enhancement; it is already complete. There is no second unfinished candidate in this list. Concept/industry remains CN-bound and is not expanded. No second page is implemented.

## Boundary and CN compatibility

L3 is necessary because this core page has no extension slot preceding its hooks. L1 configuration and existing L2 slots cannot prevent StrategyBacktest mounting. Only `Backtest.tsx` is changed in the existing product tree: exported Backtest delegates to BacktestMarkets; original body becomes ChinaBacktest; the inert header MarketSwitcher is replaced by an injected controlled MarketSwitcherBar. No CN descendant or lifecycle implementation is changed. This small entry change is the upstream merge surface.

Dispatch precedes **all** original useSearchParams/useLocation/useNavigate, state-candidate consumption effect and legacy redirects. HK/US never mount ChinaBacktest, StrategyBacktest, RobustnessValidation, StrategyOptimizer, StrategyWalkForward or ResearchCandidatesDialog. Production query parameters (`run`, `candidate`, legacy `tab`, highlight) and router-state loadCandidate cannot activate them. CN retains strategy/validation tabs, candidate dialog load/close/consume, state consumption and factor/mining legacy redirects with remaining query parameters.

The existing task modules define functions, stores and subscriptions on import; task adoption/reconnection starts from CN mounted effects. Existing module-level CN date constants do not supply Preview dates. No new module-level network/storage/timer behavior is introduced. Switching to Preview unmounts the CN page; it **does not cancel already running global CN tasks** or disable Layout services. Task lifecycle preservation is intentional; Preview itself never starts, adopts or cancels tasks.

## Synthetic contract and UI

Independent BacktestPreviewData / BacktestSample DTO and fail-closed runtime validator. Only local fixtures. Market-owned HK and US envelopes have distinct fixture IDs, HKD/USD, fixed start dates/windows and fixed generated_at values; each has strategy and robustness metadata. No CN config, production strategy ID or actual bars are copied.

Identity flags: PREVIEW / synthetic-fixture / preview / is_production=false / is_investment_signal=false / fixture_only=true / synthetic=true. `fixture-backtest-{HK|US}-{A|B}` identity must match market, currency and evidence. Unknown production run/version, return, drawdown, trade count, completion time, input contract and Universe identity are **null with reasons**, never zero or READY. A missing lookback remains null with its own reason. Date validity/order, safe positive integer windows, AND metadata only, exact keys, provenance, duplicate identity and nonempty blockers/warnings are checked. NaN/Infinity/numeric strings, mixed markets, production readiness/IDs/evidence, unexpected executable fields and unknown-to-zero mutations are rejected.

This is a **backtest plan display**, not an executed result, equity curve, performance claim or validated trading rule. PARTIAL/BLOCKED refers to sample metadata completeness; execution is always BLOCKED. Generated time means authored fixture time, not a task execution/completion time. Date ranges are illustrative calendar strings, not certified trading sessions or coverage.

Presentation reuses PreviewNotice, PreviewDisabledAction, MarketSwitcherBar, StockDataTable/useTableSort, EmptyState/ErrorState. Search, type/completeness filtering, three-state sorting and details are local UI state. URL market defaults CN; keyed market root resets search, filters and details on switches/back navigation; reload restores market only. All unknown/error/empty/loading states retain the nonproduction declaration. Native buttons preserve keyboard and aria-sort support.

Eight actions remain natively disabled with reasons: run, cancel, parameter optimization, walk-forward, save candidate, save configuration, restore production task, publish strategy. No callback, fake success, storage write, notification, Query hook, API client, provider or execution engine in Preview. No unified controller, validator factory, loader or context is added. Other Preview contracts, fixtures and entry dispatches are untouched.

## This-run verification

Commands run from `frontend`, using installed locked runners; native node:test files are separated by their actual `node:test` imports, not dropped failing tests. All results below are A10 runs, not A09 historical evidence.

| Command / scope | Result | Exit | Measured wall seconds |
| --- | --- | --- | --- |
| `node node_modules/vitest/vitest.mjs run src/pages/BacktestPreview.test.tsx` | 30 PASS | 0 | 3.14 |
| Same runner: BacktestPreview, backtest/tradeNav, MarketSwitcher.integration, MarketSwitcher, StockDataTable, ReadOnlyPreview, SignalPreview, FactorPreview, StockAnalysisPreview | 130 PASS / 9 files | 0 | 5.26 |
| Same runner over all 53 discovered Vitest files | 494 PASS / 53 files | 0 | 12.06 |
| `node --test src/components/DimensionMembersDialog.test.ts src/lib/neighborPrefetch.test.ts` | 5 PASS | 0 | 0.91 |
| `node node_modules/typescript/bin/tsc -b` | PASS | 0 | 23.54 |
| `node node_modules/vite/bin/vite.js build` | PASS | 0 | 18.88 |

Warnings retained: existing React Router v7 future flags and Vite >500kB chunk advisory; no assertion removed or unrelated product fix. Test CN descendant substitutes explicitly verify original dispatch/candidate props/redirects without running production business services; this is not full real-service CN execution validation. Offline isolation spies cover API/fetch/EventSource, storage reads/writes/removal/clear, notifications/toast, hostile URL/router state and reconnect key. Production descendants are not mounted on either Preview market. Contract negatives and loading/error/empty states are tested separately.

Browser acceptance = **PARTIAL**. This-run real Microsoft Edge `155.0.4283.62` headless/CDP smoke: **28 checks passed, 0 failed**, script exit 0, 50.70 seconds. One raw driver protocol error is retained: `Invalid InterceptionId` for the isolated `/api/intraday/stream` request during HK direct navigation. It is not counted as a page error and is not erased or called a completely clean browser pass. Page exceptions = 0; console errors = 0. Build/jsdom are not browser evidence.

Command: `node .vite/backtest-A10-20261019/browser.mjs`. Dedicated temporary profile, Vite with **no backend proxy**, fixed local synthetic HTTP responses, non-GET rejection and external page-request blocking. Verified direct HK/US URLs with hostile production parameters; actual React fiber traversal found no CN execution descendants. Native Enter/Space each changed sort once; Tab reached the next sortable header. Verified search/empty/detail/null reasons, eight disabled actions, refresh, CN → HK → US → CN and history.back, plus 1440px and 390px layout. Whole-document horizontal overflow was absent; horizontal scrolling stays within the shared table. Screenshots were generated and existence checked for HK/US desktop/390; HK 390 and US desktop were additionally opened for visual inspection. Title clears the fixed menu; no observed new visual P1/P2.

Local ignored evidence: `frontend/.vite/backtest-A10-20261019/{browser.mjs,results.json,hk-desktop.png,hk-390.png,us-desktop.png,us-390.png}`. These are real local artifacts, not committed test fixtures. The report records all attempted API method/path/phase values. Zero non-GET business attempts were observed. Direct Preview visits still have **host** GETs including `/api/custom-signals`, `/api/alerts`, `/api/intraday/stream`, settings and pipeline status, all fulfilled synthetically. CN-control visits additionally query factor columns, factors, strategies, data status and task registry. Host storage writes were not instrumented in this smoke; no whole-site zero-write claim is made. Preview-owned API/storage/notification isolation is established by source plus the separate offline spies, not inferred from the host GET list. No real task is run or cancelled even on CN. Full real-service CN execution, long-running task interactions, every timing permutation and production fault recovery remain NOT VERIFIED.

CN source reverse comparison: after reversing only the declared import/wrapper/header-control changes, the original Backtest body matches HEAD exactly (PASS). TypeScript AST inspection of top-level statements in the three CN task modules and four backtest view modules found store Set initialization, CN date constants and local label metadata initialization, not new network/task starts.

Complete six-file source/diff review: PASS. `git diff --check`: PASS. Extra trailing-whitespace scan includes all untracked candidates: PASS. High-confidence secret pattern scan (private keys, GitHub/OpenAI token shapes, literal credential assignments): 0 matches; this bounded scan is not a guarantee against every secret form. Candidate allowlist: exactly six paths; index empty; HEAD unchanged. No changes to backend, other Preview contracts/fixtures or other page sources. No new product P1/P2 found in the reviewed scope; the retained browser driver protocol limitation remains open.

Handoff grades: Candidate selection PASS; CN compatibility PASS within source/offline/synthetic smoke scope; HK Preview isolation PASS; US Preview isolation PASS; Market switching PASS; Browser acceptance PARTIAL; Production validation NOT VERIFIED. Existing host request/storage behavior and already running CN tasks remain outside page-owned zero-side-effect claims.

## Production limits and handoff

Production validation = **NOT VERIFIED**. No backend, database, Provider, production input gate, frozen Momentum contract or CN execution core changed. No real backtest, provider health, trading-session coverage, fee/return calculation or execution recovery is verified. Longbridge Volume/VR20, split-only, Daily finality, historical PIT/vintage and formal Universe blockers remain unchanged. No real HK/US Universe/producer is created.

No staging, commit, push or synchronization is authorized in A10. Keep precisely the six task candidates unstaged for review. Browser artifacts are ignored local QA output, not production data or task candidates. Next single step after review: decide whether this page is ready for a separate Git-closure task; do not start another candidate.
