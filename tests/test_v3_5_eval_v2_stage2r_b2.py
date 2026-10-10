from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from shiliu.eval_v3_5.eval_v2.providers import ReviewerPayload
from shiliu.eval_v3_5.eval_v2.reviewer_registry import PRIMARY_REVIEWER, SECONDARY_REVIEWER
from shiliu.eval_v3_5.eval_v2.stage2r_b2_runtime import (
    _invoke_phase,
    derive_unavailable_agreement_status,
)
from shiliu.eval_v3_5.eval_v2.run_stage2r_b2 import remaining_candidates, specs
from shiliu.eval_v3_5.eval_v2.stage2r_b_runtime import ProviderInvocationError, RawInvocation
from shiliu.eval_v3_5.eval_v2.stage2r_b2_intake import (
    HumanDecisionValidationError,
    _validate_one,
    validate_human_decisions,
    validate_preconditions,
)


def test_b2_frozen_preconditions_and_expanded_decisions_validate() -> None:
    validate_preconditions()
    values = validate_human_decisions()
    assert [item.value["case_id"] for item in values] == [
        "V2C_B1A00001", "V2C_B1A00002"
    ]
    assert all(item.value["human_action"] == "approve_primary" for item in values)


def test_b2_expansion_is_exact_primary_mapping() -> None:
    value = validate_human_decisions()[1].value
    assert value["final_status"] == "sufficient"
    assert [span["span_id"] for span in value["final_required_spans"]] == ["S1", "S2"]
    assert value["final_reason_codes"] == [
        "COMPARATIVE_EXPLANATION_SUPPORTED",
        "CLI_ADVANTAGE_OVER_MCP_SUPPORTED",
    ]


def test_b2_validator_rejects_semantic_or_reference_mutation() -> None:
    value = copy.deepcopy(validate_human_decisions()[1].value)
    value["final_required_spans"][0]["segment_ids"][0] = "not_a_packet_segment"
    with pytest.raises(HumanDecisionValidationError):
        _validate_one(value)


def test_openai_five_attempt_policy_is_byte_identical_and_bounded() -> None:
    calls = 0
    attempts = []
    sleeps = []
    payload = ReviewerPayload(b"{}", "same", {"type": "object"})

    def invoke(_: ReviewerPayload) -> RawInvocation:
        nonlocal calls
        calls += 1
        if calls < 5:
            raise ProviderInvocationError(
                "safe", code="failed", retryable=True,
                failure_class="unknown_http_400", http_status=400,
            )
        return RawInvocation({}, "gpt-5.6-terra", 1, None, None, None, "stop", "gpt-5.6-terra", True, 1)

    result = _invoke_phase(
        payload=payload, invoke=invoke, config=PRIMARY_REVIEWER,
        packet_case_id="case", role="primary", phase="initial",
        max_total_attempts=5, retry_delays=(1, 2, 4, 8), attempts=attempts,
        sleep=sleeps.append,
    )
    assert result is not None and calls == 5
    assert sleeps == [1, 2, 4, 8]
    assert len({attempt.payload_fingerprint for attempt in attempts}) == 1
    assert attempts[0].input_tokens == "unavailable"


def test_deepseek_three_attempt_policy_exhausts_without_infinite_retry() -> None:
    calls = 0
    attempts = []
    payload = ReviewerPayload(b"{}", "same", {"type": "object"})

    def invoke(_: ReviewerPayload) -> RawInvocation:
        nonlocal calls
        calls += 1
        raise ProviderInvocationError(
            "safe", code="failed", retryable=True,
            failure_class="connection_failure",
        )

    result = _invoke_phase(
        payload=payload, invoke=invoke, config=SECONDARY_REVIEWER,
        packet_case_id="case", role="secondary", phase="initial",
        max_total_attempts=3, retry_delays=(1, 2), attempts=attempts,
        sleep=lambda _: None,
    )
    assert result is None and calls == 3 and len(attempts) == 3


def test_unavailable_agreement_states_are_explicit() -> None:
    assert derive_unavailable_agreement_status(None, None) == "unavailable_no_valid_review"
    review = object()
    assert derive_unavailable_agreement_status(review, None) == "unavailable_single_review"  # type: ignore[arg-type]


def test_b2_inventory_contains_only_two_remaining_safe_candidates() -> None:
    remaining = remaining_candidates()
    assert {row["candidate_id"] for row in remaining} == {
        "SAFEQ_4c4b6895fe044589f229",
        "SAFEQ_ab03f4a17565fae4de35",
    }
    assert {spec.candidate_id for spec in specs()} == {
        row["candidate_id"] for row in remaining
    }
    assert all(spec.projection_status == "annotatable" for spec in specs())


def test_b2_completed_assets_are_two_case_blank_non_gold_packets() -> None:
    root = Path("research/v3_5/eval_v2/stage2r_b2")
    cases = sorted(path.name for path in root.glob("V2C_B2P*") if path.is_dir())
    assert cases == ["V2C_B2P00001", "V2C_B2P00002"]
    for case in cases:
        packet = (root / case / "human_review_packet.md").read_text(encoding="utf-8")
        assert "Human decision is pending" in packet
        assert "final_status:\n" in packet
        assert "Final Gold" in packet and "not Final Gold" in packet
        assert (root / case / "primary/reviewer_packet.json").read_bytes() == (
            root / case / "secondary/reviewer_packet.json"
        ).read_bytes()
    assert not any("third" in path.name.casefold() for path in root.rglob("*"))


def test_b2_attempt_usage_includes_every_real_attempt() -> None:
    root = Path("research/v3_5/eval_v2/stage2r_b2")
    records = [
        json.loads(line)
        for line in (root / "provider_attempt_usage.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(records) == 4
    assert {(row["case_id"], row["reviewer_role"]) for row in records} == {
        ("V2C_B2P00001", "primary"), ("V2C_B2P00001", "secondary"),
        ("V2C_B2P00002", "primary"), ("V2C_B2P00002", "secondary"),
    }
    assert all(row["selected_for_final"] is True for row in records)
    assert all(row["model_body_returned"] is True for row in records)


def test_b2_adjudicated_canaries_are_not_final_gold() -> None:
    path = Path("research/v3_5/eval_v2/stage2r_b2/adjudicated_canary_cases.jsonl")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 2
    assert all(record["adjudication_status"] == "pilot_adjudicated" for record in records)
    serialized = path.read_text(encoding="utf-8")
    assert "final_master_gold" not in serialized
    assert "heldout_gold" not in serialized
    assert "gold_lock_complete" not in serialized
