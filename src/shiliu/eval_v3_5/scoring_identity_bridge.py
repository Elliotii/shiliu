"""Generic scorer bridge for canonical, segment-backed evidence identity."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import math
from pathlib import Path
import sqlite3
from typing import Any, Literal


TIME_TOLERANCE_SECONDS = 1e-6
MatchStatus = Literal["match", "non_match", "unverifiable"]


@dataclass(frozen=True)
class CanonicalVideoIdentity:
    source_type: str
    source_video_id: str
    numeric_video_id: int
    part: int

    @property
    def source_platform(self) -> str:
        return self.source_type


@dataclass(frozen=True)
class EvidenceProvenance:
    underlying_evidence_source: str
    source_generation_lineage: str | None
    selection_method: str | None
    extraction_method: str | None
    model_or_builder_version: str | None


@dataclass(frozen=True)
class CanonicalScoringIdentity:
    source_artifact_id: str | None
    source_version: str
    video: CanonicalVideoIdentity
    timeline_run_id: str
    segment_ids: tuple[str, ...]
    start_time: float
    end_time: float
    provenance: EvidenceProvenance

    @property
    def source_type(self) -> str | None:
        return self.provenance.source_generation_lineage

    @property
    def source_platform(self) -> str:
        return self.video.source_platform


@dataclass(frozen=True)
class EvidenceMatchResult:
    status: MatchStatus
    reason: str
    left: CanonicalScoringIdentity | None
    right: CanonicalScoringIdentity | None


class VideoIdentityCanonicalizer:
    """Resolve BVID and snapshot numeric IDs through one authoritative mapping."""

    def __init__(
        self,
        identities: Sequence[CanonicalVideoIdentity],
        *,
        source: str,
        source_sha256: str,
    ) -> None:
        by_numeric: dict[int, CanonicalVideoIdentity] = {}
        by_source: dict[tuple[str, str], CanonicalVideoIdentity] = {}
        for identity in identities:
            source_key = (identity.source_platform, identity.source_video_id)
            if identity.numeric_video_id in by_numeric or source_key in by_source:
                raise ValueError("authoritative video identity mapping is not one-to-one")
            by_numeric[identity.numeric_video_id] = identity
            by_source[source_key] = identity
        self._by_numeric = by_numeric
        self._by_source = by_source
        self.source = source
        self.source_sha256 = source_sha256

    @classmethod
    def from_sqlite(cls, path: str | Path) -> "VideoIdentityCanonicalizer":
        source_path = Path(path)
        digest = sha256(source_path.read_bytes()).hexdigest()
        with sqlite3.connect(f"file:{source_path}?mode=ro", uri=True) as connection:
            rows = connection.execute(
                "SELECT platform, source_id, id, part FROM videos ORDER BY id"
            ).fetchall()
        identities = [
            CanonicalVideoIdentity(
                source_type=str(platform),
                source_video_id=str(source_id),
                numeric_video_id=int(numeric_id),
                part=int(part),
            )
            for platform, source_id, numeric_id, part in rows
        ]
        return cls(identities, source=str(source_path), source_sha256=digest)

    def resolve(self, value: object | None) -> CanonicalVideoIdentity | None:
        if value in (None, "") or isinstance(value, bool):
            return None
        if isinstance(value, int) or (isinstance(value, str) and value.isdecimal()):
            return self._by_numeric.get(int(value))
        text = str(value).strip()
        if ":" in text:
            source_platform, source_video_id = text.split(":", 1)
        elif text.startswith("BV"):
            source_platform, source_video_id = "bilibili", text
        else:
            return None
        return self._by_source.get((source_platform.casefold(), source_video_id))

    def resolve_span(self, span: Mapping[str, Any]) -> CanonicalVideoIdentity | None:
        values: list[object] = []
        for field in ("canonical_video_id", "video_id", "bvid", "source_id"):
            value = span.get(field)
            if value not in (None, ""):
                if field in {"bvid", "source_id"} and ":" not in str(value):
                    platform = str(span.get("source_platform") or span.get("platform") or "bilibili")
                    values.append(f"{platform}:{value}")
                else:
                    values.append(value)
        resolved = [self.resolve(value) for value in values]
        if not resolved or any(value is None for value in resolved):
            return None
        identity = resolved[0]
        if any(value != identity for value in resolved[1:]):
            return None
        explicit_platform = span.get("source_platform", span.get("platform"))
        if explicit_platform not in (None, "") and str(explicit_platform).casefold() != identity.source_platform.casefold():
            return None
        if span.get("aid") not in (None, "") and not values:
            return None
        return identity

    def __len__(self) -> int:
        return len(self._by_numeric)


def _text(span: Mapping[str, Any], *fields: str) -> str | None:
    for field in fields:
        value = span.get(field)
        if value not in (None, ""):
            return str(value)
    return None


def _segment_ids(span: Mapping[str, Any]) -> tuple[str, ...]:
    values = span.get("segment_ids")
    if values in (None, ""):
        single = span.get("segment_id")
        values = [] if single in (None, "") else [single]
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        return ()
    result = tuple(str(value) for value in values if value not in (None, ""))
    if not result or len(set(result)) != len(result):
        return ()
    return result


def _provenance(span: Mapping[str, Any]) -> EvidenceProvenance:
    legacy = (_text(span, "source_type") or "").casefold()
    extraction = _text(span, "extraction_method")
    explicit_underlying = (_text(span, "underlying_evidence_source", "artifact_role") or "").casefold()
    summary_markers = {"ai_generated_summary", "generated_summary", "ai_summary", "summary"}
    if explicit_underlying in summary_markers or (extraction or "").casefold() in summary_markers:
        underlying = "ai_generated_summary"
    elif explicit_underlying in {"raw_subtitle", "official_subtitle", "asr_transcript", "transcript"}:
        underlying = "raw_subtitle"
    elif legacy in summary_markers:
        underlying = "ai_generated_summary"
    elif legacy in {"raw_subtitle", "official_subtitle", "asr_transcript", "human", "ai", "asr"}:
        underlying = "raw_subtitle"
    elif span.get("segment_identity_version") or span.get("evidence_candidate_contract_version"):
        underlying = "raw_subtitle"
    else:
        underlying = "unverifiable"

    if legacy in {"human", "ai", "asr"}:
        lineage = legacy
    elif legacy == "official_subtitle":
        lineage = "official"
    elif legacy == "asr_transcript":
        lineage = "asr"
    else:
        lineage = _text(span, "source_generation_lineage", "source_lineage")
    return EvidenceProvenance(
        underlying_evidence_source=underlying,
        source_generation_lineage=lineage,
        selection_method=_text(span, "selection_method", "selector_method"),
        extraction_method=extraction,
        model_or_builder_version=_text(span, "builder_version", "model_name", "model_version"),
    )


def canonical_scoring_identity(
    span: Mapping[str, Any], canonicalizer: VideoIdentityCanonicalizer,
) -> CanonicalScoringIdentity | None:
    video = canonicalizer.resolve_span(span)
    source_version = _text(span, "source_version")
    timeline_run_id = _text(span, "timeline_run_id")
    segment_ids = _segment_ids(span)
    try:
        start_time = float(span["start_time"])
        end_time = float(span["end_time"])
    except (KeyError, TypeError, ValueError):
        return None
    provenance = _provenance(span)
    if (
        video is None
        or source_version is None
        or timeline_run_id is None
        or not segment_ids
        or not math.isfinite(start_time)
        or not math.isfinite(end_time)
        or start_time < 0
        or end_time < start_time
        or provenance.underlying_evidence_source == "unverifiable"
    ):
        return None
    return CanonicalScoringIdentity(
        source_artifact_id=_text(span, "source_artifact_id"),
        source_version=source_version,
        video=video,
        timeline_run_id=timeline_run_id,
        segment_ids=segment_ids,
        start_time=start_time,
        end_time=end_time,
        provenance=provenance,
    )


def _same_span_namespace(
    gold: CanonicalScoringIdentity, candidate: CanonicalScoringIdentity,
) -> bool:
    if gold.video != candidate.video:
        return False
    if gold.source_version != candidate.source_version:
        return False
    if gold.timeline_run_id != candidate.timeline_run_id:
        return False
    if gold.provenance.underlying_evidence_source != candidate.provenance.underlying_evidence_source:
        return False
    if (
        gold.source_artifact_id
        and candidate.source_artifact_id
        and gold.source_artifact_id != candidate.source_artifact_id
    ):
        return False
    return True


def canonical_evidence_match(
    left_span: Mapping[str, Any],
    right_span: Mapping[str, Any],
    canonicalizer: VideoIdentityCanonicalizer,
) -> EvidenceMatchResult:
    left = canonical_scoring_identity(left_span, canonicalizer)
    right = canonical_scoring_identity(right_span, canonicalizer)
    if left is None or right is None:
        return EvidenceMatchResult("unverifiable", "missing_or_ambiguous_identity", left, right)
    if not _same_span_namespace(left, right):
        return EvidenceMatchResult("non_match", "different_identity_namespace", left, right)
    if left.segment_ids != right.segment_ids:
        return EvidenceMatchResult("non_match", "different_segment_identity", left, right)
    if (
        abs(left.start_time - right.start_time) > TIME_TOLERANCE_SECONDS
        or abs(left.end_time - right.end_time) > TIME_TOLERANCE_SECONDS
    ):
        return EvidenceMatchResult("non_match", "different_temporal_interval", left, right)
    return EvidenceMatchResult("match", "canonical_identity_equal", left, right)


def span_is_covered(
    gold_span: Mapping[str, Any],
    candidate_spans: Sequence[Mapping[str, Any]],
    canonicalizer: VideoIdentityCanonicalizer,
) -> bool:
    gold = canonical_scoring_identity(gold_span, canonicalizer)
    if gold is None:
        return False
    available: set[str] = set()
    contributing: list[CanonicalScoringIdentity] = []
    required = set(gold.segment_ids)
    for candidate_span in candidate_spans:
        candidate = canonical_scoring_identity(candidate_span, canonicalizer)
        if candidate is not None and _same_span_namespace(gold, candidate):
            if required & set(candidate.segment_ids):
                contributing.append(candidate)
                available.update(candidate.segment_ids)
    if not required.issubset(available) or not contributing:
        return False
    return (
        min(value.start_time for value in contributing) <= gold.start_time + TIME_TOLERANCE_SECONDS
        and max(value.end_time for value in contributing) >= gold.end_time - TIME_TOLERANCE_SECONDS
    )


def covered_span_ids(
    evidence: Mapping[str, Any],
    candidate_spans: Sequence[Mapping[str, Any]],
    canonicalizer: VideoIdentityCanonicalizer,
) -> set[str]:
    return {
        str(gold_span["span_id"])
        for gold_span in evidence.get("span_registry", [])
        if span_is_covered(gold_span, candidate_spans, canonicalizer)
    }


def complete_group_ids(evidence: Mapping[str, Any], covered_spans: set[str]) -> list[str]:
    completed = []
    for group in evidence.get("acceptable_evidence_groups", []):
        required_sets = group.get("required_span_sets", [])
        if all(set(value.get("required_span_ids", [])).issubset(covered_spans) for value in required_sets):
            completed.append(str(group["group_id"]))
    return completed


def covered_aspect_ids(evidence: Mapping[str, Any], covered_spans: set[str]) -> list[str]:
    return [
        str(aspect["aspect_id"])
        for aspect in evidence.get("aspect_evidence_options", [])
        if any(
            set(option.get("required_span_ids", [])).issubset(covered_spans)
            for option in aspect.get("alternative_sets", [])
        )
    ]


def required_span_ids(evidence: Mapping[str, Any]) -> set[str]:
    return {
        str(span_id)
        for group in evidence.get("acceptable_evidence_groups", [])
        for required_set in group.get("required_span_sets", [])
        for span_id in required_set.get("required_span_ids", [])
    }


def material_aspect_ids(evidence: Mapping[str, Any]) -> set[str]:
    return {
        str(aspect["aspect_id"])
        for aspect in evidence.get("required_aspects", [])
        if aspect.get("materiality") == "material"
    }
