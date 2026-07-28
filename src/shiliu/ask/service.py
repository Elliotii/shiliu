from __future__ import annotations

import time
from typing import Callable
from uuid import uuid4

from shiliu.ask.answer import GroundedAnswerService
from shiliu.ask.context import TranscriptContextBuilder, fuse_evidence
from shiliu.ask.contracts import (
    AskRequest,
    AskResponse,
    TraceSummary,
)
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
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
        self._traces: dict[str, dict[str, object]] = {}

    def ask(self, request: AskRequest) -> AskResponse:
        if request.mode != "fast":
            raise AskModeNotImplemented(
                "Goal 1 只实现 fast 模式；deep 模式将在 Goal 2 实现"
            )
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
                retrieval_errors.append(
                    f"{type(exc).__name__}: {exc}"[:500]
                )

        fused = fuse_evidence(all_spans)
        base_trace: dict[str, object] = {
            "run_id": run_id,
            "query": request.query,
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
            "valid_evidence_count": len(fused),
        }
        if not fused:
            limitations = ["没有找到可绑定当前字幕版本的有效证据"]
            if retrieval_errors:
                limitations.append("部分或全部检索执行失败")
            return self._insufficient(
                run_id=run_id,
                started=started,
                query_count=len(plan.queries),
                retrieval_count=len(plan.queries),
                stale_count=len(stale_reasons),
                termination_reason="evidence_unavailable",
                limitations=limitations,
                trace=base_trace,
            )

        context = self.context_builder.build(
            query=request.query,
            normalized_intent=plan.analysis.normalized_intent,
            spans=fused,
        )
        base_trace.update(
            {
                "context_span_count": len(context.spans),
                "context_truncated": context.truncated,
                "context_dropped_span_count": context.dropped_span_count,
                "citation_allowlist": list(context.citation_allowlist),
            }
        )
        if not context.spans:
            return self._insufficient(
                run_id=run_id,
                started=started,
                query_count=len(plan.queries),
                retrieval_count=len(plan.queries),
                stale_count=len(stale_reasons),
                termination_reason="evidence_unavailable",
                limitations=["有效字幕证据超过上下文预算，无法安全生成回答"],
                trace=base_trace,
                context_truncated=True,
            )

        try:
            answer = self.answer_service.answer(
                query=request.query, context=context
            )
        except Exception as exc:
            base_trace.update(
                {
                    "answer_usage": [],
                    "answer_calls": 1,
                    "repair_calls": 0,
                    "answer_provider_call_count": 0,
                    "transport_retry_count": 0,
                    "repair_used": False,
                    "provider_error_code": str(
                        getattr(exc, "code", type(exc).__name__)
                    ),
                    "answer_provider_error": (
                        f"{type(exc).__name__}: {exc}"[:500]
                    ),
                }
            )
            return self._insufficient(
                run_id=run_id,
                started=started,
                query_count=len(plan.queries),
                retrieval_count=len(plan.queries),
                stale_count=len(stale_reasons),
                termination_reason="provider_error",
                limitations=["模型服务未能生成可验证的结构化回答"],
                trace=base_trace,
                context_span_count=len(context.spans),
                context_truncated=context.truncated,
            )
        base_trace.update(
            {
                "answer_usage": list(answer.usage),
                "answer_calls": answer.answer_calls,
                "repair_calls": answer.repair_calls,
                "answer_provider_call_count": answer.provider_call_count,
                "transport_retry_count": answer.transport_retry_count,
                "repair_used": answer.repair_used,
                "initial_answer_validation_errors": [
                    value.as_dict()
                    for value in answer.initial_validation_errors
                ],
                "initial_answer_provider_error": answer.initial_provider_error,
                "initial_provider_error_code": (
                    answer.initial_provider_error_code
                ),
                "answer_validation_errors": [
                    value.as_dict() for value in answer.validation_errors
                ],
                "answer_provider_error": answer.provider_error,
                "provider_error_code": answer.provider_error_code,
            }
        )
        if answer.draft is None:
            return self._insufficient(
                run_id=run_id,
                started=started,
                query_count=len(plan.queries),
                retrieval_count=len(plan.queries),
                stale_count=len(stale_reasons),
                termination_reason="provider_error",
                limitations=[
                    (
                        "模型回答在一次修复后仍未通过确定性验证"
                        if answer.repair_used
                        else "模型服务故障，未形成可修复的结构化输出"
                    )
                ],
                trace=base_trace,
                context_span_count=len(context.spans),
                context_truncated=context.truncated,
                repair_used=answer.repair_used,
            )

        used_ids = {
            citation_id
            for block in answer.draft.answer_blocks
            for citation_id in block.citation_ids
        }
        used_spans = tuple(
            value for value in context.spans if value.citation_id in used_ids
        )
        try:
            for span in used_spans:
                self.materializer.validate_current(span)
        except Exception as exc:
            base_trace["final_source_revalidation_error"] = (
                f"{type(exc).__name__}: {exc}"[:500]
            )
            return self._insufficient(
                run_id=run_id,
                started=started,
                query_count=len(plan.queries),
                retrieval_count=len(plan.queries),
                stale_count=len(stale_reasons) + 1,
                termination_reason="evidence_unavailable",
                limitations=["回答所用字幕版本在返回前已发生变化"],
                trace=base_trace,
                context_span_count=len(context.spans),
                context_truncated=context.truncated,
                repair_used=answer.repair_used,
            )

        limitations = list(answer.draft.limitations)
        status = answer.draft.status
        if context.truncated:
            limitations.append("上下文预算已截断部分候选证据")
            if status == "complete":
                status = "partial"
        termination_reason = "answer_ready"
        latency_ms = _milliseconds(started)
        summary = TraceSummary(
            query_count=len(plan.queries),
            retrieval_count=len(plan.queries),
            valid_evidence_count=len(fused),
            stale_evidence_count=len(stale_reasons),
            context_span_count=len(context.spans),
            context_truncated=context.truncated,
            repair_used=answer.repair_used,
            latency_ms=latency_ms,
            termination_reason=termination_reason,
        )
        response = AskResponse(
            run_id=run_id,
            mode="fast",
            status=status,
            answer_blocks=answer.draft.answer_blocks,
            citations=[value.as_citation() for value in used_spans],
            limitations=list(dict.fromkeys(limitations)),
            termination_reason=termination_reason,
            trace_summary=summary,
        )
        base_trace.update(
            {
                "status": response.status,
                "termination_reason": termination_reason,
                "latency_ms": latency_ms,
                "citation_ids": [
                    value.citation_id for value in response.citations
                ],
            }
        )
        self._traces[run_id] = base_trace
        return response

    def get_trace(self, run_id: str) -> dict[str, object] | None:
        value = self._traces.get(run_id)
        return dict(value) if value is not None else None

    def _insufficient(
        self,
        *,
        run_id: str,
        started: float,
        query_count: int,
        retrieval_count: int,
        stale_count: int,
        termination_reason: str,
        limitations: list[str],
        trace: dict[str, object],
        context_span_count: int = 0,
        context_truncated: bool = False,
        repair_used: bool = False,
    ) -> AskResponse:
        latency_ms = _milliseconds(started)
        summary = TraceSummary(
            query_count=query_count,
            retrieval_count=retrieval_count,
            valid_evidence_count=int(trace.get("valid_evidence_count", 0)),
            stale_evidence_count=stale_count,
            context_span_count=context_span_count,
            context_truncated=context_truncated,
            repair_used=repair_used,
            latency_ms=latency_ms,
            termination_reason=termination_reason,  # type: ignore[arg-type]
        )
        response = AskResponse(
            run_id=run_id,
            mode="fast",
            status="insufficient",
            answer_blocks=[],
            citations=[],
            limitations=limitations,
            termination_reason=termination_reason,  # type: ignore[arg-type]
            trace_summary=summary,
        )
        trace.update(
            {
                "status": "insufficient",
                "termination_reason": termination_reason,
                "latency_ms": latency_ms,
                "repair_used": repair_used,
            }
        )
        self._traces[run_id] = trace
        return response


def _milliseconds(started: float) -> float:
    return round((time.monotonic() - started) * 1000, 3)
