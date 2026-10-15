# Momentum Snapshot Foundation v1

## Scope and architecture

`backend/app/services/momentum_snapshots.py` provides a provider-neutral frozen
Pydantic record and an independent SQLite side store, following the existing
Factor Snapshot and Intelligence store patterns. It does not import providers,
Factor Engine, calendars, anomaly services or scoring code. No generic repository,
ORM, dependencies, startup wiring, API or frontend are introduced.

There is no production producer. Importing the module or constructing the store
does not create a directory or database. Empty reads return `None`/`()`. Only an
explicit `save()` initializes `data_dir/user_data/momentum_snapshots.sqlite3`.
Runtime SQLite files remain ignored by Git. Tests write isolated fixtures only.
An API is deferred until a real consumer and producer have defined a useful query
workflow; the Foundation has direct typed read methods.

## Identity and revisions

`MomentumIdentity` requires exact market (HK/US), symbol, trading date, input
contract ID/version, calculation version, calendar ID/version/content hash,
universe ID/version/content hash, and a score profile ID/version pair. Both score
profile fields null means NOT_SELECTED. One null and one non-null is invalid.
No production universe, score profile or calendar is invented or installed here.
Hashes are lowercase 64-character SHA-256 strings. Identity references are caller
assertions; this layer does not certify their upstream content or membership.

`logical_key` is SHA-256 of these exact identity fields serialized as sorted,
compact UTF-8 JSON. `revision` is SHA-256 of the complete canonical snapshot
payload excluding `stored_at`. `snapshot_id` is
`momentum-v1:<logical_key>:<revision>`.

The revision includes provenance, source revision/vintage, input references,
metric values/statuses, blockers/warnings, session and knowledge timestamps,
generation/availability timestamps, and schema version. Changed evidence or
results produce a new revision of the same logical calculation. A new generation
timestamp also represents a separate frozen artifact. References, warnings and
blockers are canonicalized as sorted sets; metric status entries are sorted by
metric name. Tuple-only nested containers and frozen models prevent mutation.
Equivalent timezone-aware instants normalize to UTC before hashing.

Same ID/payload saves are idempotent and retain the first `stored_at`. Different
revisions are appended, never overwritten. Payload disagreement for an existing
ID is an explicit conflict. SQLite primary key plus `(logical_key, revision)`
uniqueness and transactional inserts protect concurrent writers. A bounded exact
lookup index avoids a table scan; no UPDATE/delete method is exposed.

`to_dict()` includes derived snapshot ID, logical key and revision. Pydantic JSON
contains the underlying typed content; revalidation deterministically derives
the same identity. Reads revalidate the payload hash and exact query identity.

## Time and PIT

- `trading_date`: session date label, not information availability.
- `session_timestamp`: optional, semantically proven upstream session instant.
- `generated_at`: artifact generation instant.
- `available_at`: optional artifact availability, never inferred from candle time.
- `knowledge_cutoff`: optional bound on the inputs declared by a future producer.
- `stored_at`: assigned by the store's UTC clock on first insertion; caller values
  cannot backdate insertion and are excluded from identity.

All non-null timestamps must be timezone-aware and normalize to UTC. Naive
upstream datetimes are rejected; in particular SDK 5.2.0 historical candle naive
datetime must not be relabeled UTC. Unknown times remain null. Generation cannot
precede session/input cutoff; availability cannot precede generation. Future
generation/availability is rejected on save. Stored time cannot precede the
artifact. A source's historical availability is distinct from local storage time.

`pit_status=READY` requires explicit availability, knowledge cutoff, source
vintage and input references. These are structural checks, not independent
certification of vendor facts. Missing availability cannot claim PIT READY.
`overall_status` is explicitly supplied and never computed by min/max of metric
statuses. READY requires a known price basis and a READY PIT envelope. This
necessary validation is not a complete future Momentum Input Contract or a
readiness algorithm. A future producer must establish completed-session finality,
calendar coverage, provenance, price/volume comparability and per-metric rules.

## Evidence and metric quality

The envelope records source, provider, input references, adjustment method, price
basis, volume unit, source vintage and source revision. Null/UNKNOWN metadata is
allowed without manufactured defaults. Statuses are READY, PARTIAL, UNAVAILABLE,
BLOCKED; unknown semantics are represented by null/UNKNOWN metadata plus reasons.

All requested price, technical, volume, score/rank/tier and classification slots
are nullable. No slot is calculated. Metric status entries independently contain
metric name, status, blockers, warnings and evidence references. Non-null values
require an entry. READY requires a value, references and no blockers, plus known
price/volume basis where applicable. A disabled score profile prohibits score,
rank and tier values; it does not imply a score of zero. Unknown metrics and
duplicate status entries are rejected. Numeric slots reject NaN/infinity.

Returns/change percentages, volume, turnover, breakout definitions and scoring
units/algorithms are deliberately not interpreted by the Foundation; the exact
input contract and calculation version must define them before any producer
populates the fields. A fixture label is not a production contract.

## Strict reads

- `get_by_snapshot_id(id)` returns only that artifact or None.
- `query_exact(MomentumIdentity(...))` returns **all** revisions for that exact
  identity in deterministic snapshot-ID order, including blocked evidence.
- Optional aware `as_of` enforces `generated_at <= as_of`,
  `available_at <= as_of`, and actual `stored_at <= as_of`. SQL NULL availability
  is excluded. Returned records retain their original PIT/overall/metric statuses;
  visibility through a time filter does not itself prove strict PIT readiness.

There is no latest, earlier-date, fuzzy-version, alternative-universe/calendar,
score-profile or input-contract fallback. Multiple revisions stay explicit for a
consumer to select by exact ID; the store does not decide a winning revision.
Read-only SQLite connections do not create or modify stores. All SQL values are
bound parameters. Queries do not fetch quotes or inspect bars/runtime market state.

## Validation and unresolved dependencies

Fixture tests cover immutable round trips, deterministic identity, revision
changes, idempotency/concurrency, unknown metadata, independent metric states,
all exact identity dimensions, UTC normalization/naive rejection, temporal
visibility, corruption rejection and a non-creating empty store. These do not
constitute real Momentum data or producer validation.

Existing Longbridge findings remain unchanged: HK/US Daily reads proven;
volume/VR20 blocked; split-only basis blocked; corporate-action semantics unknown;
Daily finality partial; historical PIT/vintage blocked. Supplier confirmation is
pending. This layer does not bypass those limitations or write production samples.

MomentumSnapshot Foundation READY does **not** mean Momentum Input Contract READY,
Momentum Engine READY, or Momentum Ladder production READY. Next work is supplier
contract closure and an explicit input/producer design, not automatic computation.

No external GitHub reference was needed for this stage; existing project patterns
were used. No third-party code was copied.

### Acceptance evidence (2026-10-15)

- New Foundation targeted: 53 passed; related contracts/stores: 252 passed.
- Backend full: 3867 passed, 6 skipped, 1 xfailed, 214 warnings, 311.17 seconds.
  Sandbox execution first failed at collection because its temporary directory
  was inaccessible. The host run used normal threading and an isolated writable
  test directory. The known native/worker timing issue did not recur;
  `POLARS_MAX_THREADS=1` was not needed. No worker code changed.
- Ruff passed for both new Python files; no unrelated baseline cleanup.
- Sensitive scan and whitespace review passed; only the three planned files
  changed. No frontend changes, frontend suite or real production producer smoke.
