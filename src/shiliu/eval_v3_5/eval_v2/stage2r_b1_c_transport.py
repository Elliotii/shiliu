from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from .canary import payload_fingerprint
from .reviewer_registry import PRIMARY_REVIEWER
from .stage2r_b_runtime import ProviderInvocationError, RawInvocation, invoke_primary
from .transport_diagnosis import fixed_transport_fixture_payload


TRANSPORT_FIXTURE_CASE_ID = "NON_FORMAL_TRANSPORT_FIXTURE"
CALL_COUNT = 2


def verify_openai_transport(
    invoke: Callable[[object], RawInvocation] = invoke_primary,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Perform exactly two independent calls with one attempt each and no repair."""
    payload = fixed_transport_fixture_payload()
    fingerprint = payload_fingerprint(payload, PRIMARY_REVIEWER)
    calls: list[dict[str, object]] = []
    usage: list[dict[str, object]] = []
    for index in range(1, CALL_COUNT + 1):
        started = time.perf_counter()
        result: RawInvocation | None = None
        failure: ProviderInvocationError | None = None
        try:
            result = invoke(payload)
        except ProviderInvocationError as exc:
            failure = exc
        except Exception:
            failure = ProviderInvocationError(
                "sanitized unexpected fixture failure",
                code="provider_request_failed",
                retryable=False,
                failure_class="connection_or_sdk_failure",
            )
        elapsed = round((time.perf_counter() - started) * 1000)
        body_returned = result is not None
        call = {
            "call_index": index,
            "transport_attempt_count": 1,
            "retry_count": 0,
            "draft_repair_count": 0,
            "http_status": (
                failure.http_status
                if failure is not None and failure.http_status is not None
                else "unavailable"
            ),
            "safe_error_category": failure.failure_class if failure is not None else "none",
            "safe_provider_error_code": (
                failure.safe_provider_error_code if failure is not None else None
            ),
            "request_id": failure.request_id if failure is not None else None,
            "latency_ms": elapsed,
            "payload_fingerprint": fingerprint,
            "model_body_returned": body_returned,
            "response_model_echo": result.response_model if result is not None else None,
            "input_tokens": _available(result.input_tokens if result is not None else None),
            "output_tokens": _available(result.output_tokens if result is not None else None),
            "cached_tokens": _available(result.cached_tokens if result is not None else None),
        }
        calls.append(call)
        usage.append(
            {
                "provider": "openai",
                "case_id": TRANSPORT_FIXTURE_CASE_ID,
                "reviewer_role": "primary",
                "attempt_index": index,
                "attempt_type": "initial_draft" if body_returned else "transport",
                "selected_for_final": False,
                "http_status": call["http_status"],
                "model_body_returned": body_returned,
                "input_tokens": call["input_tokens"],
                "output_tokens": call["output_tokens"],
                "cached_tokens": call["cached_tokens"],
                "provider_latency_ms": _available(
                    result.latency_ms if result is not None else None
                ),
                "end_to_end_latency_ms": elapsed,
                "safe_error_category": call["safe_error_category"],
            }
        )
    bodies = sum(bool(call["model_body_returned"]) for call in calls)
    http_400_count = sum(call["http_status"] == 400 for call in calls)
    identical = len({str(call["payload_fingerprint"]) for call in calls}) == 1
    summary = {
        "fixture": "non_formal_transport_fixture",
        "not_master_case": True,
        "not_gold": True,
        "provider": "openai",
        "model": PRIMARY_REVIEWER.model,
        "reasoning_effort": PRIMARY_REVIEWER.reasoning_effort,
        "call_count": len(calls),
        "attempts_per_call": [call["transport_attempt_count"] for call in calls],
        "model_body_count": bodies,
        "http_400_count": http_400_count,
        "payload_fingerprints_identical": identical,
        "payload_fingerprint": fingerprint,
        "calls": calls,
        "openai_transport_fix_verified": bool(
            len(calls) == 2 and bodies == 2 and http_400_count == 0 and identical
        ),
        "request_payload_persisted": False,
        "raw_error_body_persisted": False,
        "base_url_persisted": False,
    }
    return summary, usage


def persist_transport_verification(
    output_root: Path,
    summary: dict[str, object],
    usage: list[dict[str, object]],
) -> None:
    output_root.mkdir(parents=True, exist_ok=False)
    (output_root / "openai_transport_verification.safe.json").write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_root / "provider_attempt_usage.jsonl").write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in usage
        ),
        encoding="utf-8",
    )


def _available(value: int | None) -> int | str:
    return value if value is not None else "unavailable"
