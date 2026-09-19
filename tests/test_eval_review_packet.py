from __future__ import annotations

from pathlib import Path

from shiliu.eval.review import render_review_packet


def test_review_packet_bounds_main_table_and_evidence(tmp_path: Path) -> None:
    query = {
        "query_id": "Q01", "query": "MCP", "category": "exact_entity",
        "scope": "all", "filters": {}, "held_out": False,
        "expected_query_type": "exact_entity",
    }
    pool = [
        {
            "query_id": "Q01", "video_id": index, "title": f"title {index}",
            "uploader": "u", "lexical_rank": index, "dense_rank": None,
            "hybrid_rank": None, "best_rank": index, "appeared_in_modes": ["lexical"],
            "candidate_label": "unknown", "candidate_rationale": "",
            "top_evidence": [{"start": 1, "end": 2, "subtitle_sources": ["ai"], "evidence": "x" * 500}],
        }
        for index in range(1, 18)
    ]
    gold = [{"query_id": "Q01", "suggested_relevant_video_ids": [], "possible_relevant_video_ids": [], "uncertain_video_ids": [], "suggested_intervals": [], "review_notes": "review"}]
    output = tmp_path / "packet.md"
    render_review_packet([query], pool, gold, output)
    text = output.read_text(encoding="utf-8")
    assert "Hidden from the main table: 2" in text
    assert "Gold is not locked" in text
    assert "title 16" not in text
    assert "x" * 301 not in text
