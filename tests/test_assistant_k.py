from __future__ import annotations

from assistant_offline_provider import offline_provider

import asyncio
import json
from types import SimpleNamespace

import numpy as np
import pytest

from shiliu.assistant.contracts import KnowledgeSearchArgs
from shiliu.assistant.memory import MemoryService
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.assistant.wiki_retrieval import WikiHybridIndex
from test_assistant_stage_c import _services, _add_material
from test_assistant_upgrade_d import _message_id


class FakeEmbedding:
    dimension = 4
    def __init__(self):
        self.documents = 0
        self.instructions = []
    def model_identity(self):
        return SimpleNamespace(model_id='isolated-fake', dimension=4)
    def count_tokens(self, text, **kwargs):
        return len(text)
    def truncate_text(self, text, count):
        return text[:count]
    def vector(self, text):
        result = np.array([1., '摄影' in text or '拍照' in text, 'Qwen' in text, '长块尾部' in text], dtype=np.float32)
        return result / np.linalg.norm(result)
    def embed_documents(self, texts):
        self.documents += len(texts)
        return [self.vector(text) for text in texts]
    def embed_query(self, text, *, instruction=None):
        self.instructions.append(instruction)
        return self.vector(text)


def setup(app_paths):
    db, artifacts, sources, store, wiki = _services(app_paths)
    provider = FakeEmbedding()
    wiki.retrieval = WikiHybridIndex(provider, app_paths.state_dir / 'wiki-cache.sqlite3')
    registry = AssistantToolRegistry(sources=sources, memories=MemoryService(db), store=store, wiki=wiki)
    space = store.create_space(name='K isolated', all_active=True)
    return db, artifacts, sources, store, wiki, registry, space, provider


def call(registry, store, run, name, arguments, **kwargs):
    return asyncio.run(registry.execute(name=name, arguments=arguments, call_id=kwargs.pop('call_id', 'k-call'),
                                       run_context=store.run_context(run['id']), **kwargs))


def test_hybrid_read_long_personal_cache_and_version(app_paths):
    db, _, _, store, wiki, registry, space, provider = setup(app_paths)
    message = _message_id(store, space['id'], '保存我的经验：摄影时先找侧光')
    page = wiki.save_discussion(space_id=space['id'], title='Qwen 与摄影', purpose='有效块定位',
        blocks=[{'role':'personal', 'heading':'摄影经验', 'markdown':'摄影时先找侧光', 'user_quote':'摄影时先找侧光'},
                {'role':'analysis', 'heading':'长文', 'markdown':'开头内容。' * 180 + '长块尾部精确名称 Qwen3-Embedding'}],
        source_message_id=message, operation_key='k-page')
    run = store.create_run(store.create_thread(space['id'])['id'], text='拍照有哪些经验，长块尾部 Qwen3-Embedding', request_id='k')
    found = call(registry, store, run, 'search_knowledge', {'query':'长块尾部 Qwen3-Embedding', 'sources':['wiki']})
    assert found['status'] == 'ok'
    candidate = found['items'][0]['candidates'][0]
    assert candidate['page_id'] == page['id'] and candidate['page_version'] == page['version']
    long_hit = next(hit for hit in candidate['hits'] if hit['heading'] == '长文')
    assert long_hit['position']['start'] > 0 and 'Qwen3-Embedding' in long_hit['candidate_excerpt']
    read = call(registry, store, run, 'knowledge_read', {'page_id':page['id'], 'page_version':page['version'], 'block_ids':[long_hit['block_id']]})
    assert 'Qwen3-Embedding' in read['items'][0]['blocks'][0]['markdown']
    count = provider.documents
    personal = call(registry, store, run, 'search_knowledge', {'query':'拍照时如何选择光线', 'sources':['wiki']})
    assert any(hit['role'] == 'personal' for hit in personal['items'][0]['candidates'][0]['hits'])
    assert provider.documents == count
    wiki.retrieval = WikiHybridIndex(provider, app_paths.state_dir / 'wiki-cache.sqlite3')
    assert call(registry, store, run, 'search_knowledge', {'query':'拍照', 'sources':['wiki']})['status'] == 'ok'
    assert provider.documents == count
    assert 'personal' in provider.instructions[0]
    wiki.edit_block(page['id'], block_id=long_hit['block_id'], markdown='新内容', expected_version=page['version'], operation_key='k-edit')
    stale = call(registry, store, run, 'knowledge_read', {'page_id':page['id'], 'page_version':page['version'], 'block_ids':[long_hit['block_id']]})
    assert stale['error_code'] == 'knowledge_page_version_changed'
    assert call(registry, store, run, 'collection_search', {'query':'摄影'})['error_code'] == 'retired_tool'


@pytest.mark.parametrize('change', ['deleted', 'archived', 'page_archived', 'scope', 'memory'])
def test_old_vectors_never_admit_invalid_blocks(app_paths, change):
    db, artifacts, sources, store, wiki, registry, space, provider = setup(app_paths)
    source = db.create_favorite_source(folder_id=99, folder_title='K', history_policy='all')
    video = _add_material(db, artifacts, source, bvid='BV1K00000001', title='摄影', text='摄影侧光')
    ref = f'video:{video}:{sources.snapshots.capture(video).revision}'
    from assistant_context_support import deliver_collection
    research = start_run(store, space, '保存摄影经验', key='deliver-valid')
    message = next(m['id'] for m in store.run_context(research['id'])['thread']['messages'] if m['role'] == 'user')
    deliver_collection(store, registry, research, ref)
    memory = registry.memories.save_explicit(text='侧光', scope_kind='space', scope_id=space['id'], subject_key='k-light', kind='preference', operation_key='k-memory')
    page = wiki.save_discussion(space_id=space['id'], title='摄影', purpose='有效性',
        blocks=[{'role':'analysis', 'heading':'侧光', 'markdown':'摄影侧光', 'source_refs':[ref],
                 'memory_id':memory['id'], 'memory_version':memory['version']}],
        source_message_id=message, operation_key='k-valid')
    run = store.create_run(store.create_thread(space['id'])['id'], text='摄影', request_id='valid')
    found = call(registry, store, run, 'search_knowledge', {'query':'摄影', 'sources':['wiki']})
    assert found['items'][0]['candidates']
    if change == 'deleted':
        blocks = page['blocks']; blocks[0]['deleted'] = True
        with db.connect() as c:
            c.execute('UPDATE assistant_wiki_pages SET blocks_json=? WHERE id=?', (json.dumps(blocks),page['id']))
    elif change == 'page_archived':
        with db.connect() as c:
            c.execute("UPDATE assistant_wiki_pages SET status='archived' WHERE id=?", (page['id'],))
    elif change == 'archived':
        db.set_archived(video, True)
    elif change == 'scope':
        with db.connect() as c:
            c.execute('UPDATE assistant_spaces SET all_active=0,source_ids_json=?,video_ids_json=? WHERE id=?', ('[]','[]',space['id']))
    else:
        registry.memories.correct(memory['id'], text='改为逆光', expected_version=memory['version'], operation_key='k-correct')
    result = call(registry, store, run, 'search_knowledge', {'query':'摄影', 'sources':['wiki']})
    assert not result['items'][0]['candidates']
    read = call(registry, store, run, 'knowledge_read', {'page_id':page['id'], 'page_version':page['version'], 'block_ids':[page['blocks'][0]['stable_id']]})
    assert read['status'] != 'ok'


def test_collection_only_filters_and_partial_source_failure(app_paths, monkeypatch):
    db, artifacts, sources, store, wiki, registry, space, _ = setup(app_paths)
    source = db.create_favorite_source(folder_id=77, folder_title='收藏', history_policy='all')
    _add_material(db, artifacts, source, bvid='BV1K00000002', title='Qwen 精确名称', text='内容')
    run = store.create_run(store.create_thread(space['id'])['id'], text='Qwen', request_id='collection')
    result = call(registry, store, run, 'search_knowledge', {'query':'Qwen', 'sources':['collection'], 'mode':'metadata', 'limit':1})
    assert result['items'][0]['candidates'][0]['title'] == 'Qwen 精确名称'
    assert result['items'][0]['coverage']['mode'] == 'metadata'
    assert call(registry, store, run, 'search_knowledge', {'query':'Qwen', 'uploader':'作者'})['status'] == 'invalid_arguments'
    monkeypatch.setattr(wiki.retrieval, 'search', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('offline')))
    original_search = sources.search
    monkeypatch.setattr(sources, 'search', lambda **kw: original_search(**{**kw, 'mode':'metadata'}))
    both = call(registry, store, run, 'search_knowledge', {'query':'Qwen'})
    assert both['status'] == 'partial' and both['items'][0]['status'] == 'unavailable'
    assert both['items'][1]['source'] == 'collection'
    names = [item['function']['name'] for item in registry.schemas()]
    assert 'search_knowledge' in names and 'collection_search' not in names and 'knowledge_search' not in names

from shiliu.assistant.provider import ModelTurn, NativeToolCall
from shiliu.assistant.runtime import AssistantExecutionGraph


class AnswerProvider:
    def __init__(self):
        self.requests = []
    def turn(self, *, messages, tools, **kwargs):
        self.requests.append(messages)
        return ModelTurn(text='这是基于当前可用材料的回答。')


def graph_for(store, registry, provider):
    from assistant_offline_provider import OfflineRequestProvider
    provider = OfflineRequestProvider(provider)
    return AssistantExecutionGraph(store=store, memories=registry.memories, tools=registry, provider_factory=lambda: offline_provider(provider))


def start_run(store, space, text, *, thread_id=None, key='question'):
    created = store.create_run(thread_id or store.create_thread(space['id'])['id'], text=text, request_id=key)
    claimed = store.claim_next_run()
    assert claimed['id'] == created['id']
    return claimed


def test_bootstrap_after_greeting_no_fake_tool_pair_and_once(app_paths, monkeypatch):
    _, _, _, store, wiki, registry, space, _ = setup(app_paths)
    provider = AnswerProvider()
    graph = graph_for(store, registry, provider)
    greeting = start_run(store, space, '你好')
    asyncio.run(graph.run(greeting))
    assert not store.get_run(greeting['id'])['working_state'].get('knowledge_bootstrap')
    run = start_run(store, space, '你好，摄影如何选择光线？', thread_id=greeting['thread_id'], key='knowledge')
    asyncio.run(graph.run(run))
    current = store.get_run(run['id'])
    assert current['status'] == 'completed'
    assert current['working_state']['knowledge_bootstrap']['status'] == 'completed'
    assert 'bootstrap_candidates' in str(provider.requests[-1])
    messages = store.get_thread(run['thread_id'])['messages']
    assert not [message for message in messages if message['role'] == 'tool']
    followup = start_run(store, space, '再说说别的摄影技巧', thread_id=run['thread_id'], key='followup')
    asyncio.run(graph.run(followup))
    with store.db.connect() as c:
        assert c.execute("SELECT COUNT(*) FROM assistant_tool_calls WHERE name='search_knowledge'").fetchone()[0] == 1
    assert all(not message.get('tool_calls') for message in provider.requests[1])
    source_id = current['working_state']['knowledge_bootstrap']['message_id']
    monkeypatch.setattr(registry.memories, 'suppressed_source_message_ids', lambda **kwargs: {source_id})
    fresh = start_run(store,space,'继续核对摄影',thread_id=run['thread_id'],key='suppressed-bootstrap')
    projected = graph.composer.prepare(fresh['id'],provider=graph.provider_factory()).request.body['messages']
    assert 'origin=bootstrap' not in projected[0]['content']



@pytest.mark.parametrize('text', ['谢谢！', '翻译下面：Hello world', '帮我把这段文字改写：Hello world', '保存刚才的讨论成果', '记住我的偏好', '继续'])
def test_explicit_nonknowledge_skips_discovery(text):
    assert AssistantExecutionGraph._discovery_request(text)[0] is False


def test_unresolved_subset_delays_and_scope_quote_cannot_expand(app_paths):
    db, artifacts, sources, store, wiki, registry, space, _ = setup(app_paths)
    source = db.create_favorite_source(folder_id=78, folder_title='K 子集', history_policy='all')
    first = _add_material(db, artifacts, source, bvid='BV1K00000003', title='北京', text='北京内容')
    second = _add_material(db, artifacts, source, bvid='BV1K00000004', title='上海', text='上海内容')
    provider = AnswerProvider()
    graph = graph_for(store, registry, provider)
    run = start_run(store, space, '其他城市不用管，只看这几篇北京资料')
    state = {'run_id': run['id'], 'epoch':run['run_epoch'], 'tool_count':0,'step_count':0,'usage':{}}
    assert asyncio.run(graph._bootstrap_knowledge(state)) is None
    assert not store.get_run(run['id'])['working_state'].get('knowledge_bootstrap')
    assert call(registry,store,run,'task_scope',{'video_ids':[first], 'basis_quote':'不存在的用户原话'})['status'] != 'ok'
    assert call(registry,store,run,'task_scope',{'video_ids':[first], 'basis_quote':'其他城市不用管'})['status'] == 'ok'
    assert call(registry,store,run,'task_scope',{'video_ids':[second], 'basis_quote':'其他城市不用管'})['status'] != 'ok'
    assert asyncio.run(graph._bootstrap_knowledge(state)) is None
    assert store.get_run(run['id'])['working_state']['knowledge_bootstrap']['status'] == 'completed'
    result = store.run_context(run['id'])['bootstrap_results'][0]['result']
    assert result['coverage']['scope']['video_ids'] == [first]
    assert not call(registry,store,run,'collection_read',{'source_ref':f'video:{second}'})['status'] == 'ok'
    store.cancel_run(run['id'])
    next_run=start_run(store,space,'现在改看上海资料',thread_id=run['thread_id'],key='replace-subset')
    assert call(registry,store,next_run,'task_scope',{'video_ids':[second],'basis_quote':'现在改看上海资料'})['status']=='ok'
    assert store.run_context(next_run['id'])['space']['video_ids']==[second]



@pytest.mark.parametrize('action', ['stop', 'finish'])
@pytest.mark.parametrize('origin', ['bootstrap', 'model'])
def test_search_control_does_not_wait_or_deliver_late_candidates(app_paths, monkeypatch, action, origin):
    _, _, _, store, _, registry, space, _ = setup(app_paths)
    class SearchProvider(AnswerProvider):
        def turn(self, **kwargs):
            if origin == 'model' and not self.requests:
                self.requests.append(kwargs['messages'])
                return ModelTurn(text='',tool_calls=[NativeToolCall(call_id='model-search',name='search_knowledge',arguments={'query':'摄影'})])
            return super().turn(**kwargs)
    provider = SearchProvider()
    graph = graph_for(store, registry, provider)
    run = start_run(store, space, '继续' if origin == 'model' else '摄影有什么技巧')
    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()
        original = registry.search_knowledge
        async def blocked(*args, **kwargs):
            started.set()
            await release.wait()
            return await original(*args, **kwargs)
        monkeypatch.setattr(registry, 'search_knowledge', blocked)
        task = asyncio.create_task(graph.run(run))
        await asyncio.wait_for(started.wait(), 2)
        if action == 'stop':
            store.cancel_run(run['id'])
        else:
            store.request_finish(run['id'])
        await asyncio.wait_for(task, 2)
        assert not release.is_set()
        release.set()
        for _ in range(100):
            with store.db.connect() as c:
                if c.execute('SELECT result_json FROM assistant_tool_calls WHERE run_id=?', (run['id'],)).fetchone()[0]:
                    break
            await asyncio.sleep(.02)
    asyncio.run(scenario())
    assert not store.run_context(run['id'])['bootstrap_results']
    with store.db.connect() as c:
        result = json.loads(c.execute('SELECT result_json FROM assistant_tool_calls WHERE run_id=?', (run['id'],)).fetchone()[0])
        assert result['coverage']['discarded'] is True
    if action == 'finish':
        assert store.get_run(run['id'])['status'] == 'completed'
        assert 'origin=bootstrap' not in provider.requests[-1][0]['content']


def test_grouped_material_projection_is_candidate_only():
    result = {'coverage':{'canonical_name':'search_knowledge'}, 'items':[
        {'source':'wiki','source_refs':['video:1:rev'],'candidates':[{'page_id':'awiki_x','page_version':2,'title':'知识',
         'hits':[{'block_id':'stable'}]}]},
        {'source':'collection','candidates':[{'source_ref':'video:1:rev','title':'收藏'}]}]}
    from shiliu.assistant.delivery import read_evidence
    _, materials = read_evidence('search_knowledge', result, result_ref='run-result:run:search')
    assert len(materials) == 2 and all(not item['complete'] and item['view']=='candidate_excerpt' for item in materials)
    assert materials[0]['lineage_refs'] == ['video:1:rev']


def test_bootstrap_receipt_reused_after_checkpoint_interruption(app_paths, monkeypatch):
    _, _, _, store, _, registry, space, _ = setup(app_paths)
    provider = AnswerProvider()
    graph = graph_for(store, registry, provider)
    run = start_run(store, space, '摄影技巧')
    state = {'run_id':run['id'],'epoch':run['run_epoch'],'tool_count':0,'step_count':0,'usage':{}}
    asyncio.run(graph._bootstrap_knowledge(state))
    marker = store.get_run(run['id'])['working_state']['knowledge_bootstrap']
    store.set_knowledge_bootstrap(run['id'], epoch=run['run_epoch'], value={**marker, 'status':'running'})
    async def must_not_search(*args, **kwargs):
        raise AssertionError('completed receipt was searched again')
    monkeypatch.setattr(registry, 'search_knowledge', must_not_search)
    asyncio.run(graph.run(store.get_run(run['id'])))
    assert store.get_run(run['id'])['status'] == 'completed'
    assert store.get_run(run['id'])['tool_count'] == 1
    with store.db.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM assistant_tool_calls WHERE run_id=?',(run['id'],)).fetchone()[0] == 1


def test_old_pending_replays_only_predeployment_identity_and_receipt_reads(app_paths):
    db, artifacts, sources, store, _, registry, space, _ = setup(app_paths)
    source = db.create_favorite_source(folder_id=33, folder_title='历史兼容', history_policy='all')
    _add_material(db, artifacts, source, bvid='BV1K00000005', title='摄影', text='正文')
    run = start_run(store, space, '继续')
    old_args = {'mode':'metadata','query':'摄影'}
    store.save_assistant_tool_message(run['id'],content='',provider_payload={'tool_calls':[
        {'id':'old-pending','type':'function','function':{'name':'collection_search','arguments':json.dumps(old_args)}}]})
    provider = AnswerProvider()
    graph = graph_for(store,registry,provider)
    asyncio.run(graph.run(run))
    assert store.get_run(run['id'])['status'] == 'completed'
    ref = f"run-result:{run['id']}:old-pending"
    recovered = store.resolve_run_result(ref,current_thread_id=run['thread_id'],current_scope_version=space['scope_version'])
    assert recovered['name'] == 'collection_search' and recovered['result']['coverage']['canonical_name'] == 'search_knowledge'
    assert recovered['result']['items'][0]['candidates'][0]['title'] == '摄影'
    read = call(registry,store,run,'run_read_result',{'result_ref':ref,'item_index':0,'candidate_index':0,'field':'title'})
    assert read['status'] == 'ok' and read['items'][0]['value'] == '摄影'
    # A new old-name call cannot gain authorization merely by being persisted and restarted.
    next_run = start_run(store,space,'继续',thread_id=run['thread_id'],key='new-old-call')
    store.save_assistant_tool_message(next_run['id'],content='',provider_payload={'tool_calls':[
        {'id':'new-old','type':'function','function':{'name':'collection_search','arguments':json.dumps(old_args)}}]})
    asyncio.run(graph_for(store,registry,provider).run(next_run))
    forbidden = store.resolve_run_result(f"run-result:{next_run['id']}:new-old",current_thread_id=run['thread_id'],current_scope_version=space['scope_version'])
    assert forbidden['result']['error_code'] == 'retired_tool'


def test_search_read_composer_model_delivery_chain(app_paths):
    _, _, _, store, wiki, registry, space, _ = setup(app_paths)
    run = start_run(store,space,'摄影时如何选择光线？')
    user = next(item for item in store.run_context(run['id'])['thread']['messages'] if item['role']=='user')
    page = wiki.save_discussion(space_id=space['id'],title='摄影条件',purpose='隔离验证',source_message_id=user['id'],operation_key='chain',
        blocks=[{'role':'analysis','heading':'侧光','markdown':'侧光能突出纹理，阴天需要重新观察光线。'}])
    class ReadProvider(AnswerProvider):
        def turn(self, *, messages, tools, **kwargs):
            self.requests.append(messages)
            if len(self.requests)==1:
                assert 'bootstrap_candidates' in str(messages) and 'candidate_only' in str(messages)
                return ModelTurn(text='',tool_calls=[NativeToolCall(call_id='read-block',name='knowledge_read',arguments={
                    'page_id':page['id'],'page_version':page['version'],'block_ids':[page['blocks'][0]['stable_id']]})])
            assert any(message['role']=='tool' and '阴天需要重新观察光线' in message['content'] for message in messages)
            return ModelTurn(text='根据知识页，侧光能突出纹理；阴天仍需重新观察光线。')
    provider = ReadProvider()
    asyncio.run(graph_for(store,registry,provider).run(run))
    current=store.get_run(run['id'])
    assert current['status']=='completed' and len(provider.requests)==2
    materials=current['working_state']['model_delivered_materials']
    assert any(material['view']=='candidate_excerpt' and not material['complete'] for material in materials)
    assert any(material['kind']=='knowledge_read' and material['position']['block_ids']==[page['blocks'][0]['stable_id']] for material in materials)
    assert not any(material['kind']=='collection_read' for material in materials)


def test_context7_stays_independent_and_private_arguments_rejected(app_paths):
    _, _, _, store, _, registry, space, _ = setup(app_paths)
    class Context7:
        tools={'context7_resolve_library_id':{'inputSchema':{'type':'object','properties':{'query':{'type':'string'}}}}}
        def __init__(self): self.calls=[]
        async def call(self,name,arguments):
            self.calls.append((name,arguments));return {'content':[{'type':'text','text':'公开文档'}]}
    registry.context7=Context7()
    run=store.create_run(store.create_thread(space['id'])['id'],text='查公开文档',request_id='context7')
    assert 'context7_resolve_library_id' in [schema['function']['name'] for schema in registry.schemas()]
    assert call(registry,store,run,'context7_resolve_library_id',{'query':'FastAPI'})['status']=='ok'
    assert call(registry,store,run,'context7_resolve_library_id',{'query':'video:1:私密字幕'})['status']!='ok'
    assert len(registry.context7.calls)==1


@pytest.mark.parametrize('legacy', ['knowledge_search', 'knowledge_read'])
def test_old_wiki_pending_uses_current_hybrid_or_stable_read(app_paths, legacy):
    _, _, _, store, wiki, registry, space, _ = setup(app_paths)
    run=start_run(store,space,'继续')
    user=next(item for item in store.run_context(run['id'])['thread']['messages'] if item['role']=='user')
    page=wiki.save_discussion(space_id=space['id'],title='摄影',purpose='旧调用恢复',source_message_id=user['id'],operation_key='old-wiki',
        blocks=[{'role':'analysis','heading':'侧光','markdown':'摄影侧光能够突出纹理。'}])
    args={'query':'侧光'} if legacy=='knowledge_search' else {'page_id':page['id'],'mode':'relevant','query':'侧光'}
    store.save_assistant_tool_message(run['id'],content='',provider_payload={'tool_calls':[
        {'id':'old-wiki','type':'function','function':{'name':legacy,'arguments':json.dumps(args)}}]})
    asyncio.run(graph_for(store,registry,AnswerProvider()).run(run))
    assert store.get_run(run['id'])['status']=='completed'
    restored=store.resolve_run_result(f"run-result:{run['id']}:old-wiki",current_thread_id=run['thread_id'],current_scope_version=space['scope_version'])['result']
    assert restored['status']=='ok'
    if legacy=='knowledge_search':
        assert restored['items'][0]['candidates'][0]['page_id']==page['id']
    else:
        assert restored['items'][0]['blocks'][0]['stable_id']==page['blocks'][0]['stable_id']
        assert restored['coverage']['mode']=='block'
