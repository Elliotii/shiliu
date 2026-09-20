from __future__ import annotations

from hashlib import sha256
from typing import Sequence

from shiliu.ask.contracts import CITATION_IDENTITY_VERSION, EvidenceSegment
from shiliu.evidence.contracts import EvidenceContractError, RawEvidenceSegment
from shiliu.evidence.source import canonical_json


def stable_citation_id(
    *,
    source_artifact_id: str,
    source_version: str,
    timeline_run_id: str,
    segments: Sequence[RawEvidenceSegment | EvidenceSegment],
    require_contiguous: bool = True,
) -> str:
    if not segments:
        raise EvidenceContractError(
            "citation must contain at least one segment",
            code="citation_segment_invalid",
        )
    segment_ids = [segment.segment_id for segment in segments]
    ordinals = [_ordinal(segment) for segment in segments]
    local_ordinals = [segment.run_local_ordinal for segment in segments]
    if len(set(segment_ids)) != len(segment_ids):
        raise EvidenceContractError(
            "citation contains duplicate segments",
            code="citation_segment_duplicate",
        )
    if any(left >= right for left, right in zip(ordinals, ordinals[1:])):
        raise EvidenceContractError(
            "citation segments are not in authoritative ordinal order",
            code="citation_segment_order_invalid",
        )
    if require_contiguous and any(
        right != left + 1
        for left, right in zip(local_ordinals, local_ordinals[1:])
    ):
        raise EvidenceContractError(
            "citation segments are not contiguous in one timeline run",
            code="citation_segment_continuity_invalid",
        )
    for segment in segments:
        if isinstance(segment, RawEvidenceSegment):
            if (
                segment.source_artifact_id != source_artifact_id
                or segment.source_version != source_version
                or segment.timeline_run_id != timeline_run_id
            ):
                raise EvidenceContractError(
                    "citation segments do not share one source/version/timeline",
                    code="citation_lineage_invalid",
                )
    payload = {
        "citation_identity_version": CITATION_IDENTITY_VERSION,
        "source_artifact_id": source_artifact_id,
        "source_version": source_version,
        "timeline_run_id": timeline_run_id,
        "ordered_segment_ids": segment_ids,
    }
    return "citation_v1_" + sha256(canonical_json(payload)).hexdigest()


def _ordinal(segment: RawEvidenceSegment | EvidenceSegment) -> int:
    if isinstance(segment, RawEvidenceSegment):
        return segment.original_ordinal
    return segment.original_ordinal
