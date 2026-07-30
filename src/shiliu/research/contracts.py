from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskStatus(str, Enum):
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    WAITING_USER = "waiting_user"
    TERMINAL = "terminal"


class AttemptStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    BLOCKED = "blocked"
    WAITING_USER = "waiting_user"
    TERMINAL = "terminal"


class AttemptCause(str, Enum):
    INITIAL = "initial"
    RESUME = "resume"
    RETRY = "retry"
    GOAL_REVISION = "goal_revision"
    BRANCH = "branch"
    REPLAY = "replay"


class AnswerStatus(str, Enum):
    VALID_SUCCESS = "valid_success"
    VALID_PARTIAL = "valid_partial"
    VALID_INSUFFICIENT = "valid_insufficient"
    NOT_PRODUCED = "not_produced"


class TerminationReason(str, Enum):
    ANSWER_READY = "answer_ready"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NO_NEW_EVIDENCE = "no_new_evidence"
    REPEATED_ACTION = "repeated_action"
    EVIDENCE_UNAVAILABLE = "evidence_unavailable"
    NEEDS_USER_INPUT = "needs_user_input"
    CANCELLED = "cancelled"
    GOAL_REVISED = "goal_revised"
    EXTERNAL_SIDE_EFFECT_UNKNOWN = "external_side_effect_unknown"
    PROVIDER_ERROR = "provider_error"
    IMPLEMENTATION_ERROR = "implementation_error"


class FailureClass(str, Enum):
    NONE = "none"
    IMPLEMENTATION_FAILURE = "implementation_failure"
    PROVIDER_FAILURE = "provider_failure"
    PRODUCT_QUALITY_FAILURE = "product_quality_failure"
    INFRASTRUCTURE_INVALID_RUN = "infrastructure_invalid_run"
    EVALUATION_INVALID_RUN = "evaluation_invalid_run"


class SideEffectStatus(str, Enum):
    RESERVED = "reserved"
    IN_FLIGHT = "in_flight"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class CreateResearchTaskRequest(StrictModel):
    command_id: str = Field(min_length=1)
    task_id: str | None = None
    objective: str = Field(min_length=1)
    success_constraints: list[str] = Field(default_factory=list)
    evidence_policy: dict[str, Any] = Field(default_factory=dict)
    parent_task_id: str | None = None

    @field_validator("command_id", "task_id", "objective", "parent_task_id")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class ResearchCommandRequest(StrictModel):
    command_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    expected_state_version: int | None = Field(default=None, ge=0)
    expected_checkpoint_id: str | None = None
    owner_id: str | None = None
    owner_epoch: int | None = Field(default=None, ge=1)
    lease_seconds: int = Field(default=30, ge=1, le=3600)
    attempt_id: str | None = None
    parent_attempt_id: str | None = None
    source_checkpoint_id: str | None = None
    cause: AttemptCause = AttemptCause.INITIAL
    state_payload: dict[str, Any] = Field(default_factory=dict)
    objective: str | None = None
    success_constraints: list[str] = Field(default_factory=list)
    evidence_policy: dict[str, Any] = Field(default_factory=dict)
    answer_status: AnswerStatus = AnswerStatus.NOT_PRODUCED
    termination_reason: TerminationReason = TerminationReason.IMPLEMENTATION_ERROR
    failure_class: FailureClass = FailureClass.NONE
    reason_detail: str = ""
    task_terminal: bool = False
    next_task_status: TaskStatus = TaskStatus.BLOCKED
    effect_kind: str | None = None
    idempotency_key: str | None = None
    effect_payload: dict[str, Any] = Field(default_factory=dict)
    side_effect_id: str | None = None
    side_effect_outcome: str = "failed"


class ResearchTaskResponse(StrictModel):
    task: dict[str, Any]
    goals: list[dict[str, Any]]
    attempts: list[dict[str, Any]]
    checkpoints: list[dict[str, Any]]
    events: list[dict[str, Any]]
    traces: list[dict[str, Any]]
    results: list[dict[str, Any]]
    command_receipts: list[dict[str, Any]]
    side_effects: list[dict[str, Any]]
    inner_actions: list[dict[str, Any]] = Field(default_factory=list)
    evidence_uses: list[dict[str, Any]] = Field(default_factory=list)
    evidence_validations: list[dict[str, Any]] = Field(default_factory=list)
    provisional_artifacts: list[dict[str, Any]] = Field(default_factory=list)
