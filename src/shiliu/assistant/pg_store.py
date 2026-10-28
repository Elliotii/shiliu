"""PostgreSQL implementation of the durable Assistant conversation core.

This module is intentionally explicit about ownership and transaction scope.
It is composed with the trusted ``Database`` facade and never initializes DDL.
"""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
import re
import json
import uuid
from typing import Any

from psycopg.types.json import Jsonb

from shiliu.assistant.runtime_contract import AssistantConflict
from shiliu.assistant.pg_access import PgAssistantAccess
from shiliu.storage.dto import assistant_run_dto, row_dto
from shiliu.storage.fences import (
    CoordinationConflict,
    append_run_event,
    cancel_run as cancel_run_row,
    guard_tool_operation as pg_guard_tool_operation,
    lock_thread_run,
    lock_workspace,
)
from shiliu.db import Database


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class PgAssistantRunStore(PgAssistantAccess):
    """Scoped Assistant spaces, threads, runs, messages, events and tools."""

    def __init__(self, db: Database) -> None:
        if not isinstance(db, Database):
            raise TypeError("PgAssistantRunStore requires an injected Database")
        self.db = db
        self.context = db.context
        self.principal_id = self.context.user_id
        self.workspace_id = self.context.workspace_id

    def create_space(self, *, name: str, goal: str = "", source_ids=None,
                     video_ids=None, all_active: bool = False,
                     maintenance_mode: str = "on_demand") -> dict[str, Any]:
        if maintenance_mode not in {"on_demand", "automatic"}:
            raise ValueError("invalid_maintenance_mode")
        source_ids = sorted({int(value) for value in (source_ids or []) if int(value) > 0})
        video_ids = sorted({int(value) for value in (video_ids or []) if int(value) > 0})
        if maintenance_mode == "automatic" and (all_active or not source_ids and not video_ids):
            raise ValueError("automatic_maintenance_requires_explicit_scope")
        now = _now()
        with self.db.connect() as conn:
            row = conn.execute(
                "INSERT INTO shiliu.assistant_spaces(workspace_id,principal_id,name,goal,source_ids_json,"
                "video_ids_json,all_active,maintenance_mode,created_at,updated_at) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                (self.workspace_id, self.principal_id, name.strip(), goal,
                 Jsonb(source_ids), Jsonb(video_ids), bool(all_active), maintenance_mode, now, now),
            ).fetchone()
        return self._space(row)

    def get_space(self, space_id: int, *, conn=None) -> dict[str, Any]:
        with self.db.connect(conn) as c:
            row = c.execute(
                "SELECT * FROM shiliu.assistant_spaces WHERE workspace_id=%s AND principal_id=%s AND id=%s",
                (self.workspace_id, self.principal_id, int(space_id)),
            ).fetchone()
        if row is None:
            raise KeyError(space_id)
        return self._space(row)

    def list_spaces(self, *, conn=None) -> list[dict[str, Any]]:
        with self.db.connect(conn, read_only=True) as conn:
            rows = conn.execute(
                "SELECT * FROM shiliu.assistant_spaces WHERE workspace_id=%s AND principal_id=%s AND enabled "
                "ORDER BY updated_at DESC,id DESC", (self.workspace_id, self.principal_id),
            ).fetchall()
        return [self._space(row) for row in rows]

    @staticmethod
    def _space(row) -> dict[str, Any]:
        value = row_dto(row, timestamps=("created_at", "updated_at"))
        value["source_ids"] = value.pop("source_ids_json")
        value["video_ids"] = value.pop("video_ids_json")
        value["all_active"] = bool(value["all_active"])
        value["enabled"] = bool(value["enabled"])
        return value

    def create_thread(self, space_id: int, *, title: str = "") -> dict[str, Any]:
        space = self.get_space(space_id)
        now = _now()
        thread_id = "athr_" + uuid.uuid4().hex
        with self.db.connect() as conn:
            row = conn.execute(
                "INSERT INTO shiliu.assistant_threads(workspace_id,id,principal_id,space_id,title,created_at,updated_at) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                (self.workspace_id, thread_id, self.principal_id, space["id"], title.strip(), now, now),
            ).fetchone()
        return self._thread(row)

    def update_space(self, space_id, *, expected_scope_version, name=None, goal=None,
                     source_ids=None, video_ids=None, all_active=None, maintenance_mode=None):
        if maintenance_mode is not None and maintenance_mode not in {"on_demand","automatic"}:
            raise ValueError("invalid_maintenance_mode")
        with self.db.connect() as conn:
            lock_workspace(conn,self.context)
            prior=self.get_space(space_id,conn=conn)
            if prior["scope_version"]!=expected_scope_version:raise AssistantConflict("scope_version_conflict")
            sources=prior["source_ids"] if source_ids is None else sorted({int(v) for v in source_ids if int(v)>0})
            videos=prior["video_ids"] if video_ids is None else sorted({int(v) for v in video_ids if int(v)>0})
            all_selected=prior["all_active"] if all_active is None else bool(all_active)
            mode=maintenance_mode or prior["maintenance_mode"]
            if mode=="automatic" and (all_selected or not sources and not videos):
                raise ValueError("automatic_maintenance_requires_explicit_scope")
            changed=source_ids is not None or video_ids is not None or all_active is not None
            if changed:
                roots=conn.execute("SELECT r.id FROM shiliu.assistant_runs r JOIN shiliu.assistant_threads t "
                    "ON (t.workspace_id,t.id)=(r.workspace_id,r.thread_id) WHERE t.workspace_id=%s AND t.principal_id=%s "
                    "AND t.space_id=%s AND r.status IN ('queued','running') ORDER BY t.id,r.insertion_seq",
                    (self.workspace_id,self.principal_id,space_id)).fetchall()
                for root in roots:
                    cancel_run_row(conn,self.context,root["id"])
                    conn.execute("UPDATE shiliu.assistant_runs SET last_error_code='scope_changed',"
                        "last_error_message='Space 范围已变化，请重新提问' WHERE workspace_id=%s AND id=%s",
                        (self.workspace_id,root["id"]))
            conn.execute("UPDATE shiliu.assistant_spaces SET name=%s,goal=%s,source_ids_json=%s,video_ids_json=%s,all_active=%s,"
                "maintenance_mode=%s,scope_version=scope_version+%s,updated_at=clock_timestamp() WHERE workspace_id=%s AND principal_id=%s AND id=%s",
                ((name.strip() or prior["name"]) if name is not None else prior["name"],goal.strip() if goal is not None else prior["goal"],
                 Jsonb(sources),Jsonb(videos),all_selected,mode,int(changed),self.workspace_id,self.principal_id,space_id))
            if changed:
                conn.execute("UPDATE assistant_wiki_proposals SET status='stale',decided_at=clock_timestamp(),updated_at=clock_timestamp(),payload_json=jsonb_set(payload_json,'{decision_reason}','\"scope_changed\"') WHERE workspace_id=%s AND principal_id=%s AND space_id=%s AND kind='source_patch' AND status='pending'", (self.workspace_id,self.principal_id,space_id))
            if changed and mode=="automatic":
                self._enqueue_scope_repairs(conn,space_id=space_id,scope_version=expected_scope_version+1,
                    selected_sources=set(sources),selected_videos=set(videos),all_active=all_selected)
        return self.get_space(space_id)

    def _enqueue_scope_repairs(self, conn, *, space_id, scope_version, selected_sources, selected_videos, all_active):
        pages=conn.execute("SELECT id,title FROM shiliu.assistant_wiki_pages WHERE workspace_id=%s AND principal_id=%s "
            "AND space_id=%s AND status='active'",(self.workspace_id,self.principal_id,space_id)).fetchall()
        for page in pages:
            materials=conn.execute("SELECT m.video_id,h.current_revision,v.is_ignored,v.archived_at FROM shiliu.assistant_wiki_materials m "
                "JOIN shiliu.assistant_source_heads h ON h.workspace_id=m.workspace_id AND h.video_id=m.video_id AND h.principal_id=%s "
                "JOIN shiliu.videos v ON (v.workspace_id,v.id)=(m.workspace_id,m.video_id) WHERE m.workspace_id=%s AND m.page_id=%s",
                (self.principal_id,self.workspace_id,page["id"])).fetchall()
            available=[];lost=False
            for material in materials:
                memberships=conn.execute("SELECT m.source_id FROM shiliu.video_source_memberships m JOIN shiliu.favorite_sources s "
                    "ON (s.workspace_id,s.id)=(m.workspace_id,m.source_id) WHERE m.workspace_id=%s AND m.video_id=%s "
                    "AND m.removed_at IS NULL AND s.status='active'",(self.workspace_id,material["video_id"])).fetchall()
                visible=(not material["is_ignored"] and not material["archived_at"] and
                    (not selected_videos or material["video_id"] in selected_videos) and
                    any(all_active or m["source_id"] in selected_sources for m in memberships))
                if not visible:lost=True
                elif material["current_revision"] and conn.execute("SELECT 1 FROM shiliu.assistant_source_cards "
                    "WHERE workspace_id=%s AND revision=%s",(self.workspace_id,material["current_revision"])).fetchone():
                    available.append((material["video_id"],material["current_revision"]))
            if lost and available:
                video_id,revision=available[0]
                self.enqueue_job(conn,kind="wiki_integrate",dedupe_key=f"wiki_repair_scope:{space_id}:{page['id']}:{scope_version}",
                    payload={"space_id":space_id,"scope_version":scope_version,"video_id":video_id,"revision":revision,
                             "topic":page["title"],"repair_page_id":page["id"]})

    def list_threads(self, *, space_id, limit=30, before_updated_at=None, before_id=None):
        self.get_space(space_id)
        if (before_updated_at is None)!=(before_id is None) or type(limit) is not int or not 1<=limit<=100:
            raise ValueError("invalid_thread_cursor")
        with self.db.connect(read_only=True) as conn:
            rows=conn.execute("SELECT t.id,t.space_id,t.title,t.created_at,t.updated_at,"
                "(SELECT m.content FROM shiliu.assistant_messages m WHERE m.workspace_id=t.workspace_id AND m.thread_id=t.id AND m.role='user' ORDER BY m.seq LIMIT 1) AS first_input,"
                "(SELECT r.status FROM shiliu.assistant_runs r WHERE r.workspace_id=t.workspace_id AND r.thread_id=t.id ORDER BY r.insertion_seq DESC LIMIT 1) AS run_status,"
                "(SELECT r.last_error_code FROM shiliu.assistant_runs r WHERE r.workspace_id=t.workspace_id AND r.thread_id=t.id ORDER BY r.insertion_seq DESC LIMIT 1) AS last_error_code "
                "FROM shiliu.assistant_threads t WHERE t.workspace_id=%s AND t.principal_id=%s AND t.space_id=%s "
                "AND EXISTS(SELECT 1 FROM shiliu.assistant_messages m WHERE m.workspace_id=t.workspace_id AND m.thread_id=t.id AND m.role='user') "
                "AND (%s::timestamptz IS NULL OR (t.updated_at,t.id)<(%s::timestamptz,%s)) ORDER BY t.updated_at DESC,t.id DESC LIMIT %s",
                (self.workspace_id,self.principal_id,space_id,before_updated_at,before_updated_at,before_id,limit+1)).fetchall()
        page=[]
        for row in rows[:limit]:
            value=row_dto(row,timestamps=("created_at","updated_at"))
            value["title"]=(str(value["title"] or value.pop("first_input") or "新对话").strip().replace("\n"," ")[:48])
            value.pop("first_input",None);page.append(value)
        cursor={"before_updated_at":page[-1]["updated_at"],"before_id":page[-1]["id"]} if len(rows)>limit else None
        return {"threads":page,"next_cursor":cursor}

    @staticmethod
    def _thread(row) -> dict[str, Any]:
        value = row_dto(row, timestamps=("created_at", "updated_at"))
        value["context_state"] = dict(value.get("context_state_json") or {})
        value["messages"] = []
        value["runs"] = []
        value["task_note"] = {}
        return value

    @staticmethod
    def _current_action_run_id(runs):
        active=next((r for r in reversed(runs) if r["status"] in {"queued","running"}),None)
        if active:return active["id"]
        latest=runs[-1] if runs else None
        return latest["id"] if latest and latest["status"] in {"interrupted","budget_exhausted","failed"} else None

    def get_thread(self, thread_id: str, *, include_internal: bool = False, conn=None) -> dict[str, Any]:
        with self.db.connect(conn, read_only=True) as conn:
            row = conn.execute(
                "SELECT * FROM shiliu.assistant_threads WHERE workspace_id=%s AND principal_id=%s AND id=%s",
                (self.workspace_id, self.principal_id, thread_id),
            ).fetchone()
            if row is None:
                raise KeyError(thread_id)
            value = self._thread(row)
            value["messages"] = [row_dto(r, timestamps=("created_at",)) for r in conn.execute(
                "SELECT m.*,c.result_json AS resolved_tool_result_json FROM shiliu.assistant_messages m "
                "LEFT JOIN shiliu.assistant_tool_calls c ON c.workspace_id=m.workspace_id AND c.run_id=m.run_id "
                "AND c.call_id=m.provider_payload_json->>'tool_call_id' WHERE m.workspace_id=%s AND m.thread_id=%s ORDER BY m.seq",
                (self.workspace_id, thread_id),
            ).fetchall()]
            for message in value["messages"]:
                result=message.pop("resolved_tool_result_json",None)
                if include_internal:
                    message["_raw_content"]=message["content"]
                else:
                    payload=dict(message["provider_payload_json"] or {})
                    payload.pop("model_projection",None)
                    message["provider_payload_json"]=payload
                if message["role"]=="tool":
                    recorded=json.loads(message["content"] or "{}")
                    if recorded.get("_assistant_result_ref"):
                        message["content"]=json.dumps(result or {"status":"error","error_code":"tool_result_unavailable"},ensure_ascii=False)
            runs = conn.execute(
                "SELECT * FROM shiliu.assistant_runs WHERE workspace_id=%s AND thread_id=%s ORDER BY insertion_seq",
                (self.workspace_id, thread_id),
            ).fetchall()
            current = self._current_action_run_id(runs)
            value["runs"] = [assistant_run_dto(r, current=r["id"] == current) for r in runs]
            note = conn.execute(
                "SELECT * FROM shiliu.assistant_task_notes WHERE workspace_id=%s AND thread_id=%s "
                "AND task_segment=1", (self.workspace_id, thread_id),
            ).fetchone()
            if note:
                value["task_note"] = {key.removesuffix("_json"): item for key, item in note.items()}
                checkpoint=note["checkpoint_json"] or {};binding=value["context_state"].get("checkpoint") or {}
                usable=(note["status"]=="active" and checkpoint.get("format_version")==1 and
                    binding.get("id")==note["id"] and binding.get("version")==note["note_version"] and
                    isinstance(checkpoint.get("text"),str) and bool(checkpoint["text"].strip()))
                value["task_note"]["usable"]=usable
                value["task_note"]["searched_scope_and_material_refs"]=checkpoint.get("material_index",[]) if usable else []
            formal_ids={r["message_id"] for r in conn.execute("SELECT e.payload_json->>'message_id' AS message_id "
                "FROM shiliu.assistant_run_events e JOIN shiliu.assistant_runs r ON (r.workspace_id,r.id)=(e.workspace_id,e.run_id) "
                "WHERE r.workspace_id=%s AND r.thread_id=%s AND r.status='completed' AND e.event_type='run_completed'",
                (self.workspace_id,thread_id))}
            users={m["run_id"]:m["content"] for m in value["messages"] if m["role"]=="user"}
            candidates=[]
            for message in value["messages"]:
                if message["id"] not in formal_ids or not message["content"].strip():continue
                if (message["provider_payload_json"] or {}).get("origin")=="operation_receipt":continue
                text=str(users.get(message["run_id"],"")).strip()
                if re.fullmatch(r"(?:你好|您好|嗨|哈喽|谢谢|感谢|再见|hello|hi|thanks)[呀啊哦啦!！。，,.~～\s]*",text,re.I):continue
                if re.match(r"^(?:请)?(?:停止|继续|确认|拒绝|忽略|恢复|删除|归档|撤销|保存|记住|忘记)",text) and not re.search(r"研究|比较|解释|分析|回答|如何|为什么",text):continue
                if message["content"].startswith("这次已停止探索，当前请求是："):continue
                candidates.append(message["id"])
            value["save_answer_message_id"]=candidates[-1] if candidates else None
            value["can_save"]=bool(candidates) and current is None
            value["task_focus"]=next((r["working_state"].get("task_focus") for r in reversed(value["runs"]) if r["working_state"].get("task_focus")),None)
            if not include_internal:
                value.pop("context_state",None);value.pop("context_state_json",None)
                value["task_note"].pop("checkpoint",None)
                value["task_note"].pop("source_run_ids",None)
        return value

    def create_run(self, thread_id: str, *, text: str, request_id: str,
                   answer_message_id: str | None = None, receipt_only: bool = False) -> dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("input_empty")
        # Preserve subsecond creation identity for the manual-trial admission
        # boundary; rounding down could permanently skip a newly accepted run.
        now = datetime.now(timezone.utc)
        try:
            with self.db.connect() as conn:
                lock_workspace(conn,self.context)
                thread = conn.execute(
                    "SELECT * FROM shiliu.assistant_threads WHERE workspace_id=%s AND principal_id=%s "
                    "AND id=%s FOR UPDATE", (self.workspace_id, self.principal_id, thread_id),
                ).fetchone()
                if thread is None:
                    raise KeyError(thread_id)
                existing = conn.execute(
                    "SELECT * FROM shiliu.assistant_runs WHERE workspace_id=%s AND thread_id=%s AND request_id=%s",
                    (self.workspace_id, thread_id, request_id),
                ).fetchone()
                if existing is not None:
                    all_runs = conn.execute(
                        "SELECT id,status FROM shiliu.assistant_runs WHERE workspace_id=%s AND thread_id=%s "
                        "ORDER BY insertion_seq", (self.workspace_id, thread_id),
                    ).fetchall()
                    current = self._current_action_run_id(all_runs)==existing["id"]
                    return assistant_run_dto(existing, current=current)

                active = conn.execute(
                    "SELECT id FROM shiliu.assistant_runs WHERE workspace_id=%s AND thread_id=%s "
                    "AND status IN ('queued','running') LIMIT 1", (self.workspace_id, thread_id),
                ).fetchone()
                latest = conn.execute(
                    "SELECT status,working_state_json FROM shiliu.assistant_runs WHERE workspace_id=%s "
                    "AND thread_id=%s ORDER BY insertion_seq DESC LIMIT 1", (self.workspace_id, thread_id),
                ).fetchone()
                if active or latest and latest["status"] in {"interrupted", "budget_exhausted", "failed"}:
                    raise AssistantConflict("thread_has_active_run")
                space = self.get_space(thread["space_id"], conn=conn)
                policy_rows = conn.execute(
                    "SELECT key,value FROM shiliu.assistant_runtime_state WHERE workspace_id=%s AND principal_id=%s "
                    "AND key IN ('auto_memory_enabled','auto_memory_generation')",
                    (self.workspace_id, self.principal_id),
                ).fetchall()
                policy = {str(r["key"]): str(r["value"]) for r in policy_rows}
                epoch = int(self._memory_epoch(conn))
                run_id = "arun_" + uuid.uuid4().hex
                working = {"scope_version": int(space["scope_version"]),
                           "auto_memory_admission": {"enabled": policy.get("auto_memory_enabled", "1") != "0",
                                                      "generation": int(policy.get("auto_memory_generation", "0"))},
                           "task_subset": (latest["working_state_json"].get("task_subset") if latest else None)}
                conn.execute(
                    "INSERT INTO shiliu.assistant_runs(workspace_id,id,thread_id,request_id,status,run_epoch,memory_epoch,"
                    "extraction_memory_epoch,observed_memory_epoch,working_state_json,created_at,updated_at) "
                    "VALUES(%s,%s,%s,%s,'queued',1,%s,%s,%s,%s,%s,%s) RETURNING *",
                    (self.workspace_id, run_id, thread_id, request_id, epoch, epoch, epoch, Jsonb(working), now, now),
                )
                seq = conn.execute(
                    "SELECT COALESCE(MAX(seq),0)+1 AS seq FROM shiliu.assistant_messages "
                    "WHERE workspace_id=%s AND thread_id=%s", (self.workspace_id, thread_id),
                ).fetchone()["seq"]
                message_id = "amsg_" + uuid.uuid4().hex
                conn.execute(
                    "INSERT INTO shiliu.assistant_messages(workspace_id,id,thread_id,run_id,seq,role,content,created_at) "
                    "VALUES(%s,%s,%s,%s,%s,'user',%s,%s)",
                    (self.workspace_id, message_id, thread_id, run_id, seq, text.strip(), now),
                )
                if answer_message_id:
                    self._bind_save_request(conn, run_id, thread_id, message_id, text, answer_message_id,
                                            receipt_only=receipt_only)
                conn.execute("UPDATE shiliu.assistant_threads SET updated_at=%s WHERE workspace_id=%s AND id=%s",
                             (now, self.workspace_id, thread_id))
                conn.execute("INSERT INTO shiliu.assistant_runtime_state(workspace_id,principal_id,key,value,updated_at) "
                             "VALUES(%s,%s,'last_user_activity_at',%s,%s) ON CONFLICT(workspace_id,principal_id,key) "
                             "DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                             (self.workspace_id, self.principal_id, now.isoformat(), now))
                self._append_event(conn, run_id, "run_queued", {"message_id": message_id}, now=now)
            return self.get_run(run_id)
        except CoordinationConflict as exc:
            raise AssistantConflict(str(exc)) from exc

    def _bind_save_request(self, conn, run_id, thread_id, message_id, text, answer_message_id, *, receipt_only):
        row = conn.execute("SELECT working_state_json FROM shiliu.assistant_runs "
                           "WHERE workspace_id=%s AND id=%s", (self.workspace_id, run_id)).fetchone()
        working = dict(row["working_state_json"] or {})
        if working.get("knowledge_save"):
            return working["knowledge_save"]
        answer = conn.execute(
            "SELECT m.id,m.run_id FROM shiliu.assistant_messages m JOIN shiliu.assistant_threads t "
            "ON (t.workspace_id,t.id)=(m.workspace_id,m.thread_id) WHERE m.workspace_id=%s AND m.id=%s "
            "AND m.thread_id=%s AND t.principal_id=%s AND m.role='assistant' "
            "AND COALESCE(m.provider_payload_json->>'origin','model')<>'operation_receipt' "
            "AND EXISTS(SELECT 1 FROM shiliu.assistant_run_events e WHERE e.workspace_id=m.workspace_id "
            "AND e.run_id=m.run_id AND e.event_type='run_completed' AND e.payload_json->>'message_id'=m.id)",
            (self.workspace_id, answer_message_id, thread_id, self.principal_id),
        ).fetchone()
        if answer is None:
            raise AssistantConflict("save_answer_not_available")
        binding = {"source_message_id": message_id, "request_key": "save-message:" + message_id,
                   "answer_message_id": answer["id"], "answer_run_id": answer["run_id"],
                   "scope_text": text, "receipt_only": bool(receipt_only)}
        working["knowledge_save"] = binding
        conn.execute("UPDATE shiliu.assistant_runs SET working_state_json=%s "
                     "WHERE workspace_id=%s AND id=%s", (Jsonb(working), self.workspace_id, run_id))
        return binding

    def _memory_epoch(self, conn) -> int:
        row = conn.execute("SELECT value FROM shiliu.assistant_runtime_state WHERE workspace_id=%s AND principal_id=%s "
                           "AND key='memory_epoch'", (self.workspace_id, self.principal_id)).fetchone()
        return int(row["value"] if row else 0)

    def _append_event(self, conn, run_id: str, event_type: str, payload: dict[str, Any], *, now=None):
        # Caller must already own the thread/run root lock. The shared helper
        # re-locks in the documented order and allocates the ordinal under it.
        append_run_event(conn, self.context, run_id, event_type, payload)

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self.db.connect(read_only=True) as conn:
            run = conn.execute(
                "SELECT r.* FROM shiliu.assistant_runs r JOIN shiliu.assistant_threads t "
                "ON (t.workspace_id,t.id)=(r.workspace_id,r.thread_id) WHERE r.workspace_id=%s "
                "AND r.id=%s AND t.principal_id=%s", (self.workspace_id, run_id, self.principal_id),
            ).fetchone()
            if run is None:
                raise KeyError(run_id)
            runs = conn.execute("SELECT id,status FROM shiliu.assistant_runs WHERE workspace_id=%s AND thread_id=%s ORDER BY insertion_seq",
                                (self.workspace_id,run["thread_id"])).fetchall()
            return assistant_run_dto(run,current=self._current_action_run_id(runs)==run_id)

    def events(self, run_id: str, *, after_seq: int = 0) -> list[dict[str, Any]]:
        self.get_run(run_id)
        with self.db.connect(read_only=True) as conn:
            rows = conn.execute(
                "SELECT seq,event_type,payload_json,created_at FROM shiliu.assistant_run_events "
                "WHERE workspace_id=%s AND run_id=%s AND seq>%s ORDER BY seq LIMIT 200",
                (self.workspace_id, run_id, int(after_seq)),
            ).fetchall()
        return [dict(seq=int(row["seq"]), event_type=row["event_type"],
                     payload=row["payload_json"], created_at=row["created_at"].isoformat(timespec="seconds"))
                for row in rows]

    def resolve_run_result(self, result_ref: str, *, current_thread_id: str,
                           current_scope_version: int) -> dict[str, Any]:
        parts = result_ref.split(":")
        if len(parts) == 3 and parts[0] == "run-result":
            requested, call_id = parts[1:]
        elif len(parts) == 2 and parts[0] == "tool_call_id":
            requested, call_id = None, parts[1]
        else:
            raise ValueError("invalid_result_ref")
        if not call_id:
            raise ValueError("invalid_result_ref")
        with self.db.connect(read_only=True) as conn:
            self.get_thread(current_thread_id)
            row = conn.execute(
                "SELECT t.*,r.working_state_json FROM shiliu.assistant_tool_calls t "
                "JOIN shiliu.assistant_runs r ON (r.workspace_id,r.id)=(t.workspace_id,t.run_id) "
                "WHERE t.workspace_id=%s AND r.thread_id=%s AND t.call_id=%s AND t.status='completed' "
                "AND (%s::text IS NULL OR t.run_id=%s) ORDER BY t.completed_at DESC LIMIT 1",
                (self.workspace_id,current_thread_id,call_id,requested,requested),
            ).fetchone()
            if row is None or not row["result_json"]:
                raise KeyError(result_ref)
            if int((row["working_state_json"] or {}).get("scope_version",1)) != int(current_scope_version):
                raise ValueError("result_outside_current_scope")
            return {"run_id": row["run_id"], "call_id": row["call_id"], "name": row["name"],
                    "arguments": row["args_json"], "result": row["result_json"],
                    "result_ref": f"run-result:{row['run_id']}:{row['call_id']}"}

    def pending_tool_batch(self, run_id: str) -> list[dict[str, Any]]:
        with self.db.connect(read_only=True) as conn:
            run = conn.execute("SELECT thread_id FROM shiliu.assistant_runs WHERE workspace_id=%s AND id=%s",
                               (self.workspace_id,run_id)).fetchone()
            if run is None:
                raise KeyError(run_id)
            rows = conn.execute("SELECT role,provider_payload_json FROM shiliu.assistant_messages "
                                "WHERE workspace_id=%s AND thread_id=%s AND run_id=%s ORDER BY seq",
                                (self.workspace_id,run["thread_id"],run_id)).fetchall()
        for index in range(len(rows)-1,-1,-1):
            item=rows[index]
            if item["role"] != "assistant":
                continue
            calls=(item["provider_payload_json"] or {}).get("tool_calls") or []
            if not calls:
                continue
            returned={(r["provider_payload_json"] or {}).get("tool_call_id")
                      for r in rows[index+1:] if r["role"] == "tool"}
            return [] if len(returned.intersection(c.get("id") for c in calls)) == len(calls) else [dict(c) for c in calls]
        return []

    def tool_result_message_exists(self, run_id: str, call_id: str) -> bool:
        with self.db.connect(read_only=True) as conn:
            rows=conn.execute("SELECT provider_payload_json FROM shiliu.assistant_messages "
                              "WHERE workspace_id=%s AND run_id=%s AND role='tool'",
                              (self.workspace_id,run_id)).fetchall()
        return any((row["provider_payload_json"] or {}).get("tool_call_id")==call_id for row in rows)

    def completed_tool_message_count(self, run_id: str) -> int:
        with self.db.connect(read_only=True) as conn:
            row=conn.execute("SELECT count(*) AS n FROM shiliu.assistant_messages "
                             "WHERE workspace_id=%s AND run_id=%s AND role='tool'",
                             (self.workspace_id,run_id)).fetchone()
        return int(row["n"])

    @contextmanager
    def tool_execution_scope(self, run_id: str, epoch: int):
        from shiliu.assistant.runtime_contract import _TOOL_EXECUTION
        token = _TOOL_EXECUTION.set((run_id, epoch))
        try:
            yield
        finally:
            _TOOL_EXECUTION.reset(token)

    def guard_tool_operation(self, conn, operation_key: str = "", *,
                             expected_run_id: str | None = None, expected_epoch: int | None = None):
        from shiliu.assistant.runtime_contract import _TOOL_EXECUTION
        active = _TOOL_EXECUTION.get()
        if active is not None:
            if expected_run_id is not None and (active[0] != expected_run_id or
                    expected_epoch is not None and active[1] != expected_epoch):
                raise AssistantConflict("run_fenced")
            expected_run_id, expected_epoch = active
        if expected_run_id is None:
            if expected_epoch is not None or operation_key.startswith("tool:"):
                raise AssistantConflict("expected_run_epoch_required")
            return None
        try:
            return pg_guard_tool_operation(conn, self.context, expected_run_id, expected_epoch)
        except CoordinationConflict as exc:
            raise AssistantConflict(str(exc)) from exc

    def _guard_run_completion(self, conn, run_id: str, epoch: int):
        """Final dispatch/completion remain authorized after business tools stop."""
        if type(epoch) is not int or epoch < 1:
            raise AssistantConflict("expected_epoch_required")
        try:
            run = lock_thread_run(conn, self.context, run_id)
        except CoordinationConflict as exc:
            raise AssistantConflict(str(exc)) from exc
        state = run["working_state_json"]
        if (run["run_epoch"] != epoch or run["status"] != "running" or
                run["cancel_requested"] or not isinstance(state, dict)):
            raise AssistantConflict("run_fenced")
        if "execution_budget" in state:
            try:
                deadline = datetime.fromisoformat(state["execution_budget"]["deadline_at"].replace("Z", "+00:00"))
                if deadline.tzinfo is None:
                    raise ValueError("unzoned_deadline")
            except (KeyError, TypeError, ValueError, AttributeError):
                raise AssistantConflict("run_fenced") from None
            if not conn.execute("SELECT %s::timestamptz>clock_timestamp() AS valid", (deadline,)).fetchone()["valid"]:
                raise AssistantConflict("run_fenced")
        return run

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        try:
            with self.db.connect() as conn:
                cancel_run_row(conn, self.context, run_id)
                conn.execute("INSERT INTO shiliu.assistant_runtime_state(workspace_id,principal_id,key,value,updated_at) "
                             "VALUES(%s,%s,'last_user_activity_at',clock_timestamp()::text,clock_timestamp()) "
                             "ON CONFLICT(workspace_id,principal_id,key) DO UPDATE SET "
                             "value=excluded.value,updated_at=excluded.updated_at",
                             (self.workspace_id, self.principal_id))
            return self.get_run(run_id)
        except CoordinationConflict as exc:
            raise AssistantConflict(str(exc)) from exc

    def begin_tool_call(self, run_id: str, *, ordinal: int, call_id: str, name: str,
                        arguments: dict[str, Any], operation_key: str | None = None,
                        expected_epoch: int | None = None, reuse_validator=None):
        """Persist a tool intent under the genuine run fence before side effects."""
        with self.db.connect() as conn:
            self.guard_tool_operation(conn, expected_run_id=run_id,
                                      expected_epoch=expected_epoch)
            existing = conn.execute(
                "SELECT * FROM shiliu.assistant_tool_calls WHERE workspace_id=%s AND run_id=%s AND call_id=%s",
                (self.workspace_id, run_id, call_id),
            ).fetchone()
            if existing is not None:
                return dict(existing)
            encoded = Jsonb(arguments)
            reusable = None
            if reuse_validator and name in {"search_knowledge", "collection_read", "knowledge_read"}:
                reusable = conn.execute(
                    "SELECT * FROM shiliu.assistant_tool_calls WHERE workspace_id=%s AND run_id=%s AND name=%s "
                    "AND args_json=%s AND status='completed' AND result_json IS NOT NULL ORDER BY ordinal DESC LIMIT 1",
                    (self.workspace_id, run_id, name, encoded),
                ).fetchone()
            if reusable:
                result = reusable["result_json"]
                valid = (isinstance(result, dict) and result.get("status") == "ok"
                         and not result.get("retryable")
                         and bool(reuse_validator({**dict(reusable), "result": result})))
                if valid:
                    result = {**result, "call_id": call_id,
                              "result_ref": f"run-result:{run_id}:{call_id}",
                              "coverage": {**(result.get("coverage") or {}), "cache_hit": True,
                                           "retrieval_requests_this_call": 0}}
                    conn.execute(
                        "INSERT INTO shiliu.assistant_tool_calls(workspace_id,id,run_id,ordinal,call_id,name,args_json,"
                        "status,result_json,operation_key,created_at,completed_at) "
                        "VALUES(%s,%s,%s,%s,%s,%s,%s,'completed',%s,%s,clock_timestamp(),clock_timestamp())",
                        (self.workspace_id, "atc_" + uuid.uuid4().hex, run_id, ordinal, call_id, name,
                         encoded, Jsonb(result), operation_key),
                    )
                    self._append_event(conn, run_id, "tool_reused",
                                       {"name": name, "call_id": call_id,
                                        "reused_call_id": reusable["call_id"]})
                    return {**dict(reusable), "call_id": call_id, "ordinal": ordinal,
                            "result_json": result}
            conn.execute(
                "INSERT INTO shiliu.assistant_tool_calls(workspace_id,id,run_id,ordinal,call_id,name,args_json,"
                "status,operation_key,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,'running',%s,clock_timestamp())",
                (self.workspace_id, "atc_" + uuid.uuid4().hex, run_id, ordinal, call_id,
                 name, encoded, operation_key),
            )
            self._append_event(conn, run_id, "tool_started", {"name": name, "call_id": call_id})
        return None

    def finish_tool_call(self, run_id: str, *, call_id: str, result: dict[str, Any], expected_epoch: int | None = None):
        with self.db.connect() as conn:
            self.guard_tool_operation(conn, expected_run_id=run_id,
                                      expected_epoch=expected_epoch)
            row = conn.execute(
                "UPDATE shiliu.assistant_tool_calls SET status='completed',result_json=%s,completed_at=clock_timestamp() "
                "WHERE workspace_id=%s AND run_id=%s AND call_id=%s AND status='running' RETURNING id",
                (Jsonb(result), self.workspace_id, run_id, call_id),
            ).fetchone()
            if row is None:
                raise AssistantConflict("tool_intent_not_running")
            self._append_event(conn, run_id, "tool_completed",
                               {"call_id": call_id, "summary": str(result.get("summary") or "")[:300]})

    def save_message(self, run_id: str, *, role: str, content: str,
                     provider_payload: dict[str, Any] | None = None,
                     expected_epoch: int | None = None) -> str:
        if role not in {"user", "assistant", "tool", "system"}:
            raise ValueError("message_role_invalid")
        with self.db.connect() as conn:
            self.guard_tool_operation(conn, expected_run_id=run_id, expected_epoch=expected_epoch)
            root = conn.execute("SELECT thread_id FROM shiliu.assistant_runs WHERE workspace_id=%s AND id=%s",
                                (self.workspace_id, run_id)).fetchone()
            seq = conn.execute("SELECT COALESCE(MAX(seq),0)+1 AS seq FROM shiliu.assistant_messages "
                               "WHERE workspace_id=%s AND thread_id=%s",
                               (self.workspace_id, root["thread_id"])).fetchone()["seq"]
            message_id = "amsg_" + uuid.uuid4().hex
            conn.execute("INSERT INTO shiliu.assistant_messages(workspace_id,id,thread_id,run_id,seq,role,content,"
                         "provider_payload_json,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp())",
                         (self.workspace_id, message_id, root["thread_id"], run_id, seq, role, content,
                          Jsonb(provider_payload or {})))
            return message_id

    def save_assistant_tool_message(self, run_id: str, *, content: str,
                                    provider_payload: dict[str, Any], expected_epoch: int | None = None):
        return self.save_message(run_id, role="assistant", content=content,
                                 provider_payload=provider_payload, expected_epoch=expected_epoch)

    def save_tool_result_message(self, run_id: str, *, content: str,
                                 provider_payload: dict[str, Any], expected_epoch: int | None = None):
        call_id = str(provider_payload.get("tool_call_id") or "")
        if not call_id:
            raise ValueError("tool_call_id_required")
        with self.db.connect() as conn:
            self.guard_tool_operation(conn, expected_run_id=run_id,
                                      expected_epoch=expected_epoch)
            receipt = conn.execute("SELECT result_json FROM shiliu.assistant_tool_calls WHERE workspace_id=%s "
                                   "AND run_id=%s AND call_id=%s AND status='completed'",
                                   (self.workspace_id, run_id, call_id)).fetchone()
            if receipt and receipt["result_json"] is not None and receipt["result_json"] == json.loads(content):
                content = json.dumps({"_assistant_result_ref": f"run-result:{run_id}:{call_id}"})
            root = conn.execute("SELECT thread_id FROM shiliu.assistant_runs WHERE workspace_id=%s AND id=%s",
                                (self.workspace_id, run_id)).fetchone()
            seq = conn.execute("SELECT COALESCE(MAX(seq),0)+1 AS seq FROM shiliu.assistant_messages "
                               "WHERE workspace_id=%s AND thread_id=%s",
                               (self.workspace_id, root["thread_id"])).fetchone()["seq"]
            message_id = "amsg_" + uuid.uuid4().hex
            conn.execute("INSERT INTO shiliu.assistant_messages(workspace_id,id,thread_id,run_id,seq,role,content,"
                         "provider_payload_json,created_at) VALUES(%s,%s,%s,%s,%s,'tool',%s,%s,clock_timestamp())",
                         (self.workspace_id, message_id, root["thread_id"], run_id, seq, content,
                          Jsonb(provider_payload)))
            return message_id

    @staticmethod
    def message_context_fingerprint(message: dict[str, Any]) -> str:
        import hashlib
        payload = dict(message.get("provider_payload_json") or {})
        payload.pop("model_projection", None)
        value = {key: message.get(key) for key in
                 ("id", "thread_id", "run_id", "seq", "role", "created_at")}
        value.update(content=message.get("_raw_content", message.get("content")),
                     resolved_content=message.get("content"), payload=payload)
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def install_working_context(self, conn, *, thread_id: str, state: dict,
                                projections: dict[str, dict]) -> None:
        from shiliu.assistant.delivery import validate_model_sequence

        thread = conn.execute("SELECT id FROM shiliu.assistant_threads WHERE workspace_id=%s AND principal_id=%s "
                              "AND id=%s FOR UPDATE", (self.workspace_id, self.principal_id, thread_id)).fetchone()
        if thread is None:
            raise KeyError(thread_id)
        entries = state.get("entries") or []
        message_ids = [entry["message_id"] for entry in entries if entry.get("kind") == "message"]
        if len(message_ids) != len(set(message_ids)) or set(projections) - set(message_ids):
            raise AssistantConflict("working_context_message_identity")
        binding = state.get("checkpoint")
        if binding:
            note = conn.execute("SELECT id,note_version,status,checkpoint_json FROM shiliu.assistant_task_notes "
                                "WHERE workspace_id=%s AND thread_id=%s AND task_segment=1 FOR UPDATE",
                                (self.workspace_id, thread_id)).fetchone()
            if (note is None or note["id"] != binding["id"] or note["note_version"] != binding["version"]
                    or note["status"] != "active" or (note["checkpoint_json"] or {}).get("format_version") != 1):
                raise AssistantConflict("working_checkpoint_changed")
        sequence, updates = [], []
        for entry in entries:
            if entry.get("kind") == "block":
                sequence.append({"role": "system", "content": entry["content"]})
                continue
            if entry.get("kind") != "message":
                raise AssistantConflict("working_context_entry_invalid")
            row = conn.execute(
                "SELECT m.*,t.result_json AS resolved_tool_result_json FROM shiliu.assistant_messages m "
                "LEFT JOIN shiliu.assistant_tool_calls t ON t.workspace_id=m.workspace_id AND t.run_id=m.run_id "
                "AND t.call_id=m.provider_payload_json->>'tool_call_id' WHERE m.workspace_id=%s "
                "AND m.id=%s AND m.thread_id=%s FOR UPDATE OF m",
                (self.workspace_id, entry["message_id"], thread_id),
            ).fetchone()
            if row is None:
                raise AssistantConflict("working_context_message_missing")
            fingerprint_row = row_dto(row, timestamps=("created_at",))
            if row["role"] == "tool" and isinstance(row["content"], str):
                ref = json.loads(row["content"] or "{}")
                if ref.get("_assistant_result_ref"):
                    fingerprint_row["_raw_content"] = row["content"]
                    fingerprint_row["content"] = json.dumps(row["resolved_tool_result_json"] or
                        {"status": "error", "error_code": "tool_result_unavailable"},ensure_ascii=False)
            payload = dict(row["provider_payload_json"] or {})
            stored, proposed = payload.get("model_projection"), projections.get(entry["message_id"])
            projection = stored or proposed
            if (not projection or projection.get("format_version") != 1
                    or projection.get("source_fingerprint") != self.message_context_fingerprint(fingerprint_row)
                    or projection.get("message", {}).get("role") != row["role"]):
                raise AssistantConflict("working_projection_invalid")
            if stored and proposed and {k:v for k,v in stored.items() if k != "delivery"} != {
                    k:v for k,v in proposed.items() if k != "delivery"}:
                raise AssistantConflict("working_projection_frozen")
            sequence.append(projection["message"])
            if not stored:
                payload["model_projection"] = projection
                updates.append((Jsonb(payload), row["id"]))
        validate_model_sequence(sequence)
        for payload, message_id in updates:
            conn.execute("UPDATE shiliu.assistant_messages SET provider_payload_json=%s "
                         "WHERE workspace_id=%s AND id=%s", (payload, self.workspace_id, message_id))
        conn.execute("UPDATE shiliu.assistant_threads SET context_state_json=%s "
                     "WHERE workspace_id=%s AND principal_id=%s AND id=%s",
                     (Jsonb(state), self.workspace_id, self.principal_id, thread_id))

    def working_source_guard(self, conn, *, space_id: int) -> str:
        import hashlib
        queries = [
            ("SELECT principal_id,video_id,current_revision FROM shiliu.assistant_source_heads WHERE workspace_id=%s AND principal_id=%s ORDER BY id", (self.workspace_id,self.principal_id)),
            ("SELECT id,status,is_ignored,removed_at,updated_at FROM shiliu.videos WHERE workspace_id=%s ORDER BY id", (self.workspace_id,)),
            ("SELECT id,status FROM shiliu.favorite_sources WHERE workspace_id=%s ORDER BY id", (self.workspace_id,)),
            ("SELECT source_id,video_id,removed_at FROM shiliu.video_source_memberships WHERE workspace_id=%s ORDER BY source_id,video_id", (self.workspace_id,)),
            ("SELECT id,version,status FROM shiliu.assistant_wiki_pages WHERE workspace_id=%s AND principal_id=%s AND space_id=%s ORDER BY id", (self.workspace_id,self.principal_id,space_id)),
        ]
        values=[[list(row.values()) for row in conn.execute(query,params)] for query,params in queries]
        return hashlib.sha256(json.dumps(values,ensure_ascii=False,default=lambda v:v.isoformat()).encode()).hexdigest()

    def working_navigation_guard(self, conn, *, thread_id: str) -> str:
        import hashlib
        rows=conn.execute("SELECT r.id,r.working_state_json FROM shiliu.assistant_runs r JOIN shiliu.assistant_threads t "
                          "ON (t.workspace_id,t.id)=(r.workspace_id,r.thread_id) WHERE r.workspace_id=%s AND t.principal_id=%s "
                          "AND r.thread_id=%s ORDER BY r.insertion_seq",(self.workspace_id,self.principal_id,thread_id))
        values=[[r["id"],{key:(r["working_state_json"] or {}).get(key) for key in
                 ("task_focus","task_subset","knowledge_save","knowledge_bootstrap")}] for r in rows]
        return hashlib.sha256(json.dumps(values,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

    def save_working_context(self, run_id: str, *, epoch: int, expected_revision: int,
                             state: dict, projections: dict[str, dict], message_frontier: int,
                             memory_epoch: int, source_guard: str, scope_version: int,
                             task_subset: dict | None, dependency_refs: list[str],
                             navigation_guard: str, checkpoint_candidate: dict | None = None,
                             expected_note_version: int = 0) -> None:
        """Fenced installer; all representations/checkpoint/thread state commit together."""
        with self.db.connect() as conn:
            lock_workspace(conn, self.context)
            run = self._guard_run_completion(conn,run_id,epoch)
            thread = conn.execute("SELECT context_state_json,space_id FROM shiliu.assistant_threads "
                                  "WHERE workspace_id=%s AND id=%s FOR UPDATE",
                                  (self.workspace_id, run["thread_id"])).fetchone()
            prior = dict(thread["context_state_json"] or {})
            working = dict(run["working_state_json"] or {})
            scope = conn.execute("SELECT scope_version FROM shiliu.assistant_spaces WHERE workspace_id=%s "
                                 "AND principal_id=%s AND id=%s", (self.workspace_id, self.principal_id,
                                                                   thread["space_id"])).fetchone()
            frontier = conn.execute("SELECT COALESCE(MAX(seq),0) AS seq FROM shiliu.assistant_messages "
                                    "WHERE workspace_id=%s AND thread_id=%s",
                                    (self.workspace_id, run["thread_id"])).fetchone()["seq"]
            if (int(prior.get("revision") or 0) != expected_revision
                    or int(state.get("revision") or 0) != expected_revision + 1
                    or state.get("format_version") != 1 or not scope or int(scope["scope_version"]) != scope_version
                    or working.get("task_subset") != task_subset or int(frontier) != message_frontier
                    or self._memory_epoch(conn) != memory_epoch
                    or self.working_source_guard(conn, space_id=int(thread["space_id"])) != source_guard
                    or self.working_navigation_guard(conn, thread_id=str(run["thread_id"])) != navigation_guard
                    or not self._memory_refs_valid(conn, dependency_refs, space_id=int(thread["space_id"]))):
                raise AssistantConflict("working_context_changed")
            if checkpoint_candidate is not None:
                existing = conn.execute("SELECT id,note_version FROM shiliu.assistant_task_notes "
                                         "WHERE workspace_id=%s AND thread_id=%s AND task_segment=1 FOR UPDATE",
                                         (self.workspace_id, run["thread_id"])).fetchone()
                current_version = int(existing["note_version"] if existing else 0)
                note = checkpoint_candidate
                if (current_version != expected_note_version or int(note["note_version"]) != current_version + 1
                        or existing and existing["id"] != note["id"]):
                    raise AssistantConflict("working_checkpoint_changed")
                conn.execute(
                    "INSERT INTO shiliu.assistant_task_notes(workspace_id,id,thread_id,task_segment,note_version,"
                    "covered_until_message_seq,source_run_ids_json,dependencies_json,scope_version,memory_generation,"
                    "checkpoint_json,created_at,updated_at) VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s,clock_timestamp(),clock_timestamp()) "
                    "ON CONFLICT(thread_id,task_segment) DO UPDATE SET note_version=excluded.note_version,"
                    "covered_until_message_seq=excluded.covered_until_message_seq,source_run_ids_json=excluded.source_run_ids_json,"
                    "dependencies_json=excluded.dependencies_json,scope_version=excluded.scope_version,"
                    "memory_generation=excluded.memory_generation,checkpoint_json=excluded.checkpoint_json,status='active',"
                    "goal='',explicit_constraints_json='[]'::jsonb,searched_scope_and_material_refs_json='[]'::jsonb,"
                    "findings_json='[]'::jsonb,open_questions_json='[]'::jsonb,next_actions_json='[]'::jsonb,"
                    "updated_at=excluded.updated_at",
                    (self.workspace_id,note["id"],run["thread_id"],note["note_version"],note["covered_until_message_seq"],
                     Jsonb(note["source_run_ids"]),Jsonb(note["dependencies"]),scope_version,memory_epoch,
                     Jsonb(note["checkpoint"])))
            self.install_working_context(conn, thread_id=run["thread_id"], state=state, projections=projections)

    def _memory_refs_valid(self, conn, refs: list[str], *, space_id: int) -> bool:
        for ref in refs:
            if not str(ref).startswith("memory:"):
                continue
            parts = str(ref).split(":")
            if len(parts) != 3 or not parts[2].isdigit():
                return False
            row = conn.execute("SELECT status,version,scope_kind,scope_space_id,valid_from,expires_at "
                               "FROM shiliu.assistant_memories WHERE workspace_id=%s AND principal_id=%s AND id=%s",
                               (self.workspace_id,self.principal_id,parts[1])).fetchone()
            if row is None or row["status"] != "active" or int(row["version"]) != int(parts[2]):
                return False
            if row["scope_kind"] == "space" and int(row["scope_space_id"] or -1) != space_id:
                return False
            if not conn.execute("SELECT (%s::timestamptz IS NULL OR %s::timestamptz<=clock_timestamp()) "
                                "AND (%s::timestamptz IS NULL OR %s::timestamptz>clock_timestamp()) AS valid",
                                (row["valid_from"],row["valid_from"],row["expires_at"],row["expires_at"])).fetchone()["valid"]:
                return False
        return True

    def enqueue_job(self, conn, *, context=None, kind: str, dedupe_key: str, payload: dict,
                    not_before=None) -> str:
        from shiliu.storage.fences import CoordinationConflict
        context = context or self.context
        if context != self.context:
            raise AssistantConflict("job_scope_mismatch")
        job_id="ajob_"+uuid.uuid4().hex
        conn.execute("INSERT INTO shiliu.assistant_jobs(workspace_id,principal_id,id,kind,dedupe_key,status,"
                     "payload_json,not_before,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,'queued',%s,"
                     "coalesce(%s::timestamptz,clock_timestamp()),clock_timestamp(),clock_timestamp()) "
                     "ON CONFLICT(workspace_id,principal_id,dedupe_key) DO NOTHING",
                     (context.workspace_id,context.user_id,job_id,kind,dedupe_key,Jsonb(payload),not_before))
        row=conn.execute("SELECT id FROM shiliu.assistant_jobs WHERE workspace_id=%s AND principal_id=%s "
                         "AND dedupe_key=%s",(context.workspace_id,context.user_id,dedupe_key)).fetchone()
        if row is None: raise CoordinationConflict("job_enqueue_failed")
        return row["id"]

    def claim_job(self, *, owner, lease_seconds=120, allow_model_jobs=True,
                  allow_maintenance=True, kinds=None, scheduler_reason="normal"):
        return super().claim_job(owner=owner, lease_seconds=lease_seconds,
            allow_model_jobs=allow_model_jobs,allow_maintenance=allow_maintenance,kinds=kinds)

    @staticmethod
    def job_transition(conn, context, job_id: str, owner: str, epoch: int, **kwargs):
        from shiliu.storage.scheduler import job_transition
        return job_transition(conn, context, job_id, owner, epoch, **kwargs)

    @staticmethod
    def recover_job(conn, context, job_id: str, *, disposition: str):
        from shiliu.storage.scheduler import recover_job
        return recover_job(conn, context, job_id, disposition=disposition)

    def list_jobs(self, *, limit: int = 100, space_id: int | None = None):
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("invalid_job_limit")
        with self.db.connect(read_only=True) as conn:
            if space_id is None:
                rows=conn.execute("SELECT * FROM shiliu.assistant_jobs WHERE workspace_id=%s AND principal_id=%s "
                                  "ORDER BY created_at DESC,id DESC LIMIT %s",(self.workspace_id,self.principal_id,limit)).fetchall()
            else:
                joins,params=self._maintenance_job_scope(self.get_space(space_id,conn=conn))
                rows=conn.execute("SELECT j.*"+joins+" ORDER BY j.created_at DESC,j.id DESC LIMIT %s",(*params,limit)).fetchall()
        return [dict(id=r["id"],kind=r["kind"],dedupe_key=r["dedupe_key"],status=r["status"],
                     payload=r["payload_json"],attempt=int(r["attempt"]),not_before=r["not_before"].isoformat(),
                     proposal=r["proposal_json"],last_error_code=r["last_error_code"],
                     last_error_message=r["last_error_message"],lease_owner=r["lease_owner"],
                     lease_epoch=int(r["lease_epoch"])) for r in rows]

    def _maintenance_job_scope(self, space):
        joins=""" FROM shiliu.assistant_jobs j
            LEFT JOIN shiliu.assistant_threads t ON t.workspace_id=j.workspace_id AND t.id=j.payload_json->>'thread_id' AND t.principal_id=j.principal_id
            LEFT JOIN shiliu.assistant_memories m ON m.workspace_id=j.workspace_id AND m.id=j.payload_json->>'memory_id' AND m.principal_id=j.principal_id
            LEFT JOIN shiliu.assistant_maintenance_batches b ON b.workspace_id=j.workspace_id AND b.id=j.payload_json->>'maintenance_batch_id'
            WHERE j.workspace_id=%s AND j.principal_id=%s AND
            (coalesce((j.payload_json->>'space_id')::bigint,t.space_id,m.scope_space_id,b.space_id)=%s OR m.scope_kind='user'
             OR (j.payload_json->>'space_id' IS NULL AND t.id IS NULL AND m.id IS NULL AND b.id IS NULL AND
                 (j.payload_json->>'video_id')::bigint IN (
                     SELECT ms.video_id FROM shiliu.video_source_memberships ms JOIN shiliu.favorite_sources fs
                     ON (fs.workspace_id,fs.id)=(ms.workspace_id,ms.source_id) JOIN shiliu.videos v
                     ON (v.workspace_id,v.id)=(ms.workspace_id,ms.video_id)
                     WHERE ms.workspace_id=j.workspace_id AND ms.removed_at IS NULL AND fs.status='active'
                     AND NOT v.is_ignored AND v.archived_at IS NULL AND (%s OR ms.source_id=ANY(%s))
                     AND (%s OR ms.video_id=ANY(%s)))))"""
        return joins,(self.workspace_id,self.principal_id,space["id"],space["all_active"],space["source_ids"],not space["video_ids"],space["video_ids"])

    def maintenance_activity(self, space_id, *, limit=20):
        from shiliu.storage.dto import iso_time
        limit=max(1,min(int(limit),50));items=[]
        with self.db.connect(read_only=True) as conn:
            space=self.get_space(space_id,conn=conn)
            memories=conn.execute("SELECT m.*,ch.operation,ch.created_at AS changed_at,"
                "(m.status='active' AND (m.expires_at IS NULL OR m.expires_at>clock_timestamp()) AND "
                "(m.valid_from IS NULL OR m.valid_from<=clock_timestamp())) AS valid "
                "FROM shiliu.assistant_memory_changes ch JOIN shiliu.assistant_memories m "
                "ON (m.workspace_id,m.id)=(ch.workspace_id,ch.memory_id) WHERE m.workspace_id=%s AND m.principal_id=%s "
                "AND ch.actor='assistant' AND ch.version=m.version AND (m.scope_kind='user' OR m.scope_space_id=%s) "
                "ORDER BY ch.created_at DESC,ch.id DESC LIMIT %s",(self.workspace_id,self.principal_id,space_id,limit)).fetchall()
            for row in memories:
                items.append(dict(id=f"memory:{row['id']}:{row['version']}",kind="memory",time=iso_time(row["changed_at"]),
                    title=row["text"] if row["valid"] else "记忆已失效或待核对",
                    result=("新增记忆" if row["operation"]=="created" else "更新记忆") if row["valid"] else "当前不用于回答",
                    scope="所有对话" if row["scope_kind"]=="user" else space["name"],**({"memory_id":row["id"]} if row["valid"] else {})))
            changes=conn.execute("SELECT p.id,p.title,p.status,ch.version,ch.operation,ch.created_at FROM shiliu.assistant_wiki_changes ch "
                "JOIN shiliu.assistant_wiki_pages p ON (p.workspace_id,p.id)=(ch.workspace_id,ch.page_id) WHERE p.workspace_id=%s "
                "AND p.principal_id=%s AND p.space_id=%s ORDER BY ch.created_at DESC,ch.id DESC LIMIT %s",
                (self.workspace_id,self.principal_id,space_id,limit)).fetchall()
            changed={(r["id"],r["version"]) for r in changes}
            for row in changes:
                items.append(dict(id=f"wiki:{row['id']}:{row['version']}",kind="wiki",time=iso_time(row["created_at"]),title=row["title"],
                    result={"created":"新增知识页","source_integrated":"增补知识","source_amended":"修订知识","source_associated":"关联来源"}.get(row["operation"],"知识页有变更"),
                    scope=space["name"],**({"page_id":row["id"]} if row["status"]=="active" else {})))
            joins,params=self._maintenance_job_scope(space)
            counts={r["status"]:r["n"] for r in conn.execute("SELECT j.status,count(*) AS n"+joins+" GROUP BY j.status",params)}
            jobs=conn.execute("SELECT j.*,t.id AS thread_id,m.scope_kind AS memory_scope,b.space_id AS batch_space"+joins+
                             " ORDER BY (j.status<>'completed') DESC,j.updated_at DESC,j.id DESC LIMIT %s",(*params,limit)).fetchall()
            for row in jobs:
                payload=row["payload_json"] or {};result=row["proposal_json"] or {}
                if row["status"]=="completed" and not result.get("no_change") and not result.get("superseded"):
                    if row["kind"]!="wiki_integrate" or (result.get("page_id"),result.get("version")) in changed:continue
                page=conn.execute("SELECT title,status FROM shiliu.assistant_wiki_pages WHERE workspace_id=%s AND principal_id=%s AND space_id=%s AND id=%s",
                    (self.workspace_id,self.principal_id,space_id,result.get("page_id"))).fetchone() if result.get("page_id") else None
                video=conn.execute("SELECT title FROM shiliu.videos WHERE workspace_id=%s AND id=%s",
                                   (self.workspace_id,payload.get("video_id"))).fetchone() if payload.get("video_id") else None
                labels={"memory_extract":"记忆提炼","memory_index":"记忆索引","memory_purge":"记忆清理","source_reconcile":"来源检查","source_extract":"材料整理","wiki_integrate":"知识整理"}
                state={"queued":"等待执行","running":"执行中","retry_wait":"等待重试","budget_wait":"等待额度","blocked":"需要处理","failed":"处理失败","completed":"处理完成"}.get(row["status"],row["status"])
                if row["status"]=="completed":state="已跳过" if result.get("superseded") else "无需变化" if result.get("no_change") else "处理完成"
                shared=not (payload.get("space_id") or row["thread_id"] or row["memory_scope"] or row["batch_space"])
                detail={"wiki_manual_conflict":"已有人工修改，请查看知识页","provider_auth":"模型凭据需要检查","api_key_missing":"未配置模型凭据", "memory_backend_unavailable":"记忆索引暂不可用","maintenance_budget_wait":"本次整理额度已用完","background_budget_wait":"等待下一个每日额度"}.get(row["last_error_code"],"")
                items.append(dict(id=row["id"],kind="job",time=iso_time(row["updated_at"]),title=page["title"] if page else video["title"] if video else labels.get(row["kind"],"后台处理"),
                    result=state,detail=detail if row["status"] in {"blocked","failed","retry_wait","budget_wait"} else "",
                    scope="共享来源处理" if shared else "所有对话" if row["memory_scope"]=="user" else space["name"],
                    **({"page_id":result["page_id"]} if page and page["status"]=="active" else {}),**({"thread_id":row["thread_id"]} if row["thread_id"] else {})))
        return {"items":sorted(items,key=lambda item:(item["time"],item["id"]),reverse=True)[:limit],"counts":counts}

    def reserve_model_dispatch(self, dispatch_id: str, *, lane: str, request_limit: int,
                               request_hash: str, requests: int = 1, run_id: str | None = None,
                               job_id: str | None = None):
        from shiliu.storage.budget import reserve_dispatch
        with self.db.connect() as conn:
            row=reserve_dispatch(conn,self.context,dispatch_id,lane=lane,request_limit=request_limit,
                                 request_hash=request_hash,requests=requests,run_id=run_id,job_id=job_id)
        return dict(row)

    def settle_model_dispatch(self, dispatch_id: str, *, usage: dict | None):
        from shiliu.storage.budget import settle_dispatch
        with self.db.connect() as conn:
            row=settle_dispatch(conn,self.context,dispatch_id,usage=usage)
        return dict(row)

    def mark_dispatch_unknown(self, dispatch_id: str):
        from shiliu.storage.budget import settle_dispatch
        with self.db.connect() as conn:
            row=settle_dispatch(conn,self.context,dispatch_id,usage=None)
        return dict(row)

    def reserve_model_request(self, *, lane: str, request_limit: int, run_id: str,
                              request_hash: str) -> dict[str, Any]:
        dispatch_id="dispatch_"+uuid.uuid4().hex
        row=self.reserve_model_dispatch(dispatch_id,lane=lane,request_limit=request_limit,
                                        request_hash=request_hash,run_id=run_id)
        return {**row,"dispatch_id":dispatch_id,"budget_date":row["budget_day"].isoformat()}

    def record_model_usage(self, *, dispatch_id: str, usage: dict[str, Any] | None,
                           outcome: str, latency_ms: float, **_ignored):
        # The durable receipt is the billing identity. Outcome/latency are
        # diagnostics and do not mutate provider usage or invent zero usage.
        return self.settle_model_dispatch(dispatch_id,usage=usage)

    def release_model_request(self, dispatch_id: str):
        from shiliu.storage.budget import release_dispatch
        with self.db.connect() as conn:
            row=release_dispatch(conn,self.context,dispatch_id)
        return dict(row)

    def current_memory_epoch(self) -> int:
        with self.db.connect(read_only=True) as conn:
            return self._memory_epoch(conn)

    def save_answer_draft(self, run_id, *, epoch, text, allow_finish=False, call_id=None, start_call=False):
        with self.db.connect() as conn:
            lock_workspace(conn,self.context)
            try:run=self._guard_run_completion(conn,run_id,epoch)
            except AssistantConflict:return False
            working=dict(run["working_state_json"] or {})
            if not start_call and working.get("answer_draft_call_id")!=call_id:return False
            if start_call:working["answer_draft_call_id"]=call_id
            thread=conn.execute("SELECT space_id FROM shiliu.assistant_threads WHERE workspace_id=%s AND id=%s",
                                (self.workspace_id,run["thread_id"])).fetchone()
            valid=(not working.get("finish_requested") or allow_finish) and self._memory_refs_valid(conn,
                (working.get("context_observation") or {}).get("dependency_refs") or [],space_id=int(thread["space_id"]))
            working["answer_draft"]={"text":text if valid else "","epoch":epoch,"status":"generating" if valid else "invalidated"}
            conn.execute("UPDATE shiliu.assistant_runs SET working_state_json=%s WHERE workspace_id=%s AND id=%s",
                         (Jsonb(working),self.workspace_id,run_id))
            return valid

    def confirm_model_delivery(self, run_id, *, epoch, spans, materials=None, message_ids=None, context_revision=None):
        if not spans and not materials and not message_ids:return
        with self.db.connect() as conn:
            run=self._guard_run_completion(conn,run_id,epoch)
            working=dict(run["working_state_json"] or {})
            if message_ids:
                thread=conn.execute("SELECT context_state_json FROM shiliu.assistant_threads WHERE workspace_id=%s AND id=%s",
                                    (self.workspace_id,run["thread_id"])).fetchone()
                state=dict(thread["context_state_json"] or {})
                active={e["message_id"] for e in state.get("entries") or [] if e.get("kind")=="message"}
                if context_revision!=state.get("revision") or not set(message_ids).issubset(active):
                    raise AssistantConflict("working_delivery_changed")
                spans,materials=[],[]
                for message_id in dict.fromkeys(message_ids):
                    row=conn.execute("SELECT provider_payload_json FROM shiliu.assistant_messages WHERE workspace_id=%s AND thread_id=%s AND id=%s FOR UPDATE",
                                     (self.workspace_id,run["thread_id"],message_id)).fetchone()
                    payload=dict(row["provider_payload_json"] or {})
                    projection=payload.get("model_projection")
                    if not projection:raise AssistantConflict("working_delivery_projection_missing")
                    projection["delivery"]={"confirmed":True,"run_id":run_id,"revision":context_revision}
                    spans.extend(projection.get("read_spans") or []);materials.extend(projection.get("materials") or [])
                    conn.execute("UPDATE shiliu.assistant_messages SET provider_payload_json=%s WHERE workspace_id=%s AND id=%s",
                                 (Jsonb(payload),self.workspace_id,message_id))
                for entry in state.get("entries") or []:
                    if entry.get("kind")=="block":
                        materials.extend(entry.get("materials") or [])
                        entry["delivery"]={"confirmed":True,"run_id":run_id,"revision":context_revision}
                conn.execute("UPDATE shiliu.assistant_threads SET context_state_json=%s WHERE workspace_id=%s AND id=%s",
                             (Jsonb(state),self.workspace_id,run["thread_id"]))
            for key,values,limit in (("model_delivered_read_spans",spans,200),("model_delivered_materials",materials or [],160)):
                existing=list(working.get(key) or [])
                seen={json.dumps(v,sort_keys=True) for v in existing}
                for value in values:
                    encoded=json.dumps(value,sort_keys=True)
                    if encoded not in seen:existing.append(value);seen.add(encoded)
                if key=="model_delivered_materials":
                    working["model_delivered_materials_truncated"]=bool(working.get("model_delivered_materials_truncated") or len(existing)>limit)
                working[key]=existing[-limit:]
            conn.execute("UPDATE shiliu.assistant_runs SET working_state_json=%s WHERE workspace_id=%s AND id=%s",
                         (Jsonb(working),self.workspace_id,run_id))

    def record_compaction(self, run_id, *, epoch, usage, input_characters, latency_ms):
        with self.db.connect() as conn:
            run=self._guard_run_completion(conn,run_id,epoch)
            working=dict(run["working_state_json"] or {})
            observation=dict(working.get("compaction_observation") or {})
            for key,amount in (("calls",1),("input_characters",input_characters),("latency_ms",latency_ms),("usage_known_calls",int(bool(usage)))):
                observation[key]=observation.get(key,0)+amount
            totals=dict(observation.get("usage") or {})
            for key,value in usage.items():
                if type(value) in {int,float}:totals[key]=totals.get(key,0)+value
            observation["usage"]=totals;working["compaction_observation"]=observation
            conn.execute("UPDATE shiliu.assistant_runs SET working_state_json=%s WHERE workspace_id=%s AND id=%s",
                         (Jsonb(working),self.workspace_id,run_id))

    def record_late_tool_completion(self, run_id, ordinal):
        with self.db.connect() as conn:
            lock_thread_run(conn,self.context,run_id)
            conn.execute("UPDATE shiliu.assistant_runs SET tool_count=greatest(tool_count,%s) WHERE workspace_id=%s AND id=%s AND status='cancelled'",
                         (ordinal,self.workspace_id,run_id))

    def mark_user_activity(self, conn=None) -> None:
        with self.db.connect(conn) as active:
            active.execute("INSERT INTO shiliu.assistant_runtime_state(workspace_id,principal_id,key,value,updated_at) "
                           "VALUES(%s,%s,'last_user_activity_at',clock_timestamp()::text,clock_timestamp()) "
                           "ON CONFLICT(workspace_id,principal_id,key) DO UPDATE SET "
                           "value=excluded.value,updated_at=excluded.updated_at",
                           (self.workspace_id,self.principal_id))

    def claim_next_run(self, *, created_after: str | None = None) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            thread = conn.execute("SELECT t.id,t.space_id FROM shiliu.assistant_threads t "
                                  "JOIN shiliu.assistant_spaces s ON (s.workspace_id,s.id)=(t.workspace_id,t.space_id) "
                                  "JOIN shiliu.assistant_runs r ON r.workspace_id=t.workspace_id AND r.thread_id=t.id "
                                  "WHERE t.workspace_id=%s AND t.principal_id=%s AND s.enabled AND r.status='queued' "
                                  "AND (%s::timestamptz IS NULL OR r.created_at >= %s::timestamptz) "
                                  "ORDER BY r.created_at,r.id LIMIT 1 FOR UPDATE OF t SKIP LOCKED",
                                  (self.workspace_id,self.principal_id,created_after,created_after)).fetchone()
            if thread is None:
                return None
            run = conn.execute("SELECT * FROM shiliu.assistant_runs WHERE workspace_id=%s AND thread_id=%s "
                               "AND status='queued' AND (%s::timestamptz IS NULL OR created_at >= %s::timestamptz) "
                               "ORDER BY created_at,id LIMIT 1 FOR UPDATE",
                               (self.workspace_id,thread["id"],created_after,created_after)).fetchone()
            if run is None:
                return None
            working=dict(run["working_state_json"] or {})
            working.setdefault("segment_started_at",_now().isoformat())
            budget=working.get("execution_budget")
            if budget and "paused_remaining" in budget:
                from datetime import timedelta
                budget["deadline_at"]=(_now()+timedelta(seconds=budget.pop("paused_remaining"))).isoformat()
            updated=conn.execute("UPDATE shiliu.assistant_runs SET status='running',started_at=coalesce(started_at,%s),"
                                 "working_state_json=%s,updated_at=%s WHERE workspace_id=%s AND id=%s AND status='queued' "
                                 "RETURNING *",(_now(),Jsonb(working),_now(),self.workspace_id,run["id"])).fetchone()
            if updated is None:
                return None
            self._append_event(conn,run["id"],"run_started",{})
            return assistant_run_dto(updated,current=True)

    def has_active_runs(self) -> bool:
        with self.db.connect(read_only=True) as conn:
            return conn.execute("SELECT 1 FROM shiliu.assistant_runs r JOIN shiliu.assistant_threads t "
                                "ON (t.workspace_id,t.id)=(r.workspace_id,r.thread_id) WHERE r.workspace_id=%s "
                                "AND t.principal_id=%s AND r.status IN ('queued','running') LIMIT 1",
                                (self.workspace_id,self.principal_id)).fetchone() is not None

    def maintenance_idle(self, *, seconds=180, startup_at=None, connection=None):
        with self.db.connect(connection, read_only=connection is None) as conn:
            active=conn.execute("SELECT 1 FROM shiliu.assistant_runs r JOIN shiliu.assistant_threads t "
                "ON (t.workspace_id,t.id)=(r.workspace_id,r.thread_id) WHERE r.workspace_id=%s AND t.principal_id=%s "
                "AND r.status IN ('queued','running') LIMIT 1",(self.workspace_id,self.principal_id)).fetchone()
            if active:return False
            return conn.execute("SELECT clock_timestamp()-greatest(%s::timestamptz, "
                "(SELECT max(stamp) FROM ("
                "SELECT updated_at AS stamp FROM shiliu.assistant_runtime_state WHERE workspace_id=%s AND principal_id=%s AND key='last_user_activity_at' "
                "UNION ALL SELECT r.completed_at FROM shiliu.assistant_runs r JOIN shiliu.assistant_threads t ON (t.workspace_id,t.id)=(r.workspace_id,r.thread_id) "
                "WHERE t.workspace_id=%s AND t.principal_id=%s UNION ALL SELECT m.created_at FROM shiliu.assistant_messages m "
                "JOIN shiliu.assistant_threads t ON (t.workspace_id,t.id)=(m.workspace_id,m.thread_id) WHERE t.workspace_id=%s AND t.principal_id=%s AND m.role='user'"
                ") activity)) >= %s*interval '1 second' AS idle",
                (startup_at or '1970-01-01T00:00:00+00:00',self.workspace_id,self.principal_id,self.workspace_id,self.principal_id,
                 self.workspace_id,self.principal_id,seconds)).fetchone()["idle"]

    def heartbeat_job(self, job_id, *, owner, lease_epoch, lease_seconds=120):
        try:
            with self.db.connect() as conn:
                self.job_transition(conn,self.context,job_id,owner,lease_epoch,action="heartbeat",lease_seconds=lease_seconds)
            return True
        except CoordinationConflict:
            return False

    def defer_job_for_activity(self, job):
        return self.defer_maintenance_job(job,reason="activity")

    def defer_job_for_budget(self, job, *, message):
        return self.defer_maintenance_job(job,reason="daily_budget")

    def defer_job_for_batch_budget(self, job, *, message):
        return self.defer_maintenance_job(job,reason="batch_budget")

    def fail_job(self, job, *, code, message, blocked=False):
        with self.db.connect() as conn:
            self.job_transition(conn,self.context,job["id"],job["lease_owner"],job["lease_epoch"],action="fail")
            conn.execute("UPDATE shiliu.assistant_jobs SET status=CASE WHEN %s THEN 'blocked' ELSE status END,"
                "last_error_code=%s,last_error_message=%s WHERE workspace_id=%s AND principal_id=%s AND id=%s",
                (blocked,code,message[:1000],self.workspace_id,self.principal_id,job["id"]))
            self.notify_job_issue(conn, job["id"])

    def recover_expired_jobs(self):
        with self.db.connect() as conn:
            rows=conn.execute("SELECT id,kind,proposal_json,attempt FROM shiliu.assistant_jobs WHERE workspace_id=%s "
                "AND principal_id=%s AND status='running' AND lease_until<=clock_timestamp()",
                (self.workspace_id,self.principal_id)).fetchall()
            count=0
            for row in rows:
                disposition=("exhausted" if row["attempt"]>=3 else "staged" if row["proposal_json"] is not None
                    else "replay_safe" if row["kind"] in {"memory_index","memory_purge"} else "unknown")
                recovered=self.recover_job(conn,self.context,row["id"],disposition=disposition)
                count+=bool(recovered)
                if recovered and disposition=="unknown":
                    conn.execute("UPDATE shiliu.assistant_jobs SET last_error_code='external_side_effect_unknown' "
                                 "WHERE workspace_id=%s AND principal_id=%s AND id=%s",
                                 (self.workspace_id,self.principal_id,row["id"]))
                if recovered:
                    self.notify_job_issue(conn, row["id"])
            return count

    def retry_job(self, job_id):
        with self.db.connect() as conn:
            # Match scheduler's lane -> Job order, even for manually resumed work.
            conn.execute("SELECT lane FROM shiliu.scheduler_lanes WHERE workspace_id=%s AND principal_id=%s "
                         "AND lane='model-maintenance' FOR UPDATE",(self.workspace_id,self.principal_id))
            row=conn.execute("SELECT * FROM shiliu.assistant_jobs WHERE workspace_id=%s AND principal_id=%s AND id=%s FOR UPDATE",
                             (self.workspace_id,self.principal_id,job_id)).fetchone()
            if row is None:raise KeyError(job_id)
            if row["status"] not in {"blocked","failed","retry_wait","budget_wait"}:raise AssistantConflict("job_not_retryable")
            if row["last_error_code"]=="external_side_effect_unknown":raise AssistantConflict("job_outcome_resolution_required")
            payload=dict(row["payload_json"] or {})
            continued=False
            if row["status"]=="budget_wait" and row["last_error_code"]=="maintenance_budget_wait":
                prior=conn.execute("SELECT b.* FROM shiliu.assistant_maintenance_batches b JOIN shiliu.assistant_spaces s "
                    "ON (s.workspace_id,s.id)=(b.workspace_id,b.space_id) WHERE b.workspace_id=%s AND s.principal_id=%s AND b.id=%s",
                    (self.workspace_id,self.principal_id,payload.get("maintenance_batch_id"))).fetchone()
                if prior is None:raise AssistantConflict("maintenance_batch_missing")
                batch_id="amb_"+uuid.uuid4().hex
                conn.execute("INSERT INTO shiliu.assistant_maintenance_batches(workspace_id,id,space_id,source_limit,model_limit,calls_used,created_at) "
                    "VALUES(%s,%s,%s,1,%s,0,clock_timestamp())",(self.workspace_id,batch_id,prior["space_id"],prior["model_limit"]))
                payload["maintenance_batch_id"]=batch_id;continued=True
            row=conn.execute("UPDATE shiliu.assistant_jobs SET status='queued',not_before=clock_timestamp(),payload_json=%s,"
                "lease_owner=NULL,lease_until=NULL,last_error_code=NULL,last_error_message=NULL,completed_at=NULL,updated_at=clock_timestamp() "
                "WHERE workspace_id=%s AND principal_id=%s AND id=%s RETURNING *",(Jsonb(payload),self.workspace_id,self.principal_id,job_id)).fetchone()
            if continued:
                conn.execute("INSERT INTO shiliu.assistant_scheduler_events(workspace_id,principal_id,job_id,event_type,reason,created_at) "
                    "VALUES(%s,%s,%s,'continued','explicit_new_budget_segment',clock_timestamp())",(self.workspace_id,self.principal_id,job_id))
            return self.job_dto(row)

    def recover_interrupted_runs(self) -> int:
        """On process owner loss, preserve run data/epochs and mark foreground runs resumable."""
        with self.db.connect() as conn:
            rows=conn.execute("SELECT r.id FROM shiliu.assistant_runs r JOIN shiliu.assistant_threads t "
                              "ON (t.workspace_id,t.id)=(r.workspace_id,r.thread_id) WHERE r.workspace_id=%s "
                              "AND t.principal_id=%s AND r.status='running' ORDER BY t.id,r.insertion_seq",
                              (self.workspace_id,self.principal_id)).fetchall()
            count=0
            for row in rows:
                run=lock_thread_run(conn,self.context,row["id"])
                if run["status"]!="running":continue
                conn.execute("UPDATE shiliu.assistant_runs SET status='interrupted',updated_at=clock_timestamp(),"
                             "last_error_code='service_restarted',last_error_message='服务重启后需要用户继续' "
                             "WHERE workspace_id=%s AND id=%s AND status='running'",
                             (self.workspace_id,row["id"]))
                self._append_event(conn,row["id"],"run_interrupted",{})
                count+=1
            return count

    def try_complete_run(self, run_id: str, *, epoch: int, answer: str, usage: dict[str, Any],
                         expected_scope_version: int, expected_observed_memory_epoch: int,
                         dependency_refs: list[str], expected_task_note_version: int | None,
                         dependency_validator=None, completion_origin="model") -> str:
        """Complete only after root/run fence and current scope/memory validation."""
        with self.db.connect() as conn:
            lock_workspace(conn, self.context)
            try:
                run=self._guard_run_completion(conn,run_id,epoch)
            except AssistantConflict:
                return "run_fenced"
            thread=conn.execute("SELECT t.space_id,t.id FROM shiliu.assistant_threads t "
                                "WHERE t.workspace_id=%s AND t.id=%s FOR UPDATE",
                                (self.workspace_id,run["thread_id"])).fetchone()
            space=conn.execute("SELECT scope_version FROM shiliu.assistant_spaces WHERE workspace_id=%s "
                               "AND principal_id=%s AND id=%s",(self.workspace_id,self.principal_id,
                                                                 thread["space_id"])).fetchone()
            if space is None or int(space["scope_version"])!=int(expected_scope_version):
                return "scope_changed"
            memory_epoch=self._memory_epoch(conn)
            if memory_epoch!=int(expected_observed_memory_epoch):
                return "memory_changed"
            if not self._memory_refs_valid(conn,dependency_refs,space_id=int(thread["space_id"])):
                return "memory_dependency_changed"
            if dependency_validator and not dependency_validator(dependency_refs,int(thread["space_id"]),
                                                                  str(thread["id"]),int(space["scope_version"])):
                return "dependency_changed"
            if expected_task_note_version is not None:
                note=conn.execute("SELECT note_version,status FROM shiliu.assistant_task_notes WHERE workspace_id=%s "
                                  "AND thread_id=%s AND task_segment=1",(self.workspace_id,thread["id"])).fetchone()
                if note is None or note["status"]!="active" or int(note["note_version"])!=expected_task_note_version:
                    return "task_note_changed"
            state=dict(run["working_state_json"] or {})
            budget=state.get("execution_budget")
            if budget and not conn.execute("SELECT %s::timestamptz>clock_timestamp() AS valid",
                                           (budget["deadline_at"],)).fetchone()["valid"]:
                return "execution_budget_exhausted"
            actual_usage=dict(run["usage_json"] or {}) if budget else dict(usage)
            late=state.get("late_model_usage") or {}
            if not state.get("usage_includes_late"):
                for key,value in late.items():
                    if isinstance(value,(int,float)) and not isinstance(value,bool):
                        actual_usage[key]=actual_usage.get(key,0)+value
            message_id="amsg_"+uuid.uuid4().hex
            seq=conn.execute("SELECT COALESCE(MAX(seq),0)+1 AS seq FROM shiliu.assistant_messages "
                             "WHERE workspace_id=%s AND thread_id=%s",(self.workspace_id,thread["id"])).fetchone()["seq"]
            conn.execute("INSERT INTO shiliu.assistant_messages(workspace_id,id,thread_id,run_id,seq,role,content,"
                         "provider_payload_json,created_at) VALUES(%s,%s,%s,%s,%s,'assistant',%s,%s,clock_timestamp())",
                         (self.workspace_id,message_id,thread["id"],run_id,seq,answer,
                          Jsonb({"origin":completion_origin,"dependency_refs":dependency_refs,
                                 "memory_observed_epoch":memory_epoch,"task_note_version":expected_task_note_version})))
            conn.execute("UPDATE shiliu.assistant_runs SET status='completed',usage_json=%s,observed_memory_epoch=%s,"
                         "memory_epoch=%s,updated_at=clock_timestamp(),completed_at=clock_timestamp() "
                         "WHERE workspace_id=%s AND id=%s AND status='running' AND run_epoch=%s AND NOT cancel_requested",
                         (Jsonb(actual_usage),memory_epoch,memory_epoch,self.workspace_id,run_id,epoch))
            conn.execute("UPDATE shiliu.assistant_threads SET updated_at=clock_timestamp() WHERE workspace_id=%s AND id=%s",
                         (self.workspace_id,thread["id"]))
            self._append_event(conn,run_id,"run_completed",{"message_id":message_id})
            users=conn.execute("SELECT id,content FROM shiliu.assistant_messages WHERE workspace_id=%s AND run_id=%s "
                               "AND role='user' ORDER BY seq",(self.workspace_id,run_id)).fetchall()
            narrow=False
            if len(users)==1:
                text=users[0]["content"].strip()
                if len(text)<=160 and any(word in text for word in ("只需","只要")) and any(word in text for word in ("找回","有没有","哪条收藏","哪个视频")) and not any(word in text for word in ("记住","我决定","我认为","我觉得","我希望","以后","今后")):
                    names={r["name"] for r in conn.execute("SELECT name FROM shiliu.assistant_tool_calls WHERE workspace_id=%s AND run_id=%s",
                                                          (self.workspace_id,run_id))}
                    narrow=bool(names) and names<={"search_knowledge","collection_search","collection_read"}
            if not narrow:
                self._enqueue_memory_extraction(conn,run=run,user_messages=users,admission=state.get("auto_memory_admission") or {})
            return "completed"

    def _enqueue_memory_extraction(self, conn, *, run, user_messages, admission):
        message_ids=[r["id"] for r in user_messages]
        if not message_ids or admission.get("enabled") is not True:return None
        thread_id=run["thread_id"];epoch=int(run["extraction_memory_epoch"]);generation=int(admission.get("generation",-1))
        rows=conn.execute("SELECT id,payload_json FROM shiliu.assistant_jobs WHERE workspace_id=%s AND principal_id=%s "
            "AND kind='memory_extract' AND status='queued' AND attempt=0 AND proposal_json IS NULL ORDER BY created_at DESC LIMIT 30 FOR UPDATE",
            (self.workspace_id,self.principal_id)).fetchall()
        for row in rows:
            payload=dict(row["payload_json"] or {})
            if (payload.get("thread_id")!=thread_id or int(payload.get("memory_epoch",-1))!=epoch or
                int(payload.get("auto_memory_generation",-1))!=generation or payload.get("auto_enabled_at_enqueue") is not True):continue
            merged=list(dict.fromkeys([*payload.get("message_ids",[]),*message_ids]))
            payload["message_ids"]=merged;payload["message_cursor"]=merged[-1]
            payload["run_ids"]=list(dict.fromkeys([*payload.get("run_ids",[payload.get("run_id")]),run["id"]]))
            conn.execute("UPDATE shiliu.assistant_jobs SET payload_json=%s,updated_at=clock_timestamp() WHERE workspace_id=%s AND id=%s",
                         (Jsonb(payload),self.workspace_id,row["id"]))
            return row["id"]
        return self.enqueue_job(conn,kind="memory_extract",dedupe_key=f"memory_extract:{run['id']}:v1",payload={
            "run_id":run["id"],"run_ids":[run["id"]],"thread_id":thread_id,"message_ids":message_ids,
            "message_cursor":message_ids[-1],"memory_epoch":epoch,"policy_version":"v1","auto_enabled_at_enqueue":True,
            "auto_memory_generation":generation})

    def run_context(self, run_id: str) -> dict[str, Any]:
        run=self.get_run(run_id)
        thread=self.get_thread(run["thread_id"])
        space=self.task_space(thread["id"])
        versions={r["id"]:int(r["working_state"].get("scope_version",1)) for r in thread["runs"]}
        thread["messages"]=[m for m in thread["messages"] if m["run_id"] is not None and
                            versions.get(m["run_id"])==int(space["scope_version"])]
        subset=run["working_state"].get("task_subset")
        if subset:
            same_runs={r["id"] for r in thread["runs"] if r["working_state"].get("task_subset")==subset}
            allowed=set(space["video_ids"]);accepted=set()
            for message in thread["messages"]:
                if message["role"]!="tool":continue
                result=json.loads(message["content"] or "{}")
                refs=result.get("source_refs") or []
                if refs and all(str(ref).startswith("video:") and int(str(ref).split(":")[1]) in allowed for ref in refs):
                    accepted.add((message["provider_payload_json"] or {}).get("tool_call_id"))
            projected=[]
            for message in thread["messages"]:
                if message["role"]=="user" or message["run_id"] in same_runs:
                    projected.append(message);continue
                payload=message["provider_payload_json"] or {}
                if message["role"]=="tool" and payload.get("tool_call_id") in accepted:projected.append(message)
                elif message["role"]=="assistant" and payload.get("tool_calls"):
                    calls=[c for c in payload["tool_calls"] if c["id"] in accepted]
                    if calls:projected.append({**message,"content":"","provider_payload_json":{**payload,"tool_calls":calls}})
            thread["messages"]=projected
            thread["runs"]=[{**r,"working_state":r["working_state"] if r["id"] in same_runs else {}} for r in thread["runs"]]
            thread.pop("task_note",None);thread.pop("task_focus",None)
        bootstrap=[]
        for prior in thread["runs"]:
            marker=prior["working_state"].get("knowledge_bootstrap") or {}
            if marker.get("status")!="completed":continue
            try:
                resolved=self.resolve_run_result(marker["result_ref"],current_thread_id=thread["id"],current_scope_version=space["scope_version"])
                if not resolved["result"].get("coverage",{}).get("discarded"):bootstrap.append(resolved)
            except (KeyError,ValueError):continue
        return {"run":run,"thread":thread,"space":space,
                "bootstrap_results":bootstrap,
                "messages":[m for m in thread["messages"] if m["run_id"]==run_id]}

    def working_run_context(self, run_id: str) -> dict[str, Any]:
        run=self.get_run(run_id)
        thread=self.get_thread(run["thread_id"],include_internal=True)
        return {"run":run,"thread":thread,"space":self.task_space(thread["id"])}

    def knowledge_save_request(self, run_id: str) -> dict:
        run=self.get_run(run_id)
        binding=run["working_state"].get("knowledge_save")
        if binding:return dict(binding)
        with self.db.connect(read_only=True) as conn:
            message=conn.execute("SELECT id,content FROM shiliu.assistant_messages WHERE workspace_id=%s AND run_id=%s "
                                 "AND role='user' ORDER BY seq DESC LIMIT 1",(self.workspace_id,run_id)).fetchone()
        if message is None:raise AssistantConflict("task_user_message_missing")
        return {"source_message_id":message["id"],"request_key":"save-message:"+message["id"],"scope_text":message["content"]}

    def knowledge_message(self, message_id, *, thread_id, allow_operation_receipt=False, conn=None):
        row=super().knowledge_message(message_id,thread_id=thread_id,
            allow_operation_receipt=allow_operation_receipt,conn=conn)
        return row_dto(row,timestamps=("created_at",))

    def set_task_subset(self, run_id, *, epoch, video_ids, source_message_id=None, basis_quote=None):
        if not video_ids:raise ValueError("empty_task_subset")
        with self.db.connect() as conn:
            run=self.guard_tool_operation(conn,expected_run_id=run_id,expected_epoch=epoch)
            working=dict(run["working_state_json"] or {})
            working["task_subset"]={"video_ids":sorted(set(video_ids)),**({"source_message_id":source_message_id,"basis_quote":basis_quote} if source_message_id else {})}
            working.pop("task_focus",None);working.pop("answer_draft",None)
            conn.execute("UPDATE shiliu.assistant_runs SET working_state_json=%s WHERE workspace_id=%s AND id=%s",
                         (Jsonb(working),self.workspace_id,run_id))
            self.mark_user_activity(conn)
            self._append_event(conn,run_id,"task_scope_changed",working["task_subset"])

    def save_task_focus(self, run_id, *, epoch, focus):
        focus={key:([str(item).strip() for item in value] if isinstance(value,list) else value.strip() if isinstance(value,str) else value)
               for key,value in focus.items()}
        focus["selected_source_refs"]=sorted(set(focus.get("selected_source_refs") or []))
        with self.db.connect() as conn:
            lock_workspace(conn,self.context)
            run=self.guard_tool_operation(conn,expected_run_id=run_id,expected_epoch=epoch)
            user=conn.execute("SELECT id,content,seq FROM shiliu.assistant_messages WHERE workspace_id=%s AND run_id=%s "
                              "AND role='user' ORDER BY seq DESC LIMIT 1",(self.workspace_id,run_id)).fetchone()
            if user is None:raise AssistantConflict("task_user_message_missing")
            state=dict(run["working_state_json"] or {})
            observed=state.get("context_observation") or {}
            inherited=[str(v) for v in observed.get("visible_user_message_ids") or []]
            dependencies=[str(v) for v in observed.get("dependency_refs") or []]
            space=conn.execute("SELECT space_id FROM shiliu.assistant_threads WHERE workspace_id=%s AND id=%s",
                               (self.workspace_id,run["thread_id"])).fetchone()
            memories=conn.execute("SELECT id,version,source_message_ids_json FROM shiliu.assistant_memories WHERE workspace_id=%s "
                "AND principal_id=%s AND status='active' AND (scope_kind='user' OR (scope_kind='space' AND scope_space_id=%s))",
                (self.workspace_id,self.principal_id,space["space_id"])).fetchall()
            for memory in memories:
                if set(memory["source_message_ids_json"] or []).intersection(inherited):
                    dependencies.append(f"memory:{memory['id']}:{memory['version']}")
            filtered=[]
            for ref in dependencies:
                parts=ref.split(":",2)
                if len(parts)==3 and parts[0]=="run-result" and conn.execute("SELECT 1 FROM shiliu.assistant_tool_calls "
                    "WHERE workspace_id=%s AND run_id=%s AND call_id=%s AND name='task_focus'",
                    (self.workspace_id,parts[1],parts[2])).fetchone():continue
                filtered.append(ref)
            candidate={**focus,"dependency_refs":list(dict.fromkeys(filtered)),"inherited_message_ids":list(dict.fromkeys(inherited)),
                       "source_message_id":user["id"],"source_message_seq":int(user["seq"]),"user_quote":user["content"][:2000]}
            if state.get("task_focus")==candidate:return {**candidate,"changed":False}
            state["task_focus"]=candidate
            conn.execute("UPDATE shiliu.assistant_runs SET working_state_json=%s,updated_at=clock_timestamp() WHERE workspace_id=%s AND id=%s",
                         (Jsonb(state),self.workspace_id,run_id))
            return {**candidate,"changed":True}

    def task_space(self, thread_id: str, *, conn=None) -> dict[str, Any]:
        return super().task_space(thread_id, conn=conn)

    def initialize_execution_budget(self, run_id: str, *, epoch: int, model_limit: int,
                                    tool_limit: int) -> dict[str, Any]:
        from shiliu.config import ASSISTANT_ACTIVE_SECONDS
        with self.db.connect() as conn:
            run=self._guard_run_completion(conn,run_id,epoch)
            state=dict(run["working_state_json"] or {})
            if "execution_budget" not in state:
                now=_now()
                state["execution_budget"]={"deadline_at":(now+__import__("datetime").timedelta(seconds=ASSISTANT_ACTIVE_SECONDS)).isoformat(),
                    "model_limit":max(0,int(model_limit)),"tool_limit":max(0,int(tool_limit)),"model_calls":0,
                    "tool_executions":0,"known_tokens":0,"unknown_responses":0,"final_dispatched":False}
                conn.execute("UPDATE shiliu.assistant_runs SET working_state_json=%s WHERE workspace_id=%s AND id=%s",
                             (Jsonb(state),self.workspace_id,run_id))
            return dict(state["execution_budget"])

    def execution_remaining(self, run_id: str, *, final: bool = False) -> float:
        from shiliu.config import ASSISTANT_ACTIVE_SECONDS, ASSISTANT_FINAL_SECONDS
        run=self.get_run(run_id)
        budget=run["working_state"].get("execution_budget")
        if not budget:
            return float(ASSISTANT_ACTIVE_SECONDS if final else ASSISTANT_ACTIVE_SECONDS-ASSISTANT_FINAL_SECONDS)
        deadline=datetime.fromisoformat(budget["deadline_at"].replace("Z","+00:00"))
        remaining=(deadline-datetime.now(timezone.utc)).total_seconds()
        return max(0.,remaining-(0 if final else ASSISTANT_FINAL_SECONDS))

    def dispatch_model(self, run_id: str, *, epoch: int, final: bool,
                       input_tokens: int, output_tokens: int, reserve_input_tokens: int | None = None):
        from shiliu.assistant.runtime_contract import ExecutionBudgetExceeded
        from shiliu.config import ASSISTANT_FINAL_SECONDS, ASSISTANT_TOKEN_LIMIT
        with self.db.connect() as conn:
            run=(self._guard_run_completion(conn,run_id,epoch) if final else
                 self.guard_tool_operation(conn,expected_run_id=run_id,expected_epoch=epoch))
            state=dict(run["working_state_json"] or {})
            budget=state.get("execution_budget")
            if not budget: raise AssistantConflict("execution_budget_missing")
            remaining=(datetime.fromisoformat(budget["deadline_at"].replace("Z","+00:00"))-_now()).total_seconds()
            limit=int(budget["model_limit"])-(0 if final else 1)
            reserve=0 if final else (input_tokens if reserve_input_tokens is None else reserve_input_tokens)+8192
            if (remaining <= (0 if final else ASSISTANT_FINAL_SECONDS)
                    or int(budget["model_calls"])>=limit or budget.get("final_dispatched")
                    or state.get("finish_requested") and not final
                    or int(budget["known_tokens"])+input_tokens+output_tokens+reserve>ASSISTANT_TOKEN_LIMIT):
                raise ExecutionBudgetExceeded("当前段模型/Token/期限额度不足")
            budget["model_calls"]+=1
            if final: budget["final_dispatched"]=True
            conn.execute("UPDATE shiliu.assistant_runs SET working_state_json=%s WHERE workspace_id=%s AND id=%s",
                         (Jsonb(state),self.workspace_id,run_id))

    def dispatch_tool(self, run_id: str, *, epoch: int):
        from shiliu.assistant.runtime_contract import ExecutionBudgetExceeded
        with self.db.connect() as conn:
            run=self.guard_tool_operation(conn,expected_run_id=run_id,expected_epoch=epoch)
            state=dict(run["working_state_json"] or {})
            budget=state.get("execution_budget")
            if not budget: raise AssistantConflict("execution_budget_missing")
            if state.get("finish_requested") or budget.get("final_dispatched") or \
                    int(budget["tool_executions"])>=int(budget["tool_limit"]):
                raise ExecutionBudgetExceeded("当前段工具执行额度已用完")
            budget["tool_executions"]+=1
            conn.execute("UPDATE shiliu.assistant_runs SET working_state_json=%s WHERE workspace_id=%s AND id=%s",
                         (Jsonb(state),self.workspace_id,run_id))

    def save_step(self, run_id: str, *, step_count: int, tool_count: int,
                  usage: dict[str, Any], epoch: int | None = None):
        with self.db.connect() as conn:
            run=self._guard_run_completion(conn,run_id,epoch)
            budget=(run["working_state_json"] or {}).get("execution_budget")
            actual=dict(run["usage_json"] or {}) if budget else dict(usage)
            conn.execute("UPDATE shiliu.assistant_runs SET step_count=%s,tool_count=%s,usage_json=%s,"
                         "updated_at=clock_timestamp() WHERE workspace_id=%s AND id=%s AND run_epoch=%s "
                         "AND status='running'",(step_count,tool_count,Jsonb(actual),self.workspace_id,run_id,epoch))

    def fail_run(self, run_id: str, *, code: str, message: str, epoch: int | None = None):
        paused=code in {"step_budget_exhausted","tool_budget_exhausted","context_budget_exceeded","execution_budget_exhausted"}
        with self.db.connect() as conn:
            current=self._lock_execution_diagnostic(conn,run_id,epoch)
            if current is None:return
            status="budget_exhausted" if paused else "failed"
            conn.execute("UPDATE shiliu.assistant_runs SET status=%s,last_error_code=%s,last_error_message=%s,"
                         "updated_at=clock_timestamp(),completed_at=clock_timestamp() WHERE workspace_id=%s AND id=%s",
                         (status,code,message[:1000],self.workspace_id,run_id))
            self._append_event(conn,run_id,"run_budget_exhausted" if paused else "run_failed",
                               {"error_code":code,"message":message[:300]})
            if not paused and (current["working_state_json"] or {}).get(
                "knowledge_save"
            ):
                from shiliu.assistant.notifications import record

                record(
                    conn,
                    self.context,
                    event_key=f"run-issue:{run_id}",
                    origin_type="run_issue",
                    origin_id=run_id,
                    source_type="system",
                    space_id=current.get("space_id"),
                    cause_refs={"run_id": run_id},
                )

    def pause_run(self, run_id: str, *, code: str, message: str, epoch: int | None = None):
        with self.db.connect() as conn:
            run=self._lock_execution_diagnostic(conn,run_id,epoch)
            if run is None:return
            state=dict(run["working_state_json"] or {})
            budget=state.get("execution_budget")
            if budget and "paused_remaining" not in budget:
                deadline=datetime.fromisoformat(budget["deadline_at"].replace("Z","+00:00"))
                budget["paused_remaining"]=max(0.,(deadline-datetime.now(timezone.utc)).total_seconds())
            conn.execute("UPDATE shiliu.assistant_runs SET status='interrupted',working_state_json=%s,last_error_code=%s,"
                         "last_error_message=%s,updated_at=clock_timestamp(),completed_at=clock_timestamp() "
                         "WHERE workspace_id=%s AND id=%s AND status='running'",
                         (Jsonb(state),code,message[:1000],self.workspace_id,run_id))
            self._append_event(conn,run_id,"run_interrupted",{"reason":code,"message":message[:300]})

    def _lock_execution_diagnostic(self, conn, run_id, epoch):
        from shiliu.assistant.runtime_contract import _TOOL_EXECUTION
        active=_TOOL_EXECUTION.get()
        if active is not None:
            if active[0]!=run_id or epoch is not None and epoch!=active[1]:raise AssistantConflict("run_fenced")
            epoch=active[1]
        if type(epoch) is not int or epoch<1:raise AssistantConflict("expected_epoch_required")
        run=lock_thread_run(conn,self.context,run_id)
        # Failure/stop reporting is legal after budget expiry, but cannot revoke
        # a replacement execution or alter a terminal run.
        if run["status"]!="running" or run["run_epoch"]!=epoch or run["cancel_requested"]:return None
        return run

    def request_finish(self, run_id: str) -> dict[str, Any]:
        with self.db.connect() as conn:
            run=lock_thread_run(conn,self.context,run_id)
            if run["status"] in {"queued","running"}:
                state=dict(run["working_state_json"] or {})
                state["finish_requested"]=True
                conn.execute("UPDATE shiliu.assistant_runs SET working_state_json=%s,updated_at=clock_timestamp() "
                             "WHERE workspace_id=%s AND id=%s",(Jsonb(state),self.workspace_id,run_id))
        return self.get_run(run_id)

    def resume_run(self, run_id: str) -> dict[str, Any]:
        with self.db.connect() as conn:
            run=lock_thread_run(conn,self.context,run_id)
            state=dict(run["working_state_json"] or {})
            compaction=(run["status"]=="failed" and run["last_error_code"]=="context_compaction_failed")
            if run["status"] not in {"interrupted","budget_exhausted"} and not compaction:
                raise AssistantConflict("run_not_resumable")
            if compaction:
                if int(state.get("compaction_retries",0))>=1: raise AssistantConflict("context_recovery_not_available")
                state["compaction_retries"]=1
            if run["last_error_code"]=="context_budget_exceeded" and int(state.get("context_recovery_attempts",0))>=1:
                raise AssistantConflict("context_recovery_not_available")
            newer=conn.execute("SELECT 1 FROM shiliu.assistant_runs WHERE workspace_id=%s AND thread_id=%s "
                               "AND insertion_seq>%s LIMIT 1",(self.workspace_id,run["thread_id"],run["insertion_seq"])).fetchone()
            other=conn.execute("SELECT 1 FROM shiliu.assistant_runs WHERE workspace_id=%s AND thread_id=%s AND id<>%s "
                               "AND status IN ('queued','running') LIMIT 1",(self.workspace_id,run["thread_id"],run_id)).fetchone()
            if newer or other: raise AssistantConflict("run_superseded" if newer else "thread_has_active_run")
            state["explicit_new_segment"]=True
            state["segment_step_base"]=int(run["step_count"])
            state["segment_tool_base"]=int(run["tool_count"])
            state.pop("execution_budget",None)
            state.pop("finish_requested",None)
            conn.execute("UPDATE shiliu.assistant_runs SET status='queued',run_epoch=run_epoch+1,cancel_requested=false,"
                         "working_state_json=%s,updated_at=clock_timestamp(),completed_at=NULL,last_error_code=NULL,"
                         "last_error_message=NULL WHERE workspace_id=%s AND id=%s",
                         (Jsonb(state),self.workspace_id,run_id))
            self._append_event(conn,run_id,"run_resumed",{})
        return self.get_run(run_id)

    def set_knowledge_bootstrap(self, run_id: str, *, epoch: int, value: dict):
        with self.db.connect() as conn:
            run=(self._lock_execution_diagnostic(conn,run_id,epoch) if value.get("status")=="abandoned" else
                 self.guard_tool_operation(conn,expected_run_id=run_id,expected_epoch=epoch))
            if run is None:return
            state=dict(run["working_state_json"] or {})
            state["knowledge_bootstrap"]=value
            conn.execute("UPDATE shiliu.assistant_runs SET working_state_json=%s WHERE workspace_id=%s AND id=%s",
                         (Jsonb(state),self.workspace_id,run_id))

    def mark_context_recovery_attempt(self, run_id: str, *, epoch: int) -> bool:
        with self.db.connect() as conn:
            run=self.guard_tool_operation(conn,expected_run_id=run_id,expected_epoch=epoch)
            state=dict(run["working_state_json"] or {})
            if int(state.get("context_recovery_attempts",0))>=1:return False
            state["context_recovery_attempts"]=1
            conn.execute("UPDATE shiliu.assistant_runs SET working_state_json=%s WHERE workspace_id=%s AND id=%s",
                         (Jsonb(state),self.workspace_id,run_id))
            return True

    @staticmethod
    def _legacy_call_key(run_id: str, call_id: str, name: str, arguments: dict) -> list:
        return [run_id,call_id,name,json.dumps(arguments,sort_keys=True,ensure_ascii=False)]

    def freeze_legacy_recovery_calls(self, *, stage: str = "k") -> None:
        allowed=( {"collection_search","knowledge_search","knowledge_read","task_scope"}
                  if stage=="k" else {"knowledge_save_outcome","knowledge_save_discussion","knowledge_propose","knowledge_confirm"} )
        key=f"{stage}_legacy_recovery_calls:{self.principal_id}"
        with self.db.connect() as conn:
            exists=conn.execute("SELECT 1 FROM shiliu.assistant_runtime_state WHERE workspace_id=%s AND principal_id=%s AND key=%s",
                                (self.workspace_id,self.principal_id,key)).fetchone()
            if exists:return
            messages=conn.execute("SELECT m.run_id,m.provider_payload_json FROM shiliu.assistant_messages m "
                                  "JOIN shiliu.assistant_runs r ON (r.workspace_id,r.id)=(m.workspace_id,m.run_id) "
                                  "JOIN shiliu.assistant_threads t ON (t.workspace_id,t.id)=(r.workspace_id,r.thread_id) "
                                  "WHERE m.workspace_id=%s AND t.principal_id=%s AND m.role='assistant' "
                                  "AND r.status IN ('queued','running','interrupted','budget_exhausted','failed')",
                                  (self.workspace_id,self.principal_id)).fetchall()
            permitted=[]
            for row in messages:
                for call in (row["provider_payload_json"] or {}).get("tool_calls") or []:
                    try:
                        call_id=str(call["id"]); fn=call["function"]
                        name=str(fn["name"]); arguments=json.loads(fn.get("arguments") or "{}")
                        if name not in allowed:continue
                        done=conn.execute("SELECT 1 FROM shiliu.assistant_messages WHERE workspace_id=%s AND run_id=%s "
                                          "AND role='tool' AND provider_payload_json->>'tool_call_id'=%s LIMIT 1",
                                          (self.workspace_id,row["run_id"],call_id)).fetchone()
                        if not done:permitted.append(self._legacy_call_key(row["run_id"],call_id,name,arguments))
                    except (KeyError,TypeError,ValueError,json.JSONDecodeError):
                        continue
            conn.execute("INSERT INTO shiliu.assistant_runtime_state(workspace_id,principal_id,key,value,updated_at) "
                         "VALUES(%s,%s,%s,%s,clock_timestamp()) ON CONFLICT(workspace_id,principal_id,key) "
                         "DO NOTHING",(self.workspace_id,self.principal_id,key,json.dumps(permitted,ensure_ascii=False)))

    def legacy_call_registered(self, run_id: str, call_id: str, name: str, arguments: dict, *, stage: str="k") -> bool:
        with self.db.connect(read_only=True) as conn:
            row=conn.execute("SELECT value FROM shiliu.assistant_runtime_state WHERE workspace_id=%s AND principal_id=%s "
                             "AND key=%s",(self.workspace_id,self.principal_id,
                                            f"{stage}_legacy_recovery_calls:{self.principal_id}")).fetchone()
        return bool(row and self._legacy_call_key(run_id,call_id,name,arguments) in json.loads(row["value"]))

    def record_context_attempt(self, candidate, *, attempted: bool, reason: str=""):
        with self.db.connect() as conn:
            run=self._guard_run_completion(conn,candidate.run_id,candidate.epoch)
            thread=conn.execute("SELECT context_state_json FROM shiliu.assistant_threads WHERE workspace_id=%s "
                                "AND id=%s FOR UPDATE",(self.workspace_id,run["thread_id"])).fetchone()
            prior=dict(thread["context_state_json"] or {})
            if int(prior.get("revision") or 0)!=candidate.expected_revision:
                raise AssistantConflict("working_context_changed")
            state=prior or {**candidate.state,"entries":[],"checkpoint":None,"materialized_through_seq":0}
            state["revision"]=candidate.expected_revision+1
            state["pressure_event_attempted"]=bool(attempted)
            if attempted:
                state["last_attempt_history_frontier"]=candidate.state["materialized_through_seq"]
                state["last_attempt_reason"]=reason
            conn.execute("UPDATE shiliu.assistant_threads SET context_state_json=%s WHERE workspace_id=%s AND id=%s",
                         (Jsonb(state),self.workspace_id,run["thread_id"]))

    def save_context_observation(self, run_id: str, *, epoch: int, metadata: dict[str, Any]) -> bool:
        with self.db.connect() as conn:
            run=self._guard_run_completion(conn,run_id,epoch)
            state=dict(run["working_state_json"] or {})
            value={"scope_version":int(metadata["scope_version"]),
                   "observed_memory_epoch":int(metadata["observed_memory_epoch"]),
                   "dependency_refs":list(metadata.get("dependency_refs") or []),
                   "task_note_version":metadata.get("task_note_version"),
                   "visible_user_message_ids":list(metadata.get("visible_user_message_ids") or []),
                   "estimated_input_tokens":int(metadata.get("estimated_input_tokens") or 0)}
            state["context_observation"]=value
            updated=conn.execute("UPDATE shiliu.assistant_runs SET working_state_json=%s WHERE workspace_id=%s AND id=%s "
                                 "AND status='running' AND run_epoch=%s RETURNING id",
                                 (Jsonb(state),self.workspace_id,run_id,epoch)).fetchone()
            return updated is not None

    def record_provider_response(self, run_id: str, turn: Any, *, late: bool, call_id: str | None = None):
        usage=getattr(turn,"usage",None) or {}
        with self.db.connect() as conn:
            root=lock_thread_run(conn,self.context,run_id)
            if call_id and conn.execute("SELECT 1 FROM shiliu.assistant_run_events WHERE workspace_id=%s AND run_id=%s "
                "AND event_type='provider_response' AND payload_json->>'call_id'=%s",
                (self.workspace_id,run_id,call_id)).fetchone():return
            self._append_event(conn,run_id,"provider_response",{"call_id":call_id,"late":bool(late),
                                "usage_known":bool(usage),"finish_reason":getattr(turn,"finish_reason",None)})
            state=dict(root["working_state_json"] or {})
            if state.get("execution_budget") and call_id:
                from shiliu.assistant.runtime_contract import known_tokens
                budget=state["execution_budget"]
                budget["known_tokens"]=int(budget.get("known_tokens",0))+known_tokens(usage)
                budget["unknown_responses"]=int(budget.get("unknown_responses",0))+int(not usage)
                state["usage_includes_late"]=True
            if late or root["status"]!="running":
                late_usage=dict(state.get("late_model_usage") or {})
                for key,value in usage.items():
                    if isinstance(value,(int,float)) and not isinstance(value,bool):late_usage[key]=late_usage.get(key,0)+value
                state["late_model_usage"]=late_usage
                conn.execute("UPDATE shiliu.assistant_runs SET working_state_json=%s WHERE workspace_id=%s AND id=%s",
                             (Jsonb(state),self.workspace_id,run_id))
                if not state.get("execution_budget"):return
            aggregate=dict(root["usage_json"] or {})
            for key,value in usage.items():
                if isinstance(value,(int,float)) and not isinstance(value,bool):aggregate[key]=aggregate.get(key,0)+value
            conn.execute("UPDATE shiliu.assistant_runs SET usage_json=%s,working_state_json=%s WHERE workspace_id=%s AND id=%s",
                         (Jsonb(aggregate),Jsonb(state),self.workspace_id,run_id))

    def add_late_run_usage(self, run_id: str, usage: dict[str, Any], *, epoch: int | None = None):
        with self.db.connect() as conn:
            run=lock_thread_run(conn,self.context,run_id)
            state=dict(run["working_state_json"] or {})
            target=dict(state.get("late_model_usage") or {}) if run["status"]=="running" else dict(run["usage_json"] or {})
            for key,value in usage.items():
                if isinstance(value,(int,float)) and not isinstance(value,bool):target[key]=target.get(key,0)+value
            if run["status"]=="running":
                state["late_model_usage"]=target
                conn.execute("UPDATE shiliu.assistant_runs SET working_state_json=%s WHERE workspace_id=%s AND id=%s",
                             (Jsonb(state),self.workspace_id,run_id))
            else:
                conn.execute("UPDATE shiliu.assistant_runs SET usage_json=%s WHERE workspace_id=%s AND id=%s",
                             (Jsonb(target),self.workspace_id,run_id))
