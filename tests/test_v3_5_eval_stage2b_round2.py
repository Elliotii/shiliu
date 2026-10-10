from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from shiliu.eval_v3_5.intake import ROUND2_ORDER
from shiliu.eval_v3_5.models import CompletedReviewDecision, ReviewDecisionTemplate
from shiliu.eval_v3_5.round2 import (
    CALIBRATION_LEDGER_HASH,
    ROUND2_INPUT,
    ROUND2_INPUT_HASH,
    validate_round2,
)


ROOT = Path("research/v3_5")
HUMAN = ROOT / "human_reviews"


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _canonical(records: list[dict[str, object]]) -> str:
    return "".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for item in records
    )


def test_round2_input_identity_order_count_and_schema() -> None:
    path = HUMAN / "intake" / ROUND2_INPUT
    assert sha256(path.read_bytes()).hexdigest() == ROUND2_INPUT_HASH
    records = _jsonl(path)
    assert len(records) == 8
    assert tuple(item["case_id"] for item in records) == ROUND2_ORDER
    assert len({item["case_id"] for item in records}) == 8
    decisions = [CompletedReviewDecision.model_validate(item) for item in records]
    assert all(item.reviewer == "human_user" and item.decision_status == "completed" for item in decisions)


def test_round2_evidence_source_time_timeline_and_four_state_validation() -> None:
    records, audit = validate_round2()
    assert tuple(item["case_id"] for item in records) == ROUND2_ORDER
    for key in (
        "schema_validation_result", "packet_validation_result", "source_version_validation_result",
        "segment_validation_result", "timeline_validation_result", "four_state_invariant_result",
    ):
        assert audit[key] == "passed"
    assert audit["warnings"] == [] and audit["errors"] == []
    assert audit["label_distribution"] == {
        "insufficient": 3, "partial": 1, "sufficient": 3, "unverifiable": 1,
    }


def test_case004_is_sole_second_review_and_prior_span_reconstructs() -> None:
    records, audit = validate_round2()
    assert audit["needs_second_review_cases"] == ["CASE_004"]
    case004 = next(item for item in records if item["case_id"] == "CASE_004")
    assert case004["sufficiency_label"] == "partial"
    assert case004["review_confidence"] == "medium"
    assert case004["needs_second_review"] is True
    span = case004["gold_evidence_groups"][0]["required_spans"][0]
    assert (span["start_time"], span["end_time"]) == (129.16, 138.91)
    assert span["timeline_run_id"] == "timeline_run_f710676b394f8e735bec0dbf32407591d0a657e5eeb4496868ee1b15df274ce0"


def test_round2_canonical_ledger_is_deterministic_and_exact() -> None:
    source = _jsonl(HUMAN / "intake" / ROUND2_INPUT)
    expected = _canonical(source)
    ledger = HUMAN / "review_decisions.round2.8_cases.validated.jsonl"
    assert ledger.read_text(encoding="utf-8") == expected
    assert sha256(expected.encode("utf-8")).hexdigest() == "9c2a8ac2feb9d18fb7bac0f68b196192b8a22fac4948b0a4351b263b74fb16bb"
    audit = json.loads((HUMAN / "round2_8_case_validation_audit.json").read_text(encoding="utf-8"))
    assert audit["canonical_output_sha256"] == sha256(ledger.read_bytes()).hexdigest()


def test_provisional_18_case_merge_is_deterministic_and_marked_not_gold() -> None:
    calibration = HUMAN / "review_decisions.calibration.10_cases.validated.jsonl"
    round2 = HUMAN / "review_decisions.round2.8_cases.validated.jsonl"
    assert sha256(calibration.read_bytes()).hexdigest() == CALIBRATION_LEDGER_HASH
    expected = _canonical(_jsonl(calibration) + _jsonl(round2))
    master = HUMAN / "review_decisions.master.18_cases.provisional.jsonl"
    assert master.read_text(encoding="utf-8") == expected
    assert sha256(master.read_bytes()).hexdigest() == "ed2f18e8850d4fef891c1d89c191d49a793190bd40c8e4ae84b5e3b192a60ba0"
    records = _jsonl(master)
    assert len(records) == len({item["case_id"] for item in records}) == 18
    assert Counter(item["sufficiency_label"] for item in records) == Counter(
        {"sufficient": 9, "partial": 1, "insufficient": 6, "unverifiable": 2}
    )
    manifest = json.loads(
        (HUMAN / "review_decisions.master.18_cases.provisional.manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["ledger_status"] == "Provisional Master Ledger"
    assert manifest["gold_status"] == "Not Final Gold"
    assert manifest["source_type_distribution"] == {
        "ai": 10, "asr": 2, "human": 2, "query_corpus": 2, "title_only": 2,
    }


def test_case004_second_review_template_is_blank_and_prior_guide_is_nonfinal() -> None:
    template_path = HUMAN / "adjudication" / "review_decision.CASE_004.second_review.template.jsonl"
    decision = ReviewDecisionTemplate.model_validate_json(template_path.read_text(encoding="utf-8"))
    assert decision.case_id == "CASE_004"
    assert decision.decision_status == decision.sufficiency_label == "unreviewed"
    assert not decision.required_aspects and not decision.gold_evidence_groups
    guide = (HUMAN / "adjudication" / "CASE_004_SECOND_REVIEW_GUIDE.md").read_text(encoding="utf-8")
    assert "Prior Human Decision — Not Final Adjudicated Gold" in guide
    assert "ra" in guide and "A1" in guide and "A2" in guide and "A3" in guide


def test_no_split_or_reserve_activation_and_reason_codes_preserved() -> None:
    leakage = json.loads((ROOT / "preliminary_leakage_report.json").read_text(encoding="utf-8"))
    constraints = leakage["stage2b_round2_constraints"]
    assert constraints["split_assigned"] is False
    assert constraints["development_only"] == ["CASE_012"]
    assert any(set(item["case_ids"]) == {"CASE_001", "CASE_012"} for item in constraints["future_same_split_groups"])
    audit = json.loads((HUMAN / "round2_reason_code_registry_audit.json").read_text(encoding="utf-8"))
    assert audit["automatic_renaming_performed"] is False
    assert {"limited_aspect_coverage", "partial_aspect_coverage"} == set(
        audit["recommended_stage2c_canonical_registry"]["review_alias_pair"]
    )
    active_reserves = [
        item for item in _jsonl(ROOT / "active_review_round2.jsonl")
        if str(item["case_id"]).startswith("RESERVE_")
    ]
    assert active_reserves == []
