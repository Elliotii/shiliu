from __future__ import annotations

from pathlib import Path

from shiliu.artifacts import ArtifactStore
from shiliu.db import Database
from shiliu.domain import (
    PipelineError,
    StageName,
    SubtitleLanguage,
    SummaryResult,
    TranscriptResult,
    VideoBundle,
)
from shiliu.pipeline import PipelineService
from shiliu.llm import OpenAICompatibleProvider


class FakeAdapter:
    def __init__(self, bundle: VideoBundle) -> None:
        self.bundle = bundle
        self.calls = 0

    def fetch_video_bundle(self, bvid: str) -> VideoBundle:
        self.calls += 1
        assert bvid == self.bundle.bvid
        return self.bundle


class FakeProvider:
    name = "fake-openai-compatible"
    model = "fake-model"

    def __init__(self, *, fail_summary_times: int = 0) -> None:
        self.fail_summary_times = fail_summary_times
        self.transcript_calls = 0
        self.summary_calls = 0

    def complete_json(self, prompt: str, schema, *, max_tokens: int | None = None):
        if schema is TranscriptResult:
            self.transcript_calls += 1
            return TranscriptResult.model_validate(
                {
                    "sections": [
                        {
                            "title": "方法",
                            "start_seconds": 0,
                            "paragraphs": ["这是整理后的原文。"],
                        }
                    ]
                }
            )
        if schema is SummaryResult:
            self.summary_calls += 1
            if self.summary_calls <= self.fail_summary_times:
                raise PipelineError(
                    "invalid json", code="invalid_model_output", retryable=True
                )
            return SummaryResult.model_validate(
                {
                    "conclusion": "一句话结论",
                    "key_points": ["要点一", "要点二", "要点三"],
                    "detailed_notes": ["详细笔记。"],
                    "related_links": ["https://hallucinated.invalid"],
                }
            )
        raise AssertionError(schema)


def bundle(*, subtitle: bool = True) -> VideoBundle:
    data = {
        "bvid": "BV1234567890",
        "title": "AI Agent 视频",
        "uploader": "UP",
        "description": "项目 https://github.com/example/demo ，文档 https://example.com/docs",
        "video_url": "https://www.bilibili.com/video/BV1234567890",
        "cover_url": None,
        "duration_seconds": 300,
        "page_count": 2,
        "subtitle_track": None,
        "subtitle_segments": [],
    }
    if subtitle:
        data["subtitle_track"] = {
            "language": "zh",
            "source": "ai",
            "upstream_type": 1,
            "upstream_language": "ai-zh",
        }
        data["subtitle_segments"] = [
            {"from": 0.1, "to": 2.2, "content": "这是第一句"},
            {"from": 2.2, "to": 5.0, "content": "这是第二句"},
        ]
    return VideoBundle.model_validate(data)


def make_pipeline(app_paths, adapter, provider, collection_db):
    db = collection_db
    artifacts = ArtifactStore(app_paths.videos_dir, db=collection_db)
    service = PipelineService(
        db=db,
        adapter=adapter,
        artifacts=artifacts,
        provider_factory=lambda: provider,
    )
    video_id = db.create_video("BV1234567890", "初始标题")
    return db, artifacts, service, video_id


def test_normal_video_uses_exactly_two_model_calls_and_saves_artifacts(
    app_paths, collection_db
) -> None:
    adapter = FakeAdapter(bundle())
    provider = FakeProvider()
    db, artifacts, service, video_id = make_pipeline(
        app_paths, adapter, provider, collection_db
    )

    assert service.process_video(video_id) is True

    video = db.get_video(video_id)
    assert video["status"] == "completed"
    assert video["subtitle_language"] == "zh"
    assert video["subtitle_source"] == "ai"
    assert provider.transcript_calls == 1
    assert provider.summary_calls == 1
    directory = app_paths.videos_dir / "explicit-export"
    artifacts.export("BV1234567890", directory)
    assert (
        (directory / "subtitle-raw.txt")
        .read_text(encoding="utf-8")
        .startswith("[00:00:00.100")
    )
    assert (directory / "transcript.json").is_file()
    summary = SummaryResult.model_validate_json(
        (directory / "summary.json").read_text(encoding="utf-8")
    )
    assert summary.related_links == [
        "https://github.com/example/demo",
        "https://example.com/docs",
    ]
    transcript_provenance = artifacts.load_generation_provenance(
        "BV1234567890", "transcript", revision="refined"
    )
    summary_provenance = artifacts.load_generation_provenance(
        "BV1234567890", "summary", revision="refined"
    )
    assert transcript_provenance["provider"] == provider.name
    assert transcript_provenance["model"] == provider.model
    assert transcript_provenance["prompt_version"]
    assert transcript_provenance["schema"] == "TranscriptResult"
    assert transcript_provenance["generated_at"]
    assert transcript_provenance["source_hash"].startswith("sha256:")
    assert summary_provenance["schema"] == "SummaryResult"


def test_missing_generation_provenance_is_explicitly_legacy_unknown(
    app_paths, collection_db
) -> None:
    store = ArtifactStore(app_paths.videos_dir, db=collection_db)
    vid = collection_db.create_video("BV1234567890", "旧摘要")
    batch = store.batch(vid)
    batch.save_summary(
        "BV1234567890",
        SummaryResult.model_validate(
            {
                "conclusion": "旧摘要",
                "key_points": ["一", "二", "三"],
                "detailed_notes": ["旧数据"],
            }
        ),
    )

    batch.commit(lambda conn: None)
    provenance = store.load_generation_provenance("BV1234567890", "summary")

    assert provenance == {
        "provenance_status": "legacy_unknown",
        "provider": "unknown",
        "model": "unknown",
        "prompt_version": "unknown",
        "schema": "unknown",
        "generated_at": None,
    }


def test_summary_failure_does_not_repeat_successful_transcript_stage(
    app_paths, collection_db
) -> None:
    adapter = FakeAdapter(bundle())
    provider = FakeProvider(fail_summary_times=1)
    db, _, service, video_id = make_pipeline(
        app_paths, adapter, provider, collection_db
    )

    service.process_video(video_id)
    assert db.get_stage(video_id, StageName.TRANSCRIPT)["status"] == "completed"
    assert db.get_stage(video_id, StageName.SUMMARY)["status"] == "retry_wait"
    assert provider.transcript_calls == 1
    assert provider.summary_calls == 1

    assert service.process_video(video_id) is False
    assert provider.transcript_calls == 1
    assert provider.summary_calls == 1

    db.update_stage(
        video_id, StageName.SUMMARY, next_retry_at="2000-01-01T00:00:00+00:00"
    )
    service.process_video(video_id)
    assert db.get_video(video_id)["status"] == "completed"
    assert provider.transcript_calls == 1
    assert provider.summary_calls == 2
    assert adapter.calls == 1


def test_three_missing_subtitle_checks_end_in_skipped_without_model(
    app_paths, collection_db
) -> None:
    adapter = FakeAdapter(bundle(subtitle=False))
    provider = FakeProvider()
    db, _, service, video_id = make_pipeline(
        app_paths, adapter, provider, collection_db
    )

    service.process_video(video_id)
    service.process_video(video_id)
    service.process_video(video_id)

    video = db.get_video(video_id)
    assert video["status"] == "skipped_no_subtitle"
    assert video["subtitle_check_count"] == 3
    assert provider.transcript_calls == 0
    assert provider.summary_calls == 0


def test_english_subtitle_metadata_is_preserved(app_paths, collection_db) -> None:
    english = bundle().model_copy(
        update={
            "subtitle_track": bundle().subtitle_track.model_copy(
                update={"language": SubtitleLanguage.EN, "upstream_language": "ai-en"}
            )
        }
    )
    adapter = FakeAdapter(english)
    provider = FakeProvider()
    db, _, service, video_id = make_pipeline(
        app_paths, adapter, provider, collection_db
    )
    service.process_video(video_id)
    assert db.get_video(video_id)["subtitle_language"] == "en"


def test_connection_test_allows_reasoning_token_budget() -> None:
    provider = OpenAICompatibleProvider(
        base_url="https://api.deepseek.com", api_key="secret", model="deepseek-reasoner"
    )
    from unittest.mock import patch

    with patch.object(provider, "_generate", return_value="OK") as generate:
        assert provider.test_connection() == "OK"
    assert generate.call_args.kwargs["max_tokens"] == 1024


def test_fractional_timestamps_from_model_are_valid() -> None:
    transcript = TranscriptResult.model_validate(
        {
            "sections": [
                {
                    "title": "开场",
                    "start_seconds": 0.08,
                    "paragraphs": ["正文"],
                },
                {
                    "title": "主题",
                    "start_seconds": 20.259,
                    "paragraphs": ["正文"],
                },
            ]
        }
    )
    assert transcript.sections[0].start_seconds == 0.08
    assert transcript.sections[1].start_seconds == 20.259


def test_scheduled_cycle_submits_two_eligible_automatic_asr_jobs(
    app_paths, collection_db
) -> None:
    first = bundle(subtitle=False).model_copy(update={"duration_seconds": 183})
    second = first.model_copy(
        update={
            "bvid": "BV2234567890",
            "title": "第二条无字幕视频",
            "video_url": "https://www.bilibili.com/video/BV2234567890",
        }
    )

    class Adapter:
        def fetch_video_bundle(self, bvid: str) -> VideoBundle:
            return first if bvid == first.bvid else second

    from shiliu.asr import ASRService
    from shiliu.domain import FavoriteItem, SyncMode
    from shiliu.sync import SyncService
    from test_collection_asr import SuccessfulProvider

    class Provider(SuccessfulProvider):
        def query(self, task_id):
            self.query_calls += 1
            return "processing", None

    class SyncAdapter(Adapter):
        def list_favorite_items(self, folder_id):
            return [FavoriteItem(bvid=b.bvid, title=b.title) for b in (first, second)]

        def download_audio(self, bvid, output_path):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"audio")
            return output_path

    db = collection_db
    provider = Provider()
    adapter = SyncAdapter()
    artifacts = ArtifactStore(app_paths.videos_dir, db=collection_db)
    asr = ASRService(db=db, adapter=adapter, artifacts=artifacts, provider=provider)
    service = PipelineService(
        db=db,
        adapter=adapter,
        artifacts=artifacts,
        provider_factory=lambda: FakeProvider(),
        asr_service_factory=lambda: asr,
    )
    source = db.create_favorite_source(folder_id=42, folder_title="合成")
    db.initialize_source_memberships(source, [], authoritative=True)
    db.record_source_snapshot(source, adapter.list_favorite_items(42), processing_profile="formal")
    for video in db.list_videos():
        db.update_video(video["id"], subtitle_check_count=2)
    sync = SyncService(db=db, adapter=adapter, pipeline=service, favorite_id=42,
                       lock_path=app_paths.sync_lock, sleep=lambda _: None)
    sync.sync(SyncMode.SCHEDULED)

    assert provider.submit_calls == provider.upload_calls == provider.query_calls == 2
    for video in db.list_videos():
        assert db.get_asr_job(video["id"])["status"] == "processing"
        assert video["status"] == "subtitle_pending"
        assert video["error_code"] == "asr_processing"


def test_discovery_cover_is_independent_of_models_and_preserves_old_cover_on_failure(
    app_paths, monkeypatch, collection_db
):
    from shiliu.domain import FavoriteItem

    db = collection_db
    artifacts = ArtifactStore(app_paths.videos_dir, db=collection_db)
    video_id = db.create_video("BV1234567890", "新收藏", "UP")

    def no_provider(*a, **k):
        raise AssertionError("discovery must not invoke a model")

    pipeline = PipelineService(
        db=db, adapter=None, artifacts=artifacts, provider_factory=no_provider
    )
    app_paths.state_dir.mkdir(parents=True, exist_ok=True)
    batch = artifacts.batch(video_id)
    cover = batch._save("cover.jpg", b"image", media_type="image/jpeg")
    batch.commit(lambda conn: None)
    calls = []
    monkeypatch.setattr(
        artifacts, "download_cover", lambda bvid, url: calls.append(url) or cover
    )
    item = FavoriteItem(
        bvid="BV1234567890", title="新收藏", cover_url="https://i.example/one.jpg"
    )
    pipeline.sync_favorite_covers([item])
    pipeline.sync_favorite_covers([item])
    assert calls == [item.cover_url]
    assert db.get_video(video_id)["status"] == "discovered"
    assert db.get_video(video_id)["cover_path"] == str(cover)
    monkeypatch.setattr(artifacts, "download_cover", lambda *a: None)
    changed = item.model_copy(update={"cover_url": "https://i.example/two.jpg"})
    pipeline.sync_favorite_covers([changed])
    assert db.get_video(video_id)["cover_url"] == item.cover_url
    assert db.get_video(video_id)["cover_path"] == str(cover)
    calls.clear()
    monkeypatch.setattr(
        artifacts, "download_cover", lambda bvid, url: calls.append(url) or cover
    )
    pipeline.sync_favorite_covers([changed])
    assert calls == [changed.cover_url]

    pipeline.adapter = FakeAdapter(
        bundle().model_copy(update={"cover_url": changed.cover_url})
    )
    calls.clear()
    assert pipeline._fetch_source(db.get_video(video_id))
    assert calls == []  # The source stage reuses the discovery cover.
