"""Reduce output budget and private length-failure Trace contracts (no network)."""
import hashlib
import json
import runpy
import time
from pathlib import Path

import httpx
import pytest

from shiliu.artifacts import ArtifactStore
from shiliu.ask.deep.v2 import DeepV2Graph, QueryReduction, V2Action, V2Budget
from shiliu.domain import PipelineError
from shiliu.llm import OpenAICompatibleProvider
from test_reduce_json_mode_integration import mock_http


def provider():
    return OpenAICompatibleProvider(base_url='https://offline.invalid', api_key='offline-secret',
                                    model='deepseek-v4-flash', thinking_enabled=False)


@pytest.mark.parametrize('size', [0, 100, 8192, 30000])
def test_length_metadata_is_bounded_complete_and_never_parsed(monkeypatch, caplog, size):
    content = ('{"findings":["' + '私' * size + 'JSON-tail') if size else ''
    requests = []
    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body['max_tokens'] == 6000
        return httpx.Response(200, json={'id': 'length-call', 'model': 'deepseek-flash',
            'choices': [{'message': {'content': content}, 'finish_reason': 'length'}],
            'usage': {'prompt_tokens': 22000, 'completion_tokens': 6000, 'total_tokens': 28000}})
    mock_http(monkeypatch, handler)
    with pytest.raises(PipelineError) as raised:
        provider().generate_structured(role='query_reduce', messages=[{'role': 'user', 'content': 'JSON'}],
                                      response_schema=QueryReduction, max_tokens=6000, timeout_seconds=5)
    error = raised.value
    assert error.code == 'output_budget_exhausted' and not error.retryable
    metadata = error.completion_metadata
    assert len(requests) == 1  # no automatic retry or partial JSON parse
    assert metadata['finish_reason'] == 'length' and metadata['error_code'] == error.code
    assert metadata['max_tokens'] == 6000 and metadata['request_role'] == 'query_reduce'
    assert metadata['model_requested'] == 'deepseek-v4-flash'
    assert metadata['model_response'] == 'deepseek-flash'
    assert metadata['response_id'] == 'length-call' and metadata['retry_count'] == 0
    assert metadata['latency_ms'] >= 0 and metadata['usage']['completion_tokens'] == 6000
    assert metadata['content_received'] == bool(content)
    assert metadata['raw_content_length'] == len(content)
    assert metadata['raw_content_hash'] == hashlib.sha256(content.encode()).hexdigest()
    prefix, suffix = metadata['raw_content_prefix'], metadata['raw_content_suffix']
    assert len(prefix) <= 4096 and len(suffix) <= 4096
    assert prefix == content[:4096] and suffix == content[max(4096, len(content)-4096):]
    assert metadata['raw_content_omitted_chars'] == max(0, len(content)-8192)
    assert metadata['raw_content_diagnostic_only']
    assert '私' not in caplog.text and 'JSON-tail' not in str(error)


def test_length_excerpts_redact_credentials_before_boundary_slicing(monkeypatch):
    content = 'x' * 4092 + 'offline-secret Bearer private-token' + 'x' * 16000
    mock_http(monkeypatch, lambda request: httpx.Response(200, json={'choices': [
        {'message': {'content': content}, 'finish_reason': 'length'}]}))
    with pytest.raises(PipelineError) as raised:
        provider().generate_structured(role='query_reduce', messages=[], response_schema=QueryReduction,
                                      max_tokens=6000)
    metadata = raised.value.completion_metadata
    saved = metadata['raw_content_prefix'] + metadata['raw_content_suffix']
    assert 'offline-secret' not in saved and 'private-token' not in saved
    assert metadata['raw_content_hash'] == hashlib.sha256(content.encode()).hexdigest()
    assert metadata['model_response'] is None


def test_failed_reduce_trace_persists_without_findings_or_final_refs(monkeypatch, tmp_path):
    f = runpy.run_path(str(Path(__file__).with_name('test_deep_v2.py')))
    controller = f['Provider']([f['_continue'](['topic']),
        {'type': 'finish', 'outcome': 'insufficient', 'unresolved_items': ['Missing legal evidence']}])
    content = '{"findings":[{"subject":"DIAGNOSTIC_ONLY", "text":"' + 'x'*20000
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={'id': 'reduce-length', 'model': 'deepseek-flash',
            'choices': [{'message': {'content': content}, 'finish_reason': 'length'}],
            'usage': {'completion_tokens': 6000}})
    mock_http(monkeypatch, handler)
    class Search:
        def search(self, *args, **kwargs):
            return {'spans': [f['_span']('original', 'private transcript')], 'hits': [],
                    'available': 1, 'raw_count': 1, 'scope': {}}
    real = provider()
    graph = DeepV2Graph(provider_factory=lambda role: real if role == 'query_reduce' else controller,
                        transcripts=Search(), navigation=None, windows=None)
    state = graph.run(f['_state']())
    event = next(e for e in state['events'] if e['event_type'] == 'v2_query_reduce')
    path = tmp_path/'trace.json'
    ArtifactStore.write_json(path, {'events': state['events']})
    saved = json.loads(path.read_text())
    diagnostic = next(e for e in saved['events'] if e['event_type'] == 'v2_query_reduce')['provider']
    assert diagnostic == event['provider']
    assert diagnostic['raw_content_prefix'].startswith('{"findings"')
    assert diagnostic['raw_content_hash'] == hashlib.sha256(content.encode()).hexdigest()
    assert event['findings'] == [] and event['retained_evidence_refs'] == []
    assert state['v2_final_refs'] == [] and len(state['v2_store']) == 1
    assert state['v2_query_results'][0]['findings'] == []
    assert all('DIAGNOSTIC_ONLY' not in json.dumps(call['messages']) for call in controller.calls)
    assert len(seen) == 1 and seen[0]['max_tokens'] == 6000
    assert all(call['max_tokens'] == 4096 for call in controller.calls)
    assert V2Budget().answer_output_tokens == 8192


def test_reduce_budget_override_reaches_actual_wire_without_changing_deadline(monkeypatch):
    f = runpy.run_path(str(Path(__file__).with_name('test_deep_v2.py')))
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={'model': 'deepseek-flash', 'choices': [{'message': {'content':
            json.dumps({'findings': [{'subject': 's', 'text': 'fact', 'evidence_refs': ['c0']}],
                        'sufficient': True, 'unresolved': []})}, 'finish_reason': 'stop'}]})
    mock_http(monkeypatch, handler)
    graph = DeepV2Graph(provider_factory=lambda _: provider(), transcripts=None, navigation=None,
                        windows=None, budget=V2Budget(reduce_output_tokens=6123))
    result = graph._query_reduce_one(V2Action(action_id='a', kind='search_transcripts',
        arguments={'query': 'q'}, purpose='q'), {'spans': [f['_span']('original', 'fact')]},
        'question', time.monotonic()+5)
    assert seen[0]['max_tokens'] == 6123 and 'error' not in result
    assert result['retained_evidence_refs'] == ['original']
    assert V2Budget().search_seconds == 180 and V2Budget().total_seconds == 240
