from __future__ import annotations

from test_assistant_context_c2 import c2
from test_assistant_context_c3 import c3, history, state_for, notes
from assistant_context_support import mixed_checkpoint

import asyncio
import json

from shiliu.assistant.provider import ModelTurn, NativeToolCall
from assistant_context_support import ContextHarness
from test_assistant_k import setup, start_run, graph_for, AnswerProvider


def test_focus_noop_and_only_one_current_projection(app_paths):
    db, _, _, store, _, registry, space, _ = setup(app_paths)
    run=start_run(store,space,'继续核对这些材料')
    focus={'goal':'核对条件','requirements':['保留未知'],'working_notes':'长稿条件与未知'*30,'selected_source_refs':[], 'next_actions':[]}
    first=store.save_task_focus(run['id'],epoch=run['run_epoch'],focus=focus)
    with db.connect() as c:
        before=c.execute('SELECT working_state_json,updated_at FROM assistant_runs WHERE id=?',(run['id'],)).fetchone()
        before=tuple(before)
    second=store.save_task_focus(run['id'],epoch=run['run_epoch'],focus={**focus,'goal':' 核对条件 '})
    assert first['changed'] and not second['changed']
    with db.connect() as c:
        assert tuple(c.execute('SELECT working_state_json,updated_at FROM assistant_runs WHERE id=?',(run['id'],)).fetchone())==before
    call={'id':'focus-old','type':'function','function':{'name':'task_focus','arguments':json.dumps(focus)}}
    store.save_assistant_tool_message(run['id'],content='',provider_payload={'tool_calls':[call]})
    store.begin_tool_call(run['id'],ordinal=1,call_id='focus-old',name='task_focus',arguments=focus)
    result={'status':'ok','items':[first],'dependency_refs':[],'source_refs':[], 'result_ref':f"run-result:{run['id']}:focus-old"}
    store.finish_tool_call(run['id'],call_id='focus-old',result=result)
    store.save_tool_result_message(run['id'],content=json.dumps(result),provider_payload={'name':'task_focus','tool_call_id':'focus-old'})
    messages,_=ContextHarness(registry.memories).request_messages(store.run_context(run['id']))
    assert json.dumps(messages,ensure_ascii=False).count(focus['working_notes'])==1
    assert any(m.get('name') == 'task_focus' for m in messages)
    assert not any('\"kind\": \"task_focus\"' in m.get('content','') for m in messages if m['role']=='system')


def test_six_focus_rounds_finish_after_feedback_without_extra_schema(app_paths):
    _,_,_,store,_,registry,space,_=setup(app_paths)
    run=start_run(store,space,'继续')
    class FocusProvider(AnswerProvider):
        def turn(self, *,messages,tools,**kwargs):
            self.requests.append(messages)
            if not tools:
                assert len(self.requests)==4
                return ModelTurn(text='根据已完成材料给出部分结论，未验证项保留。')
            n=len(self.requests)
            assert n<=3
            if n==3:
                assert '连续两轮仅维护焦点' in json.dumps(messages,ensure_ascii=False)
            return ModelTurn(text='',tool_calls=[NativeToolCall(call_id=f'focus-{n}',name='task_focus',arguments={
                'goal':f'核对要求 {n}', 'working_notes':'没有新增材料，准备交付'})])
    provider=FocusProvider()
    asyncio.run(graph_for(store,registry,provider).run(run))
    assert store.get_run(run['id'])['status']=='completed'
    with store.db.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM assistant_tool_calls WHERE run_id=? AND name='task_focus'",(run['id'],)).fetchone()[0]==2

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from shiliu.assistant.store import ExecutionBudgetExceeded, AssistantConflict
from shiliu.assistant.task_notes import TaskNoteService
from shiliu.domain import PipelineError


def change_budget(store, run_id, **changes):
    with store.db.connect() as c:
        row=c.execute('SELECT working_state_json FROM assistant_runs WHERE id=?',(run_id,)).fetchone()
        working=json.loads(row[0]);working['execution_budget'].update(changes)
        c.execute('UPDATE assistant_runs SET working_state_json=? WHERE id=?',(json.dumps(working),run_id))


def test_actual_dispatch_token_reserve_unknown_and_late_settle_once(app_paths):
    _,_,_,store,_,registry,space,_=setup(app_paths)
    run=start_run(store,space,'继续')
    store.initialize_execution_budget(run['id'],epoch=run['run_epoch'],model_limit=3,tool_limit=2)
    for _ in range(2):
        store.dispatch_model(run['id'],epoch=run['run_epoch'],final=False,input_tokens=100,output_tokens=4096)
    with pytest.raises(ExecutionBudgetExceeded):
        store.dispatch_model(run['id'],epoch=run['run_epoch'],final=False,input_tokens=100,output_tokens=4096)
    store.record_provider_response(run['id'],ModelTurn(text='',usage={}),late=False,call_id='unknown')
    known={'prompt_tokens':100,'completion_tokens':10,'total_tokens':110,'prompt_cache_hit_tokens':80}
    store.record_provider_response(run['id'],ModelTurn(text='',usage=known),late=True,call_id='late')
    store.record_provider_response(run['id'],ModelTurn(text='',usage=known),late=True,call_id='late')
    store.save_step(run['id'],step_count=0,tool_count=0,usage={})
    current=store.get_run(run['id'])
    assert current['usage']['total_tokens']==110
    assert current['working_state']['execution_budget']['known_tokens']==110
    assert current['working_state']['execution_budget']['unknown_responses']==1
    assert current['working_state']['execution_budget']['model_calls']==2
    change_budget(store,run['id'],known_tokens=1_990_000)
    with pytest.raises(ExecutionBudgetExceeded):
        store.dispatch_model(run['id'],epoch=run['run_epoch'],final=True,input_tokens=2000,output_tokens=8192)
    change_budget(store,run['id'],known_tokens=110)
    store.dispatch_model(run['id'],epoch=run['run_epoch'],final=True,input_tokens=100,output_tokens=8192)
    with pytest.raises(ExecutionBudgetExceeded):
        store.dispatch_model(run['id'],epoch=run['run_epoch'],final=True,input_tokens=100,output_tokens=8192)


def test_deadline_recovery_pause_and_explicit_continue_keep_cost(app_paths):
    _,_,_,store,_,registry,space,_=setup(app_paths)
    run=start_run(store,space,'继续')
    store.initialize_execution_budget(run['id'],epoch=run['run_epoch'])
    store.dispatch_model(run['id'],epoch=run['run_epoch'],final=False,input_tokens=1,output_tokens=1)
    store.record_provider_response(run['id'],ModelTurn(text='',usage={'total_tokens':42}),late=False,call_id='first')
    old_deadline=store.get_run(run['id'])['working_state']['execution_budget']['deadline_at']
    assert store.recover_interrupted_runs()==1
    store.resume_run(run['id']);resumed=store.claim_next_run()
    budget=store.initialize_execution_budget(run['id'],epoch=resumed['run_epoch'])
    assert budget['deadline_at']==old_deadline and budget['model_calls']==1
    store.pause_run(run['id'],code='awaiting_selection',message='等待用户选择')
    remaining=store.get_run(run['id'])['working_state']['execution_budget']['paused_remaining']
    change_budget(store,run['id'],deadline_at=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat())
    store.resume_run(run['id']);resumed=store.claim_next_run()
    assert remaining-2 < store.execution_remaining(run['id'],final=True) <= remaining
    assert store.get_run(run['id'])['working_state']['execution_budget']['model_calls']==1
    store.fail_run(run['id'],code='execution_budget_exhausted',message='已用完本段')
    store.resume_run(run['id']);resumed=store.claim_next_run()
    budget=store.initialize_execution_budget(run['id'],epoch=resumed['run_epoch'])
    assert budget['model_calls']==0 and budget['known_tokens']==0
    assert store.get_run(run['id'])['usage']['total_tokens']==42
    assert store.execution_remaining(run['id'],final=True) <= 300


@pytest.mark.parametrize('remaining,expected', [(59,'completed'),(-1,'budget_exhausted')])
def test_final_reserve_is_inside_300_seconds(app_paths,remaining,expected):
    _,_,_,store,_,registry,space,_=setup(app_paths)
    run=start_run(store,space,'继续')
    store.initialize_execution_budget(run['id'],epoch=run['run_epoch'])
    change_budget(store,run['id'],deadline_at=(datetime.now(timezone.utc)+timedelta(seconds=remaining)).isoformat())
    provider=AnswerProvider()
    asyncio.run(graph_for(store,registry,provider).run(run))
    assert store.get_run(run['id'])['status']==expected
    assert len(provider.requests)==int(remaining>0)
    if provider.requests:
        assert '现在结束探索' in provider.requests[0][-1]['content']


def test_format_repair_counts_dispatch_and_known_failed_usage(app_paths):
    _,_,_,store,_,registry,space,_=setup(app_paths)
    run=start_run(store,space,'继续')
    class RepairProvider(AnswerProvider):
        def turn(self,**kwargs):
            self.requests.append(kwargs['messages'])
            if len(self.requests)==1:
                error=PipelineError('bad json',code='tool_arguments_invalid',retryable=False)
                error.usage={'prompt_tokens':7,'completion_tokens':3,'total_tokens':10}
                raise error
            return ModelTurn(text='已交付',usage={'prompt_tokens':4,'completion_tokens':1,'total_tokens':5})
    provider=RepairProvider()
    asyncio.run(graph_for(store,registry,provider).run(run))
    current=store.get_run(run['id'])
    assert current['status']=='completed' and current['usage']['total_tokens']==15
    assert current['working_state']['execution_budget']['model_calls']==2


def test_compaction_retries_share_the_real_model_budget(c3):
    run, state, _ = history(c3)
    c3.provider.summary = lambda request: ModelTurn('截断候选',[], 'length',{'total_tokens':3})
    c3.provider.main = lambda request: ModelTurn('来源条件未知，不合并为共识。',[], 'stop',{'total_tokens':5})
    output = asyncio.run(c3.graph._model(state))
    assert output['route']=='final' and not notes(c3)
    assert [r.purpose for r in c3.provider.sent]==['compact','turn']
    current = c3.store.get_run(run['id'])
    assert current['working_state']['execution_budget']['model_calls']==2
    assert current['usage']['total_tokens']==current['working_state']['execution_budget']['known_tokens']==8


def test_normal_new_reads_do_not_trigger_focus_finisher(app_paths):
    _,_,_,store,wiki,registry,space,_=setup(app_paths)
    run=start_run(store,space,'继续')
    user=next(item for item in store.run_context(run['id'])['thread']['messages'] if item['role']=='user')
    page=wiki.save_discussion(space_id=space['id'],title='三方条件',purpose='正常补查',source_message_id=user['id'],operation_key='t-reads',blocks=[
        {'role':'analysis','heading':name,'markdown':text} for name,text in [('A','只陈述周期触发'),('B','要求证据条件'),('C','默认行为未知')]])
    class ReadProvider(AnswerProvider):
        def turn(self,*,messages,tools,**kwargs):
            self.requests.append(messages);n=len(self.requests)
            assert tools
            if n==7:
                text=json.dumps(messages,ensure_ascii=False)
                assert all(term in text for term in ['周期触发','证据条件','默认行为未知'])
                return ModelTurn(text='A 周期触发，B 要求证据，C 默认未知；不能合成共识。')
            if n%2:
                call=NativeToolCall(call_id=f'f{n}',name='task_focus',arguments={'goal':'比较三方','working_notes':'补查不同块'})
            else:
                call=NativeToolCall(call_id=f'r{n}',name='knowledge_read',arguments={'page_id':page['id'],'page_version':page['version'],
                   'block_ids':[page['blocks'][n//2-1]['stable_id']]})
            return ModelTurn(text='',tool_calls=[call])
    provider=ReadProvider();asyncio.run(graph_for(store,registry,provider).run(run))
    assert store.get_run(run['id'])['status']=='completed' and len(provider.requests)==7


def test_ordinary_compact_evidence_has_no_eight_item_selector_and_keeps_reread():
    text = '不要保存；只看这几篇；默认行为未知。' + '\n'.join(
        f'来源{i}：条件未知，不等于默认开启；仅有证据时成立。回读 run-result:run:read{i}。'+'长文'*500 for i in range(9))
    note = {'id':'note','note_version':1,'checkpoint':{'format_version':1,'text':text}}
    rendered = TaskNoteService.render(note)
    payload = json.loads(rendered.split('\n',1)[1])
    assert payload['text']==text
    assert all(f'来源{i}' in rendered and f'run-result:run:read{i}' in rendered for i in range(9))
    assert len(payload['text'])>8000


def test_duplicate_read_body_keeps_user_authorization_and_actual_delivery(c3):
    from test_assistant_context_c2 import running, batch, read
    run = running(c3,text='不要保存，只看这篇。')
    for i in range(2): batch(c3,run,[(f'read{i}','collection_read',{},read(c3,f'read{i}'))])
    candidate = c3.composer.prepare(run['id'],provider=c3.provider)
    messages = candidate.request.body['messages']
    assert '不要保存，只看这篇。' in str(messages)
    assert sum('甲乙丙丁条件' in m.get('content','') for m in messages if m['role']=='tool')==2
    assert len(candidate.read_spans)==2


def test_tool_limit_and_expired_mutation_guard(app_paths):
    _, _, _, store, _, _, space, _ = setup(app_paths)
    run = start_run(store, space, '继续')
    store.initialize_execution_budget(run['id'], epoch=run['run_epoch'])
    for _ in range(64):
        store.dispatch_tool(run['id'], epoch=run['run_epoch'])
    with pytest.raises(ExecutionBudgetExceeded):
        store.dispatch_tool(run['id'], epoch=run['run_epoch'])
    assert store.get_run(run['id'])['working_state']['execution_budget']['tool_executions'] == 64
    change_budget(store, run['id'], deadline_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())
    with store.tool_execution_scope(run['id'], run['run_epoch']):
        with pytest.raises(AssistantConflict):
            store.save_task_focus(run['id'], epoch=run['run_epoch'], focus={'goal': '不得迟到写入'})
    assert not store.get_run(run['id'])['working_state'].get('task_focus')


def test_external_document_tool_uses_same_deadline_and_discards_late_result(app_paths):
    _, _, _, store, _, registry, space, _ = setup(app_paths)
    run = start_run(store, space, '继续')
    store.initialize_execution_budget(run['id'], epoch=run['run_epoch'])

    class Documents:
        tools = {}
        async def call(self, name, arguments):
            change_budget(store, run['id'], deadline_at=(datetime.now(timezone.utc)+timedelta(seconds=59)).isoformat())
            await asyncio.sleep(.1)
            return {'text': '迟到文档不进入收尾输入'}

    registry.context7 = Documents()

    class Provider(AnswerProvider):
        def turn(self, *, messages, tools, **kwargs):
            self.requests.append(messages)
            if len(self.requests) == 1:
                return ModelTurn(text='', tool_calls=[NativeToolCall(call_id='doc', name='context7_lookup', arguments={'query': '公开接口'})])
            assert not tools
            assert '迟到文档不进入收尾输入' not in json.dumps(messages, ensure_ascii=False)
            return ModelTurn(text='当前文档未在期限内取回，先交付已知范围。')

    async def check():
        await graph_for(store, registry, Provider()).run(run)
        await asyncio.sleep(.15)

    asyncio.run(check())
    assert store.get_run(run['id'])['status'] == 'completed'
    with store.db.connect() as c:
        receipt = json.loads(c.execute("SELECT result_json FROM assistant_tool_calls WHERE run_id=? AND call_id='doc'", (run['id'],)).fetchone()[0])
    assert receipt['coverage']['discarded']
