from __future__ import annotations

import json
import inspect

from fastapi.testclient import TestClient

from shiliu.ask.contracts import AskRequest
from shiliu.web import create_web_app
from test_v4_deep_search import _ScriptedProvider, _dynamic_policy, _make_core
from test_v4_fast_ask_api import _Provider, _application
from test_v5_b_stage1_knowledge_workspace import _fixture_core, _terminal_task


def test_fast_ndjson_is_persisted_ordered_and_reconnectable(app_paths) -> None:
    core, _ = _application(app_paths, _Provider())
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
    assert event_types.index("minimum_trust_passed") < event_types.index("trusted_answer_block")
    assert event_types.index("trusted_answer_block") < event_types.index("soft_review_started")
    assert "soft_review_completed" in event_types
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


def test_soft_review_material_change_is_visible_and_non_overwriting(app_paths) -> None:
    core, _ = _application(app_paths, _Provider())
    original_validate = core.ask_service.materializer.validate_current
    def changes_after_trust(span):
        if any(frame.function == "provider_free_soft_review" for frame in inspect.stack()):
            raise RuntimeError("source changed after first trusted body")
        return original_validate(span)

    core.ask_service.materializer.validate_current = changes_after_trust
    client = TestClient(create_web_app(core))
    body = client.post("/api/ask", json={"query": "MCP"}).json()
    assert body["answer_version"] == 2
    events = core.ask_service.run_store.get_events(body["run_id"])
    original = next(value for value in events if value["event_type"] == "answer_completed")
    revision = next(value for value in events if value["event_type"] == "answer_revision_created")
    assert original["payload"]["answer_version"] == 1
    assert revision["payload"]["from_version"] == 1
    assert revision["payload"]["to_version"] == 2
    assert original["payload"]["answer_blocks"] == body["answer_blocks"]
