from __future__ import annotations

from dataclasses import replace
import json

from shiliu.evidence.stage3a import (
    ADAPTIVE_BOUNDED_COVERAGE_SWAP_VERSION,
    CandidateBuilderConfig,
    EvidenceCandidate,
    adaptive_bounded_coverage_swap,
)


def candidate(
    index: int, segment_ids: tuple[str, ...], *,
    supported: bool = True, characters: int = 10,
) -> EvidenceCandidate:
    return EvidenceCandidate(
        candidate_id=f"candidate_{index:03d}",
        query_id="PUBLIC_QUERY",
        video_id=7,
        source_artifact_id="source_artifact",
        source_version="a" * 64,
        timeline_run_id="timeline_run",
        segment_ids=segment_ids,
        original_ordinals=tuple(range(index * 10, index * 10 + len(segment_ids))),
        start_time=float(index * 10),
        end_time=float(index * 10 + len(segment_ids)),
        source_text=f"candidate text {index}",
        source_language="zh",
        source_type="ai",
        parent_chunk_ids=("chunk",),
        search_candidate_ids=("search_candidate",),
        candidate_methods=("boundary_preserving", "chunk_mapped", "query_anchor"),
        segment_count=len(segment_ids),
        character_count=characters,
        lexical_token_count=3,
        overlap_group_id=f"overlap_{index}",
        related_candidate_ids=(),
        overlap_relation="none",
        trace_id="trace",
        normalization_status="valid",
        validation_errors=(),
        parent_rank=1,
        score_breakdown={
            "query_coverage_score": 1.0 if supported else 0.0,
            "exact_phrase_score": 0.0,
            "ngram_score": 0.0,
            "token_overlap_score": 0.0,
            "entity_overlap_score": 0.0,
            "asr_acronym_anchor_score": 0.0,
            "final_score": float(100 - index),
        },
    )


def config(**changes) -> CandidateBuilderConfig:
    values = {
        "within_video_max_candidates": 32,
        "within_video_max_total_characters": 6000,
        "within_video_max_total_union_duration_seconds": 600.0,
        "adaptive_coverage_swap_enabled": True,
        "adaptive_coverage_swap_max_swaps": 4,
    }
    values.update(changes)
    return CandidateBuilderConfig(**values)


def original_with_duplicate_pairs(pair_count: int = 1) -> tuple[EvidenceCandidate, ...]:
    values = []
    next_segment = 0
    for pair in range(pair_count):
        shared = tuple(f"segment_pair_{pair}_{offset}" for offset in range(6))
        values.extend((candidate(pair * 2, shared), candidate(pair * 2 + 1, shared)))
        next_segment = pair_count * 2
    for index in range(next_segment, 32):
        values.append(candidate(
            index, tuple(f"segment_{index}_{offset}" for offset in range(6)),
        ))
    return tuple(values)


def test_no_eligible_outside_candidate_preserves_original_top_32() -> None:
    original = original_with_duplicate_pairs()
    outside = [candidate(100, tuple(f"outside_{index}" for index in range(6)), supported=False)]
    final, trace = adaptive_bounded_coverage_swap(original, outside, config())
    assert [value.candidate_id for value in final] == [
        value.candidate_id for value in original
    ]
    assert trace["swap_count"] == 0
    assert trace["no_swap_reason"] == "no_eligible_outside_candidate"
    assert trace["final_candidate_ids"] == trace["original_top_32"]


def test_query_unsupported_new_region_is_rejected() -> None:
    original = original_with_duplicate_pairs()
    unsupported = candidate(100, tuple(f"new_{index}" for index in range(6)), supported=False)
    _, trace = adaptive_bounded_coverage_swap(original, [unsupported], config())
    assert trace["outside_eligible_candidate_ids"] == []
    assert trace["outside_rejection_reasons"] == [{
        "candidate_id": unsupported.candidate_id,
        "reasons": ["query_support_guard_failed"],
    }]


def test_supported_strict_new_coverage_replaces_redundant_non_tail_candidate() -> None:
    original = original_with_duplicate_pairs()
    addition = candidate(100, tuple(f"new_{index}" for index in range(6)))
    final, trace = adaptive_bounded_coverage_swap(original, [addition], config())
    removed = trace["swap_iterations"][0]["removed_candidate_id"]
    assert trace["design"] == ADAPTIVE_BOUNDED_COVERAGE_SWAP_VERSION
    assert trace["swap_count"] == 1
    assert addition.candidate_id in {value.candidate_id for value in final}
    assert removed in {"candidate_000", "candidate_001"}
    assert removed not in {f"candidate_{index:03d}" for index in range(28, 32)}
    assert trace["swap_iterations"][0]["coverage_after"] > trace["swap_iterations"][0]["coverage_before"]


def test_victim_ranking_prefers_high_overlap_low_exclusive_coverage() -> None:
    original = original_with_duplicate_pairs()
    addition = candidate(100, tuple(f"new_{index}" for index in range(6)))
    _, trace = adaptive_bounded_coverage_swap(original, [addition], config())
    first = trace["victim_candidates_ranked"][0]
    assert first["candidate_id"] in {"candidate_000", "candidate_001"}
    assert first["redundancy"] == 1.0
    assert first["exclusive_segment_count"] == 0


def test_swap_count_is_bounded_zero_to_four_and_not_forced() -> None:
    original = original_with_duplicate_pairs(pair_count=4)
    outside = [
        candidate(100 + index, tuple(f"new_{index}_{offset}" for offset in range(6)))
        for index in range(6)
    ]
    final, trace = adaptive_bounded_coverage_swap(original, outside, config())
    assert len(final) == 32
    assert 0 <= trace["swap_count"] <= 4
    assert trace["swap_count"] == 4
    one_final, one_trace = adaptive_bounded_coverage_swap(
        original_with_duplicate_pairs(), outside[:1], config(),
    )
    assert len(one_final) == 32
    assert one_trace["swap_count"] == 1


def test_each_swap_preserves_count_and_immutable_budgets() -> None:
    original = original_with_duplicate_pairs(pair_count=2)
    outside = [
        candidate(100 + index, tuple(f"new_{index}_{offset}" for offset in range(6)))
        for index in range(2)
    ]
    final, trace = adaptive_bounded_coverage_swap(original, outside, config())
    assert all(value["candidate_count_after_swap"] == 32 for value in trace["swap_iterations"])
    assert len(final) == 32
    assert sum(value.character_count for value in final) <= 6000
    assert all(value.segment_count <= 6 for value in final)
    assert all(value.end_time - value.start_time <= 60 for value in final)


def test_budget_violation_prevents_swap() -> None:
    original = original_with_duplicate_pairs()
    expensive = candidate(
        100, tuple(f"new_{index}" for index in range(6)), characters=500,
    )
    constrained = config(within_video_max_total_characters=350)
    final, trace = adaptive_bounded_coverage_swap(original, [expensive], constrained)
    assert [value.candidate_id for value in final] == [
        value.candidate_id for value in original
    ]
    assert trace["swap_count"] == 0
    assert trace["no_swap_reason"] == "no_strict_budget_valid_set_improvement"


def test_identical_input_has_canonical_deterministic_output_and_trace() -> None:
    original = original_with_duplicate_pairs(pair_count=2)
    outside = [
        candidate(100 + index, tuple(f"new_{index}_{offset}" for offset in range(6)))
        for index in range(2)
    ]
    first, first_trace = adaptive_bounded_coverage_swap(original, outside, config())
    second, second_trace = adaptive_bounded_coverage_swap(original, outside, config())
    assert [value.candidate_id for value in first] == [value.candidate_id for value in second]
    assert json.dumps(first_trace, sort_keys=True) == json.dumps(second_trace, sort_keys=True)


def test_candidate_count_other_than_32_is_a_no_op() -> None:
    original = original_with_duplicate_pairs()[:8]
    outside = [candidate(100, tuple(f"new_{index}" for index in range(6)))]
    final, trace = adaptive_bounded_coverage_swap(
        original, outside, config(within_video_max_candidates=8),
    )
    assert final == original
    assert trace["swap_count"] == 0
    assert trace["no_swap_reason"] == "candidate_count_not_exactly_32"


def test_no_case_or_video_identity_affects_decision() -> None:
    original = original_with_duplicate_pairs()
    outside = [candidate(100, tuple(f"new_{index}" for index in range(6)))]
    first, first_trace = adaptive_bounded_coverage_swap(original, outside, config())
    changed_original = tuple(
        replace(value, query_id="OTHER_QUERY", video_id=999) for value in original
    )
    changed_outside = [
        replace(value, query_id="OTHER_QUERY", video_id=999) for value in outside
    ]
    second, second_trace = adaptive_bounded_coverage_swap(
        changed_original, changed_outside, config(),
    )
    assert [value.candidate_id for value in first] == [value.candidate_id for value in second]
    assert first_trace == second_trace
