from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

from shiliu.config import AppPaths, load_api_key, load_config
from shiliu.domain import PipelineError

from .contracts import AnnotationPacketV2, Usage
from .providers import (
    DeepSeekAnnotationReviewer,
    OpenAIAnnotationReviewer,
    ProviderRequest,
    ReviewerPayload,
    ReviewerRawResult,
    build_deepseek_secondary_request,
)
from .review_compiler import CompilationContext, ReviewCompilationError, compile_reviewer_draft
from .review_validation import ValidationResult, validate_review
from .reviewer_draft import DraftValidationResult, validate_reviewer_draft
from .reviewer_registry import PRIMARY_REVIEWER, SECONDARY_REVIEWER
from .secret_config import (
    MissingSecretError,
    load_openai_reviewer_local_config,
    load_required_secret,
)
from .workspace import (
    PRIMARY_WORKSPACE_FILES,
    ProjectSensitivePaths,
    export_primary_workspace,
    write_sandbox_profile,
)


PRIMARY_MODEL = PRIMARY_REVIEWER.model
SECONDARY_MODEL = SECONDARY_REVIEWER.model
SECONDARY_REASONING_STRENGTH = SECONDARY_REVIEWER.reasoning_effort


class ProviderInvocationError(PipelineError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        retryable: bool,
        failure_class: str,
        http_status: int | None = None,
        safe_provider_error_code: str | None = None,
        request_id: str | None = None,
        safe_response_headers: tuple[tuple[str, str], ...] = (),
    ) -> None:
        super().__init__(message, code=code, retryable=retryable)
        self.failure_class = failure_class
        self.http_status = http_status
        self.safe_provider_error_code = safe_provider_error_code
        self.request_id = request_id
        self.safe_response_headers = safe_response_headers


@dataclass(frozen=True)
class RawInvocation:
    body: object
    model: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    finish_reason: str | None
    response_model: str | None
    response_model_echo_available: bool
    raw_call_count: int


@dataclass(frozen=True)
class ReviewerPathResult:
    status: str
    initial: RawInvocation | None
    repaired: RawInvocation | None
    validation: ValidationResult | None
    initial_errors: tuple[str, ...]
    raw_call_count: int
    provider_error: str | None = None


@dataclass(frozen=True)
class IndependentPreflightResult:
    primary: ReviewerPathResult
    secondary: ReviewerPathResult


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def parse_json_object(text: str) -> object:
    value = text.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, re.I | re.S)
    if fence:
        value = fence.group(1).strip()
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end < start:
        raise ValueError("response_has_no_json_object")
    return json.loads(value[start : end + 1])


def _sandbox_profile(workspace: Path, profile_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[4]
    write_sandbox_profile(
        workspace=workspace,
        profile_path=profile_path,
        sensitive=ProjectSensitivePaths.defaults(repository_root),
    )


def invoke_primary_codex_legacy(workspace: Path, *, model: str = "gpt-5.4") -> RawInvocation:
    """Retained only for historical reproducibility; it is not in the active Registry."""
    workspace = workspace.resolve()
    prompt = (
        "Read annotation_protocol_excerpt.md, primary_reviewer.draft.v1.md, "
        "reviewer_draft.v1.schema.json, and current_case.packet.json. Do not use tools or "
        "the network. Independently review the entire packet and return only one JSON object "
        "matching the supplied ReviewerDraft schema. Use only array indices for aspect/span/group "
        "references; never create A/S/G IDs."
    )
    profile = workspace.parent / f"{workspace.name}.sandbox.sb"
    _sandbox_profile(workspace, profile)
    events_path = workspace / "output" / "codex_events.jsonl"
    response_path = workspace / "output" / "raw_response.txt"
    started = time.perf_counter()
    command = [
        "/usr/bin/sandbox-exec",
        "-f",
        str(profile),
        "/Applications/ChatGPT.app/Contents/Resources/codex",
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--dangerously-bypass-approvals-and-sandbox",
        "--model",
        model,
        "--cd",
        str(workspace),
        "--output-schema",
        str(workspace / "reviewer_draft.v1.schema.json"),
        "--output-last-message",
        str(response_path),
        "--json",
        prompt,
    ]
    result = subprocess.run(
        command, cwd=workspace, capture_output=True, text=True, timeout=600, check=False
    )
    latency_ms = round((time.perf_counter() - started) * 1000)
    events_path.write_text(result.stdout, encoding="utf-8")
    (workspace / "output" / "stderr.redacted.txt").write_text(
        "" if result.returncode == 0 else "codex_invocation_failed_without_persisting_sensitive_stderr",
        encoding="utf-8",
    )
    if result.returncode != 0 or not response_path.exists():
        raise RuntimeError(f"primary_invocation_failed:{result.returncode}")
    usage: dict[str, int] = {}
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = event["usage"]
    return RawInvocation(
        body=parse_json_object(response_path.read_text(encoding="utf-8")),
        model=model,
        latency_ms=latency_ms,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        cached_tokens=usage.get("cached_input_tokens"),
        finish_reason=None,
        response_model=model,
        response_model_echo_available=False,
        raw_call_count=1,
    )


def _raw_invocation(result: ReviewerRawResult) -> RawInvocation:
    return RawInvocation(
        body=result.body,
        model=result.requested_model,
        latency_ms=result.latency_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cached_tokens=result.cached_tokens,
        finish_reason=result.finish_reason,
        response_model=result.response_model,
        response_model_echo_available=result.response_model is not None,
        raw_call_count=1,
    )


def invoke_primary(payload: ReviewerPayload) -> RawInvocation:
    local = load_openai_reviewer_local_config()
    try:
        result = OpenAIAnnotationReviewer(
            api_key=local.api_key,
            base_url=local.base_url,
        ).review(payload)
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        safe_code = _safe_provider_error_code(exc)
        failure_class = _classify_openai_failure(status, safe_code, exc)
        retryable = failure_class in {
            "unknown_http_400",
            "gateway_rejection",
            "capacity_or_rate",
            "connection_or_sdk_failure",
        } or status in {408, 409} or (isinstance(status, int) and status >= 500)
        request_id, safe_headers = _safe_openai_response_metadata(exc)
        raise ProviderInvocationError(
            "OpenAI annotation provider request failed",
            code="provider_request_failed",
            retryable=retryable or status is None,
            failure_class=failure_class,
            http_status=status if isinstance(status, int) else None,
            safe_provider_error_code=safe_code,
            request_id=request_id,
            safe_response_headers=safe_headers,
        ) from None
    return _raw_invocation(result)


def _safe_provider_error_code(exc: Exception) -> str | None:
    code = getattr(exc, "code", None)
    if not isinstance(code, str):
        body = getattr(exc, "body", None)
        error = body.get("error") if isinstance(body, dict) else None
        code = error.get("code") if isinstance(error, dict) else None
    if not isinstance(code, str):
        return None
    normalized = re.sub(r"[^a-zA-Z0-9_.-]", "_", code)[:100]
    return normalized or None


def _classify_openai_failure(status: object, code: str | None, exc: Exception) -> str:
    value = (code or "").casefold()
    if any(term in value for term in ("rate_limit", "capacity", "overloaded", "quota")):
        return "capacity_or_rate"
    if any(term in value for term in ("model_not_found", "model_unavailable", "unsupported_model")):
        return "model_unavailable"
    if any(term in value for term in ("invalid_parameter", "invalid_request", "bad_parameter")):
        return "invalid_parameter"
    if status == 429:
        return "capacity_or_rate"
    if status == 400:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", {})
        if any(str(key).casefold() in {"cf-ray", "x-gateway-error"} for key in headers):
            return "gateway_rejection"
        return "unknown_http_400"
    if status is None:
        return "connection_or_sdk_failure"
    return f"http_{status}"


def _safe_openai_response_metadata(
    exc: Exception,
) -> tuple[str | None, tuple[tuple[str, str], ...]]:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {})
    allowed = {
        "x-request-id",
        "request-id",
        "cf-ray",
        "retry-after",
        "x-ratelimit-limit-requests",
        "x-ratelimit-remaining-requests",
        "x-ratelimit-reset-requests",
    }
    safe = tuple(
        sorted(
            (str(key).casefold(), str(value)[:200])
            for key, value in headers.items()
            if str(key).casefold() in allowed
        )
    )
    request_id = getattr(exc, "request_id", None)
    if not isinstance(request_id, str):
        request_id = dict(safe).get("x-request-id") or dict(safe).get("request-id")
    return request_id, safe


def invoke_primary_repair(
    payload: ReviewerPayload,
    *,
    packet: AnnotationPacketV2,
    raw_output: object,
    errors: tuple[str, ...],
) -> RawInvocation:
    prompt = "\n\n".join(
        [
            "Repair only the supplied Primary reviewer output. Return only a JSON ReviewerDraft matching the supplied schema. Use indices only and never create A/S/G IDs. Do not use outside knowledge, the network, other reviews, or any other files.",
            "VALIDATION ERRORS:\n" + canonical_json(list(errors)),
            "ORIGINAL PACKET:\n" + packet.model_dump_json(),
            "ORIGINAL PRIMARY OUTPUT:\n" + canonical_json(raw_output),
        ]
    )
    repair_payload = ReviewerPayload(
        packet_bytes=payload.packet_bytes,
        prompt=prompt,
        draft_schema=payload.draft_schema,
    )
    return invoke_primary(repair_payload)


def invoke_secondary(packet: AnnotationPacketV2, prompt: str) -> RawInvocation:
    config = load_config(AppPaths.defaults())
    try:
        secret = load_required_secret(SECONDARY_REVIEWER.key_env_var)
        api_key = secret.value
    except MissingSecretError:
        # Current installation stores the existing DeepSeek key in macOS Keychain.
        api_key = load_api_key(config.api_key_ref)
    payload = ReviewerPayload.from_packet(packet, prompt)

    def transport(body: dict[str, object], headers: dict[str, str]) -> dict[str, object]:
        try:
            with httpx.Client(timeout=600) as client:
                response = client.post(
                    f"{config.llm_base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=body,
                )
        except httpx.HTTPError:
            raise ProviderInvocationError(
                "annotation provider network failure",
                code="provider_network",
                retryable=True,
                failure_class="connection_failure",
            ) from None
        if response.status_code >= 400:
            retryable = response.status_code in {408, 409, 429} or response.status_code >= 500
            raise ProviderInvocationError(
                f"annotation provider HTTP {response.status_code}",
                code="provider_request_failed",
                retryable=retryable,
                failure_class=(
                    f"http_{response.status_code}_transient"
                    if retryable
                    else f"http_{response.status_code}"
                ),
                http_status=response.status_code,
            ) from None
        value = response.json()
        if not isinstance(value, dict):
            raise PipelineError(
                "annotation provider returned a non-object response",
                code="provider_response_invalid",
                retryable=False,
            )
        return value

    try:
        result = DeepSeekAnnotationReviewer(
            api_key=api_key,
            base_url=config.llm_base_url,
            transport=transport,
        ).review(payload)
    except PipelineError:
        raise
    except Exception:
        raise PipelineError(
            "DeepSeek annotation provider response failed validation",
            code="provider_response_invalid",
            retryable=False,
        ) from None
    return _raw_invocation(result)


def invoke_secondary_repair(
    packet: AnnotationPacketV2,
    *,
    raw_output: object,
    errors: tuple[str, ...],
    draft_schema: object,
) -> RawInvocation:
    repair_prompt = "\n\n".join(
        [
            "Repair only the supplied Secondary reviewer draft. Return one ReviewerDraft JSON object. Preserve semantic intent; use array indices only and never create A/S/G IDs. Do not use another review, Agreement, Gold, adjudication, system predictions, outside knowledge, or tools.",
            "DRAFT SCHEMA:\n" + canonical_json(draft_schema),
            "VALIDATION ERRORS:\n" + canonical_json(list(errors)),
            "ORIGINAL SECONDARY OUTPUT:\n" + canonical_json(raw_output),
        ]
    )
    return invoke_secondary(packet, repair_prompt)


def bind_and_validate(
    *, packet: AnnotationPacketV2, invocation: RawInvocation, provider: str, role: str,
    prompt_version: str, repair_count: int = 0
) -> ValidationResult:
    """Compile a model-facing Draft, bind local identity, then validate Canonical Review v2."""
    completed = utcnow()
    started = datetime.fromtimestamp(
        completed.timestamp() - invocation.latency_ms / 1000, tz=timezone.utc
    )
    try:
        compiled = compile_reviewer_draft(
            raw_draft=invocation.body,
            packet=packet,
            context=CompilationContext(
                reviewer_provider=provider,
                reviewer_model=invocation.model,
                reviewer_role=role,
                prompt_version=prompt_version,
                started_at=started,
                completed_at=completed,
                latency_ms=invocation.latency_ms,
                usage=Usage(
                    input_tokens=invocation.input_tokens,
                    output_tokens=invocation.output_tokens,
                    cached_tokens=invocation.cached_tokens,
                ),
                repair_count=repair_count,
            ),
        )
    except ReviewCompilationError as exc:
        return ValidationResult("invalid", None, exc.errors, repair_count)
    except Exception as exc:
        return ValidationResult("invalid", None, (f"compile:{type(exc).__name__}",), repair_count)
    validated = validate_review(compiled.annotation.model_dump(mode="json"), packet)
    return ValidationResult(
        validated.status,
        validated.review,
        validated.errors,
        repair_count,
        compiled.query_grounding.status,
        compiled.query_grounding.errors,
    )


def validate_draft_invocation(
    *, packet: AnnotationPacketV2, invocation: RawInvocation, repair_count: int = 0
) -> DraftValidationResult:
    result = validate_reviewer_draft(invocation.body, packet)
    return DraftValidationResult(result.status, result.draft, result.errors, repair_count)


def execute_reviewer_path(
    *,
    packet: AnnotationPacketV2,
    invoke: Callable[[], RawInvocation],
    repair: Callable[[RawInvocation, tuple[str, ...]], RawInvocation],
    provider: str,
    role: str,
    prompt_version: str,
) -> ReviewerPathResult:
    try:
        initial = invoke()
    except Exception:
        return ReviewerPathResult(
            status="provider_error",
            initial=None,
            repaired=None,
            validation=None,
            initial_errors=(),
            raw_call_count=0,
            provider_error=f"{provider}_initial_request_failed",
        )
    initial_validation = bind_and_validate(
        packet=packet,
        invocation=initial,
        provider=provider,
        role=role,
        prompt_version=prompt_version,
        repair_count=0,
    )
    selected = initial
    repair_count = 0
    repaired: RawInvocation | None = None
    validation = initial_validation
    if initial_validation.status != "valid":
        try:
            repaired = repair(initial, initial_validation.errors)
        except Exception:
            return ReviewerPathResult(
                status="repair_provider_error",
                initial=initial,
                repaired=None,
                validation=initial_validation,
                initial_errors=initial_validation.errors,
                raw_call_count=1,
                provider_error=f"{provider}_repair_request_failed",
            )
        selected = repaired
        repair_count = 1
        validation = bind_and_validate(
            packet=packet,
            invocation=selected,
            provider=provider,
            role=role,
            prompt_version=prompt_version,
            repair_count=repair_count,
        )
    status = (
        "valid"
        if validation.status == "valid" and repair_count == 0
        else "valid_after_repair"
        if validation.status == "valid"
        else "invalid_after_repair"
    )
    return ReviewerPathResult(
        status=status,
        initial=initial,
        repaired=repaired,
        validation=validation,
        initial_errors=initial_validation.errors,
        raw_call_count=1 + repair_count,
    )


def run_independent_preflight(
    *,
    packet: AnnotationPacketV2,
    primary_invoke: Callable[[], RawInvocation],
    primary_repair: Callable[[RawInvocation, tuple[str, ...]], RawInvocation],
    secondary_invoke: Callable[[], RawInvocation],
    secondary_repair: Callable[[RawInvocation, tuple[str, ...]], RawInvocation],
) -> IndependentPreflightResult:
    """Run both independent paths; a format failure on one does not suppress the other."""
    primary = execute_reviewer_path(
        packet=packet,
        invoke=primary_invoke,
        repair=primary_repair,
        provider=PRIMARY_REVIEWER.provider_id,
        role="primary",
        prompt_version=PRIMARY_REVIEWER.prompt_version,
    )
    secondary = execute_reviewer_path(
        packet=packet,
        invoke=secondary_invoke,
        repair=secondary_repair,
        provider=SECONDARY_REVIEWER.provider_id,
        role="secondary",
        prompt_version=SECONDARY_REVIEWER.prompt_version,
    )
    return IndependentPreflightResult(primary=primary, secondary=secondary)


def request_audit(request: ProviderRequest) -> dict[str, object]:
    body = request.body
    return {
        "provider_configured": True,
        "configured_model": body.get("model"),
        "configured_reasoning_strength": body.get("reasoning_effort"),
        "thinking": body.get("thinking"),
        "provider_usage": request.provider_usage,
        "request_model_confirmed": body.get("model") == SECONDARY_MODEL,
        "request_reasoning_strength_confirmed": body.get("reasoning_effort") == "max",
        "authorization_persisted": False,
        "case_packet_sha256": request.manifest.packet_sha256,
    }
