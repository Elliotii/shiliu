from __future__ import annotations

from typing import Any


GROUNDED_CURRENT_EVIDENCE_PROFILE_ID = "grounded_current_evidence"
GROUNDED_CURRENT_EVIDENCE_PROFILE_VERSION = "v5-a-product-profile-v1"


def grounded_current_evidence_profile() -> dict[str, Any]:
    """Return the immutable server-owned product success profile binding."""
    return {
        "profile_id": GROUNDED_CURRENT_EVIDENCE_PROFILE_ID,
        "profile_version": GROUNDED_CURRENT_EVIDENCE_PROFILE_VERSION,
        "authority": "server_product_composition",
        "objective_evaluator_kind": "grounded_answer",
        "required_current_evidence": 1,
    }


def is_grounded_current_evidence_profile(value: object) -> bool:
    return value == grounded_current_evidence_profile()
