from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import numpy as np
import pytest

from research.v3_model_selection.harness import (
    CandidateSpec,
    ExperimentalDenseIndex,
    OfflineModelError,
    OUTPUT_DIMENSION,
    QUERY_INSTRUCTION,
    QwenLocalEmbeddingProvider,
    _validated,
    format_download_checkpoint,
    format_qwen_query,
    formal_dense_fingerprint,
    parse_gate_state,
    validate_phase_transition,
    verify_local_snapshot,
)


class FakeCandidateProvider:
    model_id = "fake/candidate"
    revision = "abc123"
    dimension = OUTPUT_DIMENSION
    query_instruction = QUERY_INSTRUCTION

    def embed_documents(self, texts):
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        return self._vector(format_qwen_query(text))

    def count_tokens(self, text, *, add_special_tokens=True):
        return len(text) + int(add_special_tokens) * 2

    def truncate_text(self, text, max_content_tokens):
        return text[:max_content_tokens]

    def _vector(self, text):
        vector = np.zeros(self.dimension, dtype=np.float32)
        for index, value in enumerate(text.encode("utf-8")):
            vector[index % self.dimension] += value % 31 + 1
        vector[0] += 1
        return vector / np.linalg.norm(vector)


def make_formal_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE retrieval_units (
            unit_id TEXT PRIMARY KEY, unit_type TEXT NOT NULL, video_id INTEGER NOT NULL,
            chunk_id TEXT, start_time REAL, end_time REAL, source_type TEXT NOT NULL,
            content_hash TEXT NOT NULL, search_text TEXT NOT NULL
        );
        CREATE TABLE retrieval_dense_vectors (
            unit_id TEXT PRIMARY KEY, embedding_blob BLOB NOT NULL
        );
        CREATE TABLE retrieval_dense_index_meta (
            index_name TEXT PRIMARY KEY, model_id TEXT NOT NULL
        );
        INSERT INTO retrieval_units VALUES
          ('video:bilibili:BV1:p1','video',1,NULL,NULL,NULL,'video','vh','[Title]\nAgent workflow'),
          ('chunk:bilibili:BV1:p1:c1','transcript_chunk',1,'c1',1.25,4.5,'human','ch','MCP protocol evidence');
        INSERT INTO retrieval_dense_vectors VALUES('formal-vector', X'01020304');
        INSERT INTO retrieval_dense_index_meta VALUES('shiliu_dense','BAAI/bge-small-zh-v1.5');
        """
    )
    connection.commit()
    connection.close()


def test_gate_state_parse_and_transitions(tmp_path: Path) -> None:
    state = tmp_path / "state.md"
    state.write_text(
        "# State\n```text\ngate_version: v1\ncurrent_phase: PREPARING\n```\n",
        encoding="utf-8",
    )
    assert parse_gate_state(state)["current_phase"] == "PREPARING"
    validate_phase_transition("PREPARING", "AWAITING_QWEN_DOWNLOAD")
    with pytest.raises(ValueError, match="invalid Gate transition"):
        validate_phase_transition("PREPARING", "QWEN_EVALUATED")


def test_download_checkpoint_has_required_manual_stop_fields(tmp_path: Path) -> None:
    result = format_download_checkpoint(
        revision="a" * 40, dry_run_command="hf download --dry-run",
        download_command="hf download --local-dir /tmp/model", target=tmp_path / "model",
        expected="12 files, 1.2 GiB", free_disk="500 GiB",
        verification_command="HF_HUB_OFFLINE=1 python verify.py",
    )
    assert result.startswith("=== MODEL DOWNLOAD CHECKPOINT ===")
    assert "Qwen/Qwen3-Embedding-0.6B" in result
    assert "AWAITING_QWEN_DOWNLOAD" in result
    assert "Qwen3 模型下载完成，继续" in result


def test_offline_verification_rejects_missing_or_wrong_revision(tmp_path: Path) -> None:
    with pytest.raises(OfflineModelError, match="does not exist"):
        verify_local_snapshot(tmp_path / "missing", "abc")
    model = tmp_path / "model"
    model.mkdir()
    (model / "config.json").write_text("{}")
    (model / "tokenizer.json").write_text("{}")
    (model / "model.safetensors").write_bytes(b"weights")
    (model / ".candidate-revision").write_text("wrong")
    with pytest.raises(OfflineModelError, match="MODEL DOWNLOAD INCOMPLETE"):
        verify_local_snapshot(model, "expected")


def test_qwen_provider_requires_absolute_local_path_and_does_not_load(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute"):
        QwenLocalEmbeddingProvider(
            CandidateSpec("Qwen/Qwen3-Embedding-0.6B", "abc", Path("relative"))
        )
    provider = QwenLocalEmbeddingProvider(
        CandidateSpec("Qwen/Qwen3-Embedding-0.6B", "abc", tmp_path / "missing")
    )
    assert provider._model is None
    with pytest.raises(OfflineModelError, match="does not exist"):
        provider.embed_query("MCP")


def test_output_dimension_normalization_and_non_finite_rejection() -> None:
    vector = _validated(np.ones(OUTPUT_DIMENSION), OUTPUT_DIMENSION)
    assert vector.shape == (512,)
    assert np.isclose(np.linalg.norm(vector), 1.0)
    with pytest.raises(ValueError, match="dimension mismatch"):
        _validated(np.ones(511), OUTPUT_DIMENSION)
    with pytest.raises(ValueError, match="non-finite"):
        _validated(np.full(OUTPUT_DIMENSION, np.nan), OUTPUT_DIMENSION)


def test_query_instruction_is_fixed_and_normalizes_only_whitespace() -> None:
    first = format_qwen_query("  MCP   协议 ")
    second = format_qwen_query("MCP 协议")
    assert first == second
    assert first == f"Instruct: {QUERY_INSTRUCTION}\nQuery: MCP 协议"
    with pytest.raises(ValueError, match="empty"):
        format_qwen_query("   ")


def test_experimental_index_preserves_identity_provenance_and_isolation(tmp_path: Path) -> None:
    formal = tmp_path / "formal.db"
    experiment = tmp_path / "candidate.db"
    make_formal_database(formal)
    before = formal_dense_fingerprint(formal)
    index = ExperimentalDenseIndex(
        formal_database=formal, experimental_database=experiment,
        provider=FakeCandidateProvider(),
    )
    stats = index.build(batch_size=1)
    after = formal_dense_fingerprint(formal)
    assert before == after
    assert stats.total_units == stats.successful_vectors == 2
    assert stats.video_units == stats.chunk_units == 1
    assert stats.failed_vectors == stats.duplicate_count == stats.damaged_vector_count == 0
    with sqlite3.connect(experiment) as connection:
        rows = connection.execute(
            "SELECT unit_id,chunk_id,start_time,end_time,source_type FROM candidate_units ORDER BY unit_id"
        ).fetchall()
        formal_tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'retrieval_dense_%'"
        ).fetchall()
    assert rows == [
        ("chunk:bilibili:BV1:p1:c1", "c1", 1.25, 4.5, "human"),
        ("video:bilibili:BV1:p1", None, None, None, "video"),
    ]
    assert formal_tables == []
    assert index.search("MCP", top_k=2)[0]["unit_id"] in {row[0] for row in rows}


def test_experimental_database_cannot_equal_formal_database(tmp_path: Path) -> None:
    formal = tmp_path / "formal.db"
    make_formal_database(formal)
    with pytest.raises(ValueError, match="must differ"):
        ExperimentalDenseIndex(
            formal_database=formal, experimental_database=formal,
            provider=FakeCandidateProvider(),
        )


def test_baseline_evidence_is_frozen_and_non_sensitive() -> None:
    path = Path("research/v3_model_selection/baseline_evidence.json")
    evidence = json.loads(path.read_text(encoding="utf-8"))
    assert evidence["model_id"] == "BAAI/bge-small-zh-v1.5"
    assert evidence["formal_units"] == {"video": 142, "transcript_chunk": 1405, "total": 1547}
    assert evidence["ascii_collapse"]["all_pairwise_exactly_identical"] is True
    assert "embedding_blob" not in path.read_text(encoding="utf-8")
