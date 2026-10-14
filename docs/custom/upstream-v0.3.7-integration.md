# Upstream v0.3.7 integration

## Scope and source

Merge upstream tag `v0.3.7` (`ec8307eb3b6da57ee17bf2c97837df373d2976fe`)
into the custom application, preserving its existing history and extensions.
The GitHub releases API confirmed v0.3.7 as the latest non-prerelease release
on 2026-10-14; the cached HTML latest-release page still showed v0.3.6.
The original custom recovery point is
`d5d08e6865f40a98ea316e5b42bb33fd40e42548` and backup branch
`codex/backup-before-upstream-v0.3.7-20261014`.

This is an L3 upstream integration, not a redesign of the custom features.
It was prepared and tested in an isolated Git worktree without production
credentials or production data. The original backend remained running during
candidate validation. This integrates source; it does not install an official
binary over the customized application.

## Verified merge base

The previously imported upstream v0.3.4 parent is
`3cc8f1fd6e84e3d9026023c63090d9abef79b94e`. Its tree exactly equals the current
upstream v0.3.4 tree (`717e20082b6bb04289562fdc001c10c42eada9a1`). Upstream's
changed ancestry makes the ordinary merge base older than the already imported
content and produces misleading conflicts.

A semantic three-way merge therefore used that verified imported parent as
the explicit `git merge-tree --merge-base` base. A normal no-commit merge
established the real merge parents, then the computed tree was loaded into the
isolated candidate index/worktree. No branch history was reset or rewritten.
Seven actual conflicts were resolved by reading both implementations.

## Resolutions and preserved contracts

- QuoteService retains custom UTC timestamps, archive handoff and non-CN
  routing while incorporating upstream changes.
- DashboardGrid combines upstream page-scale positioning with custom sizing.
- Dashboard and Watchlist retain market switching and session/calendar hints.
  Watchlist follows upstream's shorter title, `自选`; its integration assertion
  was updated without weakening market-isolation checks.
- The upstream paper extension/modal layout is used; the comparison view keeps
  the custom market switcher. Old page-only callbacks were not carried into the
  new modal.
- DataSources combines upstream billing indicators and key-based plugin gates
  with the custom Longbridge credentials panel and installation protection.
- The regenerated uv lock retains historical extras and the audited Longbridge
  SDK 5.2.0. No new production data-source configuration is installed.
- Tier A OpenAPI snapshot deliberately adds `DELETE /api/paper/account` and
  `GET /api/paper/rounds`, both real upstream routes under existing
  `paper:trade` scope. No previous open endpoint is removed.

Custom anomaly rules, thresholds, event schema, immutable calendar/policies,
factor NOT_SELECTED behavior and intelligence first-result freeze are retained.
Regulatory readiness is unchanged. Historical source PIT and event/baseline
price-scale compatibility remain unproven; move/ATR remains gated. No benchmark
wiring fix, synthetic snapshot or production anomaly is part of this upgrade.

## Validation

| Check | Result |
| --- | --- |
| Custom/backend affected suite | 708 passed |
| OpenAPI snapshot after explicit update | 1 passed |
| Frontend Vitest | 239 passed across 35 files |
| Separate node:test | 5 passed |
| TypeScript + production frontend build | Passed |
| Normal backend full, final candidate | 3813 passed, 1 failed, 6 skipped, 1 xfailed |
| Failed native-worker test in isolation | 1 passed |
| Controlled backend full | 3814 passed, 6 skipped, 1 xfailed; POLARS_MAX_THREADS=1 |
| Ruff regression comparison | 709 current diagnostics; no diagnostic code/message absent from both parents in the same file |

The normal full failure is the existing Windows native-worker exit class:
`test_spawn_worker_returns_compact_result_and_memory_metrics`, exit code
`3221225477` (`0xC0000005`). It passed alone. Controlled full validation uses
process-local `POLARS_MAX_THREADS=1`; this is an acceptance environment
constraint, not a worker code fix. No worker architecture was changed for this
failure. Earlier full validation exposed the two stale OpenAPI expectations;
earlier frontend validation exposed the old Watchlist title assertion. These
were audited and updated before the final runs.

Ruff debt exists in both parents and was not mass-fixed. Comparison runs used
the same current Ruff configuration and tool, feeding each parent file via
`--stdin-filename`; paths, rule codes and messages were compared, excluding
line-number shifts. This is a regression check, not a claim of zero lint debt.
Vitest required host execution because sandboxed dependency realpath returned
EPERM. Tests, caches, environments and bundles are excluded from Git.

## Runtime migration and rollback boundary

Upstream startup seeds default custom signals when empty. It can move user
strategies that reference removed built-ins into `_archive_unloadable`, retaining
their files with collision-safe names. Paper's first access can migrate the
single-account layout into `paper/accounts/default`; the upstream fixture tests
cover the normal migration and repeated access.

Before live cutover, stop only the identified TSP backend and make a verified,
encrypted backup of existing runtime state. Keep the original data directory;
do not copy production credentials into the isolated candidate. Runtime backup,
databases, logs and credentials must not enter Git. Reverting source alone does
not reverse data migration: stop the application and deliberately restore the
appropriate saved state if rollback is required. Windows CurrentUser DPAPI
backups require the same Windows user profile and are not cross-machine backup.

Generated frontend bundles must correspond to the merged source. After cutover
verify health version 0.3.7, custom anomaly/worker routes, production policy
bindings and the served frontend. Do not claim a fresh packaged desktop
installer or real benchmark archive observation from source validation.

## Remaining limitations

Benchmark archive runtime observation, factor producer, historical PIT,
price-scale compatibility and evidence refresh remain separate work. No new
financial factual claims or provider entitlement claims follow from this merge.
No external source code was copied beyond the upstream MIT-licensed merge;
the upstream LICENSE and history remain present.
