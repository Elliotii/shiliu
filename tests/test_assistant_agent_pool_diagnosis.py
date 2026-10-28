"""Two no-paid Agent runs: single-connection failure vs Application default pool."""
import asyncio
from contextlib import contextmanager
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import threading
import traceback

import httpx
import pytest

from assistant_agent_pg_fixture import assistant_agent_resources
from test_assistant_bm25_search_read_pg import helpers
from shiliu.assistant.pg_store import PgAssistantRunStore
from shiliu.assistant.provider import OpenAICompatibleAssistantProvider, ModelTurn, NativeToolCall
from shiliu.assistant.runtime import AssistantRuntime, AssistantExecutionGraph
from shiliu.assistant.snapshots import SourceSnapshotStore
from shiliu.assistant.sources import CollectionSourceService
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.domain import FavoriteItem
from shiliu.retrieval.bm25 import RANKING_VERSION
from shiliu.retrieval.consolidation import SearchResultConsolidator
from shiliu.retrieval.coordinator import ProjectionWorker
from shiliu.retrieval.dense import PgExactDenseIndex
from shiliu.retrieval.enrichment import EvidenceEnricher
from shiliu.retrieval.hybrid import HybridRetrievalService
from shiliu.retrieval.orchestrator import SearchOrchestrator
from shiliu.retrieval.product_search import ProductSearchService
from shiliu.storage.errors import StorageError

pytestmark = pytest.mark.skipif(os.environ.get("SHILIU_BM25_PRODUCT_TEST") != "1",
    reason="explicit guarded 55487 fixture required")
OLD = Path('/absolute/historical/new-systems/agent-job-prep/Shiiu-1023-assistant-agent-smoke-runtime-20261027')


@pytest.mark.parametrize("single", [True, False], ids=["single-connection", "application-default"])
def test_agent_pool_control_and_scripted_search_read(monkeypatch, single):
    out = Path(os.environ["SHILIU_ASSISTANT_POOL_DIAG_OUT"]) / ("single" if single else "default")
    out.mkdir(parents=True, exist_ok=False)
    def write(name, value):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")
    def forbidden(*args, **kwargs):
        pytest.fail("diagnosis forbids networked models and credentials")
    monkeypatch.setattr(httpx, "post", forbidden)
    monkeypatch.setattr(httpx, "stream", forbidden)
    monkeypatch.setattr(OpenAICompatibleAssistantProvider, "_post", forbidden)
    monkeypatch.setattr(OpenAICompatibleAssistantProvider, "_stream_prepared", forbidden)
    import shiliu.config
    monkeypatch.setattr(shiliu.config, "load_api_key", forbidden)
    old_seal = sha256((OLD / 'EVIDENCE_SHA256.json').read_bytes()).hexdigest()
    corpus = json.loads((OLD / 'SYNTHETIC_CORPUS.json').read_text())
    question = json.loads((OLD / 'PLAN.json').read_text())['questions'][0]
    with assistant_agent_resources(single_connection_control=single,
            cleanup_receipt=lambda value: write('CLEANUP.json', value)) as (db, artifacts, lexical):
        settings = asdict(db.pg.settings)
        assert settings['max_size'] == (1 if single else 8)
        assert settings['timeout'] == 5 and settings['lock_timeout_ms'] == 3000
        source_id = db.create_favorite_source(folder_id=901, folder_title='Pool diagnosis synthetic')
        videos = []
        for index, item in enumerate(corpus):
            bvid = f'BV{901 + index:010d}'
            db.record_source_snapshot(source_id, [FavoriteItem(bvid=bvid,
                title=('故障复盘与证据边界', '缓存与灰度验收')[index], uploader='合成讲者',
                favorite_time=1700000000)], processing_profile='formal', authoritative=False)
            video = db.get_video_by_source(bvid)['id']
            batch = artifacts.batch(video)
            ref = batch._save('subtitle-raw.json', item['raw_json'].encode(), media_type='application/json')
            batch.commit(lambda conn: db.update_video(video, raw_subtitle_path=ref,
                subtitle_source='human', subtitle_language='zh', status='completed', conn=conn))
            ProjectionWorker(lexical).run_one(video_id=video)
            videos.append(video)
        dense = PgExactDenseIndex(db=db, provider=helpers.FixedProvider(), lexical=lexical)
        dense.rebuild()
        hybrid = HybridRetrievalService(lexical=lexical, dense=dense)
        raw = SearchOrchestrator(db=db, lexical=lexical, dense_factory=lambda: dense,
            hybrid_factory=lambda: hybrid, persist_trace=False)
        product = ProductSearchService(db=db, raw_search=raw, consolidator=SearchResultConsolidator(),
            enricher=EvidenceEnricher(db=db, artifacts=artifacts), persist_trace=False)
        sources = CollectionSourceService(db=db, artifacts=artifacts,
            snapshots=SourceSnapshotStore(db, artifacts), product_search=product)
        searches = []
        actual_search = product.search_with_raw
        def observe_search(*args, **kwargs):
            response, result = actual_search(*args, **kwargs)
            searches.append({'request': args[0].model_dump(mode='json'), 'raw': response.as_dict()})
            return response, result
        monkeypatch.setattr(product, 'search_with_raw', observe_search)
        class ScriptedProvider(OpenAICompatibleAssistantProvider):
            def __init__(self):
                super().__init__(base_url='https://api.deepseek.com/v1', api_key='offline', model='deepseek-v4-flash')
                self.requests, self.read_args = [], None
            def send_prepared(self, request, **kwargs):
                self.requests.append(request.body)
                write(f'prepared-{len(self.requests)}.json', request.body)
                if len(self.requests) == 1:
                    return ModelTurn('', [NativeToolCall('script-search', 'search_knowledge', {
                        'query': '灰度发布 来源版本不一致', 'sources': ['collection'],
                        'collection_scope': 'transcript_chunk'})], 'tool_calls', {'total_tokens': 1})
                if len(self.requests) == 2:
                    tool = next(m for m in reversed(request.body['messages']) if m['role'] == 'tool')
                    value = json.loads(tool['content'])
                    candidates = value['items'][0]['candidates']
                    hint = next(h for card in candidates if card['video_id'] == videos[1]
                                for h in card['read_hints'] if h['start_time'] >= 180)
                    self.read_args = hint['read_args']
                    return ModelTurn('', [NativeToolCall('script-read', 'collection_read', self.read_args)],
                        'tool_calls', {'total_tokens': 1})
                assert len(self.requests) == 3
                tool = next(m for m in reversed(request.body['messages']) if m['role'] == 'tool')
                value = json.loads(tool['content'])
                assert '先停止发布并回滚应用包' in value['items'][0]['content']
                assert value['coverage']['read_position']['start'] > 0
                return ModelTurn('合成测试动作已完成，来源版本不一致时停止发布并回滚应用包。', [],
                    'stop', {'total_tokens': 1})
        provider = ScriptedProvider()
        store = PgAssistantRunStore(db)
        runtime = AssistantRuntime(store=store, sources=sources, context7=None,
            provider_factory=lambda: provider, embedding_provider=helpers.FixedProvider())
        tools = AssistantToolRegistry(store=store, sources=sources, memories=runtime.memories, wiki=runtime.wiki)
        graph = AssistantExecutionGraph(store=store, memories=runtime.memories, tools=tools,
            provider_factory=lambda: provider)
        space = store.create_space(name='Pool diagnosis', source_ids=[source_id])
        thread = store.create_thread(space['id'])
        created = store.create_run(thread['id'], text=question, request_id='synthetic-once')
        run = store.claim_next_run()
        assert run['id'] == created['id']
        with db.connect(read_only=True) as conn:
            identity = conn.execute('SELECT current_user,current_database(),pg_backend_pid()').fetchone()
        write('SETUP.json', {'pool_settings': settings, 'identity': identity,
            'question_unchanged': question, 'paid_calls': 0, 'synthetic_actions': True})
        # Test-local observation at the actual pool acquisition boundary.
        pool = db.pg._pool
        getconn, putconn = pool.getconn, pool.putconn
        holders, timeouts, maximum = {}, [], [0]
        lock = threading.Lock()
        def traced_getconn(*args, **kwargs):
            waiting_stack = traceback.format_stack()
            try:
                connection = getconn(*args, **kwargs)
            except Exception:
                with lock:
                    timeouts.append({'exception_traceback': traceback.format_exc(), 'waiting_stack': waiting_stack,
                        'holders': list(holders.values()), 'pool_stats': pool.get_stats()})
                write('ACQUISITION_FAILURE.json', timeouts)
                raise
            with lock:
                holders[id(connection)] = {'thread': threading.get_ident(),
                    'backend_pid': connection.info.backend_pid, 'acquired_stack': waiting_stack}
                maximum[0] = max(maximum[0], len(holders))
            return connection
        def traced_putconn(connection, *args, **kwargs):
            with lock:
                holders.pop(id(connection), None)
            return putconn(connection, *args, **kwargs)
        failure = None
        with monkeypatch.context() as observer:
            observer.setattr(pool, 'getconn', traced_getconn)
            observer.setattr(pool, 'putconn', traced_putconn)
            try:
                asyncio.run(graph.run(run))
            except Exception as exc:
                failure = exc
                (out / 'PYTHON_EXCEPTION.txt').write_text(traceback.format_exc())
        result = store.get_run(run['id'])
        write('RUN.json', result)
        write('SEARCHES.json', searches)
        write('THREAD.json', store.get_thread(thread['id']))
        write('EVENTS.json', store.events(run['id']))
        with db.connect(read_only=True) as conn:
            receipts = conn.execute('SELECT call_id,name,args_json,result_json,status FROM shiliu.assistant_tool_calls '
                'WHERE workspace_id=%s AND run_id=%s ORDER BY ordinal', (db.workspace_id, run['id'])).fetchall()
            projections = conn.execute('SELECT role,provider_payload_json FROM shiliu.assistant_messages '
                'WHERE workspace_id=%s AND run_id=%s ORDER BY seq', (db.workspace_id, run['id'])).fetchall()
        write('TOOLS.json', receipts)
        write('FROZEN_PROJECTIONS.json', projections)
        if single:
            assert isinstance(failure, StorageError) and failure.category == 'pool_timeout'
            assert timeouts and timeouts[0]['holders'] and not provider.requests
            assert timeouts[0]['pool_stats']['pool_size'] == 1
        else:
            assert failure is None and not timeouts
            assert result['status'] == 'completed' and len(provider.requests) == 3
            assert any(s['request']['scope'] == 'transcript_chunk' and
                s['raw']['index_identity']['lexical_index_version'] == RANKING_VERSION for s in searches)
            read = next(r for r in receipts if r['name'] == 'collection_read')
            assert read['args_json'] == provider.read_args
            text = read['result_json']['items'][0]['content']
            position = read['result_json']['coverage']['read_position']
            assert text == corpus[1]['raw_json'][position['start']:position['end']]
            read_projection = next(p['provider_payload_json']['model_projection'] for p in projections
                if p['role'] == 'tool' and p['provider_payload_json'].get('name') == 'collection_read')
            assert read_projection['delivery']['confirmed'] and read_projection['read_spans']
            assert maximum[0] >= 2
        write('RESULT.json', {'status': result['status'], 'expected_pool_failure': single,
            'scripted_model_calls': len(provider.requests), 'paid_calls': 0, 'http_attempts': 0,
            'max_simultaneous_checkouts': maximum[0], 'pool_stats': pool.get_stats(),
            'old_evidence_seal_unchanged': sha256((OLD / 'EVIDENCE_SHA256.json').read_bytes()).hexdigest() == old_seal})
