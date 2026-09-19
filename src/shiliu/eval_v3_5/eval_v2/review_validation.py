from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from pydantic import ValidationError

from .contracts import AnnotationPacketV2, AnnotationReviewV2, ReviewBody, ReviewMetadata, Span, Usage


@dataclass(frozen=True)
class ValidationResult:
    status: str
    review: AnnotationReviewV2 | None
    errors: tuple[str, ...]
    repair_count: int
    query_grounding_status: str = "valid"
    query_grounding_errors: tuple[str, ...] = ()


def bind_local_review_identity(*, packet: AnnotationPacketV2, review_body: object, provider: str, model: str,
                               role: str, prompt_version: str, started_at: datetime, completed_at: datetime,
                               latency_ms: int, usage: Usage | None = None, repair_count: int = 0) -> AnnotationReviewV2:
    """Bind identities locally; reviewer-generated identity fields are never trusted."""
    body = ReviewBody.model_validate(review_body)
    metadata = ReviewMetadata(reviewer_provider=provider, reviewer_model=model, reviewer_role=role,
        prompt_version=prompt_version, packet_version=packet.packet_version,
        case_input_sha256=packet.case_input_sha256, started_at=started_at, completed_at=completed_at,
        latency_ms=latency_ms, usage=usage or Usage(), validation_status="valid", repair_count=repair_count)
    return AnnotationReviewV2(case_id=packet.case_id, review_metadata=metadata, review=body)


def validate_review(raw: object, packet: AnnotationPacketV2) -> ValidationResult:
    try:
        review = AnnotationReviewV2.model_validate(raw)
    except ValidationError as exc:
        return ValidationResult("invalid", None, tuple(_schema_errors(exc)), 0)
    errors = _semantic_errors(review, packet)
    return ValidationResult("valid" if not errors else "invalid", review if not errors else None, tuple(errors), 0)


def validate_with_one_repair(raw: object, packet: AnnotationPacketV2,
                             repair: Callable[[object, tuple[str, ...], AnnotationPacketV2], object]) -> ValidationResult:
    initial = validate_review(raw, packet)
    if initial.status == "valid":
        return initial
    repaired = validate_review(repair(raw, initial.errors, packet), packet)
    return ValidationResult(repaired.status, repaired.review, repaired.errors, 1)


def reconstruct_span(span: Span, packet: AnnotationPacketV2) -> dict[str, object]:
    by_id = {x.segment_id: x for x in packet.full_raw_transcript}
    selected = [by_id[x] for x in span.segment_ids]
    return {
        "span_id": span.span_id,
        "quote_text": "".join(x.text for x in selected),
        "start_time": min(x.start_time for x in selected),
        "end_time": max(x.end_time for x in selected),
        "segment_ids": list(span.segment_ids),
    }


def _schema_errors(exc: ValidationError) -> list[str]:
    return [f"schema:{'.'.join(map(str, item['loc']))}:{item['type']}" for item in exc.errors()]


def _semantic_errors(review: AnnotationReviewV2, packet: AnnotationPacketV2) -> list[str]:
    errors: list[str] = []
    meta, body = review.review_metadata, review.review
    if review.case_id != packet.case_id:
        errors.append("case_id_mismatch")
    if meta.case_input_sha256 != packet.case_input_sha256:
        errors.append("case_input_sha256_mismatch")
    ids = [x.segment_id for x in packet.full_raw_transcript]
    by_id = {x.segment_id: x for x in packet.full_raw_transcript}
    if not body.reviewed_full_transcript:
        errors.append("full_transcript_not_reviewed")
    first = ids[0] if ids else None
    last = ids[-1] if ids else None
    if body.transcript_first_segment_id != first or body.transcript_last_segment_id != last:
        errors.append("transcript_boundary_mismatch")
    aspect_ids = {x.aspect_id for x in body.required_aspects}
    supported, missing = set(body.supported_aspects), set(body.missing_aspects)
    if supported & missing or not supported | missing <= aspect_ids:
        errors.append("illegal_aspect_reference")
    spans = body.required_spans + body.optional_context_spans
    for span in spans:
        selected = [by_id.get(x) for x in span.segment_ids]
        if any(x is None for x in selected):
            errors.append(f"invalid_segment_id:{span.span_id}")
            continue
        assert all(x is not None for x in selected)
        if any(x.timeline_run_id != span.timeline_run_id for x in selected):
            errors.append(f"timeline_run_mismatch:{span.span_id}")
        if any(x.source_artifact_id != span.source_artifact_id or x.source_version != span.source_version for x in selected):
            errors.append(f"source_identity_mismatch:{span.span_id}")
        rebuilt = reconstruct_span(span, packet)
        if rebuilt["start_time"] != span.start_time or rebuilt["end_time"] != span.end_time:
            errors.append(f"span_time_not_reconstructed:{span.span_id}")
    span_ids = {x.span_id for x in body.required_spans}
    for group in body.acceptable_evidence_groups:
        if not set(group.required_span_ids) <= span_ids or not set(group.required_aspect_ids) <= aspect_ids:
            errors.append(f"illegal_group_reference:{group.group_id}")
            continue
        selected = [x for x in body.required_spans if x.span_id in group.required_span_ids]
        source_runs: dict[tuple[str, str, str], set[str]] = {}
        for span in selected:
            source_runs.setdefault((span.video_id, span.source_artifact_id, span.source_version), set()).add(span.timeline_run_id)
        if any(len(runs) > 1 for runs in source_runs.values()):
            errors.append(f"cross_timeline_group:{group.group_id}")
    if body.status == "sufficient" and (supported != aspect_ids or missing or not body.acceptable_evidence_groups):
        errors.append("illegal_sufficient_state")
    if body.status == "partial" and (not supported or not missing):
        errors.append("illegal_partial_state")
    if body.status == "insufficient" and supported:
        errors.append("illegal_insufficient_state")
    return errors
