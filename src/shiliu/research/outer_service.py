from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from shiliu.db import Database
from shiliu.research.errors import (
    ResearchConflict,
    ResearchError,
    ResearchUnsafeState,
    ResearchValidationError,
    SimulatedCrash,
)
from shiliu.research.inner_contracts import InnerBudgetLedger, InnerResearchState
from shiliu.research.inner_evidence import (
    CurrentnessResult,
    PersistentEvidenceAuthority,
    canonical_hash,
)
from shiliu.research.outer_contracts import (
    AdvanceOuterResearchRequest,
    ConstraintEvaluation,
    OuterAdvanceResponse,
    OuterBudgetLedger,
    RegisteredConstraintEvaluator,
)
from shiliu.research.product_policy import (
    GROUNDED_CURRENT_EVIDENCE_PROFILE_VERSION,
    is_grounded_current_evidence_profile,
)
from shiliu.research.schema import (
    COMPACT_IMPROVEMENT_SCHEMA_VERSION,
    CONSTRAINT_SPEC_SCHEMA_VERSION,
    CONTINUATION_SEED_SCHEMA_VERSION,
    EVIDENCE_USE_SCHEMA_VERSION,
    EVIDENCE_VALIDATION_POLICY_VERSION,
    INNER_ACTION_SCHEMA_VERSION,
    INNER_RESEARCH_STATE_SCHEMA_VERSION,
    OUTER_AUDIT_SCHEMA_VERSION,
    OUTER_STATE_SCHEMA_VERSION,
)
from shiliu.research.service import ResearchTaskService


Clock = Callable[[], datetime]
FaultInjector = Callable[[str], None]


def _utc_clock() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _stable_id(prefix: str, payload: Any) -> str:
    return f"{prefix}_{canonical_hash(payload)[:32]}"


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


class OuterResearchService:
    """Durable deterministic outer gate and exact-once targeted continuation."""

    MAX_OUTER_AUDITS = 3
    MAX_TARGETED_CONTINUATIONS = 2
    MAX_CONSECUTIVE_NO_PROGRESS = 2
    MAX_DISTINCT_TARGETS = 2
    MAX_TOTAL_INNER_ACTIONS = 24
    MAX_TOTAL_EVIDENCE_USES = 48
    MAX_OUTER_CONTEXT_CHARACTERS = 8_000
    MAX_CANDIDATE_CHARACTERS = 4_000
    MAX_RUNTIME_SECONDS = 900
    AUDIT_POLICY_VERSION = "v5-a-stage3-deterministic-gate-v2"
    EVALUATOR_REGISTRY_VERSION = "v5-a-stage3-evaluator-registry-v2"
    CANDIDATE_SCHEMA_VERSION = "v5-a-stage3-audit-candidate-v2"

    def __init__(
        self,
        *,
        db: Database,
        kernel: ResearchTaskService,
        authority: PersistentEvidenceAuthority | None = None,
        clock: Clock = _utc_clock,
        fault_injector: FaultInjector | None = None,
        provider_runs_authorized: bool = False,
        registered_evaluators: tuple[
            RegisteredConstraintEvaluator, ...
        ] = (),
    ) -> None:
        self.db = db
        self.kernel = kernel
        self.authority = authority or PersistentEvidenceAuthority(db)
        self.clock = clock
        self.fault_injector = fault_injector or (lambda _point: None)
        self.provider_runs_authorized = provider_runs_authorized
        self.registered_evaluators: dict[
            tuple[str, str], RegisteredConstraintEvaluator
        ] = {}
        for supplied in registered_evaluators:
            registration = RegisteredConstraintEvaluator.model_validate(
                supplied.model_dump(mode="json")
            )
            key = (
                registration.constraint_scope,
                _normalized(registration.exact_text),
            )
            if key in self.registered_evaluators:
                raise ValueError(
                    "duplicate server evaluator registration for exact constraint"
                )
            self._validate_registration(registration)
            self.registered_evaluators[key] = registration.model_copy(deep=True)

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def advance(
        self, task_id: str, request: AdvanceOuterResearchRequest
    ) -> dict[str, Any]:
        try:
            request = AdvanceOuterResearchRequest.model_validate(
                request.model_dump(mode="json")
            )
        except ValidationError as exc:
            raise ResearchValidationError(
                "outer advance request 不符合 bounded schema"
            ) from exc
        candidate_payload = self._candidate_payload(request)
        if (
            candidate_payload is not None
            and len(_json(candidate_payload)) > self.MAX_CANDIDATE_CHARACTERS
        ):
            raise ResearchValidationError(
                "audit candidate 超过 canonical serialized-size limit"
            )
        try:
            return self._advance(task_id, request)
        except (ResearchError, SimulatedCrash):
            raise
        except Exception as exc:
            return self._commit_implementation_failure(
                task_id=task_id,
                request=request,
                cause=exc,
            )

    @staticmethod
    def _candidate_payload(
        request: AdvanceOuterResearchRequest,
    ) -> dict[str, Any] | None:
        return (
            request.candidate.model_dump(mode="json")
            if request.candidate is not None
            else None
        )

    @staticmethod
    def _validate_registration(
        registration: RegisteredConstraintEvaluator,
    ) -> None:
        parameters = registration.parameters
        if registration.evaluator_kind == "minimum_current_evidence":
            if set(parameters) != {"minimum"}:
                raise ValueError(
                    "registered minimum_current_evidence only accepts minimum"
                )
            minimum = parameters.get("minimum")
            if (
                isinstance(minimum, bool)
                or not isinstance(minimum, int)
                or minimum < 1
            ):
                raise ValueError(
                    "registered minimum_current_evidence requires minimum >= 1"
                )
        elif registration.evaluator_kind == "answer_status":
            if set(parameters) != {"allowed"}:
                raise ValueError(
                    "registered answer_status only accepts allowed"
                )
            allowed = parameters.get("allowed")
            valid = {"valid_success", "valid_partial", "valid_insufficient"}
            if (
                not isinstance(allowed, list)
                or not allowed
                or any(value not in valid for value in allowed)
            ):
                raise ValueError(
                    "registered answer_status requires bounded valid allowed values"
                )
        elif registration.evaluator_kind == "natural_language":
            unknown = set(parameters) - {"gap_policy"}
            if unknown or parameters.get("gap_policy") not in {
                None,
                "targeted_evidence_once",
            }:
                raise ValueError("invalid registered natural-language gap policy")
        elif parameters:
            raise ValueError("grounded_answer registration accepts no parameters")

    def _advance(
        self, task_id: str, request: AdvanceOuterResearchRequest
    ) -> dict[str, Any]:
        payload = {"operation": "advance_outer", **request.model_dump(mode="json")}
        payload_hash = canonical_hash(payload)
        if request.execution_mode == "provider":
            if not self.provider_runs_authorized:
                raise ResearchUnsafeState(
                    "Stage 3 真实 Provider run 未获单独授权"
                )
            raise ResearchUnsafeState(
                "Provider candidate wiring 未绑定获授权的 SideEffect receipt"
            )
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
            task, attempt, goal, checkpoint, artifact = self._guard_source(
                connection, task_id=task_id, request=request, now=now_value
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
                    "存在 unresolved SideEffect，不能提交 outer audit"
                )

            specs, snapshot_hash = self._constraint_snapshot(
                connection, task=task, goal=goal, now=now
            )
            budget_before = self._budget(connection, goal, now_value)
            context_characters = len(
                _json(
                    {
                        "candidate": self._candidate_payload(request),
                        "constraints": [
                            {
                                "constraint_id": value["constraint_id"],
                                "constraint_scope": value["constraint_scope"],
                                "original_text": value["original_text"],
                                "constraint_kind": value["constraint_kind"],
                                "evaluator_policy": value["evaluator_policy"],
                            }
                            for value in specs
                        ],
                        "artifact": {
                            "artifact_id": str(artifact["artifact_id"]),
                            "answer_status": str(artifact["answer_status"]),
                            "evidence_use_ids": list(
                                json.loads(str(artifact["evidence_use_ids_json"]))
                            ),
                        },
                    }
                )
            )
            context_overflow = (
                budget_before.outer_context_characters + context_characters
                > self.MAX_OUTER_CONTEXT_CHARACTERS
            )
            if context_overflow:
                candidate_id = None
                validation_ids: list[str] = []
                current_by_use: dict[
                    str, tuple[str, str, CurrentnessResult]
                ] = {}
                evaluations = [
                    ConstraintEvaluation(
                        constraint_id=str(value["constraint_id"]),
                        status="unknown",
                        recoverability="not_applicable",
                        reason_codes=["outer_context_budget_prevented_gate"],
                    )
                    for value in specs
                ]
                decision = self._stop_decision(artifact)
                target = None
                reason_codes = ["outer_budget:outer_context_characters"]
                blocker = "budget_exhausted"
            else:
                candidate_id = self._insert_candidate(
                    connection,
                    request=request,
                    task_id=task_id,
                    goal_id=str(goal["goal_id"]),
                    artifact_id=str(artifact["artifact_id"]),
                    now=now,
                )
                validation_ids, current_by_use = self._observe_artifact_evidence(
                    connection,
                    task_id=task_id,
                    goal_id=str(goal["goal_id"]),
                    attempt_id=request.attempt_id,
                    checkpoint_id=request.expected_checkpoint_id,
                    artifact=artifact,
                    owner_epoch=request.owner_epoch,
                    now=now,
                )
                evaluations = self._evaluate_constraints(
                    connection,
                    specs=specs,
                    artifact=artifact,
                    current_by_use=current_by_use,
                    validation_ids=validation_ids,
                )
                decision, target, reason_codes, blocker = self._decide(
                    connection,
                    goal_id=str(goal["goal_id"]),
                    evaluations=evaluations,
                    required_constraint_ids={
                        str(value["constraint_id"])
                        for value in specs
                        if bool(value["is_required"])
                    },
                    artifact=artifact,
                    budget=budget_before,
                    current_by_use=current_by_use,
                )
            progress_fingerprint = self._progress_fingerprint(
                evaluations=evaluations,
                artifact=artifact,
                current_by_use=current_by_use,
                blocker=blocker,
            )
            previous = connection.execute(
                """
                SELECT progress_fingerprint, budget_after_json
                FROM research_outer_audits
                WHERE goal_id=? ORDER BY created_at DESC, audit_id DESC LIMIT 1
                """,
                (str(goal["goal_id"]),),
            ).fetchone()
            no_progress = (
                int(json.loads(str(previous["budget_after_json"]))[
                    "consecutive_semantic_no_progress"
                ])
                if previous is not None
                else 0
            )
            if previous is not None and str(previous["progress_fingerprint"]) == (
                progress_fingerprint
            ):
                no_progress += 1
            else:
                no_progress = 0
            if (
                decision == "targeted_continue"
                and no_progress >= self.MAX_CONSECUTIVE_NO_PROGRESS
            ):
                decision = self._stop_decision(artifact)
                target = None
                blocker = "semantic_no_progress"
                reason_codes = ["semantic_no_progress_limit"]

            budget_after = budget_before.model_copy(deep=True)
            budget_after.outer_audits += 1
            budget_after.consecutive_semantic_no_progress = no_progress
            if not context_overflow:
                budget_after.outer_context_characters += context_characters
            if decision == "targeted_continue":
                budget_after.targeted_continuations += 1
                target_fingerprint = canonical_hash(
                    {"targeted_objective": _normalized(str(target))}
                )
                existing_target = connection.execute(
                    """
                    SELECT 1 FROM research_continuation_decisions cd
                    JOIN research_outer_audits oa ON oa.audit_id=cd.audit_id
                    WHERE cd.goal_id=? AND cd.target_fingerprint=?
                      AND oa.progress_fingerprint=?
                    """,
                    (
                        str(goal["goal_id"]),
                        target_fingerprint,
                        progress_fingerprint,
                    ),
                ).fetchone()
                if existing_target is not None:
                    decision = self._stop_decision(artifact)
                    target = None
                    blocker = "repeated_target"
                    reason_codes = ["target_repeated_without_progress"]
                    budget_after.targeted_continuations -= 1
                else:
                    distinct = int(
                        connection.execute(
                            """
                            SELECT COUNT(DISTINCT target_fingerprint)
                            FROM research_continuation_decisions
                            WHERE goal_id=? AND target_fingerprint IS NOT NULL
                            """,
                            (str(goal["goal_id"]),),
                        ).fetchone()[0]
                    )
                    budget_after.distinct_targeted_objectives = distinct + 1
                    budget_after.total_evidence_uses += sum(
                        1
                        for value in current_by_use.values()
                        if value[2].outcome == "current"
                    )

            exhausted = (
                "outer_context_characters"
                if context_overflow
                else self._exhausted_dimension(budget_after, now_value)
            )
            if exhausted is not None:
                had_target = decision == "targeted_continue"
                decision = self._stop_decision(artifact)
                target = None
                blocker = "budget_exhausted"
                reason_codes = [f"outer_budget:{exhausted}"]
                if had_target:
                    budget_after.targeted_continuations = (
                        budget_before.targeted_continuations
                    )
                    budget_after.distinct_targeted_objectives = (
                        budget_before.distinct_targeted_objectives
                    )
                    budget_after.total_evidence_uses = (
                        budget_before.total_evidence_uses
                    )

            audit_id = _id("outer_audit")
            observation_ids = [
                _id("constraint_observation") for _ in evaluations
            ]
            audit_outcome = decision
            connection.execute(
                """
                INSERT INTO research_outer_audits(
                    audit_id, audit_schema_version, audit_policy_version,
                    task_id, goal_id, attempt_id, source_checkpoint_id,
                    artifact_id, constraint_snapshot_hash, observation_ids_json,
                    validation_observation_ids_json, artifact_fingerprint,
                    evidence_fingerprint, progress_fingerprint, outcome,
                    blocker, reason_codes_json, budget_before_json,
                    budget_after_json, candidate_id, owner_epoch, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                         ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    OUTER_AUDIT_SCHEMA_VERSION,
                    self.AUDIT_POLICY_VERSION,
                    task_id,
                    str(goal["goal_id"]),
                    request.attempt_id,
                    request.expected_checkpoint_id,
                    str(artifact["artifact_id"]),
                    snapshot_hash,
                    _json(observation_ids),
                    _json(validation_ids),
                    str(artifact["artifact_hash"]),
                    str(artifact["evidence_set_fingerprint"]),
                    progress_fingerprint,
                    audit_outcome,
                    blocker,
                    _json(reason_codes),
                    _json(budget_before.model_dump(mode="json")),
                    _json(budget_after.model_dump(mode="json")),
                    candidate_id,
                    request.owner_epoch,
                    now,
                ),
            )
            self.fault_injector("after_outer_audit_insert")
            for observation_id, value in zip(
                observation_ids, evaluations, strict=True
            ):
                connection.execute(
                    """
                    INSERT INTO research_constraint_audit_observations(
                        audit_observation_id, audit_id, task_id, goal_id,
                        attempt_id, artifact_id, constraint_id,
                        evaluator_policy_version, status, recoverability,
                        evidence_use_ids_json, validation_observation_ids_json,
                        reason_codes_json, owner_epoch, observed_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        observation_id,
                        audit_id,
                        task_id,
                        str(goal["goal_id"]),
                        request.attempt_id,
                        str(artifact["artifact_id"]),
                        value.constraint_id,
                        self.EVALUATOR_REGISTRY_VERSION,
                        value.status,
                        value.recoverability,
                        _json(value.evidence_use_ids),
                        _json(value.validation_observation_ids),
                        _json(value.reason_codes),
                        request.owner_epoch,
                        now,
                    ),
                )
            self.fault_injector("after_constraint_observations_insert")

            checkpoint_id = _id("checkpoint")
            improvement_id = _id("improvement")
            proposed_child_id = (
                _id("attempt") if decision == "targeted_continue" else None
            )
            improvement = self._improvement_payload(
                evaluations=evaluations,
                artifact=artifact,
                budget=budget_after,
                blocker=blocker,
                target=target,
                parent_audit_id=audit_id,
                parent_checkpoint_id=request.expected_checkpoint_id,
                parent_attempt_id=request.attempt_id,
                proposed_child_attempt_id=proposed_child_id,
                current_by_use=current_by_use,
            )
            connection.execute(
                """
                INSERT INTO research_compact_improvement_states(
                    improvement_state_id, improvement_schema_version,
                    task_id, goal_id, attempt_id, audit_id,
                    source_checkpoint_id, artifact_id, state_payload_json,
                    state_hash, owner_epoch, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    improvement_id,
                    COMPACT_IMPROVEMENT_SCHEMA_VERSION,
                    task_id,
                    str(goal["goal_id"]),
                    request.attempt_id,
                    audit_id,
                    request.expected_checkpoint_id,
                    str(artifact["artifact_id"]),
                    _json(improvement),
                    canonical_hash(improvement),
                    request.owner_epoch,
                    now,
                ),
            )
            self.fault_injector("after_improvement_state_insert")
            outer_state = {
                "state_schema_version": OUTER_STATE_SCHEMA_VERSION,
                "task_id": task_id,
                "goal_id": str(goal["goal_id"]),
                "attempt_id": request.attempt_id,
                "phase": self._phase(decision),
                "audit_id": audit_id,
                "improvement_state_id": improvement_id,
                "decision": decision,
                "budget": budget_after.model_dump(mode="json"),
                "progress_fingerprint": progress_fingerprint,
                "blocker": blocker,
                "answer_status": str(artifact["answer_status"]),
                "termination_reason": self._termination(
                    decision, artifact, blocker
                ),
                "failure_class": "none",
            }
            sequence = int(checkpoint["sequence"]) + 1
            state_json = _json(outer_state)
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
                    request.expected_checkpoint_id,
                    sequence,
                    OUTER_STATE_SCHEMA_VERSION,
                    hashlib.sha256(state_json.encode()).hexdigest(),
                    state_json,
                    request.owner_epoch,
                    now,
                ),
            )
            self.fault_injector("after_outer_checkpoint_insert")

            result_id: str | None = None
            child_attempt_id: str | None = None
            seed_id: str | None = None
            task_status: str
            if decision == "targeted_continue":
                assert proposed_child_id is not None and target is not None
                result_id, child_attempt_id, seed_id = self._commit_continuation(
                    connection,
                    task=task,
                    goal=goal,
                    parent_attempt=attempt,
                    artifact=artifact,
                    evaluations=evaluations,
                    current_by_use=current_by_use,
                    audit_id=audit_id,
                    improvement_id=improvement_id,
                    outer_checkpoint_id=checkpoint_id,
                    child_attempt_id=proposed_child_id,
                    target=target,
                    progress_fingerprint=progress_fingerprint,
                    owner_epoch=request.owner_epoch,
                    now=now,
                )
                task_status = "running"
            elif decision == "blocked":
                decision_id = self._insert_decision(
                    connection,
                    task_id=task_id,
                    goal_id=str(goal["goal_id"]),
                    parent_attempt_id=request.attempt_id,
                    child_attempt_id=None,
                    audit_id=audit_id,
                    improvement_id=improvement_id,
                    decision=decision,
                    target=None,
                    reason_codes=reason_codes,
                    owner_epoch=request.owner_epoch,
                    now=now,
                )
                connection.execute(
                    "UPDATE research_attempts SET status='waiting_user' WHERE attempt_id=?",
                    (request.attempt_id,),
                )
                connection.execute(
                    """
                    UPDATE research_tasks
                    SET status='waiting_user', state_version=state_version+1,
                        updated_at=?
                    WHERE task_id=?
                    """,
                    (now, task_id),
                )
                task_status = "waiting_user"
                self.fault_injector("after_outer_blocked_update")
                _ = decision_id
            else:
                result_id = self._commit_terminal(
                    connection,
                    task_id=task_id,
                    goal_id=str(goal["goal_id"]),
                    attempt_id=request.attempt_id,
                    checkpoint_id=checkpoint_id,
                    artifact=artifact,
                    evaluations=evaluations,
                    audit_id=audit_id,
                    decision=decision,
                    blocker=blocker,
                    validation_ids=validation_ids,
                    owner_epoch=request.owner_epoch,
                    now=now,
                )
                self._insert_decision(
                    connection,
                    task_id=task_id,
                    goal_id=str(goal["goal_id"]),
                    parent_attempt_id=request.attempt_id,
                    child_attempt_id=None,
                    audit_id=audit_id,
                    improvement_id=improvement_id,
                    decision=decision,
                    target=None,
                    reason_codes=reason_codes,
                    owner_epoch=request.owner_epoch,
                    now=now,
                )
                task_status = "terminal"

            self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(goal["goal_id"]),
                attempt_id=request.attempt_id,
                checkpoint_id=checkpoint_id,
                event_type=(
                    "outer_targeted_continuation_committed"
                    if decision == "targeted_continue"
                    else "outer_audit_committed"
                ),
                payload={
                    "audit_id": audit_id,
                    "decision": decision,
                    "result_id": result_id,
                    "child_attempt_id": child_attempt_id,
                    "seed_id": seed_id,
                    "budget": budget_after.model_dump(mode="json"),
                    "progress_fingerprint": progress_fingerprint,
                },
                command_id=request.command_id,
                owner_epoch=request.owner_epoch,
                now=now,
            )
            self.fault_injector("after_outer_event_insert")
            response = OuterAdvanceResponse(
                task_id=task_id,
                goal_id=str(goal["goal_id"]),
                parent_attempt_id=request.attempt_id,
                child_attempt_id=child_attempt_id,
                audit_id=audit_id,
                decision=decision,
                checkpoint_id=checkpoint_id,
                result_id=result_id,
                continuation_seed_id=seed_id,
                state_version=request.expected_state_version + 1,
                task_status=task_status,
                answer_status=(
                    "valid_success"
                    if decision == "accept"
                    else str(artifact["answer_status"])
                ),
                termination_reason=self._termination(
                    decision, artifact, blocker
                ),
                failure_class="none",
            ).model_dump(mode="json")
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="advance_outer",
                payload_hash=payload_hash,
                outcome_reference=audit_id,
                response=response,
                owner_epoch=request.owner_epoch,
                now=now,
            )
            self.fault_injector("after_outer_receipt_insert")
        return response

    def _commit_implementation_failure(
        self,
        *,
        task_id: str,
        request: AdvanceOuterResearchRequest,
        cause: Exception,
    ) -> dict[str, Any]:
        payload = {"operation": "advance_outer", **request.model_dump(mode="json")}
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
            task, attempt, goal, checkpoint, artifact = self._guard_source(
                connection, task_id=task_id, request=request, now=now_value
            )
            audit_id = _id("outer_audit")
            budget = self._safe_failure_budget(
                connection, goal=goal, now=now_value
            )
            progress_fingerprint = canonical_hash(
                {
                    "failure": "implementation_failure",
                    "attempt_id": request.attempt_id,
                    "artifact_id": str(artifact["artifact_id"]),
                    "expected_checkpoint_id": request.expected_checkpoint_id,
                }
            )
            connection.execute(
                """
                INSERT INTO research_outer_audits(
                    audit_id, audit_schema_version, audit_policy_version,
                    task_id, goal_id, attempt_id, source_checkpoint_id,
                    artifact_id, constraint_snapshot_hash, observation_ids_json,
                    validation_observation_ids_json, artifact_fingerprint,
                    evidence_fingerprint, progress_fingerprint, outcome,
                    blocker, reason_codes_json, budget_before_json,
                    budget_after_json, candidate_id, owner_epoch, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', '[]', ?, ?, ?,
                         'failed', 'implementation_error', ?, ?, ?, NULL, ?, ?)
                """,
                (
                    audit_id,
                    OUTER_AUDIT_SCHEMA_VERSION,
                    self.AUDIT_POLICY_VERSION,
                    task_id,
                    str(goal["goal_id"]),
                    request.attempt_id,
                    request.expected_checkpoint_id,
                    str(artifact["artifact_id"]),
                    canonical_hash(
                        {
                            "goal_id": str(goal["goal_id"]),
                            "failure_before_constraint_publication": True,
                        }
                    ),
                    str(artifact["artifact_hash"]),
                    str(artifact["evidence_set_fingerprint"]),
                    progress_fingerprint,
                    _json(["outer_internal_implementation_error"]),
                    _json(budget.model_dump(mode="json")),
                    _json(budget.model_dump(mode="json")),
                    request.owner_epoch,
                    now,
                ),
            )
            checkpoint_id = _id("checkpoint")
            state = {
                "state_schema_version": OUTER_STATE_SCHEMA_VERSION,
                "task_id": task_id,
                "goal_id": str(goal["goal_id"]),
                "attempt_id": request.attempt_id,
                "phase": "failed",
                "audit_id": audit_id,
                "improvement_state_id": None,
                "decision": "blocked",
                "budget": budget.model_dump(mode="json"),
                "progress_fingerprint": progress_fingerprint,
                "blocker": "implementation_error",
                "answer_status": str(artifact["answer_status"]),
                "termination_reason": "implementation_error",
                "failure_class": "implementation_failure",
            }
            state_json = _json(state)
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
                    request.expected_checkpoint_id,
                    int(checkpoint["sequence"]) + 1,
                    OUTER_STATE_SCHEMA_VERSION,
                    hashlib.sha256(state_json.encode()).hexdigest(),
                    state_json,
                    request.owner_epoch,
                    now,
                ),
            )
            connection.execute(
                "UPDATE research_attempts SET status='blocked' WHERE attempt_id=?",
                (request.attempt_id,),
            )
            connection.execute(
                """
                UPDATE research_tasks
                SET status='blocked', state_version=state_version+1, updated_at=?
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
                event_type="outer_implementation_failure",
                payload={
                    "audit_id": audit_id,
                    "error_type": type(cause).__name__,
                    "answer_status": str(artifact["answer_status"]),
                    "termination_reason": "implementation_error",
                    "failure_class": "implementation_failure",
                },
                command_id=request.command_id,
                owner_epoch=request.owner_epoch,
                now=now,
            )
            response = {
                "task_id": task_id,
                "goal_id": str(goal["goal_id"]),
                "parent_attempt_id": request.attempt_id,
                "child_attempt_id": None,
                "audit_id": audit_id,
                "decision": "blocked",
                "checkpoint_id": checkpoint_id,
                "result_id": None,
                "continuation_seed_id": None,
                "state_version": request.expected_state_version + 1,
                "task_status": "blocked",
                "answer_status": str(artifact["answer_status"]),
                "termination_reason": "implementation_error",
                "failure_class": "implementation_failure",
                "deduplicated": False,
            }
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="advance_outer_implementation_failure",
                payload_hash=payload_hash,
                outcome_reference=audit_id,
                response=response,
                owner_epoch=request.owner_epoch,
                now=now,
            )
        return response

    def _safe_failure_budget(
        self,
        connection: sqlite3.Connection,
        *,
        goal: sqlite3.Row,
        now: datetime,
    ) -> OuterBudgetLedger:
        try:
            return self._budget(connection, goal, now)
        except Exception:
            return OuterBudgetLedger(started_at=str(goal["created_at"]))

    def get_outer_state(self, task_id: str) -> dict[str, Any]:
        tables = {
            "constraint_specs": (
                "SELECT * FROM research_constraint_specs WHERE task_id=? "
                "ORDER BY goal_revision, ordinal"
            ),
            "audit_candidates": (
                "SELECT * FROM research_audit_candidates WHERE task_id=? "
                "ORDER BY created_at, candidate_id"
            ),
            "constraint_observations": (
                "SELECT cao.* FROM research_constraint_audit_observations cao "
                "JOIN research_outer_audits oa ON oa.audit_id=cao.audit_id "
                "JOIN research_constraint_specs cs "
                "ON cs.constraint_id=cao.constraint_id "
                "WHERE cao.task_id=? ORDER BY oa.rowid, cs.ordinal"
            ),
            "outer_audits": (
                "SELECT * FROM research_outer_audits WHERE task_id=? "
                "ORDER BY rowid"
            ),
            "improvement_states": (
                "SELECT * FROM research_compact_improvement_states "
                "WHERE task_id=? ORDER BY rowid"
            ),
            "continuation_decisions": (
                "SELECT * FROM research_continuation_decisions WHERE task_id=? "
                "ORDER BY rowid"
            ),
            "continuation_seeds": (
                "SELECT * FROM research_continuation_seeds WHERE task_id=? "
                "ORDER BY rowid"
            ),
            "result_links": (
                "SELECT * FROM research_outer_result_links WHERE task_id=? "
                "ORDER BY rowid"
            ),
        }
        with self.db.connect() as connection:
            self.kernel._task(connection, task_id)
            result = {
                key: [
                    self.kernel._decode_row(row)
                    for row in connection.execute(query, (task_id,)).fetchall()
                ]
                for key, query in tables.items()
            }
            latest = connection.execute(
                """
                SELECT state_payload_json FROM research_checkpoints
                WHERE task_id=? AND state_schema_version=?
                ORDER BY created_at DESC, sequence DESC LIMIT 1
                """,
                (task_id, OUTER_STATE_SCHEMA_VERSION),
            ).fetchone()
        result["state"] = (
            json.loads(str(latest["state_payload_json"])) if latest else None
        )
        return result

    def _guard_source(
        self,
        connection: sqlite3.Connection,
        *,
        task_id: str,
        request: AdvanceOuterResearchRequest,
        now: datetime,
    ) -> tuple[
        sqlite3.Row, sqlite3.Row, sqlite3.Row, sqlite3.Row, sqlite3.Row
    ]:
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
        if (
            str(attempt["task_id"]) != task_id
            or str(attempt["status"]) != "running"
            or int(attempt["owner_epoch"]) != request.owner_epoch
        ):
            raise ResearchConflict("Attempt identity/status/owner fence 不匹配")
        if str(task["active_goal_id"]) != str(attempt["goal_id"]):
            raise ResearchConflict("Attempt 不属于 active Goal")
        checkpoint = connection.execute(
            """
            SELECT * FROM research_checkpoints
            WHERE attempt_id=? ORDER BY sequence DESC LIMIT 1
            """,
            (request.attempt_id,),
        ).fetchone()
        if (
            checkpoint is None
            or str(checkpoint["checkpoint_id"]) != request.expected_checkpoint_id
            or str(checkpoint["state_schema_version"])
            != INNER_RESEARCH_STATE_SCHEMA_VERSION
        ):
            raise ResearchConflict("outer audit 要求最新完整 Stage 2 checkpoint")
        inner_state = json.loads(str(checkpoint["state_payload_json"]))
        if inner_state.get("phase") != "complete":
            raise ResearchUnsafeState("Stage 2 inner loop 尚未形成完整 provisional artifact")
        goal = connection.execute(
            "SELECT * FROM research_goals WHERE goal_id=?",
            (str(attempt["goal_id"]),),
        ).fetchone()
        artifact = connection.execute(
            """
            SELECT * FROM research_provisional_artifacts
            WHERE task_id=? AND goal_id=? AND attempt_id=?
            ORDER BY created_at DESC, artifact_id DESC LIMIT 1
            """,
            (task_id, str(attempt["goal_id"]), request.attempt_id),
        ).fetchone()
        if goal is None or artifact is None:
            raise ResearchUnsafeState("Goal 或 provisional artifact 不可寻址")
        if str(artifact["checkpoint_id"]) != request.expected_checkpoint_id:
            raise ResearchConflict("非最新 artifact/checkpoint 组合")
        return task, attempt, goal, checkpoint, artifact

    def _constraint_snapshot(
        self,
        connection: sqlite3.Connection,
        *,
        task: sqlite3.Row,
        goal: sqlite3.Row,
        now: str,
    ) -> tuple[list[dict[str, Any]], str]:
        created = connection.execute(
            "SELECT payload_json FROM research_events "
            "WHERE task_id=? AND event_type='task_created' "
            "ORDER BY sequence LIMIT 1",
            (str(task["task_id"]),),
        ).fetchone()
        created_payload = (
            json.loads(str(created["payload_json"])) if created is not None else {}
        )
        server_profile = created_payload.get("server_constraint_profile")
        success_constraints = json.loads(str(goal["success_constraints_json"]))
        trusted_product_profile = (
            is_grounded_current_evidence_profile(server_profile)
            and not success_constraints
        )
        source = [
            ("objective", str(goal["objective"])),
            *[
                (
                    "success_constraint",
                    str(text),
                )
                for text in success_constraints
            ],
        ]
        specs: list[dict[str, Any]] = []
        for ordinal, (scope, text) in enumerate(source):
            registration = self.registered_evaluators.get(
                (scope, _normalized(text))
            )
            if scope == "objective" and trusted_product_profile:
                kind = "grounded_answer"
                evaluator_version = GROUNDED_CURRENT_EVIDENCE_PROFILE_VERSION
                policy = {
                    **dict(server_profile),
                    "authority": "server_product_profile",
                    "registration_id": None,
                }
            elif registration is not None:
                kind = registration.evaluator_kind
                evaluator_version = registration.evaluator_policy_version
                policy = {
                    "authority": "server_registry",
                    "registration_id": registration.registration_id,
                    **registration.parameters,
                }
            else:
                kind = "natural_language"
                evaluator_version = self.EVALUATOR_REGISTRY_VERSION
                policy = {
                    "authority": "unregistered_natural_language",
                    "registration_id": None,
                }
            canonical = {
                "constraint_schema_version": CONSTRAINT_SPEC_SCHEMA_VERSION,
                "goal_id": str(goal["goal_id"]),
                "goal_revision": int(goal["revision"]),
                "ordinal": ordinal,
                "constraint_scope": scope,
                "original_text": text,
                "normalized_text": _normalized(text),
                "constraint_kind": kind,
                "is_required": (
                    True
                    if scope == "objective" or registration is None
                    else registration.required
                ),
                "evaluator_policy": policy,
                "evaluator_policy_version": evaluator_version,
            }
            constraint_id = _stable_id("constraint", canonical)
            canonical["constraint_id"] = constraint_id
            payload_hash = canonical_hash(canonical)
            existing = connection.execute(
                """
                SELECT * FROM research_constraint_specs
                WHERE goal_id=? AND ordinal=?
                """,
                (str(goal["goal_id"]), ordinal),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO research_constraint_specs(
                        constraint_id, constraint_schema_version, task_id,
                        goal_id, goal_revision, ordinal, constraint_scope,
                        original_text, normalized_text, constraint_kind,
                        is_required, evaluator_policy_json,
                        evaluator_policy_version, canonical_payload_hash,
                        created_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        constraint_id,
                        CONSTRAINT_SPEC_SCHEMA_VERSION,
                        str(task["task_id"]),
                        str(goal["goal_id"]),
                        int(goal["revision"]),
                        ordinal,
                        scope,
                        text,
                        canonical["normalized_text"],
                        kind,
                        int(canonical["is_required"]),
                        _json(policy),
                        evaluator_version,
                        payload_hash,
                        now,
                    ),
                )
            elif (
                str(existing["constraint_id"]) != constraint_id
                or str(existing["canonical_payload_hash"]) != payload_hash
            ):
                raise ResearchConflict(
                    "ConstraintSpec/server evaluator registry identity mismatch"
                )
            specs.append(canonical)
        snapshot_hash = canonical_hash(
            {
                "goal_id": str(goal["goal_id"]),
                "constraints": [
                    {
                        "constraint_id": item["constraint_id"],
                        "payload_hash": canonical_hash(item),
                    }
                    for item in specs
                ],
            }
        )
        return specs, snapshot_hash

    def _insert_candidate(
        self,
        connection: sqlite3.Connection,
        *,
        request: AdvanceOuterResearchRequest,
        task_id: str,
        goal_id: str,
        artifact_id: str,
        now: str,
    ) -> str | None:
        if request.candidate is None:
            return None
        candidate_id = _id("audit_candidate")
        connection.execute(
            """
            INSERT INTO research_audit_candidates(
                candidate_id, candidate_schema_version, task_id, goal_id,
                attempt_id, artifact_id, producer_kind, proposal_json,
                proposal_hash, provider_side_effect_id, owner_epoch, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, 'deterministic', ?, ?, NULL, ?, ?)
            """,
            (
                candidate_id,
                self.CANDIDATE_SCHEMA_VERSION,
                task_id,
                goal_id,
                request.attempt_id,
                artifact_id,
                _json(self._candidate_payload(request)),
                canonical_hash(self._candidate_payload(request)),
                request.owner_epoch,
                now,
            ),
        )
        return candidate_id

    def _observe_artifact_evidence(
        self,
        connection: sqlite3.Connection,
        *,
        task_id: str,
        goal_id: str,
        attempt_id: str,
        checkpoint_id: str,
        artifact: sqlite3.Row,
        owner_epoch: int,
        now: str,
    ) -> tuple[list[str], dict[str, tuple[str, str, CurrentnessResult]]]:
        use_ids = list(json.loads(str(artifact["evidence_use_ids_json"])))
        values: dict[str, tuple[str, str, CurrentnessResult]] = {}
        observation_ids: list[str] = []
        for use_id in use_ids:
            row = connection.execute(
                """
                SELECT eu.*, ei.* FROM research_evidence_uses eu
                JOIN research_evidence_identities ei ON ei.evidence_id=eu.evidence_id
                WHERE eu.evidence_use_id=? AND eu.task_id=? AND eu.goal_id=?
                  AND eu.attempt_id=?
                """,
                (use_id, task_id, goal_id, attempt_id),
            ).fetchone()
            if row is None:
                raise ResearchUnsafeState(
                    "artifact 引用了 forged/cross-Attempt EvidenceUse"
                )
            observed = self.authority.observe(row)
            observation_id = _id("evidence_validation")
            connection.execute(
                """
                INSERT INTO research_evidence_validations(
                    observation_id, evidence_use_id, evidence_id, task_id,
                    goal_id, attempt_id, checkpoint_id,
                    validation_policy_version, authority_mode,
                    expected_source_version, observed_source_version,
                    outcome, reason_code, owner_epoch, observed_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'live_current_exact_replay',
                         ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation_id,
                    str(use_id),
                    str(row["evidence_id"]),
                    task_id,
                    goal_id,
                    attempt_id,
                    checkpoint_id,
                    EVIDENCE_VALIDATION_POLICY_VERSION,
                    observed.expected_source_version,
                    observed.observed_source_version,
                    observed.outcome,
                    observed.reason_code,
                    owner_epoch,
                    now,
                ),
            )
            observation_ids.append(observation_id)
            values[str(use_id)] = (
                str(row["evidence_id"]),
                observation_id,
                observed,
            )
        self.fault_injector("after_outer_currentness_observations_insert")
        return observation_ids, values

    def _evaluate_constraints(
        self,
        connection: sqlite3.Connection,
        *,
        specs: list[dict[str, Any]],
        artifact: sqlite3.Row,
        current_by_use: dict[str, tuple[str, str, CurrentnessResult]],
        validation_ids: list[str],
    ) -> list[ConstraintEvaluation]:
        del validation_ids
        current_uses = [
            use_id
            for use_id, (_, _, observed) in current_by_use.items()
            if observed.outcome == "current"
        ]
        all_current = len(current_uses) == len(current_by_use)
        prior_continuations = int(
            connection.execute(
                """
                SELECT COUNT(*) FROM research_continuation_decisions
                WHERE goal_id=? AND decision='targeted_continue'
                """,
                (str(artifact["goal_id"]),),
            ).fetchone()[0]
        )
        results: list[ConstraintEvaluation] = []
        for spec in specs:
            policy = dict(spec["evaluator_policy"])
            kind = str(spec["constraint_kind"])
            status = "unknown"
            recoverability = "needs_user"
            reasons: list[str] = []
            if not all_current:
                status = "invalid"
                recoverability = "irrecoverable"
                reasons = sorted(
                    {
                        value[2].reason_code
                        for value in current_by_use.values()
                        if value[2].outcome != "current"
                    }
                ) or ["artifact_evidence_not_current"]
            elif kind == "grounded_answer":
                satisfied = bool(current_uses) and str(artifact["answer_status"]) in {
                    "valid_success",
                    "valid_partial",
                }
                status = "satisfied" if satisfied else "unsatisfied"
                recoverability = "not_applicable" if satisfied else "recoverable"
                reasons = [
                    "grounded_artifact_satisfied"
                    if satisfied
                    else "grounded_artifact_insufficient"
                ]
            elif kind == "minimum_current_evidence":
                try:
                    minimum = max(1, int(policy.get("minimum", 1)))
                except (TypeError, ValueError) as exc:
                    raise ResearchValidationError(
                        "minimum_current_evidence.minimum 必须是正整数"
                    ) from exc
                satisfied = len(current_uses) >= minimum
                status = "satisfied" if satisfied else "unsatisfied"
                recoverability = "not_applicable" if satisfied else "recoverable"
                reasons = [
                    "minimum_current_evidence_satisfied"
                    if satisfied
                    else "minimum_current_evidence_not_met"
                ]
            elif kind == "answer_status":
                allowed = set(
                    policy.get("allowed") or ["valid_success", "valid_partial"]
                )
                satisfied = str(artifact["answer_status"]) in allowed
                status = "satisfied" if satisfied else "unsatisfied"
                recoverability = "not_applicable" if satisfied else "recoverable"
                reasons = [
                    "answer_status_satisfied"
                    if satisfied
                    else "answer_status_not_met"
                ]
            elif kind == "natural_language":
                status = "unknown"
                if (
                    policy.get("gap_policy") == "targeted_evidence_once"
                    and prior_continuations == 0
                ):
                    recoverability = "recoverable"
                    reasons = ["natural_language_targeted_gap_policy"]
                else:
                    recoverability = "needs_user"
                    reasons = ["no_authorized_semantic_evaluator"]
            else:
                status = "invalid"
                recoverability = "needs_user"
                reasons = ["unregistered_evaluator_kind"]
            results.append(
                ConstraintEvaluation(
                    constraint_id=str(spec["constraint_id"]),
                    status=status,  # type: ignore[arg-type]
                    recoverability=recoverability,  # type: ignore[arg-type]
                    evidence_use_ids=list(current_uses),
                    validation_observation_ids=[
                        current_by_use[value][1] for value in current_uses
                    ],
                    reason_codes=reasons,
                )
            )
        return results

    def _budget(
        self,
        connection: sqlite3.Connection,
        goal: sqlite3.Row,
        now: datetime,
    ) -> OuterBudgetLedger:
        latest = connection.execute(
            """
            SELECT budget_after_json FROM research_outer_audits
            WHERE goal_id=? ORDER BY created_at DESC, audit_id DESC LIMIT 1
            """,
            (str(goal["goal_id"]),),
        ).fetchone()
        if latest is None:
            budget = OuterBudgetLedger(started_at=str(goal["created_at"]))
        else:
            budget = OuterBudgetLedger.model_validate_json(
                str(latest["budget_after_json"])
            )
        budget.total_inner_actions = int(
            connection.execute(
                """
                SELECT COUNT(*) FROM research_inner_actions
                WHERE goal_id=? AND status != 'planned'
                """,
                (str(goal["goal_id"]),),
            ).fetchone()[0]
        )
        budget.total_evidence_uses = int(
            connection.execute(
                "SELECT COUNT(*) FROM research_evidence_uses WHERE goal_id=?",
                (str(goal["goal_id"]),),
            ).fetchone()[0]
        )
        budget.targeted_continuations = int(
            connection.execute(
                """
                SELECT COUNT(*) FROM research_continuation_decisions
                WHERE goal_id=? AND decision='targeted_continue'
                """,
                (str(goal["goal_id"]),),
            ).fetchone()[0]
        )
        budget.distinct_targeted_objectives = int(
            connection.execute(
                """
                SELECT COUNT(DISTINCT target_fingerprint)
                FROM research_continuation_decisions
                WHERE goal_id=? AND target_fingerprint IS NOT NULL
                """,
                (str(goal["goal_id"]),),
            ).fetchone()[0]
        )
        _ = now
        return budget

    def _exhausted_dimension(
        self, budget: OuterBudgetLedger, now: datetime
    ) -> str | None:
        started = datetime.fromisoformat(budget.started_at)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        checks = (
            ("outer_audits", budget.outer_audits >= self.MAX_OUTER_AUDITS),
            (
                "targeted_continuations",
                budget.targeted_continuations > self.MAX_TARGETED_CONTINUATIONS,
            ),
            (
                "distinct_targeted_objectives",
                budget.distinct_targeted_objectives > self.MAX_DISTINCT_TARGETS,
            ),
            (
                "total_inner_actions",
                budget.total_inner_actions >= self.MAX_TOTAL_INNER_ACTIONS,
            ),
            (
                "total_evidence_uses",
                budget.total_evidence_uses >= self.MAX_TOTAL_EVIDENCE_USES,
            ),
            (
                "outer_context_characters",
                budget.outer_context_characters > self.MAX_OUTER_CONTEXT_CHARACTERS,
            ),
            (
                "runtime",
                (now - started.astimezone(timezone.utc)).total_seconds()
                >= self.MAX_RUNTIME_SECONDS,
            ),
        )
        return next((name for name, exhausted in checks if exhausted), None)

    def _decide(
        self,
        connection: sqlite3.Connection,
        *,
        goal_id: str,
        evaluations: list[ConstraintEvaluation],
        required_constraint_ids: set[str],
        artifact: sqlite3.Row,
        budget: OuterBudgetLedger,
        current_by_use: dict[str, tuple[str, str, CurrentnessResult]],
    ) -> tuple[str, str | None, list[str], str | None]:
        del connection, goal_id
        if any(value[2].outcome != "current" for value in current_by_use.values()):
            return (
                self._stop_decision(artifact),
                None,
                ["artifact_evidence_not_current"],
                "evidence_unavailable",
            )
        required_unresolved = [
            value
            for value in evaluations
            if value.constraint_id in required_constraint_ids
            and value.status != "satisfied"
        ]
        if not required_unresolved:
            return "accept", None, ["all_required_constraints_satisfied"], None
        recoverable = [
            value
            for value in required_unresolved
            if value.recoverability == "recoverable"
        ]
        needs_user = [
            value
            for value in required_unresolved
            if value.recoverability == "needs_user"
        ]
        if needs_user:
            return "blocked", None, ["authorized_evaluator_required"], "needs_user"
        exhausted = self._exhausted_dimension(budget, self._now())
        if recoverable and exhausted is None:
            return (
                "targeted_continue",
                f"Resolve constraint {recoverable[0].constraint_id}",
                ["recoverable_constraint_gap"],
                "constraint_gap",
            )
        if recoverable and exhausted is not None:
            return (
                self._stop_decision(artifact),
                None,
                [f"outer_budget:{exhausted}"],
                "budget_exhausted",
            )
        return (
            self._stop_decision(artifact),
            None,
            ["required_constraint_irrecoverable"],
            "constraint_unsatisfied",
        )

    @staticmethod
    def _stop_decision(artifact: sqlite3.Row) -> str:
        return (
            "stop_partial"
            if str(artifact["answer_status"]) in {"valid_success", "valid_partial"}
            else "stop_insufficient"
        )

    @staticmethod
    def _progress_fingerprint(
        *,
        evaluations: list[ConstraintEvaluation],
        artifact: sqlite3.Row,
        current_by_use: dict[str, tuple[str, str, CurrentnessResult]],
        blocker: str | None,
    ) -> str:
        return canonical_hash(
            {
                "constraints": sorted(
                    (
                        value.constraint_id,
                        value.status,
                        value.recoverability,
                    )
                    for value in evaluations
                ),
                "current_evidence_ids": sorted(
                    value[0]
                    for value in current_by_use.values()
                    if value[2].outcome == "current"
                ),
                "currentness": sorted(
                    (value[0], value[2].outcome)
                    for value in current_by_use.values()
                ),
                "answer_status": str(artifact["answer_status"]),
                "blocker": blocker,
            }
        )

    @staticmethod
    def _improvement_payload(
        *,
        evaluations: list[ConstraintEvaluation],
        artifact: sqlite3.Row,
        budget: OuterBudgetLedger,
        blocker: str | None,
        target: str | None,
        parent_audit_id: str,
        parent_checkpoint_id: str,
        parent_attempt_id: str,
        proposed_child_attempt_id: str | None,
        current_by_use: dict[str, tuple[str, str, CurrentnessResult]],
    ) -> dict[str, Any]:
        by_status = {
            status: [
                value.constraint_id
                for value in evaluations
                if value.status == status
            ]
            for status in ("satisfied", "unsatisfied", "unknown", "invalid")
        }
        return {
            "verified_evidence_ids": sorted(
                value[0]
                for value in current_by_use.values()
                if value[2].outcome == "current"
            ),
            "satisfied_constraint_ids": by_status["satisfied"],
            "unsatisfied_constraint_ids": by_status["unsatisfied"],
            "unknown_constraint_ids": by_status["unknown"],
            "invalid_constraint_ids": by_status["invalid"],
            "rejected_direction_fingerprints": [],
            "conflict_currentness_flags": sorted(
                {
                    value[2].outcome
                    for value in current_by_use.values()
                    if value[2].outcome != "current"
                }
            ),
            "blocker": blocker,
            "targeted_objective": target,
            "target_fingerprint": (
                canonical_hash({"targeted_objective": _normalized(target)})
                if target
                else None
            ),
            "outer_budget": budget.model_dump(mode="json"),
            "parent_audit_id": parent_audit_id,
            "parent_checkpoint_id": parent_checkpoint_id,
            "parent_artifact_id": str(artifact["artifact_id"]),
            "parent_attempt_id": parent_attempt_id,
            "proposed_child_attempt_id": proposed_child_attempt_id,
        }

    def _commit_continuation(
        self,
        connection: sqlite3.Connection,
        *,
        task: sqlite3.Row,
        goal: sqlite3.Row,
        parent_attempt: sqlite3.Row,
        artifact: sqlite3.Row,
        evaluations: list[ConstraintEvaluation],
        current_by_use: dict[str, tuple[str, str, CurrentnessResult]],
        audit_id: str,
        improvement_id: str,
        outer_checkpoint_id: str,
        child_attempt_id: str,
        target: str,
        progress_fingerprint: str,
        owner_epoch: int,
        now: str,
    ) -> tuple[str, str, str]:
        task_id = str(task["task_id"])
        goal_id = str(goal["goal_id"])
        parent_attempt_id = str(parent_attempt["attempt_id"])
        result_id = _id("result")
        connection.execute(
            """
            INSERT INTO research_results(
                result_id, task_id, goal_id, attempt_id, checkpoint_id,
                answer_status, termination_reason, failure_class,
                reason_detail, is_task_terminal, owner_epoch, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, 'targeted_continuation', 'none',
                     ?, 0, ?, ?)
            """,
            (
                result_id,
                task_id,
                goal_id,
                parent_attempt_id,
                outer_checkpoint_id,
                str(artifact["answer_status"]),
                "outer audit authorized bounded targeted continuation",
                owner_epoch,
                now,
            ),
        )
        self.fault_injector("after_outer_parent_result_insert")
        connection.execute(
            """
            UPDATE research_attempts
            SET status='terminal', result_id=?, ended_at=?
            WHERE attempt_id=?
            """,
            (result_id, now, parent_attempt_id),
        )
        connection.execute(
            """
            UPDATE research_traces
            SET ended_at=?, termination_reason='targeted_continuation'
            WHERE attempt_id=? AND ended_at IS NULL
            """,
            (now, parent_attempt_id),
        )
        ordinal = int(
            connection.execute(
                "SELECT COALESCE(MAX(ordinal), 0) + 1 FROM research_attempts WHERE task_id=?",
                (task_id,),
            ).fetchone()[0]
        )
        connection.execute(
            """
            INSERT INTO research_attempts(
                attempt_id, task_id, goal_id, ordinal, cause,
                parent_attempt_id, source_checkpoint_id, status,
                owner_epoch, result_id, started_at, ended_at, created_at
            ) VALUES(?, ?, ?, ?, 'retry', ?, ?, 'running', ?, NULL, ?, NULL, ?)
            """,
            (
                child_attempt_id,
                task_id,
                goal_id,
                ordinal,
                parent_attempt_id,
                outer_checkpoint_id,
                owner_epoch,
                now,
                now,
            ),
        )
        trace_id = _id("trace")
        connection.execute(
            """
            INSERT INTO research_traces(
                trace_id, task_id, attempt_id, trace_schema_version,
                started_at, ended_at, termination_reason, retention_class
            ) VALUES(?, ?, ?, ?, ?, NULL, NULL, 'stage3_targeted_continuation')
            """,
            (
                trace_id,
                task_id,
                child_attempt_id,
                self.kernel.TRACE_SCHEMA_VERSION,
                now,
            ),
        )
        self.fault_injector("after_outer_child_attempt_insert")
        decision_id = self._insert_decision(
            connection,
            task_id=task_id,
            goal_id=goal_id,
            parent_attempt_id=parent_attempt_id,
            child_attempt_id=child_attempt_id,
            audit_id=audit_id,
            improvement_id=improvement_id,
            decision="targeted_continue",
            target=target,
            reason_codes=["outer_targeted_followup"],
            owner_epoch=owner_epoch,
            now=now,
        )
        seed_id = _id("continuation_seed")
        carry_ids = sorted(
            value[0]
            for value in current_by_use.values()
            if value[2].outcome == "current"
        )
        seed_payload = {
            "mode": "outer_targeted_followup",
            "task_id": task_id,
            "goal_id": goal_id,
            "parent_attempt_id": parent_attempt_id,
            "child_attempt_id": child_attempt_id,
            "audit_id": audit_id,
            "source_checkpoint_id": outer_checkpoint_id,
            "source_artifact_id": str(artifact["artifact_id"]),
            "targeted_objective": target,
            "target_fingerprint": canonical_hash(
                {"targeted_objective": _normalized(target)}
            ),
            "carry_evidence_ids": carry_ids,
        }
        connection.execute(
            """
            INSERT INTO research_continuation_seeds(
                seed_id, seed_schema_version, task_id, goal_id,
                parent_attempt_id, child_attempt_id,
                continuation_decision_id, audit_id, source_checkpoint_id,
                source_artifact_id, targeted_objective, target_fingerprint,
                carry_evidence_ids_json, seed_payload_hash,
                owner_epoch, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                seed_id,
                CONTINUATION_SEED_SCHEMA_VERSION,
                task_id,
                goal_id,
                parent_attempt_id,
                child_attempt_id,
                decision_id,
                audit_id,
                outer_checkpoint_id,
                str(artifact["artifact_id"]),
                target,
                seed_payload["target_fingerprint"],
                _json(carry_ids),
                canonical_hash(seed_payload),
                owner_epoch,
                now,
            ),
        )
        self._seed_child_inner_state(
            connection,
            task_id=task_id,
            goal_id=goal_id,
            child_attempt_id=child_attempt_id,
            parent_checkpoint_id=outer_checkpoint_id,
            target=target,
            current_by_use=current_by_use,
            owner_epoch=owner_epoch,
            now=now,
        )
        self.fault_injector("after_outer_continuation_seed_insert")
        self._insert_result_link(
            connection,
            result_id=result_id,
            task_id=task_id,
            goal_id=goal_id,
            attempt_id=parent_attempt_id,
            audit_id=audit_id,
            artifact=artifact,
            evaluations=evaluations,
            validation_ids=[
                value[1] for value in current_by_use.values()
            ],
            now=now,
        )
        connection.execute(
            """
            UPDATE research_tasks
            SET status='running', terminal_result_id=NULL,
                state_version=state_version+1, updated_at=?
            WHERE task_id=?
            """,
            (now, task_id),
        )
        return result_id, child_attempt_id, seed_id

    def _seed_child_inner_state(
        self,
        connection: sqlite3.Connection,
        *,
        task_id: str,
        goal_id: str,
        child_attempt_id: str,
        parent_checkpoint_id: str,
        target: str,
        current_by_use: dict[str, tuple[str, str, CurrentnessResult]],
        owner_epoch: int,
        now: str,
    ) -> None:
        checkpoint_id = _id("checkpoint")
        action_id = _id("inner_action")
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
            ) VALUES(?, ?, ?, ?, ?, 'plan', ?, ?, ?, ?, 'planned', ?,
                     NULL, NULL, NULL, ?, NULL, NULL, ?, NULL, NULL)
            """,
            (
                action_id,
                task_id,
                goal_id,
                child_attempt_id,
                None,
                INNER_ACTION_SCHEMA_VERSION,
                f"outer-carry:{child_attempt_id}",
                canonical_hash({"target": target}),
                _json({"targeted_objective": target}),
                owner_epoch,
                _json({"mode": "outer_carry_forward"}),
                now,
            ),
        )
        child_use_ids: list[str] = []
        for parent_use_id, (evidence_id, _, observed) in current_by_use.items():
            if observed.outcome != "current":
                continue
            use_id = _id("evidence_use")
            use_payload = {
                "evidence_id": evidence_id,
                "task_id": task_id,
                "goal_id": goal_id,
                "attempt_id": child_attempt_id,
                "first_action_id": action_id,
                "originating_checkpoint_id": checkpoint_id,
                "owner_epoch": owner_epoch,
                "use_purpose": "outer_targeted_carry_forward",
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
                    evidence_id,
                    task_id,
                    goal_id,
                    child_attempt_id,
                    action_id,
                    None,
                    owner_epoch,
                    "outer_targeted_carry_forward",
                    EVIDENCE_USE_SCHEMA_VERSION,
                    canonical_hash(use_payload),
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO research_evidence_provenance(
                    provenance_id, evidence_use_id, action_id, execution_id,
                    search_trace_id, query_fingerprint, rank,
                    retrieval_method, index_identity_json,
                    parent_chunk_ids_json, source_version_authority,
                    mapping_policy_versions_json, provenance_hash, observed_at
                ) VALUES(?, ?, ?, NULL, NULL, ?, NULL,
                         'outer_carry_forward', '{}', '[]',
                         'live_current_exact_replay', ?, ?, ?)
                """,
                (
                    _id("provenance"),
                    use_id,
                    action_id,
                    canonical_hash({"target": _normalized(target)}),
                    _json({"stage3": CONTINUATION_SEED_SCHEMA_VERSION}),
                    canonical_hash(
                        {
                            "parent_use_id": parent_use_id,
                            "evidence_id": evidence_id,
                            "target": _normalized(target),
                        }
                    ),
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO research_evidence_validations(
                    observation_id, evidence_use_id, evidence_id, task_id,
                    goal_id, attempt_id, checkpoint_id,
                    validation_policy_version, authority_mode,
                    expected_source_version, observed_source_version,
                    outcome, reason_code, owner_epoch, observed_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, 'live_current_exact_replay',
                         ?, ?, 'current', 'outer_carry_forward_revalidated', ?, ?)
                """,
                (
                    _id("evidence_validation"),
                    use_id,
                    evidence_id,
                    task_id,
                    goal_id,
                    child_attempt_id,
                    None,
                    EVIDENCE_VALIDATION_POLICY_VERSION,
                    observed.expected_source_version,
                    observed.observed_source_version,
                    owner_epoch,
                    now,
                ),
            )
            child_use_ids.append(use_id)
        state = InnerResearchState(
            task_id=task_id,
            goal_id=goal_id,
            attempt_id=child_attempt_id,
            open_questions=[target],
            evidence_use_ids=child_use_ids,
            budget=InnerBudgetLedger(
                started_at=now, materialized_evidence_uses=len(child_use_ids)
            ),
            evidence_set_fingerprint=canonical_hash(
                {"evidence_use_ids": sorted(child_use_ids)}
            ),
            last_complete_checkpoint_id=checkpoint_id,
        )
        state_json = _json(state.model_dump(mode="json"))
        connection.execute(
            """
            INSERT INTO research_checkpoints(
                checkpoint_id, task_id, goal_id, attempt_id,
                parent_checkpoint_id, sequence, state_schema_version,
                state_hash, state_payload_json, is_complete,
                owner_epoch, created_at
            ) VALUES(?, ?, ?, ?, ?, 1, ?, ?, ?, 1, ?, ?)
            """,
            (
                checkpoint_id,
                task_id,
                goal_id,
                child_attempt_id,
                parent_checkpoint_id,
                INNER_RESEARCH_STATE_SCHEMA_VERSION,
                hashlib.sha256(state_json.encode()).hexdigest(),
                state_json,
                owner_epoch,
                now,
            ),
        )

    def _commit_terminal(
        self,
        connection: sqlite3.Connection,
        *,
        task_id: str,
        goal_id: str,
        attempt_id: str,
        checkpoint_id: str,
        artifact: sqlite3.Row,
        evaluations: list[ConstraintEvaluation],
        audit_id: str,
        decision: str,
        blocker: str | None,
        validation_ids: list[str],
        owner_epoch: int,
        now: str,
    ) -> str:
        result_id = _id("result")
        answer_status = (
            "valid_success" if decision == "accept" else str(artifact["answer_status"])
        )
        termination = self._termination(decision, artifact, blocker)
        connection.execute(
            """
            INSERT INTO research_results(
                result_id, task_id, goal_id, attempt_id, checkpoint_id,
                answer_status, termination_reason, failure_class,
                reason_detail, is_task_terminal, owner_epoch, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, 'none', ?, 1, ?, ?)
            """,
            (
                result_id,
                task_id,
                goal_id,
                attempt_id,
                checkpoint_id,
                answer_status,
                termination,
                f"outer decision: {decision}",
                owner_epoch,
                now,
            ),
        )
        self._insert_result_link(
            connection,
            result_id=result_id,
            task_id=task_id,
            goal_id=goal_id,
            attempt_id=attempt_id,
            audit_id=audit_id,
            artifact=artifact,
            evaluations=evaluations,
            validation_ids=validation_ids,
            now=now,
        )
        connection.execute(
            """
            UPDATE research_attempts
            SET status='terminal', result_id=?, ended_at=? WHERE attempt_id=?
            """,
            (result_id, now, attempt_id),
        )
        connection.execute(
            """
            UPDATE research_traces SET ended_at=?, termination_reason=?
            WHERE attempt_id=? AND ended_at IS NULL
            """,
            (now, termination, attempt_id),
        )
        connection.execute(
            """
            UPDATE research_tasks
            SET status='terminal', terminal_result_id=?,
                state_version=state_version+1, updated_at=?
            WHERE task_id=?
            """,
            (result_id, now, task_id),
        )
        self.fault_injector("after_outer_terminal_result_insert")
        return result_id

    def _insert_result_link(
        self,
        connection: sqlite3.Connection,
        *,
        result_id: str,
        task_id: str,
        goal_id: str,
        attempt_id: str,
        audit_id: str,
        artifact: sqlite3.Row,
        evaluations: list[ConstraintEvaluation],
        validation_ids: list[str],
        now: str,
    ) -> None:
        constraint_fingerprint = canonical_hash(
            sorted(
                (value.constraint_id, value.status, value.recoverability)
                for value in evaluations
            )
        )
        connection.execute(
            """
            INSERT INTO research_outer_result_links(
                result_id, task_id, goal_id, attempt_id, audit_id,
                artifact_id, constraint_fingerprint,
                validation_observation_ids_json, generation_policy_version,
                audit_policy_version, evaluator_policy_versions_json, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result_id,
                task_id,
                goal_id,
                attempt_id,
                audit_id,
                str(artifact["artifact_id"]),
                constraint_fingerprint,
                _json(validation_ids),
                str(artifact["generation_policy_version"]),
                self.AUDIT_POLICY_VERSION,
                _json([self.EVALUATOR_REGISTRY_VERSION]),
                now,
            ),
        )

    def _insert_decision(
        self,
        connection: sqlite3.Connection,
        *,
        task_id: str,
        goal_id: str,
        parent_attempt_id: str,
        child_attempt_id: str | None,
        audit_id: str,
        improvement_id: str,
        decision: str,
        target: str | None,
        reason_codes: list[str],
        owner_epoch: int,
        now: str,
    ) -> str:
        decision_id = _id("continuation_decision")
        target_fingerprint = (
            canonical_hash({"targeted_objective": _normalized(target)})
            if target
            else None
        )
        connection.execute(
            """
            INSERT INTO research_continuation_decisions(
                continuation_decision_id, task_id, goal_id,
                parent_attempt_id, child_attempt_id, audit_id,
                improvement_state_id, decision, targeted_objective,
                target_fingerprint, reason_codes_json, owner_epoch, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                task_id,
                goal_id,
                parent_attempt_id,
                child_attempt_id,
                audit_id,
                improvement_id,
                decision,
                target,
                target_fingerprint,
                _json(reason_codes),
                owner_epoch,
                now,
            ),
        )
        return decision_id

    @staticmethod
    def _phase(decision: str) -> str:
        return {
            "accept": "accepted",
            "targeted_continue": "targeted_continuation_committed",
            "stop_partial": "stopped",
            "stop_insufficient": "stopped",
            "blocked": "blocked",
        }[decision]

    @staticmethod
    def _termination(
        decision: str, artifact: sqlite3.Row, blocker: str | None
    ) -> str:
        del artifact
        if decision == "accept":
            return "answer_ready"
        if decision == "targeted_continue":
            return "targeted_continuation"
        if decision == "blocked":
            return "needs_user_input"
        if blocker == "budget_exhausted":
            return "budget_exhausted"
        if blocker in {"semantic_no_progress", "repeated_target"}:
            return "no_new_evidence"
        if blocker == "evidence_unavailable":
            return "evidence_unavailable"
        return "constraint_unsatisfied"
