# Momentum Calculation & Score Profile Contract Foundation v1

## Scope and audit

Baseline `f0a7dd74`. Definition metadata only: no metric, score, percentile, rank or
tier calculation, provider request, producer, production Universe, API or frontend.
All persisted validation artifacts are isolated fixtures.

Audited patterns: Momentum Snapshot/Universe frozen models and side stores; Factor
registry parameter/component/version dependencies; Factor Snapshot exact provenance;
immutable Experiment definitions; multi-factor research scoring; Strategy scoring
weights/directions; Evidence Policy immutable versions; exact Trading Calendar
ID/version/hash; existing canonical JSON/SHA-256 helpers.

Existing research scoring is equal-weight complete-case, with average ranks,
`(rank-1)/(N-1)` and singleton/equal-cohort neutrality. It is not automatically
adopted as a Momentum product contract. The registry's annualized volatility is not
this non-annualized metric. Existing Factor/Strategy engines are neither changed
nor invoked. Formula strings below are inert metadata, never evaluated. No DSL,
BaseMetric, generic registry/repository, ORM or dependency is introduced.

## Calculation definition and dependencies

`MomentumCalculationDefinition` freezes calculation ID/version/hash and a tuple of
`MomentumMetricDefinition`: key/version/hash, formula, required inputs/history,
history rule, price/volume/calendar/finality/PIT requirements, output type,
nullability, missing-input behavior and unresolved-definition blockers.
`CalculationIdentity` and `MetricReference` require exact IDs/versions/hashes.
Definition status is DEFINED when no declared definition gaps remain; execution
eligibility is separately BLOCKED throughout this non-executing Foundation.

Explicit opt-in `candidate_calculation_v1()` defines `momentum-daily / v1`:

| Metric | Completed sessions | Definition |
| --- | --- | --- |
| change_pct | 2 | `C_D/C_(D-1)-1`, fraction |
| consecutive_up_days | Data-dependent | Maximal contiguous strict close-to-previous-session increase run ending D; stop at first non-increase; missing boundary/history means null |
| return_3d / return_5d / return_10d | 4 / 6 / 11 | `C_D/C_(D-n)-1`; n exact session intervals |
| breakout_20 / breakout_60 | 21 / 61 | Current close > maximum preceding 20/60 session highs, excluding D |
| high_break_20 / high_break_60 | 21 / 61 | Current high > maximum preceding 20/60 session highs, excluding D |
| volatility_20 | 21 | Sample standard deviation, ddof=1, of 20 daily log returns ending D; non-annualized |
| volatility_status | 21, via volatility_20 | Quality status propagation matching Snapshot's status slot, not a volatility-regime classification |
| volume_ratio_20 | 21 | `V_D/mean(V_(D-20),...,V_(D-1))`, excludes D |

Return inputs are close; breakout inputs close/high; high-break inputs high;
volatility inputs close; VR20 inputs volume. Daily windows are exact contiguous
trading sessions, not natural days or the most recent available rows. Consecutive
days have no invented finite warmup; incomplete prior history cannot imply zero.
Positive price/divisor requirements are declared. Price metrics require
split-adjusted-price-only; VR20 independently requires corporate-action-comparable
quantity semantics. All require exact immutable calendar sequence, final completed
Daily sessions and inputs known by the knowledge cutoff. Snapshot binds the exact
calendar; this module does not select a calendar or read bars.

`MissingInputContract` freezes null result, missing status/reason, contract-conflict
status/reason and partial-input status. Candidate rules are UNAVAILABLE for missing
input/session, BLOCKED for conflicting/unverified semantics, PARTIAL for explicitly
partial evidence. No zero/forward/backward fill, skipped session, shortened window,
provider or adjustment substitution is allowed. These are rules, not execution.

## Score profile and unconfirmed decisions

`MomentumScoreProfile` binds one exact Calculation identity. Each component freezes
key, integer weight in basis points, exact metric dependencies, aggregation,
direction and eligibility. Weights sum to 10000; scoring dependencies must be exact
required metrics. Optional metrics cannot silently substitute. No missing-required
component may yield a score: result stays null with explicit status/reason, without
weight redistribution, missing-as-zero, available-component mean or fallback profile.

`candidate_technical_profile_v1(calculation)` defines the known candidate envelope:
`momentum-technical-v1 / v1`, price 4000 bps, volume 2500, breakout 2000, volatility
quality 1500. **Candidate definition_status=BLOCKED; execution_eligibility=BLOCKED.**

The inspected repository/vault did not contain the referenced complete Momentum
Contract Design v1. The request fixes weights/formulas but does not uniquely fix
component metric mappings/combinations, volatility quality direction/transform,
percentile endpoint/singleton formula, or competition-vs-dense rank numbering.
Clarification was requested; unresolved fields remain null with named blockers.
No defaults are invented and a complete technical profile is not claimed DEFINED.

The schema supports a fully DEFINED profile given explicit decisions. Tests use
`fixture-technical` choices only, not product defaults. No canonical price-only
profile is defined because its weights/mappings are unconfirmed and there is no
consumer. An isolated `fixture-price-only` proves separate identity/selection and
BLOCKED execution. Missing volume never selects it automatically.

## Normalization, tiers and ranking

Supported declaration: same-universe percentile with average ordinal mid-ranks,
explicit formula version, singleton behavior and incomplete-coverage behavior.
Incomplete Universe must block or expose coverage warnings, never silently claim
full-cohort percentile; the canonical candidate blocks it. Its precise boundary
formula/singleton policy remains unresolved. Research's formula is not silently reused.

`TierContract`: eligibility `change_pct>0 AND return_5d>0`; T1 rank boundary
`ceil(valid_candidate_count*0.05)`, T2 `ceil(valid_candidate_count*0.20)`, otherwise
T3 for eligible candidates. Same-score candidates share tier. `RankingContract`
freezes descending score, all exact comparison dimensions, and symbol tie-breaking
for display only, never rank/score. Rank numbering is explicit or BLOCKED, not guessed.

Comparison dimensions: market, trading date, Universe ID/version/hash, Input
Contract ID/version, Calculation ID/version/hash and Score Profile ID/version/hash.
`MomentumRankingCohort` is only this required identity envelope, rejecting
market/Universe conflicts. No ranking, percentile, tier assignment or candidate
selection occurs. Classification remains a separate future layer.

## Canonical identity, persistence and resolver

Sorted compact UTF-8 JSON freezes formulas, lookbacks, dependencies, requirements,
normalization, weights, missing behavior, tiers/ranking and blockers. Set-like
fields, metrics/components/references have deterministic ordering. SHA-256 gives
metric, Calculation and Profile hashes. No database ID or stored time enters hash.
Formula bytes are identity content; there is no algebra/expression interpreter.
`to_dict()` includes derived hash/status; model JSON round-trips underlying content.

`MomentumCalculationStore`: independent
`data_dir/user_data/momentum_calculation_contracts.sqlite3`, initialized only by
explicit save. One metadata table has primary key `(kind,object_id,version)`.
Same content is idempotent; same ID/version with different content is a semantic
collision. New semantics require a new explicit version; old artifacts stay frozen.
`BEGIN IMMEDIATE` serializes check/insert and stored time is aware UTC.

Profiles require an already stored exact Calculation. Every declared metric
dependency must match its key/version/hash. `get_calculation`/`get_score_profile`
use exact ID/version/hash with SQLite mode=ro and validate payload identity/hash.
`resolve_cohort_contracts` checks the requested Calculation/Profile link. Exact
binding, definition completeness and execution eligibility are distinct results.
No latest/nearest/fallback/auto-upgrade/price-only selection or input lookup occurs.
An incomplete stored candidate is immutable too; completing it requires a new version.

## Additive Snapshot binding

Existing calculation version and score ID/version were insufficient to prove exact
artifacts. Optional `calculation_id`, `calculation_content_hash` and
`score_profile_content_hash` were added. New exact bindings require Calculation
ID/version/hash plus selected Profile ID/version/hash. Disabled profile stays null.
No default Calculation/Profile is discovered or installed by Snapshot.

Old payloads lacking added fields are `LEGACY_INCOMPLETE`, with original logical
key/revision/ID preserved: null added fields are omitted from canonical identity and
payload. Existing SQLite rows are read without rewriting; no table migration.
New exact bindings have distinct identities and cannot match legacy records through
fallback. `contract_binding_status=EXACT` denotes complete identity fields, not
executable score or verified market inputs. Existing legacy READY data is not
retroactively reclassified as exact-contract proof.

## Production boundary and remaining work

Production calculation producer: NO. Calculation/Score/Ranking Engine: NO.
No startup materialization; metadata store may be empty until explicit saves.
No provider, Factor, Evidence Policy, Universe production, anomaly or benchmark
behavior changes. No API/frontend; typed Store/resolver is sufficient without a consumer.

Longbridge HK/US Daily read remains PROVEN; volume/VR20 and split-only basis BLOCKED;
corporate actions UNKNOWN; Daily finality PARTIAL; historical PIT/vintage BLOCKED.
Supplier confirmation remains pending. Formula/requirement metadata never proves
the supplier satisfies it. This Foundation version cannot declare execution READY;
a future verified Input Contract and engine need explicit versioned implementation.

Calculation Foundation READY != Calculation Engine READY.
Score Profile DEFINED != Score executable.
Momentum Foundation READY != Momentum production READY.

Next: confirm component mappings/transforms, percentile endpoints/singleton policy
and rank tie numbering, then freeze a new complete profile. Supplier/Input Contract
closure proceeds independently; no production calculation or implicit price-only scoring.

The subsequent [Technical Score Semantics v1](momentum-technical-score-semantics-v1.md)
closes these product-math decisions in a distinct `momentum-technical / v1.1`
Profile. The original blocked `momentum-technical-v1 / v1` and `momentum-daily / v1`
remain immutable with their original hashes. Pure deterministic helpers validate
explicitly supplied inputs; production execution and supplier blockers remain BLOCKED.

## Acceptance evidence (2026-10-15)

- 49 new contract/binding cases within the final 300-case related run pass,
  including Snapshot/Universe, Factor Snapshot, Experiment, Evidence Policy and
  Evidence Execution compatibility. Old-format SQLite payloads retain their exact
  logical key/revision/ID and are not rewritten on read.
- Full backend: 3970 passed, 6 skipped, 1 xfailed, 214 warnings, 295.19 seconds.
  Host execution uses normal threading and a project-external isolated test path,
  following the previously verified sandbox temporary-directory limitation.
  Worker timing did not recur; no Polars thread constraint or worker change.
- Ruff passes for four changed/new Python files. Sensitive, whitespace and final
  content review cover the six planned files. Runtime SQLite paths remain ignored.
  No frontend changes/tests/build or real production calculation validation.
