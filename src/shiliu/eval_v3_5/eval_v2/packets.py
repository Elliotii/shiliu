from __future__ import annotations

from typing import Iterable

from .contracts import AnnotationPacketV2, TranscriptSegment
from .hashing import stable_sha256


def packet_input_payload(*, case_id: str, query: str, query_language: str,
                         transcript: Iterable[TranscriptSegment], source_metadata: dict[str, object]) -> dict[str, object]:
    return {
        "packet_version": "v3.5-annotation-packet-v2",
        "case_id": case_id,
        "query": query,
        "query_language": query_language,
        "full_raw_transcript": [x.model_dump(mode="json") for x in transcript],
        "source_metadata": source_metadata,
        "segment_schema": "v3.5-raw-segment-review-v2",
        "annotation_protocol_version": "v3.5-annotation-protocol-v2",
        "review_output_schema_version": "v3.5-annotation-review-v2",
    }


def build_packet(*, case_id: str, query: str, query_language: str,
                 transcript: Iterable[TranscriptSegment], source_metadata: dict[str, object]) -> AnnotationPacketV2:
    payload = packet_input_payload(case_id=case_id, query=query, query_language=query_language,
                                   transcript=tuple(transcript), source_metadata=source_metadata)
    return AnnotationPacketV2.model_validate({**payload, "case_input_sha256": stable_sha256(payload)})


def verify_packet_hash(packet: AnnotationPacketV2) -> bool:
    payload = packet.model_dump(mode="json")
    claimed = payload.pop("case_input_sha256")
    return stable_sha256(payload) == claimed
