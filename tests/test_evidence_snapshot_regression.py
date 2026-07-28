from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from shiliu.evidence import (
    RetrievalChunkReference,
    SourceArtifactReference,
    load_source_artifact,
    map_retrieval_chunk,
    replay_source_chunks,
    source_version_for_bytes,
)


SNAPSHOT_ROOT = Path(
    "/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365"
)
SNAPSHOT_DB = SNAPSHOT_ROOT / "shiliu_eval.db"
GOLD_LEDGER = Path("research/v3_eval/eval_gold_review.decisions.amended.jsonl")
ARTIFACT_MANIFEST = Path("research/v3_eval/artifact_manifest.jsonl")
EXPECTED_DB_SHA256 = "61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1"
VIDEO_88_SHA256 = "cc6afce905dc90ee1c89d1906c2617ba80c4992196c256e5fa8a66db9c0e2f0c"


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{SNAPSHOT_DB}?mode=ro&immutable=1", uri=True)


def _source_reference(row: sqlite3.Row) -> SourceArtifactReference:
    return SourceArtifactReference(
        platform=row["platform"],
        source_id=row["source_id"],
        part=row["part"],
        source_type=row["subtitle_source"],
        source_language=row["subtitle_language"],
        artifact_path=row["raw_subtitle_path"],
    )


def _chunk_reference(row: sqlite3.Row) -> RetrievalChunkReference:
    return RetrievalChunkReference(
        unit_id=row["unit_id"],
        chunk_id=row["chunk_id"],
        start_time=row["start_time"],
        end_time=row["end_time"],
        source_text=row["source_text"],
        content_hash=row["content_hash"],
    )


def _video_and_chunks(video_id: int) -> tuple[sqlite3.Row, list[sqlite3.Row]]:
    connection = _connect()
    connection.row_factory = sqlite3.Row
    try:
        video = connection.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        assert video is not None
        chunks = connection.execute(
            "SELECT * FROM retrieval_units WHERE video_id = ? AND unit_type = 'transcript_chunk' "
            "ORDER BY rowid",
            (video_id,),
        ).fetchall()
        return video, chunks
    finally:
        connection.close()


def test_real_ai_human_and_asr_chunks_map_exactly() -> None:
    # Video 78 and 77 are the two Phase 0 AI exact-mapping examples; 14 is human; 2 is ASR.
    for video_id in (78, 77, 14, 2):
        video, chunks = _video_and_chunks(video_id)
        reference = _source_reference(video)
        version = source_version_for_bytes(Path(reference.artifact_path).read_bytes())
        result = map_retrieval_chunk(
            reference, _chunk_reference(chunks[0]), expected_source_version=version
        )
        assert result.mapping_status == "exact_mapped"
        assert result.segment_ids
        assert result.candidate_eligibility is True


def test_video_88_has_two_runs_and_exactly_one_invalid_cross_run_chunk() -> None:
    video, chunks = _video_and_chunks(88)
    reference = _source_reference(video)
    path = Path(reference.artifact_path)
    before = _hash(path)
    artifact = load_source_artifact(reference, expected_source_version=VIDEO_88_SHA256)

    assert artifact.validation_status == "valid_multiple_runs"
    assert len(artifact.segments) == 1748
    assert [
        (run.first_original_ordinal, run.last_original_ordinal, run.start_time, run.end_time)
        for run in artifact.timeline_runs
    ] == [
        (0, 1388, 567.4, 2767.8),
        (1389, 1747, 0.133, 567.333),
    ]

    results = [
        map_retrieval_chunk(
            reference,
            _chunk_reference(chunk),
            expected_source_version=artifact.source_version,
        )
        for chunk in chunks
    ]
    invalid = [value for value in results if value.mapping_status == "invalid_cross_timeline_chunk"]
    mapped = [value for value in results if value.mapping_status == "exact_mapped"]
    assert len(invalid) == 1
    assert invalid[0].parent_chunk_id.endswith("chunk_cc3222c5f91a7fa074ec5802f8a21799")
    assert invalid[0].candidate_eligibility is False
    assert mapped
    assert all(value.candidate_eligibility for value in mapped)
    assert _hash(path) == before == VIDEO_88_SHA256


def test_all_ten_approved_intervals_map_to_contiguous_run_local_raw_segments() -> None:
    intervals: list[dict[str, object]] = []
    for line in GOLD_LEDGER.read_text(encoding="utf-8").splitlines():
        intervals.extend(json.loads(line)["approved_intervals"])
    assert len(intervals) == 10

    mapped_segment_count = 0
    for interval in intervals:
        video, _ = _video_and_chunks(int(interval["video_id"]))
        reference = _source_reference(video)
        artifact = load_source_artifact(reference)
        start = int(interval["raw_segment_start_index"])
        end = int(interval["raw_segment_end_index"])
        selected = tuple(
            segment for segment in artifact.segments if start <= segment.original_ordinal <= end
        )
        assert [segment.original_ordinal for segment in selected] == list(range(start, end + 1))
        assert len({segment.timeline_run_id for segment in selected}) == 1
        assert selected[0].start_time == pytest.approx(float(interval["start"]))
        assert selected[-1].end_time == pytest.approx(float(interval["end"]))
        assert all(segment.source_version == artifact.source_version for segment in selected)
        assert all(segment.segment_id for segment in selected)
        mapped_segment_count += len(selected)
    assert mapped_segment_count > 10


def test_snapshot_database_integrity_hash() -> None:
    assert _hash(SNAPSHOT_DB) == EXPECTED_DB_SHA256
    checked = 0
    for line in ARTIFACT_MANIFEST.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["status"] != "ok":
            continue
        snapshot_path = Path(record["snapshot_path"])
        assert snapshot_path.is_file()
        assert snapshot_path.stat().st_size == record["size"]
        assert _hash(snapshot_path) == record["sha256"]
        checked += 1
    assert checked == 372
