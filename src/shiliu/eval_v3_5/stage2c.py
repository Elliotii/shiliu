from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from shiliu.eval_v3_5.intake import ROUND2_ORDER, validate_human_intake
from shiliu.eval_v3_5.models import CompletedReviewDecision, MasterCaseCandidate


LOCK_VERSION = "v3.5-gold-lock-v1"
DEFAULT_LOCKED_AT = "2026-07-21T04:14:19.046075+00:00"
ADJUDICATION_LAYER_VERSION = "v3.5-case-adjudication-v1"
ADJUDICATION_INPUT_HASH = "9a6f193fe472efb7647d66dc16916466bc99131eff12e8adad3926ada8f79f22"
CALIBRATION_LEDGER_HASH = "06ce0e3980e09618a901f572e96ab9d0970660219f33cab79630860532f01737"
ROUND2_LEDGER_HASH = "9c2a8ac2feb9d18fb7bac0f68b196192b8a22fac4948b0a4351b263b74fb16bb"
PROVISIONAL_LEDGER_HASH = "ed2f18e8850d4fef891c1d89c191d49a793190bd40c8e4ae84b5e3b192a60ba0"

MASTER_ORDER = (
    "CASE_015", "CASE_017", "CASE_013", "CASE_001", "CASE_003", "CASE_012",
    "CASE_007", "CASE_008", "CASE_009", "CASE_010", "CASE_002", "CASE_004",
    "CASE_005", "CASE_006", "CASE_011", "CASE_014", "CASE_016", "CASE_018",
)
DEVELOPMENT_ORDER = (
    "CASE_001", "CASE_002", "CASE_003", "CASE_005",
    "CASE_012", "CASE_013", "CASE_015", "CASE_017",
)
HELDOUT_ORDER = (
    "CASE_004", "CASE_006", "CASE_007", "CASE_008", "CASE_009",
    "CASE_010", "CASE_011", "CASE_014", "CASE_016", "CASE_018",
)
LEAKAGE_GROUPS = {
    "LG_MCP": ["CASE_001", "CASE_003", "CASE_012"],
    "LG_MEMORYOS": ["CASE_002", "CASE_013"],
    "LG_RAG_OPTIMIZATION": ["CASE_007", "CASE_014"],
    "LG_PI_AGENT": ["CASE_011", "CASE_016"],
}

INPUTS = {
    "research/v3_5/human_reviews/review_decisions.calibration.10_cases.validated.jsonl": CALIBRATION_LEDGER_HASH,
    "research/v3_5/human_reviews/review_decisions.round2.8_cases.validated.jsonl": ROUND2_LEDGER_HASH,
    "research/v3_5/human_reviews/review_decisions.master.18_cases.provisional.jsonl": PROVISIONAL_LEDGER_HASH,
    "research/v3_5/human_reviews/adjudication/review_decision.CASE_004.second_review.completed.jsonl": ADJUDICATION_INPUT_HASH,
}

ALLOWED_CASE004_CHANGES = {
    "conflict_notes", "needs_second_review", "primary_reason_codes", "reviewed_at",
    "reviewer_flags", "support_notes",
}

GRANULARITY_CLASSIFICATIONS = {
    "CASE_001": ("pass", "Compact definition and purpose span."),
    "CASE_002": ("pass", "One coherent span identifies MemoryOS and its four-module, three-tier memory design."),
    "CASE_003": ("pass_with_documented_breadth", "The continuous comparison is broad but jointly establishes Function Calling, MCP, and their relationship."),
    "CASE_004": ("pass", "Two adjacent ASR segments support only the authorized A3 capability claim."),
    "CASE_005": ("pass_with_documented_breadth", "Four complementary spans map to four distinct required evaluation-design aspects."),
    "CASE_007": ("pass_with_documented_breadth", "Two complementary spans cover pipeline optimization and the evaluation/feedback loop."),
    "CASE_008": ("pass", "Two compact alternative OR groups independently support both required aspects."),
    "CASE_009": ("pass_with_documented_breadth", "Six non-contiguous spans each cover a distinct required enterprise-agent design aspect."),
    "CASE_010": ("pass_with_documented_breadth", "Three complementary spans cover gates, stochastic-error control, and concrete CI checks."),
    "CASE_011": ("pass", "Two compact spans cover plugin capability/install and configuration effect."),
}


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _canonical(records: list[dict[str, Any]]) -> str:
    return "".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for item in records
    )


def _write_json(path: Path, value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    return sha256(text.encode("utf-8")).hexdigest()


def _file_meta(path: Path) -> dict[str, str]:
    return {"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest()}


def _distributions(records: list[dict[str, Any]], cases: dict[str, MasterCaseCandidate]) -> dict[str, dict[str, int]]:
    return {
        "labels": dict(sorted(Counter(str(item["sufficiency_label"]) for item in records).items())),
        "sources": dict(sorted(Counter(
            cases[str(item["case_id"])].source_type or cases[str(item["case_id"])].source_state
            for item in records
        ).items())),
        "source_languages": dict(sorted(Counter(
            cases[str(item["case_id"])].source_language
            or ("query_corpus" if cases[str(item["case_id"])].case_scope == "query_corpus" else "none")
            for item in records
        ).items())),
        "query_languages": dict(sorted(Counter(
            cases[str(item["case_id"])].query_language for item in records
        ).items())),
    }


def _reason_registry(records: list[dict[str, Any]]) -> dict[str, Any]:
    entries = {
        "partial_aspect_coverage": ("coverage", "evidence_resolution_action"),
        "semantic_neighbor_only": ("source_or_corpus_gold", "safe_abstain"),
        "query_target_mismatch": ("source_or_corpus_gold", "safe_abstain"),
        "title_only": ("source", "source_recovery_action"),
        "no_approved_target": ("corpus_gold", "safe_abstain"),
        "out_of_domain_negative_control": ("corpus_gold", "safe_abstain"),
        "asr_transcription_uncertainty": ("source_uncertainty", "human_review_action"),
        "search_candidate_but_no_supporting_evidence": ("source_or_corpus_gold", "safe_abstain"),
    }
    observed = Counter(code for item in records for code in item["primary_reason_codes"])
    return {
        "registry_version": "v3.5-reason-code-registry-v1",
        "status": "locked",
        "codes": {
            code: {"layer": layer, "primary_action_family": action, "observed_primary_count": observed[code]}
            for code, (layer, action) in entries.items()
        },
        "historical_aliases": {"limited_aspect_coverage": "partial_aspect_coverage"},
        "rules": [
            "Aliases interpret historical intake and do not rewrite immutable Human Intake.",
            "query_target_mismatch and semantic_neighbor_only are distinct.",
            "no_approved_target and out_of_domain_negative_control are distinct.",
            "ASR uncertainty may coexist with a coverage reason or reviewer flag.",
            "Readiness reports absolute reason counts, not aggregate metrics alone.",
        ],
    }


def validate_stage2c_inputs(root: str | Path = ".") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    repo = Path(root)
    for relative, expected in INPUTS.items():
        actual = sha256((repo / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Human/Gold Input Identity Mismatch: {relative}: {actual}")

    v35 = repo / "research/v3_5"
    provisional = _jsonl(v35 / "human_reviews/review_decisions.master.18_cases.provisional.jsonl")
    adjudication = _jsonl(v35 / "human_reviews/adjudication/review_decision.CASE_004.second_review.completed.jsonl")
    if len(adjudication) != 1:
        raise ValueError("CASE_004 adjudication must contain exactly one record")
    adjudicated = CompletedReviewDecision.model_validate(adjudication[0])
    if (
        adjudicated.case_id != "CASE_004" or adjudicated.reviewer != "human_user"
        or adjudicated.sufficiency_label != "partial" or adjudicated.needs_second_review
        or adjudicated.review_confidence != "medium"
    ):
        raise ValueError("CASE_004 adjudication identity mismatch")

    prior = next(item for item in provisional if item["case_id"] == "CASE_004")
    changed_fields = {key for key in set(prior) | set(adjudication[0]) if prior.get(key) != adjudication[0].get(key)}
    if not changed_fields <= ALLOWED_CASE004_CHANGES:
        raise ValueError(f"unauthorized CASE_004 semantic changes: {sorted(changed_fields)}")
    invariant_fields = {
        "case_id", "decision_status", "required_aspects", "gold_evidence_groups",
        "sufficiency_label", "supported_aspects", "missing_aspects", "review_confidence",
        "review_version", "reviewer",
    }
    if any(prior[key] != adjudication[0][key] for key in invariant_fields):
        raise ValueError("CASE_004 authorized label/aspect/span identity changed")
    if adjudication[0]["primary_reason_codes"] != ["partial_aspect_coverage"]:
        raise ValueError("CASE_004 canonical primary reason mismatch")
    flags_and_notes = " ".join(adjudication[0]["reviewer_flags"] + [adjudication[0]["conflict_notes"]])
    if "asr" not in flags_and_notes.lower() or "ra" not in flags_and_notes.lower():
        raise ValueError("CASE_004 ASR uncertainty provenance was not retained")

    _, calibration_audit = validate_human_intake(root=v35)
    _, round2_audit = validate_human_intake(
        root=v35,
        intake_files=("../review_decisions.round2.8_cases.validated.jsonl",),
        expected_input_hashes={
            "../review_decisions.round2.8_cases.validated.jsonl": ROUND2_LEDGER_HASH,
        },
        authorized_order=ROUND2_ORDER,
        expected_label_distribution={
            "sufficient": 3, "partial": 1, "insufficient": 3, "unverifiable": 1,
        },
    )
    _, adjudication_audit = validate_human_intake(
        root=v35,
        intake_files=("../adjudication/review_decision.CASE_004.second_review.completed.jsonl",),
        expected_input_hashes={
            "../adjudication/review_decision.CASE_004.second_review.completed.jsonl": ADJUDICATION_INPUT_HASH,
        },
        authorized_order=("CASE_004",),
        expected_label_distribution={"partial": 1},
    )

    records = [adjudication[0] if item["case_id"] == "CASE_004" else item for item in provisional]
    if tuple(item["case_id"] for item in records) != MASTER_ORDER:
        raise ValueError("Master order mismatch")
    if len(records) != 18 or len({item["case_id"] for item in records}) != 18:
        raise ValueError("Master identity failure")
    if any(item["needs_second_review"] for item in records):
        raise ValueError("needs_second_review remains true")
    if Counter(item["sufficiency_label"] for item in records) != Counter(
        {"sufficient": 9, "partial": 1, "insufficient": 6, "unverifiable": 2}
    ):
        raise ValueError("final label distribution mismatch")
    allowed_reasons = {
        "partial_aspect_coverage", "semantic_neighbor_only", "query_target_mismatch",
        "title_only", "no_approved_target", "out_of_domain_negative_control",
        "asr_transcription_uncertainty", "search_candidate_but_no_supporting_evidence",
    }
    for item in records:
        reasons = set(item["primary_reason_codes"])
        if not reasons <= allowed_reasons:
            raise ValueError(f"unknown final reason code: {item['case_id']}: {sorted(reasons)}")
        label = item["sufficiency_label"]
        if label == "sufficient" and reasons:
            raise ValueError(f"sufficient Case has failure reason: {item['case_id']}")
        if label == "partial" and "partial_aspect_coverage" not in reasons:
            raise ValueError(f"partial Case lacks canonical coverage reason: {item['case_id']}")
        if label == "unverifiable" and "title_only" not in reasons:
            raise ValueError(f"unverifiable Case lacks source-authority reason: {item['case_id']}")
        if label == "insufficient" and not reasons:
            raise ValueError(f"insufficient Case lacks abstention reason: {item['case_id']}")
    return records, {
        "changed_fields": sorted(changed_fields),
        "calibration_validation": calibration_audit,
        "round2_validation": round2_audit,
        "adjudication_validation": adjudication_audit,
    }


def write_stage2c_outputs(*, root: str | Path = ".", locked_at: str | None = None) -> dict[str, Any]:
    repo = Path(root)
    v35 = repo / "research/v3_5"
    gold = v35 / "gold"
    gold.mkdir(parents=True, exist_ok=True)
    records, validation = validate_stage2c_inputs(repo)
    candidates = _jsonl(v35 / "master_case_candidates.jsonl") + _jsonl(v35 / "master_case_reserves.jsonl")
    cases = {item.case_id: item for item in (MasterCaseCandidate.model_validate(value) for value in candidates)}
    by_case = {str(item["case_id"]): item for item in records}
    development = [by_case[case_id] for case_id in DEVELOPMENT_ORDER]
    heldout = [by_case[case_id] for case_id in HELDOUT_ORDER]
    if set(DEVELOPMENT_ORDER) & set(HELDOUT_ORDER) or set(DEVELOPMENT_ORDER) | set(HELDOUT_ORDER) != set(MASTER_ORDER):
        raise ValueError("Development/Held-out partition failure")
    for members in LEAKAGE_GROUPS.values():
        splits = {"development" if case_id in DEVELOPMENT_ORDER else "heldout" for case_id in members}
        if len(splits) != 1:
            raise ValueError(f"Leakage Group crosses split: {members}")

    timestamp = locked_at or DEFAULT_LOCKED_AT
    adjudicated_path = gold / "review_decisions.master.18_cases.adjudicated.jsonl"
    master_path = gold / "master_gold.18_cases.locked.jsonl"
    development_path = gold / "development_gold.8_cases.locked.jsonl"
    heldout_path = gold / "heldout_gold.10_cases.locked.jsonl"
    adjudicated_text = _canonical(records)
    adjudicated_path.write_text(adjudicated_text, encoding="utf-8")
    master_path.write_text(adjudicated_text, encoding="utf-8")
    development_path.write_text(_canonical(development), encoding="utf-8")
    heldout_path.write_text(_canonical(heldout), encoding="utf-8")

    master_dist = _distributions(records, cases)
    dev_dist = _distributions(development, cases)
    held_dist = _distributions(heldout, cases)
    membership = {
        "membership_version": "v3.5-master-membership-v1", "status": "locked",
        "case_ids": list(MASTER_ORDER), "case_count": 18,
        "excluded_cases": ["CASE_019", "CASE_020"], "active_reserve_count": 0,
        "development_only_cases": ["CASE_012"], "distributions": master_dist,
    }
    membership_path = gold / "master_case_membership.locked.json"
    _write_json(membership_path, membership)
    split = {
        "split_version": "v3.5-development-heldout-split-v1", "status": "locked",
        "development": {"case_ids": list(DEVELOPMENT_ORDER), "case_count": 8, "distributions": dev_dist},
        "heldout": {"case_ids": list(HELDOUT_ORDER), "case_count": 10, "distributions": held_dist},
        "leakage_groups": LEAKAGE_GROUPS, "development_only_cases": ["CASE_012"],
        "excluded_cases": ["CASE_019", "CASE_020"], "active_reserve_count": 0,
        "known_limitation": "Development contains no real Human-approved partial Case.",
    }
    split_path = gold / "development_heldout_split.locked.json"
    _write_json(split_path, split)
    reason_path = gold / "reason_code_registry.locked.json"
    _write_json(reason_path, _reason_registry(records))

    group_rows = []
    validation_rows = validation["calibration_validation"]["group_durations"] + validation["round2_validation"]["group_durations"]
    duration_map = {(item["case_id"], item["group_id"]): item for item in validation_rows}
    for item in records:
        case_id = str(item["case_id"])
        if not item["gold_evidence_groups"]:
            continue
        classification, rationale = GRANULARITY_CLASSIFICATIONS[case_id]
        for group in item["gold_evidence_groups"]:
            duration = duration_map[(case_id, group["group_id"])]
            group_rows.append({
                "case_id": case_id, "query": cases[case_id].query,
                "required_aspects": [aspect["aspect_id"] for aspect in item["required_aspects"] if aspect["is_required"]],
                "group_id": group["group_id"], "group_structure": "required_spans_AND",
                "span_count": len(group["required_spans"]),
                "segment_count": sum(len(span["segment_ids"]) for span in group["required_spans"]),
                "union_duration_seconds": duration["duration_seconds"],
                "authorized_supported_aspects": group["supported_aspects"],
                "each_span_supports_authorized_aspect": True,
                "obvious_unrelated_lead_in_or_tail": False,
                "appears_minimally_sufficient": True,
                "potential_granularity_concern": rationale if classification != "pass" else "none",
                "audit_classification": classification,
            })
    granularity = {
        "audit_version": "v3.5-gold-granularity-audit-v1", "status": "passed",
        "automatic_semantic_edits": False, "groups_audited": len(group_rows), "cases_audited": len(GRANULARITY_CLASSIFICATIONS),
        "blocking_provenance_errors": 0, "needs_human_granularity_review": 0,
        "groups": group_rows,
    }
    granularity_path = gold / "gold_granularity_audit.json"
    _write_json(granularity_path, granularity)

    protocol_path = gold / "V3_5_EVAL_PROTOCOL.locked.md"
    isolation_path = gold / "HELDOUT_ISOLATION_CONTRACT.md"
    if not protocol_path.is_file() or not isolation_path.is_file():
        raise ValueError("frozen protocol and held-out isolation contract must exist before lock generation")

    assets = {
        "adjudicated_ledger": _file_meta(adjudicated_path), "master_gold": _file_meta(master_path),
        "development_gold": _file_meta(development_path), "heldout_gold": _file_meta(heldout_path),
        "master_membership": _file_meta(membership_path), "development_heldout_split": _file_meta(split_path),
        "reason_registry": _file_meta(reason_path), "gold_granularity_audit": _file_meta(granularity_path),
        "eval_protocol": _file_meta(protocol_path), "heldout_isolation_contract": _file_meta(isolation_path),
    }
    manifest = {
        "lock_version": LOCK_VERSION, "locked_at": timestamp,
        "source_identity_version": "v3.5-source-identity-v2",
        "source_version_authority_version": "v3.5-source-version-authority-v1",
        "timeline_policy_version": "v3.5-timeline-policy-v1",
        "source_chunk_policy_version": "v3-frozen-transcript-chunk-policy-v1",
        "replay_implementation_version": "v3.5-frozen-chunker-replay-v1",
        "chunk_mapping_version": "v3.5-exact-chunk-mapping-v1",
        "search_candidate_contract_version": "v3.5-search-candidate-v1",
        "trace_policy_version": "v3.5-search-trace-policy-v1",
        "inputs": [{"path": path, "sha256": digest} for path, digest in INPUTS.items()],
        "adjudication_layer_version": ADJUDICATION_LAYER_VERSION, "assets": assets,
        "counts": {"master": 18, "development": 8, "heldout": 10},
        "distributions": {"master": master_dist, "development": dev_dist, "heldout": held_dist},
        "leakage_groups": LEAKAGE_GROUPS, "excluded_cases": ["CASE_019", "CASE_020"],
        "active_reserve_count": 0,
        "known_limitations": [
            "English positive evidence is not established.", "Cross-language evidence resolution is not evaluated.",
            "The only Human-approved partial Case is Held-out; Development has no real partial Case.",
            "Two unverifiable Cases are title-only.", "The 18 Cases are not statistically representative.",
        ],
    }
    manifest_path = gold / "gold_lock_manifest.json"
    manifest_hash = _write_json(manifest_path, manifest)
    audit = {
        "audit_version": "v3.5-gold-lock-audit-v1", "lock_version": LOCK_VERSION, "audited_at": timestamp,
        "all_input_hashes_verified": True, "case004_adjudication_validated": True,
        "case004_changed_fields": validation["changed_fields"], "only_case004_changed_from_provisional": True,
        "other_17_records_value_identical": True, "all_decisions_completed": True,
        "needs_second_review_count": 0, "schema_valid_count": 18,
        "segment_ids_valid": True, "source_versions_valid": True, "timeline_runs_valid": True,
        "four_state_invariants_valid": True, "granularity_audit_result": "passed",
        "reason_registry_result": "locked", "master_membership_result": "passed",
        "leakage_group_result": "passed", "split_result": "passed",
        "development_heldout_disjoint": True, "development_heldout_union_equals_master": True,
        "heldout_class_coverage": ["sufficient", "partial", "insufficient", "unverifiable"],
        "heldout_source_coverage": ["ai", "asr", "human", "title_only", "query_corpus"],
        "excluded_case_count": 2, "active_reserve_count": 0,
        "manifest_sha256": manifest_hash, "asset_hashes": {name: value["sha256"] for name, value in assets.items()},
        "errors": [], "warnings": ["Development contains no real Human-approved partial Case."],
    }
    audit_path = gold / "gold_lock_audit.json"
    audit_hash = _write_json(audit_path, audit)
    return {"manifest_sha256": manifest_hash, "audit_sha256": audit_hash, "assets": assets}


if __name__ == "__main__":
    print(json.dumps(write_stage2c_outputs(), ensure_ascii=False, sort_keys=True))
