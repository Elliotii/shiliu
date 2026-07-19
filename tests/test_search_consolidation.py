from __future__ import annotations

from shiliu.retrieval.consolidation import SearchResultConsolidator
from shiliu.retrieval.orchestrator import RawSearchHit


def hit(
    unit_id: str,
    *,
    video_id: int = 1,
    rank: int = 1,
    score: float = 1.0,
    unit_type: str = "transcript_chunk",
    start: float | None = 0.0,
    end: float | None = 10.0,
) -> RawSearchHit:
    return RawSearchHit(
        unit_id=unit_id, video_id=video_id, unit_type=unit_type, rank=rank,
        score=score, retrieval_method="lexical", lexical_rank=rank,
        lexical_score=score, dense_rank=None, dense_score=None, rrf_score=None,
        title=f"Video {video_id}", uploader="UP", subtitle_source="ai",
        start_time=start if unit_type == "transcript_chunk" else None,
        end_time=end if unit_type == "transcript_chunk" else None,
        excerpt="excerpt",
    )


def test_same_video_grouping_video_and_chunks_and_different_videos() -> None:
    value = SearchResultConsolidator().consolidate(
        (hit("video", unit_type="video"), hit("chunk", rank=2), hit("other", video_id=2, rank=3))
    )
    assert len(value.groups) == 2
    first = value.groups[0]
    assert first.video_id == 1 and len(first.hits) == 2 and len(first.windows) == 1
    assert first.best_hit.unit_id == "video"


def test_duplicate_unit_keeps_best_rank_and_reports_count() -> None:
    value = SearchResultConsolidator().consolidate(
        (hit("same", rank=5, score=9), hit("same", rank=2, score=1))
    )
    assert value.duplicate_raw_hit_count == 1
    assert value.groups[0].best_hit.rank == 2


def test_group_rank_uses_best_hit_not_score_sum_or_chunk_count() -> None:
    many = tuple(hit(f"many-{index}", video_id=1, rank=index + 2, score=100) for index in range(5))
    value = SearchResultConsolidator().consolidate(
        (hit("winner", video_id=2, rank=1, score=0.1), *many)
    )
    assert [group.video_id for group in value.groups] == [2, 1]
    assert value.groups[1].best_hit.score == 100


def test_group_stable_tie_break_uses_score_then_video_id() -> None:
    value = SearchResultConsolidator().consolidate(
        (hit("b", video_id=2, rank=1, score=1), hit("a", video_id=1, rank=1, score=2))
    )
    assert [group.video_id for group in value.groups] == [1, 2]


def test_scope_video_shape_has_no_windows() -> None:
    value = SearchResultConsolidator().consolidate((hit("video", unit_type="video"),))
    assert value.groups[0].windows == []


def test_overlap_zero_gap_and_twenty_seconds_merge_chain() -> None:
    value = SearchResultConsolidator().consolidate(
        (
            hit("a", rank=3, start=0, end=10),
            hit("b", rank=2, start=10, end=20),
            hit("c", rank=1, start=40, end=50),
        )
    )
    window = value.groups[0].windows[0]
    assert (window.window_start, window.window_end) == (0, 50)
    assert window.component_chunk_ids == ("c", "b", "a")
    assert window.best_hit.unit_id == "c"


def test_gap_over_twenty_and_far_chunks_form_separate_windows() -> None:
    value = SearchResultConsolidator().consolidate(
        (hit("a", rank=3, start=0, end=10), hit("b", rank=1, start=30.001, end=40),
         hit("c", rank=2, start=200, end=210))
    )
    windows = value.groups[0].windows
    assert len(windows) == 3
    assert [window.best_hit.unit_id for window in windows] == ["b", "c", "a"]


def test_window_rank_is_component_best_rank_not_time_order() -> None:
    value = SearchResultConsolidator().consolidate(
        (hit("early", rank=9, start=0, end=5), hit("late", rank=1, start=100, end=105))
    )
    assert [window.window_start for window in value.groups[0].windows] == [100, 0]


def test_missing_invalid_timestamp_is_unwindowed_but_matched() -> None:
    value = SearchResultConsolidator().consolidate(
        (hit("valid"), hit("missing", rank=2, start=None, end=None), hit("reverse", rank=3, start=5, end=4))
    )
    group = value.groups[0]
    assert len(group.hits) == 3 and len(group.windows) == 1
    assert group.unwindowed_chunk_count == 2


def test_window_evidence_preserves_component_ranks_sources_and_methods() -> None:
    value = SearchResultConsolidator().consolidate(
        (hit("a", rank=2, start=0, end=10), hit("b", rank=1, start=5, end=20))
    )
    payload = value.groups[0].windows[0].as_dict()
    assert payload["component_raw_ranks"] == [1, 2]
    assert payload["subtitle_sources"] == ["ai"]
    assert payload["retrieval_methods"] == ["lexical"]
