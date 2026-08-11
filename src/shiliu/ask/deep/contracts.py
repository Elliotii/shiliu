from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shiliu.ask.contracts import TerminationReason, TranscriptEvidenceSpan
from shiliu.retrieval.planner import normalize_query
from shiliu.retrieval.product_search import ProductSearchFilterRequest


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchNavigationAction(_StrictModel):
    kind: Literal["search_navigation"]
    query: str

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        return normalize_query(value)


class SearchTranscriptsAction(_StrictModel):
    kind: Literal["search_transcripts"]
    query: str
    video_ids: list[int] = Field(default_factory=list, max_length=8)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        return normalize_query(value)

    @field_validator("video_ids")
    @classmethod
    def validate_video_ids(cls, values: list[int]) -> list[int]:
        if any(value <= 0 for value in values):
            raise ValueError("video_ids must be positive")
        return list(dict.fromkeys(values))


class ReadTranscriptWindowAction(_StrictModel):
    kind: Literal["read_transcript_window"]
    anchor_segment_id: str = Field(min_length=1)
    before: int = Field(default=2, ge=0, le=4)
    after: int = Field(default=2, ge=0, le=4)

    @field_validator("anchor_segment_id")
    @classmethod
    def normalize_anchor(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("anchor_segment_id must not be empty")
        return normalized


class FinishAction(_StrictModel):
    kind: Literal["finish"]
    summary: str = Field(default="", max_length=500)


class StopAction(_StrictModel):
    kind: Literal["stop"]
    summary: str = Field(default="", max_length=500)


AgentAction = Annotated[
    SearchNavigationAction
    | SearchTranscriptsAction
    | ReadTranscriptWindowAction
    | FinishAction
    | StopAction,
    Field(discriminator="kind"),
]


class ResolvedQuestionSuggestion(_StrictModel):
    question: str
    citation_ids: list[str] = Field(min_length=1, max_length=12)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        return normalize_query(value)


class AgentDecision(_StrictModel):
    action: AgentAction
    open_questions: list[str] = Field(default_factory=list, max_length=6)
    resolved_questions: list[ResolvedQuestionSuggestion] = Field(
        default_factory=list, max_length=6
    )

    @field_validator("open_questions")
    @classmethod
    def normalize_questions(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(normalize_query(value) for value in values))[:6]


class NavigationSourceLabel(_StrictModel):
    source: str
    navigation_allowed: bool = True
    citation_allowed: bool = False
    priority: Literal["high", "medium", "low", "enrichment"] = "low"


class NavigationDocument(_StrictModel):
    video_id: int
    bvid: str
    title: str
    uploader: str
    description: str
    summary_sections: list[str]
    user_notes: list[str] = Field(default_factory=list)
    cleaned_transcript: list[str] = Field(default_factory=list)
    metadata: dict[str, Any]
    matched_excerpt: str
    matched_sources: list[str]
    source_labels: dict[str, NavigationSourceLabel]
    authority: Literal["navigation_only"] = "navigation_only"


class ToolObservation(_StrictModel):
    kind: Literal["navigation", "transcript_search", "transcript_window"]
    summary: str = Field(max_length=1000)
    navigation_documents: list[NavigationDocument] = Field(default_factory=list)
    evidence_spans: list[TranscriptEvidenceSpan] = Field(default_factory=list)
    stale_reasons: list[str] = Field(default_factory=list)
    dropped_evidence_count: int = Field(default=0, ge=0)
    error: str | None = Field(default=None, max_length=500)
    latency_ms: float = Field(default=0, ge=0)
    search_executions: list[dict[str, Any]] = Field(
        default_factory=list, max_length=3
    )


class DeepSearchState(TypedDict):
    run_id: str
    query: str
    filters: ProductSearchFilterRequest
    open_questions: list[str]
    resolved_questions: list[dict[str, Any]]
    evidence_spans: list[TranscriptEvidenceSpan]
    navigation_documents: list[NavigationDocument]
    visited_video_ids: list[int]
    visited_segment_ids: list[str]
    previous_queries: list[str]
    repeated_action_keys: list[str]
    decision_rounds: int
    tool_calls: int
    consecutive_no_new_evidence: int
    navigation_result_count: int
    started_at: float
    search_deadline: float
    total_deadline: float
    last_action: dict[str, Any] | None
    last_observation_summary: str
    pending_observation: ToolObservation | None
    errors: list[str]
    stale_reasons: list[str]
    events: list[dict[str, Any]]
    usage: list[dict[str, Any]]
    termination_reason: TerminationReason | None
