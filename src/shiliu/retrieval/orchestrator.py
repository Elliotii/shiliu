from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import sqlite3
import time
from typing import Callable, Sequence
from uuid import uuid4

from shiliu.db import Database
from shiliu.retrieval.dense import (
    DenseIndexNotReadyError,
    DenseIndexRebuildRequiredError,
    SQLiteExactDenseIndex,
)
from shiliu.retrieval.hybrid import FUSION_VERSION, HybridExecution, HybridRetrievalService
from shiliu.retrieval.models import DenseSearchResult, HybridSearchResult, SearchResult
from shiliu.retrieval.planner import SearchPlan, SearchPlanner, SearchRequest, SearchValidationError
from shiliu.retrieval.qwen import LocalModelNotReadyError
from shiliu.retrieval.service import INDEX_NAME, RetrievalService


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
                "unit_id", "rank", "score", "lexical_rank", "lexical_score",
                "dense_rank", "dense_score", "rrf_score",
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
        self, message: str, *, code: str, stage: str, http_status: int,
        trace_id: str | None = None, trace_persisted: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.http_status = http_status
        self.trace_id = trace_id
        self.trace_persisted = trace_persisted

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code, "stage": self.stage, "message": str(self),
            "trace_id": self.trace_id, "trace_persisted": self.trace_persisted,
        }


class SearchOrchestrator:
    def __init__(
        self, *, db: Database, lexical: RetrievalService,
        dense_factory: Callable[[], SQLiteExactDenseIndex],
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
        if self.persist_trace:
            self.initialize_schema()

    def initialize_schema(self) -> None:
        with self.db.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS retrieval_search_traces (
                    trace_id TEXT PRIMARY KEY,
                    trace_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    raw_query TEXT NOT NULL,
                    normalized_query TEXT,
                    query_type TEXT,
                    requested_mode TEXT NOT NULL,
                    planned_mode TEXT,
                    executed_mode TEXT,
                    routing_reason TEXT,
                    scope TEXT NOT NULL,
                    filters_json TEXT NOT NULL,
                    raw_top_k INTEGER NOT NULL,
                    lexical_candidate_count INTEGER NOT NULL DEFAULT 0,
                    dense_candidate_count INTEGER NOT NULL DEFAULT 0,
                    raw_hit_count INTEGER NOT NULL DEFAULT 0,
                    planning_ms REAL NOT NULL DEFAULT 0,
                    lexical_ms REAL NOT NULL DEFAULT 0,
                    dense_ms REAL NOT NULL DEFAULT 0,
                    fusion_ms REAL NOT NULL DEFAULT 0,
                    total_ms REAL NOT NULL DEFAULT 0,
                    lexical_index_version TEXT,
                    dense_index_version TEXT,
                    model_id TEXT,
                    model_revision TEXT,
                    provider_version TEXT,
                    projection_version TEXT,
                    query_instruction_version TEXT,
                    input_policy_version TEXT,
                    fusion_version TEXT,
                    fallback INTEGER NOT NULL DEFAULT 0,
                    fallback_reason TEXT,
                    status TEXT NOT NULL,
                    error_code TEXT,
                    error_stage TEXT,
                    error_message TEXT,
                    raw_hits_json TEXT NOT NULL DEFAULT '[]'
                );
                CREATE INDEX IF NOT EXISTS idx_retrieval_search_traces_created
                    ON retrieval_search_traces(created_at DESC, trace_id);
                """
            )

    def search(self, request: SearchRequest) -> RawSearchResponse:
        trace_id = str(uuid4())
        started = time.monotonic()
        planning_started = time.monotonic()
        try:
            plan = self.planner.plan(request)
        except SearchValidationError as exc:
            total = _milliseconds(started)
            error = SearchExecutionError(
                str(exc), code="invalid_search_request", stage="planning",
                http_status=400, trace_id=trace_id,
            )
            if self.persist_trace:
                error.trace_persisted = self._persist_validation_error(
                    trace_id, request, error, total
                )
            raise error from exc
        planning_ms = _milliseconds(planning_started)
        filters = request.filters.retrieval_filters()
        include_ignored = request.filters.ignored
        executed_mode = plan.planned_mode
        fallback = False
        fallback_reason = None
        lexical_ms = dense_ms = fusion_ms = 0.0
        lexical_count = dense_count = 0
        try:
            if plan.planned_mode == "lexical":
                phase = time.monotonic()
                results: Sequence[SearchResult | DenseSearchResult | HybridSearchResult] = (
                    self.lexical.search(
                        plan.normalized_query, level=plan.scope,
                        top_k=plan.raw_top_k, filters=filters,
                        include_ignored=include_ignored,
                    )
                )
                lexical_ms = _milliseconds(phase)
                lexical_count = len(results)
            elif plan.planned_mode == "dense":
                phase = time.monotonic()
                results = self._dense_factory().search(
                    plan.normalized_query, level=plan.scope,
                    top_k=plan.raw_top_k, filters=filters,
                    include_ignored=include_ignored,
                )
                dense_ms = _milliseconds(phase)
                dense_count = len(results)
            else:
                try:
                    execution = self._hybrid_factory().search_with_trace(
                        plan.normalized_query, level=plan.scope,
                        top_k=plan.raw_top_k, filters=filters,
                        include_ignored=include_ignored,
                    )
                    results = execution.results
                    lexical_ms, dense_ms, fusion_ms = (
                        execution.lexical_ms, execution.dense_ms, execution.fusion_ms
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
                        plan.normalized_query, level=plan.scope,
                        top_k=plan.raw_top_k, filters=filters,
                        include_ignored=include_ignored,
                    )
                    lexical_ms = _milliseconds(phase)
                    lexical_count = len(results)
            hits = tuple(_raw_hit(result, rank) for rank, result in enumerate(results, 1))
            identity = self._index_identity(executed_mode)
            timing = SearchTiming(
                planning_ms=planning_ms, lexical_ms=lexical_ms, dense_ms=dense_ms,
                fusion_ms=fusion_ms, total_ms=_milliseconds(started),
            )
            candidate_counts = {"lexical": lexical_count, "dense": dense_count}
            response = RawSearchResponse(
                trace_id=trace_id, trace_persisted=False, trace_error=None,
                plan=plan, executed_mode=executed_mode, fallback=fallback,
                fallback_reason=fallback_reason, index_identity=identity,
                raw_hits=hits, timing=timing, candidate_counts=candidate_counts,
            )
            if self.persist_trace:
                try:
                    self._persist_trace(response, status="success")
                except Exception as exc:
                    return RawSearchResponse(
                        **{**response.__dict__, "trace_error": _bounded_error(exc)}
                    )
                return RawSearchResponse(**{**response.__dict__, "trace_persisted": True})
            return response
        except Exception as exc:
            mapped = _map_error(exc, trace_id=trace_id)
            identity = self._index_identity(executed_mode)
            timing = SearchTiming(
                planning_ms=planning_ms, lexical_ms=lexical_ms, dense_ms=dense_ms,
                fusion_ms=fusion_ms, total_ms=_milliseconds(started),
            )
            empty = RawSearchResponse(
                trace_id=trace_id, trace_persisted=False, trace_error=None,
                plan=plan, executed_mode=executed_mode, fallback=fallback,
                fallback_reason=fallback_reason, index_identity=identity,
                raw_hits=(), timing=timing,
                candidate_counts={"lexical": lexical_count, "dense": dense_count},
                error={"code": mapped.code, "stage": mapped.stage, "message": str(mapped)},
            )
            if self.persist_trace:
                try:
                    self._persist_trace(empty, status="error")
                    mapped.trace_persisted = True
                except Exception:
                    pass
            raise mapped from exc

    def search_raw(self, request: SearchRequest) -> RawSearchResponse:
        """Named Stage 4A boundary used by post-retrieval product presentation."""
        return self.search(request)

    def get_trace(self, trace_id: str) -> dict[str, object] | None:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM retrieval_search_traces WHERE trace_id=?", (trace_id,)
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["filters"] = json.loads(str(result.pop("filters_json")))
        result["raw_hits"] = json.loads(str(result.pop("raw_hits_json")))
        result["fallback"] = bool(result["fallback"])
        return result

    def _index_identity(self, executed_mode: str) -> dict[str, object]:
        with self.db.connect() as connection:
            lexical = connection.execute(
                "SELECT * FROM retrieval_index_meta WHERE index_name=?", (INDEX_NAME,)
            ).fetchone()
            dense_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='retrieval_dense_index_meta'"
            ).fetchone()
            dense = (
                connection.execute(
                    "SELECT * FROM retrieval_dense_index_meta "
                    "WHERE index_name='shiliu_dense'"
                ).fetchone()
                if dense_table is not None
                else None
            )
        result: dict[str, object] = {
            "lexical_index_version": str(lexical["index_version"]) if lexical else None,
            "dense_index_version": str(dense["dense_index_version"]) if dense else None,
            "model_id": str(dense["model_id"]) if dense else None,
            "model_revision": str(dense["model_revision"]) if dense else None,
            "provider_version": str(dense["provider_version"]) if dense else None,
            "projection_version": str(dense["projection_version"]) if dense else None,
            "query_instruction_version": str(dense["query_instruction_version"]) if dense else None,
            "input_policy_version": str(dense["input_policy_version"]) if dense else None,
            "fusion_version": FUSION_VERSION if executed_mode == "hybrid" else None,
        }
        return result

    def _persist_validation_error(
        self, trace_id: str, request: SearchRequest,
        error: SearchExecutionError, total_ms: float,
    ) -> bool:
        try:
            with self.db.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO retrieval_search_traces(
                      trace_id,trace_version,created_at,raw_query,requested_mode,
                      scope,filters_json,raw_top_k,total_ms,status,error_code,
                      error_stage,error_message
                    ) VALUES(?,?,?,?,?,?,?,?,?,'error',?,?,?)
                    """,
                    (trace_id, TRACE_VERSION, _utc_now(), request.query, request.mode,
                     request.scope, request.filters.model_dump_json(exclude_none=True),
                     request.raw_top_k, total_ms, error.code, error.stage,
                     str(error)[:500]),
                )
            return True
        except Exception:
            return False

    def _persist_trace(self, response: RawSearchResponse, *, status: str) -> None:
        plan, identity, timing = response.plan, response.index_identity, response.timing
        error = response.error or {}
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO retrieval_search_traces VALUES(
                  ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                )
                """,
                (
                    response.trace_id, TRACE_VERSION, _utc_now(), plan.raw_query,
                    plan.normalized_query, plan.query_type, plan.requested_mode,
                    plan.planned_mode, response.executed_mode, plan.routing_reason,
                    plan.scope, json.dumps(plan.validated_filters, ensure_ascii=False),
                    plan.raw_top_k, response.candidate_counts["lexical"],
                    response.candidate_counts["dense"], len(response.raw_hits),
                    timing.planning_ms, timing.lexical_ms, timing.dense_ms,
                    timing.fusion_ms, timing.total_ms,
                    identity.get("lexical_index_version"),
                    identity.get("dense_index_version"), identity.get("model_id"),
                    identity.get("model_revision"), identity.get("provider_version"),
                    identity.get("projection_version"),
                    identity.get("query_instruction_version"),
                    identity.get("input_policy_version"), identity.get("fusion_version"),
                    int(response.fallback), response.fallback_reason, status,
                    error.get("code"), error.get("stage"),
                    str(error.get("message", ""))[:500] or None,
                    json.dumps([item.trace_dict() for item in response.raw_hits]),
                ),
            )


_APPROVED_DENSE_ERRORS = (
    DenseIndexNotReadyError, DenseIndexRebuildRequiredError, LocalModelNotReadyError,
)


def _raw_hit(
    result: SearchResult | DenseSearchResult | HybridSearchResult, rank: int
) -> RawSearchHit:
    if isinstance(result, HybridSearchResult):
        score = result.rrf_score
        lexical_rank, dense_rank = result.lexical_rank, result.dense_rank
        lexical_score, dense_score, rrf_score = (
            result.lexical_score, result.dense_score, result.rrf_score
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
        unit_id=result.unit_id, video_id=result.video_id, unit_type=result.unit_type,
        rank=rank, score=float(score), retrieval_method=result.retrieval_method,
        lexical_rank=lexical_rank, lexical_score=lexical_score,
        dense_rank=dense_rank, dense_score=dense_score, rrf_score=rrf_score,
        title=result.title, uploader=result.uploader,
        subtitle_source=result.source_type,
        start_time=result.start_time, end_time=result.end_time, excerpt=excerpt,
    )


def _map_error(exc: Exception, *, trace_id: str) -> SearchExecutionError:
    if isinstance(exc, SearchExecutionError):
        return exc
    code, status = _dense_error(exc)
    if code:
        return SearchExecutionError(
            str(exc), code=code, stage="dense", http_status=status, trace_id=trace_id
        )
    if isinstance(exc, ValueError):
        return SearchExecutionError(
            str(exc), code="invalid_search_request", stage="retrieval",
            http_status=400, trace_id=trace_id,
        )
    return SearchExecutionError(
        f"{type(exc).__name__}: {exc}"[:500], code="retrieval_internal_error",
        stage="retrieval", http_status=500, trace_id=trace_id,
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
    return {"code": "trace_persistence_failed", "message": f"{type(exc).__name__}: {exc}"[:500]}


def _milliseconds(started: float) -> float:
    return (time.monotonic() - started) * 1000


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
