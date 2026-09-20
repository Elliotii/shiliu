from __future__ import annotations

import hashlib
from dataclasses import asdict

from .canary import TransportBudget, invoke_with_transport_budget, payload_fingerprint
from .contracts import TranscriptSegment
from .hashing import stable_sha256
from .providers import ReviewerPayload, reviewer_draft_prompt
from .query_projection import QueryProjectedAnnotationPacketV2
from .reviewer_registry import PRIMARY_REVIEWER
from .stage2r_b_runtime import invoke_primary


def fixed_transport_fixture_payload() -> ReviewerPayload:
    segment = TranscriptSegment(
        segment_id="transport_fixture_seg_000001",
        start_time=0.0,
        end_time=1.0,
        text="This is a non-formal transport fixture.",
        source_language="en",
        source_type="raw_subtitle",
        timeline_run_id="transport_fixture_timeline",
        source_artifact_id="transport_fixture_artifact",
        source_version="sha256:" + "0" * 64,
    )
    base = {
        "packet_version": "v3.5-annotation-packet-v2",
        "case_id": "TRANSPORT_FIXTURE_NOT_A_CASE",
        "query": "transport fixture",
        "original_query": "transport fixture",
        "evaluation_view": "single_video_topic_evidence",
        "evidence_question": "Does this fixture transcript discuss transport fixture?",
        "projection_policy_version": "v3.5-query-projection-v1",
        "query_language": "en",
        "full_raw_transcript": [segment.model_dump(mode="json")],
        "source_metadata": {
            "video_id": "TRANSPORT_FIXTURE",
            "full_transcript": True,
            "non_formal_fixture": True,
        },
        "segment_schema": "v3.5-raw-segment-review-v2",
        "annotation_protocol_version": "v3.5-annotation-protocol-v2",
        "review_output_schema_version": "v3.5-annotation-review-v2",
    }
    packet = QueryProjectedAnnotationPacketV2.model_validate(
        {**base, "case_input_sha256": stable_sha256(base)}
    )
    prompt = reviewer_draft_prompt(
        role="Primary",
        protocol_excerpt="Non-formal transport fixture. Apply the supplied four-state protocol.",
    )
    return ReviewerPayload.from_packet(packet, prompt)


def diagnose_openai_transport() -> dict[str, object]:
    """Run no more than three fixed, byte-identical diagnostic attempts."""
    payload = fixed_transport_fixture_payload()
    fingerprint = payload_fingerprint(payload, PRIMARY_REVIEWER)
    budget = TransportBudget()
    result = invoke_with_transport_budget(
        invoke=lambda: invoke_primary(payload),
        phase="transport_diagnosis",
        fingerprint=fingerprint,
        budget=budget,
    )
    attempts = [asdict(attempt) for attempt in budget.attempts]
    return {
        "fixture": "non_formal_fixed_transport_fixture_v1",
        "model": PRIMARY_REVIEWER.model,
        "reasoning_effort": PRIMARY_REVIEWER.reasoning_effort,
        "provider_usage": PRIMARY_REVIEWER.usage,
        "packet_byte_count": len(payload.packet_bytes),
        "payload_fingerprint": fingerprint,
        "payload_fingerprint_consistent": all(
            attempt["payload_fingerprint"] == fingerprint for attempt in attempts
        ),
        "attempt_count": len(attempts),
        "attempts": attempts,
        "eventual_model_body_returned": result is not None,
        "response_model_echo": result.response_model if result is not None else None,
        "payload_content_persisted": False,
        "base_url_persisted": False,
        "raw_error_body_persisted": False,
        "diagnostic_sha256": hashlib.sha256(fingerprint.encode("ascii")).hexdigest(),
    }
