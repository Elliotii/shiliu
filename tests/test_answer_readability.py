"""Shared final-answer contract, local repair safety, and historical Shanghai replay."""
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from shiliu.ask.answer import GroundedAnswerService
from shiliu.ask.context import ContextBuildResult, TranscriptContextBuilder
from shiliu.ask.contracts import GroundedAnswerDraft
from shiliu.ask.finalize import AnswerFinalizer
from test_v4_context_and_citations import _span


class Provider:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        result = self.outputs.pop(0)
        if isinstance(result, Exception):
            raise result
        if callable(result):
            result = result(kwargs)
        return SimpleNamespace(output=GroundedAnswerDraft.model_validate(result),
            usage={}, latency_ms=10)


def draft(blocks, **kw):
    return dict(status='complete', intro='按主题整理如下。', outro='口味因人而异，出行前建议核实。',
        answer_blocks=blocks, limitations=[], **kw)


def block(text, refs):
    return dict(text=text, citation_ids=refs)


@pytest.fixture
def evidence():
    return (_span(texts=('红黑榜推荐松竹香与味香斋。',), ordinals=(0,)),
        _span(texts=('年度榜单推荐阿峰与四如春。',), ordinals=(5,)))


def finalize(outputs, evidence, *, current=lambda span: None, deadline=None,
             clock=lambda: 0, **kw):
    provider = Provider(outputs)
    materializer = SimpleNamespace(validate_current=current)
    service = GroundedAnswerService(lambda role: provider, materializer)
    finalizer = AnswerFinalizer(context_builder=TranscriptContextBuilder(),
        answer_service=service, materializer=materializer)
    events = []
    result = finalizer.finalize(query='上海有什么美食?', normalized_intent='',
        spans=list(evidence), stale_reasons=[], termination_reason='answer_ready',
        prepared_context=ContextBuildResult(tuple(evidence), 'test context',
            tuple(s.citation_id for s in evidence), False, 0),
        deadline=deadline, clock=clock, event_sink=lambda k, v: events.append((k, v)), **kw)
    return result, provider, events


def test_optional_framing_no_repair_and_complete(evidence):
    b=block('推荐松竹香。', [evidence[0].citation_id])
    result, p, events=finalize([draft([b])], evidence)
    assert result.status == 'complete' and len(p.calls) == 1
    assert result.intro and result.outro and not result.limitations
    assert [k for k,v in events].count('minimum_trust_passed') == 1
    old = dict(status='complete', answer_blocks=[b], limitations=[])
    result,p,_=finalize([old],evidence)
    assert result.intro is result.outro is None and len(p.calls)==1


def test_no_positional_exemption(evidence):
    blocks=[block('没有引用的开头',[]),block('正文',[evidence[0].citation_id]),block('没有引用的结尾',[])]
    result,p,_=finalize([draft(blocks),dict(status='insufficient',answer_blocks=[],limitations=['无法支持'])],evidence)
    assert len(p.calls)==2 and len(result.answer_blocks)==1
    assert result.status=='partial'
    assert result.intro and result.outro


def test_local_repair_keeps_other_blocks_and_framing_exact(evidence):
    a,b=[s.citation_id for s in evidence]
    good=block('完整合法正文',[a,b]); bad=block('两个来源共同推荐面馆',[a,'citation_ids_placeholder'])
    result,p,events=finalize([draft([good,bad]),draft([block(bad['text'],[a,b])])],evidence)
    assert result.status=='complete' and len(result.answer_blocks)==2
    assert result.answer_blocks[0].model_dump()==good
    assert result.answer_blocks[1].text==bad['text']
    assert result.intro=='按主题整理如下。' and result.outro=='口味因人而异，出行前建议核实。'
    trace=result.trace['local_citation_repair']
    assert trace['recovered_block_indices']==[1]
    assert result.trace['answer_provider_call_count']==2 and result.trace['repair_calls']==1
    repair=p.calls[1]
    assert repair['timeout_seconds']==30
    failed=json.loads(repair['messages'][-1]['content'].split('Failed original blocks: ')[1])
    assert failed==[bad] and good not in failed
    assert [k for k,v in events].count('minimum_trust_passed')==1


@pytest.mark.parametrize('kind',['invalid','stripped','rewritten','extra','duplicate','timeout','omitted'])
def test_failed_repair_never_loses_valid_original(evidence,kind):
    a,b=[s.citation_id for s in evidence]
    good=block('好正文',[a]);bad=block('待修复正文',[a,'placeholder'])
    patch=block(bad['text'],[a,b])
    outputs={
        'invalid':draft([block(bad['text'],['unknown'])]),
        'stripped':draft([block(bad['text'],[a])]),
        'rewritten':draft([block('新增推荐和价格',[a,b])]),
        'extra':draft([patch,block('额外正文',[a])]),
        'duplicate':draft([patch,block(bad['text'],[b,a])]),
        'timeout':TimeoutError('timeout'),
        'omitted':dict(status='insufficient',answer_blocks=[],limitations=['无法支持']),
    }
    result,p,_=finalize([draft([good,bad]),outputs[kind]],evidence)
    assert len(p.calls)==2
    assert [v.model_dump() for v in result.answer_blocks]==[good]
    assert result.status=='partial' and result.intro and result.outro


def test_all_failed_can_recover_without_rewriting(evidence):
    a=evidence[0].citation_id
    b=block('待修复的原事实',[])
    result,p,_=finalize([draft([b]),draft([block(b['text'],[a])])],evidence)
    assert result.status=='complete' and result.answer_blocks[0].text==b['text']


def test_all_failed_cannot_publish_framing_only(evidence):
    result,p,_=finalize([draft([block('无法支持',[])]),
        dict(status='insufficient',answer_blocks=[],limitations=['无法支持'])],evidence)
    assert result.status=='insufficient' and not result.answer_blocks
    assert result.intro is result.outro is None


def test_insufficient_or_no_evidence_has_no_framing_repair(evidence):
    insufficient=dict(status='insufficient',intro='不应展示',outro='不应展示',answer_blocks=[],limitations=['缺证据'])
    result,p,_=finalize([insufficient],evidence)
    assert len(p.calls)==1 and result.intro is result.outro is None
    result,p,_=finalize([],())
    assert not p.calls and result.status=='insufficient'


def test_deadline_skips_local_repair(evidence):
    times=iter([0,0,.5,.5])
    result,p,_=finalize([draft([block('有效',[evidence[0].citation_id]),block('无引用',[])])],
        evidence,deadline=1,clock=lambda: next(times, .5))
    assert len(p.calls)==1 and result.status=='partial'
    assert result.trace['local_citation_repair']['skipped_reason']=='deadline_exhausted'


def test_stale_source_never_repaired_to_other_source(evidence):
    def current(s):
        if s.citation_id==evidence[1].citation_id: raise ValueError('stale')
    result,p,_=finalize([draft([block('有效',[evidence[0].citation_id]),
        block('失效',[evidence[1].citation_id])])], evidence,current=current)
    assert len(p.calls)==1 and result.status=='partial'
    assert result.trace['trust_summary']['reason_codes']==['citation_not_current']


def test_late_source_change_checked_after_repair(evidence):
    counter=0
    def current(s):
        nonlocal counter
        counter+=1
        if counter>len(evidence): raise ValueError('changed during repair')
    a,b=[s.citation_id for s in evidence]
    result,p,_=finalize([draft([block('原事实',[a,'unknown'])]),
        draft([block('原事实',[a,b])])],evidence,current=current)
    assert len(p.calls)==2 and result.status=='insufficient'
    assert result.intro is result.outro is None


def test_prior_schema_repair_uses_shared_single_repair_budget(evidence):
    a=evidence[0].citation_id
    result,p,_=finalize([dict(status='complete',answer_blocks=[],limitations=[]),
        draft([block('仍然非法',['unknown'])])],evidence)
    assert len(p.calls)==2 and result.status=='insufficient'
    assert result.trace['local_citation_repair']['skipped_reason']=='repair_budget_used'


def test_gaps_still_partial_and_repair_cannot_clear_them(evidence):
    data=draft([block('部分事实',[])])
    data.update(status='partial',limitations=['交通信息未覆盖'])
    result,p,_=finalize([data,draft([block('部分事实',[evidence[0].citation_id])])],evidence)
    assert result.status=='partial' and '交通信息未覆盖' in result.limitations
    data=draft([block('事实',[evidence[0].citation_id])]); data['limitations']=['未覆盖重要问题']
    result,p,_=finalize([data],evidence)
    assert result.status=='partial'
    result,p,_=finalize([draft([block('事实',[evidence[0].citation_id])])],evidence,
        decision_projection={'open_aspects':['未覆盖方面']})
    assert result.status=='partial'


def test_shanghai_original_three_removed_then_new_contract_restores_all():
    fixture=json.loads((Path(__file__).parent/'fixtures/answer_readability/shanghai_deep.json').read_text())
    original=fixture['original_draft']
    spans=tuple(_span(texts=(e['quote'],),ordinals=(i,)).model_copy(update={
        'citation_id':e['citation_id'],'video_id':e['video_id'],'title':e['video_title'],
        'start_time':e['start_time'],'end_time':e['end_time']}) for i,e in enumerate(fixture['evidence']))
    old,p,_=finalize([original,dict(status='insufficient',answer_blocks=[],limitations=['未修复'])],spans)
    assert len(old.answer_blocks)==7
    assert [d['answer_block_id'] for d in old.trace['trust_summary']['dispositions'] if d['outcome']=='remove']==[
        'answer_block_1','answer_block_6','answer_block_10']
    revised=dict(status='complete',intro=original['answer_blocks'][0]['text'],
        outro=original['answer_blocks'][-1]['text'],answer_blocks=original['answer_blocks'][1:-1],limitations=[])
    noodle=revised['answer_blocks'][4]
    refs=[noodle['citation_ids'][0],'citation_v1_02ef456b748947a91bf912d6972a398db8f3c60ddf2b479b7df9f48b586d9878']
    fixed,p,_=finalize([revised,dict(status='complete',answer_blocks=[block(noodle['text'],refs)],limitations=[])],spans)
    assert fixed.status=='complete' and len(fixed.answer_blocks)==8
    assert fixed.intro==original['answer_blocks'][0]['text'] and fixed.outro==original['answer_blocks'][-1]['text']
    assert fixed.answer_blocks[4].citation_ids==refs
    for i,b in enumerate(fixed.answer_blocks): assert b.text==revised['answer_blocks'][i]['text']


@pytest.mark.parametrize('mode',['fast','deep'])
def test_formal_paths_persist_framing_in_result_events_and_draft(formal,mode):
    from shiliu.ask.contracts import AskRequest
    core,provider,_=formal
    real=provider.generate_structured
    def framed(**kw):
        reply=real(**kw)
        if kw['role']=='grounded_answer':
            reply.output=reply.output.model_copy(update={'intro':'自由开头','outro':'自由结尾'})
        return reply
    provider.generate_structured=framed
    result=core.ask_service.ask(AskRequest(query='MCP',mode=mode))
    stored=core.ask_service.get_result(result.run_id)
    assert stored.intro==result.intro=='自由开头' and stored.outro=='自由结尾'
    events=core.ask_service.run_store.get_events(result.run_id)
    completed=next(e['payload'] for e in events if e['event_type']=='answer_completed')
    assert completed['intro']=='自由开头' and completed['outro']=='自由结尾'
    source=core.knowledge_drafts._ask_source(result.run_id)
    assert source['snapshot']['intro']=='自由开头' and source['snapshot']['outro']=='自由结尾'


# Real Application fixture imported for both product modes.
from ask_product_fixture import formal
