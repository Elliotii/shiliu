import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/v3_5/handoff_draft/fact_freeze"
REQUIRED = {
    "artifact_name", "repository_path", "exists", "status", "file_sha256",
    "content_or_manifest_sha256", "hash_scope", "schema_or_policy_version",
    "produced_by_stage", "supersedes", "superseded_by", "authority_scope",
    "record_count", "notes",
}


def load(name: str):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def inventory():
    return [json.loads(line) for line in (OUT / "handoff_authority_inventory.r2.jsonl").read_text(encoding="utf-8").splitlines()]


def test_r2_preserves_prior_freezes_and_does_not_execute_system_work():
    audit = load("handoff_fact_freeze_r2_execution.audit.json")
    assert audit["original_h0_assets_modified"] is False
    assert audit["r1_assets_modified"] is False
    assert audit["retrieval_run"] is False
    assert audit["frozen_evaluation_accessed"] is False
    assert audit["stage3r_pqs_b0_executed"] is False
    assert audit["stage3r_pqs_b0_accepted"] is False
    assert audit["formal_handoff_files_generated"] is False


def test_r2_fact_freeze_resolves_current_state_metadata_consistency():
    facts = load("handoff_fact_freeze.r2.json")
    assert facts["previous_current_state_audit"]["status"] == "stale_requires_update"
    assert facts["current_state_audit"]["status"] == "current"
    assert facts["metadata_consistency"]["status"] == "passed"
    assert facts["unresolved_facts"] == []


def test_r2_inventory_has_complete_schema_and_normalized_metadata():
    entries = inventory()
    assert entries
    assert all(set(entry) == REQUIRED for entry in entries)
    assert all(entry["produced_by_stage"] != "local historical asset" for entry in entries)
    assert all(entry["schema_or_policy_version"] for entry in entries)
    assert all(entry["exists"] for entry in entries)
    by_name = {entry["artifact_name"]: entry for entry in entries}
    assert by_name["Structured LLM selector v1"]["status"] == "rejected"
    assert by_name["Mechanical Gate v1"]["status"] == "historical"
    assert by_name["Stage 3R-PQS-B0 execution candidate report"]["status"] == "unreviewed_execution_candidate"


def test_current_state_has_authority_notice_without_completion_claims():
    state = (ROOT / "V3_5_CURRENT_STATE.md").read_text(encoding="utf-8")
    assert "> **Current authority notice**" in state
    assert "## Stage 3R-S1 Authoritative Update" in state
    assert "v3_5_version_complete: false" in state
    assert "acceptance_status: unreviewed_execution_candidate" in state


def test_r2_hash_inventory_matches_current_recorded_files_and_is_ready():
    changed = set()
    for line in (OUT / "artifact_hash_inventory.r2.jsonl").read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        path = ROOT / entry["repository_path"]
        assert path.is_file()
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["file_sha256"]:
            changed.add(entry["repository_path"])
    assert changed == {
        "V3_5_CURRENT_STATE.md",
        "research/v3_5/stage3b/stage3b_run_manifest.json",
        "src/shiliu/evidence/stage3a.py",
        "research/v3_5/stage4a/mechanical_gate_contract.json",
    }
    assert (ROOT / "V3_5_FINAL_FREEZE_SEAL.json").is_file()
    assert load("handoff_fact_freeze_r2_manifest.json")["ready_for_five_file_draft"] is True
