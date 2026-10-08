"""Offline wire-contract and HTTP diagnostics; all HTTP uses MockTransport."""
import json
import runpy
import time
from pathlib import Path

import httpx
import pytest

from shiliu.ask.deep.v2 import (
    CONTROLLER_INSTRUCTIONS, DEEP_ANSWER_INSTRUCTIONS, QUERY_REDUCE_INSTRUCTIONS,
    DeepV2Graph, V2Action,
)
from shiliu.domain import PipelineError
from shiliu.llm import OpenAICompatibleProvider


def mock_http(monkeypatch, handler):
    client = httpx.Client
    monkeypatch.setattr('shiliu.llm.httpx.Client',
        lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs))


def test_actual_reduce_messages_and_json_object_wire_contract(monkeypatch):
    fixture = runpy.run_path(str(Path(__file__).with_name('test_deep_v2.py')))
    seen = []
    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        assert body['model'] == 'deepseek-v4-flash'
        assert body['response_format'] == {'type': 'json_object'}
        assert body['thinking'] == {'type': 'disabled'} and body['temperature'] == 0
        assert body['max_tokens'] == 6000
        system = body['messages'][0]['content']
        assert 'Return JSON matching schema:' in system
        assert 'QueryReduction' in system
        for phrase in ('Write subject first', 'needed for later dependent queries',
                       'must not enter findings or unresolved as factual state', 'use unresolved=[]'):
            assert phrase in system
        output = dict(findings=[dict(subject='item', text='Original fact.', evidence_refs=['c0'])],
                      sufficient=True, unresolved=[])
        return httpx.Response(200, json={'id': 'offline', 'model': 'deepseek-flash',
            'choices': [{'message': {'content': json.dumps(output)}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}})
    mock_http(monkeypatch, handler)
    provider = OpenAICompatibleProvider(base_url='https://offline.invalid', api_key='offline-secret',
                                        model='deepseek-v4-flash', thinking_enabled=False)
    graph = DeepV2Graph(provider_factory=lambda _: provider, transcripts=None, navigation=None, windows=None)
    result = graph._query_reduce_one(V2Action(action_id='one', kind='search_transcripts',
        arguments={'query': 'item'}, purpose='required fact'),
        {'spans': [fixture['_span']('original', 'Original fact.')]}, 'required fact', time.monotonic()+10)
    assert len(seen) == 1 and 'error' not in result
    assert result['findings'][0]['evidence_refs'] == ['original']
    assert result['sufficient'] and result['unresolved'] == []


@pytest.mark.parametrize('status,code', [(400, 'bad_provider_config'),
                                         (401, 'provider_authentication'),
                                         (422, 'bad_provider_config')])
def test_http_failure_body_survives_metadata_and_redacts_credentials(monkeypatch, status, code):
    count = []
    def handler(request):
        count.append(request)
        return httpx.Response(status, json={'error': {'message':
            'Request must mention JSON; echoed offline-secret and Bearer other-secret', 'code': 'json_contract'}})
    mock_http(monkeypatch, handler)
    provider = OpenAICompatibleProvider(base_url='https://offline.invalid', api_key='offline-secret',
                                        model='deepseek-v4-flash', thinking_enabled=False)
    from shiliu.ask.deep.v2 import QueryReduction
    with pytest.raises(PipelineError) as error:
        provider.generate_structured(role='query_reduce', response_schema=QueryReduction,
            messages=[{'role': 'system', 'content': QUERY_REDUCE_INSTRUCTIONS}])
    assert len(count) == 1 and error.value.code == code and not error.value.retryable
    metadata = error.value.completion_metadata
    assert metadata['http_status'] == status
    assert 'Request must mention JSON' in metadata['provider_response_body']
    assert metadata['provider_error_code'] == 'json_contract'
    assert metadata['request_role'] == 'query_reduce'
    assert metadata['model_requested'] == 'deepseek-v4-flash'
    assert metadata['retry_count'] == 0
    assert all(secret not in json.dumps(metadata) for secret in ('offline-secret', 'other-secret'))
    assert 'Authorization' not in metadata


def test_reduce_fidelity_policy_keeps_round2_controller_final_and_engineering():
    import ast
    import subprocess
    from types import SimpleNamespace
    def source(ref, path):
        return subprocess.check_output(['git', 'show', ref + ':' + path], text=True)
    old = ast.parse(source('ee11714aba3e75911744deb6823f870b818eb02b', 'src/shiliu/ask/deep/v2.py'))
    def historical_policy(name):
        fn = next(n for n in ast.walk(old) if isinstance(n, ast.FunctionDef) and n.name == name)
        return next(n.value for n in fn.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'policy' for t in n.targets))
    expected = eval(compile(ast.Expression(historical_policy('_decide')), '<round2>', 'eval'),
                    {'self': SimpleNamespace(budget=SimpleNamespace(max_actions_per_decision=4))})
    assert CONTROLLER_INSTRUCTIONS == expected
    for phrase in (
        'Evidence support is necessary but not sufficient for retention',
        'subject, relation, object, role, direction, quantity, condition and membership or containment',
        'Verify the complete subject-to-relation-to-object statement',
        'Co-occurrence, similar behavior, shared topics or proximity do not establish',
        'needed for an explicitly necessary later dependent search',
        'Stop adding findings and refs once the query can support a qualified answer',
        'Return JSON matching schema: ',
    ):
        assert phrase in QUERY_REDUCE_INSTRUCTIONS
    base = ast.parse(source('a74a16b1c62616186b7e3df194d4327614e5ec26', 'src/shiliu/ask/deep/v2.py'))
    current = ast.parse(Path('src/shiliu/ask/deep/v2.py').read_text())
    def without_reduce(tree):
        tree.body = [n for n in tree.body if not (isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == 'QUERY_REDUCE_INSTRUCTIONS' for t in n.targets))]
        return ast.dump(tree, include_attributes=False)
    # Normalize only the newly authorized independent Reduce budget.
    for node in ast.walk(current):
        if isinstance(node, ast.ClassDef) and node.name == 'V2Budget':
            node.body = [n for n in node.body if not (isinstance(n, ast.AnnAssign)
                and isinstance(n.target, ast.Name) and n.target.id == 'reduce_output_tokens')]
        if isinstance(node, ast.Attribute) and node.attr == 'reduce_output_tokens':
            node.attr = 'controller_output_tokens'
    assert without_reduce(current) == without_reduce(base)
    fixed = ast.parse(source('f0e6389a80a895308d367c7a4c36e549a367e681', 'src/shiliu/ask/deep/v2.py'))
    answer = next(ast.literal_eval(n.value) for n in fixed.body if isinstance(n, ast.Assign)
                  and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'DEEP_ANSWER_INSTRUCTIONS')
    assert DEEP_ANSWER_INSTRUCTIONS == answer
    assert 'transcript_evidence' in answer and 'adopted_video_sources' in answer
    # Existing HTTP error handling must remain identical; length diagnostics are
    # independently exercised below rather than pinning the entire source file.
    llm_current = ast.parse(Path('src/shiliu/llm.py').read_text())
    llm_old = ast.parse(source('f0e6389a80a895308d367c7a4c36e549a367e681', 'src/shiliu/llm.py'))
    for name in ('_http_failure_metadata', '_attach_failure_metadata', '_raise_for_status'):
        def function(tree):
            return ast.dump(next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == name), include_attributes=False)
        assert function(llm_current) == function(llm_old)
