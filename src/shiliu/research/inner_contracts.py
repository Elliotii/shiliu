from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shiliu.research.schema import INNER_RESEARCH_STATE_SCHEMA_VERSION


InnerPhase = Literal[
    "plan",
    "navigation",
    "transcript_search",
    "transcript_window",
    "provisional_synthesis",
    "complete",
    "stopped",
]
InnerActionKind = Literal[
    "plan",
    "navigation",
    "transcript_search",
    "transcript_window",
    "provisional_synthesis",
]
InnerExecutionMode = Literal["deterministic", "provider"]
InnerAnswerStatus = Literal[
    "valid_success",
    "valid_partial",
    "valid_insufficient",
    "not_produced",
]
InnerTerminationReason = Literal[
    "answer_ready",
    "budget_exhausted",
    "no_new_evidence",
    "repeated_action",
    "evidence_unavailable",
    "provider_error",
    "implementation_error",
]
InnerFailureClass = Literal[
    "none",
    "implementation_failure",
    "provider_failure",
    "product_quality_failure",
    "infrastructure_invalid_run",
    "evaluation_invalid_run",
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContinueInnerResearchRequest(_StrictModel):
    command_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    owner_epoch: int = Field(ge=1)
    expected_state_version: int = Field(ge=0)
    expected_checkpoint_id: str | None = None
    execution_mode: InnerExecutionMode = "deterministic"

    @field_validator("command_id", "attempt_id", "owner_id")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class RevalidateInnerEvidenceRequest(_StrictModel):
    command_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    owner_epoch: int = Field(ge=1)
    expected_state_version: int = Field(ge=0)
    expected_checkpoint_id: str = Field(min_length=1)

    @field_validator(
        "command_id", "attempt_id", "owner_id", "expected_checkpoint_id"
    )
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class InnerBudgetLedger(_StrictModel):
    profile: str = "v5-a-stage2-inner-v1"
    decision_rounds: int = Field(default=0, ge=0)
    research_actions: int = Field(default=0, ge=0)
    window_reads: int = Field(default=0, ge=0)
    materialized_evidence_uses: int = Field(default=0, ge=0)
    synthesis_context_characters: int = Field(default=0, ge=0)
    provider_logical_calls: int = Field(default=0, ge=0)
    started_at: str


class ProgressDelta(_StrictModel):
    new_evidence_ids: list[str] = Field(default_factory=list)
    new_evidence_groups: int = Field(default=0, ge=0)
    newly_resolved_questions: list[str] = Field(default_factory=list)
    higher_authority_sources: int = Field(default=0, ge=0)
    resolved_conflicts: int = Field(default=0, ge=0)
    reduced_missing_aspects: int = Field(default=0, ge=0)
    improved_answer_status: bool = False

    @property
    def meaningful(self) -> bool:
        return bool(
            self.new_evidence_groups
            or self.newly_resolved_questions
            or self.higher_authority_sources
            or self.resolved_conflicts
            or self.reduced_missing_aspects
            or self.improved_answer_status
        )


class InnerResearchState(_StrictModel):
    state_schema_version: Literal[
        "v5-a-stage2-inner-state-v1"
    ] = INNER_RESEARCH_STATE_SCHEMA_VERSION
    task_id: str
    goal_id: str
    attempt_id: str
    phase: InnerPhase = "plan"
    pending_action: dict[str, Any] | None = None
    action_ids: list[str] = Field(default_factory=list)
    evidence_use_ids: list[str] = Field(default_factory=list)
    provisional_artifact_ids: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    focused_video_ids: list[int] = Field(default_factory=list)
    scoped_action_keys: list[str] = Field(default_factory=list)
    rejected_direction_fingerprints: list[str] = Field(default_factory=list)
    budget: InnerBudgetLedger
    last_progress_delta: ProgressDelta = Field(default_factory=ProgressDelta)
    cumulative_progress: ProgressDelta = Field(default_factory=ProgressDelta)
    consecutive_no_progress: int = Field(default=0, ge=0)
    evidence_set_fingerprint: str
    last_complete_checkpoint_id: str | None = None
    stop_reason: str | None = None
    answer_status: InnerAnswerStatus = "not_produced"
    termination_reason: InnerTerminationReason | None = None
    failure_class: InnerFailureClass = "none"


class ProviderInnerAction(_StrictModel):
    kind: InnerActionKind
    query: str = Field(default="", max_length=500)
    anchor_segment_id: str | None = None
    summary: str = Field(default="", max_length=500)


class InnerContinueResponse(_StrictModel):
    task_id: str
    attempt_id: str
    action_id: str
    action_kind: InnerActionKind
    checkpoint_id: str
    state_version: int
    phase: InnerPhase
    evidence_use_ids: list[str]
    provisional_artifact_id: str | None = None
    stop_reason: str | None = None
    deduplicated: bool = False
