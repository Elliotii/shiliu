from __future__ import annotations

from dataclasses import dataclass
import json
import re
import time
import unicodedata
from pathlib import Path

from pydantic import ValidationError

from shiliu.artifacts import ArtifactStore
from shiliu.db import Database
from shiliu.domain import ImportantChapter, SubtitleSegment
from shiliu.retrieval.consolidation import EvidenceWindowDraft, VideoResultGroupDraft


JUMP_ANCHOR_VERSION = "v3-query-aware-anchor-v1"
CHAPTER_ENRICHMENT_VERSION = "v3-ai-chapter-enrichment-v1"
MAX_EXCERPT_CHARACTERS = 300
MAX_CHAPTER_SUMMARY_CHARACTERS = 240

_ASCII_TOKEN_PATTERN = (
    r"(?:\.[A-Za-z][A-Za-z0-9]*|"
    r"[A-Za-z][A-Za-z0-9]*(?:(?:[._:/+\-][A-Za-z0-9]+)|\+\+|#)*)"
)
_ASCII_TERM = re.compile(_ASCII_TOKEN_PATTERN)
_ASCII_SPAN = re.compile(
    rf"{_ASCII_TOKEN_PATTERN}(?:\s+{_ASCII_TOKEN_PATTERN})+"
)
_CJK_TERM = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]{2,}")
_STOPWORDS = {
    "的", "了", "和", "与", "是", "在", "如何", "怎么", "怎样", "为什么",
    "what", "how", "why", "the", "a", "an",
}


@dataclass(frozen=True)
class EnrichmentResult:
    anchor_ms: float
    chapter_ms: float
    warnings: tuple[dict[str, object], ...]
    anchored_window_count: int
    chapter_enriched_count: int


@dataclass(frozen=True)
class _Chapter:
    title: str
    summary: str
    start: float
    end: float | None
    boundary_type: str

    def as_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "summary": self.summary[:MAX_CHAPTER_SUMMARY_CHARACTERS],
            "start_time": self.start,
            "derived_end_time": self.end,
            "source": "ai_summary",
            "boundary_type": self.boundary_type,
        }


class EvidenceEnricher:
    def __init__(self, *, db: Database, artifacts: ArtifactStore) -> None:
        self.db = db
        self.artifacts = artifacts

    def enrich(
        self,
        groups: tuple[VideoResultGroupDraft, ...],
        *,
        normalized_query: str,
        query_type: str,
    ) -> EnrichmentResult:
        warnings: list[dict[str, object]] = []
        subtitle_cache: dict[int, list[SubtitleSegment] | None] = {}
        chapter_cache: dict[int, list[_Chapter] | None] = {}
        videos: dict[int, dict[str, object] | None] = {}

        anchor_started = time.monotonic()
        anchored = 0
        for group in groups:
            video = videos.setdefault(group.video_id, self.db.get_video(group.video_id))
            self._canonical_metadata(group, video)
            segments = subtitle_cache.setdefault(
                group.video_id,
                self._load_segments(video, group.video_id, warnings),
            )
            for window in group.windows:
                self._anchor_window(
                    window,
                    segments=segments,
                    normalized_query=normalized_query,
                    query_type=query_type,
                )
                if window.jump_source != "chunk_start_fallback":
                    anchored += 1
        anchor_ms = _milliseconds(anchor_started)

        chapter_started = time.monotonic()
        chapter_count = 0
        for group in groups:
            video = videos[group.video_id]
            chapters = chapter_cache.setdefault(
                group.video_id,
                self._load_chapters(video, group.video_id, group.duration, warnings),
            )
            if not chapters:
                continue
            for window in group.windows:
                target = (
                    window.jump_time
                    if window.jump_time is not None
                    else (window.window_start + window.window_end) / 2
                )
                chapter = _chapter_for_time(chapters, target)
                if chapter is not None:
                    window.chapter = chapter.as_dict()
                    chapter_count += 1
        chapter_ms = _milliseconds(chapter_started)
        return EnrichmentResult(
            anchor_ms=anchor_ms,
            chapter_ms=chapter_ms,
            warnings=tuple(warnings),
            anchored_window_count=anchored,
            chapter_enriched_count=chapter_count,
        )

    @staticmethod
    def _canonical_metadata(
        group: VideoResultGroupDraft, video: dict[str, object] | None
    ) -> None:
        if video is None:
            group.warnings.append({"stage": "metadata", "code": "video_not_found"})
            return
        group.title = str(video.get("title") or group.title)
        group.uploader = str(video.get("uploader") or group.uploader)
        group.bvid = str(video.get("source_id") or "")
        group.video_url = str(
            video.get("video_url") or (
                f"https://www.bilibili.com/video/{group.bvid}" if group.bvid else ""
            )
        )
        value = video.get("duration_seconds")
        group.duration = float(value) if isinstance(value, (int, float)) and value > 0 else None

    def _load_segments(
        self,
        video: dict[str, object] | None,
        video_id: int,
        warnings: list[dict[str, object]],
    ) -> list[SubtitleSegment] | None:
        raw_path = video.get("raw_subtitle_path") if video else None
        if not raw_path:
            return None
        path = Path(str(raw_path)).with_name("subtitle-raw.json")
        try:
            if not path.is_file():
                raise FileNotFoundError(path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise ValueError("raw subtitle JSON is not an array")
            return [SubtitleSegment.model_validate(item) for item in payload]
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            warnings.append(_warning(video_id, "subtitle", "subtitle_unavailable", exc))
            return None

    def _load_chapters(
        self,
        video: dict[str, object] | None,
        video_id: int,
        duration: float | None,
        warnings: list[dict[str, object]],
    ) -> list[_Chapter] | None:
        if not video or not video.get("summary_path"):
            return None
        directory = Path(str(video["summary_path"])).parent
        revision = str(video.get("active_revision") or "refined")
        candidates = [directory / f"summary.{revision}.json", directory / "summary.json"]
        path = next((item for item in candidates if item.is_file()), None)
        if path is None:
            warnings.append(
                _warning(video_id, "chapter", "summary_unavailable", FileNotFoundError())
            )
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("summary JSON is not an object")
            raw_chapters = payload.get("important_chapters") or []
            if not isinstance(raw_chapters, list):
                raise ValueError("important_chapters is not an array")
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            warnings.append(_warning(video_id, "chapter", "summary_malformed", exc))
            return None

        valid: list[tuple[int, ImportantChapter]] = []
        for index, item in enumerate(raw_chapters):
            try:
                valid.append((index, ImportantChapter.model_validate(item)))
            except ValidationError as exc:
                warnings.append(_warning(video_id, "chapter", "chapter_skipped", exc))
        valid.sort(key=lambda item: (item[1].start_seconds, item[0]))
        unique: list[ImportantChapter] = []
        starts: set[float] = set()
        for _, chapter in valid:
            start = float(chapter.start_seconds)
            if start in starts:
                warnings.append(
                    {"video_id": video_id, "stage": "chapter", "code": "duplicate_chapter_start"}
                )
                continue
            starts.add(start)
            unique.append(chapter)
        result: list[_Chapter] = []
        for index, chapter in enumerate(unique):
            if index + 1 < len(unique):
                end = float(unique[index + 1].start_seconds)
                boundary = "derived_from_next_start"
            elif duration is not None and duration >= chapter.start_seconds:
                end = duration
                boundary = "derived_from_video_duration"
            else:
                end = None
                boundary = "open_ended"
            result.append(
                _Chapter(
                    title=chapter.title,
                    summary=chapter.summary,
                    start=float(chapter.start_seconds),
                    end=end,
                    boundary_type=boundary,
                )
            )
        return result

    def _anchor_window(
        self,
        window: EvidenceWindowDraft,
        *,
        segments: list[SubtitleSegment] | None,
        normalized_query: str,
        query_type: str,
    ) -> None:
        window.jump_time = float(window.best_hit.start_time)
        window.excerpt = window.best_hit.excerpt[:MAX_EXCERPT_CHARACTERS]
        if not segments:
            return
        indexed = [
            (index, segment)
            for index, segment in enumerate(segments)
            if segment.end >= window.window_start - 1
            and segment.start <= window.window_end + 1
        ]
        if not indexed:
            return
        if query_type == "semantic_question":
            window.excerpt = _excerpt(segments, indexed[0][0]) or window.excerpt
            return

        query_view = _normalize(normalized_query)
        phrase = [
            item
            for item in indexed
            if _contains_query_phrase(
                _normalize(item[1].content), query_view, query_type
            )
        ]
        if phrase:
            index, segment = min(phrase, key=lambda item: (item[1].start, item[0]))
            self._apply_anchor(window, segments, index, segment, "exact_query_phrase", "high", (normalized_query,))
            return

        ascii_terms = _ascii_terms(normalized_query)
        entity = _best_term_match(indexed, ascii_terms)
        if entity is not None:
            index, segment, matched = entity
            self._apply_anchor(window, segments, index, segment, "exact_entity_term", "high", matched)
            return

        if query_type in {"mixed_entity", "keyword_phrase"}:
            keyword = _best_term_match(indexed, _query_terms(normalized_query))
            if keyword is not None:
                index, segment, matched = keyword
                self._apply_anchor(window, segments, index, segment, "keyword_overlap", "medium", matched)

    @staticmethod
    def _apply_anchor(
        window: EvidenceWindowDraft,
        segments: list[SubtitleSegment],
        index: int,
        segment: SubtitleSegment,
        source: str,
        confidence: str,
        matched: tuple[str, ...],
    ) -> None:
        window.jump_time = float(segment.start)
        window.jump_source = source
        window.anchor_confidence = confidence
        window.anchor_segment_start = float(segment.start)
        window.anchor_segment_end = float(segment.end)
        window.matched_terms = matched[:8]
        window.excerpt = _excerpt(segments, index)


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def contains_technical_entity(normalized_segment: str, normalized_entity: str) -> bool:
    """Match an ASCII technical entity without relying on ``\b`` semantics."""
    return _technical_entity_match_count(normalized_segment, normalized_entity) > 0


def _technical_entity_match_count(
    normalized_segment: str, normalized_entity: str
) -> int:
    segment = _normalize(normalized_segment)
    entity = _normalize(normalized_entity)
    if not entity or not entity.isascii() or not any(char.isalpha() for char in entity):
        return 0
    count = 0
    cursor = 0
    while cursor < len(segment):
        index = segment.find(entity, cursor)
        if index < 0:
            break
        end = index + len(entity)
        left = segment[index - 1] if index else ""
        right = segment[end] if end < len(segment) else ""
        left_safe = not _ascii_alphanumeric(left) or entity.startswith(".")
        right_safe = not _ascii_alphanumeric(right) or (
            entity.endswith("++") and right.isdigit()
        )
        if left_safe and right_safe:
            count += 1
        cursor = index + max(1, len(entity))
    return count


def _contains_query_phrase(segment: str, query: str, query_type: str) -> bool:
    if query not in segment:
        return False
    if query_type == "exact_entity":
        return contains_technical_entity(segment, query)
    if query_type == "mixed_entity":
        ascii_terms = _ascii_terms(query)
        return all(contains_technical_entity(segment, term) for term in ascii_terms)
    return True


def _ascii_terms(query: str) -> tuple[str, ...]:
    values = _ASCII_SPAN.findall(query) + _ASCII_TERM.findall(query)
    return _unique_terms(values)


def _query_terms(query: str) -> tuple[str, ...]:
    values = list(_ascii_terms(query)) + _CJK_TERM.findall(query)
    return _unique_terms(values)


def _unique_terms(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize(value)
        if not normalized or normalized in _STOPWORDS or normalized in seen:
            continue
        seen.add(normalized)
        result.append(value.strip())
    return tuple(result)


def _best_term_match(
    indexed: list[tuple[int, SubtitleSegment]], terms: tuple[str, ...]
) -> tuple[int, SubtitleSegment, tuple[str, ...]] | None:
    candidates: list[tuple[int, int, float, int, SubtitleSegment, tuple[str, ...]]] = []
    for index, segment in indexed:
        view = _normalize(segment.content)
        counts = tuple((term, _term_match_count(view, term)) for term in terms)
        matched = tuple(term for term, count in counts if count)
        if not matched:
            continue
        total = sum(count for _, count in counts)
        candidates.append((-len(matched), -total, segment.start, index, segment, matched))
    if not candidates:
        return None
    _, _, _, index, segment, matched = min(candidates)
    return index, segment, matched


def _term_match_count(normalized_segment: str, term: str) -> int:
    normalized_term = _normalize(term)
    if normalized_term.isascii() and any(char.isalpha() for char in normalized_term):
        return _technical_entity_match_count(normalized_segment, normalized_term)
    return normalized_segment.count(normalized_term)


def _ascii_alphanumeric(value: str) -> bool:
    return bool(value) and value.isascii() and value.isalnum()


def _excerpt(segments: list[SubtitleSegment], index: int) -> str:
    values = [
        segments[item].content.strip()
        for item in range(max(0, index - 1), min(len(segments), index + 2))
        if segments[item].content.strip()
    ]
    return " ".join(values)[:MAX_EXCERPT_CHARACTERS]


def _chapter_for_time(chapters: list[_Chapter], target: float) -> _Chapter | None:
    eligible = [chapter for chapter in chapters if chapter.start <= target]
    return max(eligible, key=lambda chapter: chapter.start) if eligible else None


def _warning(video_id: int, stage: str, code: str, exc: Exception) -> dict[str, object]:
    message = f"{type(exc).__name__}: {exc}"[:300]
    return {"video_id": video_id, "stage": stage, "code": code, "message": message}


def _milliseconds(started: float) -> float:
    return (time.monotonic() - started) * 1000
