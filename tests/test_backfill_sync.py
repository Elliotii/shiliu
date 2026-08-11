from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.bilibili import BilibiliAdapter
from shiliu.db import Database
from shiliu.domain import FavoriteItem, PipelineError, SyncMode
from shiliu.sync import SyncService
from shiliu.web import create_web_app


def favorite(index: int, favorite_time: int | None = None) -> FavoriteItem:
    return FavoriteItem(
        bvid=f"BV{index:010d}",
        title=f"视频 {index}",
        uploader="UP",
        favorite_time=favorite_time,
    )


def source_rows(db: Database, source_id: int) -> list[dict]:
    with db.connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM video_source_memberships WHERE source_id=? ORDER BY bvid",
                (source_id,),
            ).fetchall()
        ]


def test_latest_n_initial_backfill_resolves_stable_time_boundary(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    source_id = db.create_favorite_source(
        folder_id=1, folder_title="稳定边界", history_policy="latest_n", history_limit=2
    )
    items = [favorite(1, 100), favorite(2, 300), favorite(3, 200)]

    queued = db.initialize_source_memberships(
        source_id, items, authoritative=True, remote_total=3
    )

    source = db.get_source(source_id)
    rows = source_rows(db, source_id)
    assert queued == 2
    assert source["history_cutoff_time"] == 200
    assert source["discovery_complete"] == 1
    assert {row["bvid"] for row in rows if row["queued_history"]} == {
        favorite(2).bvid,
        favorite(3).bvid,
    }

    # A later forward favorite enters even when its supplied favorite_time is older
    # than the stable historical cutoff. The cutoff itself does not drift.
    created = db.record_source_snapshot(
        source_id,
        [*items, favorite(4, 50), favorite(5, None)],
        processing_profile="formal",
        authoritative=True,
        remote_total=5,
    )
    assert len(created) == 2
    assert db.get_video_by_source(favorite(4).bvid) is not None
    assert db.get_video_by_source(favorite(5).bvid) is not None
    assert next(
        row for row in source_rows(db, source_id) if row["bvid"] == favorite(5).bvid
    )["favorite_time"] is None
    db.update_source_history_coverage(
        source_id, history_policy="latest_n", history_limit=2
    )
    assert db.get_source(source_id)["history_cutoff_time"] == 200


def test_incomplete_initial_scan_does_not_finalize_or_queue_baseline(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    source_id = db.create_favorite_source(
        folder_id=1, folder_title="Partial", history_policy="latest_n", history_limit=2
    )

    assert db.initialize_source_memberships(
        source_id, [favorite(1, 300), favorite(2, 200)], authoritative=False, remote_total=6
    ) == 0
    source = db.get_source(source_id)
    assert source["baseline_initialized"] == 0
    assert source["discovery_complete"] == 0
    assert source["last_snapshot_complete"] == 0
    assert all(row["queued_history"] == 0 for row in source_rows(db, source_id))

    assert db.initialize_source_memberships(
        source_id,
        [favorite(1, 300), favorite(2, 200), favorite(3, 100)],
        authoritative=True,
        remote_total=3,
    ) == 2
    assert db.get_source(source_id)["baseline_initialized"] == 1


def test_partial_snapshot_cannot_remove_and_complete_snapshot_still_can(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    source_id = db.create_favorite_source(folder_id=1, folder_title="Authority")
    items = [favorite(1, 300), favorite(2, 200), favorite(3, 100)]
    db.record_source_snapshot(
        source_id, items, processing_profile="formal", authoritative=True, remote_total=3
    )
    video = db.get_video_by_source(favorite(3).bvid)

    db.record_source_snapshot(
        source_id,
        [items[0]],
        processing_profile="formal",
        authoritative=False,
        remote_total=3,
    )
    assert all(row["removed_at"] is None for row in source_rows(db, source_id))
    assert db.get_video(int(video["id"]))["removed_at"] is None

    db.record_source_snapshot(
        source_id,
        [items[0]],
        processing_profile="formal",
        authoritative=True,
        remote_total=1,
    )
    removed = {row["bvid"] for row in source_rows(db, source_id) if row["removed_at"]}
    assert removed == {favorite(2).bvid, favorite(3).bvid}
    assert db.get_video(int(video["id"]))["removed_at"] is not None


def test_expand_then_shrink_changes_only_unmaterialized_pending_work(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    source_id = db.create_favorite_source(
        folder_id=1, folder_title="Coverage", history_policy="latest_n", history_limit=100
    )
    items = [favorite(index, 1000 - index) for index in range(300)]
    assert db.initialize_source_memberships(
        source_id, items, authoritative=True, remote_total=300
    ) == 100
    video_id = db.materialize_history_membership(source_id, favorite(0).bvid)
    db.set_reading_state(video_id, "read")
    db.set_marked(video_id, True)
    note_id = db.create_note(video_id, "保留状态")["id"]

    assert db.update_source_history_coverage(
        source_id, history_policy="latest_n", history_limit=300
    ) == 299
    assert len(source_rows(db, source_id)) == 300

    assert db.update_source_history_coverage(
        source_id, history_policy="latest_n", history_limit=100
    ) == 99
    video = db.get_video(video_id)
    assert video["reading_state"] == "read"
    assert video["is_marked"] == 1
    assert db.get_note(int(note_id))["content"] == "保留状态"
    assert len(source_rows(db, source_id)) == 300
    assert sum(row["removed_at"] is not None for row in source_rows(db, source_id)) == 0
    assert db.source_sync_metrics(source_id)["not_backfilled"] == 200


def test_reactivated_unmaterialized_baseline_item_is_forward_materialized(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    source_id = db.create_favorite_source(
        folder_id=1, folder_title="Refavorite", history_policy="future_only"
    )
    item = favorite(1, 100)
    db.initialize_source_memberships(
        source_id, [item], authoritative=True, remote_total=1
    )
    assert db.get_video_by_source(item.bvid) is None

    db.record_source_snapshot(
        source_id, [], processing_profile="formal", authoritative=True, remote_total=0
    )
    created = db.record_source_snapshot(
        source_id, [item], processing_profile="formal", authoritative=True, remote_total=1
    )
    assert len(created) == 1
    assert db.get_video_by_source(item.bvid) is not None
    assert source_rows(db, source_id)[0]["removed_at"] is None


def test_shared_video_survives_until_last_authoritative_membership_is_removed(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    first = db.create_favorite_source(folder_id=1, folder_title="A")
    second = db.create_favorite_source(folder_id=2, folder_title="B")
    item = favorite(1, 100)
    db.record_source_snapshot(
        first, [item], processing_profile="formal", authoritative=True, remote_total=1
    )
    db.record_source_snapshot(
        second, [item], processing_profile="formal", authoritative=True, remote_total=1
    )
    video_id = int(db.get_video_by_source(item.bvid)["id"])

    db.record_source_snapshot(
        first, [], processing_profile="formal", authoritative=True, remote_total=0
    )
    assert db.get_video(video_id)["removed_at"] is None
    assert db.video_has_active_source(video_id) is True

    db.record_source_snapshot(
        second, [], processing_profile="formal", authoritative=True, remote_total=0
    )
    assert db.get_video(video_id)["removed_at"] is not None
    assert db.video_has_active_source(video_id) is False


def test_pause_resume_and_all_history_are_non_destructive_and_idempotent(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    source_id = db.create_favorite_source(
        folder_id=1, folder_title="All", history_policy="future_only"
    )
    items = [favorite(1, 300), favorite(2, 200), favorite(3, 100)]
    db.initialize_source_memberships(
        source_id, items, authoritative=True, remote_total=3
    )
    assert db.update_source_history_coverage(source_id, history_policy="all") == 3

    db.set_source_status(source_id, "paused")
    assert db.list_history_backlog(source_ids={source_id}) == []
    assert db.history_pending_count() == 3
    db.set_source_status(source_id, "active")
    assert len(db.list_history_backlog(limit=8, source_ids={source_id})) == 3

    video_id = db.materialize_history_membership(source_id, items[0].bvid)
    restarted = Database(app_paths.database)
    restarted.initialize()
    assert restarted.update_source_history_coverage(source_id, history_policy="all") == 2
    assert restarted.get_video(video_id) is not None
    assert len(source_rows(restarted, source_id)) == 3


def test_remote_failure_never_reconciles_absence_and_stale_run_recovers(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    source_id = db.create_favorite_source(folder_id=1, folder_title="Failure")
    item = favorite(1, 100)
    db.record_source_snapshot(
        source_id, [item], processing_profile="formal", authoritative=True, remote_total=1
    )
    stale_run = db.start_sync_run("scheduled")

    class Adapter:
        def list_favorite_items(self, folder_id: int):
            raise PipelineError("temporary", code="upstream_error", retryable=True)

    class Pipeline:
        def begin_sync_cycle(self):
            pass

        def process_video(self, video_id: int) -> bool:
            raise AssertionError("failed source must not process")

        def process_refinement(self, video_id: int) -> bool:
            return False

    service = SyncService(
        db=db,
        adapter=Adapter(),
        pipeline=Pipeline(),
        favorite_id=None,
        lock_path=app_paths.sync_lock,
        now_factory=lambda: datetime(2026, 8, 11, 13, 0),
        sleep=lambda _: None,
        randint=lambda low, high: low,
    )
    result = service.sync(SyncMode.MANUAL)

    assert result.failed_count == 1
    assert db.get_sync_run(stale_run)["status"] == "interrupted"
    assert source_rows(db, source_id)[0]["removed_at"] is None
    assert db.get_video_by_source(item.bvid)["removed_at"] is None


def test_materialize_rejects_paused_or_no_longer_queued_membership(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    source_id = db.create_favorite_source(
        folder_id=1, folder_title="Guard", history_policy="all"
    )
    item = favorite(1, 100)
    db.initialize_source_memberships(
        source_id, [item], authoritative=True, remote_total=1
    )
    db.set_source_status(source_id, "paused")
    with pytest.raises(KeyError):
        db.materialize_history_membership(source_id, item.bvid)


def test_bilibili_scan_exposes_completeness_and_rejects_count_mismatch(tmp_path: Path) -> None:
    adapter = BilibiliAdapter(tmp_path)
    pages = {
        1: {
            "items": [favorite(1, 200).model_dump()],
            "has_more": True,
            "remote_total": 2,
        },
        2: {
            "items": [favorite(2, 100).model_dump()],
            "has_more": False,
            "remote_total": None,
        },
    }
    adapter._run_bridge = lambda args: pages[int(args[-1])]  # type: ignore[method-assign]
    scan = adapter.list_favorite_scan(1)
    assert scan.is_complete is True
    assert scan.remote_total == 2
    assert scan.pages_fetched == 2

    pages[1] = {
        "items": [favorite(1, 200).model_dump()],
        "has_more": False,
        "remote_total": 2,
    }
    mismatch = adapter.list_favorite_scan(1)
    assert mismatch.is_complete is False
    with pytest.raises(PipelineError, match="不完整"):
        adapter.list_favorite_items(1)


def test_source_ui_reports_metrics_and_updates_history_coverage(app_paths) -> None:
    application = Application(app_paths)
    source_id = application.db.create_favorite_source(
        folder_id=1, folder_title="UI Coverage", history_policy="latest_n", history_limit=100
    )
    application.db.initialize_source_memberships(
        source_id,
        [favorite(1, 300), favorite(2, 200), favorite(3, 100)],
        authoritative=True,
        remote_total=3,
    )
    client = TestClient(create_web_app(application))

    page = client.get("/setup")
    assert page.status_code == 200
    assert "Remote detected 3" in page.text
    assert "Imported 0" in page.text
    assert "Not backfilled 0" in page.text
    assert "Latest 100" in page.text
    assert "Continuous sync: OFF" in page.text

    response = client.post(
        f"/api/sources/{source_id}/history-coverage",
        json={"history_policy": "future_only", "history_limit": None},
    )
    assert response.status_code == 200
    assert response.json()["history_pending"] == 0
    assert application.db.source_sync_metrics(source_id)["not_backfilled"] == 3
