"""Historical JSON representation and genuine new-source review, no live Provider."""

import copy
import json

import pytest

from shiliu.assistant.snapshots import _json_hash
from shiliu.assistant.wiki import WikiService
from shiliu.assistant.runtime_contract import AssistantConflict
from test_assistant_runtime_p0 import runtime_parts, drain, enqueue, row  # noqa: F401
from test_wiki import wiki_parts, add_source  # noqa: F401
from test_assistant_source_patch_p2 import decision, proposal


@pytest.mark.parametrize("links", [[], ["https://example.invalid/a"]])
def test_links_json_representation_only_is_equivalent(links):
    old = {"content_hash": "body", "metadata": {"title": "same", "description_links_json": json.dumps(links)}}
    new = {"content_hash": "body", "metadata": {"title": "same", "description_links_json": links}}
    assert WikiService._card_body_equivalent(old, new, {})
    assert WikiService._card_body_equivalent(new, old, {})


@pytest.mark.parametrize("changed", ["body", "links", "order", "title", "invalid", "non_list"])
def test_representation_fix_does_not_accept_real_or_invalid_changes(changed):
    old = {"content_hash": "body", "metadata": {"title": "same", "description_links_json": '["a", "b"]'}}
    new = {"content_hash": "body", "metadata": {"title": "same", "description_links_json": ["a", "b"]}}
    if changed == "body":new["content_hash"] = "different"
    elif changed == "links":new["metadata"]["description_links_json"] = ["changed"]
    elif changed == "order":new["metadata"]["description_links_json"] = ["b", "a"]
    elif changed == "title":new["metadata"]["title"] = "different"
    elif changed == "invalid":old["metadata"]["description_links_json"] = "[broken"
    else:old["metadata"]["description_links_json"] = '{"a":1}'
    assert not WikiService._card_body_equivalent(old, new, {})


def seed_historical_page(parts, wiki_parts, monkeypatch, *, manual=False):
    db, store, runtime, provider, space, msg, sources = parts
    vid, sid, _, _ = add_source(wiki_parts)
    db.update_video(vid, description_links_json='["https://example.invalid/a"]')
    original = sources.snapshots._build_snapshot

    def historical(state):
        snapshot = original(state)
        snapshot["metadata"]["description_links_json"] = json.dumps(snapshot["metadata"]["description_links_json"])
        stable = {k:v for k,v in snapshot["metadata"].items() if k != "metadata_observed_at"}
        snapshot["metadata_hash"] = _json_hash(stable)
        snapshot["revision"] = _json_hash({k:snapshot[k] for k in ("metadata_hash", "content_hash", "membership_hash")} | {"extractor_version":"assistant-source-v1"})
        return snapshot

    monkeypatch.setattr(sources.snapshots, "_build_snapshot", historical)
    old = sources.snapshots.capture(vid)
    runtime.wiki.request_topic(space_id=space, topic="PG事务", source_refs=[f"video:{vid}:{old.revision}"],
                               request_key=f"{space}:compat-old", source_message_id=msg)
    jobs = drain(runtime)
    assert all(row(store,j["id"])["status"] == "completed" for j in jobs)
    page = runtime.wiki.list_pages(space_id=space)[0]
    if manual:
        block=runtime.wiki.get_page(page["id"])["blocks"][0]
        runtime.wiki.edit_block(page["id"],block_id=block["stable_id"],markdown=block["markdown"],
                                expected_version=page["version"],operation_key="compat-manual")
        page=runtime.wiki.get_page(page["id"])
        assert page["blocks"][0]["manual_lock"]
    monkeypatch.setattr(sources.snapshots, "_build_snapshot", original)
    current = sources.snapshots.capture(vid)
    assert current.revision != old.revision
    return page, vid, sid, old, current


def test_real_pg_equivalent_rebind_without_provider_and_idempotent(runtime_parts, wiki_parts, monkeypatch):
    db, store, runtime, provider, space, msg, sources = runtime_parts
    page, vid, sid, old, current = seed_historical_page(runtime_parts, wiki_parts, monkeypatch,manual=True)
    before_calls = provider.structured_calls
    before_blocks = runtime.wiki.get_page(page["id"], include_hidden=True)["blocks"]
    runtime.wiki.request_topic(space_id=space, topic="PG事务", source_refs=[f"video:{vid}:{current.revision}"],
                               request_key=f"{space}:compat-new", source_message_id=msg)
    jobs = drain(runtime)
    assert all(row(store,j["id"])["status"] == "completed" for j in jobs)
    assert provider.structured_calls == before_calls
    after = runtime.wiki.get_page(page["id"], include_hidden=True)
    assert after["version"] == page["version"] + 1
    assert [(b["markdown"],b.get("manual_lock"),b.get("deleted")) for b in after["blocks"]] == [(b["markdown"],b.get("manual_lock"),b.get("deleted")) for b in before_blocks]
    with db.connect(read_only=True) as c:
        deps=c.execute("SELECT source_revision FROM assistant_wiki_dependencies WHERE page_id=%s",(page["id"],)).fetchall()
        assert deps and {x["source_revision"] for x in deps} == {current.revision}
        assert not c.execute("SELECT 1 FROM assistant_wiki_proposals WHERE kind='source_patch'").fetchone()
    assert sources.snapshots.load(vid,old.revision).snapshot == old.snapshot
    integration = next(j for j in jobs if j["kind"] == "wiki_integrate")
    identity=enqueue(store,kind="wiki_integrate",key="compat-repeat",payload=integration["payload"])
    drain(runtime)
    assert row(store,identity)["status"] == "completed"
    assert runtime.wiki.get_page(page["id"])["version"] == after["version"]
    assert provider.structured_calls == before_calls


def test_genuine_new_content_can_propose_without_reactivating_old_dependencies(runtime_parts, wiki_parts, monkeypatch):
    db, store, runtime, provider, space, msg, sources = runtime_parts
    page, vid, sid, old, current = seed_historical_page(runtime_parts,wiki_parts,monkeypatch)
    # A real content change cannot use equivalent-source rebinding.
    db.create_note(vid, "新增真正的事务结论，不属于原内容。")
    current=sources.snapshots.capture(vid)
    store.update_space(space,expected_scope_version=1,source_ids=[sid],all_active=False,maintenance_mode="automatic")
    original=provider.generate_json
    def generated(**kw):
        response=original(**kw)
        if "Wiki" in kw["system"]:
            response.update(operation="add_block",same_topic=True)
        return response
    monkeypatch.setattr(provider,"generate_json",generated)
    with db.connect() as c:
        generation=runtime.wiki._ensure_dirty(c,vid)
        runtime.wiki._enqueue_reconcile(c,vid,generation)
    jobs=drain(runtime)
    assert all(row(store,j["id"])["status"] == "completed" for j in jobs)
    outcomes=[row(store,j["id"])["proposal_json"] for j in jobs if j["kind"]=="wiki_integrate"]
    assert outcomes and all(not (x or {}).get("superseded") for x in outcomes), outcomes
    p=proposal(runtime_parts)
    assert p["status"] == "pending"
    assert old.revision not in p["payload_json"]["source_revisions"]
    # Pre-upgrade saved bases remain strict; never silently reinterpret them.
    legacy=copy.deepcopy(p)
    legacy["payload_json"]["source_revisions"].append(old.revision)
    forged=copy.deepcopy(p)
    forged["payload_json"]["patch"]["blocks"][0]["source_refs"].append(old.revision)
    for invalid in (legacy,forged):
        with db.connect(read_only=True) as c:
            with pytest.raises(AssistantConflict,match="wiki_source_out_of_scope"):
                runtime.wiki._validate_source_patch(c,invalid)
    assert runtime.wiki.get_page(page["id"],include_hidden=True)["version"] == page["version"]
    assert decision(runtime.wiki,p)["status"] == "accepted"
    view=runtime.wiki.get_page(page["id"])
    assert len(view["blocks"]) == 1
    assert view["blocks"][0]["source_refs"] == [current.revision]
    with db.connect(read_only=True) as c:
        deps=c.execute("SELECT source_revision FROM assistant_wiki_dependencies WHERE page_id=%s",(page["id"],)).fetchall()
        assert {x["source_revision"] for x in deps} == {old.revision,current.revision}
    assert decision(runtime.wiki,p)["status"] == "accepted"
    # A separate genuinely new video can revise the visible block while the
    # untouched old block remains stale. Retain the current target's evidence.
    vid2,sid2,_,_=add_source(wiki_parts,index=2,text="另一个视频补充了回滚和事务边界。")
    store.update_space(space,expected_scope_version=2,source_ids=[sid,sid2])
    target=view["blocks"][0]["stable_id"]
    def revise(**kw):
        response=original(**kw)
        if "Wiki" in kw["system"]:
            response.update(operation="revise_block",same_topic=True,target_block_id=target)
            response["blocks"][0]["source_keys"]=["s1","s2"]
        return response
    monkeypatch.setattr(provider,"generate_json",revise)
    with db.connect() as c:
        generation=runtime.wiki._ensure_dirty(c,vid2)
        runtime.wiki._enqueue_reconcile(c,vid2,generation)
    drain(runtime)
    revised=proposal(runtime_parts)
    assert revised["id"] != p["id"] and revised["status"] == "pending"
    assert revised["payload_json"]["patch"]["local_operation"] == "revise_block"
    assert decision(runtime.wiki,revised,key="revise-new-video")["status"] == "accepted"
    assert len(runtime.wiki.get_page(page["id"])["blocks"]) == 1
