from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from shiliu.db import Database
from shiliu.research.contracts import AnswerStatus
from shiliu.research.control_contracts import (
    ControlCommandRequest,
    CreateInputRequest,
    DeriveTaskRequest,
    HumanDecisionRequest,
    ResolveSideEffectRequest,
)
from shiliu.research.errors import (
    ResearchConflict,
    ResearchForbidden,
    ResearchNotFound,
    ResearchUnsafeState,
    ResearchValidationError,
)
from shiliu.research.schema import (
    CONTROL_SCHEMA_VERSION,
    DERIVATION_SCHEMA_VERSION,
    INPUT_SCHEMA_VERSION,
)
from shiliu.research.service import (
    ResearchTaskService,
    _canonical_json,
    _hash,
    _iso,
    _new_id,
    _parse_iso,
    _utc_clock,
)


Clock = Callable[[], datetime]
FaultInjector = Callable[[str], None]


ALL_CAPABILITIES = frozenset(
    {
        "control:interrupt",
        "control:resume",
        "control:cancel",
        "input:create",
        "input:decide",
        "side_effect:resolve",
        "task:derive",
    }
)


class ControlAuthorizationPolicy:
    """Server-owned principal registry; payload metadata never grants capability."""

    def __init__(
        self, principals: Mapping[str, frozenset[str] | set[str]] | None = None
    ) -> None:
        configured = principals or {"local_operator": ALL_CAPABILITIES}
        self._principals = {
            str(principal): frozenset(capabilities)
            for principal, capabilities in configured.items()
        }

    def require(self, principal_id: str, capability: str) -> None:
        if capability not in self._principals.get(principal_id, frozenset()):
            raise ResearchForbidden(
                f"server principal {principal_id!r} lacks {capability!r} capability"
            )


class ResearchControlService:
    MAX_AUDIT_METADATA_CHARACTERS = 1000
    MAX_RESPONSE_CHARACTERS = 4000
    MAX_DERIVATION_MANIFEST_CHARACTERS = 8000
    MAX_LINEAGE_DEPTH = 256
    TRACE_SCHEMA_VERSION = "v5-a-stage4-trace-v1"

    def __init__(
        self,
        db: Database,
        *,
        kernel: ResearchTaskService,
        authorization: ControlAuthorizationPolicy | None = None,
        clock: Clock = _utc_clock,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        self.db = db
        self.kernel = kernel
        self.authorization = authorization or ControlAuthorizationPolicy()
        self.clock = clock
        self.fault_injector = fault_injector or (lambda _point: None)

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _active_attempt(
        connection: sqlite3.Connection, task_id: str
    ) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM research_attempts WHERE task_id=? AND status!='terminal' "
            "ORDER BY ordinal DESC LIMIT 1",
            (task_id,),
        ).fetchone()

    @staticmethod
    def _latest_checkpoint(
        connection: sqlite3.Connection, attempt_id: str
    ) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM research_checkpoints WHERE attempt_id=? "
            "ORDER BY sequence DESC LIMIT 1",
            (attempt_id,),
        ).fetchone()

    @staticmethod
    def _control_generation(task: sqlite3.Row) -> int:
        return int(task["control_generation"])

    @staticmethod
    def _assert_control_expected(
        task: sqlite3.Row,
        *,
        expected_state_version: int,
        expected_control_generation: int,
    ) -> None:
        if int(task["state_version"]) != expected_state_version:
            raise ResearchConflict("stale task state for control mutation")
        if int(task["control_generation"]) != expected_control_generation:
            raise ResearchConflict("stale control generation")

    @staticmethod
    def _assert_checkpoint(
        latest: sqlite3.Row | None, expected_checkpoint_id: str | None
    ) -> None:
        current = str(latest["checkpoint_id"]) if latest is not None else None
        if current != expected_checkpoint_id:
            raise ResearchConflict("stale expected checkpoint for control mutation")

    @staticmethod
    def _bounded_json(value: Any, limit: int, label: str) -> str:
        encoded = _canonical_json(value)
        if len(encoded) > limit:
            raise ResearchValidationError(f"{label} exceeds {limit} characters")
        return encoded

    def _fence(
        self,
        connection: sqlite3.Connection,
        *,
        task: sqlite3.Row,
        now: str,
    ) -> tuple[int, int]:
        next_generation = int(task["control_generation"]) + 1
        next_epoch = max(1, int(task["owner_epoch"]) + 1)
        updated = connection.execute(
            """
            UPDATE research_tasks
            SET owner_id=NULL, lease_until=NULL, owner_epoch=?, control_generation=?,
                state_version=state_version+1, updated_at=?
            WHERE task_id=? AND state_version=? AND control_generation=?
            """,
            (
                next_epoch,
                next_generation,
                now,
                str(task["task_id"]),
                int(task["state_version"]),
                int(task["control_generation"]),
            ),
        )
        if updated.rowcount != 1:
            raise ResearchConflict("control fence CAS failed")
        connection.execute(
            "UPDATE research_attempts SET owner_epoch=? "
            "WHERE task_id=? AND status!='terminal'",
            (next_epoch, str(task["task_id"])),
        )
        return next_generation, next_epoch

    def _clone_checkpoint(
        self,
        connection: sqlite3.Connection,
        *,
        checkpoint: sqlite3.Row,
        owner_epoch: int,
        now: str,
    ) -> str:
        checkpoint_id = _new_id("checkpoint")
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
                str(checkpoint["task_id"]),
                str(checkpoint["goal_id"]),
                str(checkpoint["attempt_id"]),
                str(checkpoint["checkpoint_id"]),
                int(checkpoint["sequence"]) + 1,
                str(checkpoint["state_schema_version"]),
                str(checkpoint["state_hash"]),
                str(checkpoint["state_payload_json"]),
                owner_epoch,
                now,
            ),
        )
        return checkpoint_id

    def _insert_control_records(
        self,
        connection: sqlite3.Connection,
        *,
        task_id: str,
        attempt_id: str | None,
        request: ControlCommandRequest,
        payload_hash: str,
        payload_json: str,
        audit_json: str,
        principal_id: str,
        generation: int,
        owner_epoch: int,
        now: str,
    ) -> str:
        request_id = _new_id("control")
        connection.execute(
            """
            INSERT INTO research_control_requests(
                control_request_id, control_schema_version, task_id, attempt_id,
                command_id, request_kind, payload_hash, payload_json,
                audit_actor_metadata_json, principal_id, expected_state_version,
                expected_checkpoint_id, expected_control_generation,
                admitted_control_generation, admitted_owner_epoch, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                CONTROL_SCHEMA_VERSION,
                task_id,
                attempt_id,
                request.command_id,
                request.kind,
                payload_hash,
                payload_json,
                audit_json,
                principal_id,
                request.expected_state_version,
                request.expected_checkpoint_id,
                request.expected_control_generation,
                generation,
                owner_epoch,
                now,
            ),
        )
        self.fault_injector("after_control_request_insert")
        return request_id

    @staticmethod
    def _insert_disposition(
        connection: sqlite3.Connection,
        *,
        request_id: str,
        task_id: str,
        status: str,
        generation: int,
        owner_epoch: int,
        reason: str,
        references: dict[str, Any],
        now: str,
    ) -> str:
        disposition_id = _new_id("control_disposition")
        connection.execute(
            """
            INSERT INTO research_control_dispositions(
                disposition_id, control_request_id, task_id, status,
                observed_control_generation, owner_epoch, reason,
                resulting_references_json, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                disposition_id,
                request_id,
                task_id,
                status,
                generation,
                owner_epoch,
                reason,
                _canonical_json(references),
                now,
            ),
        )
        return disposition_id

    @staticmethod
    def _latest_answer_status(
        connection: sqlite3.Connection, task_id: str
    ) -> str:
        artifact = connection.execute(
            "SELECT answer_status FROM research_provisional_artifacts "
            "WHERE task_id=? ORDER BY created_at DESC, artifact_id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        if artifact is not None and str(artifact["answer_status"]) in {
            AnswerStatus.VALID_PARTIAL.value,
            AnswerStatus.VALID_INSUFFICIENT.value,
        }:
            return str(artifact["answer_status"])
        result = connection.execute(
            "SELECT answer_status FROM research_results WHERE task_id=? "
            "ORDER BY created_at DESC, result_id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        if result is not None and str(result["answer_status"]) in {
            AnswerStatus.VALID_PARTIAL.value,
            AnswerStatus.VALID_INSUFFICIENT.value,
        }:
            return str(result["answer_status"])
        return AnswerStatus.NOT_PRODUCED.value

    def _terminal_cancel(
        self,
        connection: sqlite3.Connection,
        *,
        task: sqlite3.Row,
        attempt: sqlite3.Row | None,
        checkpoint_id: str | None,
        owner_epoch: int,
        reason: str,
        now: str,
    ) -> str:
        task_id = str(task["task_id"])
        result_id = _new_id("result")
        goal_id = (
            str(attempt["goal_id"])
            if attempt is not None
            else str(task["active_goal_id"])
        )
        answer_status = self._latest_answer_status(connection, task_id)
        connection.execute(
            """
            INSERT INTO research_results(
                result_id, task_id, goal_id, attempt_id, checkpoint_id,
                answer_status, termination_reason, failure_class, reason_detail,
                is_task_terminal, owner_epoch, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, 'cancelled', 'none', ?, 1, ?, ?)
            """,
            (
                result_id,
                task_id,
                goal_id,
                str(attempt["attempt_id"]) if attempt is not None else None,
                checkpoint_id,
                answer_status,
                reason or "cancel requested",
                owner_epoch,
                now,
            ),
        )
        if attempt is not None:
            connection.execute(
                "UPDATE research_attempts SET status='terminal', result_id=?, ended_at=? "
                "WHERE attempt_id=?",
                (result_id, now, str(attempt["attempt_id"])),
            )
            connection.execute(
                "UPDATE research_traces SET ended_at=?, termination_reason='cancelled' "
                "WHERE attempt_id=? AND ended_at IS NULL",
                (now, str(attempt["attempt_id"])),
            )
        connection.execute(
            "UPDATE research_tasks SET status='terminal', terminal_result_id=?, updated_at=? "
            "WHERE task_id=?",
            (result_id, now, task_id),
        )
        return result_id

    def apply_control(
        self,
        task_id: str,
        request: ControlCommandRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        self.authorization.require(principal_id, f"control:{request.kind}")
        audit_json = self._bounded_json(
            request.audit_actor_metadata,
            self.MAX_AUDIT_METADATA_CHARACTERS,
            "audit_actor_metadata",
        )
        payload = {**request.model_dump(mode="json"), "principal_id": principal_id}
        payload_json = _canonical_json(payload)
        payload_hash = _hash(payload)
        now = _iso(self._now())
        with self.kernel._transaction() as connection:
            existing = self.kernel._existing_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                payload_hash=payload_hash,
            )
            if existing is not None:
                return {**existing, "deduplicated": True}
            task = self.kernel._task(connection, task_id)
            self.kernel._assert_nonterminal(task)
            self._assert_control_expected(
                task,
                expected_state_version=request.expected_state_version,
                expected_control_generation=request.expected_control_generation,
            )
            attempt = self._active_attempt(connection, task_id)
            latest = (
                self._latest_checkpoint(connection, str(attempt["attempt_id"]))
                if attempt is not None
                else None
            )
            self._assert_checkpoint(latest, request.expected_checkpoint_id)
            if request.kind in {"interrupt", "resume"} and attempt is None:
                raise ResearchUnsafeState(f"{request.kind} requires an active Attempt")
            if request.kind == "resume":
                unresolved = connection.execute(
                    "SELECT COUNT(*) FROM research_side_effects WHERE task_id=? "
                    "AND status IN ('in_flight', 'unknown')",
                    (task_id,),
                ).fetchone()[0]
                if int(unresolved):
                    raise ResearchUnsafeState("unresolved SideEffect blocks resume")
                if str(task["status"]) not in {"blocked", "waiting_user"}:
                    raise ResearchUnsafeState("Task is not durably paused")
                prior = connection.execute(
                    """
                    SELECT 1 FROM research_control_requests cr
                    JOIN research_control_dispositions cd
                      ON cd.control_request_id=cr.control_request_id
                    WHERE cr.task_id=? AND cr.request_kind='interrupt'
                      AND cd.status='applied'
                    LIMIT 1
                    """,
                    (task_id,),
                ).fetchone()
                resolved_input = connection.execute(
                    """
                    SELECT 1 FROM research_input_requests ir
                    JOIN research_input_dispositions idp
                      ON idp.input_request_id=ir.input_request_id
                    WHERE ir.task_id=? AND idp.status='resolved' LIMIT 1
                    """,
                    (task_id,),
                ).fetchone()
                if prior is None and resolved_input is None:
                    raise ResearchUnsafeState("resume lacks interrupt/input lineage")

            generation, owner_epoch = self._fence(
                connection, task=task, now=now
            )
            self.fault_injector("after_control_fence")
            request_id = self._insert_control_records(
                connection,
                task_id=task_id,
                attempt_id=str(attempt["attempt_id"]) if attempt else None,
                request=request,
                payload_hash=payload_hash,
                payload_json=payload_json,
                audit_json=audit_json,
                principal_id=principal_id,
                generation=generation,
                owner_epoch=owner_epoch,
                now=now,
            )
            checkpoint_id = request.expected_checkpoint_id
            result_id: str | None = None
            unknown_ids: list[str] = []
            if request.kind in {"interrupt", "cancel"}:
                rows = connection.execute(
                    "SELECT side_effect_id, attempt_id FROM research_side_effects "
                    "WHERE task_id=? AND status='in_flight'",
                    (task_id,),
                ).fetchall()
                for row in rows:
                    connection.execute(
                        "UPDATE research_side_effects SET status='unknown', updated_at=? "
                        "WHERE side_effect_id=? AND status='in_flight'",
                        (now, str(row["side_effect_id"])),
                    )
                    unknown_ids.append(str(row["side_effect_id"]))
                unknown_ids.extend(
                    str(row[0])
                    for row in connection.execute(
                        "SELECT side_effect_id FROM research_side_effects "
                        "WHERE task_id=? AND status='unknown'",
                        (task_id,),
                    ).fetchall()
                    if str(row[0]) not in unknown_ids
                )
            if request.kind == "cancel":
                connection.execute(
                    "UPDATE research_side_effects SET status='failed', owner_epoch=?, "
                    "updated_at=? WHERE task_id=? AND status='reserved'",
                    (owner_epoch, now, task_id),
                )
                if unknown_ids:
                    if attempt is not None:
                        connection.execute(
                            "UPDATE research_attempts SET status='blocked' WHERE attempt_id=?",
                            (str(attempt["attempt_id"]),),
                        )
                    connection.execute(
                        "UPDATE research_tasks SET status='blocked' WHERE task_id=?",
                        (task_id,),
                    )
                    outcome = "cancel_pending"
                else:
                    result_id = self._terminal_cancel(
                        connection,
                        task=task,
                        attempt=attempt,
                        checkpoint_id=checkpoint_id,
                        owner_epoch=owner_epoch,
                        reason=request.reason,
                        now=now,
                    )
                    outcome = "cancelled"
            elif request.kind == "interrupt":
                if unknown_ids:
                    checkpoint_id = request.expected_checkpoint_id
                elif latest is not None:
                    checkpoint_id = self._clone_checkpoint(
                        connection,
                        checkpoint=latest,
                        owner_epoch=owner_epoch,
                        now=now,
                    )
                assert attempt is not None
                connection.execute(
                    "UPDATE research_attempts SET status='blocked' WHERE attempt_id=?",
                    (str(attempt["attempt_id"]),),
                )
                connection.execute(
                    "UPDATE research_tasks SET status='blocked' WHERE task_id=?",
                    (task_id,),
                )
                outcome = "blocked_external_unknown" if unknown_ids else "interrupted"
            else:
                assert attempt is not None and latest is not None
                checkpoint_id = self._clone_checkpoint(
                    connection,
                    checkpoint=latest,
                    owner_epoch=owner_epoch,
                    now=now,
                )
                connection.execute(
                    "UPDATE research_attempts SET status='running' WHERE attempt_id=?",
                    (str(attempt["attempt_id"]),),
                )
                connection.execute(
                    "UPDATE research_tasks SET status='running' WHERE task_id=?",
                    (task_id,),
                )
                outcome = "resumed"

            references = {
                "checkpoint_id": checkpoint_id,
                "result_id": result_id,
                "unknown_side_effect_ids": sorted(set(unknown_ids)),
            }
            disposition_id = self._insert_disposition(
                connection,
                request_id=request_id,
                task_id=task_id,
                status="applied",
                generation=generation,
                owner_epoch=owner_epoch,
                reason=request.reason,
                references=references,
                now=now,
            )
            self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(task["active_goal_id"]),
                attempt_id=str(attempt["attempt_id"]) if attempt else None,
                checkpoint_id=checkpoint_id,
                event_type=f"control_{request.kind}_applied",
                payload={
                    "control_request_id": request_id,
                    "disposition_id": disposition_id,
                    "control_generation": generation,
                    "outcome": outcome,
                    **references,
                },
                command_id=request.command_id,
                owner_epoch=owner_epoch,
                now=now,
            )
            response = {
                "task_id": task_id,
                "control_request_id": request_id,
                "disposition_id": disposition_id,
                "outcome": outcome,
                "control_generation": generation,
                "owner_epoch": owner_epoch,
                "state_version": request.expected_state_version + 1,
                **references,
            }
            self.fault_injector("after_control_apply")
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type=f"control_{request.kind}",
                payload_hash=payload_hash,
                outcome_reference=result_id or request_id,
                response=response,
                owner_epoch=owner_epoch,
                now=now,
            )
        return {**response, "deduplicated": False}

    def create_input(
        self,
        task_id: str,
        request: CreateInputRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        self.authorization.require(principal_id, "input:create")
        response_schema_json = self._bounded_json(
            request.response_schema, self.MAX_RESPONSE_CHARACTERS, "response_schema"
        )
        payload = {**request.model_dump(mode="json"), "principal_id": principal_id}
        payload_hash = _hash(payload)
        now_value = self._now()
        now = _iso(now_value)
        with self.kernel._transaction() as connection:
            existing = self.kernel._existing_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                payload_hash=payload_hash,
                owner_id=request.owner_id,
                owner_epoch=request.owner_epoch,
                now=now_value,
            )
            if existing is not None:
                return {**existing, "deduplicated": True}
            task = self.kernel._task(connection, task_id)
            attempt = self.kernel._attempt(connection, request.attempt_id)
            self.kernel._assert_nonterminal(task)
            self.kernel._assert_expected(task, request.expected_state_version)
            self.kernel._assert_owner(
                task,
                owner_id=request.owner_id,
                owner_epoch=request.owner_epoch,
                now=now_value,
            )
            if str(task["status"]) != "waiting_user" or str(attempt["status"]) != "waiting_user":
                raise ResearchUnsafeState("InputRequest requires waiting_user state")
            if str(attempt["task_id"]) != task_id:
                raise ResearchValidationError("InputRequest Attempt belongs to another Task")
            latest = self._latest_checkpoint(connection, request.attempt_id)
            self._assert_checkpoint(latest, request.expected_checkpoint_id)
            open_request = connection.execute(
                """
                SELECT 1 FROM research_input_requests ir
                WHERE ir.task_id=? AND NOT EXISTS (
                    SELECT 1 FROM research_input_dispositions idp
                    WHERE idp.input_request_id=ir.input_request_id
                      AND idp.status IN ('resolved', 'cancelled', 'superseded')
                ) LIMIT 1
                """,
                (task_id,),
            ).fetchone()
            if open_request is not None:
                raise ResearchConflict("Task already has an open InputRequest")
            if request.kind == "constraint_choice":
                if request.constraint_id is None or not request.choices:
                    raise ResearchValidationError(
                        "constraint_choice requires constraint_id and choices"
                    )
                constraint = connection.execute(
                    "SELECT * FROM research_constraint_specs WHERE constraint_id=?",
                    (request.constraint_id,),
                ).fetchone()
                if constraint is None or str(constraint["task_id"]) != task_id:
                    raise ResearchValidationError("constraint identity mismatch")
                policy = json.loads(str(constraint["evaluator_policy_json"]))
                allowed = policy.get("allowed_human_options")
                if (
                    policy.get("authority") != "server_registry"
                    or policy.get("human_decidable") is not True
                    or not isinstance(allowed, list)
                    or request.choices != allowed
                ):
                    raise ResearchForbidden(
                        "constraint is not server-registered as exact human_decidable"
                    )
            input_request_id = _new_id("input")
            connection.execute(
                """
                INSERT INTO research_input_requests(
                    input_request_id, input_schema_version, task_id, goal_id,
                    attempt_id, source_checkpoint_id, command_id, request_kind,
                    prompt, choices_json, response_schema_json, constraint_id,
                    payload_hash, owner_epoch, expires_at, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    input_request_id,
                    INPUT_SCHEMA_VERSION,
                    task_id,
                    str(attempt["goal_id"]),
                    request.attempt_id,
                    request.expected_checkpoint_id,
                    request.command_id,
                    request.kind,
                    request.prompt,
                    _canonical_json(request.choices),
                    response_schema_json,
                    request.constraint_id,
                    payload_hash,
                    request.owner_epoch,
                    request.expires_at,
                    now,
                ),
            )
            disposition_id = _new_id("input_disposition")
            connection.execute(
                "INSERT INTO research_input_dispositions("
                "disposition_id, input_request_id, task_id, status, control_generation, "
                "reason, resulting_reference, created_at) "
                "VALUES(?, ?, ?, 'open', ?, '', NULL, ?)",
                (
                    disposition_id,
                    input_request_id,
                    task_id,
                    int(task["control_generation"]),
                    now,
                ),
            )
            connection.execute(
                "UPDATE research_tasks SET state_version=state_version+1, updated_at=? "
                "WHERE task_id=?",
                (now, task_id),
            )
            self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(attempt["goal_id"]),
                attempt_id=request.attempt_id,
                checkpoint_id=request.expected_checkpoint_id,
                event_type="input_request_opened",
                payload={"input_request_id": input_request_id, "kind": request.kind},
                command_id=request.command_id,
                owner_epoch=request.owner_epoch,
                now=now,
            )
            response = {
                "task_id": task_id,
                "input_request_id": input_request_id,
                "input_disposition_id": disposition_id,
                "state_version": request.expected_state_version + 1,
                "control_generation": int(task["control_generation"]),
            }
            self.fault_injector("after_input_request_insert")
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="create_input_request",
                payload_hash=payload_hash,
                outcome_reference=input_request_id,
                response=response,
                owner_epoch=request.owner_epoch,
                now=now,
            )
        return {**response, "deduplicated": False}

    def decide_input(
        self,
        task_id: str,
        request: HumanDecisionRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        self.authorization.require(principal_id, "input:decide")
        response_json = self._bounded_json(
            request.response, self.MAX_RESPONSE_CHARACTERS, "input response"
        )
        payload = {**request.model_dump(mode="json"), "principal_id": principal_id}
        payload_hash = _hash(payload)
        now = _iso(self._now())
        with self.kernel._transaction() as connection:
            existing = self.kernel._existing_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                payload_hash=payload_hash,
            )
            if existing is not None:
                return {**existing, "deduplicated": True}
            task = self.kernel._task(connection, task_id)
            self.kernel._assert_nonterminal(task)
            self._assert_control_expected(
                task,
                expected_state_version=request.expected_state_version,
                expected_control_generation=request.expected_control_generation,
            )
            input_row = connection.execute(
                "SELECT * FROM research_input_requests WHERE input_request_id=?",
                (request.input_request_id,),
            ).fetchone()
            if input_row is None or str(input_row["task_id"]) != task_id:
                raise ResearchNotFound("InputRequest not found for Task")
            terminal_disposition = connection.execute(
                "SELECT * FROM research_input_dispositions WHERE input_request_id=? "
                "AND status IN ('resolved','cancelled','superseded') LIMIT 1",
                (request.input_request_id,),
            ).fetchone()
            if terminal_disposition is not None:
                raise ResearchConflict("InputRequest already disposed")
            if input_row["expires_at"] is not None and _parse_iso(
                str(input_row["expires_at"])
            ) <= self._now():
                raise ResearchConflict("InputRequest expired")
            kind = str(input_row["request_kind"])
            if kind == "clarification" and request.decision_kind != "clarify_goal":
                raise ResearchValidationError("decision kind does not match clarification")
            if kind == "constraint_choice" and request.decision_kind != "select_constraint_option":
                raise ResearchValidationError("decision kind does not match constraint choice")
            attempt = self.kernel._attempt(connection, str(input_row["attempt_id"]))
            if str(attempt["status"]) != "waiting_user":
                raise ResearchConflict("InputRequest Attempt is no longer waiting")
            generation, owner_epoch = self._fence(connection, task=task, now=now)
            decision_id = _new_id("human_decision")
            references: dict[str, Any] = {}
            human_observation: tuple[str, sqlite3.Row, str] | None = None
            if request.decision_kind == "clarify_goal":
                objective = str(request.response.get("objective", "")).strip()
                if not objective:
                    raise ResearchValidationError("clarification objective is required")
                constraints = request.response.get("success_constraints", [])
                policy = request.response.get("evidence_policy", {})
                if not isinstance(constraints, list) or not all(
                    isinstance(value, str) and value.strip() for value in constraints
                ):
                    raise ResearchValidationError("invalid success_constraints")
                if not isinstance(policy, dict):
                    raise ResearchValidationError("invalid evidence_policy")
                checkpoint_id = str(input_row["source_checkpoint_id"])
                result_id = _new_id("result")
                connection.execute(
                    """
                    INSERT INTO research_results(
                        result_id, task_id, goal_id, attempt_id, checkpoint_id,
                        answer_status, termination_reason, failure_class,
                        reason_detail, is_task_terminal, owner_epoch, created_at
                    ) VALUES(?, ?, ?, ?, ?, ?, 'goal_revised', 'none',
                             'human clarification', 0, ?, ?)
                    """,
                    (
                        result_id,
                        task_id,
                        str(attempt["goal_id"]),
                        str(attempt["attempt_id"]),
                        checkpoint_id,
                        self._latest_answer_status(connection, task_id),
                        owner_epoch,
                        now,
                    ),
                )
                connection.execute(
                    "UPDATE research_attempts SET status='terminal', result_id=?, ended_at=? "
                    "WHERE attempt_id=?",
                    (result_id, now, str(attempt["attempt_id"])),
                )
                connection.execute(
                    "UPDATE research_traces SET ended_at=?, termination_reason='goal_revised' "
                    "WHERE attempt_id=? AND ended_at IS NULL",
                    (now, str(attempt["attempt_id"])),
                )
                revision = int(
                    connection.execute(
                        "SELECT MAX(revision)+1 FROM research_goals WHERE task_id=?",
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
                        str(attempt["goal_id"]),
                        objective,
                        _canonical_json(constraints),
                        _canonical_json(policy),
                        now,
                    ),
                )
                child_attempt_id = _new_id("attempt")
                ordinal = int(attempt["ordinal"]) + 1
                connection.execute(
                    """
                    INSERT INTO research_attempts(
                        attempt_id, task_id, goal_id, ordinal, cause,
                        parent_attempt_id, source_checkpoint_id, status, owner_epoch,
                        result_id, started_at, ended_at, created_at
                    ) VALUES(?, ?, ?, ?, 'goal_revision', ?, ?, 'running', ?,
                             NULL, ?, NULL, ?)
                    """,
                    (
                        child_attempt_id,
                        task_id,
                        goal_id,
                        ordinal,
                        str(attempt["attempt_id"]),
                        checkpoint_id,
                        owner_epoch,
                        now,
                        now,
                    ),
                )
                trace_id = _new_id("trace")
                connection.execute(
                    "INSERT INTO research_traces(trace_id, task_id, attempt_id, "
                    "trace_schema_version, started_at, ended_at, termination_reason, "
                    "retention_class) VALUES(?, ?, ?, ?, ?, NULL, NULL, 'stage4_control')",
                    (
                        trace_id,
                        task_id,
                        child_attempt_id,
                        self.TRACE_SCHEMA_VERSION,
                        now,
                    ),
                )
                connection.execute(
                    "UPDATE research_tasks SET active_goal_id=?, status='running' "
                    "WHERE task_id=?",
                    (goal_id, task_id),
                )
                references = {
                    "result_id": result_id,
                    "goal_id": goal_id,
                    "attempt_id": child_attempt_id,
                    "trace_id": trace_id,
                }
                applied_action = "goal_revision"
            else:
                selected = request.response.get("selected_option")
                choices = json.loads(str(input_row["choices_json"]))
                if not isinstance(selected, str) or selected not in choices:
                    raise ResearchValidationError("selected_option is not allowed")
                constraint = connection.execute(
                    "SELECT * FROM research_constraint_specs WHERE constraint_id=?",
                    (str(input_row["constraint_id"]),),
                ).fetchone()
                if constraint is None:
                    raise ResearchUnsafeState("human-decidable constraint disappeared")
                policy = json.loads(str(constraint["evaluator_policy_json"]))
                if (
                    policy.get("authority") != "server_registry"
                    or policy.get("human_decidable") is not True
                    or policy.get("allowed_human_options") != choices
                ):
                    raise ResearchForbidden("constraint lacks server human authority")
                observation_id = _new_id("human_observation")
                human_observation = (observation_id, constraint, selected)
                connection.execute(
                    "UPDATE research_attempts SET status='blocked' WHERE attempt_id=?",
                    (str(attempt["attempt_id"]),),
                )
                connection.execute(
                    "UPDATE research_tasks SET status='blocked' WHERE task_id=?",
                    (task_id,),
                )
                references = {"observation_id": observation_id}
                applied_action = "human_constraint_observation"

            connection.execute(
                """
                INSERT INTO research_human_decisions(
                    decision_id, input_request_id, task_id, command_id,
                    principal_id, decision_kind, response_hash, response_json,
                    applied_action, result_references_json, control_generation,
                    created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    request.input_request_id,
                    task_id,
                    request.command_id,
                    principal_id,
                    request.decision_kind,
                    hashlib.sha256(response_json.encode()).hexdigest(),
                    response_json,
                    applied_action,
                    _canonical_json(references),
                    generation,
                    now,
                ),
            )
            if human_observation is not None:
                observation_id, constraint, selected = human_observation
                connection.execute(
                    """
                    INSERT INTO research_human_constraint_observations(
                        observation_id, task_id, goal_id, attempt_id,
                        constraint_id, decision_id, selected_option,
                        evaluator_policy_version, control_generation, created_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        observation_id,
                        task_id,
                        str(input_row["goal_id"]),
                        str(input_row["attempt_id"]),
                        str(input_row["constraint_id"]),
                        decision_id,
                        selected,
                        str(constraint["evaluator_policy_version"]),
                        generation,
                        now,
                    ),
                )
            disposition_id = _new_id("input_disposition")
            connection.execute(
                "INSERT INTO research_input_dispositions("
                "disposition_id, input_request_id, task_id, status, control_generation, "
                "reason, resulting_reference, created_at) "
                "VALUES(?, ?, ?, 'resolved', ?, '', ?, ?)",
                (
                    disposition_id,
                    request.input_request_id,
                    task_id,
                    generation,
                    decision_id,
                    now,
                ),
            )
            self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(input_row["goal_id"]),
                attempt_id=str(input_row["attempt_id"]),
                checkpoint_id=str(input_row["source_checkpoint_id"]),
                event_type="human_decision_applied",
                payload={
                    "input_request_id": request.input_request_id,
                    "decision_id": decision_id,
                    "decision_kind": request.decision_kind,
                    "control_generation": generation,
                    **references,
                },
                command_id=request.command_id,
                owner_epoch=owner_epoch,
                now=now,
            )
            response = {
                "task_id": task_id,
                "decision_id": decision_id,
                "input_disposition_id": disposition_id,
                "control_generation": generation,
                "owner_epoch": owner_epoch,
                "state_version": request.expected_state_version + 1,
                **references,
            }
            self.fault_injector("after_human_decision_apply")
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="human_decision",
                payload_hash=payload_hash,
                outcome_reference=decision_id,
                response=response,
                owner_epoch=owner_epoch,
                now=now,
            )
        return {**response, "deduplicated": False}

    def resolve_side_effect(
        self,
        task_id: str,
        request: ResolveSideEffectRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        self.authorization.require(principal_id, "side_effect:resolve")
        if request.resolution == "confirmed_succeeded" and (
            not request.receipt_hash or not request.result_reference
        ):
            raise ResearchValidationError(
                "confirmed_succeeded requires receipt_hash and result_reference"
            )
        payload = {**request.model_dump(mode="json"), "principal_id": principal_id}
        payload_hash = _hash(payload)
        now = _iso(self._now())
        with self.kernel._transaction() as connection:
            existing = self.kernel._existing_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                payload_hash=payload_hash,
            )
            if existing is not None:
                return {**existing, "deduplicated": True}
            task = self.kernel._task(connection, task_id)
            self.kernel._assert_nonterminal(task)
            self._assert_control_expected(
                task,
                expected_state_version=request.expected_state_version,
                expected_control_generation=request.expected_control_generation,
            )
            effect = self.kernel._side_effect(connection, request.side_effect_id)
            if str(effect["task_id"]) != task_id or str(effect["status"]) != "unknown":
                raise ResearchUnsafeState("SideEffect is not unresolved for this Task")
            generation, owner_epoch = self._fence(connection, task=task, now=now)
            resolution_id = _new_id("side_effect_resolution")
            connection.execute(
                """
                INSERT INTO research_side_effect_resolutions(
                    resolution_id, side_effect_id, task_id, command_id,
                    principal_id, resolution, reason, receipt_hash,
                    result_reference, control_generation, owner_epoch, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolution_id,
                    request.side_effect_id,
                    task_id,
                    request.command_id,
                    principal_id,
                    request.resolution,
                    request.reason,
                    request.receipt_hash,
                    request.result_reference,
                    generation,
                    owner_epoch,
                    now,
                ),
            )
            effect_status = (
                "succeeded"
                if request.resolution == "confirmed_succeeded"
                else "failed"
            )
            connection.execute(
                "UPDATE research_side_effects SET status=?, owner_epoch=?, "
                "receipt_hash=COALESCE(?, receipt_hash), "
                "result_reference=COALESCE(?, result_reference), updated_at=? "
                "WHERE side_effect_id=? AND status='unknown'",
                (
                    effect_status,
                    owner_epoch,
                    request.receipt_hash,
                    request.result_reference,
                    now,
                    request.side_effect_id,
                ),
            )
            pending_unknown = int(
                connection.execute(
                    "SELECT COUNT(*) FROM research_side_effects WHERE task_id=? "
                    "AND status IN ('in_flight','unknown')",
                    (task_id,),
                ).fetchone()[0]
            )
            pending_cancel = connection.execute(
                """
                SELECT cr.* FROM research_control_requests cr
                JOIN research_control_dispositions cd
                  ON cd.control_request_id=cr.control_request_id
                WHERE cr.task_id=? AND cr.request_kind='cancel' AND cd.status='applied'
                ORDER BY cr.created_at DESC LIMIT 1
                """,
                (task_id,),
            ).fetchone()
            result_id: str | None = None
            if pending_cancel is not None and pending_unknown == 0:
                attempt = self._active_attempt(connection, task_id)
                latest = (
                    self._latest_checkpoint(connection, str(attempt["attempt_id"]))
                    if attempt is not None
                    else None
                )
                result_id = self._terminal_cancel(
                    connection,
                    task=task,
                    attempt=attempt,
                    checkpoint_id=(str(latest["checkpoint_id"]) if latest else None),
                    owner_epoch=owner_epoch,
                    reason="cancel completed after side-effect resolution",
                    now=now,
                )
                outcome = "cancelled"
            else:
                connection.execute(
                    "UPDATE research_tasks SET status='blocked' WHERE task_id=?",
                    (task_id,),
                )
                outcome = "resolved_blocked"
            self.kernel._event(
                connection,
                task_id=task_id,
                attempt_id=str(effect["attempt_id"]),
                event_type="side_effect_resolution_applied",
                payload={
                    "resolution_id": resolution_id,
                    "side_effect_id": request.side_effect_id,
                    "resolution": request.resolution,
                    "result_id": result_id,
                },
                command_id=request.command_id,
                owner_epoch=owner_epoch,
                now=now,
            )
            response = {
                "task_id": task_id,
                "side_effect_id": request.side_effect_id,
                "resolution_id": resolution_id,
                "status": effect_status,
                "outcome": outcome,
                "result_id": result_id,
                "control_generation": generation,
                "owner_epoch": owner_epoch,
                "state_version": request.expected_state_version + 1,
            }
            self.fault_injector("after_side_effect_resolution_apply")
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="resolve_side_effect_human",
                payload_hash=payload_hash,
                outcome_reference=resolution_id,
                response=response,
                owner_epoch=owner_epoch,
                now=now,
            )
        return {**response, "deduplicated": False}

    def _assert_derivation_depth(
        self, connection: sqlite3.Connection, source_task_id: str
    ) -> None:
        current = source_task_id
        visited: set[str] = set()
        for _ in range(self.MAX_LINEAGE_DEPTH):
            if current in visited:
                raise ResearchUnsafeState("TaskDerivation lineage cycle")
            visited.add(current)
            row = connection.execute(
                "SELECT source_task_id FROM research_task_derivations "
                "WHERE child_task_id=?",
                (current,),
            ).fetchone()
            if row is None:
                return
            current = str(row["source_task_id"])
        raise ResearchUnsafeState("TaskDerivation lineage exceeds maximum depth")

    def derive_task(
        self,
        source_task_id: str,
        request: DeriveTaskRequest,
        *,
        principal_id: str,
    ) -> dict[str, Any]:
        self.authorization.require(principal_id, "task:derive")
        if request.kind == "replay" and any(
            value is not None
            for value in (
                request.objective,
                request.success_constraints,
                request.evidence_policy,
            )
        ):
            raise ResearchValidationError("replay forbids Goal overrides")
        payload = {**request.model_dump(mode="json"), "principal_id": principal_id}
        payload_hash = _hash(payload)
        child_task_id = request.child_task_id or (
            "rtask_"
            + hashlib.sha256(
                f"stage4:{source_task_id}:{request.command_id}".encode()
            ).hexdigest()[:32]
        )
        now = _iso(self._now())
        with self.kernel._transaction() as connection:
            existing_derivation = connection.execute(
                "SELECT child_task_id FROM research_task_derivations "
                "WHERE source_task_id=? AND command_id=?",
                (source_task_id, request.command_id),
            ).fetchone()
            if existing_derivation is not None:
                existing = self.kernel._existing_receipt(
                    connection,
                    task_id=str(existing_derivation["child_task_id"]),
                    command_id=request.command_id,
                    payload_hash=payload_hash,
                )
                if existing is None:
                    raise ResearchConflict("TaskDerivation receipt is missing")
                return {**existing, "deduplicated": True}
            existing_child = connection.execute(
                "SELECT 1 FROM research_tasks WHERE task_id=?", (child_task_id,)
            ).fetchone()
            if existing_child is not None:
                existing = self.kernel._existing_receipt(
                    connection,
                    task_id=child_task_id,
                    command_id=request.command_id,
                    payload_hash=payload_hash,
                )
                if existing is None:
                    raise ResearchConflict("derived child_task_id already exists")
                return {**existing, "deduplicated": True}
            source_task = self.kernel._task(connection, source_task_id)
            source_checkpoint = connection.execute(
                "SELECT * FROM research_checkpoints WHERE checkpoint_id=?",
                (request.source_checkpoint_id,),
            ).fetchone()
            if (
                source_checkpoint is None
                or str(source_checkpoint["task_id"]) != source_task_id
                or not bool(source_checkpoint["is_complete"])
            ):
                raise ResearchValidationError("source checkpoint is incomplete or mismatched")
            source_attempt = self.kernel._attempt(
                connection, str(source_checkpoint["attempt_id"])
            )
            source_goal = connection.execute(
                "SELECT * FROM research_goals WHERE goal_id=?",
                (str(source_checkpoint["goal_id"]),),
            ).fetchone()
            if source_goal is None:
                raise ResearchUnsafeState("source Goal is not addressable")
            self._assert_derivation_depth(connection, source_task_id)
            source_manifest = {
                "source_task_id": source_task_id,
                "source_goal_id": str(source_goal["goal_id"]),
                "source_attempt_id": str(source_attempt["attempt_id"]),
                "source_checkpoint_id": request.source_checkpoint_id,
                "source_state_schema_version": str(
                    source_checkpoint["state_schema_version"]
                ),
                "source_state_hash": str(source_checkpoint["state_hash"]),
                "source_owner_epoch": int(source_checkpoint["owner_epoch"]),
                "evidence_identity_ids": [
                    str(row[0])
                    for row in connection.execute(
                        "SELECT DISTINCT evidence_id FROM research_evidence_uses "
                        "WHERE task_id=? ORDER BY evidence_id",
                        (source_task_id,),
                    ).fetchall()
                ],
                "provider_replay": False,
                "side_effect_replay": False,
            }
            manifest_json = self._bounded_json(
                source_manifest,
                self.MAX_DERIVATION_MANIFEST_CHARACTERS,
                "source derivation manifest",
            )
            objective = (
                request.objective.strip()
                if request.objective is not None
                else str(source_goal["objective"])
            )
            if not objective:
                raise ResearchValidationError("derived objective cannot be blank")
            constraints = (
                request.success_constraints
                if request.success_constraints is not None
                else json.loads(str(source_goal["success_constraints_json"]))
            )
            evidence_policy = (
                request.evidence_policy
                if request.evidence_policy is not None
                else json.loads(str(source_goal["evidence_policy_json"]))
            )
            goal_delta = {
                "objective_changed": objective != str(source_goal["objective"]),
                "success_constraints_changed": constraints
                != json.loads(str(source_goal["success_constraints_json"])),
                "evidence_policy_changed": evidence_policy
                != json.loads(str(source_goal["evidence_policy_json"])),
            }
            if request.kind == "branch" and not any(goal_delta.values()):
                raise ResearchValidationError("branch requires an explicit Goal delta")
            child_goal_id = _new_id("goal")
            child_attempt_id = _new_id("attempt")
            child_checkpoint_id = _new_id("checkpoint")
            trace_id = _new_id("trace")
            connection.execute(
                """
                INSERT INTO research_tasks(
                    task_id, parent_task_id, status, active_goal_id, state_version,
                    owner_id, owner_epoch, control_generation, lease_until,
                    terminal_result_id, created_at, updated_at
                ) VALUES(?, NULL, 'blocked', NULL, 0, NULL, 1, 0, NULL, NULL, ?, ?)
                """,
                (child_task_id, now, now),
            )
            connection.execute(
                """
                INSERT INTO research_goals(
                    goal_id, task_id, revision, parent_goal_id, objective,
                    success_constraints_json, evidence_policy_json,
                    created_by_event_id, created_at
                ) VALUES(?, ?, 1, NULL, ?, ?, ?, NULL, ?)
                """,
                (
                    child_goal_id,
                    child_task_id,
                    objective,
                    _canonical_json(constraints),
                    _canonical_json(evidence_policy),
                    now,
                ),
            )
            connection.execute(
                "UPDATE research_tasks SET active_goal_id=? WHERE task_id=?",
                (child_goal_id, child_task_id),
            )
            connection.execute(
                """
                INSERT INTO research_attempts(
                    attempt_id, task_id, goal_id, ordinal, cause,
                    parent_attempt_id, source_checkpoint_id, status, owner_epoch,
                    result_id, started_at, ended_at, created_at
                ) VALUES(?, ?, ?, 1, ?, ?, ?, 'blocked', 1, NULL, ?, NULL, ?)
                """,
                (
                    child_attempt_id,
                    child_task_id,
                    child_goal_id,
                    request.kind,
                    str(source_attempt["attempt_id"]),
                    request.source_checkpoint_id,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO research_checkpoints(
                    checkpoint_id, task_id, goal_id, attempt_id,
                    parent_checkpoint_id, sequence, state_schema_version,
                    state_hash, state_payload_json, is_complete, owner_epoch, created_at
                ) VALUES(?, ?, ?, ?, NULL, 1, ?, ?, ?, 1, 1, ?)
                """,
                (
                    child_checkpoint_id,
                    child_task_id,
                    child_goal_id,
                    child_attempt_id,
                    str(source_checkpoint["state_schema_version"]),
                    str(source_checkpoint["state_hash"]),
                    str(source_checkpoint["state_payload_json"]),
                    now,
                ),
            )
            connection.execute(
                "INSERT INTO research_traces(trace_id, task_id, attempt_id, "
                "trace_schema_version, started_at, ended_at, termination_reason, "
                "retention_class) VALUES(?, ?, ?, ?, ?, NULL, NULL, 'stage4_derivation')",
                (
                    trace_id,
                    child_task_id,
                    child_attempt_id,
                    self.TRACE_SCHEMA_VERSION,
                    now,
                ),
            )
            derivation_id = _new_id("derivation")
            connection.execute(
                """
                INSERT INTO research_task_derivations(
                    derivation_id, derivation_schema_version, source_task_id,
                    source_goal_id, source_attempt_id, source_checkpoint_id,
                    child_task_id, child_goal_id, child_attempt_id, command_id,
                    derivation_kind, source_state_hash, source_manifest_json,
                    goal_delta_json, payload_hash, principal_id, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    derivation_id,
                    DERIVATION_SCHEMA_VERSION,
                    source_task_id,
                    str(source_goal["goal_id"]),
                    str(source_attempt["attempt_id"]),
                    request.source_checkpoint_id,
                    child_task_id,
                    child_goal_id,
                    child_attempt_id,
                    request.command_id,
                    request.kind,
                    str(source_checkpoint["state_hash"]),
                    manifest_json,
                    _canonical_json(goal_delta),
                    payload_hash,
                    principal_id,
                    now,
                ),
            )
            event_id = self.kernel._event(
                connection,
                task_id=child_task_id,
                goal_id=child_goal_id,
                attempt_id=child_attempt_id,
                checkpoint_id=child_checkpoint_id,
                event_type="derived_task_created",
                payload={
                    "derivation_id": derivation_id,
                    "kind": request.kind,
                    "source_task_id": source_task_id,
                    "source_checkpoint_id": request.source_checkpoint_id,
                },
                command_id=request.command_id,
                owner_epoch=1,
                now=now,
            )
            connection.execute(
                "UPDATE research_goals SET created_by_event_id=? WHERE goal_id=?",
                (event_id, child_goal_id),
            )
            response = {
                "task_id": child_task_id,
                "derivation_id": derivation_id,
                "goal_id": child_goal_id,
                "attempt_id": child_attempt_id,
                "checkpoint_id": child_checkpoint_id,
                "trace_id": trace_id,
                "source_task_id": source_task_id,
                "source_checkpoint_id": request.source_checkpoint_id,
                "state_version": 0,
            }
            self.fault_injector("after_task_derivation_apply")
            self.kernel._insert_receipt(
                connection,
                task_id=child_task_id,
                command_id=request.command_id,
                command_type=f"derive_{request.kind}",
                payload_hash=payload_hash,
                outcome_reference=derivation_id,
                response=response,
                owner_epoch=1,
                now=now,
            )
        return {**response, "deduplicated": False}

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        for name in (
            "payload_json",
            "audit_actor_metadata_json",
            "resulting_references_json",
            "choices_json",
            "response_schema_json",
            "response_json",
            "result_references_json",
            "source_manifest_json",
            "goal_delta_json",
        ):
            if name in value:
                raw = value.pop(name)
                value[name.removesuffix("_json")] = json.loads(str(raw)) if raw else None
        return value

    def get_status(self, task_id: str) -> dict[str, Any]:
        with self.db.connect() as connection:
            task = self.kernel._task(connection, task_id)
            tables = {
                "control_requests": (
                    "SELECT * FROM research_control_requests WHERE task_id=? "
                    "ORDER BY created_at, control_request_id"
                ),
                "control_dispositions": (
                    "SELECT * FROM research_control_dispositions WHERE task_id=? "
                    "ORDER BY created_at, disposition_id"
                ),
                "input_requests": (
                    "SELECT * FROM research_input_requests WHERE task_id=? "
                    "ORDER BY created_at, input_request_id"
                ),
                "input_dispositions": (
                    "SELECT * FROM research_input_dispositions WHERE task_id=? "
                    "ORDER BY created_at, disposition_id"
                ),
                "human_decisions": (
                    "SELECT * FROM research_human_decisions WHERE task_id=? "
                    "ORDER BY created_at, decision_id"
                ),
                "human_constraint_observations": (
                    "SELECT * FROM research_human_constraint_observations WHERE task_id=? "
                    "ORDER BY created_at, observation_id"
                ),
                "side_effect_resolutions": (
                    "SELECT * FROM research_side_effect_resolutions WHERE task_id=? "
                    "ORDER BY created_at, resolution_id"
                ),
                "derivations": (
                    "SELECT * FROM research_task_derivations "
                    "WHERE source_task_id=? OR child_task_id=? ORDER BY created_at, derivation_id"
                ),
            }
            status = str(task["status"])
            allowed: list[str] = []
            if status != "terminal":
                allowed.extend(["cancel", "derive"])
                if status == "running":
                    allowed.append("interrupt")
                if status in {"blocked", "waiting_user"}:
                    allowed.append("resume")
            value: dict[str, Any] = {
                "task": self.kernel._decode_row(task),
                "allowed_operations": sorted(allowed),
            }
            for key, query in tables.items():
                params = (task_id, task_id) if key == "derivations" else (task_id,)
                value[key] = [
                    self._decode(row)
                    for row in connection.execute(query, params).fetchall()
                ]
        return value
