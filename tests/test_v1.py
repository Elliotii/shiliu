from __future__ import annotations

from pathlib import Path
import sqlite3
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.artifacts import ArtifactStore
from shiliu.bilibili import BilibiliAdapter
from shiliu.config import load_config
from shiliu.db import Database
from shiliu.domain import (
    FavoriteItem,
    FavoriteSourcePreview,
    SummaryResult,
    SummaryReviewResult,
    TranscriptResult,
)
from shiliu.llm import OpenAICompatibleProvider
from shiliu.pipeline import PipelineService
from shiliu.domain import SyncMode
from shiliu.sync import SyncService
from shiliu.web import create_web_app


def favorite(bvid: str, *, favorite_time: int, title: str = "视频") -> FavoriteItem:
    return FavoriteItem(
        bvid=bvid,
        title=title,
        uploader="UP",
        favorite_time=favorite_time,
    )


def test_multi_source_memberships_deduplicate_video_and_sort_by_favorite_time(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    first = db.create_favorite_source(
        folder_id=100,
        folder_title="大号收藏",
        account_id=1,
        account_name="大号",
        history_policy="latest_n",
        history_limit=2,
    )
    items = [
        favorite("BV1111111111", favorite_time=300, title="最新"),
        favorite("BV2222222222", favorite_time=200, title="次新"),
        favorite("BV3333333333", favorite_time=100, title="旧视频"),
    ]
    assert db.initialize_source_memberships(first, items) == 2
    assert db.history_pending_count() == 2

    video_id = db.materialize_history_membership(first, "BV1111111111")
    assert db.get_video(video_id)["processing_profile"] == "formal"

    second = db.create_favorite_source(
        folder_id=200,
        folder_title="另一个收藏",
        account_id=2,
        account_name="小号",
        history_policy="future_only",
    )
    db.initialize_source_memberships(
        second, [favorite("BV1111111111", favorite_time=400, title="同一视频")]
    )
    assert len(db.video_sources(video_id)) == 2

    created = db.record_source_snapshot(
        second,
        [
            favorite("BV4444444444", favorite_time=500, title="刚收藏"),
            favorite("BV1111111111", favorite_time=400, title="同一视频"),
        ],
        processing_profile="fast",
    )
    assert len(created) == 1
    assert db.get_video(created[0])["processing_profile"] == "fast"
    assert db.list_videos()[0]["source_id"] == "BV4444444444"


def test_source_order_can_be_changed_and_persists(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    first = db.create_favorite_source(folder_id=100, folder_title="LLM")
    second = db.create_favorite_source(folder_id=200, folder_title="新收藏夹")

    assert [source["id"] for source in db.list_sources()] == [first, second]
    assert db.move_source(second, "up") is True
    assert [source["id"] for source in db.list_sources()] == [second, first]
    assert db.move_source(second, "up") is False

    Database(app_paths.database).initialize()
    assert [source["id"] for source in db.list_sources()] == [second, first]


def test_source_move_endpoint_updates_settings_and_home_order(app_paths) -> None:
    application = Application(app_paths)
    first = application.db.create_favorite_source(folder_id=100, folder_title="LLM")
    second = application.db.create_favorite_source(folder_id=200, folder_title="新收藏夹")
    client = TestClient(create_web_app(application))

    response = client.post(f"/api/sources/{second}/move", json={"direction": "up"})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "moved": True}
    assert [source["id"] for source in application.db.list_sources()] == [second, first]
    assert client.get("/").text.index("新收藏夹") < client.get("/").text.index("LLM")


def test_old_xhigh_config_is_normalized_to_max(app_paths) -> None:
    app_paths.state_dir.mkdir(parents=True)
    app_paths.config.write_text(
        f'''[app]
content_dir = "{app_paths.content_dir}"
[bilibili]
favorite_id = 0
[llm]
base_url = "https://example.com/v1"
model = "demo"
formal_reasoning_effort = "xhigh"
''',
        encoding="utf-8",
    )
    config = load_config(app_paths)
    assert config.formal_reasoning_effort == "max"
    assert config.model_for("fast_transcript") == "demo"


def test_schema_migration_keeps_pre_v3_database_backup(app_paths) -> None:
    app_paths.state_dir.mkdir(parents=True)
    connection = sqlite3.connect(app_paths.database)
    connection.executescript(
        """
        CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO schema_meta(key, value) VALUES('schema_version', '1');
        CREATE TABLE proof(value TEXT NOT NULL);
        INSERT INTO proof(value) VALUES('v0-data');
        """
    )
    connection.commit()
    connection.close()

    Database(app_paths.database).initialize()
    backup = app_paths.database.with_name("shiliu.pre-v3.backup.db")
    assert backup.is_file()
    copied = sqlite3.connect(backup)
    assert copied.execute("SELECT value FROM proof").fetchone()[0] == "v0-data"
    assert copied.execute(
        "SELECT value FROM schema_meta WHERE key='schema_version'"
    ).fetchone()[0] == "1"
    copied.close()


def test_provider_sends_deepseek_thinking_controls() -> None:
    captured: dict = {}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, *, headers, json):
            captured.update(json)
            request = httpx.Request("POST", url)
            return httpx.Response(
                200,
                request=request,
                json={"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]},
            )

    provider = OpenAICompatibleProvider(
        base_url="https://api.deepseek.com",
        api_key="secret",
        model="deepseek-v4-pro",
        thinking_enabled=True,
        reasoning_effort="xhigh",
    )
    with patch("shiliu.llm.httpx.Client", FakeClient):
        assert provider.test_connection() == "OK"
    assert captured["thinking"] == {"type": "enabled"}
    assert captured["reasoning_effort"] == "max"
    assert "temperature" not in captured


def test_public_favorite_url_preview_parses_fid_without_importing(tmp_path: Path) -> None:
    adapter = BilibiliAdapter(tmp_path)
    with patch.object(
        adapter,
        "_run_bridge",
        return_value={
            "account_id": 32958899,
            "account_name": "零分姐姐",
            "folder_id": 3876418799,
            "folder_title": "2026找工作学习",
            "media_count": 128,
        },
    ) as bridge:
        preview = adapter.preview_favorite_url(
            "https://space.bilibili.com/32958899/favlist?fid=3876418799&ftype=create"
        )
    assert preview.folder_title == "2026找工作学习"
    assert preview.media_count == 128
    bridge.assert_called_once_with(["favorite-preview", "3876418799"])


class BundleAdapter:
    def fetch_video_bundle(self, bvid: str):
        from tests.test_pipeline import bundle

        return bundle()


class RefinementProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self) -> None:
        self.calls: list[type] = []

    def complete_json(self, prompt: str, schema):
        self.calls.append(schema)
        if schema is TranscriptResult:
            text = "快速整理原文。" if self.calls.count(TranscriptResult) == 1 else "精修后的原文。"
            return TranscriptResult.model_validate(
                {"sections": [{"title": "主题", "start_seconds": 0, "paragraphs": [text]}]}
            )
        if schema is SummaryResult:
            return SummaryResult.model_validate(
                {
                    "conclusion": "快速摘要",
                    "key_points": ["一", "二", "三"],
                    "detailed_notes": ["笔记"],
                }
            )
        if schema is SummaryReviewResult:
            return SummaryReviewResult.model_validate(
                {"decision": "keep", "change_reasons": ["摘要仍然准确"], "revised_summary": None}
            )
        raise AssertionError(schema)


def test_fast_result_is_refined_atomically_and_keep_preserves_summary(app_paths) -> None:
    from tests.test_pipeline import bundle

    db = Database(app_paths.database)
    db.initialize()
    artifacts = ArtifactStore(app_paths.videos_dir)
    provider = RefinementProvider()

    class Adapter:
        def fetch_video_bundle(self, bvid: str):
            return bundle()

    pipeline = PipelineService(
        db=db,
        adapter=Adapter(),
        artifacts=artifacts,
        provider_factory=lambda role: provider,
    )
    video_id = db.create_video("BV1234567890", "标题", processing_profile="fast")
    assert pipeline.process_video(video_id) is True
    fast = db.get_video(video_id)
    assert fast["active_revision"] == "fast"
    assert fast["refinement_status"] == "pending"
    assert (artifacts.video_dir("BV1234567890") / "summary.fast.json").is_file()

    assert pipeline.process_refinement(video_id) is True
    refined = db.get_video(video_id)
    assert refined["active_revision"] == "refined"
    assert refined["refinement_status"] == "completed"
    assert Path(refined["transcript_path"]).name == "transcript.refined.md"
    summary = artifacts.load_summary("BV1234567890", revision="refined")
    assert summary.conclusion == "快速摘要"
    assert provider.calls.count(TranscriptResult) == 2
    assert provider.calls.count(SummaryResult) == 1
    assert provider.calls.count(SummaryReviewResult) == 1


def test_source_preview_endpoint_has_no_database_side_effect(app_paths) -> None:
    application = Application(app_paths)
    application.adapter.preview_favorite_url = lambda url: FavoriteSourcePreview(
        account_id=32958899,
        account_name="零分姐姐",
        folder_id=3876418799,
        folder_title="2026找工作学习",
        media_count=128,
        original_url=url,
    )
    client = TestClient(create_web_app(application))
    response = client.post(
        "/api/sources/preview",
        json={"url": "https://space.bilibili.com/32958899/favlist?fid=3876418799"},
    )
    assert response.status_code == 200
    assert response.json()["preview"]["media_count"] == 128
    assert application.db.list_sources() == []
    assert application.db.list_videos() == []


def test_scheduled_history_backlog_uses_formal_profile_and_caps_batch_at_eight(app_paths) -> None:
    from datetime import datetime

    db = Database(app_paths.database)
    db.initialize()
    source_id = db.create_favorite_source(
        folder_id=42,
        folder_title="历史收藏",
        history_policy="all",
    )
    items = [
        favorite(f"BV{i:010d}", favorite_time=1000 - i, title=f"历史 {i}")
        for i in range(10)
    ]
    assert db.initialize_source_memberships(source_id, items) == 10

    class Adapter:
        def list_favorite_items(self, folder_id: int):
            assert folder_id == 42
            return items

    class Pipeline:
        def __init__(self):
            self.video_ids: list[int] = []

        def process_video(self, video_id: int) -> bool:
            self.video_ids.append(video_id)
            db.update_video(video_id, status="completed")
            return True

        def process_refinement(self, video_id: int) -> bool:
            return False

    pipeline = Pipeline()
    service = SyncService(
        db=db,
        adapter=Adapter(),
        pipeline=pipeline,
        favorite_id=None,
        lock_path=app_paths.sync_lock,
        now_factory=lambda: datetime(2026, 7, 15, 13, 0),
        sleep=lambda _: None,
        randint=lambda low, high: low,
    )
    result = service.sync(SyncMode.SCHEDULED)
    assert result.processed_count == 8
    assert db.history_pending_count() == 2
    assert len(pipeline.video_ids) == 8
    assert all(db.get_video(video_id)["processing_profile"] == "formal" for video_id in pipeline.video_ids)


def test_quiet_hours_still_process_history_without_scanning_or_refining(app_paths) -> None:
    from datetime import datetime

    db = Database(app_paths.database)
    db.initialize()
    source_id = db.create_favorite_source(
        folder_id=42,
        folder_title="历史收藏",
        history_policy="all",
    )
    items = [favorite("BV0000000001", favorite_time=1000, title="历史 1")]
    assert db.initialize_source_memberships(source_id, items) == 1

    class Adapter:
        def list_favorite_items(self, folder_id: int):
            raise AssertionError("静默时段不应扫描收藏夹")

    class Pipeline:
        def __init__(self):
            self.video_ids: list[int] = []
            self.refinement_calls = 0

        def process_video(self, video_id: int) -> bool:
            self.video_ids.append(video_id)
            db.update_video(video_id, status="completed")
            return True

        def process_refinement(self, video_id: int) -> bool:
            self.refinement_calls += 1
            return False

    pipeline = Pipeline()
    service = SyncService(
        db=db,
        adapter=Adapter(),
        pipeline=pipeline,
        favorite_id=None,
        lock_path=app_paths.sync_lock,
        now_factory=lambda: datetime(2026, 7, 15, 8, 0),
        sleep=lambda _: None,
        randint=lambda low, high: low,
    )

    result = service.sync(SyncMode.SCHEDULED)

    assert result.skipped_quiet_hours is True
    assert result.processed_count == 1
    assert result.history_pending_count == 0
    assert len(pipeline.video_ids) == 1
    assert pipeline.refinement_calls == 0
    assert "历史积压继续处理" in result.messages[0]
