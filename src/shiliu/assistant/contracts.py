from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class KnowledgeSearchArgs(CollectionSearchArgs):
    sources: list[Literal["wiki", "collection"]] = Field(default_factory=lambda: ["wiki", "collection"], min_length=1, max_length=2)
    limit: int = Field(default=5, ge=1, le=10)
    wiki_limit: int = Field(default=3, ge=1, le=8)

    @field_validator("sources")
    @classmethod
    def unique_sources(cls, values):
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def source_parameters(self):
        collection_only = (self.mode == "metadata" or self.cursor is not None or self.folder_ids is not None
                           or self.uploader is not None or self.sort != "relevance"
                           or any(value is not None for value in (self.published_from, self.published_to,
                                                                  self.collected_from, self.collected_to))
                           or self.require_transcript)
        if collection_only and self.sources != ["collection"]:
            raise ValueError("收藏专属筛选及元数据分页请使用 sources=[collection]")
        if "wiki" in self.sources and not str(self.query or "").strip():
            raise ValueError("Wiki 检索需要 query")
        return self


class CollectionReadArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_ref: str = Field(
        pattern=r"^video:[1-9][0-9]*(?::[0-9a-f]{64})?$"
    )
    view: Literal["overview", "description", "summary", "notes", "transcript"] = "overview"
    revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    cursor: str | None = None
    query: str | None = Field(default=None, max_length=200)
    max_characters: int = Field(default=24000, ge=1000, le=40000)
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


def search_material_projection(result: dict[str, Any], *, origin: str) -> list[dict[str, Any]]:
    """Project candidate identity without claiming body reads or lineage delivery."""
    values = []
    for group in result.get("items") or []:
        for candidate in group.get("candidates") or []:
            wiki = group.get("source") == "wiki"
            values.append({
                "source_ref": f"wiki:{candidate['page_id']}:{candidate['page_version']}" if wiki else candidate.get("source_ref", ""),
                "title": candidate.get("title", ""), "kind": "search_knowledge", "view": "candidate_excerpt",
                "position": {"block_ids": [hit["block_id"] for hit in candidate.get("hits") or []]} if wiki else {},
                "complete": False, "projection": "候选摘要（未读取正文）", "origin": origin,
                **({"lineage_refs": group.get("source_refs") or []} if wiki else {}),
            })
    return values
