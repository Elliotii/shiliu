"""Deep V2 F1 retrieval and exact source materialization."""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import asdict, replace
from types import SimpleNamespace
from uuid import uuid4

from shiliu.ask.evidence import TranscriptEvidenceMaterializer, _reference
from shiliu.evidence.search import EvidenceSearchService, SearchExecution
from shiliu.evidence.source import load_source_artifact
from shiliu.retrieval.dense import PgExactDenseIndex, DenseIndexNotReadyError
from shiliu.retrieval.qwen import LocalModelNotReadyError
from psycopg.types.json import Jsonb
from shiliu.retrieval.f1 import F1LexicalIndex, dense_50, rrf_50
from shiliu.retrieval.service import RetrievalService
from shiliu.retrieval.product_search import (
    ProductSearchFilterRequest,
    ProductSearchRequest,
)


class F1Materializer(TranscriptEvidenceMaterializer):
    def __init__(self, db, artifacts, lexical):
        super().__init__(db, artifacts)
        self.lexical = lexical

    def _materialize_candidate(self, candidate, row, *, execution, query_index):
        scope = replace(
            execution.request.filters.retrieval_filters(), video_ids=execution.video_ids
        )
        where, parameters = self.lexical._search_filters(
            level="transcript_chunk", filters=scope, include_ignored=False
        )
        with self.db.connect() as connection:
            eligible = connection.execute(
                "SELECT 1 "
                + self.lexical.current_join()
                + "WHERE u.unit_id=%s AND "
                + where,
                [candidate.unit_id, *parameters],
            ).fetchone()
        if eligible is None:
            raise ValueError("source no longer eligible in immutable request scope")
        additions = []
        if any(
            right != left + 1
            for left, right in zip(
                candidate.segment_ordinals, candidate.segment_ordinals[1:]
            )
        ):
            artifact = load_source_artifact(
                _reference(row),
                expected_source_version=candidate.source_version,
                artifacts=self.artifacts,
            )
            by_id = {segment.segment_id: segment for segment in artifact.segments}
            core = [by_id[identity] for identity in candidate.segment_ids]
            if (
                tuple(segment.original_ordinal for segment in core)
                != candidate.segment_ordinals
            ):
                raise ValueError("core coordinate mismatch")
            if (artifact.source_artifact_id, artifact.source_version) != (
                candidate.source_artifact_id,
                candidate.source_version,
            ):
                raise ValueError("core source identity mismatch")
            selected = [
                segment
                for segment in artifact.segments
                if core[0].original_ordinal
                <= segment.original_ordinal
                <= core[-1].original_ordinal
            ]
            additions = [
                segment
                for segment in selected
                if segment.segment_id not in candidate.segment_ids
            ]
            if any(
                segment.source_text.strip()
                or segment.timeline_run_id != candidate.timeline_run_id
                for segment in additions
            ):
                raise ValueError("nonempty or cross timeline interior segment omitted")
            candidate = replace(
                candidate,
                segment_ids=tuple(segment.segment_id for segment in selected),
                segment_ordinals=tuple(
                    segment.original_ordinal for segment in selected
                ),
            )
        span = super()._materialize_candidate(
            candidate, row, execution=execution, query_index=query_index
        )
        if additions:
            span = span.model_copy(
                update={
                    "retrieval_provenance": (
                        *span.retrieval_provenance,
                        {
                            "kind": "empty_coordinate_continuity",
                            "original_ordinals": [
                                segment.original_ordinal for segment in additions
                            ],
                        },
                    )
                }
            )
        return span


class F1TranscriptTool:
    def __init__(
        self,
        search: EvidenceSearchService,
        embedding_provider,
        lexical: RetrievalService,
        materializer: F1Materializer | None = None,
    ) -> None:
        self.search_service = search
        self.db = search.db
        self.embedding_provider = embedding_provider
        self.lexical = F1LexicalIndex(lexical)
        self.dense = PgExactDenseIndex(
            db=self.db, provider=embedding_provider, lexical=lexical
        )
        self.materializer = materializer or F1Materializer(
            self.db, search.artifacts, lexical
        )

    def search(
        self,
        query: str,
        *,
        filters: ProductSearchFilterRequest,
        video_ids: tuple[int, ...] | None = None,
    ) -> dict:
        base = filters.retrieval_filters()
        if video_ids is not None and base.video_ids is not None:
            ids = tuple(sorted(set(video_ids) & set(base.video_ids)))
            if not ids:
                return {
                    "hits": [],
                    "spans": [],
                    "stale": [],
                    "index_identity": {},
                    "scope": asdict(base),
                    "empty_intersection": True,
                }
        else:
            ids = video_ids if video_ids is not None else base.video_ids
        scoped = replace(base, video_ids=ids)
        self.lexical.ensure_ready()
        degraded = None
        try:
            dense = dense_50(self.dense, query, scoped)
            if not self.dense.statistics()["index"]["ready"]:
                degraded = "partial"
        except (DenseIndexNotReadyError, LocalModelNotReadyError) as exc:
            dense = []
            degraded = type(exc).__name__
        lexical = self.lexical.search(query, filters=scoped)
        lexical_identity = self.lexical.validate_source()
        hits = rrf_50(dense, lexical)
        trace_id = "deep_v2_f1_" + uuid4().hex
        raw = SimpleNamespace(
            trace_id=trace_id,
            trace_persisted=False,
            trace_error=None,
            executed_mode="lexical" if degraded and not dense else "hybrid",
            raw_hits=tuple(hits),
            plan=SimpleNamespace(query_type="explicit_hybrid_no_planner"),
            fallback=bool(degraded),
            fallback_reason=degraded,
            index_identity={
                "storage_backend": "postgresql+pgvector",
                "lexical_profile": self.lexical.tokenizer.profile,
                "embedding_profile": self.dense.active_profile(),
                "degraded_reason": degraded,
                "dense": asdict(self.embedding_provider.model_identity()),
                "lexical": lexical_identity,
                "lexical_index_version": lexical_identity["index_version"],
                "corpus": self.search_service.runtime_corpus_identity,
            },
        )
        product = SimpleNamespace(
            results=(),
            trace_id=trace_id,
            trace_persisted=False,
            presentation_trace_persisted=False,
        )
        execution = SearchExecution(
            trace_id,
            ProductSearchRequest(
                query=query, mode="dense", scope="transcript_chunk", filters=filters
            ),
            raw,
            product,
            ids,
        )
        with self.db.connect() as connection:
            connection.execute(
                """INSERT INTO retrieval_search_traces
                (workspace_id,trace_id,trace_version,created_at,raw_query,requested_mode,executed_mode,
                 scope,filters_json,raw_top_k,lexical_candidate_count,dense_candidate_count,
                 raw_hit_count,status,raw_hits_json,storage_backend,lexical_profile,embedding_profile,degraded_reason,lexical_index_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    self.db.workspace_id,
                    trace_id,
                    "deep-v2-f1",
                    datetime.now(timezone.utc).isoformat(),
                    query,
                    "hybrid",
                    raw.executed_mode,
                    "transcript_chunk",
                    Jsonb(asdict(scoped)),
                    50,
                    len(lexical),
                    len(dense),
                    len(hits),
                    "complete",
                    Jsonb(
                        [
                            {
                                **hit.trace_dict(),
                                "video_id": hit.video_id,
                                "start_time": hit.start_time,
                                "end_time": hit.end_time,
                            }
                            for hit in hits
                        ]
                    ),
                    "postgresql+pgvector",
                    self.lexical.tokenizer.profile,
                    self.dense.active_profile(),
                    degraded,
                    lexical_identity["index_version"],
                ),
            )
        raw.trace_persisted = True
        candidates = self.search_service.materialize_execution(execution)
        materialized = self.materializer.materialize(
            execution, candidates, query_index=0
        )
        return {
            "hits": hits,
            "spans": materialized.spans,
            "stale": materialized.stale_reasons,
            "index_identity": raw.index_identity,
            "scope": asdict(scoped),
            "trace_id": trace_id,
            "available": len(materialized.spans),
            "raw_count": len(hits),
            "search_executions": [
                {
                    "execution_id": trace_id,
                    "search_trace_id": trace_id,
                    "trace_persisted": True,
                    "query": query,
                }
            ],
        }
