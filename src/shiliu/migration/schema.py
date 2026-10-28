from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from psycopg import Connection, sql
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool


HEAD_REVISION = "0014_assistant_source_patch"
_PACKAGED = Path(__file__).with_name("alembic")
MIGRATIONS = (
    _PACKAGED
    if _PACKAGED.is_dir()
    else Path(__file__).resolve().parents[3] / "migrations"
)


def upgrade(conn: Connection, revision: str = "head") -> None:
    """Consume a dedicated migration connection; commit/close the revision chain.

    SQLAlchemy is confined to Alembic's migration machinery. No runtime ORM or
    application wiring; no plaintext URL is handed to its engine/logger.
    """
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    engine = create_engine(
        "postgresql+psycopg://", creator=lambda: conn, poolclass=NullPool, echo=False
    )
    # This administrative operation consumes the dedicated raw connection.
    # Never pass a runtime or caller business-transaction connection here.
    with engine.connect() as migration_conn:
        config.attributes["connection"] = migration_conn
        with migration_conn.begin():
            command.upgrade(config, revision)


def grant_roles(conn: Connection, *, runtime_role: str, etl_role: str) -> None:
    """Explicit migration operation. Roles are provisioned by the operator.

    Runtime cannot read migration staging/ledgers or alter schema/extension/
    triggers. ETL has business DML and staging DDL but no trigger-disable powers.
    """
    from shiliu.retrieval.bm25 import grant_query_access

    for role in (runtime_role, etl_role):
        row = conn.execute(
            "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls "
            "FROM pg_catalog.pg_roles WHERE rolname=%s",
            (role,),
        ).fetchone()
        if row is None or any(row.values() if isinstance(row, dict) else row):
            raise ValueError("Refusing absent or privileged migration/runtime role")
        grant_query_access(conn, role)
        conn.execute(
            sql.SQL("GRANT USAGE ON SCHEMA shiliu TO {}").format(sql.Identifier(role))
        )
        conn.execute(
            sql.SQL(
                "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA shiliu TO {}"
            ).format(sql.Identifier(role))
        )
        conn.execute(
            sql.SQL(
                "GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA shiliu TO {}"
            ).format(sql.Identifier(role))
        )
        if role == etl_role:
            conn.execute(
                sql.SQL("GRANT UPDATE ON ALL SEQUENCES IN SCHEMA shiliu TO {}").format(
                    sql.Identifier(role)
                )
            )
        conn.execute(
            sql.SQL("REVOKE ALL ON shiliu.alembic_version FROM {}").format(
                sql.Identifier(role)
            )
        )
        conn.execute(
            sql.SQL("GRANT SELECT ON shiliu.alembic_version TO {}").format(
                sql.Identifier(role)
            )
        )
    for table in ("migration_runs", "migration_batches", "migration_exceptions"):
        conn.execute(
            sql.SQL("REVOKE ALL ON shiliu.{} FROM {}").format(
                sql.Identifier(table), sql.Identifier(runtime_role)
            )
        )
    conn.execute(
        sql.SQL("GRANT USAGE,CREATE ON SCHEMA shiliu_migration TO {}").format(
            sql.Identifier(etl_role)
        )
    )
    # pg_restore --no-owner makes the operator own restored staging ledgers.
    # ETL needs their DML back; runtime still has no staging schema USAGE.
    conn.execute(
        sql.SQL(
            "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA shiliu_migration TO {}"
        ).format(sql.Identifier(etl_role))
    )
