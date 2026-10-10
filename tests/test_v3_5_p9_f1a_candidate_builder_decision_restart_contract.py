from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    ROOT
    / "research/v3_5/product_query_set_v1/"
    "f1a_candidate_builder_decision_restart"
)
AMENDMENT = (
    ROOT
    / "research/v3_5/product_query_set_v1/"
    "product_initial_baseline_attempt_3/scoring_amendment_v1"
)


FAILURE_IDS = {
    "PQS_V1_Q003",
    "PQS_V1_Q004",
    "PQS_V1_Q005",
    "PQS_V1_Q008",
    "PQS_V1_Q015",
    "PQS_V1_Q018",
}


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def test_amended_scoring_identity_matches() -> None:
    manifest = load_json(OUTPUT / "f1a_decision.manifest.json")
    assert (
        manifest["input_identity"]["p8_scoring_hash_root"]
        == "54bc35083f4410ace027452b64fc2d22432111be5a2036c0ce245e6319849795"
    )
    assert manifest["input_identity"]["p8_scoring_version"] == "P8_SCORING_AMENDMENT_V1"
    assert manifest["input_identity"]["checkpoint_1_amendment_status"] == "complete_and_accepted"


def test_exactly_six_builder_failure_records() -> None:
    rows = load_jsonl(OUTPUT / "f1a_failure_analysis.jsonl")
    assert len(rows) == 6
    assert {row["query_id"] for row in rows} == FAILURE_IDS


def test_q017_excluded() -> None:
    decision = load_json(OUTPUT / "f1a_decision.json")
    assert decision["decision_basis"]["q017_included"] is False
    assert "PQS_V1_Q017" not in decision["decision_basis"]["supporting_query_ids"]
    attributions = load_jsonl(
        AMENDMENT / "p8_scoring_amendment.failure_attribution.jsonl"
    )
    q017 = next(row for row in attributions if row["query_id"] == "PQS_V1_Q017")
    assert q017["primary_attribution"] == "gold_defined_evidence_absent"


def test_all_six_are_builder_failure_eligible() -> None:
    attributions = load_jsonl(
        AMENDMENT / "p8_scoring_amendment.failure_attribution.jsonl"
    )
    rows = [
        row
        for row in attributions
        if row["primary_attribution"] == "candidate_builder_failure"
    ]
    assert {row["query_id"] for row in rows} == FAILURE_IDS
    for row in rows:
        eligibility = row["eligibility"]
        assert eligibility["eligible_for_candidate_builder_failure"] is True
        assert eligibility["authoritative_source_reviewable"] is True
        assert eligibility["acceptable_evidence_group_count"] > 0
        assert eligibility["required_material_evidence_constructible"] is True


def test_failure_records_reference_persisted_assets() -> None:
    p8_hash_rows = {
        row["path"]: row["sha256"]
        for row in load_jsonl(
            ROOT
            / "research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3"
            / "blind_run/product_initial_baseline.prediction_hash_manifest.jsonl"
        )
    }
    for record in load_jsonl(OUTPUT / "f1a_failure_analysis.jsonl"):
        assert record["retrieval_success_proof"]["acceptable_hit"] is True
        assert (
            record["retrieval_success_proof"][
                "all_required_gold_segments_present_in_raw_mapped_union"
            ]
            is True
        )
        for reference in record["artifact_references"]:
            path = ROOT / reference["path"]
            if path.is_file():
                assert digest(path) == reference["sha256"]
            else:
                relative = str(
                    path.relative_to(
                        ROOT
                        / "research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3"
                    )
                )
                assert p8_hash_rows[relative] == reference["sha256"]


def test_execute_requires_genericity_gate() -> None:
    decision = load_json(OUTPUT / "f1a_decision.json")
    assert decision["f1a_decision_candidate"] == "execute"
    assert all(decision["genericity_gate"].values())


def test_execute_has_single_bounded_design() -> None:
    audit = load_json(OUTPUT / "f1a_decision.audit.json")
    design = load_json(OUTPUT / "f1a_candidate_design.json")
    change = design["single_algorithm_or_policy_change"]
    assert audit["decision"]["single_candidate_design_count"] == 1
    assert change["total_slot_cap"] == 32
    assert change["existing_relevance_slots"] == 28
    assert change["coverage_reserve_slots"] == 4
    assert len(design["addressable_failure_ids"]) == 5


def test_no_case_video_gold_specific_rule() -> None:
    design = load_json(OUTPUT / "f1a_candidate_design.json")
    safety = design["safety_constraints"]
    assert safety["case_id_rule_forbidden"] is True
    assert safety["video_id_rule_forbidden"] is True
    assert safety["gold_feature_forbidden"] is True


def test_no_heavy_architecture_or_unbounded_window() -> None:
    design = load_json(OUTPUT / "f1a_candidate_design.json")
    safety = design["safety_constraints"]
    assert safety["heavy_architecture_forbidden"] is True
    assert safety["per_video_candidate_maximum"] == 32
    assert safety["candidate_max_segments"] == 6
    assert safety["candidate_max_duration_seconds"] == 60
    assert safety["total_union_duration_seconds_maximum"] == 600


def test_no_code_prediction_scoring_change() -> None:
    audit = load_json(OUTPUT / "f1a_decision.audit.json")
    scope = audit["scope"]
    assert scope["code_changed"] is False
    assert scope["predictions_rerun"] is False
    assert scope["scoring_rerun"] is False
    assert scope["query_split_gold_changed"] is False
    selector_v2_seal = load_json(ROOT / "SELECTOR_V2_FREEZE_SEAL.json")
    assert digest(ROOT / "src/shiliu/evidence/stage3a.py") == (
        selector_v2_seal["selector_source_hashes"]["src/shiliu/evidence/stage3a.py"]
    )
    assert (
        digest(ROOT / "src/shiliu/evidence/stage3b.py")
        == "8a2ed841efdf42f048347bf23ed1170a67ce7be0f3b03823eabef31847a80458"
    )


def test_no_frozen_access() -> None:
    audit = load_json(OUTPUT / "f1a_decision.audit.json")
    assert audit["scope"]["frozen_gold_opened"] is False
    for path in OUTPUT.iterdir():
        if path.is_file():
            assert "frozen_guarded/" not in path.read_text()


def test_no_f1a_implementation_or_f1b_stage4_start() -> None:
    audit = load_json(OUTPUT / "f1a_decision.audit.json")
    execution = load_json(OUTPUT / "f1a_decision.execution_decision.json")
    assert audit["scope"]["f1a_implementation_started"] is False
    assert audit["scope"]["f1b_started"] is False
    assert audit["scope"]["stage4_started"] is False
    assert execution["f1a_authorized_by_codex"] is False
    assert execution["f1b_authorized"] is False
    assert execution["next_stage_started"] is False
    assert execution["component_behavior_changed"] is False


def test_manifest_hashes_match() -> None:
    rows = load_jsonl(OUTPUT / "f1a_decision.file_hash_manifest.jsonl")
    assert len(rows) == 9
    for row in rows:
        path = ROOT / row["path"]
        assert path.is_file()
        assert path.name != "f1a_decision.file_hash_manifest.jsonl"
        assert digest(path) == row["sha256"]
