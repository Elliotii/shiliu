from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

from shiliu.retrieval.planner import SearchFilterRequest


CATEGORY_COUNTS = {
    "exact_entity": 5,
    "mixed_entity": 4,
    "semantic_topic_question": 5,
    "evidence_lookup": 4,
    "metadata_filter": 3,
    "temporal_filter": 3,
}
SCOPES = {"all", "video", "transcript_chunk"}


def load_queries(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def validate_query_candidates(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(rows) != 24:
        raise ValueError("candidate query set must contain exactly 24 rows")
    ids = [str(row.get("query_id", "")) for row in rows]
    if len(set(ids)) != len(ids) or ids != [f"Q{i:02d}" for i in range(1, 25)]:
        raise ValueError("query_id values must be unique Q01..Q24 in order")
    counts = Counter(str(row.get("category")) for row in rows)
    if dict(counts) != CATEGORY_COUNTS:
        raise ValueError(f"unexpected category distribution: {dict(counts)}")
    if sum(bool(row.get("held_out")) for row in rows) < 12:
        raise ValueError("at least 12 queries must be held out")
    if sum(bool(row.get("negative_control")) for row in rows) != 2:
        raise ValueError("exactly two queries must be negative controls")
    for row in rows:
        if row.get("status") != "candidate":
            raise ValueError(f"{row['query_id']} is not a candidate")
        if row.get("scope") not in SCOPES:
            raise ValueError(f"{row['query_id']} has invalid scope")
        SearchFilterRequest.model_validate(row.get("filters") or {})
        if not str(row.get("query", "")).strip():
            raise ValueError(f"{row['query_id']} has an empty query")
    return {
        "query_count": len(rows),
        "category_counts": dict(counts),
        "held_out_count": sum(bool(row["held_out"]) for row in rows),
        "negative_control_count": sum(bool(row["negative_control"]) for row in rows),
    }
