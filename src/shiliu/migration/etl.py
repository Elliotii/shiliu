"""Bounded Schema26 importer, with atomic batch receipts.

No Application/provider import. Stable PK batches and their receipts commit
atomically; terminal Research cycles defer only inside the required transaction.
"""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import shutil

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from shiliu.config import PostgresConfig, LIBPQ_DISABLED_PASSFILE
from shiliu.migration.safety import guard, guard_input_target
from shiliu.migration.schema import HEAD_REVISION
from shiliu.migration.snapshot import (
    mapping,
    plan_snapshot,
    inspect_snapshot,
    convert_snapshot,
    sha,
)
from shiliu.migration.stream import BatchSource
from shiliu.migration.ownership import artifact_workspace
from shiliu.migration.values import JsonDocument, MigrationRejected, logical_hash

POINTERS = {
    "assistant_source_heads": ("current_revision",),
    "research_tasks": ("active_goal_id", "terminal_result_id"),
    "research_attempts": ("result_id",),
    "research_goals": ("created_by_event_id",),
}


def _connect(config):
    guard(config, etl=True)
    conn = psycopg.connect(
        config.database_url,
        passfile=LIBPQ_DISABLED_PASSFILE,
        row_factory=dict_row,
        options="-c search_path=pg_catalog,shiliu -c timezone=UTC -c lock_timeout=3000 -c statement_timeout=60000 -c idle_in_transaction_session_timeout=30000",
        connect_timeout=2,
    )
    try:
        if config.environment == "production":
            from shiliu.migration.deployment import check_server

            check_server(conn)
        from pgvector.psycopg import register_vector

        register_vector(conn)
        conn.commit()
    except Exception:
        conn.close()
        raise MigrationRejected("etl_vector_registration_failed") from None
    return conn


def _adapt(value):
    return Jsonb(value.value) if isinstance(value, JsonDocument) else value


def _initial(table, row):
    result = dict(row)
    for key in POINTERS.get(table, ()):
        result[key] = None
    if table == "research_tasks" and result["status"] == "terminal":
        # Keep terminal status and result pointer intact. The explicit Research
        # cycle group below inserts its required parents in the same transaction.
        result["terminal_result_id"] = row["terminal_result_id"]
    return result


def _read_row(conn, table, row, contract):
    columns = contract["columns"]
    keys = contract["pk"]
    fields = [sql.Identifier(k) for k in columns]
    json_fields = [k for k in columns if columns[k]["type"] == "jsonb"]
    fields += [
        sql.SQL("{} IS NULL AS {}").format(
            sql.Identifier(k), sql.Identifier("__sql_null_" + k)
        )
        for k in json_fields
    ]
    found = conn.execute(
        sql.SQL("SELECT {} FROM shiliu.{} WHERE {}").format(
            sql.SQL(",").join(fields),
            sql.Identifier(table),
            sql.SQL(" AND ").join(
                sql.SQL("{}=%s").format(sql.Identifier(k)) for k in keys
            ),
        ),
        [_adapt(row[k]) for k in keys],
    ).fetchone()
    if found is not None:
        for k in json_fields:
            is_null = found.pop("__sql_null_" + k)
            if not is_null:
                found[k] = JsonDocument(found[k])
    return found


def _insert(conn, table, row):
    cols = list(row)
    conn.execute(
        sql.SQL("INSERT INTO shiliu.{} ({}) VALUES ({})").format(
            sql.Identifier(table),
            sql.SQL(",").join(map(sql.Identifier, cols)),
            sql.SQL(",").join(sql.Placeholder() for _ in cols),
        ),
        [_adapt(row[k]) for k in cols],
    )


def _same(expected, actual, definition):
    return actual is not None and logical_hash(
        [expected], definition["columns"]
    ) == logical_hash([actual], definition["columns"])


def _binding(row, identity):
    if (
        row["source_manifest_hash"] != identity["manifest_hash"]
        or row["mapping_version"] != identity["mapping_version"]
        or row["target_revision"] != HEAD_REVISION
    ):
        raise MigrationRejected("migration_input_identity_conflict")


def _root_contract(conn):
    if conn.execute("SELECT version_num FROM shiliu.alembic_version").fetchall() != [
        {"version_num": HEAD_REVISION}
    ]:
        raise MigrationRejected("migration_revision_mismatch")
    if conn.info.server_version != 180006:
        raise MigrationRejected("migration_server_mismatch")
    if conn.execute(
        "SELECT extversion FROM pg_extension WHERE extname='vector'"
    ).fetchone() != {"extversion": "0.8.7"}:
        raise MigrationRejected("migration_vector_version_mismatch")
    role = conn.execute(
        "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user"
    ).fetchone()
    if role is None or any(role.values()):
        raise MigrationRejected("privileged_etl_role_rejected")


def _ready_table(conn, name, rows, tables, pending):
    # Tables with external parents wait; known mutable cyclic pointers are
    # intentionally NULL in phase one and restored after all parent rows exist.
    for row in rows:
        for key, parent, _ in mapping()["json_scope_guards"].get(name, []):
            if (
                isinstance(row[key], JsonDocument)
                and row[key].value
                and parent in pending
            ):
                return False
        row = _initial(name, row)
        for f in tables[name]["foreign_keys"]:
            if f["table"] == name:
                continue
            values = [row[c] for c in f["columns"]]
            if any(v is None for v in values):
                continue
            if f["table"] in pending:
                return False
    return True


def _insert_ordered(conn, name, rows, tables):
    definition = tables[name]
    waiting = list(rows)
    while waiting:
        progress = False
        for row in list(waiting):
            start = _initial(name, row)
            existing = _read_row(conn, name, row, definition)
            if existing is not None:
                if not (
                    _same(row, existing, definition)
                    or _same(start, existing, definition)
                ):
                    raise MigrationRejected(
                        "same_primary_key_different_payload",
                        table_name=name,
                        record_key={k: row[k] for k in definition["pk"]},
                    )
                waiting.remove(row)
                progress = True
                continue
            blocked = False
            for f in definition["foreign_keys"]:
                if f["table"] != name:
                    continue
                values = [start[c] for c in f["columns"]]
                if any(v is None for v in values):
                    continue
                if all(start.get(r) == v for r, v in zip(f["references"], values)):
                    continue
                exists = conn.execute(
                    sql.SQL("SELECT 1 FROM shiliu.{} WHERE {}").format(
                        sql.Identifier(name),
                        sql.SQL(" AND ").join(
                            sql.SQL("{}=%s").format(sql.Identifier(k))
                            for k in f["references"]
                        ),
                    ),
                    values,
                ).fetchone()
                if exists is None:
                    blocked = True
                    break
            if blocked:
                continue
            _insert(conn, name, start)
            waiting.remove(row)
            progress = True
        if not progress:
            raise MigrationRejected("unresolved_self_reference_cycle")


def _batch(
    conn,
    run_id,
    identity,
    name,
    expected,
    staged,
    raw,
    tables,
    *,
    phase_one_allowed=True,
    fault_table=None,
):
    definition = tables[name]
    keys = [[row[k] for k in definition["pk"]] for row in expected]
    batch_key = hashlib.sha256(
        json.dumps([keys[0], keys[-1]], default=str).encode()
    ).hexdigest()[:24]
    digest = logical_hash(expected, definition["columns"])
    prior = conn.execute(
        "SELECT input_hash,input_rows FROM shiliu.migration_batches WHERE run_id=%s AND table_name=%s AND batch_key=%s",
        (run_id, name, batch_key),
    ).fetchone()
    if prior:
        if prior["input_hash"] != digest or prior["input_rows"] != len(expected):
            raise MigrationRejected("batch_input_identity_conflict")
        for row in expected:
            found = _read_row(conn, name, row, definition)
            if not (
                _same(row, found, definition)
                or (phase_one_allowed and _same(_initial(name, row), found, definition))
            ):
                raise MigrationRejected(
                    "same_primary_key_different_payload",
                    table_name=name,
                    record_key={k: row[k] for k in definition["pk"]},
                )
        return
    if staged is not None:
        with conn.cursor().copy(
            "COPY shiliu_migration.rows (run_id,table_name,batch_key,ordinal,data) FROM STDIN"
        ) as copy:
            for i, row in enumerate(staged):
                copy.write_row((run_id, name, batch_key, i, Jsonb(row)))
        data = conn.execute(
            "SELECT data FROM shiliu_migration.rows WHERE run_id=%s AND table_name=%s AND batch_key=%s ORDER BY ordinal",
            (run_id, name, batch_key),
        ).fetchall()
        converted = convert_snapshot(
            identity, BatchSource(raw, name, [r["data"] for r in data]), artifacts=False
        )[name]
        if logical_hash(converted, definition["columns"]) != digest:
            raise MigrationRejected("staging_conversion_mismatch")
    else:
        converted = expected
    _insert_ordered(conn, name, converted, tables)
    if fault_table == name:
        raise MigrationRejected("injected_batch_failure")
    conn.execute(
        "INSERT INTO shiliu.migration_batches (run_id,table_name,batch_key,input_hash,input_rows,target_rows,completed_at) VALUES (%s,%s,%s,%s,%s,%s,clock_timestamp())",
        (run_id, name, batch_key, digest, len(expected), len(expected)),
    )


def _self_parents_available(conn, name, rows, definition):
    for f in definition["foreign_keys"]:
        if f["table"] != name:
            continue
        local = {tuple(row[k] for k in f["references"]) for row in rows}
        for row in rows:
            values = tuple(row[k] for k in f["columns"])
            if any(v is None for v in values) or values in local:
                continue
            found = conn.execute(
                sql.SQL("SELECT 1 FROM shiliu.{} WHERE {}").format(
                    sql.Identifier(name),
                    sql.SQL(" AND ").join(
                        sql.SQL("{}=%s").format(sql.Identifier(k))
                        for k in f["references"]
                    ),
                ),
                values,
            ).fetchone()
            if found is None:
                return False
    return True


def _table_batches(
    conn,
    run_id,
    identity,
    name,
    rows,
    raw,
    tables,
    *,
    commit,
    phase_one_allowed=True,
    fault_table=None,
    after_batch=None,
):
    # A stable PK range can refer to an immutable parent in a later range.
    # Defer that range, process its parents, then revisit. Only range identities
    # are retained; neither a table nor its ancestor closure is held in memory.
    finished = set()
    while True:
        blocked = False
        progress = False
        batches = rows.batches() if hasattr(rows, "batches") else ((None, rows),)
        for staged, expected in batches:
            key = tuple(expected[0][k] for k in tables[name]["pk"])
            if key in finished:
                continue
            if not _self_parents_available(conn, name, expected, tables[name]):
                blocked = True
                if commit:
                    conn.commit()
                continue
            with conn.transaction():
                _batch(
                    conn,
                    run_id,
                    identity,
                    name,
                    expected,
                    staged,
                    raw,
                    tables,
                    phase_one_allowed=phase_one_allowed,
                    fault_table=fault_table,
                )
            if commit:
                conn.commit()
            finished.add(key)
            progress = True
            if after_batch:
                after_batch()
        if not blocked:
            return
        if not progress:
            raise MigrationRejected("unresolved_self_reference_cycle", table_name=name)


def _terminal_research_group(
    conn, run_id, identity, rows, raw, tables, *, fault_table=None
):
    """Task/result and independent derivation lineage, one real FK transaction.

    No fake intermediate task state, no disabled triggers, no unvalidated FK.
    Nullable active-goal/created-event/attempt-result pointers use phase two;
    the NOT NULL conditional terminal-result pointer is retained from the start.
    """
    group = [
        n
        for n in (
            "research_tasks",
            "research_goals",
            "research_attempts",
            "research_checkpoints",
            "research_results",
            "research_task_derivations",
        )
        if n in rows
    ]
    with conn.transaction():
        conn.execute("SET CONSTRAINTS ALL DEFERRED")
        for name in group:
            _table_batches(
                conn,
                run_id,
                identity,
                name,
                rows[name],
                raw,
                tables,
                commit=False,
                fault_table=fault_table,
            )
        conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
    return group


def _safe_target_path(root, key, workspace):
    relative = Path(key)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or not relative.as_posix().startswith(workspace + "/")
    ):
        raise MigrationRejected("unsafe_target_artifact_key")
    path = root / relative
    for parent in [path, *path.parents]:
        if parent == root.parent:
            break
        if parent.is_symlink():
            raise MigrationRejected("target_artifact_symlink")
    if not path.resolve().is_relative_to(root.resolve()):
        raise MigrationRejected("unsafe_target_artifact_key")
    return path


def _copy_artifacts(source, root, identity):
    artifacts = identity["artifacts"]
    for a in artifacts:
        key = Path(a["relative_key"])
        workspace = artifact_workspace(identity, a)
        if (
            key.is_absolute()
            or ".." in key.parts
            or not key.as_posix().startswith(workspace + "/")
        ):
            raise MigrationRejected("unsafe_target_artifact_key")
        destination = root / key
        # Every component is task-owned and must remain free of symlinks.
        for parent in [destination, *destination.parents]:
            if parent == root.parent:
                break
            if parent.is_symlink():
                raise MigrationRejected("target_artifact_symlink")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if sha(destination) != a["sha256"]:
                raise MigrationRejected("target_artifact_conflict")
        else:
            temp = destination.with_name(destination.name + ".w04-partial")
            if temp.exists():
                if temp.is_symlink() or not temp.is_file():
                    raise MigrationRejected("unsafe_partial_artifact")
                temp.unlink()
            with (
                (source.parent / a["source_file"]).open("rb") as reader,
                temp.open("xb") as writer,
            ):
                shutil.copyfileobj(reader, writer)
                writer.flush()
                __import__("os").fsync(writer.fileno())
            if sha(temp) != a["sha256"]:
                temp.unlink()
                raise MigrationRejected("source_artifact_changed")
            temp.replace(destination)
            import os

            descriptor = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        if destination.stat().st_size != a["byte_size"]:
            raise MigrationRejected("target_artifact_size_mismatch")


def _import_snapshot(
    source: Path,
    config: PostgresConfig,
    run_id: str,
    *,
    _fault_after_batches: int | None = None,
    _fault_inside_table: str | None = None,
):
    guard(config, etl=True)
    guard_input_target(source, config)
    if not re.fullmatch(r"w(?:04|14)_[a-z0-9_]+", run_id):
        raise MigrationRejected("invalid_run_id")
    identity, rows = plan_snapshot(source)
    again, raw = inspect_snapshot(source)
    if again != identity:
        raise MigrationRejected("source_changed_after_plan")
    tables = mapping()["tables"]
    with _connect(config) as conn:
        _root_contract(conn)
        old = conn.execute(
            "SELECT * FROM shiliu.migration_runs WHERE run_id=%s FOR UPDATE", (run_id,)
        ).fetchone()
        if old:
            _binding(old, identity)
        else:
            for name, column, expected in [
                ("users", "id", {"local_operator"}),
                ("workspaces", "id", {"personal:local_operator"}),
                ("workspace_guards", "workspace_id", {"personal:local_operator"}),
            ]:
                actual = conn.execute(
                    sql.SQL("SELECT {} FROM shiliu.{}").format(
                        sql.Identifier(column), sql.Identifier(name)
                    )
                ).fetchall()
                if {row[column] for row in actual} != expected:
                    raise MigrationRejected("new_run_requires_seed_only_target")
            for table in tables:
                if table in {
                    "users",
                    "workspaces",
                    "workspace_guards",
                    "migration_runs",
                    "migration_batches",
                    "migration_exceptions",
                }:
                    continue
                if conn.execute(
                    sql.SQL("SELECT 1 FROM shiliu.{} LIMIT 1").format(
                        sql.Identifier(table)
                    )
                ).fetchone():
                    raise MigrationRejected("new_run_requires_empty_target")
            conn.execute(
                "INSERT INTO shiliu.migration_runs (run_id,source_manifest_hash,source_head,source_schema_version,"
                "target_revision,mapping_version,tool_version,status,started_at) VALUES (%s,%s,%s,26,%s,%s,'w14-v1','inspected',clock_timestamp())",
                (
                    run_id,
                    identity["manifest_hash"],
                    identity["source_head"],
                    HEAD_REVISION,
                    identity["mapping_version"],
                ),
            )
            conn.execute(
                "UPDATE shiliu.migration_runs SET status='planned' WHERE run_id=%s",
                (run_id,),
            )
        for owner, workspace in identity["ownership"]["principals"].items():
            existing = conn.execute(
                "SELECT owner_user_id FROM shiliu.workspaces WHERE id=%s", (workspace,)
            ).fetchone()
            if existing and existing["owner_user_id"] != owner:
                raise MigrationRejected("workspace_owner_conflict")
            conn.execute(
                "INSERT INTO shiliu.users (id,display_name,created_at) VALUES (%s,%s,clock_timestamp()) ON CONFLICT DO NOTHING",
                (owner, owner),
            )
            conn.execute(
                "INSERT INTO shiliu.workspaces (id,kind,owner_user_id,created_at) VALUES (%s,'personal',%s,clock_timestamp()) ON CONFLICT DO NOTHING",
                (workspace, owner),
            )
            conn.execute(
                "INSERT INTO shiliu.workspace_guards (workspace_id) VALUES (%s) ON CONFLICT DO NOTHING",
                (workspace,),
            )
        phase_one_allowed = old is None or old["status"] in {
            "inspected",
            "planned",
            "importing",
        }
        ready_replay = bool(old and old["status"] == "ready")
        if ready_replay:
            # Ready replay still validates actual target rows/files below.
            pass
        else:
            conn.execute(
                "UPDATE shiliu.migration_runs SET status='importing' WHERE run_id=%s",
                (run_id,),
            )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS shiliu_migration.rows "
            "(run_id text NOT NULL,table_name text NOT NULL,batch_key text NOT NULL,ordinal bigint NOT NULL,data jsonb NOT NULL,PRIMARY KEY(run_id,table_name,batch_key,ordinal))"
        )
    if ready_replay:
        return validate_snapshot(source, config, run_id)
    _copy_artifacts(source, config.artifact_root, identity)
    completed = 0
    pending = dict(rows)
    with _connect(config) as conn:
        if any(row["status"] == "terminal" for row in rows.get("research_tasks", [])):
            for name in _terminal_research_group(
                conn,
                run_id,
                identity,
                rows,
                raw,
                tables,
                fault_table=_fault_inside_table,
            ):
                pending.pop(name, None)
        while pending:
            progress = False
            for name, table_rows in list(pending.items()):
                if not _ready_table(conn, name, table_rows, tables, pending):
                    continue

                def after_batch():
                    nonlocal completed
                    completed += 1
                    if (
                        _fault_after_batches is not None
                        and completed == _fault_after_batches
                    ):
                        raise MigrationRejected("injected_import_interruption")

                _table_batches(
                    conn,
                    run_id,
                    identity,
                    name,
                    table_rows,
                    raw,
                    tables,
                    commit=True,
                    phase_one_allowed=phase_one_allowed,
                    fault_table=_fault_inside_table,
                    after_batch=after_batch,
                )
                del pending[name]
                progress = True
            if not progress:
                raise MigrationRejected("unresolved_table_dependency_cycle")
        with conn.transaction():
            for name, keys in POINTERS.items():
                for row in rows.get(name, []):
                    for key in keys:
                        if row[key] is not None:
                            conn.execute(
                                sql.SQL("UPDATE shiliu.{} SET {}=%s WHERE {}").format(
                                    sql.Identifier(name),
                                    sql.Identifier(key),
                                    sql.SQL(" AND ").join(
                                        sql.SQL("{}=%s").format(sql.Identifier(k))
                                        for k in tables[name]["pk"]
                                    ),
                                ),
                                [
                                    _adapt(row[key]),
                                    *[_adapt(row[k]) for k in tables[name]["pk"]],
                                ],
                            )
            conn.execute(
                "UPDATE shiliu.workspace_guards SET membership_highwater=(SELECT coalesce(max(membership_seq),0) "
                "FROM shiliu.video_source_memberships WHERE workspace_id=shiliu.workspace_guards.workspace_id)"
            )
            from shiliu.migration.sequences import check as check_sequences

            check_sequences(conn, source, tables, calibrate=True)
            conn.execute(
                "UPDATE shiliu.migration_runs SET status='imported' WHERE run_id=%s AND status<>'ready'",
                (run_id,),
            )
    with _connect(config) as conn:
        conn.execute(
            "UPDATE shiliu.migration_runs SET status='validating' WHERE run_id=%s AND status<>'ready'",
            (run_id,),
        )
    report = validate_snapshot(source, config, run_id)
    with _connect(config) as conn:
        conn.execute(
            "UPDATE shiliu.migration_runs SET status='ready',completed_at=coalesce(completed_at,clock_timestamp()) WHERE run_id=%s",
            (run_id,),
        )
    return report


def validate_snapshot(
    source: Path,
    config: PostgresConfig,
    run_id: str,
    *,
    _allow_rebuild_incomplete=False,
):
    guard(config, etl=True)
    guard_input_target(source, config)
    identity, rows = plan_snapshot(source)
    tables = mapping()["tables"]
    counts = {}
    hashes = {}
    with _connect(config) as conn:
        conn.read_only = True
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        _root_contract(conn)
        run = conn.execute(
            "SELECT * FROM shiliu.migration_runs WHERE run_id=%s", (run_id,)
        ).fetchone()
        if run is None:
            raise MigrationRejected("migration_run_missing")
        _binding(run, identity)
        from shiliu.migration.projection_state import (
            receipt,
            adjusted_row,
            verify,
            DERIVED_TABLES,
        )

        state = receipt(conn, run_id)
        if state and state["source_manifest_hash"] != identity["manifest_hash"]:
            raise MigrationRejected("rebuild_input_identity_conflict")
        if state:
            from shiliu.retrieval.lexical import F1Tokenizer

            tokenizer = F1Tokenizer(config.artifact_root / "tokenizer-cache")
        from shiliu.migration.catalog import read_catalog, compare_catalog

        conn.execute("SET LOCAL search_path=pg_catalog")
        catalog = read_catalog(conn)
        errors = compare_catalog(catalog, mapping())
        if errors:
            raise MigrationRejected("target_catalog_contract_mismatch")
        for name, expected in rows.items():
            definition = tables[name]

            def checked_rows():
                for original in expected:
                    found = _read_row(conn, name, original, definition)
                    if found is None:
                        raise MigrationRejected(
                            "target_record_missing",
                            table_name=name,
                            record_key={k: original[k] for k in definition["pk"]},
                        )
                    checked = (
                        adjusted_row(conn, name, original, found, state, tokenizer)
                        if state
                        else original
                    )
                    if not _same(checked, found, definition):
                        raise MigrationRejected(
                            "same_primary_key_different_payload",
                            table_name=name,
                            record_key={k: original[k] for k in definition["pk"]},
                        )
                    yield found

            digest = logical_hash(checked_rows(), definition["columns"])
            count = conn.execute(
                sql.SQL("SELECT count(*) AS n FROM shiliu.{}").format(
                    sql.Identifier(name)
                )
            ).fetchone()["n"]
            if count != len(expected) and not (state and name in DERIVED_TABLES):
                raise MigrationRejected("target_row_count_mismatch")
            counts[name] = count
            hashes[name] = digest
        for name in tables:
            if name in rows or name in {
                "users",
                "workspaces",
                "workspace_guards",
                "migration_runs",
                "migration_batches",
                "migration_exceptions",
            }:
                continue
            if state and name in DERIVED_TABLES:
                continue
            if conn.execute(
                sql.SQL("SELECT 1 FROM shiliu.{} LIMIT 1").format(sql.Identifier(name))
            ).fetchone():
                raise MigrationRejected("unexpected_nonempty_target_table")
        if conn.execute(
            "SELECT 1 FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname='shiliu' AND NOT c.convalidated"
        ).fetchone():
            raise MigrationRejected("unvalidated_target_constraint")
        from shiliu.migration.sequences import check as check_sequences

        sequence_report, _ = check_sequences(conn, source, tables)
        verify(conn, state, tables, allow_incomplete=_allow_rebuild_incomplete)
    for a in identity["artifacts"]:
        path = _safe_target_path(
            config.artifact_root, a["relative_key"], artifact_workspace(identity, a)
        )
        if path.is_symlink() or not path.is_file() or sha(path) != a["sha256"]:
            raise MigrationRejected("target_artifact_missing_or_changed")
    return {
        "run_id": run_id,
        "manifest_hash": identity["manifest_hash"],
        "mapping_version": identity["mapping_version"],
        "synthetic_only": identity["provenance"]["synthetic_only"],
        "sequence_verification": sequence_report,
        "rebuild": None
        if not state
        else {
            "status": state["status"],
            "profiles": state["details"].get("profiles", {}),
            "table_snapshots": state["details"].get("table_snapshots", {}),
            **state["details"].get("summary", {}),
        },
        "counts": counts,
        "logical_hashes": hashes,
        "artifacts_verified": len(identity["artifacts"]),
        "state_dispositions": identity["state_dispositions"],
        "raw_identity_references_verified": identity[
            "raw_identity_references_verified"
        ],
        "file_reference_dispositions": identity["file_reference_dispositions"],
        "catalog_verified": {
            "tables": len(catalog),
            "columns": sum(len(t["columns"]) for t in catalog.values()),
            "constraints": sum(len(t["constraints"]) for t in catalog.values()),
            "triggers": sum(len(t["triggers"]) for t in catalog.values()),
        },
        "table_coverage": {
            n: (
                "imported"
                if n in rows and t["source"]
                else "generated"
                if n in rows
                else "seed"
                if n in {"users", "workspaces", "workspace_guards"}
                else "ledger"
                if n.startswith("migration_")
                else "empty"
            )
            for n, t in tables.items()
        },
    }


def import_snapshot(source: Path, config: PostgresConfig, run_id: str, **fault_options):
    # Administrative single-run guard is independent of application Job/lane
    # protocols. try-lock is bounded; batches still use separate transactions.
    with _connect(config) as control:
        control.autocommit = True
        acquired = control.execute(
            "SELECT pg_try_advisory_lock(198023,4) AS ok"
        ).fetchone()["ok"]
        if not acquired:
            raise MigrationRejected("migration_already_active")
        try:
            return _import_snapshot(source, config, run_id, **fault_options)
        except (MigrationRejected, psycopg.Error) as error:
            category = (
                str(error)
                if isinstance(error, MigrationRejected)
                else "target_constraint_" + str(error.sqlstate)
            )
            # Independent diagnostic transaction; a failed batch never commits
            # partial business rows/receipt, but its safe rejection is recorded.
            try:
                with _connect(config) as audit:
                    if audit.execute(
                        "SELECT 1 FROM shiliu.migration_runs WHERE run_id=%s", (run_id,)
                    ).fetchone():
                        audit.execute(
                            "INSERT INTO shiliu.migration_exceptions (run_id,table_name,record_key,category,disposition,created_at) "
                            "VALUES (%s,%s,%s,%s,'rejected',clock_timestamp()) ON CONFLICT DO NOTHING",
                            (
                                run_id,
                                getattr(error, "table_name", "__run__"),
                                Jsonb(
                                    json.loads(
                                        json.dumps(
                                            getattr(
                                                error, "record_key", {"run_id": run_id}
                                            ),
                                            default=str,
                                        )
                                    )
                                ),
                                category,
                            ),
                        )
            except psycopg.Error:
                pass  # Do not mask original bounded failure if diagnostic storage is down.
            raise MigrationRejected(category) from None
        finally:
            control.execute("SELECT pg_advisory_unlock(198023,4)")
