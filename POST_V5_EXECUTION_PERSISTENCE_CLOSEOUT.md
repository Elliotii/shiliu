# Post-V5 Execution Persistence Closeout

## Baseline and Isolation

- Baseline: `ad1d93562f89318f25282a801466299ccc2c7867`.
- Development branch: `codex/post-v5-execution-persistence`.
- Isolated worktree: `/Users/elliot/.codex/worktrees/post-v5-execution-persistence/Shiliu`.
- Stable implementation checkpoints:
  - `a00a258` — Fast Ask persistence, v16 migration, design and migration/restart tests.
  - `5e42881` — Deep forensic persistence and Deep restart/lineage tests.
- Final handoff HEAD is the branch tip after the closeout/review commit and is reported by `git rev-parse origin/codex/post-v5-execution-persistence` in the handoff response. A commit cannot embed its own hash.
- The live worktree remains at `ad1d935` on `codex/post-v5-product-closeout`, with exactly its pre-existing Markdown changes. No live source, config, schema, SQLite/Application Support data, LaunchAgent, branch, or onboarding process was changed.

## Schema and Migration

Application schema v16 adds three Ask-owned tables:

- `ask_runs`: run identity, request/lifecycle, bounded analysis/result/usage/trace payloads, and an optional future `parent_run_id` identity reference.
- `ask_search_trace_links`: ordered references to existing Search trace identities plus persistence status/error; it does not copy Search candidates, ranks, index identity, or presentation payloads.
- `ask_events`: ordered bounded Deep decision/guard/observation records.

Migration uses idempotent table/index creation and the existing pre-migration SQLite backup convention (`shiliu.pre-v16.backup.db` when upgrading v15). The temporary v15-shaped migration tests prove existing Search and Research sentinels survive, then execute and restart-read new Fast and Deep runs. Search tables remain lazily owned by Search, so Ask does not add a foreign-key dependency to their creation order.

## Fast Persistence

Fast creates `ask_run_id` before query analysis. On completion it durably binds:

```text
Ask query and filters
  -> normalized analysis and bounded original/rewrite queries
  -> ordered child Search trace references
  -> adopted evidence source/version/segment identities
  -> citations
  -> answer blocks and limitations
  -> usage, status, and termination
```

A fresh `AskService` reconstructs the trace by ID from SQLite. The three-rewrite restart test also joins every Ask child reference to its durable `retrieval_search_traces` row.

## Deep Persistence

Deep creates the same Ask identity before entering the existing graph. On completion it stores bounded, typed, ordered forensic information:

- Agent decisions and actions.
- Guard approvals/stops and deterministic fallback events.
- Navigation, transcript-search, and transcript-window observations.
- Navigation and transcript Search trace references with their decision round and query, including zero-evidence searches.
- Window anchors/resulting segment identities, visited videos/segments, open/resolved questions, and bounded guard/budget state.
- Adopted evidence/citations, answer/limitations, usage, status, and stop reason.

This is diagnostic durability only. The LangGraph execution still has no checkpointer and cannot resume after a crash. No prompt, policy, budget, tool, retrieval, answer, or citation behavior was changed.

## Search Relationship

Search remains the sole owner of durable retrieval execution and presentation traces. Ask stores only ordered identity references plus minimal query/execution attribution. Forensic inspection follows `ask_search_trace_links.search_trace_id` to `retrieval_search_traces.trace_id`; no Search trace payload is duplicated into Ask.

## Research Boundary

Research remains the separate durable, resumable Task/Goal/Attempt/Trace/Checkpoint/Evidence/Result workflow. Ask does not import Research contracts, create Research tasks/attempts/checkpoints, use Research resume logic, or share a generic runtime. The only alignment is semantic: durable identity, lineage, result attribution, and diagnosability.

## Verification

All tests were run from the isolated worktree with the source path explicitly pinned:

```text
PYTHONPATH=<isolated-worktree>/src:<isolated-worktree> \
  <shared-venv>/bin/python -m pytest

1802 passed, 4 deselected, 7 warnings in 128.17s
```

The four deselections are the repository's configured `external_artifact` and `live_provider` exclusions. Warnings are existing Starlette/httpx and multiprocessing fork deprecations.

Focused evidence includes:

- Fast multiple rewrites, partial/insufficient, answer repair, provider failure, and restart recovery.
- Deep multiple actions, navigation + transcript search + window read, normal completion, repeated/no-new/guard/budget stops, insufficient/provider failure, and restart recovery.
- Search execution persistence regressions.
- v15-to-v16 migration with Search/Research preservation.
- Research kernel and the full Research regression suite.
- Forensic recovery using only `ask_run_id`: query, analysis/decisions, child Search lineage, durable retrieval rows, final evidence, citations, answer, status, and termination.
- Fast and Deep degraded paths that fail after Search trace creation still retain and join the durable error Search trace.

## Independent Read-only Review

A fresh GPT-5.6 Sol/High reviewer inspected scope, schema, Search duplication, Research coupling, migration, restart claims, tests, semantics, and live isolation without editing files. It found one High issue at checkpoint `5e42881`: a Search exception could lose its already-created durable trace reference. The Main Owner applied the narrow Fast/Deep fix and added join tests; the one bounded re-review verified the defect resolved and reported no remaining Blocking or High findings.

Follow-through also addressed its non-blocking observations: migrated DB tests now execute/restart-read both modes, unexpected failures distinguish provider/time-budget/implementation classes, structured link/event/result data is no longer duplicated inside `trace_json`, and Search `trace_persisted`/`trace_error` accompanies the identity reference without duplicating Search payloads.

## Known Limitations and Explicit Non-goals

- A process death can leave an identifiable `running` Ask row; partial step journaling and crash resume are not implemented.
- Ask records follow current product DB retention and have no new deletion/retention UI.
- No raw prompts, full provider payloads, full navigation documents, unbounded model context, or transcript dumps are stored. Final citation quotes remain part of the user-visible result.
- No live cutover, feedback UI, intent/router implementation, retry/remediation workflow, evidence enrichment, retrieval/model/index changes, Deep policy tuning, Research rewrite, generic runtime, checkpointer, observability platform, dashboard, event bus, eval framework, or multi-agent architecture is included.

## Live Integration Instructions (Main Owner Only)

Do not integrate until the 600+ item ingestion is confirmed complete and the live owner has preserved its Markdown work.

1. Fetch and review `origin/codex/post-v5-execution-persistence`, including the independent review result and this closeout.
2. Integrate in a separate non-live worktree; do not switch the current live worktree branch while ingestion or its closeout is active.
3. Run the full deterministic suite with the intended source path pinned.
4. Stop the Web process only after ingestion is complete. Create a verified SQLite backup using the SQLite backup API so WAL state is included; retain the automatic `pre-v16` migration backup as an additional safeguard.
5. Start the integrated application so `Database.initialize()` performs the v16 migration. Never run the migration against live data from this development session.
6. Smoke `/search`, Fast Ask, Deep Ask, and Research. Record Fast and Deep `ask_run_id` values, recreate/restart the service, and verify `/api/ask/traces/{run_id}` still returns the durable answer/diagnostics and child Search lineage.
7. If any migration or smoke check fails, stop and restore from the verified pre-cutover backup; do not alter the completed ingestion data in place.

No merge, live migration, service restart, LaunchAgent change, or cutover was performed by this session.
