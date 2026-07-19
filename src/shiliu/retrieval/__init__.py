"""Product lexical retrieval for Shiliu V3.

Raw subtitle JSON segments are the only timestamp-authoritative source.  Product
identities never expose an FTS rowid: video unit IDs derive from canonical
platform identity, while chunk IDs hash the video identity, subtitle source,
boundaries, and complete chunk text.  Identical inputs therefore reproduce the
same IDs; changed boundaries or text change the chunk ID and content hash.
"""

from shiliu.retrieval.chunking import ChunkingConfig, build_raw_subtitle_chunks
from shiliu.retrieval.dense import FastEmbedEmbeddingProvider, SQLiteExactDenseIndex
from shiliu.retrieval.qwen import QwenEmbeddingProvider
from shiliu.retrieval.coordinator import RetrievalIndexCoordinator
from shiliu.retrieval.hybrid import HybridRetrievalService
from shiliu.retrieval.models import RetrievalFilters, SearchResult, SearchUnit
from shiliu.retrieval.orchestrator import SearchExecutionError, SearchOrchestrator
from shiliu.retrieval.planner import SearchFilterRequest, SearchPlanner, SearchRequest
from shiliu.retrieval.consolidation import SearchResultConsolidator
from shiliu.retrieval.enrichment import EvidenceEnricher
from shiliu.retrieval.product_search import (
    ProductSearchError,
    ProductSearchRequest,
    ProductSearchService,
)
from shiliu.retrieval.service import RetrievalService

__all__ = [
    "ChunkingConfig",
    "RetrievalFilters",
    "RetrievalService",
    "FastEmbedEmbeddingProvider",
    "QwenEmbeddingProvider",
    "SQLiteExactDenseIndex",
    "HybridRetrievalService",
    "SearchExecutionError",
    "SearchFilterRequest",
    "SearchOrchestrator",
    "SearchPlanner",
    "SearchRequest",
    "SearchResultConsolidator",
    "EvidenceEnricher",
    "ProductSearchError",
    "ProductSearchRequest",
    "ProductSearchService",
    "RetrievalIndexCoordinator",
    "SearchResult",
    "SearchUnit",
    "build_raw_subtitle_chunks",
]
