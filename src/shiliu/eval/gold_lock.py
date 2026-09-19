from __future__ import annotations

from collections.abc import Iterable
from typing import Any


LABEL_FIELDS = {
    "R_evidence": "relevant_evidence_video_ids",
    "R_title": "relevant_title_only_video_ids",
    "N": "not_relevant_video_ids",
    "U_title": "unjudged_due_to_missing_content_video_ids",
    "OOS": "out_of_scope_due_to_filter_video_ids",
}


def semantic_partition(rows: Iterable[dict[str, Any]]) -> dict[tuple[str, int], str]:
    result: dict[tuple[str, int], str] = {}
    for row in rows:
        for label, field in LABEL_FIELDS.items():
            for video_id in row[field]:
                key = (str(row["query_id"]), int(video_id))
                if key in result:
                    raise ValueError(f"candidate assigned more than once: {key}")
                result[key] = label
    return result


def amendment_changes(
    original: dict[tuple[str, int], str],
    amended: dict[tuple[str, int], str],
    allowed_pairs: set[tuple[str, int]],
) -> list[dict[str, Any]]:
    if set(original) != set(amended):
        raise ValueError("amended ledger changes candidate coverage")
    changes = []
    allowed_transitions = {
        ("U_title", "R_evidence"), ("U_title", "N"), ("U_title", "U_title")
    }
    for key in sorted(original):
        prior, final = original[key], amended[key]
        if prior == final:
            continue
        if key not in allowed_pairs or (prior, final) not in allowed_transitions:
            raise ValueError(f"amendment scope violation: {key}: {prior}->{final}")
        changes.append({"query_id": key[0], "video_id": key[1], "prior": prior, "final": final})
    return changes


def move_to_out_of_scope(
    *, query_id: str, video_id: int, prior_label: str, failures: list[str]
) -> dict[str, Any]:
    if not failures:
        raise ValueError("eligibility failure is required")
    return {
        "query_id": query_id,
        "video_id": video_id,
        "prior_human_semantic_label": prior_label,
        "eligibility_failure": list(failures),
        "eligibility_source": "snapshot",
    }


def assert_positive_coverage(rows: Iterable[dict[str, Any]]) -> None:
    for row in rows:
        discovery = set(row["video_discovery_relevant_ids"])
        evidence = set(row["evidence_retrieval_relevant_ids"])
        if row["negative_control"]:
            if discovery or evidence:
                raise ValueError(f"negative control has Relevant Gold: {row['query_id']}")
        elif not discovery or not evidence:
            raise ValueError(f"positive query lost Relevant Gold: {row['query_id']}")
