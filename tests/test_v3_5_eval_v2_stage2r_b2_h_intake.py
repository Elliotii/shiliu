from __future__ import annotations

import copy

import pytest

from shiliu.eval_v3_5.eval_v2.stage2r_b2_h_intake import (
    RemainingPilotDecisionError,
    _apply_patch,
    _load_decisions,
    expand_decisions,
)


def test_user_decisions_are_exact_two_case_simplified_jsonl() -> None:
    rows = _load_decisions()
    assert [row["case_id"] for row in rows] == ["V2C_B2P00001", "V2C_B2P00002"]
    assert [row["human_action"] for row in rows] == [
        "approve_primary", "merge_and_revise"
    ]


def test_decisions_expand_deterministically() -> None:
    records = expand_decisions()
    first, second = records
    assert first["final_status"] == "insufficient"
    assert first["final_reason_codes"] == ["TOPIC_NOT_SUBSTANTIALLY_DISCUSSED"]
    assert first["final_evidence_groups"] == []
    assert first["final_required_spans"] == []
    assert second["base_review"] == "secondary"
    assert second["final_status"] == "insufficient"
    assert second["final_supported_aspects"] == []
    assert second["final_missing_aspects"] == ["A1"]
    assert second["final_evidence_groups"] == []
    assert second["final_required_spans"] == []
    assert second["final_reason_codes"] == ["TOPIC_NOT_SUBSTANTIALLY_DISCUSSED"]
    assert second["final_required_aspects"] == [
        {"aspect_id": "A1", "description": "视频的完整原字幕是否实质讨论 vibe coding。"}
    ]


def test_patch_rejects_unapproved_or_unknown_mutations() -> None:
    value = {
        "final_status": "insufficient",
        "final_required_aspects": [{"aspect_id": "A1", "description": "x"}],
        "final_required_spans": [],
        "final_evidence_groups": [],
        "final_reason_codes": [],
        "final_boundary_notes": [],
    }
    with pytest.raises(RemainingPilotDecisionError, match="unsupported_patch_keys"):
        _apply_patch("case", copy.deepcopy(value), {"full_canonical_review": {}})
    with pytest.raises(RemainingPilotDecisionError, match="aspect_replacement_target_invalid"):
        _apply_patch(
            "case",
            copy.deepcopy(value),
            {"replace_required_aspect_text": {"aspect_id": "A2", "description": "y"}},
        )
