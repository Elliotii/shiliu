from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from shiliu.eval_v3_5.eval_v2.stage2r_c0 import (
    EXPECTED_FREEZE_SHA256,
    FIRST_BATCH_KEYS,
    FREEZE_MANIFEST,
    OUTPUT_ROOT,
    build_candidates,
    sha256_file,
    validate_candidates,
    validate_pilots,
)


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_c0_pilot_ledger_and_freeze_are_exact() -> None:
    records, distribution = validate_pilots()
    assert len(records) == 4
    assert distribution == {
        "sufficient": 1,
        "partial": 0,
        "insufficient": 3,
        "unverifiable": 0,
    }
    assert sha256_file(FREEZE_MANIFEST) == EXPECTED_FREEZE_SHA256


def test_c0_pool_has_twelve_unique_gold_blind_candidates() -> None:
    rows = _jsonl(OUTPUT_ROOT / "development_expansion_candidate_pool.v1.jsonl")
    assert len(rows) == 12
    assert len({row["candidate_case_id"] for row in rows}) == 12
    assert len({row["original_query"] for row in rows}) == 12
    assert len({row["evidence_question"] for row in rows}) == 12
    assert all(row["constructor_fields_must_be_stripped"] is True for row in rows)
    serialized = json.dumps(rows, ensure_ascii=False).casefold()
    assert "final_gold" not in serialized
    assert "heldout_gold" not in serialized


def test_c0_first_batch_distribution_and_diversity() -> None:
    rows = _jsonl(OUTPUT_ROOT / "first_batch_8.provisional.jsonl")
    assert len(rows) == 8
    assert Counter(row["constructor_expected_status"] for row in rows) == {
        "sufficient": 2,
        "partial": 3,
        "insufficient": 1,
        "unverifiable": 2,
    }
    assert len({row["source_video_id"] for row in rows}) >= 4
    assert sum(row["source_type"] == "raw_subtitle" for row in rows) >= 3
    assert sum(row["source_type"] == "raw_asr" for row in rows) >= 1
    assert sum(row["source_type"] == "unavailable" for row in rows) == 2
    assert max(Counter(row["source_video_id"] for row in rows).values()) <= 2


def test_c0_partial_and_unverifiable_construction_is_strict() -> None:
    rows = _jsonl(OUTPUT_ROOT / "development_expansion_candidate_pool.v1.jsonl")
    for row in rows:
        if row["constructor_expected_status"] == "partial":
            assert row["constructor_supported_aspects"]
            assert row["constructor_missing_aspects"]
            assert len(row["constructor_aspects"]) >= 2
            assert all(aspect["why_material"] for aspect in row["constructor_aspects"])
        if row["constructor_expected_status"] == "unverifiable":
            failure = row["source_failure_metadata"]
            assert failure["raw_subtitle_exists"] is False
            assert failure["raw_asr_exists"] is False
            assert row["transcript_segment_count"] == 0


def test_c0_runtime_validation_and_stable_hashes() -> None:
    generated = build_candidates()
    validation = validate_candidates(generated)
    assert len(validation["first"]) == len(FIRST_BATCH_KEYS) == 8
    manifest = json.loads(
        (OUTPUT_ROOT / "development_expansion_candidate_pool.v1.manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["reviewer_calls"] == manifest["provider_calls"] == 0
    assert manifest["heldout_or_gold_accessed"] is False
    assert manifest["final_gold_created"] == 0
    assert manifest["stage2r_c1_entered"] is False
    for path, expected in manifest["artifact_sha256"].items():
        assert sha256_file(Path(path)) == expected


def test_c0_constructor_fields_have_explicit_strip_contract() -> None:
    rows = _jsonl(OUTPUT_ROOT / "first_batch_8.provisional.jsonl")
    constructor_keys = {
        "constructor_expected_status",
        "constructor_aspects",
        "constructor_supported_aspects",
        "constructor_missing_aspects",
        "constructor_evidence_route_summary",
        "constructor_evidence_regions",
        "coverage_tags",
        "risk_tags",
        "construction_reason",
    }
    assert all(constructor_keys <= set(row) for row in rows)
    assert all(row["constructor_fields_must_be_stripped"] is True for row in rows)


def test_c0_created_no_review_or_gold_artifacts() -> None:
    names = {path.name.casefold() for path in OUTPUT_ROOT.rglob("*") if path.is_file()}
    assert not any("canonical_review" in name for name in names)
    assert not any("agreement" in name for name in names)
    assert not any("human_decision" in name for name in names)
    assert not any("gold_lock" in name for name in names)
