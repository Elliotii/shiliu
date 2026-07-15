from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VideoStatus(str, Enum):
    DISCOVERED = "discovered"
    SUBTITLE_PENDING = "subtitle_pending"
    TRANSCRIPT_PROCESSING = "transcript_processing"
    SUMMARY_PROCESSING = "summary_processing"
    RETRY_WAIT = "retry_wait"
    COMPLETED = "completed"
    SKIPPED_NO_SUBTITLE = "skipped_no_subtitle"
    NEEDS_REVIEW = "needs_review"


class StageName(str, Enum):
    TRANSCRIPT = "transcript_cleanup"
    SUMMARY = "summary_generation"
    REFINED_TRANSCRIPT = "refined_transcript_cleanup"
    REFINEMENT_REVIEW = "refinement_review"


class StageStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    RETRY_WAIT = "retry_wait"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"


class SyncMode(str, Enum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class ProcessingProfile(str, Enum):
    FAST = "fast"
    FORMAL = "formal"


class RefinementStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ReadingState(str, Enum):
    UNREAD = "unread"
    IN_PROGRESS = "in_progress"
    READ = "read"


class SubtitleLanguage(str, Enum):
    ZH = "zh"
    EN = "en"


class SubtitleSource(str, Enum):
    HUMAN = "human"
    AI = "ai"
    ASR = "asr"
    UNKNOWN = "unknown"


class ASRTriggerMode(str, Enum):
    AUTOMATIC = "automatic"
    MANUAL = "manual"


class ASRJobStatus(str, Enum):
    PENDING = "pending"
    AUDIO_DOWNLOADING = "audio_downloading"
    UPLOADING = "uploading"
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    RETRY_WAIT = "retry_wait"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"


class FavoriteItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bvid: str
    title: str
    uploader: str = ""
    duration_seconds: int = 0
    favorite_time: int | None = None


class FavoriteSourcePreview(BaseModel):
    account_id: int
    account_name: str
    folder_id: int
    folder_title: str
    media_count: int
    original_url: str = ""


class SubtitleTrack(BaseModel):
    model_config = ConfigDict(extra="allow")

    language: SubtitleLanguage
    source: SubtitleSource
    upstream_type: int | None = None
    upstream_language: str = ""
    upstream_language_label: str = ""


class SubtitleSegment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    start: float = Field(alias="from")
    end: float = Field(alias="to")
    content: str


class VideoBundle(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bvid: str
    title: str
    uploader: str = ""
    description: str = ""
    video_url: str
    cover_url: str | None = None
    cid: int | None = None
    part_title: str = ""
    duration_seconds: int = 0
    page_count: int = 1
    subtitle_track: SubtitleTrack | None = None
    subtitle_segments: list[SubtitleSegment] = Field(default_factory=list)


class TranscriptSection(BaseModel):
    title: str = Field(min_length=1)
    start_seconds: float | None = Field(default=None, ge=0)
    paragraphs: list[str] = Field(min_length=1)

    @field_validator("paragraphs")
    @classmethod
    def paragraphs_must_have_text(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if not cleaned:
            raise ValueError("paragraphs must contain text")
        return cleaned


class TranscriptResult(BaseModel):
    sections: list[TranscriptSection] = Field(min_length=1)


class ImportantChapter(BaseModel):
    title: str = Field(min_length=1)
    start_seconds: float = Field(ge=0)
    summary: str = ""


class EntityItem(BaseModel):
    name: str = Field(min_length=1)
    kind: str = ""
    note: str = ""


class ActionItem(BaseModel):
    action: str = Field(min_length=1)
    rationale: str = ""


class SummaryResult(BaseModel):
    conclusion: str = Field(min_length=1)
    key_points: list[str] = Field(min_length=3, max_length=7)
    detailed_notes: list[str] = Field(min_length=1)
    important_chapters: list[ImportantChapter] = Field(default_factory=list)
    entities: list[EntityItem] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    related_links: list[str] = Field(default_factory=list)


class SummaryReviewResult(BaseModel):
    decision: str
    change_reasons: list[str] = Field(default_factory=list)
    revised_summary: SummaryResult | None = None

    @field_validator("decision")
    @classmethod
    def decision_is_supported(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"keep", "revise"}:
            raise ValueError("decision must be keep or revise")
        return normalized

    @field_validator("revised_summary")
    @classmethod
    def revised_summary_matches_decision(
        cls, value: SummaryResult | None, info: Any
    ) -> SummaryResult | None:
        if info.data.get("decision") == "revise" and value is None:
            raise ValueError("revised_summary is required when decision is revise")
        return value


class SyncResult(BaseModel):
    mode: SyncMode
    skipped_quiet_hours: bool = False
    baseline_created: bool = False
    current_count: int = 0
    discovered_count: int = 0
    processed_count: int = 0
    failed_count: int = 0
    history_pending_count: int = 0
    run_id: int | None = None
    messages: list[str] = Field(default_factory=list)


class ProviderErrorKind(str, Enum):
    RETRYABLE = "retryable"
    AUTHENTICATION = "authentication"
    FORBIDDEN = "forbidden"
    MODEL_NOT_FOUND = "model_not_found"
    BAD_CONFIG = "bad_config"
    CONTEXT_TOO_LARGE = "context_too_large"


class PipelineError(RuntimeError):
    def __init__(self, message: str, *, code: str, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


JsonDict = dict[str, Any]
