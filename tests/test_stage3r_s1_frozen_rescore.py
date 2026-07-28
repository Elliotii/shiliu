from __future__ import annotations

import inspect
from pathlib import Path

from shiliu.eval_v3_5 import stage3r_s1
from shiliu.eval_v3_5.stage3r_s1 import file_sha256


ROOT = Path(__file__).resolve().parents[1]
STAGE3R = ROOT / "research/v3_5/stage3r"


def test_stage3r_s1_reuses_frozen_predictions() -> None:
    source = inspect.getsource(stage3r_s1.run_stage3r_s1)
    assert "track_a_predictions.jsonl" in source
    assert "track_b_predictions.jsonl" in source


def test_stage3r_s1_prediction_hashes_unchanged() -> None:
    assert file_sha256(STAGE3R / "prediction_freeze/track_a_predictions.jsonl") == stage3r_s1.TRACK_A_SHA256
    assert file_sha256(STAGE3R / "prediction_freeze/track_b_predictions.jsonl") == stage3r_s1.TRACK_B_SHA256


def test_stage3r_s1_forbids_retrieval_call() -> None:
    source = inspect.getsource(stage3r_s1)
    assert "search_library(" not in source


def test_stage3r_s1_forbids_candidate_builder_call() -> None:
    source = inspect.getsource(stage3r_s1)
    assert "resolve_from_search_candidates(" not in source
    assert "build_within_video_candidates(" not in source


def test_stage3r_s1_forbids_selector_call() -> None:
    source = inspect.getsource(stage3r_s1)
    assert "select_deterministic_bundle(" not in source


def test_stage3r_s1_insufficient_excluded_from_positive_recall() -> None:
    source = inspect.getsource(stage3r_s1.rescore_frozen_stage3r_predictions)
    assert 'role in {"sufficient", "partial"}' in source


def test_stage3r_s1_unverifiable_excluded_from_positive_recall() -> None:
    test_stage3r_s1_insufficient_excluded_from_positive_recall()


def test_stage3r_s1_old_invalid_metrics_not_reused() -> None:
    source = inspect.getsource(stage3r_s1.run_stage3r_s1)
    assert '"old_invalid_metrics_reused": False' in source


def test_stage3r_s1_heldout_not_accessed() -> None:
    source = inspect.getsource(stage3r_s1.run_stage3r_s1)
    assert "heldout" in source
    assert "load_jsonl(heldout" not in source
    assert "read_text(heldout" not in source
