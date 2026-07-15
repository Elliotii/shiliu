from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from shiliu.artifacts import ArtifactStore, extract_urls
from shiliu.asr import ASRService
from shiliu.bilibili import BilibiliAdapter
from shiliu.db import Database, utc_now
from shiliu.domain import (
    PipelineError,
    ASRTriggerMode,
    ProcessingProfile,
    RefinementStatus,
    StageName,
    StageStatus,
    SubtitleLanguage,
    SummaryResult,
    SummaryReviewResult,
    TranscriptResult,
    VideoStatus,
)
from shiliu.llm import OpenAICompatibleProvider
from shiliu.prompts import (
    SUMMARY_PROMPT_VERSION,
    TRANSCRIPT_PROMPT_VERSION,
    REFINEMENT_REVIEW_PROMPT_VERSION,
    build_refinement_review_prompt,
    build_summary_prompt,
    build_transcript_prompt,
)


ProviderFactory = Callable[..., OpenAICompatibleProvider]
ASRServiceFactory = Callable[[], ASRService]


class PipelineService:
    def __init__(
        self,
        *,
        db: Database,
        adapter: BilibiliAdapter,
        artifacts: ArtifactStore,
        provider_factory: ProviderFactory,
        asr_service_factory: ASRServiceFactory | None = None,
    ) -> None:
        self.db = db
        self.adapter = adapter
        self.artifacts = artifacts
        self.provider_factory = provider_factory
        self.asr_service_factory = asr_service_factory
        self._automatic_asr_submissions = 0

    def begin_sync_cycle(self) -> None:
        self._automatic_asr_submissions = 0

    def process_video(self, video_id: int) -> bool:
        video = self._require_video(video_id)
        status = VideoStatus(video["status"])
        if status in {VideoStatus.COMPLETED, VideoStatus.SKIPPED_NO_SUBTITLE, VideoStatus.NEEDS_REVIEW}:
            return False

        if not video.get("raw_subtitle_path"):
            asr_job = self.db.get_asr_job(video_id)
            if asr_job is not None:
                if not self._acquire_asr(video_id, ASRTriggerMode(str(asr_job["trigger_mode"]))):
                    return True
                video = self._require_video(video_id)
            elif not self._fetch_source(video):
                return True
            video = self._require_video(video_id)

        transcript = self._load_completed_transcript(video_id)
        if transcript is None:
            transcript_stage = self.db.ensure_stage(video_id, StageName.TRANSCRIPT)
            if not _stage_is_due(transcript_stage):
                return False
            transcript = self._run_transcript_stage(video_id)
            if transcript is None:
                return True

        summary = self._load_completed_summary(video_id)
        if summary is None:
            summary_stage = self.db.ensure_stage(video_id, StageName.SUMMARY)
            if not _stage_is_due(summary_stage):
                return False
            summary = self._run_summary_stage(video_id, transcript)
            if summary is None:
                return True
        return True

    def process_manual_asr(self, video_id: int) -> bool:
        video = self._require_video(video_id)
        if video.get("raw_subtitle_path"):
            return False
        acquired = self._acquire_asr(video_id, ASRTriggerMode.MANUAL, wait_seconds=180)
        if not acquired:
            return True
        return self.process_video(video_id)

    def process_refinement(self, video_id: int, *, force: bool = False) -> bool:
        video = self._require_video(video_id)
        refinement_status = str(video.get("refinement_status") or "not_required")
        if refinement_status not in {
            RefinementStatus.PENDING.value,
            RefinementStatus.PROCESSING.value,
            RefinementStatus.FAILED.value,
        }:
            return False
        if refinement_status == RefinementStatus.FAILED.value and not force:
            return False
        if not video.get("raw_subtitle_path"):
            return False

        transcript_stage = self.db.ensure_stage(video_id, StageName.REFINED_TRANSCRIPT)
        if force and transcript_stage["status"] == StageStatus.NEEDS_REVIEW.value:
            self.db.update_stage(
                video_id,
                StageName.REFINED_TRANSCRIPT,
                status=StageStatus.PENDING.value,
                attempt_count=0,
                next_retry_at=None,
                last_error_code=None,
                last_error_message=None,
            )
            transcript_stage = self.db.ensure_stage(video_id, StageName.REFINED_TRANSCRIPT)
        self.db.update_video(video_id, refinement_status=RefinementStatus.PROCESSING.value)
        if transcript_stage["status"] == StageStatus.COMPLETED.value:
            refined_transcript = self.artifacts.load_transcript(
                str(video["source_id"]), revision="refined"
            )
        else:
            if not _stage_is_due(transcript_stage):
                self.db.update_video(video_id, refinement_status=RefinementStatus.PENDING.value)
                return False
            refined_transcript = self._run_refined_transcript_stage(video_id, transcript_stage)
            if refined_transcript is None:
                return True

        review_stage = self.db.ensure_stage(video_id, StageName.REFINEMENT_REVIEW)
        if force and review_stage["status"] == StageStatus.NEEDS_REVIEW.value:
            self.db.update_stage(
                video_id,
                StageName.REFINEMENT_REVIEW,
                status=StageStatus.PENDING.value,
                attempt_count=0,
                next_retry_at=None,
                last_error_code=None,
                last_error_message=None,
            )
            review_stage = self.db.ensure_stage(video_id, StageName.REFINEMENT_REVIEW)
        if not _stage_is_due(review_stage):
            return False
        return self._run_refinement_review_stage(video_id, refined_transcript, review_stage)

    def _fetch_source(self, video: dict[str, object]) -> bool:
        video_id = int(video["id"])
        bvid = str(video["source_id"])
        try:
            bundle = self.adapter.fetch_video_bundle(bvid)
        except PipelineError as exc:
            if exc.code == "authentication_required":
                self._mark_video_needs_review(video_id, exc)
            else:
                self.db.update_video(
                    video_id,
                    status=VideoStatus.RETRY_WAIT.value if exc.retryable else VideoStatus.NEEDS_REVIEW.value,
                    error_code=exc.code,
                    error_message=str(exc),
                    subtitle_next_check_at=_iso_after(minutes=30) if exc.retryable else None,
                )
            return False

        self.artifacts.save_metadata(bundle)
        cover_path = self.artifacts.download_cover(bvid, bundle.cover_url)
        links = extract_urls(bundle.description)
        self.db.update_video(
            video_id,
            title=bundle.title,
            uploader=bundle.uploader,
            description=bundle.description,
            description_links_json=json.dumps(links, ensure_ascii=False),
            video_url=bundle.video_url,
            cover_url=bundle.cover_url,
            cover_path=str(cover_path) if cover_path else None,
            artifact_dir=str(self.artifacts.video_dir(bvid)),
            duration_seconds=bundle.duration_seconds,
            page_count=bundle.page_count,
            error_code=None,
            error_message=None,
        )

        if bundle.subtitle_track is None or not bundle.subtitle_segments:
            automatic = self._record_missing_subtitle(
                video_id, video, duration_seconds=bundle.duration_seconds
            )
            if automatic:
                return self._acquire_asr(video_id, ASRTriggerMode.AUTOMATIC)
            return False

        _, raw_text_path = self.artifacts.save_raw_subtitle(bvid, bundle.subtitle_segments)
        track = bundle.subtitle_track
        self.db.update_video(
            video_id,
            subtitle_language=track.language.value,
            subtitle_source=track.source.value,
            subtitle_upstream_type=track.upstream_type,
            raw_subtitle_path=str(raw_text_path),
            status=VideoStatus.TRANSCRIPT_PROCESSING.value,
            subtitle_next_check_at=None,
            error_code=None,
            error_message=None,
        )
        return True

    def _record_missing_subtitle(
        self,
        video_id: int,
        previous: dict[str, object],
        *,
        duration_seconds: int,
    ) -> bool:
        now = datetime.now(timezone.utc)
        count = int(previous.get("subtitle_check_count") or 0) + 1
        first_text = previous.get("subtitle_first_checked_at")
        first = _parse_time(str(first_text)) if first_text else now
        expired = now - first >= timedelta(hours=24)
        if count >= 3 or expired:
            short_video = 0 < duration_seconds <= 300 and self.asr_service_factory is not None
            eligible = short_video and self._automatic_asr_submissions < 1
            deferred = short_video and not eligible
            self.db.update_video(
                video_id,
                status=(
                    VideoStatus.SUBTITLE_PENDING.value
                    if eligible or deferred
                    else VideoStatus.SKIPPED_NO_SUBTITLE.value
                ),
                subtitle_check_count=count,
                subtitle_first_checked_at=first.isoformat(timespec="seconds"),
                subtitle_next_check_at=_iso_after(minutes=60) if deferred else None,
                error_code=(
                    "asr_pending"
                    if eligible
                    else "asr_deferred_capacity"
                    if deferred
                    else "no_supported_subtitle"
                ),
                error_message=(
                    "未发现站内字幕，将尝试语音识别"
                    if eligible
                    else "本轮自动识别名额已使用，将在下次同步继续"
                    if deferred
                    else "三次检查或 24 小时内未发现中文/英文字幕"
                ),
            )
            if eligible:
                self._automatic_asr_submissions += 1
            return eligible
        self.db.update_video(
            video_id,
            status=VideoStatus.SUBTITLE_PENDING.value,
            subtitle_check_count=count,
            subtitle_first_checked_at=first.isoformat(timespec="seconds"),
            subtitle_next_check_at=(now + timedelta(hours=1)).isoformat(timespec="seconds"),
            error_code="subtitle_pending",
            error_message="尚未发现中文或英文字幕，将在后续同步中重试",
        )
        return False

    def _acquire_asr(
        self,
        video_id: int,
        trigger_mode: ASRTriggerMode,
        *,
        wait_seconds: int = 0,
    ) -> bool:
        if self.asr_service_factory is None:
            return False
        try:
            service = self.asr_service_factory()
            return service.acquire(
                video_id, trigger_mode=trigger_mode, wait_seconds=wait_seconds
            )
        except PipelineError as exc:
            video = self._require_video(video_id)
            self.db.update_video(
                video_id,
                status=VideoStatus.SKIPPED_NO_SUBTITLE.value,
                error_code=exc.code,
                error_message=str(exc),
                subtitle_next_check_at=None,
            )
            return False

    def _run_transcript_stage(self, video_id: int) -> TranscriptResult | None:
        stage = self.db.ensure_stage(video_id, StageName.TRANSCRIPT)
        if not _stage_is_due(stage):
            return None
        video = self._require_video(video_id)
        bvid = str(video["source_id"])
        raw_json_path = self.artifacts.video_dir(bvid) / "subtitle-raw.json"
        segments_data = json.loads(raw_json_path.read_text(encoding="utf-8"))
        from shiliu.domain import SubtitleSegment

        segments = [SubtitleSegment.model_validate(item) for item in segments_data]
        language = SubtitleLanguage(str(video["subtitle_language"]))
        attempt = int(stage["attempt_count"]) + 1
        profile = str(video.get("processing_profile") or ProcessingProfile.FORMAL.value)
        role = "fast_transcript" if profile == ProcessingProfile.FAST.value else "formal_transcript"
        thinking = profile != ProcessingProfile.FAST.value
        self.db.update_stage(
            video_id,
            StageName.TRANSCRIPT,
            status=StageStatus.PROCESSING.value,
            attempt_count=attempt,
            next_retry_at=None,
            started_at=utc_now(),
            prompt_version=TRANSCRIPT_PROMPT_VERSION,
            profile=profile,
            thinking_enabled=int(thinking),
            reasoning_effort="max" if thinking else None,
        )
        self.db.update_video(video_id, status=VideoStatus.TRANSCRIPT_PROCESSING.value)
        try:
            started = time.monotonic()
            provider = self._provider(role)
            self.db.update_stage(
                video_id,
                StageName.TRANSCRIPT,
                provider=provider.name,
                model=provider.model,
            )
            prompt = build_transcript_prompt(title=str(video["title"]), language=language, segments=segments)
            result = provider.complete_json(prompt, TranscriptResult)
        except PipelineError as exc:
            self._record_stage_failure(video_id, StageName.TRANSCRIPT, attempt, exc)
            return None
        revision = "fast" if profile == ProcessingProfile.FAST.value else "refined"
        _, markdown_path = self.artifacts.save_transcript(bvid, result, revision=revision)
        if revision == "refined":
            self.artifacts.save_transcript(bvid, result)
        self.db.update_stage(
            video_id,
            StageName.TRANSCRIPT,
            status=StageStatus.COMPLETED.value,
            provider=provider.name,
            model=provider.model,
            completed_at=utc_now(),
            elapsed_seconds=time.monotonic() - started,
            last_error_code=None,
            last_error_message=None,
        )
        self.db.update_video(
            video_id,
            transcript_path=str(markdown_path),
            status=VideoStatus.SUMMARY_PROCESSING.value,
            error_code=None,
            error_message=None,
        )
        return result

    def _run_summary_stage(self, video_id: int, transcript: TranscriptResult) -> SummaryResult | None:
        stage = self.db.ensure_stage(video_id, StageName.SUMMARY)
        if not _stage_is_due(stage):
            return None
        video = self._require_video(video_id)
        links = _json_list(str(video.get("description_links_json") or "[]"))
        attempt = int(stage["attempt_count"]) + 1
        profile = str(video.get("processing_profile") or ProcessingProfile.FORMAL.value)
        self.db.update_stage(
            video_id,
            StageName.SUMMARY,
            status=StageStatus.PROCESSING.value,
            attempt_count=attempt,
            next_retry_at=None,
            started_at=utc_now(),
            prompt_version=SUMMARY_PROMPT_VERSION,
            profile=profile,
            thinking_enabled=1,
            reasoning_effort="max",
        )
        self.db.update_video(video_id, status=VideoStatus.SUMMARY_PROCESSING.value)
        try:
            started = time.monotonic()
            provider = self._provider("formal_summary")
            self.db.update_stage(
                video_id,
                StageName.SUMMARY,
                provider=provider.name,
                model=provider.model,
            )
            prompt = build_summary_prompt(
                title=str(video["title"]),
                description=str(video.get("description") or ""),
                links=links,
                transcript=transcript,
            )
            result = provider.complete_json(prompt, SummaryResult)
            result.related_links = links
        except PipelineError as exc:
            self._record_stage_failure(video_id, StageName.SUMMARY, attempt, exc)
            return None
        revision = "fast" if profile == ProcessingProfile.FAST.value else "refined"
        _, markdown_path = self.artifacts.save_summary(
            str(video["source_id"]), result, revision=revision
        )
        if revision == "refined":
            self.artifacts.save_summary(str(video["source_id"]), result)
        now = utc_now()
        self.db.update_stage(
            video_id,
            StageName.SUMMARY,
            status=StageStatus.COMPLETED.value,
            provider=provider.name,
            model=provider.model,
            completed_at=now,
            elapsed_seconds=time.monotonic() - started,
            last_error_code=None,
            last_error_message=None,
        )
        self.db.update_video(
            video_id,
            summary_path=str(markdown_path),
            status=VideoStatus.COMPLETED.value,
            completed_at=now,
            active_revision=revision,
            refinement_status=(
                RefinementStatus.PENDING.value
                if revision == "fast"
                else RefinementStatus.NOT_REQUIRED.value
            ),
            error_code=None,
            error_message=None,
        )
        self.db.add_event("summary_completed", video_id, {"source_id": video["source_id"]})
        return result

    def _run_refined_transcript_stage(
        self, video_id: int, stage: dict[str, object]
    ) -> TranscriptResult | None:
        video = self._require_video(video_id)
        bvid = str(video["source_id"])
        raw_json_path = self.artifacts.video_dir(bvid) / "subtitle-raw.json"
        segments_data = json.loads(raw_json_path.read_text(encoding="utf-8"))
        from shiliu.domain import SubtitleSegment

        segments = [SubtitleSegment.model_validate(item) for item in segments_data]
        language = SubtitleLanguage(str(video["subtitle_language"]))
        attempt = int(stage["attempt_count"]) + 1
        self.db.update_stage(
            video_id,
            StageName.REFINED_TRANSCRIPT,
            status=StageStatus.PROCESSING.value,
            attempt_count=attempt,
            next_retry_at=None,
            started_at=utc_now(),
            prompt_version=TRANSCRIPT_PROMPT_VERSION,
            profile="refinement",
            thinking_enabled=1,
            reasoning_effort="max",
        )
        started = time.monotonic()
        try:
            provider = self._provider("formal_transcript")
            self.db.update_stage(
                video_id,
                StageName.REFINED_TRANSCRIPT,
                provider=provider.name,
                model=provider.model,
            )
            prompt = build_transcript_prompt(title=str(video["title"]), language=language, segments=segments)
            result = provider.complete_json(prompt, TranscriptResult)
        except PipelineError as exc:
            self._record_refinement_failure(
                video_id, StageName.REFINED_TRANSCRIPT, attempt, exc
            )
            return None
        self.artifacts.save_transcript(bvid, result, revision="refined")
        self.db.update_stage(
            video_id,
            StageName.REFINED_TRANSCRIPT,
            status=StageStatus.COMPLETED.value,
            completed_at=utc_now(),
            elapsed_seconds=time.monotonic() - started,
            last_error_code=None,
            last_error_message=None,
        )
        return result

    def _run_refinement_review_stage(
        self,
        video_id: int,
        refined_transcript: TranscriptResult,
        stage: dict[str, object],
    ) -> bool:
        video = self._require_video(video_id)
        bvid = str(video["source_id"])
        links = _json_list(str(video.get("description_links_json") or "[]"))
        try:
            fast_summary = self.artifacts.load_summary(bvid, revision="fast")
        except FileNotFoundError:
            self._record_refinement_failure(
                video_id,
                StageName.REFINEMENT_REVIEW,
                int(stage["attempt_count"]) + 1,
                PipelineError(
                    "快速摘要文件不存在",
                    code="fast_artifact_missing",
                    retryable=False,
                ),
            )
            return True
        attempt = int(stage["attempt_count"]) + 1
        self.db.update_stage(
            video_id,
            StageName.REFINEMENT_REVIEW,
            status=StageStatus.PROCESSING.value,
            attempt_count=attempt,
            next_retry_at=None,
            started_at=utc_now(),
            prompt_version=REFINEMENT_REVIEW_PROMPT_VERSION,
            profile="refinement",
            thinking_enabled=1,
            reasoning_effort="max",
        )
        started = time.monotonic()
        try:
            provider = self._provider("formal_summary")
            self.db.update_stage(
                video_id,
                StageName.REFINEMENT_REVIEW,
                provider=provider.name,
                model=provider.model,
            )
            prompt = build_refinement_review_prompt(
                title=str(video["title"]),
                description=str(video.get("description") or ""),
                links=links,
                refined_transcript=refined_transcript,
                fast_summary=fast_summary,
            )
            review = provider.complete_json(prompt, SummaryReviewResult)
            final_summary = fast_summary if review.decision == "keep" else review.revised_summary
            if final_summary is None:
                raise PipelineError(
                    "精修摘要缺少 revised_summary",
                    code="invalid_model_output",
                    retryable=True,
                )
            final_summary.related_links = links
        except PipelineError as exc:
            self._record_refinement_failure(
                video_id, StageName.REFINEMENT_REVIEW, attempt, exc
            )
            return True

        _, transcript_markdown = self.artifacts.save_transcript(
            bvid, refined_transcript, revision="refined"
        )
        _, summary_markdown = self.artifacts.save_summary(
            bvid, final_summary, revision="refined"
        )
        # Keep the V0 filenames as readable aliases for external local-file use.
        self.artifacts.save_transcript(bvid, refined_transcript)
        self.artifacts.save_summary(bvid, final_summary)
        now = utc_now()
        self.db.update_stage(
            video_id,
            StageName.REFINEMENT_REVIEW,
            status=StageStatus.COMPLETED.value,
            completed_at=now,
            elapsed_seconds=time.monotonic() - started,
            decision=review.decision,
            change_reasons_json=json.dumps(review.change_reasons, ensure_ascii=False),
            last_error_code=None,
            last_error_message=None,
        )
        self.db.update_video(
            video_id,
            transcript_path=str(transcript_markdown),
            summary_path=str(summary_markdown),
            active_revision="refined",
            refinement_status=RefinementStatus.COMPLETED.value,
            error_code=None,
            error_message=None,
        )
        self.db.add_event(
            "refinement_completed",
            video_id,
            {"decision": review.decision, "change_reasons": review.change_reasons},
        )
        return True

    def _record_refinement_failure(
        self, video_id: int, stage_name: StageName, attempt: int, error: PipelineError
    ) -> None:
        retryable = error.retryable and attempt < 3
        next_retry = _iso_after(minutes=5 if attempt == 1 else 30) if retryable else None
        self.db.update_stage(
            video_id,
            stage_name,
            status=(StageStatus.RETRY_WAIT if retryable else StageStatus.NEEDS_REVIEW).value,
            attempt_count=attempt,
            next_retry_at=next_retry,
            last_error_code=error.code,
            last_error_message=str(error),
        )
        self.db.update_video(
            video_id,
            refinement_status=(
                RefinementStatus.PENDING.value if retryable else RefinementStatus.FAILED.value
            ),
            error_code=error.code if not retryable else None,
            error_message=str(error) if not retryable else None,
        )
        self.db.add_event(
            "refinement_failed",
            video_id,
            {"stage": stage_name.value, "code": error.code, "retryable": retryable},
        )

    def _provider(self, role: str) -> OpenAICompatibleProvider:
        try:
            return self.provider_factory(role)
        except TypeError:
            # V0 test doubles and third-party callers used a no-argument factory.
            return self.provider_factory()

    def _record_stage_failure(
        self, video_id: int, stage_name: StageName, attempt: int, error: PipelineError
    ) -> None:
        retryable = error.retryable and attempt < 3
        delay = 5 if attempt == 1 else 30
        next_retry = _iso_after(minutes=delay) if retryable else None
        stage_status = StageStatus.RETRY_WAIT if retryable else StageStatus.NEEDS_REVIEW
        video_status = VideoStatus.RETRY_WAIT if retryable else VideoStatus.NEEDS_REVIEW
        self.db.update_stage(
            video_id,
            stage_name,
            status=stage_status.value,
            next_retry_at=next_retry,
            last_error_code=error.code,
            last_error_message=str(error),
        )
        self.db.update_video(
            video_id,
            status=video_status.value,
            error_code=error.code,
            error_message=str(error),
        )
        self.db.add_event(
            "summary_failed",
            video_id,
            {"stage": stage_name.value, "code": error.code, "retryable": retryable},
        )

    def _mark_video_needs_review(self, video_id: int, error: PipelineError) -> None:
        self.db.update_video(
            video_id,
            status=VideoStatus.NEEDS_REVIEW.value,
            error_code=error.code,
            error_message=str(error),
        )
        self.db.add_event("summary_failed", video_id, {"stage": "source", "code": error.code})

    def _load_completed_transcript(self, video_id: int) -> TranscriptResult | None:
        video = self._require_video(video_id)
        stage = self.db.get_stage(video_id, StageName.TRANSCRIPT)
        if not stage or stage["status"] != StageStatus.COMPLETED.value:
            return None
        profile = str(video.get("processing_profile") or "formal")
        revision = "fast" if profile == "fast" else "refined"
        path = self.artifacts.video_dir(str(video["source_id"])) / f"transcript.{revision}.json"
        if not path.exists():
            path = self.artifacts.video_dir(str(video["source_id"])) / "transcript.json"
        return TranscriptResult.model_validate_json(path.read_text(encoding="utf-8"))

    def _load_completed_summary(self, video_id: int) -> SummaryResult | None:
        video = self._require_video(video_id)
        stage = self.db.get_stage(video_id, StageName.SUMMARY)
        if not stage or stage["status"] != StageStatus.COMPLETED.value:
            return None
        profile = str(video.get("processing_profile") or "formal")
        revision = "fast" if profile == "fast" else "refined"
        path = self.artifacts.video_dir(str(video["source_id"])) / f"summary.{revision}.json"
        if not path.exists():
            path = self.artifacts.video_dir(str(video["source_id"])) / "summary.json"
        return SummaryResult.model_validate_json(path.read_text(encoding="utf-8"))

    def _require_video(self, video_id: int) -> dict[str, object]:
        value = self.db.get_video(video_id)
        if value is None:
            raise KeyError(f"video {video_id} not found")
        return value


def _stage_is_due(stage: dict[str, object]) -> bool:
    if stage["status"] in {StageStatus.COMPLETED.value, StageStatus.NEEDS_REVIEW.value}:
        return False
    next_retry = stage.get("next_retry_at")
    return not next_retry or _parse_time(str(next_retry)) <= datetime.now(timezone.utc)


def _iso_after(*, minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat(timespec="seconds")


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _json_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []
