# Evidence Execution Binding Foundation v1

Independent explicit registration only. No production bindings are installed. No Collector,
Intelligence, API, UI, database, provider, event, detector, Engine or Snapshot Builder changes.

## Calendar

TradingCalendarContract freezes calendar_id/version/market/timezone/source,
inclusive effective and coverage date periods, weekdays, holidays and explicit additional
trading days. All schedule data must be supplied; no implicit global-calendar reference.
The same ID/version cannot be replaced with different content; identical registration is idempotent.
Contracts are JSON serializable and deeply frozen. Registration does not authenticate sources.

resolve_previous_trading_day(market,calendar_id,version,date) searches strictly before the
requested date within frozen coverage. Weekends/holidays follow this exact contract, including
explicit extra trading days. Unknown ID/version, market mismatch, date outside coverage or
no previous date in coverage returns BLOCKED. No bars or runtime market states are consulted.
Coverage must be inside effective dates. An explicit calendar version is required even if the
global current calendar is available. No latest-version selection or automatic copying occurs.

## Factor identity

Namespace `market_factor_engine` refers exclusively to EngineFactorMetadata, not legacy
FactorSpec column IDs. registry_key is the exact canonical key; version is its positive integer
metadata version. parameters.period is explicit for every periodic family, including volatility.
Only MACD accepts explicit null (its existing fixed definition); its output component is required.

FactorRequest.definition is reused for parameter/output validation without Engine.compute.
`ma` plus period=5 binds exactly to `ma5`; `ma5` is not a registry key and cannot satisfy `ma`.
Case variants, unknown/future registry versions, null periodic defaults and wrong components fail.
Only registry versions supported by the installed metadata can bind; historical versions are not
silently interpreted using new defaults. Version drift fails closed.

## Policy execution

PolicyExecutionBinding pins the full frozen policy, exact policy_id/version, explicit calendar
ID/version, and factor identities. policy.required_factor_versions.name means the exact Engine
registry key, not an output column. Its version string must equal the canonical decimal integer
registry version (for example `1`, not `v1`). Calendar ID must equal policy.trading_calendar.
Factor requirement sets must match exactly and each family has one unambiguous binding.
The policy already pins definition_id/universe_id/normalization_version and all remaining rules.

EvidenceExecutionResolver requires explicit registration for the exact policy identity. Changed
policy content, missing calendar/version or unavailable registry version returns BLOCKED; one valid
binding returns READY plus frozen calendar/factor selection metadata. Conflicting registration
raises instead of replacing. No latest policy, default calendar or inferred definition is used.

READY means execution rules bound, not actual evidence found, source PIT certified or price scale
verified. Consumer evaluation date still needs event window_end in the bound timezone; factor
available/generated/stored times must be checked against detected_at in a future Collector.
Engine/registry build provenance and historical universe membership remain snapshot evidence
requirements; this layer does not certify them or rewrite existing historical blockers.

## Verification

Tests use isolated schedules and policies, never production data. Coverage includes immutability,
weekend/holiday previous dates, independence from the current calendar, unknown/missing binding,
exact factor parameter/component identity, policy conflicts and registry drift. No persistence
layer or consumer lifecycle is added in this phase.
