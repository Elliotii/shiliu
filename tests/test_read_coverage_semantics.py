"""Read windows and frozen fixture metadata, without products/models/services."""
from types import SimpleNamespace
import hashlib
import json
from pathlib import Path
import pytest
from shiliu.assistant.sources import CollectionSourceService, SourceScope
from shiliu.assistant.snapshots import CapturedSource
from shiliu.assistant.delivery import project_tool_result


def reader(text, duration=0):
    meta = dict(id=1, source_id='BVtest', part=1, title='测试', duration_seconds=duration, description='',
                published_at=None, active_revision='refined')
    snap = dict(metadata=meta, materials={'raw_subtitle':text,'summary':'短摘要'}, notes=[], memberships=[],
                coverage='full_available_transcript', material_hashes={'raw_subtitle':'h','summary':'s'})
    service = CollectionSourceService.__new__(CollectionSourceService)
    service._allowed_sources = lambda scope, query: set()
    service._video_is_available = lambda *args, **kw: True
    service._capture_or_load = lambda *args: CapturedSource('a'*64,'snapshot',snap)
    return service


def read(service, **kw):
    return service.read(call_id='call',scope=SourceScope(),source_ref='video:1',view=kw.pop('view','transcript'),**kw).model_dump(mode='json')


def test_query_to_end_is_not_whole_view_and_repeat_is_same_span():
    s=reader('前'*900+'定位'+'后'*20)
    a=read(s,query='定位',max_characters=4000)
    b=read(s,query='定位',max_characters=4000)
    assert a['coverage']['read_position']==b['coverage']['read_position']=={'start':400,'end':922,'total':922}
    assert a['items'][0]['content']=='前'*500+'定位'+'后'*20
    assert a['coverage']['has_unread_before'] and not a['coverage']['has_unread_after']
    assert not a['coverage']['read_complete'] and not a['truncated'] and a['next_cursor'] is None
    full=read(s,**{k:v for k,v in a['coverage']['read_from_start_args'].items()if k!='source_ref'})
    assert full['coverage']['read_complete'] and full['coverage']['read_position']['start']==0


def test_summary_complete_is_not_transcript_complete_and_unicode_offsets():
    s=reader('汉字🙂正文')
    summary=read(s,view='summary',query='摘要')
    assert summary['coverage']['read_complete'] and summary['coverage']['requested_view']=='summary'
    raw=read(s,max_characters=3)
    assert raw['items'][0]['content']=='汉字🙂'
    assert raw['coverage']['read_position']=={'start':0,'end':3,'total':5}
    end=read(s,cursor=raw['next_cursor'])
    assert end['items'][0]['content']=='正文' and end['coverage']['has_unread_before']
    assert not end['coverage']['read_complete']


@pytest.mark.parametrize('duration,expected',[(0,None),(104,104)])
def test_duration_read_and_projection(duration,expected):
    s=reader('abcdef',duration)
    raw=read(s)
    projected=project_tool_result('collection_read',raw,result_ref='ref',sources=s)
    assert raw['items'][0]['video']['duration_seconds']==expected
    assert projected['items'][0]['video']['duration_seconds']==expected
    clipped=s.clip_read_result(raw,max_characters=2)
    assert clipped['coverage']['has_unread_after'] and not clipped['coverage']['read_complete']
    assert clipped['coverage']['read_position']['end']==2




def test_model_tool_contract_has_exactly_five_wiki_entries():
    from shiliu.assistant.tools import AssistantToolRegistry
    from shiliu.assistant.context import SYSTEM_RULES
    schemas=AssistantToolRegistry(store=None,sources=None,memories=None,wiki=object()).schemas()
    assert {t['function']['name']for t in schemas if t['function']['name'].startswith('knowledge_')or t['function']['name']=='search_knowledge'}=={'search_knowledge','knowledge_read','knowledge_save_request','knowledge_update_page','knowledge_save_status'}
    read_tool=next(t['function']for t in schemas if t['function']['name']=='collection_read')
    assert '首次不传query/cursor'in read_tool['description']
    for retired in ['knowledge_propose','knowledge_confirm','knowledge_save_discussion','knowledge_save_personal','knowledge_organize']:
        assert retired not in SYSTEM_RULES


def test_empty_view_is_not_a_complete_transcript():
    result=read(reader(''))
    assert result['status']=='empty' and not result['coverage']['read_complete']
    assert result['coverage']['read_position']=={'start':0,'end':0,'total':0}
