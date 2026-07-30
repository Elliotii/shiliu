from __future__ import annotations

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from shiliu.db import Database, SCHEMA_VERSION
from shiliu.research import (
    AnswerStatus,
    AttemptCause,
    DeterministicEffectAdapter,
    FailureClass,
    ResearchConflict,
    ResearchUnsafeState,
    ResearchValidationError,
    SimulatedCrash,
    TaskStatus,
    TerminationReason,
)
from shiliu.research.service import ResearchTaskService


RESEARCH_TABLES = {
    "research_tasks",
    "research_goals",
    "research_attempts",
    "research_checkpoints",
    "research_events",
    "research_traces",
    "research_results",
    "research_command_receipts",
    "research_side_effects",
}


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 7, 31, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


@pytest.fixture
def research(app_paths):
    db = Database(app_paths.database)
    db.initialize()
    clock = MutableClock()
    adapter = DeterministicEffectAdapter()
    service = ResearchTaskService(db, clock=clock, effect_adapter=adapter)
    return db, clock, adapter, service


def create_task(
    service: ResearchTaskService,
    *,
    command_id: str = "create-1",
    task_id: str = "task-1",
) -> dict:
    return service.create_task(
        command_id=command_id,
        task_id=task_id,
        objective="研究稳定任务内核",
        success_constraints=["可恢复", "不重复副作用"],
        evidence_policy={"authority": "transcript"},
    )


def claim(
    service: ResearchTaskService,
    task_id: str = "task-1",
    *,
    owner_id: str = "worker-a",
    command_id: str = "claim-1",
    expected: int = 0,
    lease_seconds: int = 30,
) -> dict:
    return service.claim_owner(
        task_id=task_id,
        command_id=command_id,
        owner_id=owner_id,
        expected_state_version=expected,
        lease_seconds=lease_seconds,
    )


def start(
    service: ResearchTaskService,
    task_id: str = "task-1",
    *,
    owner_id: str = "worker-a",
    owner_epoch: int = 1,
    command_id: str = "start-1",
    expected: int = 1,
    cause: AttemptCause = AttemptCause.INITIAL,
    parent_attempt_id: str | None = None,
) -> dict:
    return service.start_attempt(
        task_id=task_id,
        command_id=command_id,
        owner_id=owner_id,
        owner_epoch=owner_epoch,
        expected_state_version=expected,
        cause=cause,
        parent_attempt_id=parent_attempt_id,
    )


def bootstrap(service: ResearchTaskService, task_id: str = "task-1") -> dict:
    create_task(service, task_id=task_id, command_id=f"create:{task_id}")
    claim(service, task_id, command_id=f"claim:{task_id}")
    return start(service, task_id, command_id=f"start:{task_id}")


def task_version(service: ResearchTaskService, task_id: str = "task-1") -> int:
    return int(service.get_task(task_id)["task"]["state_version"])


def test_schema_8_preserves_stage1_and_migrates_temporary_database_idempotently(
    app_paths,
) -> None:
    app_paths.database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(app_paths.database)
    connection.executescript(
        """
        CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO schema_meta(key, value) VALUES('schema_version', '6');
        """
    )
    connection.commit()
    connection.close()

    db = Database(app_paths.database)
    db.initialize()
    db.initialize()

    assert SCHEMA_VERSION == 8
    assert app_paths.database.with_name("shiliu.pre-v8.backup.db").is_file()
    with db.connect() as migrated:
        version = migrated.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
        tables = {
            str(row[0])
            for row in migrated.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            ).fetchall()
        }
        integrity = migrated.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_violations = migrated.execute("PRAGMA foreign_key_check").fetchall()
    assert version == "8"
    assert RESEARCH_TABLES.issubset(tables)
    assert integrity == "ok"
    assert foreign_key_violations == []


def test_temp_migration_does_not_touch_unrelated_sentinel(app_paths) -> None:
    sentinel = app_paths.state_dir / "live-db-sentinel"
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_bytes(b"must remain unchanged")
    before = (sentinel.stat().st_mtime_ns, hashlib.sha256(sentinel.read_bytes()).hexdigest())

    Database(app_paths.database).initialize()

    after = (sentinel.stat().st_mtime_ns, hashlib.sha256(sentinel.read_bytes()).hexdigest())
    assert after == before


def test_create_task_is_atomic_and_entities_have_distinct_ids(research) -> None:
    _db, _clock, _adapter, service = research
    outcome = create_task(service)
    state = service.get_task("task-1")

    assert state["task"]["status"] == "ready"
    assert outcome["task_id"] == "task-1"
    ids = {
        state["task"]["task_id"],
        state["goals"][0]["goal_id"],
        state["events"][0]["event_id"],
        state["command_receipts"][0]["receipt_id"],
    }
    assert len(ids) == 4
    assert state["task"]["active_goal_id"] == state["goals"][0]["goal_id"]
    assert state["goals"][0]["created_by_event_id"] == state["events"][0]["event_id"]


def test_all_stage1_entity_id_namespaces_remain_distinct(research) -> None:
    _db, _clock, _adapter, service = research
    attempt = bootstrap(service)
    checkpoint = service.commit_checkpoint(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="checkpoint-identity",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        expected_checkpoint_id=None,
        state_payload={"identity": True},
    )
    effect = service.execute_deterministic_side_effect(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="effect-identity",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=checkpoint["state_version"],
        effect_kind="identity_probe",
        idempotency_key="identity-key",
        request_payload={},
    )
    service.complete_attempt(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="result-identity",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=effect["state_version"],
        checkpoint_id=checkpoint["checkpoint_id"],
        answer_status=AnswerStatus.VALID_SUCCESS,
        termination_reason=TerminationReason.ANSWER_READY,
        failure_class=FailureClass.NONE,
        reason_detail="identity coverage",
        task_terminal=True,
    )
    state = service.get_task("task-1")
    entity_ids = {
        state["task"]["task_id"],
        state["goals"][0]["goal_id"],
        state["attempts"][0]["attempt_id"],
        state["checkpoints"][0]["checkpoint_id"],
        state["events"][0]["event_id"],
        state["traces"][0]["trace_id"],
        state["results"][0]["result_id"],
        state["command_receipts"][0]["receipt_id"],
        state["side_effects"][0]["side_effect_id"],
    }
    assert len(entity_ids) == len(RESEARCH_TABLES)


def test_create_fault_rolls_back_task_goal_event_and_receipt(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()

    def fault(point: str) -> None:
        if point == "after_task_insert":
            raise SimulatedCrash(point)

    service = ResearchTaskService(db, fault_injector=fault)
    with pytest.raises(SimulatedCrash):
        create_task(service)

    with db.connect() as connection:
        for table in (
            "research_tasks",
            "research_goals",
            "research_events",
            "research_command_receipts",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_command_dedupe_returns_same_response_and_payload_mismatch_fails_closed(
    research,
) -> None:
    _db, _clock, _adapter, service = research
    first = create_task(service)
    second = create_task(service)
    assert second == first
    receipt_before = service.get_task("task-1")["command_receipts"][0]

    with pytest.raises(ResearchConflict, match="payload hash"):
        service.create_task(
            command_id="create-1",
            task_id="task-1",
            objective="不同目标",
        )
    state = service.get_task("task-1")
    assert state["command_receipts"] == [receipt_before]
    assert state["events"][-1]["event_type"] == "command_payload_mismatch_rejected"


def test_active_owner_cannot_be_taken_over_and_renew_is_fenced(research) -> None:
    _db, _clock, _adapter, service = research
    create_task(service)
    owned = claim(service)

    with pytest.raises(ResearchConflict, match="active owner"):
        claim(
            service,
            owner_id="worker-b",
            command_id="claim-b",
            expected=owned["state_version"],
        )

    renewed = service.renew_owner(
        task_id="task-1",
        command_id="renew-a",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=owned["state_version"],
        lease_seconds=60,
    )
    assert renewed["owner_epoch"] == 1
    with pytest.raises(ResearchConflict):
        service.renew_owner(
            task_id="task-1",
            command_id="renew-stale",
            owner_id="worker-a",
            owner_epoch=2,
            expected_state_version=renewed["state_version"],
            lease_seconds=60,
        )


def test_takeover_increments_epoch_and_stale_worker_cannot_checkpoint(research) -> None:
    _db, clock, _adapter, service = research
    attempt = bootstrap(service)
    clock.advance(31)
    takeover = claim(
        service,
        owner_id="worker-b",
        command_id="claim-b",
        expected=2,
    )
    assert takeover["owner_epoch"] == 2

    with pytest.raises(ResearchConflict, match="owner fence"):
        service.commit_checkpoint(
            task_id="task-1",
            attempt_id=attempt["attempt_id"],
            command_id="checkpoint-stale",
            owner_id="worker-a",
            owner_epoch=1,
            expected_state_version=3,
            expected_checkpoint_id=None,
            state_payload={"step": 1},
        )

    checkpoint = service.commit_checkpoint(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="checkpoint-new-owner",
        owner_id="worker-b",
        owner_epoch=2,
        expected_state_version=3,
        expected_checkpoint_id=None,
        state_payload={"step": 1},
    )
    assert checkpoint["state_version"] == 4


def test_takeover_blocks_stale_owner_even_on_command_receipt_replay(research) -> None:
    _db, clock, _adapter, service = research
    attempt = bootstrap(service)
    original = service.commit_checkpoint(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="checkpoint-before-takeover",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        expected_checkpoint_id=None,
        state_payload={"step": 1},
    )
    clock.advance(31)
    claim(
        service,
        owner_id="worker-b",
        command_id="claim-b",
        expected=original["state_version"],
    )

    with pytest.raises(ResearchConflict, match="owner fence"):
        service.commit_checkpoint(
            task_id="task-1",
            attempt_id=attempt["attempt_id"],
            command_id="checkpoint-before-takeover",
            owner_id="worker-a",
            owner_epoch=1,
            expected_state_version=2,
            expected_checkpoint_id=None,
            state_payload={"step": 1},
        )


def test_concurrent_owner_claim_has_one_winner(research) -> None:
    _db, _clock, _adapter, service = research
    create_task(service)

    def run(owner: str):
        try:
            return claim(
                service,
                owner_id=owner,
                command_id=f"claim:{owner}",
                expected=0,
            )
        except ResearchConflict as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ["worker-a", "worker-b"]))

    assert sum(isinstance(value, dict) for value in results) == 1
    assert sum(isinstance(value, ResearchConflict) for value in results) == 1
    assert service.get_task("task-1")["task"]["owner_epoch"] == 1


def test_takeover_fault_rolls_back_epoch_owner_event_and_receipt(research) -> None:
    db, clock, adapter, service = research
    bootstrap(service)
    clock.advance(31)

    def fault(point: str) -> None:
        if point == "after_owner_claim":
            raise SimulatedCrash(point)

    crashing = ResearchTaskService(
        db, clock=clock, effect_adapter=adapter, fault_injector=fault
    )
    with pytest.raises(SimulatedCrash):
        claim(
            crashing,
            owner_id="worker-b",
            command_id="crashing-takeover",
            expected=2,
        )
    after_crash = service.get_task("task-1")
    assert after_crash["task"]["owner_id"] == "worker-a"
    assert after_crash["task"]["owner_epoch"] == 1
    assert after_crash["task"]["state_version"] == 2
    assert all(
        receipt["command_id"] != "crashing-takeover"
        for receipt in after_crash["command_receipts"]
    )

    takeover = claim(
        service,
        owner_id="worker-b",
        command_id="successful-takeover",
        expected=2,
    )
    assert takeover["owner_epoch"] == 2


def test_reserved_side_effect_rebinds_atomically_on_takeover_and_executes_once(
    research,
) -> None:
    db, clock, adapter, service = research
    attempt = bootstrap(service)
    reserved = service.reserve_side_effect(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="reserve-old-owner",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        effect_kind="test_write",
        idempotency_key="rebind-key",
        request_payload={"value": 1},
    )
    clock.advance(31)

    def fault(point: str) -> None:
        if point == "after_owner_claim":
            raise SimulatedCrash(point)

    crashing = ResearchTaskService(
        db, clock=clock, effect_adapter=adapter, fault_injector=fault
    )
    with pytest.raises(SimulatedCrash):
        claim(
            crashing,
            owner_id="worker-b",
            command_id="takeover-rebind-crash",
            expected=reserved["state_version"],
        )
    after_crash = service.get_task("task-1")
    assert after_crash["task"]["owner_id"] == "worker-a"
    assert after_crash["task"]["owner_epoch"] == 1
    assert after_crash["task"]["state_version"] == reserved["state_version"]
    assert after_crash["side_effects"][0]["owner_epoch"] == 1
    assert all(
        event["event_type"] != "side_effect_reserved_rebound"
        for event in after_crash["events"]
    )

    takeover = claim(
        service,
        owner_id="worker-b",
        command_id="takeover-rebind",
        expected=reserved["state_version"],
    )
    assert takeover["owner_epoch"] == 2
    assert takeover["rebound_reserved_side_effect_ids"] == [
        reserved["side_effect_id"]
    ]
    assert (
        claim(
            service,
            owner_id="worker-b",
            command_id="takeover-rebind",
            expected=reserved["state_version"],
        )
        == takeover
    )
    rebound = service.get_task("task-1")
    assert rebound["side_effects"][0]["owner_epoch"] == 2
    assert rebound["side_effects"][0]["status"] == "reserved"
    assert rebound["events"][-2]["event_type"] == "side_effect_reserved_rebound"

    with pytest.raises(ResearchConflict, match="owner fence"):
        service.transition_side_effect(
            task_id="task-1",
            side_effect_id=reserved["side_effect_id"],
            command_id="stale-start-after-rebind",
            owner_id="worker-a",
            owner_epoch=1,
            expected_state_version=takeover["state_version"],
            target_status="in_flight",
        )

    completed = service.execute_deterministic_side_effect(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="continue-rebound-effect",
        owner_id="worker-b",
        owner_epoch=2,
        expected_state_version=takeover["state_version"],
        effect_kind="test_write",
        idempotency_key="rebind-key",
        request_payload={"value": 1},
    )
    replay = service.execute_deterministic_side_effect(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="continue-rebound-effect",
        owner_id="worker-b",
        owner_epoch=2,
        expected_state_version=takeover["state_version"],
        effect_kind="test_write",
        idempotency_key="rebind-key",
        request_payload={"value": 1},
    )
    assert completed["status"] == "succeeded"
    assert replay["deduplicated"] is True
    assert len(adapter.calls) == 1
    state = service.get_task("task-1")
    assert len(state["side_effects"]) == 1
    assert state["side_effects"][0]["owner_epoch"] == 2

    with pytest.raises(ResearchUnsafeState, match="request hash"):
        service.reserve_side_effect(
            task_id="task-1",
            attempt_id=attempt["attempt_id"],
            command_id="rebound-hash-mismatch",
            owner_id="worker-b",
            owner_epoch=2,
            expected_state_version=completed["state_version"],
            effect_kind="test_write",
            idempotency_key="rebind-key",
            request_payload={"value": 2},
        )
    assert len(service.get_task("task-1")["side_effects"]) == 1


def test_concurrent_rebound_reserved_effect_continuation_has_one_execution(
    research,
) -> None:
    _db, clock, adapter, service = research
    attempt = bootstrap(service)
    reserved = service.reserve_side_effect(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="reserve-before-concurrent-takeover",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        effect_kind="test_write",
        idempotency_key="concurrent-rebind-key",
        request_payload={"same": True},
    )
    clock.advance(31)
    takeover = claim(
        service,
        owner_id="worker-b",
        command_id="concurrent-takeover",
        expected=reserved["state_version"],
    )

    def execute(command_id: str):
        try:
            return service.execute_deterministic_side_effect(
                task_id="task-1",
                attempt_id=attempt["attempt_id"],
                command_id=command_id,
                owner_id="worker-b",
                owner_epoch=2,
                expected_state_version=takeover["state_version"],
                effect_kind="test_write",
                idempotency_key="concurrent-rebind-key",
                request_payload={"same": True},
            )
        except ResearchConflict as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(execute, ["continue-a", "continue-b"]))
    assert sum(isinstance(value, dict) for value in values) == 1
    assert sum(isinstance(value, ResearchConflict) for value in values) == 1
    assert len(adapter.calls) == 1
    assert len(service.get_task("task-1")["side_effects"]) == 1


def test_stale_owner_cannot_commit_result_or_reserve_side_effect(research) -> None:
    _db, clock, _adapter, service = research
    attempt = bootstrap(service)
    clock.advance(31)
    takeover = claim(
        service,
        owner_id="worker-b",
        command_id="takeover-for-stale-mutations",
        expected=2,
    )

    with pytest.raises(ResearchConflict, match="owner fence"):
        service.complete_attempt(
            task_id="task-1",
            attempt_id=attempt["attempt_id"],
            command_id="stale-result",
            owner_id="worker-a",
            owner_epoch=1,
            expected_state_version=takeover["state_version"],
            answer_status=AnswerStatus.NOT_PRODUCED,
            termination_reason=TerminationReason.IMPLEMENTATION_ERROR,
            failure_class=FailureClass.IMPLEMENTATION_FAILURE,
            reason_detail="must be fenced",
            task_terminal=True,
        )
    with pytest.raises(ResearchConflict, match="owner fence"):
        service.reserve_side_effect(
            task_id="task-1",
            attempt_id=attempt["attempt_id"],
            command_id="stale-reserve",
            owner_id="worker-a",
            owner_epoch=1,
            expected_state_version=takeover["state_version"],
            effect_kind="test_write",
            idempotency_key="stale-key",
            request_payload={},
        )
    state = service.get_task("task-1")
    assert state["results"] == []
    assert state["side_effects"] == []


def test_checkpoint_resume_and_strict_lineage_survive_restart(research) -> None:
    db, _clock, _adapter, service = research
    attempt = bootstrap(service)
    first = service.commit_checkpoint(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="checkpoint-1",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        expected_checkpoint_id=None,
        state_payload={"verified": ["segment-1"]},
    )
    second = service.resume_attempt(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="resume-1",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=3,
        expected_checkpoint_id=first["checkpoint_id"],
    )

    restarted = ResearchTaskService(db)
    assert restarted.checkpoint_lineage(second["checkpoint_id"]) == [
        second["checkpoint_id"],
        first["checkpoint_id"],
    ]
    state = restarted.get_task("task-1")
    assert state["task"]["status"] == "running"
    assert state["checkpoints"][1]["state_payload"] == {"verified": ["segment-1"]}
    assert state["events"][-1]["event_type"] == "attempt_resumed"


def test_start_resume_and_retry_command_replays_are_semantically_idempotent(
    research,
) -> None:
    _db, _clock, _adapter, service = research
    create_task(service)
    claim(service)
    started = start(service)
    assert start(service) == started

    first_checkpoint = service.commit_checkpoint(
        task_id="task-1",
        attempt_id=started["attempt_id"],
        command_id="checkpoint-for-resume",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        expected_checkpoint_id=None,
        state_payload={"step": 1},
    )
    resume_kwargs = {
        "task_id": "task-1",
        "attempt_id": started["attempt_id"],
        "command_id": "resume-idempotent",
        "owner_id": "worker-a",
        "owner_epoch": 1,
        "expected_state_version": first_checkpoint["state_version"],
        "expected_checkpoint_id": first_checkpoint["checkpoint_id"],
    }
    resumed = service.resume_attempt(**resume_kwargs)
    assert service.resume_attempt(**resume_kwargs) == resumed

    service.complete_attempt(
        task_id="task-1",
        attempt_id=started["attempt_id"],
        command_id="finish-for-retry",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=resumed["state_version"],
        checkpoint_id=resumed["checkpoint_id"],
        answer_status=AnswerStatus.VALID_INSUFFICIENT,
        termination_reason=TerminationReason.NO_NEW_EVIDENCE,
        failure_class=FailureClass.NONE,
        reason_detail="retry needed",
        task_terminal=False,
        next_task_status=TaskStatus.READY,
    )
    retry_kwargs = {
        "task_id": "task-1",
        "parent_attempt_id": started["attempt_id"],
        "command_id": "retry-idempotent",
        "owner_id": "worker-a",
        "owner_epoch": 1,
        "expected_state_version": 5,
    }
    retried = service.retry_attempt(**retry_kwargs)
    assert service.retry_attempt(**retry_kwargs) == retried
    state = service.get_task("task-1")
    assert len(state["attempts"]) == 2
    assert sum(event["event_type"] == "attempt_resumed" for event in state["events"]) == 1


def test_public_start_attempt_rejects_cause_and_lineage_bypasses_without_drift(
    research,
) -> None:
    _db, _clock, _adapter, service = research
    create_task(service)
    claim(service)

    invalid_before_initial = (
        {
            "cause": AttemptCause.INITIAL,
            "parent_attempt_id": "forged-parent",
        },
        {"cause": AttemptCause.RESUME},
        {"cause": AttemptCause.RETRY},
        {"cause": AttemptCause.GOAL_REVISION},
        {"cause": AttemptCause.BRANCH, "source_checkpoint_id": "forged-checkpoint"},
        {"cause": AttemptCause.REPLAY, "parent_attempt_id": "forged-parent"},
    )
    for index, cause_fields in enumerate(invalid_before_initial):
        before = service.get_task("task-1")
        with pytest.raises(ResearchValidationError):
            service.start_attempt(
                task_id="task-1",
                command_id=f"invalid-start-before:{index}",
                owner_id="worker-a",
                owner_epoch=1,
                expected_state_version=1,
                **cause_fields,
            )
        assert service.get_task("task-1") == before

    attempt = start(service)
    checkpoint = service.commit_checkpoint(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="cause-guard-checkpoint",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        expected_checkpoint_id=None,
        state_payload={"guard": True},
    )
    service.complete_attempt(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="cause-guard-terminal-attempt",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=checkpoint["state_version"],
        checkpoint_id=checkpoint["checkpoint_id"],
        answer_status=AnswerStatus.VALID_INSUFFICIENT,
        termination_reason=TerminationReason.NO_NEW_EVIDENCE,
        failure_class=FailureClass.NONE,
        reason_detail="prepare historical Attempt",
        task_terminal=False,
        next_task_status=TaskStatus.READY,
    )

    invalid_after_history = (
        {"cause": AttemptCause.INITIAL},
        {"cause": AttemptCause.RESUME},
        {"cause": AttemptCause.RETRY},
        {
            "cause": AttemptCause.RETRY,
            "parent_attempt_id": attempt["attempt_id"],
            "source_checkpoint_id": checkpoint["checkpoint_id"],
        },
        {"cause": AttemptCause.GOAL_REVISION},
        {
            "cause": AttemptCause.BRANCH,
            "parent_attempt_id": "not-the-source-attempt",
            "source_checkpoint_id": checkpoint["checkpoint_id"],
        },
        {
            "cause": AttemptCause.REPLAY,
            "parent_attempt_id": attempt["attempt_id"],
        },
    )
    for index, cause_fields in enumerate(invalid_after_history):
        before = service.get_task("task-1")
        with pytest.raises(ResearchValidationError):
            service.start_attempt(
                task_id="task-1",
                command_id=f"invalid-start-after:{index}",
                owner_id="worker-a",
                owner_epoch=1,
                expected_state_version=4,
                **cause_fields,
            )
        assert service.get_task("task-1") == before


def test_stale_checkpoint_and_checkpoint_fault_fail_closed(research) -> None:
    db, clock, adapter, service = research
    attempt = bootstrap(service)
    first = service.commit_checkpoint(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="checkpoint-1",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        expected_checkpoint_id=None,
        state_payload={"step": 1},
    )
    with pytest.raises(ResearchConflict, match="checkpoint"):
        service.commit_checkpoint(
            task_id="task-1",
            attempt_id=attempt["attempt_id"],
            command_id="checkpoint-stale",
            owner_id="worker-a",
            owner_epoch=1,
            expected_state_version=3,
            expected_checkpoint_id=None,
            state_payload={"step": 2},
        )

    def fault(point: str) -> None:
        if point == "after_checkpoint_insert":
            raise SimulatedCrash(point)

    crashing = ResearchTaskService(
        db, clock=clock, effect_adapter=adapter, fault_injector=fault
    )
    with pytest.raises(SimulatedCrash):
        crashing.commit_checkpoint(
            task_id="task-1",
            attempt_id=attempt["attempt_id"],
            command_id="checkpoint-crash",
            owner_id="worker-a",
            owner_epoch=1,
            expected_state_version=3,
            expected_checkpoint_id=first["checkpoint_id"],
            state_payload={"step": 2},
        )
    state = service.get_task("task-1")
    assert len(state["checkpoints"]) == 1
    assert state["task"]["state_version"] == 3
    assert all(
        receipt["command_id"] != "checkpoint-crash"
        for receipt in state["command_receipts"]
    )


def test_result_commit_requires_latest_checkpoint_guard(research) -> None:
    _db, _clock, _adapter, service = research
    attempt = bootstrap(service)
    checkpoint = service.commit_checkpoint(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="checkpoint-result-guard",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        expected_checkpoint_id=None,
        state_payload={"step": 1},
    )

    with pytest.raises(ResearchConflict, match="stale expected checkpoint"):
        service.complete_attempt(
            task_id="task-1",
            attempt_id=attempt["attempt_id"],
            command_id="stale-result",
            owner_id="worker-a",
            owner_epoch=1,
            expected_state_version=checkpoint["state_version"],
            checkpoint_id=None,
            answer_status=AnswerStatus.VALID_SUCCESS,
            termination_reason=TerminationReason.ANSWER_READY,
            failure_class=FailureClass.NONE,
            reason_detail="must not commit without the latest checkpoint identity",
            task_terminal=True,
        )
    state = service.get_task("task-1")
    assert state["results"] == []
    assert state["attempts"][0]["status"] == "running"


def test_checkpoint_lineage_cycle_is_detected_without_chronological_fallback(
    research,
) -> None:
    db, _clock, _adapter, service = research
    attempt = bootstrap(service)
    checkpoint = service.commit_checkpoint(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="checkpoint-1",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        expected_checkpoint_id=None,
        state_payload={},
    )
    raw = sqlite3.connect(db.path)
    raw.execute("PRAGMA foreign_keys=OFF")
    raw.execute(
        "UPDATE research_checkpoints SET parent_checkpoint_id=? WHERE checkpoint_id=?",
        (checkpoint["checkpoint_id"], checkpoint["checkpoint_id"]),
    )
    raw.commit()
    raw.close()

    with pytest.raises(ResearchUnsafeState, match="cycle"):
        service.checkpoint_lineage(checkpoint["checkpoint_id"])


def test_attempt_result_can_be_terminal_while_task_remains_retryable(research) -> None:
    _db, _clock, _adapter, service = research
    attempt = bootstrap(service)
    completed = service.complete_attempt(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="attempt-insufficient",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        answer_status=AnswerStatus.VALID_INSUFFICIENT,
        termination_reason=TerminationReason.EVIDENCE_UNAVAILABLE,
        failure_class=FailureClass.NONE,
        reason_detail="没有足够证据",
        task_terminal=False,
        next_task_status=TaskStatus.READY,
    )
    assert completed["task_status"] == "ready"

    retried = service.retry_attempt(
        task_id="task-1",
        parent_attempt_id=attempt["attempt_id"],
        command_id="retry-1",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=3,
    )
    state = service.get_task("task-1")
    assert state["task"]["status"] == "running"
    assert state["task"]["terminal_result_id"] is None
    assert state["attempts"][0]["status"] == "terminal"
    assert state["attempts"][1]["parent_attempt_id"] == attempt["attempt_id"]
    assert retried["attempt_id"] == state["attempts"][1]["attempt_id"]


def test_result_dimensions_preserve_partial_provider_failure_without_provider_run(
    research,
) -> None:
    _db, _clock, _adapter, service = research
    attempt = bootstrap(service)
    service.complete_attempt(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="result-1",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        answer_status=AnswerStatus.VALID_PARTIAL,
        termination_reason=TerminationReason.PROVIDER_ERROR,
        failure_class=FailureClass.PROVIDER_FAILURE,
        reason_detail="schema expressiveness test only",
        task_terminal=True,
    )
    result = service.get_task("task-1")["results"][0]
    assert (
        result["answer_status"],
        result["termination_reason"],
        result["failure_class"],
    ) == ("valid_partial", "provider_error", "provider_failure")


def test_result_dimensions_preserve_implementation_failure_without_answer(
    research,
) -> None:
    _db, _clock, _adapter, service = research
    attempt = bootstrap(service)
    service.complete_attempt(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="implementation-failure-result",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        answer_status=AnswerStatus.NOT_PRODUCED,
        termination_reason=TerminationReason.IMPLEMENTATION_ERROR,
        failure_class=FailureClass.IMPLEMENTATION_FAILURE,
        reason_detail="deterministic schema and derivation coverage",
        task_terminal=True,
    )
    result = service.get_task("task-1")["results"][0]
    assert (
        result["answer_status"],
        result["termination_reason"],
        result["failure_class"],
    ) == ("not_produced", "implementation_error", "implementation_failure")


def test_result_fault_rolls_back_result_attempt_and_task_terminal_state(research) -> None:
    db, clock, adapter, service = research
    attempt = bootstrap(service)

    def fault(point: str) -> None:
        if point == "after_result_insert":
            raise SimulatedCrash(point)

    crashing = ResearchTaskService(
        db, clock=clock, effect_adapter=adapter, fault_injector=fault
    )
    with pytest.raises(SimulatedCrash):
        crashing.complete_attempt(
            task_id="task-1",
            attempt_id=attempt["attempt_id"],
            command_id="terminal-crash",
            owner_id="worker-a",
            owner_epoch=1,
            expected_state_version=2,
            answer_status=AnswerStatus.VALID_SUCCESS,
            termination_reason=TerminationReason.ANSWER_READY,
            failure_class=FailureClass.NONE,
            reason_detail="done",
            task_terminal=True,
        )
    state = service.get_task("task-1")
    assert state["task"]["status"] == "running"
    assert state["task"]["terminal_result_id"] is None
    assert state["attempts"][0]["status"] == "running"
    assert state["results"] == []


def test_terminal_task_cannot_revive_and_retry_creates_immutable_child_lineage(
    research,
) -> None:
    _db, _clock, _adapter, service = research
    attempt = bootstrap(service)
    service.complete_attempt(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="terminal-1",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        answer_status=AnswerStatus.VALID_SUCCESS,
        termination_reason=TerminationReason.ANSWER_READY,
        failure_class=FailureClass.NONE,
        reason_detail="done",
        task_terminal=True,
    )
    parent_before = service.get_task("task-1")["task"]

    with pytest.raises(ResearchUnsafeState, match="terminal"):
        start(
            service,
            command_id="illegal-restart",
            expected=3,
            cause=AttemptCause.RETRY,
            parent_attempt_id=attempt["attempt_id"],
        )

    child = service.create_child_task(
        parent_task_id="task-1", command_id="child-retry"
    )
    parent_after = service.get_task("task-1")["task"]
    child_state = service.get_task(child["task_id"])
    assert parent_after == parent_before
    assert child_state["task"]["parent_task_id"] == "task-1"
    assert service.task_lineage(child["task_id"]) == [child["task_id"], "task-1"]


def test_goal_revision_is_immutable_and_starts_new_attempt(research) -> None:
    _db, _clock, _adapter, service = research
    first = bootstrap(service)
    service.complete_attempt(
        task_id="task-1",
        attempt_id=first["attempt_id"],
        command_id="finish-first",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        answer_status=AnswerStatus.VALID_INSUFFICIENT,
        termination_reason=TerminationReason.NO_NEW_EVIDENCE,
        failure_class=FailureClass.NONE,
        reason_detail="revise",
        task_terminal=False,
        next_task_status=TaskStatus.READY,
    )
    revised = service.revise_goal(
        task_id="task-1",
        command_id="revise-1",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=3,
        objective="修订后的目标",
        success_constraints=["新约束"],
        evidence_policy={"authority": "transcript"},
    )
    state = service.get_task("task-1")
    assert [goal["revision"] for goal in state["goals"]] == [1, 2]
    assert state["goals"][0]["objective"] == "研究稳定任务内核"
    assert state["goals"][1]["objective"] == "修订后的目标"
    assert revised["attempt_id"] == state["attempts"][1]["attempt_id"]
    assert state["attempts"][1]["cause"] == "goal_revision"


def test_branch_and_replay_use_read_only_checkpoint_from_current_or_ancestor_task(
    research,
) -> None:
    _db, _clock, _adapter, service = research
    original_attempt = bootstrap(service)
    source = service.commit_checkpoint(
        task_id="task-1",
        attempt_id=original_attempt["attempt_id"],
        command_id="branch-source",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        expected_checkpoint_id=None,
        state_payload={"seed": "immutable"},
    )
    service.complete_attempt(
        task_id="task-1",
        attempt_id=original_attempt["attempt_id"],
        command_id="terminal-source-task",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=source["state_version"],
        checkpoint_id=source["checkpoint_id"],
        answer_status=AnswerStatus.VALID_PARTIAL,
        termination_reason=TerminationReason.NO_NEW_EVIDENCE,
        failure_class=FailureClass.NONE,
        reason_detail="branch source",
        task_terminal=True,
    )
    parent_before = service.get_task("task-1")
    child = service.create_child_task(
        parent_task_id="task-1", command_id="create-branch-child"
    )
    claim(
        service,
        child["task_id"],
        command_id="claim-branch-child",
    )
    branch = service.start_attempt(
        task_id=child["task_id"],
        command_id="start-branch-child",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=1,
        cause=AttemptCause.BRANCH,
        parent_attempt_id=original_attempt["attempt_id"],
        source_checkpoint_id=source["checkpoint_id"],
    )
    child_state = service.get_task(child["task_id"])
    assert child_state["attempts"][0]["attempt_id"] == branch["attempt_id"]
    assert child_state["attempts"][0]["cause"] == "branch"
    assert child_state["attempts"][0]["source_checkpoint_id"] == source["checkpoint_id"]
    assert service.get_task("task-1") == parent_before

    unrelated_attempt = bootstrap(service, "unrelated")
    unrelated_source = service.commit_checkpoint(
        task_id="unrelated",
        attempt_id=unrelated_attempt["attempt_id"],
        command_id="unrelated-checkpoint",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        expected_checkpoint_id=None,
        state_payload={},
    )
    service.complete_attempt(
        task_id="unrelated",
        attempt_id=unrelated_attempt["attempt_id"],
        command_id="terminal-unrelated",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=unrelated_source["state_version"],
        checkpoint_id=unrelated_source["checkpoint_id"],
        answer_status=AnswerStatus.VALID_SUCCESS,
        termination_reason=TerminationReason.ANSWER_READY,
        failure_class=FailureClass.NONE,
        reason_detail="unrelated",
        task_terminal=True,
    )
    second_child = service.create_child_task(
        parent_task_id="task-1", command_id="create-replay-child"
    )
    claim(
        service,
        second_child["task_id"],
        command_id="claim-replay-child",
    )
    with pytest.raises(ResearchValidationError, match="祖先"):
        service.start_attempt(
            task_id=second_child["task_id"],
            command_id="wrong-replay-source",
            owner_id="worker-a",
            owner_epoch=1,
            expected_state_version=1,
            cause=AttemptCause.REPLAY,
            parent_attempt_id=unrelated_attempt["attempt_id"],
            source_checkpoint_id=unrelated_source["checkpoint_id"],
        )


def test_cancel_is_idempotent_and_cancel_result_wins_only_once(research) -> None:
    _db, _clock, _adapter, service = research
    attempt = bootstrap(service)
    first = service.cancel_task(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="cancel-1",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
    )
    second = service.cancel_task(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="cancel-1",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
    )
    assert second == first
    state = service.get_task("task-1")
    assert state["task"]["status"] == "terminal"
    assert len(state["results"]) == 1
    assert state["results"][0]["termination_reason"] == "cancelled"


def test_cancel_and_result_race_has_one_terminal_winner(research) -> None:
    _db, _clock, _adapter, service = research
    attempt = bootstrap(service)

    def cancel():
        try:
            return service.cancel_task(
                task_id="task-1",
                attempt_id=attempt["attempt_id"],
                command_id="race-cancel",
                owner_id="worker-a",
                owner_epoch=1,
                expected_state_version=2,
            )
        except ResearchConflict as exc:
            return exc

    def finish():
        try:
            return service.complete_attempt(
                task_id="task-1",
                attempt_id=attempt["attempt_id"],
                command_id="race-result",
                owner_id="worker-a",
                owner_epoch=1,
                expected_state_version=2,
                answer_status=AnswerStatus.VALID_SUCCESS,
                termination_reason=TerminationReason.ANSWER_READY,
                failure_class=FailureClass.NONE,
                reason_detail="done",
                task_terminal=True,
            )
        except (ResearchConflict, ResearchUnsafeState) as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(cancel), pool.submit(finish)]
        values = [future.result() for future in results]
    assert sum(isinstance(value, dict) for value in values) == 1
    assert len(service.get_task("task-1")["results"]) == 1


def test_deterministic_side_effect_is_task_scoped_and_replay_safe(research) -> None:
    _db, _clock, adapter, service = research
    attempt = bootstrap(service)
    first = service.execute_deterministic_side_effect(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="effect-1",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        effect_kind="test_write",
        idempotency_key="business-key",
        request_payload={"value": 1},
    )
    replay = service.execute_deterministic_side_effect(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="effect-1",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        effect_kind="test_write",
        idempotency_key="business-key",
        request_payload={"value": 1},
    )
    assert first["status"] == "succeeded"
    assert replay["deduplicated"] is True
    assert len(adapter.calls) == 1
    assert len(service.get_task("task-1")["side_effects"]) == 1

    with pytest.raises(ResearchUnsafeState, match="request hash"):
        service.reserve_side_effect(
            task_id="task-1",
            attempt_id=attempt["attempt_id"],
            command_id="effect-mismatch",
            owner_id="worker-a",
            owner_epoch=1,
            expected_state_version=5,
            effect_kind="test_write",
            idempotency_key="business-key",
            request_payload={"value": 2},
        )


def test_same_side_effect_business_key_is_valid_across_tasks(research) -> None:
    _db, _clock, adapter, service = research
    first_attempt = bootstrap(service, "task-1")
    second_attempt = bootstrap(service, "task-2")
    for task_id, attempt in (("task-1", first_attempt), ("task-2", second_attempt)):
        service.execute_deterministic_side_effect(
            task_id=task_id,
            attempt_id=attempt["attempt_id"],
            command_id=f"effect:{task_id}",
            owner_id="worker-a",
            owner_epoch=1,
            expected_state_version=2,
            effect_kind="test_write",
            idempotency_key="shared-business-key",
            request_payload={"task": task_id},
        )
    assert len(adapter.calls) == 2
    assert len(service.get_task("task-1")["side_effects"]) == 1
    assert len(service.get_task("task-2")["side_effects"]) == 1


def test_concurrent_same_task_side_effect_reservation_creates_one_record(
    research,
) -> None:
    _db, _clock, _adapter, service = research
    attempt = bootstrap(service)

    def reserve(command_id: str):
        try:
            return service.reserve_side_effect(
                task_id="task-1",
                attempt_id=attempt["attempt_id"],
                command_id=command_id,
                owner_id="worker-a",
                owner_epoch=1,
                expected_state_version=2,
                effect_kind="test_write",
                idempotency_key="contended-key",
                request_payload={"same": True},
            )
        except ResearchConflict as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(reserve, ["reserve-a", "reserve-b"]))
    assert sum(isinstance(value, dict) for value in values) == 1
    assert sum(isinstance(value, ResearchConflict) for value in values) == 1
    assert len(service.get_task("task-1")["side_effects"]) == 1


def test_reserved_side_effect_survives_restart_and_can_continue_once(research) -> None:
    db, clock, adapter, service = research
    attempt = bootstrap(service)
    reserved = service.reserve_side_effect(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="reserve-before-restart",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        effect_kind="test_write",
        idempotency_key="restart-key",
        request_payload={"value": 1},
    )
    restarted = ResearchTaskService(db, clock=clock, effect_adapter=adapter)
    completed = restarted.execute_deterministic_side_effect(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="continue-after-restart",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=reserved["state_version"],
        effect_kind="test_write",
        idempotency_key="restart-key",
        request_payload={"value": 1},
    )
    assert completed["status"] == "succeeded"
    assert len(adapter.calls) == 1
    assert len(service.get_task("task-1")["side_effects"]) == 1


def test_external_call_crash_stays_in_flight_and_never_auto_replays(research) -> None:
    db, clock, adapter, service = research
    attempt = bootstrap(service)
    checkpoint = service.commit_checkpoint(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="before-effect",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        expected_checkpoint_id=None,
        state_payload={"safe": True},
    )

    def fault(point: str) -> None:
        if point == "after_external_call":
            raise SimulatedCrash(point)

    crashing = ResearchTaskService(
        db, clock=clock, effect_adapter=adapter, fault_injector=fault
    )
    with pytest.raises(SimulatedCrash):
        crashing.execute_deterministic_side_effect(
            task_id="task-1",
            attempt_id=attempt["attempt_id"],
            command_id="crashing-effect",
            owner_id="worker-a",
            owner_epoch=1,
            expected_state_version=3,
            effect_kind="test_write",
            idempotency_key="ambiguous-key",
            request_payload={"value": 1},
        )
    assert service.get_task("task-1")["side_effects"][0]["status"] == "in_flight"
    assert len(adapter.calls) == 1

    with pytest.raises(ResearchUnsafeState, match="禁止自动重放"):
        service.execute_deterministic_side_effect(
            task_id="task-1",
            attempt_id=attempt["attempt_id"],
            command_id="crashing-effect",
            owner_id="worker-a",
            owner_epoch=1,
            expected_state_version=3,
            effect_kind="test_write",
            idempotency_key="ambiguous-key",
            request_payload={"value": 1},
        )
    assert len(adapter.calls) == 1

    clock.advance(31)
    takeover = claim(
        service,
        owner_id="worker-b",
        command_id="takeover",
        expected=5,
    )
    assert takeover["rebound_reserved_side_effect_ids"] == []
    assert service.get_task("task-1")["side_effects"][0]["owner_epoch"] == 1
    recovered = service.recover_in_flight(
        task_id="task-1",
        command_id="recover",
        owner_id="worker-b",
        owner_epoch=2,
        expected_state_version=takeover["state_version"],
    )
    assert recovered["unknown_side_effect_ids"]
    assert service.get_task("task-1")["task"]["status"] == "blocked"

    with pytest.raises(ResearchConflict):
        service.transition_side_effect(
            task_id="task-1",
            side_effect_id=recovered["unknown_side_effect_ids"][0],
            command_id="stale-receipt",
            owner_id="worker-a",
            owner_epoch=1,
            expected_state_version=recovered["state_version"],
            target_status="failed",
        )
    resolved = service.resolve_unknown_side_effect(
        task_id="task-1",
        side_effect_id=recovered["unknown_side_effect_ids"][0],
        command_id="resolve",
        owner_id="worker-b",
        owner_epoch=2,
        expected_state_version=recovered["state_version"],
        outcome="failed",
    )
    resumed = service.resume_attempt(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="resume-after-resolution",
        owner_id="worker-b",
        owner_epoch=2,
        expected_state_version=resolved["state_version"],
        expected_checkpoint_id=checkpoint["checkpoint_id"],
    )
    assert resumed["parent_checkpoint_id"] == checkpoint["checkpoint_id"]
    assert len(adapter.calls) == 1


def test_in_flight_cannot_be_marked_unknown_before_old_owner_is_fenced(research) -> None:
    _db, _clock, _adapter, service = research
    attempt = bootstrap(service)
    reserved = service.reserve_side_effect(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="reserve",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        effect_kind="test_write",
        idempotency_key="key",
        request_payload={},
    )
    started = service.transition_side_effect(
        task_id="task-1",
        side_effect_id=reserved["side_effect_id"],
        command_id="start-effect",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=reserved["state_version"],
        target_status="in_flight",
    )
    recovered = service.recover_in_flight(
        task_id="task-1",
        command_id="premature-recovery",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=started["state_version"],
    )
    assert recovered["unknown_side_effect_ids"] == []
    assert service.get_task("task-1")["side_effects"][0]["status"] == "in_flight"


def test_checkpoint_rejected_while_side_effect_is_unresolved(research) -> None:
    _db, _clock, _adapter, service = research
    attempt = bootstrap(service)
    reserved = service.reserve_side_effect(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="reserve",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        effect_kind="test_write",
        idempotency_key="key",
        request_payload={},
    )
    started = service.transition_side_effect(
        task_id="task-1",
        side_effect_id=reserved["side_effect_id"],
        command_id="start-effect",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=reserved["state_version"],
        target_status="in_flight",
    )
    with pytest.raises(ResearchUnsafeState, match="unresolved"):
        service.commit_checkpoint(
            task_id="task-1",
            attempt_id=attempt["attempt_id"],
            command_id="unsafe-checkpoint",
            owner_id="worker-a",
            owner_epoch=1,
            expected_state_version=started["state_version"],
            expected_checkpoint_id=None,
            state_payload={},
        )


def test_task_lineage_missing_parent_fails_closed(research) -> None:
    db, _clock, _adapter, service = research
    attempt = bootstrap(service)
    service.complete_attempt(
        task_id="task-1",
        attempt_id=attempt["attempt_id"],
        command_id="terminal",
        owner_id="worker-a",
        owner_epoch=1,
        expected_state_version=2,
        answer_status=AnswerStatus.VALID_SUCCESS,
        termination_reason=TerminationReason.ANSWER_READY,
        failure_class=FailureClass.NONE,
        reason_detail="done",
        task_terminal=True,
    )
    child = service.create_child_task(parent_task_id="task-1", command_id="child")
    raw = sqlite3.connect(db.path)
    raw.execute("PRAGMA foreign_keys=OFF")
    raw.execute(
        "UPDATE research_tasks SET parent_task_id='missing' WHERE task_id=?",
        (child["task_id"],),
    )
    raw.commit()
    raw.close()
    with pytest.raises(ResearchUnsafeState, match="不可寻址"):
        service.task_lineage(child["task_id"])
