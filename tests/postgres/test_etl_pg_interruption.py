"""C13: real backend termination rolls back COPY/data/receipt, then PG restart."""

from pathlib import Path
import subprocess
import sys
import psycopg
import pytest
from full_source import make_full_source
from schema_support import formal_target
from test_etl import target_etl
from shiliu.config import load_postgres_config, LIBPQ_DISABLED_PASSFILE
from shiliu.migration import etl
from shiliu.migration.values import MigrationRejected


def test_backend_termination_and_server_restart_resume_atomic_batch(monkeypatch):
    source = make_full_source()
    with formal_target(load_postgres_config()) as (runtime, admin):
        target = target_etl(runtime)
        original = etl._insert_ordered
        terminated = []

        def insert(conn, name, rows, tables):
            original(conn, name, rows, tables)
            if name == "events" and not terminated:
                pid = conn.info.backend_pid
                with psycopg.connect(
                    admin.database_url,
                    passfile=LIBPQ_DISABLED_PASSFILE,
                    autocommit=True,
                ) as control:
                    assert control.execute(
                        "SELECT pg_terminate_backend(%s)", (pid,)
                    ).fetchone() == (True,)
                terminated.append(pid)
                conn.execute("SELECT 1")

        monkeypatch.setattr(etl, "_insert_ordered", insert)
        with pytest.raises(MigrationRejected, match="target_constraint_57P01"):
            etl.import_snapshot(source, target, "w14_pg_restart")
        assert len(terminated) == 1
        with psycopg.connect(admin.database_url, passfile=LIBPQ_DISABLED_PASSFILE) as c:
            assert c.execute("SELECT count(*) FROM shiliu.events").fetchone() == (0,)
            assert c.execute(
                "SELECT count(*) FROM shiliu.migration_batches WHERE table_name='events'"
            ).fetchone() == (0,)
            assert c.execute(
                "SELECT count(*) FROM shiliu_migration.rows WHERE table_name='events'"
            ).fetchone() == (0,)
        # No open runtime pool. Lifecycle helper rechecks marker/private root,
        # touches only this task's service, and preserves all committed batches.
        helper = str(Path("scripts/postgres_w01_local.py").resolve())
        try:
            subprocess.run(
                [sys.executable, helper, "stop"],
                check=True,
                capture_output=True,
                timeout=20,
            )
        finally:
            subprocess.run(
                [sys.executable, helper, "start"],
                check=True,
                capture_output=True,
                timeout=20,
            )
        monkeypatch.setattr(etl, "_insert_ordered", original)
        report = etl.import_snapshot(source, target, "w14_pg_restart")
        assert report["counts"]["events"] == 1105
        assert etl.import_snapshot(source, target, "w14_pg_restart") == report
        with psycopg.connect(admin.database_url, passfile=LIBPQ_DISABLED_PASSFILE) as c:
            assert (
                c.execute(
                    "SELECT nextval(pg_get_serial_sequence('shiliu.events','id'))"
                ).fetchone()[0]
                > 1105
            )
