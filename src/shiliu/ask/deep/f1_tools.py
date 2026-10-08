"""Deep V2 F1 retrieval and exact source materialization."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from shiliu.ask.evidence import TranscriptEvidenceMaterializer, _reference
from shiliu.evidence.search import EvidenceSearchService, SearchExecution
from shiliu.evidence.source import load_source_artifact
from shiliu.retrieval.dense import SQLiteExactDenseIndex
from shiliu.retrieval.f1 import F1LexicalIndex, dense_50, rrf_50
from shiliu.retrieval.models import RetrievalFilters
from shiliu.retrieval.service import RetrievalService
from shiliu.retrieval.product_search import ProductSearchFilterRequest, ProductSearchRequest


class F1Materializer(TranscriptEvidenceMaterializer):
    def _materialize_candidate(self, candidate, row, *, execution, query_index):
        scope = replace(execution.request.filters.retrieval_filters(), video_ids=execution.video_ids)
        where, parameters = RetrievalService._search_filters(
            level="transcript_chunk", filters=scope, include_ignored=False)
        with self.db.connect() as connection:
            eligible = connection.execute(
                "SELECT 1 FROM retrieval_units u JOIN videos v ON v.id=u.video_id "
                "WHERE u.unit_id=? AND v.removed_at IS NULL AND v.is_ignored=0 AND " + where,
                [candidate.unit_id, *parameters]).fetchone()
        if eligible is None:
            raise ValueError("source no longer eligible in immutable request scope")
        additions = []
        if any(right != left + 1 for left, right in zip(candidate.segment_ordinals, candidate.segment_ordinals[1:])):
            artifact = load_source_artifact(_reference(row), expected_source_version=candidate.source_version)
            by_id = {segment.segment_id: segment for segment in artifact.segments}
            core = [by_id[identity] for identity in candidate.segment_ids]
            if tuple(segment.original_ordinal for segment in core) != candidate.segment_ordinals:
                raise ValueError("core coordinate mismatch")
            if (artifact.source_artifact_id, artifact.source_version) != (candidate.source_artifact_id, candidate.source_version):
                raise ValueError("core source identity mismatch")
            selected = [segment for segment in artifact.segments if core[0].original_ordinal <= segment.original_ordinal <= core[-1].original_ordinal]
            additions = [segment for segment in selected if segment.segment_id not in candidate.segment_ids]
            if any(segment.source_text.strip() or segment.timeline_run_id != candidate.timeline_run_id for segment in additions):
                raise ValueError("nonempty or cross timeline interior segment omitted")
            candidate = replace(candidate, segment_ids=tuple(segment.segment_id for segment in selected),
                                segment_ordinals=tuple(segment.original_ordinal for segment in selected))
        span = super()._materialize_candidate(candidate, row, execution=execution, query_index=query_index)
        if additions:
            span = span.model_copy(update={"retrieval_provenance": (*span.retrieval_provenance,
                {"kind": "empty_coordinate_continuity", "original_ordinals": [segment.original_ordinal for segment in additions]})})
        return span


class F1TranscriptTool:
    def __init__(self, search: EvidenceSearchService, embedding_provider, lexical_path: Path,
                 materializer: F1Materializer | None = None) -> None:
        self.search_service = search
        self.db = search.db
        self.embedding_provider = embedding_provider
        self.lexical = F1LexicalIndex(lexical_path, self.db.path)
        self.dense = SQLiteExactDenseIndex(db=self.db, provider=embedding_provider)
        self.materializer = materializer or F1Materializer(self.db)

    def search(self, query: str, *, filters: ProductSearchFilterRequest,
               video_ids: tuple[int, ...] = ()) -> dict:
        base = filters.retrieval_filters()
        if video_ids and base.video_ids:
            ids = tuple(sorted(set(video_ids) & set(base.video_ids)))
            if not ids:
                return {"hits": [], "spans": [], "stale": [], "index_identity": {}, "scope": asdict(base), "empty_intersection": True}
        else:
            ids = video_ids or base.video_ids
        scoped = replace(base, video_ids=ids)
        dense = dense_50(self.dense, query, scoped)
        lexical = self.lexical.search(query, filters=scoped)
        lexical_identity = self.lexical.validate_source()
        hits = rrf_50(dense, lexical)
        trace_id = "deep_v2_f1_" + uuid4().hex
        raw = SimpleNamespace(trace_id=trace_id, trace_persisted=False, trace_error=None,
            executed_mode="hybrid", raw_hits=tuple(hits), plan=SimpleNamespace(query_type="explicit_hybrid_no_planner"),
            fallback=False, fallback_reason=None, index_identity={"dense": asdict(self.embedding_provider.model_identity()),
                "lexical": lexical_identity, "corpus": self.search_service.runtime_corpus_identity})
        product = SimpleNamespace(results=(), trace_id=trace_id, trace_persisted=False,
                                  presentation_trace_persisted=False)
        execution = SearchExecution(trace_id, ProductSearchRequest(query=query, mode="dense", scope="transcript_chunk",
            filters=filters), raw, product, ids)
        with self.db.connect() as connection:
            connection.execute("""INSERT INTO retrieval_search_traces
                (trace_id,trace_version,created_at,raw_query,requested_mode,executed_mode,
                 scope,filters_json,raw_top_k,lexical_candidate_count,dense_candidate_count,
                 raw_hit_count,status,raw_hits_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (trace_id, "deep-v2-f1", datetime.now(timezone.utc).isoformat(), query,
                 "hybrid", "hybrid", "transcript_chunk", json.dumps(asdict(scoped)),
                 50, len(lexical), len(dense), len(hits), "complete",
                 json.dumps([hit.trace_dict() for hit in hits], ensure_ascii=False)))
        raw.trace_persisted = True
        candidates = self.search_service.materialize_execution(execution)
        materialized = self.materializer.materialize(execution, candidates, query_index=0)
        return {"hits": hits, "spans": materialized.spans, "stale": materialized.stale_reasons,
                "index_identity": raw.index_identity, "scope": asdict(scoped), "trace_id": trace_id,
                "available": len(materialized.spans), "raw_count": len(hits),
                "search_executions": [{"execution_id": trace_id, "search_trace_id": trace_id,
                                       "trace_persisted": True, "query": query}]}
