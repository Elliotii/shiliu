"""P1 R1: current trigger provenance and the original Memory undo entry."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shiliu.assistant.api import router
from shiliu.assistant.tools import AssistantToolRegistry
from test_assistant_notifications_p1 import wiki_parts, service, save_memory


def client_for(s):
    app = FastAPI()
    app.include_router(router)
    app.state.core = SimpleNamespace(
        config=SimpleNamespace(assistant_enabled=True), assistant_runtime=s.runtime
    )
    return TestClient(app)


def version_message(s, version):
    return next(
        row
        for row in s.list(show_history=True)["items"]
        if row["origin_type"] == "memory_change"
        and row["object_refs"][0]["version"] == version
    )


def test_current_dialogue_correction_is_not_original_auto_extraction(
    wiki_parts, record_property
):
    s = service(wiki_parts)
    _, _, _, _, msg, run, _ = wiki_parts
    memory = save_memory(s, origin="extracted", source_message_ids=[msg])
    assert version_message(s, 1)["source_type"] == "auto_memory"
    with client_for(s) as client:
        refused = client.post(
            f"/api/assistant/memories/{memory['id']}/undo-created",
            json={
                "space_id": wiki_parts[3],
                "save_operation_key": "p1-save",
                "expected_version": 1,
                "operation_key": "r1-auto-undo-refused",
            },
        )
        assert refused.status_code == 409
    assert s.runtime.memories.get(memory["id"])["version"] == 1
    s.runtime.memories.correct(
        memory["id"],
        text="用户现在明确更正为晚上学习",
        expected_version=1,
        operation_key="r1-dialogue-correction",
        source_message_ids=[msg],
        _notification_causes={"request_message_id": msg, "run_id": run},
    )
    corrected = version_message(s, 2)
    record_property("actual_source_type", corrected["source_type"])
    assert corrected["source_type"] == "dialogue"
    assert corrected["cause_refs"]["request_message_id"] == msg
    assert s.runtime.memories.get(memory["id"])["origin"] == "extracted"


@pytest.mark.parametrize("origin", ["extracted", "explicit"])
def test_original_management_correction_and_forget_are_manual(wiki_parts, origin):
    s = service(wiki_parts)
    msg = wiki_parts[4]
    memory = save_memory(s, origin=origin, source_message_ids=[msg])
    with client_for(s) as client:
        response = client.patch(
            f"/api/assistant/memories/{memory['id']}",
            json={
                "text": "由记忆管理入口明确更正",
                "expected_version": 1,
                "operation_key": "r1-ui-correct",
            },
        )
        assert response.status_code == 200, response.text
        corrected = version_message(s, 2)
        assert corrected["source_type"] == "manual"
        assert corrected["cause_refs"]["source_message_ids"] == [msg]
        assert "request_message_id" not in corrected["cause_refs"]
        assert response.json()["memory"]["origin"] == origin
        response = client.delete(
            f"/api/assistant/memories/{memory['id']}",
            params={"expected_version": 2, "operation_key": "r1-ui-forget"},
        )
        assert response.status_code == 200, response.text
    forgotten = version_message(s, 3)
    assert forgotten["source_type"] == "manual"
    assert forgotten["cause_refs"]["source_message_ids"] == [msg]
    assert all(row["undo_ref"] is None for row in s.list(show_history=True)["items"])


def test_production_dialogue_forget_retains_its_current_request(wiki_parts):
    s = service(wiki_parts)
    db, _, _, _, msg, run, sources = wiki_parts
    memory = save_memory(s, origin="extracted", source_message_ids=[msg])
    with db.connect() as c:
        c.execute(
            "UPDATE assistant_messages SET content='请忘记此前记录的学习偏好' WHERE id=%s",
            (msg,),
        )
    tools = AssistantToolRegistry(
        store=s.store, memories=s.runtime.memories, sources=sources
    )
    result = asyncio.run(
        tools.execute(
            name="memory_forget",
            arguments={"memory_id": memory["id"], "expected_version": 1},
            call_id="r1-forget",
            run_context=s.store.run_context(run),
        )
    )
    assert result["status"] == "ok", result
    forgotten = version_message(s, 2)
    assert forgotten["source_type"] == "dialogue"
    assert forgotten["cause_refs"]["request_message_id"] == msg
    assert forgotten["cause_refs"]["run_id"] == run


def test_original_undo_api_updates_the_same_message_atomically_and_replays(
    wiki_parts, monkeypatch, record_property
):
    import shiliu.assistant.notifications as notifications

    s = service(wiki_parts)
    space = wiki_parts[3]
    memory = save_memory(s)
    original = version_message(s, 1)
    payload = {
        "space_id": space,
        "save_operation_key": "p1-save",
        "expected_version": 1,
        "operation_key": "r1-original-api-undo",
    }
    path = f"/api/assistant/memories/{memory['id']}/undo-created"
    record = notifications.record

    def failure(*a, **kw):
        raise RuntimeError("r1 notification insert failed")

    with client_for(s) as client:
        monkeypatch.setattr(notifications, "record", failure)
        with pytest.raises(RuntimeError, match="r1 notification insert failed"):
            client.post(path, json=payload)
        assert s.runtime.memories.get(memory["id"])["version"] == 1
        assert s.runtime.memories.current_epoch() == 1
        assert s.get(original["id"])["undo_ref"] is None
        monkeypatch.setattr(notifications, "record", record)
        response = client.post(path, json=payload)
        assert response.status_code == 200, response.text
        message = s.get(original["id"])
        record_property("actual_message_state", message["business_state"])
        record_property(
            "actual_memory_state", s.runtime.memories.get(memory["id"])["status"]
        )
        assert message["business_state"] == "undone"
        assert message["undo_ref"] == payload["operation_key"]
        assert message["created_at"] == original["created_at"]
        assert message["read_at"] == original["read_at"]
        assert message["source_type"] == original["source_type"]
        before = s.list(show_history=True)
        assert client.post(path, json=payload).json() == response.json()
        assert s.list(show_history=True) == before
        assert s.runtime.memories.get(memory["id"])["version"] == 2
        assert s.runtime.memories.current_epoch() == 2
        with s.db.connect(read_only=True) as c:
            assert (
                c.execute("SELECT count(*) n FROM assistant_notifications").fetchone()[
                    "n"
                ]
                == 1
            )
            assert (
                c.execute(
                    "SELECT count(*) n FROM assistant_jobs WHERE kind='memory_purge'"
                ).fetchone()["n"]
                == 1
            )


def test_original_undo_materializes_only_its_exact_missing_creation(wiki_parts):
    s = service(wiki_parts)
    space = wiki_parts[3]
    memory = save_memory(s)
    original = version_message(s, 1)
    with s.db.connect() as c:
        c.execute("DELETE FROM assistant_notifications WHERE id=%s", (original["id"],))
    with client_for(s) as client:
        response = client.post(
            f"/api/assistant/memories/{memory['id']}/undo-created",
            json={
                "space_id": space,
                "save_operation_key": "p1-save",
                "expected_version": 1,
                "operation_key": "r1-missing-index-undo",
            },
        )
        assert response.status_code == 200, response.text
    message = s.get(original["id"])
    assert message["business_state"] == "undone"
    assert message["created_at"] == original["created_at"]
    assert message["source_type"] == "system"  # Unknown old trigger is not guessed.
    assert len(s.list(show_history=True)["items"]) == 1
