"""Small transaction-local lock/fence primitives; no connections or commits here."""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from psycopg import Connection
from psycopg.types.json import Jsonb

from shiliu.storage.scope import ResourceContext


class CoordinationConflict(RuntimeError):
    pass


def lock_workspace(conn: Connection, context: ResourceContext):
    row=conn.execute('SELECT * FROM shiliu.workspace_guards WHERE workspace_id=%s FOR UPDATE',
                     (context.workspace_id,)).fetchone()
    if row is None:raise CoordinationConflict('workspace_missing')
    return row


def lock_thread_run(conn: Connection, context: ResourceContext, run_id: str):
    root=conn.execute('SELECT thread_id FROM shiliu.assistant_runs WHERE workspace_id=%s AND id=%s',
                      (context.workspace_id,run_id)).fetchone()
    if root is None:raise CoordinationConflict('run_missing')
    thread=conn.execute('SELECT id FROM shiliu.assistant_threads WHERE workspace_id=%s AND principal_id=%s '
                       'AND id=%s FOR UPDATE',(context.workspace_id,context.user_id,root['thread_id'])).fetchone()
    if thread is None:raise CoordinationConflict('run_owner_mismatch')
    run=conn.execute('SELECT * FROM shiliu.assistant_runs WHERE workspace_id=%s AND thread_id=%s '
                    'AND id=%s FOR UPDATE',(context.workspace_id,root['thread_id'],run_id)).fetchone()
    if run is None:raise CoordinationConflict('run_root_changed')
    return run


def guard_tool_operation(conn: Connection, context: ResourceContext, run_id: str, expected_epoch: int):
    if type(expected_epoch) is not int or expected_epoch<1:
        raise CoordinationConflict('expected_epoch_required')
    run=lock_thread_run(conn,context,run_id)
    state=run['working_state_json']
    if (not isinstance(state,dict) or run['run_epoch']!=expected_epoch
            or run['status']!='running' or run['cancel_requested'] or state.get('finish_requested')):
        raise CoordinationConflict('run_fenced')
    # No execution_budget presence condition; even legacy runs must be fenced.
    # AssistantRunStore.initialize_execution_budget creates an ISO, zoned
    # deadline in this nested object. Only absence denotes an unbudgeted run;
    # malformed/present budgets cannot silently grant unlimited authorization.
    if 'execution_budget' in state:
        budget=state['execution_budget']
        try:
            if not isinstance(budget,dict) or budget.get('final_dispatched'):
                raise ValueError('invalid_or_final_budget')
            deadline=datetime.fromisoformat(budget['deadline_at'].replace('Z','+00:00'))
            if deadline.tzinfo is None or deadline.utcoffset() is None:
                raise ValueError('unzoned_deadline')
        except (KeyError,TypeError,ValueError,AttributeError):
            raise CoordinationConflict('run_fenced') from None
        # Evaluate after both locks, using actual time even in a long transaction.
        if not conn.execute('SELECT %s::timestamptz > clock_timestamp() AS valid',
                            (deadline,)).fetchone()['valid']:
            raise CoordinationConflict('run_fenced')
    return run


def append_run_event(conn: Connection, context: ResourceContext, run_id: str, event_type: str, payload: dict):
    # All writers lock thread -> run before allocating MAX+1. The unique key is a
    # last defense, never the sole serialization mechanism.
    lock_thread_run(conn,context,run_id)
    seq=conn.execute('SELECT coalesce(max(seq),0)+1 AS seq FROM shiliu.assistant_run_events '
                     'WHERE workspace_id=%s AND run_id=%s',(context.workspace_id,run_id)).fetchone()['seq']
    conn.execute('INSERT INTO shiliu.assistant_run_events '
                 '(workspace_id,run_id,seq,event_type,payload_json,created_at) '
                 'VALUES (%s,%s,%s,%s,%s,clock_timestamp())',
                 (context.workspace_id,run_id,seq,event_type,Jsonb(payload)))
    return seq


def cancel_run(conn: Connection, context: ResourceContext, run_id: str):
    run=lock_thread_run(conn,context,run_id)
    if run['status'] in {'queued','running','interrupted','budget_exhausted','failed'}:
        conn.execute("UPDATE shiliu.assistant_runs SET cancel_requested=true,run_epoch=run_epoch+1,"
                     "status='cancelled',updated_at=clock_timestamp(),completed_at=clock_timestamp() WHERE id=%s",(run_id,))
        append_run_event(conn,context,run_id,'run_cancelled',{'reason':'user_abandoned'})
    return conn.execute('SELECT * FROM shiliu.assistant_runs WHERE id=%s',(run_id,)).fetchone()


def guard_task_owner(conn: Connection, context: ResourceContext, task_id: str, owner: str, epoch: int):
    row=conn.execute('SELECT * FROM shiliu.research_tasks '
                     'WHERE workspace_id=%s AND owner_user_id=%s AND task_id=%s FOR UPDATE',
                     (context.workspace_id,context.user_id,task_id)).fetchone()
    if row is None or row['status']!='running' or row['owner_id']!=owner or row['owner_epoch']!=epoch or not _task_lease_valid(conn,row):
        raise CoordinationConflict('task_fenced')
    return row


def _task_lease_valid(conn: Connection, row):
    # LockRows may wait after SELECT target expressions were evaluated. A new
    # statement after acquiring the row lock must observe the database clock.
    return bool(conn.execute('SELECT %s::timestamptz>clock_timestamp() AS valid',
                             (row['lease_until'],)).fetchone()['valid'])


def append_task_event(conn: Connection, context: ResourceContext, task_id: str, event_type: str,
                      payload: dict, *, command_id: str | None = None):
    task=conn.execute('SELECT owner_epoch FROM shiliu.research_tasks WHERE workspace_id=%s '
                      'AND owner_user_id=%s AND task_id=%s FOR UPDATE',
                      (context.workspace_id,context.user_id,task_id)).fetchone()
    if task is None:raise CoordinationConflict('task_missing')
    seq=conn.execute('SELECT coalesce(max(sequence),0)+1 AS seq FROM shiliu.research_events '
                     'WHERE workspace_id=%s AND task_id=%s',(context.workspace_id,task_id)).fetchone()['seq']
    conn.execute('INSERT INTO shiliu.research_events (event_id,workspace_id,task_id,sequence,event_type,'
                 'payload_json,command_id,owner_epoch,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp())',
                 ('evt_'+uuid4().hex,context.workspace_id,task_id,seq,event_type,Jsonb(payload),command_id,task['owner_epoch']))


def claim_task_root(conn: Connection, context: ResourceContext, task_id: str, owner: str, *, lease_seconds: float=60):
    """Root lease claim + existing attempt/reserved-effect rebind, same transaction.

    Goal/attempt creation and checkpoint/result installation stay in W12. This
    primitive never resurrects terminal tasks or replays dispatched/unknown work.
    """
    if not owner or not 0<lease_seconds<=60:raise ValueError('invalid_task_lease')
    row=conn.execute('SELECT * FROM shiliu.research_tasks '
                     'WHERE workspace_id=%s AND owner_user_id=%s AND task_id=%s FOR UPDATE',
                     (context.workspace_id,context.user_id,task_id)).fetchone()
    if row is None or row['status'] not in {'ready','running'}:return None
    if row['status']=='running' and _task_lease_valid(conn,row):return None
    updated=conn.execute("UPDATE shiliu.research_tasks SET status='running',owner_id=%s,owner_epoch=owner_epoch+1,"
                         "state_version=state_version+1,lease_until=clock_timestamp()+%s*interval '1 second',"
                         'updated_at=clock_timestamp() WHERE task_id=%s AND state_version=%s RETURNING *',
                         (owner,lease_seconds,task_id,row['state_version'])).fetchone()
    if updated is None:raise CoordinationConflict('task_cas_failed')
    conn.execute("UPDATE shiliu.research_attempts SET owner_epoch=%s,status='running' WHERE task_id=%s "
                 "AND status IN ('pending','running')",(updated['owner_epoch'],task_id))
    conn.execute("UPDATE shiliu.research_side_effects SET owner_epoch=%s,updated_at=clock_timestamp() "
                 "WHERE task_id=%s AND status='reserved'",(updated['owner_epoch'],task_id))
    append_task_event(conn,context,task_id,'owner_claimed',{'owner_epoch':updated['owner_epoch']})
    return updated
