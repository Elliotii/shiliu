from __future__ import annotations

from test_assistant_context_c2 import c2
from test_assistant_context_c3 import c3, history, state_for, notes
from assistant_context_support import mixed_checkpoint

import asyncio
import copy
import json
import pytest

from assistant_context_support import ContextHarness
from shiliu.assistant.provider import ModelTurn, NativeToolCall
from shiliu.assistant.store import AssistantConflict
from test_assistant_w1 import fixture, execute
from test_assistant_consolidation_nb import _run, _topics
from test_assistant_real_use_a import formal, material
from test_assistant_k import graph_for


def record(store, run, name, args, result, call='read', ordinal=1):
    store.begin_tool_call(run['id'], ordinal=ordinal, call_id=call, name=name, arguments=args)
    store.save_assistant_tool_message(run['id'], content='', provider_payload={'tool_calls':[
        {'id':call,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]})
    store.finish_tool_call(run['id'], call_id=call, result=result)
    store.save_tool_result_message(run['id'], content=json.dumps(result),
                                  provider_payload={'name':name,'tool_call_id':call})


def test_natural_save_first_context_exposes_answer_identity_and_existing_body(c3):
    from test_assistant_context_c2 import running, batch, read
    run = running(c3,text='请核对阅读方法的条件。')
    result = read(c3,'natural-read')
    batch(c3,run,[('natural-read','collection_read',{'source_ref':f'video:{c3.video_id}','view':'summary'},result)])
    answer_text = '四层阅读与四个问题：先判断全书主题，再检查论证。'
    assert c3.store.complete_run(run['id'],epoch=run['run_epoch'],answer=answer_text,usage={})
    answer = next(m for m in c3.store.get_thread(c3.thread['id'])['messages'] if m['content']==answer_text)
    save = running(c3,text='把之前的阅读方法保存为知识',key='natural-save')
    before = copy.deepcopy(c3.store.get_thread(c3.thread['id'])['messages'])
    candidate = c3.composer.prepare(save['id'],provider=c3.provider)
    assert answer['id'] in str(candidate.request.body) and answer_text in str(candidate.request.body)
    assert result['items'][0]['content'] in str(candidate.request.body)
    assert c3.store.get_thread(c3.thread['id'])['messages']==before
    assert not c3.store.get_run(save['id'])['working_state'].get('knowledge_save')


def test_view_error_identifies_actual_ref_then_same_run_repair(app_paths):
    db,artifacts,sources,store,wiki,space,tools=fixture(app_paths)
    run,_=_run(store,space['id'],'保存讨论')
    ref=material(db,artifacts,sources,store,run,1,'summary')
    topic={'title':'日常运动','purpose':'实际做法','blocks':[{'role':'source','heading':'动作|条件',
        'markdown':'摘要中的动作','source_refs':[ref],'source_view':'transcript'}]}
    failed=execute(tools,store,run,{'topics':[topic]})
    plan=failed['items'][0]
    issues=plan.get('issues') or plan['results']['0']['issues']
    assert any(i['source_ref']==ref and i['requested_view']=='transcript' and i['observed_views']==['summary'] for i in issues)
    assert all('指定字段' not in i['action'] for i in issues)
    replacement=copy.deepcopy(topic);replacement['blocks'][0]['source_view']='summary'
    fixed=execute(tools,store,run,{'plan_id':plan['id'],'expected_version':plan['version'],
        'replacements':[{'index':0,'topic':replacement}]},call='fixed')
    assert fixed['status']=='ok',fixed
    assert fixed['items'][0]['id']==plan['id']
    assert len(wiki.list_pages(space_id=space['id']))==1


def test_save_projection_preserves_target_users_and_reread_not_fake_delivery(app_paths):
    _,_,_,store,_,space,tools=fixture(app_paths)
    research,_=_run(store,space['id'],'只安排午休，保留疼痛时停止这一限制',key='research')
    # Non-source result is deliberately large; the persisted result remains readable.
    result={'status':'ok','summary':'历史检索记录','items':[{'text':'历史候选正文'*5000}],
        'source_refs':[],'dependency_refs':[],'coverage':{},'result_ref':f"run-result:{research['id']}:read"}
    research=store.claim_next_run()
    record(store,research,'collection_search',{'query':'历史'},result)
    store.complete_run(research['id'],epoch=research['run_epoch'],answer='正式运动成果：午休活动，疼痛停止。',usage={})
    answer=next(m for m in store.get_thread(research['thread_id'])['messages'] if m['role']=='assistant' and m['content'])
    run=store.create_run(research['thread_id'],text='请保存这份成果',request_id='save',answer_message_id=answer['id'])
    run=store.claim_next_run()
    composer=ContextHarness(tools.memories)
    messages,_,meta=composer.request_input(store.run_context(run['id']))
    text=json.dumps(messages,ensure_ascii=False)
    assert '正式运动成果：午休活动，疼痛停止。' in text
    assert '只安排午休，保留疼痛时停止这一限制' in text
    assert '历史候选正文' in text and result['result_ref'] in text
    assert not meta['delivered_read_spans']
    original=store.resolve_run_result(result['result_ref'],current_thread_id=run['thread_id'],current_scope_version=space['scope_version'])
    assert original['result']['items']==result['items']


def test_partial_projection_keeps_failed_draft_and_success_handles():
    from shiliu.assistant.delivery import project_tool_result
    plan = {'id':'plan','payload':{'topics':[{'title':'完成','blocks':[{'markdown':'成功大稿'*100}]},
        {'title':'待修','blocks':[{'markdown':'只修这个原稿','source_view':'summary'}]}]},
        'results':{'0':{'status':'completed','page_id':'page','version':1},'1':{'status':'failed','issues':[{'code':'wrong_view'}]}}}
    raw = {'items':[plan],'status':'partial'}
    original = copy.deepcopy(raw)
    projected = project_tool_result('knowledge_save_discussion',raw,result_ref='run-result:r:save',sources=None)
    text = json.dumps(projected,ensure_ascii=False)
    assert '成功大稿' not in text and '只修这个原稿' in text and 'wrong_view' in text and 'page' in text
    assert projected['items'][0]['unfinished_topics'][0]['index']==1
    assert raw==original and projected['status']=='partial'


@pytest.mark.parametrize('button',[True,False])
def test_receipt_completion_only_for_button_and_no_fake_model_call(app_paths,button):
    _,_,_,store,wiki,space,tools=fixture(app_paths)
    research,answer=formal(store,space,'可保存的正式运动方案')
    run=store.create_run(research['thread_id'],text='保存方案并解释适用条件' if not button else '保存讨论成果',
        request_id='save',answer_message_id=answer['id'],receipt_only=button)
    run=store.claim_next_run()
    class Provider:
        calls=0
        def turn(self,**kwargs):
            self.calls+=1
            if self.calls==1:
                return ModelTurn(text='',tool_calls=[NativeToolCall('save','knowledge_save_discussion',
                    {'topics':[_topics()[0]],'answer_message_ids':[answer['id']]})],usage={'total_tokens':10})
            return ModelTurn(text='已保存，适用条件仍需按实际场景判断。',usage={'total_tokens':5})
    provider=Provider();asyncio.run(graph_for(store,tools,provider).run(run))
    final=store.get_run(run['id']);assert final['status']=='completed',final
    assert provider.calls==(1 if button else 2)
    assert final['working_state']['execution_budget']['model_calls']==provider.calls
    message=[m for m in store.get_thread(run['thread_id'])['messages'] if m['role']=='assistant' and m['content']][-1]
    assert json.loads(message['provider_payload_json'])['origin']==('operation_receipt' if button else 'model')
    assert len(wiki.list_pages(space_id=space['id']))==1
    if button:
        thread=store.get_thread(run['thread_id'])
        assert thread['save_answer_message_id']==answer['id']
        with pytest.raises(AssistantConflict):
            store.knowledge_message(message['id'],thread_id=run['thread_id'])
        assert store.knowledge_message(message['id'],thread_id=run['thread_id'],allow_operation_receipt=True)['content']


def test_receipt_result_does_not_bypass_stopping(app_paths,monkeypatch):
    _,_,_,store,_,space,tools=fixture(app_paths)
    research,answer=formal(store,space)
    run=store.create_run(research['thread_id'],text='保存',request_id='save',answer_message_id=answer['id'])
    run=store.claim_next_run()
    graph=graph_for(store,tools,None)
    store.cancel_run(run['id'])
    state={'run_id':run['id'],'epoch':run['run_epoch'],'turn':ModelTurn(text='已保存'),
        'completion_origin':'operation_receipt','receipt_pages':[]}
    assert asyncio.run(graph._final(state))['route']=='stopped'
    assert not any(m['role']=='assistant' and m['content']=='已保存' for m in store.get_thread(run['thread_id'])['messages'])


def test_wiki_feedback_undo_creation_update_and_conflict(app_paths):
    _,_,_,store,wiki,space,tools=fixture(app_paths)
    run,_=_run(store,space['id'],'保存讨论')
    saved=execute(tools,store,run,{'topics':[_topics()[0]]})
    plan=saved['items'][0];item=saved['coverage']['save_feedback']['items'][0]
    assert item['undo']=={'kind':'archive'}
    page=wiki.get_page(item['page_id'],space_id=space['id'])
    wiki.edit_block(page['id'],block_id=page['blocks'][0]['stable_id'],markdown='用户的新编辑',expected_version=1,operation_key='edit')
    assert wiki.save_feedback(plan)['items'][0]['undo'] is None
    with pytest.raises(AssistantConflict):
        wiki.manage_page(page['id'],space_id=space['id'],action='archive',expected_version=1,operation_key='old-undo')
    next_run,_=_run(store,space['id'],'保存更新',thread_id=run['thread_id'],key='update')
    topic=copy.deepcopy(_topics()[0]);topic['expected_version']=2
    updated=execute(tools,store,next_run,{'topics':[topic]})
    item=updated['coverage']['save_feedback']['items'][0]
    assert item['undo']=={'kind':'revert','target_version':2}
    wiki.revert(page['id'],target_version=2,expected_version=3,operation_key='undo-update')
    assert any(b['markdown']=='用户的新编辑' for b in wiki.get_page(page['id'],space_id=space['id'])['blocks'])


def test_memory_feedback_noop_has_no_undo(app_paths):
    _,_,_,_,_,space,tools=fixture(app_paths)
    m=tools.memories;args=dict(text='喜欢摄影',subject_key='photo',kind='preference',scope_kind='space',scope_id=space['id'])
    created=m.save_explicit(**args,operation_key='new')
    feedback=m.creation_feedback(created,save_operation_key='new',space_id=space['id'])
    assert feedback['items'][0]['undo']['save_operation_key']=='new'
    reused=m.save_explicit(**args,operation_key='same')
    assert m.creation_feedback(reused,save_operation_key='same',space_id=space['id'])['items'][0]['undo'] is None
    assert m.creation_feedback(created,save_operation_key='new',space_id=space['id'])['items'][0]['undo'] is None


def test_fresh_reread_body_reaches_save_model_then_becomes_handle(c3):
    from test_assistant_context_c2 import running, batch, read
    run = running(c3,text='明确再读这份原文，再保存讨论成果。')
    first = read(c3,'reread1')
    batch(c3,run,[('reread1','collection_read',{},first)])
    before = c3.composer.prepare(run['id'],provider=c3.provider)
    c3.composer.persist(before)
    c3.store.confirm_model_delivery(run['id'],epoch=run['run_epoch'],spans=[],message_ids=before.message_ids,context_revision=before.state['revision'])
    batch(c3,run,[('reread2','collection_read',{},read(c3,'reread2'))])
    after = c3.composer.prepare(run['id'],provider=c3.provider)
    assert after.request.body['messages'][:len(before.request.body['messages'])]==before.request.body['messages']
    assert sum('甲乙丙丁条件' in m.get('content','') for m in after.request.body['messages'] if m['role']=='tool')==2
    assert first['items'][0]['content'] in str(after.request.body)


def test_memory_index_projection_does_not_block_creation_undo(app_paths):
    db,_,_,_,_,space,tools=fixture(app_paths)
    m=tools.memories
    value=m.save_explicit(text='喜欢散步',subject_key='walking',kind='preference',scope_kind='space',scope_id=space['id'],operation_key='new')
    with db.connect() as c:
        c.execute('UPDATE assistant_memories SET backend_id=?,last_projected_version=1,updated_at=? WHERE id=?',
                  ('derived-index-id','2026-10-16T00:00:00+00:00',value['id']))
    assert m.creation_feedback(m.get(value['id']),save_operation_key='new',space_id=space['id'])['items'][0]['undo']
    assert m.undo_created(value['id'],save_operation_key='new',expected_version=1,operation_key='undo')['status']=='forgotten'
