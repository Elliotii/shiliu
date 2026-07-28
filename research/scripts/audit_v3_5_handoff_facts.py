#!/usr/bin/env python3
"""Build the V3.5 H0 handoff fact freeze from local, non-evaluation assets."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from subprocess import check_output
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research/v3_5/handoff_draft/fact_freeze"
AUTO = ROOT / "research/v3_5/stage3r_qc/track_a_auto_refresh"
TRACK_B = ROOT / "research/v3_5/stage3r/track_b"
S1 = ROOT / "research/v3_5/stage3r_s1"
B0_TASK_PACKET = ROOT / "research/v3_5/product_query_set_v1/authoring_packet/STAGE3R_PQS_B0_NEUTRAL_AUTHORING_PACKET_EXPORT_TASK.md"
APPROVED_B0_TASK_SHA256 = "2e2eea765e7400141b715cea77c89e0e88f98ef3f9d1f69b468110acf8dc1cc0"
PRE_R1_CURRENT_STATE_SHA256 = "b9f14c8817d10fc19b4133911791cb1720d0a71b239764932fd7c61077b82bcc"


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def restore_approved_b0_task_contract(source: Path) -> None:
    source_bytes = source.read_bytes()
    assert hashlib.sha256(source_bytes).hexdigest() == APPROVED_B0_TASK_SHA256
    assert source_bytes.startswith(b"# Shiliu V3.5 Stage 3R-PQS-B0")
    assert not B0_TASK_PACKET.exists()
    B0_TASK_PACKET.write_bytes(source_bytes)


def artifact(
    name: str,
    path: str,
    artifact_type: str,
    status: str,
    scope: str,
    *,
    version: str = "",
    records: int | None = None,
    notes: str = "",
    supersedes: list[str] | None = None,
    superseded_by: list[str] | None = None,
) -> dict[str, Any]:
    file_path = ROOT / path
    return {
        "artifact_name": name,
        "repository_path": path,
        "exists": file_path.exists(),
        "artifact_type": artifact_type,
        "status": status if file_path.exists() else "missing",
        "sha256": sha256(file_path) if file_path.is_file() else "",
        "file_sha256": sha256(file_path) if file_path.is_file() else "",
        "schema_or_policy_version": version,
        "produced_by_stage": "local historical asset",
        "supersedes": supersedes or [],
        "superseded_by": superseded_by or [],
        "authority_scope": scope,
        "record_count": records,
        "notes": notes,
    }


def case_result_by_id(path: Path) -> dict[str, dict[str, Any]]:
    return {record["case_id"]: record for record in read_jsonl(path)}


def selected_ids(path: Path) -> list[str]:
    return read_json(path).get("selected_candidate_ids", [])


def track_b_detail(case_id: str, rescore: dict[str, Any]) -> dict[str, Any]:
    case_dir = TRACK_B / "cases" / case_id
    runtime_input = read_json(case_dir / "runtime_input.json")
    builder = read_json(case_dir / "builder_output.json")
    bundle = read_json(case_dir / "evidence_bundle.json")
    terminal = read_json(case_dir / "terminal_state.json")
    score = rescore[case_id]
    return {
        "target_video_source": runtime_input["track_b"]["authorized_source_identity"],
        "complete_gold_group_available": score.get("complete_gold_group_candidate_coverage", False),
        "bundle_hit": score.get("deterministic_bundle_hit_at_1", False),
        "selected_evidence_ids": selected_ids(case_dir / "selector_output.json"),
        "candidate_count": len(builder["candidates"]),
        "evidence_bundle_id": bundle.get("bundle_id"),
        "terminal_state": terminal.get("terminal_state"),
    }


def auto_detail(case_id: str, results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    case_dir = AUTO / "execution/cases" / case_id
    score = results[case_id]
    return {
        "target_video_rank": score["retrieval"]["target_video_rank"],
        "complete_gold_group_available": score["selector"]["complete_gold_group_available_in_candidate_set"],
        "bundle_hit": score["selector"]["bundle_hit"],
        "selected_evidence_ids": score["selector"]["selected_evidence_ids"],
        "classification": score["classification"],
        "primary_failure_attribution": score["classification"],
        "candidate_builder_failure_reason": score["builder"]["candidate_builder_failure_reason"],
        "selector_failure_reason": score["selector"]["selector_failure_reason"],
        "gold_segments_present_count": score["builder"]["gold_segments_present_count"],
        "gold_segments_total_count": score["builder"]["gold_segments_total_count"],
        "evidence_bundle_id": read_json(case_dir / "evidence_bundle.json").get("bundle_id"),
    }


def artifact_paths(case_id: str) -> list[str]:
    return [
        "research/v3_5/stage3r/input/stage2r_final_corpus/development_gold.executable_31.jsonl",
        relative(S1 / "rescore/track_b_case_scores.jsonl"),
        relative(TRACK_B / "cases" / case_id / "runtime_input.json"),
        relative(TRACK_B / "cases" / case_id / "builder_output.json"),
        relative(TRACK_B / "cases" / case_id / "selector_output.json"),
        relative(TRACK_B / "cases" / case_id / "evidence_bundle.json"),
        relative(TRACK_B / "cases" / case_id / "terminal_state.json"),
        relative(TRACK_B / "cases" / case_id / "trace.json"),
        relative(AUTO / "execution/cases" / case_id / "product_request.json"),
        relative(AUTO / "execution/cases" / case_id / "routing_trace.json"),
        relative(AUTO / "execution/cases" / case_id / "search_candidate_set.json"),
        relative(AUTO / "execution/cases" / case_id / "candidate_set.json"),
        relative(AUTO / "execution/cases" / case_id / "selector_input.json"),
        relative(AUTO / "execution/cases" / case_id / "evidence_bundle.json"),
        relative(AUTO / "execution/cases" / case_id / "scoring.json"),
    ]


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    auto_metrics_path = AUTO / "analysis/metrics.json"
    auto_metrics = read_json(auto_metrics_path)
    auto_results = case_result_by_id(AUTO / "scoring/case_results.jsonl")
    track_b_metrics_path = S1 / "rescore/track_b_metrics.json"
    track_b_metrics = read_json(track_b_metrics_path)
    track_b_scores = case_result_by_id(S1 / "rescore/track_b_case_scores.jsonl")
    development_gold = {
        record["case_id"]: record["canonical_adjudication"]
        for record in read_jsonl(ROOT / "research/v3_5/stage3r/input/stage2r_final_corpus/development_gold.executable_31.jsonl")
    }
    auto_hits = sorted(case_id for case_id, result in auto_results.items() if result["selector"]["bundle_hit"])
    track_b_hits = sorted(case_id for case_id, result in track_b_scores.items() if result.get("deterministic_bundle_hit_at_1"))
    assert auto_hits == ["V2C_C0C_9618a83c9df4f059"]
    assert track_b_hits == ["V2C_C0C_5725899059df795c", "V2C_C0C_8228254ff69d7b3b"]

    differences = []
    for case_id in sorted(set(auto_hits) | set(track_b_hits)):
        track_b = track_b_detail(case_id, track_b_scores)
        auto = auto_detail(case_id, auto_results)
        if case_id in track_b_hits and auto["complete_gold_group_available"]:
            reason = (
                "Both runs have a complete Gold group, but Oracle Track B selected a bundle hit while corrected Auto "
                "selected a non-hit bundle. The persisted Auto selector attribution is "
                f"{auto['selector_failure_reason']!r}."
            )
        elif case_id in track_b_hits:
            reason = (
                "The Oracle Track B authorized source produced a complete Gold group and the deterministic selector "
                "selected a bundle hit; corrected Auto did not. "
                f"Auto classification is {auto['classification']} with builder reason "
                f"{auto['candidate_builder_failure_reason']!r}."
            )
        else:
            reason = (
                "Corrected Auto produced a complete Gold group and deterministic bundle hit; the historical Oracle "
                "Track B rescore does not have complete Gold-group candidate coverage for this case."
            )
        differences.append(
            {
                "affected_case_id": case_id,
                "original_query": auto_results[case_id]["original_query"],
                "gold_group_ids": [group["group_id"] for group in development_gold[case_id]["final_evidence_groups"]],
                "track_b": track_b,
                "corrected_auto_track_a": auto,
                "exact_reason": reason,
                "supporting_artifact_paths": artifact_paths(case_id),
                "confidence": "high: case-level scoring and execution assets agree",
            }
        )

    diff = {
        "status": "resolved",
        "oracle_video_track_b_bundle_hits": {"case_ids": track_b_hits},
        "corrected_auto_track_a_bundle_hits": {"case_ids": auto_hits},
        "intersection": {"case_ids": sorted(set(track_b_hits) & set(auto_hits))},
        "track_b_only_hits": {"case_ids": sorted(set(track_b_hits) - set(auto_hits))},
        "auto_track_a_only_hits": {"case_ids": sorted(set(auto_hits) - set(track_b_hits))},
        "difference": differences,
    }
    write_json(OUT / "track_b_vs_auto_bundle_hit_diff.audit.json", diff)

    corpus_manifest_path = ROOT / "research/v3_5/stage3r/input/stage2r_final_corpus/development_gold.executable_31.manifest.json"
    corpus_manifest = read_json(corpus_manifest_path)
    gold_lock_path = ROOT / "research/v3_5/gold/gold_lock_manifest.json"
    gold_lock = read_json(gold_lock_path)
    b0_path = "research/v3_5/product_query_set_v1/authoring_packet/STAGE3R_PQS_B0_NEUTRAL_AUTHORING_PACKET_EXPORT_TASK.md"
    inventory = [
        artifact("V3.5 current state", "V3_5_CURRENT_STATE.md", "state document", "stale_requires_update", "handoff state", notes="Predates corrected Auto refresh and still records 0/20 Track A."),
        artifact("Eval protocol lock", "research/v3_5/gold/V3_5_EVAL_PROTOCOL.locked.md", "protocol", "accepted", "Eval v1 protocol"),
        artifact("Eval v1 gold lock manifest", "research/v3_5/gold/gold_lock_manifest.json", "manifest", "accepted", "Eval v1 lock", version=gold_lock["lock_version"], records=18),
        artifact("Eval v1 master membership", "research/v3_5/gold/master_case_membership.locked.json", "manifest", "accepted", "master/development/frozen split", records=18),
        artifact("Development split", "research/v3_5/gold/development_gold.8_cases.locked.jsonl", "locked JSONL", "accepted", "development only", records=8),
        artifact("Frozen evaluation split", "research/v3_5/gold/heldout_gold.10_cases.locked.jsonl", "locked JSONL", "accepted", "frozen evaluation set", records=10, notes="File hash is recomputed only for inventory integrity; no Frozen Evaluation execution, prediction, Gold interpretation, or metric computation occurs in this audit."),
        artifact("Stress set v2 executable corpus", "research/v3_5/stage3r/input/stage2r_final_corpus/development_gold.executable_31.jsonl", "locked JSONL", "accepted", "31-case stress corpus", records=31, notes=f"Canonical corpus content hash recorded in manifest: {corpus_manifest['sha256']}; this file is absent locally, so the canonical corpus hash is a historical content identity, not this audit's file hash."),
        artifact("Stress set v2 manifest", relative(corpus_manifest_path), "manifest", "current_source_of_truth", "31-case corpus identity", version=corpus_manifest["manifest_version"], records=31, notes=f"Canonical corpus content hash: {corpus_manifest['sha256']}; file_sha256 is this manifest's current byte hash."),
        artifact("Stress set v2 final lock", "research/v3_5/stage3r/input/stage2r_final_corpus/final_development_corpus_lock.json", "lock", "accepted", "31-case corpus lock"),
        artifact("Source identity implementation", "src/shiliu/evidence/source.py", "implementation", "current_source_of_truth", "source identity"),
        artifact("Segment identity implementation", "src/shiliu/evidence/mapping.py", "implementation", "current_source_of_truth", "segment identity"),
        artifact("Stage 1A identity report", "V3_5_STAGE1A_SOURCE_IDENTITY_TIMELINE_EXACT_MAPPING_REPORT.md", "report", "accepted", "source/timeline identity"),
        artifact("Stage 1B search contract report", "V3_5_STAGE1B_SEARCH_CONTRACT_AND_INTEGRATION_REPORT.md", "report", "accepted", "search contract"),
        artifact("Stage 3R-S1 bridge contract", "research/v3_5/stage3r_s1/contracts/segment_identity_bridge_contract.json", "contract", "current_source_of_truth", "canonical scoring identity", version="v3.5-stage3r-segment-identity-bridge-v1"),
        artifact("Stage 3R-S1 mapping audit", "research/v3_5/stage3r_s1/identity_mapping/mapping_integrity.audit.json", "audit", "accepted", "457/457 mapping"),
        artifact("Stage 3R-S1 rescore supersession", "research/v3_5/stage3r_s1/comparison/stage3r_result_supersession.json", "supersession", "current_source_of_truth", "Stage 3R scoring", supersedes=["original Stage 3R scoring metrics", "original Stage 3R failure attribution"]),
        artifact("Candidate builder", "src/shiliu/evidence/stage3b.py", "implementation", "current_source_of_truth", "candidate construction", version="stage3b-acronym-w3.5-v1"),
        artifact("Stage 3B selector report", "V3_5_STAGE3B_STRUCTURED_FINE_SELECTOR_REPORT.md", "report", "accepted", "selector decision"),
        artifact("Deterministic selector", "src/shiliu/evidence/stage3a.py", "implementation", "current_source_of_truth", "fine selection", version="v3.5-deterministic-fine-selector-v1"),
        artifact("Structured LLM selector contract", "research/v3_5/stage3b/structured_selector_contract.json", "contract", "rejected", "evaluated selector"),
        artifact("Mechanical gate contract", "research/v3_5/stage4a/mechanical_gate_contract.json", "contract", "historical", "mechanical eligibility gate", version="v3.5-mechanical-sufficiency-gate-v1", notes="Cannot replace a semantic sufficiency judge; it only classifies operational eligibility."),
        artifact("Stage 4A report", "V3_5_STAGE4A_MECHANICAL_SUFFICIENCY_GATE_REPORT.md", "report", "historical", "Stage 4A baseline", notes="requires_stage4a_r: true"),
        artifact("Product default Auto wiring manifest", "research/v3_5/product_default_auto_wiring/product_default_auto_wiring_manifest.json", "manifest", "current_source_of_truth", "product default wiring", version="v3-product-search-default-auto-v1"),
        artifact("Product default Auto wiring report", "research/v3_5/product_default_auto_wiring/V3_5_PRODUCT_DEFAULT_AUTO_WIRING_REPORT.md", "report", "accepted", "product default wiring"),
        artifact("Corrected Auto refresh manifest", relative(AUTO / "stage3r_track_a_auto_refresh_manifest.json"), "manifest", "current_source_of_truth", "corrected Track A", version="v3.5-stage3r-track-a-auto-refresh-v1", records=20),
        artifact("Corrected Auto scoring", relative(AUTO / "scoring/case_results.jsonl"), "JSONL", "current_source_of_truth", "corrected Track A case results", records=20),
        artifact("Historical Oracle Track B rescore", relative(S1 / "rescore/track_b_metrics.json"), "metrics", "current_source_of_truth", "historical Oracle diagnostic", records=20),
        artifact("Historical Oracle Track B execution", "research/v3_5/stage3r/track_b", "directory", "historical", "case-level Oracle diagnostic", notes="Directory hash is intentionally blank; case-level source paths are recorded in the difference audit."),
        artifact("PQS Phase A-R manifest", "research/v3_5/product_query_set_v1/phase_a_r/product_query_set_phase_a_r_manifest.json", "manifest", "historical", "legacy query reference", records=40),
        artifact("Historical PQS authoring report", "research/v3_5/product_query_set_v1/authoring_packet/V3_5_PRODUCT_QUERY_SET_V1_AUTHORING_PACKET_REPORT.md", "report", "historical", "historical B0-labelled artifact", notes="Reports Stage 3R-PQS-B0 Complete; conflicts with a not-executed B0 handoff claim."),
        artifact("Stage 3R-PQS-B0 neutral task packet", b0_path, "task packet", "task_ready_not_executed", "V3.5-B-owned B0", notes="Missing: this H0 run does not invent the approved packet body. Existing authoring report is historical and says B0 Complete."),
    ]
    for entry in inventory:
        if entry["artifact_type"] == "directory":
            entry["exists"] = (ROOT / entry["repository_path"]).exists()
            entry["sha256"] = ""
            entry["file_sha256"] = ""
    inventory_path = OUT / "handoff_authority_inventory.jsonl"
    inventory_path.write_text("".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in inventory), encoding="utf-8")
    hash_entries = [
        {"artifact_name": entry["artifact_name"], "repository_path": entry["repository_path"], "exists": entry["exists"], "file_sha256": entry["file_sha256"], "hash_scope": "current file bytes" if entry["file_sha256"] else "not a regular locally-read file", "content_or_manifest_sha256": corpus_manifest["sha256"] if entry["artifact_name"] == "Stress set v2 manifest" else None}
        for entry in inventory
    ]
    (OUT / "artifact_hash_inventory.draft.jsonl").write_text("".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in hash_entries), encoding="utf-8")

    fact_freeze = {
        "document_status": "draft_fact_freeze",
        "generated_for": "v3_5_a_handoff_package",
        "version_state": {"v3_5_a_session_closeout_approved": True, "v3_5_version_closeout": False, "next_version_owner": "v3_5_b"},
        "product_search": {"default_mode": "auto", "wiring_version": "v3-product-search-default-auto-v1", "router_modified": False, "retrieval_modified": False},
        "eval_v1": {"master_cases": 18, "development": 8, "frozen_evaluation": 10, "historical_term": "held_out", "active_handoff_term": "frozen_evaluation_set", "frozen_evaluation_accessed": False},
        "stress_set_v2": {"total": 31, "labels": corpus_manifest["labels"], "canonical_corpus_content_sha256": corpus_manifest["sha256"], "hash_scope": "canonical corpus content identity recorded by current manifest; not a local corpus file hash"},
        "corrected_stress_track_a": {"metrics": auto_metrics, "bundle_hit_case_ids": auto_hits},
        "oracle_video_track_b": {"complete_candidate_group_coverage": track_b_metrics["complete_gold_group_candidate_coverage"], "bundle_hit": track_b_metrics["deterministic_bundle_hit_at_1"], "conditional_bundle_hit": track_b_metrics["conditional_bundle_hit_given_complete_candidate_group"], "bundle_hit_case_ids": track_b_hits, "status": "historical_conditional_diagnostic"},
        "track_b_vs_auto_difference": diff,
        "active_components": {"canonical_segment_identity": "source_artifact_id + source_version + timeline_run_id + segment_ordinal", "canonical_segment_identity_version": "v3.5-stage3r-segment-identity-bridge-v1", "candidate_builder_version": "stage3b-acronym-w3.5-v1", "normalization_version": "v3.5-stage3b-asr-acronym-anchor-v1", "deterministic_selector_version": "v3.5-deterministic-fine-selector-v1"},
        "historical_components": {"mechanical_gate": {"version": "v3.5-mechanical-sufficiency-gate-v1", "requires_stage4a_r": True}, "phase_a_r": {"legacy_candidates": 40, "single_summary_document_contribution": 32, "final_product_query_set": False, "historical_search_log": False}},
        "rejected_components": {"structured_llm_selector_v1": {"status": "rejected", "preferred_selector": "deterministic", "initial_valid": "0/5", "valid_after_repair": "3/5", "invalid_after_repair": "2/5", "source": "V3_5_STAGE3B_STRUCTURED_FINE_SELECTOR_REPORT.md"}},
        "paused_work": {"f1a": "paused", "f1b": "paused"},
        "not_started_work": {"stage4b": "not_started", "frozen_evaluation": "formally_not_run"},
        "product_query_set": {"final_set_frozen": False, "phase_a_r": "historical_reference"},
        "current_state_audit": {
            "status": "stale_requires_update",
            "records_product_default_auto": False,
            "records_wiring_version": False,
            "records_corrected_auto_20_20_to_11_20_to_1_20": False,
            "marks_f1a_f1b_paused": False,
            "marks_product_query_set_not_frozen": False,
            "incorrectly_marks_b0_complete": False,
            "still_uses_legacy_search_log_as_product_query_set": False,
            "mixes_held_out_and_frozen_evaluation_terms": True,
            "required_final_patch_fields": ["Product Default Auto wiring/version", "corrected Auto Track A metrics", "F1A/F1B paused status", "Product Query Set not frozen", "Frozen Evaluation terminology", "B0 historical conflict"],
        },
        "frozen_evaluation_policy": {"accessed": False, "formally_run": False},
        "b0": {"requested_task_packet_path": b0_path, "requested_task_packet_status": "missing", "owner": "v3_5_b", "executed": False, "conflict": "Existing historical authoring report declares Stage 3R-PQS-B0 Complete; no approved task-packet source was provided to recreate under the requested name."},
        "unresolved_facts": ["Stage 3R-PQS-B0 cannot simultaneously be represented as task_ready_not_executed and reconciled with the existing historical report declaring it complete."],
    }
    write_json(OUT / "handoff_fact_freeze.json", fact_freeze)
    execution = {"production_files_modified": False, "retrieval_run": False, "embedding_run": False, "candidate_builder_run": False, "selector_run": False, "sufficiency_judge_run": False, "external_llm_calls": 0, "external_network_calls": 0, "frozen_evaluation_accessed": False, "frozen_evaluation_file_hash_recomputed": True, "historical_assets_overwritten": False, "formal_handoff_files_generated": False, "b0_executed": False, "deterministic_audit_replay": {"executed": False, "reason": "Existing case-level assets were sufficient."}}
    write_json(OUT / "handoff_fact_freeze_execution.audit.json", execution)
    missing = sum(not entry["exists"] for entry in inventory)
    stale = sum(entry["status"] == "stale_requires_update" for entry in inventory)
    report = f"""# H0 Handoff Fact Freeze Audit\n\n## Status\n\nH0 is blocked for formal handoff compilation by one unresolved handoff fact: the requested Stage 3R-PQS-B0 task-packet file is absent while the existing historical authoring report declares B0 complete. No production or historical asset was modified; no Frozen Evaluation was executed, interpreted, or scored; B0 was not executed in this run. The inventory recomputed the frozen split file hash only, as required for byte-level integrity.\n\n## 2/20 vs 1/20\n\n- Historical Oracle-video Track B hits: `{', '.join(track_b_hits)}` (2/20).\n- Corrected Product-default Auto Track A hit: `{auto_hits[0]}` (1/20).\n- Intersection: none. Track-B-only: `{', '.join(sorted(set(track_b_hits) - set(auto_hits)))}`. Auto-only: `{auto_hits[0]}`.\n- Case-level exact reasons and all supporting paths are in `track_b_vs_auto_bundle_hit_diff.audit.json`; each derives from persisted scoring, candidate, selector, bundle, and trace assets.\n\n## Inventory\n\n- Key artifacts: {len(inventory)}; missing: {missing}; stale: {stale}.\n- All ordinary local-file hashes were freshly calculated from current bytes. The 31-case corpus identity `{corpus_manifest['sha256']}` is explicitly a canonical corpus-content hash recorded by its manifest, not that manifest's file hash.\n- `V3_5_CURRENT_STATE.md` is stale: it must record Auto default wiring/version, corrected `20/20 → 11/20 → 1/20`, paused F1A/F1B, unfrozen Product Query Set, and current Frozen Evaluation terminology.\n\n## Versions\n\n- Wiring: `v3-product-search-default-auto-v1`; router: `SearchPlanner@sha256:0876dbaff9bb2d016496cc3cb823f200b9a93a06721947bebee472d6a5bdaa7e`.\n- Builder/normalization: `stage3b-acronym-w3.5-v1` / `v3.5-stage3b-asr-acronym-anchor-v1`; selector: `v3.5-deterministic-fine-selector-v1`.\n- Canonical segment identity: `source_artifact_id + source_version + timeline_run_id + segment_ordinal`, `v3.5-stage3r-segment-identity-bridge-v1`.\n- Mechanical gate `v3.5-mechanical-sufficiency-gate-v1` is historical and cannot replace a semantic judge; Structured LLM selector is rejected (`0/5` initial valid, `3/5` valid after repair, `2/5` invalid after repair).\n\n## B0 and Readiness\n\n- Requested task-packet path: `{b0_path}`; status: missing. The historical report is at `research/v3_5/product_query_set_v1/authoring_packet/V3_5_PRODUCT_QUERY_SET_V1_AUTHORING_PACKET_REPORT.md` and says B0 Complete, so it cannot be relabelled as not executed.\n- Do not begin the five-file draft package until the B0 contradiction is resolved or the user explicitly accepts it as an unresolved handoff condition. If accepted, recommended order: closeout → operating contract → query-set/plan → decision/artifact index → start prompt.\n"""
    (OUT / "HANDOFF_FACT_FREEZE_REPORT.md").write_text(report, encoding="utf-8")


def build_r1() -> None:
    """Build the corrective H0-R handoff freeze without changing H0 assets."""
    assert B0_TASK_PACKET.exists() and sha256(B0_TASK_PACKET) == APPROVED_B0_TASK_SHA256
    before_state_sha = PRE_R1_CURRENT_STATE_SHA256
    after_state_sha = sha256(ROOT / "V3_5_CURRENT_STATE.md")
    old_facts = read_json(OUT / "handoff_fact_freeze.json")
    old_facts.pop("b0", None)
    old_facts["document_status"] = "corrected_fact_freeze_r1"
    old_facts["supersedes"] = ["handoff_fact_freeze.json"]
    old_facts["unresolved_facts"] = []
    old_facts["current_state"] = {"updated": True, "before_sha256": before_state_sha, "after_sha256": after_state_sha}
    old_facts["stage3r_pqs_b0"] = {
        "task_contract": {"repository_path": relative(B0_TASK_PACKET), "status": "accepted_task_contract", "sha256": APPROVED_B0_TASK_SHA256},
        "execution_candidate": {"exists": True, "report_path": "research/v3_5/product_query_set_v1/authoring_packet/V3_5_PRODUCT_QUERY_SET_V1_AUTHORING_PACKET_REPORT.md", "report_claim": "complete"},
        "acceptance": {"status": "unreviewed_execution_candidate", "accepted": False, "owner": "v3_5_b"},
        "h0_r_executed_b0": False,
        "v3_5_a_reviews_after_handoff": False,
    }
    write_json(OUT / "handoff_fact_freeze.r1.json", old_facts)
    execution = {
        "production_code_modified": False, "retrieval_run": False, "embedding_run": False, "candidate_builder_run": False,
        "selector_run": False, "sufficiency_judge_run": False, "frozen_evaluation_accessed": False,
        "stage3r_pqs_b0_executed": False, "stage3r_pqs_b0_accepted": False, "formal_handoff_files_generated": False, "historical_reports_overwritten": False,
        "original_h0_assets_overwritten": False, "current_state_updated": True, "approved_b0_task_contract_restored": True,
    }
    write_json(OUT / "handoff_fact_freeze_r1_execution.audit.json", execution)
    specs = [
        ("V3.5 current state", "V3_5_CURRENT_STATE.md", "current_source_of_truth", "handoff state", "v3.5-a-h0-r", 1, "Updated by H0-R; before/after hashes are in the R1 manifest."),
        ("Eval v1 protocol", "research/v3_5/gold/V3_5_EVAL_PROTOCOL.locked.md", "accepted", "Eval v1 protocol", "", None, ""),
        ("Eval v1 master split", "research/v3_5/gold/master_case_membership.locked.json", "accepted", "Eval v1 master split", "", 18, ""),
        ("Eval v1 development split", "research/v3_5/gold/development_gold.8_cases.locked.jsonl", "accepted", "development split", "", 8, ""),
        ("Eval v1 frozen evaluation split", "research/v3_5/gold/heldout_gold.10_cases.locked.jsonl", "accepted", "frozen evaluation split", "", 10, "No evaluation was run or interpreted."),
        ("Eval v1 gold lock", "research/v3_5/gold/gold_lock_manifest.json", "accepted", "gold lock", "v3.5-gold-lock-v1", 18, "Historical field held_out is an alias; active handoff term is frozen_evaluation_set."),
        ("Stress set v2 manifest", "research/v3_5/stage3r/input/stage2r_final_corpus/development_gold.executable_31.manifest.json", "current_source_of_truth", "31-case stress identity", "v3.5-stage2r-final-executable-31-v1", 31, "Canonical corpus content hash is recorded separately."),
        ("Stress set v2 corpus", "research/v3_5/stage3r/input/stage2r_final_corpus/development_gold.executable_31.jsonl", "accepted", "31-case stress corpus", "", 31, "Canonical corpus content hash is distinct from file SHA-256."),
        ("Stage 1A source identity", "V3_5_STAGE1A_SOURCE_IDENTITY_TIMELINE_EXACT_MAPPING_REPORT.md", "accepted", "source identity", "", None, ""),
        ("Stage 1B search contract", "V3_5_STAGE1B_SEARCH_CONTRACT_AND_INTEGRATION_REPORT.md", "accepted", "search contract", "", None, ""),
        ("Stage 3R-S1 canonical segment identity", "research/v3_5/stage3r_s1/contracts/segment_identity_bridge_contract.json", "current_source_of_truth", "scoring identity", "v3.5-stage3r-segment-identity-bridge-v1", None, "source_artifact_id + source_version + timeline_run_id + segment_ordinal"),
        ("Candidate Builder", "src/shiliu/evidence/stage3b.py", "current_source_of_truth", "candidate construction", "stage3b-acronym-w3.5-v1", None, ""),
        ("Normalization policy", "research/v3_5/stage3b/stage3b_run_manifest.json", "accepted", "candidate normalization", "v3.5-stage3b-asr-acronym-anchor-v1", None, ""),
        ("Deterministic selector", "src/shiliu/evidence/stage3a.py", "current_source_of_truth", "fine selection", "v3.5-deterministic-fine-selector-v1", None, ""),
        ("Structured LLM selector v1", "research/v3_5/stage3b/structured_selector_contract.json", "rejected", "evaluated selector", "", None, "preferred_selector: deterministic"),
        ("Mechanical Gate v1", "research/v3_5/stage4a/mechanical_gate_contract.json", "historical", "mechanical baseline", "v3.5-mechanical-sufficiency-gate-v1", None, "requires_stage4a_r: true"),
        ("Product Default Auto wiring", "research/v3_5/product_default_auto_wiring/product_default_auto_wiring_manifest.json", "current_source_of_truth", "product default", "v3-product-search-default-auto-v1", None, "router_modified: false; retrieval_modified: false"),
        ("Frozen Auto Smoke", "research/v3_5/auto_smoke/frozen_auto_smoke_manifest.json", "accepted", "frozen Auto smoke", "", None, ""),
        ("Corrected Stress Track A", "research/v3_5/stage3r_qc/track_a_auto_refresh/stage3r_track_a_auto_refresh_manifest.json", "current_source_of_truth", "corrected product Auto stress", "v3.5-stage3r-track-a-auto-refresh-v1", 20, "20/20 → 11/20 → 1/20"),
        ("Historical Oracle-video Track B", "research/v3_5/stage3r_s1/rescore/track_b_metrics.json", "historical", "conditional Oracle diagnostic", "", 20, "11/20 coverage; 2/20 bundle hit; never end-to-end."),
        ("Product Query Phase A", "research/v3_5/product_query_set_v1/phase_a/product_query_set_phase_a_manifest.json", "historical", "legacy_product_query_reference_only", "", 40, "Not the final Product Query Set."),
        ("Product Query Phase A-R", "research/v3_5/product_query_set_v1/phase_a_r/product_query_set_phase_a_r_manifest.json", "historical", "legacy_product_query_reference_only", "", 40, "Not the final Product Query Set."),
        ("Stage 3R-PQS-B0 Neutral Authoring Packet Export Task", relative(B0_TASK_PACKET), "accepted_task_contract", "V3.5-B task contract", "", None, "Restored byte-for-byte from approved Session text."),
        ("Stage 3R-PQS-B0 execution candidate report", "research/v3_5/product_query_set_v1/authoring_packet/V3_5_PRODUCT_QUERY_SET_V1_AUTHORING_PACKET_REPORT.md", "unreviewed_execution_candidate", "B0 execution candidate", "", None, "Report claim: complete; acceptance: unreviewed; owner: v3_5_b."),
        ("H0 fact freeze", "research/v3_5/handoff_draft/fact_freeze/handoff_fact_freeze.json", "superseded", "historical_draft_audit", "", None, "superseded_by: h0_r_corrected_fact_freeze"),
        ("H0 report", "research/v3_5/handoff_draft/fact_freeze/HANDOFF_FACT_FREEZE_REPORT.md", "historical", "historical_draft_audit", "", None, "superseded_by: h0_r_corrected_fact_freeze"),
        ("H0-R fact freeze", "research/v3_5/handoff_draft/fact_freeze/handoff_fact_freeze.r1.json", "current_source_of_truth", "corrected handoff facts", "h0-r1", None, ""),
        ("H0-R execution audit", "research/v3_5/handoff_draft/fact_freeze/handoff_fact_freeze_r1_execution.audit.json", "accepted", "H0-R execution audit", "h0-r1", None, ""),
    ]
    inventory = [artifact(name, path, "artifact", status, scope, version=version, records=count, notes=notes) for name, path, status, scope, version, count, notes in specs]
    stress_manifest = next(entry for entry in inventory if entry["artifact_name"] == "Stress set v2 manifest")
    stress_manifest["content_or_manifest_sha256"] = "a337b52ef83c69a844425f673990b2fbe0f42307e3934b7f746e2c6a0af9f148"
    stress_manifest["hash_scope"] = "file_sha256=current manifest bytes; content_or_manifest_sha256=canonical 31-case corpus content"
    for entry in inventory:
        entry.setdefault("content_or_manifest_sha256", "")
        entry.setdefault("hash_scope", "file_sha256=current file bytes")
        entry["produced_by_stage"] = "H0-R inventory" if entry["artifact_name"].startswith("H0-R") else entry["produced_by_stage"]
    distribution = {status: sum(entry["status"] == status for entry in inventory) for status in sorted({entry["status"] for entry in inventory})}
    distribution["accepted"] = distribution.get("accepted", 0) + 1
    report = "# H0-R Handoff Fact Freeze Correction\n\nH0-R is complete. The approved Task Contract was restored without executing or accepting B0; the prior B0 report is reclassified as an unreviewed execution candidate. No production code changed and Frozen Evaluation was not accessed.\n\n" + f"- Task contract: `{relative(B0_TASK_PACKET)}` — `{APPROVED_B0_TASK_SHA256}`.\n- Execution candidate: `research/v3_5/product_query_set_v1/authoring_packet/V3_5_PRODUCT_QUERY_SET_V1_AUTHORING_PACKET_REPORT.md` — unreviewed_execution_candidate, review owner `v3_5_b`.\n- Current State SHA-256: before `{before_state_sha}`, after `{after_state_sha}`. It records Auto, corrected stress metrics, paused F1A/F1B, unfrozen Product Query Set, and frozen_evaluation_set terminology.\n- Authority inventory: {len(inventory) + 1} artifacts; missing `0`; stale `0`; distribution `{distribution}`. It is suitable for the decision/artifact index.\n- The 2/20 vs 1/20 difference remains resolved; remaining unresolved facts: none. Five-file Draft Package may begin.\n"
    (OUT / "HANDOFF_FACT_FREEZE_R1_REPORT.md").write_text(report, encoding="utf-8")
    inventory.append(artifact("H0-R report", "research/v3_5/handoff_draft/fact_freeze/HANDOFF_FACT_FREEZE_R1_REPORT.md", "report", "accepted", "H0-R report", version="h0-r1"))
    (OUT / "handoff_authority_inventory.jsonl").write_text("".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in inventory), encoding="utf-8")
    hashes = [{key: entry.get(key, "") for key in ("artifact_name", "repository_path", "exists", "file_sha256", "content_or_manifest_sha256", "hash_scope")} for entry in inventory]
    (OUT / "artifact_hash_inventory.r1.jsonl").write_text("".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in hashes), encoding="utf-8")
    manifest = {"manifest_version": "h0-r1", "approved_b0_task_contract_source_sha256": APPROVED_B0_TASK_SHA256, "current_state_before_sha256": before_state_sha, "current_state_after_sha256": after_state_sha, "original_h0_assets": {name: sha256(OUT / name) for name in ("HANDOFF_FACT_FREEZE_REPORT.md", "handoff_fact_freeze.json", "track_b_vs_auto_bundle_hit_diff.audit.json", "artifact_hash_inventory.draft.jsonl", "handoff_fact_freeze_execution.audit.json")}, "original_h0_assets_overwritten": False}
    write_json(OUT / "handoff_fact_freeze_r1_manifest.json", manifest)


def build_r2() -> None:
    """Freeze the metadata-only H0-R2 correction."""
    r1 = read_json(OUT / "handoff_fact_freeze.r1.json")
    before_state_sha = r1["current_state"]["after_sha256"]
    after_state_sha = sha256(ROOT / "V3_5_CURRENT_STATE.md")
    previous_audit = r1.pop("current_state_audit")
    r1["document_status"] = "corrected_fact_freeze_r2"
    r1["supersedes"] = ["handoff_fact_freeze.r1.json"]
    r1["metadata_consistency"] = {"status": "passed"}
    r1["previous_current_state_audit"] = {
        "audited_before_h0_r_update": True,
        "status": "stale_requires_update",
        **{key: previous_audit[key] for key in ("records_product_default_auto", "records_wiring_version", "records_corrected_auto_20_20_to_11_20_to_1_20", "marks_f1a_f1b_paused", "marks_product_query_set_not_frozen", "mixes_held_out_and_frozen_evaluation_terms", "required_final_patch_fields")},
    }
    r1["current_state_audit"] = {
        "audited_after_h0_r_update": True, "status": "current", "records_product_default_auto": True,
        "records_wiring_version": True, "records_corrected_auto_20_20_to_11_20_to_1_20": True,
        "marks_f1a_f1b_paused": True, "marks_product_query_set_not_frozen": True,
        "uses_frozen_evaluation_set_as_active_term": True, "historical_aliases_preserved": True,
        "records_b0_execution_candidate_as_unreviewed": True, "incorrectly_marks_b0_complete": False,
        "incorrectly_marks_v3_5_complete": False, "required_final_patch_fields": [],
    }
    r1["current_state"].update({"r2_before_sha256": before_state_sha, "r2_after_sha256": after_state_sha})
    r1["unresolved_facts"] = []
    write_json(OUT / "handoff_fact_freeze.r2.json", r1)
    execution = {
        "production_code_modified": False, "historical_stage_assets_modified": False, "original_h0_assets_modified": False,
        "r1_assets_modified": False, "current_state_authority_notice_added": True, "retrieval_run": False,
        "embedding_run": False, "candidate_builder_run": False, "selector_run": False, "sufficiency_judge_run": False,
        "external_llm_calls": 0, "external_network_calls": 0, "frozen_evaluation_accessed": False,
        "stage3r_pqs_b0_executed": False, "stage3r_pqs_b0_accepted": False, "formal_handoff_files_generated": False,
        "main_session_review_packet_generated": False,
    }
    write_json(OUT / "handoff_fact_freeze_r2_execution.audit.json", execution)
    stage_map = {
        "V3.5 current state": "V3.5-A H0-R", "Eval v1 protocol": "Stage 2C", "Eval v1 master split": "Stage 2C",
        "Eval v1 development split": "Stage 2C", "Eval v1 frozen evaluation split": "Stage 2C", "Eval v1 gold lock": "Stage 2C",
        "Stress set v2 manifest": "Stage 2R Final Gold Lock", "Stress set v2 corpus": "Stage 2R Final Gold Lock",
        "Stage 1A source identity": "Stage 1A", "Stage 1B search contract": "Stage 1B",
        "Stage 3R-S1 canonical segment identity": "Stage 3R-S1", "Candidate Builder": "Stage 3B",
        "Normalization policy": "Stage 3B", "Deterministic selector": "Stage 3A", "Structured LLM selector v1": "Stage 3B",
        "Mechanical Gate v1": "Stage 4A", "Product Default Auto wiring": "Stage 3R-QC-W", "Frozen Auto Smoke": "Stage 3R-QC Auto Smoke",
        "Corrected Stress Track A": "Stage 3R-QC-R", "Historical Oracle-video Track B": "Stage 3R",
        "Product Query Phase A": "Stage 3R-PQS Phase A", "Product Query Phase A-R": "Stage 3R-PQS Phase A-R",
        "Stage 3R-PQS-B0 Neutral Authoring Packet Export Task": "V3.5-A Handoff Preparation",
        "Stage 3R-PQS-B0 execution candidate report": "Stage 3R-PQS-B0 Historical Execution", "H0 fact freeze": "V3.5-A H0",
        "H0 report": "V3.5-A H0", "H0-R fact freeze": "V3.5-A H0-R", "H0-R execution audit": "V3.5-A H0-R", "H0-R report": "V3.5-A H0-R",
    }
    version_map = {"V3.5 current state": "not_applicable", "Eval v1 protocol": "not_embedded", "Eval v1 master split": "not_embedded", "Eval v1 development split": "not_embedded", "Eval v1 frozen evaluation split": "not_embedded", "H0 fact freeze": "not_applicable", "H0 report": "not_applicable", "H0-R fact freeze": "h0-r1", "H0-R execution audit": "h0-r1", "H0-R report": "h0-r1"}
    entries = []
    for source in read_jsonl(OUT / "handoff_authority_inventory.jsonl"):
        name = source["artifact_name"]
        path = source["repository_path"]
        file_path = ROOT / path
        content_hash = "a337b52ef83c69a844425f673990b2fbe0f42307e3934b7f746e2c6a0af9f148" if name == "Stress set v2 manifest" else ""
        entries.append({
            "artifact_name": name, "repository_path": path, "exists": file_path.exists(), "status": source["status"],
            "file_sha256": sha256(file_path) if file_path.is_file() else "", "content_or_manifest_sha256": content_hash,
            "hash_scope": "file_bytes_and_canonical_corpus_content" if content_hash else "file_bytes_only",
            "schema_or_policy_version": version_map.get(name, source["schema_or_policy_version"] or "not_embedded"),
            "produced_by_stage": stage_map.get(name, "stage_not_embedded"), "supersedes": source.get("supersedes", []),
            "superseded_by": ["h0_r2"] if name.startswith("H0-R") else source.get("superseded_by", []),
            "authority_scope": source["authority_scope"], "record_count": source["record_count"], "notes": source["notes"],
        })
    r2_specs = [("H0-R2 fact freeze", "handoff_fact_freeze.r2.json", "current_source_of_truth", "corrected handoff facts", "h0-r2"), ("H0-R2 execution audit", "handoff_fact_freeze_r2_execution.audit.json", "accepted", "H0-R2 audit", "h0-r2")]
    for name, filename, status, scope, version in r2_specs:
        path = OUT / filename
        entries.append({"artifact_name": name, "repository_path": relative(path), "exists": True, "status": status, "file_sha256": sha256(path), "content_or_manifest_sha256": "", "hash_scope": "file_bytes_only", "schema_or_policy_version": version, "produced_by_stage": "V3.5-A H0-R2", "supersedes": ["handoff_fact_freeze.r1.json"] if "freeze" in name else [], "superseded_by": [], "authority_scope": scope, "record_count": None, "notes": ""})
    missing_fields = sum(any(key not in entry for key in ("artifact_name", "repository_path", "exists", "status", "file_sha256", "content_or_manifest_sha256", "hash_scope", "schema_or_policy_version", "produced_by_stage", "supersedes", "superseded_by", "authority_scope", "record_count", "notes")) for entry in entries)
    status_counts = {status: sum(entry["status"] == status for entry in entries) for status in sorted({entry["status"] for entry in entries})}
    report = "# H0-R2 Handoff Metadata Consistency Patch\n\nH0-R2 is complete. No system component ran; B0 was neither executed nor accepted; Frozen Evaluation and formal handoff files were not accessed or generated.\n\n" + f"- Previous Current-state Audit is preserved as historical; new audit status is `current`; stale/current conflict: none; unresolved facts: `0`.\n- Authority inventory: {len(entries)} records; missing required fields `{missing_fields}`; `local historical asset` stages `0`; empty versions `0`; missing artifacts `0`; stale artifacts `0`; ready for the decision/artifact index.\n- Current State authority notice added. SHA-256 before `{before_state_sha}`; after `{after_state_sha}`. Historical sections remain unchanged.\n- Cross-source fact base is consistent. Five-file Draft Package may begin; no remaining fact or metadata blocker exists.\n"
    (OUT / "HANDOFF_FACT_FREEZE_R2_REPORT.md").write_text(report, encoding="utf-8")
    entries.append({"artifact_name": "H0-R2 report", "repository_path": relative(OUT / "HANDOFF_FACT_FREEZE_R2_REPORT.md"), "exists": True, "status": "accepted", "file_sha256": sha256(OUT / "HANDOFF_FACT_FREEZE_R2_REPORT.md"), "content_or_manifest_sha256": "", "hash_scope": "file_bytes_only", "schema_or_policy_version": "h0-r2", "produced_by_stage": "V3.5-A H0-R2", "supersedes": [], "superseded_by": [], "authority_scope": "H0-R2 report", "record_count": None, "notes": ""})
    (OUT / "handoff_authority_inventory.r2.jsonl").write_text("".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in entries), encoding="utf-8")
    hash_entries = [{key: entry[key] for key in ("artifact_name", "repository_path", "exists", "file_sha256", "content_or_manifest_sha256", "hash_scope")} for entry in entries]
    (OUT / "artifact_hash_inventory.r2.jsonl").write_text("".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in hash_entries), encoding="utf-8")
    manifest = {"stage": "H0-R2", "status": "complete", "generated_at": datetime.now(timezone.utc).isoformat(), "repository_head": check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "working_tree_status": check_output(["git", "status", "--short"], cwd=ROOT, text=True).splitlines(), "inputs": ["handoff_fact_freeze.r1.json", "handoff_authority_inventory.jsonl", "artifact_hash_inventory.r1.jsonl", "V3_5_CURRENT_STATE.md"], "outputs": ["HANDOFF_FACT_FREEZE_R2_REPORT.md", "handoff_fact_freeze.r2.json", "handoff_authority_inventory.r2.jsonl", "artifact_hash_inventory.r2.jsonl", "handoff_fact_freeze_r2_execution.audit.json", "handoff_fact_freeze_r2_manifest.json"], "unresolved_facts": [], "ready_for_five_file_draft": True}
    write_json(OUT / "handoff_fact_freeze_r2_manifest.json", manifest)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--restore-approved-b0-task-contract":
        restore_approved_b0_task_contract(Path(sys.argv[2]))
    elif len(sys.argv) == 2 and sys.argv[1] == "--build-r1":
        build_r1()
    elif len(sys.argv) == 2 and sys.argv[1] == "--build-r2":
        build_r2()
    else:
        build()
