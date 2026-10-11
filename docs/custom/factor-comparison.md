# Factor Validation & Comparison Framework

## Boundary and usage

`app.factors.comparison.FactorComparison` is an independent, read-only analysis
tool. No production API, backtest/screener caller, strategy, provider, capability,
archive or factor definition is modified. It reads an already supplied history
frame or calls the existing daily history interface **once** for both modes.
There is no source switching, trading, persistence or synthetic history.

```python
from datetime import date
from app.factors.comparison import FactorComparison

tool = FactorComparison()
result = tool.from_history(
    repository, "stock", "600519.SH",
    date(2026, 2, 1), date(2026, 2, 28), "EMA20",
    history_start=date(2026, 1, 1), compatibility_backend="polars",
)
payload = result.to_dict()
# Or compare an already read Polars daily frame:
# result = tool.compare(history, symbol, start, end, "MACD",
#                       compatibility_backend="matrix")
```

The supplied repository must implement the existing `get_daily_asset` interface
and be appropriate for read-only historical analysis. Its existing cache/source
semantics are not changed. The tool itself never calls providers or sync methods.
No CLI that boots the application or starts its workers is introduced.

## Inputs

- symbol: explicit nonempty security code; other symbols are excluded.
- start/end: Date range; history_start defaults to start. Earlier history_start
  explicitly supplies observed warmup bars; no calendar-day estimates are made.
- factor_name: MA/EMA/MACD/RSI/ATR, case-insensitive. Bare names use the existing
  engine defaults. Named periods (MA5, EMA20, rsi_6, atr_14) must be supported by
  the engine. MACD returns all three components; macd_dif/dea/hist selects one.
- compatibility_backend: **required**, polars or matrix. Their inherited gap,
  seed and precision conventions differ; the tool does not guess a backend.
- price_basis: existing caller metadata, never an adjustment operation.
- relative_tolerance=1e-6, absolute_tolerance=1e-10: explicit finite nonnegative
  numerical comparison tolerances. Use zero for both for exact comparison.

The same filtered source rows and warmup range feed both engine modes. Input is
not changed. Date range is clipped only after calculating on warmup history.
Sparse dates are not interpreted as exchange holidays or missing sessions.

## Results

One row per observed date/output component, sorted by date and engine component
order, contains research, backtest_compat, difference, status and explanation
evidence. `difference = research - backtest_compat`; if either side is null it is
null, never zero. Nonfinite subtraction sets difference_overflow=true and null.

Statuses:

- equal: exact values match, including two nulls; two nulls do **not** prove a
  computable factor. Evidence and original null values remain visible.
- within_tolerance: finite unequal values within declared tolerance. The actual
  nonzero difference is retained; no cause is fabricated.
- different: null mismatch or finite difference outside tolerance.
- unavailable: compatibility requires a missing/non-numeric price column; the
  research result is retained, the compatible value/difference stay null.

Top-level status is empty/compared/unavailable; summary counts the row statuses.
Missing symbol or range, and schema-less empty frames, return empty rows. Missing
numeric price columns explicitly report missing_columns and compatibility_error.
Bad keys/duplicate dates/unsupported names/backend/options fail closed. Other
SDK or calculation exceptions are not hidden as a successful comparison.
`to_dict()` returns an independent JSON-safe payload with ISO dates, no volatile
clock fields and no credentials. Determinism is scoped to the same source data,
installed calculation stack, backend, range and options.

## Difference explanations

| Category | Evidence and boundary |
| --- | --- |
| warmup | Research is null, compatible value exists, current valid segment has fewer than research minimum bars. |
| missing_data | Current required price is missing, nonfinite, nonpositive or (for ATR) OHLC-inconsistent; or compatibility cannot run because a numeric column is missing. Invalid numeric values are recorded as invalid inputs, not invented replacements. |
| gap_handling | A differing row follows an explicit invalid observation in supplied history. Research resets; selected legacy backend keeps its audited missing-observation policy. Calendar dates absent entirely are not fabricated as gaps. |
| initialization | Both values are finite and differ after an earlier invalid observation for EMA/MACD/RSI/ATR. Research reseeds its new segment while legacy retains previous recurrence history. This is an additional contributor alongside gap_handling, not an independent competing formula. |

`difference_reasons` can have several contributors; difference_reason is its first
entry (missing_data, then warmup, then gap_handling/initialization as applicable).
Evidence includes invalid_inputs, segment_bars, research_minimum_bars,
previous_invalid_observation and recursive_factor. These explain audited policy
contributors, not proof that every numerical bit has only one cause. A gap can
also coexist with matrix rounding. Unexplained finite differences use **unknown**;
in particular, exact matrix-versus-Polars rounding differences on continuous data
are not mislabeled initialization. All rows retain actual values for inspection.

No volume is read, converted or used by these five families. The existing modes
continue to own calculation semantics; this framework only compares them.

## Verification

- Comparison plus existing engine/mode targeted tests: 74 passed.
- Final backend full regression: 3051 passed, 6 skipped, 0 failed.
- Ruff on new Python files: zero violations.
- First full run: 3050 passed, 6 skipped, one existing walkforward worker test
  failed on native Windows exit code 3221225477 after returning valid results.
  Its isolated rerun passed, then the full rerun above passed. No worker/test
  assertions or production code were changed to suppress the failure. The native
  crash root cause is not established; the one incident remains documented.
