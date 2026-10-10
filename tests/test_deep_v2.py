from __future__ import annotations

from threading import Barrier
import time
from types import SimpleNamespace

from shiliu.ask.deep.v2 import DeepV2Graph, V2Budget, V2Decision, QueryReduction
from shiliu.ask.deep.v2 import DeepV2ContextBuilder
from shiliu.ask.contracts import AskResponse, TraceSummary, EvidenceSegment, TranscriptEvidenceSpan
from shiliu.ask.deep.f1_tools import F1TranscriptTool
from shiliu.ask.deep.contracts import NavigationDocument
from shiliu.ask.deep.service import DeepSearchService
from shiliu.artifacts import ArtifactStore
from shiliu.ask.contracts import AskRequest
from shiliu.ask.service import AskService
from shiliu.db import Database
from shiliu.app import Application
from shiliu.web import create_web_app
from fastapi.testclient import TestClient
from shiliu.retrieval.product_search import ProductSearchFilterRequest
from shiliu.retrieval.f1 import rrf_50
from shiliu.retrieval.orchestrator import RawSearchHit


def _hit(identity: str, rank: int, channel: str):
    return RawSearchHit(identity, 1, "transcript_chunk", rank, 1.0, channel,
        rank if channel == "lexical" else None, 1.0 if channel == "lexical" else None,
        rank if channel == "dense" else None, 1.0 if channel == "dense" else None,
        None, "t", "u", "ai", 0, 1, "text")


def test_f1_rrf_raw_rank_and_stable_identity():
    hits = rrf_50([_hit("a", 1, "dense"), _hit("b", 2, "dense")],
                  [_hit("b", 1, "lexical"), _hit("c", 2, "lexical")])
    assert [hit.unit_id for hit in hits] == ["b", "a", "c"]
    assert hits[0].dense_rank == 2 and hits[0].lexical_rank == 1
    assert hits[0].rrf_score == 1 / 62 + 1 / 61


class Provider:
    def __init__(self, decisions):
        self.decisions = iter(decisions)
        self.calls = []
        self.model = "test-flash"

    def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["role"] == "query_reduce":
            import json
            candidates = json.loads(kwargs["messages"][-1]["content"])["candidates"]
            findings = ([{"subject": "test source", "text": "relevant original text", "evidence_refs": [candidates[0]["evidence_ref"]]}]
                if candidates else [])
            return SimpleNamespace(output=QueryReduction.model_validate({"findings": findings,
                "sufficient": bool(findings), "unresolved": [] if findings else ["no evidence"]}),
                usage={"prompt_tokens": 10, "completion_tokens": 5}, latency_ms=1)
        return SimpleNamespace(output=V2Decision.model_validate(next(self.decisions)), usage={"total_tokens": 3}, latency_ms=1)


class Transcripts:
    def __init__(self, barrier=None):
        self.barrier = barrier
        self.started = []

    def search(self, query, *, filters, video_ids=()):
        self.started.append((query, time.monotonic()))
        if self.barrier:
            self.barrier.wait(timeout=2)
        time.sleep({"a": .04, "b": .03, "c": .02, "d": .01}.get(query, 0))
        return {"spans": (), "hits": (), "available": 0, "scope": {"video_ids": video_ids}}


def _state():
    now = time.monotonic()
    return {"query": "question", "filters": ProductSearchFilterRequest(), "search_deadline": now + 8,
        "total_deadline": now + 10, "decision_rounds": 0, "tool_calls": 0, "usage": [], "events": [],
        "termination_reason": None, "errors": [], "evidence_spans": [], "navigation_result_count": 0,
        "visited_video_ids": [], "visited_segment_ids": []}


def _continue(queries):
    return {"type": "continue", "actions": [{"action_id": q, "kind": "search_transcripts",
        "arguments": {"query": q}, "purpose": q} for q in queries]}


def _finish():
    return {"type": "finish", "outcome": "insufficient", "finish_reason": "none"}


def test_four_actions_start_concurrently_and_reduce_in_action_order():
    provider = Provider([_continue("abcd"), _finish()])
    tool = Transcripts(Barrier(4))
    graph = DeepV2Graph(provider_factory=lambda _: provider, transcripts=tool, navigation=None,
                        windows=None, budget=V2Budget())
    state = graph.run(_state())
    assert state["tool_calls"] == 4
    assert len(tool.started) == 4
    assert max(t for _, t in tool.started) - min(t for _, t in tool.started) < .1
    assert [e["action_id"] for e in state["events"] if e["event_type"] == "v2_tool_result"] == list("abcd")
    assert len(provider.calls) == 2


def test_oversized_batch_repaired_before_any_execution():
    provider = Provider([_continue("abcde"), _continue("abcd"), _finish()])
    tool = Transcripts()
    graph = DeepV2Graph(provider_factory=lambda _: provider, transcripts=tool, navigation=None,
                        windows=None, budget=V2Budget())
    state = graph.run(_state())
    assert state["tool_calls"] == 4
    assert len(provider.calls) == 3
    assert not any(query == "e" for query, _ in tool.started)
    assert provider.calls[1]["messages"][1]["content"].find("batch exceeds") >= 0


def test_same_batch_read_dependency_rejected():
    graph = DeepV2Graph(provider_factory=lambda _: None, transcripts=Transcripts(), navigation=None, windows=None)
    decision = V2Decision.model_validate({"type": "continue", "actions": [
        {"action_id": "s", "kind": "search_transcripts", "arguments": {"query": "a"}, "purpose": "find"},
        {"action_id": "r", "kind": "read_context", "arguments": {"evidence_ref": "future"}, "purpose": "read"}]})
    state = _state()
    state["v2_store"] = {}
    assert "same-batch" in graph._validate(decision, state)


def test_empty_scope_intersection_never_invokes_either_channel():
    tool = F1TranscriptTool.__new__(F1TranscriptTool)
    class Filters:
        def retrieval_filters(self):
            from shiliu.retrieval.models import RetrievalFilters
            return RetrievalFilters(video_ids=(3,))
    result = tool.search("query", filters=Filters(), video_ids=(7,))
    assert result["empty_intersection"] and result["hits"] == []


def _span(ref: str, quote: str) -> TranscriptEvidenceSpan:
    segment = EvidenceSegment(segment_id=ref, original_ordinal=0, run_local_ordinal=0,
                              start_time=0, end_time=1, source_text=quote)
    return TranscriptEvidenceSpan(citation_id=ref, video_id=1, bvid="BV1234567890", title="title",
        source_type="ai", source_language="zh", source_artifact_id="artifact_" + ref, source_version="version",
        source_version_authority="test", timeline_run_id="run", segment_ids=(ref,), segment_ordinals=(0,),
        start_time=0, end_time=1, quote_text=quote, jump_url="https://www.bilibili.com/video/BV1234567890?t=0",
        parent_chunk_ids=(), retrieval_provenance=(), segments=(segment,))


def test_final_context_keeps_full_quotes_and_preferred_order():
    builder = DeepV2ContextBuilder(8000)
    builder.preferred_refs = ["second"]
    builder.candidate_refs = ["first"]
    context = builder.build(query="question", normalized_intent="question",
                            spans=(_span("first", "甲" * 400), _span("second", "乙" * 400)))
    assert list(context.citation_allowlist) == ["second", "first"]
    assert "乙" * 400 in context.model_context and "甲" * 400 in context.model_context
    assert not context.truncated


def test_final_context_keeps_only_adopted_video_source_and_original_identity():
    import json
    builder = DeepV2ContextBuilder(8000)
    builder.preferred_refs = ['original']
    builder.source_metadata = {1: {'uploader': 'Publishing channel'}}
    builder.adopted_sources = [{'video_id': 7, 'title': 'Published work',
        'uploader': 'Artist', 'bvid': 'BV1234567890', 'url': 'https://example.com/7'}]
    context = builder.build(query='Who published the work?', normalized_intent='source',
                            spans=(_span('original', 'The work was discussed here.'),))
    payload = json.loads(context.model_context)
    assert payload['adopted_video_sources'] == builder.adopted_sources
    assert payload['transcript_evidence'][0]['source_uploader'] == 'Publishing channel'
    assert context.citation_allowlist == ('original',)
    assert 'candidate-only' not in context.model_context


def test_finish_rejects_unknown_adopted_source():
    graph = DeepV2Graph(provider_factory=lambda _: None, transcripts=None, navigation=None, windows=None)
    state = _state()
    state.update(v2_store={}, v2_sources={7: {'video_id': 7}}, v2_query_results=[], v2_needs={})
    decision = V2Decision(type='finish', outcome='sufficient', answer_source_ids=['nav:8'])
    assert graph._validate(decision, state) == "unknown answer navigation source IDs: ['nav:8']"


def test_transcript_video_id_cannot_impersonate_navigation_record():
    import pytest
    from pydantic import ValidationError
    graph = DeepV2Graph(provider_factory=lambda _: None, transcripts=None, navigation=None, windows=None)
    span = _span('ref', 'content').model_copy(update={'video_id': 423})
    state = _state()
    state.update(v2_store={'ref': span}, v2_sources={7: {'video_id': 7}}, v2_needs={})
    with pytest.raises(ValidationError):
        V2Decision(type='finish', outcome='sufficient', answer_source_ids=[423])
    assert graph._validate(V2Decision(type='finish', outcome='sufficient',
        answer_source_ids=['nav:423']), state) == "unknown answer navigation source IDs: ['nav:423']"
    assert graph._validate(V2Decision(type='finish', outcome='sufficient',
        answer_source_ids=['nav:7'], answer_evidence_refs=['ref']), state) is None


def test_navigation_validation_failure_is_not_provider_failure():
    provider = Provider([{'type': 'finish', 'outcome': 'sufficient', 'answer_source_ids': ['nav:7']}] * 2)
    state = DeepV2Graph(provider_factory=lambda _: provider, transcripts=None,
        navigation=None, windows=None).run(_state())
    assert state['termination_reason'] == 'invalid_structured_output'
    assert state['v2_controller_calls'] == 2 and state['tool_calls'] == 0


def test_subject_binding_survives_shared_quote_and_final_projection():
    """Exercise the data path; semantic extraction itself is checked by the real runs."""
    import json
    quote = 'First device costs 100. Next device folds flat.'
    shared = _span('shared', quote).model_copy(update={'start_time': 10, 'end_time': 20})
    earlier = _span('earlier', 'Two distinct devices are introduced.').model_copy(
        update={'start_time': 0, 'end_time': 10})
    class Selector:
        model = 'test-flash'
        def generate_structured(self, **kwargs):
            payload = json.loads(kwargs['messages'][1]['content'])
            assert [item['evidence_ref'] for item in payload['candidates']] == ['c1', 'c0']
            return SimpleNamespace(output=QueryReduction(sufficient=True, findings=[
                {'subject': 'first device', 'text': 'Costs 100.', 'evidence_refs': ['c0']},
                {'subject': 'next device', 'text': 'Folds flat.', 'evidence_refs': ['c0']}]), usage={}, latency_ms=1)
    provider = Selector()
    graph = DeepV2Graph(provider_factory=lambda _: provider, transcripts=None, navigation=None, windows=None)
    action = V2Decision.model_validate(_continue(['compare devices'])).actions[0]
    reduced = graph._query_reduce_one(action, {'spans': [shared, earlier]}, 'Compare devices', time.monotonic()+5)
    assert reduced['findings'] == [
        {'subject': 'first device', 'text': 'Costs 100.', 'evidence_refs': ['shared']},
        {'subject': 'next device', 'text': 'Folds flat.', 'evidence_refs': ['shared']}]
    state = _state()
    state.update(v2_store={}, v2_sources={}, v2_cache={}, v2_query_results=[])
    graph._reduce(action, {'spans': [shared, earlier], 'status': 'ok', 'cache_key': 'test',
        'query_reduction': reduced, 'started_at': 0, 'ended_at': 1}, state)
    assert state['v2_query_results'][0]['findings'] == reduced['findings']
    controller = Provider([_finish()])
    graph.provider_factory = lambda _: controller
    state.update(v2_needs={}, v2_controller_calls=1, v2_round_timings=[])
    graph._decide(state)
    assert json.loads(controller.calls[-1]['messages'][1]['content'])['query_results'][0]['findings'] == reduced['findings']
    builder = DeepV2ContextBuilder()
    builder.candidate_refs = ['shared']
    builder.subject_bindings = reduced['findings'] + [
        {'subject': 'unselected', 'text': 'Unselected annotation.', 'evidence_refs': ['earlier']}]
    context = builder.build(query='Compare devices', normalized_intent='compare', spans=(shared, earlier))
    payload = json.loads(context.model_context)
    assert payload['subject_bindings_not_new_evidence'] == reduced['findings']
    assert context.citation_allowlist == ('shared',)
    assert payload['transcript_evidence'][0]['quote'] == quote


def test_controller_source_identity_contract_and_content_path():
    import json
    # The mock follows the tool-choice contract; real model selection is covered
    # by the five regression cases, without an intent classifier or forced tool.
    class ContractProvider:
        model = 'test-flash'
        def generate_structured(self, **kwargs):
            policy = kwargs['messages'][0]['content']
            payload = json.loads(kwargs['messages'][1]['content'])
            assert 'use search_videos to locate that source' in policy
            assert 'Ordinary content questions should use search_transcripts directly' in policy
            assert 'Transcript video_id is never a navigation record ID' in policy
            if payload['needs'][0]['gap'] == 'Original release identity is not established.':
                decision = V2Decision.model_validate({'type': 'continue', 'actions': [
                    {'action_id': 'locate', 'kind': 'search_videos', 'arguments': {'query': 'Named work'},
                     'purpose': 'Locate the original release'}]})
            else:
                decision = V2Decision.model_validate(_continue(['content question']))
            return SimpleNamespace(output=decision, usage={}, latency_ms=1)
    graph = DeepV2Graph(provider_factory=lambda _: ContractProvider(), transcripts=None, navigation=None, windows=None)
    state = _state()
    state.update(v2_needs={'source': {'text': 'Find the original release', 'status': 'open',
        'gap': 'Original release identity is not established.'}}, v2_query_results=[],
        v2_sources={}, v2_round_timings=[], v2_controller_calls=1)
    assert graph._decide(state)[0].actions[0].kind == 'search_videos'
    state['v2_needs'] = {'content': {'text': 'Explain the content', 'status': 'open', 'gap': 'Content needed.'}}
    assert graph._decide(state)[0].actions[0].kind == 'search_transcripts'


def test_source_lookup_shape_requires_real_sources():
    trace = TraceSummary(query_count=0, retrieval_count=0, valid_evidence_count=0,
        stale_evidence_count=0, context_span_count=0, context_truncated=False, repair_used=False,
        latency_ms=1, termination_reason="answer_ready")
    response = AskResponse(run_id="r", mode="deep", status="complete",
        execution_outcome="source_lookup_complete", answer_blocks=[], citations=[], limitations=[],
        source_matches=[{"video_id": 1, "title": "source", "url": "https://example.com"}],
        termination_reason="answer_ready", trace_summary=trace)
    assert response.source_matches[0]["video_id"] == 1


def test_pure_source_lookup_persists_and_reloads(tmp_path):
    db = Database(tmp_path / "state.db")
    db.initialize()
    provider = Provider([{"type": "continue", "actions": [{"action_id": "s", "kind": "search_videos",
        "arguments": {"query": "title"}, "purpose": "locate"}]},
        {"type": "finish", "outcome": "sources_found", "answer_source_ids": ["nav:7"],
         "finish_reason": "located"}])
    class Embedding:
        dimension = 512
    service = DeepSearchService(db=db, artifacts=ArtifactStore(tmp_path / "videos"),
        product_search=None, provider_factory=lambda _: provider,
        embedding_provider=Embedding(), lexical_index_path=tmp_path / "unused.sqlite")
    source = NavigationDocument(video_id=7, bvid="BV1234567890", title="Located", uploader="Author",
        description="description", summary_sections=[], user_notes=[], cleaned_transcript=[],
        metadata={"video_url": "https://www.bilibili.com/video/BV1234567890", "subtitle_available": False},
        matched_excerpt="title", matched_sources=["title"], source_labels={})
    service.graph.navigation = SimpleNamespace(search=lambda *args, **kwargs: [source])
    response, trace = service.ask(AskRequest(query="find the video", mode="deep"))
    assert response.status == "complete" and response.execution_outcome == "source_lookup_complete"
    assert response.answer_blocks == [] and response.citations == []
    reader = AskService.__new__(AskService)
    reader.run_store = service.run_store
    reader._candidate_disclosure = lambda run_id: None
    durable = reader.get_result(response.run_id)
    assert durable is not None and durable.source_matches[0]["url"].endswith("BV1234567890")
    assert trace["implementation_version"] == "deep-v2"
    assert trace['v2_final_source_ids'] == ['nav:7']
    import json
    assert json.loads(trace['v2_final_context'])['adopted_video_sources'][0]['uploader'] == 'Author'


def test_durable_api_deep_v2_source_lookup(app_paths):
    app = Application(app_paths)
    provider = Provider([{"type": "continue", "actions": [{"action_id": "s", "kind": "search_videos",
        "arguments": {"query": "title"}, "purpose": "locate"}]},
        {"type": "finish", "outcome": "sources_found", "finish_reason": "located"}])
    app.deep_v2_provider = lambda _: provider
    source = NavigationDocument(video_id=7, bvid="BV1234567890", title="Located", uploader="Author",
        description="description", summary_sections=[], user_notes=[], cleaned_transcript=[],
        metadata={"video_url": "https://www.bilibili.com/video/BV1234567890"},
        matched_excerpt="title", matched_sources=["title"], source_labels={})
    app.ask_service.deep_service.graph.navigation = SimpleNamespace(search=lambda *args, **kwargs: [source])
    client = TestClient(create_web_app(app))
    created = client.post("/api/ask/runs", json={"query": "find the video", "mode": "deep"})
    assert created.status_code == 202
    run_id = created.json()["run_id"]
    result = client.get(f"/api/ask/runs/{run_id}").json()["result"]
    assert result["execution_outcome"] == "source_lookup_complete"
    assert result["source_matches"][0]["video_id"] == 7


def test_cache_larger_projection_does_not_repeat_retrieval():
    first = _continue(['same'])
    second = _continue(['same'])
    second['actions'][0]['action_id'] = 'expanded'
    second['actions'][0]['arguments']['result_limit'] = 50
    provider, tool = Provider([first, second, _finish()]), Transcripts()
    graph = DeepV2Graph(provider_factory=lambda _: provider, transcripts=tool, navigation=None, windows=None)
    state = graph.run(_state())
    assert len(tool.started) == 1
    events = [e for e in state['events'] if e['event_type'] == 'v2_tool_result']
    assert events[1]['cache_hit'] is True


def test_single_tool_failure_keeps_other_result_and_waits_all():
    class Failing(Transcripts):
        def search(self, query, **kwargs):
            if query == 'a':
                raise RuntimeError('broken source')
            return super().search(query, **kwargs)
    provider = Provider([_continue('ab'), _finish()])
    state = DeepV2Graph(provider_factory=lambda _: provider, transcripts=Failing(),
                        navigation=None, windows=None).run(_state())
    events = [e for e in state['events'] if e['event_type'] == 'v2_tool_result']
    assert [e['action_id'] for e in events] == ['a', 'b']
    assert events[0]['status'] == 'error' and events[1]['status'] == 'empty'
    assert len(provider.calls) == 2


def test_budget_rejects_whole_batch_without_partial_dispatch():
    provider, tool = Provider([_continue('ab'), _continue('ab')]), Transcripts()
    state = DeepV2Graph(provider_factory=lambda _: provider, transcripts=tool, navigation=None,
        windows=None, budget=V2Budget(max_tool_calls=1)).run(_state())
    assert state['tool_calls'] == 0 and tool.started == []
    assert state['v2_controller_calls'] == 2
    assert state['termination_reason'] == 'tool_budget_exhausted'
    assert state['v2_outcome'] == 'insufficient'


def test_cancelled_run_never_schedules_provider():
    provider = Provider([_finish()])
    graph = DeepV2Graph(provider_factory=lambda _: provider, transcripts=Transcripts(),
                       navigation=None, windows=None, cancelled=lambda _: True)
    state = graph.run(_state())
    assert provider.calls == []
    assert state['termination_reason'] == 'cancelled'
    assert state['v2_outcome'] == 'insufficient'


def test_controller_deadline_failure_is_timeout_not_provider_error():
    from shiliu.domain import PipelineError

    class DeadlineProvider:
        def generate_structured(self, **kwargs):
            raise PipelineError('controller deadline', code='deadline_exhausted', retryable=False)

    graph = DeepV2Graph(provider_factory=lambda _: DeadlineProvider(), transcripts=Transcripts(),
                       navigation=None, windows=None)
    state = graph.run(_state())
    assert state['termination_reason'] == 'timeout'
    assert state['v2_outcome'] == 'insufficient'


def test_search_and_known_read_share_batch_then_dependent_next_decision():
    anchor = _span('known', '原始语境')
    first = _continue(['find'])
    first['actions'].append({'action_id': 'read', 'kind': 'read_context',
        'arguments': {'evidence_ref': 'known'}, 'purpose': 'context', 'based_on_refs': ['known']})
    second = _continue(['follow'])
    second['actions'][0]['based_on_refs'] = ['known']
    provider = Provider([first, second, _finish()])
    windows = SimpleNamespace(read_context=lambda *args, **kwargs:
        SimpleNamespace(span=anchor, before_boundary=True, after_boundary=True))
    state = _state()
    state['evidence_spans'] = [anchor]
    result = DeepV2Graph(provider_factory=lambda _: provider, transcripts=Transcripts(),
                        navigation=None, windows=windows).run(state)
    assert result['tool_calls'] == 3
    events = [e for e in result['events'] if e['event_type'] == 'v2_tool_result']
    assert [e['action_id'] for e in events] == ['find', 'read', 'follow']
    assert events[2]['based_on_refs'] == ['known']


def test_same_lineage_overlap_deduplicates_original_segments():
    from shiliu.ask.deep.v2 import canonical_material
    first = _span('first', '甲')
    segment2 = EvidenceSegment(segment_id='s2', original_ordinal=1, run_local_ordinal=1,
        start_time=1, end_time=2, source_text='乙')
    second = first.model_copy(update={'citation_id': 'second', 'segments': (first.segments[0], segment2),
        'segment_ids': ('first', 's2'), 'segment_ordinals': (0, 1), 'end_time': 2, 'quote_text': '甲\n乙'})
    canonical, aliases = canonical_material([first, second])
    assert len(canonical) == 1
    merged = next(iter(canonical.values()))
    assert merged.segment_ids == ('first', 's2')
    assert merged.quote_text.count('甲') == 1
    assert aliases['first'] == aliases['second']


def test_f1_companion_index_tracks_existing_video_update_boundary(tmp_path):
    import sqlite3
    from shiliu.retrieval.f1 import F1LexicalIndex
    source, target = tmp_path / 'corpus.db', tmp_path / 'f1.sqlite'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE retrieval_units(unit_id TEXT,unit_type TEXT,video_id INTEGER,source_text TEXT,content_hash TEXT)')
        db.executemany('INSERT INTO retrieval_units VALUES (?,?,?,?,?)',
            [('a','transcript_chunk',1,'甲','h1'),('b','transcript_chunk',2,'乙','h2')])
    index = F1LexicalIndex(target, source)
    old = index.build()
    with sqlite3.connect(source) as db:
        db.execute("DELETE FROM retrieval_units WHERE video_id=1")
        db.execute("INSERT INTO retrieval_units VALUES ('c','transcript_chunk',1,'新原文','h3')")
    index.sync_video(1)
    new = index.validate_source()
    assert new['content_sha256'] != old['content_sha256'] and new['unit_count'] == 2
    with sqlite3.connect(target) as db:
        assert [r[0] for r in db.execute('SELECT unit_id FROM docs ORDER BY unit_id')] == ['b','c']
        assert db.execute("SELECT count(*) FROM body_fts WHERE body_fts MATCH '甲'").fetchone()[0] == 0


def test_long_canonical_material_pages_without_dropping_segments():
    from shiliu.ask.deep.v2 import canonical_material
    first = _span('first', '甲')
    segments = tuple(EvidenceSegment(segment_id=f's{i}', original_ordinal=i, run_local_ordinal=i,
        start_time=float(i), end_time=float(i+1), source_text=f'第{i}条原文') for i in range(300))
    long = first.model_copy(update={'segments':segments,'segment_ids':tuple(s.segment_id for s in segments),
        'segment_ordinals':tuple(range(300)),'start_time':0,'end_time':300,
        'quote_text':'\n'.join(s.source_text for s in segments)})
    pages, aliases = canonical_material([long])
    assert [len(page.segments) for page in pages.values()] == [300]
    assert aliases['first'] == list(pages)
    assert [segment for page in pages.values() for segment in page.segments] == list(segments)
    assert list(pages) == ['first']


def test_two_concurrent_requests_keep_scope_needs_and_usage_isolated():
    import json
    from concurrent.futures import ThreadPoolExecutor
    class DynamicProvider:
        model = 'test'
        def generate_structured(self, **kwargs):
            payload=json.loads(kwargs['messages'][1]['content'])
            question=payload['question']
            decision=_finish() if payload['recent_actions'] else _continue([question])
            decision['need_updates']=[{'need_id':question,'text':question}]
            return SimpleNamespace(output=V2Decision.model_validate(decision),usage={'total_tokens':1})
    tool=Transcripts(Barrier(2))
    graph=DeepV2Graph(provider_factory=lambda _: DynamicProvider(),transcripts=tool,navigation=None,windows=None)
    left,right=_state(),_state()
    left.update(query='left',filters=ProductSearchFilterRequest(uploader='left'))
    right.update(query='right',filters=ProductSearchFilterRequest(uploader='right'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        outputs=list(pool.map(graph.run,[left,right]))
    for name,state in zip(['left','right'],outputs):
        assert list(state['v2_needs']) == [name]
        assert state['filters'].uploader == name
        assert state['tool_calls'] == 1 and state['v2_controller_calls'] == 2
        assert len(state['usage']) == 2


def test_late_result_is_discarded_before_state_merge():
    provider=Provider([_continue(['late']),_finish()])
    graph=DeepV2Graph(provider_factory=lambda _:provider,transcripts=None,navigation=None,windows=None)
    state=_state()
    graph._execute_batch=lambda actions,s: [{'status':'ok','cache_key':'late','spans':[_span('late','迟到原文')],
        'started_at':s['search_deadline']-1,'ended_at':s['search_deadline']+1}]
    result=graph.run(state)
    assert not result['v2_store']
    events=[e for e in result['events'] if e['event_type']=='v2_tool_result']
    assert events[0]['status']=='timeout' and events[0]['evidence_refs']==[]


def test_audit_store_does_not_enter_controller_context():
    import json
    provider=Provider([_finish()])
    state=_state()
    original=_span('original','完整原文')
    state['evidence_spans']=[original.model_copy(update={'citation_id':f'raw_{i:04d}_'+('x'*100)})
                             for i in range(900)]
    state['events']=[{'event_type':'v2_tool_result','evidence_refs':[s.citation_id for s in state['evidence_spans']],
                     'omitted_refs':[],'action_id':'previous'}]
    graph=DeepV2Graph(provider_factory=lambda _:provider,transcripts=None,navigation=None,windows=None)
    graph.run(state)
    messages=provider.calls[0]['messages']
    payload=json.loads(messages[1]['content'])
    assert sum(len(m['content']) for m in messages)<80000
    assert payload['query_results']==[]
    assert '完整原文' not in messages[1]['content']


def test_controller_keeps_query_findings_when_navigation_metadata_is_large():
    import json
    import pytest
    for case, source_count, evidence_count in [('C12', 30, 50), ('C14', 18, 60), ('C70', 20, 70)]:
        provider = Provider([_finish()])
        state = _state()
        spans = [_span(f'{case}_ref_{index}', '原文证据' * 80) for index in range(evidence_count)]
        state['evidence_spans'] = spans
        state['v2_sources'] = {index: {'video_id': index, 'title': '导航标题' * 300,
            'uploader': '作者', 'subtitle_available': True, 'navigation_summary': '导航' * 2000}
            for index in range(source_count)}
        state['v2_needs'] = {'n': {'need_id': 'n', 'text': '用户必要需求',
            'status': 'open', 'evidence_refs': [spans[0].citation_id], 'gap': '仍需原文'}}
        state['v2_query_results'] = [{'action_id': 'prior', 'kind': 'search_transcripts',
            'query': '必要调查', 'findings': [{'text': '有用的事实', 'evidence_refs': [spans[0].citation_id]}],
            'retained_evidence_refs': [spans[0].citation_id], 'unresolved': ['仍需原文']}]
        DeepV2Graph(provider_factory=lambda _: provider, transcripts=None,
            navigation=None, windows=None).run(state)
        messages = provider.calls[0]['messages']
        payload = json.loads(messages[1]['content'])
        assert payload['query_results'][0]['findings'][0]['text'] == '有用的事实', case
        assert spans[0].citation_id in messages[1]['content']
        assert spans[0].quote_text not in messages[1]['content']
        assert payload['needs'][0]['gap'] == '仍需原文'
        assert sum(len(message['content']) for message in messages) <= 80000


def test_repeated_cached_query_and_gap_rewording_are_not_progress():
    import json
    decisions = [_continue(['same']), _continue([' SAME  ']), _finish()]
    for index, decision in enumerate(decisions[:2]):
        decision['need_updates'] = [{'need_id': 'n', 'text': '必要需求',
            'status': 'open', 'gap': f'改写缺口{index}'}]
    provider = Provider(decisions)
    state = DeepV2Graph(provider_factory=lambda _: provider, transcripts=Transcripts(),
        navigation=None, windows=None).run(_state())
    events = [event for event in state['events'] if event['event_type'] == 'v2_tool_result']
    assert events[1]['cache_hit'] and events[1]['no_new_result']
    assert state['v2_no_progress'] == 1
    assert json.loads(provider.calls[2]['messages'][1]['content'])['repeated_query_advice']


def test_final_context_does_not_fill_from_unrelated_store():
    import json
    builder = DeepV2ContextBuilder(80000)
    builder.preferred_refs = ['required']
    spans = (_span('required', '必要原文'), *(_span(f'unrelated_{index}', '无关原文' * 300)
        for index in range(40)))
    context = builder.build(query='问题', normalized_intent='问题', spans=spans)
    assert [span.citation_id for span in context.spans] == ['required']
    assert len(context.model_context) < 5000
    assert 'citation_allowlist' not in json.loads(context.model_context)


def test_answer_output_budget_is_independent_configuration():
    from shiliu.ask.deep.v2 import AuditedProvider
    provider=Provider([_finish()]);calls=[]
    AuditedProvider(provider,calls,output_limit=1234).generate_structured(max_tokens=8192,messages=[],role="grounded_answer")
    assert provider.calls[0]['max_tokens']==1234 and calls[0]['max_tokens']==1234


def test_materializer_rechecks_current_source_eligibility_and_request_scope(tmp_path):
    import sqlite3
    import pytest
    from shiliu.ask.deep.f1_tools import F1Materializer
    from shiliu.retrieval.models import RetrievalFilters
    path=tmp_path/'eligibility.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE videos(id INTEGER,removed_at TEXT,is_ignored INTEGER)')
        db.execute('CREATE TABLE retrieval_units(unit_id TEXT,video_id INTEGER,unit_type TEXT,removed_at TEXT,is_ignored INTEGER)')
        db.execute("INSERT INTO videos VALUES (7,NULL,1)")
        db.execute("INSERT INTO retrieval_units VALUES ('chunk',7,'transcript_chunk',NULL,0)")
    materializer=F1Materializer(SimpleNamespace(connect=lambda:sqlite3.connect(path)))
    execution=SimpleNamespace(request=SimpleNamespace(filters=SimpleNamespace(retrieval_filters=lambda:RetrievalFilters())),video_ids=(7,))
    with pytest.raises(ValueError,match='eligible'):
        materializer._materialize_candidate(SimpleNamespace(unit_id='chunk'),{},execution=execution,query_index=0)
    with sqlite3.connect(path) as db:db.execute('UPDATE videos SET is_ignored=0')
    execution.video_ids=(3,)
    with pytest.raises(ValueError,match='scope'):
        materializer._materialize_candidate(SimpleNamespace(unit_id='chunk'),{},execution=execution,query_index=0)


def test_final_messages_budget_includes_complete_omission_metadata():
    from shiliu.ask.answer import _answer_messages
    spans=tuple(_span(f'ref_{i}_'+('x'*100),str(i)*400) for i in range(60))
    builder=DeepV2ContextBuilder(18000)
    builder.candidate_refs=[span.citation_id for span in spans]
    context=builder.build(query='question',normalized_intent='question',spans=spans)
    assert builder.omitted
    assert context.spans
    assert sum(len(m['content']) for m in _answer_messages(query='question',context=context))<=18000


def test_live_wal_change_invalidates_f1_content_identity_cache(tmp_path):
    import sqlite3
    import pytest
    from shiliu.retrieval.f1 import F1LexicalIndex
    source,target=tmp_path/'wal-corpus.db',tmp_path/'lexical.sqlite'
    db=sqlite3.connect(source)
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE retrieval_units(unit_id TEXT,unit_type TEXT,source_text TEXT,content_hash TEXT)')
        db.execute("INSERT INTO retrieval_units VALUES ('u','transcript_chunk','甲','h1')")
        db.commit();db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        index=F1LexicalIndex(target,source);index.build();index.validate_source()
        before=(source.stat().st_mtime_ns,source.stat().st_size)
        db.execute("UPDATE retrieval_units SET source_text='乙',content_hash='h2'");db.commit()
        assert before==(source.stat().st_mtime_ns,source.stat().st_size)
        with pytest.raises(ValueError,match='content identity mismatch'):index.validate_source()
    finally:db.close()


def test_companion_partial_multi_video_update_cannot_claim_full_source_identity(tmp_path):
    import sqlite3
    import pytest
    from shiliu.retrieval.f1 import F1LexicalIndex
    source,target=tmp_path/'corpus.db',tmp_path/'lexical.sqlite'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE retrieval_units(unit_id TEXT,unit_type TEXT,video_id INTEGER,source_text TEXT,content_hash TEXT)')
        db.executemany('INSERT INTO retrieval_units VALUES (?,?,?,?,?)',
            [('a','transcript_chunk',1,'甲','h1'),('b','transcript_chunk',2,'乙','h2')])
    index=F1LexicalIndex(target,source);index.build()
    with sqlite3.connect(source) as db:
        db.execute("UPDATE retrieval_units SET source_text='新甲',content_hash='n1' WHERE video_id=1")
        db.execute("UPDATE retrieval_units SET source_text='新乙',content_hash='n2' WHERE video_id=2")
    index.sync_video(1)
    with pytest.raises(ValueError,match='content identity mismatch'):index.validate_source()
    index.sync_video(2)
    assert index.validate_source()['unit_count']==2


def test_query_reduce_keeps_only_cited_chunk_and_never_replays_raw_candidates_to_controller():
    import json

    class TwoChunks:
        def search(self, query, *, filters, video_ids=()):
            return {'spans': [_span(query + '-useful', 'useful original ' + query),
                              _span(query + '-noise', 'irrelevant raw chunk ' + query)],
                    'hits': [], 'available': 2, 'raw_count': 2, 'scope': {}}

    provider = Provider([_continue(['topic']), {'type': 'finish', 'outcome': 'sufficient',
        'answer_evidence_refs': ['topic-useful']}])
    state = DeepV2Graph(provider_factory=lambda _: provider, transcripts=TwoChunks(),
        navigation=None, windows=None).run(_state())
    assert len(state['v2_store']) == 2
    assert state['v2_query_results'][0]['retained_evidence_refs'] == ['topic-useful']
    assert state['v2_query_results'][0]['raw_candidate_count'] == 2
    second_controller = next(call for call in provider.calls if call['role'] == 'agent_action'
        and 'topic-useful' in call['messages'][-1]['content'])
    payload = json.loads(second_controller['messages'][-1]['content'])
    assert payload['query_results'][0]['findings'][0]['evidence_refs'] == ['topic-useful']
    assert 'irrelevant raw chunk' not in second_controller['messages'][-1]['content']
    assert 'useful original' not in second_controller['messages'][-1]['content']
    assert state['v2_final_refs'] == ['topic-useful']
    reduction = next(e for e in state['events'] if e['event_type'] == 'v2_query_reduce')
    assert reduction['candidate_count'] == 2 and reduction['retained_evidence_chars'] < reduction['candidate_chars']


def test_one_loop_supports_parallel_first_round_then_dependent_parallel_second_round():
    import json
    from threading import Barrier

    first_barrier, second_barrier = Barrier(2), Barrier(3)

    class Search:
        def __init__(self):
            self.started = []
        def search(self, query, *, filters, video_ids=()):
            self.started.append((query, time.monotonic()))
            (first_barrier if query in {'A', 'B'} else second_barrier).wait(timeout=2)
            return {'spans': [_span(query, query + ' original')], 'hits': [],
                    'available': 1, 'raw_count': 1, 'scope': {}}

    class DynamicProvider:
        model = 'test-flash'
        def __init__(self):
            self.selector_started = []
        def generate_structured(self, **kwargs):
            payload = json.loads(kwargs['messages'][-1]['content'])
            if kwargs['role'] == 'query_reduce':
                assert 'smallest sufficient set of factual findings' in kwargs['messages'][0]['content']
                assert 'exact short candidate evidence_ref(s)' in kwargs['messages'][0]['content']
                query = payload['current_query']
                self.selector_started.append((query, time.monotonic()))
                (first_barrier if query in {'A', 'B'} else second_barrier).wait(timeout=2)
                fact = {'A': 'A uses X and Y', 'B': 'B uses Y and Z',
                    'X inventor': 'X was invented by P', 'Y inventor': 'Y was invented by Q',
                    'Z inventor': 'Z was invented by R'}[query]
                output = QueryReduction(sufficient=True, findings=[{'subject': query, 'text': fact,
                    'evidence_refs': [payload['candidates'][0]['evidence_ref']]}])
            else:
                assert 'A new entity, keyword, source, or interesting lead' in kwargs['messages'][0]['content']
                assert '25 seconds' in kwargs['messages'][0]['content']
                results = payload['query_results']
                assert payload['research_round'] == {0: 1, 2: 2, 5: 3}[len(results)]
                assert payload['transcript_queries_executed'] == len(results)
                assert payload['elapsed_wall_seconds'] >= 0
                assert payload['remaining']['total_seconds'] > 0
                if not results:
                    output = V2Decision.model_validate(_continue(['A', 'B']))
                elif len(results) == 2:
                    facts = ' '.join(f['text'] for item in results for f in item['findings'])
                    assert all(value in facts for value in ['X', 'Y', 'Z'])
                    output = V2Decision.model_validate(_continue(['X inventor', 'Y inventor', 'Z inventor']))
                else:
                    output = V2Decision(type='finish', outcome='sufficient',
                        answer_evidence_refs=[ref for item in results for ref in item['retained_evidence_refs']])
            return SimpleNamespace(output=output, usage={'prompt_tokens': 10, 'completion_tokens': 5}, latency_ms=1)

    tool, provider = Search(), DynamicProvider()
    state = DeepV2Graph(provider_factory=lambda _: provider, transcripts=tool,
        navigation=None, windows=None).run(_state())
    assert state['termination_reason'] == 'answer_ready'
    assert [item['query_count'] for item in state['v2_round_timings']] == [2, 3]
    assert state['v2_controller_calls'] == 3 and state['tool_calls'] == 5
    assert len(state['v2_query_results']) == 5
    assert max(t for q, t in tool.started if q in {'A', 'B'}) - min(t for q, t in tool.started if q in {'A', 'B'}) < .1
    assert max(t for q, t in provider.selector_started if q in {'A', 'B'}) - min(t for q, t in provider.selector_started if q in {'A', 'B'}) < .1


def test_one_query_can_expand_to_three_parallel_queries_next_round():
    import json
    class Search:
        def search(self, query, *, filters, video_ids=()):
            return {'spans': [_span(query, query + ' source')], 'hits': [],
                    'available': 1, 'raw_count': 1, 'scope': {}}
    class ProviderByResult:
        model = 'test-flash'
        def generate_structured(self, **kwargs):
            payload = json.loads(kwargs['messages'][-1]['content'])
            if kwargs['role'] == 'query_reduce':
                query = payload['current_query']
                fact = 'found X Y Z' if query == 'discover' else query + ' inventor known'
                output = QueryReduction(sufficient=True, findings=[{'subject': query, 'text': fact,
                    'evidence_refs': [payload['candidates'][0]['evidence_ref']]}])
            else:
                results = payload['query_results']
                if not results:
                    output = V2Decision.model_validate(_continue(['discover']))
                elif len(results) == 1:
                    assert 'X Y Z' in results[0]['findings'][0]['text']
                    output = V2Decision.model_validate(_continue(['X', 'Y', 'Z']))
                else:
                    output = V2Decision(type='finish', outcome='sufficient',
                        answer_evidence_refs=[ref for item in results for ref in item['retained_evidence_refs']])
            return SimpleNamespace(output=output, usage={'prompt_tokens': 10}, latency_ms=1)
    state = DeepV2Graph(provider_factory=lambda _: ProviderByResult(), transcripts=Search(),
        navigation=None, windows=None).run(_state())
    assert [item['query_count'] for item in state['v2_round_timings']] == [1, 3]
    assert state['tool_calls'] == 4 and state['termination_reason'] == 'answer_ready'


def test_final_selection_does_not_merge_adjacent_raw_store_chunks():
    base = _span('raw', 'base')
    spans = []
    for index in range(25):
        segment = EvidenceSegment(segment_id=f'segment_{index}', original_ordinal=index,
            run_local_ordinal=index, start_time=float(index), end_time=float(index + 1),
            source_text=f'chunk {index} text')
        spans.append(base.model_copy(update={'citation_id': f'raw_{index}',
            'segment_ids': (segment.segment_id,), 'segment_ordinals': (index,),
            'segments': (segment,), 'quote_text': segment.source_text,
            'start_time': float(index), 'end_time': float(index + 1)}))
    builder = DeepV2ContextBuilder()
    builder.candidate_refs = ['raw_12']
    context = builder.build(query='question', normalized_intent='question', spans=tuple(spans))
    assert context.citation_allowlist == ('raw_12',)
    assert 'chunk 12 text' in context.model_context
    assert 'chunk 11 text' not in context.model_context
    assert 'chunk 13 text' not in context.model_context


def test_query_reduce_rejects_unbound_finding_without_promoting_raw_candidate():
    class InvalidSelector:
        model = 'test-flash'
        def generate_structured(self, **kwargs):
            return SimpleNamespace(output=QueryReduction(sufficient=True,
                findings=[{'subject': 'unknown', 'text': 'invented fact', 'evidence_refs': ['c999']}]),
                usage={'prompt_tokens': 1}, latency_ms=1)
    graph = DeepV2Graph(provider_factory=lambda _: InvalidSelector(), transcripts=None,
        navigation=None, windows=None)
    result = graph._query_reduce_one(V2Decision.model_validate(_continue(['topic'])).actions[0],
        {'spans': [_span('original', 'verified source')]}, 'question', time.monotonic()+5)
    assert result['error'] and result['retained_evidence_refs'] == []
    assert result['findings'] == []


def test_final_context_never_promotes_unselected_audit_candidate():
    builder = DeepV2ContextBuilder()
    context = builder.build(query='question', normalized_intent='question',
        spans=(_span('raw', 'unselected original'),))
    assert context.citation_allowlist == ()
    assert 'unselected original' not in context.model_context


def test_reduce_prompt_keeps_unknown_developer_slot_unknown():
    """Prompt contract only: no natural-language runtime verifier is introduced."""
    import json
    class MissingDeveloperProvider:
        model = 'test-flash'
        def generate_structured(self, **kwargs):
            policy = kwargs['messages'][0]['content']
            payload = json.loads(kwargs['messages'][-1]['content'])
            assert 'unresolved describes missing information, not candidate answers' in policy
            assert 'You may name already evidenced entities' in policy
            assert 'must not enter findings or unresolved as factual state' in policy
            assert 'Model prior knowledge or search hypotheses' in policy
            assert 'describe only the missing attribute' in policy
            assert payload['candidates'][0]['quote'] == 'Game A uses fragmented storytelling.'
            return SimpleNamespace(output=QueryReduction(sufficient=False,
                findings=[{'subject': 'Game A', 'text': 'Game A uses fragmented storytelling.', 'evidence_refs': ['c0']}],
                unresolved=['Game A developer is not yet established.']), usage={}, latency_ms=1)
    graph = DeepV2Graph(provider_factory=lambda _: MissingDeveloperProvider(),
        transcripts=None, navigation=None, windows=None)
    result = graph._query_reduce_one(V2Decision.model_validate(_continue(['Game A developer'])).actions[0],
        {'spans': [_span('original', 'Game A uses fragmented storytelling.')]},
        'Which developer made Game A?', time.monotonic() + 5)
    assert result['findings'][0]['evidence_refs'] == ['original']
    assert result['unresolved'] == ['Game A developer is not yet established.']
    assert 'error' not in result


def test_reduce_uses_source_description_for_identity_and_explicit_subjects():
    import json
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, *_args):
            return [{'id': 1, 'description': 'Game: Best Pals; platform: Steam'}]
    class DB:
        def connect(self): return Connection()
    class Selector:
        model = 'test-flash'
        def generate_structured(self, **kwargs):
            policy = kwargs['messages'][0]['content']
            payload = json.loads(kwargs['messages'][1]['content'])
            assert 'describe several people, products, games, or works in sequence' in policy
            assert 'produce separate subject-bound findings' in policy
            assert payload['candidates'][0]['source_description_for_identity'].startswith('Game: Best Pals')
            return SimpleNamespace(output=QueryReduction(findings=[], sufficient=False,
                unresolved=['The named game is not established by this transcript.']), usage={}, latency_ms=1)
    graph = DeepV2Graph(provider_factory=lambda _: Selector(), transcripts=None,
        navigation=SimpleNamespace(db=DB()), windows=None)
    result = graph._query_reduce_one(V2Decision.model_validate(_continue(['paddling game'])).actions[0],
        {'spans': [_span('original', 'We paddled a boat in one minigame.')]},
        'Which game was this?', time.monotonic() + 5)
    assert not result['findings'] and not result.get('error')


def test_final_prompt_preserves_subject_relations_and_source_roles():
    from shiliu.ask.deep.v2 import AuditedProvider
    from shiliu.ask.context import ContextBuildResult
    context = ContextBuildResult((_span('ref', 'First product costs 100. Second uses Lyocell.'),),
        'context', ('ref',), False, 0)
    class Capture:
        model = 'test-flash'
        def generate_structured(self, **kwargs):
            policy = kwargs['messages'][0]['content']
            assert 'Preserve which action, attribute, price, condition' in policy
            assert 'long quote may discuss several people' in policy
            assert 'Keep uploaders distinct from speakers' in policy
            return SimpleNamespace(output=SimpleNamespace(model_dump=lambda **_: {}), usage={}, latency_ms=1)
    from shiliu.ask.answer import _answer_messages
    AuditedProvider(Capture(), []).generate_structured(role='grounded_answer',
        messages=_answer_messages(query='Compare them', context=context))


def test_product_final_prompt_remains_shared_and_unmodified():
    from shiliu.ask.answer import _answer_messages, _ANSWER_PRODUCT_INSTRUCTIONS
    from shiliu.ask.context import ContextBuildResult
    from shiliu.ask.deep.v2 import AuditedProvider
    context = ContextBuildResult((), '{}', (), False, 0)
    messages = _answer_messages(query='question', context=context)
    class Capture:
        def generate_structured(self, **kwargs):
            assert kwargs['messages'] == messages
            return SimpleNamespace(output=__import__("shiliu.ask.contracts",fromlist=["GroundedAnswerDraft"]).GroundedAnswerDraft(status="insufficient",answer_blocks=[],limitations=[]), usage={}, latency_ms=0)
    AuditedProvider(Capture(), [], use_deep_instructions=False).generate_structured(
        role='grounded_answer', messages=messages, response_schema=dict)


def test_deep_consolidated_initial_and_repair_contract_leave_fast_intact():
    from shiliu.ask.answer import _answer_messages, _repair_messages, _ANSWER_PRODUCT_INSTRUCTIONS
    from shiliu.ask.deep.v2 import deep_answer_messages, DEEP_ANSWER_INSTRUCTIONS
    from shiliu.ask.context import ContextBuildResult
    context = ContextBuildResult((), '{}', (), False, 0)
    for shared in (_answer_messages(query='question', context=context),
                   _repair_messages(query='question', context=context, issues=())):
        before = [dict(message) for message in shared]
        deep = deep_answer_messages(shared)
        assert shared == before
        assert _ANSWER_PRODUCT_INSTRUCTIONS in shared[0]['content']
        assert 'quotes as the only factual material' not in deep[0]['content']
        assert deep[0]['content'].count(DEEP_ANSWER_INSTRUCTIONS) == 1
        assert 'adopting a record alone does not establish this' in deep[0]['content']
        assert 'within blocks that also contain supported transcript-derived content' in deep[0]['content']
        assert 'Keep uploaders distinct from speakers' in deep[0]['content']
        assert deep[1] == shared[1]
        assert deep_answer_messages(deep) == deep
        if 'Repair only' in shared[0]['content']:
            assert deep[0]['content'].startswith('Repair only')


def test_consolidated_context_budget_matches_actual_deep_answer_messages():
    from shiliu.ask.answer import _answer_messages
    from shiliu.ask.deep.v2 import deep_answer_messages
    span = _span('budget-ref', 'supported original ' * 100)
    builder = DeepV2ContextBuilder(budget=8000)
    builder.preferred_refs = [span.citation_id]
    builder.adopted_sources = [{'source_record_id': 'nav:1', 'title': 'source'}]
    context = builder.build(query='question', normalized_intent='question', spans=(span,))
    assert context.spans
    assert sum(len(message['content']) for message in deep_answer_messages(
        _answer_messages(query='question', context=context))) <= builder.budget
