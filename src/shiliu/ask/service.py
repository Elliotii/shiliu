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
        self._traces: dict[str, dict[str, object]] = {}

    def ask(self, request: AskRequest) -> AskResponse:
        if request.mode == "deep":
            if self.deep_service is None:
                raise AskModeNotImplemented(
                    "Deep Search 缺少 ArtifactStore 接线"
                )
            response, trace = self.deep_service.ask(request)
            self._traces[response.run_id] = trace
            return response
        return self._ask_fast(request)

    def _ask_fast(self, request: AskRequest) -> AskResponse:
        started = time.monotonic()
        run_id = f"ask_run_{uuid4().hex}"
        plan = self.query_analyzer.analyze(request.query)
        all_spans = []
        stale_reasons: list[str] = []
        retrieval_errors: list[str] = []
        executions = []
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
                executions.append(execution)
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

        trace: dict[str, object] = {
            "run_id": run_id,
            "query": request.query,
            "mode": "fast",
            "normalized_intent": plan.analysis.normalized_intent,
            "queries": list(plan.queries),
            "query_analysis_error": plan.error,
            "query_analysis_usage": plan.usage,
            "query_analysis_latency_ms": plan.latency_ms,
            "query_analysis_finish_reason": plan.finish_reason,
            "query_analysis_retry_count": plan.retry_count,
            "search_executions": [
                {
                    "execution_id": value.execution_id,
                    "search_trace_id": value.raw_response.trace_id,
                    "query": value.request.query,
                }
                for value in executions
            ],
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
            answer_blocks=list(final.answer_blocks),
            citations=list(final.citations),
            limitations=list(final.limitations),
            termination_reason=final.termination_reason,
            trace_summary=summary,
        )
        trace.update(
            {
                "status": response.status,
                "termination_reason": response.termination_reason,
                "latency_ms": latency_ms,
                "citation_ids": [
                    value.citation_id for value in response.citations
                ],
            }
        )
        self._traces[run_id] = trace
        return response

    def get_trace(self, run_id: str) -> dict[str, object] | None:
        value = self._traces.get(run_id)
        return dict(value) if value is not None else None


def _milliseconds(started: float) -> float:
    return round((time.monotonic() - started) * 1000, 3)
