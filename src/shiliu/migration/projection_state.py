"""Narrow offline rebuild receipts and checks for explicitly derived fields."""

from __future__ import annotations
from uuid import uuid4
from psycopg import sql
from shiliu.migration.values import JsonDocument, MigrationRejected, logical_hash

DERIVED_TABLES = {
    "embedding_profiles",
    "collection_embeddings",
    "memory_embeddings",
    "wiki_windows",
    "wiki_embeddings",
    "retrieval_projection_tasks",
    "assistant_runtime_state",
}
MUTABLE_FIELDS = {
    "retrieval_units": {"tokenized_text", "search_vector"},
    "assistant_memories": {"tokenized_text", "search_vector", "last_projected_version"},
}
POLICY = "w14-preserved-units-projections-v1"


def receipt(conn, run_id):
    if (
        conn.execute(
            "SELECT to_regclass('shiliu_migration.rebuild_receipts') AS name"
        ).fetchone()["name"]
        is None
    ):
        return None
    return conn.execute(
        "SELECT * FROM shiliu_migration.rebuild_receipts WHERE run_id=%s", (run_id,)
    ).fetchone()


def adjusted_row(conn, name, expected, found, state, tokenizer):
    if not state or name not in MUTABLE_FIELDS or found is None:
        return expected
    row = dict(expected)
    text = (
        expected["search_text"]
        if name == "retrieval_units"
        else expected["text"]
        if expected["status"] == "active"
        else ""
    )
    tokenized = tokenizer.document(text)
    if (
        state["status"] == "building"
        and found["tokenized_text"] == expected["tokenized_text"]
    ):
        tokenized = expected["tokenized_text"]
    vector = conn.execute(
        "SELECT to_tsvector('simple',%s)::text AS text", (tokenized,)
    ).fetchone()["text"]
    row.update(tokenized_text=tokenized, search_vector=vector)
    if (
        name == "assistant_memories"
        and found["last_projected_version"] != expected["last_projected_version"]
    ):
        if (
            found["last_projected_version"] != expected["version"]
            or expected["status"] != "active"
        ):
            raise MigrationRejected("unexpected_memory_projection_progress")
        profile = state["details"].get("profiles", {}).get("memory")
        valid = conn.execute(
            "SELECT 1 FROM shiliu.memory_embeddings WHERE workspace_id=%s AND memory_id=%s AND profile_id=%s AND memory_version=%s AND change_epoch=%s "
            "AND embedding_text_hash=encode(sha256(convert_to(normalize(%s,NFKC),'UTF8')),'hex')",
            (
                expected["workspace_id"],
                expected["id"],
                profile,
                expected["version"],
                expected["change_epoch"],
                expected["text"],
            ),
        ).fetchone()
        if not valid:
            raise MigrationRejected("memory_projection_progress_without_current_vector")
        row["last_projected_version"] = found["last_projected_version"]
    return row


def table_digest(conn, name, definition):
    columns = definition["columns"]
    json_columns = [k for k, c in columns.items() if c["type"] == "jsonb"]
    fields = [sql.Identifier(k) for k in columns] + [
        sql.SQL("{} IS NULL AS {}").format(
            sql.Identifier(k), sql.Identifier("__sql_null_" + k)
        )
        for k in json_columns
    ]
    query = sql.SQL("SELECT {} FROM shiliu.{} ORDER BY {}").format(
        sql.SQL(",").join(fields),
        sql.Identifier(name),
        sql.SQL(",").join(map(sql.Identifier, definition["pk"])),
    )
    count = 0

    def values():
        nonlocal count
        with conn.cursor(name="p5_" + uuid4().hex) as cursor:
            cursor.itersize = 128
            cursor.execute(query)
            for row in cursor:
                for key in json_columns:
                    if not row.pop("__sql_null_" + key):
                        row[key] = JsonDocument(row[key])
                count += 1
                yield row

    digest = logical_hash(values(), columns)
    return {"count": count, "logical_hash": digest}


def capture(conn, tables):
    return {
        name: table_digest(conn, name, tables[name])
        for name in sorted(DERIVED_TABLES | set(MUTABLE_FIELDS))
    }


def verify(conn, state, tables, *, allow_incomplete=False):
    if not state:
        return
    if state["policy_version"] != POLICY:
        raise MigrationRejected("rebuild_policy_mismatch")
    if state["status"] != "ready":
        if allow_incomplete:
            return
        raise MigrationRejected("rebuild_incomplete_resume_rebuild")
    if capture(conn, tables) != state["details"]["table_snapshots"]:
        raise MigrationRejected("rebuilt_projection_snapshot_changed")
