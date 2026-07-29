from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Iterable

from shiliu.ask.citations import stable_citation_id
from shiliu.ask.contracts import (
    CITATION_IDENTITY_VERSION,
    EvidenceSegment,
    TranscriptEvidenceSpan,
)
from shiliu.db import Database
from shiliu.evidence.authority import bind_live_current_version
from shiliu.evidence.contracts import (
    EvidenceContractError,
    SearchCandidateSet,
    SourceArtifactReference,
)
from shiliu.evidence.search import SearchExecution
from shiliu.evidence.source import load_source_artifact
from shiliu.retrieval.product_search import build_bilibili_jump_url


@dataclass(frozen=True)
class MaterializationResult:
    spans: tuple[TranscriptEvidenceSpan, ...]
    stale_reasons: tuple[str, ...]
    dropped_span_count: int = 0


class TranscriptEvidenceMaterializer:
    def __init__(self, db: Database) -> None:
        self.db = db

    def materialize(
        self,
        execution: SearchExecution,
        candidates: SearchCandidateSet,
        *,
        query_index: int,
    ) -> MaterializationResult:
        unit_candidates = [
            value
            for value in candidates.raw_unit_candidates
            if value.unit_type == "transcript_chunk"
        ]
        rows = self._unit_rows([value.unit_id for value in unit_candidates])
        spans: list[TranscriptEvidenceSpan] = []
        stale: list[str] = []
        for candidate in unit_candidates:
            if not candidate.candidate_eligibility:
                stale.append(
                    candidate.reason_codes[0]
                    if candidate.reason_codes
                    else candidate.mapping_status
                )
                continue
            row = rows.get(candidate.unit_id)
            if row is None:
                stale.append("source_unavailable")
                continue
            try:
                spans.append(
                    self._materialize_candidate(
                        candidate,
                        row,
                        execution=execution,
                        query_index=query_index,
                    )
                )
            except (EvidenceContractError, ValueError, KeyError, TypeError) as exc:
                stale.append(getattr(exc, "code", type(exc).__name__))
        return MaterializationResult(tuple(spans), tuple(stale))

    def validate_current(self, span: TranscriptEvidenceSpan) -> None:
        row = self._video_row(span.video_id)
        if row is None:
            raise EvidenceContractError(
                "citation video no longer exists", code="citation_source_unavailable"
            )
        reference = _reference(row)
        binding = bind_live_current_version(
            reference, db=self.db, video_id=span.video_id
        )
        if (
            binding.source_artifact_id != span.source_artifact_id
            or binding.source_version != span.source_version
        ):
            raise EvidenceContractError(
                "citation source version is no longer current",
                code="citation_source_version_stale",
            )
        artifact = load_source_artifact(
            reference, expected_source_version=span.source_version
        )
        by_id = {segment.segment_id: segment for segment in artifact.segments}
        try:
            segments = tuple(by_id[value] for value in span.segment_ids)
        except KeyError as exc:
            raise EvidenceContractError(
                "citation segment no longer exists",
                code="citation_segment_missing",
            ) from exc
        _validate_candidate_segments(
            segments,
            expected_ordinals=span.segment_ordinals,
            timeline_run_id=span.timeline_run_id,
        )
        citation_id = stable_citation_id(
            source_artifact_id=span.source_artifact_id,
            source_version=span.source_version,
            timeline_run_id=span.timeline_run_id,
            segments=segments,
        )
        quote = _quote(segments)
        start_time = segments[0].start_time
        end_time = segments[-1].end_time
        jump_url = build_bilibili_jump_url(
            str(row["video_url"] or ""), str(row["source_id"]), start_time
        )
        if (
            citation_id != span.citation_id
            or quote != span.quote_text
            or start_time != span.start_time
            or end_time != span.end_time
            or jump_url != span.jump_url
        ):
            raise EvidenceContractError(
                "citation cannot be reconstructed from current segments",
                code="citation_reconstruction_failed",
            )

    def _materialize_candidate(
        self,
        candidate,
        row: sqlite3.Row,
        *,
        execution: SearchExecution,
        query_index: int,
    ) -> TranscriptEvidenceSpan:
        if (
            not candidate.source_artifact_id
            or not candidate.source_version
            or not candidate.timeline_run_id
        ):
            raise EvidenceContractError(
                "mapped candidate has incomplete source identity",
                code="citation_lineage_invalid",
            )
        reference = _reference(row)
        artifact = load_source_artifact(
            reference, expected_source_version=candidate.source_version
        )
        if artifact.source_artifact_id != candidate.source_artifact_id:
            raise EvidenceContractError(
                "mapped candidate artifact identity changed",
                code="source_version_mismatch",
            )
        by_id = {segment.segment_id: segment for segment in artifact.segments}
        try:
            segments = tuple(by_id[value] for value in candidate.segment_ids)
        except KeyError as exc:
            raise EvidenceContractError(
                "mapped segment is absent from the current source",
                code="segment_identity_invalid",
            ) from exc
        _validate_candidate_segments(
            segments,
            expected_ordinals=candidate.segment_ordinals,
            timeline_run_id=candidate.timeline_run_id,
        )
        citation_id = stable_citation_id(
            source_artifact_id=artifact.source_artifact_id,
            source_version=artifact.source_version,
            timeline_run_id=candidate.timeline_run_id,
            segments=segments,
        )
        start_time = segments[0].start_time
        end_time = segments[-1].end_time
        bvid = str(row["source_id"])
        jump_url = build_bilibili_jump_url(
            str(row["video_url"] or ""), bvid, start_time
        )
        if jump_url is None:
            raise EvidenceContractError(
                "citation jump URL is unavailable", code="citation_jump_url_invalid"
            )
        return TranscriptEvidenceSpan(
            citation_id=citation_id,
            citation_identity_version=CITATION_IDENTITY_VERSION,
            video_id=int(row["video_id"]),
            bvid=bvid,
            title=str(row["title"]),
            source_type=_source_type(candidate.subtitle_source),
            source_language=str(candidate.source_language or "unknown"),
            source_artifact_id=artifact.source_artifact_id,
            source_version=artifact.source_version,
            source_version_authority=str(candidate.source_version_authority),
            timeline_run_id=candidate.timeline_run_id,
            segment_ids=tuple(segment.segment_id for segment in segments),
            segment_ordinals=tuple(
                segment.original_ordinal for segment in segments
            ),
            start_time=start_time,
            end_time=end_time,
            quote_text=_quote(segments),
            jump_url=jump_url,
            parent_chunk_ids=(candidate.unit_id,),
            retrieval_provenance=(
                {
                    "execution_id": execution.execution_id,
                    "search_trace_id": execution.raw_response.trace_id,
                    "query": execution.request.query,
                    "query_index": query_index,
                    "rank": candidate.raw_rank,
                    "retrieval_method": candidate.retrieval_method,
                    "video_ids": list(execution.video_ids),
                },
            ),
            segments=tuple(
                EvidenceSegment(
                    segment_id=segment.segment_id,
                    original_ordinal=segment.original_ordinal,
                    run_local_ordinal=segment.run_local_ordinal,
                    start_time=segment.start_time,
                    end_time=segment.end_time,
                    source_text=segment.source_text,
                )
                for segment in segments
            ),
        )

    def _unit_rows(self, unit_ids: Iterable[str]) -> dict[str, sqlite3.Row]:
        values = list(dict.fromkeys(unit_ids))
        if not values:
            return {}
        placeholders = ",".join("?" for _ in values)
        with self.db.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT ru.*, v.source_id, v.title, v.video_url,
                       v.subtitle_language, v.subtitle_source,
                       v.raw_subtitle_path
                FROM retrieval_units ru
                JOIN videos v ON v.id=ru.video_id
                WHERE ru.unit_id IN ({placeholders})
                """,
                values,
            ).fetchall()
        return {str(row["unit_id"]): row for row in rows}

    def _video_row(self, video_id: int) -> sqlite3.Row | None:
        with self.db.connect() as connection:
            return connection.execute(
                """
                SELECT id AS video_id, platform, source_id, part, title,
                       video_url, subtitle_language, subtitle_source,
                       raw_subtitle_path
                FROM videos WHERE id=?
                """,
                (video_id,),
            ).fetchone()


def _reference(row: sqlite3.Row) -> SourceArtifactReference:
    return SourceArtifactReference(
        platform=str(row["platform"]),
        source_id=str(row["source_id"]),
        part=int(row["part"]),
        source_type=str(row["subtitle_source"] or "unknown"),
        source_language=str(row["subtitle_language"] or "unknown"),
        artifact_path=str(row["raw_subtitle_path"] or ""),
    )


def _validate_candidate_segments(
    segments,
    *,
    expected_ordinals: tuple[int, ...],
    timeline_run_id: str,
) -> None:
    if not segments:
        raise EvidenceContractError(
            "mapped candidate has no segments", code="segment_identity_invalid"
        )
    if tuple(value.original_ordinal for value in segments) != expected_ordinals:
        raise EvidenceContractError(
            "mapped candidate ordinals do not reconstruct",
            code="segment_identity_invalid",
        )
    if any(value.timeline_run_id != timeline_run_id for value in segments):
        raise EvidenceContractError(
            "mapped candidate crosses timeline runs",
            code="invalid_cross_timeline_chunk",
        )


def _quote(segments) -> str:
    return "\n".join(
        value.source_text.strip()
        for value in segments
        if value.source_text.strip()
    )


def _source_type(value: str) -> str:
    normalized = str(value or "unknown").lower()
    return normalized if normalized in {"human", "ai", "asr"} else "unknown"
