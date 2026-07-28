from __future__ import annotations

from dataclasses import replace

from shiliu.evidence.stage3a import (
    DETERMINISTIC_SELECTOR_V2_VERSION,
    EvidenceCandidate,
    EvidenceCandidateSet,
    select_greedy_marginal_bundle,
    validate_bundle,
)


def candidate(
    candidate_id: str,
    *,
    text: str,
    segments: tuple[str, ...],
    start: float,
    video_id: int = 1,
    builder_score: float = 1.0,
    normalization_status: str = "valid",
    validation_errors: tuple[str, ...] = (),
) -> EvidenceCandidate:
    return EvidenceCandidate(
        candidate_id=candidate_id,
        query_id="Q",
        video_id=video_id,
        source_artifact_id=f"artifact-{video_id}",
        source_version="v1",
        timeline_run_id=f"timeline-{video_id}",
        segment_ids=segments,
        original_ordinals=tuple(range(len(segments))),
        start_time=start,
        end_time=start + 20.0,
        source_text=text,
        source_language="zh",
        source_type="human",
        parent_chunk_ids=(),
        search_candidate_ids=(),
        candidate_methods=("synthetic",),
        segment_count=len(segments),
        character_count=len(text),
        lexical_token_count=len(text.split()),
        overlap_group_id="none",
        related_candidate_ids=(),
        overlap_relation="none",
        trace_id="trace",
        normalization_status=normalization_status,
        validation_errors=validation_errors,
        parent_rank=1,
        score_breakdown={"final_score": builder_score},
    )


def candidate_set(*values: EvidenceCandidate) -> EvidenceCandidateSet:
    return EvidenceCandidateSet(
        query_id="Q",
        original_query="alpha beta gamma",
        candidates=tuple(values),
        evaluation_track="synthetic",
        end_to_end_claim_eligible=False,
        trace={},
    )


def test_complementary_segment_beats_redundant_higher_local_score() -> None:
    anchor = candidate(
        "anchor", text="alpha beta", segments=("s1", "s2"), start=0,
        builder_score=10,
    )
    redundant = candidate(
        "redundant", text="alpha beta", segments=("s1", "s2"), start=2,
        builder_score=9,
    )
    complementary = candidate(
        "complementary", text="gamma implementation", segments=("s3", "s4"),
        start=120, builder_score=5,
    )
    fillers = [
        candidate(
            f"filler-{index}", text="alpha", segments=(f"s{index + 5}",),
            start=200 + index * 30, builder_score=1,
        )
        for index in range(5)
    ]
    bundle = select_greedy_marginal_bundle(
        "alpha beta gamma",
        candidate_set(anchor, redundant, complementary, *fillers),
    )
    assert bundle is not None
    assert "complementary" in bundle.candidate_ids
    assert "redundant" not in bundle.candidate_ids


def test_temporal_region_and_query_anchor_novelty_complete_bundle() -> None:
    values = [
        candidate("alpha", text="alpha overview", segments=("s1",), start=0),
        candidate("beta", text="beta mechanism", segments=("s2",), start=120),
        candidate("gamma", text="gamma validation", segments=("s3",), start=240),
        *[
            candidate(
                f"duplicate-{index}", text="alpha overview",
                segments=("s1",), start=float(index), builder_score=2,
            )
            for index in range(1, 6)
        ],
    ]
    bundle = select_greedy_marginal_bundle(
        "alpha beta gamma", candidate_set(*values),
    )
    assert bundle is not None
    selected = {
        value.candidate_id: value
        for value in values if value.candidate_id in bundle.candidate_ids
    }
    assert any("alpha" in value.source_text for value in selected.values())
    assert any("beta" in value.source_text for value in selected.values())
    assert any("gamma" in value.source_text for value in selected.values())
    assert bundle.score_breakdown["temporal_diversity"] >= 0.5


def test_deterministic_budget_identity_timeline_and_overlap_penalty() -> None:
    values = [
        candidate(
            f"candidate-{index}",
            text=f"alpha beta region {index}",
            segments=(f"s{index}", f"s{index + 1}"),
            start=index * 100.0,
        )
        for index in range(8)
    ]
    fixture = candidate_set(*values)
    first = select_greedy_marginal_bundle("alpha beta", fixture)
    second = select_greedy_marginal_bundle("alpha beta", fixture)
    assert first == second
    assert first is not None
    assert len(first.candidate_ids) == 6
    assert first.selection_method == DETERMINISTIC_SELECTOR_V2_VERSION
    validate_bundle(first, fixture)
    by_id = {value.candidate_id: value for value in values}
    for span in first.normalized_spans:
        source = by_id[str(span["candidate_id"])]
        assert span["timeline_run_id"] == source.timeline_run_id
        assert span["segment_ids"] == list(source.segment_ids)
        assert span["start_time"] == source.start_time
        assert span["end_time"] == source.end_time


def test_unrelated_low_score_and_wrong_video_do_not_win_for_novelty() -> None:
    strong = [
        candidate(
            f"strong-{index}", text=f"alpha beta {index}",
            segments=(f"a{index}",), start=index * 100.0, video_id=1,
            builder_score=10,
        )
        for index in range(6)
    ]
    unrelated = [
        candidate(
            f"unrelated-{index}", text=f"novel unrelated word {index}",
            segments=(f"u{index}",), start=index * 100.0, video_id=2,
            builder_score=0,
        )
        for index in range(6)
    ]
    bundle = select_greedy_marginal_bundle(
        "alpha beta", candidate_set(*strong, *unrelated),
    )
    assert bundle is not None
    assert bundle.video_id == 1
    assert all(value.startswith("strong-") for value in bundle.candidate_ids)


def test_invalid_identity_is_excluded_and_gold_fields_are_not_runtime_inputs() -> None:
    valid = [
        candidate(
            f"valid-{index}", text=f"alpha beta {index}",
            segments=(f"s{index}",), start=index * 30.0,
        )
        for index in range(6)
    ]
    invalid = candidate(
        "invalid", text="alpha beta gamma", segments=("bad",), start=0,
        builder_score=100, normalization_status="invalid",
        validation_errors=("source_version_mismatch",),
    )
    bundle = select_greedy_marginal_bundle(
        "alpha beta", candidate_set(invalid, *valid),
    )
    assert bundle is not None
    assert "invalid" not in bundle.candidate_ids
    assert "gold" not in select_greedy_marginal_bundle.__code__.co_varnames


def test_candidate_id_is_only_a_stable_tie_break_not_a_semantic_signal() -> None:
    values = [
        candidate(
            f"id-{index}", text=f"alpha topic {index}",
            segments=(f"s{index}",), start=index * 100.0,
            builder_score=float(10 - index),
        )
        for index in range(7)
    ]
    original = select_greedy_marginal_bundle(
        "alpha topic", candidate_set(*values),
    )
    renamed_values = [
        replace(value, candidate_id=f"renamed-{index}")
        for index, value in enumerate(values)
    ]
    renamed = select_greedy_marginal_bundle(
        "alpha topic", candidate_set(*renamed_values),
    )
    assert original is not None and renamed is not None
    original_texts = {
        value.source_text for value in values
        if value.candidate_id in original.candidate_ids
    }
    renamed_texts = {
        value.source_text for value in renamed_values
        if value.candidate_id in renamed.candidate_ids
    }
    assert original_texts == renamed_texts
