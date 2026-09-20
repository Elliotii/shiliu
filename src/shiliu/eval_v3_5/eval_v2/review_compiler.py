from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime

from .contracts import (
    AnnotationPacketV2,
    AnnotationReviewV2,
    Aspect,
    EvidenceGroup,
    ReviewBody,
    ReviewMetadata,
    Span,
    Usage,
)
from .reviewer_draft import ReviewerDraft, validate_reviewer_draft
from .query_grounding import QueryGroundingValidation, validate_query_grounding


REVIEW_COMPILER_VERSION = "v3.5-review-compiler-v1"


class ReviewCompilationError(ValueError):
    def __init__(self, errors: tuple[str, ...]):
        self.errors = errors
        super().__init__("review draft compilation rejected: " + ", ".join(errors))


@dataclass(frozen=True)
class CompilationContext:
    reviewer_provider: str
    reviewer_model: str
    reviewer_role: str
    prompt_version: str
    started_at: datetime
    completed_at: datetime
    latency_ms: int
    usage: Usage = field(default_factory=Usage)
    repair_count: int = 0


@dataclass(frozen=True)
class CompiledReview:
    annotation: AnnotationReviewV2
    canonical_bytes: bytes
    sha256: str
    query_grounding: QueryGroundingValidation


def compile_reviewer_draft(
    *, raw_draft: object, packet: AnnotationPacketV2, context: CompilationContext
) -> CompiledReview:
    validation = validate_reviewer_draft(raw_draft, packet)
    if validation.status != "valid" or validation.draft is None:
        raise ReviewCompilationError(validation.errors)

    grounding = validate_query_grounding(validation.draft, packet)
    if grounding.status == "query_grounding_invalid":
        raise ReviewCompilationError(grounding.errors)

    body = compile_review_body(validation.draft, packet)
    metadata = ReviewMetadata(
        reviewer_provider=context.reviewer_provider,
        reviewer_model=context.reviewer_model,
        reviewer_role=context.reviewer_role,
        prompt_version=context.prompt_version,
        packet_version=packet.packet_version,
        case_input_sha256=packet.case_input_sha256,
        started_at=context.started_at,
        completed_at=context.completed_at,
        latency_ms=context.latency_ms,
        usage=context.usage,
        validation_status="valid",
        repair_count=context.repair_count,
    )
    annotation = AnnotationReviewV2(case_id=packet.case_id, review_metadata=metadata, review=body)
    canonical_bytes = json.dumps(
        annotation.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return CompiledReview(
        annotation=annotation,
        canonical_bytes=canonical_bytes,
        sha256=hashlib.sha256(canonical_bytes).hexdigest(),
        query_grounding=grounding,
    )


def compile_review_body(draft: ReviewerDraft, packet: AnnotationPacketV2) -> ReviewBody:
    aspects = tuple(
        Aspect(aspect_id=f"A{index + 1}", description=aspect.text)
        for index, aspect in enumerate(draft.required_aspects)
    )
    required_spans = tuple(
        _compile_span(
            packet=packet,
            segment_ids=span.segment_ids,
            span_id=f"S{index + 1}",
            role="required",
            required_aspect_ids=tuple(f"A{i + 1}" for i in span.supported_aspect_indices),
        )
        for index, span in enumerate(draft.required_spans)
    )
    optional_spans = tuple(
        _compile_span(
            packet=packet,
            segment_ids=span.segment_ids,
            span_id=f"S{len(required_spans) + index + 1}",
            role="optional_context",
            required_aspect_ids=(),
        )
        for index, span in enumerate(draft.optional_context_spans)
    )
    groups = tuple(
        EvidenceGroup(
            group_id=f"G{index + 1}",
            required_aspect_ids=tuple(f"A{i + 1}" for i in group.required_aspect_indices),
            required_span_ids=tuple(f"S{i + 1}" for i in group.required_span_indices),
            alternative_expression_notes=group.alternative_expression_notes,
        )
        for index, group in enumerate(draft.evidence_groups)
    )
    segment_ids = [segment.segment_id for segment in packet.full_raw_transcript]
    return ReviewBody(
        status=draft.status,
        required_aspects=aspects,
        supported_aspects=tuple(f"A{i + 1}" for i in draft.supported_aspect_indices),
        missing_aspects=tuple(f"A{i + 1}" for i in draft.missing_aspect_indices),
        acceptable_evidence_groups=groups,
        required_spans=required_spans,
        optional_context_spans=optional_spans,
        reason_codes=draft.reason_codes,
        conflict_notes=draft.conflict_notes,
        confidence=draft.confidence,
        boundary_notes="\n".join(draft.boundary_notes),
        reviewed_full_transcript=True,
        transcript_first_segment_id=segment_ids[0] if segment_ids else None,
        transcript_last_segment_id=segment_ids[-1] if segment_ids else None,
    )


def _compile_span(
    *,
    packet: AnnotationPacketV2,
    segment_ids: tuple[str, ...],
    span_id: str,
    role: str,
    required_aspect_ids: tuple[str, ...],
) -> Span:
    by_id = {segment.segment_id: segment for segment in packet.full_raw_transcript}
    selected = [by_id[segment_id] for segment_id in segment_ids]
    first = selected[0]
    identities = {
        (
            segment.source_artifact_id,
            segment.source_version,
            segment.timeline_run_id,
            segment.source_language,
            segment.source_type,
            _video_id(packet, segment.segment_id),
        )
        for segment in selected
    }
    if len(identities) != 1:
        dimensions = {
            "cross_timeline_run" if len({x.timeline_run_id for x in selected}) > 1 else "",
            "source_or_version_mismatch"
            if len({(x.source_artifact_id, x.source_version) for x in selected}) > 1
            else "",
            "source_language_or_type_mismatch"
            if len({(x.source_language, x.source_type) for x in selected}) > 1
            else "",
            "video_id_mismatch"
            if len({_video_id(packet, x.segment_id) for x in selected}) > 1
            else "",
        }
        raise ReviewCompilationError(tuple(sorted(x for x in dimensions if x)))
    return Span(
        span_id=span_id,
        video_id=_video_id(packet, first.segment_id),
        source_artifact_id=first.source_artifact_id,
        source_version=first.source_version,
        timeline_run_id=first.timeline_run_id,
        segment_ids=segment_ids,
        start_time=min(segment.start_time for segment in selected),
        end_time=max(segment.end_time for segment in selected),
        source_language=first.source_language,
        source_type=first.source_type,
        span_role=role,
        required_aspect_ids=required_aspect_ids,
    )


def _video_id(packet: AnnotationPacketV2, segment_id: str) -> str:
    mapping = packet.source_metadata.get("segment_video_ids")
    if isinstance(mapping, dict) and isinstance(mapping.get(segment_id), str):
        return mapping[segment_id]
    video_id = packet.source_metadata.get("video_id")
    if not isinstance(video_id, str) or not video_id:
        raise ReviewCompilationError((f"missing_video_id:{segment_id}",))
    return video_id
