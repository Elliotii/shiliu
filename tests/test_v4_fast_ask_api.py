from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re

from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.ask import AskService
from shiliu.ask.contracts import (
    AnswerBlock,
    GroundedAnswerDraft,
    QueryAnalysis,
)
from shiliu.ask.deep.contracts import AgentDecision
from shiliu.domain import FavoriteItem, SubtitleSegment
from shiliu.domain import PipelineError
from shiliu.retrieval.coordinator import SYNC_STATE_VERSION
from shiliu.retrieval.product_search import ProductSearchRequest
from shiliu.web import create_web_app


@dataclass
class _Reply:
    output: object
    usage: dict[str, int]


class _Provider:
    def __init__(self, *, rewrites=(), answer_modes=("complete",)) -> None:
        self.rewrites = list(rewrites)
        self.answer_modes = list(answer_modes)
        self.query_calls = 0
        self.answer_calls = 0
        self.agent_calls = 0

    def generate_structured(
        self, *, role, messages, response_schema, max_tokens, timeout_seconds=None
    ):
        if role == "query_analysis":
            self.query_calls += 1
            return _Reply(
                QueryAnalysis(
                    normalized_intent="解释 MCP",
                    search_queries=self.rewrites,
                    entities=["MCP"],
                    language="zh",
                ),
                {"prompt_tokens": 10, "completion_tokens": 8},
            )
        if role == "agent_action":
            self.agent_calls += 1
            action = (
                {
                    "action": {
                        "kind": "search_transcripts",
                        "query": "MCP",
                        "video_ids": [],
                    }
                }
                if self.agent_calls == 1
                else {"action": {"kind": "finish", "summary": "证据已找到"}}
            )
            return _Reply(
                AgentDecision.model_validate(action),
                {"prompt_tokens": 20, "completion_tokens": 10},
            )
        self.answer_calls += 1
        serialized = "\n".join(value["content"] for value in messages)
        citation_ids = re.findall(r"citation_v1_[0-9a-f]{64}", serialized)
        citation_id = citation_ids[0] if citation_ids else "citation_v1_" + "0" * 64
        mode = self.answer_modes[min(self.answer_calls - 1, len(self.answer_modes) - 1)]
        if mode == "schema_invalid":
            error = PipelineError(
                "invalid structured JSON",
                code="invalid_model_output",
                retryable=True,
            )
            error.completion_metadata = {
                "finish_reason": "stop",
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
                "response_id": "invalid-response",
                "latency_ms": 3,
                "retry_count": 0,
                "content_received": True,
            }
            raise error
        if mode == "invalid":
            citation_id = "citation_v1_" + "f" * 64
            draft = GroundedAnswerDraft(
                status="complete",
                answer_blocks=[
                    AnswerBlock(text="非法引用回答", citation_ids=[citation_id])
                ],
                limitations=[],
            )
        elif mode == "duplicate":
            draft = GroundedAnswerDraft(
                status="complete",
                answer_blocks=[
                    AnswerBlock(text="同一个材料结论。", citation_ids=[citation_id]),
                    AnswerBlock(text=" 同一个材料结论! ", citation_ids=[citation_id]),
                ],
                limitations=[],
            )
        elif mode == "partial":
            draft = GroundedAnswerDraft(
                status="partial",
                answer_blocks=[
                    AnswerBlock(text="只覆盖了部分问题", citation_ids=[citation_id])
                ],
                limitations=["字幕没有覆盖其余部分"],
            )
        elif mode == "insufficient":
            draft = GroundedAnswerDraft(
                status="insufficient",
                answer_blocks=[],
                limitations=["现有字幕无法回答"],
            )
        else:
            draft = GroundedAnswerDraft(
                status="complete",
                answer_blocks=[
                    AnswerBlock(
                        text="MCP 通过协议连接模型与外部工具。",
                        citation_ids=[citation_id],
                    )
                ],
                limitations=[],
            )
        return _Reply(
            draft, {"prompt_tokens": 100, "completion_tokens": 30}
        )


def _application(app_paths, provider: _Provider):
    core = Application(app_paths)
    source_db_id = core.db.create_favorite_source(
        folder_id=901, folder_title="Ask Fixture"
    )
    core.db.record_source_snapshot(
        source_db_id,
        [
            FavoriteItem(
                bvid="BV1234567890",
                title="MCP 介绍",
                uploader="UP",
                favorite_time=1,
            )
        ],
        processing_profile="formal",
    )
    video = core.db.get_video_by_source("BV1234567890")
    video_id = int(video["id"])
    _, raw_path = core.artifacts.save_raw_subtitle(
        "BV1234567890",
        [
            SubtitleSegment.model_validate(
                {
                    "from": 12,
                    "to": 16,
                    "content": "MCP 通过协议连接模型与外部工具。",
                }
            ),
            SubtitleSegment.model_validate(
                {
                    "from": 16,
                    "to": 20,
                    "content": "调用结果会返回给模型继续处理。",
                }
            ),
        ],
    )
    core.db.update_video(
        video_id,
        status="completed",
        raw_subtitle_path=str(raw_path),
        subtitle_source="human",
        subtitle_language="zh",
    )
    core.retrieval.rebuild()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with core.db.connect() as connection:
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
        product_search=core.product_search,
        provider_factory=lambda _role: provider,
        runtime_corpus_identity=core.runtime_config.corpus_identity,
    )
    return core, raw_path


def test_fast_ask_api_complete_and_multi_query_deduplicated(app_paths) -> None:
    provider = _Provider(rewrites=(" ｍｃｐ ", "MCP"))
    core, _ = _application(app_paths, provider)
    calls = 0
    original = core.product_search.search_with_raw

    def counted(request):
        nonlocal calls
        calls += 1
        return original(request)

    core.product_search.search_with_raw = counted
    client = TestClient(create_web_app(core))
    response = client.post("/api/ask", json={"query": "MCP", "mode": "fast"})
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "complete"
    assert body["termination_reason"] == "answer_ready"
    assert len(body["answer_blocks"]) == len(body["citations"]) == 1
    assert body["answer_blocks"][0]["citation_ids"] == [
        body["citations"][0]["citation_id"]
    ]
    assert body["citations"][0]["quote_text"].startswith("MCP")
    assert body["citations"][0]["start_time"] == 12
    assert body["citations"][0]["jump_url"].endswith("t=12")
    assert calls == body["trace_summary"]["retrieval_count"] == 1
    assert provider.query_calls == provider.answer_calls == 1
    trace = client.get(f"/api/ask/traces/{body['run_id']}").json()["trace"]
    assert len(trace["search_executions"]) == 1


def test_fast_ask_is_durable_across_service_recreation(app_paths) -> None:
    provider = _Provider(rewrites=("RAG", "AI"))
    core, _ = _application(app_paths, provider)
    body = TestClient(create_web_app(core)).post(
        "/api/ask", json={"query": "MCP", "mode": "fast"}
    ).json()

    restarted = AskService(
        db=core.db,
        product_search=core.product_search,
        provider_factory=lambda _role: provider,
        runtime_corpus_identity=core.runtime_config.corpus_identity,
    )
    trace = restarted.get_trace(body["run_id"])
    run = restarted.run_store.get_run(body["run_id"])

    assert trace is not None and run is not None
    assert trace["query"] == "MCP"
    assert trace["normalized_intent"] == "解释 MCP"
    assert trace["queries"] == ["MCP", "RAG", "AI"]
    assert trace["status"] == body["status"] == "complete"
    assert trace["termination_reason"] == "answer_ready"
    assert trace["answer_blocks"] == body["answer_blocks"]
    assert trace["citations"] == body["citations"]
    assert trace["final_evidence"][0]["citation_id"] == body["citations"][0]["citation_id"]
    assert trace["provider_usage"]["query_analysis"] == {
        "prompt_tokens": 10,
        "completion_tokens": 8,
    }
    assert run["lifecycle_status"] == "completed"
    assert run["answer_status"] == "complete"
    assert "search_executions" not in run["trace"]
    assert "answer_blocks" not in run["trace"]
    assert run["query_analysis"]["entities"] == ["MCP"]
    assert run["rewrites"] == ["MCP", "RAG", "AI"]
    assert [value["relation_kind"] for value in run["search_executions"]] == [
        "original_query",
        "rewrite",
        "rewrite",
    ]
    assert all(value["trace_persisted"] for value in run["search_executions"])
    with core.db.connect() as connection:
        linked = connection.execute(
            """
            SELECT COUNT(*)
            FROM ask_search_trace_links l
            JOIN retrieval_search_traces s ON s.trace_id=l.search_trace_id
            WHERE l.run_id=?
            """,
            (body["run_id"],),
        ).fetchone()[0]
    assert linked == 3


def test_candidate_disclosure_deduplicates_and_marks_stale_after_restart(
    app_paths,
) -> None:
    provider = _Provider(rewrites=("协议",), answer_modes=("insufficient",))
    core, _ = _application(app_paths, provider)
    body = TestClient(create_web_app(core)).post(
        "/api/ask", json={"query": "MCP", "mode": "fast"}
    ).json()
    disclosure = body["candidate_disclosure"]

    assert disclosure["inspected_search_trace_count"] == 2
    assert disclosure["available_presentation_count"] == 2
    assert disclosure["reconstructed_candidate_count"] == 1
    assert len(disclosure["candidates"]) == 1
    unit_id = disclosure["candidates"][0]["unit_id"]

    with core.db.connect() as connection:
        connection.execute(
            "DELETE FROM retrieval_units_fts WHERE unit_id=?",
            (unit_id,),
        )
        connection.execute("DELETE FROM retrieval_units WHERE unit_id=?", (unit_id,))

    restarted = AskService(
        db=core.db,
        product_search=core.product_search,
        provider_factory=lambda _role: provider,
        runtime_corpus_identity=core.runtime_config.corpus_identity,
    )
    core._ask_service = restarted
    trace = TestClient(create_web_app(core)).get(
        f"/api/ask/traces/{body['run_id']}"
    ).json()["trace"]
    stale = trace["candidate_disclosure"]["candidates"]

    assert len(stale) == 1
    assert stale[0]["identity_status"] == "stale"
    assert stale[0]["unit_id"] == unit_id
    assert stale[0]["excerpt"] is None
    assert trace["citations"] == trace["final_evidence"] == []


def test_restart_marks_transcript_window_without_exact_unit_identity_stale(
    app_paths,
) -> None:
    provider = _Provider(answer_modes=("insufficient",))
    core, _ = _application(app_paths, provider)
    body = TestClient(create_web_app(core)).post(
        "/api/ask", json={"query": "MCP", "mode": "fast"}
    ).json()
    run_id = body["run_id"]
    trace_id = core.ask_service.run_store.get_run(run_id)["search_executions"][0][
        "search_trace_id"
    ]
    presentation = core.product_search.get_presentation(trace_id)
    groups = presentation["group_summary"]
    groups[0]["windows"][0].pop("best_chunk_id")
    with core.db.connect() as connection:
        connection.execute(
            """
            UPDATE retrieval_search_presentations
            SET group_summary_json=?
            WHERE trace_id=?
            """,
            (json.dumps(groups, ensure_ascii=False), trace_id),
        )

    restarted = AskService(
        db=core.db,
        product_search=core.product_search,
        provider_factory=lambda _role: provider,
        runtime_corpus_identity=core.runtime_config.corpus_identity,
    )
    candidate = restarted.get_trace(run_id)["candidate_disclosure"]["candidates"][0]

    assert candidate["candidate_kind"] == "transcript_candidate"
    assert candidate["identity_status"] == "stale"
    assert candidate["unit_id"] is None
    assert candidate["excerpt"] is None
    assert candidate["jump_url"] is None


def test_metadata_only_lead_and_unavailable_identity_remain_non_authoritative(
    app_paths,
) -> None:
    provider = _Provider()
    core, _ = _application(app_paths, provider)
    source_id = core.db.create_favorite_source(
        folder_id=902,
        folder_title="Metadata only",
    )
    core.db.record_source_snapshot(
        source_id,
        [
            FavoriteItem(
                bvid="BV0987654321",
                title="上海本帮菜餐厅清单",
                uploader="美食 UP",
                favorite_time=2,
            )
        ],
        processing_profile="formal",
    )
    core.retrieval.rebuild()
    _raw, search = core.product_search.search_with_raw(
        ProductSearchRequest(
            query="上海本帮菜餐厅",
            mode="lexical",
            scope="video",
            result_limit=5,
        )
    )
    assert search.results and search.results[0].windows == ()

    run_id = "ask_run_metadata_only_fixture"
    core.ask_service.run_store.start(
        run_id=run_id,
        query="我收藏过哪些上海餐厅视频？",
        mode="fast",
        filters={},
    )
    core.ask_service.run_store.complete(
        run_id=run_id,
        trace={},
        answer_status="insufficient",
        termination_reason="answer_ready",
        query_analysis={},
        rewrites=[],
        search_executions=[
            {
                "search_trace_id": search.trace_id,
                "trace_persisted": True,
                "query": "上海本帮菜餐厅",
                "relation_kind": "original_query",
            }
        ],
        final_evidence=[],
        citations=[],
        answer_blocks=[],
        limitations=["没有可用字幕"],
        usage_summary={},
    )
    disclosure = core.ask_service.candidate_projector.project(run_id)
    lead = disclosure.candidates[0]

    assert lead.candidate_kind == "metadata_lead"
    assert lead.identity_status == "current"
    assert lead.title == "上海本帮菜餐厅清单"
    assert lead.unit_id is lead.excerpt is None
    assert lead.jump_url is not None
    assert core.ask_service.run_store.get_run(run_id)["citations"] == []
    assert core.ask_service.run_store.get_run(run_id)["final_evidence"] == []

    presentation = core.product_search.get_presentation(search.trace_id)
    groups = presentation["group_summary"]
    groups[0]["video_id"] = 999_999
    with core.db.connect() as connection:
        connection.execute(
            """
            UPDATE retrieval_search_presentations
            SET group_summary_json=?
            WHERE trace_id=?
            """,
            (json.dumps(groups, ensure_ascii=False), search.trace_id),
        )
    unavailable = core.ask_service.candidate_projector.project(run_id).candidates[0]

    assert unavailable.video_id == 999_999
    assert unavailable.identity_status == "unavailable"
    assert unavailable.title == "历史视频 #999999（当前不可用）"
    assert unavailable.jump_url is unavailable.detail_url is None

    bounded_groups = [
        {**groups[0], "video_id": 999_000 + index, "best_rank": index}
        for index in range(1, 10)
    ]
    with core.db.connect() as connection:
        connection.execute(
            """
            UPDATE retrieval_search_presentations
            SET group_summary_json=?
            WHERE trace_id=?
            """,
            (json.dumps(bounded_groups, ensure_ascii=False), search.trace_id),
        )
    bounded = core.ask_service.candidate_projector.project(run_id)
    hard_bounded = core.ask_service.candidate_projector.project(run_id, limit=8)

    assert len(bounded.candidates) == 5
    assert bounded.reconstructed_candidate_count == 8
    assert bounded.truncated is True
    assert len(hard_bounded.candidates) == 8
    assert hard_bounded.truncated is True


def test_zero_candidate_run_reports_honest_empty_reconstruction(app_paths) -> None:
    provider = _Provider(answer_modes=("insufficient",))
    core, _ = _application(app_paths, provider)
    body = TestClient(create_web_app(core)).post(
        "/api/ask",
        json={"query": "完全不存在的词xyz987", "mode": "fast"},
    ).json()

    assert body["status"] == "insufficient"
    disclosure = body["candidate_disclosure"]
    assert disclosure["inspected_search_trace_count"] == 1
    assert disclosure["available_presentation_count"] == 1
    assert disclosure["candidates"] == []
    assert disclosure["empty_reason"] == "no_unadopted_candidates"


def test_candidate_reconstruction_bounds_lineage_and_reports_missing_presentation(
    app_paths,
) -> None:
    provider = _Provider(answer_modes=("insufficient",))
    core, _ = _application(app_paths, provider)
    body = TestClient(create_web_app(core)).post(
        "/api/ask", json={"query": "MCP", "mode": "fast"}
    ).json()
    run_id = body["run_id"]
    run = core.ask_service.run_store.get_run(run_id)
    trace_id = run["search_executions"][0]["search_trace_id"]
    with core.db.connect() as connection:
        for sequence in range(1, 13):
            connection.execute(
                """
                INSERT INTO ask_search_trace_links(
                    run_id, sequence, relation_kind, decision_sequence,
                    execution_id, search_trace_id, trace_persisted,
                    trace_error, query, created_at
                ) VALUES(?, ?, 'rewrite', NULL, NULL, ?, 1, NULL, ?, ?)
                """,
                (
                    run_id,
                    sequence,
                    trace_id,
                    f"rewrite {sequence}",
                    run["completed_at"],
                ),
            )
    bounded = core.ask_service.candidate_projector.project(run_id)

    assert bounded.inspected_search_trace_count == 12
    assert bounded.available_presentation_count == 12
    assert bounded.reconstructed_candidate_count == 1
    assert bounded.truncated is True

    with core.db.connect() as connection:
        connection.execute(
            "DELETE FROM retrieval_search_presentations WHERE trace_id=?",
            (trace_id,),
        )
    missing = core.ask_service.candidate_projector.project(run_id)

    assert missing.inspected_search_trace_count == 12
    assert missing.available_presentation_count == 0
    assert missing.failed_or_unavailable_trace_count == 12
    assert missing.candidates == []
    assert missing.empty_reason == "search_presentations_unavailable"


def test_partial_answer_discloses_only_unadopted_comparison_candidate(
    app_paths,
) -> None:
    provider = _Provider(answer_modes=("partial",))
    core, _ = _application(app_paths, provider)
    source_id = core.db.create_favorite_source(
        folder_id=903,
        folder_title="Second transcript",
    )
    core.db.record_source_snapshot(
        source_id,
        [
            FavoriteItem(
                bvid="BV1122334455",
                title="MCP 第二条介绍",
                uploader="另一位 UP",
                favorite_time=3,
            )
        ],
        processing_profile="formal",
    )
    second = core.db.get_video_by_source("BV1122334455")
    second_id = int(second["id"])
    _, raw_path = core.artifacts.save_raw_subtitle(
        "BV1122334455",
        [
            SubtitleSegment.model_validate(
                {
                    "from": 30,
                    "to": 36,
                    "content": "MCP 在另一条视频中也连接模型与外部工具。",
                }
            )
        ],
    )
    core.db.update_video(
        second_id,
        status="completed",
        raw_subtitle_path=str(raw_path),
        subtitle_source="human",
        subtitle_language="zh",
    )
    core.retrieval.rebuild()

    body = TestClient(create_web_app(core)).post(
        "/api/ask", json={"query": "MCP", "mode": "fast"}
    ).json()
    candidates = body["candidate_disclosure"]["candidates"]

    assert body["status"] == "partial"
    assert len(body["citations"]) == 1
    assert len(candidates) == 1
    assert candidates[0]["video_id"] != body["citations"][0]["video_id"]
    assert candidates[0]["video_id"] in {
        second_id,
        int(core.db.get_video_by_source("BV1234567890")["id"]),
    }


def test_fast_failed_retrieval_keeps_its_durable_search_trace_link(app_paths) -> None:
    provider = _Provider()
    core, _ = _application(app_paths, provider)
    original = core.ask_service.evidence_search.execute_search

    def searched_then_failed(request):
        execution = original(request)
        error = RuntimeError("post-search materialization failure")
        error.trace_id = execution.raw_response.trace_id
        raise error

    core.ask_service.evidence_search.execute_search = searched_then_failed
    body = TestClient(create_web_app(core)).post(
        "/api/ask", json={"query": "MCP", "mode": "fast"}
    ).json()
    trace = core.ask_service.get_trace(body["run_id"])

    assert body["status"] == "insufficient"
    assert trace is not None
    assert len(trace["search_executions"]) == 1
    assert trace["retrieval_errors"] == [
        "RuntimeError: post-search materialization failure"
    ]
    with core.db.connect() as connection:
        linked = connection.execute(
            """
            SELECT COUNT(*)
            FROM ask_search_trace_links l
            JOIN retrieval_search_traces s ON s.trace_id=l.search_trace_id
            WHERE l.run_id=?
            """,
            (body["run_id"],),
        ).fetchone()[0]
    assert linked == 1


def test_fast_ask_executes_after_v15_database_migration(app_paths) -> None:
    provider = _Provider()
    core, _ = _application(app_paths, provider)
    with core.db.connect() as connection:
        connection.executescript(
            """
            DROP TABLE ask_events;
            DROP TABLE ask_search_trace_links;
            DROP TABLE ask_runs;
            UPDATE schema_meta SET value='15' WHERE key='schema_version';
            """
        )
    core.db.initialize()
    core._ask_service = AskService(
        db=core.db,
        artifacts=core.artifacts,
        product_search=core.product_search,
        provider_factory=lambda _role: provider,
        runtime_corpus_identity=core.runtime_config.corpus_identity,
    )

    body = TestClient(create_web_app(core)).post(
        "/api/ask", json={"query": "MCP", "mode": "fast"}
    ).json()
    restarted = AskService(
        db=core.db,
        product_search=core.product_search,
        provider_factory=lambda _role: provider,
    )

    assert body["status"] == "complete"
    assert restarted.get_trace(body["run_id"])["answer_blocks"] == body[
        "answer_blocks"
    ]


def test_three_distinct_queries_execute_exactly_three_retrievals_and_keep_filters(
    app_paths,
) -> None:
    provider = _Provider(rewrites=("RAG", "AI"))
    core, _ = _application(app_paths, provider)
    requests = []
    original = core.product_search.search_with_raw

    def counted(request):
        requests.append(request)
        return original(request)

    core.product_search.search_with_raw = counted
    body = TestClient(create_web_app(core)).post(
        "/api/ask",
        json={
            "query": "MCP",
            "filters": {"reading_state": "unread", "marked": False},
        },
    ).json()
    assert body["status"] == "complete"
    assert body["trace_summary"]["query_count"] == 3
    assert body["trace_summary"]["retrieval_count"] == 3
    assert [value.query for value in requests] == ["MCP", "RAG", "AI"]
    assert all(value.filters.reading_state == "unread" for value in requests)
    assert all(value.filters.marked is False for value in requests)


def test_query_analysis_failure_falls_back_to_original_query(app_paths) -> None:
    class QueryFailureProvider(_Provider):
        def generate_structured(
            self, *, role, messages, response_schema, max_tokens
        ):
            if role == "query_analysis":
                self.query_calls += 1
                raise RuntimeError("query analysis unavailable")
            return super().generate_structured(
                role=role,
                messages=messages,
                response_schema=response_schema,
                max_tokens=max_tokens,
            )

    provider = QueryFailureProvider()
    core, _ = _application(app_paths, provider)
    body = TestClient(create_web_app(core)).post(
        "/api/ask", json={"query": "MCP"}
    ).json()
    assert body["status"] == "complete"
    assert body["trace_summary"]["query_count"] == 1
    assert body["trace_summary"]["retrieval_count"] == 1
    assert body["trace_summary"]["repair_used"] is False


def test_fast_ask_partial_and_model_declared_insufficient(app_paths) -> None:
    partial_provider = _Provider(answer_modes=("partial",))
    partial_core, _ = _application(app_paths, partial_provider)
    partial = TestClient(create_web_app(partial_core)).post(
        "/api/ask", json={"query": "MCP"}
    ).json()
    assert partial["status"] == "partial"
    assert partial["execution_outcome"] == "answer_generated"
    assert partial["answer_blocks"] and partial["limitations"]

    insufficient_provider = _Provider(answer_modes=("insufficient",))
    insufficient_core, _ = _application(app_paths, insufficient_provider)
    insufficient = TestClient(create_web_app(insufficient_core)).post(
        "/api/ask", json={"query": "MCP"}
    ).json()
    assert insufficient["status"] == "insufficient"
    assert insufficient["execution_outcome"] == "evidence_insufficient"
    assert insufficient["termination_reason"] == "answer_ready"
    assert insufficient["answer_blocks"] == insufficient["citations"] == []
    assert insufficient["limitations"] == [
        "本次检索未找到足以回答该问题的可靠字幕证据"
    ]
    disclosure = insufficient["candidate_disclosure"]
    assert disclosure["reconstruction_kind"] == (
        "durable_search_lineage_current_projection"
    )
    assert len(disclosure["candidates"]) == 1
    candidate = disclosure["candidates"][0]
    assert candidate["candidate_kind"] == "transcript_candidate"
    assert candidate["identity_status"] == "current"
    assert candidate["excerpt"] == "MCP 通过协议连接模型与外部工具。 调用结果会返回给模型继续处理。"
    assert candidate["search_query"] == "MCP"
    assert candidate["search_rank"] == 1
    assert "citation_id" not in candidate


def test_unknown_citation_repairs_once_and_repair_failure_fails_closed(
    app_paths,
) -> None:
    repaired_provider = _Provider(answer_modes=("invalid", "complete"))
    repaired_core, _ = _application(app_paths, repaired_provider)
    repaired = TestClient(create_web_app(repaired_core)).post(
        "/api/ask", json={"query": "MCP"}
    ).json()
    assert repaired["status"] == "complete"
    assert repaired["trace_summary"]["repair_used"] is True
    assert repaired_provider.answer_calls == 2
    repaired_trace = repaired_core.ask_service.get_trace(repaired["run_id"])
    assert repaired_trace["answer_calls"] == 1
    assert repaired_trace["repair_calls"] == 1
    assert repaired_trace["answer_provider_call_count"] == 2

    failed_provider = _Provider(answer_modes=("invalid", "invalid"))
    failed_core, _ = _application(app_paths, failed_provider)
    failed = TestClient(create_web_app(failed_core)).post(
        "/api/ask", json={"query": "MCP"}
    ).json()
    assert failed["status"] == "insufficient"
    assert failed["execution_outcome"] == "generation_failed"
    assert failed["termination_reason"] == "provider_error"
    assert failed["answer_blocks"] == failed["citations"] == []
    assert failed["candidate_disclosure"]["candidates"][0][
        "candidate_kind"
    ] == "transcript_candidate"
    assert failed_provider.answer_calls == 2
    failed_trace = failed_core.ask_service.get_trace(failed["run_id"])
    assert failed_trace["answer_calls"] == 1
    assert failed_trace["repair_calls"] == 1
    assert failed_trace["answer_provider_call_count"] == 2


def test_duplicate_answer_blocks_trigger_one_bounded_repair(app_paths) -> None:
    provider = _Provider(answer_modes=("duplicate", "complete"))
    core, _ = _application(app_paths, provider)
    body = TestClient(create_web_app(core)).post(
        "/api/ask", json={"query": "MCP"}
    ).json()
    trace = core.ask_service.get_trace(body["run_id"])

    assert body["status"] == "complete"
    assert body["trace_summary"]["repair_used"] is True
    assert provider.answer_calls == 2
    assert [
        value["code"] for value in trace["initial_answer_validation_errors"]
    ] == ["duplicate_answer_block"]


def test_grounded_answer_prompt_distinguishes_finite_counterexample_and_synthesis(
    app_paths,
) -> None:
    class CapturingProvider(_Provider):
        answer_system: str = ""

        def generate_structured(
            self, *, role, messages, response_schema, max_tokens, timeout_seconds=None
        ):
            if role == "grounded_answer":
                self.answer_system = messages[0]["content"]
            return super().generate_structured(
                role=role,
                messages=messages,
                response_schema=response_schema,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
            )

    provider = CapturingProvider()
    core, _ = _application(app_paths, provider)
    TestClient(create_web_app(core)).post(
        "/api/ask", json={"query": "MCP"}
    )

    assert "direct counterexample" in provider.answer_system
    assert "not a complete collection-wide audit" in provider.answer_system
    assert "For cross-video questions" in provider.answer_system
    assert "material, non-duplicate point" in provider.answer_system


def test_invalid_structured_output_still_allows_one_repair(app_paths) -> None:
    provider = _Provider(answer_modes=("schema_invalid", "complete"))
    core, _ = _application(app_paths, provider)
    body = TestClient(create_web_app(core)).post(
        "/api/ask", json={"query": "MCP"}
    ).json()
    trace = core.ask_service.get_trace(body["run_id"])
    assert body["status"] == "complete"
    assert body["trace_summary"]["repair_used"] is True
    assert provider.answer_calls == 2
    assert trace["answer_calls"] == 1
    assert trace["repair_calls"] == 1
    assert trace["answer_provider_call_count"] == 2
    assert trace["initial_provider_error_code"] == "invalid_model_output"


def test_provider_network_failure_does_not_enter_repair(app_paths) -> None:
    class NetworkFailureProvider(_Provider):
        def generate_structured(
            self, *, role, messages, response_schema, max_tokens
        ):
            if role == "grounded_answer":
                self.answer_calls += 1
                error = PipelineError(
                    "network exhausted",
                    code="provider_network",
                    retryable=True,
                )
                error.completion_metadata = {
                    "finish_reason": None,
                    "usage": None,
                    "response_id": None,
                    "latency_ms": 9,
                    "retry_count": 1,
                    "content_received": False,
                }
                raise error
            return super().generate_structured(
                role=role,
                messages=messages,
                response_schema=response_schema,
                max_tokens=max_tokens,
            )

    provider = NetworkFailureProvider()
    core, _ = _application(app_paths, provider)
    body = TestClient(create_web_app(core)).post(
        "/api/ask", json={"query": "MCP"}
    ).json()
    trace = core.ask_service.get_trace(body["run_id"])
    assert body["status"] == "insufficient"
    assert body["execution_outcome"] == "generation_failed"
    assert body["termination_reason"] == "provider_error"
    assert body["answer_blocks"] == body["citations"] == []
    assert body["trace_summary"]["repair_used"] is False
    assert provider.answer_calls == 1
    assert trace["answer_calls"] == 1
    assert trace["repair_calls"] == 0
    assert trace["answer_provider_call_count"] == 1
    assert trace["transport_retry_count"] == 1
    assert trace["provider_error_code"] == "provider_network"


def test_output_budget_failure_uses_one_role_specific_recovery(app_paths) -> None:
    class BudgetFailureProvider(_Provider):
        def generate_structured(self, **kwargs):
            if kwargs["role"] != "grounded_answer":
                return super().generate_structured(**kwargs)
            self.answer_calls += 1
            error = PipelineError(
                "reasoning consumed output budget",
                code="output_budget_exhausted",
                retryable=False,
            )
            error.completion_metadata = {
                "finish_reason": "length",
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 4096,
                    "completion_tokens_details": {"reasoning_tokens": 4096},
                },
                "latency_ms": 64000,
                "retry_count": 0,
                "content_received": False,
            }
            raise error

    primary = BudgetFailureProvider()
    recovery = _Provider()
    core, _ = _application(app_paths, primary)
    core._ask_service = AskService(
        db=core.db,
        product_search=core.product_search,
        provider_factory=lambda role: (
            recovery if role == "grounded_answer_recovery" else primary
        ),
        runtime_corpus_identity=core.runtime_config.corpus_identity,
    )

    body = TestClient(create_web_app(core)).post(
        "/api/ask", json={"query": "MCP"}
    ).json()
    trace = core.ask_service.get_trace(body["run_id"])

    assert body["status"] == "complete"
    assert body["execution_outcome"] == "answer_generated"
    assert primary.answer_calls == recovery.answer_calls == 1
    assert trace["repair_calls"] == 1
    assert trace["answer_provider_call_count"] == 2
    assert trace["initial_provider_error_code"] == "output_budget_exhausted"
    assert [item["call_kind"] for item in trace["answer_usage"]] == [
        "initial",
        "generation_recovery",
    ]
    assert trace["answer_usage"][0]["finish_reason"] == "length"
    assert trace["answer_usage"][0]["completion_tokens_details"] == {
        "reasoning_tokens": 4096
    }


def test_output_budget_recovery_failure_remains_generation_failure(app_paths) -> None:
    class BudgetFailureProvider(_Provider):
        def generate_structured(self, **kwargs):
            if kwargs["role"] != "grounded_answer":
                return super().generate_structured(**kwargs)
            self.answer_calls += 1
            error = PipelineError(
                "reasoning consumed output budget",
                code="output_budget_exhausted",
                retryable=False,
            )
            error.completion_metadata = {
                "finish_reason": "length",
                "usage": {"completion_tokens": 4096},
                "latency_ms": 1,
                "retry_count": 0,
                "content_received": False,
            }
            raise error

    primary = BudgetFailureProvider()
    recovery = BudgetFailureProvider()
    core, _ = _application(app_paths, primary)
    core._ask_service = AskService(
        db=core.db,
        product_search=core.product_search,
        provider_factory=lambda role: (
            recovery if role == "grounded_answer_recovery" else primary
        ),
        runtime_corpus_identity=core.runtime_config.corpus_identity,
    )

    body = TestClient(create_web_app(core)).post(
        "/api/ask", json={"query": "MCP"}
    ).json()
    trace = core.ask_service.get_trace(body["run_id"])

    assert body["status"] == "insufficient"
    assert body["execution_outcome"] == "generation_failed"
    assert body["termination_reason"] == "provider_error"
    assert body["answer_blocks"] == body["citations"] == []
    assert primary.answer_calls == recovery.answer_calls == 1
    assert trace["answer_provider_call_count"] == 2
    assert [item["call_kind"] for item in trace["answer_usage"]] == [
        "initial",
        "generation_recovery",
    ]


def test_empty_model_output_uses_one_role_specific_recovery(app_paths) -> None:
    class EmptyOutputProvider(_Provider):
        def generate_structured(self, **kwargs):
            if kwargs["role"] != "grounded_answer":
                return super().generate_structured(**kwargs)
            self.answer_calls += 1
            error = PipelineError(
                "empty model output",
                code="empty_model_output",
                retryable=True,
            )
            error.completion_metadata = {
                "finish_reason": "stop",
                "usage": {"prompt_tokens": 100, "completion_tokens": 0},
                "latency_ms": 10,
                "retry_count": 0,
                "content_received": False,
            }
            raise error

    primary = EmptyOutputProvider()
    recovery = _Provider()
    core, _ = _application(app_paths, primary)
    core._ask_service = AskService(
        db=core.db,
        product_search=core.product_search,
        provider_factory=lambda role: (
            recovery if role == "grounded_answer_recovery" else primary
        ),
        runtime_corpus_identity=core.runtime_config.corpus_identity,
    )

    body = TestClient(create_web_app(core)).post(
        "/api/ask", json={"query": "MCP"}
    ).json()
    trace = core.ask_service.get_trace(body["run_id"])

    assert body["status"] == "complete"
    assert body["execution_outcome"] == "answer_generated"
    assert primary.answer_calls == recovery.answer_calls == 1
    assert trace["initial_provider_error_code"] == "empty_model_output"
    assert trace["answer_provider_call_count"] == 2
    assert [item["call_kind"] for item in trace["answer_usage"]] == [
        "initial",
        "generation_recovery",
    ]


def test_non_retryable_provider_error_does_not_enter_repair(app_paths) -> None:
    class AuthenticationFailureProvider(_Provider):
        def generate_structured(
            self, *, role, messages, response_schema, max_tokens
        ):
            if role == "grounded_answer":
                self.answer_calls += 1
                error = PipelineError(
                    "bad key",
                    code="provider_authentication",
                    retryable=False,
                )
                error.completion_metadata = {
                    "finish_reason": None,
                    "usage": None,
                    "response_id": None,
                    "latency_ms": 2,
                    "retry_count": 0,
                    "content_received": False,
                }
                raise error
            return super().generate_structured(
                role=role,
                messages=messages,
                response_schema=response_schema,
                max_tokens=max_tokens,
            )

    provider = AuthenticationFailureProvider()
    core, _ = _application(app_paths, provider)
    body = TestClient(create_web_app(core)).post(
        "/api/ask", json={"query": "MCP"}
    ).json()
    trace = core.ask_service.get_trace(body["run_id"])
    assert body["status"] == "insufficient"
    assert body["termination_reason"] == "provider_error"
    assert body["trace_summary"]["repair_used"] is False
    assert provider.answer_calls == 1
    assert trace["answer_calls"] == 1
    assert trace["repair_calls"] == 0
    assert trace["answer_provider_call_count"] == 1
    assert trace["transport_retry_count"] == 0
    assert trace["provider_error_code"] == "provider_authentication"


def test_provider_factory_failure_does_not_enter_repair(app_paths) -> None:
    bootstrap_provider = _Provider()
    core, _ = _application(app_paths, bootstrap_provider)

    def failed_factory(_role):
        raise PipelineError(
            "provider config unavailable",
            code="bad_provider_config",
            retryable=False,
        )

    core._ask_service = AskService(
        db=core.db,
        product_search=core.product_search,
        provider_factory=failed_factory,
        runtime_corpus_identity=core.runtime_config.corpus_identity,
    )
    body = TestClient(create_web_app(core)).post(
        "/api/ask", json={"query": "MCP"}
    ).json()
    trace = core.ask_service.get_trace(body["run_id"])
    assert body["status"] == "insufficient"
    assert body["termination_reason"] == "provider_error"
    assert body["trace_summary"]["repair_used"] is False
    assert trace["answer_calls"] == 1
    assert trace["repair_calls"] == 0
    assert trace["answer_provider_call_count"] == 0
    assert trace["transport_retry_count"] == 0
    assert trace["provider_error_code"] == "bad_provider_config"


def test_stale_evidence_is_skipped_before_answer_generation(app_paths) -> None:
    provider = _Provider()
    core, raw_path = _application(app_paths, provider)
    payload = json.loads(raw_path.with_name("subtitle-raw.json").read_text(encoding="utf-8"))
    payload[0]["content"] = "索引建立后字幕发生变化"
    raw_path.with_name("subtitle-raw.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    body = TestClient(create_web_app(core)).post(
        "/api/ask", json={"query": "MCP"}
    ).json()
    assert body["status"] == "insufficient"
    assert body["termination_reason"] == "evidence_unavailable"
    assert body["trace_summary"]["stale_evidence_count"] >= 1
    assert provider.answer_calls == 0


def test_final_source_version_revalidation_fails_closed(app_paths, monkeypatch) -> None:
    provider = _Provider()
    core, raw_path = _application(app_paths, provider)
    materializer = core.ask_service.materializer
    original = materializer.validate_current
    calls = 0

    def mutate_after_first_validation(span):
        nonlocal calls
        calls += 1
        original(span)
        if calls == 1:
            source = raw_path.with_name("subtitle-raw.json")
            payload = json.loads(source.read_text(encoding="utf-8"))
            payload[0]["content"] += "（变化）"
            source.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )

    monkeypatch.setattr(
        materializer, "validate_current", mutate_after_first_validation
    )
    body = TestClient(create_web_app(core)).post(
        "/api/ask", json={"query": "MCP"}
    ).json()
    assert calls == 2
    assert body["status"] == "insufficient"
    assert body["termination_reason"] == "evidence_unavailable"
    assert body["citations"] == []


def test_no_evidence_and_deep_mode_are_typed(app_paths) -> None:
    provider = _Provider()
    core, _ = _application(app_paths, provider)
    client = TestClient(create_web_app(core))
    missing = client.post(
        "/api/ask", json={"query": "ZZZZZ-NO-SUCH-EVIDENCE"}
    ).json()
    assert missing["status"] == "insufficient"
    assert missing["termination_reason"] == "evidence_unavailable"
    assert provider.answer_calls == 0

    deep = client.post(
        "/api/ask", json={"query": "MCP", "mode": "deep"}
    )
    assert deep.status_code == 200
    deep_body = deep.json()
    assert deep_body["mode"] == "deep"
    assert deep_body["status"] == "complete"
    assert deep_body["termination_reason"] == "answer_ready"
    assert deep_body["trace_summary"]["decision_rounds"] == 2
    assert deep_body["trace_summary"]["tool_calls"] == 1
    trace = client.get(
        f"/api/ask/traces/{deep_body['run_id']}"
    ).json()["trace"]
    assert [
        event["action"]["kind"]
        for event in trace["events"]
        if event["event_type"] == "decision"
    ] == ["search_transcripts", "finish"]
