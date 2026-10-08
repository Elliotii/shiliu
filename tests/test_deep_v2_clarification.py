from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from shiliu.app import Application
from shiliu.artifacts import ArtifactStore
from shiliu.ask.context import TranscriptContextBuilder
from shiliu.ask.contracts import AskRequest
from shiliu.ask.deep.service import DeepSearchService, _v2_clarification_requests
from shiliu.ask.finalize import AnswerFinalizer
from shiliu.ask.service import AskService
from shiliu.db import Database
from shiliu.domain import PipelineError
from shiliu.web import create_web_app


FIXTURES = Path(__file__).parent / 'fixtures/deep_v2_clarification'


class RecordedController:
    model = 'offline-recorded-controller'

    def __init__(self, decisions):
        self.decisions = iter(decisions)
        self.roles = []

    def generate_structured(self, **kwargs):
        self.roles.append(kwargs['role'])
        assert kwargs['role'] == 'agent_action', 'no search Reduce or Final call expected'
        return SimpleNamespace(output=kwargs['response_schema'].model_validate(next(self.decisions)),
            usage={}, latency_ms=0)


def _service(tmp_path, provider):
    db = Database(tmp_path / 'state.db')
    db.initialize()
    return DeepSearchService(db=db, artifacts=ArtifactStore(tmp_path / 'videos'),
        product_search=None, provider_factory=lambda _: provider,
        embedding_provider=SimpleNamespace(dimension=512),
        lexical_index_path=tmp_path / 'unused.sqlite')


@pytest.mark.parametrize('case', ['V2-C08', 'V2-C54'])
def test_recorded_failed_clarification_is_delivered_and_persisted(tmp_path, case):
    fixture = json.loads((FIXTURES / f'{case}.json').read_text())
    provider = RecordedController(fixture['decisions'])
    service = _service(tmp_path, provider)
    response, trace = service.ask(AskRequest(query=fixture['query'], mode='deep'))
    assert response.status == 'insufficient'
    assert response.execution_outcome == 'evidence_insufficient'
    assert response.answer_blocks == [] and response.citations == []
    assert trace['v2_outcome'] == 'needs_clarification'
    assert trace['v2_clarification_requests']
    assert trace['finalization']['clarification_requests'] == trace['v2_clarification_requests']
    assert provider.roles == ['agent_action'] * len(fixture['decisions'])
    assert trace['v2_answer_calls'] == []
    text = '\n'.join(response.limitations)
    assert '没有找到可绑定' not in text
    if case == 'V2-C08':
        for field in ['房屋面积', '居住人数', '家具家电', '厨房用品和书籍']:
            assert field in text
        assert '10-20' not in text and '50-100' not in text
    else:
        for field in ['CPU', 'GPU', '内存', '模型', '量化', '流畅']:
            assert field in text
    reader = AskService.__new__(AskService)
    reader.run_store = service.run_store
    reader._candidate_disclosure = lambda _: None
    durable = reader.get_result(response.run_id)
    assert durable.limitations == response.limitations
    assert durable.execution_outcome == 'evidence_insufficient'


def test_clarification_survives_durable_api(app_paths):
    fixture = json.loads((FIXTURES / 'V2-C08.json').read_text())
    provider = RecordedController(fixture['decisions'])
    app = Application(app_paths)
    app.provider = lambda _: provider
    app.deep_answer_provider = lambda _: provider
    client = TestClient(create_web_app(app))
    created = client.post('/api/ask/runs', json={'query': fixture['query'], 'mode': 'deep'})
    assert created.status_code == 202
    result = client.get(f"/api/ask/runs/{created.json()['run_id']}").json()['result']
    assert result['status'] == 'insufficient'
    assert result['execution_outcome'] == 'evidence_insufficient'
    assert '房屋面积' in '\n'.join(result['limitations'])
    assert not result['answer_blocks'] and not result['citations']


@pytest.mark.parametrize('outcome', ['insufficient', 'partial', 'sufficient'])
def test_corpus_gap_is_not_relabelled_user_clarification(tmp_path, outcome):
    provider = RecordedController([{'type': 'finish', 'outcome': outcome,
        'unresolved_items': ['需要知道这条原文是否存在'], 'finish_reason': '没有检索到证据'}])
    response, trace = _service(tmp_path, provider).ask(AskRequest(query='库内内容问题', mode='deep'))
    assert trace['v2_clarification_requests'] == []
    assert response.execution_outcome == 'evidence_unavailable'
    assert response.limitations == ['没有找到可绑定当前字幕版本的有效证据']


def test_controller_failure_is_not_relabelled_user_clarification(tmp_path):
    class FailedProvider:
        def generate_structured(self, **kwargs):
            raise PipelineError('需要提供API服务', code='provider_network', retryable=False)
    response, trace = _service(tmp_path, FailedProvider()).ask(AskRequest(query='问题', mode='deep'))
    assert trace['v2_search_termination_reason'] == 'provider_error'
    assert trace['v2_clarification_requests'] == []
    assert '需要你补充' not in '\n'.join(response.limitations)


@pytest.mark.parametrize('stale,errors,termination', [
    ([], [], 'provider_error'),
    ([], [], 'invalid_structured_output'),
    ([], [], 'timeout'),
    ([], [], 'cancelled'),
])
def test_no_evidence_errors_keep_their_existing_path(stale, errors, termination):
    finalizer = AnswerFinalizer(context_builder=TranscriptContextBuilder(),
        answer_service=SimpleNamespace(), materializer=SimpleNamespace())
    result = finalizer.finalize(query='q', normalized_intent='q', spans=[],
        stale_reasons=stale, retrieval_errors=errors, termination_reason=termination,
        clarification_requests=('电脑型号',))
    assert result.execution_outcome == 'evidence_unavailable'
    assert result.termination_reason == termination
    assert result.limitations[0] == '没有找到可绑定当前字幕版本的有效证据'
    assert 'clarification_requests' not in result.trace


def test_clarification_without_explicit_request_does_not_invent_one():
    decision = {'type': 'finish', 'outcome': 'needs_clarification',
        'unresolved_items': [], 'finish_reason': '资料不足。猜测可能需要20个。'}
    state = {'v2_outcome': 'needs_clarification', 'termination_reason': 'evidence_unavailable',
        'events': [{'event_type': 'v2_decision', 'decision': decision}]}
    assert _v2_clarification_requests(state) == ()


@pytest.mark.parametrize('answer_status', ['complete', 'insufficient'])
def test_existing_evidence_does_not_hide_confirmed_clarification(tmp_path, answer_status):
    # Exercise factual generation/Trust as well as the zero-evidence path.
    from test_deep_v2 import _span
    from shiliu.ask.contracts import GroundedAnswerDraft
    from shiliu.ask.deep.v2 import QueryReduction, V2Decision
    span = _span('valid-ref', '该来源只支持这个局部事实。')

    class PartialEvidenceProvider:
        def __init__(self):
            self.controller_calls = 0
        def generate_structured(self, **kwargs):
            role = kwargs['role']
            if role == 'agent_action':
                self.controller_calls += 1
                if self.controller_calls == 1:
                    output = V2Decision(type='continue', actions=[{'action_id': 'a1',
                        'kind': 'search_transcripts', 'arguments': {'query': '背景资料'},
                        'purpose': '查询背景'}])
                else:
                    output = V2Decision(type='finish', outcome='needs_clarification',
                        answer_evidence_refs=[span.citation_id],
                        unresolved_items=['请补充具体使用场景'], finish_reason='缺少用户条件')
            elif role == 'query_reduce':
                candidates = json.loads(kwargs['messages'][-1]['content'])['candidates']
                output = QueryReduction(findings=[{'subject': '该来源', 'text': span.quote_text,
                    'evidence_refs': [candidates[0]['evidence_ref']]}], sufficient=True)
            else:
                assert role == 'grounded_answer'
                output = GroundedAnswerDraft(status=answer_status,
                    answer_blocks=([{'text': span.quote_text, 'citation_ids': [span.citation_id]}]
                        if answer_status == 'complete' else []),
                    limitations=['尚缺使用场景'] if answer_status == 'insufficient' else [])
            return SimpleNamespace(output=output, usage={}, latency_ms=0)

    service = _service(tmp_path, PartialEvidenceProvider())
    service.materializer.validate_current = lambda _: None
    service.graph.transcripts = SimpleNamespace(search=lambda *args, **kwargs: {
        'spans': (span,), 'hits': (), 'available': 1, 'scope': {}})
    response, _ = service.ask(AskRequest(query='用户条件未指定', mode='deep'))
    assert '请补充具体使用场景' in response.limitations
    if answer_status == 'complete':
        assert response.status == 'partial'
        assert response.answer_blocks[0].citation_ids == [span.citation_id]
        assert response.citations[0].citation_id == span.citation_id
    else:
        assert response.status == 'insufficient' and not response.answer_blocks


@pytest.mark.parametrize('stale,errors,warning', [
    (['引用失效'], [], '已有字幕引用失效，未用于事实回答'),
    ([], ['检索失败'], '部分或全部检索执行失败'),
])
def test_confirmed_clarification_and_evidence_error_are_both_preserved(stale, errors, warning):
    finalizer = AnswerFinalizer(context_builder=TranscriptContextBuilder(),
        answer_service=SimpleNamespace(), materializer=SimpleNamespace())
    result = finalizer.finalize(query='q', normalized_intent='q', spans=[],
        stale_reasons=stale, retrieval_errors=errors, termination_reason='evidence_unavailable',
        clarification_requests=('请补充具体使用场景',))
    assert '请补充具体使用场景' in result.limitations
    assert warning in result.limitations
    assert result.execution_outcome == 'evidence_unavailable'
    assert result.stale_evidence_count == len(stale)
    assert result.answer_blocks == () and result.citations == ()
