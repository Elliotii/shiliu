"""Normal knowledge operations and deterministic object/provenance constraints."""
from __future__ import annotations

import copy

from test_assistant_w1 import fixture, execute
from test_assistant_consolidation_nb import _run, _topics
from test_assistant_real_use_a import formal


def test_preview_confirmation_respects_thread_and_plan_state(app_paths):
    _, _, _, store, wiki, space, tools = fixture(app_paths)
    proposal, _ = _run(store, space['id'], '先给两页提案，不要直接保存', key='proposal')
    pending = execute(tools, store, proposal, {'topics': _topics()}, name='knowledge_propose')['items'][0]
    assert pending['status'] == 'pending' and not wiki.list_pages(space_id=space['id'])
    foreign, _ = _run(store, space['id'], '确认这个提案', key='foreign')
    denied = execute(tools, store, foreign, {'plan_id': pending['id'], 'expected_version': 1, 'accept': True}, name='knowledge_confirm')
    assert denied['error_code'] == 'knowledge_plan_request_mismatch'
    rejection, _ = _run(store, space['id'], '拒绝这个提案', thread_id=proposal['thread_id'], key='reject')
    rejected = execute(tools, store, rejection, {'plan_id': pending['id'], 'expected_version': 1, 'accept': False}, name='knowledge_confirm')
    assert rejected['status'] == 'ok' and rejected['items'][0]['status'] == 'rejected'
    later, _ = _run(store, space['id'], '继续看看提案', thread_id=proposal['thread_id'], key='late')
    late = execute(tools, store, later, {'plan_id': pending['id'], 'expected_version': 1, 'accept': True}, name='knowledge_confirm')
    assert late['status'] != 'ok'
    assert not wiki.list_pages(space_id=space['id'])


def test_natural_save_and_short_edit_keep_same_page(app_paths):
    _, _, _, store, wiki, space, tools = fixture(app_paths)
    research, _ = formal(store, space, '可以把判断改为“条件未知时保留未知”，其他不动。')
    initial, _ = _run(store, space['id'], '帮我把这条笔记加到知识页里', thread_id=research['thread_id'], key='save')
    topic = _topics()[0]
    saved = execute(tools, store, initial, {'topics': [topic]})
    assert saved['status'] == 'ok', saved
    page_id = saved['items'][0]['results']['0']['page_id']
    claimed = store.claim_next_run()
    assert store.complete_run(initial['id'], epoch=claimed['run_epoch'],
        answer='我可以把判断更正为“条件未知时保留未知”，其他不动。', usage={})
    edit, _ = _run(store, space['id'], '可以，改吧', thread_id=research['thread_id'], key='edit')
    revised = copy.deepcopy(topic)
    revised['expected_version'] = 1
    revised['blocks'][0]['markdown'] = '条件未知时保留未知。'
    result = execute(tools, store, edit, {'topics': [revised]})
    assert result['status'] == 'ok', result
    page = wiki.get_page(page_id, space_id=space['id'])
    assert page['version'] == 2 and page['blocks'][0]['markdown'] == '条件未知时保留未知。'
    assert len(wiki.list_pages(space_id=space['id'])) == 1


def test_personal_paraphrase_keeps_actual_user_quote(app_paths):
    _, _, _, store, wiki, space, tools = fixture(app_paths)
    run, ctx = _run(store, space['id'], '请保存我的笔记：我喜欢清淡口味', key='personal')
    quote_id = ctx['thread']['messages'][-1]['id']
    body = '我偏好清淡口味'
    result = execute(tools, store, run, {'topics': [{'title': '我的笔记', 'purpose': '保留口味偏好', 'blocks': [
        {'role': 'personal', 'heading': '口味偏好', 'markdown': body, 'user_quote': '我喜欢清淡口味',
         'user_message_id': quote_id}]}]})
    assert result['status'] == 'ok', result
    block = wiki.list_pages(space_id=space['id'])[0]['blocks'][0]
    assert block['markdown'] == body
    assert block['user_quote'] == '我喜欢清淡口味' and block['user_message_id'] == quote_id
    assert block['assessment'] == 'user_explicit'
