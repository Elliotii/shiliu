"""Typed, first-delivery representations. Raw receipts remain owned by the Store."""
from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from shiliu.assistant.contracts import search_material_projection


FORMAT_VERSION = 1


def field_value(value: Any, path: str) -> Any:
    for part in path.split('.'):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            raise KeyError(path)
    return value


def read_evidence(name: str, result: dict, *, result_ref: str) -> tuple[list[dict], list[dict]]:
    """Describe only text/blocks actually in this representation, never inferred reading."""
    spans, materials = [], []
    if name == 'collection_read':
        view = result.get('coverage', {}).get('requested_view')
        for item in result.get('items') or []:
            ref = next(iter(result.get('source_refs') or []), item.get('source_ref'))
            title = item.get('video', {}).get('title', '')
            base = {'source_ref': ref, 'title': title, 'kind': name, 'origin': '工作输入',
                    'result_ref': result_ref, 'projection': '原文片段'}
            for attached in ('metadata', 'time'):
                if item.get('video' if attached == 'metadata' else 'time'):
                    materials.append({**base, 'view': attached, 'position': {}, 'complete': False})
            content = item.get('content')
            position = item.get('provenance', {}).get('content_position') or {}
            if isinstance(content, str) and content and position and ref:
                start = int(position.get('start') or 0)
                end = int(position.get('end') or 0)
                if end - start != len(content):
                    raise ValueError('delivery_position_mismatch')
                span = {'source_ref': ref, 'view': view, 'start': start, 'end': end,
                        'total': int(position.get('total') or 0)}
                spans.append(span)
                materials.append({**base, 'view': view, 'position': position,
                                  'complete': start == 0 and end == span['total']})
    elif name == 'knowledge_read':
        for page in result.get('items') or []:
            blocks = page.get('blocks') or []
            if blocks:
                materials.append({
                    'source_ref': f"wiki:{page['id']}:{page['version']}", 'title': page.get('title'),
                    'kind': name, 'view': '知识页正文', 'projection': '知识块原文', 'complete': False,
                    'position': {'block_ids': [b['stable_id'] for b in blocks]},
                    'lineage_refs': result.get('source_refs') or [], 'result_ref': result_ref,
                })
    elif name == 'search_knowledge':
        materials = search_material_projection(result, origin='工作输入')
    elif name == 'run_read_result':
        spans = deepcopy(result.get('coverage', {}).get('read_spans') or [])
        materials = deepcopy(result.get('coverage', {}).get('materials') or [])
    elif name.startswith('context7_'):
        for item_index, item in enumerate(result.get('items') or []):
            for index, block in enumerate(item.get('response', {}).get('content') or []):
                if isinstance(block, dict) and block.get('type') == 'text' and block.get('text'):
                    materials.append({'source_ref': result_ref, 'kind': name, 'view': '公开文档',
                        'projection': '原文片段', 'complete': False, 'result_ref': result_ref,
                        'position': {'item_index': item_index, 'field': f'response.content.{index}.text',
                                     'start': 0, 'end': len(block['text'])}})
    return spans, materials


def project_tool_result(name: str, result: dict, *, result_ref: str,
                        sources: Any, body_characters: int | None = None) -> dict:
    value = deepcopy(result)
    value['result_ref'] = result_ref
    coverage = value.setdefault('coverage', {})
    if name == 'collection_read':
        if body_characters is not None:
            value = sources.clip_read_result(value, max_characters=body_characters)
            coverage = value.setdefault('coverage', {})
        for item in value.get('items') or []:
            raw_video = item.get('video') or {}
            item['video'] = {k: v for k, v in raw_video.items() if k in {
                'video_id', 'bvid', 'part', 'cid', 'page_count', 'part_title', 'title',
                'uploader', 'uploader_id', 'duration_seconds', 'coverage',
            }}
            if coverage.get('requested_view') == 'overview':
                description = str(raw_video.get('description') or '')
                item['video'].update(description_excerpt=description[:1200],
                    description_excerpt_truncated=len(description) > 1200,
                    description_read_args={'source_ref': next(iter(value.get('source_refs') or []), item['source_ref']),
                                           'view': 'description'})
                value['truncated'] = bool(value.get('truncated') or len(description) > 1200)
    elif name == 'search_knowledge':
        for group in value.get('items') or []:
            if group.get('source') == 'collection':
                group['candidates'] = [{k: v for k, v in card.items() if k in {
                    'source_ref', 'revision', 'video_id', 'bvid', 'part', 'coverage', 'title',
                    'uploader', 'published_at', 'metadata_observed_at', 'memberships',
                    'matched_excerpt', 'available_views', 'full_text_available',
                }} for card in group.get('candidates') or []]
    elif name == 'knowledge_read' and body_characters is not None:
        remaining = body_characters
        for page in value.get('items') or []:
            kept = []
            blocks = page.get('blocks') or []
            for block in blocks:
                size = len(json.dumps(block, ensure_ascii=False))
                if size > remaining:
                    break
                kept.append(block)
                remaining -= size
            page['blocks'] = kept
            if len(kept) < len(blocks):
                start = int(coverage.get('start_block') or 0)
                value['truncated'] = True
                if coverage.get('mode') == 'block':
                    value['next_cursor'] = None
                    coverage['next_read_args'] = {'page_id': page['id'], 'page_version': page['version'],
                        'mode': 'block', 'block_ids': [b['stable_id'] for b in blocks[len(kept):]]}
                else:
                    value['next_cursor'] = f"{page['version']}:{start + len(kept) + 1}"
                    coverage['next_read_args'] = {'page_id': page['id'], 'page_version': page['version'],
                        'mode': 'page', 'cursor': value['next_cursor']}
                coverage.update(returned_blocks=len(kept), complete=False,
                                returned_block_ids=[b['stable_id'] for b in kept])
    elif name.startswith('context7_'):
        remaining = min(40000, body_characters if body_characters is not None else 40000)
        positions = []
        for item_index, item in enumerate(value.get('items') or []):
            response = item.get('response') or {}
            content = []
            for index, block in enumerate(response.get('content') or []):
                if not isinstance(block, dict) or block.get('type') != 'text':
                    content.append({'type': block.get('type') if isinstance(block, dict) else 'unknown',
                                    'read_field': f'response.content.{index}'})
                    value['truncated'] = True
                    continue
                text = str(block.get('text') or '')
                delivered = text[:remaining]
                remaining -= len(delivered)
                content.append({'type': 'text', 'text': delivered})
                positions.append({'item_index': item_index, 'field': f'response.content.{index}.text',
                                  'start': 0, 'end': len(delivered), 'total': len(text)})
                if len(delivered) < len(text):
                    value['truncated'] = True
            item['response'] = {'content': content, **({'isError': response['isError']} if 'isError' in response else {})}
            if set(response) - {'content', 'isError'}:
                item['response_fields'] = list(response)
                value['truncated'] = True
        coverage['text_positions'] = positions
        coverage['next_read_args'] = next(({'result_ref': result_ref, 'item_index': p['item_index'],
                                            'field': p['field'], 'start': p['end']}
                                           for p in positions if p['end'] < p['total']), None)
        coverage['read_result_ref'] = result_ref
    elif name.startswith('knowledge_') and name not in {'knowledge_read', 'knowledge_search'}:
        # Full raw receipts own drafts. Retain original unfinished topic positions/repair data.
        for item in value.get('items') or []:
            if not isinstance(item, dict):
                continue
            payload = item.get('payload') or {}
            topics = item.get('topics', payload.get('topics') if isinstance(payload, dict) else None)
            outcomes = item.get('results') or {}
            if topics is not None:
                item['topic_index'] = [{'index': index, **{k: v for k, v in topic.items() if k in {'title', 'purpose'}}}
                                       for index, topic in enumerate(topics)]
                item['unfinished_topics'] = [{'index': index, 'topic': topic} for index, topic in enumerate(topics)
                                             if outcomes.get(str(index), {}).get('status') != 'completed']
                item.pop('topics', None)
                item.pop('payload', None)
                value['truncated'] = True
            for key, outcome in list(outcomes.items()):
                if isinstance(outcome, dict) and outcome.get('status') == 'completed':
                    outcomes[key] = {k: v for k, v in outcome.items()
                                     if k in {'status', 'page_id', 'version', 'title', 'operation_key', 'undo'}}
            if value.get('status') == 'ok' and 'blocks' in item:
                item.pop('blocks')
                value['truncated'] = True
    if value.get('truncated'):
        value.setdefault('coverage', {})['read_result_ref'] = result_ref
    return value


def validate_model_sequence(messages: list[dict]) -> None:
    """Application system blocks may appear only between complete protocol units."""
    index = 0
    while index < len(messages):
        message = messages[index]
        if message.get('role') == 'tool':
            raise ValueError('working_context_orphan_tool')
        calls = message.get('tool_calls') or []
        index += 1
        if not calls:
            continue
        ids = [c.get('id') for c in calls]
        if message.get('role') != 'assistant' or not all(ids) or len(set(ids)) != len(ids):
            raise ValueError('working_context_duplicate_call')
        received = []
        while index < len(messages) and messages[index].get('role') == 'tool':
            received.append(messages[index].get('tool_call_id'))
            index += 1
        if len(received) != len(ids) or set(received) != set(ids):
            raise ValueError('working_context_incomplete_tool_group')
