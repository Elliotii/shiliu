from __future__ import annotations

import hashlib
import json
from typing import Any

EXCLUDED_HASH_FIELDS = frozenset({
    "started_at", "completed_at", "approved_at", "request_id", "provider_request_id",
    "process_id", "temporary_path", "authorization", "api_key",
})


def canonicalize(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: canonicalize(item) for key, item in sorted(value.items()) if key.lower() not in EXCLUDED_HASH_FIELDS}
    if isinstance(value, (list, tuple)):
        return [canonicalize(item) for item in value]
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(canonicalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def stable_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
