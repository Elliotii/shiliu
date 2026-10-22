from __future__ import annotations
import asyncio
import copy
import json
import pytest
from shiliu.assistant.store import AssistantConflict
from shiliu.assistant.provider import ModelTurn, NativeToolCall
from test_assistant_w1 import fixture, execute
from test_assistant_consolidation_nb import _run, _topics
from test_assistant_stage_c import _add_material


def persisted(tools, store, run, args, call='save'):
    # The Runtime persists args before validation. Direct execute helpers alone do not.
    store.begin_tool_call(run['id'], ordinal=1, call_id=call, name='knowledge_save_discussion', arguments=args)
    result=execute(tools,store,run,args,call)
    store.finish_tool_call(run['id'],call_id=call,result=result)
    return result


def formal(store, space, text='泡面做法成果'):
    run=store.create_run(store.create_thread(space['id'])['id'],text='研究材料',request_id='research')
    claimed=store.claim_next_run()
    store.complete_run(run['id'],epoch=claimed['run_epoch'],answer=text,usage={})
    msg=next(m for m in store.get_thread(run['thread_id'])['messages'] if m['role']=='assistant')
    return run,msg


@pytest.mark.parametrize('bad_target',[False,True])
def test_schema_invalid_resume_uses_persisted_call_not_new_binding(app_paths,bad_target):
    _,_,_,store,wiki,space,tools=fixture(app_paths)
    research,answer=formal(store,space)
    first,_=_run(store,space['id'],'请保存这份成果',thread_id=research['thread_id'],key='first')
    args={'answer_message_ids':['not-a-message' if bad_target else answer['id']], 'topics':[_topics()[0]]}
    args['topics'][0]['blocks'][0]['role_note']='非法字段'
    error=persisted(tools,store,first,args)
    assert error['status']=='invalid_arguments' and not wiki.list_discussion_plans(space_id=space['id'])
    assert not store.get_run(first['id'])['working_state'].get('knowledge_save')
    next_run,_=_run(store,space['id'],'再试一下',thread_id=first['thread_id'],key='next')
    fixed={'resume_result_ref':f"run-result:{first['id']}:save",'topics':[_topics()[0]]}
    if bad_target:
        denied=execute(tools,store,next_run,fixed)
        assert denied['status']=='invalid_arguments' and not wiki.list_pages(space_id=space['id'])
        fixed['answer_message_ids']=[answer['id']]
    saved=execute(tools,store,next_run,fixed,'fixed')
    assert saved['status']=='ok',saved
    plan=saved['items'][0]
    assert plan['source_message_id']==store.knowledge_save_request(first['id'])['source_message_id']
    assert plan['payload']['save_request']['answer_message_ids']==[answer['id']]
    assert len(wiki.list_discussion_plans(space_id=space['id']))==1


def test_partial_resubmission_then_new_edit_can_add_preference_to_success(app_paths):
    _,_,_,store,wiki,space,tools=fixture(app_paths)
    quote,ctx=_run(store,space['id'],'我喜欢餐蛋面加午餐肉',key='quote')
    quote_id=ctx['thread']['messages'][-1]['id']
    run,_=_run(store,space['id'],'保存讨论',thread_id=quote['thread_id'],key='save')
    topics=_topics();topics[1]['blocks']=[{'role':'personal','heading':'偏好','markdown':'**餐蛋面**，加午餐肉','user_quote':'我喜欢餐蛋面加午餐肉','source_refs':['video:999:fake']}]
    partial=execute(tools,store,run,{'topics':topics});assert partial['status']=='partial',partial
    plan=partial['items'][0];first=wiki.list_pages(space_id=space['id'])[0]
    next_run,_=_run(store,space['id'],'按照你的方法保存吧',thread_id=run['thread_id'],key='retry')
    replacement=copy.deepcopy(topics[1]);replacement['blocks'][0].update(source_refs=[],user_message_id=quote_id)
    fixed=execute(tools,store,next_run,{'plan_id':plan['id'],'expected_version':plan['version'],'replacements':[{'index':1,'topic':replacement}]})
    assert fixed['status']=='ok',fixed
    assert wiki.get_page(first['id'],space_id=space['id'])['version']==first['version']
    denied=execute(tools,store,next_run,{'plan_id':plan['id'],'expected_version':fixed['items'][0]['version'],'replacements':[{'index':0,'topic':topics[0]}]},'rewrite')
    assert denied['status']!='ok'
    edit,_=_run(store,space['id'],'把这条偏好补充到已保存的做法页',thread_id=run['thread_id'],key='edit')
    added=execute(tools,store,edit,{'page_id':first['id'],'expected_page_version':first['version'],'text':'我喜欢餐蛋面加午餐肉','user_message_id':quote_id},'note',name='knowledge_save_personal')
    assert added['status']=='ok',added
    assert wiki.get_page(first['id'],space_id=space['id'])['version']==first['version']+1


def material(db,artifacts,sources,store,run,n,view):
    sid=db.create_favorite_source(folder_id=800+n,folder_title='isolated',history_policy='all')
    vid=_add_material(db,artifacts,sid,bvid=f'BV1REAL{n:05d}',title=f'做法{n}',text='有条件正文')
    ref=f'video:{vid}:{sources.snapshots.capture(vid).revision}'
    with db.connect() as c:
        w=json.loads(c.execute('SELECT working_state_json FROM assistant_runs WHERE id=?',(run['id'],)).fetchone()[0])
        w.setdefault('model_delivered_materials',[]).append({'kind':'collection_read','source_ref':ref,'view':view,'projection':'正文片段'})
        c.execute('UPDATE assistant_runs SET working_state_json=? WHERE id=?',(json.dumps(w),run['id']))
    return ref


def test_source_delivery_blank_view_never_uses_metadata_or_implicit_binding_bypass(app_paths):
    db,artifacts,sources,store,wiki,space,tools=fixture(app_paths)
    run,_=_run(store,space['id'],'保存研究',key='sources')
    meta=material(db,artifacts,sources,store,run,0,'metadata')
    args={'topics':[{'title':'来源事实','purpose':'读到什么保存什么','blocks':[{'role':'source','heading':'实际做法','markdown':'不能凭元数据推导字幕','source_refs':[meta]}]}]}
    rejected=execute(tools,store,run,args)
    assert rejected['status']=='partial' and 'source_not_delivered' in json.dumps(rejected)
    refs=[material(db,artifacts,sources,store,run,n,'summary' if n==1 else 'transcript') for n in range(1,7)]
    topic=copy.deepcopy(args['topics'][0]);topic['blocks'][0].update(markdown='来自已读摘要及转写的综合，未宣称全字幕',source_refs=refs)
    plan=rejected['items'][0]
    fixed=execute(tools,store,run,{'plan_id':plan['id'],'expected_version':plan['version'],'replacements':[{'index':0,'topic':topic}]},'mixed')
    assert fixed['status']=='ok',fixed
    read=wiki.get_page(fixed['items'][0]['results']['0']['page_id'],space_id=space['id'])
    assert read['blocks'][0].get('source_view') in {None,''}
    # An explicit transcript claim for a summary-only ref is still rejected.
    second,_=_run(store,space['id'],'保存另一个主题',thread_id=run['thread_id'],key='wrong-view')
    topic['title']='字幕不能冒充';topic['blocks'][0]['source_view']='transcript'
    bad=execute(tools,store,second,{'topics':[topic]})
    assert bad['status']=='partial' and 'source_not_delivered' in json.dumps(bad)


def test_history_reads_old_official_answer_and_not_other_thread(app_paths):
    _,_,_,store,_,space,tools=fixture(app_paths)
    research,answer=formal(store,space,'旧的正式泡面成果很长')
    run,_=_run(store,space['id'],'找早先的成果',thread_id=research['thread_id'],key='read')
    result=execute(tools,store,run,{'message_id':answer['id'],'role':'assistant','start':2,'max_characters':4},name='conversation_history')
    assert result['items'][0]['messages'][0]['text']==answer['content'][2:6]
    other,_=_run(store,space['id'],'其他对话',key='other')
    assert execute(tools,store,other,{'message_id':answer['id'],'role':'all'},name='conversation_history')['items'][0]['messages']==[]


def test_list_is_lightweight_without_validating_drafts(app_paths,monkeypatch):
    _,_,_,store,wiki,space,tools=fixture(app_paths)
    run,_=_run(store,space['id'],'保存讨论')
    execute(tools,store,run,{'topics':[_topics()[0]]})
    monkeypatch.setattr(wiki,'_plan_block_issues',lambda **kw:pytest.fail('list revalidated draft'))
    listing=wiki.list_discussion_plans(space_id=space['id'],lightweight=True)
    assert len(listing)==1 and 'blocks' not in listing[0]['payload']['topics'][0]


def test_memory_creation_undo_does_not_suppress_message_and_blocks_old_extraction(app_paths):
    db,_,_,store,_,space,tools=fixture(app_paths);m=tools.memories
    run,ctx=_run(store,space['id'],'我喜欢餐蛋面，也喜欢摄影')
    msg=ctx['thread']['messages'][-1]['id']
    old_epoch=m.current_epoch()
    saved=m.save_explicit(text='我喜欢餐蛋面',subject_key='food',kind='preference',scope_kind='space',scope_id=space['id'],operation_key='save-food',source_message_ids=[msg])
    other=m.save_explicit(text='我喜欢摄影',subject_key='photo',kind='preference',scope_kind='space',scope_id=space['id'],operation_key='save-photo',source_message_ids=[msg])
    result=m.undo_created(saved['id'],save_operation_key='save-food',expected_version=1,operation_key='undo-food')
    assert result['status']=='forgotten'
    assert msg not in m.suppressed_source_message_ids(space_id=space['id'])
    assert m.get(other['id'])['status']=='active'
    proposal={'op':'add','scope_kind':'space','scope_id':space['id'],'text':'我喜欢餐蛋面','subject_key':'food','kind':'preference'}
    assert m.apply_extracted(proposal,source_message_ids=[msg],expected_epoch=old_epoch,operation_key='old-extract') is None
    assert m.apply_extracted({**proposal,'subject_key':'new-label'},source_message_ids=[msg],expected_epoch=m.current_epoch(),operation_key='new-extract') is None
    assert m.undo_created(saved['id'],save_operation_key='save-food',expected_version=1,operation_key='undo-food')==result


def test_memory_noop_save_is_not_creation_undo(app_paths):
    _,_,_,_,_,space,tools=fixture(app_paths);m=tools.memories
    args=dict(text='喜欢摄影',subject_key='photo',kind='preference',scope_kind='space',scope_id=space['id'])
    saved=m.save_explicit(**args,operation_key='original')
    m.save_explicit(**args,operation_key='again')
    with pytest.raises(AssistantConflict):m.undo_created(saved['id'],save_operation_key='again',expected_version=1,operation_key='undo-again')
    assert m.get(saved['id'])['status']=='active'


def test_repeat_failed_call_finishes_early_but_changed_work_is_allowed(app_paths):
    from test_assistant_k import setup,start_run,graph_for,AnswerProvider
    _,_,_,store,_,tools,space,_=setup(app_paths)
    run=start_run(store,space,'继续处理我的操作')
    class BadProvider(AnswerProvider):
        def turn(self,**kwargs):
            self.requests.append(kwargs)
            if not kwargs['tools']:return ModelTurn(text='保存没有完成，参数仍不正确。')
            return ModelTurn(text='',tool_calls=[NativeToolCall(call_id=f'bad{len(self.requests)}',name='knowledge_save_discussion',arguments={'topics':[]})])
    provider=BadProvider();graph=graph_for(store,tools,provider)
    asyncio.run(graph.run(run))
    assert store.get_run(run['id'])['status']=='completed'
    assert len(provider.requests)<=4
    # The last native batch was intentionally not executed after repeated errors.
    # Its incomplete protocol cannot be sent to a final model; use program progress.
    assert not [r for r in provider.requests if not r['tools']]
    assert store.pending_tool_batch(run['id'])
    assert not tools.wiki.list_pages(space_id=space['id'])
    assert '不能可靠' in store.get_thread(run['thread_id'])['messages'][-1]['content']
    assert store.get_run(run['id'])['working_state']['execution_budget']['model_calls']==len(provider.requests)


def test_bare_dsml_is_not_official_answer(app_paths):
    from test_assistant_k import setup,start_run,graph_for,AnswerProvider
    _,_,_,store,_,tools,space,_=setup(app_paths)
    run=start_run(store,space,'翻译以下：hello')
    class ProtocolProvider(AnswerProvider):
        def turn(self,**kwargs):return ModelTurn(text='<｜｜DSML｜｜ calls><｜｜DSML｜｜ invoke name="search_knowledge">')
    graph=graph_for(store,tools,ProtocolProvider());asyncio.run(graph.run(run))
    assert store.get_run(run['id'])['status']=='failed'
    assert not any(m['role']=='assistant' for m in store.get_thread(run['thread_id'])['messages'])
    assert not graph._bare_tool_protocol('协议示例：\n```text\n<｜｜DSML｜｜ calls>\n```')


def test_delivered_context7_document_is_distinct_from_video_metadata(app_paths):
    db,_,_,store,_,space,tools=fixture(app_paths)
    run,_=_run(store,space['id'],'保存这份公开文档')
    url='https://example.org/official-doc'
    store.begin_tool_call(run['id'],ordinal=1,call_id='docs',name='context7_query_docs',arguments={})
    store.finish_tool_call(run['id'],call_id='docs',result={'status':'ok','items':[{'text':url}]})
    ref=f"run-result:{run['id']}:docs"
    with db.connect() as c:
        w=json.loads(c.execute('SELECT working_state_json FROM assistant_runs WHERE id=?',(run['id'],)).fetchone()[0])
        w['model_delivered_materials']=[{'source_ref':ref,'kind':'context7_query_docs','view':'公开文档','projection':'工具正文'}]
        c.execute('UPDATE assistant_runs SET working_state_json=? WHERE id=?',(json.dumps(w),run['id']))
    topic={'title':'公开文档','purpose':'保留官方说明','blocks':[{'role':'source','heading':'说明','markdown':'文档的条件说明','external_sources':[{'url':url,'result_ref':ref}]}]}
    saved=execute(tools,store,run,{'topics':[topic]})
    assert saved['status']=='ok',saved


def test_identical_failed_topic_does_not_create_progress_versions(app_paths):
    _,_,_,store,_,space,tools=fixture(app_paths)
    run,_=_run(store,space['id'],'保存主题')
    topic=_topics()[0];topic['blocks'][0]['role']='source'
    plan=execute(tools,store,run,{'topics':[topic]})['items'][0]
    args={'plan_id':plan['id'],'expected_version':plan['version'],'replacements':[{'index':0,'topic':topic}]}
    first=execute(tools,store,run,args,'first')['items'][0]
    args['expected_version']=first['version']
    second=execute(tools,store,run,args,'second')['items'][0]
    assert first['version']==second['version']


def test_legacy_protocol_answer_cannot_become_new_save_target(app_paths):
    _,_,_,store,wiki,space,tools=fixture(app_paths)
    prior,answer=formal(store,space,'<｜｜DSML｜｜ calls><｜｜DSML｜｜ invoke name="search_knowledge">')
    run,_=_run(store,space['id'],'保存成果',thread_id=prior['thread_id'],key='save-protocol')
    result=execute(tools,store,run,{'answer_message_ids':[answer['id']],'topics':[_topics()[0]]})
    assert result['error_code']=='save_answer_contains_tool_protocol'
    assert not wiki.list_pages(space_id=space['id'])


def test_unknown_failed_call_has_stable_error_and_no_guess(app_paths):
    _,_,_,store,wiki,space,tools=fixture(app_paths)
    run,_=_run(store,space['id'],'再试一下')
    result=execute(tools,store,run,{'resume_result_ref':'run-result:missing:call','topics':[_topics()[0]]})
    assert result['error_code']=='save_reference_not_found'
    assert not wiki.list_pages(space_id=space['id'])


def test_chained_schema_failures_keep_original_ui_target_and_request(app_paths):
    _,_,_,store,wiki,space,tools=fixture(app_paths)
    research,answer=formal(store,space)
    first=store.create_run(research['thread_id'],text='保存所点成果',request_id='clicked',answer_message_id=answer['id'])
    persisted(tools,store,first,{'topics':[]})
    second,_=_run(store,space['id'],'再试一下',thread_id=first['thread_id'],key='second')
    persisted(tools,store,second,{'topics':[],'resume_result_ref':f"run-result:{first['id']}:save"})
    third,_=_run(store,space['id'],'继续原来的成果',thread_id=first['thread_id'],key='third')
    result=execute(tools,store,third,{'topics':[_topics()[0]],'resume_result_ref':f"run-result:{second['id']}:save"})
    assert result['status']=='ok',result
    binding=result['items'][0]['payload']['save_request']
    assert binding['answer_message_ids']==[answer['id']]
    assert binding['source_message_id']==store.knowledge_save_request(first['id'])['source_message_id']
    assert len(wiki.list_discussion_plans(space_id=space['id']))==1


def test_bad_unplanned_target_can_be_corrected_to_user_expression(app_paths):
    _,_,_,store,_,space,tools=fixture(app_paths)
    first,ctx=_run(store,space['id'],'保存我的偏好：喜欢餐蛋面',key='first')
    quote_id=ctx['thread']['messages'][-1]['id']
    persisted(tools,store,first,{'topics':[],'answer_message_ids':['wrong-answer']})
    next_run,_=_run(store,space['id'],'就保存这个偏好',thread_id=first['thread_id'],key='retry')
    result=execute(tools,store,next_run,{'resume_result_ref':f"run-result:{first['id']}:save",'answer_message_ids':[],
        'user_message_ids':[quote_id],'topics':[_topics()[0]]})
    assert result['status']=='ok',result
    assert result['items'][0]['payload']['save_request']['answer_message_ids']==[]


def test_failed_saves_do_not_stop_a_real_history_read(app_paths):
    from test_assistant_k import setup,start_run,graph_for,AnswerProvider
    _,_,_,store,_,tools,space,_=setup(app_paths)
    run=start_run(store,space,'继续处理原请求')
    class RecoverProvider(AnswerProvider):
        def turn(self,**kw):
            self.requests.append(kw)
            n=len(self.requests)
            if n<=2:return ModelTurn(text='',tool_calls=[NativeToolCall(call_id=f'bad{n}',name='knowledge_save_discussion',arguments={'topics':[]})])
            if n==3:return ModelTurn(text='',tool_calls=[NativeToolCall(call_id='real-read',name='conversation_history',arguments={})])
            return ModelTurn(text='已核对消息，仍需更正候选。')
    provider=RecoverProvider();asyncio.run(graph_for(store,tools,provider).run(run))
    with store.db.connect() as c:
        row=c.execute("SELECT status FROM assistant_tool_calls WHERE run_id=? AND call_id='real-read'",(run['id'],)).fetchone()
    assert row and row[0]=='completed'
    assert all(request['tools'] for request in provider.requests)


def test_memory_creation_undo_keeps_previous_real_forget_protection(app_paths):
    _,_,_,store,_,space,tools=fixture(app_paths);m=tools.memories
    old,ctx=_run(store,space['id'],'我喜欢餐蛋面',key='old')
    old_id=ctx['thread']['messages'][-1]['id']
    common=dict(text='我喜欢餐蛋面',subject_key='food',kind='preference',scope_kind='space',scope_id=space['id'])
    first=m.save_explicit(**common,operation_key='old-save',source_message_ids=[old_id])
    m.forget(first['id'],expected_version=1,operation_key='genuine-forget')
    new,ctx=_run(store,space['id'],'现在明确重新记住这条偏好',thread_id=old['thread_id'],key='new')
    new_id=ctx['thread']['messages'][-1]['id']
    recreated=m.save_explicit(**common,operation_key='new-save',source_message_ids=[new_id])
    m.undo_created(recreated['id'],save_operation_key='new-save',expected_version=1,operation_key='retract-new')
    suppressed=m.suppressed_source_message_ids(space_id=space['id'])
    assert old_id in suppressed and new_id not in suppressed


def test_preview_confirmation_cannot_use_another_threads_plan(app_paths):
    _,_,_,store,wiki,space,tools=fixture(app_paths)
    first,_=_run(store,space['id'],'先看一页草案',key='proposal')
    proposed=execute(tools,store,first,{'topics':[_topics()[0]]},name='knowledge_propose')['items'][0]
    other,_=_run(store,space['id'],'就这样存吧',key='other-thread')
    rejected=execute(tools,store,other,{'plan_id':proposed['id'],'expected_version':proposed['version'],'accept':True},name='knowledge_confirm')
    assert rejected['error_code']=='knowledge_plan_request_mismatch'
    assert not wiki.list_pages(space_id=space['id'])
