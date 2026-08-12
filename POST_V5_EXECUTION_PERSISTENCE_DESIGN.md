# Post-V5 Execution Persistence Design

## Current State

| Path | Durable today | Missing or unlinked |
|---|---|---|
| Search | query, filters/scope, routing, index identity, candidates/ranks, presentation identities, `trace_id` | full UI response snapshot (not required here) |
| Fast Ask | each child Search trace | Ask run identity, analysis/rewrites, child lineage, adopted evidence, answer/citations, usage and termination |
| Deep Ask | each transcript Search trace; source artifacts | ordered Agent decisions/actions/observations, child lineage, navigation/window reads, worklist/guards, adopted evidence, answer and termination |
| Research | task/goal/attempt/trace/checkpoint/evidence/result contracts and ordered durable workflow | no Ask gap; Research remains a separate resumable runtime |

Source inspection confirms the audit's main boundary. `AskService._traces` is process memory, while Search writes SQLite trace/presentation rows and Research owns its independent durable workflow schema.

## Problem

After a Web/service restart, a user-visible Ask answer cannot be attributed to its analysis, child Search traces, evidence, citations, or termination. The target is durable identity, lineage, attribution, and forensic diagnosis—not runtime unification or crash-resume.

## Minimal Contract

Every Ask creates a durable run before model/retrieval work begins and completes it atomically with its final diagnostic record.

- Identity: `run_id`, contract version, `created_at`, `completed_at`, `mode`, optional `parent_run_id`.
- Request: original query and bounded filters.
- Lifecycle: `lifecycle_status` (`running`, `completed`, `failed`), answer status, termination reason, bounded failure metadata.
- Understanding: normalized intent/analysis, original plus bounded rewrites, analysis error and provider usage.
- Search lineage: ordered references containing query, execution ID, Search `trace_id`, and the Deep event/decision position when applicable.
- Result attribution: bounded final evidence identities (citation/source/version/timeline/segments plus retrieval provenance), citation records, answer blocks, limitations.
- Diagnostics: provider/usage summary and the existing bounded Fast trace or typed ordered Deep event trace.
- Deep-only diagnostics: ordered decisions/guards/observations; navigation and transcript-window identities; visited video/segment identities; open/resolved questions; budget/guard state; stop reason.

An interrupted process leaves a durable `running` row, so the execution remains identifiable. This change does not add resume/checkpoint semantics.

## Schema Choice

Use three Ask-owned SQLite tables rather than a generic execution runtime:

1. `ask_runs`: one canonical run row with searchable identity/lifecycle columns and bounded JSON payloads for request analysis, final evidence/result, usage, trace, and failure.
2. `ask_search_trace_links`: ordered Ask-to-Search references plus the Search trace's persistence status/error. Search trace content remains exclusively in existing Search tables.
3. `ask_events`: ordered, typed, bounded Deep diagnostic events. Fast does not synthesize workflow events.

This is intentionally smaller than Research. JSON is appropriate for bounded versioned diagnostic/result shapes; identity, lifecycle, ordering, and lineage remain relational.

## Lineage Model

```text
ask_runs.run_id
  -> ask_search_trace_links.search_trace_id
       -> retrieval_search_traces.trace_id
  -> final_evidence[].retrieval_provenance.search_trace_id
  -> citations[].citation_id
       -> answer_blocks[].citation_ids
```

Deep events keep the reason/action immediately before each tool observation. Transcript-search observations record their Search trace references even when retrieval returns no evidence. Window reads record anchor and resulting segment identities without copying transcript windows or prompts.

`parent_run_id` is only an identity extension point for a future retry/remediation flow. No retry, feedback, routing, or enrichment behavior is implemented.

## Retention Decision

Ask records follow the product database's current durable retention behavior: no automatic deletion is introduced. Payloads are bounded by existing query/action/evidence limits. Raw prompts, full provider responses, navigation documents, transcript bodies beyond final citation quotes, model context, and unbounded internal objects are not stored.

## Migration Strategy

- Advance the application schema from v15 to v16.
- Create the three new tables and indexes with idempotent `CREATE TABLE/INDEX IF NOT EXISTS` statements.
- Do not rewrite Search or Research rows and do not add foreign keys to lazily-created Search tables.
- Preserve the existing pre-migration backup convention.
- Test a v15-shaped temporary database containing Search and Research sentinels, initialize v16, verify preservation, then execute and restart-read new Fast and Deep runs.

## Design Gate

- New generic runtime: **No**. The repository is Ask-owned and has no execution engine.
- Search trace duplication: **No**. Only trace identity/query/execution references are stored.
- Ask converted to Research: **No**. No task, attempt, checkpoint, resume, or Research dependency is introduced.
- Future over-design: **No**. The sole future field is optional `parent_run_id`; current run IDs already provide a feedback target.

## Explicit Non-goals

No retrieval, rewrite-quality, answer, citation, Deep prompt/policy/tool/budget, Research runtime, routing, feedback UI, evidence enrichment, retry orchestration, resume/checkpointer, dashboard, telemetry platform, event bus, or live cutover change is authorized.
