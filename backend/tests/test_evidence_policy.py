"""Isolated policies are fixtures, not active production evidence configuration."""
import json
import sqlite3
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.services.evidence_policy import EvidencePolicy, EvidencePolicyResolver, EvidencePolicyStore


def policy(**changes):
    values = {
        "policy_id": "fixture-policy", "version": "v1", "status": "ACTIVE",
        "effective_from": "2026-10-01T00:00:00Z", "effective_to": "2026-11-01T00:00:00Z",
        "market": "US", "symbol_scope": ["AAPL.US"], "event_types": ["rapid_price_move"],
        "event_time_source": "window_end", "knowledge_cutoff_source": "detected_at",
        "trading_calendar": "fixture-calendar-v1", "definition_id": "fixture-definition",
        "universe_id": "fixture-universe", "snapshot_date_rule": "previous_completed_trading_day",
        "normalization_version": "fixture-rank-v1",
        "required_factor_versions": [{"name": "ma", "version": "1"}],
        "allow_atr_display": True, "allow_move_atr_ratio": False, "require_price_scale_verified": True,
        "benchmark_required": False,
        "benchmark_selection_mode": "existing_event_market_context_no_substitution",
        "required_evidence": ["factors"], "optional_evidence": ["historical", "market"],
    }
    return EvidencePolicy.model_validate(values | changes)


def event(**changes):
    return {"symbol": "AAPL.US", "market": "US", "event_type": "rapid_price_move",
            "detected_at": "2026-10-14T15:00:00Z", "evidence": {"unchanged": True}} | changes


def disabled_policy(**changes):
    return policy(**({"required_evidence": ["historical", "market"], "optional_evidence": [],
        "definition_id": None, "universe_id": None, "normalization_version": None,
        "required_factor_versions": []} | changes))


def test_legacy_list_defaults_to_symbols():
    raw = policy().to_dict()
    raw.pop("scope_type")
    restored = EvidencePolicy.model_validate(raw)
    assert restored.scope_type == "SYMBOLS"
    assert restored.symbol_scope == ("AAPL.US",)


@pytest.mark.parametrize("scope,symbol,expected", [
    ("SYMBOLS", "AAPL.US", "READY"),
    ("SYMBOLS", "NVDA.US", "BLOCKED"),
    ("MARKET_WIDE", "AAPL.US", "READY"),
    ("MARKET_WIDE", "NVDA.US", "READY"),
    ("MARKET_WIDE", "NOT-IN-A-CATALOG.US", "READY"),
])
def test_scope_membership_without_provider_or_catalog(tmp_path, scope, symbol, expected):
    store = EvidencePolicyStore(tmp_path)
    store.save(policy(scope_type=scope, symbol_scope=[] if scope == "MARKET_WIDE" else ["AAPL.US"]))
    assert EvidencePolicyResolver(store).resolve(event(symbol=symbol))["status"] == expected


@pytest.mark.parametrize("market,symbol", [("CN", "600519.SH"), ("HK", "700.HK")])
def test_market_wide_does_not_cross_markets(tmp_path, market, symbol):
    store = EvidencePolicyStore(tmp_path)
    store.save(policy(scope_type="MARKET_WIDE", symbol_scope=[]))
    assert EvidencePolicyResolver(store).resolve(event(market=market, symbol=symbol))["blocker"] == "no_matching_policy"


def test_cn_market_wide_is_bound_to_declared_event_market(tmp_path):
    store = EvidencePolicyStore(tmp_path)
    store.save(policy(market="CN", scope_type="MARKET_WIDE", symbol_scope=[]))
    resolver = EvidencePolicyResolver(store)
    assert resolver.resolve(event(market="CN", symbol="000002.SZ"))["status"] == "READY"
    assert resolver.resolve(event())["blocker"] == "no_matching_policy"
    assert resolver.resolve(event(market="HK", symbol="700.HK"))["blocker"] == "no_matching_policy"
    assert resolver.resolve(event(market="CN", symbol="AAPL.US"))["blocker"] == "event_market_conflict"


def test_overlapping_market_wide_versions_still_conflict(tmp_path):
    store = EvidencePolicyStore(tmp_path)
    store.save(policy(scope_type="MARKET_WIDE", symbol_scope=[]))
    store.save(policy(version="v2", scope_type="MARKET_WIDE", symbol_scope=[]))
    assert EvidencePolicyResolver(store).resolve(event())["blocker"] == "multiple_matching_policies"


@pytest.mark.parametrize("changes", [
    {"symbol_scope": []}, {"symbol_scope": None}, {"symbol_scope": ["*"]},
    {"scope_type": None, "symbol_scope": []},
    {"scope_type": "SYMBOLS", "symbol_scope": []},
    {"scope_type": "MARKET_WIDE", "symbol_scope": ["AAPL.US"]},
    {"scope_type": "MARKET_WIDE", "symbol_scope": ["*"]},
    {"scope_type": "MARKET_WIDE", "symbol_scope": None},
])
def test_scope_never_inferred_or_ambiguous(changes):
    with pytest.raises(ValidationError):
        policy(**changes)


def test_market_wide_requires_explicit_empty_list():
    raw = policy(scope_type="MARKET_WIDE", symbol_scope=[]).to_dict()
    raw.pop("symbol_scope")
    with pytest.raises(ValidationError):
        EvidencePolicy.model_validate(raw)


def test_market_wide_and_symbols_overlap_has_no_precedence(tmp_path):
    store = EvidencePolicyStore(tmp_path)
    store.save(policy())
    store.save(policy(policy_id="market-policy", scope_type="MARKET_WIDE", symbol_scope=[]))
    resolver = EvidencePolicyResolver(store)
    assert resolver.resolve(event())["blocker"] == "multiple_matching_policies"
    assert resolver.resolve(event(symbol="NVDA.US"))["policy_id"] == "market-policy"


@pytest.mark.parametrize("timestamp,expected", [
    ("2026-09-30T23:59:59Z", "BLOCKED"), ("2026-10-01T00:00:00Z", "READY"),
    ("2026-11-01T00:00:00Z", "BLOCKED"),
])
def test_market_wide_preserves_effective_period(tmp_path, timestamp, expected):
    store = EvidencePolicyStore(tmp_path)
    store.save(policy(scope_type="MARKET_WIDE", symbol_scope=[]))
    assert EvidencePolicyResolver(store).resolve(event(detected_at=timestamp))["status"] == expected


def test_legacy_persistence_read_is_not_rewritten_and_scope_is_immutable(tmp_path):
    store = EvidencePolicyStore(tmp_path)
    raw = policy().to_dict()
    raw.pop("scope_type")
    payload = json.dumps(raw)
    store.path.parent.mkdir(parents=True)
    with sqlite3.connect(store.path) as db:
        db.execute("CREATE TABLE policies (policy_id TEXT, version TEXT, payload TEXT, PRIMARY KEY(policy_id,version))")
        db.execute("INSERT INTO policies VALUES (?,?,?)", (raw["policy_id"], raw["version"], payload))
    assert store.get(raw["policy_id"], raw["version"]).scope_type == "SYMBOLS"
    assert EvidencePolicyResolver(store).resolve(event(symbol="NVDA.US"))["status"] == "BLOCKED"
    store.save(policy())  # Equal legacy meaning remains idempotent, without migration.
    with sqlite3.connect(store.path) as db:
        assert db.execute("SELECT payload FROM policies").fetchone()[0] == payload
    with pytest.raises(ValueError, match="immutable_policy_version_conflict"):
        store.save(policy(scope_type="MARKET_WIDE", symbol_scope=[]))


def test_market_wide_serialization_and_store_roundtrip(tmp_path):
    item = disabled_policy(scope_type="MARKET_WIDE", symbol_scope=[])
    assert EvidencePolicy.model_validate_json(item.model_dump_json()) == item
    store = EvidencePolicyStore(tmp_path)
    store.save(item)
    store.save(item)
    assert store.list_policies() == (item,)
    assert store.get(item.policy_id, item.version).to_dict()["scope_type"] == "MARKET_WIDE"


def test_factor_disabled_roundtrip_and_resolution(tmp_path):
    item = disabled_policy()
    assert item.factor_enabled is False
    assert EvidencePolicy.model_validate_json(item.model_dump_json()) == item
    store = EvidencePolicyStore(tmp_path)
    store.save(item)
    result = EvidencePolicyResolver(store).resolve(event())
    assert result["status"] == "READY"
    assert result["selection_rules"]["definition_id"] is None
    assert result["selection_rules"]["required_factor_versions"] == []


@pytest.mark.parametrize("required,optional", [(["factors"], ["historical", "market"]),
    (["historical", "market"], ["factors"])])
@pytest.mark.parametrize("missing", ["definition_id", "universe_id", "normalization_version", "required_factor_versions"])
def test_factor_enabled_missing_metadata_fails_closed(required, optional, missing):
    with pytest.raises(ValidationError):
        policy(required_evidence=required, optional_evidence=optional,
               **{missing: [] if missing == "required_factor_versions" else None})


def test_old_factor_enabled_serialization_unchanged():
    item = policy()
    assert item.factor_enabled is True
    assert EvidencePolicy.model_validate_json(item.model_dump_json()).to_dict() == item.to_dict()


def test_disabled_legacy_unused_metadata_does_not_enable_factors():
    item = policy(required_evidence=["historical", "market"], optional_evidence=[])
    assert item.factor_enabled is False
    assert item.definition_id == "fixture-definition"


@pytest.mark.parametrize("missing", ["definition_id", "universe_id", "normalization_version", "required_factor_versions"])
def test_invalid_enabled_stored_policy_resolves_blocked(tmp_path, missing):
    store = EvidencePolicyStore(tmp_path)
    store.save(policy())
    invalid = policy().to_dict()
    invalid[missing] = [] if missing == "required_factor_versions" else None
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE policies SET payload=?", (json.dumps(invalid),))
    result = EvidencePolicyResolver(store).resolve(event())
    assert result["status"] == "BLOCKED"
    assert result["blocker"] == "policy_store_unavailable_or_invalid"


def test_serialization_and_nested_immutability():
    item = policy()
    assert EvidencePolicy.model_validate_json(item.model_dump_json()) == item
    detached = item.to_dict()
    detached["required_factor_versions"][0]["version"] = "2"
    assert item.required_factor_versions[0].version == "1"
    with pytest.raises(ValidationError):
        item.required_factor_versions[0].version = "2"


def test_save_get_list_idempotence_and_immutable_version(tmp_path):
    store = EvidencePolicyStore(tmp_path)
    assert store.get("missing", "v1") is None
    assert not store.path.exists()
    item = policy()
    store.save(item)
    store.save(item)
    assert store.get(item.policy_id, item.version) == item
    assert store.list_policies() == (item,)
    with pytest.raises(ValueError, match="immutable_policy_version_conflict"):
        store.save(policy(status="INACTIVE"))
    store.save(policy(version="v2"))
    assert len(store.list_policies()) == 2


def test_missing_policy_blocks_without_creating_database(tmp_path):
    store = EvidencePolicyStore(tmp_path)
    assert EvidencePolicyResolver(store).resolve(event())["blocker"] == "no_matching_policy"
    assert not store.path.exists()


def test_unique_match_preserves_event_and_explicit_rules(tmp_path):
    store = EvidencePolicyStore(tmp_path)
    item = policy()
    store.save(item)
    original = event()
    before = deepcopy(original)
    result = EvidencePolicyResolver(store).resolve(original)
    assert result == {"status": "READY", "blocker": None, "policy_id": item.policy_id,
                      "version": "v1", "selection_rules": item.to_dict()}
    assert original == before


@pytest.mark.parametrize("changes", [{"version": "v2"}, {"policy_id": "other-policy"}])
def test_multiple_matches_block_even_if_newer_version(tmp_path, changes):
    store = EvidencePolicyStore(tmp_path)
    store.save(policy())
    store.save(policy(**changes))
    assert EvidencePolicyResolver(store).resolve(event())["blocker"] == "multiple_matching_policies"


@pytest.mark.parametrize("timestamp,expected", [
    ("2026-09-30T23:59:59Z", "BLOCKED"), ("2026-10-01T00:00:00Z", "READY"),
    ("2026-11-01T00:00:00Z", "BLOCKED"), ("2026-11-01T08:00:00+08:00", "BLOCKED"),
])
def test_effective_period_half_open(tmp_path, timestamp, expected):
    store = EvidencePolicyStore(tmp_path)
    store.save(policy())
    assert EvidencePolicyResolver(store).resolve(event(detected_at=timestamp))["status"] == expected


@pytest.mark.parametrize("changes", [
    {"symbol": "700.HK", "market": "HK"}, {"symbol": "600519.SH", "market": "CN"},
    {"symbol": "NVDA.US"}, {"event_type": "intraday_breakout"},
    {"market": "HK"}, {"detected_at": "2026-10-14T15:00:00"},
])
def test_scope_and_invalid_time_fail_closed(tmp_path, changes):
    store = EvidencePolicyStore(tmp_path)
    store.save(policy())
    assert EvidencePolicyResolver(store).resolve(event(**changes))["status"] == "BLOCKED"


def test_inactive_and_open_ended_policy(tmp_path):
    store = EvidencePolicyStore(tmp_path)
    store.save(policy(status="INACTIVE"))
    assert EvidencePolicyResolver(store).resolve(event())["status"] == "BLOCKED"
    store.save(policy(version="v2", effective_to=None))
    assert EvidencePolicyResolver(store).resolve(event())["version"] == "v2"


@pytest.mark.parametrize("changes", [
    {"effective_to": "2026-10-01T00:00:00Z"}, {"definition_id": "default"},
    {"knowledge_cutoff_source": "latest"}, {"snapshot_date_rule": "yesterday"},
    {"symbol_scope": ["700.HK"]}, {"symbol_scope": ["AAPL.US", "AAPL.US"]},
    {"required_factor_versions": []}, {"normalization_version": "unknown"},
    {"required_evidence": ["factors"], "optional_evidence": ["factors"]},
    {"allow_move_atr_ratio": True, "require_price_scale_verified": False},
    {"allow_move_atr_ratio": True, "allow_atr_display": False},
    {"benchmark_required": True},
])
def test_ambiguous_or_unsafe_contract_rejected(changes):
    with pytest.raises(ValidationError):
        policy(**changes)


def test_store_corruption_blocks_instead_of_fallback(tmp_path):
    store = EvidencePolicyStore(tmp_path)
    store.path.parent.mkdir(parents=True)
    store.path.write_bytes(b"invalid sqlite fixture")
    assert EvidencePolicyResolver(store).resolve(event())["blocker"] == "policy_store_unavailable_or_invalid"
