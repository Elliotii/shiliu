from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable

from shiliu.ask.context import ContextBuildResult
from shiliu.ask.contracts import GroundedAnswerDraft
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.ask.validation import ValidationIssue, validate_grounded_answer


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
            messages=_answer_messages(query=query, context=context),
            usage=usage,
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

        repair_call = self._call(
            provider,
            messages=_repair_messages(
                query=query,
                context=context,
                issues=issues,
            ),
            usage=usage,
        )
        total_transport_retries = (
            first_call.transport_retry_count
            + repair_call.transport_retry_count
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
    ) -> _ProviderCallResult:
        response: object | None = None
        try:
            response = provider.generate_structured(  # type: ignore[attr-defined]
                role="grounded_answer",
                messages=messages,
                response_schema=GroundedAnswerDraft,
                max_tokens=4096,
            )
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
                    or (
                        error_code == "invalid_model_output"
                        and content_received
                    )
                ),
                transport_retry_count=retry_count,
            )


def _answer_messages(
    *, query: str, context: ContextBuildResult
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
