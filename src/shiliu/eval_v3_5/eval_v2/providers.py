from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .contracts import AnnotationPacketV2
from .reviewer_draft import ReviewerDraft
from .reviewer_registry import (
    PRIMARY_REVIEWER,
    SECONDARY_REVIEWER,
    ReviewerProviderConfig,
)
from .workspace import strict_output_schema


SECRET_PATTERN = re.compile(
    r"(?i)(authorization|api[_-]?key|bearer)\s*[:=]\s*[^\s,}]+"
)
FORBIDDEN_PAYLOAD_TERMS = (
    "candidate_builder",
    "deterministic_selector",
    "llm_selector",
    "mechanical_gate",
    "semantic_judge",
    "sufficiency_gold",
    "evidence_gold",
    "gold_segment",
    "other_reviewer",
    "agreement_result",
    "adjudication",
    "held_out_label",
    "heldout_label",
    "historical_review",
    "system_prediction",
)


def reviewer_draft_prompt(*, role: str, protocol_excerpt: str) -> str:
    return "\n\n".join(
        [
            f"You are the independent {role} annotation reviewer. Review exactly one supplied synthetic packet. Do not use tools, the network, outside knowledge, system predictions, Gold, adjudication, historical reviews, or another review.",
            protocol_excerpt,
            "Required Aspects must be derived from the explicit information need in evidence_question. Do not derive Required Aspects from topics that merely appear in the Transcript. Transcript content may support or fail to support the Query, but it must never redefine the Query. Judge only whether this single video's complete Raw Transcript answers evidence_question; do not decide which video is best in a collection.",
            "Return only one ReviewerDraft JSON object matching the supplied schema. Define each required_aspect with non-empty text and query_anchor_texts. Every query_anchor_text must be an exact substring copied from evidence_question and must bind the Aspect to its core entity, relation, or explicit information need. For a comparison, preserve both compared entities and the comparison/advantage relation; do not expand a topic query into definitions, mechanisms, or advantages it did not request. Refer to aspects and required spans only by zero-based array indices. Required spans contain only packet segment_ids plus supported_aspect_indices. Evidence groups contain required_aspect_indices and required_span_indices. Never create A/S/G IDs, timestamps, quotes, source identities, canonical metadata, or fields outside the schema. Read the entire transcript before deciding status. Use sufficient only when every required aspect is supported by a complete evidence group; partial when supported and missing aspects are both non-empty; insufficient when no aspect is supported despite readable source; unverifiable only when source authority is unreliable.",
        ]
    )


def _decode_json_result(text: str) -> object:
    value = text.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, re.I | re.S)
    if fence:
        value = fence.group(1).strip()
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return text


def redact_secrets(value: str) -> str:
    return SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)


def provider_configured(env_name: str = "DEEPSEEK_API_KEY") -> bool:
    return bool(os.getenv(env_name))


def canonical_packet_bytes(packet: AnnotationPacketV2) -> bytes:
    return json.dumps(
        packet.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True)
class ReviewerPayload:
    packet_bytes: bytes
    prompt: str
    draft_schema: dict[str, object]

    @classmethod
    def from_packet(cls, packet: AnnotationPacketV2, prompt: str) -> "ReviewerPayload":
        schema = strict_output_schema(ReviewerDraft.model_json_schema())
        assert isinstance(schema, dict)
        return cls(canonical_packet_bytes(packet), prompt, schema)

    @property
    def packet_sha256(self) -> str:
        return hashlib.sha256(self.packet_bytes).hexdigest()


@dataclass(frozen=True)
class PayloadAudit:
    packet_sha256: str
    allowed_top_level_fields: tuple[str, ...]
    forbidden_field_scan: tuple[str, ...]
    prompt_version: str
    schema_version: str
    provider_id: str
    model: str

    @property
    def passed(self) -> bool:
        return not self.forbidden_field_scan


@dataclass(frozen=True)
class ProviderRequest:
    provider_usage: str
    endpoint_family: str
    headers_present: tuple[str, ...]
    body: dict[str, object]
    manifest: PayloadAudit


# Compatibility name retained for the existing Recovery B test surface.
SecondaryRequest = ProviderRequest


@dataclass(frozen=True)
class ReviewerRawResult:
    body: object
    requested_model: str
    response_model: str | None
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    latency_ms: int
    finish_reason: str | None


class AnnotationReviewerProvider(Protocol):
    config: ReviewerProviderConfig

    def review(self, payload: ReviewerPayload) -> ReviewerRawResult:
        ...


def audit_reviewer_payload(
    payload: ReviewerPayload, config: ReviewerProviderConfig
) -> PayloadAudit:
    packet = json.loads(payload.packet_bytes)
    if not isinstance(packet, dict):
        raise ValueError("reviewer packet must be a JSON object")
    fields = tuple(sorted(str(key) for key in packet))
    forbidden = tuple(sorted(_find_forbidden_fields(packet)))
    return PayloadAudit(
        packet_sha256=payload.packet_sha256,
        allowed_top_level_fields=fields,
        forbidden_field_scan=forbidden,
        prompt_version=config.prompt_version,
        schema_version=config.draft_schema_version,
        provider_id=config.provider_id,
        model=config.model,
    )


def _find_forbidden_fields(value: object, path: str = "") -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
            child_path = f"{path}.{key}" if path else str(key)
            if any(term in normalized for term in FORBIDDEN_PAYLOAD_TERMS):
                found.add(child_path)
            found.update(_find_forbidden_fields(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.update(_find_forbidden_fields(child, f"{path}[{index}]"))
    return found


def build_openai_primary_request(payload: ReviewerPayload) -> ProviderRequest:
    config = PRIMARY_REVIEWER
    manifest = audit_reviewer_payload(payload, config)
    if not manifest.passed:
        raise ValueError("forbidden reviewer payload fields: " + ",".join(manifest.forbidden_field_scan))
    return ProviderRequest(
        provider_usage=config.usage,
        endpoint_family="openai_responses",
        headers_present=("Authorization", "Content-Type"),
        body={
            "model": config.model,
            "instructions": payload.prompt,
            "input": payload.packet_bytes.decode("utf-8"),
            "reasoning": {"effort": config.reasoning_effort},
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "reviewer_draft",
                    "strict": True,
                    "schema": payload.draft_schema,
                }
            },
            "store": False,
        },
        manifest=manifest,
    )


def build_deepseek_secondary_request(
    packet: AnnotationPacketV2 | ReviewerPayload,
    prompt: str | None = None,
    model: str = "deepseek-v4-pro",
    reasoning_strength: str = "max",
) -> ProviderRequest:
    config = SECONDARY_REVIEWER
    if model != config.model:
        raise ValueError("annotation secondary reviewer requires deepseek-v4-pro")
    if reasoning_strength != config.reasoning_effort:
        raise ValueError("annotation secondary reviewer requires max reasoning")
    payload = packet if isinstance(packet, ReviewerPayload) else ReviewerPayload.from_packet(packet, prompt or "")
    manifest = audit_reviewer_payload(payload, config)
    if not manifest.passed:
        raise ValueError("forbidden reviewer payload fields: " + ",".join(manifest.forbidden_field_scan))
    return ProviderRequest(
        provider_usage=config.usage,
        endpoint_family="deepseek_chat_completions",
        headers_present=("Authorization", "Content-Type"),
        body={
            "model": config.model,
            "messages": [
                {
                    "role": "system",
                    "content": payload.prompt
                    + "\n\nREVIEWER_DRAFT_SCHEMA:\n"
                    + json.dumps(
                        payload.draft_schema,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                },
                {"role": "user", "content": payload.packet_bytes.decode("utf-8")},
            ],
            "thinking": {"type": config.thinking},
            "reasoning_effort": config.reasoning_effort,
            "stream": False,
        },
        manifest=manifest,
    )


class OpenAIAnnotationReviewer:
    config = PRIMARY_REVIEWER

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        client_factory: Callable[..., Any] | None = None,
    ):
        self._api_key = api_key
        self._base_url = base_url
        self._client_factory = client_factory

    def review(self, payload: ReviewerPayload) -> ReviewerRawResult:
        request = build_openai_primary_request(payload)
        if self._client_factory is None:
            from openai import OpenAI

            factory: Callable[..., Any] = OpenAI
        else:
            factory = self._client_factory
        client_options = {"api_key": self._api_key}
        if self._base_url:
            client_options["base_url"] = self._base_url
        client = factory(**client_options)
        started = time.perf_counter()
        response = client.responses.create(**request.body)
        latency_ms = round((time.perf_counter() - started) * 1000)
        usage = getattr(response, "usage", None)
        return ReviewerRawResult(
            body=_decode_json_result(response.output_text),
            requested_model=self.config.model,
            response_model=getattr(response, "model", None),
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            cached_tokens=getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", None),
            latency_ms=latency_ms,
            finish_reason=getattr(response, "status", None),
        )


class DeepSeekAnnotationReviewer:
    config = SECONDARY_REVIEWER

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        transport: Callable[[dict[str, object], dict[str, str]], dict[str, object]],
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    def review(self, payload: ReviewerPayload) -> ReviewerRawResult:
        request = build_deepseek_secondary_request(payload)
        started = time.perf_counter()
        response = self._transport(
            request.body,
            {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
        )
        latency_ms = round((time.perf_counter() - started) * 1000)
        choice = response["choices"][0]  # type: ignore[index]
        message = choice["message"]  # type: ignore[index]
        usage = response.get("usage") or {}
        assert isinstance(message, dict) and isinstance(usage, dict)
        return ReviewerRawResult(
            body=_decode_json_result(str(message.get("content") or "")),
            requested_model=self.config.model,
            response_model=str(response["model"]) if response.get("model") is not None else None,
            input_tokens=usage.get("prompt_tokens"),  # type: ignore[arg-type]
            output_tokens=usage.get("completion_tokens"),  # type: ignore[arg-type]
            cached_tokens=usage.get("prompt_cache_hit_tokens") or usage.get("cached_tokens"),  # type: ignore[arg-type]
            latency_ms=latency_ms,
            finish_reason=str(choice.get("finish_reason")) if choice.get("finish_reason") else None,
        )


class MockProvider:
    def __init__(self, response: object):
        self.response = response
        self.call_count = 0

    def invoke(self, _: ProviderRequest) -> object:
        self.call_count += 1
        return self.response
