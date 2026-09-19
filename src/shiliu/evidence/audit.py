from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import sqlite3

from shiliu.evidence.authority import bind_snapshot_manifest_version
from shiliu.evidence.contracts import EvidenceContractError, RetrievalChunkReference, SourceArtifactReference
from shiliu.evidence.mapping import map_chunk_in_artifact, replay_source_chunks
from shiliu.evidence.source import load_source_artifact


@dataclass(frozen=True)
class MappingAuditIssue:
    video_id: int
    source_id: str
    unit_id: str
    source_type: str
    status: str
    reason: str


@dataclass(frozen=True)
class MappingAuditSummary:
    total_transcript_chunks: int
    terminal_status_counts: dict[str, int]
    by_source_type: dict[str, dict[str, int]]
    by_source_language: dict[str, dict[str, int]]
    by_video_id: dict[int, dict[str, int]]
    by_timeline_status: dict[str, dict[str, int]]
    issues: tuple[MappingAuditIssue, ...]

    @property
    def accounted_total(self) -> int:
        return sum(self.terminal_status_counts.values())


def audit_snapshot_chunk_mappings(
    *,
    snapshot_db: str | Path,
    artifact_manifest: str | Path,
) -> MappingAuditSummary:
    connection = sqlite3.connect(
        f"file:{Path(snapshot_db).resolve()}?mode=ro&immutable=1", uri=True
    )
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT ru.*, v.platform, v.source_id, v.part, v.subtitle_source,
                   v.subtitle_language, v.raw_subtitle_path
            FROM retrieval_units ru
            JOIN videos v ON v.id=ru.video_id
            WHERE ru.unit_type='transcript_chunk'
            ORDER BY ru.rowid
            """
        ).fetchall()
    finally:
        connection.close()

    statuses: Counter[str] = Counter()
    source_types: dict[str, Counter[str]] = defaultdict(Counter)
    languages: dict[str, Counter[str]] = defaultdict(Counter)
    videos: dict[int, Counter[str]] = defaultdict(Counter)
    timelines: dict[str, Counter[str]] = defaultdict(Counter)
    issues: list[MappingAuditIssue] = []
    grouped: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[int(row["video_id"])].append(row)

    for video_id, video_rows in grouped.items():
        first = video_rows[0]
        reference = _reference(first)
        try:
            binding = bind_snapshot_manifest_version(
                reference, video_id=video_id, manifest_path=artifact_manifest
            )
            artifact = load_source_artifact(
                reference, expected_source_version=binding.source_version_expected
            )
            replayed = replay_source_chunks(artifact)
            timeline_status = artifact.validation_status
            for row in video_rows:
                mapping = map_chunk_in_artifact(
                    artifact, _chunk(row), replayed_chunks=replayed
                )
                status = mapping.mapping_status
                _record(statuses, source_types, languages, videos, timelines, row, status, timeline_status)
                if status != "exact_mapped":
                    issues.append(_issue(row, status, "exact replay terminal status"))
        except EvidenceContractError as exc:
            status = _authority_terminal_status(exc.code)
            for row in video_rows:
                _record(statuses, source_types, languages, videos, timelines, row, status, "unavailable")
                issues.append(_issue(row, status, str(exc)))

    return MappingAuditSummary(
        total_transcript_chunks=len(rows),
        terminal_status_counts=dict(sorted(statuses.items())),
        by_source_type=_nested(source_types),
        by_source_language=_nested(languages),
        by_video_id={key: dict(sorted(value.items())) for key, value in sorted(videos.items())},
        by_timeline_status=_nested(timelines),
        issues=tuple(issues),
    )


def _reference(row: sqlite3.Row) -> SourceArtifactReference:
    return SourceArtifactReference(
        platform=str(row["platform"]),
        source_id=str(row["source_id"]),
        part=int(row["part"]),
        source_type=str(row["subtitle_source"] or "unknown"),
        source_language=str(row["subtitle_language"] or "unknown"),
        artifact_path=str(row["raw_subtitle_path"]),
    )


def _chunk(row: sqlite3.Row) -> RetrievalChunkReference:
    return RetrievalChunkReference(
        unit_id=str(row["unit_id"]),
        chunk_id=str(row["chunk_id"]),
        start_time=float(row["start_time"]),
        end_time=float(row["end_time"]),
        source_text=str(row["source_text"]),
        content_hash=str(row["content_hash"]),
    )


def _record(statuses, source_types, languages, videos, timelines, row, status, timeline):
    statuses[status] += 1
    source_types[str(row["subtitle_source"] or "unknown")][status] += 1
    languages[str(row["subtitle_language"] or "unknown")][status] += 1
    videos[int(row["video_id"])][status] += 1
    timelines[timeline][status] += 1


def _issue(row: sqlite3.Row, status: str, reason: str) -> MappingAuditIssue:
    return MappingAuditIssue(
        video_id=int(row["video_id"]), source_id=str(row["source_id"]),
        unit_id=str(row["unit_id"]), source_type=str(row["subtitle_source"] or "unknown"),
        status=status, reason=reason,
    )


def _authority_terminal_status(code: str) -> str:
    if code in {"raw_subtitle_missing", "source_unavailable"}:
        return "source_missing"
    if code == "source_unreadable":
        return "source_unreadable"
    if code == "source_version_mismatch":
        return "source_version_mismatch"
    if code == "chunk_policy_version_mismatch":
        return "chunk_policy_version_mismatch"
    return f"other:{code}"


def _nested(values) -> dict[str, dict[str, int]]:
    return {key: dict(sorted(value.items())) for key, value in sorted(values.items())}
