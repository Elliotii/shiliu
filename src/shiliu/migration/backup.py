"""Paired backup verification for the marker-guarded isolated rehearsal target.

The CLI is shiliu.migration.backup_cli; resource binding remains mandatory.
The target must be quiescent: no Application or background worker is started.
"""

from __future__ import annotations
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from psycopg import sql
from shiliu.config import LIBPQ_DISABLED_PASSFILE
from shiliu.migration.safety import TASK_ROOT, guard, resource_root
from shiliu.migration.snapshot import sha
from shiliu.migration.etl import _connect, _safe_target_path, validate_snapshot
from shiliu.migration.values import MigrationRejected


def _preinstalled_vector_toc(text):
    """Keep every data/constraint/trigger entry; only reuse exact bootstrap DDL."""
    omitted = []
    kept = []
    for line in text.splitlines():
        match = re.match(
            r"^\d+; \d+ \d+ (SCHEMA - shiliu_search|SCHEMA - shiliu|EXTENSION - pg_textsearch|EXTENSION - vector|COMMENT - EXTENSION pg_textsearch|COMMENT - EXTENSION vector)(?: |$)",
            line,
        )
        if match:
            omitted.append(match[1])
            kept.append("; " + line)
        else:
            kept.append(line)
    if sorted(x for x in omitted if not x.startswith("COMMENT - EXTENSION ")) != [
        "EXTENSION - pg_textsearch",
        "EXTENSION - vector",
        "SCHEMA - shiliu",
        "SCHEMA - shiliu_search",
    ]:
        raise MigrationRejected("unexpected_extension_bootstrap_archive")
    return "\n".join(kept) + "\n"


def verify_pair(directory):
    directory = Path(directory)
    from shiliu.migration.deployment import ROOT, binding, private

    root = binding() if directory.parent == ROOT / "backups" else TASK_ROOT
    if directory.is_symlink() or directory.parent.resolve() != root / "backups":
        raise MigrationRejected("unsafe_backup_directory")
    if root == ROOT:
        private(directory)
    manifest = json.loads((directory / "pair.json").read_text())
    if sha(directory / "database.dump") != manifest["dump_sha256"]:
        raise MigrationRejected("backup_dump_hash_mismatch")
    for item in manifest["artifacts"]:
        path = _safe_target_path(
            directory / "artifacts", item["relative_key"], item["workspace_id"]
        )
        if (
            not path.is_file()
            or sha(path) != item["sha256"]
            or path.stat().st_size != item["byte_size"]
        ):
            raise MigrationRejected("backup_artifact_hash_mismatch")
    return manifest


def create_pair(source, config, run_id, directory):
    return _create_pair(
        config, run_id, directory,
        lambda: validate_snapshot(source, config, run_id),
    )


def runtime_report(config):
    """Snapshot the quiescent running database, including post-migration writes.

    This deliberately has no legacy source argument. It verifies the current
    catalog and hashes every mapped row with the existing typed hash contract.
    Writers must be stopped; create_runtime_pair checks stability around dump.
    """
    import hashlib
    import psycopg
    from shiliu.migration.schema import HEAD_REVISION, MIGRATIONS
    from shiliu.migration.catalog import read_catalog
    from shiliu.migration.values import JsonDocument, logical_hash
    from pgvector import Vector

    contract = json.loads((MIGRATIONS / "contracts/runtime_0014_catalog.json").read_text())
    counts, hashes, sequences = {}, {}, {}
    with _connect(config) as conn:
        conn.read_only = True
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        conn.execute("SET LOCAL search_path=pg_catalog")
        catalog = read_catalog(conn)
        revision = conn.execute("SELECT version_num FROM shiliu.alembic_version").fetchone()
        if revision["version_num"] != "0014_assistant_source_patch" or HEAD_REVISION != revision["version_num"]:
            raise MigrationRejected("runtime_backup_revision_mismatch")
        if catalog != contract:
            raise MigrationRejected("runtime_backup_catalog_mismatch")
        for name, table in contract.items():
            columns = {k: dict(v, type=v["type"].replace("timestamp with time zone", "timestamptz"))
                       for k, v in table["columns"].items()}
            pk = next(x["columns"] for x in table["constraints"] if x["kind"] == "p")
            json_fields = [k for k, v in columns.items() if v["type"] == "jsonb"]
            vector_fields = [k for k, v in columns.items() if v["type"].startswith("shiliu.vector")]
            fields = [sql.Identifier(k) for k in columns]
            fields += [sql.SQL("{} IS NULL AS {}").format(
                sql.Identifier(k), sql.Identifier("__sql_null_" + k)
            ) for k in json_fields]
            query = sql.SQL("SELECT {} FROM shiliu.{} ORDER BY {}").format(
                sql.SQL(",").join(fields), sql.Identifier(name),
                sql.SQL(",").join(map(sql.Identifier, pk)),
            )
            count = 0

            def rows():
                nonlocal count
                with conn.cursor(name="runtime_backup_rows") as cursor:
                    cursor.execute(query)
                    for row in cursor:
                        for key in json_fields:
                            if not row.pop("__sql_null_" + key):
                                row[key] = JsonDocument(row[key])
                        for key in vector_fields:
                            if row[key] is not None and not isinstance(row[key], Vector):
                                row[key] = Vector(row[key])
                        count += 1
                        yield row

            hashes[name] = logical_hash(rows(), columns)
            counts[name] = count
            for key, column in columns.items():
                if not column["identity"]:
                    continue
                seq = conn.execute("SELECT pg_get_serial_sequence(%s,%s) seq",
                                   ("shiliu." + name, key)).fetchone()["seq"]
                state = conn.execute(sql.SQL("SELECT last_value,is_called FROM {}").format(
                    sql.Identifier(*seq.split(".")))).fetchone()
                maximum = conn.execute(sql.SQL("SELECT max({}) n FROM shiliu.{}").format(
                    sql.Identifier(key), sql.Identifier(name))).fetchone()["n"]
                if maximum is not None and state["last_value"] + int(state["is_called"]) <= maximum:
                    raise MigrationRejected("runtime_sequence_below_highwater")
                sequences[name + "." + key] = state
        revision = conn.execute("SELECT version_num FROM shiliu.alembic_version").fetchone()
        # Rebuild audit lives outside the application schema, but belongs to
        # the same dump and must remain part of the operational snapshot.
        audit = hashlib.sha256()
        has_audit = conn.execute("SELECT to_regclass('shiliu_migration.rebuild_receipts') t").fetchone()["t"] is not None
        if has_audit:
            for row in conn.execute("SELECT to_jsonb(t)::text payload FROM shiliu_migration.rebuild_receipts t ORDER BY to_jsonb(t)::text"):
                audit.update(row["payload"].encode())
                audit.update(b"\n")
        objects = conn.execute("SELECT workspace_id,relative_key,sha256,byte_size FROM shiliu.artifact_objects ORDER BY workspace_id,relative_key").fetchall()
    return {"kind": "running-database", "revision": revision["version_num"],
            "counts": counts, "logical_hashes": hashes, "sequences": sequences,
            "catalog": catalog, "rebuild_audit_sha256": audit.hexdigest() if has_audit else None,
            "artifacts": objects}


def create_runtime_pair(config, run_id, directory):
    """Pair the current PG and all Artifact objects without fixed-source ETL checks."""
    return _create_pair(config, run_id, directory, lambda: runtime_report(config))


def _create_pair(config, run_id, directory, read_report):
    guard(config, etl=True)
    directory = Path(directory)
    if (
        directory.exists()
        or directory.parent.resolve() != resource_root(config) / "backups"
        or not re.fullmatch("w14_[a-z0-9_]+", directory.name)
    ):
        raise MigrationRejected("backup_requires_new_private_directory")
    report = read_report()
    with _connect(config) as c:
        c.read_only = True
        objects = c.execute(
            "SELECT workspace_id,relative_key,sha256,byte_size FROM shiliu.artifact_objects ORDER BY workspace_id,relative_key"
        ).fetchall()
    directory.mkdir(mode=0o700)
    (directory / "artifacts").mkdir(mode=0o700)
    for item in objects:
        original = _safe_target_path(
            config.artifact_root, item["relative_key"], item["workspace_id"]
        )
        destination = _safe_target_path(
            directory / "artifacts", item["relative_key"], item["workspace_id"]
        )
        destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        with original.open("rb") as reader, destination.open("xb") as writer:
            shutil.copyfileobj(reader, writer, 1024 * 1024)
        destination.chmod(0o600)
        if sha(destination) != item["sha256"]:
            raise MigrationRejected("backup_source_artifact_changed")
    dump = directory / "database.dump"
    done = subprocess.run(
        [
            str(resource_root(config) / "pg/bin/pg_dump"),
            "--dbname",
            config.database_url,
            "--format=custom",
            "--no-owner",
            "--no-acl",
            "--file",
            str(dump),
        ],
        capture_output=True,
        timeout=60,
        env=dict(os.environ, PGPASSFILE=LIBPQ_DISABLED_PASSFILE),
    )
    if done.returncode:
        raise MigrationRejected("isolated_pg_dump_failed")
    dump.chmod(0o600)
    if read_report() != report:
        raise MigrationRejected("backup_target_changed")
    manifest = {
        "format": "shiliu-pg-artifact-pair-v1",
        "run_id": run_id,
        "source_manifest_hash": report.get("manifest_hash"),
        "mapping_version": report.get("mapping_version"),
        "snapshot_kind": report.get("kind", "migration-source"),
        "dump_sha256": sha(dump),
        "artifacts": objects,
        "validation": report,
    }
    (directory / "pair.json").write_text(
        json.dumps(manifest, sort_keys=True, ensure_ascii=False, indent=2)
    )
    (directory / "pair.json").chmod(0o600)
    verify_pair(directory)
    return manifest


def restore_pair(directory, admin, etl):
    guard(admin, admin=True)
    guard(etl, etl=True)
    if (
        resource_root(admin) != resource_root(etl)
        or Path(directory).parent.resolve() != resource_root(etl) / "backups"
        or guard(admin, admin=True)["dbname"] != guard(etl, etl=True)["dbname"]
    ):
        raise MigrationRejected("restore_resource_binding_mismatch")
    manifest = verify_pair(directory)
    import psycopg

    with psycopg.connect(admin.database_url, passfile=LIBPQ_DISABLED_PASSFILE) as c:
        if admin.environment == "production":
            from shiliu.migration.deployment import check_server

            check_server(c)
        # Extension C code is bootstrap-only. The restore role owns the
        # precreated empty schema/extension, without superuser privileges.
        if c.execute(
            "SELECT extversion,n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE extname='vector'"
        ).fetchone() != ("0.8.7", "shiliu"):
            raise MigrationRejected("restore_requires_preinstalled_vector")
        from shiliu.retrieval.bm25 import check_extension
        check_extension(c)
        if c.execute(
            "SELECT 1 FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname IN ('shiliu','shiliu_migration') LIMIT 1"
        ).fetchone():
            raise MigrationRejected("restore_requires_independent_empty_database")
    if any(etl.artifact_root.iterdir()):
        raise MigrationRejected("restore_requires_independent_empty_artifacts")
    listed = subprocess.run(
        [
            str(resource_root(admin) / "pg/bin/pg_restore"),
            "--list",
            str(Path(directory) / "database.dump"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    from uuid import uuid4

    (resource_root(admin) / "execution").mkdir(mode=0o700, exist_ok=True)
    toc = (
        resource_root(admin)
        / "execution"
        / ("restore-toc-" + uuid4().hex + ".list")
    )
    toc.write_text(_preinstalled_vector_toc(listed.stdout))
    toc.chmod(0o600)
    arguments = ["--use-list", str(toc)]
    done = subprocess.run(
        [
            str(resource_root(admin) / "pg/bin/pg_restore"),
            "--dbname",
            admin.database_url,
            "--no-owner",
            "--no-acl",
            "--exit-on-error",
            *arguments,
            str(Path(directory) / "database.dump"),
        ],
        capture_output=True,
        timeout=60,
        env=dict(os.environ, PGPASSFILE=LIBPQ_DISABLED_PASSFILE),
    )
    if done.returncode:
        raise MigrationRejected("isolated_pg_restore_failed")
    from shiliu.migration.schema import grant_roles
    from shiliu.migration.safety import RUN_USER, ETL_USER

    if admin.environment == "production":
        from shiliu.migration.deployment import RUNTIME, ETL

        RUN_USER, ETL_USER = RUNTIME, ETL

    with psycopg.connect(admin.database_url, passfile=LIBPQ_DISABLED_PASSFILE) as c:
        grant_roles(c, runtime_role=RUN_USER, etl_role=ETL_USER)
        for role in (RUN_USER, ETL_USER):
            parts = guard(etl, etl=True)
            c.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(parts["dbname"]), sql.Identifier(role)
                )
            )
    for item in manifest["artifacts"]:
        original = _safe_target_path(
            Path(directory) / "artifacts", item["relative_key"], item["workspace_id"]
        )
        destination = _safe_target_path(
            etl.artifact_root, item["relative_key"], item["workspace_id"]
        )
        if destination.exists():
            raise MigrationRejected("restore_requires_independent_empty_artifacts")
        destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        with original.open("rb") as reader, destination.open("xb") as writer:
            shutil.copyfileobj(reader, writer, 1024 * 1024)
    return manifest
