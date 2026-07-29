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
        trace: dict[str, object] = {
            "run_id": run_id,
            "query": request.query,
            "mode": "deep",
            "policy_version": DEEP_POLICY_VERSION,
            "started_at": started,
            "budget": self.budget.__dict__,
            "finalization_started_at": finalization_started,
            "answer_deadline": answer_deadline,
            "events": state["events"],
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
            "finalization": final.trace,
            "citation_ids": [
                value.citation_id for value in response.citations
            ],
        }
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
