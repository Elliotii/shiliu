from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from shiliu.db import Database
from shiliu.research.errors import ResearchConflict, ResearchUnsafeState
from shiliu.research.schema import RESEARCH_ACTIVE_TIME_POLICY_VERSION
from shiliu.research.service import ResearchTaskService


DEFAULT_ACTIVE_BUDGET_MS = 360_000
DEFAULT_TICK_RESERVATION_MS = 5_000


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class ActiveTimeSnapshot:
    task_id: str
    time_policy_version: str
    active_budget_ms: int
    consumed_active_ms: int
    reserved_tail_ms: int
    timing_status: str
    scheduling_intent: str
    scheduling_status: str
    automatic_failure_count: int
    lifetime_automatic_failure_count: int
    manual_generation: int
    next_retry_at: str | None
    resume_reason: str | None
    last_failure_code: str | None
    segment_id: str | None

    @property
    def remaining_active_ms(self) -> int:
        return max(
            0,
            self.active_budget_ms
            - self.consumed_active_ms
            - self.reserved_tail_ms,
        )

    def projection(self) -> dict[str, Any]:
        return {
            "time_policy_version": self.time_policy_version,
            "active_budget_ms": self.active_budget_ms,
            "consumed_active_ms": self.consumed_active_ms,
            "reserved_tail_ms": self.reserved_tail_ms,
            "remaining_active_ms": self.remaining_active_ms,
            "timing_status": self.timing_status,
            "scheduling_intent": self.scheduling_intent,
            "scheduling_status": self.scheduling_status,
            "automatic_failure_count": self.automatic_failure_count,
            "lifetime_automatic_failure_count": self.lifetime_automatic_failure_count,
            "manual_generation": self.manual_generation,
            "next_retry_at": self.next_retry_at,
            "resume_reason": self.resume_reason,
            "last_failure_code": self.last_failure_code,
            "active_time_is_approximate": True,
        }


class ResearchExecutionLedger:
    """Fenced active-time and scheduling state for product Provider Research.

    Ticks never mutate ``research_tasks.state_version``. A segment persists a
    single short reservation so a hard exit cannot repeatedly earn free time.
    Normal ticks settle the *complete* observed monotonic delta; five seconds is
    only the persistence/reservation cadence.
    """

    def __init__(
        self,
        db: Database,
        kernel: ResearchTaskService,
        *,
        reservation_ms: int = DEFAULT_TICK_RESERVATION_MS,
    ) -> None:
        if reservation_ms <= 0:
            raise ValueError("reservation_ms must be positive")
        self.db = db
        self.kernel = kernel
        self.reservation_ms = int(reservation_ms)

    @staticmethod
    def insert_v2(
        connection: Any,
        *,
        task_id: str,
        now: str,
        run_command_id: str,
        run_immediately: bool,
        active_budget_ms: int = DEFAULT_ACTIVE_BUDGET_MS,
    ) -> None:
        connection.execute(
            """
            INSERT INTO research_execution_metadata(
                task_id, time_policy_version, active_budget_ms,
                scheduling_intent, scheduling_status, run_command_id,
                resume_reason, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                RESEARCH_ACTIVE_TIME_POLICY_VERSION,
                int(active_budget_ms),
                "queued" if run_immediately else "none",
                "queued" if run_immediately else "idle",
                run_command_id,
                "initial_run_requested" if run_immediately else None,
                now,
                now,
            ),
        )

    def snapshot(self, task_id: str, *, required: bool = True) -> ActiveTimeSnapshot | None:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM research_execution_metadata WHERE task_id=?",
                (task_id,),
            ).fetchone()
        if row is None:
            if required:
                raise ResearchUnsafeState(
                    "legacy_time_unaccounted: active-time budget cannot be established"
                )
            return None
        return self._snapshot(row)

    @staticmethod
    def _snapshot(row: Any) -> ActiveTimeSnapshot:
        return ActiveTimeSnapshot(
            task_id=str(row["task_id"]),
            time_policy_version=str(row["time_policy_version"]),
            active_budget_ms=int(row["active_budget_ms"]),
            consumed_active_ms=int(row["consumed_active_ms"]),
            reserved_tail_ms=int(row["reserved_tail_ms"]),
            timing_status=str(row["timing_status"]),
            scheduling_intent=str(row["scheduling_intent"]),
            scheduling_status=str(row["scheduling_status"]),
            automatic_failure_count=int(row["automatic_failure_count"]),
            lifetime_automatic_failure_count=int(
                row["lifetime_automatic_failure_count"]
            ),
            manual_generation=int(row["manual_generation"]),
            next_retry_at=(str(row["next_retry_at"]) if row["next_retry_at"] else None),
            resume_reason=(str(row["resume_reason"]) if row["resume_reason"] else None),
            last_failure_code=(
                str(row["last_failure_code"]) if row["last_failure_code"] else None
            ),
            segment_id=(str(row["segment_id"]) if row["segment_id"] else None),
        )

    def enqueue(
        self,
        task_id: str,
        *,
        command_id: str,
        manual: bool,
        reason: str,
    ) -> ActiveTimeSnapshot:
        now = _iso(self.kernel._now())
        with self.kernel._transaction() as connection:
            task = self.kernel._task(connection, task_id)
            if str(task["status"]) == "terminal":
                raise ResearchUnsafeState("terminal Task cannot be scheduled")
            row = connection.execute(
                "SELECT * FROM research_execution_metadata WHERE task_id=?",
                (task_id,),
            ).fetchone()
            if row is None:
                raise ResearchUnsafeState(
                    "legacy_time_unaccounted: old active Task cannot receive new budget"
                )
            if str(row["timing_status"]) in {"uncertain", "exhausted"}:
                raise ResearchUnsafeState(
                    f"active-time state is {row['timing_status']}; "
                    "resolution is required before execution"
                )
            generation = int(row["manual_generation"]) + (1 if manual else 0)
            automatic = 0 if manual else int(row["automatic_failure_count"])
            connection.execute(
                """
                UPDATE research_execution_metadata
                SET scheduling_intent=?, scheduling_status='queued',
                    run_command_id=?, resume_reason=?, manual_generation=?,
                    automatic_failure_count=?, next_retry_at=NULL, updated_at=?
                WHERE task_id=?
                """,
                (
                    "manual" if manual else "queued",
                    command_id,
                    reason,
                    generation,
                    automatic,
                    now,
                    task_id,
                ),
            )
            result = connection.execute(
                "SELECT * FROM research_execution_metadata WHERE task_id=?",
                (task_id,),
            ).fetchone()
        return self._snapshot(result)

    def begin_segment(
        self, *, task_id: str, owner_id: str, owner_epoch: int
    ) -> tuple[str, ActiveTimeSnapshot]:
        now_value = self.kernel._now()
        now = _iso(now_value)
        segment_id = f"rseg_{uuid.uuid4().hex}"
        with self.kernel._transaction() as connection:
            task = self.kernel._task(connection, task_id)
            self.kernel._assert_owner(
                task, owner_id=owner_id, owner_epoch=owner_epoch, now=now_value
            )
            row = connection.execute(
                "SELECT * FROM research_execution_metadata WHERE task_id=?",
                (task_id,),
            ).fetchone()
            if row is None:
                raise ResearchUnsafeState("legacy_time_unaccounted")
            if row["segment_id"] is not None:
                if (
                    str(row["segment_owner_id"]) == owner_id
                    and int(row["segment_owner_epoch"]) == owner_epoch
                ):
                    return str(row["segment_id"]), self._snapshot(row)
                # A dead process can only lose its one already-reserved tail.
                recovered = min(
                    int(row["reserved_tail_ms"]),
                    max(0, int(row["active_budget_ms"]) - int(row["consumed_active_ms"])),
                )
                connection.execute(
                    """
                    UPDATE research_execution_metadata
                    SET consumed_active_ms=consumed_active_ms+?, reserved_tail_ms=0,
                        segment_id=NULL, segment_owner_id=NULL,
                        segment_owner_epoch=NULL, segment_settled_ms=0,
                        timing_status=CASE
                            WHEN consumed_active_ms+? >= active_budget_ms
                            THEN 'exhausted' ELSE 'idle' END,
                        updated_at=? WHERE task_id=?
                    """,
                    (recovered, recovered, now, task_id),
                )
                row = connection.execute(
                    "SELECT * FROM research_execution_metadata WHERE task_id=?",
                    (task_id,),
                ).fetchone()
            if str(row["timing_status"]) == "uncertain":
                raise ResearchUnsafeState("execution_time_uncertain")
            remaining = int(row["active_budget_ms"]) - int(row["consumed_active_ms"])
            if remaining <= 0:
                connection.execute(
                    "UPDATE research_execution_metadata SET timing_status='exhausted', "
                    "scheduling_status='manual_required', updated_at=? WHERE task_id=?",
                    (now, task_id),
                )
                raise ResearchUnsafeState("research active-time budget is exhausted")
            reserved = min(self.reservation_ms, remaining)
            connection.execute(
                """
                UPDATE research_execution_metadata
                SET segment_id=?, segment_owner_id=?, segment_owner_epoch=?,
                    segment_settled_ms=0, reserved_tail_ms=?, tick_sequence=tick_sequence+1,
                    timing_status='active', scheduling_status='running', updated_at=?
                WHERE task_id=?
                """,
                (segment_id, owner_id, owner_epoch, reserved, now, task_id),
            )
            result = connection.execute(
                "SELECT * FROM research_execution_metadata WHERE task_id=?",
                (task_id,),
            ).fetchone()
        return segment_id, self._snapshot(result)

    def tick(
        self,
        *,
        task_id: str,
        owner_id: str,
        owner_epoch: int,
        segment_id: str,
        elapsed_ms: int,
        interval_classification: str = "running",
    ) -> ActiveTimeSnapshot:
        if elapsed_ms < 0:
            raise ValueError("elapsed_ms must not be negative")
        if interval_classification not in {"running", "sleep", "uncertain"}:
            raise ValueError("invalid interval classification")
        now_value = self.kernel._now()
        now = _iso(now_value)
        with self.kernel._transaction() as connection:
            task = self.kernel._task(connection, task_id)
            self.kernel._assert_owner(
                task, owner_id=owner_id, owner_epoch=owner_epoch, now=now_value
            )
            row = connection.execute(
                "SELECT * FROM research_execution_metadata WHERE task_id=?",
                (task_id,),
            ).fetchone()
            if (
                row is None
                or str(row["segment_id"] or "") != segment_id
                or str(row["segment_owner_id"] or "") != owner_id
                or int(row["segment_owner_epoch"] or -1) != owner_epoch
            ):
                raise ResearchConflict("stale active-time segment fence")
            if interval_classification == "uncertain":
                connection.execute(
                    """
                    UPDATE research_execution_metadata
                    SET timing_status='uncertain', scheduling_status='manual_required',
                        scheduling_intent='none', resume_reason='execution_time_uncertain',
                        last_failure_code='execution_time_uncertain', updated_at=?
                    WHERE task_id=?
                    """,
                    (now, task_id),
                )
            elif interval_classification == "running":
                settled = int(row["segment_settled_ms"])
                delta = max(0, int(elapsed_ms) - settled)
                consumed = int(row["consumed_active_ms"]) + delta
                budget = int(row["active_budget_ms"])
                remaining = max(0, budget - consumed)
                reserved = min(self.reservation_ms, remaining)
                exhausted = consumed >= budget
                connection.execute(
                    """
                    UPDATE research_execution_metadata
                    SET consumed_active_ms=?, segment_settled_ms=?, reserved_tail_ms=?,
                        tick_sequence=tick_sequence+1, timing_status=?,
                        scheduling_status=CASE WHEN ? THEN 'manual_required'
                                               ELSE scheduling_status END,
                        resume_reason=CASE WHEN ? THEN 'active_time_exhausted'
                                           ELSE resume_reason END,
                        updated_at=? WHERE task_id=?
                    """,
                    (
                        consumed,
                        int(elapsed_ms),
                        reserved,
                        "exhausted" if exhausted else "active",
                        exhausted,
                        exhausted,
                        now,
                        task_id,
                    ),
                )
            # Confirmed sleep advances neither settled elapsed nor consumed time.
            result = connection.execute(
                "SELECT * FROM research_execution_metadata WHERE task_id=?",
                (task_id,),
            ).fetchone()
        return self._snapshot(result)

    def settle(
        self,
        *,
        task_id: str,
        owner_id: str,
        owner_epoch: int,
        segment_id: str,
        elapsed_ms: int,
        scheduling_status: str = "idle",
        resume_reason: str | None = None,
    ) -> ActiveTimeSnapshot:
        snapshot = self.tick(
            task_id=task_id,
            owner_id=owner_id,
            owner_epoch=owner_epoch,
            segment_id=segment_id,
            elapsed_ms=elapsed_ms,
        )
        now = _iso(self.kernel._now())
        with self.kernel._transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE research_execution_metadata
                SET segment_id=NULL, segment_owner_id=NULL, segment_owner_epoch=NULL,
                    segment_settled_ms=0, reserved_tail_ms=0,
                    timing_status=CASE WHEN consumed_active_ms >= active_budget_ms
                                       THEN 'exhausted' ELSE 'idle' END,
                    scheduling_status=CASE WHEN consumed_active_ms >= active_budget_ms
                                           THEN 'manual_required' ELSE ? END,
                    scheduling_intent='none', resume_reason=COALESCE(?, resume_reason),
                    updated_at=?
                WHERE task_id=? AND segment_id=? AND segment_owner_id=?
                  AND segment_owner_epoch=?
                """,
                (
                    scheduling_status,
                    resume_reason,
                    now,
                    task_id,
                    segment_id,
                    owner_id,
                    owner_epoch,
                ),
            )
            if cursor.rowcount != 1:
                raise ResearchConflict("stale active-time segment settle")
            row = connection.execute(
                "SELECT * FROM research_execution_metadata WHERE task_id=?",
                (task_id,),
            ).fetchone()
        return self._snapshot(row)

    def renew_lease_only(
        self, *, task_id: str, owner_id: str, owner_epoch: int, lease_seconds: int
    ) -> str:
        now_value = self.kernel._now()
        now = _iso(now_value)
        expires = _iso(now_value + timedelta(seconds=lease_seconds))
        with self.kernel._transaction() as connection:
            task = self.kernel._task(connection, task_id)
            self.kernel._assert_owner(
                task, owner_id=owner_id, owner_epoch=owner_epoch, now=now_value
            )
            cursor = connection.execute(
                """
                UPDATE research_tasks SET lease_until=?, updated_at=?
                WHERE task_id=? AND owner_id=? AND owner_epoch=?
                """,
                (expires, now, task_id, owner_id, owner_epoch),
            )
            if cursor.rowcount != 1:
                raise ResearchConflict("lease-only renewal fence failed")
        return expires

    def record_failure(
        self, task_id: str, *, code: str, safe_to_retry: bool
    ) -> ActiveTimeSnapshot:
        now_value = self.kernel._now()
        now = _iso(now_value)
        with self.kernel._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM research_execution_metadata WHERE task_id=?",
                (task_id,),
            ).fetchone()
            if row is None:
                raise ResearchUnsafeState("legacy_time_unaccounted")
            count = int(row["automatic_failure_count"])
            if safe_to_retry and count < 2:
                delay = (5, 30)[count]
                status = "backoff"
                next_retry = _iso(now_value + timedelta(seconds=delay))
                intent = "queued"
                count += 1
            else:
                status = "manual_required"
                next_retry = None
                intent = "none"
            connection.execute(
                """
                UPDATE research_execution_metadata
                SET automatic_failure_count=?,
                    lifetime_automatic_failure_count=lifetime_automatic_failure_count+1,
                    scheduling_status=?, scheduling_intent=?, next_retry_at=?,
                    last_failure_code=?, resume_reason=?, updated_at=?
                WHERE task_id=?
                """,
                (
                    count,
                    status,
                    intent,
                    next_retry,
                    code,
                    "safe_retry_backoff" if next_retry else code,
                    now,
                    task_id,
                ),
            )
            result = connection.execute(
                "SELECT * FROM research_execution_metadata WHERE task_id=?",
                (task_id,),
            ).fetchone()
        return self._snapshot(result)
