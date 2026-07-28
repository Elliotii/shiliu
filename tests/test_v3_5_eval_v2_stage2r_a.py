from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from shiliu.eval_v3_5.eval_v2.agreement import compare_reviews, selected_for_spot_check
from shiliu.eval_v3_5.eval_v2.contracts import (
    AnnotationReviewV2, MasterCaseV2, TranscriptSegment,
)
from shiliu.eval_v3_5.eval_v2.hashing import canonical_bytes, stable_sha256
from shiliu.eval_v3_5.eval_v2.isolation import ProtectedPathError, Stage2RAAccessGuard, assert_primary_workspace_isolated
from shiliu.eval_v3_5.eval_v2.leakage import LeakageRecord, assert_leakage_safe, validate_split
from shiliu.eval_v3_5.eval_v2.packets import build_packet, verify_packet_hash
from shiliu.eval_v3_5.eval_v2.projections import project_v3_5_fine_evidence, project_v3_5_sufficiency, project_v3_retrieval
from shiliu.eval_v3_5.eval_v2.providers import build_deepseek_secondary_request, redact_secrets
from shiliu.eval_v3_5.eval_v2.review_validation import reconstruct_span, validate_review, validate_with_one_repair


def segments():
    return tuple(TranscriptSegment(segment_id=f"seg_{i}", start_time=float(i-1), end_time=float(i), text=text,
        source_language="en", source_type="raw_subtitle", timeline_run_id="run_1",
        source_artifact_id="artifact_fixture", source_version="version_fixture")
        for i, text in enumerate(("alpha", "beta", "context"), 1))


def packet():
    return build_packet(case_id="V2C_FIXTURE01", query="alpha and beta?", query_language="en",
                        transcript=segments(), source_metadata={"video_id": "video_fixture", "synthetic": True})


def review(*, status="sufficient", aspect="alpha and beta", ids=("seg_1", "seg_2"), role="primary",
           hash_value=None, confidence="high", groups=1, valid="valid"):
    p = packet(); now = datetime(2026, 7, 22, tzinfo=timezone.utc)
    spans = [{"span_id": f"S{i}", "video_id": "video_fixture", "source_artifact_id": "artifact_fixture",
              "source_version": "version_fixture", "timeline_run_id": "run_1", "segment_ids": [seg],
              "start_time": float(int(seg[-1])-1), "end_time": float(int(seg[-1])), "source_language": "en",
              "source_type": "raw_subtitle", "span_role": "required", "required_aspect_ids": ["A1"]}
             for i, seg in enumerate(ids, 1)]
    evidence_groups = [{"group_id": f"G{i}", "required_aspect_ids": ["A1"],
                        "required_span_ids": [x["span_id"] for x in spans], "alternative_expression_notes": ""}
                       for i in range(1, groups+1)] if status in {"sufficient", "partial"} else []
    supported = ["A1"] if status in {"sufficient", "partial"} else []
    missing = ["A2"] if status == "partial" else ([] if status == "sufficient" else ["A1"])
    aspects = [{"aspect_id": "A1", "description": aspect}]
    if status == "partial": aspects.append({"aspect_id": "A2", "description": "missing condition"})
    return AnnotationReviewV2.model_validate({"case_id": p.case_id, "review_metadata": {
        "reviewer_provider": "local-mock", "reviewer_model": "mock", "reviewer_role": role,
        "prompt_version": f"v3.5-{role}-reviewer-prompt-v2", "packet_version": p.packet_version,
        "case_input_sha256": hash_value or p.case_input_sha256, "output_schema_version": "v3.5-annotation-review-v2",
        "started_at": now, "completed_at": now, "latency_ms": 0, "usage": {},
        "validation_status": valid, "repair_count": 0}, "review": {
        "status": status, "required_aspects": aspects, "supported_aspects": supported, "missing_aspects": missing,
        "acceptable_evidence_groups": evidence_groups, "required_spans": spans, "optional_context_spans": [],
        "reason_codes": [], "conflict_notes": "", "confidence": confidence, "boundary_notes": "",
        "reviewed_full_transcript": True, "transcript_first_segment_id": "seg_1",
        "transcript_last_segment_id": "seg_3"}})


def case(status="sufficient"):
    available = status != "unverifiable"
    aspects = [{"aspect_id": "A1", "description": "alpha"}, {"aspect_id": "A2", "description": "beta"}]
    supported = ["A1", "A2"] if status == "sufficient" else (["A1"] if status == "partial" else [])
    missing = [] if status == "sufficient" else (["A2"] if status == "partial" else ["A1", "A2"])
    spans = [{"span_id": "S1", "video_id": "video_fixture", "source_artifact_id": "artifact_fixture",
              "source_version": "version_fixture", "timeline_run_id": "run_1", "segment_ids": ["seg_1"],
              "start_time": 0, "end_time": 1, "source_language": "en", "source_type": "raw_subtitle",
              "span_role": "required", "required_aspect_ids": ["A1", "A2"] if status == "sufficient" else ["A1"]}] if status in {"sufficient", "partial"} else []
    groups = [{"group_id": "G1", "required_aspect_ids": ["A1", "A2"] if status == "sufficient" else ["A1"],
               "required_span_ids": ["S1"], "alternative_expression_notes": ""}] if status in {"sufficient", "partial"} else []
    return MasterCaseV2.model_validate({"case_identity": {"case_id": "V2C_FIXTURE01", "query": "q",
        "query_language": "en", "query_family": "fixture", "query_type": "semantic_question",
        "leakage_group": "LGV2_FIXTURE", "lineage": {"origin": "new_case"}, "case_status": "candidate"},
        "corpus_truth": {"target_video_ids": ["video_fixture"], "acceptable_video_ids": ["video_fixture"],
        "source_availability": [{"video_id": "video_fixture", "status": "available" if available else "missing"}],
        "source_types": ["raw_subtitle"] if available else [], "source_artifact_ids": ["artifact_fixture"] if available else [],
        "source_versions": ["version_fixture"] if available else [], "languages": ["en"],
        "timeline_runs": ["run_1"] if available else [], "source_limitations": []},
        "retrieval_gold": {"relevant_video_ids": ["video_fixture"], "acceptable_video_ids": ["video_fixture"],
        "expected_retrieval_state": "transcript_chunk_reachable" if available else "not_applicable"},
        "evidence_gold": {"required_aspects": aspects, "acceptable_evidence_groups": groups,
        "required_spans": spans, "optional_context_spans": []},
        "sufficiency_gold": {"status": status, "supported_aspects": supported, "missing_aspects": missing,
        "reason_codes": [], "confidence": "high"}})


def test_four_states_and_future_gold_forbidden():
    for state in ("sufficient", "partial", "insufficient", "unverifiable"):
        assert case(state).sufficiency_gold.status == state
    raw = case().model_dump(); raw["answer_gold"] = {}
    with pytest.raises(ValidationError): MasterCaseV2.model_validate(raw)
    raw = case().model_dump(); raw["sufficiency_gold"]["status"] = "partial"
    with pytest.raises(ValidationError): MasterCaseV2.model_validate(raw)


def test_packet_hash_full_transcript_reconstruction_and_validation():
    p = packet(); assert verify_packet_hash(p) and len(p.full_raw_transcript) == 3
    r = review(ids=("seg_1",)); result = validate_review(r.model_dump(), p)
    assert result.status == "valid"
    assert reconstruct_span(r.review.required_spans[0], p)["quote_text"] == "alpha"
    bad = r.model_dump(); bad["review"]["required_spans"][0]["segment_ids"] = ["invented"]
    assert "invalid_segment_id:S1" in validate_review(bad, p).errors
    cross = r.model_dump(); cross["review"]["required_spans"][0]["timeline_run_id"] = "run_2"
    assert "timeline_run_mismatch:S1" in validate_review(cross, p).errors


def test_one_repair_only_success_and_terminal_failure():
    good = review(ids=("seg_1",)).model_dump(); bad = {"wrong": True}
    repaired = validate_with_one_repair(bad, packet(), lambda *_: good)
    assert repaired.status == "valid" and repaired.repair_count == 1
    failed = validate_with_one_repair(bad, packet(), lambda *_: bad)
    assert failed.status == "invalid" and failed.repair_count == 1


def test_agreement_checks_aspects_regions_hash_and_mandatory_triggers():
    a = review(ids=("seg_1",), role="primary")
    b = review(ids=("seg_1",), role="secondary")
    assert compare_reviews(a, b).status in {"passed", "passed_requires_spot_check"}
    assert compare_reviews(a, review(ids=("seg_1",), aspect="unrelated gamma", role="secondary")).status == "mandatory_human_review"
    assert compare_reviews(a, review(ids=("seg_3",), role="secondary")).status == "mandatory_human_review"
    assert compare_reviews(a, review(ids=("seg_1",), role="secondary", hash_value="0"*64)).status == "input_mismatch"
    assert compare_reviews(review(status="partial", ids=("seg_1",)), review(status="partial", ids=("seg_1",), role="secondary")).status == "mandatory_human_review"


def test_spot_check_is_deterministic_and_rate_bounded():
    first = [selected_for_spot_check(f"V2C_{i:08d}") for i in range(1000)]
    assert first == [selected_for_spot_check(f"V2C_{i:08d}") for i in range(1000)]
    assert 150 <= sum(first) <= 250
    with pytest.raises(ValueError): selected_for_spot_check("x", rate=.5)


def test_leakage_conflict_and_safe_split():
    a = LeakageRecord(case_id="a", split="development", leakage_group="g", query_family="f", target_video_ids=("v",))
    b = LeakageRecord(case_id="b", split="held_out", leakage_group="g", query_family="f", target_video_ids=("v",))
    assert validate_split((a, b))
    with pytest.raises(ValueError): assert_leakage_safe((a, b))
    assert not validate_split((a, b.model_copy(update={"split": "development"})))


def test_hash_redaction_provider_builder_and_projections_are_deterministic():
    value = {"x": 1, "started_at": "later", "request_id": "random"}
    assert stable_sha256(value) == stable_sha256({"x": 1})
    assert canonical_bytes(value) == canonical_bytes(value)
    assert "secret" not in redact_secrets("Authorization: Bearer-secret")
    request = build_deepseek_secondary_request(packet(), "blind prompt")
    assert request.provider_usage == "annotation_secondary_review" and "Authorization" not in request.body
    c = case(); assert project_v3_retrieval(c)["constraint"] == "diagnostic_only_no_v3_retuning_authority"
    assert "required_spans" in project_v3_5_fine_evidence(c) and project_v3_5_sufficiency(c)["status"] == "sufficient"


def test_stage2r_a_guard_rejects_protected_paths_without_opening(tmp_path):
    guard = Stage2RAAccessGuard(Path.cwd())
    synthetic_protected_path = tmp_path / "heldout_gold.synthetic.must_not_open.jsonl"
    with pytest.raises(ProtectedPathError): guard.read_text(synthetic_protected_path)
    with pytest.raises(ProtectedPathError):
        guard.read_text(Path("research/v3_eval/eval_queries.candidate.jsonl"))
    with pytest.raises(ProtectedPathError):
        guard.read_text(Path("research/v3_eval/eval_queries.locked.jsonl"))
    assert guard.audit()["forbidden_access_attempts"] == 3
    assert_primary_workspace_isolated(["packets/V2C_FIXTURE01.json"])
    with pytest.raises(ProtectedPathError): assert_primary_workspace_isolated(["agreements/result.json"])


def test_prompts_are_independent_and_forbid_judge_prediction_leakage():
    root = Path("research/v3_5/eval_v2/stage2r_a/prompts")
    primary = (root / "primary_reviewer.v2.md").read_text()
    secondary = (root / "secondary_reviewer.v2.md").read_text()
    assert "eval-v2-gold-annotation-primary" in primary and "eval-v2-gold-annotation-secondary" in secondary
    assert "你未获得其他 Reviewer 的结论" in secondary and "检查一审是否正确" not in secondary
    assert "system predictions" in primary and "Stage 4B" not in primary
