from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from shiliu.domain import PipelineError


@dataclass(frozen=True)
class NativeToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelTurn:
    text: str
    tool_calls: list[NativeToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    opaque_provider_state: dict[str, Any] = field(default_factory=dict)


class AssistantModelProvider(Protocol):
    def turn(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> ModelTurn: ...

    def extract_memories(self, *, prompt: str) -> list[dict[str, Any]]: ...

    def generate_json(
        self, *, system: str, prompt: str, max_tokens: int = 2400
    ) -> dict[str, Any]: ...

    def generate_json_with_usage(
        self, *, system: str, prompt: str, max_tokens: int = 2400
    ) -> tuple[dict[str, Any], dict[str, Any]]: ...


class OpenAICompatibleAssistantProvider:
    """Native tool-calling adapter using the product's configured interactive model."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        if not self.base_url.startswith(("http://", "https://")) or not model.strip():
            raise PipelineError("助手模型配置无效", code="bad_provider_config", retryable=False)

    def turn(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 4096,
    ) -> ModelTurn:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "max_tokens": max_tokens,
            "thinking": {"type": "disabled"},
        }
        payload = self._post(body)
        try:
            choice = payload["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise PipelineError(
                "助手模型返回格式无效", code="provider_schema", retryable=True
            ) from exc
        calls: list[NativeToolCall] = []
        for raw in message.get("tool_calls") or []:
            try:
                function = raw["function"]
                arguments = function.get("arguments") or "{}"
                parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
                if not isinstance(parsed, dict):
                    raise ValueError("tool arguments must be an object")
                calls.append(
                    NativeToolCall(
                        call_id=str(raw["id"]),
                        name=str(function["name"]),
                        arguments=parsed,
                    )
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise PipelineError(
                    "助手模型工具参数无效", code="tool_arguments_invalid", retryable=False
                ) from exc
        return ModelTurn(
            text=str(message.get("content") or ""),
            tool_calls=calls,
            finish_reason=str(choice.get("finish_reason") or "") or None,
            usage=dict(payload.get("usage") or {}),
            opaque_provider_state={"response_id": payload.get("id")},
        )

    def extract_memories(self, *, prompt: str) -> list[dict[str, Any]]:
        payload = self._post(
            {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是用户记忆提炼器。只依据用户原话输出 JSON；"
                            "不得把视频内容、工具结果或助手回答写成用户记忆。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": 1600,
                "thinking": {"type": "disabled"},
            }
        )
        try:
            content = payload["choices"][0]["message"]["content"]
            value = json.loads(content)
            proposals = value.get("proposals", [])
            if not isinstance(proposals, list):
                raise TypeError("proposals")
            return [dict(item) for item in proposals[:5] if isinstance(item, dict)]
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PipelineError(
                "记忆提炼返回格式无效", code="memory_proposal_invalid", retryable=False
            ) from exc

    def generate_json(
        self, *, system: str, prompt: str, max_tokens: int = 2400
    ) -> dict[str, Any]:
        return self.generate_json_with_usage(
            system=system, prompt=prompt, max_tokens=max_tokens
        )[0]

    def generate_json_with_usage(
        self, *, system: str, prompt: str, max_tokens: int = 2400
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = self._post(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": max_tokens,
                "thinking": {"type": "disabled"},
            }
        )
        try:
            value = json.loads(payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PipelineError(
                "后台整理返回格式无效", code="wiki_proposal_invalid", retryable=False
            ) from exc
        if not isinstance(value, dict):
            raise PipelineError(
                "后台整理返回格式无效", code="wiki_proposal_invalid", retryable=False
            )
        return value, dict(payload.get("usage") or {})

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise PipelineError("助手模型调用超时", code="provider_timeout", retryable=True) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            raise PipelineError(
                f"助手模型服务返回 HTTP {status}",
                code="provider_auth" if status in {401, 403} else "provider_http",
                retryable=status in {408, 429, 500, 502, 503, 504},
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise PipelineError("助手模型网络调用失败", code="provider_network", retryable=True) from exc
        if not isinstance(payload, dict):
            raise PipelineError("助手模型返回格式无效", code="provider_schema", retryable=True)
        return payload
