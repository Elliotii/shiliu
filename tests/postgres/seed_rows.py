"""Synthetic relational fixtures only: no application, providers, or user data."""
from datetime import datetime,timezone,date
import json
from pathlib import Path
import re

from psycopg import sql
from psycopg.types.json import Jsonb

MAPPING=json.loads(Path('migrations/contracts/schema26_target.json').read_text())
WORKSPACE='personal:local_operator'
NOW=datetime(2026,10,23,tzinfo=timezone.utc)


def insert(conn,table,row):
    columns=list(row)
    adapted=[Jsonb(row[k]) if MAPPING['tables'][table]['columns'][k]['type']=='jsonb' and row[k] is not None else row[k] for k in columns]
    conn.execute(sql.SQL('INSERT INTO shiliu.{} ({}) VALUES ({})').format(
        sql.Identifier(table),sql.SQL(',').join(map(sql.Identifier,columns)),sql.SQL(',').join(sql.Placeholder() for _ in columns)),adapted)


class SyntheticGraph:
    """Deterministic complete parent closure for catalog/trigger negative tests.

    Values come from the committed target contract, not production snapshots.
    W04 has a separately authored semantic PoC with different states/versions.
    """
    def __init__(self,conn,*,workspace=WORKSPACE,user='local_operator',suffix='',numeric_id=1,overrides=None):
        self.workspace=workspace;self.user=user;self.suffix=suffix;self.numeric_id=numeric_id
        self.conn=conn
        self.overrides=overrides or {}
        self.rows={'users':{'id':user},'workspaces':{'id':workspace,'owner_user_id':user},
                   'workspace_guards':{'workspace_id':workspace}}
        self.visiting=set()

    def ensure(self,name):
        if name in self.rows:return self.rows[name]
        if name in self.visiting:raise RuntimeError('Required fixture cycle: '+name)
        self.visiting.add(name)
        target=MAPPING['tables'][name]
        row={}
        for key,c in target['columns'].items():
            if c['nullable']:row[key]=None;continue
            typ=c['type']
            if key=='workspace_id':value=self.workspace
            elif key in {'principal_id','owner_user_id'}:value=self.user
            elif typ in {'bigint','integer'}:value=self.numeric_id
            elif typ=='boolean':value=False
            elif typ=='double precision':value=1.
            elif typ=='timestamptz':value=NOW
            elif typ=='date':value=date(2026,10,23)
            elif typ=='jsonb':value=[] if key in {'source_ids_json','video_ids_json','source_message_ids_json','source_run_ids_json'} else {}
            elif typ=='tsvector':value=''
            elif typ.startswith('shiliu.vector'):value='['+','.join(['1']+['0']*511)+']'
            else:
                value=name+'_'+key+self.suffix
                for check in target['checks']:
                    match=re.search(r'\b'+key+r"\s*(?:=\s*|IN\s*\(\s*)'([^']+)'",check)
                    if match:value=match[1];break
            row[key]=value
        row.update(self.overrides.get(name,{}))
        for f in target['foreign_keys']:
            if any(row[c] is None for c in f['columns']):continue
            if f['table']==name:continue
            parent=self.ensure(f['table'])
            for c,r in zip(f['columns'],f['references']):row[c]=parent[r]
        if name=='research_task_derivations':
            source=self.ensure('research_tasks');goal=self.ensure('research_goals');attempt=self.ensure('research_attempts');checkpoint=self.ensure('research_checkpoints')
            child=dict(source,task_id='synthetic_child'+self.suffix,parent_task_id=source['task_id'],active_goal_id=None,terminal_result_id=None,status='ready')
            insert(self.conn,'research_tasks',child)
            child_goal=dict(goal,goal_id='synthetic_child_goal'+self.suffix,task_id=child['task_id'],parent_goal_id=None,created_by_event_id=None,revision=1)
            insert(self.conn,'research_goals',child_goal)
            child_attempt=dict(attempt,attempt_id='synthetic_child_attempt'+self.suffix,task_id=child['task_id'],goal_id=child_goal['goal_id'],parent_attempt_id=None,source_checkpoint_id=None,result_id=None,status='pending',ordinal=1)
            insert(self.conn,'research_attempts',child_attempt)
            row.update(workspace_id=self.workspace,source_task_id=source['task_id'],source_goal_id=goal['goal_id'],source_attempt_id=attempt['attempt_id'],source_checkpoint_id=checkpoint['checkpoint_id'],child_task_id=child['task_id'],child_goal_id=child_goal['goal_id'],child_attempt_id=child_attempt['attempt_id'])
        if name=='research_events':row['event_type']='candidate_deltas_materialized'
        if name=='assistant_memories':row.update(scope_kind='user',scope_id='',scope_space_id=None)
        if name=='assistant_memory_suppressions':row.update(scope_kind='user',scope_id='')
        if name=='knowledge_draft_revisions':
            parent=self.ensure('ask_runs');row.update(origin_kind='fast',ask_run_id=parent['run_id'],research_task_id=None,version=1)
        if name=='research_side_effect_resolutions':row.update(receipt_hash='synthetic_hash',result_reference='synthetic_result')
        if name=='retrieval_units':row.update(unit_type='video',chunk_id=None,start_time=None,end_time=None)
        if name=='artifact_objects':row.update(sha256='a'*64,relative_key=WORKSPACE+'/objects/'+'a'*64)
        if name=='embedding_profiles':row.update(dimension=512,max_tokens=512,dtype='float32',normalized=True)
        insert(self.conn,name,row)
        self.rows[name]=row
        self.visiting.remove(name)
        return row
