from __future__ import annotations

import fcntl
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import TracebackType
from typing import Callable, Protocol

from shiliu.bilibili import BilibiliAdapter
from shiliu.db import Database, utc_now
from shiliu.domain import PipelineError, SyncMode, SyncResult
from shiliu.pipeline import PipelineService


# Temporarily disabled on 2026-07-16 so scheduled discovery, refinement, and
# retries can continue throughout the day. Keep the time-window function below
# so the previous behavior can be restored without rewriting the workflow.
QUIET_HOURS_ENABLED = False


class SyncAlreadyRunning(RuntimeError):
    pass


class _IndexCoordinator(Protocol):
    def safe_sync_video(self, video_id: int, *, trigger: str) -> object: ...


class ProcessLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None

    def __enter__(self) -> "ProcessLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+")
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._handle.close()
            self._handle = None
            raise SyncAlreadyRunning("已有一次同步正在运行") from exc
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None


class SyncService:
    def __init__(
        self,
        *,
        db: Database,
        adapter: BilibiliAdapter,
        pipeline: PipelineService,
        favorite_id: int | None,
        lock_path: Path,
        now_factory: Callable[[], datetime] = datetime.now,
        sleep: Callable[[float], None] = time.sleep,
        randint: Callable[[int, int], int] = random.randint,
        index_coordinator: _IndexCoordinator | None = None,
    ) -> None:
        self.db = db
        self.adapter = adapter
        self.pipeline = pipeline
        self.favorite_id = favorite_id
        self.lock_path = lock_path
        self.now_factory = now_factory
        self.sleep = sleep
        self.randint = randint
        self.index_coordinator = index_coordinator

    def sync(
        self,
        mode: SyncMode = SyncMode.SCHEDULED,
        *,
        source_db_id: int | None = None,
        run_id: int | None = None,
    ) -> SyncResult:
        result = SyncResult(mode=mode, run_id=run_id)
        begin_cycle = getattr(self.pipeline, "begin_sync_cycle", None)
        if begin_cycle is not None:
            begin_cycle()
        quiet_hours = (
            QUIET_HOURS_ENABLED
            and mode == SyncMode.SCHEDULED
            and is_quiet_hour(self.now_factory())
        )

        all_sources = self.db.list_sources()
        sources = [
            source
            for source in all_sources
            if source.get("status") in {"active", "cooldown"}
        ]
        if source_db_id is not None:
            sources = [source for source in sources if int(source["id"]) == source_db_id]
            if not sources:
                raise PipelineError(
                    "该来源未启用或正在等待人工处理",
                    code="source_not_active",
                    retryable=False,
                )

        # Legacy single-folder installations do not have a history queue. Keep
        # their original quiet-hours behavior; multi-source V1 installations
        # continue below so queued history can be processed around the clock.
        if quiet_hours and not sources:
            result.skipped_quiet_hours = True
            result.messages.append("05:00–11:59 自动发现暂停；立即同步仍可使用")
            if run_id is not None:
                self.db.finish_sync_run(run_id, status="skipped_quiet_hours", message=result.messages[0])
            return result

        # Scheduled jitter happens before acquiring the global lock so a manual
        # sync is never blocked by a sleeping launchd process.
        if mode == SyncMode.SCHEDULED:
            delay = self.randint(60, 300)
            if run_id is not None:
                self.db.update_sync_run(
                    run_id,
                    current_phase="jitter",
                    message=f"定时启动抖动 {delay} 秒",
                )
            self.sleep(delay)

        if not sources:
            if all_sources:
                raise PipelineError(
                    "收藏夹来源当前均已暂停、需要登录或暂时不可用；请先恢复来源",
                    code="source_not_active",
                    retryable=False,
                )
            if self.favorite_id is None:
                raise PipelineError("尚未添加收藏夹来源", code="setup_required", retryable=False)
            with ProcessLock(self.lock_path):
                return self._sync_legacy(result, run_id=run_id)

        with ProcessLock(self.lock_path):
            return self._sync_sources(
                result,
                sources,
                run_id=run_id,
                quiet_hours=quiet_hours,
            )

    def _sync_sources(
        self,
        result: SyncResult,
        sources: list[dict[str, object]],
        *,
        run_id: int | None,
        quiet_hours: bool,
    ) -> SyncResult:
        active_run_id = run_id or self.db.start_sync_run(
            result.mode.value,
            scope_source_id=(int(sources[0]["id"]) if len(sources) == 1 else None),
        )
        result.run_id = active_run_id
        discovered_ids: list[int] = []
        try:
            if quiet_hours:
                result.skipped_quiet_hours = True
                result.messages.append("05:00–11:59 暂停自动发现和精修；历史积压继续处理")
                self.db.update_sync_run(
                    active_run_id,
                    current_phase="history",
                    message="静默时段：正在处理历史积压",
                )
            else:
                for source in sources:
                    source_id = int(source["id"])
                    if self._source_is_cooling_down(source):
                        result.messages.append(f"{source['folder_title']} 正在冷却，已跳过")
                        continue
                    self.db.update_sync_run(
                        active_run_id,
                        current_phase="scanning",
                        message=f"正在读取 {source['account_name']} / {source['folder_title']}",
                    )
                    try:
                        items = self.adapter.list_favorite_items(int(source["folder_id"]))
                    except PipelineError as exc:
                        self._record_source_failure(source_id, exc, history=False)
                        if exc.code == "authentication_required":
                            for item in sources:
                                self.db.update_source_error(
                                    int(item["id"]),
                                    status="needs_auth",
                                    code=exc.code,
                                    message=str(exc),
                                )
                            raise
                        result.failed_count += 1
                        continue
                    self.db.update_video_durations(items)
                    result.current_count += len(items)
                    if not bool(source.get("baseline_initialized")):
                        queued = self.db.initialize_source_memberships(source_id, items)
                        self._sync_source_videos(source_id, "source_baseline_initialized")
                        result.baseline_created = True
                        result.messages.append(
                            f"{source['folder_title']} 已建立基线，历史待处理 {queued} 条"
                        )
                    else:
                        profile = "fast" if result.mode == SyncMode.MANUAL else "formal"
                        new_ids = self.db.record_source_snapshot(
                            source_id,
                            items,
                            processing_profile=profile,
                        )
                        self._sync_source_videos(source_id, "source_snapshot_recorded")
                        discovered_ids.extend(new_ids)
                        result.discovered_count += len(new_ids)

                self._process_new_and_due(
                    active_run_id,
                    result,
                    discovered_ids,
                    allowed_source_ids={int(source["id"]) for source in sources},
                )

                if result.mode == SyncMode.SCHEDULED:
                    self._process_pending_refinements(active_run_id, result)

            if result.mode == SyncMode.SCHEDULED:
                self._process_history_backlog(active_run_id, result)

            result.history_pending_count = self.db.history_pending_count()
            status = "completed" if result.failed_count == 0 else "completed_with_errors"
            self.db.finish_sync_run(
                active_run_id,
                status=status,
                current_count=result.current_count,
                discovered_count=result.discovered_count,
                processed_count=result.processed_count,
                failed_count=result.failed_count,
                history_pending_count=result.history_pending_count,
                current_phase="completed",
                message="同步完成",
            )
            return result
        except Exception as exc:
            self.db.finish_sync_run(
                active_run_id,
                status="failed",
                current_count=result.current_count,
                discovered_count=result.discovered_count,
                processed_count=result.processed_count,
                failed_count=result.failed_count,
                history_pending_count=self.db.history_pending_count(),
                current_phase="failed",
                error_summary=f"{type(exc).__name__}: {exc}",
            )
            raise

    def _sync_source_videos(self, source_id: int, trigger: str) -> None:
        if self.index_coordinator is None:
            return
        with self.db.connect() as connection:
            video_ids = [
                int(row[0])
                for row in connection.execute(
                    "SELECT DISTINCT video_id FROM video_source_memberships "
                    "WHERE source_id=? AND video_id IS NOT NULL ORDER BY video_id",
                    (source_id,),
                )
            ]
        for video_id in video_ids:
            self.index_coordinator.safe_sync_video(video_id, trigger=trigger)

    def _process_new_and_due(
        self,
        run_id: int,
        result: SyncResult,
        discovered_ids: list[int],
        *,
        allowed_source_ids: set[int] | None = None,
    ) -> None:
        due = self.db.list_processable_videos()
        if allowed_source_ids is not None:
            due = [
                video
                for video in due
                if any(
                    int(source["id"]) in allowed_source_ids
                    for source in self.db.video_sources(int(video["id"]))
                )
            ]
        new_set = set(discovered_ids)
        due.sort(key=lambda video: (int(video["id"]) not in new_set, str(video["discovered_at"])))
        for video in due:
            video_id = int(video["id"])
            self.db.update_sync_run(
                run_id,
                current_phase="processing",
                current_video_id=video_id,
                message=f"正在处理 {video['title']}",
                processed_count=result.processed_count,
                failed_count=result.failed_count,
            )
            try:
                if self.pipeline.process_video(video_id):
                    result.processed_count += 1
                self._apply_video_rate_limit(video_id, history=False)
            except Exception as exc:
                result.failed_count += 1
                self.db.update_video(
                    video_id,
                    status="needs_review",
                    error_code="internal_error",
                    error_message=f"{type(exc).__name__}: {exc}",
                )

    def _process_pending_refinements(self, run_id: int, result: SyncResult) -> None:
        for video in self.db.list_videos():
            if video.get("refinement_status") != "pending":
                continue
            video_id = int(video["id"])
            self.db.update_sync_run(
                run_id,
                current_phase="refinement",
                current_video_id=video_id,
                message=f"正在精修 {video['title']}",
            )
            if self.pipeline.process_refinement(video_id):
                result.processed_count += 1

    def _process_history_backlog(self, run_id: int, result: SyncResult) -> None:
        backlog = self.db.list_history_backlog(limit=8)
        for index, membership in enumerate(backlog):
            video_id = self.db.materialize_history_membership(
                int(membership["source_id"]), str(membership["bvid"])
            )
            if self.index_coordinator is not None:
                self.index_coordinator.safe_sync_video(
                    video_id, trigger="history_membership_materialized"
                )
            self.db.update_sync_run(
                run_id,
                current_phase="history",
                current_video_id=video_id,
                message=f"正在处理历史内容 {index + 1}/{len(backlog)}：{membership['title']}",
                history_pending_count=self.db.history_pending_count(),
            )
            try:
                if self.pipeline.process_video(video_id):
                    result.processed_count += 1
                self._apply_video_rate_limit(video_id, history=True)
            except Exception as exc:
                result.failed_count += 1
                self.db.update_video(
                    video_id,
                    status="needs_review",
                    error_code="internal_error",
                    error_message=f"{type(exc).__name__}: {exc}",
                )
            if index + 1 < len(backlog):
                self.sleep(self.randint(2, 6))

    def _apply_video_rate_limit(self, video_id: int, *, history: bool) -> None:
        video = self.db.get_video(video_id)
        if not video:
            return
        message = str(video.get("error_message") or "")
        if not any(token in message.lower() for token in ("412", "429", "rate")):
            return
        minutes = 20 if history else 10
        cooldown = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat(timespec="seconds")
        for source in self.db.video_sources(video_id):
            self.db.update_source_error(
                int(source["id"]),
                status="cooldown",
                code=str(video.get("error_code") or "upstream_retryable"),
                message=message,
                cooldown_until=cooldown,
            )

    def _record_source_failure(
        self, source_db_id: int, error: PipelineError, *, history: bool
    ) -> None:
        message = str(error)
        is_rate_limited = any(token in message.lower() for token in ("412", "429", "rate"))
        if error.code == "authentication_required":
            status = "needs_auth"
            cooldown = None
        elif is_rate_limited or error.retryable:
            status = "cooldown"
            minutes = 20 if history else 10
            cooldown = (
                datetime.now(timezone.utc) + timedelta(minutes=minutes)
            ).isoformat(timespec="seconds")
        else:
            status = "unavailable"
            cooldown = None
        self.db.update_source_error(
            source_db_id,
            status=status,
            code=error.code,
            message=message,
            cooldown_until=cooldown,
        )

    @staticmethod
    def _source_is_cooling_down(source: dict[str, object]) -> bool:
        if source.get("status") != "cooldown" or not source.get("cooldown_until"):
            return False
        value = datetime.fromisoformat(str(source["cooldown_until"]))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value > datetime.now(timezone.utc)

    def _sync_legacy(self, result: SyncResult, *, run_id: int | None) -> SyncResult:
        active_run_id = run_id or self.db.start_sync_run(result.mode.value)
        result.run_id = active_run_id
        try:
            items = self.adapter.list_favorite_items(int(self.favorite_id))
            self.db.update_video_durations(items)
            current_ids = {item.bvid for item in items}
            result.current_count = len(current_ids)
            if not self.db.has_baseline():
                self.db.establish_baseline(sorted(current_ids))
                result.baseline_created = True
                result.messages.append(f"已建立 {len(current_ids)} 条首次基线；未生成历史卡片")
                self.db.finish_sync_run(active_run_id, status="completed", current_count=result.current_count)
                return result

            known_ids = self.db.seen_source_ids()
            new_items = [item for item in items if item.bvid not in known_ids]
            for item in items:
                self.db.mark_seen(item.bvid)
            self.db.reconcile_current_items(current_ids)
            if self.index_coordinator is not None:
                with self.db.connect() as connection:
                    legacy_video_ids = [
                        int(row[0])
                        for row in connection.execute("SELECT id FROM videos ORDER BY id")
                    ]
                for video_id in legacy_video_ids:
                    self.index_coordinator.safe_sync_video(
                        video_id, trigger="legacy_snapshot_recorded"
                    )
            profile = "fast" if result.mode == SyncMode.MANUAL else "formal"
            for item in new_items:
                self.db.create_video(
                    item.bvid,
                    item.title,
                    item.uploader,
                    processing_profile=profile,
                    display_favorite_time=item.favorite_time,
                    duration_seconds=item.duration_seconds,
                )
            result.discovered_count = len(new_items)
            self._process_new_and_due(active_run_id, result, [])
            status = "completed" if result.failed_count == 0 else "completed_with_errors"
            self.db.finish_sync_run(
                active_run_id,
                status=status,
                current_count=result.current_count,
                discovered_count=result.discovered_count,
                processed_count=result.processed_count,
                failed_count=result.failed_count,
            )
            return result
        except Exception as exc:
            self.db.finish_sync_run(
                active_run_id,
                status="failed",
                error_summary=f"{type(exc).__name__}: {exc}",
            )
            raise


def is_quiet_hour(moment: datetime) -> bool:
    return 5 <= moment.hour < 12
