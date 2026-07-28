"""Fast transcript-grounded Ask runtime."""

from shiliu.ask.citations import stable_citation_id
from shiliu.ask.context import (
    ContextBuildResult,
    TranscriptContextBuilder,
    fuse_evidence,
)
from shiliu.ask.contracts import (
    CITATION_IDENTITY_VERSION,
    AnswerBlock,
    AskRequest,
    AskResponse,
    Citation,
    GroundedAnswerDraft,
    QueryAnalysis,
    TraceSummary,
    TranscriptEvidenceSpan,
)
from shiliu.ask.service import AskModeNotImplemented, AskService

__all__ = [
    "CITATION_IDENTITY_VERSION",
    "AnswerBlock",
    "AskModeNotImplemented",
    "AskRequest",
    "AskResponse",
    "AskService",
    "Citation",
    "ContextBuildResult",
    "GroundedAnswerDraft",
    "QueryAnalysis",
    "TraceSummary",
    "TranscriptContextBuilder",
    "TranscriptEvidenceSpan",
    "fuse_evidence",
    "stable_citation_id",
]
