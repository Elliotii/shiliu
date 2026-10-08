from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from shiliu.ask.answer import (
    BOUNDED_SYNTHESIS_POLICY,
    GenerationPolicy,
    GroundedAnswerService,
)
from shiliu.ask.context import ContextBuildResult, TranscriptContextBuilder, fuse_evidence
from shiliu.ask.contracts import (
    AnswerBlock,
    AnswerExecutionOutcome,
    AnswerStatus,
    Citation,
    TerminationReason,
    TranscriptEvidenceSpan,
)
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.ask.trust import ClaimVerifier, DisabledClaimVerifier, EventSink, apply_answer_trust
from shiliu.ask.validation import ValidationIssue


logger = logging.getLogger(__name__)


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
        claim_verifier: ClaimVerifier | None = None,
    ) -> None:
        self.context_builder = context_builder
        self.answer_service = answer_service
        self.materializer = materializer
        self.claim_verifier = claim_verifier or DisabledClaimVerifier()

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
        decision_projection: Mapping[str, object] | None = None,
        run_id: str = "unpersisted_answer",
        event_sink: EventSink | None = None,
        answer_service: GroundedAnswerService | None = None,
        prepared_context: ContextBuildResult | None = None,
        clarification_requests: tuple[str, ...] = (),
    ) -> FinalizedAnswer:
        resolved_answer_service = answer_service or self.answer_service
        fused = list(prepared_context.spans) if prepared_context is not None else list(fuse_evidence(spans))
        generation_policy = _generation_policy(self.claim_verifier.enabled)
        trace: dict[str, Any] = {
            "valid_evidence_count": len(fused),
            "generation_policy": generation_policy,
        }
        if not fused:
            if clarification_requests and termination_reason in {"answer_ready", "evidence_unavailable"}:
                # Requests for user input are limitations, not uncited factual
                # answer blocks. No generation or citation bypass is needed.
                trace["clarification_requests"] = list(clarification_requests)
                limitations = ["需要你补充以下信息后才能回答：", *clarification_requests]
                if stale_reasons:
                    limitations.append("已有字幕引用失效，未用于事实回答")
                if retrieval_errors:
                    limitations.append("部分或全部检索执行失败")
                return self._insufficient(
                    limitations=limitations,
                    execution_outcome=("evidence_unavailable" if stale_reasons or retrieval_errors
                        else "evidence_insufficient"),
                    termination_reason=termination_reason,
                    stale_count=len(stale_reasons),
                    trace=trace,
                )
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
        context = prepared_context or self.context_builder.build(
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
        if event_sink is not None:
            try:
                event_sink(
                    "evidence_preview",
                    {
                        "items": [
                            span.as_citation().model_dump(mode="json")
                            for span in context.spans[:3]
                        ]
                    },
                )
            except Exception:
                logger.warning(
                    "Evidence preview projection or delivery failed for run %s",
                    run_id,
                    exc_info=True,
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
            answer = resolved_answer_service.answer(
                query=query,
                context=context,
                generation_policy=generation_policy,
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
        limitations = list(answer.draft.limitations)
        status = answer.draft.status
        status, limitations = _merge_explicit_answer_gaps(
            status=status,
            limitations=limitations,
            decision_projection=decision_projection,
        )
        if context.truncated:
            limitations.append("上下文预算已截断部分候选证据")
        trusted = apply_answer_trust(
            run_id=run_id,
            answer_blocks=answer.draft.answer_blocks,
            citations=tuple(value.as_citation() for value in context.spans),
            spans=context.spans,
            status=status,
            limitations=limitations,
            termination_reason=termination_reason,
            validate_current=self.materializer.validate_current,
            verifier=self.claim_verifier,
            event_sink=event_sink,
        )
        repair_used = answer.repair_used
        if (
            trusted.status == "insufficient"
            and not answer.repair_used
            and _repairable_citation_failure(trusted.summary)
        ):
            issues = tuple(
                ValidationIssue(
                    code=reason,
                    path=disposition.answer_block_id,
                    message=(
                        "Use only citation IDs from the current citation_allowlist "
                        "and include at least one ID per answer block"
                    ),
                )
                for disposition in trusted.summary.dispositions
                for reason in disposition.reason_codes
            )
            repair = resolved_answer_service.repair(
                query=query,
                context=context,
                issues=issues,
                deadline=deadline,
                clock=clock,
            )
            repair_used = True
            trace["answer_usage"] = [
                *trace.get("answer_usage", []),
                *repair.usage,
            ]
            trace["repair_calls"] = int(trace.get("repair_calls", 0)) + 1
            trace["answer_provider_call_count"] = int(
                trace.get("answer_provider_call_count", 0)
            ) + repair.provider_call_count
            trace["transport_retry_count"] = int(
                trace.get("transport_retry_count", 0)
            ) + repair.transport_retry_count
            trace["repair_used"] = True
            trace["answer_validation_errors"] = [
                value.as_dict() for value in repair.validation_errors
            ]
            trace["answer_provider_error"] = repair.provider_error
            trace["provider_error_code"] = repair.provider_error_code
            if repair.draft is not None and repair.draft.status != "insufficient":
                repaired_limitations = list(repair.draft.limitations)
                repaired_status, repaired_limitations = _merge_explicit_answer_gaps(
                    status=repair.draft.status,
                    limitations=repaired_limitations,
                    decision_projection=decision_projection,
                )
                if context.truncated:
                    repaired_limitations.append(
                        "上下文预算已截断部分候选证据"
                    )
                trusted = apply_answer_trust(
                    run_id=run_id,
                    answer_blocks=repair.draft.answer_blocks,
                    citations=tuple(
                        value.as_citation() for value in context.spans
                    ),
                    spans=context.spans,
                    status=repaired_status,
                    limitations=repaired_limitations,
                    termination_reason=termination_reason,
                    validate_current=self.materializer.validate_current,
                    verifier=self.claim_verifier,
                    event_sink=event_sink,
                )
        trace["trust_summary"] = trusted.summary.model_dump(mode="json")
        return FinalizedAnswer(
            status=trusted.status,
            execution_outcome=trusted.execution_outcome,
            answer_blocks=trusted.answer_blocks,
            citations=trusted.citations,
            limitations=trusted.limitations,
            termination_reason=trusted.termination_reason,
            valid_evidence_count=len(fused),
            context_span_count=len(context.spans),
            context_truncated=context.truncated,
            stale_evidence_count=len(stale_reasons),
            repair_used=repair_used,
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
        "tool_budget_exhausted": "本次搜索已达到工具执行预算",
        "controller_budget_exhausted": "本次搜索已达到决策调用预算",
        "invalid_structured_output": "决策输出未通过结构校验，已保留现有证据",
        "timeout": "本次搜索已达到时间边界",
        "cancelled": "本次搜索已取消",
        "no_new_evidence": "继续搜索没有发现新的有效字幕证据",
        "repeated_search": "后续搜索开始重复已有结果",
        "provider_error": "模型服务未能生成可验证的结构化回答",
        "evidence_unavailable": "相关线索的当前字幕证据不可用或已过期",
        "answer_ready": "本次检索未找到足以回答该问题的可靠字幕证据",
    }[termination_reason]


def _generation_policy(verifier_enabled: bool) -> GenerationPolicy:
    return BOUNDED_SYNTHESIS_POLICY


def _repairable_citation_failure(summary: object) -> bool:
    dispositions = getattr(summary, "dispositions", ())
    if not dispositions:
        return False
    repairable = {"citation_missing", "citation_not_allowed", "citation_unmapped"}
    reasons = {
        reason
        for disposition in dispositions
        for reason in disposition.reason_codes
    }
    return bool(reasons) and reasons.issubset(repairable)


def _merge_explicit_answer_gaps(
    *,
    status: AnswerStatus,
    limitations: list[str],
    decision_projection: Mapping[str, object] | None,
) -> tuple[AnswerStatus, list[str]]:
    """Merge only explicit answer gaps before the Trust result is finalized."""

    merged = list(limitations)
    open_aspects = tuple(
        str(value)
        for value in ((decision_projection or {}).get("open_aspects") or ())
    )
    conflicts = tuple((decision_projection or {}).get("conflicts") or ())
    confirmed_conflicts = tuple(
        value
        for value in conflicts
        if isinstance(value, Mapping)
        and str(value.get("status") or "") == "confirmed"
    )
    if open_aspects:
        merged.append(f"仍有 {len(open_aspects)} 个证据方面未覆盖")
    if confirmed_conflicts:
        merged.append(f"检测到 {len(confirmed_conflicts)} 个待处理冲突")
    merged = list(dict.fromkeys(merged))
    if status == "complete" and (limitations or open_aspects or confirmed_conflicts):
        status = "partial"
    return status, merged
