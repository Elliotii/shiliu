"""Read-only complete Schema26 preflight and bounded typed table views."""

from __future__ import annotations
from datetime import datetime
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from shiliu.migration.stream import (
    closed_reader,
    SourceRows,
    SourceTables,
    converted_tables,
)

from shiliu.migration.schema import MIGRATIONS
from shiliu.migration.safety import guard_source, source_kind
from shiliu.migration.states import (
    TERMINAL,
    summarize,
    forgotten_purge_complete,
    FORGOTTEN_PURGE_COMPLETION,
)
from shiliu.migration.references import (
    reference_index,
    bind_row,
    verify_raw_identities,
    verify_file_references,
)
from shiliu.migration.source_contract import check_columns
from shiliu.migration.ownership import load_ownership, owner_for, artifact_workspace
from shiliu.migration.values import JsonDocument, MigrationRejected, convert


@lru_cache(maxsize=1)
def mapping():
    return json.loads((MIGRATIONS / "contracts/schema26_target.json").read_text())


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def inspect_snapshot(source: Path):
    source = guard_source(source)
    initial_hash = sha(source)
    provenance = source_kind(source)
    if (
        not provenance["synthetic_only"]
        and provenance["database_sha256"] != initial_hash
    ):
        raise MigrationRejected("approved_source_identity_mismatch")
    manifest_path = source.parent / "artifacts.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise MigrationRejected("artifact_manifest_missing")
    artifacts = json.loads(manifest_path.read_text())
    vector_file = source.parent / "synthetic_vectors.json"
    vectors = []
    if vector_file.exists():
        if not provenance["synthetic_only"]:
            raise MigrationRejected("synthetic_vectors_for_historical_source_rejected")
        if vector_file.is_symlink():
            raise MigrationRejected("unsafe_synthetic_vectors")
        vectors = json.loads(vector_file.read_text())
        import math

        for vector in vectors:
            data = vector["values"]
            if (
                len(data) != 512
                or not all(type(x) in {int, float} and math.isfinite(x) for x in data)
                or abs(math.sqrt(sum(x * x for x in data)) - 1) > 0.01
            ):
                raise MigrationRejected("invalid_synthetic_vector")
    if not isinstance(artifacts, list):
        raise MigrationRejected("invalid_artifact_manifest")
    for a in artifacts:
        relative = Path(a["source_file"])
        if relative.is_absolute() or ".." in relative.parts:
            raise MigrationRejected("unsafe_source_artifact")
        path = source.parent / relative
        if (
            path.is_symlink()
            or not path.is_file()
            or path.resolve().parent != source.parent / "files"
        ):
            raise MigrationRejected("artifact_missing_or_unsafe")
        if sha(path) != a["sha256"] or path.stat().st_size != a["byte_size"]:
            raise MigrationRejected("artifact_hash_mismatch")
    # The only legal SQLite connection in this module is explicit immutable RO.
    with closed_reader(source) as conn:
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise MigrationRejected("source_fk_orphan")
        source_contract = json.loads(
            (MIGRATIONS / "contracts/schema26_target.json").read_text()
        )
        actual = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        expected = {
            t for t, v in source_contract["tables"].items() if v["source"] is not None
        }
        expected |= {
            x["name"]
            for x in source_contract["excluded_source_objects"]
            if x["database"] == "main" and x["type"] == "table"
        }
        if actual != expected:
            raise MigrationRejected("source_table_set_mismatch")
        raw = SourceTables()
        variants = []
        for table, t in source_contract["tables"].items():
            if t["source"] is None:
                continue
            actual_columns = [
                dict(r) for r in conn.execute(f'PRAGMA table_xinfo("{table}")')
            ]
            variants.extend(
                check_columns(table, actual_columns, t["source"]["columns"])
            )
            pk = [
                c["name"]
                for c in sorted(t["source"]["columns"], key=lambda x: x["pk"])
                if c["pk"]
            ]
            count = conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            if count:
                raw[table] = SourceRows(source, table, pk, count)
        version = conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()
        if version is None or str(version[0]) != "26":
            raise MigrationRejected("unsupported_source_schema")
    if sha(source) != initial_hash:
        raise MigrationRejected("source_changed_during_inspection")
    normalization_file = source.parent / "normalization.json"
    if normalization_file.is_symlink():
        raise MigrationRejected("unsafe_normalization_evidence")
    normalization = (
        json.loads(normalization_file.read_text())
        if normalization_file.exists()
        else None
    )
    identity = {
        "normalization": normalization,
        "etl_contract": "w14-full-v2",
        "database_sha256": initial_hash,
        "source_schema": 26,
        "source_head": source_contract["source_head"],
        "mapping_version": source_contract["mapping_version"],
        "mapping_sha256": sha(MIGRATIONS / "contracts/schema26_target.json"),
        "artifacts": artifacts,
        "synthetic_vectors": vectors,
        "artifact_reference_index": reference_index(artifacts),
        "source_variants": variants,
        "provenance": provenance,
        "ownership": load_ownership(
            source.parent / "ownership.json", synthetic=provenance["synthetic_only"]
        ),
    }
    identity["state_dispositions"] = summarize(raw, identity)
    identity["file_reference_dispositions"] = verify_file_references(
        identity, raw, source.parent
    )
    identity["raw_identity_references_verified"] = verify_raw_identities(identity, raw)
    identity["manifest_hash"] = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    identity["_descriptor_index"] = {a["version_id"]: a for a in artifacts}
    return identity, raw


def plan_snapshot(source: Path):
    identity, raw = inspect_snapshot(source)
    result = converted_tables(identity, raw)
    # Preflight every typed value without retaining a table in memory. A plan
    # must reject malformed input before any target connection is opened.
    for rows in result.values():
        for _ in rows:
            pass
    return identity, result


def convert_snapshot(identity, raw, *, artifacts=True):
    contract = mapping()
    tables = contract["tables"]
    result = {}

    def only(table, key, value):
        if hasattr(raw, "parent"):
            return raw.parent(table, key, value)
        found = [r for r in raw.get(table, []) if r[key] == value]
        if len(found) != 1:
            raise MigrationRejected("missing_or_ambiguous_source_parent")
        return found[0]

    for name, rows in raw.items():
        target = tables[name]
        converted = []
        for row in rows:
            owner, workspace = owner_for(identity, row)
            out = {}
            for key, definition in target["columns"].items():
                if "source" in definition:
                    out[key] = convert(row[key], definition, field=name + "." + key)
                elif key == "workspace_id":
                    out[key] = workspace
                elif key in {"principal_id", "owner_user_id"}:
                    out[key] = owner
                elif key in {"insertion_seq", "membership_seq"}:
                    out[key] = row["__source_rowid"]
                elif key == "scope_space_id":
                    if row["scope_kind"] == "user":
                        out[key] = None
                    else:
                        text = row["scope_id"]
                        try:
                            value = int(text)
                        except (ValueError, TypeError):
                            raise MigrationRejected("invalid_memory_scope") from None
                        if str(value) != text:
                            raise MigrationRejected("noncanonical_memory_scope")
                        out[key] = value
                elif key == "video_id" and name == "assistant_source_revisions":
                    out[key] = only("assistant_source_heads", "id", row["head_id"])[
                        "video_id"
                    ]
                elif name == "research_evidence_provenance" and key in {
                    "task_id",
                    "goal_id",
                    "attempt_id",
                }:
                    use = only(
                        "research_evidence_uses",
                        "evidence_use_id",
                        row["evidence_use_id"],
                    )
                    action = only(
                        "research_inner_actions", "action_id", row["action_id"]
                    )
                    if use[key] != action[key]:
                        raise MigrationRejected("evidence_parent_root_mismatch")
                    out[key] = use[key]
                elif definition["default"] is not None:
                    default = definition["default"]
                    if definition["type"] in {"bigint", "integer"}:
                        out[key] = int(default)
                    elif definition["type"] in {"text", "tsvector"}:
                        out[key] = ""
                    else:
                        raise MigrationRejected("unreviewed_added_column_default")
                elif definition["nullable"]:
                    out[key] = None
                else:
                    raise MigrationRejected("unmapped_required_column")
            if name == "ask_runs" and out["lifecycle_status"] == "running":
                out.update(
                    lifecycle_status="failed", termination_reason="migration_owner_loss"
                )
            # No state blanket reset. ASR task_id, Jobs, Research epoch/unknown,
            # Context/seq and historical aggregate usage are retained verbatim.
            if name == "assistant_memories" and out["status"] in {
                "forgotten",
                "superseded",
            }:
                out["tokenized_text"] = ""
                out["search_vector"] = ""
            if (
                name == "assistant_jobs"
                and out["kind"] in {"memory_index", "memory_purge"}
                and out["status"] not in TERMINAL
            ):
                legacy = out["payload_json"].value
                memory = only("assistant_memories", "id", legacy.get("memory_id"))
                out["payload_json"] = JsonDocument(
                    {
                        "memory_id": memory["id"],
                        "version": memory["version"],
                        "change_epoch": memory["change_epoch"],
                        "storage_backend": "pgvector",
                        "requires_projection": memory["status"] == "active",
                    }
                )
                out["status"] = "blocked"
                out["last_error_code"] = "migration_projection_pending"
                if forgotten_purge_complete(row, memory, owner):
                    # A deterministic completion receipt, in the same typed
                    # batch as the Job. This timestamp is an input-derived
                    # audit anchor, never a claimed historical worker finish.
                    memory_updated = convert(
                        memory["updated_at"],
                        tables["assistant_memories"]["columns"]["updated_at"],
                        field="assistant_memories.updated_at",
                    )
                    completed = max(out["updated_at"], memory_updated)
                    out["payload_json"].value["migration_completion"] = {
                        "policy": FORGOTTEN_PURGE_COMPLETION,
                        "time_basis": "max_source_job_and_memory_updated_at",
                        "audit_anchor": completed.isoformat(),
                    }
                    out.update(
                        status="completed",
                        completed_at=completed,
                        updated_at=completed,
                        lease_owner=None,
                        lease_until=None,
                        last_error_code=None,
                        last_error_message=None,
                    )
            bind_row(identity, name, row, out)
            converted.append(out)
        result[name] = converted
    if not artifacts:
        return result
    # Files are exported as explicit manifest rows; canonical raw identity never
    # depends on a temporary source/target absolute path.
    objects = []
    versions = []
    heads = []
    for a in identity["artifacts"]:
        workspace = artifact_workspace(identity, a)
        objects.append(
            dict(
                workspace_id=workspace,
                sha256=a["sha256"],
                relative_key=a["relative_key"],
                byte_size=a["byte_size"],
                media_type=a["media_type"],
                created_at=datetime.fromisoformat(a["created_at"]),
            )
        )
        versions.append(
            dict(
                id=a["version_id"],
                workspace_id=workspace,
                video_id=a["video_id"],
                logical_key=a["logical_key"],
                source_version=a["source_version"],
                object_sha256=a["sha256"],
                created_at=datetime.fromisoformat(a["created_at"]),
            )
        )
        if a.get("is_head", True):
            heads.append(
                dict(
                    workspace_id=workspace,
                    logical_key=a["logical_key"],
                    artifact_version_id=a["version_id"],
                )
            )
    for n, rows in [
        ("artifact_objects", objects),
        ("artifact_versions", versions),
        ("artifact_heads", heads),
    ]:
        if rows:
            result[n] = list(
                {tuple((k, v) for k, v in row.items()): row for row in rows}.values()
            )
    if identity["synthetic_vectors"]:
        from pgvector import Vector

        profile_identity = {
            "model_id": "synthetic-fixed512",
            "model_revision": "w04-fixture-only",
            "dimension": 512,
            "dtype": "float32",
            "normalized": True,
            "provider_version": "synthetic-v1",
            "document_policy_version": "w04-synthetic-collection-v1",
            "tokenizer_revision": "synthetic",
            "max_tokens": 512,
        }
        profile_id = hashlib.sha256(
            json.dumps(profile_identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        result["embedding_profiles"] = [
            dict(
                profile_id=profile_id,
                identity=JsonDocument(profile_identity),
                **profile_identity,
            )
        ]
        result["collection_embeddings"] = []
        for vector in identity["synthetic_vectors"]:
            matches = [
                r
                for r in result.get("retrieval_units", [])
                if r["unit_id"] == vector["unit_id"]
            ]
            if len(matches) != 1:
                raise MigrationRejected("synthetic_vector_unit_missing")
            unit = matches[0]
            result["collection_embeddings"].append(
                dict(
                    unit_id=unit["unit_id"],
                    profile_id=profile_id,
                    workspace_id=unit["workspace_id"],
                    source_content_hash=unit["content_hash"],
                    embedding_text_hash=hashlib.sha256(
                        unit["source_text"].encode()
                    ).hexdigest(),
                    generation=unit["generation"],
                    embedding=Vector(vector["values"]),
                    created_at=unit["archived_at"]
                    or datetime.fromisoformat("2026-10-23T00:00:00+00:00"),
                    updated_at=datetime.fromisoformat("2026-10-23T00:00:00+00:00"),
                )
            )
    return result
