from __future__ import annotations

from dataclasses import asdict, dataclass
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shiliu.retrieval.models import RetrievalFilters


SearchMode = Literal["lexical", "dense", "hybrid", "auto"]
QueryType = Literal["exact_entity", "mixed_entity", "semantic_question", "keyword_phrase"]
Scope = Literal["all", "video", "transcript_chunk"]

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_ASCII_ENTITY = re.compile(r"^[A-Za-z0-9 ._\-+/#:]+$")
_QUESTION_WORDS = re.compile(
    r"(?:如何|怎么|怎样|为什么|为何|是否|什么|哪种|"
    r"\bhow\b|\bwhy\b|\bwhat\b|\bwhen\b|\bwhere\b|\bwhich\b)",
    re.IGNORECASE,
)


class SearchValidationError(ValueError):
    pass


class SearchFilterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_db_id: int | None = Field(default=None, gt=0)
    folder_id: int | None = Field(default=None, gt=0)
    favorite_time_from: int | None = None
    favorite_time_to: int | None = None
    reading_state: Literal["unread", "in_progress", "read"] | None = None
    marked: bool | None = None
    uploader: str | None = Field(default=None, max_length=200)
    archived: bool | None = None
    ignored: bool = False

    @field_validator("uploader")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @model_validator(mode="after")
    def validate_range(self) -> "SearchFilterRequest":
        if (
            self.favorite_time_from is not None
            and self.favorite_time_to is not None
            and self.favorite_time_from > self.favorite_time_to
        ):
            raise ValueError("favorite_time_from must not exceed favorite_time_to")
        return self

    def retrieval_filters(self) -> RetrievalFilters:
        return RetrievalFilters(
            source_db_id=self.source_db_id,
            folder_id=self.folder_id,
            favorite_time_from=self.favorite_time_from,
            favorite_time_to=self.favorite_time_to,
            reading_state=self.reading_state,
            is_marked=self.marked,
            uploader=self.uploader,
            archived=self.archived,
        )

    def active_dict(self) -> dict[str, object]:
        values = self.model_dump(exclude_none=True)
        if not values.get("ignored"):
            values.pop("ignored", None)
        return values


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    mode: SearchMode = "lexical"
    scope: Scope = "all"
    raw_top_k: int = Field(default=20, ge=1, le=100)
    filters: SearchFilterRequest = Field(default_factory=SearchFilterRequest)


@dataclass(frozen=True)
class SearchPlan:
    raw_query: str
    normalized_query: str
    query_type: QueryType
    requested_mode: SearchMode
    planned_mode: Literal["lexical", "dense", "hybrid"]
    scope: Scope
    raw_top_k: int
    validated_filters: dict[str, object]
    routing_reason: str
    fallback_allowed: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class SearchPlanner:
    def plan(self, request: SearchRequest) -> SearchPlan:
        raw_query = request.query
        normalized = normalize_query(raw_query)
        query_type = classify_query(normalized)
        if request.mode == "auto":
            if query_type == "exact_entity":
                planned_mode = "lexical"
                reason = "short_ascii_entity"
            else:
                planned_mode = "hybrid"
                reason = {
                    "mixed_entity": "entity_plus_semantic_context",
                    "semantic_question": "semantic_question_dual_signal",
                    "keyword_phrase": "keyword_phrase_dual_signal",
                }[query_type]
        else:
            planned_mode = request.mode
            reason = "explicit_mode"
        return SearchPlan(
            raw_query=raw_query,
            normalized_query=normalized,
            query_type=query_type,
            requested_mode=request.mode,
            planned_mode=planned_mode,
            scope=request.scope,
            raw_top_k=request.raw_top_k,
            validated_filters=request.filters.active_dict(),
            routing_reason=reason,
            fallback_allowed=request.mode == "auto" and planned_mode == "hybrid",
        )


def normalize_query(raw_query: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", raw_query).split())
    if not normalized:
        raise SearchValidationError("query must not be empty")
    if len(normalized) > 500:
        raise SearchValidationError("normalized query must not exceed 500 characters")
    return normalized


def classify_query(query: str) -> QueryType:
    has_ascii = bool(re.search(r"[A-Za-z]", query))
    has_cjk = bool(_CJK.search(query))
    if _is_semantic_question(query, has_cjk=has_cjk):
        return "semantic_question"
    if has_ascii and has_cjk:
        return "mixed_entity"
    tokens = query.split()
    if (
        has_ascii
        and not has_cjk
        and len(query) <= 64
        and len(tokens) <= 6
        and _ASCII_ENTITY.fullmatch(query) is not None
    ):
        return "exact_entity"
    return "keyword_phrase"


def _is_semantic_question(query: str, *, has_cjk: bool) -> bool:
    if "?" in query or "？" in query or _QUESTION_WORDS.search(query):
        return True
    if has_cjk:
        return len(query) >= 24
    return len(query) >= 80 and len(query.split()) >= 8
