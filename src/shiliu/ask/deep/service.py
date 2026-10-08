from __future__ import annotations

import time
import os
from pathlib import Path
import json
import re
from dataclasses import replace
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
from shiliu.ask.deep.f1_tools import F1Materializer, F1TranscriptTool
from shiliu.ask.deep.v2 import DeepV2ContextBuilder, DeepV2Graph, V2Budget
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.ask.finalize import AnswerFinalizer, FinalizedAnswer
from shiliu.ask.persistence import AskRunStore, final_evidence_identities
from shiliu.ask.trust import ClaimVerifier
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
        "tool_budget_exhausted",
        "controller_budget_exhausted",
        "invalid_structured_output",
        "timeout",
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
        answer_provider_factory: Callable[[str], object] | None = None,
        runtime_corpus_identity: str | None = None,
        evidence_search: EvidenceSearchService | None = None,
        materializer: TranscriptEvidenceMaterializer | None = None,
        context_builder: TranscriptContextBuilder | None = None,
        finalizer: AnswerFinalizer | None = None,
        claim_verifier: ClaimVerifier | None = None,
        budget: DeepSearchBudget | None = None,
        embedding_provider: object | None = None,
        lexical_index_path: Path | None = None,
        v2_budget: V2Budget | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.db = db
        self.run_store = AskRunStore(db)
        self.artifacts = artifacts
        self.product_search = product_search
        self.provider_factory = provider_factory
        self.clock = clock
        self.budget = budget or DeepSearchBudget()
        self.v2_budget = v2_budget or V2Budget()
        self.is_v2 = embedding_provider is not None
        self.evidence_search = evidence_search or EvidenceSearchService(
            db=db,
            product_search=product_search,
            authority_mode="live_current_exact_replay",
            runtime_corpus_identity=runtime_corpus_identity,
        )
        self.materializer = materializer or (F1Materializer(db) if self.is_v2 else TranscriptEvidenceMaterializer(db))
        self.context_builder = (DeepV2ContextBuilder(self.v2_budget.final_context_chars) if self.is_v2
            else context_builder or TranscriptContextBuilder(total_character_budget=self.budget.final_evidence_context_chars))
        self.answer_service = GroundedAnswerService(
            answer_provider_factory or provider_factory, self.materializer
        )
        self.answer_provider_factory = answer_provider_factory or provider_factory
        self.finalizer = (None if self.is_v2 else finalizer) or AnswerFinalizer(
            context_builder=self.context_builder,
            answer_service=self.answer_service,
            materializer=self.materializer,
            claim_verifier=claim_verifier,
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
        if self.is_v2:
            lexical = lexical_index_path or Path(os.environ.get("SHILIU_DEEP_V2_LEXICAL_INDEX",
                str(db.path.parent / "deep-v2-lexical.sqlite")))
            self.graph = DeepV2Graph(
                provider_factory=provider_factory,
                transcripts=F1TranscriptTool(self.evidence_search, embedding_provider, lexical, self.materializer),
                navigation=NavigationService(db=db, artifacts=artifacts, product_search=product_search),
                windows=TranscriptWindowReader(db, self.materializer),
                budget=self.v2_budget, clock=clock,
                cancelled=lambda run_id: self._v2_cancelled(run_id),
            )

    def _v2_cancelled(self, run_id: str) -> bool:
        with self.db.connect() as connection:
            row = connection.execute("SELECT lifecycle_status FROM ask_runs WHERE run_id=?", (run_id,)).fetchone()
        return row is not None and row["lifecycle_status"] != "running"

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
        context_builder = (DeepV2ContextBuilder(self.v2_budget.final_context_chars)
            if self.is_v2 else self.context_builder)
        finalizer = (AnswerFinalizer(context_builder=context_builder,
            answer_service=self.answer_service, materializer=self.materializer,
            claim_verifier=self.finalizer.claim_verifier) if self.is_v2 else self.finalizer)
        if self.is_v2:
            context_builder.preferred_refs = list(dict.fromkeys([
                *state.get("v2_final_refs", []),
                *(ref for need in state.get("v2_needs", {}).values() for ref in need.get("evidence_refs", [])),
            ]))
            # The Query selector has already determined which original chunks
            # are useful. Keep those refs; never fall back to raw Top50 ranks.
            context_builder.candidate_refs = list(dict.fromkeys(
                ref for result in state.get("v2_query_results", [])
                for ref in result.get("retained_evidence_refs", [])))
            context_builder.task_notes = {"outcome": state.get("v2_outcome"),
                "termination_reason": termination_reason,
                "resolved_needs": [need for need in state.get("v2_needs", {}).values()
                    if need["status"] == "supported"],
                "unresolved_needs": [need for need in state.get("v2_needs", {}).values()
                    if need["status"] != "supported"],
                "unresolved_items": state.get("v2_unresolved", []),
                "instruction": "These are investigation notes, not facts. Use transcript quotes for content and source labels or adopted metadata for identity; preserve actual gaps."}
            context_builder.subject_bindings = list({
                json.dumps(finding, sort_keys=True, ensure_ascii=False): finding
                for result in state.get("v2_query_results", [])
                for finding in result.get("findings", []) if finding.get("subject")}.values())
            context_builder.adopted_sources = [{"source_record_id": source_id,
                **{key: source.get(key) for key in
                ("video_id", "title", "uploader", "bvid", "url")}
                } for source_id in dict.fromkeys(state.get("v2_final_source_ids", []))
                if (source := state.get("v2_sources", {}).get(int(source_id.removeprefix("nav:")))) is not None]
            for video_id in {span.video_id for span in state["evidence_spans"]}:
                video = self.db.get_video(video_id)
                if video is not None and any(span.video_id == video_id and span.bvid == video["source_id"]
                                             for span in state["evidence_spans"]):
                    context_builder.source_metadata[video_id] = {"uploader": video.get("uploader")}
        answer_calls = []
        local_answer_service = self.answer_service
        if self.is_v2:
            from shiliu.ask.deep.v2 import AuditedProvider
            local_answer_service = GroundedAnswerService(
                lambda role: AuditedProvider(self.answer_provider_factory(role), answer_calls, self.v2_budget.answer_output_tokens), self.materializer)
        prepared_context = (context_builder.build(query=request.query, normalized_intent=request.query,
            spans=tuple(state["evidence_spans"])) if self.is_v2 else None)
        clarification_requests = _v2_clarification_requests(state) if self.is_v2 else ()
        answer_deadline = min(
            state["total_deadline"],
            finalization_started + self.budget.final_answer_reserve_seconds,
        )
        final = finalizer.finalize(
            query=request.query,
            normalized_intent=request.query,
            spans=state["evidence_spans"],
            stale_reasons=state["stale_reasons"],
            termination_reason=termination_reason,
            retrieval_errors=state["errors"],
            deadline=answer_deadline,
            clock=self.clock,
            downgrade_for_search_stop=True,
            decision_projection=decision_projection(active_decision),
            run_id=run_id,
            event_sink=lambda event_type, payload: self.run_store.append_event(
                run_id, event_type, payload
            ),
            answer_service=local_answer_service,
            prepared_context=prepared_context,
            clarification_requests=clarification_requests,
        )
        if self.is_v2 and state.get("v2_outcome") == "sources_found" and state.get("v2_sources") and not state["evidence_spans"]:
            final = FinalizedAnswer(status="complete", execution_outcome="source_lookup_complete",
                answer_blocks=(), citations=(), limitations=(), termination_reason="answer_ready",
                valid_evidence_count=0, context_span_count=0, context_truncated=False,
                stale_evidence_count=0, repair_used=False,
                trace={"source_lookup": list(state["v2_sources"].values()), "answer_usage": []})
        elif self.is_v2 and final.answer_blocks and state.get("v2_outcome") == "partial":
            final = replace(final, status="partial", limitations=tuple(dict.fromkeys([
                *final.limitations, *(str(item) for item in state.get("v2_unresolved", []) if str(item).strip())])))
        if clarification_requests and final.execution_outcome in {"answer_generated", "evidence_insufficient"}:
            final = replace(final,
                status="partial" if final.answer_blocks else final.status,
                limitations=tuple(dict.fromkeys([
                    *final.limitations, "需要你补充以下信息后才能回答：", *clarification_requests])))
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
                if value.get("observation_kind") == "transcript_search" or value.get("kind") == "search_transcripts"
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
            source_matches=list(state.get("v2_sources", {}).values()) if self.is_v2 else [],
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
            "implementation_version": "deep-v2" if self.is_v2 else "deep-v1",
            "v2_budget": self.v2_budget.__dict__ if self.is_v2 else None,
            "v2_outcome": state.get("v2_outcome"),
            "v2_search_termination_reason": state.get("termination_reason"),
            "v2_unresolved": state.get("v2_unresolved", []),
            "v2_clarification_requests": list(clarification_requests),
            "v2_answer_calls": answer_calls,
            "v2_controller_calls": state.get("v2_controller_calls", 0),
            "v2_query_results": state.get("v2_query_results", []),
            "v2_round_timings": state.get("v2_round_timings", []),
            "provider_cost": {"actual_cost": None, "reason": "Provider usage has no monetary cost field; no price estimate applied."},
            "source_matches": list(state.get("v2_sources", {}).values()) if self.is_v2 else [],
            "v2_final_refs": state.get("v2_final_refs", []),
            "v2_final_source_ids": state.get("v2_final_source_ids", []),
            "v2_context_omitted": getattr(context_builder, "omitted", []),
            "v2_final_context": (context_builder.last_context.model_context
                if self.is_v2 and context_builder.last_context is not None else None),
            "v2_evidence_store": ({ref: {**span.model_dump(mode="json"),
                "segments": [segment.model_dump(mode="json") for segment in span.segments]}
                for ref, span in state.get("v2_store", {}).items()} if self.is_v2 else None),
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
        if self.is_v2:
            trace_dir = Path(os.environ.get("SHILIU_DEEP_V2_TRACE_DIR",
                "/Users/elliot/new-systems/agent-job-prep/Shiliu-retrieval-benchmark-runtime/optimization/deep-v2/runs"))
            trace_dir.mkdir(parents=True, exist_ok=True)
            (trace_dir / f"{run_id}.json").write_text(
                json.dumps(trace, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
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
            "search_deadline": started + (self.v2_budget.search_seconds if self.is_v2 else self.budget.search_phase_cutoff_seconds),
            "total_deadline": started + (self.v2_budget.total_seconds if self.is_v2 else self.budget.total_runtime_seconds),
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


def _v2_clarification_requests(state: dict) -> tuple[str, ...]:
    """Project only an accepted Controller finish requesting user input.

    Query-local gaps and error messages are not clarification requests. Older
    decisions sometimes put the request only in finish_reason; extract its
    explicit request clause rather than exposing the entire reasoning as facts.
    """
    if (state.get("v2_outcome") != "needs_clarification"
            or state.get("termination_reason") != "evidence_unavailable"):
        return ()
    decision = next((event.get("decision", {}) for event in reversed(state.get("events", []))
        if event.get("event_type") == "v2_decision"), {})
    if decision.get("type") != "finish" or decision.get("outcome") != "needs_clarification":
        return ()
    requests = [item.strip() for item in decision.get("unresolved_items", [])
        if isinstance(item, str) and item.strip()]
    if not requests:
        reason = decision.get("finish_reason") or ""
        request = re.search(
            r"(?:需要(?:用户)?(?:知道|补充|提供|说明|确认)|请(?:补充|提供|说明|确认))"
            r"[^。！？\n]*",
            reason,
        )
        if request:
            requests = [request.group().strip()]
    return tuple(dict.fromkeys(requests))
