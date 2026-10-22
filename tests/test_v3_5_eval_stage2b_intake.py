from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from shiliu.eval_v3_5.intake import (
    AUTHORIZED_ORDER,
    EXPECTED_INPUT_HASHES,
    INTAKE_FILES,
    ROUND2_ORDER,
    validate_human_intake,
)
from shiliu.eval_v3_5.models import CompletedReviewDecision, ReviewDecisionTemplate, Round2ReviewRecord


ROOT = Path("research/v3_5")
HUMAN = ROOT / "human_reviews"


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_human_input_hashes_counts_and_unique_ids() -> None:
    records = []
    for filename, expected_count in zip(INTAKE_FILES, (6, 4), strict=True):
        path = HUMAN / "intake" / filename
        assert sha256(path.read_bytes()).hexdigest() == EXPECTED_INPUT_HASHES[filename]
        values = _jsonl(path)
        assert len(values) == expected_count
        records.extend(values)
    assert tuple(item["case_id"] for item in records) == AUTHORIZED_ORDER
    assert len({item["case_id"] for item in records}) == 10


def test_all_ten_decisions_validate_formal_schema_and_human_authority() -> None:
    records = []
    for filename in INTAKE_FILES:
        records.extend(_jsonl(HUMAN / "intake" / filename))
    decisions = [CompletedReviewDecision.model_validate(item) for item in records]
    assert all(item.reviewer == "human_user" and item.decision_status == "completed" for item in decisions)
    assert {item.sufficiency_label for item in decisions} == {"sufficient", "insufficient", "unverifiable"}


def test_evidence_source_segment_time_timeline_aspect_and_four_state_validation() -> None:
    records, audit = validate_human_intake()
    assert tuple(item["case_id"] for item in records) == AUTHORIZED_ORDER
    for key in (
        "schema_validation_result", "packet_validation_result", "source_version_validation_result",
        "segment_validation_result", "timeline_validation_result", "four_state_invariant_result",
    ):
        assert audit[key] == "passed"
    assert audit["warnings"] == [] and audit["errors"] == []
    assert audit["label_distribution"] == {"insufficient": 3, "sufficient": 6, "unverifiable": 1}
    assert audit["needs_second_review_cases"] == []


def test_canonical_ledger_is_deterministic_and_semantically_exact() -> None:
    source = []
    for filename in INTAKE_FILES:
        source.extend(_jsonl(HUMAN / "intake" / filename))
    expected = "".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for item in source
    )
    ledger = HUMAN / "review_decisions.calibration.10_cases.validated.jsonl"
    assert ledger.read_text(encoding="utf-8") == expected
    digest = sha256(expected.encode("utf-8")).hexdigest()
    manifest = json.loads((HUMAN / "calibration_intake_manifest.json").read_text(encoding="utf-8"))
    audit = json.loads((HUMAN / "calibration_10_case_validation_audit.json").read_text(encoding="utf-8"))
    assert digest == "06ce0e3980e09618a901f572e96ab9d0970660219f33cab79630860532f01737"
    assert manifest["canonical_ledger"]["sha256"] == audit["canonical_output_sha256"] == digest


def test_round2_active_set_has_exact_order_packets_and_no_reserve() -> None:
    records = [Round2ReviewRecord.model_validate(item) for item in _jsonl(ROOT / "active_review_round2.jsonl")]
    assert tuple(item.case_id for item in records) == ROUND2_ORDER
    assert [item.review_order for item in records] == list(range(1, 9))
    assert all(Path(item.packet_path).is_file() for item in records)
    assert all(item.decision_status == "unreviewed" and not item.case_id.startswith("RESERVE_") for item in records)


def test_round2_decisions_are_exactly_eight_blank_records() -> None:
    values = _jsonl(ROOT / "review_decisions.round2.template.jsonl")
    decisions = [ReviewDecisionTemplate.model_validate(item) for item in values]
    assert tuple(item.case_id for item in decisions) == ROUND2_ORDER
    assert all(item.decision_status == item.sufficiency_label == "unreviewed" for item in decisions)
    assert all(not item.required_aspects and not item.gold_evidence_groups for item in decisions)
    assert all(not item.supported_aspects and not item.missing_aspects and not item.primary_reason_codes for item in decisions)


def test_no_split_or_reserve_activation_was_assigned() -> None:
    active = _jsonl(ROOT / "active_review_round2.jsonl")
    assert all("split" not in item and "activation_reason" not in item for item in active)
    leakage = json.loads((ROOT / "preliminary_leakage_report.json").read_text(encoding="utf-8"))
    assert leakage["status"] == "preliminary_only_no_split_assigned"
    assert leakage["stage2b_round2_constraints"]["split_assigned"] is False
    assert leakage["stage2b_round2_constraints"]["development_only"] == ["CASE_012"]
