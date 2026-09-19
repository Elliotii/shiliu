from __future__ import annotations

from pathlib import Path
from typing import Any


def validate_formal_result_payload(payload: dict[str, Any]) -> None:
    metrics = payload["aggregate_metrics"]
    for mode in ("lexical", "dense", "hybrid", "auto"):
        policies = metrics["policies"][mode]
        for policy in (
            "condensed_judged", "conservative_lower_bound", "discovery_upper_bound"
        ):
            if set(policies[policy]) != {"discovery", "evidence"}:
                raise ValueError("discovery and evidence metrics must remain separate")
        if set(metrics["negative_controls"][mode]) != {"Q14", "Q18"}:
            raise ValueError("negative controls must be reported separately")


def assert_no_closeout(output_paths: list[Path]) -> None:
    if any(path.name == "V3_CLOSEOUT.md" for path in output_paths):
        raise ValueError("Stage 6B must not generate V3_CLOSEOUT.md")
