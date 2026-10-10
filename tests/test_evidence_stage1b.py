from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from shiliu.artifacts import ArtifactStore
from shiliu.db import Database
from shiliu.evidence import (
    REPLAY_IMPLEMENTATION_VERSION,
    SOURCE_CHUNK_POLICY_VERSION,
    SOURCE_IDENTITY_V1_VERSION,
    SOURCE_IDENTITY_VERSION,
    EvidenceContractError,
    EvidenceSearchService,
    SourceArtifactReference,
    audit_snapshot_chunk_mappings,
    bind_live_current_version,
    bind_pinned_version,
    bind_snapshot_manifest_version,
    load_source_artifact,
    make_source_artifact_id,
    make_source_artifact_id_v1,
    map_retrieval_chunk,
    replay_source_chunks,
)
from shiliu.evidence.contracts import RetrievalChunkReference
from shiliu.retrieval.consolidation import SearchResultConsolidator
from shiliu.retrieval.enrichment import EvidenceEnricher
from shiliu.retrieval.models import SearchResult
from shiliu.retrieval.orchestrator import SearchOrchestrator
from shiliu.retrieval.product_search import ProductSearchRequest, ProductSearchService
from shiliu.retrieval.service import RetrievalService


SNAPSHOT_ROOT = Path(
    "/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365"
)
SNAPSHOT_DB = SNAPSHOT_ROOT / "shiliu_eval.db"
SNAPSHOT_ARTIFACTS = SNAPSHOT_ROOT / "artifacts"
ARTIFACT_MANIFEST = Path("research/v3_eval/artifact_manifest.jsonl")
SNAPSHOT_ID = "20260720T094346Z_c7663365"
SNAPSHOT_DB_SHA256 = "61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1"


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _snapshot_reference(video_id: int) -> SourceArtifactReference:
    connection = sqlite3.connect(f"file:{SNAPSHOT_DB}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
    finally:
        connection.close()
    assert row is not None
    return SourceArtifactReference(
        platform=row["platform"], source_id=row["source_id"], part=row["part"],
        source_type=row["subtitle_source"], source_language=row["subtitle_language"],
        artifact_path=row["raw_subtitle_path"],
    )


def _first_chunk(video_id: int) -> RetrievalChunkReference:
    connection = sqlite3.connect(f"file:{SNAPSHOT_DB}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM retrieval_units WHERE video_id=? AND unit_type='transcript_chunk' "
            "ORDER BY rowid LIMIT 1", (video_id,),
        ).fetchone()
    finally:
        connection.close()
    assert row is not None
    return RetrievalChunkReference(
        unit_id=row["unit_id"], chunk_id=row["chunk_id"],
        start_time=row["start_time"], end_time=row["end_time"],
        source_text=row["source_text"], content_hash=row["content_hash"],
    )


def test_source_identity_v2_excludes_language_and_versions_v1_explicitly() -> None:
    zh = _snapshot_reference(78)
    en = replace(zh, source_language="en")
    human = replace(zh, source_lineage="human")
    assert SOURCE_IDENTITY_V1_VERSION == "v3.5-source-identity-v1"
    assert SOURCE_IDENTITY_VERSION == "v3.5-source-identity-v2"
    assert make_source_artifact_id(zh) == make_source_artifact_id(en)
    assert make_source_artifact_id(zh) != make_source_artifact_id(human)
    assert make_source_artifact_id_v1(zh) != make_source_artifact_id_v1(en)
    assert make_source_artifact_id_v1(zh) != make_source_artifact_id(zh)
    first = load_source_artifact(zh)
    second = load_source_artifact(en)
    assert first.segments[0].segment_id == second.segments[0].segment_id


def test_real_snapshot_manifest_and_pinned_authorities_fail_closed(tmp_path: Path) -> None:
    reference = _snapshot_reference(78)
    snapshot = bind_snapshot_manifest_version(
        reference, video_id=78, manifest_path=ARTIFACT_MANIFEST
    )
    assert snapshot.source_version_authority == "snapshot_manifest"
    assert snapshot.source_version_verified
    pinned = bind_pinned_version(
        reference, expected_source_version=snapshot.source_version
    )
    assert pinned.source_version_authority == "pinned_request"
    assert pinned.source_version_verified

    with pytest.raises(EvidenceContractError) as pinned_error:
        bind_pinned_version(reference, expected_source_version="0" * 64)
    assert pinned_error.value.code == "source_version_mismatch"

    records = [json.loads(line) for line in ARTIFACT_MANIFEST.read_text().splitlines()]
    for record in records:
        if record.get("video_id") == 78 and record.get("artifact_type") == "raw_subtitle":
            record["sha256"] = "0" * 64
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text("\n".join(json.dumps(value) for value in records), encoding="utf-8")
    with pytest.raises(EvidenceContractError) as snapshot_error:
        bind_snapshot_manifest_version(reference, video_id=78, manifest_path=manifest)
    assert snapshot_error.value.code == "source_version_mismatch"


def test_live_authority_requires_current_sync_and_current_exact_replay(tmp_path: Path) -> None:
    work_db = tmp_path / "work.db"
    shutil.copy2(SNAPSHOT_DB, work_db)
    work_db.chmod(0o600)
    db = Database(work_db)
    reference = _snapshot_reference(78)
    binding = bind_live_current_version(reference, db=db, video_id=78)
    mapping = map_retrieval_chunk(
        reference, _first_chunk(78), expected_source_version=binding.source_version
    )
    assert binding.source_version_authority == "live_current_exact_replay"
    assert mapping.mapping_status == "exact_mapped"
    failed = map_retrieval_chunk(
        reference,
        replace(_first_chunk(78), source_text="not the indexed chunk text"),
        expected_source_version=binding.source_version,
    )
    assert failed.mapping_status == "chunk_segment_mapping_failed"
    assert failed.candidate_eligibility is False

    missing = replace(reference, artifact_path=str(tmp_path / "missing" / "subtitle-raw.json"))
    with pytest.raises(EvidenceContractError) as missing_error:
        bind_live_current_version(missing, db=db, video_id=78)
    assert missing_error.value.code == "source_unavailable"

    with db.connect() as connection:
        connection.execute(
            "UPDATE retrieval_sync_state SET lexical_state='failed' WHERE video_id=78"
        )
    with pytest.raises(EvidenceContractError) as sync_error:
        bind_live_current_version(reference, db=db, video_id=78)
    assert sync_error.value.code == "index_not_ready"


def test_chunk_policy_and_replay_versions_are_bound_and_mismatch_fails_closed() -> None:
    reference = _snapshot_reference(78)
    artifact = load_source_artifact(reference)
    mapping = map_retrieval_chunk(
        reference, _first_chunk(78), expected_source_version=artifact.source_version
    )
    assert mapping.source_chunk_policy_version == SOURCE_CHUNK_POLICY_VERSION
    assert mapping.replay_implementation_version == REPLAY_IMPLEMENTATION_VERSION
    with pytest.raises(EvidenceContractError) as error:
        map_retrieval_chunk(
            reference, _first_chunk(78), expected_source_version=artifact.source_version,
            source_chunk_policy_version="unsupported",
        )
    assert error.value.code == "chunk_policy_version_mismatch"


def test_corpus_wide_mapping_audit_accounts_for_every_snapshot_chunk() -> None:
    summary = audit_snapshot_chunk_mappings(
        snapshot_db=SNAPSHOT_DB, artifact_manifest=ARTIFACT_MANIFEST
    )
    assert summary.total_transcript_chunks == summary.accounted_total == 1412
    assert summary.terminal_status_counts == {
        "exact_mapped": 1411,
        "invalid_cross_timeline_chunk": 1,
    }
    assert summary.by_source_type == {
        "ai": {"exact_mapped": 1333},
        "asr": {"exact_mapped": 14},
        "human": {"exact_mapped": 64, "invalid_cross_timeline_chunk": 1},
    }
    assert len(summary.issues) == 1
    assert summary.issues[0].video_id == 88


class _CountingLexical:
    def __init__(self, delegate) -> None:
        self.delegate = delegate
        self.calls = 0
        self.last_results = []

    def search(self, *args, **kwargs):
        self.calls += 1
        self.last_results = self.delegate.search(*args, **kwargs)
        return self.last_results


def _snapshot_search_service(tmp_path: Path, *, persist_trace: bool = False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    work_db = tmp_path / ("enabled.db" if persist_trace else "disabled.db")
    shutil.copy2(SNAPSHOT_DB, work_db)
    work_db.chmod(0o600)
    db = Database(work_db)
    lexical = _CountingLexical(
        RetrievalService(db=db, artifacts=ArtifactStore(SNAPSHOT_ARTIFACTS))
    )
    orchestrator = SearchOrchestrator(
        db=db, lexical=lexical,
        dense_factory=lambda: (_ for _ in ()).throw(AssertionError("dense forbidden")),
        hybrid_factory=lambda: (_ for _ in ()).throw(AssertionError("hybrid forbidden")),
        persist_trace=persist_trace,
    )
    product = ProductSearchService(
        db=db, raw_search=orchestrator,
        consolidator=SearchResultConsolidator(),
        enricher=EvidenceEnricher(db=db, artifacts=ArtifactStore(SNAPSHOT_ARTIFACTS)),
        persist_trace=persist_trace,
    )
    evidence = EvidenceSearchService(
        db=db, product_search=product, authority_mode="snapshot_manifest",
        snapshot_id=SNAPSHOT_ID, artifact_manifest=ARTIFACT_MANIFEST,
    )
    return evidence, lexical, db, work_db


def test_real_search_projection_preserves_orders_scores_identity_and_single_execution(tmp_path: Path) -> None:
    evidence, lexical, _, _ = _snapshot_search_service(tmp_path)
    result = evidence.search_library(
        ProductSearchRequest(query="MCP", scope="all", result_limit=10)
    )
    assert lexical.calls == 1
    assert [value.raw_rank for value in result.raw_unit_candidates] == list(
        range(1, len(result.raw_unit_candidates) + 1)
    )
    assert [value.unit_id for value in result.raw_unit_candidates] == [
        value.unit_id for value in lexical.last_results
    ]
    assert [value.raw_score for value in result.raw_unit_candidates] == [
        value.lexical_score for value in lexical.last_results
    ]
    assert [value.product_rank for value in result.video_candidates] == list(
        range(1, len(result.video_candidates) + 1)
    )
    assert result.contract_version == "v3.5-search-candidate-v1"
    assert result.search_trace_id == result.presentation_trace_id
    assert result.index_identity["lexical_index_version"] == "v3-stage1-lexical-v1"
    assert result.trace_persisted is result.presentation_trace_persisted is False
    assert any(value.unit_type == "video" and value.mapping_status == "not_applicable"
               for value in result.raw_unit_candidates)
    mapped = [value for value in result.raw_unit_candidates if value.mapping_status == "exact_mapped"]
    assert mapped and all(value.segment_ids and value.source_version_verified for value in mapped)
    for video in result.video_candidates:
        expected = tuple(
            value.unit_id for value in result.raw_unit_candidates if value.video_id == video.video_id
        )
        assert video.component_unit_ids == expected


def test_cross_run_and_mapping_failure_candidates_remain_ranked_but_ineligible(
    tmp_path: Path, monkeypatch
) -> None:
    evidence, _, _, _ = _snapshot_search_service(tmp_path)
    cross = evidence.search_library(
        ProductSearchRequest(query="ClaudeCode", scope="transcript_chunk", result_limit=20)
    )
    invalid = [
        value for value in cross.raw_unit_candidates
        if value.mapping_status == "invalid_cross_timeline_chunk"
    ]
    assert len(invalid) == 1 and invalid[0].video_id == 88
    assert invalid[0].candidate_eligibility is False

    def fail(*args, **kwargs):
        raise EvidenceContractError("forced exact mismatch", code="chunk_segment_mapping_failed")

    monkeypatch.setattr("shiliu.evidence.search.map_retrieval_chunk", fail)
    failed = evidence.search_library(
        ProductSearchRequest(query="MCP", scope="transcript_chunk", result_limit=3)
    )
    assert failed.raw_unit_candidates
    assert [value.raw_rank for value in failed.raw_unit_candidates] == list(
        range(1, len(failed.raw_unit_candidates) + 1)
    )
    assert all(value.mapping_status == "chunk_segment_mapping_failed" for value in failed.raw_unit_candidates)
    assert all(not value.candidate_eligibility for value in failed.raw_unit_candidates)
    assert all(value.source_version_authority == "snapshot_manifest" for value in failed.raw_unit_candidates)
    assert all(value.source_version_verified for value in failed.raw_unit_candidates)


def test_empty_search_is_successful_and_specific_missing_candidate_is_structured(tmp_path: Path) -> None:
    evidence, _, _, _ = _snapshot_search_service(tmp_path)
    result = evidence.search_library(
        ProductSearchRequest(query="zzzzzz-no-such-token-zzzzzz", scope="all")
    )
    assert result.raw_unit_candidates == result.video_candidates == ()
    assert result.reason_codes == ("no_search_candidate",)
    with pytest.raises(EvidenceContractError) as error:
        result.require_candidate("missing")
    assert error.value.code == "candidate_not_found"


def test_disabled_trace_mode_creates_no_schema_or_rows_and_enabled_uses_work_db(tmp_path: Path) -> None:
    before_snapshot = _hash(SNAPSHOT_DB)
    disabled, _, disabled_db, _ = _snapshot_search_service(tmp_path / "off")
    with disabled_db.connect() as connection:
        connection.execute("DROP TABLE retrieval_search_traces")
        connection.execute("DROP TABLE retrieval_search_presentations")
    disabled.search_library(ProductSearchRequest(query="MCP", result_limit=2))
    with disabled_db.connect() as connection:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "retrieval_search_traces" not in tables
    assert "retrieval_search_presentations" not in tables

    enabled, _, enabled_db, _ = _snapshot_search_service(tmp_path / "on", persist_trace=True)
    with enabled_db.connect() as connection:
        before = (
            connection.execute("SELECT count(*) FROM retrieval_search_traces").fetchone()[0],
            connection.execute("SELECT count(*) FROM retrieval_search_presentations").fetchone()[0],
        )
    enabled_result = enabled.search_library(ProductSearchRequest(query="MCP", result_limit=2))
    with enabled_db.connect() as connection:
        after = (
            connection.execute("SELECT count(*) FROM retrieval_search_traces").fetchone()[0],
            connection.execute("SELECT count(*) FROM retrieval_search_presentations").fetchone()[0],
        )
    assert enabled_result.trace_persisted and enabled_result.presentation_trace_persisted
    assert after == (before[0] + 1, before[1] + 1)
    assert _hash(SNAPSHOT_DB) == before_snapshot == SNAPSHOT_DB_SHA256


def test_trace_enabled_and_disabled_preserve_substantive_search_results(tmp_path: Path) -> None:
    disabled, _, _, _ = _snapshot_search_service(tmp_path / "off")
    enabled, _, _, _ = _snapshot_search_service(tmp_path / "on", persist_trace=True)
    request = ProductSearchRequest(query="MCP", result_limit=4)
    left = disabled.search_library(request)
    right = enabled.search_library(request)
    assert [
        (value.unit_id, value.raw_rank, value.raw_score, value.mapping_status)
        for value in left.raw_unit_candidates
    ] == [
        (value.unit_id, value.raw_rank, value.raw_score, value.mapping_status)
        for value in right.raw_unit_candidates
    ]
    assert [
        (value.video_id, value.product_rank, value.component_unit_ids)
        for value in left.video_candidates
    ] == [
        (value.video_id, value.product_rank, value.component_unit_ids)
        for value in right.video_candidates
    ]


def test_existing_product_search_and_raw_reuse_path_are_equivalent(tmp_path: Path) -> None:
    evidence, lexical, _, _ = _snapshot_search_service(tmp_path)
    request = ProductSearchRequest(query="MCP", result_limit=4)
    existing = evidence.product_search.search(request)
    raw, reused = evidence.product_search.search_with_raw(request)
    assert lexical.calls == 2
    assert [value.unit_id for value in raw.raw_hits] == [
        candidate.unit_id
        for candidate in evidence.search_library(request).raw_unit_candidates
    ]
    assert [value.as_dict() for value in existing.results] == [
        value.as_dict() for value in reused.results
    ]
    assert existing.plan == reused.plan
    assert existing.executed_mode == reused.executed_mode
    assert existing.fallback == reused.fallback
