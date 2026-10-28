"""Small closeout regressions: real isolated PG, controlled external calls."""

from datetime import datetime, timezone

import pytest

from shiliu.asr import ASRService
from shiliu.domain import ASRTriggerMode, PipelineError, StageName, SyncMode
from shiliu.pipeline import PipelineService
from shiliu.sync import SyncService
from test_collection import CompletingPipeline, FakeAdapter as ScanAdapter, favorite
from test_collection_asr import SuccessfulProvider, make_service
from test_collection_pipeline import FakeAdapter, FakeProvider, bundle, make_pipeline


def test_nine_new_favorites_are_saved_and_processed_in_one_scheduled_cycle(
    collection_db, app_paths
):
    db = collection_db
    adapter = ScanAdapter([])
    pipeline = CompletingPipeline(db)
    sync = SyncService(db=db, adapter=adapter, pipeline=pipeline, favorite_id=42,
                       lock_path=app_paths.sync_lock, sleep=lambda _: None)
    assert sync.sync(SyncMode.SCHEDULED).baseline_created
    adapter.items = [favorite(f"BV{i:010d}", f"合成 {i}") for i in range(1, 10)]
    result = sync.sync(SyncMode.SCHEDULED)
    assert result.discovered_count == result.processed_count == 9
    assert len(set(pipeline.calls)) == len(db.list_videos()) == 9
    assert all(v["status"] == "completed" for v in db.list_videos())


@pytest.mark.parametrize("stage", [StageName.SOURCE_FETCH, StageName.SUMMARY,
                                    StageName.REFINED_TRANSCRIPT])
def test_stage_failures_survive_new_service_and_stop_after_three(
    collection_db, app_paths, stage
):
    class UnavailableAdapter(FakeAdapter):
        def fetch_video_bundle(self, bvid):
            self.calls += 1
            raise PipelineError("temporary", code="upstream_timeout", retryable=True)

    adapter = UnavailableAdapter(bundle()) if stage == StageName.SOURCE_FETCH else FakeAdapter(bundle())
    provider = FakeProvider(fail_summary_times=99)
    db, artifacts, service, vid = make_pipeline(app_paths, adapter, provider, collection_db)
    if stage == StageName.REFINED_TRANSCRIPT:
        # Save genuine synthetic source bytes through the normal source stage.
        assert service._fetch_source(db.get_video(vid))
        db.update_video(vid, refinement_status="pending")

        def fail(*args, **kwargs):
            provider.transcript_calls += 1
            raise PipelineError("temporary", code="provider_network", retryable=True)

        provider.complete_json = fail

    def process():
        # Reconstruct the service each time: no in-memory retry counter survives.
        resumed = PipelineService(db=db, adapter=adapter, artifacts=artifacts,
                                  provider_factory=lambda: provider)
        if stage == StageName.REFINED_TRANSCRIPT:
            return resumed.process_refinement(vid)
        return resumed.process_video(vid)

    for attempt in range(1, 4):
        before = datetime.now(timezone.utc)
        process()
        row = db.get_stage(vid, stage)
        assert row["attempt_count"] == attempt
        if attempt < 3:
            assert row["status"] == "retry_wait"
            wait = (datetime.fromisoformat(row["next_retry_at"]) - before).total_seconds()
            assert (299 if attempt == 1 else 1799) <= wait <= (301 if attempt == 1 else 1801)
            process()
            assert db.get_stage(vid, stage)["attempt_count"] == attempt
            db.update_stage(vid, stage, next_retry_at="2000-01-01T00:00:00+00:00")
        else:
            assert row["status"] == "needs_review" and row["next_retry_at"] is None
    for _ in range(2):
        process()
    assert db.get_stage(vid, stage)["attempt_count"] == 3
    assert (adapter.calls if stage == StageName.SOURCE_FETCH else
            provider.summary_calls if stage == StageName.SUMMARY else provider.transcript_calls) == 3


@pytest.mark.parametrize("retryable", [True, False])
def test_asr_query_failures_are_bounded_and_never_reupload_missing_scratch(
    collection_db, app_paths, retryable
):
    class FailingQuery(SuccessfulProvider):
        def query(self, task_id):
            assert task_id == "task-1"
            self.query_calls += 1
            raise PipelineError("controlled failure", code="asr_provider_error" if retryable
                                else "asr_authentication", retryable=retryable)

    provider = FailingQuery()
    db, adapter, artifacts, _, vid = make_service(app_paths, provider, collection_db)
    db.ensure_asr_job(vid, provider=provider.name, model=provider.model, trigger_mode="manual")
    db.update_asr_job(vid, status="processing", task_id="task-1",
                      audio_path=str(artifacts.video_dir("BV1234567890") / ".tmp/missing.m4a"))
    db.update_video(vid, status="subtitle_pending")
    attempts = 3 if retryable else 1
    for attempt in range(1, attempts + 1):
        service = ASRService(db=db, adapter=adapter, artifacts=artifacts, provider=provider)
        before = datetime.now(timezone.utc)
        assert not service.acquire(vid, trigger_mode=ASRTriggerMode.AUTOMATIC)
        row = db.get_asr_job(vid)
        assert row["attempt_count"] == attempt
        if attempt < attempts:
            assert row["status"] == "retry_wait"
            wait = (datetime.fromisoformat(row["next_retry_at"]) - before).total_seconds()
            assert (599 if attempt == 1 else 1799) <= wait <= (601 if attempt == 1 else 1801)
            assert not service.acquire(vid, trigger_mode=ASRTriggerMode.AUTOMATIC)
            assert provider.query_calls == attempt
            db.update_asr_job(vid, next_retry_at="2000-01-01T00:00:00+00:00")
    assert db.get_asr_job(vid)["status"] == "needs_review"
    # A due video with an old manual-origin job must not authorize an automatic reset.
    db.update_video(vid, status="subtitle_pending")
    for _ in range(2):
        PipelineService(db=db, adapter=adapter, artifacts=artifacts,
                        provider_factory=lambda: None, asr_service_factory=lambda: service).process_video(vid)
    assert db.get_asr_job(vid)["attempt_count"] == provider.query_calls == attempts
    assert db.get_asr_job(vid)["task_id"] == "task-1"
    assert adapter.calls == provider.upload_calls == provider.submit_calls == 0


def test_source_authentication_failure_does_not_retry(collection_db, app_paths):
    class Unauthorized(FakeAdapter):
        def fetch_video_bundle(self, bvid):
            self.calls += 1
            raise PipelineError("denied", code="authentication_required", retryable=False)

    adapter = Unauthorized(bundle())
    db, _, service, vid = make_pipeline(app_paths, adapter, FakeProvider(), collection_db)
    service.process_video(vid)
    service.process_video(vid)
    assert adapter.calls == 1
    assert db.get_stage(vid, StageName.SOURCE_FETCH)["status"] == "needs_review"
    assert db.get_stage(vid, StageName.SOURCE_FETCH)["attempt_count"] == 1


@pytest.mark.parametrize("state", ["UNKNOWN", "FAILED", "CANCELED"])
def test_asr_terminal_provider_response_stops_without_resubmit(
    collection_db, app_paths, monkeypatch, state
):
    from shiliu.asr import ParaformerProvider

    provider = ParaformerProvider(api_key="synthetic")
    db, adapter, artifacts, service, vid = make_service(app_paths, provider, collection_db)
    db.ensure_asr_job(vid, provider=provider.name, model=provider.model, trigger_mode="automatic")
    db.update_asr_job(vid, status="processing", task_id="existing-task")
    calls = []

    def query(method, url, **kwargs):
        assert method == "GET" and url.endswith("/tasks/existing-task")
        calls.append(url)
        return {"output": {"task_status": state}}

    monkeypatch.setattr(provider, "_json_request", query)
    assert not service.acquire(vid, trigger_mode=ASRTriggerMode.AUTOMATIC)
    assert not service.acquire(vid, trigger_mode=ASRTriggerMode.AUTOMATIC)
    row = db.get_asr_job(vid)
    assert row["status"] == "needs_review" and row["attempt_count"] == 1
    assert row["next_retry_at"] is None and row["task_id"] == "existing-task"
    assert len(calls) == 1 and adapter.calls == 0
