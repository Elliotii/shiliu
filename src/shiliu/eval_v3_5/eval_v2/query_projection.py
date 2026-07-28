from __future__ import annotations

from typing import Literal

from pydantic import Field

from .contracts import AnnotationPacketV2


QUERY_PROJECTION_POLICY_VERSION = "v3.5-query-projection-v1"

ProjectionStatus = Literal["annotatable", "not_annotatable"]


class QueryProjectedAnnotationPacketV2(AnnotationPacketV2):
    """Stage 2R packet extension; the frozen canonical review contract is unchanged."""

    original_query: str = Field(min_length=1)
    evaluation_view: Literal[
        "single_video_topic_evidence", "single_video_claim_evidence"
    ]
    evidence_question: str = Field(min_length=1)
    projection_policy_version: Literal["v3.5-query-projection-v1"] = (
        QUERY_PROJECTION_POLICY_VERSION
    )


def validate_projection(
    *, original_query: str, evaluation_view: str, evidence_question: str
) -> ProjectionStatus:
    """Reject an absent/ambiguous projection before any reviewer is called."""
    if not original_query.strip() or not evidence_question.strip():
        return "not_annotatable"
    if evaluation_view not in {
        "single_video_topic_evidence",
        "single_video_claim_evidence",
    }:
        return "not_annotatable"
    return "annotatable"
