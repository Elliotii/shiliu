from __future__ import annotations

from shiliu.artifacts import ArtifactStore
from shiliu.assistant.snapshots import SourceSnapshotStore
from shiliu.assistant.sources import CollectionSourceService, SourceScope
from shiliu.assistant.store import AssistantRunStore
from shiliu.assistant.wiki import BudgetedStructuredProvider, MaintenanceBudgetExceeded, WikiService
from shiliu.db import Database
from shiliu.domain import FavoriteItem
import pytest


def _setup(app_paths):
    db = Database(app_paths.database)
    db.initialize()
    artifacts = ArtifactStore(app_paths.videos_dir)
    sources = CollectionSourceService(
        db=db, artifacts=artifacts,
        snapshots=SourceSnapshotStore(db, artifacts, app_paths.assistant_content_dir),
    )
    return db, sources


def test_metadata_pages_match_direct_scope_and_reject_scope_change(app_paths):
    db, sources = _setup(app_paths)
    source_id = db.create_favorite_source(folder_id=9901, folder_title="A", history_policy="all")
    items = [FavoriteItem(bvid=f"BV9A23456{i:02d}", title=f"材料 {i}", uploader="UP", favorite_time=1000+i) for i in range(13)]
    db.record_source_snapshot(source_id, items, processing_profile="fast", authoritative=True, remote_total=13)
    scope = SourceScope(source_db_ids=frozenset({source_id}))
    first = sources.search(call_id="first", scope=scope, mode="metadata", sort="collected_desc", limit=10, scope_version=1)
    second = sources.search(call_id="second", scope=scope, mode="metadata", sort="collected_desc", limit=10, scope_version=1, cursor=first.next_cursor)
    expected = sources.visible_video_ids(scope, order="collected_desc")
    actual = [item["video_id"] for item in first.items + second.items]
    assert actual == expected and len(set(actual)) == 13
    assert first.coverage["exhaustive"] and first.coverage["matched_count"] == 13
    assert second.next_cursor is None
    changed = sources.search(call_id="changed", scope=scope, mode="metadata", sort="collected_desc", limit=10, scope_version=2, cursor=first.next_cursor)
    assert changed.error_code == "cursor_scope_mismatch"


def test_multi_membership_filter_and_unknown_publication_are_explicit(app_paths):
    db, sources = _setup(app_paths)
    first = db.create_favorite_source(folder_id=9902, folder_title="A", history_policy="all")
    second = db.create_favorite_source(folder_id=9903, folder_title="B", history_policy="all")
    item = FavoriteItem(bvid="BV9B23456789", title="旧电影", uploader="电影作者", favorite_time=100)
    db.record_source_snapshot(first, [item], processing_profile="fast", authoritative=True, remote_total=1)
    db.record_source_snapshot(second, [FavoriteItem(bvid=item.bvid, title=item.title, uploader=item.uploader, favorite_time=300)], processing_profile="fast", authoritative=True, remote_total=1)
    scope = SourceScope(source_db_ids=frozenset({first}))
    result = sources.search(call_id="filter", scope=scope, mode="metadata", query="电影", collected_to=150, sort="collected_desc")
    assert len(result.items) == 1
    assert [m["source_db_id"] for m in result.items[0]["memberships"]] == [first]
    assert result.coverage["unknown_published_count"] == 1
    unknown = sources.search(call_id="unknown", scope=scope, mode="metadata", published_from=1000)
    assert unknown.status == "empty" and unknown.coverage["unknown_published_count"] == 1
    assert sources.search(call_id="empty", scope=SourceScope(source_db_ids=frozenset({999}))).coverage["visible_count"] == 0


def test_full_scope_defaults_to_on_demand_and_does_not_queue_model_work(app_paths):
    db, _sources = _setup(app_paths)
    source_id = db.create_favorite_source(folder_id=9904, folder_title="A", history_policy="all")
    store = AssistantRunStore(db)
    space = store.create_space(name="全库", all_active=True)
    assert space["maintenance_mode"] == "on_demand"
    db.record_source_snapshot(source_id, [FavoriteItem(bvid="BV9C23456789", title="新片", uploader="UP", favorite_time=100)], processing_profile="fast", authoritative=True, remote_total=1)
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM assistant_source_dirty").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM assistant_jobs").fetchone()[0] == 0


def test_empty_summary_does_not_hide_available_raw_subtitle(app_paths):
    db, sources = _setup(app_paths)
    source_id = db.create_favorite_source(folder_id=9905, folder_title="A", history_policy="all")
    db.record_source_snapshot(source_id, [FavoriteItem(bvid="BV9D23456789", title="有字幕无摘要", uploader="UP", favorite_time=100)], processing_profile="fast", authoritative=True, remote_total=1)
    video_id = int(db.get_video_by_source("BV9D23456789")["id"])
    path = sources.artifacts.video_dir("BV9D23456789") / "subtitle-raw.txt"
    path.write_text("原始字幕内容", encoding="utf-8")
    db.update_video(video_id, raw_subtitle_path=str(path), status="completed")
    scope = SourceScope(source_db_ids=frozenset({source_id}))
    summary = sources.read(call_id="summary", scope=scope, source_ref=f"video:{video_id}", view="summary")
    assert summary.status == "empty"
    assert "transcript" in summary.coverage["available_views"]
    transcript = sources.read(call_id="transcript", scope=scope, source_ref=f"video:{video_id}", view="transcript")
    assert transcript.status == "ok" and "原始字幕内容" in transcript.items[0]["content"]


def test_explicit_batch_has_persistent_hard_model_budget_and_targets_one_space(app_paths):
    db, sources = _setup(app_paths)
    source_id = db.create_favorite_source(folder_id=9906, folder_title="A", history_policy="all")
    db.record_source_snapshot(source_id, [FavoriteItem(bvid="BV9E23456789", title="材料", uploader="UP", favorite_time=100)], processing_profile="fast", authoritative=True, remote_total=1)
    video_id = int(db.get_video_by_source("BV9E23456789")["id"])
    store = AssistantRunStore(db)
    automatic = store.create_space(name="窄自动", source_ids=[source_id], video_ids=[video_id], maintenance_mode="automatic")
    manual = store.create_space(name="全库按需", all_active=True)
    wiki = WikiService(db=db, store=store, sources=sources)
    batch = wiki.bootstrap_space(manual["id"], limit=1, model_budget=1)
    assert batch["queued"] == 1 and batch["model_budget"] == 1

    class Provider:
        calls = 0
        def generate_json(self, **_kwargs):
            self.calls += 1
            return {}

    delegate = Provider()
    budgeted = BudgetedStructuredProvider(db, batch["batch_id"], delegate)
    assert budgeted.generate_json(system="s", prompt="p") == {}
    with pytest.raises(MaintenanceBudgetExceeded):
        budgeted.generate_json(system="s", prompt="p")
    with db.connect() as connection:
        assert connection.execute("SELECT calls_used FROM assistant_maintenance_batches WHERE id=?", (batch["batch_id"],)).fetchone()[0] == 1
    assert delegate.calls == 1

    manual_jobs = wiki._enqueue_integrations(video_id, "a" * 64, batch_id=batch["batch_id"])
    auto_jobs = wiki._enqueue_integrations(video_id, "b" * 64)
    with db.connect() as connection:
        targets = [connection.execute("SELECT payload_json FROM assistant_jobs WHERE id=?", (job_id,)).fetchone()[0] for job_id in manual_jobs + auto_jobs]
    assert len(targets) == 2
    assert f'"space_id": {manual["id"]}' in targets[0]
    assert f'"space_id": {automatic["id"]}' in targets[1]
