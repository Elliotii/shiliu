from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import Any, Iterable

from shiliu.artifacts import ArtifactStore
from shiliu.db import Database
from shiliu.evidence.contracts import (
    CHUNK_MAPPING_VERSION,
    REPLAY_IMPLEMENTATION_VERSION,
    SEARCH_CANDIDATE_CONTRACT_VERSION,
    SOURCE_CHUNK_POLICY_VERSION,
    SOURCE_IDENTITY_VERSION,
    SOURCE_VERSION_AUTHORITY_VERSION,
    SearchCandidateVideo,
    SearchRawUnitCandidate,
    TIMELINE_POLICY_VERSION,
    TRACE_POLICY_VERSION,
)
from shiliu.evidence.search import EvidenceSearchService
from shiliu.retrieval.consolidation import CONSOLIDATION_VERSION, SearchResultConsolidator
from shiliu.retrieval.dense import SQLiteExactDenseIndex
from shiliu.retrieval.enrichment import EvidenceEnricher
from shiliu.retrieval.hybrid import FUSION_VERSION, HybridRetrievalService
from shiliu.retrieval.orchestrator import SearchOrchestrator
from shiliu.retrieval.product_search import (
    PRESENTATION_VERSION,
    ProductSearchRequest,
    ProductSearchService,
)
from shiliu.retrieval.service import INDEX_VERSION, RetrievalService


EXECUTION_MANIFEST_VERSION = "v3.5-development-execution-manifest-v1"
LOCK_VERSION = "v3.5-development-execution-manifest-lock-v1"
AUDIT_VERSION = "v3.5-development-execution-manifest-audit-v1"
EXPECTED_DEVELOPMENT_GOLD_SHA256 = "5693830749e3fba38dd35fc143988fb615ae48bf0f02b7344c8b03ce4a1d90d0"
EXPECTED_SNAPSHOT_DATABASE_SHA256 = "61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1"
EXPECTED_ARTIFACT_MANIFEST_SHA256 = "36e63e3a510e840f688b7ce5075fef2a0b1f65086c039960632a9ec726dfd08f"
AUTHORIZED_CASE_IDS = (
    "CASE_001", "CASE_002", "CASE_003", "CASE_005",
    "CASE_012", "CASE_013", "CASE_015", "CASE_017",
)
FORBIDDEN_SEMANTIC_FIELDS = frozenset(
    {
        "sufficiency_label", "required_aspects", "supported_aspects", "missing_aspects",
        "gold_evidence_groups", "gold_segment_ids", "primary_reason_codes",
        "support_notes", "conflict_notes", "reviewer_flags", "heldout_membership",
        "split_constraint", "applicable_metrics", "candidate_rationale",
    }
)


def canonical_json(value: Any) -> str:
    """UTF-8-ready canonical JSON with stable keys, lists, and normalized newlines."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_jsonl(records: Iterable[dict[str, Any]]) -> bytes:
    return ("\n".join(canonical_json(record) for record in records) + "\n").encode("utf-8")


def file_sha256(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def search_configuration() -> dict[str, Any]:
    # SearchPlanner and ProductSearchService have no separately exported version constants.
    # Their frozen contract identities are therefore recorded explicitly and bound by the
    # enclosing configuration digest.
    return {
        "retrieval_router_version": "unversioned:SearchPlanner@sha256:0876dbaff9bb2d016496cc3cb823f200b9a93a06721947bebee472d6a5bdaa7e",
        "lexical_provider_version": INDEX_VERSION,
        "dense_provider_version": "v3-qwen3-embedding-provider-v1",
        "fusion_version": FUSION_VERSION,
        "requested_limit": 10,
        "per_channel_limit": 50,
        "grouping_policy": CONSOLIDATION_VERSION,
        "presentation_policy": PRESENTATION_VERSION,
        "max_windows_per_video": 2,
        "trace_policy": {"version": TRACE_POLICY_VERSION, "persistence": "disabled"},
        "request_defaults": {"mode": "lexical", "scope": "all", "filters": {}},
    }


def search_configuration_identity(configuration: dict[str, Any]) -> str:
    return sha256(canonical_json(configuration).encode("utf-8")).hexdigest()


def load_case_projection(
    *, development_gold: str | Path, candidate_metadata: str | Path,
    query_registry: str | Path,
) -> list[dict[str, Any]]:
    development_ids = [
        json.loads(line)["case_id"]
        for line in Path(development_gold).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if tuple(development_ids) != AUTHORIZED_CASE_IDS:
        raise ValueError(f"development membership mismatch: {development_ids!r}")
    queries: dict[str, list[str]] = {}
    for line in Path(query_registry).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            query = str(row["query"])
            queries.setdefault(query, []).append(str(row["query_id"]))
    candidates = {
        row["case_id"]: row
        for row in (
            json.loads(line)
            for line in Path(candidate_metadata).read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if row.get("case_id") in AUTHORIZED_CASE_IDS
    }
    if set(candidates) != set(AUTHORIZED_CASE_IDS):
        raise ValueError("authorized candidate metadata is incomplete")
    projection = []
    for case_id in AUTHORIZED_CASE_IDS:
        row = candidates[case_id]
        query = str(row["query"])
        query_ids = queries.get(query, [])
        if len(query_ids) != 1:
            raise ValueError(f"query identity must resolve exactly once for {query!r}: {query_ids!r}")
        case_type = str(row["case_scope"])
        target_video_id = row.get("target_video_id")
        target_bvid = row.get("target_bvid")
        corpus = case_type == "query_corpus"
        if corpus and (target_video_id is not None or target_bvid is not None):
            raise ValueError(f"query-corpus target must be null: {case_id}")
        if not corpus and (target_video_id is None or not target_bvid):
            raise ValueError(f"query-video target is incomplete: {case_id}")
        projection.append(
            {
                "case_id": case_id,
                "case_type": case_type,
                "query_id": query_ids[0],
                "original_query": query,
                "query_origin": "research/v3_eval/eval_queries.locked.jsonl",
                "target_video_id": target_video_id,
                "target_bvid": target_bvid,
                "query_corpus_control": corpus,
                "case_origin": str(row["case_origin"]),
            }
        )
    return projection


def _search_service(*, work_db: Path, snapshot_artifacts: Path, artifact_manifest: Path,
                    snapshot_id: str) -> EvidenceSearchService:
    db = Database(work_db)
    lexical = RetrievalService(db=db, artifacts=ArtifactStore(snapshot_artifacts))
    orchestrator = SearchOrchestrator(
        db=db,
        lexical=lexical,
        dense_factory=lambda: SQLiteExactDenseIndex(db=db),
        hybrid_factory=lambda: HybridRetrievalService(
            lexical=lexical, dense=SQLiteExactDenseIndex(db=db)
        ),
        persist_trace=False,
    )
    product = ProductSearchService(
        db=db,
        raw_search=orchestrator,
        consolidator=SearchResultConsolidator(),
        enricher=EvidenceEnricher(db=db, artifacts=ArtifactStore(snapshot_artifacts)),
        persist_trace=False,
    )
    return EvidenceSearchService(
        db=db,
        product_search=product,
        authority_mode="snapshot_manifest",
        snapshot_id=snapshot_id,
        artifact_manifest=artifact_manifest,
        runtime_corpus_identity=file_sha256(work_db),
    )


def generate_manifest(
    *, development_gold: str | Path, candidate_metadata: str | Path,
    query_registry: str | Path, snapshot_db: str | Path, snapshot_artifacts: str | Path,
    artifact_manifest: str | Path, snapshot_id: str,
) -> list[dict[str, Any]]:
    projection = load_case_projection(
        development_gold=development_gold,
        candidate_metadata=candidate_metadata,
        query_registry=query_registry,
    )
    snapshot_hash = file_sha256(snapshot_db)
    artifact_hash = file_sha256(artifact_manifest)
    if snapshot_hash != EXPECTED_SNAPSHOT_DATABASE_SHA256:
        raise ValueError("snapshot database hash mismatch")
    if artifact_hash != EXPECTED_ARTIFACT_MANIFEST_SHA256:
        raise ValueError("artifact manifest hash mismatch")
    configuration = search_configuration()
    configuration_id = search_configuration_identity(configuration)
    records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="shiliu-stage3a-input-") as directory:
        work_db = Path(directory) / "snapshot-work-copy.db"
        shutil.copy2(snapshot_db, work_db)
        service = _search_service(
            work_db=work_db,
            snapshot_artifacts=Path(snapshot_artifacts),
            artifact_manifest=Path(artifact_manifest),
            snapshot_id=snapshot_id,
        )
        for item in projection:
            # This frozen Stage 3A projection predates the product-default change;
            # preserve its historical lexical replay explicitly.
            request = ProductSearchRequest(query=item["original_query"], mode="lexical")
            result = service.search_library(request)
            if result.trace_persisted or result.presentation_trace_persisted:
                raise RuntimeError("trace persistence must remain disabled")
            candidates = {
                "raw_unit_candidates": [asdict(value) for value in result.raw_unit_candidates],
                "video_candidates": [asdict(value) for value in result.video_candidates],
            }
            identity_input = {
                "search_candidate_contract_version": result.contract_version,
                "snapshot_database_sha256": snapshot_hash,
                "search_configuration_identity": configuration_id,
                "query_id": item["query_id"],
                "original_query": item["original_query"],
                "search_candidates": candidates,
            }
            set_id = sha256(canonical_json(identity_input).encode("utf-8")).hexdigest()
            records.append(
                {
                    "execution_manifest_version": EXECUTION_MANIFEST_VERSION,
                    **{key: item[key] for key in (
                        "case_id", "case_type", "query_id", "original_query", "query_origin",
                        "target_video_id", "target_bvid", "query_corpus_control",
                    )},
                    "search_candidate_contract_version": result.contract_version,
                    "search_request": result.request_parameters,
                    "search_candidate_set_id": set_id,
                    "search_candidates": candidates,
                    "snapshot_database_sha256": snapshot_hash,
                    "artifact_manifest_sha256": artifact_hash,
                    "search_configuration_identity": configuration_id,
                    "source_projection": {
                        "authority_mode": "snapshot_manifest",
                        "snapshot_id": snapshot_id,
                        "source_identity_version": SOURCE_IDENTITY_VERSION,
                        "source_version_authority_version": SOURCE_VERSION_AUTHORITY_VERSION,
                    },
                    "provenance": {
                        "development_membership": "research/v3_5/gold/development_gold.8_cases.locked.jsonl:case_id",
                        "case_and_target": "research/v3_5/master_case_candidates.jsonl:case_scope,target_video_id,target_bvid",
                        "original_query": "research/v3_5/master_case_candidates.jsonl:query",
                        "query_identity": "research/v3_eval/eval_queries.locked.jsonl:query_id joined by exact query",
                        "search_execution": "src/shiliu/evidence/search.py:EvidenceSearchService.search_library",
                        "trace_persistence": False,
                    },
                }
            )
    if file_sha256(snapshot_db) != snapshot_hash:
        raise RuntimeError("frozen snapshot database changed during generation")
    return records


def build_audit(records: list[dict[str, Any]], *, manifest_bytes: bytes,
                second_manifest_bytes: bytes, development_gold_sha256: str,
                expected_development_gold_sha256: str, snapshot_before: str,
                snapshot_after: str, artifact_manifest_sha256: str,
                expected_artifact_manifest_sha256: str,
                snapshot_db: str | Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = [
        "Projection session accidentally exposed one CASE_015 line from each of two forbidden full semantic assets during an initial broad text search; neither source was used for projection."
    ]
    ids = [row.get("case_id") for row in records]
    if len(records) != 8:
        errors.append("record_count_not_8")
    if tuple(ids) != AUTHORIZED_CASE_IDS or len(set(ids)) != 8:
        errors.append("development_membership_invalid")
    if development_gold_sha256 != expected_development_gold_sha256:
        errors.append("development_gold_hash_mismatch")
    if artifact_manifest_sha256 != expected_artifact_manifest_sha256:
        errors.append("artifact_manifest_hash_mismatch")
    if snapshot_before != snapshot_after:
        errors.append("snapshot_database_was_modified")
    if manifest_bytes != second_manifest_bytes:
        errors.append("two_run_manifest_mismatch")
    forbidden_hits = sorted(_find_keys(records, FORBIDDEN_SEMANTIC_FIELDS))
    if forbidden_hits:
        errors.append("forbidden_semantic_fields_present")
    chunk_unit_ids = {
        candidate["unit_id"]
        for row in records
        for candidate in row["search_candidates"]["raw_unit_candidates"]
        if candidate["unit_type"] == "transcript_chunk"
    }
    resolved_chunk_ids: set[str] = set()
    connection = sqlite3.connect(f"file:{Path(snapshot_db).resolve()}?mode=ro&immutable=1", uri=True)
    try:
        if chunk_unit_ids:
            placeholders = ",".join("?" for _ in chunk_unit_ids)
            resolved_chunk_ids = {
                str(value[0]) for value in connection.execute(
                    f"SELECT unit_id FROM retrieval_units WHERE unit_id IN ({placeholders})",
                    sorted(chunk_unit_ids),
                ).fetchall()
            }
    finally:
        connection.close()
    if resolved_chunk_ids != chunk_unit_ids:
        errors.append("candidate_chunk_ids_unresolvable")
    raw_schema = {field.name for field in fields(SearchRawUnitCandidate)}
    video_schema = {field.name for field in fields(SearchCandidateVideo)}
    for row in records:
        if not row.get("query_id") or not row.get("original_query"):
            errors.append(f"query_identity_missing:{row.get('case_id')}")
        corpus = row.get("case_type") == "query_corpus"
        if corpus != bool(row.get("query_corpus_control")):
            errors.append(f"query_corpus_flag_invalid:{row.get('case_id')}")
        if corpus and (row.get("target_video_id") is not None or row.get("target_bvid") is not None):
            errors.append(f"query_corpus_target_present:{row.get('case_id')}")
        if not corpus and (row.get("target_video_id") is None or not row.get("target_bvid")):
            errors.append(f"query_video_target_missing:{row.get('case_id')}")
        candidates = row.get("search_candidates", {})
        raw = candidates.get("raw_unit_candidates", [])
        videos = candidates.get("video_candidates", [])
        if [value.get("raw_rank") for value in raw] != list(range(1, len(raw) + 1)):
            errors.append(f"raw_candidate_order_invalid:{row.get('case_id')}")
        if [value.get("product_rank") for value in videos] != list(range(1, len(videos) + 1)):
            errors.append(f"video_candidate_order_invalid:{row.get('case_id')}")
        expected_id = sha256(canonical_json({
            "search_candidate_contract_version": row["search_candidate_contract_version"],
            "snapshot_database_sha256": row["snapshot_database_sha256"],
            "search_configuration_identity": row["search_configuration_identity"],
            "query_id": row["query_id"], "original_query": row["original_query"],
            "search_candidates": row["search_candidates"],
        }).encode("utf-8")).hexdigest()
        if expected_id != row.get("search_candidate_set_id"):
            errors.append(f"search_candidate_set_id_invalid:{row.get('case_id')}")
        for candidate in raw:
            if set(candidate) != raw_schema:
                errors.append(f"raw_candidate_schema_invalid:{row.get('case_id')}")
                break
        for candidate in videos:
            if set(candidate) != video_schema:
                errors.append(f"video_candidate_schema_invalid:{row.get('case_id')}")
                break
    return {
        "audit_version": AUDIT_VERSION,
        "checks": {
            "record_count": len(records),
            "unique_authorized_case_ids": len(set(ids)) == 8 and set(ids) == set(AUTHORIZED_CASE_IDS),
            "no_non_development_case": set(ids) <= set(AUTHORIZED_CASE_IDS),
            "all_original_queries_present": all(row.get("original_query") for row in records),
            "all_query_identities_present": all(row.get("query_id") for row in records),
            "query_video_targets_present": all(row.get("target_video_id") is not None and row.get("target_bvid") for row in records if row.get("case_type") == "query_video"),
            "query_corpus_targets_absent": all(row.get("target_video_id") is None and row.get("target_bvid") is None for row in records if row.get("case_type") == "query_corpus"),
            "all_search_candidate_sets_present": all("search_candidates" in row for row in records),
            "search_candidate_set_ids_deterministic": not any("search_candidate_set_id_invalid" in value for value in errors),
            "candidate_ordering_deterministic": manifest_bytes == second_manifest_bytes,
            "all_candidates_satisfy_frozen_schema": not any("candidate_schema_invalid" in value for value in errors),
            "candidate_chunk_ids_resolvable": resolved_chunk_ids == chunk_unit_ids,
            "source_identities_valid": all(
                candidate.get("source_artifact_id") and candidate.get("source_version_verified")
                for row in records for candidate in row["search_candidates"]["raw_unit_candidates"]
                if candidate.get("candidate_eligibility")
            ),
            "snapshot_hash_correct_and_unchanged": snapshot_before == snapshot_after,
            "artifact_manifest_hash_correct": artifact_manifest_sha256 == expected_artifact_manifest_sha256,
            "no_semantic_gold_fields_copied": not forbidden_hits,
            "no_heldout_semantic_fields_copied": not forbidden_hits,
            "no_frozen_database_writes": snapshot_before == snapshot_after,
            "manifest_bytes_identical_across_two_runs": manifest_bytes == second_manifest_bytes,
        },
        "forbidden_semantic_field_hits": forbidden_hits,
        "errors": sorted(set(errors)),
        "warnings": warnings,
    }


def _find_keys(value: Any, forbidden: frozenset[str]) -> set[str]:
    hits: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in forbidden:
                hits.add(key)
            hits.update(_find_keys(child, forbidden))
    elif isinstance(value, list):
        for child in value:
            hits.update(_find_keys(child, forbidden))
    return hits


def write_projection_assets(
    *, output_dir: str | Path, development_gold: str | Path,
    candidate_metadata: str | Path, query_registry: str | Path,
    snapshot_db: str | Path, snapshot_artifacts: str | Path,
    artifact_manifest: str | Path, snapshot_id: str,
    expected_development_gold_sha256: str,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    snapshot_before = file_sha256(snapshot_db)
    generation_a = generate_manifest(
        development_gold=development_gold, candidate_metadata=candidate_metadata,
        query_registry=query_registry, snapshot_db=snapshot_db,
        snapshot_artifacts=snapshot_artifacts, artifact_manifest=artifact_manifest,
        snapshot_id=snapshot_id,
    )
    generation_b = generate_manifest(
        development_gold=development_gold, candidate_metadata=candidate_metadata,
        query_registry=query_registry, snapshot_db=snapshot_db,
        snapshot_artifacts=snapshot_artifacts, artifact_manifest=artifact_manifest,
        snapshot_id=snapshot_id,
    )
    bytes_a = canonical_jsonl(generation_a)
    bytes_b = canonical_jsonl(generation_b)
    if bytes_a != bytes_b:
        raise RuntimeError("SearchCandidateSet Reproducibility Conflict")
    manifest_path = output / "development_execution_manifest.8_cases.locked.jsonl"
    manifest_path.write_bytes(bytes_a)
    manifest_hash = sha256(bytes_a).hexdigest()
    configuration = search_configuration()
    lock = {
        "lock_version": LOCK_VERSION,
        "locked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_hash,
        "record_count": len(generation_a),
        "case_ids": list(AUTHORIZED_CASE_IDS),
        "development_gold_path": str(development_gold),
        "development_gold_sha256": file_sha256(development_gold),
        "snapshot_database_sha256": snapshot_before,
        "artifact_manifest_sha256": file_sha256(artifact_manifest),
        "stage1_contract_versions": {
            "source_identity": SOURCE_IDENTITY_VERSION,
            "source_version_authority": SOURCE_VERSION_AUTHORITY_VERSION,
            "timeline_policy": TIMELINE_POLICY_VERSION,
            "chunk_mapping": CHUNK_MAPPING_VERSION,
            "source_chunk_policy": SOURCE_CHUNK_POLICY_VERSION,
            "replay_implementation": REPLAY_IMPLEMENTATION_VERSION,
            "search_candidate": SEARCH_CANDIDATE_CONTRACT_VERSION,
            "trace_policy": TRACE_POLICY_VERSION,
        },
        "search_configuration": configuration,
        "search_configuration_identity": search_configuration_identity(configuration),
        "per_case_search_candidate_set_ids": {
            row["case_id"]: row["search_candidate_set_id"] for row in generation_a
        },
        "forbidden_semantic_fields": sorted(FORBIDDEN_SEMANTIC_FIELDS),
        "known_limitations": [
            "CASE_015 has title metadata but no authoritative raw subtitle artifact.",
            "CASE_017 is a corpus negative control and intentionally has no target video.",
            "Operational search reason_codes are retained only where required by the frozen SearchCandidate contract; no Gold reason codes are copied.",
            "Projection-session access warning is recorded in the audit and report.",
        ],
    }
    (output / "development_execution_manifest.lock.json").write_text(
        json.dumps(lock, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    audit = build_audit(
        generation_a, manifest_bytes=bytes_a, second_manifest_bytes=bytes_b,
        development_gold_sha256=file_sha256(development_gold),
        expected_development_gold_sha256=expected_development_gold_sha256,
        snapshot_before=snapshot_before, snapshot_after=file_sha256(snapshot_db),
        artifact_manifest_sha256=file_sha256(artifact_manifest),
        expected_artifact_manifest_sha256=EXPECTED_ARTIFACT_MANIFEST_SHA256,
        snapshot_db=snapshot_db,
    )
    (output / "development_execution_manifest.audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    if audit["errors"]:
        raise RuntimeError(f"projection audit failed: {audit['errors']}")
    return {"records": generation_a, "manifest_sha256": manifest_hash, "lock": lock, "audit": audit}
