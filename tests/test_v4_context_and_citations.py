from __future__ import annotations

from shiliu.ask.citations import stable_citation_id
from shiliu.ask.context import TranscriptContextBuilder, fuse_evidence
from shiliu.ask.contracts import EvidenceSegment, TranscriptEvidenceSpan


def _span(
    *,
    ordinals=(0, 1),
    texts=("原字幕事实一", "原字幕事实二"),
    rank=1,
    method="lexical",
    title="仅展示标题",
) -> TranscriptEvidenceSpan:
    segments = tuple(
        EvidenceSegment(
            segment_id=f"segment-{ordinal}",
            original_ordinal=ordinal,
            run_local_ordinal=ordinal,
            start_time=float(ordinal),
            end_time=float(ordinal + 1),
            source_text=text,
        )
        for ordinal, text in zip(ordinals, texts)
    )
    citation_id = stable_citation_id(
        source_artifact_id="artifact",
        source_version="version",
        timeline_run_id="timeline",
        segments=segments,
    )
    return TranscriptEvidenceSpan(
        citation_id=citation_id,
        video_id=1,
        bvid="BV1234567890",
        title=title,
        source_type="human",
        source_language="zh",
        source_artifact_id="artifact",
        source_version="version",
        source_version_authority="live_current_exact_replay",
        timeline_run_id="timeline",
        segment_ids=tuple(value.segment_id for value in segments),
        segment_ordinals=tuple(value.original_ordinal for value in segments),
        start_time=segments[0].start_time,
        end_time=segments[-1].end_time,
        quote_text="\n".join(texts),
        jump_url="https://www.bilibili.com/video/BV1234567890?t=0",
        parent_chunk_ids=("chunk",),
        retrieval_provenance=(
            {"rank": rank, "retrieval_method": method, "query": "MCP"},
        ),
        segments=segments,
    )


def test_fusion_deduplicates_identity_and_merges_query_provenance() -> None:
    lexical = _span()
    dense = _span(rank=4, method="hybrid", title="显示标题变化")
    fused = fuse_evidence((lexical, dense))
    assert len(fused) == 1
    assert fused[0].citation_id == lexical.citation_id == dense.citation_id
    assert len(fused[0].retrieval_provenance) == 2
    assert fused[0].fusion_score > 0


def test_context_contains_transcript_facts_but_not_navigation_metadata() -> None:
    span = _span(title="不应进入模型的标题与 AI Summary")
    result = TranscriptContextBuilder().build(
        query="问题",
        normalized_intent="意图",
        spans=fuse_evidence((span,)),
    )
    assert "原字幕事实一" in result.model_context
    assert span.citation_id in result.model_context
    assert "不应进入模型的标题" not in result.model_context
    assert "AI Summary" not in result.model_context


def test_context_merges_overlapping_spans_and_enforces_budgets() -> None:
    first = _span(ordinals=(0, 1), texts=("一" * 10, "二" * 10))
    second = _span(ordinals=(1, 2), texts=("二" * 10, "三" * 10), rank=2)
    merged = TranscriptContextBuilder(
        per_span_character_budget=40,
        total_character_budget=40,
        max_spans=3,
    ).build(
        query="问题",
        normalized_intent="",
        spans=fuse_evidence((first, second)),
    )
    assert len(merged.spans) == 1
    assert merged.spans[0].segment_ordinals == (0, 1, 2)
    assert merged.spans[0].quote_text.count("二" * 10) == 1

    truncated = TranscriptContextBuilder(
        per_span_character_budget=12,
        total_character_budget=12,
        max_spans=1,
    ).build(
        query="问题",
        normalized_intent="",
        spans=fuse_evidence((first, second)),
    )
    assert truncated.truncated is True
    assert len(truncated.spans) <= 1
