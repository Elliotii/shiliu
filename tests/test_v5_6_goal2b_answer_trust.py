from __future__ import annotations

from fastapi.testclient import TestClient

from shiliu.ask.answer import BOUNDED_SYNTHESIS_POLICY, _answer_messages, _repair_messages
from shiliu.ask.context import TranscriptContextBuilder
from shiliu.ask.contracts import (
    AnswerBlock,
    AnswerDraftBlock,
    EvidenceSegment,
    TranscriptEvidenceSpan,
)
from shiliu.ask.finalize import _merge_explicit_answer_gaps
from shiliu.ask.trust import apply_answer_trust
from shiliu.ask.validation import ValidationIssue
from shiliu.web import create_web_app
from test_v4_fast_ask_api import _Provider, _application


def _span(name: str = "1") -> TranscriptEvidenceSpan:
    segment = EvidenceSegment(
        segment_id=f"segment-{name}",
        original_ordinal=0,
        run_local_ordinal=0,
        start_time=0,
        end_time=2,
        source_text=f"第{name}条当前 Raw Evidence。",
    )
    return TranscriptEvidenceSpan(
        citation_id=f"citation-{name}",
        video_id=int(name),
        bvid=f"BV{name}",
        title=f"title-{name}",
        source_type="human",
        source_language="zh",
        source_artifact_id=f"artifact-{name}",
        source_version=f"version-{name}",
        source_version_authority="raw_subtitle",
        timeline_run_id=f"timeline-{name}",
        segment_ids=(segment.segment_id,),
        segment_ordinals=(0,),
        start_time=0,
        end_time=2,
        quote_text=segment.source_text,
        jump_url="https://example.test?t=0",
        parent_chunk_ids=(f"chunk-{name}",),
        retrieval_provenance=(),
        segments=(segment,),
    )


def _trust(blocks, *, spans=None, citations=None, validate_current=lambda _span: None):
    resolved_spans = tuple(spans or (_span(),))
    resolved_citations = tuple(
        citations
        if citations is not None
        else (value.as_citation() for value in resolved_spans)
    )
    return apply_answer_trust(
        run_id="run-trust",
        answer_blocks=blocks,
        citations=resolved_citations,
        spans=resolved_spans,
        status="complete",
        limitations=[],
        termination_reason="answer_ready",
        validate_current=validate_current,
    )


def test_initial_and_repair_prompts_share_citation_integrity_boundary() -> None:
    context = TranscriptContextBuilder().build(
        query="问题", normalized_intent="问题", spans=(_span(),)
    )
    prompts = (
        _answer_messages(query="问题", context=context)[0]["content"],
        _repair_messages(
            query="问题",
            context=context,
            issues=(ValidationIssue("citation_not_allowed", "$", "invalid"),),
        )[0]["content"],
    )
    for prompt in prompts:
        assert "Faithful paraphrase" in prompt
        assert "citation_allowlist" in prompt
        assert "theme-level abstraction" in prompt
        assert "Exact-excerpt compatibility policy" not in prompt
        assert "Verifier" not in prompt


def test_non_verbatim_multi_citation_is_kept_and_stably_deduplicated() -> None:
    first, second = _span("1"), _span("2")
    result = _trust(
        [
            AnswerDraftBlock(
                text="这是对两条证据的忠实归纳，并非任一原文子串。",
                citation_ids=[first.citation_id, second.citation_id, first.citation_id],
            )
        ],
        spans=(first, second),
    )
    assert result.status == "complete"
    assert result.answer_blocks == (
        AnswerBlock(
            text="这是对两条证据的忠实归纳，并非任一原文子串。",
            citation_ids=[first.citation_id, second.citation_id],
        ),
    )
    assert tuple(value.citation_id for value in result.citations) == (
        first.citation_id,
        second.citation_id,
    )
    disposition = result.summary.dispositions[0]
    assert disposition.support_class == "unobserved"
    assert disposition.accepted_reference_ids == [first.citation_id, second.citation_id]
    assert result.summary.verifier_logical_calls == 0


def test_empty_unknown_unmapped_and_noncurrent_citations_remove_whole_blocks() -> None:
    span = _span()
    empty = _trust([AnswerDraftBlock(text="空引用", citation_ids=[])])
    unknown = _trust(
        [AnswerDraftBlock(text="越权引用", citation_ids=["citation-unknown"])]
    )
    unmapped = _trust(
        [AnswerDraftBlock(text="不可映射", citation_ids=[span.citation_id])],
        spans=(span,),
        citations=(),
    )
    noncurrent = _trust(
        [AnswerDraftBlock(text="版本失效", citation_ids=[span.citation_id])],
        validate_current=lambda _span: (_ for _ in ()).throw(RuntimeError("stale")),
    )
    assert empty.summary.reason_codes == ["citation_missing"]
    assert unknown.summary.reason_codes == ["citation_not_allowed"]
    assert unmapped.summary.reason_codes == ["citation_unmapped"]
    assert noncurrent.summary.reason_codes == ["citation_not_current"]
    assert all(
        value.status == "insufficient" and not value.answer_blocks
        for value in (empty, unknown, unmapped, noncurrent)
    )


def test_valid_block_survives_invalid_block_without_repair() -> None:
    span = _span()
    result = _trust(
        [
            AnswerDraftBlock(text="合法归纳", citation_ids=[span.citation_id]),
            AnswerDraftBlock(text="非法块", citation_ids=["citation-unknown"]),
        ]
    )
    assert result.status == "partial"
    assert result.answer_blocks == (
        AnswerBlock(text="合法归纳", citation_ids=[span.citation_id]),
    )
    assert [value.outcome for value in result.summary.dispositions] == [
        "allow",
        "remove",
    ]


def test_all_invalid_uses_existing_repair_once_and_structural_repair_is_not_repeated(
    app_paths,
) -> None:
    citation_repair_provider = _Provider(answer_modes=("invalid", "complete"))
    core, _ = _application(
        app_paths, citation_repair_provider, claim_verifier=None
    )
    client = TestClient(create_web_app(core))
    repaired = client.post("/api/ask", json={"query": "MCP"}).json()
    repaired_trace = client.get(
        f"/api/ask/traces/{repaired['run_id']}"
    ).json()["trace"]
    assert repaired["status"] == "complete"
    assert repaired_trace["repair_calls"] == 1
    assert repaired_trace["answer_provider_call_count"] == 2
    assert citation_repair_provider.answer_calls == 2

    structural_provider = _Provider(answer_modes=("schema_invalid", "invalid"))
    structural_core, _ = _application(
        app_paths, structural_provider, claim_verifier=None
    )
    structural_client = TestClient(create_web_app(structural_core))
    withheld = structural_client.post("/api/ask", json={"query": "MCP"}).json()
    withheld_trace = structural_client.get(
        f"/api/ask/traces/{withheld['run_id']}"
    ).json()["trace"]
    assert withheld["status"] == "insufficient"
    assert withheld_trace["repair_calls"] == 1
    assert withheld_trace["answer_provider_call_count"] == 2
    assert structural_provider.answer_calls == 2


def test_fast_and_deep_share_bounded_synthesis_without_verifier_calls(app_paths) -> None:
    provider = _Provider(answer_modes=("partial",))
    core, _ = _application(app_paths, provider, claim_verifier=None)
    client = TestClient(create_web_app(core))
    fast = client.post("/api/ask", json={"query": "MCP", "mode": "fast"}).json()
    deep = client.post("/api/ask", json={"query": "MCP", "mode": "deep"}).json()
    fast_trace = client.get(f"/api/ask/traces/{fast['run_id']}").json()["trace"]
    deep_trace = client.get(f"/api/ask/traces/{deep['run_id']}").json()["trace"]
    assert fast["answer_blocks"][0]["text"] == "只覆盖了部分问题"
    assert deep["answer_blocks"][0]["text"] == "只覆盖了部分问题"
    assert fast_trace["generation_policy"] == BOUNDED_SYNTHESIS_POLICY
    assert deep_trace["finalization"]["generation_policy"] == BOUNDED_SYNTHESIS_POLICY
    for body in (fast, deep):
        assert body["trust_summary"]["semantic_passes"] == 0
        assert body["trust_summary"]["verifier_logical_calls"] == 0
        assert body["trust_summary"]["verifier_http_attempts"] == 0


def test_finalizer_only_downgrades_explicit_gaps_and_confirmed_conflicts() -> None:
    internal_status, internal_limitations = _merge_explicit_answer_gaps(
        status="complete",
        limitations=[],
        decision_projection={
            "open_aspects": [],
            "conflicts": [{"status": "potential"}],
            "contributions": [{"kind": "dropped"}],
        },
    )
    assert internal_status == "complete"
    assert internal_limitations == []

    explicit_status, explicit_limitations = _merge_explicit_answer_gaps(
        status="complete",
        limitations=["模型明确限制"],
        decision_projection={
            "open_aspects": ["价格"],
            "conflicts": [{"status": "confirmed"}],
            "contributions": [],
        },
    )
    assert explicit_status == "partial"
    assert explicit_limitations == [
        "模型明确限制",
        "仍有 1 个证据方面未覆盖",
        "检测到 1 个待处理冲突",
    ]
