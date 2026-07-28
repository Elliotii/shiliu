from __future__ import annotations

from collections import Counter
from dataclasses import fields
from hashlib import sha256
import argparse
import json
from pathlib import Path
from statistics import mean
import time
from typing import Any, Iterable, Mapping, Sequence

from shiliu.evidence.stage3a import (
    CandidateBuilderConfig,
    EvidenceCandidateSet,
    SelectorConfig,
    interval_union_duration,
    resolve_from_search_candidates,
    select_deterministic_bundle,
    validate_bundle,
)
from shiliu.evidence.contracts import EvidenceContractError
from shiliu.eval_v3_5.isolation import HeldoutAccessGuard
from shiliu.eval_v3_5.stage3a import FrozenRawSourceResolver
from shiliu.eval_v3_5.stage3r_track_a_auto_refresh import (
    _complete_groups,
    _physical_groups,
    load_jsonl,
)


ROOT = Path("/Users/elliot/new-systems/agent-job-prep/Shiliu")
OUT = ROOT / "research/v3_5/product_query_set_v1/f1a_candidate_builder_major_cycle_1"
P8 = ROOT / "research/v3_5/product_query_set_v1/product_initial_baseline_attempt_3"
STRESS = ROOT / "research/v3_5/stage3r_qc/track_a_auto_refresh"
ARTIFACT_MANIFEST = ROOT / "research/v3_eval/artifact_manifest.jsonl"
SNAPSHOT_DB = Path(
    "/Users/elliot/Documents/Shiliu/eval/v3_stage6/"
    "20260720T094346Z_c7663365/shiliu_eval.db"
)
DEVELOPMENT_GOLD = ROOT / (
    "research/v3_5/product_query_set_v1/gold_construction_v1/"
    "development_seal_v1/sealed"
)
DEVELOPMENT_GOLD_PATHS = {
    "retrieval": DEVELOPMENT_GOLD / "product_retrieval_gold.development.v1.sealed.jsonl",
    "evidence": DEVELOPMENT_GOLD / "product_evidence_gold.development.v1.sealed.jsonl",
    "sufficiency": DEVELOPMENT_GOLD / "product_sufficiency_gold.development.v1.sealed.jsonl",
    "case_status": DEVELOPMENT_GOLD / "reviewed_case_status.development.v1.sealed.jsonl",
}
STRESS_SCORING = ROOT / "research/v3_5/stage3r/scoring/development_scoring_projection.31_cases.jsonl"
STRESS_RUNTIME = ROOT / "research/v3_5/stage3r/execution_manifest/development_runtime_input.31_cases.jsonl"
STRESS_BRIDGE = ROOT / "research/v3_5/stage3r_s1/identity_mapping/gold_segment_identity_projection.jsonl"
P8_QUERY_IDS = (
    "PQS_V1_Q003", "PQS_V1_Q004", "PQS_V1_Q005", "PQS_V1_Q006",
    "PQS_V1_Q007", "PQS_V1_Q008", "PQS_V1_Q011", "PQS_V1_Q012",
    "PQS_V1_Q013", "PQS_V1_Q014", "PQS_V1_Q015", "PQS_V1_Q017",
    "PQS_V1_Q018", "PQS_V1_Q019",
)
EXISTING_SIX = {
    "PQS_V1_Q006", "PQS_V1_Q007", "PQS_V1_Q011",
    "PQS_V1_Q012", "PQS_V1_Q013", "PQS_V1_Q019",
}
AUTHORITATIVE_SOURCE_TERMINAL_CODES = frozenset({"no_supported_subtitle"})
RUNNER_VERSION = "v3.5-b-f1a-evaluation-harness-recovery-v1"


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    values = [
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for row in rows
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(values) + ("\n" if values else ""), encoding="utf-8")


def stable_identity(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def builder_config() -> CandidateBuilderConfig:
    raw = load(ROOT / "research/v3_5/stage3b/stage3b_run_manifest.json")[
        "builder_config"
    ]
    allowed = {field.name for field in fields(CandidateBuilderConfig)}
    return CandidateBuilderConfig(**{
        key: tuple(value) if key in {
            "preferred_duration_seconds", "preferred_characters",
        } else value
        for key, value in raw.items() if key in allowed
    })


def assert_sealed() -> dict[str, Any]:
    seal_path = OUT / "f1a_implementation_freeze_seal.json"
    if not seal_path.is_file():
        raise RuntimeError("implementation freeze seal is absent")
    seal = load(seal_path)
    expected = {
        **seal["source_hashes"], **seal["config_hashes"],
        **seal["test_hashes"],
    }
    mismatches = {
        relative: {"expected": expected_hash, "actual": digest(ROOT / relative)}
        for relative, expected_hash in expected.items()
        if digest(ROOT / relative) != expected_hash
    }
    if mismatches:
        raise RuntimeError(f"sealed implementation mismatch: {mismatches}")
    return seal


def normalize_source_terminal(
    *, query_id: str, query: str, error: EvidenceContractError,
) -> EvidenceCandidateSet:
    """Convert only contract-recognized source terminals to legal empty output."""

    if error.code not in AUTHORITATIVE_SOURCE_TERMINAL_CODES:
        raise error
    return EvidenceCandidateSet(
        query_id=query_id,
        original_query=query,
        candidates=(),
        evaluation_track="frozen_v3_end_to_end",
        end_to_end_claim_eligible=True,
        trace={
            "recognized_authoritative_source_terminal": True,
            "source_failure_code": error.code,
            "source_failure_message": str(error),
            "serialization_policy": RUNNER_VERSION,
        },
        normalization_status="typed_empty",
        validation_errors=(),
        failure_category=error.code,
    )


def runtime_terminal(candidate_set: EvidenceCandidateSet) -> dict[str, Any]:
    if candidate_set.failure_category in AUTHORITATIVE_SOURCE_TERMINAL_CODES:
        return {
            "complete": True,
            "status": "source_unverifiable",
            "reason_code": candidate_set.failure_category,
            "recognized_source_terminal": True,
            "builder_called": False,
            "selector_called": False,
            "mechanical_gate_outcome": "terminal_unverifiable",
        }
    if candidate_set.failure_category == "upstream_retrieval_failure":
        return {
            "complete": True,
            "status": "upstream_retrieval_failure",
            "reason_code": "upstream_retrieval_failure",
            "recognized_source_terminal": False,
            "builder_called": True,
            "selector_called": False,
            "mechanical_gate_outcome": "mechanically_incomplete",
        }
    return {
        "complete": True,
        "status": "runtime_complete",
        "reason_code": None,
        "recognized_source_terminal": False,
        "builder_called": True,
        "selector_called": True,
        "mechanical_gate_outcome": "judge_eligible",
    }


def resolver() -> FrozenRawSourceResolver:
    return FrozenRawSourceResolver(
        artifact_manifest=ARTIFACT_MANIFEST,
        snapshot_db=SNAPSHOT_DB,
        guard=HeldoutAccessGuard(ROOT),
    )


def query_text(trace: Mapping[str, Any]) -> str:
    for location in (
        trace,
        trace.get("request", {}),
        trace.get("query", {}),
        trace.get("input", {}),
    ):
        if isinstance(location, Mapping):
            for key in ("original_query", "query", "query_text"):
                if isinstance(location.get(key), str):
                    return str(location[key])
    prediction = trace.get("prediction", {})
    if isinstance(prediction, Mapping):
        for key in ("original_query", "query"):
            if isinstance(prediction.get(key), str):
                return str(prediction[key])
    raise RuntimeError("P8 trace lacks original query")


def swap_summary(trace: Mapping[str, Any]) -> dict[str, Any]:
    per_video = trace.get("adaptive_bounded_coverage_swap", {})
    values = [
        value for value in per_video.values() if isinstance(value, Mapping)
    ] if isinstance(per_video, Mapping) else []
    iterations = [
        item
        for value in values
        for item in value.get("swap_iterations", [])
    ]
    return {
        "swap_count": sum(int(value.get("swap_count", 0)) for value in values),
        "zero_swap": not iterations,
        "added_candidate_ids": [
            str(value["added_candidate_id"]) for value in iterations
        ],
        "removed_candidate_ids": [
            str(value["removed_candidate_id"]) for value in iterations
        ],
        "iterations": iterations,
        "per_video": per_video,
    }


def candidate_runtime(
    query_id: str, query: str, search: Mapping[str, Any],
    source_resolver: FrozenRawSourceResolver, config: CandidateBuilderConfig,
) -> tuple[Any, Any, float, dict[str, Any]]:
    started = time.perf_counter()
    try:
        candidates = resolve_from_search_candidates(
            query, search, source_resolver, config,
            query_id=query_id,
            search_candidate_set_id=stable_identity(search),
            execution_manifest_identity="F1A_FROZEN_SEARCH_CANDIDATE_SET_REPLAY",
        )
    except EvidenceContractError as error:
        candidates = normalize_source_terminal(
            query_id=query_id, query=query, error=error,
        )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    bundle = (
        None if candidates.failure_category in AUTHORITATIVE_SOURCE_TERMINAL_CODES
        else select_deterministic_bundle(query, candidates, SelectorConfig())
    )
    if bundle is not None:
        validate_bundle(bundle, candidates)
    return candidates, bundle, elapsed_ms, swap_summary(candidates.trace)


def _dry_row(
    *, input_id: str, candidate_set: EvidenceCandidateSet, bundle: Any,
    swaps: Mapping[str, Any],
) -> dict[str, Any]:
    terminal = runtime_terminal(candidate_set)
    return {
        "input_id": input_id,
        "terminal": terminal,
        "candidate_count": len(candidate_set.candidates),
        "candidate_set_sha256": stable_identity(candidate_set.as_dict()),
        "bundle_sha256": stable_identity(bundle.as_dict()) if bundle else None,
        "swap_count": int(swaps["swap_count"]),
        "normalization_status": candidate_set.normalization_status,
        "validation_errors": list(candidate_set.validation_errors),
        "failure_category": candidate_set.failure_category,
        "legal_terminal": bool(terminal["complete"]) and (
            terminal["status"] != "source_unverifiable"
            or (
                terminal["reason_code"] in AUTHORITATIVE_SOURCE_TERMINAL_CODES
                and not candidate_set.candidates
                and bundle is None
            )
        ),
    }


def dry_development() -> dict[str, Any]:
    assert_sealed()
    config = builder_config()
    source_resolver = resolver()
    rows = []
    evidence_errors = []
    for query_id in P8_QUERY_IDS:
        trace = load(
            P8 / f"blind_run/product_initial_baseline.traces/{query_id}.trace.json"
        )
        query = query_text(trace)
        try:
            candidates, bundle, _, swaps = candidate_runtime(
                query_id, query, trace["search_candidate_set"],
                source_resolver, config,
            )
            rows.append(_dry_row(
                input_id=query_id, candidate_set=candidates,
                bundle=bundle, swaps=swaps,
            ))
        except EvidenceContractError as error:
            evidence_errors.append({
                "input_id": query_id, "code": error.code, "message": str(error),
            })
    stable_rows = sorted(rows, key=lambda value: value["input_id"])
    result = {
        "schema_version": "v3.5-b-f1a-gold-free-development-dry-run-v1",
        "runner_version": RUNNER_VERSION,
        "development_gold_semantic_accessed": False,
        "input_count": len(P8_QUERY_IDS),
        "runtime_output_count": len(rows),
        "legal_terminal_count": sum(row["legal_terminal"] for row in rows),
        "invalid_terminal_count": sum(not row["legal_terminal"] for row in rows),
        "evidence_contract_error_count": len(evidence_errors),
        "evidence_contract_errors": evidence_errors,
        "source_unverifiable_count": sum(
            row["terminal"]["status"] == "source_unverifiable" for row in rows
        ),
        "candidate_count_total": sum(row["candidate_count"] for row in rows),
        "maximum_swap_count_per_query": max(
            (row["swap_count"] for row in rows), default=0,
        ),
        "outputs": stable_rows,
        "output_hash_root": stable_identity(stable_rows),
        "status": "complete" if (
            len(rows) == len(P8_QUERY_IDS)
            and all(row["legal_terminal"] for row in rows)
            and not evidence_errors
        ) else "invalid",
    }
    write_json(OUT / "f1a_gold_free_development_dry_run.json", result)
    return result


def dry_stress() -> dict[str, Any]:
    assert_sealed()
    config = builder_config()
    source_resolver = resolver()
    case_ids = load(
        STRESS / "input_freeze/evidence_bearing_case_ids.json"
    )["case_ids"]
    rows = []
    evidence_errors = []
    for case_id in case_ids:
        case_root = STRESS / f"execution/cases/{case_id}"
        query = str(load(case_root / "candidate_builder_input.json")["query"])
        search = load(case_root / "search_candidate_set.json")
        try:
            candidates, bundle, _, swaps = candidate_runtime(
                case_id, query, search, source_resolver, config,
            )
            rows.append(_dry_row(
                input_id=case_id, candidate_set=candidates,
                bundle=bundle, swaps=swaps,
            ))
        except EvidenceContractError as error:
            evidence_errors.append({
                "input_id": case_id, "code": error.code, "message": str(error),
            })
    stable_rows = sorted(rows, key=lambda value: value["input_id"])
    result = {
        "schema_version": "v3.5-b-f1a-gold-free-stress-dry-run-v1",
        "runner_version": RUNNER_VERSION,
        "development_gold_semantic_accessed": False,
        "input_count": len(case_ids),
        "runtime_output_count": len(rows),
        "legal_terminal_count": sum(row["legal_terminal"] for row in rows),
        "invalid_terminal_count": sum(not row["legal_terminal"] for row in rows),
        "evidence_contract_error_count": len(evidence_errors),
        "evidence_contract_errors": evidence_errors,
        "source_unverifiable_count": sum(
            row["terminal"]["status"] == "source_unverifiable" for row in rows
        ),
        "candidate_count_total": sum(row["candidate_count"] for row in rows),
        "maximum_swap_count_per_query": max(
            (row["swap_count"] for row in rows), default=0,
        ),
        "outputs": stable_rows,
        "output_hash_root": stable_identity(stable_rows),
        "status": "complete" if (
            len(rows) == len(case_ids)
            and all(row["legal_terminal"] for row in rows)
            and not evidence_errors
        ) else "invalid",
    }
    write_json(OUT / "f1a_gold_free_stress_dry_run.json", result)
    return result


def _mapping(record: Mapping[str, Any]) -> Mapping[str, Any]:
    for key in ("canonical_adjudication", "adjudication", "decision"):
        value = record.get(key)
        if isinstance(value, Mapping):
            return value
    return record


def _list_at(record: Mapping[str, Any], keys: Sequence[str]) -> list[dict[str, Any]]:
    for source in (record, _mapping(record)):
        for key in keys:
            value = source.get(key)
            if isinstance(value, list):
                return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def _groups_and_spans(record: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    spans = _list_at(record, ("evidence_spans", "gold_spans", "spans"))
    span_by_id = {
        str(span.get("span_id") or span.get("evidence_span_id") or span.get("id")): span
        for span in spans
    }
    groups = _list_at(
        record,
        ("acceptable_evidence_groups", "evidence_groups", "gold_groups", "groups"),
    )
    normalized = []
    for index, group in enumerate(groups):
        required = group.get("required_spans")
        if not isinstance(required, list):
            ids = (
                group.get("required_span_ids")
                or group.get("evidence_span_ids")
                or group.get("span_ids")
                or []
            )
            required = [span_by_id[str(value)] for value in ids if str(value) in span_by_id]
        normalized.append({
            **group,
            "group_id": str(
                group.get("group_id") or group.get("evidence_group_id")
                or group.get("id") or f"group_{index + 1}"
            ),
            "required_spans": [dict(value) for value in required if isinstance(value, Mapping)],
        })
    return normalized, span_by_id


def _span_segments(span: Mapping[str, Any]) -> set[str]:
    for key in (
        "segment_ids", "physical_segment_ids", "required_segment_ids",
        "source_segment_ids",
    ):
        value = span.get(key)
        if isinstance(value, list):
            return {str(item) for item in value}
    return set()


def _span_id(span: Mapping[str, Any]) -> str:
    return str(
        span.get("span_id") or span.get("evidence_span_id")
        or span.get("id") or stable_identity(span)
    )


def _aspect_ids(span: Mapping[str, Any]) -> set[str]:
    for key in ("aspect_ids", "required_aspect_ids", "material_aspect_ids"):
        value = span.get(key)
        if isinstance(value, list):
            return {str(item) for item in value}
    for key in ("aspect_id", "required_aspect_id", "material_aspect_id"):
        if span.get(key) is not None:
            return {str(span[key])}
    return set()


def _material_aspects(
    evidence: Mapping[str, Any], sufficiency: Mapping[str, Any],
    spans: Mapping[str, Mapping[str, Any]],
) -> set[str]:
    for source in (sufficiency, _mapping(sufficiency), evidence, _mapping(evidence)):
        for key in (
            "material_aspect_ids", "required_material_aspect_ids",
            "required_aspects", "material_aspects",
        ):
            value = source.get(key)
            if isinstance(value, list):
                return {
                    str(item.get("aspect_id") or item.get("id"))
                    if isinstance(item, Mapping) else str(item)
                    for item in value
                }
    return set().union(*(_aspect_ids(span) for span in spans.values())) if spans else set()


def score_development() -> dict[str, Any]:
    seal = assert_sealed()
    existing_output = OUT / "f1a_after_metrics.json"
    if existing_output.exists():
        raise RuntimeError("Development scored output already exists")
    config = builder_config()
    source_resolver = resolver()
    runtime_rows = []
    candidate_sets: dict[str, Any] = {}
    bundles: dict[str, Any] = {}
    for query_id in P8_QUERY_IDS:
        trace_path = P8 / f"blind_run/product_initial_baseline.traces/{query_id}.trace.json"
        trace = load(trace_path)
        search = trace["search_candidate_set"]
        query = query_text(trace)
        candidates, bundle, elapsed_ms, swaps = candidate_runtime(
            query_id, query, search, source_resolver, config,
        )
        candidate_sets[query_id] = candidates
        bundles[query_id] = bundle
        runtime_rows.append({
            "query_id": query_id,
            "query": query,
            "candidate_count": len(candidates.candidates),
            "invalid_candidate_count": sum(
                candidate.normalization_status != "valid"
                or bool(candidate.validation_errors)
                for candidate in candidates.candidates
            ),
            "latency_ms": elapsed_ms,
            "candidate_set": candidates.as_dict(),
            "bundle": bundle.as_dict() if bundle else None,
            "swap": swaps,
        })
        write_json(
            OUT / f"f1a_swap_traces/{query_id}.json",
            {"query_id": query_id, **swaps},
        )

    gold_opened_at = time.time()
    layers = {
        name: {str(row["query_id"]): row for row in load_jsonl(path)}
        for name, path in DEVELOPMENT_GOLD_PATHS.items()
    }
    scored = []
    for runtime in runtime_rows:
        query_id = runtime["query_id"]
        evidence = layers["evidence"][query_id]
        sufficiency = layers["sufficiency"][query_id]
        case_status = layers["case_status"][query_id]
        groups, spans = _groups_and_spans(evidence)
        available = set().union(*(
            set(candidate.segment_ids)
            for candidate in candidate_sets[query_id].candidates
        )) if candidate_sets[query_id].candidates else set()
        selected_candidates = [
            candidate for candidate in candidate_sets[query_id].candidates
            if bundles[query_id] is not None
            and candidate.candidate_id in bundles[query_id].candidate_ids
        ]
        selected_available = set().union(*(
            set(candidate.segment_ids) for candidate in selected_candidates
        )) if selected_candidates else set()
        covered_spans = {
            _span_id(span)
            for span in spans.values()
            if _span_segments(span) and _span_segments(span).issubset(available)
        }
        selected_spans = {
            _span_id(span)
            for span in spans.values()
            if _span_segments(span) and _span_segments(span).issubset(selected_available)
        }

        def group_hits(segment_ids: set[str]) -> list[str]:
            return [
                str(group["group_id"]) for group in groups
                if group["required_spans"] and all(
                    _span_segments(span)
                    and _span_segments(span).issubset(segment_ids)
                    for span in group["required_spans"]
                )
            ]

        hits = group_hits(available)
        selected_hits = group_hits(selected_available)
        aspects = _material_aspects(evidence, sufficiency, spans)
        covered_aspects = set().union(*(
            _aspect_ids(span) for span in spans.values()
            if _span_id(span) in covered_spans
        )) if spans else set()
        status_source = _mapping(sufficiency)
        sufficiency_status = str(
            status_source.get("final_status")
            or status_source.get("status")
            or status_source.get("sufficiency_status")
            or ""
        )
        review_source = _mapping(case_status)
        source_reviewable = str(
            review_source.get("authoritative_source_reviewable")
            if "authoritative_source_reviewable" in review_source
            else review_source.get("review_status", "")
        ).casefold() not in {"false", "unreviewable", "source_unverifiable"}
        builder_denominator = query_id != "PQS_V1_Q017"
        primary_failure_eligible = (
            builder_denominator and query_id != "PQS_V1_Q014"
        )
        scored.append({
            **{key: value for key, value in runtime.items() if key != "candidate_set"},
            "complete_group_hit": bool(hits),
            "covered_group_ids": hits,
            "selected_bundle_hit": bool(selected_hits),
            "selected_group_ids": selected_hits,
            "covered_span_ids": sorted(covered_spans),
            "covered_aspect_ids": sorted(covered_aspects),
            "required_span_recall": (
                len(covered_spans) / len(spans) if spans else 0.0
            ),
            "required_aspect_coverage": (
                len(covered_aspects & aspects) / len(aspects) if aspects else 0.0
            ),
            "eligible_for_builder_denominator": builder_denominator,
            "eligible_for_primary_failure": primary_failure_eligible,
            "source_reviewable": source_reviewable,
            "sufficiency_status": sufficiency_status,
        })
    eligible = [row for row in scored if row["eligible_for_builder_denominator"]]
    complete = sum(row["complete_group_hit"] for row in eligible)
    primary_failures = sum(
        not row["complete_group_hit"] for row in scored
        if row["eligible_for_primary_failure"]
    )
    all_candidates = [
        candidate
        for value in candidate_sets.values()
        for candidate in value.candidates
    ]
    swap_counts = [int(row["swap"]["swap_count"]) for row in scored]
    after = {
        "schema_version": "v3.5-b-f1a-after-v1",
        "builder_version": config.config_id,
        "implementation_freeze_seal_sha256": digest(
            OUT / "f1a_implementation_freeze_seal.json"
        ),
        "development_scored_run_count": 1,
        "development_gold_opened_after_implementation_freeze": True,
        "development_gold_opened_at_epoch": gold_opened_at,
        "development_gold_hashes": {
            name: digest(path) for name, path in DEVELOPMENT_GOLD_PATHS.items()
        },
        "eligible_builder_queries": len(eligible),
        "complete_group_coverage": {
            "numerator": complete,
            "denominator": len(eligible),
            "rate": complete / len(eligible),
        },
        "builder_primary_failures": primary_failures,
        "required_span_recall": mean(
            row["required_span_recall"] for row in eligible
        ),
        "required_aspect_coverage": mean(
            row["required_aspect_coverage"] for row in eligible
        ),
        "candidate_count_total": len(all_candidates),
        "invalid_candidate_count": sum(
            candidate.normalization_status != "valid"
            or bool(candidate.validation_errors)
            for candidate in all_candidates
        ),
        "mean_window_seconds": mean(
            candidate.end_time - candidate.start_time
            for candidate in all_candidates
        ),
        "builder_latency_ms": {
            "mean": mean(row["latency_ms"] for row in scored),
            "max": max(row["latency_ms"] for row in scored),
            "min": min(row["latency_ms"] for row in scored),
        },
        "swap_count": {
            "total": sum(swap_counts),
            "mean": mean(swap_counts),
            "max": max(swap_counts),
            "zero_swap_query_count": sum(value == 0 for value in swap_counts),
        },
        "existing_six_regressions": sorted(
            query_id for query_id in EXISTING_SIX
            if not next(
                row["complete_group_hit"] for row in scored
                if row["query_id"] == query_id
            )
        ),
        "runtime_retrieval_calls": 0,
        "runtime_embedding_calls": 0,
        "runtime_llm_calls": 0,
        "frozen_gold_opened": False,
        "seal_builder_version": seal["builder_version"],
    }
    write_jsonl(OUT / "f1a_after_per_query.jsonl", scored)
    write_json(OUT / "f1a_after_metrics.json", after)
    return after


def score_stress() -> dict[str, Any]:
    assert_sealed()
    if not (OUT / "f1a_after_metrics.json").is_file():
        raise RuntimeError("Development scored run must finish before Stress")
    output = OUT / "f1a_stress_regression.json"
    if output.exists():
        raise RuntimeError("Stress scored output already exists")
    config = builder_config()
    source_resolver = resolver()
    case_ids = load(STRESS / "input_freeze/evidence_bearing_case_ids.json")["case_ids"]
    gold = {row["case_id"]: row for row in load_jsonl(STRESS_SCORING)}
    runtime = {row["case_id"]: row for row in load_jsonl(STRESS_RUNTIME)}
    bridge = {
        (row["case_id"], row["gold_segment_id"]): row["physical_segment_id"]
        for row in load_jsonl(STRESS_BRIDGE)
    }
    rows = []
    for case_id in case_ids:
        search = load(STRESS / f"execution/cases/{case_id}/search_candidate_set.json")
        query = str(runtime[case_id]["original_query"])
        candidates, bundle, elapsed_ms, swaps = candidate_runtime(
            case_id, query, search, source_resolver, config,
        )
        physical_groups = _physical_groups(
            case_id, gold[case_id]["evidence_groups"], bridge,
        )
        candidate_values = [candidate.as_dict() for candidate in candidates.candidates]
        selected = [
            candidate.as_dict() for candidate in candidates.candidates
            if bundle is not None and candidate.candidate_id in bundle.candidate_ids
        ]
        complete = _complete_groups(physical_groups, candidate_values)
        selected_complete = _complete_groups(physical_groups, selected)
        rows.append({
            "case_id": case_id,
            "candidate_count": len(candidate_values),
            "invalid_candidate_count": sum(
                candidate.normalization_status != "valid"
                or bool(candidate.validation_errors)
                for candidate in candidates.candidates
            ),
            "complete_group_hit": bool(complete),
            "covered_group_ids": complete,
            "selected_bundle_hit": bool(selected_complete),
            "latency_ms": elapsed_ms,
            "swap": swaps,
        })
        write_json(
            OUT / f"f1a_swap_traces/stress_{case_id}.json",
            {"case_id": case_id, **swaps},
        )
    complete = sum(row["complete_group_hit"] for row in rows)
    result = {
        "schema_version": "v3.5-b-f1a-stress-regression-v1",
        "stress_scored_run_count": 1,
        "optimization_authority": False,
        "evidence_bearing_cases": len(rows),
        "complete_group_coverage": {
            "numerator": complete,
            "denominator": len(rows),
            "rate": complete / len(rows),
        },
        "candidate_count_total": sum(row["candidate_count"] for row in rows),
        "invalid_candidate_count": sum(
            row["invalid_candidate_count"] for row in rows
        ),
        "builder_latency_ms": {
            "mean": mean(row["latency_ms"] for row in rows),
            "max": max(row["latency_ms"] for row in rows),
            "min": min(row["latency_ms"] for row in rows),
        },
        "swap_count": {
            "total": sum(row["swap"]["swap_count"] for row in rows),
            "mean": mean(row["swap"]["swap_count"] for row in rows),
            "max": max(row["swap"]["swap_count"] for row in rows),
            "zero_swap_case_count": sum(
                row["swap"]["swap_count"] == 0 for row in rows
            ),
        },
        "runtime_retrieval_calls": 0,
        "runtime_embedding_calls": 0,
        "runtime_llm_calls": 0,
        "frozen_gold_opened": False,
        "per_case": rows,
    }
    write_json(output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "phase",
        choices=("dry-development", "dry-stress", "development", "stress"),
    )
    args = parser.parse_args()
    actions = {
        "dry-development": dry_development,
        "dry-stress": dry_stress,
        "development": score_development,
        "stress": score_stress,
    }
    result = actions[args.phase]()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
