"""Operational backups preserve new writes rather than compare to old ETL input."""

import uuid
import psycopg
import pytest
from shiliu.migration.values import MigrationRejected
from shiliu.migration.backup_cli import main, require_quiescent

from schema_support import formal_target
from test_etl import target_etl
from shiliu.config import LIBPQ_DISABLED_PASSFILE, load_postgres_config
from shiliu.migration.backup import restore_pair, runtime_report
from shiliu.migration.safety import TASK_ROOT


def test_runtime_pair_keeps_post_import_write_and_restores_vectors_and_audit(monkeypatch):
    import shiliu.migration.backup_cli as cli
    from seed_rows import SyntheticGraph, WORKSPACE, MAPPING
    from hashlib import sha256
    from psycopg import sql
    payload = b"synthetic paired artifact\n"
    digest = sha256(payload).hexdigest()
    key = WORKSPACE + '/objects/' + digest
    with formal_target(load_postgres_config()) as (runtime, admin):
        target = target_etl(runtime)
        with psycopg.connect(target.database_url, passfile=LIBPQ_DISABLED_PASSFILE) as conn:
            graph = SyntheticGraph(conn, overrides={'artifact_objects': {'sha256': digest, 'relative_key': key, 'byte_size': len(payload)}})
            graph.ensure('artifact_objects')
            conn.execute("UPDATE shiliu.artifact_objects SET sha256=%s,relative_key=%s,byte_size=%s", (digest,key,len(payload)))
            graph.rows['artifact_objects'].update(sha256=digest,relative_key=key,byte_size=len(payload))
            graph.ensure('collection_embeddings')
            graph.ensure('assistant_wiki_proposals')
            conn.execute("CREATE TABLE shiliu_migration.rebuild_receipts (run_id text PRIMARY KEY,source_manifest_hash text NOT NULL,policy_version text NOT NULL,status text NOT NULL,details jsonb NOT NULL)")
            conn.execute("INSERT INTO shiliu_migration.rebuild_receipts VALUES ('synthetic','synthetic','test','ready','{}')")
            conn.execute("INSERT INTO shiliu.assistant_notifications(id,workspace_id,principal_id,event_key,origin_type,origin_id,source_type,created_at,activity_at) SELECT 'backup-test',id,owner_user_id,'backup-test','job_issue','synthetic-job','system',now(),now() FROM shiliu.workspaces LIMIT 1")
            conn.execute("UPDATE shiliu.assistant_wiki_proposals SET content_version=2")
            for name, table in MAPPING['tables'].items():
                for col, definition in table['columns'].items():
                    if definition['identity']:
                        conn.execute(sql.SQL("SELECT setval(pg_get_serial_sequence(%s,%s),COALESCE((SELECT max({}) FROM shiliu.{}),1),true)").format(sql.Identifier(col),sql.Identifier(name)), ('shiliu.'+name,col))
        artifact = target.artifact_root / key
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(payload)
        before = runtime_report(target)
        assert before["revision"] == "0014_assistant_source_patch"
        assert before["counts"]["assistant_notifications"] == 1
        assert len(before["counts"]) == 132
        with psycopg.connect(target.database_url, passfile=LIBPQ_DISABLED_PASSFILE) as conn:
            conn.execute("UPDATE shiliu.videos SET reading_state='read'")
        current = runtime_report(target)
        assert current["logical_hashes"]["videos"] != before["logical_hashes"]["videos"]
        directory = TASK_ROOT / "backups" / ("w14_runtime_" + uuid.uuid4().hex[:10])
        monkeypatch.setattr(cli, "load_postgres_config", lambda: target)
        require_quiescent(target)
        assert main(["create", str(directory), "--writers-stopped"]) == 0
        from shiliu.migration.backup import verify_pair
        pair = verify_pair(directory)
        assert main(['verify', str(directory)]) == 0
        saved = (directory / 'artifacts' / key).read_bytes()
        (directory / 'artifacts' / key).write_bytes(b'tampered')
        with pytest.raises(MigrationRejected, match='artifact_hash_mismatch'):
            verify_pair(directory)
        (directory / 'artifacts' / key).write_bytes(saved)
        assert pair["snapshot_kind"] == "running-database"
        assert pair["validation"] == current
        with formal_target(load_postgres_config(), revisions=()) as (runtime2, admin2):
            target2 = target_etl(runtime2)
            with psycopg.connect(admin2.database_url, passfile=LIBPQ_DISABLED_PASSFILE) as conn:
                conn.execute("CREATE SCHEMA shiliu")
                conn.execute("CREATE EXTENSION vector WITH SCHEMA shiliu VERSION '0.8.7'")
            occupied = target2.artifact_root / "occupied"
            occupied.write_text("synthetic")
            with pytest.raises(MigrationRejected, match="empty_artifacts"):
                restore_pair(directory, admin2, target2)
            occupied.unlink()
            monkeypatch.setattr(cli, "load_postgres_config", lambda: target2)
            assert main(["restore", str(directory), "--writers-stopped", "--admin-url", admin2.database_url]) == 0
            with pytest.raises(MigrationRejected, match="independent_empty_database"):
                restore_pair(directory, admin2, target2)
            assert runtime_report(target2) == current


def test_runtime_backup_rejects_catalog_drift_and_connected_writer():
    from shiliu.migration.catalog import read_catalog
    from shiliu.migration.schema import MIGRATIONS
    import json
    with formal_target(load_postgres_config()) as (runtime, admin):
        target = target_etl(runtime)
        with psycopg.connect(admin.database_url, passfile=LIBPQ_DISABLED_PASSFILE) as conn:
            conn.execute("SET LOCAL search_path=pg_catalog")
            assert read_catalog(conn) == json.loads((MIGRATIONS / 'contracts/runtime_0014_catalog.json').read_text())
            with pytest.raises(MigrationRejected, match='disconnected_writers'):
                require_quiescent(target)
            conn.execute("ALTER TABLE shiliu.assistant_notifications ADD COLUMN unapproved text")
        with pytest.raises(MigrationRejected, match='catalog_mismatch'):
            runtime_report(target)


def test_backup_cli_requires_explicit_stop_confirmation():
    with pytest.raises(SystemExit):
        main(['create', '/irrelevant'])
