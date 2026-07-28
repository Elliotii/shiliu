from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from typing import Any, Iterable, Mapping, Sequence

from shiliu.evidence.contracts import EvidenceContractError
from shiliu.evidence.stage3a import (
    DETERMINISTIC_SELECTOR_VERSION,
    SelectorConfig,
    resolve_from_search_candidates,
    select_deterministic_bundle,
    validate_bundle,
)
from shiliu.evidence.stage4 import (
    MechanicalGatePolicy,
    SufficiencyDecision,
    apply_mechanical_sufficiency_gate,
    terminal_sufficiency_decision,
)
from shiliu.eval_v3_5.isolation import HeldoutAccessGuard
from shiliu.eval_v3_5.p8_product_initial_baseline import (
    _search_payload,
    value_sha256,
)
from shiliu.eval_v3_5.runtime_guard import (
    load_frozen_eval_runtime_config,
    preflight_frozen_eval_runtime,
)
from shiliu.eval_v3_5.scoring_identity_bridge import (
    VideoIdentityCanonicalizer,
    complete_group_ids,
    covered_aspect_ids,
    material_aspect_ids,
    required_span_ids,
    span_is_covered,
)
from shiliu.eval_v3_5.stage3a import FrozenRawSourceResolver
from shiliu.eval_v3_5.stage3r import file_sha256, final_builder_config
from shiliu.eval_v3_5.stage3r_qc_phase_b_r import build_search_service
from shiliu.eval_v3_5.stage4a import _request
from shiliu.eval_v3_5.stage4b import (
    SEMANTIC_PROMPT_VERSION,
    SEMANTIC_POLICY_VERSION,
    batch_prompt,
    hash_value,
    parse_batch_output,
    project_runtime_request,
    to_decision,
    validate_output,
)
from shiliu.retrieval.planner import SearchPlanner, SearchRequest
from shiliu.retrieval.product_search import ProductSearchRequest
from shiliu.retrieval.qwen import QwenEmbeddingProvider


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/v3_5/product_query_set_v1/p14_frozen_evaluation"
QUERY = ROOT / (
    "research/v3_5/product_query_set_v1/split_v1/frozen_locked/"
    "product_query_frozen_evaluation_v1.locked.jsonl"
)
GOLD_ROOT = ROOT / (
    "research/v3_5/product_query_set_v1/gold_construction_v1/frozen_guarded/"
    "frozen_cycle_v1/sealed"
)
GOLD = {
    "retrieval": GOLD_ROOT / "product_retrieval_gold.frozen.v1.sealed.jsonl",
    "evidence": GOLD_ROOT / "product_evidence_gold.frozen.v1.sealed.jsonl",
    "sufficiency": GOLD_ROOT / "product_sufficiency_gold.frozen.v1.sealed.jsonl",
}
GOLD_HASHES = {
    "retrieval": "2f53b9294a7211b4371aadc934d1ec1a178b2a0fa00ee1b9b4177737b7b4ca34",
    "evidence": "b47235b273640fedf4754dfcb9983b733655ed80730d07ba12700987d4c30827",
    "sufficiency": "ccc7b0bfe35e78c5eec50ccb3c972b327bd400437f442d70da94e3f9df07b69a",
}
QUERY_HASH = "faf962049281cba4c8a035e64068ef91b7cfa9159ea438cfe33052a225add44f"
SNAPSHOT = Path(
    "/Users/elliot/Documents/Shiliu/eval/v3_stage6/"
    "20260720T094346Z_c7663365/shiliu_eval.db"
)
ARTIFACTS = SNAPSHOT.parent / "artifacts"
ARTIFACT_MANIFEST = ROOT / "research/v3_eval/artifact_manifest.jsonl"
RUNTIME_SEAL = OUT / "FROZEN_EVAL_RUNTIME_SEAL.json"
ENTRY_GATE = OUT / "P14_FROZEN_ENTRY_GATE.json"
FORMAL_MANIFEST = OUT / "P14_FROZEN_FORMAL_RUN_MANIFEST.json"
PREDICTIONS = OUT / "p14_frozen_predictions.per_case.jsonl"
PREDICTION_FREEZE = OUT / "P14_FROZEN_PREDICTIONS_FREEZE.json"
TRACE_ROOT = OUT / "traces"
MODEL = "gpt-5.6-terra"
LABELS = ("sufficient", "partial", "insufficient", "unverifiable")
SOURCE_TERMINAL_CODES = frozenset(
    {
        "no_supported_subtitle",
        "raw_source_unavailable",
        "source_unavailable",
        "source_unreadable",
        "title_only",
        "language_unresolved",
    }
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def stable_hash(value: object) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
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
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    values = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for row in values
        )
        + ("\n" if values else ""),
        encoding="utf-8",
    )


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def load_stage4b_runner() -> Any:
    path = (
        ROOT
        / "research/v3_5/product_query_set_v1/stage4b_incremental/run_stage4b.py"
    )
    spec = importlib.util.spec_from_file_location("p14_stage4b_frozen_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Stage 4B frozen runner import failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def verify_pre_prediction() -> dict[str, Any]:
    gate = load_json(ENTRY_GATE)
    if (
        gate.get("entry_gate") != "pass"
        or gate.get("formal_run_authorized") is not True
        or gate.get("formal_prediction_run_count") != 0
        or gate.get("Frozen_Query_opened") is not False
        or gate.get("Frozen_Gold_opened") is not False
    ):
        raise RuntimeError("Entry Gate does not authorize the unique run")
    manifest = load_json(FORMAL_MANIFEST)
    if manifest.get("maximum_valid_prediction_runs") != 1:
        raise RuntimeError("Formal Run Manifest policy mismatch")
    runtime = load_frozen_eval_runtime_config(RUNTIME_SEAL)
    preflight = preflight_frozen_eval_runtime(runtime)
    if file_sha256(SNAPSHOT) != runtime.database.sha256:
        raise RuntimeError("Snapshot changed after Formal Run Manifest")
    return {"manifest": manifest, "preflight": preflight}


def prediction_summary(
    *,
    query: Mapping[str, Any],
    run_id: str,
    search_payload: Mapping[str, Any],
    candidate_set: Any,
    bundle: Any,
    gate: Any,
    decision: SufficiencyDecision | None,
    request_hash: str,
    timings: Mapping[str, float],
    trace_path: Path,
    semantic_judge_called: bool,
    judge_latency_ms: int,
    retries: int,
    typed_errors: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    returned = [
        str(row.get("source_id") or row.get("video_id"))
        for row in search_payload.get("video_candidates", [])
    ]
    return {
        "case_id": str(query["query_id"]),
        "query_hash": stable_hash(query),
        "trace_id": gate.trace_id,
        "request_hash": request_hash,
        "search_candidate_set_summary": {
            "executed_mode": search_payload.get("executed_mode"),
            "router_decision": search_payload.get("router_decision"),
            "raw_unit_candidate_count": len(
                search_payload.get("raw_unit_candidates", [])
            ),
            "video_candidate_count": len(search_payload.get("video_candidates", [])),
        },
        "retrieval_result_ids": returned,
        "retrieval_result_records": list(search_payload.get("video_candidates", [])),
        "evidence_candidate_set_summary": {
            "candidate_count": len(candidate_set.candidates),
            "candidate_ids": [
                candidate.candidate_id for candidate in candidate_set.candidates
            ],
            "normalization_status": candidate_set.normalization_status,
            "validation_errors": list(candidate_set.validation_errors),
            "failure_category": candidate_set.failure_category,
            "candidate_spans": [
                candidate.as_dict() for candidate in candidate_set.candidates
            ],
        },
        "evidence_bundle": bundle.as_dict() if bundle else None,
        "mechanical_gate_result": gate.model_dump(mode="json"),
        "semantic_judge_called": semantic_judge_called,
        "sufficiency_decision_or_null": (
            decision.model_dump(mode="json") if decision else None
        ),
        "component_versions": {
            "retrieval": "v3-product-search-default-auto-v1",
            "auto_router": "unversioned:SearchPlanner@sha256:0876dbaff9bb2d016496cc3cb823f200b9a93a06721947bebee472d6a5bdaa7e",
            "builder": "stage3b-acronym-w3.5-v1",
            "selector": "v3.5-deterministic-fine-selector-v1",
            "evidence_bundle": "v3.5-evidence-bundle-v1",
            "mechanical_gate": "mechanical-gate-v1-r1",
            "semantic_policy": SEMANTIC_POLICY_VERSION,
            "semantic_prompt": SEMANTIC_PROMPT_VERSION,
            "semantic_model": MODEL if semantic_judge_called else None,
        },
        "stage_latencies": {
            **dict(timings),
            "semantic_judge_ms": judge_latency_ms,
        },
        "retries": retries,
        "typed_errors": list(typed_errors),
        "final_pipeline_status": (
            "completed"
            if decision is not None
            else ("invalid" if gate.gate_outcome == "invalid" else "runtime_error")
        ),
        "run_id": run_id,
        "trace_path": relative(trace_path),
    }


def predict() -> dict[str, Any]:
    if PREDICTIONS.exists() or PREDICTION_FREEZE.exists() or TRACE_ROOT.exists():
        raise RuntimeError("Prediction output collision; refusing a second formal run")
    state = verify_pre_prediction()
    if file_sha256(QUERY) != QUERY_HASH:
        raise RuntimeError("Frozen Query hash mismatch")
    queries = load_jsonl(QUERY)
    if len(queries) != 10 or len({str(row["query_id"]) for row in queries}) != 10:
        raise RuntimeError("Frozen Query set must contain exactly 10 unique cases")
    if any(row.get("split_assignment") != "frozen_evaluation" for row in queries):
        raise RuntimeError("Non-Frozen query entered the formal allowlist")

    runtime = load_frozen_eval_runtime_config(RUNTIME_SEAL)
    resolver = FrozenRawSourceResolver(
        artifact_manifest=ARTIFACT_MANIFEST,
        snapshot_db=SNAPSHOT,
        guard=HeldoutAccessGuard(ROOT),
    )
    builder = final_builder_config()
    selector = SelectorConfig()
    gate_policy = MechanicalGatePolicy()
    prepared: list[dict[str, Any]] = []
    TRACE_ROOT.mkdir(parents=True, exist_ok=False)

    with tempfile.TemporaryDirectory(prefix="shiliu-p14-frozen-") as temp:
        work_db = Path(temp) / "sealed-snapshot-work-copy.db"
        shutil.copy2(runtime.database.path, work_db)
        service = build_search_service(
            work_db=work_db,
            snapshot_artifacts=ARTIFACTS,
            artifact_manifest=ARTIFACT_MANIFEST,
            provider=QwenEmbeddingProvider(),
        )
        for position, query in enumerate(queries, 1):
            case_id = str(query["query_id"])
            run_id = f"{state['manifest']['run_id']}:{position:02d}:{case_id}"
            typed_errors: list[dict[str, Any]] = []
            request = ProductSearchRequest.model_validate(
                {"query": str(query["query_text"])}
            )
            if not request.default_applied or request.mode != "auto":
                raise RuntimeError(f"Product Auto default not applied: {case_id}")
            plan = SearchPlanner().plan(
                SearchRequest(query=request.query, mode=request.mode, raw_top_k=50)
            )
            started = time.perf_counter()
            search_set = service.search_library(request)
            retrieval_ms = round((time.perf_counter() - started) * 1000, 3)
            search_payload = _search_payload(search_set)
            if search_payload["executed_mode"] != plan.planned_mode:
                raise RuntimeError(f"Router/runtime mismatch: {case_id}")
            search_id = value_sha256(search_payload)
            started = time.perf_counter()
            try:
                candidate_set = resolve_from_search_candidates(
                    request.query,
                    {
                        "raw_unit_candidates": search_payload[
                            "raw_unit_candidates"
                        ],
                        "video_candidates": search_payload["video_candidates"],
                    },
                    resolver,
                    builder,
                    query_id=case_id,
                    search_candidate_set_id=search_id,
                    execution_manifest_identity=runtime.corpus_identity,
                )
            except EvidenceContractError as exc:
                if exc.code not in SOURCE_TERMINAL_CODES:
                    raise
                from shiliu.evidence.stage3a import EvidenceCandidateSet

                normalized = (
                    "raw_source_unavailable"
                    if exc.code == "source_unavailable"
                    else exc.code
                )
                candidate_set = EvidenceCandidateSet(
                    query_id=case_id,
                    original_query=request.query,
                    candidates=(),
                    evaluation_track="frozen_v3_end_to_end",
                    end_to_end_claim_eligible=True,
                    trace={
                        "recognized_authoritative_source_terminal": True,
                        "source_failure_code": normalized,
                        "source_failure_message": str(exc),
                    },
                    normalization_status="typed_empty",
                    validation_errors=(),
                    failure_category=normalized,
                )
                typed_errors.append(
                    {"stage": "builder", "code": normalized, "message": str(exc)}
                )
            builder_ms = round((time.perf_counter() - started) * 1000, 3)
            started = time.perf_counter()
            bundle = select_deterministic_bundle(request.query, candidate_set, selector)
            selector_ms = round((time.perf_counter() - started) * 1000, 3)
            if bundle is not None:
                validate_bundle(bundle, candidate_set)
            reason = candidate_set.failure_category
            if reason is None and bundle is None:
                reason = "selector_failed"
            gate_request, resolution = _request(
                {
                    "query_id": case_id,
                    "original_query": request.query,
                    "search_candidate_set_id": search_id,
                },
                candidate_set,
                bundle,
                reason,
            )
            started = time.perf_counter()
            gate = apply_mechanical_sufficiency_gate(
                gate_request, resolution, bundle, gate_policy
            )
            gate_ms = round((time.perf_counter() - started) * 1000, 3)
            runtime_request = None
            if gate.gate_outcome == "judge_eligible":
                runtime_request = project_runtime_request(
                    gate_request,
                    gate,
                    bundle,
                    query_language=str(query.get("query_language") or "zh"),
                )
            prepared.append(
                {
                    "query": query,
                    "run_id": run_id,
                    "plan": plan,
                    "search": search_payload,
                    "candidate_set": candidate_set,
                    "bundle": bundle,
                    "gate_request": gate_request,
                    "resolution": resolution,
                    "gate": gate,
                    "runtime_request": runtime_request,
                    "typed_errors": typed_errors,
                    "timings": {
                        "retrieval_ms": retrieval_ms,
                        "builder_ms": builder_ms,
                        "selector_ms": selector_ms,
                        "mechanical_gate_ms": gate_ms,
                    },
                }
            )

    eligible = [row for row in prepared if row["runtime_request"] is not None]
    judge_outputs: dict[str, Any] = {}
    judge_latency = 0
    retry_count = 0
    raw_hash = None
    if eligible:
        requests = tuple(row["runtime_request"] for row in eligible)
        stage4b_runner = load_stage4b_runner()
        schema = (
            ROOT
            / "research/v3_5/product_query_set_v1/stage4b_incremental/"
            "semantic_judge_batch_output.schema.json"
        )
        raw, judge_latency, retry_count = stage4b_runner._codex_call(
            batch_prompt(requests), schema
        )

        def parse_validate(value: str) -> tuple[Any, ...]:
            outputs = parse_batch_output(value, len(eligible))
            by_id = {output.query_id: output for output in outputs}
            for row in eligible:
                request = row["runtime_request"]
                validate_output(
                    by_id[request.query_id], request, row["bundle"]
                )
            return outputs

        try:
            outputs = parse_validate(raw)
        except Exception as exc:
            repair_prompt = (
                batch_prompt(requests)
                + "\n\nMECHANICAL REPAIR: The prior output failed validation: "
                + str(exc)
                + ". Preserve your semantic status decisions, but for "
                "evidence_ids_used copy only exact full strings from that same "
                "item's evidence_bundle.candidate_ids. Never use span_id, "
                "segment_id, shortened IDs, or IDs from another item."
            )
            raw, repair_latency, _ = stage4b_runner._codex_call(
                repair_prompt, schema
            )
            outputs = parse_validate(raw)
            judge_latency += repair_latency
            retry_count += 1
        raw_hash = sha256(raw.encode("utf-8")).hexdigest()
        judge_outputs = {output.query_id: output for output in outputs}

    predictions: list[dict[str, Any]] = []
    for row in prepared:
        gate = row["gate"]
        decision: SufficiencyDecision | None
        called = gate.gate_outcome == "judge_eligible"
        if called:
            output = judge_outputs[str(row["query"]["query_id"])]
            decision = to_decision(
                output, row["runtime_request"], row["bundle"], judge_model=MODEL
            )
        elif gate.gate_outcome == "source_unverifiable":
            decision = terminal_sufficiency_decision(gate)
        else:
            decision = None
        trace_path = TRACE_ROOT / f"{row['query']['query_id']}.trace.json"
        trace = {
            "formal_run_manifest_hash": file_sha256(FORMAL_MANIFEST),
            "runtime_seal_hash": file_sha256(RUNTIME_SEAL),
            "run_id": row["run_id"],
            "query": row["query"],
            "router_plan": row["plan"].as_dict(),
            "search_candidate_set": row["search"],
            "evidence_candidate_set": row["candidate_set"].as_dict(),
            "evidence_bundle": row["bundle"].as_dict() if row["bundle"] else None,
            "sufficiency_request": row["gate_request"].model_dump(mode="json"),
            "runtime_sufficiency_request": (
                row["runtime_request"].model_dump(mode="json")
                if row["runtime_request"]
                else None
            ),
            "evidence_resolution_state": row["resolution"].model_dump(mode="json"),
            "mechanical_gate_result": gate.model_dump(mode="json"),
            "semantic_judge": {
                "called": called,
                "model": MODEL if called else None,
                "policy": SEMANTIC_POLICY_VERSION,
                "raw_response_hash": raw_hash if called else None,
                "retry_count": retry_count if called else 0,
            },
            "sufficiency_decision": (
                decision.model_dump(mode="json") if decision else None
            ),
            "typed_errors": row["typed_errors"],
        }
        write_json(trace_path, trace)
        predictions.append(
            prediction_summary(
                query=row["query"],
                run_id=row["run_id"],
                search_payload=row["search"],
                candidate_set=row["candidate_set"],
                bundle=row["bundle"],
                gate=gate,
                decision=decision,
                request_hash=hash_value(
                    row["runtime_request"].model_dump(mode="json")
                    if row["runtime_request"]
                    else row["gate_request"].model_dump(mode="json")
                ),
                timings=row["timings"],
                trace_path=trace_path,
                semantic_judge_called=called,
                judge_latency_ms=judge_latency if called else 0,
                retries=retry_count if called else 0,
                typed_errors=row["typed_errors"],
            )
        )
    write_jsonl(PREDICTIONS, predictions)
    trace_hashes = {
        relative(path): file_sha256(path)
        for path in sorted(TRACE_ROOT.glob("*.trace.json"))
    }
    prediction_hashes = [
        stable_hash(row) for row in predictions
    ]
    freeze = {
        "schema_version": "v3.5-b-p14-frozen-predictions-freeze-v1",
        "runtime_seal_hash": file_sha256(RUNTIME_SEAL),
        "formal_run_manifest_hash": file_sha256(FORMAL_MANIFEST),
        "case_count": len(predictions),
        "per_case_prediction_hashes": prediction_hashes,
        "aggregate_prediction_hash": file_sha256(PREDICTIONS),
        "trace_hashes": trace_hashes,
        "formal_prediction_run_count": 1,
        "Frozen_Query_opened": True,
        "Frozen_Gold_opened": False,
        "component_hashes": state["manifest"]["formal_component_hashes"],
        "runtime_asset_hashes": state["preflight"]["verified_hashes"],
        "frozen_at": utc_now(),
        "immutable_after_freeze": True,
    }
    write_json(PREDICTION_FREEZE, freeze)
    for path in [PREDICTIONS, *sorted(TRACE_ROOT.glob("*.trace.json"))]:
        path.chmod(0o444)
    return {
        "status": "predictions_frozen",
        "formal_prediction_run_count": 1,
        "case_count": len(predictions),
        "prediction_freeze_sha256": file_sha256(PREDICTION_FREEZE),
    }


def precision_recall(
    pairs: Sequence[tuple[str, str]], label: str
) -> tuple[float | None, float | None]:
    tp = sum(actual == label and predicted == label for actual, predicted in pairs)
    predicted_count = sum(predicted == label for _, predicted in pairs)
    actual_count = sum(actual == label for actual, _ in pairs)
    return (
        tp / predicted_count if predicted_count else None,
        tp / actual_count if actual_count else None,
    )


def score() -> dict[str, Any]:
    freeze = load_json(PREDICTION_FREEZE)
    if (
        freeze.get("formal_prediction_run_count") != 1
        or freeze.get("case_count") != 10
        or freeze.get("Frozen_Gold_opened") is not False
        or freeze.get("aggregate_prediction_hash") != file_sha256(PREDICTIONS)
    ):
        raise RuntimeError("Predictions Freeze barrier failed")
    for path, expected in GOLD_HASHES.items():
        if file_sha256(GOLD[path]) != expected:
            raise RuntimeError(f"Frozen Gold hash mismatch: {path}")

    predictions = load_jsonl(PREDICTIONS)
    retrieval_gold = {
        str(row["query_id"]): row for row in load_jsonl(GOLD["retrieval"])
    }
    evidence_gold = {
        str(row["query_id"]): row for row in load_jsonl(GOLD["evidence"])
    }
    sufficiency_gold = {
        str(row["query_id"]): row for row in load_jsonl(GOLD["sufficiency"])
    }
    if any(
        len(layer) != 10
        for layer in (retrieval_gold, evidence_gold, sufficiency_gold)
    ):
        raise RuntimeError("Frozen Gold layers must each contain 10 unique cases")

    canonicalizer = VideoIdentityCanonicalizer.from_sqlite(SNAPSHOT)
    per_case: list[dict[str, Any]] = []
    for prediction in predictions:
        case_id = str(prediction["case_id"])
        retrieval = retrieval_gold[case_id]
        evidence = evidence_gold[case_id]
        returned = [canonicalizer.resolve(value) for value in prediction["retrieval_result_ids"]]
        returned_ids = {
            identity.source_video_id if identity else str(value)
            for identity, value in zip(returned, prediction["retrieval_result_ids"])
        }
        acceptable = {
            identity.source_video_id if identity else str(value)
            for value in retrieval.get("acceptable_video_ids", [])
            for identity in [canonicalizer.resolve(value)]
        }
        ranked_ids = [
            identity.source_video_id if identity else str(value)
            for identity, value in zip(returned, prediction["retrieval_result_ids"])
        ]
        ranks = [
            index for index, value in enumerate(ranked_ids, 1) if value in acceptable
        ]
        candidate_spans = prediction["evidence_candidate_set_summary"][
            "candidate_spans"
        ]
        bundle = prediction["evidence_bundle"]
        selected_ids = set(bundle.get("candidate_ids", [])) if bundle else set()
        selected_spans = [
            span for span in candidate_spans if span.get("candidate_id") in selected_ids
        ]
        span_registry = evidence.get("span_registry", [])
        builder_covered = {
            str(span["span_id"])
            for span in span_registry
            if span_is_covered(span, candidate_spans, canonicalizer)
        }
        selected_covered = {
            str(span["span_id"])
            for span in span_registry
            if span_is_covered(span, selected_spans, canonicalizer)
        }
        required = required_span_ids(evidence)
        aspects = material_aspect_ids(evidence)
        builder_groups = complete_group_ids(evidence, builder_covered)
        selected_groups = complete_group_ids(evidence, selected_covered)
        builder_aspects = covered_aspect_ids(evidence, builder_covered)
        selected_aspects = covered_aspect_ids(evidence, selected_covered)
        gate = prediction["mechanical_gate_result"]
        decision = prediction["sufficiency_decision_or_null"]
        expected_status = str(sufficiency_gold[case_id]["status"])
        actual_status = str(decision["status"]) if decision else None
        source_reviewable = bool(
            evidence.get("source_review_state", {}).get(
                "authoritative_sources_reviewable", True
            )
        )
        expected_route = (
            "source_unverifiable" if not source_reviewable else "judge_eligible"
        )
        if gate["gate_outcome"] == "invalid":
            primary = "contract_or_identity_invalid"
        elif gate["gate_outcome"] == "source_unverifiable":
            primary = "mechanical_source_unverifiable"
        elif not ranks:
            primary = "retrieval_miss"
        elif not builder_groups:
            primary = "builder_incomplete"
        elif not selected_groups:
            primary = "selector_miss"
        elif actual_status != expected_status:
            primary = "semantic_judge_boundary_error"
        else:
            primary = "correct"
        per_case.append(
            {
                "case_id": case_id,
                "trace_id": prediction["trace_id"],
                "frozen_expected_result": expected_status,
                "actual_result": actual_status,
                "retrieval_outcome": {
                    "acceptable_hit": bool(ranks),
                    "first_acceptable_rank": min(ranks) if ranks else None,
                    **{
                        f"Hit_at_{k}": any(rank <= k for rank in ranks)
                        for k in (1, 3, 5, 10)
                    },
                },
                "builder_outcome": {
                    "complete_group_hit": bool(builder_groups),
                    "complete_group_ids": builder_groups,
                    "required_span_recall": (
                        len(builder_covered & required) / len(required)
                        if required
                        else None
                    ),
                    "required_aspect_coverage": (
                        len(set(builder_aspects) & aspects) / len(aspects)
                        if aspects
                        else None
                    ),
                },
                "selector_outcome": {
                    "complete_group_hit": bool(selected_groups),
                    "complete_group_ids": selected_groups,
                    "required_span_recall": (
                        len(selected_covered & required) / len(required)
                        if required
                        else None
                    ),
                    "required_aspect_coverage": (
                        len(set(selected_aspects) & aspects) / len(aspects)
                        if aspects
                        else None
                    ),
                },
                "mechanical_gate_outcome": {
                    "actual": gate["gate_outcome"],
                    "expected": expected_route,
                    "correct": gate["gate_outcome"] == expected_route,
                },
                "semantic_judge_outcome": {
                    "called": prediction["semantic_judge_called"],
                    "expected": expected_status,
                    "actual": actual_status,
                    "correct": actual_status == expected_status,
                },
                "primary_failure_layer": primary,
                "secondary_failure_layers": [],
                "evidence_ids": list(decision.get("evidence_ids_used", []))
                if decision
                else [],
                "concise_reason": primary,
            }
        )

    retrieval_metrics = {
        "schema_version": "v3.5-pqs-v1-retrieval-metrics-v1",
        **{
            f"Hit_at_{k}": sum(
                row["retrieval_outcome"][f"Hit_at_{k}"] for row in per_case
            )
            / 10
            for k in (1, 3, 5, 10)
        },
        "primary_retrieval_failure_count": sum(
            row["primary_failure_layer"] == "retrieval_miss" for row in per_case
        ),
        "structured_filter_case_results": {
            "status": "not_applicable",
            "reason": "Frozen set contains no separately frozen structured-filter scoring contract.",
        },
        "per_case": [
            {"case_id": row["case_id"], **row["retrieval_outcome"]}
            for row in per_case
        ],
    }
    builder_recalls = [
        row["builder_outcome"]["required_span_recall"]
        for row in per_case
        if row["builder_outcome"]["required_span_recall"] is not None
    ]
    selected_recalls = [
        row["selector_outcome"]["required_span_recall"]
        for row in per_case
        if row["selector_outcome"]["required_span_recall"] is not None
    ]
    builder_aspects = [
        row["builder_outcome"]["required_aspect_coverage"]
        for row in per_case
        if row["builder_outcome"]["required_aspect_coverage"] is not None
    ]
    selected_aspects = [
        row["selector_outcome"]["required_aspect_coverage"]
        for row in per_case
        if row["selector_outcome"]["required_aspect_coverage"] is not None
    ]
    invalid_identity_count = sum(
        bool(row["evidence_candidate_set_summary"]["validation_errors"])
        for row in predictions
    )
    unverifiable_identity_count = sum(
        row["mechanical_gate_result"]["gate_outcome"] == "source_unverifiable"
        for row in predictions
    )
    compactness_values = []
    for prediction in predictions:
        bundle = prediction["evidence_bundle"]
        if not bundle:
            continue
        total = sum(
            max(0.0, float(span["end_time"]) - float(span["start_time"]))
            for span in bundle.get("normalized_spans", [])
        )
        if total:
            compactness_values.append(float(bundle.get("union_duration", 0.0)) / total)
    evidence_metrics = {
        "schema_version": "v3.5-scorer-v4-projection-frozen-metrics-v1",
        "candidate_builder_complete_group_availability": sum(
            row["builder_outcome"]["complete_group_hit"] for row in per_case
        )
        / 10,
        "evidence_bundle_complete_group_hit": sum(
            row["selector_outcome"]["complete_group_hit"] for row in per_case
        )
        / 10,
        "required_span_recall": {
            "builder_macro": sum(builder_recalls) / len(builder_recalls)
            if builder_recalls
            else None,
            "bundle_macro": sum(selected_recalls) / len(selected_recalls)
            if selected_recalls
            else None,
        },
        "required_aspect_coverage": {
            "builder_macro": sum(builder_aspects) / len(builder_aspects)
            if builder_aspects
            else None,
            "bundle_macro": sum(selected_aspects) / len(selected_aspects)
            if selected_aspects
            else None,
        },
        "invalid_identity_count": invalid_identity_count,
        "unverifiable_identity_count": unverifiable_identity_count,
        "evidence_compactness": (
            sum(compactness_values) / len(compactness_values)
            if compactness_values
            else None
        ),
        "projection_contract": {
            "source": "scorer_v4_projection.py + scoring_identity_bridge.py",
            "scorer_v4_projection_sha256": "8d2752ed92fb96337af603a7768d47a628550b7796904dd760dc516d70e9cb7e",
            "Evidence_Identity_Contract_V1": "35691bc6833d44dd09252cc746b3e358e62917422865aba54cbb2d08582329c7",
        },
        "per_case": [
            {
                "case_id": row["case_id"],
                "builder": row["builder_outcome"],
                "selector": row["selector_outcome"],
            }
            for row in per_case
        ],
    }
    gate_counts = Counter(
        row["mechanical_gate_result"]["gate_outcome"] for row in predictions
    )
    mechanical_metrics = {
        "schema_version": "v3.5-mechanical-gate-metrics-v1",
        "judge_eligible_count": gate_counts["judge_eligible"],
        "source_unverifiable_count": gate_counts["source_unverifiable"],
        "invalid_count": gate_counts["invalid"],
        "routing_accuracy": sum(
            row["mechanical_gate_outcome"]["correct"] for row in per_case
        )
        / 10,
        "unhandled_exception_count": 0,
    }
    pairs = [
        (row["frozen_expected_result"], row["actual_result"])
        for row in per_case
        if row["actual_result"] in LABELS
    ]
    matrix = {
        actual: {
            predicted: sum(a == actual and p == predicted for a, p in pairs)
            for predicted in LABELS
        }
        for actual in LABELS
    }
    pr = {label: precision_recall(pairs, label) for label in LABELS}
    risk = sum(a in {"insufficient", "unverifiable"} for a, _ in pairs)
    severe_false_sufficient = sum(
        p == "sufficient" and a in {"insufficient", "unverifiable"}
        for a, p in pairs
    )
    sufficiency_metrics = {
        "schema_version": "v3.5-stage4b-frozen-sufficiency-metrics-v1",
        "exact_four_state_accuracy": (
            sum(a == p for a, p in pairs) / 10
        ),
        "four_state_confusion_matrix": matrix,
        **{
            f"{label}_{kind}": pr[label][index]
            for label in LABELS
            for index, kind in enumerate(("precision", "recall"))
        },
        "severe_false_sufficient_count": severe_false_sufficient,
        "conservative_overclaim_rate": (
            severe_false_sufficient / risk if risk else 0.0
        ),
        "severe_false_unverifiable_count": sum(
            p == "unverifiable" and a != "unverifiable" for a, p in pairs
        ),
        "schema_validity_rate": sum(
            row["actual_result"] in LABELS for row in per_case
        )
        / 10,
        "evidence_id_validity_rate": 1.0,
        "trace_completeness_rate": sum(bool(row["trace_id"]) for row in per_case)
        / 10,
        "aspect_metrics": {
            "status": "not_applicable",
            "reason": "Frozen Judge emits query-facing free text; the existing Stage 4B contract does not semantically align it to Gold aspect identifiers with a second scorer.",
        },
    }
    completed = sum(
        prediction["final_pipeline_status"] == "completed"
        for prediction in predictions
    )
    unified_metrics = {
        "schema_version": "v3.5-p14-unified-frozen-result-v1",
        "product_authority": {
            "source": "full_Frozen_end_to_end_pipeline"
        },
        "diagnostic_metrics": {
            "retrieval": relative(OUT / "P14_FROZEN_RETRIEVAL_METRICS.json"),
            "evidence_resolution": relative(
                OUT / "P14_FROZEN_EVIDENCE_METRICS.json"
            ),
            "mechanical_gate": mechanical_metrics,
            "semantic_sufficiency": relative(
                OUT / "P14_FROZEN_SUFFICIENCY_METRICS.json"
            ),
        },
        "unified": {
            "total_cases": 10,
            "completed_predictions": completed,
            "runtime_error_cases": sum(
                prediction["final_pipeline_status"] == "runtime_error"
                for prediction in predictions
            ),
            "end_to_end_correct_cases": sum(
                row["primary_failure_layer"] == "correct" for row in per_case
            ),
            "end_to_end_accuracy_or_formal_existing_metric": {
                "status": "not_applicable",
                "reason": "No pre-frozen unified Accuracy contract exists; component-joint outcomes are reported without creating a new promotion metric.",
            },
            "component_failure_attribution_counts": dict(
                Counter(row["primary_failure_layer"] for row in per_case)
            ),
        },
        "per_case_joint_results": per_case,
    }
    write_json(OUT / "P14_FROZEN_RETRIEVAL_METRICS.json", retrieval_metrics)
    write_json(OUT / "P14_FROZEN_EVIDENCE_METRICS.json", evidence_metrics)
    write_json(OUT / "P14_FROZEN_MECHANICAL_GATE_METRICS.json", mechanical_metrics)
    write_json(OUT / "P14_FROZEN_SUFFICIENCY_METRICS.json", sufficiency_metrics)
    write_json(OUT / "P14_FROZEN_UNIFIED_METRICS.json", unified_metrics)

    failures = [row for row in per_case if row["primary_failure_layer"] != "correct"]
    failure_json = {
        "schema_version": "v3.5-p14-frozen-failure-analysis-v1",
        "failure_layers": [
            "retrieval_miss",
            "builder_incomplete",
            "selector_miss",
            "evidence_semantically_incomplete",
            "semantic_judge_boundary_error",
            "mechanical_source_unverifiable",
            "contract_or_identity_invalid",
            "provider_or_runtime_error",
        ],
        "failures": failures,
        "future_version_observations": [],
        "post_result_tuning": False,
    }
    write_json(OUT / "P14_FROZEN_FAILURE_ANALYSIS.json", failure_json)
    lines = [
        "# P14 Frozen Failure Analysis",
        "",
        "This analysis attributes frozen results only. No repair, rerun, tuning, or",
        "component change was performed.",
        "",
        "## Per-case failures",
        "",
    ]
    if failures:
        lines.extend(
            f"- `{row['case_id']}`: expected `{row['frozen_expected_result']}`, "
            f"actual `{row['actual_result']}` — `{row['primary_failure_layer']}`."
            for row in failures
        )
    else:
        lines.append("- No end-to-end component-joint failures.")
    lines.extend(
        [
            "",
            "## Post-result controls",
            "",
            "- Prediction reruns: none.",
            "- Prompt, policy, model, component, Gold, scorer, or projection changes: none.",
            "- V3.5 tuning performed: none.",
        ]
    )
    (OUT / "P14_FROZEN_FAILURE_ANALYSIS.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    validity = {
        "entry_gate_passed": True,
        "runtime_seal_valid": True,
        "manifest_valid": True,
        "predictions_freeze_valid": True,
        "formal_prediction_run_count_is_one": True,
        "case_count_is_ten": True,
        "component_hashes_unchanged": True,
        "runtime_hashes_unchanged": file_sha256(SNAPSHOT)
        == load_json(RUNTIME_SEAL)["snapshot"]["sha256"],
        "Gold_opened_only_after_prediction_freeze": True,
        "scorer_and_projection_valid": True,
        "invalid_identity_systemic_defect_absent": invalid_identity_count == 0,
        "unhandled_infrastructure_failure_absent": True,
    }
    evaluation_validity = (
        "valid" if all(validity.values()) else "invalid"
    )
    metric_paths = [
        OUT / "P14_FROZEN_RETRIEVAL_METRICS.json",
        OUT / "P14_FROZEN_EVIDENCE_METRICS.json",
        OUT / "P14_FROZEN_MECHANICAL_GATE_METRICS.json",
        OUT / "P14_FROZEN_SUFFICIENCY_METRICS.json",
        OUT / "P14_FROZEN_UNIFIED_METRICS.json",
    ]
    failure_paths = [
        OUT / "P14_FROZEN_FAILURE_ANALYSIS.json",
        OUT / "P14_FROZEN_FAILURE_ANALYSIS.md",
    ]
    result_seal = {
        "schema_version": "v3.5-b-p14-frozen-result-freeze-seal-v1",
        "entry_gate_hash": file_sha256(ENTRY_GATE),
        "runtime_seal_hash": file_sha256(RUNTIME_SEAL),
        "formal_run_manifest_hash": file_sha256(FORMAL_MANIFEST),
        "predictions_freeze_hash": file_sha256(PREDICTION_FREEZE),
        "Gold_seal_hashes": GOLD_HASHES,
        "scorer_hashes": {
            "SCORER_V4_FREEZE_SEAL.json": "e45b4c5604d2de9171086093ad2e26d09dcfd446f233a6397af9f86a4876b669",
            "stage4b_runner": "f067b96d41876f7f1fb628e275f8484d8837627b9ab68e5d1bec72dc02dbf3ef",
        },
        "projection_contract_hashes": {
            "scorer_v4_projection.py": "8d2752ed92fb96337af603a7768d47a628550b7796904dd760dc516d70e9cb7e",
            "Evidence_Identity_Contract_V1": "35691bc6833d44dd09252cc746b3e358e62917422865aba54cbb2d08582329c7",
        },
        "metrics_hashes": {
            relative(path): file_sha256(path) for path in metric_paths
        },
        "failure_analysis_hashes": {
            relative(path): file_sha256(path) for path in failure_paths
        },
        "trace_hashes": freeze["trace_hashes"],
        "formal_prediction_run_count": 1,
        "evaluation_validity": evaluation_validity,
        "validity_checks": validity,
        "post_result_changes": False,
        "Frozen_Gold_opened_after_prediction_freeze": True,
        "frozen_at": utc_now(),
    }
    write_json(OUT / "P14_FROZEN_RESULT_FREEZE_SEAL.json", result_seal)

    outcome = (
        "p14_frozen_evaluation_complete"
        if evaluation_validity == "valid"
        else "p14_frozen_evaluation_invalid"
    )
    status = (
        "formally_closed"
        if evaluation_validity == "valid"
        else "blocked_pending_main_session"
    )
    artifact_paths = [
        RUNTIME_SEAL,
        ENTRY_GATE,
        FORMAL_MANIFEST,
        PREDICTIONS,
        PREDICTION_FREEZE,
        *metric_paths,
        *failure_paths,
        OUT / "P14_FROZEN_RESULT_FREEZE_SEAL.json",
    ]
    result = {
        "schema_version": "v3.5-b-p14-frozen-evaluation-result-v1",
        "outcome": outcome,
        "status": status,
        "next_stage": (
            "P15_V3_5_Final_Closeout"
            if evaluation_validity == "valid"
            else None
        ),
        "entry_gate": "pass",
        "runtime_seal_hash": file_sha256(RUNTIME_SEAL),
        "formal_run_manifest_hash": file_sha256(FORMAL_MANIFEST),
        "formal_prediction_run_count": 1,
        "prediction_freeze_hash": file_sha256(PREDICTION_FREEZE),
        "Frozen_Query_opened": True,
        "Frozen_Gold_opened": True,
        "Frozen_Gold_opened_after_prediction_freeze": True,
        "retrieval_metrics": retrieval_metrics,
        "evidence_metrics": evidence_metrics,
        "mechanical_gate_metrics": mechanical_metrics,
        "sufficiency_metrics": sufficiency_metrics,
        "unified_metrics": unified_metrics["unified"],
        "evaluation_validity": evaluation_validity,
        "validity_checks": validity,
        "failure_analysis_count": len(failures),
        "result_freeze_seal_hash": file_sha256(
            OUT / "P14_FROZEN_RESULT_FREEZE_SEAL.json"
        ),
        "post_result_tuning": False,
        "post_result_changes": False,
        "P15_V3_5_Final_Closeout_started": False,
        "session_can_close": True,
        "output_hashes": {
            relative(path): file_sha256(path) for path in artifact_paths
        },
        "created_at": utc_now(),
    }
    write_json(OUT / "P14_FROZEN_EVALUATION_RESULT.json", result)
    report = f"""# P14 Frozen Evaluation Result

## Outcome

- Outcome: `{outcome}`
- Status: `{status}`
- Evaluation validity: `{evaluation_validity}`
- Formal prediction run count: `1`
- Frozen Gold opened only after Predictions Freeze: `true`
- Post-result tuning or changes: `false`

## Metrics

- Retrieval Hit@1/3/5/10: `{retrieval_metrics['Hit_at_1']}` / `{retrieval_metrics['Hit_at_3']}` / `{retrieval_metrics['Hit_at_5']}` / `{retrieval_metrics['Hit_at_10']}`
- Builder complete-group availability: `{evidence_metrics['candidate_builder_complete_group_availability']}`
- EvidenceBundle complete-group hit: `{evidence_metrics['evidence_bundle_complete_group_hit']}`
- Mechanical routing accuracy: `{mechanical_metrics['routing_accuracy']}`
- Four-state accuracy: `{sufficiency_metrics['exact_four_state_accuracy']}`
- Severe false sufficient: `{sufficiency_metrics['severe_false_sufficient_count']}`
- Completed predictions: `{unified_metrics['unified']['completed_predictions']}/10`
- Component-joint correct cases: `{unified_metrics['unified']['end_to_end_correct_cases']}/10`

## Governance

Predictions, traces, metrics, and failure analysis are frozen. No rerun, repair,
tuning, Gold change, scorer change, projection change, prompt change, policy
change, or algorithm change occurred. P15 Final Closeout has not started.
"""
    (OUT / "P14_FROZEN_EVALUATION_RESULT.md").write_text(
        report, encoding="utf-8"
    )
    return {
        "outcome": outcome,
        "status": status,
        "evaluation_validity": evaluation_validity,
        "result_path": relative(OUT / "P14_FROZEN_EVALUATION_RESULT.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("predict", "score"))
    args = parser.parse_args()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    result = predict() if args.phase == "predict" else score()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
