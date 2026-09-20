from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


MASTER_CASE_SCHEMA_VERSION = "v3.5-master-case-draft-v1"
REVIEW_DECISION_SCHEMA_VERSION = "v3.5-review-decision-draft-v1"
REVIEW_PACKET_VERSION = "v3.5-review-packet-v1"
EVAL_PROTOCOL_DRAFT_VERSION = "v3.5-eval-protocol-draft-v1"
REASON_CODE_DRAFT_VERSION = "v3.5-reason-code-draft-v1"
CALIBRATION_BATCH_VERSION = "v3.5-label-calibration-batch-v1"
ROUND2_BATCH_VERSION = "v3.5-round2-active-review-v1"

SamplingStratum = Literal[
    "likely_evidence_positive",
    "possible_partial",
    "semantic_neighbor_negative",
    "title_only_source_state",
    "no_subtitle_source_state",
    "negative_control",
    "multi_timeline_robustness",
]


class ActiveCalibrationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: Literal["stage2a-followup-calibration-01"]
    batch_version: Literal["v3.5-label-calibration-batch-v1"] = CALIBRATION_BATCH_VERSION
    review_order: int = Field(ge=1, le=6)
    case_id: str
    packet_path: str
    decision_record_id: str
    calibration_focus: str
    review_depth: Literal[
        "quick_authority_check",
        "focused_semantic_review",
        "deep_multi_aspect_review",
        "robustness_review",
    ]
    navigation_summary: str
    special_constraints: tuple[str, ...] = ()
    decision_status: Literal["unreviewed"] = "unreviewed"


class Round2ReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: Literal["stage2b-round2-01"]
    batch_version: Literal["v3.5-round2-active-review-v1"] = ROUND2_BATCH_VERSION
    review_order: int = Field(ge=1, le=8)
    case_id: str
    packet_path: str
    decision_record_id: str
    review_focus: str
    review_depth: Literal[
        "quick_authority_check",
        "seed_assisted_evidence_verification",
        "focused_semantic_review",
        "deep_multi_aspect_review",
    ]
    activation_rationale: str
    special_constraints: tuple[str, ...] = ()
    decision_status: Literal["unreviewed"] = "unreviewed"


class NavigationAid(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aid_type: str
    label: Literal["Navigation Aid Only — Not Annotation Boundary"] = (
        "Navigation Aid Only — Not Annotation Boundary"
    )
    details: dict[str, object] = Field(default_factory=dict)


class MasterCaseCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    case_version: Literal["v3.5-master-case-draft-v1"] = MASTER_CASE_SCHEMA_VERSION
    case_scope: Literal["query_video", "query_corpus"]
    query: str
    query_language: Literal["zh", "en", "mixed"]
    query_type: Literal["exact_entity", "mixed_entity", "semantic_question", "keyword_phrase"]
    target_video_id: int | None = None
    target_bvid: str | None = None
    source_state: Literal[
        "readable_raw", "title_only", "subtitle_missing", "query_corpus"
    ]
    source_artifact_id: str | None = None
    source_version: str | None = None
    source_type: str | None = None
    source_language: str | None = None
    timeline_status: str | None = None
    sampling_stratum: SamplingStratum
    case_origin: str
    candidate_rationale: str
    navigation_aids: tuple[NavigationAid, ...] = ()
    split_constraint: Literal["unassigned", "development_only"] = "unassigned"
    preliminary_leakage_keys: dict[str, str]
    decision_status: Literal["unreviewed"] = "unreviewed"
    applicable_metrics: tuple[str, ...]

    @model_validator(mode="after")
    def validate_scope_and_source(self) -> "MasterCaseCandidate":
        if self.case_scope == "query_corpus":
            if self.target_video_id is not None or self.target_bvid is not None:
                raise ValueError("query_corpus must not contain a target video")
            if self.source_state != "query_corpus":
                raise ValueError("query_corpus must use query_corpus source_state")
            if any((self.source_artifact_id, self.source_version, self.source_type)):
                raise ValueError("query_corpus must not contain source authority fields")
        else:
            if self.target_video_id is None or not self.target_bvid:
                raise ValueError("query_video requires target video identity")
            if self.source_state == "readable_raw":
                if not self.source_artifact_id or not self.source_version:
                    raise ValueError("readable_raw requires artifact identity and version")
                if not re.fullmatch(r"[0-9a-f]{64}", self.source_version):
                    raise ValueError("source_version must be a SHA-256 hex digest")
            elif self.source_artifact_id or self.source_version:
                raise ValueError("unavailable source must not claim artifact authority")
        if self.split_constraint == "development_only" and self.sampling_stratum != "multi_timeline_robustness":
            raise ValueError("development_only is reserved for declared robustness cases")
        return self


class RequiredAspect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aspect_id: str
    description: str
    is_required: bool = True


class EvidenceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    span_id: str
    segment_ids: tuple[str, ...]
    start_time: float
    end_time: float
    timeline_run_id: str


class GoldEvidenceGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: str
    required_spans: tuple[EvidenceSpan, ...]
    supported_aspects: tuple[str, ...]
    group_notes: str = ""

    @model_validator(mode="after")
    def require_one_run(self) -> "GoldEvidenceGroup":
        run_ids = {span.timeline_run_id for span in self.required_spans}
        if len(run_ids) > 1:
            raise ValueError("a Gold Evidence Group must not cross timeline runs")
        return self


class ReviewDecisionTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    review_version: Literal["v3.5-review-decision-draft-v1"] = REVIEW_DECISION_SCHEMA_VERSION
    reviewer: str = ""
    reviewed_at: str = ""
    decision_status: Literal["unreviewed"] = "unreviewed"
    required_aspects: tuple[RequiredAspect, ...] = ()
    gold_evidence_groups: tuple[GoldEvidenceGroup, ...] = ()
    sufficiency_label: Literal["unreviewed"] = "unreviewed"
    supported_aspects: tuple[str, ...] = ()
    missing_aspects: tuple[str, ...] = ()
    conflict_notes: str = ""
    primary_reason_codes: tuple[str, ...] = ()
    support_notes: str = ""
    review_confidence: Literal["unreviewed"] = "unreviewed"
    needs_second_review: Literal["unreviewed"] = "unreviewed"
    reviewer_flags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def reject_prefill(self) -> "ReviewDecisionTemplate":
        if self.required_aspects or self.gold_evidence_groups:
            raise ValueError("unreviewed template must not prefill Gold fields")
        if self.supported_aspects or self.missing_aspects or self.primary_reason_codes:
            raise ValueError("unreviewed template must not prefill decision fields")
        return self


class CompletedReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    review_version: str
    reviewer: str
    reviewed_at: str
    decision_status: Literal["completed"]
    required_aspects: tuple[RequiredAspect, ...]
    gold_evidence_groups: tuple[GoldEvidenceGroup, ...]
    sufficiency_label: Literal["sufficient", "partial", "insufficient", "unverifiable"]
    supported_aspects: tuple[str, ...]
    missing_aspects: tuple[str, ...]
    conflict_notes: str = ""
    primary_reason_codes: tuple[str, ...]
    support_notes: str = ""
    review_confidence: Literal["high", "medium", "low"]
    needs_second_review: bool
    reviewer_flags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_label_semantics(self) -> "CompletedReviewDecision":
        required = {item.aspect_id for item in self.required_aspects if item.is_required}
        supported = set(self.supported_aspects)
        missing = set(self.missing_aspects)
        if self.sufficiency_label == "sufficient" and (not required <= supported or missing):
            raise ValueError("sufficient must support every required aspect and miss none")
        if self.sufficiency_label == "partial" and (not supported or not missing):
            raise ValueError("partial requires non-empty supported and missing aspects")
        if self.sufficiency_label in {"insufficient", "unverifiable"} and self.gold_evidence_groups:
            raise ValueError("no-evidence labels must not contain Gold Evidence Groups")
        return self
