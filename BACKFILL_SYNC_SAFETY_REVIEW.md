# Backfill / Sync Safety Review

Date: 2026-08-11 (Asia/Shanghai)

Reviewer mode: GPT-5.6 Sol, high reasoning, read-only. The reviewer confirmed
that it did not modify code, SQLite, config, LaunchAgents, Git, or live product
state. The Main Owner verified the cited paths before implementation.

## Verdict before implementation

Blocking changes are required before real-corpus onboarding. The existing
architecture is reusable, but its source snapshot API assumes completeness and
its `latest_n` behavior is a one-time queue count rather than durable coverage.

## Findings

1. **Blocking — partial scans can false-remove.**
   `Database.record_source_snapshot` in `src/shiliu/db.py` marks every unseen
   membership removed and then removes a video when it has no other active
   membership. There is no completeness/authority input. Any bounded page,
   interrupted pagination result, or future partial caller could therefore
   remove memberships and deindex videos.
2. **Blocking — incomplete initial discovery can corrupt forward semantics.**
   `initialize_source_memberships` finalizes `baseline_initialized` from the
   supplied list without an authoritative-complete assertion. Items omitted by
   an incomplete first scan would later look like new favorites and bypass the
   requested historical boundary.
3. **High — `latest_n` has no stable boundary.**
   Initial queueing uses source position only. No `favorite_time` cutoff is
   stored, there is no supported expansion/shrink operation, and an UPSERT does
   not recompute queued coverage.
4. **High — re-favorited unmaterialized items can be missed.**
   `record_source_snapshot` creates a Video only when a membership row is new.
   A removed baseline membership that reappears with no `video_id` is
   reactivated but not materialized as a forward favorite.
5. **High — source lifecycle mutations race the sync lock.**
   Pause/remove/history-policy Web operations do not take the process lock.
   Source selection happens before `SyncService` acquires the lock, and a
   successful snapshot unconditionally writes source status `active`; a stale
   scan can undo a pause.
6. **Medium — history materialization and pipeline completion are separate
   transactions.** `materialize_history_membership` clears `queued_history`
   before pipeline work. Existing durable Video/pipeline-stage retry behavior
   makes eventual recovery possible, but crash points require explicit tests.
7. **Existing safe basis — multi-folder ownership is modeled correctly.**
   Videos are deduplicated while memberships remain source-specific, and video
   removal checks for another active membership. This must be retained and
   regression-tested for both complete and partial snapshots.

## Required invariants

- Only a complete, explicitly authoritative snapshot may reconcile removals.
- An incomplete initial scan may record observations but may not finalize a
  baseline or begin historical materialization.
- `latest_n` resolves once to a stable `favorite_time` boundary; later new
  favorites are forward materialized regardless of that boundary.
- Shrinking coverage changes only future backlog eligibility. It never deletes
  a Video, membership, artifact, index, note, reading state, or knowledge state.
- Expanding coverage queues only previously unmaterialized active memberships.
- Source pause/remove/coverage changes serialize with sync, and sync rechecks
  source state after acquiring its lock.
- A crash before/after membership materialization is safe to rerun and does not
  duplicate a Video or lose durable retry work.
- Removing a membership from one complete source snapshot cannot remove a Video
  that another active source still owns.

## Minimum regression matrix

- latest 100 initial discovery resolves to stable cutoff;
- expansion 100 → 300 and 300 → all;
- shrink 300 → 100 without deletion or state loss;
- new favorite after cutoff enters forward processing;
- incomplete initial scan does not finalize baseline;
- partial/bounded scan does not remove unseen memberships;
- complete snapshot still reconciles a real removal;
- re-favorited unmaterialized baseline item is materialized;
- same Video in two folders survives removal from one;
- pause/resume serializes with sync and does not change coverage;
- crash before pipeline, restart/resume, and idempotent rerun;
- all-history mode queues all remaining active memberships.

## Minimal implementation recommendation

Keep the existing SQLite, process lock, pipeline stages, bounded history batch,
retrieval coordinator, and LaunchAgent. Add an additive source coverage cutoff
and snapshot-completeness state; require an explicit authoritative flag for
removal reconciliation; add a non-destructive coverage update method; recheck
source state under the sync lock; and expose only focused source status/coverage
controls and metrics.
