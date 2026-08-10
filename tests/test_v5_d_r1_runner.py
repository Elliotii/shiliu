from __future__ import annotations

import pytest

from scripts.v5_d_r1_source_runner import (
    FROZEN_SEQUENCE,
    all_task_ids,
    task_id,
    task_identity_manifest,
    _validate_attempt_order,
)


def test_frozen_sequence_and_all_replacement_tasks_are_deterministic() -> None:
    assert FROZEN_SEQUENCE == (
        ("V5D-S0-D-02", "baseline"),
        ("V5D-S0-D-02", "treatment"),
        ("V5D-S0-D-04", "treatment"),
        ("V5D-S0-D-04", "baseline"),
    )
    identifiers = all_task_ids()
    assert len(identifiers) == 8
    assert len(set(identifiers)) == 8
    assert len(task_identity_manifest()) == 8
    assert task_id("V5D-S0-D-02", "baseline", 1).startswith("rtask_")


def test_a1_execution_must_follow_frozen_sequence() -> None:
    manifest = {
        "attempts": [
            {
                "case_id": "V5D-S0-D-02",
                "arm": "baseline",
                "outer_attempt": 1,
            }
        ]
    }
    _validate_attempt_order(manifest, "V5D-S0-D-02", "treatment", 1)
    with pytest.raises(RuntimeError, match="next frozen arm"):
        _validate_attempt_order(manifest, "V5D-S0-D-04", "baseline", 1)


def test_replacement_requires_frozen_invalid_classification() -> None:
    manifest = {
        "attempts": [
            {
                "case_id": "V5D-S0-D-02",
                "arm": "baseline",
                "outer_attempt": 1,
                "status": "completed",
            }
        ]
    }
    with pytest.raises(RuntimeError, match="legal frozen invalid"):
        _validate_attempt_order(manifest, "V5D-S0-D-02", "baseline", 2)
    manifest["attempts"][0]["invalid_classification"] = "provider_invalid"
    _validate_attempt_order(manifest, "V5D-S0-D-02", "baseline", 2)
