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
RegisteredEvaluatorKind = Literal[
    "grounded_answer",
    "minimum_current_evidence",
    "answer_status",
    "natural_language",
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AuditCandidateInput(_StrictModel):
    proposed_status: ConstraintStatus | None = None
    evidence_refs: list[str] = Field(default_factory=list, max_length=24)
    gap: str | None = Field(default=None, max_length=500)
    targeted_objective: str | None = Field(default=None, max_length=500)
    reason_codes: list[str] = Field(default_factory=list, max_length=16)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @field_validator("evidence_refs")
    @classmethod
    def bound_evidence_refs(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 128 for value in values):
            raise ValueError("evidence_ref must contain 1..128 characters")
        return values

    @field_validator("reason_codes")
    @classmethod
    def bound_reason_codes(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 100 for value in values):
            raise ValueError("reason_code must contain 1..100 characters")
        return values


class RegisteredConstraintEvaluator(_StrictModel):
    registration_id: str = Field(min_length=1, max_length=100)
    constraint_scope: Literal["objective", "success_constraint"]
    exact_text: str = Field(min_length=1, max_length=1000)
    evaluator_kind: RegisteredEvaluatorKind
    evaluator_policy_version: str = Field(min_length=1, max_length=100)
    required: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "registration_id",
        "exact_text",
        "evaluator_policy_version",
    )
    @classmethod
    def normalize_registry_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class AdvanceOuterResearchRequest(_StrictModel):
    command_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    owner_epoch: int = Field(ge=1)
    expected_state_version: int = Field(ge=0)
    expected_checkpoint_id: str = Field(min_length=1)
    execution_mode: OuterExecutionMode = "deterministic"
    candidate: AuditCandidateInput | None = None

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
