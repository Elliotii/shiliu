from __future__ import annotations

import json
from pathlib import Path

from shiliu.eval_v3_5.eval_v2.canary import (
    CanaryCaseSpec,
    TransportBudget,
    build_canary_packet,
    invoke_with_transport_budget,
    run_canary_case,
    scan_artifacts_for_secrets,
)
from shiliu.eval_v3_5.eval_v2.providers import ReviewerPayload
from shiliu.eval_v3_5.eval_v2.stage2r_b_runtime import (
    ProviderInvocationError,
    RawInvocation,
)


def spec(tmp_path: Path) -> CanaryCaseSpec:
    raw = tmp_path / "subtitle-raw.json"
    raw.write_text(
        json.dumps(
            [
                {"from": 0.0, "to": 1.0, "content": "condition alpha"},
                {"from": 1.0, "to": 2.0, "content": "condition beta"},
            ]
        ),
        encoding="utf-8",
    )
    return CanaryCaseSpec(
        case_id="V2C_B1ATEST1",
        candidate_id="SAFEQ_TEST",
        query_id="QTEST",
        query="Which conditions?",
        evaluation_view="single_video_claim_evidence",
        evidence_question="Does this video explain which conditions?",
        projection_policy_version="v3.5-query-projection-v1",
        projection_status="annotatable",
        query_language="en",
        query_family="test_family",
        leakage_group="LGV2_TEST_ONE",
        case_class="ordinary",
        selection_reason="local-only reason",
        complexity_tags=("single_video",),
        video_id="BVTEST",
        source_language="en",
        source_type="raw_subtitle",
        raw_subtitle_json=raw,
        full_transcript_reference=raw,
        development_authorization_source="test",
    )


def valid_draft() -> dict[str, object]:
    return {
        "status": "sufficient",
        "required_aspects": [
            {"text": "conditions: alpha", "query_anchor_texts": ["conditions"]},
            {"text": "conditions: beta", "query_anchor_texts": ["conditions"]},
        ],
        "supported_aspect_indices": [0, 1],
        "missing_aspect_indices": [],
        "required_spans": [
            {
                "segment_ids": ["BVTEST_seg_000001"],
                "supported_aspect_indices": [0],
            },
            {
                "segment_ids": ["BVTEST_seg_000002"],
                "supported_aspect_indices": [1],
            },
        ],
        "optional_context_spans": [],
        "evidence_groups": [
            {"required_aspect_indices": [0, 1], "required_span_indices": [0, 1]}
        ],
        "reason_codes": [],
        "conflict_notes": "",
        "confidence": "high",
        "boundary_notes": [],
    }


def invocation(model: str) -> RawInvocation:
    return RawInvocation(valid_draft(), model, 10, 100, 20, 0, "stop", model, True, 1)


def test_canary_packet_is_full_hash_valid_and_excludes_selection_metadata(tmp_path: Path) -> None:
    packet = build_canary_packet(spec(tmp_path))
    assert len(packet.full_raw_transcript) == 2
    assert packet.full_raw_transcript[0].segment_id == "BVTEST_seg_000001"
    assert packet.source_metadata["full_transcript"] is True
    assert packet.original_query == "Which conditions?"
    assert packet.evidence_question == "Does this video explain which conditions?"
    serialized = packet.model_dump_json()
    assert "selection_reason" not in serialized
    assert "complexity_tags" not in serialized
    assert "leakage_group" not in serialized


def test_transport_retry_preserves_fingerprint_and_records_safe_failure() -> None:
    calls = 0

    def invoke() -> RawInvocation:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ProviderInvocationError(
                "sanitized",
                code="provider_request_failed",
                retryable=True,
                failure_class="http_400_transient",
                http_status=400,
            )
        return invocation("gpt-5.6-terra")

    budget = TransportBudget()
    result = invoke_with_transport_budget(
        invoke=invoke,
        phase="initial",
        fingerprint="same-payload",
        budget=budget,
        delays_ms=(0, 0),
    )
    assert result is not None
    assert calls == 2
    assert [x.payload_fingerprint for x in budget.attempts] == [
        "same-payload",
        "same-payload",
    ]
    assert budget.attempts[0].http_status == 400
    assert budget.attempts[1].success is True


def test_canary_run_writes_complete_secret_free_assets(tmp_path: Path) -> None:
    case = spec(tmp_path)

    def primary(payload: ReviewerPayload) -> RawInvocation:
        assert payload.packet_bytes
        return invocation("gpt-5.6-terra")

    def secondary(payload: ReviewerPayload) -> RawInvocation:
        assert payload.packet_bytes
        return invocation("deepseek-v4-pro")

    def no_repair(
        _payload: ReviewerPayload, _raw: RawInvocation, _errors: tuple[str, ...]
    ) -> tuple[RawInvocation, ReviewerPayload]:
        raise AssertionError("repair should not be called")

    result = run_canary_case(
        spec=case,
        output_root=tmp_path / "runs",
        primary_invoke_factory=primary,
        primary_repair_factory=no_repair,
        secondary_invoke_factory=secondary,
        secondary_repair_factory=no_repair,
        protocol_excerpt="Use only packet evidence.",
    )
    assert result.primary.status == result.secondary.status == "valid"
    assert result.agreement is not None
    assert result.human_packet_path.is_file()
    for role in ("primary", "secondary"):
        root = result.run_root / role
        assert (root / "reviewer_packet.json").is_file()
        assert (root / "packet_manifest.json").is_file()
        assert (root / "reviewer_draft.initial.json").is_file()
        assert (root / "reviewer_validation.json").is_file()
        assert (root / "canonical_review.json").is_file()
        assert (root / "provider_result_manifest.json").is_file()
        assert not (root / "reviewer_draft.repair.json").exists()
    assert (result.run_root / "primary/reviewer_packet.json").read_bytes() == (
        result.run_root / "secondary/reviewer_packet.json"
    ).read_bytes()
    human = result.human_packet_path.read_text(encoding="utf-8")
    assert "Raw text: condition alpha" in human
    assert "Human decision: **pending**" in human
    audit = scan_artifacts_for_secrets(result.run_root, secrets=("fake-real-key",))
    assert audit["passed"] is True
