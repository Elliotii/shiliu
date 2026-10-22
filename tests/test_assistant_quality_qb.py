from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

import pytest

from shiliu.assistant.memory import MemoryService
from shiliu.assistant.tools import AssistantToolRegistry
from test_assistant_stage_c import _add_material, _services


def test_material_projection_uses_actual_payload_and_keeps_wiki_lineage_distinct():
    from shiliu.assistant.delivery import project_tool_result, read_evidence
    read = {'status':'ok','source_refs':['video:7:rev'],'coverage':{'requested_view':'transcript'},
        'items':[{'source_ref':'video:7','video':{'title':'甲','description':'附带简介'},'content':'一段',
                  'provenance':{'content_position':{'start':100,'end':102,'total':1000}}}]}
    projected = project_tool_result('collection_read',read,result_ref='run-result:r:read',sources=None)
    spans, materials = read_evidence('collection_read',projected,result_ref='run-result:r:read')
    assert spans[0]['start']==100 and spans[0]['end']==102
    assert any(m['view']=='metadata' for m in materials)
    assert not any(m['view']=='description' for m in materials)
    assert not materials[-1]['complete'] and materials[-1]['title']=='甲'
    wiki = {'source_refs':['video:7:rev'],'items':[{'id':'awiki_1','version':2,'title':'知识页',
            'blocks':[{'stable_id':'block-2','markdown':'派生判断'}]}]}
    _, pages = read_evidence('knowledge_read',wiki,result_ref='run-result:r:wiki')
    assert pages[0]['source_ref']=='wiki:awiki_1:2' and pages[0]['lineage_refs']==['video:7:rev']
    assert pages[0]['position']['block_ids']==['block-2'] and not pages[0]['complete']
    assert read_evidence('collection_read',{'items':[]},result_ref='run-result:r:unseen') == ([],[])
    from shiliu.assistant.task_notes import TaskNoteService
    note = {'id':'note','note_version':1,'checkpoint':{'format_version':1,'text':'摘要接续，不代表原文通读',
            'material_index':materials}}
    assert TaskNoteService.material_index(note)==materials
    assert '不代表原文通读' in TaskNoteService.render(note)


def test_missing_source_local_repair_and_title_options(app_paths):
    db, artifacts, sources, store, wiki = _services(app_paths)
    source_id = db.create_favorite_source(folder_id=887, folder_title='Q-B isolated', history_policy='all')
    video_id = _add_material(db, artifacts, source_id, bvid='BV1QB0000001', title='当前版本材料', text='有效正文')
    ref = f'video:{video_id}:{sources.snapshots.capture(video_id).revision}'
    space = store.create_space(name='Q-B isolated', source_ids=[source_id])
    thread = store.create_thread(space['id'])
    run = store.create_run(thread['id'], text='整理成两个主题提案，等待我确认', request_id='qb-repair')
    registry = AssistantToolRegistry(sources=sources, memories=MemoryService(db), store=store, wiki=wiki)
    store.begin_tool_call(run['id'], ordinal=1, call_id='read', name='collection_read', arguments={})
    store.finish_tool_call(run['id'], call_id='read', result={
        'status': 'ok', 'source_refs': [ref], 'items': [{'video': {'title': '当前版本材料'}}],
    })
    topics = [
        {'title': '来源主题', 'purpose': '保存事实', 'blocks': [
            {'role': 'source', 'heading': '材料', 'markdown': '有效正文'}]},
        {'title': '独立分析', 'purpose': '保存判断', 'blocks': [
            {'role': 'analysis', 'heading': '判断', 'markdown': '待核对'}]},
    ]
    context = store.run_context(run['id'])
    invalid = asyncio.run(registry.execute(name='knowledge_propose',
        arguments={'topics': topics}, call_id='p1', run_context=context))
    assert invalid['error_code'] == 'knowledge_plan_not_confirmable'
    assert invalid['items'][0]['issues'][0]['path'] == 'topics[0].blocks[0].source_refs'
    candidate = invalid['items'][0]['candidates'][0]
    assert candidate['title'] == '当前版本材料' and 'source_ref' not in candidate
    assert len(wiki.list_discussion_plans(space_id=space['id'])) == 1
    store.begin_tool_call(run['id'], ordinal=2, call_id='p1', name='knowledge_propose', arguments={})
    store.finish_tool_call(run['id'], call_id='p1', result=invalid)
    topics[0]['blocks'][0]['source_refs'] = [candidate['handle']]
    with db.connect() as connection:
        working = json.loads(connection.execute('SELECT working_state_json FROM assistant_runs WHERE id=?', (run['id'],)).fetchone()[0])
        working['model_delivered_materials'] = [{'source_ref': ref, 'kind': 'collection_read', 'view': 'summary', 'projection': '正文'}]
        connection.execute('UPDATE assistant_runs SET working_state_json=? WHERE id=?', (json.dumps(working), run['id']))
    repaired = asyncio.run(registry.execute(name='knowledge_save_discussion',
        arguments={'plan_id': invalid['items'][0]['id'], 'expected_version': 1,
                   'corrections': [{'path': 'topics[0].blocks[0].source_refs', 'value': [candidate['handle']]}]},
        call_id='p2', run_context=context))
    assert repaired['status'] == 'ok' and repaired['items'][0]['confirmable']
    plan = repaired['items'][0]
    assert plan['payload']['topics'][0]['blocks'][0]['source_refs'] == [ref]
    assert plan['payload']['topics'][1]['blocks'][0]['source_refs'] == []
    options = wiki.plan_source_options(plan['id'], space_id=space['id'])
    assert options[0]['title'] == '当前版本材料' and options[0]['selected']
    assert wiki.plan_selected_source_statuses(plan['id'], space_id=space['id']) == [
        {'source_ref': ref, 'title': '当前版本材料', 'status': 'available'}]
    assert wiki.plan_source_options(plan['id'], space_id=space['id'], query='当前版本') == options
    store.begin_tool_call(run['id'], ordinal=3, call_id='p2', name='knowledge_propose', arguments={})
    store.finish_tool_call(run['id'], call_id='p2', result=repaired)
    blocked = asyncio.run(registry.execute(name='knowledge_propose',
        arguments={'topics': topics}, call_id='p3', run_context=context))
    assert blocked['items'][0]['id'] == plan['id'] and blocked['status'] == 'ok'
    assert len(wiki.list_discussion_plans(space_id=space['id'])) == 1
    with db.connect() as connection:
        video = connection.execute('SELECT summary_path FROM videos WHERE id=?', (video_id,)).fetchone()
    artifacts.write_text(Path(video['summary_path']), '有效正文的新版本')
    current_ref = f'video:{video_id}:{sources.snapshots.capture(video_id).revision}'
    assert current_ref != ref
    assert wiki.plan_source_options(plan['id'], space_id=space['id']) == []
    assert wiki.plan_selected_source_statuses(plan['id'], space_id=space['id']) == [
        {'source_ref': ref, 'title': '当前版本材料', 'status': 'revision_changed'}]
    assert not wiki.list_discussion_plans(space_id=space['id'])[0]['confirmable']
    old_topics = copy.deepcopy(plan['payload']['topics'])
    with pytest.raises(ValueError, match='source_revision_changed'):
        wiki.revise_discussion_plan(plan['id'], space_id=space['id'], expected_version=plan['version'],
            topics=old_topics, omitted=[], operation_key='qb-r1-unchanged')
    current_options = wiki.plan_source_options(plan['id'], space_id=space['id'], query='当前版本')
    assert any(item['source_ref'] == current_ref for item in current_options)
    old_topics[0]['blocks'][0]['source_refs'] = [current_ref]
    with db.connect() as connection:
        working['model_delivered_materials'] = [{'source_ref': current_ref, 'kind': 'collection_read', 'view': 'summary', 'projection': '正文'}]
        connection.execute('UPDATE assistant_runs SET working_state_json=? WHERE id=?', (json.dumps(working), run['id']))
    revised = wiki.revise_discussion_plan(plan['id'], space_id=space['id'], expected_version=plan['version'],
        topics=old_topics, omitted=[], operation_key='qb-r1-user-replaced')
    assert revised['confirmable'] and revised['version'] == plan['version'] + 1
    assert revised['payload']['topics'][0]['blocks'][0]['source_refs'] == [current_ref]
    assert ref not in json.dumps(revised['payload'], ensure_ascii=False)
