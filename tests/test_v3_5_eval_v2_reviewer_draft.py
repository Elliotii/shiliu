from __future__ import annotations

import json
from pathlib import Path

from shiliu.eval_v3_5.eval_v2.contracts import AnnotationPacketV2
from shiliu.eval_v3_5.eval_v2.reviewer_draft import ReviewerDraft, validate_reviewer_draft


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "research/v3_5/eval_v2/stage2r_a/fixtures/annotation_packet.synthetic.v2.json"


def packet() -> AnnotationPacketV2:
    return AnnotationPacketV2.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


def valid_draft() -> dict[str, object]:
    return {
        "status": "sufficient",
        "required_aspects": [
            {"text": "condition alpha", "query_anchor_texts": ["condition"]},
            {"text": "condition beta", "query_anchor_texts": ["condition"]},
        ],
        "supported_aspect_indices": [0, 1],
        "missing_aspect_indices": [],
        "required_spans": [
            {"segment_ids": ["seg_1"], "supported_aspect_indices": [0]},
            {"segment_ids": ["seg_2"], "supported_aspect_indices": [1]},
        ],
        "optional_context_spans": [{"segment_ids": ["seg_3"]}],
        "evidence_groups": [
            {"required_aspect_indices": [0, 1], "required_span_indices": [0, 1]}
        ],
        "reason_codes": [],
        "conflict_notes": "",
        "confidence": "high",
        "boundary_notes": [],
    }


def test_model_facing_draft_is_index_only() -> None:
    draft = ReviewerDraft.model_validate(valid_draft())
    schema = json.dumps(ReviewerDraft.model_json_schema())
    assert draft.supported_aspect_indices == (0, 1)
    assert "aspect_id" not in schema
    assert "span_id" not in schema
    assert "group_id" not in schema


def test_out_of_range_indices_are_rejected() -> None:
    raw = valid_draft()
    raw["supported_aspect_indices"] = [0, 2]
    result = validate_reviewer_draft(raw, packet())
    assert result.status == "invalid"
    assert "out_of_range_supported_aspect_index:2" in result.errors


def test_unknown_packet_segment_is_rejected() -> None:
    raw = valid_draft()
    raw["required_spans"] = [
        {"segment_ids": ["seg_missing"], "supported_aspect_indices": [0, 1]}
    ]
    raw["evidence_groups"] = [
        {"required_aspect_indices": [0, 1], "required_span_indices": [0]}
    ]
    result = validate_reviewer_draft(raw, packet())
    assert result.status == "invalid"
    assert any(error.startswith("unknown_segment_id:") for error in result.errors)


def test_status_and_aspect_partition_must_agree() -> None:
    raw = valid_draft()
    raw["status"] = "partial"
    result = validate_reviewer_draft(raw, packet())
    assert result.status == "invalid"
    assert "illegal_partial_state" in result.errors


def test_group_without_required_span_is_rejected() -> None:
    raw = valid_draft()
    raw["evidence_groups"] = [
        {"required_aspect_indices": [0, 1], "required_span_indices": []}
    ]
    result = validate_reviewer_draft(raw, packet())
    assert result.status == "invalid"
    assert any("required_span_indices" in error for error in result.errors)
