"""Adapters that connect Ask/Deep/Research to the canonical V5.6 decision."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Literal

from shiliu.ask.context import fuse_evidence
from shiliu.ask.contracts import Citation, TranscriptEvidenceSpan
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.ask.persistence import AskRunStore
from shiliu.evidence.continuation import (
    ContinuationEnvelope,
    ContinuationExecutionResult,
    ContinuationFailureState,
    ContinuationTarget,
    InheritedEvidenceReference,
    RefreshObservation,
    SearchExecutionReference,
    create_continuation_envelope,
    evidence_lineage_hash,
    run_targeted_refresh,
)
from shiliu.evidence.decision import (
    AspectCoverage,
    AuthorizationStatus,
    ContributionKind,
    CorpusNewMaterialCheck,
    CorpusNewMaterialStatus,
    CoverageStatus,
    CANONICAL_SEGMENT_ID_LIMIT,
    EvidenceAuthorityReference,
    EvidenceContribution,
    EvidenceDecision,
    EvidenceDecisionAction,
    EvidenceDecisionInput,
    EvidenceRequirement,
    LibraryFreshness,
    LibraryFreshnessStatus,
    ReferenceScopeStatus,
    RequirementOrigin,
    ScopeAssessment,
    ScopeMatchStatus,
    SourceVersionStatus,
    create_evidence_decision,
    decision_from_persistence_projection,
    decision_to_persistence_projection,
    scope_hash,
    sha256_identity,
)
from shiliu.evidence.contracts import EvidenceContractError
from shiliu.evidence.search import EvidenceSearchService
from shiliu.retrieval.product_search import ProductSearchFilterRequest, ProductSearchRequest


AdaptiveDirective = Literal["finalize", "targeted_refresh", "deep_research", "stop"]


@dataclass(frozen=True)
class RevalidatedInheritance:
    decision: EvidenceDecision
    spans: tuple[TranscriptEvidenceSpan, ...]
    dropped_reference_ids: tuple[str, ...]
    failure_state: ContinuationFailureState


@dataclass(frozen=True)
class AdaptiveRefreshOutput:
    execution: ContinuationExecutionResult
    inherited_spans: tuple[TranscriptEvidenceSpan, ...]
    new_spans: tuple[TranscriptEvidenceSpan, ...]

    @property
    def spans(self) -> tuple[TranscriptEvidenceSpan, ...]:
        return tuple(fuse_evidence([*self.inherited_spans, *self.new_spans]))


def decision_directive(decision: EvidenceDecision) -> AdaptiveDirective:
    if decision.action in {
        EvidenceDecisionAction.ANSWER_FRESH,
        EvidenceDecisionAction.DIRECT_REUSE,
    }:
        return "finalize"
    if decision.action == EvidenceDecisionAction.TARGETED_REFRESH:
        return "targeted_refresh"
    if decision.action == EvidenceDecisionAction.DEEP_RESEARCH:
        return "deep_research"
    return "stop"


def create_current_evidence_decision(
    *,
    question: str,
    filters: ProductSearchFilterRequest,
    spans: Iterable[TranscriptEvidenceSpan],
    requirements: tuple[EvidenceRequirement, ...] | None = None,
    parent_decision_id: str | None = None,
    contribution_kind: ContributionKind = ContributionKind.NEW,
    existing_reference_ids: set[str] | None = None,
    inherited_contributions: tuple[EvidenceContribution, ...] = (),
    recorded_at: datetime | None = None,
) -> EvidenceDecision:
    """Build the canonical projection after current Evidence acquisition."""

    current_time = recorded_at or datetime.now(timezone.utc)
    bounded_requirements = requirements or (
        EvidenceRequirement(
            aspect_id="question",
            description=question,
            origin=RequirementOrigin.EXPLICIT_USER,
        ),
    )
    fused_spans = tuple(fuse_evidence(spans))
    eligible_spans = tuple(
        value
        for value in fused_spans
        if len(value.segment_ids) <= CANONICAL_SEGMENT_ID_LIMIT
    )
    oversized_spans = tuple(
        value
        for value in fused_spans
        if len(value.segment_ids) > CANONICAL_SEGMENT_ID_LIMIT
    )
    references = tuple(evidence_reference(value) for value in eligible_spans)
    coverage = tuple(
        AspectCoverage(
            aspect_id=requirement.aspect_id,
            status=CoverageStatus.COVERED if references else CoverageStatus.OPEN,
            authority_references=references,
            explanation=(
                "current Evidence acquired for the requirement"
                if references
                else "no eligible current Evidence acquired"
            ),
        )
        for requirement in bounded_requirements
    )
    existing_ids = existing_reference_ids or set()
    contributions = tuple(inherited_contributions) + tuple(
        EvidenceContribution(
            kind=(
                ContributionKind.REUSED
                if reference.reference_id in existing_ids
                else contribution_kind
            ),
            reference_id=reference.reference_id,
            aspect_ids=tuple(value.aspect_id for value in bounded_requirements),
        )
        for reference in references
    ) + tuple(
        EvidenceContribution(
            kind=ContributionKind.DROPPED,
            reference_id=span.citation_id,
            aspect_ids=tuple(value.aspect_id for value in bounded_requirements),
        )
        for span in oversized_spans
    )
    request_scope = filters.model_dump(mode="json", exclude_none=True)
    decision_input = EvidenceDecisionInput(
        normalized_question=question,
        parent_decision_id=parent_decision_id,
        requirements=bounded_requirements,
        scope=ScopeAssessment(
            status=ScopeMatchStatus.EXACT,
            requested_scope_hash=scope_hash(request_scope),
            candidate_scope_hash=scope_hash(request_scope),
            explanation="current execution uses the requested normalized scope",
        ),
        coverage=coverage,
        library_freshness=LibraryFreshness(
            status=LibraryFreshnessStatus.FRESH,
            corpus_new_material_check=CorpusNewMaterialCheck(
                status=CorpusNewMaterialStatus.NO_RELEVANT_NEW_MATERIAL,
                recorded_check_time=current_time,
                bounded_query_hash=sha256_identity(
                    {"question": question, "scope": request_scope}
                ),
                candidate_reference_ids=tuple(value.reference_id for value in references),
            ),
        ),
        contributions=contributions,
    )
    return create_evidence_decision(decision_input, recorded_at=current_time)


def evidence_reference(span: TranscriptEvidenceSpan) -> EvidenceAuthorityReference:
    if len(span.segment_ids) > CANONICAL_SEGMENT_ID_LIMIT:
        raise ValueError(
            "Evidence reference exceeds the canonical segment-ID limit "
            f"of {CANONICAL_SEGMENT_ID_LIMIT}"
        )
    return EvidenceAuthorityReference(
        reference_id=span.citation_id,
        source_artifact_id=span.source_artifact_id,
        source_version=span.source_version,
        timeline_run_id=span.timeline_run_id,
        segment_ids=span.segment_ids,
        source_version_status=SourceVersionStatus.CURRENT,
        scope_status=ReferenceScopeStatus.IN_SCOPE,
        authorization_status=AuthorizationStatus.AUTHORIZED,
    )


def envelope_for_completed_run(
    *,
    run_id: str,
    decision: EvidenceDecision,
    target: ContinuationTarget,
    question: str,
    filters: dict[str, Any],
    citations: Iterable[dict[str, Any]],
    search_executions: Iterable[dict[str, Any]],
    failure_state: ContinuationFailureState = ContinuationFailureState.NONE,
) -> ContinuationEnvelope:
    search_values = tuple(_search_reference(value) for value in search_executions)
    execution_ids = tuple(
        value.execution_id for value in search_values if value.execution_id is not None
    )
    citation_values = tuple(citations)
    eligible_citations = tuple(
        value
        for value in citation_values
        if len(tuple(value["segment_ids"])) <= CANONICAL_SEGMENT_ID_LIMIT
    )
    oversized_citations = tuple(
        value
        for value in citation_values
        if len(tuple(value["segment_ids"])) > CANONICAL_SEGMENT_ID_LIMIT
    )
    inherited = tuple(
        InheritedEvidenceReference(
            reference_id=str(value["citation_id"]),
            citation_identity_version=str(value["citation_identity_version"]),
            source_artifact_id=str(value["source_artifact_id"]),
            source_version=str(value["source_version"]),
            timeline_run_id=str(value["timeline_run_id"]),
            segment_ids=tuple(str(item) for item in value["segment_ids"]),
            citation_lineage_hash=evidence_lineage_hash(value),
            search_execution_ids=execution_ids,
        )
        for value in eligible_citations
    )
    contributions = tuple(decision.contributions) + tuple(
        EvidenceContribution(
            kind=ContributionKind.DROPPED,
            reference_id=str(value["citation_id"]),
            aspect_ids=decision.open_aspects or decision.covered_aspects,
        )
        for value in oversized_citations
    )
    inherited_failure_state = failure_state
    if oversized_citations and not inherited and failure_state == ContinuationFailureState.NONE:
        inherited_failure_state = ContinuationFailureState.EVIDENCE_UNAVAILABLE
    return create_continuation_envelope(
        parent_run_id=run_id,
        parent_decision=decision,
        target=target,
        original_question=question,
        normalized_scope=filters,
        inherited_evidence=inherited,
        search_executions=search_values,
        failure_state=inherited_failure_state,
        contributions=tuple(dict.fromkeys(contributions)),
    )


def revalidate_inherited_evidence(
    *,
    run_store: AskRunStore,
    materializer: TranscriptEvidenceMaterializer,
    decision: EvidenceDecision,
    envelope: ContinuationEnvelope,
) -> RevalidatedInheritance:
    """Reload the parent run and replay every inherited citation from raw source."""

    if envelope.parent_decision_id != decision.decision_id:
        raise ValueError("continuation parent decision mismatch")
    parent = run_store.get_run(envelope.parent_run_id)
    if parent is None or parent["lifecycle_status"] != "completed":
        return RevalidatedInheritance(
            decision=decision,
            spans=(),
            dropped_reference_ids=tuple(value.reference_id for value in envelope.inherited_evidence),
            failure_state=ContinuationFailureState.EVIDENCE_UNAVAILABLE,
        )
    citations = {
        str(value["citation_id"]): Citation.model_validate(value)
        for value in parent["citations"]
    }
    valid: list[TranscriptEvidenceSpan] = []
    dropped: list[str] = []
    search_by_id = {
        str(value.get("execution_id")): value
        for value in parent["search_executions"]
        if value.get("execution_id")
    }
    for inherited in envelope.inherited_evidence:
        citation = citations.get(inherited.reference_id)
        if citation is None or not _citation_matches_envelope(citation, inherited):
            dropped.append(inherited.reference_id)
            continue
        search = next(
            (
                search_by_id[value]
                for value in inherited.search_execution_ids
                if value in search_by_id
            ),
            None,
        )
        try:
            valid.append(
                materializer.reconstruct_citation(
                    citation,
                    execution_id=str((search or {}).get("execution_id") or "inherited"),
                    search_trace_id=str((search or {}).get("search_trace_id") or "inherited"),
                    query=str((search or {}).get("query") or parent["query"]),
                )
            )
        except (EvidenceContractError, ValueError, KeyError, TypeError):
            dropped.append(inherited.reference_id)
    revalidated = _revalidated_decision(
        decision,
        valid_reference_ids={value.citation_id for value in valid},
        dropped_reference_ids=set(dropped),
    )
    failure = (
        ContinuationFailureState.NONE
        if valid or not envelope.inherited_evidence
        else ContinuationFailureState.EVIDENCE_UNAVAILABLE
    )
    return RevalidatedInheritance(
        decision=revalidated,
        spans=tuple(valid),
        dropped_reference_ids=tuple(dropped),
        failure_state=failure,
    )


def execute_targeted_refresh(
    *,
    decision: EvidenceDecision,
    envelope: ContinuationEnvelope,
    inherited_spans: tuple[TranscriptEvidenceSpan, ...],
    filters: ProductSearchFilterRequest,
    evidence_search: EvidenceSearchService,
    materializer: TranscriptEvidenceMaterializer,
) -> AdaptiveRefreshOutput:
    new_spans: list[TranscriptEvidenceSpan] = []

    def refresh(aspect_id: str, query: str, round_number: int) -> RefreshObservation:
        request = ProductSearchRequest(
            query=query,
            mode="auto",
            scope="transcript_chunk",
            result_limit=10,
            max_windows_per_video=2,
            filters=filters,
        )
        try:
            execution = evidence_search.execute_search(request)
            candidates = evidence_search.materialize_execution(execution)
            result = materializer.materialize(
                execution, candidates, query_index=round_number - 1
            )
        except Exception:
            return RefreshObservation(
                aspect_id=aspect_id,
                aspect_complete=False,
                failure_state=ContinuationFailureState.EVIDENCE_UNAVAILABLE,
            )
        eligible_spans = tuple(
            value
            for value in result.spans
            if len(value.segment_ids) <= CANONICAL_SEGMENT_ID_LIMIT
        )
        oversized_spans = tuple(
            value
            for value in result.spans
            if len(value.segment_ids) > CANONICAL_SEGMENT_ID_LIMIT
        )
        new_spans.extend(eligible_spans)
        return RefreshObservation(
            aspect_id=aspect_id,
            aspect_complete=bool(eligible_spans),
            authority_references=tuple(evidence_reference(value) for value in eligible_spans),
            dropped_reference_ids=tuple(
                value.citation_id for value in oversized_spans
            ),
            search_executions=(
                SearchExecutionReference(
                    execution_id=execution.execution_id,
                    search_trace_id=execution.raw_response.trace_id,
                    query=execution.request.query,
                    relation_kind="targeted_refresh",
                    trace_persisted=execution.raw_response.trace_persisted,
                ),
            ),
        )

    execution = run_targeted_refresh(decision, envelope, refresh)
    return AdaptiveRefreshOutput(
        execution=execution,
        inherited_spans=inherited_spans,
        new_spans=tuple(fuse_evidence(new_spans)),
    )


def decision_projection(decision: EvidenceDecision) -> dict[str, Any]:
    return decision_to_persistence_projection(decision)


def decision_from_trace(trace: dict[str, Any]) -> EvidenceDecision | None:
    value = trace.get("evidence_decision")
    return decision_from_persistence_projection(value) if isinstance(value, dict) else None


def _revalidated_decision(
    decision: EvidenceDecision,
    *,
    valid_reference_ids: set[str],
    dropped_reference_ids: set[str],
) -> EvidenceDecision:
    coverage: list[AspectCoverage] = []
    contributions: list[EvidenceContribution] = []
    for item in decision.coverage:
        references = []
        for reference in item.authority_references:
            if reference.reference_id in valid_reference_ids:
                references.append(reference.model_copy(update={
                    "source_version_status": SourceVersionStatus.CURRENT,
                    "scope_status": ReferenceScopeStatus.IN_SCOPE,
                    "authorization_status": AuthorizationStatus.AUTHORIZED,
                }))
            elif reference.reference_id in dropped_reference_ids:
                references.append(reference.model_copy(update={
                    "source_version_status": SourceVersionStatus.STALE,
                }))
        eligible = [value for value in references if value.source_version_status == SourceVersionStatus.CURRENT]
        coverage.append(AspectCoverage(
            aspect_id=item.aspect_id,
            status=CoverageStatus.COVERED if eligible else CoverageStatus.OPEN,
            authority_references=tuple(references),
            explanation="inherited Evidence was revalidated for this child execution",
        ))
    for value in decision.contributions:
        if value.reference_id in valid_reference_ids:
            contributions.append(value.model_copy(update={"kind": ContributionKind.REUSED}))
        elif value.reference_id in dropped_reference_ids:
            contributions.append(value.model_copy(update={"kind": ContributionKind.DROPPED}))
    recorded_at = datetime.now(timezone.utc)
    return create_evidence_decision(EvidenceDecisionInput(
        normalized_question=decision.normalized_question,
        parent_decision_id=decision.decision_id,
        requirements=decision.requirements,
        scope=decision.scope,
        coverage=tuple(coverage),
        library_freshness=LibraryFreshness(
            status=LibraryFreshnessStatus.FRESH,
            corpus_new_material_check=CorpusNewMaterialCheck(
                status=CorpusNewMaterialStatus.NO_RELEVANT_NEW_MATERIAL,
                recorded_check_time=recorded_at,
                previous_check_time=decision.library_freshness.corpus_new_material_check.recorded_check_time,
                bounded_query_hash=sha256_identity({
                    "parent_decision_id": decision.decision_id,
                    "revalidated": sorted(valid_reference_ids),
                }),
                candidate_reference_ids=tuple(sorted(valid_reference_ids)),
            ),
        ),
        conflicts=decision.conflicts,
        contributions=tuple(contributions),
        semantic_advice=decision.semantic_advice,
    ), recorded_at=recorded_at)


def _citation_matches_envelope(citation: Citation, inherited: InheritedEvidenceReference) -> bool:
    payload = citation.model_dump(mode="json")
    return (
        citation.citation_identity_version == inherited.citation_identity_version
        and citation.source_artifact_id == inherited.source_artifact_id
        and citation.source_version == inherited.source_version
        and citation.timeline_run_id == inherited.timeline_run_id
        and tuple(citation.segment_ids) == inherited.segment_ids
        and evidence_lineage_hash(payload) == inherited.citation_lineage_hash
    )


def _search_reference(value: dict[str, Any]) -> SearchExecutionReference:
    return SearchExecutionReference(
        execution_id=(str(value["execution_id"]) if value.get("execution_id") else None),
        search_trace_id=str(value["search_trace_id"]),
        query=str(value.get("query") or "unknown"),
        relation_kind=str(value.get("relation_kind") or "retrieval"),
        trace_persisted=bool(value.get("trace_persisted", True)),
    )
