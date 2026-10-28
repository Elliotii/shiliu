"""Fast-only packing and send-size contracts; no live providers."""
import json
from types import SimpleNamespace

import httpx
import pytest

from shiliu.ask.answer import GroundedAnswerService, _answer_messages, _check_fast_request_size
from shiliu.ask.f1_context import FastWide30ContextBuilder
from shiliu.domain import PipelineError
from shiliu.llm import OpenAICompatibleProvider
from test_v4_context_and_citations import _span


def build(*spans):
    return FastWide30ContextBuilder().build(query='问题', normalized_intent='问题', spans=spans)


def test_complete_segments_merge_only_at_tail_and_keep_citations():
    long = '完整原文' * 1000
    result = build(_span(ordinals=(4, 5), texts=(long, '下一句')),
                   _span(ordinals=(6,), texts=('连续',), rank=2),
                   _span(ordinals=(0,), texts=('稍后排名',), rank=3))
    assert [s.segment_ordinals for s in result.spans] == [(4, 5, 6), (0,)]
    assert result.spans[0].quote_text == long + '\n下一句\n连续'
    citation = result.spans[0].as_citation()
    assert citation.segment_ids == ['segment-4', 'segment-5', 'segment-6']
    assert result.spans[0].segment_ordinals == (4, 5, 6)
    assert (citation.source_artifact_id, citation.source_version, citation.timeline_run_id) == ('artifact', 'version', 'timeline')
    assert citation.start_time == 4 and citation.end_time == 7 and 't=4' in citation.jump_url
    assert result.citation_allowlist == tuple(s.citation_id for s in result.spans)
    assert json.loads(result.model_context)['transcript_evidence'][0]['quote'] == result.spans[0].quote_text
    assert not result.truncated and result.dropped_span_count == 0


@pytest.mark.parametrize('middle', ['blank', 'duplicate', 'gap'])
def test_blank_duplicate_and_gap_are_merge_barriers(middle):
    first = _span(ordinals=(0,), texts=('零',))
    if middle == 'blank':
        next_span = _span(ordinals=(0, 1), texts=('  ', '一'), rank=2)
    elif middle == 'duplicate':
        next_span = _span(ordinals=(0, 1), texts=('零', '一'), rank=2)
    else:
        next_span = _span(ordinals=(3,), texts=('三',), rank=2)
    result = build(first, next_span)
    assert len(result.spans) == 2
    assert result.spans[0].segment_ordinals == (0,)
    assert not result.truncated


def test_raw_rank30_slots_never_fill_from31_after_blanks_or_duplicates():
    first = _span(ordinals=(7,), texts=('保留',), rank=30)
    result = build(_span(ordinals=(8,), texts=('不得补位',), rank=31), first,
                   first, _span(ordinals=(9,), texts=(' ',), rank=29))
    assert [s.segment_ordinals for s in result.spans] == [(7,)]
    assert not result.truncated and result.dropped_span_count == 0
    assert not build(_span(rank=31)).spans


@pytest.mark.parametrize('field', ['source_artifact_id', 'source_version', 'timeline_run_id'])
def test_equal_text_with_distinct_lineage_is_preserved(field):
    first = _span(ordinals=(0,), texts=('相同文字',))
    other = first.model_copy(update={field: 'other'})
    result = build(first, other)
    assert len(result.spans) == len(set(result.citation_allowlist)) == 2
    assert getattr(result.spans[1].as_citation(), field) == 'other'


def test_conflicting_text_at_duplicate_coordinate_is_an_error():
    with pytest.raises(ValueError, match='conflicting original segment text'):
        build(_span(ordinals=(0,), texts=('原文',)), _span(ordinals=(0,), texts=('冲突',)))


@pytest.mark.parametrize('fast,large', [(True, False), (True, True), (False, True)])
def test_fast_size_gate_uses_complete_request_and_other_modes_default_unchanged(monkeypatch, fast, large):
    requests = []
    def post(self, url, **kwargs):
        requests.append(kwargs['json'])
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({
            'status': 'insufficient', 'answer_blocks': [], 'limitations': ['无足够证据']})},
            'finish_reason': 'stop'}], 'usage': {}}, request=httpx.Request('POST', url))
    monkeypatch.setattr('shiliu.llm.httpx.Client.post', post)
    provider = OpenAICompatibleProvider(base_url='https://synthetic.invalid/v1', api_key='synthetic',
        model='deepseek-v4-flash', thinking_enabled=False)
    context = build(_span(ordinals=(0,), texts=(('中' * 340000) if large else '完整原文',)))
    service = GroundedAnswerService(lambda _: provider, SimpleNamespace(validate_current=lambda _: True),
        fast_request_preflight=fast)
    result = service.answer(query='问题', context=context)
    if fast and large:
        assert not requests and result.provider_error_code == 'context_too_large'
        assert not result.repair_used and result.repair_calls == 0
    else:
        assert len(requests) == 1 and result.draft.status == 'insufficient'
        assert requests[0]['messages'] == _answer_messages(query='问题', context=context)
        assert requests[0]['max_tokens'] == 8192


@pytest.mark.parametrize('first_error', ['invalid_model_output', 'output_budget_exhausted'])
def test_natural_repair_and_recovery_each_pass_size_check(monkeypatch, first_error):
    checks, roles = [], []
    original_check = _check_fast_request_size
    def check(provider, kwargs):
        checks.append(kwargs['messages'])
        original_check(provider, kwargs)
    monkeypatch.setattr('shiliu.ask.answer._check_fast_request_size', check)
    class Provider:
        calls = 0
        def generate_structured(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                error = PipelineError('synthetic recovery', code=first_error, retryable=False)
                error.completion_metadata = {'content_received': True}
                raise error
            return SimpleNamespace(output={'status': 'insufficient', 'answer_blocks': [], 'limitations': ['不足']})
    provider = Provider()
    def factory(role):
        roles.append(role)
        return provider
    result = GroundedAnswerService(factory, None, fast_request_preflight=True).answer(query='问题', context=build(_span()))
    assert provider.calls == len(checks) == 2 and result.repair_used and result.draft is not None
    assert 'Deterministic validation errors' in checks[1][-1]['content']
    assert roles == (['grounded_answer', 'grounded_answer_recovery'] if first_error == 'output_budget_exhausted' else ['grounded_answer'])


def test_repair_request_growth_is_rechecked_before_dispatch():
    class Provider:
        calls = 0
        def generate_structured(self, **kwargs):
            self.calls += 1
            raise AssertionError('oversized local repair must not dispatch')
    # _error_text caps diagnostic growth; directly exercise the existing local
    # citation-repair send point with a large supplied failed block instead.
    from shiliu.ask.contracts import AnswerDraftBlock
    from shiliu.ask.validation import ValidationIssue
    provider = Provider()
    result = GroundedAnswerService(lambda _: provider, None, fast_request_preflight=True).repair(
        query='问题', context=build(_span()), issues=(ValidationIssue('citation_not_allowed', '$', 'bad'),),
        failed_blocks=(AnswerDraftBlock(text='中' * 340000, citation_ids=['invalid']),))
    assert provider.calls == 0 and result.provider_error_code == 'context_too_large'


def test_stream_fields_and_utf8_bytes_are_included_in_size_bound(monkeypatch):
    serialized = []
    dumps = json.dumps
    def capture(body, **kwargs):
        serialized.append(body)
        return dumps(body, **kwargs)
    monkeypatch.setattr('shiliu.ask.answer.json.dumps', capture)
    provider = SimpleNamespace(model='deepseek-v4-flash', thinking_enabled=False)
    _check_fast_request_size(provider, {'messages': [{'role': 'user', 'content': '中文'}],
        'max_tokens': 8192, 'on_content': lambda _: None})
    assert serialized[0] == {'model': 'deepseek-v4-flash', 'messages': [{'role': 'user', 'content': '中文'}],
        'max_tokens': 8192, 'response_format': {'type': 'json_object'}, 'thinking': {'type': 'disabled'},
        'temperature': 0, 'stream': True, 'stream_options': {'include_usage': True}}
