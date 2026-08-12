# Post-V5 Product Closeout

Date: 2026-08-11 (Asia/Shanghai)

Protected baseline: `codex/v5-main` at `3cd5c8c`. Development branch:
`codex/post-v5-product-closeout`. This closeout does not reopen V5-A/B/C/D, change
held-out semantics, rerun Frozen Eval, or reclassify an accepted V5 outcome.

## Product outcome

Shiliu is positioned as a local, evidence-driven retrieval and research assistant for a
personal Bilibili collection. This round closes the gap between the accepted V5 product
and long-lived real-corpus operation:

- ingestion transcript and summary roles use Flash;
- interactive query analysis, Deep decisions and grounded answers use Pro;
- taxonomy uses an independent Pro role family;
- Web Setup persists those three mappings independently;
- new ingestion artifacts receive lightweight generation provenance;
- favorite membership discovery, bounded historical materialization and continuous
  forward sync have distinct semantics;
- stable favorite-time boundaries make Latest N non-drifting and non-destructive;
- only complete authoritative snapshots may reconcile remote removals;
- multi-folder membership and last-active ownership remain explicit;
- interruption/restart uses the existing database stages, sync lock, retry state and
  retrieval coordinator.

## Stable checkpoints

| Checkpoint | Commit | Meaning |
|---|---|---|
| Model routing + provenance | `7e78424` | Static role isolation, Web Setup decoupling, legacy config compatibility and ingestion artifact sidecars |
| Backfill + sync + UI | `0f3f613` | Schema v15, stable history coverage, authoritative snapshot safety, source metrics and regression suite |
| Bounded history drain | `4ed19b7` | Materialize already-discovered history through the normal locked pipeline without rescanning the remote source |
| Large-source scan | `271865d` + `ea1d697` | Reuse one authenticated bridge process for all pages, pace calls and keep upstream error payloads bounded |

The last three fixes were found during the real-corpus rollout. They stay within the
existing SyncService/Bilibili bridge architecture and do not introduce a new scheduler,
queueing system, distributed runtime or agent framework.

## Backfill safety contract

The repository now enforces the following product invariants:

1. Latest N resolves to a persisted `favorite_time` cutoff at authoritative baseline
   initialization. New forward favorites enter regardless of that cutoff.
2. Expanding history queues additional unmaterialized memberships. Shrinking history
   only clears old queue flags; it never deletes videos, artifacts, indexes, notes,
   reading state or knowledge state.
3. Partial/bounded/incomplete scans may update observations but cannot mark unseen
   memberships removed. Remote failure performs no reconciliation.
4. A complete authoritative snapshot can still remove a source membership. Shared video
   state remains active while another source has an active membership.
5. Pause/resume/history/source removal mutations use the same process lock as sync, and
   materialization rechecks active source/membership state.
6. History batches are idempotent and resumable through the existing membership queue,
   video pipeline stages and index coordinator.

The pre-implementation audit is in `BACKFILL_SYNC_SAFETY_REVIEW.md`. The persistence
branch received a fresh independent read-only review; its single High degraded-lineage
finding was fixed by `770801c` and bounded re-review found no remaining Blocking/High
issue. The integrated tree then passed local scope review and the full deterministic
suite before live cutover.

## Evidence and provenance boundary

Raw Subtitle / Raw ASR remains the only factual Citation Authority. Transcript cleanup,
Summary, Chapter metadata and Taxonomy are derived/navigation material.

New transcript/summary artifacts record provider, requested model, prompt/schema
version, generation time, reasoning settings and source hash in a small sidecar. Existing
artifacts are not regenerated; missing metadata is returned as `legacy_unknown` rather
than guessed.

## Portfolio claim boundary

Allowed positioning: “个人 Bilibili 收藏的证据驱动检索与研究助手”. Capability-to-
evidence mapping is in `PORTFOLIO_EVIDENCE_INDEX.md` and the repeatable walkthrough is in
`DEMO_GUIDE.md`.

This evidence does not support claims of a large-scale distributed system,
production-grade high concurrency, universal multimodal understanding, validated
self-improvement, GraphRAG or an open-ended autonomous agent.

## Operational handoff

The redacted real-corpus counts, 100/300/full coverage transitions, schema v16 cutover,
scheduled-sync recovery, retrieval checks, restart smoke and known limitations are
authoritative in `POST_V5_REAL_CORPUS_ONBOARDING_REPORT.md`. All readiness gates passed on
2026-08-12. Shiliu is `READY_FOR_REAL_USE_TESTING` and enters live-use/observational mode:
natural queries and naturally occurring failures should drive selective repair; this
closeout does not authorize V6 feature expansion.
