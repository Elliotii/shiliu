# Post-V5 Real Corpus Onboarding Report

Date: 2026-08-12 (Asia/Shanghai)

## Baseline and integration

- Protected V5 baseline: `codex/v5-main` at `3cd5c8c` (unchanged).
- Product branch: `codex/post-v5-product-closeout`.
- Integrated live cutover HEAD: `1707ab1db206d7a262952126bed4a51404095e80`.
- Ask persistence lineage: authoritative `fea6553b06e64162c3056210a9e3a7da2a63981f`
  is an ancestor of the integrated merge.
- Integration branch: `codex/post-v5-persistence-integration` (pushed).
- The private favorite URL, folder identity, credentials and corpus payloads are omitted.

## Default source and historical backfill

| Metric | Verified live value |
|---|---:|
| Remote-reported total | 2099 |
| API-visible/discovered memberships | 2054 |
| Imported/materialized | 2054 |
| Active memberships | 2054 |
| Historical queue | 0 |
| Not backfilled | 0 |
| Removed memberships | 0 |
| Oldest covered favorite time | 2020-07-04 11:18:44 CST |

The 45-item difference between the remote-reported total and complete API pagination is
`remote-unavailable/unresolved`: the authoritative scan reached the end, returned no
invalid or duplicate BVIDs, and supplied no identities that would allow a more specific
classification. It is not guessed to mean deleted, private or inaccessible.

Latest 100 and Latest 300 were expanded through stable favorite-time boundaries without
deletion. Their transient phase snapshots were not retained as separate corpus databases.
The authoritative final state proves the All History transition completed for all 2054
API-visible memberships: queue zero, no unbackfilled membership, no removal. Historical
Backfill is complete; content processing and evidence coverage remain naturally partial.

## Current content processing state

| State | Count | Classification |
|---|---:|---|
| completed | 1210 | Completed processing |
| subtitle_pending | 221 | Durable pending/recovery state |
| retry_wait | 244 | Durable bounded retry state |
| skipped_no_subtitle | 371 | Known evidence-coverage outcome |
| needs_review | 8 | Manual-review coverage state |
| hard failed | 0 | Terminal processing failure |

`subtitle_pending` and `retry_wait` are SQLite-owned states with persisted scheduling
metadata. They are consumed by the existing scheduled `SyncService` process and do not
depend on a Web-process memory queue. Two automatic ASR jobs had durable remote task IDs;
restart polls them instead of resubmitting them. The persistence cutover gate was `PASS`:
execution was quiesced at a safe boundary while business state remained unchanged.

## Database, migration and retrieval

- Live migration: schema v15 to v16 through normal `Database.initialize()` — PASS.
- WAL-aware verified backup: SQLite Backup API copy opens at schema v15 and passes
  `PRAGMA integrity_check`.
- Automatic second-layer backup: `shiliu.pre-v16.backup.db`, schema v15, integrity OK.
- Live schema: v16; `ask_runs`, `ask_search_trace_links`, `ask_events` present.
- Live `PRAGMA integrity_check`: `ok`.
- Retrieval units: 14,058; FTS units: 14,058; consistency PASS.

## Execution persistence and runtime smoke

| Path | Evidence | Result |
|---|---|---|
| Search | Trace `dd71b1e3-6b60-4a9e-afa7-870910d9c596` persisted and recovered | PASS |
| Ask Fast | Run `ask_run_234200b5595642ec847f105107a8e3b9`, partial/answer_ready, citation present, child Search links durable | PASS |
| Ask Deep | Run `ask_run_9f4607bc8e0d4f5e91a1f6872037ac7b`, partial/answer_ready, 12 ordered forensic events, child Search links durable | PASS |
| Web restart | Search/Fast/Deep traces recovered from a fresh process | PASS |
| Research | Minimal non-provider task created and read after restart; durable pending state preserved | PASS |

The integrated tree passed the full deterministic suite: 1,803 passed, 4 deselected, 7
existing warnings. The one-test difference from the persistence handoff is the product
branch's scheduled-runner self-unload regression test. The upstream independent review's
single High degraded-lineage issue was fixed by `770801c`; bounded re-review reported no
remaining Blocking or High findings. Local integration review found no scope expansion or
regression to Sync, retrieval, model routing, Deep policy or Research ownership.

## Scheduled processing recovery

- Existing LaunchAgent reused: `app.shiliu.sync`; no second scheduler created.
- Loaded: yes.
- Enabled: yes.
- Default source active: yes.
- Start interval: 3600 seconds, with the existing 60–300 second scheduled jitter.
- Post-cutover scheduled smoke: run 731 entered `running / scanning` and wrote a live
  heartbeat. It continues autonomously; pending/retry counts are not required to reach
  zero for readiness.

## LLM role routing and provenance

| Role | Model family |
|---|---|
| Transcript cleanup/refinement | `deepseek-v4-flash` |
| Structured summary/refinement | `deepseek-v4-flash` |
| Taxonomy | independent `deepseek-v4-pro` |
| Query analysis | `deepseek-v4-pro` |
| Deep agent action | `deepseek-v4-pro` |
| Grounded answer | `deepseek-v4-pro` |

Web Setup persists ingestion, interactive and taxonomy mappings independently. New
ingestion artifacts receive lightweight provider/model/prompt-schema/generated-at/source
provenance sidecars. Legacy artifacts are not regenerated and missing provenance remains
`legacy_unknown`.

## Safety, limitations and readiness

Backfill regression coverage proves stable Latest N boundaries, non-destructive shrink,
forward favorites bypassing the historical cutoff, idempotent restart/resume, partial
scan false-removal protection, authoritative complete-snapshot removal, multi-folder
ownership and pause/resume safety.

Known limitations are the unresolved remote-total gap, naturally pending/retry/manual
coverage states, bounded unsupported/no-subtitle outcomes, and diagnostic-but-not-
resumable Deep execution after abrupt process death. These do not invalidate the safe
cutover.

**Real-use testing readiness: `READY_FOR_REAL_USE_TESTING`.**

Shiliu now enters live-use/observational mode. This closeout does not start a new eval,
retrieval tuning cycle, feature expansion or V6 plan.
