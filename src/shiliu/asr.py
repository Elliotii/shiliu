from __future__ import annotations

import mimetypes
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from shiliu.artifacts import ArtifactStore
from shiliu.bilibili import BilibiliAdapter
from shiliu.db import Database, utc_now
from shiliu.storage.collection_leases import renewing_lease, worker_id
from shiliu.domain import (
    ASRJobStatus,
    ASRTriggerMode,
    PipelineError,
    SubtitleSegment,
    VideoStatus,
)


class ASRProvider(Protocol):
    name: str
    model: str

    def test_connection(self) -> None: ...

    def upload_audio(self, path: Path) -> str: ...

    def submit(self, remote_file_url: str) -> str: ...

    def query(self, task_id: str) -> tuple[str, str | None]: ...

    def fetch_result(self, result_url: str) -> dict[str, Any]: ...


class _IndexCoordinator(Protocol):
    def safe_sync_video(self, video_id: int, *, trigger: str) -> object: ...


class ParaformerProvider:
    name = "dashscope"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://dashscope.aliyuncs.com/api/v1",
        model: str = "paraformer-v2",
        timeout_seconds: int = 120,
    ) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def test_connection(self) -> None:
        self._upload_policy()

    def upload_audio(self, path: Path) -> str:
        policy = self._upload_policy()
        upload_dir = str(policy["upload_dir"]).rstrip("/")
        filename = path.name
        key = f"{upload_dir}/{filename}"
        fields = [
            ("key", (None, key)),
            ("policy", (None, str(policy["policy"]))),
            ("OSSAccessKeyId", (None, str(policy["oss_access_key_id"]))),
            ("signature", (None, str(policy["signature"]))),
            (
                "x-oss-object-acl",
                (None, str(policy.get("x_oss_object_acl", "private"))),
            ),
            (
                "x-oss-forbid-overwrite",
                (None, str(policy.get("x_oss_forbid_overwrite", "true"))),
            ),
            ("success_action_status", (None, "200")),
        ]
        media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        try:
            with (
                path.open("rb") as source,
                httpx.Client(timeout=self.timeout_seconds) as client,
            ):
                response = client.post(
                    str(policy["upload_host"]),
                    files=[*fields, ("file", (filename, source, media_type))],
                )
                response.raise_for_status()
        except (OSError, httpx.HTTPError) as exc:
            raise _provider_error(exc, "asr_upload_failed") from exc
        return f"oss://{key}"

    def submit(self, remote_file_url: str) -> str:
        payload = {
            "model": self.model,
            "input": {"file_urls": [remote_file_url]},
            "parameters": {
                "language_hints": ["zh", "en"],
                "timestamp_alignment_enabled": True,
                "disfluency_removal_enabled": False,
                "diarization_enabled": False,
            },
        }
        headers = {
            **self.headers,
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
            "X-DashScope-OssResourceResolve": "enable",
        }
        data = self._json_request(
            "POST",
            f"{self.base_url}/services/audio/asr/transcription",
            headers=headers,
            json=payload,
        )
        task_id = str((data.get("output") or {}).get("task_id") or "")
        if not task_id:
            raise PipelineError(
                "语音识别服务没有返回任务 ID", code="asr_submit_schema", retryable=True
            )
        return task_id

    def query(self, task_id: str) -> tuple[str, str | None]:
        data = self._json_request(
            "GET", f"{self.base_url}/tasks/{task_id}", headers=self.headers
        )
        output = data.get("output") or {}
        state = str(output.get("task_status") or output.get("status") or "").upper()
        if state in {"PENDING", "RUNNING", "PROCESSING"}:
            return "processing", None
        if state in {"SUCCEEDED", "SUCCESS"}:
            results = output.get("results") or []
            result_url = ""
            for item in results:
                if isinstance(item, dict) and item.get("transcription_url"):
                    result_url = str(item["transcription_url"])
                    break
            if not result_url:
                raise PipelineError(
                    "识别任务成功但没有结果地址",
                    code="asr_result_schema",
                    retryable=True,
                )
            return "completed", result_url
        if state == "UNKNOWN":
            # DashScope uses UNKNOWN for an absent/expired task. Preserve its ID
            # for review; repeated queries cannot recover a deleted result.
            raise PipelineError(
                "语音识别任务不存在或状态未知，原任务 ID 已保留待检查",
                code="asr_task_unknown", retryable=False,
            )
        message = str(
            output.get("message") or data.get("message") or "语音识别任务失败"
        )
        raise PipelineError(
            message, code="asr_task_failed",
            retryable=state not in {"FAILED", "CANCELED", "CANCELLED"},
        )

    def fetch_result(self, result_url: str) -> dict[str, Any]:
        try:
            with httpx.Client(
                timeout=self.timeout_seconds, follow_redirects=True
            ) as client:
                response = client.get(result_url)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise _provider_error(exc, "asr_result_fetch_failed") from exc
        if not isinstance(data, dict):
            raise PipelineError(
                "语音识别结果格式无效", code="asr_result_schema", retryable=True
            )
        return data

    def _upload_policy(self) -> dict[str, Any]:
        data = self._json_request(
            "GET",
            f"{self.base_url}/uploads",
            headers={**self.headers, "Content-Type": "application/json"},
            params={"action": "getPolicy", "model": self.model},
        )
        policy = data.get("data") or {}
        required = {
            "policy",
            "signature",
            "upload_dir",
            "upload_host",
            "oss_access_key_id",
        }
        if not isinstance(policy, dict) or not required.issubset(policy):
            raise PipelineError(
                "上传凭证格式无效", code="asr_policy_schema", retryable=True
            )
        return policy

    def _json_request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.request(method, url, **kwargs)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise _provider_error(exc, "asr_provider_error") from exc
        if not isinstance(data, dict):
            raise PipelineError(
                "语音识别服务返回格式无效", code="asr_provider_schema", retryable=True
            )
        return data


class ASRService:
    """Acquire normalized subtitle segments; transcript and summary stay in PipelineService."""

    def __init__(
        self,
        *,
        db: Database,
        adapter: BilibiliAdapter,
        artifacts: ArtifactStore,
        provider: ASRProvider,
        index_coordinator: _IndexCoordinator | None = None,
    ) -> None:
        self.db = db
        self.adapter = adapter
        self.artifacts = artifacts
        self.provider = provider
        self.index_coordinator = index_coordinator

    def acquire(
        self, video_id: int, *, trigger_mode: ASRTriggerMode, wait_seconds: int = 0
    ) -> bool:
        video = self.db.get_video(video_id)
        if video is None:
            raise KeyError(video_id)
        job = self.db.ensure_asr_job(
            video_id,
            provider=self.provider.name,
            model=self.provider.model,
            trigger_mode=trigger_mode.value,
        )
        if job["status"] == "completed" and video.get("raw_subtitle_path"):
            return True
        if job["status"] == "needs_review":
            # A missing upstream identity after dispatch is not proof of failure.
            if (
                job["last_error_code"]
                in {"external_result_unknown", "asr_submit_unknown"}
                or trigger_mode != ASRTriggerMode.MANUAL
            ):
                return False
            self.db.update_asr_job(
                video_id,
                status="pending",
                attempt_count=0,
                next_retry_at=None,
                last_error_code=None,
                last_error_message=None,
            )
        claim = self.db.claim_asr(video_id, worker_id())
        if claim is None:
            return False
        with renewing_lease(self.db, "asr_jobs", claim):
            return self._acquire_claimed(
                video_id,
                trigger_mode=trigger_mode,
                wait_seconds=wait_seconds,
                claim=claim,
            )

    def _acquire_claimed(
        self,
        video_id: int,
        *,
        trigger_mode: ASRTriggerMode,
        wait_seconds: int = 0,
        claim,
    ) -> bool:
        video = self.db.get_video(video_id)
        if video is None:
            raise KeyError(video_id)
        job = self.db.ensure_asr_job(
            video_id,
            provider=self.provider.name,
            model=self.provider.model,
            trigger_mode=trigger_mode.value,
        )
        if job["status"] == ASRJobStatus.COMPLETED.value and video.get(
            "raw_subtitle_path"
        ):
            return True
        if job["status"] == ASRJobStatus.NEEDS_REVIEW.value:
            if trigger_mode != ASRTriggerMode.MANUAL:
                return False
            self.db.update_asr_job(
                video_id,
                claim=claim,
                trigger_mode=ASRTriggerMode.MANUAL.value,
                status=ASRJobStatus.PENDING.value,
                attempt_count=0,
                next_retry_at=None,
                last_error_code=None,
                last_error_message=None,
            )
            job.update(
                trigger_mode=ASRTriggerMode.MANUAL.value,
                status=ASRJobStatus.PENDING.value,
                attempt_count=0,
                next_retry_at=None,
            )
        if job["status"] == ASRJobStatus.RETRY_WAIT.value and not _is_due(
            job.get("next_retry_at")
        ):
            return False
        if (
            trigger_mode == ASRTriggerMode.MANUAL
            and job["trigger_mode"] != trigger_mode.value
        ):
            self.db.update_asr_job(
                video_id, claim=claim, trigger_mode=trigger_mode.value
            )
            job["trigger_mode"] = trigger_mode.value

        job["input_raw"] = video.get("raw_subtitle_path")
        bvid = str(video["source_id"])
        temp_dir = self.artifacts.video_dir(bvid) / ".tmp"
        stored_audio = str(job.get("audio_path") or "")
        immutable_audio = stored_audio.startswith("artifact:")
        audio_path = temp_dir / "asr-input.m4a"
        try:
            if stored_audio and not immutable_audio:
                candidate = Path(stored_audio).resolve()
                if candidate.is_relative_to(self.artifacts.videos_dir.resolve()):
                    audio_path = candidate
                elif not job.get("task_id"):
                    raise PipelineError(
                        "音频输入未绑定当前隔离内容根",
                        code="asr_audio_root_mismatch",
                        retryable=False,
                    )
            if immutable_audio and not job.get("task_id"):
                try:
                    audio_path = self.artifacts.managed_file(stored_audio)
                except (OSError, ValueError, RuntimeError) as exc:
                    raise PipelineError(
                        "历史音频输入不可用",
                        code="asr_audio_unavailable",
                        retryable=False,
                    ) from exc
            # A durable upstream ID resumes query only, even when its old upload
            # URL is absent. Imported immutable input objects are never scratch.
            if not job.get("task_id") and not job.get("remote_file_url"):
                if not audio_path.is_file():
                    self.db.update_asr_job(
                        video_id,
                        claim=claim,
                        status=ASRJobStatus.AUDIO_DOWNLOADING.value,
                        audio_path=str(audio_path),
                    )
                    self.adapter.download_audio(bvid, audio_path)
                self.db.update_asr_job(
                    video_id, claim=claim, status=ASRJobStatus.UPLOADING.value
                )
                remote_url = self.provider.upload_audio(audio_path)
                self.db.update_asr_job(
                    video_id, claim=claim, remote_file_url=remote_url
                )
                job["remote_file_url"] = remote_url

            if not job.get("task_id"):
                # Commit the possibility of dispatch before sending. Recovery without
                # task_id now stops for review, never submits the request twice.
                self.db.update_asr_job(
                    video_id,
                    claim=claim,
                    status="submitted",
                    submitted_at=utc_now(),
                    last_error_code="external_result_unknown",
                )
                task_id = self.provider.submit(str(job["remote_file_url"]))
                self.db.update_asr_job(
                    video_id,
                    claim=claim,
                    status=ASRJobStatus.SUBMITTED.value,
                    task_id=task_id,
                    last_error_code=None,
                    submitted_at=utc_now(),
                )
                job["task_id"] = task_id

            deadline = time.monotonic() + max(0, wait_seconds)
            while True:
                state, result_url = self.provider.query(str(job["task_id"]))
                if state == "completed" and result_url:
                    payload = self.provider.fetch_result(result_url)
                    self._complete(video, job, payload, result_url, claim=claim)
                    if not immutable_audio:
                        _remove_temp(audio_path)
                    return True
                self.db.update_asr_job(
                    video_id, claim=claim, status=ASRJobStatus.PROCESSING.value
                )
                self.db.update_video(
                    video_id,
                    publish_guard=lambda c: self.db.check_lease(c, "asr_jobs", claim),
                    status=VideoStatus.SUBTITLE_PENDING.value,
                    subtitle_next_check_at=_iso_after(minutes=1),
                    error_code="asr_processing",
                    error_message="正在等待语音识别结果",
                )
                if time.monotonic() >= deadline:
                    return False
                time.sleep(min(3, max(0, deadline - time.monotonic())))
        except PipelineError as exc:
            self._record_failure(
                video_id,
                job,
                exc,
                audio_path,
                claim=claim,
                remove_audio=not immutable_audio,
            )
            return False

    def _complete(
        self,
        video: dict[str, Any],
        job: dict[str, Any],
        payload: dict[str, Any],
        result_url: str,
        *,
        claim,
    ) -> None:
        video_id = int(video["id"])
        bvid = str(video["source_id"])
        segments = normalize_paraformer_result(payload)
        if not segments:
            raise PipelineError(
                "语音识别结果没有有效文本", code="asr_empty_result", retryable=True
            )
        batch = self.artifacts.batch(video_id)
        batch.save_asr_raw(bvid, payload)
        _, raw_text_path = batch.save_raw_subtitle(bvid, segments)
        manual = str(job["trigger_mode"]) == ASRTriggerMode.MANUAL.value

        def publish(conn):
            self.db.check_lease(conn, "asr_jobs", claim)
            self.db.update_asr_job(
                video_id,
                claim=claim,
                conn=conn,
                status=ASRJobStatus.COMPLETED.value,
                result_url=result_url,
                completed_at=utc_now(),
                next_retry_at=None,
                last_error_code=None,
                last_error_message=None,
            )
            self.db.update_video(
                video_id,
                conn=conn,
                publish_guard=lambda c: self.db.check_lease(c, "asr_jobs", claim),
                subtitle_language=detect_subtitle_language(segments),
                subtitle_source="asr",
                raw_subtitle_path=str(raw_text_path),
                asr_provider=self.provider.name,
                asr_model=self.provider.model,
                processing_profile="fast" if manual else "formal",
                active_revision="fast" if manual else "refined",
                refinement_status="pending" if manual else "not_required",
                status=VideoStatus.TRANSCRIPT_PROCESSING.value,
                subtitle_next_check_at=None,
                error_code=None,
                error_message=None,
            )

        def validate(conn):
            self.db.check_lease(conn, "asr_jobs", claim)
            if self.db._video(conn, video_id, lock=True)[
                "raw_subtitle_path"
            ] != job.get("input_raw"):
                from shiliu.storage.fences import CoordinationConflict

                raise CoordinationConflict("source_version_changed")

        batch.commit(publish, validate=validate)
        if self.index_coordinator is not None:
            self.index_coordinator.safe_sync_video(
                video_id, trigger="asr_subtitle_completed"
            )

    def _record_failure(
        self,
        video_id: int,
        previous: dict[str, Any],
        exc: PipelineError,
        audio_path: Path,
        *,
        claim,
        remove_audio: bool = True,
    ) -> None:
        attempt = int(previous.get("attempt_count") or 0) + 1
        final = not exc.retryable or attempt >= 3
        delay = 10 if attempt == 1 else 30
        status = ASRJobStatus.NEEDS_REVIEW if final else ASRJobStatus.RETRY_WAIT
        next_retry = None if final else _iso_after(minutes=delay)
        job_fields: dict[str, Any] = {
            "status": status.value,
            "attempt_count": attempt,
            "next_retry_at": next_retry,
            "last_error_code": exc.code,
            "last_error_message": str(exc),
        }
        current = self.db.get_asr_job(video_id)
        if current and not current["task_id"] and current["status"] == "submitted":
            final = True
            next_retry = None
            job_fields.update(
                status="needs_review",
                next_retry_at=None,
                last_error_code="asr_submit_unknown",
            )
        self.db.update_asr_job(video_id, claim=claim, **job_fields)
        self.db.update_video(
            video_id,
            publish_guard=lambda c: self.db.check_lease(c, "asr_jobs", claim),
            status=VideoStatus.NEEDS_REVIEW.value
            if final
            else VideoStatus.SUBTITLE_PENDING.value,
            subtitle_next_check_at=next_retry,
            error_code=exc.code,
            error_message=str(exc),
        )
        if final and remove_audio:
            _remove_temp(audio_path)


def normalize_paraformer_result(payload: dict[str, Any]) -> list[SubtitleSegment]:
    segments: list[SubtitleSegment] = []
    for transcript in payload.get("transcripts") or []:
        if not isinstance(transcript, dict):
            continue
        for sentence in transcript.get("sentences") or []:
            if not isinstance(sentence, dict):
                continue
            text = str(sentence.get("text") or "").strip()
            if not text:
                continue
            begin = _milliseconds(sentence.get("begin_time"))
            end = _milliseconds(sentence.get("end_time"))
            segments.append(
                SubtitleSegment.model_validate(
                    {"from": begin, "to": max(begin, end), "content": text}
                )
            )
    return segments


def detect_subtitle_language(segments: list[SubtitleSegment]) -> str:
    text = " ".join(segment.content for segment in segments)
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    return "en" if latin_count > 0 and cjk_count == 0 else "zh"


def _milliseconds(value: Any) -> float:
    try:
        return max(0.0, float(value) / 1000.0)
    except (TypeError, ValueError):
        return 0.0


def _provider_error(exc: Exception, fallback_code: str) -> PipelineError:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        parts = urlsplit(str(exc.request.url))
        safe_url = f"{parts.scheme}://{parts.netloc}{parts.path}"
        detail = ""
        try:
            payload = exc.response.json()
            if isinstance(payload, dict):
                provider_code = str(payload.get("code") or "").strip()
                provider_message = str(payload.get("message") or "").strip()
                detail = ": ".join(
                    value for value in (provider_code, provider_message) if value
                )
        except ValueError:
            pass
        if status in {401, 403}:
            message = "语音识别 API Key 无效、地域不匹配或无权限"
            if detail:
                message += f"（{detail}）"
            return PipelineError(message, code="asr_authentication", retryable=False)
        retryable = status == 429 or status >= 500
        message = f"语音识别服务返回 HTTP {status} · {safe_url}"
        if detail:
            message += f"（{detail}）"
        return PipelineError(message, code=fallback_code, retryable=retryable)
    return PipelineError(str(exc), code=fallback_code, retryable=True)


def _is_due(value: Any) -> bool:
    if not value:
        return True
    try:
        return datetime.fromisoformat(str(value)) <= datetime.now(timezone.utc)
    except ValueError:
        return True


def _iso_after(*, minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat(
        timespec="seconds"
    )


def _remove_temp(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
        path.parent.rmdir()
    except OSError:
        pass
