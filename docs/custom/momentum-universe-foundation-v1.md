# Momentum Universe Contract Foundation v1

## Current Universe audit

This is a code/contract audit at baseline `08c2feeb`. No live security list,
watchlist contents, provider credentials or production database was requested.
Existing behavior is preserved.

| Existing component | Actual collection and boundary | Momentum suitability |
| --- | --- | --- |
| `plugins/longbridge/provider.py:get_realtime_universe` | US-only wrapper over `QuoteContext.security_list(Market.US)`; returns symbol strings, not classified membership artifacts | Provider-available directory candidate, not exchange-complete/PIT Universe; current wrapper rejects HK |
| `services/us_dashboard_service.py:refresh_universe` | Mutable in-memory US provider sweep, batches of 500, latest-date quote cohort; coverage explicitly says includes ETFs/other securities and `exchange_complete=False` | Display/statistics coverage, not frozen ordinary-stock membership |
| US Dashboard fallback candidates | Six core samples, movers, cache/focus, bounded display set | Dynamic candidates; not market-wide |
| `services/hk_dashboard_service.py` | Movers plus cached/focus symbols, capped at 20 | Dynamic candidates/UI set; not HK directory |
| `services/instrument_sync.py` | SH/SZ/BJ provider instrument directory, flattened symbol/name/code/exchange/type metadata and current `as_of`, written to instruments Parquet | CN directory metadata, not a verified historical HK/US Universe; an exchange/provider origin is not immutable membership proof |
| `services/watchlist.py` | Mutable user membership/groups in Parquet/JSON; process-local revision counter | Watchlist only; no durable historical membership/vintage identity |
| `services/screener.py` | Instrument joins against existing enriched snapshots/history with asset-specific paths | Computation/data coverage set, not authoritative security directory or frozen universe |
| `services/factor_snapshots.py` | Frozen sorted score-cohort symbols, membership hash/size, supplied as-of/availability evidence | Existing calculation-cohort semantics; no general classified membership registry, no change here |

No inspected source path already provides the full HK/US contract of classified,
complete, versioned, historically available membership. No real source is promoted
to production Universe by this Foundation. A large list is not proof of coverage.

Existing normalization is context-specific: `market_session.market_from_symbol`
checks market namespace; HK/US Dashboard validators check their display symbol
formats; `services/ext_data.normalize_symbol` contains CN code-to-exchange fallback
and must not be reused to guess HK/US identity. No stable cross-provider security
ID or corporate-identity timeline was established in these paths. Display names
are not keys. Future source adapters must prove listing/delisting/rename and alias
identity; the Foundation does not infer them.

## Architecture and model

`backend/app/services/momentum_universes.py` adds frozen Pydantic models and one
independent SQLite side store. It reuses the Momentum Snapshot canonical JSON,
hash/label/status types and the existing market namespace validator. No registry,
ORM, dependency, provider, generic repository, API, frontend or startup hook is
added. Existing Snapshot, Factor, Evidence Policy and anomaly code is unchanged.

`MomentumUniverseDefinition` contains:

- Universe ID/version, market (HK/US), type and derived content hash.
- Effective interval, generated/available/stored timestamps.
- Source, source kind/version/references, membership vintage and availability proof.
- Allowed instrument types, explicit exclusion rules and frozen member tuples.
- Expected/effective/missing/excluded counts and coverage evidence.
- Explicit quality status, PIT status, blockers and warnings.

Universe types: MARKET_WIDE, CUSTOM, WATCHLIST, INDEX_CONSTITUENTS. Source kinds:
DIRECTORY, CUSTOM, WATCHLIST, DYNAMIC_CANDIDATES, DISPLAY_SET, INDEX_CONSTITUENTS.
MARKET_WIDE requires a DIRECTORY declaration; WATCHLIST and INDEX_CONSTITUENTS
require the matching source kind. This validates the declared scope, not a vendor's
truthfulness or real market completeness. CUSTOM may explicitly freeze a finite
subset from any source kind. Dynamic/display/watchlist sets are never silently
upgraded. No production Universe of any type is created here.

## Membership and eligibility

Each member records symbol, explicit market/instrument type, INCLUDED/EXCLUDED/
UNRESOLVED decision, effective interval, evidence reference and decision reason.
EXCLUDED/UNRESOLVED require reasons. Missing/unknown evidence is retained only with
non-READY quality and the `membership_evidence_missing` blocker.

Symbols normalize whitespace/case only and must agree with the explicit market
namespace. Duplicate normalized symbols and mixed-market membership are rejected.
There is no HK zero-padding, US share-class/provider alias or display-name mapping.
For example `700.HK` and `0700.HK` are not automatically asserted equivalent.
Future producers must supply canonical source identities and resolve aliases
before freezing; this layer does not certify a symbol's existence or provider support.

Instrument types are explicit: COMMON_STOCK, ADR, ETF, REIT, PREFERRED, WARRANT,
RIGHTS, BOND, FUND, OTHER, UNKNOWN. None is inferred from a symbol, provider list
or price. INCLUDED requires an allowed type and must not match explicit symbol/
instrument-type exclusions. UNKNOWN cannot be INCLUDED even if listed in allowed
types; it remains unresolved or explicitly excluded. OTHER is an explicit source
classification, not an automatic substitute for UNKNOWN.

Exclusion rules are only exact normalized symbol sets and instrument-type sets.
The Foundation validates decisions; it does not generate or filter membership
from a provider list. More complex eligibility would require another explicit
contract, not opaque executable expressions or guessed defaults.

Members must be effective for the entire Universe interval. Their evidence interval
may be broader. This makes the frozen membership and counts stable throughout the
declared interval. A membership change uses a new version/interval; there is no
implicit daily filtering of a mutable member list.

## Completeness and quality

`expected_count` means the source candidate population **before** eligibility
exclusions. It needs independent source/coverage evidence; it must not be invented
by simply counting downloaded rows. `effective_count` counts INCLUDED rows;
`excluded_count` counts EXCLUDED rows; derived `unresolved_count` counts UNRESOLVED
rows. `missing_count` counts source candidates not represented by any frozen row.

For known expected count:

`expected_count = effective_count + excluded_count + unresolved_count + missing_count`.

For unknown expected count, both expected/missing counts are null,
`expected_count_unknown` warning is mandatory, and status cannot be READY.
Counts are nonnegative strict integers and are checked against member decisions.
READY also requires nonzero eligible membership, no missing/unresolved candidates,
source/version, coverage evidence, member evidence, PIT READY and no blockers.
All are necessary structural checks; they do not independently certify the source.
PARTIAL, UNAVAILABLE and BLOCKED artifacts preserve explicitly supplied quality.
The Foundation does not compute a business readiness score or promote status.

## Identity, immutability and revisions

Canonical compact sorted UTF-8 JSON includes the complete definition, market/type,
sorted normalized membership and instrument types, eligibility, effective interval,
source identity/version/evidence, quality and generation/availability metadata.
Reference/rule/warning sets are sorted; members sort by symbol. All aware times
normalize to UTC. SHA-256 of this payload is `content_hash`. Only `stored_at` is
excluded. `to_dict()` exposes the derived hash and unresolved count; model JSON
contains the underlying content and deterministically reconstructs that hash.

Exact identity is `(market, universe_id, universe_version, content_hash)`. Version
is the explicit membership revision; no separate automatic revision counter exists.
Same ID/version plus same canonical payload is an idempotent no-op. Different
content at the same ID/version is an explicit conflict, including changed evidence
or generation metadata. A changed membership/evidence artifact requires a new
explicit version and hash. Old versions remain readable and are never overwritten.
An ID cannot change its market or universe type between versions; use a distinct
ID. In particular HK and US rankings cannot share a mixed-market identity.

## Effective time versus knowledge/PIT

Effective intervals are aware instants `[effective_from, effective_to)`; null end
means unbounded, not an inferred calendar end. Dates must be mapped to instants by
a future producer using an explicit market calendar/timezone contract. Effective
membership at D does not prove knowledge of membership before D.

`generated_at` is artifact creation; `available_at` is artifact availability backed
by membership vintage/availability evidence; null means unknown. Availability must
not precede generation. `stored_at` is assigned by the local UTC clock on first
insertion and cannot be backdated by caller input. Future generation/availability
is rejected on save. All non-null times are aware and normalized UTC; naive inputs
are rejected, never relabeled UTC. Unknown availability cannot claim PIT READY.
PIT READY needs explicit availability, membership vintage, availability reference
and source references. Merely fetching the current directory now cannot establish
historical membership vintage; effective time can be historical while PIT remains
BLOCKED. The store's current insertion time remains part of every as-of gate.

## Persistence and exact resolver

Path: `data_dir/user_data/momentum_universes.sqlite3`, separate from every existing
store. Construction and empty reads do not create it. Explicit save initializes
the schema deterministically. `BEGIN IMMEDIATE` serializes conflict check/insert;
primary key `(universe_id, version)`, exact identity index and bound SQL provide
immutable, transactional, indexed access. No update/delete method exists.

- `get_by_identity(MomentumUniverseIdentity(...))` returns that exact artifact or
  None, including non-ready evidence for inspection. Missing version is invalid.
- `query_exact(identity, effective_at=..., as_of=...)` is the strict resolver.
  It checks effective interval, generation, availability and actual storage cutoff.
  Future/unseen/out-of-period records are UNAVAILABLE; unknown/unproven membership
  availability is BLOCKED. Otherwise it returns the original quality status and
  frozen record. It never upgrades PARTIAL evidence to READY.
- Reads use SQLite `mode=ro` and verify hash/identity against payload. Wrong hash,
  market or version yields no match. No market-only, latest, nearest-date,
  watchlist, provider-list or missing-version fallback exists.

## Momentum Snapshot binding

Existing `MomentumIdentity` already accepts exact `universe_id`, `universe_version`
and `universe_content_hash`. A future producer explicitly copies the frozen
Universe's ID/version/content hash, then uses the exact resolver and validates the
symbol's INCLUDED decision. No Snapshot change or automatic Universe lookup was
needed. Future rankings must also match market, trading date, input contract and
calculation version; this Foundation does not rank anything.

## Production behavior and unresolved sources

Production Universe producer: **NO**. No Longbridge security-list request, watchlist
freeze, automatic directory import, market scan or MomentumSnapshot generation is
wired into application startup. Empty production Store is valid. Runtime SQLite
files remain ignored; all new records in tests are explicitly isolated fixtures.
There is no real consumer yet, so typed Store only: no API or frontend changes.

Unresolved real HK/US sources still need market coverage denominator, trustworthy
instrument classifications/eligibility, source revision, historical membership
vintage, alias/listing/delisting evidence and availability proof. The HK wrapper's
current absence is not proof the vendor lacks HK securities data. No provider
permissions or completeness were probed during this stage.

Longbridge volume/VR20 and split-only basis remain BLOCKED, corporate actions
UNKNOWN, Daily finality PARTIAL and historical PIT/vintage BLOCKED. Supplier
confirmation remains pending. These do not prevent a provider-neutral Foundation,
and they are not upgraded by a fixture passing structural validation.

Universe Foundation READY does not mean HK production Universe READY, US production
Universe READY, Momentum Input Contract READY or Momentum Ladder READY. Next work
is an explicit real source/eligibility/vintage contract, not automatic production
membership or Momentum calculations.

## Acceptance evidence (2026-10-15)

- 54 new Universe cases pass within the 154-case related run, including Momentum
  Snapshot, Factor Snapshot and Evidence Execution regression tests.
- Backend full: 3921 passed, 6 skipped, 1 xfailed, 214 warnings, 280.19 seconds.
  Host execution used normal threading and a project-external isolated test
  directory, following the previously verified sandbox temporary-directory limit.
  The worker timing issue did not recur; no `POLARS_MAX_THREADS=1` constraint or
  worker modification was used.
- Ruff passes for both new Python files; no unrelated baseline cleanup. Sensitive,
  whitespace and final content review pass for the three planned files. Runtime
  DB paths are ignored. No frontend changes or frontend test/build run.
- These are fixture/contract results. No real HK/US Universe, provider request or
  production membership/metadata validation was performed.
