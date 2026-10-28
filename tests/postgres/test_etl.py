from shiliu.config import LIBPQ_DISABLED_PASSFILE
import os
from dataclasses import replace
import json
from pathlib import Path
import uuid

import psycopg
from psycopg.conninfo import conninfo_to_dict,make_conninfo
import pytest

from shiliu.config import load_postgres_config
from shiliu.migration.safety import TASK_ROOT,guard,ETL_USER
from shiliu.migration.etl import import_snapshot,validate_snapshot
from shiliu.migration.snapshot import inspect_snapshot,plan_snapshot
from schema_support import formal_target
from poc_source import make_source


def target_etl(runtime):
    root=TASK_ROOT/'artifacts'/('w04_'+uuid.uuid4().hex[:12]);root.mkdir(mode=0o700)
    parts=conninfo_to_dict(runtime.database_url);parts['user']=ETL_USER
    config=replace(runtime,database_url=make_conninfo(**parts),artifact_root=root)
    guard(config,etl=True)
    return config


def test_inspect_plan_and_full_import_smoke():
    source=make_source()
    identity,raw=inspect_snapshot(source)
    identity,converted=plan_snapshot(source)
    assert len(converted['videos'])==3
    with formal_target(load_postgres_config()) as (runtime,admin):
        target=target_etl(runtime)
        report=import_snapshot(source,target,'w04_smoke')
        assert report['counts']['videos']==3 and report['artifacts_verified']==3
        (TASK_ROOT/'poc-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        assert import_snapshot(source,target,'w04_smoke')==report


@pytest.fixture(scope='module')
def closed_source():return make_source()


def test_poc_history_context_memory_state_bytes_identity_and_empty_sequence(closed_source):
    from shiliu.migration.history import old_ask_citation,resolve_version
    from shiliu.migration.values import JsonDocument
    from shiliu.storage.postgres import PgDatabase
    from shiliu.storage.scope import personal_context
    from shiliu.migration.schema import HEAD_REVISION
    identity,expected=plan_snapshot(closed_source)
    with formal_target(load_postgres_config()) as (runtime,admin):
        target=target_etl(runtime)
        report=import_snapshot(closed_source,target,'w04_contract')
        with PgDatabase(runtime) as db:
            db.validate_startup(revision=HEAD_REVISION,context=personal_context())
            with db.read() as c:
                ask=expected['ask_runs'][0]
                dto,raw,payload=old_ask_citation(c,target.artifact_root,ask['run_id'])
                old=next(a for a in identity['artifacts'] if not a['is_head'])
                assert raw==(closed_source.parent/old['source_file']).read_bytes()
                assert payload[0]['content']=='合成证据' and dto['created_at'].endswith('+00:00')
                new=next(a for a in identity['artifacts'] if a['logical_key']=='subtitle:1' and a['is_head'])
                assert old['source_version']!=new['source_version'] and json.loads(raw)==json.loads((closed_source.parent/new['source_file']).read_bytes())
                assert c.execute('SELECT membership_highwater FROM shiliu.workspace_guards').fetchone()['membership_highwater']==20
                assert [r['membership_seq'] for r in c.execute('SELECT membership_seq FROM shiliu.video_source_memberships ORDER BY membership_seq')]==[4,9,20]
                assert [r['seq'] for r in c.execute('SELECT seq FROM shiliu.assistant_messages ORDER BY seq')]==[4,9]
                assert c.execute('SELECT insertion_seq FROM shiliu.assistant_runs').fetchone()['insertion_seq']==7
                context=c.execute('SELECT context_state_json FROM shiliu.assistant_threads').fetchone()['context_state_json']
                assert context['format_version']==1 and context['frozen']['messages'][0]['content']=='合成原始原话'
                chain=c.execute('SELECT revision,parent_revision_id FROM shiliu.research_fact_revisions ORDER BY revision').fetchall()
                assert len(chain)==2 and chain[1]['parent_revision_id'] is not None
                assert c.execute('SELECT current_revision_id FROM shiliu.research_knowledge_fact_states').fetchone()['current_revision_id']=='synthetic_fact_revision_2'
                effects=c.execute('SELECT status,owner_epoch,provider_operation_id FROM shiliu.research_side_effects').fetchone()
                assert effects=={'status':'unknown','owner_epoch':7,'provider_operation_id':'synthetic_upstream_task'}
                assert c.execute('SELECT task_id FROM shiliu.asr_jobs').fetchone()['task_id']=='synthetic_existing_asr_task'
                assert c.execute('SELECT owner_epoch FROM shiliu.research_tasks').fetchone()['owner_epoch']==7
                budget=c.execute('SELECT requests_used,usage_json FROM shiliu.assistant_model_budget_days').fetchone()
                assert budget['requests_used']==9 and budget['usage_json']['unknown'] is True
                assert c.execute("SELECT count(*) AS n FROM shiliu.memory_embeddings").fetchone()['n']==0
                vec=c.execute('SELECT embedding FROM shiliu.collection_embeddings').fetchone()['embedding']
                assert vec.to_list()==[1.]+[0.]*511
                assert c.execute('SELECT model_id FROM shiliu.embedding_profiles').fetchone()['model_id']=='synthetic-fixed512'
                jobs=c.execute('SELECT kind,status,attempt,lease_epoch,payload_json FROM shiliu.assistant_jobs').fetchall()
                assert all(r['attempt']==2 and r['lease_epoch']==5 and r['payload_json']['storage_backend']=='pgvector' and 'backend_id' not in r['payload_json'] for r in jobs)
                assert {r['kind']:r['status'] for r in jobs}=={'memory_index':'blocked','memory_purge':'completed'}
                memory=c.execute("SELECT text,search_vector FROM shiliu.assistant_memories WHERE id='memory_forgotten'").fetchone()
                assert memory=={'text':'','search_vector':''}
                nulls=c.execute('SELECT id,before_json,before_json IS NULL AS sql_null FROM shiliu.assistant_memory_changes ORDER BY id').fetchall()
                assert nulls[0]['before_json'] is None and nulls[0]['sql_null'] is False
                assert nulls[1]['before_json'] is None and nulls[1]['sql_null'] is True
                row=c.execute('SELECT after_json FROM shiliu.assistant_memory_changes WHERE id=1').fetchone()['after_json']
                assert row['present'] is None and 'missing' not in row and row['order']==[3,1,2]
        with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as c:
            next_video=c.execute("INSERT INTO shiliu.videos (workspace_id,platform,source_id,part,title,video_url,status,discovered_at,updated_at) VALUES ('personal:local_operator','synthetic','new',1,'新行','synthetic','pending',clock_timestamp(),clock_timestamp()) RETURNING id").fetchone()[0]
            assert next_video==4
            # Empty identity table starts at 1, not an incorrectly consumed 2.
            n=c.execute("INSERT INTO shiliu.taxonomy_corpus_snapshots (workspace_id,selected_source_ids_json,membership_count,content_count,duplicate_memberships_merged,discovery_eligible_count,trial_assignment_only_count,evidence_counts_json,snapshot_hash,created_at,frozen_at) VALUES ('personal:local_operator','[]',0,0,0,0,0,'{}','synthetic-new-hash',clock_timestamp(),clock_timestamp()) RETURNING id").fetchone()[0]
            assert n==1


def test_batch_interruption_resume_and_failed_batch_is_atomic(closed_source):
    from shiliu.migration.values import MigrationRejected
    with formal_target(load_postgres_config()) as (runtime,admin):
        target=target_etl(runtime)
        with pytest.raises(MigrationRejected,match='injected_import_interruption'):
            import_snapshot(closed_source,target,'w04_resume',_fault_after_batches=2)
        with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as c:
            assert c.execute("SELECT status FROM shiliu.migration_runs WHERE run_id='w04_resume'").fetchone()[0]=='importing'
            assert c.execute('SELECT count(*) FROM shiliu.migration_batches').fetchone()[0]==2
        result=import_snapshot(closed_source,target,'w04_resume')
        assert result['counts']['videos']==3
    with formal_target(load_postgres_config()) as (runtime,admin):
        target=target_etl(runtime)
        with pytest.raises(MigrationRejected,match='injected_batch_failure'):
            import_snapshot(closed_source,target,'w04_atomic',_fault_inside_table='videos')
        with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as c:
            assert c.execute('SELECT count(*) FROM shiliu.videos').fetchone()[0]==0
            assert c.execute("SELECT count(*) FROM shiliu.migration_batches WHERE table_name='videos'").fetchone()[0]==0
            assert c.execute('SELECT count(*) FROM shiliu.migration_exceptions').fetchone()[0]==1
        assert import_snapshot(closed_source,target,'w04_atomic')['counts']['videos']==3


def clone_source(source):
    import shutil
    dest=source.parent.parent/('w04_'+uuid.uuid4().hex[:12])
    shutil.copytree(source.parent,dest);dest.chmod(0o700)
    return dest/'source.sqlite3'


@pytest.mark.parametrize('statement,category',[
    ("UPDATE assistant_memory_changes SET after_json='{broken' WHERE id=1",'invalid_json'),
    ("UPDATE assistant_memories SET created_at='2026-10-23T08:00:00'",'unknown_timestamp_timezone_or_format'),
    ("UPDATE assistant_messages SET thread_id='missing-thread'",'source_fk_orphan'),
])
def test_invalid_json_unknown_timezone_and_orphans_rejected(closed_source,statement,category):
    import sqlite3
    from shiliu.migration.values import MigrationRejected
    source=clone_source(closed_source)
    with sqlite3.connect(source) as c:c.execute(statement)
    with pytest.raises(MigrationRejected,match=category):plan_snapshot(source)


def test_source_identity_binding_target_pk_conflict_and_artifact_missing(closed_source):
    import sqlite3
    from shiliu.migration.values import MigrationRejected
    with formal_target(load_postgres_config()) as (runtime,admin):
        target=target_etl(runtime)
        import_snapshot(closed_source,target,'w04_conflicts')
        changed=clone_source(closed_source)
        with sqlite3.connect(changed) as c:c.execute("UPDATE videos SET title='不同输入' WHERE id=1")
        with pytest.raises(MigrationRejected,match='migration_input_identity_conflict'):
            import_snapshot(changed,target,'w04_conflicts')
        with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as c:c.execute("UPDATE shiliu.videos SET title='目标被更改' WHERE id=1")
        with pytest.raises(MigrationRejected,match='same_primary_key_different_payload'):
            import_snapshot(closed_source,target,'w04_conflicts')
    missing=clone_source(closed_source)
    (missing.parent/'files'/'0.json').unlink()
    with pytest.raises(MigrationRejected,match='artifact_missing_or_unsafe'):plan_snapshot(missing)


def test_dump_restore_into_independent_database_and_artifact_root(closed_source):
    import shutil,subprocess
    from shiliu.migration.schema import grant_roles
    from shiliu.migration.history import old_ask_citation
    from shiliu.storage.postgres import PgDatabase
    from shiliu.migration.safety import RUN_USER
    with formal_target(load_postgres_config()) as (runtime,admin):
        target=target_etl(runtime)
        report=import_snapshot(closed_source,target,'w04_restore')
        directory=TASK_ROOT/'backups';directory.mkdir(mode=0o700,exist_ok=True)
        dump=directory/('w04_'+uuid.uuid4().hex+'.dump')
        guard(admin,admin=True)
        subprocess.run([str(TASK_ROOT/'pg/bin/pg_dump'),'--dbname',admin.database_url,'--format=custom','--no-owner','--no-acl','--file',str(dump)],check=True,capture_output=True,timeout=15,env=dict(os.environ,PGPASSFILE=LIBPQ_DISABLED_PASSFILE))
        with formal_target(load_postgres_config(),revisions=()) as (restored_runtime,restored_admin):
            guard(restored_admin,admin=True)
            subprocess.run([str(TASK_ROOT/'pg/bin/pg_restore'),'--dbname',restored_admin.database_url,'--no-owner','--no-acl','--exit-on-error',str(dump)],check=True,capture_output=True,timeout=15,env=dict(os.environ,PGPASSFILE=LIBPQ_DISABLED_PASSFILE))
            with psycopg.connect(restored_admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as c:
                grant_roles(c,runtime_role=RUN_USER,etl_role=ETL_USER)
                from psycopg import sql
                for role in [RUN_USER,ETL_USER]:
                    c.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(conninfo_to_dict(restored_admin.database_url)['dbname']),sql.Identifier(role)))
            restored=target_etl(restored_runtime)
            shutil.copytree(target.artifact_root,restored.artifact_root,dirs_exist_ok=True)
            assert validate_snapshot(closed_source,restored,'w04_restore')==report
            (TASK_ROOT/'poc-restore-report.json').write_text(json.dumps({'source_report':report,'restored_report_equal':True,'independent_database':target.database_url!=restored.database_url,'independent_artifact_root':target.artifact_root!=restored.artifact_root},ensure_ascii=False,indent=2)+'\n')
            with PgDatabase(restored_runtime) as db:
                with db.read() as c:
                    run=c.execute('SELECT run_id FROM shiliu.ask_runs').fetchone()['run_id']
                    _,raw,payload=old_ask_citation(c,restored.artifact_root,run)
                    assert payload[0]['content']=='合成证据'
                    assert c.execute('SELECT payload_json FROM shiliu.research_workspace_records').fetchone()['payload_json']['中文']=='合成追加工作记录'


def test_cli_inspect_plan_are_socket_free_and_unsupported_rebuild_fails(closed_source,monkeypatch,capsys):
    from shiliu.migration.__main__ import main
    from shiliu.migration.safety import ETL_USER
    config=load_postgres_config()
    parts=conninfo_to_dict(config.database_url);parts['user']=ETL_USER
    args=['--source',str(closed_source),'--database-url',make_conninfo(**parts),
          '--artifact-root',str(config.artifact_root),'--environment','test','--run-id','w04_cli']
    with monkeypatch.context() as no_socket:
        no_socket.setattr(psycopg,'connect',lambda *a,**k:(_ for _ in ()).throw(AssertionError('inspect/plan must not connect')))
        assert main(['inspect',*args])==0
        assert main(['plan',*args])==0
    # Retain the W04 testcase identity. W14 implements rebuild; its real
    # predecessor gate now rejects an empty target with no imported run.
    with formal_target(config) as (runtime,admin):
        target=target_etl(runtime)
        args[args.index('--database-url')+1]=target.database_url
        args[args.index('--artifact-root')+1]=str(target.artifact_root)
        assert main(['rebuild',*args])==1
    output=capsys.readouterr()
    assert 'target_modified' in output.out and 'migration_run_missing' in output.err
    assert config.database_url not in output.out+output.err


def test_ready_replay_rejects_pointer_tamper_and_missing_target_bytes(closed_source):
    from shiliu.migration.values import MigrationRejected
    with formal_target(load_postgres_config()) as (runtime,admin):
        target=target_etl(runtime)
        import_snapshot(closed_source,target,'w04_pointer')
        with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as c:c.execute('UPDATE shiliu.assistant_source_heads SET current_revision=NULL')
        with pytest.raises(MigrationRejected,match='same_primary_key_different_payload'):
            import_snapshot(closed_source,target,'w04_pointer')
    with formal_target(load_postgres_config()) as (runtime,admin):
        target=target_etl(runtime)
        import_snapshot(closed_source,target,'w04_missing_target')
        identity,_=inspect_snapshot(closed_source)
        (target.artifact_root/identity['artifacts'][0]['relative_key']).unlink()
        with pytest.raises(MigrationRejected,match='target_artifact_missing_or_changed'):
            validate_snapshot(closed_source,target,'w04_missing_target')


def test_actual_standalone_cli_import_validate_report_and_no_application_import(closed_source):
    import subprocess,sys
    with formal_target(load_postgres_config()) as (runtime,admin):
        target=target_etl(runtime)
        args=['--source',str(closed_source),'--database-url',target.database_url,'--artifact-root',str(target.artifact_root),
              '--environment','test','--run-id','w04_standalone']
        for command in ['import','validate','report']:
            done=subprocess.run([sys.executable,'-m','shiliu.migration',command,*args],capture_output=True,text=True,timeout=20)
            assert done.returncode==0,done.stderr
            result=json.loads(done.stdout)
            assert result['run_id']=='w04_standalone'
            if command=='report':assert result['status']=='ready'
            assert target.database_url not in done.stdout+done.stderr
        script="""
import sys
from shiliu.migration.__main__ import main
assert 'shiliu.app' not in sys.modules
sys.addaudithook(lambda event,args: (_ for _ in ()).throw(AssertionError('socket')) if event in {'socket.connect','socket.__new__'} else None)
raise SystemExit(main(sys.argv[1:]))
"""
        done=subprocess.run([sys.executable,'-c',script,'plan',*args],capture_output=True,text=True,timeout=10)
        assert done.returncode==0,done.stderr


def test_comprehensive_source_revision_hash_and_historical_dto(closed_source):
    from shiliu.migration.history import resolve_version
    from shiliu.assistant.snapshots import _json_hash
    from shiliu.storage.postgres import PgDatabase
    identity,rows=plan_snapshot(closed_source)
    revision=rows['assistant_source_revisions'][0]['revision']
    with formal_target(load_postgres_config()) as (runtime,admin):
        target=target_etl(runtime)
        import_snapshot(closed_source,target,'w04_revision')
        with PgDatabase(runtime) as db:
            with db.read() as c:
                payload=json.loads(resolve_version(c,target.artifact_root,'personal:local_operator','source_snapshot:'+revision,revision))
                assert revision==_json_hash({key:payload[key] for key in ['metadata_hash','content_hash','membership_hash']}|{'extractor_version':'assistant-source-v1'})
                assert revision not in {a['sha256'] for a in identity['artifacts'] if a['logical_key']=='subtitle:1'}
                row=c.execute('SELECT discovered_at,published_at FROM shiliu.videos WHERE id=1').fetchone()
                assert row['discovered_at'].isoformat()=='2026-10-23T00:01:02+00:00'
                assert row['published_at']==1792713662


def test_invalid_vector_and_source_guard_boundaries(closed_source):
    from shiliu.migration.safety import guard_source
    from shiliu.migration.values import MigrationRejected
    source=clone_source(closed_source)
    (source.parent/'synthetic_vectors.json').write_text(json.dumps([{'unit_id':'synthetic','values':[0.]*512}]))
    with pytest.raises(MigrationRejected,match='invalid_synthetic_vector'):plan_snapshot(source)
    with pytest.raises(ValueError,match='Refusing unknown W04 source'):
        guard_source(Path('/tmp/unknown_daily_source.sqlite3'))


def test_terminal_research_cycle_keeps_terminal_state_result_and_immutable_parents(closed_source):
    import sqlite3
    from shiliu.storage.postgres import PgDatabase
    source=clone_source(closed_source)
    with sqlite3.connect(source) as c:
        c.row_factory=sqlite3.Row
        task=dict(c.execute('SELECT * FROM research_tasks').fetchone())
        attempt=dict(c.execute('SELECT * FROM research_attempts').fetchone())
        checkpoint=dict(c.execute('SELECT * FROM research_checkpoints').fetchone())
        c.execute("INSERT INTO research_results (result_id,task_id,goal_id,attempt_id,checkpoint_id,answer_status,termination_reason,failure_class,reason_detail,is_task_terminal,owner_epoch,created_at) VALUES (?,?,?,?,?,'not_produced','cancelled','none','synthetic history',1,7,'2026-10-23T00:00:00+00:00')",('synthetic_terminal_result',task['task_id'],attempt['goal_id'],attempt['attempt_id'],checkpoint['checkpoint_id']))
        c.execute("UPDATE research_tasks SET status='terminal',terminal_result_id='synthetic_terminal_result'")
        c.execute("UPDATE research_attempts SET status='terminal',result_id='synthetic_terminal_result'")
    with formal_target(load_postgres_config()) as (runtime,admin):
        target=target_etl(runtime)
        from shiliu.migration.values import MigrationRejected
        with pytest.raises(MigrationRejected,match='injected_batch_failure'):
            import_snapshot(source,target,'w04_terminal',_fault_inside_table='research_results')
        with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as c:
            assert c.execute('SELECT count(*) FROM shiliu.research_tasks').fetchone()[0]==0
            assert c.execute('SELECT count(*) FROM shiliu.migration_batches').fetchone()[0]==0
        report=import_snapshot(source,target,'w04_terminal')
        assert report['counts']['research_results']==1
        assert import_snapshot(source,target,'w04_terminal')==report
        with PgDatabase(runtime) as db:
            with db.read() as c:
                row=c.execute('SELECT status,terminal_result_id FROM shiliu.research_tasks').fetchone()
                assert row=={'status':'terminal','terminal_result_id':'synthetic_terminal_result'}
                assert c.execute('SELECT is_task_terminal FROM shiliu.research_results').fetchone()['is_task_terminal'] is True
