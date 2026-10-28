from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from psycopg import sql
from psycopg.types.json import Jsonb
from shiliu.db import collection_dto
from shiliu.storage.errors import StorageError
import time
from typing import Callable, Sequence
from uuid import uuid4

from shiliu.db import Database
from shiliu.retrieval.dense import (
    DenseIndexNotReadyError,
    DenseIndexRebuildRequiredError,
    PgExactDenseIndex,
)
from shiliu.retrieval.hybrid import (
    FUSION_VERSION,
    HybridRetrievalService,
)
from shiliu.retrieval.models import DenseSearchResult, HybridSearchResult, SearchResult
from shiliu.retrieval.planner import (
    SearchPlan,
    SearchPlanner,
    SearchRequest,
    SearchValidationError,
)
from shiliu.retrieval.qwen import LocalModelNotReadyError
from shiliu.retrieval.service import INDEX_VERSION, RetrievalService


TRACE_VERSION = "v3-stage4a-search-trace-v1"
MAX_EXCERPT_CHARACTERS = 300


@dataclass(frozen=True)
class SearchTiming:
    planning_ms: float = 0.0
    lexical_ms: float = 0.0
    dense_ms: float = 0.0
    fusion_ms: float = 0.0
    total_ms: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {name: round(value, 3) for name, value in asdict(self).items()}


@dataclass(frozen=True)
class RawSearchHit:
    unit_id: str
    video_id: int
    unit_type: str
    rank: int
    score: float
    retrieval_method: str
    lexical_rank: int | None
    lexical_score: float | None
    dense_rank: int | None
    dense_score: float | None
    rrf_score: float | None
    title: str
    uploader: str
    subtitle_source: str
    start_time: float | None
    end_time: float | None
    excerpt: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def trace_dict(self) -> dict[str, object]:
        return {
            name: getattr(self, name)
            for name in (
                "unit_id",
                "rank",
                "score",
                "lexical_rank",
                "lexical_score",
                "dense_rank",
                "dense_score",
                "rrf_score",
            )
        }


@dataclass(frozen=True)
class RawSearchResponse:
    trace_id: str
    trace_persisted: bool
    trace_error: dict[str, str] | None
    plan: SearchPlan
    executed_mode: str
    fallback: bool
    fallback_reason: str | None
    index_identity: dict[str, object]
    raw_hits: tuple[RawSearchHit, ...]
    timing: SearchTiming
    candidate_counts: dict[str, int]
    error: dict[str, object] | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "trace_id": self.trace_id,
            "trace_persisted": self.trace_persisted,
            "trace_error": self.trace_error,
            "plan": self.plan.as_dict(),
            "executed_mode": self.executed_mode,
            "fallback": self.fallback,
            "fallback_reason": self.fallback_reason,
            "index_identity": self.index_identity,
            "raw_hits": [item.as_dict() for item in self.raw_hits],
            "timing": self.timing.as_dict(),
            "candidate_counts": self.candidate_counts,
            "error": self.error,
        }


class SearchExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        stage: str,
        http_status: int,
        trace_id: str | None = None,
        trace_persisted: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.http_status = http_status
        self.trace_id = trace_id
        self.trace_persisted = trace_persisted

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "stage": self.stage,
            "message": str(self),
            "trace_id": self.trace_id,
            "trace_persisted": self.trace_persisted,
        }


class SearchOrchestrator:
    def __init__(
        self,
        *,
        db: Database,
        lexical: RetrievalService,
        dense_factory: Callable[[], PgExactDenseIndex],
        hybrid_factory: Callable[[], HybridRetrievalService],
        planner: SearchPlanner | None = None,
        persist_trace: bool = True,
    ) -> None:
        self.db = db
        self.lexical = lexical
        self._dense_factory = dense_factory
        self._hybrid_factory = hybrid_factory
        self.planner = planner or SearchPlanner()
        self.persist_trace = persist_trace

    def search(
        self,
        request: SearchRequest,
        *,
        video_ids: tuple[int, ...] | None = None,
        scope_video_ids: tuple[int, ...] | None = None,
    ) -> RawSearchResponse:
        trace_id = str(uuid4())
        started = time.monotonic()
        planning_started = time.monotonic()
        try:
            plan = self.planner.plan(request)
        except SearchValidationError as exc:
            total = _milliseconds(started)
            error = SearchExecutionError(
                str(exc),
                code="invalid_search_request",
                stage="planning",
                http_status=400,
                trace_id=trace_id,
            )
            if self.persist_trace:
                error.trace_persisted = self._persist_validation_error(
                    trace_id, request, error, total
                )
            raise error from exc
        planning_ms = _milliseconds(planning_started)
        if video_ids is not None and (
            len(video_ids) > 8 or any(value <= 0 for value in video_ids)
        ):
            raise ValueError("video_ids must contain at most 8 positive IDs")
        if scope_video_ids is not None and (
            video_ids or any(value <= 0 for value in scope_video_ids)
        ):
            raise ValueError("invalid scoped video_ids")
        filters = replace(
            request.filters.retrieval_filters(),
            video_ids=(
                tuple(dict.fromkeys(scope_video_ids))
                if scope_video_ids is not None
                else tuple(dict.fromkeys(video_ids))
                if video_ids is not None
                else None
            ),
        )
        include_ignored = request.filters.ignored
        executed_mode = plan.planned_mode
        fallback = False
        fallback_reason = None
        lexical_ms = dense_ms = fusion_ms = 0.0
        lexical_count = dense_count = 0
        try:
            if plan.planned_mode == "lexical":
                phase = time.monotonic()
                results: Sequence[
                    SearchResult | DenseSearchResult | HybridSearchResult
                ] = self.lexical.search(
                    plan.normalized_query,
                    level=plan.scope,
                    top_k=plan.raw_top_k,
                    filters=filters,
                    include_ignored=include_ignored,
                )
                lexical_ms = _milliseconds(phase)
                lexical_count = len(results)
            elif plan.planned_mode == "dense":
                phase = time.monotonic()
                results = self._dense_factory().search(
                    plan.normalized_query,
                    level=plan.scope,
                    top_k=plan.raw_top_k,
                    filters=filters,
                    include_ignored=include_ignored,
                )
                dense_ms = _milliseconds(phase)
                dense_count = len(results)
            else:
                try:
                    execution = self._hybrid_factory().search_with_trace(
                        plan.normalized_query,
                        level=plan.scope,
                        top_k=plan.raw_top_k,
                        filters=filters,
                        include_ignored=include_ignored,
                    )
                    results = execution.results
                    lexical_ms, dense_ms, fusion_ms = (
                        execution.lexical_ms,
                        execution.dense_ms,
                        execution.fusion_ms,
                    )
                    lexical_count, dense_count = (
                        execution.lexical_candidate_count,
                        execution.dense_candidate_count,
                    )
                except _APPROVED_DENSE_ERRORS as exc:
                    if not plan.fallback_allowed:
                        raise
                    executed_mode = "lexical"
                    fallback = True
                    fallback_reason = _dense_error(exc)[0]
                    phase = time.monotonic()
                    results = self.lexical.search(
                        plan.normalized_query,
                        level=plan.scope,
                        top_k=plan.raw_top_k,
                        filters=filters,
                        include_ignored=include_ignored,
                    )
                    lexical_ms = _milliseconds(phase)
                    lexical_count = len(results)
            hits = tuple(
                _raw_hit(result, rank) for rank, result in enumerate(results, 1)
            )
            identity = self._index_identity(executed_mode, plan.scope, plan.normalized_query)
            if fallback_reason:
                identity["degraded_reason"] = fallback_reason
            timing = SearchTiming(
                planning_ms=planning_ms,
                lexical_ms=lexical_ms,
                dense_ms=dense_ms,
                fusion_ms=fusion_ms,
                total_ms=_milliseconds(started),
            )
            candidate_counts = {"lexical": lexical_count, "dense": dense_count}
            response = RawSearchResponse(
                trace_id=trace_id,
                trace_persisted=False,
                trace_error=None,
                plan=plan,
                executed_mode=executed_mode,
                fallback=fallback,
                fallback_reason=fallback_reason,
                index_identity=identity,
                raw_hits=hits,
                timing=timing,
                candidate_counts=candidate_counts,
            )
            if self.persist_trace:
                try:
                    self._persist_trace(response, status="success")
                except Exception as exc:
                    return RawSearchResponse(
                        **{**response.__dict__, "trace_error": _bounded_error(exc)}
                    )
                return RawSearchResponse(
                    **{**response.__dict__, "trace_persisted": True}
                )
            return response
        except Exception as exc:
            mapped = _map_error(exc, trace_id=trace_id)
            identity = self._index_identity(executed_mode, plan.scope, plan.normalized_query)
            if fallback_reason:
                identity["degraded_reason"] = fallback_reason
            timing = SearchTiming(
                planning_ms=planning_ms,
                lexical_ms=lexical_ms,
                dense_ms=dense_ms,
                fusion_ms=fusion_ms,
                total_ms=_milliseconds(started),
            )
            empty = RawSearchResponse(
                trace_id=trace_id,
                trace_persisted=False,
                trace_error=None,
                plan=plan,
                executed_mode=executed_mode,
                fallback=fallback,
                fallback_reason=fallback_reason,
                index_identity=identity,
                raw_hits=(),
                timing=timing,
                candidate_counts={"lexical": lexical_count, "dense": dense_count},
                error={
                    "code": mapped.code,
                    "stage": mapped.stage,
                    "message": str(mapped),
                },
            )
            if self.persist_trace:
                try:
                    self._persist_trace(empty, status="error")
                    mapped.trace_persisted = True
                except Exception:
                    pass
            raise mapped from exc

    def search_raw(
        self,
        request: SearchRequest,
        *,
        video_ids: tuple[int, ...] | None = None,
        scope_video_ids: tuple[int, ...] | None = None,
    ) -> RawSearchResponse:
        """Named Stage 4A boundary used by post-retrieval product presentation."""
        if scope_video_ids is not None:
            return self.search(request, scope_video_ids=scope_video_ids)
        if video_ids is not None:
            return self.search(request, video_ids=video_ids)
        return self.search(request)

    def get_trace(self, trace_id):
        with self.db.connect(read_only=True) as c:
            row = c.execute(
                "SELECT * FROM shiliu.retrieval_search_traces WHERE workspace_id=%s AND trace_id=%s",
                (self.db.workspace_id, trace_id),
            ).fetchone()
        if row is None:
            return None
        result = collection_dto(row)
        result["filters"] = result.pop("filters_json")
        result["raw_hits"] = result.pop("raw_hits_json")
        return result

    def _index_identity(self, executed_mode, scope="all", query=""):
        from shiliu.retrieval.bm25 import RANKING_VERSION
        chunk_bm25 = scope == "transcript_chunk" and len(query) >= 3
        with self.db.connect(read_only=True) as c:
            row = c.execute(
                "SELECT p.* FROM shiliu.assistant_runtime_state s JOIN shiliu.embedding_profiles p ON p.profile_id=s.embedding_profile_id WHERE s.workspace_id=%s AND s.principal_id=%s AND s.embedding_domain='collection'",
                (self.db.workspace_id, self.db.context.user_id),
            ).fetchone()
            pending = c.execute(
                "SELECT COUNT(*) AS n FROM shiliu.retrieval_projection_tasks WHERE workspace_id=%s AND domain='collection' AND status!='completed'",
                (self.db.workspace_id,),
            ).fetchone()["n"]
        identity = row["identity"] if row else {}
        configured_dense = self._dense_factory()
        missing = (
            configured_dense.statistics()["index"]["missing_count"]
            if row and row["profile_id"] == configured_dense.profile_id
            else 0
        )
        return dict(
            storage_backend="postgresql+pgvector",
            lexical_profile=self.lexical.tokenizer.profile,
            embedding_profile=row["profile_id"] if row else None,
            degraded_reason="lexical_only"
            if row is None
            else "partial"
            if pending or missing
            else None,
            lexical_index_version=RANKING_VERSION if chunk_bm25 else INDEX_VERSION,
            dense_index_version=identity.get("dense_index_version"),
            model_id=identity.get("model_id"),
            model_revision=identity.get("model_revision"),
            provider_version=identity.get("provider_version"),
            projection_version=identity.get("projection_version"),
            query_instruction_version=(
                self._dense_factory().identity.query_instruction_version
                if row
                else None
            ),
            input_policy_version=identity.get("input_policy_version"),
            fusion_version=FUSION_VERSION if executed_mode == "hybrid" else None,
        )

    def _insert_trace(self, c, values):
        values = dict(values, workspace_id=self.db.workspace_id)
        c.execute(
            sql.SQL("INSERT INTO shiliu.retrieval_search_traces({}) VALUES({})").format(
                sql.SQL(",").join(map(sql.Identifier, values)),
                sql.SQL(",").join(sql.SQL("%s") for _ in values),
            ),
            list(values.values()),
        )

    def _persist_validation_error(self, trace_id, request, error, total_ms):
        try:
            with self.db.connect() as c:
                self._insert_trace(
                    c,
                    dict(
                        trace_id=trace_id,
                        trace_version=TRACE_VERSION,
                        created_at=_utc_now(),
                        raw_query=request.query,
                        requested_mode=request.mode,
                        scope=request.scope,
                        filters_json=Jsonb(
                            request.filters.model_dump(exclude_none=True)
                        ),
                        raw_top_k=request.raw_top_k,
                        total_ms=total_ms,
                        status="error",
                        error_code=error.code,
                        error_stage=error.stage,
                        error_message=str(error)[:500],
                        storage_backend="postgresql+pgvector",
                    ),
                )
            return True
        except Exception:
            return False

    def _persist_trace(self, response, *, status):
        p, i, t = response.plan, response.index_identity, response.timing
        e = response.error or {}
        values = dict(
            trace_id=response.trace_id,
            trace_version=TRACE_VERSION,
            created_at=_utc_now(),
            raw_query=p.raw_query,
            normalized_query=p.normalized_query,
            query_type=p.query_type,
            requested_mode=p.requested_mode,
            planned_mode=p.planned_mode,
            executed_mode=response.executed_mode,
            routing_reason=p.routing_reason,
            scope=p.scope,
            filters_json=Jsonb(p.validated_filters),
            raw_top_k=p.raw_top_k,
            lexical_candidate_count=response.candidate_counts["lexical"],
            dense_candidate_count=response.candidate_counts["dense"],
            raw_hit_count=len(response.raw_hits),
            planning_ms=t.planning_ms,
            lexical_ms=t.lexical_ms,
            dense_ms=t.dense_ms,
            fusion_ms=t.fusion_ms,
            total_ms=t.total_ms,
            fallback=response.fallback,
            fallback_reason=response.fallback_reason,
            status=status,
            error_code=e.get("code"),
            error_stage=e.get("stage"),
            error_message=str(e.get("message", ""))[:500] or None,
            raw_hits_json=Jsonb([h.trace_dict() for h in response.raw_hits]),
        )
        for key in [
            "lexical_index_version",
            "dense_index_version",
            "model_id",
            "model_revision",
            "provider_version",
            "projection_version",
            "query_instruction_version",
            "input_policy_version",
            "fusion_version",
            "storage_backend",
            "lexical_profile",
            "embedding_profile",
            "degraded_reason",
        ]:
            values[key] = i.get(key)
        if response.fallback_reason:
            values["degraded_reason"] = response.fallback_reason
        with self.db.connect() as c:
            self._insert_trace(c, values)


_APPROVED_DENSE_ERRORS = (
    DenseIndexNotReadyError,
    DenseIndexRebuildRequiredError,
    LocalModelNotReadyError,
)


def _raw_hit(
    result: SearchResult | DenseSearchResult | HybridSearchResult, rank: int
) -> RawSearchHit:
    if isinstance(result, HybridSearchResult):
        score = result.rrf_score
        lexical_rank, dense_rank = result.lexical_rank, result.dense_rank
        lexical_score, dense_score, rrf_score = (
            result.lexical_score,
            result.dense_score,
            result.rrf_score,
        )
    elif isinstance(result, DenseSearchResult):
        score = result.dense_score
        lexical_rank = lexical_score = rrf_score = None
        dense_rank, dense_score = rank, result.dense_score
    else:
        score = result.lexical_score
        dense_rank = dense_score = rrf_score = None
        lexical_rank, lexical_score = rank, result.lexical_score
    excerpt = result.matched_excerpt[:MAX_EXCERPT_CHARACTERS]
    return RawSearchHit(
        unit_id=result.unit_id,
        video_id=result.video_id,
        unit_type=result.unit_type,
        rank=rank,
        score=float(score),
        retrieval_method=result.retrieval_method,
        lexical_rank=lexical_rank,
        lexical_score=lexical_score,
        dense_rank=dense_rank,
        dense_score=dense_score,
        rrf_score=rrf_score,
        title=result.title,
        uploader=result.uploader,
        subtitle_source=result.source_type,
        start_time=result.start_time,
        end_time=result.end_time,
        excerpt=excerpt,
    )


def _map_error(exc: Exception, *, trace_id: str) -> SearchExecutionError:
    if isinstance(exc, SearchExecutionError):
        return exc
    code, status = _dense_error(exc)
    if code:
        return SearchExecutionError(
            str(exc), code=code, stage="dense", http_status=status, trace_id=trace_id
        )
    if isinstance(exc, StorageError) and exc.category.startswith("bm25_"):
        return SearchExecutionError(
            str(exc), code=exc.category, stage="lexical", http_status=503, trace_id=trace_id
        )
    if isinstance(exc, ValueError):
        return SearchExecutionError(
            str(exc),
            code="invalid_search_request",
            stage="retrieval",
            http_status=400,
            trace_id=trace_id,
        )
    return SearchExecutionError(
        f"{type(exc).__name__}: {exc}"[:500],
        code="retrieval_internal_error",
        stage="retrieval",
        http_status=500,
        trace_id=trace_id,
    )


def _dense_error(exc: Exception) -> tuple[str | None, int]:
    if isinstance(exc, DenseIndexNotReadyError):
        return "dense_not_ready", 503
    if isinstance(exc, DenseIndexRebuildRequiredError):
        return "dense_rebuild_required", 409
    if isinstance(exc, LocalModelNotReadyError):
        return "local_model_not_ready", 503
    return None, 500


def _bounded_error(exc: Exception) -> dict[str, str]:
    return {
        "code": "trace_persistence_failed",
        "message": f"{type(exc).__name__}: {exc}"[:500],
    }


def _milliseconds(started: float) -> float:
    return (time.monotonic() - started) * 1000


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
