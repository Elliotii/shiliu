from __future__ import annotations

import pytest

from scripts.v5_d_r1_source_runner import (
    FROZEN_SEQUENCE,
    all_task_ids,
    residual_budget_policy,
    task_id,
    task_identity_manifest,
    _validate_attempt_order,
)


def test_e1_policy_enforces_exact_r1_residual_caps() -> None:
    policy = residual_budget_policy("2026-08-11T00:00:00+00:00")
    assert policy.max_logical_calls == 99
    assert policy.max_http_attempts == 203
    assert policy.max_input_tokens == 1_051_107
    assert policy.max_output_tokens == 139_451
    assert policy.max_wall_seconds == 5_719
    assert str(policy.reserve_stop_usd) == "0.159353387"
    assert str(policy.absolute_max_cost_usd) == "0.199353387"
    assert len(policy.task_ids) == 6


def test_frozen_sequence_and_all_replacement_tasks_are_deterministic() -> None:
    assert FROZEN_SEQUENCE == (
        ("V5D-S0-D-02", "treatment"),
        ("V5D-S0-D-04", "treatment"),
        ("V5D-S0-D-04", "baseline"),
    )
    identifiers = all_task_ids()
    assert len(identifiers) == 6
    assert len(set(identifiers)) == 6
    assert len(task_identity_manifest()) == 6
    assert task_id("V5D-S0-D-02", "treatment", 1).startswith("rtask_")


def test_a1_execution_must_follow_frozen_sequence() -> None:
    manifest = {"attempts": []}
    _validate_attempt_order(manifest, "V5D-S0-D-02", "treatment", 1)
    with pytest.raises(RuntimeError, match="next frozen arm"):
        _validate_attempt_order(manifest, "V5D-S0-D-04", "baseline", 1)


def test_replacement_requires_frozen_invalid_classification() -> None:
    manifest = {
        "attempts": [
            {
                "case_id": "V5D-S0-D-02",
                "arm": "treatment",
                "outer_attempt": 1,
                "status": "completed",
            }
        ]
    }
    with pytest.raises(RuntimeError, match="legal frozen invalid"):
        _validate_attempt_order(manifest, "V5D-S0-D-02", "treatment", 2)
    manifest["attempts"][0]["invalid_classification"] = "provider_invalid"
    _validate_attempt_order(manifest, "V5D-S0-D-02", "treatment", 2)
