from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from shiliu.db import Database
from shiliu.research.adapter import DeterministicEffectAdapter
from shiliu.research.contracts import (
    AnswerStatus,
    AttemptCause,
    FailureClass,
    ResearchCommandRequest,
    TaskStatus,
    TerminationReason,
)
from shiliu.research.errors import (
    ResearchConflict,
    ResearchNotFound,
    ResearchUnsafeState,
    ResearchValidationError,
)
from shiliu.research.schema import RESEARCH_STATE_SCHEMA_VERSION


Clock = Callable[[], datetime]
FaultInjector = Callable[[str], None]


def _utc_clock() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class ResearchTaskService:
    TRACE_SCHEMA_VERSION = "v5-a-stage1-trace-v1"

    def __init__(
        self,
        db: Database,
        *,
        clock: Clock = _utc_clock,
        effect_adapter: DeterministicEffectAdapter | None = None,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        self.db = db
        self.clock = clock
        self.effect_adapter = effect_adapter or DeterministicEffectAdapter()
        self.fault_injector = fault_injector or (lambda _point: None)

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            yield connection

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _task(connection: sqlite3.Connection, task_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM research_tasks WHERE task_id=?", (task_id,)
        ).fetchone()
        if row is None:
            raise ResearchNotFound(f"Research Task 不存在: {task_id}")
        return row

    @staticmethod
    def _attempt(connection: sqlite3.Connection, attempt_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM research_attempts WHERE attempt_id=?", (attempt_id,)
        ).fetchone()
        if row is None:
            raise ResearchNotFound(f"Research Attempt 不存在: {attempt_id}")
        return row

    @staticmethod
    def _side_effect(connection: sqlite3.Connection, side_effect_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM research_side_effects WHERE side_effect_id=?",
            (side_effect_id,),
        ).fetchone()
        if row is None:
            raise ResearchNotFound(f"SideEffect 不存在: {side_effect_id}")
        return row

    @staticmethod
    def _assert_expected(task: sqlite3.Row, expected_state_version: int) -> None:
        if int(task["state_version"]) != expected_state_version:
            raise ResearchConflict(
                "stale task state: "
                f"expected {expected_state_version}, current {task['state_version']}"
            )

    @staticmethod
    def _assert_nonterminal(task: sqlite3.Row) -> None:
        if str(task["status"]) == TaskStatus.TERMINAL.value:
            raise ResearchUnsafeState("terminal Task 不可原地修改或复活")

    def _assert_owner(
        self,
        task: sqlite3.Row,
        *,
        owner_id: str,
        owner_epoch: int,
        now: datetime,
    ) -> None:
        if (
            str(task["owner_id"] or "") != owner_id
            or int(task["owner_epoch"]) != owner_epoch
        ):
            raise ResearchConflict("stale owner fence")
        lease_until = task["lease_until"]
        if not lease_until or _parse_iso(str(lease_until)) <= now:
            raise ResearchConflict("owner lease 已过期")

    @staticmethod
    def _receipt_response(row: sqlite3.Row) -> dict[str, Any]:
        if row["response_json"]:
            return dict(json.loads(str(row["response_json"])))
        return {"outcome_reference": row["outcome_reference"]}

    def _existing_receipt(
        self,
        connection: sqlite3.Connection,
        *,
        task_id: str,
        command_id: str,
        payload_hash: str,
        owner_id: str | None = None,
        owner_epoch: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            """
            SELECT * FROM research_command_receipts
            WHERE task_id=? AND command_id=?
            """,
            (task_id, command_id),
        ).fetchone()
        if row is None:
            return None
        task: sqlite3.Row | None = None
        if owner_id is not None:
            task = self._task(connection, task_id)
            receipt_epoch = (
                owner_epoch if owner_epoch is not None else int(row["owner_epoch"])
            )
            self._assert_owner(
                task,
                owner_id=owner_id,
                owner_epoch=receipt_epoch,
                now=now or self._now(),
            )
        if str(row["payload_hash"]) != payload_hash:
            task = task or self._task(connection, task_id)
            event_now = _iso(now or self._now())
            self._event(
                connection,
                task_id=task_id,
                goal_id=(
                    str(task["active_goal_id"])
                    if task["active_goal_id"] is not None
                    else None
                ),
                event_type="command_payload_mismatch_rejected",
                payload={
                    "command_id": command_id,
                    "stored_payload_hash": str(row["payload_hash"]),
                    "received_payload_hash": payload_hash,
                },
                command_id=command_id,
                owner_epoch=int(task["owner_epoch"]),
                now=event_now,
            )
            # The rejection audit is itself a complete append-only fact. Commit it
            # before raising so the caller's rollback cannot erase the conflict.
            connection.commit()
            raise ResearchConflict(
                "同一 command_id 的 payload hash 不一致，已 fail closed"
            )
        return self._receipt_response(row)

    @staticmethod
    def _insert_receipt(
        connection: sqlite3.Connection,
        *,
        task_id: str,
        command_id: str,
        command_type: str,
        payload_hash: str,
        outcome_reference: str | None,
        response: dict[str, Any],
        owner_epoch: int,
        now: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO research_command_receipts(
                receipt_id, task_id, command_id, command_type, payload_hash,
                status, outcome_reference, response_json, owner_epoch,
                created_at, completed_at
            ) VALUES(?, ?, ?, ?, ?, 'committed', ?, ?, ?, ?, ?)
            """,
            (
                _new_id("receipt"),
                task_id,
                command_id,
                command_type,
                payload_hash,
                outcome_reference,
                _canonical_json(response),
                owner_epoch,
                now,
                now,
            ),
        )

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        *,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
        command_id: str | None,
        owner_epoch: int,
        now: str,
        goal_id: str | None = None,
        attempt_id: str | None = None,
        checkpoint_id: str | None = None,
    ) -> str:
        sequence = int(
            connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM research_events WHERE task_id=?",
                (task_id,),
            ).fetchone()[0]
        )
        event_id = _new_id("event")
        connection.execute(
            """
            INSERT INTO research_events(
                event_id, task_id, goal_id, attempt_id, checkpoint_id,
                sequence, event_type, payload_json, command_id, owner_epoch, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                task_id,
                goal_id,
                attempt_id,
                checkpoint_id,
                sequence,
                event_type,
                _canonical_json(payload),
                command_id,
                owner_epoch,
                now,
            ),
        )
        return event_id

    @staticmethod
    def _decode_row(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        for name in (
            "success_constraints_json",
            "evidence_policy_json",
            "state_payload_json",
            "payload_json",
            "response_json",
            "request_json",
        ):
            if name in value:
                raw = value.pop(name)
                value[name.removesuffix("_json")] = json.loads(str(raw)) if raw else None
        for name in ("is_complete", "is_task_terminal"):
            if name in value:
                value[name] = bool(value[name])
        return value

    def create_task(
        self,
        *,
        command_id: str,
        objective: str,
        success_constraints: list[str] | None = None,
        evidence_policy: dict[str, Any] | None = None,
        task_id: str | None = None,
        parent_task_id: str | None = None,
    ) -> dict[str, Any]:
        objective = objective.strip()
        if not objective:
            raise ResearchValidationError("objective 不能为空")
        task_id = task_id or f"rtask_{hashlib.sha256(command_id.encode()).hexdigest()[:32]}"
        payload = {
            "objective": objective,
            "success_constraints": success_constraints or [],
            "evidence_policy": evidence_policy or {},
            "parent_task_id": parent_task_id,
            "task_id": task_id,
        }
        payload_hash = _hash(payload)
        now = _iso(self._now())
        with self._transaction() as connection:
            existing_task = connection.execute(
                "SELECT task_id FROM research_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if existing_task is not None:
                existing = self._existing_receipt(
                    connection,
                    task_id=task_id,
                    command_id=command_id,
                    payload_hash=payload_hash,
                )
                if existing is None:
                    raise ResearchConflict("task_id 已存在但 command receipt 不匹配")
                return existing
            if parent_task_id is not None:
                parent = self._task(connection, parent_task_id)
                if str(parent["status"]) != TaskStatus.TERMINAL.value:
                    raise ResearchValidationError("parent_task_id 必须指向 terminal Task")
            connection.execute(
                """
                INSERT INTO research_tasks(
                    task_id, parent_task_id, status, active_goal_id, state_version,
                    owner_id, owner_epoch, lease_until, terminal_result_id,
                    created_at, updated_at
                ) VALUES(?, ?, 'ready', NULL, 0, NULL, 0, NULL, NULL, ?, ?)
                """,
                (task_id, parent_task_id, now, now),
            )
            self.fault_injector("after_task_insert")
            goal_id = _new_id("goal")
            connection.execute(
                """
                INSERT INTO research_goals(
                    goal_id, task_id, revision, parent_goal_id, objective,
                    success_constraints_json, evidence_policy_json,
                    created_by_event_id, created_at
                ) VALUES(?, ?, 1, NULL, ?, ?, ?, NULL, ?)
                """,
                (
                    goal_id,
                    task_id,
                    objective,
                    _canonical_json(success_constraints or []),
                    _canonical_json(evidence_policy or {}),
                    now,
                ),
            )
            connection.execute(
                "UPDATE research_tasks SET active_goal_id=? WHERE task_id=?",
                (goal_id, task_id),
            )
            event_id = self._event(
                connection,
                task_id=task_id,
                goal_id=goal_id,
                event_type="task_created",
                payload={"parent_task_id": parent_task_id, "goal_revision": 1},
                command_id=command_id,
                owner_epoch=0,
                now=now,
            )
            connection.execute(
                "UPDATE research_goals SET created_by_event_id=? WHERE goal_id=?",
                (event_id, goal_id),
            )
            response = {"task_id": task_id, "goal_id": goal_id, "state_version": 0}
            self._insert_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                command_type="create_task",
                payload_hash=payload_hash,
                outcome_reference=task_id,
                response=response,
                owner_epoch=0,
                now=now,
            )
        return response

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self.db.connect() as connection:
            task = self._task(connection, task_id)
            queries = {
                "goals": "SELECT * FROM research_goals WHERE task_id=? ORDER BY revision",
                "attempts": "SELECT * FROM research_attempts WHERE task_id=? ORDER BY ordinal",
                "checkpoints": (
                    "SELECT * FROM research_checkpoints WHERE task_id=? "
                    "ORDER BY created_at, sequence"
                ),
                "events": "SELECT * FROM research_events WHERE task_id=? ORDER BY sequence",
                "traces": (
                    "SELECT * FROM research_traces WHERE task_id=? "
                    "ORDER BY started_at, trace_id"
                ),
                "results": (
                    "SELECT * FROM research_results WHERE task_id=? "
                    "ORDER BY created_at, result_id"
                ),
                "command_receipts": (
                    "SELECT * FROM research_command_receipts WHERE task_id=? "
                    "ORDER BY created_at, receipt_id"
                ),
                "side_effects": (
                    "SELECT * FROM research_side_effects WHERE task_id=? "
                    "ORDER BY created_at, side_effect_id"
                ),
            }
            value: dict[str, Any] = {"task": self._decode_row(task)}
            for key, query in queries.items():
                value[key] = [
                    self._decode_row(row)
                    for row in connection.execute(query, (task_id,)).fetchall()
                ]
        return value

    def claim_owner(
        self,
        *,
        task_id: str,
        command_id: str,
        owner_id: str,
        expected_state_version: int,
        lease_seconds: int,
    ) -> dict[str, Any]:
        now_value = self._now()
        now = _iso(now_value)
        payload = {
            "owner_id": owner_id,
            "expected_state_version": expected_state_version,
            "lease_seconds": lease_seconds,
        }
        payload_hash = _hash(payload)
        with self._transaction() as connection:
            existing = self._existing_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                payload_hash=payload_hash,
                owner_id=owner_id,
                now=now_value,
            )
            if existing is not None:
                return existing
            task = self._task(connection, task_id)
            self._assert_nonterminal(task)
            self._assert_expected(task, expected_state_version)
            lease_until = task["lease_until"]
            if (
                task["owner_id"]
                and lease_until
                and _parse_iso(str(lease_until)) > now_value
            ):
                raise ResearchConflict("Task 已有未过期 active owner")
            owner_epoch = int(task["owner_epoch"]) + 1
            expires = _iso(now_value + timedelta(seconds=lease_seconds))
            cursor = connection.execute(
                """
                UPDATE research_tasks
                SET owner_id=?, owner_epoch=?, lease_until=?,
                    state_version=state_version+1, updated_at=?
                WHERE task_id=? AND state_version=? AND owner_epoch=?
                """,
                (
                    owner_id,
                    owner_epoch,
                    expires,
                    now,
                    task_id,
                    expected_state_version,
                    int(task["owner_epoch"]),
                ),
            )
            if cursor.rowcount != 1:
                raise ResearchConflict("owner claim CAS 失败")
            connection.execute(
                """
                UPDATE research_attempts
                SET owner_epoch=?
                WHERE task_id=? AND status!='terminal'
                """,
                (owner_epoch, task_id),
            )
            self.fault_injector("after_owner_claim")
            self._event(
                connection,
                task_id=task_id,
                event_type="owner_claimed",
                payload={"owner_id": owner_id, "lease_until": expires},
                command_id=command_id,
                owner_epoch=owner_epoch,
                now=now,
            )
            response = {
                "task_id": task_id,
                "owner_id": owner_id,
                "owner_epoch": owner_epoch,
                "lease_until": expires,
                "state_version": expected_state_version + 1,
            }
            self._insert_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                command_type="claim_owner",
                payload_hash=payload_hash,
                outcome_reference=task_id,
                response=response,
                owner_epoch=owner_epoch,
                now=now,
            )
        return response

    def renew_owner(
        self,
        *,
        task_id: str,
        command_id: str,
        owner_id: str,
        owner_epoch: int,
        expected_state_version: int,
        lease_seconds: int,
    ) -> dict[str, Any]:
        now_value = self._now()
        now = _iso(now_value)
        payload = {
            "owner_id": owner_id,
            "owner_epoch": owner_epoch,
            "expected_state_version": expected_state_version,
            "lease_seconds": lease_seconds,
        }
        payload_hash = _hash(payload)
        with self._transaction() as connection:
            existing = self._existing_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                payload_hash=payload_hash,
                owner_id=owner_id,
                owner_epoch=owner_epoch,
                now=now_value,
            )
            if existing is not None:
                return existing
            task = self._task(connection, task_id)
            self._assert_nonterminal(task)
            self._assert_expected(task, expected_state_version)
            self._assert_owner(
                task, owner_id=owner_id, owner_epoch=owner_epoch, now=now_value
            )
            expires = _iso(now_value + timedelta(seconds=lease_seconds))
            connection.execute(
                """
                UPDATE research_tasks
                SET lease_until=?, state_version=state_version+1, updated_at=?
                WHERE task_id=?
                """,
                (expires, now, task_id),
            )
            self._event(
                connection,
                task_id=task_id,
                event_type="owner_renewed",
                payload={"owner_id": owner_id, "lease_until": expires},
                command_id=command_id,
                owner_epoch=owner_epoch,
                now=now,
            )
            response = {
                "task_id": task_id,
                "owner_epoch": owner_epoch,
                "lease_until": expires,
                "state_version": expected_state_version + 1,
            }
            self._insert_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                command_type="renew_owner",
                payload_hash=payload_hash,
                outcome_reference=task_id,
                response=response,
                owner_epoch=owner_epoch,
                now=now,
            )
        return response

    def start_attempt(
        self,
        *,
        task_id: str,
        command_id: str,
        owner_id: str,
        owner_epoch: int,
        expected_state_version: int,
        cause: AttemptCause = AttemptCause.INITIAL,
        parent_attempt_id: str | None = None,
        source_checkpoint_id: str | None = None,
    ) -> dict[str, Any]:
        now_value = self._now()
        now = _iso(now_value)
        payload = {
            "owner_id": owner_id,
            "owner_epoch": owner_epoch,
            "expected_state_version": expected_state_version,
            "cause": cause.value,
            "parent_attempt_id": parent_attempt_id,
            "source_checkpoint_id": source_checkpoint_id,
        }
        payload_hash = _hash(payload)
        with self._transaction() as connection:
            existing = self._existing_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                payload_hash=payload_hash,
                owner_id=owner_id,
                owner_epoch=owner_epoch,
                now=now_value,
            )
            if existing is not None:
                return existing
            task = self._task(connection, task_id)
            self._assert_nonterminal(task)
            self._assert_expected(task, expected_state_version)
            self._assert_owner(
                task, owner_id=owner_id, owner_epoch=owner_epoch, now=now_value
            )
            active = connection.execute(
                """
                SELECT attempt_id FROM research_attempts
                WHERE task_id=? AND status!='terminal'
                """,
                (task_id,),
            ).fetchone()
            if active is not None:
                raise ResearchConflict("Task 已存在非终态 Attempt")
            if parent_attempt_id is not None:
                parent = self._attempt(connection, parent_attempt_id)
                if (
                    str(parent["task_id"]) != task_id
                    or str(parent["status"]) != "terminal"
                ):
                    raise ResearchValidationError("parent Attempt 必须属于同一 Task 且已终态")
            if cause in {AttemptCause.BRANCH, AttemptCause.REPLAY}:
                if source_checkpoint_id is None:
                    raise ResearchValidationError("branch/replay 必须提供 source checkpoint")
                source = connection.execute(
                    "SELECT * FROM research_checkpoints WHERE checkpoint_id=?",
                    (source_checkpoint_id,),
                ).fetchone()
                if source is None or not bool(source["is_complete"]):
                    raise ResearchValidationError("source checkpoint 不存在或不完整")
                source_attempt = self._attempt(
                    connection, str(source["attempt_id"])
                )
                if str(source_attempt["status"]) != "terminal":
                    raise ResearchValidationError("source Attempt 必须已终态")
                source_task_id = str(source["task_id"])
                lineage_cursor: str | None = task_id
                visited_tasks: set[str] = set()
                source_is_current_or_ancestor = False
                while lineage_cursor is not None:
                    if lineage_cursor in visited_tasks:
                        raise ResearchUnsafeState("Task lineage cycle")
                    visited_tasks.add(lineage_cursor)
                    if lineage_cursor == source_task_id:
                        source_is_current_or_ancestor = True
                        break
                    lineage_row = connection.execute(
                        """
                        SELECT parent_task_id FROM research_tasks
                        WHERE task_id=?
                        """,
                        (lineage_cursor,),
                    ).fetchone()
                    if lineage_row is None:
                        raise ResearchUnsafeState("Task lineage parent 不可寻址")
                    lineage_cursor = (
                        str(lineage_row["parent_task_id"])
                        if lineage_row["parent_task_id"] is not None
                        else None
                    )
                if not source_is_current_or_ancestor:
                    raise ResearchValidationError(
                        "source checkpoint 不属于当前 Task 或其祖先"
                    )
            ordinal = int(
                connection.execute(
                    "SELECT COALESCE(MAX(ordinal), 0) + 1 FROM research_attempts WHERE task_id=?",
                    (task_id,),
                ).fetchone()[0]
            )
            attempt_id = _new_id("attempt")
            connection.execute(
                """
                INSERT INTO research_attempts(
                    attempt_id, task_id, goal_id, ordinal, cause,
                    parent_attempt_id, source_checkpoint_id, status,
                    owner_epoch, result_id, started_at, ended_at, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, 'running', ?, NULL, ?, NULL, ?)
                """,
                (
                    attempt_id,
                    task_id,
                    str(task["active_goal_id"]),
                    ordinal,
                    cause.value,
                    parent_attempt_id,
                    source_checkpoint_id,
                    owner_epoch,
                    now,
                    now,
                ),
            )
            trace_id = _new_id("trace")
            connection.execute(
                """
                INSERT INTO research_traces(
                    trace_id, task_id, attempt_id, trace_schema_version,
                    started_at, ended_at, termination_reason, retention_class
                ) VALUES(?, ?, ?, ?, ?, NULL, NULL, 'stage1_kernel')
                """,
                (trace_id, task_id, attempt_id, self.TRACE_SCHEMA_VERSION, now),
            )
            connection.execute(
                """
                UPDATE research_tasks
                SET status='running', state_version=state_version+1, updated_at=?
                WHERE task_id=?
                """,
                (now, task_id),
            )
            self.fault_injector("after_attempt_insert")
            self._event(
                connection,
                task_id=task_id,
                goal_id=str(task["active_goal_id"]),
                attempt_id=attempt_id,
                event_type="attempt_started",
                payload={"cause": cause.value, "ordinal": ordinal},
                command_id=command_id,
                owner_epoch=owner_epoch,
                now=now,
            )
            response = {
                "task_id": task_id,
                "attempt_id": attempt_id,
                "trace_id": trace_id,
                "state_version": expected_state_version + 1,
            }
            self._insert_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                command_type="start_attempt",
                payload_hash=payload_hash,
                outcome_reference=attempt_id,
                response=response,
                owner_epoch=owner_epoch,
                now=now,
            )
        return response

    def commit_checkpoint(
        self,
        *,
        task_id: str,
        attempt_id: str,
        command_id: str,
        owner_id: str,
        owner_epoch: int,
        expected_state_version: int,
        expected_checkpoint_id: str | None,
        state_payload: dict[str, Any],
        _event_type: str = "checkpoint_committed",
        _command_type: str = "commit_checkpoint",
    ) -> dict[str, Any]:
        now_value = self._now()
        now = _iso(now_value)
        payload = {
            "attempt_id": attempt_id,
            "owner_id": owner_id,
            "owner_epoch": owner_epoch,
            "expected_state_version": expected_state_version,
            "expected_checkpoint_id": expected_checkpoint_id,
            "state_payload": state_payload,
            "operation": _command_type,
        }
        payload_hash = _hash(payload)
        with self._transaction() as connection:
            existing = self._existing_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                payload_hash=payload_hash,
                owner_id=owner_id,
                owner_epoch=owner_epoch,
                now=now_value,
            )
            if existing is not None:
                return existing
            task = self._task(connection, task_id)
            attempt = self._attempt(connection, attempt_id)
            self._assert_nonterminal(task)
            self._assert_expected(task, expected_state_version)
            self._assert_owner(
                task, owner_id=owner_id, owner_epoch=owner_epoch, now=now_value
            )
            if (
                str(attempt["task_id"]) != task_id
                or str(attempt["status"]) == "terminal"
                or int(attempt["owner_epoch"]) != owner_epoch
            ):
                raise ResearchConflict("Attempt 与当前 Task/owner fence 不一致")
            latest = connection.execute(
                """
                SELECT * FROM research_checkpoints
                WHERE attempt_id=? ORDER BY sequence DESC LIMIT 1
                """,
                (attempt_id,),
            ).fetchone()
            current_checkpoint_id = str(latest["checkpoint_id"]) if latest else None
            if current_checkpoint_id != expected_checkpoint_id:
                raise ResearchConflict("stale expected checkpoint")
            unresolved = int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM research_side_effects
                    WHERE task_id=? AND status IN ('in_flight', 'unknown')
                    """,
                    (task_id,),
                ).fetchone()[0]
            )
            if unresolved:
                raise ResearchUnsafeState("存在 unresolved SideEffect，不能提交安全 checkpoint")
            sequence = int(latest["sequence"]) + 1 if latest else 1
            checkpoint_id = _new_id("checkpoint")
            state_json = _canonical_json(state_payload)
            state_hash = hashlib.sha256(state_json.encode("utf-8")).hexdigest()
            connection.execute(
                """
                INSERT INTO research_checkpoints(
                    checkpoint_id, task_id, goal_id, attempt_id,
                    parent_checkpoint_id, sequence, state_schema_version,
                    state_hash, state_payload_json, is_complete, owner_epoch, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    checkpoint_id,
                    task_id,
                    str(attempt["goal_id"]),
                    attempt_id,
                    expected_checkpoint_id,
                    sequence,
                    RESEARCH_STATE_SCHEMA_VERSION,
                    state_hash,
                    state_json,
                    owner_epoch,
                    now,
                ),
            )
            self.fault_injector("after_checkpoint_insert")
            connection.execute(
                """
                UPDATE research_tasks
                SET status=CASE WHEN ?='attempt_resumed' THEN 'running' ELSE status END,
                    state_version=state_version+1, updated_at=?
                WHERE task_id=?
                """,
                (_event_type, now, task_id),
            )
            if _event_type == "attempt_resumed":
                connection.execute(
                    "UPDATE research_attempts SET status='running' WHERE attempt_id=?",
                    (attempt_id,),
                )
            self._event(
                connection,
                task_id=task_id,
                goal_id=str(attempt["goal_id"]),
                attempt_id=attempt_id,
                checkpoint_id=checkpoint_id,
                event_type=_event_type,
                payload={"sequence": sequence, "state_hash": state_hash},
                command_id=command_id,
                owner_epoch=owner_epoch,
                now=now,
            )
            response = {
                "task_id": task_id,
                "attempt_id": attempt_id,
                "checkpoint_id": checkpoint_id,
                "parent_checkpoint_id": expected_checkpoint_id,
                "state_hash": state_hash,
                "state_version": expected_state_version + 1,
            }
            self._insert_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                command_type=_command_type,
                payload_hash=payload_hash,
                outcome_reference=checkpoint_id,
                response=response,
                owner_epoch=owner_epoch,
                now=now,
            )
        return response

    def resume_attempt(
        self,
        *,
        task_id: str,
        attempt_id: str,
        command_id: str,
        owner_id: str,
        owner_epoch: int,
        expected_state_version: int,
        expected_checkpoint_id: str,
    ) -> dict[str, Any]:
        with self.db.connect() as connection:
            checkpoint = connection.execute(
                "SELECT * FROM research_checkpoints WHERE checkpoint_id=?",
                (expected_checkpoint_id,),
            ).fetchone()
            if checkpoint is None:
                raise ResearchNotFound("resume checkpoint 不存在")
            if (
                str(checkpoint["task_id"]) != task_id
                or str(checkpoint["attempt_id"]) != attempt_id
                or not bool(checkpoint["is_complete"])
            ):
                raise ResearchUnsafeState("resume checkpoint identity/receipt 无效")
            state_payload = json.loads(str(checkpoint["state_payload_json"]))
        return self.commit_checkpoint(
            task_id=task_id,
            attempt_id=attempt_id,
            command_id=command_id,
            owner_id=owner_id,
            owner_epoch=owner_epoch,
            expected_state_version=expected_state_version,
            expected_checkpoint_id=expected_checkpoint_id,
            state_payload=state_payload,
            _event_type="attempt_resumed",
            _command_type="resume_attempt",
        )

    def complete_attempt(
        self,
        *,
        task_id: str,
        attempt_id: str,
        command_id: str,
        owner_id: str,
        owner_epoch: int,
        expected_state_version: int,
        answer_status: AnswerStatus,
        termination_reason: TerminationReason,
        failure_class: FailureClass,
        reason_detail: str,
        task_terminal: bool,
        next_task_status: TaskStatus = TaskStatus.BLOCKED,
        checkpoint_id: str | None = None,
    ) -> dict[str, Any]:
        now_value = self._now()
        now = _iso(now_value)
        payload = {
            "attempt_id": attempt_id,
            "owner_id": owner_id,
            "owner_epoch": owner_epoch,
            "expected_state_version": expected_state_version,
            "answer_status": answer_status.value,
            "termination_reason": termination_reason.value,
            "failure_class": failure_class.value,
            "reason_detail": reason_detail,
            "task_terminal": task_terminal,
            "next_task_status": next_task_status.value,
            "checkpoint_id": checkpoint_id,
        }
        payload_hash = _hash(payload)
        with self._transaction() as connection:
            existing = self._existing_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                payload_hash=payload_hash,
                owner_id=owner_id,
                owner_epoch=owner_epoch,
                now=now_value,
            )
            if existing is not None:
                return existing
            task = self._task(connection, task_id)
            attempt = self._attempt(connection, attempt_id)
            self._assert_nonterminal(task)
            self._assert_expected(task, expected_state_version)
            self._assert_owner(
                task, owner_id=owner_id, owner_epoch=owner_epoch, now=now_value
            )
            if (
                str(attempt["task_id"]) != task_id
                or str(attempt["status"]) == "terminal"
                or int(attempt["owner_epoch"]) != owner_epoch
            ):
                raise ResearchConflict("Attempt 已终态或 owner fence 不一致")
            if (
                not task_terminal
                and next_task_status in {TaskStatus.RUNNING, TaskStatus.TERMINAL}
            ):
                raise ResearchValidationError(
                    "非 Task-terminal completion 只能进入 ready/blocked/waiting_user"
                )
            latest_checkpoint = connection.execute(
                """
                SELECT * FROM research_checkpoints
                WHERE attempt_id=? ORDER BY sequence DESC LIMIT 1
                """,
                (attempt_id,),
            ).fetchone()
            current_checkpoint_id = (
                str(latest_checkpoint["checkpoint_id"])
                if latest_checkpoint is not None
                else None
            )
            if checkpoint_id != current_checkpoint_id:
                raise ResearchConflict("stale expected checkpoint for Result commit")
            if latest_checkpoint is not None and (
                str(latest_checkpoint["task_id"]) != task_id
                or str(latest_checkpoint["attempt_id"]) != attempt_id
            ):
                raise ResearchValidationError("Result checkpoint lineage 不匹配")
            result_id = _new_id("result")
            connection.execute(
                """
                INSERT INTO research_results(
                    result_id, task_id, goal_id, attempt_id, checkpoint_id,
                    answer_status, termination_reason, failure_class, reason_detail,
                    is_task_terminal, owner_epoch, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result_id,
                    task_id,
                    str(attempt["goal_id"]),
                    attempt_id,
                    checkpoint_id,
                    answer_status.value,
                    termination_reason.value,
                    failure_class.value,
                    reason_detail,
                    int(task_terminal),
                    owner_epoch,
                    now,
                ),
            )
            self.fault_injector("after_result_insert")
            connection.execute(
                """
                UPDATE research_attempts
                SET status='terminal', result_id=?, ended_at=?
                WHERE attempt_id=?
                """,
                (result_id, now, attempt_id),
            )
            connection.execute(
                """
                UPDATE research_traces
                SET ended_at=?, termination_reason=?
                WHERE attempt_id=? AND ended_at IS NULL
                """,
                (now, termination_reason.value, attempt_id),
            )
            task_status = (
                TaskStatus.TERMINAL.value if task_terminal else next_task_status.value
            )
            connection.execute(
                """
                UPDATE research_tasks
                SET status=?, terminal_result_id=?,
                    state_version=state_version+1, updated_at=?
                WHERE task_id=?
                """,
                (task_status, result_id if task_terminal else None, now, task_id),
            )
            self._event(
                connection,
                task_id=task_id,
                goal_id=str(attempt["goal_id"]),
                attempt_id=attempt_id,
                checkpoint_id=checkpoint_id,
                event_type=(
                    "task_terminal_result_committed"
                    if task_terminal
                    else "attempt_result_committed"
                ),
                payload={
                    "result_id": result_id,
                    "answer_status": answer_status.value,
                    "termination_reason": termination_reason.value,
                    "failure_class": failure_class.value,
                },
                command_id=command_id,
                owner_epoch=owner_epoch,
                now=now,
            )
            response = {
                "task_id": task_id,
                "attempt_id": attempt_id,
                "result_id": result_id,
                "task_status": task_status,
                "state_version": expected_state_version + 1,
            }
            self._insert_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                command_type="complete_attempt",
                payload_hash=payload_hash,
                outcome_reference=result_id,
                response=response,
                owner_epoch=owner_epoch,
                now=now,
            )
        return response

    def retry_attempt(
        self,
        *,
        task_id: str,
        parent_attempt_id: str,
        command_id: str,
        owner_id: str,
        owner_epoch: int,
        expected_state_version: int,
    ) -> dict[str, Any]:
        return self.start_attempt(
            task_id=task_id,
            command_id=command_id,
            owner_id=owner_id,
            owner_epoch=owner_epoch,
            expected_state_version=expected_state_version,
            cause=AttemptCause.RETRY,
            parent_attempt_id=parent_attempt_id,
        )

    def revise_goal(
        self,
        *,
        task_id: str,
        command_id: str,
        owner_id: str,
        owner_epoch: int,
        expected_state_version: int,
        objective: str,
        success_constraints: list[str],
        evidence_policy: dict[str, Any],
    ) -> dict[str, Any]:
        objective = objective.strip()
        if not objective:
            raise ResearchValidationError("objective 不能为空")
        now_value = self._now()
        now = _iso(now_value)
        payload = {
            "owner_id": owner_id,
            "owner_epoch": owner_epoch,
            "expected_state_version": expected_state_version,
            "objective": objective,
            "success_constraints": success_constraints,
            "evidence_policy": evidence_policy,
        }
        payload_hash = _hash(payload)
        with self._transaction() as connection:
            existing = self._existing_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                payload_hash=payload_hash,
                owner_id=owner_id,
                owner_epoch=owner_epoch,
                now=now_value,
            )
            if existing is not None:
                return existing
            task = self._task(connection, task_id)
            self._assert_nonterminal(task)
            self._assert_expected(task, expected_state_version)
            self._assert_owner(
                task, owner_id=owner_id, owner_epoch=owner_epoch, now=now_value
            )
            active_attempt = connection.execute(
                """
                SELECT attempt_id FROM research_attempts
                WHERE task_id=? AND status!='terminal'
                """,
                (task_id,),
            ).fetchone()
            if active_attempt is not None:
                raise ResearchConflict("goal revision 前必须先终结当前 Attempt")
            previous_goal_id = str(task["active_goal_id"])
            revision = int(
                connection.execute(
                    "SELECT MAX(revision) + 1 FROM research_goals WHERE task_id=?",
                    (task_id,),
                ).fetchone()[0]
            )
            goal_id = _new_id("goal")
            connection.execute(
                """
                INSERT INTO research_goals(
                    goal_id, task_id, revision, parent_goal_id, objective,
                    success_constraints_json, evidence_policy_json,
                    created_by_event_id, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    goal_id,
                    task_id,
                    revision,
                    previous_goal_id,
                    objective,
                    _canonical_json(success_constraints),
                    _canonical_json(evidence_policy),
                    now,
                ),
            )
            ordinal = int(
                connection.execute(
                    "SELECT COALESCE(MAX(ordinal), 0) + 1 FROM research_attempts WHERE task_id=?",
                    (task_id,),
                ).fetchone()[0]
            )
            attempt_id = _new_id("attempt")
            connection.execute(
                """
                INSERT INTO research_attempts(
                    attempt_id, task_id, goal_id, ordinal, cause,
                    parent_attempt_id, source_checkpoint_id, status, owner_epoch,
                    result_id, started_at, ended_at, created_at
                ) VALUES(?, ?, ?, ?, 'goal_revision', NULL, NULL, 'running', ?,
                         NULL, ?, NULL, ?)
                """,
                (attempt_id, task_id, goal_id, ordinal, owner_epoch, now, now),
            )
            trace_id = _new_id("trace")
            connection.execute(
                """
                INSERT INTO research_traces(
                    trace_id, task_id, attempt_id, trace_schema_version,
                    started_at, ended_at, termination_reason, retention_class
                ) VALUES(?, ?, ?, ?, ?, NULL, NULL, 'stage1_kernel')
                """,
                (trace_id, task_id, attempt_id, self.TRACE_SCHEMA_VERSION, now),
            )
            connection.execute(
                """
                UPDATE research_tasks
                SET active_goal_id=?, status='running',
                    state_version=state_version+1, updated_at=?
                WHERE task_id=?
                """,
                (goal_id, now, task_id),
            )
            event_id = self._event(
                connection,
                task_id=task_id,
                goal_id=goal_id,
                attempt_id=attempt_id,
                event_type="goal_revised",
                payload={"revision": revision, "parent_goal_id": previous_goal_id},
                command_id=command_id,
                owner_epoch=owner_epoch,
                now=now,
            )
            connection.execute(
                "UPDATE research_goals SET created_by_event_id=? WHERE goal_id=?",
                (event_id, goal_id),
            )
            response = {
                "task_id": task_id,
                "goal_id": goal_id,
                "attempt_id": attempt_id,
                "trace_id": trace_id,
                "state_version": expected_state_version + 1,
            }
            self._insert_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                command_type="revise_goal",
                payload_hash=payload_hash,
                outcome_reference=goal_id,
                response=response,
                owner_epoch=owner_epoch,
                now=now,
            )
        return response

    def create_child_task(
        self,
        *,
        parent_task_id: str,
        command_id: str,
        objective: str | None = None,
        success_constraints: list[str] | None = None,
        evidence_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self.db.connect() as connection:
            parent = self._task(connection, parent_task_id)
            if str(parent["status"]) != TaskStatus.TERMINAL.value:
                raise ResearchValidationError("child Task 只用于 terminal parent")
            goal = connection.execute(
                "SELECT * FROM research_goals WHERE goal_id=?",
                (str(parent["active_goal_id"]),),
            ).fetchone()
            if goal is None:
                raise ResearchUnsafeState("parent active Goal 不可寻址")
            child_objective = objective.strip() if objective else str(goal["objective"])
            constraints = (
                success_constraints
                if success_constraints is not None
                else list(json.loads(str(goal["success_constraints_json"])))
            )
            policy = (
                evidence_policy
                if evidence_policy is not None
                else dict(json.loads(str(goal["evidence_policy_json"])))
            )
        child_task_id = (
            "rtask_"
            + hashlib.sha256(f"{parent_task_id}:{command_id}".encode()).hexdigest()[:32]
        )
        return self.create_task(
            command_id=command_id,
            task_id=child_task_id,
            parent_task_id=parent_task_id,
            objective=child_objective,
            success_constraints=constraints,
            evidence_policy=policy,
        )

    def cancel_task(
        self,
        *,
        task_id: str,
        attempt_id: str,
        command_id: str,
        owner_id: str,
        owner_epoch: int,
        expected_state_version: int,
        reason_detail: str = "cancel requested",
    ) -> dict[str, Any]:
        return self.complete_attempt(
            task_id=task_id,
            attempt_id=attempt_id,
            command_id=command_id,
            owner_id=owner_id,
            owner_epoch=owner_epoch,
            expected_state_version=expected_state_version,
            answer_status=AnswerStatus.NOT_PRODUCED,
            termination_reason=TerminationReason.CANCELLED,
            failure_class=FailureClass.NONE,
            reason_detail=reason_detail,
            task_terminal=True,
        )

    def reserve_side_effect(
        self,
        *,
        task_id: str,
        attempt_id: str,
        command_id: str,
        owner_id: str,
        owner_epoch: int,
        expected_state_version: int,
        effect_kind: str,
        idempotency_key: str,
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        now_value = self._now()
        now = _iso(now_value)
        request_hash = _hash(request_payload)
        payload = {
            "attempt_id": attempt_id,
            "owner_id": owner_id,
            "owner_epoch": owner_epoch,
            "expected_state_version": expected_state_version,
            "effect_kind": effect_kind,
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
        }
        payload_hash = _hash(payload)
        with self._transaction() as connection:
            existing_receipt = self._existing_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                payload_hash=payload_hash,
                owner_id=owner_id,
                owner_epoch=owner_epoch,
                now=now_value,
            )
            if existing_receipt is not None:
                return existing_receipt
            task = self._task(connection, task_id)
            attempt = self._attempt(connection, attempt_id)
            self._assert_nonterminal(task)
            self._assert_expected(task, expected_state_version)
            self._assert_owner(
                task, owner_id=owner_id, owner_epoch=owner_epoch, now=now_value
            )
            if (
                str(attempt["task_id"]) != task_id
                or str(attempt["status"]) == "terminal"
                or int(attempt["owner_epoch"]) != owner_epoch
            ):
                raise ResearchConflict("Attempt 与 SideEffect owner fence 不一致")
            existing_effect = connection.execute(
                """
                SELECT * FROM research_side_effects
                WHERE task_id=? AND effect_kind=? AND idempotency_key=?
                """,
                (task_id, effect_kind, idempotency_key),
            ).fetchone()
            if existing_effect is not None:
                if str(existing_effect["request_hash"]) != request_hash:
                    raise ResearchUnsafeState(
                        "同一 Task-scoped idempotency key 的 request hash 不一致"
                    )
                side_effect_id = str(existing_effect["side_effect_id"])
                event_type = "side_effect_deduplicated"
            else:
                side_effect_id = _new_id("effect")
                connection.execute(
                    """
                    INSERT INTO research_side_effects(
                        side_effect_id, task_id, attempt_id, command_id,
                        idempotency_key, effect_kind, request_hash, request_json,
                        status, owner_epoch, provider_operation_id, receipt_hash,
                        result_reference, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'reserved', ?, NULL, NULL, NULL, ?, ?)
                    """,
                    (
                        side_effect_id,
                        task_id,
                        attempt_id,
                        command_id,
                        idempotency_key,
                        effect_kind,
                        request_hash,
                        _canonical_json(request_payload),
                        owner_epoch,
                        now,
                        now,
                    ),
                )
                event_type = "side_effect_reserved"
            connection.execute(
                """
                UPDATE research_tasks
                SET state_version=state_version+1, updated_at=?
                WHERE task_id=?
                """,
                (now, task_id),
            )
            self._event(
                connection,
                task_id=task_id,
                goal_id=str(attempt["goal_id"]),
                attempt_id=attempt_id,
                event_type=event_type,
                payload={
                    "side_effect_id": side_effect_id,
                    "effect_kind": effect_kind,
                    "idempotency_key": idempotency_key,
                },
                command_id=command_id,
                owner_epoch=owner_epoch,
                now=now,
            )
            response = {
                "task_id": task_id,
                "side_effect_id": side_effect_id,
                "state_version": expected_state_version + 1,
            }
            self._insert_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                command_type="reserve_side_effect",
                payload_hash=payload_hash,
                outcome_reference=side_effect_id,
                response=response,
                owner_epoch=owner_epoch,
                now=now,
            )
        return response

    def transition_side_effect(
        self,
        *,
        task_id: str,
        side_effect_id: str,
        command_id: str,
        owner_id: str,
        owner_epoch: int,
        expected_state_version: int,
        target_status: str,
        operation_id: str | None = None,
        receipt_hash: str | None = None,
        result_reference: str | None = None,
    ) -> dict[str, Any]:
        if target_status not in {"in_flight", "succeeded", "failed"}:
            raise ResearchValidationError("不支持的 SideEffect transition")
        now_value = self._now()
        now = _iso(now_value)
        payload = {
            "side_effect_id": side_effect_id,
            "owner_id": owner_id,
            "owner_epoch": owner_epoch,
            "expected_state_version": expected_state_version,
            "target_status": target_status,
            "operation_id": operation_id,
            "receipt_hash": receipt_hash,
            "result_reference": result_reference,
        }
        payload_hash = _hash(payload)
        with self._transaction() as connection:
            existing_receipt = self._existing_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                payload_hash=payload_hash,
                owner_id=owner_id,
                owner_epoch=owner_epoch,
                now=now_value,
            )
            if existing_receipt is not None:
                return existing_receipt
            task = self._task(connection, task_id)
            effect = self._side_effect(connection, side_effect_id)
            self._assert_nonterminal(task)
            self._assert_expected(task, expected_state_version)
            self._assert_owner(
                task, owner_id=owner_id, owner_epoch=owner_epoch, now=now_value
            )
            if (
                str(effect["task_id"]) != task_id
                or int(effect["owner_epoch"]) != owner_epoch
            ):
                raise ResearchConflict("SideEffect stale owner fence")
            current = str(effect["status"])
            allowed = (
                current == "reserved" and target_status == "in_flight"
            ) or (
                current == "in_flight" and target_status in {"succeeded", "failed"}
            )
            if not allowed:
                raise ResearchUnsafeState(
                    f"非法 SideEffect transition: {current} -> {target_status}"
                )
            connection.execute(
                """
                UPDATE research_side_effects
                SET status=?, provider_operation_id=COALESCE(?, provider_operation_id),
                    receipt_hash=COALESCE(?, receipt_hash),
                    result_reference=COALESCE(?, result_reference), updated_at=?
                WHERE side_effect_id=?
                """,
                (
                    target_status,
                    operation_id,
                    receipt_hash,
                    result_reference,
                    now,
                    side_effect_id,
                ),
            )
            connection.execute(
                """
                UPDATE research_tasks
                SET state_version=state_version+1, updated_at=?
                WHERE task_id=?
                """,
                (now, task_id),
            )
            event_type = {
                "in_flight": "side_effect_started",
                "succeeded": "side_effect_succeeded",
                "failed": "side_effect_failed",
            }[target_status]
            self._event(
                connection,
                task_id=task_id,
                attempt_id=str(effect["attempt_id"]),
                event_type=event_type,
                payload={
                    "side_effect_id": side_effect_id,
                    "receipt_hash": receipt_hash,
                },
                command_id=command_id,
                owner_epoch=owner_epoch,
                now=now,
            )
            response = {
                "task_id": task_id,
                "side_effect_id": side_effect_id,
                "status": target_status,
                "state_version": expected_state_version + 1,
            }
            self._insert_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                command_type=f"side_effect_{target_status}",
                payload_hash=payload_hash,
                outcome_reference=side_effect_id,
                response=response,
                owner_epoch=owner_epoch,
                now=now,
            )
        return response

    def execute_deterministic_side_effect(
        self,
        *,
        task_id: str,
        attempt_id: str,
        command_id: str,
        owner_id: str,
        owner_epoch: int,
        expected_state_version: int,
        effect_kind: str,
        idempotency_key: str,
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        reserved = self.reserve_side_effect(
            task_id=task_id,
            attempt_id=attempt_id,
            command_id=f"{command_id}:reserve",
            owner_id=owner_id,
            owner_epoch=owner_epoch,
            expected_state_version=expected_state_version,
            effect_kind=effect_kind,
            idempotency_key=idempotency_key,
            request_payload=request_payload,
        )
        side_effect_id = str(reserved["side_effect_id"])
        current_version = int(reserved["state_version"])
        with self.db.connect() as connection:
            effect = self._side_effect(connection, side_effect_id)
            task = self._task(connection, task_id)
            status = str(effect["status"])
            if status in {"succeeded", "failed"}:
                return {
                    "task_id": task_id,
                    "side_effect_id": side_effect_id,
                    "status": status,
                    "state_version": int(task["state_version"]),
                    "deduplicated": True,
                }
            if status != "reserved":
                raise ResearchUnsafeState(
                    f"SideEffect 为 {status}，禁止自动重放 deterministic adapter"
                )
        started = self.transition_side_effect(
            task_id=task_id,
            side_effect_id=side_effect_id,
            command_id=f"{command_id}:start",
            owner_id=owner_id,
            owner_epoch=owner_epoch,
            expected_state_version=current_version,
            target_status="in_flight",
        )
        result = self.effect_adapter.execute(
            effect_kind=effect_kind,
            idempotency_key=idempotency_key,
            payload=request_payload,
        )
        self.fault_injector("after_external_call")
        completed = self.transition_side_effect(
            task_id=task_id,
            side_effect_id=side_effect_id,
            command_id=f"{command_id}:finish",
            owner_id=owner_id,
            owner_epoch=owner_epoch,
            expected_state_version=int(started["state_version"]),
            target_status="succeeded",
            operation_id=str(result["operation_id"]),
            receipt_hash=str(result["receipt_hash"]),
            result_reference=str(result["result_reference"]),
        )
        return {**completed, "deduplicated": False}

    def recover_in_flight(
        self,
        *,
        task_id: str,
        command_id: str,
        owner_id: str,
        owner_epoch: int,
        expected_state_version: int,
    ) -> dict[str, Any]:
        now_value = self._now()
        now = _iso(now_value)
        payload = {
            "owner_id": owner_id,
            "owner_epoch": owner_epoch,
            "expected_state_version": expected_state_version,
        }
        payload_hash = _hash(payload)
        with self._transaction() as connection:
            existing = self._existing_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                payload_hash=payload_hash,
                owner_id=owner_id,
                owner_epoch=owner_epoch,
                now=now_value,
            )
            if existing is not None:
                return existing
            task = self._task(connection, task_id)
            self._assert_nonterminal(task)
            self._assert_expected(task, expected_state_version)
            self._assert_owner(
                task, owner_id=owner_id, owner_epoch=owner_epoch, now=now_value
            )
            rows = connection.execute(
                """
                SELECT * FROM research_side_effects
                WHERE task_id=? AND status='in_flight' AND owner_epoch < ?
                ORDER BY created_at, side_effect_id
                """,
                (task_id, owner_epoch),
            ).fetchall()
            for effect in rows:
                connection.execute(
                    """
                    UPDATE research_side_effects
                    SET status='unknown', updated_at=?
                    WHERE side_effect_id=?
                    """,
                    (now, str(effect["side_effect_id"])),
                )
                self._event(
                    connection,
                    task_id=task_id,
                    attempt_id=str(effect["attempt_id"]),
                    event_type="side_effect_marked_unknown",
                    payload={
                        "side_effect_id": str(effect["side_effect_id"]),
                        "fenced_owner_epoch": int(effect["owner_epoch"]),
                    },
                    command_id=command_id,
                    owner_epoch=owner_epoch,
                    now=now,
                )
            connection.execute(
                """
                UPDATE research_tasks
                SET status=CASE WHEN ? > 0 THEN 'blocked' ELSE status END,
                    state_version=state_version+1, updated_at=?
                WHERE task_id=?
                """,
                (len(rows), now, task_id),
            )
            response = {
                "task_id": task_id,
                "unknown_side_effect_ids": [
                    str(row["side_effect_id"]) for row in rows
                ],
                "state_version": expected_state_version + 1,
            }
            self._insert_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                command_type="recover_in_flight",
                payload_hash=payload_hash,
                outcome_reference=task_id,
                response=response,
                owner_epoch=owner_epoch,
                now=now,
            )
        return response

    def resolve_unknown_side_effect(
        self,
        *,
        task_id: str,
        side_effect_id: str,
        command_id: str,
        owner_id: str,
        owner_epoch: int,
        expected_state_version: int,
        outcome: str,
    ) -> dict[str, Any]:
        if outcome not in {"succeeded", "failed"}:
            raise ResearchValidationError("unknown SideEffect 只能解析为 succeeded/failed")
        now_value = self._now()
        now = _iso(now_value)
        payload = {
            "side_effect_id": side_effect_id,
            "owner_id": owner_id,
            "owner_epoch": owner_epoch,
            "expected_state_version": expected_state_version,
            "outcome": outcome,
        }
        payload_hash = _hash(payload)
        with self._transaction() as connection:
            existing = self._existing_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                payload_hash=payload_hash,
                owner_id=owner_id,
                owner_epoch=owner_epoch,
                now=now_value,
            )
            if existing is not None:
                return existing
            task = self._task(connection, task_id)
            effect = self._side_effect(connection, side_effect_id)
            self._assert_nonterminal(task)
            self._assert_expected(task, expected_state_version)
            self._assert_owner(
                task, owner_id=owner_id, owner_epoch=owner_epoch, now=now_value
            )
            if str(effect["task_id"]) != task_id or str(effect["status"]) != "unknown":
                raise ResearchUnsafeState("SideEffect 不是当前 Task 的 unknown record")
            connection.execute(
                """
                UPDATE research_side_effects
                SET status=?, owner_epoch=?, updated_at=?
                WHERE side_effect_id=?
                """,
                (outcome, owner_epoch, now, side_effect_id),
            )
            connection.execute(
                """
                UPDATE research_tasks
                SET state_version=state_version+1, updated_at=?
                WHERE task_id=?
                """,
                (now, task_id),
            )
            self._event(
                connection,
                task_id=task_id,
                attempt_id=str(effect["attempt_id"]),
                event_type="side_effect_resolved",
                payload={"side_effect_id": side_effect_id, "outcome": outcome},
                command_id=command_id,
                owner_epoch=owner_epoch,
                now=now,
            )
            response = {
                "task_id": task_id,
                "side_effect_id": side_effect_id,
                "status": outcome,
                "state_version": expected_state_version + 1,
            }
            self._insert_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                command_type="resolve_unknown_side_effect",
                payload_hash=payload_hash,
                outcome_reference=side_effect_id,
                response=response,
                owner_epoch=owner_epoch,
                now=now,
            )
        return response

    def checkpoint_lineage(self, checkpoint_id: str, *, max_depth: int = 256) -> list[str]:
        lineage: list[str] = []
        visited: set[str] = set()
        expected_task: str | None = None
        expected_attempt: str | None = None
        current: str | None = checkpoint_id
        with self.db.connect() as connection:
            while current is not None:
                if current in visited:
                    raise ResearchUnsafeState("checkpoint lineage cycle")
                if len(lineage) >= max_depth:
                    raise ResearchUnsafeState("checkpoint lineage depth exceeded")
                row = connection.execute(
                    "SELECT * FROM research_checkpoints WHERE checkpoint_id=?",
                    (current,),
                ).fetchone()
                if row is None:
                    raise ResearchUnsafeState("checkpoint parent 不可寻址")
                task_id = str(row["task_id"])
                attempt_id = str(row["attempt_id"])
                expected_task = expected_task or task_id
                expected_attempt = expected_attempt or attempt_id
                if task_id != expected_task or attempt_id != expected_attempt:
                    raise ResearchUnsafeState("checkpoint lineage 跨 Task/Attempt")
                visited.add(current)
                lineage.append(current)
                current = (
                    str(row["parent_checkpoint_id"])
                    if row["parent_checkpoint_id"] is not None
                    else None
                )
        return lineage

    def task_lineage(self, task_id: str, *, max_depth: int = 256) -> list[str]:
        lineage: list[str] = []
        visited: set[str] = set()
        current: str | None = task_id
        with self.db.connect() as connection:
            while current is not None:
                if current in visited:
                    raise ResearchUnsafeState("task lineage cycle")
                if len(lineage) >= max_depth:
                    raise ResearchUnsafeState("task lineage depth exceeded")
                row = connection.execute(
                    "SELECT task_id, parent_task_id FROM research_tasks WHERE task_id=?",
                    (current,),
                ).fetchone()
                if row is None:
                    raise ResearchUnsafeState("parent Task 不可寻址")
                visited.add(current)
                lineage.append(current)
                current = (
                    str(row["parent_task_id"])
                    if row["parent_task_id"] is not None
                    else None
                )
        return lineage

    @staticmethod
    def _required(value: Any, name: str) -> Any:
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ResearchValidationError(f"{name} 为必填字段")
        return value

    def execute_command(
        self, task_id: str, command: ResearchCommandRequest
    ) -> dict[str, Any]:
        kind = command.kind
        if kind == "claim_owner":
            return self.claim_owner(
                task_id=task_id,
                command_id=command.command_id,
                owner_id=self._required(command.owner_id, "owner_id"),
                expected_state_version=self._required(
                    command.expected_state_version, "expected_state_version"
                ),
                lease_seconds=command.lease_seconds,
            )
        if kind == "renew_owner":
            return self.renew_owner(
                task_id=task_id,
                command_id=command.command_id,
                owner_id=self._required(command.owner_id, "owner_id"),
                owner_epoch=self._required(command.owner_epoch, "owner_epoch"),
                expected_state_version=self._required(
                    command.expected_state_version, "expected_state_version"
                ),
                lease_seconds=command.lease_seconds,
            )
        if kind == "start_attempt":
            return self.start_attempt(
                task_id=task_id,
                command_id=command.command_id,
                owner_id=self._required(command.owner_id, "owner_id"),
                owner_epoch=self._required(command.owner_epoch, "owner_epoch"),
                expected_state_version=self._required(
                    command.expected_state_version, "expected_state_version"
                ),
                cause=command.cause,
                parent_attempt_id=command.parent_attempt_id,
                source_checkpoint_id=command.source_checkpoint_id,
            )
        if kind in {"checkpoint", "resume"}:
            attempt_id = self._required(command.attempt_id, "attempt_id")
            expected_checkpoint_id = command.expected_checkpoint_id
            common = {
                "task_id": task_id,
                "attempt_id": attempt_id,
                "command_id": command.command_id,
                "owner_id": self._required(command.owner_id, "owner_id"),
                "owner_epoch": self._required(command.owner_epoch, "owner_epoch"),
                "expected_state_version": self._required(
                    command.expected_state_version, "expected_state_version"
                ),
            }
            if kind == "resume":
                return self.resume_attempt(
                    **common,
                    expected_checkpoint_id=self._required(
                        expected_checkpoint_id, "expected_checkpoint_id"
                    ),
                )
            return self.commit_checkpoint(
                **common,
                expected_checkpoint_id=expected_checkpoint_id,
                state_payload=command.state_payload,
            )
        if kind == "retry":
            with self.db.connect() as connection:
                task = self._task(connection, task_id)
                terminal = str(task["status"]) == TaskStatus.TERMINAL.value
            if terminal:
                return self.create_child_task(
                    parent_task_id=task_id,
                    command_id=command.command_id,
                    objective=command.objective,
                    success_constraints=(
                        command.success_constraints
                        if command.success_constraints
                        else None
                    ),
                    evidence_policy=(
                        command.evidence_policy if command.evidence_policy else None
                    ),
                )
            return self.retry_attempt(
                task_id=task_id,
                parent_attempt_id=self._required(
                    command.parent_attempt_id, "parent_attempt_id"
                ),
                command_id=command.command_id,
                owner_id=self._required(command.owner_id, "owner_id"),
                owner_epoch=self._required(command.owner_epoch, "owner_epoch"),
                expected_state_version=self._required(
                    command.expected_state_version, "expected_state_version"
                ),
            )
        if kind == "revise_goal":
            with self.db.connect() as connection:
                task = self._task(connection, task_id)
                terminal = str(task["status"]) == TaskStatus.TERMINAL.value
            if terminal:
                return self.create_child_task(
                    parent_task_id=task_id,
                    command_id=command.command_id,
                    objective=self._required(command.objective, "objective"),
                    success_constraints=command.success_constraints,
                    evidence_policy=command.evidence_policy,
                )
            return self.revise_goal(
                task_id=task_id,
                command_id=command.command_id,
                owner_id=self._required(command.owner_id, "owner_id"),
                owner_epoch=self._required(command.owner_epoch, "owner_epoch"),
                expected_state_version=self._required(
                    command.expected_state_version, "expected_state_version"
                ),
                objective=self._required(command.objective, "objective"),
                success_constraints=command.success_constraints,
                evidence_policy=command.evidence_policy,
            )
        if kind in {"complete_attempt", "complete_task"}:
            return self.complete_attempt(
                task_id=task_id,
                attempt_id=self._required(command.attempt_id, "attempt_id"),
                command_id=command.command_id,
                owner_id=self._required(command.owner_id, "owner_id"),
                owner_epoch=self._required(command.owner_epoch, "owner_epoch"),
                expected_state_version=self._required(
                    command.expected_state_version, "expected_state_version"
                ),
                answer_status=command.answer_status,
                termination_reason=command.termination_reason,
                failure_class=command.failure_class,
                reason_detail=command.reason_detail,
                task_terminal=kind == "complete_task",
                next_task_status=command.next_task_status,
                checkpoint_id=command.expected_checkpoint_id,
            )
        if kind == "cancel":
            return self.cancel_task(
                task_id=task_id,
                attempt_id=self._required(command.attempt_id, "attempt_id"),
                command_id=command.command_id,
                owner_id=self._required(command.owner_id, "owner_id"),
                owner_epoch=self._required(command.owner_epoch, "owner_epoch"),
                expected_state_version=self._required(
                    command.expected_state_version, "expected_state_version"
                ),
                reason_detail=command.reason_detail or "cancel requested",
            )
        if kind == "execute_effect":
            return self.execute_deterministic_side_effect(
                task_id=task_id,
                attempt_id=self._required(command.attempt_id, "attempt_id"),
                command_id=command.command_id,
                owner_id=self._required(command.owner_id, "owner_id"),
                owner_epoch=self._required(command.owner_epoch, "owner_epoch"),
                expected_state_version=self._required(
                    command.expected_state_version, "expected_state_version"
                ),
                effect_kind=self._required(command.effect_kind, "effect_kind"),
                idempotency_key=self._required(
                    command.idempotency_key, "idempotency_key"
                ),
                request_payload=command.effect_payload,
            )
        if kind == "recover_effects":
            return self.recover_in_flight(
                task_id=task_id,
                command_id=command.command_id,
                owner_id=self._required(command.owner_id, "owner_id"),
                owner_epoch=self._required(command.owner_epoch, "owner_epoch"),
                expected_state_version=self._required(
                    command.expected_state_version, "expected_state_version"
                ),
            )
        if kind == "resolve_effect":
            return self.resolve_unknown_side_effect(
                task_id=task_id,
                side_effect_id=self._required(
                    command.side_effect_id, "side_effect_id"
                ),
                command_id=command.command_id,
                owner_id=self._required(command.owner_id, "owner_id"),
                owner_epoch=self._required(command.owner_epoch, "owner_epoch"),
                expected_state_version=self._required(
                    command.expected_state_version, "expected_state_version"
                ),
                outcome=command.side_effect_outcome,
            )
        raise ResearchValidationError(f"不支持的 research command: {kind}")
