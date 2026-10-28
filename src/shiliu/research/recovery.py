from __future__ import annotations

import logging
from shiliu.storage.errors import StorageError
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from shiliu.research.errors import ResearchConflict, ResearchError
from shiliu.research.execution import ResearchExecutionLedger


logger = logging.getLogger(__name__)


def _parse_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class ResearchRecoveryCoordinator:
    """One-process bounded scanner and supervised Provider runner."""

    LEASE_SECONDS = 60
    LEASE_RENEW_SECONDS = 15
    TICK_SECONDS = 5
    SCAN_SECONDS = 2

    def __init__(
        self,
        application: Any,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.application = application
        self.context = application.db.context
        self.ledger = ResearchExecutionLedger(
            application.db, application.research
        )
        self.monotonic = monotonic
        self.wall_clock = wall_clock
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._guard = threading.Lock()
        self._active_task_id: str | None = None

    def start(self) -> None:
        with self._guard:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop,
                name="research-recovery",
                daemon=True,
            )
            self._thread.start()

    def request_stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def stop(self, *, timeout: float = 30) -> None:
        self.request_stop()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)

    def wake(self) -> None:
        self._wake.set()

    def run_once(self) -> str | None:
        if self._stop.is_set():
            return None
        with self.application.db.connect(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT m.task_id FROM research_execution_metadata m
                JOIN research_tasks t ON (t.workspace_id,t.task_id)=(m.workspace_id,m.task_id)
                WHERE m.workspace_id=%s AND t.owner_user_id=%s AND t.status NOT IN ('terminal','waiting_user')
                  AND m.scheduling_intent IN ('queued','manual')
                  AND (
                      m.scheduling_status IN ('queued','running')
                      OR (m.scheduling_status='backoff'
                          AND m.next_retry_at IS NOT NULL AND m.next_retry_at<=clock_timestamp())
                  )
                ORDER BY m.updated_at, m.task_id LIMIT 1
                """,
                (self.context.workspace_id,self.context.user_id),
            ).fetchone()
        if row is None:
            return None
        task_id = str(row["task_id"])
        with self._guard:
            if self._stop.is_set() or self._active_task_id is not None:
                return None
            self._active_task_id = task_id
        try:
            self._run_supervised(task_id)
        finally:
            with self._guard:
                self._active_task_id = None
        return task_id

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                ran = self.run_once()
            except Exception:
                logger.exception("Research recovery scan failed")
                ran = None
            self._wake.wait(0.1 if ran else self.SCAN_SECONDS)
            self._wake.clear()

    def _claim_and_recover(self, task_id: str) -> tuple[str, int] | None:
        kernel=self.application.research
        runner_id=self.application.research_provider_product.runner_id
        with kernel._transaction() as connection:
            task=kernel._task(connection,task_id)
            live=bool(task["lease_valid"])
        if str(task["status"]) in {"terminal","waiting_user","blocked"}:
            return None
        if task.get("owner_id") and str(task["owner_id"]) != runner_id and live:
            return None
        if str(task.get("owner_id") or "") != runner_id or not live:
            claimed = self.application.research.claim_owner(
                task_id=task_id,
                command_id=f"recovery:{task_id}:claim:{task['state_version']}",
                owner_id=runner_id,
                expected_state_version=int(task["state_version"]),
                lease_seconds=self.LEASE_SECONDS,
            )
            owner_epoch = int(claimed["owner_epoch"])
        else:
            owner_epoch = int(task["owner_epoch"])
        current = self.application.research.get_task(task_id)["task"]
        recovered = self.application.research.recover_in_flight(
            task_id=task_id,
            command_id=(
                f"recovery:{task_id}:in-flight:{owner_epoch}:"
                f"{current['state_version']}"
            ),
            owner_id=runner_id,
            owner_epoch=owner_epoch,
            expected_state_version=int(current["state_version"]),
        )
        if recovered["unknown_side_effect_ids"]:
            self.ledger.record_failure(
                task_id, code="provider_outcome_unknown", safe_to_retry=False
            )
            return None
        return runner_id, owner_epoch

    def _run_supervised(self, task_id: str) -> None:
        raw = self.application.research.get_task(task_id)
        local_completion = any(
            receipt.get("command_type") == "provider_deep_finalized"
            for receipt in raw["command_receipts"]
        ) or any(
            checkpoint.get("state_payload", {}).get("phase") == "complete"
            for checkpoint in raw["checkpoints"]
        )
        if local_completion:
            try:
                owner = self._claim_and_recover(task_id)
                if owner is None:
                    return
                budget = (
                    self.application.research_provider_product.provider_run_budget(
                        task_id
                    )
                )
                self.application.research_provider_orchestrator.run_to_boundary(
                    task_id,
                    command_id=f"web:provider-research:{task_id}:run",
                    max_continuation_cycles=1,
                    max_logical_calls=17,
                    max_http_attempts=34,
                    max_input_tokens=140_000,
                    max_output_tokens=31_984,
                    max_wall_time_seconds=360,
                    case_deadline_at=None,
                    run_budget=budget,
                )
                with self.application.research._transaction() as connection:
                    current=self.application.research._task(connection,task_id)
                    if int(current["owner_epoch"]) != owner[1]:
                        raise ResearchConflict("completion belongs to stale owner")
                    connection.execute(
                        """
                        UPDATE research_execution_metadata
                        SET scheduling_intent='none', scheduling_status='complete',
                            resume_reason='completed', updated_at=%s WHERE workspace_id=%s AND task_id=%s
                        """,
                        (
                            self.application.research._now(),
                            self.context.workspace_id,
                            task_id,
                        ),
                    )
            except ResearchConflict as exc:
                if type(exc) is ResearchConflict:
                    return
                self.ledger.record_failure(
                    task_id,
                    code=exc.code,
                    safe_to_retry=self._safe_local_completion_retry(task_id, exc),
                )
            except ResearchError as exc:
                self.ledger.record_failure(
                    task_id,
                    code=exc.code,
                    safe_to_retry=self._safe_local_completion_retry(task_id, exc),
                )
            return
        availability = self.application.provider_research_availability()
        if not bool(availability["available"]):
            self.ledger.record_failure(
                task_id, code="provider_research_unavailable", safe_to_retry=False
            )
            return
        # Tests and bounded adapters may supply a protocol-compatible orchestrator
        # without the production ownership hooks. Preserve their direct semantics;
        # the real orchestrator always exposes its task lock.
        orchestrator = self.application.research_provider_orchestrator
        if not hasattr(orchestrator, "_run_lock"):
            budget = self.application.research_provider_product.provider_run_budget(
                task_id
            )
            try:
                orchestrator.run_to_boundary(
                    task_id,
                    command_id=f"web:provider-research:{task_id}:run",
                    max_continuation_cycles=1,
                    max_logical_calls=17,
                    max_http_attempts=34,
                    max_input_tokens=140_000,
                    max_output_tokens=31_984,
                    max_wall_time_seconds=360,
                    case_deadline_at=None,
                    run_budget=budget,
                )
            except ResearchConflict:
                return
            return
        try:
            owner = self._claim_and_recover(task_id)
        except ResearchConflict:
            # A live lease/competing scheduler is queueing, not an execution failure.
            return
        except StorageError as exc:
            if exc.category in {"lock_timeout","transaction_retryable"}:
                self.ledger.record_failure(
                    task_id, code="database_busy", safe_to_retry=True
                )
                return
            raise
        if owner is None:
            return
        owner_id, owner_epoch = owner
        segment_id, _ = self.ledger.begin_segment(
            task_id=task_id, owner_id=owner_id, owner_epoch=owner_epoch
        )
        budget = self.application.research_provider_product.provider_run_budget(task_id)
        outcome: dict[str, Any] = {}

        def run() -> None:
            try:
                outcome["value"] = (
                    self.application.research_provider_orchestrator.run_to_boundary(
                        task_id,
                        command_id=f"web:provider-research:{task_id}:run",
                        max_continuation_cycles=1,
                        max_logical_calls=17,
                        max_http_attempts=34,
                        max_input_tokens=140_000,
                        max_output_tokens=31_984,
                        max_wall_time_seconds=360,
                        case_deadline_at=None,
                        run_budget=budget,
                    )
                )
            except BaseException as exc:  # propagated after the timing boundary
                outcome["error"] = exc

        worker = threading.Thread(
            target=run, name=f"research-provider-{task_id[-8:]}", daemon=True
        )
        start_mono = previous_mono = self.monotonic()
        previous_wall = self.wall_clock().astimezone(timezone.utc)
        active_elapsed = 0.0
        last_lease = start_mono
        worker.start()
        timing_uncertain = False
        while worker.is_alive():
            worker.join(timeout=min(0.25, self.TICK_SECONDS))
            current_mono = self.monotonic()
            current_wall = self.wall_clock().astimezone(timezone.utc)
            mono_delta = max(0.0, current_mono - previous_mono)
            wall_delta = max(0.0, (current_wall - previous_wall).total_seconds())
            if current_mono - last_lease >= self.LEASE_RENEW_SECONDS:
                self.ledger.renew_lease_only(
                    task_id=task_id,
                    owner_id=owner_id,
                    owner_epoch=owner_epoch,
                    lease_seconds=self.LEASE_SECONDS,
                )
                last_lease = current_mono
            if timing_uncertain:
                continue
            if current_mono - start_mono >= self.TICK_SECONDS:
                classification = "running"
                if wall_delta - mono_delta > max(2.0, self.TICK_SECONDS):
                    classification = "sleep"
                elif (
                    mono_delta > self.TICK_SECONDS * 3
                    and abs(wall_delta - mono_delta) <= 2.0
                ):
                    classification = "uncertain"
                    timing_uncertain = True
                if classification == "running":
                    active_elapsed += mono_delta
                snapshot = self.ledger.tick(
                    task_id=task_id,
                    owner_id=owner_id,
                    owner_epoch=owner_epoch,
                    segment_id=segment_id,
                    elapsed_ms=round(active_elapsed * 1000),
                    interval_classification=classification,
                )
                if snapshot.timing_status in {"uncertain", "exhausted"}:
                    # Python cannot safely kill the in-flight call. Its eventual
                    # receipt/Unknown boundary is preserved; no next call is admitted.
                    timing_uncertain = timing_uncertain or snapshot.timing_status == "uncertain"
                start_mono = current_mono
                previous_mono = current_mono
                previous_wall = current_wall
        end_mono = self.monotonic()
        active_elapsed += max(0.0, end_mono - previous_mono)
        try:
            if not timing_uncertain:
                self.ledger.settle(
                    task_id=task_id,
                    owner_id=owner_id,
                    owner_epoch=owner_epoch,
                    segment_id=segment_id,
                    elapsed_ms=round(active_elapsed * 1000),
                    scheduling_status="complete"
                    if "error" not in outcome
                    else "manual_required",
                    resume_reason="completed" if "error" not in outcome else None,
                )
        except ResearchConflict:
            # A lost owner may not settle or refund the old segment.
            pass
        error = outcome.get("error")
        if error is None:
            return
        if type(error) is ResearchConflict:
            return
        try:
            self.application.research_provider_product.close_provider_failure(
                task_id,
                command_id=f"web:provider-research:{task_id}:provider-failure",
                cause=error,
            )
        except ResearchError:
            logger.exception("Could not durably close Provider Research failure")
        safe_local_retry = self._safe_local_completion_retry(task_id, error)
        self.ledger.record_failure(
            task_id,
            code=type(error).__name__,
            safe_to_retry=safe_local_retry,
        )

    def _safe_local_completion_retry(self, task_id: str, error: BaseException) -> bool:
        if isinstance(error, StorageError) and error.category in {"lock_timeout","transaction_retryable"}:
            return True
        raw = self.application.research.get_task(task_id)
        effects = list(raw["side_effects"])
        return bool(effects) and all(
            str(effect["status"]) in {"succeeded", "failed"} for effect in effects
        ) and any(str(effect["status"]) == "succeeded" for effect in effects)
