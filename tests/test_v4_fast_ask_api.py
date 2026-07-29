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
    assert partial["answer_blocks"] and partial["limitations"]

    insufficient_provider = _Provider(answer_modes=("insufficient",))
    insufficient_core, _ = _application(app_paths, insufficient_provider)
    insufficient = TestClient(create_web_app(insufficient_core)).post(
        "/api/ask", json={"query": "MCP"}
    ).json()
    assert insufficient["status"] == "insufficient"
    assert insufficient["termination_reason"] == "answer_ready"
    assert insufficient["answer_blocks"] == insufficient["citations"] == []
    assert insufficient["limitations"] == [
        "本次检索未找到足以回答该问题的可靠字幕证据"
    ]


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
    assert failed["termination_reason"] == "provider_error"
    assert failed["answer_blocks"] == failed["citations"] == []
    assert failed_provider.answer_calls == 2
    failed_trace = failed_core.ask_service.get_trace(failed["run_id"])
    assert failed_trace["answer_calls"] == 1
    assert failed_trace["repair_calls"] == 1
    assert failed_trace["answer_provider_call_count"] == 2


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
    assert body["termination_reason"] == "provider_error"
    assert body["answer_blocks"] == body["citations"] == []
    assert body["trace_summary"]["repair_used"] is False
    assert provider.answer_calls == 1
    assert trace["answer_calls"] == 1
    assert trace["repair_calls"] == 0
    assert trace["answer_provider_call_count"] == 1
    assert trace["transport_retry_count"] == 1
    assert trace["provider_error_code"] == "provider_network"


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
