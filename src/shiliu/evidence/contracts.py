from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


SOURCE_IDENTITY_V1_VERSION = "v3.5-source-identity-v1"
SOURCE_IDENTITY_VERSION = "v3.5-source-identity-v2"
SOURCE_VERSION_AUTHORITY_VERSION = "v3.5-source-version-authority-v1"
TIMELINE_POLICY_VERSION = "v3.5-timeline-policy-v1"
CHUNK_MAPPING_VERSION = "v3.5-exact-chunk-mapping-v1"
SOURCE_CHUNK_POLICY_VERSION = "v3-frozen-transcript-chunk-policy-v1"
REPLAY_IMPLEMENTATION_VERSION = "v3.5-frozen-chunker-replay-v1"
SEARCH_CANDIDATE_CONTRACT_VERSION = "v3.5-search-candidate-v1"
TRACE_POLICY_VERSION = "v3.5-search-trace-policy-v1"
TIMELINE_EPSILON_SECONDS = 1e-6

ValidationStatus = Literal[
    "valid_single_run",
    "valid_multiple_runs",
    "invalid_segment_time",
    "source_unreadable",
]
MappingStatus = Literal[
    "exact_mapped",
    "chunk_segment_mapping_failed",
    "invalid_cross_timeline_chunk",
    "source_version_mismatch",
    "source_unavailable",
    "chunk_policy_version_mismatch",
    "not_applicable",
]
SourceVersionAuthority = Literal[
    "snapshot_manifest",
    "pinned_request",
    "live_current_exact_replay",
]


class EvidenceContractError(RuntimeError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


@dataclass(frozen=True)
class SourceArtifactReference:
    platform: str
    source_id: str
    part: int
    source_type: str
    source_language: str
    artifact_path: str
    artifact_role: str = "raw_subtitle"
    source_lineage: str | None = None


@dataclass(frozen=True)
class SourceVersionBinding:
    source_artifact_id: str
    source_identity_version: str
    source_version: str
    source_version_authority: SourceVersionAuthority
    source_version_verified: bool
    source_version_expected: str
    source_version_actual: str


@dataclass(frozen=True)
class EvidenceWarning:
    code: str
    message: str
    original_ordinal: int | None = None


@dataclass(frozen=True)
class TimelineRun:
    timeline_run_id: str
    run_ordinal: int
    first_original_ordinal: int
    last_original_ordinal: int
    start_time: float
    end_time: float
    segment_count: int


@dataclass(frozen=True)
class RawEvidenceSegment:
    segment_id: str
    source_artifact_id: str
    source_version: str
    original_ordinal: int
    start_time: float
    end_time: float
    source_text: str
    source_type: str
    source_language: str
    segment_digest: str
    timeline_run_id: str
    run_local_ordinal: int

    @property
    def evidence_eligible(self) -> bool:
        return bool(self.source_text.strip())


@dataclass(frozen=True)
class ParsedSourceArtifact:
    reference: SourceArtifactReference
    source_artifact_id: str
    source_version: str
    validation_status: ValidationStatus
    warnings: tuple[EvidenceWarning, ...]
    invalid_segment_ordinals: tuple[int, ...]
    timeline_runs: tuple[TimelineRun, ...]
    segments: tuple[RawEvidenceSegment, ...]


@dataclass(frozen=True)
class RetrievalChunkReference:
    unit_id: str
    chunk_id: str
    start_time: float
    end_time: float
    source_text: str
    content_hash: str


@dataclass(frozen=True)
class ChunkSegmentMapping:
    parent_chunk_id: str
    source_artifact_id: str
    source_version: str
    segment_ids: tuple[str, ...]
    segment_ordinals: tuple[int, ...]
    timeline_run_id: str | None
    mapping_method: Literal["exact_chunk_replay"]
    mapping_status: MappingStatus
    mapping_digest: str
    candidate_eligibility: bool
    mapping_version: str
    source_chunk_policy_version: str
    replay_implementation_version: str
    source_validation_status: ValidationStatus


@dataclass(frozen=True)
class SearchRawUnitCandidate:
    unit_id: str
    video_id: int
    unit_type: Literal["video", "transcript_chunk"]
    raw_rank: int
    raw_score: float
    retrieval_method: str
    subtitle_source: str
    source_language: str | None
    start_time: float | None
    end_time: float | None
    source_artifact_id: str | None
    source_identity_version: str | None
    source_version: str | None
    source_version_authority: SourceVersionAuthority | None
    source_version_verified: bool
    source_version_expected: str | None
    source_version_actual: str | None
    segment_ids: tuple[str, ...]
    segment_ordinals: tuple[int, ...]
    timeline_run_id: str | None
    mapping_status: MappingStatus
    candidate_eligibility: bool
    reason_codes: tuple[str, ...]
    source_chunk_policy_version: str | None
    mapping_version: str | None
    replay_implementation_version: str | None


@dataclass(frozen=True)
class SearchCandidateVideo:
    video_id: int
    source_id: str
    product_rank: int
    title: str
    uploader: str
    best_unit_id: str
    best_unit_type: str
    best_score: float
    component_unit_ids: tuple[str, ...]
    retrieval_methods: tuple[str, ...]
    product_windows: tuple[dict[str, object], ...]
    source_types: tuple[str, ...]
    video_level_hit_present: bool


@dataclass(frozen=True)
class SearchCandidateSet:
    contract_version: str
    original_query: str
    request_parameters: dict[str, object]
    search_trace_id: str
    presentation_trace_id: str | None
    trace_persisted: bool
    presentation_trace_persisted: bool
    executed_mode: str
    query_type: str
    fallback_state: dict[str, object]
    index_identity: dict[str, object]
    raw_unit_candidates: tuple[SearchRawUnitCandidate, ...]
    video_candidates: tuple[SearchCandidateVideo, ...]
    snapshot_id: str | None
    runtime_corpus_identity: str | None
    created_at: str
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def require_candidate(self, unit_id: str) -> SearchRawUnitCandidate:
        for candidate in self.raw_unit_candidates:
            if candidate.unit_id == unit_id:
                return candidate
        raise EvidenceContractError(
            f"candidate is not present in this SearchCandidateSet: {unit_id}",
            code="candidate_not_found",
        )


STAGE1_ERROR_CODES = frozenset(
    {
        "raw_subtitle_missing",
        "source_unreadable",
        "source_version_mismatch",
        "segment_identity_invalid",
        "segment_time_invalid",
        "source_timeline_non_monotonic",
        "chunk_segment_mapping_failed",
        "invalid_cross_timeline_chunk",
        "chunk_policy_version_mismatch",
        "source_unavailable",
        "no_search_candidate",
        "index_not_ready",
        "retrieval_failed",
        "candidate_not_found",
    }
)
