from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from urllib.parse import urlencode

from shiliu.db import Database
from shiliu.research.errors import ResearchError
from shiliu.research.knowledge_reuse import ResearchArtifactRouteService
from shiliu.research.schema import PERSONAL_WORKSPACE_POLICY_VERSION


ROUTE_RECOMMENDATION_POLICY_VERSION = "v5-c-stage3-route-recommendation-v1"
ROUTING_PREFERENCE_KEY = "research.routing.default_path"
ROUTING_PATHS = {"fast", "deep", "research"}
EXPLICIT_PATHS = {"artifact_route", "fast", "deep", "research", "manual_asr"}
_ACTIVE_ASR_STATUSES = {"audio_downloading", "uploading", "submitted", "processing"}


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _decode(value: object, expected: type) -> Any:
    decoded = json.loads(str(value))
    if not isinstance(decoded, expected):
        raise ValueError("invalid persisted JSON shape")
    return decoded


def _normalized(value: object) -> str:
    return " ".join(str(value).casefold().split())


class RouteRecommendationProjection:
    """Read-only task-scoped advisory projection over real product capabilities."""

    def __init__(
        self,
        db: Database,
        *,
        artifact_routes: ResearchArtifactRouteService,
    ) -> None:
        self.db = db
        self.artifact_routes = artifact_routes

    def project(
        self,
        task_id: str,
        *,
        principal_id: str | None,
        enabled: bool,
        current_explicit_path: str | None,
        allow_provider_answer: bool,
        allow_high_cost_or_durable: bool,
        allow_manual_asr: bool,
        asr_video_id: int | None,
    ) -> dict[str, Any]:
        settings = {
            "current_explicit_path": current_explicit_path,
            "allow_provider_answer": bool(allow_provider_answer),
            "allow_high_cost_or_durable": bool(allow_high_cost_or_durable),
            "allow_manual_asr": bool(allow_manual_asr),
            "asr_video_id": asr_video_id,
        }
        if current_explicit_path not in EXPLICIT_PATHS | {None}:
            return self._outcome(
                task_id=task_id,
                enabled=enabled,
                status="fail_closed",
                reasons=["unknown_explicit_path"],
                settings=settings,
            )
        if not enabled:
            return self._outcome(
                task_id=task_id,
                enabled=False,
                status="disabled",
                reasons=["routing_personalization_disabled"],
                settings=settings,
            )
        if principal_id is None:
            return self._outcome(
                task_id=task_id,
                enabled=True,
                status="fail_closed",
                reasons=["principal_context_missing"],
                settings=settings,
            )

        try:
            task = self._task_context(task_id)
            preference, preference_reasons, preference_failed = self._preference(
                task_id, principal_id=principal_id
            )
            capabilities, artifact_failed = self._capabilities(
                task_id,
                allow_provider_answer=allow_provider_answer,
                allow_high_cost_or_durable=allow_high_cost_or_durable,
                allow_manual_asr=allow_manual_asr,
                asr_video_id=asr_video_id,
            )
        except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return self._outcome(
                task_id=task_id,
                enabled=True,
                status="fail_closed",
                reasons=["malformed_or_drifted_routing_context"],
                settings=settings,
            )

        if current_explicit_path is not None:
            return self._outcome(
                task_id=task_id,
                enabled=True,
                status="overridden",
                reasons=[
                    "explicit_path_preserved",
                    *preference_reasons,
                    *(
                        ["selected_artifact_context_unsafe"]
                        if artifact_failed and current_explicit_path == "artifact_route"
                        else []
                    ),
                ],
                settings=settings,
                task=task,
                preference=preference,
                capabilities=capabilities,
                explicit_choice_preserved=True,
            )
        if preference_failed:
            return self._outcome(
                task_id=task_id,
                enabled=True,
                status="fail_closed",
                reasons=preference_reasons,
                settings=settings,
                task=task,
                capabilities=capabilities,
            )
        if preference is None:
            return self._outcome(
                task_id=task_id,
                enabled=True,
                status="baseline",
                reasons=preference_reasons or ["no_confirmed_route_preference"],
                settings=settings,
                task=task,
                capabilities=capabilities,
            )
        if artifact_failed:
            return self._outcome(
                task_id=task_id,
                enabled=True,
                status="fail_closed",
                reasons=["artifact_route_authority_drift"],
                settings=settings,
                task=task,
                preference=preference,
                capabilities=capabilities,
            )
        if capabilities["artifact_route"].get("status") == "available":
            target, reasons = self._target(
                task=task,
                preferred_path=(str(preference["value"]) if preference else "research"),
                capabilities=capabilities,
                asr_video_id=None,
            )
            return self._outcome(
                task_id=task_id,
                enabled=True,
                status="recommended" if target is not None else "blocked",
                reasons=reasons,
                settings=settings,
                task=task,
                preference=preference,
                capabilities=capabilities,
                recommendation=target,
            )
        if (
            asr_video_id is not None
            and capabilities["manual_asr"].get("status") == "unsafe"
        ):
            return self._outcome(
                task_id=task_id,
                enabled=True,
                status="fail_closed",
                reasons=["manual_asr_context_unsafe"],
                settings=settings,
                task=task,
                preference=preference,
                capabilities=capabilities,
            )
        target, reasons = self._target(
            task=task,
            preferred_path=str(preference["value"]),
            capabilities=capabilities,
            asr_video_id=asr_video_id,
        )
        if target is None:
            return self._outcome(
                task_id=task_id,
                enabled=True,
                status="blocked",
                reasons=reasons,
                settings=settings,
                task=task,
                preference=preference,
                capabilities=capabilities,
            )
        return self._outcome(
            task_id=task_id,
            enabled=True,
            status="recommended",
            reasons=reasons,
            settings=settings,
            task=task,
            preference=preference,
            capabilities=capabilities,
            recommendation=target,
        )

    def _task_context(self, task_id: str) -> dict[str, Any]:
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT t.task_id, t.status, g.goal_id, g.revision, g.objective
                FROM research_tasks t
                JOIN research_goals g ON g.goal_id=t.active_goal_id
                WHERE t.task_id=?
                """,
                (task_id,),
            ).fetchone()
        if row is None:
            raise ValueError("routing Task does not exist")
        return {
            "task_id": str(row["task_id"]),
            "task_status": str(row["status"]),
            "goal_id": str(row["goal_id"]),
            "goal_revision": int(row["revision"]),
            "objective": str(row["objective"]),
        }

    def _preference(
        self, task_id: str, *, principal_id: str
    ) -> tuple[dict[str, Any] | None, list[str], bool]:
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT w.* FROM research_workspace_records w
                JOIN (
                    SELECT record_id, MAX(version) AS version
                    FROM research_workspace_records GROUP BY record_id
                ) latest ON latest.record_id=w.record_id AND latest.version=w.version
                WHERE w.command_task_id=? AND w.semantic_key=?
                ORDER BY w.record_id
                """,
                (task_id, ROUTING_PREFERENCE_KEY),
            ).fetchall()
        if not rows:
            return None, ["no_confirmed_route_preference"], False

        candidates: list[dict[str, Any]] = []
        reasons: list[str] = []
        for value in rows:
            row = dict(value)
            status = str(row["status"])
            if row["expires_at"] and status == "current":
                expires = datetime.fromisoformat(str(row["expires_at"]))
                if expires <= datetime.now(timezone.utc):
                    status = "expired"
            if status in {"candidate", "rejected", "expired", "tombstoned", "superseded", "invalidated"}:
                reasons.append(
                    "candidate_route_preference_not_confirmed"
                    if status == "candidate"
                    else "terminal_route_preference_not_applied"
                )
                continue
            if (
                row["record_kind"] != "explicit_memory"
                or row["authority_class"] != "user_authored"
                or status != "current"
                or row["principal_id"] != principal_id
                or row["policy_version"] != PERSONAL_WORKSPACE_POLICY_VERSION
            ):
                return None, ["unauthorized_route_preference"], True
            payload = _decode(row["payload_json"], dict)
            refs = _decode(row["source_refs_json"], list)
            if (
                set(payload) != {"key", "value"}
                or _normalized(payload["key"]) != ROUTING_PREFERENCE_KEY
                or not isinstance(payload["value"], str)
                or refs
                or row["source_boundary_hash"] != _hash(refs)
            ):
                return None, ["malformed_route_preference"], True
            preferred = _normalized(payload["value"])
            if preferred not in ROUTING_PATHS:
                return None, ["unknown_route_preference_value"], True
            expected_hash = _hash(
                {
                    "record_kind": row["record_kind"],
                    "authority_class": row["authority_class"],
                    "status": row["status"],
                    "semantic_key": row["semantic_key"],
                    "payload": payload,
                    "source_refs": refs,
                    "confidence": row["confidence"],
                    "expires_at": row["expires_at"],
                    "policy_version": row["policy_version"],
                }
            )
            if row["content_hash"] != expected_hash:
                return None, ["route_preference_content_drift"], True
            candidates.append(
                {
                    "record_id": str(row["record_id"]),
                    "record_revision_id": str(row["record_revision_id"]),
                    "version": int(row["version"]),
                    "content_hash": str(row["content_hash"]),
                    "authority_class": "user_authored",
                    "value": preferred,
                }
            )
        if not candidates:
            return None, list(dict.fromkeys(reasons)), False
        if len({value["value"] for value in candidates}) != 1:
            return None, ["confirmed_route_preference_conflict"], True
        selected = max(
            candidates,
            key=lambda value: (value["version"], value["record_revision_id"]),
        )
        return selected, ["confirmed_route_preference_available"], False

    def _capabilities(
        self,
        task_id: str,
        *,
        allow_provider_answer: bool,
        allow_high_cost_or_durable: bool,
        allow_manual_asr: bool,
        asr_video_id: int | None,
    ) -> tuple[dict[str, Any], bool]:
        artifact_failed = False
        try:
            artifact = self.artifact_routes.recommendation_assessment(task_id)
        except (ResearchError, AttributeError, KeyError, TypeError, ValueError) as exc:
            artifact_failed = True
            artifact = {
                "status": "unsafe",
                "reason": f"{type(exc).__name__}: {exc}"[:500],
            }
        capabilities: dict[str, Any] = {
            "artifact_route": artifact or {"status": "inapplicable"},
            "fast": {
                "status": "available" if allow_provider_answer else "permission_denied",
                "provider_call_on_recommendation": False,
            },
            "deep": {
                "status": (
                    "permission_denied"
                    if not allow_provider_answer
                    else "cost_denied"
                    if not allow_high_cost_or_durable
                    else "available"
                ),
                "provider_call_on_recommendation": False,
                "bounded_budget_preserved": True,
            },
            "research": {
                "status": "available" if allow_high_cost_or_durable else "cost_denied",
                "task_created_or_run": False,
            },
            "manual_asr": self._manual_asr(
                video_id=asr_video_id, allowed=allow_manual_asr
            ),
            "translation": {
                "status": "not_implemented",
                "reason": "not_a_distinct_route",
            },
        }
        return capabilities, artifact_failed

    def _manual_asr(self, *, video_id: int | None, allowed: bool) -> dict[str, Any]:
        if video_id is None:
            return {"status": "inapplicable", "reason": "no_exact_video_context"}
        with self.db.connect() as connection:
            video = connection.execute(
                "SELECT id, raw_subtitle_path FROM videos WHERE id=?", (video_id,)
            ).fetchone()
            job = connection.execute(
                "SELECT status, trigger_mode FROM asr_jobs WHERE video_id=?", (video_id,)
            ).fetchone()
        if video is None:
            return {"status": "unsafe", "reason": "exact_video_not_found"}
        if video["raw_subtitle_path"]:
            return {"status": "inapplicable", "reason": "current_transcript_available"}
        if job is not None and str(job["status"]) in _ACTIVE_ASR_STATUSES:
            return {
                "status": "inapplicable",
                "reason": "asr_job_already_active",
                "job_status": str(job["status"]),
            }
        return {
            "status": "available" if allowed else "permission_denied",
            "video_id": video_id,
            "manual_only": True,
            "credential_checked": False,
            "provider_call_on_recommendation": False,
            "job_created_on_recommendation": False,
        }

    @staticmethod
    def _target(
        *,
        task: dict[str, Any],
        preferred_path: str,
        capabilities: dict[str, Any],
        asr_video_id: int | None,
    ) -> tuple[dict[str, Any] | None, list[str]]:
        artifact = capabilities["artifact_route"]
        if artifact.get("status") == "available":
            route = artifact["recommended_route"]
            if route == "direct_reuse":
                return (
                    {
                        "path": "artifact_route",
                        "artifact_route": route,
                        "cta": {"kind": "focus_artifact_route"},
                    },
                    ["artifact_route_gate_precedes_profile"],
                )
            if capabilities["research"]["status"] != "available":
                return None, ["artifact_route_requires_durable_cost_permission"]
            return (
                {
                    "path": "research",
                    "artifact_route": route,
                    "cta": {"kind": "focus_research_controls"},
                },
                ["artifact_route_gate_precedes_profile"],
            )
        manual_asr = capabilities["manual_asr"]
        if asr_video_id is not None:
            if manual_asr["status"] != "available":
                return None, [f"manual_asr_{manual_asr['status']}"]
            return (
                {
                    "path": "manual_asr",
                    "then_path": preferred_path,
                    "video_id": asr_video_id,
                    "cta": {
                        "kind": "inspect_video_transcript",
                        "href": f"/videos/{asr_video_id}/transcript",
                    },
                },
                ["exact_video_manual_asr_prerequisite"],
            )
        capability = capabilities[preferred_path]
        if capability["status"] != "available":
            return None, [f"{preferred_path}_{capability['status']}"]
        if preferred_path in {"fast", "deep"}:
            href = "/ask?" + urlencode(
                {"q": task["objective"], "mode": preferred_path}
            )
            cta = {"kind": "prefill_ask", "href": href}
        else:
            cta = {"kind": "focus_research_controls"}
        return (
            {"path": preferred_path, "cta": cta},
            ["confirmed_default_path_recommended"],
        )

    @staticmethod
    def _outcome(
        *,
        task_id: str,
        enabled: bool,
        status: str,
        reasons: list[str],
        settings: dict[str, Any],
        task: dict[str, Any] | None = None,
        preference: dict[str, Any] | None = None,
        capabilities: dict[str, Any] | None = None,
        recommendation: dict[str, Any] | None = None,
        explicit_choice_preserved: bool = False,
    ) -> dict[str, Any]:
        identity = {
            "policy_version": ROUTE_RECOMMENDATION_POLICY_VERSION,
            "task_id": task_id,
            "enabled": bool(enabled),
            "status": status,
            "effect_scope": "advisory_panel_only",
            "task": task,
            "preference": preference,
            "settings": settings,
            "capabilities": capabilities or {},
            "recommendation": recommendation,
            "explicit_choice_preserved": explicit_choice_preserved,
            "reason_codes": list(dict.fromkeys(reasons)),
            "authority": {
                "preference": "recommendation_rationale_only",
                "explicit_choice_precedes_personalization": True,
                "artifact_route_gates_preserved": True,
                "execution_authority": False,
                "citation_authority": False,
                "verifier_authority": False,
                "fact_authority": False,
                "budget_authority": False,
                "permission_authority": False,
                "corpus_focus_candidate_experience_route_authority": False,
            },
            "side_effects": {
                "provider_calls": 0,
                "research_tasks_created_or_run": 0,
                "artifact_routes_proceeded": 0,
                "asr_jobs_or_posts": 0,
                "background_tasks": 0,
                "workspace_writes": 0,
            },
        }
        return {**identity, "context_hash": _hash(identity)}
