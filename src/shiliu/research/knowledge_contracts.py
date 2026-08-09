from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IntakeKnowledgeCandidatesRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)

    @field_validator("command_id")
    @classmethod
    def normalize_command_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("command_id must not be blank")
        return value


class ReviewKnowledgeCandidateRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    decision: Literal["accept", "reject", "edit"]
    expected_state_version: int = Field(ge=0)
    reason: str = Field(default="", max_length=1000)
    edited_claim: str | None = Field(default=None, max_length=2000)

    @field_validator("command_id")
    @classmethod
    def normalize_command_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("command_id must not be blank")
        return value

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip()

    @field_validator("edited_claim")
    @classmethod
    def normalize_edited_claim(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_edit(self) -> "ReviewKnowledgeCandidateRequest":
        if self.decision == "edit" and self.edited_claim is None:
            raise ValueError("edited_claim is required for edit")
        if self.decision != "edit" and self.edited_claim is not None:
            raise ValueError("edited_claim is only allowed for edit")
        return self


class BuildKnowledgeArtifactRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    fact_revision_ids: list[str] = Field(min_length=1, max_length=32)

    @field_validator("command_id")
    @classmethod
    def normalize_command_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("command_id must not be blank")
        return value

    @field_validator("fact_revision_ids")
    @classmethod
    def normalize_fact_revision_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("fact_revision_ids must not contain blanks")
        if len(normalized) != len(set(normalized)):
            raise ValueError("fact_revision_ids must be unique")
        return normalized


class BuildTopicPageRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    artifact_revision_id: str = Field(min_length=1, max_length=160)

    @field_validator("command_id", "artifact_revision_id")
    @classmethod
    def normalize_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value


class ReviewTopicPageRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    decision: Literal["publish", "return"]
    expected_version: int = Field(ge=1)
    reason: str = Field(default="", max_length=1000)

    @field_validator("command_id")
    @classmethod
    def normalize_command_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("command_id must not be blank")
        return value

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip()


class RevalidateKnowledgeRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    fact_revision_ids: list[str] = Field(default_factory=list, max_length=64)
    trigger: Literal["explicit", "source_change", "recovery"] = "explicit"

    @field_validator("command_id")
    @classmethod
    def normalize_command_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("command_id must not be blank")
        return value

    @field_validator("fact_revision_ids")
    @classmethod
    def normalize_fact_revision_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("fact_revision_ids must not contain blanks")
        if len(normalized) != len(set(normalized)):
            raise ValueError("fact_revision_ids must be unique")
        return normalized


class ProposeFactUpdateRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    kind: Literal["user_correction", "retire", "supersede", "potential_conflict"]
    expected_fact_state_version: int = Field(ge=0)
    proposed_claim: str | None = Field(default=None, max_length=2000)
    temporal_scope: dict[str, Any] = Field(default_factory=dict)
    viewpoint_scope: dict[str, Any] = Field(default_factory=dict)
    evidence_use_ids: list[str] = Field(default_factory=list, max_length=32)
    related_fact_revision_id: str | None = Field(default=None, max_length=160)
    reason: str = Field(default="", max_length=1000)

    @field_validator("command_id")
    @classmethod
    def normalize_command_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("command_id must not be blank")
        return value

    @field_validator("proposed_claim", "related_fact_revision_id")
    @classmethod
    def normalize_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip()

    @field_validator("evidence_use_ids")
    @classmethod
    def normalize_use_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("evidence_use_ids must not contain blanks")
        if len(normalized) != len(set(normalized)):
            raise ValueError("evidence_use_ids must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_kind(self) -> "ProposeFactUpdateRequest":
        if self.kind in {"user_correction", "supersede"} and not self.proposed_claim:
            raise ValueError("proposed_claim is required for correction/supersede")
        if self.kind == "potential_conflict" and not self.related_fact_revision_id:
            raise ValueError("related_fact_revision_id is required for conflict")
        if self.kind in {"retire", "potential_conflict"} and self.proposed_claim:
            raise ValueError("proposed_claim is not allowed for retire/conflict")
        return self


class ReviewFactUpdateRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    decision: Literal["accept", "reject", "edit"]
    expected_candidate_version: int = Field(ge=0)
    expected_fact_state_version: int = Field(ge=0)
    reason: str = Field(default="", max_length=1000)
    edited_claim: str | None = Field(default=None, max_length=2000)

    @field_validator("command_id")
    @classmethod
    def normalize_command_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("command_id must not be blank")
        return value

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip()

    @field_validator("edited_claim")
    @classmethod
    def normalize_edited_claim(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_edit(self) -> "ReviewFactUpdateRequest":
        if self.decision == "edit" and not self.edited_claim:
            raise ValueError("edited_claim is required for edit")
        if self.decision != "edit" and self.edited_claim:
            raise ValueError("edited_claim is only allowed for edit")
        return self


class RunKnowledgeOperationRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    claimant_id: str = Field(default="local_stage2_worker", min_length=1, max_length=160)

    @field_validator("command_id", "claimant_id")
    @classmethod
    def normalize_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value


class RecoverKnowledgeOperationsRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    limit: int = Field(default=8, ge=1, le=32)

    @field_validator("command_id")
    @classmethod
    def normalize_command_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("command_id must not be blank")
        return value


class ResolveKnowledgeOperationRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    action: Literal["retry", "cancel"]
    expected_claim_generation: int = Field(ge=0)
    reason: str = Field(default="", max_length=1000)

    @field_validator("command_id")
    @classmethod
    def normalize_command_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("command_id must not be blank")
        return value

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip()


class EditTopicPageRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=500)
    limitations: list[str] | None = Field(default=None, max_length=64)
    unresolved: list[str] | None = Field(default=None, max_length=64)
    annotation: str | None = Field(default=None, max_length=4000)
    reason: str = Field(default="", max_length=1000)

    @field_validator("command_id")
    @classmethod
    def normalize_command_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("command_id must not be blank")
        return value

    @field_validator("title", "annotation")
    @classmethod
    def normalize_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip()


class RevertTopicPageRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    expected_version: int = Field(ge=1)
    target_version: int = Field(ge=1)
    reason: str = Field(default="", max_length=1000)

    @field_validator("command_id")
    @classmethod
    def normalize_command_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("command_id must not be blank")
        return value

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip()


class ExportTopicPageRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    page_revision_id: str = Field(min_length=1, max_length=160)
    export_format: Literal["markdown", "json"] = "markdown"

    @field_validator("command_id", "page_revision_id")
    @classmethod
    def normalize_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value


class AssessArtifactRouteRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    query: str = Field(min_length=1, max_length=2000)
    required_aspects: list[str] = Field(default_factory=list, max_length=16)
    temporal_scope: dict[str, Any] = Field(default_factory=dict)
    viewpoint_scope: dict[str, Any] = Field(default_factory=dict)
    max_artifact_candidates: int = Field(default=5, ge=1, le=5)
    max_open_results: int = Field(default=5, ge=1, le=5)

    @field_validator("command_id", "query")
    @classmethod
    def normalize_required(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("required_aspects")
    @classmethod
    def normalize_aspects(cls, values: list[str]) -> list[str]:
        normalized = [" ".join(value.split()) for value in values]
        if any(not value or len(value) > 500 for value in normalized):
            raise ValueError("aspects must contain 1..500 characters")
        if len(normalized) != len(set(normalized)):
            raise ValueError("required_aspects must be unique")
        return normalized


class ProceedArtifactRouteRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    action: Literal["confirm", "finalize"] = "confirm"
    expected_version: int = Field(ge=1)
    route: Literal["direct_reuse", "incremental_refresh", "research_seed"] | None = None
    new_fact_aspect_map: dict[str, str] = Field(default_factory=dict)
    dropped_fact_revision_ids: list[str] = Field(default_factory=list, max_length=32)
    outcome_artifact_revision_id: str | None = Field(default=None, max_length=160)
    reason: str = Field(default="", max_length=1000)

    @field_validator("command_id")
    @classmethod
    def normalize_command_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("command_id must not be blank")
        return value

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip()

    @field_validator("outcome_artifact_revision_id")
    @classmethod
    def normalize_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("new_fact_aspect_map")
    @classmethod
    def normalize_fact_map(cls, value: dict[str, str]) -> dict[str, str]:
        normalized = {" ".join(key.split()): item.strip() for key, item in value.items()}
        if any(not key or not item for key, item in normalized.items()):
            raise ValueError("new_fact_aspect_map must not contain blanks")
        return normalized

    @field_validator("dropped_fact_revision_ids")
    @classmethod
    def normalize_dropped_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("dropped_fact_revision_ids must not contain blanks")
        if len(normalized) != len(set(normalized)):
            raise ValueError("dropped_fact_revision_ids must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_action(self) -> "ProceedArtifactRouteRequest":
        if self.action == "confirm":
            if self.route is None:
                raise ValueError("route is required for confirm")
            if self.new_fact_aspect_map or self.dropped_fact_revision_ids or self.outcome_artifact_revision_id:
                raise ValueError("outcome fields are only allowed for finalize")
        elif self.route is not None:
            raise ValueError("route is only allowed for confirm")
        return self


class SubmitKnowledgeFeedbackRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    target_kind: Literal["topic_page_revision", "artifact_route"]
    target_id: str = Field(min_length=1, max_length=160)
    decision: Literal["helpful", "needs_fix"]
    reason_code: Literal[
        "answer_quality", "citation", "currentness", "route", "usability", "other"
    ]
    note: str = Field(default="", max_length=500)
    expected_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")

    @field_validator("command_id", "target_id")
    @classmethod
    def normalize_feedback_ids(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("note")
    @classmethod
    def normalize_feedback_note(cls, value: str) -> str:
        return value.strip()


class WorkspaceSourceRef(_StrictModel):
    ref_type: Literal[
        "research_task",
        "research_event",
        "research_attempt",
        "research_trace",
        "research_result",
        "fact_revision",
        "artifact_revision",
        "taxonomy_snapshot",
    ]
    ref_id: str = Field(min_length=1, max_length=200)
    task_id: str | None = Field(default=None, max_length=160)
    boundary_hash: str | None = Field(default=None, max_length=128)

    @field_validator("ref_id")
    @classmethod
    def normalize_ref_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("ref_id must not be blank")
        return value

    @field_validator("task_id", "boundary_hash")
    @classmethod
    def normalize_optional_ref(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validate_scope(self) -> "WorkspaceSourceRef":
        if self.ref_type == "taxonomy_snapshot":
            if self.task_id is not None:
                raise ValueError("taxonomy_snapshot must not carry task_id")
        elif self.task_id is None:
            raise ValueError("task-bound source refs require task_id")
        return self


class CreateWorkspaceRecordRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    record_kind: Literal[
        "explicit_memory",
        "inferred_candidate",
        "focus_state",
        "progress_observation",
        "corpus_observation",
        "system_experience",
    ]
    semantic_key: str = Field(min_length=1, max_length=300)
    payload: dict[str, Any]
    source_refs: list[WorkspaceSourceRef] = Field(default_factory=list, max_length=32)
    confidence: float | None = Field(default=None, ge=0, le=1)
    expires_at: datetime | None = None
    reason: str = Field(default="", max_length=1000)
    reopen_reason: str | None = Field(default=None, max_length=1000)

    @field_validator("command_id", "semantic_key")
    @classmethod
    def normalize_required_workspace_text(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("value must not be blank")
        return value

    @field_validator("reason")
    @classmethod
    def normalize_workspace_reason(cls, value: str) -> str:
        return value.strip()

    @field_validator("reopen_reason")
    @classmethod
    def normalize_reopen_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("source_refs")
    @classmethod
    def unique_source_refs(
        cls, values: list[WorkspaceSourceRef]
    ) -> list[WorkspaceSourceRef]:
        identities = [(value.ref_type, value.ref_id, value.task_id) for value in values]
        if len(identities) != len(set(identities)):
            raise ValueError("source_refs must be unique")
        return values


class DecideWorkspaceRecordRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    action: Literal[
        "confirm",
        "correct",
        "reject",
        "expire",
        "tombstone",
        "diagnose",
        "candidate_source",
        "invalidate",
    ]
    expected_version: int = Field(ge=1)
    replacement_payload: dict[str, Any] | None = None
    reason: str = Field(default="", max_length=1000)

    @field_validator("command_id")
    @classmethod
    def normalize_workspace_command_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("command_id must not be blank")
        return value

    @field_validator("reason")
    @classmethod
    def normalize_decision_reason(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_replacement(self) -> "DecideWorkspaceRecordRequest":
        requires_payload = self.action in {"correct", "diagnose"}
        if requires_payload and self.replacement_payload is None:
            raise ValueError("replacement_payload is required for correct/diagnose")
        if not requires_payload and self.replacement_payload is not None:
            raise ValueError("replacement_payload is only allowed for correct/diagnose")
        return self
