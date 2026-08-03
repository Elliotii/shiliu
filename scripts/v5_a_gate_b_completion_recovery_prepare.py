from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys

from scripts.v5_a_gate_b_postfix_prepare import (
    ACCEPTED_PRODUCT_COMPLETION_HEAD,
    EXPECTED_ORIGINAL_MANIFEST_SHA,
    EXPECTED_ORIGINAL_REPORT_SHA,
    EXPECTED_SCHEMA9_SHA,
    FROZEN_BLOBS,
    WRITE_BITS,
    _git_blob,
    _make_read_only,
    _read_facts,
    _rebind_eval_artifact_paths,
    _sha256,
    _tree_digest,
    _write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-root", type=Path, required=True)
    parser.add_argument("--original-root", type=Path, required=True)
    parser.add_argument("--new-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--implementation-head", required=True)
    parser.add_argument("--joint-test-evidence", required=True)
    parser.add_argument("--default-regression-evidence", required=True)
    args = parser.parse_args()

    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if args.implementation_head != head:
        raise RuntimeError("recovery builder HEAD argument mismatch")
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise RuntimeError("recovery Entry Gate requires a clean worktree")
    subprocess.check_call(
        ["git", "merge-base", "--is-ancestor", ACCEPTED_PRODUCT_COMPLETION_HEAD, head]
    )
    if {path: _git_blob(path) for path in FROZEN_BLOBS} != FROZEN_BLOBS:
        raise RuntimeError("frozen Prompt/Tool/Schema blob mismatch")

    parent = args.parent_root.expanduser().resolve()
    original = args.original_root.expanduser().resolve()
    root = args.new_root.expanduser().resolve()
    if root.exists() or root.parent != parent.parent or parent.parent != original.parent:
        raise RuntimeError("recovery root must be a new sibling")
    if _sha256(original / "manifest.json") != EXPECTED_ORIGINAL_MANIFEST_SHA:
        raise RuntimeError("immutable original manifest mismatch")
    if _sha256(original / "V5_A_STAGE_5_GATE_B_EVALUATION_REPORT.md") != EXPECTED_ORIGINAL_REPORT_SHA:
        raise RuntimeError("immutable original report mismatch")
    if _sha256(original / "eval.schema9.snapshot.db") != EXPECTED_SCHEMA9_SHA:
        raise RuntimeError("immutable schema-9 snapshot mismatch")

    parent_manifest_path = parent / "manifest.json"
    parent_manifest_sha = _sha256(parent_manifest_path)
    parent_eval_sha = _sha256(parent / "eval.db")
    parent_manifest = json.loads(parent_manifest_path.read_text(encoding="utf-8"))
    snapshot = parent_manifest.get("run_budget_snapshot") or {}
    if (
        parent_manifest.get("run_status") != "stopped_fail_closed_no_rerun"
        or snapshot.get("committed_logical_calls") != 4
        or snapshot.get("committed_http_attempts") != 4
        or parent_manifest.get("stop", {}).get("message")
        != "post-fix product Task was left running"
    ):
        raise RuntimeError("parent is not the exact durable continuation boundary")
    if not isinstance(parent_manifest.get("run_budget_policy"), dict):
        raise RuntimeError("parent run budget policy is missing")

    connection = sqlite3.connect(parent / "eval.db")
    try:
        unresolved = int(
            connection.execute(
                "SELECT COUNT(*) FROM research_side_effects "
                "WHERE status IN ('unknown','in_flight')"
            ).fetchone()[0]
        )
        statuses = dict(
            connection.execute("SELECT task_id,status FROM research_tasks").fetchall()
        )
    finally:
        connection.close()
    case_runs = parent_manifest["case_runs"]
    g_task_id = str(case_runs["GB-PC-G-01"]["task_id"])
    policy_task_ids = tuple(parent_manifest["run_budget_policy"]["task_ids"])
    h_task_id = next(value for value in policy_task_ids if value != g_task_id)
    if unresolved or statuses != {g_task_id: "running", h_task_id: "ready"}:
        raise RuntimeError("parent durable Task/SideEffect boundary changed")

    historical = {
        str(path.parent): _sha256(path)
        for path in sorted(root.parent.glob("*/manifest.json"))
    }
    root.mkdir(parents=False)
    (root / "logs").mkdir()
    schema9_copy = root / "eval.schema9.snapshot.db"
    working = root / "eval.db"
    shutil.copy2(original / "eval.schema9.snapshot.db", schema9_copy)
    shutil.copy2(parent / "eval.db", working)
    working.chmod(working.stat().st_mode | stat.S_IWUSR)
    shutil.copytree(original / "artifacts", root / "artifacts", copy_function=shutil.copy2)
    if _tree_digest(root / "artifacts") != _tree_digest(original / "artifacts"):
        raise RuntimeError("recovery artifact identity mismatch")
    _make_read_only(root / "artifacts")
    rebound = _rebind_eval_artifact_paths(working, root / "artifacts")
    if schema9_copy.stat().st_mode & WRITE_BITS:
        raise RuntimeError("recovery schema-9 evidence copy is writable")
    facts = _read_facts(working)
    if facts["schema_version"] != 10 or facts["integrity_check"] != "ok":
        raise RuntimeError("recovery work database preflight failed")

    manifest = dict(parent_manifest)
    for key in (
        "stop",
        "results",
        "run_completed_at",
        "wall_time_seconds",
        "executed_cases",
    ):
        manifest.pop(key, None)
    manifest.update(
        {
            "run_id": args.run_id,
            "run_type": "gate_b_product_completion_durable_recovery",
            "run_status": "entry_gate_pass_recovery_provider_not_started",
            "implementation_head": head,
            "formal_evaluation_root": str(root),
            "credential_access": {"status": "not_accessed"},
            "provider_calls_performed": 4,
            "case_runs": {
                "GB-PC-G-01": {
                    "status": "durable_parent_continuation",
                    "task_id": g_task_id,
                },
                "GB-PC-H-01": {"status": "ready_not_exercised", "task_id": h_task_id},
            },
            "historical_root_manifest_hashes_before_run": historical,
            "recovery_parent": {
                "root": str(parent),
                "run_id": parent_manifest["run_id"],
                "manifest_sha256": parent_manifest_sha,
                "eval_db_sha256": parent_eval_sha,
                "committed_logical_calls": 4,
                "committed_http_attempts": 4,
                "committed_cost_usd": snapshot["committed_cost_usd"],
                "unknown_or_in_flight": 0,
                "G_rerun_forbidden": True,
                "H_previously_exercised": False,
            },
            "eval_snapshot": {
                **parent_manifest["eval_snapshot"],
                "schema10_recovery_pre_run_sha256": _sha256(working),
                "facts": facts,
                "eval_artifact_paths_rebound": rebound,
            },
            "entry_gate": {
                **parent_manifest["entry_gate"],
                "status": "pass",
                "entry_builder_commit": head,
                "stage_1_to_5_joint_targeted_tests": args.joint_test_evidence,
                "default_no_provider_regression": args.default_regression_evidence,
                "durable_parent_hashes": "pass",
                "parent_unknown_or_in_flight": 0,
            },
        }
    )
    _write_json(root / "manifest.json", manifest)
    print(json.dumps({"root": str(root), "manifest_sha256": _sha256(root / "manifest.json")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
