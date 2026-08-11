from __future__ import annotations

from shiliu.db import Database, SCHEMA_VERSION


def test_v15_migration_preserves_search_and_research_and_adds_ask(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    with db.connect() as connection:
        connection.executescript(
            """
            CREATE TABLE retrieval_search_traces (
                trace_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );
            INSERT INTO retrieval_search_traces(trace_id, payload)
            VALUES('search-sentinel', 'preserved');

            INSERT INTO research_tasks(
                task_id, status, state_version, owner_epoch,
                control_generation, created_at, updated_at
            ) VALUES(
                'research-sentinel', 'ready', 0, 0, 0,
                '2026-08-11T00:00:00+00:00',
                '2026-08-11T00:00:00+00:00'
            );

            DROP TABLE ask_events;
            DROP TABLE ask_search_trace_links;
            DROP TABLE ask_runs;
            UPDATE schema_meta SET value='15' WHERE key='schema_version';
            """
        )

    db.initialize()

    assert SCHEMA_VERSION == 16
    assert app_paths.database.with_name("shiliu.pre-v16.backup.db").is_file()
    with db.connect() as connection:
        assert connection.execute(
            "SELECT payload FROM retrieval_search_traces WHERE trace_id='search-sentinel'"
        ).fetchone()[0] == "preserved"
        assert connection.execute(
            "SELECT status FROM research_tasks WHERE task_id='research-sentinel'"
        ).fetchone()[0] == "ready"
        assert connection.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0] == "16"
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            ).fetchall()
        }
    assert {"ask_runs", "ask_search_trace_links", "ask_events"}.issubset(tables)
