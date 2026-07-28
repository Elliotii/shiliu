from __future__ import annotations

from dataclasses import dataclass
import json

from shiliu.ask.citations import stable_citation_id
from shiliu.ask.contracts import EvidenceSegment, TranscriptEvidenceSpan
from shiliu.retrieval.product_search import build_bilibili_jump_url


@dataclass(frozen=True)
class ContextBuildResult:
    spans: tuple[TranscriptEvidenceSpan, ...]
    model_context: str
    citation_allowlist: tuple[str, ...]
    truncated: bool
    dropped_span_count: int


def fuse_evidence(
    spans: list[TranscriptEvidenceSpan] | tuple[TranscriptEvidenceSpan, ...],
) -> tuple[TranscriptEvidenceSpan, ...]:
    by_identity: dict[str, TranscriptEvidenceSpan] = {}
    for span in spans:
        score = sum(
            1.0 / (60.0 + max(1, int(value.get("rank", 1))))
            for value in span.retrieval_provenance
        )
        existing = by_identity.get(span.citation_id)
        if existing is None:
            by_identity[span.citation_id] = span.model_copy(
                update={"fusion_score": score}
            )
            continue
        provenance = _unique_dicts(
            (*existing.retrieval_provenance, *span.retrieval_provenance)
        )
        parents = tuple(
            dict.fromkeys((*existing.parent_chunk_ids, *span.parent_chunk_ids))
        )
        by_identity[span.citation_id] = existing.model_copy(
            update={
                "retrieval_provenance": provenance,
                "parent_chunk_ids": parents,
                "fusion_score": existing.fusion_score + score,
            }
        )
    return tuple(
        sorted(
            by_identity.values(),
            key=lambda value: (
                -value.fusion_score,
                value.video_id,
                value.start_time,
                value.citation_id,
            ),
        )
    )


class TranscriptContextBuilder:
    def __init__(
        self,
        *,
        per_span_character_budget: int = 2500,
        total_character_budget: int = 12000,
        max_spans: int = 12,
    ) -> None:
        if per_span_character_budget <= 0 or total_character_budget <= 0:
            raise ValueError("context character budgets must be positive")
        if max_spans <= 0:
            raise ValueError("max_spans must be positive")
        self.per_span_character_budget = per_span_character_budget
        self.total_character_budget = total_character_budget
        self.max_spans = max_spans

    def build(
        self,
        *,
        query: str,
        normalized_intent: str,
        spans: tuple[TranscriptEvidenceSpan, ...],
    ) -> ContextBuildResult:
        selected: list[TranscriptEvidenceSpan] = []
        total = 0
        truncated = False
        dropped = 0
        for source_span in spans:
            span = _fit_span(source_span, self.per_span_character_budget)
            if span is None:
                truncated = True
                dropped += 1
                continue
            if span.segment_ids != source_span.segment_ids:
                truncated = True
            merged = False
            for index, existing in enumerate(selected):
                if not _same_lineage(existing, span):
                    continue
                relation = _segment_relation(existing, span)
                if relation == "separate":
                    continue
                candidate = _merge_spans(existing, span)
                if len(candidate.quote_text) > self.per_span_character_budget:
                    if relation == "overlap":
                        truncated = True
                        dropped += 1
                        merged = True
                    continue
                delta = len(candidate.quote_text) - len(existing.quote_text)
                if total + delta > self.total_character_budget:
                    truncated = True
                    dropped += 1
                    merged = True
                    continue
                selected[index] = candidate
                total += delta
                merged = True
                break
            if merged:
                continue
            if len(selected) >= self.max_spans or total + len(span.quote_text) > self.total_character_budget:
                truncated = True
                dropped += 1
                continue
            selected.append(span)
            total += len(span.quote_text)

        context_items = [
            {
                "citation_id": value.citation_id,
                "source_type": value.source_type,
                "source_language": value.source_language,
                "start_time": value.start_time,
                "end_time": value.end_time,
                "quote_text": value.quote_text,
            }
            for value in selected
        ]
        model_context = json.dumps(
            {
                "user_query": query,
                "normalized_intent": normalized_intent,
                "citation_allowlist": [
                    value.citation_id for value in selected
                ],
                "transcript_evidence": context_items,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return ContextBuildResult(
            spans=tuple(selected),
            model_context=model_context,
            citation_allowlist=tuple(value.citation_id for value in selected),
            truncated=truncated,
            dropped_span_count=dropped,
        )


def _fit_span(
    span: TranscriptEvidenceSpan, character_budget: int
) -> TranscriptEvidenceSpan | None:
    selected: list[EvidenceSegment] = []
    for segment in span.segments:
        candidate = "\n".join(
            value.source_text.strip()
            for value in (*selected, segment)
            if value.source_text.strip()
        )
        if len(candidate) > character_budget:
            break
        selected.append(segment)
    if not selected:
        return None
    if len(selected) == len(span.segments):
        return span
    return _span_with_segments(span, tuple(selected))


def _same_lineage(
    left: TranscriptEvidenceSpan, right: TranscriptEvidenceSpan
) -> bool:
    return (
        left.video_id == right.video_id
        and left.source_artifact_id == right.source_artifact_id
        and left.source_version == right.source_version
        and left.timeline_run_id == right.timeline_run_id
    )


def _segment_relation(
    left: TranscriptEvidenceSpan, right: TranscriptEvidenceSpan
) -> str:
    left_values = {segment.run_local_ordinal for segment in left.segments}
    right_values = {segment.run_local_ordinal for segment in right.segments}
    if left_values & right_values:
        return "overlap"
    if max(left_values) + 1 == min(right_values) or max(right_values) + 1 == min(left_values):
        return "adjacent"
    return "separate"


def _merge_spans(
    left: TranscriptEvidenceSpan, right: TranscriptEvidenceSpan
) -> TranscriptEvidenceSpan:
    by_id = {
        segment.segment_id: segment
        for segment in (*left.segments, *right.segments)
    }
    segments = tuple(
        sorted(by_id.values(), key=lambda value: value.original_ordinal)
    )
    provenance = _unique_dicts(
        (*left.retrieval_provenance, *right.retrieval_provenance)
    )
    parents = tuple(
        dict.fromkeys((*left.parent_chunk_ids, *right.parent_chunk_ids))
    )
    return _span_with_segments(
        left,
        segments,
        provenance=provenance,
        parents=parents,
        fusion_score=max(left.fusion_score, right.fusion_score),
    )


def _span_with_segments(
    span: TranscriptEvidenceSpan,
    segments: tuple[EvidenceSegment, ...],
    *,
    provenance: tuple[dict[str, object], ...] | None = None,
    parents: tuple[str, ...] | None = None,
    fusion_score: float | None = None,
) -> TranscriptEvidenceSpan:
    quote = "\n".join(
        value.source_text.strip() for value in segments if value.source_text.strip()
    )
    start_time = segments[0].start_time
    citation_id = stable_citation_id(
        source_artifact_id=span.source_artifact_id,
        source_version=span.source_version,
        timeline_run_id=span.timeline_run_id,
        segments=segments,
    )
    jump_url = build_bilibili_jump_url(span.jump_url, span.bvid, start_time)
    if jump_url is None:
        raise ValueError("unable to rebuild citation jump URL")
    return span.model_copy(
        update={
            "citation_id": citation_id,
            "segment_ids": tuple(value.segment_id for value in segments),
            "segment_ordinals": tuple(
                value.original_ordinal for value in segments
            ),
            "start_time": start_time,
            "end_time": segments[-1].end_time,
            "quote_text": quote,
            "jump_url": jump_url,
            "segments": segments,
            "retrieval_provenance": provenance or span.retrieval_provenance,
            "parent_chunk_ids": parents or span.parent_chunk_ids,
            "fusion_score": (
                span.fusion_score if fusion_score is None else fusion_score
            ),
        }
    )


def _unique_dicts(values) -> tuple[dict[str, object], ...]:
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for value in values:
        key = json.dumps(value, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(value))
    return tuple(result)
