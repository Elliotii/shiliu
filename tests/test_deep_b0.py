"""Integration boundaries with real Graph/Store and deterministic provider transports."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import httpx
import pytest
from test_deep_v2 import _span, _state, _continue, _finish, Provider
from shiliu.ask.deep.v2 import DeepV2Graph, QueryReduction
from shiliu.ask.deep.batch_reduce import BatchReduction, project, snapshots, union, choose
from shiliu.ask.deep.jev import JevClient, JevBatchError, MODEL
from shiliu.config import AppConfig, load_config, save_config

class Jev:
    def __init__(self, fail=False): self.fail, self.calls = fail, 0
    def score(self, snapshots, **kwargs):
        self.calls += 1
        kwargs['on_dispatch']()
        records = [{'role':'jev_score','usage':{'input_tokens':50},'model_response':MODEL}]
        if self.fail: raise JevBatchError('injected partial failure', records)
        return {s['id']:{c['evidence_ref']:1 for c in s['candidates']} for s in snapshots}, records

class BatchProvider(Provider):
    def __init__(self, decisions, invalid=False): super().__init__(decisions); self.invalid=invalid
    def generate_structured(self, **kwargs):
        if kwargs['response_schema'] is not BatchReduction: return super().generate_structured(**kwargs)
        self.calls.append(kwargs)
        payload=json.loads(kwargs['messages'][-1]['content'])
        # First query deliberately cites a chunk retrieved only for the other query.
        ref=next(c['evidence_ref'] for c in payload['candidates'] if 'only-b' in c['quote'])
        output={'findings':[{'subject':'source','text':'cross query finding',
            'evidence_refs':['bogus' if self.invalid else ref],
            'query_ids':[q['query_id'] for q in payload['queries']]}],
            'query_assessments':[{'query_id':q['query_id'],'sufficient':True,'unresolved':[]} for q in payload['queries']]}
        return SimpleNamespace(output=BatchReduction.model_validate(output),usage={'prompt_tokens':100,'completion_tokens':10},latency_ms=1)

def setup(queries=('a','b'), strategy='b0', invalid=False, fail=False):
    provider=BatchProvider([_continue(queries), _finish()],invalid)
    jev=Jev(fail)
    spans={'a':(_span('a','only-a'),),'b':(_span('b','only-b'),)}
    graph=DeepV2Graph(provider_factory=lambda _:provider, transcripts=SimpleNamespace(
        search=lambda q,**kw:{'spans':spans.get(q,()),'hits':(),'scope':{}}),
        navigation=None, windows=None, reduce_strategy=strategy, jev=jev)
    state=_state(); state['search_deadline']=time.monotonic()+180;state['total_deadline']=time.monotonic()+240
    return graph,provider,jev,state

def test_cross_query_registration_and_cache_isolation():
    graph,provider,jev,state=setup()
    result=graph.run(state)
    assert set(result['v2_store'])=={'a','b'}
    assert result['v2_query_results'][0]['retained_evidence_refs']==['b']
    assert all('query_reduction' not in cached for cached in result['v2_cache'].values())
    assert not any(key.startswith('_b0_') for cached in result['v2_cache'].values() for key in cached)
    assert len([c for c in provider.calls if c['response_schema'] is BatchReduction])==1
    assert len([c for c in result['usage'] if c.get('role')=='query_reduce'])==1
    assert len([c for c in result['usage'] if c.get('role')=='jev_score'])==1
    assert next(e for e in result['events'] if e['event_type']=='b0_batch')['accepted']
    # Existing independent cache retains its own summary and does not inherit B0.
    result['v2_cache'][next(iter(result['v2_cache']))]['query_reduction']={'findings':[], 'retained_evidence_refs':[], 'provider':{'usage':{}}}
    graph._execute_batch(__import__('shiliu.ask.deep.v2',fromlist=['V2Decision']).V2Decision.model_validate(_continue(('a','b'))).actions,result)
    assert jev.calls==1  # only one eligible cache-free query now

@pytest.mark.parametrize('strategy,queries,remaining', [('s',('a','b'),180),('b0',('a',),180),('b0',('a','empty'),180),('b0',('a','b'),30)])
def test_s_and_ineligible_batches_use_original_reduce(strategy,queries,remaining):
    graph,provider,jev,state=setup(queries,strategy)
    state['search_deadline']=time.monotonic()+remaining
    result=graph.run(state)
    assert jev.calls==0
    assert not any(c['response_schema'] is BatchReduction for c in provider.calls)
    assert all(c.get('query_reduction') for c in result['v2_cache'].values() if c.get('spans'))

@pytest.mark.parametrize('invalid,fail',[(True,False),(False,True)])
def test_failure_falls_back_whole_batch_without_losing_sunk_usage(invalid,fail):
    graph,provider,jev,state=setup(invalid=invalid,fail=fail)
    result=graph.run(state)
    batch=next(e for e in result['events'] if e['event_type']=='b0_batch')
    assert batch['fallback'] and not batch['accepted']
    assert len([c for c in provider.calls if c['response_schema'] is QueryReduction])==2
    assert all(c['query_reduction'].get('provider') for c in result['v2_cache'].values())
    assert len([c for c in result['usage'] if c.get('role')=='jev_score'])==1
    assert len([c for c in result['usage'] if c.get('role')=='query_reduce'])== (3 if invalid else 2)
    assert not result['errors']

def test_same_graph_concurrent_runs_keep_callbacks_and_state_local():
    graph,_,jev,_=setup()
    class Stateless(BatchProvider):
        def generate_structured(self,**kw):
            if kw['role']=='agent_action':
                p=json.loads(kw['messages'][-1]['content'])
                return SimpleNamespace(output=kw['response_schema'].model_validate(_finish() if p['query_results'] else _continue(('a','b'))),usage={},latency_ms=0)
            return super().generate_structured(**kw)
    graph.provider_factory=lambda _:Stateless([])
    def run(i):
        _,_,_,state=setup();state['query']=f'user-{i}'
        events=[]
        result=graph.run(state,event_sink=lambda k,p:events.append((k,p)))
        return result,events
    with ThreadPoolExecutor(max_workers=2) as pool: outputs=list(pool.map(run,range(2)))
    assert all(any(p.get('phase')=='jev_started' for _,p in events) for _,events in outputs)
    assert outputs[0][0]['v2_store'] is not outputs[1][0]['v2_store']
    assert outputs[0][0]['v2_cache'] is not outputs[1][0]['v2_cache']

def test_jev_pinned_http_batch_and_partial_failure_usage():
    candidates=[]
    for i in range(25):
        candidates.append({'evidence_ref':f'c{i}','video_id':1,'title':'title',
            'source_description_for_identity':'','start_time':i,'end_time':i+1,'quote':'text '*100,'rank':i})
    ss=[{'id':'a','user_question':'q','current_query':'a','candidates':candidates}]
    seen=[];phases=[]
    def handler(request):
        body=json.loads(request.content);seen.append(body)
        assert body['model']==MODEL and 1<=len(body['questions'])<=8
        return httpx.Response(200,json={'model':MODEL,'usage':{'input_tokens':10},
            'answers':{k:{'type':'noul','noul':.5} for k in body['questions']}})
    scores,records=JevClient('test',transport=httpx.MockTransport(handler)).score(ss,deadline=time.monotonic()+30,on_dispatch=lambda:phases.append(1))
    assert len(phases)==1 and len(seen)==2 and len(records)==2
    assert scores['a']['c24']==.5
    def bad(request): return httpx.Response(200,json={'model':MODEL,'usage':{'input_tokens':12},'answers':{}})
    with pytest.raises(JevBatchError) as exc:
        JevClient('test',transport=httpx.MockTransport(bad)).score(ss,deadline=time.monotonic()+30)
    assert exc.value.records and all(r['usage']['input_tokens']==12 for r in exc.value.records)
    seen.clear()
    with pytest.raises(JevBatchError):
        JevClient('test',transport=httpx.MockTransport(handler)).score(ss,deadline=time.monotonic()-1)
    assert not seen

def test_config_persistence_override_and_rejection(app_paths,monkeypatch):
    save_config(AppConfig(content_dir=str(app_paths.content_dir),deep_reduce_strategy='b0'),app_paths)
    assert load_config(app_paths).deep_reduce_strategy=='b0'
    monkeypatch.setenv('SHILIU_DEEP_REDUCE_STRATEGY','s')
    assert load_config(app_paths).deep_reduce_strategy=='s'
    with pytest.raises(ValueError): AppConfig(content_dir='.',deep_reduce_strategy='c')

def test_frozen_selection_prompt_schema_and_jev_contract():
    from hashlib import sha256
    from pathlib import Path
    from shiliu.ask.deep.batch_reduce import POLICY, SCHEMA_SHA256, POLICY_SHA256
    from shiliu.ask.deep.jev import C_REL
    f=json.loads((Path(__file__).parent/'fixtures/deep_b0_frozen.json').read_text())
    assert [c['evidence_ref'] for c in choose({'candidates':f['candidates']},'R',f['scores'])]==f['selected_refs']
    assert POLICY_SHA256==f['policy_sha256'] and SCHEMA_SHA256==f['schema_sha256']
    assert C_REL==f['jev_question']

@pytest.mark.parametrize('failure',['input_budget','controller_budget','late','cancelled','partial_search'])
def test_budget_deadline_cancellation_and_partial_search(failure):
    graph,provider,jev,state=setup(('a','b','c') if failure=='partial_search' else ('a','b'))
    if failure=='input_budget':
        graph.transcripts.search=lambda q,**kw:{'spans':(_span(q,'only-'+q+' 字'*30000),),'hits':(),'scope':{}}
    if failure=='partial_search':
        search=graph.transcripts.search
        def partial(q,**kw):
            if q=='c':raise RuntimeError('injected search failure')
            return search(q,**kw)
        graph.transcripts.search=partial
    if failure in {'controller_budget','late'}:
        generate=provider.generate_structured
        now=[0];graph.clock=lambda:now[0];state['search_deadline']=180;state['total_deadline']=240
        def changed(**kw):
            response=generate(**kw)
            if kw['response_schema'] is BatchReduction:
                if failure=='late':now[0]=161
                else:response.output.findings[0].text='x'*80000
            return response
        provider.generate_structured=changed
    if failure=='cancelled':
        cancelled=[False];graph.cancelled=lambda _:cancelled[0]
        score=jev.score
        def stop(*a,**kw):
            output=score(*a,**kw);cancelled[0]=True;return output
        jev.score=stop
    result=graph.run(state)
    batch=next(e for e in result['events'] if e['event_type']=='b0_batch')
    if failure=='partial_search':
        assert batch['accepted'] and len(result['errors'])==1
    elif failure=='cancelled':
        assert result['termination_reason']=='cancelled'
        assert not any(c['role']=='query_reduce' for c in provider.calls)
    else:
        assert batch['fallback'] and not batch['accepted']
        assert len([c for c in provider.calls if c['response_schema'] is QueryReduction])==2


def test_repeated_b0_raw_cache_preserves_no_progress_advice():
    graph,provider,_,state=setup()
    again=_continue(('a','b'))
    for action in again['actions']:action['action_id']+='-again'
    provider.decisions=iter([_continue(('a','b')),again,_finish()])
    result=graph.run(state)
    events=[e for e in result['events'] if e['event_type']=='v2_tool_result']
    assert len(events)==4
    assert all(not e['no_new_result'] for e in events[:2])
    assert all(e['no_new_result'] for e in events[2:])
    assert result['v2_no_progress']==1 and result['v2_repeated_query_advice']

@pytest.mark.parametrize('change',['assessment_duplicate','unknown_query','empty_refs','sufficient_gap'])
def test_shared_output_rejection_is_atomic(change):
    graph,_,_,state=setup();result=graph.run(state)
    batch=next(e for e in result['events'] if e['event_type']=='b0_batch')
    raw=json.loads(json.dumps(batch['raw_output']))
    if change=='assessment_duplicate':raw['query_assessments'][1]=raw['query_assessments'][0]
    if change=='unknown_query':raw['findings'][0]['query_ids']=['unknown']
    if change=='empty_refs':raw['findings'][0]['evidence_refs']=[]
    if change=='sufficient_gap':raw['query_assessments'][0]['unresolved']=['gap']
    actions=__import__('shiliu.ask.deep.v2',fromlist=['V2Decision']).V2Decision.model_validate(_continue(('a','b'))).actions
    results=[{'spans':(result['v2_store'][q],)} for q in ('a','b')]
    with pytest.raises(ValueError):project(snapshots(graph,[0,1],actions,results,result),raw,batch['reference_map'])

def test_product_deep_provider_is_pinned_without_changing_other_routes(app_paths):
    from shiliu.app import Application
    app=Application(app_paths)
    app.provider=lambda role:SimpleNamespace(model='existing-'+role,thinking_enabled=True,reasoning_effort='high',timeout_seconds=600)
    deep=app.deep_v2_provider('query_reduce')
    assert deep.model=='deepseek-v4-flash' and deep.thinking_enabled is False
    assert deep.reasoning_effort is None and deep.timeout_seconds==180
    assert app.provider('assistant').model=='existing-assistant'
    assert app.fast_answer_provider('grounded_answer').model=='existing-grounded_answer_fast'
    assert app.ask_service.deep_service.is_v2
    assert app.ask_service.deep_service.graph.reduce_strategy=='s'
    with app.db.connect() as db:assert db.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0]=='25'

def test_optional_f1_companion_failure_does_not_block_original_sync(app_paths,monkeypatch):
    from shiliu.app import Application
    from shiliu.retrieval.f1 import F1LexicalIndex
    app=Application(app_paths)
    app._deep_lexical_path().write_bytes(b'corrupt test companion')
    monkeypatch.setattr(F1LexicalIndex,'sync_video',lambda *a:(_ for _ in ()).throw(ValueError('injected F1 failure')))
    result=app.retrieval.replace_video(999)
    assert result['video_id']==999 and result['chunk_units']==0
    # The next Deep search fails closed against the invalid companion.
    with pytest.raises(Exception):F1LexicalIndex(app._deep_lexical_path(),app.db.path).validate_source()
