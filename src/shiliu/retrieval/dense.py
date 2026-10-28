from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import re
import time
from typing import Iterable, Protocol, Sequence

import numpy as np
import json
from psycopg.types.json import Jsonb

from shiliu.retrieval.models import (
    DenseSearchResult,
    RetrievalFilters,
)
from shiliu.retrieval.service import _excerpt, _folder_contexts


DENSE_INDEX_NAME = "shiliu_dense"
EMBEDDING_DTYPE = "float32"

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
    raise ValueError("complete_embedding_profile_required")


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
        identity = self.identity
        if identity is None:
            raise ValueError("complete_embedding_profile_required")
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
        for paragraph in filter(
            None, (" ".join(p.split()) for p in value.splitlines())
        ):
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


def profile_identity(provider):
    identity = provider_identity(provider)
    if identity.dimension != 512:
        raise ValueError("embedding_dimension_must_be_512")
    fields = asdict(identity)
    # Query instruction is a trace/query policy, not a document profile field.
    fields.pop("query_instruction_version")
    fields.update(
        dtype="float32",
        normalized=True,
        max_tokens=512,
        tokenizer_revision=identity.model_revision,
        document_policy_version=identity.projection_version,
    )
    if any(not value for value in fields.values()):
        raise ValueError("complete_embedding_profile_required")
    profile = (
        "embedding_"
        + sha256(
            json.dumps(
                fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
    )
    return profile, fields


class EncodedVectors(dict):
    def __init__(self, values, *, encoded_count, reused_count):
        super().__init__(values)
        self.encoded_count = encoded_count
        self.reused_count = reused_count


class PgExactDenseIndex:
    """Exact pgvector ranking. Encoding never holds a connection."""

    def __init__(self, *, db, provider, lexical=None):
        self.db, self.provider, self.lexical = db, provider, lexical
        self.identity = provider_identity(provider)
        self.profile_id, self.profile = profile_identity(provider)

    def register(self, *, conn=None):
        with self.db.connect(conn) as c:
            c.execute(
                "INSERT INTO shiliu.embedding_profiles(profile_id,model_id,model_revision,dimension,dtype,normalized,provider_version,document_policy_version,tokenizer_revision,max_tokens,identity) VALUES(%s,%s,%s,512,'float32',true,%s,%s,%s,512,%s) ON CONFLICT(profile_id) DO NOTHING",
                (
                    self.profile_id,
                    self.identity.model_id,
                    self.identity.model_revision,
                    self.identity.provider_version,
                    self.identity.projection_version,
                    self.identity.model_revision,
                    Jsonb(self.profile),
                ),
            )
            old = c.execute(
                "SELECT identity FROM shiliu.embedding_profiles WHERE profile_id=%s",
                (self.profile_id,),
            ).fetchone()
            if old["identity"] != self.profile:
                raise ValueError("embedding_profile_conflict")
        return self.profile_id

    def active_profile(self, *, conn=None):
        with self.db.connect(conn, read_only=True) as c:
            row = c.execute(
                "SELECT embedding_profile_id FROM shiliu.assistant_runtime_state WHERE workspace_id=%s AND principal_id=%s AND embedding_domain='collection'",
                (self.db.workspace_id, self.db.context.user_id),
            ).fetchone()
            return row["embedding_profile_id"] if row else None

    def encode(self, units):
        texts = [
            prepare_embedding_document(
                u.unit_type, u.search_text, provider=self.provider
            )
            for u in units
        ]
        if any(self.provider.count_tokens(text) > MODEL_MAX_TOKENS for text in texts):
            raise ValueError("embedding_document_exceeds_512_token_policy")
        # A freshly prepared document with the same immutable complete profile
        # and exact input hash has the same encoding. Rebind its source hash and
        # generation only at the later fenced publication, never in this read.
        with self.db.connect(read_only=True) as c:
            cached = {
                r["unit_id"]: r
                for r in c.execute(
                    "SELECT unit_id,embedding_text_hash,embedding FROM shiliu.collection_embeddings WHERE workspace_id=%s AND profile_id=%s AND unit_id=ANY(%s)",
                    (self.db.workspace_id, self.profile_id, [u.unit_id for u in units]),
                )
            }
        result, missing = {}, []
        for unit, text in zip(units, texts):
            text_hash = _hash(text)
            row = cached.get(unit.unit_id)
            if row and row["embedding_text_hash"] == text_hash:
                try:
                    result[unit.unit_id] = (
                        _validate_vector(row["embedding"].to_numpy(), 512),
                        text_hash,
                    )
                    continue
                except ValueError:
                    pass
            missing.append((unit, text, text_hash))
        vectors = (
            self.provider.embed_documents([text for _, text, _ in missing])
            if missing
            else []
        )
        if len(vectors) != len(missing):
            raise ValueError("embedding_result_count_mismatch")
        reused = len(result)
        result.update(
            {
                u.unit_id: (_validate_vector(v, 512), text_hash)
                for (u, _, text_hash), v in zip(missing, vectors)
            }
        )
        return EncodedVectors(result, encoded_count=len(missing), reused_count=reused)

    def publish(self, conn, units, vectors, generation):
        self.register(conn=conn)
        for unit in units:
            vector, text_hash = vectors[unit.unit_id]
            conn.execute(
                "INSERT INTO shiliu.collection_embeddings(unit_id,profile_id,workspace_id,source_content_hash,embedding_text_hash,generation,embedding,created_at,updated_at) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,clock_timestamp(),clock_timestamp()) ON CONFLICT(workspace_id,unit_id,profile_id) DO UPDATE SET "
                "source_content_hash=excluded.source_content_hash,embedding_text_hash=excluded.embedding_text_hash,generation=excluded.generation,embedding=excluded.embedding,updated_at=excluded.updated_at",
                (
                    unit.unit_id,
                    self.profile_id,
                    self.db.workspace_id,
                    unit.content_hash,
                    text_hash,
                    generation,
                    vector,
                ),
            )

    def activate(self):
        with self.db.connect(guard=True) as c:
            missing = self._coverage(c)
            if missing:
                raise DenseIndexNotReadyError("embedding_profile_coverage_incomplete")
            c.execute(
                "INSERT INTO shiliu.assistant_runtime_state(workspace_id,principal_id,key,value,updated_at,embedding_domain,embedding_profile_id) "
                "VALUES(%s,%s,'embedding:collection:active',%s,clock_timestamp(),'collection',%s) ON CONFLICT(workspace_id,principal_id,key) DO UPDATE SET "
                "value=excluded.value,embedding_profile_id=excluded.embedding_profile_id,updated_at=excluded.updated_at",
                (
                    self.db.workspace_id,
                    self.db.context.user_id,
                    self.profile_id,
                    self.profile_id,
                ),
            )

    def _coverage(self, c):
        missing = c.execute(
            "SELECT COUNT(*) AS n FROM shiliu.videos v WHERE v.workspace_id=%s AND v.removed_at IS NULL "
            "AND EXISTS(SELECT 1 FROM shiliu.video_source_memberships m JOIN shiliu.favorite_sources s ON s.workspace_id=m.workspace_id AND s.id=m.source_id WHERE m.workspace_id=v.workspace_id AND m.video_id=v.id AND m.removed_at IS NULL AND s.status='active') "
            "AND NOT EXISTS(SELECT 1 FROM shiliu.retrieval_units u JOIN shiliu.retrieval_projection_tasks t ON t.workspace_id=u.workspace_id AND t.domain='collection' AND t.resource_key=u.video_id::text AND t.requested_generation=u.generation WHERE u.workspace_id=v.workspace_id AND u.video_id=v.id AND u.unit_type='video')",
            (self.db.workspace_id,),
        ).fetchone()["n"]
        where, params = self.lexical._search_filters(
            level="all", filters=RetrievalFilters(), include_ignored=True
        )
        missing += c.execute(
            "SELECT COUNT(*) AS n "
            + self.lexical.current_join()
            + "WHERE "
            + where
            + " AND NOT EXISTS(SELECT 1 FROM shiliu.collection_embeddings e WHERE (e.workspace_id,e.unit_id)=(u.workspace_id,u.unit_id) AND e.profile_id=%s AND e.generation=u.generation AND e.source_content_hash=u.content_hash)",
            [*params, self.profile_id],
        ).fetchone()["n"]
        return missing

    def rebuild(self, *, batch_size=64):
        if self.lexical is None:
            raise ValueError("lexical_service_required")
        from shiliu.retrieval.coordinator import ProjectionWorker

        self.register()
        stats = DenseRebuildStats(identity=self.identity)
        started = time.monotonic()
        for video in self.db.list_videos():
            # Keep the formal generation and active profile valid during a new
            # profile build; only the requested target/profile payload changes.
            with self.db.connect(guard=True) as c:
                row = c.execute(
                    "SELECT id FROM shiliu.retrieval_projection_tasks WHERE workspace_id=%s AND domain='collection' AND resource_key=%s FOR UPDATE",
                    (self.db.workspace_id, str(video["id"])),
                ).fetchone()
                if row is None:
                    self.db._touch(c, video["id"], reason="dense_rebuild")
                c.execute(
                    "UPDATE shiliu.retrieval_projection_tasks SET payload=payload||%s,status='queued',attempt=0,not_before=clock_timestamp(),updated_at=clock_timestamp() WHERE workspace_id=%s AND domain='collection' AND resource_key=%s",
                    (
                        Jsonb({"target_profile": self.profile_id}),
                        self.db.workspace_id,
                        str(video["id"]),
                    ),
                )
            result = ProjectionWorker(self.lexical, self).run_one(video_id=video["id"])
            if result and result.get("dense_state") == "current":
                stats.embedded_count += result.get("embedded_count", 0)
                stats.reused_count += result.get("reused_count", 0)
        self.activate()
        current = self.statistics()["index"]
        stats.total_unit_count = current["total_unit_count"]
        stats.video_unit_count = current["video_unit_count"]
        stats.chunk_unit_count = current["chunk_unit_count"]
        stats.duration_seconds = time.monotonic() - started
        return stats

    def replace_video(self, video_id):
        if self.lexical is None:
            raise ValueError("lexical_service_required")
        from shiliu.retrieval.coordinator import ProjectionWorker

        result = ProjectionWorker(self.lexical, self).run_one(video_id=video_id)
        return DenseRebuildStats(
            embedded_count=(result or {}).get("total_units", 0), identity=self.identity
        )

    def statistics(self):
        with self.db.connect(read_only=True) as c:
            active = self.active_profile(conn=c)
            missing = self._coverage(c) if self.lexical is not None else 0
            where, params = self.lexical._search_filters(
                level="all", filters=RetrievalFilters(), include_ignored=True
            )
            counts = c.execute(
                "SELECT COUNT(*) AS total_unit_count,COUNT(*) FILTER(WHERE u.unit_type='video') AS video_unit_count,COUNT(*) FILTER(WHERE u.unit_type='transcript_chunk') AS chunk_unit_count "
                + self.lexical.current_join()
                + "JOIN shiliu.collection_embeddings e ON (e.workspace_id,e.unit_id)=(u.workspace_id,u.unit_id) WHERE "
                + where
                + " AND e.profile_id=%s AND e.generation=u.generation AND e.source_content_hash=u.content_hash",
                [*params, self.profile_id],
            ).fetchone()
            tasks = c.execute(
                "SELECT resource_key,requested_generation,payload->>'ready_generation' AS ready_generation,status,attempt,last_error "
                "FROM shiliu.retrieval_projection_tasks WHERE workspace_id=%s AND domain='collection' ORDER BY id",
                (self.db.workspace_id,),
            ).fetchall()
        return {
            "index": dict(
                counts,
                **asdict(self.identity),
                embedding_profile=self.profile_id,
                active_profile=active,
                ready=active == self.profile_id and missing == 0,
                missing_count=missing,
                failed_count=sum(t["status"] == "failed" for t in tasks),
                pending_count=sum(t["status"] != "completed" for t in tasks),
                tasks=tasks,
                embedding_dimension=512,
            ),
            "current": dict(counts),
        }

    def search(
        self, query, *, level="all", top_k=10, filters=None, include_ignored=False
    ):
        if not query.strip():
            return []
        if self.active_profile() != self.profile_id:
            raise DenseIndexNotReadyError("embedding_profile_not_active")
        if self.lexical is None:
            raise ValueError("lexical_service_required")
        vector = _validate_vector(self.provider.embed_query(query), 512)
        return self.search_vector(
            vector,
            query=query,
            level=level,
            top_k=top_k,
            filters=filters,
            include_ignored=include_ignored,
        )

    def search_vector(
        self,
        vector,
        *,
        query="",
        level="all",
        top_k=10,
        filters=None,
        include_ignored=False,
    ):
        vector = _validate_vector(vector, 512)
        if level not in {"all", "video", "transcript_chunk"} or not 1 <= top_k <= 500:
            raise ValueError("Invalid dense bounds")
        where, params = self.lexical._search_filters(
            level=level,
            filters=filters or RetrievalFilters(),
            include_ignored=include_ignored,
        )
        with self.db.connect(read_only=True) as c:
            active = self.active_profile(conn=c)
            if active != self.profile_id:
                raise DenseIndexNotReadyError("embedding_profile_not_active")
            rows = c.execute(
                "SELECT u.*,e.embedding <=> %s AS distance "
                + self.lexical.current_join()
                + "JOIN shiliu.collection_embeddings e ON (e.workspace_id,e.unit_id)=(u.workspace_id,u.unit_id) "
                "JOIN shiliu.embedding_profiles p ON p.profile_id=e.profile_id "
                "WHERE "
                + where
                + " AND e.profile_id=%s AND e.generation=u.generation AND e.source_content_hash=u.content_hash "
                "ORDER BY distance,u.unit_id LIMIT %s",
                [vector, *params, active, top_k],
            ).fetchall()
            folders = _folder_contexts(
                c, self.db.workspace_id, [r["unit_id"] for r in rows]
            )
            return [
                self._result(
                    r, 1 - float(r["distance"]), query, folders.get(r["unit_id"], ())
                )
                for r in rows
            ]

    def _result(
        self, row: dict, score: float, query: str, folders: tuple
    ) -> DenseSearchResult:
        identity = provider_identity(self.provider)
        return DenseSearchResult(
            unit_id=str(row["unit_id"]),
            unit_type=str(row["unit_type"]),
            video_id=int(row["video_id"]),
            platform=str(row["platform"]),
            source_id=str(row["source_id"]),
            part=int(row["part"]),
            title=str(row["title"]),
            uploader=str(row["uploader"]),
            chunk_id=str(row["chunk_id"]) if row["chunk_id"] else None,
            source_type=str(row["source_type"]),
            start_time=float(row["start_time"])
            if row["start_time"] is not None
            else None,
            end_time=float(row["end_time"]) if row["end_time"] is not None else None,
            matched_excerpt=_excerpt(str(row["source_text"]), query),
            dense_score=score,
            retrieval_method="dense",
            index_version=str(row["index_version"]),
            dense_index_version=identity.dense_index_version,
            model_id=identity.model_id,
            projection_version=identity.projection_version,
            reading_state=str(row["reading_state"]),
            is_marked=bool(row["is_marked"]),
            is_ignored=bool(row["is_ignored"]),
            archived=bool(row["archived_at"]),
            folders=folders,
        )


def _labeled_sections(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"(?m)^\[([^\]]+)\]\n", text))
    return {
        m.group(1): text[
            m.end() : matches[i + 1].start() if i + 1 < len(matches) else len(text)
        ].strip()
        for i, m in enumerate(matches)
    }


def _normalize(value: Iterable[float]) -> np.ndarray:
    vector = np.asarray(value, dtype=np.float32)
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(vector).all() or norm <= 0:
        raise ValueError("embedding vector must be finite and non-zero")
    return vector / norm


def _validate_vector(value, dimension):
    vector = np.asarray(value, dtype=np.float32)
    if vector.ndim != 1 or vector.size != dimension:
        raise ValueError("embedding_dimension_mismatch")
    if not np.isfinite(vector).all():
        raise ValueError("embedding_not_finite")
    norm = float(np.linalg.norm(vector))
    if norm <= 0 or abs(norm - 1.0) > 0.01:
        raise ValueError("embedding_norm_invalid")
    return vector


def _hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
