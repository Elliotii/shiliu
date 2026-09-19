from __future__ import annotations

import time
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
from shiliu.ask.context import TranscriptContextBuilder
from shiliu.ask.contracts import AskRequest, AskResponse, AnswerTrustSummary, TraceSummary
from shiliu.ask.deep.budget import DeepSearchBudget
from shiliu.ask.deep.contracts import DeepSearchState
from shiliu.ask.deep.decision import AgentDecisionService
from shiliu.ask.deep.graph import DeepSearchGraph
from shiliu.ask.deep.navigation import NavigationService
from shiliu.ask.deep.policy import DEEP_POLICY_VERSION
from shiliu.ask.deep.reducer import DeepStateReducer
from shiliu.ask.deep.transcript import (
    TranscriptSearchService,
    TranscriptWindowReader,
)
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.ask.finalize import AnswerFinalizer
from shiliu.ask.trust import provider_free_soft_review
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
from shiliu.retrieval.product_search import ProductSearchService


_SAFE_ZERO_EVIDENCE_CONTINUATION_STOPS = frozenset(
    {
        "no_new_evidence",
        "repeated_search",
        "evidence_unavailable",
        "budget_exhausted",
    }
)


class DeepSearchService:
    def __init__(
        self,
        *,
        db: Database,
        artifacts: ArtifactStore,
        product_search: ProductSearchService,
        provider_factory: Callable[[str], object],
        runtime_corpus_identity: str | None = None,
        evidence_search: EvidenceSearchService | None = None,
        materializer: TranscriptEvidenceMaterializer | None = None,
        context_builder: TranscriptContextBuilder | None = None,
        finalizer: AnswerFinalizer | None = None,
        budget: DeepSearchBudget | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.db = db
        self.run_store = AskRunStore(db)
        self.artifacts = artifacts
        self.product_search = product_search
        self.provider_factory = provider_factory
        self.clock = clock
        self.budget = budget or DeepSearchBudget()
        self.evidence_search = evidence_search or EvidenceSearchService(
            db=db,
            product_search=product_search,
            authority_mode="live_current_exact_replay",
            runtime_corpus_identity=runtime_corpus_identity,
        )
        self.materializer = materializer or TranscriptEvidenceMaterializer(db)
        self.context_builder = context_builder or TranscriptContextBuilder(
            total_character_budget=self.budget.final_evidence_context_chars
        )
        self.answer_service = GroundedAnswerService(
            provider_factory, self.materializer
        )
        self.finalizer = finalizer or AnswerFinalizer(
            context_builder=self.context_builder,
            answer_service=self.answer_service,
            materializer=self.materializer,
        )
        reducer = DeepStateReducer(self.budget)
        self.graph = DeepSearchGraph(
            decision_service=AgentDecisionService(
                provider_factory, self.budget, clock=clock
            ),
            navigation=NavigationService(
                db=db, artifacts=artifacts, product_search=product_search
            ),
            transcripts=TranscriptSearchService(
                evidence_search=self.evidence_search,
                materializer=self.materializer,
                max_spans_per_search=6,
                max_characters_per_search=max(
                    1, self.budget.final_evidence_context_chars // 2
                ),
            ),
            windows=TranscriptWindowReader(db, self.materializer),
            reducer=reducer,
            budget=self.budget,
            clock=clock,
        )

    def ask(
        self,
        request: AskRequest,
        *,
        evidence_decision: EvidenceDecision | None = None,
        continuation_envelope: ContinuationEnvelope | None = None,
    ) -> tuple[AskResponse, dict[str, object]]:
        if (evidence_decision is None) != (continuation_envelope is None):
            raise ContinuationContractError(
                "canonical decision and continuation envelope are required together",
                code="continuation_pair_required",
            )
        if evidence_decision is not None and continuation_envelope is not None:
            validate_continuation_consumption(
                evidence_decision,
                continuation_envelope,
                current_question=request.query,
                current_scope=request.filters.model_dump(mode="json", exclude_none=True),
                target=ContinuationTarget.DEEP,
            )
            if decision_directive(evidence_decision) == "stop":
                raise ContinuationContractError(
                    "canonical action cannot enter the Deep execution boundary",
                    code="continuation_action_boundary",
                )
        started = self.clock()
        run_id = f"ask_run_{uuid4().hex}"
        created_at = self.run_store.start(
            run_id=run_id,
            query=request.query,
            mode="deep",
            filters=request.filters.model_dump(mode="json", exclude_none=True),
            parent_run_id=(
                continuation_envelope.parent_run_id
                if continuation_envelope is not None
                else None
            ),
        )
        self.run_store.append_event(
            run_id,
            "run_created",
            {"mode": "deep", "query_hash": sha256_identity(request.query)},
        )
        try:
            return self._execute(
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

    def execute_started(
        self,
        request: AskRequest,
        *,
        run_id: str,
        created_at: str,
    ) -> tuple[AskResponse, dict[str, object]]:
        """Execute a Deep run whose durable identity was allocated by the API."""

        started = self.clock()
        try:
            return self._execute(
                request,
                run_id=run_id,
                created_at=created_at,
                started=started,
            )
        except Exception as exc:
            self.run_store.fail(run_id, exc)
            raise

    def _execute(
        self,
        request: AskRequest,
        *,
        run_id: str,
        created_at: str,
        started: float,
        evidence_decision: EvidenceDecision | None = None,
        continuation_envelope: ContinuationEnvelope | None = None,
    ) -> tuple[AskResponse, dict[str, object]]:
        if (evidence_decision is None) != (continuation_envelope is None):
            raise ValueError("canonical decision and continuation envelope are required together")
        state = self._initial_state(run_id, request, started)
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
            state["evidence_spans"] = list(inherited.spans)
            state["visited_video_ids"] = list(
                dict.fromkeys(value.video_id for value in inherited.spans)
            )
            state["visited_segment_ids"] = list(
                dict.fromkeys(
                    segment_id
                    for value in inherited.spans
                    for segment_id in value.segment_ids
                )
            )
            inherited_dropped.extend(inherited.dropped_reference_ids)
            working_envelope = create_continuation_envelope(
                parent_run_id=continuation_envelope.parent_run_id,
                parent_decision=active_decision,
                target=ContinuationTarget.DEEP,
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
                state["evidence_spans"] = list(refreshed.spans)
                adaptive_rounds = [
                    value.model_dump(mode="json")
                    for value in refreshed.execution.rounds
                ]
                adaptive_stop_reason = refreshed.execution.stop_reason.value
                for reference in refreshed.execution.search_executions:
                    state["events"].append(
                        {
                            "event_type": "adaptive_targeted_refresh",
                            "search_executions": [reference.model_dump(mode="json")],
                        }
                    )
            state["open_questions"] = [
                value.description
                for value in active_decision.requirements
                if value.aspect_id in active_decision.open_aspects
            ] or [request.query]
            state["events"].append(
                {
                    "event_type": "canonical_evidence_decision_consumed",
                    "decision_id": active_decision.decision_id,
                    "action": active_decision.action.value,
                    "directive": decision_directive(active_decision),
                    "provider_authority_inherited": False,
                }
            )
        executed_deep_research = (
            active_decision is None
            or decision_directive(active_decision) == "deep_research"
        )
        parent_decision = active_decision
        if executed_deep_research:
            state = self.graph.run(state)
        else:
            state["termination_reason"] = (
                "answer_ready"
                if decision_directive(active_decision) == "finalize"
                else "no_new_evidence"
            )
        termination_reason = state["termination_reason"] or "budget_exhausted"
        if active_decision is None:
            active_decision = create_current_evidence_decision(
                question=request.query,
                filters=request.filters,
                spans=state["evidence_spans"],
            )
        elif executed_deep_research and parent_decision is not None:
            active_decision = create_current_evidence_decision(
                question=request.query,
                filters=request.filters,
                spans=state["evidence_spans"],
                requirements=parent_decision.requirements,
                parent_decision_id=parent_decision.decision_id,
                existing_reference_ids={
                    reference.reference_id
                    for value in parent_decision.coverage
                    for reference in value.authority_references
                },
                inherited_contributions=parent_decision.contributions,
            )
        for event in state["events"]:
            event_type = str(event.get("event_type") or "deep_round_completed")
            search_ids = [
                str(value.get("execution_id"))
                for value in event.get("search_executions", [])
                if isinstance(value, dict) and value.get("execution_id")
            ]
            self.run_store.append_event(
                run_id,
                event_type,
                {key: value for key, value in event.items() if key != "event_type"},
                provenance={
                    "search_execution_ids": search_ids,
                    "decision_ids": (
                        [str(event["decision_id"])] if event.get("decision_id") else []
                    ),
                },
            )
        zero_evidence_continuation_terminal = (
            evidence_decision is not None
            and executed_deep_research
            and not state["evidence_spans"]
            and not state["errors"]
            and termination_reason in _SAFE_ZERO_EVIDENCE_CONTINUATION_STOPS
        )
        if (
            evidence_decision is not None
            and decision_directive(active_decision) != "finalize"
            and not zero_evidence_continuation_terminal
        ):
            raise ContinuationContractError(
                "continuation did not reach a Deep-finalizable action",
                code="continuation_action_boundary",
            )
        evidence_ids = list(
            dict.fromkeys(value.citation_id for value in state["evidence_spans"])
        )
        self.run_store.append_event(
            run_id,
            "evidence_batch_ready",
            {
                "current_evidence_count": len(evidence_ids),
                "stale_evidence_count": len(state["stale_reasons"]),
                "deep_round_count": state["decision_rounds"],
            },
            provenance={"evidence_reference_ids": evidence_ids},
        )
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
        finalization_started = self.clock()
        answer_deadline = min(
            state["total_deadline"],
            finalization_started + self.budget.final_answer_reserve_seconds,
        )
        final = self.finalizer.finalize(
            query=request.query,
            normalized_intent=request.query,
            spans=state["evidence_spans"],
            stale_reasons=state["stale_reasons"],
            termination_reason=termination_reason,
            retrieval_errors=state["errors"],
            deadline=answer_deadline,
            clock=self.clock,
            downgrade_for_search_stop=True,
            run_id=run_id,
            event_sink=lambda event_type, payload: self.run_store.append_event(
                run_id, event_type, payload
            ),
        )
        dropped_evidence_count = sum(
            int(value.get("dropped_evidence_count", 0))
            for value in state["events"]
            if value.get("event_type") == "observation"
        )
        latency_ms = round((self.clock() - started) * 1000, 3)
        summary = TraceSummary(
            query_count=len(state["previous_queries"]),
            retrieval_count=sum(
                1
                for value in state["events"]
                if value.get("observation_kind") == "transcript_search"
            ),
            valid_evidence_count=final.valid_evidence_count,
            stale_evidence_count=final.stale_evidence_count,
            context_span_count=final.context_span_count,
            context_truncated=final.context_truncated,
            repair_used=final.repair_used,
            latency_ms=latency_ms,
            termination_reason=final.termination_reason,
            decision_rounds=state["decision_rounds"],
            tool_calls=state["tool_calls"],
            visited_video_count=len(state["visited_video_ids"]),
            visited_segment_count=len(state["visited_segment_ids"]),
            navigation_result_count=state["navigation_result_count"],
            evidence_candidate_dropped_count=dropped_evidence_count,
        )
        response = AskResponse(
            run_id=run_id,
            mode="deep",
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
                {
                    "answer_version": 1,
                    "status": response.status,
                    "execution_outcome": response.execution_outcome,
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
                },
                provenance={
                    "evidence_reference_ids": [
                        value.citation_id for value in response.citations
                    ]
                },
            )
            self.run_store.append_event(
                run_id,
                "soft_review_started",
                {"answer_version": 1, "provider_calls": 0, "searches": 0},
            )
            by_citation = {
                value.citation_id: value for value in state["evidence_spans"]
            }
            review = provider_free_soft_review(
                answer_blocks=response.answer_blocks,
                citations=response.citations,
                limitations=response.limitations,
                status=response.status,
                decision_projection=decision_projection(active_decision),
                validate_citation=lambda citation_id: self.materializer.validate_current(
                    by_citation[citation_id]
                ),
            )
            if review.changed:
                trust_summary = (
                    response.trust_summary.model_copy(
                        update={
                            "answer_version": review.answer_version,
                            "previous_answer_snapshot_hash": review.previous_answer_snapshot_hash,
                            "answer_snapshot_hash": review.answer_snapshot_hash,
                        }
                    )
                    if response.trust_summary is not None
                    else None
                )
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
                run_id, "soft_review_skipped", {"reason": "no_trusted_body"}
            )
        search_executions = _deep_search_executions(state["events"])
        final_evidence = final_evidence_identities(
            state["evidence_spans"],
            {value.citation_id for value in response.citations},
        )
        provider_usage = {
            "agent_actions": state["usage"],
            "answer": final.trace.get("answer_usage", []),
        }
        trace: dict[str, object] = {
            "run_id": run_id,
            "created_at": created_at,
            "query": request.query,
            "mode": "deep",
            "policy_version": DEEP_POLICY_VERSION,
            "started_at": started,
            "budget": self.budget.__dict__,
            "finalization_started_at": finalization_started,
            "answer_deadline": answer_deadline,
            "events": state["events"],
            "search_executions": search_executions,
            "stale_reasons": state["stale_reasons"],
            "errors": state["errors"],
            "termination_reason": response.termination_reason,
            "status": response.status,
            "execution_outcome": response.execution_outcome,
            "decision_rounds": state["decision_rounds"],
            "tool_calls": state["tool_calls"],
            "visited_video_count": len(state["visited_video_ids"]),
            "visited_segment_count": len(state["visited_segment_ids"]),
            "navigation_result_count": state["navigation_result_count"],
            "evidence_count": len(state["evidence_spans"]),
            "evidence_candidate_dropped_count": dropped_evidence_count,
            "total_latency_ms": latency_ms,
            "usage": state["usage"],
            "provider_usage": provider_usage,
            "open_questions": list(state["open_questions"]),
            "resolved_questions": list(state["resolved_questions"]),
            "visited_video_ids": list(state["visited_video_ids"]),
            "visited_segment_ids": list(state["visited_segment_ids"]),
            "guard_state": {
                "previous_queries": list(state["previous_queries"]),
                "repeated_action_keys": list(state["repeated_action_keys"]),
                "consecutive_no_new_evidence": state[
                    "consecutive_no_new_evidence"
                ],
                "decision_rounds": state["decision_rounds"],
                "tool_calls": state["tool_calls"],
            },
            "finalization": final.trace,
            "evidence_decision": decision_projection(active_decision),
            "evidence_decision_action": active_decision.action.value,
            "adaptive_directive": decision_directive(active_decision),
            "adaptive_rounds": adaptive_rounds,
            "adaptive_stop_reason": adaptive_stop_reason,
            "inherited_dropped_reference_ids": inherited_dropped,
            "final_evidence": final_evidence,
            "citation_ids": [
                value.citation_id for value in response.citations
            ],
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
        }
        continuation = envelope_for_completed_run(
            run_id=run_id,
            decision=active_decision,
            target=ContinuationTarget.RESEARCH,
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
                "strategy": "deep_agent_decisions",
                "open_questions": list(state["open_questions"]),
                "resolved_questions": list(state["resolved_questions"]),
            },
            rewrites=[],
            search_executions=search_executions,
            final_evidence=final_evidence,
            citations=trace["citations"],
            answer_blocks=trace["answer_blocks"],
            limitations=response.limitations,
            usage_summary=provider_usage,
            events=(),
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
        return response, trace

    def _initial_state(
        self, run_id: str, request: AskRequest, started: float
    ) -> DeepSearchState:
        return {
            "run_id": run_id,
            "query": request.query,
            "filters": request.filters,
            "open_questions": [request.query],
            "resolved_questions": [],
            "evidence_spans": [],
            "navigation_documents": [],
            "visited_video_ids": [],
            "visited_segment_ids": [],
            "previous_queries": [],
            "repeated_action_keys": [],
            "decision_rounds": 0,
            "tool_calls": 0,
            "consecutive_no_new_evidence": 0,
            "navigation_result_count": 0,
            "started_at": started,
            "search_deadline": started + self.budget.search_phase_cutoff_seconds,
            "total_deadline": started + self.budget.total_runtime_seconds,
            "last_action": None,
            "last_observation_summary": "",
            "pending_observation": None,
            "errors": [],
            "stale_reasons": [],
            "events": [],
            "usage": [],
            "termination_reason": None,
        }


def _deep_search_executions(
    events: list[dict[str, object]],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    decision_sequence: int | None = None
    for event in events:
        if event.get("event_type") == "decision":
            value = event.get("decision_round")
            decision_sequence = int(value) if isinstance(value, int) else None
        references = event.get("search_executions")
        if not isinstance(references, list):
            continue
        for reference in references:
            if not isinstance(reference, dict) or not reference.get(
                "search_trace_id"
            ):
                continue
            result.append(
                {
                    "relation_kind": "deep_search",
                    "decision_sequence": decision_sequence,
                    "execution_id": reference.get("execution_id"),
                    "search_trace_id": reference["search_trace_id"],
                    "trace_persisted": bool(
                        reference.get("trace_persisted", True)
                    ),
                    "trace_error": reference.get("trace_error"),
                    "query": reference.get("query") or "",
                }
            )
    return result


def _continuation_failure(outcome: str | None) -> ContinuationFailureState:
    return {
        "evidence_insufficient": ContinuationFailureState.EVIDENCE_INSUFFICIENT,
        "evidence_unavailable": ContinuationFailureState.EVIDENCE_UNAVAILABLE,
        "generation_failed": ContinuationFailureState.GENERATION_FAILURE,
    }.get(str(outcome), ContinuationFailureState.NONE)
