# Momentum Calculation Engine Foundation v1

Engine Foundation READY is limited to isolated pure calculation on declared validated
inputs. HK Production Momentum BLOCKED; US Production Momentum BLOCKED.
No provider, production Universe/producer, API, frontend, scheduler, worker, Store
writer or startup registration was added. No real quotes/Daily bars were requested.

## Audit and minimal boundary

Audited Snapshot v1, Universe, Calculation/Score contracts and exact metadata Store,
the immutable Calendar/registry, HistoricalDailyResult research schema, MetricEvidence
and State, and the existing score helpers/tests. Historical research rows do not
prove split-only prices, comparable quantities, finality or vintage and are NOT
adapted automatically into Engine inputs. The InStock source map was consulted;
its indicator/network/persistence paths do not implement these frozen Momentum
contracts. No third-party source was copied or dependency added.

This is a focused L3 addition to the Momentum services. Existing L1 configuration
and L2 startup/router/notification extension hooks cannot express pure calculations
or immutable typed definitions. No shared quote, archive, Factor, anomaly,
Historical/Market Context, policy, startup or routing implementation changed.

`backend/app/services/momentum_engine.py` contains typed input/result models,
`calculate_metrics`, `volatility_trend`, `calculate_momentum`, and Snapshot v2
candidates. Existing percentile, component, score, competition-rank and tier helpers
are reused. The Engine accepts exact artifacts explicitly; it never opens SQLite,
selects latest, queries a provider, constructs a Universe or changes quality rules.

## Versioning and unchanged artifacts

| Artifact | Version | Canonical SHA-256 |
|---|---|---|
| momentum-daily, old | v1 | 05acb22677f4fc9148916ba5c7b1c012ea15c556befbaa51a422bfa5d21e6a09 |
| momentum-technical-v1, blocked legacy | v1 | be55cfbab6d46a03797b883922209b9e7d2afb2d63893830d0ddb922d7e1c35c |
| momentum-technical, existing | v1.1 | 03701dc8d08cb15c9640c11df3ad5c47fcc6ced812172860612046da02ca0369 |
| momentum-daily, extended | v1.1 | 790212a4fd6ac7f3c50f2941a1eb51e192ebd873ac3c796cc07a0dd12460e7de |
| momentum-technical, explicit extended binding | v1.2 | 8c48c32df331939908af76363e697827eda83de41639b80767e160be22d0832f |

`calculation_with_trend_v1_1()` retains the original twelve metric definitions and
adds one independently identified metric. `technical_profile_v1_2(calculation)`
retains all v1.1 scoring mathematics; only its own version and exact Calculation
binding change. A distinct Profile is necessary because the frozen v1.1 Profile
binds Calculation v1 exactly. No automatic rebinding/fallback occurs.

The existing metadata Store accepts both versions through its unchanged exact
immutable save/read behavior. Tests save definitions only to temporary fixture
stores. No migration, bootstrap or production metadata installation occurs.

## Quality versus volatility trend

`volatility_status` remains QUALITY_STATUS: READY/PARTIAL/UNAVAILABLE/BLOCKED,
propagating current sigma quality. Its metric version/hash/meaning do not change.

New `volatility_trend_status` has only EXPANDING/CONTRACTING/UNCHANGED, or null.
For sigma20(D) and sigma20(previous exact completed session), compare actual
computed values with >, < or ==. No tolerance, threshold or rounding is applied.
Both sigmas use sample standard deviation (ddof=1) of 20 log returns, non-annualized.
The two overlapping windows require 22 contiguous session closes in total.

Missing current/previous sigma, missing session, non-READY quality or invalid
values produces null with independent MetricEvidence status/blockers/references.
UNCHANGED is never a missing-data substitute. PARTIAL quality remains non-ready;
BLOCKED quality cannot be promoted. No upward probability interpretation exists.
Trend does not participate in scoring eligibility, normalization, weights or tier.

## Typed inputs and exact sessions

ValidatedDailyInput supplies exact MomentumIdentity, immutable DailyBar tuples,
source/evidence references, price/quantity/PIT declarations, source vintage,
knowledge_cutoff and generated_at. These are caller-provided evidence declarations,
not Engine authentication of a supplier's facts. Numeric values must be finite;
numeric booleans and naive availability/generation times are rejected. Times are
normalized to aware UTC, with no assumption about naive upstream candle times.

The exact immutable Calendar is revalidated, including its hash. Market, Calendar,
Calculation, input identity and effective trading date must match. The Engine
enumerates official weekdays/holidays/additional sessions inside coverage, not
dates on which bars happen to exist. Duplicate, non-session and future bars are
rejected. Missing required dates yield null with reasons, never suspension guesses,
date skipping, shortened windows, zero filling or alternate sources.

Every consumed bar must have explicit READY finality evidence, session close not
later than knowledge_cutoff and proven bar availability between session close and
cutoff. Close uses the frozen regular session or half-day early close and market
timezone. Source vintage/PIT proof is required separately; bar date is not
publication time. Missing/blocked price basis and quantity semantics block their
respective branches independently. Source contract declarations are not inferred
from numeric samples, unit labels or the existence of this Engine.

MetricEvidence references contain input proof plus the consumed window's bar and
finality references. An unrelated older bar is not attached as used evidence.
generated_at is caller-supplied computation time; when input availability is proven,
candidate available_at denotes availability of the computed candidate at generation,
not historical vendor publication. Unproven availability/vintage retains null
available_at and cannot yield PIT READY. This envelope check conservatively covers
all supplied bars, including the extra prior-sigma observation, even when current
sigma or some scoring metrics can independently be READY.

## Raw metrics

Definitions/metric IDs/versions/hashes come from the explicitly supplied canonical
Calculation. Return/change_pct uses C_D/C_previous−1 over exact session intervals.
Consecutive-up scans strict adjacent increases until a proven equality/down boundary;
missing prior history cannot imply zero or a completed run length.

B20/B60 compares current close with preceding highs, HB20/HB60 current high with
preceding highs; D is excluded and equality is false. VR20 uses 21 observations,
divides current volume by the preceding twenty-session average, excludes D from
the denominator, and returns null for missing quantities or zero denominator.
The Engine cannot override BLOCKED quantity comparability.

sigma20 uses log(C_t/C_previous) over 20 exact intervals, then sample standard
deviation. No annualization, scaling or regime threshold. Nonfinite intermediate
ratios/results produce explicit null/BLOCKED output rather than NaN/infinity.
Return/VR fractions are converted only after calculation; score helpers retain exact
rational arithmetic. Snapshot float score is an output representation, never used
to recompute ranks/tiers; the result also retains the exact rational scoring result.

## Cohort, score and explicit candidate status

The Engine verifies batch identities, passes metric values AND quality to existing
fixed-cohort validation, then reuses the exact 40/25/20/15 components, internal
25/35/40 price weights, boolean breakout points and descending-volatility percentile.
No Factor total_score, price-only fallback, missing=0 or redistribution is permitted.
Missing/blocked scoring candidates are excluded BEFORE percentiles. Exclusions and
coverage warnings are preserved. HK/US and any identity/version cannot be mixed.

MomentumEngineResult stores exact cohort identities, per-input metric results,
scoring/exclusion reasons and expected_count/valid_count/excluded_count.
Here expected_count is the frozen Universe's INCLUDED/effective membership count
(the eligible cohort denominator). Universe source-level expected/excluded/missing
counts retain their original distinct meaning and artifact identity.

Competition rank and tier-eligible subset semantics remain unchanged. Trend missing
does not remove an otherwise score-ready candidate. change_pct affects tier only.

Candidate overall status uses an explicit conservative Engine policy: any blocked
metric gives BLOCKED; all metrics READY plus score yields READY; otherwise some
READY metrics gives PARTIAL and none gives UNAVAILABLE. A missing tier or scoring
coverage warning downgrades otherwise READY output to PARTIAL. Unproven PIT cannot
produce an overall READY candidate. This does not change the Snapshot Foundation's
explicit-storage rules and is not a claim of production readiness.

## Snapshot and production isolation

Calculation v1 produces ordinary Snapshot v1 candidates. Calculation v1.1 produces
MomentumTrendSnapshotCandidate with `snapshot_version=momentum-snapshot-v2`, an
independent trend value/evidence pair and exact new Calculation/Profile bindings.
Its ID prefix is momentum-v2. Calculation ID/version/hash and Profile identity
already distinguish logical identity, and the v2 payload determines revision.

Snapshot v1 fields/validation/hash and persisted rows remain untouched. Old v1
payloads cannot become v2 records. New trend candidates reject old Calculation or
Profile identities. The existing Snapshot Store intentionally rejects v2 before any
DB initialization: no new persistence writer/migration was added in this phase.
There is no automatic save for either schema.

All stores/Universe/Daily inputs used by tests are synthetic/test-only and isolated.
The Engine never constructs them on application startup. Production Momentum and
Universe producers remain NO; provider selection and archive acceptance are unchanged.

## Remaining blockers and validation

Longbridge volume/VR20 and split-only basis BLOCKED; corporate actions UNKNOWN;
Daily finality PARTIAL; historical PIT/vintage BLOCKED; supplier confirmation
pending. Real frozen HK/US production Universes remain absent. Engine Foundation
READY does not close any of these facts or authorize production execution.

Tests cover strict trend comparisons/missing inputs, all raw metric families,
window/finality/PIT gates, exact versions/golden old hashes, score compatibility,
Snapshot schema separation, Store rejection and blocked-source null propagation.
Existing pure score tests continue to cover percentile/ties/cohort/rank/tier boundaries.
Final acceptance (2026-10-16): 48 new Engine cases PASS; 501 related cases PASS
including all Momentum, immutable Calendar, Market Calendar, Factor Snapshot,
Experiment, Evidence Policy and Evidence Execution cases. Final backend full:
4093 passed, 6 skipped, 1 xfailed, 214 existing warnings, 311.20 seconds.
Ruff passes all four changed/new Python files. Sensitive and whitespace/content
review cover the six planned source/test/doc files. Staged area remains empty;
no runtime files, API/frontend changes or frontend suite/build.

Full runs used the previously verified host execution with project-external isolated
temporary directories. POLARS_MAX_THREADS was not set; worker timing did not recur
and no worker architecture was changed. Earlier full passes preceded final
availability-proof refinements; the result above is for the final implementation.
No commit/push is authorized or performed.

## Subsequent Input Contract Gate

[Input Contract Gate v1](momentum-input-contract-gate-v1.md) adds the public input
boundary without changing this phase's Calculation/Profile hashes or equations.
Public calculate_metrics/calculate_momentum now require replay-verified Gate inputs;
the original mathematical core is private and its existing tests remain isolated.
Caller-assigned READY declarations alone are no longer accepted. Adjustment method,
source warnings and Gate receipt reference are retained in candidate evidence.
Production execution remains BLOCKED, and this earlier acceptance record describes
the Engine phase before the subsequent Gate acceptance recorded in its own document.
