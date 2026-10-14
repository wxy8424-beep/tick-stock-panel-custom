# Benchmark Archive Trace Instrumentation v1

## Boundary

Implements only opt-in diagnostic instrumentation of existing quote/archive calls.
It does not repair benchmark requests, subscriptions, Dashboard bypass, archive
coverage or any acceptance rule. CN/US complete root causes remain PARTIAL until
naturally running regular-session evidence is collected. No real provider request
or production write is executed as acceptance of this stage.

The earlier [trace design](benchmark-archive-trace-contract-design-v1.md) remains the
baseline. Its implementation block described the previous non-invasion authorization
boundary; the user subsequently authorized minimal diagnostic injection for this stage.
No additional business behavior is authorized.

## Enablement and output

Before starting the normal application, explicitly set the non-secret process
environment variable `TSP_ARCHIVE_TRACE_SYMBOLS` to a comma-separated list, e.g.
`000001.SH,.SPX.US,AAPL.US`. This is a diagnostic filter, never a request list.
At import, only the first 32 entries are considered; invalid symbols and wildcard
strings do not enable tracing. Empty/unset means disabled. No .env change, new API,
file sink, provider, polling loop or automatic service restart is installed.

Records use the existing application logging configuration under
`app.services.archive_trace`, INFO, with `archive_trace` followed by structured JSON.
The bounded 1024-item diagnostic queue uses put_nowait; a daemon thread performs
logging. Overflow and sink failure drop diagnostics without changing business results.
The observer exposes a process-local dropped counter; it is not a durable coverage
ledger. Closing is bounded (two-second join), so shutdown can also lose diagnostics.
An unavailable/filtered INFO logger can produce no visible trace. Missing records
always remain UNKNOWN, including when logging is disabled or process shutdown intervenes.

No token, credential, environment dump, full response, price/volume payload or raw
exception is included. Only exact validated scoped symbols and allowlisted fields,
origins and reason codes are emitted. Scope may expose selected security symbols
in local logs, so enable only for the bounded observation window actually needed.

## Identity and call sites

One opaque request_id belongs to an actual outbound quote call; every observed
requested symbol has its own trace_id. New requests receive new identities.
No trace is retroactively assigned to historical rows or an unrequested benchmark.

- Longbridge get_realtime: REQUESTED, actual item receipt, existing normalization
  success/failure and explicit response omission/shape diagnostics.
- Longbridge dashboard_request quote method: request and receipt only. Its existing
  Dashboard bypass remains unchanged, identified as `dashboard_quote`.
- QuoteService uses context-local `quote_service_poll` or `quote_service_fetch`
  origins and emits QUOTESERVICE_ACCEPTED at the existing archive handoff.
- SnapshotWriter emits WRITER_ATTEMPTED on entry, existing refusal/prepare failures,
  and another WRITER_ATTEMPTED with ENQUEUED when the worker actually dequeues the
  batch. These are observations of one attempt, not two write attempts. The first
  record does not claim enqueue success; repeated stage records carry increasing
  causal sequence numbers. Worker-side acknowledgement avoids a producer/consumer
  race that could otherwise report enqueue acknowledgement after PERSISTED.
- PERSISTED is emitted only when the existing _write returns, after its transaction
  context has committed. No SQL statement or transaction boundary is changed.

provider_realtime is used for direct existing provider calls with no QuoteService
origin context. These origin labels refine the design's example vocabulary; they do
not pretend every Dashboard quote is specifically an index request.

## Out-of-band propagation

TraceRows is a list subclass; its business dictionaries are unchanged. Its sidecar
maps object identity to the original row reference and trace. Plain/untraced results
remain plain lists. No global symbol/time matching, latest-result cache or trace
field inside a quote dictionary is introduced.

Preparation keeps each trace alongside the exact accepted prepared row when that
row is appended, producing a TraceBatch list subclass. A filtered preceding record
cannot shift trace attribution to the next row. The existing writer queue transports
that list and sidecar across threads. SQLite receives the same tuples as before.
Commit references use batch identity, prepared-row ordinal and committed row count;
no SQLite ID is guessed from MAX(id), timestamps or lastrowid ranges.

## Stages, rejections and uncertainty

The seven stage names remain REQUESTED, PROVIDER_RECEIVED, NORMALIZED,
QUOTESERVICE_ACCEPTED, WRITER_ATTEMPTED, PERSISTED and REJECTED. Fields include identity,
UTC stage timestamp, causal sequence, source, status and safe reason code.
provider_quote_at is explicitly null in this instrumentation; diagnostics do not
add SDK timestamp inspection or invent a source event time.

Explicit rejections include an existing request exception, response omission/shape
failure, normalization failure, missing archive dependency, skipped invalid archive
symbol, closed/oversized writer batch, queue-full and preparation exception. They
retain the exact observed boundary; no generic exception becomes an entitlement,
session, freshness or instrument-type diagnosis.

An exception from _write leaves PERSISTED UNKNOWN. The existing generic write-failure
warning remains, but instrumentation does not assert rollback or absence of a committed
row when it cannot prove that outcome. Successful persistence followed by diagnostic
loss also remains UNKNOWN from trace alone. Missing WRITER_ATTEMPTED is never
converted into a writer rejection. Provider omissions are evidence about that
response, not proof the provider cannot support that symbol.

## Isolation and validation

No Anomaly Event, Evidence Policy, Market Context, Historical Context, Factor Snapshot,
provider selection, benchmark identity, quantity contract or archive schema changes.
No fake production data, backfill, benchmark wiring or new subscriptions. Diagnostic
failures are best effort; original archive returns/exceptions and queue decisions remain.

Tests use mocked SDK objects and isolated SQLite only. Coverage includes lifecycle,
per-request/per-symbol identity, exact row mapping after filtering, queue rejection,
post-commit persistence, missing-stage UNKNOWN, diagnostic loss/sink failure,
sanitized logging, Dashboard bypass, poll origin and unchanged prepared business values.
Fixture success is not real benchmark archive observation.

Acceptance on 2026-10-14: 25 new diagnostic tests; 166 affected tests passed across
archive_trace, snapshot_archive, Longbridge provider/realtime health/market state/health,
and US Dashboard tests. The initial default sandbox temp directory could not create
pytest directories (35 passed / 31 fixture setup errors); unchanged tests passed with
a separate writable test basetemp. No product change was made to fix that environment.
No full suite or frontend tests/build were run for this diagnostic-only scope.
Ruff passed for the new module/tests and modified provider/archive; QuoteService
had 44 HEAD diagnostics and the same 44 working-tree diagnostics, with zero new
code/message regressions (UTF-8 stdin comparison, preserving the repository path).
Sensitive-pattern, whitespace/binary and planned-file reviews passed; no runtime
DB, logs, credentials or temporary comparison files are included.

## References

Uses the prior design's review of OpenTelemetry's structured trace/log correlation
patterns ([logs data model](https://github.com/open-telemetry/opentelemetry-specification/blob/main/specification/logs/data-model.md),
[Apache-2.0 license](https://github.com/open-telemetry/opentelemetry-specification/blob/main/LICENSE)).
No OpenTelemetry dependency, exporter, collector, code copy or wire-compatibility
claim is introduced. No new broad GitHub research was needed for implementation.

## Next observation

Enable the explicit diagnostic scope in a normally launched service, observe CN/US
in their own regular sessions, and correlate exact trace/request/batch/item identities
with a naturally requested equity control. An unrequested CN benchmark or a Dashboard
only US benchmark should not be made to traverse missing stages. Report each observed
stage and UNKNOWN separately; inspect existing SQLite read-only. Root-cause reclassification
and any benchmark fix remain separate tasks.
