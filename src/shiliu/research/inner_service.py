from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from typing import Any, Callable
from uuid import uuid4

from shiliu.ask.context import TranscriptContextBuilder
from shiliu.ask.contracts import AnswerBlock, GroundedAnswerDraft, TranscriptEvidenceSpan
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.ask.validation import validate_grounded_answer
from shiliu.db import Database
from shiliu.research.errors import (
    ResearchConflict,
    ResearchError,
    ResearchUnsafeState,
    ResearchValidationError,
    SimulatedCrash,
)
from shiliu.research.inner_contracts import (
    ContinueInnerResearchRequest,
    InnerBudgetLedger,
    InnerContinueResponse,
    InnerResearchState,
    ProgressDelta,
    RevalidateInnerEvidenceRequest,
)
from shiliu.research.inner_evidence import (
    CurrentnessResult,
    PersistentEvidenceAuthority,
    canonical_hash,
    evidence_identity_payload,
    provenance_payloads,
)
from shiliu.research.inner_tools import InnerToolAdapter
from shiliu.research.schema import (
    EVIDENCE_USE_SCHEMA_VERSION,
    EVIDENCE_VALIDATION_POLICY_VERSION,
    INNER_ACTION_SCHEMA_VERSION,
    INNER_RESEARCH_STATE_SCHEMA_VERSION,
    PROVISIONAL_ARTIFACT_SCHEMA_VERSION,
)
from shiliu.research.service import ResearchTaskService


Clock = Callable[[], datetime]
FaultInjector = Callable[[str], None]
GroundedValidator = Callable[..., Any]


def _utc_clock() -> datetime:
    return datetime.now(timezone.utc)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


@dataclass(frozen=True)
class _PreparedAction:
    kind: str
    action_key: str
    request_payload: dict[str, Any]
    observation: dict[str, Any]
    spans: tuple[TranscriptEvidenceSpan, ...] = ()
    stale_reasons: tuple[str, ...] = ()
    focused_video_ids: tuple[int, ...] = ()
    error_code: str | None = None
    error_detail: str | None = None


class _PreActionBudgetExhausted(RuntimeError):
    def __init__(self, dimension: str) -> None:
        super().__init__(dimension)
        self.dimension = dimension


class _SynthesisImplementationError(RuntimeError):
    def __init__(self, cause: Exception) -> None:
        super().__init__(f"{type(cause).__name__}: {cause}")
        self.cause = cause


class InnerResearchService:
    MAX_DECISION_ROUNDS = 6
    MAX_RESEARCH_ACTIONS = 12
    MAX_WINDOW_READS = 4
    MAX_CONSECUTIVE_NO_PROGRESS = 2
    MAX_EVIDENCE_USES = 24
    MAX_CONTEXT_CHARACTERS = 12_000
    MAX_RUNTIME_SECONDS = 360
    GENERATION_POLICY_VERSION = "v5-a-stage2-deterministic-extractive-v1"
    VALIDATOR_POLICY_VERSION = "v4-grounded-answer-validation-v1"

    def __init__(
        self,
        *,
        db: Database,
        kernel: ResearchTaskService,
        tools: InnerToolAdapter,
        materializer: TranscriptEvidenceMaterializer | None = None,
        authority: PersistentEvidenceAuthority | None = None,
        context_builder: TranscriptContextBuilder | None = None,
        grounded_validator: GroundedValidator = validate_grounded_answer,
        clock: Clock = _utc_clock,
        fault_injector: FaultInjector | None = None,
        provider_runs_authorized: bool = False,
    ) -> None:
        self.db = db
        self.kernel = kernel
        self.tools = tools
        self.materializer = materializer or TranscriptEvidenceMaterializer(db)
        self.authority = authority or PersistentEvidenceAuthority(db)
        self.context_builder = context_builder or TranscriptContextBuilder(
            total_character_budget=self.MAX_CONTEXT_CHARACTERS
        )
        self.grounded_validator = grounded_validator
        self.clock = clock
        self.fault_injector = fault_injector or (lambda _point: None)
        self.provider_runs_authorized = provider_runs_authorized

    def continue_run(
        self, task_id: str, request: ContinueInnerResearchRequest
    ) -> dict[str, Any]:
        payload = {
            "operation": "continue_inner",
            **request.model_dump(mode="json"),
        }
        payload_hash = canonical_hash(payload)
        preflight = self._preflight(task_id, request, payload_hash)
        if preflight is not None:
            return {**preflight, "deduplicated": True}
        state, objective = self._load_state(task_id, request)
        budget_dimension = self._pre_action_budget_dimension(
            state, self._now()
        )
        if budget_dimension is not None:
            return self._commit_durable_stop(
                task_id=task_id,
                request=request,
                payload_hash=payload_hash,
                budget_dimension=budget_dimension,
            )
        if request.execution_mode == "provider":
            if not self.provider_runs_authorized:
                raise ResearchUnsafeState(
                    "Stage 2 真实 Provider run 未获单独授权"
                )
            raise ResearchUnsafeState(
                "Provider wiring 只可经 SideEffect protocol 调用；当前入口未启用"
            )
        prepared = self._prepare_action(state, objective)
        try:
            return self._commit(
                task_id=task_id,
                request=request,
                payload_hash=payload_hash,
                prepared=prepared,
            )
        except _PreActionBudgetExhausted as exc:
            return self._commit_durable_stop(
                task_id=task_id,
                request=request,
                payload_hash=payload_hash,
                budget_dimension=exc.dimension,
            )
        except _SynthesisImplementationError as exc:
            self.fault_injector("before_inner_failure_commit")
            return self._commit_implementation_failure(
                task_id=task_id,
                request=request,
                payload_hash=payload_hash,
                prepared=prepared,
                cause=exc.cause,
            )

    def get_inner_state(self, task_id: str) -> dict[str, Any]:
        with self.db.connect() as connection:
            self.kernel._task(connection, task_id)
            rows = {
                "inner_actions": connection.execute(
                    """
                    SELECT * FROM research_inner_actions
                    WHERE task_id=? ORDER BY created_at, action_id
                    """,
                    (task_id,),
                ).fetchall(),
                "evidence_uses": connection.execute(
                    """
                    SELECT eu.*, ei.citation_identity_version,
                           ei.video_id, ei.source_artifact_id, ei.source_version,
                           ei.timeline_run_id, ei.segment_ids_json,
                           ei.segment_ordinals_json, ei.start_time, ei.end_time,
                           ei.quote_hash, ei.quote_preview
                    FROM research_evidence_uses eu
                    JOIN research_evidence_identities ei
                      ON ei.evidence_id=eu.evidence_id
                    WHERE eu.task_id=?
                    ORDER BY eu.created_at, eu.evidence_use_id
                    """,
                    (task_id,),
                ).fetchall(),
                "evidence_provenance": connection.execute(
                    """
                    SELECT ep.* FROM research_evidence_provenance ep
                    JOIN research_evidence_uses eu
                      ON eu.evidence_use_id=ep.evidence_use_id
                    WHERE eu.task_id=?
                    ORDER BY ep.observed_at, ep.provenance_id
                    """,
                    (task_id,),
                ).fetchall(),
                "evidence_validations": connection.execute(
                    """
                    SELECT * FROM research_evidence_validations
                    WHERE task_id=? ORDER BY observed_at, observation_id
                    """,
                    (task_id,),
                ).fetchall(),
                "provisional_artifacts": connection.execute(
                    """
                    SELECT * FROM research_provisional_artifacts
                    WHERE task_id=? ORDER BY created_at, artifact_id
                    """,
                    (task_id,),
                ).fetchall(),
            }
            latest = connection.execute(
                """
                SELECT state_payload_json FROM research_checkpoints
                WHERE task_id=? AND state_schema_version=?
                ORDER BY created_at DESC, sequence DESC LIMIT 1
                """,
                (task_id, INNER_RESEARCH_STATE_SCHEMA_VERSION),
            ).fetchone()
        result = {
            key: [self.kernel._decode_row(value) for value in values]
            for key, values in rows.items()
        }
        derived_currentness: dict[str, dict[str, Any]] = {}
        with self.db.connect() as connection:
            for use in result["evidence_uses"]:
                identity = connection.execute(
                    """
                    SELECT * FROM research_evidence_identities
                    WHERE evidence_id=?
                    """,
                    (str(use["evidence_id"]),),
                ).fetchone()
                if identity is None:
                    outcome = CurrentnessResult(
                        outcome="missing",
                        reason_code="evidence_identity_missing",
                        expected_source_version=str(use["source_version"]),
                        observed_source_version=None,
                        span=None,
                    )
                else:
                    outcome = self.authority.observe(identity)
                derived_currentness[str(use["evidence_use_id"])] = {
                    "outcome": outcome.outcome,
                    "reason_code": outcome.reason_code,
                    "expected_source_version": outcome.expected_source_version,
                    "observed_source_version": outcome.observed_source_version,
                    "authority_mode": "live_current_exact_replay",
                    "persisted_observation": False,
                }
        result["derived_currentness"] = derived_currentness
        for artifact in result["provisional_artifacts"]:
            use_ids = list(artifact.get("evidence_use_ids") or [])
            artifact["derived_current"] = all(
                derived_currentness.get(str(use_id), {}).get("outcome")
                == "current"
                for use_id in use_ids
            )
        result["state"] = (
            json.loads(str(latest["state_payload_json"])) if latest else None
        )
        return result

    def revalidate_evidence(
        self,
        task_id: str,
        request: RevalidateInnerEvidenceRequest,
    ) -> dict[str, Any]:
        payload = {
            "operation": "revalidate_inner_evidence",
            **request.model_dump(mode="json"),
        }
        payload_hash = canonical_hash(payload)
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
            self._assert_attempt(task_id, attempt, request.owner_epoch)
            latest = self._latest_checkpoint(connection, request.attempt_id)
            if (
                latest is None
                or str(latest["checkpoint_id"])
                != request.expected_checkpoint_id
                or str(latest["state_schema_version"])
                != INNER_RESEARCH_STATE_SCHEMA_VERSION
            ):
                raise ResearchConflict("stale or non-inner expected checkpoint")
            state = self._state_from_checkpoint(
                latest,
                task_id=task_id,
                goal_id=str(attempt["goal_id"]),
                attempt_id=request.attempt_id,
                objective="",
                now=now_value,
            )
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
                raise ResearchUnsafeState(
                    "存在 unresolved SideEffect，不能提交 currentness checkpoint"
                )
            observations: list[tuple[str, str, CurrentnessResult]] = []
            outcomes: dict[str, str] = {}
            for use_id in state.evidence_use_ids:
                row = connection.execute(
                    """
                    SELECT eu.*, ei.* FROM research_evidence_uses eu
                    JOIN research_evidence_identities ei
                      ON ei.evidence_id=eu.evidence_id
                    WHERE eu.evidence_use_id=? AND eu.task_id=?
                      AND eu.attempt_id=?
                    """,
                    (use_id, task_id, request.attempt_id),
                ).fetchone()
                if row is None:
                    raise ResearchUnsafeState(
                        "checkpoint evidence use 不可寻址或跨 Attempt"
                    )
                observed = self.authority.observe(row)
                observations.append(
                    (use_id, str(row["evidence_id"]), observed)
                )
                outcomes[use_id] = observed.outcome
            checkpoint_id = _id("checkpoint")
            state.last_complete_checkpoint_id = checkpoint_id
            state_json = _json(state.model_dump(mode="json"))
            state_hash = hashlib.sha256(state_json.encode("utf-8")).hexdigest()
            sequence = int(latest["sequence"]) + 1
            connection.execute(
                """
                INSERT INTO research_checkpoints(
                    checkpoint_id, task_id, goal_id, attempt_id,
                    parent_checkpoint_id, sequence, state_schema_version,
                    state_hash, state_payload_json, is_complete,
                    owner_epoch, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    checkpoint_id,
                    task_id,
                    str(attempt["goal_id"]),
                    request.attempt_id,
                    request.expected_checkpoint_id,
                    sequence,
                    INNER_RESEARCH_STATE_SCHEMA_VERSION,
                    state_hash,
                    state_json,
                    request.owner_epoch,
                    now,
                ),
            )
            observation_ids = self._insert_observations(
                connection,
                values=observations,
                task_id=task_id,
                goal_id=str(attempt["goal_id"]),
                attempt_id=request.attempt_id,
                checkpoint_id=checkpoint_id,
                owner_epoch=request.owner_epoch,
                now=now,
            )
            self.fault_injector("after_inner_revalidation_insert")
            connection.execute(
                """
                UPDATE research_tasks
                SET state_version=state_version+1, updated_at=?
                WHERE task_id=?
                """,
                (now, task_id),
            )
            self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(attempt["goal_id"]),
                attempt_id=request.attempt_id,
                checkpoint_id=checkpoint_id,
                event_type="inner_evidence_revalidated",
                payload={
                    "observation_ids": observation_ids,
                    "outcomes": outcomes,
                    "state_hash": state_hash,
                },
                command_id=request.command_id,
                owner_epoch=request.owner_epoch,
                now=now,
            )
            response = {
                "task_id": task_id,
                "attempt_id": request.attempt_id,
                "checkpoint_id": checkpoint_id,
                "state_version": request.expected_state_version + 1,
                "observation_ids": observation_ids,
                "outcomes": outcomes,
                "deduplicated": False,
            }
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="revalidate_inner_evidence",
                payload_hash=payload_hash,
                outcome_reference=checkpoint_id,
                response=response,
                owner_epoch=request.owner_epoch,
                now=now,
            )
        return response

    def _preflight(
        self,
        task_id: str,
        request: ContinueInnerResearchRequest,
        payload_hash: str,
    ) -> dict[str, Any] | None:
        with self.kernel._transaction() as connection:
            return self.kernel._existing_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                payload_hash=payload_hash,
                owner_id=request.owner_id,
                owner_epoch=request.owner_epoch,
                now=self._now(),
            )

    def _load_state(
        self,
        task_id: str,
        request: ContinueInnerResearchRequest,
    ) -> tuple[InnerResearchState, str]:
        now = self._now()
        with self.db.connect() as connection:
            task = self.kernel._task(connection, task_id)
            attempt = self.kernel._attempt(connection, request.attempt_id)
            self.kernel._assert_nonterminal(task)
            self.kernel._assert_expected(task, request.expected_state_version)
            self.kernel._assert_owner(
                task,
                owner_id=request.owner_id,
                owner_epoch=request.owner_epoch,
                now=now,
            )
            self._assert_attempt(task_id, attempt, request.owner_epoch)
            latest = self._latest_checkpoint(connection, request.attempt_id)
            latest_id = str(latest["checkpoint_id"]) if latest else None
            if latest_id != request.expected_checkpoint_id:
                raise ResearchConflict("stale expected checkpoint")
            goal = connection.execute(
                "SELECT * FROM research_goals WHERE goal_id=?",
                (str(attempt["goal_id"]),),
            ).fetchone()
            if goal is None or str(task["active_goal_id"]) != str(goal["goal_id"]):
                raise ResearchConflict("Attempt/Goal 不属于当前 active Goal")
            state = self._state_from_checkpoint(
                latest,
                task_id=task_id,
                goal_id=str(goal["goal_id"]),
                attempt_id=request.attempt_id,
                objective=str(goal["objective"]),
                now=now,
            )
        self._assert_state_open(state)
        return state, str(goal["objective"])

    def _commit_durable_stop(
        self,
        *,
        task_id: str,
        request: ContinueInnerResearchRequest,
        payload_hash: str,
        budget_dimension: str,
    ) -> dict[str, Any]:
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
            self._assert_attempt(task_id, attempt, request.owner_epoch)
            latest = self._latest_checkpoint(connection, request.attempt_id)
            latest_id = str(latest["checkpoint_id"]) if latest else None
            if latest_id != request.expected_checkpoint_id:
                raise ResearchConflict("stale expected checkpoint")
            goal = connection.execute(
                "SELECT * FROM research_goals WHERE goal_id=?",
                (str(attempt["goal_id"]),),
            ).fetchone()
            if goal is None or str(task["active_goal_id"]) != str(goal["goal_id"]):
                raise ResearchConflict("Attempt/Goal 不属于当前 active Goal")
            state = self._state_from_checkpoint(
                latest,
                task_id=task_id,
                goal_id=str(goal["goal_id"]),
                attempt_id=request.attempt_id,
                objective=str(goal["objective"]),
                now=now_value,
            )
            self._assert_state_open(state)
            actual_dimension = self._pre_action_budget_dimension(
                state, now_value
            )
            if actual_dimension is None or actual_dimension != budget_dimension:
                raise ResearchConflict("hard budget stop condition 已变化")
            self._assert_no_unresolved_side_effect(connection, task_id)
            stopped = state.model_copy(deep=True)
            stopped.phase = "stopped"
            stopped.stop_reason = "budget_exhausted"
            stopped.termination_reason = "budget_exhausted"
            stopped.failure_class = "none"
            checkpoint_id = _id("checkpoint")
            stopped.last_complete_checkpoint_id = checkpoint_id
            state_json = _json(stopped.model_dump(mode="json"))
            state_hash = hashlib.sha256(state_json.encode("utf-8")).hexdigest()
            sequence = int(latest["sequence"]) + 1 if latest else 1
            connection.execute(
                """
                INSERT INTO research_checkpoints(
                    checkpoint_id, task_id, goal_id, attempt_id,
                    parent_checkpoint_id, sequence, state_schema_version,
                    state_hash, state_payload_json, is_complete,
                    owner_epoch, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    checkpoint_id,
                    task_id,
                    str(goal["goal_id"]),
                    request.attempt_id,
                    latest_id,
                    sequence,
                    INNER_RESEARCH_STATE_SCHEMA_VERSION,
                    state_hash,
                    state_json,
                    request.owner_epoch,
                    now,
                ),
            )
            self.fault_injector("after_inner_budget_stop_checkpoint_insert")
            connection.execute(
                """
                UPDATE research_tasks
                SET state_version=state_version+1, updated_at=?
                WHERE task_id=?
                """,
                (now, task_id),
            )
            self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(goal["goal_id"]),
                attempt_id=request.attempt_id,
                checkpoint_id=checkpoint_id,
                event_type="inner_budget_exhausted",
                payload={
                    "budget_dimension": budget_dimension,
                    "phase": stopped.phase,
                    "answer_status": stopped.answer_status,
                    "termination_reason": stopped.termination_reason,
                    "failure_class": stopped.failure_class,
                    "state_hash": state_hash,
                },
                command_id=request.command_id,
                owner_epoch=request.owner_epoch,
                now=now,
            )
            response = {
                "task_id": task_id,
                "attempt_id": request.attempt_id,
                "action_id": None,
                "action_kind": None,
                "checkpoint_id": checkpoint_id,
                "state_version": request.expected_state_version + 1,
                "phase": "stopped",
                "evidence_use_ids": list(stopped.evidence_use_ids),
                "provisional_artifact_id": None,
                "stop_reason": "budget_exhausted",
                "budget_dimension": budget_dimension,
                "deduplicated": False,
            }
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="continue_inner_budget_stop",
                payload_hash=payload_hash,
                outcome_reference=checkpoint_id,
                response=response,
                owner_epoch=request.owner_epoch,
                now=now,
            )
            self.fault_injector("after_inner_budget_stop_receipt_insert")
        return response

    def _commit_implementation_failure(
        self,
        *,
        task_id: str,
        request: ContinueInnerResearchRequest,
        payload_hash: str,
        prepared: _PreparedAction,
        cause: Exception,
    ) -> dict[str, Any]:
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
            self._assert_attempt(task_id, attempt, request.owner_epoch)
            latest = self._latest_checkpoint(connection, request.attempt_id)
            latest_id = str(latest["checkpoint_id"]) if latest else None
            if latest_id != request.expected_checkpoint_id:
                raise ResearchConflict("stale expected checkpoint")
            goal = connection.execute(
                "SELECT * FROM research_goals WHERE goal_id=?",
                (str(attempt["goal_id"]),),
            ).fetchone()
            if goal is None or str(task["active_goal_id"]) != str(goal["goal_id"]):
                raise ResearchConflict("Attempt/Goal 不属于当前 active Goal")
            state = self._state_from_checkpoint(
                latest,
                task_id=task_id,
                goal_id=str(goal["goal_id"]),
                attempt_id=request.attempt_id,
                objective=str(goal["objective"]),
                now=now_value,
            )
            self._assert_state_open(state)
            expected_key = self._action_key(
                state.phase, state, str(goal["objective"])
            )
            if (
                prepared.kind != "provisional_synthesis"
                or state.phase != "provisional_synthesis"
                or prepared.action_key != expected_key
            ):
                raise ResearchConflict(
                    "implementation failure 与 durable synthesis phase 不一致"
                )
            self._assert_no_unresolved_side_effect(connection, task_id)
            action_id = _id("inner_action")
            checkpoint_id = _id("checkpoint")
            error_detail = (
                f"{type(cause).__name__} during provisional_synthesis"
            )
            connection.execute(
                """
                INSERT INTO research_inner_actions(
                    action_id, task_id, goal_id, attempt_id,
                    originating_checkpoint_id, action_kind,
                    action_schema_version, action_key, request_hash,
                    request_json, status, owner_epoch,
                    retrieval_execution_id, retrieval_trace_id, side_effect_id,
                    observation_json, error_code, error_detail,
                    created_at, started_at, completed_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'failed', ?, NULL, NULL,
                         NULL, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action_id,
                    task_id,
                    str(goal["goal_id"]),
                    request.attempt_id,
                    latest_id,
                    prepared.kind,
                    INNER_ACTION_SCHEMA_VERSION,
                    prepared.action_key,
                    canonical_hash(prepared.request_payload),
                    _json(prepared.request_payload),
                    request.owner_epoch,
                    _json({"generation": "rolled_back_before_failure_commit"}),
                    "synthesis_implementation_error",
                    error_detail,
                    now,
                    now,
                    now,
                ),
            )
            failed_prepared = _PreparedAction(
                kind=prepared.kind,
                action_key=prepared.action_key,
                request_payload=prepared.request_payload,
                observation={
                    "generation": "rolled_back_before_failure_commit"
                },
                error_code="synthesis_implementation_error",
                error_detail=error_detail,
            )
            failed = self._advance_state(
                state,
                action_id=action_id,
                prepared=failed_prepared,
                new_use_ids=[],
                new_evidence_ids=[],
                stale_reasons=[],
                now=now_value,
            )
            failed.last_complete_checkpoint_id = checkpoint_id
            state_json = _json(failed.model_dump(mode="json"))
            state_hash = hashlib.sha256(state_json.encode("utf-8")).hexdigest()
            sequence = int(latest["sequence"]) + 1 if latest else 1
            connection.execute(
                """
                INSERT INTO research_checkpoints(
                    checkpoint_id, task_id, goal_id, attempt_id,
                    parent_checkpoint_id, sequence, state_schema_version,
                    state_hash, state_payload_json, is_complete,
                    owner_epoch, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    checkpoint_id,
                    task_id,
                    str(goal["goal_id"]),
                    request.attempt_id,
                    latest_id,
                    sequence,
                    INNER_RESEARCH_STATE_SCHEMA_VERSION,
                    state_hash,
                    state_json,
                    request.owner_epoch,
                    now,
                ),
            )
            self.fault_injector("after_inner_failure_checkpoint_insert")
            connection.execute(
                """
                UPDATE research_tasks
                SET state_version=state_version+1, updated_at=?
                WHERE task_id=?
                """,
                (now, task_id),
            )
            self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(goal["goal_id"]),
                attempt_id=request.attempt_id,
                checkpoint_id=checkpoint_id,
                event_type="inner_action_failed",
                payload={
                    "action_id": action_id,
                    "action_kind": prepared.kind,
                    "phase": failed.phase,
                    "stop_reason": failed.stop_reason,
                    "answer_status": failed.answer_status,
                    "termination_reason": failed.termination_reason,
                    "failure_class": failed.failure_class,
                    "state_hash": state_hash,
                },
                command_id=request.command_id,
                owner_epoch=request.owner_epoch,
                now=now,
            )
            response = InnerContinueResponse(
                task_id=task_id,
                attempt_id=request.attempt_id,
                action_id=action_id,
                action_kind="provisional_synthesis",
                checkpoint_id=checkpoint_id,
                state_version=request.expected_state_version + 1,
                phase="stopped",
                evidence_use_ids=list(failed.evidence_use_ids),
                stop_reason="implementation_error",
            ).model_dump(mode="json")
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="continue_inner_failure",
                payload_hash=payload_hash,
                outcome_reference=checkpoint_id,
                response=response,
                owner_epoch=request.owner_epoch,
                now=now,
            )
            self.fault_injector("after_inner_failure_receipt_insert")
        return response

    def _prepare_action(
        self, state: InnerResearchState, objective: str
    ) -> _PreparedAction:
        phase = state.phase
        key = self._action_key(phase, state, objective)
        if key in state.scoped_action_keys:
            return _PreparedAction(
                kind=self._phase_action_kind(phase),
                action_key=key,
                request_payload={"objective": objective},
                observation={},
                error_code="repeated_action",
                error_detail="canonical action key already committed",
            )
        if phase == "plan":
            return _PreparedAction(
                kind="plan",
                action_key=key,
                request_payload={"objective": objective},
                observation={
                    "objective": objective,
                    "open_questions": list(state.open_questions),
                    "strategy": [
                        "navigation",
                        "transcript_search",
                        "transcript_window",
                        "provisional_synthesis",
                    ],
                },
            )
        if phase == "navigation":
            try:
                documents = self.tools.navigate(objective)
                videos = tuple(
                    dict.fromkeys(value.video_id for value in documents)
                )[:8]
                observation = {
                    "authority": "navigation_only",
                    "documents": [
                        {
                            "video_id": value.video_id,
                            "title": value.title[:200],
                            "matched_excerpt": value.matched_excerpt[:300],
                            "authority": value.authority,
                        }
                        for value in documents[:8]
                    ],
                }
                return _PreparedAction(
                    kind="navigation",
                    action_key=key,
                    request_payload={"query": objective},
                    observation=observation,
                    focused_video_ids=videos,
                )
            except Exception as exc:
                return self._failed("navigation", key, objective, exc)
        if phase == "transcript_search":
            try:
                result = self.tools.search(
                    objective,
                    video_ids=tuple(state.focused_video_ids[:8]),
                    query_index=state.budget.research_actions,
                )
                return _PreparedAction(
                    kind="transcript_search",
                    action_key=key,
                    request_payload={
                        "query": objective,
                        "video_ids": state.focused_video_ids[:8],
                    },
                    observation={
                        "materialized_span_count": len(result.spans),
                        "stale_reasons": list(result.stale_reasons),
                        "dropped_span_count": result.dropped_span_count,
                    },
                    spans=result.spans,
                    stale_reasons=result.stale_reasons,
                )
            except Exception as exc:
                return self._failed("transcript_search", key, objective, exc)
        if phase == "transcript_window":
            current = self._current_spans(state.evidence_use_ids)
            if not current:
                return _PreparedAction(
                    kind="transcript_window",
                    action_key=key,
                    request_payload={"objective": objective},
                    observation={"skipped": "no_current_anchor"},
                    stale_reasons=("evidence_unavailable",),
                )
            try:
                span = self.tools.read_window(current[0])
                return _PreparedAction(
                    kind="transcript_window",
                    action_key=key,
                    request_payload={
                        "anchor_citation_id": current[0].citation_id,
                    },
                    observation={
                        "anchor_citation_id": current[0].citation_id,
                        "materialized_span_count": 1,
                    },
                    spans=(span,),
                )
            except Exception as exc:
                return self._failed("transcript_window", key, objective, exc)
        if phase == "provisional_synthesis":
            return _PreparedAction(
                kind="provisional_synthesis",
                action_key=key,
                request_payload={
                    "objective": objective,
                    "evidence_set_fingerprint": state.evidence_set_fingerprint,
                    "execution_mode": "deterministic",
                },
                observation={"generation": "pending_commit_revalidation"},
            )
        raise ResearchUnsafeState(f"inner phase 不可继续: {phase}")

    def _commit(
        self,
        *,
        task_id: str,
        request: ContinueInnerResearchRequest,
        payload_hash: str,
        prepared: _PreparedAction,
    ) -> dict[str, Any]:
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
            self._assert_attempt(task_id, attempt, request.owner_epoch)
            latest = self._latest_checkpoint(connection, request.attempt_id)
            latest_id = str(latest["checkpoint_id"]) if latest else None
            if latest_id != request.expected_checkpoint_id:
                raise ResearchConflict("stale expected checkpoint")
            goal = connection.execute(
                "SELECT * FROM research_goals WHERE goal_id=?",
                (str(attempt["goal_id"]),),
            ).fetchone()
            if goal is None or str(task["active_goal_id"]) != str(goal["goal_id"]):
                raise ResearchConflict("Attempt/Goal 不属于当前 active Goal")
            state = self._state_from_checkpoint(
                latest,
                task_id=task_id,
                goal_id=str(goal["goal_id"]),
                attempt_id=request.attempt_id,
                objective=str(goal["objective"]),
                now=now_value,
            )
            self._assert_state_open(state)
            budget_dimension = self._pre_action_budget_dimension(
                state, now_value
            )
            if budget_dimension is not None:
                raise _PreActionBudgetExhausted(budget_dimension)
            expected_key = self._action_key(
                state.phase, state, str(goal["objective"])
            )
            if (
                prepared.kind != self._phase_action_kind(state.phase)
                or prepared.action_key != expected_key
            ):
                raise ResearchConflict("inner action 与当前 durable phase 不一致")
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
                raise ResearchUnsafeState(
                    "存在 unresolved SideEffect，不能提交 inner checkpoint"
                )
            action_id = _id("inner_action")
            checkpoint_id = _id("checkpoint")
            action_status = "failed" if prepared.error_code else "succeeded"
            connection.execute(
                """
                INSERT INTO research_inner_actions(
                    action_id, task_id, goal_id, attempt_id,
                    originating_checkpoint_id, action_kind,
                    action_schema_version, action_key, request_hash,
                    request_json, status, owner_epoch,
                    retrieval_execution_id, retrieval_trace_id, side_effect_id,
                    observation_json, error_code, error_detail,
                    created_at, started_at, completed_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL,
                         ?, ?, ?, ?, ?, ?)
                """,
                (
                    action_id,
                    task_id,
                    str(goal["goal_id"]),
                    request.attempt_id,
                    latest_id,
                    prepared.kind,
                    INNER_ACTION_SCHEMA_VERSION,
                    prepared.action_key,
                    canonical_hash(prepared.request_payload),
                    _json(prepared.request_payload),
                    action_status,
                    request.owner_epoch,
                    self._first_provenance(prepared.spans, "execution_id"),
                    self._first_provenance(prepared.spans, "search_trace_id"),
                    _json(prepared.observation),
                    prepared.error_code,
                    prepared.error_detail,
                    now,
                    now,
                    now,
                ),
            )
            self.fault_injector("after_inner_action_insert")
            new_use_ids: list[str] = []
            new_evidence_ids: list[str] = []
            pending_observations: list[tuple[str, str, CurrentnessResult]] = []
            stale_reasons = list(prepared.stale_reasons)
            for span in prepared.spans:
                if len(state.evidence_use_ids) + len(new_use_ids) >= self.MAX_EVIDENCE_USES:
                    stale_reasons.append("evidence_budget_exhausted")
                    break
                try:
                    self.materializer.validate_current(span)
                except Exception as exc:
                    stale_reasons.append(
                        str(getattr(exc, "code", type(exc).__name__))
                    )
                    continue
                evidence_id, use_id, created_use = self._persist_span(
                    connection,
                    span=span,
                    task_id=task_id,
                    goal_id=str(goal["goal_id"]),
                    attempt_id=request.attempt_id,
                    action_id=action_id,
                    originating_checkpoint_id=latest_id,
                    owner_epoch=request.owner_epoch,
                    query=str(goal["objective"]),
                    now=now,
                )
                if created_use:
                    new_use_ids.append(use_id)
                    new_evidence_ids.append(evidence_id)
                identity = connection.execute(
                    """
                    SELECT * FROM research_evidence_identities
                    WHERE evidence_id=?
                    """,
                    (evidence_id,),
                ).fetchone()
                assert identity is not None
                currentness = self.authority.observe(identity)
                if currentness.outcome != "current":
                    raise ResearchUnsafeState(
                        "evidence 在 checkpoint commit 前不再 current"
                    )
                pending_observations.append(
                    (use_id, evidence_id, currentness)
                )
            if prepared.kind != "provisional_synthesis":
                observed_use_ids = {value[0] for value in pending_observations}
                for use_id in state.evidence_use_ids:
                    if use_id in observed_use_ids:
                        continue
                    row = connection.execute(
                        """
                        SELECT eu.*, ei.* FROM research_evidence_uses eu
                        JOIN research_evidence_identities ei
                          ON ei.evidence_id=eu.evidence_id
                        WHERE eu.evidence_use_id=? AND eu.task_id=?
                          AND eu.attempt_id=?
                        """,
                        (use_id, task_id, request.attempt_id),
                    ).fetchone()
                    if row is None:
                        raise ResearchUnsafeState(
                            "checkpoint evidence use 不可寻址或跨 Attempt"
                        )
                    pending_observations.append(
                        (
                            use_id,
                            str(row["evidence_id"]),
                            self.authority.observe(row),
                        )
                    )
            state = self._advance_state(
                state,
                action_id=action_id,
                prepared=prepared,
                new_use_ids=new_use_ids,
                new_evidence_ids=new_evidence_ids,
                stale_reasons=stale_reasons,
                now=now_value,
            )
            artifact_id: str | None = None
            artifact_data: dict[str, Any] | None = None
            if prepared.kind == "provisional_synthesis":
                artifact_id = _id("provisional")
                try:
                    artifact_data, synthesis_observations = self._synthesize(
                        connection,
                        state=state,
                        objective=str(goal["objective"]),
                        checkpoint_id=checkpoint_id,
                        owner_epoch=request.owner_epoch,
                        now=now,
                    )
                except (SimulatedCrash, ResearchError):
                    raise
                except Exception as exc:
                    raise _SynthesisImplementationError(exc) from exc
                pending_observations.extend(synthesis_observations)
                state.provisional_artifact_ids.append(artifact_id)
                state.phase = "complete"
                state.answer_status = artifact_data["answer_status"]
                state.termination_reason = (
                    "evidence_unavailable"
                    if artifact_data["answer_status"] == "valid_insufficient"
                    else "answer_ready"
                )
                state.failure_class = "none"
                state.stop_reason = state.termination_reason
                state.last_progress_delta = ProgressDelta(
                    improved_answer_status=True
                )
                state.cumulative_progress.improved_answer_status = True
            state.last_complete_checkpoint_id = checkpoint_id
            state_payload = state.model_dump(mode="json")
            state_json = _json(state_payload)
            state_hash = hashlib.sha256(state_json.encode("utf-8")).hexdigest()
            sequence = int(latest["sequence"]) + 1 if latest else 1
            connection.execute(
                """
                INSERT INTO research_checkpoints(
                    checkpoint_id, task_id, goal_id, attempt_id,
                    parent_checkpoint_id, sequence, state_schema_version,
                    state_hash, state_payload_json, is_complete,
                    owner_epoch, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    checkpoint_id,
                    task_id,
                    str(goal["goal_id"]),
                    request.attempt_id,
                    latest_id,
                    sequence,
                    INNER_RESEARCH_STATE_SCHEMA_VERSION,
                    state_hash,
                    state_json,
                    request.owner_epoch,
                    now,
                ),
            )
            self.fault_injector("after_inner_checkpoint_insert")
            validation_ids = self._insert_observations(
                connection,
                values=pending_observations,
                task_id=task_id,
                goal_id=str(goal["goal_id"]),
                attempt_id=request.attempt_id,
                checkpoint_id=checkpoint_id,
                owner_epoch=request.owner_epoch,
                now=now,
            )
            if artifact_data is not None and artifact_id is not None:
                artifact_data["validation_observation_ids"] = validation_ids
                artifact_payload = {
                    **artifact_data,
                    "artifact_id": artifact_id,
                    "artifact_schema_version": PROVISIONAL_ARTIFACT_SCHEMA_VERSION,
                    "task_id": task_id,
                    "goal_id": str(goal["goal_id"]),
                    "attempt_id": request.attempt_id,
                    "checkpoint_id": checkpoint_id,
                }
                artifact_hash = canonical_hash(artifact_payload)
                connection.execute(
                    """
                    INSERT INTO research_provisional_artifacts(
                        artifact_id, artifact_schema_version, task_id, goal_id,
                        attempt_id, checkpoint_id, objective, answer_status,
                        answer_blocks_json, limitations_json,
                        evidence_set_fingerprint, evidence_use_ids_json,
                        evidence_ids_json, validation_observation_ids_json,
                        generation_policy_version, validator_policy_version,
                        provider_side_effect_id, artifact_hash, created_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                             NULL, ?, ?)
                    """,
                    (
                        artifact_id,
                        PROVISIONAL_ARTIFACT_SCHEMA_VERSION,
                        task_id,
                        str(goal["goal_id"]),
                        request.attempt_id,
                        checkpoint_id,
                        str(goal["objective"]),
                        artifact_data["answer_status"],
                        _json(artifact_data["answer_blocks"]),
                        _json(artifact_data["limitations"]),
                        artifact_data["evidence_set_fingerprint"],
                        _json(artifact_data["evidence_use_ids"]),
                        _json(artifact_data["evidence_ids"]),
                        _json(validation_ids),
                        self.GENERATION_POLICY_VERSION,
                        self.VALIDATOR_POLICY_VERSION,
                        artifact_hash,
                        now,
                    ),
                )
                self.fault_injector("after_provisional_artifact_insert")
            connection.execute(
                """
                UPDATE research_tasks
                SET state_version=state_version+1, updated_at=?
                WHERE task_id=?
                """,
                (now, task_id),
            )
            self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(goal["goal_id"]),
                attempt_id=request.attempt_id,
                checkpoint_id=checkpoint_id,
                event_type=(
                    "inner_action_failed"
                    if prepared.error_code
                    else "inner_action_committed"
                ),
                payload={
                    "action_id": action_id,
                    "action_kind": prepared.kind,
                    "phase": state.phase,
                    "new_evidence_count": len(new_use_ids),
                    "artifact_id": artifact_id,
                    "stop_reason": state.stop_reason,
                    "answer_status": state.answer_status,
                    "termination_reason": state.termination_reason,
                    "failure_class": state.failure_class,
                    "state_hash": state_hash,
                },
                command_id=request.command_id,
                owner_epoch=request.owner_epoch,
                now=now,
            )
            response = InnerContinueResponse(
                task_id=task_id,
                attempt_id=request.attempt_id,
                action_id=action_id,
                action_kind=prepared.kind,  # type: ignore[arg-type]
                checkpoint_id=checkpoint_id,
                state_version=request.expected_state_version + 1,
                phase=state.phase,
                evidence_use_ids=list(state.evidence_use_ids),
                provisional_artifact_id=artifact_id,
                stop_reason=state.stop_reason,
            ).model_dump(mode="json")
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="continue_inner",
                payload_hash=payload_hash,
                outcome_reference=artifact_id or checkpoint_id,
                response=response,
                owner_epoch=request.owner_epoch,
                now=now,
            )
            self.fault_injector("after_inner_receipt_insert")
        return response

    def _persist_span(
        self,
        connection: sqlite3.Connection,
        *,
        span: TranscriptEvidenceSpan,
        task_id: str,
        goal_id: str,
        attempt_id: str,
        action_id: str,
        originating_checkpoint_id: str | None,
        owner_epoch: int,
        query: str,
        now: str,
    ) -> tuple[str, str, bool]:
        identity = evidence_identity_payload(span)
        identity_hash = canonical_hash(identity)
        existing_identity = connection.execute(
            "SELECT * FROM research_evidence_identities WHERE evidence_id=?",
            (span.citation_id,),
        ).fetchone()
        if existing_identity is None:
            connection.execute(
                """
                INSERT INTO research_evidence_identities(
                    evidence_id, citation_identity_version, video_id,
                    source_artifact_id, source_version, timeline_run_id,
                    segment_ids_json, segment_ordinals_json,
                    start_time, end_time, quote_hash, quote_preview,
                    identity_payload_hash, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    span.citation_id,
                    span.citation_identity_version,
                    span.video_id,
                    span.source_artifact_id,
                    span.source_version,
                    span.timeline_run_id,
                    _json(list(span.segment_ids)),
                    _json(list(span.segment_ordinals)),
                    span.start_time,
                    span.end_time,
                    identity["quote_hash"],
                    span.quote_text[:500],
                    identity_hash,
                    now,
                ),
            )
            self.fault_injector("after_evidence_identity_insert")
        elif str(existing_identity["identity_payload_hash"]) != identity_hash:
            raise ResearchUnsafeState(
                "相同 evidence_id 的 canonical identity payload 不一致"
            )
        existing_use = connection.execute(
            """
            SELECT * FROM research_evidence_uses
            WHERE task_id=? AND attempt_id=? AND evidence_id=?
            """,
            (task_id, attempt_id, span.citation_id),
        ).fetchone()
        created_use = existing_use is None
        if existing_use is None:
            use_id = _id("evidence_use")
            use_payload = {
                "evidence_use_id": use_id,
                "evidence_id": span.citation_id,
                "task_id": task_id,
                "goal_id": goal_id,
                "attempt_id": attempt_id,
                "first_action_id": action_id,
                "originating_checkpoint_id": originating_checkpoint_id,
                "owner_epoch": owner_epoch,
                "use_purpose": "inner_research_grounding",
                "use_schema_version": EVIDENCE_USE_SCHEMA_VERSION,
            }
            connection.execute(
                """
                INSERT INTO research_evidence_uses(
                    evidence_use_id, evidence_id, task_id, goal_id, attempt_id,
                    first_action_id, originating_checkpoint_id, owner_epoch,
                    use_purpose, use_schema_version, use_payload_hash, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    use_id,
                    span.citation_id,
                    task_id,
                    goal_id,
                    attempt_id,
                    action_id,
                    originating_checkpoint_id,
                    owner_epoch,
                    "inner_research_grounding",
                    EVIDENCE_USE_SCHEMA_VERSION,
                    canonical_hash(use_payload),
                    now,
                ),
            )
            self.fault_injector("after_evidence_use_insert")
        else:
            use_id = str(existing_use["evidence_use_id"])
        for provenance in provenance_payloads(span, fallback_query=query):
            provenance_hash = canonical_hash(provenance)
            connection.execute(
                """
                INSERT OR IGNORE INTO research_evidence_provenance(
                    provenance_id, evidence_use_id, action_id, execution_id,
                    search_trace_id, query_fingerprint, rank,
                    retrieval_method, index_identity_json,
                    parent_chunk_ids_json, source_version_authority,
                    mapping_policy_versions_json, provenance_hash, observed_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _id("provenance"),
                    use_id,
                    action_id,
                    provenance["execution_id"],
                    provenance["search_trace_id"],
                    provenance["query_fingerprint"],
                    provenance["rank"],
                    provenance["retrieval_method"],
                    _json(provenance["index_identity"]),
                    _json(provenance["parent_chunk_ids"]),
                    provenance["source_version_authority"],
                    _json(provenance["mapping_policy_versions"]),
                    provenance_hash,
                    now,
                ),
            )
        self.fault_injector("after_evidence_provenance_insert")
        return span.citation_id, use_id, created_use

    def _synthesize(
        self,
        connection: sqlite3.Connection,
        *,
        state: InnerResearchState,
        objective: str,
        checkpoint_id: str,
        owner_epoch: int,
        now: str,
    ) -> tuple[
        dict[str, Any],
        list[tuple[str, str, CurrentnessResult]],
    ]:
        spans: list[TranscriptEvidenceSpan] = []
        observations: list[tuple[str, str, CurrentnessResult]] = []
        current_use_ids: list[str] = []
        evidence_ids: list[str] = []
        for use_id in state.evidence_use_ids:
            row = connection.execute(
                """
                SELECT eu.*, ei.* FROM research_evidence_uses eu
                JOIN research_evidence_identities ei
                  ON ei.evidence_id=eu.evidence_id
                WHERE eu.evidence_use_id=? AND eu.task_id=?
                  AND eu.attempt_id=?
                """,
                (use_id, state.task_id, state.attempt_id),
            ).fetchone()
            if row is None:
                raise ResearchUnsafeState(
                    "checkpoint evidence use 不可寻址或跨 Attempt"
                )
            observed = self.authority.observe(row)
            observations.append(
                (use_id, str(row["evidence_id"]), observed)
            )
            if observed.outcome == "current" and observed.span is not None:
                spans.append(observed.span)
                current_use_ids.append(use_id)
                evidence_ids.append(str(row["evidence_id"]))
        context = self.context_builder.build(
            query=objective,
            normalized_intent=objective,
            spans=tuple(spans),
        )
        if context.spans:
            blocks = [
                AnswerBlock(
                    text=value.quote_text,
                    citation_ids=[value.citation_id],
                )
                for value in context.spans[:3]
            ]
            draft = GroundedAnswerDraft(
                status="partial",
                answer_blocks=blocks,
                limitations=[
                    "无 Provider deterministic extractive synthesis；尚未执行 Outer Goal Audit"
                ],
            )
            issues = self.grounded_validator(
                draft,
                context=context,
                materializer=self.materializer,
            )
            if issues:
                raise ResearchUnsafeState(
                    "deterministic provisional synthesis 未通过 citation validation"
                )
            answer_status = "valid_partial"
        else:
            draft = GroundedAnswerDraft(
                status="insufficient",
                answer_blocks=[],
                limitations=["没有可绑定当前字幕版本的有效证据"],
            )
            answer_status = "valid_insufficient"
        data = {
            "objective": objective,
            "answer_status": answer_status,
            "answer_blocks": [
                value.model_dump(mode="json") for value in draft.answer_blocks
            ],
            "limitations": list(draft.limitations),
            "evidence_set_fingerprint": canonical_hash(
                {
                    "evidence_use_ids": current_use_ids,
                    "evidence_ids": evidence_ids,
                }
            ),
            "evidence_use_ids": current_use_ids,
            "evidence_ids": evidence_ids,
            "validation_observation_ids": [],
            "generation_policy_version": self.GENERATION_POLICY_VERSION,
            "validator_policy_version": self.VALIDATOR_POLICY_VERSION,
            "checkpoint_id": checkpoint_id,
            "owner_epoch": owner_epoch,
            "created_at": now,
        }
        return data, observations

    def _insert_observations(
        self,
        connection: sqlite3.Connection,
        *,
        values: list[tuple[str, str, CurrentnessResult]],
        task_id: str,
        goal_id: str,
        attempt_id: str,
        checkpoint_id: str,
        owner_epoch: int,
        now: str,
    ) -> list[str]:
        ids: list[str] = []
        for use_id, evidence_id, observed in values:
            observation_id = _id("validation")
            connection.execute(
                """
                INSERT INTO research_evidence_validations(
                    observation_id, evidence_use_id, evidence_id,
                    task_id, goal_id, attempt_id, checkpoint_id,
                    validation_policy_version, authority_mode,
                    expected_source_version, observed_source_version,
                    outcome, reason_code, owner_epoch, observed_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation_id,
                    use_id,
                    evidence_id,
                    task_id,
                    goal_id,
                    attempt_id,
                    checkpoint_id,
                    EVIDENCE_VALIDATION_POLICY_VERSION,
                    "live_current_exact_replay",
                    observed.expected_source_version,
                    observed.observed_source_version,
                    observed.outcome,
                    observed.reason_code,
                    owner_epoch,
                    now,
                ),
            )
            ids.append(observation_id)
        self.fault_injector("after_evidence_validation_insert")
        return ids

    def _advance_state(
        self,
        state: InnerResearchState,
        *,
        action_id: str,
        prepared: _PreparedAction,
        new_use_ids: list[str],
        new_evidence_ids: list[str],
        stale_reasons: list[str],
        now: datetime,
    ) -> InnerResearchState:
        updated = state.model_copy(deep=True)
        updated.action_ids.append(action_id)
        updated.scoped_action_keys.append(prepared.action_key)
        updated.pending_action = None
        updated.budget.research_actions += 1
        if prepared.kind in {"plan", "provisional_synthesis"}:
            updated.budget.decision_rounds += 1
        if prepared.kind == "transcript_window":
            updated.budget.window_reads += 1
        if prepared.focused_video_ids:
            updated.focused_video_ids = list(prepared.focused_video_ids[:8])
        for use_id in new_use_ids:
            if use_id not in updated.evidence_use_ids:
                updated.evidence_use_ids.append(use_id)
        updated.budget.materialized_evidence_uses = len(
            updated.evidence_use_ids
        )
        updated.evidence_set_fingerprint = canonical_hash(
            {"evidence_use_ids": sorted(updated.evidence_use_ids)}
        )
        progress = ProgressDelta(
            new_evidence_ids=list(dict.fromkeys(new_evidence_ids)),
            new_evidence_groups=len(set(new_evidence_ids)),
        )
        updated.last_progress_delta = progress
        combined = list(
            dict.fromkeys(
                [
                    *updated.cumulative_progress.new_evidence_ids,
                    *progress.new_evidence_ids,
                ]
            )
        )
        updated.cumulative_progress.new_evidence_ids = combined
        updated.cumulative_progress.new_evidence_groups = len(combined)
        if prepared.kind in {"transcript_search", "transcript_window"}:
            updated.consecutive_no_progress = (
                0
                if progress.meaningful
                else updated.consecutive_no_progress + 1
            )
        if prepared.error_code:
            updated.stop_reason = "implementation_error"
            updated.termination_reason = "implementation_error"
            updated.failure_class = "implementation_failure"
            updated.phase = "stopped"
            return updated
        next_phase = {
            "plan": "navigation",
            "navigation": "transcript_search",
            "transcript_search": (
                "transcript_window"
                if updated.evidence_use_ids
                else "provisional_synthesis"
            ),
            "transcript_window": "provisional_synthesis",
            "provisional_synthesis": "complete",
        }[prepared.kind]
        if updated.budget.research_actions >= self.MAX_RESEARCH_ACTIONS:
            updated.phase = "stopped"
            updated.stop_reason = "budget_exhausted"
            updated.termination_reason = "budget_exhausted"
            updated.failure_class = "none"
        elif (
            updated.consecutive_no_progress
            >= self.MAX_CONSECUTIVE_NO_PROGRESS
            and next_phase != "provisional_synthesis"
        ):
            updated.phase = "stopped"
            updated.stop_reason = (
                "evidence_unavailable"
                if not updated.evidence_use_ids and stale_reasons
                else "no_new_evidence"
            )
            updated.termination_reason = updated.stop_reason
            updated.failure_class = "none"
        else:
            updated.phase = next_phase  # type: ignore[assignment]
        return updated

    def _state_from_checkpoint(
        self,
        checkpoint: sqlite3.Row | None,
        *,
        task_id: str,
        goal_id: str,
        attempt_id: str,
        objective: str,
        now: datetime,
    ) -> InnerResearchState:
        if (
            checkpoint is not None
            and str(checkpoint["state_schema_version"])
            == INNER_RESEARCH_STATE_SCHEMA_VERSION
        ):
            state = InnerResearchState.model_validate_json(
                str(checkpoint["state_payload_json"])
            )
            if (
                state.task_id != task_id
                or state.goal_id != goal_id
                or state.attempt_id != attempt_id
                or state.last_complete_checkpoint_id
                != str(checkpoint["checkpoint_id"])
            ):
                raise ResearchUnsafeState(
                    "inner checkpoint identity/lineage 不一致"
                )
            return state
        return InnerResearchState(
            task_id=task_id,
            goal_id=goal_id,
            attempt_id=attempt_id,
            open_questions=[objective],
            budget=InnerBudgetLedger(started_at=_iso(now)),
            evidence_set_fingerprint=canonical_hash(
                {"evidence_use_ids": []}
            ),
            last_complete_checkpoint_id=(
                str(checkpoint["checkpoint_id"]) if checkpoint else None
            ),
        )

    @staticmethod
    def _assert_state_open(state: InnerResearchState) -> None:
        if state.phase in {"complete", "stopped"}:
            raise ResearchUnsafeState(
                f"inner run 已停止，phase={state.phase}"
            )

    def _pre_action_budget_dimension(
        self, state: InnerResearchState, now: datetime
    ) -> str | None:
        if state.budget.research_actions >= self.MAX_RESEARCH_ACTIONS:
            return "research_actions"
        if (
            state.phase in {"plan", "provisional_synthesis"}
            and state.budget.decision_rounds >= self.MAX_DECISION_ROUNDS
        ):
            return "decision_rounds"
        if (
            state.phase == "transcript_window"
            and state.budget.window_reads >= self.MAX_WINDOW_READS
        ):
            return "window_reads"
        if (
            now - _parse_iso(state.budget.started_at)
        ).total_seconds() >= self.MAX_RUNTIME_SECONDS:
            return "runtime_seconds"
        return None

    @staticmethod
    def _assert_no_unresolved_side_effect(
        connection: sqlite3.Connection, task_id: str
    ) -> None:
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
            raise ResearchUnsafeState(
                "存在 unresolved SideEffect，不能提交 inner checkpoint"
            )

    @staticmethod
    def _assert_attempt(
        task_id: str, attempt: sqlite3.Row, owner_epoch: int
    ) -> None:
        if (
            str(attempt["task_id"]) != task_id
            or str(attempt["status"]) == "terminal"
            or int(attempt["owner_epoch"]) != owner_epoch
        ):
            raise ResearchConflict("Attempt 与 Task/current owner fence 不一致")

    @staticmethod
    def _latest_checkpoint(
        connection: sqlite3.Connection, attempt_id: str
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT * FROM research_checkpoints
            WHERE attempt_id=? ORDER BY sequence DESC LIMIT 1
            """,
            (attempt_id,),
        ).fetchone()

    def _current_spans(
        self, use_ids: list[str]
    ) -> tuple[TranscriptEvidenceSpan, ...]:
        spans: list[TranscriptEvidenceSpan] = []
        with self.db.connect() as connection:
            for use_id in use_ids:
                row = connection.execute(
                    """
                    SELECT eu.*, ei.* FROM research_evidence_uses eu
                    JOIN research_evidence_identities ei
                      ON ei.evidence_id=eu.evidence_id
                    WHERE eu.evidence_use_id=?
                    """,
                    (use_id,),
                ).fetchone()
                if row is None:
                    continue
                observed = self.authority.observe(row)
                if observed.outcome == "current" and observed.span is not None:
                    spans.append(observed.span)
        return tuple(spans)

    @staticmethod
    def _action_key(
        phase: str, state: InnerResearchState, objective: str
    ) -> str:
        payload = {
            "phase": phase,
            "objective": " ".join(objective.casefold().split()),
            "evidence_set_fingerprint": state.evidence_set_fingerprint,
            "focused_video_ids": state.focused_video_ids,
        }
        return f"{phase}:{canonical_hash(payload)}"

    @staticmethod
    def _phase_action_kind(phase: str) -> str:
        if phase not in {
            "plan",
            "navigation",
            "transcript_search",
            "transcript_window",
            "provisional_synthesis",
        }:
            raise ResearchUnsafeState(f"inner phase 不可执行: {phase}")
        return phase

    @staticmethod
    def _failed(
        kind: str, key: str, objective: str, exc: Exception
    ) -> _PreparedAction:
        return _PreparedAction(
            kind=kind,
            action_key=key,
            request_payload={"objective": objective},
            observation={},
            error_code=str(getattr(exc, "code", type(exc).__name__)),
            error_detail=f"{type(exc).__name__}: {exc}"[:500],
        )

    @staticmethod
    def _first_provenance(
        spans: tuple[TranscriptEvidenceSpan, ...], key: str
    ) -> str | None:
        for span in spans:
            for value in span.retrieval_provenance:
                found = str(value.get(key) or "").strip()
                if found:
                    return found
        return None

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
