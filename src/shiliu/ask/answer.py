from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any, Callable, Literal

from shiliu.ask.context import ContextBuildResult
from shiliu.ask.contracts import GroundedAnswerDraft
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.ask.validation import ValidationIssue, validate_grounded_answer


_ANSWER_PRODUCT_INSTRUCTIONS = """Answer the user's actual question directly and coherently. Let the question determine the structure. Each answer block represents one coherent user-facing conclusion or theme; merge evidence spans that support the same conclusion and use separate blocks only for genuinely distinct conclusions. For multi-source or cross-video questions, synthesize themes, common ground, and differences rather than listing one source per block. Mention video titles naturally when source identity helps. Omit weak, tangential, or merely similar evidence.

Treat the user's terminology and assumptions as a request, not as evidence. Treat retrieved videos as attributed sources, not automatically as objective truth. Synthesize the sources actively, while preserving provenance when a material definition, classification, causal claim, comparison, or disputed judgment comes from the user's wording or a particular source instead of silently turning it into an objective system claim. If a source does not use the user's label, describe what it actually says without presenting that label as the source's definition. When sources differ, explain and synthesize their common ground and differences instead of defaulting to refusal or uncertainty. A single source can support an answer when its material claims retain necessary attribution.

Use transcript_evidence quotes as the only factual material. Faithful paraphrase, spoken-language cleanup, and theme-level abstraction are allowed. Do not infer collection-wide or universal scope unless the quotes support it; a counterexample may refute a universal claim without proving its universal opposite. Every citation_id must directly support the complete material conclusion in its block. video_title and video_id identify a source but add no facts. Express citation affiliation only with citation_ids from the citation_allowlist; never write display citation markers in answer text.

Return partial only when there is a substantive answer but an important requested aspect lacks evidence. Return insufficient with no answer blocks only when the evidence cannot support a substantive answer. A bounded sample, source disagreement, or single-source answer alone does not require partial. Limitations must name a real answer gap or execution boundary and must not contradict the answer. Return one JSON object matching the supplied schema.
Required JSON Schema: """


BOUNDED_SYNTHESIS_POLICY = "bounded_grounded_synthesis_v1"
GenerationPolicy = Literal["bounded_grounded_synthesis_v1"]


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
            citation_allowlist=context.citation_allowlist,
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
            citation_allowlist=context.citation_allowlist,
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

    def repair(
        self,
        *,
        query: str,
        context: ContextBuildResult,
        issues: tuple[ValidationIssue, ...],
        deadline: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> GroundedAnswerResult:
        """Use the existing single Answer repair for citation-ID correction."""

        usage: list[dict[str, Any]] = []
        try:
            provider = self.provider_factory("grounded_answer")
        except Exception as exc:
            return GroundedAnswerResult(
                draft=None,
                repair_used=True,
                usage=(),
                answer_calls=0,
                repair_calls=1,
                provider_call_count=0,
                transport_retry_count=0,
                initial_validation_errors=issues,
                initial_provider_error=None,
                initial_provider_error_code=None,
                validation_errors=(),
                provider_error=_error_text(exc),
                provider_error_code=_error_code(
                    exc, fallback="provider_factory_error"
                ),
            )
        call = self._call(
            provider,
            messages=_repair_messages(
                query=query,
                context=context,
                issues=issues,
            ),
            usage=usage,
            citation_allowlist=context.citation_allowlist,
            timeout_seconds=_remaining(deadline, clock),
            call_kind="validation_repair",
        )
        if call.draft is None:
            validation_errors = (
                ValidationIssue(
                    "provider_output_invalid",
                    "$",
                    call.error or "repair output is invalid",
                ),
            )
            draft = None
        else:
            validation_errors = validate_grounded_answer(
                call.draft,
                context=context,
                materializer=self.materializer,
            )
            draft = (
                _downgrade_complete_with_limitations(call.draft)
                if not validation_errors
                else None
            )
        return GroundedAnswerResult(
            draft=draft,
            repair_used=True,
            usage=tuple(usage),
            answer_calls=0,
            repair_calls=1,
            provider_call_count=1,
            transport_retry_count=call.transport_retry_count,
            initial_validation_errors=issues,
            initial_provider_error=None,
            initial_provider_error_code=None,
            validation_errors=validation_errors,
            provider_error=call.error,
            provider_error_code=(
                call.error_code if draft is None else None
            ),
        )

    @staticmethod
    def _call(
        provider: object,
        *,
        messages: list[dict[str, str]],
        usage: list[dict[str, Any]],
        citation_allowlist: tuple[str, ...],
        timeout_seconds: float | None = None,
        call_kind: str,
    ) -> _ProviderCallResult:
        response: object | None = None
        try:
            kwargs: dict[str, Any] = {
                "role": "grounded_answer",
                "messages": messages,
                "response_schema": GroundedAnswerDraft,
                "max_tokens": 8192,
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
            draft = _deduplicate_fully_equivalent_blocks(
                draft,
                citation_allowlist=citation_allowlist,
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
            "content": f"{_ANSWER_PRODUCT_INSTRUCTIONS}{schema}",
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
                "Repair only the structured output while preserving the same evidence "
                "and answer contract. Do not retrieve, invent evidence, or substitute "
                "citations.\n\n"
                f"{_ANSWER_PRODUCT_INSTRUCTIONS}{schema}"
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


def _deduplicate_fully_equivalent_blocks(
    draft: GroundedAnswerDraft,
    *,
    citation_allowlist: tuple[str, ...],
) -> GroundedAnswerDraft:
    allowed = set(citation_allowlist)
    seen: set[tuple[str, tuple[str, ...]]] = set()
    blocks = []
    for block in draft.answer_blocks:
        references = tuple(block.citation_ids)
        if not references or not set(references).issubset(allowed):
            blocks.append(block)
            continue
        key = (block.text, references)
        if key in seen:
            continue
        seen.add(key)
        blocks.append(block)
    if len(blocks) == len(draft.answer_blocks):
        return draft
    return draft.model_copy(update={"answer_blocks": blocks})


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
