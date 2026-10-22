import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/v3_5/handoff_draft/fact_freeze"


def read_json(name: str):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_handoff_fact_freeze_does_not_modify_production():
    assert read_json("handoff_fact_freeze_execution.audit.json")["production_files_modified"] is False


def test_handoff_fact_freeze_does_not_run_retrieval_or_access_frozen_evaluation():
    audit = read_json("handoff_fact_freeze_execution.audit.json")
    assert audit["retrieval_run"] is False
    assert audit["frozen_evaluation_accessed"] is False


def test_handoff_fact_freeze_does_not_execute_b0_or_formal_handoff():
    audit = read_json("handoff_fact_freeze_execution.audit.json")
    assert audit["b0_executed"] is False
    assert audit["formal_handoff_files_generated"] is False


def test_authority_inventory_hashes_are_preserved_with_known_supersessions():
    changed = set()
    for line in (OUT / "handoff_authority_inventory.jsonl").read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        if entry["file_sha256"]:
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


def test_current_state_and_stress_corpus_are_explicitly_classified():
    inventory = [json.loads(line) for line in (OUT / "handoff_authority_inventory.jsonl").read_text(encoding="utf-8").splitlines()]
    by_name = {entry["artifact_name"]: entry for entry in inventory}
    assert by_name["V3.5 current state"]["status"] == "current_source_of_truth"
    assert (ROOT / "V3_5_FINAL_CLOSEOUT.md").is_file()
    assert by_name["Stress set v2 manifest"]["notes"].startswith("Canonical corpus content hash")


def test_case_metrics_and_b0_handoff_fact_are_resolved_or_explicitly_unresolved():
    facts = read_json("handoff_fact_freeze.json")
    assert facts["corrected_stress_track_a"]["metrics"]["bundle_hit"]["numerator"] == 1
    assert facts["oracle_video_track_b"]["bundle_hit"]["numerator"] == 2
    assert facts["track_b_vs_auto_difference"]["status"] == "resolved"
    assert facts["b0"]["owner"] == "v3_5_b"
    assert facts["b0"]["executed"] is False


def test_stress_set_record_count_distribution_and_hash_scope_are_explicit():
    stress = read_json("handoff_fact_freeze.json")["stress_set_v2"]
    assert stress["total"] == 31
    assert stress["labels"] == {"sufficient": 11, "partial": 9, "insufficient": 7, "unverifiable": 4}
    assert stress["hash_scope"].startswith("canonical corpus content identity")


def test_track_b_vs_auto_case_ids_and_trace_paths_are_resolved():
    difference = read_json("track_b_vs_auto_bundle_hit_diff.audit.json")
    assert difference["oracle_video_track_b_bundle_hits"]["case_ids"] == [
        "V2C_C0C_5725899059df795c",
        "V2C_C0C_8228254ff69d7b3b",
    ]
    assert difference["corrected_auto_track_a_bundle_hits"]["case_ids"] == ["V2C_C0C_9618a83c9df4f059"]
    assert all(any(path.endswith("trace.json") for path in entry["supporting_artifact_paths"]) for entry in difference["difference"])


def test_versions_and_component_statuses_are_recorded():
    facts = read_json("handoff_fact_freeze.json")
    assert facts["product_search"]["wiring_version"] == "v3-product-search-default-auto-v1"
    assert facts["active_components"]["candidate_builder_version"] == "stage3b-acronym-w3.5-v1"
    assert facts["active_components"]["deterministic_selector_version"] == "v3.5-deterministic-fine-selector-v1"
    assert facts["rejected_components"]["structured_llm_selector_v1"]["status"] == "rejected"
    assert facts["historical_components"]["mechanical_gate"]["requires_stage4a_r"] is True
