# HK/US Factor Page Preview v1

Date: 2026-10-18. Main-worktree baseline: `bde25de44fb09011767605da6b2f02b6671e12de`.

## Mainline page inventory and choice

Audit used `router.tsx`, `Layout.tsx`, `lib/navOrder.ts`, extension registrations, actual market wrappers, fixture loaders, presentation contracts and test sources. The following is a source/test inventory, not a claim that production HK/US capabilities or browser visuals have been accepted.

| Page / route | Actual current implementation and evidence |
|---|---|
| Indices `/indices` | `IndexMarkets`, `index-preview` presentation/contract, `index_preview` fixture, `IndicesPreview.test.tsx`. Existing CN component remains separate. |
| Watchlist `/watchlist` | `WatchlistMarkets`, `watchlist-preview`, `watchlist_preview`, `WatchlistPreview.test.tsx`. |
| Review `/review` | Extension uses `ReviewMarkets`, `review-preview`, `review_preview`, `ReviewPreview.test.tsx`. |
| Environment `/regime` | `EnvironmentMarkets`, `environment-preview`, `environment_preview`, `RegimePreview.test.tsx`. |
| Monitoring `/monitor` | Extension uses `MonitorMarkets`, `monitor-preview`, `monitor_preview`, `MonitorPreview.test.tsx`. |
| Abnormal monitoring `/abnormal` | Extension uses `AbnormalMarkets`, `abnormal-preview`, `abnormal_preview`, `AbnormalPreview.test.tsx`. Different from `/anomalies`. |
| Position reminders `/lots` | Extension uses `LotsMarkets`, `lots-preview`, `lots_preview`, `LotsPreview.test.tsx`. |
| Paper trading `/paper` | Extension uses `PaperMarkets`, `paper-preview`, `paper_preview`, `PaperPreview.test.tsx`. |
| Data `/data` | `DataMarkets`, `data-preview`, `data_preview`, `DataPreview.test.tsx`. Static audit and synthetic coverage are distinct. |
| Financials `/financials` | Extension uses `FinancialMarkets`, `financial-preview`, `financial_preview`, `FinancialPreview.test.tsx`. |
| Strategy / screener `/screener` | Already implemented as `StrategyMarkets` with `strategy_preview`, `StrategyPreview.test.tsx`. There is no separate unfinished core screener route to duplicate. |
| Ladder `/limit-ladder` | Existing Momentum Preview presentation/contract, independent `momentum_ladder` fixture and `Presentation.test.tsx`; no producer implied. |
| Dashboard `/` | Existing HK/US components and tests. They use `api.hkDashboard` / `api.usDashboard` query paths; they are not identical to the fixture-only pages above. No changes or new live requests made here. |
| Factors `/factors` | **Selected gap.** Before this task, only default CN `PageHeader showMarketSwitcher`; no HK/US wrapper, fixture, presentation or page tests. Five real CN research views were mounted from this route. |
| Backtest `/backtest` | Real CN strategy/robustness views with CN-only default switcher; no isolated HK/US Preview. Deferred. |
| Stock analysis `/stock-analysis` | Existing business component and default CN switcher, no independent HK/US Preview found. Deferred. |
| Concept / industry `/concept-analysis`, `/industry-analysis` | Existing dimensions, marketSnapshot queries, enrichment and default CN switchers; no independent HK/US Preview found. Deferred. |
| Signals `/signals` | Existing shared user-definition editor and real save/AI paths, no market-specific Preview. Scope needs its own decision. |
| Realtime event stream `/anomalies` | Existing backend-event delivery and market filters, not an independent synthetic Preview. Preserve its production evidence/notification behavior; not part of this task. |
| Analysis / infrastructure | `/analysis` redirects to extension-page settings; `/analysis/:menuId` is a configured dynamic page. `/mining` redirects to `/factors?tab=mining`. Branding/settings/dev/onboarding/auth are infrastructure, not missing market-data Preview pages. |

The ten specified completed pages were verified to have an actual isolated market entry, independent fixture and corresponding test source; their tests also passed in this task's complete frontend run. No implementation was duplicated.

Factors is the first unfinished business page following the completed Strategy page in `DEFAULT_NAV_PATHS`. Its existing metadata model supports a bounded read-only presentation without requiring execution, provider facts or a new backend. Backtest has a larger execution/result surface; it and all other unfinished pages remain unchanged. The external open-loop record was read for context; its pre-commit currency-fix checkpoint was stale, so live Git state was authoritative.

## Audited factor behavior and minimal boundary

`Factors.tsx` owns tab/focus/edit URL state and the research-candidate dialog. Existing children:

- `FactorDiscovery`: columns/watchlist queries, factor-batch execution, candidate persistence and introduction preference storage.
- `FactorLibrary`: registry query; lifecycle/group/delete mutations; strategy generation.
- `FactorEditor`: library/column queries, validation/trial, create/update.
- `FactorComposite`: registry query and composite registration.
- `MiningWorkbench`: library/strategy/run/availability/regime/config queries, local draft storage, mining jobs, publish/promote and scheduling.
- `ResearchCandidatesDialog`: existing candidate loading and navigation to real backtest.

The existing page has no whole-page market isolation slot. This is a narrowly scoped L3 entry change plus a dedicated presentation module following the established Preview pattern. L1 configuration and existing L2 toolbar/navigation slots cannot prevent the real child components from mounting. No router, Layout, shared API, Query cache or extension registry change is needed.

Six planned files:

1. `frontend/src/pages/Factors.tsx`: wrapper and injection of existing market controls.
2. `frontend/src/custom/damon/factor-preview/contract.ts`: inert typed display DTO, validation and view labels.
3. `frontend/src/custom/damon/factor-preview/Presentation.tsx`: read-only HK/US UI and URL market boundary.
4. `frontend/tests/fixtures/factor_preview/index.ts`: newly authored fixed samples.
5. `frontend/src/pages/FactorPreview.test.tsx`: CN compatibility and Preview isolation tests.
6. This document.

The established `custom/damon` namespace here is inside the main worktree. No Damon AI branch/worktree or candidate files were accessed or modified.

## Preview contract and UI

Reuse `IndexPreviewProvenance`, type-only `FactorLibraryItem` metadata, `MarketSwitcherBar`, `PageHeader`, `StockDataTable`, `useTableSort`, `EmptyState` and `ErrorState`. No generic framework, network client, query cache or factor engine was added.

Each market has four separate sample identities, covering base/virtual/composite/custom shapes. IDs start `fixture-factor-HK-*` or `fixture-factor-US-*`; versions are `preview-v1` / `preview-v2`. The loader allocates fresh independent data on every call and validates it. It does not copy CN registry rows or other pages' fixtures.

- Fixed trading date: `2026-09-16`.
- Fixed generated_at: `2026-09-17T09:00:00Z`, the authored fixture time, never a real evaluation time.
- `status=PREVIEW`, `source=synthetic-fixture`, `data_mode=preview`, `is_production=false`, `is_investment_signal=false`, `fixture_only=true`, `synthetic=true`.
- Names, IDs, types, groups, versions, direction metadata, formula text, units, history requirements, dependencies and evidence are visible. Formulas are inert descriptions, never evaluated or registered; the frozen Momentum calculation/profile hashes are untouched.
- Two fixed example values differ between HK and US. Missing sample values, formula/unit/history/dependencies remain null with reasons. No interpolation, zero filling or default normal state.
- Definition quality READY/PARTIAL/UNAVAILABLE/BLOCKED describes the authored sample structure only. Validation and execution stay BLOCKED for every row.
- PIT, real evaluation time, IC mean, IC IR, real coverage count, exact input-contract identity and production Universe identity stay null with independent reasons. Four sample rows are not a market coverage measure.

The declaration is always visible, including error/loading/empty states:

> 演示因子｜合成数据｜非生产因子配置｜不产生真实信号｜不构成投资建议

## Interaction and execution isolation

HK/US can search names/IDs/formula text/descriptions, filter kind/group/definition quality, sort supported columns (null last in either direction), select details and navigate five read-only views.

- Inspect: shows authored values and absence of IC/IR/results; run disabled.
- Library: metadata and evidence; lifecycle changes and strategy/signal generation disabled.
- Editor: only formula text; no DSL, trial or save.
- Composite: missing weights remain unknown; no equal-weight inference, redistribution or registration.
- Mining: no real run/candidate loaded from URL, no worker, schedule, job, promotion or publication.

Every disabled action explains `Preview 模式不可执行`. No new execution callbacks are attached. The Preview modules have no API client, Query hook, browser storage, provider request, notification or production persistence path. Type-only API imports do not make requests.

Market selection lives in the existing URL `market` parameter, defaults to CN, and preserves unrelated URL parameters. `tab` is the requested view context; Preview ignores real focus/edit/run/candidate payloads. Preview tab changes clear focus/edit consistently with CN tab navigation. Direct URL/reload reads the same fixed market. Switching markets remounts the page subtree, resets local search/filter/selection/detail, and closes CN dialogs. Returning CN restores its original URL-driven/default view; unsaved drafts are not preserved and already-started backend jobs are not cancelled.

CN body and business callbacks were checked against HEAD after removing the explicitly reviewed market shell/control substitutions: **exact textual match**. New tests exercise original CN tab dispatch, focus/edit parameters, candidate dialog, the actual FactorLibrary query/filter component and its inspect callback. Heavy CN computation children are stubbed in these page-routing tests; no claim of real production factor computation is made.

## Initial candidate validation (historical; superseded by P2 revalidation below)

- Dependency preparation: pnpm 9.10.0, Node v24.15.0; current main worktree initially lacked node_modules. `pnpm install --offline --frozen-lockfile` reused 243 packages, downloaded zero, changed no dependency manifests/lockfile. Initial sandbox realpath EPERM was an environment restriction; normal approved execution succeeded without changing permissions/configuration or using another worktree's dependencies.
- New page targeted: **13 PASS**.
- Related regression: **42 PASS / 5 files**, including new page, StrategyPreview, MarketSwitcher integration/unit and navOrder tests.
- Complete Vitest: **392 PASS / 48 files**. Command: `pnpm exec vitest run --exclude src/components/DimensionMembersDialog.test.ts --exclude src/lib/neighborPrefetch.test.ts`.
- Both excluded files use node:test rather than Vitest; `node --test src/components/DimensionMembersDialog.test.ts src/lib/neighborPrefetch.test.ts`: **5 PASS**. No test was dropped from the appropriate runner.
- `pnpm build` (`tsc -b && vite build`): **PASS**. Existing Router future warnings and large-chunk warning remain, no test/build failure.
- Build regenerated the tracked Vite declaration with equivalent content but different line endings; canonical Git hashes matched HEAD before restoring its checkout line endings. No configuration change remains.
- Real-browser visual validation: **NOT RUN**. jsdom assertions and successful build are not visual acceptance.
- Sensitive scan, `git diff --check`, conflict/trailing-whitespace checks and final source/fixture/test/report review: **PASS**, six planned files only. No credentials, databases, runtime logs, cache or dependency/build output enters the change list. Preview query/API/storage/current-clock boundary scan **PASS**. Staged area remains empty; staged review is **NOT RUN** because staging is not authorized in this task.
- Backend tests: **NOT RUN**, no backend or production contract changes. The earlier mining native-exit and auth DATA_DIR failures are separate historical open loops, not new frontend results or resolved by this task.

## Boundaries and delivery

Longbridge historical read evidence does not establish production inputs. Volume/VR20, split-only price basis, historical PIT/vintage and real Universe/membership remain BLOCKED; Daily finality PARTIAL and corporate actions UNKNOWN remain unchanged. No Factor producer, Momentum producer, production Universe, score, rank, worker, provider selection or archive acceptance changes.

The page-level Preview is available independently of supplier confirmation. It does not prove real HK/US Factor calculation, historical testing, registry publication, production signals or investment suitability.

No commit, staging, remote operation or push is performed for this task. Changes remain in the main worktree for manual review. Other missing pages are audit findings only and were not developed in this task.

## P2 browser findings and minimal fixes — 2026-10-18

The independent initial Edge acceptance was PARTIAL: sortable headers could not receive keyboard focus, and the fixed mobile menu covered the HK/US title prefix at 390px. Its report and all 21 screenshots remain intact in `frontend/.vite/factors-browser-qa-20261018/`. The earlier NOT RUN above refers to initial implementation validation, not this later browser session.

This follow-up changes five files only: shared `StockDataTable.tsx`, its new `StockDataTable.test.tsx`, the existing Preview Presentation/page test, and this document. All six initial candidate files remain; the total pending candidate scope is eight files. No Layout, backend, provider, production contract or other worktree changes.

### Keyboard sorting

Each sortable column now has a native `button type=button`, a descriptive accessible name, visible keyboard focus and an `aria-hidden` decorative arrow. `th` retains column-header semantics, `scope=col` and controlled `aria-sort=none/ascending/descending`. Native Enter/Space activation requires no custom keyboard handler. The button stops click propagation so a single activation toggles exactly once; existing clicks on header padding still work. Original tri-state sorting, null-last handling and caller filtering/value logic are unchanged. Custom header controls remain siblings of the sort button, avoiding nested buttons and retaining existing stopPropagation behavior.

### Narrow header clearance

Only the factor Preview PageHeader gets `pl-14 md:pl-5`: 56px left padding below md, original 20px at desktop. CN's header and global Layout/menu logic are unchanged. This is a page-local clearance adjustment, not a navigation redesign.

### Automated validation actually run for these fixes

- Table and page targeted: **19 PASS** (5 shared-table tests + 14 page tests; also included in related/full runs).
- Related selected regression: **43 PASS / 5 files**. The separately named integration file was at `src/pages/MarketSwitcher.integration.test.tsx`, not `src/components`; its 5 tests were subsequently executed and passed in the complete run below. No claim that it ran in the selected run.
- Complete Vitest: **398 PASS / 49 files**, using `pnpm exec vitest run --exclude src/components/DimensionMembersDialog.test.ts --exclude src/lib/neighborPrefetch.test.ts`.
- Both excluded node:test files: **5 PASS**, using `node --test src/components/DimensionMembersDialog.test.ts src/lib/neighborPrefetch.test.ts`.
- `pnpm build` (`tsc -b && vite build`): **PASS**. Existing Router future notices and Vite large-chunk warning remain.
- The first targeted run had one failure in the new layout test: changing MemoryRouter initialEntries on an already-mounted router did not navigate from HK to US. The test now operates the actual MarketSwitcher and verifies both markets plus CN. No production workaround or weakened assertion was used; the original 13 page tests passed even in that first run.
- jsdom verifies native-button structure, controlled sort state, single activation, legacy header clicks, CN-style rows/nulls, custom controls and responsive class boundaries. It does not prove native keyboard default actions or physical layout; Edge evidence below does.

### Real Edge revalidation

New evidence is separate: `frontend/.vite/factors-browser-p2-20261018/`, including `run.mjs`, `results.json`, `acceptance.md` and **23 actual screenshots**. All screenshot paths were checked to exist. Microsoft Edge **154.0.4258.62**, native headless CDP, actual frontend with existing Tailwind, dark theme, 1440×1000 desktop and 390×844 narrow viewport. No browser framework/dependency was installed.

**74 checkpoints PASS, zero FAIL**:

- Real Tab reaches the first and numeric sorting buttons in HK and US. Real Enter sets ascending once; real Space sets descending once; subsequent mouse activation clears once. Row order and `aria-sort` are checked together. Sorting focus is captured in the keyboard screenshots.
- Both desktop headers retain 20px left padding, with no document overflow.
- At 390px, both headings start at x=56 while the menu ends at x=46; vertical bounds overlap but horizontal bounds do not. Both complete HK/US prefixes are visible. Document scrollWidth remains 390; the 900px table scrolls within its 354px container. Narrow screenshots were actually inspected, not inferred from jsdom/build.
- Five views, search/filters, null-last mouse sorting, details/reasons, direct URLs/reload, market reset/browser back, empty state and a controlled real error-component render pass.
- Actual CN inspect/library components, synthetic library loading, inspect callback/focus, reload and candidate dialog remain functional; leaving CN unmounts its components/dialog. Shared-table CN-style mouse/null/custom-header compatibility is also covered by unit tests. Real production factor execution remains deliberately NOT RUN.
- HK/US runtime inspection finds no CN factor execution components. **Zero HK/US factor/mining/candidate API requests, zero non-GET API requests, zero page errors and zero console errors** in the observed flows. Global frontend GET requests use isolated synthetic HTTP responses; this is not a claim of zero overall requests or real backend availability.

The runner used a fresh isolated Edge profile and loopback Vite middleware with no backend proxy. All API/health responses were synthetic and outbound page requests were blocked. No actual service, model, quote, provider or production database was accessed. Owned browser/server processes were closed after capture. All eight candidate hashes were unchanged by browser observation.

P2 keyboard finding: **CLOSED in tested flows**. P2 narrow-title finding: **CLOSED at tested viewports**. Light theme, physical mobile touch and real production execution/network errors remain **NOT RUN**. No conclusion that Longbridge/Momentum production inputs or execution are ready.

### Scope and delivery checks

Sensitive scan of all eight candidate files: no private keys, credential/token patterns or secret assignments found. Conflict-marker/trailing-whitespace scan and `git diff --check`: PASS. Full source/test/doc scope reviewed; no backend, production configuration, databases, dependencies or generated files in the candidate list. The staging area remains empty; its diff is empty, with no staged changes to review. No commit, push, fetch, pull, rebase or external memory change. Branch/HEAD remain `main` / `bde25de44fb09011767605da6b2f02b6671e12de`. All changes are retained for human review.
