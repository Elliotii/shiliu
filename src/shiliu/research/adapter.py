from __future__ import annotations

import hashlib
import json
from typing import Any


class DeterministicEffectAdapter:
    """A no-network adapter used to prove the external-effect protocol."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute(
        self, *, effect_kind: str, idempotency_key: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        request = {
            "effect_kind": effect_kind,
            "idempotency_key": idempotency_key,
            "payload": payload,
        }
        self.calls.append(request)
        canonical = json.dumps(
            request,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return {
            "adapter": "deterministic_no_provider",
            "operation_id": f"deterministic:{digest[:24]}",
            "receipt_hash": digest,
            "result_reference": f"deterministic-result:{digest}",
        }
