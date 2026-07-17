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
                {"sections": [{"title": "方法", "start_seconds": 0, "paragraphs": ["这是整理后的原文。"]}]}
            )
        if schema is SummaryResult:
            self.summary_calls += 1
            if self.summary_calls <= self.fail_summary_times:
                raise PipelineError("invalid json", code="invalid_model_output", retryable=True)
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


def make_pipeline(app_paths, adapter, provider):
    db = Database(app_paths.database)
    db.initialize()
    artifacts = ArtifactStore(app_paths.videos_dir)
    service = PipelineService(
        db=db,
        adapter=adapter,
        artifacts=artifacts,
        provider_factory=lambda: provider,
    )
    video_id = db.create_video("BV1234567890", "初始标题")
    return db, artifacts, service, video_id


def test_normal_video_uses_exactly_two_model_calls_and_saves_artifacts(app_paths) -> None:
    adapter = FakeAdapter(bundle())
    provider = FakeProvider()
    db, artifacts, service, video_id = make_pipeline(app_paths, adapter, provider)

    assert service.process_video(video_id) is True

    video = db.get_video(video_id)
    assert video["status"] == "completed"
    assert video["subtitle_language"] == "zh"
    assert video["subtitle_source"] == "ai"
    assert provider.transcript_calls == 1
    assert provider.summary_calls == 1
    directory = artifacts.video_dir("BV1234567890")
    assert (directory / "subtitle-raw.txt").read_text(encoding="utf-8").startswith("[00:00:00.100")
    assert (directory / "transcript.json").is_file()
    summary = SummaryResult.model_validate_json((directory / "summary.json").read_text(encoding="utf-8"))
    assert summary.related_links == ["https://github.com/example/demo", "https://example.com/docs"]


def test_summary_failure_does_not_repeat_successful_transcript_stage(app_paths) -> None:
    adapter = FakeAdapter(bundle())
    provider = FakeProvider(fail_summary_times=1)
    db, _, service, video_id = make_pipeline(app_paths, adapter, provider)

    service.process_video(video_id)
    assert db.get_stage(video_id, StageName.TRANSCRIPT)["status"] == "completed"
    assert db.get_stage(video_id, StageName.SUMMARY)["status"] == "retry_wait"
    assert provider.transcript_calls == 1
    assert provider.summary_calls == 1

    assert service.process_video(video_id) is False
    assert provider.transcript_calls == 1
    assert provider.summary_calls == 1

    db.update_stage(video_id, StageName.SUMMARY, next_retry_at="2000-01-01T00:00:00+00:00")
    service.process_video(video_id)
    assert db.get_video(video_id)["status"] == "completed"
    assert provider.transcript_calls == 1
    assert provider.summary_calls == 2
    assert adapter.calls == 1


def test_three_missing_subtitle_checks_end_in_skipped_without_model(app_paths) -> None:
    adapter = FakeAdapter(bundle(subtitle=False))
    provider = FakeProvider()
    db, _, service, video_id = make_pipeline(app_paths, adapter, provider)

    service.process_video(video_id)
    service.process_video(video_id)
    service.process_video(video_id)

    video = db.get_video(video_id)
    assert video["status"] == "skipped_no_subtitle"
    assert video["subtitle_check_count"] == 3
    assert provider.transcript_calls == 0
    assert provider.summary_calls == 0


def test_english_subtitle_metadata_is_preserved(app_paths) -> None:
    english = bundle().model_copy(
        update={
            "subtitle_track": bundle().subtitle_track.model_copy(
                update={"language": SubtitleLanguage.EN, "upstream_language": "ai-en"}
            )
        }
    )
    adapter = FakeAdapter(english)
    provider = FakeProvider()
    db, _, service, video_id = make_pipeline(app_paths, adapter, provider)
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


def test_scheduled_cycle_submits_only_one_automatic_asr_and_defers_the_next(app_paths) -> None:
    first = bundle(subtitle=False).model_copy(
        update={"duration_seconds": 183}
    )
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

    class ASR:
        def __init__(self) -> None:
            self.calls: list[int] = []

        def acquire(self, video_id: int, **_: object) -> bool:
            self.calls.append(video_id)
            return False

    db = Database(app_paths.database)
    db.initialize()
    asr = ASR()
    service = PipelineService(
        db=db,
        adapter=Adapter(),
        artifacts=ArtifactStore(app_paths.videos_dir),
        provider_factory=lambda: FakeProvider(),
        asr_service_factory=lambda: asr,
    )
    first_id = db.create_video(first.bvid, first.title)
    second_id = db.create_video(second.bvid, second.title)
    service.begin_sync_cycle()

    for _ in range(3):
        service.process_video(first_id)
    for _ in range(3):
        service.process_video(second_id)

    assert asr.calls == [first_id]
    deferred = db.get_video(second_id)
    assert deferred["status"] == "subtitle_pending"
    assert deferred["error_code"] == "asr_deferred_capacity"
    assert deferred["subtitle_next_check_at"] is not None
