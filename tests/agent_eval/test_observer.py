import json
from shiliu.agent_eval import observer
from shiliu.assistant.provider import OpenAICompatibleAssistantProvider


def test_transport_attempt_is_private_and_does_not_change_request(tmp_path, monkeypatch):
    monkeypatch.setenv('SHILIU_EVAL_OBSERVER_DIR', str(tmp_path))
    sent=[]
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'choices': []}
    def fake_post(url, **kwargs):
        sent.append(kwargs['json'])
        return Response()
    monkeypatch.setattr('shiliu.assistant.provider.httpx.post', fake_post)
    provider=OpenAICompatibleAssistantProvider(base_url='https://example.test', api_key='secret', model='fixture')
    body={'messages':[{'role':'user','content':'fixture'}], 'model':'fixture'}
    token=observer.context.set({'run_id':'fixture','dispatch_id':'fixture','call_id':'fixture'})
    try: assert provider._post(body)=={'choices': []}
    finally: observer.context.reset(token)
    assert sent == [body]
    observer._events.join()
    files=list(tmp_path.iterdir())
    assert len(files)==2 and all(p.stat().st_mode & 0o777 == 0o600 for p in files)
    value=next(json.loads(p.read_text()) for p in files if json.loads(p.read_text())['event']=='transport_attempt')
    assert value['event']=='transport_attempt' and value['body']==body
    assert 'secret' not in files[0].read_text()


def test_observer_failure_does_not_escape(monkeypatch):
    monkeypatch.setenv('SHILIU_EVAL_OBSERVER_DIR','/nonexistent/fixture')
    token=observer.context.set({'run_id':'fixture'})
    try: observer.record('prepared_context', body={'fixture':True})
    finally: observer.context.reset(token)


def test_disabled_observer_does_not_construct_candidate(monkeypatch):
    monkeypatch.delenv('SHILIU_EVAL_OBSERVER_DIR',raising=False)
    class Candidate:
        @property
        def request(self): raise AssertionError('must not construct snapshot')
    observer.candidate_snapshot(Candidate())




def test_runtime_stub_preserves_result_and_correlates_late_receipt(tmp_path,monkeypatch):
    import asyncio
    import time
    from types import SimpleNamespace
    from shiliu.assistant.runtime import AssistantExecutionGraph
    monkeypatch.setenv('SHILIU_EVAL_OBSERVER_DIR',str(tmp_path))
    class Store:
        def __init__(self):self.responses=[];self.receipts=[]
        def save_answer_draft(self,*args,**kwargs):pass
        def get_run(self,*args):return {'status':'running','run_epoch':1,'working_state':{}}
        def execution_remaining(self,*args,**kwargs):return 2
        def dispatch_model(self,*args,**kwargs):pass
        def record_provider_response(self,*args,**kwargs):self.responses.append(kwargs)
        def record_model_usage(self,**kwargs):self.receipts.append(kwargs)
        def mark_dispatch_unknown(self,*args):pass
        def release_model_request(self,*args):pass
    graph=AssistantExecutionGraph.__new__(AssistantExecutionGraph);graph.store=Store()
    turn=SimpleNamespace(usage={'total_tokens':7},finish_reason='stop',opaque_provider_state={'response_id':'native-fixture','response_model':'native-model'})
    async def run():
        result=await graph._wait_for_model({'run_id':'run-a','epoch':1},lambda call:turn,dispatch_id='dispatch-a',input_tokens=3,output_tokens=4)
        assert result==('ready',turn)
        error=ValueError('fixture provider failure')
        def fail(call): raise error
        try: await graph._wait_for_model({'run_id':'run-a','epoch':1},fail,dispatch_id='dispatch-error',input_tokens=3,output_tokens=4)
        except ValueError as exc: assert exc is error
        else: raise AssertionError('provider error must propagate unchanged')
        def slow(call):time.sleep(.15);return turn
        result=await graph._wait_for_model({'run_id':'run-a','epoch':1},slow,dispatch_id='dispatch-b',timeout=.01,input_tokens=3,output_tokens=4)
        assert result==('timeout',None)
        await asyncio.sleep(.2)
    asyncio.run(run());observer._events.join()
    events=[json.loads(p.read_text()) for p in tmp_path.iterdir()]
    responses=[e for e in events if e['event']=='response']
    assert {e['dispatch_id'] for e in responses}=={'dispatch-a','dispatch-b'}
    assert any(e['late'] for e in responses)
    assert all(e['identity']['response_model']=='native-model' and e['latency_ms']>=0 for e in responses)
    assert len(graph.store.receipts)==3 and len(graph.store.responses)==3
    assert any(e['event']=='response_error' and e['dispatch_id']=='dispatch-error' for e in events)


def test_stream_attempt_and_native_response_unchanged(tmp_path,monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace
    monkeypatch.setenv('SHILIU_EVAL_OBSERVER_DIR',str(tmp_path))
    bodies=[]
    class Response:
        def raise_for_status(self):pass
        def iter_lines(self):
            yield 'data: '+json.dumps({'id':'native-id','model':'native-model','choices':[{'delta':{'content':'hello'},'finish_reason':'stop'}],'usage':{'total_tokens':5}})
            yield 'data: [DONE]'
    @contextmanager
    def stream(*args,**kwargs):bodies.append(kwargs['json']);yield Response()
    monkeypatch.setattr('shiliu.assistant.provider.httpx.stream',stream)
    provider=OpenAICompatibleAssistantProvider(base_url='https://example.test',api_key='secret',model='fixture')
    body={'model':'fixture','messages':[{'role':'user','content':'fixture'}],'stream':True}
    token=observer.context.set({'run_id':'run-a','dispatch_id':'fixture'})
    try:turn=provider._stream_prepared(SimpleNamespace(body=body),on_text=lambda _:None)
    finally:observer.context.reset(token)
    observer._events.join()
    assert bodies==[body] and turn.text=='hello' and turn.usage=={'total_tokens':5}
    assert turn.opaque_provider_state['response_model']=='native-model'


def test_compaction_records_trigger_accept_and_discard(tmp_path,monkeypatch):
    import asyncio
    from contextlib import nullcontext
    from types import SimpleNamespace
    from shiliu.assistant import runtime
    monkeypatch.setenv('SHILIU_EVAL_OBSERVER_DIR',str(tmp_path))
    class Store:
        db=SimpleNamespace(connect=lambda:nullcontext(None))
        def get_run(self,*args):return {'working_state':{'execution_budget':{'known_tokens':0}}}
        def reserve_model_request(self,**kwargs):return {'budget_date':'fixture','dispatch_id':'dispatch-compact'}
        def execution_remaining(self,*args):return 10
        def record_compaction(self,*args,**kwargs):pass
        def _append_event(self,*args):pass
    graph=runtime.AssistantExecutionGraph.__new__(runtime.AssistantExecutionGraph)
    graph.store=Store();graph._final_reserve_input=lambda *a,**k:0;graph._run_epoch_active=lambda _:True
    graph.composer=SimpleNamespace(persist=lambda *a,**k:None)
    request=SimpleNamespace(body={'max_tokens':5},input_tokens=10)
    provider=SimpleNamespace(prepare_compaction=lambda **kw:request,send_prepared=lambda *a,**kw:SimpleNamespace(text='summary',finish_reason='stop',tool_calls=[],usage={'total_tokens':4}))
    async def wait(state,invoke,**kwargs):
        token=observer.context.set({'run_id':state['run_id'],'dispatch_id':kwargs['dispatch_id'],'call_id':'compact-call'})
        try:return 'ready',invoke('compact-call')
        finally:observer.context.reset(token)
    graph._wait_for_model=wait
    candidate=SimpleNamespace(state={'revision':1},request=SimpleNamespace(input_tokens=100))
    proposed=SimpleNamespace(state={'revision':2,'checkpoint':{'id':'note','version':1}},request=SimpleNamespace(input_tokens=10),budget=SimpleNamespace(fits=True))
    monkeypatch.setattr(runtime,'checkpoint_proposal',lambda *a,**kw:proposed)
    plan=SimpleNamespace(messages=[{'content':'fixture'}])
    result=asyncio.run(graph._compact_once({'run_id':'run-a','epoch':1},candidate=candidate,plan=plan,provider=provider,trigger='hard'))
    assert result==(proposed,None)
    provider.prepare_compaction=lambda **kw:(_ for _ in ()).throw(ValueError('fixture failure'))
    result=asyncio.run(graph._compact_once({'run_id':'run-a','epoch':1},candidate=candidate,plan=plan,provider=provider,trigger='preventative'))
    assert result[0] is None and result[1]['stage']=='prepare'
    observer._events.join();events=[json.loads(p.read_text()) for p in tmp_path.iterdir()]
    accepted=next(e for e in events if e['event']=='compaction_accepted')
    assert accepted['checkpoint']=={'id':'note','version':1}
    assert any(e['event']=='compaction_trigger' and e['compaction_id']==accepted['compaction_id'] for e in events)
    assert any(e['event']=='compaction_discarded' for e in events)


def test_context_snapshot_keeps_knowledge_versions_and_request_hash(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import hashlib
    monkeypatch.setenv('SHILIU_EVAL_OBSERVER_DIR',str(tmp_path))
    body={'model':'fixture','messages':[{'role':'system','content':'Memory v2 fixture; Wiki v3 fixture'}]}
    metadata={'observed_memory_epoch':2,'dependency_refs':['memory:fixture:2','wiki:fixture:3'],'material_projection':[{'kind':'wiki','version':3}],'delivered_read_spans':[{'tool_call_id':'tool-fixture','revision':'v3'}]}
    candidate=SimpleNamespace(request=SimpleNamespace(body=body),metadata=metadata,message_ids=['message-fixture'],state={'revision':4})
    token=observer.context.set({'run_id':'run-a','dispatch_id':'dispatch-a'})
    try:observer.candidate_snapshot(candidate)
    finally:observer.context.reset(token)
    observer._events.join();value=json.loads(next(tmp_path.iterdir()).read_text())
    assert value['body']==body and value['metadata']==metadata
    assert value['request_hash']==hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
