# Momentum Technical Score Semantics v1

Technical Score Semantics CLOSED; Production Execution BLOCKED.
This is definition metadata and pure deterministic arithmetic on caller-supplied
fixtures/inputs. There is no production producer, scheduler, provider integration,
Ranking Engine, API or frontend. No real market data was read for this closure.

## Audit and immutable transition

The existing Calculation/Score side-store, MomentumSnapshot exact contract binding,
Universe membership/coverage contract, Factor research rank patterns and earlier
score design were audited. Research average-rank helpers do not freeze these endpoint,
singleton, cohort and tier rules, so this version uses dedicated standard-library
arithmetic. No dependency or third-party code was added; no GitHub research/copy.

This is a focused L3 additive contract change: existing L1 configuration and L2
notification/router/startup extension points cannot express immutable Score Profile
metadata or these pure mathematics. The only existing Python module edited is the
Momentum-specific contract service. Upstream merge review should retain its legacy
canonical omission and validators; no shared startup, cache, quote or engine entry
point was changed.

`momentum-daily / v1` already defines all required raw metrics and remains unchanged:
`05acb22677f4fc9148916ba5c7b1c012ea15c556befbaa51a422bfa5d21e6a09`.

The old `momentum-technical-v1 / v1` stays definition BLOCKED, execution BLOCKED:
`be55cfbab6d46a03797b883922209b9e7d2afb2d63893830d0ddb922d7e1c35c`.
Its canonical payload omits the newly optional `technical_semantics` field, preserving
old payload bytes/hashes and SQLite records. Nothing overwrites or upgrades it.

New explicit factory: `technical_profile_v1_1(calculation)` in
`backend/app/services/momentum_calculation_contracts.py`.
It requires the exact canonical `momentum-daily / v1` identity.

- Profile: `momentum-technical / v1.1`.
- Definition: DEFINED, with no unresolved mathematical decisions.
- Hash: `03701dc8d08cb15c9640c11df3ad5c47fcc6ced812172860612046da02ca0369`.
- Execution: BLOCKED; source contracts and a production engine are absent/unverified.
- No price-only profile, bootstrap installation, fallback or auto-selection.

## Components and final score

All component and final scores use the closed interval [0, 100].
`P(x)` denotes the ascending percentile score in the fixed scoring cohort.

| Component | Final weight | Definition |
|---|---:|---|
| PriceStrength | 40% | 0.25 P(return_3d) + 0.35 P(return_5d) + 0.40 P(return_10d) |
| VolumeStrength | 25% | P(volume_ratio_20) |
| BreakoutStrength | 20% | 25 breakout_20 + 25 breakout_60 + 20 high_break_20 + 30 high_break_60, booleans mapped true=1/false=0 |
| VolatilityQuality | 15% | 100 − P(volatility_20), lower volatility scores higher |

Breakout uses fixed points, never percentile normalization. No turnover, absolute
volume, inverse volatility, z-score, winsorization, target or cap substitution.
Every input to each component is required. Missing component input yields null;
all four components are required for final score:

`strength_score = .40 PriceStrength + .25 VolumeStrength + .20 BreakoutStrength + .15 VolatilityQuality`.

Missing required component means null score. No zero filling, redistribution,
partial weighted score, mean of available components or fallback profile.
`change_pct` affects tier eligibility only. `consecutive_up_days` stays context/display;
it never affects score, ranking or scoring-cohort selection.

## Exact percentile and arithmetic

For N values, L strictly lower and E equal to the candidate:

`ascending_score = 100 * (L + (E - 1)/2) / (N - 1)` for N > 1.

N=1 yields 50. All-equal values yield 50. Unique endpoints are 0 and 100.
Descending score is `100 - ascending_score`. Ties share a mid-rank score.
An empty cohort produces empty percentile maps, with no artificial observation.

`backend/app/services/momentum_score_semantics.py` uses `Fraction` arithmetic.
Finite int/float/Decimal inputs are converted from their decimal text; Fraction
inputs retain exact ratios. No intermediate/final rounding, epsilon tie grouping,
library-default percentile, NaN, infinity or numeric boolean is accepted.
Exact score equality determines ranks/tiers; a later display layer may format a
score without using its rounded display value to recompute rank.

## Frozen cohort and completeness

Before any percentile, validate one exact comparison identity:

market + trading_date + Universe id/version/hash + Input Contract id/version +
Calculation id/version/hash + Score Profile id/version/hash.

Cross-market, cross-Universe, cross-contract/Profile, duplicate and non-member
candidates are explicit conflicts. There is no market-only, latest, nearby-date,
watchlist or alternate-profile fallback. HK and US cannot be mixed.

The caller must explicitly supply the frozen Universe and per-candidate contract
eligibility evidence. Universe must be READY, match exactly, and cover the whole
trading date in the market timezone. INCLUDED members only may participate.
The pure helper checks supplied declarations; it does not prove real vendor/PIT
facts or resolve official sessions. Those remain future Input Contract duties.

The nine scoring raw metrics are return_3d/5d/10d, volume_ratio_20,
volatility_20 and four boolean breakout metrics. They must all have READY status,
non-null finite/type-valid values, and satisfied exact Input Contract requirements.
VR20/volatility must be nonnegative and returns cannot be below −1.
Missing/invalid/non-READY candidates are excluded BEFORE every percentile.
Every percentile uses exactly this same fixed set. Nothing is removed afterward.

Missing Universe members/candidates or scoring exclusions are enumerated with
reasons and `scoring_coverage_incomplete_no_complete_market_ranking`. A valid
scoring subset is not a claim of complete MARKET_WIDE ranking. An unverified or
incomplete Universe blocks validation outright. An empty eligible set returns
empty score/rank/tier maps with explicit exclusion/coverage information.

The Profile declares `change_pct` as required for its full score-and-tier output,
but it is NOT a scoring-component dependency. Missing/invalid/non-READY
`change_pct` leaves score/rank intact, produces no tier for that symbol and emits
`tier_eligibility_input_missing`. `return_5d` already is a required scoring input.

## Rank, tier and small N

Rank all non-null scores in the scoring cohort, score descending. Competition rank:
100, 95, 95, 90 gives 1, 2, 2, 4. Symbol sorts presentation only; it cannot break
numerical score/rank ties.

Tier eligibility: non-null score AND change_pct > 0 AND return_5d > 0.
Order this separate subset by descending score. Its N and local positions, rather
than the wider scoring cohort's ranks, determine tier boundaries:

- T1 nominal boundary: ceil(N * .05).
- T2 cumulative nominal boundary: ceil(N * .20).
- T3: remaining eligible candidates; no tier for ineligible candidates.

If a boundary intersects a score tie, the entire equal-score group gets the higher
tier. Equivalently, compare each tied group's competition rank within the
tier-eligible subset with the nominal boundaries. Tier sizes may exceed 5%/20%.

N=1: T1. N=2 with different scores: top T1, other T3; no forced T2.
N=2 tied: both T1. Empty eligible set: no tiers. Changes to the tier subset do not
alter score-cohort percentiles or the wider competition ranks.

## Persistence, compatibility and production boundary

The existing append-only `MomentumCalculationStore` persists the new opt-in
Profile in the same dedicated metadata SQLite store. Same ID/version/content is
idempotent; changed content at the same ID/version is rejected. Exact hashes are
required on reads. No migration, deletion or runtime SQLite file is committed.

New semantic metadata freezes internal weights, point mappings, endpoint formula,
singleton policy, cohort/missing rules, score range, tie expansion and arithmetic.
Existing component weights, exact metric references, directions, thresholds and
ranking rules also remain in the Profile hash. Set-like ordering is canonical.
Pure composed validation accepts only the exact v1.1 Profile; a changed/future
profile needs its own explicit helper support, never automatic adaptation.

MomentumSnapshot already carries calculation ID/version/hash and selected Profile
ID/version/hash. No Snapshot schema change or default resolver is needed.
Supplier/input eligibility is not inferred from definition status or arithmetic.
The validation result retains `execution_eligibility=BLOCKED`, including fixtures
that explicitly declare their supplied inputs READY.

Longbridge volume/VR20 and split-only basis remain BLOCKED, corporate actions
UNKNOWN, Daily finality PARTIAL, historical PIT/vintage BLOCKED. Supplier
confirmation is still pending. No real input contract, production Universe,
Momentum Engine, production Score/Ranking Engine or producer was created.

Technical Score Semantics CLOSED != Production Execution READY.

## Validation

Tests use isolated in-memory arithmetic and fixture stores only. Acceptance covers
percentile ties/endpoints/N=1, each mapping/weight, null propagation, exact shared
cohort and coverage, market/identity separation, competition rank, tier subset/tie
expansion/small N, legacy hashes, immutable persistence and exact Snapshot binding.

Acceptance (2026-10-15): 75 new cases are included in 375 passing related tests
(Calculation, Snapshot binding/store, Universe, Factor Snapshot, Experiment,
Evidence Policy and Execution). Full backend: 4045 passed, 6 skipped, 1 xfailed,
214 existing warnings, 309.91 seconds. Full used the established host execution
with an isolated temporary directory and normal threading. Worker timing did not
recur; no POLARS_MAX_THREADS constraint or worker change was needed.
Changed/new Python files pass Ruff. Sensitive/whitespace/content review covers the
five planned files. Frontend unchanged; no frontend tests/build were run.
