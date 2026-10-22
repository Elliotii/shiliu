"""Aggregate-only projection of identities protected from development use."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable


PROTECTED_INPUT_NAMES = (
    "eval_queries.locked.jsonl",
    "eval_gold.locked.jsonl",
    "eval_gold_review.decisions.amended.jsonl",
    "gold_lock_audit.json",
    "human_ledger_amendment_audit.json",
)


class ProtectedProjectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProtectedSourceProjection:
    heldout_query_identities: frozenset[str]
    source_identities: frozenset[str]
    video_identities: frozenset[str]
    leakage_groups: frozenset[str]
    protected_input_file_count: int
    protected_record_count: int

    def aggregate(self, *, excluded_source_count: int, unknown_count: int) -> dict[str, int]:
        return {
            "protected_input_file_count": self.protected_input_file_count,
            "protected_record_count": self.protected_record_count,
            "heldout_query_count": len(self.heldout_query_identities),
            "protected_source_identity_count": len(self.source_identities),
            "protected_video_identity_count": len(self.video_identities),
            "protected_leakage_group_count": len(self.leakage_groups),
            "excluded_source_count": excluded_source_count,
            "unknown_protection_excluded_count": unknown_count,
        }


def _records(path: Path) -> list[Any]:
    try:
        if path.suffix == ".jsonl":
            return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [json.loads(path.read_text(encoding="utf-8"))]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProtectedProjectionError("protected input missing or invalid") from exc


def _walk(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key), child
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _scalar_strings(record: Any, keys: set[str]) -> set[str]:
    values: set[str] = set()
    for key, value in _walk(record):
        if key.lower() not in keys:
            continue
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            if isinstance(candidate, (str, int)) and str(candidate).strip():
                values.add(str(candidate).strip())
    return values


def _is_heldout(record: Any) -> bool:
    for key, value in _walk(record):
        normalized_key = key.lower()
        if normalized_key in {"held_out", "heldout", "is_held_out", "is_heldout"} and value is True:
            return True
        if normalized_key in {"split", "partition", "evaluation_split", "query_split"}:
            if str(value).lower().replace("-", "").replace("_", "") == "heldout":
                return True
    return False


def build_protected_source_projection(protected_root: str | Path) -> ProtectedSourceProjection:
    root = Path(protected_root).resolve()
    paths = tuple(root / name for name in PROTECTED_INPUT_NAMES)
    if any(not path.is_file() for path in paths):
        raise ProtectedProjectionError("protected input missing or invalid")
    loaded = [_records(path) for path in paths]
    query_records = loaded[0]
    query_keys = {"query_id", "query_identity", "eval_query_id", "id"}
    heldout: set[str] = set()
    for record in query_records:
        if _is_heldout(record):
            heldout.update(_scalar_strings(record, query_keys))
    # Locked query authorities may contain only held-out records and omit a split field.
    if not heldout and query_records:
        for record in query_records:
            heldout.update(_scalar_strings(record, query_keys))
    if not heldout:
        raise ProtectedProjectionError("held-out query identities unavailable")

    source_keys = {
        "source_artifact_id", "source_identity", "source_identity_id",
        "artifact_id", "raw_source_artifact_id",
    }
    video_keys = {
        "video_id", "source_video_id", "bvid", "source_id", "platform_video_id",
    }
    group_keys = {"leakage_group", "leakage_group_id", "source_leakage_group"}
    sources: set[str] = set()
    videos: set[str] = set()
    groups: set[str] = set()
    judgment_record_count = 0
    for file_records in loaded[1:]:
        for record in file_records:
            record_queries = _scalar_strings(record, query_keys)
            if record_queries & heldout:
                judgment_record_count += 1
                sources.update(_scalar_strings(record, source_keys))
                videos.update(_scalar_strings(record, video_keys))
                groups.update(_scalar_strings(record, group_keys))
    if judgment_record_count == 0 or (not sources and not videos):
        raise ProtectedProjectionError("protected source mapping unavailable")
    return ProtectedSourceProjection(
        heldout_query_identities=frozenset(heldout),
        source_identities=frozenset(sources),
        video_identities=frozenset(videos),
        leakage_groups=frozenset(groups),
        protected_input_file_count=len(paths),
        protected_record_count=sum(len(records) for records in loaded),
    )

