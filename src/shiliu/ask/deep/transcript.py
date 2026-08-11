from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from shiliu.ask.citations import stable_citation_id
from shiliu.ask.context import fuse_evidence
from shiliu.ask.contracts import (
    CITATION_IDENTITY_VERSION,
    EvidenceSegment,
    TranscriptEvidenceSpan,
)
from shiliu.ask.evidence import MaterializationResult, TranscriptEvidenceMaterializer
from shiliu.db import Database
from shiliu.evidence.authority import bind_live_current_version
from shiliu.evidence.contracts import EvidenceContractError, SourceArtifactReference
from shiliu.evidence.search import EvidenceSearchService
from shiliu.evidence.source import load_source_artifact
from shiliu.retrieval.product_search import (
    ProductSearchFilterRequest,
    ProductSearchRequest,
    build_bilibili_jump_url,
)


class TranscriptSearchService:
    def __init__(
        self,
        *,
        evidence_search: EvidenceSearchService,
        materializer: TranscriptEvidenceMaterializer,
        max_spans_per_search: int = 6,
        max_characters_per_search: int = 6000,
    ) -> None:
        if max_spans_per_search <= 0 or max_characters_per_search <= 0:
            raise ValueError("transcript search evidence bounds must be positive")
        self.evidence_search = evidence_search
        self.materializer = materializer
        self.max_spans_per_search = max_spans_per_search
        self.max_characters_per_search = max_characters_per_search

    def search(
        self,
        query: str,
        *,
        filters: ProductSearchFilterRequest,
        video_ids: tuple[int, ...] = (),
        query_index: int = 0,
    ) -> "TranscriptSearchResult":
        if len(video_ids) > 8:
            raise ValueError("focused transcript search accepts at most 8 videos")
        request = ProductSearchRequest(
            query=query,
            mode="auto",
            scope="transcript_chunk",
            result_limit=10,
            max_windows_per_video=2,
            filters=filters,
        )
        execution = self.evidence_search.execute_search(
            request, video_ids=video_ids
        )
        candidates = self.evidence_search.materialize_execution(execution)
        materialized = self.materializer.materialize(
            execution, candidates, query_index=query_index
        )
        selected = []
        character_count = 0
        fused = fuse_evidence(materialized.spans)
        for span in fused:
            if len(selected) >= self.max_spans_per_search:
                break
            if (
                character_count + len(span.quote_text)
                > self.max_characters_per_search
            ):
                continue
            selected.append(span)
            character_count += len(span.quote_text)
        if not selected and fused:
            selected.append(fused[0])
        return TranscriptSearchResult(
            spans=tuple(selected),
            stale_reasons=materialized.stale_reasons,
            dropped_span_count=max(0, len(fused) - len(selected)),
            execution_id=execution.execution_id,
            search_trace_id=execution.raw_response.trace_id,
            query=execution.request.query,
        )


@dataclass(frozen=True)
class TranscriptSearchResult(MaterializationResult):
    execution_id: str = ""
    search_trace_id: str = ""
    query: str = ""


@dataclass(frozen=True)
class WindowReadResult:
    span: TranscriptEvidenceSpan


class TranscriptWindowReader:
    def __init__(self, db: Database, materializer: TranscriptEvidenceMaterializer) -> None:
        self.db = db
        self.materializer = materializer

    def read(
        self,
        *,
        video_id: int,
        anchor_segment_id: str,
        before: int = 2,
        after: int = 2,
    ) -> WindowReadResult:
        if not 0 <= before <= 4 or not 0 <= after <= 4:
            raise ValueError("window sides must be between 0 and 4")
        row = self._video_row(video_id)
        if row is None:
            raise EvidenceContractError(
                "window video is unavailable", code="citation_source_unavailable"
            )
        reference = _reference(row)
        binding = bind_live_current_version(reference, db=self.db, video_id=video_id)
        artifact = load_source_artifact(
            reference, expected_source_version=binding.source_version
        )
        matches = [
            value for value in artifact.segments
            if value.segment_id == anchor_segment_id
        ]
        if len(matches) != 1:
            raise EvidenceContractError(
                "window anchor is absent from the current source",
                code="citation_segment_missing",
            )
        anchor = matches[0]
        run = [
            value for value in artifact.segments
            if value.timeline_run_id == anchor.timeline_run_id
        ]
        run.sort(key=lambda value: value.original_ordinal)
        index = next(
            position
            for position, value in enumerate(run)
            if value.segment_id == anchor_segment_id
        )
        segments = tuple(
            run[max(0, index - before) : min(len(run), index + after + 1)]
        )
        if not segments or any(
            value.timeline_run_id != anchor.timeline_run_id for value in segments
        ):
            raise EvidenceContractError(
                "window crosses a transcript timeline",
                code="invalid_cross_timeline_chunk",
            )
        citation_id = stable_citation_id(
            source_artifact_id=artifact.source_artifact_id,
            source_version=artifact.source_version,
            timeline_run_id=anchor.timeline_run_id,
            segments=segments,
        )
        start_time = segments[0].start_time
        jump_url = build_bilibili_jump_url(
            str(row["video_url"] or ""), str(row["source_id"]), start_time
        )
        if jump_url is None:
            raise EvidenceContractError(
                "window jump URL is unavailable", code="citation_jump_url_invalid"
            )
        span = TranscriptEvidenceSpan(
            citation_id=citation_id,
            citation_identity_version=CITATION_IDENTITY_VERSION,
            video_id=video_id,
            bvid=str(row["source_id"]),
            title=str(row["title"]),
            source_type=_source_type(str(row["subtitle_source"] or "unknown")),
            source_language=str(row["subtitle_language"] or "unknown"),
            source_artifact_id=artifact.source_artifact_id,
            source_version=artifact.source_version,
            source_version_authority=binding.source_version_authority,
            timeline_run_id=anchor.timeline_run_id,
            segment_ids=tuple(value.segment_id for value in segments),
            segment_ordinals=tuple(value.original_ordinal for value in segments),
            start_time=start_time,
            end_time=segments[-1].end_time,
            quote_text="\n".join(
                value.source_text.strip()
                for value in segments
                if value.source_text.strip()
            ),
            jump_url=jump_url,
            parent_chunk_ids=(),
            retrieval_provenance=(
                {
                    "action": "read_transcript_window",
                    "anchor_segment_id": anchor_segment_id,
                    "before": before,
                    "after": after,
                },
            ),
            segments=tuple(
                EvidenceSegment(
                    segment_id=value.segment_id,
                    original_ordinal=value.original_ordinal,
                    run_local_ordinal=value.run_local_ordinal,
                    start_time=value.start_time,
                    end_time=value.end_time,
                    source_text=value.source_text,
                )
                for value in segments
            ),
        )
        self.materializer.validate_current(span)
        return WindowReadResult(span)

    def _video_row(self, video_id: int) -> sqlite3.Row | None:
        with self.db.connect() as connection:
            return connection.execute(
                """
                SELECT id AS video_id, platform, source_id, part, title,
                       video_url, subtitle_language, subtitle_source,
                       raw_subtitle_path
                FROM videos WHERE id=? AND removed_at IS NULL
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


def _source_type(value: str) -> str:
    normalized = value.lower()
    return normalized if normalized in {"human", "ai", "asr"} else "unknown"
