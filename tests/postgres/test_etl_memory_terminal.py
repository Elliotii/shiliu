"""Historical terminal Memory Jobs keep every typed field on import/reentry."""

from contextlib import closing
import json
import sqlite3

from psycopg import connect
from psycopg.rows import dict_row

from poc_source import make_source
from schema_support import formal_target
from test_etl import target_etl
from shiliu.config import LIBPQ_DISABLED_PASSFILE, load_postgres_config
from shiliu.migration.etl import import_snapshot
from shiliu.migration.snapshot import plan_snapshot
from shiliu.migration.states import TERMINAL, FORGOTTEN_PURGE_COMPLETION
from shiliu.migration.values import JsonDocument, convert


def test_terminal_memory_jobs_preserve_all_fields_pending_controls_and_reentry():
    source = make_source()
    originals = []
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.row_factory = sqlite3.Row
        templates = conn.execute("SELECT * FROM assistant_jobs ORDER BY kind").fetchall()
        for template in templates:
            for status in sorted(TERMINAL):
                row = dict(template)
                row.update(
                    id=f"synthetic_{row['kind']}_{status}",
                    dedupe_key=f"terminal:{row['kind']}:{status}",
                    status=status,
                    proposal_json=json.dumps({"history": [3, 1], "optional": None}),
                    last_error_code="historical_error",
                    last_error_message="historical audit retained",
                    completed_at="2026-10-23T01:00:00+00:00",
                )
                # A legitimate legacy payload must not become a new PG intent.
                payload = json.loads(row["payload_json"])
                payload.update(backend_id="synthetic_legacy", history=[3, 1])
                row["payload_json"] = json.dumps(payload)
                columns = ",".join('"' + k + '"' for k in row)
                conn.execute(
                    f"INSERT INTO assistant_jobs ({columns}) VALUES ({','.join('?' for _ in row)})",
                    list(row.values()),
                )
                originals.append(row)

    identity, expected = plan_snapshot(source)
    from shiliu.migration.snapshot import mapping

    definitions = mapping()["tables"]["assistant_jobs"]["columns"]
    typed = {row["id"]: row for row in expected["assistant_jobs"]}
    for original in originals:
        row = typed[original["id"]]
        for key, definition in definitions.items():
            value = (
                convert(original[key], definition, field="assistant_jobs." + key)
                if "source" in definition
                else identity["ownership"]["principals"][identity["ownership"]["default_principal"]]
                if key == "workspace_id"
                else identity["ownership"]["default_principal"]
            )
            assert row[key] == value, (original["kind"], original["status"], key)
    controls = [row for key, row in typed.items() if key not in {r["id"] for r in originals}]
    assert {r["kind"]: r["status"] for r in controls} == {
        "memory_index": "blocked", "memory_purge": "completed",
    }
    purge = next(r for r in controls if r["kind"] == "memory_purge")
    assert purge["payload_json"].value["migration_completion"]["policy"] == FORGOTTEN_PURGE_COMPLETION

    with formal_target(load_postgres_config()) as (runtime, _):
        target = target_etl(runtime)
        report = import_snapshot(source, target, "w14_terminal_memory")

        def read_jobs():
            with connect(target.database_url, passfile=LIBPQ_DISABLED_PASSFILE, row_factory=dict_row) as conn:
                return conn.execute("SELECT * FROM shiliu.assistant_jobs ORDER BY id").fetchall()

        before = read_jobs()
        assert len(before) == len(originals) + 2
        for row in before:
            assert row == {
                key: value.value if isinstance(value, JsonDocument) else value
                for key, value in typed[row["id"]].items()
            }
        assert import_snapshot(source, target, "w14_terminal_memory") == report
        assert read_jobs() == before
