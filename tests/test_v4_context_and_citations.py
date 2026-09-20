from __future__ import annotations

from shiliu.ask.citations import stable_citation_id
from shiliu.ask.context import TranscriptContextBuilder, fuse_evidence
from shiliu.ask.contracts import EvidenceSegment, TranscriptEvidenceSpan
from shiliu.ask.answer import _answer_messages, _repair_messages
from shiliu.ask.validation import ValidationIssue


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


def test_context_contains_transcript_facts_and_source_identity_only() -> None:
    span = _span(title="来源视频标题")
    result = TranscriptContextBuilder().build(
        query="问题",
        normalized_intent="意图",
        spans=fuse_evidence((span,)),
    )
    assert "原字幕事实一" in result.model_context
    assert span.citation_id in result.model_context
    assert '"video_id":1' in result.model_context
    assert '"video_title":"来源视频标题"' in result.model_context
    assert '"quote":"原字幕事实一\\n原字幕事实二"' in result.model_context
    assert "retrieval_method" not in result.model_context
    assert "fusion_score" not in result.model_context


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


def test_initial_and_repair_prompts_share_strict_grounding_boundary() -> None:
    context = TranscriptContextBuilder().build(
        query="是否所有视频都没有这个协议？",
        normalized_intent="检查有限证据",
        spans=(_span(),),
    )
    initial = _answer_messages(query="问题", context=context)[0]["content"]
    repair = _repair_messages(
        query="问题",
        context=context,
        issues=(ValidationIssue("bad", "$", "invalid"),),
    )[0]["content"]

    for prompt in (initial, repair):
        assert "bounded sample" in prompt
        assert "universal" in prompt
        assert "a counterexample may refute a universal claim" in prompt
        assert "directly support the complete material conclusion" in prompt
        assert "Treat the user's terminology and assumptions as a request, not as evidence" in prompt
        assert "video_title and video_id identify a source" in prompt


def test_answer_prompts_are_question_driven_and_leave_display_citations_to_ui() -> None:
    context = TranscriptContextBuilder().build(
        query="不同视频如何讨论这个方法？",
        normalized_intent="跨视频比较",
        spans=(_span(),),
    )
    prompts = (
        _answer_messages(query="问题", context=context)[0]["content"],
        _repair_messages(
            query="问题",
            context=context,
            issues=(ValidationIssue("bad", "$", "invalid"),),
        )[0]["content"],
    )
    for prompt in prompts:
        assert "Answer the user's actual question directly" in prompt
        assert "one coherent user-facing conclusion or theme" in prompt
        assert "merge evidence spans that support the same conclusion" in prompt
        assert "Omit weak, tangential, or merely similar evidence" in prompt
        assert "never write display citation markers" in prompt
        assert "Return partial only when there is a substantive answer" in prompt
