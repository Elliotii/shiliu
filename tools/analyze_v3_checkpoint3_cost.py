from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from shiliu.config import AppPaths, load_config
from shiliu.db import Database
from shiliu.taxonomy.repository import TaxonomyRepository


SYSTEM_PROMPT = "Follow the user's transformation rules and return valid JSON only."
STAGE_ORDER = [
    "facet",
    "local_discovery",
    "content_type_discovery",
    "consolidation",
    "quality_gate_feedback",
    "hierarchy_validation",
    "trial_assignment",
    "json_repair",
    "other",
]


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def estimated_tokens(text: str) -> float:
    """Tokenizer-free mixed Chinese/ASCII estimate; never reported as actual."""

    total = 0.0
    ascii_run = 0
    for char in text:
        code = ord(char)
        if char.isascii() and char.isalnum():
            ascii_run += 1
            continue
        if ascii_run:
            total += math.ceil(ascii_run / 4)
            ascii_run = 0
        if char.isspace():
            continue
        if 0x3400 <= code <= 0x9FFF:
            total += 1
        elif char.isascii():
            total += 0.35
        else:
            total += 0.8
    if ascii_run:
        total += math.ceil(ascii_run / 4)
    return total


def parse_json_response(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.S | re.I)
    if fence:
        stripped = fence.group(1)
    return json.loads(stripped[stripped.find("{") : stripped.rfind("}") + 1])


def usage_value(usage: dict[str, Any], key: str) -> int | None:
    value = usage.get(key)
    return int(value) if isinstance(value, (int, float)) else None


def cached_tokens(usage: dict[str, Any]) -> int | None:
    value = usage.get("prompt_cache_hit_tokens")
    if isinstance(value, (int, float)):
        return int(value)
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict) and isinstance(details.get("cached_tokens"), (int, float)):
        return int(details["cached_tokens"])
    return None


def reasoning_tokens(usage: dict[str, Any]) -> int | None:
    details = usage.get("completion_tokens_details")
    if isinstance(details, dict) and isinstance(details.get("reasoning_tokens"), (int, float)):
        return int(details["reasoning_tokens"])
    return None


def stage_from_path(relative: Path) -> str:
    value = relative.parts[0]
    return value if value in STAGE_ORDER else "other"


def thinking_mode(audit: dict[str, Any], *, repair: bool = False) -> str:
    if repair:
        return "off"
    params = audit.get("parameters") or {}
    if params.get("thinking_enabled") is False:
        return "off"
    if params.get("thinking_enabled") is True:
        return str(params.get("reasoning_effort") or "on")
    return "unspecified"


def card_count(stage: str, audit: dict[str, Any]) -> int:
    if stage in {"local_discovery", "trial_assignment", "content_type_discovery"}:
        return int(audit.get("input_count") or 0)
    return 0


def collect_calls(run_dir: Path) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for audit_path in sorted(run_dir.glob("**/audit.json")):
        relative = audit_path.relative_to(run_dir)
        stage = stage_from_path(relative)
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        attempt_dir = audit_path.parent.name
        stage_attempt = int(attempt_dir.split("-")[-1])
        unit = audit_path.parent.parent.name
        request_count = int(audit.get("request_attempt_count") or 1)
        history = {int(item["attempt"]): item for item in audit.get("attempt_history") or []}
        for request_attempt in range(1, request_count + 1):
            if request_attempt == request_count:
                source = audit
            else:
                source = history.get(request_attempt)
            if source is None:
                raw_name = "raw-response.txt" if request_attempt == 1 else f"raw-response-{request_attempt:02d}.txt"
                raw_path = audit_path.parent / raw_name
                source = {
                    "status": "empty_response" if raw_path.is_file() and raw_path.stat().st_size == 0 else "unknown",
                    "usage": None,
                    "elapsed_seconds": None,
                    "raw_response_path": raw_name if raw_path.is_file() else None,
                }
            usage = source.get("usage") or {}
            prompt = (audit_path.parent / "prompt.txt").read_text(encoding="utf-8")
            raw_name = source.get("raw_response_path")
            raw_path = audit_path.parent / str(raw_name or "")
            raw_chars = len(raw_path.read_text(encoding="utf-8")) if raw_path.is_file() else None
            repair_path = audit_path.parent / "repair-audit.json"
            validation_path = audit_path.parent / "validation-error.txt"
            schema_valid = bool(source.get("status") not in {"empty_response", "unknown"})
            if request_attempt == 1 and validation_path.is_file():
                schema_valid = False
            prompt_tokens = usage_value(usage, "prompt_tokens")
            completion = usage_value(usage, "completion_tokens")
            calls.append(
                {
                    "call_id": f"{stage}/{unit}/stage-{stage_attempt:02d}/request-{request_attempt:02d}",
                    "stage_name": stage,
                    "batch_id": unit,
                    "card_count": card_count(stage, audit),
                    "attempt_number": request_attempt,
                    "stage_attempt_number": stage_attempt,
                    "thinking_mode": thinking_mode(audit),
                    "prompt_characters": len(prompt),
                    "prompt_tokens": prompt_tokens,
                    "cached_prompt_tokens": cached_tokens(usage),
                    "completion_tokens": completion,
                    "reasoning_tokens": reasoning_tokens(usage),
                    "total_tokens": (
                        prompt_tokens + completion
                        if prompt_tokens is not None and completion is not None
                        else None
                    ),
                    "elapsed_seconds": source.get("elapsed_seconds"),
                    "raw_output_characters": raw_chars,
                    "schema_valid": schema_valid,
                    "repair_required": repair_path.is_file() and request_attempt == 1,
                    "source_stage": stage,
                    "audit_path": str(relative),
                    "status": source.get("status"),
                }
            )

        repair_path = audit_path.parent / "repair-audit.json"
        if repair_path.is_file():
            repair = json.loads(repair_path.read_text(encoding="utf-8"))
            usage = repair.get("usage") or {}
            repair_prompt = (audit_path.parent / "repair-prompt.txt").read_text(encoding="utf-8")
            raw_path = audit_path.parent / str(repair.get("raw_response_path") or "")
            prompt_tokens = usage_value(usage, "prompt_tokens")
            completion = usage_value(usage, "completion_tokens")
            calls.append(
                {
                    "call_id": f"json_repair/{stage}/{unit}/stage-{stage_attempt:02d}/repair-{int(repair.get('attempt_count') or 1):02d}",
                    "stage_name": "json_repair",
                    "batch_id": unit,
                    "card_count": 0,
                    "attempt_number": int(repair.get("attempt_count") or 1),
                    "stage_attempt_number": stage_attempt,
                    "thinking_mode": thinking_mode(repair, repair=True),
                    "prompt_characters": len(repair_prompt),
                    "prompt_tokens": prompt_tokens,
                    "cached_prompt_tokens": cached_tokens(usage),
                    "completion_tokens": completion,
                    "reasoning_tokens": reasoning_tokens(usage),
                    "total_tokens": (
                        prompt_tokens + completion
                        if prompt_tokens is not None and completion is not None
                        else None
                    ),
                    "elapsed_seconds": repair.get("elapsed_seconds"),
                    "raw_output_characters": len(raw_path.read_text(encoding="utf-8")) if raw_path.is_file() else None,
                    "schema_valid": repair.get("status") == "completed",
                    "repair_required": False,
                    "source_stage": stage,
                    "audit_path": str(repair_path.relative_to(run_dir)),
                    "status": repair.get("status"),
                }
            )
    return calls


def aggregate_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for stage in STAGE_ORDER:
        rows = [row for row in calls if row["stage_name"] == stage]
        result.append(
            {
                "stage_name": stage,
                "call_count": len(rows),
                "known_total_tokens": sum(row["total_tokens"] or 0 for row in rows),
                "unknown_usage_calls": sum(row["total_tokens"] is None for row in rows),
                "prompt_tokens": sum(row["prompt_tokens"] or 0 for row in rows),
                "cached_prompt_tokens": sum(row["cached_prompt_tokens"] or 0 for row in rows),
                "completion_tokens": sum(row["completion_tokens"] or 0 for row in rows),
                "reasoning_tokens": sum(row["reasoning_tokens"] or 0 for row in rows),
                "known_elapsed_seconds": round(sum(row["elapsed_seconds"] or 0 for row in rows), 3),
            }
        )
    return result


def serialized_field_chars(rows: list[list[Any]]) -> dict[str, int]:
    counts = Counter()
    serialized = "\n".join(compact_json(row) for row in rows)
    for row in rows:
        evidence = row[1]
        counts["短 ID 和证据等级"] += len(str(row[0])) + len(str(evidence))
        counts["标题"] += len(str(row[2]))
        if evidence in {"A", "B"}:
            counts["一句话结论"] += len(str(row[3]))
            counts["核心观点"] += sum(len(str(value)) for value in row[4])
            counts["实体"] += sum(len(str(value)) for value in row[5])
        elif evidence == "C":
            counts["简介"] += len(str(row[3]))
    content = sum(counts.values())
    counts["重复 JSON / 行式协议字段"] += len(serialized) - content
    return dict(counts)


def split_prompt(stage: str, prompt: str, rows: list[list[Any]] | None) -> dict[str, int]:
    counts = Counter({"System Prompt": len(SYSTEM_PROMPT)})
    if stage == "json_repair":
        task, rest = prompt.split("精简 Schema：\n", 1)
        schema, rest = rest.split("\n\n校验错误", 1)
        error, raw = rest.split("\n\n原始响应：\n", 1)
        counts["任务说明"] += len(task) + len("校验错误") + len(error)
        counts["Schema"] += len(schema)
        counts["历史阶段输出"] += len(raw)
        return dict(counts)
    if "精简输出结构：" in prompt:
        task, rest = prompt.split("精简输出结构：", 1)
        counts["任务说明"] += len(task)
    else:
        rest = prompt
    if stage == "local_discovery":
        schema, rest = rest.split("\n输入行协议：", 1)
        protocol, _ = rest.split("\n本批卡片：\n", 1)
        counts["Schema"] += len(schema)
        counts["重复 JSON / 行式协议字段"] += len("输入行协议：") + len(protocol)
        counts.update(serialized_field_chars(rows or []))
    elif stage == "trial_assignment":
        schema, rest = rest.split("\n冻结 Taxonomy：", 1)
        taxonomy, _ = rest.split("\n卡片行：\n", 1)
        counts["Schema"] += len(schema)
        counts["历史阶段输出"] += len(taxonomy)
        counts.update(serialized_field_chars(rows or []))
    elif stage == "consolidation":
        schema, history = rest.split("\n候选支持统计：", 1)
        counts["Schema"] += len(schema)
        feedback_marker = "\n\n上次质量门禁反馈。"
        if feedback_marker in history:
            history, feedback = history.split(feedback_marker, 1)
            counts["Quality Gate feedback"] += len(feedback_marker) + len(feedback)
        counts["历史阶段输出"] += len("候选支持统计：") + len(history)
    elif stage == "hierarchy_validation":
        schema, history = rest.split("\n输入：", 1)
        counts["Schema"] += len(schema)
        counts["历史阶段输出"] += len(history)
    else:
        counts["任务说明"] += len(rest)
    return dict(counts)


def input_costs(run_dir: Path, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = json.loads((run_dir / "compact-corpus.json").read_text(encoding="utf-8"))
    by_id = {row[0]: row for row in compact["rows"]}
    output = []
    for call in calls:
        if call["total_tokens"] is None:
            continue
        audit_path = run_dir / call["audit_path"]
        call_dir = audit_path.parent
        prompt_name = "repair-prompt.txt" if call["stage_name"] == "json_repair" else "prompt.txt"
        prompt = (call_dir / prompt_name).read_text(encoding="utf-8")
        audit = json.loads((call_dir / "audit.json").read_text(encoding="utf-8"))
        rows = [by_id[value] for value in audit.get("input_ids") or [] if value in by_id]
        components = split_prompt(call["stage_name"], prompt, rows)
        weights = {key: estimated_tokens("字" * value) if key not in {"System Prompt"} else estimated_tokens(SYSTEM_PROMPT) for key, value in components.items()}
        total_weight = sum(weights.values()) or 1
        actual_prompt_tokens = int(call["prompt_tokens"] or 0)
        allocated = {key: actual_prompt_tokens * value / total_weight for key, value in weights.items()}
        for key, chars in components.items():
            output.append(
                {
                    "call_id": call["call_id"],
                    "stage_name": call["stage_name"],
                    "component": key,
                    "characters": chars,
                    "allocated_prompt_tokens_estimate": round(allocated[key], 1),
                    "share_of_prompt": round(allocated[key] / actual_prompt_tokens, 4) if actual_prompt_tokens else 0,
                    "token_method": "character-weight allocation calibrated to API prompt_tokens; not DeepSeek tokenizer output",
                }
            )
    return output


def candidate_stats(value: dict[str, Any], *, label: str) -> dict[str, Any]:
    cts = value.get("content_types") or []
    domains = value.get("domains") or []
    topics = value.get("topics") or []
    entities = value.get("entities") or []
    primary = [item for item in domains if item.get("suggested_level", "primary") == "primary"]
    sub = [item for item in domains if item.get("suggested_level") == "subdomain"]
    if domains and "children" in domains[0]:
        primary = domains
        sub = [child for item in domains for child in item.get("children") or []]
    all_items = [*cts, *domains, *topics, *entities]
    if domains and "children" in domains[0]:
        all_items.extend(sub)
    return {
        "output_id": label,
        "content_type_count": len(cts),
        "primary_domain_count": len(primary),
        "subdomain_count": len(sub),
        "topic_count": len(topics),
        "entity_count": len(entities),
        "supporting_id_occurrences": sum(len(item.get("supporting_ids") or []) for item in all_items),
        "definition_characters": sum(len(str(item.get("definition") or "")) for item in all_items),
        "includes_excludes_characters": sum(
            sum(len(str(x)) for x in item.get("includes") or [])
            + sum(len(str(x)) for x in item.get("excludes") or [])
            for item in all_items
        ),
        "reason_characters": sum(len(str(item.get("stability_reason") or "")) for item in all_items),
    }


def output_inflation(run_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for raw_path in sorted(run_dir.glob("local_discovery/**/raw-response*.txt")):
        if raw_path.stat().st_size:
            try:
                value = parse_json_response(raw_path.read_text(encoding="utf-8"))
                stats_source = "raw_response"
            except (json.JSONDecodeError, ValueError):
                value = json.loads((raw_path.parent / "parsed-output.json").read_text(encoding="utf-8"))
                stats_source = "validated_or_repaired_output"
            item = candidate_stats(value, label=str(raw_path.relative_to(run_dir)))
            item["stats_source"] = stats_source
            rows.append(item)
    for raw_path in sorted(run_dir.glob("consolidation/**/raw-response*.txt")):
        if raw_path.stat().st_size:
            try:
                value = parse_json_response(raw_path.read_text(encoding="utf-8"))
                stats_source = "raw_response"
            except (json.JSONDecodeError, ValueError):
                value = json.loads((raw_path.parent / "parsed-output.json").read_text(encoding="utf-8"))
                stats_source = "validated_or_repaired_output"
            item = candidate_stats(value, label=str(raw_path.relative_to(run_dir)))
            item["stats_source"] = stats_source
            rows.append(item)
    for raw_path in sorted(run_dir.glob("trial_assignment/**/raw-response*.txt")):
        if raw_path.stat().st_size:
            value = parse_json_response(raw_path.read_text(encoding="utf-8"))
            assignments = value.get("assignments") or []
            rows.append(
                {
                    "output_id": str(raw_path.relative_to(run_dir)),
                    "assignment_count": len(assignments),
                    "reason_characters": sum(len(str(item.get("reason") or item.get("classification_reason") or "")) for item in assignments),
                    "dynamic_topic_count": sum(len(item.get("dynamic_topics") or []) for item in assignments),
                    "entity_count": sum(len(item.get("entities") or []) for item in assignments),
                }
            )
    return rows


def profile_row(short_id: str, title: str, evidence: str, facet: dict[str, Any]) -> list[Any]:
    return [
        short_id,
        evidence,
        title,
        facet.get("main_subject") or "",
        facet.get("content_goal") or "",
        list(facet.get("technical_aspects") or [])[:5],
        list(facet.get("usage_context") or [])[:3],
        [item.get("name", "") for item in facet.get("candidate_entities") or []][:5],
    ]


def projection(rows: list[list[Any]], facets: list[dict[str, Any]], id_map: dict[str, str]) -> dict[str, Any]:
    facet_map = {item["content_id"]: item for item in facets}
    templates = facets
    profile_rows = []
    real_profiles = 0
    for index, row in enumerate(rows):
        facet = facet_map.get(id_map[row[0]])
        if facet is not None:
            real_profiles += 1
        else:
            facet = templates[index % len(templates)]
        profile_rows.append(profile_row(row[0], row[2], row[1], facet))
    current_text = "\n".join(compact_json(row) for row in rows)
    profile_text = "\n".join(compact_json(row) for row in profile_rows)
    return {
        "card_count": len(rows),
        "current_compact_characters": len(current_text),
        "classification_profile_characters_projected": len(profile_text),
        "current_tokens_estimated": round(estimated_tokens(current_text)),
        "classification_profile_tokens_projected": round(estimated_tokens(profile_text)),
        "character_ratio_profile_to_current": round(len(profile_text) / len(current_text), 4),
        "token_ratio_profile_to_current": round(estimated_tokens(profile_text) / estimated_tokens(current_text), 4),
        "profiles_with_real_existing_facets": real_profiles,
        "projection_method": "actual id/title/evidence plus existing 12-facet shapes cycled for missing profiles; row-array encoding",
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if rows:
            writer.writeheader()
            writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--snapshot-id", type=int, default=2)
    parser.add_argument("--facets", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run_dir = args.run_dir.expanduser().resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    paths = AppPaths.defaults()
    config = load_config(paths)
    db = Database(paths.database)
    snapshot = TaxonomyRepository(db).get_snapshot(args.snapshot_id)
    if snapshot is None:
        raise SystemExit("snapshot not found")
    facets = json.loads(args.facets.read_text(encoding="utf-8"))
    compact = json.loads((run_dir / "compact-corpus.json").read_text(encoding="utf-8"))
    plan = json.loads((run_dir / "batch-plan.json").read_text(encoding="utf-8"))
    by_id = {row[0]: row for row in compact["rows"]}
    selected_ids = [value for batch in plan["batches"] for value in batch]
    selected_rows = [by_id[value] for value in selected_ids]
    full_rows = [row for row in compact["rows"] if row[1] != "D"]

    calls = collect_calls(run_dir)
    aggregates = aggregate_calls(calls)
    costs = input_costs(run_dir, calls)
    inflation = output_inflation(run_dir)
    projections = {
        "cards_48": projection(selected_rows, facets, compact["id_map"]),
        "cards_128": projection(full_rows, facets, compact["id_map"]),
    }
    analysis = {
        "run_id": 1,
        "snapshot_id": args.snapshot_id,
        "snapshot_hash": snapshot["snapshot_hash"],
        "selected_evidence_counts": dict(Counter(row[1] for row in selected_rows)),
        "full_evidence_counts": dict(Counter(row[1] for row in full_rows)),
        "calls": calls,
        "stage_aggregates": aggregates,
        "input_component_costs": costs,
        "output_inflation": inflation,
        "compression_projections": projections,
        "tokenizer": {
            "deepseek_tokenizer_available": False,
            "field_level_method": "character-weight allocation calibrated to actual API prompt_tokens",
            "projection_method": "mixed Chinese/ASCII heuristic; not actual tokenizer output",
        },
    }
    (out / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(out / "call_details.csv", calls)
    write_csv(out / "input_component_costs.csv", costs)
    write_csv(out / "output_inflation.csv", inflation)

    card_by_key = {card["content_key"]: card for card in snapshot["cards"]}
    sample_ids = []
    wanted = Counter({"A": 2, "B": 1, "C": 2})
    for row in selected_rows:
        if wanted[row[1]] > 0:
            sample_ids.append(row[0])
            wanted[row[1]] -= 1
    samples = [
        {
            "short_id": short_id,
            "content_key": compact["id_map"][short_id],
            "evidence_level": by_id[short_id][1],
            "discovery_view": card_by_key[compact["id_map"][short_id]]["discovery_view"],
        }
        for short_id in sample_ids
    ]
    (out / "discovery_view_samples.json").write_text(json.dumps(samples, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    local_dir = run_dir / "local_discovery" / "batch-001" / "attempt-01"
    (out / "local_discovery_request_batch001.txt").write_text((local_dir / "prompt.txt").read_text(encoding="utf-8"), encoding="utf-8")
    (out / "local_discovery_raw_output_batch001.txt").write_text((local_dir / "raw-response.txt").read_text(encoding="utf-8"), encoding="utf-8")

    consolidation_prompt = (run_dir / "consolidation" / "main" / "attempt-02" / "prompt.txt").read_text(encoding="utf-8")
    consolidation_summary = {
        "prompt_characters": len(consolidation_prompt),
        "contains_original_cards": False,
        "fields": ["task instructions", "compact schema", "candidate support summary", "two local candidate outputs", "quality gate feedback"],
        "component_characters": split_prompt("consolidation", consolidation_prompt, None),
    }
    (out / "consolidation_request_summary.json").write_text(json.dumps(consolidation_summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    assignment_dir = run_dir / "trial_assignment" / "batch-001" / "attempt-01"
    assignment_prompt = (assignment_dir / "prompt.txt").read_text(encoding="utf-8")
    assignment_output = parse_json_response((assignment_dir / "raw-response.txt").read_text(encoding="utf-8"))
    assignment_summary = {
        "prompt_characters": len(assignment_prompt),
        "input_card_count": 24,
        "request_fields": ["task instructions", "compact schema", "frozen taxonomy draft", "24 compact card rows"],
        "output_assignment_count": len(assignment_output.get("assignments") or []),
        "output_reason_characters": sum(len(str(item.get("reason") or item.get("classification_reason") or "")) for item in assignment_output.get("assignments") or []),
        "request_component_characters": split_prompt("trial_assignment", assignment_prompt, [by_id[value] for value in json.loads((assignment_dir / "audit.json").read_text())["input_ids"]]),
        "first_output_sample": (assignment_output.get("assignments") or [None])[0],
    }
    (out / "trial_assignment_request_output_summary.json").write_text(json.dumps(assignment_summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
