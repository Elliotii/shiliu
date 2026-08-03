from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import inspect
import json
import re
from typing import Callable
from unittest.mock import patch

import numpy as np
import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from shiliu.app import Application
from shiliu.ask import AskService
from shiliu.ask.contracts import AskRequest, AnswerBlock, GroundedAnswerDraft
from shiliu.ask.deep.budget import DeepSearchBudget
from shiliu.ask.deep.contracts import AgentDecision, ToolObservation
from shiliu.ask.deep.decision import DecisionViewProjector, _decision_messages
from shiliu.ask.deep.navigation import NavigationService
from shiliu.ask.deep.reducer import DeepStateReducer, action_key
from shiliu.ask.deep.transcript import TranscriptSearchService, TranscriptWindowReader
from shiliu.domain import FavoriteItem, SubtitleSegment
from shiliu.domain import PipelineError
from shiliu.evidence.contracts import SourceArtifactReference
from shiliu.evidence.source import load_source_artifact
from shiliu.retrieval.coordinator import SYNC_STATE_VERSION
from shiliu.retrieval.dense import SQLiteExactDenseIndex
from shiliu.retrieval.hybrid import HybridRetrievalService
from shiliu.retrieval.models import RetrievalFilters
from shiliu.retrieval.product_search import ProductSearchFilterRequest
from shiliu.llm import OpenAICompatibleProvider
from shiliu.web import create_web_app


@dataclass
class _Reply:
    output: object
    usage: dict[str, int]
    finish_reason: str = "stop"
    response_id: str = "scripted-response"
    latency_ms: float = 1
    retry_count: int = 0


class _ScriptedProvider:
    def __init__(
        self,
        policy: Callable[[int, dict[str, object]], dict[str, object]],
        *,
        answer_status: str = "complete",
        on_call: Callable[[str, int], None] | None = None,
    ) -> None:
        self.policy = policy
        self.answer_status = answer_status
        self.on_call = on_call
        self.agent_calls = 0
        self.answer_calls = 0
        self.timeouts: list[tuple[str, float | None]] = []
        self.answer_messages: list[dict[str, str]] = []

    def generate_structured(
        self,
        *,
        role,
        messages,
        response_schema,
        max_tokens,
        timeout_seconds=None,
    ):
        self.timeouts.append((role, timeout_seconds))
        if role == "agent_action":
            self.agent_calls += 1
            if self.on_call is not None:
                self.on_call(role, self.agent_calls)
            payload = json.loads(messages[-1]["content"])
            return _Reply(
                AgentDecision.model_validate(
                    self.policy(self.agent_calls, payload)
                ),
                {"prompt_tokens": 20, "completion_tokens": 10},
                response_id=f"agent-{self.agent_calls}",
            )
        if role == "grounded_answer":
            self.answer_calls += 1
            if self.on_call is not None:
                self.on_call(role, self.answer_calls)
            self.answer_messages = list(messages)
            serialized = "\n".join(value["content"] for value in messages)
            citation_ids = re.findall(r"citation_v1_[0-9a-f]{64}", serialized)
            citation_id = citation_ids[0] if citation_ids else ""
            if self.answer_status == "insufficient":
                draft = GroundedAnswerDraft(
                    status="insufficient",
                    answer_blocks=[],
                    limitations=["字幕证据不足"],
                )
            else:
                draft = GroundedAnswerDraft(
                    status=self.answer_status,
                    answer_blocks=[
                        AnswerBlock(
                            text="MCP 的权威字幕事实。",
                            citation_ids=[citation_id],
                        )
                    ],
                    limitations=(
                        ["只覆盖部分问题"]
                        if self.answer_status == "partial"
                        else []
                    ),
                )
            return _Reply(
                draft,
                {"prompt_tokens": 100, "completion_tokens": 30},
                response_id=f"answer-{self.answer_calls}",
            )
        raise AssertionError(f"unexpected role: {role}")


class _MalformedProvider(_ScriptedProvider):
    def generate_structured(self, **kwargs):
        if kwargs["role"] == "agent_action":
            error = PipelineError(
                "malformed action", code="invalid_model_output", retryable=True
            )
            error.completion_metadata = {
                "finish_reason": "stop",
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
                "response_id": "bad-action",
                "latency_ms": 4,
                "retry_count": 0,
                "content_received": True,
            }
            raise error
        return super().generate_structured(**kwargs)


class _FakeEmbeddingProvider:
    model_id = "v4-deep-filter-fake"
    dimension = 8

    def embed_documents(self, texts):
        return [self._vector(value) for value in texts]

    def embed_query(self, text):
        return self._vector(text)

    def count_tokens(self, text, *, add_special_tokens=True):
        return len(text) + (2 if add_special_tokens else 0)

    def truncate_text(self, text, max_content_tokens):
        return text[:max_content_tokens]

    def _vector(self, text):
        vector = np.zeros(self.dimension, dtype=np.float32)
        for index, value in enumerate(text.encode("utf-8")):
            vector[index % self.dimension] += value % 31 + 1
        vector[0] += 1
        return vector / np.linalg.norm(vector)


class _FakeClock:
    def __init__(self, value: float = 1000) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _make_core(app_paths, provider):
    core = Application(app_paths)
    source_db_id = core.db.create_favorite_source(
        folder_id=902, folder_title="Deep Fixture"
    )
    items = [
        FavoriteItem(
            bvid="BV1234567890",
            title="MCP Agent Architecture",
            uploader="Creator A",
            favorite_time=2,
        ),
        FavoriteItem(
            bvid="BV0987654321",
            title="Other Topic",
            uploader="Creator B",
            favorite_time=1,
        ),
    ]
    core.db.record_source_snapshot(
        source_db_id, items, processing_profile="formal"
    )
    video_ids: list[int] = []
    for index, item in enumerate(items):
        video = core.db.get_video_by_source(item.bvid)
        assert video is not None
        video_id = int(video["id"])
        video_ids.append(video_id)
        text = (
            [
                "MCP 使用客户端、服务端和传输层连接模型与外部能力。",
                "协议消息遵循明确的请求和响应结构。",
                "Agent 根据工具观察结果继续规划。",
                "字幕窗口提供相邻上下文。",
                "最终回答必须绑定原字幕引用。",
            ]
            if index == 0
            else [
                "这是与目标无关的另一个主题。",
                "它不包含 MCP 的关键事实。",
            ]
        )
        _, raw_path = core.artifacts.save_raw_subtitle(
            item.bvid,
            [
                SubtitleSegment.model_validate(
                    {"from": offset * 5, "to": offset * 5 + 4, "content": value}
                )
                for offset, value in enumerate(text)
            ],
        )
        directory = core.artifacts.video_dir(item.bvid)
        summary_path = directory / "summary.refined.json"
        transcript_path = directory / "transcript.refined.json"
        core.artifacts.write_json(
            summary_path,
            {
                "conclusion": "导航摘要绝密：这是导航材料，不能引用。",
                "key_points": ["导航关键点一", "导航关键点二", "导航关键点三"],
                "detailed_notes": ["导航详细说明"],
                "important_chapters": [],
                "entities": [{"name": "MCP", "kind": "protocol", "note": ""}],
                "action_items": [],
                "limitations": [],
                "related_links": [],
            },
        )
        core.artifacts.write_json(
            transcript_path,
            {
                "sections": [
                    {
                        "title": "整理稿",
                        "start_seconds": 0,
                        "paragraphs": ["整理稿绝密：只允许导航。"],
                    }
                ]
            },
        )
        core.db.update_video(
            video_id,
            title=item.title,
            uploader=item.uploader,
            description="简介绝密：只允许导航。",
            status="completed",
            raw_subtitle_path=str(raw_path),
            subtitle_source="human",
            subtitle_language="zh",
            summary_path=str(summary_path),
            transcript_path=str(transcript_path),
            active_revision="refined",
        )
        core.db.create_note(video_id, "用户笔记绝密：只允许导航。")
    core.retrieval.rebuild()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with core.db.connect() as connection:
        for video_id in video_ids:
            connection.execute(
                """
                INSERT INTO retrieval_sync_state(
                    video_id, sync_state_version, desired_state, lexical_state,
                    dense_state, last_trigger, last_attempt_at, last_success_at,
                    last_error_stage, last_error_message, updated_at
                ) VALUES(?, ?, 'indexed', 'current', 'not_ready', 'test',
                         ?, ?, NULL, NULL, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    sync_state_version=excluded.sync_state_version,
                    desired_state=excluded.desired_state,
                    lexical_state=excluded.lexical_state,
                    dense_state=excluded.dense_state,
                    last_trigger=excluded.last_trigger,
                    last_attempt_at=excluded.last_attempt_at,
                    last_success_at=excluded.last_success_at,
                    last_error_stage=NULL,
                    last_error_message=NULL,
                    updated_at=excluded.updated_at
                """,
                (video_id, SYNC_STATE_VERSION, now, now, now),
            )
    core._ask_service = AskService(
        db=core.db,
        artifacts=core.artifacts,
        product_search=core.product_search,
        provider_factory=lambda _role: provider,
        runtime_corpus_identity=core.runtime_config.corpus_identity,
    )
    return core, tuple(video_ids)


def _dynamic_policy(round_number: int, payload: dict[str, object]):
    if round_number == 1:
        return {"action": {"kind": "search_navigation", "query": "MCP"}}
    if round_number == 2:
        navigation = payload["navigation_documents"]
        assert isinstance(navigation, list) and navigation
        return {
            "action": {
                "kind": "search_transcripts",
                "query": "MCP",
                "video_ids": [navigation[0]["video_id"]],
            }
        }
    if round_number == 3:
        anchors = payload["window_anchors"]
        assert isinstance(anchors, list) and anchors
        return {
            "action": {
                "kind": "read_transcript_window",
                "anchor_segment_id": anchors[0]["anchor_segment_id"],
                "before": 1,
                "after": 1,
            }
        }
    return {"action": {"kind": "finish", "summary": "已有权威证据"}}


def test_action_contract_is_strict_and_bounded() -> None:
    decision = AgentDecision.model_validate(
        {
            "action": {
                "kind": "search_transcripts",
                "query": "  ＭＣＰ ",
                "video_ids": [3, 3, 2],
            }
        }
    )
    assert decision.action.query == "MCP"
    assert decision.action.video_ids == [3, 2]


def test_decision_view_is_deterministic_bounded_and_keeps_legal_anchors(
    app_paths,
) -> None:
    provider = _ScriptedProvider(_dynamic_policy)
    core, _ = _make_core(app_paths, provider)
    deep = core.ask_service.deep_service
    search = TranscriptSearchService(
        evidence_search=deep.evidence_search,
        materializer=deep.materializer,
    ).search("MCP", filters=ProductSearchFilterRequest())
    state = deep._initial_state(
        "projection", AskRequest(query="MCP", mode="deep"), 1000
    )
    state["evidence_spans"] = list(search.spans)
    state["visited_segment_ids"] = [
        f"visited-segment-{index}" for index in range(60)
    ]
    state["visited_video_ids"] = list(range(1, 25))
    state["previous_queries"] = [f"query-{index}" for index in range(24)]
    original_ids = [
        tuple(value.segment_ids) for value in state["evidence_spans"]
    ]

    projector = DecisionViewProjector(DeepSearchBudget())
    first = projector.project(state, now=1001)
    second = projector.project(state, now=1001)

    assert first == second
    assert first["question"] == first["priority_open_question"] == "MCP"
    assert "visited_segment_ids" not in first
    assert first["visited_summary"]["segment_count"] == 60
    assert len(first["visited_summary"]["recent_video_ids"]) == 8
    assert len(first["previous_scoped_query_keys"]) == 12
    assert all(
        "segment_ids" not in value for value in first["transcript_evidence"]
    )
    legal = {
        segment_id
        for span in state["evidence_spans"]
        for segment_id in span.segment_ids
    }
    assert {
        value["anchor_segment_id"] for value in first["window_anchors"]
    }.issubset(legal)
    assert original_ids == [
        tuple(value.segment_ids) for value in state["evidence_spans"]
    ]


def test_decision_view_materially_reduces_scripted_high_cost_payload() -> None:
    state = {
        "query": "原始问题",
        "open_questions": ["当前问题"] * 6,
        "resolved_questions": [{"question": "已解决"}] * 6,
        "last_action": {"kind": "search_transcripts", "query": "问题"},
        "last_observation_summary": "观察" * 500,
        "navigation_documents": [],
        "evidence_spans": [],
        "visited_video_ids": list(range(1, 25)),
        "visited_segment_ids": [f"segment-{index:03d}" for index in range(60)],
        "previous_queries": [f"query-{index:02d}" for index in range(24)],
        "decision_rounds": 3,
        "tool_calls": 3,
        "search_deadline": 1200,
        "total_deadline": 1300,
    }
    from shiliu.ask.deep.contracts import NavigationDocument

    state["navigation_documents"] = [
        NavigationDocument(
            video_id=index,
            bvid=f"BV{index:010d}",
            title="标题" * 20,
            uploader="作者" * 10,
            description="描述" * 200,
            summary_sections=["摘要" * 200] * 4,
            matched_excerpt="匹配" * 200,
            matched_sources=["title"],
            source_labels={},
            metadata={},
        )
        for index in range(1, 9)
    ]
    old_shape = {
        "question": state["query"],
        "open_questions": state["open_questions"],
        "resolved_questions": state["resolved_questions"],
        "last_action": state["last_action"],
        "last_observation_summary": state["last_observation_summary"][:1000],
        "navigation_documents": [
            {
                "video_id": value.video_id,
                "title": value.title,
                "uploader": value.uploader,
                "description": value.description[:400],
                "summary_sections": value.summary_sections[:4],
                "matched_excerpt": value.matched_excerpt[:400],
            }
            for value in state["navigation_documents"]
        ],
        "visited_video_ids": state["visited_video_ids"][-24:],
        "visited_segment_ids": state["visited_segment_ids"][-60:],
        "previous_scoped_query_keys": state["previous_queries"][-24:],
    }
    projected = DecisionViewProjector(DeepSearchBudget()).project(
        state, now=1001
    )
    old_chars = len(json.dumps(old_shape, ensure_ascii=False))
    new_chars = len(json.dumps(projected, ensure_ascii=False))

    assert new_chars <= old_chars * 0.60
    invalid = [
        {"action": {"kind": "unknown", "query": "MCP"}},
        {"action": {"kind": "search_navigation", "query": ""}},
        {
            "action": {
                "kind": "search_transcripts",
                "query": "MCP",
                "video_ids": list(range(1, 10)),
            }
        },
        {
            "action": {
                "kind": "read_transcript_window",
                "anchor_segment_id": "s",
                "before": -1,
                "after": 0,
            }
        },
        {
            "action": {"kind": "finish", "summary": ""},
            "unexpected": True,
        },
    ]
    for payload in invalid:
        with pytest.raises(ValidationError):
            AgentDecision.model_validate(payload)

    navigation_key = action_key(
        AgentDecision.model_validate(
            {"action": {"kind": "search_navigation", "query": "MCP"}}
        )
    )
    transcript_key = action_key(
        AgentDecision.model_validate(
            {
                "action": {
                    "kind": "search_transcripts",
                    "query": "MCP",
                    "video_ids": [3, 2],
                }
            }
        )
    )
    reordered_key = action_key(
        AgentDecision.model_validate(
            {
                "action": {
                    "kind": "search_transcripts",
                    "query": "ｍｃｐ",
                    "video_ids": [2, 3],
                }
            }
        )
    )
    assert navigation_key != transcript_key
    assert transcript_key == reordered_key
    window_key = action_key(
        AgentDecision.model_validate(
            {
                "action": {
                    "kind": "read_transcript_window",
                    "anchor_segment_id": "segment-1",
                    "before": 2,
                    "after": 2,
                }
            }
        )
    )
    assert window_key == action_key(
        AgentDecision.model_validate(
            {
                "action": {
                    "kind": "read_transcript_window",
                    "anchor_segment_id": "segment-1",
                    "before": 2,
                    "after": 2,
                }
            }
        )
    )


def test_navigation_projection_is_source_labeled_and_navigation_only(
    app_paths,
) -> None:
    provider = _ScriptedProvider(_dynamic_policy)
    core, video_ids = _make_core(app_paths, provider)
    documents = NavigationService(
        db=core.db,
        artifacts=core.artifacts,
        product_search=core.product_search,
    ).search("MCP", filters=ProductSearchFilterRequest())
    assert documents and documents[0].video_id == video_ids[0]
    document = documents[0]
    assert document.authority == "navigation_only"
    assert "导航摘要绝密" in "\n".join(document.summary_sections)
    assert "用户笔记绝密" in "\n".join(document.user_notes)
    assert all(
        label.navigation_allowed and not label.citation_allowed
        for label in document.source_labels.values()
    )
    assert document.source_labels["title"].priority == "high"
    assert document.source_labels["description"].priority == "medium"
    assert document.source_labels["user_notes"].priority == "low"
    assert document.source_labels["cleaned_transcript"].priority == "low"


def test_focused_filter_applies_before_lexical_dense_and_hybrid_ranking(
    app_paths,
) -> None:
    provider = _ScriptedProvider(_dynamic_policy)
    core, video_ids = _make_core(app_paths, provider)
    filters = RetrievalFilters(video_ids=(video_ids[1],))
    lexical = core.retrieval.search(
        "MCP", level="transcript_chunk", top_k=20, filters=filters
    )
    assert lexical and {value.video_id for value in lexical} == {video_ids[1]}

    dense = SQLiteExactDenseIndex(
        db=core.db, provider=_FakeEmbeddingProvider()
    )
    dense.rebuild()
    with core.db.connect() as connection:
        connection.execute(
            "UPDATE retrieval_sync_state SET dense_state='current'"
        )
    dense_results = dense.search(
        "MCP", level="transcript_chunk", top_k=20, filters=filters
    )
    hybrid_results = HybridRetrievalService(
        lexical=core.retrieval, dense=dense
    ).search("MCP", level="transcript_chunk", top_k=20, filters=filters)
    assert dense_results and {value.video_id for value in dense_results} == {
        video_ids[1]
    }
    assert hybrid_results and {
        value.video_id for value in hybrid_results
    } == {video_ids[1]}


def test_window_reader_stays_current_and_within_one_timeline(app_paths) -> None:
    provider = _ScriptedProvider(_dynamic_policy)
    core, video_ids = _make_core(app_paths, provider)
    deep = core.ask_service.deep_service
    calls = 0
    original_search = core.product_search.search_with_raw

    def counted_search(request, *, video_ids=()):
        nonlocal calls
        calls += 1
        return original_search(request, video_ids=video_ids)

    core.product_search.search_with_raw = counted_search
    search = TranscriptSearchService(
        evidence_search=deep.evidence_search,
        materializer=deep.materializer,
    ).search(
        "MCP",
        filters=ProductSearchFilterRequest(),
        video_ids=(video_ids[0],),
    )
    assert search.spans
    assert calls == 1
    assert {value.video_id for value in search.spans} == {video_ids[0]}
    assert search.spans[0].retrieval_provenance[0]["video_ids"] == [
        video_ids[0]
    ]
    anchor = search.spans[0].segment_ids[0]
    span = TranscriptWindowReader(
        core.db, deep.materializer
    ).read(
        video_id=video_ids[0],
        anchor_segment_id=anchor,
        before=4,
        after=4,
    ).span
    assert anchor in span.segment_ids
    assert len({value.run_local_ordinal for value in span.segments}) == len(
        span.segments
    )
    assert all(
        value.timeline_run_id == span.timeline_run_id
        for value in load_source_artifact(
            SourceArtifactReference(
                platform="bilibili",
                source_id="BV1234567890",
                part=1,
                source_type="human",
                source_language="zh",
                artifact_path=core.db.get_video(video_ids[0])["raw_subtitle_path"],
            )
        ).segments
        if value.segment_id in span.segment_ids
    )
    deep.materializer.validate_current(span)

    raw_json = core.artifacts.video_dir("BV1234567890") / "subtitle-raw.json"
    payload = [
        {"from": 0, "to": 1, "content": "first run one"},
        {"from": 1, "to": 2, "content": "first run two"},
        {"from": 0, "to": 1, "content": "second run one"},
        {"from": 1, "to": 2, "content": "second run two"},
    ]
    core.artifacts.write_json(raw_json, payload)
    reference = SourceArtifactReference(
        platform="bilibili",
        source_id="BV1234567890",
        part=1,
        source_type="human",
        source_language="zh",
        artifact_path=str(raw_json),
    )
    multi_run = load_source_artifact(reference)
    assert len(multi_run.timeline_runs) == 2
    first_window = TranscriptWindowReader(
        core.db, deep.materializer
    ).read(
        video_id=video_ids[0],
        anchor_segment_id=multi_run.segments[0].segment_id,
        before=0,
        after=4,
    ).span
    second_window = TranscriptWindowReader(
        core.db, deep.materializer
    ).read(
        video_id=video_ids[0],
        anchor_segment_id=multi_run.segments[3].segment_id,
        before=4,
        after=0,
    ).span
    assert len(first_window.segment_ids) == len(second_window.segment_ids) == 2
    assert first_window.timeline_run_id != second_window.timeline_run_id
    with pytest.raises(Exception) as error:
        TranscriptWindowReader(core.db, deep.materializer).read(
            video_id=video_ids[0],
            anchor_segment_id=anchor,
        )
    assert getattr(error.value, "code", "") == "citation_segment_missing"


def test_deep_api_replans_navigation_search_window_and_shared_answer(
    app_paths,
) -> None:
    provider = _ScriptedProvider(_dynamic_policy)
    core, _ = _make_core(app_paths, provider)
    with patch(
        "shiliu.evidence.stage3a.resolve_from_search_candidates",
        side_effect=AssertionError("Candidate Builder must not run"),
    ):
        client = TestClient(create_web_app(core))
        response = client.post(
            "/api/ask", json={"query": "MCP 如何连接外部能力", "mode": "deep"}
        )
    body = response.json()
    assert response.status_code == 200
    assert body["mode"] == "deep"
    assert body["status"] == "complete"
    assert body["termination_reason"] == "answer_ready"
    assert body["answer_blocks"] and body["citations"]
    assert body["trace_summary"]["decision_rounds"] == 4
    assert body["trace_summary"]["tool_calls"] == 3
    trace = client.get(f"/api/ask/traces/{body['run_id']}").json()["trace"]
    assert trace["policy_version"] == "v4-deep-policy-v1"
    actions = [
        event["action"]["kind"]
        for event in trace["events"]
        if event["event_type"] == "decision"
    ]
    assert actions == [
        "search_navigation",
        "search_transcripts",
        "read_transcript_window",
        "finish",
    ]
    answer_context = "\n".join(
        value["content"] for value in provider.answer_messages
    )
    assert "MCP 使用客户端" in answer_context
    assert "导航摘要绝密" not in answer_context
    assert "用户笔记绝密" not in answer_context
    assert "整理稿绝密" not in answer_context
    assert core.ask_service.finalizer is core.ask_service.deep_service.finalizer
    assert getattr(core.ask_service.deep_service.graph.compiled, "checkpointer") is None
    for component in (
        core.ask_service.deep_service.graph.__class__,
        core.ask_service.deep_service.__class__,
        DeepStateReducer,
    ):
        source = inspect.getsource(component)
        assert "stage3a" not in source
        assert "create_agent" not in source


def test_empty_navigation_forces_one_global_transcript_search_for_arbitrary_wording(
    app_paths,
) -> None:
    def policy(round_number: int, payload: dict[str, object]):
        if round_number == 1:
            return {
                "action": {
                    "kind": "search_navigation",
                    "query": "外部能力",
                }
            }
        evidence = payload["transcript_evidence"]
        assert isinstance(evidence, list) and evidence
        return {"action": {"kind": "finish", "summary": "已有字幕证据"}}

    provider = _ScriptedProvider(policy)
    core, _ = _make_core(app_paths, provider)
    deep = core.ask_service.deep_service
    deep.graph.navigation.search = lambda *_args, **_kwargs: []

    response, trace = deep.ask(
        AskRequest(query="请解释一种任意措辞的连接方式", mode="deep")
    )

    assert response.status == "complete"
    assert response.answer_blocks and response.citations
    assert response.trace_summary.decision_rounds == 2
    assert response.trace_summary.tool_calls == 2
    assert response.trace_summary.retrieval_count == 1
    decisions = [
        value["action"]["kind"]
        for value in trace["events"]
        if value["event_type"] == "decision"
    ]
    observations = [
        value["observation_kind"]
        for value in trace["events"]
        if value["event_type"] == "observation"
    ]
    fallback = [
        value
        for value in trace["events"]
        if value["event_type"] == "empty_navigation_transcript_fallback"
    ]
    assert decisions == ["search_navigation", "finish"]
    assert observations == ["navigation", "transcript_search"]
    assert fallback == [
        {
            "event_type": "empty_navigation_transcript_fallback",
            "source_action_key": "navigation:外部能力",
            "forced_action": {
                "kind": "search_transcripts",
                "query": "外部能力",
                "video_ids": [],
            },
            "bounded_observation_summary": (
                "empty navigation deterministically routed to one global "
                "transcript search"
            ),
        }
    ]


def test_repeated_no_new_and_malformed_action_stop_are_typed(app_paths) -> None:
    repeated = _ScriptedProvider(
        lambda _round, _payload: {
            "action": {
                "kind": "search_transcripts",
                "query": "ZZZZZ",
                "video_ids": [],
            }
        }
    )
    repeated_core, _ = _make_core(app_paths, repeated)
    repeated_body = TestClient(create_web_app(repeated_core)).post(
        "/api/ask", json={"query": "不存在", "mode": "deep"}
    ).json()
    assert repeated_body["status"] == "insufficient"
    assert repeated_body["termination_reason"] == "repeated_search"
    assert repeated_body["trace_summary"]["decision_rounds"] == 2
    assert repeated_body["trace_summary"]["tool_calls"] == 1

    malformed = _MalformedProvider(_dynamic_policy)
    malformed_core, _ = _make_core(app_paths, malformed)
    malformed_body = TestClient(create_web_app(malformed_core)).post(
        "/api/ask", json={"query": "MCP", "mode": "deep"}
    ).json()
    assert malformed_body["status"] == "insufficient"
    assert malformed_body["termination_reason"] == "provider_error"
    trace = malformed_core.ask_service.get_trace(malformed_body["run_id"])
    event = next(
        value for value in trace["events"]
        if value["event_type"] == "decision_error"
    )
    assert event["response_id"] == "bad-action"
    assert event["provider_error_code"] == "invalid_model_output"
    assert malformed.answer_calls == 0


def test_evidence_stop_returns_partial_and_worklist_resolution_is_citation_bound(
    app_paths,
) -> None:
    provider = _ScriptedProvider(
        lambda _round, _payload: {
            "action": {
                "kind": "search_transcripts",
                "query": "MCP",
                "video_ids": [],
            }
        }
    )
    core, _ = _make_core(app_paths, provider)
    response, _ = core.ask_service.deep_service.ask(
        AskRequest(query="MCP", mode="deep")
    )
    assert response.status == "partial"
    assert response.termination_reason == "repeated_search"
    assert response.answer_blocks and response.citations

    deep = core.ask_service.deep_service
    search = TranscriptSearchService(
        evidence_search=deep.evidence_search,
        materializer=deep.materializer,
    ).search("MCP", filters=ProductSearchFilterRequest())
    state = deep._initial_state(
        "worklist", AskRequest(query="MCP", mode="deep"), 100
    )
    state["evidence_spans"] = list(search.spans)
    known_id = search.spans[0].citation_id
    decision = AgentDecision.model_validate(
        {
            "action": {"kind": "finish", "summary": "done"},
            "open_questions": ["MCP", "补充问题", "补充问题"],
            "resolved_questions": [
                {"question": "MCP", "citation_ids": [known_id]},
                {
                    "question": "伪解决问题",
                    "citation_ids": ["citation_v1_" + "0" * 64],
                },
            ],
        }
    )
    reduced = DeepStateReducer(DeepSearchBudget()).record_decision(
        state, decision, {}
    )
    assert "MCP" not in reduced["open_questions"]
    assert reduced["open_questions"] == ["补充问题"]
    assert [value["question"] for value in reduced["resolved_questions"]] == [
        "MCP"
    ]

    stale_state = deep._initial_state(
        "stale", AskRequest(query="MCP", mode="deep"), 100
    )
    reducer = DeepStateReducer(DeepSearchBudget())
    observation = ToolObservation(
        kind="transcript_search",
        summary="stale only",
        stale_reasons=["source_version_mismatch"],
    )
    stale_state = reducer.record_observation(stale_state, observation)
    stale_state = reducer.record_observation(stale_state, observation)
    assert stale_state["termination_reason"] == "evidence_unavailable"


def test_stop_action_with_evidence_returns_partial_no_new_evidence(
    app_paths,
) -> None:
    provider = _ScriptedProvider(
        lambda round_number, _payload: (
            {
                "action": {
                    "kind": "search_transcripts",
                    "query": "MCP",
                    "video_ids": [],
                }
            }
            if round_number == 1
            else {
                "action": {
                    "kind": "stop",
                    "summary": "现有证据可用，但无法继续取得新证据",
                }
            }
        )
    )
    core, _ = _make_core(app_paths, provider)
    response, _ = core.ask_service.deep_service.ask(
        AskRequest(query="MCP", mode="deep")
    )
    assert response.status == "partial"
    assert response.termination_reason == "no_new_evidence"
    assert response.answer_blocks and response.citations
    assert provider.answer_calls == 1


def test_stop_action_without_evidence_returns_evidence_unavailable(
    app_paths,
) -> None:
    provider = _ScriptedProvider(
        lambda _round, _payload: {
            "action": {
                "kind": "stop",
                "summary": "没有可继续使用的证据",
            }
        }
    )
    core, _ = _make_core(app_paths, provider)
    response, _ = core.ask_service.deep_service.ask(
        AskRequest(query="MCP", mode="deep")
    )
    assert response.status == "insufficient"
    assert response.termination_reason == "evidence_unavailable"
    assert response.answer_blocks == []
    assert provider.answer_calls == 0


def test_finish_action_without_evidence_returns_evidence_unavailable(
    app_paths,
) -> None:
    provider = _ScriptedProvider(
        lambda _round, _payload: {
            "action": {"kind": "finish", "summary": "没有证据可回答"}
        }
    )
    core, _ = _make_core(app_paths, provider)
    response, _ = core.ask_service.deep_service.ask(
        AskRequest(query="MCP", mode="deep")
    )
    assert response.status == "insufficient"
    assert response.termination_reason == "evidence_unavailable"
    assert provider.answer_calls == 0


def test_fake_clock_enforces_search_cutoff_and_answer_deadline(app_paths) -> None:
    clock = _FakeClock()

    def advance_after_decision(role: str, count: int) -> None:
        if role == "agent_action" and count == 1:
            clock.advance(151)

    provider = _ScriptedProvider(
        lambda _round, _payload: {
            "action": {"kind": "search_navigation", "query": "MCP"}
        },
        on_call=advance_after_decision,
    )
    core, _ = _make_core(app_paths, provider)
    service = core.ask_service.deep_service.__class__(
        db=core.db,
        artifacts=core.artifacts,
        product_search=core.product_search,
        provider_factory=lambda _role: provider,
        runtime_corpus_identity=core.runtime_config.corpus_identity,
        budget=DeepSearchBudget(),
        clock=clock,
    )
    request = AskRequest(query="MCP", mode="deep")
    cutoff_response, cutoff_trace = service.ask(request)
    assert cutoff_response.status == "insufficient"
    assert cutoff_response.termination_reason == "budget_exhausted"
    assert cutoff_response.trace_summary.tool_calls == 0
    assert [
        value["guard_decision"]
        for value in cutoff_trace["events"]
        if value["event_type"] == "guard"
    ][-1] == "budget_exhausted"
    assert provider.timeouts[0][1] == pytest.approx(150)

    answer_clock = _FakeClock()

    def answer_policy(round_number: int, payload: dict[str, object]):
        if round_number == 1:
            return {
                "action": {
                    "kind": "search_transcripts",
                    "query": "MCP",
                    "video_ids": [],
                }
            }
        return {"action": {"kind": "finish", "summary": "done"}}

    def advance_before_finish(role: str, count: int) -> None:
        if role == "agent_action" and count == 2:
            answer_clock.advance(149)

    answer_provider = _ScriptedProvider(
        answer_policy, on_call=advance_before_finish
    )
    answer_service = core.ask_service.deep_service.__class__(
        db=core.db,
        artifacts=core.artifacts,
        product_search=core.product_search,
        provider_factory=lambda _role: answer_provider,
        runtime_corpus_identity=core.runtime_config.corpus_identity,
        budget=DeepSearchBudget(),
        clock=answer_clock,
    )
    answer_response, _ = answer_service.ask(request)
    assert answer_response.status == "complete"
    grounded_timeout = next(
        value for role, value in answer_provider.timeouts
        if role == "grounded_answer"
    )
    assert grounded_timeout == pytest.approx(210)

    total_clock = _FakeClock()

    def overrun_answer(role: str, _count: int) -> None:
        if role == "grounded_answer":
            total_clock.advance(361)

    total_provider = _ScriptedProvider(
        answer_policy, on_call=overrun_answer
    )
    total_service = core.ask_service.deep_service.__class__(
        db=core.db,
        artifacts=core.artifacts,
        product_search=core.product_search,
        provider_factory=lambda _role: total_provider,
        runtime_corpus_identity=core.runtime_config.corpus_identity,
        clock=total_clock,
    )
    total_response, total_trace = total_service.ask(request)
    assert total_response.status == "insufficient"
    assert total_response.termination_reason == "budget_exhausted"
    assert total_trace["finalization"]["answer_provider_call_count"] == 1

    repair_clock = _FakeClock()

    class RepairProvider(_ScriptedProvider):
        def generate_structured(self, **kwargs):
            if kwargs["role"] != "grounded_answer":
                return super().generate_structured(**kwargs)
            self.answer_calls += 1
            timeout_seconds = kwargs.get("timeout_seconds")
            self.timeouts.append(("grounded_answer", timeout_seconds))
            serialized = "\n".join(
                value["content"] for value in kwargs["messages"]
            )
            citation_ids = re.findall(
                r"citation_v1_[0-9a-f]{64}", serialized
            )
            if self.answer_calls == 1:
                repair_clock.advance(100)
                citation_id = "citation_v1_" + "f" * 64
            else:
                citation_id = citation_ids[0]
            return _Reply(
                GroundedAnswerDraft(
                    status="complete",
                    answer_blocks=[
                        AnswerBlock(
                            text="MCP 的权威字幕事实。",
                            citation_ids=[citation_id],
                        )
                    ],
                    limitations=[],
                ),
                {"prompt_tokens": 100, "completion_tokens": 30},
            )

    repair_provider = RepairProvider(answer_policy)
    repair_service = core.ask_service.deep_service.__class__(
        db=core.db,
        artifacts=core.artifacts,
        product_search=core.product_search,
        provider_factory=lambda _role: repair_provider,
        runtime_corpus_identity=core.runtime_config.corpus_identity,
        clock=repair_clock,
    )
    repair_response, repair_trace = repair_service.ask(request)
    assert repair_response.status == "complete"
    assert repair_response.trace_summary.repair_used is True
    answer_timeouts = [
        value
        for role, value in repair_provider.timeouts
        if role == "grounded_answer"
    ]
    assert answer_timeouts == [pytest.approx(210), pytest.approx(110)]
    assert repair_trace["finalization"]["repair_calls"] == 1


def test_httpx_agent_action_deadline_maps_to_budget_exhausted(
    app_paths,
) -> None:
    clock = _FakeClock()
    setup_provider = _ScriptedProvider(_dynamic_policy)
    core, _ = _make_core(app_paths, setup_provider)
    provider = OpenAICompatibleProvider(
        base_url="https://example.com/v1",
        api_key="secret",
        model="demo",
        timeout_seconds=300,
        thinking_enabled=False,
    )
    calls = 0

    class DeadlineClient:
        def __init__(self, *, timeout):
            self.timeout = float(timeout)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, *, headers, json):
            nonlocal calls
            calls += 1
            clock.advance(self.timeout)
            raise httpx.ReadTimeout(
                "agent deadline elapsed",
                request=httpx.Request("POST", url),
            )

    service = core.ask_service.deep_service.__class__(
        db=core.db,
        artifacts=core.artifacts,
        product_search=core.product_search,
        provider_factory=lambda _role: provider,
        runtime_corpus_identity=core.runtime_config.corpus_identity,
        clock=clock,
    )
    with (
        patch("shiliu.llm.time.monotonic", clock),
        patch("shiliu.llm.httpx.Client", DeadlineClient),
    ):
        response, trace = service.ask(AskRequest(query="MCP", mode="deep"))
    assert response.status == "insufficient"
    assert response.termination_reason == "budget_exhausted"
    assert calls == 1
    event = next(
        value
        for value in trace["events"]
        if value["event_type"] == "decision_error"
    )
    assert event["provider_error_code"] == "deadline_exhausted"
    assert event["retry_count"] == 0


def test_httpx_grounded_answer_deadline_maps_to_budget_exhausted(
    app_paths,
) -> None:
    clock = _FakeClock()

    def policy(round_number: int, _payload: dict[str, object]):
        if round_number == 1:
            return {
                "action": {
                    "kind": "search_transcripts",
                    "query": "MCP",
                    "video_ids": [],
                }
            }
        return {"action": {"kind": "finish", "summary": "done"}}

    agent_provider = _ScriptedProvider(policy)
    core, _ = _make_core(app_paths, agent_provider)
    answer_provider = OpenAICompatibleProvider(
        base_url="https://example.com/v1",
        api_key="secret",
        model="demo",
        timeout_seconds=300,
        thinking_enabled=False,
    )
    calls = 0
    timeouts: list[float] = []

    class DeadlineClient:
        def __init__(self, *, timeout):
            self.timeout = float(timeout)
            timeouts.append(self.timeout)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, *, headers, json):
            nonlocal calls
            calls += 1
            clock.advance(self.timeout)
            raise httpx.ReadTimeout(
                "answer deadline elapsed",
                request=httpx.Request("POST", url),
            )

    service = core.ask_service.deep_service.__class__(
        db=core.db,
        artifacts=core.artifacts,
        product_search=core.product_search,
        provider_factory=lambda role: (
            agent_provider if role == "agent_action" else answer_provider
        ),
        runtime_corpus_identity=core.runtime_config.corpus_identity,
        clock=clock,
    )
    with (
        patch("shiliu.llm.time.monotonic", clock),
        patch("shiliu.llm.httpx.Client", DeadlineClient),
    ):
        response, trace = service.ask(AskRequest(query="MCP", mode="deep"))
    assert response.status == "insufficient"
    assert response.termination_reason == "budget_exhausted"
    assert calls == 1
    assert timeouts == [pytest.approx(210)]
    assert trace["finalization"]["provider_error_code"] == "deadline_exhausted"
    assert trace["finalization"]["transport_retry_count"] == 0


def test_round_tool_no_new_and_context_budgets_are_code_enforced(
    app_paths,
) -> None:
    provider = _ScriptedProvider(
        lambda round_number, _payload: {
            "action": {
                "kind": "search_navigation",
                "query": f"MCP {round_number}",
            }
        }
    )
    core, _ = _make_core(app_paths, provider)
    core.ask_service.deep_service.graph.navigation.search = (
        lambda *_args, **_kwargs: []
    )
    request = AskRequest(query="MCP", mode="deep")
    round_response, _ = core.ask_service.deep_service.ask(request)
    assert round_response.termination_reason == "repeated_search"
    assert round_response.trace_summary.decision_rounds == 2
    assert round_response.trace_summary.tool_calls == 2

    no_new_provider = _ScriptedProvider(
        lambda round_number, _payload: {
            "action": {
                "kind": "search_transcripts",
                "query": f"ZZZZZ-{round_number}",
                "video_ids": [],
            }
        }
    )
    no_new_service = core.ask_service.deep_service.__class__(
        db=core.db,
        artifacts=core.artifacts,
        product_search=core.product_search,
        provider_factory=lambda _role: no_new_provider,
        runtime_corpus_identity=core.runtime_config.corpus_identity,
    )
    no_new_response, _ = no_new_service.ask(request)
    assert no_new_response.termination_reason == "no_new_evidence"
    assert no_new_response.trace_summary.tool_calls == 2

    tool_provider = _ScriptedProvider(
        lambda round_number, _payload: {
            "action": {
                "kind": "search_navigation",
                "query": f"MCP tool {round_number}",
            }
        }
    )
    tool_service = core.ask_service.deep_service.__class__(
        db=core.db,
        artifacts=core.artifacts,
        product_search=core.product_search,
        provider_factory=lambda _role: tool_provider,
        runtime_corpus_identity=core.runtime_config.corpus_identity,
        budget=DeepSearchBudget(max_decision_rounds=6, max_tool_calls=1),
    )
    tool_response, _ = tool_service.ask(request)
    assert tool_response.termination_reason == "budget_exhausted"
    assert tool_response.trace_summary.tool_calls == 1

    context_provider = _ScriptedProvider(
        lambda _round, _payload: {
            "action": {
                "kind": "search_transcripts",
                "query": "MCP",
                "video_ids": [],
            }
        }
    )
    context_service = core.ask_service.deep_service.__class__(
        db=core.db,
        artifacts=core.artifacts,
        product_search=core.product_search,
        provider_factory=lambda _role: context_provider,
        runtime_corpus_identity=core.runtime_config.corpus_identity,
        budget=DeepSearchBudget(final_evidence_context_chars=10),
    )
    context_response, _ = context_service.ask(request)
    assert context_response.termination_reason == "budget_exhausted"
    assert context_response.status in {"partial", "insufficient"}


def test_agent_action_provider_role_is_json_bounded_and_has_no_schema_repair() -> None:
    calls = 0
    timeouts: list[float] = []
    bodies: list[dict[str, object]] = []

    class FakeClient:
        def __init__(self, *, timeout):
            timeouts.append(float(timeout))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, *, headers, json):
            nonlocal calls
            calls += 1
            bodies.append(json)
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={
                    "id": "agent-response",
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"action":{"kind":"finish","summary":"done"},'
                                    '"open_questions":[],"resolved_questions":[]}'
                                )
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 3},
                },
            )

    provider = OpenAICompatibleProvider(
        base_url="https://example.com/v1",
        api_key="secret",
        model="demo",
        timeout_seconds=180,
        thinking_enabled=False,
    )
    with patch("shiliu.llm.httpx.Client", FakeClient):
        response = provider.generate_structured(
            role="agent_action",
            messages=[{"role": "user", "content": "choose"}],
            response_schema=AgentDecision,
            timeout_seconds=3,
        )
    assert response.output.action.kind == "finish"
    assert calls == 1
    assert timeouts[0] <= 3
    assert bodies[0]["temperature"] == 0
    assert bodies[0]["response_format"] == {"type": "json_object"}

    class InvalidClient(FakeClient):
        def post(self, url, *, headers, json):
            nonlocal calls
            calls += 1
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={
                    "id": "invalid-agent",
                    "choices": [
                        {
                            "message": {
                                "content": '{"action":{"kind":"unknown"}}'
                            },
                            "finish_reason": "stop",
                        }
                    ],
                },
            )

    calls = 0
    with patch("shiliu.llm.httpx.Client", InvalidClient):
        with pytest.raises(PipelineError) as error:
            provider.generate_structured(
                role="agent_action",
                messages=[{"role": "user", "content": "choose"}],
                response_schema=AgentDecision,
                timeout_seconds=3,
            )
    assert error.value.code == "invalid_model_output"
    assert calls == 1
