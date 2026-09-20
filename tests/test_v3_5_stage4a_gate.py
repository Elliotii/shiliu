from __future__ import annotations

from dataclasses import replace
import json

import pytest
from pydantic import ValidationError

from shiliu.evidence.stage3a import DETERMINISTIC_SELECTOR_VERSION, EvidenceBundle
from shiliu.evidence.stage4 import (
    FINAL_CANDIDATE_BUILDER_VERSION, EvidenceResolutionState, MechanicalGatePolicy,
    SufficiencyRequest, apply_mechanical_sufficiency_gate, canonical_bytes,
    terminal_sufficiency_decision,
)


def request(**changes):
    values = dict(
        request_id="request_x", query_id="QUERY_1", original_query="query",
        evaluation_track="frozen_v3_end_to_end", end_to_end_claim_eligible=True,
        search_candidate_set_id="search_1", evidence_candidate_set_id="cset_1",
        evidence_bundle_id="bundle_1", evidence_resolution_status="resolved",
        failure_attribution=None, candidate_builder_version=FINAL_CANDIDATE_BUILDER_VERSION,
        selector_version=DETERMINISTIC_SELECTOR_VERSION, source_states=("valid",),
        source_languages=("zh",), trace_id="trace_1",
    )
    values.update(changes)
    return SufficiencyRequest(**values)


def state(**changes):
    values = dict(
        status="resolved", search_candidate_set_id="search_1", evidence_candidate_set_id="cset_1",
        evidence_bundle_id="bundle_1", available_evidence_candidate_ids=("evidence_1",),
        evidence_ids_raw_derived=True, source_integrity_valid=True,
    )
    values.update(changes)
    return EvidenceResolutionState(**values)


def bundle(**changes):
    values = dict(
        bundle_id="bundle_1", query_id="QUERY_1", video_id=1,
        source_artifact_ids=("artifact_1",), source_versions=("a" * 64,),
        timeline_run_ids=("run_1",), candidate_ids=("evidence_1",),
        normalized_spans=({"candidate_id": "evidence_1", "timeline_run_id": "run_1", "start_time": 1.0, "end_time": 2.0, "segment_ids": ["segment_1"]},),
        union_duration=1.0, source_texts=("raw-derived",),
        selection_method=DETERMINISTIC_SELECTOR_VERSION, score=1.0, score_breakdown={},
        evaluation_track="frozen_v3_end_to_end", end_to_end_claim_eligible=True,
        trace_id="trace_bundle", normalization_status="valid", validation_errors=(),
    )
    values.update(changes)
    return EvidenceBundle(**values)


def test_valid_bundle_is_judge_eligible_and_stage4a_emits_no_final_status() -> None:
    gate = apply_mechanical_sufficiency_gate(request(), state(), bundle(), MechanicalGatePolicy())
    assert gate.gate_outcome == "judge_eligible"
    assert gate.terminal_status is None and gate.semantic_judge_required is True
    assert gate.operational_reason_code is None and gate.action_family == "none"
    with pytest.raises(ValueError, match="only source-unverifiable"):
        terminal_sufficiency_decision(gate)


@pytest.mark.parametrize("reason,action", [
    ("upstream_retrieval_failure", "retrieval_action"),
    ("no_search_candidate", "retrieval_action"),
    ("candidate_generation_failure", "evidence_resolution_action"),
    ("selector_failure", "selector_recovery_action"),
    ("raw_source_unavailable", "source_recovery_action"),
    ("no_supported_subtitle", "source_recovery_action"),
    ("title_only", "source_recovery_action"),
    ("source_unreadable", "source_recovery_action"),
    ("source_version_mismatch", "data_integrity_action"),
    ("language_unresolved", "source_recovery_action"),
    ("normalization_failure", "data_integrity_action"),
])
def test_operational_failures_are_terminal_and_not_insufficient(reason: str, action: str) -> None:
    gate = apply_mechanical_sufficiency_gate(
        request(evidence_bundle_id=None, evidence_resolution_status="failed", failure_attribution=reason),
        state(status="failed", operational_reason_code=reason, evidence_bundle_id=None,
              available_evidence_candidate_ids=(), evidence_ids_raw_derived=False, source_integrity_valid=False),
        None,
    )
    expected = (
        "source_unverifiable"
        if reason in {
            "upstream_retrieval_failure", "no_search_candidate", "raw_source_unavailable",
            "no_supported_subtitle", "title_only", "source_unreadable", "language_unresolved",
        }
        else "invalid"
    )
    assert gate.gate_outcome == expected and gate.action_family == action
    if expected == "source_unverifiable":
        decision = terminal_sufficiency_decision(gate)
        assert decision.status == "unverifiable" and decision.semantic_reason_code is None
        assert decision.semantic_judge_invoked is False
    else:
        with pytest.raises(ValueError, match="only source-unverifiable"):
            terminal_sufficiency_decision(gate)


@pytest.mark.parametrize("request_changes,state_changes,bundle_changes,error", [
    ({}, {}, {"validation_errors": ("bad",)}, "invalid_evidence_bundle"),
    ({}, {}, {"normalization_status": "invalid"}, "invalid_evidence_bundle"),
    ({}, {}, {"candidate_ids": ("missing",)}, "invalid_evidence_bundle"),
    ({"selector_version": "wrong"}, {}, {}, "selector_failed"),
    ({"candidate_builder_version": "wrong"}, {}, {}, "execution_manifest_mismatch"),
    ({"search_candidate_set_id": "wrong"}, {}, {}, "search_candidate_set_mismatch"),
])
def test_invalid_bundle_and_version_identity_fail_closed(request_changes, state_changes, bundle_changes, error) -> None:
    gate = apply_mechanical_sufficiency_gate(request(**request_changes), state(**state_changes), bundle(**bundle_changes))
    assert gate.gate_outcome == "invalid"
    assert gate.operational_reason_code == error


def test_stable_identity_serialization_and_ordering() -> None:
    first = apply_mechanical_sufficiency_gate(request(), state(), bundle())
    second = apply_mechanical_sufficiency_gate(request(), state(), bundle())
    assert first.gate_decision_id == second.gate_decision_id
    assert canonical_bytes(first) == canonical_bytes(second)
    assert json.loads(canonical_bytes(first))["trace_id"] == "trace_1"


def test_contracts_are_strict_and_oracle_claim_is_false() -> None:
    with pytest.raises(ValidationError):
        SufficiencyRequest(**{**request().model_dump(), "case_id": "CASE_001"})
    with pytest.raises(ValidationError):
        SufficiencyRequest(**{**request().model_dump(), "evaluation_track": "wrong"})
    with pytest.raises(ValidationError):
        request(evaluation_track="oracle_video_conditional", end_to_end_claim_eligible=True)
    assert "case_id" not in SufficiencyRequest.model_json_schema()["properties"]
    assert not any("gold" in key.lower() for key in SufficiencyRequest.model_json_schema()["properties"])
