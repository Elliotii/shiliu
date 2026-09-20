from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient

from shiliu.ask.context import ContextBuildResult
from shiliu.ask.contracts import AskRequest
from shiliu.retrieval.product_search import ProductSearchRequest
from shiliu.web import create_web_app
from test_v4_deep_search import _ScriptedProvider, _dynamic_policy, _make_core
from test_v4_fast_ask_api import _Provider, _application
from test_v5_b_stage1_knowledge_workspace import _fixture_core, _terminal_task


def test_fast_ndjson_is_persisted_ordered_and_reconnectable(
    app_paths, monkeypatch
) -> None:
    provider = _Provider()
    core, _ = _application(app_paths, provider)
    timeline = []
    original_append = core.ask_service.run_store.append_event
    original_generate = provider.generate_structured
    original_build = core.ask_service.finalizer.context_builder.build

    def record_event(run_id, event_type, payload=None, **kwargs):
        timeline.append(event_type)
        return original_append(run_id, event_type, payload, **kwargs)

    def record_provider(**kwargs):
        if kwargs["role"] == "grounded_answer":
            timeline.append("grounded_answer_provider")
        return original_generate(**kwargs)

    def four_selected_spans(**kwargs):
        context = original_build(**kwargs)
        first = context.spans[0]
        selected = (first,) + tuple(
            first.model_copy(
                update={
                    "citation_id": f"citation_v1_{index:064x}",
                    "title": f"Preview {index}",
                    "video_id": index,
                }
            )
            for index in range(2, 5)
        )
        return ContextBuildResult(
            spans=selected,
            model_context=context.model_context,
            citation_allowlist=tuple(value.citation_id for value in selected),
            truncated=context.truncated,
            dropped_span_count=context.dropped_span_count,
        )

    monkeypatch.setattr(core.ask_service.run_store, "append_event", record_event)
    monkeypatch.setattr(provider, "generate_structured", record_provider)
    monkeypatch.setattr(
        core.ask_service.finalizer.context_builder, "build", four_selected_spans
    )
    client = TestClient(create_web_app(core))
    with client.stream("POST", "/api/ask/stream", json={"query": "MCP", "mode": "fast"}) as response:
        assert response.status_code == 200
        assert response.headers["x-shiliu-run-id"].startswith("ask_run_")
        events = [json.loads(line) for line in response.iter_lines() if line]
    assert events
    assert [value["sequence"] for value in events] == list(range(1, len(events) + 1))
    assert len({value["event_id"] for value in events}) == len(events)
    assert all(value["schema_version"] == "v5.6-lifecycle-event-v1" for value in events)
    event_types = [value["event_type"] for value in events]
    previews = [value for value in events if value["event_type"] == "evidence_preview"]
    assert len(previews) == 1
    assert [value["title"] for value in previews[0]["payload"]["items"]] == [
        "MCP 介绍",
        "Preview 2",
        "Preview 3",
    ]
    assert event_types.index("evidence_preview") < event_types.index("minimum_trust_passed")
    assert timeline.index("evidence_preview") < timeline.index("grounded_answer_provider")
    assert event_types.index("minimum_trust_passed") < event_types.index("trusted_answer_block")
    assert event_types.index("trusted_answer_block") < event_types.index("answer_completed")
    assert "soft_review_started" not in event_types
    assert "soft_review_completed" not in event_types
    assert event_types[-1] == "run_completed"
    run_id = response.headers["x-shiliu-run-id"]
    cursor = events[-3]["sequence"]
    reconnect = client.get(f"/api/ask/runs/{run_id}?after_sequence={cursor}").json()
    assert [value["sequence"] for value in reconnect["events"]] == [
        value["sequence"] for value in events if value["sequence"] > cursor
    ]
    search_event = next(value for value in events if value["event_type"] == "search_completed")
    assert search_event["provenance"]["search_execution_ids"]
    assert search_event["provenance"]["evidence_reference_ids"]


def test_deep_202_poll_abort_and_research_projection_are_honest(app_paths) -> None:
    provider = _ScriptedProvider(_dynamic_policy)
    core, _ = _make_core(app_paths, provider)
    client = TestClient(create_web_app(core))
    created = client.post(
        "/api/ask/runs",
        json={"query": "MCP 如何连接外部能力", "mode": "deep"},
    )
    assert created.status_code == 202
    assert created.json()["durable_worker_claimed"] is False
    polled = client.get(created.json()["events_href"]).json()
    assert polled["run"]["lifecycle_status"] == "completed"
    assert polled["events"][-1]["event_type"] == "run_completed"
    deep_previews = [
        value for value in polled["events"] if value["event_type"] == "evidence_preview"
    ]
    assert len(deep_previews) == 1
    assert deep_previews[0]["payload"]["items"]
    assert polled["events"].index(deep_previews[0]) < next(
        index
        for index, value in enumerate(polled["events"])
        if value["event_type"] == "minimum_trust_passed"
    )

    run_id, _ = core.ask_service.start_run(AskRequest(query="等待中", mode="fast"))
    aborted = client.post(
        f"/api/ask/runs/{run_id}/abort", json={"command_id": "goal2b:abort"}
    )
    assert aborted.status_code == 202
    interrupted = client.get(f"/api/ask/runs/{run_id}").json()
    assert interrupted["run"]["lifecycle_status"] == "failed"
    assert interrupted["run"]["termination_reason"] == "interrupted"
    assert interrupted["events"][-1]["event_type"] == "run_interrupted"

    research_core = _fixture_core(app_paths)
    task_id = _terminal_task(research_core, "goal2b-lifecycle")
    research_client = TestClient(create_web_app(research_core))
    projected = research_client.get(
        f"/api/research/product/tasks/{task_id}/lifecycle"
    ).json()["events"]
    raw = research_core.research.get_task(task_id)["events"]
    assert [value["sequence"] for value in projected] == [value["sequence"] for value in raw]
    assert all(value["source_kind"] == "research_task" for value in projected)
    assert all(value["provenance"]["research_event_ids"] for value in projected)


def test_preview_emit_failure_does_not_change_answer_or_provider_calls(
    app_paths, monkeypatch
) -> None:
    provider = _Provider()
    core, _ = _application(app_paths, provider)
    original_append = core.ask_service.run_store.append_event

    def fail_preview(run_id, event_type, payload=None, **kwargs):
        if event_type == "evidence_preview":
            raise RuntimeError("preview unavailable")
        return original_append(run_id, event_type, payload, **kwargs)

    monkeypatch.setattr(core.ask_service.run_store, "append_event", fail_preview)
    client = TestClient(create_web_app(core))
    body = client.post("/api/ask", json={"query": "MCP", "mode": "fast"}).json()

    assert body["status"] == "complete"
    assert body["answer_blocks"] and body["citations"]
    assert provider.answer_calls == 1
    trace = core.ask_service.get_trace(body["run_id"])
    assert trace["answer_provider_call_count"] == 1
    assert trace["transport_retry_count"] == 0
    assert trace["repair_calls"] == 0
    events = core.ask_service.run_store.get_events(body["run_id"])
    assert not any(value["event_type"] == "evidence_preview" for value in events)
    assert events[-1]["event_type"] == "run_completed"


def test_ready_evidence_previews_before_exhausted_answer_deadline(app_paths) -> None:
    provider = _Provider()
    core, _ = _application(app_paths, provider)
    execution = core.ask_service.evidence_search.execute_search(
        ProductSearchRequest(
            query="MCP",
            mode="auto",
            scope="transcript_chunk",
            result_limit=10,
            max_windows_per_video=2,
        )
    )
    candidates = core.ask_service.evidence_search.materialize_execution(execution)
    materialized = core.ask_service.materializer.materialize(
        execution, candidates, query_index=0
    )
    events = []

    final = core.ask_service.finalizer.finalize(
        query="MCP",
        normalized_intent="解释 MCP",
        spans=list(materialized.spans),
        stale_reasons=list(materialized.stale_reasons),
        termination_reason="answer_ready",
        deadline=10,
        clock=lambda: 10,
        event_sink=lambda event_type, payload: events.append((event_type, payload)),
    )

    assert [event_type for event_type, _payload in events] == ["evidence_preview"]
    assert events[0][1]["items"]
    assert final.execution_outcome == "generation_failed"
    assert final.termination_reason == "budget_exhausted"
    assert final.limitations == ("深入搜索总运行时间已耗尽，未启动最终回答",)
    assert provider.answer_calls == 0


def test_trusted_block_reaches_final_response_without_second_review(app_paths) -> None:
    core, _ = _application(app_paths, _Provider())
    client = TestClient(create_web_app(core))
    body = client.post("/api/ask", json={"query": "MCP"}).json()
    assert body["answer_version"] == 1
    assert body["answer_blocks"]
    assert body["citations"]
    events = core.ask_service.run_store.get_events(body["run_id"])
    original = next(value for value in events if value["event_type"] == "answer_completed")
    assert original["payload"]["answer_version"] == 1
    assert original["payload"]["answer_blocks"] == body["answer_blocks"]
    event_types = [value["event_type"] for value in events]
    assert "answer_revision_created" not in event_types
    assert not any(value.startswith("soft_review_") for value in event_types)


@pytest.mark.parametrize("mode,count", [("deep", 6), ("fast", 96)])
def test_result_projection_uses_valid_count_not_adopted_identity_count(app_paths, mode, count) -> None:
    core, _ = _application(app_paths, _Provider())
    store = core.ask_service.run_store
    run_id, _ = core.ask_service.start_run(AskRequest(query="统计投影", mode=mode))
    metrics = {"valid_evidence_count": count}
    trace = {"execution_outcome": "generation_failed"}
    trace.update({"finalization": metrics} if mode == "deep" else metrics)
    store.complete(
        run_id=run_id, trace=trace, answer_status="insufficient",
        termination_reason="provider_error", query_analysis={}, rewrites=[],
        search_executions=[], final_evidence=[], citations=[], answer_blocks=[],
        limitations=["回答生成失败"], usage_summary={},
    )
    client = TestClient(create_web_app(core))
    response = client.get(f"/api/ask/runs/{run_id}").json()["result"]
    assert response["trace_summary"]["valid_evidence_count"] == count
    assert response["citations"] == []
