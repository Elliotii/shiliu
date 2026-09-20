from __future__ import annotations

from .contracts import AnnotationAgreementV2, AnnotationPacketV2, AnnotationReviewV2
from .review_validation import reconstruct_span


def build_adjudication_packet(packet: AnnotationPacketV2, primary: AnnotationReviewV2,
                              secondary: AnnotationReviewV2, agreement: AnnotationAgreementV2) -> dict[str, object]:
    spans = primary.review.required_spans + secondary.review.required_spans
    return {"packet_version": "v3.5-human-adjudication-packet-v2", "case_id": packet.case_id,
            "query": packet.query, "source_metadata": packet.source_metadata,
            "primary_review": primary.review.model_dump(mode="json"),
            "secondary_review": secondary.review.model_dump(mode="json"),
            "agreement_differences": agreement.model_dump(mode="json"),
            "relevant_raw_transcript_regions": [reconstruct_span(x, packet) for x in spans],
            "full_transcript_reference": {"case_input_sha256": packet.case_input_sha256,
                                          "first_segment_id": packet.full_raw_transcript[0].segment_id if packet.full_raw_transcript else None,
                                          "last_segment_id": packet.full_raw_transcript[-1].segment_id if packet.full_raw_transcript else None},
            "suggested_decision_template": {"adjudication_status": "pending", "adjudicator": "",
                "final_label": None, "final_required_aspects": [], "final_evidence_groups": [], "final_spans": [],
                "changes_from_primary": "", "changes_from_secondary": "", "adjudication_reason": "", "approved_at": None}}
