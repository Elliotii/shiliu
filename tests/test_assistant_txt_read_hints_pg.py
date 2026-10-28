"""Real TXT Snapshot capture and paired JSON, only guarded random 55487 children."""
import asyncio
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest
import httpx

from assistant_agent_pg_fixture import assistant_agent_resources
from test_assistant_bm25_search_read_pg import helpers
from shiliu.artifacts import ExportArtifactStore, format_timestamp
from shiliu.assistant.contracts import KnowledgeSearchArgs
from shiliu.assistant.delivery import project_tool_result
from shiliu.assistant.snapshots import CapturedSource, SourceSnapshotStore
from shiliu.assistant.sources import CollectionSourceService, SourceScope
from shiliu.assistant.tools import AssistantToolRegistry
from shiliu.domain import FavoriteItem, SubtitleSegment
from shiliu.retrieval.bm25 import RANKING_VERSION
from shiliu.retrieval.consolidation import SearchResultConsolidator
from shiliu.retrieval.coordinator import ProjectionWorker
from shiliu.retrieval.dense import PgExactDenseIndex
from shiliu.retrieval.enrichment import EvidenceEnricher
from shiliu.retrieval.hybrid import HybridRetrievalService
from shiliu.retrieval.orchestrator import SearchOrchestrator
from shiliu.retrieval.product_search import ProductSearchService

pytestmark = pytest.mark.skipif(os.environ.get('SHILIU_BM25_PRODUCT_TEST') != '1',
    reason='explicit guarded 55487 fixture required')


@pytest.mark.parametrize('legacy', [False, True], ids=['shared-version', 'independent-legacy-hashes'])
def test_real_txt_snapshot_hint_pairing_and_rejections(tmp_path, monkeypatch, legacy):
    def forbidden(*args, **kwargs):
        pytest.fail('TXT hint validation forbids models, network calls and encoding')
    monkeypatch.setattr(httpx, 'post', forbidden)
    monkeypatch.setattr(httpx, 'stream', forbidden)
    monkeypatch.setattr(helpers.FixedProvider, 'embed_query', forbidden)
    monkeypatch.setattr(helpers.FixedProvider, 'embed_documents', forbidden)
    evidence = Path(os.environ['SHILIU_ASSISTANT_TXT_FIX_OUT']) / ('legacy' if legacy else 'shared')
    evidence.mkdir(parents=True, exist_ok=False)
    def write(name, value):
        (evidence / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')
    with assistant_agent_resources(cleanup_receipt=lambda value: write('CLEANUP.json', value)) as (db, artifacts, lexical):
        sid = db.create_favorite_source(folder_id=1001, folder_title='TXT synthetic')
        bvid = 'BV0000001001'
        db.record_source_snapshot(sid, [FavoriteItem(bvid=bvid, title='TXT raw pair',
            uploader='合成作者', favorite_time=1700000000)], processing_profile='formal', authoritative=False)
        vid = db.get_video_by_source(bvid)['id']
        segments = [SubtitleSegment.model_validate(s) for s in [
            {'from': 0, 'to': 10, 'content': '缓存命中 alpha 日常说明。' + '中文前文。' * 160},
            {'from': 11, 'to': 12, 'content': ' \n '},
            {'from': 180, 'to': 205, 'content': '缓存命中 alpha NeedleUni 后段验收。\n条件：先停止发布，再回滚。'},
            {'from': 206, 'to': 207, 'content': ''},
            {'from': 400, 'to': 450, 'content': '后文。' * 350},
        ]]
        # The existing export owns newline/timestamp formatting, not this test.
        json_path, txt_path = ExportArtifactStore(tmp_path / 'export').save_raw_subtitle(bvid, segments)
        raw, txt = json_path.read_bytes(), txt_path.read_text()
        json_hash, txt_hash = sha256(raw).hexdigest(), sha256(txt.encode()).hexdigest()
        assert json_hash != txt_hash and txt.endswith('\n')
        batch = artifacts.batch(vid)
        if legacy:
            json_ref = batch._save('subtitle-raw.json', raw)
            txt_ref = batch._save('subtitle-raw.txt', txt.encode(), media_type='text/plain')
        else:
            json_ref, txt_ref = batch.save_raw_subtitle_bytes(raw)
        batch.commit(lambda c: db.update_video(vid, raw_subtitle_path=txt_ref,
            subtitle_source='human', subtitle_language='zh', status='completed', conn=c))
        ProjectionWorker(lexical).run_one(video_id=vid)
        dense = PgExactDenseIndex(db=db, provider=helpers.FixedProvider(), lexical=lexical)
        # ASCII entity routing is lexical; no document or query encoding is needed.
        hybrid = HybridRetrievalService(lexical=lexical, dense=dense)
        raw_search = SearchOrchestrator(db=db, lexical=lexical, dense_factory=lambda: dense,
            hybrid_factory=lambda: hybrid, persist_trace=False)
        product = ProductSearchService(db=db, raw_search=raw_search,
            consolidator=SearchResultConsolidator(), enricher=EvidenceEnricher(db=db, artifacts=artifacts),
            persist_trace=False)
        sources = CollectionSourceService(db=db, artifacts=artifacts,
            snapshots=SourceSnapshotStore(db, artifacts), product_search=product)
        registry = AssistantToolRegistry(store=None, sources=sources, memories=None)
        observed = []
        actual = product.search_with_raw
        def record(*args, **kwargs):
            response, value = actual(*args, **kwargs)
            observed.append(response.as_dict())
            return response, value
        product.search_with_raw = record
        context = {'space': {'id': 1, 'scope_version': 1, 'source_ids': [sid],
            'video_ids': [vid], 'all_active': False}, 'thread': {'id': 'isolated-txt'}}
        found = asyncio.run(registry.search_knowledge(KnowledgeSearchArgs(query='NeedleUni',
            sources=['collection'], collection_scope='transcript_chunk'), call_id='txt-search', run_context=context))
        assert found['status'] == 'ok'
        candidate = found['items'][0]['candidates'][0]
        assert candidate['read_hints'] and not candidate['read_hint_unavailable_reasons']
        assert observed[0]['index_identity']['lexical_index_version'] == RANKING_VERSION
        captured = sources.snapshots.load(vid, candidate['revision'])
        assert captured.snapshot['materials']['raw_subtitle'] == txt
        assert captured.snapshot['material_hashes']['raw_subtitle'] == txt_hash
        assert artifacts.objects.manifest(version_id=json_ref)['source_version'] == json_hash
        assert artifacts.objects.manifest(version_id=txt_ref)['source_version'] == (txt_hash if legacy else json_hash)
        projected = project_tool_result('search_knowledge', found, result_ref='test:txt', sources=sources)
        hint = projected['items'][0]['candidates'][0]['read_hints'][0]
        assert hint['start_time'] == 180
        prefix = [f'[{format_timestamp(s.start)} --> {format_timestamp(s.end)}] {s.content}\n'
                  for s in segments[:2]]
        expected = len(''.join(prefix)) - 500
        scope = SourceScope(source_db_ids=frozenset({sid}), video_ids=frozenset({vid}))
        first = sources.read(call_id='read1', scope=scope, **hint['read_args'], max_characters=1000)
        assert first.status == 'ok' and first.coverage['read_position']['start'] == expected > 0
        assert first.items[0]['content'] == txt[expected:expected + 1000]
        assert 'NeedleUni 后段验收。\n条件：' in first.items[0]['content']
        small = sources.read(call_id='page1', scope=scope, **hint['read_args'], max_characters=1000)
        assert small.next_cursor
        next_page = sources.read(call_id='page2', scope=scope, source_ref=hint['read_args']['source_ref'],
            view='transcript', cursor=small.next_cursor, max_characters=40000)
        assert next_page.coverage['read_position']['start'] == small.coverage['read_position']['end']
        assert small.items[0]['content'] + next_page.items[0]['content'] == txt[expected:]
        # A captured body cannot be substituted even with its hash recomputed.
        changed = deepcopy(captured.snapshot)
        changed['materials']['raw_subtitle'] += '篡改\n'
        changed['material_hashes']['raw_subtitle'] = sha256(changed['materials']['raw_subtitle'].encode()).hexdigest()
        assert sources.search_read_hints(candidate, CapturedSource(captured.revision, captured.snapshot_ref, changed)) == ([], ['snapshot_text_mismatch'])
        unit_id = hint['unit_id']
        with db.connect() as c:
            old_text = c.execute('SELECT source_text FROM shiliu.retrieval_units WHERE workspace_id=%s AND unit_id=%s',
                (db.workspace_id, unit_id)).fetchone()['source_text']
            c.execute('UPDATE shiliu.retrieval_units SET source_text=%s WHERE workspace_id=%s AND unit_id=%s',
                ('错配Chunk', db.workspace_id, unit_id))
        assert sources.search_read_hints(candidate, captured) == ([], ['chunk_segment_mapping_failed'])
        with db.connect() as c:
            c.execute('UPDATE shiliu.retrieval_units SET source_text=%s WHERE workspace_id=%s AND unit_id=%s',
                (old_text, db.workspace_id, unit_id))
        # A current JSON head with a different projection is not an old TXT pair.
        incompatible = artifacts.batch(vid)
        new_raw = raw.replace(b'NeedleUni', b'Different')
        incompatible._save('subtitle-raw.json', new_raw)
        incompatible.commit(lambda c: None)
        if legacy:
            assert sources.search_read_hints(candidate, captured) == ([], ['source_unavailable'])
            # Even matching new JSON/TXT heads cannot authorize an old legacy ref.
            newer = artifacts.batch(vid)
            newer._save('subtitle-raw.txt', txt.replace('NeedleUni', 'Different').encode(), media_type='text/plain')
            newer.commit(lambda c: None)
            assert sources.search_read_hints(candidate, captured) == ([], ['source_unavailable'])
        else:
            # A real shared historical version remains exact, regardless of head.
            assert sources.search_read_hints(candidate, captured)[0] == candidate['read_hints']
            # The shared-version path still must prove the complete TXT rendering.
            invalid_pair = artifacts.batch(vid)
            invalid_txt = invalid_pair._save('subtitle-raw.txt', (txt + '额外正文\n').encode(),
                version=sha256(new_raw).hexdigest(), media_type='text/plain')
            invalid_pair.commit(lambda c: db.update_video(vid, raw_subtitle_path=invalid_txt, conn=c))
            ProjectionWorker(lexical).run_one(video_id=vid)
            invalid_result = asyncio.run(registry.search_knowledge(KnowledgeSearchArgs(query='Different',
                sources=['collection'], collection_scope='transcript_chunk'), call_id='invalid-txt', run_context=context))
            invalid_card = invalid_result['items'][0]['candidates'][0]
            assert invalid_result['status'] == 'ok' and invalid_card['read_hints'] == []
            assert invalid_card['read_hint_unavailable_reasons'] == ['snapshot_text_mismatch']
        with db.connect(read_only=True) as c:
            identity = c.execute('SELECT current_user,current_database()').fetchone()
        write('RESULT.json', {'status': 'passed', 'identity': identity, 'pool_settings': vars(db.pg.settings),
            'legacy': legacy, 'json_hash': json_hash, 'snapshot_txt_hash': txt_hash,
            'target_original_ordinal': 2, 'read_start': expected, 'raw_search': observed,
            'search': found, 'projection': projected, 'read': first.model_dump(mode='json'),
            'small_page': small.model_dump(mode='json'), 'continuation': next_page.model_dump(mode='json'),
            'snapshot_mismatch_rejected': True, 'chunk_mismatch_rejected': True,
            'legacy_wrong_pair_and_historical_ref_rejected': legacy, 'paid_calls': 0})
