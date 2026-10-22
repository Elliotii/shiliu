from __future__ import annotations

import json
import hashlib
import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from shiliu.db import Database, utc_now
from shiliu.config import (ASSISTANT_ACTIVE_SECONDS, ASSISTANT_FINAL_SECONDS,
                           ASSISTANT_MODEL_DISPATCH_LIMIT, ASSISTANT_TOOL_EXECUTION_LIMIT,
                           ASSISTANT_TOKEN_LIMIT)


ACTIVE_RUN_STATES = {"queued", "running"}
_TOOL_EXECUTION = ContextVar("assistant_tool_execution", default=None)


class AssistantConflict(RuntimeError):
    pass


class ModelBudgetWait(RuntimeError):
    code = "background_budget_wait"


class ExecutionBudgetExceeded(AssistantConflict):
    code = "execution_budget_exhausted"


class AssistantRunStore:
    def __init__(self, db: Database, *, principal_id: str = "local_operator") -> None:
        self.db = db
        self.principal_id = principal_id

    @staticmethod
    def known_tokens(usage: dict) -> int:
        return max(int(usage.get("total_tokens") or 0),
                   int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
                   + int(usage.get("completion_tokens") or usage.get("output_tokens") or 0))

    def initialize_execution_budget(self, run_id: str, *, epoch: int,
                                    model_limit: int = ASSISTANT_MODEL_DISPATCH_LIMIT,
                                    tool_limit: int = ASSISTANT_TOOL_EXECUTION_LIMIT) -> dict:
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM assistant_runs WHERE id=? AND status='running' AND run_epoch=?", (run_id, epoch)).fetchone()
            if row is None:
                raise AssistantConflict("run_fenced")
            working = json.loads(row["working_state_json"] or "{}")
            if "execution_budget" not in working:
                started = datetime.fromisoformat(str(working.get("segment_started_at") or row["started_at"] or row["created_at"]))
                responses = int(connection.execute("SELECT COUNT(*) FROM assistant_run_events WHERE run_id=? AND event_type='provider_response'", (run_id,)).fetchone()[0])
                working["execution_budget"] = {
                    "deadline_at": (started + timedelta(seconds=ASSISTANT_ACTIVE_SECONDS)).isoformat(),
                    "model_limit": max(0, model_limit), "tool_limit": max(0, tool_limit),
                    "model_calls": 0 if working.get("explicit_new_segment") else max(responses, int(row["step_count"]) - int(working.get("segment_step_base", 0))),
                    "tool_executions": max(0, int(row["tool_count"]) - int(working.get("segment_tool_base", 0))),
                    "known_tokens": 0 if working.get("explicit_new_segment") else self.known_tokens(json.loads(row["usage_json"] or "{}")),
                    "unknown_responses": 0, "final_dispatched": False,
                }
                # Old late totals lived outside usage_json. Fold once, retaining diagnostics.
                aggregate = json.loads(row["usage_json"] or "{}")
                if not working.get("usage_includes_late"):
                    for key, value in (working.get("late_model_usage") or {}).items():
                        if isinstance(value, (int, float)) and not isinstance(value, bool):
                            aggregate[key] = aggregate.get(key, 0) + value
                    if not working.get("explicit_new_segment"):
                        working["execution_budget"]["known_tokens"] = self.known_tokens(aggregate)
                    working["usage_includes_late"] = True
                connection.execute("UPDATE assistant_runs SET working_state_json=?,usage_json=? WHERE id=?",
                                   (json.dumps(working, ensure_ascii=False), json.dumps(aggregate), run_id))
            return working["execution_budget"]

    def execution_remaining(self, run_id: str, *, final: bool = False) -> float:
        budget = self.get_run(run_id)["working_state"].get("execution_budget")
        if not budget:
            return float(ASSISTANT_ACTIVE_SECONDS if final else ASSISTANT_ACTIVE_SECONDS - ASSISTANT_FINAL_SECONDS)
        remaining = (datetime.fromisoformat(budget["deadline_at"]) - datetime.now(timezone.utc)).total_seconds()
        return max(0., remaining - (0 if final else ASSISTANT_FINAL_SECONDS))

    def dispatch_model(self, run_id: str, *, epoch: int, final: bool,
                       input_tokens: int, output_tokens: int, reserve_input_tokens: int | None = None) -> None:
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT working_state_json,status,run_epoch FROM assistant_runs WHERE id=?", (run_id,)).fetchone()
            if row is None or row["status"] != "running" or int(row["run_epoch"]) != epoch:
                raise AssistantConflict("run_fenced")
            working = json.loads(row["working_state_json"] or "{}")
            budget = working["execution_budget"]
            remaining = (datetime.fromisoformat(budget["deadline_at"]) - datetime.now(timezone.utc)).total_seconds()
            limit = budget["model_limit"] - (0 if final else 1)
            reserve = 0 if final else (input_tokens if reserve_input_tokens is None else reserve_input_tokens) + 8192
            if (remaining <= (0 if final else ASSISTANT_FINAL_SECONDS)
                    or int(budget["model_calls"]) >= limit
                    or budget.get("final_dispatched")
                    or (working.get("finish_requested") and not final)
                    or int(budget["known_tokens"]) + input_tokens + output_tokens + reserve > ASSISTANT_TOKEN_LIMIT):
                raise ExecutionBudgetExceeded("当前段模型/Token/期限额度不足")
            budget["model_calls"] += 1
            if final:
                budget["final_dispatched"] = True
            connection.execute("UPDATE assistant_runs SET working_state_json=? WHERE id=?", (json.dumps(working, ensure_ascii=False), run_id))

    def dispatch_tool(self, run_id: str, *, epoch: int) -> None:
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT working_state_json,status,run_epoch FROM assistant_runs WHERE id=?", (run_id,)).fetchone()
            if row is None or row["status"] != "running" or int(row["run_epoch"]) != epoch:
                raise AssistantConflict("run_fenced")
            working = json.loads(row["working_state_json"] or "{}")
            budget = working["execution_budget"]
            if (datetime.fromisoformat(budget["deadline_at"]) - datetime.now(timezone.utc)).total_seconds() <= ASSISTANT_FINAL_SECONDS or budget["tool_executions"] >= budget["tool_limit"] or working.get("finish_requested") or budget.get("final_dispatched"):
                raise ExecutionBudgetExceeded("当前段工具/期限额度不足")
            budget["tool_executions"] += 1
            connection.execute("UPDATE assistant_runs SET working_state_json=? WHERE id=?", (json.dumps(working, ensure_ascii=False), run_id))

    @contextmanager
    def tool_execution_scope(self, run_id: str, epoch: int):
        token = _TOOL_EXECUTION.set((run_id, epoch))
        try:
            yield
        finally:
            _TOOL_EXECUTION.reset(token)

    @staticmethod
    def guard_tool_operation(connection: Any, operation_key: str = "") -> None:
        active = _TOOL_EXECUTION.get()
        if active:
            run_id, expected_epoch = active
        elif operation_key.startswith("tool:"):
            run_id, expected_epoch = operation_key.split(":", 2)[1], None
        else:
            return
        row = connection.execute("SELECT status,run_epoch,cancel_requested,working_state_json FROM assistant_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise AssistantConflict("run_fenced")
        working = json.loads(row["working_state_json"] or "{}")
        budget = working.get("execution_budget")
        if budget and (row["status"] != "running" or row["cancel_requested"] or working.get("finish_requested")
                       or (expected_epoch is not None and int(row["run_epoch"]) != expected_epoch)
                       or budget.get("final_dispatched") or datetime.fromisoformat(budget["deadline_at"]) <= datetime.now(timezone.utc)):
            raise AssistantConflict("run_fenced")

    @staticmethod
    def _pause_execution_budget(working: dict, *, stopped_at: str | None = None) -> None:
        budget = working.get("execution_budget")
        if budget and "paused_remaining" not in budget:
            stopped = datetime.fromisoformat(stopped_at) if stopped_at else datetime.now(timezone.utc)
            budget["paused_remaining"] = max(0., (datetime.fromisoformat(budget["deadline_at"]) - stopped).total_seconds())

    def create_space(
        self,
        *,
        name: str,
        goal: str = "",
        source_ids: list[int] | None = None,
        video_ids: list[int] | None = None,
        all_active: bool = False,
        maintenance_mode: str = "on_demand",
    ) -> dict[str, Any]:
        if maintenance_mode not in {"on_demand", "automatic"}:
            raise ValueError("invalid_maintenance_mode")
        now = utc_now()
        normalized = sorted({int(value) for value in (source_ids or []) if int(value) > 0})
        normalized_videos = sorted(
            {int(value) for value in (video_ids or []) if int(value) > 0}
        )
        if maintenance_mode == "automatic" and (
            all_active or (not normalized and not normalized_videos)
        ):
            raise ValueError("automatic_maintenance_requires_explicit_scope")
        with self.db.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO assistant_spaces(
                    principal_id, name, goal, source_ids_json, video_ids_json, all_active, maintenance_mode,
                    scope_version, enabled, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
                """,
                (
                    self.principal_id,
                    name.strip() or "我的收藏助手",
                    goal.strip(),
                    json.dumps(normalized),
                    json.dumps(normalized_videos),
                    int(all_active),
                    maintenance_mode,
                    now,
                    now,
                ),
            )
            space_id = int(cursor.lastrowid)
        return self.get_space(space_id)

    def list_spaces(self) -> list[dict[str, Any]]:
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM assistant_spaces
                WHERE principal_id=? AND enabled=1
                ORDER BY updated_at DESC, id DESC
                """,
                (self.principal_id,),
            ).fetchall()
        return [self._space(dict(row)) for row in rows]

    def get_space(self, space_id: int) -> dict[str, Any]:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM assistant_spaces WHERE id=? AND principal_id=?",
                (space_id, self.principal_id),
            ).fetchone()
        if row is None:
            raise KeyError(space_id)
        return self._space(dict(row))

    def update_space(
        self,
        space_id: int,
        *,
        expected_scope_version: int,
        name: str | None = None,
        goal: str | None = None,
        source_ids: list[int] | None = None,
        video_ids: list[int] | None = None,
        all_active: bool | None = None,
        maintenance_mode: str | None = None,
    ) -> dict[str, Any]:
        if maintenance_mode is not None and maintenance_mode not in {"on_demand", "automatic"}:
            raise ValueError("invalid_maintenance_mode")
        now = utc_now()
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM assistant_spaces WHERE id=? AND principal_id=?",
                (space_id, self.principal_id),
            ).fetchone()
            if row is None:
                raise KeyError(space_id)
            if int(row["scope_version"]) != expected_scope_version:
                raise AssistantConflict("scope_version_conflict")
            fields: dict[str, Any] = {"updated_at": now}
            if name is not None:
                fields["name"] = name.strip() or str(row["name"])
            if goal is not None:
                fields["goal"] = goal.strip()
            scope_changed = (
                source_ids is not None or video_ids is not None or all_active is not None
            )
            if source_ids is not None:
                fields["source_ids_json"] = json.dumps(
                    sorted({int(value) for value in source_ids if int(value) > 0})
                )
            if all_active is not None:
                fields["all_active"] = int(all_active)
            if maintenance_mode is not None:
                fields["maintenance_mode"] = maintenance_mode
            if video_ids is not None:
                fields["video_ids_json"] = json.dumps(
                    sorted({int(value) for value in video_ids if int(value) > 0})
                )
            effective_mode = fields.get("maintenance_mode", row["maintenance_mode"])
            effective_all = bool(fields.get("all_active", row["all_active"]))
            effective_videos = json.loads(fields.get("video_ids_json", row["video_ids_json"]))
            effective_sources = json.loads(fields.get("source_ids_json", row["source_ids_json"]))
            if effective_mode == "automatic" and (
                effective_all or (not effective_sources and not effective_videos)
            ):
                raise ValueError("automatic_maintenance_requires_explicit_scope")
            if scope_changed:
                fields["scope_version"] = expected_scope_version + 1
            assignments = ", ".join(f"{key}=?" for key in fields)
            connection.execute(
                f"UPDATE assistant_spaces SET {assignments} WHERE id=?",
                [*fields.values(), space_id],
            )
            if scope_changed:
                active = connection.execute(
                    """
                    SELECT r.id FROM assistant_runs r
                    JOIN assistant_threads t ON t.id=r.thread_id
                    WHERE t.space_id=? AND r.status IN ('queued','running')
                    """,
                    (space_id,),
                ).fetchall()
                connection.execute(
                    """
                    UPDATE assistant_runs SET status='cancelled', cancel_requested=1,
                        run_epoch=run_epoch+1, last_error_code='scope_changed',
                        last_error_message='Space 范围已变化，请重新提问', updated_at=?
                    WHERE id IN (
                        SELECT r.id FROM assistant_runs r
                        JOIN assistant_threads t ON t.id=r.thread_id
                        WHERE t.space_id=? AND r.status IN ('queued','running')
                    )
                    """,
                    (now, space_id),
                )
                for active_run in active:
                    self._append_event(
                        connection, str(active_run["id"]), "run_cancelled",
                        {"reason": "scope_changed"},
                    )
                if effective_mode == "automatic":
                    self._enqueue_scope_repairs(
                        connection, space_id=space_id,
                        scope_version=expected_scope_version + 1,
                        selected_sources={int(value) for value in effective_sources},
                        selected_videos={int(value) for value in effective_videos},
                        all_active=effective_all,
                    )
        return self.get_space(space_id)

    def _enqueue_scope_repairs(
        self, connection: Any, *, space_id: int, scope_version: int,
        selected_sources: set[int], selected_videos: set[int], all_active: bool,
    ) -> None:
        """Only revisit maintained pages that lost a previously associated material."""
        pages = connection.execute(
            """SELECT id,title FROM assistant_wiki_pages
            WHERE space_id=? AND principal_id=? AND status='active'""",
            (space_id, self.principal_id),
        ).fetchall()
        for page in pages:
            materials = connection.execute(
                """SELECT m.video_id,h.current_revision,v.is_ignored,v.archived_at
                FROM assistant_wiki_materials m
                JOIN assistant_source_heads h ON h.video_id=m.video_id
                  AND h.principal_id=?
                JOIN videos v ON v.id=m.video_id
                WHERE m.page_id=?""",
                (self.principal_id, page["id"]),
            ).fetchall()
            available = []
            lost = False
            for material in materials:
                video_id = int(material["video_id"])
                membership = connection.execute(
                    """SELECT m.source_id FROM video_source_memberships m
                    JOIN favorite_sources s ON s.id=m.source_id AND s.status='active'
                    WHERE m.video_id=? AND m.removed_at IS NULL""",
                    (video_id,),
                ).fetchall()
                visible = (
                    not material["is_ignored"] and not material["archived_at"]
                    and (not selected_videos or video_id in selected_videos)
                    and any(all_active or int(item["source_id"]) in selected_sources
                            for item in membership)
                )
                if not visible:
                    lost = True
                elif material["current_revision"] and connection.execute(
                    "SELECT 1 FROM assistant_source_cards WHERE revision=?",
                    (material["current_revision"],),
                ).fetchone():
                    available.append((video_id, str(material["current_revision"])))
            if not lost or not available:
                continue
            video_id, revision = available[0]
            self.enqueue_job(
                connection, kind="wiki_integrate",
                dedupe_key=f"wiki_repair_scope:{space_id}:{page['id']}:{scope_version}",
                payload={
                    "space_id": space_id, "scope_version": scope_version,
                    "video_id": video_id, "revision": revision,
                    "topic": str(page["title"]), "repair_page_id": str(page["id"]),
                },
            )

    def create_thread(self, space_id: int, *, title: str = "") -> dict[str, Any]:
        self.get_space(space_id)
        thread_id = f"ath_{uuid.uuid4().hex}"
        now = utc_now()
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO assistant_threads(id, principal_id, space_id, title, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (thread_id, self.principal_id, space_id, title.strip(), now, now),
            )
        return self.get_thread(thread_id)

    def get_thread(self, thread_id: str, *, include_internal: bool = False) -> dict[str, Any]:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM assistant_threads WHERE id=? AND principal_id=?",
                (thread_id, self.principal_id),
            ).fetchone()
            if row is None:
                raise KeyError(thread_id)
            messages = connection.execute(
                """SELECT m.*,t.result_json AS resolved_tool_result_json
                FROM assistant_messages m LEFT JOIN assistant_tool_calls t
                  ON t.run_id=m.run_id AND t.call_id=json_extract(m.provider_payload_json,'$.tool_call_id')
                WHERE m.thread_id=? ORDER BY m.seq""",
                (thread_id,),
            ).fetchall()
            runs = connection.execute(
                "SELECT * FROM assistant_runs WHERE thread_id=? ORDER BY rowid",
                (thread_id,),
            ).fetchall()
            note = connection.execute(
                """
                SELECT id, scope_version, note_version, covered_until_message_seq, source_run_ids_json, goal,
                       searched_scope_and_material_refs_json, open_questions_json,
                       next_actions_json, status, updated_at, checkpoint_json
                FROM assistant_task_notes WHERE thread_id=? AND task_segment=1
                """,
                (thread_id,),
            ).fetchone()
        value = dict(row)
        context_state = json.loads(value.pop('context_state_json') or '{}')
        if include_internal:
            value['context_state'] = context_state
        value["messages"] = []
        for item in messages:
            message = dict(item)
            resolved = message.pop("resolved_tool_result_json", None)
            if include_internal:
                message['_raw_content'] = message['content']
            else:
                payload = json.loads(message['provider_payload_json'] or '{}')
                payload.pop('model_projection', None)
                message['provider_payload_json'] = json.dumps(payload, ensure_ascii=False)
            if message["role"] == "tool":
                recorded = json.loads(message["content"] or "{}")
                if recorded.get("_assistant_result_ref"):
                    message["content"] = resolved or json.dumps({"status": "error", "error_code": "tool_result_unavailable"})
            value["messages"].append(message)
        value["runs"] = [self._run(dict(item)) for item in runs]
        current_id = self._current_action_run_id(value["runs"])
        value["runs"] = [
            self._with_actions(item, current=item["id"] == current_id)
            for item in value["runs"]
        ]
        if note:
            value["task_note"] = {
                **dict(note),
                "searched_scope_and_material_refs": json.loads(
                    note["searched_scope_and_material_refs_json"] or "[]"
                ),
                "open_questions": json.loads(note["open_questions_json"] or "[]"),
                "next_actions": json.loads(note["next_actions_json"] or "[]"),
            }
            value["task_note"].pop("searched_scope_and_material_refs_json", None)
            value["task_note"].pop("open_questions_json", None)
            value["task_note"].pop("next_actions_json", None)
            value["task_note"]["usable"] = False
            checkpoint = json.loads(value['task_note'].pop('checkpoint_json') or '{}')
            if checkpoint.get('format_version') == 1:
                binding = context_state.get('checkpoint') or {}
                value['task_note']['usable'] = bool(note['status'] == 'active'
                    and binding.get('id') == note['id'] and binding.get('version') == note['note_version']
                    and isinstance(checkpoint.get('text'), str) and bool(checkpoint['text'].strip()))
                value['task_note']['searched_scope_and_material_refs'] = (
                    checkpoint.get('material_index') or []) if value['task_note']['usable'] else []
            if not value['task_note']['usable']:
                value['task_note']['searched_scope_and_material_refs'] = []
            value["task_note"].pop("source_run_ids_json", None)
        else:
            value["task_note"] = None
        formal_ids = set()
        with self.db.connect() as connection:
            formal_ids = {str(item[0]) for item in connection.execute("SELECT json_extract(e.payload_json,'$.message_id') FROM assistant_run_events e JOIN assistant_runs r ON r.id=e.run_id WHERE r.thread_id=? AND r.status='completed' AND e.event_type='run_completed'", (thread_id,))}
        users = {m["run_id"]: m["content"] for m in value["messages"] if m["role"] == "user"}
        candidates = []
        for message in value["messages"]:
            if message["id"] not in formal_ids or not str(message["content"]).strip():
                continue
            if json.loads(message.get("provider_payload_json") or "{}").get("origin") == "operation_receipt":
                continue
            text = str(users.get(message["run_id"], "")).strip()
            if re.fullmatch(r"(?:你好|您好|嗨|哈喽|谢谢|感谢|再见|hello|hi|thanks)[呀啊哦啦!！。，,.~～\s]*", text, re.I):
                continue
            if re.match(r"^(?:请)?(?:停止|继续|确认|拒绝|忽略|恢复|删除|归档|撤销|保存|记住|忘记)", text) and not re.search(r"研究|比较|解释|分析|回答|如何|为什么", text):
                continue
            if str(message["content"]).startswith("这次已停止探索，当前请求是："):
                continue
            candidates.append(message["id"])
        value["save_answer_message_id"] = candidates[-1] if candidates else None
        value["can_save"] = bool(candidates) and current_id is None
        value["task_focus"] = next(
            (run.get("working_state", {}).get("task_focus") for run in reversed(value["runs"])
             if run.get("working_state", {}).get("task_focus")), None
        )
        return value

    def list_threads(self, *, space_id: int, limit: int = 30,
                     before_updated_at: str | None = None,
                     before_id: str | None = None) -> dict[str, Any]:
        self.get_space(space_id)
        if (before_updated_at is None) != (before_id is None):
            raise ValueError("invalid_thread_cursor")
        with self.db.connect() as connection:
            rows = connection.execute(
                """SELECT t.id,t.space_id,t.title,t.created_at,t.updated_at,
                          (SELECT m.content FROM assistant_messages m
                           WHERE m.thread_id=t.id AND m.role='user'
                           ORDER BY m.seq LIMIT 1) AS first_input,
                          (SELECT r.status FROM assistant_runs r WHERE r.thread_id=t.id
                           ORDER BY r.rowid DESC LIMIT 1) AS run_status,
                          (SELECT r.last_error_code FROM assistant_runs r WHERE r.thread_id=t.id
                           ORDER BY r.rowid DESC LIMIT 1) AS last_error_code
                   FROM assistant_threads t
                   WHERE t.principal_id=? AND t.space_id=?
                     AND EXISTS(SELECT 1 FROM assistant_messages m WHERE m.thread_id=t.id AND m.role='user')
                     AND (? IS NULL OR t.updated_at<? OR (t.updated_at=? AND t.id<?))
                   ORDER BY t.updated_at DESC,t.id DESC LIMIT ?""",
                (self.principal_id, space_id, before_updated_at, before_updated_at,
                 before_updated_at, before_id, limit + 1),
            ).fetchall()
        page = [dict(row) for row in rows[:limit]]
        for item in page:
            item["title"] = (str(item["title"] or item.pop("first_input") or "新对话")
                             .strip().replace("\n", " ")[:48])
            item.pop("first_input", None)
        next_cursor = None
        if len(rows) > limit:
            last = page[-1]
            next_cursor = {"before_updated_at": last["updated_at"], "before_id": last["id"]}
        return {"threads": page, "next_cursor": next_cursor}

    @staticmethod
    def _current_action_run_id(runs: list[dict[str, Any]]) -> str | None:
        active = next(
            (run for run in reversed(runs) if run["status"] in {"queued", "running"}),
            None,
        )
        if active:
            return str(active["id"])
        latest = runs[-1] if runs else None
        return str(latest["id"]) if latest and latest["status"] in {
            "interrupted", "budget_exhausted", "failed"
        } else None

    @staticmethod
    def _with_actions(run: dict[str, Any], *, current: bool = True) -> dict[str, Any]:
        status = str(run["status"])
        code = str(run.get("last_error_code") or "")
        recovery_attempts = int(run.get("working_state", {}).get("context_recovery_attempts", 0))
        compaction_retries = int(run.get("working_state", {}).get("compaction_retries", 0))
        resumable = current and (
            status in {"interrupted", "budget_exhausted"}
            and (code != "context_budget_exceeded" or recovery_attempts == 0)
            or status == "failed" and code == "context_compaction_failed" and compaction_retries == 0
        )
        return {**run, "actions": {
            "resume": resumable,
            "abandon": current and status in {"queued", "running", "interrupted", "budget_exhausted", "failed"},
            "terminated": status == "cancelled",
            "current": current,
            "reason": "run_superseded" if not current and status in {"interrupted", "budget_exhausted"} else (code or None),
        }}

    def _bind_save_request(self, connection: Any, run_id: str, thread_id: str,
                           message_id: str, text: str, answer_message_id: str | None = None,
                           receipt_only: bool = False) -> dict:
        row = connection.execute("SELECT working_state_json FROM assistant_runs WHERE id=?", (run_id,)).fetchone()
        working = json.loads(row[0] or "{}")
        if working.get("knowledge_save"):
            return working["knowledge_save"]
        answer = connection.execute(
            """SELECT m.id,m.run_id FROM assistant_messages m JOIN assistant_threads t ON t.id=m.thread_id
            WHERE m.id=? AND m.thread_id=? AND t.principal_id=? AND m.role='assistant'
            AND COALESCE(json_extract(m.provider_payload_json,'$.origin'),'model')<>'operation_receipt'
            AND EXISTS(SELECT 1 FROM assistant_run_events e WHERE e.run_id=m.run_id
              AND e.event_type='run_completed' AND json_extract(e.payload_json,'$.message_id')=m.id)""",
            (answer_message_id, thread_id, self.principal_id),
        ).fetchone()
        if answer is None:
            raise AssistantConflict("save_answer_not_available")
        binding = {"source_message_id": message_id, "request_key": "save-message:" + message_id,
                   "answer_message_id": answer["id"], "answer_run_id": answer["run_id"], "scope_text": text,
                   "receipt_only": receipt_only}
        working["knowledge_save"] = binding
        connection.execute("UPDATE assistant_runs SET working_state_json=? WHERE id=?", (json.dumps(working, ensure_ascii=False), run_id))
        return binding

    def knowledge_save_request(self, run_id: str) -> dict:
        """Read existing UI selection; ordinary text creates no pre-plan state."""
        self.get_run(run_id)
        with self.db.connect() as connection:
            message = connection.execute("SELECT * FROM assistant_messages WHERE run_id=? AND role='user' ORDER BY seq DESC LIMIT 1", (run_id,)).fetchone()
            working = json.loads(connection.execute("SELECT working_state_json FROM assistant_runs WHERE id=?", (run_id,)).fetchone()[0])
        return working.get("knowledge_save") or {"source_message_id": message["id"],
            "request_key": "save-message:" + message["id"], "scope_text": message["content"]}

    def knowledge_message(self, message_id: str, *, thread_id: str, allow_operation_receipt: bool = False) -> dict:
        """Identity and suppression checks shared by save selection and history read."""
        from shiliu.assistant.memory import MemoryService
        with self.db.connect() as connection:
            row = connection.execute("""SELECT m.*,t.space_id FROM assistant_messages m
                JOIN assistant_threads t ON t.id=m.thread_id WHERE m.id=? AND m.thread_id=?
                AND t.principal_id=? AND m.role IN ('user','assistant')""", (message_id, thread_id, self.principal_id)).fetchone()
            if row is None:
                raise AssistantConflict("save_message_not_available")
            value = dict(row)
            suppressed = MemoryService(self.db).suppressed_source_message_ids(space_id=int(value['space_id']))
            user_ids = {r[0] for r in connection.execute("SELECT id FROM assistant_messages WHERE run_id=? AND role='user'", (value['run_id'],))}
            if message_id in suppressed or (value['role'] == 'assistant' and user_ids.intersection(suppressed)):
                raise AssistantConflict("save_message_suppressed")
            if value['role'] == 'assistant' and not connection.execute("SELECT 1 FROM assistant_run_events WHERE run_id=? AND event_type='run_completed' AND json_extract(payload_json,'$.message_id')=?", (value['run_id'], message_id)).fetchone():
                raise AssistantConflict("save_answer_not_available")
            if value['role'] == 'assistant':
                if not allow_operation_receipt and json.loads(value.get('provider_payload_json') or '{}').get('origin') == 'operation_receipt':
                    raise AssistantConflict('save_target_is_operation_receipt')
                from shiliu.assistant.provider import contains_unexecuted_tool_protocol
                if contains_unexecuted_tool_protocol(str(value['content'])):
                    raise AssistantConflict('save_answer_contains_tool_protocol')
            refs = json.loads(value.get('provider_payload_json') or '{}').get('dependency_refs') or []
            if not self._memory_refs_valid(connection, refs, space_id=int(value['space_id']), now=utc_now()):
                raise AssistantConflict("save_answer_dependencies_changed")
        return value

    def create_run(self, thread_id: str, *, text: str, request_id: str, answer_message_id: str | None = None,
                   receipt_only: bool = False) -> dict[str, Any]:
        if not text.strip():
            raise ValueError("input_empty")
        now = utc_now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            thread = connection.execute(
                "SELECT * FROM assistant_threads WHERE id=? AND principal_id=?",
                (thread_id, self.principal_id),
            ).fetchone()
            if thread is None:
                raise KeyError(thread_id)
            existing = connection.execute(
                "SELECT * FROM assistant_runs WHERE thread_id=? AND request_id=?",
                (thread_id, request_id),
            ).fetchone()
            if existing is not None:
                runs = [dict(item) for item in connection.execute(
                    "SELECT id,status FROM assistant_runs WHERE thread_id=? ORDER BY rowid", (thread_id,)
                )]
                return self._with_actions(
                    self._run(dict(existing)),
                    current=existing["id"] == self._current_action_run_id(runs),
                )
            active = connection.execute(
                """
                SELECT id FROM assistant_runs
                WHERE thread_id=? AND status IN ('queued','running')
                LIMIT 1
                """,
                (thread_id,),
            ).fetchone()
            latest = connection.execute(
                "SELECT status,working_state_json FROM assistant_runs WHERE thread_id=? ORDER BY rowid DESC LIMIT 1",
                (thread_id,),
            ).fetchone()
            if active is not None or (latest and latest["status"] in {"interrupted", "budget_exhausted", "failed"}):
                raise AssistantConflict("thread_has_active_run")
            run_id = f"arun_{uuid.uuid4().hex}"
            epoch = self._memory_epoch(connection)
            scope_row = connection.execute(
                "SELECT scope_version FROM assistant_spaces WHERE id=? AND principal_id=?",
                (thread["space_id"], self.principal_id),
            ).fetchone()
            if scope_row is None:
                raise KeyError(thread["space_id"])
            policy_rows = connection.execute(
                "SELECT key,value FROM assistant_runtime_state WHERE key IN ('auto_memory_enabled','auto_memory_generation')"
            ).fetchall()
            policy = {str(row["key"]): str(row["value"]) for row in policy_rows}
            admission = {
                "enabled": policy.get("auto_memory_enabled", "1") != "0",
                "generation": int(policy.get("auto_memory_generation", "0")),
            }
            connection.execute(
                """
                INSERT INTO assistant_runs(
                    id, thread_id, request_id, status, run_epoch, memory_epoch,
                    extraction_memory_epoch, observed_memory_epoch,
                    working_state_json, created_at, updated_at
                ) VALUES(?, ?, ?, 'queued', 1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id, thread_id, request_id, epoch, epoch, epoch,
                    json.dumps({"scope_version": int(scope_row["scope_version"]),
                                "auto_memory_admission": admission,
                                "task_subset": (json.loads(latest["working_state_json"] or "{}").get("task_subset") if latest else None)}), now, now,
                ),
            )
            message_id = f"amsg_{uuid.uuid4().hex}"
            seq = self._next_message_seq(connection, thread_id)
            connection.execute(
                """
                INSERT INTO assistant_messages(
                    id, thread_id, run_id, seq, role, content, created_at
                ) VALUES(?, ?, ?, ?, 'user', ?, ?)
                """,
                (message_id, thread_id, run_id, seq, text.strip(), now),
            )
            if answer_message_id:
                self._bind_save_request(connection, run_id, thread_id, message_id, text, answer_message_id, receipt_only=receipt_only)
            connection.execute(
                "UPDATE assistant_threads SET updated_at=? WHERE id=?", (now, thread_id)
            )
            self.mark_user_activity(connection)
            self._append_event(
                connection, run_id, "run_queued", {"message_id": message_id}
            )
            row = connection.execute(
                "SELECT * FROM assistant_runs WHERE id=?", (run_id,)
            ).fetchone()
        return self._with_actions(self._run(dict(row)))

    def claim_next_run(self) -> dict[str, Any] | None:
        now = utc_now()
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT r.* FROM assistant_runs r
                JOIN assistant_threads t ON t.id=r.thread_id
                JOIN assistant_spaces s ON s.id=t.space_id
                WHERE r.status='queued' AND s.enabled=1 AND s.principal_id=?
                ORDER BY r.created_at, r.id LIMIT 1
                """,
                (self.principal_id,),
            ).fetchone()
            if row is None:
                return None
            working = json.loads(row["working_state_json"] or "{}")
            working.setdefault("segment_started_at", now)
            budget = working.get("execution_budget")
            if budget and "paused_remaining" in budget:
                budget["deadline_at"] = (datetime.fromisoformat(now) + timedelta(seconds=budget.pop("paused_remaining"))).isoformat()
            updated = connection.execute(
                """
                UPDATE assistant_runs SET status='running', started_at=COALESCE(started_at, ?),
                    working_state_json=?, updated_at=? WHERE id=? AND status='queued'
                """,
                (now, json.dumps(working, ensure_ascii=False), now, row["id"]),
            )
            if updated.rowcount != 1:
                return None
            self._append_event(connection, str(row["id"]), "run_started", {})
            claimed = connection.execute(
                "SELECT * FROM assistant_runs WHERE id=?", (row["id"],)
            ).fetchone()
        return self._run(dict(claimed))

    def has_active_runs(self) -> bool:
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM assistant_runs r
                JOIN assistant_threads t ON t.id=r.thread_id
                WHERE t.principal_id=? AND r.status IN ('queued','running') LIMIT 1
                """,
                (self.principal_id,),
            ).fetchone()
        return row is not None

    def maintenance_idle(self, *, seconds: int = 180, startup_at: str | None = None,
                         connection: Any | None = None) -> bool:
        """Automatic maintenance may start or publish only after real foreground idle."""
        now = datetime.now(timezone.utc)
        if connection is None:
            with self.db.connect() as opened:
                return self.maintenance_idle(seconds=seconds, startup_at=startup_at,
                                             connection=opened)
        active = connection.execute(
                "SELECT 1 FROM assistant_runs WHERE status IN ('queued','running') LIMIT 1"
            ).fetchone()
        latest = connection.execute(
                "SELECT MAX(stamp) FROM ("
                "SELECT MAX(created_at) AS stamp FROM assistant_messages WHERE role='user' "
                "UNION ALL SELECT MAX(completed_at) FROM assistant_runs "
                "UNION ALL SELECT value FROM assistant_runtime_state WHERE key='last_user_activity_at')"
            ).fetchone()[0]
        if active:
            return False
        dates = [datetime.fromisoformat(value) for value in (latest, startup_at) if value]
        return not dates or (now - max(dates)).total_seconds() >= seconds

    def mark_user_activity(self, connection: Any | None = None) -> None:
        if connection is None:
            with self.db.connect() as opened:
                self.mark_user_activity(opened)
            return
        now = utc_now()
        connection.execute(
            "INSERT INTO assistant_runtime_state(key,value,updated_at) VALUES('last_user_activity_at',?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
            (now, now),
        )

    def save_task_focus(self, run_id: str, *, epoch: int, focus: dict[str, Any]) -> dict[str, Any]:
        """Persist changed navigation only, anchored to the actual user and evidence."""
        focus = {key: ([str(item).strip() for item in value] if isinstance(value, list)
                       else value.strip() if isinstance(value, str) else value)
                 for key, value in focus.items()}
        focus["selected_source_refs"] = sorted(set(focus.get("selected_source_refs") or []))
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT thread_id,working_state_json FROM assistant_runs "
                "WHERE id=? AND status='running' AND run_epoch=? AND cancel_requested=0",
                (run_id, epoch),
            ).fetchone()
            if row is None:
                raise AssistantConflict("run_fenced")
            user = connection.execute(
                "SELECT id,content,seq FROM assistant_messages WHERE run_id=? AND role='user' "
                "ORDER BY seq DESC LIMIT 1", (run_id,),
            ).fetchone()
            if user is None:
                raise AssistantConflict("task_user_message_missing")
            state = json.loads(row["working_state_json"] or "{}")
            space = connection.execute("SELECT space_id FROM assistant_threads WHERE id=?",
                                       (row["thread_id"],)).fetchone()
            observed = state.get("context_observation") or {}
            # Bind the draft only to user turns actually admitted into this
            # model context. Superseded turns and trimmed history cannot become
            # dependencies of a new draft after correction or forgetting.
            inherited_ids = [str(value) for value in observed.get("visible_user_message_ids") or []]
            dependencies = [str(value) for value in observed.get("dependency_refs") or []]
            memories = connection.execute(
                "SELECT id,version,source_message_ids_json FROM assistant_memories "
                "WHERE principal_id=? AND status='active' AND "
                "(scope_kind='user' OR (scope_kind='space' AND scope_id=?))",
                (self.principal_id, str(space["space_id"])),
            ).fetchall()
            for memory in memories:
                if set(json.loads(memory["source_message_ids_json"] or "[]")).intersection(inherited_ids):
                    dependencies.append(f"memory:{memory['id']}:{int(memory['version'])}")
            # A focus receipt pointing back to itself is not new material provenance.
            dependencies = [ref for ref in dependencies if not (
                ref.startswith("run-result:") and connection.execute(
                    "SELECT 1 FROM assistant_tool_calls WHERE run_id=? AND call_id=? AND name='task_focus'",
                    tuple(ref.split(":", 2)[1:])).fetchone())]
            candidate = {**focus,
                                   "dependency_refs": list(dict.fromkeys(dependencies)),
                                   "inherited_message_ids": list(dict.fromkeys(inherited_ids)),
                                   "source_message_id": str(user["id"]),
                                   "source_message_seq": int(user["seq"]),
                                   "user_quote": str(user["content"])[:2000]}
            if state.get("task_focus") == candidate:
                return {**candidate, "changed": False}
            state["task_focus"] = candidate
            self.guard_tool_operation(connection)
            connection.execute(
                "UPDATE assistant_runs SET working_state_json=?,updated_at=? "
                "WHERE id=? AND status='running' AND run_epoch=?",
                (json.dumps(state, ensure_ascii=False), utc_now(), run_id, epoch),
            )
        return {**state["task_focus"], "changed": True}

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT r.* FROM assistant_runs r
                JOIN assistant_threads t ON t.id=r.thread_id
                WHERE r.id=? AND t.principal_id=?
                """,
                (run_id, self.principal_id),
            ).fetchone()
            runs = [dict(item) for item in connection.execute(
                "SELECT id,status FROM assistant_runs WHERE thread_id=? ORDER BY rowid",
                (row["thread_id"],),
            )] if row is not None else []
        if row is None:
            raise KeyError(run_id)
        return self._with_actions(
            self._run(dict(row)), current=run_id == self._current_action_run_id(runs)
        )

    def set_task_subset(self, run_id: str, *, epoch: int, video_ids: list[int], source_message_id: str | None = None, basis_quote: str | None = None) -> None:
        if not video_ids:
            raise ValueError("empty_task_subset")
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT working_state_json FROM assistant_runs WHERE id=? "
                                     "AND status='running' AND run_epoch=?", (run_id, epoch)).fetchone()
            if row is None:
                raise AssistantConflict("run_fenced")
            working = json.loads(row[0] or "{}")
            working["task_subset"] = {"video_ids": sorted(set(video_ids)),
                                      **({"source_message_id": source_message_id, "basis_quote": basis_quote} if source_message_id else {})}
            working.pop("task_focus", None)
            working.pop("answer_draft", None)
            connection.execute("UPDATE assistant_runs SET working_state_json=? WHERE id=?",
                               (json.dumps(working, ensure_ascii=False), run_id))
            self.mark_user_activity(connection)
            self._append_event(connection, run_id, "task_scope_changed", working["task_subset"])

    def task_space(self, thread_id: str) -> dict[str, Any]:
        thread = self.get_thread(thread_id)
        space = self.get_space(int(thread["space_id"]))
        subset = (thread["runs"][-1]["working_state"].get("task_subset") if thread["runs"] else None)
        if subset:
            allowed = set(space["video_ids"])
            space["video_ids"] = [int(v) for v in subset["video_ids"] if not allowed or int(v) in allowed]
            # An empty intersection must never mean unrestricted in SourceScope.
            space["video_ids"] = space["video_ids"] or [-1]
            space["task_subset"] = subset
        return space

    def run_context(self, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        thread = self.get_thread(str(run["thread_id"]))
        space = self.task_space(str(thread["id"]))
        current_scope_version = int(space["scope_version"])
        version_by_run = {
            str(item["id"]): int(item["working_state"].get("scope_version", 1))
            for item in thread["runs"]
        }
        thread["messages"] = [
            item for item in thread["messages"]
            if item["run_id"] is not None
            and version_by_run.get(str(item["run_id"])) == current_scope_version
        ]
        subset = run["working_state"].get("task_subset")
        if subset:
            same_runs = {item["id"] for item in thread["runs"]
                         if item["working_state"].get("task_subset") == subset}
            allowed_ids = set(space["video_ids"])
            accepted_calls = set()
            for item in thread["messages"]:
                if item["role"] != "tool":
                    continue
                result = json.loads(item["content"] or "{}")
                refs = result.get("source_refs") or []
                if refs and all(str(ref).startswith("video:") and int(str(ref).split(":")[1]) in allowed_ids for ref in refs):
                    accepted_calls.add(json.loads(item.get("provider_payload_json") or "{}").get("tool_call_id"))
            projected_messages = []
            for item in thread["messages"]:
                if item["role"] == "user" or item["run_id"] in same_runs:
                    projected_messages.append(item)
                    continue
                payload = json.loads(item.get("provider_payload_json") or "{}")
                if item["role"] == "tool" and payload.get("tool_call_id") in accepted_calls:
                    projected_messages.append(item)
                elif item["role"] == "assistant" and payload.get("tool_calls"):
                    calls = [call for call in payload["tool_calls"] if call["id"] in accepted_calls]
                    if calls:
                        projected_messages.append({**item, "content": "", "provider_payload_json": json.dumps({**payload,"tool_calls":calls})})
            thread["messages"] = projected_messages
            thread["runs"] = [{**item, "working_state": item["working_state"] if item["id"] in same_runs else {}}
                              for item in thread["runs"]]
            thread.pop("task_note", None)
            thread.pop("task_focus", None)
        bootstrap_results = []
        for prior_run in thread["runs"]:
            marker = prior_run["working_state"].get("knowledge_bootstrap") or {}
            if marker.get("status") != "completed":
                continue
            try:
                resolved = self.resolve_run_result(marker["result_ref"], current_thread_id=str(thread["id"]),
                                                   current_scope_version=current_scope_version)
                if not resolved["result"].get("coverage", {}).get("discarded"):
                    bootstrap_results.append(resolved)
            except (KeyError, ValueError):
                continue
        return {"run": run, "thread": thread, "space": space, "bootstrap_results": bootstrap_results}

    def working_run_context(self, run_id: str) -> dict[str, Any]:
        """C2 component entry: raw identities, no old Composer projection or Note writes."""
        run = self.get_run(run_id)
        thread = self.get_thread(str(run['thread_id']), include_internal=True)
        return {'run': run, 'thread': thread, 'space': self.task_space(str(thread['id']))}

    @staticmethod
    def message_context_fingerprint(message: dict) -> str:
        payload = json.loads(message.get('provider_payload_json') or '{}')
        payload.pop('model_projection', None)
        value = {k: message.get(k) for k in ('id', 'thread_id', 'run_id', 'seq', 'role', 'created_at')}
        value.update(content=message.get('_raw_content', message.get('content')),
                     resolved_content=message.get('content'), payload=payload)
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    @staticmethod
    def working_source_guard(connection: Any, *, space_id: int) -> str:
        # Short transaction guard over source/version/scope metadata, not content copies.
        queries = [
            ("SELECT principal_id,video_id,current_revision FROM assistant_source_heads ORDER BY id", ()),
            ("SELECT id,status,is_ignored,removed_at,updated_at FROM videos ORDER BY id", ()),
            ("SELECT id,status FROM favorite_sources ORDER BY id", ()),
            ("SELECT source_id,video_id,removed_at FROM video_source_memberships ORDER BY source_id,video_id", ()),
            ("SELECT id,version,status FROM assistant_wiki_pages WHERE space_id=? ORDER BY id", (space_id,)),
        ]
        values = [[tuple(row) for row in connection.execute(query, params)] for query, params in queries]
        return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()

    @staticmethod
    def working_navigation_guard(connection: Any, *, thread_id: str) -> str:
        values = []
        for row in connection.execute('SELECT id,working_state_json FROM assistant_runs WHERE thread_id=? ORDER BY rowid',
                                      (thread_id,)):
            working = json.loads(row['working_state_json'] or '{}')
            values.append([row['id'], {key: working.get(key) for key in
                           ('task_focus', 'task_subset', 'knowledge_save', 'knowledge_bootstrap')}])
        return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def save_working_context(self, run_id: str, *, epoch: int, expected_revision: int,
                             state: dict, projections: dict[str, dict],
                             message_frontier: int, memory_epoch: int, source_guard: str,
                             scope_version: int, task_subset: dict | None,
                             dependency_refs: list[str], navigation_guard: str,
                             checkpoint_candidate: dict | None = None, expected_note_version: int = 0) -> None:
        """Freeze first representations and the active sequence in one fenced CAS.

        Checkpoint replacement uses this same transaction; model generation and
        service-level dependency validation must finish before entering it.
        """
        with self.db.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            run = connection.execute(
                "SELECT r.*,t.context_state_json,t.space_id FROM assistant_runs r "
                "JOIN assistant_threads t ON t.id=r.thread_id WHERE r.id=? AND t.principal_id=?",
                (run_id, self.principal_id)).fetchone()
            if (run is None or run['status'] != 'running' or int(run['run_epoch']) != epoch
                    or run['cancel_requested']):
                raise AssistantConflict('run_fenced')
            prior = json.loads(run['context_state_json'] or '{}')
            working = json.loads(run['working_state_json'] or '{}')
            current_scope = connection.execute('SELECT scope_version FROM assistant_spaces WHERE id=?',
                                               (run['space_id'],)).fetchone()[0]
            frontier = connection.execute('SELECT COALESCE(MAX(seq),0) FROM assistant_messages WHERE thread_id=?',
                                          (run['thread_id'],)).fetchone()[0]
            if (int(prior.get('revision') or 0) != expected_revision
                    or int(state.get('revision') or 0) != expected_revision + 1
                    or state.get('format_version') != 1 or int(current_scope) != scope_version
                    or working.get('task_subset') != task_subset or frontier != message_frontier
                    or self._memory_epoch(connection) != memory_epoch
                    or not self._memory_refs_valid(connection, dependency_refs, space_id=int(run['space_id']), now=utc_now())
                    or self.working_source_guard(connection, space_id=int(run['space_id'])) != source_guard
                    or self.working_navigation_guard(connection, thread_id=str(run['thread_id'])) != navigation_guard):
                raise AssistantConflict('working_context_changed')
            if checkpoint_candidate is not None:
                execution = working.get('execution_budget') or {}
                if (working.get('finish_requested') or execution.get('final_dispatched')
                        or (execution.get('deadline_at') and
                            (datetime.fromisoformat(execution['deadline_at']) - datetime.now(timezone.utc)).total_seconds()
                            <= ASSISTANT_FINAL_SECONDS)):
                    raise AssistantConflict('compaction_control_changed')
                existing = connection.execute('SELECT id,note_version FROM assistant_task_notes WHERE thread_id=? AND task_segment=1',
                                              (run['thread_id'],)).fetchone()
                if int(existing['note_version'] if existing else 0) != expected_note_version:
                    raise AssistantConflict('working_checkpoint_changed')
                note = checkpoint_candidate
                if (note['note_version'] != expected_note_version + 1
                        or (existing and existing['id'] != note['id'])):
                    raise AssistantConflict('working_checkpoint_changed')
                connection.execute(
                    "INSERT INTO assistant_task_notes(id,thread_id,task_segment,note_version,covered_until_message_seq,"
                    "source_run_ids_json,dependencies_json,scope_version,memory_generation,checkpoint_json,created_at,updated_at) "
                    "VALUES(?,?,1,?,?,?,?,?,?,?,?,?) ON CONFLICT(thread_id,task_segment) DO UPDATE SET "
                    "note_version=excluded.note_version,covered_until_message_seq=excluded.covered_until_message_seq,"
                    "source_run_ids_json=excluded.source_run_ids_json,dependencies_json=excluded.dependencies_json,"
                    "scope_version=excluded.scope_version,memory_generation=excluded.memory_generation,"
                    "checkpoint_json=excluded.checkpoint_json,status='active',goal='',explicit_constraints_json='[]',"
                    "searched_scope_and_material_refs_json='[]',findings_json='[]',open_questions_json='[]',next_actions_json='[]',"
                    "updated_at=excluded.updated_at",
                    (note['id'],run['thread_id'],note['note_version'],note['covered_until_message_seq'],
                     json.dumps(note['source_run_ids']),json.dumps(note['dependencies']),scope_version,memory_epoch,
                     json.dumps(note['checkpoint'],ensure_ascii=False),utc_now(),utc_now()))
            self.install_working_context(connection, thread_id=str(run['thread_id']),
                                         state=state, projections=projections)

    def record_context_attempt(self, candidate: Any, *, attempted: bool, reason: str = '') -> None:
        """Record scheduling only; pending tool representations are never frozen here."""
        with self.db.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            run = connection.execute('SELECT r.*,t.context_state_json FROM assistant_runs r JOIN assistant_threads t '
                                     'ON t.id=r.thread_id WHERE r.id=?', (candidate.run_id,)).fetchone()
            if not run or run['status'] != 'running' or run['run_epoch'] != candidate.epoch or run['cancel_requested']:
                raise AssistantConflict('run_fenced')
            prior = json.loads(run['context_state_json'] or '{}')
            if int(prior.get('revision') or 0) != candidate.expected_revision:
                raise AssistantConflict('working_context_changed')
            state = prior or {**candidate.state, 'entries': [], 'checkpoint': None, 'materialized_through_seq': 0}
            state['revision'] = candidate.expected_revision + 1
            state['pressure_event_attempted'] = attempted
            if attempted:
                state['last_attempt_history_frontier'] = candidate.state['materialized_through_seq']
                state['last_attempt_reason'] = reason
            connection.execute('UPDATE assistant_threads SET context_state_json=? WHERE id=?',
                               (json.dumps(state,ensure_ascii=False),run['thread_id']))

    def install_working_context(self, connection: Any, *, thread_id: str,
                                state: dict, projections: dict[str, dict]) -> None:
        """Same-connection installer for prepared input (caller owns admission/CAS)."""
        from shiliu.assistant.delivery import validate_model_sequence
        entries = state.get('entries') or []
        ids = [entry['message_id'] for entry in entries if entry.get('kind') == 'message']
        if len(ids) != len(set(ids)) or set(projections) - set(ids):
            raise AssistantConflict('working_context_message_identity')
        binding = state.get('checkpoint')
        if binding:
            note = connection.execute('SELECT id,note_version,status,checkpoint_json FROM assistant_task_notes '
                                      'WHERE thread_id=? AND task_segment=1', (thread_id,)).fetchone()
            if (note is None or note['id'] != binding['id'] or note['note_version'] != binding['version']
                    or note['status'] != 'active' or json.loads(note['checkpoint_json']).get('format_version') != 1):
                raise AssistantConflict('working_checkpoint_changed')
        sequence, updates = [], []
        for entry in entries:
            if entry.get('kind') == 'block':
                sequence.append({'role': 'system', 'content': entry['content']})
                continue
            if entry.get('kind') != 'message':
                raise AssistantConflict('working_context_entry_invalid')
            row = connection.execute(
                "SELECT m.*,t.result_json AS resolved_tool_result_json FROM assistant_messages m "
                "LEFT JOIN assistant_tool_calls t ON t.run_id=m.run_id "
                "AND t.call_id=json_extract(m.provider_payload_json,'$.tool_call_id') "
                "WHERE m.id=? AND m.thread_id=?", (entry['message_id'], thread_id)).fetchone()
            if row is None:
                raise AssistantConflict('working_context_message_missing')
            fingerprint_row = dict(row)
            if row['role'] == 'tool' and json.loads(row['content'] or '{}').get('_assistant_result_ref'):
                fingerprint_row['_raw_content'] = row['content']
                fingerprint_row['content'] = row['resolved_tool_result_json'] or json.dumps({'status': 'error', 'error_code': 'tool_result_unavailable'})
            payload = json.loads(row['provider_payload_json'] or '{}')
            stored = payload.get('model_projection')
            proposed = projections.get(entry['message_id'])
            projection = stored or proposed
            if (not projection or projection.get('format_version') != 1
                    or projection.get('source_fingerprint') != self.message_context_fingerprint(fingerprint_row)
                    or projection.get('message', {}).get('role') != row['role']):
                raise AssistantConflict('working_projection_invalid')
            if stored and proposed and {k: v for k, v in stored.items() if k != 'delivery'} != {k: v for k, v in proposed.items() if k != 'delivery'}:
                raise AssistantConflict('working_projection_frozen')
            sequence.append(projection['message'])
            if not stored:
                payload['model_projection'] = projection
                updates.append((json.dumps(payload, ensure_ascii=False), row['id']))
        validate_model_sequence(sequence)
        for payload, message_id in updates:
            connection.execute('UPDATE assistant_messages SET provider_payload_json=? WHERE id=?', (payload, message_id))
        connection.execute('UPDATE assistant_threads SET context_state_json=? WHERE id=?',
                           (json.dumps(state, ensure_ascii=False), thread_id))

    def pending_tool_batch(self, run_id: str) -> list[dict[str, Any]]:
        """Return only calls whose durable assistant tool message lacks a result message."""
        context = self.run_context(run_id)
        messages = [
            item for item in context["thread"]["messages"]
            if item["run_id"] == run_id
        ]
        for index in range(len(messages) - 1, -1, -1):
            item = messages[index]
            if item["role"] != "assistant":
                continue
            payload = json.loads(item.get("provider_payload_json") or "{}")
            calls = payload.get("tool_calls") or []
            if not calls:
                continue
            returned = {
                json.loads(result.get("provider_payload_json") or "{}").get("tool_call_id")
                for result in messages[index + 1:] if result["role"] == "tool"
            }
            if len(returned.intersection({call.get("id") for call in calls})) == len(calls):
                return []
            return [dict(call) for call in calls]
        return []

    def tool_result_message_exists(self, run_id: str, call_id: str) -> bool:
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT provider_payload_json FROM assistant_messages
                WHERE run_id=? AND role='tool'
                """,
                (run_id,),
            ).fetchall()
        return any(
            json.loads(row["provider_payload_json"]).get("tool_call_id") == call_id
            for row in rows
        )

    def completed_tool_message_count(self, run_id: str) -> int:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM assistant_messages WHERE run_id=? AND role='tool'",
                (run_id,),
            ).fetchone()
        return int(row["n"])

    def resolve_run_result(
        self,
        result_ref: str,
        *,
        current_thread_id: str,
        current_scope_version: int,
    ) -> dict[str, Any]:
        parts = result_ref.split(":")
        if len(parts) == 3 and parts[0] == "run-result":
            requested_run, call_id = parts[1], parts[2]
        elif len(parts) == 2 and parts[0] == "tool_call_id":
            requested_run, call_id = None, parts[1]
        else:
            raise ValueError("invalid_result_ref")
        if not call_id:
            raise ValueError("invalid_result_ref")
        conditions = ["th.id=?", "t.call_id=?", "th.principal_id=?"]
        params: list[Any] = [current_thread_id, call_id, self.principal_id]
        if requested_run is not None:
            conditions.append("t.run_id=?")
            params.append(requested_run)
        with self.db.connect() as connection:
            row = connection.execute(
                f"""
                SELECT t.run_id, t.call_id, t.name, t.args_json, t.result_json,
                       r.working_state_json, th.id AS thread_id
                FROM assistant_tool_calls t
                JOIN assistant_runs r ON r.id=t.run_id
                JOIN assistant_threads th ON th.id=r.thread_id
                WHERE {' AND '.join(conditions)} AND t.status='completed'
                ORDER BY t.completed_at DESC LIMIT 1
                """,
                params,
            ).fetchone()
        if row is None or not row["result_json"]:
            raise KeyError(result_ref)
        working = json.loads(row["working_state_json"] or "{}")
        if int(working.get("scope_version", 1)) != int(current_scope_version):
            raise ValueError("result_outside_current_scope")
        return {
            "run_id": str(row["run_id"]),
            "call_id": str(row["call_id"]),
            "name": str(row["name"]),
            "arguments": json.loads(row["args_json"] or "{}"),
            "result": json.loads(row["result_json"]),
            "result_ref": f"run-result:{row['run_id']}:{row['call_id']}",
        }

    def save_step(self, run_id: str, *, step_count: int, tool_count: int, usage: dict[str, Any]) -> None:
        with self.db.connect() as connection:
            current = connection.execute("SELECT working_state_json,usage_json FROM assistant_runs WHERE id=?", (run_id,)).fetchone()
            if current and json.loads(current["working_state_json"] or "{}").get("execution_budget"):
                usage = json.loads(current["usage_json"] or "{}")
            connection.execute(
                """
                UPDATE assistant_runs SET step_count=?, tool_count=?, usage_json=?, updated_at=?
                WHERE id=? AND status='running'
                """,
                (step_count, tool_count, json.dumps(usage), utc_now(), run_id),
            )

    def add_late_run_usage(self, run_id: str, usage: dict[str, Any]) -> None:
        """Account for a fenced remote response without admitting its answer or tools."""
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT usage_json,working_state_json,status FROM assistant_runs WHERE id=?", (run_id,)
            ).fetchone()
            if row is None:
                return
            working = json.loads(row["working_state_json"] or "{}")
            merged = (dict(working.get("late_model_usage") or {}) if row["status"] == "running"
                      else json.loads(row["usage_json"] or "{}"))
            for key, amount in usage.items():
                if isinstance(amount, (int, float)) and not isinstance(amount, bool):
                    merged[key] = merged.get(key, 0) + amount
            if row["status"] == "running":
                working["late_model_usage"] = merged
                connection.execute("UPDATE assistant_runs SET working_state_json=? WHERE id=?",
                                   (json.dumps(working, ensure_ascii=False), run_id))
            else:
                connection.execute("UPDATE assistant_runs SET usage_json=? WHERE id=?",
                                   (json.dumps(merged), run_id))

    def record_late_tool_completion(self, run_id: str, ordinal: int) -> None:
        with self.db.connect() as connection:
            connection.execute("UPDATE assistant_runs SET tool_count=MAX(tool_count,?) "
                               "WHERE id=? AND status='cancelled'", (ordinal, run_id))

    def save_context_observation(
        self, run_id: str, *, epoch: int, metadata: dict[str, Any]
    ) -> bool:
        now = utc_now()
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT working_state_json FROM assistant_runs WHERE id=? AND status='running' AND run_epoch=?",
                (run_id, epoch),
            ).fetchone()
            if row is None:
                return False
            working = json.loads(row["working_state_json"] or "{}")
            working["context_observation"] = metadata
            observed = int(metadata["observed_memory_epoch"])
            updated = connection.execute(
                """
                UPDATE assistant_runs SET observed_memory_epoch=?, memory_epoch=?,
                    working_state_json=?, updated_at=?
                WHERE id=? AND status='running' AND run_epoch=?
                """,
                (observed, observed, json.dumps(working, ensure_ascii=False), now, run_id, epoch),
            )
        return updated.rowcount == 1

    def record_provider_response(self, run_id: str, turn: Any, *, late: bool, call_id: str | None = None) -> None:
        identity = getattr(turn, "opaque_provider_state", {})
        usage = getattr(turn, "usage", {}) or {}
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if call_id and connection.execute("SELECT 1 FROM assistant_run_events WHERE run_id=? AND event_type='provider_response' AND json_extract(payload_json,'$.call_id')=?", (run_id, call_id)).fetchone():
                return
            row = connection.execute("SELECT working_state_json,usage_json,status FROM assistant_runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                return
            working = json.loads(row["working_state_json"] or "{}")
            if working.get("execution_budget") and call_id:
                aggregate = json.loads(row["usage_json"] or "{}")
                for key, value in usage.items():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        aggregate[key] = aggregate.get(key, 0) + value
                working["execution_budget"]["known_tokens"] += self.known_tokens(usage)
                working["execution_budget"]["unknown_responses"] += int(not usage)
                if late:
                    diagnostics = working.setdefault("late_model_usage", {})
                    for key, value in usage.items():
                        if isinstance(value, (int, float)) and not isinstance(value, bool):
                            diagnostics[key] = diagnostics.get(key, 0) + value
                working["usage_includes_late"] = True
                connection.execute("UPDATE assistant_runs SET working_state_json=?,usage_json=? WHERE id=?",
                                   (json.dumps(working, ensure_ascii=False), json.dumps(aggregate), run_id))
            self._append_event(connection, run_id, "provider_response", {
                **identity, "call_id": call_id, "late": late, "usage": usage,
                "content_characters": len(getattr(turn, "text", "")), "tool_calls": len(getattr(turn, "tool_calls", [])),
            })

    def save_answer_draft(self, run_id: str, *, epoch: int, text: str,
                          allow_finish: bool = False, call_id: str | None = None,
                          start_call: bool = False) -> bool:
        # Drafts are overwrite-only snapshots, never chat messages or write receipts.
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM assistant_runs WHERE id=?", (run_id,)).fetchone()
            if row is None or row["status"] != "running" or int(row["run_epoch"]) != epoch:
                return False
            working = json.loads(row["working_state_json"] or "{}")
            # Ownership is checked before dependency invalidation: an obsolete
            # call must neither publish text nor clear the current call's draft.
            if not start_call and working.get("answer_draft_call_id") != call_id:
                return False
            if start_call:
                working["answer_draft_call_id"] = call_id
            observation = working.get("context_observation") or {}
            space_id = connection.execute("SELECT space_id FROM assistant_threads WHERE id=?",
                                          (row["thread_id"],)).fetchone()[0]
            budget = working.get("execution_budget") or {}
            within_deadline = not budget or datetime.fromisoformat(budget["deadline_at"]) > datetime.now(timezone.utc)
            valid = within_deadline and (not working.get("finish_requested") or allow_finish) and self._memory_refs_valid(
                connection, observation.get("dependency_refs") or [], space_id=int(space_id), now=utc_now())
            working["answer_draft"] = {"text": text if valid else "", "epoch": epoch,
                                       "status": "generating" if valid else "invalidated"}
            connection.execute("UPDATE assistant_runs SET working_state_json=? WHERE id=?",
                               (json.dumps(working, ensure_ascii=False), run_id))
            return valid

    def confirm_model_delivery(self, run_id: str, *, epoch: int,
                               spans: list[dict[str, Any]],
                               materials: list[dict[str, Any]] | None = None,
                               message_ids: list[str] | None = None,
                               context_revision: int | None = None) -> None:
        if not spans and not materials and not message_ids:
            return
        with self.db.connect() as connection:
            if message_ids:
                connection.execute('BEGIN IMMEDIATE')
            row = connection.execute(
                "SELECT working_state_json FROM assistant_runs WHERE id=? AND status='running' AND run_epoch=?",
                (run_id, epoch),
            ).fetchone()
            if row is None:
                if message_ids:
                    raise AssistantConflict('run_fenced')
                return
            if message_ids:
                state_row = connection.execute(
                    'SELECT t.context_state_json,t.id FROM assistant_threads t JOIN assistant_runs r ON r.thread_id=t.id WHERE r.id=?',
                    (run_id,)).fetchone()
                state = json.loads(state_row['context_state_json'] or '{}')
                active = {e['message_id'] for e in state.get('entries') or [] if e.get('kind') == 'message'}
                if context_revision != state.get('revision') or not set(message_ids).issubset(active):
                    raise AssistantConflict('working_delivery_changed')
                spans, materials = [], []
                for message_id in dict.fromkeys(message_ids):
                    message = connection.execute('SELECT provider_payload_json FROM assistant_messages WHERE id=? AND thread_id=?',
                                                 (message_id, state_row['id'])).fetchone()
                    payload = json.loads(message['provider_payload_json'] or '{}')
                    projection = payload.get('model_projection')
                    if not projection:
                        raise AssistantConflict('working_delivery_projection_missing')
                    projection['delivery'] = {'confirmed': True, 'run_id': run_id,
                                              'revision': context_revision}
                    spans.extend(projection.get('read_spans') or [])
                    materials.extend(projection.get('materials') or [])
                    connection.execute('UPDATE assistant_messages SET provider_payload_json=? WHERE id=?',
                                       (json.dumps(payload, ensure_ascii=False), message_id))
                for entry in state.get('entries') or []:
                    if entry.get('kind') == 'block':
                        materials.extend(entry.get('materials') or [])
                        entry['delivery'] = {'confirmed': True, 'run_id': run_id, 'revision': context_revision}
                connection.execute('UPDATE assistant_threads SET context_state_json=? WHERE id=?',
                                   (json.dumps(state,ensure_ascii=False), state_row['id']))
            working = json.loads(row["working_state_json"] or "{}")
            existing = working.get("model_delivered_read_spans") or []
            seen = {json.dumps(value, sort_keys=True) for value in existing}
            for span in spans:
                key = json.dumps(span, sort_keys=True)
                if key not in seen:
                    existing.append(span)
                    seen.add(key)
            working["model_delivered_read_spans"] = existing[-200:]
            delivered = working.get("model_delivered_materials") or []
            seen_materials = {json.dumps(value, sort_keys=True) for value in delivered}
            for material in materials or []:
                key = json.dumps(material, sort_keys=True)
                if key not in seen_materials:
                    delivered.append(material)
                    seen_materials.add(key)
            working["model_delivered_materials_truncated"] = bool(
                working.get("model_delivered_materials_truncated") or len(delivered) > 160
            )
            working["model_delivered_materials"] = delivered[-160:]
            connection.execute(
                "UPDATE assistant_runs SET working_state_json=? WHERE id=? AND status='running' AND run_epoch=?",
                (json.dumps(working, ensure_ascii=False), run_id, epoch),
            )

    @staticmethod
    def confirmed_context_materials(connection: Any, *, thread_id: str,
                                    run_id: str | None = None) -> list[dict]:
        """Durable evidence survives Run aggregate display limits and restarts."""
        materials = []
        for row in connection.execute(
            "SELECT provider_payload_json FROM assistant_messages WHERE thread_id=? "
            "AND (? IS NULL OR run_id=?) AND json_extract(provider_payload_json,'$.model_projection.delivery.confirmed')=1",
            (thread_id, run_id, run_id)):
            projection = json.loads(row[0])['model_projection']
            materials.extend(projection.get('materials') or [])
        return materials

    def context_read_coverage(self, thread_id: str, *, source_ref: str, view: str) -> dict:
        """Derive coverage from confirmed ranges of this exact source/version/view."""
        self.get_thread(thread_id)
        ranges, totals = [], set()
        with self.db.connect() as connection:
            for row in connection.execute(
                "SELECT provider_payload_json FROM assistant_messages WHERE thread_id=? "
                "AND json_extract(provider_payload_json,'$.model_projection.delivery.confirmed')=1", (thread_id,)):
                for span in json.loads(row[0])['model_projection'].get('read_spans') or []:
                    if span.get('source_ref') == source_ref and span.get('view') == view:
                        start, end, total = int(span['start']), int(span['end']), int(span['total'])
                        if not 0 <= start <= end <= total:
                            raise AssistantConflict('working_delivery_range_invalid')
                        ranges.append((start, end)); totals.add(total)
        if len(totals) > 1:
            raise AssistantConflict('working_delivery_version_mismatch')
        merged = []
        for start, end in sorted(ranges):
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        total, missing, cursor = next(iter(totals), None), [], 0
        for start, end in merged:
            if start > cursor:
                missing.append([cursor, start])
            cursor = end
        if total is not None and cursor < total:
            missing.append([cursor, total])
        return {'source_ref': source_ref, 'view': view, 'total': total,
                'ranges': merged, 'missing_ranges': missing}

    def mark_context_recovery_attempt(self, run_id: str, *, epoch: int) -> bool:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT working_state_json FROM assistant_runs WHERE id=? AND status='running' AND run_epoch=?",
                (run_id, epoch),
            ).fetchone()
            if row is None:
                return False
            working = json.loads(row["working_state_json"] or "{}")
            if int(working.get("context_recovery_attempts", 0)) >= 1:
                return False
            working["context_recovery_attempts"] = 1
            connection.execute(
                "UPDATE assistant_runs SET working_state_json=? WHERE id=? AND status='running' AND run_epoch=?",
                (json.dumps(working, ensure_ascii=False), run_id, epoch),
            )
        return True

    def record_compaction(self, run_id: str, *, epoch: int,
                          usage: dict[str, Any], input_characters: int,
                          latency_ms: float) -> None:
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT working_state_json FROM assistant_runs WHERE id=? AND status='running' AND run_epoch=?",
                (run_id, epoch),
            ).fetchone()
            if row is None:
                return
            working = json.loads(row["working_state_json"] or "{}")
            observation = dict(working.get("compaction_observation") or {})
            observation["calls"] = int(observation.get("calls") or 0) + 1
            observation["input_characters"] = int(observation.get("input_characters") or 0) + input_characters
            observation["latency_ms"] = round(float(observation.get("latency_ms") or 0) + latency_ms, 3)
            totals = dict(observation.get("usage") or {})
            for key, value in usage.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    totals[key] = totals.get(key, 0) + value
            observation["usage"] = totals
            observation["usage_known_calls"] = int(observation.get("usage_known_calls") or 0) + bool(usage)
            working["compaction_observation"] = observation
            connection.execute(
                "UPDATE assistant_runs SET working_state_json=? WHERE id=? AND status='running' AND run_epoch=?",
                (json.dumps(working, ensure_ascii=False), run_id, epoch),
            )

    def save_assistant_tool_message(
        self, run_id: str, *, content: str, provider_payload: dict[str, Any]
    ) -> str:
        return self._save_message(
            run_id, role="assistant", content=content, provider_payload=provider_payload
        )

    def save_tool_result_message(
        self, run_id: str, *, content: str, provider_payload: dict[str, Any]
    ) -> str:
        call_id = str(provider_payload.get("tool_call_id") or "")
        with self.db.connect() as connection:
            result = connection.execute("SELECT result_json FROM assistant_tool_calls "
                "WHERE run_id=? AND call_id=? AND status='completed'", (run_id, call_id)).fetchone()
        if result and result["result_json"] and json.loads(result["result_json"]) == json.loads(content):
            # The immutable tool receipt owns the body. New history rows point
            # at it; old full-body history remains readable without migration.
            content = json.dumps({"_assistant_result_ref": f"run-result:{run_id}:{call_id}"})
        return self._save_message(
            run_id, role="tool", content=content, provider_payload=provider_payload
        )

    def _save_message(
        self, run_id: str, *, role: str, content: str, provider_payload: dict[str, Any]
    ) -> str:
        now = utc_now()
        with self.db.connect() as connection:
            run = connection.execute(
                "SELECT thread_id FROM assistant_runs WHERE id=?", (run_id,)
            ).fetchone()
            if run is None:
                raise KeyError(run_id)
            message_id = f"amsg_{uuid.uuid4().hex}"
            connection.execute(
                """
                INSERT INTO assistant_messages(
                    id, thread_id, run_id, seq, role, content, provider_payload_json, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    run["thread_id"],
                    run_id,
                    self._next_message_seq(connection, str(run["thread_id"])),
                    role,
                    content,
                    json.dumps(provider_payload, ensure_ascii=False),
                    now,
                ),
            )
        return message_id

    def set_knowledge_bootstrap(self, run_id: str, *, epoch: int, value: dict) -> None:
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT working_state_json FROM assistant_runs WHERE id=? AND status='running' AND run_epoch=?",
                                     (run_id, epoch)).fetchone()
            if row is None:
                raise AssistantConflict("run_fenced")
            working = json.loads(row[0] or "{}")
            working["knowledge_bootstrap"] = value
            connection.execute("UPDATE assistant_runs SET working_state_json=? WHERE id=?",
                               (json.dumps(working, ensure_ascii=False), run_id))

    @staticmethod
    def _legacy_call_key(run_id: str, call_id: str, name: str, arguments: dict) -> list:
        return [run_id, call_id, name, json.dumps(arguments, sort_keys=True, ensure_ascii=False)]

    def freeze_legacy_recovery_calls(self, *, stage: str = "k") -> None:
        """One deployment boundary: only already-persisted retired calls may replay."""
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            key = f"{stage}_legacy_recovery_calls:{self.principal_id}"
            if connection.execute("SELECT 1 FROM assistant_runtime_state WHERE key=?", (key,)).fetchone():
                return
            rows = connection.execute(
                "SELECT m.run_id,m.provider_payload_json FROM assistant_messages m JOIN assistant_runs r ON r.id=m.run_id "
                "JOIN assistant_threads t ON t.id=r.thread_id WHERE m.role='assistant' AND t.principal_id=? "
                "AND r.status IN ('queued','running','interrupted','budget_exhausted','failed')", (self.principal_id,)).fetchall()
            permitted = []
            for row in rows:
                for call in json.loads(row["provider_payload_json"] or "{}").get("tool_calls") or []:
                    try:
                        name = call["function"]["name"]
                        arguments = json.loads(call["function"].get("arguments") or "{}")
                        if name not in ({"collection_search", "knowledge_search", "knowledge_read", "task_scope"} if stage == "k" else {"knowledge_save_outcome", "knowledge_save_discussion", "knowledge_propose", "knowledge_confirm"}):
                            continue
                        completed = connection.execute("SELECT 1 FROM assistant_messages WHERE run_id=? AND role='tool' "
                            "AND json_extract(provider_payload_json,'$.tool_call_id')=?", (row["run_id"], call["id"])).fetchone()
                        if not completed:
                            permitted.append(self._legacy_call_key(row["run_id"], call["id"], name, arguments))
                    except (KeyError, ValueError, TypeError):
                        continue
            connection.execute("INSERT INTO assistant_runtime_state(key,value,updated_at) VALUES(?,?,?)",
                               (key, json.dumps(permitted, ensure_ascii=False), utc_now()))

    def legacy_call_registered(self, run_id: str, call_id: str, name: str, arguments: dict, *, stage: str = "k") -> bool:
        with self.db.connect() as connection:
            boundary = connection.execute("SELECT value FROM assistant_runtime_state WHERE key=?",
                                          (f"{stage}_legacy_recovery_calls:{self.principal_id}",)).fetchone()
        return boundary is not None and self._legacy_call_key(run_id, call_id, name, arguments) in json.loads(boundary[0])

    def begin_tool_call(
        self,
        run_id: str,
        *,
        ordinal: int,
        call_id: str,
        name: str,
        arguments: dict[str, Any],
        operation_key: str | None = None,
        reuse_validator: Callable[[dict[str, Any]], bool] | None = None,
    ) -> dict[str, Any] | None:
        now = utc_now()
        encoded_arguments = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM assistant_tool_calls WHERE run_id=? AND call_id=?",
                (run_id, call_id),
            ).fetchone()
            if existing is not None:
                return dict(existing)
            reusable = None
            if reuse_validator is not None and name in {
                "search_knowledge", "collection_read", "knowledge_read",
            }:
                reusable = connection.execute(
                    """
                    SELECT * FROM assistant_tool_calls
                    WHERE run_id=? AND name=? AND args_json=? AND status='completed'
                      AND result_json IS NOT NULL
                    ORDER BY ordinal DESC LIMIT 1
                    """,
                    (run_id, name, encoded_arguments),
                ).fetchone()
            if reusable is not None:
                try:
                    result = json.loads(str(reusable["result_json"] or "{}"))
                    reusable_valid = (
                        str(result.get("status") or "") == "ok"
                        and not bool(result.get("retryable"))
                        and bool(reuse_validator({**dict(reusable), "result": result}))
                    )
                except (TypeError, ValueError, json.JSONDecodeError):
                    reusable_valid = False
                if not reusable_valid:
                    reusable = None
            if reusable is not None:
                result["call_id"] = call_id
                result["result_ref"] = f"run-result:{run_id}:{call_id}"
                result["coverage"] = {**(result.get("coverage") or {}),
                                      "cache_hit": True,
                                      "retrieval_requests_this_call": 0}
                reused_json = json.dumps(result, ensure_ascii=False)
                connection.execute(
                    """
                    INSERT INTO assistant_tool_calls(
                        id,run_id,ordinal,call_id,name,args_json,status,result_json,
                        operation_key,created_at,completed_at
                    ) VALUES(?,?,?,?,?,?,'completed',?,?,?,?)
                    """,
                    (
                        f"atc_{uuid.uuid4().hex}", run_id, ordinal, call_id, name,
                        encoded_arguments, reused_json, operation_key,
                        now, now,
                    ),
                )
                self._append_event(
                    connection, run_id, "tool_reused",
                    {
                        "name": name, "call_id": call_id,
                        "reused_call_id": str(reusable["call_id"]),
                    },
                )
                value = dict(reusable)
                value.update({"call_id": call_id, "ordinal": ordinal,
                              "result_json": reused_json})
                return value
            connection.execute(
                """
                INSERT INTO assistant_tool_calls(
                    id, run_id, ordinal, call_id, name, args_json, status,
                    operation_key, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, 'running', ?, ?)
                """,
                (
                    f"atc_{uuid.uuid4().hex}", run_id, ordinal, call_id, name,
                    encoded_arguments,
                    operation_key, now,
                ),
            )
            self._append_event(
                connection, run_id, "tool_started", {"name": name, "call_id": call_id}
            )
        return None

    def finish_tool_call(
        self, run_id: str, *, call_id: str, result: dict[str, Any]
    ) -> None:
        now = utc_now()
        with self.db.connect() as connection:
            connection.execute(
                """
                UPDATE assistant_tool_calls SET status='completed', result_json=?, completed_at=?
                WHERE run_id=? AND call_id=?
                """,
                (json.dumps(result, ensure_ascii=False), now, run_id, call_id),
            )
            self._append_event(
                connection,
                run_id,
                "tool_completed",
                {"call_id": call_id, "summary": str(result.get("summary") or "")[:300]},
            )

    def try_complete_run(
        self,
        run_id: str,
        *,
        epoch: int,
        answer: str,
        usage: dict[str, Any],
        expected_scope_version: int,
        expected_observed_memory_epoch: int,
        dependency_refs: list[str],
        expected_task_note_version: int | None,
        dependency_validator: Callable[[list[str], int, str, int], bool] | None = None,
        completion_origin: str = "model",
    ) -> str:
        now = utc_now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                """
                SELECT r.*, t.space_id, s.scope_version FROM assistant_runs r
                JOIN assistant_threads t ON t.id=r.thread_id
                JOIN assistant_spaces s ON s.id=t.space_id
                WHERE r.id=? AND t.principal_id=?
                """,
                (run_id, self.principal_id),
            ).fetchone()
            if (
                run is None
                or str(run["status"]) != "running"
                or int(run["run_epoch"]) != epoch
                or bool(run["cancel_requested"])
            ):
                return "run_fenced"
            working = json.loads(run["working_state_json"] or "{}")
            budget = working.get("execution_budget")
            if budget and datetime.fromisoformat(budget["deadline_at"]) <= datetime.now(timezone.utc):
                return "execution_budget_exhausted"
            if int(run["scope_version"]) != int(expected_scope_version):
                return "scope_changed"
            current_memory_epoch = self._memory_epoch(connection)
            if (
                current_memory_epoch != int(expected_observed_memory_epoch)
                and self._memory_changes_affect_space(
                    connection,
                    after_epoch=int(expected_observed_memory_epoch),
                    space_id=int(run["space_id"]),
                )
            ):
                return "memory_changed"
            if not self._memory_refs_valid(
                connection, dependency_refs, space_id=int(run["space_id"]), now=now
            ):
                return "memory_dependency_changed"
            if dependency_validator is not None and not dependency_validator(
                dependency_refs,
                int(run["space_id"]),
                str(run["thread_id"]),
                int(run["scope_version"]),
            ):
                return "dependency_changed"
            if expected_task_note_version is not None:
                note = connection.execute(
                    "SELECT note_version, status FROM assistant_task_notes WHERE thread_id=? AND task_segment=1",
                    (run["thread_id"],),
                ).fetchone()
                if (
                    note is None or str(note["status"]) != "active"
                    or int(note["note_version"]) != int(expected_task_note_version)
                ):
                    return "task_note_changed"
            late = json.loads(run["working_state_json"] or "{}").get("late_model_usage") or {}
            usage = json.loads(run["usage_json"] or "{}") if budget else dict(usage)
            for key, amount in ({} if working.get("usage_includes_late") else late).items():
                if isinstance(amount, (int, float)) and not isinstance(amount, bool):
                    usage[key] = usage.get(key, 0) + amount
            message_id = f"amsg_{uuid.uuid4().hex}"
            connection.execute(
                """
                INSERT INTO assistant_messages(
                    id, thread_id, run_id, seq, role, content, provider_payload_json, created_at
                ) VALUES(?, ?, ?, ?, 'assistant', ?, ?, ?)
                """,
                (
                    message_id,
                    run["thread_id"],
                    run_id,
                    self._next_message_seq(connection, str(run["thread_id"])),
                    answer,
                    json.dumps({
                        "origin": completion_origin,
                        "dependency_refs": dependency_refs,
                        "memory_observed_epoch": current_memory_epoch,
                        "task_note_version": expected_task_note_version,
                    }, ensure_ascii=False),
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE assistant_runs SET status='completed', usage_json=?,
                    observed_memory_epoch=?, memory_epoch=?, updated_at=?, completed_at=?
                WHERE id=? AND run_epoch=? AND cancel_requested=0
                """,
                (
                    json.dumps(usage), current_memory_epoch, current_memory_epoch,
                    now, now, run_id, epoch,
                ),
            )
            connection.execute(
                "UPDATE assistant_threads SET updated_at=? WHERE id=?",
                (now, run["thread_id"]),
            )
            self._append_event(
                connection, run_id, "run_completed", {"message_id": message_id}
            )
            user_messages = connection.execute(
                "SELECT id,content FROM assistant_messages WHERE run_id=? AND role='user' ORDER BY seq",
                (run_id,),
            ).fetchall()
            if not self._simple_collection_lookup(connection, run_id, user_messages):
                admission = json.loads(str(run["working_state_json"] or "{}")).get(
                    "auto_memory_admission", {}
                )
                self._enqueue_memory_extraction(
                    connection, run=run, user_messages=user_messages,
                    admission=admission,
                )
        return "completed"

    def _enqueue_memory_extraction(
        self, connection: Any, *, run: Any, user_messages: list[Any],
        admission: dict[str, Any],
    ) -> str | None:
        message_ids = [str(item["id"]) for item in user_messages]
        if not message_ids or admission.get("enabled") is not True:
            return None
        thread_id = str(run["thread_id"])
        epoch = int(run["extraction_memory_epoch"])
        generation = int(admission.get("generation", -1))
        # Only merge jobs that have never started or staged a proposal. A new
        # message arriving during inference therefore remains a separate job.
        rows = connection.execute(
            """SELECT id,payload_json FROM assistant_jobs
            WHERE kind='memory_extract' AND status='queued' AND attempt=0
              AND proposal_json IS NULL ORDER BY created_at DESC LIMIT 30"""
        ).fetchall()
        for row in rows:
            payload = json.loads(row["payload_json"] or "{}")
            if (str(payload.get("thread_id")) != thread_id
                    or int(payload.get("memory_epoch", -1)) != epoch
                    or int(payload.get("auto_memory_generation", -1)) != generation
                    or payload.get("auto_enabled_at_enqueue") is not True):
                continue
            merged = list(dict.fromkeys([*payload.get("message_ids", []), *message_ids]))
            payload["message_ids"] = merged
            payload["run_ids"] = list(dict.fromkeys([
                *payload.get("run_ids", [payload.get("run_id")]), str(run["id"])
            ]))
            payload["message_cursor"] = merged[-1]
            connection.execute(
                "UPDATE assistant_jobs SET payload_json=?,updated_at=? WHERE id=?",
                (json.dumps(payload, ensure_ascii=False), utc_now(), row["id"]),
            )
            return str(row["id"])
        payload = {
            "run_id": str(run["id"]), "run_ids": [str(run["id"])],
            "thread_id": thread_id, "message_ids": message_ids,
            "message_cursor": message_ids[-1],
            "memory_epoch": epoch, "policy_version": "v1",
            "auto_enabled_at_enqueue": True,
            "auto_memory_generation": generation,
        }
        return self.enqueue_job(
            connection, kind="memory_extract",
            dedupe_key=f"memory_extract:{run['id']}:v1", payload=payload,
        )

    @staticmethod
    def _simple_collection_lookup(connection: Any, run_id: str, messages: list[Any]) -> bool:
        """Avoid a model extraction for an explicitly narrow, read-only lookup."""
        if len(messages) != 1:
            return False
        text = str(messages[0]["content"] or "").strip()
        if not (len(text) <= 160 and ("只需" in text or "只要" in text)):
            return False
        if not any(word in text for word in ("找回", "有没有", "哪条收藏", "哪个视频")):
            return False
        if any(word in text for word in ("记住", "我决定", "我认为", "我觉得", "我希望", "以后", "今后")):
            return False
        names = {
            str(row["name"]) for row in connection.execute(
                "SELECT name FROM assistant_tool_calls WHERE run_id=?", (run_id,)
            )
        }
        return bool(names) and names <= {"search_knowledge", "collection_search", "collection_read"}

    def complete_run(self, run_id: str, *, epoch: int, answer: str, usage: dict[str, Any]) -> bool:
        """Backward-compatible completion used by existing recovery tests."""
        run = self.get_run(run_id)
        context = self.run_context(run_id)
        outcome = self.try_complete_run(
            run_id, epoch=epoch, answer=answer, usage=usage,
            expected_scope_version=int(context["space"]["scope_version"]),
            expected_observed_memory_epoch=self.current_memory_epoch(),
            dependency_refs=[], expected_task_note_version=None,
        )
        return outcome == "completed"

    def fail_run(self, run_id: str, *, code: str, message: str) -> None:
        now = utc_now()
        paused = code in {
            "step_budget_exhausted", "tool_budget_exhausted", "context_budget_exceeded", "execution_budget_exhausted"
        }
        status = "budget_exhausted" if paused else "failed"
        with self.db.connect() as connection:
            updated = connection.execute(
                """
                UPDATE assistant_runs SET status=?, last_error_code=?,
                    last_error_message=?, updated_at=?, completed_at=?
                WHERE id=? AND status='running'
                """,
                (status, code, message[:1000], now, now, run_id),
            )
            if updated.rowcount:
                connection.execute(
                    "UPDATE assistant_threads SET updated_at=? WHERE id=(SELECT thread_id FROM assistant_runs WHERE id=?)",
                    (now, run_id),
                )
                self._append_event(
                    connection, run_id, "run_budget_exhausted" if paused else "run_failed",
                    {"error_code": code, "message": message[:300]},
                )

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.db.connect() as connection:
            self.mark_user_activity(connection)
            row = connection.execute(
                """SELECT r.* FROM assistant_runs r JOIN assistant_threads t ON t.id=r.thread_id
                   WHERE r.id=? AND t.principal_id=?""", (run_id, self.principal_id)
            ).fetchone()
            if row is None:
                raise KeyError(run_id)
            if str(row["status"]) in {"queued", "running", "interrupted", "budget_exhausted", "failed"}:
                connection.execute(
                    """
                    UPDATE assistant_runs SET cancel_requested=1, run_epoch=run_epoch+1,
                        status='cancelled', updated_at=?, completed_at=? WHERE id=?
                    """,
                    (now, now, run_id),
                )
                connection.execute(
                    "UPDATE assistant_threads SET updated_at=? WHERE id=?",
                    (now, row["thread_id"]),
                )
                self._append_event(connection, run_id, "run_cancelled", {"reason": "user_abandoned"})
        return self.get_run(run_id)

    def request_finish(self, run_id: str) -> dict[str, Any]:
        """Fence new exploration immediately while retaining the run for one final answer."""
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT r.working_state_json,r.status FROM assistant_runs r "
                "JOIN assistant_threads t ON t.id=r.thread_id "
                "WHERE r.id=? AND t.principal_id=?", (run_id, self.principal_id),
            ).fetchone()
            if row is None:
                raise KeyError(run_id)
            self.mark_user_activity(connection)
            if row["status"] in {"queued", "running"}:
                state = json.loads(row["working_state_json"] or "{}")
                state["finish_requested"] = True
                connection.execute(
                    "UPDATE assistant_runs SET working_state_json=?,updated_at=? WHERE id=?",
                    (json.dumps(state, ensure_ascii=False), utc_now(), run_id),
                )
        return self.get_run(run_id)

    def pause_run(self, run_id: str, *, code: str, message: str) -> None:
        now = utc_now()
        with self.db.connect() as connection:
            row = connection.execute("SELECT working_state_json FROM assistant_runs WHERE id=?", (run_id,)).fetchone()
            if row:
                working = json.loads(row[0] or "{}")
                self._pause_execution_budget(working)
                connection.execute("UPDATE assistant_runs SET working_state_json=? WHERE id=?", (json.dumps(working), run_id))
            updated = connection.execute(
                """
                UPDATE assistant_runs SET status='interrupted', last_error_code=?,
                    last_error_message=?, updated_at=?, completed_at=?
                WHERE id=? AND status='running'
                """,
                (code, message[:1000], now, now, run_id),
            )
            if updated.rowcount:
                self._append_event(
                    connection, run_id, "run_interrupted",
                    {"reason": code, "message": message[:300]},
                )

    def resume_run(self, run_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.db.connect() as connection:
            self.mark_user_activity(connection)
            row = connection.execute(
                """SELECT r.status,r.last_error_code,r.step_count,r.tool_count,r.working_state_json,
                          r.thread_id FROM assistant_runs r JOIN assistant_threads t ON t.id=r.thread_id
                   WHERE r.id=? AND t.principal_id=?""", (run_id, self.principal_id)
            ).fetchone()
            if row is None:
                raise KeyError(run_id)
            compaction_failure = (str(row["status"]) == "failed"
                                  and str(row["last_error_code"] or "") == "context_compaction_failed")
            if str(row["status"]) not in {"interrupted", "budget_exhausted"} and not compaction_failure:
                raise AssistantConflict("run_not_resumable")
            working_state = json.loads(row["working_state_json"] or "{}")
            if compaction_failure:
                if int(working_state.get("compaction_retries", 0)) >= 1:
                    raise AssistantConflict("context_recovery_not_available")
                working_state["compaction_retries"] = 1
            if (str(row["last_error_code"] or "") == "context_budget_exceeded"
                    and int(working_state.get("context_recovery_attempts", 0)) >= 1):
                raise AssistantConflict("context_recovery_not_available")
            newer = connection.execute(
                """SELECT 1 FROM assistant_runs WHERE thread_id=? AND rowid>(
                   SELECT rowid FROM assistant_runs WHERE id=?) LIMIT 1""",
                (row["thread_id"], run_id),
            ).fetchone()
            if newer:
                raise AssistantConflict("run_superseded")
            other_active = connection.execute(
                """SELECT 1 FROM assistant_runs WHERE thread_id=? AND id<>?
                   AND status IN ('queued','running') LIMIT 1""",
                (row["thread_id"], run_id),
            ).fetchone()
            if other_active:
                raise AssistantConflict("thread_has_active_run")
            if str(row["last_error_code"] or "") == "context_budget_exceeded":
                working_state["context_recovery_attempts"] = 1
            if str(row["status"]) == "budget_exhausted":
                working_state.pop("execution_budget", None)
                working_state.pop("segment_started_at", None)
                working_state["explicit_new_segment"] = True
            if str(row["status"]) == "budget_exhausted":
                working_state["segment_step_base"] = int(row["step_count"])
                working_state["segment_tool_base"] = max(int(row["tool_count"]), self.completed_tool_message_count(run_id))
            connection.execute(
                """
                UPDATE assistant_runs SET status='queued', cancel_requested=0,
                    run_epoch=run_epoch+1, working_state_json=?, updated_at=?,
                    completed_at=NULL WHERE id=?
                """,
                (json.dumps(working_state), now, run_id),
            )
            connection.execute(
                "UPDATE assistant_threads SET updated_at=? WHERE id=?",
                (now, row["thread_id"]),
            )
            self._append_event(connection, run_id, "run_resumed", {})
        return self.get_run(run_id)

    def events(self, run_id: str, *, after_seq: int = 0) -> list[dict[str, Any]]:
        self.get_run(run_id)
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT seq, event_type, payload_json, created_at
                FROM assistant_run_events WHERE run_id=? AND seq>?
                ORDER BY seq LIMIT 200
                """,
                (run_id, after_seq),
            ).fetchall()
        return [
            {
                "seq": int(row["seq"]),
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def recover_interrupted_runs(self) -> int:
        now = utc_now()
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT id FROM assistant_runs WHERE status='running'"
            ).fetchall()
            connection.execute(
                """
                UPDATE assistant_runs SET status='interrupted', updated_at=?,
                    last_error_code='service_restarted',
                    last_error_message='服务重启后需要用户继续'
                WHERE status='running'
                """,
                (now,),
            )
            # Unexpected downtime cannot grant active time: retain the absolute deadline.
            # Explicit pause_run checkpoints, in contrast, carry paused_remaining.
            for row in rows:
                self._append_event(connection, str(row["id"]), "run_interrupted", {})
        return len(rows)

    @staticmethod
    def enqueue_job(
        connection: Any,
        *,
        kind: str,
        dedupe_key: str,
        payload: dict[str, Any],
        not_before: str | None = None,
    ) -> str:
        now = utc_now()
        job_id = f"ajob_{uuid.uuid4().hex}"
        connection.execute(
            """
            INSERT INTO assistant_jobs(
                id, kind, dedupe_key, status, payload_json, not_before, created_at, updated_at
            ) VALUES(?, ?, ?, 'queued', ?, ?, ?, ?)
            ON CONFLICT(dedupe_key) DO NOTHING
            """,
            (job_id, kind, dedupe_key, json.dumps(payload, ensure_ascii=False), not_before or now, now, now),
        )
        row = connection.execute(
            "SELECT id FROM assistant_jobs WHERE dedupe_key=?", (dedupe_key,)
        ).fetchone()
        return str(row["id"])

    def recover_expired_jobs(self) -> int:
        """Only expired leases are recoverable; retain proposals, budgets and attempts."""
        now = utc_now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute("SELECT id,attempt,proposal_json FROM assistant_jobs "
                                      "WHERE status='running' AND lease_until<?", (now,)).fetchall()
            for row in rows:
                exhausted = int(row["attempt"]) >= 3
                connection.execute("UPDATE assistant_jobs SET status=?,lease_owner=NULL,lease_until=NULL, "
                                   "last_error_code=?,last_error_message=?,updated_at=? WHERE id=?",
                                   ("blocked" if exhausted else "queued", "lease_expired",
                                    "重启/租约到期；未暂存的远端请求可能重复，已有候选和回执保留" if not row["proposal_json"] else
                                    "租约到期；恢复已有候选并重新核对", now, row["id"]))
                connection.execute("INSERT INTO assistant_scheduler_events(job_id,event_type,reason,created_at) "
                                   "VALUES(?,'recovered',?,?)", (row["id"],
                                   "retry_limit" if exhausted else "staged" if row["proposal_json"] else "remote_replay_possible", now))
            return len(rows)

    def claim_job(
        self, *, owner: str, lease_seconds: int = 120,
        allow_model_jobs: bool = True, allow_maintenance: bool = True,
        scheduler_reason: str = "normal",
    ) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        now_text = now.isoformat(timespec="seconds")
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat(timespec="seconds")
        self.recover_expired_jobs()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            held_jobs_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='metadata_backfill_job_holds'"
            ).fetchone()
            hold_filter = (
                " AND NOT EXISTS (SELECT 1 FROM metadata_backfill_job_holds h "
                "WHERE h.job_id=assistant_jobs.id)"
                if held_jobs_table else ""
            )
            row = connection.execute(
                f"""
                SELECT * FROM assistant_jobs
                WHERE status IN ('queued','retry_wait','budget_wait') AND not_before<=?
                  AND (? OR kind NOT IN (
                      'memory_extract','source_extract','wiki_integrate','external_material_integrate'
                  ))
                  AND (? OR kind IN ('memory_purge','memory_index'))
                  AND (kind IN ('memory_purge','memory_index') OR NOT EXISTS (
                    SELECT 1 FROM assistant_jobs active WHERE active.status='running'
                    AND active.kind NOT IN ('memory_purge','memory_index') AND active.lease_until>=?
                  ))
                  {hold_filter}
                ORDER BY CASE kind WHEN 'memory_purge' THEN 0 WHEN 'memory_index' THEN 1 ELSE 2 END,
                         created_at LIMIT 1
                """,
                (now_text, int(allow_model_jobs), int(allow_maintenance), now_text),
            ).fetchone()
            if row is None:
                return None
            updated = connection.execute(
                """
                UPDATE assistant_jobs SET status='running', lease_owner=?, lease_until=?,
                    lease_epoch=lease_epoch+1, attempt=attempt+1, updated_at=?
                WHERE id=? AND status IN ('queued','retry_wait','budget_wait')
                """,
                (owner, lease_until, now_text, row["id"]),
            )
            if updated.rowcount != 1:
                return None
            claimed = connection.execute(
                "SELECT * FROM assistant_jobs WHERE id=?", (row["id"],)
            ).fetchone()
            wait_seconds = max(
                0.0,
                (now - datetime.fromisoformat(str(row["created_at"]))).total_seconds(),
            )
            connection.execute(
                """
                INSERT INTO assistant_scheduler_events(
                    job_id,event_type,reason,queue_wait_seconds,created_at
                ) VALUES(?, 'claimed', ?, ?, ?)
                """,
                (row["id"], scheduler_reason, wait_seconds, now_text),
            )
        value = dict(claimed)
        value["payload"] = json.loads(value.pop("payload_json"))
        value["proposal"] = json.loads(value.get("proposal_json") or "null")
        return value

    def defer_job_for_activity(self, job: dict[str, Any]) -> None:
        """Keep a staged proposal and release the lease when the user returns."""
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE assistant_jobs SET status='queued', lease_owner=NULL, lease_until=NULL, "
                "attempt=MAX(0,attempt-1), not_before=?, updated_at=? "
                "WHERE id=? AND status='running' AND lease_owner=? AND lease_epoch=?",
                (utc_now(), utc_now(), job["id"], job["lease_owner"], job["lease_epoch"]),
            )

    def model_job_wait_exceeded(self, seconds: int = 30) -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(
            timespec="seconds"
        )
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM assistant_jobs
                WHERE status IN ('queued','retry_wait') AND created_at<=?
                  AND kind IN ('memory_extract','source_extract','wiki_integrate','external_material_integrate')
                LIMIT 1
                """,
                (cutoff,),
            ).fetchone()
        return row is not None

    def reserve_model_request(self, *, lane: str, request_limit: int) -> dict[str, Any]:
        if lane not in {"foreground", "background"} or request_limit < 1:
            raise ValueError("invalid_model_budget")
        now = datetime.now(timezone.utc)
        budget_date = now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT OR IGNORE INTO assistant_model_budget_days(
                    budget_date,lane,request_limit,requests_used,updated_at
                ) VALUES(?,?,?,0,?)
                """,
                (budget_date, lane, request_limit, now.isoformat(timespec="seconds")),
            )
            updated = connection.execute(
                """
                UPDATE assistant_model_budget_days
                SET requests_used=requests_used+1, request_limit=?, updated_at=?
                WHERE budget_date=? AND lane=? AND requests_used<?
                """,
                (
                    request_limit, now.isoformat(timespec="seconds"), budget_date,
                    lane, request_limit,
                ),
            )
            if updated.rowcount != 1:
                raise ModelBudgetWait("后台模型每日额度已用完，等待下一个本地自然日")
            row = connection.execute(
                "SELECT * FROM assistant_model_budget_days WHERE budget_date=? AND lane=?",
                (budget_date, lane),
            ).fetchone()
        return dict(row)

    def record_model_usage(
        self,
        *,
        lane: str,
        usage: dict[str, Any] | None,
        outcome: str,
        latency_ms: float,
        budget_date: str | None = None,
    ) -> None:
        """Settle an already reserved request without treating missing usage as zero."""
        if lane not in {"foreground", "background"}:
            raise ValueError("invalid_model_budget")
        now = datetime.now(timezone.utc)
        budget_date = budget_date or now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT usage_json FROM assistant_model_budget_days "
                "WHERE budget_date=? AND lane=?",
                (budget_date, lane),
            ).fetchone()
            if row is None:
                raise AssistantConflict("model_request_not_reserved")
            aggregate = json.loads(row["usage_json"] or "{}")
            aggregate["responses"] = int(aggregate.get("responses", 0)) + 1
            aggregate["latency_ms"] = round(
                float(aggregate.get("latency_ms", 0.0)) + max(0.0, latency_ms), 3
            )
            aggregate[f"outcome_{outcome}"] = int(
                aggregate.get(f"outcome_{outcome}", 0)
            ) + 1
            numeric = {
                str(key): value for key, value in (usage or {}).items()
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            }
            if numeric:
                aggregate["known_usage_responses"] = int(
                    aggregate.get("known_usage_responses", 0)
                ) + 1
                totals = dict(aggregate.get("usage_totals") or {})
                for key, value in numeric.items():
                    totals[key] = totals.get(key, 0) + value
                aggregate["usage_totals"] = totals
            else:
                aggregate["unknown_usage_responses"] = int(
                    aggregate.get("unknown_usage_responses", 0)
                ) + 1
            connection.execute(
                "UPDATE assistant_model_budget_days SET usage_json=?, updated_at=? "
                "WHERE budget_date=? AND lane=?",
                (
                    json.dumps(aggregate, ensure_ascii=False, sort_keys=True),
                    now.isoformat(timespec="seconds"), budget_date, lane,
                ),
            )

    def defer_job_for_budget(self, job: dict[str, Any], *, message: str) -> None:
        local_now = datetime.now(ZoneInfo("Asia/Shanghai"))
        tomorrow = (local_now + timedelta(days=1)).date()
        resume_local = datetime.combine(tomorrow, datetime.min.time(), tzinfo=ZoneInfo("Asia/Shanghai"))
        resume_at = resume_local.astimezone(timezone.utc).isoformat(timespec="seconds")
        now = utc_now()
        with self.db.connect() as connection:
            updated = connection.execute(
                """
                UPDATE assistant_jobs SET status='budget_wait', not_before=?,
                    attempt=MAX(attempt-1,0), lease_owner=NULL, lease_until=NULL,
                    last_error_code='background_budget_wait', last_error_message=?, updated_at=?
                WHERE id=? AND status='running' AND lease_owner=? AND lease_epoch=?
                """,
                (
                    resume_at, message[:1000], now, job["id"],
                    job["lease_owner"], job["lease_epoch"],
                ),
            )
            if updated.rowcount:
                connection.execute(
                    """
                    INSERT INTO assistant_scheduler_events(
                        job_id,event_type,reason,created_at
                    ) VALUES(?, 'budget_wait', 'daily_background_limit', ?)
                    """,
                    (job["id"], now),
                )

    def defer_job_for_batch_budget(self, job: dict[str, Any], *, message: str) -> None:
        """Pause an explicit maintenance unit until the user grants a new segment."""
        now = utc_now()
        with self.db.connect() as connection:
            updated = connection.execute(
                """
                UPDATE assistant_jobs SET status='budget_wait', not_before='9999-12-31T23:59:59+00:00',
                    attempt=MAX(attempt-1,0), lease_owner=NULL, lease_until=NULL,
                    last_error_code='maintenance_budget_wait', last_error_message=?, updated_at=?
                WHERE id=? AND status='running' AND lease_owner=? AND lease_epoch=?
                """,
                (
                    message[:1000], now, job["id"],
                    job["lease_owner"], job["lease_epoch"],
                ),
            )
            if updated.rowcount:
                connection.execute(
                    """
                    INSERT INTO assistant_scheduler_events(
                        job_id,event_type,reason,created_at
                    ) VALUES(?, 'budget_wait', 'explicit_batch_limit', ?)
                    """,
                    (job["id"], now),
                )

    def heartbeat_job(
        self, job_id: str, *, owner: str, lease_epoch: int, lease_seconds: int = 120
    ) -> bool:
        now = datetime.now(timezone.utc)
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat(timespec="seconds")
        with self.db.connect() as connection:
            updated = connection.execute(
                """
                UPDATE assistant_jobs SET lease_until=?, updated_at=?
                WHERE id=? AND status='running' AND lease_owner=? AND lease_epoch=?
                """,
                (lease_until, now.isoformat(timespec="seconds"), job_id, owner, lease_epoch),
            )
        return updated.rowcount == 1

    def finish_job(
        self,
        job_id: str,
        *,
        proposal: dict[str, Any] | None = None,
        owner: str | None = None,
        lease_epoch: int | None = None,
    ) -> bool:
        now = utc_now()
        fencing = ""
        parameters: list[Any] = [
            json.dumps(proposal, ensure_ascii=False) if proposal is not None else None,
            now,
            now,
            job_id,
        ]
        if owner is not None and lease_epoch is not None:
            fencing = " AND status='running' AND lease_owner=? AND lease_epoch=?"
            parameters.extend([owner, lease_epoch])
        with self.db.connect() as connection:
            updated = connection.execute(
                f"""
                UPDATE assistant_jobs SET status='succeeded', proposal_json=?,
                    lease_owner=NULL, lease_until=NULL, completed_at=?, updated_at=? WHERE id=?
                    {fencing}
                """,
                parameters,
            )
        return updated.rowcount == 1

    def save_job_proposal(
        self,
        job_id: str,
        proposal: dict[str, Any],
        *,
        owner: str | None = None,
        lease_epoch: int | None = None,
    ) -> bool:
        fencing = ""
        parameters: list[Any] = [json.dumps(proposal, ensure_ascii=False), utc_now(), job_id]
        if owner is not None and lease_epoch is not None:
            fencing = " AND lease_owner=? AND lease_epoch=?"
            parameters.extend([owner, lease_epoch])
        with self.db.connect() as connection:
            updated = connection.execute(
                f"UPDATE assistant_jobs SET proposal_json=?, updated_at=? "
                f"WHERE id=? AND status='running'{fencing}",
                parameters,
            )
        return updated.rowcount == 1

    def fail_job(self, job: dict[str, Any], *, code: str, message: str, blocked: bool = False) -> None:
        attempt = int(job["attempt"])
        terminal = blocked or attempt >= 3
        delay = (10, 60, 300)[min(max(attempt - 1, 0), 2)]
        next_time = datetime.now(timezone.utc) + timedelta(seconds=delay)
        with self.db.connect() as connection:
            connection.execute(
                """
                UPDATE assistant_jobs SET status=?, not_before=?, lease_owner=NULL,
                    lease_until=NULL, last_error_code=?, last_error_message=?, updated_at=?
                WHERE id=? AND status='running' AND lease_owner=? AND lease_epoch=?
                """,
                (
                    "blocked" if terminal else "retry_wait",
                    next_time.isoformat(timespec="seconds"),
                    code,
                    message[:1000],
                    utc_now(),
                    job["id"],
                    job["lease_owner"],
                    job["lease_epoch"],
                ),
            )

    def retry_job(self, job_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM assistant_jobs WHERE id=?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] not in {"blocked", "failed", "retry_wait", "budget_wait"}:
                raise AssistantConflict("job_not_retryable")
            payload = json.loads(row["payload_json"] or "{}")
            continued_batch_id: str | None = None
            if (
                str(row["status"]) == "budget_wait"
                and str(row["last_error_code"] or "") == "maintenance_budget_wait"
            ):
                previous_batch_id = str(payload.get("maintenance_batch_id") or "")
                previous = connection.execute(
                    "SELECT * FROM assistant_maintenance_batches WHERE id=?",
                    (previous_batch_id,),
                ).fetchone()
                if previous is None:
                    raise AssistantConflict("maintenance_batch_missing")
                continued_batch_id = f"amb_{uuid.uuid4().hex}"
                connection.execute(
                    """
                    INSERT INTO assistant_maintenance_batches(
                        id,space_id,source_limit,model_limit,calls_used,created_at
                    ) VALUES(?,?,?,?,0,?)
                    """,
                    (
                        continued_batch_id, int(previous["space_id"]), 1,
                        int(previous["model_limit"]), now,
                    ),
                )
                payload["maintenance_batch_id"] = continued_batch_id
            connection.execute(
                """
                UPDATE assistant_jobs SET status='queued', not_before=?,
                    payload_json=?,
                    lease_owner=NULL, lease_until=NULL, last_error_code=NULL,
                    last_error_message=NULL, completed_at=NULL, updated_at=? WHERE id=?
                """,
                (now, json.dumps(payload, ensure_ascii=False), now, job_id),
            )
            if continued_batch_id:
                connection.execute(
                    """
                    INSERT INTO assistant_scheduler_events(
                        job_id,event_type,reason,created_at
                    ) VALUES(?, 'continued', 'explicit_new_budget_segment', ?)
                    """,
                    (job_id, now),
                )
            value = dict(connection.execute(
                "SELECT * FROM assistant_jobs WHERE id=?", (job_id,)
            ).fetchone())
        value["payload"] = json.loads(value.pop("payload_json"))
        return value

    def requeue_blocked_memory_jobs(self) -> int:
        now = utc_now()
        with self.db.connect() as connection:
            updated = connection.execute(
                """
                UPDATE assistant_jobs SET status='queued', not_before=?, attempt=0,
                    last_error_code=NULL, last_error_message=NULL, updated_at=?
                WHERE kind IN ('memory_index','memory_purge') AND status='blocked'
                    AND last_error_code IN ('memory_backend_unavailable','semantic_index_not_started')
                """,
                (now, now),
            )
        return updated.rowcount

    def list_jobs(self, *, limit: int = 100, space_id: int | None = None) -> list[dict[str, Any]]:
        with self.db.connect() as connection:
            if space_id is None:
                rows = connection.execute("SELECT * FROM assistant_jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            else:
                joins, params = self._maintenance_job_scope(self.get_space(space_id))
                rows = connection.execute("SELECT j.*" + joins + " ORDER BY j.created_at DESC LIMIT ?", (*params, limit)).fetchall()
        values = []
        for row in rows:
            value = dict(row)
            value["payload"] = json.loads(value.pop("payload_json"))
            values.append(value)
        return values

    def _maintenance_job_scope(self, space: dict) -> tuple[str, tuple]:
        space_id = space["id"]
        joins = """ FROM assistant_jobs j
            LEFT JOIN assistant_threads t ON t.id=json_extract(j.payload_json,'$.thread_id') AND t.principal_id=?
            LEFT JOIN assistant_memories m ON m.id=json_extract(j.payload_json,'$.memory_id') AND m.principal_id=?
            LEFT JOIN assistant_maintenance_batches b ON b.id=json_extract(j.payload_json,'$.maintenance_batch_id')
            WHERE (COALESCE(json_extract(j.payload_json,'$.space_id'),t.space_id,
                    CASE WHEN m.scope_kind='space' THEN CAST(m.scope_id AS INTEGER) END,b.space_id)=?
                OR m.scope_kind='user'
                OR (json_extract(j.payload_json,'$.space_id') IS NULL AND t.id IS NULL AND m.id IS NULL AND b.id IS NULL
                    AND json_extract(j.payload_json,'$.video_id') IN (
                      SELECT ms.video_id FROM video_source_memberships ms JOIN favorite_sources fs ON fs.id=ms.source_id
                      JOIN videos v ON v.id=ms.video_id WHERE ms.removed_at IS NULL AND fs.status='active'
                      AND v.is_ignored=0 AND v.archived_at IS NULL
                      AND (? OR ms.source_id IN (SELECT value FROM json_each(?)))
                      AND (json_array_length(?)=0 OR ms.video_id IN (SELECT value FROM json_each(?))))))"""
        params=(self.principal_id,self.principal_id,space_id,int(space['all_active']),json.dumps(space['source_ids']),
                json.dumps(space['video_ids']),json.dumps(space['video_ids']))
        return joins, params

    def maintenance_activity(self, space_id: int, *, limit: int = 20) -> dict[str, Any]:
        """Bounded read projection of existing changes/jobs, not a new event store."""
        space = self.get_space(space_id)
        limit = max(1, min(limit, 50))
        items = []
        with self.db.connect() as c:
            memories = c.execute("SELECT m.*,ch.operation,ch.created_at AS changed_at FROM assistant_memory_changes ch "
                "JOIN assistant_memories m ON m.id=ch.memory_id WHERE m.principal_id=? AND ch.actor='assistant' "
                "AND ch.version=m.version AND (m.scope_kind='user' OR (m.scope_kind='space' AND m.scope_id=?)) "
                "ORDER BY ch.created_at DESC,ch.id DESC LIMIT ?", (self.principal_id,str(space_id),limit)).fetchall()
            for row in memories:
                valid = row['status']=='active' and (not row['expires_at'] or row['expires_at']>utc_now()) and (not row['valid_from'] or row['valid_from']<=utc_now())
                items.append(dict(id=f"memory:{row['id']}:{row['version']}",kind='memory',time=row['changed_at'],
                    title=row['text'] if valid else '记忆已失效或待核对',
                    result=('新增记忆' if row['operation']=='created' else '更新记忆') if valid else '当前不用于回答',
                    scope='所有对话' if row['scope_kind']=='user' else space['name'],
                    **({'memory_id':row['id']} if valid else {})))
            changes = c.execute("SELECT p.id,p.title,p.status,ch.version,ch.operation,ch.created_at FROM assistant_wiki_changes ch "
                "JOIN assistant_wiki_pages p ON p.id=ch.page_id WHERE p.principal_id=? AND p.space_id=? "
                "ORDER BY ch.created_at DESC,ch.id DESC LIMIT ?", (self.principal_id,space_id,limit)).fetchall()
            changed = {(row['id'],row['version']) for row in changes}
            for row in changes:
                items.append(dict(id=f"wiki:{row['id']}:{row['version']}",kind='wiki',time=row['created_at'],
                    title=row['title'],result={'created':'新增知识页','source_integrated':'增补知识',
                        'source_amended':'修订知识','source_associated':'关联来源'}.get(row['operation'],'知识页有变更'),
                    scope=space['name'],**({'page_id':row['id']} if row['status']=='active' else {})))
            joins, params = self._maintenance_job_scope(space)
            counts={row[0]:row[1] for row in c.execute('SELECT j.status,COUNT(*)'+joins+' GROUP BY j.status',params)}
            jobs=c.execute("SELECT j.*,t.id AS thread_id,m.scope_kind AS memory_scope,b.space_id AS batch_space"+joins+
                " ORDER BY (j.status<>'succeeded') DESC,j.updated_at DESC,j.id DESC LIMIT ?",(*params,limit)).fetchall()
            for row in jobs:
                payload=json.loads(row['payload_json']);result=json.loads(row['proposal_json'] or '{}')
                if row['status']=='succeeded' and not result.get('no_change') and not result.get('superseded'):
                    if row['kind']!='wiki_integrate' or (result.get('page_id'),result.get('version')) in changed:
                        continue
                shared=not (payload.get('space_id') or row['thread_id'] or row['memory_scope'] or row['batch_space'])
                page_id=result.get('page_id');page=c.execute('SELECT title,status FROM assistant_wiki_pages WHERE id=? AND space_id=? AND principal_id=?',
                    (page_id,space_id,self.principal_id)).fetchone() if page_id else None
                video=c.execute('SELECT title FROM videos WHERE id=?',(payload.get('video_id'),)).fetchone()
                labels={'memory_extract':'记忆提炼','memory_index':'记忆索引','memory_purge':'记忆清理',
                        'source_reconcile':'来源检查','source_extract':'材料整理','wiki_integrate':'知识整理'}
                state={'queued':'等待执行','running':'执行中','retry_wait':'等待重试','budget_wait':'等待额度',
                       'blocked':'需要处理','failed':'处理失败','succeeded':'处理完成'}.get(row['status'],row['status'])
                if row['status']=='succeeded':
                    state='已跳过' if result.get('superseded') else '无需变化' if result.get('no_change') else '处理完成'
                detail = {'wiki_manual_conflict':'已有人工修改，请查看知识页',
                          'provider_auth':'模型凭据需要检查', 'api_key_missing':'未配置模型凭据',
                          'memory_backend_unavailable':'记忆索引暂不可用',
                          'maintenance_budget_wait':'本次整理额度已用完',
                          'background_budget_wait':'等待下一个每日额度'}.get(row['last_error_code'], '')
                items.append(dict(id=row['id'],kind='job',time=row['updated_at'],title=page['title'] if page else video[0] if video else labels.get(row['kind'],'后台处理'),
                    result=state,detail=detail if row['status'] in {'blocked','failed','retry_wait','budget_wait'} else '',
                    scope='共享来源处理' if shared else '所有对话' if row['memory_scope']=='user' else space['name'],
                    **({'page_id':page_id} if page and page['status']=='active' else {}),
                    **({'thread_id':row['thread_id']} if row['thread_id'] else {})))
        return {'items':sorted(items,key=lambda item:(item['time'],item['id']),reverse=True)[:limit], 'counts':counts}

    def current_memory_epoch(self) -> int:
        with self.db.connect() as connection:
            return self._memory_epoch(connection)

    @staticmethod
    def _memory_refs_valid(
        connection: Any, refs: list[str], *, space_id: int, now: str
    ) -> bool:
        for ref in refs:
            if not str(ref).startswith("memory:"):
                continue
            parts = str(ref).split(":")
            if len(parts) != 3 or not parts[2].isdigit():
                return False
            row = connection.execute(
                "SELECT * FROM assistant_memories WHERE id=?", (parts[1],)
            ).fetchone()
            if row is None or str(row["status"]) != "active":
                return False
            if int(row["version"]) != int(parts[2]):
                return False
            if str(row["scope_kind"]) == "space" and str(row["scope_id"]) != str(space_id):
                return False
            if row["valid_from"] and str(row["valid_from"]) > now:
                return False
            if row["expires_at"] and str(row["expires_at"]) <= now:
                return False
        return True

    @staticmethod
    def _memory_changes_affect_space(
        connection: Any, *, after_epoch: int, space_id: int
    ) -> bool:
        rows = connection.execute(
            """
            SELECT m.scope_kind, m.scope_id
            FROM assistant_memory_changes c
            LEFT JOIN assistant_memories m ON m.id=c.memory_id
            WHERE c.memory_epoch>?
            """,
            (after_epoch,),
        ).fetchall()
        for row in rows:
            if row["scope_kind"] is None:
                return True
            if str(row["scope_kind"]) == "user":
                return True
            if str(row["scope_kind"]) == "space" and str(row["scope_id"]) == str(space_id):
                return True
        return False

    @staticmethod
    def _space(value: dict[str, Any]) -> dict[str, Any]:
        value["source_ids"] = json.loads(value.pop("source_ids_json"))
        value["video_ids"] = json.loads(value.pop("video_ids_json", "[]"))
        value["all_active"] = bool(value["all_active"])
        value["enabled"] = bool(value["enabled"])
        return value

    @staticmethod
    def _run(value: dict[str, Any]) -> dict[str, Any]:
        value["working_state"] = json.loads(value.pop("working_state_json"))
        value["usage"] = json.loads(value.pop("usage_json"))
        value["cancel_requested"] = bool(value["cancel_requested"])
        return value

    @staticmethod
    def _next_message_seq(connection: Any, thread_id: str) -> int:
        row = connection.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS value FROM assistant_messages WHERE thread_id=?",
            (thread_id,),
        ).fetchone()
        return int(row["value"])

    @staticmethod
    def _append_event(connection: Any, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        row = connection.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS value FROM assistant_run_events WHERE run_id=?",
            (run_id,),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO assistant_run_events(run_id, seq, event_type, payload_json, created_at)
            VALUES(?, ?, ?, ?, ?)
            """,
            (run_id, int(row["value"]), event_type, json.dumps(payload, ensure_ascii=False), utc_now()),
        )

    @staticmethod
    def _memory_epoch(connection: Any) -> int:
        row = connection.execute(
            "SELECT value FROM assistant_runtime_state WHERE key='memory_epoch'"
        ).fetchone()
        return int(row["value"] if row else 0)
