from __future__ import annotations

import json

import httpx
from unittest.mock import patch
from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.artifacts import ArtifactStore, extract_urls
from shiliu.domain import SubtitleLanguage, SubtitleSegment, SummaryResult
from shiliu.llm import OpenAICompatibleProvider
from shiliu.prompts import build_transcript_prompt
from shiliu.web import create_web_app


def test_extract_urls_preserves_order_without_opening_anything() -> None:
    text = "先看 https://example.com/a，再看 https://github.com/x/y。重复 https://example.com/a"
    assert extract_urls(text) == ["https://example.com/a", "https://github.com/x/y"]


def test_managed_file_rejects_path_traversal(app_paths, tmp_path) -> None:
    store = ArtifactStore(app_paths.videos_dir)
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    try:
        store.managed_file(outside)
    except ValueError as exc:
        assert "不在拾流内容目录" in str(exc)
    else:
        raise AssertionError("outside path must be rejected")


def test_english_prompt_keeps_raw_file_english_but_requests_chinese_output() -> None:
    segments = [SubtitleSegment.model_validate({"from": 0, "to": 1, "content": "Use Claude Code."})]
    prompt = build_transcript_prompt(title="Demo", language=SubtitleLanguage.EN, segments=segments)
    assert "原始字幕文件继续保留英文" in prompt
    assert "整理结果必须输出中文" in prompt
    assert "Claude Code" in prompt


def test_summary_requires_three_to_seven_key_points() -> None:
    valid = {
        "conclusion": "结论",
        "key_points": ["1", "2"],
        "detailed_notes": ["note"],
    }
    try:
        SummaryResult.model_validate(valid)
    except Exception:
        pass
    else:
        raise AssertionError("two key points must be rejected")


def test_provider_classifies_context_limit_without_truncating() -> None:
    request = httpx.Request("POST", "https://example.com/v1/chat/completions")
    response = httpx.Response(400, request=request, text='{"error":"maximum context length exceeded"}')
    try:
        OpenAICompatibleProvider._raise_for_status(response)
    except Exception as exc:
        assert getattr(exc, "code") == "context_too_large"
        assert getattr(exc, "retryable") is False
    else:
        raise AssertionError("context limit must not pass")


def test_homepage_transcript_and_ignore_routes(app_paths) -> None:
    application = Application(app_paths)
    video_id = application.db.create_video("BV1234567890", "测试视频")
    directory = application.artifacts.video_dir("BV1234567890")
    transcript = directory / "transcript.md"
    transcript.write_text("## 第一部分\n\n正文。\n", encoding="utf-8")
    raw = directory / "subtitle-raw.txt"
    raw.write_text("[00:00:00.000 --> 00:00:01.000] 正文\n", encoding="utf-8")
    application.db.update_video(
        video_id,
        transcript_path=str(transcript),
        raw_subtitle_path=str(raw),
        artifact_dir=str(directory),
        status="completed",
    )
    client = TestClient(create_web_app(application))

    home = client.get("/")
    assert home.status_code == 200
    assert "测试视频" in home.text
    assert "完整原文" in home.text

    page = client.get(f"/videos/{video_id}/transcript")
    assert page.status_code == 200
    assert "<h2>第一部分</h2>" in page.text
    assert "## 第一部分" not in page.text

    assert client.post(f"/api/videos/{video_id}/ignore").json() == {"ok": True}
    assert application.db.get_video(video_id)["is_ignored"] == 1
    assert client.post(f"/api/videos/{video_id}/restore").json() == {"ok": True}
    assert application.db.get_video(video_id)["is_ignored"] == 0


def test_raw_subtitle_route_cannot_take_arbitrary_path(app_paths) -> None:
    application = Application(app_paths)
    video_id = application.db.create_video("BV1234567890", "测试视频")
    application.db.update_video(video_id, raw_subtitle_path="/etc/passwd")
    client = TestClient(create_web_app(application), raise_server_exceptions=False)
    response = client.get(f"/media/{video_id}/raw-subtitle")
    assert response.status_code == 404


def test_retry_wait_card_offers_immediate_retry(app_paths) -> None:
    application = Application(app_paths)
    video_id = application.db.create_video("BV1234567890", "等待重试")
    application.db.update_video(video_id, status="retry_wait", error_message="稍后重试")
    client = TestClient(create_web_app(application))
    page = client.get("/")
    assert page.status_code == 200
    assert "立即重试" in page.text


def test_setup_has_independent_provider_connection_tool(app_paths) -> None:
    application = Application(app_paths)
    client = TestClient(create_web_app(application))
    page = client.get("/setup")
    assert "测试连接" in page.text
    with patch("shiliu.web.OpenAICompatibleProvider.test_connection", return_value="OK"):
        response = client.post(
            "/api/setup/test-provider",
            json={"base_url": "https://example.com/v1", "api_key": "secret", "model": "demo"},
        )
    assert response.status_code == 200
    assert response.json() == {"ok": True, "result": "OK"}


def test_setup_draft_saves_provider_fields_without_plaintext_key(app_paths) -> None:
    application = Application(app_paths)
    client = TestClient(create_web_app(application))
    with patch("shiliu.web.store_api_key") as save_key:
        response = client.post(
            "/api/setup/draft",
            json={
                "content_dir": str(app_paths.content_dir),
                "favorite_id": 42,
                "favorite_title": "llm",
                "base_url": "https://api.deepseek.com",
                "api_key": "secret-key",
                "model": "deepseek-reasoner",
            },
        )
    assert response.status_code == 200
    save_key.assert_called_once_with("secret-key")
    saved = app_paths.config.read_text(encoding="utf-8")
    assert "https://api.deepseek.com" in saved
    assert "deepseek-reasoner" in saved
    assert "secret-key" not in saved


def test_existing_qr_login_process_is_resumed_instead_of_rejected(app_paths) -> None:
    class WaitingProcess:
        def poll(self):
            return None

    application = Application(app_paths)
    web = create_web_app(application)
    web.state.login_process = WaitingProcess()
    qr_path = application.paths.state_dir / "bilibili-login-qr.png"
    qr_path.write_bytes(b"fake-png")
    client = TestClient(web)

    status = client.get("/api/setup/bilibili-login/status")
    assert status.json() == {
        "status": "waiting",
        "qr_url": "/api/setup/bilibili-login/qr",
    }
    resumed = client.post("/api/setup/bilibili-login")
    assert resumed.status_code == 200
    assert resumed.json()["reused"] is True
