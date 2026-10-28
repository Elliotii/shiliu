"""Atomic dispatch reservation/settlement, distinct from legacy aggregate usage."""
from __future__ import annotations
from datetime import date
import math
import re
from psycopg import Connection
from psycopg.types.json import Jsonb
from shiliu.storage.fences import CoordinationConflict
from shiliu.storage.scope import ResourceContext


def _day(conn,context,day,lane):
    return conn.execute('SELECT * FROM shiliu.assistant_model_budget_days WHERE workspace_id=%s AND principal_id=%s '
                        'AND budget_date=%s AND lane=%s FOR UPDATE',
                        (context.workspace_id,context.user_id,day,lane)).fetchone()


def _same_binding(receipt,*,day,lane,requests,run_id,job_id,request_hash):
    if receipt['request_hash'] is None:raise CoordinationConflict('dispatch_input_identity_unverifiable')
    if (receipt['budget_day'],receipt['lane'],receipt['reserved_requests'],receipt['run_id'],receipt['job_id'],receipt['request_hash'])!=(day,lane,requests,run_id,job_id,request_hash):
        raise CoordinationConflict('dispatch_identity_mismatch')


def reserve_dispatch(conn: Connection, context: ResourceContext, dispatch_id: str, *, lane: str,
                     request_limit: int, request_hash: str, requests: int=1, run_id: str | None=None, job_id: str | None=None,
                     day: date | None=None):
    if not isinstance(request_hash,str) or not re.fullmatch(r'[0-9a-f]{64}',request_hash):raise ValueError('explicit_dispatch_request_hash_required')
    if lane not in {'foreground','background'} or type(requests) is not int or requests<1 or type(request_limit) is not int or request_limit<1:
        raise ValueError('invalid_budget_reservation')
    day=day or conn.execute("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date AS day").fetchone()['day']
    conn.execute('INSERT INTO shiliu.assistant_model_budget_days '
                 '(workspace_id,principal_id,budget_date,lane,request_limit,updated_at) VALUES (%s,%s,%s,%s,%s,clock_timestamp()) '
                 'ON CONFLICT DO NOTHING',(context.workspace_id,context.user_id,day,lane,request_limit))
    budget=_day(conn,context,day,lane)
    if budget['request_limit']!=request_limit:raise CoordinationConflict('budget_policy_mismatch')
    old=conn.execute('SELECT * FROM shiliu.model_dispatch_receipts WHERE workspace_id=%s AND principal_id=%s AND dispatch_id=%s',
                     (context.workspace_id,context.user_id,dispatch_id)).fetchone()
    if old:
        _same_binding(old,day=day,lane=lane,requests=requests,run_id=run_id,job_id=job_id,request_hash=request_hash)
        return old
    if budget['requests_used']+requests>request_limit:raise CoordinationConflict('budget_exhausted')
    conn.execute("INSERT INTO shiliu.model_dispatch_receipts (workspace_id,principal_id,dispatch_id,run_id,job_id,lane,"
        "budget_day,status,reserved_requests,request_hash,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,'reserved',%s,%s,clock_timestamp())",
        (context.workspace_id,context.user_id,dispatch_id,run_id,job_id,lane,day,requests,request_hash))
    conn.execute('UPDATE shiliu.assistant_model_budget_days SET requests_used=requests_used+%s,updated_at=clock_timestamp() '
                 'WHERE workspace_id=%s AND principal_id=%s AND budget_date=%s AND lane=%s',
                 (requests,context.workspace_id,context.user_id,day,lane))
    return conn.execute('SELECT * FROM shiliu.model_dispatch_receipts WHERE workspace_id=%s AND principal_id=%s AND dispatch_id=%s',
                        (context.workspace_id,context.user_id,dispatch_id)).fetchone()


def settle_dispatch(conn: Connection, context: ResourceContext, dispatch_id: str, *, usage: dict | None):
    if usage is not None:
        for value in usage.values():
            if isinstance(value,(int,float)) and not isinstance(value,bool) and not math.isfinite(value):
                raise ValueError('nonfinite_usage')
    row=conn.execute('SELECT * FROM shiliu.model_dispatch_receipts WHERE workspace_id=%s AND principal_id=%s AND dispatch_id=%s',
                     (context.workspace_id,context.user_id,dispatch_id)).fetchone()
    if row is None:raise CoordinationConflict('dispatch_not_reserved')
    budget=_day(conn,context,row['budget_day'],row['lane'])
    row=conn.execute('SELECT * FROM shiliu.model_dispatch_receipts WHERE workspace_id=%s AND principal_id=%s AND dispatch_id=%s FOR UPDATE',
                     (context.workspace_id,context.user_id,dispatch_id)).fetchone()
    if row['settled_at'] is not None:
        if row['usage']==usage:return row
        # A transport timeout may first be recorded as unknown and later return
        # an authoritative provider receipt. Upgrade that one receipt once;
        # never erase or fabricate cost, and keep the response count unchanged.
        if row['status']=='unknown' and row['usage'] is None and usage is not None:
            aggregate=dict(budget['usage_json'])
            aggregate['unknown_responses']=max(0,int(aggregate.get('unknown_responses',0))-1)
            for key,value in usage.items():
                if type(value) in {int,float}:aggregate[key]=aggregate.get(key,0)+value
            conn.execute('UPDATE shiliu.assistant_model_budget_days SET usage_json=%s,updated_at=clock_timestamp() '
                         'WHERE workspace_id=%s AND principal_id=%s AND budget_date=%s AND lane=%s',
                         (Jsonb(aggregate),context.workspace_id,context.user_id,row['budget_day'],row['lane']))
            return conn.execute("UPDATE shiliu.model_dispatch_receipts SET status='settled',usage=%s "
                                'WHERE workspace_id=%s AND principal_id=%s AND dispatch_id=%s RETURNING *',
                                (Jsonb(usage),context.workspace_id,context.user_id,dispatch_id)).fetchone()
        raise CoordinationConflict('dispatch_settlement_mismatch')
        return row
    aggregate=dict(budget['usage_json'])
    aggregate['responses']=int(aggregate.get('responses',0))+1
    if usage is None:aggregate['unknown_responses']=int(aggregate.get('unknown_responses',0))+1
    else:
        for key,value in usage.items():
            if type(value) in {int,float}:aggregate[key]=aggregate.get(key,0)+value
    conn.execute('UPDATE shiliu.assistant_model_budget_days SET usage_json=%s,updated_at=clock_timestamp() '
                 'WHERE workspace_id=%s AND principal_id=%s AND budget_date=%s AND lane=%s',
                 (Jsonb(aggregate),context.workspace_id,context.user_id,row['budget_day'],row['lane']))
    return conn.execute('UPDATE shiliu.model_dispatch_receipts SET status=%s,usage=%s,settled_at=clock_timestamp() '
        'WHERE workspace_id=%s AND principal_id=%s AND dispatch_id=%s RETURNING *',
        ('unknown' if usage is None else 'settled',None if usage is None else Jsonb(usage),context.workspace_id,context.user_id,dispatch_id)).fetchone()


def release_dispatch(conn: Connection, context: ResourceContext, dispatch_id: str):
    """Release only a reservation whose caller proves the provider was not sent."""
    row=conn.execute('SELECT * FROM shiliu.model_dispatch_receipts WHERE workspace_id=%s AND principal_id=%s AND dispatch_id=%s',
                     (context.workspace_id,context.user_id,dispatch_id)).fetchone()
    if row is None:raise CoordinationConflict('dispatch_not_reserved')
    budget=_day(conn,context,row['budget_day'],row['lane'])
    receipt=conn.execute('SELECT * FROM shiliu.model_dispatch_receipts WHERE workspace_id=%s AND principal_id=%s '
                         'AND dispatch_id=%s FOR UPDATE',(context.workspace_id,context.user_id,dispatch_id)).fetchone()
    if receipt['status']=='released':return receipt
    if receipt['status']!='reserved' or receipt['settled_at'] is not None:
        raise CoordinationConflict('dispatch_already_sent_or_settled')
    updated=conn.execute('UPDATE shiliu.assistant_model_budget_days SET requests_used=requests_used-%s,updated_at=clock_timestamp() '
                         'WHERE workspace_id=%s AND principal_id=%s AND budget_date=%s AND lane=%s AND requests_used>=%s',
                         (receipt['reserved_requests'],context.workspace_id,context.user_id,receipt['budget_day'],receipt['lane'],receipt['reserved_requests']))
    if updated.rowcount!=1:raise CoordinationConflict('budget_reservation_inconsistent')
    return conn.execute("UPDATE shiliu.model_dispatch_receipts SET status='released',settled_at=clock_timestamp() "
                        'WHERE workspace_id=%s AND principal_id=%s AND dispatch_id=%s RETURNING *',
                        (context.workspace_id,context.user_id,dispatch_id)).fetchone()
