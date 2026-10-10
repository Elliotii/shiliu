from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import logging
import time
from typing import Callable

from shiliu.db import Database
from shiliu.retrieval.dense import (
    DENSE_INDEX_VERSION,
    DenseIndexNotReadyError,
    DenseIndexRebuildRequiredError,
    SQLiteExactDenseIndex,
)
from shiliu.retrieval.service import RetrievalService
from shiliu.retrieval.service import INDEX_VERSION


LOGGER = logging.getLogger(__name__)
SYNC_STATE_VERSION = "v3-stage3-sync-state-v1"


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
    lexical_result: dict[str, object] | None = None
    dense_result: dict[str, object] | None = None
    duration_seconds: float = 0.0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ReconcileResult:
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    desired_indexed: int = 0
    desired_absent: int = 0
    embedded: int = 0
    reused: int = 0
    removed: int = 0
    lexical_failures: int = 0
    dense_failures: int = 0
    dense_not_ready: int = 0
    dense_rebuild_required: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


class RetrievalIndexCoordinator:
    """Best-effort post-commit synchronization for derived retrieval indexes."""

    def __init__(
        self,
        *,
        db: Database,
        lexical: RetrievalService,
        dense_factory: Callable[[], SQLiteExactDenseIndex],
    ) -> None:
        self.db = db
        self.lexical = lexical
        self._dense_factory = dense_factory

    def initialize_schema(self) -> None:
        with self.db.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS retrieval_sync_state (
                    video_id INTEGER PRIMARY KEY REFERENCES videos(id) ON DELETE CASCADE,
                    sync_state_version TEXT NOT NULL,
                    desired_state TEXT NOT NULL CHECK(desired_state IN ('indexed', 'absent')),
                    lexical_state TEXT NOT NULL,
                    dense_state TEXT NOT NULL,
                    last_trigger TEXT NOT NULL,
                    last_attempt_at TEXT NOT NULL,
                    last_success_at TEXT,
                    last_error_stage TEXT,
                    last_error_message TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_retrieval_sync_failure "
                "ON retrieval_sync_state(lexical_state, dense_state, video_id)"
            )

    def sync_video(self, video_id: int, *, trigger: str) -> VideoSyncResult:
        started = time.monotonic()
        self.initialize_schema()
        if not self._video_exists(video_id):
            return VideoSyncResult(
                video_id, trigger, "absent", "missing_video", "not_attempted", False,
                "eligibility", "video does not exist",
            )
        desired = "indexed" if self._is_eligible(video_id) else "absent"
        if desired == "absent":
            return self._remove_video(video_id, trigger=trigger)
        try:
            lexical_result = self.lexical.replace_video(video_id)
        except Exception as exc:  # product mutation has already committed
            return self._failed(
                video_id, trigger, desired, "error", "stale", "lexical", exc,
                started=started,
            )
        try:
            dense_result = self._dense_factory().replace_video(video_id)
        except DenseIndexNotReadyError as exc:
            return self._failed(
                video_id, trigger, desired, "current", "not_ready", "dense", exc,
                lexical_result=lexical_result, started=started,
            )
        except DenseIndexRebuildRequiredError as exc:
            return self._failed(
                video_id, trigger, desired, "current", "rebuild_required", "dense", exc,
                lexical_result=lexical_result, started=started,
            )
        except Exception as exc:
            return self._failed(
                video_id, trigger, desired, "current", "error", "dense", exc,
                lexical_result=lexical_result, started=started,
            )
        result = VideoSyncResult(
            video_id, trigger, desired, "current", "current", True,
            lexical_result=lexical_result, dense_result=dense_result.as_dict(),
            duration_seconds=time.monotonic() - started,
        )
        self._record(result)
        return result

    def safe_sync_video(self, video_id: int, *, trigger: str) -> VideoSyncResult:
        """Never let derived-index failure change the Product mutation result."""
        try:
            return self.sync_video(video_id, trigger=trigger)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"[:500]
            LOGGER.exception(
                "retrieval sync boundary failed video_id=%s trigger=%s", video_id, trigger
            )
            return VideoSyncResult(
                video_id, trigger, "indexed", "error", "stale", False,
                "coordinator", message,
            )

    def reconcile_video(self, video_id: int, *, trigger: str = "manual_reconcile") -> VideoSyncResult:
        return self.sync_video(video_id, trigger=trigger)

    def remove_video(self, video_id: int, *, trigger: str) -> VideoSyncResult:
        self.initialize_schema()
        return self._remove_video(video_id, trigger=trigger)

    def reconcile_all(self, *, trigger: str = "manual_reconcile") -> ReconcileResult:
        self.initialize_schema()
        with self.db.connect() as connection:
            video_ids = [
                int(row[0])
                for row in connection.execute("SELECT id FROM videos ORDER BY id")
            ]
        result = ReconcileResult()
        for video_id in video_ids:
            result.attempted += 1
            synced = self.sync_video(video_id, trigger=trigger)
            result.desired_indexed += synced.desired_state == "indexed"
            result.desired_absent += synced.desired_state == "absent"
            if synced.dense_result:
                result.embedded += int(synced.dense_result.get("embedded_count", 0))
                result.reused += int(synced.dense_result.get("reused_count", 0))
            if synced.lexical_result:
                result.removed += int(synced.lexical_result.get("removed_units", 0))
            if synced.success:
                result.succeeded += 1
            else:
                result.failed += 1
                result.lexical_failures += synced.error_stage == "lexical"
                result.dense_failures += synced.error_stage == "dense"
                result.dense_not_ready += synced.dense_state == "not_ready"
                result.dense_rebuild_required += synced.dense_state == "rebuild_required"
        return result

    def retry_failed(self) -> ReconcileResult:
        self.initialize_schema()
        with self.db.connect() as connection:
            video_ids = [
                int(row[0])
                for row in connection.execute(
                    """
                    SELECT video_id FROM retrieval_sync_state
                    WHERE lexical_state='error' OR dense_state IN ('error', 'stale')
                    ORDER BY video_id
                    """
                )
            ]
        result = ReconcileResult()
        for video_id in video_ids:
            result.attempted += 1
            synced = self.sync_video(video_id, trigger="retry_failed")
            if synced.success:
                result.succeeded += 1
            else:
                result.failed += 1
        return result

    def status(self) -> dict[str, object]:
        self.initialize_schema()
        with self.db.connect() as connection:
            total = int(connection.execute(
                "SELECT COUNT(*) FROM retrieval_sync_state"
            ).fetchone()[0])
            groups = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT desired_state, lexical_state, dense_state, COUNT(*) AS count
                    FROM retrieval_sync_state
                    GROUP BY desired_state, lexical_state, dense_state
                    ORDER BY desired_state, lexical_state, dense_state
                    """
                )
            ]
            failed = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT video_id, desired_state, lexical_state, dense_state,
                           last_trigger, last_error_stage, last_error_message, updated_at
                    FROM retrieval_sync_state
                    WHERE lexical_state NOT IN ('current', 'absent')
                       OR dense_state NOT IN ('current', 'absent')
                    ORDER BY video_id
                    """
                )
            ]
        return {"sync_state_version": SYNC_STATE_VERSION, "total": total,
                "groups": groups, "failed": failed}

    def _remove_video(self, video_id: int, *, trigger: str) -> VideoSyncResult:
        started = time.monotonic()
        try:
            removed_units = self.lexical.delete_video(video_id)
        except Exception as exc:
            return self._failed(
                video_id, trigger, "absent", "error", "stale", "lexical", exc,
                started=started,
            )
        try:
            removed_dense = self._dense_factory().delete_video(video_id)
        except DenseIndexNotReadyError as exc:
            return self._failed(
                video_id, trigger, "absent", "absent", "not_ready", "dense", exc,
                lexical_result={"removed_units": removed_units}, started=started,
            )
        except DenseIndexRebuildRequiredError as exc:
            return self._failed(
                video_id, trigger, "absent", "absent", "rebuild_required", "dense", exc,
                lexical_result={"removed_units": removed_units}, started=started,
            )
        except Exception as exc:
            return self._failed(
                video_id, trigger, "absent", "absent", "error", "dense", exc,
                lexical_result={"removed_units": removed_units}, started=started,
            )
        result = VideoSyncResult(
            video_id, trigger, "absent", "absent", "absent", True,
            lexical_result={"removed_units": removed_units},
            dense_result={"removed_vectors": removed_dense},
            duration_seconds=time.monotonic() - started,
        )
        self._record(result)
        return result

    def _video_exists(self, video_id: int) -> bool:
        with self.db.connect() as connection:
            return connection.execute(
                "SELECT 1 FROM videos WHERE id=?", (video_id,)
            ).fetchone() is not None

    def _is_eligible(self, video_id: int) -> bool:
        with self.db.connect() as connection:
            return connection.execute(
                """
                SELECT 1 FROM videos v
                WHERE v.id=? AND v.removed_at IS NULL
                  AND EXISTS (
                    SELECT 1 FROM video_source_memberships m
                    JOIN favorite_sources s ON s.id=m.source_id
                    WHERE m.video_id=v.id AND m.removed_at IS NULL AND s.status='active'
                  )
                """,
                (video_id,),
            ).fetchone() is not None

    def _failed(
        self,
        video_id: int,
        trigger: str,
        desired: str,
        lexical: str,
        dense: str,
        stage: str,
        exc: Exception,
        lexical_result: dict[str, object] | None = None,
        started: float | None = None,
    ) -> VideoSyncResult:
        message = f"{type(exc).__name__}: {exc}"[:500]
        result = VideoSyncResult(
            video_id, trigger, desired, lexical, dense, False, stage, message,
            lexical_result=lexical_result,
            duration_seconds=time.monotonic() - started if started is not None else 0.0,
        )
        self._record(result)
        LOGGER.warning(
            "retrieval sync failed video_id=%s trigger=%s stage=%s error_type=%s",
            video_id, trigger, stage, type(exc).__name__,
        )
        return result

    def _record(self, result: VideoSyncResult) -> None:
        now = _utc_now()
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO retrieval_sync_state(
                    video_id, sync_state_version, desired_state, lexical_state,
                    dense_state, last_trigger, last_attempt_at, last_success_at,
                    last_error_stage, last_error_message, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    sync_state_version=excluded.sync_state_version,
                    desired_state=excluded.desired_state,
                    lexical_state=excluded.lexical_state,
                    dense_state=excluded.dense_state,
                    last_trigger=excluded.last_trigger,
                    last_attempt_at=excluded.last_attempt_at,
                    last_success_at=CASE WHEN excluded.last_success_at IS NOT NULL
                                         THEN excluded.last_success_at
                                         ELSE retrieval_sync_state.last_success_at END,
                    last_error_stage=excluded.last_error_stage,
                    last_error_message=excluded.last_error_message,
                    updated_at=excluded.updated_at
                """,
                (result.video_id, SYNC_STATE_VERSION, result.desired_state,
                 result.lexical_state, result.dense_state, result.trigger, now,
                 now if result.success else None, result.error_stage,
                 result.error_message, now),
            )
        LOGGER.info(
            "retrieval sync video_id=%s trigger=%s desired_state=%s "
            "lexical_status=%s dense_status=%s duration_seconds=%.6f "
            "lexical_index_version=%s dense_index_version=%s error_stage=%s",
            result.video_id, result.trigger, result.desired_state,
            result.lexical_state, result.dense_state, result.duration_seconds,
            INDEX_VERSION, DENSE_INDEX_VERSION, result.error_stage,
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
