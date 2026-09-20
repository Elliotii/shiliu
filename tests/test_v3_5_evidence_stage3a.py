from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from shiliu.evidence import EvidenceContractError, SourceArtifactReference, load_source_artifact
from shiliu.evidence.stage3a import (
    CandidateBuilderConfig,
    EvidenceBundle,
    EvidenceCandidateSet,
    SelectorConfig,
    build_within_video_candidates,
    interval_union_duration,
    resolve_from_search_candidates,
    select_deterministic_bundle,
    validate_bundle,
    validate_raw_span,
)
from shiliu.eval_v3_5.isolation import HeldoutAccessError, HeldoutAccessGuard
from shiliu.eval_v3_5.stage3a import (
    candidate_union_covers,
    deterministic_covering_subset,
    validate_oracle_video_boundary,
)


ROOT = Path(__file__).resolve().parents[1]


def artifact(tmp_path: Path, *, count: int = 18, reset_at: int | None = None):
    directory = tmp_path / "BVTEST"
    directory.mkdir()
    values = []
    for index in range(count):
        start = index * 4.0 if reset_at is None or index < reset_at else (index - reset_at) * 4.0
        values.append({"from": start, "to": start + 3.0, "content": f"segment {index} memory os 记忆管理"})
    (directory / "subtitle-raw.json").write_text(json.dumps(values), encoding="utf-8")
    return load_source_artifact(SourceArtifactReference(
        platform="bilibili", source_id="BVTEST", part=1, source_type="ai",
        source_language="zh", artifact_path=str(directory / "subtitle-raw.json"), source_lineage="ai",
    ))


def test_heldout_guard_rejects_every_stage3a_forbidden_family() -> None:
    guard = HeldoutAccessGuard(ROOT)
    for name in (
        "eval_gold.locked.jsonl", "eval_gold_review.decisions.jsonl", "heldout_gold.jsonl",
        "master_gold.jsonl", "review_decisions.adjudicated.jsonl", "gold_lock_manifest.json",
        "gold_lock_audit.json", "master_case_membership.json", "development_heldout_split.json",
        "reason_code_registry.json", "human_reviews/x", "review_packets/x",
    ):
        with pytest.raises(HeldoutAccessError):
            guard.validate_path(ROOT / "research" / name)


def test_heldout_guard_allows_authorized_inputs_and_raw(tmp_path: Path) -> None:
    guard = HeldoutAccessGuard(ROOT)
    for value in (
        ROOT / "research/v3_5/gold/development_gold.8_cases.locked.jsonl",
        ROOT / "research/v3_5/stage3a_inputs/development_execution_manifest.8_cases.locked.jsonl",
        ROOT / "research/v3_5/stage3a/V3_5_STAGE3A_REACHABILITY_AND_CONDITIONAL_EVAL_ADDENDUM.md",
        ROOT / "src/shiliu/evidence/source.py", tmp_path / "subtitle-raw.json",
    ):
        assert guard.validate_path(value) == value.resolve()


def test_within_video_is_bounded_run_local_and_deterministic(tmp_path: Path) -> None:
    raw = artifact(tmp_path, count=30, reset_at=15)
    config = CandidateBuilderConfig(within_video_max_candidates=8, within_video_max_total_characters=2000)
    first = build_within_video_candidates("MemoryOS", 7, raw.source_version, raw, config, query_id="Q")
    second = build_within_video_candidates("MemoryOS", 7, raw.source_version, raw, config, query_id="Q")
    assert [value.candidate_id for value in first.candidates] == [value.candidate_id for value in second.candidates]
    assert len(first.candidates) <= 8
    assert sum(value.character_count for value in first.candidates) <= 2000
    assert all(value.segment_count <= 6 and value.end_time - value.start_time <= 60 for value in first.candidates)
    assert all(len({raw_segment.timeline_run_id for raw_segment in raw.segments if raw_segment.segment_id in value.segment_ids}) == 1 for value in first.candidates)
    assert all(value.segment_count < len(raw.segments) for value in first.candidates)


def test_source_version_mismatch_and_cross_run_are_typed(tmp_path: Path) -> None:
    raw = artifact(tmp_path, count=8, reset_at=4)
    with pytest.raises(EvidenceContractError, match="versions differ") as version:
        build_within_video_candidates("query", 1, "wrong", raw)
    assert version.value.code == "source_version_mismatch"
    with pytest.raises(EvidenceContractError) as cross:
        validate_raw_span(raw, raw.segments[3:5])
    assert cross.value.code == "timeline_run_mismatch"


def test_chunk_path_exact_mapping_and_provenance(tmp_path: Path) -> None:
    raw = artifact(tmp_path)
    mapped = raw.segments[3:11]
    search = {
        "raw_unit_candidates": [{
            "video_id": 7, "unit_type": "transcript_chunk", "candidate_eligibility": True,
            "source_version": raw.source_version, "source_artifact_id": raw.source_artifact_id,
            "segment_ids": [value.segment_id for value in mapped], "unit_id": "chunk:one", "raw_rank": 1,
        }],
        "video_candidates": [{"video_id": 7, "video_level_hit_present": True, "product_rank": 1, "best_unit_id": "chunk:one"}],
    }
    result = resolve_from_search_candidates("MemoryOS", search, lambda _: raw, query_id="Q")
    assert result.candidates
    assert all("chunk_mapped" in value.candidate_methods for value in result.candidates)
    assert all(value.parent_chunk_ids == ("chunk:one",) for value in result.candidates)


def test_video_path_and_upstream_miss(tmp_path: Path) -> None:
    raw = artifact(tmp_path)
    video_search = {"raw_unit_candidates": [], "video_candidates": [{
        "video_id": 7, "video_level_hit_present": True, "product_rank": 1, "best_unit_id": "video:7",
    }]}
    result = resolve_from_search_candidates("MemoryOS", video_search, lambda _: raw, query_id="Q")
    assert result.candidates and all("video_level_within_video" in value.candidate_methods for value in result.candidates)
    miss = resolve_from_search_candidates("MemoryOS", {"raw_unit_candidates": [], "video_candidates": []}, lambda _: raw)
    assert miss.candidates == ()
    assert miss.failure_category == "upstream_retrieval_failure"
    assert miss.validation_errors == ("upstream_retrieval_failure",)


def test_oracle_boundary_rejects_gold_fields() -> None:
    record = {"case_id": "C", "original_query": "Q", "target_video_id": 7}
    valid = {"case_id": "C", "original_query": "Q", "oracle_target_video_id": 7}
    validate_oracle_video_boundary(valid, manifest_record=record)
    with pytest.raises(EvidenceContractError) as error:
        validate_oracle_video_boundary({**valid, "gold_segment_ids": []}, manifest_record=record)
    assert error.value.code == "execution_manifest_mismatch"


def test_exact_identity_bundle_identity_and_invalid_reference(tmp_path: Path) -> None:
    raw = artifact(tmp_path)
    values = build_within_video_candidates("MemoryOS", 7, raw.source_version, raw, query_id="Q")
    first = select_deterministic_bundle("MemoryOS", values, SelectorConfig(max_candidates_per_bundle=4))
    second = select_deterministic_bundle("MemoryOS", values, SelectorConfig(max_candidates_per_bundle=4))
    assert first is not None and second is not None and first.bundle_id == second.bundle_id
    validate_bundle(first, values)
    invalid = replace(first, candidate_ids=("candidate_missing",))
    with pytest.raises(EvidenceContractError) as error:
        validate_bundle(invalid, values)
    assert error.value.code == "invalid_bundle_reference"


def test_union_coverage_and_deterministic_subset_tiebreak(tmp_path: Path) -> None:
    raw = artifact(tmp_path, count=12)
    values = build_within_video_candidates("MemoryOS", 7, raw.source_version, raw, CandidateBuilderConfig(within_video_max_candidates=12), query_id="Q")
    candidates = tuple(sorted(values.candidates, key=lambda value: value.start_time))
    required = list(candidates[0].segment_ids[-2:]) + list(candidates[1].segment_ids[-2:])
    span = {"segment_ids": required}
    assert candidate_union_covers(span, candidates[:2])
    assert not candidate_union_covers(span, candidates[:1])
    subset = deterministic_covering_subset(span, candidates)
    assert subset
    assert candidate_union_covers(span, subset)


def test_interval_union_is_not_envelope() -> None:
    assert interval_union_duration([(0, 10), (5, 15), (30, 35)]) == 20
    assert interval_union_duration([]) == 0
