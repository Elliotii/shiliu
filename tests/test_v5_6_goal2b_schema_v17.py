from __future__ import annotations

import shutil
import sqlite3

import pytest

from shiliu.db import Database, SCHEMA_VERSION


def test_v16_copy_migrates_additively_with_backup_and_preserves_data(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    with db.connect() as connection:
        connection.executescript(
            """
            DROP TRIGGER trg_knowledge_draft_revisions_no_update;
            DROP TRIGGER trg_knowledge_draft_revisions_no_delete;
            DROP TABLE knowledge_draft_revisions;
            INSERT INTO seen_items(platform,source_id,part,is_baseline,first_seen_at,last_seen_at)
            VALUES('test','v16-sentinel',1,0,'2026-01-01','2026-01-01');
            UPDATE schema_meta SET value='16' WHERE key='schema_version';
            """
        )
    db.initialize()
    backup = app_paths.database.with_name("shiliu.pre-v17.backup.db")
    assert SCHEMA_VERSION == 17
    assert backup.is_file()
    with db.connect() as connection:
        assert connection.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0] == "17"
        assert connection.execute(
            "SELECT COUNT(*) FROM seen_items WHERE source_id='v16-sentinel'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_schema WHERE name='knowledge_draft_revisions'"
        ).fetchone()[0] == 1
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    restored = app_paths.database.with_name("restored-v16.db")
    shutil.copy2(backup, restored)
    connection = sqlite3.connect(restored)
    try:
        assert connection.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0] == "16"
        assert connection.execute(
            "SELECT COUNT(*) FROM seen_items WHERE source_id='v16-sentinel'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_schema WHERE name='knowledge_draft_revisions'"
        ).fetchone()[0] == 0
    finally:
        connection.close()


def test_fresh_v17_is_idempotent_constrained_and_refuses_future_schema(app_paths) -> None:
    db = Database(app_paths.database)
    db.initialize()
    db.initialize()
    with db.connect() as connection:
        triggers = {
            value[0]
            for value in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='trigger' "
                "AND name LIKE 'trg_knowledge_draft_revisions_%'"
            )
        }
        indexes = {
            value[0]
            for value in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='index' "
                "AND name LIKE 'idx_knowledge_draft_%'"
            )
        }
        assert len(triggers) == 2
        assert len(indexes) == 2
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO knowledge_draft_revisions(
                    draft_revision_id,draft_id,draft_schema_version,version,
                    owner_scope,origin_kind,source_answer_snapshot_json,
                    source_answer_hash,evidence_refs_json,scope_json,limitations_json,
                    revalidation_state,status,dedupe_identity,event_kind,command_id,
                    command_payload_hash,created_at
                ) VALUES('r','d','v5.6-knowledge-draft-v1',1,
                         'local_user_workspace','fast','{}','h','[]','{}','[]',
                         'current','saved','x','saved','c','p','now')
                """
            )
        connection.execute(
            "UPDATE schema_meta SET value='18' WHERE key='schema_version'"
        )
    with pytest.raises(RuntimeError, match="newer than supported"):
        db.initialize()
