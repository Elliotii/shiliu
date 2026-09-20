from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from shiliu.eval.pooling import build_candidate_pool


@dataclass
class Result:
    video_id: int
    bvid: str
    title: str
    uploader: str = "uploader"
    folder_names: tuple[str, ...] = ()
    matched_unit_count: int = 1
    windows: tuple[dict, ...] = ()


def _search(request):
    ids = {"lexical": (1, 2), "dense": (2, 3), "hybrid": (3, 1)}[request.mode]
    return SimpleNamespace(
        executed_mode=request.mode, fallback=False,
        timing=SimpleNamespace(total_ms=10.0), raw_hit_count=2,
        trace_id=f"trace-{request.mode}",
        results=tuple(Result(value, f"BV{value:010d}", f"title {value}") for value in ids),
    )


def test_pool_is_three_mode_union_with_ranks_and_no_review_truncation() -> None:
    query = {
        "query_id": "Q01", "query": "MCP", "scope": "all", "filters": {},
        "expected_query_type": "exact_entity",
    }
    rows, stats = build_candidate_pool([query], _search)
    assert [row["video_id"] for row in rows] == [1, 2, 3]
    assert rows[0]["lexical_rank"] == 1 and rows[0]["hybrid_rank"] == 2
    assert stats["request_count_by_mode"] == {"lexical": 1, "dense": 1, "hybrid": 1}
    assert query["actual_planned_mode"] == "lexical"


def test_explicit_fallback_is_rejected() -> None:
    def fallback(request):
        value = _search(request)
        value.fallback = request.mode == "dense"
        return value

    query = {"query_id": "Q01", "query": "MCP", "scope": "all", "filters": {}, "expected_query_type": "exact_entity"}
    try:
        build_candidate_pool([query], fallback)
    except ValueError as exc:
        assert "explicit dense" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("fallback accepted")
