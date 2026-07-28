from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from shiliu.eval_v3_5.scoring_identity_bridge import (
    VideoIdentityCanonicalizer,
    canonical_evidence_match,
    canonical_scoring_identity,
    span_is_covered,
)


@dataclass(frozen=True)
class SpanProjection:
    covered: bool
    match_count: int
    non_match_count: int
    unverifiable_count: int
    aggregate_preserved_span_coverage: bool


def project_gold_span(
    gold_span: Mapping[str, Any],
    candidate_spans: Sequence[Mapping[str, Any]],
    canonicalizer: VideoIdentityCanonicalizer,
) -> SpanProjection:
    statuses = Counter(
        canonical_evidence_match(gold_span, candidate, canonicalizer).status
        for candidate in candidate_spans
    )
    aggregate_coverage = span_is_covered(gold_span, candidate_spans, canonicalizer)
    covered = statuses["match"] > 0 or aggregate_coverage
    return SpanProjection(
        covered=covered,
        match_count=statuses["match"],
        non_match_count=statuses["non_match"],
        unverifiable_count=statuses["unverifiable"],
        aggregate_preserved_span_coverage=aggregate_coverage and statuses["match"] == 0,
    )


def project_evidence(
    evidence: Mapping[str, Any],
    candidate_spans: Sequence[Mapping[str, Any]],
    canonicalizer: VideoIdentityCanonicalizer,
) -> tuple[set[str], dict[str, SpanProjection]]:
    projections = {
        str(gold_span["span_id"]): project_gold_span(
            gold_span, candidate_spans, canonicalizer,
        )
        for gold_span in evidence.get("span_registry", [])
    }
    covered = {
        span_id for span_id, projection in projections.items() if projection.covered
    }
    return covered, projections


def unverifiable_candidate_count(
    candidate_spans: Sequence[Mapping[str, Any]],
    canonicalizer: VideoIdentityCanonicalizer,
) -> int:
    return sum(
        canonical_scoring_identity(candidate, canonicalizer) is None
        for candidate in candidate_spans
    )
