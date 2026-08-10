# Post-V5 Implementation Preflight

Date: 2026-08-11 (Asia/Shanghai)

## Protected baseline

- Protected branch: `codex/v5-main`
- Protected/pushed HEAD: `3cd5c8cd66ba7d7250383385a7f9d25064820fc2`
- Remote: `origin` (`https://github.com/Elliotii/shiliu.git`)
- The protected branch and `origin/codex/v5-main` were aligned at preflight.
- Development branch: `codex/post-v5-product-closeout`
- No V5 history, Frozen Eval identity, held-out semantics, or accepted V5-D outcome was changed.
- The only pre-existing worktree item was the untracked, task-supplied
  `SHILIU_CURRENT_LLM_CALL_INVENTORY.md`; it was preserved.

## Repository instructions and migration convention

- No repository `AGENTS.md` was present.
- Schema changes use additive `CREATE TABLE IF NOT EXISTS` / `_ensure_columns`
  migrations, a monotonically increasing `SCHEMA_VERSION`, and a pre-migration
  SQLite backup. The live schema is version 14.
- Existing retrieval, sync lock, pipeline stage, history backlog, and LaunchAgent
  mechanisms are the required extension points; no parallel runtime is needed.

## Live product read-only baseline

- SQLite integrity: `ok`.
- Favorite Sources: 2 total; one active and one in cooldown.
- Memberships: 159 total, 156 active, 0 queued history.
- Videos: 157 total; 140 completed, 1 needs review, 3 remotely removed.
- Retrieval units: 1,633.
- No sync run was active during preflight. Recent scheduled runs completed with
  bounded per-item/source errors rather than a process crash.
- The existing hourly `app.shiliu.sync` LaunchAgent is loaded, has a 3,600-second
  interval, and most recently exited 0. `app.shiliu.web` is loaded and running.
- Live config has automatic sync and baseline confirmation enabled. Credential
  references exist in Keychain-backed configuration; no secret value was read.

## Model routing baseline

- Transcript cleanup/refinement: `deepseek-v4-flash`.
- Summary/refinement: `deepseek-v4-pro`.
- Query analysis, Deep agent action, and grounded answer: global
  `deepseek-v4-pro`.
- All `taxonomy_*` roles are currently remapped to the summary role.
- Web Setup currently writes the summary form's general `model` value into
  `llm.model`, so a Summary edit can unintentionally move interactive roles.
- Pipeline stage rows already record provider, model, prompt version, and stage
  timestamps. Artifact files do not yet carry a compact generation receipt.

## Backfill/sync baseline risks to resolve

- `latest_n` is represented as a one-time queue count, not a stable
  `favorite_time` boundary.
- There is no supported expansion/shrink operation after source creation.
- Snapshot reconciliation always treats the returned item list as complete and
  authoritative; a partial scan could therefore false-remove memberships.
- Initial membership discovery and materialization are partly separated, and
  history processing already uses the global sync lock, bounded batches, durable
  pipeline stages, and retrieval coordinator.
- Video removal reconciliation already checks for any remaining active
  membership, which is the basis for multi-folder safety, but needs regression
  coverage around partial snapshots and policy changes.

## Execution decision

Proceed on the dedicated branch with: (1) static independent ingestion,
interactive, and taxonomy routing plus lightweight artifact receipts; (2) an
additive source coverage schema and authoritative-snapshot flag; (3) non-
destructive coverage expansion/shrink controls; and (4) focused UI/tests. Real
source onboarding begins only after both implementation gates are committed and
pushed.
