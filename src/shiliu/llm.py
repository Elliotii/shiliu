from __future__ import annotations

import json
import re
from dataclasses import dataclass
import hashlib
import time
from typing import Any, Generic, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from shiliu.domain import PipelineError


SchemaT = TypeVar("SchemaT", bound=BaseModel)


@dataclass(frozen=True)
class CompletionResponse:
    """Raw provider response metadata used by recoverable long workflows."""

    content: str
    finish_reason: str | None
    usage: dict[str, Any] | None
    response_id: str | None
    reasoning_content: str | None = None
    latency_ms: float = 0
    retry_count: int = 0
    response_model: str | None = None


@dataclass(frozen=True)
class StructuredCompletionResponse(Generic[SchemaT]):
    output: SchemaT
    finish_reason: str | None
    usage: dict[str, Any] | None
    response_id: str | None
    latency_ms: float
    retry_count: int
    output_diagnostics: dict[str, Any] | None = None
    response_model: str | None = None


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 120,
        thinking_enabled: bool | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.thinking_enabled = thinking_enabled
        normalized_effort = (reasoning_effort or "").lower()
        if normalized_effort == "xhigh":
            normalized_effort = "max"
        if normalized_effort and normalized_effort not in {"low", "high", "max"}:
            raise PipelineError(
                "推理强度只支持 low、high 或 max",
                code="bad_provider_config",
                retryable=False,
            )
        self.reasoning_effort = normalized_effort or None
        if not self.base_url.startswith(("http://", "https://")):
            raise PipelineError("Base URL 必须是 http(s) 地址", code="bad_provider_config", retryable=False)
        if not self.model.strip():
            raise PipelineError("模型名称不能为空", code="bad_provider_config", retryable=False)

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def list_models(self) -> list[str]:
        try:
            with httpx.Client(timeout=20) as client:
                response = client.get(f"{self.base_url}/models", headers=self.headers)
                self._raise_for_status(response)
        except httpx.HTTPError as exc:
            raise PipelineError("刷新模型列表失败", code="provider_network", retryable=True) from exc
        payload = response.json()
        values = payload.get("data", []) if isinstance(payload, dict) else []
        return sorted(str(item["id"]) for item in values if isinstance(item, dict) and item.get("id"))

    def test_connection(self) -> str:
        payload = self._generate(
            [
                {"role": "system", "content": "Return exactly: OK"},
                {"role": "user", "content": "Connection test"},
            ],
            # Reasoning providers count hidden/reasoning tokens inside this
            # budget. Eight tokens can therefore produce reasoning_content
            # but no final content even though the connection is healthy.
            max_tokens=1024,
        )
        return payload.strip()

    def complete_json(
        self,
        prompt: str,
        schema: type[SchemaT],
        *,
        max_tokens: int | None = None,
    ) -> SchemaT:
        content = self._generate(
            [
                {"role": "system", "content": "Follow the user's transformation rules and return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
        )
        return parse_json_content(content, schema)

    def complete_raw(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
    ) -> CompletionResponse:
        """Return raw content and usage before application-level parsing."""

        return self._generate_response(
            [
                {
                    "role": "system",
                    "content": "Follow the user's transformation rules and return valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            allow_incomplete=True,
        )

    def generate_structured(
        self,
        *,
        role: str,
        messages: list[dict[str, str]],
        response_schema: type[SchemaT],
        max_tokens: int | None = None,
        timeout_seconds: float | None = None,
    ) -> StructuredCompletionResponse[SchemaT]:
        if role not in {"query_analysis", "agent_action", "query_reduce", "grounded_answer"}:
            raise PipelineError(
                f"不支持的结构化运行时角色：{role}",
                code="bad_provider_config",
                retryable=False,
            )
        try:
            response = self._generate_response(
                messages,
                max_tokens=max_tokens or (1200 if role == "query_analysis" else 4096),
                response_format={"type": "json_object"},
                transport_retries=1,
                timeout_seconds=timeout_seconds,
            )
        except PipelineError as exc:
            metadata = dict(getattr(exc, "completion_metadata", {}))
            metadata.update(request_role=role, model_requested=self.model)
            exc.completion_metadata = metadata
            raise
        normalization: dict[str, Any] | None = None
        try:
            output, normalization = _parse_structured_provider_content(
                response.content,
                response_schema,
                role=role,
            )
        except PipelineError as exc:
            exc.completion_metadata = {
                "finish_reason": response.finish_reason,
                "usage": response.usage,
                "response_id": response.response_id,
                "latency_ms": response.latency_ms,
                "retry_count": response.retry_count,
                "content_received": True,
                **_raw_content_diagnostics(response.content),
                "validation_error": str(exc),
            }
            if normalization := getattr(exc, "output_normalization", None):
                exc.completion_metadata.update(normalization)
            raise
        output_diagnostics = None
        if normalization is not None:
            output_diagnostics = {
                **_raw_content_diagnostics(response.content),
                **normalization,
            }
        return StructuredCompletionResponse(
            output=output,
            finish_reason=response.finish_reason,
            usage=response.usage,
            response_id=response.response_id,
            latency_ms=response.latency_ms,
            retry_count=response.retry_count,
            output_diagnostics=output_diagnostics,
            response_model=response.response_model,
        )

    def _generate(self, messages: list[dict[str, str]], *, max_tokens: int | None = None) -> str:
        return self._generate_response(messages, max_tokens=max_tokens).content

    def _generate_response(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        allow_incomplete: bool = False,
        response_format: dict[str, str] | None = None,
        transport_retries: int = 0,
        timeout_seconds: float | None = None,
    ) -> CompletionResponse:
        if transport_retries < 0:
            raise ValueError("transport_retries must not be negative")
        started = time.monotonic()
        invocation_deadline = (
            started + timeout_seconds
            if timeout_seconds is not None
            else None
        )
        body: dict[str, Any] = {"model": self.model, "messages": messages}
        if self.thinking_enabled is not None:
            body["thinking"] = {"type": "enabled" if self.thinking_enabled else "disabled"}
        if self.thinking_enabled is not False and self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        if self.thinking_enabled is False:
            body["temperature"] = 0
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if response_format is not None:
            body["response_format"] = response_format
        retry_count = 0
        for attempt in range(transport_retries + 1):
            try:
                invocation_remaining = (
                    timeout_seconds - (time.monotonic() - started)
                    if timeout_seconds is not None
                    else None
                )
                effective_timeout = (
                    min(self.timeout_seconds, invocation_remaining)
                    if invocation_remaining is not None
                    else self.timeout_seconds
                )
                if effective_timeout <= 0:
                    raise PipelineError(
                        "模型调用已超过运行截止时间",
                        code="deadline_exhausted",
                        retryable=False,
                    )
                with httpx.Client(timeout=effective_timeout) as client:
                    response = client.post(
                        f"{self.base_url}/chat/completions",
                        headers=self.headers,
                        json=body,
                    )
                    try:
                        self._raise_for_status(response)
                    except PipelineError as exc:
                        exc.completion_metadata = _http_failure_metadata(response, self.api_key)
                        raise
                break
            except PipelineError as exc:
                if exc.retryable and _deadline_reached(invocation_deadline):
                    error = _deadline_error()
                    error.completion_metadata = dict(getattr(exc, "completion_metadata", {}))
                    _attach_failure_metadata(
                        error, started=started, retry_count=retry_count
                    )
                    raise error from exc
                if exc.retryable and attempt < transport_retries:
                    retry_count += 1
                    continue
                _attach_failure_metadata(
                    exc, started=started, retry_count=retry_count
                )
                raise
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if _deadline_reached(invocation_deadline):
                    error = _deadline_error()
                    _attach_failure_metadata(
                        error, started=started, retry_count=retry_count
                    )
                    raise error from exc
                if attempt < transport_retries:
                    retry_count += 1
                    continue
                error = PipelineError(
                    "模型服务网络错误或超时",
                    code="provider_network",
                    retryable=True,
                )
                _attach_failure_metadata(
                    error, started=started, retry_count=retry_count
                )
                raise error from exc
            except httpx.HTTPError as exc:
                if _deadline_reached(invocation_deadline):
                    error = _deadline_error()
                    _attach_failure_metadata(
                        error, started=started, retry_count=retry_count
                    )
                    raise error from exc
                if attempt < transport_retries:
                    retry_count += 1
                    continue
                error = PipelineError(
                    "模型服务请求失败",
                    code="provider_network",
                    retryable=True,
                )
                _attach_failure_metadata(
                    error, started=started, retry_count=retry_count
                )
                raise error from exc
        try:
            payload = response.json()
            choice = payload["choices"][0]
            message = choice["message"]
            content = message.get("content")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            error = PipelineError(
                "模型服务返回格式无效",
                code="provider_schema",
                retryable=True,
            )
            _attach_failure_metadata(
                error, started=started, retry_count=retry_count
            )
            raise error from exc
        finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
        usage = payload.get("usage") if isinstance(payload, dict) else None
        response_model = str(payload.get("model")) if isinstance(payload, dict) and payload.get("model") else None
        response_id = (
            str(payload["id"])
            if isinstance(payload, dict) and payload.get("id") is not None
            else None
        )
        if finish_reason == "length" and not allow_incomplete:
            error = PipelineError(
                "模型输出达到保险上限，请人工确认后重试",
                code="output_budget_exhausted",
                retryable=False,
            )
            _attach_failure_metadata(
                error,
                started=started,
                retry_count=retry_count,
                finish_reason=finish_reason,
                usage=usage,
                response_id=response_id,
            )
            # Diagnostic only: never parse or return truncated structured output.
            # The exception metadata follows the existing private run Trace path,
            # rather than emitting model content to ordinary application logs.
            error.completion_metadata.update(
                error_code=error.code,
                max_tokens=max_tokens,
                model_requested=self.model,
                model_response=response_model,
                content_received=isinstance(content, str) and bool(content),
            )
            if isinstance(content, str):
                error.completion_metadata.update(_bounded_length_diagnostics(content, self.api_key))
            raise error
        reasoning = message.get("reasoning_content") if isinstance(message, dict) else None
        if (not isinstance(content, str) or not content.strip()) and not allow_incomplete:
            error = PipelineError(
                "模型返回为空", code="empty_model_output", retryable=True
            )
            _attach_failure_metadata(
                error,
                started=started,
                retry_count=retry_count,
                finish_reason=finish_reason,
                usage=usage,
                response_id=response_id,
            )
            raise error
        return CompletionResponse(
            content=content if isinstance(content, str) else "",
            finish_reason=str(finish_reason) if finish_reason is not None else None,
            usage=usage if isinstance(usage, dict) else None,
            response_id=response_id,
            reasoning_content=reasoning if isinstance(reasoning, str) else None,
            latency_ms=(time.monotonic() - started) * 1000,
            retry_count=retry_count,
            response_model=response_model,
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        status = response.status_code
        body = response.text[:500].lower()
        if status in {401}:
            raise PipelineError("API Key 无效", code="provider_authentication", retryable=False)
        if status == 402:
            raise PipelineError("模型账户余额不足", code="provider_insufficient_balance", retryable=False)
        if status == 403:
            raise PipelineError("模型服务拒绝访问", code="provider_forbidden", retryable=False)
        if status == 404:
            raise PipelineError("模型或接口不存在", code="provider_model_not_found", retryable=False)
        if status in {408, 429} or status >= 500:
            raise PipelineError(f"模型服务暂时不可用（HTTP {status}）", code="provider_retryable", retryable=True)
        if status == 400 and any(token in body for token in ("context", "token", "too long", "maximum")):
            raise PipelineError("字幕超过模型上下文限制，未做静默截断", code="context_too_large", retryable=False)
        raise PipelineError(f"模型服务配置或请求无效（HTTP {status}）", code="bad_provider_config", retryable=False)


def _http_failure_metadata(response: httpx.Response, api_key: str) -> dict[str, Any]:
    """Keep bounded server diagnostics, never request headers or credentials."""
    def redact(value: object, limit: int) -> str:
        text = str(value)
        if api_key:
            text = text.replace(api_key, "[REDACTED]")
        return re.sub(r"(?i)bearer\s+[^\s\"']+", "Bearer [REDACTED]", text)[:limit]

    body = response.text
    metadata: dict[str, Any] = {
        "http_status": response.status_code,
        "provider_response_body": redact(body, 8192),
        "provider_response_body_truncated": len(body) > 8192,
    }
    try:
        payload = response.json()
    except ValueError:
        return metadata
    error = payload.get("error", payload) if isinstance(payload, dict) else {}
    if isinstance(error, dict):
        for key in ("message", "code"):
            if error.get(key) is not None:
                metadata[f"provider_error_{key}"] = redact(error[key], 2048)
    return metadata


def _deadline_reached(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() >= deadline


def _deadline_error() -> PipelineError:
    return PipelineError(
        "模型调用已超过运行截止时间",
        code="deadline_exhausted",
        retryable=False,
    )


def _attach_failure_metadata(
    error: PipelineError,
    *,
    started: float,
    retry_count: int,
    finish_reason: object = None,
    usage: object = None,
    response_id: object = None,
) -> None:
    error.completion_metadata = {
        **getattr(error, "completion_metadata", {}),
        "finish_reason": (
            str(finish_reason) if finish_reason is not None else None
        ),
        "usage": usage if isinstance(usage, dict) else None,
        "response_id": (
            str(response_id) if response_id is not None else None
        ),
        "latency_ms": (time.monotonic() - started) * 1000,
        "retry_count": retry_count,
        "content_received": False,
    }


def _extract_json(content: str) -> str:
    text = content.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("response has no JSON object")
    return text[start : end + 1]


def parse_json_content(content: str, schema: type[SchemaT]) -> SchemaT:
    """Validate raw content after callers have durably persisted it."""

    try:
        parsed = json.loads(_extract_json(content))
        return schema.model_validate(parsed)
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise PipelineError(
            f"模型返回未通过结构校验：{exc}",
            code="invalid_model_output",
            retryable=True,
        ) from exc


def _parse_structured_provider_content(
    content: str,
    schema: type[SchemaT],
    *,
    role: str,
) -> tuple[SchemaT, dict[str, Any] | None]:
    """Parse one Provider response with the sole agent-summary normalization."""

    normalization: dict[str, Any] | None = None
    try:
        parsed = json.loads(_extract_json(content))
        if role == "agent_action":
            normalization = _bound_agent_stop_summary(parsed)
        return schema.model_validate(parsed), normalization
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        error = PipelineError(
            f"模型返回未通过结构校验：{exc}",
            code="invalid_model_output",
            retryable=True,
        )
        error.output_normalization = normalization
        raise error from exc


def _bound_agent_stop_summary(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    action = value.get("action")
    if not isinstance(action, dict) or action.get("kind") not in {"finish", "stop"}:
        return None
    summary = action.get("summary")
    if not isinstance(summary, str) or len(summary) <= 500:
        return None
    action["summary"] = summary[:499] + "…"
    return {
        "normalization_applied": True,
        "normalized_field": f"action.{action['kind']}.summary",
        "original_summary_length": len(summary),
        "normalized_summary_length": len(action["summary"]),
        "normalization_rule": "python_str_first_499_plus_ellipsis",
    }


def _raw_content_diagnostics(content: str) -> dict[str, Any]:
    return {
        "raw_content": content,
        "raw_content_length": len(content),
        "raw_content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }


def _bounded_length_diagnostics(content: str, api_key: str) -> dict[str, Any]:
    """Bound private failure diagnostics to 8192 chars, preserving both JSON ends."""
    def redact(text: str) -> str:
        if api_key:
            text = text.replace(api_key, "[REDACTED]")
        return re.sub(r"(?i)bearer\s+[^\s\"']+", "Bearer [REDACTED]", text)

    # Redact before slicing so credentials crossing an excerpt boundary cannot leak.
    safe = redact(content)
    # Hash/length describe original content; excerpt lengths describe redacted text.
    return {
        "raw_content_length": len(content),
        "raw_content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "raw_content_prefix": safe[:4096],
        "raw_content_suffix": safe[max(4096, len(safe) - 4096):],
        "raw_content_redacted_length": len(safe),
        "raw_content_omitted_chars": max(0, len(safe) - 8192),
        "raw_content_truncated": len(safe) > 8192,
        "raw_content_diagnostic_only": True,
    }
