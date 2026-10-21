# US quote snapshot detail V1 — A28

Agent A / MAINLINE, 2026-10-21. Base main:
`0c5cc3e860587256a4aa9245bcb8c1b72e889a97`.

## Scope and identity

This is a read-only quote snapshot dialog in the existing US Dashboard, not a
complete stock analysis feature or a new synthetic production data source.
Runtime values come only from the existing `api.usDashboard(symbol)` response.
Tests use fixed synthetic responses and never contact a provider or database.
No backend, API client, provider, schema, dependency or global retry changes.

L3 frontend changes are necessary because existing slots cannot control the
dashboard's URL/query/dialog lifecycle. The core router is unchanged. Existing
Modal and centralized Query key/API client are reused; no parallel cache or loader.

The prior A20/A22/A24 15-file candidates remain unmodified and uncommitted.
A28 has eight separate candidate files: Dashboard.tsx, UnitedStatesDashboard.tsx,
widgets.tsx, USQuoteSnapshotDialog.tsx, their three page/component test files,
and this document. No staging, commits, remote operations or Agent B worktree work.

## Entry and URL contract

`/?market=US&quote_symbol=AAPL.US` directly opens the dialog, including after a
refresh or sharing. Gainers/losers/turnover (their existing visible top eight)
and monitor/activity buttons open it. Index cards are unchanged.

URL is the authority for the selected symbol and open state. New opens push a
history entry; previous/next replace that entry. A bounded, deduplicated list
of symbols from the source list and the return URL are kept in the router's
native history state, not a new localStorage/sessionStorage record. This is
navigation metadata, never cached prices. Direct links without this context
disable previous/next with an accessible reason. A list's background changes
do not reorder the saved navigation context.

Closing an entry opened from the same dashboard goes back to its dashboard
entry; direct links remove the parameter in place. Back/forward restore URL
selection. Switching to CN/HK removes the US-specific parameter. CN behavior
without this new parameter remains unchanged.

Empty, repeated or invalid quote symbols fail closed. A quote link with missing,
non-US or repeated market parameters fails before any market business hooks.
The symbol grammar matches the existing US API grammar; it does not prove a
security's actual listing or asset type. No production object is reconstructed
from another market's ID. Reload/retry cannot bypass the invalid-link gate.

## Request and response mapping

Dashboard → UnitedStatesDashboard → QK.usDashboard(symbol) → api.usDashboard →
GET /api/dashboard/us?symbol=... → USDashboardService → existing provider path.
This endpoint is an existing aggregate and may read its other existing sections;
the detail does not promise a quote-only backend call. It creates no second
query observer or new endpoint. Original 30-second cache/polling and retry=false
settings remain. Detail close changes observation back to the default dashboard
key; already-started requests may finish into their own cache entries.

Only matching URL symbol, response focus_symbol, focus_quote.symbol and US
response market can produce displayed quote fields. An explicit conflicting
row market is rejected. Placeholder response data keeps the dashboard stable
while changing symbols, but cannot supply the new dialog's quote. Late A
responses never become B's displayed quote.

Actual supplied fields: symbol, market, name, close (labelled quote snapshot
price, not final daily close), change_pct (fraction ×100), open/high/low,
amount, currency and timestamp. Names/currency are optional. Finite zero values
are retained; null, invalid numeric inputs, overflow and invalid timestamps
display a missing/invalid reason rather than a fabricated zero.

Quote timestamp is the API-returned epoch milliseconds, rendered with full date,
seconds and America/New_York. Response updated_at is displayed separately and
only accepts timezone-bearing input; it cannot stand in for quote time.

The current focus DTO lacks a dedicated source, receive time, delay entitlement,
per-security trading status and authoritative expiry/finality metadata. The
dialog explicitly states these limits. Source/updated_at from rank sections or
sample batch status/stale/completed_at are NOT attached to the focus quote.
An old timestamp remains visibly old; there is no invented staleness threshold.
Fresh query cache, regular session or a successful request does not establish
real-time quote freshness. Background request failure with matching data is
labelled retained cached quote (possibly stale), distinct from initial failure,
missing quote and loading. The retry button refetches only the current US key.

Previous close, absolute change, volume/unit and bid/ask are not supplied by the
current focus mapping, even if the broad shared TS row type permits them.
They are explicitly unavailable; no reverse calculation or substitution.

No CN daily/minute, key levels, AI analysis, report saving, reminders, strategy,
backtest or trading components are mounted by this dialog. No new business
mutations, notifications or detail persistence. The existing US dashboard layout
localStorage effect and Layout/global requests remain; no site-wide zero-effects
claim is made. Existing HK/CN StockList callers retain the default div behavior;
only US opts into native anchors for keyboard/link sharing support.

## Offline acceptance

Real QueryClient + MemoryRouter page tests cover direct URL, back/forward,
source navigation, delayed responses, CN default/query recovery, fail-closed
parameters, all five entry lists, invalid-link reload, and actual cache-error
recovery. Component tests cover metadata, finite/null values, distinct states,
disabled navigation, Escape and focus restoration. API functions alone are
replaced with synthetic responses; the new query lifecycle is not mocked away.

Final command/exit/time records and complete output are retained under the
ignored `.vite/a28-20261021/` QA directory. The final results are recorded below
after execution; they are A28 runs, not A24/A25 historical results.

Final commands executed from frontend, all exit 0:

| Check | Scope / command | Result | Wall seconds |
| --- | --- | --- | --- |
| Targeted | `node node_modules/vitest/vitest.mjs run src/pages/Dashboard.test.tsx src/components/dashboard/UnitedStatesDashboard.test.tsx src/components/dashboard/USQuoteSnapshotDialog.test.tsx` | 37 PASS / 3 files | 10.03 |
| Related | same runner, 11 Dashboard/layout/market/watchlist test files, exact argv in verification-final.json | 133 PASS | 10.69 |
| Full Vitest | all 57 Vitest files; two native-node files run separately | 624 PASS | 23.95 |
| Native Node | `node --test src/components/DimensionMembersDialog.test.ts src/lib/neighborPrefetch.test.ts` | 5 PASS | 0.60 |
| TypeScript | `node node_modules/typescript/bin/tsc -b` | PASS | 30.03 |
| Production build | `node node_modules/vite/bin/vite.js build` | PASS | 22.04 |

Earlier A28 green 616-test run is also retained in verification.json and logs.
Final tests were repeated after tightening placeholder loading/row-market guards
and adding coverage. This does not erase the initial failures below. Existing
React Router future warnings and Vite >500kB chunk advisory remain visible.

Failure history is preserved, not retroactively labelled PASS:

- First two-suite command was mistakenly launched from repository root, so Vite
  could not resolve the frontend @ alias; two suites failed collection, no tests
  ran. Running from the frontend directory loaded the unchanged project config.
- The first route test fixture returned an incomplete CN overview `{}` and
  failed on emotion.label (28 passed / 1 failed combined). The synthetic fixture
  was completed; no CN product code was changed to accept the invalid fixture.
- The next route run had 4 pass / 1 fail: its new assertion incorrectly required
  a request immediately on CN return, despite the existing 5s fresh cache.
  The corrected test proves cache retention AND successful explicit invalidation
  after return. No existing business assertions were removed or relaxed.
- Python command wrapper could not spawn its interpreter; no file write occurred.
  The authorized file edits used the installed Node runtime instead.
- Initial final static audit reported CN body inequality because its comparison
  trimmed only the Git output and sliced using offsets before CRLF normalization.
  The original final-audit.json (exit1) is retained. A corrected read-only check
  normalizes both strings identically before finding the body and proves exact
  equality (20,037 characters). No product code was changed to satisfy this check.

Final static checks: exact eight-file A28 scope / 23 cumulative candidates,
all prior 15 SHA-256 unchanged, no staged files, git diff --check PASS, A28
high-confidence secret-pattern matches 0. Corrected result and candidate hashes
are in `.vite/a28-20261021/final-audit-verified.json`. CN body after the market
entry is unchanged; no full runtime/production CN compatibility claim is made.

## Real Edge acceptance — NOT EXECUTED

Actual browser launch was attempted using the existing ownership-checking A15
harness, a fresh profile, local synthetic API server and external-traffic blocking.
There is no real backend or provider. Original records:

- attempt1.json / attempt1-console.txt: Edge exited before CDP discovery, exit0,
  no stderr, zero page assertions; owned cleanup completed, sockets=0.
- attempt2.json / attempt2-console.txt: normal escalation was permitted, CDP
  reported Edg/155.0.4283.62, but browser PID differed from launcher PID. The
  harness rejected ownership before page navigation. Zero page assertions;
  cleanup completed, sockets=0. No ownership check was weakened or unknown
  browser adopted. The exact infrastructure cause remains unconfirmed.

Thus desktop/390px geometry, native Tab/Enter, focus trapping, refresh, back,
late-response behavior and request isolation have NOT been verified in a real
page this round. Zero collected page requests/errors from these launches are
not evidence of page isolation. No page screenshot was produced. Build/jsdom
success does not replace browser acceptance. Prior browser failures remain intact.

## Limits and next step

Browser acceptance: NOT EXECUTED. Product candidate requires independent review
and a working owned-browser session before claiming visual acceptance.
Production validation: NOT VERIFIED. No credential, real quote/model service,
account or production database was accessed. No price or timestamp was invented
to fill a missing runtime value. Tests are synthetic evidence only.

No history K-line, financial analysis, technical indicator, options or trading
feature is implemented here. Existing Volume/VR20, split-only, finality,
PIT/vintage and formal Universe/membership blockers are unchanged. The preexisting
watchlist narrow-title issue and unclassified host SSE ERR_ABORTED are not fixed
by this task. Existing 15-file local-commit permission blocker is not bypassed.
