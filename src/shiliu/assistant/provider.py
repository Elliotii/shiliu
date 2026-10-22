from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol, Callable

import httpx

from shiliu.domain import PipelineError
from shiliu.config import ASSISTANT_INPUT_TOKENS
from shiliu.assistant.provider_request import (
    EndpointCapabilities, PreparedRequest, RequestBudget, official_capabilities,
    prepare_request, request_budget,
)


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


def contains_unexecuted_tool_protocol(raw: str) -> bool:
    """Only bare protocol lines, not inline discussion or fenced examples."""
    visible = re.sub(r"```[\s\S]*?```", "", raw)
    return bool(re.search(r"(?m)^\s*<[^>]*DSML[^>]*(?:calls|invoke|parameter)[^>]*>", visible, re.I))


class AssistantModelProvider(Protocol):
    def turn(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> ModelTurn: ...

    def prepare_request(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]],
                        max_tokens: int, stream: bool = False) -> PreparedRequest: ...

    def budget_request(self, request: PreparedRequest, *,
                       input_limit_tokens: int = ASSISTANT_INPUT_TOKENS) -> RequestBudget: ...

    def prepare_compaction(self, *, messages: list[dict[str, Any]], remaining_tokens: int,
                           input_limit_tokens: int | None = None) -> PreparedRequest: ...

    def compact_context(self, *, messages: list[dict[str, Any]], remaining_tokens: int,
                        remaining_seconds: float,
                        input_limit_tokens: int | None = None) -> ModelTurn: ...

    def send_prepared(self, request: PreparedRequest, *, on_text: Callable[[str], None] | None = None,
                      timeout_seconds: float | None = None) -> ModelTurn: ...

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
        capabilities: EndpointCapabilities | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.capabilities = capabilities or official_capabilities(self.base_url, model)
        if capabilities is not None and (
            capabilities.base_url.rstrip('/') != self.base_url or capabilities.model != model
        ):
            raise PipelineError("助手能力配置与实际端点不匹配", code="bad_provider_config", retryable=False)
        if not self.base_url.startswith(("http://", "https://")) or not model.strip():
            raise PipelineError("助手模型配置无效", code="bad_provider_config", retryable=False)

    def turn(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 4096,
    ) -> ModelTurn:
        request = self.prepare_request(messages=messages, tools=tools, max_tokens=max_tokens)
        return self._parse_turn(self._post(request.body))

    @staticmethod
    def _parse_turn(payload: dict[str, Any]) -> ModelTurn:
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
                error = PipelineError("助手模型工具参数无效", code="tool_arguments_invalid", retryable=False)
                error.usage = dict(payload.get("usage") or {})
                error.tool_names = [str(item.get("function", {}).get("name") or "") for item in message.get("tool_calls") or []]
                raise error from exc
        return ModelTurn(
            text=str(message.get("content") or ""),
            tool_calls=calls,
            finish_reason=str(choice.get("finish_reason") or "") or None,
            usage=dict(payload.get("usage") or {}),
            opaque_provider_state={"response_id": payload.get("id"),
                                   "response_model": payload.get("model")},
        )

    def stream_turn(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]],
                    max_tokens: int, on_text: Callable[[str], None]) -> ModelTurn:
        """Consume provider SSE; only content is text, and tool JSON executes after DONE."""
        request = self.prepare_request(messages=messages, tools=tools,
                                       max_tokens=max_tokens, stream=True)
        return self._stream_prepared(request, on_text=on_text)

    def _stream_prepared(self, request: PreparedRequest, *, on_text: Callable[[str], None]) -> ModelTurn:
        body = request.body
        text_parts: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        usage: dict[str, Any] = {}
        identity: dict[str, Any] = {}
        finish = None
        done = False
        try:
            with httpx.stream("POST", f"{self.base_url}/chat/completions",
                              headers={"Authorization": f"Bearer {self.api_key}"},
                              json=body, timeout=self.timeout_seconds) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError:
                    # A streamed error body must be read while the connection is open.
                    response.read()
                    raise
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        done = True
                        break
                    payload = json.loads(data)
                    identity.update({"response_id": payload.get("id"),
                                     "response_model": payload.get("model"), "transport": "sse"})
                    if payload.get("usage"):
                        usage = dict(payload["usage"])
                    for choice in payload.get("choices") or []:
                        delta = choice.get("delta") or {}
                        # reasoning_content and tool arguments are never answer text.
                        if delta.get("content"):
                            text_parts.append(str(delta["content"]))
                            on_text("".join(text_parts))
                        for item in delta.get("tool_calls") or []:
                            call = calls.setdefault(int(item["index"]),
                                                    {"id": "", "name": "", "arguments": ""})
                            call["id"] += str(item.get("id") or "")
                            function = item.get("function") or {}
                            call["name"] += str(function.get("name") or "")
                            call["arguments"] += str(function.get("arguments") or "")
                        if choice.get("finish_reason"):
                            finish = str(choice["finish_reason"])
            if not done or finish not in {"stop", "tool_calls"}:
                raise PipelineError("流式回答未完整结束，已保留进度", code="provider_stream_incomplete", retryable=True)
            parsed_calls = []
            for item in calls.values():
                arguments = json.loads(item["arguments"])
                if not isinstance(arguments, dict) or not item["id"] or not item["name"]:
                    raise ValueError("incomplete tool call")
                parsed_calls.append(NativeToolCall(item["id"], item["name"], arguments))
            return ModelTurn("".join(text_parts), parsed_calls, finish, usage, identity)
        except PipelineError as exc:
            exc.usage = usage
            raise
        except (ValueError, KeyError, TypeError) as exc:
            error = PipelineError("流式工具参数无效", code="tool_arguments_invalid", retryable=False)
            error.tool_names = [str(item.get("name") or "") for item in calls.values()]
            error.usage = usage
            raise error from exc
        except httpx.HTTPStatusError as exc:
            error = self._http_error(exc)
            if error.code != "provider_context_window_exceeded":
                # Preserve existing non-capacity stream failure behavior.
                error = PipelineError("流式连接中断，已保留进度", code="provider_stream_network", retryable=True)
            error.usage = usage
            raise error from exc
        except httpx.HTTPError as exc:
            error = PipelineError("流式连接中断，已保留进度", code="provider_stream_network", retryable=True)
            error.usage = usage
            raise error from exc

    def prepare_request(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]],
                        max_tokens: int, stream: bool = False) -> PreparedRequest:
        return prepare_request(base_url=self.base_url, model=self.model, messages=messages,
                               tools=tools, max_tokens=max_tokens, stream=stream)

    def _capabilities(self, *, low: bool = False) -> EndpointCapabilities:
        caps = self.capabilities
        if caps is None:
            raise PipelineError("当前助手端点缺少已确认的窗口/输出能力配置",
                                code="provider_capabilities_unknown", retryable=False)
        if low and (not caps.supports_low_thinking or caps.low_default_output_tokens is None):
            raise PipelineError("当前助手端点未确认 low thinking 及其默认输出额度",
                                code="provider_low_unsupported", retryable=False)
        return caps

    def budget_request(self, request: PreparedRequest, *,
                       input_limit_tokens: int = ASSISTANT_INPUT_TOKENS) -> RequestBudget:
        return request_budget(request, self._capabilities(), input_limit_tokens=input_limit_tokens)

    def prepare_compaction(self, *, messages: list[dict[str, Any]], remaining_tokens: int,
                           input_limit_tokens: int | None = None) -> PreparedRequest:
        """remaining_tokens is Run allowance AFTER final reserve, BEFORE this input/output.

        Caller handles dispatch count/deadline admission. Do not pass a balance that
        has already reserved this call's output: input and output are charged once.
        input_limit_tokens is an optional explicit summary cap, independent of the
        main working-input limit. By default only endpoint and Run capacity apply.
        """
        caps = self._capabilities(low=True)
        request = prepare_request(base_url=self.base_url, model=self.model, messages=messages,
                                  tools=[], max_tokens=1, compact=True)
        output = min(caps.low_default_output_tokens, caps.max_output_tokens,
                     caps.shared_window_tokens - request.input_tokens - caps.uncounted_input_tokens,
                     remaining_tokens - request.input_tokens)
        if output <= 0:
            raise PipelineError("会话摘要没有可用输入/输出额度", code="provider_capacity_invalid", retryable=False)
        request = prepare_request(base_url=self.base_url, model=self.model, messages=request.body['messages'],
                                  tools=[], max_tokens=output, compact=True)
        if not self.budget_request(request, input_limit_tokens=(
                caps.shared_window_tokens if input_limit_tokens is None else input_limit_tokens)).fits:
            raise PipelineError("会话摘要输入超过可用窗口", code="context_budget_exceeded", retryable=False)
        return request

    def compact_context(self, *, messages: list[dict[str, Any]], remaining_tokens: int,
                        remaining_seconds: float,
                        input_limit_tokens: int | None = None) -> ModelTurn:
        request = self.prepare_compaction(messages=messages, remaining_tokens=remaining_tokens,
                                          input_limit_tokens=input_limit_tokens)
        if remaining_seconds <= 0:
            raise PipelineError("会话摘要时间额度已耗尽", code="provider_timeout", retryable=False)
        return self.send_prepared(request, timeout_seconds=remaining_seconds)

    def send_prepared(self, request: PreparedRequest, *, on_text: Callable[[str], None] | None = None,
                      timeout_seconds: float | None = None) -> ModelTurn:
        """Dispatch exactly the admitted snapshot, without rebuilding its messages."""
        if request.base_url != self.base_url or request.model != self.model:
            raise PipelineError("请求与端点不匹配", code="bad_provider_request", retryable=False)
        if request.body.get('stream'):
            return self._stream_prepared(request, on_text=on_text or (lambda text: None))
        payload = self._post(request.body, timeout_seconds=(
            min(self.timeout_seconds, timeout_seconds) if timeout_seconds is not None else None))
        if request.purpose != 'compact':
            return self._parse_turn(payload)
        try:
            choice = payload['choices'][0]
            message = choice['message']
            if not isinstance(message, dict):
                raise TypeError('message must be an object')
        except (KeyError, IndexError, TypeError) as exc:
            error = PipelineError("会话摘要返回格式无效", code="provider_schema", retryable=True)
            error.usage = dict(payload.get('usage') or {})
            raise error from exc
        content = message.get('content')
        if (choice.get('finish_reason') != 'stop' or not isinstance(content, str)
                or not content.strip() or message.get('tool_calls') or message.get('refusal')):
            error = PipelineError("会话摘要未完整结束或正文无效", code="provider_compaction_incomplete", retryable=False)
            error.usage = dict(payload.get('usage') or {})
            error.finish_reason = choice.get('finish_reason')
            raise error
        return self._parse_turn(payload)

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
            error = PipelineError("后台整理返回格式无效", code="wiki_proposal_invalid", retryable=False)
            error.usage = dict(payload.get("usage") or {})
            raise error from exc
        if not isinstance(value, dict):
            error = PipelineError("后台整理返回格式无效", code="wiki_proposal_invalid", retryable=False)
            error.usage = dict(payload.get("usage") or {})
            raise error
        return value, dict(payload.get("usage") or {})

    @staticmethod
    def _http_error(exc: httpx.HTTPStatusError) -> PipelineError:
        status = exc.response.status_code
        try:
            error = exc.response.json().get('error')
        except (ValueError, AttributeError):
            error = None
        # Only explicit structured capacity codes. Never infer from free-form text/400.
        overflow = (status in {400, 413, 422} and isinstance(error, dict)
                    and any(isinstance(error.get(key), str)
                            and error[key] in {'context_length_exceeded', 'context_window_exceeded'}
                            for key in ('code', 'type')))
        return PipelineError(
            f"助手模型服务返回 HTTP {status}",
            code=('provider_context_window_exceeded' if overflow else
                  'provider_auth' if status in {401, 403} else 'provider_http'),
            retryable=status in {408, 429, 500, 502, 503, 504},
        )

    def _post(self, body: dict[str, Any], *, timeout_seconds: float | None = None) -> dict[str, Any]:
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=self.timeout_seconds if timeout_seconds is None else timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise PipelineError("助手模型调用超时", code="provider_timeout", retryable=True) from exc
        except httpx.HTTPStatusError as exc:
            raise self._http_error(exc) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise PipelineError("助手模型网络调用失败", code="provider_network", retryable=True) from exc
        if not isinstance(payload, dict):
            raise PipelineError("助手模型返回格式无效", code="provider_schema", retryable=True)
        return payload
