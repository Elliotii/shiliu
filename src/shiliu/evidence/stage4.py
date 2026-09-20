from __future__ import annotations

from hashlib import sha256
import json
import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shiliu.evidence.stage3a import (
    DETERMINISTIC_SELECTOR_VERSION,
    EVIDENCE_BUNDLE_CONTRACT_VERSION,
    EvidenceBundle,
)


SUFFICIENCY_REQUEST_CONTRACT_VERSION = "v3.5-sufficiency-request-v1"
MECHANICAL_GATE_CONTRACT_VERSION = "v3.5-mechanical-sufficiency-gate-v1"
SUFFICIENCY_DECISION_CONTRACT_VERSION = "v3.5-sufficiency-decision-v1"
MECHANICAL_GATE_POLICY_VERSION = "v3.5-mechanical-gate-policy-v1"
FINAL_CANDIDATE_BUILDER_VERSION = "stage3b-acronym-w3.5-v1"

OperationalReason = Literal[
    "upstream_retrieval_failure", "no_search_candidate", "candidate_generation_failure",
    "selector_failed", "raw_source_unavailable", "no_supported_subtitle", "title_only",
    "source_unreadable", "source_version_mismatch", "language_unresolved",
    "normalization_failure", "invalid_evidence_bundle", "execution_manifest_mismatch",
    "search_candidate_set_mismatch", "unknown_operational_state",
]
ActionFamily = Literal[
    "retrieval_action", "evidence_resolution_action", "selector_recovery_action",
    "source_recovery_action", "data_integrity_action", "none",
]

REASON_ACTION: dict[str, str] = {
    "upstream_retrieval_failure": "retrieval_action",
    "no_search_candidate": "retrieval_action",
    "candidate_generation_failure": "evidence_resolution_action",
    "selector_failed": "selector_recovery_action",
    "raw_source_unavailable": "source_recovery_action",
    "no_supported_subtitle": "source_recovery_action",
    "title_only": "source_recovery_action",
    "source_unreadable": "source_recovery_action",
    "source_version_mismatch": "data_integrity_action",
    "language_unresolved": "source_recovery_action",
    "normalization_failure": "data_integrity_action",
    "invalid_evidence_bundle": "data_integrity_action",
    "execution_manifest_mismatch": "data_integrity_action",
    "search_candidate_set_mismatch": "data_integrity_action",
    "unknown_operational_state": "data_integrity_action",
}
REASON_ALIASES = {
    "selector_failure": "selector_failed", "no_selected_bundle": "selector_failed",
    "selector_abstain": "selector_failed", "invalid_bundle_reference": "selector_failed",
}
SOURCE_UNVERIFIABLE_REASONS = frozenset({
    "upstream_retrieval_failure", "no_search_candidate", "raw_source_unavailable",
    "no_supported_subtitle", "title_only", "source_unreadable", "language_unresolved",
})


def canonical_bytes(value: object) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def stable_id(prefix: str, value: object) -> str:
    return prefix + sha256(canonical_bytes(value)).hexdigest()


class SufficiencyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sufficiency_request_contract_version: Literal["v3.5-sufficiency-request-v1"] = SUFFICIENCY_REQUEST_CONTRACT_VERSION
    request_id: str
    query_id: str
    original_query: str
    evaluation_track: Literal[
        "frozen_v3_end_to_end", "oracle_video_conditional", "approved_evidence_diagnostic"
    ]
    end_to_end_claim_eligible: bool
    search_candidate_set_id: str
    evidence_candidate_set_id: str | None
    evidence_bundle_id: str | None
    evidence_resolution_status: str
    failure_attribution: str | None
    candidate_builder_version: str
    selector_version: str
    source_states: tuple[str, ...]
    source_languages: tuple[str, ...]
    trace_id: str
    # Stage 4B additive compatibility fields. Defaults preserve every Stage 4A
    # caller while allowing the existing Request contract to carry the complete
    # semantic-judge runtime projection.
    query_language: str = "und"
    evidence_bundle: dict[str, object] | None = None
    mechanical_gate_status: str | None = None
    policy_version: str | None = None

    @model_validator(mode="after")
    def validate_track(self) -> "SufficiencyRequest":
        if self.evaluation_track == "oracle_video_conditional" and self.end_to_end_claim_eligible:
            raise ValueError("oracle-video requests cannot make end-to-end claims")
        return self


class EvidenceResolutionState(BaseModel):
    """Already-resolved runtime facts; never reads source, database, selector, or Gold."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    status: str
    operational_reason_code: str | None = None
    search_candidate_set_id: str
    evidence_candidate_set_id: str | None = None
    evidence_bundle_id: str | None = None
    available_evidence_candidate_ids: tuple[str, ...] = ()
    evidence_ids_raw_derived: bool = False
    source_integrity_valid: bool = False
    validation_errors: tuple[str, ...] = ()


class MechanicalGatePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    mechanical_gate_policy_version: Literal["v3.5-mechanical-gate-policy-v1"] = MECHANICAL_GATE_POLICY_VERSION
    supported_bundle_contract_version: Literal["v3.5-evidence-bundle-v1"] = EVIDENCE_BUNDLE_CONTRACT_VERSION
    required_candidate_builder_version: Literal["stage3b-acronym-w3.5-v1"] = FINAL_CANDIDATE_BUILDER_VERSION
    required_selector_version: Literal["v3.5-deterministic-fine-selector-v1"] = DETERMINISTIC_SELECTOR_VERSION


class MechanicalGateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mechanical_gate_contract_version: Literal["v3.5-mechanical-sufficiency-gate-v1"] = MECHANICAL_GATE_CONTRACT_VERSION
    gate_decision_id: str
    gate_outcome: Literal["judge_eligible", "source_unverifiable", "invalid"]
    terminal_status: Literal["source_unverifiable", "invalid"] | None
    operational_reason_code: OperationalReason | None
    action_family: ActionFamily
    semantic_judge_required: bool
    query_id: str
    evaluation_track: Literal[
        "frozen_v3_end_to_end", "oracle_video_conditional", "approved_evidence_diagnostic"
    ]
    end_to_end_claim_eligible: bool
    search_candidate_set_id: str
    evidence_candidate_set_id: str | None
    evidence_bundle_id: str | None
    evidence_ids_used: tuple[str, ...]
    mechanical_gate_policy_version: Literal["v3.5-mechanical-gate-policy-v1"]
    candidate_builder_version: str
    selector_version: str
    trace_id: str
    validation_errors: tuple[str, ...]

    @model_validator(mode="after")
    def consistency(self) -> "MechanicalGateDecision":
        if self.gate_outcome == "judge_eligible":
            if self.terminal_status is not None or self.operational_reason_code is not None:
                raise ValueError("judge-eligible decision cannot be terminal")
            if self.action_family != "none" or not self.semantic_judge_required or not self.evidence_ids_used:
                raise ValueError("judge-eligible decision requires valid evidence and semantic judge")
        elif (
            self.terminal_status != self.gate_outcome
            or self.operational_reason_code is None
            or self.action_family == "none"
            or self.semantic_judge_required
            or self.evidence_ids_used
        ):
            raise ValueError("terminal decision consistency violation")
        return self


class SufficiencyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sufficiency_decision_contract_version: Literal["v3.5-sufficiency-decision-v1"] = SUFFICIENCY_DECISION_CONTRACT_VERSION
    decision_id: str
    status: Literal["sufficient", "partial", "insufficient", "unverifiable"]
    supported_aspects: tuple[str, ...]
    missing_aspects: tuple[str, ...]
    conflicts: tuple[str, ...]
    operational_reason_code: OperationalReason | None
    semantic_reason_code: str | None
    action_family: ActionFamily
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_bundle_id: str | None
    evidence_ids_used: tuple[str, ...]
    mechanical_gate_applied: bool
    semantic_judge_invoked: bool
    policy_version: str
    judge_contract_version: str | None
    judge_prompt_version: str | None
    judge_model: str | None
    evaluation_track: Literal[
        "frozen_v3_end_to_end", "oracle_video_conditional", "approved_evidence_diagnostic"
    ]
    end_to_end_claim_eligible: bool
    trace_id: str
    validation_errors: tuple[str, ...]
    # Additive alias-free collection for semantic policy reasons. The existing
    # operational_reason_code and semantic_reason_code fields remain authoritative.
    reason_codes: tuple[str, ...] = ()


def _reason(value: str | None) -> OperationalReason:
    normalized = REASON_ALIASES.get(value or "", value or "unknown_operational_state")
    if normalized not in REASON_ACTION:
        normalized = "unknown_operational_state"
    return normalized  # type: ignore[return-value]


def _decision_id(request: SufficiencyRequest, outcome: str, reason: str | None, action: str) -> str:
    return stable_id("gate_", {
        "mechanical_gate_contract_version": MECHANICAL_GATE_CONTRACT_VERSION,
        "query_id": request.query_id, "evaluation_track": request.evaluation_track,
        "search_candidate_set_id": request.search_candidate_set_id,
        "evidence_candidate_set_id": request.evidence_candidate_set_id,
        "evidence_bundle_id": request.evidence_bundle_id, "gate_outcome": outcome,
        "operational_reason_code": reason, "action_family": action,
        "mechanical_gate_policy_version": MECHANICAL_GATE_POLICY_VERSION,
    })


def _bundle_contract_errors(
    request: SufficiencyRequest,
    state: EvidenceResolutionState,
    bundle: EvidenceBundle,
) -> list[str]:
    """Validate only mechanical bundle structure; never infer semantic sufficiency."""

    errors: list[str] = []
    candidate_ids = list(bundle.candidate_ids)
    if not candidate_ids or any(not value for value in candidate_ids):
        errors.append("empty_evidence_ids")
    if len(candidate_ids) != len(set(candidate_ids)):
        errors.append("duplicate_or_conflicting_evidence_id")
    if not bundle.source_artifact_ids or any(not value for value in bundle.source_artifact_ids):
        errors.append("missing_source_artifact_id")
    if (
        not bundle.source_versions
        or any(not value or re.fullmatch(r"[0-9a-f]{64}", value) is None for value in bundle.source_versions)
    ):
        errors.append("missing_or_invalid_source_version")
    if not bundle.timeline_run_ids or any(not value for value in bundle.timeline_run_ids):
        errors.append("missing_timeline_run_id")
    if not isinstance(bundle.video_id, int) or isinstance(bundle.video_id, bool) or bundle.video_id < 0:
        errors.append("invalid_canonical_video_identity")
    if not bundle.normalized_spans:
        errors.append("missing_evidence_span")
    if (
        len(bundle.source_texts) != len(candidate_ids)
        or any(not str(value).strip() for value in bundle.source_texts)
    ):
        errors.append("missing_authoritative_source_text")
    if not request.source_languages or any(not value for value in request.source_languages):
        errors.append("missing_source_language")
    if not bundle.trace_id:
        errors.append("missing_bundle_trace_id")
    if (
        not isinstance(bundle.union_duration, (int, float))
        or isinstance(bundle.union_duration, bool)
        or not math.isfinite(float(bundle.union_duration))
        or float(bundle.union_duration) < 0
    ):
        errors.append("invalid_union_duration")
    span_candidates: list[str] = []
    for span in bundle.normalized_spans:
        candidate_id = str(span.get("candidate_id", ""))
        span_candidates.append(candidate_id)
        if not candidate_id or candidate_id not in candidate_ids:
            errors.append("unresolved_candidate_to_segment_lineage")
        timeline_run_id = str(span.get("timeline_run_id", ""))
        if not timeline_run_id or timeline_run_id not in bundle.timeline_run_ids:
            errors.append("missing_or_conflicting_timeline_run_id")
        segment_ids = span.get("segment_ids")
        if (
            not isinstance(segment_ids, (list, tuple))
            or not segment_ids
            or any(not str(value) for value in segment_ids)
        ):
            errors.append("empty_or_unresolvable_segment_ids")
        start_time, end_time = span.get("start_time"), span.get("end_time")
        if (
            not isinstance(start_time, (int, float)) or isinstance(start_time, bool)
            or not isinstance(end_time, (int, float)) or isinstance(end_time, bool)
            or not math.isfinite(float(start_time)) or not math.isfinite(float(end_time))
            or float(start_time) < 0 or float(end_time) < float(start_time)
        ):
            errors.append("invalid_temporal_interval")
    if sorted(span_candidates) != sorted(candidate_ids):
        errors.append("candidate_span_lineage_mismatch")
    if not set(candidate_ids).issubset(state.available_evidence_candidate_ids):
        errors.append("unresolved_candidate_to_segment_lineage")
    return sorted(set(errors))


def apply_mechanical_sufficiency_gate(
    request: SufficiencyRequest,
    evidence_resolution_state: EvidenceResolutionState,
    evidence_bundle: EvidenceBundle | None,
    policy: MechanicalGatePolicy | None = None,
) -> MechanicalGateDecision:
    """Pure Stage 4A boundary: consumes constructed objects and performs no I/O."""

    policy = policy or MechanicalGatePolicy()
    errors = list(evidence_resolution_state.validation_errors)
    reason: str | None = None
    if request.search_candidate_set_id != evidence_resolution_state.search_candidate_set_id:
        reason, errors = "search_candidate_set_mismatch", [*errors, "search_candidate_set_mismatch"]
    elif request.evidence_candidate_set_id != evidence_resolution_state.evidence_candidate_set_id:
        reason, errors = "execution_manifest_mismatch", [*errors, "evidence_candidate_set_id_mismatch"]
    elif request.candidate_builder_version != policy.required_candidate_builder_version:
        reason, errors = "execution_manifest_mismatch", [*errors, "candidate_builder_version_mismatch"]
    elif request.selector_version != policy.required_selector_version:
        reason, errors = "selector_failed", [*errors, "selector_version_mismatch"]
    elif evidence_resolution_state.status != "resolved" or request.evidence_resolution_status != "resolved":
        reason = _reason(evidence_resolution_state.operational_reason_code or request.failure_attribution)
    elif evidence_bundle is None:
        reason, errors = "selector_failed", [*errors, "evidence_bundle_missing"]
    elif request.evidence_bundle_id != evidence_bundle.bundle_id or evidence_resolution_state.evidence_bundle_id != evidence_bundle.bundle_id:
        reason, errors = "invalid_evidence_bundle", [*errors, "evidence_bundle_id_mismatch"]
    elif bundle_errors := _bundle_contract_errors(request, evidence_resolution_state, evidence_bundle):
        reason, errors = "invalid_evidence_bundle", [*errors, *bundle_errors]
    elif evidence_bundle.normalization_status != "valid" or evidence_bundle.validation_errors:
        bundle_errors = evidence_bundle.validation_errors or ("bundle_normalization_invalid",)
        reason, errors = "invalid_evidence_bundle", [*errors, *bundle_errors]
    elif evidence_bundle.selection_method != policy.required_selector_version:
        reason, errors = "selector_failed", [*errors, "bundle_selector_version_mismatch"]
    elif evidence_bundle.query_id != request.query_id or evidence_bundle.evaluation_track != request.evaluation_track:
        reason, errors = "execution_manifest_mismatch", [*errors, "bundle_request_identity_mismatch"]
    elif not evidence_bundle.candidate_ids or any(not value for value in evidence_bundle.candidate_ids):
        reason, errors = "invalid_evidence_bundle", [*errors, "empty_evidence_ids"]
    elif not set(evidence_bundle.candidate_ids).issubset(evidence_resolution_state.available_evidence_candidate_ids):
        reason, errors = "invalid_evidence_bundle", [*errors, "invalid_bundle_reference"]
    elif not evidence_resolution_state.evidence_ids_raw_derived or not evidence_resolution_state.source_integrity_valid:
        reason, errors = "normalization_failure", [*errors, "raw_source_integrity_unproven"]

    if reason is None:
        outcome, terminal, action, required = "judge_eligible", None, "none", True
        evidence_ids = tuple(evidence_bundle.candidate_ids)  # type: ignore[union-attr]
    else:
        reason = _reason(reason)
        outcome = "source_unverifiable" if reason in SOURCE_UNVERIFIABLE_REASONS else "invalid"
        terminal, action, required = outcome, REASON_ACTION[reason], False
        evidence_ids = ()
    return MechanicalGateDecision(
        gate_decision_id=_decision_id(request, outcome, reason, action), gate_outcome=outcome,
        terminal_status=terminal, operational_reason_code=reason, action_family=action,
        semantic_judge_required=required, query_id=request.query_id,
        evaluation_track=request.evaluation_track, end_to_end_claim_eligible=request.end_to_end_claim_eligible,
        search_candidate_set_id=request.search_candidate_set_id,
        evidence_candidate_set_id=request.evidence_candidate_set_id, evidence_bundle_id=request.evidence_bundle_id,
        evidence_ids_used=evidence_ids, mechanical_gate_policy_version=policy.mechanical_gate_policy_version,
        candidate_builder_version=request.candidate_builder_version, selector_version=request.selector_version,
        trace_id=request.trace_id, validation_errors=tuple(sorted(set(errors))),
    )


def terminal_sufficiency_decision(gate: MechanicalGateDecision) -> SufficiencyDecision:
    if gate.gate_outcome != "source_unverifiable":
        raise ValueError("Stage 4A may synthesize only source-unverifiable decisions")
    payload = {
        "contract_version": SUFFICIENCY_DECISION_CONTRACT_VERSION,
        "gate_decision_id": gate.gate_decision_id, "status": "unverifiable",
        "operational_reason_code": gate.operational_reason_code, "policy_version": MECHANICAL_GATE_POLICY_VERSION,
    }
    return SufficiencyDecision(
        decision_id=stable_id("decision_", payload), status="unverifiable", supported_aspects=(),
        missing_aspects=(), conflicts=(), operational_reason_code=gate.operational_reason_code,
        semantic_reason_code=None, action_family=gate.action_family, confidence=1.0,
        evidence_bundle_id=gate.evidence_bundle_id, evidence_ids_used=(), mechanical_gate_applied=True,
        semantic_judge_invoked=False, policy_version=MECHANICAL_GATE_POLICY_VERSION,
        judge_contract_version=None, judge_prompt_version=None, judge_model=None,
        evaluation_track=gate.evaluation_track, end_to_end_claim_eligible=gate.end_to_end_claim_eligible,
        trace_id=gate.trace_id, validation_errors=gate.validation_errors,
    )
