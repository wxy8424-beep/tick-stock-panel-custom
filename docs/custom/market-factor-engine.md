# Market Factor Engine foundation

## Scope

`app.factors.engine.MarketFactorEngine` is a stateless selection and history facade
over the **existing** `app.indicators.pipeline.compute_indicators`. No indicator
formulas are copied from screener/backtest or an external project. The existing
factor registry/DSL, screener, backtest and Dashboard consumers remain unchanged;
they can adopt this entry point in later scoped migrations. This stage introduces
no endpoints, persistence, caching, provider requests, trading, dependencies,
realtime changes or snapshot schema changes.

The user-designated InStock indexes were consulted. This repository already has
the required common computations; no third-party source is extracted or added.

## Factors and exact inherited conventions

| Request | Available periods | Output | Convention | Research minimum bars |
| --- | --- | --- | --- | --- |
| MA | 5,10,20,30,60 (default20) | maN | arithmetic trailing mean | N |
| EMA | 5,10,20,30,60 (default20) | emaN | alpha=2/(N+1), adjust=False, first-close seed | N |
| MACD | fixed12/26/9 | macd_dif/dea/hist | DIF=EMA12-EMA26; DEA=EMA9(DIF); hist=2*(DIF-DEA) | 34 |
| RSI | 6,14,24 (default14) | rsi_N | existing gain/loss EWM alpha=1/N, adjust=False, initial gain/loss zero | N+1 |
| ROC | 5,10,20,30,60 (default20) | roc_N | existing momentum_Nd: close/close.shift(N)-1 | N+1 |
| ATR | 14 | atr_14 | max(high-low, abs(high-prev_close), abs(low-prev_close)); EWM alpha=1/14 | 14 |
| volatility | 20 | annual_vol_20d | sample stddev of 20 simple daily returns (ddof=1) * sqrt(252) | 21 |

MA/EMA/MACD/ATR use the input price scale. RSI is on the 0–100 scale, including the
existing zero-loss epsilon (1e-12); a flat series produces zero with this inherited
zero-gain convention. ROC/volatility are decimal ratios, not percent points.
252 is the existing research annualization assumption, not a computed exchange
calendar count. The facade does not claim equivalence to a different TA-Lib
initialization or MACD-histogram convention.

All seven kinds are the default request. Custom periods unsupported by the
existing implementation fail explicitly rather than creating a second formula.
Minimum bars are research mode's conservative display policy, not proof of EMA
convergence; the existing pipeline's early seeded values remain unchanged for
legacy consumers. Values after the facade warmup use the original computations.

## Inputs, gaps and units

The default `mode="research"` retains the original strict behavior described
below. An opt-in `mode="backtest_compat"` requires an explicit
`compatibility_backend="polars"` or `"matrix"`; there is no guessed backend.

`compute(history, requests, price_basis="as_provided")` accepts existing Polars
daily history: nonempty string `symbol`, Date `date`, and numeric `close`. ATR
also needs numeric `high`/`low`. Keys must be unique. Output is sorted by
symbol/date. Dates correspond to supplied observations; no weekdays are generated
and a weekend/holiday gap is not automatically treated as missing trading data.

Finite positive prices are required. Missing close, zero, negative, NaN or infinity
break the continuous calculation segment for all factors. ATR additionally breaks
on missing or inconsistent high/low. New segments restart the original recursive
seeds and must warm up again. High/low absent from the input disables only ATR.
No forward-fill, bridging, duplicate-date aggregation or future observations are
used. Extremely large derived non-finite results become null, not fake zeroes.

Volume is not read or converted. Unsupported volume-dependent requests fail with
an explicit unavailable error. This stage does not unlock quantity capabilities.
`price_basis` is caller metadata (`as_provided`, `raw`, `qfq`), not an adjustment
operation or validation of the repository's price basis; no currency is guessed.

## Compatibility semantics

Legacy backtest has two different computation paths. Compatibility selects the
existing calculator rather than copying formulas or changing its implementation:

| Policy | research (default) | backtest_compat / polars | backtest_compat / matrix |
| --- | --- | --- | --- |
| Calculator | existing Polars pipeline per valid segment | existing Polars pipeline on the whole supplied history | existing matrix_feature kernels on Float32 time/asset arrays |
| Warmup | strict minimum-bars mask | native rolling readiness; EMA/MACD/RSI/ATR early seeded values retained | native effective-observation readiness; early seeded values retained |
| Gaps | reset segment and warm up again | inherited Polars null/shift/EWM behavior, no reset | inherited effective-observation behavior, no reset |
| Initial values | inherited seed per segment, masked | inherited seed for whole symbol history | inherited matrix seed for whole valid-observation sequence |
| Price validation | finite positive prices; ATR checks OHLC | preserve numeric source prices without research sanitation | preserve legacy Float32 projection without research sanitation |

Missing/non-numeric required price columns fail explicitly in compatibility mode;
they are not fabricated or silently changed to research mode. Invalid keys and
duplicate dates still fail closed. Selected price factors never consume volume;
the matrix adapter keeps volume unknown (NaN) and trading flags disabled. It does
not execute strategies, transactions or returns. Sparse asset/date cells remain
unknown and the output contains only input rows. Nonfinite results normalize to
null, matching BacktestEngine's finite-output boundary and enabling strict JSON.
This is representation normalization, not filling missing values with zero.

Finite outputs and missing positions match the selected legacy path, not a promise
that both old backends match one another. Matrix Float32 values are preserved when
projected into the facade's Float64 columns; no precision equivalence with Polars
is claimed. ROC keeps the facade's roc_N alias for the legacy momentum_Nd source.
Existing consumers and their schemas remain unchanged and do not call this new
mode yet; no legacy code or calculation definition is deleted or modified.

FactorResult and JSON carry `mode` and `compatibility_backend` (additive fields,
default research/None). Factor metadata includes `warmup_policy`: strict or
legacy_backend. `warmup_bars` remains the research minimum-bar reference and is
not an enforced mask in compatibility mode. It must not be used to suppress
compatible early values. Existing positional FactorResult construction remains
valid. `from_history()` forwards both options and uses the same explicit warmup
range and output trimming as before.

```python
result = engine.compute(history, mode="backtest_compat",
                        compatibility_backend="polars")
# For the unchanged matrix backtest semantics:
result = engine.compute(history, mode="backtest_compat",
                        compatibility_backend="matrix")
```

## Existing history API

`from_history(repository, asset_type, symbol, start, end, ..., history_start=None)`
uses only `get_daily_asset(asset_type, symbol, start, end, columns=...)`, with
asset type stock/ETF/index. The caller can supply an earlier history_start for
warmup; the engine does not estimate trading bars from calendar days. Output is
clipped to start/end after calculating on supplied warmup bars. Out-of-range and
other-symbol rows from a repository cache are excluded before calculation.

Repository methods retain their current cache/live-overlay behavior. The engine
does not reinterpret that data or guarantee availability/PIT correctness beyond
the source history contract. Absent HK/US histories stay empty/unavailable: there
is no provider fallback, source switching or capability unlock. No SQLite
snapshots are treated as historical daily bars.

```python
from app.factors.engine import FactorRequest, MarketFactorEngine

engine = MarketFactorEngine()
result = engine.compute(history, (FactorRequest("ma", 20), FactorRequest("roc", 20)))
payload = result.to_dict()
# Or use the existing repository with explicit start/end/history_start dates:
# result = engine.from_history(repo, "stock", symbol, start, end,
#                              history_start=warmup_start, price_basis="qfq")
```

## Output and compatibility

FactorResult contains a fresh DataFrame of symbol/date plus selected factor
columns, factor metadata and price_basis. Unrequested indicators/input payloads
are not returned. `to_dict()` yields JSON-compatible rows (ISO dates, nullable
finite floats) and copied metadata; `uses_volume` is always false.

Metadata state=available means at least one finite output exists for this factor
in the requested result window; it is not a guarantee that every symbol or the
latest row is ready. Consumers must inspect each nullable row value. All-null
outputs state unavailable, with empty/insufficient/invalid-history reason.
Price/missing-data errors are not hidden by zero values. Old pipeline functions,
factor catalog order, cache keys and existing output schemas are not changed.

This is a backend foundation for later consumer reuse, not an automatic migration
of screener/backtest/Dashboard to new warmup/gap semantics. There is no performance
claim for large universes; calculation partitions per symbol/valid segment.

## Semantics-mode verification

- Modes plus original strict-engine tests: 49 passed.
- Factor and existing backtest targeted regression: 384 passed.
- Final full backend: 3026 passed, 6 skipped, 0 failed.
- Ruff on the engine and both factor-engine test files: zero violations.
- All supported periods are compared to unchanged production calculators on
  empty, short, flat, declining, gap, nonfinite and multi-symbol inputs.
  Compatibility preserves finite values exactly per backend, with nonfinite
  values represented as null. Prefix, sparse-date, mode serialization and
  existing history API forwarding are covered.
- The deliberate infinity fixture exercises an existing matrix subtraction
  RuntimeWarning; research continues to treat these prices as invalid.
- No backtest/screener consumer, strategy, transaction or return logic changed.

## Foundation verification (prior stage)

- Targeted factor/pipeline/registry/DSL/screener/backtest tests: 101 passed.
- Full backend regression: 2997 passed, 6 skipped, 0 failed.
- Ruff on the two new Python files: zero violations.
- Numerical references, empty/invalid/insufficient histories, serialization,
  independent symbols, causal prefixes and existing history API are covered.
- Frontend was not modified; no frontend tests/build were required.
