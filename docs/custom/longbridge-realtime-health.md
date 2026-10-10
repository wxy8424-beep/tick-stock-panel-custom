# Longbridge realtime health

2026-10-10; SDK 5.2.0; baseline 551994a. No new datasets are enabled.

## Actual architecture and lifecycle

The provider uses `QuoteContext.quote()` snapshots, batches <=500, deduplicated
symbols, one lazy reused context per provider, serialized by its existing lock.
There are no subscriptions or callbacks in this adapter. Subscription failures,
unsubscribe and callback registration are therefore not applicable; parser row
isolation and duplicate-request tests protect the equivalent snapshot boundary.
Malformed response containers are rejected safely; invalid rows cannot discard
other valid rows. Metadata failure does not invalidate a valid price receipt.

Official SDK v5.2.0 [Rust quote core](https://github.com/longbridge/openapi/blob/v5.2.0/rust/src/quote/core.rs)
owns reconnection, including its 2s retry delay, session restoration and resubscribe.
The project adds no retry/reconnect loop and performs at most one request per batch
per invocation. A later normal polling invocation may try again. Python's installed
public interface exposes no reliable connection/reconnecting observer; health
reports `connection_state=unknown`, `reconnect_state=unobservable` rather than
pretending that a request error proves reconnecting. No callback or subscription
is introduced, and no project thread/task is created by the provider.

`close()` drops the final owned SDK context references, metadata and health under
locks; SDK 5.2.0 has no public `close()`. SDK core shutdown stops reconnecting when
the owning context is dropped. Registry reload already calls provider close;
application shutdown now closes Longbridge after quote consumers stop. Stopping
only the quote poller leaves the registry-owned context reusable by Dashboard
requests; that is intentional, not a second live polling worker.

## Authority and time contract

`market_capabilities` remains the only capability authority: CN/HK/US realtime
supported; quantity blockers and financial statuses remain unchanged. Runtime
health never changes datasets or capability declarations, and never gates the
existing CN/non-CN routing. `usable` is only the diagnostic display value.

Per market, memory stores the latest **valid normalized quote** receipt:
these observations cover `get_realtime()` / `get_realtime_for_markets()` callers
(including US universe batches). Raw Dashboard auxiliary requests are not this
dataset's reception signals; a Dashboard response alone does not fabricate a
successful realtime-pipeline observation.

- `last_event_at`: normalized SDK `datetime` event time, retaining the existing
  timestamp inverse conversion; no integer timestamp-unit guess.
- `last_received_at`: local UTC time immediately after the quote response, before
  optional metadata requests. Repeated valid snapshots advance it even if the
  underlying event time remains old. It measures process reception, not trade
  activity, full-market coverage or proof of non-delayed exchange entitlement.
- `evaluated_at`: one injected UTC clock value for health evaluation.
- `last_checked`: last explicit snapshot attempt; empty/error responses do not
  refresh `last_received_at`.

## Freshness and sessions

Reuse `app.market_session.get_market_session` without network probing. Its regular
window is a weekday clock model, **not a confirmed trading/holiday calendar**.
`market_state` and `calendar_status` preserve that distinction. All markets use
one centralized 120s threshold (several ordinary 30s polling cycles). Age >120s
in a regular clock window means `stale`; <=120s means `healthy`. Closed, break
and pre-open windows do not require new snapshots: retained receipts show
`market_closed`, not stale. No receipt means `no_data`; unknown session state or
backward clock means `unknown`, never healthy. Threshold/session authority stays
entirely in backend. Long-running full-universe sweeps can legitimately exceed
this threshold; it is diagnostic, not a reason to change routing or discard data.

## Failure scope and safe reasons

All batches are aggregated before recording each requested market. Successful
rows win over failed batches for the same market. A missing/bad symbol or later
failed single-symbol request cannot erase another valid receipt. With retained
data the ordinary freshness rule continues, while `last_error_code` independently
records the safe reason. A never-successful failed requested market is unavailable;
other markets remain independent. This is requested-market reception health, not
a claim that every security in the market is unavailable/covered.

Context initialization failure reports `context_unavailable`; no-data reports
`realtime_no_data`; active delayed reception reports `realtime_stale`; good recent
reception reports `realtime_healthy`; unknown sessions report `market_state_unknown`.
Request errors are whitelisted `realtime_authentication_failed`,
`realtime_permission_denied`, `realtime_symbol_error`, `realtime_network_error`,
`realtime_parse_error`, `realtime_sdk_error`. Raw SDK errors, credentials, account
details and response objects never enter health. No new runtime storage is written.

## API and UI

Reuse existing settings data-sources `provider_health`; no new endpoint. Added
runtime fields are optional for other capabilities/providers, typed in the
frontend. Old availability/code/message/last_checked/symbol fields remain.
The settings component displays backend contract labels, runtime message and UTC
receipt time. It never computes stale from `Date.now`, guesses a session, or calls
SDK on page open. A reconnecting message can be rendered if supplied by a future
verified observer; this provider intentionally does not manufacture it today.

## Future work

Authoritative holiday/session calendars, observable SDK connection events, and
symbol-level entitlement/coverage summaries require separately verified contracts.
No daily/minute/depth/financial unlock, unit conversion or trading API is included.

## Verification (2026-10-10)

- Final targeted backend: 116 passed, including 18 new realtime health cases.
- Final full backend: 2838 passed / 6 skipped / 0 failed. One intermediate run
  hit the unchanged Windows optimizer worker exitcode 3221225477; standalone
  verification passed and the final full rerun passed. No backtest changes.
- Settings/provider frontend: 21 passed (8 new); TypeScript/production build PASS.
  Existing bundle-size warning remains. ESLint unavailable in project, not installed.
- Modified plugin/test Python Ruff PASS; main.py historical 27 violations exactly
  match HEAD, with zero added violations. Loader historical lint remains untouched.
- Real read-only two-round quote smoke: CN 600519.SH, HK 700.HK, US AAPL.US all
  returned valid snapshots and advancing receipt times; all three markets closed
  at evaluation, correctly not marked stale. Context/health cleanup PASS.
- Candidate sensitive check: 10 files, three locally matched credential values,
  zero violations; no credentials or raw errors are recorded in this document.
