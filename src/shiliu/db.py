"""Collection queries on the injected PostgreSQL pool.

Every domain query carries workspace ownership. Private notes additionally carry
principal ownership. Methods accepting conn participate in its caller transaction.
Schema creation and source SQLite readers are deliberately outside this facade.
"""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Iterator

from psycopg import Connection, sql
from psycopg.types.json import Jsonb

from shiliu.domain import FavoriteItem, StageName
from shiliu.storage.dto import row_dto
from shiliu.storage.fences import CoordinationConflict, lock_workspace
from shiliu.storage.postgres import PgDatabase
from shiliu.storage.scope import ResourceContext

# Historical source version, used only by explicit migration tools.
SCHEMA_VERSION = 26
LibraryCardCursor = tuple[int, int, str, int, int, int]


@dataclass(frozen=True)
class LibraryCardPage:
    items: list[dict[str, Any]]
    has_previous: bool
    has_next: bool
    snapshot_rowid: int


def library_card_cursor(row: dict[str, Any]) -> LibraryCardCursor:
    return (
        int(row["card_order_favorite_time"]),
        int(row["card_order_source_position_desc"]),
        str(row["discovered_at"]),
        int(row["id"]),
        int(row["card_order_source_id_desc"]),
        int(row["card_snapshot_rowid"]),
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


TIMESTAMPS = frozenset(
    "created_at updated_at discovered_at completed_at removed_at ignored_at "
    "marked_at archived_at reading_state_updated_at subtitle_first_checked_at subtitle_next_check_at "
    "metadata_observed_at first_observed_at last_observed_at first_seen_at last_seen_at "
    "last_sync_at history_updated_at cooldown_until lease_until next_retry_at submitted_at "
    "started_at finished_at heartbeat_at frozen_at".split()
)


def collection_dto(row):
    return (
        None if row is None else row_dto(row, timestamps=TIMESTAMPS.intersection(row))
    )


def json_field(value):
    # Explicit JSON column input adapter; ordinary strings never pass here.
    return Jsonb(json.loads(value) if isinstance(value, str) else value)


VIDEO_FIELDS = frozenset(
    "title uploader description description_links_json video_url cover_url cover_path "
    "subtitle_language subtitle_source subtitle_upstream_type raw_subtitle_path transcript_path summary_path "
    "artifact_dir status error_code error_message subtitle_check_count subtitle_first_checked_at "
    "subtitle_next_check_at completed_at removed_at processing_profile active_revision refinement_status "
    "display_favorite_time duration_seconds page_count asr_provider asr_model published_at "
    "metadata_observed_at cid part_title uploader_id reading_state reading_state_updated_at "
    "is_marked marked_at archived_at is_ignored ignored_at".split()
)
ASR_FIELDS = frozenset(
    "provider model trigger_mode status task_id remote_file_url result_url audio_path "
    "attempt_count next_retry_at last_error_code last_error_message submitted_at completed_at".split()
)
STAGE_FIELDS = frozenset(
    "status attempt_count next_retry_at last_error_code last_error_message provider model "
    "prompt_version started_at completed_at profile thinking_enabled reasoning_effort decision "
    "change_reasons_json elapsed_seconds".split()
)
SYNC_FIELDS = frozenset(
    "current_count discovered_count processed_count failed_count history_pending_count "
    "current_phase current_video_id message error_summary".split()
)


class Database:
    def __init__(self, pg: PgDatabase, context: ResourceContext) -> None:
        if not isinstance(pg, PgDatabase) or not isinstance(context, ResourceContext):
            raise TypeError(
                "Database requires an injected PgDatabase and trusted ResourceContext"
            )
        self.pg, self.context = pg, context
        self.workspace_id = context.workspace_id
        # Only coordinate this instance's source writer with its own heartbeat.
        # Other processes remain fenced by PostgreSQL owner/epoch/DB time.
        self._source_lease_locks = {}

    def _source_lease_lock(self, claim):
        return self._source_lease_locks.setdefault(int(claim["id"]), RLock())

    @contextmanager
    def _source_write(self, claim, conn=None):
        # A supplied connection is owned by its caller. Never acquire a local
        # mutex after that caller may already have acquired database row locks.
        local = self._source_lease_lock(claim) if claim and conn is None else nullcontext()
        with local, self.connect(conn, guard=True) as c:
            yield c
            if claim is not None:
                # A long atomic batch cannot publish after its lease expired.
                self.check_lease(c, "favorite_sources", claim)

    @contextmanager
    def connect(
        self,
        conn: Connection | None = None,
        *,
        guard: bool = False,
        read_only: bool = False,
    ) -> Iterator[Connection]:
        if conn is not None:
            if guard:
                lock_workspace(conn, self.context)
            yield conn
        else:
            with self.pg.transaction(read_only=read_only) as active:
                if guard:
                    lock_workspace(active, self.context)
                yield active

    def _video(self, conn, video_id, *, lock=False):
        row = conn.execute(
            "SELECT * FROM shiliu.videos WHERE workspace_id=%s AND id=%s"
            + (" FOR UPDATE" if lock else ""),
            (self.workspace_id, video_id),
        ).fetchone()
        if row is None:
            raise KeyError(video_id)
        return row

    def _source(self, conn, source_id, *, lock=False):
        row = conn.execute(
            "SELECT * FROM shiliu.favorite_sources WHERE workspace_id=%s AND id=%s"
            + (" FOR UPDATE" if lock else ""),
            (self.workspace_id, source_id),
        ).fetchone()
        if row is None:
            raise KeyError(source_id)
        return row

    def _update(self, conn, table, fields, allowed, predicate, params):
        if set(fields) - allowed:
            raise ValueError(
                "Unsupported "
                + table
                + " fields: "
                + str(sorted(set(fields) - allowed))
            )
        values = dict(fields, updated_at=utc_now())
        if "thinking_enabled" in values and values["thinking_enabled"] is not None:
            values["thinking_enabled"] = bool(values["thinking_enabled"])
        assignments = [sql.SQL("{}=%s").format(sql.Identifier(k)) for k in values]
        # published_at is an epoch count; missing upstream metadata never erases it.
        if "published_at" in values:
            assignments[list(values).index("published_at")] = sql.SQL(
                "published_at=COALESCE(%s,published_at)"
            )
        statement = sql.SQL(
            "UPDATE shiliu.{} SET {} WHERE workspace_id=%s AND "
        ).format(sql.Identifier(table), sql.SQL(",").join(assignments)) + sql.SQL(
            predicate
        )
        return conn.execute(
            statement,
            [json_field(v) if k.endswith("_json") else v for k, v in values.items()]
            + [self.workspace_id, *params],
        )

    def _touch(self, conn, video_id, *, reason):
        """Formal change and durable intent share this transaction, never a callback."""
        self._video(conn, video_id)
        conn.execute(
            "UPDATE shiliu.workspace_guards SET dependency_epoch=dependency_epoch+1 "
            "WHERE workspace_id=%s",
            (self.workspace_id,),
        )
        conn.execute(
            "INSERT INTO shiliu.retrieval_projection_tasks(workspace_id,domain,resource_key,"
            "requested_generation,payload,status,attempt,not_before,created_at,updated_at) "
            "VALUES(%s,'collection',%s,1,%s,'queued',0,clock_timestamp(),clock_timestamp(),clock_timestamp()) "
            "ON CONFLICT(workspace_id,domain,resource_key) DO UPDATE SET "
            "requested_generation=shiliu.retrieval_projection_tasks.requested_generation+1,"
            "payload=excluded.payload,status='queued',attempt=0,not_before=clock_timestamp(),"
            "last_error=NULL,updated_at=clock_timestamp()",
            (
                self.workspace_id,
                str(video_id),
                Jsonb({"video_id": video_id, "reason": reason}),
            ),
        )
        self._notify_assistant_source_change(conn, video_id, reason=reason)

    def create_video(
        self,
        source_id,
        title,
        uploader="",
        *,
        processing_profile="formal",
        display_favorite_time=None,
        duration_seconds=0,
        part=1,
        conn=None,
    ):
        with self.connect(conn, guard=True) as c:
            existed = c.execute(
                "SELECT id FROM shiliu.videos WHERE workspace_id=%s AND "
                "platform='bilibili' AND source_id=%s AND part=%s",
                (self.workspace_id, source_id, part),
            ).fetchone()
            row = c.execute(
                "INSERT INTO shiliu.videos(workspace_id,platform,source_id,part,title,uploader,"
                "video_url,status,processing_profile,active_revision,refinement_status,display_favorite_time,"
                "duration_seconds,discovered_at,updated_at) VALUES(%s,'bilibili',%s,%s,%s,%s,%s,'discovered',"
                "%s,%s,%s,%s,%s,clock_timestamp(),clock_timestamp()) "
                "ON CONFLICT(workspace_id,platform,source_id,part) DO UPDATE SET title=excluded.title,"
                "uploader=excluded.uploader,removed_at=NULL,display_favorite_time=COALESCE("
                "excluded.display_favorite_time,videos.display_favorite_time),duration_seconds=CASE WHEN "
                "excluded.duration_seconds>0 THEN excluded.duration_seconds ELSE videos.duration_seconds END,"
                "updated_at=excluded.updated_at RETURNING id",
                (
                    self.workspace_id,
                    source_id,
                    part,
                    title,
                    uploader,
                    f"https://www.bilibili.com/video/{source_id}",
                    processing_profile,
                    "fast" if processing_profile == "fast" else "refined",
                    "pending" if processing_profile == "fast" else "not_required",
                    display_favorite_time,
                    max(0, int(duration_seconds)),
                ),
            ).fetchone()
            video_id = int(row["id"])
            if existed is None:
                self.add_event(
                    "new_favorite", video_id, {"source_id": source_id}, conn=c
                )
            self._touch(
                c,
                video_id,
                reason="video_created" if existed is None else "video_updated",
            )
            return video_id

    def update_video(self, video_id, *, publish_guard=None, conn=None, **fields):
        if not fields:
            return
        with self.connect(conn, guard=True) as c:
            if publish_guard is not None:
                publish_guard(c)
            self._video(c, video_id, lock=True)
            self._update(c, "videos", fields, VIDEO_FIELDS, "id=%s", [video_id])
            self._touch(c, video_id, reason="video_updated")

    def get_video(self, video_id, *, conn=None):
        with self.connect(conn, read_only=True) as c:
            return collection_dto(
                c.execute(
                    "SELECT * FROM shiliu.videos WHERE workspace_id=%s AND id=%s",
                    (self.workspace_id, video_id),
                ).fetchone()
            )

    def get_video_by_source(self, source_id, *, part=1, conn=None):
        with self.connect(conn, read_only=True) as c:
            return collection_dto(
                c.execute(
                    "SELECT * FROM shiliu.videos WHERE workspace_id=%s AND "
                    "platform='bilibili' AND source_id=%s AND part=%s",
                    (self.workspace_id, source_id, part),
                ).fetchone()
            )

    def list_videos(self, source_db_id=None, *, conn=None):
        with self.connect(conn, read_only=True) as c:
            if source_db_id is None:
                rows = c.execute(
                    "SELECT * FROM shiliu.videos WHERE workspace_id=%s ORDER BY "
                    "COALESCE(display_favorite_time,0) DESC,discovered_at DESC,id DESC",
                    (self.workspace_id,),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT v.* FROM shiliu.videos v JOIN shiliu.video_source_memberships m "
                    "ON (m.workspace_id,m.video_id)=(v.workspace_id,v.id) WHERE v.workspace_id=%s "
                    "AND m.source_id=%s AND m.removed_at IS NULL ORDER BY "
                    "COALESCE(m.favorite_time,v.display_favorite_time,0) DESC,m.source_position,v.discovered_at DESC,v.id DESC",
                    (self.workspace_id, source_db_id),
                ).fetchall()
            result = [collection_dto(r) for r in rows]
            for row in result:
                row["sources"] = self.video_sources(row["id"], connection=c)
            return result

    def create_favorite_source(
        self,
        *,
        folder_id,
        folder_title,
        account_id=None,
        account_name="",
        original_url="",
        media_count=0,
        history_policy="future_only",
        history_limit=None,
        conn=None,
    ):
        with self.connect(conn, guard=True) as c:
            order = c.execute(
                "SELECT COALESCE(MAX(sort_order),-1)+1 AS n FROM shiliu.favorite_sources "
                "WHERE workspace_id=%s",
                (self.workspace_id,),
            ).fetchone()["n"]
            row = c.execute(
                "INSERT INTO shiliu.favorite_sources(workspace_id,platform,folder_id,folder_title,"
                "account_id,account_name,original_url,media_count,history_policy,history_limit,sort_order,created_at,updated_at) "
                "VALUES(%s,'bilibili',%s,%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp(),clock_timestamp()) "
                "ON CONFLICT(workspace_id,platform,folder_id) DO UPDATE SET "
                "original_url=CASE WHEN excluded.original_url='' THEN favorite_sources.original_url ELSE excluded.original_url END,"
                "account_id=COALESCE(excluded.account_id,favorite_sources.account_id),"
                "account_name=CASE WHEN excluded.account_name='' THEN favorite_sources.account_name ELSE excluded.account_name END,"
                "folder_title=CASE WHEN excluded.folder_title='' THEN favorite_sources.folder_title ELSE excluded.folder_title END,"
                "media_count=excluded.media_count,updated_at=excluded.updated_at RETURNING id",
                (
                    self.workspace_id,
                    folder_id,
                    folder_title,
                    account_id,
                    account_name,
                    original_url,
                    media_count,
                    history_policy,
                    history_limit,
                    order,
                ),
            ).fetchone()
            return int(row["id"])

    def get_source(self, source_db_id, *, conn=None):
        with self.connect(conn, read_only=True) as c:
            return collection_dto(
                c.execute(
                    "SELECT * FROM shiliu.favorite_sources WHERE workspace_id=%s AND id=%s",
                    (self.workspace_id, source_db_id),
                ).fetchone()
            )

    def get_source_by_folder(self, folder_id, *, conn=None):
        with self.connect(conn, read_only=True) as c:
            return collection_dto(
                c.execute(
                    "SELECT * FROM shiliu.favorite_sources WHERE workspace_id=%s "
                    "AND platform='bilibili' AND folder_id=%s",
                    (self.workspace_id, folder_id),
                ).fetchone()
            )

    def list_sources(self, *, active_only=False, conn=None):
        with self.connect(conn, read_only=True) as c:
            return [
                collection_dto(r)
                for r in c.execute(
                    "SELECT * FROM shiliu.favorite_sources WHERE workspace_id=%s"
                    + (" AND status IN ('active','cooldown')" if active_only else "")
                    + " ORDER BY sort_order,id",
                    (self.workspace_id,),
                ).fetchall()
            ]

    def _touch_source(self, c, source_id, reason):
        for r in c.execute(
            "SELECT DISTINCT video_id FROM shiliu.video_source_memberships "
            "WHERE workspace_id=%s AND source_id=%s AND video_id IS NOT NULL ORDER BY video_id",
            (self.workspace_id, source_id),
        ).fetchall():
            self._touch(c, r["video_id"], reason=reason)

    def set_source_status(self, source_db_id, status, *, conn=None):
        if status not in {"active", "paused", "needs_auth", "unavailable", "cooldown"}:
            raise ValueError("Unsupported source status")
        with self.connect(conn, guard=True) as c:
            self._source(c, source_db_id, lock=True)
            c.execute(
                "UPDATE shiliu.favorite_sources SET status=%s,updated_at=clock_timestamp() "
                "WHERE workspace_id=%s AND id=%s",
                (status, self.workspace_id, source_db_id),
            )
            self._touch_source(c, source_db_id, "source_status")

    def move_source(self, source_db_id, direction):
        if direction not in {"up", "down"}:
            raise ValueError("Unsupported move direction")
        with self.connect(guard=True) as c:
            rows = c.execute(
                "SELECT id,sort_order FROM shiliu.favorite_sources WHERE workspace_id=%s "
                "ORDER BY sort_order,id FOR UPDATE",
                (self.workspace_id,),
            ).fetchall()
            i = next((i for i, r in enumerate(rows) if r["id"] == source_db_id), None)
            if i is None:
                raise KeyError(source_db_id)
            j = i + (-1 if direction == "up" else 1)
            if not 0 <= j < len(rows):
                return False
            for a, b in ((i, j), (j, i)):
                c.execute(
                    "UPDATE shiliu.favorite_sources SET sort_order=%s,updated_at=clock_timestamp() "
                    "WHERE workspace_id=%s AND id=%s",
                    (rows[b]["sort_order"], self.workspace_id, rows[a]["id"]),
                )
            return True

    def remove_source(self, source_db_id):
        with self.connect(guard=True) as c:
            self._source(c, source_db_id, lock=True)
            ids = [
                r["video_id"]
                for r in c.execute(
                    "SELECT DISTINCT video_id FROM shiliu.video_source_memberships "
                    "WHERE workspace_id=%s AND source_id=%s AND video_id IS NOT NULL",
                    (self.workspace_id, source_db_id),
                ).fetchall()
            ]
            c.execute(
                "DELETE FROM shiliu.favorite_sources WHERE workspace_id=%s AND id=%s",
                (self.workspace_id, source_db_id),
            )
            for vid in ids:
                self._touch(c, vid, reason="source_removed")

    def _membership(
        self, c, source_id, item, position, video_id, *, baseline=False, queued=False
    ):
        old = c.execute(
            "SELECT membership_seq FROM shiliu.video_source_memberships WHERE workspace_id=%s "
            "AND source_id=%s AND bvid=%s",
            (self.workspace_id, source_id, item.bvid),
        ).fetchone()
        if old is None:
            seq = c.execute(
                "UPDATE shiliu.workspace_guards SET membership_highwater=membership_highwater+1 "
                "WHERE workspace_id=%s RETURNING membership_highwater",
                (self.workspace_id,),
            ).fetchone()["membership_highwater"]
        else:
            seq = old["membership_seq"]
        c.execute(
            "INSERT INTO shiliu.video_source_memberships(workspace_id,membership_seq,source_id,bvid,video_id,"
            "title,uploader,favorite_time,source_position,is_baseline,queued_history,first_observed_at,last_observed_at) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp(),clock_timestamp()) "
            "ON CONFLICT(source_id,bvid) DO UPDATE SET video_id=COALESCE(video_source_memberships.video_id,excluded.video_id),"
            "title=excluded.title,uploader=excluded.uploader,favorite_time=COALESCE(excluded.favorite_time,video_source_memberships.favorite_time),"
            "source_position=excluded.source_position,last_observed_at=excluded.last_observed_at,removed_at=NULL",
            (
                self.workspace_id,
                seq,
                source_id,
                item.bvid,
                video_id,
                item.title,
                item.uploader,
                item.favorite_time,
                position,
                baseline,
                queued,
            ),
        )

    def _observe_video(self, c, video_id, item, *, reenter=False):
        if reenter:
            c.execute(
                "UPDATE shiliu.videos SET archived_at=NULL,reading_state='unread',reading_state_updated_at=clock_timestamp(),"
                "is_ignored=false,ignored_at=NULL,removed_at=NULL,display_favorite_time=%s WHERE workspace_id=%s AND id=%s",
                (
                    item.favorite_time or int(datetime.now(timezone.utc).timestamp()),
                    self.workspace_id,
                    video_id,
                ),
            )
        c.execute(
            "UPDATE shiliu.videos SET title=CASE WHEN %s<>'' THEN %s ELSE title END,"
            "uploader=CASE WHEN %s<>'' THEN %s ELSE uploader END,duration_seconds=CASE WHEN %s>0 THEN %s ELSE duration_seconds END,"
            "removed_at=NULL,display_favorite_time=GREATEST(COALESCE(display_favorite_time,0),%s),updated_at=clock_timestamp() "
            "WHERE workspace_id=%s AND id=%s",
            (
                item.title,
                item.title,
                item.uploader,
                item.uploader,
                item.duration_seconds,
                item.duration_seconds,
                item.favorite_time or 0,
                self.workspace_id,
                video_id,
            ),
        )

    def initialize_source_memberships(
        self,
        source_db_id,
        items,
        *,
        authoritative,
        remote_total=None,
        claim=None,
        conn=None,
    ):
        with self._source_write(claim, conn) as c:
            source = self._source(c, source_db_id, lock=True)
            if claim is not None:
                self.check_lease(c, "favorite_sources", claim)
            else:
                self._assert_unclaimed(c, "favorite_sources", "id=%s", [source_db_id])
            ordered = sorted(
                enumerate(items),
                key=lambda p: (
                    p[1].favorite_time is None,
                    -(p[1].favorite_time or 0),
                    p[0],
                ),
            )
            n = (
                len(items)
                if source["history_policy"] == "all"
                else int(source["history_limit"] or 0)
                if source["history_policy"] == "latest_n"
                else 0
            )
            selected = {i.bvid for _, i in ordered[:n]} if authoritative else set()
            for pos, item in enumerate(items):
                video = self.get_video_by_source(item.bvid, conn=c)
                active = video is not None and self.video_has_active_source(
                    video["id"], conn=c
                )
                self._membership(
                    c,
                    source_db_id,
                    item,
                    pos,
                    video["id"] if video else None,
                    baseline=item.bvid not in selected,
                    queued=item.bvid in selected,
                )
                if video:
                    self._observe_video(
                        c,
                        video["id"],
                        item,
                        reenter=bool(video["archived_at"] or not active),
                    )
                    self._touch(c, video["id"], reason="membership_baseline")
            times = (
                [i.favorite_time for _, i in ordered[:n] if i.favorite_time is not None]
                if authoritative
                else []
            )
            cutoff = (
                min(times)
                if times
                else int(datetime.now(timezone.utc).timestamp())
                if source["history_policy"] == "future_only"
                else None
            )
            if authoritative:
                c.execute(
                    "UPDATE shiliu.favorite_sources SET baseline_initialized=true,media_count=%s,last_sync_at=clock_timestamp(),"
                    "updated_at=clock_timestamp(),history_cutoff_time=%s,discovery_complete=true,last_snapshot_complete=true,"
                    "history_updated_at=clock_timestamp(),last_error_code=NULL,last_error_message=NULL WHERE workspace_id=%s AND id=%s",
                    (
                        remote_total if remote_total is not None else len(items),
                        cutoff,
                        self.workspace_id,
                        source_db_id,
                    ),
                )
            else:
                c.execute(
                    "UPDATE shiliu.favorite_sources SET last_snapshot_complete=false,updated_at=clock_timestamp() "
                    "WHERE workspace_id=%s AND id=%s",
                    (self.workspace_id, source_db_id),
                )
            return len(selected)

    def record_source_snapshot(
        self,
        source_db_id,
        items,
        *,
        processing_profile,
        authoritative=False,
        remote_total=None,
        claim=None,
        conn=None,
    ):
        created = []
        with self._source_write(claim, conn) as c:
            self._source(c, source_db_id, lock=True)
            if claim is not None:
                self.check_lease(c, "favorite_sources", claim)
            else:
                self._assert_unclaimed(c, "favorite_sources", "id=%s", [source_db_id])
            known = {
                r["bvid"]: r
                for r in c.execute(
                    "SELECT * FROM shiliu.video_source_memberships "
                    "WHERE workspace_id=%s AND source_id=%s",
                    (self.workspace_id, source_db_id),
                ).fetchall()
            }
            for pos, item in enumerate(items):
                prior = known.get(item.bvid)
                video = self.get_video_by_source(item.bvid, conn=c)
                vid = prior["video_id"] if prior else None
                if prior is None or (prior["removed_at"] and vid is None):
                    vid = self.create_video(
                        item.bvid,
                        item.title,
                        item.uploader,
                        processing_profile=processing_profile,
                        display_favorite_time=item.favorite_time
                        or int(datetime.now(timezone.utc).timestamp()),
                        duration_seconds=item.duration_seconds,
                        conn=c,
                    )
                    if video is None:
                        created.append(vid)
                    video = self.get_video(vid, conn=c)
                active = vid is not None and self.video_has_active_source(vid, conn=c)
                self._membership(c, source_db_id, item, pos, vid)
                if vid is not None:
                    self._observe_video(
                        c,
                        vid,
                        item,
                        reenter=bool(
                            (prior is None or prior["removed_at"])
                            and ((video or {}).get("archived_at") or not active)
                        ),
                    )
            if authoritative:
                c.execute(
                    "UPDATE shiliu.video_source_memberships SET removed_at=COALESCE(removed_at,clock_timestamp()) "
                    "WHERE workspace_id=%s AND source_id=%s AND NOT (bvid=ANY(%s))",
                    (self.workspace_id, source_db_id, [i.bvid for i in items]),
                )
                c.execute(
                    "UPDATE shiliu.videos v SET removed_at=CASE WHEN EXISTS(SELECT 1 FROM "
                    "shiliu.video_source_memberships m WHERE (m.workspace_id,m.video_id)=(v.workspace_id,v.id) "
                    "AND m.removed_at IS NULL) THEN NULL ELSE COALESCE(v.removed_at,clock_timestamp()) END,updated_at=clock_timestamp() "
                    "WHERE v.workspace_id=%s AND v.id IN(SELECT video_id FROM shiliu.video_source_memberships "
                    "WHERE workspace_id=%s AND source_id=%s)",
                    (self.workspace_id, self.workspace_id, source_db_id),
                )
            c.execute(
                "UPDATE shiliu.favorite_sources SET media_count=CASE WHEN %s THEN %s ELSE media_count END,"
                "last_sync_at=clock_timestamp(),status=CASE WHEN status='paused' THEN status ELSE 'active' END,"
                "cooldown_until=CASE WHEN status='paused' THEN cooldown_until ELSE NULL END,"
                "discovery_complete=discovery_complete OR %s,last_snapshot_complete=%s,last_error_code=NULL,"
                "last_error_message=NULL,updated_at=clock_timestamp() WHERE workspace_id=%s AND id=%s",
                (
                    authoritative,
                    remote_total if remote_total is not None else len(items),
                    authoritative,
                    authoritative,
                    self.workspace_id,
                    source_db_id,
                ),
            )
            self._touch_source(c, source_db_id, "membership_snapshot")
        return created

    def update_source_history_coverage(
        self, source_db_id, *, history_policy, history_limit=None
    ):
        if history_policy not in {"future_only", "latest_n", "all"} or (
            history_policy == "latest_n" and (history_limit or 0) < 1
        ):
            raise ValueError("Unsupported history policy/limit")
        with self.connect(guard=True) as c:
            source = self._source(c, source_db_id, lock=True)
            if not source["discovery_complete"]:
                raise ValueError("历史范围只能基于完整收藏夹发现结果更新")
            rows = c.execute(
                "SELECT * FROM shiliu.video_source_memberships WHERE workspace_id=%s AND source_id=%s "
                "AND removed_at IS NULL ORDER BY favorite_time DESC NULLS LAST,source_position,bvid",
                (self.workspace_id, source_db_id),
            ).fetchall()
            if (
                source["history_policy"] == history_policy
                and source["history_limit"]
                == (history_limit if history_policy == "latest_n" else None)
                and source["history_updated_at"]
            ):
                return sum(r["queued_history"] for r in rows)
            selected = (
                rows
                if history_policy == "all"
                else rows[:history_limit]
                if history_policy == "latest_n"
                else []
            )
            ids = {r["bvid"] for r in selected}
            for r in rows:
                c.execute(
                    "UPDATE shiliu.video_source_memberships SET queued_history=%s,is_baseline=CASE WHEN %s THEN false ELSE is_baseline END "
                    "WHERE workspace_id=%s AND source_id=%s AND bvid=%s",
                    (
                        r["bvid"] in ids and r["video_id"] is None,
                        r["bvid"] in ids,
                        self.workspace_id,
                        source_db_id,
                        r["bvid"],
                    ),
                )
            times = [
                r["favorite_time"] for r in selected if r["favorite_time"] is not None
            ]
            cutoff = (
                min(times)
                if times
                else int(datetime.now(timezone.utc).timestamp())
                if history_policy == "future_only"
                else None
            )
            c.execute(
                "UPDATE shiliu.favorite_sources SET history_policy=%s,history_limit=%s,history_cutoff_time=%s,"
                "history_updated_at=clock_timestamp(),updated_at=clock_timestamp() WHERE workspace_id=%s AND id=%s",
                (
                    history_policy,
                    history_limit if history_policy == "latest_n" else None,
                    cutoff,
                    self.workspace_id,
                    source_db_id,
                ),
            )
            return sum(r["bvid"] in ids and r["video_id"] is None for r in rows)

    def list_history_backlog(self, *, limit=8, source_ids=None):
        with self.connect(read_only=True) as c:
            return [
                collection_dto(r)
                for r in c.execute(
                    "SELECT m.*,s.folder_title,s.status AS source_status,s.cooldown_until "
                    "FROM shiliu.video_source_memberships m JOIN shiliu.favorite_sources s ON "
                    "(m.workspace_id,m.source_id)=(s.workspace_id,s.id) WHERE m.workspace_id=%s AND m.queued_history "
                    "AND m.removed_at IS NULL AND s.status='active' AND (%s::bigint[] IS NULL OR m.source_id=ANY(%s)) "
                    "ORDER BY m.first_observed_at,m.source_id,m.source_position LIMIT %s",
                    (
                        self.workspace_id,
                        list(source_ids) if source_ids is not None else None,
                        list(source_ids) if source_ids is not None else None,
                        limit,
                    ),
                ).fetchall()
            ]

    def materialize_history_membership(self, source_db_id, bvid):
        with self.connect(guard=True) as c:
            source = self._source(c, source_db_id, lock=True)
            row = c.execute(
                "SELECT * FROM shiliu.video_source_memberships WHERE workspace_id=%s AND source_id=%s AND bvid=%s "
                "AND removed_at IS NULL FOR UPDATE",
                (self.workspace_id, source_db_id, bvid),
            ).fetchone()
            if row is None or source["status"] != "active":
                raise KeyError((source_db_id, bvid))
            if row["video_id"] is not None:
                return int(row["video_id"])
            if not row["queued_history"]:
                raise KeyError((source_db_id, bvid))
            vid = self.create_video(
                bvid,
                row["title"],
                row["uploader"],
                display_favorite_time=row["favorite_time"]
                or int(row["first_observed_at"].timestamp()),
                conn=c,
            )
            c.execute(
                "UPDATE shiliu.video_source_memberships SET video_id=%s,queued_history=false,is_baseline=false "
                "WHERE workspace_id=%s AND source_id=%s AND bvid=%s",
                (vid, self.workspace_id, source_db_id, bvid),
            )
            self._touch(c, vid, reason="history_materialized")
            return vid

    def history_pending_count(self):
        with self.connect(read_only=True) as c:
            return c.execute(
                "SELECT COUNT(*) AS n FROM shiliu.video_source_memberships WHERE workspace_id=%s "
                "AND queued_history AND removed_at IS NULL",
                (self.workspace_id,),
            ).fetchone()["n"]

    def video_sources(self, video_id, *, connection=None):
        with self.connect(connection, read_only=True) as c:
            return [
                collection_dto(r)
                for r in c.execute(
                    "SELECT s.id,s.account_id,s.account_name,s.folder_id,s.folder_title,"
                    "m.favorite_time,m.removed_at FROM shiliu.video_source_memberships m JOIN shiliu.favorite_sources s "
                    "ON (m.workspace_id,m.source_id)=(s.workspace_id,s.id) WHERE m.workspace_id=%s AND m.video_id=%s "
                    "ORDER BY COALESCE(m.favorite_time,0) DESC,s.id",
                    (self.workspace_id, video_id),
                ).fetchall()
            ]

    def video_has_active_source(self, video_id, *, allowed_source_ids=None, conn=None):
        with self.connect(conn, read_only=True) as c:
            return (
                c.execute(
                    "SELECT 1 FROM shiliu.video_source_memberships m JOIN shiliu.favorite_sources s "
                    "ON (m.workspace_id,m.source_id)=(s.workspace_id,s.id) WHERE m.workspace_id=%s AND m.video_id=%s "
                    "AND m.removed_at IS NULL AND s.status='active' AND (%s::bigint[] IS NULL OR s.id=ANY(%s)) LIMIT 1",
                    (
                        self.workspace_id,
                        video_id,
                        list(allowed_source_ids)
                        if allowed_source_ids is not None
                        else None,
                        list(allowed_source_ids)
                        if allowed_source_ids is not None
                        else None,
                    ),
                ).fetchone()
                is not None
            )

    def source_sync_metrics(self, source_db_id):
        with self.connect(read_only=True) as c:
            source = self._source(c, source_db_id)
            rows = c.execute(
                "SELECT m.*,v.status FROM shiliu.video_source_memberships m LEFT JOIN shiliu.videos v "
                "ON (m.workspace_id,m.video_id)=(v.workspace_id,v.id) WHERE m.workspace_id=%s AND m.source_id=%s "
                "AND m.removed_at IS NULL",
                (self.workspace_id, source_db_id),
            ).fetchall()
            result = {
                "remote_detected": source["media_count"],
                "discovered_memberships": len(rows),
                "imported": sum(r["video_id"] is not None for r in rows),
                "completed": sum(r["status"] == "completed" for r in rows),
                "pending_history": sum(r["queued_history"] for r in rows),
                "pending_pipeline": sum(
                    r["status"]
                    in {
                        "discovered",
                        "subtitle_pending",
                        "transcript_processing",
                        "summary_processing",
                        "retry_wait",
                    }
                    for r in rows
                ),
                "failed": sum(r["status"] in {"needs_review", "failed"} for r in rows),
                "not_backfilled": sum(
                    r["video_id"] is None and not r["queued_history"] for r in rows
                ),
                "oldest_covered_favorite_time": min(
                    (
                        r["favorite_time"]
                        for r in rows
                        if r["video_id"] and r["favorite_time"] is not None
                    ),
                    default=None,
                ),
            }
            result["remote_unavailable"] = max(0, result["remote_detected"] - len(rows))
            result["pending"] = result["pending_history"] + result["pending_pipeline"]
            return result

    def list_video_cards(
        self,
        *,
        view: str = "feed",
        source_db_id: int | None = None,
    ) -> list[dict[str, Any]]:
        return self.page_video_cards(
            view=view,
            source_db_id=source_db_id,
            page_size=None,
        ).items

    def page_video_cards(
        self,
        *,
        view: str = "feed",
        source_db_id: int | None = None,
        page_size: int | None = 40,
        after: LibraryCardCursor | None = None,
        before: LibraryCardCursor | None = None,
    ) -> LibraryCardPage:
        conditions = {
            "feed": "v.archived_at IS NULL",
            "marked": "v.archived_at IS NULL AND v.is_marked",
            "noted": (
                "v.archived_at IS NULL AND EXISTS "
                "(SELECT 1 FROM video_notes vn WHERE vn.video_id=v.id AND vn.owner_user_id=(SELECT owner_user_id FROM shiliu.workspaces WHERE id=m.workspace_id))"
            ),
            "archived": "v.archived_at IS NOT NULL",
        }
        if view not in conditions:
            raise ValueError("Unsupported library view")
        if after is not None and before is not None:
            raise ValueError("Library page accepts only one cursor direction")
        if page_size is not None and not 1 <= page_size <= 200:
            raise ValueError("Library page size must be between 1 and 200")
        with self.connect(guard=True) as connection:
            return self._page_video_cards(
                connection,
                view=view,
                source_db_id=source_db_id,
                page_size=page_size,
                after=after,
                before=before,
            )

    def _page_video_cards(
        self, connection, *, view, source_db_id, page_size, after, before
    ):
        conditions = {
            "feed": "v.archived_at IS NULL",
            "marked": "v.archived_at IS NULL AND v.is_marked",
            "noted": "v.archived_at IS NULL AND EXISTS(SELECT 1 FROM shiliu.video_notes vn WHERE vn.video_id=v.id AND vn.workspace_id=v.workspace_id AND vn.owner_user_id=%s)",
            "archived": "v.archived_at IS NOT NULL",
        }
        snapshot_rowid = (
            after[5]
            if after is not None
            else before[5]
            if before is not None
            else self._library_membership_snapshot_rowid(connection)
        )
        if after is not None:
            after = self._refresh_library_card_cursor(after, connection=connection)
        if before is not None:
            before = self._refresh_library_card_cursor(before, connection=connection)
        params: list[Any] = [self.workspace_id]
        if view == "noted":
            params.append(self.context.user_id)
        source_clause = ""
        if source_db_id is not None:
            source_clause = " AND m.source_id=%s"
            params.append(source_db_id)
        params.append(snapshot_rowid)
        snapshot_position = f"""
            COALESCE(m.source_position, -1) - (
                SELECT COUNT(*)
                FROM video_source_memberships newer
                WHERE newer.workspace_id=m.workspace_id AND newer.source_id=m.source_id
                  AND newer.membership_seq>{snapshot_rowid}
                  AND newer.removed_at IS NULL
                  AND newer.video_id IS NOT NULL
                  AND COALESCE(newer.source_position, -1)
                      < COALESCE(m.source_position, -1)
            )
        """
        order_values = """
            COALESCE(
                m.favorite_time,
                v.display_favorite_time,
                floor(EXTRACT(EPOCH FROM m.first_observed_at))::bigint,
                0
            ),
            -({snapshot_position}),
            date_trunc('second',v.discovered_at),
            v.id,
            -m.source_id
        """.format(snapshot_position=snapshot_position)
        cursor_clause = ""
        if after is not None:
            cursor_clause = f" AND ({order_values}) < (%s, %s, %s, %s, %s)"
            params.extend(after[:5])
        elif before is not None:
            cursor_clause = f" AND ({order_values}) > (%s, %s, %s, %s, %s)"
            params.extend(before[:5])
        order_direction = "ASC" if before is not None else "DESC"
        limit_clause = ""
        if page_size is not None:
            limit_clause = " LIMIT %s"
            params.append(page_size + 1)
        with self.connect(connection) as connection:
            rows = connection.execute(
                f"""
                SELECT v.*,
                       m.source_id AS card_source_id,
                       m.favorite_time AS card_favorite_time,
                       m.source_position AS card_source_position,
                       m.first_observed_at AS card_first_observed_at,
                       s.account_id AS card_account_id,
                       s.account_name AS card_account_name,
                       s.folder_id AS card_folder_id,
                       s.folder_title AS card_folder_title,
                       COALESCE(
                           m.favorite_time,
                           v.display_favorite_time,
                           floor(EXTRACT(EPOCH FROM m.first_observed_at))::bigint,
                           0
                       ) AS card_order_favorite_time,
                       -({snapshot_position})
                           AS card_order_source_position_desc,
                       -m.source_id AS card_order_source_id_desc,
                       {snapshot_rowid} AS card_snapshot_rowid
                FROM video_source_memberships m
                JOIN videos v ON v.id=m.video_id
                JOIN favorite_sources s ON s.id=m.source_id
                WHERE m.workspace_id=%s AND m.removed_at IS NULL
                  AND m.video_id IS NOT NULL
                  AND {conditions[view]}
                  {source_clause}
                  AND m.membership_seq<=%s
                  {cursor_clause}
                ORDER BY COALESCE(
                             m.favorite_time,
                             v.display_favorite_time,
                             floor(EXTRACT(EPOCH FROM m.first_observed_at))::bigint,
                             0
                         ) {order_direction},
                         -({snapshot_position}) {order_direction},
                         date_trunc('second',v.discovered_at) {order_direction},
                         v.id {order_direction},
                         -m.source_id {order_direction}
                {limit_clause}
                """,
                params,
            ).fetchall()
        values = [collection_dto(row) for row in rows]
        if page_size is None:
            return self._finish_library_card_page(
                values,
                has_previous=False,
                has_next=False,
                snapshot_rowid=snapshot_rowid,
                connection=connection,
            )
        if before is not None:
            has_previous = len(values) > page_size
            return self._finish_library_card_page(
                list(reversed(values[:page_size])),
                has_previous=has_previous,
                has_next=True,
                snapshot_rowid=snapshot_rowid,
                connection=connection,
            )
        has_next = len(values) > page_size
        return self._finish_library_card_page(
            values[:page_size],
            has_previous=after is not None,
            has_next=has_next,
            snapshot_rowid=snapshot_rowid,
            connection=connection,
        )

    def _library_membership_snapshot_rowid(self, connection) -> int:
        with self.connect(connection) as connection:
            row = connection.execute(
                "SELECT membership_highwater FROM shiliu.workspace_guards WHERE workspace_id=%s",
                (self.workspace_id,),
            ).fetchone()
        return int(row["membership_highwater"])

    def _finish_library_card_page(
        self,
        items: list[dict[str, Any]],
        *,
        has_previous: bool,
        has_next: bool,
        snapshot_rowid: int,
        connection,
    ) -> LibraryCardPage:
        note_counts: dict[int, int] = {}
        video_ids = sorted({int(item["id"]) for item in items})
        if video_ids:
            placeholders = ",".join("%s" for _ in video_ids)
            with self.connect(connection) as connection:
                rows = connection.execute(
                    f"""
                    SELECT video_id, COUNT(*) AS note_count
                    FROM video_notes
                    WHERE workspace_id=%s AND owner_user_id=%s AND video_id IN ({placeholders})
                    GROUP BY video_id
                    """,
                    [self.workspace_id, self.context.user_id, *video_ids],
                ).fetchall()
            note_counts = {int(row["video_id"]): int(row["note_count"]) for row in rows}
        for item in items:
            item["note_count"] = note_counts.get(int(item["id"]), 0)
            item["card_snapshot_rowid"] = snapshot_rowid
        return LibraryCardPage(
            items=items,
            has_previous=has_previous,
            has_next=has_next,
            snapshot_rowid=snapshot_rowid,
        )

    def _refresh_library_card_cursor(
        self,
        cursor: LibraryCardCursor,
        *,
        connection,
    ) -> LibraryCardCursor:
        """Re-anchor a cursor after forward sync updates membership positions."""

        video_id = cursor[3]
        source_db_id = -cursor[4]
        snapshot_rowid = cursor[5]
        snapshot_position = f"""
            COALESCE(m.source_position, -1) - (
                SELECT COUNT(*)
                FROM video_source_memberships newer
                WHERE newer.workspace_id=m.workspace_id AND newer.source_id=m.source_id
                  AND newer.membership_seq>{snapshot_rowid}
                  AND newer.removed_at IS NULL
                  AND newer.video_id IS NOT NULL
                  AND COALESCE(newer.source_position, -1)
                      < COALESCE(m.source_position, -1)
            )
        """
        with self.connect(connection) as connection:
            row = connection.execute(
                f"""
                SELECT v.id, date_trunc('second',v.discovered_at) AS discovered_at, m.source_id AS card_source_id,
                       COALESCE(
                           m.favorite_time,
                           v.display_favorite_time,
                           floor(EXTRACT(EPOCH FROM m.first_observed_at))::bigint,
                           0
                       ) AS card_order_favorite_time,
                       -({snapshot_position})
                           AS card_order_source_position_desc,
                       -m.source_id AS card_order_source_id_desc,
                       {snapshot_rowid} AS card_snapshot_rowid
                FROM video_source_memberships m
                JOIN videos v ON v.id=m.video_id
                WHERE m.workspace_id=%s AND v.id=%s AND m.source_id=%s AND m.membership_seq<=%s
                """,
                (self.workspace_id, video_id, source_db_id, snapshot_rowid),
            ).fetchone()
        return library_card_cursor(collection_dto(row)) if row is not None else cursor

    def set_reading_state(self, video_id, state):
        self.update_video(
            video_id, reading_state=state, reading_state_updated_at=utc_now()
        )

    def set_marked(self, video_id, marked):
        self.update_video(
            video_id, is_marked=bool(marked), marked_at=utc_now() if marked else None
        )

    def set_archived(self, video_id, archived):
        self.update_video(video_id, archived_at=utc_now() if archived else None)

    def set_ignored(self, video_id, ignored):
        self.update_video(
            video_id,
            is_ignored=bool(ignored),
            ignored_at=utc_now() if ignored else None,
        )

    def create_note(self, video_id, content, *, conn=None):
        with self.connect(conn, guard=True) as c:
            self._video(c, video_id, lock=True)
            row = c.execute(
                "INSERT INTO shiliu.video_notes(workspace_id,owner_user_id,video_id,content,created_at,updated_at) "
                "VALUES(%s,%s,%s,%s,clock_timestamp(),clock_timestamp()) RETURNING *",
                (self.workspace_id, self.context.user_id, video_id, content),
            ).fetchone()
            self._touch(c, video_id, reason="note_created")
            return collection_dto(row)

    def get_note(self, note_id, *, conn=None):
        with self.connect(conn, read_only=True) as c:
            return collection_dto(
                c.execute(
                    "SELECT * FROM shiliu.video_notes WHERE workspace_id=%s AND owner_user_id=%s "
                    "AND id=%s",
                    (self.workspace_id, self.context.user_id, note_id),
                ).fetchone()
            )

    def update_note(self, note_id, content):
        with self.connect(guard=True) as c:
            row = c.execute(
                "UPDATE shiliu.video_notes SET content=%s,updated_at=clock_timestamp() "
                "WHERE workspace_id=%s AND owner_user_id=%s AND id=%s RETURNING *",
                (content, self.workspace_id, self.context.user_id, note_id),
            ).fetchone()
            if row:
                self._touch(c, row["video_id"], reason="note_updated")
            return collection_dto(row)

    def delete_note(self, note_id):
        with self.connect(guard=True) as c:
            row = c.execute(
                "DELETE FROM shiliu.video_notes WHERE workspace_id=%s AND owner_user_id=%s AND id=%s RETURNING video_id",
                (self.workspace_id, self.context.user_id, note_id),
            ).fetchone()
            if row:
                self._touch(c, row["video_id"], reason="note_deleted")

    def list_notes(self, video_id):
        return self.list_notes_for_videos([video_id]).get(video_id, [])

    def list_notes_for_videos(self, video_ids, *, conn=None):
        result = {vid: [] for vid in set(video_ids)}
        with self.connect(conn, read_only=True) as c:
            for row in c.execute(
                "SELECT * FROM shiliu.video_notes WHERE workspace_id=%s AND owner_user_id=%s "
                "AND video_id=ANY(%s) ORDER BY created_at,id",
                (self.workspace_id, self.context.user_id, list(result)),
            ).fetchall():
                result[row["video_id"]].append(collection_dto(row))
        return result

    def update_video_durations(self, items):
        changed = 0
        with self.connect(guard=True) as c:
            for item in items:
                if item.duration_seconds <= 0:
                    continue
                row = c.execute(
                    "UPDATE shiliu.videos SET duration_seconds=%s,updated_at=clock_timestamp() WHERE workspace_id=%s "
                    "AND platform='bilibili' AND source_id=%s AND part=1 AND duration_seconds<=0 RETURNING id",
                    (item.duration_seconds, self.workspace_id, item.bvid),
                ).fetchone()
                if row:
                    changed += 1
                    self._touch(c, row["id"], reason="duration_backfill")
        return changed

    def list_processable_videos(self, now=None):
        # Due admission always uses the database wall clock, not caller time.
        with self.connect(read_only=True) as c:
            return [
                collection_dto(r)
                for r in c.execute(
                    "SELECT * FROM shiliu.videos WHERE workspace_id=%s AND status IN "
                    "('discovered','subtitle_pending','transcript_processing','summary_processing','retry_wait') "
                    "AND (subtitle_next_check_at IS NULL OR subtitle_next_check_at<=clock_timestamp()) ORDER BY discovered_at,id",
                    (self.workspace_id,),
                ).fetchall()
            ]

    def ensure_asr_job(self, video_id, *, provider, model, trigger_mode, conn=None):
        with self.connect(conn) as c:
            self._video(c, video_id)
            c.execute(
                "INSERT INTO shiliu.asr_jobs(workspace_id,video_id,provider,model,trigger_mode,status,created_at,updated_at) "
                "VALUES(%s,%s,%s,%s,%s,'pending',clock_timestamp(),clock_timestamp()) ON CONFLICT(video_id) DO NOTHING",
                (self.workspace_id, video_id, provider, model, trigger_mode),
            )
            return self.get_asr_job(video_id, conn=c)

    def get_asr_job(self, video_id, *, conn=None):
        with self.connect(conn, read_only=True) as c:
            return collection_dto(
                c.execute(
                    "SELECT * FROM shiliu.asr_jobs WHERE workspace_id=%s AND video_id=%s",
                    (self.workspace_id, video_id),
                ).fetchone()
            )

    def update_asr_job(self, video_id, *, claim=None, conn=None, **fields):
        with self.connect(conn) as c:
            if claim is not None:
                self.check_lease(c, "asr_jobs", claim)
            else:
                self._assert_unclaimed(c, "asr_jobs", "video_id=%s", [video_id])
            self._update(c, "asr_jobs", fields, ASR_FIELDS, "video_id=%s", [video_id])

    def ensure_stage(self, video_id, stage, *, conn=None):
        with self.connect(conn) as c:
            self._video(c, video_id)
            c.execute(
                "INSERT INTO shiliu.pipeline_stages(workspace_id,video_id,stage_name,status,updated_at) "
                "VALUES(%s,%s,%s,'pending',clock_timestamp()) ON CONFLICT(video_id,stage_name) DO NOTHING",
                (self.workspace_id, video_id, stage.value),
            )
            return self.get_stage(video_id, stage, conn=c)

    def get_stage(self, video_id, stage, *, conn=None):
        with self.connect(conn, read_only=True) as c:
            return collection_dto(
                c.execute(
                    "SELECT * FROM shiliu.pipeline_stages WHERE workspace_id=%s AND video_id=%s "
                    "AND stage_name=%s",
                    (self.workspace_id, video_id, stage.value),
                ).fetchone()
            )

    def update_stage(self, video_id, stage, *, claim=None, conn=None, **fields):
        with self.connect(conn) as c:
            if claim is not None:
                self.check_lease(c, "pipeline_stages", claim)
            else:
                self._assert_unclaimed(
                    c,
                    "pipeline_stages",
                    "video_id=%s AND stage_name=%s",
                    [video_id, stage.value],
                )
            self._update(
                c,
                "pipeline_stages",
                fields,
                STAGE_FIELDS,
                "video_id=%s AND stage_name=%s",
                [video_id, stage.value],
            )

    def reset_failed_stages(self, video_id):
        with self.connect(guard=True) as c:
            self._video(c, video_id, lock=True)
            c.execute(
                "UPDATE shiliu.pipeline_stages SET status='pending',attempt_count=0,next_retry_at=NULL,"
                "last_error_code=NULL,lease_owner=NULL,lease_until=NULL,lease_epoch=lease_epoch+1,updated_at=clock_timestamp() "
                "WHERE workspace_id=%s AND video_id=%s AND status IN ('retry_wait','needs_review')",
                (self.workspace_id, video_id),
            )
            c.execute(
                "UPDATE shiliu.videos SET status=CASE WHEN transcript_path IS NOT NULL THEN 'summary_processing' "
                "WHEN raw_subtitle_path IS NOT NULL THEN 'transcript_processing' ELSE 'discovered' END,"
                "error_code=NULL,error_message=NULL,subtitle_next_check_at=NULL,updated_at=clock_timestamp() "
                "WHERE workspace_id=%s AND id=%s",
                (self.workspace_id, video_id),
            )
            self._touch(c, video_id, reason="retry_reset")

    def add_event(self, event_type, video_id, payload, *, conn=None):
        with self.connect(conn) as c:
            if video_id is not None:
                self._video(c, video_id)
            c.execute(
                "INSERT INTO shiliu.events(workspace_id,event_type,video_id,payload_json,created_at) "
                "VALUES(%s,%s,%s,%s,clock_timestamp())",
                (self.workspace_id, event_type, video_id, Jsonb(payload)),
            )

    def start_sync_run(self, mode, *, scope_source_id=None):
        with self.connect() as c:
            if scope_source_id is not None:
                self._source(c, scope_source_id)
            return c.execute(
                "INSERT INTO shiliu.sync_runs(workspace_id,mode,status,scope_source_id,started_at,heartbeat_at,current_phase) "
                "VALUES(%s,%s,'running',%s,clock_timestamp(),clock_timestamp(),'starting') RETURNING id",
                (self.workspace_id, mode, scope_source_id),
            ).fetchone()["id"]

    def update_sync_run(self, run_id, **fields):
        if set(fields) - SYNC_FIELDS:
            raise ValueError("Unsupported sync fields")
        assignments = sql.SQL(",").join(
            sql.SQL("{}=%s").format(sql.Identifier(k)) for k in fields
        )
        with self.connect() as c:
            c.execute(
                sql.SQL(
                    "UPDATE shiliu.sync_runs SET {},heartbeat_at=clock_timestamp() WHERE workspace_id=%s AND id=%s"
                ).format(assignments),
                [*fields.values(), self.workspace_id, run_id],
            )

    def finish_sync_run(self, run_id, *, status, **counts):
        fields = {k: v for k, v in counts.items() if k in SYNC_FIELDS}
        with self.connect() as c:
            if fields:
                c.execute(
                    sql.SQL(
                        "UPDATE shiliu.sync_runs SET {} WHERE workspace_id=%s AND id=%s"
                    ).format(
                        sql.SQL(",").join(
                            sql.SQL("{}=%s").format(sql.Identifier(k)) for k in fields
                        )
                    ),
                    [*fields.values(), self.workspace_id, run_id],
                )
            c.execute(
                "UPDATE shiliu.sync_runs SET status=%s,finished_at=clock_timestamp(),heartbeat_at=clock_timestamp() "
                "WHERE workspace_id=%s AND id=%s",
                (status, self.workspace_id, run_id),
            )

    def get_sync_run(self, run_id):
        with self.connect(read_only=True) as c:
            return collection_dto(
                c.execute(
                    "SELECT * FROM shiliu.sync_runs WHERE workspace_id=%s AND id=%s",
                    (self.workspace_id, run_id),
                ).fetchone()
            )

    def latest_sync_run(self):
        with self.connect(read_only=True) as c:
            return collection_dto(
                c.execute(
                    "SELECT * FROM shiliu.sync_runs WHERE workspace_id=%s ORDER BY id DESC LIMIT 1",
                    (self.workspace_id,),
                ).fetchone()
            )

    def active_sync_run(self):
        with self.connect(read_only=True) as c:
            return collection_dto(
                c.execute(
                    "SELECT * FROM shiliu.sync_runs WHERE workspace_id=%s AND status='running' ORDER BY id DESC LIMIT 1",
                    (self.workspace_id,),
                ).fetchone()
            )

    def recover_stale_sync_runs(self, *, exclude_run_id=None):
        with self.connect() as c:
            rows = c.execute(
                "SELECT id FROM shiliu.sync_runs WHERE workspace_id=%s AND status='running' "
                "AND (%s::bigint IS NULL OR id<>%s) AND COALESCE(heartbeat_at,started_at)<clock_timestamp()-interval '10 minutes' "
                "ORDER BY id FOR UPDATE SKIP LOCKED",
                (self.workspace_id, exclude_run_id, exclude_run_id),
            ).fetchall()
            for row in rows:
                # Fresh statement after the run lock: an earlier statement's
                # no-active-source snapshot may predate an unrelated lease claim.
                c.execute(
                    "UPDATE shiliu.sync_runs r SET status='interrupted',finished_at=clock_timestamp(),"
                    "error_summary='应用进程中断，等待下次同步恢复' WHERE r.workspace_id=%s AND r.id=%s AND r.status='running' "
                    "AND COALESCE(r.heartbeat_at,r.started_at)<clock_timestamp()-interval '10 minutes' "
                    "AND NOT EXISTS(SELECT 1 FROM shiliu.favorite_sources s WHERE s.workspace_id=r.workspace_id "
                    "AND s.lease_owner IS NOT NULL AND s.lease_until>clock_timestamp())",
                    (self.workspace_id, row["id"]),
                )

    def update_source_error(
        self, source_db_id, *, status, code, message, cooldown_until=None, claim=None
    ):
        with self._source_write(claim) as c:
            self._source(c, source_db_id, lock=True)
            if claim is not None:
                self.check_lease(c, "favorite_sources", claim)
            else:
                self._assert_unclaimed(c, "favorite_sources", "id=%s", [source_db_id])
            c.execute(
                "UPDATE shiliu.favorite_sources SET status=%s,last_error_code=%s,last_error_message=%s,"
                "cooldown_until=%s,updated_at=clock_timestamp() WHERE workspace_id=%s AND id=%s",
                (
                    status,
                    code,
                    message,
                    cooldown_until,
                    self.workspace_id,
                    source_db_id,
                ),
            )
            self._touch_source(c, source_db_id, "source_error")

    def _assert_unclaimed(self, c, table, predicate, params):
        row = c.execute(
            sql.SQL(
                "SELECT lease_owner,lease_until FROM shiliu.{} WHERE workspace_id=%s AND "
            ).format(sql.Identifier(table))
            + sql.SQL(predicate + " FOR UPDATE"),
            [self.workspace_id, *params],
        ).fetchone()
        if row is not None and row["lease_owner"] is not None:
            raise CoordinationConflict("claim_required")

    def claim_source(self, source_id, owner, *, seconds=120):
        return self._claim("favorite_sources", "id=%s", [source_id], owner, seconds)

    def claim_asr(self, video_id, owner, *, seconds=120):
        return self._claim("asr_jobs", "video_id=%s", [video_id], owner, seconds)

    def claim_stage(self, video_id, stage, owner, *, seconds=120):
        return self._claim(
            "pipeline_stages",
            "video_id=%s AND stage_name=%s",
            [video_id, stage.value],
            owner,
            seconds,
        )

    def _claim(self, table, predicate, params, owner, seconds):
        if not owner or not 0 < seconds <= 600:
            raise ValueError("Invalid lease")
        with self.connect() as c:
            row = c.execute(
                sql.SQL("SELECT * FROM shiliu.{} WHERE workspace_id=%s AND ").format(
                    sql.Identifier(table)
                )
                + sql.SQL(predicate + " FOR UPDATE"),
                [self.workspace_id, *params],
            ).fetchone()
            if row is None:
                raise KeyError(params)
            if row["lease_owner"] and self._lease_live(c, row["lease_until"]):
                return None
            if table != "favorite_sources":
                if row["status"] == "completed":
                    return None
                due = c.execute(
                    "SELECT %s::timestamptz IS NULL OR %s::timestamptz<=clock_timestamp() AS due",
                    (row["next_retry_at"], row["next_retry_at"]),
                ).fetchone()["due"]
                if not due:
                    return None
                # A worker died while an external request might have been sent.
                # task_id is a safe poll identity. Missing identity requires review.
                uncertain = (
                    table == "asr_jobs"
                    and not row["task_id"]
                    and row["status"] in {"submitted", "processing"}
                ) or (
                    table == "pipeline_stages"
                    and row["status"] == "processing"
                    and row["stage_name"] != "source_fetch"
                )
                if uncertain:
                    c.execute(
                        sql.SQL(
                            "UPDATE shiliu.{} SET status='needs_review',last_error_code='external_result_unknown',"
                            "lease_owner=NULL,lease_until=NULL,lease_epoch=lease_epoch+1 WHERE workspace_id=%s AND id=%s"
                        ).format(sql.Identifier(table)),
                        (self.workspace_id, row["id"]),
                    )
                    return None
                if row["status"] == "needs_review":
                    return None
            return collection_dto(
                c.execute(
                    sql.SQL(
                        "UPDATE shiliu.{} SET lease_owner=%s,lease_epoch=lease_epoch+1,"
                        "lease_until=clock_timestamp()+%s*interval '1 second' WHERE workspace_id=%s AND id=%s RETURNING *"
                    ).format(sql.Identifier(table)),
                    (owner, seconds, self.workspace_id, row["id"]),
                ).fetchone()
            )

    @staticmethod
    def _lease_live(c, until):
        # Only call after acquiring the resource row lock. A volatile expression
        # in the locking SELECT can be evaluated before its LockRows wait.
        return c.execute(
            "SELECT %s::timestamptz>clock_timestamp() AS live", (until,)
        ).fetchone()["live"]

    def check_lease(self, c, table, claim, *, renewal=False):
        if table not in {"favorite_sources", "asr_jobs", "pipeline_stages"}:
            raise ValueError("Invalid lease domain")
        row = c.execute(
            sql.SQL(
                "SELECT * FROM shiliu.{} WHERE workspace_id=%s AND id=%s "
            ).format(sql.Identifier(table))
            + sql.SQL("FOR NO KEY UPDATE" if table == "favorite_sources" and renewal else "FOR UPDATE"),
            (
                self.workspace_id,
                claim["id"],
            ),
        ).fetchone()
        if (
            row is None
            or row["lease_owner"] != claim["lease_owner"]
            or row["lease_epoch"] != claim["lease_epoch"]
            or not self._lease_live(c, row["lease_until"])
        ):
            raise CoordinationConflict("lease_fenced")
        return row

    def heartbeat(self, table, claim, *, seconds=120):
        if not 0 < seconds <= 600:
            raise ValueError("Invalid lease duration")
        local = self._source_lease_lock(claim) if table == "favorite_sources" else nullcontext()
        with local, self.connect() as c:
            self.check_lease(c, table, claim, renewal=True)
            c.execute(
                sql.SQL(
                    "UPDATE shiliu.{} SET lease_until=clock_timestamp()+%s*interval '1 second' "
                    "WHERE workspace_id=%s AND id=%s"
                ).format(sql.Identifier(table)),
                (seconds, self.workspace_id, claim["id"]),
            )

    def release(self, table, claim, *, conn=None):
        with self.connect(conn) as c:
            self.check_lease(c, table, claim)
            c.execute(
                sql.SQL(
                    "UPDATE shiliu.{} SET lease_owner=NULL,lease_until=NULL WHERE workspace_id=%s AND id=%s "
                    "AND lease_owner=%s AND lease_epoch=%s"
                ).format(sql.Identifier(table)),
                (
                    self.workspace_id,
                    claim["id"],
                    claim["lease_owner"],
                    claim["lease_epoch"],
                ),
            )

    def _notify_assistant_source_change(self, c, video_id, *, reason):
        memberships = {
            r["source_id"]
            for r in c.execute(
                "SELECT m.source_id FROM shiliu.video_source_memberships m "
                "JOIN shiliu.favorite_sources s ON (m.workspace_id,m.source_id)=(s.workspace_id,s.id) "
                "WHERE m.workspace_id=%s AND m.video_id=%s AND m.removed_at IS NULL AND s.status='active'",
                (self.workspace_id, video_id),
            ).fetchall()
        }
        video = self._video(c, video_id)
        if video["is_ignored"] or video["archived_at"] or video["removed_at"]:
            memberships = set()
        visible = set()
        automatic = False
        spaces = c.execute(
            "SELECT * FROM shiliu.assistant_spaces WHERE workspace_id=%s AND principal_id=%s AND enabled",
            (self.workspace_id, self.context.user_id),
        ).fetchall()
        for space in spaces:
            if space["video_ids_json"] and video_id not in space["video_ids_json"]:
                continue
            if memberships and (
                space["all_active"]
                or memberships.intersection(space["source_ids_json"])
            ):
                visible.add(space["id"])
                automatic |= space["maintenance_mode"] == "automatic"
        lost = c.execute(
            "SELECT p.id,p.title,p.space_id,s.scope_version,s.maintenance_mode,s.source_ids_json,"
            "s.video_ids_json,s.all_active FROM shiliu.assistant_wiki_materials m JOIN shiliu.assistant_wiki_pages p "
            "ON p.id=m.page_id JOIN shiliu.assistant_spaces s ON s.id=p.space_id "
            "WHERE m.workspace_id=%s AND m.video_id=%s AND p.principal_id=%s AND p.status='active' AND s.enabled",
            (self.workspace_id, video_id, self.context.user_id),
        ).fetchall()
        lost = [p for p in lost if p["space_id"] not in visible]
        if not visible and not lost:
            return
        generation = c.execute(
            "INSERT INTO shiliu.assistant_source_dirty(workspace_id,video_id,dirty_generation,updated_at) "
            "VALUES(%s,%s,1,clock_timestamp()) ON CONFLICT(video_id) DO UPDATE SET "
            "dirty_generation=assistant_source_dirty.dirty_generation+1,updated_at=excluded.updated_at RETURNING dirty_generation",
            (self.workspace_id, video_id),
        ).fetchone()["dirty_generation"]

        def job(kind, key, payload):
            c.execute(
                "INSERT INTO shiliu.assistant_jobs(workspace_id,principal_id,id,kind,dedupe_key,status,payload_json,"
                "not_before,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,'queued',%s,clock_timestamp(),clock_timestamp(),clock_timestamp()) "
                "ON CONFLICT(workspace_id,principal_id,dedupe_key) DO NOTHING",
                (
                    self.workspace_id,
                    self.context.user_id,
                    "ajob_" + uuid.uuid4().hex,
                    kind,
                    key,
                    Jsonb(payload),
                ),
            )

        for page in lost:
            if page["maintenance_mode"] != "automatic":
                continue
            candidates = c.execute(
                "SELECT m.video_id,h.current_revision FROM shiliu.assistant_wiki_materials m "
                "JOIN shiliu.assistant_source_heads h ON (h.workspace_id,h.video_id)=(m.workspace_id,m.video_id) "
                "JOIN shiliu.assistant_source_cards sc ON sc.revision=h.current_revision "
                "JOIN shiliu.videos v ON (v.workspace_id,v.id)=(m.workspace_id,m.video_id) "
                "WHERE m.workspace_id=%s AND m.page_id=%s AND m.video_id<>%s AND h.principal_id=%s "
                "AND NOT v.is_ignored AND v.archived_at IS NULL AND v.removed_at IS NULL ORDER BY m.updated_at DESC",
                (self.workspace_id, page["id"], video_id, self.context.user_id),
            ).fetchall()
            for candidate in candidates:
                vid = candidate["video_id"]
                if page["video_ids_json"] and vid not in page["video_ids_json"]:
                    continue
                allowed = None if page["all_active"] else set(page["source_ids_json"])
                if not self.video_has_active_source(
                    vid, allowed_source_ids=allowed, conn=c
                ):
                    continue
                job(
                    "wiki_integrate",
                    f"wiki_repair:{page['id']}:{video_id}:{generation}",
                    {
                        "space_id": page["space_id"],
                        "scope_version": page["scope_version"],
                        "video_id": vid,
                        "revision": candidate["current_revision"],
                        "topic": page["title"],
                        "repair_page_id": page["id"],
                        "lost_video_id": video_id,
                    },
                )
                break
        if automatic:
            job(
                "source_reconcile",
                f"source_reconcile:{video_id}:{generation}",
                {
                    "video_id": video_id,
                    "dirty_generation": generation,
                    "reason": reason,
                },
            )

    def has_baseline(self):
        with self.connect(read_only=True) as c:
            return (
                c.execute(
                    "SELECT 1 FROM shiliu.assistant_runtime_state WHERE workspace_id=%s AND principal_id=%s "
                    "AND key='collection:baseline_initialized' AND value='1'",
                    (self.workspace_id, self.context.user_id),
                ).fetchone()
                is not None
                or c.execute(
                    "SELECT 1 FROM shiliu.favorite_sources WHERE workspace_id=%s AND baseline_initialized LIMIT 1",
                    (self.workspace_id,),
                ).fetchone()
                is not None
            )

    def establish_baseline(self, source_ids, *, platform="bilibili"):
        with self.connect(guard=True) as c:
            for source_id in source_ids:
                self.mark_seen(source_id, is_baseline=True, platform=platform, conn=c)
            c.execute(
                "INSERT INTO shiliu.assistant_runtime_state(workspace_id,principal_id,key,value,updated_at) "
                "VALUES(%s,%s,'collection:baseline_initialized','1',clock_timestamp()) "
                "ON CONFLICT(workspace_id,principal_id,key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                (self.workspace_id, self.context.user_id),
            )

    def seen_source_ids(self, *, platform="bilibili"):
        with self.connect(read_only=True) as c:
            return {
                r["source_id"]
                for r in c.execute(
                    "SELECT source_id FROM shiliu.seen_items WHERE workspace_id=%s "
                    "AND platform=%s AND part=1",
                    (self.workspace_id, platform),
                ).fetchall()
            }

    def mark_seen(
        self, source_id, *, is_baseline=False, platform="bilibili", conn=None
    ):
        with self.connect(conn) as c:
            c.execute(
                "INSERT INTO shiliu.seen_items(workspace_id,platform,source_id,part,is_baseline,first_seen_at,last_seen_at) "
                "VALUES(%s,%s,%s,1,%s,clock_timestamp(),clock_timestamp()) ON CONFLICT(workspace_id,platform,source_id,part) "
                "DO UPDATE SET last_seen_at=excluded.last_seen_at,removed_at=NULL",
                (self.workspace_id, platform, source_id, is_baseline),
            )

    def reconcile_current_items(self, current_ids, *, platform="bilibili"):
        with self.connect(guard=True) as c:
            c.execute(
                "UPDATE shiliu.seen_items SET removed_at=CASE WHEN source_id=ANY(%s) THEN NULL ELSE "
                "COALESCE(removed_at,clock_timestamp()) END,last_seen_at=CASE WHEN source_id=ANY(%s) THEN "
                "clock_timestamp() ELSE last_seen_at END WHERE workspace_id=%s AND platform=%s AND part=1",
                (list(current_ids), list(current_ids), self.workspace_id, platform),
            )
            rows = c.execute(
                "UPDATE shiliu.videos SET removed_at=CASE WHEN source_id=ANY(%s) THEN NULL ELSE "
                "COALESCE(removed_at,clock_timestamp()) END,updated_at=clock_timestamp() WHERE workspace_id=%s AND platform=%s "
                "AND part=1 RETURNING id",
                (list(current_ids), self.workspace_id, platform),
            ).fetchall()
            for row in rows:
                self._touch(c, row["id"], reason="legacy_reconciled")
