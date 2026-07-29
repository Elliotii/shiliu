from __future__ import annotations

import importlib.util
from io import StringIO
import json
from pathlib import Path
import sys

import pytest

from shiliu.ask.answer import GroundedAnswerService
from shiliu.ask.context import TranscriptContextBuilder
from shiliu.ask.contracts import (
    AnswerBlock,
    EvidenceSegment,
    GroundedAnswerDraft,
    TranscriptEvidenceSpan,
)
from shiliu.ask.deep.budget import DeepSearchBudget
from shiliu.ask.deep.contracts import DeepSearchState
from shiliu.ask.deep.decision import _decision_messages
from shiliu.ask.deep.service import DeepSearchService
from shiliu.ask.query_analysis import bounded_distinct_queries
from shiliu.llm import OpenAICompatibleProvider
from shiliu.domain import PipelineError


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_v4_1_h0_investigation.py"
)
SPEC = importlib.util.spec_from_file_location("v4_1_h0", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
h0 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = h0
SPEC.loader.exec_module(h0)


def _span(
    *,
    citation_id: str = "citation_v1_" + "a" * 64,
    video_id: int = 1,
    ordinal: int = 0,
    text: str = "原字幕事实",
    query_index: int = 0,
) -> TranscriptEvidenceSpan:
    segment = EvidenceSegment(
        segment_id=f"segment-{video_id}-{ordinal}",
        original_ordinal=ordinal,
        run_local_ordinal=ordinal,
        start_time=float(ordinal),
        end_time=float(ordinal + 1),
        source_text=text,
    )
    return TranscriptEvidenceSpan(
        citation_id=citation_id,
        video_id=video_id,
        bvid="BV1234567890",
        title="display only",
        source_type="human",
        source_language="zh",
        source_artifact_id=f"artifact-{video_id}",
        source_version=f"version-{video_id}",
        source_version_authority="live_current_exact_replay",
        timeline_run_id=f"timeline-{video_id}",
        segment_ids=(segment.segment_id,),
        segment_ordinals=(ordinal,),
        start_time=segment.start_time,
        end_time=segment.end_time,
        quote_text=text,
        jump_url="https://www.bilibili.com/video/BV1234567890?t=0",
        parent_chunk_ids=(f"chunk-{video_id}-{ordinal}",),
        retrieval_provenance=(
            {
                "rank": 1,
                "query": f"query-{query_index}",
                "query_index": query_index,
                "retrieval_method": "lexical",
            },
        ),
        segments=(segment,),
    )


def _state(span: TranscriptEvidenceSpan | None = None) -> DeepSearchState:
    evidence = [span] if span is not None else []
    return {
        "run_id": "run",
        "query": "问题",
        "filters": h0.AskRequest(query="问题").filters,
        "open_questions": ["问题"],
        "resolved_questions": [],
        "evidence_spans": evidence,
        "navigation_documents": [],
        "visited_video_ids": [1] if span is not None else [],
        "visited_segment_ids": list(span.segment_ids) if span is not None else [],
        "previous_queries": [],
        "repeated_action_keys": [],
        "decision_rounds": 0,
        "tool_calls": 0,
        "consecutive_no_new_evidence": 0,
        "navigation_result_count": 0,
        "started_at": 1000,
        "search_deadline": 1150,
        "total_deadline": 1360,
        "last_action": None,
        "last_observation_summary": "",
        "pending_observation": None,
        "errors": [],
        "stale_reasons": [],
        "events": [],
        "usage": [],
        "termination_reason": None,
    }


def _fixed_request(
    *,
    case_id: str = "case",
    query: str = "问题",
    evidence_text: str = "原字幕事实",
) -> object:
    span = _span(text=evidence_text)
    context = TranscriptContextBuilder().build(
        query=query, normalized_intent=query, spans=(span,)
    )
    return h0.FixedRequest(
        case_id=case_id,
        query=query,
        context=context,
        messages=h0._answer_messages(query=query, context=context),
        request_hash=f"request-hash-{case_id}",
        message_chars=100,
        context_chars=len(context.model_context),
        citation_allowlist_count=1,
        source_version_hashes=("version-hash",),
    )


def _checkpoint_trial(
    fixed,
    configuration,
    sequence: int,
    trial_index: int,
    *,
    answer_text: str = "私有 Provider 回答正文",
) -> object:
    draft = _draft(answer_text)
    return h0.TrialRecord(
        trial_id=f"{fixed.case_id}:{configuration.name}:{trial_index}",
        request=fixed,
        configuration=configuration,
        measurement={
            "request_id": fixed.case_id,
            "request_hash": fixed.request_hash,
            "sequence_index": sequence,
            "configuration_trial_index": trial_index,
            "latency_ms": sequence,
            "repair_required": False,
            "retry_count": 0,
            "provider_call_count": 1,
            "validation_error_codes": [],
            "provider_error_code": None,
        },
        draft=draft,
        citation_ids=(_span().citation_id,),
    )


class _Materializer:
    def validate_current(self, span):
        return None


def _passing_reviewer(material):
    return h0.QualityScores(
        supportedness="pass",
        usefulness="pass",
        coverage="pass",
        status_honesty="pass",
        reason_summary="有界质量理由",
    )


def _draft(text: str = "回答摘要") -> GroundedAnswerDraft:
    return GroundedAnswerDraft(
        status="partial",
        answer_blocks=[
            AnswerBlock(
                text=text,
                citation_ids=[_span().citation_id],
            )
        ],
        limitations=["只覆盖当前证据"],
    )


def _trial(
    fixed,
    *,
    index: int,
    latency: int,
    draft: GroundedAnswerDraft | None,
    provider_error_code: str | None = None,
    repair_required: bool = False,
) -> object:
    return h0.TrialRecord(
        trial_id=f"case:baseline:{index}",
        request=fixed,
        configuration=h0.BASELINE,
        measurement={
            "request_id": "case",
            "latency_ms": latency,
            "repair_required": repair_required,
            "retry_count": 0,
            "validation_error_codes": [],
            "provider_error_code": provider_error_code,
        },
        draft=draft,
        citation_ids=(
            (_span().citation_id,) if draft is not None else ()
        ),
    )


def test_trial_order_rotates_and_each_variant_has_three_trials() -> None:
    schedule = h0.trial_schedule()
    assert schedule == [
        "baseline",
        "thinking_off",
        "thinking_off",
        "baseline",
        "baseline",
        "thinking_off",
    ]
    assert schedule.count("baseline") == 3
    assert schedule.count("thinking_off") == 3


def test_fixed_request_hash_is_canonical_and_stable_across_trials() -> None:
    body = {
        "role": "grounded_answer",
        "messages": [{"role": "user", "content": "bounded"}],
        "max_tokens": 4096,
    }
    hashes = [h0.stable_hash(body) for _ in range(3)]
    assert len(set(hashes)) == 1
    assert h0.stable_hash({"b": 2, "a": 1}) == h0.stable_hash(
        {"a": 1, "b": 2}
    )


def test_provider_variant_bodies_differ_only_in_approved_fields() -> None:
    messages = [
        {"role": "system", "content": "schema"},
        {"role": "user", "content": "bounded"},
    ]
    baseline = h0.capture_variant_body(
        model="model", messages=messages, variant=h0.BASELINE
    )
    thinking_off = h0.capture_variant_body(
        model="model", messages=messages, variant=h0.THINKING_OFF
    )
    variant_fields = {"thinking", "reasoning_effort", "temperature"}
    strip = lambda value: {
        key: item for key, item in value.items() if key not in variant_fields
    }
    assert strip(baseline) == strip(thinking_off)
    assert baseline["thinking"] == {"type": "enabled"}
    assert baseline["reasoning_effort"] == "high"
    assert "temperature" not in baseline
    assert thinking_off["thinking"] == {"type": "disabled"}
    assert thinking_off["temperature"] == 0
    assert "reasoning_effort" not in thinking_off


def test_reduced_reasoning_is_unavailable_in_current_provider_contract() -> None:
    with pytest.raises(Exception) as error:
        OpenAICompatibleProvider(
            base_url="https://example.invalid",
            api_key="placeholder",
            model="model",
            thinking_enabled=True,
            reasoning_effort="medium",
        )
    assert getattr(error.value, "code", None) == "bad_provider_config"


def test_nested_usage_extraction_preserves_missing_values() -> None:
    metrics = h0.extract_usage_metrics(
        [
            {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "prompt_tokens_details": {"cached_tokens": 30},
                "completion_tokens_details": {"reasoning_tokens": 7},
                "latency_ms": 10.5,
            },
            {
                "prompt_tokens": 50,
                "completion_tokens": 5,
                "prompt_cache_hit_tokens": 10,
                "prompt_cache_miss_tokens": 40,
                "completion_tokens_details": {"reasoning_tokens": 2},
                "latency_ms": 4,
            },
        ]
    )
    assert metrics == {
        "prompt_tokens": 150,
        "cache_hit_tokens": 40,
        "cache_miss_tokens": 40,
        "completion_tokens": 25,
        "reasoning_tokens": 9,
        "latency_ms": 14,
    }
    assert h0.extract_usage_metrics([]) == {
        "prompt_tokens": None,
        "cache_hit_tokens": None,
        "cache_miss_tokens": None,
        "completion_tokens": None,
        "reasoning_tokens": None,
        "latency_ms": None,
    }


def test_first_pass_schema_repair_and_call_counts_are_preserved() -> None:
    class Provider:
        calls = 0

        def generate_structured(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                error = PipelineError(
                    "invalid", code="invalid_model_output", retryable=True
                )
                error.completion_metadata = {
                    "usage": {"prompt_tokens": 10, "completion_tokens": 1},
                    "latency_ms": 2,
                    "retry_count": 1,
                    "content_received": True,
                }
                raise error
            citation_id = kwargs["messages"][-1]["content"].split(
                '"citation_allowlist":["', 1
            )[1].split('"', 1)[0]
            return type(
                "Reply",
                (),
                {
                    "output": GroundedAnswerDraft(
                        status="partial",
                        answer_blocks=[
                            AnswerBlock(
                                text="原字幕事实",
                                citation_ids=[citation_id],
                            )
                        ],
                        limitations=["有界"],
                    ),
                    "usage": {"prompt_tokens": 12, "completion_tokens": 3},
                    "latency_ms": 3,
                    "finish_reason": "stop",
                    "retry_count": 0,
                },
            )()

    span = _span()
    context = TranscriptContextBuilder().build(
        query="问题", normalized_intent="问题", spans=(span,)
    )
    provider = Provider()
    result = GroundedAnswerService(
        lambda role: provider,
        type("Materializer", (), {"validate_current": lambda self, value: None})(),
    ).answer(query="问题", context=context)
    assert result.repair_used is True
    assert result.repair_calls == 1
    assert result.provider_call_count == 2
    assert result.transport_retry_count == 1
    assert result.draft is not None
    assert result.initial_provider_error_code == "invalid_model_output"
    assert [value.code for value in result.initial_validation_errors] == [
        "provider_output_invalid"
    ]


def test_provider_error_is_retained_without_resampling_or_repair() -> None:
    class Provider:
        def generate_structured(self, **kwargs):
            error = PipelineError(
                "network", code="provider_network", retryable=True
            )
            error.completion_metadata = {
                "usage": None,
                "latency_ms": 7,
                "retry_count": 1,
                "content_received": False,
            }
            raise error

    context = TranscriptContextBuilder().build(
        query="问题", normalized_intent="问题", spans=(_span(),)
    )
    result = GroundedAnswerService(
        lambda role: Provider(),
        type("Materializer", (), {"validate_current": lambda self, value: None})(),
    ).answer(query="问题", context=context)
    assert result.draft is None
    assert result.repair_used is False
    assert result.repair_calls == 0
    assert result.provider_call_count == 1
    assert result.transport_retry_count == 1
    assert result.provider_error_code == "provider_network"
    assert result.usage == ({"latency_ms": 7, "retry_count": 1},)


def test_current_decision_messages_are_audited_without_rewrite() -> None:
    state = _state(_span())
    messages = _decision_messages(state, DeepSearchBudget(), now=1001)
    previous: dict[str, str] = {}
    row = h0._breakdown_round(messages, previous)
    assert sum(
        value["chars"] for value in row["blocks"].values()
    ) == sum(len(value["content"]) for value in messages)
    assert row["blocks"]["historical_observations"] == {
        "chars": 0,
        "estimated_tokens": 0,
        "token_estimation_method": h0.ESTIMATION_METHOD,
        "repeated_from_previous_round": False,
        "content_count": 0,
        "normalized_hash": h0.stable_hash(None),
        "present_in_current_payload": False,
    }
    assert row["blocks"]["tool_contracts"]["present_in_current_payload"] is False
    assert row["bounded_field_checks"]["visited_segment_count"] == 0
    assert row["bounded_field_checks"]["evidence_segment_ids_total_count"] == 0
    assert row["bounded_field_checks"]["evidence_segment_ids_total_chars"] == 0
    assert messages == _decision_messages(state, DeepSearchBudget(), now=1001)


def test_repeated_block_hash_uses_normalized_equality() -> None:
    messages = _decision_messages(_state(), DeepSearchBudget(), now=1001)
    previous: dict[str, str] = {}
    first = h0._breakdown_round(messages, previous)
    second = h0._breakdown_round(messages, previous)
    assert first["blocks"]["static_policy"]["repeated_from_previous_round"] is False
    assert second["blocks"]["static_policy"]["repeated_from_previous_round"] is True
    assert second["blocks"]["action_schema"]["repeated_from_previous_round"] is True
    assert second["blocks"]["original_query"]["repeated_from_previous_round"] is True


def test_context_diagnostics_definitions_cover_raw_fused_selected_and_dropped(
    monkeypatch,
) -> None:
    duplicate = _span()
    second = _span(
        citation_id="citation_v1_" + "b" * 64,
        video_id=2,
        text="另一个视频事实",
        query_index=1,
    )
    raw = [duplicate, duplicate.model_copy(), second]

    monkeypatch.setattr(
        h0,
        "_materialize_case",
        lambda application, case: (raw, ["stale"], []),
    )
    audit, fixed = h0.audit_fast_case(
        object(),
        {"case_id": "direct_fact_mcp", "query": "问题"},
    )
    assert audit.raw_materialized_span_count == 3
    assert audit.candidate_span_count == 2
    assert audit.selected_span_count == 2
    assert audit.exact_citation_duplicate_count == 1
    assert audit.rewrite_duplicate_recall_count == 1
    assert audit.dropped_span_count == 0
    assert audit.builder_dropped_event_count == 0
    assert audit.builder_drop_event_overcount == 0
    assert audit.merged_candidate_span_count == 0
    assert audit.candidate_video_count == 2
    assert audit.selected_video_count == 2
    assert audit.stale_count == 1
    assert audit.dropped_chars >= 0
    assert "approximate_nonnegative" in audit.dropped_chars_precision
    assert fixed.request_hash
    assert fixed.citation_allowlist_count == 2


def test_selected_model_context_and_identity_are_not_mutated_by_audit(
    monkeypatch,
) -> None:
    spans = [_span(), _span(
        citation_id="citation_v1_" + "b" * 64,
        video_id=2,
        text="第二事实",
    )]
    monkeypatch.setattr(
        h0, "_materialize_case", lambda application, case: (spans, [], [])
    )
    expected = TranscriptContextBuilder().build(
        query="问题",
        normalized_intent="问题",
        spans=h0.fuse_evidence(spans),
    )
    audit, fixed = h0.audit_fast_case(
        object(),
        {"case_id": "direct_fact_mcp", "query": "问题"},
    )
    assert fixed.context.model_context == expected.model_context
    assert fixed.context.citation_allowlist == expected.citation_allowlist
    assert tuple(value.citation_id for value in fixed.context.spans) == tuple(
        value.citation_id for value in expected.spans
    )
    assert audit.model_context_sha256 == h0.hashlib.sha256(
        expected.model_context.encode()
    ).hexdigest()


def test_bounded_output_rejects_prompts_secrets_and_raw_responses() -> None:
    h0.assert_bounded_output(
        {
            "request_hash": "abc",
            "privacy": {"api_key_loaded": False},
        }
    )
    for value in (
        {"messages": [{"content": "private"}]},
        {"Authorization": "secret"},
        {"raw_response": "private"},
    ):
        with pytest.raises(AssertionError):
            h0.assert_bounded_output(value)


def test_live_and_end_to_end_paths_require_separate_exact_authorization() -> None:
    with pytest.raises(PermissionError):
        h0.run_live_replay("")
    with pytest.raises(ValueError):
        h0.run_live_replay(h0.LIVE_AUTHORIZATION_PHRASE)
    with pytest.raises(ValueError, match="TTY preflight"):
        h0.run_live_replay(
            h0.LIVE_AUTHORIZATION_PHRASE,
            reviewer=_passing_reviewer,
        )
    stale_proof = h0.TTYPreflightProof(
        process_id=-1,
        verified_at_utc="2026-07-29T00:00:00+00:00",
        challenge_hash="hash",
        read_write_roundtrip=True,
    )
    with pytest.raises(ValueError, match="TTY preflight"):
        h0.run_live_replay(
            h0.LIVE_AUTHORIZATION_PHRASE,
            reviewer=_passing_reviewer,
            tty_preflight=stale_proof,
        )
    with pytest.raises(PermissionError):
        h0.run_end_to_end("", ("baseline",))
    with pytest.raises(ValueError):
        h0.run_end_to_end(
            h0.E2E_AUTHORIZATION_PHRASE,
            ("baseline", "thinking_off", "baseline"),
        )


def test_campaign_fail_fast_preserves_completed_trials_and_marks_incomplete() -> None:
    fixed = _fixed_request()

    def execute(request, configuration, sequence, trial_index):
        return h0.TrialRecord(
            trial_id=f"case:{configuration.name}:{trial_index}",
            request=request,
            configuration=configuration,
            measurement={
                "latency_ms": sequence,
                "repair_required": False,
                "retry_count": 1,
                "validation_error_codes": [],
                "provider_error_code": "provider_network",
            },
            draft=None,
            citation_ids=(),
        )

    result = h0.run_campaign(
        fixed_requests=[fixed],
        execute_trial=execute,
    )
    assert len(result.trials) == 3
    assert result.expected_trial_count == 6
    assert result.stopped_early is True
    assert result.matrix_complete is False
    assert result.stop_reason == (
        "campaign_fail_fast_after_3_consecutive_provider_failures"
    )
    assert result.bounded_summary()["completed_trial_count"] == 3


def test_campaign_failure_counter_resets_after_success() -> None:
    fixed = _fixed_request()
    failures = {1, 2, 4, 5, 6}

    def execute(request, configuration, sequence, trial_index):
        failed = sequence in failures
        return h0.TrialRecord(
            trial_id=f"case:{configuration.name}:{trial_index}",
            request=request,
            configuration=configuration,
            measurement={
                "latency_ms": sequence,
                "repair_required": False,
                "retry_count": 0,
                "validation_error_codes": [],
                "provider_error_code": (
                    "provider_network" if failed else None
                ),
            },
            draft=None if failed else _draft(),
            citation_ids=() if failed else (_span().citation_id,),
        )

    result = h0.run_campaign(
        fixed_requests=[fixed],
        execute_trial=execute,
    )
    assert len(result.trials) == 6
    assert result.stopped_early is True
    assert result.stop_reason is not None


def test_checkpointed_campaign_fail_fast_reviews_completed_trials(
    tmp_path,
) -> None:
    fixed = _fixed_request()
    calls = []

    def execute(request, configuration, sequence, trial_index):
        calls.append(sequence)
        return h0.TrialRecord(
            trial_id=f"{request.case_id}:{configuration.name}:{trial_index}",
            request=request,
            configuration=configuration,
            measurement={
                "request_id": request.case_id,
                "request_hash": request.request_hash,
                "sequence_index": sequence,
                "configuration_trial_index": trial_index,
                "latency_ms": sequence,
                "repair_required": False,
                "retry_count": 1,
                "provider_call_count": 1,
                "validation_error_codes": [],
                "provider_error_code": "provider_network",
            },
            draft=None,
            citation_ids=(),
        )

    result = h0.run_checkpointed_campaign(
        fixed_requests=[fixed],
        execute_trial=execute,
        materializer=_Materializer(),
        reviewer=_passing_reviewer,
        checkpoint_path=tmp_path / "checkpoint.json",
    )
    assert calls == [1, 2, 3]
    assert result["status"] == "stopped_early"
    assert result["matrix_complete"] is False
    assert result["completed_trial_count"] == 3
    assert result["stop_reason"] == (
        "campaign_fail_fast_after_3_consecutive_provider_failures"
    )
    assert result["quality_reviews"]


def test_quality_review_uses_current_full_evidence_and_reviews_all_divergence() -> None:
    fixed = _fixed_request()
    records = (
        _trial(fixed, index=1, latency=10, draft=_draft("回答一")),
        _trial(fixed, index=2, latency=20, draft=_draft("回答二")),
        _trial(
            fixed,
            index=3,
            latency=30,
            draft=_draft("回答三"),
            repair_required=True,
        ),
    )
    campaign = h0.CampaignResult(
        trials=records,
        expected_trial_count=3,
        consecutive_failure_limit=3,
        stopped_early=False,
        stop_reason=None,
    )

    class Materializer:
        validations = 0

        def validate_current(self, span):
            self.validations += 1
            assert span.quote_text == "原字幕事实"

    materializer = Materializer()
    calls = []

    def reviewer(material):
        calls.append(material)
        assert material.current_full_evidence[0].quote_text == "原字幕事实"
        index = int(material.trial_id.rsplit(":", 1)[1])
        value = {1: "pass", 2: "partial", 3: "fail"}[index]
        reason = (
            "原字幕事实"
            if index == 1
            else f"第 {index} 次输出的有界质量摘要"
        )
        return h0.QualityScores(
            supportedness=value,
            usefulness=value,
            coverage=value,
            status_honesty=value,
            reason_summary=reason,
        )

    reviews = h0.conduct_quality_reviews(
        campaign,
        materializer=materializer,
        reviewer=reviewer,
    )
    assert len(calls) == 3
    assert materializer.validations == 3
    assert len(reviews) == 3
    by_id = {value["trial_id"]: value for value in reviews}
    assert "median_latency" in by_id["case:baseline:2"]["selection_reasons"]
    assert (
        "worst_quality_or_failure"
        in by_id["case:baseline:3"]["selection_reasons"]
    )
    assert all(
        "behavior_divergence_review_all" in value["selection_reasons"]
        for value in reviews
    )
    assert by_id["case:baseline:1"]["reason_summary"].startswith(
        "Reviewer reason withheld"
    )
    serialized = json.dumps(reviews, ensure_ascii=False)
    assert "回答一" not in serialized
    assert "原字幕事实" not in serialized
    assert all(value["review_material_hash"] for value in reviews)
    assert all(
        value["full_answer_or_evidence_persisted"] is False
        for value in reviews
    )


def test_quality_review_same_behavior_selects_median_and_risk_only() -> None:
    fixed = _fixed_request()
    same = _draft()
    records = (
        _trial(fixed, index=1, latency=10, draft=same),
        _trial(fixed, index=2, latency=20, draft=same),
        _trial(
            fixed,
            index=3,
            latency=30,
            draft=same,
            repair_required=True,
        ),
    )
    campaign = h0.CampaignResult(
        trials=records,
        expected_trial_count=3,
        consecutive_failure_limit=3,
        stopped_early=False,
        stop_reason=None,
    )

    class Materializer:
        def validate_current(self, span):
            pass

    reviewed_ids = []

    def reviewer(material):
        reviewed_ids.append(material.trial_id)
        return h0.QualityScores(
            supportedness="pass",
            usefulness="pass",
            coverage="pass",
            status_honesty="pass",
            reason_summary="行为一致且通过",
        )

    reviews = h0.conduct_quality_reviews(
        campaign,
        materializer=Materializer(),
        reviewer=reviewer,
    )
    assert reviewed_ids == ["case:baseline:2", "case:baseline:3"]
    assert len(reviews) == 2


def test_quality_review_tty_uses_separate_non_seekable_streams() -> None:
    class NonSeekableInput(StringIO):
        def seekable(self) -> bool:
            return False

        def seek(self, *args, **kwargs):
            raise OSError("not seekable")

    class NonSeekableOutput(StringIO):
        def seekable(self) -> bool:
            return False

        def seek(self, *args, **kwargs):
            raise OSError("not seekable")

    material = h0.QualityReviewMaterial(
        trial_id="case:baseline:1",
        query="问题",
        draft=_draft("私有完整回答"),
        cited_ids=(_span().citation_id,),
        current_full_evidence=(_span(),),
        material_hash="abc",
    )
    terminal_in = NonSeekableInput(
        "pass\npartial\npass\npass\n有界理由摘要\n"
    )
    terminal_out = NonSeekableOutput()
    scores = h0._quality_review_with_streams(
        material, terminal_in, terminal_out
    )
    assert scores == h0.QualityScores(
        supportedness="pass",
        usefulness="partial",
        coverage="pass",
        status_honesty="pass",
        reason_summary="有界理由摘要",
    )
    assert "私有完整回答" in terminal_out.getvalue()
    assert "原字幕事实" in terminal_out.getvalue()


def test_tty_preflight_requires_successful_read_write_challenge() -> None:
    challenge = "H0-REVIEW-READY-test"
    output = StringIO()
    proof = h0._tty_preflight_with_streams(
        StringIO(challenge + "\n"),
        output,
        challenge=challenge,
    )
    assert proof.valid_for_current_process is True
    assert proof.challenge_hash == h0.stable_hash(challenge)
    assert "No Provider call has started" in output.getvalue()
    h0._consume_tty_preflight(proof)
    assert proof.valid_for_current_process is False
    with pytest.raises(ValueError):
        h0._consume_tty_preflight(proof)
    with pytest.raises(RuntimeError):
        h0._tty_preflight_with_streams(
            StringIO("wrong\n"),
            StringIO(),
            challenge=challenge,
        )


def test_provider_return_before_trial_checkpoint_blocks_duplicate_recovery(
    tmp_path,
) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    fixed = _fixed_request(
        query="绝密问题文本",
        evidence_text="绝密字幕 Evidence",
    )
    calls = []

    def execute(request, configuration, sequence, trial_index):
        calls.append(
            f"{request.case_id}:{configuration.name}:{trial_index}"
        )
        return _checkpoint_trial(
            request,
            configuration,
            sequence,
            trial_index,
            answer_text="绝密 Provider Answer",
        )

    def crash_after_provider(event, details):
        if event == "provider_returned_before_checkpoint":
            raise RuntimeError("injected provider-post checkpoint-pre crash")

    with pytest.raises(RuntimeError):
        h0.run_checkpointed_campaign(
            fixed_requests=[fixed],
            execute_trial=execute,
            materializer=_Materializer(),
            reviewer=_passing_reviewer,
            checkpoint_path=checkpoint,
            event_hook=crash_after_provider,
        )
    assert len(calls) == 1
    persisted = checkpoint.read_text(encoding="utf-8")
    assert "绝密问题文本" not in persisted
    assert "绝密字幕 Evidence" not in persisted
    assert "绝密 Provider Answer" not in persisted
    assert "raw_response" not in persisted
    assert "api_key" not in persisted
    assert checkpoint.stat().st_mode & 0o077 == 0

    recovered = h0.run_checkpointed_campaign(
        fixed_requests=[fixed],
        execute_trial=execute,
        materializer=_Materializer(),
        reviewer=_passing_reviewer,
        checkpoint_path=checkpoint,
    )
    assert len(calls) == 1
    assert recovered["status"] == "blocked_recovery"
    assert recovered["stop_reason"] == (
        "unknown_in_flight_trial_never_replayed"
    )
    assert recovered[
        "provider_logical_invocations_upper_bound_committed"
    ] == 2
    assert recovered["completed_trial_count"] == 0


def test_crash_after_six_trials_before_review_never_replays_group(
    tmp_path,
) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    fixed = _fixed_request()
    calls = []

    def execute(request, configuration, sequence, trial_index):
        calls.append(
            f"{request.case_id}:{configuration.name}:{trial_index}"
        )
        return _checkpoint_trial(
            request, configuration, sequence, trial_index
        )

    def crash_before_review(event, details):
        if event == "group_review_pending":
            raise RuntimeError("injected review-pre crash")

    with pytest.raises(RuntimeError):
        h0.run_checkpointed_campaign(
            fixed_requests=[fixed],
            execute_trial=execute,
            materializer=_Materializer(),
            reviewer=_passing_reviewer,
            checkpoint_path=checkpoint,
            event_hook=crash_before_review,
        )
    assert len(calls) == 6
    recovered = h0.run_checkpointed_campaign(
        fixed_requests=[fixed],
        execute_trial=execute,
        materializer=_Materializer(),
        reviewer=_passing_reviewer,
        checkpoint_path=checkpoint,
    )
    assert len(calls) == 6
    assert recovered["status"] == "blocked_recovery"
    assert recovered["completed_trial_count"] == 6
    assert recovered["quality_reviews"] == []
    assert recovered["group_states"][0]["state"] == (
        "review_unrecoverable_private_drafts_not_persisted"
    )


def test_crash_during_review_preserves_scores_and_never_replays_group(
    tmp_path,
) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    fixed = _fixed_request()
    calls = []
    review_calls = 0

    def execute(request, configuration, sequence, trial_index):
        calls.append(
            f"{request.case_id}:{configuration.name}:{trial_index}"
        )
        return _checkpoint_trial(
            request, configuration, sequence, trial_index
        )

    def reviewer(material):
        nonlocal review_calls
        review_calls += 1
        if review_calls == 2:
            raise RuntimeError("injected review-mid crash")
        return _passing_reviewer(material)

    with pytest.raises(RuntimeError):
        h0.run_checkpointed_campaign(
            fixed_requests=[fixed],
            execute_trial=execute,
            materializer=_Materializer(),
            reviewer=reviewer,
            checkpoint_path=checkpoint,
        )
    assert len(calls) == 6
    recovered = h0.run_checkpointed_campaign(
        fixed_requests=[fixed],
        execute_trial=execute,
        materializer=_Materializer(),
        reviewer=_passing_reviewer,
        checkpoint_path=checkpoint,
    )
    assert len(calls) == 6
    assert recovered["status"] == "blocked_recovery"
    assert len(recovered["quality_reviews"]) == 1
    assert recovered["quality_reviews"][0]["checkpoint_phase"] == (
        "score_captured_pending_group_finalization"
    )


def test_reviewed_group_resume_skips_six_provider_calls_and_finishes_next(
    tmp_path,
) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    first = _fixed_request(case_id="case-one")
    second = _fixed_request(case_id="case-two")
    calls = []
    events = []

    def execute(request, configuration, sequence, trial_index):
        calls.append(
            f"{request.case_id}:{configuration.name}:{trial_index}"
        )
        return _checkpoint_trial(
            request, configuration, sequence, trial_index
        )

    def crash_after_first_group(event, details):
        events.append((event, details["request_id"]))
        if (
            event == "group_review_complete"
            and details["request_id"] == "case-one"
        ):
            raise RuntimeError("injected crash after reviewed group")

    with pytest.raises(RuntimeError):
        h0.run_checkpointed_campaign(
            fixed_requests=[first, second],
            execute_trial=execute,
            materializer=_Materializer(),
            reviewer=_passing_reviewer,
            checkpoint_path=checkpoint,
            event_hook=crash_after_first_group,
        )
    assert len(calls) == 6
    assert all(value.startswith("case-one:") for value in calls)
    first_review_event = next(
        index
        for index, value in enumerate(events)
        if value == ("group_review_pending", "case-one")
    )
    assert all(
        event != ("provider_wal_persisted", "case-two")
        for event in events[: first_review_event + 1]
    )

    recovered = h0.run_checkpointed_campaign(
        fixed_requests=[first, second],
        execute_trial=execute,
        materializer=_Materializer(),
        reviewer=_passing_reviewer,
        checkpoint_path=checkpoint,
    )
    assert len(calls) == 12
    assert len([value for value in calls if value.startswith("case-one:")]) == 6
    assert len([value for value in calls if value.startswith("case-two:")]) == 6
    assert len(set(calls)) == 12
    assert recovered["status"] == "complete"
    assert recovered["matrix_complete"] is True
    assert recovered["completed_trial_count"] == 12
    assert recovered["provider_logical_invocations_completed"] == 12
    assert recovered["completed_request_groups"] == [
        "case-one",
        "case-two",
    ]
    persisted = checkpoint.read_text(encoding="utf-8")
    assert "私有 Provider 回答正文" not in persisted
    assert "原字幕事实" not in persisted
    assert "问题" not in persisted


def test_trial_public_measurement_keeps_hash_and_ids_but_not_full_draft() -> None:
    record = _trial(
        _fixed_request(), index=1, latency=10, draft=_draft("私有完整回答")
    )
    public = record.public_measurement()
    serialized = json.dumps(public, ensure_ascii=False)
    assert public["final_draft_hash"]
    assert public["final_citation_ids"] == [_span().citation_id]
    assert "私有完整回答" not in serialized
    assert public["configuration"] == {
        "configuration_id": "baseline",
        "thinking": True,
        "reasoning_effort": "high",
        "temperature": "provider_default",
    }


def test_scripted_rewrites_are_bounded_distinct_and_not_gold() -> None:
    manifest = json.loads(h0.MANIFEST_PATH.read_text(encoding="utf-8"))
    for case in manifest["cases"]:
        rewrites = h0.SCRIPTED_REWRITES[case["case_id"]]
        queries = bounded_distinct_queries(case["query"], rewrites)
        assert len(queries) == 3
        assert len(set(value.casefold() for value in queries)) == 3
    assert "target_answer" not in json.dumps(
        h0.SCRIPTED_REWRITES, ensure_ascii=False
    ).casefold()


def test_current_runtime_is_not_modified_to_implement_h2_decision_view() -> None:
    assert "DecisionView" not in SCRIPT_PATH.read_text(encoding="utf-8")
    assert not hasattr(DeepSearchService, "decision_view")
    assert GroundedAnswerDraft.model_json_schema()["title"] == "GroundedAnswerDraft"
