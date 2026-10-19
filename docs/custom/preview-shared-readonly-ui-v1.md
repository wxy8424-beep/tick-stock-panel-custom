# Shared read-only Preview UI v1

Task: T-2026-10-19-A09. Date: 2026-10-19.
Main baseline: `a2f597b837aad8874177c6481822660c2feb9063`.

## Scope and interfaces

Only two leaf presentation components are extracted into
`frontend/src/components/preview/ReadOnlyPreview.tsx`:

- PreviewNotice: statement, description, optional className. It renders the
  existing `div role="note" > strong + p` structure; wording comes from the page.
- PreviewDisabledAction: label, reason, optional className. It renders a native
  `button type="button" disabled`, exposes reason through the original title,
  and preserves the visible `（Preview 不可执行）` suffix.

Neither component imports hooks, Query, router, storage, notifications, API,
fixture or production code. They have no effect, execution callback, onClick,
enabled switch or unrestricted DOM-prop spread. Unexpected runtime execution
props are not forwarded to the button. These leaves do not enforce the page's
market boundary and cannot replace its independent isolation contract.

## Deliberately not abstracted

The market controller remains local: it determines when CN business components
mount, URL history/remount behavior and page-specific height/scroll behavior.
Factor also owns five views and tab/focus/edit semantics. UI deduplication is not
authorization to change those lifecycles.

Validators, schemas, DTOs and fixture loaders remain independent. Their exact
identity rules, unknown fields, dates and validation strictness differ. A generic
validator could silently strengthen or weaken an existing accepted contract.
No new data layer, Provider, Repository, registry or Preview framework is added.

Query mocks remain in the existing page tests: Factor's query substitute and the
Signal/Stock query/action substitutes observe different boundaries. Consolidating
them here could hide a production request. READY continues to mean the individual
page's sample-definition quality, never production execution readiness. Domain
blockers and null reasons are not centralized or rewritten.

## Ordered migration and DOM

Migration followed Signal -> Stock Analysis -> Factor, with each page's targeted
test completing successfully before the next page was edited.

- Signal: replaces only the note and seven permanent disabled actions, retaining
  labels, order, reason, placement and existing error/loading/empty behavior.
- Stock Analysis: replaces only the note and twelve disabled actions. Its
  `rounded-card` note class is passed explicitly, preserving original classes.
- Factor: replaces the note and the local Disabled helper's seven action sites.
  Which buttons appear in inspect/library/editor/composite/mining remains in the
  original page conditions. Each view retains its original wording and order.

No DOM wrapper or level is added; React component boundaries do not add DOM.
The only intentional native attribute addition is explicit type="button" on
Factor's already-disabled action buttons (previously implicit default type).
No page layout class, aria/role, data attribute, filtering, formula, validation,
fixture, market controller, CN entry or global host component is changed.

## Validation evidence

All A09 runs below are this task's execution, not reused A06 results. The new
component tests cover text/escaping, note structure/role, default/custom classes,
native disabled/type/title/label, exclusion and non-forwarding of execution props,
mouse/key-event attempts without callbacks or form submission, and zero
request/storage-access/notification observations over mount/rerender/unmount.
jsdom does not establish real browser keyboard default behavior or visual geometry.

Ordered initial runs:

| Run | Result | Exit | Wall seconds |
| --- | --- | --- | --- |
| Shared component + SignalPreview | 5 + 36 = 41 PASS | 0 | 29.01 |
| StockAnalysisPreview | 25 PASS | 0 | 3.00 |
| FactorPreview | 14 PASS | 0 | 3.05 |
| Joint shared/three-page/MarketSwitcher integration/component/StockDataTable | 94 PASS / 7 files | 0 | 5.46 |

Final local runs (all exit 0):

| Command from frontend | Result | Wall seconds |
| --- | --- | --- |
| `node node_modules/vitest/vitest.mjs run` with every discovered Vitest file explicitly supplied | 464 PASS / 52 files | 11.60 |
| `node --test src/components/DimensionMembersDialog.test.ts src/lib/neighborPrefetch.test.ts` | 5 PASS | 0.60 |
| `node node_modules/typescript/bin/tsc -b` | PASS | 29.06 |
| `node node_modules/vite/bin/vite.js build` | PASS; Vite 24.51s | 25.37 |

Each targeted/joint command used the same installed Vitest entry above. Discovery
used rg test/spec .ts/.tsx paths: the two native node:test files ran separately,
and all remaining 52 files ran in Vitest. No failing tests were excluded, assertions
weakened or production code changed to obtain passing results. Existing Router
future notices and Vite large-chunk warning remain.

## Real Edge smoke: PARTIAL

Actual Edge **155.0.4283.62**, native headless CDP, fresh dedicated QA profiles,
1440x1000 desktop and 390x844 narrow viewports. The real frontend/React/Tailwind
ran against an ephemeral loopback synthetic HTTP server with no backend proxy.
Non-GET business requests were rejected; outbound page requests were intercepted
and blocked. No real service was contacted. Existing whole-host synthetic GETs
are not described as zero Preview-page network traffic.

First full smoke (`browser.mjs`, `browser-results.json`, `browser.log`):

- Signal HK/US, Stock Analysis HK/US and Factor HK completed **15 passing checks**:
  visible declaration, exact disabled native-button count/reasons, desktop title
  bounds/no document overflow and 390px title clearance/no document overflow.
- Waiting for the final Factor US mount timed out at the unchanged 40-second
  driver wait. The run exited **1**, wall **85.95s**, without reaching the final
  aggregate assertions. This is an incomplete run, not an all-pass result.
- Five CDP `Invalid InterceptionId` warnings were captured for
  `/api/intraday/stream`, separately from page Runtime exceptions. Both observed
  page exceptions and console error arrays were empty. These protocol warnings
  are retained, not suppressed or reclassified as application successes.
- Ten screenshots were actually written and confirmed to exist.

Focused follow-up (`factor-us-smoke.mjs`, `factor-us-results.json`, `factor-us.log`):

- Only the incomplete Factor US scenario was rerun in a fresh separate profile;
  declarations/action/layout assertions and timeout were unchanged. The original
  full report was not overwritten, and no product source or test changed.
- **5 PASS / 0 FAIL**, exit **0**, wall **31.84s**. This includes Factor US notice/
  disabled action, desktop/390px layout, no non-GET synthetic API calls, and no
  page/console errors. Two screenshots were actually written and confirmed.
- One additional SSE interception-protocol warning remains recorded.

The observed scenarios therefore cover all three Preview pages in both markets
and both widths, across two runs. Selected actual screenshots (Signal US narrow,
Stock US narrow and Factor HK desktop) were inspected. Existing table-local
horizontal scrolling is retained; it is not whole-document overflow. No confirmed
product P1/P2 was found. However the continuous full-run mount timeout and protocol
warnings have no proved root cause; fresh-profile success alone does not prove
that the full-run issue is unrelated to the host or environment.

**Browser acceptance remains PARTIAL**, not PASS. This is a UI smoke, not a full
new keyboard/five-view/CN/browser validation, and it does not rewrite the earlier
Stock Analysis A06 NOT EXECUTED or Signal whole-host zero-write failure records.
Light theme, physical devices, long-running host state and production validation
remain NOT VERIFIED / NOT RUN as applicable. Owned QA browser/server processes
completed their cleanup. QA artifacts remain in ignored
`frontend/.vite/preview-shared-A09-20261019/`.

## Final review, scope and disposition

The three diffs contain only the shared import, note replacement and disabled
action replacement; Factor additionally keeps its reason string locally. Its
view branches and action order remain in the page. Source review confirms the
Fixture/market-controller tails are unchanged, as are the original CN entries,
contracts, fixtures, shared Layout/MarketSwitcher/QueryClient and existing tests.

Final diff review and git diff --check: PASS. Explicit six-file allowlist and
high-confidence private-key/token/literal-credential pattern scan: PASS, zero
hits; untracked candidate whitespace was also checked. Pattern scanning is not
a guarantee against every conceivable secret. No seventh candidate, dependency,
configuration, database or generated runtime file enters the candidate set.

Shared component purity, Signal migration, Stock migration, Factor migration,
CN compatibility and Preview-own isolation: PASS within source/offline evidence.
No shared execution abstraction or production-readiness rule was introduced.
Browser acceptance: PARTIAL as detailed above. Production validation: NOT VERIFIED.

The candidates are ready for human source/commit review with the browser limitation
explicitly retained. An unconditional all-green browser/Git-closure recommendation
should wait for review or resolution of that limitation. No Git action is taken.

## Production and delivery boundaries

Production validation: **NOT VERIFIED**. No real model, market data, stock-analysis
service, provider, database, signal, factor execution, report save or alert write
is used. Existing Longbridge/Momentum production blockers are unchanged.
Whole-host requests/persistence are distinct from Preview-own behavior; no host
functionality is disabled to make isolation checks green.

Only six candidate files are planned: shared component, its test, the three
Presentation files and this document. QA scripts/logs/screenshots remain ignored
under frontend/.vite. No fourth Preview is migrated. No staging, commit, push or
Git synchronization is authorized; retain the candidates for human review.
