from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from hashlib import sha256
import math
import re
from typing import Callable, Iterable, Mapping, Sequence

from shiliu.evidence.contracts import EvidenceContractError, ParsedSourceArtifact, RawEvidenceSegment
from shiliu.evidence.source import canonical_json


EVIDENCE_CANDIDATE_CONTRACT_VERSION = "v3.5-evidence-candidate-v1"
EVIDENCE_BUNDLE_CONTRACT_VERSION = "v3.5-evidence-bundle-v1"
COVERAGE_SEMANTICS_VERSION = "v3.5-candidate-union-coverage-v1"
DETERMINISTIC_SELECTOR_VERSION = "v3.5-deterministic-fine-selector-v1"
DETERMINISTIC_SELECTOR_V2_VERSION = "v3.5-deterministic-fine-selector-v2"
CANDIDATE_GENERATION_POLICY_STAGE3B = "v3.5-stage3b-asr-acronym-anchor-v1"
ADAPTIVE_BOUNDED_COVERAGE_SWAP_VERSION = "adaptive_bounded_coverage_swap_v1"
F1A_CANDIDATE_BUILDER_VERSION = "stage3b-adaptive-swap-w3.5-v1"
STAGE3A_ERROR_CODES = frozenset({
    "segment_not_found", "segment_video_mismatch", "source_artifact_mismatch",
    "source_version_mismatch", "timeline_run_mismatch", "segment_order_invalid",
    "candidate_not_contiguous", "candidate_budget_exceeded", "raw_source_unavailable",
    "no_supported_subtitle", "invalid_bundle_reference", "execution_manifest_mismatch",
    "search_candidate_set_mismatch", "upstream_retrieval_failure",
})


@dataclass(frozen=True)
class CandidateBuilderConfig:
    config_id: str = "stage3a-builder-default-v1"
    max_segments_per_candidate: int = 6
    preferred_duration_seconds: tuple[float, float] = (10.0, 45.0)
    hard_max_duration_seconds: float = 60.0
    preferred_characters: tuple[int, int] = (100, 350)
    hard_max_characters: int = 500
    within_video_max_candidates: int = 24
    within_video_max_total_characters: int = 6000
    within_video_max_total_union_duration_seconds: float = 600.0
    per_anchor_window_max_segments: int = 6
    near_duplicate_jaccard_threshold: float = 0.75
    candidate_generation_policy_version: str = "v3.5-stage3a-query-anchor-v1"
    asr_acronym_anchor_enabled: bool = False
    acronym_min_length: int = 2
    acronym_max_length: int = 8
    acronym_max_substitution_distance: int = 1
    acronym_equal_length_only: bool = True
    acronym_anchor_weight: float = 3.5
    adaptive_coverage_swap_enabled: bool = True
    adaptive_coverage_swap_max_swaps: int = 4
    candidate_allocation_policy_version: str = ADAPTIVE_BOUNDED_COVERAGE_SWAP_VERSION


@dataclass(frozen=True)
class SelectorConfig:
    config_id: str = "stage3a-selector-default-v1"
    max_candidates_per_bundle: int = 6
    exact_phrase_weight: float = 2.0
    query_coverage_weight: float = 2.0
    ngram_weight: float = 1.25
    token_overlap_weight: float = 1.25
    entity_overlap_weight: float = 1.0
    parent_rank_weight: float = 0.35
    length_penalty_weight: float = 0.15
    overlap_penalty_weight: float = 0.8
    marginal_coverage_weight: float = 0.75
    locality_weight: float = 0.4
    bundle_candidate_count_penalty: float = 0.04
    bundle_duration_penalty: float = 0.0005


@dataclass(frozen=True)
class MarginalSelectorConfig:
    """Frozen, generic weights for F1B greedy marginal bundle assembly."""

    config_id: str = "stage3a-selector-greedy-marginal-v2"
    max_candidates_per_bundle: int = 6
    lexical_relevance_weight: float = 0.55
    builder_relevance_weight: float = 0.25
    query_atom_novelty_weight: float = 1.10
    new_segment_weight: float = 0.45
    temporal_region_novelty_weight: float = 0.30
    segment_redundancy_weight: float = 0.80
    temporal_overlap_weight: float = 0.50
    text_redundancy_weight: float = 0.30
    temporal_region_seconds: float = 90.0
    temporal_distance_cap_seconds: float = 180.0
    bundle_query_coverage_weight: float = 3.0
    bundle_peak_relevance_weight: float = 1.5
    bundle_mean_relevance_weight: float = 1.0
    bundle_segment_diversity_weight: float = 0.30
    bundle_temporal_diversity_weight: float = 0.50
    bundle_redundancy_weight: float = 0.75
    bundle_duration_penalty: float = 0.0005


@dataclass(frozen=True)
class EvidenceCandidate:
    candidate_id: str
    query_id: str
    video_id: int
    source_artifact_id: str
    source_version: str
    timeline_run_id: str
    segment_ids: tuple[str, ...]
    original_ordinals: tuple[int, ...]
    start_time: float
    end_time: float
    source_text: str
    source_language: str
    source_type: str
    parent_chunk_ids: tuple[str, ...]
    search_candidate_ids: tuple[str, ...]
    candidate_methods: tuple[str, ...]
    segment_count: int
    character_count: int
    lexical_token_count: int
    overlap_group_id: str
    related_candidate_ids: tuple[str, ...]
    overlap_relation: str
    trace_id: str
    normalization_status: str
    validation_errors: tuple[str, ...]
    parent_rank: int | None = None
    score_breakdown: Mapping[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["evidence_candidate_contract_version"] = EVIDENCE_CANDIDATE_CONTRACT_VERSION
        return value


@dataclass(frozen=True)
class EvidenceCandidateSet:
    query_id: str
    original_query: str
    candidates: tuple[EvidenceCandidate, ...]
    evaluation_track: str
    end_to_end_claim_eligible: bool
    trace: Mapping[str, object]
    normalization_status: str = "valid"
    validation_errors: tuple[str, ...] = ()
    failure_category: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "evidence_candidate_contract_version": EVIDENCE_CANDIDATE_CONTRACT_VERSION,
            "query_id": self.query_id,
            "original_query": self.original_query,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "evaluation_track": self.evaluation_track,
            "end_to_end_claim_eligible": self.end_to_end_claim_eligible,
            "trace": dict(self.trace),
            "normalization_status": self.normalization_status,
            "validation_errors": list(self.validation_errors),
            "failure_category": self.failure_category,
        }


@dataclass(frozen=True)
class EvidenceBundle:
    bundle_id: str
    query_id: str
    video_id: int
    source_artifact_ids: tuple[str, ...]
    source_versions: tuple[str, ...]
    timeline_run_ids: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    normalized_spans: tuple[dict[str, object], ...]
    union_duration: float
    source_texts: tuple[str, ...]
    selection_method: str
    score: float
    score_breakdown: Mapping[str, float]
    evaluation_track: str
    end_to_end_claim_eligible: bool
    trace_id: str
    normalization_status: str
    validation_errors: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["evidence_bundle_contract_version"] = EVIDENCE_BUNDLE_CONTRACT_VERSION
        return value


RawSourceResolver = Callable[[int], ParsedSourceArtifact]


def _stable_hash(prefix: str, value: object) -> str:
    return prefix + sha256(canonical_json(value)).hexdigest()


def _candidate_identity(
    artifact: ParsedSourceArtifact,
    segments: Sequence[RawEvidenceSegment],
    methods: Iterable[str],
    parent_chunks: Iterable[str],
) -> str:
    payload = {
        "candidate_methods": sorted(set(methods)),
        "contract_version": EVIDENCE_CANDIDATE_CONTRACT_VERSION,
        "parent_chunk_ids": sorted(set(parent_chunks)),
        "segment_ids": [segment.segment_id for segment in segments],
        "source_artifact_id": artifact.source_artifact_id,
        "source_version": artifact.source_version,
        "timeline_run_id": segments[0].timeline_run_id,
    }
    return _stable_hash("candidate_", payload)


def _candidate_identity_from_fields(candidate: EvidenceCandidate, methods: Iterable[str], parents: Iterable[str]) -> str:
    return _stable_hash("candidate_", {
        "candidate_methods": sorted(set(methods)),
        "contract_version": EVIDENCE_CANDIDATE_CONTRACT_VERSION,
        "parent_chunk_ids": sorted(set(parents)),
        "segment_ids": list(candidate.segment_ids),
        "source_artifact_id": candidate.source_artifact_id,
        "source_version": candidate.source_version,
        "timeline_run_id": candidate.timeline_run_id,
    })


def _query_features(query: str) -> dict[str, set[str] | str]:
    normalized = re.sub(r"\s+", " ", query.casefold()).strip()
    english = set(re.findall(r"[a-z][a-z0-9_.+-]{1,}", normalized))
    chinese_runs = re.findall(r"[\u3400-\u9fff]+", normalized)
    chinese = "".join(chinese_runs)
    bigrams = {chinese[i:i + 2] for i in range(max(0, len(chinese) - 1))}
    trigrams = {chinese[i:i + 3] for i in range(max(0, len(chinese) - 2))}
    stop = {"哪些", "内容", "讨论", "什么", "如何", "怎么", "是否", "以及", "区别", "关系"}
    return {
        "normalized": normalized,
        "english": english,
        "bigrams": bigrams - stop,
        "trigrams": trigrams - stop,
        "entities": {token for token in english if len(token) >= 3},
    }


def compact_acronym_tokens(value: str, *, query_tokens: bool = False) -> tuple[str, ...]:
    """Return bounded Latin/alphanumeric acronym tokens without a correction lexicon."""

    patterns = (
        r"(?<![A-Za-z0-9])(?:[A-Za-z0-9][._-]){1,7}[A-Za-z0-9](?![A-Za-z0-9])",
        r"(?<![A-Za-z0-9])[A-Za-z0-9]{2,8}(?![A-Za-z0-9])",
    )
    values: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, value):
            raw = match.group(0)
            compact = re.sub(r"[^A-Za-z0-9]", "", raw)
            if not 2 <= len(compact) <= 8 or not any(character.isalpha() for character in compact):
                continue
            if query_tokens:
                letters = [character for character in raw if character.isalpha()]
                if not letters or not all(character.isupper() for character in letters):
                    continue
            values.add(compact.casefold())
    return tuple(sorted(values))


def one_substitution_acronym_matches(query: str, text: str, config: CandidateBuilderConfig) -> tuple[tuple[str, str], ...]:
    if not config.asr_acronym_anchor_enabled:
        return ()
    query_values = [
        value for value in compact_acronym_tokens(query, query_tokens=True)
        if config.acronym_min_length <= len(value) <= config.acronym_max_length
    ]
    text_values = [
        value for value in compact_acronym_tokens(text)
        if config.acronym_min_length <= len(value) <= config.acronym_max_length
    ]
    matches: set[tuple[str, str]] = set()
    for expected in query_values:
        for observed in text_values:
            if config.acronym_equal_length_only and len(expected) != len(observed):
                continue
            if len(expected) != len(observed):
                continue
            distance = sum(left != right for left, right in zip(expected, observed))
            if 0 < distance <= config.acronym_max_substitution_distance:
                matches.add((expected, observed))
    return tuple(sorted(matches))


def lexical_score(
    query: str, text: str, *, parent_rank: int | None = None,
    builder_config: CandidateBuilderConfig | None = None,
) -> dict[str, float]:
    features = _query_features(query)
    normalized_text = re.sub(r"\s+", " ", text.casefold()).strip()
    english_sequence = re.findall(r"[a-z][a-z0-9_.+-]{0,}", normalized_text)
    english_text = set(english_sequence)
    # Subtitle tokenization often inserts a space into a product or protocol name
    # (for example ``memory os``).  Adjacent-token compaction is deterministic and
    # applies to every query; it is not a case/video feature.
    english_text |= {
        english_sequence[index] + english_sequence[index + 1]
        for index in range(max(0, len(english_sequence) - 1))
    }
    compact_query = re.sub(r"[^a-z0-9\u3400-\u9fff]", "", str(features["normalized"]))
    compact_text = re.sub(r"[^a-z0-9\u3400-\u9fff]", "", normalized_text)
    exact = float(bool(compact_query and compact_query in compact_text))
    english = features["english"]
    bigrams = features["bigrams"]
    trigrams = features["trigrams"]
    token_overlap = len(english & english_text) / max(1, len(english))
    ngram_hits = sum(1 for value in bigrams | trigrams if value in normalized_text)
    ngram_score = ngram_hits / max(1, len(bigrams | trigrams))
    entity_overlap = len(features["entities"] & english_text) / max(1, len(features["entities"]))
    query_coverage = min(1.0, (token_overlap + ngram_score) / 2.0)
    parent_rank_score = 0.0 if parent_rank is None else 1.0 / max(1, parent_rank)
    acronym_matches = one_substitution_acronym_matches(query, text, builder_config) if builder_config else ()
    return {
        "exact_phrase_score": exact,
        "query_coverage_score": query_coverage,
        "ngram_score": ngram_score,
        "token_overlap_score": token_overlap,
        "entity_overlap_score": entity_overlap,
        "parent_rank_score": parent_rank_score,
        "asr_acronym_anchor_score": float(bool(acronym_matches)),
        "asr_acronym_anchor_match_count": float(len(acronym_matches)),
    }


def _make_candidate(
    *, query_id: str, video_id: int, artifact: ParsedSourceArtifact,
    segments: Sequence[RawEvidenceSegment], methods: Iterable[str],
    parent_chunk_ids: Iterable[str] = (), search_candidate_ids: Iterable[str] = (),
    parent_rank: int | None = None, trace_id: str,
) -> EvidenceCandidate:
    validate_raw_span(artifact, segments)
    methods_tuple = tuple(sorted(set(methods)))
    parents = tuple(sorted(set(parent_chunk_ids)))
    search_ids = tuple(sorted(set(search_candidate_ids)))
    source_text = " ".join(segment.source_text.strip() for segment in segments if segment.source_text.strip())
    candidate_id = _candidate_identity(artifact, segments, methods_tuple, parents)
    return EvidenceCandidate(
        candidate_id=candidate_id, query_id=query_id, video_id=video_id,
        source_artifact_id=artifact.source_artifact_id, source_version=artifact.source_version,
        timeline_run_id=segments[0].timeline_run_id,
        segment_ids=tuple(segment.segment_id for segment in segments),
        original_ordinals=tuple(segment.original_ordinal for segment in segments),
        start_time=segments[0].start_time, end_time=segments[-1].end_time,
        source_text=source_text, source_language=segments[0].source_language,
        source_type=segments[0].source_type, parent_chunk_ids=parents,
        search_candidate_ids=search_ids, candidate_methods=methods_tuple,
        segment_count=len(segments), character_count=len(source_text),
        lexical_token_count=len(re.findall(r"[a-z0-9]+|[\u3400-\u9fff]", source_text.casefold())),
        overlap_group_id=_stable_hash("overlap_", {"artifact": artifact.source_artifact_id, "run": segments[0].timeline_run_id, "first": segments[0].segment_id}),
        related_candidate_ids=(), overlap_relation="none", trace_id=trace_id,
        normalization_status="valid", validation_errors=(), parent_rank=parent_rank,
    )


def validate_raw_span(artifact: ParsedSourceArtifact, segments: Sequence[RawEvidenceSegment]) -> None:
    if not segments:
        raise EvidenceContractError("candidate has no segments", code="segment_not_found")
    known = {segment.segment_id: segment for segment in artifact.segments}
    if any(segment.segment_id not in known for segment in segments):
        raise EvidenceContractError("candidate segment is absent from raw source", code="segment_not_found")
    if any(segment.source_artifact_id != artifact.source_artifact_id for segment in segments):
        raise EvidenceContractError("candidate source artifact mismatch", code="source_artifact_mismatch")
    if any(segment.source_version != artifact.source_version for segment in segments):
        raise EvidenceContractError("candidate source version mismatch", code="source_version_mismatch")
    if len({segment.timeline_run_id for segment in segments}) != 1:
        raise EvidenceContractError("candidate crosses timeline runs", code="timeline_run_mismatch")
    ordinals = [segment.original_ordinal for segment in segments]
    if ordinals != sorted(set(ordinals)):
        raise EvidenceContractError("candidate segment order is invalid", code="segment_order_invalid")
    locals_ = [segment.run_local_ordinal for segment in segments]
    if any(right != left + 1 for left, right in zip(locals_, locals_[1:])):
        raise EvidenceContractError("candidate is not run-local contiguous", code="candidate_not_contiguous")
    if segments[0].start_time < 0 or segments[-1].end_time < segments[0].start_time:
        raise EvidenceContractError("candidate time is invalid", code="segment_order_invalid")


def _all_windows(artifact: ParsedSourceArtifact, config: CandidateBuilderConfig) -> list[tuple[RawEvidenceSegment, ...]]:
    by_run: dict[str, list[RawEvidenceSegment]] = {}
    for segment in artifact.segments:
        if segment.evidence_eligible:
            by_run.setdefault(segment.timeline_run_id, []).append(segment)
    result: list[tuple[RawEvidenceSegment, ...]] = []
    for run_id in sorted(by_run):
        values = by_run[run_id]
        for start in range(len(values)):
            selected: list[RawEvidenceSegment] = []
            for segment in values[start:start + config.max_segments_per_candidate]:
                proposed = selected + [segment]
                text = " ".join(value.source_text.strip() for value in proposed)
                duration = proposed[-1].end_time - proposed[0].start_time
                if selected and (len(text) > config.hard_max_characters or duration > config.hard_max_duration_seconds):
                    break
                if len(text) <= config.hard_max_characters and duration <= config.hard_max_duration_seconds:
                    selected.append(segment)
            if selected:
                result.append(tuple(selected))
    return result


def _interval_union_duration(candidates: Sequence[EvidenceCandidate]) -> float:
    intervals = sorted((candidate.start_time, candidate.end_time) for candidate in candidates)
    if not intervals:
        return 0.0
    total = 0.0
    start, end = intervals[0]
    for next_start, next_end in intervals[1:]:
        if next_start <= end:
            end = max(end, next_end)
        else:
            total += end - start
            start, end = next_start, next_end
    return total + end - start


def _segment_jaccard(left: EvidenceCandidate, right: EvidenceCandidate) -> float:
    a, b = set(left.segment_ids), set(right.segment_ids)
    return len(a & b) / max(1, len(a | b))


def _interval_overlap_ratio(left: EvidenceCandidate, right: EvidenceCandidate) -> float:
    overlap = max(0.0, min(left.end_time, right.end_time) - max(left.start_time, right.start_time))
    shorter = min(left.end_time - left.start_time, right.end_time - right.start_time)
    return overlap / max(1e-9, shorter)


_DIRECT_QUERY_SUPPORT_FIELDS = (
    "exact_phrase_score",
    "query_coverage_score",
    "ngram_score",
    "token_overlap_score",
    "entity_overlap_score",
    "asr_acronym_anchor_score",
)


def _candidate_support_signature(candidate: EvidenceCandidate) -> frozenset[str]:
    direct = {
        name for name in _DIRECT_QUERY_SUPPORT_FIELDS
        if float(candidate.score_breakdown.get(name, 0.0)) > 0.0
    }
    if float(candidate.score_breakdown.get("anchor_neighbourhood_score", 0.0)) > 0.0:
        direct.add("anchor_neighbourhood")
    if float(candidate.score_breakdown.get("anchor_follow_score", 0.0)) > 0.0:
        direct.add("anchor_follow")
    return frozenset(direct)


def _candidate_relevance(candidate: EvidenceCandidate) -> float:
    return float(candidate.score_breakdown.get("final_score", 0.0))


def _covered_segments(candidates: Sequence[EvidenceCandidate]) -> set[str]:
    return set().union(*(set(value.segment_ids) for value in candidates), set())


def _set_support_signature(candidates: Sequence[EvidenceCandidate]) -> frozenset[str]:
    return frozenset().union(*(_candidate_support_signature(value) for value in candidates))


def _candidate_redundancy(
    candidate: EvidenceCandidate, candidates: Sequence[EvidenceCandidate],
) -> float:
    return max((
        max(_segment_jaccard(candidate, value), _interval_overlap_ratio(candidate, value))
        for value in candidates if value.candidate_id != candidate.candidate_id
    ), default=0.0)


def _exclusive_segment_count(
    candidate: EvidenceCandidate, candidates: Sequence[EvidenceCandidate],
) -> int:
    others = _covered_segments([
        value for value in candidates if value.candidate_id != candidate.candidate_id
    ])
    return len(set(candidate.segment_ids) - others)


def adaptive_bounded_coverage_swap(
    original_selected: Sequence[EvidenceCandidate],
    outside_pool: Sequence[EvidenceCandidate],
    config: CandidateBuilderConfig,
) -> tuple[tuple[EvidenceCandidate, ...], dict[str, object]]:
    """Apply the F1A deterministic bounded swap without using case or Gold identity."""

    selected = list(original_selected)
    original_ids = [value.candidate_id for value in selected]
    trace: dict[str, object] = {
        "design": ADAPTIVE_BOUNDED_COVERAGE_SWAP_VERSION,
        "builder_version": F1A_CANDIDATE_BUILDER_VERSION,
        "original_top_32": original_ids,
        "outside_eligible_candidate_ids": [],
        "outside_rejection_reasons": [],
        "victim_candidates_ranked": [],
        "swap_iterations": [],
        "final_candidate_ids": original_ids,
        "swap_count": 0,
        "no_swap_reason": None,
    }
    if not config.adaptive_coverage_swap_enabled:
        trace["no_swap_reason"] = "adaptive_swap_disabled"
        return tuple(selected), trace
    if config.within_video_max_candidates != 32 or len(selected) != 32:
        trace["no_swap_reason"] = "candidate_count_not_exactly_32"
        return tuple(selected), trace

    eligible: list[EvidenceCandidate] = []
    rejections: list[dict[str, object]] = []
    selected_ids = set(original_ids)
    for candidate in outside_pool:
        reasons: list[str] = []
        if candidate.candidate_id in selected_ids:
            reasons.append("already_selected")
        if candidate.normalization_status != "valid" or candidate.validation_errors:
            reasons.append("invalid_source_identity_or_timeline")
        if not _candidate_support_signature(candidate):
            reasons.append("query_support_guard_failed")
        if not candidate.search_candidate_ids and "video_level_within_video" not in candidate.candidate_methods:
            reasons.append("retrieval_lineage_missing")
        if (
            candidate.segment_count > config.max_segments_per_candidate
            or candidate.character_count > config.hard_max_characters
            or candidate.end_time - candidate.start_time > config.hard_max_duration_seconds
        ):
            reasons.append("per_window_budget_exceeded")
        if reasons:
            rejections.append({
                "candidate_id": candidate.candidate_id,
                "reasons": sorted(set(reasons)),
            })
        else:
            eligible.append(candidate)
    trace["outside_eligible_candidate_ids"] = [
        value.candidate_id for value in eligible
    ]
    trace["outside_rejection_reasons"] = rejections
    if not eligible:
        trace["no_swap_reason"] = "no_eligible_outside_candidate"
        return tuple(selected), trace

    remaining = list(eligible)
    max_swaps = min(4, max(0, config.adaptive_coverage_swap_max_swaps))
    for iteration in range(1, max_swaps + 1):
        coverage_before_ids = _covered_segments(selected)
        coverage_before = len(coverage_before_ids)
        support_before = _set_support_signature(selected)
        outside_ranked = sorted(
            remaining,
            key=lambda value: (
                -len(_candidate_support_signature(value) - support_before),
                -len(set(value.segment_ids) - coverage_before_ids),
                _candidate_redundancy(value, selected),
                -_candidate_relevance(value),
                value.end_time - value.start_time,
                value.character_count,
                value.candidate_id,
            ),
        )
        chosen_swap: tuple[EvidenceCandidate, EvidenceCandidate, list[EvidenceCandidate]] | None = None
        ranked_victims_for_trace: list[dict[str, object]] = []
        for addition in outside_ranked:
            victims = sorted(
                selected,
                key=lambda value: (
                    -_candidate_redundancy(value, selected),
                    _exclusive_segment_count(value, selected),
                    _candidate_relevance(value),
                    value.candidate_id,
                ),
            )
            if not ranked_victims_for_trace:
                ranked_victims_for_trace = [{
                    "outside_candidate_id": addition.candidate_id,
                    "candidate_id": value.candidate_id,
                    "redundancy": _candidate_redundancy(value, selected),
                    "exclusive_segment_count": _exclusive_segment_count(value, selected),
                    "original_relevance": _candidate_relevance(value),
                } for value in victims]
            for removal in victims:
                trial = [
                    addition if value.candidate_id == removal.candidate_id else value
                    for value in selected
                ]
                if len(trial) != 32 or len({value.candidate_id for value in trial}) != 32:
                    continue
                if not support_before.issubset(_set_support_signature(trial)):
                    continue
                coverage_after = len(_covered_segments(trial))
                if coverage_after <= coverage_before:
                    continue
                if sum(value.character_count for value in trial) > config.within_video_max_total_characters:
                    continue
                if _interval_union_duration(trial) > config.within_video_max_total_union_duration_seconds:
                    continue
                chosen_swap = (addition, removal, trial)
                break
            if chosen_swap:
                break
        if ranked_victims_for_trace:
            trace["victim_candidates_ranked"] = ranked_victims_for_trace
        if chosen_swap is None:
            break
        addition, removal, trial = chosen_swap
        redundancy_before = _candidate_redundancy(removal, selected)
        redundancy_after = _candidate_redundancy(addition, trial)
        coverage_after = len(_covered_segments(trial))
        trace["swap_iterations"].append({
            "iteration": iteration,
            "removed_candidate_id": removal.candidate_id,
            "added_candidate_id": addition.candidate_id,
            "removal_reason": "higher_redundancy_lower_exclusive_supported_coverage",
            "addition_reason": "strict_new_query_supported_coverage",
            "query_support_proof": sorted(_candidate_support_signature(addition)),
            "coverage_before": coverage_before,
            "coverage_after": coverage_after,
            "redundancy_before": redundancy_before,
            "redundancy_after": redundancy_after,
            "candidate_count_after_swap": len(trial),
        })
        selected = trial
        remaining = [
            value for value in remaining
            if value.candidate_id != addition.candidate_id
        ]

    final: list[EvidenceCandidate] = []
    for candidate in selected:
        related = tuple(sorted(
            value.candidate_id for value in selected
            if value.candidate_id != candidate.candidate_id
            and set(value.segment_ids) & set(candidate.segment_ids)
        ))
        final.append(replace(
            candidate,
            related_candidate_ids=related,
            overlap_relation="segment_overlap" if related else "none",
        ))
    trace["final_candidate_ids"] = [value.candidate_id for value in final]
    trace["swap_count"] = len(trace["swap_iterations"])
    if not trace["swap_iterations"]:
        trace["no_swap_reason"] = "no_strict_budget_valid_set_improvement"
    return tuple(final), trace


def _rank_candidates(
    query: str, candidates: Sequence[EvidenceCandidate],
    config: CandidateBuilderConfig, *, swap_trace: dict[str, object] | None = None,
) -> tuple[EvidenceCandidate, ...]:
    scored: list[EvidenceCandidate] = []
    for candidate in candidates:
        breakdown = lexical_score(
            query, candidate.source_text, parent_rank=candidate.parent_rank,
            builder_config=config,
        )
        length_penalty = max(0.0, candidate.character_count - config.preferred_characters[1]) / max(1, config.hard_max_characters)
        final = (
            2 * breakdown["exact_phrase_score"] + 2 * breakdown["query_coverage_score"]
            + 1.25 * breakdown["ngram_score"] + 1.25 * breakdown["token_overlap_score"]
            + breakdown["entity_overlap_score"] + 0.35 * breakdown["parent_rank_score"]
            + config.acronym_anchor_weight * breakdown["asr_acronym_anchor_score"]
            - 0.15 * length_penalty
        )
        scored.append(replace(candidate, score_breakdown={**breakdown, "length_penalty": length_penalty, "overlap_penalty": 0.0, "final_score": final}))
    # A lexical anchor is useful only if its bounded local context can travel with it.
    # This query-independent neighbourhood propagation keeps adjacent windows eligible
    # without using Gold locations and prevents a single repeated phrase from consuming
    # the entire budget.
    propagated: list[EvidenceCandidate] = []
    for candidate in scored:
        neighbours = [
            value.score_breakdown["final_score"] / (1.0 + abs(value.start_time - candidate.start_time) / 60.0)
            for value in scored
            if value.timeline_run_id == candidate.timeline_run_id
            and abs(value.start_time - candidate.start_time) <= 90.0
        ]
        neighbourhood = max(neighbours, default=0.0)
        preceding_anchors = [
            value.score_breakdown["final_score"] / (1.0 + (candidate.start_time - value.start_time) / 60.0)
            for value in scored
            if value.timeline_run_id == candidate.timeline_run_id
            and value.start_time <= candidate.start_time
            and candidate.start_time - value.start_time <= 90.0
            and any(value.score_breakdown[name] > 0 for name in (
                "exact_phrase_score", "query_coverage_score", "ngram_score",
                "token_overlap_score", "entity_overlap_score",
                "asr_acronym_anchor_score",
            ))
        ]
        anchor_follow = max(preceding_anchors, default=0.0)
        breakdown = dict(candidate.score_breakdown)
        breakdown["anchor_neighbourhood_score"] = neighbourhood
        breakdown["anchor_follow_score"] = anchor_follow
        breakdown["final_score"] += 0.8 * neighbourhood + 0.8 * anchor_follow
        propagated.append(replace(candidate, score_breakdown=breakdown))
    scored = propagated
    scored.sort(key=lambda value: (value.timeline_run_id, value.start_time, value.candidate_id))
    anchors = [
        value for value in scored
        if any(value.score_breakdown[name] > 0 for name in (
            "exact_phrase_score", "query_coverage_score", "ngram_score",
            "token_overlap_score", "entity_overlap_score",
            "asr_acronym_anchor_score",
        ))
    ]
    regions: list[list[EvidenceCandidate]] = []
    for anchor in anchors:
        if (
            not regions or regions[-1][-1].timeline_run_id != anchor.timeline_run_id
            or anchor.start_time - regions[-1][-1].start_time > 30.0
        ):
            regions.append([anchor])
        else:
            regions[-1].append(anchor)
    region_by_candidate: dict[str, int | None] = {}
    for candidate in scored:
        matches = [
            (min(abs(candidate.start_time - anchor.start_time) for anchor in region), index)
            for index, region in enumerate(regions)
            if region[0].timeline_run_id == candidate.timeline_run_id
            and min(abs(candidate.start_time - anchor.start_time) for anchor in region) <= 90.0
        ]
        region_by_candidate[candidate.candidate_id] = min(matches)[1] if matches else None
    # Reserve enough capacity for the bounded left/right context around even a
    # single sparse anchor. Dense regions still receive proportionally more.
    region_weights = {index: max(8, len(region)) for index, region in enumerate(regions)}
    chosen: list[EvidenceCandidate] = []
    total_chars = 0
    remaining = list(scored)
    region_counts: dict[int, int] = {}
    while remaining and len(chosen) < config.within_video_max_candidates:
        def allocation_score(value: EvidenceCandidate) -> tuple[float, float, str]:
            region = region_by_candidate[value.candidate_id]
            if region is None:
                allocation = 0.05
            else:
                allocation = region_weights[region] / (region_counts.get(region, 0) + 1)
            max_interval_overlap = max((_interval_overlap_ratio(value, item) for item in chosen), default=0.0)
            already_covered = set().union(*(set(item.segment_ids) for item in chosen), set())
            new_segment_fraction = len(set(value.segment_ids) - already_covered) / max(1, len(value.segment_ids))
            diversity = max(0.05, (1.0 - 0.8 * max_interval_overlap) * new_segment_fraction ** 2)
            return (-value.score_breakdown["final_score"] * allocation * diversity, value.start_time, value.candidate_id)
        remaining.sort(key=allocation_score)
        candidate = remaining.pop(0)
        relation = [
            value for value in chosen
            if _segment_jaccard(candidate, value) >= config.near_duplicate_jaccard_threshold
            or _interval_overlap_ratio(candidate, value) >= config.near_duplicate_jaccard_threshold
        ]
        if relation:
            continue
        if total_chars + candidate.character_count > config.within_video_max_total_characters:
            continue
        if _interval_union_duration(chosen + [candidate]) > config.within_video_max_total_union_duration_seconds:
            continue
        related = tuple(sorted(value.candidate_id for value in chosen if set(value.segment_ids) & set(candidate.segment_ids)))
        chosen.append(replace(candidate, related_candidate_ids=related, overlap_relation="segment_overlap" if related else "none"))
        total_chars += candidate.character_count
        region = region_by_candidate[candidate.candidate_id]
        if region is not None:
            region_counts[region] = region_counts.get(region, 0) + 1
    chosen_ids = {value.candidate_id for value in chosen}
    outside_pool = [
        value for value in scored if value.candidate_id not in chosen_ids
    ]
    final, adaptive_trace = adaptive_bounded_coverage_swap(
        chosen, outside_pool, config,
    )
    if swap_trace is not None:
        swap_trace.update(adaptive_trace)
    return final


def build_within_video_candidates(
    query: str, video_id: int, source_artifact_version: str,
    raw_transcript: ParsedSourceArtifact, config: CandidateBuilderConfig | None = None,
    *, query_id: str = "query", trace_id: str | None = None,
) -> EvidenceCandidateSet:
    config = config or CandidateBuilderConfig()
    if raw_transcript.source_version != source_artifact_version:
        raise EvidenceContractError("expected and actual source versions differ", code="source_version_mismatch")
    if raw_transcript.validation_status not in {"valid_single_run", "valid_multiple_runs"}:
        raise EvidenceContractError("raw source is unavailable", code="raw_source_unavailable")
    trace_id = trace_id or _stable_hash("trace_", {"query_id": query_id, "video_id": video_id, "version": source_artifact_version, "config": asdict(config)})
    candidates = [
        _make_candidate(query_id=query_id, video_id=video_id, artifact=raw_transcript,
                        segments=window, methods=("boundary_preserving", "query_anchor"), trace_id=trace_id)
        for window in _all_windows(raw_transcript, config)
    ]
    swap_trace: dict[str, object] = {}
    ranked = _rank_candidates(query, candidates, config, swap_trace=swap_trace)
    return EvidenceCandidateSet(
        query_id=query_id, original_query=query, candidates=ranked,
        evaluation_track="oracle_video_conditional", end_to_end_claim_eligible=False,
        trace={"evaluation_track": "oracle_video_conditional", "oracle_video_used": True,
               "video_id": video_id, "source_artifact_id": raw_transcript.source_artifact_id,
               "source_version": raw_transcript.source_version,
               "timeline_run_ids": [run.timeline_run_id for run in raw_transcript.timeline_runs],
               "candidate_ids": [candidate.candidate_id for candidate in ranked],
               "config_id": config.config_id,
               "candidate_allocation_policy_version": config.candidate_allocation_policy_version,
               "adaptive_bounded_coverage_swap": swap_trace},
    )


def _merge_exact(candidates: Sequence[EvidenceCandidate]) -> tuple[EvidenceCandidate, ...]:
    merged: dict[tuple[str, str, str, tuple[str, ...]], EvidenceCandidate] = {}
    for candidate in candidates:
        key = (candidate.source_artifact_id, candidate.source_version, candidate.timeline_run_id, candidate.segment_ids)
        existing = merged.get(key)
        if existing is None:
            merged[key] = candidate
            continue
        methods = tuple(sorted(set(existing.candidate_methods) | set(candidate.candidate_methods)))
        parents = tuple(sorted(set(existing.parent_chunk_ids) | set(candidate.parent_chunk_ids)))
        search_ids = tuple(sorted(set(existing.search_candidate_ids) | set(candidate.search_candidate_ids)))
        merged[key] = replace(
            existing, candidate_id=_candidate_identity_from_fields(existing, methods, parents),
            candidate_methods=methods, parent_chunk_ids=parents, search_candidate_ids=search_ids,
        )
    return tuple(merged.values())


def resolve_from_search_candidates(
    query: str, search_candidate_set: Mapping[str, object], raw_source_resolver: RawSourceResolver,
    config: CandidateBuilderConfig | None = None, *, query_id: str = "query",
    search_candidate_set_id: str = "", execution_manifest_identity: str = "",
) -> EvidenceCandidateSet:
    config = config or CandidateBuilderConfig()
    raw_units = list(search_candidate_set.get("raw_unit_candidates", []))
    videos = list(search_candidate_set.get("video_candidates", []))
    legal_video_ids = {int(value["video_id"]) for value in videos if value.get("video_id") is not None}
    if not legal_video_ids:
        return EvidenceCandidateSet(
            query_id=query_id, original_query=query, candidates=(), evaluation_track="frozen_v3_end_to_end",
            end_to_end_claim_eligible=True,
            trace={"evaluation_track": "frozen_v3_end_to_end", "oracle_video_used": False,
                   "search_candidate_set_id": search_candidate_set_id, "search_candidate_ids": []},
            normalization_status="typed_empty", validation_errors=("upstream_retrieval_failure",),
            failure_category="upstream_retrieval_failure",
        )
    trace_id = _stable_hash("trace_", {"query_id": query_id, "set": search_candidate_set_id, "config": asdict(config)})
    built: list[EvidenceCandidate] = []
    chunk_video_ids: set[int] = set()
    for raw in raw_units:
        video_id = int(raw["video_id"])
        if video_id not in legal_video_ids or raw.get("unit_type") != "transcript_chunk" or not raw.get("candidate_eligibility"):
            continue
        artifact = raw_source_resolver(video_id)
        if artifact.source_version != raw.get("source_version") or artifact.source_artifact_id != raw.get("source_artifact_id"):
            raise EvidenceContractError("frozen search candidate source identity mismatch", code="source_version_mismatch")
        by_id = {segment.segment_id: segment for segment in artifact.segments}
        try:
            mapped = [by_id[value] for value in raw.get("segment_ids", [])]
        except KeyError as exc:
            raise EvidenceContractError("exact mapped segment is absent", code="segment_not_found") from exc
        validate_raw_span(artifact, mapped)
        allowed = set(raw.get("segment_ids", []))
        for window in _all_windows(artifact, config):
            if set(segment.segment_id for segment in window).issubset(allowed):
                built.append(_make_candidate(
                    query_id=query_id, video_id=video_id, artifact=artifact, segments=window,
                    methods=("chunk_mapped", "query_anchor", "boundary_preserving"),
                    parent_chunk_ids=(str(raw["unit_id"]),), search_candidate_ids=(str(raw["unit_id"]),),
                    parent_rank=int(raw["raw_rank"]), trace_id=trace_id,
                ))
        chunk_video_ids.add(video_id)
    for video in videos:
        video_id = int(video["video_id"])
        if video_id in chunk_video_ids or not video.get("video_level_hit_present"):
            continue
        artifact = raw_source_resolver(video_id)
        within = build_within_video_candidates(query, video_id, artifact.source_version, artifact, config, query_id=query_id, trace_id=trace_id)
        rank = int(video["product_rank"])
        search_id = str(video["best_unit_id"])
        by_id = {segment.segment_id: segment for segment in artifact.segments}
        built.extend(
            _make_candidate(
                query_id=query_id, video_id=video_id, artifact=artifact,
                segments=[by_id[value] for value in candidate.segment_ids],
                methods=tuple(sorted(set(candidate.candidate_methods) | {"video_level_within_video"})),
                search_candidate_ids=(search_id,), parent_rank=rank, trace_id=trace_id,
            )
            for candidate in within.candidates
        )
    merged = _merge_exact(built)
    by_video: dict[int, list[EvidenceCandidate]] = {}
    for candidate in merged:
        by_video.setdefault(candidate.video_id, []).append(candidate)
    ranked_values: list[EvidenceCandidate] = []
    video_order = sorted(
        by_video,
        key=lambda video_id: (
            min((value.parent_rank for value in by_video[video_id] if value.parent_rank is not None), default=10**9),
            video_id,
        ),
    )
    per_video_swap_traces: dict[str, object] = {}
    remaining_query_swap_budget = min(
        4, max(0, config.adaptive_coverage_swap_max_swaps),
    )
    for video_id in video_order:
        swap_trace: dict[str, object] = {}
        video_config = replace(
            config,
            adaptive_coverage_swap_max_swaps=remaining_query_swap_budget,
        )
        ranked_values.extend(_rank_candidates(
            query, by_video[video_id], video_config, swap_trace=swap_trace,
        ))
        remaining_query_swap_budget -= int(swap_trace.get("swap_count", 0))
        per_video_swap_traces[str(video_id)] = swap_trace
    ranked = tuple(ranked_values)
    return EvidenceCandidateSet(
        query_id=query_id, original_query=query, candidates=ranked,
        evaluation_track="frozen_v3_end_to_end", end_to_end_claim_eligible=True,
        trace={"evaluation_track": "frozen_v3_end_to_end", "oracle_video_used": False,
               "execution_manifest_identity": execution_manifest_identity,
               "search_candidate_set_id": search_candidate_set_id,
               "search_candidate_ids": [str(value.get("unit_id")) for value in raw_units],
               "paths": ["chunk" if chunk_video_ids else "video_level"],
               "candidate_ids": [candidate.candidate_id for candidate in ranked],
               "candidate_allocation_policy_version": config.candidate_allocation_policy_version,
               "adaptive_bounded_coverage_swap": per_video_swap_traces,
               "adaptive_bounded_coverage_swap_total": sum(
                   int(value.get("swap_count", 0))
                   for value in per_video_swap_traces.values()
               ),
               "adaptive_bounded_coverage_swap_query_limit": 4},
    )


def select_deterministic_bundle(
    query: str, candidate_set: EvidenceCandidateSet, config: SelectorConfig | None = None,
) -> EvidenceBundle | None:
    config = config or SelectorConfig()
    if not candidate_set.candidates:
        return None
    by_video: dict[int, list[EvidenceCandidate]] = {}
    for candidate in candidate_set.candidates:
        by_video.setdefault(candidate.video_id, []).append(candidate)
    best_bundle: EvidenceBundle | None = None
    for video_id in sorted(by_video):
        pool = list(by_video[video_id])
        selected: list[EvidenceCandidate] = []
        covered_features: set[str] = set()
        query_features = _query_features(query)
        query_atoms = set(query_features["english"]) | set(query_features["bigrams"]) | set(query_features["trigrams"])
        decisions: list[dict[str, object]] = []
        while pool and len(selected) < config.max_candidates_per_bundle:
            ranked: list[tuple[float, EvidenceCandidate, dict[str, float]]] = []
            for candidate in pool:
                lexical = lexical_score(query, candidate.source_text, parent_rank=candidate.parent_rank)
                normalized_candidate = candidate.source_text.casefold()
                features = {value for value in query_atoms if value in normalized_candidate}
                marginal = len(features - covered_features) / max(1, len(query_atoms))
                overlap = max((_segment_jaccard(candidate, value) for value in selected), default=0.0)
                if selected:
                    gap = min(max(0.0, candidate.start_time - value.end_time, value.start_time - candidate.end_time) for value in selected)
                    locality = 1.0 / (1.0 + gap / 60.0)
                else:
                    locality = 0.0
                length_penalty = max(0.0, candidate.character_count - 350) / 500.0
                final = (
                    config.exact_phrase_weight * lexical["exact_phrase_score"]
                    + config.query_coverage_weight * lexical["query_coverage_score"]
                    + config.ngram_weight * lexical["ngram_score"]
                    + config.token_overlap_weight * lexical["token_overlap_score"]
                    + config.entity_overlap_weight * lexical["entity_overlap_score"]
                    + config.parent_rank_weight * lexical["parent_rank_score"]
                    + config.marginal_coverage_weight * marginal + config.locality_weight * locality
                    - config.length_penalty_weight * length_penalty - config.overlap_penalty_weight * overlap
                )
                ranked.append((final, candidate, {**lexical, "length_penalty": length_penalty,
                                                   "overlap_penalty": overlap, "marginal_query_term_coverage": marginal,
                                                   "locality_score": locality, "final_score": final}))
            ranked.sort(key=lambda value: (-value[0], value[1].start_time, value[1].candidate_id))
            score, chosen, breakdown = ranked[0]
            selected.append(chosen)
            pool.remove(chosen)
            covered_features |= {value for value in query_atoms if value in chosen.source_text.casefold()}
            decisions.append({"candidate_id": chosen.candidate_id, "score": score, "score_breakdown": breakdown})
        selected.sort(key=lambda value: (value.start_time, value.candidate_id))
        union_duration = _interval_union_duration(selected)
        score = sum(value["score"] for value in decisions) - config.bundle_candidate_count_penalty * len(selected) - config.bundle_duration_penalty * union_duration
        candidate_ids = tuple(value.candidate_id for value in selected)
        bundle_id = _stable_hash("bundle_", {"contract_version": EVIDENCE_BUNDLE_CONTRACT_VERSION,
                                              "query_id": candidate_set.query_id, "video_id": video_id,
                                              "candidate_ids": list(candidate_ids), "selector": config.config_id})
        bundle = EvidenceBundle(
            bundle_id=bundle_id, query_id=candidate_set.query_id, video_id=video_id,
            source_artifact_ids=tuple(sorted({value.source_artifact_id for value in selected})),
            source_versions=tuple(sorted({value.source_version for value in selected})),
            timeline_run_ids=tuple(sorted({value.timeline_run_id for value in selected})),
            candidate_ids=candidate_ids,
            normalized_spans=tuple({"candidate_id": value.candidate_id, "timeline_run_id": value.timeline_run_id,
                                    "start_time": value.start_time, "end_time": value.end_time,
                                    "segment_ids": list(value.segment_ids)} for value in selected),
            union_duration=union_duration, source_texts=tuple(value.source_text for value in selected),
            selection_method=DETERMINISTIC_SELECTOR_VERSION, score=score,
            score_breakdown={"candidate_score_sum": sum(value["score"] for value in decisions),
                             "candidate_count_penalty": config.bundle_candidate_count_penalty * len(selected),
                             "duration_penalty": config.bundle_duration_penalty * union_duration,
                             "final_score": score},
            evaluation_track=candidate_set.evaluation_track,
            end_to_end_claim_eligible=candidate_set.end_to_end_claim_eligible,
            trace_id=_stable_hash("trace_", {"bundle": bundle_id, "decisions": decisions}),
            normalization_status="valid", validation_errors=(),
        )
        if best_bundle is None or (-bundle.score, bundle.bundle_id) < (-best_bundle.score, best_bundle.bundle_id):
            best_bundle = bundle
    return best_bundle


def _selector_text_features(value: str) -> set[str]:
    normalized = re.sub(r"\s+", " ", value.casefold()).strip()
    latin = set(re.findall(r"[a-z][a-z0-9_.+-]{1,}", normalized))
    chinese = "".join(re.findall(r"[\u3400-\u9fff]+", normalized))
    return latin | {
        chinese[index:index + 2]
        for index in range(max(0, len(chinese) - 1))
    }


def _selector_base_relevance(query: str, candidate: EvidenceCandidate) -> float:
    lexical = lexical_score(
        query, candidate.source_text, parent_rank=candidate.parent_rank,
    )
    return (
        2.0 * lexical["exact_phrase_score"]
        + 2.0 * lexical["query_coverage_score"]
        + 1.25 * lexical["ngram_score"]
        + 1.25 * lexical["token_overlap_score"]
        + lexical["entity_overlap_score"]
        + 0.35 * lexical["parent_rank_score"]
    )


def select_greedy_marginal_bundle(
    query: str,
    candidate_set: EvidenceCandidateSet,
    config: MarginalSelectorConfig | None = None,
) -> EvidenceBundle | None:
    """Assemble a deterministic bundle using only generic runtime evidence signals."""

    config = config or MarginalSelectorConfig()
    valid_candidates = tuple(
        candidate for candidate in candidate_set.candidates
        if candidate.normalization_status == "valid"
        and not candidate.validation_errors
        and candidate.segment_ids
        and candidate.timeline_run_id
        and candidate.source_artifact_id
        and candidate.source_version
        and candidate.end_time >= candidate.start_time
    )
    if not valid_candidates:
        return None

    query_features = _query_features(query)
    query_atoms = (
        set(query_features["english"])
        | set(query_features["bigrams"])
        | set(query_features["trigrams"])
    )
    raw_lexical = {
        candidate.candidate_id: _selector_base_relevance(query, candidate)
        for candidate in valid_candidates
    }
    raw_builder = {
        candidate.candidate_id: max(
            0.0, float(candidate.score_breakdown.get("final_score", 0.0)),
        )
        for candidate in valid_candidates
    }
    lexical_scale = max(raw_lexical.values(), default=1.0) or 1.0
    builder_scale = max(raw_builder.values(), default=1.0) or 1.0

    by_video: dict[int, list[EvidenceCandidate]] = {}
    for candidate in valid_candidates:
        by_video.setdefault(candidate.video_id, []).append(candidate)

    best_bundle: EvidenceBundle | None = None
    for video_id in sorted(by_video):
        pool = list(by_video[video_id])
        selected: list[EvidenceCandidate] = []
        covered_query_atoms: set[str] = set()
        covered_segments: set[str] = set()
        covered_regions: set[tuple[str, int]] = set()
        decisions: list[dict[str, object]] = []

        while pool and len(selected) < config.max_candidates_per_bundle:
            ranked: list[tuple[float, EvidenceCandidate, dict[str, float]]] = []
            for candidate in pool:
                candidate_text = candidate.source_text.casefold()
                candidate_query_atoms = {
                    atom for atom in query_atoms if atom in candidate_text
                }
                lexical_relevance = raw_lexical[candidate.candidate_id] / lexical_scale
                builder_relevance = raw_builder[candidate.candidate_id] / builder_scale
                atom_novelty = len(
                    candidate_query_atoms - covered_query_atoms,
                ) / max(1, len(query_atoms))
                new_segment_fraction = len(
                    set(candidate.segment_ids) - covered_segments,
                ) / max(1, len(candidate.segment_ids))
                region = (
                    candidate.timeline_run_id,
                    int(candidate.start_time // config.temporal_region_seconds),
                )
                region_novelty = float(region not in covered_regions)
                if selected:
                    temporal_distance = min(
                        max(
                            0.0,
                            candidate.start_time - value.end_time,
                            value.start_time - candidate.end_time,
                        )
                        for value in selected
                    )
                    temporal_novelty = region_novelty * min(
                        1.0,
                        temporal_distance / config.temporal_distance_cap_seconds,
                    )
                else:
                    temporal_novelty = 0.0
                segment_redundancy = max(
                    (_segment_jaccard(candidate, value) for value in selected),
                    default=0.0,
                )
                temporal_overlap = max(
                    (_interval_overlap_ratio(candidate, value) for value in selected),
                    default=0.0,
                )
                candidate_text_features = _selector_text_features(candidate.source_text)
                text_redundancy = max((
                    len(candidate_text_features & _selector_text_features(value.source_text))
                    / max(1, len(candidate_text_features | _selector_text_features(value.source_text)))
                    for value in selected
                ), default=0.0)
                score = (
                    config.lexical_relevance_weight * lexical_relevance
                    + config.builder_relevance_weight * builder_relevance
                    + config.query_atom_novelty_weight * atom_novelty
                    + config.new_segment_weight * new_segment_fraction
                    + config.temporal_region_novelty_weight * temporal_novelty
                    - config.segment_redundancy_weight * segment_redundancy
                    - config.temporal_overlap_weight * temporal_overlap
                    - config.text_redundancy_weight * text_redundancy
                )
                breakdown = {
                    "lexical_relevance": lexical_relevance,
                    "builder_relevance": builder_relevance,
                    "query_atom_novelty": atom_novelty,
                    "new_segment_fraction": new_segment_fraction,
                    "temporal_region_novelty": temporal_novelty,
                    "segment_redundancy": segment_redundancy,
                    "temporal_overlap": temporal_overlap,
                    "text_redundancy": text_redundancy,
                    "final_score": score,
                }
                ranked.append((score, candidate, breakdown))

            ranked.sort(key=lambda value: (
                -value[0], value[1].start_time, value[1].candidate_id,
            ))
            score, chosen, breakdown = ranked[0]
            selected.append(chosen)
            pool.remove(chosen)
            covered_query_atoms |= {
                atom for atom in query_atoms if atom in chosen.source_text.casefold()
            }
            covered_segments |= set(chosen.segment_ids)
            covered_regions.add((
                chosen.timeline_run_id,
                int(chosen.start_time // config.temporal_region_seconds),
            ))
            decisions.append({
                "candidate_id": chosen.candidate_id,
                "score": score,
                "score_breakdown": breakdown,
            })

        selected.sort(key=lambda value: (value.start_time, value.candidate_id))
        union_duration = _interval_union_duration(selected)
        pair_redundancies = [
            max(_segment_jaccard(left, right), _interval_overlap_ratio(left, right))
            for index, left in enumerate(selected)
            for right in selected[index + 1:]
        ]
        query_coverage = len(covered_query_atoms) / max(1, len(query_atoms))
        relevance_values = [
            (
                config.lexical_relevance_weight
                * raw_lexical[value.candidate_id] / lexical_scale
                + config.builder_relevance_weight
                * raw_builder[value.candidate_id] / builder_scale
            )
            for value in selected
        ]
        segment_diversity = len(covered_segments) / max(
            1, sum(len(value.segment_ids) for value in selected),
        )
        temporal_diversity = len(covered_regions) / max(1, len(selected))
        redundancy = sum(pair_redundancies) / max(1, len(pair_redundancies))
        bundle_score = (
            config.bundle_query_coverage_weight * query_coverage
            + config.bundle_peak_relevance_weight * max(relevance_values, default=0.0)
            + config.bundle_mean_relevance_weight
            * (sum(relevance_values) / max(1, len(relevance_values)))
            + config.bundle_segment_diversity_weight * segment_diversity
            + config.bundle_temporal_diversity_weight * temporal_diversity
            - config.bundle_redundancy_weight * redundancy
            - config.bundle_duration_penalty * union_duration
        )
        candidate_ids = tuple(value.candidate_id for value in selected)
        bundle_id = _stable_hash("bundle_", {
            "contract_version": EVIDENCE_BUNDLE_CONTRACT_VERSION,
            "query_id": candidate_set.query_id,
            "video_id": video_id,
            "candidate_ids": list(candidate_ids),
            "selector": config.config_id,
        })
        bundle = EvidenceBundle(
            bundle_id=bundle_id,
            query_id=candidate_set.query_id,
            video_id=video_id,
            source_artifact_ids=tuple(sorted({
                value.source_artifact_id for value in selected
            })),
            source_versions=tuple(sorted({
                value.source_version for value in selected
            })),
            timeline_run_ids=tuple(sorted({
                value.timeline_run_id for value in selected
            })),
            candidate_ids=candidate_ids,
            normalized_spans=tuple({
                "candidate_id": value.candidate_id,
                "timeline_run_id": value.timeline_run_id,
                "start_time": value.start_time,
                "end_time": value.end_time,
                "segment_ids": list(value.segment_ids),
            } for value in selected),
            union_duration=union_duration,
            source_texts=tuple(value.source_text for value in selected),
            selection_method=DETERMINISTIC_SELECTOR_V2_VERSION,
            score=bundle_score,
            score_breakdown={
                "query_atom_coverage": query_coverage,
                "peak_relevance": max(relevance_values, default=0.0),
                "mean_relevance": (
                    sum(relevance_values) / max(1, len(relevance_values))
                ),
                "segment_diversity": segment_diversity,
                "temporal_diversity": temporal_diversity,
                "mean_redundancy": redundancy,
                "duration_penalty": config.bundle_duration_penalty * union_duration,
                "final_score": bundle_score,
            },
            evaluation_track=candidate_set.evaluation_track,
            end_to_end_claim_eligible=candidate_set.end_to_end_claim_eligible,
            trace_id=_stable_hash("trace_", {
                "bundle": bundle_id,
                "decisions": decisions,
            }),
            normalization_status="valid",
            validation_errors=(),
        )
        if best_bundle is None or (
            -bundle.score, bundle.bundle_id
        ) < (-best_bundle.score, best_bundle.bundle_id):
            best_bundle = bundle
    return best_bundle


def validate_bundle(bundle: EvidenceBundle, candidate_set: EvidenceCandidateSet) -> None:
    candidates = {candidate.candidate_id: candidate for candidate in candidate_set.candidates}
    if any(candidate_id not in candidates for candidate_id in bundle.candidate_ids):
        raise EvidenceContractError("bundle references an unknown candidate", code="invalid_bundle_reference")
    if len({candidates[value].video_id for value in bundle.candidate_ids}) != 1:
        raise EvidenceContractError("bundle candidates must belong to one video", code="invalid_bundle_reference")


def interval_union_duration(intervals: Iterable[tuple[float, float]]) -> float:
    values = sorted(intervals)
    if not values:
        return 0.0
    total = 0.0
    start, end = values[0]
    for next_start, next_end in values[1:]:
        if next_start <= end:
            end = max(end, next_end)
        else:
            total += end - start
            start, end = next_start, next_end
    return total + end - start
