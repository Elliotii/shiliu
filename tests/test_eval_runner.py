from types import SimpleNamespace
import pytest

from shiliu.eval.runner import assert_explicit_execution, assert_snapshot_only, assert_stable_repetitions


def test_explicit_modes_cannot_fallback():
    assert_explicit_execution("dense", SimpleNamespace(executed_mode="dense", fallback=False))
    with pytest.raises(ValueError):
        assert_explicit_execution("dense", SimpleNamespace(executed_mode="lexical", fallback=True))


def test_repetitions_require_identical_product_and_raw_order():
    run = {"product_video_ids": [1, 2], "raw_unit_ids": ["a", "b"]}
    assert_stable_repetitions([run, dict(run)])
    with pytest.raises(ValueError):
        assert_stable_repetitions([run, {"product_video_ids": [2, 1], "raw_unit_ids": ["a", "b"]}])


def test_snapshot_only_integrity_gate():
    assert_snapshot_only({"snapshot_sha256_before": "x", "snapshot_sha256_after": "x", "work_hashes_unchanged": True, "live_trace_counts_unchanged": {"raw": True, "presentation": True}})

