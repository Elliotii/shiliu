from __future__ import annotations

import hashlib
import re
import unicodedata

from .contracts import AgreementMetric, AnnotationAgreementV2, AnnotationReviewV2, Span

ASPECT_THRESHOLD = 0.80
SEGMENT_IOU_THRESHOLD = 0.50
TIME_IOU_THRESHOLD = 0.50


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[\w]+", value, flags=re.UNICODE))


def _token_score(left: str, right: str) -> float:
    a, b = set(normalize_text(left).split()), set(normalize_text(right).split())
    return len(a & b) / len(a | b) if a | b else 1.0


def _aspect_metric(left: tuple, right: tuple) -> AgreementMetric:
    a, b = [normalize_text(x.description) for x in left], [normalize_text(x.description) for x in right]
    if a == b:
        return AgreementMetric(state="agree", score=1.0, details={"method": "normalized_exact"})
    if len(a) != len(b) or not a or not b:
        return AgreementMetric(state="unresolved", score=0.0, details={"count_difference": abs(len(a)-len(b))})
    scores = [max(_token_score(item, other) for other in b) for item in a]
    score = sum(scores) / len(scores)
    state = "agree" if score >= ASPECT_THRESHOLD else "unresolved"
    return AgreementMetric(state=state, score=score, details={"method": "deterministic_token_overlap"})


def _set_metric(left: set[str], right: set[str]) -> AgreementMetric:
    score = len(left & right) / len(left | right) if left | right else 1.0
    return AgreementMetric(state="agree" if left == right else "disagree", score=score)


def _aspect_semantics(body, aspect_ids: tuple[str, ...]) -> set[str]:
    descriptions = {aspect.aspect_id: normalize_text(aspect.description) for aspect in body.required_aspects}
    return {descriptions[aspect_id] for aspect_id in aspect_ids if aspect_id in descriptions}


def _group_semantics(body) -> set[tuple[tuple[str, ...], tuple[str, ...]]]:
    spans = {span.span_id: span for span in body.required_spans}
    descriptions = {aspect.aspect_id: normalize_text(aspect.description) for aspect in body.required_aspects}
    return {
        (
            tuple(sorted(descriptions[aspect_id] for aspect_id in group.required_aspect_ids)),
            tuple(
                sorted(
                    segment
                    for span_id in group.required_span_ids
                    for segment in spans[span_id].segment_ids
                )
            ),
        )
        for group in body.acceptable_evidence_groups
        if set(group.required_span_ids) <= set(spans)
        and set(group.required_aspect_ids) <= set(descriptions)
    }


def _segment_iou(left: tuple[Span, ...], right: tuple[Span, ...]) -> AgreementMetric:
    a = {x for span in left for x in span.segment_ids}
    b = {x for span in right for x in span.segment_ids}
    score = len(a & b) / len(a | b) if a | b else 1.0
    recall_ab = len(a & b) / len(a) if a else 1.0
    recall_ba = len(a & b) / len(b) if b else 1.0
    return AgreementMetric(state="agree" if score >= SEGMENT_IOU_THRESHOLD else "disagree", score=score,
                           details={"primary_recall": recall_ab, "secondary_recall": recall_ba})


def _time_iou(left: tuple[Span, ...], right: tuple[Span, ...]) -> AgreementMetric:
    if not left and not right:
        return AgreementMetric(state="agree", score=1.0)
    if not left or not right:
        return AgreementMetric(state="disagree", score=0.0)
    a0, a1 = min(x.start_time for x in left), max(x.end_time for x in left)
    b0, b1 = min(x.start_time for x in right), max(x.end_time for x in right)
    intersection = max(0.0, min(a1, b1) - max(a0, b0))
    union = max(a1, b1) - min(a0, b0)
    score = intersection / union if union else 1.0
    return AgreementMetric(state="agree" if score >= TIME_IOU_THRESHOLD else "disagree", score=score)


def selected_for_spot_check(case_id: str, seed: str = "stage2r-a-v2", rate: float = 0.20) -> bool:
    if not 0.15 <= rate <= 0.25:
        raise ValueError("spot-check rate must be between 15% and 25%")
    number = int(hashlib.sha256(f"{seed}:{case_id}".encode()).hexdigest()[:16], 16) / 2**64
    return number < rate


def compare_reviews(primary: AnnotationReviewV2, secondary: AnnotationReviewV2,
                    *, cross_language: bool = False, asr_error: bool = False) -> AnnotationAgreementV2:
    if primary.review_metadata.validation_status != "valid" or secondary.review_metadata.validation_status != "valid":
        return _terminal(primary, "invalid_review", ("invalid_after_repair",))
    if primary.review_metadata.case_input_sha256 != secondary.review_metadata.case_input_sha256:
        return _terminal(primary, "input_mismatch", ("input_hash_mismatch",))
    a, b = primary.review, secondary.review
    aspects = _aspect_metric(a.required_aspects, b.required_aspects)
    supported = _set_metric(
        _aspect_semantics(a, a.supported_aspects),
        _aspect_semantics(b, b.supported_aspects),
    )
    missing = _set_metric(
        _aspect_semantics(a, a.missing_aspects),
        _aspect_semantics(b, b.missing_aspects),
    )
    groups = _set_metric(_group_semantics(a), _group_semantics(b))
    spans, times = _segment_iou(a.required_spans, b.required_spans), _time_iou(a.required_spans, b.required_spans)
    optional_spans = _segment_iou(a.optional_context_spans, b.optional_context_spans)
    spans = spans.model_copy(
        update={
            "details": {
                **spans.details,
                "optional_context_state": optional_spans.state,
                "optional_context_iou": optional_spans.score,
            }
        }
    )
    source_a = {(x.video_id, x.source_artifact_id, x.source_version, x.timeline_run_id) for x in a.required_spans}
    source_b = {(x.video_id, x.source_artifact_id, x.source_version, x.timeline_run_id) for x in b.required_spans}
    triggers: list[str] = []
    if a.status != b.status: triggers.append("label_disagreement")
    if aspects.state != "agree": triggers.append("required_aspect_unresolved")
    if supported.state != "agree": triggers.append("supported_aspect_disagreement")
    if missing.state != "agree": triggers.append("missing_aspect_disagreement")
    if groups.state != "agree": triggers.append("evidence_group_disagreement")
    if a.status == "partial" or b.status == "partial": triggers.append("partial")
    if max(len(a.required_spans), len(b.required_spans)) > 1: triggers.append("multiple_required_spans")
    if max(len(a.acceptable_evidence_groups), len(b.acceptable_evidence_groups)) > 1: triggers.append("multiple_evidence_groups")
    if a.confidence == "low" or b.confidence == "low": triggers.append("low_confidence")
    if a.conflict_notes or b.conflict_notes: triggers.append("conflict_evidence")
    if times.state != "agree": triggers.append("evidence_region_difference")
    if optional_spans.state != "agree": triggers.append("optional_context_difference")
    if cross_language: triggers.append("cross_language")
    if asr_error: triggers.append("asr_error")
    combined_reasons = set(a.reason_codes) | set(b.reason_codes)
    for code in ("suspected_external_knowledge", "incomplete_transcript_review", "source_unclear", "boundary_dispute"):
        if code in combined_reasons: triggers.append(code)
    if not a.reviewed_full_transcript or not b.reviewed_full_transcript:
        triggers.append("incomplete_transcript_review")
    if (a.status, b.status) in {("sufficient", "insufficient"), ("insufficient", "sufficient"),
                               ("sufficient", "unverifiable"), ("unverifiable", "sufficient")}:
        triggers.append("extreme_label_disagreement")
    source_agreement = source_a == source_b
    if not source_agreement: triggers.append("source_disagreement")
    boundary_notes_equal = normalize_text(a.boundary_notes) == normalize_text(b.boundary_notes)
    if not boundary_notes_equal:
        triggers.append("boundary_notes_difference")
    reason_metric = _set_metric(set(a.reason_codes), set(b.reason_codes))
    if reason_metric.state != "agree":
        triggers.append("reason_code_disagreement")
    reason_metric = reason_metric.model_copy(
        update={"details": {**reason_metric.details, "boundary_notes_equal": boundary_notes_equal}}
    )
    core = (
        a.status == b.status
        and aspects.state == supported.state == missing.state == groups.state == "agree"
        and spans.state == times.state == optional_spans.state == "agree"
        and reason_metric.state == "agree"
        and boundary_notes_equal
        and source_agreement
    )
    spot = selected_for_spot_check(primary.case_id) if core and not triggers else False
    status = "mandatory_human_review" if triggers or not core else ("passed_requires_spot_check" if spot else "passed")
    confidence_rank = {"low": 0, "medium": 1, "high": 2}
    return AnnotationAgreementV2(
        case_id=primary.case_id, case_input_sha256=primary.review_metadata.case_input_sha256, status=status,
        label_exact_agreement=a.status == b.status, required_aspect_agreement=aspects,
        supported_aspect_agreement=supported, missing_aspect_agreement=missing,
        evidence_group_agreement=groups, required_span_overlap=spans, time_region_overlap=times,
        source_agreement=source_agreement, reason_code_agreement=reason_metric,
        confidence_difference=abs(confidence_rank[a.confidence]-confidence_rank[b.confidence]),
        mandatory_triggers=tuple(dict.fromkeys(triggers)), human_adjudication_required=bool(triggers or not core),
        spot_check_status="selected" if spot else "not_selected",
    )


def _terminal(review: AnnotationReviewV2, status: str, triggers: tuple[str, ...]) -> AnnotationAgreementV2:
    na = AgreementMetric(state="not_applicable")
    return AnnotationAgreementV2(case_id=review.case_id, case_input_sha256=review.review_metadata.case_input_sha256,
        status=status, label_exact_agreement=False, required_aspect_agreement=na, supported_aspect_agreement=na,
        missing_aspect_agreement=na, evidence_group_agreement=na, required_span_overlap=na,
        time_region_overlap=na, source_agreement=False, reason_code_agreement=na, confidence_difference=0,
        mandatory_triggers=triggers, human_adjudication_required=True, spot_check_status="not_applicable")
