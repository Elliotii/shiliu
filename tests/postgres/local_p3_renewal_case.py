# ruff: noqa: F811
"""Explicit slow acceptance: unchanged default120 lease, actual121-second local model."""

import json
import time
from pathlib import Path
from threading import Event
from concurrent.futures import ThreadPoolExecutor
from test_memory import memory_parts  # noqa: F401
from test_memory_extraction import prepare
from shiliu.assistant.memory_extraction import MemoryExtractionWorker


def test_default_extraction_lease_is_renewed_while_model_is_running(memory_parts):
    db, m, job_id, proposal = prepare(memory_parts)
    started = Event()

    class SlowSyntheticProvider:
        calls = 0

        def extract_memories(self, *, prompt):
            self.calls += 1
            started.set()
            # Real elapsed time, no forced expiry or altered production lease.
            end = time.monotonic() + 121
            while time.monotonic() < end:
                Event().wait(min(1, end - time.monotonic()))
            return [proposal]

    provider = SlowSyntheticProvider()
    worker = MemoryExtractionWorker(
        m, owner="supervisor-slow-default", provider_factory=lambda: provider
    )
    checks = []
    output = Path("/tmp/shiliu-w01-20261023/p3-repair-default-renewal.json")
    with ThreadPoolExecutor(1) as ex:
        future = ex.submit(worker.run_once)
        assert started.wait(5)
        start = time.monotonic()
        last_sample = -20
        while not future.done():
            elapsed = time.monotonic() - start
            if elapsed - last_sample >= 10:
                with db.connect(read_only=True) as c:
                    row = c.execute(
                        "SELECT status,lease_owner,lease_epoch,lease_until,lease_until>clock_timestamp() AS live,clock_timestamp() AS db_now FROM assistant_jobs WHERE id=%s",
                        (job_id,),
                    ).fetchone()
                checks.append(dict(elapsed=round(elapsed, 2), **row))
                output.write_text(
                    json.dumps(
                        dict(
                            scope="default 120-second lease; fake model waits real 121 seconds; no forced expiry, no external calls",
                            samples=checks,
                        ),
                        default=str,
                        indent=2,
                    )
                    + "\n"
                )
                last_sample = elapsed
            Event().wait(0.5)
        result = future.result(3)
    with db.connect(read_only=True) as c:
        row = c.execute(
            "SELECT status,lease_epoch,lease_until,proposal_json FROM assistant_jobs WHERE id=%s",
            (job_id,),
        ).fetchone()
        dispatch = c.execute(
            "SELECT status FROM model_dispatch_receipts WHERE job_id=%s", (job_id,)
        ).fetchall()
    output.write_text(
        json.dumps(
            dict(
                scope="default 120-second lease, unmodified claim; fake model real 121-second wait; no external calls",
                samples=checks,
                result=result,
                job_after=row,
                dispatch_after=dispatch,
                model_calls=provider.calls,
                memories=m.list(),
            ),
            ensure_ascii=False,
            default=str,
            indent=2,
        )
        + "\n"
    )
    assert result.get("reason") == "applied", (
        "No renewal during a normal slow model call: lease expires, response cannot be staged or applied"
    )
