from __future__ import annotations

from pathlib import Path

import pytest

from shiliu.eval_v3_5.isolation import HeldoutAccessError, HeldoutAccessGuard
from shiliu.eval_v3_5.stage4a import _classification


def test_s0_s1_metrics_false_sufficient_and_partial_warning() -> None:
    gold = [
        {"case_id": "A", "status": "sufficient"},
        {"case_id": "B", "status": "insufficient"},
        {"case_id": "C", "status": "unverifiable"},
    ]
    s0 = _classification(gold, {"A": "sufficient", "B": "sufficient", "C": "sufficient"})
    assert s0["absolute_correct_count"] == 1 and s0["absolute_incorrect_count"] == 2
    assert s0["false_sufficient_count"] == 2
    assert s0["insufficient_to_sufficient"] == 1 and s0["unverifiable_to_sufficient"] == 1
    assert "zero Development support" in s0["partial_zero_support_warning"]
    s1 = _classification(gold, {"A": "sufficient", "B": "sufficient", "C": "unverifiable"})
    assert s1["false_sufficient_count"] == 1 and s1["overall_accuracy"] == pytest.approx(2 / 3)


@pytest.mark.parametrize("fragment", [
    "eval_gold.locked", "eval_gold_review", "heldout_gold", "master_gold", "adjudicated",
    "gold_lock_manifest", "gold_lock_audit", "master_case_membership",
    "development_heldout_split", "reason_code_registry", "human_reviews", "review_packets",
])
def test_heldout_guard_rejects_protected_paths_without_opening(tmp_path: Path, fragment: str) -> None:
    guard = HeldoutAccessGuard(tmp_path)
    with pytest.raises(HeldoutAccessError):
        guard.validate_path(tmp_path / fragment)
    assert len(guard.forbidden_open_attempts) == 1
