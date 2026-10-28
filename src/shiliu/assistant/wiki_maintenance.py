"""P3-only source/Wiki maintenance consumer; Assistant execution stays W10."""

from shiliu.assistant.lease_renewal import job_renewal, renewal_period


class WikiMaintenanceWorker:
    """Only P3 source/wiki maintenance; Assistant run/extraction loop is W10."""

    def __init__(
        self, wiki, *, owner, provider, lease_seconds=120, heartbeat_interval=None
    ):
        self.wiki = wiki
        self.db = wiki.db
        self.owner = owner
        self.lease_seconds = lease_seconds
        self.heartbeat_interval = renewal_period(lease_seconds, heartbeat_interval)
        self.provider = provider

    def run_once(self):
        job = self.wiki.store.claim_job(
            owner=self.owner,
            lease_seconds=self.lease_seconds,
            kinds=("source_reconcile", "source_extract", "wiki_integrate"),
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
        from shiliu.storage.scheduler import guard_job, job_transition
        from shiliu.storage.fences import CoordinationConflict
        from shiliu.assistant.runtime_contract import ModelBudgetWait
        from shiliu.assistant.wiki import MaintenanceYield, MaintenanceBudgetExceeded

        try:
            if job["kind"] == "source_reconcile":
                result = self.wiki.reconcile(job)
            elif job["kind"] == "source_extract":
                result = self.wiki.extract_source_card(job, provider=self.provider)
            else:
                result = self.wiki.integrate_source_card(job, provider=self.provider)
            completed = result.pop("_job_completed", False) is True
            with self.db.connect() as c:
                row = c.execute(
                    "SELECT status FROM assistant_jobs WHERE workspace_id=%s AND id=%s",
                    (self.db.workspace_id, job["id"]),
                ).fetchone()
                if not completed and row["status"] != "completed":
                    self.wiki.store.finish_job(
                        job["id"],
                        owner=self.owner,
                        lease_epoch=job["lease_epoch"],
                        proposal=result,
                        conn=c,
                    )
            return {"kind": job["kind"], "status": "completed", "result": result}
        except CoordinationConflict:
            return {"kind": job["kind"], "status": "stale"}
        except (MaintenanceYield, ModelBudgetWait, MaintenanceBudgetExceeded) as exc:
            reason = (
                "activity"
                if isinstance(exc, MaintenanceYield)
                else "daily_budget"
                if isinstance(exc, ModelBudgetWait)
                else "batch_budget"
            )
            try:
                self.wiki.store.defer_maintenance_job(job, reason=reason)
            except CoordinationConflict:
                return {"kind": job["kind"], "status": "stale"}
            return {
                "kind": job["kind"],
                "status": "queued" if reason == "activity" else "budget_wait",
            }
        except Exception as exc:
            from shiliu.assistant.wiki import ModelOutcomeUnknown

            try:
                with self.db.connect() as c:
                    guard_job(
                        c, self.db.context, job["id"], self.owner, job["lease_epoch"]
                    )
                    job_transition(
                        c,
                        self.db.context,
                        job["id"],
                        self.owner,
                        job["lease_epoch"],
                        action="fail",
                    )
                    if isinstance(exc, ModelOutcomeUnknown):
                        c.execute(
                            "UPDATE assistant_jobs SET status='blocked' WHERE id=%s",
                            (job["id"],),
                        )
                    c.execute(
                        "UPDATE assistant_jobs SET last_error_code=%s,last_error_message=%s WHERE id=%s",
                        (
                            type(exc).__name__,
                            "Wiki maintenance failed; staged proposal and dispatch receipt retained",
                            job["id"],
                        ),
                    )
                    self.wiki.store.notify_job_issue(c, job["id"])
            except CoordinationConflict:
                return {"kind": job["kind"], "status": "stale"}
            return {
                "kind": job["kind"],
                "status": "blocked"
                if isinstance(exc, ModelOutcomeUnknown)
                else "retry_wait",
                "error_code": type(exc).__name__,
                "message": str(exc)[:160],
            }
