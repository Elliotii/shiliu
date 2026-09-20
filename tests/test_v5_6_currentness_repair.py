from __future__ import annotations

import json

import numpy as np
import pytest

from shiliu.app import Application
from shiliu.ask.evidence import TranscriptEvidenceMaterializer
from shiliu.cli import main
from shiliu.domain import FavoriteItem, SubtitleSegment
from shiliu.evidence import (
    EvidenceContractError,
    EvidenceSearchService,
    SourceArtifactReference,
    bind_live_current_version,
)
from shiliu.retrieval.coordinator import ReconcileResult
from shiliu.retrieval.dense import SQLiteExactDenseIndex
from shiliu.retrieval.product_search import ProductSearchRequest


class _DeterministicEmbeddingProvider:
    model_id = "v5.6-currentness-repair-fake"
    dimension = 8

    def embed_documents(self, texts):
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        return self._vector(text)

    def count_tokens(self, text, *, add_special_tokens=True):
        return sum(not value.isspace() for value in text) + (
            2 if add_special_tokens else 0
        )

    def truncate_text(self, text, max_content_tokens):
        kept: list[str] = []
        used = 0
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


def _currentness_fixture(app_paths):
    app = Application(app_paths)
    source_id = app.db.create_favorite_source(
        folder_id=5601, folder_title="Currentness Repair"
    )
    app.db.record_source_snapshot(
        source_id,
        [
            FavoriteItem(
                bvid="BV5600000001",
                title="Currentness Recovery",
                uploader="Local Fixture",
                favorite_time=1,
            )
        ],
        processing_profile="formal",
    )
    video_id = int(app.db.get_video_by_source("BV5600000001")["id"])
    _, raw_path = app.artifacts.save_raw_subtitle(
        "BV5600000001",
        [
            SubtitleSegment.model_validate(
                {
                    "from": 0,
                    "to": 4,
                    "content": "dense rebuild recovery restores current evidence",
                }
            )
        ],
    )
    app.db.update_video(
        video_id,
        status="completed",
        raw_subtitle_path=str(raw_path),
        subtitle_source="human",
        subtitle_language="en",
    )
    app._dense_retrieval = SQLiteExactDenseIndex(
        db=app.db, provider=_DeterministicEmbeddingProvider()
    )
    app.retrieval.rebuild()
    initial = app.retrieval_coordinator.sync_video(
        video_id, trigger="currentness_repair_fixture"
    )
    assert not initial.success
    assert initial.lexical_state == "current"
    assert initial.dense_state == "not_ready"
    reference = SourceArtifactReference(
        platform="bilibili",
        source_id="BV5600000001",
        part=1,
        source_type="human",
        source_language="en",
        artifact_path=str(raw_path),
    )
    return app, video_id, reference


def _assert_dense_replay_not_ready(app, video_id, reference) -> None:
    with pytest.raises(EvidenceContractError) as error:
        bind_live_current_version(
            reference,
            db=app.db,
            video_id=video_id,
            require_dense_current=True,
        )
    assert error.value.code == "index_not_ready"


def test_dense_rebuild_reconciles_and_restores_current_evidence_and_citation(
    app_paths, monkeypatch, capsys
) -> None:
    app, video_id, reference = _currentness_fixture(app_paths)
    _assert_dense_replay_not_ready(app, video_id, reference)
    monkeypatch.setattr("shiliu.cli.Application", lambda: app)

    assert main(["retrieval", "dense-rebuild"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["total_unit_count"] == 2
    assert payload["video_unit_count"] == 1
    assert payload["chunk_unit_count"] == 1
    assert payload["dense_index_version"]
    assert payload["reconciliation"] == {
        "attempted": 1,
        "succeeded": 1,
        "failed": 0,
        "desired_indexed": 1,
        "desired_absent": 0,
        "embedded": 0,
        "reused": 2,
        "removed": 0,
        "lexical_failures": 0,
        "dense_failures": 0,
        "dense_not_ready": 0,
        "dense_rebuild_required": 0,
    }
    assert app.retrieval_coordinator.status()["groups"] == [
        {
            "desired_state": "indexed",
            "lexical_state": "current",
            "dense_state": "current",
            "count": 1,
        }
    ]

    evidence = EvidenceSearchService(
        db=app.db,
        product_search=app.product_search,
        authority_mode="live_current_exact_replay",
    )
    execution = evidence.execute_search(
        ProductSearchRequest(
            query="dense rebuild recovery",
            mode="hybrid",
            scope="transcript_chunk",
            result_limit=5,
        )
    )
    candidates = evidence.materialize_execution(execution)
    materialized = TranscriptEvidenceMaterializer(app.db).materialize(
        execution, candidates, query_index=0
    )
    assert materialized.stale_reasons == ()
    assert len(materialized.spans) == 1
    span = materialized.spans[0]
    TranscriptEvidenceMaterializer(app.db).validate_current(span)
    citation = span.as_citation()
    assert citation.video_id == video_id
    assert "recovery restores current evidence" in citation.quote_text


def test_dense_rebuild_reports_reconciliation_failure_and_stays_fail_closed(
    app_paths, monkeypatch, capsys
) -> None:
    app, video_id, reference = _currentness_fixture(app_paths)
    _assert_dense_replay_not_ready(app, video_id, reference)
    calls: list[str] = []

    def controlled_failure(*, trigger):
        calls.append(trigger)
        return ReconcileResult(
            attempted=1,
            failed=1,
            desired_indexed=1,
            dense_failures=1,
            dense_not_ready=1,
        )

    monkeypatch.setattr(app.retrieval_coordinator, "reconcile_all", controlled_failure)
    monkeypatch.setattr("shiliu.cli.Application", lambda: app)

    assert main(["retrieval", "dense-rebuild"]) == 1
    payload = json.loads(capsys.readouterr().out)

    assert calls == ["cli_dense_rebuild"]
    assert payload["total_unit_count"] == 2
    assert payload["dense_index_version"]
    assert payload["reconciliation"]["failed"] == 1
    assert payload["reconciliation"]["dense_not_ready"] == 1
    _assert_dense_replay_not_ready(app, video_id, reference)
