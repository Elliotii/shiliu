from shiliu.eval_v3_5.scoring_identity_bridge import (
    CanonicalVideoIdentity,
    VideoIdentityCanonicalizer,
    canonical_scoring_identity,
    complete_group_ids,
    covered_aspect_ids,
    covered_span_ids,
)


CANONICALIZER = VideoIdentityCanonicalizer(
    [
        CanonicalVideoIdentity("bilibili", "BVfixture", 41, 1),
        CanonicalVideoIdentity("bilibili", "BVother", 42, 1),
    ],
    source="synthetic-authoritative-mapping",
    source_sha256="fixture",
)


def evidence() -> dict:
    return {
        "span_registry": [{
            "span_id": "S1", "source_version": "version-A",
            "source_type": "official_subtitle", "video_id": "bilibili:BVfixture",
            "timeline_run_id": "timeline-A", "segment_ids": ["s1", "s2"],
            "start_time": 1.0, "end_time": 3.0,
        }],
        "acceptable_evidence_groups": [{
            "group_id": "G1", "required_span_sets": [{"required_span_ids": ["S1"]}],
        }],
        "aspect_evidence_options": [{
            "aspect_id": "A1", "alternative_sets": [{"required_span_ids": ["S1"]}],
        }],
        "required_aspects": [{"aspect_id": "A1", "materiality": "material"}],
    }


def candidate(candidate_id: str, **changes: object) -> dict:
    value = {
        "candidate_id": candidate_id, "source_artifact_id": "source-A",
        "source_version": "version-A", "source_type": "official_subtitle",
        "video_id": 41, "timeline_run_id": "timeline-A",
        "segment_ids": ["s1", "s2"], "start_time": 1.0, "end_time": 3.0,
    }
    value.update(changes)
    return value


def test_same_video_bvid_and_numeric_id_are_canonically_equal() -> None:
    gold = canonical_scoring_identity(evidence()["span_registry"][0], CANONICALIZER)
    runtime = canonical_scoring_identity(candidate("runtime"), CANONICALIZER)
    assert gold is not None and runtime is not None
    assert gold.video == runtime.video
    assert covered_span_ids(evidence(), [candidate("runtime")], CANONICALIZER) == {"S1"}


def test_different_video_bvid_and_numeric_id_are_not_equal() -> None:
    assert covered_span_ids(
        evidence(), [candidate("runtime", video_id=42)], CANONICALIZER,
    ) == set()


def test_unknown_or_unmapped_identity_is_a_conservative_non_match() -> None:
    assert covered_span_ids(
        evidence(), [candidate("runtime", video_id=999)], CANONICALIZER,
    ) == set()


def test_same_video_but_wrong_timeline_does_not_match() -> None:
    assert covered_span_ids(
        evidence(), [candidate("runtime", timeline_run_id="other")], CANONICALIZER,
    ) == set()


def test_same_video_and_timeline_but_wrong_segment_does_not_match() -> None:
    assert covered_span_ids(
        evidence(), [candidate("runtime", segment_ids=["s1"])], CANONICALIZER,
    ) == set()


def test_candidate_id_only_is_not_sufficient_for_match() -> None:
    assert covered_span_ids(evidence(), [{"candidate_id": "S1"}], CANONICALIZER) == set()


def test_candidate_id_is_not_the_scoring_identity() -> None:
    covered = covered_span_ids(evidence(), [candidate("candidate-before")], CANONICALIZER)
    assert covered_span_ids(evidence(), [candidate("candidate-after")], CANONICALIZER) == covered


def test_preserved_lineage_matches_when_segments_are_split_across_candidates() -> None:
    candidates = [
        candidate("candidate-a", segment_ids=["s1"]),
        candidate("candidate-b", segment_ids=["s2"]),
    ]
    covered = covered_span_ids(evidence(), candidates, CANONICALIZER)
    assert covered == {"S1"}
    assert complete_group_ids(evidence(), covered) == ["G1"]
    assert covered_aspect_ids(evidence(), covered) == ["A1"]


def test_canonical_identity_preserves_source_timeline_segments_and_times() -> None:
    identity = canonical_scoring_identity(candidate("candidate"), CANONICALIZER)
    assert identity is not None
    assert identity.source_type == "official"
    assert identity.provenance.underlying_evidence_source == "raw_subtitle"
    assert identity.timeline_run_id == "timeline-A"
    assert identity.segment_ids == ("s1", "s2")
    assert (identity.start_time, identity.end_time) == (1.0, 3.0)


def test_query_specific_rules_are_absent() -> None:
    assert not hasattr(CANONICALIZER, "query_id")
