from __future__ import annotations

from pathlib import Path

from shiliu.artifacts import ArtifactStore
from shiliu.asr import ASRService, detect_subtitle_language, normalize_paraformer_result
from shiliu.domain import ASRTriggerMode, PipelineError


class AudioAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def download_audio(self, bvid: str, output_path: Path) -> Path:
        self.calls += 1
        assert bvid == "BV1234567890"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"audio")
        return output_path


class SuccessfulProvider:
    name = "dashscope"
    model = "paraformer-v2"

    def __init__(self) -> None:
        self.upload_calls = 0
        self.submit_calls = 0
        self.query_calls = 0

    def test_connection(self) -> None:
        return None

    def upload_audio(self, path: Path) -> str:
        self.upload_calls += 1
        assert path.read_bytes() == b"audio"
        return "oss://temporary/audio.m4a"

    def submit(self, remote_file_url: str) -> str:
        self.submit_calls += 1
        assert remote_file_url.startswith("oss://")
        return "task-1"

    def query(self, task_id: str) -> tuple[str, str | None]:
        self.query_calls += 1
        assert task_id == "task-1"
        return "completed", "https://result.invalid/signed"

    def fetch_result(self, result_url: str):
        return {
            "transcripts": [
                {
                    "sentences": [
                        {"begin_time": 100, "end_time": 2200, "text": "第一句"},
                        {"begin_time": 2200, "end_time": 5000, "text": "第二句"},
                    ]
                }
            ]
        }


class FailingUploadProvider(SuccessfulProvider):
    def upload_audio(self, path: Path) -> str:
        self.upload_calls += 1
        raise PipelineError("temporary", code="asr_upload_failed", retryable=True)


def make_service(app_paths, provider, collection_db):
    db = collection_db
    video_id = db.create_video("BV1234567890", "无字幕视频")
    db.update_video(video_id, duration_seconds=183, status="skipped_no_subtitle")
    adapter = AudioAdapter()
    artifacts = ArtifactStore(app_paths.videos_dir, db=collection_db)
    service = ASRService(db=db, adapter=adapter, artifacts=artifacts, provider=provider)
    return db, adapter, artifacts, service, video_id


def test_manual_asr_is_idempotent_and_selects_fast_profile(
    app_paths, collection_db
) -> None:
    provider = SuccessfulProvider()
    db, adapter, artifacts, service, video_id = make_service(
        app_paths, provider, collection_db
    )

    assert service.acquire(video_id, trigger_mode=ASRTriggerMode.MANUAL) is True
    assert service.acquire(video_id, trigger_mode=ASRTriggerMode.MANUAL) is True

    video = db.get_video(video_id)
    job = db.get_asr_job(video_id)
    assert provider.upload_calls == provider.submit_calls == 1
    assert adapter.calls == 1
    assert job["status"] == "completed"
    assert job["trigger_mode"] == "manual"
    assert video["subtitle_source"] == "asr"
    assert video["processing_profile"] == "fast"
    assert video["refinement_status"] == "pending"
    assert artifacts.read_named("BV1234567890", "asr-raw.json")
    assert not (artifacts.video_dir("BV1234567890") / ".tmp" / "asr-input.m4a").exists()


def test_automatic_asr_selects_formal_profile(app_paths, collection_db) -> None:
    provider = SuccessfulProvider()
    db, _, _, service, video_id = make_service(app_paths, provider, collection_db)
    assert service.acquire(video_id, trigger_mode=ASRTriggerMode.AUTOMATIC) is True
    video = db.get_video(video_id)
    assert video["processing_profile"] == "formal"
    assert video["active_revision"] == "refined"
    assert video["refinement_status"] == "not_required"


def test_asr_retry_cooldown_prevents_duplicate_upload(app_paths, collection_db) -> None:
    provider = FailingUploadProvider()
    db, adapter, _, service, video_id = make_service(app_paths, provider, collection_db)

    assert service.acquire(video_id, trigger_mode=ASRTriggerMode.MANUAL) is False
    assert service.acquire(video_id, trigger_mode=ASRTriggerMode.MANUAL) is False

    job = db.get_asr_job(video_id)
    assert job["status"] == "retry_wait"
    assert job["attempt_count"] == 1
    assert job["next_retry_at"] is not None
    assert provider.upload_calls == 1
    assert adapter.calls == 1


def test_paraformer_result_normalizes_milliseconds() -> None:
    segments = normalize_paraformer_result(
        {
            "transcripts": [
                {
                    "sentences": [
                        {"begin_time": 1250, "end_time": 3000, "text": " 内容 "}
                    ]
                }
            ]
        }
    )
    assert len(segments) == 1
    assert segments[0].start == 1.25
    assert segments[0].end == 3.0
    assert segments[0].content == "内容"
    assert detect_subtitle_language(segments) == "zh"
    english = normalize_paraformer_result(
        {
            "transcripts": [
                {
                    "sentences": [
                        {"begin_time": 0, "end_time": 1000, "text": "Build an AI Agent"}
                    ]
                }
            ]
        }
    )
    assert detect_subtitle_language(english) == "en"


def test_asr_unknown_submit_never_resubmits(collection_db, app_paths):
    class Unknown(SuccessfulProvider):
        def submit(self, url):
            self.submit_calls += 1
            raise PipelineError(
                "transport unknown", code="asr_provider_error", retryable=True
            )

    provider = Unknown()
    db, _, _, service, vid = make_service(app_paths, provider, collection_db)
    assert not service.acquire(vid, trigger_mode=ASRTriggerMode.MANUAL)
    assert db.get_asr_job(vid)["last_error_code"] == "asr_submit_unknown"
    assert not service.acquire(vid, trigger_mode=ASRTriggerMode.MANUAL)
    assert provider.submit_calls == 1 and provider.query_calls == 0


def test_asr_restart_polls_existing_upstream_identity(collection_db, app_paths):
    class PendingOnce(SuccessfulProvider):
        def query(self, tid):
            self.query_calls += 1
            assert tid == "task-1"
            return (
                ("processing", None)
                if self.query_calls == 1
                else ("completed", "https://result.invalid/signed")
            )

    provider = PendingOnce()
    db, _, _, service, vid = make_service(app_paths, provider, collection_db)
    assert not service.acquire(vid, trigger_mode=ASRTriggerMode.MANUAL)
    # New service instance, same persisted identity. No new submit or upload.
    resumed = ASRService(
        db=db, adapter=service.adapter, artifacts=service.artifacts, provider=provider
    )
    assert resumed.acquire(vid, trigger_mode=ASRTriggerMode.MANUAL)
    assert (
        provider.submit_calls == 1
        and provider.upload_calls == 1
        and provider.query_calls == 2
    )


def test_upstream_task_without_upload_url_only_polls_and_preserves_imported_audio(
    app_paths, collection_db
):
    provider = SuccessfulProvider()
    db, adapter, artifacts, service, vid = make_service(
        app_paths, provider, collection_db
    )
    db.ensure_asr_job(
        vid, provider=provider.name, model=provider.model, trigger_mode="manual"
    )
    batch = artifacts.batch(vid)
    ref = batch._save("historical-asr-input.m4a", b"audio", media_type="audio/mp4")
    batch.commit(
        lambda c: c.execute(
            "UPDATE asr_jobs SET status='processing',task_id='task-1',remote_file_url=NULL,audio_path=%s WHERE workspace_id=%s AND video_id=%s",
            (ref, db.workspace_id, vid),
        )
    )
    path = artifacts.managed_file(ref)
    assert service.acquire(vid, trigger_mode=ASRTriggerMode.MANUAL)
    assert provider.submit_calls == provider.upload_calls == adapter.calls == 0
    assert provider.query_calls == 1 and path.read_bytes() == b"audio"
