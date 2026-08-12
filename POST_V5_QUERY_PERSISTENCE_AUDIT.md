# Shiliu Query / Run / Trace / Evidence Persistence Audit

Current as of 2026-08-12, after the live schema v16 cutover. In this document,
“durable” means stored in the product SQLite database and readable after Web service
restart; it does not mean immutable or exempt from normal database retention.

| Product path | Query | Identity | Trace and lineage | Evidence and result | Feedback |
|---|---|---|---|---|---|
| `/search` | Durable | Durable `trace_id` | Durable execution trace and presentation identity | Durable hit IDs/ranks/windows; the complete rendered response is not snapshotted | None |
| `/ask` Fast | Durable | Durable `ask_run_id` | Durable analysis, rewrites, and ordered child Search references | Durable adopted evidence identities, citations, answer, status, termination, and bounded usage | None |
| `/ask` Deep | Durable | Durable `ask_run_id` | Fast fields plus ordered decisions, guards, observations, navigation/search/read diagnostics | Durable final evidence, citations, answer, status, termination, and bounded usage | None |
| `/research` | Durable | Durable task/goal/attempt/trace/result identities | Durable resumable workflow, checkpoints, events, commands, and side effects | Durable evidence use/provenance/validation, results, artifacts, and knowledge state | Durable advisory knowledge feedback |

## Search

Search remains the sole owner of retrieval execution persistence. It stores the original
and normalized query, mode/scope/filters, router and fallback decisions, index/model
identity, timing, candidate counts, unit IDs, ranks and scores in
`retrieval_search_traces`. Product grouping/window identities and jump positions are in
`retrieval_search_presentations`.

The HTTP response and current UI contain richer rendered fields such as complete cards,
excerpts, chapter summaries, warnings and corpus context. Those fields are not preserved
as a byte-for-byte UI snapshot. A saved trace reconstructs what retrieval selected, not
the exact historical DOM.

## Ask Fast

Schema v16 stores Fast execution in `ask_runs` and links each rewrite/search attempt to
the Search-owned trace through ordered `ask_search_trace_links` rows. A fresh Web process
can recover:

- original query, filters, normalized analysis and rewrites;
- child Search trace identities and persistence outcomes;
- adopted evidence source/version/segment identities;
- citations, answer blocks, limitations, status and termination;
- bounded provider usage and diagnostic trace data.

Search payloads are not copied into Ask. Following a child trace ID to
`retrieval_search_traces` provides the retrieval details. The degraded path also retains
the child reference when Search created a durable trace before raising an error.

## Ask Deep

Deep uses the same durable run and Search-link contract, plus ordered `ask_events` for
bounded forensic diagnostics. These events preserve decisions/actions, guards,
navigation and transcript-search observations, window-read segment identities,
visited/open/resolved state, budgets and termination context without storing raw prompts,
full provider payloads or transcript dumps.

This is diagnostic persistence, not crash-resumable execution. A process death may leave
an identifiable `running` row; LangGraph still has no checkpointer and the interrupted
Deep run is not resumed from its last action.

## Research

Research remains a separate durable and resumable Task/Goal/Attempt/Trace/Checkpoint
runtime. Its schema preserves objectives and constraints, ordered events, command
receipts, inner actions, retrieval references, side-effect state, audits, evidence
identity/use/provenance/validation, terminal results, provisional answer artifacts and
Knowledge Workspace revisions.

Research feedback is durable advisory input recorded as events and idempotent command
receipts. Ask persistence does not import Research contracts or share a generic runtime.

## UI-only and browser-local state

Loading indicators, polling state, current expanded panels, assembled product projections
and the exact rendered response remain UI/HTTP-response state. Search and Ask queries may
also appear in browser navigation history via page URLs; browser history is not Shiliu
server-side persistence.

Implementation and migration evidence is recorded in
`POST_V5_EXECUTION_PERSISTENCE_CLOSEOUT.md` and live-cutover evidence in
`POST_V5_REAL_CORPUS_ONBOARDING_REPORT.md`.
