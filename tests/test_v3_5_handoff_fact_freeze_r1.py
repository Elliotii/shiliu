import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/v3_5/handoff_draft/fact_freeze"
TASK = ROOT / "research/v3_5/product_query_set_v1/authoring_packet/STAGE3R_PQS_B0_NEUTRAL_AUTHORING_PACKET_EXPORT_TASK.md"


def load(name: str):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_h0_r_preserves_original_h0_assets_and_does_not_execute_or_accept_b0():
    audit = load("handoff_fact_freeze_r1_execution.audit.json")
    assert audit["original_h0_assets_overwritten"] is False
    assert audit["stage3r_pqs_b0_executed"] is False
    assert audit["stage3r_pqs_b0_accepted"] is False


def test_h0_r_does_not_run_retrieval_or_access_frozen_evaluation():
    audit = load("handoff_fact_freeze_r1_execution.audit.json")
    assert audit["retrieval_run"] is False
    assert audit["frozen_evaluation_accessed"] is False


def test_b0_task_contract_matches_approved_session_text_and_candidate_is_unreviewed():
    facts = load("handoff_fact_freeze.r1.json")
    b0 = facts["stage3r_pqs_b0"]
    assert TASK.exists()
    assert hashlib.sha256(TASK.read_bytes()).hexdigest() == "2e2eea765e7400141b715cea77c89e0e88f98ef3f9d1f69b468110acf8dc1cc0"
    assert b0["task_contract"]["status"] == "accepted_task_contract"
    assert b0["acceptance"] == {"status": "unreviewed_execution_candidate", "accepted": False, "owner": "v3_5_b"}


def test_current_state_records_corrected_handoff_and_no_completion_claim():
    state = (ROOT / "V3_5_CURRENT_STATE.md").read_text(encoding="utf-8")
    for expected in ("wiring_version: v3-product-search-default-auto-v1", "target_video_recall: 20/20", "f1a: {status: paused", "final_set_frozen: false", "frozen_evaluation_set:", "v3_5_version_complete: false"):
        assert expected in state
    manifest = load("handoff_fact_freeze_r1_manifest.json")
    assert manifest["current_state_before_sha256"] == "b9f14c8817d10fc19b4133911791cb1720d0a71b239764932fd7c61077b82bcc"
    assert manifest["current_state_after_sha256"] == "29c9b3c951c1ca5d504e2fbc5bbd2055c5cfd75b75b67cc83d141c8cf118134f"
    assert manifest["current_state_after_sha256"] != hashlib.sha256(
        (ROOT / "V3_5_CURRENT_STATE.md").read_bytes()
    ).hexdigest()
    assert (ROOT / "V3_5_FINAL_CLOSEOUT.md").is_file()


def test_authority_inventory_marks_required_statuses_and_no_unresolved_facts():
    entries = [json.loads(line) for line in (OUT / "handoff_authority_inventory.jsonl").read_text(encoding="utf-8").splitlines()]
    by_name = {entry["artifact_name"]: entry for entry in entries}
    assert by_name["Structured LLM selector v1"]["status"] == "rejected"
    assert by_name["Mechanical Gate v1"]["status"] == "historical"
    assert by_name["Product Query Phase A"]["status"] == "historical"
    assert by_name["Stage 3R-PQS-B0 execution candidate report"]["status"] == "unreviewed_execution_candidate"
    assert load("handoff_fact_freeze.r1.json")["unresolved_facts"] == []
