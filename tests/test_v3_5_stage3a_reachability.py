from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest
from pydantic import ValidationError

from shiliu.evidence.contracts import SearchRawUnitCandidate
from shiliu.eval_v3_5.isolation import HeldoutAccessError, HeldoutAccessGuard
from shiliu.eval_v3_5.stage3a_reachability import (
    SingleReplayLedger,
    classify_track_a,
    json_payload_equal,
    reconstruct_frozen_request,
    validate_oracle_video_boundary,
)


ROOT = Path(__file__).resolve().parents[1]


def _record() -> dict[str, object]:
    return {
        "case_id": "CASE_002",
        "original_query": "MemoryOS",
        "target_video_id": 40,
        "search_request": {
            "query": "MemoryOS", "mode": "lexical", "scope": "all",
            "result_limit": 10, "max_windows_per_video": 2,
            "filters": {
                "source_db_id": None, "folder_id": None,
                "favorite_time_from": None, "favorite_time_to": None,
                "reading_state": None, "marked": None, "uploader": None,
                "archived": None, "ignored": False,
            },
        },
    }


def test_frozen_request_reconstruction_preserves_every_field() -> None:
    record = _record()
    assert reconstruct_frozen_request(record).model_dump(mode="json") == record["search_request"]
    changed = {**record, "original_query": "changed"}
    with pytest.raises(ValueError, match="Original Query"):
        reconstruct_frozen_request(changed)


def test_json_projection_preserves_video_chunks_empty_and_order() -> None:
    video = SearchRawUnitCandidate(
        unit_id="video:bilibili:BV:p1", video_id=1, unit_type="video",
        raw_rank=1, raw_score=1.0, retrieval_method="lexical",
        subtitle_source="video_composite", source_language="zh",
        start_time=None, end_time=None, source_artifact_id=None,
        source_identity_version=None, source_version=None,
        source_version_authority=None, source_version_verified=False,
        source_version_expected=None, source_version_actual=None,
        segment_ids=(), segment_ordinals=(), timeline_run_id=None,
        mapping_status="not_applicable", candidate_eligibility=False,
        reason_codes=(), source_chunk_policy_version=None, mapping_version=None,
        replay_implementation_version=None,
    )
    serialized = asdict(video)
    serialized["segment_ids"] = []
    serialized["segment_ordinals"] = []
    serialized["reason_codes"] = []
    assert asdict(video) != serialized
    assert json_payload_equal(asdict(video), serialized)
    ordered = [serialized, {**serialized, "unit_id": "chunk:2", "raw_rank": 2,
                            "unit_type": "transcript_chunk"}]
    assert [item["unit_type"] for item in ordered] == ["video", "transcript_chunk"]
    assert json_payload_equal([], [])


def test_single_replay_ledger_rejects_second_claim() -> None:
    ledger = SingleReplayLedger(("CASE_001",))
    ledger.claim("CASE_001")
    with pytest.raises(RuntimeError, match="already executed"):
        ledger.claim("CASE_001")
    ledger.assert_complete()


@pytest.mark.parametrize(
    "relative",
    [
        "research/v3_eval/eval_gold.locked.jsonl",
        "research/v3_eval/eval_gold_review.decisions.jsonl",
        "research/v3_5/gold/heldout_gold.10_cases.locked.jsonl",
        "research/v3_5/gold/master_gold.18_cases.locked.jsonl",
        "research/v3_5/gold/review_decisions.master.18_cases.adjudicated.jsonl",
        "research/v3_5/gold/gold_lock_manifest.json",
        "research/v3_5/gold/gold_lock_audit.json",
        "research/v3_5/gold/master_case_membership.locked.json",
        "research/v3_5/gold/development_heldout_split.locked.json",
        "research/v3_5/human_reviews/a.jsonl",
        "research/v3_5/review_packets/CASE_001.md",
    ],
)
def test_heldout_guard_rejects_paths_without_opening_them(relative: str) -> None:
    guard = HeldoutAccessGuard(ROOT)
    with pytest.raises(HeldoutAccessError):
        guard.validate_path(ROOT / relative)


@pytest.mark.parametrize(
    "relative",
    [
        "research/v3_5/gold/development_gold.8_cases.locked.jsonl",
        "research/v3_5/stage3a_inputs/development_execution_manifest.8_cases.locked.jsonl",
        "research/v3_5/gold/V3_5_EVAL_PROTOCOL.locked.md",
        "research/v3_5/gold/HELDOUT_ISOLATION_CONTRACT.md",
        "src/shiliu/evidence/source.py",
        "/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/artifacts/BV1oa6uBXE8J/subtitle-raw.json",
    ],
)
def test_heldout_guard_allows_development_source_and_raw_paths(relative: str) -> None:
    guard = HeldoutAccessGuard(ROOT)
    assert guard.validate_path(Path(relative) if relative.startswith("/") else ROOT / relative)


def test_track_a_failure_attribution_is_separated() -> None:
    assert classify_track_a(target_video_reachable=False, candidate_builder_coverage=None,
                            selector_success=None) == "upstream_retrieval_failure"
    assert classify_track_a(target_video_reachable=True, candidate_builder_coverage=False,
                            selector_success=None) == "candidate_generation_failure"
    assert classify_track_a(target_video_reachable=True, candidate_builder_coverage=True,
                            selector_success=False) == "selector_failure"
    assert classify_track_a(target_video_reachable=True, candidate_builder_coverage=True,
                            selector_success=True) is None


def test_locked_replay_audit_preserves_identity_and_snapshot_contract() -> None:
    import json

    replay = json.loads(
        (ROOT / "research/v3_5/stage3a/frozen_request_replay_manifest.json").read_text()
    )
    assert replay["per_case_execution_counts"] == {
        "CASE_001": 1, "CASE_002": 1, "CASE_003": 1, "CASE_005": 1,
    }
    assert replay["snapshot_unchanged"] is True
    assert replay["trace_persistence_disabled"] is True
    for case in replay["cases"]:
        actual, serialized = case["actual"], case["serialized"]
        assert actual["ordered_unit_identities"] == serialized["ordered_candidate_identities"]
        assert actual["ordered_video_identities"] == serialized["ordered_video_identities"]
        assert actual["raw_unit_count"] == serialized["candidate_count"]
        assert actual["product_video_count"] == serialized["video_candidate_count"]
        assert actual["index_identity"]["lexical_index_version"] == "v3-stage1-lexical-v1"


def test_track_b_accepts_oracle_target_and_forbids_gold_boundary_fields() -> None:
    record = _record()
    payload = {
        "case_id": "CASE_002", "original_query": "MemoryOS",
        "oracle_target_video_id": 40,
        "raw_transcript_path": "/snapshot/BV1oa6uBXE8J/subtitle-raw.json",
        "raw_transcript_sha256": "a" * 64,
    }
    assert validate_oracle_video_boundary(payload, manifest_record=record).oracle_target_video_id == 40
    for forbidden in ("gold_segment_ids", "gold_start", "gold_end", "gold_evidence_groups",
                      "supported_aspects", "missing_aspects", "sufficiency_label", "reason_codes"):
        with pytest.raises(ValidationError):
            validate_oracle_video_boundary({**payload, forbidden: []}, manifest_record=record)
    with pytest.raises(ValueError, match="Original Query"):
        validate_oracle_video_boundary({**payload, "original_query": "changed"}, manifest_record=record)
