# Post-V5 Execution Persistence Current State

## Goal 0 — complete

- Baseline: `ad1d93562f89318f25282a801466299ccc2c7867`.
- Isolated worktree: `/Users/elliot/.codex/worktrees/post-v5-execution-persistence/Shiliu`.
- Branch: `codex/post-v5-execution-persistence`; remote: `origin` (`https://github.com/Elliotii/shiliu.git`).
- Safety: the live worktree, live SQLite/Application Support data, onboarding process, config, and LaunchAgent are explicitly excluded. All tests use pytest temporary paths/databases.
- Source map: Search durability is in `retrieval/orchestrator.py` and `retrieval/product_search.py`; Fast Ask is in `ask/service.py`; Deep Ask is in `ask/deep/{service,graph,reducer,transcript}.py`; Research durability and migration patterns are in `research/schema.py` plus its services; application migrations are coordinated by `db.py`.
- Verified state: Search persists retrieval traces/presentations; Fast and Deep retain their top-level traces only in `AskService._traces`; Research persists workflow identities, ordered records, evidence, and results.
- Baseline tests: 71 passed (`test_v4_fast_ask_api`, `test_v4_deep_search`, `test_v4_search_execution`, `test_v5_a_stage1_research_kernel`).
- Known limit: `POST_V5_QUERY_PERSISTENCE_AUDIT.md` is an uncommitted document in the live worktree and was read there without modifying or copying live state.
- Next: Goal 1 contract/design freeze.

## Goal 1 — complete

- Decision: add an Ask-owned durable contract, not a generic runtime and not a Research dependency.
- Schema: one canonical run table, ordered Ask-to-Search reference rows, and ordered bounded Deep diagnostic events. Search payloads remain owned by Search.
- Retention: durable with the product DB; bounded versioned JSON only, with no raw prompts/provider payloads or transcript/context dumps.
- Migration: application schema v15 to v16, idempotent table/index creation, existing backup convention, legacy Search/Research preservation test.
- Artifact: `POST_V5_EXECUTION_PERSISTENCE_DESIGN.md`; all four design-gate questions resolve to No.
- Known limit: crash-resume is explicitly excluded; a crash may leave a diagnosable `running` run.
- Next: Goal 2 Fast Ask persistence.

## Goal 2 — complete

- Implementation: Fast creates a v1 durable Ask row before analysis, then atomically stores analysis/rewrites, ordered child Search references, adopted evidence identities, citations, answer blocks, limitations, termination, and bounded provider usage.
- Restart: `AskService.get_trace()` now loads Fast traces from SQLite; a fresh service reconstructs the run without any prior in-memory object.
- Migration: application schema is v16; the Ask tables are idempotently created and the standard pre-v16 backup is retained.
- Tests: 55 passed across Fast Ask, Fast restart/three-rewrite lineage, v15 migration preservation, Search execution, and Research kernel coverage.
- Gate: retrieval calls/results, answer generation, citation validation, Fast response shape, and failure semantics are unchanged; existing Fast tests all pass.
- Known limit: Fast persists successful child Search references at finalization; an abrupt mid-request process death leaves the run identity as `running`, but crash-resume and partial step journaling are out of scope.
- Next: Goal 3 Deep diagnostic persistence.

## Goal 3 — complete

- Implementation: Deep now creates the same Ask identity before execution and stores its bounded ordered decisions, guards and observations; navigation/transcript Search references; window-read segment identities; visited videos/segments; worklist state; budgets/guards; termination; adopted evidence; answer/citations/limitations; and provider usage.
- Lineage: navigation and transcript searches retain ordered references to their existing durable Search traces, including decision round and query. Transcript-window reads stay typed events and do not copy transcript context.
- Restart: a fresh `AskService` loads the entire Deep diagnostic record from SQLite, including ordered actions, two child Search traces, final evidence, and result.
- Tests: 45 passed across the full Fast/Deep Ask, Ask page, migration, and restart suites. Deep coverage includes navigation + transcript search + window read, normal completion, repeated/no-new/guard stops, budget/deadline stops, insufficient results, and provider failures.
- Gate: Deep policy version, prompts, graph/checkpointer choice, budgets, tool actions, retrieval, finalizer, answer/citation semantics, and HTTP response shape are unchanged.
- Known limit: Deep is diagnostically durable but intentionally not resumable after a crash.
- Next: Goal 4 product alignment and full regression/forensic validation.

## Goal 4 — complete

- Product gradient: Search remains durable retrieval execution; Fast is durable answer execution; Deep is durable forensic Agent execution; Research remains the separate durable resumable workflow.
- Final full isolated regression: 1,802 passed, 4 deselected, 7 existing deprecation warnings in 128.17s, with `PYTHONPATH` explicitly pinned to this worktree. No live-provider or external-artifact tests ran.
- Migration: the v15 temporary DB test preserves Search and Research sentinels, creates the v16 Ask contract, retains the pre-v16 backup, and then supports new Ask records.
- Restart: fresh Fast and Deep service instances recover query, understanding/decisions, ordered child Search references, adopted evidence, citations, answer, limitations, usage, status, and termination.
- Forensic scenario: with only `ask_run_id`, the Fast restart test recovers the original query, normalized analysis and rewrites, three child Search traces joined to durable Search rows, final evidence/citation, answer, and termination. Deep provides the same plus ordered decisions/actions/observations and guards.
- Degraded lineage: focused Fast and Deep tests force a failure after Search has persisted its trace and prove the error trace remains joined to the completed insufficient Ask run.
- Semantics: all pre-existing deterministic Search, Fast, Deep, and Research suites pass; no retrieval, prompt, policy, budget, answer, citation, or Research runtime behavior was changed.
- Next: Goal 5 closeout, independent read-only review, final checkpoint and handoff.

## Goal 5 — ready for final checkpoint

- Closeout: `POST_V5_EXECUTION_PERSISTENCE_CLOSEOUT.md` contains baseline, schema/migration, Fast/Deep behavior, Search/Research boundaries, tests, limitations/non-goals, and owner-only live integration instructions.
- Independent review: fresh GPT-5.6 Sol/High read-only review found one High gap in failed Search lineage. The Main Owner applied a narrow fix, added Fast/Deep durable-error-trace join tests, and the bounded re-review confirmed the High resolved with no Blocking/High findings remaining.
- Review follow-through: migrated v15-shaped DB tests now execute and restart-read both Fast and Deep; unexpected failures are classified; duplicate link/event/result copies were removed from `trace_json`; Search persistence status/error is retained beside each reference without copying Search payloads.
- Verification: final exact-tree full suite is 1,802 passed, 4 deselected; compileall and `git diff --check` pass.
- Live isolation: read-only recheck shows the live branch/HEAD and pre-existing Markdown-only status are unchanged.
- Next: commit, push, report final branch HEAD, and stop.
