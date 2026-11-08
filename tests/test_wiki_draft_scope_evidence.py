"""Authorization/identity contracts remain; semantic publishing gates are retired."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from shiliu.assistant.wiki_draft_checks import bind_scope
from shiliu.assistant.knowledge_write import parse_writer_draft, validate_writer_draft
from shiliu.assistant.tools import KnowledgeProposeArgs

SCOPE = '请把研究方法保存到Wiki：结论标明材料和版本，证据不足列为待核。'
USER = '2026年11月12日10:00评审，请保存到Memory。另'+SCOPE
REF = 'video:7:'+'a'*64

def draft(*blocks):
    return {'topics':[{'title':'研究方法','purpose':'长期复用','blocks':list(blocks)}], 'omitted':[]}

def evidence():
    return {'space_id':1,'materials':{'original_evidence':[
        {'items':[{'source_ref':'video:7','revision':'a'*64,'content':'原始材料'}]}]}}

@pytest.mark.parametrize('quotes', [[], ['虚构授权'], [USER]])
def test_explicit_authorization_still_requires_real_wiki_scope(quotes):
    with pytest.raises(ValueError):bind_scope(USER,quotes)

def test_paraphrase_keeps_body_title_and_role_without_decision_basis():
    value=draft({'role':'source','heading':'简介概括','markdown':'三款车进行三个月长测，结论尚缺正文。','source_refs':[REF]})
    parsed=parse_writer_draft(value)
    validate_writer_draft(SimpleNamespace(validate_save_draft=lambda **kw:None),evidence(),parsed)
    assert parsed['topics'][0]['title']=='研究方法'
    assert parsed['topics'][0]['blocks'][0]['markdown']==value['topics'][0]['blocks'][0]['markdown']
    assert parsed['topics'][0]['blocks'][0]['role']=='source'
    assert 'decision_basis' not in json.dumps(KnowledgeProposeArgs.model_json_schema())

def test_retired_metadata_is_ignored_but_unknown_source_still_rejected():
    block={'role':'analysis','heading':'概括','markdown':'合理归纳保留条件。','source_refs':[REF],
           'decision_basis':[{'kind':'source','claim':'改写的结论','quote':'旧引句'}]}
    parsed=parse_writer_draft(draft(block))
    assert 'decision_basis' not in parsed['topics'][0]['blocks'][0]
    block['source_refs']=['video:9:'+'b'*64]
    with pytest.raises(ValueError,match='versioned_video_source_required'):
        validate_writer_draft(SimpleNamespace(validate_save_draft=lambda **kw:None),evidence(),parse_writer_draft(draft(block)))


def test_replacement_keeps_previous_source_lineage():
    payload={**evidence(),'space_id':1,'edit_topics':[{'page_id':'p','title':'研究方法','expected_version':1}],
             'edit_source_refs':{'b':[REF]}}
    b={'role':'analysis','heading':'更正建议','markdown':'新分析','replace_block_id':'b','source_refs':[]}
    d=draft(b);d['topics'][0].update(payload['edit_topics'][0])
    wiki=SimpleNamespace(validate_save_draft=lambda **kw:None)
    with pytest.raises(ValueError,match='retain_original_sources'):validate_writer_draft(wiki,payload,d)
    b['source_refs']=[REF];validate_writer_draft(wiki,payload,d)




def test_memory_research_topic_or_negative_instruction_is_not_a_second_destination():
    from shiliu.assistant.wiki_draft_checks import requests_memory_write
    assert not requests_memory_write('请把Memory系统研究成果保存到Wiki。')
    assert not requests_memory_write('请更新Wiki研究方法，这个方法不写入Memory。')
    assert requests_memory_write(USER)
    assert bind_scope('请把Memory系统研究成果保存到Wiki。',['请把Memory系统研究成果保存到Wiki。'])
