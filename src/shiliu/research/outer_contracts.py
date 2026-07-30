from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


OuterExecutionMode = Literal["deterministic", "provider"]
ConstraintStatus = Literal["satisfied", "unsatisfied", "unknown", "invalid"]
Recoverability = Literal[
    "recoverable", "irrecoverable", "needs_user", "not_applicable"
]
OuterDecision = Literal[
    "accept", "targeted_continue", "stop_partial", "stop_insufficient", "blocked"
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AdvanceOuterResearchRequest(_StrictModel):
    command_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    owner_epoch: int = Field(ge=1)
    expected_state_version: int = Field(ge=0)
    expected_checkpoint_id: str = Field(min_length=1)
    execution_mode: OuterExecutionMode = "deterministic"
    candidate: dict[str, Any] | None = None

    @field_validator(
        "command_id", "attempt_id", "owner_id", "expected_checkpoint_id"
    )
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class OuterBudgetLedger(_StrictModel):
    profile: str = "v5-a-stage3-outer-v1"
    outer_audits: int = Field(default=0, ge=0)
    targeted_continuations: int = Field(default=0, ge=0)
    consecutive_semantic_no_progress: int = Field(default=0, ge=0)
    distinct_targeted_objectives: int = Field(default=0, ge=0)
    total_inner_actions: int = Field(default=0, ge=0)
    total_evidence_uses: int = Field(default=0, ge=0)
    outer_context_characters: int = Field(default=0, ge=0)
    provider_logical_calls: int = Field(default=0, ge=0)
    started_at: str


class ConstraintEvaluation(_StrictModel):
    constraint_id: str
    status: ConstraintStatus
    recoverability: Recoverability
    evidence_use_ids: list[str] = Field(default_factory=list)
    validation_observation_ids: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)


class OuterAdvanceResponse(_StrictModel):
    task_id: str
    goal_id: str
    parent_attempt_id: str
    child_attempt_id: str | None = None
    audit_id: str
    decision: OuterDecision
    checkpoint_id: str
    result_id: str | None = None
    continuation_seed_id: str | None = None
    state_version: int
    task_status: str
    answer_status: str
    termination_reason: str
    failure_class: str
    deduplicated: bool = False
