from __future__ import annotations

import time
from typing import Callable
from uuid import uuid4

from shiliu.artifacts import ArtifactStore
from shiliu.ask.answer import GroundedAnswerService
from shiliu.ask.context import TranscriptContextBuilder
from shiliu.ask.contracts import AskRequest, AskResponse, TraceSummary
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
from shiliu.ask.persistence import AskRunStore, final_evidence_identities
from shiliu.db import Database
from shiliu.evidence.search import EvidenceSearchService
from shiliu.retrieval.product_search import ProductSearchService


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

    def ask(self, request: AskRequest) -> tuple[AskResponse, dict[str, object]]:
        started = self.clock()
        run_id = f"ask_run_{uuid4().hex}"
        created_at = self.run_store.start(
            run_id=run_id,
            query=request.query,
            mode="deep",
            filters=request.filters.model_dump(mode="json", exclude_none=True),
        )
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
    ) -> tuple[AskResponse, dict[str, object]]:
        state = self._initial_state(run_id, request, started)
        state = self.graph.run(state)
        termination_reason = state["termination_reason"] or "budget_exhausted"
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
            answer_blocks=list(final.answer_blocks),
            citations=list(final.citations),
            limitations=list(final.limitations),
            termination_reason=final.termination_reason,
            trace_summary=summary,
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
            "termination_reason": final.termination_reason,
            "status": final.status,
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
        }
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
            events=state["events"],
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
                    "query": reference.get("query") or "",
                }
            )
    return result
