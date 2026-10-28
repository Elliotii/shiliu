from __future__ import annotations

import hashlib
import json
import re
import uuid
import unicodedata
from functools import cached_property
from psycopg.types.json import Jsonb
from shiliu.storage.dto import row_dto
from shiliu.storage.scheduler import job_transition, guard_job
from shiliu.storage.embedding_profiles import DocumentProfile
from shiliu.retrieval.lexical import F1Tokenizer
from shiliu.retrieval.dense import _validate_vector
from shiliu.assistant.pg_access import PgAssistantAccess
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shiliu.assistant.memory_policy import (
    cancels_time,
    requests_time_change,
    plausible_personal_excerpt,
)
from shiliu.assistant.runtime_contract import AssistantConflict
from shiliu.db import Database, utc_now


from shiliu.assistant.memory_time import (
    time_context as make_time_context,
    event_signature,
    validity,
    time_summary,
    TOKEN,
)

MEMORY_KINDS = {"preference", "constraint", "decision", "context"}
_UNSET = object()


class MemoryService:
    def __init__(
        self,
        db: Database,
        *,
        provider: Any | None = None,
        store: PgAssistantAccess | None = None,
        principal_id: str = "local_operator",
    ) -> None:
        self.db = db
        self.provider = provider
        self.store = store or PgAssistantAccess(db)
        self.workspace_id = db.context.workspace_id
        if principal_id != db.context.user_id:
            raise ValueError("principal_context_mismatch")
        self.profile = (
            DocumentProfile(provider, "memory-text-v1")
            if provider is not None
            else None
        )
        self.principal_id = principal_id

    @cached_property
    def tokenizer(self):
        return F1Tokenizer()

    def auto_enabled(self) -> bool:
        return self.auto_policy()["enabled"]

    def auto_policy(self, *, conn=None) -> dict[str, Any]:
        with self.db.connect(conn) as c:
            return self._auto_policy(c)

    def _auto_policy(self, c):
        rows = c.execute(
            "SELECT key,value FROM assistant_runtime_state WHERE workspace_id=%s AND principal_id=%s AND key=ANY(%s)",
            (
                self.workspace_id,
                self.principal_id,
                ["auto_memory_enabled", "auto_memory_generation"],
            ),
        ).fetchall()
        state = {r["key"]: r["value"] for r in rows}
        return {
            "enabled": state.get("auto_memory_enabled", "1") != "0",
            "generation": int(state.get("auto_memory_generation", "0")),
        }

    def set_auto_enabled(self, enabled: bool) -> bool:
        if type(enabled) is not bool:
            raise ValueError("invalid_auto_policy")
        with self._memory_write_transaction() as c:
            policy = self._auto_policy(c)
            for key, value in [
                ("auto_memory_enabled", "1" if enabled else "0"),
                (
                    "auto_memory_generation",
                    str(policy["generation"] + int(policy["enabled"] != enabled)),
                ),
            ]:
                c.execute(
                    "INSERT INTO assistant_runtime_state(workspace_id,principal_id,key,value,updated_at) VALUES(%s,%s,%s,%s,clock_timestamp()) "
                    "ON CONFLICT(workspace_id,principal_id,key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                    (self.workspace_id, self.principal_id, key, value),
                )
        return enabled

    @contextmanager
    def _memory_write_transaction(
        self, *, operation_key="", expected_run_id=None, expected_epoch=None, job=None
    ) -> Iterator[Any]:
        """guard -> optional thread/run -> Job -> Memory. Never encode here."""
        from shiliu.assistant.lease_renewal import check_renewal

        check_renewal()
        with self.db.connect(guard=True) as c:
            self.store.guard_tool_operation(
                c,
                operation_key,
                expected_run_id=expected_run_id,
                expected_epoch=expected_epoch,
            )
            if job is not None:
                current, _ = guard_job(
                    c,
                    self.db.context,
                    job["id"],
                    job["lease_owner"],
                    job["lease_epoch"],
                )
                if current["payload_json"] != job["payload_json"]:
                    raise AssistantConflict("memory_job_payload_mismatch")
            yield c

    def list(
        self, *, space_id: int | None = None, include_inactive: bool = False
    ) -> list[dict[str, Any]]:
        conditions = ["workspace_id=%s", "principal_id=%s"]
        params: list[Any] = [self.workspace_id, self.principal_id]
        if not include_inactive:
            conditions.append("status IN ('active','needs_review')")
        if space_id is not None:
            conditions.append(
                "(scope_kind='user' OR (scope_kind='space' AND scope_id=%s))"
            )
            params.append(str(space_id))
        with self.db.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM assistant_memories WHERE {" AND ".join(conditions)}
                ORDER BY pinned DESC, updated_at DESC, id
                """,
                params,
            ).fetchall()
        items = [self._public(dict(row)) for row in rows]
        source_ids = [
            str(item["source_message_ids"][-1])
            for item in items
            if item["source_message_ids"]
        ]
        if source_ids:
            with self.db.connect() as connection:
                placeholders = ",".join("%s" for _ in source_ids)
                sources = connection.execute(
                    f"SELECT id,thread_id FROM assistant_messages WHERE workspace_id=%s AND id IN ({placeholders})",
                    [self.workspace_id, *source_ids],
                ).fetchall()
            thread_by_message = {
                str(row["id"]): str(row["thread_id"]) for row in sources
            }
            for item in items:
                if item["source_message_ids"]:
                    item["source_thread_id"] = thread_by_message.get(
                        str(item["source_message_ids"][-1])
                    )
        return items

    def get(self, memory_id: str, *, conn=None) -> dict[str, Any]:
        with self.db.connect(conn) as connection:
            row = connection.execute(
                "SELECT * FROM assistant_memories WHERE id=%s AND workspace_id=%s AND principal_id=%s",
                (memory_id, self.workspace_id, self.principal_id),
            ).fetchone()
        if row is None:
            raise KeyError(memory_id)
        return self._public(dict(row))

    def save_explicit(
        self,
        *,
        text: str,
        subject_key: str,
        kind: str,
        scope_kind: str,
        scope_id: int | None,
        operation_key: str,
        source_message_ids: list[str] | None = None,
        source_excerpt: str = "",
        pinned: bool = False,
        origin: str = "explicit",
        valid_from: str | None = None,
        expires_at: str | None = None,
        validity_note: str = "",
        validity_timezone: str | None = None,
        stated_text: str | None = None,
        stated_at: str | None = None,
        time_context: dict | None = None,
        _initial_status: str = "active",
        _connection: Any | None = None,
        _notification_causes: dict | None = None,
        expected_run_id: str | None = None,
        expected_epoch: int | None = None,
    ) -> dict[str, Any]:
        clean_text = self._validate_text(text)
        clean_subject = self._validate_subject(subject_key)
        clean_scope_id = self._validate_scope(scope_kind, scope_id, conn=_connection)
        if kind not in MEMORY_KINDS:
            raise ValueError("invalid_memory_kind")
        if origin not in {"explicit", "extracted"}:
            raise ValueError("invalid_memory_origin")
        # origin is the trusted save entry; retained fact provenance does not
        # identify the trigger of later edits or management operations.
        notification_source_type = (
            "auto_memory"
            if origin == "extracted"
            else "dialogue"
            if (_notification_causes or {}).get("request_message_id")
            else "manual"
        )
        if _initial_status not in {"active", "needs_review"}:
            raise ValueError("invalid_memory_status")
        if stated_text is not None:
            derived = validity(stated_text, stated_at or utc_now())
            valid_from = (
                valid_from if valid_from is not None else derived.get("valid_from")
            )
            expires_at = (
                expires_at if expires_at is not None else derived.get("expires_at")
            )
            validity_note = derived.get("validity_note", validity_note)
            validity_timezone = derived.get("validity_timezone", validity_timezone)
        temporal = (
            time_context
            if time_context is not None
            else (
                make_time_context(
                    stated_text,
                    stated_at or utc_now(),
                    (source_message_ids or [None])[0],
                )
                if stated_text is not None
                else {}
            )
        )
        valid_from, expires_at, validity_note, validity_timezone = (
            self._validate_validity(
                valid_from, expires_at, validity_note, validity_timezone
            )
        )
        now = utc_now()
        memory_id = f"amem_{uuid.uuid4().hex}"
        transaction = (
            self._memory_write_transaction(
                operation_key=operation_key,
                expected_run_id=expected_run_id,
                expected_epoch=expected_epoch,
            )
            if _connection is None
            else nullcontext(_connection)
        )
        with transaction as connection:
            receipt = self._receipt(connection, operation_key)
            if receipt is not None:
                return receipt
            self._validate_scope(scope_kind, scope_id, conn=connection)
            self._validate_sources(
                connection, source_message_ids or [], scope_kind, clean_scope_id
            )
            duplicates = connection.execute(
                """
                SELECT * FROM assistant_memories
                WHERE workspace_id=%s AND principal_id=%s AND scope_kind=%s AND scope_id=%s
                  AND text=%s AND status IN ('active','needs_review')
                  AND valid_from IS NOT DISTINCT FROM %s::timestamptz AND expires_at IS NOT DISTINCT FROM %s::timestamptz
                ORDER BY version DESC FOR UPDATE
                """,
                (
                    self.workspace_id,
                    self.principal_id,
                    scope_kind,
                    clean_scope_id,
                    clean_text,
                    valid_from,
                    expires_at,
                ),
            ).fetchall()
            duplicate = next(
                (
                    row
                    for row in duplicates
                    if event_signature((row["time_context_json"] or {}))
                    == event_signature(temporal)
                ),
                None,
            )
            if duplicate is not None:
                merged_source_ids = sorted(
                    {
                        *(duplicate["source_message_ids_json"] or []),
                        *(source_message_ids or []),
                    }
                )
                merged_excerpt = (
                    str(duplicate["source_excerpt"] or "") or source_excerpt[:1000]
                )
                if origin == "explicit" and (
                    not bool(duplicate["user_edited"])
                    or (pinned and not bool(duplicate["pinned"]))
                    or str(duplicate["status"]) != "active"
                ):
                    before = self._public(dict(duplicate))
                    next_version = int(duplicate["version"]) + 1
                    epoch = self._increment_epoch(connection)
                    connection.execute(
                        """
                        UPDATE assistant_memories SET origin='explicit', status='active',
                            user_edited=true, pinned=%s, version=%s,
                            source_message_ids_json=%s, source_excerpt=%s,
                            change_epoch=%s, updated_at=%s WHERE id=%s AND version=%s
                        """,
                        (
                            bool(pinned or duplicate["pinned"]),
                            next_version,
                            Jsonb(merged_source_ids),
                            merged_excerpt,
                            epoch,
                            now,
                            duplicate["id"],
                            duplicate["version"],
                        ),
                    )
                    current = connection.execute(
                        "SELECT * FROM assistant_memories WHERE id=%s",
                        (duplicate["id"],),
                    ).fetchone()
                    result = self._public(dict(current))
                    self._write_change(
                        connection,
                        result,
                        operation="adopted",
                        before=before,
                        actor="user",
                        memory_epoch=epoch,
                        operation_key=operation_key,
                        notification_causes=_notification_causes,
                        source_type=notification_source_type,
                    )
                    self._enqueue_index(
                        connection,
                        str(duplicate["id"]),
                        next_version,
                        scope_kind,
                        clean_scope_id,
                    )
                    self._save_receipt(connection, operation_key, "memory_save", result)
                    return result
                if merged_source_ids != (duplicate["source_message_ids_json"] or []):
                    connection.execute(
                        """
                        UPDATE assistant_memories SET source_message_ids_json=%s, source_excerpt=%s
                        WHERE id=%s
                        """,
                        (Jsonb(merged_source_ids), merged_excerpt, duplicate["id"]),
                    )
                    duplicate = connection.execute(
                        "SELECT * FROM assistant_memories WHERE id=%s",
                        (duplicate["id"],),
                    ).fetchone()
                result = self._public(dict(duplicate))
                self._save_receipt(connection, operation_key, "memory_save", result)
                return result
            epoch = self._increment_epoch(connection)
            connection.execute(
                """
                INSERT INTO assistant_memories(
                    workspace_id, scope_space_id, id, principal_id, scope_kind, scope_id, kind, text, subject_key,
                    origin, source_message_ids_json, source_excerpt, status, version,
                    pinned, user_edited, valid_from, expires_at, validity_note,
                    validity_timezone, change_epoch, created_at, updated_at, time_context_json
                ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    self.workspace_id,
                    (int(clean_scope_id) if scope_kind == "space" else None),
                    memory_id,
                    self.principal_id,
                    scope_kind,
                    clean_scope_id,
                    kind,
                    clean_text,
                    clean_subject,
                    origin,
                    Jsonb(source_message_ids or []),
                    source_excerpt[:1000],
                    _initial_status,
                    bool(pinned),
                    origin == "explicit",
                    valid_from,
                    expires_at,
                    validity_note,
                    validity_timezone,
                    epoch,
                    now,
                    now,
                    Jsonb(temporal),
                ),
            )
            current = connection.execute(
                "SELECT * FROM assistant_memories WHERE id=%s", (memory_id,)
            ).fetchone()
            result = self._public(dict(current))
            self._write_change(
                connection,
                result,
                operation="created",
                before=None,
                actor="user" if origin == "explicit" else "assistant",
                memory_epoch=epoch,
                operation_key=operation_key,
                notification_causes=_notification_causes,
                source_type=notification_source_type,
            )
            if _initial_status == "active":
                self._fts_replace(connection, memory_id, clean_text)
                self._enqueue_index(
                    connection, memory_id, 1, scope_kind, clean_scope_id
                )
            self._save_receipt(connection, operation_key, "memory_save", result)
        return result

    def correct(
        self,
        memory_id: str,
        *,
        text: str,
        expected_version: int,
        operation_key: str,
        subject_key: str | None = None,
        kind: str | None = None,
        valid_from: str | None | object = _UNSET,
        expires_at: str | None | object = _UNSET,
        validity_note: str | object = _UNSET,
        validity_timezone: str | None | object = _UNSET,
        source_message_ids: list[str] | object = _UNSET,
        source_excerpt: str | object = _UNSET,
        stated_text: str | None = None,
        stated_at: str | None = None,
        update_time_context: bool | None = None,
        _actor: str = "user",
        _user_edited: bool = True,
        _connection: Any | None = None,
        _notification_causes: dict | None = None,
        expected_run_id: str | None = None,
        expected_epoch: int | None = None,
    ) -> dict[str, Any]:
        clean_text = self._validate_text(text)
        now = utc_now()
        transaction = (
            self._memory_write_transaction(
                operation_key=operation_key,
                expected_run_id=expected_run_id,
                expected_epoch=expected_epoch,
            )
            if _connection is None
            else nullcontext(_connection)
        )
        with transaction as connection:
            receipt = self._receipt(connection, operation_key)
            if receipt is not None:
                return receipt
            row = connection.execute(
                "SELECT * FROM assistant_memories WHERE id=%s AND workspace_id=%s AND principal_id=%s FOR UPDATE",
                (memory_id, self.workspace_id, self.principal_id),
            ).fetchone()
            if row is None:
                raise KeyError(memory_id)
            before = self._public(dict(row))
            if int(row["version"]) != expected_version:
                raise AssistantConflict("memory_version_conflict")
            if str(row["status"]) == "forgotten":
                raise AssistantConflict("memory_forgotten")
            next_subject = self._validate_subject(
                subject_key or str(row["subject_key"])
            )
            next_kind = kind or str(row["kind"])
            if next_kind not in MEMORY_KINDS:
                raise ValueError("invalid_memory_kind")
            time_words = stated_text if stated_text is not None else clean_text
            temporal = row["time_context_json"] or {}
            candidate = make_time_context(
                time_words,
                stated_at or now,
                (list(source_message_ids) or [None])[0]
                if source_message_ids is not _UNSET
                else None,
            )
            old_expressions = [e.get("expression") for e in temporal.get("events", [])]
            new_expressions = [e.get("expression") for e in candidate.get("events", [])]
            change_time = update_time_context is True or (
                update_time_context is None
                and bool(new_expressions)
                and (
                    old_expressions != new_expressions
                    or requests_time_change(time_words)
                )
            )
            if change_time:
                if len(temporal.get("events", [])) > len(candidate["events"]):
                    retained = [
                        {
                            **event,
                            "stated_at": event.get(
                                "stated_at", temporal.get("stated_at")
                            ),
                            "source_message_id": event.get(
                                "source_message_id", temporal.get("source_message_id")
                            ),
                        }
                        for event in temporal["events"]
                        if event["expression"] in clean_text
                        and event["expression"] not in new_expressions
                    ]
                    if len(retained) + len(candidate["events"]) < len(
                        temporal["events"]
                    ):
                        raise ValueError("memory_time_source_ambiguous")
                    candidate["events"].extend(retained)
                temporal = candidate
            elif not temporal and stated_text is not None and not candidate["events"]:
                temporal = candidate
            if cancels_time(time_words, clean_text):
                valid_from, expires_at, validity_note, validity_timezone = (
                    None,
                    None,
                    "",
                    None,
                )
            elif (
                expires_at is _UNSET
                and valid_from is _UNSET
                and update_time_context is not False
            ):
                changed_bounds = update_time_context is True or TOKEN.findall(
                    time_words
                ) != TOKEN.findall(str(row["text"]))
                if changed_bounds:
                    derived = validity(time_words, stated_at or now)
                    if derived:
                        valid_from = derived.get("valid_from", valid_from)
                        expires_at = derived.get("expires_at", expires_at)
                        validity_note = derived.get("validity_note", validity_note)
                        validity_timezone = derived.get(
                            "validity_timezone", validity_timezone
                        )
            if expires_at is None:
                if validity_note is _UNSET:
                    validity_note = ""
                if validity_timezone is _UNSET:
                    validity_timezone = None
            (
                next_valid_from,
                next_expires_at,
                next_validity_note,
                next_validity_timezone,
            ) = self._validate_validity(
                row["valid_from"] if valid_from is _UNSET else valid_from,
                row["expires_at"] if expires_at is _UNSET else expires_at,
                row["validity_note"] if validity_note is _UNSET else validity_note,
                row["validity_timezone"]
                if validity_timezone is _UNSET
                else validity_timezone,
            )
            next_source_message_ids = (
                (row["source_message_ids_json"] or [])
                if source_message_ids is _UNSET
                else list(dict.fromkeys(str(value) for value in source_message_ids))
            )
            next_source_excerpt = (
                str(row["source_excerpt"] or "")
                if source_excerpt is _UNSET
                else str(source_excerpt)[:1000]
            )
            self._validate_scope(
                row["scope_kind"],
                int(row["scope_id"]) if row["scope_kind"] == "space" else None,
                conn=connection,
            )
            self._validate_sources(
                connection, next_source_message_ids, row["scope_kind"], row["scope_id"]
            )
            next_version = expected_version + 1
            epoch = self._increment_epoch(connection)
            self._suppress(
                connection,
                row,
                memory_epoch=epoch,
                content_hash=self._content_hash(str(row["text"])),
            )
            connection.execute(
                """
                UPDATE assistant_memories SET text=%s, subject_key=%s, kind=%s, version=%s,
                    status='active', user_edited=%s,
                    valid_from=%s, expires_at=%s, validity_note=%s, validity_timezone=%s,
                    source_message_ids_json=%s, source_excerpt=%s, change_epoch=%s, updated_at=%s, time_context_json=%s
                WHERE id=%s AND version=%s
                """,
                (
                    clean_text,
                    next_subject,
                    next_kind,
                    next_version,
                    bool(_user_edited),
                    next_valid_from,
                    next_expires_at,
                    next_validity_note,
                    next_validity_timezone,
                    Jsonb(next_source_message_ids),
                    next_source_excerpt,
                    epoch,
                    now,
                    Jsonb(temporal),
                    memory_id,
                    expected_version,
                ),
            )
            current = connection.execute(
                "SELECT * FROM assistant_memories WHERE id=%s", (memory_id,)
            ).fetchone()
            result = self._public(dict(current))
            self._write_change(
                connection,
                result,
                operation="corrected",
                before=before,
                actor=_actor,
                memory_epoch=epoch,
                operation_key=operation_key,
                notification_causes=_notification_causes,
                source_type=(
                    "auto_memory"
                    if _actor == "assistant"
                    else "dialogue"
                    if (_notification_causes or {}).get("request_message_id")
                    else "manual"
                ),
            )
            self._fts_replace(connection, memory_id, clean_text)
            self._enqueue_index(
                connection,
                memory_id,
                next_version,
                str(row["scope_kind"]),
                str(row["scope_id"]),
            )
            self._save_receipt(connection, operation_key, "memory_correct", result)
        return result

    def _creation_for_undo(
        self,
        c: Any,
        memory_id: str,
        save_operation_key: str,
        expected_version: int,
        *,
        lock=True,
    ):
        saved = c.execute(
            "SELECT result_json FROM assistant_mutation_receipts WHERE workspace_id=%s AND principal_id=%s AND operation_key=%s AND operation='memory_save'",
            (self.workspace_id, self.principal_id, save_operation_key),
        ).fetchone()
        row = c.execute(
            "SELECT * FROM assistant_memories WHERE id=%s AND workspace_id=%s AND principal_id=%s"
            + (" FOR UPDATE" if lock else ""),
            (memory_id, self.workspace_id, self.principal_id),
        ).fetchone()
        created = c.execute(
            "SELECT after_json FROM assistant_memory_changes WHERE memory_id=%s AND operation='created' AND version=1",
            (memory_id,),
        ).fetchone()
        if not saved or not row or not created or not created["after_json"]:
            raise AssistantConflict("memory_creation_receipt_required")
        current = self._public(dict(row))
        original = created["after_json"]
        receipt = saved["result_json"]
        # Detect adoption, no-op saves and source merges, including unversioned metadata.
        business = lambda value: {
            k: v
            for k, v in value.items()
            if k not in {"last_projected_version", "updated_at"}
        }
        if (
            expected_version != 1
            or current["version"] != 1
            or current.get("origin") != "explicit"
            or business(current) != business(original)
            or receipt != original
        ):
            raise AssistantConflict("memory_creation_changed_or_not_original")
        if c.execute(
            "SELECT 1 FROM assistant_mutation_receipts WHERE workspace_id=%s AND principal_id=%s AND operation='memory_save' AND operation_key<>%s AND result_json->>'id'=%s",
            (self.workspace_id, self.principal_id, save_operation_key, memory_id),
        ).fetchone():
            raise AssistantConflict("memory_creation_has_later_save")
        return row

    def creation_feedback(
        self, memory: dict, *, save_operation_key: str, space_id: int | None
    ) -> dict:
        undo = None
        with self.db.connect() as c:
            try:
                self._creation_for_undo(
                    c, memory["id"], save_operation_key, int(memory["version"])
                )
                undo = {
                    "kind": "memory_created",
                    "save_operation_key": save_operation_key,
                }
            except AssistantConflict:
                pass
        return {
            "kind": "memory",
            "operation_key": save_operation_key,
            "space_id": space_id,
            "count": 1,
            "items": [
                {
                    "memory_id": memory["id"],
                    "version": memory["version"],
                    "title": memory["text"],
                    "undo": undo,
                }
            ],
        }

    def undo_created(
        self,
        memory_id: str,
        *,
        save_operation_key: str,
        expected_version: int,
        operation_key: str,
        expected_run_id: str | None = None,
        expected_epoch: int | None = None,
        _notification_id: str | None = None,
    ) -> dict[str, Any]:
        """Retract one unchanged explicit creation; never suppress its entire message."""
        with self._memory_write_transaction(
            operation_key=operation_key,
            expected_run_id=expected_run_id,
            expected_epoch=expected_epoch,
        ) as c:
            prior = self._receipt(c, operation_key)
            if prior is not None:
                return prior
            row = self._creation_for_undo(
                c, memory_id, save_operation_key, expected_version
            )
            from shiliu.assistant.notifications import message_id, record

            created = c.execute(
                "SELECT id,created_at FROM assistant_memory_changes WHERE workspace_id=%s AND memory_id=%s AND operation='created' AND version=1",
                (self.workspace_id, memory_id),
            ).fetchone()
            event_key = f"memory-change:{created['id']}"
            original_notification_id = message_id(self.db.context, event_key)
            if (
                _notification_id is not None
                and _notification_id != original_notification_id
            ):
                raise AssistantConflict("memory_creation_message_mismatch")
            epoch = self._increment_epoch(c)
            content_hash = self._content_hash(str(row["text"]))
            # Retraction must not erase an earlier genuine forget's message-level
            # protection when this fact was subsequently explicitly recreated.
            existing = c.execute(
                "SELECT 1 FROM assistant_memory_suppressions WHERE workspace_id=%s AND principal_id=%s AND scope_kind=%s AND scope_id=%s AND subject_key=%s AND content_hash=%s",
                (
                    self.workspace_id,
                    self.principal_id,
                    row["scope_kind"],
                    row["scope_id"],
                    row["subject_key"],
                    content_hash,
                ),
            ).fetchone()
            if not existing:
                suppression = {**dict(row), "source_message_ids_json": []}
                self._suppress(
                    c, suppression, memory_epoch=epoch, content_hash=content_hash
                )
            c.execute(
                "UPDATE assistant_memories SET status='forgotten',version=version+1,text='',source_excerpt='',time_context_json='{}',change_epoch=%s,updated_at=%s WHERE id=%s AND version=1",
                (epoch, utc_now(), memory_id),
            )
            self._clear_projection(c, memory_id)
            result = self._public(
                dict(
                    c.execute(
                        "SELECT * FROM assistant_memories WHERE id=%s", (memory_id,)
                    ).fetchone()
                )
            )
            self._write_change(
                c,
                result,
                operation="creation_retracted",
                before=None,
                actor="user",
                memory_epoch=epoch,
                operation_key=operation_key,
            )
            self.store.enqueue_job(
                c,
                kind="memory_purge",
                dedupe_key=f"memory_purge:{memory_id}:2",
                payload={"memory_id": memory_id, "version": 2, "memory_epoch": epoch},
            )
            self._save_receipt(c, operation_key, "memory_creation_retract", result)
            # Exact creation identity also covers the original toast/API path.
            # Existing rows keep their provenance/read/creation time on conflict;
            # an old virtual creation is materialized as historical system data.
            record(
                c,
                self.db.context,
                event_key=event_key,
                origin_type="memory_change",
                origin_id=created["id"],
                space_id=None if row["scope_kind"] == "user" else int(row["scope_id"]),
                source_type="system",
                cause_refs={"operation_key": save_operation_key},
                created_at=created["created_at"],
                read_at=created["created_at"],
            )
            c.execute(
                "UPDATE assistant_notifications SET undo_ref=%s,activity_at=clock_timestamp() WHERE workspace_id=%s AND principal_id=%s AND id=%s AND undo_ref IS NULL",
                (
                    operation_key,
                    self.workspace_id,
                    self.principal_id,
                    original_notification_id,
                ),
            )
            return result

    def forget(
        self,
        memory_id: str,
        *,
        expected_version: int,
        operation_key: str,
        source_message_ids: list[str] | None = None,
        _notification_causes: dict | None = None,
        expected_run_id: str | None = None,
        expected_epoch: int | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._memory_write_transaction(
            operation_key=operation_key,
            expected_run_id=expected_run_id,
            expected_epoch=expected_epoch,
        ) as connection:
            receipt = self._receipt(connection, operation_key)
            if receipt is not None:
                return receipt
            row = connection.execute(
                "SELECT * FROM assistant_memories WHERE id=%s AND workspace_id=%s AND principal_id=%s FOR UPDATE",
                (memory_id, self.workspace_id, self.principal_id),
            ).fetchone()
            if row is None:
                raise KeyError(memory_id)
            if str(row["status"]) == "forgotten":
                result = self._public(dict(row))
                self._save_receipt(connection, operation_key, "memory_forget", result)
                return result
            if int(row["version"]) != expected_version:
                raise AssistantConflict("memory_version_conflict")
            next_version = expected_version + 1
            epoch = self._increment_epoch(connection)
            row_for_suppression = dict(row)
            if source_message_ids:
                existing_source_ids = row["source_message_ids_json"] or []
                row_for_suppression["source_message_ids_json"] = list(
                    dict.fromkeys(
                        [
                            *(str(value) for value in existing_source_ids),
                            *(str(value) for value in source_message_ids),
                        ]
                    )
                )
            self._suppress(
                connection,
                row_for_suppression,
                memory_epoch=epoch,
                content_hash=self._content_hash(str(row["text"])),
            )
            connection.execute(
                """
                UPDATE assistant_memories SET status='forgotten', version=%s, text='',
                    source_excerpt='', time_context_json='{}', source_message_ids_json=%s,
                    change_epoch=%s, updated_at=%s
                WHERE id=%s AND version=%s
                """,
                (
                    next_version,
                    Jsonb(row_for_suppression["source_message_ids_json"]),
                    epoch,
                    now,
                    memory_id,
                    expected_version,
                ),
            )
            self._clear_projection(connection, memory_id)
            connection.execute(
                "UPDATE assistant_memory_changes SET before_json=NULL, after_json=NULL WHERE memory_id=%s",
                (memory_id,),
            )
            current = connection.execute(
                "SELECT * FROM assistant_memories WHERE id=%s", (memory_id,)
            ).fetchone()
            result = self._public(dict(current))
            self._write_change(
                connection,
                result,
                operation="forgotten",
                notification_causes=_notification_causes,
                source_type="dialogue"
                if (_notification_causes or {}).get("request_message_id")
                else "manual",
                before=None,
                actor="user",
                memory_epoch=epoch,
                operation_key=operation_key,
            )
            self.store.enqueue_job(
                connection,
                kind="memory_purge",
                dedupe_key=f"memory_purge:{memory_id}:{next_version}",
                payload={
                    "memory_id": memory_id,
                    "version": next_version,
                    "memory_epoch": epoch,
                },
            )
            self._save_receipt(connection, operation_key, "memory_forget", result)
        return result

    def recall(
        self, query: str, *, space_id: int, limit: int = 8
    ) -> list[dict[str, Any]]:
        return self.recall_with_status(query, space_id=space_id, limit=limit)["items"]

    def recall_with_status(
        self,
        query: str,
        *,
        space_id: int,
        limit: int = 8,
        linked_ids: list[str] | None = None,
        excluded_kinds: set[str] | None = None,
    ) -> dict[str, Any]:
        clean_query = " ".join(query.split())[:1000]
        excluded_kinds = excluded_kinds or set()
        self._validate_scope("space", space_id)
        candidates: dict[str, dict[str, Any]] = {}
        semantic_versions: dict[str, tuple] = {}
        backend_ready = False
        backend_error = (
            "embedding_provider_unavailable" if self.provider is None else None
        )
        vector = None
        if self.provider is not None and clean_query:
            try:
                vector = _validate_vector(self.provider.embed_query(clean_query), 512)
            except Exception as exc:
                backend_error = type(exc).__name__

        def add_candidate(record_id: str, score: float, reason: str) -> None:
            value = candidates.setdefault(record_id, {"score": 0.0, "reasons": set()})
            value["score"] = max(value["score"], score)
            value["reasons"].add(reason)

        task_linked_ids = list(dict.fromkeys(linked_ids or []))[:2]
        # All SQL channels filter scope/status/time/kind BEFORE their own LIMIT.
        eligible = (
            "m.workspace_id=%s AND m.principal_id=%s AND m.status='active' "
            "AND (m.scope_kind='user' OR (m.scope_kind='space' AND m.scope_space_id=%s)) "
            "AND (m.valid_from IS NULL OR m.valid_from<=clock_timestamp()) "
            "AND (m.expires_at IS NULL OR m.expires_at>clock_timestamp()) "
            "AND NOT (m.kind=ANY(%s))"
        )
        params = [
            self.workspace_id,
            self.principal_id,
            space_id,
            sorted(excluded_kinds),
        ]
        with self.db.pg.transaction(
            read_only=True, isolation="repeatable read"
        ) as connection:
            if vector is not None:
                active_profile = connection.execute(
                    "SELECT embedding_profile_id FROM assistant_runtime_state WHERE workspace_id=%s AND principal_id=%s AND embedding_domain='memory'",
                    (self.workspace_id, self.principal_id),
                ).fetchone()
                if (
                    active_profile
                    and active_profile["embedding_profile_id"]
                    == self.profile.profile_id
                ):
                    rows = connection.execute(
                        "SELECT m.id,m.version,m.change_epoch,e.embedding_text_hash,1-(e.embedding <=> %s) AS score "
                        "FROM assistant_memories m JOIN memory_embeddings e ON (e.workspace_id,e.memory_id)=(m.workspace_id,m.id) "
                        "JOIN embedding_profiles p ON p.profile_id=e.profile_id WHERE "
                        + eligible
                        + " AND e.profile_id=%s AND e.memory_version=m.version AND e.change_epoch=m.change_epoch "
                        "AND e.embedding_text_hash=encode(sha256(convert_to(normalize(m.text,NFKC),'UTF8')),'hex') "
                        "ORDER BY e.embedding <=> %s,m.id LIMIT 20",
                        [vector, *params, self.profile.profile_id, vector],
                    ).fetchall()
                    for row in rows:
                        semantic_versions[row["id"]] = (
                            row["version"],
                            row["change_epoch"],
                            row["embedding_text_hash"],
                        )
                        add_candidate(row["id"], float(row["score"]), "semantic")
                    missing = connection.execute(
                        "SELECT count(*) AS n FROM assistant_memories m WHERE "
                        + eligible
                        + " AND NOT EXISTS (SELECT 1 FROM memory_embeddings e WHERE e.workspace_id=m.workspace_id AND e.memory_id=m.id "
                        "AND e.profile_id=%s AND e.memory_version=m.version AND e.change_epoch=m.change_epoch "
                        "AND e.embedding_text_hash=encode(sha256(convert_to(normalize(m.text,NFKC),'UTF8')),'hex'))",
                        [*params, self.profile.profile_id],
                    ).fetchone()["n"]
                    backend_ready = not missing
                    if missing:
                        backend_error = "memory_embeddings_partial"
                else:
                    backend_error = "memory_profile_not_active"
            tsquery = self.tokenizer.query(clean_query)
            if clean_query:
                escaped = (
                    unicodedata.normalize("NFKC", clean_query)
                    .casefold()
                    .replace("\\", "\\\\")
                    .replace("%", "\\%")
                    .replace("_", "\\_")
                )
                pattern = "%" + escaped + "%"
                lexical = connection.execute(
                    "SELECT m.id FROM assistant_memories m WHERE "
                    + eligible
                    + " AND ((%s<>'' AND m.search_vector @@ to_tsquery('simple',%s)) OR lower(normalize(m.text,NFKC)) LIKE %s "
                    "OR lower(normalize(m.subject_key,NFKC)) LIKE %s) "
                    "ORDER BY ts_rank(m.search_vector,to_tsquery('simple',%s)) DESC,m.pinned DESC,m.user_edited DESC,m.updated_at DESC,m.id LIMIT 60",
                    [*params, tsquery, tsquery, pattern, pattern, tsquery],
                ).fetchall()
                for rank, row in enumerate(lexical):
                    add_candidate(row["id"], 0.65 - rank * 0.002, "lexical")

            def grams(value):
                compact = re.sub(r"[\s，。？！、；：,.!?：]+", "", value)
                return {compact[i : i + 2] for i in range(max(0, len(compact) - 1))}

            query_grams = grams(clean_query)
            if query_grams:
                rows = connection.execute(
                    "SELECT m.id,m.text,m.subject_key,m.time_context_json FROM assistant_memories m WHERE "
                    + eligible
                    + " ORDER BY m.updated_at DESC,m.id LIMIT 300",
                    params,
                ).fetchall()
                for row in rows:
                    words = time_summary(row["time_context_json"] or {})
                    words = re.sub(
                        r"(\d{4})-(\d{2})(?![-\d])",
                        lambda m: f"{m[1]}年{int(m[2])}月",
                        words,
                    )
                    overlap = query_grams & grams(
                        row["text"] + row["subject_key"] + words
                    )
                    if len(overlap) >= 2:
                        add_candidate(
                            row["id"],
                            min(0.72, 0.43 + len(overlap) * 0.025),
                            "chinese_lexical",
                        )
            explicit = connection.execute(
                "SELECT m.id,m.pinned,m.kind FROM assistant_memories m WHERE "
                + eligible
                + " AND (m.pinned OR m.last_projected_version IS DISTINCT FROM m.version) ORDER BY m.pinned DESC,m.user_edited DESC,m.updated_at DESC,m.id LIMIT 40",
                params,
            ).fetchall()
            anaphoric = bool(
                re.search(
                    r"(?:按我|我的|我现在|我接下来|那我|上次|之前|我的计划|我的安排)",
                    clean_query,
                )
            )
            count = 0
            for row in explicit:
                matched = row["id"] in candidates
                fallback = (
                    anaphoric and count < 2 and row["kind"] in {"context", "decision"}
                )
                if row["pinned"] or matched or fallback:
                    add_candidate(
                        row["id"],
                        0.55 if row["pinned"] else 0.25,
                        "explicit_or_pending",
                    )
                    if fallback and not matched:
                        count += 1
            if task_linked_ids:
                for row in connection.execute(
                    "SELECT m.id FROM assistant_memories m WHERE "
                    + eligible
                    + " AND m.id=ANY(%s)",
                    [*params, task_linked_ids],
                ):
                    add_candidate(row["id"], 0.74, "current_task_dependency")
        # New statement/snapshot after query encoding and candidate enumeration.
        # Never pair a current formal text with only a stale dense match.
        with self.db.connect(read_only=True) as connection:
            rows = connection.execute(
                "SELECT m.* FROM assistant_memories m WHERE "
                + eligible
                + " AND m.id=ANY(%s)",
                [*params, sorted(candidates)],
            ).fetchall()
            active = {r["id"]: r for r in rows}

        linked_diagnostics: list[dict[str, Any]] = []
        if task_linked_ids:
            with self.db.connect() as connection:
                placeholders = ",".join("%s" for _ in task_linked_ids)
                linked_rows = {
                    str(row["id"]): row
                    for row in connection.execute(
                        f"SELECT id,version,status,kind FROM assistant_memories "
                        f"WHERE id IN ({placeholders}) AND workspace_id=%s AND principal_id=%s",
                        (*task_linked_ids, self.workspace_id, self.principal_id),
                    )
                }
            for record_id in task_linked_ids:
                row = linked_rows.get(record_id)
                linked_diagnostics.append(
                    {
                        "id": record_id,
                        "version": int(row["version"]) if row else None,
                        "decision": "excluded_by_current_request"
                        if row and row["kind"] in excluded_kinds
                        else "eligible"
                        if record_id in active
                        else "forgotten"
                        if row and row["status"] == "forgotten"
                        else "expired_or_out_of_scope",
                    }
                )
        ranked: list[tuple[dict[str, Any], float, set[str]]] = []
        for record_id, candidate in candidates.items():
            row = active.get(record_id)
            if row is None or row["kind"] in excluded_kinds:
                continue
            reasons = set(candidate["reasons"])
            score = float(candidate["score"])
            semantic_version = semantic_versions.get(record_id)
            if semantic_version is not None and semantic_version != (
                row["version"],
                row["change_epoch"],
                self._content_hash(unicodedata.normalize("NFKC", row["text"])),
            ):
                reasons.discard("semantic")
                reasons.add("stale_semantic_rechecked")
                if not reasons.intersection(
                    {
                        "lexical",
                        "chinese_lexical",
                        "explicit_or_pending",
                        "current_task_dependency",
                    }
                ):
                    continue
                if "current_task_dependency" not in reasons:
                    score = min(score, 0.3)
            ranked.append((row, score, reasons))
        ranked.sort(
            key=lambda item: (
                item[1],
                int(str(item[0]["scope_kind"]) == "space"),
                int(item[0]["pinned"]),
                int(item[0]["user_edited"]),
                item[0]["updated_at"],
            ),
            reverse=True,
        )
        subject_scopes: dict[str, set[str]] = {}
        for row, _score, _reasons in ranked:
            subject_scopes.setdefault(str(row["subject_key"]), set()).add(
                str(row["scope_kind"])
            )
        items = []
        fixed = [item for item in ranked if bool(item[0]["pinned"])]
        ordinary = [item for item in ranked if not bool(item[0]["pinned"])]
        selected = (
            fixed[: min(2, limit)] + ordinary[: max(0, limit - min(2, len(fixed)))]
        )
        for row, score, reasons in selected:
            public = self._public(row)
            public.update(
                {
                    "semantic_index_ready": backend_ready,
                    "recall_score": round(score, 6),
                    "recall_reasons": sorted(reasons),
                    "dependency_ref": self.dependency_ref(public),
                    "scope_precedence": "current_space"
                    if public["scope_kind"] == "space"
                    else "global_user",
                    "scope_conflict": len(
                        subject_scopes.get(str(public["subject_key"]), set())
                    )
                    > 1,
                }
            )
            items.append(public)
        return {
            "items": items,
            "linked_diagnostics": linked_diagnostics,
            "semantic_index": "ready"
            if backend_ready
            else "partial"
            if semantic_versions
            else "unavailable",
            "semantic_error": backend_error,
            "authoritative_store": "postgresql",
            "storage_backend": "postgresql",
            "lexical_profile": self.tokenizer.profile,
            "query_profile": "memory-query-v1",
            "embedding_profile": self.profile.profile_id if self.profile else None,
            "degraded_reason": backend_error,
            "memory_epoch": self.current_epoch(),
        }

    def current_epoch(self, *, conn=None) -> int:
        with self.db.connect(conn) as c:
            return self._current_epoch(c)

    def changes_since(
        self, after_epoch: int, *, space_id: int | None = None, limit: int = 200
    ) -> dict[str, Any]:
        if after_epoch < 0 or limit < 1 or limit > 500:
            raise ValueError("invalid_memory_change_cursor")
        conditions = ["m.workspace_id=%s", "m.principal_id=%s", "c.memory_epoch>%s"]
        params: list[Any] = [self.workspace_id, self.principal_id, after_epoch]
        if space_id is not None:
            conditions.append(
                "(m.scope_kind='user' OR (m.scope_kind='space' AND m.scope_id=%s))"
            )
            params.append(str(space_id))
        params.append(limit)
        with self.db.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT c.memory_id, c.version, c.operation, c.actor, c.reason,
                       c.memory_epoch, c.created_at, m.scope_kind, m.scope_id,
                       m.status, m.change_epoch
                FROM assistant_memory_changes c
                JOIN assistant_memories m ON m.id=c.memory_id
                WHERE {" AND ".join(conditions)}
                ORDER BY c.memory_epoch, c.id LIMIT %s
                """,
                params,
            ).fetchall()
        items = [row_dto(row, timestamps={"created_at"}) for row in rows]
        return {
            "after_epoch": after_epoch,
            "current_epoch": self.current_epoch(),
            "items": items,
            "next_epoch": max(
                (int(item["memory_epoch"]) for item in items), default=after_epoch
            ),
        }

    def suppressed_source_message_ids(self, *, space_id: int, conn=None) -> set[str]:
        """Messages fenced by a correction/forget are not default context instructions."""
        with self.db.connect(conn) as connection:
            rows = connection.execute(
                """
                SELECT source_message_ids_json FROM assistant_memory_suppressions
                WHERE workspace_id=%s AND principal_id=%s AND (
                    scope_kind='user' OR (scope_kind='space' AND scope_id=%s)
                )
                """,
                (self.workspace_id, self.principal_id, str(space_id)),
            ).fetchall()
        values: set[str] = set()
        for row in rows:
            values.update(
                str(value) for value in (row["source_message_ids_json"] or [])
            )
        return values

    def forget_receipt_valid(
        self, *, operation_key: str, memory_id: str, version: int, space_id: int
    ) -> bool:
        """Confirm a completed forget operation without treating its old text as knowledge."""
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT r.operation, r.result_json, m.status, m.version,
                       m.scope_kind, m.scope_id, m.text
                FROM assistant_mutation_receipts r
                JOIN assistant_memories m ON m.id=%s AND m.principal_id=r.principal_id
                WHERE r.operation_key=%s AND r.workspace_id=%s AND r.principal_id=%s
                """,
                (memory_id, operation_key, self.workspace_id, self.principal_id),
            ).fetchone()
        if row is None or str(row["operation"]) != "memory_forget":
            return False
        try:
            receipt = row["result_json"]
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        in_scope = str(row["scope_kind"]) == "user" or (
            str(row["scope_kind"]) == "space" and str(row["scope_id"]) == str(space_id)
        )
        return (
            in_scope
            and str(row["status"]) == "forgotten"
            and str(row["text"]) == ""
            and int(row["version"]) == version
            and str(receipt.get("id")) == memory_id
            and receipt.get("status") == "forgotten"
            and receipt.get("text") == ""
            and receipt.get("source_excerpt", "") == ""
            and receipt.get("version") == version
        )

    def dependency_refs_for_source_messages(
        self, message_ids: list[str], *, space_id: int
    ) -> list[str]:
        wanted = set(message_ids)
        if not wanted:
            return []
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, version, source_message_ids_json FROM assistant_memories
                WHERE workspace_id=%s AND principal_id=%s AND status='active' AND (
                    scope_kind='user' OR (scope_kind='space' AND scope_id=%s)
                )
                """,
                (self.workspace_id, self.principal_id, str(space_id)),
            ).fetchall()
        return [
            f"memory:{row['id']}:{int(row['version'])}"
            for row in rows
            if wanted.intersection((row["source_message_ids_json"] or []))
        ]

    def validate_dependency_refs(
        self, refs: list[str], *, space_id: int, conn=None
    ) -> dict[str, Any]:
        stale: list[str] = []
        current: list[str] = []
        for ref in refs:
            parts = str(ref).split(":")
            if len(parts) != 3 or parts[0] != "memory" or not parts[2].isdigit():
                stale.append(str(ref))
                continue
            try:
                memory = self.get(parts[1], conn=conn)
            except KeyError:
                stale.append(str(ref))
                continue
            in_scope = memory["scope_kind"] == "user" or (
                memory["scope_kind"] == "space"
                and str(memory["scope_id"]) == str(space_id)
            )
            valid_time = self._is_currently_valid(memory)
            expected_version = int(parts[2])
            if (
                not in_scope
                or memory["status"] != "active"
                or not valid_time
                or int(memory["version"]) != expected_version
            ):
                stale.append(str(ref))
            else:
                current.append(str(ref))
        return {
            "valid": not stale,
            "current": current,
            "stale": stale,
            "memory_epoch": self.current_epoch(conn=conn),
        }

    @staticmethod
    def dependency_ref(memory: dict[str, Any]) -> str:
        return f"memory:{memory['id']}:{int(memory['version'])}"

    def project(self, *, memory_id: str, version: int, job: dict) -> dict[str, Any]:
        if self.provider is None:
            raise RuntimeError("memory_embedding_unavailable")
        self._check_job_payload(job, memory_id, version, "memory_index")
        with self.db.connect(read_only=True) as c:
            row = c.execute(
                "SELECT * FROM assistant_memories WHERE workspace_id=%s AND principal_id=%s AND id=%s",
                (self.workspace_id, self.principal_id, memory_id),
            ).fetchone()
        if row is None or row["status"] != "active" or row["version"] != version:
            return {"status": "stale", "version": version}
        text = unicodedata.normalize("NFKC", row["text"])
        text_hash = self._content_hash(text)
        # Provider work is deliberately outside any connection/transaction.
        vector = _validate_vector(self.provider.embed_documents([text])[0], 512)
        with self._memory_write_transaction(job=job) as c:
            current = c.execute(
                "SELECT * FROM assistant_memories WHERE workspace_id=%s AND principal_id=%s AND id=%s FOR UPDATE",
                (self.workspace_id, self.principal_id, memory_id),
            ).fetchone()
            if (
                current is None
                or current["status"] != "active"
                or current["version"] != version
                or current["change_epoch"] != row["change_epoch"]
                or self._content_hash(unicodedata.normalize("NFKC", current["text"]))
                != text_hash
            ):
                raise AssistantConflict("memory_projection_stale")
            self.profile.register(c)
            c.execute(
                "INSERT INTO memory_embeddings (workspace_id,memory_id,profile_id,memory_version,change_epoch,embedding_text_hash,embedding,updated_at) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,clock_timestamp()) ON CONFLICT(memory_id,profile_id) DO UPDATE SET "
                "memory_version=excluded.memory_version,change_epoch=excluded.change_epoch,embedding_text_hash=excluded.embedding_text_hash,embedding=excluded.embedding,updated_at=excluded.updated_at",
                (
                    self.workspace_id,
                    memory_id,
                    self.profile.profile_id,
                    version,
                    current["change_epoch"],
                    text_hash,
                    vector,
                ),
            )
            c.execute(
                "UPDATE assistant_memories SET last_projected_version=%s WHERE workspace_id=%s AND id=%s",
                (version, self.workspace_id, memory_id),
            )
            self._activate_profile_if_covered(c)
            job_transition(
                c,
                self.db.context,
                job["id"],
                job["lease_owner"],
                job["lease_epoch"],
                action="complete",
            )
        return {
            "status": "ready",
            "version": version,
            "embedding_profile": self.profile.profile_id,
        }

    def _check_job_payload(self, job, memory_id, version, kind):
        if (
            job["workspace_id"] != self.workspace_id
            or job["principal_id"] != self.principal_id
            or job["kind"] != kind
            or job["payload_json"].get("memory_id") != memory_id
            or job["payload_json"].get("version") != version
        ):
            raise AssistantConflict("memory_job_payload_mismatch")

    def _activate_profile_if_covered(self, c):
        missing = c.execute(
            "SELECT count(*) AS n FROM assistant_memories m WHERE m.workspace_id=%s AND m.principal_id=%s AND m.status='active' "
            "AND NOT EXISTS(SELECT 1 FROM memory_embeddings e WHERE e.workspace_id=m.workspace_id AND e.memory_id=m.id AND e.profile_id=%s "
            "AND e.memory_version=m.version AND e.change_epoch=m.change_epoch AND e.embedding_text_hash=encode(sha256(convert_to(normalize(m.text,NFKC),'UTF8')),'hex'))",
            (self.workspace_id, self.principal_id, self.profile.profile_id),
        ).fetchone()["n"]
        if not missing:
            c.execute(
                "INSERT INTO assistant_runtime_state(workspace_id,principal_id,key,value,updated_at,embedding_domain,embedding_profile_id) VALUES(%s,%s,'active_profile:memory',%s,clock_timestamp(),'memory',%s) "
                "ON CONFLICT(workspace_id,principal_id,key) DO UPDATE SET value=excluded.value,embedding_profile_id=excluded.embedding_profile_id,updated_at=excluded.updated_at",
                (
                    self.workspace_id,
                    self.principal_id,
                    self.profile.profile_id,
                    self.profile.profile_id,
                ),
            )

    def purge(self, *, memory_id: str, version: int, job: dict) -> dict[str, Any]:
        self._check_job_payload(job, memory_id, version, "memory_purge")
        with self._memory_write_transaction(job=job) as c:
            row = c.execute(
                "SELECT status,version FROM assistant_memories WHERE workspace_id=%s AND principal_id=%s AND id=%s FOR UPDATE",
                (self.workspace_id, self.principal_id, memory_id),
            ).fetchone()
            if row is None or row["status"] != "forgotten" or row["version"] != version:
                raise AssistantConflict("memory_purge_stale")
            self._clear_projection(c, memory_id)
            c.execute(
                "UPDATE assistant_memories SET last_projected_version=%s WHERE workspace_id=%s AND id=%s",
                (version, self.workspace_id, memory_id),
            )
            job_transition(
                c,
                self.db.context,
                job["id"],
                job["lease_owner"],
                job["lease_epoch"],
                action="complete",
            )
        return {"status": "purged", "version": version}

    def apply_extracted(
        self,
        proposal: dict[str, Any],
        *,
        source_message_ids: list[str],
        expected_epoch: int,
        operation_key: str,
        expected_auto_generation: int | None = None,
        publish_guard: Callable[[Any], None] | None = None,
        job: dict | None = None,
        _connection: Any | None = None,
        expected_run_id: str | None = None,
        expected_run_epoch: int | None = None,
    ) -> dict[str, Any] | None:
        proposal_scope = str(proposal.get("scope_kind") or "space")
        proposal_scope_id = (
            "" if proposal_scope == "user" else str(proposal.get("scope_id") or "")
        )
        self._validate_scope(
            proposal_scope,
            int(proposal_scope_id) if proposal_scope_id else None,
            conn=_connection,
        )
        op = str(proposal.get("op") or "no_change")
        if op not in {"add", "revise"}:
            return None
        scope_kind = proposal_scope
        scope_id = int(proposal_scope_id) if proposal_scope_id else None
        proposal_text = self._validate_text(str(proposal.get("text") or ""))
        proposal_subject = self._validate_subject(
            str(proposal.get("subject_key") or "")
        )
        if (
            proposal.get("kind") == "decision"
            and proposal.get("source_excerpt")
            and not plausible_personal_excerpt(
                str(proposal["source_excerpt"]), "decision"
            )
        ):
            return None
        transaction = (
            self._memory_write_transaction(
                operation_key=operation_key,
                expected_run_id=expected_run_id,
                expected_epoch=expected_run_epoch,
                job=job,
            )
            if _connection is None
            else nullcontext(_connection)
        )
        with transaction as connection:
            receipt = self._receipt(connection, operation_key)
            if receipt is not None:
                return receipt
            if publish_guard is not None:
                publish_guard(connection)
            current_policy = self._auto_policy(connection)
            policy = {
                "auto_memory_enabled": "1" if current_policy["enabled"] else "0",
                "auto_memory_generation": str(current_policy["generation"]),
            }
            if policy.get("auto_memory_enabled", "1") == "0" or (
                expected_auto_generation is not None
                and int(policy.get("auto_memory_generation", "0"))
                != expected_auto_generation
            ):
                return None
            # Exact content suppression also applies to newly queued extraction, not
            # only jobs whose epoch predates a retract/forget. No semantic matching.
            if connection.execute(
                "SELECT 1 FROM assistant_memory_suppressions WHERE workspace_id=%s AND principal_id=%s AND ("
                "(scope_kind=%s AND scope_id=%s AND content_hash=%s) OR source_message_ids_json ?| %s)",
                (
                    self.workspace_id,
                    self.principal_id,
                    proposal_scope,
                    proposal_scope_id,
                    self._content_hash(proposal_text),
                    source_message_ids,
                ),
            ).fetchone():
                return None
            if self._current_epoch(connection) != expected_epoch:
                suppressed = connection.execute(
                    """
                    SELECT scope_kind, scope_id, subject_key, content_hash,
                           source_message_ids_json
                    FROM assistant_memory_suppressions WHERE workspace_id=%s AND principal_id=%s
                    """,
                    (self.workspace_id, self.principal_id),
                ).fetchall()
                protected = connection.execute(
                    """
                    SELECT source_message_ids_json FROM assistant_memories
                    WHERE workspace_id=%s AND principal_id=%s AND status='active' AND user_edited=true
                      AND scope_kind=%s AND scope_id=%s
                    """,
                    (
                        self.workspace_id,
                        self.principal_id,
                        proposal_scope,
                        proposal_scope_id,
                    ),
                ).fetchall()
                for row in protected:
                    protected_ids = set((row["source_message_ids_json"] or []))
                    if protected_ids.intersection(source_message_ids):
                        return None
                proposal_hash = self._content_hash(proposal_text)
                for row in suppressed:
                    blocked_ids = set((row["source_message_ids_json"] or []))
                    same_fact = (
                        str(row["scope_kind"]) == proposal_scope
                        and str(row["scope_id"] or "") == proposal_scope_id
                        and str(row["subject_key"]) == proposal_subject
                        and str(row["content_hash"]) == proposal_hash
                    )
                    if blocked_ids.intersection(source_message_ids) or same_fact:
                        return None
            if op == "revise" and proposal.get("target_memory_id"):
                target = connection.execute(
                    "SELECT * FROM assistant_memories WHERE id=%s AND workspace_id=%s AND principal_id=%s FOR UPDATE",
                    (
                        str(proposal["target_memory_id"]),
                        self.workspace_id,
                        self.principal_id,
                    ),
                ).fetchone()
                if target is None:
                    return None
                if (
                    str(target["scope_kind"]) != scope_kind
                    or str(target["scope_id"] or "") != proposal_scope_id
                    or str(target["status"]) != "active"
                ):
                    return None
                if bool(target["pinned"]) or bool(target["user_edited"]):
                    return None
                if int(proposal.get("expected_version") or 0) != int(target["version"]):
                    return None
                return self.correct(
                    str(target["id"]),
                    text=proposal_text,
                    expected_version=int(
                        proposal.get("expected_version") or target["version"]
                    ),
                    operation_key=operation_key,
                    subject_key=proposal_subject or str(target["subject_key"]),
                    kind=str(proposal.get("kind") or target["kind"]),
                    valid_from=proposal.get("valid_from", _UNSET),
                    expires_at=proposal.get("expires_at", _UNSET),
                    validity_note=proposal.get("validity_note", _UNSET),
                    validity_timezone=proposal.get("validity_timezone", _UNSET),
                    source_message_ids=source_message_ids,
                    source_excerpt=str(proposal.get("source_excerpt") or ""),
                    stated_text=proposal.get("source_excerpt"),
                    stated_at=proposal.get("stated_at"),
                    _notification_causes={"job_id": job["id"]} if job else {},
                    _actor="assistant",
                    _user_edited=False,
                    _connection=connection,
                )
            if op == "revise":
                return None
            return self._save_extracted(
                connection,
                text=proposal_text,
                _notification_causes={"job_id": job["id"]} if job else {},
                subject_key=proposal_subject,
                kind=str(proposal.get("kind") or "context"),
                scope_kind=scope_kind,
                scope_id=scope_id,
                operation_key=operation_key,
                source_message_ids=source_message_ids,
                source_excerpt=str(proposal.get("source_excerpt") or ""),
                valid_from=proposal.get("valid_from"),
                expires_at=proposal.get("expires_at"),
                validity_note=str(proposal.get("validity_note") or ""),
                validity_timezone=proposal.get("validity_timezone"),
                stated_text=proposal.get("source_excerpt"),
                stated_at=proposal.get("stated_at"),
            )

    def _save_extracted(self, connection: Any, **values: Any) -> dict[str, Any]:
        # save_explicit performs duplicate lookup, formal write, outbox enqueue,
        # and receipt in one transaction. A duplicate retains its existing origin,
        # edit protection, and pin rather than being converted to an extracted fact.
        return self.save_explicit(
            **values,
            origin="extracted",
            _initial_status="active",
            _connection=connection,
        )

    def _validate_scope(
        self, scope_kind: str, scope_id: int | None, *, conn=None
    ) -> str:
        if scope_kind == "user":
            if scope_id not in (None, ""):
                raise ValueError("invalid_memory_scope")
            return ""
        if scope_kind != "space" or type(scope_id) is not int or scope_id < 1:
            raise ValueError("invalid_memory_scope")
        with self.db.connect(conn) as c:
            row = c.execute(
                "SELECT id FROM assistant_spaces WHERE workspace_id=%s AND principal_id=%s AND id=%s AND enabled=true",
                (self.workspace_id, self.principal_id, scope_id),
            ).fetchone()
        if row is None:
            raise ValueError("invalid_memory_scope")
        return str(scope_id)

    def _validate_sources(self, c, ids, scope_kind, scope_id):
        if not ids:
            return
        found = c.execute(
            "SELECT m.id,t.space_id FROM assistant_messages m JOIN assistant_threads t ON (t.workspace_id,t.id)=(m.workspace_id,m.thread_id) "
            "WHERE m.workspace_id=%s AND t.principal_id=%s AND m.id=ANY(%s)",
            (self.workspace_id, self.principal_id, ids),
        ).fetchall()
        if {r["id"] for r in found} != set(ids) or (
            scope_kind == "space"
            and any(str(r["space_id"]) != str(scope_id) for r in found)
        ):
            raise AssistantConflict("memory_source_out_of_scope")

    @staticmethod
    def _validate_text(text: str) -> str:
        clean = " ".join(text.split())
        if not clean or len(clean) > 400:
            raise ValueError("invalid_memory_text")
        return clean

    @staticmethod
    def _validate_subject(value: str) -> str:
        clean = "_".join(value.strip().lower().split())
        if not clean or len(clean) > 120:
            raise ValueError("invalid_subject_key")
        return clean

    @staticmethod
    def _validate_validity(
        valid_from: str | None | object,
        expires_at: str | None | object,
        validity_note: str | object,
        validity_timezone: str | None | object,
    ) -> tuple[str | None, str | None, str, str | None]:
        if (
            valid_from is _UNSET
            or expires_at is _UNSET
            or validity_note is _UNSET
            or validity_timezone is _UNSET
        ):
            raise ValueError("invalid_memory_validity")
        note = " ".join(str(validity_note or "").split())[:400]
        timezone_name = str(validity_timezone).strip() if validity_timezone else None
        if timezone_name and timezone_name != "explicit_offset":
            try:
                ZoneInfo(timezone_name)
            except ZoneInfoNotFoundError as exc:
                raise ValueError("invalid_memory_timezone") from exc

        def normalize(value: str | None | object) -> str | None:
            if value in {None, ""}:
                return None
            raw = str(value).strip().replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(raw)
            except ValueError as exc:
                raise ValueError("invalid_memory_time") from exc
            if parsed.tzinfo is None:
                raise ValueError("memory_time_requires_timezone")
            return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")

        start = normalize(valid_from)
        end = normalize(expires_at)
        if start and end and end <= start:
            raise ValueError("invalid_memory_time_range")
        if (start or end) and not timezone_name:
            timezone_name = "explicit_offset"
        return start, end, note, timezone_name

    @staticmethod
    def _is_currently_valid(memory: dict[str, Any], *, now: str | None = None) -> bool:
        def at(value):
            parsed = (
                value
                if isinstance(value, datetime)
                else datetime.fromisoformat(value.replace("Z", "+00:00"))
            )
            if parsed.tzinfo is None:
                raise ValueError("memory_time_requires_timezone")
            return parsed

        current = at(now) if now else datetime.now(timezone.utc)
        return (
            not memory.get("valid_from") or at(memory["valid_from"]) <= current
        ) and (not memory.get("expires_at") or at(memory["expires_at"]) > current)

    def _suppress(
        self,
        connection: Any,
        row: Any,
        *,
        memory_epoch: int,
        content_hash: str,
    ) -> None:
        source_ids = row["source_message_ids_json"] or []
        connection.execute(
            """
            INSERT INTO assistant_memory_suppressions(
                workspace_id, principal_id, scope_kind, scope_id, subject_key, content_hash,
                source_message_ids_json, memory_epoch, created_at
            ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(principal_id, scope_kind, scope_id, subject_key, content_hash)
            DO UPDATE SET memory_epoch=excluded.memory_epoch,
                          source_message_ids_json=excluded.source_message_ids_json,
                          created_at=excluded.created_at
            """,
            (
                self.workspace_id,
                self.principal_id,
                row["scope_kind"],
                row["scope_id"],
                row["subject_key"],
                content_hash,
                Jsonb(source_ids),
                memory_epoch,
                utc_now(),
            ),
        )

    def _enqueue_index(
        self,
        connection: Any,
        memory_id: str,
        version: int,
        scope_kind: str,
        scope_id: str,
    ) -> None:
        self.store.enqueue_job(
            connection,
            kind="memory_index",
            dedupe_key=f"memory_index:{memory_id}:{version}",
            payload={
                "memory_id": memory_id,
                "version": version,
                "scope_key": self._scope_key(scope_kind, scope_id),
            },
        )

    @staticmethod
    def _scope_key(scope_kind: str, scope_id: str) -> str:
        return "user" if scope_kind == "user" else f"space:{scope_id}"

    @staticmethod
    def _content_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _fts_replace(self, connection: Any, memory_id: str, text: str) -> None:
        tokens = self.tokenizer.document(text)
        connection.execute(
            "UPDATE assistant_memories SET tokenized_text=%s,search_vector=to_tsvector('simple',%s) WHERE workspace_id=%s AND principal_id=%s AND id=%s",
            (tokens, tokens, self.workspace_id, self.principal_id, memory_id),
        )

    def _clear_projection(self, connection, memory_id):
        self._fts_replace(connection, memory_id, "")
        connection.execute(
            "DELETE FROM memory_embeddings WHERE workspace_id=%s AND memory_id=%s",
            (self.workspace_id, memory_id),
        )
        # Only owned pages in the original suppression scope are eligible.
        # Use persisted construction snapshots even after formal links/blocks
        # have been rewritten. A narrow undo has no message-level suppression.
        connection.execute(
            "DELETE FROM wiki_windows w USING assistant_wiki_pages p WHERE w.workspace_id=%s "
            "AND (p.workspace_id,p.id)=(w.workspace_id,w.page_id) AND p.principal_id=%s "
            "AND w.dependency_versions @> %s",
            (
                self.workspace_id,
                self.principal_id,
                Jsonb({"memories": [{"id": memory_id}]}),
            ),
        )
        row = connection.execute(
            "SELECT scope_kind,scope_id,source_message_ids_json FROM assistant_memories WHERE workspace_id=%s AND principal_id=%s AND id=%s",
            (self.workspace_id, self.principal_id, memory_id),
        ).fetchone()
        if row and row["source_message_ids_json"]:
            # A genuine forget persists these IDs in the same scope's suppression.
            # undo_created retains source IDs on the fact but adds no such IDs.
            connection.execute(
                "DELETE FROM wiki_windows w USING assistant_wiki_pages p WHERE w.workspace_id=%s "
                "AND (p.workspace_id,p.id)=(w.workspace_id,w.page_id) AND p.principal_id=%s "
                "AND (%s='user' OR p.space_id::text=%s) AND EXISTS ("
                "SELECT 1 FROM assistant_memory_suppressions s, jsonb_array_elements_text(s.source_message_ids_json) AS message(id) "
                "WHERE s.workspace_id=%s AND s.principal_id=%s AND s.scope_kind=%s AND s.scope_id=%s "
                "AND message.id=ANY(%s) AND (w.dependency_versions->'messages') ? message.id)",
                (
                    self.workspace_id,
                    self.principal_id,
                    row["scope_kind"],
                    row["scope_id"],
                    self.workspace_id,
                    self.principal_id,
                    row["scope_kind"],
                    row["scope_id"],
                    row["source_message_ids_json"],
                ),
            )

    def _write_change(
        self,
        connection: Any,
        current: dict[str, Any],
        *,
        operation: str,
        before: dict[str, Any] | None,
        actor: str,
        memory_epoch: int,
        operation_key: str,
        notification_causes: dict | None = None,
        source_type: str = "manual",
    ) -> None:
        change = connection.execute(
            """
            INSERT INTO assistant_memory_changes(
                workspace_id, memory_id, version, operation, before_json, after_json, actor, created_at
                , memory_epoch
            ) VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id,created_at
            """,
            (
                self.workspace_id,
                current["id"],
                current["version"],
                operation,
                Jsonb(before) if before is not None else None,
                Jsonb(current),
                actor,
                utc_now(),
                memory_epoch,
            ),
        ).fetchone()
        from shiliu.assistant.notifications import record

        if operation != "creation_retracted":
            record(
                connection,
                self.db.context,
                event_key=f"memory-change:{change['id']}",
                origin_type="memory_change",
                origin_id=change["id"],
                space_id=None
                if current["scope_kind"] == "user"
                else int(current["scope_id"]),
                source_type=source_type,
                created_at=change["created_at"],
                cause_refs={
                    "operation_key": operation_key,
                    "source_message_ids": current.get("source_message_ids", []),
                    **(notification_causes or {}),
                },
                read_at=change["created_at"] if actor == "user" else None,
            )

    def _receipt(self, connection: Any, operation_key: str) -> dict[str, Any] | None:
        if not operation_key.strip():
            raise ValueError("operation_key_required")
        row = connection.execute(
            "SELECT result_json FROM assistant_mutation_receipts WHERE operation_key=%s AND workspace_id=%s AND principal_id=%s",
            (operation_key, self.workspace_id, self.principal_id),
        ).fetchone()
        return row["result_json"] if row else None

    def _save_receipt(
        self,
        connection: Any,
        operation_key: str,
        operation: str,
        result: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO assistant_mutation_receipts(
                workspace_id, operation_key, principal_id, operation, result_json, created_at
            ) VALUES(%s, %s, %s, %s, %s, %s)
            """,
            (
                self.workspace_id,
                operation_key,
                self.principal_id,
                operation,
                Jsonb(result),
                utc_now(),
            ),
        )

    def _increment_epoch(self, connection: Any) -> int:
        row = connection.execute(
            "INSERT INTO assistant_runtime_state(workspace_id,principal_id,key,value,updated_at) VALUES(%s,%s,'memory_epoch','1',clock_timestamp()) "
            "ON CONFLICT(workspace_id,principal_id,key) DO UPDATE SET value=(assistant_runtime_state.value::bigint+1)::text,updated_at=excluded.updated_at RETURNING value",
            (self.workspace_id, self.principal_id),
        ).fetchone()
        connection.execute(
            "UPDATE workspace_guards SET dependency_epoch=dependency_epoch+1 WHERE workspace_id=%s",
            (self.workspace_id,),
        )
        return int(row["value"])

    def _current_epoch(self, connection: Any) -> int:
        row = connection.execute(
            "SELECT value FROM assistant_runtime_state WHERE workspace_id=%s AND principal_id=%s AND key='memory_epoch'",
            (self.workspace_id, self.principal_id),
        ).fetchone()
        return int(row["value"]) if row else 0

    @staticmethod
    def _public(value: dict[str, Any]) -> dict[str, Any]:
        value.pop("tokenized_text", None)
        value.pop("search_vector", None)
        value = row_dto(
            value,
            timestamps={
                "valid_from",
                "expires_at",
                "created_at",
                "updated_at",
            }.intersection(value),
        )
        value["time_context"] = value.pop("time_context_json", {}) or {}
        if value.get("status") == "forgotten":
            value["time_context"] = {}
        value["source_message_ids"] = value.pop("source_message_ids_json", [])
        value["pinned"] = bool(value["pinned"])
        value["user_edited"] = bool(value["user_edited"])
        return value
