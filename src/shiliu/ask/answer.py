from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any, Callable, Literal

from shiliu.ask.context import ContextBuildResult
from shiliu.ask.contracts import GroundedAnswerDraft
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.ask.validation import ValidationIssue, validate_grounded_answer


_GROUNDING_BOUNDARY_INSTRUCTIONS = (
    "Retrieval and transcript context are bounded samples; a fact not appearing "
    "in this context does not prove that it is absent from the entire collection. "
    "Distinguish proving a universal claim from refuting one with a direct "
    "counterexample. Finite samples cannot establish that something is always "
    "true, never occurs, or applies across the entire collection. But one current "
    "transcript span that directly contradicts an 'always' claim may support a "
    "finite counterexample conclusion: return status partial, cite that span, and "
    "state that the bounded result is not a complete collection-wide audit. "
    "For other universal or negative-scope questions, make a scope-wide conclusion "
    "only when transcript evidence directly supports that full scope. If neither "
    "the requested fact nor a direct counterexample is supported, return status "
    "insufficient with empty answer_blocks and use the scope-honest limitation "
    "本次检索未找到足以回答该问题的可靠字幕证据. "
    "For cross-video questions, compare only claims directly supported by the "
    "current transcript evidence. A useful finite comparison may be partial merely "
    "because it is not a collection-wide survey; do not reject that comparison for "
    "lack of full-library coverage, and do not inflate missing evidence into a "
    "complete comparison. "
    "Limitations may describe only retrieval scope, evidence gaps, truncation, "
    "Provider failures, or deterministic stop boundaries; they must not carry "
    "uncited material factual claims. Every citation_id must directly support the "
    "complete material statement in its answer block. An ID being present in the "
    "citation allowlist is necessary but not sufficient: never attach it "
    "mechanically, and never combine unrelated samples to claim collection-wide "
    "absence. Each answer block must add a material, non-duplicate point. Prefer "
    "the fewest concise blocks that answer the question; merge overlapping points "
    "when the same citations support them, and avoid restating a prior block."
)


BOUNDED_SYNTHESIS_POLICY = "bounded_grounded_synthesis_v1"
EXACT_EXCERPT_COMPATIBILITY_POLICY = (
    "exact_current_evidence_excerpt_compatibility_v1"
)
GenerationPolicy = Literal[
    "bounded_grounded_synthesis_v1",
    "exact_current_evidence_excerpt_compatibility_v1",
]

_EXACT_EXCERPT_COMPATIBILITY_INSTRUCTIONS = (
    "Exact-excerpt compatibility policy: every returned AnswerBlock must contain "
    "exactly one citation_id in citation_ids. Its text must be a contiguous "
    "verbatim excerpt of that citation's current transcript_evidence.quote_text, "
    "allowing only normalization already accepted by the deterministic trust "
    "gate. Do not paraphrase, synthesize across citations, merge unrelated spans, "
    "or add uncited connective factual claims. If exact current Evidence cannot "
    "truthfully answer the question, return status partial with only supported "
    "exact-excerpt blocks, or status insufficient with empty answer_blocks."
)


@dataclass(frozen=True)
class GroundedAnswerResult:
    draft: GroundedAnswerDraft | None
    repair_used: bool
    usage: tuple[dict[str, Any], ...]
    answer_calls: int
    repair_calls: int
    provider_call_count: int
    transport_retry_count: int
    initial_validation_errors: tuple[ValidationIssue, ...]
    initial_provider_error: str | None
    initial_provider_error_code: str | None
    validation_errors: tuple[ValidationIssue, ...]
    provider_error: str | None
    provider_error_code: str | None


@dataclass(frozen=True)
class _ProviderCallResult:
    draft: GroundedAnswerDraft | None
    error: str | None
    error_code: str | None
    repairable: bool
    transport_retry_count: int


_ROLE_RECOVERY_ERROR_CODES = {
    "output_budget_exhausted",
    "empty_model_output",
}


class GroundedAnswerService:
    def __init__(
        self,
        provider_factory: Callable[[str], object],
        materializer: TranscriptEvidenceMaterializer,
    ) -> None:
        self.provider_factory = provider_factory
        self.materializer = materializer

    def answer(
        self,
        *,
        query: str,
        context: ContextBuildResult,
        generation_policy: GenerationPolicy = BOUNDED_SYNTHESIS_POLICY,
        deadline: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> GroundedAnswerResult:
        usage: list[dict[str, Any]] = []
        try:
            provider = self.provider_factory("grounded_answer")
        except Exception as exc:
            return GroundedAnswerResult(
                draft=None,
                repair_used=False,
                usage=(),
                answer_calls=1,
                repair_calls=0,
                provider_call_count=0,
                transport_retry_count=0,
                initial_validation_errors=(),
                initial_provider_error=_error_text(exc),
                initial_provider_error_code=_error_code(
                    exc, fallback="provider_factory_error"
                ),
                validation_errors=(),
                provider_error=_error_text(exc),
                provider_error_code=_error_code(
                    exc, fallback="provider_factory_error"
                ),
            )
        first_call = self._call(
            provider,
            messages=_answer_messages(
                query=query,
                context=context,
                generation_policy=generation_policy,
            ),
            usage=usage,
            timeout_seconds=_remaining(deadline, clock),
            call_kind="initial",
        )
        if _deadline_reached(deadline, clock):
            return _deadline_result(
                usage=usage,
                provider_call_count=1,
                transport_retry_count=first_call.transport_retry_count,
            )
        if first_call.draft is not None:
            issues = validate_grounded_answer(
                first_call.draft,
                context=context,
                materializer=self.materializer,
            )
            if not issues:
                return GroundedAnswerResult(
                    draft=_downgrade_complete_with_limitations(
                        first_call.draft
                    ),
                    repair_used=False,
                    usage=tuple(usage),
                    answer_calls=1,
                    repair_calls=0,
                    provider_call_count=1,
                    transport_retry_count=first_call.transport_retry_count,
                    initial_validation_errors=(),
                    initial_provider_error=None,
                    initial_provider_error_code=None,
                    validation_errors=(),
                    provider_error=None,
                    provider_error_code=None,
                )
        else:
            if not first_call.repairable:
                return GroundedAnswerResult(
                    draft=None,
                    repair_used=False,
                    usage=tuple(usage),
                    answer_calls=1,
                    repair_calls=0,
                    provider_call_count=1,
                    transport_retry_count=first_call.transport_retry_count,
                    initial_validation_errors=(),
                    initial_provider_error=first_call.error,
                    initial_provider_error_code=first_call.error_code,
                    validation_errors=(),
                    provider_error=first_call.error,
                    provider_error_code=first_call.error_code,
                )
            issues = (
                ValidationIssue(
                    "provider_output_invalid",
                    "$",
                    first_call.error or "provider output is invalid",
                ),
            )

        repair_provider = provider
        repair_call_kind = "validation_repair"
        if first_call.error_code in _ROLE_RECOVERY_ERROR_CODES:
            repair_call_kind = "generation_recovery"
            try:
                repair_provider = self.provider_factory(
                    "grounded_answer_recovery"
                )
            except Exception as exc:
                return GroundedAnswerResult(
                    draft=None,
                    repair_used=True,
                    usage=tuple(usage),
                    answer_calls=1,
                    repair_calls=1,
                    provider_call_count=1,
                    transport_retry_count=first_call.transport_retry_count,
                    initial_validation_errors=issues,
                    initial_provider_error=first_call.error,
                    initial_provider_error_code=first_call.error_code,
                    validation_errors=(),
                    provider_error=_error_text(exc),
                    provider_error_code=_error_code(
                        exc, fallback="provider_factory_error"
                    ),
                )
        repair_call = self._call(
            repair_provider,
            messages=_repair_messages(
                query=query,
                context=context,
                issues=issues,
                generation_policy=generation_policy,
            ),
            usage=usage,
            timeout_seconds=_remaining(deadline, clock),
            call_kind=repair_call_kind,
        )
        total_transport_retries = (
            first_call.transport_retry_count
            + repair_call.transport_retry_count
        )
        if _deadline_reached(deadline, clock):
            return _deadline_result(
                usage=usage,
                provider_call_count=2,
                transport_retry_count=total_transport_retries,
                repair_used=True,
                repair_calls=1,
                initial_validation_errors=issues,
                initial_provider_error=first_call.error,
                initial_provider_error_code=first_call.error_code,
            )
        if repair_call.draft is not None:
            repair_issues = validate_grounded_answer(
                repair_call.draft,
                context=context,
                materializer=self.materializer,
            )
            if not repair_issues:
                return GroundedAnswerResult(
                    draft=_downgrade_complete_with_limitations(
                        repair_call.draft
                    ),
                    repair_used=True,
                    usage=tuple(usage),
                    answer_calls=1,
                    repair_calls=1,
                    provider_call_count=2,
                    transport_retry_count=total_transport_retries,
                    initial_validation_errors=issues,
                    initial_provider_error=first_call.error,
                    initial_provider_error_code=first_call.error_code,
                    validation_errors=(),
                    provider_error=None,
                    provider_error_code=None,
                )
        else:
            repair_issues = (
                ValidationIssue(
                    "provider_output_invalid",
                    "$",
                    repair_call.error or "repair output is invalid",
                ),
            )
        return GroundedAnswerResult(
            draft=None,
            repair_used=True,
            usage=tuple(usage),
            answer_calls=1,
            repair_calls=1,
            provider_call_count=2,
            transport_retry_count=total_transport_retries,
            initial_validation_errors=issues,
            initial_provider_error=first_call.error,
            initial_provider_error_code=first_call.error_code,
            validation_errors=repair_issues,
            provider_error=(
                repair_call.error
                or first_call.error
                or "grounded answer validation failed"
            ),
            provider_error_code=(
                repair_call.error_code or "answer_validation_failed"
            ),
        )

    @staticmethod
    def _call(
        provider: object,
        *,
        messages: list[dict[str, str]],
        usage: list[dict[str, Any]],
        timeout_seconds: float | None = None,
        call_kind: str,
    ) -> _ProviderCallResult:
        response: object | None = None
        try:
            kwargs: dict[str, Any] = {
                "role": "grounded_answer",
                "messages": messages,
                "response_schema": GroundedAnswerDraft,
                "max_tokens": 4096,
            }
            if timeout_seconds is not None:
                kwargs["timeout_seconds"] = timeout_seconds
            response = provider.generate_structured(**kwargs)  # type: ignore[attr-defined]
            value = getattr(response, "output", response)
            draft = (
                value
                if isinstance(value, GroundedAnswerDraft)
                else GroundedAnswerDraft.model_validate(value)
            )
            response_usage = getattr(response, "usage", None)
            metadata: dict[str, Any] = (
                dict(response_usage) if isinstance(response_usage, dict) else {}
            )
            latency = getattr(response, "latency_ms", None)
            if isinstance(latency, (int, float)):
                metadata["latency_ms"] = float(latency)
            finish_reason = getattr(response, "finish_reason", None)
            if finish_reason is not None:
                metadata["finish_reason"] = str(finish_reason)
            metadata["retry_count"] = int(
                getattr(response, "retry_count", 0)
            )
            metadata["call_kind"] = call_kind
            usage.append(metadata)
            return _ProviderCallResult(
                draft=draft,
                error=None,
                error_code=None,
                repairable=False,
                transport_retry_count=int(
                    getattr(response, "retry_count", 0)
                ),
            )
        except Exception as exc:
            completion_metadata = getattr(exc, "completion_metadata", None)
            retry_count = 0
            content_received = response is not None
            if isinstance(completion_metadata, dict):
                metadata_usage = completion_metadata.get("usage")
                metadata = (
                    dict(metadata_usage)
                    if isinstance(metadata_usage, dict)
                    else {}
                )
                for key in ("finish_reason", "latency_ms", "retry_count"):
                    value = completion_metadata.get(key)
                    if value is not None:
                        metadata[key] = value
                metadata["call_kind"] = call_kind
                usage.append(metadata)
                retry_count = int(
                    completion_metadata.get("retry_count", 0)
                )
                content_received = bool(
                    completion_metadata.get("content_received")
                )
            error_code = _error_code(exc)
            return _ProviderCallResult(
                draft=None,
                error=_error_text(exc),
                error_code=error_code,
                repairable=(
                    response is not None
                    or error_code in _ROLE_RECOVERY_ERROR_CODES
                    or (
                        error_code == "invalid_model_output"
                        and content_received
                    )
                ),
                transport_retry_count=retry_count,
            )


def _answer_messages(
    *,
    query: str,
    context: ContextBuildResult,
    generation_policy: GenerationPolicy = BOUNDED_SYNTHESIS_POLICY,
) -> list[dict[str, str]]:
    schema = json.dumps(
        GroundedAnswerDraft.model_json_schema(),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return [
        {
            "role": "system",
            "content": (
                "Return one JSON object that exactly matches the supplied JSON Schema. "
                "The only top-level keys are status, answer_blocks, and limitations. "
                "Each answer block has exactly text and citation_ids; citation_ids is "
                "a non-empty array of strings. status is exactly complete, partial, "
                "or insufficient. Never use not_found. Never emit citations, "
                "block_type, answer, or claims fields. "
                "Use only transcript_evidence in the supplied context. Never use "
                "model memory, titles, summaries, descriptions, notes, or navigation "
                "content as facts. Every answer block must cite at least one ID from "
                "citation_allowlist. Split independently supported facts into separate "
                "blocks. Use partial or insufficient when evidence does not cover the "
                "question. Do not emit answer or claims fields."
                f"\nGrounding boundary: {_GROUNDING_BOUNDARY_INSTRUCTIONS}"
                f"{_generation_policy_prompt(generation_policy)}"
                f"\nRequired JSON Schema: {schema}"
            ),
        },
        {
            "role": "user",
            "content": f"Question: {query}\nGrounded context: {context.model_context}",
        },
    ]


def _repair_messages(
    *,
    query: str,
    context: ContextBuildResult,
    issues: tuple[ValidationIssue, ...],
    generation_policy: GenerationPolicy = BOUNDED_SYNTHESIS_POLICY,
) -> list[dict[str, str]]:
    schema = json.dumps(
        GroundedAnswerDraft.model_json_schema(),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return [
        {
            "role": "system",
            "content": (
                "Repair the structured grounded answer and return one JSON object "
                "that exactly matches the supplied JSON Schema. The only top-level "
                "keys are status, answer_blocks, and limitations. Each block has "
                "exactly text and citation_ids. status must be complete, partial, or "
                "insufficient. Never use not_found, citations, block_type, answer, "
                "or claims. Use exactly the same evidence "
                "context and citation allowlist. Do not retrieve, invent evidence, "
                "introduce citation IDs, or mechanically substitute an arbitrary ID. "
                "Every returned block must be fully grounded and cited."
                f"\nGrounding boundary: {_GROUNDING_BOUNDARY_INSTRUCTIONS}"
                f"{_generation_policy_prompt(generation_policy)}"
                f"\nRequired JSON Schema: {schema}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question: {query}\nGrounded context: {context.model_context}\n"
                "Deterministic validation errors: "
                + json.dumps(
                    [value.as_dict() for value in issues],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            ),
        },
    ]


def _generation_policy_prompt(policy: GenerationPolicy) -> str:
    if policy == BOUNDED_SYNTHESIS_POLICY:
        return ""
    if policy == EXACT_EXCERPT_COMPATIBILITY_POLICY:
        return f"\n{_EXACT_EXCERPT_COMPATIBILITY_INSTRUCTIONS}"
    raise ValueError(f"unsupported grounded-answer generation policy: {policy}")


def _downgrade_complete_with_limitations(
    draft: GroundedAnswerDraft,
) -> GroundedAnswerDraft:
    if draft.status == "complete" and any(
        value.strip() for value in draft.limitations
    ):
        return draft.model_copy(update={"status": "partial"})
    return draft


def _error_code(exc: Exception, *, fallback: str | None = None) -> str:
    value = getattr(exc, "code", None)
    return str(value) if value is not None else (fallback or type(exc).__name__)


def _error_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:500]


def _remaining(
    deadline: float | None, clock: Callable[[], float]
) -> float | None:
    if deadline is None:
        return None
    remaining = deadline - clock()
    if remaining <= 0:
        raise TimeoutError("grounded answer deadline exhausted")
    return remaining


def _deadline_reached(
    deadline: float | None, clock: Callable[[], float]
) -> bool:
    return deadline is not None and clock() >= deadline


def _deadline_result(
    *,
    usage: list[dict[str, Any]],
    provider_call_count: int,
    transport_retry_count: int,
    repair_used: bool = False,
    repair_calls: int = 0,
    initial_validation_errors: tuple[ValidationIssue, ...] = (),
    initial_provider_error: str | None = None,
    initial_provider_error_code: str | None = None,
) -> GroundedAnswerResult:
    message = "grounded answer exceeded total runtime deadline"
    return GroundedAnswerResult(
        draft=None,
        repair_used=repair_used,
        usage=tuple(usage),
        answer_calls=1,
        repair_calls=repair_calls,
        provider_call_count=provider_call_count,
        transport_retry_count=transport_retry_count,
        initial_validation_errors=initial_validation_errors,
        initial_provider_error=initial_provider_error,
        initial_provider_error_code=initial_provider_error_code,
        validation_errors=(),
        provider_error=message,
        provider_error_code="deadline_exhausted",
    )
