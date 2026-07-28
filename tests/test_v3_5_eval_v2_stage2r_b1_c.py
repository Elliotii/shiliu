from __future__ import annotations

import json
from pathlib import Path

from shiliu.eval_v3_5.eval_v2.canary import run_canary_case
from shiliu.eval_v3_5.eval_v2.providers import ReviewerPayload
from shiliu.eval_v3_5.eval_v2.stage2r_b1_c_assets import (
    B1B_ROOT,
    B1C_ROOT,
    RUNS,
    render_bundle,
    sha256_file,
)
from shiliu.eval_v3_5.eval_v2.stage2r_b1_c_transport import verify_openai_transport
from shiliu.eval_v3_5.eval_v2.stage2r_b_runtime import (
    ProviderInvocationError,
    RawInvocation,
)
from test_v3_5_eval_v2_canary import invocation, spec, valid_draft


def test_transport_verification_is_exactly_two_single_attempt_calls() -> None:
    payload_ids: list[int] = []

    def fake(payload: object) -> RawInvocation:
        payload_ids.append(id(payload))
        return RawInvocation(
            body={},
            model="gpt-5.6-terra",
            latency_ms=7,
            input_tokens=11,
            output_tokens=3,
            cached_tokens=None,
            finish_reason="completed",
            response_model="gpt-5.6-terra",
            response_model_echo_available=True,
            raw_call_count=1,
        )

    summary, usage = verify_openai_transport(fake)
    assert len(payload_ids) == 2
    assert payload_ids[0] == payload_ids[1]
    assert summary["attempts_per_call"] == [1, 1]
    assert summary["payload_fingerprints_identical"] is True
    assert summary["openai_transport_fix_verified"] is True
    assert len(usage) == 2
    assert all(record["attempt_type"] == "initial_draft" for record in usage)
    assert all(record["cached_tokens"] == "unavailable" for record in usage)


def test_transport_failure_is_not_retried_and_missing_tokens_are_not_zero() -> None:
    calls = 0

    def fail(_: object) -> RawInvocation:
        nonlocal calls
        calls += 1
        raise ProviderInvocationError(
            "sanitized",
            code="provider_request_failed",
            retryable=True,
            failure_class="unknown_http_400",
            http_status=400,
        )

    summary, usage = verify_openai_transport(fail)
    assert calls == 2
    assert summary["http_400_count"] == 2
    assert summary["openai_transport_fix_verified"] is False
    assert all(record["attempt_type"] == "transport" for record in usage)
    assert all(record["input_tokens"] == "unavailable" for record in usage)


def test_initial_and_repair_usage_are_persisted_separately(tmp_path: Path) -> None:
    case = spec(tmp_path)
    bad = valid_draft()
    bad["required_aspects"] = [
        {"text": "conditions alpha", "query_anchor_texts": ["not in question"]},
        {"text": "conditions beta", "query_anchor_texts": ["conditions"]},
    ]

    def primary(_: ReviewerPayload) -> RawInvocation:
        return invocation_with_body(bad, "gpt-5.6-terra", None)

    def repair(
        payload: ReviewerPayload, _raw: RawInvocation, _errors: tuple[str, ...]
    ) -> tuple[RawInvocation, ReviewerPayload]:
        return invocation("gpt-5.6-terra"), payload

    def secondary(_: ReviewerPayload) -> RawInvocation:
        return invocation("deepseek-v4-pro")

    result = run_canary_case(
        spec=case,
        output_root=tmp_path / "runs",
        primary_invoke_factory=primary,
        primary_repair_factory=repair,
        secondary_invoke_factory=secondary,
        secondary_repair_factory=repair,
        protocol_excerpt="fixed",
    )
    records = [
        json.loads(line)
        for line in (result.run_root / "primary/provider_attempt_usage.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [record["attempt_type"] for record in records] == [
        "initial_draft",
        "draft_repair",
    ]
    assert [record["selected_for_final"] for record in records] == [False, True]
    assert records[0]["input_tokens"] == "unavailable"
    assert records[0]["cached_tokens"] == "unavailable"


def test_bundle_is_blank_and_render_does_not_modify_original_reviews() -> None:
    protected = [
        path
        for run in RUNS
        for path in (B1B_ROOT / run).rglob("canonical_review.json")
    ]
    before = {path: sha256_file(path) for path in protected}
    bundle = render_bundle()
    after = {path: sha256_file(path) for path in protected}
    assert before == after
    assert bundle.count("human_decision:") == 2
    assert "final_status:\n" in bundle
    assert "No Final Gold was produced" in bundle
    assert "V2C_B1A00003" not in bundle


def invocation_with_body(
    body: object, model: str, input_tokens: int | None
) -> RawInvocation:
    return RawInvocation(body, model, 10, input_tokens, None, None, "stop", model, True, 1)


def test_freeze_manifest_hashes_are_reproducible_after_generation() -> None:
    manifest_path = B1C_ROOT / "canary_freeze_manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["freeze_status"] == "frozen_for_remaining_pilot"
    assert manifest["remaining_pilot_authorized"] is False
    for path, expected in manifest["source_file_sha256"].items():
        assert sha256_file(Path(path)) == expected
    for path, expected in manifest["artifact_sha256"].items():
        assert sha256_file(Path(path)) == expected
