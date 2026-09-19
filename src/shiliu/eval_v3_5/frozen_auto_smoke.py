from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import statistics
import tempfile
from typing import Any, Mapping, Sequence

from shiliu.eval_v3_5.stage3r_qc_phase_b import (
    ARTIFACT_MANIFEST_SHA256,
    SNAPSHOT_ID,
    SNAPSHOT_SHA256,
    file_sha256,
)
from shiliu.eval_v3_5.stage3r_qc_phase_b_r import (
    APPROVED_QUERY_SHA256,
    INSUFFICIENT_CASE_ID,
    ROUTER_VERSION,
    build_search_service,
    inspect_index,
    load_jsonl,
    resolve_product_default_path,
    write_json,
    write_jsonl,
)
from shiliu.eval_v3_5.runtime_guard import (
    FrozenEvalRuntimeConfig,
    FrozenEvalRuntimeGuardError,
    preflight_frozen_eval_runtime,
)
from shiliu.retrieval.hybrid import FUSION_VERSION
from shiliu.retrieval.planner import SearchPlanner
from shiliu.retrieval.product_search import ProductSearchRequest
from shiliu.retrieval.qwen import (
    QWEN_MODEL_ID,
    QWEN_MODEL_PATH,
    QWEN_PROVIDER_VERSION,
    QwenEmbeddingProvider,
    verify_qwen_snapshot,
)
from shiliu.retrieval.service import INDEX_VERSION


RUNNER_VERSION = "v3.5-frozen-auto-smoke-v1"
OUTPUT_RELATIVE = Path("research/v3_5/auto_smoke")
APPROVED_RELATIVE = Path(
    "research/v3_5/stage3r_qc/phase_b/input_freeze/"
    "approved_query_decisions.jsonl"
)
CASE_RELATIVE = Path(
    "research/v3_5/stage3r_qc/sample/selected_cases.internal.jsonl"
)
IDENTITY_RELATIVE = Path(
    "research/v3_5/stage3r_qc/video_identity/"
    "canonical_video_identity_mapping.jsonl"
)
CONTROL_RELATIVE = Path(
    "research/v3_5/stage3r_qc/phase_b_r/scoring/"
    "case_results.mode_corrected.jsonl"
)
RUNTIME_INPUT_RELATIVE = Path(
    "research/v3_5/stage3r/execution_manifest/"
    "development_runtime_input.31_cases.jsonl"
)
FORMAL_QUERY_RELATIVE = Path("research/v3_eval/eval_queries.locked.jsonl")
FORMAL_RESULT_RELATIVE = Path("research/v3_eval/eval_per_query_results.jsonl")
FORMAL_GOLD_RELATIVE = Path(
    "research/v3_eval/eval_gold_review.decisions.amended.jsonl"
)
AUTO_RUNTIME_SOURCE_FILES = (
    "src/shiliu/retrieval/planner.py",
    "src/shiliu/retrieval/orchestrator.py",
    "src/shiliu/retrieval/service.py",
    "src/shiliu/retrieval/dense.py",
    "src/shiliu/retrieval/hybrid.py",
    "src/shiliu/retrieval/qwen.py",
    "src/shiliu/retrieval/product_search.py",
    "src/shiliu/retrieval/consolidation.py",
    "src/shiliu/retrieval/enrichment.py",
    "src/shiliu/evidence/search.py",
    "src/shiliu/templates/search.html",
    "src/shiliu/static/search.js",
    "src/shiliu/web.py",
)


class FrozenAutoSmokeBlocked(RuntimeError):
    def __init__(
        self, code: str, message: str, details: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


class CountingEmbeddingProvider:
    def __init__(self, provider: QwenEmbeddingProvider | None = None) -> None:
        self.provider = provider or QwenEmbeddingProvider()
        self.query_call_count = 0
        self.document_call_count = 0

    def model_identity(self):
        return self.provider.model_identity()

    def __getattr__(self, name: str):
        return getattr(self.provider, name)

    def embed_query(self, text: str):
        self.query_call_count += 1
        return self.provider.embed_query(text)

    def embed_documents(self, texts: Sequence[str]):
        self.document_call_count += len(texts)
        return self.provider.embed_documents(texts)

    @property
    def load_count(self) -> int:
        return self.provider.load_count

    @property
    def active_device(self) -> str | None:
        return self.provider.active_device


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_sha(value: object) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(body.encode("utf-8")).hexdigest()


def runtime_file_hashes(repository_root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": relative,
            "sha256": file_sha256(repository_root / relative),
            "bytes": (repository_root / relative).stat().st_size,
        }
        for relative in AUTO_RUNTIME_SOURCE_FILES
    ]


def validate_product_defaults(repository_root: Path) -> dict[str, Any]:
    try:
        resolved = resolve_product_default_path(repository_root)
    except Exception as exc:
        raise FrozenAutoSmokeBlocked(
            "product_default_modified",
            "Frontend or backend product default is not frozen lexical",
            {"error": f"{type(exc).__name__}: {exc}"},
        ) from exc
    if (
        resolved["frontend_default_mode"] != "lexical"
        or resolved["backend_default_mode"] != "lexical"
    ):
        raise FrozenAutoSmokeBlocked(
            "product_default_modified",
            "Product default was changed before frozen Auto validation",
            resolved,
        )
    return resolved


def auto_runtime_identity(repository_root: Path) -> dict[str, Any]:
    planner_path = repository_root / "src/shiliu/retrieval/planner.py"
    actual_router_version = (
        f"unversioned:SearchPlanner@sha256:{file_sha256(planner_path)}"
    )
    if actual_router_version != ROUTER_VERSION:
        raise FrozenAutoSmokeBlocked(
            "auto_router_identity_mismatch",
            "Auto Router source identity differs from the frozen router version",
            {"expected": ROUTER_VERSION, "actual": actual_router_version},
        )
    return {
        "auto_router_version": actual_router_version,
        "auto_router_module": "shiliu.retrieval.planner",
        "auto_router_entrypoint": "SearchPlanner.plan",
        "query_classifier_entrypoint": "classify_query",
        "lexical_version": INDEX_VERSION,
        "dense_provider": QWEN_PROVIDER_VERSION,
        "embedding_model": QWEN_MODEL_ID,
        "hybrid_rrf_version": FUSION_VERSION,
        "normalization": "SearchPlanner.normalize_query",
        "top_k": 10,
        "raw_top_k": 50,
        "scope": "all",
        "filters": {},
        "router_rules_modified": False,
        "retrieval_configuration_modified": False,
    }


def load_frozen_inputs(repository_root: Path) -> dict[str, Any]:
    approved_path = repository_root / APPROVED_RELATIVE
    approved_hash = file_sha256(approved_path)
    if approved_hash != APPROVED_QUERY_SHA256:
        raise FrozenAutoSmokeBlocked(
            "approved_query_hash_mismatch",
            "Approved Q1/Q2 query file does not match its frozen SHA-256",
            {"expected": APPROVED_QUERY_SHA256, "actual": approved_hash},
        )
    decisions = sorted(load_jsonl(approved_path), key=lambda row: row["case_id"])
    cases = {
        row["case_id"]: row
        for row in load_jsonl(repository_root / CASE_RELATIVE)
    }
    identities = {
        row["case_id"]: row
        for row in load_jsonl(repository_root / IDENTITY_RELATIVE)
    }
    controls = {
        row["case_id"]: row
        for row in load_jsonl(repository_root / CONTROL_RELATIVE)
    }
    runtimes = {
        row["case_id"]: row
        for row in load_jsonl(repository_root / RUNTIME_INPUT_RELATIVE)
    }
    decision_ids = {row["case_id"] for row in decisions}
    if (
        len(decisions) != 10
        or decision_ids != set(cases)
        or decision_ids - set(identities)
        or decision_ids - set(controls)
        or decision_ids - set(runtimes)
    ):
        raise FrozenAutoSmokeBlocked(
            "frozen_case_alignment_failed",
            "Frozen Phase A cases, approved queries, identities, controls, or runtimes differ",
            {
                "decision_count": len(decisions),
                "case_count": len(cases),
                "identity_count": len(identities),
                "control_count": len(controls),
            },
        )
    for row in decisions:
        case_id = row["case_id"]
        control = controls[case_id]
        if (
            control["lexical"]["q0"]["query"] != cases[case_id]["original_query"]
            or control["lexical"]["q1"]["query"] != row["q1_discovery_query"]
            or control["lexical"]["q2"]["intents"] != row["q2_retrieval_intents"]
        ):
            raise FrozenAutoSmokeBlocked(
                "frozen_query_mismatch",
                "Phase B-R controls do not preserve the approved queries",
                {"case_id": case_id},
            )
    return {
        "decisions": decisions,
        "cases": cases,
        "identities": identities,
        "controls": controls,
        "runtimes": runtimes,
        "approved_query_sha256": approved_hash,
    }


def select_known_positive_queries(repository_root: Path) -> dict[str, dict[str, Any]]:
    rows = load_jsonl(repository_root / FORMAL_RESULT_RELATIVE)
    eligible = [
        row
        for row in rows
        if not row.get("held_out")
        and row.get("systems", {}).get("auto", {}).get("product_video_ids")
    ]
    lexical = next(
        (
            row
            for row in eligible
            if row["systems"]["auto"]["executed_mode"] == "lexical"
        ),
        None,
    )
    hybrid = next(
        (
            row
            for row in eligible
            if row["systems"]["auto"]["executed_mode"] == "hybrid"
        ),
        None,
    )
    if lexical is None or hybrid is None:
        raise FrozenAutoSmokeBlocked(
            "known_positive_selection_unavailable",
            "Frozen non-held-out Auto lexical/hybrid known positives are unavailable",
        )
    return {
        "lexical": {
            "query_id": lexical["query_id"],
            "query": lexical["query"],
            "scope": lexical["systems"]["auto"]["plan"]["scope"],
            "filters": lexical["systems"]["auto"]["plan"]["validated_filters"],
            "expected_auto_branch": "lexical",
            "source_artifact": str(FORMAL_RESULT_RELATIVE),
            "selection_rule": "first non-held-out frozen Auto result routed lexical",
        },
        "hybrid": {
            "query_id": hybrid["query_id"],
            "query": hybrid["query"],
            "scope": hybrid["systems"]["auto"]["plan"]["scope"],
            "filters": hybrid["systems"]["auto"]["plan"]["validated_filters"],
            "expected_auto_branch": "hybrid",
            "source_artifact": str(FORMAL_RESULT_RELATIVE),
            "selection_rule": "first non-held-out frozen Auto result routed hybrid",
        },
    }


def select_exact_entities(repository_root: Path, count: int = 3) -> list[dict[str, Any]]:
    queries = load_jsonl(repository_root / FORMAL_QUERY_RELATIVE)
    results = {
        row["query_id"]: row
        for row in load_jsonl(repository_root / FORMAL_RESULT_RELATIVE)
    }
    gold = {
        row["query_id"]: row
        for row in load_jsonl(repository_root / FORMAL_GOLD_RELATIVE)
    }
    selected: list[dict[str, Any]] = []
    for query in queries:
        if (
            query.get("held_out")
            or query.get("actual_query_type") != "exact_entity"
            or query["query_id"] not in results
            or query["query_id"] not in gold
        ):
            continue
        frozen = results[query["query_id"]]
        systems = frozen.get("systems", {})
        if "lexical" not in systems or "auto" not in systems:
            continue
        target_ids = gold[query["query_id"]].get(
            "video_discovery_relevant_video_ids", []
        )
        selected.append(
            {
                "query": query["query"],
                "source_artifact": str(FORMAL_QUERY_RELATIVE),
                "source_case_or_fixture_id": query["query_id"],
                "selection_rule": (
                    "first three locked non-held-out exact_entity queries by query_id "
                    "with frozen Auto and Lexical results"
                ),
                "expected_auto_branch": "lexical",
                "scope": query["scope"],
                "filters": query["filters"],
                "target_video_ids": target_ids,
                "gold_source_artifact": str(FORMAL_GOLD_RELATIVE),
                "existing_lexical_control_available": True,
                "existing_hybrid_control_available": "hybrid" in systems,
                "existing_lexical_result_count": len(
                    systems["lexical"].get("product_video_ids", [])
                ),
                "existing_lexical_target_hit": bool(
                    set(target_ids) & set(systems["lexical"].get("product_video_ids", []))
                ),
                "existing_hybrid_result_count": (
                    len(systems["hybrid"].get("product_video_ids", []))
                    if "hybrid" in systems
                    else None
                ),
                "existing_hybrid_target_hit": (
                    bool(
                        set(target_ids)
                        & set(systems["hybrid"].get("product_video_ids", []))
                    )
                    if "hybrid" in systems
                    else None
                ),
            }
        )
        if len(selected) == count:
            break
    if len(selected) != count:
        raise FrozenAutoSmokeBlocked(
            "exact_entity_selection_unavailable",
            "Three eligible frozen exact-entity regression queries are required",
            {"selected": len(selected)},
        )
    return selected


def build_auto_request(
    query: str,
    request_base: Mapping[str, Any] | None = None,
    *,
    scope: str = "all",
    filters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    base = dict(request_base or {})
    base.update(
        {
            "query": query,
            "mode": "auto",
            "scope": base.get("scope", scope),
            "result_limit": base.get("result_limit", 10),
            "max_windows_per_video": base.get("max_windows_per_video", 2),
            "filters": base.get("filters", dict(filters or {})),
        }
    )
    return base


def _execute_auto(
    service,
    provider: CountingEmbeddingProvider,
    request_payload: Mapping[str, Any],
    target_video_ids: Sequence[int],
) -> dict[str, Any]:
    before_calls = provider.query_call_count
    try:
        raw, product = service.product_search.search_with_raw(
            ProductSearchRequest.model_validate(request_payload)
        )
    except Exception as exc:
        return {
            "request": dict(request_payload),
            "runtime_error": True,
            "runtime_error_type": type(exc).__name__,
            "runtime_error_message": str(exc)[:500],
            "router": None,
            "payload": None,
            "score": {
                "target_video_hit": False,
                "target_video_best_rank": None,
                "result_count": 0,
                "empty_result": True,
            },
            "embedding_invoked": provider.query_call_count > before_calls,
            "latency_ms": 0.0,
        }
    plan = raw.plan.as_dict()
    results = [value.as_dict() for value in product.results]
    matched = [
        (rank, value)
        for rank, value in enumerate(results, 1)
        if int(value["video_id"]) in set(target_video_ids)
    ]
    return {
        "request": dict(request_payload),
        "runtime_error": False,
        "runtime_error_type": None,
        "runtime_error_message": None,
        "router": {
            "requested_mode": plan["requested_mode"],
            "auto_router_invoked": plan["requested_mode"] == "auto",
            "router_version": ROUTER_VERSION,
            "router_decision": plan["planned_mode"],
            "effective_mode": raw.executed_mode,
            "router_reason_codes": [plan["routing_reason"]],
            "query_type": plan["query_type"],
            "mode_consistent": plan["planned_mode"] == raw.executed_mode,
        },
        "payload": {
            "plan": plan,
            "trace_id": raw.trace_id,
            "trace_persisted": raw.trace_persisted,
            "presentation_trace_persisted": product.presentation_trace_persisted,
            "fallback": raw.fallback,
            "fallback_reason": raw.fallback_reason,
            "index_identity": raw.index_identity,
            "candidate_counts": raw.candidate_counts,
            "raw_hits": [value.as_dict() for value in raw.raw_hits],
            "results": results,
            "timing": {
                "raw": raw.timing.as_dict(),
                "product": product.timing.as_dict(),
            },
        },
        "score": {
            "target_video_hit": bool(matched),
            "target_video_best_rank": matched[0][0] if matched else None,
            "result_count": len(results),
            "empty_result": not results,
        },
        "embedding_invoked": provider.query_call_count > before_calls,
        "latency_ms": product.timing.total_ms,
    }


def _execution_cache_key(request: Mapping[str, Any]) -> str:
    return canonical_sha(request)


def _write_execution(
    directory: Path,
    execution: Mapping[str, Any],
    *,
    query_id: str,
    case_id: str | None,
    query_view: str,
    query: str,
    intent_index: int | None = None,
    intent_count: int | None = None,
    cache_hit: bool = False,
    exact_control: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    router = execution.get("router") or {}
    score = execution["score"]
    record = {
        "query_id": query_id,
        "case_id": case_id,
        "query_view": query_view,
        "query": query,
        "query_type": router.get("query_type"),
        "requested_mode": "auto",
        "auto_router_invoked": bool(router.get("auto_router_invoked")),
        "router_version": router.get("router_version", ROUTER_VERSION),
        "router_decision": router.get("router_decision"),
        "effective_mode": router.get("effective_mode"),
        "router_reason_codes": router.get("router_reason_codes", []),
        "router_mode_consistent": bool(router.get("mode_consistent")),
        "target_video_hit": score["target_video_hit"],
        "target_video_best_rank": score["target_video_best_rank"],
        "result_count": score["result_count"],
        "empty_result": score["empty_result"],
        "embedding_invoked": execution["embedding_invoked"],
        "embedding_provider": (
            QWEN_PROVIDER_VERSION if execution["embedding_invoked"] else None
        ),
        "embedding_model": QWEN_MODEL_ID if execution["embedding_invoked"] else None,
        "embedding_cache_hit": False,
        "exact_query_cache_hit": cache_hit,
        "latency_ms": execution["latency_ms"],
        "runtime_error": execution["runtime_error"],
        "runtime_error_type": execution["runtime_error_type"],
    }
    if intent_index is not None:
        record.update({"intent_index": intent_index, "intent_count": intent_count})
    if exact_control is not None:
        record.update(
            {
                "existing_lexical_result_count": exact_control[
                    "existing_lexical_result_count"
                ],
                "existing_lexical_target_hit": exact_control[
                    "existing_lexical_target_hit"
                ],
                "existing_hybrid_result_count": exact_control[
                    "existing_hybrid_result_count"
                ],
                "existing_hybrid_target_hit": exact_control[
                    "existing_hybrid_target_hit"
                ],
            }
        )
        record["auto_vs_lexical_regression"] = bool(
            record["existing_lexical_target_hit"]
            and (
                not record["target_video_hit"]
                or record["empty_result"]
                or record["effective_mode"] != "lexical"
            )
        )
    write_json(directory / "query_record.json", record)
    write_json(directory / "request.json", execution["request"])
    write_json(directory / "search_candidate_set.json", execution["payload"])
    write_json(
        directory / "runtime_usage.json",
        {
            "retrieval_call_count": 0 if cache_hit else 1,
            "exact_query_cache_hit": cache_hit,
            "embedding_query_call_count": int(
                execution["embedding_invoked"] and not cache_hit
            ),
            "embedding_cache_hits": 0,
            "external_calls": 0,
        },
    )
    return record


def q2_union(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    hits = [
        int(record["intent_index"])
        for record in records
        if record["target_video_hit"]
    ]
    ranks = {
        str(record["intent_index"]): record["target_video_best_rank"]
        for record in records
    }
    return {
        "merge_rule": "union_of_canonical_video_identities",
        "cross_intent_rerank": False,
        "score_merge": False,
        "candidate_builder_called": False,
        "selector_called": False,
        "target_video_hit": bool(hits),
        "target_video_best_rank": min(
            (rank for rank in ranks.values() if rank is not None), default=None
        ),
        "target_video_hit_intents": hits,
        "target_video_per_intent_ranks": ranks,
        "all_intents_empty": all(record["empty_result"] for record in records),
    }


def router_distribution(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(record.get("router_decision") or "other") for record in records)
    return {
        "lexical": counts["lexical"],
        "hybrid": counts["hybrid"],
        "dense": counts["dense"],
        "other": sum(
            value
            for key, value in counts.items()
            if key not in {"lexical", "hybrid", "dense"}
        ),
    }


def latency_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    values = sorted(
        float(record["latency_ms"])
        for record in records
        if not record["runtime_error"]
    )
    if not values:
        return {"count": 0, "median_ms": None, "p95_ms": None, "max_ms": None}
    p95_index = max(0, min(len(values) - 1, int(0.95 * len(values) + 0.999) - 1))
    return {
        "count": len(values),
        "median_ms": round(statistics.median(values), 3),
        "p95_ms": round(values[p95_index], 3),
        "max_ms": round(max(values), 3),
    }


def _recall(rows: Sequence[Mapping[str, Any]], view: str) -> dict[str, Any]:
    eligible = [row for row in rows if row["label_role"] == "evidence_bearing"]
    numerator = sum(bool(row[view]["target_video_hit"]) for row in eligible)
    return {
        "numerator": numerator,
        "denominator": 9,
        "rate": numerator / 9,
    }


def apply_release_gate(
    *,
    rows: Sequence[Mapping[str, Any]],
    all_records: Sequence[Mapping[str, Any]],
    exact_records: Sequence[Mapping[str, Any]],
    runtime_stable: bool,
    snapshot_stable: bool,
) -> dict[str, Any]:
    q0_recall = _recall(rows, "q0")
    runtime_failure = any(record["runtime_error"] for record in all_records)
    consistency = all(record["router_mode_consistent"] for record in all_records)
    invoked = all(record["auto_router_invoked"] for record in all_records)
    fallback = any(
        bool(record.get("fallback"))
        for record in all_records
    )
    exact_regression = any(
        bool(record.get("auto_vs_lexical_regression")) for record in exact_records
    )
    q1_recall = _recall(rows, "q1")
    q2_recall = _recall(rows, "q2")
    human_review_required = (
        q1_recall["numerator"] != 9 or q2_recall["numerator"] != 9
    )
    if runtime_failure or not runtime_stable or not snapshot_stable:
        return {
            "release_gate": "blocked",
            "failure_class": "runtime_or_environment_failure",
            "quality_conclusion_allowed": False,
            "authorized_fallback_recommendation": None,
            "human_review_required": False,
            "product_default_wiring_authorized": False,
        }
    passed = (
        invoked
        and consistency
        and q0_recall["numerator"] == 9
        and not fallback
        and not exact_regression
    )
    if passed:
        return {
            "release_gate": "passed",
            "failure_class": None,
            "quality_conclusion_allowed": True,
            "authorized_fallback_recommendation": None,
            "human_review_required": human_review_required,
            "product_default_wiring_authorized": not human_review_required,
        }
    router_gap = any(row["q0"]["router_miss"] for row in rows)
    return {
        "release_gate": "failed",
        "failure_class": (
            "frozen_auto_router_gap" if router_gap else "release_gate_condition_failed"
        ),
        "quality_conclusion_allowed": True,
        "authorized_fallback_recommendation": "hybrid" if router_gap else None,
        "router_change_authorized": False,
        "human_review_required": True,
        "product_default_wiring_authorized": False,
    }


def _report(
    *,
    input_audit: Mapping[str, Any],
    runtime: Mapping[str, Any],
    execution: Mapping[str, Any],
    recall: Mapping[str, Any],
    exact: Mapping[str, Any],
    insufficient: Mapping[str, Any],
    gate: Mapping[str, Any],
) -> str:
    return f"""# V3.5 Frozen Auto Smoke Validation Report

## Input

- Phase A case set: {input_audit['case_count']} cases, aligned: {input_audit['case_ids_match_phase_a']}
- Approved Q1/Q2: `{APPROVED_RELATIVE}`; SHA-256 `{input_audit['approved_query_sha256']}`
- Approved queries modified: {input_audit['queries_modified']}
- Exact-entity queries: {input_audit['exact_entity_count']}; frozen sources recorded in the selection manifest

## Runtime

- Auto Router: `{runtime['auto_router_version']}` via `{runtime['auto_router_entrypoint']}`
- Router invoked for all logical executions: {execution['auto_router_invoked_for_all_queries']}
- Router decision/effective mode consistent: {execution['router_mode_consistency']}
- Index/Snapshot identity: `{runtime['index_identity']}`
- Embedding: `{runtime['dense_provider']}` / `{runtime['embedding_model']}`
- RRF: `{runtime['hybrid_rrf_version']}`
- Retrieval configuration modified: {runtime['retrieval_configuration_modified']}
- Product default modified: {runtime['product_default_modified']}

## Execution

- Logical Q0/Q1/Q2: {execution['logical_q0_queries']}/{execution['logical_q1_queries']}/{execution['logical_q2_intents']}
- Preflight / formal new calls / total actual new calls: {execution['preflight_retrieval_calls']}/{execution['formal_new_retrieval_calls']}/{execution['actual_new_retrieval_calls']}
- Exact-query reuses: {execution['exact_query_reuses']}
- Router Q0: {execution['router_distribution']['q0']}
- Router Q1: {execution['router_distribution']['q1']}
- Router Q2: {execution['router_distribution']['q2']}
- Router Exact: {execution['router_distribution']['exact_entity']}
- Embedding calls: {execution['embedding_query_call_count']}
- Provider initialization/reuse: {execution['embedding_provider_initialization_count']}/{execution['embedding_provider_reuse_count']}
- Latency: {execution['latency']}
- Runtime errors / external calls: {execution['runtime_error_count']}/0
- Held-out accessed: false

## Recall

- Frozen Lexical Q0/Q1/Q2: 0/9, 0/9, 0/9
- Frozen Hybrid Q0/Q1/Q2: 9/9, 9/9, 9/9
- Auto Q0: {recall['auto']['q0']['numerator']}/9
- Auto Q1: {recall['auto']['q1']['numerator']}/9
- Auto Q2: {recall['auto']['q2']['numerator']}/9
- Router misses: {recall['router_miss_count']} ({recall['router_miss_case_ids']})

## Exact Entity

- Total: {exact['exact_entity_total']}
- Routed lexical/hybrid: {exact['auto_routed_to_lexical']}/{exact['auto_routed_to_hybrid']}
- Auto target hits / Lexical control target hits: {exact['auto_target_hits']}/{exact['lexical_control_target_hits']}
- Clear regressions / runtime failures: {exact['clear_regression_count']}/{exact['runtime_failure_count']}

## Insufficient Diagnostic

- Case: `{INSUFFICIENT_CASE_ID}`
- Auto Q0/Q1/Q2 hit: {insufficient['auto_q0_hit']}/{insufficient['auto_q1_hit']}/{insufficient['auto_q2_hit']}
- Excluded from main recall because its frozen role is `insufficient_diagnostic`; this only reports topic discovery.

## Release Gate

- Status: **{gate['release_gate']}**
- Failure class: {gate.get('failure_class')}
- Hybrid fallback recommendation: {gate.get('authorized_fallback_recommendation')}
- Router modified: false
- Human review required: {gate['human_review_required']}
- Product default may be changed now: {gate['product_default_wiring_authorized']}
- Current Codex session should close: true
"""


def _review_packet(
    recall: Mapping[str, Any],
    distributions: Mapping[str, Any],
    router_misses: Sequence[Mapping[str, Any]],
    exact: Mapping[str, Any],
    gate: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> str:
    exceptional = [
        record
        for record in records
        if record["runtime_error"]
        or not record["router_mode_consistent"]
        or record.get("auto_vs_lexical_regression")
        or record.get("router_miss")
    ]
    lines = [
        "# V3.5 Frozen Auto Smoke Human Review Packet",
        "",
        "## Summary",
        "",
        f"- Auto Q0/Q1/Q2 Recall: {recall['auto']['q0']['numerator']}/9, "
        f"{recall['auto']['q1']['numerator']}/9, "
        f"{recall['auto']['q2']['numerator']}/9",
        f"- Router distributions: {json.dumps(distributions, ensure_ascii=False)}",
        f"- Router misses: {len(router_misses)}",
        f"- Exact-entity regressions: {exact['clear_regression_count']}",
        f"- Release Gate: {gate['release_gate']}",
        "",
        "## Exceptional Queries",
        "",
    ]
    if not exceptional:
        lines.append("No exceptional query met the review-selection rules.")
    for record in exceptional:
        lines.extend(
            [
                f"### {record['query_id']}",
                "",
                f"- Query: {record['query']}",
                f"- Query view: {record['query_view']}",
                f"- Router decision / effective mode: "
                f"{record['router_decision']} / {record['effective_mode']}",
                f"- Auto hit / rank: {record['target_video_hit']} / "
                f"{record['target_video_best_rank']}",
                f"- Lexical control: {record.get('existing_lexical_target_hit')}",
                f"- Hybrid control: {record.get('existing_hybrid_target_hit')}",
                f"- Embedding invoked: {record['embedding_invoked']}",
                f"- Latency: {record['latency_ms']} ms",
                f"- Failure classification: "
                f"{record.get('failure_class') or record.get('runtime_error_type')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _file_manifest(root: Path, destination: Path) -> None:
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


def run_frozen_auto_smoke(
    *,
    repository_root: Path,
    snapshot_db: Path,
    snapshot_artifacts: Path,
    artifact_manifest: Path,
    provider: CountingEmbeddingProvider | None = None,
    runtime_config: FrozenEvalRuntimeConfig | None = None,
) -> dict[str, Any]:
    output = repository_root / OUTPUT_RELATIVE
    if runtime_config is None:
        raise FrozenAutoSmokeBlocked(
            "frozen_eval_runtime_guard_missing",
            "Frozen Eval runtime seal is required before any frozen input is loaded",
        )
    try:
        guard_result = preflight_frozen_eval_runtime(runtime_config)
    except FrozenEvalRuntimeGuardError as exc:
        raise FrozenAutoSmokeBlocked(exc.code, str(exc)) from exc
    if runtime_config.database.path != snapshot_db.expanduser().resolve():
        raise FrozenAutoSmokeBlocked(
            "snapshot_path_not_sealed",
            "The requested snapshot database is not the database named by the runtime seal",
        )
    frozen = load_frozen_inputs(repository_root)
    product_before = validate_product_defaults(repository_root)
    runtime = auto_runtime_identity(repository_root)
    if file_sha256(snapshot_db) != SNAPSHOT_SHA256:
        raise FrozenAutoSmokeBlocked(
            "snapshot_identity_mismatch", "Frozen snapshot SHA-256 mismatch"
        )
    if file_sha256(artifact_manifest) != ARTIFACT_MANIFEST_SHA256:
        raise FrozenAutoSmokeBlocked(
            "artifact_manifest_identity_mismatch",
            "Frozen artifact manifest SHA-256 mismatch",
        )
    index = inspect_index(snapshot_db)
    phase_br_index = json.loads(
        (
            repository_root
            / "research/v3_5/stage3r_qc/phase_b_r/runtime_preflight/index_identity.json"
        ).read_text(encoding="utf-8")
    )
    if {
        key: index[key]
        for key in (
            "index_sha256_or_manifest_identity",
            "dense_index_version",
            "embedding_model",
            "embedding_provider",
            "projection_version",
        )
    } != {
        key: phase_br_index[key]
        for key in (
            "index_sha256_or_manifest_identity",
            "dense_index_version",
            "embedding_model",
            "embedding_provider",
            "projection_version",
        )
    }:
        raise FrozenAutoSmokeBlocked(
            "phase_b_r_runtime_identity_mismatch",
            "Runtime or index identity differs from frozen Phase B-R",
        )
    verify_qwen_snapshot(QWEN_MODEL_PATH)
    counter = provider or CountingEmbeddingProvider()
    if asdict(counter.model_identity())["provider_version"] != QWEN_PROVIDER_VERSION:
        raise FrozenAutoSmokeBlocked(
            "embedding_provider_identity_mismatch",
            "Dense provider identity differs from frozen runtime",
        )
    runtime_before = runtime_file_hashes(repository_root)
    snapshot_before = file_sha256(snapshot_db)
    known_positives = select_known_positive_queries(repository_root)
    exact_selection = select_exact_entities(repository_root)

    input_audit = {
        "case_count": 10,
        "evidence_bearing_count": 9,
        "insufficient_diagnostic_count": 1,
        "case_ids_match_phase_a": True,
        "approved_query_path": str(APPROVED_RELATIVE),
        "approved_query_sha256": frozen["approved_query_sha256"],
        "approved_query_sha256_match": True,
        "q1_modified": False,
        "q2_modified": False,
        "queries_modified": False,
        "exact_entity_count": len(exact_selection),
    }
    write_json(output / "input_freeze/frozen_input_validation.json", input_audit)
    write_json(
        output / "input_freeze/query_hashes.json",
        {
            row["case_id"]: {
                "q0": sha256(
                    frozen["cases"][row["case_id"]]["original_query"].encode()
                ).hexdigest(),
                "q1": sha256(row["q1_discovery_query"].encode()).hexdigest(),
                "q2": [
                    sha256(query.encode()).hexdigest()
                    for query in row["q2_retrieval_intents"]
                ],
            }
            for row in frozen["decisions"]
        },
    )
    write_json(
        output / "exact_entity_selection/exact_entity_selection_manifest.json",
        {
            "frozen_before_auto_execution": True,
            "selection_count": len(exact_selection),
            "held_out_accessed": False,
            "new_gold_created": False,
            "queries": exact_selection,
        },
    )
    write_json(
        output / "runtime_preflight/auto_runtime_identity.json",
        {
            **runtime,
            "index_identity": SNAPSHOT_SHA256,
            "frozen_eval_runtime_guard": guard_result,
        },
    )
    write_json(output / "runtime_preflight/index_identity.json", index)
    write_json(
        output / "runtime_preflight/product_default.before.json", product_before
    )
    write_json(
        output / "runtime_preflight/known_positive_selection.json",
        known_positives,
    )
    write_jsonl(
        output / "runtime_preflight/runtime_file_hashes.before.jsonl",
        runtime_before,
    )

    cache: dict[str, dict[str, Any]] = {}
    new_calls = 0
    cache_hits = 0
    all_records: list[dict[str, Any]] = []
    q0_records: list[dict[str, Any]] = []
    q1_records: list[dict[str, Any]] = []
    q2_records: list[dict[str, Any]] = []
    exact_records: list[dict[str, Any]] = []
    case_rows: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="shiliu-frozen-auto-smoke-") as temporary:
        work_db = Path(temporary) / "snapshot-work-copy.db"
        shutil.copy2(snapshot_db, work_db)
        service = build_search_service(
            work_db=work_db,
            snapshot_artifacts=snapshot_artifacts,
            artifact_manifest=artifact_manifest,
            provider=counter,
        )

        known_results: dict[str, Any] = {}
        loads_initial = counter.load_count
        for branch in ("lexical", "hybrid"):
            selection = known_positives[branch]
            request = build_auto_request(
                selection["query"],
                scope=selection["scope"],
                filters=selection["filters"],
            )
            execution = _execute_auto(service, counter, request, ())
            router = execution.get("router") or {}
            known_results[branch] = {
                **selection,
                "auto_router_invoked": bool(router.get("auto_router_invoked")),
                "router_decision": router.get("router_decision"),
                "effective_mode": router.get("effective_mode"),
                "mode_consistent": router.get("mode_consistent"),
                "result_count": execution["score"]["result_count"],
                "runtime_error": execution["runtime_error"],
                "runtime_error_type": execution["runtime_error_type"],
                "runtime_error_message": execution["runtime_error_message"],
                "embedding_invoked": execution["embedding_invoked"],
                "provider_load_count_after": counter.load_count,
            }
        known_results["embedding_lazy_load_observed"] = (
            loads_initial == 0
            and known_results["lexical"]["provider_load_count_after"] == 0
            and known_results["hybrid"]["provider_load_count_after"] == 1
        )
        if any(
            not known_results[branch]["auto_router_invoked"]
            or not known_results[branch]["mode_consistent"]
            or known_results[branch]["effective_mode"] != branch
            or known_results[branch]["result_count"] == 0
            or known_results[branch]["runtime_error"]
            for branch in ("lexical", "hybrid")
        ):
            raise FrozenAutoSmokeBlocked(
                "known_positive_auto_preflight_failed",
                "Known-positive Auto preflight failed",
                known_results,
            )
        write_json(
            output / "runtime_preflight/known_positive_smoke.audit.json",
            known_results,
        )

        def execute_cached(
            request: Mapping[str, Any], target_video_ids: Sequence[int]
        ) -> tuple[dict[str, Any], bool]:
            nonlocal new_calls, cache_hits
            key = _execution_cache_key(request)
            cached = key in cache
            if cached:
                base = cache[key]
                execution = {
                    **base,
                    "score": {
                        "target_video_hit": any(
                            int(row["video_id"]) in set(target_video_ids)
                            for row in base["payload"]["results"]
                        ),
                        "target_video_best_rank": next(
                            (
                                rank
                                for rank, row in enumerate(
                                    base["payload"]["results"], 1
                                )
                                if int(row["video_id"]) in set(target_video_ids)
                            ),
                            None,
                        ),
                        "result_count": len(base["payload"]["results"]),
                        "empty_result": not base["payload"]["results"],
                    },
                    "embedding_invoked": False,
                    "latency_ms": 0.0,
                }
                cache_hits += 1
            else:
                execution = _execute_auto(service, counter, request, target_video_ids)
                cache[key] = execution
                new_calls += 1
            return execution, cached

        for decision in frozen["decisions"]:
            case_id = decision["case_id"]
            case = frozen["cases"][case_id]
            control = frozen["controls"][case_id]
            target_id = int(
                frozen["identities"][case_id][
                    "runtime_canonical_video_identity"
                ]["product_video_id"]
            )
            request_base = frozen["runtimes"][case_id]["track_a"]["search_request"]
            label_role = (
                "insufficient_diagnostic"
                if case_id == INSUFFICIENT_CASE_ID
                else "evidence_bearing"
            )
            views: dict[str, Any] = {}
            for view, query in (
                ("q0", case["original_query"]),
                ("q1", decision["q1_discovery_query"]),
            ):
                request = build_auto_request(query, request_base)
                execution, cached = execute_cached(request, (target_id,))
                record = _write_execution(
                    output / f"execution/qc_cases/{view}/{case_id}",
                    execution,
                    query_id=f"{case_id}:{view}",
                    case_id=case_id,
                    query_view=view,
                    query=query,
                    cache_hit=cached,
                )
                control_view = control["hybrid"][view]
                lexical_view = control["lexical"][view]
                record.update(
                    {
                        "existing_lexical_target_hit": bool(
                            lexical_view["target_video_hit"]
                        ),
                        "existing_hybrid_target_hit": bool(
                            control_view["target_video_hit"]
                        ),
                    }
                )
                record["auto_matches_hybrid"] = (
                    record["target_video_hit"]
                    == record["existing_hybrid_target_hit"]
                )
                record["auto_regresses_vs_hybrid"] = bool(
                    record["existing_hybrid_target_hit"]
                    and not record["target_video_hit"]
                )
                record["auto_improves_vs_lexical"] = bool(
                    record["target_video_hit"]
                    and not record["existing_lexical_target_hit"]
                )
                record["router_miss"] = bool(
                    record["existing_hybrid_target_hit"]
                    and record["router_decision"] != "hybrid"
                    and not record["target_video_hit"]
                )
                record["fallback"] = bool(
                    (execution.get("payload") or {}).get("fallback")
                )
                records = q0_records if view == "q0" else q1_records
                records.append(record)
                all_records.append(record)
                views[view] = record

            intent_records: list[dict[str, Any]] = []
            for index_value, query in enumerate(
                decision["q2_retrieval_intents"], 1
            ):
                request = build_auto_request(query, request_base)
                execution, cached = execute_cached(request, (target_id,))
                record = _write_execution(
                    output
                    / f"execution/qc_cases/q2/{case_id}/intent_{index_value:02d}",
                    execution,
                    query_id=f"{case_id}:q2:{index_value:02d}",
                    case_id=case_id,
                    query_view="q2",
                    query=query,
                    intent_index=index_value,
                    intent_count=len(decision["q2_retrieval_intents"]),
                    cache_hit=cached,
                )
                hybrid_intent = control["hybrid"]["q2"]["intent_results"][
                    index_value - 1
                ]
                lexical_intents = control["lexical"]["q2"]["intent_results"]
                lexical_intent = lexical_intents[index_value - 1]
                record.update(
                    {
                        "existing_lexical_target_hit": bool(
                            lexical_intent.get("target_video_hit", False)
                        ),
                        "existing_hybrid_target_hit": bool(
                            hybrid_intent["target_video_hit"]
                        ),
                    }
                )
                record["auto_matches_hybrid"] = (
                    record["target_video_hit"]
                    == record["existing_hybrid_target_hit"]
                )
                record["auto_regresses_vs_hybrid"] = bool(
                    record["existing_hybrid_target_hit"]
                    and not record["target_video_hit"]
                )
                record["auto_improves_vs_lexical"] = bool(
                    record["target_video_hit"]
                    and not record["existing_lexical_target_hit"]
                )
                record["router_miss"] = bool(
                    record["existing_hybrid_target_hit"]
                    and record["router_decision"] != "hybrid"
                    and not record["target_video_hit"]
                )
                record["fallback"] = bool(
                    (execution.get("payload") or {}).get("fallback")
                )
                intent_records.append(record)
                q2_records.append(record)
                all_records.append(record)
            q2 = q2_union(intent_records)
            q2.update(
                {
                    "auto_matches_hybrid": (
                        q2["target_video_hit"]
                        == bool(control["hybrid"]["q2"]["target_video_hit"])
                    ),
                    "auto_regresses_vs_hybrid": bool(
                        control["hybrid"]["q2"]["target_video_hit"]
                        and not q2["target_video_hit"]
                    ),
                    "auto_improves_vs_lexical": bool(
                        q2["target_video_hit"]
                        and not control["lexical"]["q2"]["target_video_hit"]
                    ),
                }
            )
            write_json(
                output / f"execution/qc_cases/q2/{case_id}/q2_union.json", q2
            )
            case_rows.append(
                {
                    "case_id": case_id,
                    "label_role": label_role,
                    "identity_failure": False,
                    "q0": views["q0"],
                    "q1": views["q1"],
                    "q2": {
                        **q2,
                        "router_decisions": [
                            record["router_decision"] for record in intent_records
                        ],
                        "effective_modes": [
                            record["effective_mode"] for record in intent_records
                        ],
                    },
                    "frozen_lexical": {
                        "q0": control["lexical"]["q0"]["target_video_hit"],
                        "q1": control["lexical"]["q1"]["target_video_hit"],
                        "q2": control["lexical"]["q2"]["target_video_hit"],
                    },
                    "frozen_hybrid": {
                        "q0": control["hybrid"]["q0"]["target_video_hit"],
                        "q1": control["hybrid"]["q1"]["target_video_hit"],
                        "q2": control["hybrid"]["q2"]["target_video_hit"],
                    },
                }
            )

        for selection in exact_selection:
            query_id = selection["source_case_or_fixture_id"]
            request = build_auto_request(
                selection["query"],
                scope=selection["scope"],
                filters=selection["filters"],
            )
            execution, cached = execute_cached(
                request, selection["target_video_ids"]
            )
            record = _write_execution(
                output / f"execution/exact_entity/{query_id}",
                execution,
                query_id=query_id,
                case_id=None,
                query_view="exact_entity",
                query=selection["query"],
                cache_hit=cached,
                exact_control=selection,
            )
            record["fallback"] = bool(
                (execution.get("payload") or {}).get("fallback")
            )
            exact_records.append(record)
            all_records.append(record)

    runtime_after = runtime_file_hashes(repository_root)
    snapshot_stable = file_sha256(snapshot_db) == snapshot_before
    runtime_stable = runtime_after == runtime_before
    product_after = validate_product_defaults(repository_root)
    product_stable = product_after == product_before
    if not product_stable:
        raise FrozenAutoSmokeBlocked(
            "product_default_modified_during_smoke",
            "Product default changed during frozen Auto smoke",
        )
    write_jsonl(
        output / "runtime_preflight/runtime_file_hashes.after.jsonl",
        runtime_after,
    )
    write_json(
        output / "runtime_preflight/runtime_integrity.audit.json",
        {
            "runtime_hashes_stable": runtime_stable,
            "snapshot_hash_stable": snapshot_stable,
            "product_defaults_stable": product_stable,
            "router_modified": False,
            "retrieval_configuration_modified": False,
            "index_rebuilt": False,
        },
    )
    write_json(
        output / "runtime_preflight/product_default.after.json", product_after
    )

    write_jsonl(output / "scoring/case_results.auto.jsonl", case_rows)
    recall = {
        "lexical": {"q0": "0/9", "q1": "0/9", "q2": "0/9"},
        "hybrid": {"q0": "9/9", "q1": "9/9", "q2": "9/9"},
        "auto": {
            "q0": _recall(case_rows, "q0"),
            "q1": _recall(case_rows, "q1"),
            "q2": _recall(case_rows, "q2"),
        },
    }
    router_misses = [
        {
            "case_id": record["case_id"],
            "query_id": record["query_id"],
            "query": record["query"],
            "query_view": record["query_view"],
            "router_decision": record["router_decision"],
            "effective_mode": record["effective_mode"],
        }
        for record in [*q0_records, *q1_records, *q2_records]
        if record["router_miss"]
    ]
    recall.update(
        {
            "router_miss_count": len(router_misses),
            "router_miss_case_ids": sorted(
                {row["case_id"] for row in router_misses}
            ),
            "router_miss_queries": router_misses,
        }
    )
    distributions = {
        "q0": router_distribution(q0_records),
        "q1": router_distribution(q1_records),
        "q2": router_distribution(q2_records),
        "exact_entity": router_distribution(exact_records),
    }
    exact = {
        "exact_entity_total": len(exact_records),
        "auto_routed_to_lexical": sum(
            record["router_decision"] == "lexical" for record in exact_records
        ),
        "auto_routed_to_hybrid": sum(
            record["router_decision"] == "hybrid" for record in exact_records
        ),
        "auto_target_hits": sum(
            record["target_video_hit"] for record in exact_records
        ),
        "lexical_control_target_hits": sum(
            record["existing_lexical_target_hit"] for record in exact_records
        ),
        "clear_regression_count": sum(
            record["auto_vs_lexical_regression"] for record in exact_records
        ),
        "runtime_failure_count": sum(
            record["runtime_error"] for record in exact_records
        ),
        "empty_result_regression_count": sum(
            record["empty_result"] and record["existing_lexical_result_count"] > 0
            for record in exact_records
        ),
    }
    insufficient_row = next(
        row for row in case_rows if row["case_id"] == INSUFFICIENT_CASE_ID
    )
    insufficient = {
        "case_id": INSUFFICIENT_CASE_ID,
        "auto_q0_hit": insufficient_row["q0"]["target_video_hit"],
        "auto_q1_hit": insufficient_row["q1"]["target_video_hit"],
        "auto_q2_hit": insufficient_row["q2"]["target_video_hit"],
        "router_decisions": {
            "q0": insufficient_row["q0"]["router_decision"],
            "q1": insufficient_row["q1"]["router_decision"],
            "q2": insufficient_row["q2"]["router_decisions"],
        },
        "effective_modes": {
            "q0": insufficient_row["q0"]["effective_mode"],
            "q1": insufficient_row["q1"]["effective_mode"],
            "q2": insufficient_row["q2"]["effective_modes"],
        },
        "excluded_from_main_recall": True,
        "interpretation_scope": "topic_relevant_target_video_discovery_only",
    }
    latency = {
        "q0": latency_summary(q0_records),
        "q1": latency_summary(q1_records),
        "q2": latency_summary(q2_records),
        "exact_entity": latency_summary(exact_records),
        "lexical_routed": latency_summary(
            [
                record
                for record in all_records
                if record["effective_mode"] == "lexical"
            ]
        ),
        "hybrid_routed": latency_summary(
            [
                record
                for record in all_records
                if record["effective_mode"] == "hybrid"
            ]
        ),
    }
    gate = apply_release_gate(
        rows=case_rows,
        all_records=all_records,
        exact_records=exact_records,
        runtime_stable=runtime_stable,
        snapshot_stable=snapshot_stable,
    )
    execution = {
        "logical_q0_queries": len(q0_records),
        "logical_q1_queries": len(q1_records),
        "logical_q2_intents": len(q2_records),
        "logical_exact_entity_queries": len(exact_records),
        "preflight_retrieval_calls": 2,
        "formal_new_retrieval_calls": new_calls,
        "actual_new_retrieval_calls": new_calls + 2,
        "new_retrieval_calls": new_calls,
        "exact_query_reuses": cache_hits,
        "auto_router_invoked_for_all_queries": all(
            record["auto_router_invoked"] for record in all_records
        ),
        "router_mode_consistency": all(
            record["router_mode_consistent"] for record in all_records
        ),
        "router_distribution": distributions,
        "embedding_lazy_load_observed": known_results[
            "embedding_lazy_load_observed"
        ],
        "embedding_provider_initialization_count": counter.load_count,
        "embedding_provider_reuse_count": max(
            0, counter.query_call_count - counter.load_count
        ),
        "embedding_query_call_count": counter.query_call_count,
        "embedding_cache_hits": 0,
        "latency": latency,
        "runtime_error_count": sum(
            record["runtime_error"] for record in all_records
        ),
        "external_calls": 0,
        "heldout_accessed": False,
    }
    runtime_report = {
        **runtime,
        "index_identity": index["index_sha256_or_manifest_identity"],
        "snapshot_identity": SNAPSHOT_ID,
        "product_default_modified": False,
        "runtime_hashes_stable": runtime_stable,
        "snapshot_hash_stable": snapshot_stable,
    }
    write_json(output / "analysis/router_distribution.json", distributions)
    write_json(output / "analysis/recall_and_controls.json", recall)
    write_json(
        output / "analysis/router_misses.json",
        {
            "router_miss_count": len(router_misses),
            "router_miss_case_ids": recall["router_miss_case_ids"],
            "router_miss_queries": router_misses,
        },
    )
    write_json(output / "analysis/latency.json", latency)
    write_json(output / "analysis/exact_entity_regression.json", exact)
    write_json(output / "analysis/insufficient_diagnostic.json", insufficient)
    write_json(output / "analysis/release_gate.json", gate)
    write_json(
        output / "isolation/heldout_access.audit.json",
        {
            "heldout_accessed": False,
            "external_llm_calls": 0,
            "external_embedding_calls": 0,
            "external_network_calls": 0,
            "candidate_builder_calls": 0,
            "selector_calls": 0,
            "index_rebuild_calls": 0,
            "product_query_set_started": False,
        },
    )
    write_json(
        output / "tests/contract_summary.json",
        {
            "phase_a_case_set_reused": True,
            "approved_q1_q2_reused": True,
            "approved_query_hash_validated": True,
            "queries_modified": False,
            "phase_b_r_controls_reused": True,
            "frozen_controls_rerun": False,
            "canonical_video_identity_used": True,
            "exact_selection_frozen_before_execution": True,
            "new_gold_created": False,
            "router_modified": False,
            "retrieval_config_modified": False,
            "index_rebuilt": False,
            "product_default_changed": False,
            "candidate_builder_called": False,
            "selector_called": False,
            "heldout_accessed": False,
            "external_llm_calls": 0,
        },
    )
    report_path = output / "V3_5_FROZEN_AUTO_SMOKE_VALIDATION_REPORT.md"
    report_path.write_text(
        _report(
            input_audit=input_audit,
            runtime=runtime_report,
            execution=execution,
            recall=recall,
            exact=exact,
            insufficient=insufficient,
            gate=gate,
        ),
        encoding="utf-8",
    )
    review_path = output / "V3_5_FROZEN_AUTO_SMOKE_HUMAN_REVIEW_PACKET.md"
    review_path.write_text(
        _review_packet(
            recall,
            distributions,
            router_misses,
            exact,
            gate,
            all_records,
        ),
        encoding="utf-8",
    )
    write_json(
        output / "review/review_selection.json",
        {
            "exceptional_query_count": sum(
                record["runtime_error"]
                or not record["router_mode_consistent"]
                or record.get("auto_vs_lexical_regression", False)
                or record.get("router_miss", False)
                for record in all_records
            ),
            "full_gold_transcript_included": False,
            "packet": str(review_path.relative_to(repository_root)),
        },
    )
    execution_audit = {
        "stage": "V3.5 Frozen Auto Smoke Validation",
        "status": "complete",
        "runner_version": RUNNER_VERSION,
        "recorded_at": utc_now(),
        "frozen_inputs_verified": True,
        "auto_router_invoked": execution["auto_router_invoked_for_all_queries"],
        "router_decisions_audited": True,
        "auto_q0_q1_q2_completed": True,
        "exact_entity_regression_completed": True,
        "router_modified": False,
        "retrieval_configuration_modified": False,
        "product_default_modified": False,
        "release_gate": gate["release_gate"],
        "failure_class": gate.get("failure_class"),
        "authorized_fallback_recommendation": gate.get(
            "authorized_fallback_recommendation"
        ),
        "human_review_required": gate["human_review_required"],
        "product_default_wiring_authorized": gate[
            "product_default_wiring_authorized"
        ],
        "session_may_close": True,
    }
    write_json(output / "frozen_auto_smoke_execution.audit.json", execution_audit)
    write_json(output / "frozen_auto_smoke_runtime_usage.json", execution)
    manifest = {
        "stage": "V3.5 Frozen Auto Smoke Validation",
        "status": "complete",
        "runner_version": RUNNER_VERSION,
        "case_count": 10,
        "evidence_bearing_case_count": 9,
        "exact_entity_count": len(exact_records),
        "release_gate": gate["release_gate"],
        "human_review_required": gate["human_review_required"],
        "product_default_wiring_authorized": gate[
            "product_default_wiring_authorized"
        ],
        "report": str(report_path.relative_to(repository_root)),
        "human_review_packet": str(review_path.relative_to(repository_root)),
    }
    write_json(output / "frozen_auto_smoke_manifest.json", manifest)
    _file_manifest(
        output, output / "frozen_auto_smoke_file_hash_manifest.jsonl"
    )
    return {
        **execution_audit,
        "recall": recall,
        "router_distribution": distributions,
        "router_miss_count": len(router_misses),
        "exact_entity": exact,
        "runtime": runtime_report,
        "report_path": str(report_path),
        "review_packet_path": str(review_path),
    }


def write_blocked_attempt(
    repository_root: Path, error: FrozenAutoSmokeBlocked
) -> dict[str, Any]:
    output = repository_root / OUTPUT_RELATIVE
    audit = {
        "stage": "V3.5 Frozen Auto Smoke Validation",
        "status": "blocked",
        "message": "Frozen Auto Smoke Blocked",
        "failure_class": "runtime_or_environment_failure",
        "reason_code": error.code,
        "details": error.details,
        "quality_conclusion_allowed": False,
        "router_modified": False,
        "retrieval_configuration_modified": False,
        "product_default_modified": False,
        "session_may_close": True,
    }
    write_json(output / "frozen_auto_smoke_execution.audit.json", audit)
    return audit
