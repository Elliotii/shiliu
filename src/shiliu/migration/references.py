"""Explicit file-to-version bindings; frozen JSON history is never rewritten."""

from __future__ import annotations
import json
import hashlib
from pathlib import Path
from shiliu.migration.values import MigrationRejected

VIDEO_FILES = {"cover_path", "raw_subtitle_path", "transcript_path", "summary_path"}


def reference_index(artifacts):
    index = {}
    for artifact in artifacts:
        for value in {
            artifact["source_file"],
            artifact.get("source_reference", artifact["source_file"]),
            *artifact.get("source_references", []),
        }:
            index.setdefault(value, []).append(artifact["version_id"])
    return index


def bind_row(identity, table, row, out):
    columns = (
        VIDEO_FILES
        if table == "videos"
        else {"snapshot_ref"}
        if table == "assistant_source_revisions"
        else {"output_path"}
        if table == "taxonomy_stage_runs"
        else {"audio_path"}
        if table == "asr_jobs"
        else set()
    )
    descriptors = identity["_descriptor_index"]
    for column in columns:
        value = row.get(column)
        if not value:
            continue  # empty optional path is not missing evidence
        candidates = [
            descriptors[v] for v in identity["artifact_reference_index"].get(value, [])
        ]
        if table == "assistant_source_revisions":
            candidates = [
                a
                for a in candidates
                if a["logical_key"] == "source_snapshot:" + row["revision"]
                and a["source_version"] == row["revision"]
            ]
        elif table == "videos":
            if column == "raw_subtitle_path":
                name = "subtitle-raw" + (
                    ".txt" if str(value).endswith(".txt") else ".json"
                )
            elif column == "cover_path":
                name = "cover.jpg"
            else:
                name = Path(value).name
            candidates = [
                a
                for a in candidates
                if a["video_id"] == row["id"]
                and a["logical_key"] == f"video:{row['id']}:{name}"
            ]
        if not candidates and table == "asr_jobs" and optional_audio(row):
            out[column] = None
            continue
        if len(candidates) != 1:
            raise MigrationRejected(
                "required_file_binding_missing_or_ambiguous", table_name=table
            )
        out[column] = "artifact:" + candidates[0]["version_id"]


def optional_audio(row):
    """Scratch is no longer required after completion/review or durable submit.

    This never changes the ASR status, attempt, upstream ID or uncertainty. A
    no-ID job that could still submit must carry its actual immutable input.
    """
    return row.get("status") in {
        "completed",
        "failed",
        "cancelled",
        "needs_review",
    } or bool(row.get("task_id"))


def verify_file_references(identity, raw, root):
    checked = 0
    optional_missing = 0
    index = identity["artifact_reference_index"]
    descriptors = {a["version_id"]: a for a in identity["artifacts"]}
    for row in raw.get("asr_jobs", []):
        if row.get("audio_path") and not index.get(row["audio_path"]):
            if not optional_audio(row):
                raise MigrationRejected(
                    "required_asr_input_missing", table_name="asr_jobs"
                )
            optional_missing += 1
    for row in raw.get("taxonomy_stage_runs", []):
        value = row.get("output_path")
        if not value:
            continue
        candidates = index.get(value, [])
        if len(candidates) != 1:
            raise MigrationRejected(
                "required_file_binding_missing_or_ambiguous",
                table_name="taxonomy_stage_runs",
            )
        descriptor = descriptors[candidates[0]]
        payload = (root / descriptor["source_file"]).read_bytes()
        hashes = {hashlib.sha256(payload).hexdigest()}
        try:
            hashes.add(
                hashlib.sha256(
                    json.dumps(
                        json.loads(payload),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
            )
        except (ValueError, UnicodeError):
            pass
        if row.get("output_hash") not in hashes:
            raise MigrationRejected(
                "taxonomy_declared_output_hash_mismatch",
                table_name="taxonomy_stage_runs",
            )
        checked += 1
    for row in raw.get("research_knowledge_exports", []):
        value = row.get("relative_path")
        if value and len(index.get(value, [])) != 1:
            raise MigrationRejected(
                "research_export_bytes_missing_or_ambiguous",
                table_name="research_knowledge_exports",
            )
        if value:
            checked += 1
    return {
        "required_ledger_files_verified": checked,
        "optional_asr_scratch_unavailable": optional_missing,
    }


def source_versions(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "source_version" and isinstance(item, str) and item:
                yield item
            else:
                yield from source_versions(item)
    elif isinstance(value, list):
        for item in value:
            yield from source_versions(item)


def verify_raw_identities(identity, raw):
    hashes = {a["sha256"] for a in identity["artifacts"]}
    checked = 0
    for name, rows in raw.items():
        for row in rows:
            for column, value in row.items():
                versions = []
                if (
                    name == "research_evidence_identities"
                    and column == "source_version"
                    and value
                ):
                    versions = [value]
                elif column.endswith("_json") and value:
                    try:
                        versions = source_versions(json.loads(value))
                    except ValueError:
                        continue  # strict typed conversion reports it
                for version in versions:
                    if version.removeprefix("sha256:") not in hashes:
                        raise MigrationRejected(
                            "historical_source_version_bytes_missing", table_name=name
                        )
                    checked += 1
    return checked
