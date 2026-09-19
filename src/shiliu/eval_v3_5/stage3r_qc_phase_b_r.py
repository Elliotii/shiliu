from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import Any, Callable, Mapping, Sequence

from shiliu.artifacts import ArtifactStore
from shiliu.db import Database
from shiliu.evidence.search import EvidenceSearchService
from shiliu.eval_v3_5.stage3r import _search_payload, runtime_file_hashes
from shiliu.eval_v3_5.stage3r_qc_phase_b import (
    ARTIFACT_MANIFEST_SHA256,
    SNAPSHOT_ID,
    SNAPSHOT_SHA256,
    file_sha256,
)
from shiliu.retrieval.consolidation import (
    CONSOLIDATION_VERSION,
    SearchResultConsolidator,
)
from shiliu.retrieval.dense import SQLiteExactDenseIndex
from shiliu.retrieval.enrichment import EvidenceEnricher
from shiliu.retrieval.hybrid import FUSION_VERSION, HybridRetrievalService
from shiliu.retrieval.orchestrator import SearchOrchestrator
from shiliu.retrieval.product_search import (
    PRESENTATION_VERSION,
    ProductSearchRequest,
    ProductSearchService,
)
from shiliu.retrieval.qwen import (
    QWEN_DENSE_INDEX_VERSION,
    QWEN_DIMENSION,
    QWEN_MODEL_ID,
    QWEN_MODEL_PATH,
    QWEN_MODEL_REVISION,
    QWEN_PROVIDER_VERSION,
    QwenEmbeddingProvider,
    verify_qwen_snapshot,
)
from shiliu.retrieval.service import INDEX_VERSION, RetrievalService


RUNNER_VERSION = "v3.5-stage3r-qc-phase-b-r-v1"
APPROVED_QUERY_SHA256 = "d8e60a5525556a02b454508bc8a6f0915fd6402724713389e7a2d34264484f9a"
ROUTER_VERSION = (
    "unversioned:SearchPlanner@sha256:"
    "0876dbaff9bb2d016496cc3cb823f200b9a93a06721947bebee472d6a5bdaa7e"
)
INSUFFICIENT_CASE_ID = "C2C_ee3fac675fc7d408"
RUNTIME_KEYS = (
    "mode",
    "router_behavior",
    "normalization",
    "lexical_version",
    "dense_provider",
    "embedding_model",
    "rrf_version",
    "top_k",
    "raw_top_k",
    "scope",
    "filters",
    "index_identity",
)


class PhaseBRBlocked(RuntimeError):
    def __init__(self, code: str, message: str, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for row in rows
    )
    path.write_text(body + ("\n" if rows else ""), encoding="utf-8")


def _canonical_sha(value: object) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(body.encode("utf-8")).hexdigest()


def resolve_product_default_path(repository_root: Path) -> dict[str, Any]:
    template = repository_root / "src/shiliu/templates/search.html"
    frontend = repository_root / "src/shiliu/static/search.js"
    web = repository_root / "src/shiliu/web.py"
    product = repository_root / "src/shiliu/retrieval/product_search.py"
    template_text = template.read_text(encoding="utf-8")
    frontend_text = frontend.read_text(encoding="utf-8")
    web_text = web.read_text(encoding="utf-8")
    product_text = product.read_text(encoding="utf-8")
    checks = {
        "template_first_mode_is_lexical": (
            '<option value="lexical">' in template_text
            and template_text.index('<option value="lexical">')
            < template_text.index('<option value="auto">')
        ),
        "frontend_missing_mode_defaults_lexical": (
            "params.get('mode') : 'lexical'" in frontend_text
        ),
        "frontend_payload_sends_mode": (
            "mode: state.mode" in frontend_text
            and "JSON.stringify(requestPayload(state))" in frontend_text
        ),
        "api_route_is_product_search": (
            '@web.post("/api/search")' in web_text
            and "payload: ProductSearchRequest" in web_text
            and "_core(request).product_search.search" in web_text
        ),
        "backend_schema_defaults_lexical": (
            'mode: SearchMode = "lexical"' in product_text
        ),
    }
    if not all(checks.values()):
        raise PhaseBRBlocked(
            "product_default_path_unresolved",
            "Current product-default retrieval path cannot be established from code",
            checks,
        )
    return {
        "status": "resolved",
        "view": "View P — Product Default",
        "frontend_search_component": "src/shiliu/templates/search.html#search-mode",
        "frontend_default_mode": "lexical",
        "frontend_request_payload": {
            "query": "state.q",
            "mode": "state.mode",
            "scope": "state.scope",
            "result_limit": 10,
            "max_windows_per_video": 5,
            "filters": "current form filters",
        },
        "api_route": "POST /api/search",
        "api_request_schema": "ProductSearchRequest",
        "backend_default_mode": "lexical",
        "effective_search_request_mode": "lexical",
        "router_invoked": False,
        "router_version": ROUTER_VERSION,
        "router_decision_fields": [],
        "product_top_k": 10,
        "raw_top_k": 50,
        "scope": "all",
        "filters": {},
        "source_files": [str(template), str(frontend), str(web), str(product)],
        "checks": checks,
    }


def effective_runtime_config(mode: str, *, index_identity: str = SNAPSHOT_SHA256) -> dict[str, Any]:
    if mode not in {"lexical", "hybrid"}:
        raise ValueError(f"unsupported Phase B-R mode: {mode}")
    return {
        "mode": mode,
        "router_behavior": "explicit_mode_no_auto_routing",
        "normalization": "SearchPlanner.normalize_query",
        "lexical_version": INDEX_VERSION,
        "dense_provider": QWEN_PROVIDER_VERSION if mode == "hybrid" else None,
        "embedding_model": QWEN_MODEL_ID if mode == "hybrid" else None,
        "rrf_version": FUSION_VERSION if mode == "hybrid" else None,
        "top_k": 10,
        "raw_top_k": 50,
        "scope": "all",
        "filters": {},
        "index_identity": index_identity,
    }


def runtime_configs_equivalent(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return all(left.get(key) == right.get(key) for key in RUNTIME_KEYS)


def resolve_view_reuse(
    product: Mapping[str, Any],
    lexical: Mapping[str, Any],
    hybrid: Mapping[str, Any],
) -> str | None:
    if runtime_configs_equivalent(product, lexical):
        return "lexical"
    if runtime_configs_equivalent(product, hybrid):
        return "hybrid"
    return None


def select_frozen_known_positive(repository_root: Path) -> dict[str, Any]:
    queries = load_jsonl(repository_root / "research/v3_eval/eval_queries.locked.jsonl")
    candidates = load_jsonl(repository_root / "research/v3_eval/eval_pool_candidates.jsonl")
    modes_by_query: dict[str, set[str]] = {}
    for row in candidates:
        modes_by_query.setdefault(str(row["query_id"]), set()).update(row["appeared_in_modes"])
    for row in queries:
        modes = modes_by_query.get(str(row["query_id"]), set())
        if not row.get("held_out") and {"lexical", "hybrid"} <= modes:
            return {
                "selection_rule": (
                    "first locked, non-held-out formal-eval query with frozen "
                    "lexical and hybrid candidates"
                ),
                "query_id": row["query_id"],
                "query": row["query"],
                "source": "research/v3_eval/eval_queries.locked.jsonl",
                "candidate_source": "research/v3_eval/eval_pool_candidates.jsonl",
                "frozen_modes_with_candidates": sorted(modes),
            }
    raise PhaseBRBlocked(
        "known_positive_smoke_not_available",
        "No eligible frozen known-positive query was found",
    )


def inspect_index(snapshot_db: Path) -> dict[str, Any]:
    connection = sqlite3.connect(
        f"file:{snapshot_db.resolve()}?mode=ro&immutable=1", uri=True
    )
    connection.row_factory = sqlite3.Row
    try:
        lexical = connection.execute(
            "SELECT * FROM retrieval_index_meta WHERE index_name='shiliu_lexical'"
        ).fetchone()
        dense = connection.execute(
            "SELECT * FROM retrieval_dense_index_meta WHERE index_name='shiliu_dense'"
        ).fetchone()
        units = connection.execute(
            """
            SELECT COUNT(*) total,
                   SUM(unit_type='video') videos,
                   SUM(unit_type='transcript_chunk') chunks
            FROM retrieval_units
            """
        ).fetchone()
        vectors = connection.execute(
            "SELECT COUNT(*) count FROM retrieval_dense_vectors"
        ).fetchone()
    finally:
        connection.close()
    if lexical is None or dense is None:
        raise PhaseBRBlocked("index_identity_mismatch", "Frozen lexical or dense metadata is absent")
    value = {
        "index_path": str(snapshot_db),
        "index_version": str(lexical["index_version"]),
        "index_sha256_or_manifest_identity": file_sha256(snapshot_db),
        "video_count": int(units["videos"]),
        "chunk_count": int(units["chunks"]),
        "embedding_index_available": int(vectors["count"]) == int(units["total"]),
        "embedding_vector_count": int(vectors["count"]),
        "embedding_dimension": int(dense["embedding_dimension"]),
        "source_snapshot_identity": SNAPSHOT_SHA256,
        "dense_index_version": str(dense["dense_index_version"]),
        "embedding_model": str(dense["model_id"]),
        "embedding_model_revision": str(dense["model_revision"]),
        "embedding_provider": str(dense["provider_version"]),
        "projection_version": str(dense["projection_version"]),
    }
    expected = {
        "index_sha256_or_manifest_identity": SNAPSHOT_SHA256,
        "embedding_index_available": True,
        "embedding_dimension": QWEN_DIMENSION,
        "dense_index_version": QWEN_DENSE_INDEX_VERSION,
        "embedding_model": QWEN_MODEL_ID,
        "embedding_model_revision": QWEN_MODEL_REVISION,
        "embedding_provider": QWEN_PROVIDER_VERSION,
    }
    mismatches = {
        key: {"expected": expected_value, "actual": value.get(key)}
        for key, expected_value in expected.items()
        if value.get(key) != expected_value
    }
    if mismatches:
        raise PhaseBRBlocked("index_identity_mismatch", "Frozen index identity mismatch", mismatches)
    return value


def build_search_service(
    *,
    work_db: Path,
    snapshot_artifacts: Path,
    artifact_manifest: Path,
    provider: QwenEmbeddingProvider,
) -> EvidenceSearchService:
    db = Database(work_db)
    lexical = RetrievalService(db=db, artifacts=ArtifactStore(snapshot_artifacts))

    def dense() -> SQLiteExactDenseIndex:
        return SQLiteExactDenseIndex(db=db, provider=provider)

    orchestrator = SearchOrchestrator(
        db=db,
        lexical=lexical,
        dense_factory=dense,
        hybrid_factory=lambda: HybridRetrievalService(lexical=lexical, dense=dense()),
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
        snapshot_id=SNAPSHOT_ID,
        artifact_manifest=artifact_manifest,
        runtime_corpus_identity=file_sha256(work_db),
    )


def _score(payload: Mapping[str, Any], target: Mapping[str, Any]) -> dict[str, Any]:
    target_video_id = int(target["product_video_id"])
    candidates = list(payload.get("video_candidates", []))
    matched = [
        row for row in candidates if int(row.get("video_id", -1)) == target_video_id
    ]
    raw_target = [
        row
        for row in payload.get("raw_unit_candidates", [])
        if int(row.get("video_id", -1)) == target_video_id
    ]
    return {
        "target_video_hit": bool(matched),
        "target_video_best_rank": int(matched[0]["product_rank"]) if matched else None,
        "empty_result": not candidates,
        "candidate_video_count": len(candidates),
        "candidate_chunk_count": sum(
            row.get("unit_type") == "transcript_chunk"
            for row in payload.get("raw_unit_candidates", [])
        ),
        "target_video_level_hit": bool(
            matched and matched[0].get("video_level_hit_present")
        ),
        "target_transcript_chunk_hit": any(
            row.get("unit_type") == "transcript_chunk" for row in raw_target
        ),
    }


def execute_query(
    service: EvidenceSearchService,
    query: str,
    request_base: Mapping[str, Any],
    target: Mapping[str, Any],
) -> dict[str, Any]:
    request_payload = {
        **dict(request_base),
        "query": query,
        "mode": "hybrid",
    }
    result = service.search_library(ProductSearchRequest.model_validate(request_payload))
    if result.trace_persisted or result.presentation_trace_persisted:
        raise PhaseBRBlocked("runtime_identity_not_preserved", "Search trace was persisted")
    payload = _search_payload(result)
    if payload["executed_mode"] != "hybrid" or payload["fallback_state"]["fallback"]:
        raise PhaseBRBlocked(
            "hybrid_runtime_not_operational",
            "Explicit hybrid did not execute as hybrid",
            {
                "executed_mode": payload["executed_mode"],
                "fallback_state": payload["fallback_state"],
            },
        )
    return {
        "request": request_payload,
        "payload": payload,
        "score": _score(payload, target),
        "router": {
            "requested_mode": "hybrid",
            "effective_mode": "hybrid",
            "router_invoked": False,
            "router_decision": None,
            "router_reason_codes": [],
            "router_version": ROUTER_VERSION,
        },
    }


def classify_query_contract(q0: bool, q1: bool, q2: bool) -> str:
    if q0:
        return "already_retrievable"
    if q1:
        return "single_intent_contract_recoverable"
    if q2:
        return "decomposition_recoverable"
    return "unresolved_under_mode"


def classify_retrieval_mode(
    lexical_hit: bool, product_hit: bool, hybrid_hit: bool
) -> str:
    if lexical_hit:
        return "lexical_sufficient"
    if product_hit:
        return "product_default_required"
    if hybrid_hit:
        return "explicit_hybrid_required"
    return "persistent_across_modes"


def union_q2(
    intents: Sequence[str],
    executions: Sequence[Mapping[str, Any]],
    *,
    new_calls: int,
    cache_hits: int,
) -> dict[str, Any]:
    union: dict[str, dict[str, Any]] = {}
    ranks: dict[str, int | None] = {}
    hit_intents: list[int] = []
    for index, execution in enumerate(executions, 1):
        score = execution["score"]
        ranks[str(index)] = score["target_video_best_rank"]
        if score["target_video_hit"]:
            hit_intents.append(index)
        for candidate in execution["payload"].get("video_candidates", []):
            canonical = str(candidate["source_id"])
            union.setdefault(
                canonical,
                {"canonical_video_identity": canonical, "per_intent_ranks": {}},
            )["per_intent_ranks"][str(index)] = int(candidate["product_rank"])
    return {
        "logical_intent_count": len(intents),
        "unique_execution_query_count": len(set(intents)),
        "new_retrieval_call_count": new_calls,
        "cache_hit_count": cache_hits,
        "target_video_hit": bool(hit_intents),
        "target_video_best_rank": min(
            (rank for rank in ranks.values() if rank is not None), default=None
        ),
        "target_video_per_intent_ranks": ranks,
        "target_video_hit_intents": hit_intents,
        "union_candidate_video_count": len(union),
        "all_intents_empty": all(
            execution["score"]["empty_result"] for execution in executions
        ),
        "merge_rule": "union_of_canonical_video_identities",
        "cross_intent_rerank": False,
        "union": sorted(union.values(), key=lambda row: row["canonical_video_identity"]),
    }


def _compact_execution(execution: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **execution["score"],
        "requested_mode": execution["router"]["requested_mode"],
        "effective_mode": execution["router"]["effective_mode"],
        "router_invoked": execution["router"]["router_invoked"],
        "router_decision": execution["router"]["router_decision"],
        "router_reason_codes": execution["router"]["router_reason_codes"],
        "router_version": execution["router"]["router_version"],
        "top_candidates": [
            {
                "rank": row["product_rank"],
                "title": row["title"],
                "source_id": row["source_id"],
                "top_evidence": [
                    {
                        "unit_id": evidence.get("unit_id"),
                        "excerpt": evidence.get("evidence", "")[:240],
                    }
                    for evidence in row.get("top_evidence", [])[:2]
                ],
            }
            for row in execution["payload"].get("video_candidates", [])[:3]
        ],
    }


def _write_query_execution(
    directory: Path,
    execution: Mapping[str, Any],
    *,
    cache_hit: bool,
) -> None:
    write_json(directory / "request.json", execution["request"])
    write_json(directory / "search_candidate_set.json", execution["payload"])
    write_json(
        directory / "runtime_trace.json",
        {
            **execution["router"],
            "search_trace_id": execution["payload"]["search_trace_id"],
            "index_identity": execution["payload"]["index_identity"],
            "fallback_state": execution["payload"]["fallback_state"],
        },
    )
    write_json(
        directory / "runtime_usage.json",
        {
            "retrieval_call_count": 0 if cache_hit else 1,
            "exact_query_cache_hit": cache_hit,
            "local_query_embedding_calls": 0 if cache_hit else 1,
            "embedding_cache_hits": 0,
            "external_calls": 0,
        },
    )


def _rate(numerator: int, denominator: int = 9) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": numerator / denominator if denominator else None,
    }


def _view_metrics(rows: Sequence[Mapping[str, Any]], view: str) -> dict[str, Any]:
    evidence = [row for row in rows if row["label_role"] == "evidence_bearing"]
    q0 = sum(row[view]["q0"]["target_video_hit"] for row in evidence)
    q1 = sum(row[view]["q1"]["target_video_hit"] for row in evidence)
    q2 = sum(row[view]["q2"]["target_video_hit"] for row in evidence)
    return {
        "q0_recall": _rate(q0),
        "q1_recall": _rate(q1),
        "q2_recall": _rate(q2),
        "q1_recovery_over_q0": sum(
            not row[view]["q0"]["target_video_hit"]
            and row[view]["q1"]["target_video_hit"]
            for row in evidence
        ),
        "q2_additional_recovery_over_q0_q1": sum(
            not row[view]["q0"]["target_video_hit"]
            and not row[view]["q1"]["target_video_hit"]
            and row[view]["q2"]["target_video_hit"]
            for row in evidence
        ),
        "unresolved_count": sum(
            not (
                row[view]["q0"]["target_video_hit"]
                or row[view]["q1"]["target_video_hit"]
                or row[view]["q2"]["target_video_hit"]
            )
            for row in evidence
        ),
    }


def _empty_metrics(rows: Sequence[Mapping[str, Any]], view: str) -> dict[str, Any]:
    evidence = [row for row in rows if row["label_role"] == "evidence_bearing"]
    q2_intents = [
        value
        for row in evidence
        for value in row[view]["q2"].get("intent_results", [])
    ]
    return {
        "q0_empty": _rate(sum(row[view]["q0"]["empty_result"] for row in evidence)),
        "q1_empty": _rate(sum(row[view]["q1"]["empty_result"] for row in evidence)),
        "q2_all_intents_empty": _rate(
            sum(row[view]["q2"]["all_intents_empty"] for row in evidence)
        ),
        "q2_per_intent_empty": {
            "numerator": sum(value["empty_result"] for value in q2_intents),
            "denominator": len(q2_intents),
            "rate": (
                sum(value["empty_result"] for value in q2_intents) / len(q2_intents)
                if q2_intents
                else None
            ),
        },
    }


def _file_manifest(root: Path, destination: Path) -> list[dict[str, Any]]:
    rows = [
        {
            "path": str(path.relative_to(root)),
            "sha256": file_sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in sorted(root.rglob("*"))
        if path.is_file() and path != destination
    ]
    write_jsonl(destination, rows)
    return rows


def _report(
    product_path: Mapping[str, Any],
    index: Mapping[str, Any],
    smoke: Mapping[str, Any],
    metrics: Mapping[str, Any],
    mode_effect: Mapping[str, Any],
    budget: Mapping[str, Any],
    decision: Sequence[str],
) -> str:
    def recall(view: str, kind: str) -> str:
        value = metrics[view][f"{kind}_recall"]
        return f"{value['numerator']}/{value['denominator']} ({value['rate']:.1%})"

    return "\n".join(
        [
            "# V3.5 Stage 3R-QC Phase B-R Mode-Corrected Diagnostic Report",
            "",
            "## Status",
            "",
            "Stage 3R-QC Phase B-R Complete",
            "",
            "Ready for Human Mode-corrected Diagnostic Review",
            "",
            "## Product Path",
            "",
            "- Main page path: `search.html -> search.js -> POST /api/search -> "
            "ProductSearchRequest -> ProductSearchService -> SearchOrchestrator`.",
            "- Frontend explicitly sends mode: `true`.",
            "- Frontend initial/default mode: `lexical`.",
            "- Backend schema default: `lexical`.",
            "- View P effective mode: `lexical`; Auto router invoked: `false`.",
            "- View P equals View L by all effective runtime fields: `true`.",
            "- Product results were reused from frozen lexical results; Product was not rerun.",
            "",
            "## Runtime Preflight",
            "",
            f"- Snapshot/index identity: `{index['index_sha256_or_manifest_identity']}`.",
            f"- Lexical index: `{index['index_version']}`; Hybrid fusion: `{FUSION_VERSION}`.",
            f"- Dense provider/model: `{index['embedding_provider']}` / "
            f"`{index['embedding_model']}`.",
            f"- Corpus: `{index['video_count']}` videos, `{index['chunk_count']}` chunks; "
            f"dense vectors `{index['embedding_vector_count']}` at "
            f"`{index['embedding_dimension']}` dimensions.",
            f"- Known-positive `{smoke['query_id']} / {smoke['query']}`: lexical "
            f"`{smoke['lexical_result_count']}` results; product reused lexical; hybrid "
            f"`{smoke['hybrid_result_count']}` results.",
            "- Runtime/index/scope failure: `false`.",
            "- Retrieval configuration modified or index rebuilt: `false`.",
            "",
            "## Execution",
            "",
            "- View L: fully reused from Phase B/Q0 baseline; new calls `0`.",
            "- View P: fully reused from View L; new calls `0`.",
            f"- View H formal logical/unique/new/cache: `{budget['hybrid']['logical_queries']}` / "
            f"`{budget['hybrid']['unique_queries']}` / `{budget['hybrid']['new_calls']}` / "
            f"`{budget['hybrid']['reused_results']}`.",
            f"- Local query embedding calls: formal `{budget['hybrid']['embedding_calls']}`, "
            f"preflight `1`; embedding cache hits `{budget['hybrid']['embedding_cache_hits']}`.",
            "- External calls: `0`; held-out access: `false`; candidate builder/selector calls: `0`.",
            "",
            "## Recall Matrix",
            "",
            "| View | Q0 | Q1 | Q2 |",
            "|---|---:|---:|---:|",
            f"| L Explicit Lexical | {recall('lexical', 'q0')} | "
            f"{recall('lexical', 'q1')} | {recall('lexical', 'q2')} |",
            f"| P Product Default | {recall('product_default', 'q0')} | "
            f"{recall('product_default', 'q1')} | "
            f"{recall('product_default', 'q2')} |",
            f"| H Explicit Hybrid | {recall('hybrid', 'q0')} | "
            f"{recall('hybrid', 'q1')} | {recall('hybrid', 'q2')} |",
            "",
            "Empty-result comparisons are frozen in `analysis/empty_result_matrix.json`.",
            "",
            "## Query Contract",
            "",
            f"- Product Q1 recovery over Q0: `{metrics['product_default']['q1_recovery_over_q0']}`.",
            f"- Product Q2 additional recovery: "
            f"`{metrics['product_default']['q2_additional_recovery_over_q0_q1']}`.",
            f"- Hybrid Q1 recovery over Q0: `{metrics['hybrid']['q1_recovery_over_q0']}`.",
            f"- Hybrid Q2 additional recovery: "
            f"`{metrics['hybrid']['q2_additional_recovery_over_q0_q1']}`.",
            "",
            "## Retrieval Mode",
            "",
            f"- Lexical-to-Product recovery: `{mode_effect['lexical_to_product_recovery_count']}`.",
            f"- Product-to-Hybrid recovery: `{mode_effect['product_to_hybrid_recovery_count']}`.",
            f"- Persistent across modes: `{mode_effect['persistent_across_modes_count']}`.",
            "- When Product misses and Hybrid hits, Product used explicit lexical; no Auto "
            "router decision withheld Hybrid.",
            "",
            "## Insufficient Diagnostic",
            "",
            f"`{INSUFFICIENT_CASE_ID}` is reported separately and excluded from all n=9 recall "
            "denominators. Its result only diagnoses whether a natural discovery query retrieves "
            "the topic video, not whether that video establishes time savings or error-rate claims.",
            "",
            "## Historical Interpretation",
            "",
            "Phase B lexical execution, empty-result metrics, input freeze, and runtime audit "
            "remain valid. Its global `persistent_retrieval_gap` attribution is superseded because "
            "only Explicit Lexical was run. Stage 3R Track A represents the current product default "
            "only because current code resolves Product Default to the same effective lexical "
            "configuration.",
            "",
            "## Decision",
            "",
            *[f"- `{value}`" for value in decision],
            "",
            "This diagnostic stops for human review. It does not authorize Router changes, Product "
            "Query Set work, F1A/F1B, Stage 4, or V4.",
            "",
        ]
    )


def _review_packet(rows: Sequence[Mapping[str, Any]]) -> str:
    selected = [
        row
        for row in rows
        if row["label_role"] == "insufficient_diagnostic"
        or row["retrieval_mode_classification"]
        in {"explicit_hybrid_required", "persistent_across_modes"}
        or row["hybrid"]["query_contract_classification"]
        == "decomposition_recoverable"
    ]
    lines = [
        "# Stage 3R-QC Phase B-R Human Review Packet",
        "",
        "Only mode-diagnostic cases are shown. Full gold transcripts are excluded.",
        "",
    ]
    for row in selected:
        lines.extend(
            [
                f"## {row['case_id']}",
                "",
                f"- Query type / label role: `{row['query_type']}` / `{row['label_role']}`",
                f"- Q0: `{row['hybrid']['q0']['query']}`",
                f"- Q1: `{row['hybrid']['q1']['query']}`",
                f"- Q2: `{row['hybrid']['q2']['intents']}`",
                f"- L Q0/Q1/Q2 hit: `{row['lexical']['q0']['target_video_hit']}` / "
                f"`{row['lexical']['q1']['target_video_hit']}` / "
                f"`{row['lexical']['q2']['target_video_hit']}`",
                f"- P Q0/Q1/Q2 hit: `{row['product_default']['q0']['target_video_hit']}` / "
                f"`{row['product_default']['q1']['target_video_hit']}` / "
                f"`{row['product_default']['q2']['target_video_hit']}`",
                f"- H Q0/Q1/Q2 hit: `{row['hybrid']['q0']['target_video_hit']}` / "
                f"`{row['hybrid']['q1']['target_video_hit']}` / "
                f"`{row['hybrid']['q2']['target_video_hit']}`",
                f"- Hybrid best Q0/Q1/Q2 rank: "
                f"`{row['hybrid']['q0']['target_video_best_rank']}` / "
                f"`{row['hybrid']['q1']['target_video_best_rank']}` / "
                f"`{row['hybrid']['q2']['target_video_best_rank']}`",
                "- Product router decision: explicit lexical; Auto router not invoked.",
                f"- Query contract classification (P/H): "
                f"`{row['product_default']['query_contract_classification']}` / "
                f"`{row['hybrid']['query_contract_classification']}`",
                f"- Retrieval mode classification: `{row['retrieval_mode_classification']}`",
                "",
                "Hybrid top candidates:",
                "",
            ]
        )
        top = row["hybrid"]["q1"].get("top_candidates", [])
        if not top:
            lines.append("- Empty")
        for candidate in top:
            excerpts = " | ".join(
                value["excerpt"] for value in candidate["top_evidence"] if value["excerpt"]
            )
            lines.append(
                f"- #{candidate['rank']} {candidate['title']}: {excerpts[:360]}"
            )
        lines.append("")
    return "\n".join(lines)


def run_phase_b_r(
    *,
    repository_root: Path,
    snapshot_db: Path,
    snapshot_artifacts: Path,
    artifact_manifest: Path,
    provider_factory: Callable[[], QwenEmbeddingProvider] = QwenEmbeddingProvider,
) -> dict[str, Any]:
    output = repository_root / "research/v3_5/stage3r_qc/phase_b_r"
    phase_b = repository_root / "research/v3_5/stage3r_qc/phase_b"
    approved = phase_b / "input_freeze/approved_query_decisions.jsonl"
    if file_sha256(approved) != APPROVED_QUERY_SHA256:
        raise PhaseBRBlocked("approved_query_hash_mismatch", "Approved query hash mismatch")
    decisions = sorted(load_jsonl(approved), key=lambda row: row["case_id"])
    cases = {
        row["case_id"]: row
        for row in load_jsonl(
            repository_root
            / "research/v3_5/stage3r_qc/sample/selected_cases.internal.jsonl"
        )
    }
    identities = {
        row["case_id"]: row
        for row in load_jsonl(
            repository_root
            / "research/v3_5/stage3r_qc/video_identity/canonical_video_identity_mapping.jsonl"
        )
    }
    phase_b_rows = {
        row["case_id"]: row
        for row in load_jsonl(phase_b / "scoring/case_results.jsonl")
    }
    runtimes = {
        row["case_id"]: row
        for row in load_jsonl(
            repository_root
            / "research/v3_5/stage3r/execution_manifest/development_runtime_input.31_cases.jsonl"
        )
    }
    case_ids = [row["case_id"] for row in decisions]
    if (
        len(decisions) != 10
        or set(case_ids) != set(cases)
        or set(case_ids) - set(phase_b_rows)
        or set(case_ids) - set(identities)
        or set(case_ids) - set(runtimes)
    ):
        raise PhaseBRBlocked("phase_a_case_alignment_failed", "Frozen case alignment failed")

    product_path = resolve_product_default_path(repository_root)
    lexical_config = effective_runtime_config("lexical")
    product_config = effective_runtime_config(product_path["effective_search_request_mode"])
    hybrid_config = effective_runtime_config("hybrid")
    product_reuse = resolve_view_reuse(product_config, lexical_config, hybrid_config)
    if product_reuse != "lexical":
        raise PhaseBRBlocked(
            "product_view_equivalence_unresolved",
            "Current Product view is not safely reusable from frozen Lexical",
        )

    if file_sha256(snapshot_db) != SNAPSHOT_SHA256:
        raise PhaseBRBlocked("snapshot_hash_mismatch", "Frozen snapshot hash mismatch")
    if file_sha256(artifact_manifest) != ARTIFACT_MANIFEST_SHA256:
        raise PhaseBRBlocked("artifact_manifest_hash_mismatch", "Artifact manifest hash mismatch")
    runtime_before = runtime_file_hashes(repository_root)
    frozen_runtime_hashes = {
        row["path"]: row["sha256"]
        for row in load_jsonl(
            repository_root
            / "research/v3_5/stage3r/runtime_freeze/runtime_source_file_hashes.jsonl"
        )
    }
    if any(
        frozen_runtime_hashes.get(row["path"]) != row["sha256"]
        for row in runtime_before
    ):
        raise PhaseBRBlocked("runtime_file_hash_mismatch", "Frozen runtime files changed")
    index = inspect_index(snapshot_db)
    verify_qwen_snapshot(QWEN_MODEL_PATH)
    provider = provider_factory()
    provider_identity = asdict(provider.model_identity())
    if provider_identity["provider_version"] != QWEN_PROVIDER_VERSION:
        raise PhaseBRBlocked("embedding_provider_mismatch", "Provider identity mismatch")
    smoke_query = select_frozen_known_positive(repository_root)

    write_json(
        output / "input_validation/approved_query_validation.json",
        {
            "records": len(decisions),
            "case_alignment_with_phase_a": True,
            "byte_preserved_phase_b_freeze": True,
            "sha256_match": True,
            "sha256": file_sha256(approved),
            "queries_modified": False,
        },
    )
    write_jsonl(
        output / "input_validation/approved_query_decisions.reference.jsonl",
        [
            {
                "case_id": row["case_id"],
                "q1_sha256": sha256(row["q1_discovery_query"].encode()).hexdigest(),
                "q2_sha256": [
                    sha256(value.encode()).hexdigest()
                    for value in row["q2_retrieval_intents"]
                ],
            }
            for row in decisions
        ],
    )
    write_json(output / "product_path/product_default_resolution.json", product_path)
    write_json(output / "product_path/product_default_runtime_config.json", product_config)
    write_json(
        output / "product_path/product_default_resolution.audit.json",
        {
            "resolved": True,
            "product_default_effective_config_equals_lexical": True,
            "product_default_effective_config_equals_hybrid": False,
            "product_default_reused_from_lexical": True,
            "product_default_reused_from_hybrid": False,
            "effective_fields_compared": list(RUNTIME_KEYS),
        },
    )
    for query_kind in ("q0", "q1", "q2"):
        write_json(
            output
            / f"execution/product_default/{query_kind}/view_reuse.audit.json",
            {
                "view": "P",
                "query_kind": query_kind,
                "effective_mode": "lexical",
                "reused_from_view": "L",
                "source": (
                    "research/v3_5/stage3r_qc/q0_baseline"
                    if query_kind == "q0"
                    else "research/v3_5/stage3r_qc/phase_b"
                ),
                "new_retrieval_call_count": 0,
                "equivalence_fields": list(RUNTIME_KEYS),
                "effective_config_equal": True,
            },
        )
    (output / "product_path/frontend_search_path.md").write_text(
        "# Frontend Search Path\n\n"
        "`search.html` defaults the first mode option to `lexical`; `search.js` restores a "
        "missing URL mode to `lexical` and explicitly sends it in the JSON request to "
        "`POST /api/search`.\n",
        encoding="utf-8",
    )
    (output / "product_path/backend_search_path.md").write_text(
        "# Backend Search Path\n\n"
        "`POST /api/search` validates `ProductSearchRequest` (backend default `lexical`) "
        "and calls `ProductSearchService.search`, which constructs `SearchRequest` and "
        "invokes `SearchOrchestrator.search_raw`. Explicit lexical does not invoke Auto "
        "routing.\n",
        encoding="utf-8",
    )
    for name, config in (
        ("lexical", lexical_config),
        ("product_default", product_config),
        ("hybrid", hybrid_config),
    ):
        write_json(
            output / f"runtime_preflight/{name}_runtime_identity.json",
            {**config, "runtime_identity_sha256": _canonical_sha(config)},
        )
    write_json(
        output / "runtime_preflight/runtime_equivalence_matrix.json",
        {
            "lexical_equals_product_default": True,
            "lexical_equals_hybrid": False,
            "product_default_equals_hybrid": False,
            "compared_fields": list(RUNTIME_KEYS),
        },
    )
    write_jsonl(
        output / "runtime_preflight/runtime_file_hashes.before.jsonl", runtime_before
    )
    write_json(output / "runtime_preflight/index_identity.json", index)
    write_json(
        output / "runtime_preflight/embedding_provider_identity.json", provider_identity
    )
    write_json(
        output / "runtime_preflight/known_positive_selection.json", smoke_query
    )

    formal_calls = 0
    cache_hits = 0
    q0_calls = q1_calls = q2_calls = 0
    cache: dict[str, dict[str, Any]] = {}
    hybrid_cases: dict[str, dict[str, Any]] = {}
    snapshot_before = file_sha256(snapshot_db)
    with tempfile.TemporaryDirectory(prefix="shiliu-stage3r-qc-phase-b-r-") as temporary:
        work_db = Path(temporary) / "snapshot-work-copy.db"
        shutil.copy2(snapshot_db, work_db)
        service = build_search_service(
            work_db=work_db,
            snapshot_artifacts=snapshot_artifacts,
            artifact_manifest=artifact_manifest,
            provider=provider,
        )
        smoke_base = {
            "mode": "lexical",
            "scope": "all",
            "result_limit": 10,
            "max_windows_per_video": 2,
            "filters": {},
        }
        lexical_smoke = service.search_library(
            ProductSearchRequest(query=smoke_query["query"], **smoke_base)
        )
        hybrid_smoke = service.search_library(
            ProductSearchRequest(
                query=smoke_query["query"], **{**smoke_base, "mode": "hybrid"}
            )
        )
        smoke = {
            **smoke_query,
            "lexical_result_count": len(lexical_smoke.video_candidates),
            "product_result_count": len(lexical_smoke.video_candidates),
            "product_reused_from_lexical": True,
            "hybrid_result_count": len(hybrid_smoke.video_candidates),
            "lexical_known_positive_returns_results": bool(
                lexical_smoke.video_candidates
            ),
            "product_default_known_positive_returns_results": bool(
                lexical_smoke.video_candidates
            ),
            "hybrid_known_positive_returns_results": bool(
                hybrid_smoke.video_candidates
            ),
        }
        if not all(
            smoke[key]
            for key in (
                "lexical_known_positive_returns_results",
                "product_default_known_positive_returns_results",
                "hybrid_known_positive_returns_results",
            )
        ):
            raise PhaseBRBlocked(
                "known_positive_smoke_failed",
                "Known-positive smoke returned no results in an applicable mode",
                smoke,
            )
        write_json(output / "runtime_preflight/known_positive_smoke.audit.json", smoke)

        def get_execution(
            query: str,
            request_base: Mapping[str, Any],
            target: Mapping[str, Any],
            directory: Path,
            kind: str,
        ) -> tuple[dict[str, Any], bool]:
            nonlocal formal_calls, cache_hits, q0_calls, q1_calls, q2_calls
            cache_hit = query in cache
            if cache_hit:
                execution = cache[query]
                cache_hits += 1
            else:
                execution = execute_query(service, query, request_base, target)
                cache[query] = execution
                formal_calls += 1
                if kind == "q0":
                    q0_calls += 1
                elif kind == "q1":
                    q1_calls += 1
                else:
                    q2_calls += 1
            _write_query_execution(directory, execution, cache_hit=cache_hit)
            return execution, cache_hit

        for decision in decisions:
            case_id = decision["case_id"]
            target = identities[case_id]["runtime_canonical_video_identity"]
            request_base = runtimes[case_id]["track_a"]["search_request"]
            case_root = output / "execution/hybrid"
            q0_query = cases[case_id]["original_query"]
            q0, q0_cached = get_execution(
                q0_query,
                request_base,
                target,
                case_root / "q0/cases" / case_id,
                "q0",
            )
            q1_query = decision["q1_discovery_query"]
            q1, q1_cached = get_execution(
                q1_query,
                request_base,
                target,
                case_root / "q1/cases" / case_id,
                "q1",
            )
            intent_executions: list[dict[str, Any]] = []
            intent_rows: list[dict[str, Any]] = []
            q2_new = q2_cache = 0
            for index_value, intent in enumerate(decision["q2_retrieval_intents"], 1):
                execution, cached = get_execution(
                    intent,
                    request_base,
                    target,
                    case_root / "q2/cases" / case_id / f"intent_{index_value:02d}",
                    "q2",
                )
                q2_cache += int(cached)
                q2_new += int(not cached)
                intent_executions.append(execution)
                intent_rows.append(
                    {
                        "intent_index": index_value,
                        "query": intent,
                        **execution["score"],
                        "exact_query_cache_hit": cached,
                    }
                )
            q2 = union_q2(
                decision["q2_retrieval_intents"],
                intent_executions,
                new_calls=q2_new,
                cache_hits=q2_cache,
            )
            q2["intents"] = list(decision["q2_retrieval_intents"])
            q2["intent_results"] = intent_rows
            write_json(
                case_root / "q2/cases" / case_id / "q2_union.json",
                {
                    "merge_rule": q2["merge_rule"],
                    "cross_intent_rerank": False,
                    "union": q2.pop("union"),
                },
            )
            write_json(
                case_root / "q2/cases" / case_id / "q2_case_summary.json", q2
            )
            hybrid_cases[case_id] = {
                "q0": {
                    "query": q0_query,
                    **_compact_execution(q0),
                    "exact_query_cache_hit": q0_cached,
                },
                "q1": {
                    "query": q1_query,
                    **_compact_execution(q1),
                    "exact_query_cache_hit": q1_cached,
                },
                "q2": q2,
            }

    if file_sha256(snapshot_db) != snapshot_before:
        raise PhaseBRBlocked("snapshot_modified", "Frozen snapshot changed during execution")
    runtime_after = runtime_file_hashes(repository_root)
    if runtime_after != runtime_before:
        raise PhaseBRBlocked("runtime_hash_unstable", "Runtime hashes changed during execution")

    rows: list[dict[str, Any]] = []
    for decision in decisions:
        case_id = decision["case_id"]
        old = phase_b_rows[case_id]
        lexical = {
            "source": "reused_phase_b",
            "q0": {
                "query": old["q0"]["query"],
                "target_video_hit": old["q0"]["target_hit"],
                "target_video_best_rank": old["q0"]["target_rank"],
                "empty_result": old["q0"]["empty_result"],
                "candidate_video_count": old["q0"]["candidate_video_count"],
            },
            "q1": {
                "query": old["q1"]["query"],
                "target_video_hit": old["q1"]["target_hit"],
                "target_video_best_rank": old["q1"]["target_rank"],
                "empty_result": old["q1"]["empty_result"],
                "candidate_video_count": old["q1"]["candidate_video_count"],
            },
            "q2": {
                "intents": old["q2"]["intents"],
                "target_video_hit": old["q2"]["target_hit"],
                "target_video_best_rank": old["q2"]["target_best_rank"],
                "all_intents_empty": old["q2"]["all_intents_empty"],
                "intent_results": [
                    {
                        "query": query,
                        "empty_result": old["q2"]["all_intents_empty"],
                    }
                    for query in old["q2"]["intents"]
                ],
            },
        }
        lexical["query_contract_classification"] = classify_query_contract(
            lexical["q0"]["target_video_hit"],
            lexical["q1"]["target_video_hit"],
            lexical["q2"]["target_video_hit"],
        )
        product = json.loads(json.dumps(lexical))
        product.update(
            {
                "effective_mode": "lexical",
                "reused_from_view": "lexical",
                "router_decisions": [],
            }
        )
        hybrid = {
            **hybrid_cases[case_id],
            "reused_from_view": None,
            "query_contract_classification": classify_query_contract(
                hybrid_cases[case_id]["q0"]["target_video_hit"],
                hybrid_cases[case_id]["q1"]["target_video_hit"],
                hybrid_cases[case_id]["q2"]["target_video_hit"],
            ),
        }
        lexical_any = any(
            lexical[kind]["target_video_hit"] for kind in ("q0", "q1", "q2")
        )
        hybrid_any = any(
            hybrid[kind]["target_video_hit"] for kind in ("q0", "q1", "q2")
        )
        rows.append(
            {
                "case_id": case_id,
                "label_role": (
                    "insufficient_diagnostic"
                    if case_id == INSUFFICIENT_CASE_ID
                    else "evidence_bearing"
                ),
                "query_type": cases[case_id]["query_type"],
                "lexical": lexical,
                "product_default": product,
                "hybrid": hybrid,
                "retrieval_mode_classification": classify_retrieval_mode(
                    lexical_any, lexical_any, hybrid_any
                ),
                "identity_failure": not identities[case_id]["identity_resolved"],
                "runtime_failure": False,
                "notes": (
                    "Insufficient-label diagnostic excluded from main recall."
                    if case_id == INSUFFICIENT_CASE_ID
                    else ""
                ),
            }
        )
    write_jsonl(output / "scoring/case_results.mode_corrected.jsonl", rows)

    metrics = {
        view: _view_metrics(rows, view)
        for view in ("lexical", "product_default", "hybrid")
    }
    mode_counts = Counter(
        row["retrieval_mode_classification"]
        for row in rows
        if row["label_role"] == "evidence_bearing"
    )
    mode_effect = {
        "lexical_to_product_recovery_count": mode_counts["product_default_required"],
        "product_to_hybrid_recovery_count": mode_counts["explicit_hybrid_required"],
        "persistent_across_modes_count": mode_counts["persistent_across_modes"],
        "classification_counts": dict(sorted(mode_counts.items())),
    }
    logical_queries = sum(
        2 + len(row["q2_retrieval_intents"]) for row in decisions
    )
    budget = {
        "lexical": {
            "logical_queries": logical_queries,
            "new_calls": 0,
            "source": "reused_phase_b",
        },
        "product_default": {
            "logical_queries": logical_queries,
            "unique_queries": len(
                {
                    query
                    for row in decisions
                    for query in (
                        cases[row["case_id"]]["original_query"],
                        row["q1_discovery_query"],
                        *row["q2_retrieval_intents"],
                    )
                }
            ),
            "new_calls": 0,
            "reused_results": logical_queries,
            "embedding_calls": 0,
            "embedding_cache_hits": 0,
        },
        "hybrid": {
            "logical_queries": logical_queries,
            "unique_queries": len(cache),
            "new_calls": formal_calls,
            "reused_results": cache_hits,
            "exact_duplicate_reuse_count": cache_hits,
            "q0_new_calls": q0_calls,
            "q1_new_calls": q1_calls,
            "q2_new_calls": q2_calls,
            "embedding_calls": formal_calls,
            "embedding_cache_hits": 0,
        },
        "preflight": {
            "lexical_calls": 1,
            "hybrid_calls": 1,
            "embedding_calls": 1,
        },
    }
    empty = {
        view: _empty_metrics(rows, view)
        for view in ("lexical", "product_default", "hybrid")
    }
    insufficient = next(
        row for row in rows if row["case_id"] == INSUFFICIENT_CASE_ID
    )
    write_json(output / "analysis/retrieval_matrix.json", metrics)
    write_json(output / "analysis/query_contract_effect.json", metrics)
    write_json(output / "analysis/retrieval_mode_effect.json", mode_effect)
    write_json(output / "analysis/empty_result_matrix.json", empty)
    write_json(output / "analysis/retrieval_budget.json", budget)
    write_json(output / "analysis/insufficient_diagnostic.json", insufficient)
    write_json(
        output / "analysis/router_distribution.json",
        {
            "product_default": {
                "q0_router_distribution": {"not_invoked_explicit_lexical": 10},
                "q1_router_distribution": {"not_invoked_explicit_lexical": 10},
                "q2_router_distribution": {
                    "not_invoked_explicit_lexical": sum(
                        len(row["q2_retrieval_intents"]) for row in decisions
                    )
                },
            },
            "hybrid": {
                "q0_router_distribution": {"not_invoked_explicit_hybrid": 10},
                "q1_router_distribution": {"not_invoked_explicit_hybrid": 10},
                "q2_router_distribution": {
                    "not_invoked_explicit_hybrid": sum(
                        len(row["q2_retrieval_intents"]) for row in decisions
                    )
                },
            },
        },
    )

    decisions_out: list[str] = []
    if mode_effect["product_to_hybrid_recovery_count"]:
        decisions_out.append("frozen_hybrid_capable_but_product_default_gap")
    if (
        metrics["hybrid"]["q1_recovery_over_q0"]
        or metrics["hybrid"]["q2_additional_recovery_over_q0_q1"]
    ):
        decisions_out.append("query_contract_recovery_observed")
    if metrics["hybrid"]["unresolved_count"] > 4:
        decisions_out.append("persistent_frozen_v3_retrieval_gap_observed")
    if not decisions_out:
        decisions_out.append("product_default_retrieval_capable_on_qc_sample")
    write_json(
        output / "history/phase_b_result_reinterpretation.json",
        {
            "preserved": [
                "Phase B Lexical execution",
                "Phase B Lexical empty-result metrics",
                "Phase B input freeze",
                "Phase B runtime audit",
            ],
            "superseded": ["Phase B global persistent_retrieval_gap interpretation"],
            "reason": [
                "Phase B only executed Explicit Lexical",
                "Product-default and Hybrid were not evaluated",
            ],
        },
    )
    write_json(
        output / "history/phase_b_classification_supersession.json",
        {
            "phase_b_lexical_data_valid": True,
            "global_classification_superseded": True,
            "replacement_source": "scoring/case_results.mode_corrected.jsonl",
        },
    )
    write_jsonl(
        output / "runtime_freeze/runtime_file_hashes.after.jsonl", runtime_after
    )
    write_json(
        output / "runtime_freeze/runtime_integrity.audit.json",
        {
            "runtime_hashes_stable": runtime_before == runtime_after,
            "snapshot_hash_stable": file_sha256(snapshot_db) == snapshot_before,
            "retrieval_parameters_modified": False,
            "index_rebuilt": False,
        },
    )
    write_json(
        output / "isolation/heldout_access.audit.json",
        {
            "heldout_accessed": False,
            "known_positive_held_out": False,
            "external_llm_calls": 0,
            "external_embedding_calls": 0,
            "external_network_calls": 0,
            "candidate_builder_calls": 0,
            "selector_calls": 0,
        },
    )
    report_path = output / "V3_5_STAGE3R_QC_PHASE_B_R_MODE_CORRECTED_DIAGNOSTIC_REPORT.md"
    report_path.write_text(
        _report(product_path, index, smoke, metrics, mode_effect, budget, decisions_out),
        encoding="utf-8",
    )
    review_path = output / "STAGE3R_QC_PHASE_B_R_HUMAN_REVIEW_PACKET.md"
    review_path.write_text(_review_packet(rows), encoding="utf-8")
    write_json(
        output / "review/review_selection.json",
        {
            "selection_policy": [
                "product_default_miss_and_hybrid_hit",
                "persistent_across_modes",
                "decomposition_recoverable",
                "router_or_runtime_anomaly",
                "insufficient_diagnostic",
            ],
            "selected_case_ids": [
                row["case_id"]
                for row in rows
                if row["label_role"] == "insufficient_diagnostic"
                or row["retrieval_mode_classification"]
                in {"explicit_hybrid_required", "persistent_across_modes"}
                or row["hybrid"]["query_contract_classification"]
                == "decomposition_recoverable"
            ],
            "full_gold_transcript_included": False,
            "packet": str(review_path.relative_to(repository_root)),
        },
    )
    execution_audit = {
        "stage": "Stage 3R-QC Phase B-R",
        "status": "complete",
        "runner_version": RUNNER_VERSION,
        "recorded_at": utc_now(),
        "product_default_effective_mode": "lexical",
        "product_default_reused_from_lexical": True,
        "runtime_preflight_passed": True,
        "lexical_rerun": False,
        "product_default_rerun": False,
        "hybrid_q0_q1_q2_completed": True,
        "query_contract_and_retrieval_mode_effects_separated": True,
        "retrieval_configuration_modified": False,
        "index_rebuilt": False,
        "heldout_accessed": False,
        "external_calls": 0,
        "decision": decisions_out,
    }
    write_json(output / "stage3r_qc_phase_b_r_execution.audit.json", execution_audit)
    write_json(output / "stage3r_qc_phase_b_r_runtime_usage.json", budget)
    write_json(
        output / "tests/contract_summary.json",
        {
            "approved_query_hash_match": True,
            "phase_b_lexical_reused": True,
            "lexical_rerun": False,
            "product_path_resolved": True,
            "product_default_assumed_auto": False,
            "effective_configs_compared": True,
            "known_positive_smoke_passed": True,
            "index_rebuilt": False,
            "queries_modified": False,
            "exact_only_deduplication": True,
            "canonical_identity_used": True,
            "q2_union_only": True,
            "q2_reranked": False,
            "insufficient_excluded_from_recall": True,
            "heldout_accessed": False,
            "external_calls": 0,
        },
    )
    manifest = {
        "stage": "Stage 3R-QC Phase B-R",
        "status": "complete",
        "runner_version": RUNNER_VERSION,
        "views": {
            "L": "reused_phase_b_explicit_lexical",
            "P": "reused_from_L_product_default_lexical",
            "H": "new_explicit_hybrid",
        },
        "case_count": 10,
        "evidence_bearing_case_count": 9,
        "insufficient_diagnostic_case_count": 1,
        "decision": decisions_out,
        "report": str(report_path.relative_to(repository_root)),
        "review_packet": str(review_path.relative_to(repository_root)),
    }
    write_json(output / "stage3r_qc_phase_b_r_manifest.json", manifest)
    _file_manifest(
        output, output / "stage3r_qc_phase_b_r_file_hash_manifest.jsonl"
    )
    return {
        **execution_audit,
        "metrics": metrics,
        "mode_effect": mode_effect,
        "budget": budget,
        "report_path": str(report_path),
        "review_packet_path": str(review_path),
        "session_may_close": True,
    }


def write_blocked_attempt(repository_root: Path, error: PhaseBRBlocked) -> dict[str, Any]:
    output = repository_root / "research/v3_5/stage3r_qc/phase_b_r"
    audit = {
        "stage": "Stage 3R-QC Phase B-R",
        "status": "blocked",
        "reason_code": error.code,
        "message": str(error),
        "details": error.details,
        "recorded_at": utc_now(),
        "retrieval_quality_conclusion_formed": False,
        "retrieval_configuration_modified": False,
        "index_rebuilt": False,
        "heldout_accessed": False,
        "external_calls": 0,
        "decision": ["runtime_or_index_execution_blocker"],
    }
    write_json(output / "stage3r_qc_phase_b_r_execution.audit.json", audit)
    return audit
