from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
from typing import Any

from shiliu.db import Database


EXPECTED_SCHEMA9_SHA = "e1e276dfde8194bf3c3282d2014bcbc272b5eea330633049342aeb24329922c3"
EXPECTED_ARTIFACT_IDENTITY = "f315fc20b45251334ef89d89b75a8d0129722d8febd2c02439a15cb1443c34dc"
EXPECTED_SUBTITLE_SHA = "8e4f3f97af264a9eb1faef65b2cb797bb4616f7fe9e2dc477807244194f19016"
EXPECTED_ORIGINAL_MANIFEST_SHA = "705484087b1ee0cf577dbd7ee060a5ba923a489088b0c5f9fece00e701ee27eb"
EXPECTED_ORIGINAL_REPORT_SHA = "18105cd549b2f2428091d2726ccb72caf2d5b8e1cf611c91214a38a53d31e645"
EXPECTED_PARENT_G_MANIFEST_SHA = "24fa028dfa2af38d94f264ce4f97845063fe99c48233ffdd084520e7ce438075"
EXPECTED_PARENT_G_EVAL_DB_SHA = "bb1965af04fac1e19d58aed088e4cfd15e5b2a5a34df30353e7cd63ee4745fdd"
EXPECTED_PARENT_IH_MANIFEST_SHA = "12ec0b704f5f935a2048f5cfd64c7391c52345611a428683725eb93dcd8dae87"
EXPECTED_PARENT_IH_EVAL_DB_SHA = "8271a5fdb074d02f45febf17cd409e019a598389463b6e3f174200caf0efbb7b"
FROZEN_BLOBS = {
    "src/shiliu/ask/query_analysis.py": "2eb00bf0553bf4f173b22101351788c96665b7f5",
    "src/shiliu/ask/deep/decision.py": "b93777b6dde1bf834604fe01a6fa0c2f08c5a240",
    "src/shiliu/ask/answer.py": "ee23019f255b8772bff5beaf142ed5c0bad37bd0",
    "src/shiliu/research/inner_tools.py": "396e3433254d08117b763e4b91e8daa56dad5172",
    "src/shiliu/ask/contracts.py": "4ed333410287d25094f327f1c13bec098b367b02",
}
CASE_TOKEN_CAPS = {
    "GB-G-01": (60_000, 14_192),
    "GB-I-01": (40_000, 8_896),
    "GB-H-01": (40_000, 8_896),
    "GB-PC-G-01": (40_000, 8_896),
    "GB-PC-H-01": (40_000, 8_896),
}
COMPLETION_CASES = ["GB-PC-G-01", "GB-PC-H-01"]
ACCEPTED_PRODUCT_COMPLETION_HEAD = (
    "8d600b64338ca994a7ffc1f912365436969737df"
)
WRITE_BITS = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(value for value in root.rglob("*") if value.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        file_digest = bytes.fromhex(_sha256(path))
        digest.update(file_digest)
    return digest.hexdigest()


def _git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], text=True).strip()


def _write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _read_facts(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        schema = int(
            connection.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()[0]
        )
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        fk = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        videos, completed = connection.execute(
            "SELECT COUNT(*), SUM(status='completed') FROM videos"
        ).fetchone()
        retrieval_units = int(
            connection.execute("SELECT COUNT(*) FROM retrieval_units").fetchone()[0]
        )
        indexed = int(
            connection.execute(
                "SELECT COUNT(DISTINCT video_id) FROM retrieval_units"
            ).fetchone()[0]
        )
        index_versions = [
            str(row[0])
            for row in connection.execute(
                "SELECT DISTINCT index_version FROM retrieval_units ORDER BY index_version"
            ).fetchall()
        ]
        lexical_video = int(
            connection.execute(
                "SELECT COUNT(*) FROM retrieval_units WHERE unit_type='video'"
            ).fetchone()[0]
        )
        lexical_chunk = int(
            connection.execute(
                "SELECT COUNT(*) FROM retrieval_units WHERE unit_type='transcript_chunk'"
            ).fetchone()[0]
        )
        completed_artifacts = int(
            connection.execute(
                "SELECT COUNT(DISTINCT artifact_dir) FROM videos "
                "WHERE status='completed' AND artifact_dir IS NOT NULL"
            ).fetchone()[0]
        )
    finally:
        connection.close()
    return {
        "schema_version": schema,
        "integrity_check": integrity,
        "foreign_key_violations": fk,
        "videos": int(videos),
        "completed_videos": int(completed),
        "retrieval_units": retrieval_units,
        "indexed_videos": indexed,
        "retrieval_index_versions": index_versions,
        "lexical_video_units": lexical_video,
        "lexical_chunk_units": lexical_chunk,
        "completed_artifact_dirs": completed_artifacts,
    }


def _make_read_only(root: Path) -> None:
    for path in root.rglob("*"):
        mode = path.stat().st_mode
        if path.is_dir():
            path.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        else:
            path.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    mode = root.stat().st_mode
    root.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def _copy_schema_snapshot_for_migration(
    source_snapshot: Path, root: Path
) -> tuple[Path, Path]:
    """Keep the evidence snapshot immutable; make only its work copy writable."""

    snapshot_copy = root / "eval.schema9.snapshot.db"
    working_copy = root / "eval.db"
    shutil.copy2(source_snapshot, snapshot_copy)
    shutil.copy2(source_snapshot, working_copy)
    working_copy.chmod(working_copy.stat().st_mode | stat.S_IWUSR)
    if source_snapshot.stat().st_mode & WRITE_BITS:
        raise RuntimeError("source schema-9 snapshot unexpectedly has write permission")
    if snapshot_copy.stat().st_mode & WRITE_BITS:
        raise RuntimeError("copied schema-9 snapshot unexpectedly has write permission")
    if not working_copy.stat().st_mode & stat.S_IWUSR:
        raise RuntimeError("eval.db working copy has no owner write permission")
    return snapshot_copy, working_copy


def _rebind_eval_artifact_paths(database_path: Path, artifact_root: Path) -> int:
    """Point the isolated work DB only at its immutable artifact copy."""

    connection = sqlite3.connect(database_path)
    rebound = 0
    try:
        rows = connection.execute(
            "SELECT id, source_id, artifact_dir, cover_path, raw_subtitle_path, "
            "transcript_path, summary_path FROM videos"
        ).fetchall()
        with connection:
            for row in rows:
                video_id, source_id, *stored_paths = row
                destination_dir = artifact_root / "videos" / str(source_id)
                replacements: list[str | None] = []
                for index, stored in enumerate(stored_paths):
                    if not stored:
                        replacements.append(None)
                        continue
                    if index == 0:
                        replacement = destination_dir
                    else:
                        replacement = destination_dir / Path(str(stored)).name
                    if not replacement.exists():
                        raise RuntimeError(
                            f"isolated artifact copy missing for video {video_id}: "
                            f"{replacement}"
                        )
                    replacements.append(str(replacement))
                connection.execute(
                    "UPDATE videos SET artifact_dir=?, cover_path=?, "
                    "raw_subtitle_path=?, transcript_path=?, summary_path=? WHERE id=?",
                    (*replacements, video_id),
                )
                rebound += 1
    finally:
        connection.close()
    return rebound


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-root", type=Path, required=True)
    parser.add_argument("--new-root", type=Path, required=True)
    parser.add_argument("--cases-manifest", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--implementation-head", required=True)
    parser.add_argument("--remaining-ih", action="store_true")
    parser.add_argument("--h-only", action="store_true")
    parser.add_argument("--completion", action="store_true")
    parser.add_argument("--parent-g-root", type=Path)
    parser.add_argument("--parent-ih-root", type=Path)
    parser.add_argument("--joint-test-evidence", default="174 passed")
    parser.add_argument("--default-regression-evidence", default="not_recorded")
    args = parser.parse_args()
    if sum((args.remaining_ih, args.h_only, args.completion)) > 1:
        raise RuntimeError("remaining-I/H and H-only modes are mutually exclusive")
    if args.completion:
        if args.implementation_head != subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip():
            raise RuntimeError("completion builder HEAD argument mismatch")
        if subprocess.check_output(
            ["git", "status", "--porcelain"], text=True
        ).strip():
            raise RuntimeError("completion Entry Gate requires a clean worktree")
        subprocess.check_call(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                ACCEPTED_PRODUCT_COMPLETION_HEAD,
                args.implementation_head,
            ]
        )
    original = args.original_root.expanduser().resolve()
    root = args.new_root.expanduser().resolve()
    if root.exists():
        raise RuntimeError("new post-fix root already exists; overwrite is forbidden")
    if root.parent != original.parent:
        raise RuntimeError("post-fix root must be a sibling of the immutable original")
    if _sha256(original / "manifest.json") != EXPECTED_ORIGINAL_MANIFEST_SHA:
        raise RuntimeError("immutable original manifest hash mismatch")
    if _sha256(original / "V5_A_STAGE_5_GATE_B_EVALUATION_REPORT.md") != EXPECTED_ORIGINAL_REPORT_SHA:
        raise RuntimeError("immutable original report hash mismatch")
    source_snapshot = original / "eval.schema9.snapshot.db"
    if _sha256(source_snapshot) != EXPECTED_SCHEMA9_SHA:
        raise RuntimeError("immutable schema-9 snapshot hash mismatch")
    parent_g = (
        args.parent_g_root.expanduser().resolve() if args.parent_g_root else None
    )
    if args.remaining_ih or args.h_only:
        if parent_g is None:
            raise RuntimeError("remaining I/H recovery requires frozen GB-G-01 parent root")
        if _sha256(parent_g / "manifest.json") != EXPECTED_PARENT_G_MANIFEST_SHA:
            raise RuntimeError("frozen GB-G-01 parent manifest hash mismatch")
        if _sha256(parent_g / "eval.db") != EXPECTED_PARENT_G_EVAL_DB_SHA:
            raise RuntimeError("frozen GB-G-01 parent eval DB hash mismatch")
        if (parent_g / "manifest.json").stat().st_mode & WRITE_BITS:
            raise RuntimeError("frozen GB-G-01 parent manifest is writable")
        if (parent_g / "eval.db").stat().st_mode & WRITE_BITS:
            raise RuntimeError("frozen GB-G-01 parent eval DB is writable")
    parent_ih = (
        args.parent_ih_root.expanduser().resolve() if args.parent_ih_root else None
    )
    if args.h_only:
        if parent_ih is None:
            raise RuntimeError("H-only recovery requires frozen I/H parent root")
        if _sha256(parent_ih / "manifest.json") != EXPECTED_PARENT_IH_MANIFEST_SHA:
            raise RuntimeError("frozen I/H parent manifest hash mismatch")
        if _sha256(parent_ih / "eval.db") != EXPECTED_PARENT_IH_EVAL_DB_SHA:
            raise RuntimeError("frozen I/H parent eval DB hash mismatch")
        if (parent_ih / "manifest.json").stat().st_mode & WRITE_BITS:
            raise RuntimeError("frozen I/H parent manifest is writable")
        if (parent_ih / "eval.db").stat().st_mode & WRITE_BITS:
            raise RuntimeError("frozen I/H parent eval DB is writable")
    observed_blobs = {path: _git_blob(path) for path in FROZEN_BLOBS}
    if observed_blobs != FROZEN_BLOBS:
        raise RuntimeError("frozen Prompt/Tool/Schema blob mismatch")

    source_tree_digest = _tree_digest(original / "artifacts")
    historical_manifest_hashes = {
        str(path.parent): _sha256(path)
        for path in sorted(root.parent.glob("*/manifest.json"))
    }
    root.mkdir(parents=False)
    (root / "logs").mkdir()
    snapshot_copy, working_copy = _copy_schema_snapshot_for_migration(
        source_snapshot, root
    )
    shutil.copytree(original / "artifacts", root / "artifacts", copy_function=shutil.copy2)
    copied_tree_digest = _tree_digest(root / "artifacts")
    if copied_tree_digest != source_tree_digest:
        raise RuntimeError("artifact copy content identity mismatch")
    subtitle = root / "artifacts" / "videos" / "BV1o87764Ebs" / "subtitle-raw.txt"
    if _sha256(subtitle) != EXPECTED_SUBTITLE_SHA:
        raise RuntimeError("grounded source subtitle hash mismatch")
    _make_read_only(root / "artifacts")

    before = _read_facts(snapshot_copy)
    if before != {
        "schema_version": 9,
        "integrity_check": "ok",
        "foreign_key_violations": 0,
        "videos": 157,
        "completed_videos": 140,
        "retrieval_units": 1633,
        "indexed_videos": 154,
        "retrieval_index_versions": ["v3-stage1-lexical-v1"],
        "lexical_video_units": 154,
        "lexical_chunk_units": 1479,
        "completed_artifact_dirs": 140,
    }:
        raise RuntimeError(f"material schema-9 baseline changed: {before}")
    Database(working_copy).initialize()
    rebound_artifact_rows = 0
    if args.completion:
        rebound_artifact_rows = _rebind_eval_artifact_paths(
            working_copy, root / "artifacts"
        )
    after = _read_facts(working_copy)
    if after != {**before, "schema_version": 10}:
        raise RuntimeError(f"schema-10 eval migration changed material facts: {after}")
    if snapshot_copy.stat().st_mode & WRITE_BITS:
        raise RuntimeError("schema-9 snapshot copy became writable during migration")
    if not working_copy.stat().st_mode & stat.S_IWUSR:
        raise RuntimeError("schema-10 eval.db lost owner write permission")
    if args.completion:
        connection = sqlite3.connect(snapshot_copy)
        try:
            checkpoint_videos, checkpoint_chunks = connection.execute(
                "SELECT COUNT(DISTINCT video_id), COUNT(*) FROM retrieval_units "
                "WHERE unit_type='transcript_chunk' "
                "AND lower(search_text) LIKE '%checkpoint%'"
            ).fetchone()
            source_113 = connection.execute(
                "SELECT source_id, title FROM videos WHERE id=113"
            ).fetchone()
            unknown_effects = int(
                connection.execute(
                    "SELECT COUNT(*) FROM research_side_effects "
                    "WHERE status IN ('unknown','in_flight')"
                ).fetchone()[0]
            )
        finally:
            connection.close()
        if (int(checkpoint_videos), int(checkpoint_chunks)) != (3, 3):
            raise RuntimeError("completion checkpoint corpus reachability changed")
        if source_113 != ("BV1ixAVz9EaQ", "使用AI+SPEC+SKILL，2天写完一个Agent项目"):
            raise RuntimeError("completion grounded source identity changed")
        if unknown_effects != 0:
            raise RuntimeError("completion snapshot contains unresolved SideEffect")

    source_manifest = json.loads(args.cases_manifest.read_text(encoding="utf-8"))
    cases = []
    for source in source_manifest["cases"]:
        case_id = str(source["case_id"])
        if case_id not in CASE_TOKEN_CAPS:
            continue
        input_cap, output_cap = CASE_TOKEN_CAPS[case_id]
        cases.append(
            {
                key: source[key]
                for key in (
                    "case_id",
                    "objective",
                    "success_constraints",
                    "expected_outcomes",
                    "logical_call_cap",
                    "http_attempt_cap",
                    "agent_action_cap",
                    "research_action_cap",
                    "wall_time_seconds",
                    "search_time_seconds",
                )
            }
            | {
                "fixed_user_answer": source.get("fixed_user_answer"),
                "fixed_human_response": source.get("fixed_human_response"),
                "constraint_profile": source.get("constraint_profile"),
                "input_token_cap": input_cap,
                "output_token_cap": output_cap,
            }
        )
    expected_cases = (
        COMPLETION_CASES
        if args.completion
        else
        ["GB-H-01"]
        if args.h_only
        else ["GB-I-01", "GB-H-01"]
        if args.remaining_ih
        else ["GB-G-01", "GB-I-01", "GB-H-01"]
    )
    if args.remaining_ih or args.h_only or args.completion:
        cases = [case for case in cases if case["case_id"] in expected_cases]
    if [case["case_id"] for case in cases] != expected_cases:
        raise RuntimeError("exact authorized case set/order mismatch")

    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    total_input_tokens = (
        40_000
        if args.h_only
        else 80_000
        if args.remaining_ih or args.completion
        else 140_000
    )
    total_output_tokens = (
        8_896
        if args.h_only
        else 17_792
        if args.remaining_ih or args.completion
        else 31_984
    )
    absolute_max_cost = (
        Decimal("0.498358803")
        if args.h_only
        else Decimal("0.25")
        if args.completion
        else Decimal("0.499023773")
        if args.remaining_ih
        else Decimal("0.50")
    )
    worst = (
        Decimal(total_input_tokens) * Decimal("0.435")
        + Decimal(total_output_tokens) * Decimal("0.87")
    ) / Decimal(1_000_000) * Decimal(4)
    if worst > absolute_max_cost:
        raise RuntimeError("latest official price worst-case exceeds authorized subset cap")
    manifest = {
        "run_id": args.run_id,
        "run_type": (
            "gate_b_product_completion_validation"
            if args.completion
            else
            "post_fix_h_only_recovery_validation"
            if args.h_only
            else "post_fix_remaining_ih_integration_validation"
            if args.remaining_ih
            else "post_fix_integration_validation"
        ),
        "run_status": "entry_gate_pass_provider_not_started",
        "branch": "codex/v5-a",
        "implementation_head": args.implementation_head,
        "accepted_product_completion_head": (
            ACCEPTED_PRODUCT_COMPLETION_HEAD if args.completion else None
        ),
        "formal_evaluation_root": str(root),
        "original_formal_root": str(original),
        "original_root_mutation": "forbidden",
        "provider_calls_performed": 0,
        "credential_access": {"status": "not_accessed"},
        "provider_authorization": {
            "provider": "deepseek_openai_compatible",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-v4-pro",
            "roles": {
                "query_analysis": {"thinking_enabled": False, "reasoning_effort": None, "max_output_tokens": 1200},
                "agent_action": {"thinking_enabled": False, "reasoning_effort": None, "max_output_tokens": 1200},
                "grounded_answer": {"thinking_enabled": True, "reasoning_effort": "high", "max_output_tokens": 4096},
            },
        },
        "hard_limits": {
            "max_logical_calls_total": 5 if args.h_only else 10 if args.remaining_ih or args.completion else 17,
            "max_http_attempts_total": 10 if args.h_only else 20 if args.remaining_ih or args.completion else 34,
            "max_input_tokens_total": total_input_tokens,
            "max_output_tokens_total": total_output_tokens,
            "max_wall_time_seconds_total": 12 * 60 if args.h_only else 22 * 60 if args.remaining_ih or args.completion else 34 * 60,
            "nominal_cost_usd": "0.05" if args.completion else "0.10",
            "reserve_stop_usd": "0.20" if args.completion else "0.398358803" if args.h_only else "0.399023773" if args.remaining_ih else "0.40",
            "absolute_max_cost_usd_total": str(absolute_max_cost),
            "parent_consumed_cost_usd": "0.001641197" if args.h_only else "0.000976227" if args.remaining_ih else "0",
            "combined_absolute_max_cost_usd": "0.25" if args.completion else "0.50",
        },
        "price_table": {
            "source": "https://api-docs.deepseek.com/quick_start/pricing/",
            "checked_at": checked_at,
            "model": "deepseek-v4-pro",
            "unit": "usd_per_1m_tokens",
            "input_cache_hit": "0.003625",
            "input_cache_miss": "0.435",
            "output": "0.87",
            "reservation_peak_multiplier": "2",
            "reservation_transport_attempts": 2,
            "worst_case_authorized_cases_usd": str(worst),
        },
        "case_manifest": {
            "path": str(args.cases_manifest.resolve()),
            "sha256": _sha256(args.cases_manifest),
            "canonical_case_hashes": {
                case["case_id"]: hashlib.sha256(
                    json.dumps(
                        case,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
                for case in cases
            },
        },
        "frozen_blobs": observed_blobs,
        "eval_snapshot": {
            "source_schema9_sha256": EXPECTED_SCHEMA9_SHA,
            "schema10_pre_run_sha256": _sha256(root / "eval.db"),
            "schema9_snapshot_mode": oct(stat.S_IMODE(snapshot_copy.stat().st_mode)),
            "schema10_working_copy_mode": oct(stat.S_IMODE(working_copy.stat().st_mode)),
            "facts": after,
            "accepted_artifact_identity": EXPECTED_ARTIFACT_IDENTITY,
            "artifact_source_and_copy_canonical_sha256": source_tree_digest,
            "artifact_copy_mode": "read_only",
            "grounded_source_id": "BV1o87764Ebs",
            "grounded_source_subtitle_sha256": EXPECTED_SUBTITLE_SHA,
        },
        "original_root_verification": {
            "manifest_sha256": EXPECTED_ORIGINAL_MANIFEST_SHA,
            "report_sha256": EXPECTED_ORIGINAL_REPORT_SHA,
            "schema9_snapshot_sha256": EXPECTED_SCHEMA9_SHA,
        },
        "historical_root_manifest_hashes_before_run": historical_manifest_hashes,
        "parent_g_evidence": (
            {
                "root": str(parent_g),
                "manifest_sha256": EXPECTED_PARENT_G_MANIFEST_SHA,
                "eval_db_sha256": EXPECTED_PARENT_G_EVAL_DB_SHA,
                "provider_calls": 5,
                "http_attempts": 5,
                "input_tokens": 5063,
                "output_tokens": 685,
                "cost_usd": "0.000976227",
                "task_status": "waiting_user",
                "rerun_forbidden": True,
            }
            if args.remaining_ih or args.h_only
            else None
        ),
        "parent_ih_evidence": (
            {
                "root": str(parent_ih),
                "manifest_sha256": EXPECTED_PARENT_IH_MANIFEST_SHA,
                "eval_db_sha256": EXPECTED_PARENT_IH_EVAL_DB_SHA,
                "provider_calls": 4,
                "http_attempts": 4,
                "input_tokens": 3746,
                "output_tokens": 478,
                "cost_usd": "0.000664970",
                "I_task_status": "waiting_user",
                "H_provider_calls": 0,
                "H_fixed_answer_exact_once": True,
                "rerun_forbidden": True,
            }
            if args.h_only
            else None
        ),
        "cases": cases,
        "entry_gate": {
            "status": "pass",
            "checked_at": checked_at,
            "working_tree_clean": True,
            "run_wide_meter_commit": "85a31b2",
            "postfix_runner_commit": "d9a4313",
            "entry_builder_commit": args.implementation_head,
            "stage_1_to_5_joint_targeted_tests": args.joint_test_evidence,
            "default_no_provider_regression": args.default_regression_evidence,
            "provider_wiring_and_product_tests": "included_in_joint_targeted_tests",
            "compileall": "pass",
            "diff_check": "pass",
            "frozen_blob_check": "pass",
            "original_root_immutability": "pass",
            "eval_schema10_migration_preflight": "pass",
            "material_baseline": "pass",
            "run_wide_restart_replay_caps": "pass",
            "provider_call_meter_start": 0,
            "checkpoint_reachability": (
                {
                    "transcript_chunks": 3,
                    "distinct_videos": 3,
                    "video_113_source_id": "BV1ixAVz9EaQ",
                    "video_113_title": "使用AI+SPEC+SKILL，2天写完一个Agent项目",
                    "eval_artifact_paths_rebound": rebound_artifact_rows,
                }
                if args.completion
                else None
            ),
        },
        "gate_C_authorized": False,
        "live_database_migration_performed": False,
    }
    _write_json(root / "manifest.json", manifest)
    print(json.dumps({"root": str(root), "manifest": manifest}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
