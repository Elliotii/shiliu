from __future__ import annotations

import hashlib
import json
import re
import uuid
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from typing import Any, Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shiliu.assistant.dependencies import Mem0SemanticIndex
from shiliu.assistant.memory_policy import (
    anchored_validity, cancels_time, clears_time, keeps_time, requests_time_change, time_phrase,
)
from shiliu.assistant.store import AssistantConflict, AssistantRunStore
from shiliu.db import Database, utc_now


MEMORY_KINDS = {"preference", "constraint", "decision", "context"}
_UNSET = object()


class MemoryService:
    def __init__(
        self,
        db: Database,
        *,
        backend: Mem0SemanticIndex | None = None,
        principal_id: str = "local_operator",
    ) -> None:
        self.db = db
        self.backend = backend
        self.principal_id = principal_id

    def auto_enabled(self) -> bool:
        return self.auto_policy()["enabled"]

    def auto_policy(self) -> dict[str, Any]:
        with self.db.connect() as connection:
            rows = connection.execute("SELECT key,value FROM assistant_runtime_state WHERE key IN ('auto_memory_enabled','auto_memory_generation')").fetchall()
        state = {str(row["key"]): str(row["value"]) for row in rows}
        return {"enabled": state.get("auto_memory_enabled", "1") != "0",
                "generation": int(state.get("auto_memory_generation", "0"))}

    def set_auto_enabled(self, enabled: bool) -> bool:
        with self._memory_write_transaction() as connection:
            rows = connection.execute("SELECT key,value FROM assistant_runtime_state WHERE key IN ('auto_memory_enabled','auto_memory_generation')").fetchall()
            state = {str(row["key"]): str(row["value"]) for row in rows}
            previous = state.get("auto_memory_enabled", "1") != "0"
            generation = int(state.get("auto_memory_generation", "0")) + int(previous != enabled)
            connection.execute(
                "INSERT INTO assistant_runtime_state(key,value,updated_at) VALUES('auto_memory_enabled',?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                ("1" if enabled else "0", utc_now()),
            )
            connection.execute(
                "INSERT INTO assistant_runtime_state(key,value,updated_at) VALUES('auto_memory_generation',?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                (str(generation), utc_now()),
            )
        return enabled

    @contextmanager
    def _memory_write_transaction(self) -> Iterator[Any]:
        """Serialize the short authoritative Memory mutation transaction."""
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            yield connection

    def list(self, *, space_id: int | None = None, include_inactive: bool = False) -> list[dict[str, Any]]:
        conditions = ["principal_id=?"]
        params: list[Any] = [self.principal_id]
        if not include_inactive:
            conditions.append("status IN ('active','needs_review')")
        if space_id is not None:
            conditions.append("(scope_kind='user' OR (scope_kind='space' AND scope_id=?))")
            params.append(str(space_id))
        with self.db.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM assistant_memories WHERE {' AND '.join(conditions)}
                ORDER BY pinned DESC, updated_at DESC, id
                """,
                params,
            ).fetchall()
        items = [self._public(dict(row)) for row in rows]
        source_ids = [str(item["source_message_ids"][-1]) for item in items if item["source_message_ids"]]
        if source_ids:
            with self.db.connect() as connection:
                placeholders = ",".join("?" for _ in source_ids)
                sources = connection.execute(
                    f"SELECT id,thread_id FROM assistant_messages WHERE id IN ({placeholders})", source_ids
                ).fetchall()
            thread_by_message = {str(row["id"]): str(row["thread_id"]) for row in sources}
            for item in items:
                if item["source_message_ids"]:
                    item["source_thread_id"] = thread_by_message.get(str(item["source_message_ids"][-1]))
        return items

    def get(self, memory_id: str) -> dict[str, Any]:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM assistant_memories WHERE id=? AND principal_id=?",
                (memory_id, self.principal_id),
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
        _initial_status: str = "active",
        _connection: Any | None = None,
    ) -> dict[str, Any]:
        clean_text = self._validate_text(text)
        clean_subject = self._validate_subject(subject_key)
        clean_scope_id = self._validate_scope(scope_kind, scope_id)
        if kind not in MEMORY_KINDS:
            raise ValueError("invalid_memory_kind")
        if origin not in {"explicit", "extracted"}:
            raise ValueError("invalid_memory_origin")
        if _initial_status not in {"active", "needs_review"}:
            raise ValueError("invalid_memory_status")
        if stated_text is not None and not expires_at:
            stated_bounds = anchored_validity(stated_text, stated_at or utc_now())
            if stated_bounds is None and not clears_time(stated_text):
                raise ValueError("memory_time_needs_review")
            resolved = anchored_validity(clean_text, stated_at or utc_now())
            if resolved is None:
                raise ValueError("memory_time_needs_review")
            if resolved:
                valid_from = None
                expires_at = resolved["expires_at"]
                validity_note = resolved["validity_note"]
                validity_timezone = resolved["validity_timezone"]
            elif not clears_time(clean_text) and stated_bounds != {}:
                # The request names a time but the proposed fact does not.
                # Do not apply another fact's date or save this as timeless.
                raise ValueError("memory_time_needs_review")
        valid_from, expires_at, validity_note, validity_timezone = self._validate_validity(
            valid_from, expires_at, validity_note, validity_timezone
        )
        now = utc_now()
        memory_id = f"amem_{uuid.uuid4().hex}"
        transaction = (
            self._memory_write_transaction()
            if _connection is None
            else nullcontext(_connection)
        )
        with transaction as connection:
            receipt = self._receipt(connection, operation_key)
            if receipt is not None:
                return receipt
            duplicate = connection.execute(
                """
                SELECT * FROM assistant_memories
                WHERE principal_id=? AND scope_kind=? AND scope_id=?
                  AND text=? AND status IN ('active','needs_review')
                  AND COALESCE(valid_from, '')=? AND COALESCE(expires_at, '')=?
                  AND validity_note=? AND COALESCE(validity_timezone, '')=?
                ORDER BY version DESC LIMIT 1
                """,
                (
                    self.principal_id, scope_kind, clean_scope_id, clean_text,
                    valid_from or "", expires_at or "", validity_note,
                    validity_timezone or "",
                ),
            ).fetchone()
            if duplicate is not None:
                merged_source_ids = sorted({
                    *json.loads(str(duplicate["source_message_ids_json"] or "[]")),
                    *(source_message_ids or []),
                })
                merged_excerpt = str(duplicate["source_excerpt"] or "") or source_excerpt[:1000]
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
                            user_edited=1, pinned=?, version=?, backend_id=NULL,
                            source_message_ids_json=?, source_excerpt=?,
                            change_epoch=?, updated_at=? WHERE id=? AND version=?
                        """,
                        (
                            int(pinned or bool(duplicate["pinned"])), next_version,
                            json.dumps(merged_source_ids), merged_excerpt,
                            epoch, now, duplicate["id"], duplicate["version"],
                        ),
                    )
                    current = connection.execute(
                        "SELECT * FROM assistant_memories WHERE id=?", (duplicate["id"],)
                    ).fetchone()
                    result = self._public(dict(current))
                    self._write_change(
                        connection, result, operation="adopted", before=before,
                        actor="user", memory_epoch=epoch,
                    )
                    self._enqueue_index(
                        connection, str(duplicate["id"]), next_version,
                        scope_kind, clean_scope_id,
                        old_backend_id=str(duplicate["backend_id"]) if duplicate["backend_id"] else None,
                    )
                    self._save_receipt(connection, operation_key, "memory_save", result)
                    return result
                if merged_source_ids != json.loads(str(duplicate["source_message_ids_json"] or "[]")):
                    connection.execute(
                        """
                        UPDATE assistant_memories SET source_message_ids_json=?, source_excerpt=?
                        WHERE id=?
                        """,
                        (json.dumps(merged_source_ids), merged_excerpt, duplicate["id"]),
                    )
                    duplicate = connection.execute(
                        "SELECT * FROM assistant_memories WHERE id=?", (duplicate["id"],)
                    ).fetchone()
                result = self._public(dict(duplicate))
                self._save_receipt(connection, operation_key, "memory_save", result)
                return result
            epoch = self._increment_epoch(connection)
            connection.execute(
                """
                INSERT INTO assistant_memories(
                    id, principal_id, scope_kind, scope_id, kind, text, subject_key,
                    origin, source_message_ids_json, source_excerpt, status, version,
                    pinned, user_edited, valid_from, expires_at, validity_note,
                    validity_timezone, change_epoch, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id, self.principal_id, scope_kind, clean_scope_id, kind,
                    clean_text, clean_subject, origin, json.dumps(source_message_ids or []),
                    source_excerpt[:1000], _initial_status, int(pinned), int(origin == "explicit"),
                    valid_from, expires_at, validity_note, validity_timezone, epoch, now, now,
                ),
            )
            current = connection.execute(
                "SELECT * FROM assistant_memories WHERE id=?", (memory_id,)
            ).fetchone()
            result = self._public(dict(current))
            self._write_change(
                connection, result, operation="created", before=None,
                actor="user" if origin == "explicit" else "assistant", memory_epoch=epoch,
            )
            if _initial_status == "active":
                self._fts_replace(connection, memory_id, clean_text)
                self._enqueue_index(connection, memory_id, 1, scope_kind, clean_scope_id)
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
        _actor: str = "user",
        _user_edited: bool = True,
        _connection: Any | None = None,
    ) -> dict[str, Any]:
        clean_text = self._validate_text(text)
        now = utc_now()
        transaction = (
            self._memory_write_transaction()
            if _connection is None
            else nullcontext(_connection)
        )
        with transaction as connection:
            receipt = self._receipt(connection, operation_key)
            if receipt is not None:
                return receipt
            row = connection.execute(
                "SELECT * FROM assistant_memories WHERE id=? AND principal_id=?",
                (memory_id, self.principal_id),
            ).fetchone()
            if row is None:
                raise KeyError(memory_id)
            before = self._public(dict(row))
            if int(row["version"]) != expected_version:
                raise AssistantConflict("memory_version_conflict")
            if str(row["status"]) == "forgotten":
                raise AssistantConflict("memory_forgotten")
            next_subject = self._validate_subject(subject_key or str(row["subject_key"]))
            next_kind = kind or str(row["kind"])
            if next_kind not in MEMORY_KINDS:
                raise ValueError("invalid_memory_kind")
            time_words = stated_text if stated_text is not None else clean_text
            if expires_at is _UNSET and valid_from is _UNSET:
                if cancels_time(time_words, clean_text):
                    valid_from, expires_at = None, None
                    validity_note, validity_timezone = "", None
                elif not keeps_time(time_words):
                    if stated_text is not None and anchored_validity(time_words, stated_at or now) is None:
                        raise ValueError("memory_time_needs_review")
                    resolved = anchored_validity(clean_text, stated_at or now)
                    if resolved is None:
                        raise ValueError("memory_time_needs_review")
                    if not resolved and stated_text is not None and requests_time_change(time_words):
                        raise ValueError("memory_time_needs_review")
                    if resolved and (
                        time_phrase(clean_text) != time_phrase(str(row["text"]))
                        or not row["expires_at"]
                        or (stated_text is not None and requests_time_change(time_words))
                    ):
                        valid_from = None
                        expires_at = resolved["expires_at"]
                        validity_note = resolved["validity_note"]
                        validity_timezone = resolved["validity_timezone"]
            elif expires_at is None:
                if valid_from is _UNSET:
                    valid_from = None
                if validity_note is _UNSET:
                    validity_note = ""
                if validity_timezone is _UNSET:
                    validity_timezone = None
            elif expires_at is not _UNSET:
                if validity_note is _UNSET:
                    validity_note = ""
                if validity_timezone is _UNSET:
                    validity_timezone = "explicit_offset"
            next_valid_from, next_expires_at, next_validity_note, next_validity_timezone = (
                self._validate_validity(
                    row["valid_from"] if valid_from is _UNSET else valid_from,
                    row["expires_at"] if expires_at is _UNSET else expires_at,
                    row["validity_note"] if validity_note is _UNSET else validity_note,
                    row["validity_timezone"] if validity_timezone is _UNSET else validity_timezone,
                )
            )
            next_source_message_ids = (
                json.loads(row["source_message_ids_json"] or "[]")
                if source_message_ids is _UNSET
                else list(dict.fromkeys(str(value) for value in source_message_ids))
            )
            next_source_excerpt = (
                str(row["source_excerpt"] or "")
                if source_excerpt is _UNSET
                else str(source_excerpt)[:1000]
            )
            next_version = expected_version + 1
            old_backend_id = row["backend_id"]
            epoch = self._increment_epoch(connection)
            self._suppress(
                connection,
                row,
                memory_epoch=epoch,
                content_hash=self._content_hash(str(row["text"])),
            )
            connection.execute(
                """
                UPDATE assistant_memories SET text=?, subject_key=?, kind=?, version=?,
                    status='active', user_edited=?, backend_id=NULL,
                    valid_from=?, expires_at=?, validity_note=?, validity_timezone=?,
                    source_message_ids_json=?, source_excerpt=?, change_epoch=?, updated_at=?
                WHERE id=? AND version=?
                """,
                (
                    clean_text, next_subject, next_kind, next_version, int(_user_edited),
                    next_valid_from, next_expires_at, next_validity_note,
                    next_validity_timezone,
                    json.dumps(next_source_message_ids, ensure_ascii=False),
                    next_source_excerpt, epoch, now, memory_id, expected_version,
                ),
            )
            current = connection.execute(
                "SELECT * FROM assistant_memories WHERE id=?", (memory_id,)
            ).fetchone()
            result = self._public(dict(current))
            self._write_change(
                connection, result, operation="corrected", before=before,
                actor=_actor, memory_epoch=epoch,
            )
            self._fts_replace(connection, memory_id, clean_text)
            self._enqueue_index(
                connection,
                memory_id,
                next_version,
                str(row["scope_kind"]),
                str(row["scope_id"]),
                old_backend_id=str(old_backend_id) if old_backend_id else None,
            )
            self._save_receipt(connection, operation_key, "memory_correct", result)
        return result

    def forget(
        self,
        memory_id: str,
        *,
        expected_version: int,
        operation_key: str,
        source_message_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._memory_write_transaction() as connection:
            receipt = self._receipt(connection, operation_key)
            if receipt is not None:
                return receipt
            row = connection.execute(
                "SELECT * FROM assistant_memories WHERE id=? AND principal_id=?",
                (memory_id, self.principal_id),
            ).fetchone()
            if row is None:
                raise KeyError(memory_id)
            if str(row["status"]) == "forgotten":
                result = self._public(dict(row))
                self._save_receipt(connection, operation_key, "memory_forget", result)
                return result
            if int(row["version"]) != expected_version:
                raise AssistantConflict("memory_version_conflict")
            before = self._public(dict(row))
            next_version = expected_version + 1
            epoch = self._increment_epoch(connection)
            row_for_suppression = dict(row)
            if source_message_ids:
                existing_source_ids = json.loads(row["source_message_ids_json"] or "[]")
                row_for_suppression["source_message_ids_json"] = json.dumps(
                    list(dict.fromkeys([
                        *(str(value) for value in existing_source_ids),
                        *(str(value) for value in source_message_ids),
                    ])),
                    ensure_ascii=False,
                )
            self._suppress(
                connection,
                row_for_suppression,
                memory_epoch=epoch,
                content_hash=self._content_hash(str(row["text"])),
            )
            connection.execute(
                """
                UPDATE assistant_memories SET status='forgotten', version=?, text='',
                    source_excerpt='', source_message_ids_json=?, backend_id=NULL,
                    change_epoch=?, updated_at=?
                WHERE id=? AND version=?
                """,
                (
                    next_version, row_for_suppression["source_message_ids_json"],
                    epoch, now, memory_id, expected_version,
                ),
            )
            connection.execute("DELETE FROM assistant_memories_fts WHERE memory_id=?", (memory_id,))
            connection.execute(
                "UPDATE assistant_memory_changes SET before_json=NULL, after_json=NULL WHERE memory_id=?",
                (memory_id,),
            )
            current = connection.execute(
                "SELECT * FROM assistant_memories WHERE id=?", (memory_id,)
            ).fetchone()
            result = self._public(dict(current))
            self._write_change(
                connection, result, operation="forgotten", before=None,
                actor="user", memory_epoch=epoch,
            )
            AssistantRunStore.enqueue_job(
                connection,
                kind="memory_purge",
                dedupe_key=f"memory_purge:{memory_id}:{next_version}",
                payload={
                    "memory_id": memory_id,
                    "version": next_version,
                    "backend_id": row["backend_id"],
                    "memory_epoch": epoch,
                },
            )
            self._save_receipt(connection, operation_key, "memory_forget", result)
        return result

    def recall(self, query: str, *, space_id: int, limit: int = 8) -> list[dict[str, Any]]:
        return self.recall_with_status(query, space_id=space_id, limit=limit)["items"]

    def recall_with_status(
        self, query: str, *, space_id: int, limit: int = 8
    ) -> dict[str, Any]:
        clean_query = " ".join(query.split())[:1000]
        candidates: dict[str, dict[str, Any]] = {}
        semantic_versions: dict[str, int] = {}
        backend_ready = self.backend is not None
        backend_error: str | None = None

        def add_candidate(record_id: str, score: float, reason: str) -> None:
            if not record_id:
                return
            value = candidates.setdefault(record_id, {"score": 0.0, "reasons": set()})
            value["score"] = max(float(value["score"]), score)
            value["reasons"].add(reason)

        if backend_ready and clean_query:
            for scope_key in ("user", f"space:{space_id}"):
                try:
                    for item in self.backend.search(clean_query, top_k=20, scope_key=scope_key):
                        metadata = item.get("metadata") or {}
                        record_id = str(metadata.get("record_id") or "")
                        if record_id:
                            semantic_versions[record_id] = int(metadata.get("record_version") or 0)
                            add_candidate(record_id, float(item.get("score") or 0.0), "semantic")
                except Exception as exc:
                    backend_ready = False
                    backend_error = str(exc)[:300]
                    break

        now = utc_now()
        with self.db.connect() as connection:
            terms = [value for value in clean_query.split(" ") if value][:8]
            if not terms and clean_query:
                terms = [clean_query]
            if terms:
                clauses: list[str] = []
                params: list[Any] = [self.principal_id, str(space_id), now, now]
                for term in terms:
                    clauses.append("(text LIKE ? OR subject_key LIKE ?)")
                    pattern = f"%{term[:120]}%"
                    params.extend([pattern, pattern])
                lexical = connection.execute(
                    f"""
                    SELECT id FROM assistant_memories
                    WHERE principal_id=? AND status='active'
                      AND (scope_kind='user' OR (scope_kind='space' AND scope_id=?))
                      AND (valid_from IS NULL OR valid_from<=?)
                      AND (expires_at IS NULL OR expires_at>?)
                      AND ({' OR '.join(clauses)})
                    ORDER BY pinned DESC, user_edited DESC, updated_at DESC LIMIT 60
                    """,
                    params,
                ).fetchall()
                for rank, row in enumerate(lexical):
                    add_candidate(str(row["id"]), 0.65 - rank * 0.002, "lexical")

            # Chinese questions often contain no spaces. Match short character
            # spans against the small authoritative personal set, not a whole
            # sentence LIKE term.
            def grams(value: str) -> set[str]:
                compact = re.sub(r"[\s，。？！、；：,.!?：]+", "", value)
                return {compact[i:i + 2] for i in range(max(0, len(compact) - 1))}
            query_grams = grams(clean_query)
            if query_grams:
                rows = connection.execute(
                    """SELECT id,text,subject_key FROM assistant_memories
                       WHERE principal_id=? AND status='active'
                         AND (scope_kind='user' OR (scope_kind='space' AND scope_id=?))
                         AND (valid_from IS NULL OR valid_from<=?)
                         AND (expires_at IS NULL OR expires_at>?)
                       ORDER BY updated_at DESC LIMIT 300""",
                    (self.principal_id, str(space_id), now, now),
                ).fetchall()
                for row in rows:
                    overlap = query_grams & grams(str(row["text"]) + str(row["subject_key"]))
                    if len(overlap) >= 2:
                        add_candidate(str(row["id"]), min(0.72, 0.43 + len(overlap) * 0.025), "chinese_lexical")

            explicit = connection.execute(
                """
                SELECT id, pinned, user_edited, kind, last_projected_version, version
                FROM assistant_memories
                WHERE principal_id=? AND status='active'
                  AND (scope_kind='user' OR (scope_kind='space' AND scope_id=?))
                  AND (valid_from IS NULL OR valid_from<=?)
                  AND (expires_at IS NULL OR expires_at>?)
                  AND (pinned=1 OR last_projected_version IS NULL
                       OR last_projected_version!=version)
                ORDER BY pinned DESC, user_edited DESC, updated_at DESC LIMIT 40
                """,
                (self.principal_id, str(space_id), now, now),
            ).fetchall()
            anaphoric = bool(re.search(r"(?:按我|我的|我现在|我接下来|那我|上次|之前|我的计划|我的安排)", clean_query))
            anaphoric_count = 0
            for row in explicit:
                record_id = str(row["id"])
                matched = record_id in candidates
                fallback = (anaphoric and anaphoric_count < 2
                            and str(row["kind"]) in {"context", "decision"})
                if bool(row["pinned"]) or matched or fallback:
                    score = 0.55 if bool(row["pinned"]) else 0.25
                    add_candidate(record_id, score, "explicit_or_pending")
                    if fallback and not matched:
                        anaphoric_count += 1

            ids = sorted(candidates)
            active: dict[str, dict[str, Any]] = {}
            for offset in range(0, len(ids), 200):
                page = ids[offset:offset + 200]
                placeholders = ",".join("?" for _ in page)
                rows = connection.execute(
                    f"""
                    SELECT * FROM assistant_memories
                    WHERE id IN ({placeholders}) AND principal_id=? AND status='active'
                      AND (scope_kind='user' OR (scope_kind='space' AND scope_id=?))
                      AND (valid_from IS NULL OR valid_from<=?)
                      AND (expires_at IS NULL OR expires_at>?)
                    """,
                    (*page, self.principal_id, str(space_id), now, now),
                ).fetchall()
                active.update({str(row["id"]): dict(row) for row in rows})

        ranked: list[tuple[dict[str, Any], float, set[str]]] = []
        for record_id, candidate in candidates.items():
            row = active.get(record_id)
            if row is None:
                continue
            reasons = set(candidate["reasons"])
            score = float(candidate["score"])
            semantic_version = semantic_versions.get(record_id)
            if semantic_version is not None and semantic_version != int(row["version"]):
                reasons.discard("semantic")
                reasons.add("stale_semantic_rechecked")
                if not reasons.intersection({"lexical", "chinese_lexical", "explicit_or_pending"}):
                    continue
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
            subject_scopes.setdefault(str(row["subject_key"]), set()).add(str(row["scope_kind"]))
        items = []
        fixed = [item for item in ranked if bool(item[0]["pinned"])]
        ordinary = [item for item in ranked if not bool(item[0]["pinned"])]
        selected = fixed[:min(2, limit)] + ordinary[:max(0, limit - min(2, len(fixed)))]
        for row, score, reasons in selected:
            public = self._public(row)
            public.update({
                "semantic_index_ready": backend_ready,
                "recall_score": round(score, 6),
                "recall_reasons": sorted(reasons),
                "dependency_ref": self.dependency_ref(public),
                "scope_precedence": "current_space" if public["scope_kind"] == "space" else "global_user",
                "scope_conflict": len(subject_scopes.get(str(public["subject_key"]), set())) > 1,
            })
            items.append(public)
        return {
            "items": items,
            "semantic_index": "ready" if backend_ready else "unavailable",
            "semantic_error": backend_error,
            "authoritative_store": "sqlite",
            "memory_epoch": self.current_epoch(),
        }

    def current_epoch(self) -> int:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT value FROM assistant_runtime_state WHERE key='memory_epoch'"
            ).fetchone()
        return int(row["value"] if row else 0)

    def changes_since(
        self, after_epoch: int, *, space_id: int | None = None, limit: int = 200
    ) -> dict[str, Any]:
        if after_epoch < 0 or limit < 1 or limit > 500:
            raise ValueError("invalid_memory_change_cursor")
        conditions = ["m.principal_id=?", "c.memory_epoch>?"]
        params: list[Any] = [self.principal_id, after_epoch]
        if space_id is not None:
            conditions.append("(m.scope_kind='user' OR (m.scope_kind='space' AND m.scope_id=?))")
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
                WHERE {' AND '.join(conditions)}
                ORDER BY c.memory_epoch, c.id LIMIT ?
                """,
                params,
            ).fetchall()
        items = [dict(row) for row in rows]
        return {
            "after_epoch": after_epoch,
            "current_epoch": self.current_epoch(),
            "items": items,
            "next_epoch": max((int(item["memory_epoch"]) for item in items), default=after_epoch),
        }

    def suppressed_source_message_ids(self, *, space_id: int) -> set[str]:
        """Messages fenced by a correction/forget are not default context instructions."""
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT source_message_ids_json FROM assistant_memory_suppressions
                WHERE principal_id=? AND (
                    scope_kind='user' OR (scope_kind='space' AND scope_id=?)
                )
                """,
                (self.principal_id, str(space_id)),
            ).fetchall()
        values: set[str] = set()
        for row in rows:
            values.update(str(value) for value in json.loads(row["source_message_ids_json"] or "[]"))
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
                JOIN assistant_memories m ON m.id=? AND m.principal_id=r.principal_id
                WHERE r.operation_key=? AND r.principal_id=?
                """,
                (memory_id, operation_key, self.principal_id),
            ).fetchone()
        if row is None or str(row["operation"]) != "memory_forget":
            return False
        try:
            receipt = json.loads(row["result_json"])
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
                WHERE principal_id=? AND status='active' AND (
                    scope_kind='user' OR (scope_kind='space' AND scope_id=?)
                )
                """,
                (self.principal_id, str(space_id)),
            ).fetchall()
        return [
            f"memory:{row['id']}:{int(row['version'])}"
            for row in rows
            if wanted.intersection(json.loads(row["source_message_ids_json"] or "[]"))
        ]

    def validate_dependency_refs(
        self, refs: list[str], *, space_id: int
    ) -> dict[str, Any]:
        stale: list[str] = []
        current: list[str] = []
        for ref in refs:
            parts = str(ref).split(":")
            if len(parts) != 3 or parts[0] != "memory" or not parts[2].isdigit():
                stale.append(str(ref))
                continue
            try:
                memory = self.get(parts[1])
            except KeyError:
                stale.append(str(ref))
                continue
            in_scope = memory["scope_kind"] == "user" or (
                memory["scope_kind"] == "space" and str(memory["scope_id"]) == str(space_id)
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
            "memory_epoch": self.current_epoch(),
        }

    @staticmethod
    def dependency_ref(memory: dict[str, Any]) -> str:
        return f"memory:{memory['id']}:{int(memory['version'])}"

    def project(self, *, memory_id: str, version: int, old_backend_id: str | None = None) -> dict[str, Any]:
        if self.backend is None:
            raise RuntimeError("memory_backend_unavailable")
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM assistant_memories WHERE id=? AND principal_id=?",
                (memory_id, self.principal_id),
            ).fetchone()
        if row is None or str(row["status"]) != "active" or int(row["version"]) != version:
            return {"superseded": True}
        scope_key = self._scope_key(str(row["scope_kind"]), str(row["scope_id"]))
        operation_id = f"memory_index:{memory_id}:{version}"
        backend_id: str | None = None
        for item in self.backend.get_all(scope_key=scope_key):
            metadata = item.get("metadata") or {}
            if metadata.get("operation_id") == operation_id:
                backend_id = str(item.get("id") or item.get("memory_id") or "") or None
                break
        if backend_id is None:
            result = self.backend.add(
                str(row["text"]),
                record_id=memory_id,
                record_version=version,
                scope_key=scope_key,
                operation_id=operation_id,
            )
            values = result.get("results", []) if isinstance(result, dict) else []
            if values:
                backend_id = str(values[0].get("id") or "") or None
        if backend_id is None:
            raise RuntimeError("memory_backend_id_missing")
        with self.db.connect() as connection:
            updated = connection.execute(
                """
                UPDATE assistant_memories SET backend_id=?, last_projected_version=?, updated_at=?
                WHERE id=? AND status='active' AND version=?
                """,
                (backend_id, version, utc_now(), memory_id, version),
            )
        if updated.rowcount != 1:
            self.backend.delete(backend_id)
            return {"superseded": True}
        if old_backend_id and old_backend_id != backend_id:
            self.backend.delete(old_backend_id)
        return {"backend_id": backend_id, "version": version}

    def purge(self, *, memory_id: str, version: int, backend_id: str | None) -> dict[str, Any]:
        if backend_id:
            if self.backend is None:
                raise RuntimeError("memory_backend_unavailable")
            self.backend.delete(backend_id)
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT status, version FROM assistant_memories WHERE id=?", (memory_id,)
            ).fetchone()
        return {
            "purged": True,
            "still_forgotten": bool(row and row["status"] == "forgotten" and int(row["version"]) == version),
        }

    def apply_extracted(
        self,
        proposal: dict[str, Any],
        *,
        source_message_ids: list[str],
        expected_epoch: int,
        operation_key: str,
        expected_auto_generation: int | None = None,
    ) -> dict[str, Any] | None:
        proposal_scope = str(proposal.get("scope_kind") or "space")
        proposal_scope_id = "" if proposal_scope == "user" else str(
            proposal.get("scope_id") or ""
        )
        self._validate_scope(
            proposal_scope,
            int(proposal_scope_id) if proposal_scope_id else None,
        )
        op = str(proposal.get("op") or "no_change")
        if op not in {"add", "revise"}:
            return None
        scope_kind = proposal_scope
        scope_id = int(proposal_scope_id) if proposal_scope_id else None
        proposal_text = self._validate_text(str(proposal.get("text") or ""))
        proposal_subject = self._validate_subject(str(proposal.get("subject_key") or ""))
        with self._memory_write_transaction() as connection:
            receipt = self._receipt(connection, operation_key)
            if receipt is not None:
                return receipt
            states = connection.execute("SELECT key,value FROM assistant_runtime_state WHERE key IN ('auto_memory_enabled','auto_memory_generation')").fetchall()
            policy = {str(row["key"]): str(row["value"]) for row in states}
            if policy.get("auto_memory_enabled", "1") == "0" or (
                expected_auto_generation is not None
                and int(policy.get("auto_memory_generation", "0")) != expected_auto_generation
            ):
                return None
            if self._current_epoch(connection) != expected_epoch:
                suppressed = connection.execute(
                    """
                    SELECT scope_kind, scope_id, subject_key, content_hash,
                           source_message_ids_json
                    FROM assistant_memory_suppressions WHERE principal_id=?
                    """,
                    (self.principal_id,),
                ).fetchall()
                protected = connection.execute(
                    """
                    SELECT source_message_ids_json FROM assistant_memories
                    WHERE principal_id=? AND status='active' AND user_edited=1
                      AND scope_kind=? AND scope_id=?
                    """,
                    (self.principal_id, proposal_scope, proposal_scope_id),
                ).fetchall()
                for row in protected:
                    protected_ids = set(json.loads(str(row["source_message_ids_json"] or "[]")))
                    if protected_ids.intersection(source_message_ids):
                        return None
                proposal_hash = self._content_hash(proposal_text)
                for row in suppressed:
                    blocked_ids = set(json.loads(str(row["source_message_ids_json"] or "[]")))
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
                    "SELECT * FROM assistant_memories WHERE id=? AND principal_id=?",
                    (str(proposal["target_memory_id"]), self.principal_id),
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
                    expected_version=int(proposal.get("expected_version") or target["version"]),
                    operation_key=operation_key,
                    subject_key=proposal_subject or str(target["subject_key"]),
                    kind=str(proposal.get("kind") or target["kind"]),
                    valid_from=proposal.get("valid_from", _UNSET),
                    expires_at=proposal.get("expires_at", _UNSET),
                    validity_note=proposal.get("validity_note", _UNSET),
                    validity_timezone=proposal.get("validity_timezone", _UNSET),
                    source_message_ids=source_message_ids,
                    source_excerpt=str(proposal.get("source_excerpt") or ""),
                    _actor="assistant",
                    _user_edited=False,
                    _connection=connection,
                )
            if op == "revise":
                return None
            return self._save_extracted(
                connection,
                text=proposal_text,
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
            )

    def _save_extracted(self, connection: Any, **values: Any) -> dict[str, Any]:
        # save_explicit performs duplicate lookup, formal write, outbox enqueue,
        # and receipt in one transaction. A duplicate retains its existing origin,
        # edit protection, and pin rather than being converted to an extracted fact.
        conflicting = connection.execute(
            """
            SELECT 1 FROM assistant_memories
            WHERE principal_id=? AND scope_kind=? AND scope_id=?
              AND subject_key=? AND status='active' AND text!=?
            LIMIT 1
            """,
            (
                self.principal_id, values["scope_kind"],
                "" if values["scope_kind"] == "user" else str(values["scope_id"]),
                self._validate_subject(str(values["subject_key"])),
                self._validate_text(str(values["text"])),
            ),
        ).fetchone()
        return self.save_explicit(
            **values,
            origin="extracted",
            _initial_status="needs_review" if conflicting else "active",
            _connection=connection,
        )

    def _validate_scope(self, scope_kind: str, scope_id: int | None) -> str:
        if scope_kind == "user":
            return ""
        if scope_kind != "space" or scope_id is None:
            raise ValueError("invalid_memory_scope")
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM assistant_spaces WHERE id=? AND principal_id=? AND enabled=1",
                (scope_id, self.principal_id),
            ).fetchone()
        if row is None:
            raise ValueError("invalid_memory_scope")
        return str(scope_id)

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
        if valid_from is _UNSET or expires_at is _UNSET or validity_note is _UNSET or validity_timezone is _UNSET:
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
        current = now or utc_now()
        return (
            (not memory.get("valid_from") or str(memory["valid_from"]) <= current)
            and (not memory.get("expires_at") or str(memory["expires_at"]) > current)
        )

    def _suppress(
        self,
        connection: Any,
        row: Any,
        *,
        memory_epoch: int,
        content_hash: str,
    ) -> None:
        source_ids = json.loads(str(row["source_message_ids_json"] or "[]"))
        connection.execute(
            """
            INSERT INTO assistant_memory_suppressions(
                principal_id, scope_kind, scope_id, subject_key, content_hash,
                source_message_ids_json, memory_epoch, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(principal_id, scope_kind, scope_id, subject_key, content_hash)
            DO UPDATE SET memory_epoch=excluded.memory_epoch,
                          source_message_ids_json=excluded.source_message_ids_json,
                          created_at=excluded.created_at
            """,
            (
                self.principal_id, row["scope_kind"], row["scope_id"], row["subject_key"],
                content_hash, json.dumps(source_ids), memory_epoch, utc_now(),
            ),
        )

    def _enqueue_index(
        self,
        connection: Any,
        memory_id: str,
        version: int,
        scope_kind: str,
        scope_id: str,
        *,
        old_backend_id: str | None = None,
    ) -> None:
        AssistantRunStore.enqueue_job(
            connection,
            kind="memory_index",
            dedupe_key=f"memory_index:{memory_id}:{version}",
            payload={
                "memory_id": memory_id,
                "version": version,
                "scope_key": self._scope_key(scope_kind, scope_id),
                "old_backend_id": old_backend_id,
            },
        )

    @staticmethod
    def _scope_key(scope_kind: str, scope_id: str) -> str:
        return "user" if scope_kind == "user" else f"space:{scope_id}"

    @staticmethod
    def _content_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _fts_replace(connection: Any, memory_id: str, text: str) -> None:
        connection.execute("DELETE FROM assistant_memories_fts WHERE memory_id=?", (memory_id,))
        connection.execute(
            "INSERT INTO assistant_memories_fts(memory_id, text) VALUES(?, ?)",
            (memory_id, text),
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
    ) -> None:
        connection.execute(
            """
            INSERT INTO assistant_memory_changes(
                memory_id, version, operation, before_json, after_json, actor, created_at
                , memory_epoch
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                current["id"], current["version"], operation,
                json.dumps(before, ensure_ascii=False) if before is not None else None,
                json.dumps(current, ensure_ascii=False), actor, utc_now(), memory_epoch,
            ),
        )

    def _receipt(self, connection: Any, operation_key: str) -> dict[str, Any] | None:
        if not operation_key.strip():
            raise ValueError("operation_key_required")
        row = connection.execute(
            "SELECT result_json FROM assistant_mutation_receipts WHERE operation_key=? AND principal_id=?",
            (operation_key, self.principal_id),
        ).fetchone()
        return json.loads(row["result_json"]) if row else None

    def _save_receipt(
        self, connection: Any, operation_key: str, operation: str, result: dict[str, Any]
    ) -> None:
        connection.execute(
            """
            INSERT INTO assistant_mutation_receipts(
                operation_key, principal_id, operation, result_json, created_at
            ) VALUES(?, ?, ?, ?, ?)
            """,
            (operation_key, self.principal_id, operation, json.dumps(result, ensure_ascii=False), utc_now()),
        )

    @staticmethod
    def _increment_epoch(connection: Any) -> int:
        row = connection.execute(
            """
            INSERT INTO assistant_runtime_state(key, value, updated_at)
            VALUES('memory_epoch', '1', ?)
            ON CONFLICT(key) DO UPDATE SET
                value=CAST(assistant_runtime_state.value AS INTEGER) + 1,
                updated_at=excluded.updated_at
            RETURNING value
            """,
            (utc_now(),),
        ).fetchone()
        return int(row["value"])

    @staticmethod
    def _current_epoch(connection: Any) -> int:
        row = connection.execute(
            "SELECT value FROM assistant_runtime_state WHERE key='memory_epoch'"
        ).fetchone()
        return int(row["value"] if row else 0)

    @staticmethod
    def _public(value: dict[str, Any]) -> dict[str, Any]:
        value["source_message_ids"] = json.loads(value.pop("source_message_ids_json", "[]"))
        value["pinned"] = bool(value["pinned"])
        value["user_edited"] = bool(value["user_edited"])
        return value
