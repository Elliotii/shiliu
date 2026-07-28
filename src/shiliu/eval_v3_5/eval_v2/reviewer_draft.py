from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from .contracts import AnnotationPacketV2, Confidence, Status, StrictModel


REVIEWER_DRAFT_SCHEMA_VERSION = "v3.5-reviewer-draft-v2"


class DraftAspect(StrictModel):
    text: str = Field(min_length=1)
    query_anchor_texts: tuple[str, ...] = Field(min_length=1)


class DraftRequiredSpan(StrictModel):
    segment_ids: tuple[str, ...] = Field(min_length=1)
    supported_aspect_indices: tuple[int, ...] = Field(min_length=1)


class DraftOptionalContextSpan(StrictModel):
    segment_ids: tuple[str, ...] = Field(min_length=1)


class DraftEvidenceGroup(StrictModel):
    required_aspect_indices: tuple[int, ...] = Field(min_length=1)
    required_span_indices: tuple[int, ...] = Field(min_length=1)
    alternative_expression_notes: str = ""


class ReviewerDraft(StrictModel):
    """Model-facing review contract. It deliberately has no A/S/G identity fields."""

    status: Status
    required_aspects: tuple[DraftAspect, ...]
    supported_aspect_indices: tuple[int, ...]
    missing_aspect_indices: tuple[int, ...]
    required_spans: tuple[DraftRequiredSpan, ...]
    optional_context_spans: tuple[DraftOptionalContextSpan, ...] = ()
    evidence_groups: tuple[DraftEvidenceGroup, ...]
    reason_codes: tuple[str, ...]
    conflict_notes: str = ""
    confidence: Confidence
    boundary_notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def unique_local_references(self) -> "ReviewerDraft":
        collections = (
            self.supported_aspect_indices,
            self.missing_aspect_indices,
            *(span.supported_aspect_indices for span in self.required_spans),
            *(group.required_aspect_indices for group in self.evidence_groups),
            *(group.required_span_indices for group in self.evidence_groups),
        )
        if any(len(values) != len(set(values)) for values in collections):
            raise ValueError("draft index lists must not contain duplicates")
        if any(index < 0 for values in collections for index in values):
            raise ValueError("draft indices must be non-negative")
        return self


@dataclass(frozen=True)
class DraftValidationResult:
    status: Literal["valid", "invalid"]
    draft: ReviewerDraft | None
    errors: tuple[str, ...]
    repair_count: int = 0


def validate_reviewer_draft(raw: object, packet: AnnotationPacketV2) -> DraftValidationResult:
    try:
        draft = ReviewerDraft.model_validate(raw)
    except ValidationError as exc:
        errors = tuple(
            f"schema:{'.'.join(map(str, item['loc']))}:{item['type']}" for item in exc.errors()
        )
        return DraftValidationResult("invalid", None, errors)

    errors = tuple(_semantic_errors(draft, packet))
    return DraftValidationResult("valid" if not errors else "invalid", draft if not errors else None, errors)


def _semantic_errors(draft: ReviewerDraft, packet: AnnotationPacketV2) -> list[str]:
    errors: list[str] = []
    aspect_count = len(draft.required_aspects)
    span_count = len(draft.required_spans)
    valid_aspects = set(range(aspect_count))
    valid_spans = set(range(span_count))
    supported = set(draft.supported_aspect_indices)
    missing = set(draft.missing_aspect_indices)

    for label, indices in (
        ("supported_aspect", supported),
        ("missing_aspect", missing),
    ):
        for index in sorted(indices - valid_aspects):
            errors.append(f"out_of_range_{label}_index:{index}")

    if supported & missing:
        errors.append("supported_missing_overlap")
    if supported | missing != valid_aspects:
        errors.append("supported_missing_not_partition")

    packet_segment_ids = {segment.segment_id for segment in packet.full_raw_transcript}
    for span_index, span in enumerate(draft.required_spans):
        if len(span.segment_ids) != len(set(span.segment_ids)):
            errors.append(f"duplicate_segment_id:required_spans.{span_index}")
        unknown = sorted(set(span.segment_ids) - packet_segment_ids)
        for segment_id in unknown:
            errors.append(f"unknown_segment_id:required_spans.{span_index}:{segment_id}")
        for aspect_index in sorted(set(span.supported_aspect_indices) - valid_aspects):
            errors.append(f"out_of_range_span_aspect_index:{span_index}:{aspect_index}")
        if not set(span.supported_aspect_indices) <= supported:
            errors.append(f"span_maps_to_unsupported_aspect:{span_index}")

    for span_index, span in enumerate(draft.optional_context_spans):
        if len(span.segment_ids) != len(set(span.segment_ids)):
            errors.append(f"duplicate_segment_id:optional_context_spans.{span_index}")
        unknown = sorted(set(span.segment_ids) - packet_segment_ids)
        for segment_id in unknown:
            errors.append(f"unknown_segment_id:optional_context_spans.{span_index}:{segment_id}")

    for group_index, group in enumerate(draft.evidence_groups):
        for aspect_index in sorted(set(group.required_aspect_indices) - valid_aspects):
            errors.append(f"out_of_range_group_aspect_index:{group_index}:{aspect_index}")
        for span_index in sorted(set(group.required_span_indices) - valid_spans):
            errors.append(f"out_of_range_group_span_index:{group_index}:{span_index}")
        if not group.required_span_indices:
            errors.append(f"group_missing_required_span:{group_index}")
        if not set(group.required_aspect_indices) <= supported:
            errors.append(f"group_maps_to_unsupported_aspect:{group_index}")
        if set(group.required_span_indices) <= valid_spans:
            mapped = {
                aspect_index
                for span_index in group.required_span_indices
                for aspect_index in draft.required_spans[span_index].supported_aspect_indices
            }
            if not set(group.required_aspect_indices) <= mapped:
                errors.append(f"group_aspect_missing_required_span_support:{group_index}")

    if draft.status == "sufficient" and (
        supported != valid_aspects or missing or not draft.evidence_groups
    ):
        errors.append("illegal_sufficient_state")
    if draft.status == "partial" and (
        not supported or not missing or not draft.evidence_groups
    ):
        errors.append("illegal_partial_state")
    if draft.status in {"insufficient", "unverifiable"} and supported:
        errors.append(f"illegal_{draft.status}_state")

    return errors
