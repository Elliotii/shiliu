from __future__ import annotations

import time
import threading
from typing import Callable
from uuid import uuid4

from shiliu.artifacts import ArtifactStore
from shiliu.ask.answer import GroundedAnswerService
from shiliu.ask.adaptive import (
    create_current_evidence_decision,
    decision_directive,
    decision_projection,
    envelope_for_completed_run,
    execute_targeted_refresh,
    revalidate_inherited_evidence,
)
from shiliu.ask.candidates import AskCandidateProjector
from shiliu.ask.context import TranscriptContextBuilder
from shiliu.ask.contracts import (
    AskRequest,
    AskResponse,
    AnswerTrustSummary,
    RetrievedCandidateDisclosure,
    TraceSummary,
)
from shiliu.ask.deep.service import DeepSearchService
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.ask.finalize import AnswerFinalizer
from shiliu.ask.trust import ClaimVerifier, provider_free_soft_review
from shiliu.ask.query_analysis import QueryAnalyzer
from shiliu.ask.persistence import AskRunStore, final_evidence_identities
from shiliu.db import Database
from shiliu.evidence.search import EvidenceSearchService
from shiliu.evidence.continuation import (
    ContinuationEnvelope,
    ContinuationContractError,
    ContinuationFailureState,
    ContinuationTarget,
    create_continuation_envelope,
    validate_continuation_consumption,
)
from shiliu.evidence.decision import EvidenceDecision, sha256_identity
from shiliu.retrieval.product_search import ProductSearchRequest, ProductSearchService


class AskModeNotImplemented(RuntimeError):
    code = "ask_mode_not_implemented"
    http_status = 501


class AskService:
    def __init__(
        self,
        *,
        db: Database,
        product_search: ProductSearchService,
        provider_factory: Callable[[str], object],
        runtime_corpus_identity: str | None = None,
        evidence_search: EvidenceSearchService | None = None,
        context_builder: TranscriptContextBuilder | None = None,
        artifacts: ArtifactStore | None = None,
        claim_verifier: ClaimVerifier | None = None,
    ) -> None:
        self.db = db
        self._owned_runs: set[str] = set()
        self._owned_runs_lock = threading.Lock()
        self.run_store = AskRunStore(db)
        self.candidate_projector = AskCandidateProjector(db, self.run_store)
        self.evidence_search = evidence_search or EvidenceSearchService(
            db=db,
            product_search=product_search,
            authority_mode="live_current_exact_replay",
            runtime_corpus_identity=runtime_corpus_identity,
        )
        self.materializer = TranscriptEvidenceMaterializer(db)
        self.query_analyzer = QueryAnalyzer(provider_factory)
        self.context_builder = context_builder or TranscriptContextBuilder()
        self.answer_service = GroundedAnswerService(
            provider_factory, self.materializer
        )
        self.finalizer = AnswerFinalizer(
            context_builder=self.context_builder,
            answer_service=self.answer_service,
            materializer=self.materializer,
            claim_verifier=claim_verifier,
        )
        resolved_artifacts = artifacts or getattr(
            getattr(product_search, "enricher", None), "artifacts", None
        )
        self.deep_service = (
            DeepSearchService(
                db=db,
                artifacts=resolved_artifacts,
                product_search=product_search,
                provider_factory=provider_factory,
                runtime_corpus_identity=runtime_corpus_identity,
                evidence_search=self.evidence_search,
                materializer=self.materializer,
                context_builder=self.context_builder,
                finalizer=self.finalizer,
            )
            if isinstance(resolved_artifacts, ArtifactStore)
            else None
        )
    def ask(
        self,
        request: AskRequest,
        *,
        evidence_decision: EvidenceDecision | None = None,
        continuation_envelope: ContinuationEnvelope | None = None,
    ) -> AskResponse:
        if (evidence_decision is None) != (continuation_envelope is None):
            raise ContinuationContractError(
                "canonical decision and continuation envelope are required together",
                code="continuation_pair_required",
            )
        boundary = ContinuationTarget.DEEP if request.mode == "deep" else ContinuationTarget.FAST
        if evidence_decision is not None and continuation_envelope is not None:
            if request.mode == "fast" and continuation_envelope.target == ContinuationTarget.DEEP:
                boundary = ContinuationTarget.DEEP
            validate_continuation_consumption(
                evidence_decision,
                continuation_envelope,
                current_question=request.query,
                current_scope=request.filters.model_dump(mode="json", exclude_none=True),
                target=boundary,
            )
            if boundary == ContinuationTarget.FAST and decision_directive(evidence_decision) in {
                "deep_research",
                "stop",
            }:
                raise ContinuationContractError(
                    "canonical action cannot be finalized by Fast Ask",
                    code="continuation_action_boundary",
                )
        if boundary == ContinuationTarget.DEEP:
            if self.deep_service is None:
                raise AskModeNotImplemented(
                    "Deep Search 缺少 ArtifactStore 接线"
                )
            response, _trace = self.deep_service.ask(
                request,
                evidence_decision=evidence_decision,
                continuation_envelope=continuation_envelope,
            )
        else:
            response = self._ask_fast(
                request,
                evidence_decision=evidence_decision,
                continuation_envelope=continuation_envelope,
            )
        return response.model_copy(
            update={"candidate_disclosure": self._candidate_disclosure(response.run_id)}
        )

    def _ask_fast(
        self,
        request: AskRequest,
        *,
        evidence_decision: EvidenceDecision | None = None,
        continuation_envelope: ContinuationEnvelope | None = None,
    ) -> AskResponse:
        started = time.monotonic()
        run_id, created_at = self.start_run(
            request,
            parent_run_id=(
                continuation_envelope.parent_run_id
                if continuation_envelope is not None
                else None
            ),
        )
        try:
            return self._execute_fast(
                request,
                run_id=run_id,
                created_at=created_at,
                started=started,
                evidence_decision=evidence_decision,
                continuation_envelope=continuation_envelope,
            )
        except Exception as exc:
            self.run_store.fail(run_id, exc)
            raise
        finally:
            with self._owned_runs_lock:
                self._owned_runs.discard(run_id)

    def start_run(
        self, request: AskRequest, *, parent_run_id: str | None = None
    ) -> tuple[str, str]:
        """Allocate the durable identity before stream/202 delivery."""

        run_id = f"ask_run_{uuid4().hex}"
        created_at = self.run_store.start(
            run_id=run_id,
            query=request.query,
            mode=request.mode,
            filters=request.filters.model_dump(mode="json", exclude_none=True),
            parent_run_id=parent_run_id,
        )
        self.run_store.append_event(
            run_id,
            "run_created",
            {"mode": request.mode, "query_hash": sha256_identity(request.query)},
        )
        with self._owned_runs_lock:
            self._owned_runs.add(run_id)
        return run_id, created_at

    def execute_started(
        self, request: AskRequest, *, run_id: str, created_at: str
    ) -> AskResponse:
        """Execute a preallocated Fast/Deep run for NDJSON or durable polling."""

        try:
            if request.mode == "deep":
                if self.deep_service is None:
                    raise AskModeNotImplemented("Deep Search 缺少 ArtifactStore 接线")
                response, _trace = self.deep_service.execute_started(
                    request, run_id=run_id, created_at=created_at
                )
                return response.model_copy(
                    update={
                        "candidate_disclosure": self._candidate_disclosure(run_id)
                    }
                )
            return self._execute_fast(
                request,
                run_id=run_id,
                created_at=created_at,
                started=time.monotonic(),
            ).model_copy(
                update={"candidate_disclosure": self._candidate_disclosure(run_id)}
            )
        except Exception as exc:
            self.run_store.fail(run_id, exc)
            raise
        finally:
            with self._owned_runs_lock:
                self._owned_runs.discard(run_id)

    def is_owned(self, run_id: str) -> bool:
        with self._owned_runs_lock:
            return run_id in self._owned_runs

    def _execute_fast(
        self,
        request: AskRequest,
        *,
        run_id: str,
        created_at: str,
        started: float,
        evidence_decision: EvidenceDecision | None = None,
        continuation_envelope: ContinuationEnvelope | None = None,
    ) -> AskResponse:
        if (evidence_decision is None) != (continuation_envelope is None):
            raise ValueError("canonical decision and continuation envelope are required together")
        plan = (
            self.query_analyzer.analyze(request.query)
            if evidence_decision is None
            else None
        )
        self.run_store.append_event(
            run_id,
            "requirements_ready",
            {
                "query_count": len(plan.queries) if plan is not None else 0,
                "analysis_available": plan is not None and plan.error is None,
            },
        )
        all_spans = []
        stale_reasons: list[str] = []
        retrieval_errors: list[str] = []
        search_references: list[dict[str, object]] = []
        active_decision = evidence_decision
        adaptive_rounds: list[dict[str, object]] = []
        adaptive_stop_reason: str | None = None
        inherited_dropped: list[str] = []
        if evidence_decision is not None and continuation_envelope is not None:
            inherited = revalidate_inherited_evidence(
                run_store=self.run_store,
                materializer=self.materializer,
                decision=evidence_decision,
                envelope=continuation_envelope,
            )
            active_decision = inherited.decision
            all_spans.extend(inherited.spans)
            inherited_dropped.extend(inherited.dropped_reference_ids)
            working_envelope = create_continuation_envelope(
                parent_run_id=continuation_envelope.parent_run_id,
                parent_decision=active_decision,
                target=ContinuationTarget.FAST,
                original_question=continuation_envelope.original_question,
                normalized_scope=continuation_envelope.normalized_scope,
                inherited_evidence=continuation_envelope.inherited_evidence,
                search_executions=continuation_envelope.search_executions,
                budget=continuation_envelope.budget,
                failure_state=inherited.failure_state,
                receipt_state=continuation_envelope.receipt_state,
                side_effect_state=continuation_envelope.side_effect_state,
            )
            if decision_directive(active_decision) == "targeted_refresh":
                refreshed = execute_targeted_refresh(
                    decision=active_decision,
                    envelope=working_envelope,
                    inherited_spans=inherited.spans,
                    filters=request.filters,
                    evidence_search=self.evidence_search,
                    materializer=self.materializer,
                )
                active_decision = refreshed.execution.final_decision
                all_spans[:] = list(refreshed.spans)
                search_references.extend(
                    value.model_dump(mode="json")
                    for value in refreshed.execution.search_executions
                    if value not in continuation_envelope.search_executions
                )
                adaptive_rounds = [
                    value.model_dump(mode="json")
                    for value in refreshed.execution.rounds
                ]
                adaptive_stop_reason = refreshed.execution.stop_reason.value

            if decision_directive(active_decision) != "finalize":
                raise ContinuationContractError(
                    "continuation did not reach a Fast-finalizable action",
                    code="continuation_action_boundary",
                )

        queries = plan.queries if plan is not None else ()
        for query_index, query in enumerate(queries):
            retrieval_request = ProductSearchRequest(
                query=query,
                mode="auto",
                scope="transcript_chunk",
                result_limit=10,
                max_windows_per_video=2,
                filters=request.filters,
            )
            self.run_store.append_event(
                run_id,
                "search_started",
                {
                    "query_index": query_index,
                    "query_hash": sha256_identity(query),
                    "relation_kind": "original_query" if query_index == 0 else "rewrite",
                },
            )
            try:
                execution = self.evidence_search.execute_search(
                    retrieval_request
                )
                search_references.append(
                    {
                        "execution_id": execution.execution_id,
                        "search_trace_id": execution.raw_response.trace_id,
                        "trace_persisted": execution.raw_response.trace_persisted,
                        "trace_error": execution.raw_response.trace_error,
                        "query": execution.request.query,
                        "relation_kind": (
                            "original_query" if query_index == 0 else "rewrite"
                        ),
                    }
                )
                candidate_set = self.evidence_search.materialize_execution(
                    execution
                )
                result = self.materializer.materialize(
                    execution, candidate_set, query_index=query_index
                )
                all_spans.extend(result.spans)
                stale_reasons.extend(result.stale_reasons)
                self.run_store.append_event(
                    run_id,
                    "search_completed",
                    {
                        "query_index": query_index,
                        "execution_id": execution.execution_id,
                        "search_trace_id": execution.raw_response.trace_id,
                        "current_evidence_count": len(result.spans),
                        "stale_evidence_count": len(result.stale_reasons),
                    },
                    provenance={
                        "search_execution_ids": [execution.execution_id],
                        "evidence_reference_ids": [
                            value.citation_id for value in result.spans
                        ],
                    },
                )
            except Exception as exc:
                retrieval_errors.append(f"{type(exc).__name__}: {exc}"[:500])
                search_trace_id = getattr(exc, "trace_id", None)
                if search_trace_id:
                    search_references.append(
                        {
                            "execution_id": None,
                            "search_trace_id": str(search_trace_id),
                            "trace_persisted": bool(
                                getattr(exc, "trace_persisted", True)
                            ),
                            "trace_error": None,
                            "query": query,
                            "relation_kind": (
                                "original_query" if query_index == 0 else "rewrite"
                            ),
                        }
                    )
                self.run_store.append_event(
                    run_id,
                    "search_completed",
                    {
                        "query_index": query_index,
                        "outcome": "failed",
                        "error_code": str(getattr(exc, "code", type(exc).__name__)),
                        "search_trace_id": search_trace_id,
                    },
                    provenance={
                        "search_execution_ids": (),
                    },
                )

        trace: dict[str, object] = {
            "run_id": run_id,
            "created_at": created_at,
            "query": request.query,
            "mode": "fast",
            "normalized_intent": (
                plan.analysis.normalized_intent if plan is not None else request.query
            ),
            "queries": list(queries),
            "query_analysis_error": plan.error if plan is not None else None,
            "query_analysis_usage": plan.usage if plan is not None else {},
            "query_analysis_latency_ms": plan.latency_ms if plan is not None else 0,
            "query_analysis_finish_reason": plan.finish_reason if plan is not None else None,
            "query_analysis_retry_count": plan.retry_count if plan is not None else 0,
            "search_executions": search_references,
            "retrieval_errors": retrieval_errors,
            "stale_reasons": stale_reasons,
            "adaptive_rounds": adaptive_rounds,
            "adaptive_stop_reason": adaptive_stop_reason,
            "inherited_dropped_reference_ids": inherited_dropped,
        }
        if active_decision is None:
            active_decision = create_current_evidence_decision(
                question=request.query,
                filters=request.filters,
                spans=all_spans,
            )
        evidence_ids = list(dict.fromkeys(value.citation_id for value in all_spans))
        self.run_store.append_event(
            run_id,
            "evidence_batch_ready",
            {
                "current_evidence_count": len(evidence_ids),
                "stale_evidence_count": len(stale_reasons),
            },
            provenance={"evidence_reference_ids": evidence_ids},
        )
        trace["evidence_decision"] = decision_projection(active_decision)
        trace["evidence_decision_action"] = active_decision.action.value
        trace["adaptive_directive"] = decision_directive(active_decision)
        self.run_store.append_event(
            run_id,
            "route_decided",
            {
                "decision_id": active_decision.decision_id,
                "action": active_decision.action.value,
                "directive": decision_directive(active_decision),
            },
            provenance={"decision_ids": [active_decision.decision_id]},
        )
        final = self.finalizer.finalize(
            query=request.query,
            normalized_intent=(
                plan.analysis.normalized_intent if plan is not None else request.query
            ),
            spans=all_spans,
            stale_reasons=stale_reasons,
            termination_reason="answer_ready",
            retrieval_errors=retrieval_errors,
            run_id=run_id,
            event_sink=lambda event_type, payload: self.run_store.append_event(
                run_id, event_type, payload
            ),
        )
        trace.update(final.trace)
        latency_ms = _milliseconds(started)
        adaptive_query_count = sum(
            len(value.get("queried_aspects", []))
            for value in adaptive_rounds
            if isinstance(value.get("queried_aspects"), list)
        )
        summary = TraceSummary(
            query_count=len(queries) + adaptive_query_count,
            retrieval_count=len(queries) + adaptive_query_count,
            valid_evidence_count=final.valid_evidence_count,
            stale_evidence_count=final.stale_evidence_count,
            context_span_count=final.context_span_count,
            context_truncated=final.context_truncated,
            repair_used=final.repair_used,
            latency_ms=latency_ms,
            termination_reason=final.termination_reason,
        )
        response = AskResponse(
            run_id=run_id,
            mode="fast",
            status=final.status,
            execution_outcome=final.execution_outcome,
            answer_blocks=list(final.answer_blocks),
            citations=list(final.citations),
            limitations=list(final.limitations),
            termination_reason=final.termination_reason,
            trace_summary=summary,
            trust_summary=(
                AnswerTrustSummary.model_validate(final.trace["trust_summary"])
                if final.trace.get("trust_summary") is not None
                else None
            ),
        )
        if response.answer_blocks:
            for index, block in enumerate(response.answer_blocks):
                self.run_store.append_event(
                    run_id,
                    "trusted_answer_block",
                    {
                        "answer_version": 1,
                        "block_index": index,
                        "block": block.model_dump(mode="json"),
                    },
                    provenance={"evidence_reference_ids": block.citation_ids},
                )
            self.run_store.append_event(
                run_id,
                "answer_completed",
                _answer_event_payload(response),
                provenance={
                    "evidence_reference_ids": [
                        value.citation_id for value in response.citations
                    ]
                },
            )
            self.run_store.append_event(
                run_id,
                "soft_review_started",
                {
                    "answer_version": 1,
                    "provider_calls": 0,
                    "searches": 0,
                },
            )
            by_citation = {value.citation_id: value for value in all_spans}
            review = provider_free_soft_review(
                answer_blocks=response.answer_blocks,
                citations=response.citations,
                limitations=response.limitations,
                status=response.status,
                decision_projection=trace["evidence_decision"],
                validate_citation=lambda citation_id: self.materializer.validate_current(
                    by_citation[citation_id]
                ),
            )
            if review.changed:
                trust_summary = response.trust_summary.model_copy(
                    update={
                        "answer_version": review.answer_version,
                        "previous_answer_snapshot_hash": review.previous_answer_snapshot_hash,
                        "answer_snapshot_hash": review.answer_snapshot_hash,
                    }
                ) if response.trust_summary is not None else None
                response = response.model_copy(
                    update={
                        "status": review.status,
                        "limitations": list(review.limitations),
                        "answer_version": review.answer_version,
                        "trust_summary": trust_summary,
                    }
                )
                self.run_store.append_event(
                    run_id,
                    "answer_revision_created",
                    {
                        "from_version": 1,
                        "to_version": review.answer_version,
                        "previous_answer_snapshot_hash": review.previous_answer_snapshot_hash,
                        "answer_snapshot_hash": review.answer_snapshot_hash,
                        "reason_codes": list(review.reasons),
                        "limitations": list(review.limitations),
                        "status": review.status,
                    },
                )
            self.run_store.append_event(
                run_id,
                "soft_review_completed",
                {
                    "answer_version": response.answer_version,
                    "changed": review.changed,
                    "reason_codes": list(review.reasons),
                    "open_aspects": list(review.open_aspects),
                    "blocking_conflict_count": review.blocking_conflict_count,
                    "contribution_count": review.contribution_count,
                    "provider_calls": 0,
                    "searches": 0,
                },
            )
        else:
            self.run_store.append_event(
                run_id,
                "soft_review_skipped",
                {"reason": "no_trusted_body"},
            )
        trace.update(
            {
                "status": response.status,
                "execution_outcome": response.execution_outcome,
                "termination_reason": response.termination_reason,
                "latency_ms": latency_ms,
                "citation_ids": [
                    value.citation_id for value in response.citations
                ],
                "final_evidence": final_evidence_identities(
                    all_spans,
                    {value.citation_id for value in response.citations},
                ),
                "answer_blocks": [
                    value.model_dump(mode="json") for value in response.answer_blocks
                ],
                "citations": [
                    value.model_dump(mode="json") for value in response.citations
                ],
                "limitations": list(response.limitations),
                "trust_summary": (
                    response.trust_summary.model_dump(mode="json")
                    if response.trust_summary is not None
                    else None
                ),
                "answer_version": response.answer_version,
                "provider_usage": {
                    "query_analysis": plan.usage if plan is not None else {},
                    "answer": final.trace.get("answer_usage", []),
                },
            }
        )
        continuation = envelope_for_completed_run(
            run_id=run_id,
            decision=active_decision,
            target=ContinuationTarget.DEEP,
            question=request.query,
            filters=request.filters.model_dump(mode="json", exclude_none=True),
            citations=trace["citations"],
            search_executions=trace["search_executions"],
            failure_state=_continuation_failure(response.execution_outcome),
        )
        trace["continuation_envelope"] = continuation.model_dump(mode="json")
        self.run_store.complete(
            run_id=run_id,
            trace=trace,
            answer_status=response.status,
            termination_reason=response.termination_reason,
            query_analysis={
                **(
                    plan.analysis.model_dump(mode="json")
                    if plan is not None
                    else {"normalized_intent": request.query}
                ),
                "error": plan.error if plan is not None else None,
                "latency_ms": plan.latency_ms if plan is not None else 0,
                "finish_reason": plan.finish_reason if plan is not None else None,
                "retry_count": plan.retry_count if plan is not None else 0,
            },
            rewrites=queries,
            search_executions=trace["search_executions"],
            final_evidence=trace["final_evidence"],
            citations=trace["citations"],
            answer_blocks=trace["answer_blocks"],
            limitations=response.limitations,
            usage_summary=trace["provider_usage"],
        )
        self.run_store.append_event(
            run_id,
            "run_completed",
            {
                "status": response.status,
                "execution_outcome": response.execution_outcome,
                "answer_version": response.answer_version,
            },
        )
        return response

    def get_result(self, run_id: str) -> AskResponse | None:
        """Reconstruct the terminal response from durable state for reload/polling."""

        run = self.run_store.get_run(run_id)
        if run is None or run["lifecycle_status"] != "completed":
            return None
        trace = run["trace"]
        execution_outcome = trace.get("execution_outcome")
        if execution_outcome is None:
            completed = [
                value for value in run["events"] if value["event_type"] == "run_completed"
            ]
            if completed:
                execution_outcome = completed[-1]["payload"].get("execution_outcome")
        trust = trace.get("trust_summary")
        if trust is None:
            bodies = [
                value for value in run["events"] if value["event_type"] == "answer_completed"
            ]
            if bodies:
                trust = bodies[-1]["payload"].get("trust_summary")
        answer_version = int(trace.get("answer_version") or 1)
        revisions = [
            value for value in run["events"] if value["event_type"] == "answer_revision_created"
        ]
        if revisions:
            answer_version = int(revisions[-1]["payload"]["to_version"])
        return AskResponse(
            run_id=run_id,
            mode=run["mode"],
            status=run["answer_status"],
            execution_outcome=execution_outcome,
            answer_blocks=run["answer_blocks"],
            citations=run["citations"],
            limitations=run["limitations"],
            termination_reason=run["termination_reason"],
            trace_summary=TraceSummary(
                query_count=len(trace.get("queries") or run["rewrites"]),
                retrieval_count=len(run["search_executions"]),
                valid_evidence_count=len(run["final_evidence"]),
                stale_evidence_count=len(trace.get("stale_reasons") or ()),
                context_span_count=len(run["final_evidence"]),
                context_truncated=bool(trace.get("context_truncated", False)),
                repair_used=bool(trace.get("repair_used", False)),
                latency_ms=float(trace.get("latency_ms") or trace.get("total_latency_ms") or 0),
                termination_reason=run["termination_reason"],
                decision_rounds=int(trace.get("decision_rounds") or 0),
                tool_calls=int(trace.get("tool_calls") or 0),
                visited_video_count=int(trace.get("visited_video_count") or 0),
                visited_segment_count=int(trace.get("visited_segment_count") or 0),
                navigation_result_count=int(trace.get("navigation_result_count") or 0),
                evidence_candidate_dropped_count=int(
                    trace.get("evidence_candidate_dropped_count") or 0
                ),
            ),
            candidate_disclosure=self._candidate_disclosure(run_id),
            trust_summary=trust,
            answer_version=answer_version,
        )

    def get_trace(self, run_id: str) -> dict[str, object] | None:
        durable = self.run_store.get_trace(run_id)
        if durable is not None:
            durable["candidate_disclosure"] = self._candidate_disclosure(
                run_id
            ).model_dump(mode="json")
            return durable
        return None

    def _candidate_disclosure(self, run_id: str) -> RetrievedCandidateDisclosure:
        try:
            return self.candidate_projector.project(run_id)
        except Exception:
            return RetrievedCandidateDisclosure(
                inspected_search_trace_count=0,
                available_presentation_count=0,
                failed_or_unavailable_trace_count=0,
                reconstructed_candidate_count=0,
                empty_reason="candidate_reconstruction_failed",
            )


def _milliseconds(started: float) -> float:
    return round((time.monotonic() - started) * 1000, 3)


def _continuation_failure(outcome: str | None) -> ContinuationFailureState:
    return {
        "evidence_insufficient": ContinuationFailureState.EVIDENCE_INSUFFICIENT,
        "evidence_unavailable": ContinuationFailureState.EVIDENCE_UNAVAILABLE,
        "generation_failed": ContinuationFailureState.GENERATION_FAILURE,
    }.get(str(outcome), ContinuationFailureState.NONE)


def _answer_event_payload(response: AskResponse) -> dict[str, object]:
    return {
        "answer_version": response.answer_version,
        "status": response.status,
        "execution_outcome": response.execution_outcome,
        "answer_blocks": [
            value.model_dump(mode="json") for value in response.answer_blocks
        ],
        "citations": [value.model_dump(mode="json") for value in response.citations],
        "limitations": list(response.limitations),
        "trust_summary": (
            response.trust_summary.model_dump(mode="json")
            if response.trust_summary is not None
            else None
        ),
    }
