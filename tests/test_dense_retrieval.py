from __future__ import annotations

import sys
import sqlite3
from hashlib import sha256
from types import SimpleNamespace

import numpy as np
import pytest

from shiliu.artifacts import ArtifactStore
from shiliu.db import Database
from shiliu.domain import FavoriteItem, SubtitleSegment
from shiliu.retrieval import RetrievalFilters, RetrievalService
from shiliu.retrieval.dense import (
    DENSE_INDEX_VERSION,
    DenseIndexNotReadyError,
    DenseIndexRebuildRequiredError,
    MODEL_MAX_TOKENS,
    PROJECTION_VERSION,
    SQLiteExactDenseIndex,
    VIDEO_TOKEN_BUDGET,
    project_embedding_text,
    _validate_vector,
)
from shiliu.retrieval.hybrid import (
    FUSION_VERSION,
    HybridRetrievalService,
    _hybrid_sort_key,
)


class FakeEmbeddingProvider:
    model_id = "fake-deterministic-v1"
    dimension = 8

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.document_calls: list[list[str]] = []
        self.query_calls: list[str] = []

    def embed_documents(self, texts):
        self.document_calls.append(list(texts))
        if self.fail:
            raise RuntimeError("controlled provider failure")
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        self.query_calls.append(text)
        return self._vector(text)

    def count_tokens(self, text, *, add_special_tokens=True):
        content_tokens = sum(not character.isspace() for character in text)
        return content_tokens + (2 if add_special_tokens else 0)

    def truncate_text(self, text, max_content_tokens):
        used = 0
        output = []
        for character in text:
            if not character.isspace():
                if used >= max_content_tokens:
                    break
                used += 1
            output.append(character)
        return "".join(output).rstrip()

    def _vector(self, text):
        vector = np.zeros(self.dimension, dtype=np.float32)
        for index, value in enumerate(text.encode("utf-8")):
            vector[index % self.dimension] += (value % 29) + 1
        vector[0] += 1
        return vector / np.linalg.norm(vector)


def make_services(app_paths, provider=None):
    db = Database(app_paths.database)
    db.initialize()
    artifacts = ArtifactStore(app_paths.videos_dir)
    lexical = RetrievalService(db=db, artifacts=artifacts)
    return db, artifacts, lexical, SQLiteExactDenseIndex(
        db=db, provider=provider or FakeEmbeddingProvider()
    )


def add_video(db, artifacts, *, bvid, title, folder_id, uploader="Creator", ignored=False):
    source_id = db.create_favorite_source(
        folder_id=folder_id, folder_title=f"Folder {folder_id}", account_name="Account"
    )
    db.record_source_snapshot(
        source_id,
        [FavoriteItem(bvid=bvid, title=title, uploader=uploader, favorite_time=200)],
        processing_profile="formal",
    )
    video = db.get_video_by_source(bvid)
    video_id = int(video["id"])
    segments = [SubtitleSegment.model_validate({"from": 1, "to": 3, "content": title + " semantic detail"})]
    _, raw_path = artifacts.save_raw_subtitle(bvid, segments)
    db.update_video(
        video_id, title=title, uploader=uploader, description=title + " local description",
        status="completed", raw_subtitle_path=str(raw_path), subtitle_source="human",
    )
    if ignored:
        db.set_ignored(video_id, True)
    return source_id, video_id


def test_projection_is_token_bounded_prioritized_deterministic_and_chunks_are_direct():
    provider = FakeEmbeddingProvider()
    text = "\n\n".join(
        (
            "[Title]\n必须保留的标题",
            "[Summary Conclusion]\n核心结论",
            "[Summary Key Points]\n关键点" * 80,
            "[Summary Entities]\nMCP LangGraph RAG",
            "[Uploader]\nCreator",
            "[User Notes]\n用户笔记",
            "[Favorite Folders]\n技术收藏",
            "[Description]\n" + "很长描述" * 500,
            "[Summary Detailed Notes]\n" + "详细笔记" * 500,
            "[Cleaned Transcript (video-level only)]\n" + "转录内容" * 500,
        )
    )
    first = project_embedding_text("video", text, tokenizer=provider)
    assert first == project_embedding_text("video", text, tokenizer=provider)
    assert provider.count_tokens(first) <= VIDEO_TOKEN_BUDGET < MODEL_MAX_TOKENS
    assert first.startswith("T\n必须保留的标题")
    assert all(f"{label}\n" in first for label in "CKEUNFDSX")
    assert [first.index(f"{label}\n") for label in "TCKEUNFDSX"] == sorted(
        first.index(f"{label}\n") for label in "TCKEUNFDSX"
    )
    assert PROJECTION_VERSION == "v3-dense-projection-v2"
    assert project_embedding_text("transcript_chunk", "  exact chunk  ") == "exact chunk"


def test_projection_hash_ignores_excluded_tail_but_changes_for_included_content(app_paths):
    provider = FakeEmbeddingProvider()
    prefix = "[Title]\n标题\n\n[Summary Detailed Notes]\n" + "细节" * 200
    first_text = prefix + "尾部甲"
    second_text = prefix + "尾部乙"
    first_projection = project_embedding_text("video", first_text, tokenizer=provider)
    second_projection = project_embedding_text("video", second_text, tokenizer=provider)
    assert first_projection == second_projection
    assert sha256(first_projection.encode()).hexdigest() == sha256(second_projection.encode()).hexdigest()
    included_change = project_embedding_text(
        "video", first_text.replace("[Title]\n标题", "[Title]\n新标题"), tokenizer=provider
    )
    assert included_change != first_projection

    db, artifacts, lexical, dense = make_services(app_paths, provider)
    add_video(db, artifacts, bvid="BV1000000011", title="Tail Reuse", folder_id=111)
    lexical.rebuild()
    with db.connect() as connection:
        unit_id = connection.execute(
            "SELECT unit_id FROM retrieval_units WHERE unit_type='video'"
        ).fetchone()[0]
        connection.execute(
            "UPDATE retrieval_units SET search_text=?, content_hash='source-a' WHERE unit_id=?",
            (first_text, unit_id),
        )
    dense.rebuild()
    with db.connect() as connection:
        original_blob = bytes(connection.execute(
            "SELECT embedding_blob FROM retrieval_dense_vectors WHERE unit_id=?", (unit_id,)
        ).fetchone()[0])
        connection.execute(
            "UPDATE retrieval_units SET search_text=?, content_hash='source-b' WHERE unit_id=?",
            (second_text, unit_id),
        )
    tail_change = dense.rebuild()
    assert tail_change.embedded_count == 0 and tail_change.reused_count == 2
    with db.connect() as connection:
        row = connection.execute(
            "SELECT embedding_blob, source_content_hash FROM retrieval_dense_vectors WHERE unit_id=?",
            (unit_id,),
        ).fetchone()
    assert bytes(row["embedding_blob"]) == original_blob
    assert row["source_content_hash"] == "source-b"

    with db.connect() as connection:
        connection.execute(
            "UPDATE retrieval_units SET search_text=?, content_hash='source-c' WHERE unit_id=?",
            (first_text.replace("[Title]\n标题", "[Title]\n新标题"), unit_id),
        )
    included = dense.rebuild()
    assert included.embedded_count == 1 and included.reused_count == 1


def test_rebuild_persists_normalized_float32_and_second_build_reuses_all(app_paths):
    provider = FakeEmbeddingProvider()
    db, artifacts, lexical, dense = make_services(app_paths, provider)
    add_video(db, artifacts, bvid="BV1000000001", title="Alpha Vector", folder_id=101)
    lexical.rebuild()

    first = dense.rebuild(batch_size=1)
    second = dense.rebuild(batch_size=1)
    assert first.total_unit_count == first.embedded_count == 2
    assert second.embedded_count == 0
    assert second.reused_count == 2
    with db.connect() as connection:
        rows = connection.execute("SELECT * FROM retrieval_dense_vectors ORDER BY unit_id").fetchall()
    assert len(rows) == 2
    assert all(row["embedding_dtype"] == "float32" for row in rows)
    assert all(len(row["embedding_blob"]) == provider.dimension * 4 for row in rows)
    assert all(np.isclose(np.linalg.norm(np.frombuffer(row["embedding_blob"], dtype="<f4")), 1.0) for row in rows)
    with pytest.raises(ValueError, match="non-zero"):
        _validate_vector(np.zeros(provider.dimension), provider.dimension)
    with pytest.raises(ValueError, match="finite"):
        _validate_vector(np.full(provider.dimension, np.nan), provider.dimension)
    with pytest.raises(ValueError, match="dimension mismatch"):
        _validate_vector(np.ones(provider.dimension - 1), provider.dimension)


def test_changed_missing_and_stale_units_are_reconciled_and_failure_preserves_old(app_paths):
    provider = FakeEmbeddingProvider()
    db, artifacts, lexical, dense = make_services(app_paths, provider)
    _, video_id = add_video(db, artifacts, bvid="BV1000000002", title="Before Change", folder_id=102)
    lexical.rebuild()
    dense.rebuild()
    with db.connect() as connection:
        old = {row["unit_id"]: bytes(row["embedding_blob"]) for row in connection.execute("SELECT * FROM retrieval_dense_vectors")}
        unit_id = next(iter(old))
        connection.execute("UPDATE retrieval_units SET search_text='changed', content_hash='changed' WHERE unit_id=?", (unit_id,))
    changed = dense.rebuild()
    assert changed.embedded_count == 1 and changed.reused_count == 1
    with db.connect() as connection:
        connection.execute("DELETE FROM retrieval_units WHERE video_id=?", (video_id,))
    raw = sqlite3.connect(db.path)
    raw.execute(
        "INSERT INTO retrieval_dense_vectors VALUES(?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)",
        ("orphan", provider.model_id, provider.dimension, "float32", np.ones(provider.dimension, dtype="<f4").tobytes(), "x", "x", "v3-dense-projection-v1", DENSE_INDEX_VERSION, "now", "now"),
    )
    raw.commit()
    raw.close()
    stale = dense.rebuild()
    assert stale.stale_deleted_count == 1

    # Recreate an old valid index, then prove provider failure cannot partially replace it.
    add_video(db, artifacts, bvid="BV1000000003", title="Failure Safe", folder_id=103)
    lexical.rebuild()
    dense.rebuild()
    with db.connect() as connection:
        before = [(row[0], bytes(row[1])) for row in connection.execute("SELECT unit_id, embedding_blob FROM retrieval_dense_vectors ORDER BY unit_id")]
        connection.execute("UPDATE retrieval_units SET search_text=search_text || ' changed', content_hash='force' WHERE unit_type='video'")
    provider.fail = True
    with pytest.raises(RuntimeError, match="controlled provider failure"):
        dense.rebuild()
    with db.connect() as connection:
        after = [(row[0], bytes(row[1])) for row in connection.execute("SELECT unit_id, embedding_blob FROM retrieval_dense_vectors ORDER BY unit_id")]
    assert after == before


def test_dense_search_filters_provenance_errors_and_corrupt_skip(app_paths):
    provider = FakeEmbeddingProvider()
    db, artifacts, lexical, dense = make_services(app_paths, provider)
    source, first_id = add_video(db, artifacts, bvid="BV1000000004", title="Semantic Apple", folder_id=104, uploader="Alice Studio")
    _, ignored_id = add_video(db, artifacts, bvid="BV1000000005", title="Semantic Pear", folder_id=105, ignored=True)
    lexical.rebuild()
    with pytest.raises(DenseIndexNotReadyError, match="not ready"):
        dense.search("Semantic")
    dense.rebuild()
    results = dense.search("Semantic Apple", level="video", filters=RetrievalFilters(source_db_id=source, folder_id=104, uploader_contains="LiCe ST"))
    assert [item.video_id for item in results] == [first_id]
    assert results[0].model_id == provider.model_id
    assert results[0].dense_index_version == DENSE_INDEX_VERSION
    assert results[0].folders[0].folder_id == 104
    assert ignored_id not in {item.video_id for item in dense.search("Semantic", level="video")}
    assert ignored_id in {item.video_id for item in dense.search("Semantic", level="video", include_ignored=True)}
    db.set_reading_state(first_id, "read")
    db.set_marked(first_id, True)
    db.set_archived(first_id, True)
    lexical.replace_video(first_id)
    dense.replace_video(first_id)
    all_filters = RetrievalFilters(
        source_db_id=source,
        folder_id=104,
        favorite_time_from=200,
        favorite_time_to=200,
        reading_state="read",
        is_marked=True,
        uploader_contains="LiCe ST",
        archived=True,
    )
    filtered = dense.search("Semantic Apple", filters=all_filters)
    assert filtered and {item.video_id for item in filtered} == {first_id}
    chunk_results = dense.search("Semantic Apple", level="transcript_chunk", top_k=1, filters=all_filters)
    assert len(chunk_results) == 1 and chunk_results[0].start_time == 1
    all_results = dense.search("Semantic Apple", level="all", top_k=2, filters=all_filters)
    assert len(all_results) == 2
    assert [item.dense_score for item in all_results] == sorted(
        [item.dense_score for item in all_results], reverse=True
    )
    with db.connect() as connection:
        corrupt_id = connection.execute("SELECT unit_id FROM retrieval_dense_vectors ORDER BY unit_id LIMIT 1").fetchone()[0]
        connection.execute("UPDATE retrieval_dense_vectors SET embedding_blob=x'00' WHERE unit_id=?", (corrupt_id,))
    assert corrupt_id not in {item.unit_id for item in dense.search("Semantic", include_ignored=True)}
    with db.connect() as connection:
        connection.execute("UPDATE retrieval_dense_index_meta SET model_id='wrong'")
    with pytest.raises(DenseIndexRebuildRequiredError, match="rebuild required"):
        dense.search("Semantic")


def test_missing_vector_and_unit_count_mismatch_requires_rebuild(app_paths):
    db, artifacts, lexical, dense = make_services(app_paths)
    add_video(db, artifacts, bvid="BV1000000009", title="Count Guard", folder_id=109)
    lexical.rebuild()
    dense.rebuild()
    with db.connect() as connection:
        connection.execute(
            "DELETE FROM retrieval_dense_vectors WHERE unit_id=(SELECT unit_id FROM retrieval_dense_vectors LIMIT 1)"
        )
    with pytest.raises(DenseIndexRebuildRequiredError, match="rebuild required"):
        dense.search("Count Guard")


def test_rrf_uses_component_ranks_and_stable_tie_break(app_paths):
    db, artifacts, lexical, dense = make_services(app_paths)
    add_video(db, artifacts, bvid="BV1000000006", title="RRF Alpha", folder_id=106)
    add_video(db, artifacts, bvid="BV1000000007", title="RRF Alpha Beta", folder_id=107)
    lexical.rebuild()
    dense.rebuild()
    hybrid = HybridRetrievalService(lexical=lexical, dense=dense)
    results = hybrid.search("RRF Alpha", level="video", top_k=2)
    assert results
    assert all(item.fusion_version == FUSION_VERSION for item in results)
    assert all(item.retrieval_method == "hybrid" for item in results)
    assert all(item.lexical_index_version == "v3-stage1-lexical-v1" for item in results)
    assert all(item.rrf_score == pytest.approx(1 / (60 + item.lexical_rank) + 1 / (60 + item.dense_rank)) for item in results)
    assert results == sorted(results, key=_hybrid_sort_key)
    fallback = hybrid.search("RR", level="video", top_k=2)
    assert fallback
    assert any(item.lexical_retrieval_method == "lexical_substring_fallback" for item in fallback)

    tied = [
        SimpleNamespace(rrf_score=float(8 / 315), lexical_rank=10, dense_rank=30, unit_id="b"),
        SimpleNamespace(rrf_score=float(8 / 315), lexical_rank=3, dense_rank=45, unit_id="a"),
    ]
    tied.sort(key=_hybrid_sort_key)
    assert [(item.lexical_rank, item.dense_rank) for item in tied] == [(3, 45), (10, 30)]


def test_hybrid_fails_when_dense_is_not_ready(app_paths):
    db, artifacts, lexical, dense = make_services(app_paths)
    add_video(db, artifacts, bvid="BV1000000010", title="No Dense", folder_id=110)
    lexical.rebuild()
    hybrid = HybridRetrievalService(lexical=lexical, dense=dense)
    with pytest.raises(DenseIndexNotReadyError, match="not ready"):
        hybrid.search("No Dense")


def test_dense_replace_delete_and_fastembed_is_lazy(app_paths):
    db, artifacts, lexical, dense = make_services(app_paths)
    _, video_id = add_video(db, artifacts, bvid="BV1000000008", title="Primitive", folder_id=108)
    lexical.rebuild()
    dense.rebuild()
    assert dense.replace_video(video_id).reused_count == 2
    assert dense.delete_video(video_id) == 2
    assert dense.statistics()["index"]["total_unit_count"] == 0

    sys.modules.pop("fastembed", None)
    from shiliu.retrieval.dense import FastEmbedEmbeddingProvider

    FastEmbedEmbeddingProvider()
    assert "fastembed" not in sys.modules
