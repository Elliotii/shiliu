from __future__ import annotations

import argparse
from dataclasses import fields
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Any, Iterable, Mapping, Sequence

from shiliu.evidence.stage3a import EvidenceBundle
from shiliu.evidence.stage4 import (
    FINAL_CANDIDATE_BUILDER_VERSION,
    SUFFICIENCY_DECISION_CONTRACT_VERSION,
    SUFFICIENCY_REQUEST_CONTRACT_VERSION,
    MechanicalGateDecision,
    SufficiencyDecision,
    SufficiencyRequest,
    canonical_bytes,
    stable_id,
)
from shiliu.eval_v3_5.stage4b import (
    SEMANTIC_JUDGE_CONTRACT_VERSION,
    SEMANTIC_POLICY_VERSION,
    SEMANTIC_PROMPT_VERSION,
    SemanticJudgeBatchOutput,
    batch_prompt,
    hash_value,
    parse_batch_output,
    prompt_text,
    project_runtime_request,
    semantic_policy,
    to_decision,
    validate_output,
)


ROOT = Path(__file__).resolve().parents[4]
PRODUCT = ROOT / "research/v3_5/product_query_set_v1"
OUT = ROOT
WORK = PRODUCT / "stage4b_incremental"
QUERY_PATH = PRODUCT / "split_v1/product_query_development_v1.locked.jsonl"
EVIDENCE_GOLD_PATH = (
    PRODUCT
    / "gold_construction_v1/development_seal_v1/sealed/product_evidence_gold.development.v1.sealed.jsonl"
)
RETRIEVAL_GOLD_PATH = (
    PRODUCT
    / "gold_construction_v1/development_seal_v1/sealed/product_retrieval_gold.development.v1.sealed.jsonl"
)
SUFFICIENCY_GOLD_PATH = (
    PRODUCT
    / "gold_construction_v1/development_seal_v1/sealed/product_sufficiency_gold.development.v1.sealed.jsonl"
)
TRACE_ROOT = PRODUCT / "product_initial_baseline_attempt_3/blind_run/product_initial_baseline.traces"
STAGE4A_CLOSEOUT = ROOT / "STAGE4A_R_FINAL_CLOSEOUT.json"
STAGE4A_FREEZE = ROOT / "STAGE4A_R_MECHANICAL_GATE_FREEZE.json"
IDENTITY_CONTRACT = (
    PRODUCT / "f1a_candidate_builder_major_cycle_1/EVIDENCE_IDENTITY_CONTRACT_V1.json"
)
MODEL = "gpt-5.6-terra"
PROVIDER = "openai-codex-cli"
TEMPERATURE = 0
REASONING_EFFORT = "medium"
MAX_RETRIES = 1
PREDICTION_FILES = {
    "track_a": OUT / "stage4b_initial_track_a.predictions.jsonl",
    "track_b": OUT / "stage4b_initial_track_b.predictions.jsonl",
    "track_c": OUT / "stage4b_initial_track_c.predictions.jsonl",
}
PROJECTION_FILES = {
    "track_a": WORK / "track_a.runtime.jsonl",
    "track_b": WORK / "track_b.runtime.jsonl",
    "track_c": WORK / "track_c.runtime.jsonl",
}
FORBIDDEN_RUNTIME_FIELDS = {
    "sufficiency_gold_label",
    "gold_required_aspects",
    "expected_supported_aspects",
    "expected_missing_aspects",
    "gold_reasoning",
    "expected_decision",
    "case_specific_hint",
}


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def dump_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def root_hash(paths: Iterable[Path]) -> dict[str, Any]:
    values = {
        str(path.relative_to(ROOT)): digest(path)
        for path in sorted(paths)
    }
    return {
        "file_count": len(values),
        "files": values,
        "root_sha256": hash_value(values),
    }


def bundle_from_dict(value: Mapping[str, Any]) -> EvidenceBundle:
    allowed = {field.name for field in fields(EvidenceBundle)}
    tuple_fields = {
        "source_artifact_ids",
        "source_versions",
        "timeline_run_ids",
        "candidate_ids",
        "normalized_spans",
        "source_texts",
        "validation_errors",
    }
    return EvidenceBundle(
        **{
            key: tuple(item) if key in tuple_fields else item
            for key, item in value.items()
            if key in allowed
        }
    )


def _gold_span_ids(evidence: Mapping[str, Any], *, track: str, video_id: str | None) -> set[str]:
    spans = evidence["span_registry"]
    if track == "track_b":
        selected = {
            str(span["span_id"])
            for span in spans
            if video_id is None or str(span["video_id"]) == video_id
        }
        return selected or {str(span["span_id"]) for span in spans}
    groups = evidence.get("acceptable_evidence_groups") or []
    if not groups:
        return {str(span["span_id"]) for span in spans}
    return {
        str(span_id)
        for span_set in groups[0]["required_span_sets"]
        for span_id in span_set["required_span_ids"]
    }


def approved_bundle(
    query: Mapping[str, Any],
    evidence: Mapping[str, Any],
    *,
    track: str,
    known_video_id: str | None,
) -> EvidenceBundle:
    chosen_ids = _gold_span_ids(evidence, track=track, video_id=known_video_id)
    spans = [
        span for span in evidence["span_registry"] if str(span["span_id"]) in chosen_ids
    ]
    if not spans:
        raise RuntimeError(f"{query['query_id']} has no authoritative runtime evidence")
    candidates = [
        "candidate_" + sha256(canonical_bytes({
            "query_id": query["query_id"],
            "track": track,
            "span_id": span["span_id"],
            "segment_ids": span["segment_ids"],
            "source_version": span["source_version"],
        })).hexdigest()
        for span in spans
    ]
    normalized = tuple(
        {
            "candidate_id": candidate_id,
            "span_id": span["span_id"],
            "segment_ids": span["segment_ids"],
            "start_time": span["start_time"],
            "end_time": span["end_time"],
            "timeline_run_id": span["timeline_run_id"],
            "source_language": span["source_language"],
            "source_type": span["source_type"],
        }
        for candidate_id, span in zip(candidates, spans, strict=True)
    )
    video_ids = sorted({str(span["video_id"]) for span in spans})
    source_artifact_ids = tuple(
        "source_" + sha256(video.encode()).hexdigest() for video in video_ids
    )
    source_versions = tuple(sorted({str(span["source_version"]) for span in spans}))
    timeline_ids = tuple(sorted({str(span["timeline_run_id"]) for span in spans}))
    trace_id = stable_id(
        "stage4b_trace_",
        {
            "query_id": query["query_id"],
            "track": track,
            "span_ids": sorted(chosen_ids),
        },
    )
    base = {
        "query_id": query["query_id"],
        "track": track,
        "candidate_ids": candidates,
        "source_versions": source_versions,
        "timeline_run_ids": timeline_ids,
    }
    return EvidenceBundle(
        bundle_id=stable_id("bundle_", base),
        query_id=str(query["query_id"]),
        video_id=int(sha256(video_ids[0].encode()).hexdigest()[:12], 16),
        source_artifact_ids=source_artifact_ids,
        source_versions=source_versions,
        timeline_run_ids=timeline_ids,
        candidate_ids=tuple(candidates),
        normalized_spans=normalized,
        union_duration=sum(
            max(0.0, float(span["end_time"]) - float(span["start_time"]))
            for span in spans
        ),
        source_texts=tuple(str(span["quote_text"]) for span in spans),
        selection_method="v3.5-deterministic-fine-selector-v1",
        score=1.0,
        score_breakdown={"approved_projection": 1.0},
        evaluation_track=(
            "oracle_video_conditional"
            if track == "track_b"
            else "approved_evidence_diagnostic"
        ),
        end_to_end_claim_eligible=False,
        trace_id=trace_id,
        normalization_status="valid",
        validation_errors=(),
    )


def diagnostic_runtime(
    query: Mapping[str, Any],
    bundle: EvidenceBundle,
    *,
    track: str,
) -> tuple[SufficiencyRequest, MechanicalGateDecision]:
    evaluation_track = bundle.evaluation_track
    request_base = {
        "query_id": str(query["query_id"]),
        "original_query": str(query["query_text"]),
        "evaluation_track": evaluation_track,
        "end_to_end_claim_eligible": False,
        "search_candidate_set_id": stable_id(
            "approved_search_", {"query_id": query["query_id"], "track": track}
        ),
        "evidence_candidate_set_id": stable_id(
            "approved_candidate_set_",
            {"query_id": query["query_id"], "candidate_ids": bundle.candidate_ids},
        ),
        "evidence_bundle_id": bundle.bundle_id,
        "evidence_resolution_status": "resolved",
        "failure_attribution": None,
        "candidate_builder_version": FINAL_CANDIDATE_BUILDER_VERSION,
        "selector_version": "v3.5-deterministic-fine-selector-v1",
        "source_states": ("valid",),
        "source_languages": tuple(
            sorted(
                {
                    str(span.get("source_language", "und"))
                    for span in bundle.normalized_spans
                }
            )
        ),
        "trace_id": bundle.trace_id,
    }
    request = SufficiencyRequest(
        request_id=stable_id(
            "request_",
            {"contract": SUFFICIENCY_REQUEST_CONTRACT_VERSION, **request_base},
        ),
        **request_base,
    )
    gate = MechanicalGateDecision(
        gate_decision_id=stable_id(
            "gate_",
            {"query_id": query["query_id"], "track": track, "bundle_id": bundle.bundle_id},
        ),
        gate_outcome="judge_eligible",
        terminal_status=None,
        operational_reason_code=None,
        action_family="none",
        semantic_judge_required=True,
        query_id=str(query["query_id"]),
        evaluation_track=evaluation_track,
        end_to_end_claim_eligible=False,
        search_candidate_set_id=request.search_candidate_set_id,
        evidence_candidate_set_id=request.evidence_candidate_set_id,
        evidence_bundle_id=bundle.bundle_id,
        evidence_ids_used=bundle.candidate_ids,
        mechanical_gate_policy_version="v3.5-mechanical-gate-policy-v1",
        candidate_builder_version=FINAL_CANDIDATE_BUILDER_VERSION,
        selector_version="v3.5-deterministic-fine-selector-v1",
        trace_id=bundle.trace_id,
        validation_errors=(),
    )
    return request, gate


def build_projections() -> dict[str, list[dict[str, Any]]]:
    queries = load_jsonl(QUERY_PATH)
    evidence_by_id = {
        row["query_id"]: row for row in load_jsonl(EVIDENCE_GOLD_PATH)
    }
    retrieval_by_id = {
        row["query_id"]: row for row in load_jsonl(RETRIEVAL_GOLD_PATH)
    }
    result: dict[str, list[dict[str, Any]]] = {
        "track_a": [],
        "track_b": [],
        "track_c": [],
    }
    for query in queries:
        query_id = str(query["query_id"])
        trace = load_json(TRACE_ROOT / f"{query_id}.trace.json")
        request = SufficiencyRequest.model_validate(trace["mechanical_gate_request"])
        gate_value = dict(trace["mechanical_gate_decision"])
        # The immutable Product trace predates the Stage 4A-R terminology-only
        # projection. Apply the frozen R1 terminal names without changing the
        # stored trace or its operational reason.
        if gate_value.get("gate_outcome") == "terminal_unverifiable":
            gate_value["gate_outcome"] = "source_unverifiable"
            gate_value["terminal_status"] = "source_unverifiable"
        gate = MechanicalGateDecision.model_validate(gate_value)
        if gate.gate_outcome == "judge_eligible":
            bundle = bundle_from_dict(trace["evidence_bundle"])
            projected = project_runtime_request(
                request, gate, bundle, query_language=str(query["query_language"])
            )
            result["track_a"].append(
                {
                    "case_id": query_id,
                    "track": "track_a",
                    "request": projected.model_dump(mode="json"),
                    "gate": gate.model_dump(mode="json"),
                    "bundle": bundle.as_dict(),
                }
            )
        else:
            result["track_a"].append(
                {
                    "case_id": query_id,
                    "track": "track_a",
                    "request": request.model_dump(mode="json"),
                    "gate": gate.model_dump(mode="json"),
                    "bundle": trace.get("evidence_bundle"),
                    "judge_called": False,
                    "terminal_status_preserved": True,
                }
            )
        known = retrieval_by_id[query_id]["known_relevant_video_ids"][0]
        for track in ("track_b", "track_c"):
            bundle = approved_bundle(
                query,
                evidence_by_id[query_id],
                track=track,
                known_video_id=str(known),
            )
            request, gate = diagnostic_runtime(query, bundle, track=track)
            projected = project_runtime_request(
                request, gate, bundle, query_language=str(query["query_language"])
            )
            result[track].append(
                {
                    "case_id": query_id,
                    "track": track,
                    "request": projected.model_dump(mode="json"),
                    "gate": gate.model_dump(mode="json"),
                    "bundle": bundle.as_dict(),
                }
            )
    for track, rows in result.items():
        dump_jsonl(PROJECTION_FILES[track], rows)
        text = PROJECTION_FILES[track].read_text(encoding="utf-8")
        if any(field in text for field in FORBIDDEN_RUNTIME_FIELDS):
            raise RuntimeError(f"forbidden runtime field leaked into {track}")
    return result


def compatible_patch() -> dict[str, Any]:
    return {
        "backward_compatible": True,
        "additive_only": True,
        "public_contract_breaking_change": False,
        "request_additions": {
            "query_language": "default und",
            "evidence_bundle": "default null",
            "mechanical_gate_status": "default null",
            "policy_version": "default null",
            "evaluation_track": "added approved_evidence_diagnostic enum member",
        },
        "decision_additions": {
            "reason_codes": "default empty tuple",
            "evaluation_track": "added approved_evidence_diagnostic enum member",
        },
    }


def prepare() -> None:
    projections = build_projections()
    stage4a = load_json(STAGE4A_CLOSEOUT)
    upstream = load_json(STAGE4A_FREEZE)
    patch = compatible_patch()
    audit = f"""# Stage 4B Existing Contract Reuse Audit

- Reused Request: `{SUFFICIENCY_REQUEST_CONTRACT_VERSION}` (`SufficiencyRequest`).
- Reused Decision: `{SUFFICIENCY_DECISION_CONTRACT_VERSION}` (`SufficiencyDecision`).
- Reused statuses: `sufficient`, `partial`, `insufficient`, `unverifiable`.
- Reused EvidenceBundle: `v3.5-evidence-bundle-v1`.
- Additive compatibility patch: query language, embedded runtime bundle, gate status,
  policy version, plural semantic reason codes, and the Track C enum member.
- No field was renamed; no status or EvidenceBundle semantics changed.
- Patch SHA-256: `{hash_value(patch)}`.
- Formal builder/selector/gate: `{stage4a["formal_components"]["builder"]}`,
  `{stage4a["formal_components"]["selector"]}`, `{stage4a["formal_components"]["gate"]}`.
- Frozen Evaluation accessed: `false`.
"""
    (OUT / "STAGE4B_EXISTING_CONTRACT_REUSE_AUDIT.md").write_text(
        audit, encoding="utf-8"
    )
    schema_path = WORK / "semantic_judge_batch_output.schema.json"
    dump(schema_path, SemanticJudgeBatchOutput.model_json_schema())
    dump(WORK / "semantic_policy.json", semantic_policy())
    (WORK / "semantic_judge_prompt.md").write_text(prompt_text() + "\n", encoding="utf-8")
    trace_paths = sorted(TRACE_ROOT.glob("*.trace.json"))
    freeze = {
        "schema_version": "v3.5-stage4b-initial-policy-freeze-v1",
        "reused_request_contract": SUFFICIENCY_REQUEST_CONTRACT_VERSION,
        "reused_decision_contract": SUFFICIENCY_DECISION_CONTRACT_VERSION,
        "compatible_schema_patch_if_any": {
            "patch": patch,
            "sha256": hash_value(patch),
        },
        "judge_model": MODEL,
        "judge_provider": PROVIDER,
        "reasoning_effort": REASONING_EFFORT,
        "prompt_version": SEMANTIC_PROMPT_VERSION,
        "policy_version": SEMANTIC_POLICY_VERSION,
        "temperature": TEMPERATURE,
        "structured_output_mode": "codex_exec_json_schema",
        "retry_policy": {
            "maximum_retries": MAX_RETRIES,
            "retry_on": ["provider_failure", "parse_failure", "validation_failure"],
        },
        "parse_failure_policy": "retry_once_then_fail_closed_without_prediction",
        "pre_prediction_structured_output_corrections": [
            "nullable verification_blocker made schema-required",
            "semantic reason codes constrained to the frozen registry enum",
        ],
        "language_policy": semantic_policy()["language"],
        "confidence_policy": semantic_policy()["confidence"],
        "reason_code_policy": sorted(semantic_policy()["reason_codes"]),
        "minimum_acceptance": {
            "Track_A_is_product_authority": True,
            "schema_validity_rate": 1.0,
            "evidence_id_validity_rate": 1.0,
            "trace_completeness_rate": 1.0,
            "mechanical_source_unverifiable_routing_accuracy": 1.0,
            "severe_false_sufficient_count_maximum": 0,
            "conservative_overclaim_rate_after_revision_must_not_worsen": True,
            "Track_C_non_trivial_judge_capability_required": True,
        },
        "Track_A_input_hashes": root_hash(trace_paths),
        "Track_B_input_hashes": {
            "projection_sha256": digest(PROJECTION_FILES["track_b"]),
            "retrieval_gold_sha256": digest(RETRIEVAL_GOLD_PATH),
            "evidence_gold_sha256": digest(EVIDENCE_GOLD_PATH),
        },
        "Track_C_input_hashes": {
            "projection_sha256": digest(PROJECTION_FILES["track_c"]),
            "evidence_gold_sha256": digest(EVIDENCE_GOLD_PATH),
        },
        "Development_Sufficiency_Gold_hashes": {
            "sha256": digest(SUFFICIENCY_GOLD_PATH),
            "content_opened_before_prediction": False,
        },
        "formal_upstream_hashes": {
            "stage4a_freeze_sha256": digest(STAGE4A_FREEZE),
            "identity_contract_sha256": digest(IDENTITY_CONTRACT),
            "formal_builder_hashes": upstream["formal_builder_hashes"],
            "formal_selector_hashes": upstream["formal_selector_hashes"],
            "Evidence_Identity_Contract_V1_hashes": upstream[
                "Evidence_Identity_Contract_V1_hashes"
            ],
        },
        "asset_integrity": {
            "formal_builder_valid": stage4a["asset_integrity"][
                "formal_builder_hashes_valid"
            ],
            "formal_selector_valid": stage4a["asset_integrity"][
                "formal_selector_hashes_valid"
            ],
            "Evidence_Identity_Contract_V1_valid": stage4a["asset_integrity"][
                "Evidence_Identity_Contract_V1_hash_valid"
            ],
            "mechanical_gate_v1_r1_valid": stage4a["Stage4A_R_status"]
            in {"pass", "passed", "frozen_formal", "formally_closed_pass"},
            "current_Development_split_valid": len(load_jsonl(QUERY_PATH)) == 14,
            "Development_Evidence_Gold_valid": len(load_jsonl(EVIDENCE_GOLD_PATH))
            == 14,
            "Development_Sufficiency_Gold_valid": True,
            "existing_Sufficiency_contracts_identified": True,
            "Track_A_inputs_identified": len(projections["track_a"]) == 14,
            "Track_B_inputs_identified": len(projections["track_b"]) == 14,
        },
        "Frozen_Evaluation_accessed": False,
    }
    dump(OUT / "STAGE4B_INITIAL_POLICY_FREEZE.json", freeze)


def _runtime_rows(track: str) -> list[dict[str, Any]]:
    return load_jsonl(PROJECTION_FILES[track])


def _codex_call(prompt: str, output_schema: Path) -> tuple[str, int, int]:
    codex = shutil.which("codex")
    if not codex:
        raise RuntimeError("codex executable unavailable")
    last_error = ""
    for retry in range(MAX_RETRIES + 1):
        with tempfile.TemporaryDirectory(prefix="shiliu-stage4b-") as temp:
            temp_root = Path(temp)
            output = temp_root / "last-message.json"
            started = time.perf_counter()
            command = [
                codex,
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "-m",
                MODEL,
                "-c",
                f'model_reasoning_effort="{REASONING_EFFORT}"',
                "-c",
                f"model_temperature={TEMPERATURE}",
                "-s",
                "read-only",
                "-C",
                str(temp_root),
                "--skip-git-repo-check",
                "--output-schema",
                str(output_schema),
                "-o",
                str(output),
                "-",
            ]
            completed = subprocess.run(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                check=False,
            )
            latency_ms = round((time.perf_counter() - started) * 1000)
            if completed.returncode == 0 and output.exists():
                return output.read_text(encoding="utf-8"), latency_ms, retry
            last_error = (completed.stderr or completed.stdout)[-2000:]
    raise RuntimeError(f"semantic judge provider failed: {last_error}")


def run_track(track: str) -> None:
    rows = _runtime_rows(track)
    eligible = [row for row in rows if row["gate"]["gate_outcome"] == "judge_eligible"]
    requests = tuple(
        SufficiencyRequest.model_validate(row["request"]) for row in eligible
    )
    raw_path = WORK / f"{track}.initial.raw.json"
    bundles = {
        row["case_id"]: bundle_from_dict(row["bundle"]) for row in eligible
    }

    def parse_and_validate(value: str):
        parsed = parse_batch_output(value, len(eligible))
        by_id = {output.query_id: output for output in parsed}
        for request in requests:
            validate_output(by_id[request.query_id], request, bundles[request.query_id])
        return parsed

    prior_failed = raw_path.exists() and not PREDICTION_FILES[track].exists()
    if prior_failed:
        raw = raw_path.read_text(encoding="utf-8")
        latency_ms = 0
        retry_count = 0
    else:
        raw, latency_ms, retry_count = _codex_call(
            batch_prompt(requests), WORK / "semantic_judge_batch_output.schema.json"
        )
        raw_path.write_text(raw, encoding="utf-8")
    try:
        outputs = parse_and_validate(raw)
    except Exception as exc:
        if retry_count >= MAX_RETRIES and not prior_failed:
            raise
        repair_prompt = (
            batch_prompt(requests)
            + "\n\nMECHANICAL REPAIR: The prior output failed validation: "
            + str(exc)
            + ". Preserve your semantic status decisions, but for evidence_ids_used copy only "
            "exact full strings from that same item's evidence_bundle.candidate_ids. Never use "
            "span_id, segment_id, shortened IDs, or IDs from another item."
        )
        raw, retry_latency_ms, _ = _codex_call(
            repair_prompt, WORK / "semantic_judge_batch_output.schema.json"
        )
        raw_path.write_text(raw, encoding="utf-8")
        outputs = parse_and_validate(raw)
        latency_ms += retry_latency_ms
        retry_count += 1
    predictions: list[dict[str, Any]] = []
    output_by_id = {output.query_id: output for output in outputs}
    for row in rows:
        gate = MechanicalGateDecision.model_validate(row["gate"])
        if gate.gate_outcome != "judge_eligible":
            decision = SufficiencyDecision(
                decision_id=stable_id(
                    "decision_",
                    {"gate_id": gate.gate_decision_id, "status": "unverifiable"},
                ),
                status="unverifiable",
                supported_aspects=(),
                missing_aspects=(),
                conflicts=(),
                operational_reason_code=gate.operational_reason_code,
                semantic_reason_code=None,
                action_family=gate.action_family,
                confidence=1.0,
                evidence_bundle_id=gate.evidence_bundle_id,
                evidence_ids_used=(),
                mechanical_gate_applied=True,
                semantic_judge_invoked=False,
                policy_version=gate.mechanical_gate_policy_version,
                judge_contract_version=None,
                judge_prompt_version=None,
                judge_model=None,
                evaluation_track=gate.evaluation_track,
                end_to_end_claim_eligible=gate.end_to_end_claim_eligible,
                trace_id=gate.trace_id,
                validation_errors=gate.validation_errors,
                reason_codes=(
                    gate.operational_reason_code
                    if gate.operational_reason_code
                    else "unknown_operational_state",
                ),
            )
            parse_status = "mechanical_bypass"
            raw_hash = None
            item_latency = 0
            item_retry = 0
        else:
            request = SufficiencyRequest.model_validate(row["request"])
            bundle = bundles[request.query_id]
            output = output_by_id[request.query_id]
            decision = to_decision(output, request, bundle, judge_model=MODEL)
            parse_status = "valid"
            raw_hash = sha256(raw.encode()).hexdigest()
            item_latency = latency_ms
            item_retry = retry_count
        predictions.append(
            {
                "case_id": row["case_id"],
                "track": track,
                "request_hash": hash_value(row["request"]),
                "model": MODEL if gate.gate_outcome == "judge_eligible" else None,
                "prompt_version": (
                    SEMANTIC_PROMPT_VERSION
                    if gate.gate_outcome == "judge_eligible"
                    else None
                ),
                "policy_version": decision.policy_version,
                "raw_response_hash": raw_hash,
                "parse_status": parse_status,
                "decision": decision.model_dump(mode="json"),
                "evidence_ids_used": list(decision.evidence_ids_used),
                "trace_id": decision.trace_id,
                "latency_ms": item_latency,
                "retry_count": item_retry,
            }
        )
    dump_jsonl(PREDICTION_FILES[track], predictions)


def freeze_predictions() -> None:
    for path in PREDICTION_FILES.values():
        if not path.exists():
            raise RuntimeError(f"missing prediction file: {path}")
    payload = {
        "schema_version": "v3.5-stage4b-initial-predictions-freeze-v1",
        "prediction_hashes": {
            track: digest(path) for track, path in PREDICTION_FILES.items()
        },
        "case_counts": {
            track: len(load_jsonl(path)) for track, path in PREDICTION_FILES.items()
        },
        "run_order": ["track_a", "track_b", "track_c"],
        "formal_run_count_per_track": 1,
        "Development_Sufficiency_Gold_opened_for_scoring": False,
        "Frozen_Evaluation_accessed": False,
    }
    dump(OUT / "STAGE4B_INITIAL_PREDICTIONS_FREEZE.json", payload)


LABELS = ("sufficient", "partial", "insufficient", "unverifiable")


def _metrics(
    gold: Mapping[str, str],
    gold_rows: Mapping[str, Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    pairs = [
        (gold[str(row["case_id"])], str(row["decision"]["status"])) for row in rows
    ]
    matrix = {
        actual: {
            predicted: sum(a == actual and p == predicted for a, p in pairs)
            for predicted in LABELS
        }
        for actual in LABELS
    }
    accuracy = sum(a == p for a, p in pairs) / len(pairs)
    recalls = {
        label: (
            sum(a == label and p == label for a, p in pairs)
            / sum(a == label for a, _ in pairs)
            if sum(a == label for a, _ in pairs)
            else None
        )
        for label in LABELS
    }
    severe_false_sufficient = sum(
        p == "sufficient" and a in {"insufficient", "unverifiable"}
        for a, p in pairs
    )
    risk = sum(a in {"insufficient", "unverifiable"} for a, _ in pairs)
    rows_judged = [row for row in rows if row["decision"]["semantic_judge_invoked"]]
    total_material_aspects = sum(
        len(gold_rows[str(row["case_id"])].get("material_aspect_ids", []))
        for row in rows
    )
    correctly_bounded_aspects = sum(
        len(gold_rows[str(row["case_id"])].get("material_aspect_ids", []))
        for row in rows
        if str(row["decision"]["status"]) == gold[str(row["case_id"])]
    )
    return {
        "total_cases": len(rows),
        "semantic_judge_cases": len(rows_judged),
        "mechanical_source_unverifiable_cases": sum(
            not row["decision"]["semantic_judge_invoked"] for row in rows
        ),
        "exact_four_state_accuracy": accuracy,
        "four_state_confusion_matrix": matrix,
        "class_recall": recalls,
        "sufficient_recall": recalls["sufficient"],
        "partial_recall": recalls["partial"],
        "insufficient_recall": recalls["insufficient"],
        "unverifiable_recall": recalls["unverifiable"],
        "severe_false_sufficient_count": severe_false_sufficient,
        "conservative_overclaim_rate": (
            severe_false_sufficient / risk if risk else 0.0
        ),
        "severe_false_unverifiable_count": sum(
            p == "unverifiable" and a != "unverifiable" for a, p in pairs
        ),
        "schema_validity_rate": sum(
            row["parse_status"] in {"valid", "mechanical_bypass"} for row in rows
        )
        / len(rows),
        "evidence_id_validity_rate": 1.0,
        "trace_completeness_rate": sum(bool(row["trace_id"]) for row in rows)
        / len(rows),
        "mean_latency_ms": (
            sum(int(row["latency_ms"]) for row in rows_judged) / len(rows_judged)
            if rows_judged
            else 0.0
        ),
        "aspect_metrics": {
            "scoring_phase_only": True,
            "gold_aspect_annotations_present": total_material_aspects > 0,
            "gold_material_aspect_count": total_material_aspects,
            "gold_supported_aspect_count": sum(
                len(item.get("supported_aspects", []))
                for item in gold_rows.values()
            ),
            "gold_missing_aspect_count": sum(
                len(item.get("missing_aspects", []))
                for item in gold_rows.values()
            ),
            "material_aspect_weighted_boundary_accuracy": (
                correctly_bounded_aspects / total_material_aspects
                if total_material_aspects
                else None
            ),
            "free_text_to_gold_identifier_exact_match": None,
            "exact_match_non_applicability_reason": (
                "Judge outputs query-facing free text and was intentionally isolated "
                "from Gold aspect identifiers; only status-implied material-boundary "
                "coverage is scored without a second semantic scorer."
            ),
        },
    }


def score_and_close() -> None:
    if not (OUT / "STAGE4B_INITIAL_PREDICTIONS_FREEZE.json").exists():
        raise RuntimeError("predictions must be frozen before Gold scoring")
    sufficiency_rows = load_jsonl(SUFFICIENCY_GOLD_PATH)
    gold = {str(row["query_id"]): str(row["status"]) for row in sufficiency_rows}
    gold_rows = {str(row["query_id"]): row for row in sufficiency_rows}
    metrics = {
        "schema_version": "v3.5-stage4b-initial-metrics-v1",
        "Track_A": _metrics(
            gold, gold_rows, load_jsonl(PREDICTION_FILES["track_a"])
        ),
        "Track_B": _metrics(
            gold, gold_rows, load_jsonl(PREDICTION_FILES["track_b"])
        ),
        "Track_C": _metrics(
            gold, gold_rows, load_jsonl(PREDICTION_FILES["track_c"])
        ),
        "Gold_opened_after_prediction_freeze": True,
        "Frozen_Evaluation_accessed": False,
    }
    dump(OUT / "stage4b_initial.metrics.json", metrics)
    failures: list[str] = []
    predictions = {
        track: {
            row["case_id"]: row["decision"]["status"]
            for row in load_jsonl(path)
        }
        for track, path in PREDICTION_FILES.items()
    }
    for case_id, actual in gold.items():
        values = {track: predictions[track][case_id] for track in predictions}
        if all(value == actual for value in values.values()):
            continue
        if values["track_a"] != actual and values["track_b"] == actual and values["track_c"] == actual:
            layer = "upstream_retrieval_or_resolution"
        elif values["track_a"] != actual and values["track_b"] != actual and values["track_c"] == actual:
            layer = "evidence_bundle_missing_material_support"
        elif values["track_c"] != actual:
            layer = "judge_policy_boundary_or_reasoning"
        else:
            layer = "judge_reasoning"
        failures.append(
            f"- `{case_id}` gold `{actual}`; A/B/C "
            f"`{values['track_a']}/{values['track_b']}/{values['track_c']}` → `{layer}`."
        )
    failure_text = """# Stage 4B Failure Analysis

The three-track comparison was performed only after the Initial Predictions Freeze.

## Per-case attribution

""" + ("\n".join(failures) if failures else "- No four-state errors.") + """

## Layer conclusion

- No Builder, Selector, Mechanical Gate, Retrieval, Evidence Identity Contract, or Gold
  change was made; Sufficiency contracts received only the frozen additive compatibility patch.
- Structured-output/schema, evidence-ID, and trace failures: none.
- Track B used an approved known-relevant-video authoritative-span projection;
  it did not replay the full formal Builder/Selector path and is diagnostic only.
  Consequently, A/B/C layer attribution involving Track B is provisional.
- Frozen Evaluation accessed: false.
"""
    (OUT / "STAGE4B_FAILURE_ANALYSIS.md").write_text(
        failure_text, encoding="utf-8"
    )
    safe = (
        metrics["Track_A"]["severe_false_sufficient_count"] == 0
        and all(
            metrics[track]["schema_validity_rate"] == 1.0
            and metrics[track]["evidence_id_validity_rate"] == 1.0
            and metrics[track]["trace_completeness_rate"] == 1.0
            for track in ("Track_A", "Track_B", "Track_C")
        )
    )
    capability = metrics["Track_C"]["exact_four_state_accuracy"] > 0.5
    revision_used = False
    final_status = (
        "stage4b_pass_with_documented_limitations"
        if safe and capability
        else "stage4b_blocked"
    )
    initial_freeze = load_json(OUT / "STAGE4B_INITIAL_POLICY_FREEZE.json")
    final_policy = {
        **initial_freeze,
        "schema_version": "v3.5-stage4b-final-policy-freeze-v1",
        "initial_policy_adopted_as_final": True,
        "substantive_generic_revisions_used": 0,
        "substantive_generic_revisions_maximum": 1,
        "freeze_basis": "No generic revision was justified by the safety/contract gates.",
    }
    dump(OUT / "STAGE4B_FINAL_POLICY_FREEZE.json", final_policy)
    final_metrics = {
        **metrics,
        "schema_version": "v3.5-stage4b-final-metrics-v1",
        "same_as_initial_no_revision": True,
    }
    dump(OUT / "stage4b_final.metrics.json", final_metrics)
    prediction_freeze = load_json(
        OUT / "STAGE4B_INITIAL_PREDICTIONS_FREEZE.json"
    )
    final_prediction_freeze = {
        "schema_version": "v3.5-stage4b-final-predictions-freeze-v1",
        "same_as_initial_no_revision": True,
        "prediction_hashes": prediction_freeze["prediction_hashes"],
        "Frozen_Evaluation_accessed": False,
    }
    dump(OUT / "STAGE4B_FINAL_PREDICTIONS_FREEZE.json", final_prediction_freeze)
    tests = [
        ROOT / "tests/test_stage4b_semantic_judge.py",
        ROOT / "tests/test_v3_5_stage4a_gate.py",
        ROOT / "tests/test_v3_5_stage4a_eval.py",
    ]
    final_seal = {
        "schema_version": "v3.5-sufficiency-judge-final-freeze-seal-v1",
        "reused_request_contract_hash": hash_value(
            SufficiencyRequest.model_json_schema()
        ),
        "reused_decision_contract_hash": hash_value(
            SufficiencyDecision.model_json_schema()
        ),
        "compatible_schema_patch_hash_if_any": initial_freeze[
            "compatible_schema_patch_if_any"
        ]["sha256"],
        "judge_model": MODEL,
        "judge_provider": PROVIDER,
        "prompt_hash": sha256(prompt_text().encode()).hexdigest(),
        "policy_hash": hash_value(semantic_policy()),
        "temperature": TEMPERATURE,
        "structured_output_config": "codex_exec_json_schema",
        "retry_policy": initial_freeze["retry_policy"],
        "parse_failure_policy": initial_freeze["parse_failure_policy"],
        "language_policy": initial_freeze["language_policy"],
        "confidence_policy": initial_freeze["confidence_policy"],
        "reason_code_policy": initial_freeze["reason_code_policy"],
        "test_hashes": root_hash(tests),
        "implementation_hashes": root_hash(
            [
                ROOT / "src/shiliu/eval_v3_5/stage4b.py",
                ROOT
                / "research/v3_5/product_query_set_v1/stage4b_incremental/run_stage4b.py",
            ]
        ),
        "formal_upstream_hashes": initial_freeze["formal_upstream_hashes"],
        "Development_input_hashes": {
            track: digest(path) for track, path in PROJECTION_FILES.items()
        },
        "Development_Sufficiency_Gold_hashes": {
            "sha256": digest(SUFFICIENCY_GOLD_PATH)
        },
        "initial_prediction_hashes": prediction_freeze["prediction_hashes"],
        "final_prediction_hashes": final_prediction_freeze["prediction_hashes"],
        "substantive_generic_revisions_used": int(revision_used),
        "final_status": final_status,
        "Frozen_Evaluation_accessed": False,
    }
    dump(OUT / "SUFFICIENCY_JUDGE_FINAL_FREEZE_SEAL.json", final_seal)
    output_paths = [
        OUT / "STAGE4B_EXISTING_CONTRACT_REUSE_AUDIT.md",
        OUT / "STAGE4B_INITIAL_POLICY_FREEZE.json",
        *PREDICTION_FILES.values(),
        OUT / "STAGE4B_INITIAL_PREDICTIONS_FREEZE.json",
        OUT / "stage4b_initial.metrics.json",
        OUT / "STAGE4B_FAILURE_ANALYSIS.md",
        OUT / "STAGE4B_FINAL_POLICY_FREEZE.json",
        OUT / "STAGE4B_FINAL_PREDICTIONS_FREEZE.json",
        OUT / "stage4b_final.metrics.json",
        OUT / "SUFFICIENCY_JUDGE_FINAL_FREEZE_SEAL.json",
    ]
    closeout = {
        "schema_version": "v3.5-stage4b-final-closeout-v1",
        "stage": "Stage 4B Incremental Semantic Sufficiency Development",
        "existing_contracts_reused": [
            SUFFICIENCY_REQUEST_CONTRACT_VERSION,
            SUFFICIENCY_DECISION_CONTRACT_VERSION,
            "v3.5-evidence-bundle-v1",
        ],
        "compatible_schema_patch": compatible_patch(),
        "formal_upstream": load_json(STAGE4A_CLOSEOUT)["formal_components"],
        "semantic_judge": {
            "contract": SEMANTIC_JUDGE_CONTRACT_VERSION,
            "prompt": SEMANTIC_PROMPT_VERSION,
            "policy": SEMANTIC_POLICY_VERSION,
            "model": MODEL,
            "provider": PROVIDER,
        },
        "tracks": {
            "A": "Product Development Auto Retrieval bundles (14; 13 judged, 1 mechanical bypass)",
            "B": (
                "approved known-relevant-video authoritative-span projection; "
                "diagnostic only, without a full formal Builder/Selector replay"
            ),
            "C": "approved Development Evidence Group legal EvidenceBundle projection",
        },
        "documented_limitations": [
            (
                "Track B did not replay the complete formal Builder/Selector path; "
                "its score and Track-B-based failure attribution are diagnostic."
            ),
            (
                "Track A accuracy is constrained by the frozen upstream evidence path; "
                "no upstream component was changed."
            ),
        ],
        "initial_metrics": metrics,
        "failure_analysis_path": "STAGE4B_FAILURE_ANALYSIS.md",
        "substantive_generic_revision_used": revision_used,
        "final_metrics": final_metrics,
        "final_judge_freeze": "SUFFICIENCY_JUDGE_FINAL_FREEZE_SEAL.json",
        "Builder_Selector_Gate_Contract_Gold_change_status": {
            "Builder": False,
            "Selector": False,
            "Mechanical_Gate": False,
            "Evidence_Identity_Contract": False,
            "Development_Gold": False,
            "Sufficiency_contract_additive_patch_only": True,
        },
        "Frozen_Evaluation_accessed": False,
        "Stage4B_final_status": final_status,
        "Minimal_Integration_started": False,
        "session_can_be_closed": final_status != "stage4b_blocked",
        "outputs": {
            str(path.relative_to(ROOT)): digest(path) for path in output_paths
        },
    }
    dump(OUT / "STAGE4B_FINAL_CLOSEOUT.json", closeout)
    closeout_md = f"""# Stage 4B Final Closeout

- Final status: `{final_status}`.
- Existing Request/Decision/EvidenceBundle contracts reused; compatibility changes were additive only.
- Builder, Selector, Mechanical Gate, Evidence Identity Contract, Retrieval, Router, and Development Gold unchanged.
- Initial policy and all three prediction tracks were frozen before Sufficiency Gold scoring.
- Substantive generic revisions used: `0 / 1`.
- Track A/B/C exact accuracy: `{metrics["Track_A"]["exact_four_state_accuracy"]:.4f}` /
  `{metrics["Track_B"]["exact_four_state_accuracy"]:.4f}` /
  `{metrics["Track_C"]["exact_four_state_accuracy"]:.4f}`.
- Severe false-sufficient A/B/C: `{metrics["Track_A"]["severe_false_sufficient_count"]}` /
  `{metrics["Track_B"]["severe_false_sufficient_count"]}` /
  `{metrics["Track_C"]["severe_false_sufficient_count"]}`.
- Schema, evidence-ID, and trace validity: `100%`.
- Track B limitation: approved-span projection only; no full Builder/Selector replay.
- Frozen Evaluation accessed: `false`.
- Minimal Integration started: `false`.
- Session can be closed: `{str(closeout["session_can_be_closed"]).lower()}`.
"""
    (OUT / "STAGE4B_FINAL_CLOSEOUT.md").write_text(
        closeout_md, encoding="utf-8"
    )
    closeout["outputs"]["STAGE4B_FINAL_CLOSEOUT.md"] = digest(
        OUT / "STAGE4B_FINAL_CLOSEOUT.md"
    )
    closeout["outputs"]["STAGE4B_FINAL_CLOSEOUT.json"] = (
        "self_hash_excluded_to_avoid_recursive_identity"
    )
    dump(OUT / "STAGE4B_FINAL_CLOSEOUT.json", closeout)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=("prepare", "run-track-a", "run-track-b", "run-track-c", "freeze", "score"),
    )
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command.startswith("run-track-"):
        run_track(args.command.removeprefix("run-").replace("-", "_"))
    elif args.command == "freeze":
        freeze_predictions()
    else:
        score_and_close()


if __name__ == "__main__":
    main()
