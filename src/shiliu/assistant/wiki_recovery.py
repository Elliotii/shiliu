"""Detect a repeated empty Wiki observation, not a global tool-count gate."""
import hashlib
import json


def read_state(page):
    return hashlib.sha256(json.dumps({k: page.get(k) for k in
        ('id', 'version', 'dependency_versions', 'availability', 'blocks')},
        sort_keys=True, default=str).encode()).hexdigest()


def repeated_empty_page(calls):
    if len(calls) < 2:
        return None
    tokens = []
    for call in calls[-2:]:
        result = call.get('result_json') or {}
        coverage = result.get('coverage') or {}
        items = result.get('items') or []
        if (call.get('name') != 'knowledge_read' or result.get('status') != 'empty'
                or coverage.get('mode') != 'page' or result.get('next_cursor')
                or not coverage.get('state_token') or len(items) != 1):
            return None
        tokens.append((items[0]['id'], items[0]['version'], coverage['state_token']))
    return tokens[0][0] if tokens[0] == tokens[1] else None
