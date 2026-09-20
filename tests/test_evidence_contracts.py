from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from shiliu.evidence import (
    EvidenceContractError,
    RetrievalChunkReference,
    SourceArtifactReference,
    load_source_artifact,
    map_retrieval_chunk,
    replay_source_chunks,
    require_same_timeline_run,
)


def _write_artifact(directory: Path, segments: list[dict[str, object]]) -> Path:
    directory.mkdir(parents=True)
    path = directory / "subtitle-raw.json"
    path.write_text(
        json.dumps(segments, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return path


def _reference(path: Path, *, source_type: str = "human") -> SourceArtifactReference:
    return SourceArtifactReference(
        platform="bilibili",
        source_id="BV-test",
        part=1,
        source_type=source_type,
        source_language="zh",
        artifact_path=str(path),
    )


def _chunk_reference(replayed: object) -> RetrievalChunkReference:
    chunk = replayed.chunk
    return RetrievalChunkReference(
        unit_id=f"transcript_chunk:bilibili:BV-test:p1:{chunk.chunk_id}",
        chunk_id=chunk.chunk_id,
        start_time=chunk.start_time,
        end_time=chunk.end_time,
        source_text=chunk.text,
        content_hash=chunk.content_hash,
    )


def test_source_and_segment_identity_are_path_independent_and_version_safe(tmp_path: Path) -> None:
    payload = [
        {"from": 0, "to": 1, "content": "重复"},
        {"from": 1, "to": 2, "content": "重复"},
    ]
    first_path = _write_artifact(tmp_path / "first", payload)
    second_path = _write_artifact(tmp_path / "moved", payload)
    first = load_source_artifact(_reference(first_path))
    moved = load_source_artifact(_reference(second_path))

    assert first.source_artifact_id == moved.source_artifact_id
    assert first.source_version == moved.source_version
    assert first.segments[0].segment_id == moved.segments[0].segment_id
    assert first.segments[0].segment_id != first.segments[1].segment_id

    first_path.write_text(
        json.dumps(payload + [{"from": 2, "to": 3, "content": "变化"}], ensure_ascii=False),
        encoding="utf-8",
    )
    changed = load_source_artifact(_reference(first_path))
    assert changed.source_artifact_id == first.source_artifact_id
    assert changed.source_version != first.source_version
    assert changed.segments[0].segment_id != first.segments[0].segment_id


def test_expected_source_version_mismatch_stops_before_mapping(tmp_path: Path) -> None:
    path = _write_artifact(tmp_path / "artifact", [{"from": 0, "to": 1, "content": "正文"}])
    artifact = load_source_artifact(_reference(path))
    replayed = replay_source_chunks(artifact)[0]
    with pytest.raises(EvidenceContractError, match="does not match") as error:
        map_retrieval_chunk(
            _reference(path),
            _chunk_reference(replayed),
            expected_source_version="0" * 64,
        )
    assert error.value.code == "source_version_mismatch"


@pytest.mark.parametrize(
    ("segments", "status", "invalid"),
    [
        ([{"from": 0, "to": 1, "content": "ok"}], "valid_single_run", ()),
        ([{"from": -1, "to": 1, "content": "bad"}], "invalid_segment_time", (0,)),
        ([{"from": 2, "to": 1, "content": "bad"}], "invalid_segment_time", (0,)),
    ],
)
def test_segment_time_validation(
    tmp_path: Path,
    segments: list[dict[str, object]],
    status: str,
    invalid: tuple[int, ...],
) -> None:
    path = _write_artifact(tmp_path / status, segments)
    artifact = load_source_artifact(_reference(path))
    assert artifact.validation_status == status
    assert artifact.invalid_segment_ordinals == invalid


def test_empty_text_is_retained_without_shifting_ordinals(tmp_path: Path) -> None:
    path = _write_artifact(
        tmp_path / "empty",
        [
            {"from": 0, "to": 1, "content": "a"},
            {"from": 1, "to": 2, "content": "   "},
            {"from": 2, "to": 3, "content": "a"},
        ],
    )
    artifact = load_source_artifact(_reference(path))
    assert [segment.original_ordinal for segment in artifact.segments] == [0, 1, 2]
    assert [segment.evidence_eligible for segment in artifact.segments] == [True, False, True]
    assert len({segment.segment_id for segment in artifact.segments}) == 3


def test_same_start_and_overlap_do_not_split_a_timeline(tmp_path: Path) -> None:
    path = _write_artifact(
        tmp_path / "overlap",
        [
            {"from": 1, "to": 4, "content": "a"},
            {"from": 1, "to": 2, "content": "b"},
            {"from": 1.5, "to": 3, "content": "c"},
        ],
    )
    artifact = load_source_artifact(_reference(path))
    assert artifact.validation_status == "valid_single_run"
    assert len(artifact.timeline_runs) == 1


def test_true_backward_jump_splits_runs_and_preserves_original_order(tmp_path: Path) -> None:
    path = _write_artifact(
        tmp_path / "runs",
        [
            {"from": 10, "to": 11, "content": "first"},
            {"from": 12, "to": 13, "content": "second"},
            {"from": 0, "to": 1, "content": "third"},
            {"from": 2, "to": 3, "content": "fourth"},
        ],
    )
    artifact = load_source_artifact(_reference(path))
    assert artifact.validation_status == "valid_multiple_runs"
    assert [(run.first_original_ordinal, run.last_original_ordinal) for run in artifact.timeline_runs] == [
        (0, 1),
        (2, 3),
    ]
    assert [segment.source_text for segment in artifact.segments] == [
        "first",
        "second",
        "third",
        "fourth",
    ]
    with pytest.raises(EvidenceContractError) as error:
        require_same_timeline_run(artifact.segments)
    assert error.value.code == "invalid_cross_timeline_chunk"


def test_exact_mapping_and_all_exact_mismatch_failures(tmp_path: Path) -> None:
    path = _write_artifact(
        tmp_path / "mapping",
        [
            {"from": 0, "to": 1, "content": "a" * 500},
            {"from": 1, "to": 2, "content": "b" * 400},
        ],
    )
    reference = _reference(path, source_type="asr")
    artifact = load_source_artifact(reference)
    replayed = replay_source_chunks(artifact)[0]
    chunk = _chunk_reference(replayed)
    mapped = map_retrieval_chunk(reference, chunk, expected_source_version=artifact.source_version)
    assert mapped.mapping_status == "exact_mapped"
    assert mapped.segment_ordinals == (0, 1)
    assert mapped.candidate_eligibility is True

    mismatches = (
        replace(chunk, source_text=chunk.source_text + "x"),
        replace(chunk, content_hash="f" * 64),
        replace(chunk, start_time=chunk.start_time + 0.001),
        replace(chunk, end_time=chunk.end_time + 0.001),
    )
    for mismatch in mismatches:
        result = map_retrieval_chunk(
            reference, mismatch, expected_source_version=artifact.source_version
        )
        assert result.mapping_status == "chunk_segment_mapping_failed"
        assert result.segment_ids == ()
        assert result.candidate_eligibility is False


def test_cross_run_chunk_is_invalid_but_run_local_chunk_is_usable(tmp_path: Path) -> None:
    path = _write_artifact(
        tmp_path / "cross-run",
        [
            {"from": 100, "to": 101, "content": "a" * 500},
            {"from": 101, "to": 102, "content": "b" * 400},
            {"from": 0, "to": 1, "content": "c" * 50},
        ],
    )
    reference = _reference(path)
    artifact = load_source_artifact(reference)
    replayed = replay_source_chunks(artifact)
    results = [
        map_retrieval_chunk(
            reference,
            _chunk_reference(value),
            expected_source_version=artifact.source_version,
        )
        for value in replayed
    ]
    assert any(result.mapping_status == "exact_mapped" for result in results)
    assert any(result.mapping_status == "invalid_cross_timeline_chunk" for result in results)
    assert all(
        result.candidate_eligibility == (result.mapping_status == "exact_mapped") for result in results
    )
