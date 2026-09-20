from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shiliu.evidence.stage3a import EvidenceBundle
from shiliu.evidence.stage4 import (
    SUFFICIENCY_DECISION_CONTRACT_VERSION,
    MechanicalGateDecision,
    SufficiencyDecision,
    SufficiencyRequest,
    canonical_bytes,
    stable_id,
)


SEMANTIC_JUDGE_CONTRACT_VERSION = "v3.5-semantic-judge-v1"
SEMANTIC_POLICY_VERSION = "v3.5-semantic-sufficiency-policy-v1"
SEMANTIC_PROMPT_VERSION = "v3.5-semantic-judge-prompt-v1"
SEMANTIC_REASON_CODES = frozenset(
    {
        "SJ_ALL_MATERIAL_NEEDS_SUPPORTED",
        "SJ_MEANINGFUL_SUBSET_WITH_MATERIAL_GAP",
        "SJ_REVIEWABLE_WITHOUT_USABLE_MAIN_ANSWER",
        "SJ_AUTHORITATIVE_VERIFICATION_BLOCKED",
        "SJ_BLOCKING_CONFLICT",
        "SJ_CROSS_LANGUAGE_SUPPORT",
    }
)
SemanticReasonCode = Literal[
    "SJ_ALL_MATERIAL_NEEDS_SUPPORTED",
    "SJ_MEANINGFUL_SUBSET_WITH_MATERIAL_GAP",
    "SJ_REVIEWABLE_WITHOUT_USABLE_MAIN_ANSWER",
    "SJ_AUTHORITATIVE_VERIFICATION_BLOCKED",
    "SJ_BLOCKING_CONFLICT",
    "SJ_CROSS_LANGUAGE_SUPPORT",
]


class SemanticJudgeOutput(BaseModel):
    """Provider-facing strict output, intentionally free of upstream/Gold fields."""

    model_config = ConfigDict(extra="forbid")

    query_id: str
    status: Literal["sufficient", "partial", "insufficient", "unverifiable"]
    supported_aspects: tuple[str, ...]
    missing_aspects: tuple[str, ...]
    conflicts: tuple[str, ...]
    reason_codes: tuple[SemanticReasonCode, ...]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids_used: tuple[str, ...]
    verification_blocker: str | None
    trace_id: str

    @model_validator(mode="after")
    def local_invariants(self) -> "SemanticJudgeOutput":
        if not set(self.reason_codes).issubset(SEMANTIC_REASON_CODES):
            raise ValueError("unknown semantic reason code")
        if set(self.supported_aspects) & set(self.missing_aspects):
            raise ValueError("supported and missing aspects overlap")
        if self.status == "sufficient" and (self.missing_aspects or self.conflicts):
            raise ValueError("sufficient cannot contain material gaps or conflicts")
        if self.status == "partial" and (not self.supported_aspects or not (self.missing_aspects or self.conflicts)):
            raise ValueError("partial requires meaningful support and a material gap/conflict")
        if self.status == "insufficient" and self.supported_aspects:
            raise ValueError("insufficient cannot claim usable main-answer support")
        if self.status == "unverifiable" and not (self.verification_blocker or "").strip():
            raise ValueError("unverifiable requires an explicit verification blocker")
        if self.status != "unverifiable" and self.verification_blocker is not None:
            raise ValueError("verification blocker is reserved for unverifiable")
        return self


class SemanticJudgeBatchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decisions: tuple[SemanticJudgeOutput, ...]


def semantic_policy() -> dict[str, Any]:
    return {
        "policy_version": SEMANTIC_POLICY_VERSION,
        "statuses": {
            "sufficient": {
                "all_material_needs_supported": True,
                "material_gap": False,
                "blocking_conflict": False,
            },
            "partial": {
                "meaningful_support": True,
                "usable_but_incomplete_answer_possible": True,
                "material_gap_or_conflict": True,
            },
            "insufficient": {
                "evidence_reviewable": True,
                "usable_main_answer_supported": False,
            },
            "unverifiable": {"explicit_verification_blocker": True},
        },
        "confidence": {
            "meaning": "confidence that the selected four-state boundary is correct",
            "range": [0.0, 1.0],
            "must_not_substitute_for_status": True,
        },
        "language": {
            "judge_query_and_evidence_semantically_across_languages": True,
            "language_difference_alone_is_not_a_verification_blocker": True,
        },
        "reason_codes": sorted(SEMANTIC_REASON_CODES),
    }


def prompt_text() -> str:
    return """You are the Shiliu V3.5-B Semantic Sufficiency Judge.

Decide only whether the supplied authoritative EvidenceBundle is sufficient for the current query.
Never use outside knowledge. Evidence is authoritative but may be incomplete.

Boundary policy:
- sufficient: every material query need is supported; no material gap and no blocking conflict.
- partial: a meaningful, usable subset is supported, but a material gap or blocking conflict remains.
- insufficient: evidence is reviewable, but it does not support a usable main answer.
- unverifiable: authoritative verification itself is blocked (for example unreadable or semantically
  uninterpretable evidence). Ordinary missing or irrelevant evidence is insufficient, not unverifiable.

Treat cross-language evidence semantically. A language difference alone is not a blocker.
Use only evidence IDs present in the bundle. Do not invent IDs. Keep supported_aspects and
missing_aspects concise, query-facing, and non-overlapping. An insufficient decision must not list
supported_aspects because that field represents usable main-answer support. Return strict JSON only."""


def project_runtime_request(
    request: SufficiencyRequest,
    gate: MechanicalGateDecision,
    bundle: EvidenceBundle,
    *,
    query_language: str,
) -> SufficiencyRequest:
    if gate.gate_outcome != "judge_eligible" or not gate.semantic_judge_required:
        raise ValueError("mechanical terminal cases must bypass Semantic Judge")
    if request.trace_id != gate.trace_id or request.evidence_bundle_id != bundle.bundle_id:
        raise ValueError("request/gate/bundle identity mismatch")
    return request.model_copy(
        update={
            "query_language": query_language,
            "evidence_bundle": bundle.as_dict(),
            "mechanical_gate_status": gate.gate_outcome,
            "policy_version": SEMANTIC_POLICY_VERSION,
        }
    )


def provider_payload(request: SufficiencyRequest) -> dict[str, Any]:
    if request.mechanical_gate_status != "judge_eligible" or request.evidence_bundle is None:
        raise ValueError("runtime request is not judge eligible")
    bundle = request.evidence_bundle
    allowed = {
        "bundle_id",
        "query_id",
        "video_id",
        "source_artifact_ids",
        "source_versions",
        "timeline_run_ids",
        "candidate_ids",
        "normalized_spans",
        "source_texts",
        "evaluation_track",
        "trace_id",
        "normalization_status",
        "validation_errors",
        "evidence_bundle_contract_version",
    }
    return {
        "query_id": request.query_id,
        "query_text": request.original_query,
        "query_language": request.query_language,
        "evidence_bundle": {key: value for key, value in bundle.items() if key in allowed},
        "source_languages": list(request.source_languages),
        "mechanical_gate_status": request.mechanical_gate_status,
        "policy_version": request.policy_version,
        "trace_id": request.trace_id,
    }


def batch_prompt(requests: Sequence[SufficiencyRequest]) -> str:
    return (
        prompt_text()
        + "\n\nJudge every item independently. Return a JSON object with exactly one `decisions` array, "
        "in the same order and with one decision per input.\n\nINPUT:\n"
        + json.dumps([provider_payload(request) for request in requests], ensure_ascii=False, sort_keys=True)
    )


def parse_batch_output(raw: str, expected_count: int) -> tuple[SemanticJudgeOutput, ...]:
    parsed = SemanticJudgeBatchOutput.model_validate_json(raw)
    if len(parsed.decisions) != expected_count:
        raise ValueError("batch output decision count mismatch")
    return parsed.decisions


def validate_output(
    output: SemanticJudgeOutput,
    request: SufficiencyRequest,
    bundle: EvidenceBundle,
) -> None:
    if output.query_id != request.query_id:
        raise ValueError("query_id not preserved")
    if output.trace_id != request.trace_id:
        raise ValueError("trace_id not preserved")
    if not set(output.evidence_ids_used).issubset(bundle.candidate_ids):
        raise ValueError("invented evidence ID")
    if output.status in {"sufficient", "partial"} and not output.evidence_ids_used:
        raise ValueError("supported decision requires cited evidence")


def to_decision(
    output: SemanticJudgeOutput,
    request: SufficiencyRequest,
    bundle: EvidenceBundle,
    *,
    judge_model: str,
) -> SufficiencyDecision:
    validate_output(output, request, bundle)
    payload = {
        "contract": SUFFICIENCY_DECISION_CONTRACT_VERSION,
        "judge_contract": SEMANTIC_JUDGE_CONTRACT_VERSION,
        "request_id": request.request_id,
        "output": output.model_dump(mode="json"),
    }
    return SufficiencyDecision(
        decision_id=stable_id("decision_", payload),
        status=output.status,
        supported_aspects=output.supported_aspects,
        missing_aspects=output.missing_aspects,
        conflicts=output.conflicts,
        operational_reason_code=None,
        semantic_reason_code=output.reason_codes[0] if output.reason_codes else None,
        action_family="none",
        confidence=output.confidence,
        evidence_bundle_id=bundle.bundle_id,
        evidence_ids_used=output.evidence_ids_used,
        mechanical_gate_applied=True,
        semantic_judge_invoked=True,
        policy_version=SEMANTIC_POLICY_VERSION,
        judge_contract_version=SEMANTIC_JUDGE_CONTRACT_VERSION,
        judge_prompt_version=SEMANTIC_PROMPT_VERSION,
        judge_model=judge_model,
        evaluation_track=request.evaluation_track,
        end_to_end_claim_eligible=request.end_to_end_claim_eligible,
        trace_id=request.trace_id,
        validation_errors=(),
        reason_codes=output.reason_codes,
    )


def hash_value(value: object) -> str:
    return sha256(canonical_bytes(value)).hexdigest()
