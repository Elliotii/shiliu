"""Bounded, provider-free material claim-to-Evidence support contract.

The evaluator consumes already-produced semantic observations but never calls a
verifier or performs a repair.  Verifier type, semantic pass count, bounded
repair selection, and deterministic-only claim classes remain unresolved.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shiliu.evidence.decision import (
    AuthorityReference,
    AuthorizationStatus,
    ReferenceScopeStatus,
    SourceVersionStatus,
    sha256_identity,
)


CLAIM_SUPPORT_SCHEMA_VERSION = "v5.6-bounded-claim-support-v1"
MAX_MATERIAL_CLAIMS = 32
MAX_CLAIM_AUTHORITY_REFERENCES = 64
MAX_REFERENCES_PER_CLAIM = 16
MAX_SEMANTIC_OBSERVATIONS = 64


class ClaimSupportOutcome(str, Enum):
    ALLOW = "allow"
    DOWNGRADE = "downgrade"
    REMOVE = "remove"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


class SemanticSupportVerdict(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class ClaimSupportReasonCode(str, Enum):
    SUPPORTED_BY_ELIGIBLE_EVIDENCE = "supported_by_eligible_evidence"
    SEMANTIC_SUPPORT_PARTIAL = "semantic_support_partial"
    SEMANTIC_SUPPORT_MISSING = "semantic_support_missing"
    SEMANTIC_SUPPORT_REJECTED = "semantic_support_rejected"
    EVIDENCE_REFERENCE_MISSING = "evidence_reference_missing"
    EVIDENCE_SOURCE_STALE = "evidence_source_stale"
    EVIDENCE_SOURCE_INVALID = "evidence_source_invalid"
    EVIDENCE_SOURCE_UNAVAILABLE = "evidence_source_unavailable"
    EVIDENCE_SOURCE_UNKNOWN = "evidence_source_unknown"
    EVIDENCE_OUT_OF_SCOPE = "evidence_out_of_scope"
    EVIDENCE_SCOPE_UNKNOWN = "evidence_scope_unknown"
    EVIDENCE_UNAUTHORIZED = "evidence_unauthorized"
    EVIDENCE_AUTHORIZATION_UNKNOWN = "evidence_authorization_unknown"
    SEMANTIC_RESULT_CANNOT_OVERRIDE_AUTHORITY = (
        "semantic_result_cannot_override_authority"
    )


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MaterialClaim(_StrictFrozenModel):
    claim_id: str = Field(min_length=1, max_length=160)
    answer_block_id: str = Field(min_length=1, max_length=160)
    claim_text_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    materiality: Literal["material"] = "material"
    authority_reference_ids: tuple[str, ...] = Field(
        min_length=1, max_length=MAX_REFERENCES_PER_CLAIM
    )


class SemanticSupportObservation(_StrictFrozenModel):
    observation_id: str = Field(min_length=1, max_length=160)
    claim_id: str = Field(min_length=1, max_length=160)
    verdict: SemanticSupportVerdict
    authority_reference_ids: tuple[str, ...] = Field(
        min_length=1, max_length=MAX_REFERENCES_PER_CLAIM
    )
    verifier_reference: str = Field(min_length=1, max_length=240)
    non_authoritative: Literal[True] = True


class BoundedClaimSupportInput(_StrictFrozenModel):
    schema_version: Literal[CLAIM_SUPPORT_SCHEMA_VERSION] = CLAIM_SUPPORT_SCHEMA_VERSION
    material_claims: tuple[MaterialClaim, ...] = Field(
        min_length=1, max_length=MAX_MATERIAL_CLAIMS
    )
    authority_references: tuple[AuthorityReference, ...] = Field(
        min_length=1, max_length=MAX_CLAIM_AUTHORITY_REFERENCES
    )
    semantic_observations: tuple[SemanticSupportObservation, ...] = Field(
        default=(), max_length=MAX_SEMANTIC_OBSERVATIONS
    )
    verifier_type: None = None
    semantic_pass_count: None = None
    bounded_repair_selected: None = None
    deterministic_only_claim_classes: tuple[()] = ()
    unresolved_policy: Literal["main_decision_required"] = "main_decision_required"
    provider_verifier_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_bounded_references(self) -> "BoundedClaimSupportInput":
        claim_ids = [item.claim_id for item in self.material_claims]
        reference_ids = [item.reference_id for item in self.authority_references]
        observation_ids = [item.observation_id for item in self.semantic_observations]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("material claim IDs must be unique")
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("authority reference IDs must be unique")
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("semantic observation IDs must be unique")
        known_claims = set(claim_ids)
        known_references = set(reference_ids)
        claim_references = {
            claim.claim_id: set(claim.authority_reference_ids)
            for claim in self.material_claims
        }
        for observation in self.semantic_observations:
            if observation.claim_id not in known_claims:
                raise ValueError("semantic observation references an unknown claim")
            if not set(observation.authority_reference_ids).issubset(known_references):
                raise ValueError("semantic observation references unknown authority")
            if not set(observation.authority_reference_ids).issubset(
                claim_references[observation.claim_id]
            ):
                raise ValueError("semantic observation is outside the claim's references")
        return self


class ClaimSupportDisposition(_StrictFrozenModel):
    claim_id: str
    outcome: ClaimSupportOutcome
    accepted_reference_ids: tuple[str, ...]
    rejected_reference_ids: tuple[str, ...]
    reason_codes: tuple[ClaimSupportReasonCode, ...] = Field(min_length=1)


class ClaimSupportExecutionRecord(_StrictFrozenModel):
    input_claim_count: int = Field(ge=1, le=MAX_MATERIAL_CLAIMS)
    input_reference_count: int = Field(ge=1, le=MAX_CLAIM_AUTHORITY_REFERENCES)
    semantic_observation_count: int = Field(ge=0, le=MAX_SEMANTIC_OBSERVATIONS)
    deterministic_evaluation_passes: Literal[1] = 1
    verifier_calls: Literal[0] = 0
    repair_attempts: Literal[0] = 0
    unbounded_loop_possible: Literal[False] = False


class BoundedClaimSupportDecision(_StrictFrozenModel):
    schema_version: Literal[CLAIM_SUPPORT_SCHEMA_VERSION] = CLAIM_SUPPORT_SCHEMA_VERSION
    input_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    dispositions: tuple[ClaimSupportDisposition, ...]
    overall_outcome: ClaimSupportOutcome
    execution: ClaimSupportExecutionRecord
    verifier_type: None = None
    semantic_pass_count_policy: None = None
    bounded_repair_policy: None = None
    deterministic_only_claim_classes: tuple[()] = ()
    unresolved_policy: Literal["main_decision_required"] = "main_decision_required"
    provider_authority_granted: Literal[False] = False


def _authority_failure_reasons(
    reference: AuthorityReference,
) -> tuple[ClaimSupportReasonCode, ...]:
    reasons: list[ClaimSupportReasonCode] = []
    if reference.source_version_status != SourceVersionStatus.CURRENT:
        reasons.append(
            {
                SourceVersionStatus.STALE: ClaimSupportReasonCode.EVIDENCE_SOURCE_STALE,
                SourceVersionStatus.INVALID: ClaimSupportReasonCode.EVIDENCE_SOURCE_INVALID,
                SourceVersionStatus.UNAVAILABLE: ClaimSupportReasonCode.EVIDENCE_SOURCE_UNAVAILABLE,
                SourceVersionStatus.UNKNOWN: ClaimSupportReasonCode.EVIDENCE_SOURCE_UNKNOWN,
            }[reference.source_version_status]
        )
    if reference.scope_status != ReferenceScopeStatus.IN_SCOPE:
        reasons.append(
            ClaimSupportReasonCode.EVIDENCE_OUT_OF_SCOPE
            if reference.scope_status == ReferenceScopeStatus.OUT_OF_SCOPE
            else ClaimSupportReasonCode.EVIDENCE_SCOPE_UNKNOWN
        )
    if reference.authorization_status != AuthorizationStatus.AUTHORIZED:
        reasons.append(
            ClaimSupportReasonCode.EVIDENCE_UNAUTHORIZED
            if reference.authorization_status == AuthorizationStatus.UNAUTHORIZED
            else ClaimSupportReasonCode.EVIDENCE_AUTHORIZATION_UNKNOWN
        )
    return tuple(reasons)


def evaluate_bounded_claim_support(
    value: BoundedClaimSupportInput,
) -> BoundedClaimSupportDecision:
    """Perform exactly one provider-free pass over bounded material claims."""

    references = {item.reference_id: item for item in value.authority_references}
    observations: dict[str, list[SemanticSupportObservation]] = {}
    for observation in value.semantic_observations:
        observations.setdefault(observation.claim_id, []).append(observation)
    dispositions: list[ClaimSupportDisposition] = []
    for claim in value.material_claims:
        claim_observations = observations.get(claim.claim_id, [])
        claimed = [references.get(item) for item in claim.authority_reference_ids]
        missing_ids = tuple(
            item
            for item, reference in zip(claim.authority_reference_ids, claimed, strict=True)
            if reference is None
        )
        rejected: list[str] = list(missing_ids)
        failure_reasons: list[ClaimSupportReasonCode] = []
        if missing_ids:
            failure_reasons.append(ClaimSupportReasonCode.EVIDENCE_REFERENCE_MISSING)
        eligible: list[str] = []
        for reference in (item for item in claimed if item is not None):
            reasons = _authority_failure_reasons(reference)
            if reasons:
                rejected.append(reference.reference_id)
                failure_reasons.extend(reasons)
            else:
                eligible.append(reference.reference_id)
        eligible_ids = set(eligible)
        supported_reference_ids = tuple(
            dict.fromkeys(
                reference_id
                for observation in claim_observations
                if observation.verdict == SemanticSupportVerdict.SUPPORTED
                for reference_id in observation.authority_reference_ids
                if reference_id in eligible_ids
            )
        )
        if failure_reasons:
            if claim_observations:
                failure_reasons.append(
                    ClaimSupportReasonCode.SEMANTIC_RESULT_CANNOT_OVERRIDE_AUTHORITY
                )
            dispositions.append(
                ClaimSupportDisposition(
                    claim_id=claim.claim_id,
                    outcome=ClaimSupportOutcome.REMOVE,
                    accepted_reference_ids=supported_reference_ids,
                    rejected_reference_ids=tuple(dict.fromkeys(rejected)),
                    reason_codes=tuple(dict.fromkeys(failure_reasons)),
                )
            )
            continue
        verdicts = {item.verdict for item in claim_observations}
        if SemanticSupportVerdict.UNSUPPORTED in verdicts:
            outcome = ClaimSupportOutcome.REMOVE
            reason = ClaimSupportReasonCode.SEMANTIC_SUPPORT_REJECTED
        elif SemanticSupportVerdict.PARTIAL in verdicts or SemanticSupportVerdict.UNKNOWN in verdicts:
            outcome = ClaimSupportOutcome.DOWNGRADE
            reason = ClaimSupportReasonCode.SEMANTIC_SUPPORT_PARTIAL
        elif (
            verdicts == {SemanticSupportVerdict.SUPPORTED}
            and supported_reference_ids
        ):
            outcome = ClaimSupportOutcome.ALLOW
            reason = ClaimSupportReasonCode.SUPPORTED_BY_ELIGIBLE_EVIDENCE
        else:
            outcome = ClaimSupportOutcome.DOWNGRADE
            reason = ClaimSupportReasonCode.SEMANTIC_SUPPORT_MISSING
        dispositions.append(
            ClaimSupportDisposition(
                claim_id=claim.claim_id,
                outcome=outcome,
                accepted_reference_ids=supported_reference_ids,
                rejected_reference_ids=(),
                reason_codes=(reason,),
            )
        )
    per_claim = {item.outcome for item in dispositions}
    if per_claim == {ClaimSupportOutcome.ALLOW}:
        overall = ClaimSupportOutcome.ALLOW
    elif per_claim.issubset(
        {ClaimSupportOutcome.ALLOW, ClaimSupportOutcome.DOWNGRADE}
    ):
        overall = ClaimSupportOutcome.PARTIAL
    elif any(
        item.outcome in {ClaimSupportOutcome.ALLOW, ClaimSupportOutcome.DOWNGRADE}
        for item in dispositions
    ):
        overall = ClaimSupportOutcome.PARTIAL
    else:
        overall = ClaimSupportOutcome.INSUFFICIENT
    return BoundedClaimSupportDecision(
        input_hash=sha256_identity(value.model_dump(mode="json", exclude_none=True)),
        dispositions=tuple(dispositions),
        overall_outcome=overall,
        execution=ClaimSupportExecutionRecord(
            input_claim_count=len(value.material_claims),
            input_reference_count=len(value.authority_references),
            semantic_observation_count=len(value.semantic_observations),
        ),
    )
