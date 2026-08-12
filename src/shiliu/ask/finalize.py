from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable

from shiliu.ask.answer import GroundedAnswerService
from shiliu.ask.context import TranscriptContextBuilder, fuse_evidence
from shiliu.ask.contracts import (
    AnswerBlock,
    AnswerExecutionOutcome,
    AnswerStatus,
    Citation,
    TerminationReason,
    TranscriptEvidenceSpan,
)
from shiliu.ask.evidence import TranscriptEvidenceMaterializer


@dataclass(frozen=True)
class FinalizedAnswer:
    status: AnswerStatus
    execution_outcome: AnswerExecutionOutcome
    answer_blocks: tuple[AnswerBlock, ...]
    citations: tuple[Citation, ...]
    limitations: tuple[str, ...]
    termination_reason: TerminationReason
    valid_evidence_count: int
    context_span_count: int
    context_truncated: bool
    stale_evidence_count: int
    repair_used: bool
    trace: dict[str, Any]


class AnswerFinalizer:
    """Shared Fast/Deep transcript-only answer and citation finalization."""

    def __init__(
        self,
        *,
        context_builder: TranscriptContextBuilder,
        answer_service: GroundedAnswerService,
        materializer: TranscriptEvidenceMaterializer,
    ) -> None:
        self.context_builder = context_builder
        self.answer_service = answer_service
        self.materializer = materializer

    def finalize(
        self,
        *,
        query: str,
        normalized_intent: str,
        spans: list[TranscriptEvidenceSpan],
        stale_reasons: list[str],
        termination_reason: TerminationReason,
        retrieval_errors: list[str] | None = None,
        deadline: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        downgrade_for_search_stop: bool = False,
    ) -> FinalizedAnswer:
        fused = list(fuse_evidence(spans))
        trace: dict[str, Any] = {"valid_evidence_count": len(fused)}
        if not fused:
            limitations = ["没有找到可绑定当前字幕版本的有效证据"]
            if retrieval_errors:
                limitations.append("部分或全部检索执行失败")
            return self._insufficient(
                limitations=limitations,
                execution_outcome="evidence_unavailable",
                termination_reason=(
                    "evidence_unavailable"
                    if termination_reason == "answer_ready"
                    else termination_reason
                ),
                stale_count=len(stale_reasons),
                trace=trace,
            )
        context = self.context_builder.build(
            query=query,
            normalized_intent=normalized_intent,
            spans=fused,
        )
        trace.update(
            {
                "context_span_count": len(context.spans),
                "context_truncated": context.truncated,
                "context_dropped_span_count": context.dropped_span_count,
                "citation_allowlist": list(context.citation_allowlist),
            }
        )
        if not context.spans:
            return self._insufficient(
                limitations=["有效字幕证据超过上下文预算，无法安全生成回答"],
                execution_outcome="evidence_unavailable",
                termination_reason=(
                    "evidence_unavailable"
                    if termination_reason == "answer_ready"
                    else termination_reason
                ),
                stale_count=len(stale_reasons),
                trace=trace,
                context_truncated=True,
            )
        if deadline is not None and clock() >= deadline:
            return self._insufficient(
                limitations=["深入搜索总运行时间已耗尽，未启动最终回答"],
                execution_outcome="generation_failed",
                termination_reason="budget_exhausted",
                stale_count=len(stale_reasons),
                trace=trace,
                context_span_count=len(context.spans),
                context_truncated=context.truncated,
            )
        try:
            answer = self.answer_service.answer(
                query=query,
                context=context,
                deadline=deadline,
                clock=clock,
            )
        except Exception as exc:
            trace.update(
                {
                    "answer_calls": 1,
                    "repair_calls": 0,
                    "answer_provider_call_count": 0,
                    "transport_retry_count": 0,
                    "repair_used": False,
                    "provider_error_code": str(
                        getattr(exc, "code", type(exc).__name__)
                    ),
                    "answer_provider_error": f"{type(exc).__name__}: {exc}"[:500],
                }
            )
            return self._insufficient(
                limitations=["模型服务未能生成可验证的结构化回答"],
                execution_outcome="generation_failed",
                termination_reason=(
                    "budget_exhausted"
                    if isinstance(exc, TimeoutError)
                    else "provider_error"
                ),
                stale_count=len(stale_reasons),
                trace=trace,
                context_span_count=len(context.spans),
                context_truncated=context.truncated,
            )
        trace.update(
            {
                "answer_usage": list(answer.usage),
                "answer_calls": answer.answer_calls,
                "repair_calls": answer.repair_calls,
                "answer_provider_call_count": answer.provider_call_count,
                "transport_retry_count": answer.transport_retry_count,
                "repair_used": answer.repair_used,
                "initial_answer_validation_errors": [
                    value.as_dict() for value in answer.initial_validation_errors
                ],
                "initial_answer_provider_error": answer.initial_provider_error,
                "initial_provider_error_code": answer.initial_provider_error_code,
                "answer_validation_errors": [
                    value.as_dict() for value in answer.validation_errors
                ],
                "answer_provider_error": answer.provider_error,
                "provider_error_code": answer.provider_error_code,
            }
        )
        if answer.draft is None:
            return self._insufficient(
                limitations=[
                    (
                        "模型回答在一次修复后仍未通过确定性验证"
                        if answer.repair_used
                        else "模型服务故障，未形成可修复的结构化输出"
                    )
                ],
                execution_outcome="generation_failed",
                termination_reason=(
                    "budget_exhausted"
                    if answer.provider_error_code == "deadline_exhausted"
                    else "provider_error"
                ),
                stale_count=len(stale_reasons),
                trace=trace,
                context_span_count=len(context.spans),
                context_truncated=context.truncated,
                repair_used=answer.repair_used,
            )
        if answer.draft.status == "insufficient":
            limitations = [
                "本次检索未找到足以回答该问题的可靠字幕证据"
            ]
            if context.truncated:
                limitations.append("上下文预算已截断部分候选证据")
            if termination_reason != "answer_ready":
                limitations.append(
                    _insufficient_stop_limitation(termination_reason)
                )
            return self._insufficient(
                limitations=limitations,
                execution_outcome="evidence_insufficient",
                termination_reason=termination_reason,
                stale_count=len(stale_reasons),
                trace=trace,
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
            trace["final_source_revalidation_error"] = (
                f"{type(exc).__name__}: {exc}"[:500]
            )
            return self._insufficient(
                limitations=["回答所用字幕版本在返回前已发生变化"],
                execution_outcome="evidence_unavailable",
                termination_reason="evidence_unavailable",
                stale_count=len(stale_reasons) + 1,
                trace=trace,
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
        if (
            downgrade_for_search_stop
            and termination_reason != "answer_ready"
            and status == "complete"
        ):
            status = "partial"
            limitations.append("深入搜索在确定性停止边界触发后使用已有证据回答")
        return FinalizedAnswer(
            status=status,
            execution_outcome="answer_generated",
            answer_blocks=tuple(answer.draft.answer_blocks),
            citations=tuple(value.as_citation() for value in used_spans),
            limitations=tuple(dict.fromkeys(limitations)),
            termination_reason=termination_reason,
            valid_evidence_count=len(fused),
            context_span_count=len(context.spans),
            context_truncated=context.truncated,
            stale_evidence_count=len(stale_reasons),
            repair_used=answer.repair_used,
            trace=trace,
        )

    @staticmethod
    def _insufficient(
        *,
        limitations: list[str],
        execution_outcome: AnswerExecutionOutcome,
        termination_reason: TerminationReason,
        stale_count: int,
        trace: dict[str, Any],
        context_span_count: int = 0,
        context_truncated: bool = False,
        repair_used: bool = False,
    ) -> FinalizedAnswer:
        return FinalizedAnswer(
            status="insufficient",
            execution_outcome=execution_outcome,
            answer_blocks=(),
            citations=(),
            limitations=tuple(limitations),
            termination_reason=termination_reason,
            valid_evidence_count=int(trace.get("valid_evidence_count", 0)),
            context_span_count=context_span_count,
            context_truncated=context_truncated,
            stale_evidence_count=stale_count,
            repair_used=repair_used,
            trace=trace,
        )


def _insufficient_stop_limitation(
    termination_reason: TerminationReason,
) -> str:
    return {
        "budget_exhausted": "本次搜索已达到确定性预算或时间边界",
        "no_new_evidence": "继续搜索没有发现新的有效字幕证据",
        "repeated_search": "后续搜索开始重复已有结果",
        "provider_error": "模型服务未能生成可验证的结构化回答",
        "evidence_unavailable": "相关线索的当前字幕证据不可用或已过期",
        "answer_ready": "本次检索未找到足以回答该问题的可靠字幕证据",
    }[termination_reason]
