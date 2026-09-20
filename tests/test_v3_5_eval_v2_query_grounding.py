from __future__ import annotations

from pathlib import Path

from shiliu.eval_v3_5.eval_v2.canary import build_canary_packet
from shiliu.eval_v3_5.eval_v2.query_grounding import validate_query_grounding
from shiliu.eval_v3_5.eval_v2.reviewer_draft import ReviewerDraft
from test_v3_5_eval_v2_canary import spec


def test_anchor_must_be_exact_evidence_question_substring(tmp_path: Path) -> None:
    packet = build_canary_packet(spec(tmp_path))
    draft = ReviewerDraft.model_validate(
        {
            "status": "insufficient",
            "required_aspects": [
                {"text": "conditions are explained", "query_anchor_texts": ["Conditions"]}
            ],
            "supported_aspect_indices": [],
            "missing_aspect_indices": [0],
            "required_spans": [],
            "optional_context_spans": [],
            "evidence_groups": [],
            "reason_codes": [],
            "confidence": "high",
        }
    )
    result = validate_query_grounding(draft, packet)
    assert result.status == "query_grounding_invalid"
    assert any(error.startswith("anchor_not_evidence_question_substring") for error in result.errors)


def test_supported_aspect_with_no_span_lexical_link_is_warning(tmp_path: Path) -> None:
    packet = build_canary_packet(spec(tmp_path))
    draft = ReviewerDraft.model_validate(
        {
            "status": "sufficient",
            "required_aspects": [
                {"text": "conditions are explained", "query_anchor_texts": ["conditions"]}
            ],
            "supported_aspect_indices": [0],
            "missing_aspect_indices": [],
            "required_spans": [
                {"segment_ids": ["BVTEST_seg_000001"], "supported_aspect_indices": [0]}
            ],
            "optional_context_spans": [],
            "evidence_groups": [
                {"required_aspect_indices": [0], "required_span_indices": [0]}
            ],
            "reason_codes": [],
            "confidence": "medium",
        }
    )
    result = validate_query_grounding(draft, packet)
    assert result.status == "query_grounding_warning"


def test_anchor_binding_tolerates_spacing_without_weakening_exact_anchor_rule(tmp_path: Path) -> None:
    case = spec(tmp_path)
    case = case.__class__(
        **{
            **case.__dict__,
            "query": "哪个视频解释了 CLI 相比 MCP 的优势？",
            "evidence_question": "该视频的完整原字幕是否实质解释了 CLI 相比 MCP 的优势？",
        }
    )
    packet = build_canary_packet(case)
    draft = ReviewerDraft.model_validate(
        {
            "status": "insufficient",
            "required_aspects": [
                {
                    "text": "该视频解释了CLI相比MCP的优势",
                    "query_anchor_texts": ["CLI 相比 MCP 的优势"],
                }
            ],
            "supported_aspect_indices": [],
            "missing_aspect_indices": [0],
            "required_spans": [],
            "optional_context_spans": [],
            "evidence_groups": [],
            "reason_codes": [],
            "confidence": "high",
        }
    )
    assert validate_query_grounding(draft, packet).status == "valid"
