from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "SHILIU_V0_TO_V3_5_FINAL_REPOSITORY_MANIFEST.json"
MARKDOWN_PATH = ROOT / "SHILIU_V0_TO_V3_5_FINAL_REPOSITORY_MANIFEST.md"


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact(
    path: str,
    *,
    status: str,
    authority: str,
    supersedes: str | None = None,
    access_boundary: str | None = None,
) -> dict[str, Any]:
    target = ROOT / path
    if not target.is_file():
        raise FileNotFoundError(path)
    value: dict[str, Any] = {
        "path": path,
        "sha256": file_sha256(target),
        "status": status,
        "authority": authority,
        "supersedes": supersedes,
    }
    if access_boundary:
        value["access_boundary"] = access_boundary
    return value


def git_output(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True
    ).strip()


def build_manifest(repository_commit: str, commit_date: str) -> dict[str, Any]:
    v3_results = json.loads((ROOT / "research/v3_eval/eval_results.json").read_text())
    v35 = json.loads((ROOT / "V3_5_FINAL_CLOSEOUT.json").read_text())

    return {
        "schema_version": "shiliu-v0-v3.5-final-repository-manifest-v1",
        "generated_at": "2026-07-29",
        "scope": {
            "versions": "V0-V3.5",
            "early_versions_detail": "concise",
            "v3_5_detail": "full",
            "v4_planning_or_implementation_included": False,
        },
        "repository": {
            "branch": git_output("branch", "--show-current"),
            "commit": repository_commit,
            "commit_role": "content_baseline_parent_of_manifest_packaging_commit",
            "commit_date": commit_date,
            "manifest_packaging_commit": "SELF",
            "working_tree_status": "clean_after_manifest_packaging_commit",
            "historical_v3_5_source_commit": "91a34061f8aebb216749c015a37a4ff1974f4f2a",
        },
        "formal_components": [
            {
                "name": "retrieval",
                "version": "v3-product-search-default-auto-v1",
                "status": "formal_product_path",
                "authority_hash": None,
                "note": "No monolithic retrieval hash was asserted by the V3.5 final seal.",
            },
            {
                "name": "auto_router",
                "version": "v3-search-planner-auto-v1",
                "status": "formal",
                "authority_hash": "0876dbaff9bb2d016496cc3cb823f200b9a93a06721947bebee472d6a5bdaa7e",
            },
            {
                "name": "evidence_identity",
                "version": "V1",
                "status": "formal",
                "authority_hash": "35691bc6833d44dd09252cc746b3e358e62917422865aba54cbb2d08582329c7",
            },
            {
                "name": "candidate_builder",
                "version": "stage3b-acronym-w3.5-v1",
                "status": "formal_retained_after_f1a_rejection",
                "authority_hash": "7f995a3c1c31eddd0eff6221494dd60032d00a155d431a68c58fb7cf55bbf3c1",
            },
            {
                "name": "fine_selector",
                "version": "v3.5-deterministic-fine-selector-v1",
                "status": "formal_retained_after_f1b_rejection",
                "authority_hash": "350a2aa6fab58580fb259471a7a6b87fc206701189ebb7bff97d031613444c67",
            },
            {
                "name": "mechanical_gate",
                "version": "mechanical-gate-v1-r1",
                "status": "formal",
                "authority_hash": "1577a51e57661a0a8bcbd51cfaed31013bdf2859ab786d67c50f7c42fa84f17c",
            },
            {
                "name": "semantic_sufficiency",
                "version": "v3.5-semantic-sufficiency-policy-v1",
                "status": "formal_below_target",
                "authority_hash": "2e2d90afda5dc6e7f7576742e900782f857622a331303bca18b983d27b645d59",
            },
            {
                "name": "stage5_api_ui_trace",
                "version": "v3.5-stage5-current-integration-refreeze-seal-v1",
                "status": "minimally_product_integrated_limited_pilot",
                "authority_hash": "4ff57a88c23b7f114dcb8f71a1e83e1f127af81a761f439c54d7a28ecde8b40c",
            },
        ],
        "authoritative_documents": [
            artifact(
                "SHILIU_V3_VERSION_DECISION.md",
                status="archived_external_formal_decision",
                authority="V3 version decision",
            ),
            artifact(
                "V3_CLOSEOUT.md",
                status="final",
                authority="V3 repository closeout",
            ),
            artifact(
                "V3_STAGE6B_FORMAL_RETRIEVAL_EVAL_AND_EVIDENCE_REPORT.md",
                status="final",
                authority="V3 formal retrieval evaluation",
            ),
            artifact(
                "V3_5_FINAL_CLOSEOUT.md",
                status="final",
                authority="V3.5 formal narrative closeout",
            ),
            artifact(
                "V3_5_FINAL_CLOSEOUT.json",
                status="final",
                authority="V3.5 machine-readable closeout",
            ),
            artifact(
                "V3_5_V4_READINESS_REPORT.md",
                status="historical_final_readiness",
                authority="V3.5 readiness record; future-version suggestions not inherited",
            ),
            artifact(
                "SHILIU_V0_TO_V3_5_FINAL_CLOSEOUT.md",
                status="final",
                authority="repository-wide V0-V3.5 closeout",
            ),
        ],
        "superseded_documents": [
            artifact(
                "V3_CURRENT_STATE.md",
                status="superseded_historical",
                authority="historical V3 current-state ledger",
                supersedes=None,
            ),
            artifact(
                "V3_5_CURRENT_STATE.md",
                status="superseded_historical",
                authority="historical V3.5 checkpoint ledger",
                supersedes=None,
            ),
            artifact(
                "03_V3_5_DECISION_AND_ARTIFACT_INDEX.md",
                status="superseded_historical_handoff_index",
                authority="historical A-to-B artifact index",
                supersedes=None,
            ),
        ],
        "tests": {
            "deterministic_core": {
                "command": ".venv/bin/python -m pytest",
                "passed": 1405,
                "failed": 0,
                "collection_errors": 0,
                "deselected": 4,
                "clean_index_export_verified": True,
            },
            "key_suites": {
                "retrieval": {"passed": 67, "failed": 0, "status": "passed"},
                "evidence_sufficiency": {"passed": 61, "failed": 0, "status": "passed"},
                "api_stage5": {"passed": 44, "failed": 0, "status": "passed"},
                "minimal_smoke": {
                    "passed": 6,
                    "failed": 0,
                    "status": "passed_in_process_no_paid_provider",
                },
            },
            "external_or_environment_dependent": {
                "markers": ["external_artifact", "live_provider"],
                "default_suite_excludes": True,
                "requirements_documented": True,
            },
            "historical_failures": [],
            "warning": "Starlette/httpx TestClient deprecation; non-failing.",
        },
        "evaluation_artifacts": [
            artifact(
                "research/v3_eval/eval_results.json",
                status="formal_v3_aggregate_result",
                authority="V3 aggregate metrics",
            ),
            artifact(
                "research/v3_eval/eval_queries.locked.jsonl",
                status="formal_v3_case_level",
                authority="V3 locked query set",
                access_boundary="path/hash only in overview documents; no case content reproduced",
            ),
            artifact(
                "research/v3_eval/eval_gold.locked.jsonl",
                status="formal_v3_case_level",
                authority="V3 pooled/judged Gold",
                access_boundary="path/hash only in overview documents; no case content reproduced",
            ),
            artifact(
                "research/v3_5/product_query_set_v1/freeze/product_query_set_v1.manifest.json",
                status="formal_v3_5_dataset_manifest",
                authority="Product Query Set v1 identity",
            ),
            artifact(
                "research/v3_5/product_query_set_v1/split_v1/product_query_split_v1.manifest.json",
                status="formal_v3_5_split_manifest",
                authority="Development/Frozen split identity",
            ),
            artifact(
                "research/v3_5/product_query_set_v1/gold_construction_v1/development_seal_v1/development_gold_v1.seal.json",
                status="formal_v3_5_development_gold_seal",
                authority="Development Gold aggregate seal",
            ),
            artifact(
                "research/v3_5/product_query_set_v1/gold_construction_v1/frozen_guarded/frozen_cycle_v1/internal_protected/frozen_gold_v1.seal.json",
                status="formal_v3_5_frozen_gold_seal",
                authority="protected Frozen Gold aggregate seal",
                access_boundary="protected Gold; seal/path/hash only in overview documents",
            ),
            artifact(
                "research/v3_5/product_query_set_v1/p14_frozen_evaluation/P14_FROZEN_RESULT_FREEZE_SEAL.json",
                status="formal_v3_5_frozen_result_seal",
                authority="P14 aggregate result freeze",
            ),
            artifact(
                "research/v3_5/product_query_set_v1/p14_frozen_evaluation/P14_REPLACEMENT_FORMAL_RUN_MANIFEST.json",
                status="formal_v3_5_run_manifest",
                authority="replacement formal-run identity",
            ),
            artifact(
                "research/v3_5/product_query_set_v1/p14_frozen_evaluation/P14_REPLACEMENT_PREDICTIONS_FREEZE.json",
                status="formal_v3_5_prediction_freeze",
                authority="prediction-before-Gold freeze",
                access_boundary="path/hash only in overview documents; no case content reproduced",
            ),
        ],
        "aggregate_evaluation": {
            "v3": {
                "corpus": {"videos": 144, "retrieval_units": 1555, "transcript_chunks": 1412},
                "query_count": 24,
                "judgment_count": 452,
                "metrics_source": "research/v3_eval/eval_results.json",
                "positive_query_count": len(v3_results.get("per_query", [])) or 22,
                "classification": "pooled_judged_not_exhaustive",
            },
            "v3_5": {
                "query_count": v35["PQS_and_split"]["total_cases"],
                "development_count": v35["PQS_and_split"]["development_cases"],
                "frozen_count": v35["PQS_and_split"]["frozen_cases"],
                "frozen_metrics": v35["frozen_metrics"],
                "aggregate_failure_attribution": v35["frozen_metrics"][
                    "primary_failure_attribution"
                ],
                "case_level_content_included_in_manifest": False,
            },
        },
        "seals_and_manifests": [
            artifact(
                "V3_5_FINAL_FREEZE_SEAL.json",
                status="authoritative_top_level_seal",
                authority="V3.5 final seal",
            ),
            artifact(
                "STAGE5_CURRENT_INTEGRATION_REFREEZE_SEAL.json",
                status="authoritative_stage5_refreeze",
                authority="current API/UI/Trace integration",
            ),
            artifact(
                "SUFFICIENCY_JUDGE_FINAL_FREEZE_SEAL.json",
                status="authoritative_semantic_judge_seal",
                authority="semantic sufficiency policy/implementation",
            ),
            artifact(
                "STAGE4A_R_MECHANICAL_GATE_FREEZE.json",
                status="authoritative_mechanical_gate_seal",
                authority="Mechanical Gate R1",
            ),
            artifact(
                "SELECTOR_V2_FREEZE_SEAL.json",
                status="historical_rejected_candidate_seal",
                authority="selector-v2 experiment provenance; not formal selector promotion",
            ),
        ],
        "representative_traces": [],
        "excluded_local_artifacts": [
            {
                "category": "personal_product_data",
                "examples": ["user SQLite databases", "complete favorites data", "content roots"],
                "deleted": False,
                "policy": "ignored and retained outside the formal Git baseline",
            },
            {
                "category": "provider_and_runtime_state",
                "examples": ["Provider raw logs", "provider state databases", "model caches"],
                "deleted": False,
                "policy": "ignored; no credential-dependent state committed",
            },
            {
                "category": "bulk_case_level_traces",
                "examples": ["intermediate search traces", "candidate dumps", "incomplete work files"],
                "deleted": False,
                "policy": "ignored; formal manifests retain path/hash lineage where required",
            },
            {
                "category": "temporary_and_reproducible",
                "examples": ["temporary exports", "tool caches", "compiled files"],
                "deleted": False,
                "policy": "ignored and reproducible",
            },
        ],
        "generated_artifact_policy": {
            "tracked_and_authoritative": [
                "final closeouts and decisions",
                "machine-readable aggregate results required by the seal chain",
                "freeze/refreeze seals and small reproducibility manifests",
                "minimal deterministic fixtures",
            ],
            "retained_locally_not_tracked": [
                "personal databases and collection content",
                "provider/runtime state",
                "bulk unredacted case-level traces",
            ],
            "reproducible_and_excluded": [
                "caches",
                "temporary exports",
                "compiled files",
                "intermediate work directories",
            ],
            "unknown_pending_review": [],
        },
        "known_limitations": [
            "V3 retrieval evaluation is pooled/judged, not exhaustive-corpus relevance judgment.",
            "V3.5 Evidence/Sufficiency is minimally product-integrated, limited-pilot, formally below target, and partial.",
            "Semantic Judge latency is high and production proxy timeout configuration is external.",
            "Final Answer generation, Agentic Search, Memory, Harness, and automatic remediation are not implemented.",
            "Frozen Builder/Selector implementations are historical baselines, not mandatory future hard dependencies.",
        ],
        "integrity": {
            "case_level_content_reproduced_in_manifest": False,
            "representative_trace_count": 0,
            "unexplained_test_failures": 0,
            "unexplained_tracked_changes": 0,
            "unexplained_untracked_files": 0,
        },
    }


def markdown(manifest: dict[str, Any]) -> str:
    repository = manifest["repository"]
    lines = [
        "# Shiliu V0–V3.5 Final Repository Manifest",
        "",
        "Status: `final`",
        "",
        "This human-readable manifest contains only artifact identity and aggregate",
        "evaluation information. It does not reproduce Case-level queries, Gold,",
        "video identifiers, evidence text, labels, groups, decisions, or failures.",
        "",
        "## Repository baseline",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Branch | `{repository['branch']}` |",
        f"| Content baseline commit | `{repository['commit']}` |",
        f"| Commit date | `{repository['commit_date']}` |",
        "| Manifest packaging commit | `SELF` |",
        f"| Expected final working tree | `{repository['working_tree_status']}` |",
        "",
        "The content baseline commit is the parent of the commit containing the final",
        "Manifest values. `SELF` avoids the impossible requirement for a Git commit",
        "to contain its own hash.",
        "",
        "## Formal components",
        "",
        "| Component | Version | Status | Authority hash |",
        "|---|---|---|---|",
    ]
    for item in manifest["formal_components"]:
        lines.append(
            f"| {item['name']} | `{item['version']}` | `{item['status']}` | "
            f"`{item['authority_hash'] or 'not_asserted'}` |"
        )

    for heading, key in (
        ("Authoritative documents", "authoritative_documents"),
        ("Superseded documents", "superseded_documents"),
        ("Evaluation artifacts", "evaluation_artifacts"),
        ("Seals and manifests", "seals_and_manifests"),
    ):
        lines.extend(
            [
                "",
                f"## {heading}",
                "",
                "| Path | SHA-256 | Status | Authority / boundary |",
                "|---|---|---|---|",
            ]
        )
        for item in manifest[key]:
            authority = item["authority"]
            if item.get("access_boundary"):
                authority += "; " + item["access_boundary"]
            lines.append(
                f"| `{item['path']}` | `{item['sha256']}` | `{item['status']}` | "
                f"{authority} |"
            )

    tests = manifest["tests"]
    aggregate = manifest["aggregate_evaluation"]
    lines.extend(
        [
            "",
            "## Test baseline",
            "",
            f"- Deterministic core: `{tests['deterministic_core']['passed']} passed`, "
            f"`{tests['deterministic_core']['failed']} failed`, "
            f"`{tests['deterministic_core']['collection_errors']} collection errors`, "
            f"`{tests['deterministic_core']['deselected']}` explicitly separated.",
            "- The same core suite passed from a clean staged-index export.",
            "- External requirements are separated with `external_artifact` and",
            "  `live_provider` markers.",
            "- Historical failure whitelist: empty.",
            f"- Retrieval key suite: `{tests['key_suites']['retrieval']['passed']} passed`.",
            f"- Evidence/Sufficiency key suite: "
            f"`{tests['key_suites']['evidence_sufficiency']['passed']} passed`.",
            f"- API/Stage 5 key suite: "
            f"`{tests['key_suites']['api_stage5']['passed']} passed`.",
            f"- Minimal in-process Smoke: "
            f"`{tests['key_suites']['minimal_smoke']['passed']} passed`; no new paid",
            "  Provider call was required. Historical live-provider smoke remains",
            "  bound by the Stage 5 seals.",
            "",
            "## Aggregate evaluation only",
            "",
            f"- V3: {aggregate['v3']['corpus']['videos']} videos, "
            f"{aggregate['v3']['corpus']['retrieval_units']} retrieval units, "
            f"{aggregate['v3']['query_count']} queries, "
            f"{aggregate['v3']['judgment_count']} judgments; pooled/judged, not exhaustive.",
            f"- V3.5: {aggregate['v3_5']['query_count']} total queries, "
            f"{aggregate['v3_5']['development_count']} Development and "
            f"{aggregate['v3_5']['frozen_count']} Frozen.",
            f"- V3.5 Frozen Retrieval Hit@10: "
            f"`{aggregate['v3_5']['frozen_metrics']['retrieval_Hit_at_1_3_5_10'][3]}`.",
            f"- V3.5 Frozen Builder complete-group availability: "
            f"`{aggregate['v3_5']['frozen_metrics']['candidate_builder_complete_group_availability']}`.",
            f"- V3.5 Frozen EvidenceBundle complete-group hit: "
            f"`{aggregate['v3_5']['frozen_metrics']['evidence_bundle_complete_group_hit']}`.",
            f"- V3.5 Frozen semantic four-state accuracy: "
            f"`{aggregate['v3_5']['frozen_metrics']['semantic_four_state_accuracy']}`.",
            "- Aggregate primary attribution: 5 Builder-incomplete and 5",
            "  Mechanical source-unverifiable outcomes.",
            "",
            "## Representative traces",
            "",
            "None. No available raw Trace met the final package's strict redaction",
            "boundary. Formal trace contracts, seals, aggregate results, and test",
            "fixtures are retained without reproducing Query, Gold, video identifiers,",
            "subtitle text, or personal collection data.",
            "",
            "## Excluded local artifacts",
            "",
        ]
    )
    for item in manifest["excluded_local_artifacts"]:
        lines.append(
            f"- `{item['category']}`: {item['policy']}; deleted = "
            f"`{str(item['deleted']).lower()}`."
        )
    lines.extend(["", "## Known limitations", ""])
    for item in manifest["known_limitations"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Machine-readable authority",
            "",
            "See `SHILIU_V0_TO_V3_5_FINAL_REPOSITORY_MANIFEST.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-commit", required=True)
    parser.add_argument("--commit-date", required=True)
    args = parser.parse_args()
    datetime.fromisoformat(args.commit_date.replace("Z", "+00:00"))

    value = build_manifest(args.repository_commit, args.commit_date)
    JSON_PATH.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    MARKDOWN_PATH.write_text(markdown(value), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
