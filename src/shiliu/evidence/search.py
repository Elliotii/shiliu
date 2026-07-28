from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Literal

from shiliu.db import Database
from shiliu.evidence.authority import (
    bind_live_current_version,
    bind_pinned_version,
    bind_snapshot_manifest_version,
)
from shiliu.evidence.contracts import (
    CHUNK_MAPPING_VERSION,
    REPLAY_IMPLEMENTATION_VERSION,
    SEARCH_CANDIDATE_CONTRACT_VERSION,
    SOURCE_CHUNK_POLICY_VERSION,
    SOURCE_IDENTITY_VERSION,
    EvidenceContractError,
    MappingStatus,
    RetrievalChunkReference,
    SearchCandidateSet,
    SearchCandidateVideo,
    SearchRawUnitCandidate,
    SourceArtifactReference,
)
from shiliu.evidence.mapping import map_retrieval_chunk
from shiliu.retrieval.product_search import ProductSearchRequest, ProductSearchService


AuthorityMode = Literal["snapshot_manifest", "pinned_request", "live_current_exact_replay"]


class EvidenceSearchService:
    def __init__(
        self,
        *,
        db: Database,
        product_search: ProductSearchService,
        authority_mode: AuthorityMode,
        snapshot_id: str | None = None,
        artifact_manifest: str | Path | None = None,
        pinned_source_versions: dict[int, str] | None = None,
        runtime_corpus_identity: str | None = None,
    ) -> None:
        self.db = db
        self.product_search = product_search
        self.authority_mode = authority_mode
        self.snapshot_id = snapshot_id
        self.artifact_manifest = Path(artifact_manifest) if artifact_manifest else None
        self.pinned_source_versions = pinned_source_versions or {}
        self.runtime_corpus_identity = runtime_corpus_identity

    def search_library(self, request: ProductSearchRequest) -> SearchCandidateSet:
        raw, product = self.product_search.search_with_raw(request)
        rows = self._unit_rows([hit.unit_id for hit in raw.raw_hits])
        raw_candidates = tuple(
            self._raw_candidate(hit, rows.get(hit.unit_id), raw.executed_mode)
            for hit in raw.raw_hits
        )
        product_candidates = tuple(
            self._video_candidate(rank, value, raw_candidates)
            for rank, value in enumerate(product.results, 1)
        )
        reasons = ("no_search_candidate",) if not raw_candidates else ()
        return SearchCandidateSet(
            contract_version=SEARCH_CANDIDATE_CONTRACT_VERSION,
            original_query=request.query,
            request_parameters=request.model_dump(mode="json"),
            search_trace_id=raw.trace_id,
            presentation_trace_id=product.trace_id,
            trace_persisted=raw.trace_persisted,
            presentation_trace_persisted=product.presentation_trace_persisted,
            executed_mode=raw.executed_mode,
            query_type=raw.plan.query_type,
            fallback_state={
                "fallback": raw.fallback,
                "fallback_reason": raw.fallback_reason,
            },
            index_identity=dict(raw.index_identity),
            raw_unit_candidates=raw_candidates,
            video_candidates=product_candidates,
            snapshot_id=self.snapshot_id,
            runtime_corpus_identity=self.runtime_corpus_identity,
            created_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            reason_codes=reasons,
        )

    def _unit_rows(self, unit_ids: list[str]) -> dict[str, sqlite3.Row]:
        if not unit_ids:
            return {}
        placeholders = ",".join("?" for _ in unit_ids)
        with self.db.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT ru.*, v.subtitle_language, v.subtitle_source,
                       v.raw_subtitle_path
                FROM retrieval_units ru
                JOIN videos v ON v.id=ru.video_id
                WHERE ru.unit_id IN ({placeholders})
                """,
                unit_ids,
            ).fetchall()
        return {str(row["unit_id"]): row for row in rows}

    def _raw_candidate(self, hit, row: sqlite3.Row | None, executed_mode: str) -> SearchRawUnitCandidate:
        if hit.unit_type == "video":
            return _metadata_candidate(hit, row)
        if row is None:
            return _failed_candidate(hit, None, "source_unavailable", "raw_subtitle_missing")
        reference = SourceArtifactReference(
            platform=str(row["platform"]), source_id=str(row["source_id"]),
            part=int(row["part"]), source_type=str(row["subtitle_source"] or "unknown"),
            source_language=str(row["subtitle_language"] or "unknown"),
            artifact_path=str(row["raw_subtitle_path"] or ""),
        )
        try:
            binding = self._bind(reference, int(row["video_id"]), executed_mode)
        except EvidenceContractError as exc:
            status = _status_for_error(exc.code)
            return _failed_candidate(hit, row, status, exc.code)
        try:
            mapping = map_retrieval_chunk(
                reference,
                RetrievalChunkReference(
                    unit_id=str(row["unit_id"]), chunk_id=str(row["chunk_id"]),
                    start_time=float(row["start_time"]), end_time=float(row["end_time"]),
                    source_text=str(row["source_text"]), content_hash=str(row["content_hash"]),
                ),
                expected_source_version=binding.source_version_expected,
            )
        except EvidenceContractError as exc:
            status = _status_for_error(exc.code)
            return _failed_candidate(hit, row, status, exc.code, binding=binding)
        reasons: list[str] = []
        if mapping.source_validation_status == "valid_multiple_runs":
            reasons.append("source_contains_multiple_timeline_runs")
        if mapping.mapping_status != "exact_mapped":
            reasons.append(mapping.mapping_status)
        return SearchRawUnitCandidate(
            unit_id=hit.unit_id, video_id=hit.video_id, unit_type="transcript_chunk",
            raw_rank=hit.rank, raw_score=hit.score,
            retrieval_method=hit.retrieval_method,
            subtitle_source=hit.subtitle_source,
            source_language=str(row["subtitle_language"] or "unknown"),
            start_time=hit.start_time, end_time=hit.end_time,
            source_artifact_id=binding.source_artifact_id,
            source_identity_version=binding.source_identity_version,
            source_version=binding.source_version,
            source_version_authority=binding.source_version_authority,
            source_version_verified=binding.source_version_verified,
            source_version_expected=binding.source_version_expected,
            source_version_actual=binding.source_version_actual,
            segment_ids=mapping.segment_ids, segment_ordinals=mapping.segment_ordinals,
            timeline_run_id=mapping.timeline_run_id,
            mapping_status=mapping.mapping_status,
            candidate_eligibility=mapping.candidate_eligibility,
            reason_codes=tuple(reasons),
            source_chunk_policy_version=mapping.source_chunk_policy_version,
            mapping_version=mapping.mapping_version,
            replay_implementation_version=mapping.replay_implementation_version,
        )

    def _bind(self, reference: SourceArtifactReference, video_id: int, executed_mode: str):
        if self.authority_mode == "snapshot_manifest":
            if self.artifact_manifest is None:
                raise EvidenceContractError("Snapshot manifest is required", code="source_unavailable")
            return bind_snapshot_manifest_version(
                reference, video_id=video_id, manifest_path=self.artifact_manifest
            )
        if self.authority_mode == "pinned_request":
            expected = self.pinned_source_versions.get(video_id)
            if expected is None:
                raise EvidenceContractError("Pinned source version is missing", code="source_unavailable")
            return bind_pinned_version(reference, expected_source_version=expected)
        return bind_live_current_version(
            reference, db=self.db, video_id=video_id,
            require_dense_current=executed_mode in {"dense", "hybrid"},
        )

    @staticmethod
    def _video_candidate(rank, value, raw_candidates) -> SearchCandidateVideo:
        components = tuple(
            candidate.unit_id for candidate in raw_candidates if candidate.video_id == value.video_id
        )
        source_types = tuple(dict.fromkeys(
            candidate.subtitle_source for candidate in raw_candidates
            if candidate.video_id == value.video_id
        ))
        return SearchCandidateVideo(
            video_id=value.video_id, source_id=value.bvid, product_rank=rank,
            title=value.title, uploader=value.uploader,
            best_unit_id=value.best_unit_id, best_unit_type=value.best_unit_type,
            best_score=value.best_score, component_unit_ids=components,
            retrieval_methods=value.retrieval_methods,
            product_windows=tuple(value.windows), source_types=source_types,
            video_level_hit_present=value.video_level_hit_present,
        )


def _metadata_candidate(hit, row: sqlite3.Row | None) -> SearchRawUnitCandidate:
    return SearchRawUnitCandidate(
        unit_id=hit.unit_id, video_id=hit.video_id, unit_type="video",
        raw_rank=hit.rank, raw_score=hit.score, retrieval_method=hit.retrieval_method,
        subtitle_source=hit.subtitle_source,
        source_language=(str(row["subtitle_language"]) if row and row["subtitle_language"] else None),
        start_time=None, end_time=None, source_artifact_id=None,
        source_identity_version=None, source_version=None, source_version_authority=None,
        source_version_verified=False, source_version_expected=None,
        source_version_actual=None, segment_ids=(), segment_ordinals=(),
        timeline_run_id=None, mapping_status="not_applicable",
        candidate_eligibility=False, reason_codes=(),
        source_chunk_policy_version=None, mapping_version=None,
        replay_implementation_version=None,
    )


def _failed_candidate(
    hit, row, status: MappingStatus, reason: str, *, binding=None
) -> SearchRawUnitCandidate:
    return SearchRawUnitCandidate(
        unit_id=hit.unit_id, video_id=hit.video_id, unit_type="transcript_chunk",
        raw_rank=hit.rank, raw_score=hit.score, retrieval_method=hit.retrieval_method,
        subtitle_source=hit.subtitle_source,
        source_language=(str(row["subtitle_language"]) if row and row["subtitle_language"] else None),
        start_time=hit.start_time, end_time=hit.end_time,
        source_artifact_id=(binding.source_artifact_id if binding else None),
        source_identity_version=(binding.source_identity_version if binding else SOURCE_IDENTITY_VERSION),
        source_version=(binding.source_version if binding else None),
        source_version_authority=(binding.source_version_authority if binding else None),
        source_version_verified=(binding.source_version_verified if binding else False),
        source_version_expected=(binding.source_version_expected if binding else None),
        source_version_actual=(binding.source_version_actual if binding else None),
        segment_ids=(), segment_ordinals=(),
        timeline_run_id=None, mapping_status=status, candidate_eligibility=False,
        reason_codes=(reason,), source_chunk_policy_version=SOURCE_CHUNK_POLICY_VERSION,
        mapping_version=CHUNK_MAPPING_VERSION,
        replay_implementation_version=REPLAY_IMPLEMENTATION_VERSION,
    )


def _status_for_error(code: str) -> MappingStatus:
    if code == "source_version_mismatch":
        return "source_version_mismatch"
    if code in {"raw_subtitle_missing", "source_unavailable", "source_unreadable", "index_not_ready"}:
        return "source_unavailable"
    if code == "chunk_policy_version_mismatch":
        return "chunk_policy_version_mismatch"
    return "chunk_segment_mapping_failed"
