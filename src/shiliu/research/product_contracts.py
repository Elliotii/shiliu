from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateProductResearchRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    objective: str = Field(min_length=1, max_length=2000)
    success_constraints: list[str] = Field(default_factory=list, max_length=16)
    constraint_profile: Literal["grounded_current_evidence"] = (
        "grounded_current_evidence"
    )
    run_immediately: bool = True

    @field_validator("command_id", "objective")
    @classmethod
    def normalize_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("success_constraints")
    @classmethod
    def normalize_constraints(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 1000 for value in normalized):
            raise ValueError("constraints must contain 1..1000 characters")
        return normalized


class RunProductResearchRequest(_StrictModel):
    command_id: str = Field(min_length=1, max_length=160)
    max_steps: int = Field(default=24, ge=1, le=32)

    @field_validator("command_id")
    @classmethod
    def normalize_command_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("command_id must not be blank")
        return normalized
