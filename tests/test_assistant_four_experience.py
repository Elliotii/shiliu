from __future__ import annotations

import copy
import json
import pytest
from assistant_context_support import ContextHarness
from shiliu.assistant.store import AssistantConflict
from test_assistant_w1 import fixture, execute
from test_assistant_consolidation_nb import _run
from test_assistant_stage_c import _add_material, _drain_wiki_jobs
from test_assistant_s2d import TopicProvider


def memory_args(message_id):
    return dict(text='我下周开始读书', subject_key='reading', kind='context', source_message_ids=[message_id])


def test_cross_turn_memory_time_retry_and_source_protection(app_paths):
    db,_,_,store,_,space,tools=fixture(app_paths)
    fact,ctx=_run(store,space['id'],'我下周开始读书',key='fact')
    message=ctx['thread']['messages'][-1]
    with db.connect() as c:
        c.execute("UPDATE assistant_messages SET created_at='2026-10-17T01:00:00+00:00' WHERE id=?",(message['id'],))
    save,_=_run(store,space['id'],'记住这个',thread_id=fact['thread_id'],key='save')
    args=memory_args(message['id'])
    bad=execute(tools,store,save,{**args,'kind':'plan'},name='memory_save')
    assert bad['status']=='invalid_arguments'
    retry,_=_run(store,space['id'],'再试一下',thread_id=fact['thread_id'],key='retry')
    result=execute(tools,store,retry,args,name='memory_save')
    assert result['status']=='ok',result
    memory=result['items'][0]
    assert memory['expires_at'] is None  # v2: plan time is not Memory expiry.
    assert memory['time_context']['events'][0]['value']=='2026-W43'
    again=execute(tools,store,retry,args,call='another',name='memory_save')
    assert again['items'][0]['id']==memory['id']
    assert len(tools.memories.list(space_id=space['id']))==1
    other,_=_run(store,space['id'],'记住',key='other')
    assert execute(tools,store,other,args,name='memory_save')['status']!='ok'
    tools.memories.forget(memory['id'],expected_version=memory['version'],operation_key='forget')
    assert execute(tools,store,retry,args,call='after-forget',name='memory_save')['status']!='ok'


def test_memory_unknown_commit_uses_original_receipt(app_paths):
    _,_,_,store,_,space,tools=fixture(app_paths)
    first,ctx=_run(store,space['id'],'记住我下周开始读书',key='first')
    args=memory_args(ctx['thread']['messages'][-1]['id'])
    store.begin_tool_call(first['id'],ordinal=1,call_id='save',name='memory_save',arguments=args,
                          operation_key=f"tool:{first['id']}:save")
    saved=execute(tools,store,first,args,name='memory_save')
    assert saved['status']=='ok'
    # Transaction committed but tool completion was never registered.
    retry,_=_run(store,space['id'],'重试刚才的保存',thread_id=first['thread_id'],key='retry')
    restored=execute(tools,store,retry,args,call='new-call',name='memory_save')
    assert restored['status']=='ok',restored
    assert restored['items'][0]['id']==saved['items'][0]['id']
    changed=execute(tools,store,retry,{**args,'text':'我下周开始每天读书'},call='changed',name='memory_save')
    assert changed['error_code']=='memory_previous_outcome_unknown'
    assert len(tools.memories.list(space_id=space['id']))==1


def test_visible_user_identity_does_not_change_persisted_message(app_paths):
    _,_,_,store,_,space,tools=fixture(app_paths)
    run,ctx=_run(store,space['id'],'记住我喜欢散步')
    user=ctx['thread']['messages'][-1]
    messages,_,_=ContextHarness(tools.memories).request_input(store.run_context(run['id']))
    assert user['id'] in messages[-1]['content']
    assert store.get_thread(run['thread_id'])['messages'][-1]['content']==user['content']


def wiki_setup(app_paths):
    db,artifacts,sources,store,wiki,_,_=fixture(app_paths)
    sid=db.create_favorite_source(folder_id=8822,folder_title='isolated',history_policy='all')
    vid=_add_material(db,artifacts,sid,bvid='BV1FOUR12345',title='测试材料',text='阅读要先确认问题，再分析论证。')
    space=store.create_space(name='automatic',source_ids=[sid],maintenance_mode='automatic')
    with db.connect() as c:
        gen=wiki._ensure_dirty(c,vid);wiki._enqueue_reconcile(c,vid,gen)
    return db,store,wiki,space,sid,vid


def test_queued_automatic_cancel_and_shared_demand(app_paths):
    db,store,wiki,space,sid,vid=wiki_setup(app_paths)
    store.update_space(space['id'],expected_scope_version=1,maintenance_mode='on_demand')
    job=store.claim_job(owner='test')
    assert wiki.reconcile(job)['superseded']
    second=store.create_space(name='other',source_ids=[sid],maintenance_mode='automatic')
    assert wiki._maintenance_authorized(job['payload'])
    store.update_space(second['id'],expected_scope_version=1,maintenance_mode='on_demand')
    wiki.request_topic(space_id=space['id'],topic='共同主题',source_refs=[f'video:{vid}'],request_key='user')
    assert wiki._maintenance_authorized(job['payload'])
    store.finish_job(job['id'],proposal={'superseded':True},owner=job['lease_owner'],lease_epoch=job['lease_epoch'])
    _drain_wiki_jobs(store,wiki,TopicProvider())
    assert wiki.list_pages(space_id=space['id'])
    assert not wiki.list_pages(space_id=second['id'])
    assert not wiki._maintenance_authorized(job['payload'])


def test_source_model_inflight_mode_change_cannot_commit_card(app_paths):
    db,store,wiki,space,_,_=wiki_setup(app_paths)
    root=store.claim_job(owner='root');result=wiki.reconcile(root)
    store.finish_job(root['id'],proposal=result,owner=root['lease_owner'],lease_epoch=root['lease_epoch'])
    job=store.claim_job(owner='extract')
    store.update_space(space['id'],expected_scope_version=1,maintenance_mode='on_demand')
    class Never:
        def generate_json(self,**kwargs):
            raise AssertionError('closed automatic task must not dispatch a model')
    assert wiki.extract_source_card(job,provider=Never())['superseded']
    store.update_space(space['id'],expected_scope_version=1,maintenance_mode='automatic')
    class Closing(TopicProvider):
        def generate_json(self,**kwargs):
            result=super().generate_json(**kwargs)
            store.update_space(space['id'],expected_scope_version=1,maintenance_mode='on_demand')
            return result
    with pytest.raises(AssistantConflict,match='wiki_maintenance_not_authorized'):
        wiki.extract_source_card(job,provider=Closing())
    assert wiki.get_source_card(job['payload']['revision']) is None


def test_wiki_model_inflight_mode_change_cannot_publish(app_paths):
    db,store,wiki,space,_,vid=wiki_setup(app_paths)
    # Explicit initial extraction remains valid in on-demand mode.
    wiki.request_topic(space_id=space['id'],topic='共同主题',source_refs=[f'video:{vid}'],request_key='initial')
    _drain_wiki_jobs(store,wiki,TopicProvider())
    page=wiki.list_pages(space_id=space['id'])[0]
    before=copy.deepcopy(page)
    with db.connect() as c:
        revision=c.execute('SELECT current_revision FROM assistant_source_heads WHERE video_id=?',(vid,)).fetchone()[0]
        jid=store.enqueue_job(c,kind='wiki_integrate',dedupe_key='auto-new',payload=dict(space_id=space['id'],scope_version=1,video_id=vid,revision=revision,topic='新主题'))
    job=store.claim_job(owner='integrate');assert job['id']==jid
    class Closing(TopicProvider):
        def generate_json(self,**kwargs):
            result=super().generate_json(**kwargs)
            store.update_space(space['id'],expected_scope_version=1,maintenance_mode='on_demand')
            return result
    with pytest.raises(AssistantConflict,match='wiki_maintenance_not_authorized'):
        wiki.integrate_source_card(job,provider=Closing())
    assert wiki.get_page(page['id'])==before
    assert len(wiki.list_pages(space_id=space['id']))==1


def test_space_edit_api_preserves_video_limit_and_does_not_queue_maintenance(app_paths):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from shiliu.assistant.api import router
    db,store,wiki,space,sid,vid=wiki_setup(app_paths)
    limited=store.update_space(space['id'],expected_scope_version=1,video_ids=[vid])
    app=FastAPI();app.include_router(router)
    app.state.core=SimpleNamespace(config=SimpleNamespace(assistant_enabled=True),assistant_runtime=SimpleNamespace(store=store))
    client=TestClient(app)
    before=len(store.list_jobs())
    detail=client.get(f"/api/assistant/spaces/{space['id']}").json()['space']
    assert detail['selected_videos']==[{'id':vid,'title':'测试材料'}]
    response=client.patch(f"/api/assistant/spaces/{space['id']}",json={'expected_scope_version':limited['scope_version'],
        'name':'日常使用','maintenance_mode':'on_demand'})
    assert response.status_code==200,response.text
    edited=response.json()['space'];assert edited['video_ids']==[vid] and edited['source_ids']==[sid]
    assert edited['scope_version']==limited['scope_version'] and len(store.list_jobs())==before
    denied=client.patch(f"/api/assistant/spaces/{space['id']}",json={'expected_scope_version':edited['scope_version'],
        'all_active':True,'maintenance_mode':'automatic'})
    assert denied.status_code==422
    read=client.get('/api/assistant/maintenance-activity',params={'space_id':space['id'],'limit':2})
    assert read.status_code==200 and len(read.json()['items'])<=2


def test_activity_is_bounded_scoped_read_only_and_proves_writes(app_paths):
    db,store,wiki,space,sid,vid=wiki_setup(app_paths)
    from shiliu.assistant.memory import MemoryService
    m=MemoryService(db)
    auto=m.save_explicit(text='我喜欢散步',subject_key='walk',kind='preference',scope_kind='space',scope_id=space['id'],operation_key='auto',origin='extracted')
    m.save_explicit(text='所有对话使用简洁表达',subject_key='style',kind='preference',scope_kind='user',scope_id=None,operation_key='global',origin='extracted')
    other=store.create_space(name='其他',all_active=True)
    m.save_explicit(text='其他空间秘密',subject_key='other',kind='context',scope_kind='space',scope_id=other['id'],operation_key='other',origin='extracted')
    wiki.request_topic(space_id=space['id'],topic='共同主题',source_refs=[f'video:{vid}'],request_key='activity')
    # The ordinary drain helper only handles Wiki jobs; let the isolated index
    # records finish without starting a semantic backend.
    with db.connect() as c:c.execute("UPDATE assistant_jobs SET status='succeeded' WHERE kind='memory_index'")
    _drain_wiki_jobs(store,wiki,TopicProvider())
    page=wiki.list_pages(space_id=space['id'])[0]
    with db.connect() as c:
        jid=store.enqueue_job(c,kind='wiki_integrate',dedupe_key='no-change',payload={'space_id':space['id'],'video_id':vid})
        c.execute("UPDATE assistant_jobs SET status='succeeded',proposal_json=? WHERE id=?",(json.dumps({'no_change':True,'page_id':page['id'],'version':page['version']}),jid))
        blocked=store.enqueue_job(c,kind='wiki_integrate',dedupe_key='blocked',payload={'space_id':space['id'],'video_id':vid})
        c.execute("UPDATE assistant_jobs SET status='blocked',last_error_code='wiki_manual_conflict' WHERE id=?",(blocked,))
        for n in range(110):store.enqueue_job(c,kind='wiki_integrate',dedupe_key=f'other:{n}',payload={'space_id':other['id'],'video_id':vid})
    with db.connect() as c:before=[tuple(row) for row in c.execute('SELECT id,status FROM assistant_jobs')]
    activity=store.maintenance_activity(space['id'],limit=50)
    text=json.dumps(activity,ensure_ascii=False)
    assert '我喜欢散步' in text and '所有对话' in text and '其他空间秘密' not in text
    assert any(item['result']=='无需变化' and item.get('page_id')==page['id'] for item in activity['items'])
    assert any(item['result'] in {'新增知识页','增补知识'} for item in activity['items'])
    assert activity['counts']['blocked']==1 and activity['counts'].get('queued',0)==0
    assert len(store.maintenance_activity(space['id'],limit=2)['items'])<=2
    assert len(store.list_jobs(space_id=space['id']))<100
    with db.connect() as c:assert [tuple(row) for row in c.execute('SELECT id,status FROM assistant_jobs')]==before
    m.forget(auto['id'],expected_version=1,operation_key='forget-activity')
    assert '我喜欢散步' not in json.dumps(store.maintenance_activity(space['id']),ensure_ascii=False)


def test_uncertain_legacy_call_does_not_capture_new_fact(app_paths):
    _,_,_,store,_,space,tools=fixture(app_paths)
    old,_=_run(store,space['id'],'记住我喜欢步行',key='old')
    legacy={'text':'我喜欢步行','subject_key':'exercise','kind':'preference'}
    store.begin_tool_call(old['id'],ordinal=1,call_id='unknown',name='memory_save',arguments=legacy)
    new,ctx=_run(store,space['id'],'现在改记我喜欢骑车',thread_id=old['thread_id'],key='new')
    args={**legacy,'text':'我喜欢骑车','source_message_ids':[ctx['thread']['messages'][-1]['id']]}
    saved=execute(tools,store,new,args,name='memory_save')
    assert saved['status']=='ok',saved
    assert saved['items'][0]['text']=='我喜欢骑车'


def test_explicit_batch_keeps_original_scope_version_during_model(app_paths):
    db,store,wiki,space,_,vid=wiki_setup(app_paths)
    with db.connect() as c:c.execute("UPDATE assistant_jobs SET status='succeeded'")
    store.update_space(space['id'],expected_scope_version=1,maintenance_mode='on_demand')
    batch=wiki.bootstrap_space(space['id'],limit=1,model_budget=3)
    root=store.claim_job(owner='batch');assert root['payload']['scope_version']==1
    result=wiki.reconcile(root)
    store.finish_job(root['id'],proposal=result,owner=root['lease_owner'],lease_epoch=root['lease_epoch'])
    extract=store.claim_job(owner='extract');assert extract['payload']['scope_version']==1
    class Changing(TopicProvider):
        def generate_json(self,**kwargs):
            result=super().generate_json(**kwargs)
            store.update_space(space['id'],expected_scope_version=1,video_ids=[vid])
            return result
    with pytest.raises(AssistantConflict,match='wiki_maintenance_not_authorized'):
        wiki.extract_source_card(extract,provider=Changing())
    assert wiki.get_source_card(extract['payload']['revision']) is None


def test_repeated_memory_error_uses_existing_early_finish(app_paths):
    import asyncio
    from shiliu.assistant.provider import ModelTurn,NativeToolCall
    from test_assistant_k import graph_for
    _,_,_,store,_,space,tools=fixture(app_paths)
    run,_=_run(store,space['id'],'记住我的安排',key='repeated')
    run=store.claim_next_run()
    class Provider:
        calls=0
        def turn(self,**kwargs):
            self.calls+=1
            if not kwargs['tools']:return ModelTurn(text='未能定位原话，请明确要保存哪条安排。')
            return ModelTurn(text='',tool_calls=[NativeToolCall(f'bad{self.calls}','memory_save',
                {'text':'我下周读书','subject_key':'book','kind':'context','source_message_ids':['missing']})])
    provider=Provider();asyncio.run(graph_for(store,tools,provider).run(run))
    assert provider.calls<=4
    assert store.get_run(run['id'])['status']=='completed'
    assert not tools.memories.list(space_id=space['id'])


def test_activity_wait_failure_statuses_are_not_success(app_paths):
    db,_,_,store,_,space,_=fixture(app_paths)
    expected={'queued':'等待执行','running':'执行中','retry_wait':'等待重试','budget_wait':'等待额度',
              'blocked':'需要处理','failed':'处理失败'}
    ids={}
    with db.connect() as c:
        for status in expected:
            ids[status]=store.enqueue_job(c,kind='wiki_integrate',dedupe_key=status,payload={'space_id':space['id']})
            c.execute('UPDATE assistant_jobs SET status=? WHERE id=?',(status,ids[status]))
    result=store.maintenance_activity(space['id'])
    by_id={item['id']:item for item in result['items']}
    assert {status:by_id[jid]['result'] for status,jid in ids.items()}==expected
    assert all('新增' not in item['result'] and '修改' not in item['result'] for item in result['items'])
