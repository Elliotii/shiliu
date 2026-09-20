from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any


def render_review_packet(
    queries: list[dict[str, Any]],
    pool: list[dict[str, Any]],
    gold_candidates: list[dict[str, Any]],
    output_path: Path,
    *,
    max_candidates: int = 15,
) -> None:
    by_query: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in pool:
        by_query[row["query_id"]].append(row)
    gold = {row["query_id"]: row for row in gold_candidates}
    lines = [
        "# Shiliu V3 Gold Candidate Review Packet",
        "",
        "> All labels and intervals below are non-authoritative candidate suggestions. Gold is not locked.",
        "",
        "The complete, untruncated pool is in `eval_pool_candidates.jsonl`.",
    ]
    for query in queries:
        query_id = query["query_id"]
        candidates = sorted(
            by_query.get(query_id, []),
            key=lambda row: (
                row["best_rank"], -len(row["appeared_in_modes"]), row["video_id"]
            ),
        )
        visible = candidates[:max_candidates]
        hidden = len(candidates) - len(visible)
        suggestion = gold.get(query_id, {})
        lines.extend(
            [
                "",
                f"## {query_id} — {query['query']}",
                "",
                f"- Category: `{query['category']}`; scope: `{query['scope']}`; filters: `{query.get('filters') or {}}`",
                f"- Held out: `{str(bool(query['held_out'])).lower()}`; expected type: `{query['expected_query_type']}`",
                f"- Planner: `{query.get('actual_planner_query_type', 'not_run')}` → `{query.get('actual_planned_mode', 'not_run')}`; agreement candidate: `{query.get('query_type_agreement_candidate', 'not_run')}`",
                "",
                "| Video | Title | Uploader | L | D | H | Suggestion | Rationale |",
                "|---:|---|---|---:|---:|---:|---|---|",
            ]
        )
        for row in visible:
            lines.append(
                "| {video_id} | {title} | {uploader} | {lexical_rank} | {dense_rank} | "
                "{hybrid_rank} | {candidate_label} | {candidate_rationale} |".format(
                    **{key: _cell(value) for key, value in row.items()}
                )
            )
        if hidden:
            lines.extend(["", f"Hidden from the main table: {hidden}; retained in the complete JSONL pool."])
        lines.extend(["", "### Top evidence", ""])
        for row in visible:
            for evidence in row.get("top_evidence", [])[:2]:
                lines.append(
                    f"- Video {row['video_id']} · {evidence.get('start')}–{evidence.get('end')}s · "
                    f"raw subtitle sources `{evidence.get('subtitle_sources', [])}`: "
                    f"{_text(evidence.get('evidence', ''))}"
                )
        lines.extend(
            [
                "",
                f"- Suggested relevant videos: `{suggestion.get('suggested_relevant_video_ids', [])}`",
                f"- Possible relevant videos: `{suggestion.get('possible_relevant_video_ids', [])}`",
                f"- Uncertain videos: `{suggestion.get('uncertain_video_ids', [])}`",
                f"- Suggested intervals: `{suggestion.get('suggested_intervals', [])}`",
                f"- Human decision required: {suggestion.get('review_notes') or 'Confirm/reject candidate relevance and intervals.'}",
            ]
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    return _text(str(value))


def _text(value: Any) -> str:
    return " ".join(str(value).replace("|", "\\|").split())[:300]
