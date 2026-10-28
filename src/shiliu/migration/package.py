"""Prepare explicit offline packages. Planning is read-only; copying needs approval.

No daily default, Application, provider, credentials or PostgreSQL connection.
The private plan contains locators and hashes, never source document bodies.
"""

from __future__ import annotations
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
from shiliu.migration.readonly import connect_snapshot
from shiliu.migration.safety import TASK_ROOT, new_package_root
from shiliu.migration.snapshot import sha
from shiliu.migration.values import MigrationRejected
from shiliu.storage.artifacts import artifact_version_id


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def closed(source, expected):
    paths = [
        source,
        *[source.with_name(source.name + s) for s in ("-wal", "-shm", "-journal")],
    ]
    if source.is_symlink() or any(p.is_symlink() for p in source.parents):
        raise MigrationRejected("unsafe_package_source")
    opened = subprocess.run(
        ["/usr/sbin/lsof", "-F", "pn", "--", *[str(p) for p in paths if p.exists()]],
        capture_output=True,
        timeout=20,
    )
    if (
        opened.returncode not in (0, 1)
        or opened.stdout
        or any(p.exists() and p.stat().st_size for p in (paths[1], paths[3]))
    ):
        raise MigrationRejected("package_source_not_closed")
    if sha(source) != expected:
        raise MigrationRejected("package_source_identity_changed")


def reverse_support_policy(payload, audit, expected):
    """Exactly undo the documented stable→draft policy in memory, hash checked.

    Used only for the old producer's overwritten pre-policy stage output. The
    observed post-policy file and audit remain separate immutable original bytes.
    """
    value = json.loads(payload)
    events = json.loads(audit)["events"]
    if not events:
        raise MigrationRejected("empty_reconstruction_audit")
    seen = set()
    for event in events:
        match = re.fullmatch(
            r"(presentation_forms|focus_object_types|use_contexts)\[(\d+)\]\.status",
            event["field_path"],
        )
        if (
            not match
            or event["field_path"] in seen
            or event["original_value"] != "stable"
            or event["normalized_value"] != "draft"
        ):
            raise MigrationRejected("unsupported_reconstruction_event")
        seen.add(event["field_path"])
        node = value[match[1]][int(match[2])]
        if (
            node["temporary_id"] != event["node_id"]
            or node["status"] != "draft"
            or len(set(node["supporting_content_ids"])) != event["support_count"]
            or event["support_count"] >= 2
        ):
            raise MigrationRejected("reconstruction_event_precondition_mismatch")
        node["status"] = "stable"
    result = canonical(value)
    if hashlib.sha256(result).hexdigest() != expected:
        raise MigrationRejected("reconstructed_stage_hash_mismatch")
    return result, len(events)


def private_output(path):
    if (
        path.exists()
        or path.parent.is_symlink()
        or path.parent.stat().st_uid != os.getuid()
        or path.parent.stat().st_mode & 0o077
    ):
        raise MigrationRejected("new_private_plan_required")


def make_plan(audit_path, output):
    private_output(output)
    audit = json.loads(audit_path.read_text())
    source = Path(audit["source"])
    closed(source, audit["source_sha256"])
    if any(
        audit["aggregate"][k]
        for k in ("fk_anomalies", "typed_anomalies", "symlink_rejections")
    ):
        raise MigrationRejected("audit_anomalies_require_review")
    files = audit["files"]
    aliases = defaultdict(set)
    exceptions = []
    for ref in audit["references"]:
        if ref.get("reference_kind") == "directory":
            continue
        path = ref["resolved"]
        if path not in files and not Path(ref["path"]).is_absolute():
            options = [p for p in files if p.endswith("/" + ref["path"])]
            if len(options) == 1:
                path = options[0]
        if path in files:
            aliases[path].add(ref["path"])
        elif ref["table"] == "asr_jobs" and ref["field"] == "audio_path":
            exceptions.append({"kind": "optional_asr_scratch", "key": ref["key"]})
        elif ref["field"].endswith(".lexical_path") and ref["table"] in {
            "ask_runs",
            "ask_events",
        }:
            exceptions.append({"kind": "retired_f1_provenance", "key": ref["key"]})
        else:
            raise MigrationRejected(
                "unresolved_file_reference_requires_review", table_name=ref["table"]
            )
    workspace = "personal:local_operator"
    artifacts = []
    recipes = []

    def add(path, logical, version, video=None, head=False, refs=()):
        f = files[path]
        result = dict(
            source_file="files/" + f["sha256"],
            origin_path=path,
            sha256=f["sha256"],
            byte_size=f["size"],
            relative_key=workspace + "/objects/" + f["sha256"],
            media_type="application/octet-stream",
            version_id=artifact_version_id(workspace, logical, version),
            video_id=video,
            logical_key=logical,
            source_version=version,
            is_head=head,
            created_at="2026-10-24T00:00:00+00:00",
            source_references=sorted(set(refs)),
        )
        artifacts.append(result)
        return result

    with connect_snapshot(source) as c:
        c.row_factory = sqlite3.Row
        principals = {
            r[0]
            for obj in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if not obj[0].startswith("sqlite_")
            and any(
                x[1] == "principal_id"
                for x in c.execute('PRAGMA table_info("' + obj[0] + '")')
            )
            for r in c.execute('SELECT DISTINCT principal_id FROM "' + obj[0] + '"')
            if r[0]
        }
        if principals - {"local_operator"}:
            raise MigrationRejected("review_explicit_owner_mapping")
        # The special producer mismatch is accepted only with this exact inverse
        # recipe, never by weakening declared-hash validation.
        for row in c.execute(
            "SELECT id,output_path,output_hash FROM taxonomy_stage_runs WHERE output_path IS NOT NULL"
        ):
            reference = row["output_path"]
            if not reference:
                continue
            matches = [p for p in files if p == reference or reference in aliases[p]]
            if len(matches) != 1:
                raise MigrationRejected("taxonomy_file_reference_ambiguous")
            path = matches[0]
            payload = Path(path).read_bytes()
            hashes = {hashlib.sha256(payload).hexdigest()}
            try:
                hashes.add(hashlib.sha256(canonical(json.loads(payload))).hexdigest())
            except (ValueError, UnicodeError):
                pass
            if row["output_hash"] in hashes:
                continue
            audit_file = str(
                Path(path).with_name("vocabulary-support-policy-audit.json")
            )
            if audit_file not in files:
                candidate = Path(audit_file)
                roots = [
                    Path(r).resolve() for r in audit["roots"] + audit["reference_roots"]
                ]
                if (
                    not candidate.is_file()
                    or candidate.is_symlink()
                    or any(p.is_symlink() for p in candidate.parents)
                    or not any(candidate.resolve().is_relative_to(r) for r in roots)
                ):
                    raise MigrationRejected("unexplained_taxonomy_output_mismatch")
                files[audit_file] = {
                    "size": candidate.stat().st_size,
                    "sha256": sha(candidate),
                }
            reconstructed, count = reverse_support_policy(
                payload, Path(audit_file).read_bytes(), row["output_hash"]
            )
            descriptor = add(
                path,
                "reconstructed-taxonomy:" + str(row["id"]),
                row["output_hash"],
                refs=[reference],
            )
            descriptor.update(
                source_file="files/" + row["output_hash"],
                sha256=row["output_hash"],
                byte_size=len(reconstructed),
                relative_key=workspace + "/objects/" + row["output_hash"],
                reconstruction={
                    "recipe": "undo-documented-support-policy-v1",
                    "audit_file": audit_file,
                    "audit_sha256": files[audit_file]["sha256"],
                    "event_count": count,
                },
            )
            aliases[path].discard(path)
            recipes.append(
                {
                    "recipe": "undo-documented-support-policy-v1",
                    "events": count,
                    "original_bytes_preserved": True,
                }
            )
        for path, f in files.items():
            add(path, "legacy-file:" + f["sha256"], f["sha256"], refs=aliases[path])
        for row in c.execute("SELECT * FROM videos"):
            for column in (
                "cover_path",
                "raw_subtitle_path",
                "transcript_path",
                "summary_path",
            ):
                reference = row[column]
                if not reference:
                    continue
                options = [
                    p for p in files if p == reference or reference in aliases[p]
                ]
                if len(options) != 1:
                    raise MigrationRejected("video_file_reference_ambiguous")
                path = options[0]
                name = (
                    (
                        "subtitle-raw"
                        + (".txt" if reference.endswith(".txt") else ".json")
                    )
                    if column == "raw_subtitle_path"
                    else "cover.jpg"
                    if column == "cover_path"
                    else Path(reference).name
                )
                add(
                    path,
                    f"video:{row['id']}:{name}",
                    files[path]["sha256"],
                    row["id"],
                    True,
                    [reference],
                )
                # Current text/Markdown material resolves its canonical JSON twin.
                twin = Path(path).with_suffix(".json")
                if str(twin) in files and str(twin) != path:
                    add(
                        str(twin),
                        f"video:{row['id']}:{twin.name}",
                        files[str(twin)]["sha256"],
                        row["id"],
                        True,
                    )
        for row in c.execute(
            "SELECT h.video_id,r.revision,r.snapshot_ref FROM assistant_source_revisions r JOIN assistant_source_heads h ON h.id=r.head_id"
        ):
            options = [p for p in files if row["snapshot_ref"] in aliases[p]]
            if len(options) != 1:
                raise MigrationRejected("snapshot_reference_ambiguous")
            add(
                options[0],
                "source_snapshot:" + row["revision"],
                row["revision"],
                row["video_id"],
                False,
                [row["snapshot_ref"]],
            )
        # Bind every raw identity to the same video's historical logical stream.
        from shiliu.evidence.source import make_source_artifact_id
        from shiliu.evidence.contracts import SourceArtifactReference

        video_by_artifact = {
            make_source_artifact_id(
                SourceArtifactReference(
                    r["platform"],
                    r["source_id"],
                    r["part"],
                    r["subtitle_source"] or "human",
                    r["subtitle_language"] or "zh",
                    "",
                )
            ): r["id"]
            for r in c.execute("SELECT * FROM videos")
        }
        by_hash = defaultdict(list)
        for path, f in files.items():
            by_hash[f["sha256"]].append(path)
        identities = [
            dict(row)
            for row in c.execute(
                "SELECT source_artifact_id,source_version FROM research_evidence_identities"
            )
        ]

        def collect(value):
            if isinstance(value, dict):
                if isinstance(value.get("source_version"), str) and value.get(
                    "source_artifact_id"
                ):
                    identities.append(value)
                for item in value.values():
                    collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)

        for name, table in audit["tables"].items():
            if name.startswith("sqlite_") or "_fts" in name:
                continue
            columns = [
                x["name"] for x in table["columns"] if x["name"].endswith("_json")
            ]
            for column in columns:
                for row in c.execute(
                    'SELECT "'
                    + column
                    + '" FROM "'
                    + name
                    + '" WHERE "'
                    + column
                    + '" IS NOT NULL'
                ):
                    try:
                        collect(json.loads(row[0]))
                    except ValueError:
                        raise MigrationRejected("invalid_historical_json")
        for row in identities:
            vid = video_by_artifact.get(row["source_artifact_id"])
            version = row["source_version"].removeprefix("sha256:")
            if vid is None or not by_hash[version]:
                raise MigrationRejected("raw_identity_video_binding_unresolved")
            add(
                by_hash[version][0],
                f"video:{vid}:subtitle-raw.json",
                version,
                vid,
                False,
            )
    # Repeated equal hashes/versions are one manifest identity. Preserve its head.
    unique = {}
    for a in artifacts:
        key = a["version_id"]
        if key in unique:
            old = unique[key]
            if (old["sha256"], old["logical_key"]) != (a["sha256"], a["logical_key"]):
                raise MigrationRejected("artifact_version_conflict")
            old["is_head"] |= a["is_head"]
            old["source_references"] = sorted(
                set(old["source_references"] + a["source_references"])
            )
        else:
            unique[key] = a
    plan = {
        "format": "shiliu-private-source-plan-v1",
        "audit_sha256": sha(audit_path),
        "source": str(source),
        "source_sha256": audit["source_sha256"],
        "source_schema": audit["aggregate"]["source_schema"],
        "synthetic_only": source.parent.parent == TASK_ROOT / "sources"
        and (source.parent / "synthetic.json").is_file(),
        "files": files,
        "artifacts": list(unique.values()),
        "ownership": {
            "default_principal": "local_operator",
            "principals": {"local_operator": workspace},
        },
        "exceptions": exceptions,
        "normalization_recipes": recipes,
        "roots": audit["roots"] + audit["reference_roots"],
        "planned_at": datetime.now(timezone.utc).isoformat(),
    }
    closed(source, plan["source_sha256"])
    output.write_bytes(canonical(plan))
    output.chmod(0o600)
    return {
        "plan_sha256": sha(output),
        "source_schema": plan["source_schema"],
        "files": len(files),
        "bytes": sum(f["size"] for f in files.values()),
        "versions": len(unique),
        "optional_or_provenance_references": len(exceptions),
        "normalization_recipes": recipes,
    }


def prepare(plan_path, destination, approval_reference):
    if not approval_reference.strip():
        raise MigrationRejected("specific_human_approval_reference_required")
    plan = json.loads(plan_path.read_text())
    if plan["format"] != "shiliu-private-source-plan-v1":
        raise MigrationRejected("invalid_source_plan")
    source = Path(plan["source"])
    closed(source, plan["source_sha256"])
    if (
        destination.exists()
        or destination.parent.resolve() != new_package_root(destination) / "sources"
        or not re.fullmatch("w14_[a-z0-9_]+", destination.name)
    ):
        raise MigrationRejected("new_task_package_required")
    roots = [Path(p).resolve(strict=True) for p in plan["roots"]]
    for name, f in plan["files"].items():
        path = Path(name)
        if (
            path.is_symlink()
            or any(p.is_symlink() for p in path.parents)
            or not any(path.resolve().is_relative_to(r) for r in roots)
            or sha(path) != f["sha256"]
            or path.stat().st_size != f["size"]
        ):
            raise MigrationRejected("approved_file_identity_changed")
    destination.mkdir(mode=0o700)
    (destination / "files").mkdir(mode=0o700)
    with (
        connect_snapshot(source) as reader,
        closing(sqlite3.connect(destination / "source.sqlite3")) as writer,
    ):
        reader.backup(writer)
    for a in plan["artifacts"]:
        target = destination / a["source_file"]
        if target.exists():
            continue
        if recipe := a.get("reconstruction"):
            if sha(Path(recipe["audit_file"])) != recipe["audit_sha256"]:
                raise MigrationRejected("reconstruction_audit_changed")
            payload, _ = reverse_support_policy(
                Path(a["origin_path"]).read_bytes(),
                Path(recipe["audit_file"]).read_bytes(),
                a["sha256"],
            )
            target.write_bytes(payload)
        else:
            with Path(a["origin_path"]).open("rb") as r, target.open("xb") as w:
                shutil.copyfileobj(r, w, 1024 * 1024)
        target.chmod(0o600)
        if sha(target) != a["sha256"]:
            raise MigrationRejected("copied_file_hash_mismatch")
    for name, payload in {
        "artifacts.json": plan["artifacts"],
        "ownership.json": plan["ownership"],
        "package_plan_receipt.json": {
            "plan_sha256": sha(plan_path),
            "source_sha256": plan["source_sha256"],
            "normalization_recipes": plan["normalization_recipes"],
        },
        "historical.json": {
            "task": "shiliu-w01-20261023"
            if new_package_root(destination) == TASK_ROOT
            else "shiliu-w16-20261025",
            "source_kind": "historical",
            "approval_reference": approval_reference,
            "database_sha256": sha(destination / "source.sqlite3"),
        },
    }.items():
        path = destination / name
        path.write_bytes(canonical(payload))
        path.chmod(0o600)
    if plan.get("synthetic_only"):
        if new_package_root(destination) != TASK_ROOT:
            raise MigrationRejected("synthetic_source_for_production_rejected")
        if (
            source.parent.parent != TASK_ROOT / "sources"
            or not (source.parent / "synthetic.json").is_file()
        ):
            raise MigrationRejected("synthetic_provenance_not_verified")
        (destination / "historical.json").unlink()
        marker = destination / "synthetic.json"
        marker.write_bytes(
            canonical({"task": "shiliu-w01-20261023", "synthetic_only": True})
        )
        marker.chmod(0o600)
    closed(source, plan["source_sha256"])
    return destination / "source.sqlite3"


def main():
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    s = p.add_subparsers(dest="command", required=True)
    a = s.add_parser("plan")
    a.add_argument("--audit", type=Path, required=True)
    a.add_argument("--private-plan", type=Path, required=True)
    a = s.add_parser("prepare")
    a.add_argument("--plan", type=Path, required=True)
    a.add_argument("--destination", type=Path, required=True)
    a.add_argument("--approval-reference", required=True)
    args = p.parse_args()
    try:
        if args.command == "plan":
            result = make_plan(args.audit, args.private_plan)
        else:
            prepare(args.plan, args.destination, args.approval_reference)
            result = {"package_prepared": True}
        print(json.dumps(result, sort_keys=True))
    except Exception as error:
        p.exit(
            1,
            json.dumps(
                {
                    "error": str(error)
                    if isinstance(error, MigrationRejected)
                    else "package_input_or_copy_failure"
                }
            )
            + "\n",
        )


if __name__ == "__main__":
    main()
