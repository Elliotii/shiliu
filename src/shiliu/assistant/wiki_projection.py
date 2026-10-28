"""Consistent Wiki scope/dependency snapshot; file preparation is outside SQL."""

from __future__ import annotations
from hashlib import sha256
import json
from shiliu.assistant.runtime_contract import AssistantConflict
from shiliu.assistant.sources import SourceScope


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


class WikiProjection:
    def __init__(self, wiki):
        self.wiki = wiki
        self.db = wiki.db

    @staticmethod
    def _state_token(state):
        # DTO timestamps preserve the public seconds contract, so updated_at
        # alone cannot fence two metadata edits in the same second. Compare all
        # SQL source inputs, retaining original immutable Artifact references.
        return digest({key: state[key] for key in ("video", "memberships", "notes")})

    def prepare_sources(self, space_id, *, page_id=None):
        # Read immutable historical manifests in a separate phase. No encoding,
        # hashing of large files, model or network inside the snapshot below.
        with self.db.connect(read_only=True) as c:
            self.wiki.store.get_space(space_id, conn=c)
            refs = c.execute(
                "SELECT DISTINCT d.video_id,d.source_revision,h.current_revision FROM assistant_wiki_dependencies d "
                "JOIN assistant_wiki_pages p ON (p.workspace_id,p.id)=(d.workspace_id,d.page_id) "
                "LEFT JOIN assistant_source_heads h ON (h.workspace_id,h.video_id)=(d.workspace_id,d.video_id) AND h.principal_id=p.principal_id "
                "WHERE p.workspace_id=%s AND p.principal_id=%s AND p.space_id=%s AND (%s::text IS NULL OR p.id=%s)",
                (
                    self.db.workspace_id,
                    self.db.context.user_id,
                    space_id,
                    page_id,
                    page_id,
                ),
            ).fetchall()
        cache = {"@current": {}}
        snapshots = self.wiki.sources.snapshots
        for video_id in sorted({r["video_id"] for r in refs}):
            state = snapshots._state(video_id)
            current = snapshots._build_snapshot(state)
            cache[current["revision"]] = current
            cache["@current"][video_id] = {
                "token": self._state_token(state),
                "revision": current["revision"],
            }
        for r in refs:
            for revision in (r["source_revision"], r["current_revision"]):
                if revision and revision not in cache:
                    try:
                        cache[revision] = self.wiki.sources._capture_or_load(
                            r["video_id"], revision
                        ).snapshot
                    except (KeyError, ValueError, FileNotFoundError):
                        pass
        return cache

    def capture(
        self,
        space_id,
        *,
        scope=None,
        thread_id=None,
        page_id=None,
        conn=None,
        prepared=None,
    ):
        if prepared is None:
            if conn is not None:
                raise ValueError("wiki_sources_must_be_prepared_outside_transaction")
            prepared = self.prepare_sources(space_id, page_id=page_id)
        if conn is None:
            with self.db.pg.transaction(
                read_only=True, isolation="repeatable read"
            ) as c:
                return self.capture(
                    space_id,
                    scope=scope,
                    thread_id=thread_id,
                    page_id=page_id,
                    conn=c,
                    prepared=prepared,
                )
        c = conn
        snapshots = self.wiki.sources.snapshots
        for video_id, current in prepared.get("@current", {}).items():
            if (
                self._state_token(snapshots._state(video_id, conn=c))
                != current["token"]
            ):
                raise AssistantConflict("wiki_snapshot_prepare_stale")
        space = self.wiki.store.get_space(space_id, conn=c)
        if not space["enabled"]:
            raise AssistantConflict("wiki_space_disabled")
        task = self.wiki.store.task_space(thread_id, conn=c) if thread_id else space
        if thread_id and task["id"] != space_id:
            raise AssistantConflict("wiki_thread_scope_mismatch")
        actual = self.wiki._scope(task)
        if scope is not None:
            allowed_sources = (
                actual.source_db_ids if not actual.all_active else scope.source_db_ids
            )
            if not scope.all_active:
                allowed_sources = (
                    allowed_sources & scope.source_db_ids
                    if not actual.all_active
                    else scope.source_db_ids
                )
            videos = actual.video_ids
            if scope.video_ids:
                videos = (
                    videos & scope.video_ids if videos else scope.video_ids
                ) or frozenset({-1})
            actual = SourceScope(
                source_db_ids=allowed_sources,
                video_ids=videos,
                all_active=actual.all_active and scope.all_active,
            )
        rows = c.execute(
            "SELECT * FROM assistant_wiki_pages WHERE workspace_id=%s AND principal_id=%s AND space_id=%s AND status='active' "
            "AND (%s::text IS NULL OR id=%s) ORDER BY id",
            (self.db.workspace_id, self.db.context.user_id, space_id, page_id, page_id),
        ).fetchall()
        epoch = c.execute(
            "SELECT dependency_epoch FROM workspace_guards WHERE workspace_id=%s",
            (self.db.workspace_id,),
        ).fetchone()["dependency_epoch"]
        pages = []
        for row in rows:
            page = self.wiki._task_projection(
                self.wiki._visible_page(
                    self.wiki._decode_page(dict(row)), conn=c, snapshot_cache=prepared
                ),
                actual if scope is not None or task.get("task_subset") else None,
                conn=c,
            )
            deps = c.execute(
                "SELECT d.memory_id AS id,d.memory_version AS version,d.source_message_id FROM assistant_wiki_personal_dependencies d "
                "WHERE d.workspace_id=%s AND d.page_id=%s ORDER BY d.memory_id,d.block_id",
                (self.db.workspace_id, page["id"]),
            ).fetchall()
            # Include raw dependency snapshots even if task projection removes a
            # block: it is conservative for cleanup and never grants visibility.
            memories = [{"id": r["id"], "version": r["version"]} for r in deps]
            message_ids = {
                r["source_message_id"] for r in deps if r["source_message_id"]
            }
            # Record actual authored message provenance at build time, including
            # quote/external-message blocks with no direct Memory dependency.
            # This immutable snapshot is only an erasure index, never authority.
            for block in row["blocks_json"]:
                message_ids.update(
                    str(block[k])
                    for k in ("user_message_id", "source_message_id")
                    if block.get(k)
                )
            messages = [
                r["id"]
                for r in c.execute(
                    "SELECT m.id FROM assistant_messages m JOIN assistant_threads t ON (t.workspace_id,t.id)=(m.workspace_id,m.thread_id) "
                    "WHERE m.workspace_id=%s AND t.principal_id=%s AND t.space_id=%s AND m.id=ANY(%s) ORDER BY m.id",
                    (
                        self.db.workspace_id,
                        self.db.context.user_id,
                        space_id,
                        sorted(message_ids),
                    ),
                ).fetchall()
            ]
            sources = c.execute(
                "SELECT d.video_id,d.source_revision,d.dependency_kind,h.current_revision FROM assistant_wiki_dependencies d "
                "LEFT JOIN assistant_source_heads h ON (h.workspace_id,h.video_id)=(d.workspace_id,d.video_id) AND h.principal_id=%s "
                "WHERE d.workspace_id=%s AND d.page_id=%s ORDER BY d.video_id,d.block_id,d.source_revision",
                (self.db.context.user_id, self.db.workspace_id, page["id"]),
            ).fetchall()
            for source in sources:
                source["actual_current_revision"] = (
                    prepared.get("@current", {})
                    .get(source["video_id"], {})
                    .get("revision", source["current_revision"])
                )
            vector = {
                "principal_id": self.db.context.user_id,
                "space_id": space_id,
                "scope_version": space["scope_version"],
                "dependency_epoch": epoch,
                "page_version": page["version"],
                "memories": memories,
                "messages": messages,
                "sources": sources,
                "scope": {
                    "source_ids": sorted(actual.source_db_ids),
                    "video_ids": sorted(actual.video_ids),
                    "all_active": actual.all_active,
                },
                "thread_id": thread_id,
            }
            page["dependency_versions"] = vector
            page["effective_hash"] = digest(
                {
                    "title": page["title"],
                    "aliases": page["aliases"],
                    "blocks": page["blocks"],
                    "dependencies": vector,
                }
            )
            pages.append(page)
        return {
            "pages": pages,
            "scope_version": space["scope_version"],
            "dependency_epoch": epoch,
            "scope": {
                "source_ids": sorted(actual.source_db_ids),
                "video_ids": sorted(actual.video_ids),
                "all_active": actual.all_active,
            },
            "thread_id": thread_id,
            "snapshot_hash": digest([(p["id"], p["effective_hash"]) for p in pages]),
        }
