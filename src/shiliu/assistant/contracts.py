from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ToolStatus = Literal[
    "ok", "empty", "partial", "unavailable", "timeout",
    "invalid_arguments", "cancelled", "outcome_unknown",
]


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    status: ToolStatus
    summary: str
    items: list[dict[str, Any]] = Field(default_factory=list)
    result_ref: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    dependency_refs: list[str] = Field(default_factory=list)
    truncated: bool = False
    next_cursor: str | None = None
    observed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    error_code: str | None = None
    retryable: bool = False
    coverage: dict[str, Any] = Field(default_factory=dict)


class CollectionSearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str | None = Field(default=None, max_length=2000)
    query_variants: list[str] = Field(default_factory=list, max_length=2)
    require_transcript: bool = False
    mode: Literal["auto", "metadata", "content"] = "auto"
    cursor: str | None = None
    folder_ids: list[int] | None = None
    published_from: int | None = Field(default=None, ge=1)
    published_to: int | None = Field(default=None, ge=1)
    collected_from: int | None = Field(default=None, ge=1)
    collected_to: int | None = Field(default=None, ge=1)
    uploader: str | None = Field(default=None, max_length=200)
    sort: Literal["relevance", "collected_desc", "published_desc"] = "relevance"
    limit: int = Field(default=10, ge=1, le=10)


class CollectionReadArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_ref: str = Field(
        pattern=r"^video:[1-9][0-9]*(?::[0-9a-f]{64})?$"
    )
    view: Literal["overview", "description", "summary", "notes", "transcript"] = "overview"
    revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    cursor: str | None = None
    query: str | None = Field(default=None, max_length=200)
    max_characters: int = Field(default=8000, ge=1000, le=12000)
    refresh_metadata: bool = False


COLLECTION_TOOL_SCHEMAS = {
    "collection_search": CollectionSearchArgs.model_json_schema(),
    "collection_read": CollectionReadArgs.model_json_schema(),
}


class MaterialDescriptor(BaseModel):
    kind: Literal["raw_subtitle", "transcript", "summary", "user_note", "description"]
    available: bool
    subtitle_source: str | None = None
    revision: str | None = None
    content_hash: str | None = None


class MembershipTime(BaseModel):
    source_db_id: int
    folder_id: int
    folder_title: str
    favorite_time: str | None
    first_observed_at: str


class SourceView(BaseModel):
    source_ref: str
    revision: str
    kind: Literal["video"] = "video"
    video: dict[str, Any]
    time: dict[str, Any]
    materials: list[MaterialDescriptor]
    coverage: Literal[
        "metadata_only", "summary_based", "partial_transcript", "full_available_transcript"
    ]
    content: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
