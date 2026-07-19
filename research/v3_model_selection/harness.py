from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Iterable, Protocol, Sequence

import numpy as np

from shiliu.retrieval.dense import project_embedding_text


GATE_VERSION = "v3-model-selection-gate-v1"
QUERY_INSTRUCTION = (
    "Given a Chinese or English AI and software engineering knowledge retrieval "
    "query, retrieve the most relevant evidence passages."
)
OUTPUT_DIMENSION = 512
MAX_INPUT_TOKENS = 512
EXPERIMENT_VERSION = "v3-model-selection-qwen-v1"
ALLOWED_PHASES = {
    "PREPARING",
    "AWAITING_QWEN_DOWNLOAD",
    "QWEN_DOWNLOADED",
    "QWEN_SMOKE_COMPLETE",
    "QWEN_EVALUATED",
    "AWAITING_E5_DOWNLOAD",
    "E5_DOWNLOADED",
    "E5_EVALUATED",
    "GATE_COMPLETE",
    "BLOCKED",
}
ALLOWED_TRANSITIONS = {
    "PREPARING": {"AWAITING_QWEN_DOWNLOAD", "QWEN_DOWNLOADED", "BLOCKED"},
    "AWAITING_QWEN_DOWNLOAD": {"QWEN_DOWNLOADED", "BLOCKED"},
    "QWEN_DOWNLOADED": {"QWEN_SMOKE_COMPLETE", "AWAITING_QWEN_DOWNLOAD", "BLOCKED"},
    "QWEN_SMOKE_COMPLETE": {"QWEN_EVALUATED", "AWAITING_E5_DOWNLOAD", "BLOCKED"},
    "QWEN_EVALUATED": {"GATE_COMPLETE", "BLOCKED"},
    "AWAITING_E5_DOWNLOAD": {"E5_DOWNLOADED", "BLOCKED"},
    "E5_DOWNLOADED": {"E5_EVALUATED", "AWAITING_E5_DOWNLOAD", "BLOCKED"},
    "E5_EVALUATED": {"GATE_COMPLETE", "BLOCKED"},
    "GATE_COMPLETE": set(),
    "BLOCKED": {"PREPARING", "AWAITING_QWEN_DOWNLOAD", "AWAITING_E5_DOWNLOAD"},
}


@dataclass(frozen=True)
class CandidateSpec:
    model_id: str
    revision: str
    local_path: Path
    output_dimension: int = OUTPUT_DIMENSION
    query_instruction: str = QUERY_INSTRUCTION
    maximum_input_tokens: int = MAX_INPUT_TOKENS


@dataclass
class ExperimentalBuildStats:
    total_units: int = 0
    video_units: int = 0
    chunk_units: int = 0
    successful_vectors: int = 0
    failed_vectors: int = 0
    duplicate_count: int = 0
    damaged_vector_count: int = 0
    build_duration_seconds: float = 0.0

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["build_duration_seconds"] = round(self.build_duration_seconds, 6)
        return result


class CandidateProvider(Protocol):
    model_id: str
    revision: str
    dimension: int
    query_instruction: str

    def embed_documents(self, texts: Sequence[str]) -> list[np.ndarray]: ...
    def embed_query(self, text: str) -> np.ndarray: ...
    def count_tokens(self, text: str, *, add_special_tokens: bool = True) -> int: ...
    def truncate_text(self, text: str, max_content_tokens: int) -> str: ...


class OfflineModelError(RuntimeError):
    pass


class QwenLocalEmbeddingProvider:
    """Qwen adapter that accepts only an explicit local directory in offline mode."""

    def __init__(self, spec: CandidateSpec) -> None:
        if spec.model_id != "Qwen/Qwen3-Embedding-0.6B":
            raise ValueError("unsupported candidate model")
        if not spec.local_path.is_absolute():
            raise ValueError("candidate model path must be absolute")
        self.spec = spec
        self.model_id = spec.model_id
        self.revision = spec.revision
        self.dimension = spec.output_dimension
        self.query_instruction = spec.query_instruction
        self._model = None

    def _load(self):
        if self._model is None:
            verify_local_snapshot(self.spec.local_path, self.spec.revision)
            if os.environ.get("HF_HUB_OFFLINE") != "1" or os.environ.get(
                "TRANSFORMERS_OFFLINE"
            ) != "1":
                raise OfflineModelError("offline environment variables must both equal 1")
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                str(self.spec.local_path),
                local_files_only=True,
                truncate_dim=self.dimension,
                processor_kwargs={"padding_side": "left"},
                device="mps" if _mps_available() else "cpu",
            )
            self._model.max_seq_length = self.spec.maximum_input_tokens
        return self._model

    def embed_documents(self, texts: Sequence[str]) -> list[np.ndarray]:
        if not texts:
            return []
        values = self._load().encode(
            list(texts),
            normalize_embeddings=True,
            truncate_dim=self.dimension,
            batch_size=8,
            show_progress_bar=False,
        )
        return [_validated(value, self.dimension) for value in values]

    def embed_query(self, text: str) -> np.ndarray:
        formatted = format_qwen_query(text, self.query_instruction)
        value = self._load().encode(
            [formatted],
            normalize_embeddings=True,
            truncate_dim=self.dimension,
            show_progress_bar=False,
        )[0]
        return _validated(value, self.dimension)

    def count_tokens(self, text: str, *, add_special_tokens: bool = True) -> int:
        return len(self._load().tokenizer.encode(text, add_special_tokens=add_special_tokens))

    def truncate_text(self, text: str, max_content_tokens: int) -> str:
        tokenizer = self._load().tokenizer
        token_ids = tokenizer.encode(text, add_special_tokens=False)[:max_content_tokens]
        return tokenizer.decode(token_ids, skip_special_tokens=True).rstrip()


class ExperimentalDenseIndex:
    """Candidate vectors isolated from the formal Shiliu Dense tables."""

    def __init__(
        self,
        *,
        formal_database: Path,
        experimental_database: Path,
        provider: CandidateProvider,
    ) -> None:
        if formal_database.resolve() == experimental_database.resolve():
            raise ValueError("experimental database must differ from formal database")
        self.formal_database = formal_database
        self.experimental_database = experimental_database
        self.provider = provider

    def initialize_schema(self) -> None:
        self.experimental_database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.experimental_database) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS candidate_units (
                    unit_id TEXT PRIMARY KEY,
                    unit_type TEXT NOT NULL,
                    video_id INTEGER NOT NULL,
                    chunk_id TEXT,
                    start_time REAL,
                    end_time REAL,
                    source_type TEXT NOT NULL,
                    source_content_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS candidate_vectors (
                    unit_id TEXT PRIMARY KEY REFERENCES candidate_units(unit_id) ON DELETE CASCADE,
                    embedding_blob BLOB NOT NULL,
                    embedding_dimension INTEGER NOT NULL,
                    normalized INTEGER NOT NULL,
                    model_id TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    query_instruction TEXT NOT NULL,
                    experiment_version TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS candidate_meta (
                    experiment_version TEXT PRIMARY KEY,
                    model_id TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    dimension INTEGER NOT NULL,
                    query_instruction TEXT NOT NULL,
                    total_units INTEGER NOT NULL,
                    built_at TEXT NOT NULL
                );
                """
            )

    def build(self, *, batch_size: int = 8) -> ExperimentalBuildStats:
        self.initialize_schema()
        started = time.monotonic()
        with self._formal_read_only() as source:
            rows = source.execute(
                """
                SELECT unit_id, unit_type, video_id, chunk_id, start_time, end_time,
                       source_type, content_hash, search_text
                FROM retrieval_units ORDER BY unit_id
                """
            ).fetchall()
        prepared: list[tuple[sqlite3.Row, str]] = []
        for row in rows:
            text = project_embedding_text(
                str(row["unit_type"]),
                str(row["search_text"]),
                tokenizer=self.provider if str(row["unit_type"]) == "video" else None,
            )
            prepared.append((row, text))

        vectors: dict[str, np.ndarray] = {}
        failed = 0
        for offset in range(0, len(prepared), batch_size):
            batch = prepared[offset : offset + batch_size]
            try:
                embedded = self.provider.embed_documents([text for _, text in batch])
                if len(embedded) != len(batch):
                    raise ValueError("candidate returned an unexpected vector count")
                for (row, _), vector in zip(batch, embedded):
                    vectors[str(row["unit_id"])] = _validated(vector, self.provider.dimension)
            except Exception:
                failed += len(batch)
                raise

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self.experimental_database) as target:
            target.row_factory = sqlite3.Row
            target.execute("PRAGMA foreign_keys=ON")
            target.execute("DELETE FROM candidate_vectors")
            target.execute("DELETE FROM candidate_units")
            target.executemany(
                "INSERT INTO candidate_units VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (str(row["unit_id"]), str(row["unit_type"]), int(row["video_id"]),
                     row["chunk_id"], row["start_time"], row["end_time"],
                     str(row["source_type"]), str(row["content_hash"]))
                    for row, _ in prepared
                ],
            )
            target.executemany(
                "INSERT INTO candidate_vectors VALUES(?, ?, ?, 1, ?, ?, ?, ?, ?)",
                [
                    (unit_id, vector.astype("<f4").tobytes(), self.provider.dimension,
                     self.provider.model_id, self.provider.revision,
                     self.provider.query_instruction, EXPERIMENT_VERSION, now)
                    for unit_id, vector in vectors.items()
                ],
            )
            target.execute(
                "INSERT OR REPLACE INTO candidate_meta VALUES(?, ?, ?, ?, ?, ?, ?)",
                (EXPERIMENT_VERSION, self.provider.model_id, self.provider.revision,
                 self.provider.dimension, self.provider.query_instruction, len(rows), now),
            )
            counts = target.execute(
                """
                SELECT COUNT(*) total, COUNT(*)-COUNT(DISTINCT u.unit_id) duplicates,
                       SUM(u.unit_type='video') videos,
                       SUM(u.unit_type='transcript_chunk') chunks,
                       SUM(length(v.embedding_blob) != ?) damaged
                FROM candidate_units u JOIN candidate_vectors v USING(unit_id)
                """,
                (self.provider.dimension * 4,),
            ).fetchone()
        return ExperimentalBuildStats(
            total_units=len(rows), video_units=int(counts["videos"] or 0),
            chunk_units=int(counts["chunks"] or 0), successful_vectors=len(vectors),
            failed_vectors=failed, duplicate_count=int(counts["duplicates"] or 0),
            damaged_vector_count=int(counts["damaged"] or 0),
            build_duration_seconds=time.monotonic() - started,
        )

    def search(self, query: str, *, top_k: int = 5) -> list[dict[str, object]]:
        query_vector = self.provider.embed_query(query)
        ranked: list[tuple[float, sqlite3.Row]] = []
        connection = sqlite3.connect(self.experimental_database)
        connection.row_factory = sqlite3.Row
        try:
            for row in connection.execute(
                "SELECT u.*, v.embedding_blob FROM candidate_units u JOIN candidate_vectors v USING(unit_id)"
            ):
                vector = np.frombuffer(row["embedding_blob"], dtype="<f4")
                ranked.append((float(np.dot(query_vector, vector)), row))
        finally:
            connection.close()
        ranked.sort(key=lambda item: (-item[0], str(item[1]["unit_id"])))
        return [
            {
                "unit_id": str(row["unit_id"]), "unit_type": str(row["unit_type"]),
                "video_id": int(row["video_id"]), "chunk_id": row["chunk_id"],
                "start_time": row["start_time"], "end_time": row["end_time"],
                "source_type": str(row["source_type"]), "score": score,
            }
            for score, row in ranked[:top_k]
        ]

    def _formal_read_only(self):
        uri = f"file:{self.formal_database}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection


def format_qwen_query(query: str, instruction: str = QUERY_INSTRUCTION) -> str:
    normalized = " ".join(query.split())
    if not normalized:
        raise ValueError("query must not be empty")
    return f"Instruct: {instruction}\nQuery: {normalized}"


def verify_local_snapshot(path: Path, revision: str) -> dict[str, object]:
    if not path.is_dir():
        raise OfflineModelError(f"candidate directory does not exist: {path}")
    required = ["config.json", "tokenizer.json"]
    missing = [name for name in required if not (path / name).is_file()]
    weights = sorted(path.glob("*.safetensors"))
    if not weights:
        missing.append("*.safetensors")
    marker = path / ".candidate-revision"
    actual_revision = marker.read_text(encoding="utf-8").strip() if marker.is_file() else ""
    if actual_revision != revision:
        missing.append(f".candidate-revision={revision}")
    if missing:
        raise OfflineModelError("MODEL DOWNLOAD INCOMPLETE: " + ", ".join(missing))
    return {"path": str(path), "revision": revision, "weight_files": len(weights)}


def parse_gate_state(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ": " in line and not line.startswith("#"):
            key, value = line.split(": ", 1)
            if key.strip() and " " not in key.strip():
                values[key.strip()] = value.strip()
    return values


def validate_phase_transition(current: str, desired: str) -> None:
    if current not in ALLOWED_PHASES or desired not in ALLOWED_PHASES:
        raise ValueError("unsupported Gate phase")
    if desired not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"invalid Gate transition: {current} -> {desired}")


def format_download_checkpoint(
    *, revision: str, dry_run_command: str, download_command: str,
    target: Path, expected: str, free_disk: str, verification_command: str,
) -> str:
    return f"""=== MODEL DOWNLOAD CHECKPOINT ===

Candidate:
Qwen/Qwen3-Embedding-0.6B

Pinned revision:
{revision}

Why this download is required:
The pinned candidate snapshot is not present as a complete offline local model.

Dry-run command:
{dry_run_command}

Download command for the user:
{download_command}

Target directory or cache:
{target}

Expected download:
{expected}

Free disk:
{free_disk}

Verification command after download:
{verification_command}

Resume instruction:
下载完成后，请回复：
“Qwen3 模型下载完成，继续”

Current state:
AWAITING_QWEN_DOWNLOAD"""


def formal_dense_fingerprint(database: Path) -> str:
    uri = f"file:{database}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        payload = {
            "vectors": connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(length(embedding_blob)),0) FROM retrieval_dense_vectors"
            ).fetchone(),
            "meta": connection.execute(
                "SELECT * FROM retrieval_dense_index_meta ORDER BY index_name"
            ).fetchall(),
        }
    finally:
        connection.close()
    return sha256(json.dumps(payload, default=list, sort_keys=True).encode()).hexdigest()


def _validated(value: Iterable[float], dimension: int) -> np.ndarray:
    vector = np.asarray(value, dtype=np.float32)
    if vector.ndim != 1 or vector.size != dimension:
        raise ValueError(f"candidate dimension mismatch: expected {dimension}, got {vector.size}")
    if not np.isfinite(vector).all():
        raise ValueError("candidate embedding contains non-finite values")
    norm = float(np.linalg.norm(vector))
    if norm <= 0:
        raise ValueError("candidate embedding must be non-zero")
    return vector / norm


def _mps_available() -> bool:
    try:
        import torch
        return bool(torch.backends.mps.is_available())
    except Exception:
        return False
