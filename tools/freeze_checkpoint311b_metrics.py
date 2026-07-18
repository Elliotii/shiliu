from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    freeze(arguments.run_dir, arguments.output_dir)
    return 0


def freeze(run_dir: Path, output_dir: Path) -> None:
    assignments_path = run_dir / "controlled-facet-assignments.json"
    dynamic_path = run_dir / "dynamic-faceting.json"
    source_hashes = {
        "assignments": sha256(assignments_path),
        "dynamic_faceting": sha256(dynamic_path),
    }
    assignments = json.loads(assignments_path.read_text(encoding="utf-8"))["assignments"]
    dynamic = json.loads(dynamic_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        output_dir / "dynamic-facet-metrics-v1.json",
        {
            "version": "dynamic-facet-metrics-v1",
            "source_run_id": 21,
            "source_hashes": source_hashes,
            "metrics": dynamic["metrics"],
        },
    )
    write_json(
        output_dir / "cross-facet-redundancy-v1.json",
        cross_facet_redundancy(assignments, source_hashes),
    )


def cross_facet_redundancy(
    assignments: list[dict[str, Any]], source_hashes: dict[str, str]
) -> dict[str, Any]:
    records: list[dict[str, str]] = []
    for item in assignments:
        domain = item["domain"]
        domain_id = domain["primary_path"][0]
        form = item["presentation_form"]["primary"]
        objects = [value["id"] for value in item["object_types"]] or ["<empty>"]
        contexts = [value["id"] for value in item["suggested_use_contexts"]] or ["<empty>"]
        for object_id in objects:
            records.append({"domain": domain_id, "form": form, "object": object_id})
        for context_id in contexts:
            records.append({"domain": domain_id, "form": form, "context": context_id})
    pairs: list[dict[str, Any]] = []
    for left, right in (("form", "object"), ("form", "context"), ("object", "context")):
        left_support = Counter(row[left] for row in records if left in row and right in row)
        right_support = Counter(row[right] for row in records if left in row and right in row)
        joint = Counter((row[left], row[right]) for row in records if left in row and right in row)
        for (left_id, right_id), support in sorted(joint.items()):
            if support < 3:
                continue
            left_given_right = support / right_support[right_id]
            right_given_left = support / left_support[left_id]
            if left_given_right > 0.9 and right_given_left > 0.9:
                pairs.append(
                    {
                        "facets": [left, right],
                        "values": [left_id, right_id],
                        "support": support,
                        "p_left_given_right": round(left_given_right, 4),
                        "p_right_given_left": round(right_given_left, 4),
                    }
                )
    domain_members: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in assignments:
        domain = item["domain"]
        domain_members[domain["primary_path"][0]].append(item)
    reductions: dict[str, dict[str, float]] = {}
    for facet in ("presentation_form", "focus_object_type", "suggested_use_context"):
        values: list[float] = []
        mean_values: list[float] = []
        for members in domain_members.values():
            counts = Counter()
            for item in members:
                if facet == "presentation_form":
                    counts[item["presentation_form"]["primary"]] += 1
                elif facet == "focus_object_type":
                    for value in item["object_types"]:
                        counts[value["id"]] += 1
                else:
                    for value in item["suggested_use_contexts"]:
                        counts[value["id"]] += 1
            for value_id, count in counts.items():
                reduction = 1 - count / len(members)
                values.append(reduction)
                if not (facet == "presentation_form" and value_id == "unknown"):
                    mean_values.append(reduction)
        reductions[facet] = {
            "mean": round(sum(mean_values) / len(mean_values), 4) if mean_values else 0,
            "median": round(statistics.median(values), 4) if values else 0,
        }
    return {
        "version": "cross-facet-redundancy-v1",
        "source_run_id": 21,
        "source_hashes": source_hashes,
        "near_duplicate_pairs": pairs,
        "near_duplicate_pair_count": len(pairs),
        "within_domain_average_reduction": reductions,
        "thresholds": {
            "minimum_support": 3,
            "bidirectional_conditional_probability": 0.9,
        },
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
