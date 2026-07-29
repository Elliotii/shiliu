from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shiliu.retrieval.planner import SearchValidationError, normalize_query
from shiliu.retrieval.product_search import ProductSearchFilterRequest


CITATION_IDENTITY_VERSION = "v4-citation-identity-v1"

AskMode = Literal["fast", "deep"]
AnswerStatus = Literal["complete", "partial", "insufficient"]
TerminationReason = Literal[
    "answer_ready",
    "budget_exhausted",
    "no_new_evidence",
    "repeated_search",
    "provider_error",
    "evidence_unavailable",
]
CitationSourceType = Literal["human", "ai", "asr", "unknown"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AskRequest(_StrictModel):
    query: str
    mode: AskMode = "fast"
    filters: ProductSearchFilterRequest = Field(
        default_factory=ProductSearchFilterRequest
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        try:
            return normalize_query(value)
        except SearchValidationError as exc:
            raise ValueError(str(exc)) from exc


class AnswerBlock(_StrictModel):
    text: str
    citation_ids: list[str] = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("answer block text must not be empty")
        return normalized

    @field_validator("citation_ids")
    @classmethod
    def validate_citation_ids(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("citation IDs must not be empty")
        return normalized


class Citation(_StrictModel):
    citation_id: str
    citation_identity_version: str
    video_id: int
    bvid: str
    title: str
    source_type: CitationSourceType
    source_language: str
    source_artifact_id: str
    source_version: str
    timeline_run_id: str
    segment_ids: list[str] = Field(min_length=1)
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)
    quote_text: str
    jump_url: str

    @model_validator(mode="after")
    def validate_time_range(self) -> "Citation":
        if self.end_time < self.start_time:
            raise ValueError("citation end_time must not precede start_time")
        if not self.quote_text.strip():
            raise ValueError("citation quote_text must not be empty")
        return self


class TraceSummary(_StrictModel):
    query_count: int = Field(ge=0)
    retrieval_count: int = Field(ge=0)
    valid_evidence_count: int = Field(ge=0)
    stale_evidence_count: int = Field(ge=0)
    context_span_count: int = Field(ge=0)
    context_truncated: bool
    repair_used: bool
    latency_ms: float = Field(ge=0)
    termination_reason: TerminationReason
    decision_rounds: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    visited_video_count: int = Field(default=0, ge=0)
    visited_segment_count: int = Field(default=0, ge=0)
    navigation_result_count: int = Field(default=0, ge=0)
    evidence_candidate_dropped_count: int = Field(default=0, ge=0)


class AskResponse(_StrictModel):
    run_id: str
    mode: AskMode
    status: AnswerStatus
    answer_blocks: list[AnswerBlock]
    citations: list[Citation]
    limitations: list[str]
    termination_reason: TerminationReason
    trace_summary: TraceSummary

    @model_validator(mode="after")
    def validate_answer_shape(self) -> "AskResponse":
        if self.status == "insufficient" and self.answer_blocks:
            raise ValueError("insufficient responses must not contain answer blocks")
        if self.status != "insufficient" and not self.answer_blocks:
            raise ValueError("answering responses must contain answer blocks")
        citation_ids = {citation.citation_id for citation in self.citations}
        for block in self.answer_blocks:
            if not set(block.citation_ids).issubset(citation_ids):
                raise ValueError("answer block references a missing response citation")
        return self


class QueryAnalysis(_StrictModel):
    normalized_intent: str = ""
    search_queries: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    language: str = "unknown"


class GroundedAnswerDraft(_StrictModel):
    status: AnswerStatus
    answer_blocks: list[AnswerBlock]
    limitations: list[str]


class EvidenceSegment(_StrictModel):
    segment_id: str
    original_ordinal: int = Field(ge=0)
    run_local_ordinal: int = Field(ge=0)
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)
    source_text: str


class TranscriptEvidenceSpan(_StrictModel):
    citation_id: str
    citation_identity_version: str = CITATION_IDENTITY_VERSION
    video_id: int
    bvid: str
    title: str
    source_type: CitationSourceType
    source_language: str
    source_artifact_id: str
    source_version: str
    source_version_authority: str
    timeline_run_id: str
    segment_ids: tuple[str, ...]
    segment_ordinals: tuple[int, ...]
    start_time: float
    end_time: float
    quote_text: str
    jump_url: str
    parent_chunk_ids: tuple[str, ...]
    retrieval_provenance: tuple[dict[str, Any], ...]
    segments: tuple[EvidenceSegment, ...] = Field(exclude=True)
    fusion_score: float = Field(default=0, exclude=True)

    def as_citation(self) -> Citation:
        return Citation(
            citation_id=self.citation_id,
            citation_identity_version=self.citation_identity_version,
            video_id=self.video_id,
            bvid=self.bvid,
            title=self.title,
            source_type=self.source_type,
            source_language=self.source_language,
            source_artifact_id=self.source_artifact_id,
            source_version=self.source_version,
            timeline_run_id=self.timeline_run_id,
            segment_ids=list(self.segment_ids),
            start_time=self.start_time,
            end_time=self.end_time,
            quote_text=self.quote_text,
            jump_url=self.jump_url,
        )
