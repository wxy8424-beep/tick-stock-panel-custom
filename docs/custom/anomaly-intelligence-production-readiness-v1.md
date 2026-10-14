# Anomaly Intelligence Production Policies v1

## Scope and canonical configuration

Canonical manifest and installer:
`backend/app/services/anomaly_intelligence_production.py`.
PRODUCTION_REFERENCES is an immutable tuple of frozen references. production_bindings()
builds frozen policies and exact execution bindings using the existing schemas. It copies
no calendar facts: TradingCalendarContract.from_canonical() supplies the single-source
artifact, whose ID/version/hash must equal the explicit manifest reference.

| Market | policy_id | Version | Scope | Required | Optional | Factor |
| --- | --- | --- | --- | --- | --- | --- |
| CN | anomaly-intelligence-cn | v1 | MARKET_WIDE | market | historical | NOT_SELECTED |
| US | anomaly-intelligence-us | v1 | MARKET_WIDE | market | historical | NOT_SELECTED |
| HK | NOT INSTALLED | — | — | — | — | — |

Market Context is required because relative-to-market evidence is a core v1 capability.
Historical Context is supplementary: source-level PIT and realtime/baseline price-scale
compatibility remain unproven. It may supply labeled retrospective PARTIAL evidence.
Factor is explicitly not selected because no production Factor Snapshot producer exists;
that missing producer is not a requirement of these policies.

Both policies explicitly list the current AnomalyEvent schema's rapid_price_move,
intraday_breakout and volatility_expansion. Schema membership does not activate a detector
rule or claim that volatility-expansion production triggering is supported. Detector,
threshold, severity, episode, deduplication and original event schema are unchanged.

## Effective periods and exact calendar references

Both policies cover the half-open interval [2026-01-01 00:00, 2027-01-01 00:00) in their
market timezone: Asia/Shanghai for CN, America/New_York for US. The exclusive end midnight
is the boundary after the final covered date, not an included 2027 trading date.
Bootstrap checks these instants against the exact artifact's coverage boundaries.
Policy matching continues to use detected_at; this does not change event window_end or
the existing completed-history and factor time-cutoff contracts.

```text
CN calendar_id: cn-cash-equity-official
version: 2026-v1
content_hash: 62c1d558ab30fd3c171754ac17954614358a1d9c70ffb158b60fa4a54b8acc86
coverage: 2026-01-01 .. 2026-12-31
effective_from: 2026-01-01T00:00:00+08:00
effective_to (exclusive): 2027-01-01T00:00:00+08:00

US calendar_id: us-cash-equity-official
version: 2026-v1
content_hash: cfb976ea41ff8037ab0dd5225f061dcb960976cd404bcd10eae2bb74a1084d76
coverage: 2026-01-01 .. 2026-12-31
effective_from: 2026-01-01T00:00:00-05:00
effective_to (exclusive): 2027-01-01T00:00:00-05:00
```

No latest/current lookup or alternate version/hash is selected. HK calendar readiness
does not close HK's missing Market Context benchmark contract: no HK policy is installed.

## Startup and persistence

Normal backend _application_lifespan creates DataStore, then calls
bootstrap_production_evidence(store.data_dir) before Repository/data/quote/enrichment workers.
The returned EvidenceExecutionResolver is saved in app.state.intelligence_execution and
injected through AnomalyWorker into AnomalyIntelligenceWorker's existing collector.
Aggregation remains independent of quote callbacks and anomaly delivery. No per-event
installation, second provider, second policy database or SQLite binding store is introduced.

Bootstrap validates both manifest bindings and registers exact calendars/execution rules in
the existing in-memory registries. It preflights stored policy identity conflicts before
writes, then calls EvidencePolicyStore.save for the two policies. The existing independent
user_data/evidence_policies.sqlite3 is runtime data and Git ignored. Registries are rebuilt
and verified from source on startup; full calendar facts are not duplicated in the manifest.

Repeated installation of equal policy content is a no-op and preserves stored payloads.
Same policy_id/version with different content, calendar hash/version mismatch, or registry
conflict raises an explicit startup error; it is outside the worker's best-effort catch.
The app does not silently start with empty/default bindings. Old records are never deleted,
overwritten or migrated, and no latest policy is selected. Multiple applicable policies
remain multiple_matching_policies/BLOCKED; specific scope has no precedence over MARKET_WIDE.
The two saves use the existing Store's transactions, not a new cross-record migration.

## Evidence and overall states

Factor metadata is null and factor versions/execution identities are empty. factors appears
in neither selection list. The collector does not query Factor Snapshot and emits NOT_SELECTED,
with null score and no factor_missing/factor_snapshot_unavailable blocker.

Historical ATR display is allowed under existing retrospective/PIT rules. move_atr_ratio is
allowed only when the existing verified-price-scale gate permits it; otherwise it stays null
and the original blocker is retained. No ATR, market context or factor is recalculated here.

Overall status uses the unchanged existing aggregation algorithm. In particular:

| Market | Historical | Factor | Overall |
| --- | --- | --- | --- |
| READY | READY | NOT_SELECTED | READY |
| READY | PARTIAL | NOT_SELECTED | PARTIAL |
| UNAVAILABLE | PARTIAL | NOT_SELECTED | PARTIAL |
| UNAVAILABLE | UNAVAILABLE | NOT_SELECTED | UNAVAILABLE |
| BLOCKED (required) | any | NOT_SELECTED | BLOCKED |

Required market UNAVAILABLE is not converted into a required-evidence contract BLOCKED:
PARTIAL can expose remaining historical evidence with the market blocker. This is the
existing algorithm, not a lowered requirement or a claim of complete market intelligence.
Missing runtime evidence is not a startup configuration failure.

The first Intelligence record remains frozen. generated_at describes the first aggregation's
available evidence; later-arriving context does not silently upgrade the record. Installing
these policies does not rewrite already-frozen records, run a refresh or create any events.

## Validation

Isolated fixture tests cover CN/US production policy shapes, exact calendar bindings,
time boundaries, idempotency, no-overwrite/conflicts, lifecycle ordering/injection and
CN/US aggregation with factor reads explicitly forbidden. Existing SYMBOLS policies,
enabled factor strictness, execution identities and immutable calendar tests remain intact.

Real configuration validation (2026-10-14) invoked the same production bootstrap used by
startup against the normal project data directory. Policies before: 0; after: 2. Both CN/US
resolved uniquely with MARKET_WIDE, market required, historical optional, factor NOT_SELECTED
and the exact ID/version/hash above. HK returned no_matching_policy. The second bootstrap
preserved all stored policy payloads exactly and produced identical execution bindings.
This validates real installed configuration, not a real anomaly aggregation or a running
quote service. Resolver matching inputs were not persisted as events.

Read-only counts from existing stores:

| Observation | Actual rows |
| --- | --- |
| CN benchmark 000001.SH | 0 |
| US benchmark .SPX.US | 0 |
| Anomaly events | 0 |

REAL ANOMALY VALIDATION: UNAVAILABLE — NO EXISTING EVENTS.
No quote, anomaly, historical/market context or Factor Snapshot was injected into production.
Only the authorized policy store was materialized. Archive path diagnosis/repair was not run.
Fixture events/context remain isolated from production storage.

Backend targeted: 191 passed. Normal full: 3590 passed / 6 skipped (217 existing warnings).
The worker timing open-loop did not reproduce; controlled POLARS_MAX_THREADS=1 full was
not needed. No frontend code changed and no frontend suite was run.

Ruff regression comparison uses HEAD's app/main.py through git show and Ruff stdin with
the same filename/config context. HEAD and working tree each have 27 identical diagnostics:
E402=3, F811=2, I001=4, RUF003=2, RUF100=16. Matching uses code/message/source line to account
for shifted line numbers. New regressions: 0. Historical lint debt is intentionally retained.

## Deferred work

Benchmark archive root-cause investigation/repair, quote subscriptions, Factor Producer,
Historical PIT/price-scale repair, late refresh, regulatory rules, News and AI Explanation
are not part of this change. No new GitHub reference or external framework was needed.
