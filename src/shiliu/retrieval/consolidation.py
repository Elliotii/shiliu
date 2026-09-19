from __future__ import annotations

from dataclasses import dataclass, field
import math

from shiliu.retrieval.orchestrator import RawSearchHit


TEMPORAL_MERGE_GAP_SECONDS = 20.0
CONSOLIDATION_VERSION = "v3-temporal-consolidation-v1"


@dataclass
class EvidenceWindowDraft:
    window_start: float
    window_end: float
    component_hits: list[RawSearchHit]
    best_hit: RawSearchHit
    excerpt: str = ""
    jump_time: float | None = None
    jump_source: str = "chunk_start_fallback"
    anchor_confidence: str = "fallback"
    anchor_segment_start: float | None = None
    anchor_segment_end: float | None = None
    matched_terms: tuple[str, ...] = ()
    chapter: dict[str, object] | None = None

    @property
    def component_chunk_ids(self) -> tuple[str, ...]:
        return tuple(hit.unit_id for hit in sorted(self.component_hits, key=_hit_key))

    @property
    def component_raw_ranks(self) -> tuple[int, ...]:
        return tuple(sorted({hit.rank for hit in self.component_hits}))

    @property
    def retrieval_methods(self) -> tuple[str, ...]:
        return _methods(self.component_hits)

    @property
    def subtitle_sources(self) -> tuple[str, ...]:
        return tuple(sorted({hit.subtitle_source for hit in self.component_hits}))

    def as_dict(self) -> dict[str, object]:
        return {
            "window_start": self.window_start,
            "window_end": self.window_end,
            "duration": self.window_end - self.window_start,
            "best_rank": self.best_hit.rank,
            "best_score": self.best_hit.score,
            "best_chunk_id": self.best_hit.unit_id,
            "component_chunk_ids": list(self.component_chunk_ids),
            "component_hit_count": len(self.component_hits),
            "component_raw_ranks": list(self.component_raw_ranks),
            "retrieval_methods": list(self.retrieval_methods),
            "subtitle_sources": list(self.subtitle_sources),
            "jump_time": self.jump_time,
            "jump_source": self.jump_source,
            "anchor_confidence": self.anchor_confidence,
            "anchor_segment_start": self.anchor_segment_start,
            "anchor_segment_end": self.anchor_segment_end,
            "matched_terms": list(self.matched_terms),
            "excerpt": self.excerpt,
            "chapter": self.chapter,
        }


@dataclass
class VideoResultGroupDraft:
    video_id: int
    hits: list[RawSearchHit]
    best_hit: RawSearchHit
    windows: list[EvidenceWindowDraft]
    unwindowed_chunk_count: int
    title: str
    uploader: str
    bvid: str = ""
    video_url: str = ""
    duration: float | None = None
    warnings: list[dict[str, str]] = field(default_factory=list)

    @property
    def retrieval_methods(self) -> tuple[str, ...]:
        return _methods(self.hits)


@dataclass(frozen=True)
class ConsolidationResult:
    groups: tuple[VideoResultGroupDraft, ...]
    duplicate_raw_hit_count: int
    unique_video_count: int
    total_window_count: int


class SearchResultConsolidator:
    def __init__(self, *, merge_gap_seconds: float = TEMPORAL_MERGE_GAP_SECONDS) -> None:
        self.merge_gap_seconds = merge_gap_seconds

    def consolidate(self, raw_hits: tuple[RawSearchHit, ...]) -> ConsolidationResult:
        deduplicated: dict[str, RawSearchHit] = {}
        for hit in raw_hits:
            current = deduplicated.get(hit.unit_id)
            if current is None or _hit_key(hit) < _hit_key(current):
                deduplicated[hit.unit_id] = hit
        ordered = sorted(deduplicated.values(), key=_hit_key)
        by_video: dict[int, list[RawSearchHit]] = {}
        for hit in ordered:
            by_video.setdefault(hit.video_id, []).append(hit)

        groups: list[VideoResultGroupDraft] = []
        for video_id, hits in by_video.items():
            best = min(hits, key=_hit_key)
            chunks = [hit for hit in hits if hit.unit_type == "transcript_chunk"]
            valid = [hit for hit in chunks if _valid_time(hit)]
            unwindowed = len(chunks) - len(valid)
            windows = self._windows(valid)
            groups.append(
                VideoResultGroupDraft(
                    video_id=video_id,
                    hits=hits,
                    best_hit=best,
                    windows=windows,
                    unwindowed_chunk_count=unwindowed,
                    title=best.title,
                    uploader=best.uploader,
                )
            )
        groups.sort(key=lambda item: (item.best_hit.rank, -item.best_hit.score, item.video_id))
        return ConsolidationResult(
            groups=tuple(groups),
            duplicate_raw_hit_count=len(raw_hits) - len(ordered),
            unique_video_count=len(groups),
            total_window_count=sum(len(group.windows) for group in groups),
        )

    def _windows(self, hits: list[RawSearchHit]) -> list[EvidenceWindowDraft]:
        hits.sort(key=lambda hit: (hit.start_time, hit.end_time, hit.rank, hit.unit_id))
        windows: list[EvidenceWindowDraft] = []
        for hit in hits:
            start, end = float(hit.start_time), float(hit.end_time)
            if windows and start <= windows[-1].window_end + self.merge_gap_seconds:
                window = windows[-1]
                window.window_end = max(window.window_end, end)
                window.component_hits.append(hit)
                window.best_hit = min(window.component_hits, key=_hit_key)
            else:
                windows.append(
                    EvidenceWindowDraft(
                        window_start=start,
                        window_end=end,
                        component_hits=[hit],
                        best_hit=hit,
                    )
                )
        windows.sort(
            key=lambda item: (
                item.best_hit.rank, -item.best_hit.score, item.window_start
            )
        )
        return windows


def _valid_time(hit: RawSearchHit) -> bool:
    return (
        isinstance(hit.start_time, (int, float))
        and not isinstance(hit.start_time, bool)
        and isinstance(hit.end_time, (int, float))
        and not isinstance(hit.end_time, bool)
        and math.isfinite(float(hit.start_time))
        and math.isfinite(float(hit.end_time))
        and 0 <= float(hit.start_time) <= float(hit.end_time)
    )


def _hit_key(hit: RawSearchHit) -> tuple[int, float, str]:
    return (hit.rank, -hit.score, hit.unit_id)


def _methods(hits: list[RawSearchHit]) -> tuple[str, ...]:
    values: set[str] = set()
    for hit in hits:
        if hit.lexical_rank is not None:
            values.add("lexical")
        if hit.dense_rank is not None:
            values.add("dense")
        if hit.lexical_rank is None and hit.dense_rank is None:
            values.add(hit.retrieval_method)
    return tuple(sorted(values))
