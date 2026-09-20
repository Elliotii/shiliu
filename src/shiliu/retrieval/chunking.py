from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from shiliu.domain import SubtitleSegment


@dataclass(frozen=True)
class ChunkingConfig:
    target_characters: int = 800
    maximum_characters: int = 1200
    maximum_duration_seconds: float = 120.0
    trailing_segment_overlap: bool = True

    def __post_init__(self) -> None:
        if self.target_characters <= 0:
            raise ValueError("target_characters must be positive")
        if self.maximum_characters < self.target_characters:
            raise ValueError("maximum_characters must be >= target_characters")
        if self.maximum_duration_seconds <= 0:
            raise ValueError("maximum_duration_seconds must be positive")


@dataclass(frozen=True)
class RawSubtitleChunk:
    chunk_id: str
    start_time: float
    end_time: float
    text: str
    content_hash: str
    segment_count: int


def build_raw_subtitle_chunks(
    *,
    platform: str,
    source_id: str,
    part: int,
    source_type: str,
    segments: list[SubtitleSegment],
    config: ChunkingConfig | None = None,
) -> list[RawSubtitleChunk]:
    """Build deterministic chunks without splitting a subtitle segment.

    A single upstream segment may itself exceed a configured bound.  In that
    case it remains whole and forms an oversized one-segment chunk; inventing a
    split would violate timestamp provenance.  Otherwise the maximum character
    and duration bounds are enforced before adding the next segment.
    """

    resolved = config or ChunkingConfig()
    usable = [segment for segment in segments if segment.content.strip()]
    chunks: list[RawSubtitleChunk] = []
    cursor = 0

    while cursor < len(usable):
        start_index = cursor
        selected: list[SubtitleSegment] = []
        characters = 0

        while cursor < len(usable):
            candidate = usable[cursor]
            candidate_text = candidate.content.strip()
            separator = 1 if selected else 0
            next_characters = characters + separator + len(candidate_text)
            first_start = selected[0].start if selected else candidate.start
            next_duration = candidate.end - first_start
            exceeds_bound = bool(selected) and (
                next_characters > resolved.maximum_characters
                or next_duration > resolved.maximum_duration_seconds
            )
            if exceeds_bound:
                break
            selected.append(candidate)
            characters = next_characters
            cursor += 1
            if characters >= resolved.target_characters:
                break

        if not selected:  # defensive; the first complete segment is always accepted
            cursor += 1
            continue

        text = " ".join(segment.content.strip() for segment in selected)
        if text:
            chunks.append(
                _make_chunk(
                    platform=platform,
                    source_id=source_id,
                    part=part,
                    source_type=source_type,
                    start_time=selected[0].start,
                    end_time=selected[-1].end,
                    text=text,
                    segment_count=len(selected),
                )
            )

        if cursor < len(usable) and resolved.trailing_segment_overlap and len(selected) > 1:
            cursor -= 1
        if cursor <= start_index:
            cursor = start_index + 1

    return chunks


def _make_chunk(
    *,
    platform: str,
    source_id: str,
    part: int,
    source_type: str,
    start_time: float,
    end_time: float,
    text: str,
    segment_count: int,
) -> RawSubtitleChunk:
    content_hash = sha256(text.encode("utf-8")).hexdigest()
    identity = json.dumps(
        {
            "platform": platform,
            "source_id": source_id,
            "part": part,
            "source_type": source_type,
            "start_time": start_time,
            "end_time": end_time,
            "content_hash": content_hash,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    chunk_id = "chunk_" + sha256(identity.encode("utf-8")).hexdigest()[:32]
    return RawSubtitleChunk(
        chunk_id=chunk_id,
        start_time=start_time,
        end_time=end_time,
        text=text,
        content_hash=content_hash,
        segment_count=segment_count,
    )
