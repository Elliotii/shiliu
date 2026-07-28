"""Deterministically project the four adjudicated pilot cases."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


EXPECTED_CASES = ("V2C_B1A00001", "V2C_B1A00002", "V2C_B2P00001", "V2C_B2P00002")
EXPECTED_DISTRIBUTION = {"sufficient": 1, "partial": 0, "insufficient": 3, "unverifiable": 0}


class PilotProjectionError(RuntimeError):
    pass


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PilotProjectionError("adjudicated pilot input invalid") from exc


def _packet_value(text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        patterns = (
            rf"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?{re.escape(label)}(?:\*\*)?\s*[:：]\s*(.+?)\s*$",
            rf"(?im)^\s*(?:[-*]\s*)?\*\*{re.escape(label)}\s*[:：]\*\*\s*(.+?)\s*$",
            rf"(?is)^#+\s*{re.escape(label)}\s*$\s*```(?:text)?\s*\n(.*?)\n```",
            rf"(?im)^\s*\|\s*{re.escape(label)}\s*\|\s*(.*?)\s*\|\s*$",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip().strip("`")
        json_match = re.search(
            rf'(?im)^[ \t]*["\']{re.escape(label)}["\'][ \t]*:[ \t]*(["\'])(.*?)\1[ \t]*,?[ \t]*$',
            text,
        )
        if json_match:
            return json_match.group(2).strip()
        heading_match = re.search(
            rf"(?im)^\s*#+\s*{re.escape(label)}\s*$\n(?:\s*\n)*\s*(?:```(?:text)?\s*)?(.+?)\s*$",
            text,
        )
        if heading_match:
            return heading_match.group(1).strip().strip("`")
    raise PilotProjectionError("required pilot packet field unavailable")


def _source_fields(text: str) -> dict[str, Any]:
    aliases = {
        "source_video_id": ("Source Video ID", "Video ID", "source_video_id", "video_id"),
        "source_artifact_id": ("Source Artifact ID", "source_artifact_id"),
        "source_version": ("Source Version", "source_version"),
        "source_type": ("Source Type", "source_type"),
        "source_language": ("Source Language", "source_language"),
        "timeline_run_id": ("Timeline Run ID", "timeline_run_id"),
    }
    values: dict[str, Any] = {}
    fallbacks = {
        "source_video_id": r"\b(BV[0-9A-Za-z]{10})\b",
        "source_artifact_id": r"\b((?:raw_subtitle|source_artifact)[^\s,\]}`\"]+)\b",
        "timeline_run_id": r"\b(timeline(?:_run)?_[0-9a-f]{16,64})\b",
    }
    for key, labels in aliases.items():
        try:
            values[key] = _packet_value(text, labels)
            continue
        except PilotProjectionError:
            pass
        pattern = fallbacks.get(key)
        match = re.search(pattern, text) if pattern else None
        if match:
            values[key] = match.group(1)
        elif key == "source_type" and str(values.get("source_artifact_id", "")).startswith("raw_subtitle"):
            values[key] = "raw_subtitle"
        elif key == "source_language":
            language = re.search(r'(?im)["\'](?:language|lang)["\']\s*:\s*["\']([^"\']+)', text)
            if language:
                values[key] = language.group(1)
        else:
            values[key] = None
    return values


def _original_query(text: str) -> str:
    aliases = (
        "Original Query", "Original User Query", "Original Retrieval Query",
        "Search Query", "User Query", "original_query", "query_text",
    )
    try:
        return _packet_value(text, aliases)
    except PilotProjectionError:
        pass
    for line in text.splitlines():
        lowered = line.lower()
        if "query" not in lowered or "evidence" in lowered or "evaluation" in lowered:
            continue
        match = re.search(r"[:：]\*{0,2}\s*(.+?)\s*$", line)
        if match and match.group(1).strip(" `*|"):
            return match.group(1).strip(" `*|")
    raise PilotProjectionError("original pilot query unavailable")


def build_existing_pilot_coverage(
    adjudicated_paths: tuple[str | Path, str | Path],
    packet_paths: tuple[str | Path, str | Path, str | Path, str | Path],
    *,
    source_metadata_by_video: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    decisions: dict[str, dict[str, Any]] = {}
    for path in adjudicated_paths:
        for record in _jsonl(Path(path)):
            case_id = str(record.get("case_id") or "")
            if case_id in decisions:
                raise PilotProjectionError("duplicate pilot case")
            decisions[case_id] = record
    if tuple(sorted(decisions)) != tuple(sorted(EXPECTED_CASES)):
        raise PilotProjectionError("pilot case set mismatch")
    distribution = {key: 0 for key in EXPECTED_DISTRIBUTION}
    for record in decisions.values():
        status = str(record.get("final_status") or "")
        if status not in distribution:
            raise PilotProjectionError("pilot status invalid")
        distribution[status] += 1
    if distribution != EXPECTED_DISTRIBUTION:
        raise PilotProjectionError("pilot status distribution mismatch")

    packet_by_case: dict[str, str] = {}
    for path_like in packet_paths:
        path = Path(path_like)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise PilotProjectionError("pilot packet invalid") from exc
        match = re.search(r"V2C_B(?:1A|2P)\d{5}", text) or re.search(r"V2C_B(?:1A|2P)\d{5}", str(path))
        if not match:
            raise PilotProjectionError("pilot case identity unavailable")
        packet_by_case[match.group(0)] = text
    if set(packet_by_case) != set(EXPECTED_CASES):
        raise PilotProjectionError("pilot packet set mismatch")

    cases = []
    for case_id in EXPECTED_CASES:
        text = packet_by_case[case_id]
        source = _source_fields(text)
        source_video_id = str(source.get("source_video_id") or "")
        resolved = (source_metadata_by_video or {}).get(source_video_id, {})
        for key in (
            "source_artifact_id", "source_version", "source_type",
            "source_language", "timeline_run_id",
        ):
            if not source.get(key) and resolved.get(key):
                source[key] = resolved[key]
        if any(not source.get(key) for key in source):
            raise PilotProjectionError("required pilot source identity unavailable")
        status = str(decisions[case_id]["final_status"])
        view = _packet_value(text, ("Evaluation View", "evaluation_view"))
        cases.append({
            "case_id": case_id,
            "original_query": _original_query(text),
            "evaluation_view": view,
            "evidence_question": _packet_value(text, ("Evidence Question", "evidence_question")),
            "final_status": status,
            **source,
            "coverage_tags": sorted({view, status, source["source_type"], source["source_language"]}),
        })
    return {"cases": cases, "status_distribution": {**distribution, "total": len(cases)}, "version": "v3.5-existing-pilot-coverage-safe-v1"}


def write_existing_pilot_coverage(value: dict[str, Any], path: str | Path) -> None:
    Path(path).write_bytes(_canonical(value))
