"""The retained W12 risk: validate lease after waiting for a row lock."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import time

import pytest

from shiliu.storage.fences import guard_task_owner,claim_task_root,CoordinationConflict


@pytest.mark.parametrize("operation",["guard","claim"])
def test_research_lease_is_rechecked_after_lock_wait(collection_db,operation):
    from seed_rows import SyntheticGraph
    db=collection_db;ready=Event();worker_pid=[]
    with db.connect() as conn:
        graph=SyntheticGraph(conn)
        task=graph.ensure("research_tasks")
        graph.ensure("research_attempts")
        conn.execute("UPDATE shiliu.research_tasks SET status='running',owner_id='ownerA',owner_epoch=1,"
                     "lease_until=clock_timestamp()+interval '0.5 seconds' WHERE task_id=%s",(task["task_id"],))
        assert guard_task_owner(conn,db.context,task["task_id"],"ownerA",1)["owner_id"]=="ownerA"
        assert claim_task_root(conn,db.context,task["task_id"],"ownerB") is None
    def authorize():
        with db.connect() as conn:
            worker_pid.append(conn.info.backend_pid);ready.set()
            try:
                if operation=="guard":return guard_task_owner(conn,db.context,task["task_id"],"ownerA",1)
                return claim_task_root(conn,db.context,task["task_id"],"ownerB")
            except CoordinationConflict:return "fenced"
    with ThreadPoolExecutor(max_workers=1) as executor:
        with db.connect() as blocker:
            blocker.execute("SELECT task_id FROM shiliu.research_tasks WHERE task_id=%s FOR UPDATE",(task["task_id"],))
            future=executor.submit(authorize)
            assert ready.wait(1)
            deadline=time.monotonic()+2
            with db.connect(read_only=True) as observer:
                while True:
                    waiting=observer.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s",(worker_pid[0],)).fetchone()
                    if waiting and waiting["wait_event_type"]=="Lock":break
                    assert time.monotonic()<deadline,"worker did not actually wait on the lock"
                    time.sleep(.01)
                while not observer.execute("SELECT lease_until<=clock_timestamp() AS expired FROM shiliu.research_tasks WHERE task_id=%s",
                                           (task["task_id"],)).fetchone()["expired"]:
                    assert time.monotonic()<deadline,"database lease did not expire"
                    time.sleep(.01)
            assert not future.done()
            # Blocker deliberately performs no UPDATE before releasing the lock.
        result=future.result(timeout=3)
    if operation=="guard":assert result=="fenced"
    else:assert result is not None and result["owner_id"]=="ownerB" and result["owner_epoch"]==2
