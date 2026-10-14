# Evidence Policy Foundation v1

This standalone module defines selection rules; it does not select/read evidence,
calculate metrics, resolve trading dates, generate snapshots or connect a consumer.
No production policy is installed. No event, API, provider, UI or existing database changes.

## Explicit definition

`EvidencePolicy` is frozen, JSON serializable and rejects unknown fields. Every field
must be supplied (including nullable `effective_to`). Nested collections are tuples.

- Identity: policy_id/version, ACTIVE or INACTIVE, aware effective_from/effective_to.
- Scope: one market, explicit finite symbol_scope and event_types. No wildcard.
- Time rules: event_time_source=window_end; knowledge_cutoff_source=detected_at;
  explicitly supplied trading_calendar identifier/version; snapshot_date_rule=
  previous_completed_trading_day. These are instructions, not computed dates.
- Factor selection when enabled: explicit definition_id, universe_id, normalization_version,
  nonempty required_factor_versions (name/version pairs). No latest/default definition.
- Historical permissions: allow_atr_display, allow_move_atr_ratio,
  require_price_scale_verified. Ratio permission requires ATR permission and scale verification.
- Market: benchmark_required, benchmark_selection_mode=
  existing_event_market_context_no_substitution.
- Requirements: disjoint required_evidence/optional_evidence subsets of
  historical, market, factors, with at least one evidence domain.

ACTIVE means eligible for matching, not that underlying evidence is READY. Immutable
INACTIVE definitions cannot be edited into ACTIVE: create a new version. Overlapping
ACTIVE versions deliberately conflict; there is no automatic newest-version preference.

## Store / resolver

Independent `data/user_data/evidence_policies.sqlite3`, composite primary key
(policy_id,version). Administrative save is append-only, identical saves are idempotent,
different content at the same identity raises an immutable version conflict.
get requires an exact version; list/get open SQLite read-only and never create a missing DB.
There is no update/delete API or migration of an existing database.

Resolver reads only symbol/market/event_type/detected_at from an event. It requires an
aware timestamp and consistent symbol market. Match criteria are ACTIVE, exact market,
explicit symbol and event membership, and `effective_from <= detected_at < effective_to`.
A null end has no upper bound. All timestamp comparisons use instants, not server-local dates.

- Zero matches: BLOCKED / no_matching_policy.
- More than one: BLOCKED / multiple_matching_policies, even across versions of one policy.
- Invalid event or unreadable/corrupt store: BLOCKED with a diagnostic.
- Exactly one: READY, policy_id/version and detached JSON selection_rules.

Resolver READY only means rules uniquely resolved. It does not mean evidence is READY,
PIT verified, market calendar available or source price scales compatible.

## Future consumer boundary

Future consumers must verify actual calendar/version, completed-day date, universe,
normalization/factor versions and source provenance. Snapshot available/generated/stored
times must not exceed detected_at. No older-date/latest-definition fallback is authorized.
An ATR display permission permits labeled retrospective context only when source PIT is
unverified; it never upgrades that evidence to event-time READY. Ratio permission does not
prove scale compatibility. Existing source_vintage_unverified and
event_baseline_price_scale_unverified blockers remain unchanged.

No factor snapshot/history/market-context reads occur here. A future integration still
needs explicit engine/registry compatibility and universe membership/version policy;
this foundation is not Anomaly Intelligence completion.

Tests use temporary databases and explicit isolated fixture policies, not production configuration.

## Factor branch selection (conditional contract)

The sole switch is membership of `factors` in required_evidence or optional_evidence.
There is no additional enabled boolean, no metadata-based inference and no change to policy
serialization. All fields remain explicit, even nullable ones.

- Disabled by policy: factors appears in neither selection list. definition_id/universe_id/
  normalization_version may be null, required_factor_versions may be empty. No dummy data needed.
- Enabled but unavailable: full valid configuration exists but no eligible snapshot is available.
- Enabled and blocked: missing/invalid configuration is rejected; Resolver reports BLOCKED for
  invalid persisted policies. Null/empty metadata never satisfies an enabled branch.

Existing complete enabled policies parse and serialize unchanged. Legacy unused metadata in a
disabled policy is preserved, not used to enable the factor branch. Execution requires empty
factor bindings when disabled; unused old bindings must be explicitly corrected through a new
immutable binding/policy version, never silently rewritten. Existing databases are not migrated.
