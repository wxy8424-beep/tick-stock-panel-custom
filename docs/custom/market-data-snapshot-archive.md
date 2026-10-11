# Market Data Snapshot Archive

## Scope and compatibility

Consumption-layer history for CN/HK/US realtime polling. The repository previously
had no SQLite store: this stage adds Python's standard-library SQLite under
`data/user_data/market_snapshots.sqlite3` (or the configured repository data root).
No dependencies, Provider code, capabilities, realtime records, Parquet schemas,
market routing, strategy calculations or frontend change. No trading interfaces.

QuoteService archives the original returned records before its CN/non-CN guards,
including CN records excluded from Longbridge's existing CN pipeline. Records
with an unrecognizable symbol are not archived. Explicit market conflicts retain
unknown quality; the archive market is the existing symbol resolver's result.
Rejected prices can remain in audit history without becoming live display data.

Only the existing QuoteService polling/refresh paths are captured. Independent
Dashboard/SDK requests outside that consumer do not create archive history.
No requests are added, no sampling or full-market guarantee is claimed.

## Recorded fields

| Field | Meaning |
| --- | --- |
| id | SQLite insertion order; pagination cursor |
| symbol / market / provider | Source and existing market identification |
| price | Consumed last_price, finite decimal text or null |
| volume / volume_unit | Value present in the consumed record, with its declared unit or unknown |
| quote_timestamp | Original standard Unix-ms numeric value, preserved as decimal text or null |
| receive_timestamp | UTC Unix milliseconds at the consumption boundary |
| quality_state / warnings | Existing validator result for this record at receipt |
| quality_observed_at / latency_ms | Validation clock and event age; not network RTT |
| market_session_state / market_session_diagnostic | Existing resolver result at receipt |
| provider_observed_at | Only a valid timezone-aware field explicitly supplied by the record; otherwise null |

Numeric text avoids converting Decimal through float. Missing or invalid numeric
values remain null, with diagnostic warnings rather than fabricated zeroes.
The volume is **not** guaranteed to be the SDK's original value: providers can
normalize before returning it. Longbridge returns no consumable volume at this
boundary: volume remains null, unknown quality is retained, and no units are
guessed or converted. No provider observation time is inferred from quote time,
market-level aggregate health, or the archive write time.

Quality is recomputed using the existing pure validator at consumption. It is not
a copy of Longbridge's per-market aggregate and is not a new filtering gate.
Provider raw-volume diagnostics unavailable at this boundary are not invented.
Quality/session are prepared before enqueue, not recomputed when disk writing is
delayed. Archive queries do not recalculate historic quality against today's clock.

## Persistence and failure boundaries

One atomic transaction per batch, additive table/index creation, parameterized SQL.
Connections close after every operation. A daemon writer performs disk IO outside
the quote polling thread: at most four pending batches, each up to 20,000 records.
Per-record validation still runs synchronously at receipt. Queue saturation,
oversized batches, disk errors and shutdown timeout produce sanitized warnings;
they do not stop the existing realtime chain or pretend a batch was archived.
There is no durable retry queue: failures/crashes can leave gaps in history.
Normal service stop drains accepted batches, with a bounded ten-second wait.

History persists across restarts; GET endpoints never create a missing database.
Older installations with no archive return empty rows. An existing SQLite file
without the archive table is preserved and can receive the additive table on its
first write. No migration of existing Parquet/JSON data is performed.

## Read-only queries

- `GET /api/intraday/snapshots/recent?symbol=AAPL.US&market=US&limit=100`
  returns the most recently inserted snapshot per symbol.
- `GET /api/intraday/snapshots/quality?symbol=AAPL.US&market=US&limit=100&before_id=123`
  returns historic snapshots and quality diagnostics in descending insertion order.

Filters are optional; limit is 1–1000 and market must be CN/HK/US. Responses use
`{rows, count}` and warnings are JSON arrays. The application retains its existing
authentication boundary. Queries open SQLite in read-only mode and never call a
provider. An unreadable/corrupt archive gives sanitized HTTP 503, not fabricated
empty success. Global latest-per-symbol queries may scan historical rows; use a
symbol filter for large archives. SQLite readers/writers have a one-second busy
timeout and transient contention is reported rather than retried indefinitely.

## Cleanup and backup

`SnapshotArchive.cleanup(before)` is an explicit internal operation using an aware
UTC cutoff; it deletes only this table's rows whose receive timestamp is earlier
than the cutoff. No automatic retention, DELETE API, file deletion or VACUUM is
introduced. Storage therefore grows with accepted batches; retention must be
chosen explicitly in a later task. Runtime SQLite files/journals are excluded from
Git with the existing data-directory rule. Git backs up code, not this history;
database backups require a separate authorized backup procedure.

## Verification (2026-10-11)

- Related targeted tests: 99 passed. After the cleanup cursor review fix, final
  archive tests: 17 passed (including insert/query/serialization/cleanup/rollback,
  queue overflow/failure isolation and read-only API compatibility).
- Final backend full: 2977 passed / 6 skipped / 0 failed; 216 existing warnings.
- Ruff: new module/tests clean; changed core files retain 55 baseline violations
  (56 at HEAD), with zero new violations. No unrelated lint cleanup.
- Real read-only quote smoke: 600519.SH / 700.HK / AAPL.US PASS through the actual
  consumption archival method and temporary SQLite write/query. All market states
  closed, volume null, quality unknown. No credential output or trading calls;
  existing user database files were not used for this smoke.
- Frontend not modified: tests/build NOT RUN. No new frontend archive page.
