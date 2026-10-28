"""Import dispositions are audit categories, never automatic worker actions."""

from collections import Counter

TERMINAL = {"completed", "failed", "cancelled", "terminal", "succeeded", "done"}
FORGOTTEN_PURGE_COMPLETION = "complete_forgotten_purge_pg_cleanup_v1"


def forgotten_purge_complete(job, memory, principal_id):
    """Only the same owner's already-cleared forgotten fact needs no projection.

    Import clears its online lexical fields and imports no legacy Memory vectors.
    Terminal Jobs and active indexing intents retain their existing semantics.
    """
    return (
        job["kind"] == "memory_purge"
        and job["status"] not in TERMINAL
        and principal_id == memory["principal_id"]
        and memory["status"] == "forgotten"
        and memory["text"] == ""
        and memory["source_excerpt"] == ""
    )


def disposition(table, row):
    state = row.get("status", row.get("lifecycle_status"))
    if table == "ask_runs":
        return (
            "controlled_owner_loss_no_graph_replay"
            if state == "running"
            else "preserve_terminal_history"
        )
    if table == "assistant_runs":
        return (
            "preserve_context_epoch_controlled_recovery"
            if state in {"queued", "running"}
            else "preserve_terminal_history"
        )
    if table == "assistant_jobs":
        if state in TERMINAL:
            return "preserve_terminal_job"
        if row["kind"] in {"memory_index", "memory_purge"}:
            return "block_legacy_payload_pg_projection_only"
        if state == "running":
            return (
                "preserve_running_with_proposal_recovery_required"
                if row.get("proposal_json") not in (None, "", "{}", "null")
                else "preserve_running_side_effect_classification_required"
            )
        return "preserve_attempt_proposal_not_before_hold"
    if table == "research_tasks":
        return (
            "preserve_terminal_knowledge_history"
            if state == "terminal"
            else "preserve_owner_lease_epoch_controlled_recovery_only"
        )
    if table == "research_side_effects":
        return (
            "unknown_manual_resolution_no_replay"
            if state == "unknown"
            else "preserve_effect_ledger_no_replay"
        )
    if table == "asr_jobs":
        if state in TERMINAL:
            return "preserve_asr_terminal_and_upstream_identity"
        if state == "needs_review":
            return "preserve_needs_review_no_automatic_resubmit"
        return (
            "upstream_poll_only_no_submit"
            if row.get("task_id")
            else "uncertain_no_automatic_submit"
        )
    if table == "assistant_model_budget_days":
        return "preserve_business_day_lane_aggregate_no_invented_dispatch"
    return None


def summarize(raw, identity):
    result = {}
    for table in (
        "ask_runs",
        "assistant_runs",
        "assistant_jobs",
        "research_tasks",
        "research_side_effects",
        "asr_jobs",
        "assistant_model_budget_days",
    ):
        counts = Counter()
        for row in raw.get(table, []):
            category = disposition(table, row)
            if (
                table == "assistant_jobs"
                and row["kind"] == "memory_purge"
                and row["status"] not in TERMINAL
            ):
                # The changed completion policy enters the input binding only
                # for affected sources. Unaffected historical manifests stay exact.
                from shiliu.migration.values import strict_json
                from shiliu.migration.ownership import owner_for

                payload = strict_json(row["payload_json"])
                memories = raw["assistant_memories"]
                memory = memories.only("id", payload.get("memory_id"))
                owner, _ = owner_for(identity, row)
                if forgotten_purge_complete(row, memory, owner):
                    category = FORGOTTEN_PURGE_COMPLETION
            counts[category] += 1
        if counts:
            result[table] = dict(sorted(counts.items()))
    return result
