# CN/HK/US Quote Processing Isolation Audit v1

## Scope and baseline

Audit and minimal CN identity gate correction, 2026-10-17. Baseline: `772971dbb34c8accc1cd4b684f897bb11e523190`.

The original `tick-stock-panel-custom` checkout is on `feat/damon-ai-phase1` with pre-existing modifications. It was left untouched. This work uses the independent `tick-stock-panel-main` worktree on `main`. Local main and the cached origin/main ref matched at inspection; no remote synchronization or push is claimed for this task.

No real quote requests, runtime bootstrap, production database writes, production archive requests, provider integration, or Momentum execution were performed. All new data evidence below comes from fixed fixtures in temporary stores.

## Actual callchain

Implementation references: `backend/app/services/quote_service.py`, `backend/app/plugins/longbridge/provider.py`, `backend/app/services/snapshot_archive.py`, `backend/app/data_providers/quote_quality.py`, `backend/app/market_session.py`, and `backend/app/tickflow/repository.py`.

### CN full-market route

```text
_poll_loop (CN market/session polling and final retry window), or refresh
  -> _fetch_quotes (_fetch_lock, daily scoped state cleanup)
  -> _fetch_full_market_quotes
     -> configured realtime provider, or TickFlow CN_Equity_A / optional CN_ETF
     -> optional explicit CN index supplement where supported
     -> _archive_records (independent consumption history)
     -> _process_full_market_records
        -> _partition_realtime_records
        -> _update_non_cn_quotes (HK/US only)
        -> select CN records only
        -> final boundary check using admitted CN timestamps only
        -> classify CN stocks / ETFs / indices using existing repository sets
        -> CN fetch metadata and index display cache
        -> if stale final: display notification only, return no monitor input
        -> _update_volume_delta (CN stocks)
        -> _build_daily (CN date filter, original OHLCV semantics)
        -> flush_live_daily / flush_live_daily_asset / merge_live_daily_asset
        -> _build_quote_extra -> _flush_live_enriched -> repository/cache
        -> quote SSE invalidation -> return CN snapshot
  -> _evaluate_monitors outside fetch lock, under evaluation lock
     -> existing CN session/date guards
     -> stock/ETF/index/sector/abnormal/date rules, strategy results
     -> alerts.jsonl, SSE, configured notifications/webhooks
     -> existing paper evaluation hooks for eligible CN enriched data
```

`_poll_loop` confirms a final attempt only when fetch succeeded and `_last_final_confirmed` is true. Its existing retry/deadline failure behavior is unchanged. `_fetch_quotes` invokes monitor evaluation only when a CN snapshot was returned. A foreign-only batch neither replaces the CN index cache nor advances CN fetch/volume/enriched/monitor state; a foreign-only final attempt cannot reuse a previous final confirmation.

### Symbol-scoped HK/US route

```text
_poll_loop -> _poll_non_cn_quotes
  -> existing provider get_realtime_for_markets for scheduled HK/US markets
  -> _archive_records
  -> _partition_realtime_records -> _update_non_cn_quotes
  -> in-memory per-symbol basic quote cache
```

Longbridge already declares `realtime_snapshot_scope="symbols"` and `cn_volume_supported=False`. The symbol-scoped branch in `_fetch_full_market_quotes` also skips CN records and does not attempt a full-market CN snapshot or index supplement. Non-CN cache updates are partial upserts with older-timestamp protection; they do not calculate CN enriched data, broadcast CN invalidation, or evaluate CN monitors. This task does not add subscriptions, a provider, or a polling loop.

### Snapshot Archive route

`_archive_records -> SnapshotWriter queue -> SnapshotArchive.prepare -> transaction insert` writes the separate `user_data/market_snapshots.sqlite3` history. It precedes the CN business gate. The archive derives market from symbol, validates quote quality, records received/quote/provider time and unit diagnostics, and may retain observations with unknown quality. Unknown symbols are rejected. An explicit metadata conflict may remain as unknown-quality evidence rather than disappear.

Archive persistence is not proof of CN daily admission, completed Daily OHLCV, strict PIT readiness, or Market Context availability. Archive acceptance, session classification, quality rules, persistence schema and trace semantics were not changed. The fixture archive test creates only a temporary SQLite file.

## Identity, date, time and currency boundaries

| Boundary | Actual rule / evidence |
|---|---|
| Symbol and market | Existing resolver recognizes CN/HK/US suffixes. CN additionally requires exactly six ASCII digits with SH/SZ/BJ. Malformed symbols and unknown markets do not enter business partitions. |
| Explicit identity declarations | Optional market/region must agree with symbol market; optional CN exchange must match symbol suffix. Malformed declarations fail closed. No trust in a market label alone. |
| Instrument identity | CN stock/ETF/index classification uses existing repository/index sets. Symbol format does not certify listing, instrument metadata, or provider truthfulness. HK/US symbols are not a new production Universe. |
| Currency | New guard rejects explicit non-CNY or malformed currency on CN-symbol rows. Case/outer whitespace normalization matches existing declaration handling. Missing/null currency retains the legacy provider contract; it does not prove currency. No FX conversion. |
| Adapter metadata | TickFlow adapter now retains optional currency/timezone in addition to market/region/exchange, so explicit source declarations reach the existing gate/diagnostics instead of being erased. |
| Trading date | Original `_build_daily` uses `cn_today()` and Asia/Shanghai midnight boundaries; timestamped rows outside that day are excluded. Missing timestamps retain existing behavior. HK/US dates never become CN daily dates through this branch. |
| Timestamp | Existing quote timestamp is epoch milliseconds. Preserved timezone metadata is not parsed into an unproven source-time interpretation. No naive datetime is relabeled UTC; Longbridge conversion is untouched. |
| Finalization | Original batch-level maximum timestamp test with existing tolerance remains, after market/identity partition. HK/US/unknown/conflicting-currency timestamps cannot confirm stale CN data. |
| Diagnostics | Existing bounded rejection reason/count logs are reused. Raw quote payloads, currency values, credentials and sensitive exceptions are not added to logs. |

## Proven gap and minimal fix

Baseline already contained market partitioning and CN/HK/US isolation tests. It would be inaccurate to claim the whole isolation mechanism was newly implemented here.

A fixed fixture with `symbol=600519.SH`, `market=CN`, `currency=USD` reproduced the remaining gap: the pre-fix test failed because fetch returned true and CN volume/enriched/monitor/final paths ran. The ordinary adapter also discarded currency metadata before partitioning.

Changes are limited to:

1. Retain optional currency/timezone declarations in the TickFlow record adapter.
2. Reject explicit incompatible/unknown currency declarations before CN records can affect cache freshness, volume delta, daily/enriched writes, monitors or final confirmation.
3. Extend deterministic fixture coverage and document findings.

No changes to CN calculation, OHLCV values, session/freshness tolerance, duplicate policy, market selection, repository schemas, archive acceptance, UI cards, provider selection or production configuration.

## Risk list and remaining limitations

| Risk | Status / handling |
|---|---|
| HK/US or unknown records reaching CN full-market processing | Existing partition remains; mixed and foreign-only fixture regressions pass. |
| Conflicting market/region/exchange | Existing fail-closed behavior retained and covered. |
| Explicit CN currency mismatch erased or accepted | Reproduced before fix; adapter preservation and pre-CN rejection added. |
| Missing currency / false upstream metadata / unlisted six-digit symbol | Not solved by syntax validation. Legacy absent currency remains allowed. Future provider contracts need independently proven identity and units. |
| Source timezone aliases or naive time semantics | No guessed timezone mapping introduced. Must be closed independently before new source integration. |
| Per-row finality | Existing final confirmation uses the maximum admitted CN timestamp, not every row. This task does not strengthen that business contract. |
| Missing/out-of-day CN timestamps and volume-delta order | Existing missing timestamp behavior remains; volume delta runs before Daily's date filter. The date-boundary test proves Daily/monitor input isolation, not a new per-row freshness guarantee. |
| Duplicate CN rows | Original `_build_daily`/repository behavior preserved exactly. No new deduplication or winner policy inferred. |
| Archive with poor-quality observations | Intentionally independent evidence history. It must not be treated as validated CN business output or production Daily/PIT evidence. |
| Longbridge Momentum readiness | Volume/VR20, split-only price basis, historical PIT/vintage and production Universe remain BLOCKED; corporate actions UNKNOWN and Daily finality PARTIAL. No blocker was upgraded. |

These limitations do not require guessing a new contract for the narrow explicit currency-conflict fix. Broader listing, quantity, per-row finality or missing-time enforcement requires a separate reviewed contract and is not bundled into this task.

## Validation

Fixed date: `2026-09-16`. Test stores use pytest temporary paths; full-suite application settings use a unique temporary DATA_DIR and absent environment-file path. Existing virtualenv interpreter is reused without dependency installation; source imports run from this main worktree.

Tests cover pure CN stocks/ETFs/indices, mixed CN/HK/US batches, foreign/unknown-only batches, malformed symbol/declarations, incompatible CN currency, unchanged compatible/legacy CN values, adapter metadata preservation, duplicate semantics, Beijing midnight boundaries, foreign/conflicting timestamps unable to confirm stale CN data, CN monitoring/writes, and independent temporary SQLite archive market queries.

The business-boundary tests intercept monitor and enrichment entry points while using real temporary repository writes; they do not claim end-to-end production notification, provider or enrichment observation. Existing related tests separately exercise index merge, non-CN snapshots, quality, sessions, provider contracts and archive behavior.

- Pre-fix regression: incompatible USD/CN identity test failed as expected (one selected test).
- Targeted + related backend tests: **162 passed** before the final equivalent Ruff formatting correction.
- Final targeted coverage, including the equivalent Ruff formatting correction, passed as part of the controlled full-suite rerun below.
- Normal full backend suite: **4183 passed, 2 failed, 6 skipped, 1 xfailed**, 214 warnings, 310.19 seconds.
  - Mining worker returned its compact result but exited with **3221225477 / 0xC0000005**. This is a native access violation, not the previously recorded exit timeout. It is not evidence of a quote-boundary assertion failure, and its root cause is not established here.
  - Auth bootstrap test constructed `Settings` using its own fixture `.env`; the runner's process-level DATA_DIR took precedence and redirected its auth file into the runner's temporary directory. The test's expected fixture path therefore did not exist. No production path was used.
- Controlled failure recheck: **3 passed**, 10.59 seconds (the mining case plus both auth bootstrap cases). Process-only `POLARS_MAX_THREADS=1` was used. An in-memory pytest plugin removes DATA_DIR only while `test_auth_env_bootstrap.py` tests run, allowing their own temporary `.env` DATA_DIR to take precedence. Other tests/worker processes retain the runner's temporary DATA_DIR. No assertions or production/test files were weakened or modified for these failures.
- Controlled full suite under those same settings: **4185 passed, 6 skipped, 1 xfailed**, 214 warnings, **259.67 seconds**, exit code 0. This does not prove the default-concurrency native failure is resolved; that remains an independent observation/open loop.
- Ruff comparison against `git show HEAD:<path>` through matching stdin filenames: QuoteService baseline **12**, working **12**, no new violations. The test-file single new formatting diagnostic was corrected; final affected-test-file Ruff **PASS**. Existing QuoteService debt remains.
- Sensitive scan (three planned files, no detected credentials/private keys/token assignments), `git diff --check`, and final source/test/report diff review: **PASS**. Staging/commit/push: **NOT RUN**; staged area remains empty as required by the report-first delivery scope.

No frontend changes; frontend tests/build are outside the affected scope. No production data or provider behavior is represented by these fixture results.

## Delivery and next step

Only `quote_service.py`, `test_quote_market_boundary.py`, and this report are planned changes. No commit/push is authorized automatically for this task; acceptance results and remaining risks must be reported first. The original Damon AI checkout and its user modifications remain separate.

Recommended next step: review the narrow gate and retained legacy limitations, then separately define a provider-specific identity/quantity/time admission contract before any HK/US production integration. This audit does not enable that integration.
