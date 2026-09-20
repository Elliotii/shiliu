"""Typed, bounded V5.6 adaptive execution and continuation contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import json
import unicodedata
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shiliu.evidence.decision import (
    AspectCoverage,
    AuthorityReference,
    AuthorizationStatus,
    ConflictObservation,
    ContributionKind,
    CorpusNewMaterialCheck,
    CorpusNewMaterialStatus,
    CoverageStatus,
    CANONICAL_SEGMENT_ID_LIMIT,
    DecisionReasonCode,
    EvidenceContribution,
    EvidenceDecision,
    EvidenceDecisionAction,
    EvidenceDecisionInput,
    LibraryFreshness,
    LibraryFreshnessStatus,
    ReferenceScopeStatus,
    SourceVersionStatus,
    canonical_json,
    create_evidence_decision,
    serialize_evidence_decision,
    scope_hash,
    sha256_identity,
)


CONTINUATION_ENVELOPE_SCHEMA_VERSION = "v5.6-continuation-envelope-v1"
CONTINUATION_ENVELOPE_SERIALIZER_VERSION = "v5.6-continuation-json-v1"
CONTINUATION_EXECUTION_VERSION = "v5.6-adaptive-execution-v1"
MAX_REFRESH_ROUNDS = 3


class ContinuationContractError(ValueError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class ContinuationTarget(str, Enum):
    FAST = "fast"
    DEEP = "deep"
    RESEARCH = "research"
    KNOWLEDGE_REUSE = "knowledge_reuse"


class ContinuationFailureState(str, Enum):
    NONE = "none"
    EVIDENCE_INSUFFICIENT = "evidence_insufficient"
    EVIDENCE_UNAVAILABLE = "evidence_unavailable"
    SOURCE_CONFLICT = "source_conflict"
    GENERATION_FAILURE = "generation_failure"
    PROVIDER_FAILURE = "provider_failure"
    TRANSPORT_FAILURE = "transport_failure"
    INTERRUPTED = "interrupted"
    UNKNOWN_SIDE_EFFECT = "unknown_side_effect"
    BUDGET_EXHAUSTED = "budget_exhausted"
    DEADLINE_EXHAUSTED = "deadline_exhausted"


class ReceiptState(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    NOT_STARTED = "not_started"
    RESERVED = "reserved"
    IN_FLIGHT = "in_flight"
    RECEIPTED = "receipted"
    FAILED = "failed"
    UNKNOWN = "unknown"


class SideEffectState(str, Enum):
    NONE = "none"
    CONFIRMED_NONE = "confirmed_none"
    CONFIRMED = "confirmed"
    UNKNOWN = "unknown"


class ContinuationStopReason(str, Enum):
    COVERAGE_COMPLETE = "coverage_complete"
    NO_NEW_ELIGIBLE_EVIDENCE = "no_new_eligible_evidence"
    REPEATED_QUERY = "repeated_query"
    REPEATED_ACTION = "repeated_action"
    REPEATED_EVIDENCE_IDENTITY = "repeated_evidence_identity"
    SOURCE_OR_CITATION_LINEAGE_DRIFT = "source_or_citation_lineage_drift"
    CONFLICT_UNRESOLVED = "conflict_unresolved"
    DEADLINE_EXHAUSTED = "deadline_exhausted"
    TOOL_BUDGET_EXHAUSTED = "tool_budget_exhausted"
    UNKNOWN_SIDE_EFFECT = "unknown_side_effect"
    ACTION_BOUNDARY = "action_boundary"
    INTERRUPTED = "interrupted"
    RECEIPT_PREVENTS_REPLAY = "receipt_prevents_replay"
    MAX_REFRESH_ROUNDS = "max_refresh_rounds"


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SearchExecutionReference(_StrictFrozenModel):
    execution_id: str | None = Field(default=None, max_length=240)
    search_trace_id: str = Field(min_length=1, max_length=240)
    query: str = Field(min_length=1, max_length=2000)
    relation_kind: str = Field(min_length=1, max_length=80)
    trace_persisted: bool = True


class InheritedEvidenceReference(_StrictFrozenModel):
    reference_id: str = Field(min_length=1, max_length=200)
    citation_identity_version: str = Field(min_length=1, max_length=120)
    source_artifact_id: str = Field(min_length=1, max_length=240)
    source_version: str = Field(min_length=1, max_length=240)
    timeline_run_id: str = Field(min_length=1, max_length=240)
    segment_ids: tuple[str, ...] = Field(
        min_length=1, max_length=CANONICAL_SEGMENT_ID_LIMIT
    )
    citation_lineage_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    search_execution_ids: tuple[str, ...] = Field(default=(), max_length=32)


class ContinuationRequirement(_StrictFrozenModel):
    aspect_id: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=1000)
    origin: str = Field(min_length=1, max_length=80)


class ContinuationBudgetState(_StrictFrozenModel):
    refresh_rounds_completed: int = Field(default=0, ge=0, le=MAX_REFRESH_ROUNDS)
    max_refresh_rounds: Literal[MAX_REFRESH_ROUNDS] = MAX_REFRESH_ROUNDS
    remaining_tool_calls: int = Field(default=12, ge=0, le=64)
    deadline_at: datetime | None = None

    @model_validator(mode="after")
    def validate_deadline(self) -> "ContinuationBudgetState":
        if self.deadline_at is not None and self.deadline_at.tzinfo is None:
            raise ValueError("continuation deadline must be timezone-aware")
        return self


class ContinuationEnvelope(_StrictFrozenModel):
    schema_version: Literal[CONTINUATION_ENVELOPE_SCHEMA_VERSION] = CONTINUATION_ENVELOPE_SCHEMA_VERSION
    serializer_version: Literal[CONTINUATION_ENVELOPE_SERIALIZER_VERSION] = CONTINUATION_ENVELOPE_SERIALIZER_VERSION
    envelope_id: str = Field(pattern=r"^cont_[0-9a-f]{32}$")
    parent_run_id: str = Field(min_length=1, max_length=240)
    child_run_id: str | None = Field(default=None, max_length=240)
    parent_decision_id: str = Field(pattern=r"^evd_[0-9a-f]{32}$")
    parent_decision_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    target: ContinuationTarget
    original_question: str = Field(min_length=1, max_length=4000)
    normalized_scope: dict[str, Any] = Field(default_factory=dict)
    explicit_requirements: tuple[ContinuationRequirement, ...] = Field(min_length=1, max_length=24)
    covered_aspects: tuple[str, ...] = Field(default=(), max_length=24)
    open_aspects: tuple[str, ...] = Field(default=(), max_length=24)
    inherited_evidence: tuple[InheritedEvidenceReference, ...] = Field(default=(), max_length=64)
    search_executions: tuple[SearchExecutionReference, ...] = Field(default=(), max_length=64)
    current_action: EvidenceDecisionAction
    reason_codes: tuple[DecisionReasonCode, ...] = Field(default=(), max_length=64)
    contributions: tuple[EvidenceContribution, ...] = Field(default=(), max_length=96)
    budget: ContinuationBudgetState = Field(default_factory=ContinuationBudgetState)
    failure_state: ContinuationFailureState = ContinuationFailureState.NONE
    receipt_state: ReceiptState = ReceiptState.NOT_APPLICABLE
    side_effect_state: SideEffectState = SideEffectState.NONE
    stop_reason: ContinuationStopReason | None = None
    provider_authority_granted: Literal[False] = False
    provider_authority_inherited: Literal[False] = False
    envelope_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_state(self) -> "ContinuationEnvelope":
        requirement_ids = {value.aspect_id for value in self.explicit_requirements}
        if not set(self.covered_aspects).issubset(requirement_ids):
            raise ValueError("covered aspects must be declared requirements")
        if not set(self.open_aspects).issubset(requirement_ids):
            raise ValueError("open aspects must be declared requirements")
        if set(self.covered_aspects) & set(self.open_aspects):
            raise ValueError("covered and open aspects must be disjoint")
        if self.side_effect_state == SideEffectState.UNKNOWN and self.failure_state not in {
            ContinuationFailureState.UNKNOWN_SIDE_EFFECT,
            ContinuationFailureState.INTERRUPTED,
        }:
            raise ValueError("unknown side effect must remain a distinct failure")
        return self


class RefreshObservation(_StrictFrozenModel):
    aspect_id: str = Field(min_length=1, max_length=160)
    aspect_complete: bool = True
    authority_references: tuple[AuthorityReference, ...] = Field(default=(), max_length=16)
    dropped_reference_ids: tuple[str, ...] = Field(default=(), max_length=16)
    search_executions: tuple[SearchExecutionReference, ...] = Field(default=(), max_length=16)
    conflicts: tuple[ConflictObservation, ...] = Field(default=(), max_length=16)
    failure_state: ContinuationFailureState = ContinuationFailureState.NONE
    receipt_state: ReceiptState = ReceiptState.NOT_APPLICABLE
    side_effect_state: SideEffectState = SideEffectState.NONE


class RefreshRoundRecord(_StrictFrozenModel):
    round_number: int = Field(ge=1, le=MAX_REFRESH_ROUNDS)
    queried_aspects: tuple[str, ...]
    new_reference_ids: tuple[str, ...]
    dropped_reference_ids: tuple[str, ...]
    decision_id: str
    action: EvidenceDecisionAction
    reason_codes: tuple[DecisionReasonCode, ...]


class ContinuationExecutionResult(_StrictFrozenModel):
    execution_version: Literal[CONTINUATION_EXECUTION_VERSION] = CONTINUATION_EXECUTION_VERSION
    final_decision: EvidenceDecision
    envelope: ContinuationEnvelope
    rounds: tuple[RefreshRoundRecord, ...]
    stop_reason: ContinuationStopReason
    search_executions: tuple[SearchExecutionReference, ...]
    contributions: tuple[EvidenceContribution, ...]
    failure_state: ContinuationFailureState


RefreshCallback = Callable[[str, str, int], RefreshObservation]


def evidence_lineage_hash(value: dict[str, Any]) -> str:
    return sha256_identity({key: value[key] for key in (
        "citation_id", "citation_identity_version", "source_artifact_id",
        "source_version", "timeline_run_id", "segment_ids",
    )})


def create_continuation_envelope(
    *, parent_run_id: str, parent_decision: EvidenceDecision,
    target: ContinuationTarget, original_question: str,
    normalized_scope: dict[str, Any],
    inherited_evidence: tuple[InheritedEvidenceReference, ...] = (),
    search_executions: tuple[SearchExecutionReference, ...] = (),
    budget: ContinuationBudgetState | None = None,
    failure_state: ContinuationFailureState = ContinuationFailureState.NONE,
    receipt_state: ReceiptState = ReceiptState.NOT_APPLICABLE,
    side_effect_state: SideEffectState = SideEffectState.NONE,
    stop_reason: ContinuationStopReason | None = None,
    contributions: tuple[EvidenceContribution, ...] | None = None,
) -> ContinuationEnvelope:
    payload: dict[str, Any] = {
        "schema_version": CONTINUATION_ENVELOPE_SCHEMA_VERSION,
        "serializer_version": CONTINUATION_ENVELOPE_SERIALIZER_VERSION,
        "parent_run_id": parent_run_id, "child_run_id": None,
        "parent_decision_id": parent_decision.decision_id,
        "parent_decision_hash": parent_decision.decision_hash,
        "target": target,
        "original_question": original_question,
        "normalized_scope": normalized_scope,
        "explicit_requirements": tuple(
            ContinuationRequirement(aspect_id=value.aspect_id, description=value.description, origin=value.origin.value)
            for value in parent_decision.requirements
        ),
        "covered_aspects": parent_decision.covered_aspects,
        "open_aspects": parent_decision.open_aspects,
        "inherited_evidence": inherited_evidence,
        "search_executions": search_executions,
        "current_action": parent_decision.action,
        "reason_codes": parent_decision.reason_codes,
        "contributions": (
            parent_decision.contributions if contributions is None else contributions
        ),
        "budget": budget or ContinuationBudgetState(),
        "failure_state": failure_state,
        "receipt_state": receipt_state,
        "side_effect_state": side_effect_state,
        "stop_reason": stop_reason,
        "provider_authority_granted": False,
        "provider_authority_inherited": False,
    }
    return _seal_envelope(payload)


def bind_continuation_child(envelope: ContinuationEnvelope, *, child_run_id: str) -> ContinuationEnvelope:
    payload = envelope.model_dump(mode="json", exclude={"envelope_id", "envelope_hash"})
    payload["child_run_id"] = child_run_id
    return _seal_envelope(payload)


def serialize_continuation_envelope(envelope: ContinuationEnvelope) -> str:
    _verify_envelope(envelope)
    return canonical_json(envelope.model_dump(mode="json", exclude_none=True))


def parse_continuation_envelope(serialized: str | bytes | dict[str, Any]) -> ContinuationEnvelope:
    try:
        decoded = json.loads(serialized) if isinstance(serialized, (str, bytes)) else serialized
        envelope = ContinuationEnvelope.model_validate(decoded)
    except Exception as exc:
        raise ContinuationContractError("ContinuationEnvelope is invalid", code="invalid_continuation_envelope") from exc
    _verify_envelope(envelope)
    return envelope


def validate_continuation_consumption(
    decision: EvidenceDecision,
    envelope: ContinuationEnvelope,
    *,
    current_question: str,
    current_scope: dict[str, Any],
    target: ContinuationTarget,
) -> ContinuationEnvelope:
    """Revalidate every caller-supplied continuation before service side effects."""

    try:
        serialize_evidence_decision(decision)
    except Exception as exc:
        raise ContinuationContractError(
            "EvidenceDecision integrity failed at continuation boundary",
            code="continuation_decision_integrity_failed",
        ) from exc
    verified = parse_continuation_envelope(envelope.model_dump(mode="json"))
    if (
        verified.parent_decision_id != decision.decision_id
        or verified.parent_decision_hash != decision.decision_hash
    ):
        raise ContinuationContractError(
            "continuation parent decision binding changed",
            code="parent_decision_mismatch",
        )
    if decision.provider_authority_granted:
        raise ContinuationContractError(
            "continuation decision cannot grant Provider authority",
            code="continuation_provider_authority_forbidden",
        )
    if (
        verified.provider_authority_granted
        or verified.provider_authority_inherited
    ):
        raise ContinuationContractError(
            "continuation cannot grant or inherit Provider authority",
            code="continuation_provider_authority_forbidden",
        )
    normalized_current = _normalize_question(current_question)
    normalized_original = _normalize_question(verified.original_question)
    normalized_decision = _normalize_question(decision.normalized_question)
    if normalized_current != normalized_original or normalized_decision != normalized_original:
        raise ContinuationContractError(
            "current question does not match the frozen continuation question",
            code="continuation_question_mismatch",
        )
    if canonical_json(_jsonable(current_scope)) != canonical_json(
        _jsonable(verified.normalized_scope)
    ):
        raise ContinuationContractError(
            "current scope does not match the frozen continuation scope",
            code="continuation_scope_mismatch",
        )
    if decision.scope.requested_scope_hash != scope_hash(
        _jsonable(verified.normalized_scope)
    ):
        raise ContinuationContractError(
            "canonical decision scope does not match the frozen continuation scope",
            code="continuation_scope_mismatch",
        )
    if verified.target != target:
        raise ContinuationContractError(
            "continuation target is incompatible with this service boundary",
            code="continuation_target_mismatch",
        )
    unsafe = _unsafe_replay_stop(verified, current_time=datetime.now(timezone.utc))
    if unsafe in {
        ContinuationStopReason.UNKNOWN_SIDE_EFFECT,
        ContinuationStopReason.INTERRUPTED,
        ContinuationStopReason.RECEIPT_PREVENTS_REPLAY,
    }:
        raise ContinuationContractError(
            f"continuation replay is unsafe: {unsafe.value}",
            code="continuation_replay_unsafe",
        )
    return verified


def run_targeted_refresh(
    decision: EvidenceDecision, envelope: ContinuationEnvelope,
    refresh: RefreshCallback,
    *, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> ContinuationExecutionResult:
    """Search only ``open_aspects`` and stop deterministically within 3 rounds."""

    _validate_parent_binding(decision, envelope)
    pre_stop = _unsafe_replay_stop(envelope, current_time=now())
    if pre_stop is not None:
        return _terminal_result(decision, envelope, pre_stop)
    if decision.action != EvidenceDecisionAction.TARGETED_REFRESH:
        reason = ContinuationStopReason.COVERAGE_COMPLETE if not decision.open_aspects else ContinuationStopReason.ACTION_BOUNDARY
        return _terminal_result(decision, envelope, reason)

    current = decision
    coverage = {value.aspect_id: value for value in decision.coverage}
    known = {ref.reference_id: ref for item in decision.coverage for ref in item.authority_references}
    contributions = list(decision.contributions)
    search_refs = list(envelope.search_executions)
    rounds: list[RefreshRoundRecord] = []
    query_fingerprints: set[str] = set()
    decision_ids = {decision.decision_id}
    action_keys = {(decision.action.value, tuple(decision.open_aspects))}
    remaining_tools = envelope.budget.remaining_tool_calls
    stop = ContinuationStopReason.MAX_REFRESH_ROUNDS
    failure = envelope.failure_state
    requirement_by_id = {value.aspect_id: value for value in decision.requirements}

    for round_number in range(envelope.budget.refresh_rounds_completed + 1, MAX_REFRESH_ROUNDS + 1):
        if envelope.budget.deadline_at is not None and now() >= envelope.budget.deadline_at:
            stop, failure = ContinuationStopReason.DEADLINE_EXHAUSTED, ContinuationFailureState.DEADLINE_EXHAUSTED
            break
        observations: list[RefreshObservation] = []
        stop_now = False
        for aspect_id in current.open_aspects:
            if remaining_tools <= 0:
                stop, failure, stop_now = ContinuationStopReason.TOOL_BUDGET_EXHAUSTED, ContinuationFailureState.BUDGET_EXHAUSTED, True
                break
            query = requirement_by_id[aspect_id].description
            fingerprint = sha256_identity({"aspect_id": aspect_id, "query": query})
            if fingerprint in query_fingerprints:
                stop, stop_now = ContinuationStopReason.REPEATED_QUERY, True
                break
            query_fingerprints.add(fingerprint)
            observation = refresh(aspect_id, query, round_number)
            remaining_tools -= 1
            if observation.aspect_id != aspect_id:
                raise ContinuationContractError("refresh escaped its open aspect", code="refresh_aspect_mismatch")
            observations.append(observation)
            unsafe = _observation_stop(observation)
            if unsafe is not None:
                stop, failure, stop_now = unsafe[0], unsafe[1], True
                break
        if stop_now:
            break

        new_ids: list[str] = []
        dropped_ids: list[str] = []
        lineage_drift = False
        conflicts = list(current.conflicts)
        for observation in observations:
            eligible: list[AuthorityReference] = []
            for reference_id in observation.dropped_reference_ids:
                dropped_ids.append(reference_id)
                contributions.append(EvidenceContribution(
                    kind=ContributionKind.DROPPED,
                    reference_id=reference_id,
                    aspect_ids=(observation.aspect_id,),
                ))
            for reference in observation.authority_references:
                existing = known.get(reference.reference_id)
                if existing is not None and existing != reference:
                    lineage_drift = True
                    dropped_ids.append(reference.reference_id)
                    continue
                if _eligible(reference):
                    known[reference.reference_id] = reference
                    eligible.append(reference)
                    if existing is None:
                        new_ids.append(reference.reference_id)
                        contributions.append(EvidenceContribution(kind=ContributionKind.NEW, reference_id=reference.reference_id, aspect_ids=(observation.aspect_id,)))
                else:
                    dropped_ids.append(reference.reference_id)
                    contributions.append(EvidenceContribution(kind=ContributionKind.DROPPED, reference_id=reference.reference_id, aspect_ids=(observation.aspect_id,)))
            prior = coverage[observation.aspect_id]
            combined = tuple({value.reference_id: value for value in (*prior.authority_references, *eligible)}.values())
            coverage[observation.aspect_id] = AspectCoverage(
                aspect_id=observation.aspect_id,
                status=CoverageStatus.COVERED if observation.aspect_complete and eligible else CoverageStatus.PARTIAL if combined else CoverageStatus.OPEN,
                authority_references=combined,
                explanation="targeted refresh over the canonical open aspect",
            )
            conflicts.extend(observation.conflicts)
            search_refs.extend(observation.search_executions)
        if lineage_drift:
            stop = ContinuationStopReason.SOURCE_OR_CITATION_LINEAGE_DRIFT
            break
        if any(value.status.value in {"potential", "confirmed"} for value in conflicts):
            stop, failure = ContinuationStopReason.CONFLICT_UNRESOLVED, ContinuationFailureState.SOURCE_CONFLICT
        elif not new_ids:
            stop, failure = ContinuationStopReason.NO_NEW_ELIGIBLE_EVIDENCE, ContinuationFailureState.EVIDENCE_INSUFFICIENT

        recorded_at = now()
        child = create_evidence_decision(EvidenceDecisionInput(
            normalized_question=current.normalized_question,
            parent_decision_id=current.decision_id,
            requirements=current.requirements,
            scope=current.scope,
            coverage=tuple(coverage[value.aspect_id] for value in current.requirements),
            library_freshness=LibraryFreshness(
                status=LibraryFreshnessStatus.FRESH,
                corpus_new_material_check=CorpusNewMaterialCheck(
                    status=CorpusNewMaterialStatus.NO_RELEVANT_NEW_MATERIAL,
                    recorded_check_time=recorded_at,
                    previous_check_time=current.library_freshness.corpus_new_material_check.recorded_check_time,
                    bounded_query_hash=sha256_identity({"round": round_number, "open_aspects": list(current.open_aspects)}),
                    candidate_reference_ids=tuple(new_ids),
                ),
            ),
            conflicts=tuple(conflicts),
            contributions=tuple(_dedupe_contributions(contributions)),
            semantic_advice=current.semantic_advice,
        ), recorded_at=recorded_at)
        rounds.append(RefreshRoundRecord(
            round_number=round_number,
            queried_aspects=tuple(value.aspect_id for value in observations),
            new_reference_ids=tuple(dict.fromkeys(new_ids)),
            dropped_reference_ids=tuple(dict.fromkeys(dropped_ids)),
            decision_id=child.decision_id, action=child.action, reason_codes=child.reason_codes,
        ))
        current = child
        if stop in {ContinuationStopReason.CONFLICT_UNRESOLVED, ContinuationStopReason.NO_NEW_ELIGIBLE_EVIDENCE}:
            break
        if child.decision_id in decision_ids:
            stop = ContinuationStopReason.REPEATED_EVIDENCE_IDENTITY
            break
        decision_ids.add(child.decision_id)
        action_key = (child.action.value, tuple(child.open_aspects))
        if action_key in action_keys:
            stop = ContinuationStopReason.REPEATED_ACTION
            break
        action_keys.add(action_key)
        if not child.open_aspects:
            stop = ContinuationStopReason.COVERAGE_COMPLETE
            break
        if child.action != EvidenceDecisionAction.TARGETED_REFRESH:
            stop = ContinuationStopReason.ACTION_BOUNDARY
            break

    updated = create_continuation_envelope(
        parent_run_id=envelope.parent_run_id, parent_decision=current,
        target=envelope.target, original_question=envelope.original_question,
        normalized_scope=envelope.normalized_scope,
        inherited_evidence=envelope.inherited_evidence,
        search_executions=tuple(search_refs),
        budget=ContinuationBudgetState(
            refresh_rounds_completed=min(envelope.budget.refresh_rounds_completed + len(rounds), MAX_REFRESH_ROUNDS),
            remaining_tool_calls=remaining_tools, deadline_at=envelope.budget.deadline_at,
        ),
        failure_state=failure, receipt_state=envelope.receipt_state,
        side_effect_state=envelope.side_effect_state, stop_reason=stop,
    )
    return ContinuationExecutionResult(
        final_decision=current, envelope=updated, rounds=tuple(rounds),
        stop_reason=stop, search_executions=tuple(search_refs),
        contributions=tuple(_dedupe_contributions(contributions)), failure_state=failure,
    )


def _terminal_result(decision: EvidenceDecision, envelope: ContinuationEnvelope, reason: ContinuationStopReason) -> ContinuationExecutionResult:
    updated = create_continuation_envelope(
        parent_run_id=envelope.parent_run_id, parent_decision=decision,
        target=envelope.target, original_question=envelope.original_question,
        normalized_scope=envelope.normalized_scope,
        inherited_evidence=envelope.inherited_evidence,
        search_executions=envelope.search_executions, budget=envelope.budget,
        failure_state=envelope.failure_state, receipt_state=envelope.receipt_state,
        side_effect_state=envelope.side_effect_state, stop_reason=reason,
    )
    return ContinuationExecutionResult(
        final_decision=decision, envelope=updated, rounds=(), stop_reason=reason,
        search_executions=envelope.search_executions,
        contributions=decision.contributions, failure_state=envelope.failure_state,
    )


def _seal_envelope(payload: dict[str, Any]) -> ContinuationEnvelope:
    identity_hash = sha256_identity(_jsonable(payload))
    payload = {**payload, "envelope_id": "cont_" + identity_hash.removeprefix("sha256:")[:32]}
    payload["envelope_hash"] = sha256_identity(_jsonable({**payload, "envelope_hash": None}))
    return ContinuationEnvelope.model_validate(payload)


def _verify_envelope(envelope: ContinuationEnvelope) -> None:
    payload = envelope.model_dump(mode="json", exclude={"envelope_id", "envelope_hash"})
    expected_id = "cont_" + sha256_identity(_jsonable(payload)).removeprefix("sha256:")[:32]
    expected_hash = sha256_identity(_jsonable({**payload, "envelope_id": envelope.envelope_id, "envelope_hash": None}))
    if envelope.envelope_id != expected_id or envelope.envelope_hash != expected_hash:
        raise ContinuationContractError("ContinuationEnvelope integrity failed", code="continuation_integrity_failed")


def _validate_parent_binding(decision: EvidenceDecision, envelope: ContinuationEnvelope) -> None:
    _verify_envelope(envelope)
    if envelope.parent_decision_id != decision.decision_id or envelope.parent_decision_hash != decision.decision_hash:
        raise ContinuationContractError("parent decision binding changed", code="parent_decision_mismatch")
    if envelope.original_question != decision.normalized_question:
        raise ContinuationContractError("original question changed", code="original_question_mismatch")


def _unsafe_replay_stop(envelope: ContinuationEnvelope, *, current_time: datetime) -> ContinuationStopReason | None:
    if envelope.side_effect_state == SideEffectState.UNKNOWN or envelope.failure_state == ContinuationFailureState.UNKNOWN_SIDE_EFFECT:
        return ContinuationStopReason.UNKNOWN_SIDE_EFFECT
    if envelope.failure_state == ContinuationFailureState.INTERRUPTED:
        return ContinuationStopReason.INTERRUPTED
    if envelope.receipt_state in {ReceiptState.IN_FLIGHT, ReceiptState.UNKNOWN}:
        return ContinuationStopReason.RECEIPT_PREVENTS_REPLAY
    if envelope.budget.deadline_at is not None and current_time >= envelope.budget.deadline_at:
        return ContinuationStopReason.DEADLINE_EXHAUSTED
    if envelope.budget.remaining_tool_calls <= 0:
        return ContinuationStopReason.TOOL_BUDGET_EXHAUSTED
    if envelope.budget.refresh_rounds_completed >= MAX_REFRESH_ROUNDS:
        return ContinuationStopReason.MAX_REFRESH_ROUNDS
    return None


def _observation_stop(observation: RefreshObservation) -> tuple[ContinuationStopReason, ContinuationFailureState] | None:
    if observation.side_effect_state == SideEffectState.UNKNOWN or observation.failure_state == ContinuationFailureState.UNKNOWN_SIDE_EFFECT:
        return ContinuationStopReason.UNKNOWN_SIDE_EFFECT, ContinuationFailureState.UNKNOWN_SIDE_EFFECT
    if observation.failure_state == ContinuationFailureState.INTERRUPTED:
        return ContinuationStopReason.INTERRUPTED, ContinuationFailureState.INTERRUPTED
    if observation.receipt_state in {ReceiptState.IN_FLIGHT, ReceiptState.UNKNOWN}:
        return ContinuationStopReason.RECEIPT_PREVENTS_REPLAY, observation.failure_state
    if observation.failure_state != ContinuationFailureState.NONE:
        return ContinuationStopReason.ACTION_BOUNDARY, observation.failure_state
    return None


def _eligible(reference: AuthorityReference) -> bool:
    return reference.source_version_status == SourceVersionStatus.CURRENT and reference.scope_status == ReferenceScopeStatus.IN_SCOPE and reference.authorization_status == AuthorizationStatus.AUTHORIZED


def _dedupe_contributions(values: list[EvidenceContribution]) -> list[EvidenceContribution]:
    return list({(value.kind.value, value.reference_id, value.aspect_ids): value for value in values}.values())


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items() if item is not None}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _normalize_question(value: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", value).split())
    if not normalized:
        raise ContinuationContractError(
            "continuation question is empty",
            code="continuation_question_mismatch",
        )
    return normalized
