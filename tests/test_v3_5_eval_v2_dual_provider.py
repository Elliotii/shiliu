from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from shiliu.eval_v3_5.eval_v2.agreement import compare_reviews
from shiliu.eval_v3_5.eval_v2.contracts import AnnotationPacketV2, Usage
from shiliu.eval_v3_5.eval_v2.providers import (
    DeepSeekAnnotationReviewer,
    OpenAIAnnotationReviewer,
    ReviewerPayload,
    audit_reviewer_payload,
    build_deepseek_secondary_request,
    build_openai_primary_request,
)
from shiliu.eval_v3_5.eval_v2.review_compiler import CompilationContext, compile_reviewer_draft
from shiliu.eval_v3_5.eval_v2.reviewer_registry import (
    PRIMARY_REVIEWER,
    SECONDARY_REVIEWER,
)
from shiliu.eval_v3_5.eval_v2.secret_config import (
    MissingSecretError,
    load_openai_reviewer_local_config,
    load_required_secret,
)
from shiliu.eval_v3_5.eval_v2.stage2r_b_runtime import RawInvocation, run_independent_preflight
from test_v3_5_eval_v2_reviewer_draft import valid_draft


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "research/v3_5/eval_v2/stage2r_a/fixtures/annotation_packet.synthetic.v2.json"


def packet() -> AnnotationPacketV2:
    return AnnotationPacketV2.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


def invocation(body: object, model: str) -> RawInvocation:
    return RawInvocation(body, model, 1, 2, 3, 0, "stop", model, True, 1)


def context(role: str) -> CompilationContext:
    moment = datetime(2026, 7, 23, tzinfo=timezone.utc)
    return CompilationContext(
        reviewer_provider=role,
        reviewer_model="test-model",
        reviewer_role=role,
        prompt_version="test-prompt",
        started_at=moment,
        completed_at=moment,
        latency_ms=0,
        usage=Usage(input_tokens=1, output_tokens=1),
    )


def test_registry_freezes_models_usage_prompts_repairs_and_keys() -> None:
    assert PRIMARY_REVIEWER.model == "gpt-5.6-terra"
    assert PRIMARY_REVIEWER.usage == "annotation_primary_review"
    assert PRIMARY_REVIEWER.api_style == "responses"
    assert PRIMARY_REVIEWER.reasoning_effort == "high"
    assert PRIMARY_REVIEWER.temperature_policy == "omitted_unless_supported"
    assert PRIMARY_REVIEWER.prompt_version and PRIMARY_REVIEWER.repair_prompt_version
    assert PRIMARY_REVIEWER.max_repairs == 1
    assert PRIMARY_REVIEWER.key_env_var == "OPENAI_API_KEY"

    assert SECONDARY_REVIEWER.model == "deepseek-v4-pro"
    assert SECONDARY_REVIEWER.usage == "annotation_secondary_review"
    assert SECONDARY_REVIEWER.reasoning_effort == "max"
    assert SECONDARY_REVIEWER.thinking == "enabled"
    assert SECONDARY_REVIEWER.prompt_version and SECONDARY_REVIEWER.repair_prompt_version
    assert SECONDARY_REVIEWER.max_repairs == 1
    assert SECONDARY_REVIEWER.key_env_var == "DEEPSEEK_API_KEY"


def test_requests_share_packet_bytes_and_keep_provider_fields_local() -> None:
    payload = ReviewerPayload.from_packet(packet(), "review independently")
    primary = build_openai_primary_request(payload)
    secondary = build_deepseek_secondary_request(payload)

    assert primary.manifest.packet_sha256 == secondary.manifest.packet_sha256
    assert primary.body["model"] == "gpt-5.6-terra"
    assert primary.body["reasoning"] == {"effort": "high"}
    assert "temperature" not in primary.body
    assert primary.body["store"] is False
    assert primary.body["input"].encode("utf-8") == payload.packet_bytes
    assert secondary.body["model"] == "deepseek-v4-pro"
    assert secondary.body["reasoning_effort"] == "max"
    assert secondary.body["messages"][1]["content"].encode("utf-8") == payload.packet_bytes
    assert "Authorization" not in json.dumps(primary.body)
    assert "Authorization" not in json.dumps(secondary.body)


def test_payload_audit_rejects_forbidden_fields() -> None:
    raw = json.loads(ReviewerPayload.from_packet(packet(), "prompt").packet_bytes)
    raw["evidence_gold"] = {"segment_ids": ["seg_1"]}
    payload = ReviewerPayload(
        packet_bytes=json.dumps(raw).encode(), prompt="prompt", draft_schema={}
    )
    audit = audit_reviewer_payload(payload, PRIMARY_REVIEWER)
    assert audit.passed is False
    assert audit.forbidden_field_scan == ("evidence_gold",)
    with pytest.raises(ValueError, match="forbidden reviewer payload fields"):
        build_openai_primary_request(payload)


def test_openai_adapter_uses_structured_response_without_persisting_key() -> None:
    fake_key = "fake-openai-key-for-test"
    captured: dict[str, object] = {}

    class Responses:
        def create(self, **kwargs: object) -> object:
            captured.update(kwargs)
            return SimpleNamespace(
                output_text=json.dumps(valid_draft()),
                model="gpt-5.6-terra",
                status="completed",
                usage=SimpleNamespace(
                    input_tokens=10,
                    output_tokens=20,
                    input_tokens_details=SimpleNamespace(cached_tokens=3),
                ),
            )

    class Client:
        def __init__(self, api_key: str):
            assert api_key == fake_key
            self.responses = Responses()

    result = OpenAIAnnotationReviewer(api_key=fake_key, client_factory=Client).review(
        ReviewerPayload.from_packet(packet(), "prompt")
    )
    assert captured["model"] == "gpt-5.6-terra"
    assert captured["text"]["format"]["type"] == "json_schema"
    assert fake_key not in repr(result)
    assert fake_key not in json.dumps(captured)


def test_deepseek_adapter_keeps_authorization_out_of_result_and_manifest() -> None:
    fake_key = "fake-deepseek-key-for-test"
    payload = ReviewerPayload.from_packet(packet(), "prompt")

    def transport(body: dict[str, object], headers: dict[str, str]) -> dict[str, object]:
        assert body["model"] == "deepseek-v4-pro"
        assert headers["Authorization"] == f"Bearer {fake_key}"
        return {
            "model": "deepseek-v4-pro",
            "choices": [
                {
                    "message": {"content": json.dumps(valid_draft())},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }

    result = DeepSeekAnnotationReviewer(
        api_key=fake_key,
        base_url="https://api.deepseek.com/v1",
        transport=transport,
    ).review(payload)
    manifest = build_deepseek_secondary_request(payload).manifest
    assert fake_key not in repr(result)
    assert fake_key not in repr(manifest)
    assert not hasattr(result, "headers")


def test_dotenv_loader_reports_only_variable_name_on_missing(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env.local"
    dotenv.write_text("OPENAI_API_KEY=fake-local-key\n", encoding="utf-8")
    loaded = load_required_secret("OPENAI_API_KEY", dotenv_path=dotenv, environ={})
    assert loaded.source == "dotenv"
    assert "fake-local-key" not in repr(loaded)

    with pytest.raises(MissingSecretError) as exc:
        load_required_secret("DEEPSEEK_API_KEY", dotenv_path=dotenv, environ={})
    assert str(exc.value) == "missing required secret: DEEPSEEK_API_KEY"
    assert "fake-local-key" not in str(exc.value)


def test_openai_local_config_validates_registry_and_redacts_values(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env.local"
    dotenv.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=fake-local-key",
                'model="gpt-5.6-terra"',
                'base_url="https://example.invalid/v1"',
                'model_reasoning_effort="high"',
            ]
        ),
        encoding="utf-8",
    )
    config = load_openai_reviewer_local_config(dotenv_path=dotenv, environ={})
    assert config.model == PRIMARY_REVIEWER.model
    assert config.reasoning_effort == PRIMARY_REVIEWER.reasoning_effort
    assert "fake-local-key" not in repr(config)
    assert "example.invalid" not in repr(config)


def test_provider_exception_does_not_suppress_other_path() -> None:
    primary_calls = 0
    secondary_calls = 0

    def primary() -> RawInvocation:
        nonlocal primary_calls
        primary_calls += 1
        return invocation(valid_draft(), PRIMARY_REVIEWER.model)

    def secondary() -> RawInvocation:
        nonlocal secondary_calls
        secondary_calls += 1
        raise RuntimeError("fake-provider-failure")

    result = run_independent_preflight(
        packet=packet(),
        primary_invoke=primary,
        primary_repair=lambda _raw, _errors: invocation(valid_draft(), PRIMARY_REVIEWER.model),
        secondary_invoke=secondary,
        secondary_repair=lambda _raw, _errors: invocation(valid_draft(), SECONDARY_REVIEWER.model),
    )
    assert result.primary.status == "valid"
    assert result.secondary.status == "provider_error"
    assert result.secondary.provider_error == "deepseek_initial_request_failed"
    assert primary_calls == secondary_calls == 1


def test_primary_provider_exception_does_not_suppress_secondary_path() -> None:
    calls = {"primary": 0, "secondary": 0}

    def primary() -> RawInvocation:
        calls["primary"] += 1
        raise RuntimeError("fake-provider-failure")

    def secondary() -> RawInvocation:
        calls["secondary"] += 1
        return invocation(valid_draft(), SECONDARY_REVIEWER.model)

    result = run_independent_preflight(
        packet=packet(),
        primary_invoke=primary,
        primary_repair=lambda _raw, _errors: invocation(valid_draft(), PRIMARY_REVIEWER.model),
        secondary_invoke=secondary,
        secondary_repair=lambda _raw, _errors: invocation(valid_draft(), SECONDARY_REVIEWER.model),
    )
    assert result.primary.status == "provider_error"
    assert result.primary.provider_error == "openai_initial_request_failed"
    assert result.secondary.status == "valid"
    assert calls == {"primary": 1, "secondary": 1}


def test_agreement_uses_aspect_semantics_not_cross_reviewer_local_ids() -> None:
    primary_draft = {
        **valid_draft(),
        "status": "partial",
        "supported_aspect_indices": [0],
        "missing_aspect_indices": [1],
        "required_spans": [{"segment_ids": ["seg_1"], "supported_aspect_indices": [0]}],
        "evidence_groups": [{"required_aspect_indices": [0], "required_span_indices": [0]}],
    }
    secondary_draft = {
        **primary_draft,
        "required_aspects": [
            {"text": "condition beta", "query_anchor_texts": ["condition"]},
            {"text": "condition alpha", "query_anchor_texts": ["condition"]},
        ],
        "supported_aspect_indices": [1],
        "missing_aspect_indices": [0],
        "required_spans": [{"segment_ids": ["seg_1"], "supported_aspect_indices": [1]}],
        "evidence_groups": [{"required_aspect_indices": [1], "required_span_indices": [0]}],
    }
    primary = compile_reviewer_draft(
        raw_draft=primary_draft, packet=packet(), context=context("primary")
    ).annotation
    secondary = compile_reviewer_draft(
        raw_draft=secondary_draft, packet=packet(), context=context("secondary")
    ).annotation
    agreement = compare_reviews(primary, secondary)
    assert agreement.required_aspect_agreement.state == "agree"
    assert agreement.supported_aspect_agreement.state == "agree"
    assert agreement.missing_aspect_agreement.state == "agree"
    assert agreement.evidence_group_agreement.state == "agree"
