"""Accepted Fast F1 contracts adapted to the current Schema25 product factory."""
import json
import pytest
from fastapi.testclient import TestClient
from shiliu.ask.contracts import AskRequest
from shiliu.ask.f1_context import FastWide30ContextBuilder
from shiliu.web import create_web_app
from ask_product_fixture import pg_formal as product_formal

@pytest.fixture
def formal(product_formal):
    core, provider, raw = product_formal
    service = core.ask_service
    def forbidden(*args, **kwargs):
        raise AssertionError("legacy Fast execution was called")
    service.query_analyzer.analyze = forbidden
    service.evidence_search.execute_search = forbidden
    return core, provider, raw

def test_application_fast_stream_uses_f1_and_durable_output(formal, monkeypatch):
    core, provider, _ = formal
    # One complete raw segment exceeds both historical 2.5K/12K packing gates.
    from shiliu.domain import SubtitleSegment
    video = core.db.list_videos()[0]
    long_text = 'MCP 通过协议连接模型与外部工具。' + '完整原文不得裁切。' * 1600
    batch = core.artifacts.batch(video['id'])
    raw_ref, _ = batch.save_raw_subtitle(video['source_id'], [
        SubtitleSegment.model_validate({'from': 0, 'to': 300, 'content': long_text})])
    batch.commit(lambda conn: core.db.update_video(video['id'], raw_subtitle_path=raw_ref, conn=conn))
    # Existing BM25 degradation can retrieve a raw segment larger than the
    # embedding input limit; the product materializer still supplies it whole.
    core.retrieval.rebuild()
    received = []
    generate = provider.generate_structured
    def record(**kwargs):
        received.append(kwargs)
        return generate(**kwargs)
    monkeypatch.setattr(provider, 'generate_structured', record)
    search = core.ask_service.f1_transcripts.search
    def capture(*args, **kwargs):
        found = search(*args, **kwargs)
        expected.append(FastWide30ContextBuilder().build(query=args[0], normalized_intent=args[0], spans=found['spans']))
        return found
    expected = []
    monkeypatch.setattr(core.ask_service.f1_transcripts, 'search', capture)
    with TestClient(create_web_app(core, background_tasks=False)) as client:
        result = client.post('/api/ask/stream', json={'query': 'MCP', 'mode': 'fast'})
        events = [json.loads(line) for line in result.text.splitlines()]
        assert result.status_code == 200
        assert any(e['event_type'] == 'trusted_answer_block' for e in events)
        rid = result.headers['X-Shiliu-Run-ID']
        response = core.ask_service.get_result(rid)
        assert response.answer_blocks and response.citations
        trace = core.ask_service.get_trace(rid)
        assert trace['implementation_version'] == 'fast-f1'
        assert trace['queries'] == ['MCP'] and provider.query_calls == 0
        assert len(trace['search_executions']) == 1
        context = json.loads(trace['f1']['delivered_context'])
        assert context['citation_allowlist'] == trace['citation_allowlist']
        assert trace['f1']['context'] == 'Wide-30' and trace['f1']['raw_rank_cutoff'] == 30
        assert not {'payload_chars', 'quote_chars', 'max_spans'} & trace['f1'].keys()
        assert trace['f1']['delivered_context'] == expected[0].model_context
        assert len(expected[0].model_context) > 12000
        assert expected[0].spans[0].quote_text == long_text
        assert received[0]['messages'][-1]['content'] == 'Question: MCP\nGrounded context: ' + expected[0].model_context
        assert received[0]['max_tokens'] == 8192
        published = [e['payload'] for e in events if e['event_type'] == 'trusted_answer_block']
        assert published and response.answer_blocks[0].text in json.dumps(published, ensure_ascii=False)
        assert core.ask_service.run_store.get_run(rid)['lifecycle_status'] == 'completed'
        for citation in response.citations:
            assert citation.jump_url and 't=' in citation.jump_url
            assert citation.source_version and citation.segment_ids
        replay = core.ask_service.materializer.reconstruct_citation(response.citations[0],
            execution_id='wide30-replay', search_trace_id=trace['search_executions'][0]['search_trace_id'], query='MCP')
        assert replay.as_citation() == response.citations[0]


def test_fast_stale_source_fails_closed(formal):
    core, provider, raw = formal
    video = core.db.list_videos()[0]
    core.artifacts.objects.resolve(logical_key=f"video:{video['id']}:subtitle-raw.json", head=True).write_text('[]')
    response = core.ask_service.ask(AskRequest(query='MCP'))
    assert not response.citations and provider.answer_calls == 0
    assert response.execution_outcome == 'evidence_unavailable'


def test_fast_no_legal_top30_evidence_never_falls_back(formal, monkeypatch):
    core, provider, _ = formal
    search = core.ask_service.f1_transcripts.search
    def only_rank31(*args, **kwargs):
        found = search(*args, **kwargs)
        found['spans'] = [s.model_copy(update={'retrieval_provenance': (
            {**s.retrieval_provenance[0], 'rank': 31}, *s.retrieval_provenance[1:])}) for s in found['spans']]
        return found
    monkeypatch.setattr(core.ask_service.f1_transcripts, 'search', only_rank31)
    response = core.ask_service.ask(AskRequest(query='MCP'))
    assert response.execution_outcome == 'evidence_unavailable'
    assert provider.answer_calls == 0 and not response.citations


def test_fast_stream_oversized_request_has_zero_dispatch_and_no_repair(formal, monkeypatch):
    from dataclasses import replace
    core, provider, _ = formal
    build = FastWide30ContextBuilder.build
    def huge(self, **kwargs):
        context = build(self, **kwargs)
        return replace(context, model_context=context.model_context + '中' * 340000)
    monkeypatch.setattr(FastWide30ContextBuilder, 'build', huge)
    with TestClient(create_web_app(core, background_tasks=False)) as client:
        result = client.post('/api/ask/stream', json={'query': 'MCP', 'mode': 'fast'})
        rid = result.headers['X-Shiliu-Run-ID']
        response = core.ask_service.get_result(rid)
        trace = core.ask_service.get_trace(rid)
        assert response.execution_outcome == 'generation_failed' and not response.answer_blocks
        assert trace['provider_error_code'] == 'context_too_large'
        assert trace['repair_calls'] == 0 and not trace['repair_used']
        assert provider.answer_calls == 0


def test_fast_missing_dense_keeps_existing_lexical_degradation(formal):
    core, provider, _ = formal
    with core.db.connect() as db:
        db.execute('DELETE FROM collection_embeddings WHERE workspace_id=%s', (core.db.workspace_id,))
    response = core.ask_service.ask(AskRequest(query='MCP'))
    assert response.execution_outcome == 'answer_generated' and response.citations
    trace = core.ask_service.get_trace(response.run_id)
    assert not trace['retrieval_errors'] and provider.query_calls == 0
    assert trace['f1']['index_identity']['degraded_reason']


def test_fast_invalid_citation_and_provider_failure(formal):
    core, provider, _ = formal
    provider.answer_modes = ['invalid']
    response = core.ask_service.ask(AskRequest(query='MCP'))
    assert not response.citations and response.execution_outcome == 'claim_support_insufficient'
    def unavailable(**kwargs):
        raise RuntimeError('provider unavailable')
    provider.generate_structured = unavailable
    response = core.ask_service.ask(AskRequest(query='MCP'))
    assert response.execution_outcome == 'generation_failed' and response.limitations


def test_context_preserves_input_rank_and_counts_full_payload(formal):
    core, _, _ = formal
    spans = core.ask_service.f1_transcripts.search('MCP', filters=AskRequest(query='MCP').filters)['spans']
    builder = FastWide30ContextBuilder()
    context = builder.build(query='MCP', normalized_intent='MCP', spans=spans)
    assert not context.truncated and context.dropped_span_count == 0
    assert all(s.segment_ids for s in context.spans)
    assert 'x' * 2000 in builder.build(query='x' * 2000, normalized_intent='MCP', spans=spans).model_context


def test_f1_candidate_cards_reconstruct_from_raw_trace(formal):
    core, provider, _ = formal
    provider.answer_modes = ['insufficient']
    response = core.ask_service.ask(AskRequest(query='MCP'))
    assert not response.citations
    disclosure = core.ask_service.get_result(response.run_id).candidate_disclosure
    assert disclosure.candidates
    candidate = disclosure.candidates[0]
    assert candidate.identity_status == 'current' and candidate.jump_url
    assert candidate.candidate_kind == 'transcript_candidate'


def test_f1_context_rank_duplicates_blanks_and_full_payload():
    from test_v4_context_and_citations import _span
    earlier = _span(ordinals=(10, 11, 12), texts=('先来的证据', '', '空白后证据'), rank=30)
    later = _span(ordinals=(0,), texts=('后来的证据',), rank=1)
    context = FastWide30ContextBuilder().build(query='问题', normalized_intent='问题', spans=(earlier, later, earlier))
    assert [s.segment_ordinals for s in context.spans] == [(10,), (12,), (0,)]
    assert len(context.citation_allowlist) == 3
    assert not context.truncated and context.dropped_span_count == 0


@pytest.mark.parametrize("filters", [{"source_db_id": 999999}, {"folder_id": 999999}, {"uploader": "absent"}, {"uploader_contains": "absent"}])
def test_fast_scope_cannot_leak_evidence(formal, filters):
    core, provider, _ = formal
    response = core.ask_service.ask(AskRequest(query="MCP", filters=filters))
    assert not response.citations and not response.answer_blocks
    assert response.limitations and provider.answer_calls == provider.query_calls == 0


def test_fast_continuation_retrieves_original_scope_without_legacy_refresh(formal, monkeypatch):
    from shiliu.ask.adaptive import envelope_for_completed_run
    from shiliu.evidence.decision import decision_from_persistence_projection
    from shiliu.evidence.continuation import ContinuationTarget, ContinuationFailureState, ContinuationContractError
    core, provider, _ = formal
    service = core.ask_service
    request = AskRequest(query="MCP")
    first = service.ask(request)
    trace = service.get_trace(first.run_id)
    decision = decision_from_persistence_projection(trace["evidence_decision"])
    envelope = envelope_for_completed_run(
        run_id=first.run_id, decision=decision, target=ContinuationTarget.FAST,
        question=request.query, filters=request.filters.model_dump(mode="json", exclude_none=True),
        citations=trace["citations"], search_executions=trace["search_executions"],
        failure_state=ContinuationFailureState.NONE,
    )
    def forbidden(*args, **kwargs):
        raise AssertionError("legacy continuation refresh was called")
    monkeypatch.setattr("shiliu.ask.service.execute_targeted_refresh", forbidden)
    monkeypatch.setattr("shiliu.ask.service.revalidate_inherited_evidence", forbidden)
    repeated = service.ask(request, evidence_decision=decision, continuation_envelope=envelope)
    repeated_trace = service.get_trace(repeated.run_id)
    assert repeated.citations and repeated_trace["queries"] == ["MCP"]
    assert repeated_trace["search_executions"][0]["search_trace_id"] != trace["search_executions"][0]["search_trace_id"]
    assert provider.query_calls == 0
    with pytest.raises(ContinuationContractError):
        service.ask(AskRequest(query="different question"), evidence_decision=decision, continuation_envelope=envelope)


def test_fast_original_question_is_not_bound_by_legacy_search_query_limit(formal):
    core, provider, _ = formal
    query = "MCP " + "工具协议 " * 120
    response = core.ask_service.ask(AskRequest(query=query))
    trace = core.ask_service.get_trace(response.run_id)
    assert trace["queries"] == [AskRequest(query=query).query]
    assert trace["implementation_version"] == "fast-f1"
    assert provider.query_calls == 0
