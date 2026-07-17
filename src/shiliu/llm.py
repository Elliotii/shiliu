from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, TypeVar

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
        if normalized_effort and normalized_effort not in {"high", "max"}:
            raise PipelineError(
                "推理强度只支持 high 或 max",
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

    def _generate(self, messages: list[dict[str, str]], *, max_tokens: int | None = None) -> str:
        return self._generate_response(messages, max_tokens=max_tokens).content

    def _generate_response(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        allow_incomplete: bool = False,
    ) -> CompletionResponse:
        body: dict[str, Any] = {"model": self.model, "messages": messages}
        if self.thinking_enabled is not None:
            body["thinking"] = {"type": "enabled" if self.thinking_enabled else "disabled"}
        if self.thinking_enabled is not False and self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        if self.thinking_enabled is False:
            body["temperature"] = 0
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions", headers=self.headers, json=body
                )
                self._raise_for_status(response)
        except PipelineError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise PipelineError("模型服务网络错误或超时", code="provider_network", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise PipelineError("模型服务请求失败", code="provider_network", retryable=True) from exc
        try:
            payload = response.json()
            choice = payload["choices"][0]
            message = choice["message"]
            content = message.get("content")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise PipelineError("模型服务返回格式无效", code="provider_schema", retryable=True) from exc
        finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
        if finish_reason == "length" and not allow_incomplete:
            raise PipelineError(
                "模型输出达到保险上限，请人工确认后重试",
                code="output_budget_exhausted",
                retryable=False,
            )
        reasoning = message.get("reasoning_content") if isinstance(message, dict) else None
        if (not isinstance(content, str) or not content.strip()) and not allow_incomplete:
            raise PipelineError("模型返回为空", code="empty_model_output", retryable=True)
        usage = payload.get("usage") if isinstance(payload, dict) else None
        return CompletionResponse(
            content=content if isinstance(content, str) else "",
            finish_reason=str(finish_reason) if finish_reason is not None else None,
            usage=usage if isinstance(usage, dict) else None,
            response_id=(
                str(payload["id"])
                if isinstance(payload, dict) and payload.get("id") is not None
                else None
            ),
            reasoning_content=reasoning if isinstance(reasoning, str) else None,
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
