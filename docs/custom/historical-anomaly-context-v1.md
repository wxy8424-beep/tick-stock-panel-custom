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
and move_atr_ratio = Decimal(move_absolute) / Decimal(str(shared ATR)). Factor computation
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
| CN | akshare.stock_zh_a_hist/eastmoney | none, akshare_qfq | none |
| US | yfinance.Ticker.history/yahoo | yfinance_auto_adjust_false, yfinance_auto_adjust | auto_adjust_false |
| HK | no historical v1 provider | unsupported | null |

Raw and adjusted fields are selected explicitly. They never overwrite each other. The two
suppliers' adjustments are not declared equivalent. Yahoo auto_adjust=False is source-provided
OHLC; it is **not** asserted to be guaranteed as-traded unadjusted history (e.g. split/revision
semantics remain those of the historical provider). A raw-default ratio is contextual and
inherits these source limitations, especially around corporate actions.
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
