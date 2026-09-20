from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from shiliu.domain import SubtitleSegment
from shiliu.evidence.contracts import (
    CHUNK_MAPPING_VERSION,
    REPLAY_IMPLEMENTATION_VERSION,
    SOURCE_CHUNK_POLICY_VERSION,
    ChunkSegmentMapping,
    EvidenceContractError,
    ParsedSourceArtifact,
    RawEvidenceSegment,
    RetrievalChunkReference,
    SourceArtifactReference,
)
from shiliu.evidence.source import canonical_json, load_source_artifact
from shiliu.retrieval.chunking import ChunkingConfig, RawSubtitleChunk, build_raw_subtitle_chunks


@dataclass(frozen=True)
class ReplayedChunk:
    chunk: RawSubtitleChunk
    segments: tuple[RawEvidenceSegment, ...]


def replay_source_chunks(artifact: ParsedSourceArtifact) -> tuple[ReplayedChunk, ...]:
    if artifact.validation_status not in {"valid_single_run", "valid_multiple_runs"}:
        raise EvidenceContractError(
            "source must pass segment validation before exact chunk replay",
            code="chunk_segment_mapping_failed",
        )
    usable = [segment for segment in artifact.segments if segment.source_text.strip()]
    selections = _frozen_chunk_selections(usable, ChunkingConfig())
    chunks = build_raw_subtitle_chunks(
        platform=artifact.reference.platform,
        source_id=artifact.reference.source_id,
        part=artifact.reference.part,
        source_type=artifact.reference.source_type,
        segments=[
            SubtitleSegment.model_validate(
                {"from": segment.start_time, "to": segment.end_time, "content": segment.source_text}
            )
            for segment in artifact.segments
        ],
    )
    if len(chunks) != len(selections):
        raise EvidenceContractError(
            "frozen chunk replay selection count differs from V3 chunk output",
            code="chunk_segment_mapping_failed",
        )
    return tuple(
        ReplayedChunk(chunk=chunk, segments=selection)
        for chunk, selection in zip(chunks, selections)
    )


def map_retrieval_chunk(
    reference: SourceArtifactReference,
    chunk_reference: RetrievalChunkReference,
    *,
    expected_source_version: str,
    source_chunk_policy_version: str = SOURCE_CHUNK_POLICY_VERSION,
    replay_implementation_version: str = REPLAY_IMPLEMENTATION_VERSION,
) -> ChunkSegmentMapping:
    if (
        source_chunk_policy_version != SOURCE_CHUNK_POLICY_VERSION
        or replay_implementation_version != REPLAY_IMPLEMENTATION_VERSION
    ):
        raise EvidenceContractError(
            "chunk policy or replay implementation version is unsupported",
            code="chunk_policy_version_mismatch",
        )
    artifact = load_source_artifact(
        reference, expected_source_version=expected_source_version
    )
    return map_chunk_in_artifact(artifact, chunk_reference)


def map_chunk_in_artifact(
    artifact: ParsedSourceArtifact,
    chunk_reference: RetrievalChunkReference,
    *,
    replayed_chunks: tuple[ReplayedChunk, ...] | None = None,
) -> ChunkSegmentMapping:
    replayed_values = replayed_chunks or replay_source_chunks(artifact)
    candidates = [
        value for value in replayed_values
        if value.chunk.chunk_id == chunk_reference.chunk_id
    ]
    if len(candidates) != 1:
        return _failed_mapping(artifact, chunk_reference)
    replayed = candidates[0]
    exact = (
        replayed.chunk.start_time == chunk_reference.start_time
        and replayed.chunk.end_time == chunk_reference.end_time
        and replayed.chunk.text == chunk_reference.source_text
        and replayed.chunk.content_hash == chunk_reference.content_hash
        and chunk_reference.unit_id.endswith(":" + chunk_reference.chunk_id)
        and replayed.chunk.segment_count == len(replayed.segments)
    )
    if not exact:
        return _failed_mapping(artifact, chunk_reference)
    run_ids = {segment.timeline_run_id for segment in replayed.segments}
    cross_run = len(run_ids) != 1
    status = "invalid_cross_timeline_chunk" if cross_run else "exact_mapped"
    run_id = None if cross_run else next(iter(run_ids))
    segment_ids = tuple(segment.segment_id for segment in replayed.segments)
    ordinals = tuple(segment.original_ordinal for segment in replayed.segments)
    digest = _mapping_digest(
        chunk_reference.unit_id,
        artifact.source_artifact_id,
        artifact.source_version,
        segment_ids,
        ordinals,
        run_id,
        status,
    )
    return ChunkSegmentMapping(
        parent_chunk_id=chunk_reference.unit_id,
        source_artifact_id=artifact.source_artifact_id,
        source_version=artifact.source_version,
        segment_ids=segment_ids,
        segment_ordinals=ordinals,
        timeline_run_id=run_id,
        mapping_method="exact_chunk_replay",
        mapping_status=status,
        mapping_digest=digest,
        candidate_eligibility=not cross_run,
        mapping_version=CHUNK_MAPPING_VERSION,
        source_chunk_policy_version=SOURCE_CHUNK_POLICY_VERSION,
        replay_implementation_version=REPLAY_IMPLEMENTATION_VERSION,
        source_validation_status=artifact.validation_status,
    )


def _failed_mapping(
    artifact: ParsedSourceArtifact, chunk: RetrievalChunkReference
) -> ChunkSegmentMapping:
    status = "chunk_segment_mapping_failed"
    return ChunkSegmentMapping(
        parent_chunk_id=chunk.unit_id,
        source_artifact_id=artifact.source_artifact_id,
        source_version=artifact.source_version,
        segment_ids=(),
        segment_ordinals=(),
        timeline_run_id=None,
        mapping_method="exact_chunk_replay",
        mapping_status=status,
        mapping_digest=_mapping_digest(
            chunk.unit_id,
            artifact.source_artifact_id,
            artifact.source_version,
            (),
            (),
            None,
            status,
        ),
        candidate_eligibility=False,
        mapping_version=CHUNK_MAPPING_VERSION,
        source_chunk_policy_version=SOURCE_CHUNK_POLICY_VERSION,
        replay_implementation_version=REPLAY_IMPLEMENTATION_VERSION,
        source_validation_status=artifact.validation_status,
    )


def _mapping_digest(
    parent_chunk_id: str,
    source_artifact_id: str,
    source_version: str,
    segment_ids: tuple[str, ...],
    ordinals: tuple[int, ...],
    timeline_run_id: str | None,
    mapping_status: str,
) -> str:
    payload = {
        "mapping_status": mapping_status,
        "parent_chunk_id": parent_chunk_id,
        "segment_ids": list(segment_ids),
        "segment_ordinals": list(ordinals),
        "source_artifact_id": source_artifact_id,
        "source_version": source_version,
        "timeline_run_id": timeline_run_id,
    }
    return sha256(canonical_json(payload)).hexdigest()


def _frozen_chunk_selections(
    usable: list[RawEvidenceSegment], config: ChunkingConfig
) -> tuple[tuple[RawEvidenceSegment, ...], ...]:
    selections: list[tuple[RawEvidenceSegment, ...]] = []
    cursor = 0
    while cursor < len(usable):
        start_index = cursor
        selected: list[RawEvidenceSegment] = []
        characters = 0
        while cursor < len(usable):
            candidate = usable[cursor]
            candidate_text = candidate.source_text.strip()
            separator = 1 if selected else 0
            next_characters = characters + separator + len(candidate_text)
            first_start = selected[0].start_time if selected else candidate.start_time
            next_duration = candidate.end_time - first_start
            exceeds_bound = bool(selected) and (
                next_characters > config.maximum_characters
                or next_duration > config.maximum_duration_seconds
            )
            if exceeds_bound:
                break
            selected.append(candidate)
            characters = next_characters
            cursor += 1
            if characters >= config.target_characters:
                break
        if selected:
            selections.append(tuple(selected))
        if cursor < len(usable) and config.trailing_segment_overlap and len(selected) > 1:
            cursor -= 1
        if cursor <= start_index:
            cursor = start_index + 1
    return tuple(selections)
