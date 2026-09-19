from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import sqlite3
import time
from typing import Callable
from uuid import uuid4

import numpy as np

from shiliu.db import Database
from shiliu.retrieval.dense import (
    DENSE_INDEX_NAME,
    DenseModelIdentity,
    EMBEDDING_DTYPE,
    EmbeddingProvider,
    SQLiteExactDenseIndex,
    _validate_vector,
    prepare_embedding_document,
    provider_identity,
)


@dataclass
class CandidateBuildStats:
    build_id: str
    corpus_fingerprint: str
    total_unit_count: int
    video_unit_count: int
    chunk_unit_count: int
    successful_vectors: int
    failed_vectors: int
    duplicate_unit_ids: int
    damaged_vectors: int
    norm_violations: int
    duration_seconds: float

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["duration_seconds"] = round(self.duration_seconds, 6)
        return result


class DenseAdoptionManager:
    """One-candidate migration helper; it is not a general model registry."""

    def __init__(self, *, db: Database, provider: EmbeddingProvider) -> None:
        self.db = db
        self.provider = provider

    def initialize_schema(self) -> None:
        SQLiteExactDenseIndex(db=self.db, provider=self.provider).initialize_schema()
        with self.db.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS retrieval_dense_candidate_meta (
                    build_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK(status IN ('building','ready','failed','stale','cutover')),
                    model_id TEXT NOT NULL,
                    model_revision TEXT NOT NULL,
                    provider_version TEXT NOT NULL,
                    embedding_dimension INTEGER NOT NULL,
                    embedding_mode TEXT NOT NULL,
                    projection_version TEXT NOT NULL,
                    query_instruction_version TEXT NOT NULL,
                    input_policy_version TEXT NOT NULL,
                    dense_index_version TEXT NOT NULL,
                    corpus_fingerprint TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    row_count INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS retrieval_dense_vectors_candidate (
                    build_id TEXT NOT NULL REFERENCES retrieval_dense_candidate_meta(build_id) ON DELETE CASCADE,
                    unit_id TEXT NOT NULL REFERENCES retrieval_units(unit_id) ON DELETE CASCADE,
                    embedding_blob BLOB NOT NULL,
                    source_content_hash TEXT NOT NULL,
                    embedding_text_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(build_id, unit_id)
                );
                """
            )

    def corpus_snapshot(self) -> tuple[list[tuple[sqlite3.Row, str, str]], str]:
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT unit_id, unit_type, search_text, content_hash "
                "FROM retrieval_units ORDER BY unit_id"
            ).fetchall()
        prepared: list[tuple[sqlite3.Row, str, str]] = []
        digest = sha256()
        for row in rows:
            text = prepare_embedding_document(
                str(row["unit_type"]), str(row["search_text"]), provider=self.provider
            )
            text_hash = sha256(text.encode("utf-8")).hexdigest()
            for value in (
                str(row["unit_id"]), str(row["unit_type"]), text_hash,
                str(row["content_hash"]),
            ):
                digest.update(value.encode("utf-8"))
                digest.update(b"\0")
            prepared.append((row, text, text_hash))
        return prepared, digest.hexdigest()

    def build_candidate(
        self, *, batch_size: int = 8, build_id: str | None = None
    ) -> CandidateBuildStats:
        self.initialize_schema()
        started = time.monotonic()
        prepared, fingerprint = self.corpus_snapshot()
        identity = provider_identity(self.provider)
        build_id = build_id or (
            datetime.now(timezone.utc).strftime("qwen-%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
        )
        now = _utc_now()
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO retrieval_dense_candidate_meta VALUES(
                  ?, 'building', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, NULL
                )
                """,
                (build_id, identity.model_id, identity.model_revision,
                 identity.provider_version, identity.dimension, identity.embedding_mode,
                 identity.projection_version, identity.query_instruction_version,
                 identity.input_policy_version, identity.dense_index_version,
                 fingerprint, now),
            )
        successful = failed = 0
        try:
            for offset in range(0, len(prepared), batch_size):
                batch = prepared[offset : offset + batch_size]
                vectors = self.provider.embed_documents([item[1] for item in batch])
                if len(vectors) != len(batch):
                    raise ValueError("embedding provider returned an unexpected vector count")
                records = []
                for (row, _text, text_hash), value in zip(batch, vectors):
                    vector = _validate_vector(value, identity.dimension)
                    records.append(
                        (build_id, str(row["unit_id"]), vector.astype("<f4").tobytes(),
                         str(row["content_hash"]), text_hash, _utc_now())
                    )
                with self.db.connect() as connection:
                    connection.executemany(
                        "INSERT INTO retrieval_dense_vectors_candidate VALUES(?, ?, ?, ?, ?, ?)",
                        records,
                    )
                successful += len(records)
            validation = self.validate_candidate(build_id)
            status = "ready" if validation["valid"] else "failed"
            error = None if validation["valid"] else str(validation)
        except Exception as exc:
            failed = len(prepared) - successful
            status, error = "failed", f"{type(exc).__name__}: {exc}"[:1000]
            with self.db.connect() as connection:
                connection.execute(
                    "UPDATE retrieval_dense_candidate_meta SET status=?, completed_at=?, "
                    "row_count=?, error=? WHERE build_id=?",
                    (status, _utc_now(), successful, error, build_id),
                )
            raise
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE retrieval_dense_candidate_meta SET status=?, completed_at=?, "
                "row_count=?, error=? WHERE build_id=?",
                (status, _utc_now(), successful, error, build_id),
            )
        stats = CandidateBuildStats(
            build_id=build_id, corpus_fingerprint=fingerprint,
            total_unit_count=len(prepared),
            video_unit_count=sum(str(row["unit_type"]) == "video" for row, _, _ in prepared),
            chunk_unit_count=sum(str(row["unit_type"]) == "transcript_chunk" for row, _, _ in prepared),
            successful_vectors=successful, failed_vectors=failed,
            duplicate_unit_ids=0, damaged_vectors=int(validation["damaged_vectors"]),
            norm_violations=int(validation["norm_violations"]),
            duration_seconds=time.monotonic() - started,
        )
        if status != "ready":
            raise RuntimeError(f"candidate validation failed: {validation}")
        return stats

    def validate_candidate(self, build_id: str) -> dict[str, object]:
        identity = provider_identity(self.provider)
        _, current_fingerprint = self.corpus_snapshot()
        with self.db.connect() as connection:
            meta = connection.execute(
                "SELECT * FROM retrieval_dense_candidate_meta WHERE build_id=?", (build_id,)
            ).fetchone()
            if meta is None:
                raise ValueError(f"candidate build not found: {build_id}")
            blobs = connection.execute(
                "SELECT embedding_blob FROM retrieval_dense_vectors_candidate WHERE build_id=?",
                (build_id,),
            ).fetchall()
            counts = connection.execute(
                """
                SELECT
                  (SELECT COUNT(*) FROM retrieval_units) units,
                  (SELECT COUNT(*) FROM retrieval_dense_vectors_candidate WHERE build_id=?) candidates,
                  (SELECT COUNT(*) FROM retrieval_units u LEFT JOIN retrieval_dense_vectors_candidate c
                    ON c.unit_id=u.unit_id AND c.build_id=? WHERE c.unit_id IS NULL) missing,
                  (SELECT COUNT(*) FROM retrieval_dense_vectors_candidate c LEFT JOIN retrieval_units u
                    ON u.unit_id=c.unit_id WHERE c.build_id=? AND u.unit_id IS NULL) extra
                """,
                (build_id, build_id, build_id),
            ).fetchone()
            foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        damaged = sum(len(row["embedding_blob"]) != identity.dimension * 4 for row in blobs)
        norm_violations = 0
        non_finite = 0
        for row in blobs:
            vector = np.frombuffer(row["embedding_blob"], dtype="<f4")
            if not np.isfinite(vector).all():
                non_finite += 1
            elif not np.isclose(np.linalg.norm(vector), 1.0, atol=1e-5):
                norm_violations += 1
        identity_ok = all(
            (
                str(meta["model_id"]) == identity.model_id,
                str(meta["model_revision"]) == identity.model_revision,
                str(meta["provider_version"]) == identity.provider_version,
                int(meta["embedding_dimension"]) == identity.dimension,
                str(meta["embedding_mode"]) == identity.embedding_mode,
                str(meta["projection_version"]) == identity.projection_version,
                str(meta["query_instruction_version"]) == identity.query_instruction_version,
                str(meta["input_policy_version"]) == identity.input_policy_version,
                str(meta["dense_index_version"]) == identity.dense_index_version,
            )
        )
        result = {
            "build_id": build_id, "status": str(meta["status"]),
            "units": int(counts["units"]), "candidate_rows": int(counts["candidates"]),
            "missing_rows": int(counts["missing"]), "extra_rows": int(counts["extra"]),
            "duplicate_unit_ids": 0, "damaged_vectors": damaged,
            "non_finite_vectors": non_finite, "norm_violations": norm_violations,
            "foreign_key_violations": len(foreign_keys), "identity_ok": identity_ok,
            "recorded_corpus_fingerprint": str(meta["corpus_fingerprint"]),
            "current_corpus_fingerprint": current_fingerprint,
        }
        result["valid"] = all((
            int(counts["units"]) == int(counts["candidates"]),
            int(counts["missing"]) == 0, int(counts["extra"]) == 0,
            damaged == 0, non_finite == 0, norm_violations == 0,
            not foreign_keys, identity_ok,
            str(meta["corpus_fingerprint"]) == current_fingerprint,
        ))
        return result

    def atomic_cutover(
        self, build_id: str, *, expected_formal_fingerprint: str,
        expected_formal_identity: DenseModelIdentity,
        failure_hook: Callable[[str], None] | None = None,
    ) -> None:
        validation = self.validate_candidate(build_id)
        if not validation["valid"] or validation["status"] != "ready":
            raise RuntimeError("candidate is not ready for cutover")
        if formal_dense_fingerprint(self.db) != expected_formal_fingerprint:
            raise RuntimeError("formal dense index changed after shadow build")
        with self.db.connect() as connection:
            current_meta = connection.execute(
                "SELECT * FROM retrieval_dense_index_meta WHERE index_name=?",
                (DENSE_INDEX_NAME,),
            ).fetchone()
        if current_meta is None or not _meta_matches(current_meta, expected_formal_identity):
            raise RuntimeError("formal dense identity changed after shadow build")
        identity = provider_identity(self.provider)
        now = _utc_now()
        with self.db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            meta = connection.execute(
                "SELECT * FROM retrieval_dense_candidate_meta WHERE build_id=?", (build_id,)
            ).fetchone()
            if meta is None or str(meta["status"]) != "ready":
                raise RuntimeError("candidate status changed before cutover")
            formal_meta = connection.execute(
                "SELECT * FROM retrieval_dense_index_meta WHERE index_name=?",
                (DENSE_INDEX_NAME,),
            ).fetchone()
            if formal_meta is None or not _meta_matches(
                formal_meta, expected_formal_identity
            ):
                raise RuntimeError("formal dense identity changed before cutover")
            connection.execute("DELETE FROM retrieval_dense_vectors")
            connection.execute(
                """
                INSERT INTO retrieval_dense_vectors(
                  unit_id, model_id, embedding_dimension, embedding_dtype, normalized,
                  embedding_blob, source_content_hash, embedding_text_hash,
                  projection_version, dense_index_version, created_at, updated_at
                )
                SELECT unit_id, ?, ?, ?, 1, embedding_blob, source_content_hash,
                       embedding_text_hash, ?, ?, created_at, ?
                FROM retrieval_dense_vectors_candidate WHERE build_id=?
                """,
                (identity.model_id, identity.dimension, EMBEDDING_DTYPE,
                 identity.projection_version, identity.dense_index_version, now, build_id),
            )
            if failure_hook:
                failure_hook("after_vectors")
            counts = connection.execute(
                "SELECT COUNT(*) total, SUM(u.unit_type='video') videos, "
                "SUM(u.unit_type='transcript_chunk') chunks FROM retrieval_dense_vectors d "
                "JOIN retrieval_units u ON u.unit_id=d.unit_id"
            ).fetchone()
            connection.execute(
                """
                UPDATE retrieval_dense_index_meta SET
                  dense_index_version=?, model_id=?, model_revision=?, provider_version=?,
                  embedding_dimension=?, embedding_dtype=?, normalized=1, embedding_mode=?,
                  projection_version=?, query_instruction_version=?, input_policy_version=?,
                  total_unit_count=?, video_unit_count=?, chunk_unit_count=?,
                  built_at=?, updated_at=?, build_duration_seconds=0
                WHERE index_name=?
                """,
                (identity.dense_index_version, identity.model_id, identity.model_revision,
                 identity.provider_version, identity.dimension, EMBEDDING_DTYPE,
                 identity.embedding_mode, identity.projection_version,
                 identity.query_instruction_version, identity.input_policy_version,
                 int(counts["total"]), int(counts["videos"] or 0),
                 int(counts["chunks"] or 0), now, now, DENSE_INDEX_NAME),
            )
            if failure_hook:
                failure_hook("after_meta")
            connection.execute(
                "UPDATE retrieval_dense_candidate_meta SET status='cutover' WHERE build_id=?",
                (build_id,),
            )


def formal_dense_fingerprint(db: Database) -> str:
    digest = sha256()
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT unit_id, model_id, embedding_dimension, projection_version, "
            "dense_index_version, embedding_blob FROM retrieval_dense_vectors ORDER BY unit_id"
        ).fetchall()
    for row in rows:
        for key in (
            "unit_id", "model_id", "embedding_dimension", "projection_version",
            "dense_index_version", "embedding_blob",
        ):
            value = row[key]
            digest.update(value if isinstance(value, bytes) else str(value).encode("utf-8"))
            digest.update(b"\0")
    return digest.hexdigest()


def candidate_dense_fingerprint(db: Database, build_id: str) -> str:
    digest = sha256()
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT unit_id, embedding_blob FROM retrieval_dense_vectors_candidate "
            "WHERE build_id=? ORDER BY unit_id", (build_id,)
        ).fetchall()
    for row in rows:
        digest.update(str(row["unit_id"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(row["embedding_blob"])
        digest.update(b"\0")
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _meta_matches(row: sqlite3.Row, identity: DenseModelIdentity) -> bool:
    return all((
        str(row["dense_index_version"]) == identity.dense_index_version,
        str(row["model_id"]) == identity.model_id,
        str(row["model_revision"]) == identity.model_revision,
        str(row["provider_version"]) == identity.provider_version,
        int(row["embedding_dimension"]) == identity.dimension,
        str(row["embedding_mode"]) == identity.embedding_mode,
        str(row["projection_version"]) == identity.projection_version,
        str(row["query_instruction_version"]) == identity.query_instruction_version,
        str(row["input_policy_version"]) == identity.input_policy_version,
        int(row["normalized"]) == 1,
    ))
