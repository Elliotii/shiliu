from __future__ import annotations

import json
from pathlib import Path

import pytest

from shiliu.eval_v3_5.stage3r import (
    CORPUS_SHA256,
    FORBIDDEN_RUNTIME_FIELDS,
    project_runtime_input,
    project_scoring_input,
    run_predictions,
    runtime_file_hashes,
    runtime_projection_leaks,
    verify_corpus_identity,
)


SOURCE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "research/v3_5/stage3r/input/stage2r_final_corpus"
)
GOLD = SOURCE_ROOT / "development_gold.executable_31.jsonl"


def records() -> list[dict]:
    return [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines()]


def test_stage3r_runtime_projection_strips_gold_fields() -> None:
    projection = project_runtime_input(
        records(),
        video_ids={},
        retrieval_policy_version="frozen",
        corpus_snapshot_identity="snapshot",
    )
    assert len(projection) == 31
    assert runtime_projection_leaks(projection) == []
    assert not (FORBIDDEN_RUNTIME_FIELDS & set(projection[0]))


def test_stage3r_track_b_strips_gold_spans() -> None:
    projection = project_runtime_input(
        records(), video_ids={}, retrieval_policy_version="frozen",
        corpus_snapshot_identity="snapshot",
    )
    encoded = json.dumps([value["track_b"] for value in projection], ensure_ascii=False)
    assert "final_evidence_spans" not in encoded
    assert "required_span_ids" not in encoded
    assert "final_status" not in encoded


def test_stage3r_prediction_runner_rejects_gold_file(tmp_path: Path) -> None:
    path = tmp_path / "development_gold.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Runtime Input Projection"):
        run_predictions(
            repository_root=tmp_path, runtime_input_path=path, output_root=tmp_path,
            snapshot_db=tmp_path / "x", snapshot_artifacts=tmp_path / "y",
            artifact_manifest=tmp_path / "z", snapshot_id="x",
        )


def test_stage3r_track_a_does_not_accept_oracle_video() -> None:
    projection = project_runtime_input(
        records(), video_ids={}, retrieval_policy_version="frozen",
        corpus_snapshot_identity="snapshot",
    )
    assert all("authorized_source_identity" not in value["track_a"] for value in projection)
    assert all("internal_video_id" not in value["track_a"] for value in projection)


def test_stage3r_heldout_not_accessed() -> None:
    projection = project_runtime_input(
        records(), video_ids={}, retrieval_policy_version="frozen",
        corpus_snapshot_identity="snapshot",
    )
    assert len(projection) == 31
    assert all(value["case_id"] for value in projection)


def test_stage3r_runtime_files_unchanged() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    before = runtime_file_hashes(repository_root)
    project_scoring_input(records())
    after = runtime_file_hashes(repository_root)
    assert before == after


def test_stage3r_corpus_identity() -> None:
    result = verify_corpus_identity(
        GOLD,
        SOURCE_ROOT / "development_gold.executable_31.manifest.json",
        SOURCE_ROOT / "stage3r_readiness.audit.json",
        SOURCE_ROOT / "final_development_corpus_lock.json",
    )
    assert result["corpus_sha256"] == CORPUS_SHA256
    assert result["records"] == result["unique_case_ids"] == 31
