# Monitor / abnormal narrow headers and clock investigation v1

Task: T-2026-10-20-A16, Agent A / MAINLINE, 2026-10-20.
Repository: D:\娱乐\codex\lianghua\tick-stock-panel-main
Branch main; baseline HEAD f56d025d91ef47250ccacd02174fe14fe6489222.

## Protected starting state

The four modified tracked A14 files and its one untracked document were verified
against frontend/.vite/a14-acceptance-20261020/final-integrity.json. All five
starting SHA-256 values matched. Index was empty and git diff --check passed.
The prior acceptance report, screenshots and request evidence were read.
Nothing was reset, cleaned or overwritten to remove the existing candidate.

## Minimal local presentation changes

- Monitor Preview PageHeader reserves `pl-14` for the fixed menu below `md`,
  restoring its original `pl-5` on desktop. Its title/badge row may wrap below
  desktop and returns to nowrap at `md`.
- Abnormal Preview adds the same menu clearance/title wrapping and stacks the
  header contents below `md`, placing its permanently disabled action on a
  separate row. Existing desktop flex direction/alignment is retained.
- Only these two Preview Presentation files change product rendering. Shared
  Layout/PageHeader and all CN entry, market switch, query, retry, persistence
  and global Query behavior remain untouched by A16.
- Each existing page test adds HK and US layout-contract assertions. They verify
  responsive classes, title identity and continued disabled-action/API isolation.
  **jsdom classes do not prove visual geometry or successful 390px rendering.**

Original A14 entry files and its historical document remain byte-for-byte
unchanged. Its two existing test candidates are extended, not replaced.

## Actual offline checks in this task

Commands run from frontend. All durations are PowerShell wall time.

| Check | Command / scope | Actual result | Exit | Seconds |
| --- | --- | --- | --- | --- |
| Targeted | node node_modules/vitest/vitest.mjs run src/pages/MonitorPreview.test.tsx src/pages/AbnormalPreview.test.tsx | 40 PASS | 0 | 5.073 |
| Full Vitest | rg-discovered src test/spec files; all 54 Vitest files, native node files run separately | 554 PASS / 54 files | 0 | 18.621 |
| Native node | node --test src/components/DimensionMembersDialog.test.ts src/lib/neighborPrefetch.test.ts | 5 PASS | 0 | 0.682 |
| TypeScript | node node_modules/typescript/bin/tsc -b | PASS | 0 | 39.287 |
| Build | node node_modules/vite/bin/vite.js build | PASS | 0 | 20.595 |

The existing real QueryClient/fake-time cases passed for CN activity, HK/US
hidden invalidation, late responses, inactive deviation persistence suppression,
scheduled retries, retained CN state and shared observers. These are offline
tests; they do not establish real-service compatibility or browser timing.
Existing React Router future-flag warnings and Vite chunk-size advisory remain.

## Clock experiment: INVALID first collection, no causal conclusion

Historical A15 observations (78 host, 27 shared and 2 page-owned ERR_ABORTED)
remain historical. The product API client has a default 30,000ms browser timer
that calls AbortController.abort; it was read but not modified.

An isolated real Edge experiment used the same /abnormal?market=CN page,
fresh profile per trial, fixed synthetic responses with a matched **50ms real
server delay** on pipeline jobs, and a 35s browser-time window. Order was real,
virtual, virtual, real; no tests/build ran concurrently with the experiment.
Actual wall durations were about 35.17s for each real trial and 0.19s for each
virtual trial; the whole Node command exited 0 in 85.215s.

However, the two QA document-start IIFEs were concatenated without a separating
semicolon. The second observer failed on all four documents with a TypeError.
Thus its pipeline fetch/abort counts of zero are **invalid observation**, not
evidence that requests completed or that virtual time has no effect. The command
exit of 0 did not make this run valid; the raw report contains four QA-origin
page errors. Preserved artifacts:

- frontend/.vite/a16-20261020/clock-before-advance-results.json
- frontend/.vite/a16-20261020/clock-before-advance.mjs
- frontend/.vite/a16-20261020/clock-console.txt

The temporary tool was corrected to separate the probes, require observer
readiness and nonempty fetch observations, and include page errors in its exit
criterion. A follow-up matching experiment was prepared to initiate the target
request at browser time +1s within the measurement window. **It did not run.**

The normal approval review returned:

`Automatic approval review failed: stream disconnected before completion`

The tool explicitly said the command was not executed because approval review
could not be completed; this was not a safety determination. No approval was
repeated, no permission bypass or alternate browser launch was attempted.
No conclusion is drawn from the prepared script.

Clock causality: **NOT ESTABLISHED**. No product timeout, AbortController, API,
Query, host service or notification behavior was patched to force a result.

## Browser status and handoff

Post-change 390px/desktop layout, geometry, native Tab/Enter and complete page
timing browser regression: **NOT EXECUTED** after approval transport failure.
The prepared ignored browser.mjs uses stepped native virtual budgets with real
I/O drain, but this is only a proposed QA control; it has not been validated.
The A15 screenshots do not prove the A16 layout is fixed.

Narrow fix is an implemented, offline-tested candidate, **not visually accepted**.
No claim of whole-site zero effects, cancellation of in-flight requests, exact
successful real-clock polling cadence or production validation is made.
Production validation: **NOT VERIFIED**. All existing production blockers remain.

Total expected Git candidate scope is eight files: the original A14 five plus
two Preview Presentations and this document. A16 changes those two Presentations,
extends the two existing tests, and adds this document. No staging, commit,
push, synchronization, backend or other Agent worktree modification is performed.

Next step: after normal approval transport is available, review the prepared
observer guards, run the matched clock experiment, then independently validate
new 390px/desktop screenshots and page timing. Preserve all failed/invalid
evidence. No automatic Git close is authorized.
