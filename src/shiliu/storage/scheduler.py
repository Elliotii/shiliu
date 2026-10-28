"""Transaction-local scoped Job/lane CAS. No model execution or generic worker."""

from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from shiliu.storage.fences import CoordinationConflict
from shiliu.storage.scope import ResourceContext

LOCAL_KINDS = ("memory_purge", "memory_index", "source_reconcile")
MODEL_KINDS = (
    "memory_extract",
    "source_extract",
    "wiki_integrate",
    "external_material_integrate",
)


def _lane(conn, context):
    conn.execute(
        "INSERT INTO shiliu.scheduler_lanes (workspace_id,principal_id,lane) VALUES (%s,%s,'model-maintenance') "
        "ON CONFLICT DO NOTHING",
        (context.workspace_id, context.user_id),
    )
    row = conn.execute(
        "SELECT * FROM shiliu.scheduler_lanes "
        "WHERE workspace_id=%s AND principal_id=%s AND lane='model-maintenance' FOR UPDATE",
        (context.workspace_id, context.user_id),
    ).fetchone()
    row["valid"] = _lease_valid(conn, row)
    return row


def _lease_valid(conn, row):
    # A LockRows target expression can be evaluated BEFORE an unchanged-row wait.
    # Only a new statement after ownership locks uses the actual decision time.
    return conn.execute(
        "SELECT %s::timestamptz > clock_timestamp() AS valid", (row["lease_until"],)
    ).fetchone()["valid"]


def _candidate(conn, context, kinds):
    return conn.execute(
        "SELECT j.* FROM shiliu.assistant_jobs j WHERE j.workspace_id=%s AND j.principal_id=%s "
        "AND j.kind=ANY(%s) AND j.status IN ('queued','retry_wait','budget_wait') AND j.not_before<=clock_timestamp() "
        "AND NOT EXISTS (SELECT 1 FROM shiliu.metadata_backfill_job_holds h WHERE h.workspace_id=j.workspace_id AND h.job_id=j.id) "
        "ORDER BY CASE j.kind WHEN 'memory_purge' THEN 0 WHEN 'memory_index' THEN 1 ELSE 2 END,j.created_at,j.id "
        "FOR UPDATE OF j SKIP LOCKED LIMIT 1",
        (context.workspace_id, context.user_id, list(kinds)),
    ).fetchone()


def claim_job(
    conn: Connection,
    context: ResourceContext,
    owner: str,
    *,
    lease_seconds: float = 120,
    allow_model_jobs: bool = True,
    allow_maintenance: bool = True,
    activity_allowed: bool = True,
    budget_allowed: bool = True,
    kinds: tuple | None = None,
):
    """Local index/purge first, then guard lane before selecting model Jobs.

    Activity/budget admission booleans are supplied by the trusted scheduler;
    dispatch still requires atomic reserve_dispatch. No NOT EXISTS lane race.
    Expired running Jobs are classified explicitly with recover_job, not blindly
    requeued or reexecuted. Proposal, attempt and not_before remain intact.
    """
    if not owner or not 0 < lease_seconds <= 120:
        raise ValueError("invalid_job_lease")
    local_kinds = tuple(k for k in LOCAL_KINDS if kinds is None or k in kinds)
    row = _candidate(conn, context, local_kinds)
    model = False
    if (
        row is None
        and allow_maintenance
        and allow_model_jobs
        and activity_allowed
        and budget_allowed
    ):
        lane = _lane(conn, context)
        if lane["active_job_id"] and lane["valid"]:
            return None
        # Reclaim only lane ownership. An expired Job still needs explicit
        # recovery classification before it can become a runnable candidate.
        row = _candidate(
            conn, context, tuple(k for k in MODEL_KINDS if kinds is None or k in kinds)
        )
        model = row is not None
    if row is None:
        return None
    return _assign_job(conn,context,owner,row,model=model,lease_seconds=lease_seconds)


def _assign_job(conn,context,owner,row,*,model,lease_seconds):
    job = conn.execute(
        "UPDATE shiliu.assistant_jobs SET status='running',lease_owner=%s,lease_epoch=lease_epoch+1,"
        "attempt=attempt+1,lease_until=clock_timestamp()+%s*interval '1 second',updated_at=clock_timestamp() "
        "WHERE id=%s AND lease_epoch=%s RETURNING *",
        (owner, lease_seconds, row["id"], row["lease_epoch"]),
    ).fetchone()
    if model:
        conn.execute(
            "UPDATE shiliu.scheduler_lanes SET active_job_id=%s,lease_epoch=%s,lease_until=%s "
            "WHERE workspace_id=%s AND principal_id=%s AND lane='model-maintenance'",
            (
                job["id"],
                job["lease_epoch"],
                job["lease_until"],
                context.workspace_id,
                context.user_id,
            ),
        )
    conn.execute(
        "INSERT INTO shiliu.assistant_scheduler_events (workspace_id,principal_id,job_id,event_type,created_at) "
        "VALUES (%s,%s,%s,'claimed',clock_timestamp())",
        (context.workspace_id, context.user_id, job["id"]),
    )
    return job



def claim_backfill_job(conn,context,owner,*,job_id,run_id,lease_seconds=120):
    """Claim one held deterministic backfill intent through the shared lane.

    A payload key alone never bypasses the normal hold exclusion. The caller
    must match the durable hold, run, operation and this principal's exact Job.
    """
    if not owner or not 0<lease_seconds<=120:
        raise ValueError("invalid_job_lease")
    kind=conn.execute("SELECT kind FROM shiliu.assistant_jobs WHERE workspace_id=%s AND principal_id=%s AND id=%s",(context.workspace_id,context.user_id,job_id)).fetchone()
    if kind is None:return None
    model=kind["kind"] not in LOCAL_KINDS
    if model:
        lane=_lane(conn,context)
        if lane["active_job_id"] and lane["valid"]:return None
    row=conn.execute("SELECT j.* FROM shiliu.assistant_jobs j JOIN shiliu.metadata_backfill_job_holds h ON (h.workspace_id,h.job_id)=(j.workspace_id,j.id) JOIN shiliu.metadata_backfill_operations o ON (o.workspace_id,o.run_id,o.video_id)=(h.workspace_id,h.run_id,h.video_id) WHERE j.workspace_id=%s AND j.principal_id=%s AND j.id=%s AND h.run_id=%s AND o.state IN ('applied','rollback_pending') AND j.kind IN ('source_reconcile','wiki_integrate') AND j.status IN ('queued','retry_wait','budget_wait') AND j.not_before<=clock_timestamp() FOR UPDATE OF j",(context.workspace_id,context.user_id,job_id,run_id)).fetchone()
    if row is None:return None
    return _assign_job(conn,context,owner,row,model=model,lease_seconds=lease_seconds)


def guard_job(
    conn: Connection, context: ResourceContext, job_id: str, owner: str, epoch: int
):
    """Lock lane (if applicable), then Job; validate without changing progress."""
    kind = conn.execute(
        "SELECT kind FROM shiliu.assistant_jobs WHERE workspace_id=%s AND principal_id=%s AND id=%s",
        (context.workspace_id, context.user_id, job_id),
    ).fetchone()
    if kind is None:
        raise CoordinationConflict("job_missing")
    lane = _lane(conn, context) if kind["kind"] not in LOCAL_KINDS else None
    job = conn.execute(
        "SELECT * FROM shiliu.assistant_jobs "
        "WHERE workspace_id=%s AND principal_id=%s AND id=%s FOR UPDATE",
        (context.workspace_id, context.user_id, job_id),
    ).fetchone()
    if (
        job["status"] != "running"
        or job["lease_owner"] != owner
        or job["lease_epoch"] != epoch
        or not _lease_valid(conn, job)
    ):
        raise CoordinationConflict("job_fenced")
    if lane and (
        lane["active_job_id"] != job_id
        or lane["lease_epoch"] != epoch
        or not _lease_valid(conn, lane)
    ):
        raise CoordinationConflict("lane_fenced")
    return job, lane


def job_transition(
    conn: Connection,
    context: ResourceContext,
    job_id: str,
    owner: str,
    epoch: int,
    *,
    action: str,
    lease_seconds: float = 120,
    proposal: dict | None = None,
):
    """CAS heartbeat/stage/complete/fail/defer, lane -> Job lock order."""
    if action not in {"heartbeat", "stage", "complete", "fail", "defer"}:
        raise ValueError("invalid_job_action")
    if not 0 < lease_seconds <= 120:
        raise ValueError("invalid_job_lease")
    if action == "stage" and proposal is None:
        raise ValueError("proposal_required")
    job, lane = guard_job(conn, context, job_id, owner, epoch)
    if action == "heartbeat":
        until = conn.execute(
            "UPDATE shiliu.assistant_jobs SET lease_until=clock_timestamp()+%s*interval '1 second',"
            "updated_at=clock_timestamp() WHERE id=%s RETURNING lease_until",
            (lease_seconds, job_id),
        ).fetchone()["lease_until"]
        if lane:
            conn.execute(
                "UPDATE shiliu.scheduler_lanes SET lease_until=%s WHERE workspace_id=%s "
                "AND principal_id=%s AND lane='model-maintenance' AND active_job_id=%s AND lease_epoch=%s",
                (until, context.workspace_id, context.user_id, job_id, epoch),
            )
    elif action == "stage":
        conn.execute(
            "UPDATE shiliu.assistant_jobs SET proposal_json=%s,updated_at=clock_timestamp() WHERE id=%s",
            (Jsonb(proposal), job_id),
        )
    else:
        status = (
            ("blocked" if job["attempt"] >= 3 else "retry_wait")
            if action == "fail"
            else ("completed" if action == "complete" else "queued")
        )
        delay = (10, 60, 300)[min(max(job["attempt"] - 1, 0), 2)]
        conn.execute(
            "UPDATE shiliu.assistant_jobs SET status=%s,lease_owner=NULL,lease_until=NULL,"
            "attempt=CASE WHEN %s THEN greatest(0,attempt-1) ELSE attempt END,"
            "not_before=CASE WHEN %s THEN clock_timestamp()+%s*interval '1 second' ELSE not_before END,"
            "updated_at=clock_timestamp(),completed_at=CASE WHEN %s THEN clock_timestamp() ELSE completed_at END "
            "WHERE id=%s",
            (
                status,
                action == "defer",
                action == "fail",
                delay,
                action == "complete",
                job_id,
            ),
        )
        if lane:
            conn.execute(
                "UPDATE shiliu.scheduler_lanes SET active_job_id=NULL,lease_until=NULL "
                "WHERE workspace_id=%s AND principal_id=%s AND lane='model-maintenance' AND active_job_id=%s AND lease_epoch=%s",
                (context.workspace_id, context.user_id, job_id, epoch),
            )


def recover_job(
    conn: Connection, context: ResourceContext, job_id: str, *, disposition: str
):
    """Trusted recovery classification: staged/replay_safe/unknown/exhausted.

    Classifier must establish replay safety; unknown stays blocked. Never clears
    a proposal or resets attempts/epoch. W10 supplies domain recovery policies.
    """
    if disposition not in {"staged", "replay_safe", "unknown", "exhausted"}:
        raise ValueError("invalid_recovery_class")
    _lane(conn, context)
    job = conn.execute(
        "SELECT * FROM shiliu.assistant_jobs "
        "WHERE workspace_id=%s AND principal_id=%s AND id=%s FOR UPDATE",
        (context.workspace_id, context.user_id, job_id),
    ).fetchone()
    if job is None or job["status"] != "running" or _lease_valid(conn, job):
        return False
    if disposition == "staged" and job["proposal_json"] is None:
        raise CoordinationConflict("proposal_missing")
    status = (
        "blocked"
        if job["attempt"] >= 3
        else {
            "staged": "retry_wait",
            "replay_safe": "retry_wait",
            "unknown": "blocked",
            "exhausted": "blocked",
        }[disposition]
    )
    conn.execute(
        "UPDATE shiliu.assistant_jobs SET status=%s,lease_owner=NULL,lease_until=NULL,"
        "updated_at=clock_timestamp() WHERE id=%s",
        (status, job_id),
    )
    conn.execute(
        "UPDATE shiliu.scheduler_lanes SET active_job_id=NULL,lease_until=NULL WHERE workspace_id=%s "
        "AND principal_id=%s AND lane='model-maintenance' AND active_job_id=%s AND lease_epoch=%s",
        (context.workspace_id, context.user_id, job_id, job["lease_epoch"]),
    )
    return True
