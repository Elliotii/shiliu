from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MASTER_CASE_SCHEMA_VERSION = "v3.5-master-case-v2"
ANNOTATION_PACKET_VERSION = "v3.5-annotation-packet-v2"
ANNOTATION_REVIEW_SCHEMA_VERSION = "v3.5-annotation-review-v2"
ANNOTATION_AGREEMENT_VERSION = "v3.5-annotation-agreement-v2"
ANNOTATION_PROTOCOL_VERSION = "v3.5-annotation-protocol-v2"
PRIMARY_PROMPT_VERSION = "v3.5-primary-reviewer-prompt-v2"
SECONDARY_PROMPT_VERSION = "v3.5-secondary-reviewer-prompt-v2"
LEAKAGE_POLICY_VERSION = "v3.5-leakage-policy-v2"
PILOT_SELECTION_POLICY_VERSION = "v3.5-pilot-selection-policy-v2"

Status = Literal["sufficient", "partial", "insufficient", "unverifiable"]
SourceType = Literal["raw_subtitle", "raw_asr"]
Confidence = Literal["high", "medium", "low"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Lineage(StrictModel):
    origin: Literal["v3_query", "eval_v1", "new_case"]
    parent_refs: tuple[str, ...] = ()
    derivation_notes: str = ""


class CaseIdentity(StrictModel):
    case_id: str = Field(pattern=r"^V2C_[A-Z0-9]{8,}$")
    query: str = Field(min_length=1)
    query_language: str = Field(min_length=2)
    query_family: str = Field(min_length=1)
    query_type: str = Field(min_length=1)
    leakage_group: str = Field(pattern=r"^LGV2_[A-Z0-9_]+$")
    lineage: Lineage
    case_status: Literal["candidate", "pilot", "adjudicated", "frozen", "retired"]


class SourceAvailability(StrictModel):
    video_id: str
    status: Literal["available", "missing", "unreadable", "version_unknown", "integrity_failed"]
    reason: str = ""


class CorpusTruth(StrictModel):
    target_video_ids: tuple[str, ...]
    acceptable_video_ids: tuple[str, ...]
    source_availability: tuple[SourceAvailability, ...]
    source_types: tuple[SourceType, ...]
    source_artifact_ids: tuple[str, ...]
    source_versions: tuple[str, ...]
    languages: tuple[str, ...]
    timeline_runs: tuple[str, ...]
    source_limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def authority_is_explicit(self) -> "CorpusTruth":
        if not self.target_video_ids:
            raise ValueError("target_video_ids must not be empty")
        if not set(self.target_video_ids) <= set(self.acceptable_video_ids):
            raise ValueError("target videos must be acceptable videos")
        available = any(x.status == "available" for x in self.source_availability)
        authority = bool(self.source_artifact_ids and self.source_versions and self.timeline_runs)
        if available != authority:
            raise ValueError("available Raw Source requires artifact, version, and timeline identity")
        return self


class RetrievalGold(StrictModel):
    relevant_video_ids: tuple[str, ...]
    acceptable_video_ids: tuple[str, ...]
    relevant_chunk_ids: tuple[str, ...] = ()
    hard_negative_video_ids: tuple[str, ...] = ()
    expected_retrieval_state: Literal[
        "transcript_chunk_reachable", "video_level_only", "empty_search_candidate",
        "wrong_video_recall", "semantic_neighbor_only", "filter_or_scope_exclusion",
        "not_applicable",
    ]
    retrieval_notes: str = ""


class Aspect(StrictModel):
    aspect_id: str = Field(pattern=r"^A[1-9][0-9]*$")
    description: str = Field(min_length=1)


class Span(StrictModel):
    span_id: str = Field(pattern=r"^S[1-9][0-9]*$")
    video_id: str
    source_artifact_id: str
    source_version: str
    timeline_run_id: str
    segment_ids: tuple[str, ...] = Field(min_length=1)
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)
    source_language: str
    source_type: SourceType
    span_role: Literal["required", "optional_context", "conflict"]
    required_aspect_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def span_invariants(self) -> "Span":
        if self.end_time < self.start_time:
            raise ValueError("span end_time precedes start_time")
        if self.span_role == "required" and not self.required_aspect_ids:
            raise ValueError("required span must map to a required aspect")
        if self.span_role != "required" and self.required_aspect_ids:
            raise ValueError("only required spans map to required aspects")
        return self


class EvidenceGroup(StrictModel):
    group_id: str = Field(pattern=r"^G[1-9][0-9]*$")
    required_aspect_ids: tuple[str, ...] = Field(min_length=1)
    required_span_ids: tuple[str, ...] = Field(min_length=1)
    alternative_expression_notes: str = ""


class EvidenceGold(StrictModel):
    required_aspects: tuple[Aspect, ...]
    acceptable_evidence_groups: tuple[EvidenceGroup, ...]
    required_spans: tuple[Span, ...]
    optional_context_spans: tuple[Span, ...] = ()
    evidence_notes: str = ""

    @model_validator(mode="after")
    def references_are_closed(self) -> "EvidenceGold":
        aspects = {x.aspect_id for x in self.required_aspects}
        spans = {x.span_id for x in self.required_spans}
        if len(aspects) != len(self.required_aspects) or len(spans) != len(self.required_spans):
            raise ValueError("aspect and span IDs must be unique")
        if any(x.span_role != "required" for x in self.required_spans):
            raise ValueError("required_spans must have required role")
        if any(x.span_role != "optional_context" for x in self.optional_context_spans):
            raise ValueError("optional_context_spans must have optional_context role")
        for span in self.required_spans:
            if not set(span.required_aspect_ids) <= aspects:
                raise ValueError("required span references unknown aspect")
        for group in self.acceptable_evidence_groups:
            if not set(group.required_aspect_ids) <= aspects or not set(group.required_span_ids) <= spans:
                raise ValueError("evidence group contains an unknown reference")
            selected = [x for x in self.required_spans if x.span_id in group.required_span_ids]
            source_runs: dict[tuple[str, str, str], set[str]] = {}
            for span in selected:
                source = (span.video_id, span.source_artifact_id, span.source_version)
                source_runs.setdefault(source, set()).add(span.timeline_run_id)
            if any(len(runs) > 1 for runs in source_runs.values()):
                raise ValueError("one source inside an evidence group cannot cross timeline runs")
        return self


class SufficiencyGold(StrictModel):
    status: Status
    supported_aspects: tuple[str, ...]
    missing_aspects: tuple[str, ...]
    reason_codes: tuple[str, ...]
    conflict_notes: str = ""
    confidence: Confidence
    boundary_notes: str = ""


class MasterCaseV2(StrictModel):
    master_case_schema_version: Literal["v3.5-master-case-v2"] = MASTER_CASE_SCHEMA_VERSION
    case_identity: CaseIdentity
    corpus_truth: CorpusTruth
    retrieval_gold: RetrievalGold
    evidence_gold: EvidenceGold
    sufficiency_gold: SufficiencyGold

    @model_validator(mode="before")
    @classmethod
    def forbid_future_gold(cls, value: object) -> object:
        if isinstance(value, dict) and ({"answer_gold", "agentic_search_gold"} & set(value)):
            raise ValueError("answer_gold and agentic_search_gold are forbidden in v2")
        return value

    @model_validator(mode="after")
    def sufficiency_invariants(self) -> "MasterCaseV2":
        required = {x.aspect_id for x in self.evidence_gold.required_aspects}
        supported, missing = set(self.sufficiency_gold.supported_aspects), set(self.sufficiency_gold.missing_aspects)
        if not supported | missing <= required or supported & missing:
            raise ValueError("supported/missing aspects must partition known required aspects")
        available = any(x.status == "available" for x in self.corpus_truth.source_availability)
        status = self.sufficiency_gold.status
        if status == "sufficient" and (supported != required or missing or not self.evidence_gold.acceptable_evidence_groups):
            raise ValueError("sufficient requires all aspects and a complete evidence route")
        if status == "partial" and (not supported or not missing or not available or not self.evidence_gold.acceptable_evidence_groups):
            raise ValueError("partial requires supported + missing aspects, readable Raw Source, and evidence")
        if status == "insufficient" and (supported or not available):
            raise ValueError("insufficient requires readable Raw Source and no substantive supported aspect")
        if status == "unverifiable" and available:
            raise ValueError("unverifiable requires unavailable or unreliable Raw Source")
        return self


class TranscriptSegment(StrictModel):
    segment_id: str
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)
    text: str
    source_language: str
    source_type: SourceType
    timeline_run_id: str
    source_artifact_id: str
    source_version: str


class AnnotationPacketV2(StrictModel):
    packet_version: Literal["v3.5-annotation-packet-v2"] = ANNOTATION_PACKET_VERSION
    case_id: str
    query: str
    query_language: str
    full_raw_transcript: tuple[TranscriptSegment, ...]
    source_metadata: dict[str, object]
    segment_schema: str = "v3.5-raw-segment-review-v2"
    annotation_protocol_version: Literal["v3.5-annotation-protocol-v2"] = ANNOTATION_PROTOCOL_VERSION
    review_output_schema_version: Literal["v3.5-annotation-review-v2"] = ANNOTATION_REVIEW_SCHEMA_VERSION
    case_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Usage(StrictModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)


class ReviewMetadata(StrictModel):
    reviewer_provider: str
    reviewer_model: str
    reviewer_role: Literal["primary", "secondary"]
    prompt_version: str
    packet_version: str
    case_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_schema_version: Literal["v3.5-annotation-review-v2"] = ANNOTATION_REVIEW_SCHEMA_VERSION
    started_at: datetime
    completed_at: datetime
    latency_ms: int = Field(ge=0)
    usage: Usage
    validation_status: Literal["valid", "invalid"]
    repair_count: int = Field(ge=0, le=1)


class ReviewBody(StrictModel):
    status: Status
    required_aspects: tuple[Aspect, ...]
    supported_aspects: tuple[str, ...]
    missing_aspects: tuple[str, ...]
    acceptable_evidence_groups: tuple[EvidenceGroup, ...]
    required_spans: tuple[Span, ...]
    optional_context_spans: tuple[Span, ...] = ()
    reason_codes: tuple[str, ...]
    conflict_notes: str = ""
    confidence: Confidence
    boundary_notes: str = ""
    reviewed_full_transcript: bool
    transcript_first_segment_id: str | None
    transcript_last_segment_id: str | None


class AnnotationReviewV2(StrictModel):
    case_id: str
    review_metadata: ReviewMetadata
    review: ReviewBody


class AgreementMetric(StrictModel):
    state: Literal["agree", "disagree", "unresolved", "not_applicable"]
    score: float | None = Field(default=None, ge=0, le=1)
    details: dict[str, object] = Field(default_factory=dict)


class AnnotationAgreementV2(StrictModel):
    agreement_version: Literal["v3.5-annotation-agreement-v2"] = ANNOTATION_AGREEMENT_VERSION
    case_id: str
    case_input_sha256: str
    status: Literal["passed", "passed_requires_spot_check", "mandatory_human_review", "invalid_review", "input_mismatch"]
    label_exact_agreement: bool
    required_aspect_agreement: AgreementMetric
    supported_aspect_agreement: AgreementMetric
    missing_aspect_agreement: AgreementMetric
    evidence_group_agreement: AgreementMetric
    required_span_overlap: AgreementMetric
    time_region_overlap: AgreementMetric
    source_agreement: bool
    reason_code_agreement: AgreementMetric
    confidence_difference: int
    mandatory_triggers: tuple[str, ...]
    human_adjudication_required: bool
    spot_check_status: Literal["not_selected", "selected", "not_applicable"]


class AdjudicationDecision(StrictModel):
    adjudication_status: Literal["pending", "approved"]
    adjudicator: str
    final_label: Status | None = None
    final_required_aspects: tuple[Aspect, ...] = ()
    final_evidence_groups: tuple[EvidenceGroup, ...] = ()
    final_spans: tuple[Span, ...] = ()
    changes_from_primary: str = ""
    changes_from_secondary: str = ""
    adjudication_reason: str = ""
    approved_at: datetime | None = None
