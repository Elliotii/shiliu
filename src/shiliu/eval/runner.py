from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def assert_explicit_execution(requested_mode: str, response: Any) -> None:
    if requested_mode not in {"lexical", "dense", "hybrid"}:
        raise ValueError("explicit execution check only applies to base retrievers")
    if response.executed_mode != requested_mode or response.fallback:
        raise ValueError(f"explicit {requested_mode} did not execute directly")


def assert_stable_repetitions(repetitions: Iterable[dict[str, Any]]) -> None:
    values = list(repetitions)
    if len(values) < 2:
        raise ValueError("stability requires at least two repetitions")
    first = values[0]
    for value in values[1:]:
        if value["product_video_ids"] != first["product_video_ids"]:
            raise ValueError("Product order is not stable")
        if value["raw_unit_ids"] != first["raw_unit_ids"]:
            raise ValueError("Raw order is not stable")


def assert_snapshot_only(run_identity: dict[str, Any]) -> None:
    if run_identity["snapshot_sha256_before"] != run_identity["snapshot_sha256_after"]:
        raise ValueError("snapshot base changed")
    if not run_identity["work_hashes_unchanged"]:
        raise ValueError("Eval corpus/index tables changed")
    if not all(run_identity["live_trace_counts_unchanged"].values()):
        raise ValueError("Live traces changed")

