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
