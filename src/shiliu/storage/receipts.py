"""Business-specific replay contracts; no universal receipt-key decorator."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from psycopg import Connection
from psycopg.types.json import Jsonb
from shiliu.storage.fences import CoordinationConflict,append_task_event
from shiliu.storage.scope import ResourceContext
from shiliu.storage.dto import assistant_run_dto


def assistant_request_replay(conn: Connection, context: ResourceContext, thread_id: str, request_id: str):
    """Call after input validation; lock/ownership validation precedes key replay.

    Return current Run + actions; deliberately no input/answer/receipt_only hash.
    New-run admission/creation stays in W10 under this same locked thread.
    """
    root=conn.execute('SELECT id FROM shiliu.assistant_threads WHERE workspace_id=%s AND principal_id=%s '
                      'AND id=%s FOR UPDATE',(context.workspace_id,context.user_id,thread_id)).fetchone()
    if root is None:raise CoordinationConflict('thread_owner_mismatch')
    row=conn.execute('SELECT * FROM shiliu.assistant_runs WHERE workspace_id=%s AND thread_id=%s AND request_id=%s',
                     (context.workspace_id,thread_id,request_id)).fetchone()
    if row is not None:
        # Match _current_action_run_id: newest active Run takes precedence;
        # otherwise only the last inserted Run can offer recovery actions.
        latest=conn.execute("SELECT id,status FROM shiliu.assistant_runs WHERE workspace_id=%s AND thread_id=%s "
                            "ORDER BY (status IN ('queued','running')) DESC,insertion_seq DESC LIMIT 1",
                            (context.workspace_id,thread_id)).fetchone()
        current_id=latest['id'] if latest['status'] in {'queued','running','interrupted','budget_exhausted','failed'} else None
        return assistant_run_dto(row,current=row['id']==current_id)
    return row


def mutation_replay(conn: Connection, context: ResourceContext, operation_key: str, *, proposal_id: str | None=None):
    # Serialize the original principal/operation_key domain. operation is not a
    # dedup dimension. Caller has already locked guard/run/page as appropriate.
    row=conn.execute('SELECT * FROM shiliu.assistant_mutation_receipts WHERE workspace_id=%s '
                     'AND principal_id=%s AND operation_key=%s',(context.workspace_id,context.user_id,operation_key)).fetchone()
    if row is not None and proposal_id is not None and row['result_json'].get('proposal_id')!=proposal_id:
        raise CoordinationConflict('proposal_id_mismatch')
    return row


@dataclass(frozen=True)
class CommandReplay:
    row: dict[str,Any] | None
    mismatch: bool=False

    def raise_after_commit(self):
        """Must run outside the transaction to preserve the mismatch audit."""
        if self.mismatch:raise CoordinationConflict('command_payload_mismatch')
        return self.row


def research_command_replay(conn: Connection, context: ResourceContext, task_id: str,
                            command_id: str, payload_hash: str) -> CommandReplay:
    task=conn.execute('SELECT task_id FROM shiliu.research_tasks WHERE workspace_id=%s AND owner_user_id=%s '
                      'AND task_id=%s FOR UPDATE',(context.workspace_id,context.user_id,task_id)).fetchone()
    if task is None:raise CoordinationConflict('task_owner_mismatch')
    row=conn.execute('SELECT * FROM shiliu.research_command_receipts WHERE workspace_id=%s AND task_id=%s AND command_id=%s',
                     (context.workspace_id,task_id,command_id)).fetchone()
    mismatch=row is not None and row['payload_hash']!=payload_hash
    if mismatch:
        append_task_event(conn,context,task_id,'command_payload_mismatch_rejected',{'command_id':command_id,'stored_payload_hash':row['payload_hash'],'received_payload_hash':payload_hash},command_id=command_id)
    return CommandReplay(row,mismatch)


def research_effect_replay(conn: Connection, context: ResourceContext, task_id: str,
                           effect_kind: str,idempotency_key: str,request_hash: str):
    task=conn.execute('SELECT task_id FROM shiliu.research_tasks WHERE workspace_id=%s AND owner_user_id=%s '
                      'AND task_id=%s FOR UPDATE',(context.workspace_id,context.user_id,task_id)).fetchone()
    if task is None:raise CoordinationConflict('task_owner_mismatch')
    row=conn.execute('SELECT * FROM shiliu.research_side_effects WHERE workspace_id=%s AND task_id=%s '
                     'AND effect_kind=%s AND idempotency_key=%s',(context.workspace_id,task_id,effect_kind,idempotency_key)).fetchone()
    if row is not None and row['request_hash']!=request_hash:
        # Source effect mismatch has no extra mismatch audit. Do not invent one.
        raise CoordinationConflict('effect_payload_mismatch')
    return row


def record_research_command(conn: Connection, context: ResourceContext, task_id: str, command_id: str,
                            payload_hash: str, *, command_type: str, owner_epoch: int, response: dict) -> CommandReplay:
    """Record result in the caller's task-locked transaction, or same-hash replay.

    A mismatch returns the same explicit post-commit decision as replay lookup;
    it must not be raised inside a generic rollback context. Domain owner fences
    and object validations run before this function where required.
    """
    result=research_command_replay(conn,context,task_id,command_id,payload_hash)
    if result.row is not None:return result
    conn.execute("INSERT INTO shiliu.research_command_receipts (receipt_id,workspace_id,task_id,command_id,"
                 "command_type,payload_hash,status,response_json,owner_epoch,created_at,completed_at) "
                 "VALUES (%s,%s,%s,%s,%s,%s,'committed',%s,%s,clock_timestamp(),clock_timestamp())",
                 ('receipt_'+__import__('uuid').uuid4().hex,context.workspace_id,task_id,command_id,command_type,payload_hash,Jsonb(response),owner_epoch))
    return research_command_replay(conn,context,task_id,command_id,payload_hash)
