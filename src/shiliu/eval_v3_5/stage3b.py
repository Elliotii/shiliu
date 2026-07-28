from __future__ import annotations

from dataclasses import asdict, replace
import csv
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
from typing import Any, Mapping

from shiliu.evidence.stage3a import (
    CANDIDATE_GENERATION_POLICY_STAGE3B,
    CandidateBuilderConfig,
    EvidenceCandidateSet,
    SelectorConfig,
    resolve_from_search_candidates,
    build_within_video_candidates,
    select_deterministic_bundle,
)
from shiliu.evidence.stage3b import (
    STRUCTURED_SELECTOR_CONTRACT_VERSION,
    STRUCTURED_SELECTOR_PROMPT_VERSION,
    StructuredProvider,
    StructuredSelectorConfig,
    StructuredSelectorError,
    StructuredSelectorOutput,
    build_structured_selector_prompt,
    select_structured_evidence_bundle,
)
from shiliu.eval_v3_5.isolation import HeldoutAccessGuard
from shiliu.eval_v3_5.stage3a import (
    EXPECTED_ARTIFACT_HASH,
    EXPECTED_GOLD_HASH,
    EXPECTED_MANIFEST_HASH,
    EXPECTED_SNAPSHOT_HASH,
    FrozenRawSourceResolver,
    _case_metrics,
    bundle_hits_group,
    file_sha256,
    load_jsonl,
    validate_search_candidate_set,
)


STAGE3B_RUNNER_VERSION = "v3.5-stage3b-development-runner-v1"
EVIDENCE_CASE_IDS = ("CASE_001", "CASE_002", "CASE_003", "CASE_005")


def final_builder_config() -> CandidateBuilderConfig:
    return CandidateBuilderConfig(
        config_id="stage3b-acronym-w3.5-v1",
        within_video_max_candidates=32,
        candidate_generation_policy_version=CANDIDATE_GENERATION_POLICY_STAGE3B,
        asr_acronym_anchor_enabled=True,
        acronym_anchor_weight=3.5,
    )


def _safe_hash(path: Path, guard: HeldoutAccessGuard) -> str:
    return file_sha256(guard.validate_path(path))


def run_stage3b_development(
    *, repository_root: Path, manifest_path: Path, development_gold_path: Path,
    artifact_manifest_path: Path, snapshot_db_path: Path, provider: StructuredProvider,
    builder_config: CandidateBuilderConfig | None = None,
    structured_config: StructuredSelectorConfig | None = None,
) -> dict[str, Any]:
    """Predict and freeze CandidateSets before the Development runner opens Gold."""

    guard = HeldoutAccessGuard(repository_root)
    identities = {
        "development_execution_manifest_sha256": _safe_hash(manifest_path, guard),
        "artifact_manifest_sha256": _safe_hash(artifact_manifest_path, guard),
        "snapshot_database_sha256": _safe_hash(snapshot_db_path, guard),
    }
    expected_pre_prediction = {
        "development_execution_manifest_sha256": EXPECTED_MANIFEST_HASH,
        "artifact_manifest_sha256": EXPECTED_ARTIFACT_HASH,
        "snapshot_database_sha256": EXPECTED_SNAPSHOT_HASH,
    }
    if identities != expected_pre_prediction:
        raise RuntimeError(f"frozen pre-prediction identity mismatch: {identities}")
    manifest = load_jsonl(guard.read_text(manifest_path))
    records = {str(value["case_id"]): value for value in manifest}
    resolver = FrozenRawSourceResolver(
        artifact_manifest=artifact_manifest_path, snapshot_db=snapshot_db_path, guard=guard,
    )
    builder = builder_config or final_builder_config()
    deterministic_config = SelectorConfig()
    llm_config = structured_config or StructuredSelectorConfig()

    frozen: dict[str, dict[str, dict[str, Any]]] = {"track_a": {}, "track_b": {}}
    for case_id in EVIDENCE_CASE_IDS:
        record = records[case_id]
        validate_search_candidate_set(record)
        query = str(record["original_query"])
        candidate_a = resolve_from_search_candidates(
            query, record["search_candidates"], resolver, builder,
            query_id=str(record["query_id"]),
            search_candidate_set_id=str(record["search_candidate_set_id"]),
            execution_manifest_identity=EXPECTED_MANIFEST_HASH,
        )
        target = int(record["target_video_id"])
        artifact = resolver(target)
        candidate_b = build_within_video_candidates(
            query, target, artifact.source_version, artifact, builder,
            query_id=str(record["query_id"]),
        )
        for track, candidate_set in (("track_a", candidate_a), ("track_b", candidate_b)):
            # A single uniform input-pool cap is applied before Gold is opened. This
            # makes Track A obey the same global 32-Candidate contract as Track B.
            if len(candidate_set.candidates) > llm_config.max_candidates:
                candidate_set = replace(
                    candidate_set,
                    candidates=candidate_set.candidates[:llm_config.max_candidates],
                    trace={**candidate_set.trace, "stage3b_global_candidate_pool_cap": llm_config.max_candidates},
                )
            frozen[track][case_id] = {
                "candidate_set": candidate_set,
                "deterministic_bundle": select_deterministic_bundle(query, candidate_set, deterministic_config),
                "candidate_set_hash": sha256(json.dumps(
                    candidate_set.as_dict(), ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"),
                ).encode()).hexdigest(),
            }

    # Gold is first opened here: every CandidateSet, ID, ordering, budget and deterministic
    # prediction above is already frozen, and the selector receives none of these fields.
    identities["development_gold_sha256"] = _safe_hash(development_gold_path, guard)
    if identities["development_gold_sha256"] != EXPECTED_GOLD_HASH:
        raise RuntimeError("Development Gold identity mismatch")
    gold = {str(value["case_id"]): value for value in load_jsonl(guard.read_text(development_gold_path))}

    calls = 0
    provider_metrics: list[dict[str, Any]] = []
    traces: dict[str, Any] = {}
    tracks: dict[str, Any] = {}
    for track in ("track_a", "track_b"):
        rows: list[dict[str, Any]] = []
        for case_id in EVIDENCE_CASE_IDS:
            record = records[case_id]
            item = frozen[track][case_id]
            candidate_set: EvidenceCandidateSet = item["candidate_set"]
            deterministic_bundle = item["deterministic_bundle"]
            baseline = _case_metrics(gold[case_id], candidate_set, deterministic_bundle)
            eligible = bool(baseline["candidate_builder_case_covered"])
            structured = None
            selector_error = None
            if eligible:
                calls += 1
                if calls > 10:
                    raise RuntimeError("logical selector request budget exceeded")
                try:
                    structured = select_structured_evidence_bundle(
                        str(record["original_query"]), candidate_set, provider, llm_config,
                    )
                    provider_metrics.append({
                        "evaluation_track": track,
                        "case_correlation_id": case_id,
                        "request_hash": structured.request_hash,
                        "candidate_set_hash": structured.candidate_set_hash,
                        "response_hash": structured.response_hash,
                        **structured.metrics,
                    })
                except StructuredSelectorError as exc:
                    selector_error = exc.code
                    provider_metrics.append({
                        "evaluation_track": track, "case_correlation_id": case_id,
                        "error": exc.code, **exc.metrics,
                    })
            structured_bundle = structured.bundle if structured else None
            structured_hit = any(
                bundle_hits_group(group, structured_bundle, candidate_set.candidates)
                for group in gold[case_id].get("gold_evidence_groups", [])
            ) if structured else False
            structured_metrics = _case_metrics(gold[case_id], candidate_set, structured_bundle) if structured else {}
            target = record.get("target_video_id")
            search = record["search_candidates"]
            reachable = target is not None and any(
                value.get("video_id") == target
                for value in list(search.get("raw_unit_candidates", [])) + list(search.get("video_candidates", []))
            )
            failure = None
            if track == "track_a" and not reachable:
                failure = "upstream_retrieval_failure"
            elif not eligible:
                failure = "candidate_generation_failure"
            elif selector_error:
                failure = selector_error
            elif not structured_hit:
                failure = "selector_failure"
            row = {
                "case_id": case_id,
                "evaluation_track": "frozen_v3_end_to_end" if track == "track_a" else "oracle_video_conditional",
                "end_to_end_claim_eligible": track == "track_a",
                "target_video_reachable": reachable if track == "track_a" else True,
                "selector_eligible": eligible,
                "candidate_count": baseline["candidate_count"],
                "candidate_character_budget": baseline["candidate_character_budget"],
                "candidate_builder_case_covered": baseline["candidate_builder_case_covered"],
                "complete_gold_groups_covered": baseline["complete_gold_groups_covered"],
                "required_spans_covered": baseline["required_spans_covered"],
                "required_span_count": baseline["required_span_count"],
                "deterministic_bundle_hit_at_1": baseline["deterministic_bundle_hit_at_1"],
                "structured_llm_bundle_hit_at_1": structured_hit if eligible and not selector_error else None,
                "structured_output_valid": structured is not None,
                "repair_used": structured.metrics["repair_used"] if structured else None,
                "abstained": structured.output.action == "abstain" if structured else None,
                "selected_candidate_count": len(structured_bundle.candidate_ids) if structured_bundle else 0,
                "predicted_union_duration": structured_bundle.union_duration if structured_bundle else 0.0,
                "median_start_time_error": structured_metrics.get("median_start_time_error"),
                "duration_ratio": structured_metrics.get("predicted_gold_union_duration_ratio"),
                "deterministic_bundle_id": deterministic_bundle.bundle_id if deterministic_bundle else None,
                "structured_bundle_id": structured_bundle.bundle_id if structured_bundle else None,
                "selector_error": selector_error,
                "failure_attribution": failure,
            }
            rows.append(row)
            traces[f"{case_id}.{track}"] = {
                "evaluation_track": row["evaluation_track"],
                "case_correlation_id": case_id,
                "query_identity": str(record["query_id"]),
                "candidate_builder_policy_version": builder.candidate_generation_policy_version,
                "candidate_set_identity": item["candidate_set_hash"],
                "candidate_count": len(candidate_set.candidates),
                "candidate_budget": sum(value.character_count for value in candidate_set.candidates),
                "candidate_ids": [value.candidate_id for value in candidate_set.candidates],
                "selector_type": "structured_llm" if eligible else "not_eligible",
                "selector_contract_version": STRUCTURED_SELECTOR_CONTRACT_VERSION,
                "prompt_version": STRUCTURED_SELECTOR_PROMPT_VERSION,
                "model_identity": provider.model,
                "request_hash": structured.request_hash if structured else None,
                "response_hash": structured.response_hash if structured else None,
                "selected_candidate_ids": structured.output.selected_candidate_ids if structured else [],
                "abstain": structured.output.action == "abstain" if structured else None,
                "schema_validation": "valid" if structured else selector_error or "not_eligible",
                "repair_attempt": structured.metrics["repair_used"] if structured else None,
                "reconstructed_bundle_id": structured_bundle.bundle_id if structured_bundle else None,
                "raw_normalization_result": structured_bundle.normalization_status if structured_bundle else None,
                "gold_after_prediction": {
                    "hit": structured_hit if structured else None,
                    "failure_attribution": failure,
                },
            }
        eligible_rows = [value for value in rows if value["selector_eligible"]]
        valid_rows = [value for value in eligible_rows if value["structured_output_valid"]]
        tracks[track] = {
            "summary": {
                "case_count": len(rows),
                "selector_eligible_case_count": len(eligible_rows),
                "valid_structured_output_count": len(valid_rows),
                "invalid_output_count": len(eligible_rows) - len(valid_rows),
                "repair_count": sum(bool(value["repair_used"]) for value in valid_rows),
                "abstention_count": sum(bool(value["abstained"]) for value in valid_rows),
                "deterministic_hit_at_1": sum(bool(value["deterministic_bundle_hit_at_1"]) for value in eligible_rows),
                "structured_llm_hit_at_1": sum(bool(value["structured_llm_bundle_hit_at_1"]) for value in eligible_rows),
                "absolute_hit_delta": sum(bool(value["structured_llm_bundle_hit_at_1"]) for value in eligible_rows) - sum(bool(value["deterministic_bundle_hit_at_1"]) for value in eligible_rows),
                "median_selected_candidate_count": median(value["selected_candidate_count"] for value in valid_rows) if valid_rows else None,
                "median_predicted_union_duration": median(value["predicted_union_duration"] for value in valid_rows) if valid_rows else None,
            },
            "per_case": rows,
        }
    raw_attempt_count = sum(
        int(value.get("attempt_count", len(value.get("attempts", []))))
        for value in provider_metrics
    )
    if raw_attempt_count > 20:
        raise RuntimeError("raw Provider attempt budget exceeded")
    return {
        "runner_version": STAGE3B_RUNNER_VERSION,
        "input_identities": identities,
        "builder_config": asdict(builder),
        "deterministic_selector_config": asdict(deterministic_config),
        "structured_selector_config": asdict(llm_config),
        "model_identity": provider.model,
        "provider_abstraction": provider.name,
        "logical_call_count": calls,
        "raw_attempt_count": raw_attempt_count,
        "track_a": tracks["track_a"],
        "track_b": tracks["track_b"],
        "provider_metrics": provider_metrics,
        "traces": traces,
        "heldout_access_audit": guard.audit_record(
            source_files_scanned=[
                "src/shiliu/evidence/stage3a.py", "src/shiliu/evidence/stage3b.py",
                "src/shiliu/eval_v3_5/isolation.py", "src/shiliu/eval_v3_5/stage3b.py",
            ],
            test_files_scanned=["tests/test_v3_5_stage3b_selector.py"],
        ),
    }


def write_stage3b_artifacts(result: Mapping[str, Any], *, output_directory: Path) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)
    traces = output_directory / "trace_samples"
    traces.mkdir(exist_ok=True)

    def write_json(name: str, value: object) -> None:
        (output_directory / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )

    write_json("candidate_robustness_config.json", result["builder_config"])
    write_json("candidate_robustness_tuning.dev.json", {
        "experiment_limit": "baseline_plus_two_generic_configurations",
        "experiments": [
            {"config_id": "stage3a-builder-32-v1", "acronym_anchor_weight": 0.0, "complete_group_coverage": "3/4", "required_span_coverage": "6/7", "selected": False},
            {"config_id": "stage3b-acronym-w2.5-v1", "acronym_anchor_weight": 2.5, "complete_group_coverage": "3/4", "required_span_coverage": "6/7", "selected": False},
            {"config_id": "stage3b-acronym-w3.5-v1", "acronym_anchor_weight": 3.5, "complete_group_coverage": "3/4", "required_span_coverage": "6/7", "selected": True},
        ],
        "selection_reason": "No coverage gain; stronger bounded generic anchor retained as the frozen negative robustness result. No further Builder tuning was performed.",
    })
    write_json("structured_selector_contract.json", StructuredSelectorOutput.model_json_schema())
    (output_directory / "structured_selector_prompt.md").write_text(
        "# Structured Fine Selector Prompt\n\n```text\n" + build_structured_selector_prompt(
            "<Original Query>", (), StructuredSelectorConfig(),
        ) + "```\n", encoding="utf-8",
    )
    write_json("structured_selector_config.json", result["structured_selector_config"])
    write_json("provider_config.redacted.json", {
        "provider_abstraction": result["provider_abstraction"], "model_identity": result["model_identity"],
        "thinking_configuration": "high", "api_key": "redacted", "cost_pricing": "unavailable",
    })
    write_json("stage3b_run_manifest.json", {
        "runner_version": result["runner_version"], "input_identities": result["input_identities"],
        "builder_config": result["builder_config"],
        "structured_selector_config": result["structured_selector_config"],
        "model_identity": result["model_identity"],
        "logical_call_count": result.get("logical_call_count_cumulative", result["logical_call_count"]),
        "raw_attempt_count": result.get("raw_attempt_count_cumulative", result["raw_attempt_count"]),
        "final_config_logical_call_count": result["logical_call_count"],
        "final_config_raw_attempt_count": result["raw_attempt_count"],
        "evaluation_scope": "development_only",
        "heldout_executed": False,
    })
    write_json("selector_tuning_history.dev.json", {
        "variants": [
            {
                "config_id": "stage3b-structured-selector-full-v1",
                "candidate_pool": "unbounded Track A / bounded Track B",
                "max_output_tokens": 2048,
                "result": "Track A rejected locally above 32 Candidates; three Track B calls exhausted repair with invalid_json.",
                "logical_calls": 5, "raw_attempts": 6, "selected": False,
            },
            {
                "config_id": result["structured_selector_config"]["config_id"],
                "candidate_pool": "uniform top 32 frozen before Gold access",
                "max_output_tokens": result["structured_selector_config"]["max_output_tokens"],
                "result": "3/5 valid only after repair; 2/5 repair exhausted; 0 hits.",
                "logical_calls": 5, "raw_attempts": 10, "selected": True,
            },
        ],
        "variant_count": 2, "candidate_pool_configuration_count": 2,
        "cumulative_logical_calls": 10, "cumulative_raw_attempts": 16,
        "stop_condition": "invalid after one repair in 40% of final-config logical calls (>25%)",
    })
    write_json("track_a_structured_selector_eval.dev.json", result["track_a"])
    write_json("track_b_candidate_builder_eval.dev.json", {
        "summary": {
            "complete_case_coverage": sum(bool(value["candidate_builder_case_covered"]) for value in result["track_b"]["per_case"]),
            "case_count": 4,
            "required_span_coverage": sum(int(value["required_spans_covered"]) for value in result["track_b"]["per_case"]),
            "required_span_count": sum(int(value["required_span_count"]) for value in result["track_b"]["per_case"]),
        },
        "per_case": result["track_b"]["per_case"],
    })
    write_json("track_b_selector_comparison.dev.json", result["track_b"])
    write_json("provider_call_metrics.dev.json", result["provider_metrics"])
    write_json("heldout_access_audit.json", result["heldout_access_audit"])
    for name, value in result["traces"].items():
        write_json(f"trace_samples/{name}.json", value)
    for track, name in (("track_a", "track_a_per_case.dev.csv"), ("track_b", "track_b_per_case.dev.csv")):
        rows = result[track]["per_case"]
        fields = sorted({key for row in rows for key in row})
        with (output_directory / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    failures = ["# Stage 3B Development Failures", ""]
    for track in ("track_a", "track_b"):
        failures.extend([f"## {track.replace('_', ' ').title()}", ""])
        failures.extend(
            f"- {row['case_id']}: `{row['failure_attribution']}`"
            for row in result[track]["per_case"] if row["failure_attribution"]
        )
        failures.append("")
    (output_directory / "failure_cases.dev.md").write_text("\n".join(failures), encoding="utf-8")
    (output_directory / "functional_examples.md").write_text(
        "# Stage 3B Functional Examples\n\n"
        "- Generic acronym policy: an uppercase 2–8 character query token is compacted, compared case-insensitively to compact subtitle tokens, and a generic equal-length one-substitution anchor can retain its bounded local window. No correction dictionary exists.\n"
        "- CASE_001 regression, CASE_002 comparison, CASE_003 negative robustness result, and CASE_005 complementary selection are recorded in the per-case and trace assets.\n"
        "- Invalid output fixtures cover unknown/duplicate IDs, invalid actions, extra fields, malformed JSON, timeout/failure, one repair success, and repair exhaustion.\n"
        "- Reconstruction maps returned IDs back to immutable Candidates, sorts locally, restores Raw-derived text/time, computes interval-union duration, and hashes a stable Bundle ID.\n",
        encoding="utf-8",
    )
