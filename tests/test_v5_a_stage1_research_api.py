from __future__ import annotations

from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.research import AnswerStatus, FailureClass, TerminationReason
from shiliu.web import create_web_app


def test_research_api_create_command_status_and_trace_without_provider(app_paths) -> None:
    core = Application(app_paths)
    client = TestClient(create_web_app(core))

    created = client.post(
        "/api/research/tasks",
        json={
            "task_id": "api-task",
            "command_id": "create-api",
            "objective": "验证持久任务 API",
            "success_constraints": ["可重启"],
            "evidence_policy": {"authority": "transcript"},
        },
    )
    assert created.status_code == 200
    assert created.json()["research"]["task"]["status"] == "ready"

    claimed = client.post(
        "/api/research/tasks/api-task/commands",
        json={
            "kind": "claim_owner",
            "command_id": "claim-api",
            "owner_id": "api-worker",
            "expected_state_version": 0,
            "lease_seconds": 60,
        },
    )
    assert claimed.status_code == 200
    owner_epoch = claimed.json()["outcome"]["owner_epoch"]

    started = client.post(
        "/api/research/tasks/api-task/commands",
        json={
            "kind": "start_attempt",
            "command_id": "start-api",
            "owner_id": "api-worker",
            "owner_epoch": owner_epoch,
            "expected_state_version": 1,
        },
    )
    assert started.status_code == 200
    attempt_id = started.json()["outcome"]["attempt_id"]

    checkpoint = client.post(
        "/api/research/tasks/api-task/commands",
        json={
            "kind": "checkpoint",
            "command_id": "checkpoint-api",
            "owner_id": "api-worker",
            "owner_epoch": owner_epoch,
            "attempt_id": attempt_id,
            "expected_state_version": 2,
            "state_payload": {"step": "safe"},
        },
    )
    assert checkpoint.status_code == 200
    checkpoint_id = checkpoint.json()["outcome"]["checkpoint_id"]

    terminal = client.post(
        "/api/research/tasks/api-task/commands",
        json={
            "kind": "complete_task",
            "command_id": "complete-api",
            "owner_id": "api-worker",
            "owner_epoch": owner_epoch,
            "attempt_id": attempt_id,
            "expected_state_version": 3,
            "expected_checkpoint_id": checkpoint_id,
            "answer_status": "valid_success",
            "termination_reason": "answer_ready",
            "failure_class": "none",
            "reason_detail": "deterministic stage 1 completion",
        },
    )
    assert terminal.status_code == 200
    assert terminal.json()["research"]["task"]["status"] == "terminal"

    status = client.get("/api/research/tasks/api-task/status")
    assert status.status_code == 200
    assert status.json()["task"]["terminal_result_id"]

    traces = client.get("/api/research/tasks/api-task/traces")
    assert traces.status_code == 200
    assert traces.json()["traces"][0]["termination_reason"] == "answer_ready"
    assert traces.json()["events"][-1]["event_type"] == "task_terminal_result_committed"


def test_research_api_conflicts_are_explicit_and_not_found_is_404(app_paths) -> None:
    client = TestClient(create_web_app(Application(app_paths)))
    missing = client.get("/api/research/tasks/missing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "research_not_found"

    payload = {
        "task_id": "api-task",
        "command_id": "create-api",
        "objective": "原目标",
    }
    assert client.post("/api/research/tasks", json=payload).status_code == 200
    mismatch = client.post(
        "/api/research/tasks", json={**payload, "objective": "不同目标"}
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "research_conflict"


def test_research_api_terminal_retry_returns_child_task(app_paths) -> None:
    core = Application(app_paths)
    client = TestClient(create_web_app(core))
    core.research.create_task(
        task_id="parent",
        command_id="create-parent",
        objective="parent goal",
    )
    owner = core.research.claim_owner(
        task_id="parent",
        command_id="claim-parent",
        owner_id="worker",
        expected_state_version=0,
        lease_seconds=60,
    )
    attempt = core.research.start_attempt(
        task_id="parent",
        command_id="start-parent",
        owner_id="worker",
        owner_epoch=owner["owner_epoch"],
        expected_state_version=1,
    )
    core.research.complete_attempt(
        task_id="parent",
        attempt_id=attempt["attempt_id"],
        command_id="complete-parent",
        owner_id="worker",
        owner_epoch=owner["owner_epoch"],
        expected_state_version=2,
        answer_status=AnswerStatus.VALID_SUCCESS,
        termination_reason=TerminationReason.ANSWER_READY,
        failure_class=FailureClass.NONE,
        reason_detail="done",
        task_terminal=True,
    )

    response = client.post(
        "/api/research/tasks/parent/commands",
        json={"kind": "retry", "command_id": "retry-parent"},
    )
    assert response.status_code == 200
    child = response.json()["research"]["task"]
    assert child["task_id"] != "parent"
    assert child["parent_task_id"] == "parent"
    assert core.research.get_task("parent")["task"]["status"] == "terminal"
