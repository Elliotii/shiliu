from __future__ import annotations

from dataclasses import dataclass
import time

from shiliu.retrieval.dense import SQLiteExactDenseIndex
from shiliu.retrieval.models import HybridSearchResult, RetrievalFilters, SearchLevel
from shiliu.retrieval.service import RetrievalService


FUSION_VERSION = "v3-stage2-rrf-v1"


@dataclass(frozen=True)
class HybridExecution:
    results: list[HybridSearchResult]
    lexical_candidate_count: int
    dense_candidate_count: int
    lexical_ms: float
    dense_ms: float
    fusion_ms: float


class HybridRetrievalService:
    def __init__(self, *, lexical: RetrievalService, dense: SQLiteExactDenseIndex) -> None:
        self.lexical = lexical
        self.dense = dense

    def search(self, query: str, *, level: SearchLevel = "all", top_k: int = 10,
               filters: RetrievalFilters | None = None, include_ignored: bool = False,
               rrf_k: int = 60, candidate_k: int | None = None) -> list[HybridSearchResult]:
        return self.search_with_trace(
            query, level=level, top_k=top_k, filters=filters,
            include_ignored=include_ignored, rrf_k=rrf_k, candidate_k=candidate_k,
        ).results

    def search_with_trace(self, query: str, *, level: SearchLevel = "all", top_k: int = 10,
               filters: RetrievalFilters | None = None, include_ignored: bool = False,
               rrf_k: int = 60, candidate_k: int | None = None) -> HybridExecution:
        if rrf_k <= 0:
            raise ValueError("rrf_k must be positive")
        if not 1 <= top_k <= 100:
            raise ValueError("top_k must be between 1 and 100")
        candidates = candidate_k or max(50, top_k * 5)
        if candidates < top_k or candidates > 500:
            raise ValueError("candidate_k must be between top_k and 500")
        started = time.monotonic()
        lexical = self.lexical.search(query, level=level, top_k=candidates, filters=filters, include_ignored=include_ignored)
        lexical_ms = (time.monotonic() - started) * 1000
        started = time.monotonic()
        dense = self.dense.search(query, level=level, top_k=candidates, filters=filters, include_ignored=include_ignored)
        dense_ms = (time.monotonic() - started) * 1000
        started = time.monotonic()
        lexical_by_id = {item.unit_id: (rank, item) for rank, item in enumerate(lexical, 1)}
        dense_by_id = {item.unit_id: (rank, item) for rank, item in enumerate(dense, 1)}
        meta = self.dense.statistics()["index"]
        merged: list[HybridSearchResult] = []
        for unit_id in lexical_by_id.keys() | dense_by_id.keys():
            lexical_pair = lexical_by_id.get(unit_id)
            dense_pair = dense_by_id.get(unit_id)
            source = dense_pair[1] if dense_pair else lexical_pair[1]
            lr = lexical_pair[0] if lexical_pair else None
            dr = dense_pair[0] if dense_pair else None
            score = (1 / (rrf_k + lr) if lr else 0.0) + (1 / (rrf_k + dr) if dr else 0.0)
            merged.append(HybridSearchResult(
                unit_id=source.unit_id, unit_type=source.unit_type, video_id=source.video_id,
                platform=source.platform, source_id=source.source_id, part=source.part, title=source.title,
                uploader=source.uploader, chunk_id=source.chunk_id, source_type=source.source_type,
                start_time=source.start_time, end_time=source.end_time, matched_excerpt=source.matched_excerpt,
                lexical_score=lexical_pair[1].lexical_score if lexical_pair else None,
                dense_score=dense_pair[1].dense_score if dense_pair else None,
                lexical_rank=lr, dense_rank=dr, rrf_score=score, retrieval_method="hybrid",
                lexical_retrieval_method=lexical_pair[1].retrieval_method if lexical_pair else None,
                fusion_version=FUSION_VERSION, index_version=FUSION_VERSION,
                lexical_index_version=source.index_version,
                dense_index_version=meta["dense_index_version"],
                model_id=self.dense.provider.model_id, projection_version=meta["projection_version"],
                reading_state=source.reading_state, is_marked=source.is_marked, is_ignored=source.is_ignored,
                archived=source.archived, folders=source.folders,
            ))
        merged.sort(key=_hybrid_sort_key)
        fusion_ms = (time.monotonic() - started) * 1000
        return HybridExecution(
            results=merged[:top_k], lexical_candidate_count=len(lexical),
            dense_candidate_count=len(dense), lexical_ms=lexical_ms,
            dense_ms=dense_ms, fusion_ms=fusion_ms,
        )


def _hybrid_sort_key(item: HybridSearchResult) -> tuple[float, int, str]:
    available = [
        rank for rank in (item.lexical_rank, item.dense_rank) if rank is not None
    ]
    return (-item.rrf_score, min(available), item.unit_id)
