from __future__ import annotations

import hashlib
import json
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from shiliu.db import Database
from shiliu.research.contracts import AttemptCause
from shiliu.research.control_contracts import CreateInputRequest
from shiliu.research.control_service import ResearchControlService
from shiliu.research.errors import (
    ResearchConflict,
    ResearchError,
    ResearchUnsafeState,
    SimulatedCrash,
)
from shiliu.research.inner_contracts import ContinueInnerResearchRequest
from shiliu.research.inner_service import InnerResearchService
from shiliu.research.outer_contracts import AdvanceOuterResearchRequest
from shiliu.research.outer_service import OuterResearchService
from shiliu.research.product_contracts import (
    CreateProductResearchRequest,
    RunProductResearchRequest,
)
from shiliu.research.product_policy import (
    GROUNDED_CURRENT_EVIDENCE_PROFILE_ID,
    GROUNDED_CURRENT_EVIDENCE_PROFILE_VERSION,
    grounded_current_evidence_profile,
    is_grounded_current_evidence_profile,
)
from shiliu.research.schema import (
    INNER_RESEARCH_STATE_SCHEMA_VERSION,
    OUTER_STATE_SCHEMA_VERSION,
)
from shiliu.research.service import ResearchTaskService
from shiliu.retrieval.product_search import build_bilibili_jump_url


FaultInjector = Callable[[str], None]
CANDIDATE_DELTA_SCHEMA_VERSION = "v5-a-stage5-candidate-delta-v1"
PRODUCT_PROJECTION_SCHEMA_VERSION = "v5-a-stage5-product-projection-v1"
PRODUCT_RUNNER_SCHEMA_VERSION = "v5-a-stage5-local-runner-v1"
DELTA_KINDS = (
    "KnowledgeDelta",
    "CorpusDelta",
    "UserModelDelta",
    "SystemExperienceDelta",
)
UNSUPPORTED_EVALUATOR_PROMPT = (
    "当前自然语言目标或成功约束没有匹配的服务器确定性 evaluator。"
    "请改写目标，或选择产品支持的‘当前证据支撑回答’策略；"
    "未注册的自由文本成功约束不会被静默降级。"
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _parse_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _bounded_text(value: object, limit: int = 500) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _derived_command(parent: str, kind: str, *parts: object) -> str:
    digest = _hash({"parent": parent, "kind": kind, "parts": list(parts)})[:32]
    return f"stage5:{kind}:{digest}"


class ResearchProductService:
    """User-facing durable projection and bounded no-provider task runner."""

    MAX_LIST_TASKS = 50
    MAX_TRACE_EVENTS = 100
    MAX_ADVANCED_ROWS = 40
    MAX_DELTA_ITEMS = 8
    LEASE_SECONDS = 600
    LEASE_RENEW_EVERY = 4

    STATUS_LABELS = {
        "ready": "等待开始",
        "running": "正在研究",
        "waiting_user": "等待你的输入",
        "blocked": "已安全暂停",
        "terminal": "本任务已结束",
    }
    TERMINATION_LABELS = {
        "answer_ready": "已有可用答案并完成本次目标审计",
        "budget_exhausted": "达到本次研究的安全预算上限",
        "no_new_evidence": "继续研究没有发现新的有效证据",
        "repeated_action": "后续动作开始重复",
        "evidence_unavailable": "所需的当前证据不可用",
        "needs_user_input": "需要用户补充或决定",
        "cancelled": "任务已由用户取消",
        "goal_revised": "目标已由用户修订",
        "external_side_effect_unknown": "外部副作用结果未知，禁止自动重放",
        "provider_error": "Provider 执行失败",
        "implementation_error": "内部实现错误已持久记录",
        "targeted_continuation": "已创建有明确目标的后续 Attempt",
        "constraint_unsatisfied": "成功约束尚未满足",
    }
    EVENT_LABELS = {
        "task_created": "创建持久 Research Task",
        "owner_claimed": "本地 runner 取得有界执行权",
        "owner_renewed": "runner 续租执行权",
        "attempt_started": "开始新的研究 Attempt",
        "inner_action_committed": "完成一项 inner research 动作",
        "inner_action_failed": "inner research 动作失败并已记录",
        "outer_audit_committed": "完成 Outer Goal Audit",
        "outer_targeted_continuation_committed": "提交定向后续研究",
        "input_request_opened": "等待用户补充输入",
        "human_decision_applied": "应用当前用户决定",
        "control_interrupt_applied": "研究已被安全中断",
        "control_resume_applied": "沿当前暂停 lineage 恢复",
        "control_cancel_applied": "处理取消请求",
        "candidate_deltas_materialized": "记录四类 Candidate Delta",
        "product_runner_boundary": "本地 runner 到达持久边界",
        "provider_call_reserved": "为一次 Provider 调用预留预算与幂等身份",
        "provider_call_in_flight": "Provider 调用已进入不可自动重放区间",
        "provider_call_receipted": "Provider 调用已绑定真实回执与费用",
        "provider_product_boundary": "真实 Provider 产品编排到达持久边界",
        "duplicate_input_request_suppressed": "同一 evaluator 能力缺口不再重复提问",
    }
    SAFE_EVENT_KEYS = {
        "action_id",
        "action_kind",
        "phase",
        "new_evidence_count",
        "artifact_id",
        "stop_reason",
        "answer_status",
        "termination_reason",
        "failure_class",
        "audit_id",
        "decision",
        "result_id",
        "child_attempt_id",
        "seed_id",
        "input_request_id",
        "decision_id",
        "decision_kind",
        "control_generation",
        "outcome",
        "delta_snapshot_id",
        "boundary",
        "provider_cycles",
        "provider_artifact_id",
    }

    def __init__(
        self,
        *,
        db: Database,
        kernel: ResearchTaskService,
        inner: InnerResearchService,
        outer: OuterResearchService,
        control: ResearchControlService,
        principal_id: str = "local_operator",
        runner_id: str | None = None,
        fault_injector: FaultInjector | None = None,
    ) -> None:
        self.db = db
        self.kernel = kernel
        self.inner = inner
        self.outer = outer
        self.control = control
        self.principal_id = principal_id
        self.runner_id = runner_id or f"stage5-local-{uuid.uuid4().hex}"
        self.fault_injector = fault_injector or (lambda _point: None)
        self._locks_guard = threading.Lock()
        self._run_locks: dict[str, threading.Lock] = {}

    def _run_lock(self, task_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._run_locks.setdefault(task_id, threading.Lock())

    def create_task(self, request: CreateProductResearchRequest) -> dict[str, Any]:
        request = CreateProductResearchRequest.model_validate(
            request.model_dump(mode="json")
        )
        return self.kernel.create_task(
            command_id=request.command_id,
            objective=request.objective,
            success_constraints=request.success_constraints,
            evidence_policy={
                "authority": "live_current_exact_replay",
                "product_execution": "deterministic_no_provider",
                "constraint_profile": request.constraint_profile,
            },
            _server_constraint_profile=grounded_current_evidence_profile(),
        )

    def list_tasks(self, *, limit: int = 20) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), self.MAX_LIST_TASKS))
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT t.*, g.objective, g.revision, r.answer_status,
                       r.termination_reason, r.failure_class
                FROM research_tasks t
                JOIN research_goals g ON g.goal_id=t.active_goal_id
                LEFT JOIN research_results r ON r.result_id=t.terminal_result_id
                ORDER BY t.updated_at DESC, t.task_id DESC LIMIT ?
                """,
                (bounded,),
            ).fetchall()
        return [
            {
                "task_id": str(row["task_id"]),
                "parent_task_id": row["parent_task_id"],
                "objective": _bounded_text(row["objective"], 240),
                "goal_revision": int(row["revision"]),
                "status": str(row["status"]),
                "status_label": self.STATUS_LABELS.get(
                    str(row["status"]), str(row["status"])
                ),
                "answer_status": row["answer_status"],
                "termination_reason": row["termination_reason"],
                "failure_class": row["failure_class"],
                "updated_at": str(row["updated_at"]),
                "href": f"/research/{row['task_id']}",
            }
            for row in rows
        ]

    def get_task(self, task_id: str) -> dict[str, Any]:
        # Stage 4 status reconciliation may append an expired-input disposition.
        control = self.control.get_status(task_id)
        if str(control["task"]["status"]) in {"blocked", "waiting_user", "terminal"}:
            self.ensure_candidate_deltas(task_id)
            control = self.control.get_status(task_id)
        raw = self.kernel.get_task(task_id)
        inner = self.inner.get_inner_state(task_id)
        outer = self.outer.get_outer_state(task_id)
        return self._project(raw=raw, inner=inner, outer=outer, control=control)

    def _project(
        self,
        *,
        raw: dict[str, Any],
        inner: dict[str, Any],
        outer: dict[str, Any],
        control: dict[str, Any],
    ) -> dict[str, Any]:
        task = raw["task"]
        task_id = str(task["task_id"])
        active_goal = next(
            (
                goal
                for goal in reversed(raw["goals"])
                if goal["goal_id"] == task["active_goal_id"]
            ),
            raw["goals"][-1],
        )
        active_attempt = next(
            (
                attempt
                for attempt in reversed(raw["attempts"])
                if attempt["status"] != "terminal"
            ),
            raw["attempts"][-1] if raw["attempts"] else None,
        )
        latest_checkpoint = next(
            (
                checkpoint
                for checkpoint in reversed(raw["checkpoints"])
                if active_attempt is not None
                and checkpoint["attempt_id"] == active_attempt["attempt_id"]
            ),
            raw["checkpoints"][-1] if raw["checkpoints"] else None,
        )
        result = next(
            (
                value
                for value in reversed(raw["results"])
                if (
                    str(task["status"]) == "terminal"
                    and value["result_id"] == task["terminal_result_id"]
                )
                or (
                    str(task["status"]) != "terminal"
                    and active_attempt is not None
                    and value.get("attempt_id") == active_attempt["attempt_id"]
                )
            ),
            None,
        )
        artifact = next(
            (
                value
                for value in reversed(raw["provisional_artifacts"])
                if active_attempt is not None
                and value["attempt_id"] == active_attempt["attempt_id"]
            ),
            raw["provisional_artifacts"][-1]
            if str(task["status"]) == "terminal" and raw["provisional_artifacts"]
            else None,
        )
        phase_state = (
            dict(latest_checkpoint["state_payload"])
            if latest_checkpoint is not None
            else {"phase": "pending"}
        )
        answer_status = (
            result.get("answer_status")
            if result
            else artifact.get("answer_status")
            if artifact
            else phase_state.get("answer_status")
            if phase_state
            else "not_produced"
        )
        termination_reason = (
            result.get("termination_reason")
            if result
            else phase_state.get("termination_reason")
            if phase_state
            else None
        )
        failure_class = (
            result.get("failure_class")
            if result
            else phase_state.get("failure_class")
            if phase_state
            else "none"
        )
        allowed = set(control["allowed_operations"])
        if self._runner_is_available(task_id, task):
            allowed.add("run")
        if str(task["status"]) == "terminal":
            allowed.add("retry")
        citations = self._citations(
            task_id,
            str(active_attempt["attempt_id"]) if active_attempt is not None else None,
        )
        deltas = self._latest_deltas(raw["events"])
        if deltas is not None:
            deltas = {
                **deltas,
                "is_current_boundary": (
                    deltas.get("boundary", {}).get("state_version")
                    == int(task["state_version"])
                    and deltas.get("boundary", {}).get("status")
                    == str(task["status"])
                ),
            }
        return {
            "projection_schema_version": PRODUCT_PROJECTION_SCHEMA_VERSION,
            "task": {
                "task_id": task_id,
                "parent_task_id": task.get("parent_task_id"),
                "status": str(task["status"]),
                "status_label": self.STATUS_LABELS.get(
                    str(task["status"]), str(task["status"])
                ),
                "state_version": int(task["state_version"]),
                "control_generation": int(task.get("control_generation") or 0),
                "updated_at": str(task["updated_at"]),
            },
            "goal": {
                "goal_id": str(active_goal["goal_id"]),
                "revision": int(active_goal["revision"]),
                "objective": str(active_goal["objective"]),
                "success_constraints": list(active_goal["success_constraints"]),
            },
            "constraint_policy": self._constraint_policy_projection(
                raw=raw, outer=outer, active_goal=active_goal
            ),
            "attempt": self._attempt_summary(active_attempt),
            "checkpoint": self._checkpoint_summary(latest_checkpoint),
            "state": {
                "phase": phase_state.get("phase") if phase_state else None,
                "budget": phase_state.get("budget") if phase_state else None,
                "answer_status": answer_status,
                "termination_reason": termination_reason,
                "termination_label": self.TERMINATION_LABELS.get(
                    str(termination_reason), str(termination_reason or "尚未停止")
                ),
                "failure_class": failure_class,
                "reason_detail": result.get("reason_detail") if result else None,
                "stop_reason": phase_state.get("stop_reason") if phase_state else None,
                "blocker": phase_state.get("blocker") if phase_state else None,
            },
            "result": self._result_summary(result),
            "artifact": self._artifact_summary(artifact),
            "answer_blocks": list(artifact.get("answer_blocks", [])) if artifact else [],
            "limitations": list(artifact.get("limitations", [])) if artifact else [],
            "citations": citations,
            "control": {
                "allowed_operations": sorted(allowed),
                "open_input_requests": [
                    self._input_summary(value)
                    for value in control["open_input_requests"]
                ],
                "unresolved_side_effects": [
                    {
                        key: effect.get(key)
                        for key in (
                            "side_effect_id",
                            "attempt_id",
                            "effect_kind",
                            "status",
                            "created_at",
                            "updated_at",
                        )
                    }
                    for effect in raw["side_effects"]
                    if effect["status"] in {"in_flight", "unknown"}
                ],
                "action_context": {
                    "expected_state_version": int(task["state_version"]),
                    "expected_checkpoint_id": (
                        latest_checkpoint["checkpoint_id"] if latest_checkpoint else None
                    ),
                    "expected_control_generation": int(
                        task.get("control_generation") or 0
                    ),
                    "attempt_id": active_attempt["attempt_id"] if active_attempt else None,
                },
                "derivations": [
                    {
                        key: value.get(key)
                        for key in (
                            "derivation_id",
                            "derivation_kind",
                            "source_task_id",
                            "source_checkpoint_id",
                            "child_task_id",
                            "created_at",
                        )
                    }
                    for value in control["derivations"][-self.MAX_ADVANCED_ROWS :]
                ],
            },
            "candidate_deltas": deltas,
            "trace": self._trace_projection(raw, control),
            "provider_status": "not_exercised",
        }

    @staticmethod
    def _constraint_policy_projection(
        *,
        raw: dict[str, Any],
        outer: dict[str, Any],
        active_goal: dict[str, Any],
    ) -> dict[str, Any]:
        created = next(
            (
                event
                for event in raw["events"]
                if event["event_type"] == "task_created"
            ),
            None,
        )
        profile = (
            dict(created.get("payload", {}).get("server_constraint_profile") or {})
            if created is not None
            else {}
        )
        profile_selected = is_grounded_current_evidence_profile(profile)
        trusted = profile_selected and not active_goal["success_constraints"]
        current_specs = {
            (str(value["constraint_scope"]), str(value["normalized_text"])): value
            for value in outer["constraint_specs"]
            if value["goal_id"] == active_goal["goal_id"]
        }
        semantic_constraints = []
        for text in active_goal["success_constraints"]:
            normalized = " ".join(str(text).casefold().split())
            spec = current_specs.get(("success_constraint", normalized))
            authority = (
                (spec or {}).get("evaluator_policy", {}).get("authority")
                if spec is not None
                else "unregistered_natural_language"
            )
            semantic_constraints.append(
                {
                    "text": str(text),
                    "verification": (
                        "server_registered_deterministic"
                        if authority == "server_registry"
                        else "requires_supported_rewrite_or_registered_evaluator"
                    ),
                    "machine_verifiable": authority == "server_registry",
                }
            )
        return {
            "profile_id": (
                GROUNDED_CURRENT_EVIDENCE_PROFILE_ID if profile_selected else None
            ),
            "profile_version": (
                GROUNDED_CURRENT_EVIDENCE_PROFILE_VERSION
                if profile_selected
                else None
            ),
            "authority": (
                "server_product_composition" if profile_selected else "none"
            ),
            "objective_verification": (
                "grounded_answer_with_current_evidence"
                if trusted
                else "strict_semantic_constraints_require_registered_evaluator"
                if profile_selected
                else "requires_registered_evaluator"
            ),
            "objective_machine_verifiable": trusted,
            "semantic_constraints": semantic_constraints,
            "unsupported_constraints_are_required": True,
        }

    @staticmethod
    def _checkpoint_summary(checkpoint: dict[str, Any] | None) -> dict[str, Any] | None:
        if checkpoint is None:
            return None
        return {
            key: checkpoint[key]
            for key in (
                "checkpoint_id",
                "attempt_id",
                "parent_checkpoint_id",
                "sequence",
                "state_schema_version",
                "is_complete",
                "created_at",
            )
        }

    @staticmethod
    def _attempt_summary(attempt: dict[str, Any] | None) -> dict[str, Any] | None:
        if attempt is None:
            return None
        return {
            key: attempt.get(key)
            for key in (
                "attempt_id",
                "goal_id",
                "ordinal",
                "cause",
                "parent_attempt_id",
                "source_checkpoint_id",
                "status",
                "result_id",
                "started_at",
                "ended_at",
            )
        }

    @staticmethod
    def _result_summary(result: dict[str, Any] | None) -> dict[str, Any] | None:
        if result is None:
            return None
        return {
            key: result.get(key)
            for key in (
                "result_id",
                "attempt_id",
                "checkpoint_id",
                "answer_status",
                "termination_reason",
                "failure_class",
                "reason_detail",
                "is_task_terminal",
                "created_at",
            )
        }

    @staticmethod
    def _artifact_summary(artifact: dict[str, Any] | None) -> dict[str, Any] | None:
        if artifact is None:
            return None
        return {
            key: artifact.get(key)
            for key in (
                "artifact_id",
                "attempt_id",
                "checkpoint_id",
                "answer_status",
                "artifact_hash",
                "created_at",
            )
        }

    @staticmethod
    def _input_summary(value: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value.get(key)
            for key in (
                "input_request_id",
                "attempt_id",
                "source_checkpoint_id",
                "request_kind",
                "prompt",
                "choices",
                "response_schema",
                "constraint_id",
                "expires_at",
                "created_at",
                "current_status",
            )
        }

    def _runner_is_available(self, task_id: str, task: dict[str, Any]) -> bool:
        if str(task["status"]) not in {"ready", "running"}:
            return False
        lock = self._run_lock(task_id)
        if lock.locked():
            return False
        owner_id = str(task.get("owner_id") or "")
        if not owner_id or owner_id == self.runner_id:
            return True
        lease = _parse_time(task.get("lease_until"))
        return lease is None or lease <= datetime.now(timezone.utc)

    def _citations(
        self, task_id: str, attempt_id: str | None
    ) -> list[dict[str, Any]]:
        if attempt_id is None:
            return []
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT eu.evidence_use_id, eu.evidence_id, eu.attempt_id,
                       ei.citation_identity_version, ei.video_id,
                       ei.source_artifact_id, ei.source_version,
                       ei.timeline_run_id, ei.start_time, ei.end_time,
                       ei.quote_preview, v.source_id, v.title, v.video_url,
                       v.subtitle_source,
                       (SELECT ev.outcome FROM research_evidence_validations ev
                        WHERE ev.evidence_use_id=eu.evidence_use_id
                        ORDER BY ev.observed_at DESC, ev.observation_id DESC LIMIT 1)
                       AS currentness
                FROM research_evidence_uses eu
                JOIN research_evidence_identities ei ON ei.evidence_id=eu.evidence_id
                JOIN videos v ON v.id=ei.video_id
                WHERE eu.task_id=? AND eu.attempt_id=?
                ORDER BY eu.created_at, eu.evidence_use_id LIMIT 48
                """,
                (task_id, attempt_id),
            ).fetchall()
        citations: list[dict[str, Any]] = []
        for row in rows:
            source = str(row["subtitle_source"] or "unknown").casefold()
            source_type = (
                "human"
                if source in {"human", "official"}
                else "asr"
                if "asr" in source
                else "ai"
                if source in {"ai", "generated"}
                else "unknown"
            )
            citations.append(
                {
                    "citation_id": str(row["evidence_id"]),
                    "evidence_use_id": str(row["evidence_use_id"]),
                    "attempt_id": str(row["attempt_id"]),
                    "citation_identity_version": str(
                        row["citation_identity_version"]
                    ),
                    "video_id": int(row["video_id"]),
                    "title": str(row["title"]),
                    "source_type": source_type,
                    "source_artifact_id": str(row["source_artifact_id"]),
                    "source_version": str(row["source_version"]),
                    "timeline_run_id": str(row["timeline_run_id"]),
                    "start_time": float(row["start_time"]),
                    "end_time": float(row["end_time"]),
                    "quote_text": _bounded_text(row["quote_preview"], 1000),
                    "jump_url": build_bilibili_jump_url(
                        str(row["video_url"] or ""),
                        str(row["source_id"]),
                        float(row["start_time"]),
                    ),
                    "currentness": str(row["currentness"] or "unknown"),
                }
            )
        return citations

    def _trace_projection(
        self, raw: dict[str, Any], control: dict[str, Any]
    ) -> dict[str, Any]:
        events = raw["events"][-self.MAX_TRACE_EVENTS :]
        timeline = []
        for event in events:
            payload = event.get("payload") or {}
            safe = {
                key: value
                for key, value in payload.items()
                if key in self.SAFE_EVENT_KEYS
                and isinstance(value, (str, int, float, bool, type(None)))
            }
            timeline.append(
                {
                    "event_id": event["event_id"],
                    "sequence": int(event["sequence"]),
                    "event_type": event["event_type"],
                    "summary": self.EVENT_LABELS.get(
                        event["event_type"], str(event["event_type"])
                    ),
                    "attempt_id": event.get("attempt_id"),
                    "checkpoint_id": event.get("checkpoint_id"),
                    "details": safe,
                    "created_at": event["created_at"],
                }
            )
        return {
            "timeline": timeline,
            "counts": {
                "events": len(raw["events"]),
                "checkpoints": len(raw["checkpoints"]),
                "actions": len(raw["inner_actions"]),
                "audits": len(raw["outer_audits"]),
                "receipts": len(raw["command_receipts"]),
                "controls": len(control["control_requests"]),
            },
            "checkpoints": [
                self._checkpoint_summary(value)
                for value in raw["checkpoints"][-self.MAX_ADVANCED_ROWS :]
            ],
            "actions": [
                {
                    key: value.get(key)
                    for key in (
                        "action_id",
                        "attempt_id",
                        "action_kind",
                        "status",
                        "error_code",
                        "created_at",
                        "completed_at",
                    )
                }
                for value in raw["inner_actions"][-self.MAX_ADVANCED_ROWS :]
            ],
            "audits": [
                {
                    key: value.get(key)
                    for key in (
                        "audit_id",
                        "attempt_id",
                        "outcome",
                        "blocker",
                        "created_at",
                    )
                }
                for value in raw["outer_audits"][-self.MAX_ADVANCED_ROWS :]
            ],
            "receipts": [
                {
                    key: value.get(key)
                    for key in (
                        "receipt_id",
                        "command_type",
                        "status",
                        "outcome_reference",
                        "created_at",
                    )
                }
                for value in raw["command_receipts"][-self.MAX_ADVANCED_ROWS :]
            ],
            "controls": [
                {
                    key: value.get(key)
                    for key in (
                        "control_request_id",
                        "request_kind",
                        "principal_id",
                        "admitted_control_generation",
                        "created_at",
                    )
                }
                for value in control["control_requests"][-self.MAX_ADVANCED_ROWS :]
            ],
        }

    @staticmethod
    def _latest_deltas(events: list[dict[str, Any]]) -> dict[str, Any] | None:
        for event in reversed(events):
            if event["event_type"] == "candidate_deltas_materialized":
                return event.get("payload")
        return None

    def ensure_candidate_deltas(self, task_id: str) -> dict[str, Any] | None:
        with self.kernel._transaction() as connection:
            task = self.kernel._task(connection, task_id)
            if str(task["status"]) not in {"blocked", "waiting_user", "terminal"}:
                return None
            attempt = connection.execute(
                "SELECT * FROM research_attempts WHERE task_id=? "
                "ORDER BY ordinal DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            checkpoint = connection.execute(
                "SELECT * FROM research_checkpoints WHERE task_id=? "
                "ORDER BY created_at DESC, sequence DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            result = (
                connection.execute(
                    "SELECT * FROM research_results WHERE result_id=?",
                    (str(task["terminal_result_id"]),),
                ).fetchone()
                if task["terminal_result_id"] is not None
                else connection.execute(
                    "SELECT * FROM research_results WHERE task_id=? AND attempt_id=? "
                    "ORDER BY created_at DESC, result_id DESC LIMIT 1",
                    (task_id, str(attempt["attempt_id"]) if attempt else ""),
                ).fetchone()
            )
            artifact = connection.execute(
                "SELECT * FROM research_provisional_artifacts "
                "WHERE task_id=? AND attempt_id=? "
                "ORDER BY created_at DESC, artifact_id DESC LIMIT 1",
                (task_id, str(attempt["attempt_id"]) if attempt else ""),
            ).fetchone()
            boundary = {
                "task_id": task_id,
                "status": str(task["status"]),
                "state_version": int(task["state_version"]),
                "goal_id": str(task["active_goal_id"]),
                "attempt_id": str(attempt["attempt_id"]) if attempt else None,
                "checkpoint_id": str(checkpoint["checkpoint_id"]) if checkpoint else None,
                "result_id": str(result["result_id"]) if result else None,
                "artifact_id": str(artifact["artifact_id"]) if artifact else None,
            }
            boundary_hash = _hash(boundary)
            command_id = f"stage5:deltas:{boundary_hash[:32]}"
            payload_hash = _hash(
                {"operation": "materialize_candidate_deltas", **boundary}
            )
            existing = self.kernel._existing_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                payload_hash=payload_hash,
            )
            if existing is not None:
                return {**existing, "deduplicated": True}
            payload = self._candidate_payload(
                connection=connection,
                task=task,
                attempt=attempt,
                checkpoint=checkpoint,
                result=result,
                artifact=artifact,
                boundary=boundary,
                boundary_hash=boundary_hash,
            )
            now = _now()
            event_id = self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(task["active_goal_id"]),
                attempt_id=boundary["attempt_id"],
                checkpoint_id=boundary["checkpoint_id"],
                event_type="candidate_deltas_materialized",
                payload=payload,
                command_id=command_id,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            self.fault_injector("after_candidate_delta_event")
            response = {
                "task_id": task_id,
                "delta_snapshot_id": payload["delta_snapshot_id"],
                "event_id": event_id,
                "boundary_hash": boundary_hash,
            }
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                command_type="materialize_candidate_deltas",
                payload_hash=payload_hash,
                outcome_reference=event_id,
                response=response,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            self.fault_injector("after_candidate_delta_receipt")
        return {**response, "deduplicated": False}

    def _candidate_payload(
        self,
        *,
        connection,
        task,
        attempt,
        checkpoint,
        result,
        artifact,
        boundary: dict[str, Any],
        boundary_hash: str,
    ) -> dict[str, Any]:
        event_ids = [
            str(row[0])
            for row in connection.execute(
                "SELECT event_id FROM research_events WHERE task_id=? "
                "ORDER BY sequence DESC LIMIT 12",
                (boundary["task_id"],),
            ).fetchall()
        ]
        evidence_use_ids = [
            str(row[0])
            for row in connection.execute(
                "SELECT evidence_use_id FROM research_evidence_uses "
                "WHERE task_id=? AND attempt_id=? "
                "ORDER BY created_at, evidence_use_id LIMIT 24",
                (boundary["task_id"], boundary["attempt_id"]),
            ).fetchall()
        ]
        blocks = json.loads(str(artifact["answer_blocks_json"])) if artifact else []
        knowledge_items = [
            {
                "summary": _bounded_text(block.get("text"), 500),
                "citation_ids": list(block.get("citation_ids", []))[:8],
            }
            for block in blocks[: self.MAX_DELTA_ITEMS]
            if _bounded_text(block.get("text"), 500)
        ]
        validation_rows = connection.execute(
            """
            SELECT ev.* FROM research_evidence_validations ev
            JOIN (
                SELECT evidence_use_id, MAX(observed_at) AS observed_at
                FROM research_evidence_validations WHERE task_id=?
                GROUP BY evidence_use_id
            ) latest ON latest.evidence_use_id=ev.evidence_use_id
                    AND latest.observed_at=ev.observed_at
            WHERE ev.task_id=? AND ev.outcome IN ('stale','missing','invalid','error')
            ORDER BY ev.observed_at DESC LIMIT ?
            """,
            (boundary["task_id"], boundary["task_id"], self.MAX_DELTA_ITEMS),
        ).fetchall()
        corpus_items = [
            {
                "operation": "review_evidence_source",
                "evidence_use_id": str(row["evidence_use_id"]),
                "observation_id": str(row["observation_id"]),
                "outcome": str(row["outcome"]),
                "reason_code": _bounded_text(row["reason_code"], 160),
            }
            for row in validation_rows
        ]
        decisions = connection.execute(
            "SELECT decision_id, decision_kind FROM research_human_decisions "
            "WHERE task_id=? ORDER BY created_at DESC LIMIT ?",
            (boundary["task_id"], self.MAX_DELTA_ITEMS),
        ).fetchall()
        user_items = [
            {
                "decision_id": str(row["decision_id"]),
                "decision_kind": str(row["decision_kind"]),
                "summary": "本 Task 存在显式用户决定，候选仅供后续独立审查",
            }
            for row in decisions
        ]
        termination = str(result["termination_reason"]) if result else None
        failure = str(result["failure_class"]) if result else "none"
        system_items = []
        if termination and termination != "answer_ready":
            system_items.append(
                {
                    "termination_reason": termination,
                    "failure_class": failure,
                    "summary": _bounded_text(
                        result["reason_detail"] if result else termination, 500
                    ),
                }
            )
        deltas = []
        values = {
            "KnowledgeDelta": (
                knowledge_items,
                "no_grounded_answer_block_at_this_boundary",
            ),
            "CorpusDelta": (corpus_items, "no_bounded_corpus_delta_observed"),
            "UserModelDelta": (user_items, "no_explicit_user_decision_in_task"),
            "SystemExperienceDelta": (
                system_items,
                "no_bounded_system_experience_delta_observed",
            ),
        }
        for kind in DELTA_KINDS:
            items, empty_reason = values[kind]
            delta = {
                "delta_kind": kind,
                "items": items[: self.MAX_DELTA_ITEMS],
                "empty_reason": None if items else empty_reason,
                "promotion_status": "candidate_only_not_promoted",
            }
            delta["candidate_hash"] = _hash(
                {"boundary_hash": boundary_hash, **delta}
            )
            deltas.append(delta)
        snapshot = {
            "candidate_delta_schema_version": CANDIDATE_DELTA_SCHEMA_VERSION,
            "task_id": boundary["task_id"],
            "goal_id": boundary["goal_id"],
            "attempt_id": boundary["attempt_id"],
            "result_id": boundary["result_id"],
            "checkpoint_id": boundary["checkpoint_id"],
            "boundary": {key: boundary[key] for key in ("status", "state_version")},
            "boundary_hash": boundary_hash,
            "evidence_use_ids": evidence_use_ids,
            "trace_event_ids": event_ids,
            "authority": "candidate_only_not_promoted",
            "deltas": deltas,
        }
        snapshot["delta_snapshot_id"] = f"delta_{_hash(snapshot)[:32]}"
        return snapshot

    def run_to_boundary(
        self, task_id: str, request: RunProductResearchRequest
    ) -> dict[str, Any]:
        request = RunProductResearchRequest.model_validate(
            request.model_dump(mode="json")
        )
        payload = {
            "operation": "run_product_task",
            "task_id": task_id,
            **request.model_dump(mode="json"),
            "runner_schema_version": PRODUCT_RUNNER_SCHEMA_VERSION,
        }
        payload_hash = _hash(payload)
        with self.kernel._transaction() as connection:
            self.kernel._task(connection, task_id)
            existing = self.kernel._existing_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                payload_hash=payload_hash,
            )
            if existing is not None:
                return {**existing, "deduplicated": True}
        lock = self._run_lock(task_id)
        if not lock.acquire(blocking=False):
            raise ResearchConflict("Task 已由本地 runner 推进")
        try:
            response = self._run_locked(task_id, request)
            return self._commit_runner_boundary(
                task_id=task_id,
                request=request,
                payload_hash=payload_hash,
                response=response,
            )
        except (ResearchError, SimulatedCrash):
            raise
        except Exception as exc:
            raise ResearchUnsafeState(
                f"product runner internal failure: {type(exc).__name__}"
            ) from exc
        finally:
            lock.release()

    def _run_locked(
        self, task_id: str, request: RunProductResearchRequest
    ) -> dict[str, Any]:
        steps = 0
        inner_actions = 0
        outer_audits = 0
        while steps < request.max_steps:
            raw = self.kernel.get_task(task_id)
            task = raw["task"]
            status = str(task["status"])
            if status in {"blocked", "waiting_user", "terminal"}:
                self.ensure_candidate_deltas(task_id)
                return self._runner_response(task_id, "durable_boundary", steps)
            if status not in {"ready", "running"}:
                raise ResearchUnsafeState(f"unsupported product task status: {status}")
            if not task.get("owner_id"):
                claimed = self.kernel.claim_owner(
                    task_id=task_id,
                    command_id=_derived_command(
                        request.command_id, "claim", task["state_version"]
                    ),
                    owner_id=self.runner_id,
                    expected_state_version=int(task["state_version"]),
                    lease_seconds=self.LEASE_SECONDS,
                )
                task = self.kernel.get_task(task_id)["task"]
                assert int(task["owner_epoch"]) == int(claimed["owner_epoch"])
            elif str(task["owner_id"]) != self.runner_id:
                lease = _parse_time(task.get("lease_until"))
                if lease is not None and lease > datetime.now(timezone.utc):
                    raise ResearchConflict("Task 已有未过期 active owner")
                self.kernel.claim_owner(
                    task_id=task_id,
                    command_id=_derived_command(
                        request.command_id, "takeover", task["state_version"]
                    ),
                    owner_id=self.runner_id,
                    expected_state_version=int(task["state_version"]),
                    lease_seconds=self.LEASE_SECONDS,
                )
                task = self.kernel.get_task(task_id)["task"]
            active = next(
                (
                    attempt
                    for attempt in reversed(raw["attempts"])
                    if attempt["status"] != "terminal"
                ),
                None,
            )
            if active is None:
                if raw["attempts"]:
                    raise ResearchUnsafeState(
                        "nonterminal Task has only terminal Attempts; explicit retry is required"
                    )
                started = self.kernel.start_attempt(
                    task_id=task_id,
                    command_id=_derived_command(request.command_id, "start"),
                    owner_id=self.runner_id,
                    owner_epoch=int(task["owner_epoch"]),
                    expected_state_version=int(task["state_version"]),
                    cause=AttemptCause.INITIAL,
                )
                active = {
                    "attempt_id": started["attempt_id"],
                    "status": "running",
                }
                task = self.kernel.get_task(task_id)["task"]
            else:
                # A claim/takeover may have updated the active Attempt epoch.
                raw = self.kernel.get_task(task_id)
                task = raw["task"]
                active = next(
                    attempt
                    for attempt in reversed(raw["attempts"])
                    if attempt["status"] != "terminal"
                )
            if str(active["status"]) != "running":
                self.ensure_candidate_deltas(task_id)
                return self._runner_response(task_id, "durable_boundary", steps)
            latest = next(
                (
                    checkpoint
                    for checkpoint in reversed(raw["checkpoints"])
                    if checkpoint["attempt_id"] == active["attempt_id"]
                ),
                None,
            )
            if (
                latest is not None
                and latest["state_schema_version"] == INNER_RESEARCH_STATE_SCHEMA_VERSION
                and latest["state_payload"].get("phase") == "complete"
            ):
                outcome = self.outer.advance(
                    task_id,
                    AdvanceOuterResearchRequest(
                        command_id=_derived_command(
                            request.command_id,
                            "outer",
                            active["attempt_id"],
                            task["state_version"],
                        ),
                        attempt_id=str(active["attempt_id"]),
                        owner_id=self.runner_id,
                        owner_epoch=int(task["owner_epoch"]),
                        expected_state_version=int(task["state_version"]),
                        expected_checkpoint_id=str(latest["checkpoint_id"]),
                    ),
                )
                outer_audits += 1
                steps += 1
                if outcome["task_status"] == "waiting_user":
                    self._open_outer_input(task_id, outcome, request.command_id)
                continue
            if latest is not None and latest["state_schema_version"] == OUTER_STATE_SCHEMA_VERSION:
                raise ResearchUnsafeState(
                    "active Attempt cannot continue from an outer checkpoint without lineage"
                )
            outcome = self.inner.continue_run(
                task_id,
                ContinueInnerResearchRequest(
                    command_id=_derived_command(
                        request.command_id,
                        "inner",
                        active["attempt_id"],
                        task["state_version"],
                    ),
                    attempt_id=str(active["attempt_id"]),
                    owner_id=self.runner_id,
                    owner_epoch=int(task["owner_epoch"]),
                    expected_state_version=int(task["state_version"]),
                    expected_checkpoint_id=(
                        str(latest["checkpoint_id"]) if latest is not None else None
                    ),
                ),
            )
            inner_actions += 1
            steps += 1
            if steps % self.LEASE_RENEW_EVERY == 0:
                current = self.kernel.get_task(task_id)["task"]
                if str(current["status"]) != "terminal":
                    self.kernel.renew_owner(
                        task_id=task_id,
                        command_id=_derived_command(
                            request.command_id, "renew", steps
                        ),
                        owner_id=self.runner_id,
                        owner_epoch=int(current["owner_epoch"]),
                        expected_state_version=int(current["state_version"]),
                        lease_seconds=self.LEASE_SECONDS,
                    )
            if outcome["phase"] == "stopped":
                self.ensure_candidate_deltas(task_id)
                return self._runner_response(task_id, "durable_stop", steps)
        return {
            **self._runner_response(task_id, "bounded_yield", steps),
            "inner_actions": inner_actions,
            "outer_audits": outer_audits,
        }

    def _open_outer_input(
        self, task_id: str, outcome: dict[str, Any], run_command_id: str
    ) -> None:
        control = self.control.get_status(task_id)
        if control["open_input_requests"]:
            return
        if self._resolved_evaluator_capability_input_exists(task_id):
            self._suppress_repeated_evaluator_input(
                task_id=task_id,
                outcome=outcome,
                run_command_id=run_command_id,
            )
            return
        task = control["task"]
        raw = self.kernel.get_task(task_id)
        attempt = next(
            value
            for value in reversed(raw["attempts"])
            if value["status"] == "waiting_user"
        )
        self.control.create_input(
            task_id,
            CreateInputRequest(
                command_id=_derived_command(
                    run_command_id, "input", outcome["audit_id"]
                ),
                attempt_id=str(attempt["attempt_id"]),
                owner_id=self.runner_id,
                owner_epoch=int(task["owner_epoch"]),
                expected_state_version=int(task["state_version"]),
                expected_checkpoint_id=str(outcome["checkpoint_id"]),
                kind="clarification",
                prompt=UNSUPPORTED_EVALUATOR_PROMPT,
            ),
            principal_id=self.principal_id,
        )

    def _resolved_evaluator_capability_input_exists(self, task_id: str) -> bool:
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM research_input_requests ir
                JOIN research_human_decisions hd
                  ON hd.input_request_id=ir.input_request_id
                WHERE ir.task_id=? AND ir.request_kind='clarification'
                  AND ir.prompt=? AND hd.decision_kind='clarify_goal'
                  AND hd.applied_action='goal_revision'
                LIMIT 1
                """,
                (task_id, UNSUPPORTED_EVALUATOR_PROMPT),
            ).fetchone()
        return row is not None

    def _suppress_repeated_evaluator_input(
        self,
        *,
        task_id: str,
        outcome: dict[str, Any],
        run_command_id: str,
    ) -> None:
        command_id = _derived_command(
            run_command_id, "suppress-repeat-input", outcome["audit_id"]
        )
        payload = {
            "operation": "suppress_repeated_evaluator_input",
            "task_id": task_id,
            "audit_id": outcome["audit_id"],
            "attempt_id": outcome["parent_attempt_id"],
            "checkpoint_id": outcome["checkpoint_id"],
            "reason": "authorized_evaluator_required_already_answered",
        }
        payload_hash = _hash(payload)
        now_value = datetime.now(timezone.utc)
        now = now_value.isoformat(timespec="microseconds")
        with self.kernel._transaction() as connection:
            task = self.kernel._task(connection, task_id)
            existing = self.kernel._existing_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                payload_hash=payload_hash,
                owner_id=self.runner_id,
                owner_epoch=int(task["owner_epoch"]),
                now=now_value,
            )
            if existing is not None:
                return
            self.kernel._assert_nonterminal(task)
            self.kernel._assert_owner(
                task,
                owner_id=self.runner_id,
                owner_epoch=int(task["owner_epoch"]),
                now=now_value,
            )
            attempt = self.kernel._attempt(
                connection, str(outcome["parent_attempt_id"])
            )
            if (
                str(task["status"]) != "waiting_user"
                or str(attempt["task_id"]) != task_id
                or str(attempt["status"]) != "waiting_user"
                or str(attempt["goal_id"]) != str(task["active_goal_id"])
            ):
                raise ResearchConflict(
                    "repeated InputRequest suppression lost current pause lineage"
                )
            latest = connection.execute(
                "SELECT checkpoint_id FROM research_checkpoints "
                "WHERE attempt_id=? ORDER BY sequence DESC LIMIT 1",
                (str(attempt["attempt_id"]),),
            ).fetchone()
            if latest is None or str(latest["checkpoint_id"]) != str(
                outcome["checkpoint_id"]
            ):
                raise ResearchConflict(
                    "repeated InputRequest suppression checkpoint mismatch"
                )
            open_input = connection.execute(
                """
                SELECT 1 FROM research_input_requests ir
                WHERE ir.task_id=? AND NOT EXISTS (
                    SELECT 1 FROM research_input_dispositions idp
                    WHERE idp.input_request_id=ir.input_request_id
                      AND idp.status IN ('resolved','cancelled','superseded')
                ) LIMIT 1
                """,
                (task_id,),
            ).fetchone()
            if open_input is not None:
                raise ResearchConflict("current InputRequest already exists")
            connection.execute(
                "UPDATE research_attempts SET status='blocked' WHERE attempt_id=?",
                (str(attempt["attempt_id"]),),
            )
            connection.execute(
                "UPDATE research_tasks SET status='blocked', "
                "state_version=state_version+1, updated_at=? WHERE task_id=?",
                (now, task_id),
            )
            event_id = self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(attempt["goal_id"]),
                attempt_id=str(attempt["attempt_id"]),
                checkpoint_id=str(outcome["checkpoint_id"]),
                event_type="duplicate_input_request_suppressed",
                payload={
                    "audit_id": outcome["audit_id"],
                    "blocker": "authorized_evaluator_required",
                    "reason": "same_capability_gap_already_answered",
                },
                command_id=command_id,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            response = {
                "task_id": task_id,
                "event_id": event_id,
                "task_status": "blocked",
                "state_version": int(task["state_version"]) + 1,
                "owner_epoch": int(task["owner_epoch"]),
            }
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=command_id,
                command_type="suppress_repeated_evaluator_input",
                payload_hash=payload_hash,
                outcome_reference=event_id,
                response=response,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )

    def _runner_response(
        self, task_id: str, boundary: str, steps: int
    ) -> dict[str, Any]:
        task = self.kernel.get_task(task_id)["task"]
        return {
            "task_id": task_id,
            "boundary": boundary,
            "steps": steps,
            "task_status": str(task["status"]),
            "state_version": int(task["state_version"]),
            "owner_epoch": int(task["owner_epoch"]),
        }

    def _commit_runner_boundary(
        self,
        *,
        task_id: str,
        request: RunProductResearchRequest,
        payload_hash: str,
        response: dict[str, Any],
    ) -> dict[str, Any]:
        with self.kernel._transaction() as connection:
            task = self.kernel._task(connection, task_id)
            existing = self.kernel._existing_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                payload_hash=payload_hash,
            )
            if existing is not None:
                return {**existing, "deduplicated": True}
            latest = connection.execute(
                "SELECT checkpoint_id, attempt_id FROM research_checkpoints "
                "WHERE task_id=? ORDER BY created_at DESC, sequence DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            now = _now()
            event_id = self.kernel._event(
                connection,
                task_id=task_id,
                goal_id=str(task["active_goal_id"]),
                attempt_id=str(latest["attempt_id"]) if latest else None,
                checkpoint_id=str(latest["checkpoint_id"]) if latest else None,
                event_type="product_runner_boundary",
                payload={
                    "boundary": response["boundary"],
                    "task_status": response["task_status"],
                    "steps": response["steps"],
                },
                command_id=request.command_id,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            committed = {**response, "event_id": event_id}
            self.kernel._insert_receipt(
                connection,
                task_id=task_id,
                command_id=request.command_id,
                command_type="product_run_to_boundary",
                payload_hash=payload_hash,
                outcome_reference=event_id,
                response=committed,
                owner_epoch=int(task["owner_epoch"]),
                now=now,
            )
            self.fault_injector("after_product_runner_receipt")
        return {**committed, "deduplicated": False}
