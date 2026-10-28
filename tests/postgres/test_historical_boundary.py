"""Historical SQLite is closed/read-only and absent from formal import chains."""
import sqlite3
import subprocess
import sys
import pytest
from shiliu.migration.readonly import connect_snapshot
from shiliu.migration.values import MigrationRejected


def test_snapshot_reader_never_creates_or_writes_and_closes_handle(tmp_path):
    path=tmp_path/'synthetic.sqlite3'
    with pytest.raises(MigrationRejected,match='missing'):
        connect_snapshot(path)
    assert not path.exists()
    with sqlite3.connect(path) as c:c.execute('CREATE TABLE synthetic(id INTEGER)')
    before=path.read_bytes()
    with connect_snapshot(path) as c:
        assert c.execute('SELECT count(*) FROM synthetic').fetchone()==(0,)
        with pytest.raises(sqlite3.OperationalError):c.execute('INSERT INTO synthetic VALUES(1)')
    with pytest.raises(sqlite3.ProgrammingError):c.execute('SELECT 1')
    assert path.read_bytes()==before
    for suffix in ('-wal','-journal'):
        sidecar=path.with_name(path.name+suffix);sidecar.write_bytes(b'nonempty-synthetic-journal')
        with pytest.raises(MigrationRejected,match='not_closed'):connect_snapshot(path)
        sidecar.unlink()
    assert not path.with_name(path.name+'-shm').exists()
    link=tmp_path/'linked.sqlite3'
    link.symlink_to(path)
    from shiliu.evidence.audit import audit_snapshot_chunk_mappings
    with pytest.raises(MigrationRejected,match='symlink'):
        audit_snapshot_chunk_mappings(snapshot_db=link,artifact_manifest=tmp_path/'unused.json')



def test_formal_cli_web_imports_do_not_load_historical_readers():
    code='''
import sys
import shiliu.cli, shiliu.web
for name in ('shiliu.eval.snapshot','shiliu.evidence.audit','shiliu.eval_v3_5.packets','shiliu.retrieval.adoption'):
    assert name not in sys.modules, name
assert not any(n.startswith('shiliu.migration.legacy_schema') for n in sys.modules)
from shiliu.assistant.store import AssistantRunStore
from shiliu.assistant.pg_store import PgAssistantRunStore
assert AssistantRunStore is PgAssistantRunStore
from shiliu.ask import persistence
assert not hasattr(persistence,'LegacyAskRunStore')
assert not hasattr(persistence,'initialize_ask_schema')
'''
    done=subprocess.run([sys.executable,'-c',code],check=False,capture_output=True,text=True,timeout=20)
    assert done.returncode==0,done.stderr


def test_historical_navigation_requires_explicit_snapshot_and_records_its_provenance(tmp_path):
    from contextlib import closing
    import sqlite3
    from scripts.export_pqs_v1_authoring_packet import load_navigation_metadata,build_content_map
    with pytest.raises(ValueError,match='explicit historical snapshot'):load_navigation_metadata()
    path=tmp_path/'navigation.sqlite3'
    with closing(sqlite3.connect(path)) as c,c:
        c.execute('CREATE TABLE videos(id INTEGER,title TEXT,uploader TEXT,description TEXT,subtitle_language TEXT,subtitle_source TEXT,summary_path TEXT,artifact_dir TEXT,status TEXT)')
        c.execute("INSERT INTO videos VALUES(1,'synthetic PostgreSQL','synthetic','database','zh','human','','','completed')")
    topics,provenance=build_content_map(load_navigation_metadata(path))
    assert topics and len(provenance)==1 and provenance[0]['metadata_database']==str(path)
