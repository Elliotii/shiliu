from __future__ import annotations

from dataclasses import fields
from hashlib import sha256
import json
from pathlib import Path

from shiliu.evidence.contracts import SearchCandidateVideo, SearchRawUnitCandidate
from shiliu.eval_v3_5.stage3a_inputs import (
    AUTHORIZED_CASE_IDS,
    EXECUTION_MANIFEST_VERSION,
    FORBIDDEN_SEMANTIC_FIELDS,
    canonical_json,
    canonical_jsonl,
    file_sha256,
    generate_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "research/v3_5/stage3a_inputs"
MANIFEST = INPUTS / "development_execution_manifest.8_cases.locked.jsonl"
LOCK = INPUTS / "development_execution_manifest.lock.json"
AUDIT = INPUTS / "development_execution_manifest.audit.json"
SNAPSHOT = Path(
    "/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db"
)
SNAPSHOT_ARTIFACTS = SNAPSHOT.parent / "artifacts"
ARTIFACT_MANIFEST = ROOT / "research/v3_eval/artifact_manifest.jsonl"


def _records() -> list[dict[str, object]]:
    return [json.loads(line) for line in MANIFEST.read_text(encoding="utf-8").splitlines()]


def _find_forbidden(value: object) -> set[str]:
    if isinstance(value, dict):
        return ({str(key) for key in value if key in FORBIDDEN_SEMANTIC_FIELDS}
                | set().union(*(_find_forbidden(child) for child in value.values()), set()))
    if isinstance(value, list):
        return set().union(*(_find_forbidden(child) for child in value), set())
    return set()


def test_locked_manifest_schema_membership_and_query_target_identity() -> None:
    records = _records()
    assert len(records) == 8
    assert tuple(row["case_id"] for row in records) == AUTHORIZED_CASE_IDS
    assert len({row["case_id"] for row in records}) == 8
    for row in records:
        assert row["execution_manifest_version"] == EXECUTION_MANIFEST_VERSION
        assert row["query_id"] and row["original_query"] and row["query_origin"]
        assert row["search_candidate_contract_version"] == "v3.5-search-candidate-v1"
        assert len(row["search_candidate_set_id"]) == 64
        if row["case_type"] == "query_corpus":
            assert row["target_video_id"] is row["target_bvid"] is None
            assert row["query_corpus_control"] is True
        else:
            assert row["target_video_id"] is not None and row["target_bvid"]
            assert row["query_corpus_control"] is False


def test_search_candidate_schema_order_and_stable_set_identity() -> None:
    raw_fields = {field.name for field in fields(SearchRawUnitCandidate)}
    video_fields = {field.name for field in fields(SearchCandidateVideo)}
    for row in _records():
        candidates = row["search_candidates"]
        raw = candidates["raw_unit_candidates"]
        videos = candidates["video_candidates"]
        assert all(set(candidate) == raw_fields for candidate in raw)
        assert all(set(candidate) == video_fields for candidate in videos)
        assert [candidate["raw_rank"] for candidate in raw] == list(range(1, len(raw) + 1))
        assert [candidate["product_rank"] for candidate in videos] == list(range(1, len(videos) + 1))
        identity = {
            "search_candidate_contract_version": row["search_candidate_contract_version"],
            "snapshot_database_sha256": row["snapshot_database_sha256"],
            "search_configuration_identity": row["search_configuration_identity"],
            "query_id": row["query_id"],
            "original_query": row["original_query"],
            "search_candidates": candidates,
        }
        assert sha256(canonical_json(identity).encode()).hexdigest() == row["search_candidate_set_id"]


def test_manifest_is_canonical_and_contains_no_semantic_gold_or_heldout_fields() -> None:
    records = _records()
    assert MANIFEST.read_bytes() == canonical_jsonl(records)
    assert _find_forbidden(records) == set()
    assert not any("heldout" in key.lower() for row in records for key in row)
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert audit["errors"] == []
    assert audit["checks"]["no_semantic_gold_fields_copied"] is True
    assert audit["checks"]["no_heldout_semantic_fields_copied"] is True


def test_lock_hashes_manifest_and_frozen_inputs() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    assert lock["manifest_sha256"] == file_sha256(MANIFEST)
    assert lock["record_count"] == 8
    assert tuple(lock["case_ids"]) == AUTHORIZED_CASE_IDS
    assert lock["development_gold_sha256"] == "5693830749e3fba38dd35fc143988fb615ae48bf0f02b7344c8b03ce4a1d90d0"
    assert lock["snapshot_database_sha256"] == file_sha256(SNAPSHOT)
    assert lock["artifact_manifest_sha256"] == file_sha256(ARTIFACT_MANIFEST)


def test_two_independent_generations_are_byte_identical_and_do_not_write_snapshot() -> None:
    before = file_sha256(SNAPSHOT)
    common = dict(
        development_gold=ROOT / "research/v3_5/gold/development_gold.8_cases.locked.jsonl",
        candidate_metadata=ROOT / "research/v3_5/master_case_candidates.jsonl",
        query_registry=ROOT / "research/v3_eval/eval_queries.locked.jsonl",
        snapshot_db=SNAPSHOT,
        snapshot_artifacts=SNAPSHOT_ARTIFACTS,
        artifact_manifest=ARTIFACT_MANIFEST,
        snapshot_id="20260720T094346Z_c7663365",
    )
    generation_a = canonical_jsonl(generate_manifest(**common))
    generation_b = canonical_jsonl(generate_manifest(**common))
    assert generation_a == generation_b == MANIFEST.read_bytes()
    assert file_sha256(SNAPSHOT) == before
