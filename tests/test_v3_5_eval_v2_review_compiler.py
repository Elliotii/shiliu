from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from shiliu.eval_v3_5.eval_v2.contracts import AnnotationPacketV2, Usage
from shiliu.eval_v3_5.eval_v2.review_compiler import (
    CompilationContext,
    ReviewCompilationError,
    compile_reviewer_draft,
)
from test_v3_5_eval_v2_reviewer_draft import valid_draft


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "research/v3_5/eval_v2/stage2r_a/fixtures/annotation_packet.synthetic.v2.json"


def packet() -> AnnotationPacketV2:
    return AnnotationPacketV2.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


def context() -> CompilationContext:
    moment = datetime(2026, 7, 23, tzinfo=timezone.utc)
    return CompilationContext(
        reviewer_provider="test",
        reviewer_model="test-model",
        reviewer_role="primary",
        prompt_version="draft-v1",
        started_at=moment,
        completed_at=moment,
        latency_ms=0,
        usage=Usage(input_tokens=1, output_tokens=1),
    )


def test_compiler_generates_local_ids_groups_and_packet_identity() -> None:
    result = compile_reviewer_draft(raw_draft=valid_draft(), packet=packet(), context=context())
    body = result.annotation.review
    assert [aspect.aspect_id for aspect in body.required_aspects] == ["A1", "A2"]
    assert [span.span_id for span in body.required_spans] == ["S1", "S2"]
    assert [span.span_id for span in body.optional_context_spans] == ["S3"]
    assert body.acceptable_evidence_groups[0].group_id == "G1"
    assert body.acceptable_evidence_groups[0].required_span_ids == ("S1", "S2")
    assert body.required_spans[0].source_artifact_id == "artifact_fixture"
    assert body.required_spans[0].start_time == 0.0
    assert body.transcript_first_segment_id == "seg_1"
    assert body.transcript_last_segment_id == "seg_3"


def test_repeated_compilation_is_byte_and_hash_identical() -> None:
    first = compile_reviewer_draft(raw_draft=valid_draft(), packet=packet(), context=context())
    second = compile_reviewer_draft(raw_draft=valid_draft(), packet=packet(), context=context())
    assert first.canonical_bytes == second.canonical_bytes
    assert first.sha256 == second.sha256


@pytest.mark.parametrize("field,value,error", [
    ("timeline_run_id", "run_2", "cross_timeline_run"),
    ("source_version", "version_other", "source_or_version_mismatch"),
])
def test_compiler_rejects_cross_run_or_source_version_mismatch(
    field: str, value: str, error: str
) -> None:
    original = packet()
    segments = list(original.full_raw_transcript)
    segments[1] = segments[1].model_copy(update={field: value})
    changed = original.model_copy(update={"full_raw_transcript": tuple(segments)})
    raw = valid_draft()
    raw["required_spans"] = [
        {"segment_ids": ["seg_1", "seg_2"], "supported_aspect_indices": [0, 1]}
    ]
    raw["evidence_groups"] = [
        {"required_aspect_indices": [0, 1], "required_span_indices": [0]}
    ]
    with pytest.raises(ReviewCompilationError) as exc:
        compile_reviewer_draft(raw_draft=raw, packet=changed, context=context())
    assert error in exc.value.errors
