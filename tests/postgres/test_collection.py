from __future__ import annotations

from datetime import datetime

import pytest

from shiliu.db import Database
from shiliu.domain import FavoriteItem, PipelineError, SyncMode
from shiliu.sync import QUIET_HOURS_ENABLED, SyncService, is_quiet_hour


class FakeAdapter:
    def __init__(self, items: list[FavoriteItem]) -> None:
        self.items = items
        self.pages_read = 0

    def list_favorite_items(self, favorite_id: int) -> list[FavoriteItem]:
        assert favorite_id == 42
        self.pages_read += 1
        return list(self.items)


class CompletingPipeline:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.calls: list[int] = []

    def process_video(self, video_id: int) -> bool:
        self.calls.append(video_id)
        self.db.update_video(video_id, status="completed")
        return True


def favorite(bvid: str, title: str = "视频") -> FavoriteItem:
    return FavoriteItem(bvid=bvid, title=title, uploader="UP")


def test_first_scan_creates_baseline_without_cards_or_processing(
    app_paths, collection_db
) -> None:
    db = collection_db
    adapter = FakeAdapter([favorite("BV1234567890"), favorite("BV2234567890")])
    pipeline = CompletingPipeline(db)
    service = SyncService(
        db=db,
        adapter=adapter,
        pipeline=pipeline,
        favorite_id=42,
        lock_path=app_paths.sync_lock,
    )

    result = service.sync(SyncMode.MANUAL)

    assert result.baseline_created is True
    assert db.has_baseline() is True
    assert db.list_videos() == []
    assert pipeline.calls == []


def test_only_post_baseline_new_item_becomes_card_and_readd_does_not_repeat(
    app_paths, collection_db
) -> None:
    db = collection_db
    adapter = FakeAdapter([favorite("BV1234567890")])
    pipeline = CompletingPipeline(db)
    service = SyncService(
        db=db,
        adapter=adapter,
        pipeline=pipeline,
        favorite_id=42,
        lock_path=app_paths.sync_lock,
    )
    service.sync(SyncMode.MANUAL)

    adapter.items.append(favorite("BV2234567890", "新增"))
    second = service.sync(SyncMode.MANUAL)
    assert second.discovered_count == 1
    assert len(db.list_videos()) == 1
    assert len(pipeline.calls) == 1

    adapter.items = [favorite("BV1234567890")]
    service.sync(SyncMode.MANUAL)
    assert db.get_video_by_source("BV2234567890")["removed_at"] is not None

    adapter.items.append(favorite("BV2234567890", "重新收藏"))
    fourth = service.sync(SyncMode.MANUAL)
    assert fourth.discovered_count == 0
    assert len(pipeline.calls) == 1
    assert db.get_video_by_source("BV2234567890")["removed_at"] is None


def test_quiet_hours_are_temporarily_disabled_for_scheduled_sync(
    app_paths, collection_db
) -> None:
    db = collection_db
    adapter = FakeAdapter([])
    pipeline = CompletingPipeline(db)
    service = SyncService(
        db=db,
        adapter=adapter,
        pipeline=pipeline,
        favorite_id=42,
        lock_path=app_paths.sync_lock,
        now_factory=lambda: datetime(2026, 7, 15, 8, 0),
        sleep=lambda _: None,
        randint=lambda _start, _end: 60,
    )

    scheduled = service.sync(SyncMode.SCHEDULED)
    assert QUIET_HOURS_ENABLED is False
    assert scheduled.skipped_quiet_hours is False
    assert adapter.pages_read == 1
    assert scheduled.baseline_created is True


def test_quiet_hour_boundaries() -> None:
    assert is_quiet_hour(datetime(2026, 1, 1, 4, 59)) is False
    assert is_quiet_hour(datetime(2026, 1, 1, 5, 0)) is True
    assert is_quiet_hour(datetime(2026, 1, 1, 11, 59)) is True
    assert is_quiet_hour(datetime(2026, 1, 1, 12, 0)) is False


def test_existing_unavailable_source_does_not_fall_back_to_legacy_sync(
    app_paths, collection_db
) -> None:
    db = collection_db
    source_id = db.create_favorite_source(folder_id=42, folder_title="暂不可用")
    db.set_source_status(source_id, "unavailable")
    adapter = FakeAdapter([favorite("BV1234567890")])
    service = SyncService(
        db=db,
        adapter=adapter,
        pipeline=CompletingPipeline(db),
        favorite_id=42,
        lock_path=app_paths.sync_lock,
    )

    with pytest.raises(PipelineError) as error:
        service.sync(SyncMode.MANUAL)

    assert error.value.code == "source_not_active"
    assert adapter.pages_read == 0


def test_retryable_source_failure_enters_recoverable_cooldown(
    app_paths, collection_db
) -> None:
    db = collection_db
    source_id = db.create_favorite_source(folder_id=42, folder_title="网络抖动")

    class RetryableAdapter:
        def list_favorite_items(self, favorite_id: int) -> list[FavoriteItem]:
            raise PipelineError(
                "temporary network failure",
                code="upstream_retryable",
                retryable=True,
            )

    service = SyncService(
        db=db,
        adapter=RetryableAdapter(),
        pipeline=CompletingPipeline(db),
        favorite_id=None,
        lock_path=app_paths.sync_lock,
    )

    result = service.sync(SyncMode.MANUAL)

    source = db.get_source(source_id)
    assert result.failed_count == 1
    assert source is not None
    assert source["status"] == "cooldown"
    assert source["cooldown_until"] is not None


def test_ignore_is_display_state_only(app_paths, collection_db) -> None:
    db = collection_db
    video_id = db.create_video("BV1234567890", "标题")
    db.update_video(video_id, status="summary_processing")

    db.set_ignored(video_id, True)
    ignored = db.get_video(video_id)
    assert ignored["is_ignored"] == 1
    assert ignored["status"] == "summary_processing"

    db.set_ignored(video_id, False)
    restored = db.get_video(video_id)
    assert restored["is_ignored"] == 0
    assert restored["status"] == "summary_processing"


def test_legacy_unavailable_retries_retire_without_fetch_and_do_not_repeat(
    app_paths, collection_db
):
    from shiliu.domain import SyncResult

    db = collection_db
    ids = []
    for index, message in enumerate(
        ["接口返回错误代码：62002，稿件不可见", "{'code': -404}", "network timeout"]
    ):
        video_id = db.create_video(f"BV1retire{index}", f"视频{index}", "UP")
        db.update_video(
            video_id,
            status="retry_wait",
            error_code="upstream_error",
            error_message=message,
        )
        ids.append(video_id)
    pipeline = CompletingPipeline(db)
    service = SyncService(
        db=db,
        adapter=FakeAdapter([]),
        pipeline=pipeline,
        favorite_id=42,
        lock_path=app_paths.sync_lock,
    )
    result = SyncResult(mode=SyncMode.MANUAL)
    run_id = db.start_sync_run("manual")
    service._process_new_and_due(run_id, result, [])
    assert pipeline.calls == [ids[2]]
    assert result.processed_count == 1
    for video_id in ids[:2]:
        video = db.get_video(video_id)
        assert (
            video["status"] == "needs_review"
            and video["error_code"] == "video_unavailable"
        )
        assert video["subtitle_next_check_at"] is None
        assert video["error_message"]
    service._process_new_and_due(run_id, result, [])
    assert pipeline.calls == [ids[2]]
    assert len(db.list_videos()) == 3
    db.reset_failed_stages(ids[0])
    service._process_new_and_due(run_id, result, [])
    assert pipeline.calls == [ids[2], ids[0]]


def test_source_and_stage_takeover_fence_delayed_results(collection_db):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from shiliu.domain import StageName
    from shiliu.storage.fences import CoordinationConflict

    db = collection_db
    sid = db.create_favorite_source(folder_id=42, folder_title="lease")
    claim = db.claim_source(sid, "A")
    assert db.claim_source(sid, "B") is None
    calculated = Event()
    updated = Event()

    def late():
        calculated.set()
        assert updated.wait(5)
        with pytest.raises(CoordinationConflict):
            db.record_source_snapshot(
                sid,
                [favorite("BVstale", "stale")],
                processing_profile="formal",
                claim=claim,
            )

    with ThreadPoolExecutor(1) as executor:
        late_result = executor.submit(late)
        assert calculated.wait(5)
        with db.pg.transaction() as c:
            c.execute(
                "UPDATE shiliu.favorite_sources SET lease_until=clock_timestamp()-interval '1 second' WHERE workspace_id=%s AND id=%s",
                (db.workspace_id, sid),
            )
        b = db.claim_source(sid, "B")
        assert b["lease_epoch"] == claim["lease_epoch"] + 1
        db.record_source_snapshot(
            sid, [favorite("BVnew", "new")], processing_profile="formal", claim=b
        )
        updated.set()
        late_result.result(5)
    assert db.get_video_by_source("BVstale") is None
    vid = db.get_video_by_source("BVnew")["id"]
    db.ensure_stage(vid, StageName.SUMMARY)
    a = db.claim_stage(vid, StageName.SUMMARY, "A")
    db.update_stage(
        vid, StageName.SUMMARY, claim=a, status="processing", attempt_count=1
    )
    with db.pg.transaction() as c:
        c.execute(
            "UPDATE shiliu.pipeline_stages SET lease_until=clock_timestamp()-interval '1 second' WHERE workspace_id=%s AND id=%s",
            (db.workspace_id, a["id"]),
        )
    assert db.claim_stage(vid, StageName.SUMMARY, "B") is None
    assert (
        db.get_stage(vid, StageName.SUMMARY)["last_error_code"]
        == "external_result_unknown"
    )
    with pytest.raises(CoordinationConflict):
        db.update_stage(vid, StageName.SUMMARY, claim=a, status="completed")
    with pytest.raises(CoordinationConflict):
        db.release("favorite_sources", claim)
    db.release("favorite_sources", b)
