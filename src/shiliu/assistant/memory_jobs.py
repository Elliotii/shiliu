"""Memory index/purge worker on assistant_jobs; no second queue or model lane."""

from shiliu.assistant.lease_renewal import job_renewal, renewal_period

from shiliu.assistant.runtime_contract import AssistantConflict
from shiliu.storage.scheduler import claim_job, guard_job, job_transition, recover_job
from shiliu.storage.fences import CoordinationConflict


class MemoryJobWorker:
    def __init__(self, memories, *, owner, lease_seconds=120, heartbeat_interval=None):
        self.memories = memories
        self.db = memories.db
        self.owner = owner
        self.lease_seconds = lease_seconds
        self.heartbeat_interval = renewal_period(lease_seconds, heartbeat_interval)

    def recover(self):
        count = 0
        with self.db.connect() as c:
            ids = c.execute(
                "SELECT id FROM assistant_jobs WHERE workspace_id=%s AND principal_id=%s AND kind=ANY(%s) AND status='running' ORDER BY id",
                (
                    self.db.workspace_id,
                    self.db.context.user_id,
                    ["memory_index", "memory_purge"],
                ),
            ).fetchall()
        for row in ids:
            with self.db.connect() as c:
                count += int(
                    recover_job(
                        c, self.db.context, row["id"], disposition="replay_safe"
                    )
                )
        return count

    def run_once(self):
        with self.db.connect() as c:
            job = claim_job(
                c,
                self.db.context,
                self.owner,
                lease_seconds=self.lease_seconds,
                allow_model_jobs=False,
                kinds=("memory_purge", "memory_index"),
            )
        if job is None:
            return None
        with job_renewal(
            self.db,
            job,
            lease_seconds=self.lease_seconds,
            interval=self.heartbeat_interval,
        ):
            return self._run_claim(job)

    def _run_claim(self, job):
        payload = job["payload_json"]
        try:
            method = (
                self.memories.project
                if job["kind"] == "memory_index"
                else self.memories.purge
            )
            result = method(
                memory_id=payload["memory_id"], version=int(payload["version"]), job=job
            )
            if result["status"] == "stale":
                # Complete only this exact old intent; a newer version has its
                # own dedupe key and cannot be swallowed by old computation.
                with self.db.connect() as c:
                    current, _ = guard_job(
                        c, self.db.context, job["id"], self.owner, job["lease_epoch"]
                    )
                    if current["payload_json"] != payload:
                        raise CoordinationConflict("job_fenced")
                    job_transition(
                        c,
                        self.db.context,
                        job["id"],
                        self.owner,
                        job["lease_epoch"],
                        action="complete",
                    )
            return result
        except CoordinationConflict:
            return {"status": "stale", "reason": "job_fenced"}
        except Exception as exc:
            try:
                with self.db.connect() as c:
                    current, _ = guard_job(
                        c, self.db.context, job["id"], self.owner, job["lease_epoch"]
                    )
                    if current["payload_json"] != payload:
                        raise CoordinationConflict("job_fenced")
                    if isinstance(exc, AssistantConflict) and str(exc).endswith(
                        "_stale"
                    ):
                        job_transition(
                            c,
                            self.db.context,
                            job["id"],
                            self.owner,
                            job["lease_epoch"],
                            action="complete",
                        )
                    else:
                        job_transition(
                            c,
                            self.db.context,
                            job["id"],
                            self.owner,
                            job["lease_epoch"],
                            action="fail",
                        )
                        c.execute(
                            "UPDATE assistant_jobs SET last_error_code=%s,last_error_message=%s WHERE id=%s",
                            (
                                type(exc).__name__,
                                "Memory projection failed; retry policy retained",
                                job["id"],
                            ),
                        )
            except CoordinationConflict:
                return {"status": "stale", "reason": "job_fenced"}
            return {
                "status": "stale"
                if isinstance(exc, AssistantConflict)
                else "retry_wait",
                "error_code": type(exc).__name__,
            }
