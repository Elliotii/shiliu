"""Durable Collection projection intents and fenced local-computation worker."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from threading import Event, Thread
from contextlib import contextmanager
from uuid import uuid4
import json

from psycopg import sql
from psycopg.types.json import Jsonb

from shiliu.retrieval.service import RebuildStats
from shiliu.storage.fences import CoordinationConflict

SYNC_STATE_VERSION = "pg-collection-projection-v1"


class ProjectionStale(CoordinationConflict):
    pass


def fingerprint(snapshot):
    return sha256(
        json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=lambda v: asdict(v),
        ).encode()
    ).hexdigest()


class ProjectionWorker:
    def __init__(self, lexical, dense=None, *, owner=None, lease_seconds=120):
        self.lexical, self.dense = lexical, dense
        self.db = lexical.db
        self.owner = owner or "projection_" + uuid4().hex
        if not 0 < lease_seconds <= 600:
            raise ValueError("Invalid projection lease")
        self.lease_seconds = lease_seconds

    def recover(self):
        # Only deterministic local tokenization/encoding belongs to this queue.
        # A lost lease is safe to retry; no model API/ASR request can enter here.
        with self.db.connect() as c:
            # The timestamp predicate only narrows candidates. SKIP LOCKED
            # avoids waiting on live publishers; each decision uses fresh time
            # in a separate statement after its row is locked.
            rows = c.execute(
                "SELECT id,lease_until FROM shiliu.retrieval_projection_tasks "
                "WHERE workspace_id=%s AND domain='collection' AND status='running' "
                "AND lease_until<=clock_timestamp() ORDER BY id FOR UPDATE SKIP LOCKED",
                (self.db.workspace_id,),
            ).fetchall()
            for row in rows:
                if not c.execute(
                    "SELECT %s::timestamptz<=clock_timestamp() AS expired",
                    (row["lease_until"],),
                ).fetchone()["expired"]:
                    continue
                c.execute(
                    "UPDATE shiliu.retrieval_projection_tasks SET status=CASE WHEN attempt>=5 THEN 'failed' ELSE 'retry_wait' END,"
                    "not_before=clock_timestamp()+interval '1 second',lease_owner=NULL,lease_until=NULL,last_error='local_projection_interrupted',updated_at=clock_timestamp() "
                    "WHERE workspace_id=%s AND id=%s",
                    (self.db.workspace_id, row["id"]),
                )

    def claim(self, *, video_id=None):
        self.recover()
        if self.dense is not None:
            self.dense.register()
        with self.db.connect() as c:
            task = c.execute(
                "SELECT * FROM shiliu.retrieval_projection_tasks WHERE workspace_id=%s AND domain='collection' "
                "AND status IN ('queued','retry_wait') AND attempt<5 AND not_before<=clock_timestamp() AND (%s::text IS NULL OR resource_key=%s) "
                "AND (%s::text IS NULL OR payload->>'target_profile' IS NULL OR payload->>'target_profile'=%s) "
                "ORDER BY not_before,id FOR UPDATE SKIP LOCKED LIMIT 1",
                (
                    self.db.workspace_id,
                    str(video_id) if video_id is not None else None,
                    str(video_id) if video_id is not None else None,
                    self.dense.profile_id if self.dense else None,
                    self.dense.profile_id if self.dense else None,
                ),
            ).fetchone()
            if task is None:
                return None
            if not c.execute(
                "SELECT %s::timestamptz<=clock_timestamp() AS due",
                (task["not_before"],),
            ).fetchone()["due"]:
                return None
            payload = dict(task["payload"])
            if self.dense is not None:
                target = payload.get("target_profile")
                if target and target != self.dense.profile_id:
                    return None
                payload["target_profile"] = self.dense.profile_id
            task = c.execute(
                "UPDATE shiliu.retrieval_projection_tasks SET status='running',payload=%s,attempt=attempt+1,lease_owner=%s,"
                "lease_epoch=lease_epoch+1,lease_until=clock_timestamp()+%s*interval '1 second',updated_at=clock_timestamp() "
                "WHERE workspace_id=%s AND id=%s RETURNING *",
                (
                    Jsonb(payload),
                    self.owner,
                    self.lease_seconds,
                    self.db.workspace_id,
                    task["id"],
                ),
            ).fetchone()
            return task

    def _lock_claim(self, c, claim):
        task = c.execute(
            "SELECT * FROM shiliu.retrieval_projection_tasks WHERE workspace_id=%s "
            "AND domain='collection' AND id=%s FOR UPDATE",
            (self.db.workspace_id, claim["id"]),
        ).fetchone()
        if (
            task is None
            or task["status"] != "running"
            or task["lease_owner"] != self.owner
            or task["lease_epoch"] != claim["lease_epoch"]
            or task["requested_generation"] != claim["requested_generation"]
            or task["payload"] != claim["payload"]
        ):
            raise ProjectionStale("projection_request_changed")
        # Evaluate only after the locking query returns. A time predicate in a
        # locking SELECT/UPDATE may already have passed before a row-lock wait.
        if not c.execute(
            "SELECT %s::timestamptz>clock_timestamp() AS live", (task["lease_until"],)
        ).fetchone()["live"]:
            raise ProjectionStale("projection_lease_fenced")
        return task

    def heartbeat(self, claim):
        with self.db.connect() as c:
            self._lock_claim(c, claim)
            c.execute(
                "UPDATE shiliu.retrieval_projection_tasks SET lease_until=clock_timestamp()+%s*interval '1 second' "
                "WHERE workspace_id=%s AND id=%s",
                (
                    self.lease_seconds,
                    self.db.workspace_id,
                    claim["id"],
                ),
            )

    @contextmanager
    def renewing(self, claim):
        stop = Event()

        def run():
            while not stop.wait(self.lease_seconds / 3):
                try:
                    self.heartbeat(claim)
                except Exception:
                    return

        thread = Thread(target=run, name="projection-lease", daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            # Do not return while a heartbeat can still use the owned pool.
            # Connection acquisition/lock/statement timeouts bound this join;
            # Application retains its pool if its outer drain limit expires.
            thread.join()

    def _state(self, c, video_id):
        video = self.db.get_video(video_id, conn=c)
        if video is None:
            return None
        video["_snapshot_folders"] = self.lexical._active_folders(video_id, conn=c)
        video["_snapshot_notes"] = self.db.list_notes_for_videos([video_id], conn=c)[
            video_id
        ]
        video["_visible"] = not video["removed_at"] and bool(video["_snapshot_folders"])
        return video

    def snapshot(self, claim):
        with self.db.pg.transaction(read_only=True, isolation="repeatable read") as c:
            task = c.execute(
                "SELECT * FROM shiliu.retrieval_projection_tasks WHERE workspace_id=%s AND id=%s AND status='running' AND lease_owner=%s AND lease_epoch=%s AND requested_generation=%s AND lease_until>clock_timestamp()",
                (
                    self.db.workspace_id,
                    claim["id"],
                    self.owner,
                    claim["lease_epoch"],
                    claim["requested_generation"],
                ),
            ).fetchone()
            if task is None or task["payload"] != claim["payload"]:
                raise ProjectionStale("projection_request_changed")
            return self._state(c, int(claim["resource_key"]))

    def build(self, snapshot, claim):
        units = (
            self.lexical._build_video_units(snapshot, RebuildStats())
            if snapshot and snapshot["_visible"] and not claim["payload"].get("absent")
            else []
        )
        tokens = {
            u.unit_id: self.lexical.tokenizer.document(u.search_text) for u in units
        }
        return units, tokens

    def _publish_units(self, c, units, tokens, generation, video_id):
        fields = [
            "unit_id",
            "unit_type",
            "video_id",
            "platform",
            "source_id",
            "part",
            "title",
            "uploader",
            "chunk_id",
            "source_type",
            "start_time",
            "end_time",
            "source_text",
            "search_text",
            "content_hash",
            "index_version",
            "reading_state",
            "is_marked",
            "is_ignored",
            "archived_at",
            "removed_at",
        ]
        ids = [u.unit_id for u in units]
        c.execute(
            "DELETE FROM shiliu.retrieval_units WHERE workspace_id=%s AND video_id=%s AND NOT(unit_id=ANY(%s))",
            (self.db.workspace_id, video_id, ids),
        )
        columns = [
            *fields,
            "workspace_id",
            "generation",
            "tokenized_text",
            "search_vector",
        ]
        statement = sql.SQL(
            "INSERT INTO shiliu.retrieval_units({}) VALUES ({}) ON CONFLICT(workspace_id,unit_id) DO UPDATE SET {}"
        ).format(
            sql.SQL(",").join(map(sql.Identifier, columns)),
            sql.SQL(",").join(
                [sql.SQL("%s") for _ in columns[:-1]]
                + [sql.SQL("to_tsvector('simple',%s)")]
            ),
            sql.SQL(",").join(
                sql.SQL("{}=excluded.{}").format(sql.Identifier(k), sql.Identifier(k))
                for k in columns[1:]
            ),
        )
        for unit in sorted(units, key=lambda u: u.unit_id):
            values = [getattr(unit, k) for k in fields]
            c.execute(
                statement,
                [
                    *values,
                    self.db.workspace_id,
                    generation,
                    tokens[unit.unit_id],
                    tokens[unit.unit_id],
                ],
            )
            c.execute(
                "DELETE FROM shiliu.retrieval_unit_folders WHERE workspace_id=%s AND unit_id=%s",
                (self.db.workspace_id, unit.unit_id),
            )
            for folder in unit.folders:
                c.execute(
                    "INSERT INTO shiliu.retrieval_unit_folders(workspace_id,unit_id,source_db_id,folder_id,folder_title,favorite_time) VALUES(%s,%s,%s,%s,%s,%s)",
                    (
                        self.db.workspace_id,
                        unit.unit_id,
                        folder.source_db_id,
                        folder.folder_id,
                        folder.folder_title,
                        folder.favorite_time,
                    ),
                )

    def publish(self, claim, snapshot, units, tokens, *, vectors=None, error=None):
        with self.db.connect(guard=True) as c:
            video_id = int(claim["resource_key"])
            self.db._video(c, video_id, lock=True)
            task = self._lock_claim(c, claim)
            if fingerprint(self._state(c, video_id)) != fingerprint(snapshot):
                raise ProjectionStale("projection_source_changed")
            if (
                vectors is not None
                and task["payload"].get("target_profile") != self.dense.profile_id
            ):
                raise ProjectionStale("projection_profile_changed")
            self._publish_units(
                c, units, tokens, claim["requested_generation"], video_id
            )
            if vectors is not None:
                self.dense.publish(c, units, vectors, claim["requested_generation"])
            complete = not units or vectors is not None
            status = (
                "completed"
                if complete
                else "failed"
                if claim["attempt"] >= 5
                else "retry_wait"
            )
            payload = dict(
                task["payload"],
                ready_generation=claim["requested_generation"],
                lexical_profile=self.lexical.tokenizer.profile,
            )
            if vectors is not None:
                payload["ready_profile"] = self.dense.profile_id
            c.execute(
                "UPDATE shiliu.retrieval_projection_tasks SET status=%s,payload=%s,lease_owner=NULL,lease_until=NULL,last_error=%s,"
                "not_before=clock_timestamp()+%s*interval '1 second',updated_at=clock_timestamp() WHERE workspace_id=%s AND id=%s AND lease_owner=%s AND lease_epoch=%s AND requested_generation=%s",
                (
                    status,
                    Jsonb(payload),
                    None if complete else error or "model_unavailable",
                    min(300, 2 ** claim["attempt"]),
                    self.db.workspace_id,
                    claim["id"],
                    self.owner,
                    claim["lease_epoch"],
                    claim["requested_generation"],
                ),
            )
            desired = "indexed" if units else "absent"
            dense_state = "current" if complete else "partial"
            c.execute(
                "INSERT INTO shiliu.retrieval_sync_state(workspace_id,video_id,sync_state_version,desired_state,lexical_state,dense_state,last_trigger,last_attempt_at,last_success_at,last_error_stage,last_error_message,updated_at) "
                "VALUES(%s,%s,%s,%s,'current',%s,%s,clock_timestamp(),clock_timestamp(),%s,%s,clock_timestamp()) ON CONFLICT(video_id) DO UPDATE SET desired_state=excluded.desired_state,lexical_state=excluded.lexical_state,dense_state=excluded.dense_state,last_trigger=excluded.last_trigger,last_attempt_at=excluded.last_attempt_at,last_success_at=excluded.last_success_at,last_error_stage=excluded.last_error_stage,last_error_message=excluded.last_error_message,updated_at=excluded.updated_at",
                (
                    self.db.workspace_id,
                    video_id,
                    SYNC_STATE_VERSION,
                    desired,
                    dense_state,
                    str(payload.get("reason", "worker")),
                    None if complete else "dense",
                    None if complete else error or "model_unavailable",
                ),
            )
            return dict(
                video_id=video_id,
                desired_state=desired,
                lexical_state="current",
                dense_state=dense_state,
                total_units=len(units),
                embedded_count=getattr(vectors, "encoded_count", 0),
                reused_count=getattr(vectors, "reused_count", 0),
                generation=claim["requested_generation"],
                status=status,
            )

    def fail(self, claim, error):
        with self.db.connect() as c:
            self._lock_claim(c, claim)
            c.execute(
                "UPDATE shiliu.retrieval_projection_tasks SET status=CASE WHEN attempt>=5 THEN 'failed' ELSE 'retry_wait' END,"
                "last_error=%s,not_before=clock_timestamp()+LEAST(300,power(2,attempt))*interval '1 second',lease_owner=NULL,lease_until=NULL,updated_at=clock_timestamp() "
                "WHERE workspace_id=%s AND id=%s AND status='running' AND lease_owner=%s AND lease_epoch=%s AND requested_generation=%s",
                (
                    error,
                    self.db.workspace_id,
                    claim["id"],
                    self.owner,
                    claim["lease_epoch"],
                    claim["requested_generation"],
                ),
            )

    def run_one(self, *, video_id=None):
        claim = self.claim(video_id=video_id)
        if claim is None:
            return None
        try:
            with self.renewing(claim):
                snapshot = self.snapshot(claim)
                units, tokens = self.build(snapshot, claim)
                vectors = None
                error = None
                if self.dense is not None and units:
                    try:
                        vectors = self.dense.encode(units)
                    except Exception as exc:
                        error = type(exc).__name__
                return self.publish(
                    claim, snapshot, units, tokens, vectors=vectors, error=error
                )
        except ProjectionStale:
            return {
                "video_id": int(claim["resource_key"]),
                "status": "stale",
                "dense_state": "stale",
            }
        except Exception as exc:
            try:
                self.fail(claim, type(exc).__name__)
            except ProjectionStale:
                return {
                    "video_id": int(claim["resource_key"]),
                    "status": "stale",
                    "dense_state": "stale",
                }
            raise


@dataclass(frozen=True)
class VideoSyncResult:
    video_id: int
    trigger: str
    desired_state: str
    lexical_state: str
    dense_state: str
    success: bool
    error_stage: str | None = None
    error_message: str | None = None
    lexical_result: dict | None = None
    dense_result: dict | None = None
    duration_seconds: float = 0

    def as_dict(self):
        return asdict(self)


@dataclass
class ReconcileResult:
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0

    def as_dict(self):
        return asdict(self)


class RetrievalIndexCoordinator:
    """Explicit intent registration/execution; mutations already own their intent."""

    def __init__(self, *, db, lexical, dense_factory=None):
        self.db, self.lexical, self._dense_factory = db, lexical, dense_factory

    def register(self, conn, video_id, *, reason):
        self.db._touch(conn, video_id, reason=reason)

    def sync_video(self, video_id, *, trigger):
        dense = self._dense_factory() if self._dense_factory is not None else None
        if dense is not None and dense.lexical is None:
            dense.lexical = self.lexical
        result = ProjectionWorker(self.lexical, dense).run_one(video_id=video_id)
        if result is None:
            with self.db.connect(read_only=True) as c:
                task = c.execute(
                    "SELECT status FROM shiliu.retrieval_projection_tasks WHERE workspace_id=%s AND domain='collection' AND resource_key=%s",
                    (self.db.workspace_id, str(video_id)),
                ).fetchone()
            return VideoSyncResult(
                video_id,
                trigger,
                "indexed",
                "current" if task and task["status"] == "completed" else "pending",
                "pending",
                bool(task and task["status"] == "completed"),
            )
        return VideoSyncResult(
            video_id,
            trigger,
            result.get("desired_state", "indexed"),
            result.get("lexical_state", "pending"),
            result.get("dense_state", "partial"),
            result.get("status") == "completed",
            lexical_result=result,
        )

    def safe_sync_video(self, video_id, *, trigger):
        # A bounded execution hint. Failure cannot lose the already-committed
        # durable request; its retry/error lives in PG, not a callback chain.
        try:
            return self.sync_video(video_id, trigger=trigger)
        except Exception as exc:
            return VideoSyncResult(
                video_id,
                trigger,
                "indexed",
                "error",
                "partial",
                False,
                "projection",
                type(exc).__name__,
            )

    def reconcile_video(self, video_id, *, trigger="manual_reconcile"):
        self.lexical.request(video_id, reason=trigger)
        return self.sync_video(video_id, trigger=trigger)

    def reconcile_all(self, *, trigger="manual_reconcile"):
        result = ReconcileResult()
        for video in self.db.list_videos():
            value = self.reconcile_video(video["id"], trigger=trigger)
            result.attempted += 1
            if value.success:
                result.succeeded += 1
            else:
                result.failed += 1
        return result

    def remove_video(self, video_id, *, trigger):
        self.lexical.delete_video(video_id)
        return self.sync_video(video_id, trigger=trigger)
