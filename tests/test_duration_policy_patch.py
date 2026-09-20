from __future__ import annotations

from unittest.mock import patch

import httpx

from shiliu.artifacts import ArtifactStore
from shiliu.app import Application
from shiliu.db import Database
from shiliu.domain import (
    ASRTriggerMode,
    FavoriteItem,
    PipelineError,
    StageName,
    SummaryResult,
    TranscriptResult,
)
from shiliu.llm import OpenAICompatibleProvider
from shiliu.pipeline import (
    PipelineService,
    processing_policy,
    summary_token_limit,
    transcript_token_limit,
)
from shiliu.web import _format_duration
from shiliu.web import create_web_app
from fastapi.testclient import TestClient
from tests.test_pipeline import FakeAdapter, bundle


class RecordingProvider:
    def __init__(self, role: str, calls: list[dict[str, object]]) -> None:
        self.role = role
        self.calls = calls
        self.name = "fake-openai-compatible"
        self.model = "deepseek-v4-flash" if "transcript" in role else "deepseek-v4-pro"

    def complete_json(self, prompt: str, schema, *, max_tokens: int | None = None):
        self.calls.append({"role": self.role, "schema": schema, "max_tokens": max_tokens})
        if schema is TranscriptResult:
            return TranscriptResult.model_validate(
                {"sections": [{"title": "原文", "start_seconds": 0, "paragraphs": ["正文"]}]}
            )
        if schema is SummaryResult:
            return SummaryResult.model_validate(
                {
                    "conclusion": "结论",
                    "key_points": ["一", "二", "三"],
                    "detailed_notes": ["详细内容"],
                }
            )
        raise AssertionError(schema)


def make_service(app_paths, duration_seconds: int):
    db = Database(app_paths.database)
    db.initialize()
    calls: list[dict[str, object]] = []
    value = bundle().model_copy(update={"duration_seconds": duration_seconds})
    artifacts = ArtifactStore(app_paths.videos_dir)
    service = PipelineService(
        db=db,
        adapter=FakeAdapter(value),
        artifacts=artifacts,
        provider_factory=lambda role: RecordingProvider(role, calls),
    )
    video_id = db.create_video(value.bvid, value.title)
    return db, artifacts, service, video_id, calls


def test_duration_policy_boundaries_and_manual_asr_override() -> None:
    assert processing_policy(0) == "unknown_duration"
    assert processing_policy(480) == "full"
    assert processing_policy(481) == "summary_only"
    assert processing_policy(960) == "summary_only"
    assert processing_policy(961) == "subtitle_only"
    assert processing_policy(961, manual_asr=True) == "summary_only"


def test_duration_based_token_insurance_is_wide_but_bounded() -> None:
    assert transcript_token_limit(60) == 16384
    assert transcript_token_limit(480) == 24576
    assert transcript_token_limit(9999) == 24576
    assert summary_token_limit(60) == 32768
    assert summary_token_limit(480) == 32768
    assert summary_token_limit(960) == 65536
    assert summary_token_limit(9999) == 65536


def test_eight_minutes_uses_flash_cleanup_and_high_pro_summary(app_paths) -> None:
    db, _, service, video_id, calls = make_service(app_paths, 480)

    assert service.process_video(video_id) is True

    assert [call["role"] for call in calls] == ["fast_transcript", "formal_summary"]
    assert calls[0]["max_tokens"] == 24576
    assert calls[1]["max_tokens"] == 32768
    transcript_stage = db.get_stage(video_id, StageName.TRANSCRIPT)
    summary_stage = db.get_stage(video_id, StageName.SUMMARY)
    assert transcript_stage["thinking_enabled"] == 0
    assert transcript_stage["reasoning_effort"] is None
    assert transcript_stage["model"] == "deepseek-v4-flash"
    assert summary_stage["thinking_enabled"] == 1
    assert summary_stage["reasoning_effort"] == "high"
    assert summary_stage["model"] == "deepseek-v4-pro"


def test_between_eight_and_sixteen_minutes_only_generates_summary(app_paths) -> None:
    db, artifacts, service, video_id, calls = make_service(app_paths, 481)

    assert service.process_video(video_id) is True

    assert [call["role"] for call in calls] == ["formal_summary"]
    assert db.get_stage(video_id, StageName.TRANSCRIPT) is None
    assert db.get_stage(video_id, StageName.SUMMARY)["status"] == "completed"
    video = db.get_video(video_id)
    assert video["status"] == "completed"
    assert video["transcript_path"] is None
    assert video["refinement_status"] == "not_required"
    directory = artifacts.video_dir(str(video["source_id"]))
    assert not list(directory.glob("transcript*.json"))
    assert (directory / "summary.refined.json").is_file()


def test_over_sixteen_minutes_only_saves_raw_subtitle(app_paths) -> None:
    db, artifacts, service, video_id, calls = make_service(app_paths, 961)

    assert service.process_video(video_id) is True

    assert calls == []
    assert db.get_stage(video_id, StageName.TRANSCRIPT) is None
    assert db.get_stage(video_id, StageName.SUMMARY) is None
    video = db.get_video(video_id)
    assert video["status"] == "completed"
    assert video["summary_path"] is None
    assert (artifacts.video_dir(str(video["source_id"])) / "subtitle-raw.txt").is_file()
    assert service.process_video(video_id) is False


def test_manual_asr_over_sixteen_minutes_still_generates_direct_summary(app_paths) -> None:
    db, artifacts, service, video_id, calls = make_service(app_paths, 961)
    value = bundle().model_copy(update={"duration_seconds": 961})
    _, raw_path = artifacts.save_raw_subtitle(value.bvid, value.subtitle_segments)
    db.update_video(
        video_id,
        duration_seconds=961,
        raw_subtitle_path=str(raw_path),
        subtitle_language=value.subtitle_track.language.value,
        subtitle_source="asr",
        status="transcript_processing",
    )
    db.ensure_asr_job(
        video_id,
        provider="paraformer",
        model="paraformer-v2",
        trigger_mode=ASRTriggerMode.MANUAL.value,
    )

    assert service.process_video(video_id) is True

    assert [call["role"] for call in calls] == ["formal_summary"]
    assert db.get_stage(video_id, StageName.TRANSCRIPT) is None
    assert db.get_stage(video_id, StageName.SUMMARY)["reasoning_effort"] == "high"
    assert db.get_video(video_id)["refinement_status"] == "not_required"


def test_unknown_duration_stops_before_model_calls(app_paths) -> None:
    db, _, service, video_id, calls = make_service(app_paths, 0)

    assert service.process_video(video_id) is True

    video = db.get_video(video_id)
    assert calls == []
    assert video["status"] == "needs_review"
    assert video["error_code"] == "duration_unknown"


def test_favorite_scan_backfills_duration_without_overwriting_known_value(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    first = db.create_video("BV1234567890", "缺时长")
    second = db.create_video("BV2234567890", "已有时长", duration_seconds=900)

    changed = db.update_video_durations(
        [
            FavoriteItem(bvid="BV1234567890", title="缺时长", duration_seconds=480),
            FavoriteItem(bvid="BV2234567890", title="已有时长", duration_seconds=0),
        ]
    )

    assert changed == 1
    assert db.get_video(first)["duration_seconds"] == 480
    assert db.get_video(second)["duration_seconds"] == 900
    assert db.update_video_durations(
        [FavoriteItem(bvid="BV1234567890", title="缺时长", duration_seconds=480)]
    ) == 0


def test_duration_display_formats_and_hides_unknown_values() -> None:
    assert _format_duration(0) == ""
    assert _format_duration(8 * 60 + 3) == "08:03"
    assert _format_duration(60 * 60 + 2 * 60 + 9) == "1:02:09"


def test_homepage_shows_duration_and_raw_only_state(app_paths) -> None:
    application = Application(app_paths)
    video_id = application.db.create_video(
        "BV1234567890", "长视频", duration_seconds=16 * 60 + 1
    )
    directory = application.artifacts.video_dir("BV1234567890")
    raw = directory / "subtitle-raw.txt"
    raw.write_text("[00:00:00.000 --> 00:00:01.000] 正文\n", encoding="utf-8")
    application.db.update_video(
        video_id,
        raw_subtitle_path=str(raw),
        artifact_dir=str(directory),
        status="completed",
    )
    source_id = application.db.create_favorite_source(folder_id=1, folder_title="测试收藏夹")
    application.db.record_source_snapshot(
        source_id,
        [FavoriteItem(bvid="BV1234567890", title="长视频", favorite_time=1)],
        processing_profile="formal",
    )

    page = TestClient(create_web_app(application)).get("/")

    assert page.status_code == 200
    assert '<span class="duration-badge">16:01</span>' in page.text
    assert "仅保存原字幕（时长策略）" in page.text
    assert "原字幕" in page.text


def test_output_budget_exhaustion_is_not_retryable() -> None:
    provider = OpenAICompatibleProvider(
        base_url="https://api.deepseek.com/v1",
        api_key="secret",
        model="deepseek-v4-pro",
        thinking_enabled=True,
        reasoning_effort="high",
    )
    response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions"),
        json={
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {"content": "{}", "reasoning_content": "long reasoning"},
                }
            ]
        },
    )
    with patch.object(httpx.Client, "post", return_value=response):
        try:
            provider.complete_json("prompt", SummaryResult, max_tokens=32768)
        except PipelineError as exc:
            assert exc.code == "output_budget_exhausted"
            assert exc.retryable is False
        else:
            raise AssertionError("expected output budget failure")
