# Benchmark Archive Trace Contract Design v1

Historical design-stage document. The later user-authorized diagnostic-only implementation
and its stage acknowledgement details are described in
[Trace Instrumentation v1](benchmark-archive-trace-instrumentation-v1.md).
The implementation BLOCKED statements below refer to the earlier non-invasion boundary;
they do not authorize or describe a benchmark fix.

## Scope and readiness

Design only, reviewed 2026-10-14 against main commit
`591e63f922ecdfb3eb470a7f0908f60de8d83413`.
No instrumentation, logger, provider, QuoteService, writer, schema or runtime change
is implemented by this document. No new requests, subscriptions or archive writes.

**DESIGN COMPLETE — IMPLEMENTATION BLOCKED UNDER CURRENT BOUNDARY.**
Complete correlation requires diagnostic injection into existing production call sites
and propagation across the writer queue. There is no existing observer interface
covering these boundaries. This design does not authorize those modifications.
Changing business decisions remains prohibited even if instrumentation is later authorized.

CN `000001.SH` and US `.SPX.US` complete root causes remain **PARTIAL**.
The CN request-path gap and US Dashboard bypass of QuoteService are proven;
writer rejection, persistence failure and complete historical causality are not.
See [the preceding audit](benchmark-snapshot-archive-production-path-audit-v1.md).

## Existing evidence and its limits

| Layer | Existing evidence | Missing correlation |
| --- | --- | --- |
| Longbridge provider | market-level health, sanitized batch failures, aggregate parse rejection count | per-request and per-symbol successful boundaries |
| Quote callback | inspected application path uses synchronous `QuoteContext.quote`, not an SDK callback | do not invent a callback stage |
| Normalize | returned normalized records and aggregate parse diagnostics | a receipt-to-output identity |
| QuoteService | lifecycle, polling and generic archive warnings | request identity and writer acceptance result |
| SnapshotWriter | queue-full/closed/write-failure warnings | queued item identity and successful commit evidence |
| SnapshotArchive | row ID, symbol, provider, quote/receive times and quality/session metadata | request identity; no commit trace |

Current timestamps and symbol alone cannot reliably join concurrent, repeated or
cached requests. A read-only SQL row-count delta proves storage changed, not which
request caused it. Current health is not a historical per-request ledger.

## Trace identity

A trace represents **one symbol in one actual outbound quote request attempt**.
Repeated polling, manual refresh and Dashboard requests have different identities,
even when the same symbol and provider timestamp recur. No trace is reconstructed
for historical archive rows. A symbol never requested has no REQUESTED trace.

| Field | Contract |
| --- | --- |
| `trace_version` | fixed `benchmark-archive-trace/v1` |
| `trace_id` | fresh opaque random 128-bit ID; 32 lowercase hexadecimal characters; never derived from credentials, price or symbol |
| `request_id` | fresh opaque ID for one actual outbound SDK quote call; shared by its symbol traces |
| `symbol` | exact validated project symbol; no alias, benchmark substitution or wildcard |
| `market` | validated existing market identity CN/HK/US; preserve conflicts as diagnostic issues, do not remap quotes |
| `source` | provider identity, e.g. `longbridge`; not an endpoint URL or account identifier |
| `created_at` | UTC RFC3339 timestamp with explicit `Z`, captured when this request attempt is instrumented |
| `origin` | allowlisted `quote_service_poll`, `quote_service_refresh` or `dashboard_indices`; preserve the actual entry point |

Trace metadata travels out of band. It must not be inserted into SDK payloads,
normalized business record dictionaries or archive SQL columns. A multi-symbol
request creates distinct symbol traces under one request_id. Existing SDK retries
hidden from the application are UNKNOWN; do not invent attempt identities for them.
No extra provider request is allowed to obtain an identity or diagnostic result.

## Stage record: common mandatory fields

Each diagnostic record repeats the immutable identity above, plus:

| Field | Contract |
| --- | --- |
| `stage` | one of the seven fixed stages below |
| `stage_timestamp` | UTC RFC3339 `Z`; local observation of this boundary, not the provider quote time |
| `stage_sequence` | positive per-trace causal sequence, carried across threads; not inferred by sorting wall-clock timestamps |
| `status` | `PASS` for an observed successful boundary; `FAIL` only for explicit REJECTED evidence |
| `reason_code` | required allowlisted code; successful stage uses `none`; no free-text exception message |
| `rejected_at_stage` | null except REJECTED; identifies the attempted failing boundary from the six non-rejection stages |

`UNKNOWN` is a report/coverage result, not a fabricated stage occurrence. Never
emit a stage just to fill a missing sequence. A clock adjustment can reorder UTC
timestamps; stage_sequence preserves instrumented causal order within this trace.
If propagation is lost, leave the downstream join UNKNOWN instead of guessing.

## Fixed stage contract

| Stage | Exact evidence required | Additional required fields |
| --- | --- | --- |
| `REQUESTED` | instrumented symbol included in the arguments immediately before the real SDK quote call | `method=quote` |
| `PROVIDER_RECEIVED` | SDK call returned and a response item was actually associated with this exact requested symbol | `provider_quote_at` (UTC or null if unverified); no raw response |
| `NORMALIZED` | existing provider `_normalize` returned successfully for this item | `normalizer=longbridge_realtime`; no recalculation |
| `QUOTESERVICE_ACCEPTED` | existing `_archive_records` receives this normalized record with usable archive dependency, immediately before handing it to the writer | `consumer=quote_service_archive`; does not mean downstream CN/cache eligibility |
| `WRITER_ATTEMPTED` | existing `SnapshotWriter.submit` was entered for this record | `queue_outcome=ENQUEUED/REJECTED/UNKNOWN`; `writer_batch_id` when enqueued |
| `PERSISTED` | existing SQLite transaction context exited successfully, committing this exact prepared record | `writer_batch_id`, `persistence_reference` described below |
| `REJECTED` | an existing boundary explicitly refused, dropped or failed this item/request; evidence must be observed | non-`none` `reason_code`, `rejected_at_stage`; batch reference when known |

WRITER_ATTEMPTED is not a queue acknowledgement or a disk-write success.
ENQUEUED only means accepted by the existing queue; it does not imply PERSISTED.
If the queue decision is known at return, the stage record can be emitted then,
retaining the entry timestamp. Abrupt termination may leave this stage missing.
`UNKNOWN` queue outcome must not be promoted to ENQUEUED.

The existing Dashboard-specific output mapping is not the provider `_normalize`.
A Dashboard-only request may show REQUESTED and PROVIDER_RECEIVED without NORMALIZED,
QUOTESERVICE_ACCEPTED or WRITER_ATTEMPTED. Do not forward it into archive to complete
a trace. Missing downstream stages alone do not prove rejection.

Provider response empty/missing a symbol is not an observed item receipt. Keep
PROVIDER_RECEIVED UNKNOWN; an explicit omission diagnostic can use REJECTED with
`response_symbol_missing`. Unknown response item identity cannot be assigned to an
arbitrary requested symbol. Do not log an unvalidated returned symbol/payload.

### Safe reason codes

Proposed initial allowlist, emitted only where the corresponding existing outcome
is observed: `none`, `request_failed_unclassified`, `response_symbol_missing`,
`response_shape_invalid`, `normalization_failed`, `archive_dependency_missing`,
`archive_symbol_invalid`, `writer_closed_or_batch_limit`, `queue_full`,
`prepare_failed`, `persistence_failed_unclassified`.

These codes describe diagnostic observations, not new gates. Do not classify a
generic error as permission, entitlement, stale, session or instrument rejection
without explicit existing evidence. Retain the current combined closed/batch-limit
reason if it cannot be distinguished safely. Unknown classification stays unclassified.
Queue rejection points to WRITER_ATTEMPTED; transaction failure points to PERSISTED.
An exception is not proof that a transaction could not have committed if the
observation cannot determine the outcome; that ambiguous result remains UNKNOWN.

## Queue and transaction correlation

The current queue carries only prepared tuple rows. A future implementation would
need a diagnostic-only envelope associating each prepared item with its trace ID,
and one opaque `writer_batch_id`. Trace propagation must survive the worker-thread
handoff explicitly; thread-local/context-local state alone is insufficient.

Preparation can skip invalid records. Never align trace IDs to prepared rows by
blindly zipping input and output positions. Any mapping must be established at the
existing per-record preparation boundary without changing its result or ordering.
If exact correspondence cannot be established, PERSISTED attribution is BLOCKED.

`persistence_reference` consists of `writer_batch_id` plus the exact prepared-row
ordinal and total committed row count. A SQL row ID is optional only if available
without changing existing INSERT behavior. Never infer row IDs from MAX(id),
lastrowid ranges, timestamps or a later symbol query. This reference proves the
instrumented transaction association; it does not retrofit trace IDs into SQLite.

PERSISTED must be emitted **after** the transaction context has successfully exited,
not after executemany but before commit. A lost diagnostic after a successful commit
is possible: absence of PERSISTED remains UNKNOWN even if a row exists. No atomic
trace/business transaction, trace DB, SQL trigger or transactional outbox is proposed.

## UNKNOWN and causal conclusions

| Observation | Permitted conclusion |
| --- | --- |
| no trace at all | UNKNOWN; request may not have occurred, instrumentation may be off or records may be lost |
| REQUESTED but no receipt | provider outcome UNKNOWN unless an explicit failure record exists |
| normalized but no WRITER_ATTEMPTED | archive handoff UNKNOWN; not a writer rejection |
| ENQUEUED but no PERSISTED | persistence UNKNOWN; not proof of write failure |
| explicit REJECTED queue_full | this observed enqueue was rejected; no general claim about other requests |
| matched committed-item PERSISTED | this item was committed by this transaction; no claim about downstream Market Context usability |
| zero archive rows | observed storage coverage only; no inferred rejection reason |

REJECTED at one boundary does not fabricate successful earlier stages. Trace results
only apply to the observed attempt, not every historical zero-row interval.
No benchmark request is added merely to make REQUESTED appear.

## Future integration boundaries — not implemented

| Boundary | Current call site at reviewed baseline | Minimal diagnostic purpose |
| --- | --- | --- |
| request | `plugins/longbridge/provider.py:get_realtime`, around `context.quote(chunk)` | assign IDs to actual requested members; capture returned items |
| Dashboard request | `provider.py:dashboard_request`, quote method only; origin supplied at Dashboard call boundary | distinguish natural Dashboard requests from polling; retain bypass |
| normalize | `provider.py:get_realtime` around `_normalize(quote)` | record existing successful result or existing parse failure |
| QuoteService | `services/quote_service.py:_archive_records` | observe archive dependency/handoff without changing routing |
| prepare/queue | `services/snapshot_archive.py:SnapshotWriter.submit` and `SnapshotArchive.prepare` | preserve item mapping, enqueue outcome and batch identity |
| transaction | `snapshot_archive.py:SnapshotWriter._run` / `SnapshotArchive._write` | carry batch identity; emit only after successful commit |

These are **production-path diagnostic injection points**, not existing hooks.
L1 configuration/L2 extensions cannot currently provide exact correlation here;
implementation would require narrowly scoped L3 instrumentation. Authorization and
review are separate future work. No monkey-patching, global profiler, function wrapper
or external log handler is presented as a non-invasive equivalent.

## Diagnostic isolation and prohibited information

Future instrumentation must be opt-in, narrowly scoped to explicit observation
symbols/origins and bounded in memory/output. This diagnostic symbol selection
must never change provider request membership. Use non-blocking best-effort emission;
sink failure/drop cannot affect quote return values, queue decisions, transactions,
exceptions, retries, worker lifecycle or business delivery. Diagnostic loss means
UNKNOWN. Sink, retention and enablement configuration are not implemented here.

Never record tokens, credentials, cookies, authorization headers, account IDs,
signed URLs/private endpoint credentials, environment/configuration dumps, full
provider responses, quote payloads, raw exception strings/tracebacks/locals or
serialized SDK objects. Whitelist fields before emission; do not rely on post-log
redaction. Symbols are narrowly scoped diagnostic metadata, not permission to dump
watchlists or all subscriptions. No price/volume fields are required by this contract.

Do not modify Anomaly Event, Market Context, Historical Context, Evidence Policy,
calendar, benchmark identity, provider contract, normalized business schema, archive
schema, gates, quantity semantics, anomaly rules or thresholds. No new provider,
subscription, network request, backfill, fake row, event or evidence is authorized.

## Future regular-session acceptance plan

1. Record actual session, immutable application revision, instrumentation scope and
   diagnostic coverage/loss. Observe only an already naturally running service.
2. Observe CN `000001.SH` and US `.SPX.US` in their respective regular sessions;
   use a naturally requested real equity such as AAPL.US as a same-window control.
3. Join by exact request_id/trace_id through the writer batch/item reference.
   Mark each stage PASS, explicit FAIL or UNKNOWN; show origin and bypass separately.
4. Compare read-only SQLite coverage before/after. Do not treat coincident row counts
   as an exact join. Keep trace commit evidence separate from downstream usability.
5. No requests or unavailable services: report observation BLOCKED/UNKNOWN. No fake
   quote or manual request is permitted to manufacture a complete natural trace.

Future diagnostic affected tests should verify exact batch/symbol identity, filtered
row mapping, thread handoff, enqueue versus commit, transaction failure, diagnostic
loss, safe field allowlisting and unchanged business outputs/gates. This document
does not claim those tests or regular-session traces have been executed.

## GitHub architectural references

Viewed 2026-10-14; these are moving-branch design references, not dependencies or
financial authorities. No source extraction or implementation is based on them.

| Repository / license | Borrowed idea | Not adopted |
| --- | --- | --- |
| [OpenTelemetry specification](https://github.com/open-telemetry/opentelemetry-specification), [Apache-2.0 license](https://github.com/open-telemetry/opentelemetry-specification/blob/main/LICENSE) | explicit trace identity, structured fields and distinction between occurrence and observation time from its [logs data model](https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/logs/data-model.md) | SDK, collector, exporter, full span model or claim of OpenTelemetry wire compatibility |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader), [LGPL v3 license text](https://github.com/nautechsystems/nautilus_trader/blob/develop/LICENSE) | modular data adapters and explicit event/message-flow boundaries described in its README | trading engine, message bus, provider adapters, framework, dependencies or any financial assumptions |

**Code copied: NO.** No wholesale code copy, implementation excerpt or new package.
The local stage vocabulary and statuses above are a project design proposal, not
claims that either reference implements this contract.

## Result

Only this design document is added. No logger, runtime probe, business-path patch,
test/build execution, stage observation, commit or push is part of this stage.
Complete instrumentation remains BLOCKED by the current non-invasion boundary;
benchmark archive root causes remain PARTIAL pending real correlated evidence.
