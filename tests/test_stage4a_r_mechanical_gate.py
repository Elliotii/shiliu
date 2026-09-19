from __future__ import annotations

import math

import pytest

from shiliu.evidence.stage3a import DETERMINISTIC_SELECTOR_VERSION, EvidenceBundle
from shiliu.evidence.stage4 import FINAL_CANDIDATE_BUILDER_VERSION
from shiliu.evidence.stage4 import (
    EvidenceResolutionState,
    SufficiencyRequest,
    apply_mechanical_sufficiency_gate,
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
        normalized_spans=({
            "candidate_id": "evidence_1", "timeline_run_id": "run_1",
            "start_time": 1.0, "end_time": 2.0, "segment_ids": ["segment_1"],
        },),
        union_duration=1.0, source_texts=("raw-derived",),
        selection_method=DETERMINISTIC_SELECTOR_VERSION, score=1.0, score_breakdown={},
        evaluation_track="frozen_v3_end_to_end", end_to_end_claim_eligible=True,
        trace_id="trace_bundle", normalization_status="valid", validation_errors=(),
    )
    values.update(changes)
    return EvidenceBundle(**values)


@pytest.mark.parametrize("reason", [
    "no_supported_subtitle",
    "raw_source_unavailable",
    "source_unreadable",
])
def test_authoritative_source_failures_are_source_unverifiable(reason: str) -> None:
    gate = apply_mechanical_sufficiency_gate(
        request(evidence_bundle_id=None, evidence_resolution_status="failed", failure_attribution=reason),
        state(
            status="failed", operational_reason_code=reason, evidence_bundle_id=None,
            available_evidence_candidate_ids=(), evidence_ids_raw_derived=False,
            source_integrity_valid=False,
        ),
        None,
    )
    assert gate.gate_outcome == "source_unverifiable"
    assert gate.terminal_status == "source_unverifiable"
    assert not gate.semantic_judge_required


@pytest.mark.parametrize("changed,error", [
    ({"candidate_ids": ("evidence_1", "evidence_1")}, "duplicate_or_conflicting_evidence_id"),
    ({"source_versions": ()}, "missing_or_invalid_source_version"),
    ({"timeline_run_ids": ()}, "missing_timeline_run_id"),
    ({"source_texts": ("",)}, "missing_authoritative_source_text"),
    ({"normalized_spans": ()}, "missing_evidence_span"),
    ({
        "normalized_spans": ({
            "candidate_id": "evidence_1", "timeline_run_id": "run_1",
            "start_time": -1.0, "end_time": 2.0, "segment_ids": ["segment_1"],
        },),
    }, "invalid_temporal_interval"),
    ({
        "normalized_spans": ({
            "candidate_id": "evidence_1", "timeline_run_id": "wrong",
            "start_time": 1.0, "end_time": 2.0, "segment_ids": ["segment_1"],
        },),
    }, "missing_or_conflicting_timeline_run_id"),
    ({
        "normalized_spans": ({
            "candidate_id": "evidence_1", "timeline_run_id": "run_1",
            "start_time": 1.0, "end_time": 2.0, "segment_ids": [],
        },),
    }, "empty_or_unresolvable_segment_ids"),
])
def test_malformed_bundle_is_invalid(changed: dict[str, object], error: str) -> None:
    gate = apply_mechanical_sufficiency_gate(request(), state(), bundle(**changed))
    assert gate.gate_outcome == "invalid"
    assert gate.terminal_status == "invalid"
    assert error in gate.validation_errors
    assert not gate.semantic_judge_required


def test_unresolved_candidate_lineage_is_invalid() -> None:
    gate = apply_mechanical_sufficiency_gate(
        request(),
        state(available_evidence_candidate_ids=("different",)),
        bundle(),
    )
    assert gate.gate_outcome == "invalid"
    assert "unresolved_candidate_to_segment_lineage" in gate.validation_errors


def test_same_input_has_same_exclusive_status_and_reason_codes() -> None:
    first = apply_mechanical_sufficiency_gate(request(), state(), bundle())
    second = apply_mechanical_sufficiency_gate(request(), state(), bundle())
    assert first == second
    assert first.gate_outcome == "judge_eligible"
    assert first.terminal_status is None
    assert first.validation_errors == ()


def test_gate_does_not_populate_semantic_sufficiency_fields() -> None:
    properties = set(type(apply_mechanical_sufficiency_gate(request(), state(), bundle())).model_fields)
    assert not properties & {
        "status", "supported_aspects", "missing_aspects", "conflicts",
        "semantic_reason_code", "confidence",
    }


def test_invalid_non_finite_interval_is_contained() -> None:
    malformed = bundle(normalized_spans=({
        "candidate_id": "evidence_1", "timeline_run_id": "run_1",
        "start_time": 1.0, "end_time": math.inf, "segment_ids": ["segment_1"],
    },))
    gate = apply_mechanical_sufficiency_gate(request(), state(), malformed)
    assert gate.gate_outcome == "invalid"
    assert "invalid_temporal_interval" in gate.validation_errors


def test_request_and_state_contracts_remain_strict() -> None:
    with pytest.raises(Exception):
        SufficiencyRequest(**{**request().model_dump(), "unknown": True})
    with pytest.raises(Exception):
        EvidenceResolutionState(**{**state().model_dump(), "unknown": True})
