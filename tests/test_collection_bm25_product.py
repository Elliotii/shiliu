"""Opt-in integration tests against the dedicated BM25 implementation cluster."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from uuid import uuid4
import importlib.util
import json
import os
import sys
import psycopg
from psycopg import sql
import pytest

pytestmark=pytest.mark.skipif(os.environ.get('SHILIU_BM25_PRODUCT_TEST')!='1',reason='dedicated isolated BM25 cluster required')
from research.postgres_eval.bm25_product import config, admin, ROOT, write
from shiliu.retrieval.bm25 import install_extension,check_index,RANKING_VERSION,grant_query_access
from shiliu.migration.schema import upgrade,grant_roles,HEAD_REVISION
from shiliu.storage.postgres import PgDatabase,PoolSettings
from shiliu.storage.scope import personal_context,ResourceContext
from shiliu.storage.errors import StorageError
from shiliu.db import Database
from shiliu.artifacts import ArtifactStore
from shiliu.retrieval.service import RetrievalService,INDEX_VERSION
from shiliu.retrieval.coordinator import ProjectionWorker
from shiliu.retrieval.models import RetrievalFilters
from shiliu.retrieval.f1 import F1LexicalIndex

spec=importlib.util.spec_from_file_location('existing_collection_helpers',Path(__file__).parent/'postgres/test_collection_retrieval.py')
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)


@pytest.fixture(scope='module')
def resources():
    name='shiliu_bm25_fixture_'+uuid4().hex[:10]
    with admin('shiliu_bm25_fixture') as c:
        c.commit();c.autocommit=True;c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    try:
        with admin(name) as c:install_extension(c)
        with admin(name) as c:
            c.commit();c.row_factory=psycopg.rows.tuple_row;upgrade(c)
        with admin(name) as c:grant_roles(c,runtime_role='shiliu_bm25_runtime',etl_role='shiliu_bm25_etl')
        with PgDatabase(config(name),settings=PoolSettings(min_size=1,max_size=1)) as pg:
            db=Database(pg,personal_context());art=ArtifactStore(ROOT/'fixture-artifacts'/name,db);lex=RetrievalService(db=db,artifacts=art)
            yield db,art,lex,None
    finally:
        with admin('shiliu_bm25_fixture') as c:
            c.commit();c.autocommit=True;c.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


def add(resources,index,text,sid=None):
    sid,vid=helpers.add_video(resources,index,text,sid=sid)
    ProjectionWorker(resources[2]).run_one(video_id=vid)
    return sid,vid


def search(resources,query,**kw):return resources[2].search(query,level='transcript_chunk',navigation=False,**kw)


def test_bootstrap_pool_and_catalog(resources):
    db,art,lex,_=resources
    with db.connect() as c:
        check_index(c)
        assert c.execute('SHOW search_path').fetchone()['search_path']=='pg_catalog, shiliu'
        assert c.execute('SHOW default_text_search_config').fetchone()['default_text_search_config']=='pg_catalog.simple'
        assert c.execute('SELECT rolsuper FROM pg_roles WHERE rolname=current_user').fetchone()['rolsuper'] is False
        assert c.execute('SELECT version_num FROM shiliu.alembic_version').fetchone()['version_num']==HEAD_REVISION
        c.execute("SET default_text_search_config='pg_catalog.english'")
    with db.connect() as c:assert c.execute('SHOW default_text_search_config').fetchone()['default_text_search_config']=='pg_catalog.simple'
    for statement in ('CREATE TABLE shiliu.forbidden(id int)','CREATE TABLE shiliu_search.forbidden(id int)','SELECT shiliu_search.bm25_dump_index(\'shiliu.retrieval_units_chunk_bm25\')'):
        with pytest.raises(StorageError) as caught:
            with db.connect() as c:c.execute(statement)
        assert caught.value.sqlstate=='42501'
    from shiliu.migration.catalog import read_catalog,compare_catalog
    mapping=json.loads(Path('migrations/contracts/schema26_target.json').read_text())
    from psycopg.conninfo import conninfo_to_dict
    with admin(conninfo_to_dict(db.pg.config.database_url)['dbname']) as c:
        assert compare_catalog(read_catalog(c),mapping)==[]
    assert F1LexicalIndex(lex).ensure_ready()['index_version']==RANKING_VERSION
    assert lex.statistics()['index']['index_version']==INDEX_VERSION


def test_or_match_sign_empty_and_scopes(resources):
    sid,vid=add(resources,101,'稀有词甲 alpha KTC 27gr95qe');_,v2=add(resources,102,'仅有别的 banana')
    hits=search(resources,'稀有词甲 alpha KTC 27gr95qe');assert hits and all(h.lexical_score>0 for h in hits)
    assert {h.video_id for h in hits}=={vid}
    for q in ('','!!!','完全不存在zzzz'):assert search(resources,q)==[]
    assert search(resources,'alpha',filters=RetrievalFilters(video_ids=()))==[]
    assert search(resources,'alpha',filters=RetrievalFilters(video_ids=(v2,)))==[]
    for f in (RetrievalFilters(video_ids=(vid,)),RetrievalFilters(folder_id=101),RetrievalFilters(source_db_id=sid),RetrievalFilters(favorite_time_from=201,favorite_time_to=201),RetrievalFilters(archived=False)):
        assert {h.video_id for h in search(resources,'alpha',filters=f)}=={vid}
    for f in (RetrievalFilters(folder_id=99999),RetrievalFilters(favorite_time_from=202),RetrievalFilters(favorite_time_to=200),RetrievalFilters(archived=True)):
        assert search(resources,'alpha',filters=f)==[]
    db=resources[0];db.set_archived(vid,True)
    assert search(resources,'alpha',filters=RetrievalFilters(archived=False))==[]
    ProjectionWorker(resources[2]).run_one(video_id=vid)
    assert search(resources,'alpha',filters=RetrievalFilters(archived=True))
    db.set_archived(vid,False)
    db.set_ignored(vid,True);assert search(resources,'alpha')==[]
    db.set_ignored(vid,False);assert search(resources,'alpha')==[]  # generation fence
    ProjectionWorker(resources[2]).run_one(video_id=vid);assert search(resources,'alpha')
    with db.connect() as c:c.execute("UPDATE shiliu.favorite_sources SET status='removed' WHERE workspace_id=%s AND id=%s",(db.workspace_id,sid))
    assert search(resources,'alpha')==[]


def test_worker_update_delete_and_rollback(resources):
    db,art,lex,_=resources;sid,vid=add(resources,201,'oldworduniquex alpha')
    assert search(resources,'oldworduniquex')
    with pytest.raises(RuntimeError):
        with db.connect() as c:
            c.execute('DELETE FROM shiliu.retrieval_units WHERE workspace_id=%s AND video_id=%s',(db.workspace_id,vid))
            raise RuntimeError('rollback')
    assert search(resources,'oldworduniquex')
    from shiliu.domain import SubtitleSegment
    batch=art.batch(vid);_,ref=batch.save_raw_subtitle('BV0000000201',[SubtitleSegment.model_validate({'from':0,'to':3,'content':'newworduniquey beta'})])
    batch.commit(lambda c:db.update_video(vid,raw_subtitle_path=ref,conn=c))
    assert search(resources,'oldworduniquex')==[]
    ProjectionWorker(lex).run_one(video_id=vid)
    assert search(resources,'oldworduniquex')==[] and search(resources,'newworduniquey')
    db.record_source_snapshot(sid,[],processing_profile='formal',authoritative=True)
    assert search(resources,'newworduniquey')==[]
    ProjectionWorker(lex).run_one(video_id=vid)
    with db.connect(read_only=True) as c:assert c.execute('SELECT count(*) AS n FROM shiliu.retrieval_units WHERE workspace_id=%s AND video_id=%s',(db.workspace_id,vid)).fetchone()['n']==0


class RecordingConnection:
    def __init__(self,c,queries):self.c=c;self.queries=queries
    def execute(self,s,p=None,*a,**kw):
        if isinstance(s,str) and s.startswith('SELECT u.*,-('):self.queries.append((s,p))
        return self.c.execute(s,p,*a,**kw)
    def __getattr__(self,key):return getattr(self.c,key)


def test_real_join_filtered_topk_oracle_and_plan(resources,monkeypatch):
    db,art,lex,_=resources
    # Two real projected videos; clone chunks inside the same product table.
    _,hidden=add(resources,301,'needlefilter')
    _,kept=add(resources,302,'needlefilter extra extra extra extra extra')
    with db.connect() as c:
        cols=c.execute("SELECT attname FROM pg_attribute WHERE attrelid='shiliu.retrieval_units'::regclass AND attnum>0 AND NOT attisdropped ORDER BY attnum").fetchall()
        fields=[x['attname'] for x in cols]
        for vid,n,prefix in ((hidden,2048,'excluded'),(kept,64,'kept')):
            expressions=[sql.SQL('%s || g::text') if f=='unit_id' else sql.SQL('chunk_id || g::text') if f=='chunk_id' else sql.Identifier(f) for f in fields]
            c.execute(sql.SQL('INSERT INTO shiliu.retrieval_units ({}) SELECT {} FROM shiliu.retrieval_units CROSS JOIN generate_series(1,%s) g WHERE workspace_id=%s AND video_id=%s AND unit_type=\'transcript_chunk\'').format(sql.SQL(',').join(map(sql.Identifier,fields)),sql.SQL(',').join(expressions)),(prefix,n,db.workspace_id,vid))
    unfiltered=search(resources,'needlefilter',top_k=50)
    assert all(h.video_id==hidden for h in unfiltered)
    queries=[];original=db.connect
    @contextmanager
    def recorded(*a,**kw):
        with original(*a,**kw) as c:yield RecordingConnection(c,queries)
    monkeypatch.setattr(db,'connect',recorded)
    hits=search(resources,'needlefilter',top_k=50,filters=RetrievalFilters(video_ids=(kept,)))
    assert len(hits)==50 and {h.video_id for h in hits}=={kept}
    statement,params=queries[-1];pool_clause=statement.split('WHERE ',1)[1].rsplit(' ORDER BY ',1)[0]
    oracle="WITH m AS MATERIALIZED (SELECT u.unit_id,u.tokenized_text "+lex.current_join()+'WHERE '+pool_clause+") SELECT unit_id,-(tokenized_text OPERATOR(shiliu_search.<@>) shiliu_search.to_bm25query(%s,'shiliu.retrieval_units_chunk_bm25')) AS score FROM m ORDER BY score DESC,unit_id LIMIT %s"
    with original(read_only=True) as c:
        exact=c.execute(oracle,[*params[1:-2],params[0],params[-1]]).fetchall()
        plan=c.execute('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+statement,params).fetchone()['QUERY PLAN']
    assert [h.unit_id for h in hits]==[r['unit_id'] for r in exact]
    assert [h.lexical_score for h in hits]==pytest.approx([r['score'] for r in exact],abs=1e-7)
    write(ROOT/'evidence/filtered-join-plan.json',dict(plan=plan,oracle=oracle,kept=kept,excluded=hidden,rank_equal=True,score_equal=True,filtered=2049,retained=65))
    # Logical workspace isolation on the shared physical BM25 statistics.
    assert 'LIMIT' not in pool_clause


def test_missing_index_reports_not_ready(resources):
    db,art,lex,_=resources
    from psycopg.conninfo import conninfo_to_dict
    name=conninfo_to_dict(db.pg.config.database_url)['dbname']
    with admin(name) as c:c.execute('ALTER INDEX shiliu.retrieval_units_chunk_bm25 RENAME TO temporary_missing_bm25')
    try:
        with pytest.raises(StorageError,match='bm25_index_not_ready'):lex.chunk_index_identity()
        with pytest.raises(StorageError,match='bm25_index_not_ready'):search(resources,'needlefilter')
    finally:
        with admin(name) as c:c.execute('ALTER INDEX shiliu.temporary_missing_bm25 RENAME TO retrieval_units_chunk_bm25')


def test_workspace_filter_and_old_navigation(resources):
    db,art,lex,_=resources
    with db.connect() as c:
        c.execute("INSERT INTO shiliu.users(id,display_name) VALUES ('bm25_other','other')")
        c.execute("INSERT INTO shiliu.workspaces(id,kind,owner_user_id) VALUES ('personal:bm25_other','personal','bm25_other')")
        c.execute("INSERT INTO shiliu.workspace_guards(workspace_id) VALUES ('personal:bm25_other')")
    otherdb=Database(db.pg,ResourceContext('personal:bm25_other','bm25_other'))
    otherart=ArtifactStore(art.root if hasattr(art,'root') else ROOT/'other-artifacts',otherdb)
    otherlex=RetrievalService(db=otherdb,artifacts=otherart)
    add((otherdb,otherart,otherlex,None),401,'tenantprivateuniquex')
    assert otherlex.search('tenantprivateuniquex',level='transcript_chunk',navigation=False)
    assert search(resources,'tenantprivateuniquex')==[]
    _,vid=add(resources,501,'导航词字幕 navworduniquex')
    assert lex.search('字',level='transcript_chunk')[0].retrieval_method=='lexical_substring_fallback'
    assert lex.search('Claude',level='video') and lex.search('Claude',level='all')
    from shiliu.retrieval.orchestrator import SearchOrchestrator
    from shiliu.retrieval.planner import SearchRequest
    raw=SearchOrchestrator(db=db,lexical=lex,dense_factory=lambda:None,hybrid_factory=lambda:None)
    for scope,query,version in (('transcript_chunk','navworduniquex',RANKING_VERSION),('video','Claude',INDEX_VERSION),('all','Claude',INDEX_VERSION),('transcript_chunk','字',INDEX_VERSION)):
        response=raw.search(SearchRequest(query=query,mode='lexical',scope=scope))
        assert response.raw_hits and response.index_identity['lexical_index_version']==version
        assert response.trace_persisted
        with db.connect(read_only=True) as c:assert c.execute('SELECT lexical_index_version FROM shiliu.retrieval_search_traces WHERE workspace_id=%s AND trace_id=%s',(db.workspace_id,response.trace_id)).fetchone()['lexical_index_version']==version


def test_small_preinstalled_extension_restore(resources):
    import subprocess
    from psycopg.conninfo import conninfo_to_dict
    from shiliu.migration.backup import _preinstalled_vector_toc
    db,art,lex,_=resources
    source=conninfo_to_dict(db.pg.config.database_url)['dbname'];target='shiliu_bm25_fixture_restore_'+uuid4().hex[:8]
    with admin('shiliu_bm25_fixture') as c:
        c.commit();c.autocommit=True;c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(target)))
    pg=ROOT/'pg/bin';out=ROOT/'recovery';out.mkdir(exist_ok=True)
    dump=out/'fixture.dump'
    subprocess.run([str(pg/'pg_dump'),'-h','/tmp/shiiu-bm25impl-501','-p','55487','-U','shiliu_bm25_admin','-d',source,'-Fc','--no-owner','--no-acl','-f',str(dump)],check=True)
    with admin(target) as c:
        assert not c.execute("SELECT 1 FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='shiliu'").fetchone()
        c.execute(sql.SQL('GRANT CREATE ON DATABASE {} TO shiliu_bm25_restore').format(sql.Identifier(target)))
        c.execute('CREATE SCHEMA shiliu AUTHORIZATION shiliu_bm25_restore')
        c.execute("CREATE EXTENSION vector WITH SCHEMA shiliu VERSION '0.8.7'")
        install_extension(c);grant_query_access(c,'shiliu_bm25_restore',grant_option=True)
    listed=subprocess.check_output([str(pg/'pg_restore'),'--list',str(dump)],text=True)
    toc=out/'fixture.toc';toc.write_text(_preinstalled_vector_toc(listed))
    restored=subprocess.run([str(pg/'pg_restore'),'-h','/tmp/shiiu-bm25impl-501','-p','55487','-U','shiliu_bm25_restore','-d',target,'--no-owner','--no-acl','--exit-on-error','--use-list',str(toc),str(dump)],capture_output=True,text=True)
    (out/'pg_restore.log').write_text(restored.stdout+restored.stderr)
    assert restored.returncode==0,restored.stderr
    with psycopg.connect(config(target,role='shiliu_bm25_restore').database_url) as c:grant_roles(c,runtime_role='shiliu_bm25_runtime',etl_role='shiliu_bm25_etl')
    with PgDatabase(config(target)) as pool:
        restored_db=Database(pool,personal_context());restored_lex=RetrievalService(db=restored_db,artifacts=art)
        check=restored_lex.search('navworduniquex',level='transcript_chunk',navigation=False)
        assert check and all(r.lexical_score>0 for r in check)
        with restored_db.connect(read_only=True) as c:
            check_index(c)
            assert not c.execute("SELECT rolsuper FROM pg_roles WHERE rolname='shiliu_bm25_restore'").fetchone()['rolsuper']
    write(out/'result.json',dict(status='passed',restore_role_superuser=False,bootstrap_preinstalled=True,query_results=len(check),database=target))


def test_memory_wiki_lexical_paths_remain_independent(resources):
    # Reuse the existing small Wiki fixture, with no embedding provider at all.
    sys.path.insert(0,str(Path(__file__).parent/'postgres'))
    import test_wiki
    from shiliu.assistant.memory import MemoryService
    from shiliu.assistant.wiki_retrieval import WikiHybridIndex
    db,art,lex,_=resources
    parts=test_wiki.wiki_parts.__wrapped__(db,ROOT/'wiki-smoke')
    _,_,wiki,space,msg,_,_=parts
    page=test_wiki.create(wiki,space,msg,op='bm25-unrelated-wiki')
    index=WikiHybridIndex(None,wiki=wiki)
    result=index.search('事务',space_id=space)
    assert result['candidates'][0]['page_id']==page['id']
    memory=MemoryService(db)
    item=memory.save_explicit(text='保留独立记忆检索事务',subject_key='bm25-independent',kind='context',scope_kind='user',scope_id=None,operation_key='bm25-unrelated-memory',source_message_ids=[msg])
    assert item['id'] in {r['id'] for r in memory.recall('事务',space_id=space)}
