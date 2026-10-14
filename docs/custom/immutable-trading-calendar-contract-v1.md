# Immutable Trading Calendar Contract v1

## Scope and audited behavior

This freezes existing calendar behavior, not new session coverage or a production policy.
`market_calendar.py` owns the single official date/source definition and now owns the
session parameters formerly embedded in `market_session.py`. The latter still applies
the existing clock/state algorithm. Historical providers read the same calendar dates.
No exchange_calendars dependency, external calendar substitution or copied code is used.

Audited semantic inputs are market, IANA timezone, coverage, trading weekdays, holidays,
additional trading days, regular windows, half-days, early-close, pre-open start,
post-market end, half-day post-market end, HK auction-window minutes, and the existing
US overnight-unverified date/time boundaries. Regular windows include both endpoints;
lunch is strictly between windows, and post-market boundaries are exclusive.
`cash-equity-clock-v1` pins the existing algorithm and state precedence, including
holiday-before-weekend classification and the US overnight unknown override. Runtime
provider signals are separate observations and never part of the frozen calendar.

CN regular windows remain 09:30–11:30 / 13:00–15:00; HK 09:30–12:00 / 13:00–16:00;
US 09:30–16:00. Half-days truncate the windows at the declared early-close; HK retains
its ten-minute closing-auction window, US retains post-market until 17:00 on half-days.
US regular-day pre-open/post-market retain 04:00 and 20:00 boundaries. The existing
2026-12-06 overnight uncertainty remains unknown before 04:00 / from 21:00; this is
not an overnight trading entitlement or a claim of verified overnight sessions.

## Identity and canonical serialization

`TradingCalendarContract` has stable `calendar_id`, explicit human-readable `version`,
and a SHA-256 `content_hash`. `last_updated != immutable version`.

`CalendarContent.canonical_json()` serializes all content except calendar_id/version/hash
using JSON sorted keys, compact separators, ASCII escaping, ISO dates and normalized
local times (HH:MM:SS, with fractional seconds if present). Set-like date lists, weekdays
and source references are sorted. Regular windows retain their validated chronological
order. Python repr, object addresses, insertion order and system clock are never inputs.
`freeze()` validates complete content before computing the hash; deserialization checks
the supplied hash rather than trusting it. Equal content under a different version has
the same content hash. Any content change must use a new version for the same calendar_id.

Provenance is explicit: official references, source_family, source_updated_on, effective
period and coverage. Provenance is included in the content hash: changing a reference or
its update date changes artifact identity even when session behavior is unchanged. The
source update date is evidence metadata, not a version selector. No generated-at clock
value is inserted into the artifact. IANA zone identifiers are frozen; replay also depends
on the installed timezone database and the versioned clock implementation, not an embedded
copy of timezone transition files. Unsupported market/timezone bindings are rejected.

## Single source and explicit freezing

Canonical definitions in `market_calendar.CALENDARS` carry stable IDs and `2026-v1`:

| Market | calendar_id | Timezone | Coverage | Half-day close |
| --- | --- | --- | --- | --- |
| CN | cn-cash-equity-official | Asia/Shanghai | 2026-01-01..2026-12-31 | none |
| US | us-cash-equity-official | America/New_York | 2026-01-01..2026-12-31 | 13:00 |
| HK | hk-cash-equity-official | Asia/Hong_Kong | 2026-01-01..2026-12-31 | 12:00 |

Reviewed 2026-v1 content hashes (also pinned by isolated regression tests):

```text
CN 62c1d558ab30fd3c171754ac17954614358a1d9c70ffb158b60fa4a54b8acc86
US cfb976ea41ff8037ab0dd5225f061dcb960976cd404bcd10eae2bb74a1084d76
HK 945fbd11e669fc27d1c76712969871a7151d854da1547f6c05fd71a4fa733b91
```

`TradingCalendarContract.from_canonical(market)` explicitly copies these definitions into
an immutable, validated artifact. It does not register or install anything. Holidays and
sessions are not manually duplicated in evidence_execution. The runtime clock and artifact
replay both use `get_calendar_session(calendar, now)`. Replay receives its artifact explicitly;
it never reads CALENDARS or cached provider status. Result metadata belongs to that artifact,
even if the runtime calendar changes. Factories may freeze the canonical definition only
explicitly; no resolver calls the factory as a missing-version fallback.

## Registry and execution

The existing in-memory registry revalidates artifacts on registration. Same ID/version/hash
is idempotent (including equivalent collection order); different content under an existing
ID/version raises immutable_calendar_version_conflict. No SQLite binding store is introduced.
PolicyExecutionBinding now requires calendar_content_hash alongside exact ID/version.
EvidenceExecutionResolver resolves all three and blocks unknown versions or hash mismatches;
there is no latest-version search. Factor identity strictness and policy scope are unchanged.

Previous-session queries require the expected hash and search strictly before the requested
local trading date inside exact coverage, using weekdays/holidays/additional sessions.
Half-days count as trading sessions. No earlier covered date or unknown version means BLOCKED.
Session replay also rejects dates outside coverage. Neither path reads bars, provider state
or an implicit current date. An event's evaluation date remains window_end converted using
the bound timezone; detected_at remains the knowledge cutoff. No anomaly event schema changes.

## Legacy treatment and validation

Legacy date-only calendar payloads and execution bindings without hash fail validation;
they are incomplete, not silently upgraded to production-grade artifacts. Fixtures explicitly
supply full sessions/provenance/hash. Existing policy payloads are unchanged and no runtime
records are rewritten. Production persistence/materialization is deferred.

Tests cover order-independent hashing, semantic/provenance changes, half-day set/time changes,
hash tampering, registry conflicts, explicit version/hash resolution, legacy rejection,
weekend/holiday/half-day previous sessions, timezone/DST/session regressions and independent
CN/US/HK replay with the current runtime calendar removed. Existing policy and Intelligence
tests use isolated stores; no production policy, quote, event or context is injected.

## Remaining boundaries

This closes the calendar-content representation blocker for future production policy
installation. It does not install CN/US/HK Evidence Policies, bootstrap runtime stores,
audit benchmark archives, enable Factor production, repair Historical PIT/price scale,
or implement News/AI/regulatory functionality. HK's benchmark blocker remains independent.
The limited 2026 coverage remains explicit; future years need a reviewed new artifact.
