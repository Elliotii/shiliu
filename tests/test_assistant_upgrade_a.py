from __future__ import annotations

import pytest

from shiliu.assistant.store import AssistantConflict, AssistantRunStore
from shiliu.assistant.context import ContextComposer
from shiliu.assistant.memory import MemoryService

from test_assistant_stage_b import _source_service


def test_history_is_scoped_paginated_and_abandoned_run_can_be_followed(app_paths) -> None:
    db, _sources = _source_service(app_paths)
    store = AssistantRunStore(db)
    first_space = store.create_space(name="甲", all_active=True)
    other_space = store.create_space(name="乙", all_active=True)
    first = store.create_thread(first_space["id"])
    other = store.create_thread(other_space["id"])
    run = store.create_run(first["id"], text="五份材料都读完", request_id="a-1")
    other_run = store.create_run(other["id"], text="另一范围", request_id="b-1")
    store.cancel_run(other_run["id"])
    extra = store.create_thread(first_space["id"], title="另一段对话")
    page = store.list_threads(space_id=first_space["id"], limit=1)
    assert page["next_cursor"]
    following_page = store.list_threads(space_id=first_space["id"], limit=1, **page["next_cursor"])
    summaries = page["threads"] + following_page["threads"]
    assert {item["id"] for item in summaries} == {first["id"], extra["id"]}
    assert next(item for item in summaries if item["id"] == first["id"])["title"] == "五份材料都读完"
    assert other["id"] not in [item["id"] for item in summaries]

    claimed = store.claim_next_run()
    assert claimed and claimed["id"] == run["id"]
    store.fail_run(run["id"], code="context_budget_exceeded", message="太长")
    blocked = store.get_run(run["id"])
    assert blocked["actions"] == {
        "resume": True, "abandon": True, "terminated": False, "current": True,
        "reason": "context_budget_exceeded",
    }
    assert store.resume_run(run["id"])["status"] == "queued"
    assert store.get_run(run["id"])["working_state"]["context_recovery_attempts"] == 1
    with pytest.raises(AssistantConflict, match="thread_has_active_run"):
        store.create_run(first["id"], text="接着聊", request_id="a-2")
    store.cancel_run(run["id"])
    assert store.cancel_run(run["id"])["run_epoch"] == 3
    assert not store.complete_run(run["id"], epoch=1, answer="迟到回答", usage={})
    following = store.create_run(first["id"], text="接着聊", request_id="a-2")
    context = store.run_context(following["id"])
    projected, _cost = ContextComposer(MemoryService(db)).compose(context)
    assert "五份材料都读完" not in str(projected)
    assert "接着聊" in str(projected)
    assert [item["content"] for item in store.get_thread(first["id"])["messages"]] == [
        "五份材料都读完", "接着聊",
    ]


def test_budget_pause_can_resume_or_be_abandoned(app_paths) -> None:
    db, _sources = _source_service(app_paths)
    store = AssistantRunStore(db)
    space = store.create_space(name="预算", all_active=True)
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="继续找", request_id="budget-1")
    store.claim_next_run()
    store.fail_run(run["id"], code="tool_budget_exhausted", message="工具上限")
    assert store.get_run(run["id"])["actions"]["resume"] is True
    assert store.resume_run(run["id"])["status"] == "queued"
    assert store.cancel_run(run["id"])["actions"]["terminated"] is True
    failed = store.create_run(thread["id"], text="再试一次", request_id="failed-1")
    store.claim_next_run()
    store.fail_run(failed["id"], code="provider_error", message="提供方暂不可用")
    assert store.get_run(failed["id"])["actions"] == {
        "resume": False, "abandon": True, "terminated": False, "current": True,
        "reason": "provider_error",
    }
    with pytest.raises(AssistantConflict, match="thread_has_active_run"):
        store.create_run(thread["id"], text="继续聊天", request_id="after-failure")
    store.cancel_run(failed["id"])
    assert store.create_run(thread["id"], text="继续聊天", request_id="after-failure")["status"] == "queued"


@pytest.mark.parametrize("later_status", ["completed", "budget_exhausted"])
def test_legacy_superseded_pause_does_not_block_current_run(app_paths, later_status) -> None:
    db, _sources = _source_service(app_paths)
    store = AssistantRunStore(db)
    space = store.create_space(name="旧会话", all_active=True)
    thread = store.create_thread(space["id"])
    old = store.create_run(thread["id"], text="旧任务", request_id="old")
    store.claim_next_run()
    store.fail_run(old["id"], code="tool_budget_exhausted", message="旧预算暂停")
    # The previous release permitted a later Run while the first was paused.
    with db.connect() as connection:
        connection.execute("UPDATE assistant_runs SET status='cancelled' WHERE id=?", (old["id"],))
    later = store.create_run(thread["id"], text="新任务", request_id="later")
    with db.connect() as connection:
        connection.execute("UPDATE assistant_runs SET status='budget_exhausted' WHERE id=?", (old["id"],))
    claimed = store.claim_next_run()
    assert claimed and claimed["id"] == later["id"]
    if later_status == "completed":
        assert store.complete_run(later["id"], epoch=claimed["run_epoch"], answer="已完成", usage={})
    else:
        store.fail_run(later["id"], code="tool_budget_exhausted", message="新预算暂停")

    old_actions = store.get_run(old["id"])["actions"]
    assert old_actions["resume"] is False
    assert old_actions["abandon"] is False
    assert old_actions["reason"] == "run_superseded"
    with pytest.raises(AssistantConflict, match="run_superseded"):
        store.resume_run(old["id"])
    if later_status == "budget_exhausted":
        assert store.get_run(later["id"])["actions"]["resume"] is True
        with pytest.raises(AssistantConflict, match="thread_has_active_run"):
            store.create_run(thread["id"], text="第三问", request_id="third")
        store.cancel_run(later["id"])
    assert store.create_run(thread["id"], text="第三问", request_id="third")["status"] == "queued"


def test_legacy_queued_run_still_blocks_new_run(app_paths) -> None:
    db, _sources = _source_service(app_paths)
    store = AssistantRunStore(db)
    space = store.create_space(name="排队保护", all_active=True)
    thread = store.create_thread(space["id"])
    old = store.create_run(thread["id"], text="旧任务", request_id="old")
    with db.connect() as connection:
        connection.execute("UPDATE assistant_runs SET status='cancelled' WHERE id=?", (old["id"],))
    later = store.create_run(thread["id"], text="新任务", request_id="later")
    with db.connect() as connection:
        connection.execute("UPDATE assistant_runs SET status='budget_exhausted' WHERE id=?", (later["id"],))
    with db.connect() as connection:
        connection.execute("UPDATE assistant_runs SET status='queued' WHERE id=?", (old["id"],))
    assert store.get_run(old["id"])["actions"]["current"] is True
    assert store.get_run(later["id"])["actions"]["resume"] is False
    with pytest.raises(AssistantConflict, match="thread_has_active_run"):
        store.resume_run(later["id"])
    with pytest.raises(AssistantConflict, match="thread_has_active_run"):
        store.create_run(thread["id"], text="第三问", request_id="third")
