"""Assistant-only request snapshots and local capacity accounting (not a tokenizer)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from shiliu.domain import PipelineError


def estimate_tokens(value: str) -> int:
    # Preserve the established local approximation; transport and admission share it.
    ascii_count = sum(1 for character in value if ord(character) < 128)
    return max(1, ascii_count // 4 + len(value) - ascii_count + 8)


@dataclass(frozen=True)
class EndpointCapabilities:
    # Explicit overrides are assertions about this exact route, never model-name guesses.
    base_url: str
    model: str
    shared_window_tokens: int
    max_output_tokens: int
    low_default_output_tokens: int | None
    supports_low_thinking: bool
    source: str
    uncounted_input_tokens: int = 0

    def __post_init__(self) -> None:
        if (self.shared_window_tokens <= 0 or self.max_output_tokens <= 0
                or self.uncounted_input_tokens < 0 or not self.source.strip()
                or (self.low_default_output_tokens is not None
                    and not 0 < self.low_default_output_tokens <= self.max_output_tokens)):
            raise PipelineError("助手端点能力配置无效", code="bad_provider_config", retryable=False)


def official_capabilities(base_url: str, model: str) -> EndpointCapabilities | None:
    # Verified 2026-10-21; only the official HTTPS Chat Completions routes.
    if base_url.rstrip('/') not in {'https://api.deepseek.com', 'https://api.deepseek.com/v1'}:
        return None
    if model not in {'deepseek-flash', 'deepseek-v4-flash',
                     'deepseek-v4-flash-vision-exp', 'deepseek-v4-pro'}:
        return None
    return EndpointCapabilities(
        base_url=base_url.rstrip('/'), model=model,
        shared_window_tokens=1048576, max_output_tokens=393216,
        low_default_output_tokens=65536, supports_low_thinking=True,
        source='DeepSeek official Chat Completions / Models & Pricing, verified 2026-10-21: '
               'https://api-docs.deepseek.com/api/create-chat-completion/ ; '
               'https://api-docs.deepseek.com/quick_start/pricing/',
    )


@dataclass(frozen=True)
class RequestBudget:
    input_tokens: int
    input_limit_tokens: int
    shared_window_tokens: int
    output_tokens: int
    uncounted_input_tokens: int
    available_input_tokens: int

    @property
    def fits(self) -> bool:
        return self.input_tokens <= self.available_input_tokens


@dataclass(frozen=True)
class PreparedRequest:
    base_url: str
    model: str
    purpose: str
    body_json: str
    input_tokens: int

    @property
    def body(self) -> dict[str, Any]:
        # Isolate both caller-owned messages and inspection from the frozen request.
        return json.loads(self.body_json)


def prepare_request(*, base_url: str, model: str, messages: list[dict[str, Any]],
                    tools: list[dict[str, Any]], max_tokens: int,
                    stream: bool = False, compact: bool = False) -> PreparedRequest:
    if max_tokens <= 0 or (compact and (tools or stream)):
        raise PipelineError("助手请求参数无效", code="bad_provider_request", retryable=False)
    body: dict[str, Any] = {
        'model': model, 'messages': messages, 'tools': tools,
        'tool_choice': 'none' if compact else 'auto', 'max_tokens': max_tokens,
        'thinking': {'type': 'enabled' if compact else 'disabled'},
    }
    if compact:
        body['reasoning_effort'] = 'low'
    if stream:
        body.update(stream=True, stream_options={'include_usage': True})
    # Count all input-related fields, including roles, schemas and call arguments.
    # Model/output/transport controls are not model input; no hidden text is added later.
    input_body = {k: v for k, v in body.items()
                  if k not in {'model', 'max_tokens', 'stream', 'stream_options'}}
    return PreparedRequest(
        base_url, model, 'compact' if compact else 'turn',
        json.dumps(body, ensure_ascii=False),
        estimate_tokens(json.dumps(input_body, ensure_ascii=False)),
    )


def request_budget(request: PreparedRequest, capabilities: EndpointCapabilities,
                   *, input_limit_tokens: int) -> RequestBudget:
    if (request.base_url.rstrip('/') != capabilities.base_url.rstrip('/')
            or request.model != capabilities.model):
        raise PipelineError("助手能力配置与实际端点不匹配", code="bad_provider_config", retryable=False)
    output = request.body['max_tokens']
    if input_limit_tokens <= 0 or not 0 < output <= capabilities.max_output_tokens:
        raise PipelineError("助手输入/输出额度超出端点能力", code="provider_capacity_invalid", retryable=False)
    # C is already an input cap. Reserve O only against W, never against C again.
    available = min(input_limit_tokens, capabilities.shared_window_tokens
                    - output - capabilities.uncounted_input_tokens)
    return RequestBudget(request.input_tokens, input_limit_tokens,
                         capabilities.shared_window_tokens, output,
                         capabilities.uncounted_input_tokens, available)
