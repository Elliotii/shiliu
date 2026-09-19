from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


ControlKind = Literal["interrupt", "resume", "cancel"]
InputKind = Literal["clarification", "constraint_choice"]
DecisionKind = Literal["clarify_goal", "select_constraint_option"]
ResolutionKind = Literal["confirmed_succeeded", "confirmed_failed"]
DerivationKind = Literal["branch", "replay"]


class ControlCommandRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    kind: ControlKind
    expected_state_version: int = Field(ge=0)
    expected_checkpoint_id: str | None = Field(default=None, max_length=160)
    expected_control_generation: int = Field(ge=0)
    reason: str = Field(default="", max_length=1000)
    audit_actor_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("command_id", "reason")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()


class CreateInputRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    attempt_id: str = Field(min_length=1, max_length=160)
    owner_id: str = Field(min_length=1, max_length=160)
    owner_epoch: int = Field(ge=1)
    expected_state_version: int = Field(ge=0)
    expected_checkpoint_id: str = Field(min_length=1, max_length=160)
    kind: InputKind
    prompt: str = Field(min_length=1, max_length=2000)
    choices: list[str] = Field(default_factory=list, max_length=32)
    response_schema: dict[str, Any] = Field(default_factory=dict)
    constraint_id: str | None = Field(default=None, max_length=160)
    expires_at: str | None = Field(default=None, max_length=64)

    @field_validator("command_id", "attempt_id", "owner_id", "prompt")
    @classmethod
    def normalize_required(cls, value: str) -> str:
        return value.strip()

    @field_validator("choices")
    @classmethod
    def validate_choices(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 500 for value in normalized):
            raise ValueError("choices must contain 1..500 characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("choices must be unique")
        return normalized


class HumanDecisionRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    input_request_id: str = Field(min_length=1, max_length=160)
    expected_state_version: int = Field(ge=0)
    expected_control_generation: int = Field(ge=0)
    decision_kind: DecisionKind
    response: dict[str, Any]


class ResolveSideEffectRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    side_effect_id: str = Field(min_length=1, max_length=160)
    expected_state_version: int = Field(ge=0)
    expected_control_generation: int = Field(ge=0)
    resolution: ResolutionKind
    reason: str = Field(min_length=1, max_length=1000)
    receipt_hash: str | None = Field(default=None, max_length=256)
    result_reference: str | None = Field(default=None, max_length=500)


class DeriveTaskRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    kind: DerivationKind
    source_checkpoint_id: str = Field(min_length=1, max_length=160)
    child_task_id: str | None = Field(default=None, max_length=160)
    objective: str | None = Field(default=None, max_length=2000)
    success_constraints: list[str] | None = Field(default=None, max_length=32)
    evidence_policy: dict[str, Any] | None = None
    durable_effect_confirmed: bool = False


class ControlStatusResponse(_StrictModel):
    task: dict[str, Any]
    allowed_operations: list[str]
    control_requests: list[dict[str, Any]]
    control_dispositions: list[dict[str, Any]]
    input_requests: list[dict[str, Any]]
    open_input_requests: list[dict[str, Any]]
    input_dispositions: list[dict[str, Any]]
    human_decisions: list[dict[str, Any]]
    human_constraint_observations: list[dict[str, Any]]
    side_effect_resolutions: list[dict[str, Any]]
    derivations: list[dict[str, Any]]
