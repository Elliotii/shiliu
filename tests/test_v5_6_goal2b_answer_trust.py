from __future__ import annotations

from fastapi.testclient import TestClient

from shiliu.ask.answer import (
    BOUNDED_SYNTHESIS_POLICY,
    EXACT_EXCERPT_COMPATIBILITY_POLICY,
    _answer_messages,
    _repair_messages,
)
from shiliu.ask.context import TranscriptContextBuilder
from shiliu.ask.contracts import AnswerBlock, EvidenceSegment, TranscriptEvidenceSpan
from shiliu.ask.trust import (
    ClaimVerifierBatch,
    ClaimVerifierUnknown,
    ClaimVerifierVerdict,
    apply_answer_trust,
)
from shiliu.ask.validation import ValidationIssue
from shiliu.evidence.claim_support import SemanticSupportVerdict
from shiliu.web import create_web_app
from test_v4_fast_ask_api import _Provider, _application


def _span() -> TranscriptEvidenceSpan:
    segment = EvidenceSegment(
        segment_id="segment-1",
        original_ordinal=0,
        run_local_ordinal=0,
        start_time=0,
        end_time=2,
        source_text="当前 Raw Evidence 精确摘录。",
    )
    return TranscriptEvidenceSpan(
        citation_id="citation-1",
        video_id=1,
        bvid="BV1",
        title="title",
        source_type="human",
        source_language="zh",
        source_artifact_id="artifact-1",
        source_version="version-1",
        source_version_authority="raw_subtitle",
        timeline_run_id="timeline-1",
        segment_ids=(segment.segment_id,),
        segment_ordinals=(0,),
        start_time=0,
        end_time=2,
        quote_text=segment.source_text,
        jump_url="https://example.test?t=0",
        parent_chunk_ids=("chunk-1",),
        retrieval_provenance=(),
        segments=(segment,),
    )


class _FakeVerifier:
    enabled = True

    def __init__(self) -> None:
        self.calls = 0

    def verify(self, claims):
        self.calls += 1
        return ClaimVerifierBatch(
            verdicts={
                value.claim_id: ClaimVerifierVerdict(
                    verdict=SemanticSupportVerdict.SUPPORTED,
                    authority_reference_ids=value.authority_reference_ids,
                )
                for value in claims
            },
            verifier_reference="deterministic-test-fake",
        )


class _UnknownVerifier:
    enabled = True
    calls = 0

    def verify(self, claims):
        self.calls += 1
        raise ClaimVerifierUnknown("unknown test receipt")


class _RecordingProvider(_Provider):
    def __init__(self, *, answer_modes=("complete",)) -> None:
        super().__init__(answer_modes=answer_modes)
        self.answer_prompts: list[str] = []

    def generate_structured(
        self,
        *,
        role,
        messages,
        response_schema,
        max_tokens,
        timeout_seconds=None,
    ):
        if role == "grounded_answer":
            self.answer_prompts.append(messages[0]["content"])
        return super().generate_structured(
            role=role,
            messages=messages,
            response_schema=response_schema,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )


def _assert_exact_excerpt_policy(prompt: str) -> None:
    assert "Exact-excerpt compatibility policy" in prompt
    assert "exactly one citation_id in citation_ids" in prompt
    assert "contiguous verbatim excerpt" in prompt
    assert "current transcript_evidence.quote_text" in prompt
    assert "normalization already accepted by the deterministic trust gate" in prompt
    assert "Do not paraphrase, synthesize across citations" in prompt
    assert "merge unrelated spans" in prompt
    assert "uncited connective factual claims" in prompt
    assert "return status partial" in prompt
    assert "status insufficient with empty answer_blocks" in prompt


def test_disabled_initial_and_repair_prompts_share_exact_excerpt_policy() -> None:
    context = TranscriptContextBuilder().build(
        query="问题",
        normalized_intent="问题",
        spans=(_span(),),
    )
    initial = _answer_messages(
        query="问题",
        context=context,
        generation_policy=EXACT_EXCERPT_COMPATIBILITY_POLICY,
    )[0]["content"]
    repair = _repair_messages(
        query="问题",
        context=context,
        issues=(ValidationIssue("bad", "$", "invalid"),),
        generation_policy=EXACT_EXCERPT_COMPATIBILITY_POLICY,
    )[0]["content"]

    _assert_exact_excerpt_policy(initial)
    _assert_exact_excerpt_policy(repair)


def test_exact_excerpt_is_the_only_provider_free_allow_class() -> None:
    span = _span()
    exact = apply_answer_trust(
        run_id="run-exact",
        answer_blocks=[AnswerBlock(text=span.quote_text, citation_ids=[span.citation_id])],
        citations=[span.as_citation()],
        spans=[span],
        status="complete",
        limitations=[],
        termination_reason="answer_ready",
        validate_current=lambda _span: None,
    )
    assert exact.status == "complete"
    assert exact.summary.verifier_state == "not_needed"
    assert exact.summary.dispositions[0].support_class == "exact_current_evidence_excerpt_v1"

    unsupported = apply_answer_trust(
        run_id="run-disabled",
        answer_blocks=[AnswerBlock(text="这是一条改写。", citation_ids=[span.citation_id])],
        citations=[span.as_citation()],
        spans=[span],
        status="complete",
        limitations=[],
        termination_reason="answer_ready",
        validate_current=lambda _span: None,
    )
    assert unsupported.status == "insufficient"
    assert unsupported.execution_outcome == "claim_support_insufficient"
    assert unsupported.summary.verifier_state == "disabled"
    assert unsupported.answer_blocks == unsupported.citations == ()


def test_one_fake_semantic_pass_is_bounded_and_unknown_is_not_replayed() -> None:
    span = _span()
    verifier = _FakeVerifier()
    supported = apply_answer_trust(
        run_id="run-fake",
        answer_blocks=[AnswerBlock(text="受支持的改写。", citation_ids=[span.citation_id])],
        citations=[span.as_citation()],
        spans=[span],
        status="complete",
        limitations=[],
        termination_reason="answer_ready",
        validate_current=lambda _span: None,
        verifier=verifier,
    )
    assert verifier.calls == 1
    assert supported.status == "complete"
    assert supported.summary.semantic_passes == 1
    assert supported.summary.verifier_logical_calls == 1
    assert supported.summary.semantic_answer_repairs == 0

    unknown = _UnknownVerifier()
    withheld = apply_answer_trust(
        run_id="run-unknown",
        answer_blocks=[AnswerBlock(text="未知回执改写。", citation_ids=[span.citation_id])],
        citations=[span.as_citation()],
        spans=[span],
        status="complete",
        limitations=[],
        termination_reason="answer_ready",
        validate_current=lambda _span: None,
        verifier=unknown,
    )
    assert unknown.calls == 1
    assert withheld.execution_outcome == "claim_verifier_unknown"
    assert withheld.summary.semantic_passes == 0


def test_product_default_withholds_nonextractive_block_before_body(app_paths) -> None:
    core, _ = _application(
        app_paths, _Provider(answer_modes=("partial",)), claim_verifier=None
    )
    body = TestClient(create_web_app(core)).post("/api/ask", json={"query": "MCP"}).json()
    assert body["status"] == "insufficient"
    assert body["execution_outcome"] == "claim_support_insufficient"
    assert body["answer_blocks"] == []
    assert body["trust_summary"]["semantic_passes"] == 0
    assert body["trust_summary"]["verifier_logical_calls"] == 0
    assert body["trust_summary"]["verifier_http_attempts"] == 0
    events = core.ask_service.run_store.get_events(body["run_id"])
    assert [value["event_type"] for value in events].index("minimum_trust_failed") < [
        value["event_type"] for value in events
    ].index("soft_review_skipped")


def test_disabled_policy_fixture_yields_visible_exact_answer_without_verifier(
    app_paths,
) -> None:
    provider = _RecordingProvider(answer_modes=("invalid", "complete"))
    core, _ = _application(app_paths, provider, claim_verifier=None)
    client = TestClient(create_web_app(core))

    body = client.post("/api/ask", json={"query": "MCP"}).json()
    trace = client.get(f"/api/ask/traces/{body['run_id']}").json()["trace"]

    assert body["status"] == "complete"
    assert body["execution_outcome"] == "answer_generated"
    assert len(body["answer_blocks"]) == len(body["citations"]) == 1
    assert body["answer_blocks"][0]["text"] in body["citations"][0]["quote_text"]
    assert trace["generation_policy"] == EXACT_EXCERPT_COMPATIBILITY_POLICY
    assert trace["answer_calls"] == 1
    assert trace["repair_calls"] == 1
    assert trace["answer_provider_call_count"] == 2
    assert body["trust_summary"]["overall_outcome"] == "allow"
    assert body["trust_summary"]["semantic_passes"] == 0
    assert body["trust_summary"]["verifier_logical_calls"] == 0
    assert body["trust_summary"]["verifier_http_attempts"] == 0
    assert len(provider.answer_prompts) == 2
    for prompt in provider.answer_prompts:
        _assert_exact_excerpt_policy(prompt)


def test_enabled_verifier_keeps_bounded_synthesis_policy(app_paths) -> None:
    verifier = _FakeVerifier()
    provider = _RecordingProvider(answer_modes=("partial",))
    core, _ = _application(app_paths, provider, claim_verifier=verifier)
    client = TestClient(create_web_app(core))

    body = client.post("/api/ask", json={"query": "MCP"}).json()
    trace = client.get(f"/api/ask/traces/{body['run_id']}").json()["trace"]

    assert body["status"] == "partial"
    assert body["answer_blocks"][0]["text"] == "只覆盖了部分问题"
    assert trace["generation_policy"] == BOUNDED_SYNTHESIS_POLICY
    assert "Exact-excerpt compatibility policy" not in provider.answer_prompts[0]
    assert verifier.calls == 1
    assert body["trust_summary"]["semantic_passes"] == 1
    assert body["trust_summary"]["verifier_logical_calls"] == 1
    assert body["trust_summary"]["verifier_http_attempts"] == 1


def test_fast_and_deep_share_disabled_generation_policy(app_paths) -> None:
    provider = _RecordingProvider()
    core, _ = _application(app_paths, provider, claim_verifier=None)
    client = TestClient(create_web_app(core))

    fast = client.post("/api/ask", json={"query": "MCP", "mode": "fast"}).json()
    deep = client.post("/api/ask", json={"query": "MCP", "mode": "deep"}).json()
    fast_trace = client.get(f"/api/ask/traces/{fast['run_id']}").json()["trace"]
    deep_trace = client.get(f"/api/ask/traces/{deep['run_id']}").json()["trace"]

    assert fast_trace["generation_policy"] == EXACT_EXCERPT_COMPATIBILITY_POLICY
    assert (
        deep_trace["finalization"]["generation_policy"]
        == EXACT_EXCERPT_COMPATIBILITY_POLICY
    )
    assert len(provider.answer_prompts) == 2
    for prompt in provider.answer_prompts:
        _assert_exact_excerpt_policy(prompt)
