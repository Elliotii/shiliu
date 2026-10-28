"""Real PostgreSQL contracts for the first migrated Assistant Store boundary."""
from datetime import datetime, timezone
import os
from pathlib import Path

import pytest

from shiliu.config import PostgresConfig
from shiliu.assistant.pg_store import PgAssistantRunStore
from shiliu.db import Database
from shiliu.storage.scope import ResourceContext
from schema_support import formal_target


@pytest.fixture
def assistant_store():
    cfg = PostgresConfig(os.environ.get("SHILIU_DATABASE_URL", ""),
                         Path(os.environ.get("SHILIU_ARTIFACT_ROOT", "")),
                         os.environ.get("SHILIU_ENV", ""))
    from shiliu.storage.postgres import PgDatabase
    with formal_target(cfg) as (runtime, admin):
        with PgDatabase(runtime) as pool:
            yield PgAssistantRunStore(Database(pool, ResourceContext("personal:local_operator", "local_operator"))), admin


def test_create_run_is_scoped_atomic_and_replays_current_run(assistant_store):
    store, _ = assistant_store
    space = store.create_space(name="core")
    thread = store.create_thread(space["id"], title="core")
    run = store.create_run(thread["id"], text="first input", request_id="same")
    assert run["status"] == "queued"
    replay = store.create_run(thread["id"], text="different valid input", request_id="same",
                              answer_message_id="ignored-on-replay", receipt_only=True)
    assert replay["id"] == run["id"]
    assert replay["working_state"] == run["working_state"]
    history = store.get_thread(thread["id"])
    assert len(history["messages"]) == 1
    assert len(history["runs"]) == 1
    assert [(e["seq"], e["event_type"]) for e in _events(store)] == [(1, "run_queued")]


def _events(store):
    with store.db.connect(read_only=True) as conn:
        return conn.execute("SELECT seq,event_type FROM shiliu.assistant_run_events "
                             "WHERE workspace_id=%s ORDER BY seq", (store.workspace_id,)).fetchall()


def test_second_principal_can_own_resources_but_cannot_read_first(assistant_store):
    store, _admin = assistant_store
    from psycopg import connect
    from isolation import TASK_ROOT
    cfg = store.db.pg.config
    from shiliu.config import LIBPQ_DISABLED_PASSFILE
    with connect(cfg.database_url, passfile=LIBPQ_DISABLED_PASSFILE) as conn:
        conn.execute("INSERT INTO shiliu.users(id,display_name,created_at) VALUES('review_user','Review',%s)",
                     (datetime.now(timezone.utc),))
        conn.execute("INSERT INTO shiliu.workspaces(id,kind,owner_user_id,created_at) "
                     "VALUES('personal:review_user','personal','review_user',%s)",
                     (datetime.now(timezone.utc),))
        conn.execute("INSERT INTO shiliu.workspace_guards(workspace_id) VALUES('personal:review_user')")
    from shiliu.storage.postgres import PgDatabase
    from dataclasses import replace
    from psycopg.conninfo import make_conninfo
    from isolation import RUN_USER, guard
    cfg = store.db.pg.config
    parts = guard(cfg)
    with PgDatabase(replace(cfg, database_url=make_conninfo(**dict(parts, user=RUN_USER)))) as pool:
        other = PgAssistantRunStore(Database(pool, ResourceContext("personal:review_user", "review_user")))
        theirs = other.create_space(name="private")
        theirs_thread = other.create_thread(theirs["id"])
        other.create_run(theirs_thread["id"], text="private", request_id="r")
        with pytest.raises(KeyError):
            other.get_thread("nonexistent")
        with pytest.raises(KeyError):
            other.create_run("missing", text="valid", request_id="r")
    with pytest.raises(KeyError):
        store.get_thread(theirs_thread["id"])


def test_invalid_first_input_and_out_of_scope_thread_fail_closed(assistant_store):
    store, _ = assistant_store
    with pytest.raises(ValueError, match="input_empty"):
        store.create_run("missing", text="  ", request_id="r")
    with pytest.raises(KeyError):
        store.create_run("missing", text="valid", request_id="r")


def test_run_fence_serializes_tool_intent_completion_and_cancel(assistant_store):
    store, _ = assistant_store
    space = store.create_space(name="fence")
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="use tool", request_id="fence")
    with store.db.connect() as conn:
        conn.execute("UPDATE shiliu.assistant_runs SET status='running' WHERE workspace_id=%s AND id=%s",
                     (store.workspace_id, run["id"]))
    current = store.get_run(run["id"])
    epoch = current["run_epoch"]
    assert store.begin_tool_call(run["id"], ordinal=1, call_id="call-1", name="collection_search",
                                 arguments={"query": "x"}, expected_epoch=epoch) is None
    store.save_assistant_tool_message(run["id"], content="{}", provider_payload={"tool_calls": []},
                                      expected_epoch=epoch)
    store.finish_tool_call(run["id"], call_id="call-1", result={"status": "ok", "summary": "done"},
                           expected_epoch=epoch)
    assert [e["event_type"] for e in store.events(run["id"])] == [
        "run_queued", "tool_started", "tool_completed"]
    assert [e["event_type"] for e in store.events(run["id"], after_seq=1)] == ["tool_started", "tool_completed"]
    result = store.resolve_run_result(f"run-result:{run['id']}:call-1", current_thread_id=thread["id"],
                                      current_scope_version=1)
    assert result["result"] == {"status": "ok", "summary": "done"}
    assert store.completed_tool_message_count(run["id"]) == 0
    cancelled = store.cancel_run(run["id"])
    assert cancelled["status"] == "cancelled"
    with pytest.raises(Exception, match="run_fenced"):
        store.begin_tool_call(run["id"], ordinal=2, call_id="call-2", name="collection_search",
                              arguments={"query": "late"}, expected_epoch=epoch)


def test_context_installation_rolls_message_projection_and_thread_state_back(assistant_store):
    store, _ = assistant_store
    space = store.create_space(name="context")
    thread = store.create_thread(space["id"])
    run = store.create_run(thread["id"], text="raw", request_id="context")
    with store.db.connect() as conn:
        conn.execute("UPDATE shiliu.assistant_runs SET status='running' WHERE workspace_id=%s AND id=%s",
                     (store.workspace_id, run["id"]))
    message = store.get_thread(thread["id"])["messages"][0]
    from shiliu.storage.dto import row_dto
    with store.db.connect(read_only=True) as conn:
        raw_message = row_dto(conn.execute("SELECT * FROM shiliu.assistant_messages WHERE workspace_id=%s AND id=%s",
                                           (store.workspace_id, message["id"])).fetchone(),
                               timestamps=("created_at",))
    projection = {"format_version": 1,
                  "source_fingerprint": store.message_context_fingerprint(raw_message),
                  "identity": {key: raw_message.get(key) for key in ("id", "seq", "run_id", "role", "created_at")},
                  "message": {"role": "user", "content": "raw"},
                  "dependency_refs": [], "source_message_ids": [], "read_spans": [],
                  "materials": [], "delivery": {"confirmed": False}}
    state = {"format_version": 1, "revision": 1,
             "entries": [{"kind": "message", "message_id": message["id"]}],
             "checkpoint": None}
    with pytest.raises(RuntimeError, match="injected_context_failure"):
        with store.db.pg.transaction() as conn:
            conn.execute("SELECT id FROM shiliu.assistant_threads WHERE workspace_id=%s AND id=%s FOR UPDATE",
                         (store.workspace_id, thread["id"]))
            store.install_working_context(conn, thread_id=thread["id"], state=state,
                                          projections={message["id"]: projection})
            assert conn.execute("SELECT context_state_json FROM shiliu.assistant_threads "
                                "WHERE workspace_id=%s AND id=%s",
                                (store.workspace_id, thread["id"])).fetchone()["context_state_json"] == state
            persisted = conn.execute("SELECT provider_payload_json FROM shiliu.assistant_messages "
                                     "WHERE workspace_id=%s AND id=%s",
                                     (store.workspace_id, message["id"])).fetchone()["provider_payload_json"]
            assert persisted["model_projection"] == projection
            raise RuntimeError("injected_context_failure")
    history = store.get_thread(thread["id"],include_internal=True)
    assert history["context_state_json"] == {}
    assert "model_projection" not in history["messages"][0]["provider_payload_json"]


def test_pg_store_uses_shared_job_lane_and_dispatch_receipt_contract(assistant_store):
    store, _ = assistant_store
    from shiliu.storage.fences import CoordinationConflict
    from shiliu.storage.scheduler import job_transition

    with store.db.connect() as conn:
        job_id = store.enqueue_job(conn, context=store.context, kind="wiki_integrate",
                                   dedupe_key="dedupe", payload={"space_id": 7})
        assert store.enqueue_job(conn, context=store.context, kind="wiki_integrate",
                                 dedupe_key="dedupe", payload={"space_id": 7}) == job_id
    job = store.claim_job(owner="worker", kinds=("wiki_integrate",))
    assert job["id"] == job_id and job["attempt"] == 1 and job["lease_epoch"] == 1
    assert store.claim_job(owner="other", kinds=("wiki_integrate",)) is None
    with store.db.connect() as conn:
        job_transition(conn, store.context, job_id, "worker", 1, action="stage",
                       proposal={"candidate": "persisted"})
    assert store.heartbeat_job(job_id,owner="worker",lease_epoch=1)
    store.finish_job(job_id,owner="worker",lease_epoch=1)
    dispatch = store.reserve_model_dispatch("dispatch-1", lane="foreground", request_limit=1,
                                            request_hash="a" * 64)
    assert dispatch["status"] == "reserved"
    assert store.reserve_model_dispatch("dispatch-1", lane="foreground", request_limit=1,
                                        request_hash="a" * 64)["dispatch_id"] == "dispatch-1"
    with pytest.raises(CoordinationConflict, match="dispatch_identity_mismatch"):
        store.reserve_model_dispatch("dispatch-1", lane="foreground", request_limit=1,
                                     request_hash="b" * 64)
    unknown = store.mark_dispatch_unknown("dispatch-1")
    assert unknown["status"] == "unknown" and unknown["usage"] is None
    assert store.mark_dispatch_unknown("dispatch-1")["status"] == "unknown"
    settled = store.settle_model_dispatch("dispatch-1", usage={"input_tokens": 3})
    assert settled["status"] == "settled" and settled["usage"] == {"input_tokens": 3}
    released = store.reserve_model_dispatch("dispatch-2", lane="background", request_limit=1,
                                            request_hash="c" * 64)
    assert store.release_model_request("dispatch-2")["status"] == "released"
    assert store.release_model_request("dispatch-2")["status"] == "released"
    with pytest.raises(CoordinationConflict, match="already_sent_or_settled"):
        store.release_model_request("dispatch-1")


def test_foreground_claim_completion_and_owner_loss_recovery(assistant_store):
    store, _ = assistant_store
    space=store.create_space(name="foreground")
    thread=store.create_thread(space["id"])
    queued=store.create_run(thread["id"],text="question",request_id="foreground")
    claimed=store.claim_next_run()
    assert claimed["id"]==queued["id"] and claimed["status"]=="running"
    assert store.has_active_runs()
    outcome=store.try_complete_run(queued["id"],epoch=claimed["run_epoch"],answer="answer",usage={},
                                   expected_scope_version=space["scope_version"],
                                   expected_observed_memory_epoch=0,dependency_refs=[],
                                   expected_task_note_version=None)
    assert outcome=="completed"
    assert not store.has_active_runs()
    extraction=store.list_jobs()[0]
    assert extraction["kind"]=="memory_extract" and extraction["payload"]["run_ids"]==[queued["id"]]
    assert store.get_thread(thread["id"])["can_save"]
    assert not store.get_run(queued["id"])["actions"]["current"]
    assert not store.maintenance_idle(seconds=180)

    queued2=store.create_run(thread["id"],text="next",request_id="next")
    claimed2=store.claim_next_run()
    assert claimed2["id"]==queued2["id"]
    assert store.recover_interrupted_runs()==1
    recovered=store.get_run(queued2["id"])
    assert recovered["status"]=="interrupted" and recovered["run_epoch"]==claimed2["run_epoch"]
    assert [event["event_type"] for event in store.events(queued2["id"])]==["run_queued","run_started","run_interrupted"]


def test_tool_writes_require_explicit_or_scoped_epoch(assistant_store):
    from shiliu.assistant.store import AssistantConflict
    store, _ = assistant_store
    space=store.create_space(name="strict-fence")
    thread=store.create_thread(space["id"])
    run=store.create_run(thread["id"],text="tool",request_id="strict")
    run=store.claim_next_run()
    operations=[
        lambda:store.begin_tool_call(run["id"],ordinal=1,call_id="call",name="search",arguments={}),
        lambda:store.finish_tool_call(run["id"],call_id="call",result={}),
        lambda:store.save_tool_result_message(run["id"],content="{}",provider_payload={"tool_call_id":"call"}),
        lambda:store.save_assistant_tool_message(run["id"],content="tool",provider_payload={}),
    ]
    for operation in operations:
        with pytest.raises(AssistantConflict,match="epoch_required"):
            operation()
    with store.tool_execution_scope(run["id"],run["run_epoch"]):
        operations[0]()
        operations[1]()
        operations[2]()
        operations[3]()
    store.cancel_run(run["id"])
    with store.tool_execution_scope(run["id"],run["run_epoch"]):
        for operation in operations:
            with pytest.raises(AssistantConflict,match="run_fenced"):
                operation()


@pytest.mark.parametrize("requested",[False,True])
def test_reserved_final_dispatch_completes_after_tools_stop(assistant_store,requested):
    from shiliu.assistant.store import AssistantConflict
    store,_=assistant_store
    space=store.create_space(name="final")
    thread=store.create_thread(space["id"])
    run=store.create_run(thread["id"],text="final",request_id="final")
    run=store.claim_next_run()
    store.initialize_execution_budget(run["id"],epoch=run["run_epoch"],model_limit=2,tool_limit=1)
    if requested:store.request_finish(run["id"])
    store.dispatch_model(run["id"],epoch=run["run_epoch"],final=True,input_tokens=1,output_tokens=1)
    store.save_step(run["id"],epoch=run["run_epoch"],step_count=1,tool_count=0,usage={})
    with pytest.raises(AssistantConflict,match="run_fenced"):
        store.begin_tool_call(run["id"],ordinal=1,call_id="late",name="search",arguments={},expected_epoch=run["run_epoch"])
    assert store.try_complete_run(run["id"],epoch=run["run_epoch"],answer="final",usage={},
        expected_scope_version=space["scope_version"],expected_observed_memory_epoch=0,
        dependency_refs=[],expected_task_note_version=None)=="completed"


def test_runtime_graph_entry_propagates_and_resets_tool_scope(assistant_store):
    import asyncio
    from langgraph.graph import StateGraph,START,END
    from shiliu.assistant.runtime import AssistantExecutionGraph,ExecutionState
    from shiliu.assistant.store import _TOOL_EXECUTION
    store,_=assistant_store
    space=store.create_space(name="graph")
    thread=store.create_thread(space["id"])
    store.create_run(thread["id"],text="graph",request_id="graph")
    run=store.claim_next_run()
    async def node(state):
        assert _TOOL_EXECUTION.get()==(run["id"],run["run_epoch"])
        await asyncio.to_thread(store.begin_tool_call,run["id"],ordinal=1,call_id="graph-tool",name="search",arguments={})
        return state
    graph=StateGraph(ExecutionState)
    graph.add_node("boundary",node);graph.add_edge(START,"boundary");graph.add_edge("boundary",END)
    runtime=object.__new__(AssistantExecutionGraph)
    runtime.store=store;runtime.max_steps=2;runtime.max_tool_calls=1;runtime.compiled=graph.compile()
    asyncio.run(runtime.run(run))
    assert _TOOL_EXECUTION.get() is None
    with pytest.raises(RuntimeError,match="injected"):
        with store.tool_execution_scope(run["id"],run["run_epoch"]):
            raise RuntimeError("injected")
    assert _TOOL_EXECUTION.get() is None


def test_context_install_rejects_changed_source_or_navigation_snapshot(assistant_store):
    from shiliu.assistant.store import AssistantConflict
    from psycopg.types.json import Jsonb
    store,_=assistant_store
    space=store.create_space(name="snapshot")
    thread=store.create_thread(space["id"])
    store.create_run(thread["id"],text="snapshot",request_id="snapshot")
    run=store.claim_next_run()
    with store.db.connect() as conn:
        source=store.working_source_guard(conn,space_id=space["id"])
        navigation=store.working_navigation_guard(conn,thread_id=thread["id"])
        conn.execute("INSERT INTO shiliu.favorite_sources(workspace_id,folder_id,created_at,updated_at) VALUES(%s,913,clock_timestamp(),clock_timestamp())",
                     (store.workspace_id,))
    arguments=dict(epoch=run["run_epoch"],expected_revision=0,state={"format_version":1,"revision":1,"entries":[],"checkpoint":None},
        projections={},message_frontier=1,memory_epoch=0,source_guard=source,scope_version=space["scope_version"],
        task_subset=None,dependency_refs=[],navigation_guard=navigation)
    with pytest.raises(AssistantConflict,match="working_context_changed"):
        store.save_working_context(run["id"],**arguments)
    with store.db.connect() as conn:
        arguments["source_guard"]=store.working_source_guard(conn,space_id=space["id"])
        conn.execute("UPDATE shiliu.assistant_runs SET working_state_json=%s WHERE workspace_id=%s AND id=%s",
                     (Jsonb({"task_focus":{"goal":"changed"}}),store.workspace_id,run["id"]))
    with pytest.raises(AssistantConflict,match="working_context_changed"):
        store.save_working_context(run["id"],**arguments)
    with store.db.connect(read_only=True) as conn:
        arguments["navigation_guard"]=store.working_navigation_guard(conn,thread_id=thread["id"])
    store.save_working_context(run["id"],**arguments)
    assert store.get_thread(thread["id"],include_internal=True)["context_state_json"]["revision"]==1


def test_provider_accounting_takes_thread_before_run_lock(assistant_store):
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace
    import time
    store,_=assistant_store
    space=store.create_space(name="accounting-locks")
    thread=store.create_thread(space["id"])
    store.create_run(thread["id"],text="accounting",request_id="accounting")
    run=store.claim_next_run()
    with ThreadPoolExecutor(max_workers=1) as executor:
        with store.db.connect() as blocker:
            blocker.execute("SELECT id FROM shiliu.assistant_threads WHERE id=%s FOR UPDATE",(thread["id"],))
            future=executor.submit(store.record_provider_response,run["id"],SimpleNamespace(usage={"input_tokens":1}),late=False,call_id="response")
            deadline=time.monotonic()+2
            waiting=False
            while time.monotonic()<deadline:
                with store.db.connect(read_only=True) as observer:
                    waiting=bool(observer.execute("SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE 'SELECT id FROM shiliu.assistant_threads%'").fetchone())
                if waiting:break
                time.sleep(.01)
            assert waiting
            # A run-first writer would hold this lock while waiting for thread.
            blocker.execute("SELECT id FROM shiliu.assistant_runs WHERE id=%s FOR UPDATE NOWAIT",(run["id"],))
        future.result(timeout=5)
    assert store.get_run(run["id"])["usage"]["input_tokens"]==1


def test_real_context_composer_reuses_native_jsonb_projection_and_delivery(assistant_store):
    from types import SimpleNamespace
    from shiliu.assistant.memory import MemoryService
    from shiliu.assistant.task_notes import TaskNoteService
    from shiliu.assistant.working_context import WorkingContextComposer
    from shiliu.assistant.provider import OpenAICompatibleAssistantProvider
    from shiliu.assistant.provider_request import EndpointCapabilities
    store,_=assistant_store
    space=store.create_space(name="composer")
    thread=store.create_thread(space["id"])
    store.create_run(thread["id"],text="synthetic request",request_id="composer")
    run=store.claim_next_run()
    memories=MemoryService(store.db)
    tools=SimpleNamespace(memories=memories,schemas=lambda:[],scope_identity=lambda space:{"id":space["id"],"version":space["scope_version"]},
                          dependency_refs_valid=lambda *args:True)
    composer=WorkingContextComposer(store=store,tools=tools,task_notes=TaskNoteService(store.db,memories))
    provider=OpenAICompatibleAssistantProvider(base_url="https://synthetic.invalid/v1",api_key="synthetic",model="synthetic",
        capabilities=EndpointCapabilities("https://synthetic.invalid/v1","synthetic",1048576,65536,4096,True,"synthetic offline fixture"))
    candidate=composer.prepare(run["id"],provider=provider)
    composer.persist(candidate)
    store.confirm_model_delivery(run["id"],epoch=run["run_epoch"],spans=[],message_ids=list(candidate.projections),context_revision=1)
    second=composer.prepare(run["id"],provider=provider)
    assert second.expected_revision==1
    assert second.request.body["messages"]==candidate.request.body["messages"]
    assert all(m["provider_payload_json"]["model_projection"]["delivery"]["confirmed"] for m in store.get_thread(thread["id"],include_internal=True)["messages"])


@pytest.mark.parametrize("requested",[False,True])
def test_full_graph_fake_provider_completes_with_pg_context_and_usage(assistant_store,requested):
    import asyncio
    from types import SimpleNamespace
    from shiliu.assistant.memory import MemoryService
    from shiliu.assistant.runtime import AssistantExecutionGraph
    from shiliu.assistant.provider import OpenAICompatibleAssistantProvider,ModelTurn
    from shiliu.assistant.provider_request import EndpointCapabilities
    store,_=assistant_store
    space=store.create_space(name="full-graph")
    thread=store.create_thread(space["id"])
    store.create_run(thread["id"],text="synthetic answer",request_id="full-graph")
    run=store.claim_next_run()
    memories=MemoryService(store.db)
    tools=SimpleNamespace(memories=memories,sources=None,schemas=lambda:[],scope_identity=lambda space:{"id":space["id"]},
        dependency_refs_valid=lambda *args:True)
    class Provider(OpenAICompatibleAssistantProvider):
        calls=0
        def send_prepared(self,request,**kwargs):
            self.calls+=1
            return ModelTurn(text="synthetic completed answer",tool_calls=[],finish_reason="stop",usage={"input_tokens":3,"output_tokens":2})
    provider=Provider(base_url="https://synthetic.invalid/v1",api_key="synthetic",model="synthetic",
        capabilities=EndpointCapabilities("https://synthetic.invalid/v1","synthetic",1048576,65536,4096,True,"offline fixture"))
    graph=AssistantExecutionGraph(store=store,memories=memories,tools=tools,provider_factory=lambda:provider)
    if requested:store.request_finish(run["id"])
    asyncio.run(graph.run(run))
    current=store.get_run(run["id"])
    assert current["status"]=="completed", current
    assert provider.calls==1
    assert current["usage"]=={"input_tokens":3,"output_tokens":2}
    with store.db.connect(read_only=True) as conn:
        receipts=conn.execute("SELECT status,usage FROM shiliu.model_dispatch_receipts WHERE run_id=%s",(run["id"],)).fetchall()
    assert len(receipts)==1 and receipts[0]["status"]=="settled"


def test_full_graph_memory_tool_uses_pg_intent_fence_and_receipt(assistant_store):
    import asyncio
    from types import SimpleNamespace
    from shiliu.assistant.memory import MemoryService
    from shiliu.assistant.runtime import AssistantExecutionGraph
    from shiliu.assistant.tools import AssistantToolRegistry
    from shiliu.assistant.provider import OpenAICompatibleAssistantProvider,ModelTurn,NativeToolCall
    from shiliu.assistant.provider_request import EndpointCapabilities
    store,_=assistant_store
    space=store.create_space(name="memory-tool")
    thread=store.create_thread(space["id"])
    store.create_run(thread["id"],text="请记住我喜欢简短的中文回答",request_id="memory-tool")
    run=store.claim_next_run()
    memories=MemoryService(store.db)
    sources=SimpleNamespace(visible_video_ids=lambda scope:[],source_refs_visible=lambda refs,scope: not refs)
    tools=AssistantToolRegistry(store=store,memories=memories,sources=sources)
    class Provider(OpenAICompatibleAssistantProvider):
        calls=0
        def send_prepared(self,request,**kwargs):
            self.calls+=1
            if self.calls==1:
                return ModelTurn(text="",tool_calls=[NativeToolCall("save-memory","memory_save",{
                    "text":"用户喜欢简短的中文回答","subject_key":"answer-style","kind":"preference","scope_kind":"user"})],
                    finish_reason="tool_calls",usage={"input_tokens":3})
            return ModelTurn(text="已保存你的回答偏好。",tool_calls=[],finish_reason="stop",usage={"input_tokens":4})
    provider=Provider(base_url="https://synthetic.invalid/v1",api_key="synthetic",model="synthetic",
        capabilities=EndpointCapabilities("https://synthetic.invalid/v1","synthetic",1048576,65536,4096,True,"offline fixture"))
    graph=AssistantExecutionGraph(store=store,memories=memories,tools=tools,provider_factory=lambda:provider)
    asyncio.run(graph.run(run))
    assert store.get_run(run["id"])["status"]=="completed",store.get_run(run["id"])["last_error_message"]
    result=store.resolve_run_result(f"run-result:{run['id']}:save-memory",current_thread_id=thread["id"],current_scope_version=1)
    assert result["result"]["status"]=="ok", result["result"]["summary"]
    memory_id=result["result"]["items"][0]["id"]
    assert memories.get(memory_id)["text"]=="用户喜欢简短的中文回答"
    assert provider.calls==2
    with store.db.connect(read_only=True) as conn:
        notification=conn.execute("SELECT * FROM assistant_notifications WHERE origin_type='memory_change'").fetchone()
        assert notification['source_type']=='dialogue'
        assert notification['cause_refs']['run_id']==run['id']
        assert notification['cause_refs']['thread_id']==thread['id']
        assert notification['cause_refs']['request_message_id'] in notification['cause_refs']['source_message_ids']



def test_space_scope_update_cancels_live_runs_and_lists_scoped_threads(assistant_store):
    from shiliu.assistant.store import AssistantConflict
    store,_=assistant_store
    space=store.create_space(name="scope-update")
    threads=[store.create_thread(space["id"]) for _ in range(2)]
    runs=[store.create_run(thread["id"],text=f"question {i}",request_id=f"r{i}") for i,thread in enumerate(threads)]
    assert len(store.list_threads(space_id=space["id"])["threads"])==2
    from seed_rows import SyntheticGraph
    with store.db.connect() as conn:
        video_id=SyntheticGraph(conn).ensure("videos")["id"]
    updated=store.update_space(space["id"],expected_scope_version=1,video_ids=[video_id])
    assert updated["scope_version"]==2 and updated["video_ids"]==[video_id]
    for run in runs:
        current=store.get_run(run["id"])
        assert current["status"]=="cancelled" and current["last_error_code"]=="scope_changed"
    with pytest.raises(AssistantConflict,match="scope_version_conflict"):
        store.update_space(space["id"],expected_scope_version=1,name="stale")


def test_task_navigation_writes_and_job_manual_retry_use_runtime_contracts(assistant_store):
    store,_=assistant_store
    space=store.create_space(name="navigation")
    thread=store.create_thread(space["id"])
    store.create_run(thread["id"],text="focus",request_id="focus")
    run=store.claim_next_run()
    focus={"goal":"actual task","selected_source_refs":[]}
    assert store.save_task_focus(run["id"],epoch=run["run_epoch"],focus=focus)["changed"]
    assert not store.save_task_focus(run["id"],epoch=run["run_epoch"],focus=focus)["changed"]
    request=store.knowledge_save_request(run["id"])
    store.set_task_subset(run["id"],epoch=run["run_epoch"],video_ids=[2],source_message_id=request["source_message_id"],basis_quote="focus")
    assert store.task_space(thread["id"])["video_ids"]==[2]
    assert "task_focus" not in store.get_run(run["id"])["working_state"]
    with store.db.connect() as conn:
        job_id=store.enqueue_job(conn,kind="memory_index",dedupe_key="navigation-job",payload={"space_id":space["id"]})
    job=store.claim_job(owner="worker",kinds=("memory_index",))
    store.fail_job(job,code="synthetic",message="synthetic",blocked=True)
    retried=store.retry_job(job_id)
    assert retried["status"]=="queued" and retried["attempt"]==1
    assert store.list_jobs(space_id=space["id"])[0]["id"]==job_id
    activity=store.maintenance_activity(space["id"])
    assert activity["counts"]=={"queued":1}
    assert activity["items"][0]["id"]==job_id


def test_formal_assistant_router_pg_snapshot_terminal_sse_and_after_seq(assistant_store):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from shiliu.assistant.api import router
    store,_=assistant_store
    app=FastAPI();app.include_router(router)
    app.state.core=SimpleNamespace(config=SimpleNamespace(assistant_enabled=True),assistant_runtime=SimpleNamespace(store=store))
    with TestClient(app) as client:
        response=client.post("/api/assistant/spaces",json={"name":"HTTP"})
        assert response.status_code==201,response.text
        space=response.json()["space"]
        assert client.get(f"/api/assistant/spaces/{space['id']}").status_code==200
        response=client.post("/api/assistant/threads",json={"space_id":space["id"]})
        thread=response.json()["thread"]
        response=client.post(f"/api/assistant/threads/{thread['id']}/runs",json={"input":"HTTP synthetic","request_id":"http"})
        assert response.status_code==202,response.text
        run=response.json()["run"]
        assert client.get(f"/api/assistant/threads/{thread['id']}").status_code==200
        assert client.post(f"/api/assistant/runs/{run['id']}/cancel").status_code==200
        events=client.get(f"/api/assistant/runs/{run['id']}/events",params={"after_seq":1}).json()["events"]
        assert [e["event_type"] for e in events]==["run_cancelled"]
        response=client.get(f"/api/assistant/runs/{run['id']}/stream")
        assert response.headers["content-type"].startswith("text/event-stream")
        assert '"status": "cancelled"' in response.text
        assert response.text.count("data:")==1


def test_late_failure_and_pause_cannot_revoke_resumed_execution(assistant_store):
    from shiliu.assistant.store import AssistantConflict
    store,_=assistant_store
    space=store.create_space(name="diagnostic-fence")
    thread=store.create_thread(space["id"])
    store.create_run(thread["id"],text="diagnostics",request_id="diagnostics")
    first=store.claim_next_run()
    with pytest.raises(AssistantConflict,match="epoch_required"):
        store.fail_run(first["id"],code="missing",message="missing")
    store.pause_run(first["id"],epoch=first["run_epoch"],code="synthetic_pause",message="synthetic")
    store.resume_run(first["id"])
    current=store.claim_next_run()
    assert current["run_epoch"]>first["run_epoch"]
    with store.tool_execution_scope(first["id"],first["run_epoch"]):
        store.fail_run(first["id"],code="late_failure",message="old owner")
        store.pause_run(first["id"],code="late_pause",message="old owner")
    assert store.get_run(first["id"])["status"]=="running"
    assert not any(e["payload"].get("error_code")=="late_failure" for e in store.events(first["id"]))


def test_foundation_and_runtime_compose_only_injected_pg_resources(assistant_store,app_paths,monkeypatch):
    from shiliu.artifacts import ArtifactStore
    from shiliu.assistant.foundation import AssistantFoundation
    from shiliu.assistant.runtime import AssistantRuntime
    from shiliu.migration.legacy_schema import assistant as schema
    from types import SimpleNamespace
    store,_=assistant_store
    def forbidden(*args,**kwargs):raise AssertionError("runtime DDL/provider call forbidden")
    monkeypatch.setattr(schema,"initialize_assistant_foundation_schema",forbidden)
    artifacts=ArtifactStore(app_paths.videos_dir,db=store.db)
    foundation=AssistantFoundation(db=store.db,paths=app_paths,artifacts=artifacts,adapter=SimpleNamespace(),product_search=None)
    runtime=AssistantRuntime(store=foundation.store,sources=foundation.sources,context7=SimpleNamespace(),provider_factory=forbidden)
    assert runtime.store.db is store.db
    assert runtime.memories.db is store.db and runtime.wiki.db is store.db
    assert runtime.capabilities()["runtime"]=="stopped"
    runtime.stop();runtime.stop()
    class OfflineContext:
        async def connect(self):raise RuntimeError("synthetic dependency unavailable")
    runtime.context7=OfflineContext()
    runtime.maintenance_paused=True
    try:
        runtime.start()
        capabilities=runtime.capabilities()
        assert capabilities["runtime"]=="ready"
        assert capabilities["provider_transport"]=="unavailable"
        assert capabilities["context7"]=="unavailable"
    finally:runtime.stop()
    assert runtime._thread is None and runtime.capabilities()["runtime"]=="stopped"


def test_concurrent_same_key_run_creation_has_one_original_input(assistant_store):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    store,_=assistant_store
    space=store.create_space(name="concurrent-create")
    thread=store.create_thread(space["id"])
    barrier=Barrier(2)
    def create(text):
        barrier.wait(timeout=5)
        return store.create_run(thread["id"],text=text,request_id="one-key")
    with ThreadPoolExecutor(max_workers=2) as executor:
        first=executor.submit(create,"first");second=executor.submit(create,"second")
        runs=[first.result(timeout=10),second.result(timeout=10)]
    assert runs[0]["id"]==runs[1]["id"]
    history=store.get_thread(thread["id"])
    assert len(history["messages"])==len(history["runs"])==1
    assert len(store.events(runs[0]["id"]))==1


def test_runtime_sent_timeout_retains_unknown_then_settles_late_usage_once(assistant_store):
    import asyncio
    from threading import Event
    from shiliu.assistant.runtime import AssistantExecutionGraph
    from shiliu.assistant.provider import ModelTurn
    store,_=assistant_store
    space=store.create_space(name="timeout-ledger")
    thread=store.create_thread(space["id"])
    store.create_run(thread["id"],text="timeout",request_id="timeout")
    run=store.claim_next_run()
    store.initialize_execution_budget(run["id"],epoch=run["run_epoch"],model_limit=2,tool_limit=1)
    reservation=store.reserve_model_request(lane="foreground",request_limit=10000,run_id=run["id"],request_hash="d"*64)
    graph=object.__new__(AssistantExecutionGraph);graph.store=store
    release=Event();sent=Event()
    def invoke(call_id):
        sent.set()
        assert release.wait(3)
        return ModelTurn(text="late",usage={"input_tokens":7})
    async def exercise():
        try:
            with store.tool_execution_scope(run["id"],run["run_epoch"]):
                control,_=await graph._wait_for_model({"run_id":run["id"],"epoch":run["run_epoch"]},invoke,
                    timeout=.2,input_tokens=1,output_tokens=1,dispatch_id=reservation["dispatch_id"])
                assert control=="timeout" and sent.is_set()
                with store.db.connect(read_only=True) as conn:
                    receipt=conn.execute("SELECT status,usage FROM shiliu.model_dispatch_receipts WHERE dispatch_id=%s",
                                         (reservation["dispatch_id"],)).fetchone()
                assert receipt["status"]=="unknown" and receipt["usage"] is None
                release.set()
                for _ in range(50):
                    await asyncio.sleep(.02)
                    with store.db.connect(read_only=True) as conn:
                        receipt=conn.execute("SELECT status,usage FROM shiliu.model_dispatch_receipts WHERE dispatch_id=%s",
                                             (reservation["dispatch_id"],)).fetchone()
                    if receipt["status"]=="settled":break
                assert receipt["status"]=="settled" and receipt["usage"]=={"input_tokens":7}
        finally:release.set()
    asyncio.run(exercise())
    assert store.get_run(run["id"])["usage"]=={"input_tokens":7}
