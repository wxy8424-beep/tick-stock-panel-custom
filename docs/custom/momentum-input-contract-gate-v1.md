# Momentum Input Contract Gate v1

This is strict immutable input validation, not a provider, production producer,
Universe producer, API, frontend, database writer or release of real Momentum Ladder.
Existing uncommitted Engine Foundation work is retained. No commit/push is performed.

## Boundary and immutable contract

`backend/app/services/momentum_input_gate.py` adds MomentumDailyInput,
MomentumGateRequest, per-item GateCheck, MomentumGateResult and a replayable
MomentumGateAcceptedInput. Models are frozen/extra-forbid and reuse existing
MomentumIdentity, State, immutable Calendar, Universe, Calculation and hash helpers.
No generic validation framework, new registry, Store or dependency is introduced.

Contract ID/version: `momentum-daily-input-gate / v1`. Its deterministic canonical
hash covers the admission rules, including strict PIT, lookbacks, missing behavior,
mode isolation and receipt checking. Receipts and Snapshot candidate input identities
must explicitly name this Input Contract. Existing Calculation/Profile definitions
and all five canonical hashes remain unchanged, including the inherited Calculation
v1.1 and Profile v1.2. No Snapshot schema/old row migration is performed.

Canonical Gate hash:
`cb90ae0256709797fbc090102cf450d287ea0d454fd40b31805fa8793d0aa4f4`.

L3 is limited to a new Momentum-only validation service and the existing uncommitted
Engine boundary: existing L1 configuration/L2 notification/router/startup hooks cannot
express these typed pure-input rules. QuoteService, SnapshotWriter, archives,
Historical/Market Context, Factor, Anomaly, Evidence Policy and startup are unchanged.

## Daily evidence model

Each MomentumDailyInput freezes:

- Identity: exact symbol, market and instrument_type.
- Time: trading_date, exact market timezone, aware timestamp, knowledge_cutoff,
  available_at, optional fetched_at and source_vintage.
- Calendar: exact ID/version/content_hash and optional session_index. Trading date
  plus exact Calendar is the equivalent session identity when index is absent.
- Price: OHLC, optional prev_close, explicit price_basis, adjustment_method/version
  and price_basis_reference. RAW, split-only, OTHER_ADJUSTED and UNKNOWN stay distinct.
- Quantity: volume, optional turnover, unit, corporate-action-comparability semantics,
  currency and quantity_reference.
- Finality: bar_final, finality_source/reference and aware finality_verified_at.
- Provenance: source/version/vintage, availability/vintage references, input_reference,
  origin and data_kind. No opaque provider response is accepted.
- Declared quality/blockers/warnings, which cannot override failing derived checks.

Nullable/unknown evidence is representable so validation can report the actual gap;
it is not a default proof. Numeric booleans, nonfinite numbers and naive datetimes
are rejected at parsing. Parse failures produce sanitized schema BLOCKED checks;
raw payloads and original exception text are not echoed as diagnostics.

timestamp means the official completed-session close bound to this Calendar. It is
checked against the frozen regular/half-day close, not inferred from a provider's
last candle or the host timezone. It is NOT available_at. A naive Longbridge candle
datetime is never promoted to either UTC publication time or vintage.

## Exact checks

`validate_momentum_daily_input(row, request)` checks target/member identity,
Universe READY/effective/availability, exact Calculation/Profile/Input Contract and
Calendar bindings, instrument inclusion/type eligibility, session membership/index,
market timezone and target not later than the completed session/cutoff.
Universe must cover the entire target local date, matching existing Score semantics.
Historical lookback bars do not assert Universe membership on those earlier dates.

OHLC must be finite/positive, with low <= open/close <= high. Quantities must be
finite/nonnegative. prev_close is optional because frozen metrics use actual adjacent
closes; if supplied it must be positive and agree with the preceding exact supplied
session. Across a missing session it is never compared with the nearest available bar.
No value is filled or synthesized by Gate.

Price admission requires SPLIT_ADJUSTED_PRICE_ONLY, adjustment_method=SPLIT_ONLY,
explicit adjustment version and proof reference. A generic adjusted/raw label,
forward adjustment or yfinance adjusted output is not treated as split-only.
Quantity requires a known unit/currency, COMPARABLE_CORPORATE_ACTION_QUANTITY and
proof reference; an intraday snapshot/cumulative volume is not Daily evidence.
Optional turnover remains null if absent; it never substitutes for volume/VR20.

Finality needs bar_final=true, source/reference and verified_at between official
close and knowledge_cutoff. A current intraday or merely last returned bar fails.
Availability needs independent proof and close <= available_at <= knowledge_cutoff.
Source/version/vintage and vintage proof must be explicit. Request cutoff must not
exceed its explicitly supplied evaluation_boundary, and boundary must not exceed
generated_at. All rows use the same cutoff.

fetched_at is an observation only: it may be later than historical cutoff during a
proven replay, but cannot exceed generation time. It never supplies missing
available_at, vintage or finality. Gate checks structured declarations and consistency;
it does not authenticate a supplier's referenced documents or establish missing facts.

## History windows and result status

`validate_momentum_history_window(rows, request)` additionally requires strictly
increasing unique dates and every exact session across the submitted interval through D.
Weekends/official holidays are not gaps. It checks consistent source/version/vintage,
price basis/adjustment version, unit/quantity semantics/currency across the window.
No sort, merge, source switch, fallback, shortening or nearest-bar selection occurs.

Metric windows come from the exact existing Calculation: returns 3D/5D/10D require
4/6/11 sessions; VR20 and sigma20 require 21; B20/B60 require 21/61; trend requires
22. Consecutive-up history needs an observed equality/down boundary with no missing
session. A 21-session VR20 check may pass while B60/trend checks remain incomplete;
this never authorizes a whole Technical Engine input.

Zero VR20 denominator yields a per-item UNAVAILABLE check with null value/reason,
not a made-up VR20. Gates never calculate price metrics, scores, ranks or tiers.

Overall result is explicit:

- BLOCKED: invalid identity/structure or unproven critical evidence, inconsistent
  metadata, disallowed origin/mode or declared non-ready quality.
- UNAVAILABLE: no history under an otherwise valid context.
- PARTIAL: some history exists but required sessions/windows or denominator are
  unusable; individual checks retain their precise status/reason.
- READY: all full-window checks pass. Daily-only READY cannot issue an Engine input.

All per-item reasons, references, original typed rows and warnings are retained.
Validation hash deterministically covers request, rows, checks and normalized input.
Key insertion order cannot change the result. Data order is deliberately significant.

## Engine isolation and provenance

Flow: raw typed Daily evidence -> Gate HISTORY READY -> accepted_input() -> public
calculate_metrics/calculate_momentum. The public Engine no longer accepts a manually
constructed ValidatedDailyInput carrying caller-assigned READY flags.

Every entry replays validation from the receipt, checks canonical Gate hash and exact
context, and compares validation hash and Engine projection. Edited/stale receipts,
partial/daily-only results and altered rows/projections fail. In a batch all receipts
are checked before any candidate's metric arithmetic begins. This is a scientific
validation boundary, not an authentication/security token system.

The previous arithmetic is retained as private `_calculate_metrics` and
`_calculate_momentum`, used by existing isolated mathematical tests. Their equations
are not reimplemented. Public tests separately prove the Gate cannot be skipped.
Receipt hash is added to candidate input references; adjustment method and warnings
are preserved. This creates appropriate new evidence revisions rather than rewriting
old snapshots. No total_score/weight/rank/tier rules or canonical artifacts change.

## Production boundary

Canonical Gate v1 deliberately has production_enabled=false. Only explicitly
SYNTHETIC_TEST Daily OHLCV with complete fixture evidence can obtain HISTORY READY.
RESEARCH and PRODUCTION requests remain BLOCKED; relabeling an origin cannot
automatically promote research or archive snapshots. Accepted fixtures retain an
explicit synthetic-only warning; Engine result production_execution remains BLOCKED.

There is no verified production Input Contract or production Universe installed.
Gate proves fixture consistency, never Longbridge volume/VR20, split-only basis,
corporate action semantics, finality or vintage. Those supplier blockers remain.
Real production adapter integration is NOT ready. Read-only official evidence/
field-mapping audits can proceed separately; no source is fetched in this stage.

## Verification

Tests cover individual rules, strict windows, missing/duplicate sessions, naive and
nonfinite input, PIT separation, mixed metadata, deterministic results, immutable
models, old hashes, origin isolation, receipt tampering and rejection before math.
Valid Gate inputs preserve existing score weights/numbers/rank/tier exactly.

Final acceptance (2026-10-16): 76 new Gate cases PASS; 577 related cases PASS
(Gate/Engine, all Momentum foundations, immutable/market Calendar, Factor Snapshot,
Experiment, Evidence Policy and Execution). Backend full: 4169 passed, 6 skipped,
1 xfailed, 214 existing warnings, 239.20 seconds. Normal threading, no worker timing
recurrence or worker changes; host execution uses the established isolated temporary
directory procedure. No frontend changes/tests/build.

Ruff passes all six cumulative changed/new Python files; sensitive, whitespace and
content review covers the nine cumulative planned source/test/doc files. Staged
area remains empty. The previous six-file candidate is retained, with a source-only
recovery copy outside the project in `.tools/momentum-input-gate-prechange-20261016`.
Within it, the inherited Calculation/Score service files and Score Semantics doc
remain byte-identical. AST comparison confirms the original metric arithmetic is
unchanged apart from the private function name. No runtime files or Git history were
modified; HEAD stays 93b92b8c4276194e03eb070b58f5b2780fd8aa96. No commit/push.
