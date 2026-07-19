from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import re
import sqlite3
import time
from typing import Iterable, Protocol, Sequence

import numpy as np

from shiliu.db import Database
from shiliu.retrieval.models import (
    DenseSearchResult,
    FolderContext,
    RetrievalFilters,
    SearchLevel,
)
from shiliu.retrieval.service import RetrievalService, _excerpt


MODEL_ID = "BAAI/bge-small-zh-v1.5"
EMBEDDING_DIMENSION = 512
PROJECTION_VERSION = "v3-dense-projection-v2"
DENSE_INDEX_VERSION = "v3-stage2-dense-bge-small-zh-v1"
DENSE_INDEX_NAME = "shiliu_dense"
EMBEDDING_DTYPE = "float32"
BGE_MODEL_REVISION = "46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59"
BGE_PROVIDER_VERSION = "v3-fastembed-bge-provider-v1"
BGE_EMBEDDING_MODE = "fastembed-normalized-512"
BGE_QUERY_INSTRUCTION_VERSION = "none"
BGE_INPUT_POLICY_VERSION = "v3-bge-input-512-v1"

# Content-token quotas exclude the one-token field label and model special tokens.
# Their sum (456), ten one-token labels, and CLS/SEP remain below 480 tokens.
VIDEO_FIELD_TOKEN_LIMITS: tuple[tuple[str, str, int], ...] = (
    ("Title", "T", 64),
    ("Summary Conclusion", "C", 72),
    ("Summary Key Points", "K", 96),
    ("Summary Entities", "E", 56),
    ("Uploader", "U", 20),
    ("User Notes", "N", 32),
    ("Favorite Folders", "F", 20),
    ("Description", "D", 40),
    ("Summary Detailed Notes", "S", 32),
    ("Cleaned Transcript (video-level only)", "X", 24),
)
MODEL_MAX_TOKENS = 512
VIDEO_TOKEN_BUDGET = 480
VIDEO_RESERVED_TOKENS = MODEL_MAX_TOKENS - VIDEO_TOKEN_BUDGET


class EmbeddingProvider(Protocol):
    model_id: str
    dimension: int

    def embed_documents(self, texts: Sequence[str]) -> list[np.ndarray]: ...
    def embed_query(self, text: str) -> np.ndarray: ...
    def count_tokens(self, text: str, *, add_special_tokens: bool = True) -> int: ...
    def truncate_text(self, text: str, max_content_tokens: int) -> str: ...
    def model_identity(self) -> "DenseModelIdentity": ...


@dataclass(frozen=True)
class DenseModelIdentity:
    model_id: str
    model_revision: str
    provider_version: str
    dimension: int
    embedding_mode: str
    projection_version: str
    query_instruction_version: str
    input_policy_version: str
    dense_index_version: str


def provider_identity(provider: EmbeddingProvider) -> DenseModelIdentity:
    method = getattr(provider, "model_identity", None)
    if callable(method):
        return method()
    # Compatibility for the existing deterministic test providers.
    return DenseModelIdentity(
        model_id=provider.model_id,
        model_revision="test-or-legacy",
        provider_version="v3-legacy-provider-v1",
        dimension=provider.dimension,
        embedding_mode="normalized-float32",
        projection_version=PROJECTION_VERSION,
        query_instruction_version="none",
        input_policy_version="v3-legacy-input-v1",
        dense_index_version=DENSE_INDEX_VERSION,
    )


class FastEmbedEmbeddingProvider:
    """Lazy FastEmbed adapter: importing or constructing it does not load a model."""

    model_id = MODEL_ID
    dimension = EMBEDDING_DIMENSION

    def __init__(self, *, cache_dir: Path | None = None) -> None:
        self._model: object | None = None
        self.cache_dir = cache_dir

    def _get_model(self):
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(
                model_name=self.model_id,
                cache_dir=str(self.cache_dir) if self.cache_dir is not None else None,
            )
        return self._model

    def embed_documents(self, texts: Sequence[str]) -> list[np.ndarray]:
        return [_normalize(value) for value in self._get_model().embed(list(texts))]

    def embed_query(self, text: str) -> np.ndarray:
        model = self._get_model()
        method = getattr(model, "query_embed", model.embed)
        return _normalize(next(iter(method([text]))))

    def count_tokens(self, text: str, *, add_special_tokens: bool = True) -> int:
        tokenizer = self._get_model().model.tokenizer
        return len(tokenizer.encode(text, add_special_tokens=add_special_tokens).ids)

    def truncate_text(self, text: str, max_content_tokens: int) -> str:
        if max_content_tokens < 1:
            return ""
        if self.count_tokens(text, add_special_tokens=False) <= max_content_tokens:
            return text
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if self.count_tokens(text[:middle], add_special_tokens=False) <= max_content_tokens:
                low = middle
            else:
                high = middle - 1
        return text[:low].rstrip()

    def model_identity(self) -> DenseModelIdentity:
        return DenseModelIdentity(
            model_id=self.model_id,
            model_revision=BGE_MODEL_REVISION,
            provider_version=BGE_PROVIDER_VERSION,
            dimension=self.dimension,
            embedding_mode=BGE_EMBEDDING_MODE,
            projection_version=PROJECTION_VERSION,
            query_instruction_version=BGE_QUERY_INSTRUCTION_VERSION,
            input_policy_version=BGE_INPUT_POLICY_VERSION,
            dense_index_version=DENSE_INDEX_VERSION,
        )


class DenseIndexNotReadyError(RuntimeError):
    pass


class DenseIndexRebuildRequiredError(RuntimeError):
    pass


@dataclass
class DenseRebuildStats:
    total_unit_count: int = 0
    video_unit_count: int = 0
    chunk_unit_count: int = 0
    embedded_count: int = 0
    reused_count: int = 0
    stale_deleted_count: int = 0
    duration_seconds: float = 0.0
    identity: DenseModelIdentity | None = None

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        result.pop("identity")
        identity = self.identity or FastEmbedEmbeddingProvider().model_identity()
        result.update(
            model_id=identity.model_id,
            model_revision=identity.model_revision,
            provider_version=identity.provider_version,
            embedding_dimension=identity.dimension,
            embedding_mode=identity.embedding_mode,
            embedding_dtype=EMBEDDING_DTYPE,
            normalized=True,
            projection_version=identity.projection_version,
            query_instruction_version=identity.query_instruction_version,
            input_policy_version=identity.input_policy_version,
            dense_index_version=identity.dense_index_version,
        )
        result["duration_seconds"] = round(self.duration_seconds, 6)
        return result


def project_embedding_text(
    unit_type: str,
    search_text: str,
    *,
    tokenizer: EmbeddingProvider | None = None,
) -> str:
    if unit_type == "transcript_chunk":
        return search_text.strip()
    if tokenizer is None:
        raise ValueError("video projection requires the embedding model tokenizer")
    sections = _labeled_sections(search_text)
    pieces: list[str] = []
    seen: set[str] = set()
    for source_label, projection_label, token_limit in VIDEO_FIELD_TOKEN_LIMITS:
        value = sections.get(source_label, "")
        accepted: list[str] = []
        for paragraph in filter(None, (" ".join(p.split()) for p in value.splitlines())):
            key = paragraph.casefold()
            if key not in seen:
                seen.add(key)
                accepted.append(paragraph)
        body = tokenizer.truncate_text("\n".join(accepted), token_limit).strip()
        if not body:
            continue
        pieces.append(f"{projection_label}\n{body}")
    projection = "\n".join(pieces)
    token_count = tokenizer.count_tokens(projection)
    if token_count > VIDEO_TOKEN_BUDGET:
        raise ValueError(
            f"video projection exceeds token budget: {token_count} > {VIDEO_TOKEN_BUDGET}"
        )
    return projection


def prepare_embedding_document(
    unit_type: str, search_text: str, *, provider: EmbeddingProvider
) -> str:
    projected = project_embedding_text(unit_type, search_text, tokenizer=provider)
    prepare = getattr(provider, "prepare_document_text", None)
    return prepare(projected) if callable(prepare) else projected


class SQLiteExactDenseIndex:
    def __init__(self, *, db: Database, provider: EmbeddingProvider) -> None:
        self.db = db
        self.provider = provider

    def initialize_schema(self) -> None:
        with self.db.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS retrieval_dense_vectors (
                    unit_id TEXT PRIMARY KEY REFERENCES retrieval_units(unit_id) ON DELETE CASCADE,
                    model_id TEXT NOT NULL,
                    embedding_dimension INTEGER NOT NULL,
                    embedding_dtype TEXT NOT NULL,
                    normalized INTEGER NOT NULL,
                    embedding_blob BLOB NOT NULL,
                    source_content_hash TEXT NOT NULL,
                    embedding_text_hash TEXT NOT NULL,
                    projection_version TEXT NOT NULL,
                    dense_index_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS retrieval_dense_index_meta (
                    index_name TEXT PRIMARY KEY,
                    dense_index_version TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    embedding_dimension INTEGER NOT NULL,
                    embedding_dtype TEXT NOT NULL,
                    normalized INTEGER NOT NULL,
                    projection_version TEXT NOT NULL,
                    total_unit_count INTEGER NOT NULL,
                    video_unit_count INTEGER NOT NULL,
                    chunk_unit_count INTEGER NOT NULL,
                    built_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    build_duration_seconds REAL NOT NULL
                );
                """
            )
            existing = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(retrieval_dense_index_meta)")
            }
            additions = {
                "model_revision": f"TEXT NOT NULL DEFAULT '{BGE_MODEL_REVISION}'",
                "provider_version": f"TEXT NOT NULL DEFAULT '{BGE_PROVIDER_VERSION}'",
                "embedding_mode": f"TEXT NOT NULL DEFAULT '{BGE_EMBEDDING_MODE}'",
                "query_instruction_version": "TEXT NOT NULL DEFAULT 'none'",
                "input_policy_version": f"TEXT NOT NULL DEFAULT '{BGE_INPUT_POLICY_VERSION}'",
            }
            for name, definition in additions.items():
                if name not in existing:
                    connection.execute(
                        f"ALTER TABLE retrieval_dense_index_meta ADD COLUMN {name} {definition}"
                    )

    def rebuild(self, *, batch_size: int = 64) -> DenseRebuildStats:
        self.initialize_schema()
        identity = provider_identity(self.provider)
        started = time.monotonic()
        with self.db.connect() as connection:
            units = connection.execute(
                "SELECT unit_id, unit_type, search_text, content_hash FROM retrieval_units ORDER BY unit_id"
            ).fetchall()
            old = {
                str(row["unit_id"]): row
                for row in connection.execute("SELECT * FROM retrieval_dense_vectors")
            }
        desired: list[tuple[sqlite3.Row, str, str]] = []
        reusable: set[str] = set()
        metadata_updates: dict[str, str] = {}
        for row in units:
            text = prepare_embedding_document(
                str(row["unit_type"]), str(row["search_text"]), provider=self.provider,
            )
            text_hash = _hash(text)
            prior = old.get(str(row["unit_id"]))
            if prior is not None and self._compatible(prior, text_hash):
                unit_id = str(row["unit_id"])
                reusable.add(unit_id)
                if str(prior["source_content_hash"]) != str(row["content_hash"]):
                    metadata_updates[unit_id] = str(row["content_hash"])
            else:
                desired.append((row, text, text_hash))

        # Provider work happens before the replacement transaction.
        embedded: dict[str, tuple[np.ndarray, str, str]] = {}
        for offset in range(0, len(desired), batch_size):
            batch = desired[offset : offset + batch_size]
            vectors = self.provider.embed_documents([item[1] for item in batch])
            if len(vectors) != len(batch):
                raise ValueError("embedding provider returned an unexpected vector count")
            for (row, _text, text_hash), vector in zip(batch, vectors):
                checked = _validate_vector(vector, self.provider.dimension)
                embedded[str(row["unit_id"])] = (
                    checked,
                    str(row["content_hash"]),
                    text_hash,
                )

        now = _utc_now()
        current_ids = {str(row["unit_id"]) for row in units}
        stale = set(old) - current_ids
        stats = DenseRebuildStats(
            total_unit_count=len(units),
            video_unit_count=sum(str(r["unit_type"]) == "video" for r in units),
            chunk_unit_count=sum(str(r["unit_type"]) == "transcript_chunk" for r in units),
            embedded_count=len(embedded),
            reused_count=len(reusable),
            stale_deleted_count=len(stale),
            identity=identity,
        )
        with self.db.connect() as connection:
            if stale:
                connection.executemany(
                    "DELETE FROM retrieval_dense_vectors WHERE unit_id=?",
                    [(unit_id,) for unit_id in sorted(stale)],
                )
            for unit_id, (vector, source_hash, text_hash) in embedded.items():
                created_at = str(old[unit_id]["created_at"]) if unit_id in old else now
                connection.execute(
                    """
                    INSERT INTO retrieval_dense_vectors VALUES(?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(unit_id) DO UPDATE SET
                      model_id=excluded.model_id, embedding_dimension=excluded.embedding_dimension,
                      embedding_dtype=excluded.embedding_dtype, normalized=excluded.normalized,
                      embedding_blob=excluded.embedding_blob, source_content_hash=excluded.source_content_hash,
                      embedding_text_hash=excluded.embedding_text_hash,
                      projection_version=excluded.projection_version,
                      dense_index_version=excluded.dense_index_version, updated_at=excluded.updated_at
                    """,
                    (unit_id, identity.model_id, identity.dimension, EMBEDDING_DTYPE,
                     vector.astype("<f4").tobytes(), source_hash, text_hash,
                     identity.projection_version, identity.dense_index_version, created_at, now),
                )
            connection.executemany(
                "UPDATE retrieval_dense_vectors SET source_content_hash=?, updated_at=? WHERE unit_id=?",
                [
                    (source_hash, now, unit_id)
                    for unit_id, source_hash in sorted(metadata_updates.items())
                ],
            )
            stats.duration_seconds = time.monotonic() - started
            connection.execute(
                """
                INSERT INTO retrieval_dense_index_meta(
                  index_name, dense_index_version, model_id, embedding_dimension,
                  embedding_dtype, normalized, projection_version, total_unit_count,
                  video_unit_count, chunk_unit_count, built_at, updated_at,
                  build_duration_seconds, model_revision, provider_version,
                  embedding_mode, query_instruction_version, input_policy_version
                ) VALUES(?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(index_name) DO UPDATE SET
                  dense_index_version=excluded.dense_index_version, model_id=excluded.model_id,
                  embedding_dimension=excluded.embedding_dimension, embedding_dtype=excluded.embedding_dtype,
                  normalized=excluded.normalized, projection_version=excluded.projection_version,
                  total_unit_count=excluded.total_unit_count, video_unit_count=excluded.video_unit_count,
                  chunk_unit_count=excluded.chunk_unit_count, built_at=excluded.built_at,
                  updated_at=excluded.updated_at, build_duration_seconds=excluded.build_duration_seconds,
                  model_revision=excluded.model_revision, provider_version=excluded.provider_version,
                  embedding_mode=excluded.embedding_mode,
                  query_instruction_version=excluded.query_instruction_version,
                  input_policy_version=excluded.input_policy_version
                """,
                (DENSE_INDEX_NAME, identity.dense_index_version, identity.model_id,
                 identity.dimension, EMBEDDING_DTYPE, identity.projection_version,
                 stats.total_unit_count, stats.video_unit_count, stats.chunk_unit_count,
                 now, now, stats.duration_seconds, identity.model_revision,
                 identity.provider_version, identity.embedding_mode,
                 identity.query_instruction_version, identity.input_policy_version),
            )
        return stats

    def replace_video(self, video_id: int) -> DenseRebuildStats:
        self._assert_configuration_compatible()
        identity = provider_identity(self.provider)
        started = time.monotonic()
        with self.db.connect() as connection:
            units = connection.execute(
                """
                SELECT unit_id, unit_type, search_text, content_hash
                FROM retrieval_units WHERE video_id=? ORDER BY unit_id
                """,
                (video_id,),
            ).fetchall()
            old = {
                str(row["unit_id"]): row
                for row in connection.execute(
                    "SELECT d.* FROM retrieval_dense_vectors d "
                    "JOIN retrieval_units u ON u.unit_id=d.unit_id WHERE u.video_id=?",
                    (video_id,),
                )
            }
        desired: list[tuple[sqlite3.Row, str, str]] = []
        metadata_updates: dict[str, str] = {}
        reused = 0
        for row in units:
            text = prepare_embedding_document(
                str(row["unit_type"]), str(row["search_text"]), provider=self.provider
            )
            text_hash = _hash(text)
            unit_id = str(row["unit_id"])
            prior = old.get(unit_id)
            if prior is not None and self._compatible(prior, text_hash):
                reused += 1
                if str(prior["source_content_hash"]) != str(row["content_hash"]):
                    metadata_updates[unit_id] = str(row["content_hash"])
            else:
                desired.append((row, text, text_hash))
        vectors = (
            self.provider.embed_documents([item[1] for item in desired])
            if desired else []
        )
        if len(vectors) != len(desired):
            raise ValueError("embedding provider returned an unexpected vector count")
        embedded = [
            (row, _validate_vector(vector, self.provider.dimension), text_hash)
            for (row, _text, text_hash), vector in zip(desired, vectors)
        ]
        now = _utc_now()
        with self.db.connect() as connection:
            for row, vector, text_hash in embedded:
                unit_id = str(row["unit_id"])
                created_at = str(old[unit_id]["created_at"]) if unit_id in old else now
                connection.execute(
                    """
                    INSERT INTO retrieval_dense_vectors VALUES(?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(unit_id) DO UPDATE SET
                      model_id=excluded.model_id, embedding_dimension=excluded.embedding_dimension,
                      embedding_dtype=excluded.embedding_dtype, normalized=excluded.normalized,
                      embedding_blob=excluded.embedding_blob, source_content_hash=excluded.source_content_hash,
                      embedding_text_hash=excluded.embedding_text_hash,
                      projection_version=excluded.projection_version,
                      dense_index_version=excluded.dense_index_version, updated_at=excluded.updated_at
                    """,
                    (unit_id, identity.model_id, identity.dimension, EMBEDDING_DTYPE,
                     vector.astype("<f4").tobytes(), str(row["content_hash"]), text_hash,
                     identity.projection_version, identity.dense_index_version, created_at, now),
                )
            connection.executemany(
                "UPDATE retrieval_dense_vectors SET source_content_hash=?, updated_at=? WHERE unit_id=?",
                [(source_hash, now, unit_id) for unit_id, source_hash in sorted(metadata_updates.items())],
            )
            self._refresh_meta_counts(connection)
        return DenseRebuildStats(
            total_unit_count=len(units),
            video_unit_count=sum(str(row["unit_type"]) == "video" for row in units),
            chunk_unit_count=sum(str(row["unit_type"]) == "transcript_chunk" for row in units),
            embedded_count=len(embedded),
            reused_count=reused,
            duration_seconds=time.monotonic() - started,
            identity=identity,
        )

    def delete_video(self, video_id: int) -> int:
        self._assert_configuration_compatible()
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT v.unit_id FROM retrieval_dense_vectors v JOIN retrieval_units u ON u.unit_id=v.unit_id WHERE u.video_id=?",
                (video_id,),
            ).fetchall()
            connection.executemany(
                "DELETE FROM retrieval_dense_vectors WHERE unit_id=?", rows
            )
            self._refresh_meta_counts(connection)
        return len(rows)

    @staticmethod
    def _refresh_meta_counts(connection: sqlite3.Connection) -> None:
        counts = connection.execute(
            """
            SELECT COUNT(*) total,
                   SUM(u.unit_type='video') videos,
                   SUM(u.unit_type='transcript_chunk') chunks
            FROM retrieval_dense_vectors d
            JOIN retrieval_units u ON u.unit_id=d.unit_id
            """
        ).fetchone()
        connection.execute(
            """
            UPDATE retrieval_dense_index_meta
            SET total_unit_count=?, video_unit_count=?, chunk_unit_count=?, updated_at=?
            WHERE index_name=?
            """,
            (int(counts["total"] or 0), int(counts["videos"] or 0),
             int(counts["chunks"] or 0), _utc_now(), DENSE_INDEX_NAME),
        )

    def statistics(self) -> dict[str, object]:
        self.initialize_schema()
        with self.db.connect() as connection:
            meta = connection.execute(
                "SELECT * FROM retrieval_dense_index_meta WHERE index_name=?", (DENSE_INDEX_NAME,)
            ).fetchone()
            counts = connection.execute(
                "SELECT COUNT(*) n, SUM(u.unit_type='video') videos, SUM(u.unit_type='transcript_chunk') chunks FROM retrieval_dense_vectors d JOIN retrieval_units u ON u.unit_id=d.unit_id"
            ).fetchone()
            blobs = connection.execute(
                "SELECT embedding_blob FROM retrieval_dense_vectors"
            ).fetchall()
            damaged_count = sum(
                len(row["embedding_blob"]) != self.provider.dimension * 4
                for row in blobs
            )
        return {
            "ready": meta is not None,
            "current": {"total_unit_count": int(counts["n"] or 0), "video_unit_count": int(counts["videos"] or 0), "chunk_unit_count": int(counts["chunks"] or 0), "damaged_vector_count": damaged_count},
            "index": dict(meta) if meta is not None else None,
        }

    def search(self, query: str, *, level: SearchLevel = "all", top_k: int = 10,
               filters: RetrievalFilters | None = None, include_ignored: bool = False) -> list[DenseSearchResult]:
        normalized = " ".join(query.split())
        if not normalized:
            raise ValueError("query must not be empty")
        if level not in {"video", "transcript_chunk", "all"}:
            raise ValueError("unsupported search level")
        if not 1 <= top_k <= 500:
            raise ValueError("top_k must be between 1 and 500")
        self._assert_ready()
        query_vector = _validate_vector(self.provider.embed_query(normalized), self.provider.dimension)
        where, parameters = RetrievalService._search_filters(
            level=level, filters=filters or RetrievalFilters(), include_ignored=include_ignored
        )
        with self.db.connect() as connection:
            rows = connection.execute(
                f"SELECT u.*, d.embedding_blob FROM retrieval_dense_vectors d JOIN retrieval_units u ON u.unit_id=d.unit_id WHERE {where}",
                parameters,
            ).fetchall()
            ranked: list[tuple[float, sqlite3.Row]] = []
            for row in rows:
                if len(row["embedding_blob"]) != self.provider.dimension * 4:
                    continue
                vector = np.frombuffer(row["embedding_blob"], dtype="<f4")
                if vector.size != self.provider.dimension or not np.isfinite(vector).all():
                    continue
                ranked.append((float(np.dot(query_vector, vector)), row))
            ranked.sort(key=lambda item: (-item[0], str(item[1]["unit_id"])))
            return [self._result(connection, row, score, normalized) for score, row in ranked[:top_k]]

    def _assert_ready(self) -> None:
        self._assert_configuration_compatible()
        with self.db.connect() as connection:
            counts = connection.execute(
                "SELECT (SELECT COUNT(*) FROM retrieval_units) AS units, "
                "(SELECT COUNT(*) FROM retrieval_dense_vectors) AS vectors, "
                "(SELECT total_unit_count FROM retrieval_dense_index_meta "
                " WHERE index_name='shiliu_dense') AS meta_count"
            ).fetchone()
        if (
            int(counts["vectors"]) != int(counts["units"])
            or int(counts["meta_count"]) != int(counts["units"])
        ):
            raise DenseIndexRebuildRequiredError("dense index rebuild required")

    def _assert_configuration_compatible(self) -> None:
        self.initialize_schema()
        with self.db.connect() as connection:
            meta = connection.execute(
                "SELECT * FROM retrieval_dense_index_meta WHERE index_name=?", (DENSE_INDEX_NAME,)
            ).fetchone()
        if meta is None:
            raise DenseIndexNotReadyError("dense index not ready; run dense-rebuild")
        identity = provider_identity(self.provider)
        expected = (
            identity.dense_index_version, identity.model_id, identity.model_revision,
            identity.provider_version, identity.dimension, identity.embedding_mode,
            identity.projection_version, identity.query_instruction_version,
            identity.input_policy_version, 1,
        )
        actual = (
            str(meta["dense_index_version"]), str(meta["model_id"]),
            str(meta["model_revision"]), str(meta["provider_version"]),
            int(meta["embedding_dimension"]), str(meta["embedding_mode"]),
            str(meta["projection_version"]), str(meta["query_instruction_version"]),
            str(meta["input_policy_version"]), int(meta["normalized"]),
        )
        if actual != expected:
            raise DenseIndexRebuildRequiredError("dense index rebuild required")

    def _compatible(self, row: sqlite3.Row, text_hash: str) -> bool:
        identity = provider_identity(self.provider)
        return (
            str(row["model_id"]) == identity.model_id
            and int(row["embedding_dimension"]) == identity.dimension
            and str(row["embedding_dtype"]) == EMBEDDING_DTYPE
            and int(row["normalized"]) == 1
            and str(row["embedding_text_hash"]) == text_hash
            and str(row["projection_version"]) == identity.projection_version
            and str(row["dense_index_version"]) == identity.dense_index_version
            and len(row["embedding_blob"]) == identity.dimension * 4
        )

    def _result(self, connection: sqlite3.Connection, row: sqlite3.Row, score: float, query: str) -> DenseSearchResult:
        identity = provider_identity(self.provider)
        folders = tuple(FolderContext(int(f["source_db_id"]), int(f["folder_id"]), str(f["folder_title"]), int(f["favorite_time"]) if f["favorite_time"] is not None else None) for f in connection.execute("SELECT source_db_id, folder_id, folder_title, favorite_time FROM retrieval_unit_folders WHERE unit_id=? ORDER BY source_db_id", (row["unit_id"],)))
        return DenseSearchResult(
            unit_id=str(row["unit_id"]), unit_type=str(row["unit_type"]), video_id=int(row["video_id"]),
            platform=str(row["platform"]), source_id=str(row["source_id"]), part=int(row["part"]),
            title=str(row["title"]), uploader=str(row["uploader"]), chunk_id=str(row["chunk_id"]) if row["chunk_id"] else None,
            source_type=str(row["source_type"]), start_time=float(row["start_time"]) if row["start_time"] is not None else None,
            end_time=float(row["end_time"]) if row["end_time"] is not None else None,
            matched_excerpt=_excerpt(str(row["source_text"]), query), dense_score=score, retrieval_method="dense",
            index_version=str(row["index_version"]), dense_index_version=identity.dense_index_version,
            model_id=identity.model_id, projection_version=identity.projection_version,
            reading_state=str(row["reading_state"]),
            is_marked=bool(row["is_marked"]), is_ignored=bool(row["is_ignored"]), archived=bool(row["archived_at"]), folders=folders,
        )


def _labeled_sections(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"(?m)^\[([^\]]+)\]\n", text))
    return {m.group(1): text[m.end() : matches[i + 1].start() if i + 1 < len(matches) else len(text)].strip() for i, m in enumerate(matches)}


def _normalize(value: Iterable[float]) -> np.ndarray:
    vector = np.asarray(value, dtype=np.float32)
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(vector).all() or norm <= 0:
        raise ValueError("embedding vector must be finite and non-zero")
    return vector / norm


def _validate_vector(value: Iterable[float], dimension: int) -> np.ndarray:
    vector = _normalize(value)
    if vector.ndim != 1 or vector.size != dimension:
        raise ValueError(f"embedding dimension mismatch: expected {dimension}, got {vector.size}")
    return vector.astype(np.float32)


def _hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
