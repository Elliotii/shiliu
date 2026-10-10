from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from shiliu.eval_v3_5.stage2c import (
    ADJUDICATION_INPUT_HASH,
    ALLOWED_CASE004_CHANGES,
    DEVELOPMENT_ORDER,
    HELDOUT_ORDER,
    INPUTS,
    LEAKAGE_GROUPS,
    MASTER_ORDER,
    validate_stage2c_inputs,
)


ROOT = Path("research/v3_5")
GOLD = ROOT / "gold"

LOCKED_HASHES = {
    "HELDOUT_ISOLATION_CONTRACT.md": "faeccb772dd624775e58b55e8614af836fb64d102e7762244b3869767641f18e",
    "V3_5_EVAL_PROTOCOL.locked.md": "01f1dd8d6f26bd68962ccb42b489f5be3d086cef2ed0fe90616cb9d3e43db90f",
    "development_gold.8_cases.locked.jsonl": "5693830749e3fba38dd35fc143988fb615ae48bf0f02b7344c8b03ce4a1d90d0",
    "development_heldout_split.locked.json": "fc3ff77b7d22668b5a7e555e8db44abdec1ce856c0b629f80327145831b7731c",
    "gold_granularity_audit.json": "8ba9c4bbc11aa3bb1243ce189d75bf35bb07e18ad3a5fccd100ae3ba3ed45aef",
    "gold_lock_audit.json": "da65889ae2bbcea2f0a34e40a42c8ee598d185ab3183f07970d0f16e6426e77d",
    "gold_lock_manifest.json": "268d9b68e29cc7f242375ba108d9d99ef536e2f413c3747d9f95f7ab97588075",
    "heldout_gold.10_cases.locked.jsonl": "6b7d06a6a0f3eeb61a9bc542ee8c2a8d12fc6d52fbb6576f64eff72d0d662789",
    "master_case_membership.locked.json": "e95e23e6f9d4043b01d43e04c7a53ed56fe7577d2a1bcfc0b7b8996d12d60a93",
    "master_gold.18_cases.locked.jsonl": "340e90bdd078e9b9a7aeac2bd98245b22d0e0b1f6d04812c675805996ad1fc09",
    "reason_code_registry.locked.json": "6725bd1a55457319557e83b350aae50145ccb3a912d3070b4d95e859aa80f0fc",
    "review_decisions.master.18_cases.adjudicated.jsonl": "340e90bdd078e9b9a7aeac2bd98245b22d0e0b1f6d04812c675805996ad1fc09",
}


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_authoritative_input_hashes_and_case004_single_record() -> None:
    for path, expected in INPUTS.items():
        assert sha256(Path(path).read_bytes()).hexdigest() == expected
    adjudication = _jsonl(
        ROOT / "human_reviews/adjudication/review_decision.CASE_004.second_review.completed.jsonl"
    )
    assert len(adjudication) == 1
    assert sha256(
        (ROOT / "human_reviews/adjudication/review_decision.CASE_004.second_review.completed.jsonl").read_bytes()
    ).hexdigest() == ADJUDICATION_INPUT_HASH
    assert adjudication[0]["case_id"] == "CASE_004"
    assert adjudication[0]["decision_status"] == "completed"
    assert adjudication[0]["sufficiency_label"] == "partial"
    assert adjudication[0]["needs_second_review"] is False


def test_case004_comparison_and_complete_mechanical_revalidation() -> None:
    records, audit = validate_stage2c_inputs()
    assert tuple(item["case_id"] for item in records) == MASTER_ORDER
    assert set(audit["changed_fields"]) <= ALLOWED_CASE004_CHANGES
    case004 = next(item for item in records if item["case_id"] == "CASE_004")
    assert case004["supported_aspects"] == ["A3"]
    assert case004["missing_aspects"] == ["A1", "A2"]
    assert case004["primary_reason_codes"] == ["partial_aspect_coverage"]
    span = case004["gold_evidence_groups"][0]["required_spans"][0]
    assert (span["start_time"], span["end_time"]) == (129.16, 138.91)
    assert span["segment_ids"] == [
        "segment_29e70d2062a444b6421fe4bd3c46cf68474d929f556190b21d29f811896f5a0c",
        "segment_12dc3adced5bef04fabe5e3739ca4fc840a1faf8b298732064a9f6caf95c8ad3",
    ]
    for name in ("calibration_validation", "round2_validation", "adjudication_validation"):
        assert audit[name]["errors"] == []
        assert audit[name]["schema_validation_result"] == "passed"
        assert audit[name]["source_version_validation_result"] == "passed"
        assert audit[name]["segment_validation_result"] == "passed"
        assert audit[name]["timeline_validation_result"] == "passed"
        assert audit[name]["four_state_invariant_result"] == "passed"


def test_locked_master_distribution_and_only_case004_override() -> None:
    provisional = _jsonl(ROOT / "human_reviews/review_decisions.master.18_cases.provisional.jsonl")
    master = _jsonl(GOLD / "master_gold.18_cases.locked.jsonl")
    assert len(master) == len({item["case_id"] for item in master}) == 18
    assert tuple(item["case_id"] for item in master) == MASTER_ORDER
    assert not any(item["needs_second_review"] for item in master)
    assert Counter(item["sufficiency_label"] for item in master) == Counter(
        {"sufficient": 9, "partial": 1, "insufficient": 6, "unverifiable": 2}
    )
    before = {item["case_id"]: item for item in provisional}
    after = {item["case_id"]: item for item in master}
    assert all(before[case_id] == after[case_id] for case_id in MASTER_ORDER if case_id != "CASE_004")
    assert before["CASE_004"] != after["CASE_004"]
    assert (GOLD / "master_gold.18_cases.locked.jsonl").read_bytes() == (
        GOLD / "review_decisions.master.18_cases.adjudicated.jsonl"
    ).read_bytes()


def test_exact_split_leakage_groups_and_coverage() -> None:
    development = _jsonl(GOLD / "development_gold.8_cases.locked.jsonl")
    heldout = _jsonl(GOLD / "heldout_gold.10_cases.locked.jsonl")
    assert tuple(item["case_id"] for item in development) == DEVELOPMENT_ORDER
    assert tuple(item["case_id"] for item in heldout) == HELDOUT_ORDER
    dev_ids = set(DEVELOPMENT_ORDER)
    held_ids = set(HELDOUT_ORDER)
    assert not dev_ids & held_ids
    assert dev_ids | held_ids == set(MASTER_ORDER)
    assert "CASE_012" in dev_ids and "CASE_004" in held_ids
    for members in LEAKAGE_GROUPS.values():
        assert set(members) <= dev_ids or set(members) <= held_ids
    assert Counter(item["sufficiency_label"] for item in heldout) == Counter(
        {"sufficient": 5, "partial": 1, "insufficient": 3, "unverifiable": 1}
    )
    split = json.loads((GOLD / "development_heldout_split.locked.json").read_text(encoding="utf-8"))
    assert split["heldout"]["distributions"]["sources"] == {
        "ai": 6, "asr": 1, "human": 1, "query_corpus": 1, "title_only": 1,
    }
    assert split["active_reserve_count"] == 0
    assert split["excluded_cases"] == ["CASE_019", "CASE_020"]


def test_reason_registry_granularity_protocol_and_locked_hashes() -> None:
    registry = json.loads((GOLD / "reason_code_registry.locked.json").read_text(encoding="utf-8"))
    assert registry["historical_aliases"] == {"limited_aspect_coverage": "partial_aspect_coverage"}
    for code in (
        "partial_aspect_coverage", "semantic_neighbor_only", "query_target_mismatch", "title_only",
        "no_approved_target", "out_of_domain_negative_control", "asr_transcription_uncertainty",
    ):
        assert code in registry["codes"]
    granularity = json.loads((GOLD / "gold_granularity_audit.json").read_text(encoding="utf-8"))
    assert granularity["cases_audited"] == 10
    assert granularity["groups_audited"] == 11
    assert granularity["blocking_provenance_errors"] == 0
    assert granularity["needs_human_granularity_review"] == 0
    assert {item["case_id"] for item in granularity["groups"]} == {
        "CASE_001", "CASE_002", "CASE_003", "CASE_004", "CASE_005", "CASE_007",
        "CASE_008", "CASE_009", "CASE_010", "CASE_011",
    }
    protocol = (GOLD / "V3_5_EVAL_PROTOCOL.locked.md").read_text(encoding="utf-8")
    assert "Status: **Locked**" in protocol
    assert "English positive evidence: **not established**" in protocol
    assert "Development real partial: **0**" in protocol
    for filename, expected in LOCKED_HASHES.items():
        assert sha256((GOLD / filename).read_bytes()).hexdigest() == expected


def test_gold_lock_manifest_and_audit_are_complete() -> None:
    manifest = json.loads((GOLD / "gold_lock_manifest.json").read_text(encoding="utf-8"))
    audit = json.loads((GOLD / "gold_lock_audit.json").read_text(encoding="utf-8"))
    assert manifest["counts"] == {"development": 8, "heldout": 10, "master": 18}
    assert manifest["active_reserve_count"] == 0
    assert audit["all_input_hashes_verified"] is True
    assert audit["case004_adjudication_validated"] is True
    assert audit["only_case004_changed_from_provisional"] is True
    assert audit["other_17_records_value_identical"] is True
    assert audit["needs_second_review_count"] == 0
    assert audit["development_heldout_disjoint"] is True
    assert audit["development_heldout_union_equals_master"] is True
    assert audit["errors"] == []
