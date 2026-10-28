"""Stable source-row representation for existing WorkspaceSourceRef hashes.

Scope columns are target ownership, not part of the frozen source boundary.
Explicit JSON/time/bool conversion retains the source service's row payload.
"""
from datetime import datetime
from typing import Any, Mapping
import json
from shiliu.storage.dto import iso_time


def source_boundary_row(row: Mapping[str, Any], ref_type: str) -> dict[str, Any]:
    value={key:item for key,item in row.items() if key not in {
        "workspace_id","owner_user_id","insertion_seq",
    }}
    for key,item in value.items():
        if isinstance(item,datetime):
            value[key]=iso_time(item,timespec="seconds" if ref_type=="taxonomy_snapshot" else "microseconds")
        elif key.endswith("_json") and item is not None and not isinstance(item,str):
            value[key]=json.dumps(item,ensure_ascii=False,sort_keys=True,separators=(",",":"))
        elif isinstance(item,bool):
            value[key]=int(item)
    return value
