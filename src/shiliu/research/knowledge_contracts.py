from __future__ import annotations

from typing import Literal

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
