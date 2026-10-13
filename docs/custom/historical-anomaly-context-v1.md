# Historical Baseline / Normalized Anomaly Context v1

> move_atr_ratio is a daily-volatility-scale context metric, not an intraday statistical probability or intraday volatility estimate.

## Architecture and truth boundary

Existing quote -> snapshot archive -> anomaly evaluation -> immutable event -> delivery
remains authoritative. A separate daemon consumer reads committed event sequences, obtains
prior Daily evidence, computes a baseline, and stores context keyed by event_id in
`data/user_data/anomaly_historical_context.sqlite3`. The event payload, detection thresholds,
severity, episode/dedup/cooldown/escalation and delivery cursor are never rewritten.
The existing anomaly worker lifecycle starts/stops the independent enrichment worker;
AKShare/yfinance requests are never performed on quote or anomaly-detection threads.

The sidecar has baselines, contexts and an independent enrichment cursor. Context and cursor
commit together. Existing recent/incremental APIs overlay the optional evidence.historical_context
with a bounded read-only batch; they do not fetch history. Older stored events still validate.
Two read-only endpoints support async refresh:

- `/api/intraday/anomalies/historical-context?event_id=...`
- `/api/intraday/anomalies/historical-contexts?event_id=...` (at most 100 IDs)

Absent context is unknown/enrichment_pending. Store/read/provider/calculation failures have
fixed sanitized blockers and nullable metrics. Original events continue to be generated and
delivered even if the historical SDK is missing or the sidecar is unavailable.

## Baseline and reproducibility

The service requests 120 calendar days ending D-1, then **independently filters trading_date
< D before invoking Factor Engine**, even if a provider leaks D/D+1. This is a bounded
observed Daily lookback, not fabricated trading dates: no forward fill or replacement prices.
Future evaluation dates are rejected. Worker D is derived from the event's quote timestamp
in its market timezone, not server/browser local date or delayed event delivery time.
Positive finite OHLC, identity, unique dates, source and requested adjustment are checked.

ATR14 directly calls MarketFactorEngine.compute with FactorRequest('atr',14), research mode,
price_basis='as_provided'. Strict warmup/null semantics are preserved, with no copied formula.
The existing volatility output is annual_vol_20d, so daily volatility is explicitly unsupported;
no annual/daily conversion or new intraday formula is introduced.

Baseline records atr14, reference_close, lookback_start/end, observations, as_of_date,
source, adjustment_method, baseline_version, calculation engine/mode/period and all selected
OHLC bars. Bars reproduce the shared factor output; move_absolute = abs(event.change_value)
and, only when price-scale compatibility is proven, move_atr_ratio would be
Decimal(move_absolute) / Decimal(str(shared ATR)). Current events lack that proof;
the ratio remains null with a blocker. Factor computation
uses the existing Float64 implementation. JSON scalar metrics are strings; null stays null.
as_of_date is evaluation D, baseline_as_of/lookback_end is the last actual selected bar.
The baseline version must be bumped whenever lookback, calculation or validation changes;
it is not a promise that future upstream Factor Engine changes can reuse old caches unchanged.

## PIT limits

The D-2/D-1/D/D+1 regression proves only D-2/D-1 reach the factor engine and stored bar evidence.
No D final OHLC or future bar is used. **This date-level no-lookahead gate is not a fully
bitemporal PIT dataset**: the provider may revise prior bars or incorporate later corporate
action adjustments. Baselines explicitly retain pit_capable=false and
pit_blocker=source_vintage_unverified. Fetching a past-D baseline today does not establish
that these exact values were available on past D. Do not use this context as proof of PIT
strategy results. Historical bars can be sparse within the bounded lookback; observations
and dates are retained, but a complete historical session-calendar audit is not added here.

## Market and adjustment matrix

| Market | Source | Baseline methods | Default ratio path |
| --- | --- | --- | --- |
| CN | akshare.stock_zh_a_hist/eastmoney | none, akshare_qfq | null: price scale unverified |
| US | yfinance.Ticker.history/yahoo | yfinance_auto_adjust_false, yfinance_auto_adjust | null: price scale unverified |
| HK | no historical v1 provider | unsupported | null |

Raw and adjusted fields are selected explicitly. They never overwrite each other. The two
suppliers' adjustments are not declared equivalent. Yahoo auto_adjust=False is source-provided
OHLC; it is **not** asserted to be guaranteed as-traded unadjusted history (e.g. split/revision
semantics remain those of the historical provider). Default source mode is not proof that
event movement and every historical bar have compatible scales. Even default-mode context
returns unavailable/event_baseline_price_scale_unverified, retaining ATR evidence but no ratio.
Adjusted-mode ATR can be computed and cached independently, but comparison to current
realtime absolute movement is unsupported until price-scale compatibility is proven:
adjusted_baseline_realtime_price_basis_unverified. No adjustment factor is fabricated.
HK real-time anomalies remain normal; only historical context is unsupported. Volume is not
requested for factor calculation, converted or used in this context.

## Cache and failure isolation

SQLite baseline key includes symbol, evaluation_date, adjustment_method and baseline_version.
Reservation commits before the network request, preventing repeated daily fetches and avoiding
holding a SQLite transaction over network IO. Successful and failed records remain isolated
by that exact key; failure on another symbol/date/mode cannot overwrite a success.
Failures are cached for the day instead of high-frequency retries. An interrupted pending
reservation returns unavailable with an explicit blocker; this phase adds no cache-reset or
retry endpoint. A later day/new version creates an independent key. Runtime SQLite is not
included in Git; separate data backup requires its own authorization.

The enrichment consumer processes at most five events per batch in sequence. Slow/history
network calls can delay later context, but never delay original anomaly delivery. The thread
is daemonized and shutdown waits at most five seconds; source timeouts remain those of the
existing providers (no provider-contract changes). A blocked request/interrupted reservation
can leave context unavailable; engine health includes the separate enrichment state.

## Dashboard

Main cards show a quiet “本次移动 ≈ 0.76 × ATR14” only for available, finite positive ATR context.
Otherwise “历史基准暂不可用” appears. Evidence adds ATR14, absolute move, ratio, baseline cutoff,
source, adjustment, observations/version and the complete context JSON including bars/blockers.
Visible-card IDs are batched (first 100); a pending batch refreshes every three seconds.
An opened evidence panel independently refreshes pending/error context; older cards can obtain
context through evidence even when outside that visible batch. Once terminal context arrives,
polling stops. No context result changes alert eligibility or frontend escalation semantics.

## Validation and remaining limitations

Mock backend tests cover CN/US, HK unsupported, shared ATR equivalence, D/D+1 truncation,
insufficient history, source/cache failures, zero/nonfinite ATR, symbol/date/mode/version cache
isolation, adjusted-mode ratio block, immutable event bytes/sequence, serialization and bounded
read-only API. Frontend fixtures cover available/unknown display and original event UX.
Third-party history calls are not part of ordinary unit tests. This phase does not claim
real-source baseline availability from mock success; it depends on installed optional historical
SDKs, source access and sufficient compatible history. Existing missing ESLint remains unchanged.
No news, AI, probability, percentile, adaptive thresholds, minute statistics or trading is added.

## Live validation v1 (2026-10-13)

Run explicitly from backend:

```powershell
uv run --frozen --extra historical python scripts/smoke_historical_baseline.py --evaluation-date 2026-10-12
```

The harness uses actual Historical Provider instances, expanding the source fetch end to D
to test the baseline's independent cutoff. All cache and synthetic-event integration writes
are confined to a temporary directory; production stores and credentials are not accessed.
Harness unit tests mock the providers. Successful source results are `completed`/`partial`;
the baseline previously checked `ok` and incorrectly rejected completed responses. This is
corrected; baseline version v1.1 isolates older failed baseline caches. No production contexts
or enrichment cursor are deleted/replayed by this stage.

| Symbol | Source / adjustment | Eligible dates | Observations | ATR14 | Reference close | Result |
| --- | --- | --- | --- | --- | --- | --- |
| 600519.SH | AKShare / none | unavailable | 0 | null | null | BLOCKED: network_error |
| 300750.SZ | AKShare / none | unavailable | 0 | null | null | BLOCKED: network_error |
| AAPL.US | yfinance / yfinance_auto_adjust_false | 2026-06-15 to 2026-10-09 | 82 | 6.7440372890710725 | 336.6400146484375 | PASS |
| NVDA.US | yfinance / yfinance_auto_adjust_false | 2026-06-15 to 2026-10-09 | 82 | 5.678489381910391 | 229.27999877929688 | PASS |

US sources returned D=2026-10-12 as well; both factor inputs excluded it. Dates were unique,
sorted, strictly <D, OHLC valid, ATR/reference close finite and positive. The exact first/last
OHLC samples and SHA256 cache key are printed by the harness. Each symbol used one provider
fetch; the second baseline read was equal and cached. CN failure records were cached too,
but explicitly labeled `successful_baseline_cached=false`, not successful source validation.

The service's existing `as_of_date` is the **evaluation date D**. The actual evidence cutoff
is `lookback_end`/`baseline_as_of`; the harness calls this `prior_completed_as_of_date` and
requires it <D. These two dates are deliberately not conflated.

For each successful US baseline, event -> independent consumer -> side store -> read-only
API overlay was verified as **FIXTURE CONTRACT VALIDATION**, not a real anomaly observation
or browser run. The immutable fixture event bytes stayed unchanged. The frontend contract
receives unavailable plus null ratio and displays the existing unavailable state.

Price-scale compatibility remains unverified for both markets. No ratio is asserted usable,
no source-equivalence or as-traded claim is added, and no threshold/severity changed.
Source responses remain non-PIT: prior bars can be revised and corporate-action adjustments
can change. Date gating suits live context enrichment but does not establish a frozen
point-in-time research archive. No schema drift was observed; US diagnostics retain
as_traded_raw_not_established, sdk_may_deduplicate_source_dates and volume_unit_unknown.
At that initial validation, CN source access remained blocked; the later CN fallback
acceptance below supersedes that availability snapshot. No network settings were changed.

## CN Historical BaoStock fallback acceptance (2026-10-13)

Primary: AKShare / Eastmoney (`akshare.stock_zh_a_hist/eastmoney`). Fallback: BaoStock
0.9.4, pinned in the optional historical extra and uv.lock. The existing Historical Provider
factory routes CN through the primary and fallback policy; no parallel baseline is added.
Fallback scope is **CN Daily / adjustment=none only**. BaoStock requests daily frequency
and adjustflag=3, validates returned code/adjustflag/trading status, and skips suspended bars.

Fallback triggers are transport/source availability failures: connection/reset, timeout,
TLS/DNS/proxy transport errors, or HTTP 429/502/503/504. Schema, parse/numeric, OHLC/semantic
contract errors, empty responses, programming errors and requested qfq/adjusted mode do
not trigger BaoStock. Failed fallback remains historical unavailable. Actual source is
retained in normalized bars, baseline, cached provider diagnostics and primary/fallback
attempts. Baseline version **historical-baseline-v1.2** isolates prior cached results.

Two separate validations were performed at evaluation D=2026-10-12:

- **NATURAL PRIMARY PATH: AKShare PASS / fallback not triggered.** Both symbols completed
  through the normal factory/provider/baseline path, with one primary read and zero BaoStock
  calls. AKShare had recovered since the earlier upstream_reset diagnostic.
- **INJECTED FALLBACK VALIDATION: injected AKShare upstream_reset → real BaoStock PASS.**
  Only a temporary acceptance harness replaced the primary instance's read with a
  ConnectionError(RemoteDisconnected). The normal fallback policy and real, unmocked BaoStock
  network query then fed the unified Historical Provider contract, baseline and shared ATR14.
  Harness provenance explicitly labels primary_failure_class=injected_upstream_reset,
  fallback_source=baostock, fallback_data=real; provider diagnostics retain upstream_reset,
  primary_attempt, fallback_attempt=completed and fallback_used scope CN_daily_none.
  No fault injection was added to production provider logic, configuration or default smoke.

| Symbol | Final injected source / adjustment | Fetched / eligible | Eligible dates | ATR14 | Reference close |
| --- | --- | --- | --- | --- | --- |
| 600519.SH | baostock / none | 79 / 78 | 2026-06-15 to 2026-10-09 | 20.288266194303787 | 1263.0 |
| 300750.SZ | baostock / none | 79 / 78 | 2026-06-15 to 2026-10-09 | 10.165668216611294 | 297.75 |

Both sources returned the evaluation-date bar; it was excluded before factor computation.
Eligible dates were ordered, unique and strictly <D, OHLC valid, and ATR/reference close
finite and positive. In each independently isolated scenario, first cache read was a miss,
second a hit with identical results, one provider call and no repeated primary/fallback
fetch. Evidence cutoff/baseline_as_of=2026-10-09<D; service.as_of_date retains its existing
evaluation-date meaning (2026-10-12). Fixture event→worker→side store→read-only API overlay
also passed, with immutable event bytes and no production anomaly inserted.

BaoStock fallback 已通过故障注入 + 真实备用源端到端验证；尚未再次观察到生产环境中的自然 AKShare failure → BaoStock fallback。

Source-level PIT remains unresolved: date filtering does not prove source vintage, and
history can be revised or affected by corporate actions. AKShare and BaoStock are not
asserted equivalent or guaranteed as-traded. The volume contract is not expanded:
BaoStock volume remains null/unknown. Longbridge realtime versus historical price-scale
compatibility is an independent, unverified gate; move_atr_ratio remains null with
event_baseline_price_scale_unverified. Matching observed prices is not proof. qfq semantics,
anomaly thresholds/severity and production volume behavior are unchanged.

Final checks: targeted provider/baseline/harness tests **92 passed**; after replacing two
new-test percent-format expressions with f-strings for Ruff, affected BaoStock tests
**20 passed**. Ruff on all changed/new Python files and git diff --check passed. The ten
candidate files were reviewed for credentials and runtime artifacts; none were found.
pyproject/uv.lock retain AKShare 1.19.1, add only BaoStock 0.9.4 to historical, and retain
yfinance 1.7.0. No frontend source changed, so frontend full/build was not repeated.

Backend full suite: **3356 passed / 6 skipped / 0 failed**, 217 existing warnings,
178.65 seconds, outside the filesystem sandbox. The initial sandbox run was
3348 passed / 6 skipped / 8 failed: Windows open-file inspection/hard-link access denial
and one worker exit exception. The unchanged full suite passed outside the sandbox;
no unrelated test or production workaround was introduced.
