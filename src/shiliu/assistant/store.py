from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from shiliu.db import Database, utc_now


ACTIVE_RUN_STATES = {"queued", "running"}


class AssistantConflict(RuntimeError):
    pass


class ModelBudgetWait(RuntimeError):
    code = "background_budget_wait"


class AssistantRunStore:
    def __init__(self, db: Database, *, principal_id: str = "local_operator") -> None:
        self.db = db
        self.principal_id = principal_id

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

    def get_thread(self, thread_id: str) -> dict[str, Any]:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM assistant_threads WHERE id=? AND principal_id=?",
                (thread_id, self.principal_id),
            ).fetchone()
            if row is None:
                raise KeyError(thread_id)
            messages = connection.execute(
                "SELECT * FROM assistant_messages WHERE thread_id=? ORDER BY seq",
                (thread_id,),
            ).fetchall()
            runs = connection.execute(
                "SELECT * FROM assistant_runs WHERE thread_id=? ORDER BY rowid",
                (thread_id,),
            ).fetchall()
            note = connection.execute(
                """
                SELECT note_version, covered_until_message_seq, source_run_ids_json, goal,
                       searched_scope_and_material_refs_json, open_questions_json,
                       next_actions_json, status, updated_at
                FROM assistant_task_notes WHERE thread_id=? AND task_segment=1
                """,
                (thread_id,),
            ).fetchone()
        value = dict(row)
        value["messages"] = [dict(item) for item in messages]
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
            source_runs = set(json.loads(note["source_run_ids_json"] or "[]"))
            value["task_note"]["usable"] = not any(
                item["status"] == "cancelled" and item["id"] in source_runs
                for item in value["runs"]
            )
            value["task_note"].pop("source_run_ids_json", None)
        else:
            value["task_note"] = None
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

    def create_run(self, thread_id: str, *, text: str, request_id: str) -> dict[str, Any]:
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
                "SELECT status FROM assistant_runs WHERE thread_id=? ORDER BY rowid DESC LIMIT 1",
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
                                "auto_memory_admission": admission}), now, now,
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
            connection.execute(
                "UPDATE assistant_threads SET updated_at=? WHERE id=?", (now, thread_id)
            )
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
            updated = connection.execute(
                """
                UPDATE assistant_runs SET status='running', started_at=COALESCE(started_at, ?),
                    updated_at=? WHERE id=? AND status='queued'
                """,
                (now, now, row["id"]),
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

    def run_context(self, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        thread = self.get_thread(str(run["thread_id"]))
        space = self.get_space(int(thread["space_id"]))
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
        return {"run": run, "thread": thread, "space": space}

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
            connection.execute(
                """
                UPDATE assistant_runs SET step_count=?, tool_count=?, usage_json=?, updated_at=?
                WHERE id=? AND status='running'
                """,
                (step_count, tool_count, json.dumps(usage), utc_now(), run_id),
            )

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

    def confirm_model_delivery(self, run_id: str, *, epoch: int,
                               spans: list[dict[str, Any]]) -> None:
        if not spans:
            return
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT working_state_json FROM assistant_runs WHERE id=? AND status='running' AND run_epoch=?",
                (run_id, epoch),
            ).fetchone()
            if row is None:
                return
            working = json.loads(row["working_state_json"] or "{}")
            existing = working.get("model_delivered_read_spans") or []
            seen = {json.dumps(value, sort_keys=True) for value in existing}
            for span in spans:
                key = json.dumps(span, sort_keys=True)
                if key not in seen:
                    existing.append(span)
                    seen.add(key)
            working["model_delivered_read_spans"] = existing[-200:]
            connection.execute(
                "UPDATE assistant_runs SET working_state_json=? WHERE id=? AND status='running' AND run_epoch=?",
                (json.dumps(working, ensure_ascii=False), run_id, epoch),
            )

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
                "collection_search", "collection_read", "knowledge_read",
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
                self.enqueue_job(
                    connection,
                    kind="memory_extract",
                    dedupe_key=f"memory_extract:{run_id}:v1",
                    payload={
                        "run_id": run_id,
                        "thread_id": run["thread_id"],
                        "message_ids": [str(item["id"]) for item in user_messages],
                        "memory_epoch": int(run["extraction_memory_epoch"]),
                        "policy_version": "v1",
                        "auto_enabled_at_enqueue": admission.get("enabled") is True,
                        "auto_memory_generation": int(admission.get("generation", -1)),
                    },
                )
        return "completed"

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
        return bool(names) and names <= {"collection_search", "collection_read"}

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
            "step_budget_exhausted", "tool_budget_exhausted", "context_budget_exceeded"
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

    def pause_run(self, run_id: str, *, code: str, message: str) -> None:
        now = utc_now()
        with self.db.connect() as connection:
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
            working_state["segment_step_base"] = int(row["step_count"])
            working_state["segment_tool_base"] = max(
                int(row["tool_count"]), self.completed_tool_message_count(run_id)
            )
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

    def claim_job(
        self, *, owner: str, lease_seconds: int = 120,
        allow_model_jobs: bool = True, scheduler_reason: str = "normal",
    ) -> dict[str, Any] | None:
        now = datetime.now(timezone.utc)
        now_text = now.isoformat(timespec="seconds")
        lease_until = (now + timedelta(seconds=lease_seconds)).isoformat(timespec="seconds")
        with self.db.connect() as connection:
            connection.execute(
                """
                UPDATE assistant_jobs SET status='queued', lease_owner=NULL, lease_until=NULL,
                    updated_at=? WHERE status='running' AND lease_until<?
                """,
                (now_text, now_text),
            )
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
                  {hold_filter}
                ORDER BY CASE kind WHEN 'memory_purge' THEN 0 WHEN 'memory_index' THEN 1 ELSE 2 END,
                         created_at LIMIT 1
                """,
                (now_text, int(allow_model_jobs)),
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
        return value

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
    ) -> None:
        """Settle an already reserved request without treating missing usage as zero."""
        if lane not in {"foreground", "background"}:
            raise ValueError("invalid_model_budget")
        now = datetime.now(timezone.utc)
        budget_date = now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
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

    def list_jobs(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM assistant_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        values = []
        for row in rows:
            value = dict(row)
            value["payload"] = json.loads(value.pop("payload_json"))
            values.append(value)
        return values

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
