import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "research"
    / "v3_5"
    / "product_query_set_v1"
    / "f1a_preimplementation_recovery_amendment"
)


def load_json(name):
    return json.loads((OUTPUT / name).read_text())


def test_invalid_attempt_did_not_consume_major_cycle():
    decision = load_json("f1a_preimplementation_recovery.execution_decision.json")
    assert decision["f1a"]["previous_attempt"] == "invalid_preimplementation_attempt"
    assert decision["f1a"]["major_cycles_used"] == 0


def test_major_cycle_remaining_is_one():
    decision = load_json("f1a_preimplementation_recovery.execution_decision.json")
    assert decision["f1a"]["major_cycles_remaining"] == 1


def test_restart_is_not_second_cycle():
    decision = load_json("f1a_preimplementation_recovery.execution_decision.json")
    assert decision["f1a"]["restart_is_second_cycle"] is False
    assert decision["f1a"]["second_major_cycle_authorized"] is False


def test_active_design_unchanged():
    decision = load_json("f1a_preimplementation_recovery.execution_decision.json")
    assert decision["active_design"] == "adaptive_bounded_coverage_swap_v1"
    assert decision["design_changed"] is False


def test_acceptance_thresholds_unchanged():
    decision = load_json("f1a_preimplementation_recovery.execution_decision.json")
    assert decision["acceptance_thresholds_changed"] is False


def test_new_session_required():
    decision = load_json("f1a_preimplementation_recovery.execution_decision.json")
    assert decision["f1a"]["next_execution_requires_new_session"] is True


def test_default_deny_access_policy():
    policy = load_json("F1A_RECOVERY_FILESYSTEM_ACCESS_POLICY.json")
    assert policy["default"] == "deny"


def test_repository_root_recursive_search_forbidden():
    policy = load_json("F1A_RECOVERY_FILESYSTEM_ACCESS_POLICY.json")
    forbidden = "\n".join(policy["forbidden_operations"])
    assert "rg from repository root" in forbidden
    assert "find from repository root" in forbidden
    assert "grep -R from repository root" in forbidden
    assert "git grep over the repository" in forbidden


def test_frozen_path_patterns_forbidden():
    policy = load_json("F1A_RECOVERY_FILESYSTEM_ACCESS_POLICY.json")
    patterns = policy["forbidden_path_patterns"]
    assert "**/frozen_guarded/**" in patterns
    assert "**/internal_protected/**" in patterns
    assert "**/reviewed_gold_candidate/**" in patterns
    assert "**/frozen_cycle_v1/sealed/**" in patterns
    assert "**/*FROZEN_GOLD*" in patterns
    assert "**/*frozen_gold*" in patterns


def test_missing_exact_path_blocks():
    policy = load_json("F1A_RECOVERY_FILESYSTEM_ACCESS_POLICY.json")
    assert policy["failure_behavior"]["missing_exact_path"] == "block"


def test_no_builder_or_scored_run():
    audit = load_json("f1a_preimplementation_recovery.audit.json")
    assert audit["scope"]["builder_changed"] is False
    assert audit["scope"]["implementation_started"] is False
    assert audit["scope"]["development_scored_runs"] == 0
    assert audit["scope"]["stress_scored_runs"] == 0


def test_no_f1b_or_stage4_start():
    audit = load_json("f1a_preimplementation_recovery.audit.json")
    assert audit["scope"]["f1b_started"] is False
    assert audit["scope"]["stage4_started"] is False


def test_manifest_hashes_match():
    manifest = OUTPUT / "f1a_preimplementation_recovery.file_hash_manifest.jsonl"
    for line in manifest.read_text().splitlines():
        record = json.loads(line)
        payload = (OUTPUT / record["path"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == record["sha256"]
