from __future__ import annotations

from collections.abc import Sequence


def ranking_metrics(
    ranked_ids: Sequence[int], relevant_ids: set[int], *, k: int = 10
) -> dict[str, float]:
    if not relevant_ids:
        raise ValueError("ranking metrics require non-empty Relevant Gold")
    top = list(ranked_ids[:k])
    ranks = [index + 1 for index, value in enumerate(top) if value in relevant_ids]
    return {
        "recall": len(relevant_ids & set(top)) / len(relevant_ids),
        "mrr": 1 / min(ranks) if ranks else 0.0,
        "hit": float(bool(ranks)),
    }


def apply_unjudged_policy(
    ranked_ids: Sequence[int], relevant_ids: set[int], unjudged_ids: set[int], policy: str
) -> tuple[list[int], set[int]]:
    if policy == "condensed_judged":
        return [value for value in ranked_ids if value not in unjudged_ids], set(relevant_ids)
    if policy == "conservative_lower_bound":
        return list(ranked_ids), set(relevant_ids)
    if policy == "discovery_upper_bound":
        return list(ranked_ids), set(relevant_ids) | set(unjudged_ids)
    raise ValueError("unknown unjudged policy")


def duplicate_occupancy(video_ids: Sequence[int]) -> dict[str, float]:
    count = len(video_ids)
    unique = len(set(video_ids))
    return {
        "duplicate_count": count - unique,
        "duplicate_rate": 1 - unique / count if count else 0.0,
    }


def grouping_gain(grouped_ids: Sequence[int], raw_ids: Sequence[int], relevant: set[int]) -> int:
    return len(set(grouped_ids) & relevant) - len(set(raw_ids) & relevant)


def interval_overlap(predicted: tuple[float, float], gold: tuple[float, float]) -> float:
    return max(0.0, min(predicted[1], gold[1]) - max(predicted[0], gold[0]))


def anchor_error(jump_time: float, gold: tuple[float, float]) -> float:
    if jump_time < gold[0]:
        return gold[0] - jump_time
    if jump_time > gold[1]:
        return jump_time - gold[1]
    return 0.0


def oracle_mode(scores: dict[str, tuple[float, float]]) -> str:
    order = ("lexical", "dense", "hybrid")
    if set(scores) != set(order):
        raise ValueError("oracle requires lexical, dense, and hybrid")
    return max(order, key=lambda mode: (scores[mode][0], scores[mode][1], -order.index(mode)))
