from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field


class LeakageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    split: str
    leakage_group: str
    query_family: str
    target_video_ids: tuple[str, ...]
    content_lineage_keys: tuple[str, ...] = ()
    uploader_series_keys: tuple[str, ...] = ()
    terminology_template_keys: tuple[str, ...] = ()
    evidence_region_keys: tuple[str, ...] = ()
    paraphrase_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class LeakageConflict:
    key_type: str
    key: str
    case_ids: tuple[str, ...]
    splits: tuple[str, ...]


def validate_split(records: Iterable[LeakageRecord]) -> tuple[LeakageConflict, ...]:
    indexes: dict[tuple[str, str], list[LeakageRecord]] = defaultdict(list)
    fields = ("leakage_group", "query_family", "target_video_ids", "content_lineage_keys",
              "uploader_series_keys", "terminology_template_keys", "evidence_region_keys", "paraphrase_keys")
    for record in records:
        for field in fields:
            value = getattr(record, field)
            for key in value if isinstance(value, tuple) else (value,):
                indexes[(field, key)].append(record)
    conflicts = []
    for (key_type, key), grouped in sorted(indexes.items()):
        splits = sorted({x.split for x in grouped})
        if len(splits) > 1:
            conflicts.append(LeakageConflict(key_type, key, tuple(sorted(x.case_id for x in grouped)), tuple(splits)))
    return tuple(conflicts)


def assert_leakage_safe(records: Iterable[LeakageRecord]) -> None:
    conflicts = validate_split(records)
    if conflicts:
        raise ValueError(f"cross-split leakage detected: {conflicts}")

