import json

from shiliu.assistant.task_notes import TaskNoteService


def test_normal_note_preserves_claim_boundary_in_compact_projection():
    text = 'source_reported：甲只说定期；默认开关未说明。\nsystem_synthesis：先计数再检查证据是设计建议。'
    note = {'id':'checkpoint','note_version':2,'checkpoint':{'format_version':1,'text':text}}
    payload = json.loads(TaskNoteService.render(note).split('\n',1)[1])
    assert payload['text']==text
    assert 'source_reported' in payload['text'] and 'system_synthesis' in payload['text']
    assert '默认开关未说明' in payload['text'] and '设计建议' in payload['text']
