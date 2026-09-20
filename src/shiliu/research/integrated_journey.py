from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlencode


INTEGRATED_JOURNEY_POLICY_VERSION = "v5-c-stage5-integrated-journey-v1"


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


class IntegratedJourneyProjection:
    """Read-only composition of already-authoritative Stage 1-4 contexts."""

    @staticmethod
    def project(
        task_id: str,
        *,
        principal_id: str | None,
        enabled: bool,
        personalization: dict[str, Any],
        routing: dict[str, Any],
        assistance: dict[str, Any],
    ) -> dict[str, Any]:
        answer_reasons = [
            *personalization.get("reason_codes", []),
            *personalization.get("detail_reason_codes", []),
        ]
        answer_status = IntegratedJourneyProjection._answer_status(
            enabled=enabled,
            personalization=personalization,
            reasons=answer_reasons,
        )
        search_href = "/search?" + urlencode(
            {
                "corpus_task_id": task_id,
                "corpus_aware": "true" if enabled else "false",
            }
        )
        route_status = "disabled" if not enabled else str(routing.get("status") or "fail_closed")
        assistance_status = (
            "disabled" if not enabled else str(assistance.get("status") or "fail_closed")
        )
        steps = {
            "answer": {
                "status": answer_status,
                "context_hash": personalization.get("context_hash"),
                "href": "#research-answer",
                "reason_codes": answer_reasons,
            },
            "search": {
                "status": "explicit_query_required",
                "context_hash": None,
                "href": search_href,
                "reason_codes": ["search_not_run_explicit_query_required"],
            },
            "routing": {
                "status": route_status,
                "context_hash": routing.get("context_hash"),
                "href": "#research-routing",
                "reason_codes": routing.get("reason_codes", []),
            },
            "assistance": {
                "status": assistance_status,
                "context_hash": assistance.get("context_hash"),
                "href": "#research-assistance",
                "reason_codes": IntegratedJourneyProjection._assistance_reasons(
                    assistance
                ),
            },
        }
        identity = {
            "policy_version": INTEGRATED_JOURNEY_POLICY_VERSION,
            "task_id": task_id,
            "principal_id": principal_id,
            "enabled": bool(enabled),
            "steps": {
                name: {
                    "status": value["status"],
                    "context_hash": value["context_hash"],
                    "href": value["href"],
                }
                for name, value in steps.items()
            },
        }
        return {
            **identity,
            "steps": steps,
            "reason_codes": (
                [] if enabled else ["personalized_journey_disabled_for_session"]
            ),
            "journey_hash": _hash(identity),
            "authority": {
                "composition": "existing_stage_1_to_4_contexts_only",
                "truth_store": False,
                "execution": False,
                "citation_or_verifier": False,
                "telemetry_or_evaluation": False,
                "search_completed": False,
                "cross_consumer_fallback": False,
            },
            "side_effects": {
                "workspace_writes": 0,
                "search_requests": 0,
                "provider_calls": 0,
                "research_or_asr_tasks": 0,
                "artifact_routes_proceeded": 0,
            },
        }

    @staticmethod
    def _answer_status(
        *, enabled: bool, personalization: dict[str, Any], reasons: list[str]
    ) -> str:
        if not enabled or personalization.get("enabled") is not True:
            return "disabled"
        if any(
            "conflict_fail_closed" in reason
            or "malformed_or_unauthorized" in reason
            for reason in reasons
        ):
            return "fail_closed"
        if personalization.get("applied") or personalization.get("detail_applied"):
            return "treatment"
        return "baseline"

    @staticmethod
    def _assistance_reasons(assistance: dict[str, Any]) -> list[str]:
        reasons: list[str] = []
        for lane in assistance.get("lanes", {}).values():
            reasons.extend(lane.get("reason_codes", []))
        return list(dict.fromkeys(reasons))
