"""Isolated policies are fixtures, not active production evidence configuration."""
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
