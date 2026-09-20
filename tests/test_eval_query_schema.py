from __future__ import annotations

from shiliu.eval.queries import CATEGORY_COUNTS, validate_query_candidates


def _queries():
    rows = []
    number = 1
    for category, count in CATEGORY_COUNTS.items():
        for _ in range(count):
            rows.append(
                {
                    "query_id": f"Q{number:02d}", "query": f"query {number}",
                    "category": category, "scope": "all", "filters": {},
                    "expected_query_type": "keyword_phrase", "held_out": number <= 12,
                    "negative_control": number in {23, 24}, "provenance": "test",
                    "rationale": "test", "requires_interval_gold": False,
                    "status": "candidate",
                }
            )
            number += 1
    return rows


def test_candidate_query_gate() -> None:
    stats = validate_query_candidates(_queries())
    assert stats["query_count"] == 24
    assert stats["held_out_count"] == 12
    assert stats["negative_control_count"] == 2


def test_candidate_query_gate_rejects_unknown_filter() -> None:
    rows = _queries()
    rows[0]["filters"] = {"invented": True}
    try:
        validate_query_candidates(rows)
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("unknown filter accepted")
