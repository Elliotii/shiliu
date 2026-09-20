from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from shiliu.ask.contracts import TranscriptEvidenceSpan
from shiliu.ask.deep.contracts import NavigationDocument
from shiliu.ask.deep.navigation import NavigationService
from shiliu.ask.deep.transcript import TranscriptSearchService, TranscriptWindowReader
from shiliu.ask.evidence import MaterializationResult
from shiliu.retrieval.product_search import ProductSearchFilterRequest


class InnerToolAdapter(Protocol):
    def navigate(self, query: str) -> tuple[NavigationDocument, ...]: ...

    def search(
        self,
        query: str,
        *,
        video_ids: tuple[int, ...],
        query_index: int,
    ) -> MaterializationResult: ...

    def read_window(self, span: TranscriptEvidenceSpan) -> TranscriptEvidenceSpan: ...


class LocalInnerToolAdapter:
    """Local retrieval/evidence wiring. It never invokes an LLM Provider."""

    def __init__(
        self,
        *,
        navigation: NavigationService,
        transcripts: TranscriptSearchService,
        windows: TranscriptWindowReader,
    ) -> None:
        self.navigation = navigation
        self.transcripts = transcripts
        self.windows = windows

    def navigate(self, query: str) -> tuple[NavigationDocument, ...]:
        return tuple(
            self.navigation.search(
                query,
                filters=ProductSearchFilterRequest(),
                limit=8,
            )
        )

    def search(
        self,
        query: str,
        *,
        video_ids: tuple[int, ...],
        query_index: int,
    ) -> MaterializationResult:
        return self.transcripts.search(
            query,
            filters=ProductSearchFilterRequest(),
            video_ids=video_ids,
            query_index=query_index,
        )

    def read_window(self, span: TranscriptEvidenceSpan) -> TranscriptEvidenceSpan:
        if not span.segment_ids:
            raise ValueError("window source span has no segment identity")
        anchor = span.segment_ids[len(span.segment_ids) // 2]
        return self.windows.read(
            video_id=span.video_id,
            anchor_segment_id=anchor,
            before=2,
            after=2,
        ).span


@dataclass
class DeterministicInnerToolAdapter:
    """Scriptable no-network adapter for deterministic product and fault tests."""

    navigation_documents: tuple[NavigationDocument, ...] = ()
    search_spans: tuple[TranscriptEvidenceSpan, ...] = ()
    window_span: TranscriptEvidenceSpan | None = None
    stale_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def navigate(self, query: str) -> tuple[NavigationDocument, ...]:
        self.calls.append({"kind": "navigation", "query": query})
        return self.navigation_documents

    def search(
        self,
        query: str,
        *,
        video_ids: tuple[int, ...],
        query_index: int,
    ) -> MaterializationResult:
        self.calls.append(
            {
                "kind": "transcript_search",
                "query": query,
                "video_ids": list(video_ids),
                "query_index": query_index,
            }
        )
        return MaterializationResult(
            spans=self.search_spans,
            stale_reasons=self.stale_reasons,
        )

    def read_window(self, span: TranscriptEvidenceSpan) -> TranscriptEvidenceSpan:
        self.calls.append(
            {
                "kind": "transcript_window",
                "citation_id": span.citation_id,
            }
        )
        return self.window_span or span
