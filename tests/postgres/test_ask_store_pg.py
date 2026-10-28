"""Ask lifecycle contracts on the formal scoped PostgreSQL store."""
from datetime import datetime, timezone

import pytest

from shiliu.ask.persistence import AskRunStore, PgAskRunStore
from shiliu.db import Database
from shiliu.storage.scope import ResourceContext


def complete(store, run_id, **overrides):
    values=dict(run_id=run_id,trace={"intro":"intro","outro":"outro"},answer_status="complete",
        termination_reason="answered",query_analysis={},rewrites=[],search_executions=[],
        final_evidence=[],citations=[{"citation_id":"legacy-citation"}],answer_blocks=[],limitations=[],usage_summary={})
    values.update(overrides)
    return store.complete(**values)


def test_formal_ask_entry_roundtrips_history_and_atomic_terminal_event(collection_db):
    store=AskRunStore(collection_db)
    assert isinstance(store,PgAskRunStore)
    created=store.start(run_id="ask-pg",query="synthetic",mode="deep",filters={"nested":{"null":None}})
    event=store.append_event("ask-pg","run_started",{"synthetic":True})
    completed=complete(store,"ask-pg",events=[{"event_type":"run_completed","result":"done"}])
    record=store.get_run("ask-pg")
    assert record["created_at"]==created and record["completed_at"]==completed
    assert record["filters"]=={"nested":{"null":None}}
    assert record["citations"]==[{"citation_id":"legacy-citation"}]
    assert [v["sequence"] for v in record["events"]]==[1,2]
    assert store.get_events("ask-pg",after_sequence=1)[0]["event_type"]=="run_completed"
    assert store.get_trace("ask-pg")["intro"]=="intro"
    assert not store.interrupt_owner_loss("ask-pg",reason="late owner loss")
    assert event["source_id"]=="ask-pg"


def test_ask_terminal_update_rolls_back_with_events(collection_db,monkeypatch):
    from shiliu.ask import persistence
    store=AskRunStore(collection_db)
    store.start(run_id="rollback",query="synthetic",mode="fast",filters={})
    def broken(**kwargs):raise RuntimeError("injected event failure")
    monkeypatch.setattr(persistence,"_lifecycle_envelope",broken)
    with pytest.raises(RuntimeError,match="injected event failure"):
        complete(store,"rollback",events=[{"event_type":"run_completed"}])
    assert store.get_run("rollback")["lifecycle_status"]=="running"
    assert store.get_events("rollback")==[]


def test_ask_owner_loss_abort_and_second_owner_scope(collection_db):
    store=AskRunStore(collection_db)
    now=datetime.now(timezone.utc)
    with collection_db.connect() as conn:
        conn.execute("INSERT INTO shiliu.users(id,display_name,created_at) VALUES('ask-owner','Synthetic',%s)",(now,))
        conn.execute("INSERT INTO shiliu.workspaces(id,kind,owner_user_id,created_at) VALUES('personal:ask-owner','personal','ask-owner',%s)",(now,))
        conn.execute("INSERT INTO shiliu.workspace_guards(workspace_id) VALUES('personal:ask-owner')")
    other=AskRunStore(Database(collection_db.pg,ResourceContext("personal:ask-owner","ask-owner")))
    store.start(run_id="first",query="first private",mode="fast",filters={})
    other.start(run_id="other",query="other private",mode="deep",filters={})
    assert other.get_run("other")["query"]=="other private"
    assert other.get_run("first") is None and store.get_run("other") is None
    with pytest.raises(KeyError):other.append_event("first","forbidden")
    with pytest.raises(KeyError):other.start(run_id="bad-parent",query="x",mode="deep",filters={},parent_run_id="first")
    aborted=other.request_abort("other",command_id="abort-1")
    assert aborted["terminal"]["event_type"]=="run_interrupted"
    assert other.get_run("other")["termination_reason"]=="interrupted"
    assert store.interrupt_running_on_startup()==1
    assert store.interrupt_running_on_startup()==0
    assert store.get_run("first")["error"]["error_type"]=="AskOwnerLoss"


def test_candidate_disclosure_reads_pg_trace_presentation_and_lineage(collection_db):
    from seed_rows import SyntheticGraph
    from psycopg.types.json import Jsonb
    from shiliu.ask.candidates import AskCandidateProjector
    store=AskRunStore(collection_db)
    with collection_db.connect() as conn:
        graph=SyntheticGraph(conn)
        video=graph.ensure("videos")
        presentation=graph.ensure("retrieval_search_presentations")
        conn.execute("UPDATE shiliu.retrieval_search_presentations SET status='success',group_summary_json=%s WHERE workspace_id=%s AND trace_id=%s",
            (Jsonb([{"video_id":video["id"],"best_rank":1}]),collection_db.workspace_id,presentation["trace_id"]))
    store.start(run_id="candidates",query="synthetic",mode="fast",filters={})
    complete(store,"candidates",search_executions=[{"search_trace_id":presentation["trace_id"],"query":"synthetic","trace_persisted":True}])
    projector=AskCandidateProjector(collection_db,store)
    links,total=projector._lineage("candidates")
    assert total==1 and links[0]["trace_persisted"] is True
    assert projector._presentation_groups(presentation["trace_id"])[0]["video_id"]==video["id"]
    assert projector._video_metadata([{"video_id":video["id"]}])[video["id"]]["title"]==video["title"]


def test_fast_ndjson_pg_result_and_deep_202_owner_loss(retrieval,app_paths,monkeypatch):
    import json
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from shiliu.ask.service import AskService
    from shiliu.web import create_web_app
    from test_collection_retrieval import add_video,product_composition
    from test_v4_fast_ask_api import _Provider,_CompatibilityClaimVerifier
    db,artifacts,lexical,dense=retrieval
    add_video(retrieval,text="MCP 通过协议连接模型与外部工具。")
    dense.rebuild()
    _,product,evidence=product_composition(retrieval)
    provider=_Provider()
    ask=AskService(db=db,artifacts=artifacts,product_search=product,evidence_search=evidence,
        provider_factory=lambda role:provider,deep_embedding_provider=dense.provider,fast_f1=True,
        claim_verifier=_CompatibilityClaimVerifier())
    core=SimpleNamespace(config=SimpleNamespace(assistant_enabled=False),db=db,paths=app_paths,ask_service=ask,
        start=lambda **kwargs:ask.run_store.interrupt_running_on_startup(),close=ask.shutdown)
    with TestClient(create_web_app(core,background_tasks=False)) as client:
        response=client.post("/api/ask/stream",json={"query":"解释 MCP","mode":"fast"})
        assert response.status_code==200,response.text
        assert response.headers["content-type"].startswith("application/x-ndjson")
        events=[json.loads(line) for line in response.text.splitlines() if line]
        run_id=response.headers["x-shiliu-run-id"]
        record=ask.run_store.get_run(run_id)
        assert record["lifecycle_status"]=="completed",record
        assert record["citations"]
        assert events and [e["sequence"] for e in events]==sorted({e["sequence"] for e in events})
        assert client.get(f"/api/ask/runs/{run_id}").json()["run"]["lifecycle_status"]=="completed"
        from shiliu.ask.deep.v2 import V2Decision,QueryReduction
        from test_deep_v2 import Provider as ReduceProvider
        answer_provider=provider
        reducer=ReduceProvider([])
        class DeepProvider:
            model="synthetic"
            def generate_structured(self,**kwargs):
                if kwargs["response_schema"] is QueryReduction:return reducer.generate_structured(**kwargs)
                if kwargs["response_schema"] is V2Decision:
                    payload=json.loads(kwargs["messages"][-1]["content"])
                    if not payload["query_results"]:
                        decision={"type":"continue","actions":[{"action_id":"search-mcp","kind":"search_transcripts",
                            "arguments":{"query":"MCP"},"purpose":"read synthetic evidence"}]}
                    else:
                        refs=[ref for result in payload["query_results"] for ref in result.get("retained_evidence_refs",[])]
                        decision={"type":"finish","outcome":"sufficient","answer_evidence_refs":refs,"finish_reason":"synthetic evidence read"}
                    return SimpleNamespace(output=V2Decision.model_validate(decision),usage={"input_tokens":3},latency_ms=1)
                return answer_provider.generate_structured(**kwargs)
        provider=DeepProvider()
        response=client.post("/api/ask/runs",json={"query":"解释 MCP","mode":"deep"})
        assert response.status_code==202,response.text
        deep=ask.run_store.get_run(response.json()["run_id"])
        assert deep["lifecycle_status"]=="completed",deep
        assert deep["search_executions"] and deep["citations"]
        assert reducer.calls
        # Simulate loss of an in-process dispatch owner before graph execution.
        def owner_lost(request,*,run_id,created_at):
            with ask._owned_runs_lock:ask._owned_runs.discard(run_id)
        monkeypatch.setattr(ask,"execute_started",owner_lost)
        response=client.post("/api/ask/runs",json={"query":"synthetic deep owner loss","mode":"deep"})
        assert response.status_code==202,response.text
        payload=response.json()
        assert payload["execution_semantics"]=="best_effort_in_process_dispatch" and payload["durable_worker_claimed"] is False
        read=client.get(payload["events_href"]).json()
        assert read["run"]["termination_reason"]=="interrupted"
        assert read["run"]["error"]["error_type"]=="AskOwnerLoss"
