"""Source AUTOINCREMENT counters include IDs deleted before the snapshot."""

from contextlib import closing
import sqlite3
import psycopg
import pytest
from psycopg import sql
from full_source import make_full_source
from schema_support import formal_target
from test_etl import target_etl
from shiliu.config import load_postgres_config, LIBPQ_DISABLED_PASSFILE
from shiliu.migration.etl import import_snapshot, validate_snapshot, _connect
from shiliu.migration.snapshot import mapping
from shiliu.migration.sequences import check
from shiliu.migration.values import MigrationRejected


def test_source_deleted_id_highwater_is_kept_and_lowered_sequence_rejected():
    source = make_full_source()
    with closing(sqlite3.connect(source)) as c, c:
        assert (
            c.execute(
                "UPDATE sqlite_sequence SET seq=900000 WHERE name IN ('asr_jobs','taxonomy_stage_runs')"
            ).rowcount
            == 2
        )
    with formal_target(load_postgres_config()) as (runtime, admin):
        target = target_etl(runtime)
        report = import_snapshot(source, target, "w14_sequence")
        assert report["sequence_verification"]["source_autoincrement_counters"] >= 2
        with psycopg.connect(admin.database_url, passfile=LIBPQ_DISABLED_PASSFILE) as c:
            for name in ("asr_jobs", "taxonomy_stage_runs"):
                sequence = c.execute(
                    "SELECT pg_get_serial_sequence(%s,'id')", ("shiliu." + name,)
                ).fetchone()[0]
                assert (
                    c.execute("SELECT nextval(%s::regclass)", (sequence,)).fetchone()[0]
                    > 900000
                )
                c.execute(
                    sql.SQL("ALTER SEQUENCE {} RESTART WITH 1").format(
                        sql.Identifier(*sequence.split("."))
                    )
                )
        with pytest.raises(
            MigrationRejected, match="identity_sequence_below_source_highwater"
        ):
            validate_snapshot(source, target, "w14_sequence")
        with _connect(target) as c:
            _, raised = check(c, source, mapping()["tables"], calibrate=True)
            assert raised == 2
        assert validate_snapshot(source, target, "w14_sequence") == report
