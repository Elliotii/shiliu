from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from shiliu.eval_v3_5.calibration import AUTHORIZED_ORDER, validate_calibration_assets
from shiliu.eval_v3_5.models import ActiveCalibrationRecord, MasterCaseCandidate, ReviewDecisionTemplate
from shiliu.eval_v3_5.packets import validate_review_assets


ROOT = Path("research/v3_5")


def _jsonl(name: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in (ROOT / name).read_text(encoding="utf-8").splitlines()]


def test_active_calibration_has_exact_authorized_order_and_packets() -> None:
    records = [ActiveCalibrationRecord.model_validate(item) for item in _jsonl("active_review_calibration.jsonl")]
    assert tuple(item.case_id for item in records) == AUTHORIZED_ORDER
    assert [item.review_order for item in records] == list(range(1, 7))
    assert all(Path(item.packet_path).is_file() for item in records)
    assert all(item.decision_status == "unreviewed" for item in records)
    assert not any(item.case_id.startswith("RESERVE_") for item in records)


def test_calibration_decisions_are_six_blank_unreviewed_records() -> None:
    decisions = [
        ReviewDecisionTemplate.model_validate(item)
        for item in _jsonl("review_decisions.calibration.template.jsonl")
    ]
    assert tuple(item.case_id for item in decisions) == AUTHORIZED_ORDER
    assert all(item.decision_status == item.sufficiency_label == "unreviewed" for item in decisions)
    assert all(not item.required_aspects and not item.gold_evidence_groups for item in decisions)
    assert all(not item.supported_aspects and not item.missing_aspects for item in decisions)


def test_reserves_are_inactive_and_new_cases_have_no_gold_or_split() -> None:
    reserves = _jsonl("master_case_reserves.jsonl")
    assert len(reserves) == 8
    assert {item["case_id"] for item in reserves[-2:]} == {"RESERVE_007", "RESERVE_008"}
    forbidden = {
        "gold_segment_ids", "gold_evidence_groups", "sufficiency_label",
        "supported_aspects", "missing_aspects", "final_reason_codes", "split",
        "activation_reason", "activated_at", "authorized_by",
    }
    for item in reserves:
        MasterCaseCandidate.model_validate(item)
        assert not forbidden & set(item)


def test_new_unverifiable_reserves_have_real_frozen_provenance() -> None:
    summary = validate_calibration_assets()
    assert summary == {
        "active_cases": 6,
        "blank_calibration_decisions": 6,
        "inactive_reserves": 8,
        "new_unverifiable_reserves": 2,
    }


def test_protocol_contains_all_governing_corrections() -> None:
    protocol = Path("V3_5_EVAL_PROTOCOL_DRAFT.md").read_text(encoding="utf-8")
    for phrase in (
        "Full Transcript Accessible ≠ Full Transcript Linearly Read From Start to End",
        "not exhaustive proofs",
        "English-source positive evidence: not established",
        "Cross-language evidence resolution: not evaluated",
        "Reserve candidates are inactive by default",
        "Round 1: 6-case Label Calibration",
        "Round 2: Remaining necessary Primary Cases",
        "Round 3: Targeted Reserve Activation only when required",
    ):
        assert phrase in protocol


def test_original_template_and_existing_packet_hashes_are_unchanged() -> None:
    assert sha256((ROOT / "review_decisions.template.jsonl").read_bytes()).hexdigest() == (
        "8580ce39cb93989dc4dec21ea0c213ae0a5367820e5c061ff568a6cd5b3f88ee"
    )
    manifest = json.loads((ROOT / "review_packet_manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["packets"]:
        packet = Path(entry["packet_path"])
        assert sha256(packet.read_bytes()).hexdigest() == entry["sha256"]
    assert len(manifest["packets"]) == 28
    summary = validate_review_assets()
    assert summary.packet_count == 28 and summary.total_transcript_segments == 8626
