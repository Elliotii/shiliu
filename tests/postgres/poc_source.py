"""Session-generated Schema26 SQLite + exact synthetic Artifact bytes (W04)."""
from __future__ import annotations
from shiliu.config import LIBPQ_DISABLED_PASSFILE
import os
from dataclasses import replace
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

import psycopg

from shiliu.config import load_postgres_config
from shiliu.migration.safety import TASK_ROOT
from shiliu.evidence.source import (source_version_for_bytes as source_version,make_source_artifact_id,make_segment_id,make_timeline_run_id)
from shiliu.evidence.contracts import SourceArtifactReference
from shiliu.assistant.snapshots import _json_hash
from schema_support import formal_target
from seed_rows import SyntheticGraph,WORKSPACE,NOW

# Parents of these semantic examples are recursively included, never fabricated
# as missing IDs by the importer. No Application or provider is instantiated.
EXAMPLES='''retrieval_unit_folders video_source_memberships video_notes pipeline_stages asr_jobs
ask_events ask_search_trace_links assistant_messages assistant_tool_calls assistant_run_events assistant_task_notes
assistant_source_cards assistant_source_card_batches assistant_memories assistant_memory_changes
assistant_memory_suppressions assistant_wiki_dependencies assistant_wiki_materials assistant_wiki_personal_dependencies
assistant_jobs assistant_mutation_receipts assistant_model_budget_days
research_checkpoints research_command_receipts research_side_effects research_execution_metadata
research_evidence_provenance research_evidence_validations research_provisional_artifacts
research_knowledge_candidates research_knowledge_review_decisions research_fact_evidence_links
research_artifact_fact_links research_topic_page_fact_links research_workspace_records'''.split()


def make_source():
    root=TASK_ROOT/'sources'/('w04_'+uuid.uuid4().hex[:12]);root.mkdir(parents=True,mode=0o700)
    root.chmod(0o700);(root/'files').mkdir(mode=0o700)
    (root/'synthetic.json').write_text(json.dumps({'task':'shiliu-w01-20261023','synthetic_only':True}))
    with formal_target(load_postgres_config()) as (_,admin):
        with psycopg.connect(admin.database_url,passfile=LIBPQ_DISABLED_PASSFILE) as conn:
            graph=SyntheticGraph(conn)
            for table in EXAMPLES:graph.ensure(table)
            dataset={name:[dict(row)] for name,row in graph.rows.items() if name not in {'users','workspaces','workspace_guards'}}
    video=dataset['videos'][0]
    video.update(title='合成收藏：数据库迁移',published_at=1792713662,discovered_at='2026-10-23T08:01:02+08:00')
    dataset['videos'] += [dict(video,id=2,source_id='synthetic_video_2',title='合成收藏：并发验证'),dict(video,id=3,source_id='synthetic_video_3',title='合成收藏：历史引用')]
    source=dataset['favorite_sources'][0]
    dataset['favorite_sources'].append(dict(source,id=2,folder_id=2,folder_title='合成第二来源'))
    member=dataset['video_source_memberships'][0]
    member.update(bvid=video['source_id'],favorite_time=1792713662,source_position=4)
    dataset['video_source_memberships'] += [dict(member,source_id=2,bvid='synthetic_video_2',video_id=2,source_position=1),dict(member,bvid='synthetic_removed',video_id=None,source_position=9)]
    run=dataset['assistant_runs'][0]
    run.update(status='completed',run_epoch=4,working_state_json={'legacy_context':{'format_version':1,'missing_new_field':None}})
    thread=dataset['assistant_threads'][0]
    thread['context_state_json']={'format_version':1,'frozen':{'messages':[{'role':'user','content':'合成原始原话'}]}}
    message=dataset['assistant_messages'][0]
    message.update(run_id=run['id'],seq=4,role='user',content='合成原始原话')
    dataset['assistant_messages'].append(dict(message,id='synthetic_answer_message',seq=9,role='assistant',content='合成历史答案'))
    dataset['assistant_task_notes'][0].update(task_segment=3,note_version=2,covered_until_message_seq=4,checkpoint_json={'old_context':True,'nullable':None},source_run_ids_json=[run['id']])
    memory=dataset['assistant_memories'][0]
    memory.update(text='保留合成的中文偏好',scope_kind='user',scope_id='',scope_space_id=None,version=3,change_epoch=7,source_message_ids_json=[message['id']],expires_at='')
    dataset['assistant_memories'] += [dict(memory,id='memory_corrected',status='superseded',text='合成旧偏好',version=2,change_epoch=5,source_message_ids_json=[]),dict(memory,id='memory_forgotten',status='forgotten',text='',source_excerpt='',source_message_ids_json=[]),dict(memory,id='memory_expired',status='active',expires_at='2020-01-01T00:00:00+00:00')]
    memory['supersedes_id']='memory_corrected'
    change=dataset['assistant_memory_changes'][0];change.update(before_json=None,after_json={'present':None,'order':[3,1,2],'中文':'合成变化'})
    dataset['assistant_memory_changes'] += [dict(change,id=2,memory_id='memory_forgotten',before_json=None,after_json=None),dict(change,id=3,memory_id='memory_corrected',version=2,before_json={'text':'合成旧偏好'},after_json={'status':'superseded'})]
    job=dataset['assistant_jobs'][0];job.update(kind='memory_index',payload_json={'memory_id':memory['id'],'backend_id':'synthetic_retired'},status='queued',attempt=2,lease_epoch=5)
    dataset['assistant_jobs'].append(dict(job,id='synthetic_purge_job',dedupe_key='purge-forgotten',kind='memory_purge',payload_json={'memory_id':'memory_forgotten'}))
    dataset['assistant_model_budget_days'][0].update(budget_date='2026-10-23',lane='background',requests_used=9,request_limit=30,usage_json={'input_tokens':123,'unknown':True})
    dataset['assistant_wiki_pages'][0].update(title='合成Wiki',normalized_title='合成wiki',blocks_json=[{'stable_id':'block-synthetic','text':'有来源与个人依赖的合成块'}])
    for name in ['assistant_wiki_dependencies','assistant_wiki_personal_dependencies']:
        dataset[name][0]['block_id']='block-synthetic'
    dataset['assistant_wiki_personal_dependencies'][0].update(memory_version=3,source_message_id=message['id'])
    task=dataset['research_tasks'][0];task.update(active_goal_id=dataset['research_goals'][0]['goal_id'],status='running',owner_epoch=7,owner_id='synthetic_stopped_worker',lease_until='2026-10-23T00:01:00+00:00')
    for table,rows in dataset.items():
        if table.startswith('research_'):
            for row in rows:
                if 'owner_epoch' in row:row['owner_epoch']=7
    dataset['research_attempts'][0]['status']='running'
    first_fact=dataset['research_fact_revisions'][0]
    dataset['research_fact_revisions'].append(dict(first_fact,fact_revision_id='synthetic_fact_revision_2',revision=2,parent_revision_id=first_fact['fact_revision_id'],supersedes_revision_id=first_fact['fact_revision_id'],claim_text='合成修订事实',content_hash=_json_hash({'claim':'合成修订事实'})))
    dataset['research_knowledge_fact_states']=[dict(fact_id=first_fact['fact_id'],task_id=task['task_id'],current_revision_id='synthetic_fact_revision_2',lifecycle_status='current',currentness_status='current',superseded_by_revision_id=None,latest_observation_set_id=None,state_version=2,updated_at=NOW)]
    dataset['research_side_effects'][0].update(status='unknown',provider_operation_id='synthetic_upstream_task')
    dataset['asr_jobs'][0].update(status='running',task_id='synthetic_existing_asr_task')
    dataset['research_checkpoints'][0].update(sequence=9,state_payload_json={'cursor':4,'array':[3,1,2],'optional':None})
    dataset['research_workspace_records'][0].update(payload_json={'中文':'合成追加工作记录'},source_refs_json=[])
    # Two source byte layouts with the same JSON meaning have different identity.
    old='[ {"from": 0, "to": 1, "content": "合成证据"} ]\n'.encode()
    new='[{"from":0,"to":1,"content":"合成证据"}]'.encode()
    old_hash=source_version(old);new_hash=source_version(new)
    metadata={'id':video['id'],'title':video['title']}
    metadata_hash=_json_hash(metadata);content_hash=_json_hash({'material_hashes':{'subtitle':new_hash},'notes':[],'active_revision':video['active_revision']});membership_hash=_json_hash([{'source_id':source['id']}])
    revision=_json_hash({'metadata_hash':metadata_hash,'content_hash':content_hash,'membership_hash':membership_hash,'extractor_version':'assistant-source-v1'})
    snapshot={'schema':'assistant-source-snapshot-v1','coverage':'subtitle','memberships':[],'materials':{'subtitle':'合成证据'},'material_hashes':{'subtitle':new_hash},'notes':[],'revision':revision,'metadata':metadata,'metadata_hash':metadata_hash,'content_hash':content_hash,'membership_hash':membership_hash}
    snap_bytes=json.dumps(snapshot,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    previous_revision=dataset['assistant_source_revisions'][0]['revision']
    for name,rows in dataset.items():
        for row in rows:
            for key in ['revision','source_revision','current_revision']:
                if row.get(key)==previous_revision:row[key]=revision
    head=dataset['assistant_source_heads'][0]
    head.update(current_revision=revision,metadata_hash=metadata_hash,content_hash=content_hash,membership_hash=membership_hash)
    dataset['assistant_source_revisions'][0].update(snapshot_ref='files/2.json',metadata_hash=metadata_hash,content_hash=content_hash,membership_hash=membership_hash)
    artifact_id=make_source_artifact_id(SourceArtifactReference(video['platform'],video['source_id'],video['part'],'human','zh','synthetic_path'))
    segment_id=make_segment_id(artifact_id,old_hash,0)
    timeline=make_timeline_run_id(old_hash,0)
    dataset['research_evidence_identities'][0].update(source_artifact_id=artifact_id,source_version=old_hash,timeline_run_id=timeline,segment_ids_json=[segment_id],segment_ordinals_json=[0],quote_preview='合成证据')
    dataset['ask_runs'][0].update(lifecycle_status='completed',citations_json=[{'video_id':video['id'],'source_version':old_hash,'source_artifact_id':artifact_id,'segment_id':segment_id,'timeline_run_id':timeline}],answer_blocks_json=[{'text':'合成历史答案'}])
    artifacts=[]
    for i,(payload,logical,version,is_head) in enumerate([(old,'subtitle:1',old_hash,False),(new,'subtitle:1',new_hash,True),(snap_bytes,'source_snapshot:'+revision,revision,True)]):
        digest=hashlib.sha256(payload).hexdigest();file='files/'+str(i)+'.json';(root/file).write_bytes(payload)
        artifacts.append(dict(source_file=file,sha256=digest,byte_size=len(payload),relative_key=WORKSPACE+'/objects/'+digest,media_type='application/json',version_id='synthetic_artifact_'+str(i),video_id=video['id'],logical_key=logical,source_version=version,is_head=is_head,created_at=NOW.isoformat()))
    (root/'synthetic_vectors.json').write_text(json.dumps([{'unit_id':dataset['retrieval_units'][0]['unit_id'],'values':[1.]+[0.]*511}]))
    (root/'artifacts.json').write_text(json.dumps(artifacts,ensure_ascii=False,indent=2))
    schema=json.loads(Path('tests/fixtures/postgres_migration/schema26.json').read_text())['databases']['main']
    source_path=root/'source.sqlite3'
    with sqlite3.connect(source_path) as conn:
        for obj in schema:
            if obj['type']=='table' and obj.get('table_kind')!='shadow' and obj['name']!='sqlite_sequence':
                conn.execute(obj['sql'])
        for name,rows in dataset.items():
            table=next(t for t in schema if t['name']==name and t['type']=='table')
            columns={c['name']:c for c in table['columns']}
            for i,row in enumerate(rows):
                data={k:v for k,v in row.items() if k in columns}
                for key,value in data.items():
                    if key.endswith('_json'):data[key]=json.dumps(value,ensure_ascii=False,separators=(',',':')) if value is not None else None
                    elif isinstance(value,(datetime,)):data[key]=value.isoformat()
                    elif type(value) is bool:data[key]=int(value)
                if name=='assistant_memory_changes' and i==0:data['before_json']='null'
                if name=='video_source_memberships':data['rowid']=[4,9,20][i]
                if name=='assistant_runs':data['rowid']=7
                fields=list(data)
                conn.execute('INSERT INTO "'+name+'" ('+','.join('"'+k+'"' for k in fields)+') VALUES ('+','.join('?' for _ in fields)+')',list(data.values()))
        conn.execute("INSERT INTO schema_meta(key,value) VALUES ('schema_version','26')")
        for obj in schema:
            if obj['type']=='index' and obj['sql']:conn.execute(obj['sql'])
            if obj['type']=='trigger':conn.execute(obj['sql'])
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    return source_path
