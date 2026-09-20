from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import statistics
import time
from typing import Any, Callable

from shiliu.eval.snapshot import write_jsonl
from shiliu.retrieval.planner import SearchFilterRequest, SearchPlanner, SearchRequest
from shiliu.retrieval.product_search import ProductSearchRequest


MODES = ("lexical", "dense", "hybrid")


def build_candidate_pool(
    queries: list[dict[str, Any]],
    search: Callable[[ProductSearchRequest], Any],
    *,
    output_path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pooled: dict[tuple[str, int], dict[str, Any]] = {}
    observations: list[dict[str, Any]] = []
    planner = SearchPlanner()
    started = time.monotonic()
    for query in queries:
        auto_plan = planner.plan(
            SearchRequest(
                query=query["query"], mode="auto", scope=query["scope"],
                filters=SearchFilterRequest.model_validate(query.get("filters") or {}),
            )
        )
        query["actual_planner_query_type"] = auto_plan.query_type
        query["actual_planned_mode"] = auto_plan.planned_mode
        query["actual_routing_reason"] = auto_plan.routing_reason
        query["query_type_agreement_candidate"] = (
            auto_plan.query_type == query["expected_query_type"]
        )
        for mode in MODES:
            request = ProductSearchRequest(
                query=query["query"], mode=mode, scope=query["scope"],
                result_limit=20, max_windows_per_video=5,
                filters=SearchFilterRequest.model_validate(query.get("filters") or {}),
            )
            response = search(request)
            if response.executed_mode != mode or response.fallback:
                raise ValueError(
                    f"explicit {mode} changed execution for {query['query_id']}"
                )
            observations.append(
                {
                    "query_id": query["query_id"], "mode": mode,
                    "latency_ms": response.timing.total_ms,
                    "result_count": len(response.results),
                    "raw_hit_count": response.raw_hit_count,
                    "trace_id": response.trace_id,
                }
            )
            for rank, result in enumerate(response.results, 1):
                key = (query["query_id"], int(result.video_id))
                row = pooled.setdefault(
                    key,
                    {
                        "query_id": query["query_id"],
                        "video_id": int(result.video_id),
                        "bvid": result.bvid,
                        "title": result.title,
                        "uploader": result.uploader,
                        "folder_names": list(result.folder_names),
                        "lexical_rank": None,
                        "dense_rank": None,
                        "hybrid_rank": None,
                        "best_rank": None,
                        "appeared_in_modes": [],
                        "matched_unit_count": 0,
                        "window_count": 0,
                        "top_evidence": [],
                        "candidate_label": "unknown",
                        "candidate_rationale": "",
                    },
                )
                row[f"{mode}_rank"] = rank
                row["appeared_in_modes"].append(mode)
                row["matched_unit_count"] = max(
                    int(row["matched_unit_count"]), int(result.matched_unit_count)
                )
                row["window_count"] = max(int(row["window_count"]), len(result.windows))
                _merge_evidence(row["top_evidence"], result.windows)
    rows = sorted(
        pooled.values(), key=lambda row: (row["query_id"], _best_rank(row), row["video_id"])
    )
    for row in rows:
        row["best_rank"] = _best_rank(row)
        row["appeared_in_modes"] = sorted(row["appeared_in_modes"], key=MODES.index)
    if output_path is not None:
        write_jsonl(output_path, rows)
    mode_latencies: dict[str, list[float]] = defaultdict(list)
    for item in observations:
        mode_latencies[item["mode"]].append(float(item["latency_ms"]))
    stats = {
        "duration_seconds": round(time.monotonic() - started, 3),
        "request_count_by_mode": {mode: len(mode_latencies[mode]) for mode in MODES},
        "latency_ms_by_mode": {
            mode: {"p50": round(_percentile(values, 50), 3), "p95": round(_percentile(values, 95), 3)}
            for mode, values in mode_latencies.items()
        },
        "pool_size": len(rows),
        "candidate_count_by_query": {
            query["query_id"]: sum(row["query_id"] == query["query_id"] for row in rows)
            for query in queries
        },
        "observations": observations,
    }
    return rows, stats


def _merge_evidence(target: list[dict[str, Any]], windows: Any) -> None:
    for window in windows:
        if len(target) >= 2:
            return
        value = {
            "start": window.get("window_start"),
            "end": window.get("window_end"),
            "jump_time": window.get("jump_time"),
            "jump_source": window.get("jump_source"),
            "subtitle_sources": window.get("subtitle_sources", []),
            "evidence": str(window.get("excerpt") or "")[:300],
            "best_chunk_id": window.get("best_chunk_id"),
        }
        signature = (value["start"], value["end"], value["evidence"])
        if not any((item["start"], item["end"], item["evidence"]) == signature for item in target):
            target.append(value)


def _best_rank(row: dict[str, Any]) -> int:
    ranks = [row[f"{mode}_rank"] for mode in MODES if row[f"{mode}_rank"] is not None]
    return min(ranks)


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile / 100
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    fraction = index - low
    return ordered[low] * (1 - fraction) + ordered[high] * fraction
