from __future__ import annotations

import sys

import numpy as np
import pytest

from shiliu.app import Application
from shiliu.artifacts import ArtifactStore
from shiliu.asr import ASRService
from shiliu.db import Database
from shiliu.domain import ASRTriggerMode, FavoriteItem, SubtitleSegment
from shiliu.library import LibraryService
from shiliu.pipeline import PipelineService
from shiliu.retrieval.coordinator import RetrievalIndexCoordinator
from shiliu.retrieval.dense import (
    DenseIndexNotReadyError,
    DenseIndexRebuildRequiredError,
    SQLiteExactDenseIndex,
)
from shiliu.retrieval.service import RetrievalService


class FakeEmbeddingProvider:
    model_id = "fake-deterministic-v1"
    dimension = 8

    def __init__(self) -> None:
        self.document_calls: list[list[str]] = []

    def embed_documents(self, texts):
        self.document_calls.append(list(texts))
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        return self._vector(text)

    def count_tokens(self, text, *, add_special_tokens=True):
        return sum(not value.isspace() for value in text) + (2 if add_special_tokens else 0)

    def truncate_text(self, text, max_content_tokens):
        kept, used = [], 0
        for value in text:
            if not value.isspace():
                if used >= max_content_tokens:
                    break
                used += 1
            kept.append(value)
        return "".join(kept).rstrip()

    def _vector(self, text):
        vector = np.zeros(self.dimension, dtype=np.float32)
        for index, value in enumerate(text.encode("utf-8")):
            vector[index % self.dimension] += value % 29 + 1
        vector[0] += 1
        return vector / np.linalg.norm(vector)


def lifecycle(app_paths):
    db = Database(app_paths.database)
    db.initialize()
    artifacts = ArtifactStore(app_paths.videos_dir)
    source_id = db.create_favorite_source(folder_id=301, folder_title="Lifecycle")
    db.record_source_snapshot(
        source_id,
        [FavoriteItem(bvid="BV3000000001", title="Lifecycle", uploader="UP", favorite_time=1)],
        processing_profile="formal",
    )
    video_id = int(db.get_video_by_source("BV3000000001")["id"])
    _, raw_path = artifacts.save_raw_subtitle(
        "BV3000000001",
        [SubtitleSegment.model_validate({"from": 0, "to": 3, "content": "first subtitle"})],
    )
    db.update_video(
        video_id, status="completed", raw_subtitle_path=str(raw_path),
        subtitle_source="human", subtitle_language="zh",
    )
    provider = FakeEmbeddingProvider()
    lexical = RetrievalService(db=db, artifacts=artifacts)
    dense = SQLiteExactDenseIndex(db=db, provider=provider)
    lexical.rebuild()
    dense.rebuild()
    coordinator = RetrievalIndexCoordinator(
        db=db, lexical=lexical, dense_factory=lambda: dense
    )
    coordinator.initialize_schema()
    return db, artifacts, source_id, video_id, provider, lexical, dense, coordinator


def assert_consistent(db: Database, dimension: int = 8) -> None:
    with db.connect() as connection:
        metadata = int(connection.execute("SELECT COUNT(*) FROM retrieval_units").fetchone()[0])
        fts = int(connection.execute("SELECT COUNT(*) FROM retrieval_units_fts").fetchone()[0])
        dense = int(connection.execute("SELECT COUNT(*) FROM retrieval_dense_vectors").fetchone()[0])
        duplicates = int(connection.execute(
            "SELECT COUNT(*)-COUNT(DISTINCT unit_id) FROM retrieval_units"
        ).fetchone()[0])
        damaged = int(connection.execute(
            "SELECT COUNT(*) FROM retrieval_dense_vectors WHERE length(embedding_blob) != ?",
            (dimension * 4,),
        ).fetchone()[0])
    assert metadata == fts == dense
    assert duplicates == damaged == 0


def test_coordinator_success_repeat_sync_and_structured_state(app_paths) -> None:
    db, _, _, video_id, provider, _, _, coordinator = lifecycle(app_paths)
    provider.document_calls.clear()
    first = coordinator.sync_video(video_id, trigger="test")
    second = coordinator.sync_video(video_id, trigger="test_repeat")
    assert first.success and second.success
    assert first.lexical_state == first.dense_state == "current"
    assert sum(map(len, provider.document_calls)) == 0
    assert coordinator.status()["groups"] == [
        {"desired_state": "indexed", "lexical_state": "current", "dense_state": "current", "count": 1}
    ]
    assert_consistent(db)


def test_lexical_failure_stops_dense_and_truncates_error(app_paths, monkeypatch) -> None:
    _, _, _, video_id, _, lexical, dense, coordinator = lifecycle(app_paths)
    dense_called = False

    def fail_lexical(_video_id):
        raise RuntimeError("x" * 900)

    def observe_dense(_video_id):
        nonlocal dense_called
        dense_called = True

    monkeypatch.setattr(lexical, "replace_video", fail_lexical)
    monkeypatch.setattr(dense, "replace_video", observe_dense)
    result = coordinator.sync_video(video_id, trigger="controlled_failure")
    assert not result.success and result.lexical_state == "error"
    assert result.dense_state == "stale" and not dense_called
    assert len(result.error_message or "") == 500


@pytest.mark.parametrize(
    ("error", "state"),
    [
        (DenseIndexNotReadyError("not ready"), "not_ready"),
        (DenseIndexRebuildRequiredError("rebuild"), "rebuild_required"),
        (RuntimeError("provider failed"), "error"),
    ],
)
def test_dense_failure_states_preserve_current_lexical(app_paths, monkeypatch, error, state) -> None:
    _, _, _, video_id, _, _, dense, coordinator = lifecycle(app_paths)
    monkeypatch.setattr(dense, "replace_video", lambda _video_id: (_ for _ in ()).throw(error))
    result = coordinator.sync_video(video_id, trigger="dense_failure")
    assert not result.success
    assert result.lexical_state == "current" and result.dense_state == state


def test_library_mutations_are_post_commit_and_reuse_unchanged_chunks(app_paths) -> None:
    db, _, _, video_id, provider, _, _, coordinator = lifecycle(app_paths)
    library = LibraryService(db, coordinator)
    provider.document_calls.clear()
    note = library.add_note(video_id, "new evidence note")
    library.update_note(int(note["id"]), "updated evidence note")
    library.set_reading_state(video_id, "read")
    library.set_marked(video_id, True)
    library.set_archived(video_id, True)
    library.set_ignored(video_id, True)
    library.delete_note(int(note["id"]))
    video = db.get_video(video_id)
    assert video["reading_state"] == "read" and video["is_marked"] == 1
    assert video["archived_at"] and video["is_ignored"] == 1
    embedded_batches = [batch for batch in provider.document_calls if batch]
    assert embedded_batches and all(len(batch) == 1 for batch in embedded_batches)
    assert_consistent(db)


def test_retrieval_failure_does_not_rollback_product_mutation(app_paths, monkeypatch) -> None:
    db, _, _, video_id, _, lexical, _, coordinator = lifecycle(app_paths)
    monkeypatch.setattr(
        lexical, "replace_video",
        lambda _video_id: (_ for _ in ()).throw(RuntimeError("controlled lexical failure")),
    )
    video = LibraryService(db, coordinator).set_marked(video_id, True)
    assert video["is_marked"] == 1
    state = coordinator.status()["failed"]
    assert state[0]["video_id"] == video_id
    assert state[0]["lexical_state"] == "error" and state[0]["dense_state"] == "stale"


def test_not_eligible_cleanup_and_reconcile_repairs_drift(app_paths) -> None:
    db, _, source_id, video_id, _, _, _, coordinator = lifecycle(app_paths)
    with db.connect() as connection:
        connection.execute("DELETE FROM retrieval_units_fts WHERE rowid IN (SELECT rowid FROM retrieval_units_fts LIMIT 1)")
        connection.execute("DELETE FROM retrieval_dense_vectors WHERE unit_id IN (SELECT unit_id FROM retrieval_units LIMIT 1)")
    repaired = coordinator.reconcile_all()
    assert repaired.failed == 0
    assert_consistent(db)
    db.record_source_snapshot(
        source_id, [], processing_profile="formal", authoritative=True
    )
    removed = coordinator.sync_video(video_id, trigger="membership_removed")
    assert removed.success and removed.desired_state == "absent"
    with db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM retrieval_units WHERE video_id=?", (video_id,)
        ).fetchone()[0] == 0
    assert_consistent(db)


def test_asr_completion_replaces_stale_chunks_through_real_mutation(app_paths) -> None:
    db, artifacts, _, video_id, _, _, _, coordinator = lifecycle(app_paths)

    class Provider:
        name = "fake-asr"
        model = "fake-asr-v1"

    service = ASRService(
        db=db, adapter=object(), artifacts=artifacts, provider=Provider(),
        index_coordinator=coordinator,
    )
    job = db.ensure_asr_job(
        video_id, provider="fake-asr", model="fake-asr-v1",
        trigger_mode=ASRTriggerMode.MANUAL.value,
    )
    video = db.get_video(video_id)
    with db.connect() as connection:
        old_chunks = {
            row[0] for row in connection.execute(
                "SELECT unit_id FROM retrieval_units WHERE video_id=? AND unit_type='transcript_chunk'",
                (video_id,),
            )
        }
    service._complete(
        video, job,
        {"transcripts": [{"sentences": [
            {"begin_time": 1000, "end_time": 4000, "text": "replacement ASR subtitle"}
        ]}]},
        "https://example.invalid/result",
    )
    with db.connect() as connection:
        new_chunks = {
            row[0] for row in connection.execute(
                "SELECT unit_id FROM retrieval_units WHERE video_id=? AND unit_type='transcript_chunk'",
                (video_id,),
            )
        }
    assert old_chunks and new_chunks and old_chunks.isdisjoint(new_chunks)
    assert db.get_video(video_id)["subtitle_source"] == "asr"
    assert_consistent(db)


def test_pipeline_completion_and_refinement_hooks_use_real_product_functions(app_paths) -> None:
    from tests.test_pipeline import bundle
    from tests.test_v1 import RefinementProvider

    class Adapter:
        def fetch_video_bundle(self, _bvid):
            return bundle()

    class Spy:
        def __init__(self):
            self.triggers = []

        def safe_sync_video(self, video_id, *, trigger):
            self.triggers.append((video_id, trigger))

    db = Database(app_paths.database)
    db.initialize()
    artifacts = ArtifactStore(app_paths.videos_dir)
    spy = Spy()
    pipeline = PipelineService(
        db=db, adapter=Adapter(), artifacts=artifacts,
        provider_factory=lambda role: RefinementProviderInstance,
        index_coordinator=spy,
    )
    RefinementProviderInstance = RefinementProvider()
    video_id = db.create_video("BV1234567890", "title", processing_profile="fast")
    assert pipeline.process_video(video_id) is True
    assert pipeline.process_refinement(video_id) is True
    triggers = [trigger for _, trigger in spy.triggers]
    assert "source_subtitle_fetched" in triggers
    assert "transcript_completed" in triggers
    assert "summary_completed" in triggers
    assert "refinement_completed" in triggers


def test_subtitle_only_completion_hook_uses_real_pipeline_function(app_paths) -> None:
    from tests.test_pipeline import bundle

    class Adapter:
        def fetch_video_bundle(self, _bvid):
            return bundle().model_copy(update={"duration_seconds": 1200})

    class Spy:
        def __init__(self):
            self.triggers = []

        def safe_sync_video(self, video_id, *, trigger):
            self.triggers.append((video_id, trigger))

    db = Database(app_paths.database)
    db.initialize()
    spy = Spy()
    pipeline = PipelineService(
        db=db, adapter=Adapter(), artifacts=ArtifactStore(app_paths.videos_dir),
        provider_factory=lambda role: (_ for _ in ()).throw(AssertionError(role)),
        index_coordinator=spy,
    )
    video_id = db.create_video("BV1234567890", "title")
    assert pipeline.process_video(video_id) is True
    assert db.get_video(video_id)["status"] == "completed"
    assert [trigger for _, trigger in spy.triggers] == [
        "source_subtitle_fetched", "subtitle_only_completed"
    ]


def test_cache_path_is_stable_overridable_and_application_is_model_lazy(app_paths, monkeypatch) -> None:
    monkeypatch.delenv("SHILIU_FASTEMBED_CACHE_DIR", raising=False)
    before = set(sys.modules)
    application = Application(app_paths)
    assert application.fastembed_cache_dir == app_paths.state_dir / "fastembed-cache"
    assert application._dense_retrieval is None
    assert "fastembed" not in set(sys.modules) - before
    lexical = application.retrieval.rebuild()
    assert lexical.eligible_video_count == 0
    assert application._dense_retrieval is None
    monkeypatch.setenv("SHILIU_FASTEMBED_CACHE_DIR", str(app_paths.state_dir / "override"))
    overridden = Application(app_paths)
    assert overridden.fastembed_cache_dir == app_paths.state_dir / "override"


def test_web_source_membership_add_pause_resume_remove_hooks(app_paths) -> None:
    from fastapi.testclient import TestClient
    from shiliu.domain import FavoriteSourcePreview
    from shiliu.web import create_web_app

    application = Application(app_paths)
    video_id = application.db.create_video("BV3000000099", "Existing")
    _, raw_path = application.artifacts.save_raw_subtitle(
        "BV3000000099",
        [SubtitleSegment.model_validate({"from": 0, "to": 2, "content": "membership"})],
    )
    application.db.update_video(
        video_id, status="completed", raw_subtitle_path=str(raw_path),
        subtitle_source="human", subtitle_language="zh",
    )
    provider = FakeEmbeddingProvider()
    application._dense_retrieval = SQLiteExactDenseIndex(
        db=application.db, provider=provider
    )
    application.retrieval.rebuild()
    application.dense_retrieval.rebuild()
    application.adapter.preview_favorite_url = lambda _url: FavoriteSourcePreview(
        account_id=1, account_name="Account", folder_id=999,
        folder_title="Lifecycle Folder", media_count=1,
    )
    application.adapter.list_favorite_scan = lambda _folder_id: {
        "items": [
            FavoriteItem(
                bvid="BV3000000099", title="Existing", uploader="UP", favorite_time=2
            )
        ],
        "remote_total": 1,
        "is_complete": True,
        "pages_fetched": 1,
        "raw_item_count": 1,
    }
    client = TestClient(create_web_app(application))
    added = client.post(
        "/api/sources", json={"url": "https://example.invalid/favorite", "history_policy": "future_only"}
    )
    assert added.status_code == 200
    source_id = int(added.json()["source_id"])
    with application.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM retrieval_units WHERE video_id=?", (video_id,)
        ).fetchone()[0] == 2
    assert client.post(f"/api/sources/{source_id}/pause").status_code == 200
    with application.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM retrieval_units WHERE video_id=?", (video_id,)
        ).fetchone()[0] == 0
    assert client.post(f"/api/sources/{source_id}/resume").status_code == 200
    assert client.post(f"/api/sources/{source_id}/remove").status_code == 200
    with application.db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM retrieval_units WHERE video_id=?", (video_id,)
        ).fetchone()[0] == 0
    assert_consistent(application.db)
