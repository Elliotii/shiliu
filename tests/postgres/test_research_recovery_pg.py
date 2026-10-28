"""Native PG recovery scanner and supervised active-time lifecycle."""
from shiliu.research.recovery import ResearchRecoveryCoordinator
from shiliu.research.product_contracts import CreateProductResearchRequest
from test_research_knowledge_pg import knowledge_core
from test_research_outer_pg import outer_core


def test_supervisor_ticks_real_pg_while_provider_is_outside_transaction(knowledge_core):
    import time
    core=knowledge_core
    core.research_provider_product=core.research_product
    calls=[]
    class BlockingOrchestrator:
        _run_lock=object()
        def run_to_boundary(self,task_id,**kwargs):
            # A real PG read succeeds while the external call is blocked.
            with core.db.connect(read_only=True) as conn:
                assert conn.execute("SELECT count(*) AS n FROM research_tasks WHERE workspace_id=%s",(core.db.workspace_id,)).fetchone()["n"]==1
            calls.append(task_id)
            time.sleep(.08)
            return {"boundary":"test"}
    core.research_provider_orchestrator=BlockingOrchestrator()
    core.provider_research_availability=lambda:{"available":True,"reason":"local fake"}
    created=core.research_provider_product.create_provider_task(CreateProductResearchRequest(command_id="supervised-pg",objective="synthetic blocking call",run_immediately=True))
    task_id=created["task_id"]
    coordinator=ResearchRecoveryCoordinator(core)
    coordinator.TICK_SECONDS=.01
    coordinator.LEASE_RENEW_SECONDS=.02
    coordinator.LEASE_SECONDS=1
    assert coordinator.run_once()==task_id
    snapshot=coordinator.ledger.snapshot(task_id)
    assert calls==[task_id]
    assert 50<=snapshot.consumed_active_ms<1000 and snapshot.reserved_tail_ms==0
    assert not any(e["event_type"]=="owner_renewed" for e in core.research.get_task(task_id)["events"])
    assert coordinator.run_once() is None
    coordinator.start();coordinator.stop();coordinator.stop()
    assert coordinator._thread is not None and not coordinator._thread.is_alive()


def test_recovery_takeover_marks_in_flight_unknown_without_model_replay(knowledge_core):
    core=knowledge_core
    kernel=core.research
    core.research_provider_product=core.research_product
    calls=[]
    class ForbiddenOrchestrator:
        _run_lock=object()
        def run_to_boundary(self,*args,**kwargs):calls.append(args);raise AssertionError("unknown effect cannot replay")
    core.research_provider_orchestrator=ForbiddenOrchestrator()
    core.provider_research_availability=lambda:{"available":True,"reason":"local fake"}
    task_id=core.research_provider_product.create_provider_task(CreateProductResearchRequest(command_id="recover-unknown-pg",objective="synthetic unknown",run_immediately=True))["task_id"]
    claim=kernel.claim_owner(task_id=task_id,command_id="old-owner",owner_id="old-worker",expected_state_version=0,lease_seconds=60)
    attempt=kernel.start_attempt(task_id=task_id,command_id="start-old",owner_id="old-worker",owner_epoch=claim["owner_epoch"],expected_state_version=claim["state_version"])
    reserved=kernel.reserve_side_effect(task_id=task_id,attempt_id=attempt["attempt_id"],command_id="reserve",owner_id="old-worker",owner_epoch=claim["owner_epoch"],expected_state_version=attempt["state_version"],effect_kind="fake-provider",idempotency_key="single-call",request_payload={"synthetic":True})
    kernel.transition_side_effect(task_id=task_id,side_effect_id=reserved["side_effect_id"],command_id="sent",owner_id="old-worker",owner_epoch=claim["owner_epoch"],expected_state_version=reserved["state_version"],target_status="in_flight",operation_id="synthetic-operation")
    with core.db.connect() as conn:
        kernel._task(conn,task_id)
        conn.execute("UPDATE research_tasks SET lease_until=clock_timestamp()-interval '1 second' WHERE workspace_id=%s AND owner_user_id=%s AND task_id=%s",(core.db.workspace_id,core.db.context.user_id,task_id))
    coordinator=ResearchRecoveryCoordinator(core)
    assert coordinator.run_once()==task_id
    state=kernel.get_task(task_id)
    assert state["side_effects"][0]["status"]=="unknown" and state["task"]["owner_epoch"]==claim["owner_epoch"]+1
    assert calls==[]
    assert coordinator.ledger.snapshot(task_id).scheduling_status=="manual_required"
    assert coordinator.run_once() is None
