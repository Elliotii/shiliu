"""Canonical V5.6 EvidenceDecision domain contract.

This module owns a projection over existing Evidence and Fact revision
authorities.  It deliberately contains no product-mode orchestration and does
not grant Fact, Raw Evidence, Citation, or Provider authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


EVIDENCE_DECISION_SCHEMA_VERSION = "v5.6-evidence-decision-v1"
EVIDENCE_DECISION_IDENTITY_VERSION = "v5.6-evidence-decision-identity-v1"
EVIDENCE_DECISION_AUTHORITY_HASH_VERSION = "v5.6-evidence-authority-hash-v1"
EVIDENCE_DECISION_SERIALIZER_VERSION = "v5.6-canonical-json-v1"
EVIDENCE_DECISION_PROJECTION_VERSION = "v5.6-evidence-decision-projection-v1"
MAX_REQUIREMENTS = 24
MAX_INFERRED_REQUIREMENTS = 8
MAX_AUTHORITY_REFERENCES_PER_ASPECT = 16
MAX_CONFLICTS = 16
MAX_SEMANTIC_ADVICE = 16
CANONICAL_SEGMENT_ID_LIMIT = 256
EVIDENCE_SEGMENT_CARDINALITY_EXCEEDED_REASON = (
    "evidence_segment_cardinality_exceeded"
)


class EvidenceDecisionContractError(ValueError):
    """A fail-closed parse or integrity failure."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class RequirementOrigin(str, Enum):
    EXPLICIT_USER = "explicit_user"
    PRODUCT_RULE = "product_rule"
    BOUNDED_INFERENCE = "bounded_inference"
    UNKNOWN = "unknown"


REQUIREMENT_PRECEDENCE: dict[RequirementOrigin, int] = {
    RequirementOrigin.EXPLICIT_USER: 0,
    RequirementOrigin.PRODUCT_RULE: 1,
    RequirementOrigin.BOUNDED_INFERENCE: 2,
    RequirementOrigin.UNKNOWN: 3,
}


class ScopeMatchStatus(str, Enum):
    EXACT = "exact"
    COMPATIBLE = "compatible"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


class SourceVersionStatus(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class ReferenceScopeStatus(str, Enum):
    IN_SCOPE = "in_scope"
    OUT_OF_SCOPE = "out_of_scope"
    UNKNOWN = "unknown"


class AuthorizationStatus(str, Enum):
    AUTHORIZED = "authorized"
    UNAUTHORIZED = "unauthorized"
    UNKNOWN = "unknown"


class CoverageStatus(str, Enum):
    COVERED = "covered"
    PARTIAL = "partial"
    OPEN = "open"
    UNKNOWN = "unknown"


class CorpusNewMaterialStatus(str, Enum):
    NO_RELEVANT_NEW_MATERIAL = "no_relevant_new_material"
    RELEVANT_NEW_MATERIAL = "relevant_new_material"
    NOT_CHECKED = "not_checked"
    CHECK_FAILED = "check_failed"


class LibraryFreshnessStatus(str, Enum):
    FRESH = "fresh"
    NEW_MATERIAL = "new_material"
    UNKNOWN = "unknown"
    CHECK_FAILED = "check_failed"


class ConflictStatus(str, Enum):
    POTENTIAL = "potential"
    CONFIRMED = "confirmed"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ContributionKind(str, Enum):
    OLD = "old"
    REUSED = "reused"
    NEW = "new"
    DROPPED = "dropped"


class GateName(str, Enum):
    REQUIREMENTS = "requirements"
    SCOPE = "scope"
    COVERAGE = "coverage"
    SOURCE_VERSION = "source_version"
    LIBRARY_FRESHNESS = "library_freshness"
    CONFLICT = "conflict"
    AUTHORITY = "authority"


class GateOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class EvidenceDecisionAction(str, Enum):
    ANSWER_FRESH = "answer_fresh"
    DIRECT_REUSE = "direct_reuse"
    TARGETED_REFRESH = "targeted_refresh"
    DEEP_RESEARCH = "deep_research"
    CLARIFY = "clarify"
    PARTIAL_ANSWER = "partial_answer"
    ABSTAIN = "abstain"


class FailClosedOutcome(str, Enum):
    ALLOW_CURRENT_EVIDENCE = "allow_current_evidence"
    ALLOW_DIRECT_REUSE = "allow_direct_reuse"
    REQUIRE_REFRESH = "require_refresh"
    REQUIRE_DEEP_RESEARCH = "require_deep_research"
    REQUIRE_CLARIFICATION = "require_clarification"
    PARTIAL_ONLY = "partial_only"
    INSUFFICIENT = "insufficient"


class DecisionReasonCode(str, Enum):
    REQUIREMENTS_RESOLVED = "requirements_resolved"
    EXPLICIT_REQUIREMENT_PRECEDENCE = "explicit_requirement_precedence"
    BOUNDED_INFERENCE_PRESENT = "bounded_inference_present"
    REQUIREMENT_UNKNOWN = "requirement_unknown"
    SCOPE_EXACT = "scope_exact"
    SCOPE_COMPATIBLE = "scope_compatible"
    SCOPE_MISMATCH = "scope_mismatch"
    SCOPE_UNKNOWN = "scope_unknown"
    COVERAGE_COMPLETE = "coverage_complete"
    COVERAGE_INCOMPLETE = "coverage_incomplete"
    COVERAGE_UNKNOWN = "coverage_unknown"
    SOURCE_VERSION_CURRENT = "source_version_current"
    SOURCE_VERSION_STALE = "source_version_stale"
    SOURCE_VERSION_INVALID = "source_version_invalid"
    SOURCE_VERSION_UNAVAILABLE = "source_version_unavailable"
    SOURCE_VERSION_UNKNOWN = "source_version_unknown"
    LIBRARY_FRESH = "library_fresh"
    LOCAL_CORPUS_NEW_MATERIAL = "local_corpus_new_material"
    LIBRARY_FRESHNESS_UNKNOWN = "library_freshness_unknown"
    LIBRARY_FRESHNESS_CHECK_FAILED = "library_freshness_check_failed"
    NO_BLOCKING_CONFLICT = "no_blocking_conflict"
    BLOCKING_CONFLICT = "blocking_conflict"
    AUTHORITY_VALID = "authority_valid"
    EVIDENCE_UNAUTHORIZED = "evidence_unauthorized"
    EVIDENCE_OUT_OF_SCOPE = "evidence_out_of_scope"
    EVIDENCE_AUTHORITY_UNKNOWN = "evidence_authority_unknown"
    CURRENT_EVIDENCE_AVAILABLE = "current_evidence_available"
    REUSED_EVIDENCE_AVAILABLE = "reused_evidence_available"
    NO_SAFE_COVERAGE = "no_safe_coverage"
    SEMANTIC_ADVICE_NON_AUTHORITATIVE = "semantic_advice_non_authoritative"


class SemanticAdviceKind(str, Enum):
    REQUIREMENT = "requirement"
    SCOPE = "scope"
    TIME_SENSITIVITY = "time_sensitivity"
    CONFLICT = "conflict"
    CLAIM_SUPPORT = "claim_support"


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceRequirement(_StrictFrozenModel):
    aspect_id: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=1000)
    origin: RequirementOrigin
    precedence: int = Field(default=0, ge=0, le=3)

    @model_validator(mode="after")
    def bind_precedence_to_origin(self) -> "EvidenceRequirement":
        expected = REQUIREMENT_PRECEDENCE[self.origin]
        if self.precedence != expected:
            object.__setattr__(self, "precedence", expected)
        return self


class ScopeAssessment(_StrictFrozenModel):
    status: ScopeMatchStatus
    requested_scope_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    candidate_scope_hash: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    explanation: str = Field(min_length=1, max_length=1000)
    compared_reference_ids: tuple[str, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def require_candidate_for_known_match(self) -> "ScopeAssessment":
        if self.status != ScopeMatchStatus.UNKNOWN and self.candidate_scope_hash is None:
            raise ValueError("known scope match states require a candidate scope hash")
        return self


class EvidenceAuthorityReference(_StrictFrozenModel):
    kind: Literal["evidence"] = "evidence"
    reference_id: str = Field(min_length=1, max_length=200)
    source_artifact_id: str = Field(min_length=1, max_length=240)
    source_version: str = Field(min_length=1, max_length=240)
    timeline_run_id: str = Field(min_length=1, max_length=240)
    segment_ids: tuple[str, ...] = Field(
        min_length=1, max_length=CANONICAL_SEGMENT_ID_LIMIT
    )
    source_version_status: SourceVersionStatus
    scope_status: ReferenceScopeStatus
    authorization_status: AuthorizationStatus


class FactRevisionAuthorityReference(_StrictFrozenModel):
    kind: Literal["fact_revision"] = "fact_revision"
    reference_id: str = Field(min_length=1, max_length=200)
    evidence_reference_ids: tuple[str, ...] = Field(min_length=1, max_length=32)
    source_version_status: SourceVersionStatus
    scope_status: ReferenceScopeStatus
    authorization_status: AuthorizationStatus


AuthorityReference = Annotated[
    EvidenceAuthorityReference | FactRevisionAuthorityReference,
    Field(discriminator="kind"),
]
_AUTHORITY_REFERENCE_ADAPTER = TypeAdapter(AuthorityReference)


class AspectCoverage(_StrictFrozenModel):
    aspect_id: str = Field(min_length=1, max_length=160)
    status: CoverageStatus
    authority_references: tuple[AuthorityReference, ...] = Field(
        default=(), max_length=MAX_AUTHORITY_REFERENCES_PER_ASPECT
    )
    explanation: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_references_for_claimed_coverage(self) -> "AspectCoverage":
        if self.status in {CoverageStatus.COVERED, CoverageStatus.PARTIAL}:
            if not self.authority_references:
                raise ValueError("covered or partial aspects require authority references")
        return self


class CorpusNewMaterialCheck(_StrictFrozenModel):
    corpus_scope: Literal["local_shiliu_corpus"] = "local_shiliu_corpus"
    status: CorpusNewMaterialStatus
    recorded_check_time: datetime
    previous_check_time: datetime | None = None
    bounded_query_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    candidate_reference_ids: tuple[str, ...] = Field(default=(), max_length=32)
    relevant_material_reference_ids: tuple[str, ...] = Field(default=(), max_length=32)
    internet_freshness_claimed: Literal[False] = False

    @model_validator(mode="after")
    def validate_local_check(self) -> "CorpusNewMaterialCheck":
        if self.recorded_check_time.tzinfo is None:
            raise ValueError("recorded_check_time must be timezone-aware")
        if self.previous_check_time is not None:
            if self.previous_check_time.tzinfo is None:
                raise ValueError("previous_check_time must be timezone-aware")
            if self.previous_check_time > self.recorded_check_time:
                raise ValueError("previous_check_time must not follow recorded_check_time")
        if (
            self.status == CorpusNewMaterialStatus.RELEVANT_NEW_MATERIAL
            and not self.relevant_material_reference_ids
        ):
            raise ValueError("relevant local material requires traceable references")
        if (
            self.status == CorpusNewMaterialStatus.NO_RELEVANT_NEW_MATERIAL
            and self.relevant_material_reference_ids
        ):
            raise ValueError("no-new-material status cannot carry relevant references")
        return self


class LibraryFreshness(_StrictFrozenModel):
    status: LibraryFreshnessStatus
    corpus_new_material_check: CorpusNewMaterialCheck

    @model_validator(mode="after")
    def bind_status_to_check(self) -> "LibraryFreshness":
        expected = {
            CorpusNewMaterialStatus.NO_RELEVANT_NEW_MATERIAL: LibraryFreshnessStatus.FRESH,
            CorpusNewMaterialStatus.RELEVANT_NEW_MATERIAL: LibraryFreshnessStatus.NEW_MATERIAL,
            CorpusNewMaterialStatus.NOT_CHECKED: LibraryFreshnessStatus.UNKNOWN,
            CorpusNewMaterialStatus.CHECK_FAILED: LibraryFreshnessStatus.CHECK_FAILED,
        }[self.corpus_new_material_check.status]
        if self.status != expected:
            raise ValueError("library_freshness must be derived from the local-corpus check")
        return self


class ConflictObservation(_StrictFrozenModel):
    conflict_id: str = Field(min_length=1, max_length=200)
    status: ConflictStatus
    left_reference_ids: tuple[str, ...] = Field(min_length=1, max_length=16)
    right_reference_ids: tuple[str, ...] = Field(min_length=1, max_length=16)
    observed_at: datetime
    explanation: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_aware_time(self) -> "ConflictObservation":
        if self.observed_at.tzinfo is None:
            raise ValueError("conflict observed_at must be timezone-aware")
        return self


class EvidenceContribution(_StrictFrozenModel):
    kind: ContributionKind
    reference_id: str = Field(min_length=1, max_length=200)
    aspect_ids: tuple[str, ...] = Field(default=(), max_length=24)


class SemanticAdvice(_StrictFrozenModel):
    advice_id: str = Field(min_length=1, max_length=200)
    kind: SemanticAdviceKind
    proposed_value: str = Field(min_length=1, max_length=1000)
    supporting_reference_ids: tuple[str, ...] = Field(default=(), max_length=32)
    non_authoritative: Literal[True] = True


class DeterministicGateResult(_StrictFrozenModel):
    gate: GateName
    outcome: GateOutcome
    reason_codes: tuple[DecisionReasonCode, ...] = Field(min_length=1, max_length=16)


class EvidenceDecisionInput(_StrictFrozenModel):
    normalized_question: str = Field(min_length=1, max_length=4000)
    parent_decision_id: str | None = Field(
        default=None, pattern=r"^evd_[0-9a-f]{32}$"
    )
    requirements: tuple[EvidenceRequirement, ...] = Field(
        min_length=1, max_length=MAX_REQUIREMENTS
    )
    scope: ScopeAssessment
    coverage: tuple[AspectCoverage, ...] = Field(
        min_length=1, max_length=MAX_REQUIREMENTS
    )
    library_freshness: LibraryFreshness
    conflicts: tuple[ConflictObservation, ...] = Field(default=(), max_length=MAX_CONFLICTS)
    contributions: tuple[EvidenceContribution, ...] = Field(default=(), max_length=96)
    semantic_advice: tuple[SemanticAdvice, ...] = Field(
        default=(), max_length=MAX_SEMANTIC_ADVICE
    )

    @model_validator(mode="after")
    def validate_identity_sets(self) -> "EvidenceDecisionInput":
        requirement_ids = [item.aspect_id for item in self.requirements]
        coverage_ids = [item.aspect_id for item in self.coverage]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("requirement aspect_ids must be unique")
        if len(coverage_ids) != len(set(coverage_ids)):
            raise ValueError("coverage aspect_ids must be unique")
        if set(requirement_ids) != set(coverage_ids):
            raise ValueError("coverage must address every and only declared requirement")
        inferred_count = sum(
            item.origin == RequirementOrigin.BOUNDED_INFERENCE
            for item in self.requirements
        )
        if inferred_count > MAX_INFERRED_REQUIREMENTS:
            raise ValueError("bounded inferred requirements exceed the contract maximum")
        return self


class EvidenceDecision(_StrictFrozenModel):
    schema_version: Literal[EVIDENCE_DECISION_SCHEMA_VERSION] = (
        EVIDENCE_DECISION_SCHEMA_VERSION
    )
    identity_version: Literal[EVIDENCE_DECISION_IDENTITY_VERSION] = (
        EVIDENCE_DECISION_IDENTITY_VERSION
    )
    serializer_version: Literal[EVIDENCE_DECISION_SERIALIZER_VERSION] = (
        EVIDENCE_DECISION_SERIALIZER_VERSION
    )
    authority_hash_version: Literal[EVIDENCE_DECISION_AUTHORITY_HASH_VERSION] = (
        EVIDENCE_DECISION_AUTHORITY_HASH_VERSION
    )
    decision_id: str = Field(pattern=r"^evd_[0-9a-f]{32}$")
    parent_decision_id: str | None = Field(
        default=None, pattern=r"^evd_[0-9a-f]{32}$"
    )
    recorded_at: datetime
    normalized_question: str = Field(min_length=1, max_length=4000)
    requirements: tuple[EvidenceRequirement, ...]
    scope: ScopeAssessment
    coverage: tuple[AspectCoverage, ...]
    library_freshness: LibraryFreshness
    conflicts: tuple[ConflictObservation, ...]
    contributions: tuple[EvidenceContribution, ...]
    semantic_advice: tuple[SemanticAdvice, ...]
    deterministic_gates: tuple[DeterministicGateResult, ...]
    covered_aspects: tuple[str, ...]
    open_aspects: tuple[str, ...]
    action: EvidenceDecisionAction
    reason_codes: tuple[DecisionReasonCode, ...]
    fail_closed_outcome: FailClosedOutcome
    input_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    authority_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    decision_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    provider_authority_granted: Literal[False] = False
    fact_authority_granted: Literal[False] = False
    citation_authority_granted: Literal[False] = False
    raw_evidence_authority_granted: Literal[False] = False

    @model_validator(mode="after")
    def validate_parent_rule(self) -> "EvidenceDecision":
        if self.parent_decision_id == self.decision_id:
            raise ValueError("a decision cannot parent itself")
        if self.recorded_at.tzinfo is None:
            raise ValueError("recorded_at must be timezone-aware")
        return self


class EvidenceDecisionProjection(_StrictFrozenModel):
    projection_type: Literal["evidence_decision"] = "evidence_decision"
    projection_version: Literal[EVIDENCE_DECISION_PROJECTION_VERSION] = (
        EVIDENCE_DECISION_PROJECTION_VERSION
    )
    decision_id: str = Field(pattern=r"^evd_[0-9a-f]{32}$")
    parent_decision_id: str | None = Field(
        default=None, pattern=r"^evd_[0-9a-f]{32}$"
    )
    authority_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    serialized_decision: str = Field(min_length=2)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_identity(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def scope_hash(value: Any) -> str:
    """Hash a bounded scope value without assigning it factual authority."""

    return sha256_identity(value)


def resolve_requirements(
    requirements: Iterable[EvidenceRequirement],
) -> tuple[EvidenceRequirement, ...]:
    """Deduplicate aspects using the frozen explicit-first precedence rule."""

    selected: dict[str, EvidenceRequirement] = {}
    for requirement in requirements:
        current = selected.get(requirement.aspect_id)
        if current is None or requirement.precedence < current.precedence:
            selected[requirement.aspect_id] = requirement
    resolved = tuple(sorted(selected.values(), key=lambda item: (item.precedence, item.aspect_id)))
    if not resolved:
        raise EvidenceDecisionContractError(
            "at least one requirement is required", code="requirements_empty"
        )
    if len(resolved) > MAX_REQUIREMENTS:
        raise EvidenceDecisionContractError(
            "requirements exceed the bounded maximum", code="requirements_unbounded"
        )
    if sum(
        item.origin == RequirementOrigin.BOUNDED_INFERENCE for item in resolved
    ) > MAX_INFERRED_REQUIREMENTS:
        raise EvidenceDecisionContractError(
            "inferred requirements exceed the bounded maximum",
            code="inferred_requirements_unbounded",
        )
    return resolved


def _reference_eligibility(
    reference: AuthorityReference,
) -> tuple[bool, bool, tuple[DecisionReasonCode, ...]]:
    reasons: list[DecisionReasonCode] = []
    unknown = False
    if reference.source_version_status != SourceVersionStatus.CURRENT:
        reasons.append(
            {
                SourceVersionStatus.STALE: DecisionReasonCode.SOURCE_VERSION_STALE,
                SourceVersionStatus.INVALID: DecisionReasonCode.SOURCE_VERSION_INVALID,
                SourceVersionStatus.UNAVAILABLE: DecisionReasonCode.SOURCE_VERSION_UNAVAILABLE,
                SourceVersionStatus.UNKNOWN: DecisionReasonCode.SOURCE_VERSION_UNKNOWN,
            }[reference.source_version_status]
        )
        unknown |= reference.source_version_status == SourceVersionStatus.UNKNOWN
    if reference.scope_status != ReferenceScopeStatus.IN_SCOPE:
        reasons.append(
            DecisionReasonCode.EVIDENCE_OUT_OF_SCOPE
            if reference.scope_status == ReferenceScopeStatus.OUT_OF_SCOPE
            else DecisionReasonCode.EVIDENCE_AUTHORITY_UNKNOWN
        )
        unknown |= reference.scope_status == ReferenceScopeStatus.UNKNOWN
    if reference.authorization_status != AuthorizationStatus.AUTHORIZED:
        reasons.append(
            DecisionReasonCode.EVIDENCE_UNAUTHORIZED
            if reference.authorization_status == AuthorizationStatus.UNAUTHORIZED
            else DecisionReasonCode.EVIDENCE_AUTHORITY_UNKNOWN
        )
        unknown |= reference.authorization_status == AuthorizationStatus.UNKNOWN
    return not reasons, unknown, tuple(dict.fromkeys(reasons))


def _all_references(value: EvidenceDecisionInput) -> tuple[AuthorityReference, ...]:
    return tuple(
        reference
        for coverage in value.coverage
        for reference in coverage.authority_references
    )


def _evaluate_gates(
    value: EvidenceDecisionInput,
) -> tuple[DeterministicGateResult, ...]:
    requirements_unknown = any(
        item.origin == RequirementOrigin.UNKNOWN for item in value.requirements
    )
    requirement_reasons = []
    if any(item.origin == RequirementOrigin.EXPLICIT_USER for item in value.requirements):
        requirement_reasons.append(DecisionReasonCode.EXPLICIT_REQUIREMENT_PRECEDENCE)
    if any(item.origin == RequirementOrigin.BOUNDED_INFERENCE for item in value.requirements):
        requirement_reasons.append(DecisionReasonCode.BOUNDED_INFERENCE_PRESENT)
    if requirements_unknown:
        requirement_reasons.append(DecisionReasonCode.REQUIREMENT_UNKNOWN)
    if not requirement_reasons:
        requirement_reasons.append(DecisionReasonCode.REQUIREMENTS_RESOLVED)
    requirements_gate = DeterministicGateResult(
        gate=GateName.REQUIREMENTS,
        outcome=GateOutcome.UNKNOWN if requirements_unknown else GateOutcome.PASS,
        reason_codes=tuple(requirement_reasons),
    )

    scope_reason = {
        ScopeMatchStatus.EXACT: DecisionReasonCode.SCOPE_EXACT,
        ScopeMatchStatus.COMPATIBLE: DecisionReasonCode.SCOPE_COMPATIBLE,
        ScopeMatchStatus.MISMATCH: DecisionReasonCode.SCOPE_MISMATCH,
        ScopeMatchStatus.UNKNOWN: DecisionReasonCode.SCOPE_UNKNOWN,
    }[value.scope.status]
    scope_gate = DeterministicGateResult(
        gate=GateName.SCOPE,
        outcome=(
            GateOutcome.FAIL
            if value.scope.status == ScopeMatchStatus.MISMATCH
            else GateOutcome.UNKNOWN
            if value.scope.status == ScopeMatchStatus.UNKNOWN
            else GateOutcome.PASS
        ),
        reason_codes=(scope_reason,),
    )

    coverage_statuses = {item.status for item in value.coverage}
    coverage_unknown = CoverageStatus.UNKNOWN in coverage_statuses
    coverage_complete = coverage_statuses == {CoverageStatus.COVERED}
    coverage_gate = DeterministicGateResult(
        gate=GateName.COVERAGE,
        outcome=(
            GateOutcome.PASS
            if coverage_complete
            else GateOutcome.UNKNOWN
            if coverage_unknown
            else GateOutcome.FAIL
        ),
        reason_codes=(
            DecisionReasonCode.COVERAGE_COMPLETE
            if coverage_complete
            else DecisionReasonCode.COVERAGE_UNKNOWN
            if coverage_unknown
            else DecisionReasonCode.COVERAGE_INCOMPLETE,
        ),
    )

    references = _all_references(value)
    eligibility = [_reference_eligibility(reference) for reference in references]
    source_reasons = tuple(
        dict.fromkeys(
            reason
            for _eligible, _unknown, reasons in eligibility
            for reason in reasons
            if reason
            in {
                DecisionReasonCode.SOURCE_VERSION_STALE,
                DecisionReasonCode.SOURCE_VERSION_INVALID,
                DecisionReasonCode.SOURCE_VERSION_UNAVAILABLE,
                DecisionReasonCode.SOURCE_VERSION_UNKNOWN,
            }
        )
    )
    source_unknown = DecisionReasonCode.SOURCE_VERSION_UNKNOWN in source_reasons
    source_gate = DeterministicGateResult(
        gate=GateName.SOURCE_VERSION,
        outcome=(
            GateOutcome.UNKNOWN
            if source_unknown
            else GateOutcome.FAIL
            if source_reasons
            else GateOutcome.PASS
        ),
        reason_codes=source_reasons or (DecisionReasonCode.SOURCE_VERSION_CURRENT,),
    )

    freshness_reason = {
        LibraryFreshnessStatus.FRESH: DecisionReasonCode.LIBRARY_FRESH,
        LibraryFreshnessStatus.NEW_MATERIAL: DecisionReasonCode.LOCAL_CORPUS_NEW_MATERIAL,
        LibraryFreshnessStatus.UNKNOWN: DecisionReasonCode.LIBRARY_FRESHNESS_UNKNOWN,
        LibraryFreshnessStatus.CHECK_FAILED: DecisionReasonCode.LIBRARY_FRESHNESS_CHECK_FAILED,
    }[value.library_freshness.status]
    freshness_gate = DeterministicGateResult(
        gate=GateName.LIBRARY_FRESHNESS,
        outcome=(
            GateOutcome.PASS
            if value.library_freshness.status == LibraryFreshnessStatus.FRESH
            else GateOutcome.FAIL
            if value.library_freshness.status == LibraryFreshnessStatus.NEW_MATERIAL
            else GateOutcome.UNKNOWN
        ),
        reason_codes=(freshness_reason,),
    )

    blocking_conflict = any(
        conflict.status in {ConflictStatus.POTENTIAL, ConflictStatus.CONFIRMED}
        for conflict in value.conflicts
    )
    conflict_gate = DeterministicGateResult(
        gate=GateName.CONFLICT,
        outcome=GateOutcome.FAIL if blocking_conflict else GateOutcome.PASS,
        reason_codes=(
            DecisionReasonCode.BLOCKING_CONFLICT
            if blocking_conflict
            else DecisionReasonCode.NO_BLOCKING_CONFLICT,
        ),
    )

    authority_reasons = tuple(
        dict.fromkeys(
            reason
            for _eligible, _unknown, reasons in eligibility
            for reason in reasons
            if reason
            in {
                DecisionReasonCode.EVIDENCE_UNAUTHORIZED,
                DecisionReasonCode.EVIDENCE_OUT_OF_SCOPE,
                DecisionReasonCode.EVIDENCE_AUTHORITY_UNKNOWN,
            }
        )
    )
    authority_unknown = DecisionReasonCode.EVIDENCE_AUTHORITY_UNKNOWN in authority_reasons
    authority_gate = DeterministicGateResult(
        gate=GateName.AUTHORITY,
        outcome=(
            GateOutcome.UNKNOWN
            if authority_unknown
            else GateOutcome.FAIL
            if authority_reasons
            else GateOutcome.PASS
        ),
        reason_codes=authority_reasons or (DecisionReasonCode.AUTHORITY_VALID,),
    )
    return (
        requirements_gate,
        scope_gate,
        coverage_gate,
        source_gate,
        freshness_gate,
        conflict_gate,
        authority_gate,
    )


def _select_action(
    value: EvidenceDecisionInput,
    gates: tuple[DeterministicGateResult, ...],
) -> tuple[EvidenceDecisionAction, tuple[DecisionReasonCode, ...], FailClosedOutcome]:
    by_name = {gate.gate: gate for gate in gates}
    reasons = [reason for gate in gates for reason in gate.reason_codes]
    safe_references = [
        reference
        for reference in _all_references(value)
        if _reference_eligibility(reference)[0]
    ]
    safe_reference_ids = {item.reference_id for item in safe_references}
    has_reused = any(
        item.kind == ContributionKind.REUSED
        and item.reference_id in safe_reference_ids
        for item in value.contributions
    )
    if value.semantic_advice:
        reasons.append(DecisionReasonCode.SEMANTIC_ADVICE_NON_AUTHORITATIVE)
    if by_name[GateName.REQUIREMENTS].outcome == GateOutcome.UNKNOWN or by_name[
        GateName.SCOPE
    ].outcome == GateOutcome.UNKNOWN:
        return (
            EvidenceDecisionAction.CLARIFY,
            tuple(dict.fromkeys(reasons)),
            FailClosedOutcome.REQUIRE_CLARIFICATION,
        )
    if by_name[GateName.CONFLICT].outcome == GateOutcome.FAIL:
        return (
            EvidenceDecisionAction.DEEP_RESEARCH,
            tuple(dict.fromkeys(reasons)),
            FailClosedOutcome.REQUIRE_DEEP_RESEARCH,
        )
    if any(
        by_name[name].outcome in {GateOutcome.FAIL, GateOutcome.UNKNOWN}
        for name in (GateName.SOURCE_VERSION, GateName.AUTHORITY)
    ):
        return (
            EvidenceDecisionAction.DEEP_RESEARCH,
            tuple(dict.fromkeys(reasons)),
            FailClosedOutcome.REQUIRE_DEEP_RESEARCH,
        )
    if by_name[GateName.SCOPE].outcome == GateOutcome.FAIL:
        return (
            EvidenceDecisionAction.DEEP_RESEARCH,
            tuple(dict.fromkeys(reasons)),
            FailClosedOutcome.REQUIRE_DEEP_RESEARCH,
        )
    if by_name[GateName.LIBRARY_FRESHNESS].outcome != GateOutcome.PASS:
        return (
            EvidenceDecisionAction.TARGETED_REFRESH
            if safe_references
            else EvidenceDecisionAction.DEEP_RESEARCH,
            tuple(dict.fromkeys(reasons)),
            FailClosedOutcome.REQUIRE_REFRESH
            if safe_references
            else FailClosedOutcome.REQUIRE_DEEP_RESEARCH,
        )
    if by_name[GateName.COVERAGE].outcome != GateOutcome.PASS:
        more_reasons = reasons + [
            DecisionReasonCode.CURRENT_EVIDENCE_AVAILABLE
            if safe_references
            else DecisionReasonCode.NO_SAFE_COVERAGE
        ]
        return (
            EvidenceDecisionAction.TARGETED_REFRESH
            if safe_references
            else EvidenceDecisionAction.DEEP_RESEARCH,
            tuple(dict.fromkeys(more_reasons)),
            FailClosedOutcome.REQUIRE_REFRESH
            if safe_references
            else FailClosedOutcome.REQUIRE_DEEP_RESEARCH,
        )
    if value.scope.status != ScopeMatchStatus.EXACT and has_reused:
        return (
            EvidenceDecisionAction.TARGETED_REFRESH,
            tuple(dict.fromkeys(reasons)),
            FailClosedOutcome.REQUIRE_REFRESH,
        )
    if has_reused:
        reasons.append(DecisionReasonCode.REUSED_EVIDENCE_AVAILABLE)
        return (
            EvidenceDecisionAction.DIRECT_REUSE,
            tuple(dict.fromkeys(reasons)),
            FailClosedOutcome.ALLOW_DIRECT_REUSE,
        )
    reasons.append(DecisionReasonCode.CURRENT_EVIDENCE_AVAILABLE)
    return (
        EvidenceDecisionAction.ANSWER_FRESH,
        tuple(dict.fromkeys(reasons)),
        FailClosedOutcome.ALLOW_CURRENT_EVIDENCE,
    )


def _input_payload(value: EvidenceDecisionInput) -> dict[str, Any]:
    return value.model_dump(mode="json", exclude_none=True)


def _authority_payload(value: EvidenceDecisionInput) -> dict[str, Any]:
    payload = _input_payload(value)
    payload.pop("semantic_advice", None)
    return {
        "authority_hash_version": EVIDENCE_DECISION_AUTHORITY_HASH_VERSION,
        **payload,
    }


def _decision_id(
    *, parent_decision_id: str | None, input_hash: str, authority_hash: str
) -> str:
    identity = sha256_identity(
        {
            "identity_version": EVIDENCE_DECISION_IDENTITY_VERSION,
            "schema_version": EVIDENCE_DECISION_SCHEMA_VERSION,
            "parent_decision_id": parent_decision_id,
            "input_hash": input_hash,
            "authority_hash": authority_hash,
        }
    )
    return "evd_" + identity.removeprefix("sha256:")[:32]


def _validate_decision_time_causality(
    value: EvidenceDecisionInput, *, recorded_at: datetime
) -> None:
    check_time = value.library_freshness.corpus_new_material_check.recorded_check_time
    if check_time > recorded_at:
        raise EvidenceDecisionContractError(
            "local-corpus check must not follow decision recorded_at",
            code="corpus_check_after_decision",
        )
    if any(conflict.observed_at > recorded_at for conflict in value.conflicts):
        raise EvidenceDecisionContractError(
            "conflict observation must not follow decision recorded_at",
            code="conflict_observation_after_decision",
        )


def create_evidence_decision(
    value: EvidenceDecisionInput, *, recorded_at: datetime
) -> EvidenceDecision:
    """Create one deterministic decision over already-bounded inputs."""

    if recorded_at.tzinfo is None:
        raise EvidenceDecisionContractError(
            "recorded_at must be timezone-aware", code="recorded_at_invalid"
        )
    _validate_decision_time_causality(value, recorded_at=recorded_at)
    requirements = resolve_requirements(value.requirements)
    if requirements != value.requirements:
        coverage_by_id = {item.aspect_id: item for item in value.coverage}
        value = value.model_copy(
            update={
                "requirements": requirements,
                "coverage": tuple(coverage_by_id[item.aspect_id] for item in requirements),
            }
        )
    gates = _evaluate_gates(value)
    action, reasons, outcome = _select_action(value, gates)
    covered = tuple(
        item.aspect_id
        for item in value.coverage
        if item.status == CoverageStatus.COVERED
        and item.authority_references
        and all(_reference_eligibility(reference)[0] for reference in item.authority_references)
    )
    opened = tuple(item.aspect_id for item in value.coverage if item.aspect_id not in covered)
    input_hash = sha256_identity(_input_payload(value))
    authority_hash = sha256_identity(_authority_payload(value))
    decision_id = _decision_id(
        parent_decision_id=value.parent_decision_id,
        input_hash=input_hash,
        authority_hash=authority_hash,
    )
    payload: dict[str, Any] = {
        "schema_version": EVIDENCE_DECISION_SCHEMA_VERSION,
        "identity_version": EVIDENCE_DECISION_IDENTITY_VERSION,
        "serializer_version": EVIDENCE_DECISION_SERIALIZER_VERSION,
        "authority_hash_version": EVIDENCE_DECISION_AUTHORITY_HASH_VERSION,
        "decision_id": decision_id,
        "parent_decision_id": value.parent_decision_id,
        "recorded_at": recorded_at,
        "normalized_question": value.normalized_question,
        "requirements": value.requirements,
        "scope": value.scope,
        "coverage": value.coverage,
        "library_freshness": value.library_freshness,
        "conflicts": value.conflicts,
        "contributions": value.contributions,
        "semantic_advice": value.semantic_advice,
        "deterministic_gates": gates,
        "covered_aspects": covered,
        "open_aspects": opened,
        "action": action,
        "reason_codes": reasons,
        "fail_closed_outcome": outcome,
        "input_hash": input_hash,
        "authority_hash": authority_hash,
        "provider_authority_granted": False,
        "fact_authority_granted": False,
        "citation_authority_granted": False,
        "raw_evidence_authority_granted": False,
    }
    json_payload = EvidenceDecision.model_validate(
        {**payload, "decision_hash": "sha256:" + "0" * 64}
    ).model_dump(mode="json", exclude={"decision_hash"}, exclude_none=True)
    return EvidenceDecision.model_validate(
        {**payload, "decision_hash": sha256_identity(json_payload)}
    )


def serialize_evidence_decision(decision: EvidenceDecision) -> str:
    """The sole canonical serializer for the EvidenceDecision contract."""

    _verify_integrity(decision)
    return canonical_json(decision.model_dump(mode="json", exclude_none=True))


def parse_evidence_decision(serialized: str | bytes) -> EvidenceDecision:
    """Strictly parse and integrity-check one exact supported schema version."""

    try:
        decoded = json.loads(serialized)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceDecisionContractError(
            "EvidenceDecision is not valid JSON", code="invalid_json"
        ) from exc
    if not isinstance(decoded, dict):
        raise EvidenceDecisionContractError(
            "EvidenceDecision must be a JSON object", code="invalid_shape"
        )
    if decoded.get("schema_version") != EVIDENCE_DECISION_SCHEMA_VERSION:
        raise EvidenceDecisionContractError(
            "unsupported EvidenceDecision schema version",
            code="unknown_schema_version",
        )
    try:
        decision = EvidenceDecision.model_validate(decoded)
    except Exception as exc:
        raise EvidenceDecisionContractError(
            "EvidenceDecision violates the canonical schema", code="invalid_contract"
        ) from exc
    _verify_integrity(decision)
    return decision


def _input_from_decision(decision: EvidenceDecision) -> EvidenceDecisionInput:
    return EvidenceDecisionInput(
        normalized_question=decision.normalized_question,
        parent_decision_id=decision.parent_decision_id,
        requirements=decision.requirements,
        scope=decision.scope,
        coverage=decision.coverage,
        library_freshness=decision.library_freshness,
        conflicts=decision.conflicts,
        contributions=decision.contributions,
        semantic_advice=decision.semantic_advice,
    )


def _verify_integrity(decision: EvidenceDecision) -> None:
    value = _input_from_decision(decision)
    expected = create_evidence_decision(value, recorded_at=decision.recorded_at)
    compared_fields = (
        "decision_id",
        "input_hash",
        "authority_hash",
        "decision_hash",
        "deterministic_gates",
        "covered_aspects",
        "open_aspects",
        "action",
        "reason_codes",
        "fail_closed_outcome",
    )
    if any(getattr(decision, name) != getattr(expected, name) for name in compared_fields):
        raise EvidenceDecisionContractError(
            "EvidenceDecision integrity or deterministic interpretation drifted",
            code="decision_integrity_failed",
        )


def decision_to_persistence_projection(
    decision: EvidenceDecision,
) -> dict[str, Any]:
    """Adapter payload suitable for existing JSON persistence containers."""

    projection = EvidenceDecisionProjection(
        decision_id=decision.decision_id,
        parent_decision_id=decision.parent_decision_id,
        authority_hash=decision.authority_hash,
        serialized_decision=serialize_evidence_decision(decision),
    )
    return projection.model_dump(mode="json", exclude_none=True)


def decision_from_persistence_projection(payload: Any) -> EvidenceDecision:
    try:
        projection = EvidenceDecisionProjection.model_validate(payload)
    except Exception as exc:
        raise EvidenceDecisionContractError(
            "invalid EvidenceDecision persistence projection",
            code="invalid_projection",
        ) from exc
    decision = parse_evidence_decision(projection.serialized_decision)
    if (
        decision.decision_id != projection.decision_id
        or decision.parent_decision_id != projection.parent_decision_id
        or decision.authority_hash != projection.authority_hash
    ):
        raise EvidenceDecisionContractError(
            "persistence projection identity drifted",
            code="projection_identity_failed",
        )
    return decision


def authority_reference_from_dict(payload: Any) -> AuthorityReference:
    """Strict adapter for callers that already hold existing authority IDs."""

    return _AUTHORITY_REFERENCE_ADAPTER.validate_python(payload)
