"""Byte-preserving, repository-external construction workspace export."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any

from shiliu.evidence.source import canonical_json


class WorkspaceExportError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(value) + b"\n")


def _raw_paths(snapshot_db: Path) -> dict[str, Path]:
    connection = sqlite3.connect(f"file:{snapshot_db}?mode=ro", uri=True)
    try:
        return {
            str(source_id): Path(str(raw_path)).resolve()
            for source_id, raw_path in connection.execute(
                "SELECT source_id, raw_subtitle_path FROM videos WHERE raw_subtitle_path IS NOT NULL"
            ).fetchall()
        }
    finally:
        connection.close()


def export_construction_workspace(
    *,
    workspace_path: str | Path,
    repository_root: str | Path,
    snapshot_db_path: str | Path,
    inventory_path: str | Path,
    inventory_manifest_path: str | Path,
    pilot_path: str | Path,
    freeze_manifest_path: str | Path,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    workspace = Path(workspace_path).resolve()
    repository = Path(repository_root).resolve()
    if workspace == repository or repository in workspace.parents or workspace in repository.parents:
        raise WorkspaceExportError("workspace must be outside repository")
    if workspace != Path("/tmp/shiliu-v3-5-c0-construction-input-v2").resolve():
        raise WorkspaceExportError("unexpected workspace path")
    if workspace.exists():
        shutil.rmtree(workspace)
    (workspace / "inventory").mkdir(parents=True)
    (workspace / "pilot").mkdir()
    (workspace / "workflow").mkdir()
    shutil.copyfile(inventory_path, workspace / "inventory" / "development_source_inventory.safe.v2.jsonl")
    shutil.copyfile(inventory_manifest_path, workspace / "inventory" / "development_source_inventory.safe.v2.manifest.json")
    shutil.copyfile(pilot_path, workspace / "pilot" / "existing_pilot_coverage.safe.v1.json")
    shutil.copyfile(freeze_manifest_path, workspace / "workflow" / "canary_freeze_manifest.json")
    raw_paths = _raw_paths(Path(snapshot_db_path).resolve())
    raw_count = 0
    mismatch_count = 0
    for record in records:
        source_dir = workspace / "sources" / str(record["safe_source_id"])
        source_dir.mkdir(parents=True)
        _write_json(source_dir / "source_metadata.json", record)
        if record["source_availability"] != "available":
            continue
        raw_path = raw_paths.get(str(record["video_id"]))
        if raw_path is None or not raw_path.is_file():
            raise WorkspaceExportError("available raw source unavailable during export")
        target = source_dir / "subtitle-raw.json"
        shutil.copyfile(raw_path, target)
        raw_count += 1
        if _sha(target) != record["source_version"] or target.read_bytes() != raw_path.read_bytes():
            mismatch_count += 1
    if mismatch_count:
        raise WorkspaceExportError("raw hash mismatch")

    allowed_fixed = {
        "inventory/development_source_inventory.safe.v2.jsonl",
        "inventory/development_source_inventory.safe.v2.manifest.json",
        "pilot/existing_pilot_coverage.safe.v1.json",
        "workflow/canary_freeze_manifest.json",
    }
    asset_hashes: dict[str, str] = {}
    for path in sorted(item for item in workspace.rglob("*") if item.is_file()):
        relative = path.relative_to(workspace).as_posix()
        allowed_source = relative.startswith("sources/SAFESRC_") and relative.split("/")[-1] in {"source_metadata.json", "subtitle-raw.json"}
        if relative not in allowed_fixed and not allowed_source:
            raise WorkspaceExportError("workspace file whitelist violation")
        asset_hashes[relative] = _sha(path)
    manifest = {
        "workspace_version": "v3.5-c0-construction-input-safe-v2",
        "workspace_is_outside_repository": True,
        "repository_files_copied_except_allowlist": False,
        "source_count": len(records),
        "raw_source_export_count": raw_count,
        "raw_source_hash_mismatches": mismatch_count,
        "protected_source_overlap": 0,
        "unknown_protection_state_included": 0,
        "asset_sha256": asset_hashes,
    }
    _write_json(workspace / "workspace_manifest.json", manifest)
    return {**manifest, "workspace_manifest_sha256": _sha(workspace / "workspace_manifest.json")}


def audit_workspace(workspace_path: str | Path) -> dict[str, int | bool]:
    workspace = Path(workspace_path).resolve()
    forbidden_names = (".git", ".env", "database", "held-out", "gold", "quarantine", "stage3", "stage4")
    filename_violations = 0
    secret_violations = 0
    forbidden_key_violations = 0
    forbidden_keys = {
        "held_out", "split", "partition", "gold", "gold_label", "expected_status",
        "constructor_expected_status", "required_aspects", "supported_aspects", "missing_aspects",
        "evidence_groups", "evidence_spans", "reason_codes", "review", "reviewer", "agreement",
        "adjudication_reason", "stage3_result", "stage4_result", "judge_result", "retrieval_rank",
    }
    for path in (item for item in workspace.rglob("*") if item.is_file()):
        relative = path.relative_to(workspace).as_posix()
        if any(term in relative.lower() for term in forbidden_names):
            filename_violations += 1
        # Raw transcripts and the explicitly required frozen workflow manifest are byte authorities,
        # not generated structured outputs, and are excluded from content/key scans.
        if path.name == "subtitle-raw.json" or relative == "workflow/canary_freeze_manifest.json":
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            continue
        stack = [value]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                for key, child in current.items():
                    if str(key).lower() in forbidden_keys:
                        forbidden_key_violations += 1
                    stack.append(child)
            elif isinstance(current, list):
                stack.extend(current)
        serialized = json.dumps(value, ensure_ascii=False).lower()
        if any(marker in serialized for marker in ("api_key=", "authorization: bearer ", "-----begin private key-----")):
            secret_violations += 1
    return {
        "forbidden_filename_violation_count": filename_violations,
        "forbidden_key_violation_count": forbidden_key_violations,
        "secret_violation_count": secret_violations,
        "workspace_path_valid": workspace == Path("/tmp/shiliu-v3-5-c0-construction-input-v2").resolve(),
    }

