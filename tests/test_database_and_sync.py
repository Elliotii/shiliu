from __future__ import annotations

from datetime import datetime

from shiliu.db import Database
from shiliu.domain import FavoriteItem, SyncMode
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


def test_first_scan_creates_baseline_without_cards_or_processing(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
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


def test_only_post_baseline_new_item_becomes_card_and_readd_does_not_repeat(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
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


def test_quiet_hours_are_temporarily_disabled_for_scheduled_sync(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
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


def test_ignore_is_display_state_only(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
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
