from __future__ import annotations

import time
from typing import Callable
from uuid import uuid4

from shiliu.artifacts import ArtifactStore
from shiliu.ask.answer import GroundedAnswerService
from shiliu.ask.context import TranscriptContextBuilder
from shiliu.ask.contracts import AskRequest, AskResponse, TraceSummary
from shiliu.ask.deep.service import DeepSearchService
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.ask.finalize import AnswerFinalizer
from shiliu.ask.query_analysis import QueryAnalyzer
from shiliu.ask.persistence import AskRunStore, final_evidence_identities
from shiliu.db import Database
from shiliu.evidence.search import EvidenceSearchService
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
    ) -> None:
        self.db = db
        self.run_store = AskRunStore(db)
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
    def ask(self, request: AskRequest) -> AskResponse:
        if request.mode == "deep":
            if self.deep_service is None:
                raise AskModeNotImplemented(
                    "Deep Search 缺少 ArtifactStore 接线"
                )
            response, _trace = self.deep_service.ask(request)
            return response
        return self._ask_fast(request)

    def _ask_fast(self, request: AskRequest) -> AskResponse:
        started = time.monotonic()
        run_id = f"ask_run_{uuid4().hex}"
        created_at = self.run_store.start(
            run_id=run_id,
            query=request.query,
            mode="fast",
            filters=request.filters.model_dump(mode="json", exclude_none=True),
        )
        try:
            return self._execute_fast(
                request, run_id=run_id, created_at=created_at, started=started
            )
        except Exception as exc:
            self.run_store.fail(run_id, exc)
            raise

    def _execute_fast(
        self,
        request: AskRequest,
        *,
        run_id: str,
        created_at: str,
        started: float,
    ) -> AskResponse:
        plan = self.query_analyzer.analyze(request.query)
        all_spans = []
        stale_reasons: list[str] = []
        retrieval_errors: list[str] = []
        search_references: list[dict[str, object]] = []
        for query_index, query in enumerate(plan.queries):
            retrieval_request = ProductSearchRequest(
                query=query,
                mode="auto",
                scope="transcript_chunk",
                result_limit=10,
                max_windows_per_video=2,
                filters=request.filters,
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

        trace: dict[str, object] = {
            "run_id": run_id,
            "created_at": created_at,
            "query": request.query,
            "mode": "fast",
            "normalized_intent": plan.analysis.normalized_intent,
            "queries": list(plan.queries),
            "query_analysis_error": plan.error,
            "query_analysis_usage": plan.usage,
            "query_analysis_latency_ms": plan.latency_ms,
            "query_analysis_finish_reason": plan.finish_reason,
            "query_analysis_retry_count": plan.retry_count,
            "search_executions": search_references,
            "retrieval_errors": retrieval_errors,
            "stale_reasons": stale_reasons,
        }
        final = self.finalizer.finalize(
            query=request.query,
            normalized_intent=plan.analysis.normalized_intent,
            spans=all_spans,
            stale_reasons=stale_reasons,
            termination_reason="answer_ready",
            retrieval_errors=retrieval_errors,
        )
        trace.update(final.trace)
        latency_ms = _milliseconds(started)
        summary = TraceSummary(
            query_count=len(plan.queries),
            retrieval_count=len(plan.queries),
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
                "provider_usage": {
                    "query_analysis": plan.usage,
                    "answer": final.trace.get("answer_usage", []),
                },
            }
        )
        self.run_store.complete(
            run_id=run_id,
            trace=trace,
            answer_status=response.status,
            termination_reason=response.termination_reason,
            query_analysis={
                **plan.analysis.model_dump(mode="json"),
                "error": plan.error,
                "latency_ms": plan.latency_ms,
                "finish_reason": plan.finish_reason,
                "retry_count": plan.retry_count,
            },
            rewrites=plan.queries,
            search_executions=trace["search_executions"],
            final_evidence=trace["final_evidence"],
            citations=trace["citations"],
            answer_blocks=trace["answer_blocks"],
            limitations=response.limitations,
            usage_summary=trace["provider_usage"],
        )
        return response

    def get_trace(self, run_id: str) -> dict[str, object] | None:
        durable = self.run_store.get_trace(run_id)
        if durable is not None:
            return durable
        return None


def _milliseconds(started: float) -> float:
    return round((time.monotonic() - started) * 1000, 3)
