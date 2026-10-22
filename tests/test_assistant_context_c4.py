from __future__ import annotations

import asyncio
import json

from shiliu.assistant.provider import ModelTurn, NativeToolCall
from shiliu.assistant.context import SYSTEM_RULES
from test_assistant_context_c2 import c2, running
from test_assistant_context_c3 import c3, history, notes
from test_assistant_stage_c import _add_material


def test_five_transcripts_full_runtime_256k_with_checkpoint_and_ordinary_append(c3):
    lengths = [5751, 9396, 9323, 13930, 4965]
    assert sum(lengths) == 43365
    source = c3.db.create_favorite_source(folder_id=54, folder_title='五份合成字幕', history_policy='all')
    documents = []
    for index, length in enumerate(lengths):
        text = f'字幕{index}起点。' + '合成事实与条件。' * length
        suffix = f'字幕{index}终点。'
        text = text[:length-len(suffix)] + suffix
        assert len(text) == length
        bvid = f'BV1C4000000{index}'
        video = _add_material(c3.db, c3.artifacts, source, bvid=bvid, title=f'合成字幕{index}', text='合成摘要')
        path = c3.artifacts.video_dir(bvid) / 'transcript.txt'
        c3.artifacts.write_text(path, text)
        c3.db.update_video(video, transcript_path=str(path))
        documents.append((video, text))
    # Produce a genuine Runtime checkpoint first, leaving a large raw history behind it.
    prior, state, _ = history(c3, count=50)
    c3.composer.input_budget_tokens = 256000
    c3.graph.compaction_soft_target = 32000
    compacted = asyncio.run(c3.graph._prepare_dispatch(state, provider=c3.provider))
    assert compacted.checkpoint and notes(c3)[0]['note_version'] == 1
    assert c3.store.complete_run(prior['id'], epoch=prior['run_epoch'], answer='历史阶段结果，继续核对固定字幕集合。', usage={})
    requirement = '请改写以下内容：逐篇核对这五份字幕，保留全部条件与原话；不要保存，未知不补事实。'
    run = running(c3, text=requirement, key='five')
    rounds, previous, observed = [], [], []
    def main(request):
        messages = request.body['messages']
        assert messages[0]['content'] == SYSTEM_RULES
        assert requirement in str(messages)
        assert request.input_tokens < .85 * 256000
        observed.append(request.input_tokens)
        if previous:
            assert messages[:len(previous[0])] == previous[0]
        rounds.append(request)
        if len(rounds) == 1:
            previous[:] = [messages]
            return ModelTurn('', [NativeToolCall(f'transcript{i}', 'collection_read',
                {'source_ref':f'video:{video}', 'view':'transcript', 'max_characters':40000})
                for i,(video,text) in enumerate(documents)], 'tool_calls')
        for video,text in documents:
            assert text in str(messages)
        if len(rounds) == 2:
            previous[:] = [messages]
            return ModelTurn('', [NativeToolCall('five-focus','task_focus',
                {'goal':'核对固定五份字幕', 'selected_source_refs':[f'video:{v}' for v,_ in documents],
                 'requirements':['不要保存','未知不补事实'], 'working_notes':'五份原文已交付，核查仍需区分。',
                 'next_actions':['只补充缺口']})], 'tool_calls')
        assert '五份原文已交付，核查仍需区分。' in str(messages)
        return ModelTurn('依据五份合成字幕给出当前阶段结果；未知保持未知。', [], 'stop', {'total_tokens':12})
    c3.provider.main = main
    asyncio.run(c3.graph.run(run))
    assert c3.store.get_run(run['id'])['status'] == 'completed' and len(rounds) == 3
    following = running(c3, text='请改写以下内容：继续保持这五份集合，只补充缺口。', key='five-append')
    asyncio.run(c3.graph.run(following))
    assert c3.store.get_run(following['id'])['status'] == 'completed' and len(rounds) == 4
    assert len([r for r in c3.provider.sent if r.purpose == 'compact']) == 1
    assert notes(c3)[0]['note_version'] == 1
    raw = c3.store.working_run_context(following['id'])['thread']['messages']
    assert sum(len(m['content']) for m in raw) > .85 * 256000
    delivered = c3.store.get_run(run['id'])['working_state']['model_delivered_read_spans']
    for video,text in documents:
        span = next(s for s in delivered if s['source_ref'].startswith(f'video:{video}:') and s['view']=='transcript')
        assert span['start'] == 0 and span['end'] == span['total'] == len(text)
    print({'transcript_characters': lengths, 'total': sum(lengths), 'request_input_tokens': observed,
           'checkpoint_version': 1, 'summary_calls': 1})
