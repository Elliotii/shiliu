"""Incremental JSON, real SSE transport, and shared Final safety/delivery ordering."""
from __future__ import annotations

import json
import threading
from types import SimpleNamespace

import httpx
import pytest

from shiliu.ask.contracts import GroundedAnswerDraft, AskRequest
from shiliu.ask.streaming import AnswerJSONStream
from shiliu.domain import PipelineError
from shiliu.llm import OpenAICompatibleProvider
from test_answer_readability import block, draft, evidence, finalize, Provider
from ask_product_fixture import formal

@pytest.mark.parametrize('size', [1, 2, 7, 10000])
def test_complete_values_only_at_every_chunk_boundary(size):
    values=[];invalid=[]
    parser=AnswerJSONStream(lambda *v: values.append(v),lambda:invalid.append(True))
    text=json.dumps(dict(outro='结尾',answer_blocks=[block('**上海**，引号"括号}\\换行\n',["a","b"]),block('第二段',['b'])],intro='引入',status='complete',limitations=[]),ensure_ascii=False)
    for i in range(0,len(text),size):parser.feed(text[i:i+size])
    assert not invalid
    assert [v[2]['text'] for v in values if v[0]=='answer_block']==['**上海**，引号"括号}\\换行\n','第二段']
    assert len([v for v in values if v[0]=='answer_blocks_end'])==1


def test_parser_never_exposes_partial_or_duplicate_top_fields():
    values=[];invalid=[]
    p=AnswerJSONStream(lambda *v:values.append(v),lambda:invalid.append(True))
    p.feed('{"intro":"partial')
    assert not values
    p.feed('" ,"intro":"changed"}')
    assert values==[('intro',None,'partial')] and invalid
    p.feed('garbage')
    assert len(invalid)==1


@pytest.fixture
def stream_provider(monkeypatch):
    monkeypatch.setattr(Provider,'supports_answer_streaming',True,raising=False)


def test_stream_block_arrives_inside_provider_call_before_completion(evidence,stream_provider):
    a,b=[s.citation_id for s in evidence];seen=[]
    output=draft([block('第一段',[a,a]),block('第二段',[b])])
    def generate(kw):
        text=json.dumps(output,ensure_ascii=False)
        split=text.index('},',text.index('"answer_blocks"'))+1
        kw['on_content'](text[:split])
        # Provider is still executing; the first complete block must already exist.
        # Inspect the delivery receiver rather than model TTFT or terminal replay.
        assert published and published[0]['block']['text']=='第一段'
        assert published[0]['block']['citation_ids']==[a]
        seen.append('provider_not_finished')
        kw['on_content'](text[split:]);return output
    published=[]
    # Capture publication synchronously through the callback's owner.
    original=__import__('shiliu.ask.streaming',fromlist=['AnswerStreamDelivery']).AnswerStreamDelivery.emit
    from unittest.mock import patch
    def emit(self,kind,payload):
        if kind=='answer_part' and payload.get('block'):published.append(payload)
        original(self,kind,payload)
    with patch('shiliu.ask.streaming.AnswerStreamDelivery.emit',emit):
        final,p,events=finalize([generate],evidence)
    assert seen and len(p.calls)==1 and len(final.answer_blocks)==2
    kinds=[k for k,v in events]
    assert kinds.index('answer_part') < kinds.index('answer_generation_finished') < kinds.index('minimum_trust_passed')


@pytest.mark.parametrize('bad',['unknown','missing','stale'])
def test_invalid_or_stale_body_never_delivered_early(evidence,stream_provider,bad):
    a=evidence[0].citation_id
    output=draft([block('有效',[a]),block('不能提前显示',[] if bad=='missing' else ['bad' if bad=='unknown' else evidence[1].citation_id])])
    def generate(kw):kw['on_content'](json.dumps(output,ensure_ascii=False));return output
    def current(s):
        if bad=='stale' and s.citation_id==evidence[1].citation_id:raise ValueError('stale')
    final,p,events=finalize([generate,dict(status='insufficient',answer_blocks=[],limitations=['无法支持'])],evidence,current=current)
    assert [v['block']['text'] for k,v in events if k=='answer_part' and v.get('block')]==['有效']
    assert final.status=='partial'
    assert len(p.calls)==(1 if bad=='stale' else 2)


def test_local_repair_preserves_streamed_good_block(evidence,stream_provider):
    a,b=[s.citation_id for s in evidence]
    output=draft([block('好正文',[a]),block('原面馆正文',[a,'placeholder'])])
    def generate(kw):kw['on_content'](json.dumps(output,ensure_ascii=False));return output
    final,p,events=finalize([generate,draft([block('原面馆正文',[a,b])])],evidence)
    assert final.status=='complete' and len(p.calls)==2
    assert 'on_content' not in p.calls[1]
    assert [v['block']['text'] for k,v in events if k=='answer_part' and v.get('block')]==['好正文']
    assert not [v for k,v in events if k=='answer_stream_reset']
    assert final.answer_blocks[0].text=='好正文' and final.answer_blocks[1].text=='原面馆正文'


def test_schema_repair_and_insufficient_retract_attempt(evidence,stream_provider):
    a=evidence[0].citation_id
    invalid=draft([block('临时可用',[a])]);invalid['status']='partial';invalid['limitations']=[]
    def generate(kw):kw['on_content'](json.dumps(invalid,ensure_ascii=False));return invalid
    final,p,events=finalize([generate,dict(status='insufficient',answer_blocks=[],limitations=['证据不足'])],evidence)
    assert final.status=='insufficient' and len(p.calls)==2
    assert final.intro is final.outro is None
    assert 'answer_stream_reset' in [k for k,v in events]


@pytest.mark.parametrize('mode',['fast','deep'])
def test_formal_run_persists_part_while_final_provider_is_blocked(formal,mode):
    core,p,_=formal;p.supports_answer_streaming=True
    real=p.generate_structured;ready=threading.Event();release=threading.Event();errors=[]
    def generate(**kw):
        result=real(**{k:v for k,v in kw.items() if k not in {"on_content","on_reset"}})
        if kw['role']=='grounded_answer' and kw.get('on_content'):
            output=result.output.model_dump(mode='json')
            output['answer_blocks'].append({**output['answer_blocks'][0],'text':'工具结果返回后继续处理。'})
            result.output=GroundedAnswerDraft.model_validate(output)
            text=json.dumps(output,ensure_ascii=False);cut=text.index('},',text.index('"answer_blocks"'))+1
            kw['on_content'](text[:cut]);ready.set()
            if not release.wait(5):raise TimeoutError('test barrier')
            kw['on_content'](text[cut:])
        return result
    p.generate_structured=generate
    request=AskRequest(query='MCP',mode=mode);rid,created=core.ask_service.start_run(request)
    def run():
        try:core.ask_service.execute_started(request,run_id=rid,created_at=created)
        except Exception as exc:errors.append(exc)
    thread=threading.Thread(target=run);thread.start()
    try:
        assert ready.wait(5)
        events=core.ask_service.run_store.get_events(rid)
        assert any(e['event_type']=='answer_part' for e in events)
        assert not any(e['event_type']=='answer_completed' for e in events)
        assert core.ask_service.get_result(rid) is None
    finally:release.set();thread.join(5)
    assert not errors and not thread.is_alive()
    final=core.ask_service.get_result(rid)
    assert final and len(final.answer_blocks)==2
    events=core.ask_service.run_store.get_events(rid)
    assert [e['sequence'] for e in events]==list(range(1,len(events)+1))


def test_actual_sse_transport_uses_same_body_and_collects_usage(monkeypatch):
    output=draft([block('第一段',['a']),block('第二段',['b'])]);text=json.dumps(output,ensure_ascii=False)
    parts=[];done=[];requests=[]
    def event(delta,finish=None,**metadata):
        return ('data: '+json.dumps({'choices':[{'delta':{'content':delta},'finish_reason':finish}],**metadata},ensure_ascii=False)+'\n\n').encode()
    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            for chunk in [text[:60],text[60:120],text[120:]]:
                yield event(chunk)
                assert parts and not done
            yield event('', 'stop',usage={'total_tokens':123},model='deepseek-v4-flash',id='response-1')
            yield b'data: [DONE]\n\n';done.append(True)
    def handle(request):requests.append(json.loads(request.content));return httpx.Response(200,stream=Stream())
    client=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kw:client(transport=httpx.MockTransport(handle),**kw))
    p=OpenAICompatibleProvider(base_url='https://provider.test',api_key='test',model='deepseek-v4-flash',thinking_enabled=False)
    result=p.generate_structured(role='grounded_answer',messages=[{'role':'user','content':'unchanged'}],response_schema=GroundedAnswerDraft,max_tokens=8192,on_content=parts.append)
    assert ''.join(parts)==text and result.output.model_dump()==GroundedAnswerDraft.model_validate(output).model_dump()
    assert result.usage=={'total_tokens':123} and result.response_model=='deepseek-v4-flash'
    assert requests==[{'model':'deepseek-v4-flash','messages':[{'role':'user','content':'unchanged'}], 'thinking':{'type':'disabled'},'temperature':0,'max_tokens':8192,'response_format':{'type':'json_object'},'stream':True,'stream_options':{'include_usage':True}}]


def test_sse_disconnect_retry_resets_and_never_parses_truncated_output(monkeypatch):
    attempts=[];resets=[];parts=[]
    def handle(request):
        attempts.append(True)
        if len(attempts)==1:return httpx.Response(200,content=b'data: {"choices":[{"delta":{"content":"{"},"finish_reason":null}]}\n\n')
        return httpx.Response(200,content=b'data: {"choices":[{"delta":{"content":"{}"},"finish_reason":"stop"}]}\n\n')
    client=httpx.Client;monkeypatch.setattr(httpx,'Client',lambda **kw:client(transport=httpx.MockTransport(handle),**kw))
    p=OpenAICompatibleProvider(base_url='https://provider.test',api_key='test',model='flash')
    with pytest.raises(PipelineError):p.generate_structured(role='grounded_answer',messages=[],response_schema=GroundedAnswerDraft,on_content=parts.append,on_reset=lambda:resets.append(True))
    assert len(attempts)==2 and resets==[True] and parts==['{','{}']


def test_provider_failure_after_a_complete_block_is_not_success(evidence,stream_provider):
    a=evidence[0].citation_id
    def broken(kw):
        kw['on_content'](json.dumps(draft([block('临时正文',[a])]),ensure_ascii=False))
        raise TimeoutError('connection interrupted')
    final,p,events=finalize([broken],evidence)
    assert final.execution_outcome=='generation_failed' and final.status=='insufficient'
    assert not final.answer_blocks and final.intro is final.outro is None
    assert len(p.calls)==1
    assert any(k=='answer_part' for k,v in events)
    assert events[-1][0]=='answer_stream_reset'


def test_source_changes_after_stream_check_still_fail_final_trust(evidence,stream_provider):
    a=evidence[0].citation_id;changed=False
    def current(s):
        if changed:raise ValueError('source changed')
    output=draft([block('原证据正文',[a])])
    def generate(kw):
        nonlocal changed
        kw['on_content'](json.dumps(output,ensure_ascii=False))
        changed=True
        return output
    final,p,events=finalize([generate],evidence,current=current)
    assert final.status=='insufficient' and not final.answer_blocks
    assert len(p.calls)==1 and any(k=='answer_part' for k,v in events)
    assert final.trace['trust_summary']['reason_codes']==['citation_not_current']


def test_status_insufficient_and_all_illegal_citations_never_publish_body(evidence,stream_provider):
    output=dict(status='insufficient',intro='不可显示',outro='不可显示',answer_blocks=[],limitations=['证据不足'])
    def generate(kw):kw['on_content'](json.dumps(output,ensure_ascii=False));return output
    final,p,events=finalize([generate],evidence)
    assert final.status=='insufficient' and not any(k=='answer_part' for k,v in events)
    bad=draft([block('非法',['unknown'])])
    def bad_generate(kw):kw['on_content'](json.dumps(bad,ensure_ascii=False));return bad
    final,p,events=finalize([bad_generate,output],evidence)
    assert len(p.calls)==2 and final.status=='insufficient'
    assert not any(k=='answer_part' for k,v in events)


def test_optional_stream_check_failure_does_not_retry_provider(evidence,stream_provider,monkeypatch):
    import shiliu.ask.streaming as streaming
    a=evidence[0].citation_id;output=draft([block('正式正文',[a])])
    def fail(**kw):raise RuntimeError('optional delivery failure')
    monkeypatch.setattr(streaming,'apply_answer_trust',fail)
    def generate(kw):kw['on_content'](json.dumps(output,ensure_ascii=False));return output
    final,p,events=finalize([generate],evidence)
    assert len(p.calls)==1 and final.status=='complete'
    assert final.trace['answer_stream']['delivery_error'] is True
    assert not any(k=='answer_part' for k,v in events)
