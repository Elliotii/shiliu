from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic import ValidationError

from shiliu.evidence.stage3a import EvidenceBundle
from shiliu.evidence.stage4 import MechanicalGateDecision, SufficiencyRequest
from shiliu.eval_v3_5.stage4b import (
    SEMANTIC_POLICY_VERSION,
    SemanticJudgeOutput,
    project_runtime_request,
    validate_output,
)


def request() -> SufficiencyRequest:
    return SufficiencyRequest(
        request_id="request_1",
        query_id="Q1",
        original_query="What is supported?",
        evaluation_track="frozen_v3_end_to_end",
        end_to_end_claim_eligible=True,
        search_candidate_set_id="search_1",
        evidence_candidate_set_id="set_1",
        evidence_bundle_id="bundle_1",
        evidence_resolution_status="resolved",
        failure_attribution=None,
        candidate_builder_version="stage3b-acronym-w3.5-v1",
        selector_version="v3.5-deterministic-fine-selector-v1",
        source_states=("valid",),
        source_languages=("en",),
        trace_id="trace_1",
    )


def bundle() -> EvidenceBundle:
    return EvidenceBundle(
        bundle_id="bundle_1",
        query_id="Q1",
        video_id=1,
        source_artifact_ids=("source_1",),
        source_versions=("a" * 64,),
        timeline_run_ids=("timeline_1",),
        candidate_ids=("e1",),
        normalized_spans=(
            {
                "candidate_id": "e1",
                "segment_ids": ["segment_1"],
                "timeline_run_id": "timeline_1",
                "start_time": 0,
                "end_time": 1,
            },
        ),
        union_duration=1,
        source_texts=("authoritative text",),
        selection_method="v3.5-deterministic-fine-selector-v1",
        score=1,
        score_breakdown={},
        evaluation_track="frozen_v3_end_to_end",
        end_to_end_claim_eligible=True,
        trace_id="trace_1",
        normalization_status="valid",
        validation_errors=(),
    )


def gate(outcome: str = "judge_eligible") -> MechanicalGateDecision:
    eligible = outcome == "judge_eligible"
    return MechanicalGateDecision(
        gate_decision_id="gate_1",
        gate_outcome=outcome,
        terminal_status=None if eligible else "source_unverifiable",
        operational_reason_code=None if eligible else "source_unreadable",
        action_family="none" if eligible else "source_recovery_action",
        semantic_judge_required=eligible,
        query_id="Q1",
        evaluation_track="frozen_v3_end_to_end",
        end_to_end_claim_eligible=True,
        search_candidate_set_id="search_1",
        evidence_candidate_set_id="set_1",
        evidence_bundle_id="bundle_1",
        evidence_ids_used=("e1",) if eligible else (),
        mechanical_gate_policy_version="v3.5-mechanical-gate-policy-v1",
        candidate_builder_version="stage3b-acronym-w3.5-v1",
        selector_version="v3.5-deterministic-fine-selector-v1",
        trace_id="trace_1",
        validation_errors=(),
    )


@pytest.mark.parametrize(
    ("status", "supported", "missing", "blocker"),
    [
        ("sufficient", ("need",), (), None),
        ("partial", ("need",), ("gap",), None),
        ("insufficient", (), ("main answer",), None),
        ("unverifiable", (), (), "authoritative text is unreadable"),
    ],
)
def test_four_state_boundaries(status, supported, missing, blocker) -> None:
    value = SemanticJudgeOutput(
        query_id="Q1",
        status=status,
        supported_aspects=supported,
        missing_aspects=missing,
        conflicts=(),
        reason_codes=(
            {
                "sufficient": "SJ_ALL_MATERIAL_NEEDS_SUPPORTED",
                "partial": "SJ_MEANINGFUL_SUBSET_WITH_MATERIAL_GAP",
                "insufficient": "SJ_REVIEWABLE_WITHOUT_USABLE_MAIN_ANSWER",
                "unverifiable": "SJ_AUTHORITATIVE_VERIFICATION_BLOCKED",
            }[status],
        ),
        confidence=0.8,
        evidence_ids_used=("e1",) if status in {"sufficient", "partial"} else (),
        verification_blocker=blocker,
        trace_id="trace_1",
    )
    validate_output(value, request(), bundle())


def test_missing_material_aspect_cannot_be_sufficient() -> None:
    with pytest.raises(ValidationError):
        SemanticJudgeOutput(
            query_id="Q1", status="sufficient", supported_aspects=("a",),
            missing_aspects=("b",), conflicts=(),
            reason_codes=("SJ_ALL_MATERIAL_NEEDS_SUPPORTED",), confidence=.8,
            evidence_ids_used=("e1",), trace_id="trace_1",
        )


def test_weak_related_evidence_cannot_be_partial_without_meaningful_support() -> None:
    with pytest.raises(ValidationError):
        SemanticJudgeOutput(
            query_id="Q1", status="partial", supported_aspects=(),
            missing_aspects=("main answer",), conflicts=(),
            reason_codes=("SJ_MEANINGFUL_SUBSET_WITH_MATERIAL_GAP",), confidence=.8,
            evidence_ids_used=(), trace_id="trace_1",
        )


def test_insufficient_cannot_be_mislabeled_unverifiable() -> None:
    with pytest.raises(ValidationError):
        SemanticJudgeOutput(
            query_id="Q1", status="unverifiable", supported_aspects=(),
            missing_aspects=("main answer",), conflicts=(),
            reason_codes=("SJ_AUTHORITATIVE_VERIFICATION_BLOCKED",), confidence=.8,
            evidence_ids_used=(), verification_blocker=None, trace_id="trace_1",
        )


def test_invented_evidence_id_rejected() -> None:
    output = SemanticJudgeOutput(
        query_id="Q1", status="sufficient", supported_aspects=("a",),
        missing_aspects=(), conflicts=(),
        reason_codes=("SJ_ALL_MATERIAL_NEEDS_SUPPORTED",), confidence=.8,
        evidence_ids_used=("invented",), verification_blocker=None, trace_id="trace_1",
    )
    with pytest.raises(ValueError, match="invented"):
        validate_output(output, request(), bundle())


def test_trace_propagation_and_cross_language_projection() -> None:
    projected = project_runtime_request(request(), gate(), bundle(), query_language="zh")
    assert projected.trace_id == "trace_1"
    assert projected.query_language == "zh"
    assert projected.source_languages == ("en",)
    assert projected.policy_version == SEMANTIC_POLICY_VERSION


def test_mechanical_source_unverifiable_bypasses_judge() -> None:
    with pytest.raises(ValueError, match="bypass"):
        project_runtime_request(request(), gate("source_unverifiable"), bundle(), query_language="en")
