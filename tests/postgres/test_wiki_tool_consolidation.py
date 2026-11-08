"""Real isolated PG, deterministic Writers only; no external calls."""
import asyncio
import pytest
from test_wiki import wiki_parts
from test_assistant_runtime_p0 import runtime_parts
from test_assistant_p2_knowledge_write import Writer, formal_answer
from shiliu.assistant.knowledge_write import accept_save, execute_save, fallback_save
from shiliu.assistant.runtime_contract import AssistantConflict
from shiliu.assistant.tools import AssistantToolRegistry

FACT = '霁桥评审定于2026年11月12日10:00。'


def begin(parts, text):
    db, store, runtime, _, space, _, _ = parts
    thread = store.create_thread(space)
    run = store.create_run(thread['id'], text=text, request_id='new')
    claimed = store.claim_next_run()
    assert claimed['id'] == run['id']
    user = store.get_thread(thread['id'])['messages'][-1]
    context = {'thread': store.get_thread(thread['id']), 'run': store.get_run(run['id']), 'space': store.task_space(thread['id'])}
    return thread['id'], user, context


class PersonalWriter(Writer):
    def __init__(self, user, *, bad_quote=False, analysis=False):
        super().__init__()
        self.user, self.bad_quote, self.analysis = user, bad_quote, analysis

    def generate_json_with_usage(self, **kwargs):
        self.prompts.append(kwargs['messages'])
        return {'topics': [{'title': '霁桥评审', 'purpose': '用户计划', 'blocks': [
            {'role': 'analysis' if self.analysis else 'personal', 'heading': '评审时间', 'markdown': FACT,
             'user_message_id': self.user['id'], 'user_quote': '伪造原话' if self.bad_quote else FACT}]}], 'omitted': []}, {'prompt_tokens': 2, 'completion_tokens': 2, 'total_tokens': 4}


def request(parts, text='请将这项计划保存到知识页：'+FACT):
    thread, user, context = begin(parts, text)
    store, runtime = parts[1:3]
    accepted = accept_save(store, thread_id=thread, answer_message_id=None, request_id='facts',
        requirement=text, user_message_id=user['id'], user_facts=True, wiki=runtime.wiki)
    return thread, user, context, accepted


def test_first_turn_personal_job_commit_and_dedupe(runtime_parts):
    thread, user, context, accepted = request(runtime_parts)
    store, runtime = runtime_parts[1:3]
    again = accept_save(store, thread_id=thread, answer_message_id=None, request_id='different',
        requirement='ignored', user_message_id=user['id'], user_facts=True, wiki=runtime.wiki)
    assert again['id'] == accepted['id']
    job = store.claim_job(owner='wiki-test', kinds={'wiki_save'})
    assert job['payload']['answer_message_id'] is None and job['payload']['user_facts']
    assert user['id'] in job['payload']['history']['message_ids']
    result = execute_save(store, runtime.wiki, PersonalWriter(user), job, max_tokens=8192)
    store.finish_job(job['id'], proposal=result, owner=job['lease_owner'], lease_epoch=job['lease_epoch'])
    page = runtime.wiki.get_page(result['pages'][0]['page_id'])
    assert page['blocks'][0]['markdown'] == FACT
    assert page['blocks'][0]['user_message_id'] == user['id']


@pytest.mark.parametrize('text', [FACT, '请记住这项计划：'+FACT, '先给我草稿，确认后再保存到知识页：'+FACT])
def test_no_wiki_authorization_no_job(runtime_parts, text):
    thread, user, _ = begin(runtime_parts, text)
    with pytest.raises(AssistantConflict, match='explicit_wiki_save_required'):
        accept_save(runtime_parts[1], thread_id=thread, answer_message_id=None, request_id='x', requirement=text,
            user_message_id=user['id'], user_facts=True, wiki=runtime_parts[2].wiki)
    with runtime_parts[0].connect(read_only=True) as c:
        assert c.execute("SELECT count(*) AS n FROM assistant_jobs WHERE kind='wiki_save'").fetchone()['n'] == 0


@pytest.mark.parametrize('mode', ['bad_quote', 'analysis'])
def test_personal_input_cannot_forge_or_become_analysis(runtime_parts, mode):
    _, user, _, _ = request(runtime_parts)
    store, runtime = runtime_parts[1:3]
    job = store.claim_job(owner='wiki-test', kinds={'wiki_save'})
    with pytest.raises(ValueError):
        execute_save(store, runtime.wiki, PersonalWriter(user, **{mode:True}), job, max_tokens=8192)
    assert not runtime.wiki.list_pages(space_id=runtime_parts[4])


@pytest.mark.parametrize('ui_mode',[False,True])
def test_retained_plan_confirmation_queues_original_plan(runtime_parts,ui_mode):
    thread, user, _ = begin(runtime_parts, '请保存知识页：'+FACT)
    store, runtime = runtime_parts[1:3]
    plan = runtime.wiki.propose_discussion(space_id=runtime_parts[4], topics=[{'title':'霁桥评审','purpose':'计划',
        'blocks':[{'role':'personal','heading':'时间','markdown':FACT,'user_quote':FACT,'user_message_id':user['id']}]}],
        omitted=[], source_message_id=user['id'], request_key='historical')
    accepted = accept_save(store, thread_id=thread, answer_message_id=None, request_id='confirm',
        user_message_id=None if ui_mode else user['id'], requirement='确认', wiki=runtime.wiki, confirmed_plan={'id':plan['id'],'version':plan['version']})
    job = store.claim_job(owner='wiki-test', kinds={'wiki_save'})
    class NoWriter:
        def __getattr__(self, name): raise AssertionError('confirmed plan must not generate again')
    result = execute_save(store, runtime.wiki, NoWriter(), job, max_tokens=8192)
    assert result['pages'] and accepted['id'] == job['id']
    store.finish_job(job['id'],proposal=result,owner=job['lease_owner'],lease_epoch=job['lease_epoch'])
    again=accept_save(store,thread_id=thread,answer_message_id=None,request_id='repeat-ui',requirement='确认',
        wiki=runtime.wiki,confirmed_plan={'id':plan['id'],'version':plan['version']})
    assert again['id']==accepted['id']


def test_five_tools_and_update_existing_only(runtime_parts):
    store, runtime = runtime_parts[1:3]
    registry = AssistantToolRegistry(store=store,sources=runtime_parts[6],memories=runtime.memories,wiki=runtime.wiki)
    names = [s['function']['name'] for s in registry.schemas()]
    assert {n for n in names if n.startswith('knowledge_')} == {'knowledge_read','knowledge_save_request','knowledge_update_page','knowledge_save_status'}
    thread, user, context = begin(runtime_parts, '请更新原知识页的计划：'+FACT)
    result = asyncio.run(registry.execute(name='knowledge_update_page', arguments={'page_id':'awiki_missing','expected_version':1,
        'blocks':[{'role':'personal','heading':'时间','markdown':FACT,'user_quote':FACT,'user_message_id':user['id']}]}, call_id='missing',run_context=context))
    assert result['status'] != 'ok'
    assert not runtime.wiki.list_pages(space_id=runtime_parts[4])


@pytest.mark.parametrize('personal', [False,True])
def test_unified_update_uses_writer_original_page_and_version(runtime_parts, wiki_parts, personal):
    store, runtime = runtime_parts[1:3]
    thread, answer = formal_answer(runtime_parts, wiki_parts)
    accepted = accept_save(store, thread_id=thread, answer_message_id=answer, request_id='research', requirement='保存研究', wiki=runtime.wiki)
    initial_job = store.claim_job(owner='wiki-test', kinds={'wiki_save'})
    result = execute_save(store, runtime.wiki, Writer(), initial_job, max_tokens=8192)
    store.finish_job(initial_job['id'],proposal=result,owner=initial_job['lease_owner'],lease_epoch=initial_job['lease_epoch'])
    page = runtime.wiki.get_page(result['pages'][0]['page_id'])
    thread, user, context = begin(runtime_parts,'请更新知识页，补充我的项目计划：'+FACT)
    registry=AssistantToolRegistry(store=store,sources=runtime_parts[6],memories=runtime.memories,wiki=runtime.wiki)
    block = {'role':'personal' if personal else 'analysis','heading':'补充','markdown':FACT}
    if personal:block.update(user_quote=FACT,user_message_id=user['id'])
    args={'page_id':page['id'],'expected_version':page['version'],'blocks':[block]}
    received=asyncio.run(registry.execute(name='knowledge_update_page',arguments=args,call_id='update',run_context=context))
    assert received['status']=='ok'
    assert runtime.wiki.get_page(page['id'])['version']==1  # accepted is not persisted
    job=store.claim_job(owner='wiki-test',kinds={'wiki_save'})
    class UpdateWriter(Writer):
        def generate_json_with_usage(self,**kw):
            self.prompts.append(kw['messages'])
            return {'topics':[{'page_id':page['id'],'title':page['title'],'purpose':'追加','expected_version':1,'blocks':[block]}],'omitted':[]},{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}
    result=execute_save(store,runtime.wiki,UpdateWriter(),job,max_tokens=8192)
    updated=runtime.wiki.get_page(result['pages'][0]['page_id'])
    assert updated['id']==page['id'] and updated['version']==2
    assert any(b['markdown']==FACT for b in updated['blocks'])
    assert len(runtime.wiki.list_pages(space_id=runtime_parts[4]))==1


def test_failed_writer_draft_requeues_without_sync_write_or_regeneration(runtime_parts,wiki_parts):
    store,runtime=runtime_parts[1:3]
    thread,answer=formal_answer(runtime_parts,wiki_parts)
    accepted=accept_save(store,thread_id=thread,answer_message_id=answer,request_id='recover',requirement='保存',wiki=runtime.wiki)
    job=store.claim_job(owner='wiki-test',kinds={'wiki_save'})
    draft={'topics':[{'title':'事务研究','purpose':'复用','blocks':[{'role':'analysis','heading':'边界','markdown':'事务外等待模型'}]}],'omitted':[]}
    store.save_job_proposal(job['id'],{'draft':draft},owner=job['lease_owner'],lease_epoch=job['lease_epoch'])
    store.fail_job(job,code='submission_failed',message='deterministic failure',blocked=True)
    recovered=fallback_save(store,runtime.wiki,job_id=job['id'],thread_id=thread)
    assert recovered['id']==accepted['id'] and recovered['status']=='queued'
    assert not runtime.wiki.list_pages(space_id=runtime_parts[4])
    resumed=store.claim_job(owner='wiki-test',kinds={'wiki_save'})
    class NoWriter:
        def __getattr__(self,name):raise AssertionError('draft must be reused')
    result=execute_save(store,runtime.wiki,NoWriter(),resumed,max_tokens=8192)
    assert len(result['pages'])==1
    store.finish_job(resumed['id'],proposal=result,owner=resumed['lease_owner'],lease_epoch=resumed['lease_epoch'])
    with pytest.raises(AssistantConflict):fallback_save(store,runtime.wiki,job_id=job['id'],thread_id=thread)
    assert runtime.wiki.get_page(result['pages'][0]['page_id'])['version']==1


def test_history_ui_confirm_only_accepts_job(runtime_parts,monkeypatch):
    from shiliu.assistant import api
    thread,user,_=begin(runtime_parts,'请把计划保存到知识页：'+FACT)
    store,runtime=runtime_parts[1:3]
    plan=runtime.wiki.propose_discussion(space_id=runtime_parts[4],source_message_id=user['id'],request_key='ui-history',
        omitted=[],topics=[{'title':'霁桥评审','purpose':'计划','blocks':[{'role':'personal','heading':'时间','markdown':FACT,'user_message_id':user['id'],'user_quote':FACT}]}])
    monkeypatch.setattr(api,'_runtime',lambda req:runtime)
    def no_sync(*args,**kw):raise AssertionError('UI cannot synchronously persist AI content')
    monkeypatch.setattr(runtime.wiki,'decide_discussion_plan',no_sync)
    result=api.decide_knowledge_plan(plan['id'],api.KnowledgePlanDecision(space_id=runtime_parts[4],expected_version=1,accept=True,operation_key='ui-key'),object())
    assert result['job']['status']=='queued'
    assert not runtime.wiki.list_pages(space_id=runtime_parts[4])
    again=api.decide_knowledge_plan(plan['id'],api.KnowledgePlanDecision(space_id=runtime_parts[4],expected_version=1,accept=True,operation_key='other-key'),object())
    assert again['job']['id']==result['job']['id']


def test_metadata_copy_fields_persist_in_isolated_video(runtime_parts):
    db=runtime_parts[0]
    metadata=dict(duration_seconds=256,published_at=1720927800,uploader='冻结作者',description='冻结简介',page_count=1)
    video=db.create_video('BVfixturemetadata','冻结副本')
    db.update_video(video,**metadata)
    persisted=db.get_video(video)
    assert all(persisted[k]==v for k,v in metadata.items())
