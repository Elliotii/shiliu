from __future__ import annotations
import copy
import json
import pytest
from shiliu.assistant.store import AssistantConflict
from test_assistant_k import setup, start_run, call
from test_assistant_upgrade_d import _message_id
from test_assistant_w1 import fixture, execute
from test_assistant_consolidation_nb import _run, _topics
from test_assistant_stage_c import _add_material, DeterministicWikiProvider


def seed(wiki, store, space, title='生命周期页', text='摄影独特条件必须保留'):
    message = _message_id(store, space['id'], '请保存讨论')
    return wiki.save_discussion(space_id=space['id'], title=title, purpose=text,
        blocks=[{'role':'analysis','heading':'摄影条件','markdown':text}], source_message_id=message, operation_key='seed:'+title)


def test_delete_archive_restore_search_summary_and_old_vector(app_paths):
    _,_,_,store,wiki,registry,space,provider = setup(app_paths)
    page = seed(wiki,store,space)
    assert wiki.retrieval.search(wiki.list_pages(space_id=space['id']), '摄影')['candidates']
    deleted = wiki.manage_page(page['id'],space_id=space['id'],action='delete_block',block_id=page['blocks'][0]['stable_id'],expected_version=1,operation_key='delete')
    assert wiki.manage_page(page['id'],space_id=space['id'],action='delete_block',block_id=page['blocks'][0]['stable_id'],expected_version=1,operation_key='delete') == deleted
    assert wiki.get_page(page['id'],space_id=space['id'])['blocks'] == []
    assert '独特条件' not in wiki.get_page(page['id'],space_id=space['id'])['summary']
    assert wiki.list_pages(space_id=space['id']) == []
    assert not wiki.retrieval.search([], '摄影').get('candidates')
    with pytest.raises(AssistantConflict):
        wiki.edit_block(page['id'],block_id=page['blocks'][0]['stable_id'],markdown='不能借编辑恢复',expected_version=2,operation_key='bad-edit')
    wiki.manage_page(page['id'],space_id=space['id'],action='restore_block',block_id=page['blocks'][0]['stable_id'],expected_version=2,operation_key='restore-block')
    wiki.manage_page(page['id'],space_id=space['id'],action='archive',expected_version=3,operation_key='archive')
    assert wiki.list_pages(space_id=space['id']) == []
    with pytest.raises(KeyError):wiki.get_page(page['id'],space_id=space['id'])
    assert wiki._find_page(space['id'],page['title'])['status'] == 'archived'
    with pytest.raises(AssistantConflict):wiki.revert(page['id'],target_version=1,expected_version=4,operation_key='bad-revert')
    wiki.manage_page(page['id'],space_id=space['id'],action='restore',expected_version=4,operation_key='restore-page')
    assert wiki.get_page(page['id'],space_id=space['id'])['version'] == 5
    assert wiki.get_page(page['id'],space_id=space['id'])['blocks'][0]['stable_id'] == page['blocks'][0]['stable_id']


def ready_job(db, artifacts, store, wiki, space, index):
    source_id=db.create_favorite_source(folder_id=580+index,folder_title='W2 source',history_policy='all')
    video=_add_material(db,artifacts,source_id,bvid=f'BV1W2000000{index}',title=f'新材料{index}',text=f'正文{index}')
    wiki.bootstrap_space(space['id'],limit=10)
    while True:
        job=store.claim_job(owner='w2-test')
        assert job
        if job['kind']=='wiki_integrate':return video,job
        result=wiki.reconcile(job) if job['kind']=='source_reconcile' else wiki.extract_source_card(job,provider=DeterministicWikiProvider())
        store.finish_job(job['id'],proposal=result,owner=job['lease_owner'],lease_epoch=job['lease_epoch'])


def patch_apply(wiki,space,job,version,blocks,title='后台页'):
    return wiki.apply_patch(space_id=space['id'],video_id=job['payload']['video_id'],revision=job['payload']['revision'],expected_version=version,
        patch={'title':title,'page_type':'topic','summary':'不得保留已删除的摘要','blocks':blocks,'replace_derived':True},
        scope_version=space['scope_version'],job_id=job['id'],lease_owner=job['lease_owner'],lease_epoch=job['lease_epoch'])


def test_background_same_id_changed_id_revision_and_new_content(app_paths):
    db,artifacts,_,store,wiki,space,_ = fixture(app_paths)
    _,job=ready_job(db,artifacts,store,wiki,space,1)
    blocks=[{'heading':'原标题','markdown':'原样正文','source_refs':[job['payload']['revision']]}]
    created=patch_apply(wiki,space,job,0,blocks)
    page=wiki.list_pages(space_id=space['id'])[0]
    wiki.manage_page(page['id'],space_id=space['id'],action='delete_block',block_id=page['blocks'][0]['stable_id'],expected_version=1,operation_key='d')
    with pytest.raises(AssistantConflict,match='deleted'):
        patch_apply(wiki,space,job,2,blocks)
    patch_apply(wiki,space,job,2,[{'heading':'同版本新内容','markdown':'新的合法正文','source_refs':[job['payload']['revision']]}])
    added=wiki.get_page(page['id'],space_id=space['id'])['blocks'][0]
    assert added['stable_id']!=page['blocks'][0]['stable_id']
    wiki.manage_page(page['id'],space_id=space['id'],action='delete_block',block_id=added['stable_id'],expected_version=3,operation_key='d-new')
    store.finish_job(job['id'],proposal=created,owner=job['lease_owner'],lease_epoch=job['lease_epoch'])
    _,other=ready_job(db,artifacts,store,wiki,space,2)
    copied=[{**blocks[0],'source_refs':[other['payload']['revision']]}]
    with pytest.raises(AssistantConflict,match='deleted'):
        patch_apply(wiki,space,other,4,copied)
    patch_apply(wiki,space,other,4,[{'heading':'合法新内容','markdown':'不同正文','source_refs':[other['payload']['revision']]}])
    current=wiki.get_page(page['id'],space_id=space['id'])
    assert [b['markdown'] for b in current['blocks']] == ['不同正文']
    wiki.manage_page(page['id'],space_id=space['id'],action='archive',expected_version=current['version'],operation_key='archive')
    with pytest.raises(AssistantConflict,match='inactive'):
        patch_apply(wiki,space,other,current['version']+1,copied)
    with db.connect() as c:assert c.execute('SELECT count(*) FROM assistant_wiki_pages').fetchone()[0]==1


def test_ignore_restore_partial_and_success_receipts(app_paths):
    _,_,_,store,wiki,space,tools=fixture(app_paths)
    prior,context=_run(store,space['id'],'我实拍时发现景深太浅',key='prior')
    quote_id=context['thread']['messages'][-1]['id']
    run,_=_run(store,space['id'],'请保存讨论',thread_id=prior['thread_id'],key='save')
    topics=_topics();topics[1]['blocks']=[{'role':'personal','heading':'体验','markdown':'我实拍时发现景深太浅','user_quote':'我实拍时发现景深太浅'}]
    plan=execute(tools,store,run,{'topics':topics})['items'][0]
    page=wiki.list_pages(space_id=space['id'])[0]
    ignored=wiki.manage_plan_item(plan['id'],space_id=space['id'],item_index=1,action='ignore',expected_version=1,operation_key='ignore')
    assert ignored['status']=='partial' and ignored['results']['1']['status']=='ignored'
    assert wiki.list_discussion_plans(space_id=space['id'],view='pending')==[]
    assert len(wiki.list_discussion_plans(space_id=space['id'],view='ignored'))==1
    # An accepted retry must still skip ignored items.
    wiki.decide_discussion_plan(plan['id'],space_id=space['id'],expected_version=2,accept=True,operation_key='retry')
    assert wiki.get_page(page['id'],space_id=space['id'])['version']==1
    restored=wiki.manage_plan_item(plan['id'],space_id=space['id'],item_index=1,action='restore',expected_version=2,operation_key='restore')
    assert restored['results']['1']['issues']
    fixed=execute(tools,store,run,{'plan_id':plan['id'],'expected_version':3,'corrections':[{'path':'topics[1].blocks[0].user_message_id','value':quote_id}]},'fix')
    assert fixed['status']=='ok',fixed
    assert wiki.get_page(page['id'],space_id=space['id'])['version']==1
    with pytest.raises(AssistantConflict):wiki.manage_plan_item(plan['id'],space_id=space['id'],item_index=0,action='ignore',expected_version=4,operation_key='ignore-success')


def test_ignore_does_not_hide_unrecorded_committed_page(app_paths,monkeypatch):
    _,_,_,store,wiki,space,tools=fixture(app_paths)
    run,_=_run(store,space['id'],'请保存讨论',key='crash')
    original=wiki.save_discussion
    def crash(**kw):original(**kw);raise RuntimeError('after commit')
    monkeypatch.setattr(wiki,'save_discussion',crash)
    assert execute(tools,store,run,{'topics':[_topics()[0]]})['status']=='outcome_unknown'
    plan=wiki.list_discussion_plans(space_id=space['id'])[0]
    with pytest.raises(AssistantConflict,match='already_completed'):
        wiki.manage_plan_item(plan['id'],space_id=space['id'],item_index=0,action='ignore',expected_version=1,operation_key='ignore')
    monkeypatch.setattr(wiki,'save_discussion',original)
    assert execute(tools,store,run,{'topics':[_topics()[0]]},'recover')['status']=='ok'
    assert wiki.list_pages(space_id=space['id'])[0]['version']==1


def test_revert_merge_keep_deletion_decisions_and_explicit_readd(app_paths):
    _,_,_,store,wiki,space,_=fixture(app_paths)
    first=seed(wiki,store,space,'第一页')
    wiki.edit_block(first['id'],block_id=first['blocks'][0]['stable_id'],markdown='人工修订',expected_version=1,operation_key='edit')
    wiki.manage_page(first['id'],space_id=space['id'],action='delete_block',block_id=first['blocks'][0]['stable_id'],expected_version=2,operation_key='del')
    wiki.revert(first['id'],target_version=1,expected_version=3,operation_key='revert')
    assert not wiki.get_page(first['id'],space_id=space['id'])['blocks']
    second=seed(wiki,store,space,'第二页','仍有可合并的内容')
    # Merge an active page that has both a tombstone and a new explicit block.
    msg=_message_id(store,space['id'],'请保存新的讨论')
    wiki.save_discussion(space_id=space['id'],title='第一页',purpose='新内容',blocks=[{'role':'analysis','heading':'新','markdown':'新独立内容'}],source_message_id=msg,expected_version=4,operation_key='new')
    wiki.merge_pages(first['id'],second['id'],space_id=space['id'],source_version=5,target_version=1,operation_key='merge')
    raw=wiki.get_page(second['id'],space_id=space['id'],include_hidden=True)
    assert any(b.get('deleted') for b in raw['blocks'])
    with pytest.raises(AssistantConflict):wiki._assert_lifecycle(raw,[{'heading':'摄影条件','markdown':'人工修订'}])
    current=wiki.get_page(second['id'],space_id=space['id'])
    message=_message_id(store,space['id'],'请明确重新加入已删除内容')
    wiki.save_discussion(space_id=space['id'],title='第二页',purpose='重新加入',blocks=[{'role':'analysis','heading':'摄影条件','markdown':'人工修订'}],source_message_id=message,expected_version=current['version'],operation_key='readd')
    assert any(b['markdown']=='人工修订' for b in wiki.get_page(second['id'],space_id=space['id'])['blocks'])


def test_empty_history_and_formal_save_identity(app_paths):
    _,_,_,store,_,space,_=fixture(app_paths)
    empty=store.create_thread(space['id'])
    assert store.list_threads(space_id=space['id'])['threads']==[]
    assert not store.get_thread(empty['id'])['can_save']
    run=store.create_run(empty['id'],text='你好',request_id='greet');claimed=store.claim_next_run()
    store.complete_run(run['id'],epoch=claimed['run_epoch'],answer='你好！',usage={})
    assert not store.get_thread(empty['id'])['can_save']
    failed=store.create_run(empty['id'],text='研究问题',request_id='failed');claimed=store.claim_next_run()
    store.fail_run(failed['id'],code='isolated_error',message='failed')
    assert store.list_threads(space_id=space['id'])['threads'][0]['id']==empty['id']
    research=store.create_thread(space['id'])
    answer_run=store.create_run(research['id'],text='分析摄影适用条件',request_id='formal');lease=store.claim_next_run()
    store.complete_run(answer_run['id'],epoch=lease['run_epoch'],answer='摄影条件与未知项如下。',usage={})
    saved=store.get_thread(research['id'])
    assert saved['can_save'] and saved['save_answer_message_id']==next(m['id'] for m in saved['messages'] if m['role']=='assistant')


def test_merge_undo_does_not_revive_later_delete_or_archived_target(app_paths):
    _,_,_,store,wiki,space,_=fixture(app_paths)
    source=seed(wiki,store,space,'来源页','应尊重后续删除的内容')
    target=seed(wiki,store,space,'目标页','原有内容')
    merged=wiki.merge_pages(source['id'],target['id'],space_id=space['id'],source_version=1,target_version=1,operation_key='m')
    page=wiki.get_page(target['id'],space_id=space['id'])
    moved=next(b for b in page['blocks'] if b['markdown']=='应尊重后续删除的内容')
    wiki.manage_page(target['id'],space_id=space['id'],action='delete_block',block_id=moved['stable_id'],expected_version=2,operation_key='d')
    wiki.revert(target['id'],target_version=1,expected_version=3,operation_key='undo')
    assert not wiki.get_page(source['id'],space_id=space['id'])['blocks']
    assert all(b['markdown']!='应尊重后续删除的内容' for p in wiki.list_pages(space_id=space['id']) for b in p['blocks'])
    wiki.manage_page(target['id'],space_id=space['id'],action='archive',expected_version=4,operation_key='archive')
    with pytest.raises(AssistantConflict,match='inactive'):
        wiki.revert(target['id'],target_version=1,expected_version=5,operation_key='undo-archived')


def test_equivalent_rebind_preserves_tombstone_and_old_proposal_is_stale(app_paths):
    db,artifacts,_,store,wiki,space,_=fixture(app_paths)
    video,job=ready_job(db,artifacts,store,wiki,space,1)
    revision=job['payload']['revision']
    patch_apply(wiki,space,job,0,[{'heading':'来源块','markdown':'正文','source_refs':[revision]}])
    page=wiki.list_pages(space_id=space['id'])[0]
    wiki.manage_page(page['id'],space_id=space['id'],action='delete_block',block_id=page['blocks'][0]['stable_id'],expected_version=1,operation_key='delete-source')
    # Equivalent-revision fast path must neither rebind nor reactivate the deleted block.
    raw=wiki.get_page(page['id'],space_id=space['id'],include_hidden=True)
    store.finish_job(job['id'],owner=job['lease_owner'],lease_epoch=job['lease_epoch'])
    db.update_video(video,description='来源版本变化')
    current=wiki.sources.snapshots.capture(video)
    with db.connect() as connection:
        store.enqueue_job(connection,kind='wiki_integrate',dedupe_key='rebind-w2',payload={**job['payload'],'revision':current.revision})
    newjob=store.claim_job(owner='w2-rebind')
    wiki._rebind_equivalent_source(raw,space=space,video_id=video,revision=current.revision,job=newjob)
    after=wiki.get_page(page['id'],space_id=space['id'],include_hidden=True)
    assert after['blocks']==raw['blocks'] and after['version']==raw['version']
    assert not wiki.get_page(page['id'],space_id=space['id'])['blocks']
    left=seed(wiki,store,space,'人工一','观点一');right=seed(wiki,store,space,'人工二','观点二')
    for p in [left,right]:wiki.edit_block(p['id'],block_id=p['blocks'][0]['stable_id'],markdown=p['blocks'][0]['markdown'],expected_version=1,operation_key='edit-'+p['id'])
    proposal=wiki.merge_pages(left['id'],right['id'],space_id=space['id'],source_version=2,target_version=2,operation_key='propose')
    assert proposal['status']=='pending'
    wiki.manage_page(right['id'],space_id=space['id'],action='archive',expected_version=2,operation_key='ar')
    with pytest.raises(AssistantConflict,match='stale'):
        wiki.decide_proposal(proposal['proposal_id'],space_id=space['id'],accept=True,operation_key='accept-old')


def test_management_api_lifecycle_and_explicit_tool_authorization(app_paths):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from shiliu.assistant.api import router
    _,_,_,store,wiki,space,tools=fixture(app_paths)
    app=FastAPI()
    app.state.core=SimpleNamespace(config=SimpleNamespace(assistant_enabled=True),assistant_runtime=SimpleNamespace(store=store,wiki=wiki))
    app.include_router(router)
    client=TestClient(app)
    page=seed(wiki,store,space)
    run,_=_run(store,space['id'],'不要删除此知识块',key='deny')
    args={'page_id':page['id'],'action':'delete_block','expected_version':1,'block_id':page['blocks'][0]['stable_id']}
    denied=execute(tools,store,run,args,name='knowledge_manage')
    assert denied['status']=='invalid_arguments'
    assert wiki.get_page(page['id'],space_id=space['id'])['version']==1
    endpoint=f"/api/assistant/wiki/{page['id']}"
    assert client.post(endpoint+'/lifecycle',json={**args,'space_id':space['id'],'operation_key':'ui-delete','page_id':page['id']}).status_code==422
    payload={k:v for k,v in args.items() if k!='page_id'}
    assert client.post(endpoint+'/lifecycle',json={**payload,'space_id':space['id'],'operation_key':'ui-delete'}).status_code==200
    shown=client.get(endpoint+f"/management?space_id={space['id']}").json()['page']
    assert shown['blocks']==[] and shown['deleted_blocks']==[{'stable_id':args['block_id'],'heading':'摄影条件'}]
    assert client.post(endpoint+'/lifecycle',json={'space_id':space['id'],'action':'archive','expected_version':2,'operation_key':'ui-archive'}).status_code==200
    assert client.get(f"/api/assistant/wiki-management?space_id={space['id']}&status=archived").json()['pages'][0]['id']==page['id']
    assert client.get(endpoint+f"?space_id={space['id']}").status_code==404
    assert client.post(endpoint+'/lifecycle',json={'space_id':space['id'],'action':'restore','expected_version':3,'operation_key':'ui-restore'}).status_code==200
    assert client.post(endpoint+'/lifecycle',json={**payload,'space_id':space['id'],'operation_key':'ui-stale'}).status_code==409

    prior,ctx=_run(store,space['id'],'这是一条个人实拍原话',key='ui-quote')
    quote=ctx['thread']['messages'][-1]['id']
    save,_=_run(store,space['id'],'请保存讨论',thread_id=prior['thread_id'],key='ui-plan')
    topics=_topics();topics[1]['blocks']=[{'role':'personal','heading':'个人观点','markdown':'这是一条个人实拍原话','user_quote':'这是一条个人实拍原话'}]
    plan=execute(tools,store,save,{'topics':topics})['items'][0]
    base=f"/api/assistant/knowledge-plans/{plan['id']}"
    response=client.post(base+'/items/1',json={'space_id':space['id'],'action':'ignore','expected_version':1,'operation_key':'ui-ignore'})
    assert response.status_code==200 and response.json()['plan']['results']['1']['status']=='ignored'
    response=client.post(base+'/items/1',json={'space_id':space['id'],'action':'restore','expected_version':2,'operation_key':'ui-item-restore'})
    assert response.status_code==200
    response=client.post(base+'/repair',json={'space_id':space['id'],'expected_version':3,'operation_key':'ui-field','corrections':[{'path':'topics[1].blocks[0].user_message_id','value':quote}]})
    assert response.status_code==200,response.text
    repaired=response.json()['plan']
    assert repaired['version']==4 and repaired['results']['0']['status']=='completed'
    response=client.post(base+'/decide',json={'space_id':space['id'],'expected_version':4,'accept':True,'operation_key':'ui-submit'})
    assert response.status_code==200 and response.json()['plan']['status']=='completed'
    assert wiki.get_page(repaired['results']['0']['page_id'],space_id=space['id'])['version']==1
