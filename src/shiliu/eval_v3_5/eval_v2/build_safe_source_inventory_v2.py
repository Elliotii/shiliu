"""One-shot Stage 2R-C0 Recovery A v2 build entry point."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from shiliu.eval_v3_5.eval_v2.construction_workspace_export import audit_workspace, export_construction_workspace
from shiliu.eval_v3_5.eval_v2.pilot_coverage_projection import build_existing_pilot_coverage, write_existing_pilot_coverage
from shiliu.eval_v3_5.eval_v2.protected_source_projection import PROTECTED_INPUT_NAMES, build_protected_source_projection
from shiliu.eval_v3_5.eval_v2.safe_development_source_inventory import (
    build_safe_development_source_inventory_v2, write_canonical_json, write_inventory_jsonl,
)


REPOSITORY = Path("/Users/elliot/new-systems/agent-job-prep/Shiliu")
SNAPSHOT_DB = Path("/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db")
SNAPSHOT_HASH = "61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1"
ARTIFACT_ROOT = Path("/Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/artifacts")
ARTIFACT_MANIFEST = REPOSITORY / "research/v3_eval/artifact_manifest.jsonl"
ARTIFACT_MANIFEST_HASH = "36e63e3a510e840f688b7ce5075fef2a0b1f65086c039960632a9ec726dfd08f"
CORPUS_MANIFEST = REPOSITORY / "research/v3_eval/corpus_manifest.json"
FREEZE_MANIFEST = REPOSITORY / "research/v3_5/eval_v2/stage2r_b1_c/canary_freeze_manifest.json"
OUTPUT = REPOSITORY / "research/v3_5/eval_v2/stage2r_c0_inputs"
WORKSPACE = Path("/tmp/shiliu-v3-5-c0-construction-input-v2")

ADJUDICATED = (
    REPOSITORY / "research/v3_5/eval_v2/stage2r_b2/adjudicated_canary_cases.jsonl",
    REPOSITORY / "research/v3_5/eval_v2/stage2r_b2/adjudicated_remaining_pilot_cases.jsonl",
)
PACKETS = (
    REPOSITORY / "research/v3_5/eval_v2/stage2r_b1_b_canary/B1B_V2C_B1A00001_0b975c6b5eb9/human_review_packet.md",
    REPOSITORY / "research/v3_5/eval_v2/stage2r_b1_b_canary/B1B_V2C_B1A00002_fe057eee3b4a/human_review_packet.md",
    REPOSITORY / "research/v3_5/eval_v2/stage2r_b2/V2C_B2P00001/human_review_packet.md",
    REPOSITORY / "research/v3_5/eval_v2/stage2r_b2/V2C_B2P00002/human_review_packet.md",
)


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _resolver(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for record in records:
        run_ids = record["timeline_run_ids"]
        result[record["video_id"]] = {
            "source_artifact_id": record["source_artifact_id"],
            "source_version": record["source_version"],
            "source_type": record["source_type"],
            "source_language": record["source_language"],
            "timeline_run_id": run_ids[0] if len(run_ids) == 1 else None,
        }
    return result


def run() -> dict[str, Any]:
    corpus = json.loads(CORPUS_MANIFEST.read_text(encoding="utf-8"))
    if corpus.get("snapshot_db_sha256") != SNAPSHOT_HASH or Path(corpus.get("snapshot_db_path", "")).resolve() != SNAPSHOT_DB:
        raise RuntimeError("Frozen Authority Identity Not Proven")
    protection = build_protected_source_projection(REPOSITORY / "research/v3_eval")
    first_records, _, _ = build_safe_development_source_inventory_v2(
        snapshot_db_path=SNAPSHOT_DB, snapshot_db_sha256=SNAPSHOT_HASH,
        artifact_root=ARTIFACT_ROOT, artifact_manifest_path=ARTIFACT_MANIFEST,
        artifact_manifest_sha256=ARTIFACT_MANIFEST_HASH, protection=protection,
    )
    pilot = build_existing_pilot_coverage(
        ADJUDICATED, PACKETS, source_metadata_by_video=_resolver(first_records)
    )
    pilot_counts = Counter(str(case["source_video_id"]) for case in pilot["cases"])
    records, manifest, audit = build_safe_development_source_inventory_v2(
        snapshot_db_path=SNAPSHOT_DB, snapshot_db_sha256=SNAPSHOT_HASH,
        artifact_root=ARTIFACT_ROOT, artifact_manifest_path=ARTIFACT_MANIFEST,
        artifact_manifest_sha256=ARTIFACT_MANIFEST_HASH, protection=protection,
        existing_pilot_video_counts=dict(pilot_counts),
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    inventory_path = OUTPUT / "development_source_inventory.safe.v2.jsonl"
    manifest_path = OUTPUT / "development_source_inventory.safe.v2.manifest.json"
    audit_path = OUTPUT / "development_source_inventory.safe.v2.audit.json"
    pilot_path = OUTPUT / "existing_pilot_coverage.safe.v1.json"
    write_inventory_jsonl(records, inventory_path)
    manifest["inventory_sha256"] = _sha(inventory_path)
    manifest["corpus_manifest_path"] = str(CORPUS_MANIFEST)
    manifest["corpus_manifest_sha256"] = _sha(CORPUS_MANIFEST)
    write_canonical_json(manifest, manifest_path)
    write_existing_pilot_coverage(pilot, pilot_path)
    export_args = dict(
        workspace_path=WORKSPACE, repository_root=REPOSITORY, snapshot_db_path=SNAPSHOT_DB,
        inventory_path=inventory_path, inventory_manifest_path=manifest_path,
        pilot_path=pilot_path, freeze_manifest_path=FREEZE_MANIFEST, records=records,
    )
    first_workspace = export_construction_workspace(**export_args)
    first_hashes = dict(first_workspace["asset_sha256"])
    first_workspace_hash = first_workspace["workspace_manifest_sha256"]
    second_workspace = export_construction_workspace(**export_args)
    reproducible = (
        first_hashes == second_workspace["asset_sha256"]
        and first_workspace_hash == second_workspace["workspace_manifest_sha256"]
    )
    workspace_audit = audit_workspace(WORKSPACE)
    if not reproducible or any(
        int(workspace_audit[key]) != 0
        for key in ("forbidden_filename_violation_count", "forbidden_key_violation_count", "secret_violation_count")
    ):
        raise RuntimeError("External Construction Workspace Not Safe")
    audit.update({
        "workspace_audit": workspace_audit,
        "raw_source_export_count": second_workspace["raw_source_export_count"],
        "raw_source_hash_mismatches": second_workspace["raw_source_hash_mismatches"],
        "reproducible_build": reproducible,
        "inventory_sha256": _sha(inventory_path),
        "manifest_sha256": _sha(manifest_path),
        "pilot_coverage_sha256": _sha(pilot_path),
        "workspace_manifest_sha256": second_workspace["workspace_manifest_sha256"],
    })
    write_canonical_json(audit, audit_path)
    return {"records": records, "manifest": manifest, "audit": audit, "pilot": pilot}


if __name__ == "__main__":
    result = run()
    print(json.dumps(result["audit"], ensure_ascii=False, sort_keys=True))

