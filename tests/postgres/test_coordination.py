from __future__ import annotations
from shiliu.config import LIBPQ_DISABLED_PASSFILE
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date,timedelta,timezone
import multiprocessing
import threading
import time
from dataclasses import replace

import psycopg
import pytest

from shiliu.config import load_postgres_config
from shiliu.storage.postgres import PgDatabase
from shiliu.storage.scope import personal_context
from shiliu.storage.fences import (CoordinationConflict,guard_tool_operation,cancel_run,
    claim_task_root,guard_task_owner,append_run_event)
from shiliu.storage.scheduler import claim_job,job_transition,recover_job
from shiliu.storage.budget import reserve_dispatch,settle_dispatch
from shiliu.storage.receipts import (assistant_request_replay,mutation_replay,research_command_replay,research_effect_replay)
from schema_support import formal_target
from seed_rows import SyntheticGraph,insert,NOW,WORKSPACE
from psycopg.types.json import Jsonb

CTX=personal_context()


@pytest.fixture
def coordinated():
    with formal_target(load_postgres_config()) as (runtime,admin):
        with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as conn:
            graph=SyntheticGraph(conn)
            run=graph.ensure('assistant_runs')
            conn.execute("UPDATE shiliu.assistant_runs SET status='running',working_state_json='{}' WHERE id=%s",(run['id'],))
            task=graph.ensure('research_tasks')
            graph.ensure('research_attempts')
            job=graph.ensure('assistant_jobs')
            conn.execute("UPDATE shiliu.assistant_jobs SET kind='memory_index',status='queued',attempt=0,lease_epoch=0,not_before=clock_timestamp() WHERE id=%s",(job['id'],))
        with PgDatabase(runtime) as db:
            yield db,runtime,admin,run['id'],task['task_id'],job['id']


def race(db,operation):
    barrier=threading.Barrier(2)
    def worker(i):
        with db.transaction() as conn:
            pid=conn.info.backend_pid
            barrier.wait(timeout=3)
            return pid,operation(conn,i)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(worker,range(2)))
    assert results[0][0]!=results[1][0]
    return [r[1] for r in results]


def test_c01_job_and_task_claim_single_winner(coordinated):
    db,_,_,_,task,job=coordinated
    results=race(db,lambda c,i:claim_job(c,CTX,f'worker{i}',allow_model_jobs=False))
    assert sum(r is not None for r in results)==1
    winner=next(r for r in results if r)
    assert winner['id']==job and winner['attempt']==1 and winner['lease_epoch']==1
    with db.read() as conn:
        initial_epoch=conn.execute('SELECT owner_epoch FROM shiliu.research_tasks WHERE task_id=%s',(task,)).fetchone()['owner_epoch']
    results=race(db,lambda c,i:claim_task_root(c,CTX,task,f'worker{i}'))
    assert sum(r is not None for r in results)==1
    assert next(r for r in results if r)['owner_epoch']==initial_epoch+1


def test_c03_tool_lock_cancel_waits_then_post_cancel_rejected(coordinated):
    db,_,admin,run,_,_=coordinated
    started=threading.Event()
    worker_pid=[]
    def cancel():
        with db.transaction() as conn:
            worker_pid.append(conn.info.backend_pid)
            started.set()
            return cancel_run(conn,CTX,run)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with db.transaction() as conn:
            guard_tool_operation(conn,CTX,run,1)
            append_run_event(conn,CTX,run,'tool_committed_first',{})
            future=pool.submit(cancel)
            assert started.wait(2)
            deadline=time.monotonic()+2
            with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE,autocommit=True) as observer:
                while True:
                    waiting=observer.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s",(worker_pid[0],)).fetchone()
                    if waiting==('Lock',):break
                    if time.monotonic()>deadline:pytest.fail('cancel did not wait on the real lock')
                    time.sleep(.01)
            assert not future.done()
        cancelled=future.result(timeout=3)
    assert cancelled['status']=='cancelled' and cancelled['run_epoch']==2
    with pytest.raises(CoordinationConflict,match='run_fenced'):
        with db.transaction() as conn:
            guard_tool_operation(conn,CTX,run,1)
            append_run_event(conn,CTX,run,'forbidden_late_write',{})
    with db.read() as conn:
        kinds=[r['event_type'] for r in conn.execute('SELECT event_type FROM shiliu.assistant_run_events WHERE run_id=%s ORDER BY seq',(run,))]
        assert kinds==['tool_committed_first','run_cancelled']


def _tool_write_snapshot(conn,run):
    return conn.execute('SELECT t.title,(SELECT count(*) FROM shiliu.assistant_run_events WHERE run_id=r.id) AS events, '
                        '(SELECT count(*) FROM shiliu.assistant_messages WHERE thread_id=t.id) AS messages, '
                        '(SELECT count(*) FROM shiliu.assistant_tool_calls WHERE run_id=r.id) AS calls '
                        'FROM shiliu.assistant_runs r JOIN shiliu.assistant_threads t ON t.id=r.thread_id WHERE r.id=%s',
                        (run,)).fetchone()


def _guarded_tool_write(conn,run,epoch):
    row=guard_tool_operation(conn,CTX,run,epoch)
    conn.execute("UPDATE shiliu.assistant_threads SET title='guarded tool wrote' WHERE id=%s",(row['thread_id'],))
    append_run_event(conn,CTX,run,'guarded_tool_write',{})


@pytest.mark.parametrize('case,allowed',[
    ('nested_final',False),('expired',False),('future_offset',True),('unbudgeted',True),
    ('wrong_epoch',False),('queued',False),('completed',False),('cancelled',False),
    ('cancel_requested',False),('finish_requested',False),('budget_null',False),
    ('budget_empty',False),('budget_array',False),('invalid_deadline',False),
    ('unzoned_deadline',False),('numeric_deadline',False),
])
def test_tool_fence_budget_and_unbudgeted_writes(coordinated,case,allowed):
    db,_,_,run,_,_=coordinated
    with db.transaction() as conn:
        future=conn.execute("SELECT clock_timestamp()+interval '1 hour' AS at").fetchone()['at']
        state={}
        if case in {'nested_final','expired','future_offset','invalid_deadline','unzoned_deadline','numeric_deadline'}:
            deadline=(future-timedelta(hours=2) if case=='expired' else future).astimezone(timezone(timedelta(hours=8))).isoformat()
            if case=='invalid_deadline':deadline='invalid'
            if case=='unzoned_deadline':deadline=future.replace(tzinfo=None).isoformat()
            if case=='numeric_deadline':deadline=123
            state={'execution_budget':{'final_dispatched':case=='nested_final','deadline_at':deadline}}
        if case.startswith('budget_'):state={'execution_budget':{'budget_null':None,'budget_empty':{},'budget_array':[]}[case]}
        if case=='finish_requested':state={'finish_requested':True}
        status=case if case in {'queued','completed','cancelled'} else 'running'
        conn.execute('UPDATE shiliu.assistant_runs SET status=%s,cancel_requested=%s,working_state_json=%s WHERE id=%s',
                     (status,case in {'cancel_requested','cancelled'},Jsonb(state),run))
    with db.transaction() as conn:
        before=_tool_write_snapshot(conn,run)
        if allowed:
            _guarded_tool_write(conn,run,1)
        else:
            # Catch inside the committing transaction: a mistaken accepted
            # write cannot be hidden by a test-induced outer rollback.
            with pytest.raises(CoordinationConflict,match='run_fenced'):
                _guarded_tool_write(conn,run,2 if case=='wrong_epoch' else 1)
        after=_tool_write_snapshot(conn,run)
        if allowed:assert after['title']=='guarded tool wrote' and after['events']==before['events']+1
        else:assert after==before
    with db.read() as conn:
        assert _tool_write_snapshot(conn,run)==after


def test_tool_deadline_expires_after_transaction_start(coordinated):
    db,_,_,run,_,_=coordinated
    with db.transaction() as conn:
        deadline=conn.execute("SELECT clock_timestamp()+interval '0.3 seconds' AS at").fetchone()['at']
        conn.execute('UPDATE shiliu.assistant_runs SET working_state_json=%s WHERE id=%s',
                     (Jsonb({'execution_budget':{'final_dispatched':False,'deadline_at':deadline.isoformat()}}),run))
        guard_tool_operation(conn,CTX,run,1)
        # Wait until the database deadline, without depending on an app clock.
        conn.execute("SELECT pg_sleep(greatest(0,extract(epoch FROM (%s::timestamptz-clock_timestamp())))+0.02)",(deadline,))
        times=conn.execute('SELECT transaction_timestamp() AS start,clock_timestamp() AS actual').fetchone()
        assert times['start']<deadline<=times['actual']
        before=_tool_write_snapshot(conn,run)
        with pytest.raises(CoordinationConflict,match='run_fenced'):_guarded_tool_write(conn,run,1)
        assert _tool_write_snapshot(conn,run)==before
    with db.read() as conn:assert _tool_write_snapshot(conn,run)==before


def _process_fence(runtime,run,ready,cancelled,queue,kind):
    try:
        with PgDatabase(runtime) as db:
            if kind=='worker':
                with db.read() as conn:
                    epoch=conn.execute('SELECT run_epoch FROM shiliu.assistant_runs WHERE id=%s',(run,)).fetchone()['run_epoch']
                ready.set()
                if not cancelled.wait(5):raise RuntimeError('cancel barrier timeout')
                try:
                    with db.transaction() as conn:
                        guard_tool_operation(conn,CTX,run,epoch)
                        append_run_event(conn,CTX,run,'forbidden_process_result',{})
                except CoordinationConflict:queue.put(('worker','fenced'))
                else:queue.put(('worker','unexpected_publish'))
            else:
                if not ready.wait(5):raise RuntimeError('worker barrier timeout')
                with db.transaction() as conn:cancel_run(conn,CTX,run)
                cancelled.set();queue.put(('cancel','committed'))
    except Exception as error:
        queue.put(('error',type(error).__name__))
        cancelled.set();ready.set()


def test_c02_two_process_cancel_fences_computation_and_usage_still_settles(coordinated):
    db,runtime,_,run,_,_=coordinated
    with db.transaction() as conn:
        guard_tool_operation(conn,CTX,run,1)
        reserve_dispatch(conn,CTX,'late-real-cost',lane='foreground',request_limit=1,request_hash='a'*64,run_id=run)
    ctx=multiprocessing.get_context('spawn')
    ready=ctx.Event();cancelled=ctx.Event();queue=ctx.Queue()
    workers=[ctx.Process(target=_process_fence,args=(runtime,run,ready,cancelled,queue,k)) for k in ('worker','cancel')]
    for p in workers:p.start()
    try:
        for p in workers:
            p.join(timeout=10)
            assert p.exitcode==0
        assert {queue.get(timeout=2),queue.get(timeout=2)}=={('worker','fenced'),('cancel','committed')}
    finally:
        for p in workers:
            if p.is_alive():p.terminate();p.join(2)
        queue.close();queue.join_thread()
    with db.transaction() as conn:
        settle_dispatch(conn,CTX,'late-real-cost',usage={'input_tokens':7})
    with db.transaction() as conn:settle_dispatch(conn,CTX,'late-real-cost',usage={'input_tokens':7})
    with db.read() as conn:
        assert conn.execute('SELECT status FROM shiliu.assistant_runs WHERE id=%s',(run,)).fetchone()['status']=='cancelled'
        assert conn.execute("SELECT usage_json FROM shiliu.assistant_model_budget_days WHERE lane='foreground'").fetchone()['usage_json']=={'responses':1,'input_tokens':7}


def test_c04_lane_different_jobs_local_priority_and_stale_release(coordinated):
    db,_,admin,_,_,jobid=coordinated
    with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as conn:
        row=conn.execute('SELECT * FROM shiliu.assistant_jobs WHERE id=%s',(jobid,)).fetchone()
        # Use dict row to clone all required formal columns explicitly.
        from psycopg.rows import dict_row
        conn.row_factory=dict_row
        row=conn.execute('SELECT * FROM shiliu.assistant_jobs WHERE id=%s',(jobid,)).fetchone()
        conn.execute("UPDATE shiliu.assistant_jobs SET kind='memory_extract' WHERE id=%s",(jobid,))
        insert(conn,'assistant_jobs',dict(row,id='second-model',dedupe_key='second-model',kind='wiki_integrate'))
    results=race(db,lambda c,i:claim_job(c,CTX,f'model{i}'))
    assert sum(r is not None for r in results)==1
    old=next(r for r in results if r)
    with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as conn:
        insert(conn,'assistant_jobs',dict(row,id='local-purge',dedupe_key='local-purge',kind='memory_purge'))
    with db.transaction() as conn:
        purge=claim_job(conn,CTX,'purger',allow_model_jobs=False,allow_maintenance=False,activity_allowed=False,budget_allowed=False)
        assert purge['id']=='local-purge'
        job_transition(conn,CTX,purge['id'],'purger',purge['lease_epoch'],action='complete')
    # Use controlled local lease expiry, not a timing-dependent long sleep.
    with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as conn:
        conn.execute("UPDATE shiliu.assistant_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",(old['id'],))
        conn.execute("UPDATE shiliu.scheduler_lanes SET lease_until=clock_timestamp()-interval '1 second'")
    with db.transaction() as conn:new=claim_job(conn,CTX,'new-model')
    assert new and new['id']!=old['id']
    with pytest.raises(CoordinationConflict):
        with db.transaction() as conn:job_transition(conn,CTX,old['id'],old['lease_owner'],old['lease_epoch'],action='complete')
    with db.transaction() as conn:
        assert recover_job(conn,CTX,old['id'],disposition='unknown')
    with db.read() as conn:
        lane=conn.execute('SELECT * FROM shiliu.scheduler_lanes').fetchone()
        assert lane['active_job_id']==new['id']
        assert conn.execute('SELECT status FROM shiliu.assistant_jobs WHERE id=%s',(old['id'],)).fetchone()['status']=='blocked'


def test_c05_final_budget_slot_race_duplicate_settlement_and_identity(coordinated):
    db,_,_,run,_,_=coordinated
    def reserve(conn,i):
        try:return reserve_dispatch(conn,CTX,f'dispatch-{i}',lane='foreground',request_limit=1,request_hash='a'*64,run_id=run)
        except CoordinationConflict as error:return str(error)
    results=race(db,reserve)
    assert sum(isinstance(r,dict) for r in results)==1 and 'budget_exhausted' in results
    receipt=next(r for r in results if isinstance(r,dict))
    race(db,lambda c,i:settle_dispatch(c,CTX,receipt['dispatch_id'],usage={'input_tokens':11}))
    with db.read() as conn:
        row=conn.execute('SELECT * FROM shiliu.assistant_model_budget_days').fetchone()
        assert row['requests_used']==1 and row['usage_json']=={'responses':1,'input_tokens':11}
    with pytest.raises(CoordinationConflict,match='dispatch_identity_mismatch'):
        with db.transaction() as conn:
            reserve_dispatch(conn,CTX,receipt['dispatch_id'],lane='foreground',request_limit=1,request_hash='b'*64,run_id=run)
    with db.transaction() as conn:
        conn.execute("INSERT INTO shiliu.model_dispatch_receipts (workspace_id,principal_id,dispatch_id,lane,budget_day,status,reserved_requests,created_at) VALUES (%s,%s,'legacy-unverifiable','foreground',%s,'unknown',0,clock_timestamp())",(CTX.workspace_id,CTX.user_id,receipt['budget_day']))
    with pytest.raises(CoordinationConflict,match='dispatch_input_identity_unverifiable'):
        with db.transaction() as conn:
            reserve_dispatch(conn,CTX,'legacy-unverifiable',lane='foreground',request_limit=1,request_hash='a'*64)
    with pytest.raises(CoordinationConflict,match='dispatch_identity_mismatch'):
        with db.transaction() as conn:
            reserve_dispatch(conn,CTX,receipt['dispatch_id'],lane='foreground',request_limit=1,request_hash='a'*64,run_id=None)
    with db.transaction() as conn:
        reserve_dispatch(conn,CTX,'unknown-call',lane='background',request_limit=1,request_hash='a'*64)
        settle_dispatch(conn,CTX,'unknown-call',usage=None)
    with db.read() as conn:
        assert conn.execute("SELECT status,usage FROM shiliu.model_dispatch_receipts WHERE dispatch_id='unknown-call'").fetchone()=={'status':'unknown','usage':None}


def test_replay_contracts_and_research_mismatch_audit_survives(coordinated):
    db,_,admin,run,task,_=coordinated
    with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as conn:
        from psycopg.rows import dict_row
        conn.row_factory=dict_row
        g=SyntheticGraph(conn)
        # These parents already exist from the fixture with deterministic IDs.
        g.rows['research_tasks']=conn.execute('SELECT * FROM shiliu.research_tasks').fetchone()
        receipt=g.ensure('research_command_receipts')
        memory_receipt=g.ensure('assistant_mutation_receipts')
        thread=conn.execute('SELECT thread_id,request_id FROM shiliu.assistant_runs WHERE id=%s',(run,)).fetchone()
    with db.transaction() as conn:
        replay=assistant_request_replay(conn,CTX,thread['thread_id'],thread['request_id'])
        assert replay['id']==run and replay['actions']=={
            'resume':False,'abandon':True,'terminated':False,'current':True,'reason':None}
        assert mutation_replay(conn,CTX,memory_receipt['operation_key'])['operation']==memory_receipt['operation']
        result=research_command_replay(conn,CTX,task,receipt['command_id'],'changed-hash')
    with pytest.raises(CoordinationConflict,match='command_payload_mismatch'):result.raise_after_commit()
    with db.read() as conn:
        assert conn.execute("SELECT count(*) AS n FROM shiliu.research_events WHERE event_type='command_payload_mismatch_rejected'").fetchone()['n']==1
    with pytest.raises(CoordinationConflict,match='expected_epoch_required'):
        with db.transaction() as conn:guard_tool_operation(conn,CTX,run,None)


def _replay_rows(conn):
    from psycopg import sql
    # Compare full stored payloads, not only counts: a changed save binding or
    # message would violate replay even if no additional row was inserted.
    return {table:conn.execute(sql.SQL('SELECT to_jsonb(t) AS row FROM shiliu.{} t ORDER BY to_jsonb(t)::text')
                               .format(sql.Identifier(table))).fetchall()
            for table in ('assistant_threads','assistant_runs','assistant_messages','assistant_run_events',
                          'assistant_tool_calls','assistant_mutation_receipts')}


@pytest.mark.parametrize('status,code,counters,resume,abandon,terminated,current',[
    ('queued',None,{},False,True,False,True),
    ('running',None,{},False,True,False,True),
    ('completed',None,{},False,False,False,False),
    ('cancelled',None,{},False,False,True,False),
    ('interrupted','process_interrupted',{},True,True,False,True),
    ('budget_exhausted','tool_budget_exhausted',{},True,True,False,True),
    ('budget_exhausted','context_budget_exceeded',{'context_recovery_attempts':0},True,True,False,True),
    ('budget_exhausted','context_budget_exceeded',{'context_recovery_attempts':1},False,True,False,True),
    ('failed','provider_error',{},False,True,False,True),
    ('failed','context_compaction_failed',{'compaction_retries':0},True,True,False,True),
    ('failed','context_compaction_failed',{'compaction_retries':1},False,True,False,True),
])
def test_assistant_replay_current_actions_and_native_dto(coordinated,status,code,counters,resume,abandon,terminated,current):
    db,_,_,run,_,_=coordinated
    state={**counters,'knowledge_save':{'request_key':'original-key','answer_message_id':'original-answer'},
           'unknown_historical_field':{'ordered':[3,1,2],'null':None}}
    with db.transaction() as conn:
        conn.execute('UPDATE shiliu.assistant_runs SET status=%s,last_error_code=%s,cancel_requested=%s,working_state_json=%s,usage_json=%s WHERE id=%s',
                     (status,code,status=='cancelled',Jsonb(state),Jsonb({'input_tokens':7}),run))
        stored=conn.execute('SELECT * FROM shiliu.assistant_runs WHERE id=%s',(run,)).fetchone()
        insert(conn,'assistant_messages',{'workspace_id':CTX.workspace_id,'id':'original-user-message',
               'thread_id':stored['thread_id'],'run_id':run,'seq':1,'role':'user','content':'original accepted input',
               'provider_payload_json':{},'created_at':NOW})
        append_run_event(conn,CTX,run,'run_queued',{'message_id':'original-user-message'})
        if status!='queued':
            insert(conn,'assistant_tool_calls',{'workspace_id':CTX.workspace_id,'id':'original-tool-call','run_id':run,
                   'ordinal':1,'call_id':'original-call','name':'collection_search','args_json':{'query':'synthetic'},
                   'status':'completed','result_json':{'status':'ok','items':[]},'operation_key':'original-tool-key',
                   'created_at':NOW,'completed_at':NOW})
    with db.transaction() as conn:
        before=_replay_rows(conn)
        replay=assistant_request_replay(conn,CTX,stored['thread_id'],stored['request_id'])
        assert replay['actions']=={'resume':resume,'abandon':abandon,'terminated':terminated,'current':current,'reason':code}
        assert replay['working_state']==state and replay['usage']=={'input_tokens':7}
        assert 'working_state_json' not in replay and 'usage_json' not in replay
        assert type(replay['cancel_requested']) is bool
        assert replay['created_at']==stored['created_at'].astimezone(timezone.utc).isoformat(timespec='seconds')
        assert assistant_request_replay(conn,CTX,stored['thread_id'],stored['request_id'])==replay
        assert assistant_request_replay(conn,CTX,stored['thread_id'],'not-an-existing-request') is None
        assert _replay_rows(conn)==before
    with db.read() as conn:assert _replay_rows(conn)==before


@pytest.mark.parametrize('later_status,later_current',[('queued',True),('running',True),('completed',False),
                                                     ('cancelled',False),('budget_exhausted',True)])
def test_assistant_replay_superseded_and_real_insertion_order(coordinated,later_status,later_current):
    db,_,_,run,_,_=coordinated
    with db.transaction() as conn:
        # Existing read-side legacy history from test_assistant_upgrade_a:
        # an old budget pause can coexist with a later Run. This does not
        # assert that current create_run admission allows that combination.
        conn.execute("UPDATE shiliu.assistant_runs SET status='budget_exhausted',last_error_code='tool_budget_exhausted',insertion_seq=20 WHERE id=%s",(run,))
        original=conn.execute('SELECT * FROM shiliu.assistant_runs WHERE id=%s',(run,)).fetchone()
        first=assistant_request_replay(conn,CTX,original['thread_id'],original['request_id'])
        assert first['actions']=={'resume':True,'abandon':True,'terminated':False,'current':True,'reason':'tool_budget_exhausted'}
        # Opposite lexical ID order, identical times and an insertion_seq gap.
        # A terminal latest Run must not revive an earlier recoverable Run.
        later=dict(original,id='aaa_later_run',request_id='later-request',insertion_seq=90,status=later_status,
                   cancel_requested=later_status=='cancelled',last_error_code=None,
                   working_state_json={'context_recovery_attempts':0})
        insert(conn,'assistant_runs',later)
        before=_replay_rows(conn)
        old=assistant_request_replay(conn,CTX,original['thread_id'],original['request_id'])
        assert old['actions']=={'resume':False,'abandon':False,'terminated':False,'current':False,'reason':'run_superseded'}
        current=assistant_request_replay(conn,CTX,later['thread_id'],later['request_id'])
        assert current['actions']=={'resume':later_status=='budget_exhausted','abandon':later_current,
                                   'terminated':later_status=='cancelled','current':later_current,'reason':None}
        assert _replay_rows(conn)==before
        # A different thread's newer active Run is irrelevant to this thread.
        thread=conn.execute('SELECT * FROM shiliu.assistant_threads WHERE id=%s',(original['thread_id'],)).fetchone()
        insert(conn,'assistant_threads',dict(thread,id='other-thread'))
        insert(conn,'assistant_runs',dict(later,id='other-thread-run',thread_id='other-thread',request_id='other-request',insertion_seq=200,status='running',cancel_requested=False))
        assert assistant_request_replay(conn,CTX,original['thread_id'],original['request_id'])==old
        assert assistant_request_replay(conn,CTX,later['thread_id'],later['request_id'])==current
        after_setup=_replay_rows(conn)
        wrong_context=replace(CTX,user_id='not-the-owner')
        with pytest.raises(CoordinationConflict,match='thread_owner_mismatch'):
            assistant_request_replay(conn,wrong_context,original['thread_id'],original['request_id'])
        assert _replay_rows(conn)==after_setup
        assert len(before['assistant_runs'])==2
    with db.read() as conn:assert _replay_rows(conn)==after_setup


def test_task_takeover_reserved_rebind_unknown_preserved_and_clock_is_not_transaction_start(coordinated):
    db,_,admin,_,task,_=coordinated
    with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as conn:
        from psycopg.rows import dict_row
        conn.row_factory=dict_row
        g=SyntheticGraph(conn)
        for name in ('research_tasks','research_goals','research_attempts'):
            g.rows[name]=conn.execute('SELECT * FROM shiliu.'+name).fetchone()
        effect=g.ensure('research_side_effects')
        insert(conn,'research_side_effects',dict(effect,side_effect_id='unknown-effect',idempotency_key='unknown-key',status='unknown'))
    with db.transaction() as conn:
        first=claim_task_root(conn,CTX,task,'ownerA',lease_seconds=.02)
    with db.transaction() as conn:
        conn.execute('SELECT pg_sleep(.04)')
        with pytest.raises(CoordinationConflict,match='task_fenced'):
            guard_task_owner(conn,CTX,task,'ownerA',first['owner_epoch'])
    with db.transaction() as conn:
        second=claim_task_root(conn,CTX,task,'ownerB')
        assert second['owner_epoch']==first['owner_epoch']+1
        effects={r['side_effect_id']:r for r in conn.execute('SELECT * FROM shiliu.research_side_effects')}
        assert effects[effect['side_effect_id']]['owner_epoch']==second['owner_epoch']
        assert effects['unknown-effect']['status']=='unknown' and effects['unknown-effect']['owner_epoch']==effect['owner_epoch']
        with pytest.raises(CoordinationConflict):guard_task_owner(conn,CTX,task,'ownerA',first['owner_epoch'])
        assert research_effect_replay(conn,CTX,task,effect['effect_kind'],effect['idempotency_key'],effect['request_hash'])
        with pytest.raises(CoordinationConflict,match='effect_payload_mismatch'):
            research_effect_replay(conn,CTX,task,effect['effect_kind'],effect['idempotency_key'],'different')


def test_job_stage_heartbeat_recovery_and_activity_budget_gates(coordinated):
    db,_,admin,_,_,job=coordinated
    with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as conn:
        conn.execute("UPDATE shiliu.assistant_jobs SET kind='memory_extract' WHERE id=%s",(job,))
    with db.transaction() as conn:
        assert claim_job(conn,CTX,'blocked',activity_allowed=False) is None
        assert claim_job(conn,CTX,'blocked',budget_allowed=False) is None
        claimed=claim_job(conn,CTX,'worker')
        job_transition(conn,CTX,job,'worker',claimed['lease_epoch'],action='stage',proposal={'version':1})
        job_transition(conn,CTX,job,'worker',claimed['lease_epoch'],action='heartbeat')
    with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as conn:
        conn.execute("UPDATE shiliu.assistant_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",(job,))
    with db.transaction() as conn:
        assert recover_job(conn,CTX,job,disposition='staged')
        recovered=claim_job(conn,CTX,'new')
        assert recovered['proposal_json']=={'version':1} and recovered['attempt']==2 and recovered['lease_epoch']==2
    with pytest.raises(CoordinationConflict):
        with db.transaction() as conn:job_transition(conn,CTX,job,'worker',1,action='stage',proposal={'stale':True})


def test_proposal_receipt_matching_and_unknown_settlement_not_zero(coordinated):
    db,_,admin,_,_,_=coordinated
    with db.transaction() as conn:
        conn.execute("INSERT INTO shiliu.assistant_mutation_receipts "
            "(workspace_id,principal_id,operation_key,operation,result_json,created_at) "
            "VALUES (%s,%s,'key','decide_proposal','{\"proposal_id\":\"p1\"}',clock_timestamp())",(CTX.workspace_id,CTX.user_id))
        assert mutation_replay(conn,CTX,'key',proposal_id='p1')
        with pytest.raises(CoordinationConflict,match='proposal_id_mismatch'):mutation_replay(conn,CTX,'key',proposal_id='p2')
        reserve_dispatch(conn,CTX,'uncertain',lane='background',request_limit=1,request_hash='a'*64)
        settle_dispatch(conn,CTX,'uncertain',usage=None)
    with db.transaction() as conn:settle_dispatch(conn,CTX,'uncertain',usage=None)
    with db.read() as conn:
        assert conn.execute("SELECT requests_used,usage_json FROM shiliu.assistant_model_budget_days WHERE lane='background'").fetchone()=={'requests_used':1,'usage_json':{'responses':1,'unknown_responses':1}}


def test_claim_receipt_single_winner_and_retry_limit_not_reset(coordinated):
    from shiliu.storage.receipts import record_research_command
    db,_,admin,_,task,job=coordinated
    def claim(conn,i):
        row=claim_task_root(conn,CTX,task,f'worker-{i}')
        if row:
            return record_research_command(conn,CTX,task,'claim-key','fixed-input',command_type='claim',
                                           owner_epoch=row['owner_epoch'],response={'claimed':True}).row
        return None
    results=race(db,claim)
    assert sum(r is not None for r in results)==1
    with db.read() as conn:
        assert conn.execute("SELECT count(*) AS n FROM shiliu.research_command_receipts WHERE command_id='claim-key'").fetchone()['n']==1
    with db.transaction() as conn:claimed=claim_job(conn,CTX,'worker',allow_model_jobs=False)
    with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as conn:
        conn.execute("UPDATE shiliu.assistant_jobs SET attempt=3,lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",(job,))
    with db.transaction() as conn:
        assert recover_job(conn,CTX,job,disposition='replay_safe')
        assert claim_job(conn,CTX,'worker',allow_model_jobs=False) is None
        row=conn.execute('SELECT attempt,status FROM shiliu.assistant_jobs WHERE id=%s',(job,)).fetchone()
        assert row=={'attempt':3,'status':'blocked'}


def test_job_defer_backoff_hold_and_no_unbounded_retry(coordinated):
    db,_,admin,_,_,job=coordinated
    with db.transaction() as conn:
        first=claim_job(conn,CTX,'worker',allow_model_jobs=False)
        job_transition(conn,CTX,job,'worker',first['lease_epoch'],action='defer')
        second=claim_job(conn,CTX,'worker',allow_model_jobs=False)
        assert second['attempt']==1 and second['lease_epoch']==2
        job_transition(conn,CTX,job,'worker',second['lease_epoch'],action='fail')
        row=conn.execute('SELECT status,not_before>clock_timestamp() AS delayed FROM shiliu.assistant_jobs WHERE id=%s',(job,)).fetchone()
        assert row=={'status':'retry_wait','delayed':True}
        assert claim_job(conn,CTX,'worker',allow_model_jobs=False) is None
    with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as conn:
        conn.execute("UPDATE shiliu.assistant_jobs SET status='running',lease_owner='worker',lease_until=clock_timestamp()+interval '60 seconds',attempt=3 WHERE id=%s",(job,))
    with db.transaction() as conn:
        job_transition(conn,CTX,job,'worker',second['lease_epoch'],action='fail')
        assert conn.execute('SELECT status FROM shiliu.assistant_jobs WHERE id=%s',(job,)).fetchone()['status']=='blocked'
    with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as conn:
        from psycopg.rows import dict_row
        conn.row_factory=dict_row
        graph=SyntheticGraph(conn)
        graph.rows['assistant_jobs']=conn.execute('SELECT * FROM shiliu.assistant_jobs WHERE id=%s',(job,)).fetchone()
        graph.ensure('videos')
        graph.ensure('metadata_backfill_job_holds')
        conn.execute("UPDATE shiliu.assistant_jobs SET status='queued',attempt=0,not_before=clock_timestamp() WHERE id=%s",(job,))
    with db.transaction() as conn:
        assert claim_job(conn,CTX,'worker',allow_model_jobs=False) is None
