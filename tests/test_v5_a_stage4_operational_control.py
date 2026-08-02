from __future__ import annotations

import hashlib
import json
import multiprocessing
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.db import Database, SCHEMA_VERSION
from shiliu.research import (
    AnswerStatus,
    FailureClass,
    ResearchConflict,
    ResearchForbidden,
    ResearchNotFound,
    SimulatedCrash,
    TerminationReason,
)
from shiliu.research.control_contracts import (
    ControlCommandRequest,
    CreateInputRequest,
    DeriveTaskRequest,
    HumanDecisionRequest,
    ResolveSideEffectRequest,
)
from shiliu.research.control_service import (
    ControlAuthorizationPolicy,
    ResearchControlService,
)
from shiliu.research.schema import CONSTRAINT_SPEC_SCHEMA_VERSION
from shiliu.research.service import ResearchTaskService
from shiliu.web import create_web_app


STAGE4_TABLES = {
    "research_control_requests",
    "research_control_dispositions",
    "research_input_requests",
    "research_input_dispositions",
    "research_human_decisions",
    "research_human_constraint_observations",
    "research_side_effect_resolutions",
    "research_task_derivations",
}


def _bootstrap(core: Application, task_id: str = "control-task") -> dict:
    core.research.create_task(
        command_id=f"{task_id}:create",
        task_id=task_id,
        objective="研究可恢复控制",
        success_constraints=["保持历史不可变"],
        evidence_policy={"authority": "live_current_exact_replay"},
    )
    claim = core.research.claim_owner(
        task_id=task_id,
        command_id=f"{task_id}:claim",
        owner_id="worker-a",
        expected_state_version=0,
        lease_seconds=300,
    )
    attempt = core.research.start_attempt(
        task_id=task_id,
        command_id=f"{task_id}:start",
        owner_id="worker-a",
        owner_epoch=claim["owner_epoch"],
        expected_state_version=claim["state_version"],
    )
    checkpoint = core.research.commit_checkpoint(
        task_id=task_id,
        attempt_id=attempt["attempt_id"],
        command_id=f"{task_id}:checkpoint",
        owner_id="worker-a",
        owner_epoch=claim["owner_epoch"],
        expected_state_version=attempt["state_version"],
        expected_checkpoint_id=None,
        state_payload={"phase": "durable", "budget": {"actions": 1}},
    )
    return {
        "task_id": task_id,
        "owner_id": "worker-a",
        "owner_epoch": claim["owner_epoch"],
        "attempt_id": attempt["attempt_id"],
        "checkpoint_id": checkpoint["checkpoint_id"],
        "state_version": checkpoint["state_version"],
    }


def _control(
    run: dict,
    command_id: str,
    kind: str,
    *,
    state_version: int | None = None,
    checkpoint_id: str | None = None,
    generation: int = 0,
) -> ControlCommandRequest:
    return ControlCommandRequest(
        command_id=command_id,
        kind=kind,
        expected_state_version=(
            run["state_version"] if state_version is None else state_version
        ),
        expected_checkpoint_id=(
            run["checkpoint_id"] if checkpoint_id is None else checkpoint_id
        ),
        expected_control_generation=generation,
        reason=f"{kind} requested",
    )


def _multiprocess_interrupt(
    database_path: str,
    task_id: str,
    request_payload: dict,
    principal_id: str,
    queue: multiprocessing.Queue,
) -> None:
    try:
        db = Database(Path(database_path))
        kernel = ResearchTaskService(db)
        service = ResearchControlService(db, kernel=kernel)
        outcome = service.apply_control(
            task_id,
            ControlCommandRequest.model_validate(request_payload),
            principal_id=principal_id,
        )
        queue.put(("ok", outcome["control_request_id"]))
    except Exception as exc:  # pragma: no cover - asserted through process result.
        queue.put(("error", type(exc).__name__))


def test_schema_10_adds_control_tables_to_temporary_schema9_database(app_paths) -> None:
    app_paths.database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(app_paths.database)
    connection.executescript(
        """
        CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO schema_meta(key, value) VALUES('schema_version', '9');
        CREATE TABLE research_tasks(
            task_id TEXT PRIMARY KEY, parent_task_id TEXT, status TEXT NOT NULL,
            active_goal_id TEXT, state_version INTEGER NOT NULL DEFAULT 0,
            owner_id TEXT, owner_epoch INTEGER NOT NULL DEFAULT 0,
            lease_until TEXT, terminal_result_id TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        """
    )
    connection.commit()
    connection.close()

    db = Database(app_paths.database)
    db.initialize()
    db.initialize()
    assert SCHEMA_VERSION == 10
    assert app_paths.database.with_name("shiliu.pre-v10.backup.db").is_file()
    with db.connect() as migrated:
        assert migrated.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0] == "10"
        columns = {
            str(row[1]) for row in migrated.execute("PRAGMA table_info(research_tasks)")
        }
        tables = {
            str(row[0])
            for row in migrated.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            )
        }
        assert migrated.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert migrated.execute("PRAGMA foreign_key_check").fetchall() == []
    assert "control_generation" in columns
    assert STAGE4_TABLES.issubset(tables)


def test_interrupt_fences_stale_worker_and_resume_keeps_attempt_and_budget(app_paths) -> None:
    core = Application(app_paths)
    run = _bootstrap(core)
    interrupted = core.research_control.apply_control(
        run["task_id"],
        _control(run, "interrupt-1", "interrupt"),
        principal_id="local_operator",
    )
    assert interrupted["outcome"] == "interrupted"
    assert interrupted["owner_epoch"] == 2
    with pytest.raises(ResearchConflict, match="stale owner"):
        core.research.commit_checkpoint(
            task_id=run["task_id"],
            attempt_id=run["attempt_id"],
            command_id="late-worker-write",
            owner_id="worker-a",
            owner_epoch=1,
            expected_state_version=interrupted["state_version"],
            expected_checkpoint_id=interrupted["checkpoint_id"],
            state_payload={"late": True},
        )

    restarted = ResearchControlService(core.db, kernel=core.research)
    resumed = restarted.apply_control(
        run["task_id"],
        _control(
            run,
            "resume-1",
            "resume",
            state_version=interrupted["state_version"],
            checkpoint_id=interrupted["checkpoint_id"],
            generation=interrupted["control_generation"],
        ),
        principal_id="local_operator",
    )
    state = core.research.get_task(run["task_id"])
    assert resumed["outcome"] == "resumed"
    assert state["task"]["status"] == "running"
    assert len(state["attempts"]) == 1
    assert state["attempts"][0]["attempt_id"] == run["attempt_id"]
    assert state["checkpoints"][0]["state_payload"] == state["checkpoints"][-1]["state_payload"]
    assert state["checkpoints"][0]["state_schema_version"] == state["checkpoints"][-1]["state_schema_version"]


def test_control_replay_payload_mismatch_and_fault_rollback(app_paths) -> None:
    core = Application(app_paths)
    run = _bootstrap(core, "control-replay")
    request = _control(run, "interrupt-replay", "interrupt")
    first = core.research_control.apply_control(
        run["task_id"], request, principal_id="local_operator"
    )
    replay = core.research_control.apply_control(
        run["task_id"], request, principal_id="local_operator"
    )
    assert replay["control_request_id"] == first["control_request_id"]
    assert replay["deduplicated"] is True
    with pytest.raises(ResearchConflict, match="payload hash"):
        core.research_control.apply_control(
            run["task_id"],
            request.model_copy(update={"reason": "different"}),
            principal_id="local_operator",
        )
    assert core.research.get_task(run["task_id"])["task"]["state_version"] == first["state_version"]

    other = _bootstrap(core, "control-fault")

    def fault(point: str) -> None:
        if point == "after_control_fence":
            raise SimulatedCrash(point)

    service = ResearchControlService(core.db, kernel=core.research, fault_injector=fault)
    with pytest.raises(SimulatedCrash):
        service.apply_control(
            other["task_id"],
            _control(other, "interrupt-fault", "interrupt"),
            principal_id="local_operator",
        )
    persisted = core.research.get_task(other["task_id"])
    assert persisted["task"]["state_version"] == other["state_version"]
    assert persisted["task"]["owner_epoch"] == 1
    assert service.get_status(other["task_id"])["control_requests"] == []


def test_multiprocess_interrupt_cas_has_one_winner(app_paths) -> None:
    core = Application(app_paths)
    run = _bootstrap(core, "control-process-race")
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    requests = [
        _control(run, f"process-interrupt-{index}", "interrupt").model_dump(mode="json")
        for index in range(2)
    ]
    processes = [
        context.Process(
            target=_multiprocess_interrupt,
            args=(
                str(app_paths.database),
                run["task_id"],
                request,
                "local_operator",
                queue,
            ),
        )
        for request in requests
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
        assert process.exitcode == 0
    outcomes = sorted(queue.get(timeout=2)[0] for _ in processes)
    assert outcomes == ["error", "ok"]
    status = core.research_control.get_status(run["task_id"])
    assert len(status["control_requests"]) == 1
    assert status["task"]["control_generation"] == 1


def test_server_owned_authority_rejects_forged_principal_and_api_role(app_paths) -> None:
    core = Application(app_paths)
    run = _bootstrap(core, "control-authority")
    policy = ControlAuthorizationPolicy(
        {"viewer": frozenset(), "operator": {"control:interrupt"}}
    )
    service = ResearchControlService(core.db, kernel=core.research, authorization=policy)
    with pytest.raises(ResearchForbidden):
        service.apply_control(
            run["task_id"],
            _control(run, "forged-direct", "interrupt"),
            principal_id="forged_admin",
        )
    assert service.get_status(run["task_id"])["control_requests"] == []

    client = TestClient(create_web_app(core))
    payload = _control(run, "forged-api", "interrupt").model_dump(mode="json")
    payload["actor_id"] = "admin"
    payload["role"] = "root"
    response = client.post(
        f"/api/research/tasks/{run['task_id']}/control", json=payload
    )
    assert response.status_code == 422
    assert service.get_status(run["task_id"])["control_requests"] == []


def test_waiting_input_clarification_is_exact_once_and_revises_goal(app_paths) -> None:
    core = Application(app_paths)
    run = _bootstrap(core, "input-clarification")
    with core.db.connect() as connection:
        connection.execute(
            "UPDATE research_tasks SET status='waiting_user' WHERE task_id=?",
            (run["task_id"],),
        )
        connection.execute(
            "UPDATE research_attempts SET status='waiting_user' WHERE attempt_id=?",
            (run["attempt_id"],),
        )
    opened = core.research_control.create_input(
        run["task_id"],
        CreateInputRequest(
            command_id="open-clarification",
            attempt_id=run["attempt_id"],
            owner_id="worker-a",
            owner_epoch=1,
            expected_state_version=run["state_version"],
            expected_checkpoint_id=run["checkpoint_id"],
            kind="clarification",
            prompt="请澄清目标",
            response_schema={"required": ["objective"]},
        ),
        principal_id="local_operator",
    )
    request = HumanDecisionRequest(
        command_id="answer-clarification",
        input_request_id=opened["input_request_id"],
        expected_state_version=opened["state_version"],
        expected_control_generation=0,
        decision_kind="clarify_goal",
        response={
            "objective": "研究可恢复控制并保留 lineage",
            "success_constraints": ["保留 lineage"],
            "evidence_policy": {"authority": "live_current_exact_replay"},
        },
    )
    decided = core.research_control.decide_input(
        run["task_id"], request, principal_id="local_operator"
    )
    restarted = ResearchControlService(core.db, kernel=core.research)
    replay = restarted.decide_input(
        run["task_id"], request, principal_id="local_operator"
    )
    assert replay["decision_id"] == decided["decision_id"]
    state = core.research.get_task(run["task_id"])
    assert [goal["revision"] for goal in state["goals"]] == [1, 2]
    assert state["attempts"][0]["status"] == "terminal"
    assert state["attempts"][1]["cause"] == "goal_revision"
    assert state["attempts"][1]["parent_attempt_id"] == run["attempt_id"]
    assert state["results"][0]["termination_reason"] == "goal_revised"
    with pytest.raises(ResearchConflict, match="payload hash"):
        restarted.decide_input(
            run["task_id"],
            request.model_copy(update={"response": {"objective": "rewrite history"}}),
            principal_id="local_operator",
        )


def test_arbitrary_factual_input_has_no_authority_but_registered_choice_does(app_paths) -> None:
    core = Application(app_paths)
    run = _bootstrap(core, "input-authority")
    with core.db.connect() as connection:
        connection.execute("UPDATE research_tasks SET status='waiting_user' WHERE task_id=?", (run["task_id"],))
        connection.execute("UPDATE research_attempts SET status='waiting_user' WHERE attempt_id=?", (run["attempt_id"],))
        goal_id = core.research.get_task(run["task_id"])["task"]["active_goal_id"]
        connection.execute(
            """
            INSERT INTO research_constraint_specs(
                constraint_id, constraint_schema_version, task_id, goal_id,
                goal_revision, ordinal, constraint_scope, original_text,
                normalized_text, constraint_kind, is_required,
                evaluator_policy_json, evaluator_policy_version,
                canonical_payload_hash, created_at
            ) VALUES('factual', ?, ?, ?, 1, 7, 'success_constraint',
                     '月球由奶酪构成', '月球由奶酪构成', 'natural_language', 1,
                     '{}', 'unregistered-v1', 'factual-hash', '2026-08-03T00:00:00+00:00')
            """,
            (CONSTRAINT_SPEC_SCHEMA_VERSION, run["task_id"], goal_id),
        )
    with pytest.raises(ResearchForbidden):
        core.research_control.create_input(
            run["task_id"],
            CreateInputRequest(
                command_id="fake-factual-approval",
                attempt_id=run["attempt_id"], owner_id="worker-a", owner_epoch=1,
                expected_state_version=run["state_version"],
                expected_checkpoint_id=run["checkpoint_id"],
                kind="constraint_choice", prompt="批准事实？",
                choices=["satisfied"], constraint_id="factual",
            ),
            principal_id="local_operator",
        )
    assert core.research_control.get_status(run["task_id"])["input_requests"] == []

    with core.db.connect() as connection:
        goal_id = core.research.get_task(run["task_id"])["task"]["active_goal_id"]
        policy = {
            "authority": "server_registry",
            "human_decidable": True,
            "allowed_human_options": ["keep", "revise"],
        }
        connection.execute(
            """
            INSERT INTO research_constraint_specs(
                constraint_id, constraint_schema_version, task_id, goal_id,
                goal_revision, ordinal, constraint_scope, original_text,
                normalized_text, constraint_kind, is_required,
                evaluator_policy_json, evaluator_policy_version,
                canonical_payload_hash, created_at
            ) VALUES('preference', ?, ?, ?, 1, 8, 'success_constraint',
                     '选择输出形式', '选择输出形式', 'natural_language', 1,
                     ?, 'human-choice-v1', 'preference-hash', '2026-08-03T00:00:00+00:00')
            """,
            (
                CONSTRAINT_SPEC_SCHEMA_VERSION,
                run["task_id"],
                goal_id,
                json.dumps(policy, ensure_ascii=False),
            ),
        )
    opened = core.research_control.create_input(
        run["task_id"],
        CreateInputRequest(
            command_id="open-preference", attempt_id=run["attempt_id"],
            owner_id="worker-a", owner_epoch=1,
            expected_state_version=run["state_version"],
            expected_checkpoint_id=run["checkpoint_id"],
            kind="constraint_choice", prompt="选择输出形式",
            choices=["keep", "revise"], constraint_id="preference",
        ),
        principal_id="local_operator",
    )
    decided = core.research_control.decide_input(
        run["task_id"],
        HumanDecisionRequest(
            command_id="choose-preference",
            input_request_id=opened["input_request_id"],
            expected_state_version=opened["state_version"],
            expected_control_generation=0,
            decision_kind="select_constraint_option",
            response={"selected_option": "keep"},
        ),
        principal_id="local_operator",
    )
    with core.db.connect() as connection:
        observation = connection.execute(
            "SELECT * FROM research_human_constraint_observations WHERE decision_id=?",
            (decided["decision_id"],),
        ).fetchone()
    assert observation["selected_option"] == "keep"


def test_cancel_preserves_partial_and_cancel_result_race_has_one_winner(app_paths) -> None:
    core = Application(app_paths)
    run = _bootstrap(core, "cancel-partial")
    with core.db.connect() as connection:
        connection.execute(
            """
            INSERT INTO research_provisional_artifacts(
                artifact_id, artifact_schema_version, task_id, goal_id,
                attempt_id, checkpoint_id, objective, answer_status,
                answer_blocks_json, limitations_json, evidence_set_fingerprint,
                evidence_use_ids_json,
                evidence_ids_json, validation_observation_ids_json,
                generation_policy_version, validator_policy_version,
                provider_side_effect_id, artifact_hash, created_at
            ) VALUES('partial-artifact', 'test-v1', ?, ?, ?, ?, 'objective',
                     'valid_partial', '[]', '[]', 'empty', '[]', '[]', '[]',
                     'test', 'test', NULL, 'hash', '2026-08-03T00:00:00+00:00')
            """,
            (
                run["task_id"],
                core.research.get_task(run["task_id"])["task"]["active_goal_id"],
                run["attempt_id"],
                run["checkpoint_id"],
            ),
        )

    def cancel():
        try:
            return core.research_control.apply_control(
                run["task_id"],
                _control(run, "cancel-race", "cancel"),
                principal_id="local_operator",
            )
        except ResearchConflict as exc:
            return exc

    def finish():
        try:
            return core.research.complete_attempt(
                task_id=run["task_id"], attempt_id=run["attempt_id"],
                command_id="success-race", owner_id="worker-a", owner_epoch=1,
                expected_state_version=run["state_version"],
                checkpoint_id=run["checkpoint_id"],
                answer_status=AnswerStatus.VALID_SUCCESS,
                termination_reason=TerminationReason.ANSWER_READY,
                failure_class=FailureClass.NONE,
                reason_detail="done", task_terminal=True,
            )
        except (ResearchConflict, TypeError, ValueError) as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [pool.submit(cancel), pool.submit(finish)]
        _ = [future.result() for future in outcomes]
    state = core.research.get_task(run["task_id"])
    assert state["task"]["status"] == "terminal"
    assert len([result for result in state["results"] if result["is_task_terminal"]]) == 1
    terminal = [result for result in state["results"] if result["is_task_terminal"]][0]
    if terminal["termination_reason"] == "cancelled":
        assert terminal["answer_status"] == "valid_partial"


def test_cancel_pending_unknown_requires_immutable_resolution_and_never_replays(app_paths) -> None:
    core = Application(app_paths)
    run = _bootstrap(core, "cancel-unknown")
    reserved = core.research.reserve_side_effect(
        task_id=run["task_id"], attempt_id=run["attempt_id"],
        command_id="reserve-unknown", owner_id="worker-a", owner_epoch=1,
        expected_state_version=run["state_version"], effect_kind="test_write",
        idempotency_key="unknown", request_payload={"value": 1},
    )
    started = core.research.transition_side_effect(
        task_id=run["task_id"], side_effect_id=reserved["side_effect_id"],
        command_id="start-unknown", owner_id="worker-a", owner_epoch=1,
        expected_state_version=reserved["state_version"], target_status="in_flight",
    )
    cancelled = core.research_control.apply_control(
        run["task_id"],
        _control(
            run, "cancel-unknown", "cancel",
            state_version=started["state_version"], generation=0,
        ),
        principal_id="local_operator",
    )
    assert cancelled["outcome"] == "cancel_pending"
    assert cancelled["unknown_side_effect_ids"] == [reserved["side_effect_id"]]
    with pytest.raises(ResearchConflict):
        core.research.transition_side_effect(
            task_id=run["task_id"], side_effect_id=reserved["side_effect_id"],
            command_id="stale-receipt", owner_id="worker-a", owner_epoch=1,
            expected_state_version=cancelled["state_version"], target_status="failed",
        )
    resolved = core.research_control.resolve_side_effect(
        run["task_id"],
        ResolveSideEffectRequest(
            command_id="resolve-unknown", side_effect_id=reserved["side_effect_id"],
            expected_state_version=cancelled["state_version"],
            expected_control_generation=cancelled["control_generation"],
            resolution="confirmed_failed", reason="operator verified no receipt",
        ),
        principal_id="local_operator",
    )
    assert resolved["outcome"] == "cancelled"
    assert core.research.get_task(run["task_id"])["task"]["status"] == "terminal"
    status = core.research_control.get_status(run["task_id"])
    assert len(status["side_effect_resolutions"]) == 1
    assert core.research.effect_adapter.calls == []


def test_side_effect_resolution_fault_rolls_back_fence_and_resolution(app_paths) -> None:
    core = Application(app_paths)
    run = _bootstrap(core, "resolution-fault")
    reserved = core.research.reserve_side_effect(
        task_id=run["task_id"], attempt_id=run["attempt_id"], command_id="reserve",
        owner_id="worker-a", owner_epoch=1, expected_state_version=run["state_version"],
        effect_kind="test", idempotency_key="key", request_payload={},
    )
    with core.db.connect() as connection:
        connection.execute(
            "UPDATE research_side_effects SET status='unknown' WHERE side_effect_id=?",
            (reserved["side_effect_id"],),
        )
        connection.execute(
            "UPDATE research_tasks SET status='blocked' WHERE task_id=?",
            (run["task_id"],),
        )

    def fault(point: str) -> None:
        if point == "after_side_effect_resolution_apply":
            raise SimulatedCrash(point)

    service = ResearchControlService(core.db, kernel=core.research, fault_injector=fault)
    with pytest.raises(SimulatedCrash):
        service.resolve_side_effect(
            run["task_id"],
            ResolveSideEffectRequest(
                command_id="resolution-fault", side_effect_id=reserved["side_effect_id"],
                expected_state_version=reserved["state_version"],
                expected_control_generation=0,
                resolution="confirmed_failed", reason="verified",
            ),
            principal_id="local_operator",
        )
    state = core.research.get_task(run["task_id"])
    assert state["task"]["control_generation"] == 0
    assert state["side_effects"][0]["status"] == "unknown"
    assert service.get_status(run["task_id"])["side_effect_resolutions"] == []


def test_replay_and_branch_create_isolated_children_without_tool_or_effect_replay(app_paths) -> None:
    core = Application(app_paths)
    run = _bootstrap(core, "derive-source")
    before_source = core.research.get_task(run["task_id"])
    replay_request = DeriveTaskRequest(
        command_id="derive-replay", kind="replay",
        source_checkpoint_id=run["checkpoint_id"],
    )
    replay = core.research_control.derive_task(
        run["task_id"], replay_request, principal_id="local_operator"
    )
    replay_again = core.research_control.derive_task(
        run["task_id"], replay_request, principal_id="local_operator"
    )
    branch = core.research_control.derive_task(
        run["task_id"],
        DeriveTaskRequest(
            command_id="derive-branch", kind="branch",
            source_checkpoint_id=run["checkpoint_id"],
            objective="研究隔离 branch",
        ),
        principal_id="local_operator",
    )
    assert replay_again["derivation_id"] == replay["derivation_id"]
    assert replay["task_id"] != branch["task_id"]
    assert core.research.get_task(run["task_id"]) == before_source
    replay_state = core.research.get_task(replay["task_id"])
    branch_state = core.research.get_task(branch["task_id"])
    assert replay_state["attempts"][0]["cause"] == "replay"
    assert branch_state["attempts"][0]["cause"] == "branch"
    assert replay_state["checkpoints"][0]["state_hash"] == before_source["checkpoints"][0]["state_hash"]
    assert replay_state["evidence_uses"] == []
    assert branch_state["evidence_uses"] == []
    assert replay_state["side_effects"] == []
    assert branch_state["side_effects"] == []
    assert core.research.effect_adapter.calls == []


def test_control_api_status_interrupt_and_server_principal_boundary(app_paths) -> None:
    core = Application(app_paths)
    run = _bootstrap(core, "control-api")
    client = TestClient(create_web_app(core))
    response = client.post(
        f"/api/research/tasks/{run['task_id']}/control",
        json=_control(run, "api-interrupt", "interrupt").model_dump(mode="json"),
    )
    assert response.status_code == 200
    assert response.json()["outcome"]["outcome"] == "interrupted"
    status = client.get(f"/api/research/tasks/{run['task_id']}/control")
    assert status.status_code == 200
    control = status.json()["control"]
    assert control["task"]["control_generation"] == 1
    assert control["control_requests"][0]["principal_id"] == "local_operator"


def test_audit_metadata_cannot_upgrade_restricted_server_principal(app_paths) -> None:
    core = Application(app_paths)
    run = _bootstrap(core, "audit-authority")
    service = ResearchControlService(
        core.db,
        kernel=core.research,
        authorization=ControlAuthorizationPolicy({"viewer": frozenset()}),
    )
    forged = _control(run, "audit-forgery", "interrupt").model_copy(
        update={
            "audit_actor_metadata": {
                "actor_id": "root",
                "role": "admin",
                "capability": "control:interrupt",
            }
        }
    )
    with pytest.raises(ResearchForbidden):
        service.apply_control(
            run["task_id"], forged, principal_id="viewer"
        )
    assert service.get_status(run["task_id"])["control_requests"] == []


def test_cancel_reserved_effect_prevents_execution_and_terminalizes(app_paths) -> None:
    core = Application(app_paths)
    run = _bootstrap(core, "cancel-reserved")
    reserved = core.research.reserve_side_effect(
        task_id=run["task_id"], attempt_id=run["attempt_id"],
        command_id="reserve-before-cancel", owner_id="worker-a", owner_epoch=1,
        expected_state_version=run["state_version"], effect_kind="write",
        idempotency_key="reserved", request_payload={"value": 1},
    )
    cancelled = core.research_control.apply_control(
        run["task_id"],
        _control(
            run, "cancel-reserved", "cancel",
            state_version=reserved["state_version"], generation=0,
        ),
        principal_id="local_operator",
    )
    assert cancelled["outcome"] == "cancelled"
    state = core.research.get_task(run["task_id"])
    assert state["side_effects"][0]["status"] == "failed"
    assert state["task"]["status"] == "terminal"
    assert core.research.effect_adapter.calls == []


def test_bounds_fail_closed_before_any_persistent_mutation(app_paths) -> None:
    core = Application(app_paths)
    run = _bootstrap(core, "control-bounds")
    before = core.research.get_task(run["task_id"])
    with pytest.raises(ResearchConflict):
        # Validly bounded model, but deliberately stale checkpoint must fail before write.
        core.research_control.apply_control(
            run["task_id"],
            _control(
                run, "bad-checkpoint", "interrupt",
                checkpoint_id="checkpoint_missing",
            ),
            principal_id="local_operator",
        )
    assert core.research.get_task(run["task_id"]) == before
    client = TestClient(create_web_app(core))
    oversized = _control(run, "oversized-reason", "interrupt").model_dump(mode="json")
    oversized["reason"] = "x" * 1001
    response = client.post(
        f"/api/research/tasks/{run['task_id']}/control", json=oversized
    )
    assert response.status_code == 422
    assert core.research.get_task(run["task_id"]) == before


def test_derivation_fault_rolls_back_child_and_source_remains_immutable(app_paths) -> None:
    core = Application(app_paths)
    run = _bootstrap(core, "derive-fault-source")
    before = core.research.get_task(run["task_id"])

    def fault(point: str) -> None:
        if point == "after_task_derivation_apply":
            raise SimulatedCrash(point)

    service = ResearchControlService(core.db, kernel=core.research, fault_injector=fault)
    request = DeriveTaskRequest(
        command_id="derive-fault", kind="replay",
        source_checkpoint_id=run["checkpoint_id"], child_task_id="derive-fault-child",
    )
    with pytest.raises(SimulatedCrash):
        service.derive_task(
            run["task_id"], request, principal_id="local_operator"
        )
    assert core.research.get_task(run["task_id"]) == before
    with pytest.raises(ResearchNotFound):
        core.research.get_task("derive-fault-child")


def test_derived_child_can_be_claimed_and_resumed_without_source_mutation(app_paths) -> None:
    core = Application(app_paths)
    run = _bootstrap(core, "derive-runnable-source")
    before = core.research.get_task(run["task_id"])
    child = core.research_control.derive_task(
        run["task_id"],
        DeriveTaskRequest(
            command_id="derive-runnable", kind="replay",
            source_checkpoint_id=run["checkpoint_id"],
        ),
        principal_id="local_operator",
    )
    claim = core.research.claim_owner(
        task_id=child["task_id"], command_id="claim-derived",
        owner_id="derived-worker", expected_state_version=0, lease_seconds=300,
    )
    resumed = core.research.resume_attempt(
        task_id=child["task_id"], attempt_id=child["attempt_id"],
        command_id="resume-derived", owner_id="derived-worker",
        owner_epoch=claim["owner_epoch"],
        expected_state_version=claim["state_version"],
        expected_checkpoint_id=child["checkpoint_id"],
    )
    assert resumed["state_version"] == 2
    assert core.research.get_task(child["task_id"])["task"]["status"] == "running"
    assert core.research.get_task(run["task_id"]) == before


def test_side_effect_resolution_race_commits_one_immutable_decision(app_paths) -> None:
    core = Application(app_paths)
    run = _bootstrap(core, "resolution-race")
    reserved = core.research.reserve_side_effect(
        task_id=run["task_id"], attempt_id=run["attempt_id"], command_id="reserve-race",
        owner_id="worker-a", owner_epoch=1, expected_state_version=run["state_version"],
        effect_kind="test", idempotency_key="race", request_payload={},
    )
    with core.db.connect() as connection:
        connection.execute("UPDATE research_side_effects SET status='unknown' WHERE side_effect_id=?", (reserved["side_effect_id"],))
        connection.execute("UPDATE research_tasks SET status='blocked' WHERE task_id=?", (run["task_id"],))

    def resolve(index: int):
        try:
            return core.research_control.resolve_side_effect(
                run["task_id"],
                ResolveSideEffectRequest(
                    command_id=f"resolve-race-{index}",
                    side_effect_id=reserved["side_effect_id"],
                    expected_state_version=reserved["state_version"],
                    expected_control_generation=0,
                    resolution="confirmed_failed", reason="verified",
                ),
                principal_id="local_operator",
            )
        except ResearchConflict as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(resolve, index) for index in range(2)]
        outcomes = [future.result() for future in futures]
    assert sum(isinstance(value, dict) for value in outcomes) == 1
    status = core.research_control.get_status(run["task_id"])
    assert len(status["side_effect_resolutions"]) == 1


def test_stage4_rows_are_immutable_or_append_only_at_database_boundary(app_paths) -> None:
    core = Application(app_paths)
    run = _bootstrap(core, "immutable-control")
    outcome = core.research_control.apply_control(
        run["task_id"], _control(run, "immutable-interrupt", "interrupt"),
        principal_id="local_operator",
    )
    with core.db.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE research_control_requests SET principal_id='forged' "
                "WHERE control_request_id=?",
                (outcome["control_request_id"],),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "DELETE FROM research_control_dispositions WHERE control_request_id=?",
                (outcome["control_request_id"],),
            )
