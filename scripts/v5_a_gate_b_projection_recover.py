from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

from shiliu.research.control_service import ResearchControlService
from shiliu.research.errors import ResearchUnsafeState
from shiliu.research.service import ResearchTaskService

from v5_a_gate_b_postfix_validate import _case_projection, _write_case_evidence, _write_json


EXPECTED_PARENT_MANIFEST_SHA256 = "24fa028dfa2af38d94f264ce4f97845063fe99c48233ffdd084520e7ce438075"
EXPECTED_PARENT_EVAL_DB_SHA256 = "bb1965af04fac1e19d58aed088e4cfd15e5b2a5a34df30353e7cd63ee4745fdd"
EXPECTED_TASK_ID = "rtask_gate_b_postfix_283130062a74810bd319fa9e"

KERNEL_QUERIES = {
    "goals": "SELECT * FROM research_goals WHERE task_id=? ORDER BY revision",
    "attempts": "SELECT * FROM research_attempts WHERE task_id=? ORDER BY ordinal",
    "checkpoints": (
        "SELECT * FROM research_checkpoints WHERE task_id=? ORDER BY created_at, sequence"
    ),
    "events": "SELECT * FROM research_events WHERE task_id=? ORDER BY sequence",
    "traces": "SELECT * FROM research_traces WHERE task_id=? ORDER BY started_at, trace_id",
    "results": "SELECT * FROM research_results WHERE task_id=? ORDER BY created_at, result_id",
    "command_receipts": (
        "SELECT * FROM research_command_receipts WHERE task_id=? ORDER BY created_at, receipt_id"
    ),
    "side_effects": (
        "SELECT * FROM research_side_effects WHERE task_id=? ORDER BY created_at, side_effect_id"
    ),
    "inner_actions": (
        "SELECT * FROM research_inner_actions WHERE task_id=? ORDER BY created_at, action_id"
    ),
    "evidence_uses": (
        "SELECT * FROM research_evidence_uses WHERE task_id=? ORDER BY created_at, evidence_use_id"
    ),
    "evidence_validations": (
        "SELECT * FROM research_evidence_validations WHERE task_id=? ORDER BY observed_at, observation_id"
    ),
    "provisional_artifacts": (
        "SELECT * FROM research_provisional_artifacts WHERE task_id=? ORDER BY created_at, artifact_id"
    ),
    "outer_audits": "SELECT * FROM research_outer_audits WHERE task_id=? ORDER BY rowid",
    "constraint_observations": (
        "SELECT cao.* FROM research_constraint_audit_observations cao "
        "JOIN research_outer_audits oa ON oa.audit_id=cao.audit_id "
        "JOIN research_constraint_specs cs ON cs.constraint_id=cao.constraint_id "
        "WHERE cao.task_id=? ORDER BY oa.rowid, cs.ordinal"
    ),
    "continuation_decisions": (
        "SELECT * FROM research_continuation_decisions WHERE task_id=? ORDER BY rowid"
    ),
    "continuation_seeds": (
        "SELECT * FROM research_continuation_seeds WHERE task_id=? ORDER BY rowid"
    ),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_only_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"file:{path.as_posix()}?mode=ro&immutable=1", uri=True
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    if int(connection.execute("PRAGMA query_only").fetchone()[0]) != 1:
        connection.close()
        raise ResearchUnsafeState("projection recovery connection is not query-only")
    return connection


def _load_raw(connection: sqlite3.Connection, task_id: str) -> dict[str, Any]:
    task = connection.execute(
        "SELECT * FROM research_tasks WHERE task_id=?", (task_id,)
    ).fetchone()
    if task is None:
        raise ResearchUnsafeState("frozen GB-G-01 Task is missing")
    raw: dict[str, Any] = {"task": ResearchTaskService._decode_row(task)}
    for key, query in KERNEL_QUERIES.items():
        raw[key] = [
            ResearchTaskService._decode_row(row)
            for row in connection.execute(query, (task_id,)).fetchall()
        ]
    return raw


def _load_control(connection: sqlite3.Connection, task_id: str) -> dict[str, Any]:
    task = connection.execute(
        "SELECT * FROM research_tasks WHERE task_id=?", (task_id,)
    ).fetchone()
    assert task is not None
    inputs = [
        ResearchControlService._decode(row)
        for row in connection.execute(
            "SELECT * FROM research_input_requests WHERE task_id=? "
            "ORDER BY created_at, input_request_id",
            (task_id,),
        ).fetchall()
    ]
    dispositions = [
        ResearchControlService._decode(row)
        for row in connection.execute(
            "SELECT * FROM research_input_dispositions WHERE task_id=? ORDER BY rowid",
            (task_id,),
        ).fetchall()
    ]
    current = {
        str(value["input_request_id"]): str(value["status"])
        for value in dispositions
    }
    for value in inputs:
        value["current_status"] = current.get(str(value["input_request_id"]), "unknown")
    return {
        "task": ResearchTaskService._decode_row(task),
        "input_requests": inputs,
        "input_dispositions": dispositions,
        "open_input_requests": [
            value for value in inputs if value["current_status"] == "open"
        ],
        "human_decisions": [
            ResearchControlService._decode(row)
            for row in connection.execute(
                "SELECT * FROM research_human_decisions WHERE task_id=? "
                "ORDER BY created_at, decision_id",
                (task_id,),
            ).fetchall()
        ],
    }


def _orchestration_result(raw: dict[str, Any]) -> dict[str, Any]:
    for receipt in reversed(raw["command_receipts"]):
        if receipt["command_id"] == "postfix:GB-G-01:provider-product-once":
            return dict(receipt["response"])
    raise ResearchUnsafeState("frozen GB-G-01 orchestration receipt is missing")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-root", type=Path, required=True)
    parser.add_argument("--recovery-root", type=Path, required=True)
    args = parser.parse_args()
    parent = args.parent_root.expanduser().resolve()
    recovery = args.recovery_root.expanduser().resolve()
    if recovery.exists():
        raise ResearchUnsafeState("projection recovery root already exists")
    if recovery.parent != parent.parent:
        raise ResearchUnsafeState("projection recovery root must be a sibling")
    parent_manifest = parent / "manifest.json"
    parent_db = parent / "eval.db"
    manifest_before = _sha256(parent_manifest)
    db_before = _sha256(parent_db)
    if manifest_before != EXPECTED_PARENT_MANIFEST_SHA256:
        raise ResearchUnsafeState("parent manifest hash mismatch")
    if db_before != EXPECTED_PARENT_EVAL_DB_SHA256:
        raise ResearchUnsafeState("parent eval DB hash mismatch")
    parent_payload = json.loads(parent_manifest.read_text(encoding="utf-8"))
    case = next(
        value for value in parent_payload["cases"] if value["case_id"] == "GB-G-01"
    )

    connection = _read_only_connection(parent_db)
    try:
        raw = _load_raw(connection, EXPECTED_TASK_ID)
        control = _load_control(connection, EXPECTED_TASK_ID)
    finally:
        connection.close()
    projection = _case_projection(
        raw=raw,
        control=control,
        result=_orchestration_result(raw),
        hitl=None,
    )
    if (
        projection["task_status"] != "waiting_user"
        or len(projection["open_input_requests"]) != 1
        or len(projection["provider_receipts"]) != 5
        or projection["provisional_artifact"]["answer_status"] != "valid_insufficient"
        or projection["outer_audit"]["outcome"] != "blocked"
    ):
        raise ResearchUnsafeState("frozen GB-G-01 projection invariant mismatch")

    recovery.mkdir()
    _write_case_evidence(root=recovery, case=case, projection=projection, raw=raw)
    _write_json(recovery / "control_status.json", control)
    completed_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    recovery_manifest = {
        "recovery_type": "read_only_projection_only",
        "completed_at": completed_at,
        "parent_root": str(parent),
        "parent_run_id": parent_payload["run_id"],
        "parent_manifest_sha256": manifest_before,
        "parent_eval_db_sha256": db_before,
        "task_id": EXPECTED_TASK_ID,
        "case_id": "GB-G-01",
        "provider_calls_performed": 0,
        "credential_access_performed": False,
        "parent_provider_rerun_performed": False,
        "projection": {
            "task_status": projection["task_status"],
            "answer_status": projection["provisional_artifact"]["answer_status"],
            "outer_audit_outcome": projection["outer_audit"]["outcome"],
            "open_input_requests": len(projection["open_input_requests"]),
            "provider_receipts": len(projection["provider_receipts"]),
        },
    }
    _write_json(recovery / "recovery_manifest.json", recovery_manifest)
    if _sha256(parent_manifest) != manifest_before or _sha256(parent_db) != db_before:
        raise ResearchUnsafeState("projection recovery mutated frozen parent evidence")
    print(json.dumps(recovery_manifest, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
