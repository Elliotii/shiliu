from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest
from pydantic import ValidationError

from shiliu.eval_v3_5.models import (
    CompletedReviewDecision,
    GoldEvidenceGroup,
    MasterCaseCandidate,
    ReviewDecisionTemplate,
)
from shiliu.eval_v3_5.packets import validate_review_assets


ROOT = Path("research/v3_5")
SNAPSHOT_DB = Path(
    "/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db"
)


def _records(name: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in (ROOT / name).read_text().splitlines()]


def _cases() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    return _records("master_case_candidates.jsonl"), _records("master_case_reserves.jsonl")


def test_case_schema_accepts_video_and_corpus_and_forbids_gold_or_split() -> None:
    primary, _ = _cases()
    video = next(value for value in primary if value["case_scope"] == "query_video" and value["source_state"] == "readable_raw")
    corpus = next(value for value in primary if value["case_scope"] == "query_corpus")
    assert MasterCaseCandidate.model_validate(video).decision_status == "unreviewed"
    assert MasterCaseCandidate.model_validate(corpus).target_video_id is None

    for key, value in (
        ("source_version", "not-a-hash"),
        ("sampling_stratum", "sufficient"),
        ("gold_segment_ids", []),
        ("gold_evidence_groups", []),
        ("sufficiency_label", "sufficient"),
        ("split", "held_out"),
    ):
        invalid = {**video, key: value}
        with pytest.raises(ValidationError):
            MasterCaseCandidate.model_validate(invalid)

    missing = dict(video)
    missing.pop("source_artifact_id")
    with pytest.raises(ValidationError):
        MasterCaseCandidate.model_validate(missing)


def test_unreviewed_template_rejects_prefilled_gold_and_label() -> None:
    template = ReviewDecisionTemplate(case_id="CASE_X")
    assert template.decision_status == template.sufficiency_label == "unreviewed"
    with pytest.raises(ValidationError):
        ReviewDecisionTemplate(case_id="CASE_X", sufficiency_label="sufficient")
    with pytest.raises(ValidationError):
        ReviewDecisionTemplate(
            case_id="CASE_X",
            required_aspects=[{"aspect_id": "a", "description": "x"}],
        )
    templates = _records("review_decisions.template.jsonl")
    candidates = sum(_cases(), [])
    assert len(templates) == 26 and len(candidates) == 28
    by_case = {value["case_id"]: value for value in candidates}
    for value in templates:
        assert value["sufficiency_label"] == "unreviewed"
        assert by_case[value["case_id"]]["sampling_stratum"] != value["sufficiency_label"]
        assert value["gold_evidence_groups"] == []


def test_completed_schema_expresses_or_groups_and_and_spans_and_four_states() -> None:
    span = {
        "span_id": "span_a1", "segment_ids": ["segment_1"],
        "start_time": 1.0, "end_time": 2.0, "timeline_run_id": "run_1",
    }
    groups = [
        {"group_id": "group_a", "required_spans": [span, {**span, "span_id": "span_a2"}],
         "supported_aspects": ["aspect_a", "aspect_b"]},
        {"group_id": "group_b", "required_spans": [{**span, "span_id": "span_b1"}],
         "supported_aspects": ["aspect_a", "aspect_b"]},
    ]
    base = {
        "case_id": "CASE_X", "review_version": "future", "reviewer": "human",
        "reviewed_at": "2026-01-01T00:00:00Z", "decision_status": "completed",
        "required_aspects": [
            {"aspect_id": "aspect_a", "description": "A"},
            {"aspect_id": "aspect_b", "description": "B"},
        ],
        "conflict_notes": "", "primary_reason_codes": [], "support_notes": "",
        "review_confidence": "high", "needs_second_review": False,
    }
    sufficient = CompletedReviewDecision.model_validate({
        **base, "gold_evidence_groups": groups, "sufficiency_label": "sufficient",
        "supported_aspects": ["aspect_a", "aspect_b"], "missing_aspects": [],
    })
    assert len(sufficient.gold_evidence_groups) == 2
    assert len(sufficient.gold_evidence_groups[0].required_spans) == 2
    partial = CompletedReviewDecision.model_validate({
        **base, "gold_evidence_groups": [groups[0]], "sufficiency_label": "partial",
        "supported_aspects": ["aspect_a"], "missing_aspects": ["aspect_b"],
    })
    assert partial.sufficiency_label == "partial"
    for label in ("insufficient", "unverifiable"):
        decision = CompletedReviewDecision.model_validate({
            **base, "gold_evidence_groups": [], "sufficiency_label": label,
            "supported_aspects": [], "missing_aspects": ["aspect_a", "aspect_b"],
        })
        assert decision.sufficiency_label == label
    with pytest.raises(ValidationError):
        GoldEvidenceGroup.model_validate({
            "group_id": "bad", "required_spans": [span, {**span, "timeline_run_id": "run_2"}],
            "supported_aspects": ["aspect_a"],
        })


def test_sampling_targets_use_real_candidates_without_assigning_split() -> None:
    primary, reserves = _cases()
    assert 18 <= len(primary) == 20 <= 24
    assert 4 <= len(reserves) == 8
    assert sum(value["source_type"] == "human" for value in primary) >= 2
    assert sum(value["source_type"] == "asr" for value in primary) >= 2
    assert sum(value["source_language"] == "en" for value in primary) >= 1
    assert sum(value["source_state"] in {"title_only", "subtitle_missing"} for value in primary) >= 2
    assert sum(value["sampling_stratum"] == "semantic_neighbor_negative" for value in primary) >= 2
    assert {value["query"] for value in primary if value["case_scope"] == "query_corpus"} == {
        "量子纠错表面码阈值如何计算？", "如何为 Kubernetes Pod 排查 CrashLoopBackOff？"
    }
    video_88 = next(value for value in primary if value["target_video_id"] == 88)
    assert video_88["split_constraint"] == "development_only"
    assert video_88["sampling_stratum"] == "multi_timeline_robustness"
    assert all("split" not in value for value in primary + reserves)


def test_real_packet_integrity_covers_ai_human_asr_english_multirun_and_no_body() -> None:
    summary = validate_review_assets()
    assert summary.packet_count == 28
    assert summary.query_video_count == 26 and summary.query_corpus_count == 2
    assert summary.total_transcript_segments == 8626
    assert summary.largest_packet == "CASE_012"
    primary, _ = _cases()
    cases = {value["case_id"]: value for value in primary}
    assert cases["CASE_001"]["source_type"] == "ai"
    assert cases["CASE_011"]["source_type"] == "human"
    assert cases["CASE_004"]["source_type"] == "asr"
    assert cases["CASE_006"]["source_language"] == "en"
    multi = (ROOT / "review_packets/CASE_012.md").read_text()
    assert multi.count("### Timeline Run `") == 2
    assert "<!-- SEGMENT_COUNT=1748 -->" in multi
    title_only = (ROOT / "review_packets/CASE_015.md").read_text()
    corpus = (ROOT / "review_packets/CASE_017.md").read_text()
    assert "## Full Raw Transcript" not in title_only
    assert "No authoritative Raw Transcript is available" in title_only
    assert "## Full Raw Transcript" not in corpus and "不伪造 Target Video" in corpus


def test_every_readable_packet_contains_first_last_segment_and_exact_version() -> None:
    primary, reserves = _cases()
    connection = sqlite3.connect(f"file:{SNAPSHOT_DB}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        for case in primary + reserves:
            if case["source_state"] != "readable_raw":
                continue
            raw_path = Path(connection.execute(
                "SELECT raw_subtitle_path FROM videos WHERE id=?", (case["target_video_id"],)
            ).fetchone()[0])
            raw = json.loads(raw_path.read_text())
            packet = (ROOT / "review_packets" / f"{case['case_id']}.md").read_text()
            assert '"original_ordinal":0' in packet
            assert f'"original_ordinal":{len(raw) - 1}' in packet
            assert f"<!-- SOURCE_VERSION={case['source_version']} -->" in packet
            assert "Navigation Aid Only — Not Annotation Boundary" in packet
            assert "Decision Status:\nunreviewed" in packet
    finally:
        connection.close()


def test_preliminary_leakage_detects_shared_query_video_and_interval_without_split() -> None:
    report = json.loads((ROOT / "preliminary_leakage_report.json").read_text())
    assert report["status"] == "preliminary_only_no_split_assigned"
    groups = report["groups"]
    assert any(
        item["key_type"] == "query_family_key"
        and {"CASE_001", "CASE_012", "RESERVE_001"} <= set(item["case_ids"])
        for item in groups
    )
    assert any(
        item["key_type"] == "video_key"
        and {"CASE_001", "RESERVE_001"} <= set(item["case_ids"])
        for item in groups
    )
    assert any(
        item["key_type"] == "evidence_seed_key"
        and set(item["case_ids"]) == {"CASE_001", "RESERVE_001"}
        for item in groups
    )
    assert report["required_relationship_check"]["future_leakage_group_candidate"] is True


def test_stage1_snapshot_eval_and_trace_integrity_remain_frozen() -> None:
    expected = {
        "src/shiliu/evidence/contracts.py": "8417574849f0f36450f455dfc9ba00b6457762d7acee739fc5c271f9569f23b7",
        "src/shiliu/evidence/source.py": "ba39ada4505b0b6eb65013ad0c70c4f3ee8c66acff1ad6d2919df5e5e5ec3754",
        "src/shiliu/evidence/mapping.py": "e30a4873eace5d5b8a91ca58536d2345a6bd5fa7cb0f343ad3d8b349cb5e7ff0",
        "research/v3_eval/eval_queries.locked.jsonl": "21382e8ba058cc6e51ea41c776ad216824363090888ee3a5569e36dc971c36ba",
        "research/v3_eval/eval_gold.locked.jsonl": "873b5fbf78ba2e8fc90dfb2fca96776e0e703a1c4fedd56dd20a49e43995b300",
    }
    from hashlib import sha256
    for path, digest in expected.items():
        assert sha256(Path(path).read_bytes()).hexdigest() == digest
    assert sha256(SNAPSHOT_DB.read_bytes()).hexdigest() == "61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1"
    connection = sqlite3.connect(f"file:{SNAPSHOT_DB}?mode=ro&immutable=1", uri=True)
    try:
        assert connection.execute("SELECT count(*) FROM retrieval_search_traces").fetchone()[0] == 82
        assert connection.execute("SELECT count(*) FROM retrieval_search_presentations").fetchone()[0] == 52
    finally:
        connection.close()
