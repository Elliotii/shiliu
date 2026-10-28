"""Small PG access boundary required by Memory/Wiki; Assistant runtime is W10.

Every helper participates in an explicitly supplied connection. No dialect
switch, schema initialization, connection ownership, or allow-all authorization.
"""

from __future__ import annotations

from uuid import uuid4
from psycopg.types.json import Jsonb

from shiliu.assistant.runtime_contract import AssistantConflict, _TOOL_EXECUTION
from shiliu.storage.fences import guard_tool_operation, CoordinationConflict


class PgAssistantAccess:
    def __init__(self, db):
        self.db = db
        self.context = db.context
        self.principal_id = self.context.user_id

    def guard_tool_operation(
        self, conn, operation_key="", *, expected_run_id=None, expected_epoch=None
    ):
        active = _TOOL_EXECUTION.get()
        if active is not None:
            if expected_run_id is not None and active != (
                expected_run_id,
                expected_epoch,
            ):
                raise AssistantConflict("run_fenced")
            expected_run_id, expected_epoch = active
        if expected_run_id is None:
            if expected_epoch is not None or operation_key.startswith("tool:"):
                raise AssistantConflict("expected_run_epoch_required")
            return
        try:
            return guard_tool_operation(
                conn, self.context, expected_run_id, expected_epoch
            )
        except CoordinationConflict as exc:
            raise AssistantConflict(str(exc)) from exc

    def notify_job_issue(self, conn, job_id):
        row = conn.execute(
            "SELECT * FROM assistant_jobs WHERE workspace_id=%s AND principal_id=%s AND id=%s AND status IN ('blocked','failed')",
            (self.context.workspace_id, self.principal_id, job_id),
        ).fetchone()
        if row and row["kind"] in {
            "source_reconcile",
            "source_extract",
            "wiki_integrate",
            "memory_extract",
            "memory_index",
            "memory_purge",
        }:
            from shiliu.assistant.notifications import record

            payload = row["payload_json"] or {}
            record(
                conn,
                self.context,
                event_key=f"job-issue:{job_id}",
                origin_type="job_issue",
                origin_id=job_id,
                source_type="system",
                space_id=payload.get("space_id"),
                cause_refs={"job_id": job_id},
                created_at=row["updated_at"],
            )

    def enqueue_job(self, conn, *, kind, dedupe_key, payload, not_before=None):
        job_id = "ajob_" + uuid4().hex
        conn.execute(
            "INSERT INTO shiliu.assistant_jobs (workspace_id,principal_id,id,kind,dedupe_key,status,payload_json,not_before,created_at,updated_at) "
            "VALUES (%s,%s,%s,%s,%s,'queued',%s,coalesce(%s::timestamptz,clock_timestamp()),clock_timestamp(),clock_timestamp()) "
            "ON CONFLICT(workspace_id,principal_id,dedupe_key) DO NOTHING",
            (
                self.context.workspace_id,
                self.principal_id,
                job_id,
                kind,
                dedupe_key,
                Jsonb(payload),
                not_before,
            ),
        )
        return conn.execute(
            "SELECT id FROM shiliu.assistant_jobs WHERE workspace_id=%s AND principal_id=%s AND dedupe_key=%s",
            (self.context.workspace_id, self.principal_id, dedupe_key),
        ).fetchone()["id"]

    def get_space(self, space_id, *, conn=None):
        from shiliu.storage.dto import row_dto

        with self.db.connect(conn) as c:
            row = c.execute(
                "SELECT * FROM assistant_spaces WHERE workspace_id=%s AND principal_id=%s AND id=%s",
                (self.context.workspace_id, self.principal_id, space_id),
            ).fetchone()
            if row is None:
                raise KeyError(space_id)
            value = row_dto(row, timestamps={"created_at", "updated_at"})
            value["source_ids"] = value.pop("source_ids_json")
            value["video_ids"] = value.pop("video_ids_json")
            return value

    def list_spaces(self, *, conn=None):
        with self.db.connect(conn) as c:
            rows = c.execute(
                "SELECT id FROM assistant_spaces WHERE workspace_id=%s AND principal_id=%s AND enabled ORDER BY updated_at DESC,id DESC",
                (self.context.workspace_id, self.principal_id),
            ).fetchall()
            return [self.get_space(r["id"], conn=c) for r in rows]

    def get_thread(self, thread_id, *, conn=None):
        from shiliu.storage.dto import row_dto

        with self.db.connect(conn) as c:
            row = c.execute(
                "SELECT * FROM assistant_threads WHERE workspace_id=%s AND principal_id=%s AND id=%s",
                (self.context.workspace_id, self.principal_id, thread_id),
            ).fetchone()
            if row is None:
                raise KeyError(thread_id)
            value = row_dto(row, timestamps={"created_at", "updated_at"})
            runs = c.execute(
                "SELECT * FROM assistant_runs WHERE workspace_id=%s AND thread_id=%s ORDER BY insertion_seq",
                (self.context.workspace_id, thread_id),
            ).fetchall()
            value["messages"] = [
                row_dto(r, timestamps={"created_at"})
                for r in c.execute(
                    "SELECT * FROM assistant_messages WHERE workspace_id=%s AND thread_id=%s ORDER BY seq",
                    (self.context.workspace_id, thread_id),
                ).fetchall()
            ]
            value["runs"] = [
                {**r, "working_state": r["working_state_json"]} for r in runs
            ]
            note = c.execute(
                "SELECT * FROM assistant_task_notes WHERE workspace_id=%s AND thread_id=%s AND task_segment=1",
                (self.context.workspace_id, thread_id),
            ).fetchone()
            value["task_note"] = (
                {k.removesuffix("_json"): v for k, v in note.items()} if note else {}
            )
            return value

    def task_space(self, thread_id, *, conn=None):
        with self.db.connect(conn) as c:
            thread = self.get_thread(thread_id, conn=c)
            space = self.get_space(thread["space_id"], conn=c)
            subset = (
                thread["runs"][-1]["working_state"].get("task_subset")
                if thread["runs"]
                else None
            )
            if subset:
                allowed = set(space["video_ids"])
                space["video_ids"] = [
                    int(v)
                    for v in subset["video_ids"]
                    if not allowed or int(v) in allowed
                ] or [-1]
                space["task_subset"] = subset
            return space

    def confirmed_context_materials(self, conn, *, thread_id, run_id=None):
        self.get_thread(thread_id, conn=conn)
        rows = conn.execute(
            "SELECT provider_payload_json FROM assistant_messages WHERE workspace_id=%s AND thread_id=%s "
            "AND (%s::text IS NULL OR run_id=%s) AND provider_payload_json #>> '{model_projection,delivery,confirmed}'='true'",
            (self.context.workspace_id, thread_id, run_id, run_id),
        ).fetchall()
        return [
            item
            for r in rows
            for item in r["provider_payload_json"]["model_projection"].get(
                "materials", []
            )
        ]

    def resolve_run_result(
        self, result_ref, *, current_thread_id, current_scope_version, conn=None
    ):
        parts = result_ref.split(":")
        if len(parts) == 3 and parts[0] == "run-result":
            requested, call = parts[1:]
        elif len(parts) == 2 and parts[0] == "tool_call_id":
            requested, call = None, parts[1]
        else:
            raise ValueError("invalid_result_ref")
        if not call:
            raise ValueError("invalid_result_ref")
        with self.db.connect(conn) as c:
            self.get_thread(current_thread_id, conn=c)
            row = c.execute(
                "SELECT t.*,r.working_state_json FROM assistant_tool_calls t JOIN assistant_runs r ON (r.workspace_id,r.id)=(t.workspace_id,t.run_id) "
                "WHERE t.workspace_id=%s AND r.thread_id=%s AND t.call_id=%s AND t.status='completed' "
                "AND (%s::text IS NULL OR t.run_id=%s) ORDER BY t.completed_at DESC LIMIT 1",
                (
                    self.context.workspace_id,
                    current_thread_id,
                    call,
                    requested,
                    requested,
                ),
            ).fetchone()
            if row is None or not row["result_json"]:
                raise KeyError(result_ref)
            if (
                int(row["working_state_json"].get("scope_version", 1))
                != current_scope_version
            ):
                raise ValueError("result_outside_current_scope")
            return dict(
                run_id=row["run_id"],
                call_id=row["call_id"],
                name=row["name"],
                arguments=row["args_json"],
                result=row["result_json"],
                result_ref=f"run-result:{row['run_id']}:{row['call_id']}",
            )

    def knowledge_message(
        self, message_id, *, thread_id, allow_operation_receipt=False, conn=None
    ):
        from shiliu.assistant.memory import MemoryService

        with self.db.connect(conn) as c:
            thread = self.get_thread(thread_id, conn=c)
            row = c.execute(
                "SELECT * FROM assistant_messages WHERE workspace_id=%s AND thread_id=%s AND id=%s AND role IN ('user','assistant')",
                (self.context.workspace_id, thread_id, message_id),
            ).fetchone()
            if row is None:
                raise AssistantConflict("save_message_not_available")
            memory = MemoryService(self.db, principal_id=self.principal_id)
            suppressed = memory.suppressed_source_message_ids(
                space_id=thread["space_id"], conn=c
            )
            users = {
                r["id"]
                for r in c.execute(
                    "SELECT id FROM assistant_messages WHERE workspace_id=%s AND run_id=%s AND role='user'",
                    (self.context.workspace_id, row["run_id"]),
                )
            }
            if message_id in suppressed or (
                row["role"] == "assistant" and users & suppressed
            ):
                raise AssistantConflict("save_message_suppressed")
            if row["role"] == "assistant":
                if not c.execute(
                    "SELECT 1 FROM assistant_run_events WHERE workspace_id=%s AND run_id=%s AND event_type='run_completed' AND payload_json->>'message_id'=%s",
                    (self.context.workspace_id, row["run_id"], message_id),
                ).fetchone():
                    raise AssistantConflict("save_answer_not_available")
                if (
                    not allow_operation_receipt
                    and row["provider_payload_json"].get("origin")
                    == "operation_receipt"
                ):
                    raise AssistantConflict("save_target_is_operation_receipt")
                from shiliu.assistant.provider import contains_unexecuted_tool_protocol

                if contains_unexecuted_tool_protocol(row["content"]):
                    raise AssistantConflict("save_answer_contains_tool_protocol")
            refs = [
                r
                for r in row["provider_payload_json"].get("dependency_refs", [])
                if r.startswith("memory:")
            ]
            if (
                refs
                and not memory.validate_dependency_refs(
                    refs, space_id=thread["space_id"], conn=c
                )["valid"]
            ):
                raise AssistantConflict("save_answer_dependencies_changed")
            return row

    def save_job_proposal(
        self, job_id, proposal, *, owner=None, lease_epoch=None, conn=None
    ):
        from shiliu.storage.scheduler import job_transition

        from shiliu.assistant.lease_renewal import check_renewal

        check_renewal()
        if not owner or lease_epoch is None:
            raise AssistantConflict("job_owner_epoch_required")
        with self.db.connect(conn) as c:
            job_transition(
                c,
                self.context,
                job_id,
                owner,
                lease_epoch,
                action="stage",
                proposal=proposal,
            )
        return True

    def tool_execution_scope(self, run_id, epoch):
        from contextlib import contextmanager

        @contextmanager
        def active():
            token = _TOOL_EXECUTION.set((run_id, epoch))
            try:
                yield
            finally:
                _TOOL_EXECUTION.reset(token)

        return active()

    @staticmethod
    def job_dto(row):
        if row is None:
            return None
        return {**row, "payload": row["payload_json"], "proposal": row["proposal_json"]}

    def claim_job(
        self,
        *,
        owner,
        lease_seconds=120,
        allow_model_jobs=True,
        allow_maintenance=True,
        kinds=None,
    ):
        from shiliu.storage.scheduler import claim_job

        with self.db.connect() as c:
            return self.job_dto(
                claim_job(
                    c,
                    self.context,
                    owner,
                    lease_seconds=lease_seconds,
                    allow_model_jobs=allow_model_jobs,
                    allow_maintenance=allow_maintenance,
                    kinds=kinds,
                )
            )

    def finish_job(self, job_id, *, owner, lease_epoch, proposal=None, conn=None):
        from shiliu.storage.scheduler import job_transition

        with self.db.connect(conn) as c:
            if proposal is not None:
                job_transition(
                    c,
                    self.context,
                    job_id,
                    owner,
                    lease_epoch,
                    action="stage",
                    proposal=proposal,
                )
            job_transition(
                c, self.context, job_id, owner, lease_epoch, action="complete"
            )

    def defer_maintenance_job(self, job, *, reason, conn=None):
        """Release this exact lease without consuming a failed attempt."""
        from shiliu.storage.scheduler import job_transition

        if reason not in {"activity", "daily_budget", "batch_budget"}:
            raise ValueError("invalid_maintenance_wait")
        with self.db.connect(conn) as c:
            job_transition(
                c,
                self.context,
                job["id"],
                job["lease_owner"],
                job["lease_epoch"],
                action="defer",
            )
            if reason == "activity":
                return
            c.execute(
                "UPDATE assistant_jobs SET status='budget_wait',not_before=CASE WHEN %s THEN '9999-12-31T23:59:59+00:00'::timestamptz "
                "ELSE (date_trunc('day',clock_timestamp() AT TIME ZONE 'Asia/Shanghai')+interval '1 day') AT TIME ZONE 'Asia/Shanghai' END,"
                "last_error_code=%s WHERE workspace_id=%s AND principal_id=%s AND id=%s",
                (
                    reason == "batch_budget",
                    "maintenance_budget_wait"
                    if reason == "batch_budget"
                    else "background_budget_wait",
                    self.context.workspace_id,
                    self.principal_id,
                    job["id"],
                ),
            )
            c.execute(
                "INSERT INTO assistant_scheduler_events(workspace_id,principal_id,job_id,event_type,reason,created_at) VALUES(%s,%s,%s,'budget_wait',%s,clock_timestamp())",
                (self.context.workspace_id, self.principal_id, job["id"], reason),
            )
