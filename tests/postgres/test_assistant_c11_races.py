"""C11: actual Assistant append and final/cancel transactions overlap in PG."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, current_thread
import time

import pytest

from test_assistant_store_core import assistant_store  # noqa: F401
from shiliu.assistant import pg_store
from shiliu.assistant.runtime_contract import AssistantConflict
from shiliu.storage import fences


def _running(store):
    space = store.create_space(name="C11 synthetic")
    thread = store.create_thread(space["id"])
    store.create_run(thread["id"], text="synthetic input", request_id="c11")
    return space, thread, store.claim_next_run()


def _race(store, monkeypatch, winner, loser, *, message_writers=False):
    """Pause a real lock holder; prove the other real transaction waits on it.

    Hooks only gate scheduling around the existing lock function. All locks,
    status checks, message allocation, commits and events use product code.
    """
    start = Barrier(2)
    locked, release, loser_entered = Event(), Event(), Event()
    pids, first_calls = {}, set()
    original = pg_store.pg_guard_tool_operation if message_writers else fences.lock_thread_run

    def lock(conn, *args, **kwargs):
        name = current_thread().name
        if name not in {"c11-winner", "c11-loser"} or name in first_calls:
            return original(conn, *args, **kwargs)
        first_calls.add(name)
        pids[name] = conn.info.backend_pid
        if name == "c11-loser":
            assert locked.wait(5), "winner failed to acquire real locks"
            loser_entered.set()
        result = original(conn, *args, **kwargs)
        if name == "c11-winner":
            locked.set()
            assert release.wait(5), "observer failed to release lock holder"
        return result

    if message_writers:
        monkeypatch.setattr(pg_store, "pg_guard_tool_operation", lock)
    else:
        monkeypatch.setattr(pg_store, "lock_thread_run", lock)
        monkeypatch.setattr(fences, "lock_thread_run", lock)

    def invoke(name, operation):
        current_thread().name = name
        start.wait(timeout=5)
        return operation()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(invoke, "c11-winner", winner)
        second = executor.submit(invoke, "c11-loser", loser)
        try:
            assert locked.wait(5) and loser_entered.wait(5)
            assert pids["c11-winner"] != pids["c11-loser"]
            deadline = time.monotonic() + 2
            waiting = False
            while time.monotonic() < deadline:
                with store.db.connect(read_only=True) as observer:
                    row = observer.execute(
                        "SELECT wait_event_type,query,pg_blocking_pids(pid) AS blockers "
                        "FROM pg_stat_activity WHERE pid=%s", (pids["c11-loser"],),
                    ).fetchone()
                waiting = bool(
                    row and row["wait_event_type"] == "Lock"
                    and "SELECT id FROM shiliu.assistant_threads" in row["query"]
                    and pids["c11-winner"] in row["blockers"]
                )
                if waiting:
                    break
                time.sleep(.01)
            assert waiting, "contender did not block on the real thread-before-run fence"
            assert not first.done() and not second.done()
        finally:
            release.set()
        return first.result(timeout=5), second.result(timeout=5)


def test_two_actual_assistant_message_writers_preserve_both_messages(assistant_store, monkeypatch):  # noqa: F811 -- pytest fixture injection
    store, _ = assistant_store
    _, thread, run = _running(store)

    def append(content):
        return store.save_assistant_tool_message(
            run["id"], content=content, provider_payload={"synthetic": content},
            expected_epoch=run["run_epoch"],
        )

    first, second = _race(store, monkeypatch, lambda: append("writer one"),
                          lambda: append("writer two"), message_writers=True)
    messages = store.get_thread(thread["id"], include_internal=True)["messages"]
    assert first != second
    assert [m["seq"] for m in messages] == [1, 2, 3]
    assert [(m["id"], m["content"]) for m in messages[1:]] == [
        (first, "writer one"), (second, "writer two"),
    ]


@pytest.mark.parametrize("first_action", ["complete", "cancel"])
def test_actual_assistant_final_cancel_race_and_terminal_fence(assistant_store, monkeypatch, first_action):  # noqa: F811 -- pytest fixture injection
    store, _ = assistant_store
    space, thread, run = _running(store)
    epoch = run["run_epoch"]

    def complete():
        return store.try_complete_run(
            run["id"], epoch=epoch, answer="synthetic final", usage={},
            expected_scope_version=space["scope_version"],
            expected_observed_memory_epoch=run["observed_memory_epoch"],
            dependency_refs=[], expected_task_note_version=None,
        )

    def cancel():
        return store.cancel_run(run["id"])["status"]

    operations = {"complete": complete, "cancel": cancel}
    second_action = "cancel" if first_action == "complete" else "complete"
    results = _race(store, monkeypatch, operations[first_action], operations[second_action])
    expected = "completed" if first_action == "complete" else "cancelled"
    assert results == (("completed", "completed") if expected == "completed" else ("cancelled", "run_fenced"))
    final = store.get_run(run["id"])
    assert final["status"] == expected and final["completed_at"] is not None
    assert final["run_epoch"] == epoch + (expected == "cancelled")
    events = store.events(run["id"])
    assert [e["event_type"] for e in events] == ["run_queued", "run_started", "run_" + expected]
    before = store.get_thread(thread["id"], include_internal=True)["messages"]
    assert len(before) == (2 if expected == "completed" else 1)
    assert complete() == "run_fenced"
    with pytest.raises(AssistantConflict, match="run_fenced"):
        store.save_assistant_tool_message(
            run["id"], content="late", provider_payload={}, expected_epoch=epoch,
        )
    assert store.get_thread(thread["id"], include_internal=True)["messages"] == before
    assert store.events(run["id"]) == events
