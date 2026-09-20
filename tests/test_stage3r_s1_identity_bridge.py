from __future__ import annotations

from dataclasses import replace
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from shiliu.evidence.contracts import EvidenceContractError
from shiliu.eval_v3_5 import stage3r_s1
from shiliu.eval_v3_5.stage3r_s1 import (
    CanonicalSegmentKey,
    SegmentIdentity,
    assert_unique_identity_universe,
    gold_group_hit,
    project_gold_segment_identity,
    project_runtime_segment_identity,
    span_covered,
    text_digest,
    validate_exact_mapping,
)


def raw_segment(**overrides):
    values = {
        "segment_id": "segment_" + "a" * 64,
        "source_artifact_id": "source_artifact_" + "b" * 64,
        "source_version": "c" * 64,
        "timeline_run_id": "timeline_run_" + "d" * 64,
        "original_ordinal": 41,
        "start_time": 10.0,
        "end_time": 12.0,
        "source_text": "exact text",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def raw_artifact(segment=None):
    segment = segment or raw_segment()
    return SimpleNamespace(
        source_artifact_id=segment.source_artifact_id,
        source_version=segment.source_version,
        segments=(segment,),
    )


def gold_row():
    segment = raw_segment()
    return project_gold_segment_identity(
        case_id="CASE", gold_segment_id="BV1abc_seg_000042",
        source_artifact_id=segment.source_artifact_id,
        source_version=segment.source_version,
        timeline_run_id=segment.timeline_run_id,
        source_bvid="BV1abc", raw_artifact=raw_artifact(segment),
    )


def runtime_row():
    segment = raw_segment()
    candidate = {
        "candidate_id": "candidate",
        "source_artifact_id": segment.source_artifact_id,
        "source_version": segment.source_version,
        "timeline_run_id": segment.timeline_run_id,
    }
    identity = stage3r_s1.identity_from_raw_segment(segment)
    return project_runtime_segment_identity(
        candidate=candidate, runtime_segment_id=segment.segment_id,
        segment_ordinal=segment.original_ordinal,
        raw_identities={segment.segment_id: identity},
    )


def test_stage3r_s1_same_segment_different_id_namespace_maps_exactly() -> None:
    assert gold_row()["gold_segment_id"] != runtime_row()["runtime_segment_id"]
    assert validate_exact_mapping(gold_row(), runtime_row()) == "exact_identity_match"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_artifact_id", ""),
        ("source_version", ""),
        ("timeline_run_id", ""),
        ("segment_ordinal", -1),
    ],
)
def test_canonical_key_required_fields(field: str, value: object) -> None:
    values = {
        "source_artifact_id": "artifact", "source_version": "version",
        "timeline_run_id": "timeline", "segment_ordinal": 0,
    }
    values[field] = value
    with pytest.raises(ValueError):
        CanonicalSegmentKey(**values)


def test_stage3r_s1_canonical_key_requires_source_artifact() -> None:
    test_canonical_key_required_fields("source_artifact_id", "")


def test_stage3r_s1_canonical_key_requires_source_version() -> None:
    test_canonical_key_required_fields("source_version", "")


def test_stage3r_s1_canonical_key_requires_timeline_run() -> None:
    test_canonical_key_required_fields("timeline_run_id", "")


def test_stage3r_s1_canonical_key_requires_segment_ordinal() -> None:
    test_canonical_key_required_fields("segment_ordinal", -1)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("source_artifact_id", "other", "source_artifact_mismatch"),
        ("source_version", "other", "source_version_mismatch"),
        ("timeline_run_id", "other", "timeline_run_mismatch"),
        ("segment_ordinal", 99, "ordinal_mismatch"),
    ],
)
def test_rejects_structured_mismatch(field: str, value: object, expected: str) -> None:
    runtime = runtime_row()
    runtime["canonical_key"] = {**runtime["canonical_key"], field: value}
    assert validate_exact_mapping(gold_row(), runtime) == expected


def test_stage3r_s1_rejects_cross_source_mapping() -> None:
    test_rejects_structured_mismatch("source_artifact_id", "other", "source_artifact_mismatch")


def test_stage3r_s1_rejects_cross_version_mapping() -> None:
    test_rejects_structured_mismatch("source_version", "other", "source_version_mismatch")


def test_stage3r_s1_rejects_cross_timeline_mapping() -> None:
    test_rejects_structured_mismatch("timeline_run_id", "other", "timeline_run_mismatch")


def test_stage3r_s1_rejects_ambiguous_mapping() -> None:
    one = stage3r_s1.identity_from_raw_segment(raw_segment())
    two = replace(one, physical_segment_id="segment_" + "f" * 64)
    with pytest.raises(EvidenceContractError):
        assert_unique_identity_universe([one, two])


def test_stage3r_s1_rejects_duplicate_canonical_key() -> None:
    test_stage3r_s1_rejects_ambiguous_mapping()


def test_stage3r_s1_rejects_time_mismatch() -> None:
    runtime = runtime_row()
    runtime["start_time"] += 1.0
    assert validate_exact_mapping(gold_row(), runtime) == "time_mismatch"


def test_stage3r_s1_rejects_text_digest_mismatch() -> None:
    runtime = runtime_row()
    runtime["text_digest"] = text_digest("different")
    assert validate_exact_mapping(gold_row(), runtime) == "text_digest_mismatch"


def test_stage3r_s1_does_not_use_fuzzy_text_matching() -> None:
    source = inspect.getsource(stage3r_s1.project_gold_segment_identity)
    assert "SequenceMatcher" not in source
    assert "edit_distance" not in source
    assert "embedding" not in source.casefold()


def test_stage3r_s1_does_not_use_nearest_time_matching() -> None:
    source = inspect.getsource(stage3r_s1.project_gold_segment_identity)
    assert "min(" not in source
    assert "overlap" not in source


def test_stage3r_s1_does_not_use_case_specific_mapping() -> None:
    source = inspect.getsource(stage3r_s1.project_gold_segment_identity)
    assert "if case_id ==" not in source


def test_stage3r_s1_does_not_use_video_specific_mapping() -> None:
    source = inspect.getsource(stage3r_s1.project_gold_segment_identity)
    assert "if source_bvid ==" not in source


def test_stage3r_s1_gold_group_or_span_and_semantics() -> None:
    key = gold_row()["canonical_key"]
    gold = {
        ("CASE", "g1"): {"canonical_key": key},
        ("CASE", "g2"): {"canonical_key": {**key, "segment_ordinal": 42}},
        ("CASE", "g3"): {"canonical_key": {**key, "segment_ordinal": 43}},
    }
    candidate = {
        "source_artifact_id": key["source_artifact_id"],
        "source_version": key["source_version"],
        "timeline_run_id": key["timeline_run_id"],
        "original_ordinals": [41],
    }
    groups = [
        {"required_spans": [{"segment_ids": ["g1"]}, {"segment_ids": ["g2"]}]},
        {"required_spans": [{"segment_ids": ["g3"]}]},
    ]
    assert not gold_group_hit(
        case_id="CASE", groups=groups, candidates=[candidate],
        gold_by_case_id=gold,
    )
    candidate["original_ordinals"] = [41, 42]
    assert gold_group_hit(
        case_id="CASE", groups=groups, candidates=[candidate],
        gold_by_case_id=gold,
    )


def test_stage3r_s1_candidate_coverage_uses_canonical_identity() -> None:
    row = gold_row()
    candidate = {
        "source_artifact_id": row["canonical_key"]["source_artifact_id"],
        "source_version": row["canonical_key"]["source_version"],
        "timeline_run_id": row["canonical_key"]["timeline_run_id"],
        "original_ordinals": [41],
    }
    assert span_covered(
        case_id="CASE", span={"segment_ids": ["BV1abc_seg_000042"]},
        candidates=[candidate],
        gold_by_case_id={("CASE", "BV1abc_seg_000042"): row},
    )


def test_stage3r_s1_bundle_hit_uses_canonical_identity() -> None:
    test_stage3r_s1_candidate_coverage_uses_canonical_identity()
