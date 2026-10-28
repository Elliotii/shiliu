"""Additive 0012 -> 0013 contract; runnable against an installed Wheel too."""

from pathlib import Path
import psycopg
import pytest
from shiliu.config import load_postgres_config, LIBPQ_DISABLED_PASSFILE
from shiliu.migration.schema import HEAD_REVISION, MIGRATIONS, upgrade
from shiliu.storage.postgres import PgDatabase
from shiliu.storage.scope import personal_context
from shiliu.db import Database
from shiliu.assistant.notifications import record
from shiliu.assistant.pg_store import PgAssistantRunStore
from schema_support import formal_target


def test_0012_to_0013_resources_constraints_and_runtime_grant():
    assert HEAD_REVISION == "0014_assistant_source_patch"
    assert (MIGRATIONS / "sql" / "0013.sql").is_file()
    assert (MIGRATIONS / "versions" / "0013_assistant_notifications.py").is_file()
    with formal_target(
        load_postgres_config(), revisions=("0012_collection_chunk_bm25",)
    ) as (runtime, admin):
        # Existing 0012 roles are already granted. The forward migration must
        # grant only its own new table; do not re-run global grant_roles here.
        with psycopg.connect(
            admin.database_url, passfile=LIBPQ_DISABLED_PASSFILE
        ) as migration_conn:
            upgrade(migration_conn, "head")
        with PgDatabase(runtime) as pg:
            pg.validate_startup(revision=HEAD_REVISION, context=personal_context())
            db = Database(pg, personal_context())
            store = PgAssistantRunStore(db)
            space = store.create_space(name="Schema P1")
            with db.connect() as c:
                record(
                    c,
                    db.context,
                    event_key="schema",
                    origin_type="wiki_change",
                    origin_id="1",
                    source_type="manual",
                    space_id=space["id"],
                )
                row = c.execute("SELECT * FROM assistant_notifications").fetchone()
                assert set(row) == {
                    "id",
                    "workspace_id",
                    "principal_id",
                    "space_id",
                    "event_key",
                    "origin_type",
                    "origin_id",
                    "origin_version",
                    "source_type",
                    "cause_refs",
                    "effect_refs",
                    "undo_ref",
                    "created_at",
                    "activity_at",
                    "read_at",
                }
                assert c.execute(
                    "SELECT value FROM assistant_runtime_state WHERE key='messages_activation_at'"
                ).fetchone()
            with psycopg.connect(
                admin.database_url, passfile=LIBPQ_DISABLED_PASSFILE
            ) as c:
                cons = c.execute(
                    "SELECT contype FROM pg_constraint WHERE conrelid='shiliu.assistant_notifications'::regclass"
                ).fetchall()
                assert [v[0] for v in cons].count("f") == 3
                assert [v[0] for v in cons].count("c") == 4
                for field, value in [("space_id", 987654), ("principal_id", "missing")]:
                    with pytest.raises(psycopg.errors.ForeignKeyViolation):
                        with c.transaction():
                            c.execute(
                                f"UPDATE shiliu.assistant_notifications SET {field}=%s",
                                (value,),
                            )
                with pytest.raises(psycopg.errors.CheckViolation):
                    with c.transaction():
                        c.execute(
                            "UPDATE shiliu.assistant_notifications SET origin_type='source_patch'"
                        )
                ix = c.execute(
                    "SELECT indexname,indexdef FROM pg_indexes WHERE tablename='assistant_notifications'"
                ).fetchall()
                assert any("WHERE (read_at IS NULL)" in r[1] for r in ix)
                assert (
                    c.execute(
                        "SELECT version_num FROM shiliu.alembic_version"
                    ).fetchone()[0]
                    == HEAD_REVISION
                )
