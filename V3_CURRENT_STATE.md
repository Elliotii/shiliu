# Shiliu V3 Current State

> **Status: superseded.** This file is retained as a historical Stage 6 state
> record. Current V3 authority is `SHILIU_V3_VERSION_DECISION.md` and
> `V3_CLOSEOUT.md`; repository-wide authority is
> `SHILIU_V0_TO_V3_5_FINAL_CLOSEOUT.md`.

## 1. Version Identity

```text
Version: Shiliu V3 — Searchable Evidence Library
Role: Portfolio-grade Retrieval MVP
Status: Stage 6B Delivered — Ready for Version Session Review with Follow-up
Authority:
- 00_V3_RETRIEVAL_VERSION_BRIEF.md
- 01_V3_SESSION_OPERATING_CONTRACT.md
```

## 2. Local Baseline

```text
Project root:
/Users/elliot/new-systems/agent-job-prep/Shiliu

Audited branch:
codex/v3-domain-completion

Stage 5 starting HEAD:
8287c8d

Application:
Python / FastAPI / Jinja / SQLite / filesystem artifacts

Main database:
/Users/elliot/Library/Application Support/Shiliu/shiliu.db

Content root:
/Users/elliot/Documents/Shiliu
```

Phase 0 and its focused evidence supplement introduced no repository or database changes.
Stage 1 added product retrieval code and additive retrieval tables/FTS5 data to the local database.

## 3. Confirmed Data Facts

The following Product counts are the accepted Phase 0 discovery snapshot. Later
authorized Product synchronization advanced the live formal database to 144 Videos;
the Stage 4B anchor closure used 130 declared raw-subtitle files containing 65,234
segments. The historical snapshot is retained here for provenance rather than
silently rewritten.

* `videos` contains 143 rows.
* Video status distribution:

  * `completed`: 128
  * `needs_review`: 1
  * `retry_wait`: 2
  * `skipped_no_subtitle`: 11
  * `subtitle_pending`: 1
* 141 BVID artifact directories exist.
* The two Videos without artifact directories are both `retry_wait` and have no subtitle, summary, or transcript paths.
* 129 Videos have raw subtitle paths.
* All 129 associated `subtitle-raw.json` files exist and parse successfully.
* The files contain 64,925 subtitle segments.
* All 64,925 segments satisfy the Phase 0 structural timestamp validation:

  * finite numeric `from` and `to`;
  * `0 <= from <= to`;
  * non-empty `content`.
* Subtitle source coverage:

  * AI subtitle: 119 Videos / 61,521 segments
  * Human subtitle: 5 Videos / 3,210 segments
  * ASR: 5 Videos / 194 segments
* 102 Videos have summary paths.
* 85 Videos have cleaned transcript paths.
* `videos.id` is the Video primary key.
* `(platform, source_id, part)` is database-unique.
* Subtitle, subtitle segment, summary and chapter do not have stable independent IDs.
* `video_notes.id` is a primary key and references `videos.id`.
* Favorite-folder membership is represented by `favorite_sources` and `video_source_memberships`.

## 4. Confirmed Architecture

* Product processing is implemented in the Sync, Pipeline, ASR, Library, Database and Web modules.
* SQLite stores Videos, user state, memberships, notes, jobs and stages.
* Raw subtitle, cleaned transcript and summary artifacts are stored in BVID filesystem directories.
* File writes and database state updates do not share one transaction.
* Summary, subtitle-only, ASR, refinement and Note changes do not share one unified completion callback.
* The Phase 0 `events` snapshot contained 271 events, all `pending` with `processed_at IS NULL`; the Stage 4B anchor closure integrity snapshot contains 273 rows.
* The existing event table is not an active, reliable indexing queue.
* Taxonomy Research shares the Application composition root, database and Provider factory, but Product Sync, Pipeline and Library do not call the Taxonomy workflow.
* Taxonomy Research assets do not automatically become Product Search assets.
* Product retrieval is isolated in `shiliu.retrieval`; it does not import or invoke the Taxonomy workflow.
* Retrieval units use deterministic product identities derived from `(platform, source_id, part)`, unit type, timestamp bounds and a content hash.
* Raw subtitle chunks preserve whole upstream segments and use raw subtitle seconds as timestamp evidence.
* The lexical index uses SQLite FTS5 with the `trigram` tokenizer and BM25 scoring normalized so higher returned scores are better.
* The additive retrieval schema consists of `retrieval_units`, `retrieval_unit_folders`, `retrieval_index_meta` and `retrieval_units_fts`.
* The Stage 4B anchor closure snapshot contains 1,555 Retrieval Units, 1,555 matching FTS rows and 1,555 matching Dense vectors.
* `retrieval_index_meta` is defined as current index state: replace/delete refresh current Video and Chunk counts in the same transaction as metadata, FTS and folder mutations.
* `retrieval_index_meta.rebuilt_at` remains the last successful full-rebuild time; additive `updated_at` records the latest current-state refresh.
* `statistics()` and the retrieval stats CLI separate actual current table counts, current Index Meta counts and last full-rebuild time.

## 5. Current Scope Status

### Required

* Retrieval data model: delivered for the Stage 1 lexical baseline
* Video-level retrieval: delivered for lexical search
* Transcript Chunk-level retrieval: delivered from raw subtitle artifacts
* FTS5 / BM25 baseline: delivered
* Dense retrieval: Stage 2 delivered with local FastEmbed and SQLite exact search
* Hybrid retrieval: Stage 2 delivered with rank-only RRF fusion
* Query Understanding: Stage 4A deterministic normalization, classification and routing delivered
* Metadata filtering: Stage 1 baseline delivered
* Timestamp Evidence: Stage 4B grouped windows and deterministic raw-segment jump anchors delivered
* Incremental indexing: Stage 3 post-commit Product hooks, per-Video synchronization and reconciliation delivered
* Product surface: raw and grouped CLI/API plus Stage 5 evidence-oriented Web Search UI delivered
* Retrieval Eval: Stage 6B formal Snapshot-only evaluation delivered
* Search Trace and tests: linked bounded Raw and Product Presentation traces delivered

### Optional

Not entered.

### Out of Scope

Grounded QA, Agent, Memory, Multi-Agent, MCP, complete Taxonomy, GraphRAG and heavy search infrastructure remain prohibited.

## 6. Current Stage

```text
Phase 0: Accepted
Stage 1: Accepted with Follow-up
Stage 2: Accepted with Follow-up
Stage 3: Accepted with Follow-up
Model Selection Gate: Accepted with Follow-up
Selected Dense Model: Qwen/Qwen3-Embedding-0.6B revision 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3
Model Adoption: Accepted with Follow-up
Stage 4A: Accepted with Follow-up
Stage 4B: Accepted with Follow-up
Stage 5: Accepted with Follow-up
Stage 6A: Delivered
Stage 6B: Delivered — Ready for Version Session Review with Follow-up
```

Stage 1 follow-up disposition at Stage 2 delivery:

1. `eligible_video_count` means the current indexed Video-unit count, not every row in `videos`.
2. The formal database received the backward-compatible `retrieval_index_meta.updated_at` addition during the authorized Stage 2 schema initialization.

## 7. Delivered

* Phase 0 Read-only Local Discovery
* Focused evidence supplement
* Verified timestamp feasibility
* Verified current retrieval absence
* Verified Product / Taxonomy boundary
* Deterministic whole-segment subtitle chunking with bounded overlap
* Product Video and Transcript Chunk retrieval units with provenance
* Additive SQLite metadata schema and FTS5 trigram index
* BM25 lexical retrieval with Video/Chunk level selection and metadata filters
* Explicit short-query substring fallback for queries shorter than three characters
* Full rebuild, statistics and search CLI commands
* Per-Video replacement and deletion primitives
* Stage 1 test coverage and formal-database rebuild evidence
* Transactional current Index Meta refresh after per-Video replace/delete
* Additive, backward-compatible `retrieval_index_meta.updated_at`
* Favorite-time inclusive range test coverage
* Mixed active/removed Membership provenance and cleanup coverage
* Expanded short-query fallback behavior coverage
* FTS special-character regression coverage
* Lazy FastEmbed adapter using `BAAI/bge-small-zh-v1.5`
* Same-model-tokenizer-aware Video projection capped at 480 tokens and direct Transcript Chunk projection
* SQLite-persisted normalized float32 Dense vectors with exact NumPy cosine search
* Incremental Dense rebuild reuse, stale cleanup and failure-safe replacement
* Dense Video/Chunk search with Stage 1 filters and provenance
* Rank-only RRF Hybrid retrieval with approved score/best-component-rank/unit-ID ordering
* Dense/Hybrid CLI modes, rebuild and statistics commands
* Formal Dense index: 1,547 vectors aligned with 1,547 Retrieval Units
* Nine automated Dense/Hybrid tests and 310-test standard full-suite pass
* `RetrievalIndexCoordinator` with ordered Lexical-then-Dense synchronization and explicit failure states
* Additive `retrieval_sync_state` with per-Video desired/current/error recovery state
* Post-commit Product hooks for Pipeline completion, subtitle-only, ASR, summary, refinement, Library state/Note, Sync Membership and Web source lifecycle paths
* Failure-isolated Product mutations: Retrieval failures are recorded/logged without rolling back Product state
* Controlled `sync-video`, `sync-status`, `retry-failed` and `reconcile` CLI recovery commands
* Stable formal FastEmbed cache at `~/Library/Caches/Shiliu/fastembed`
* Formal reconciliation: 143 Videos examined, 142 indexed and 1 absent, with 1,547 unchanged Dense vectors reused
* Thirteen automated Stage 3 lifecycle tests and 323-test standard full-suite pass
* Formal offline-only lazy Qwen Provider with pinned local revision, fixed query instruction and normalized 512-d output
* Full Provider/Experimental parity smoke: maximum absolute difference 0 and probe cosine at least 0.999999881
* Provider/index compatibility guard covers model, revision, provider, dimension, embedding mode, projection, instruction, input policy and dense version
* Qwen Shadow Candidate: 1,547 validated vectors with zero missing, extra, duplicate, damaged, non-finite, norm or foreign-key violations
* Formal BGE vectors/meta remain active and unchanged pending explicit Cutover authorization
* Pre-cutover database backup and Product Source table hashes recorded in `V3_MODEL_ADOPTION_AND_EVIDENCE_REPORT.md`
* Seven Qwen Provider tests, seven Dense Adoption/Cutover tests and 346-test standard full-suite pass
* Atomic Cutover completed after explicit authorization with writers stopped and all preconditions revalidated
* Formal Dense Meta and all 1,547 vectors now use Qwen identity `v3-dense-qwen3-0.6b-mrl512-v1`
* Formal Qwen Dense/Hybrid searches passed for MCP, LangGraph, RAG, FAISS and a Chinese semantic query
* Two formal reconciles reused all 1,547 Qwen vectors with zero new embeddings; unchanged Video 1 sync reused all 4 vectors
* Shared `SearchRequest -> SearchPlan -> SearchOrchestrator` path for CLI and raw API
* Deterministic NFKC/whitespace normalization and four-way query classification
* Default Lexical mode retained; opt-in Auto routes exact ASCII entities to Lexical and other classified queries to Hybrid
* Auto-only approved Dense-availability fallback to Lexical with explicit reason; explicit Dense/Hybrid never silently fallback
* Raw Video/Transcript Chunk result contract preserves retriever order, component ranks/scores, provenance and timestamp evidence
* Additive bounded `retrieval_search_traces` persistence with successful and failed request evidence
* Raw Search API and Trace lookup API plus CLI `auto`, `scope`, `top-k` and `trace` controls
* Forty-three automated Stage 4A tests and 389-test standard full-suite pass
* Formal 25-query planning/routing matrix plus real HTTP and CLI smoke evidence
* Product Search over-fetches 50–100 Stage 4A Raw Hits without exposing `raw_top_k`
* Stable Raw `unit_id` deduplication and same-Video grouping ranked by best Raw Hit
* Twenty-second overlap/gap-based temporal evidence consolidation with component Unit evidence
* Deterministic query-aware jump anchors sourced only from raw subtitle segment starts
* Semantic questions explicitly retain Chunk-start fallback rather than claiming segment precision
* AI Summary Chapter enrichment with derived, auxiliary boundaries that never affect ranking or jump time
* Additive bounded `retrieval_search_presentations` linked to the authoritative Raw Trace ID
* `POST /api/search` product endpoint and combined Raw/Presentation Trace lookup
* Grouped CLI mode sharing the same `ProductSearchService`
* Thirty-seven original Stage 4B tests and 426-test standard full-suite pass
* Seventeen-request formal API matrix plus real grouped CLI and Raw API compatibility smoke
* Shared ASCII technical-entity boundary semantics for both `exact_query_phrase` and `exact_entity_term`
* Explicit boundary behavior for RAG, AI, MCP, GPT-5, OpenAI, C++, C#, `.NET` and Qwen version entities
* Fifty-nine additional anchor-boundary test cases; 75 enrichment tests and 485-test controlled full-suite pass
* Six-query formal boundary smoke with linked Raw and Product Presentation Traces
* Independent `/search` Jinja page with a single-column, backend-ordered video result list
* Native JavaScript URL state, Back/Forward restoration, explicit mode/scope and Product filters
* Additive batch-loaded cover, detail, reading, marked and folder display metadata without frontend N+1 requests
* Evidence cards with primary/additional windows, honest precise/fallback anchor wording and auxiliary AI Chapter labels
* Central Bilibili timestamp URL helper and real-browser timestamp navigation evidence
* Idle, Loading, Success, Empty, Auto Fallback, structured Error and partial-enrichment states
* AbortController plus monotonic-sequence protection against stale-search result replacement
* Safe DOM rendering, keyboard/accessibility support and desktop/narrow responsive layout
* Fourteen focused Stage 5 tests and 499-test controlled full-suite pass
* Six Stage 5 browser screenshots and real formal-database browser validation
* Stage 6A writer audit, settled Live baseline, Backup-API SQLite snapshot and lightweight artifact freeze
* Immutable 1,555-unit Eval corpus with manifest, hashes, zero Live artifact references and isolated writable trace copy
* Locked Stage 6 evaluation protocol and 24-query candidate set (20 held out, 2 negative controls)
* Three-mode 72-request candidate pooling with 452 complete query/video rows and no explicit-mode fallback
* Non-authoritative relevant-video suggestions plus 10 authoritative raw-subtitle interval candidates
* Bounded 24-section Gold Review Packet and deterministic snapshot reproducibility evidence
* Seven focused Stage 6A tests and 506-test standard full-suite pass
* Validated amended 452-row Human Decision Ledger with only the authorized five-row review set touched
* Locked 24-query pooled Gold after all Part A eligibility, interval, R_title and U_title gates passed
* Snapshot-only Lexical / Dense / Hybrid / Auto formal evaluation with three stable measured repetitions per query and mode
* Discovery, Evidence, category, held-out, window, anchor, duplicate, grouping, router, latency and negative-control diagnostics
* Dense truncation, cross-language, AI Summary, unjudged-sensitivity and failure-case evidence reports
* Twelve focused Stage 6B tests and 518-test standard full-suite pass

## 8. Eval Status

```text
Locked Query Set: 24 rows
Gold: locked from the validated amended 452-row Human Decision Ledger
Candidate Pool: complete for Lexical / Dense / Hybrid on frozen Snapshot
Lexical discovery Recall@5 / Recall@10 / MRR: 0.349973 / 0.403274 / 0.500000
Dense discovery Recall@5 / Recall@10 / MRR: 0.783956 / 0.880141 / 1.000000
Hybrid discovery Recall@5 / Recall@10 / MRR: 0.783956 / 0.882035 / 1.000000
Auto discovery Recall@5 / Recall@10 / MRR: 0.777462 / 0.881629 / 1.000000
Failure analysis: delivered
Classification: Ready for Version Session Review with Follow-up
```

Formal Stage 6B evaluation is complete. It remains a pooled/judged Snapshot-only
evaluation and does not claim exhaustive relevance judgment over the live Product corpus.

## 9. Active Issues

1. Upstream Subtitle and Segment records still have no independent stable IDs or revision history; Stage 1 Chunk IDs are deterministic derivatives of provenance and content.
2. Cleaned transcript sections do not retain exact raw-segment lineage.
3. Summary chapters are not precise timestamp evidence.
4. Historical events are not consumed as an index queue; Stage 3 reconciliation derives desired state directly from current Product tables.
5. Bilibili timestamp-link behavior was tested end to end in Stage 5; broader platform/browser variation remains outside the current evidence.
6. Queries shorter than three characters use a documented substring fallback rather than FTS5/BM25.
7. A single upstream subtitle segment longer than the configured character or duration limit is preserved whole, so that unit may exceed the target bound.
8. Stage 6B Gold locking, formal metrics and failure analysis are delivered; Version Session decisions remain, including default-mode and evidence-window follow-up.
9. Historical BGE evidence showed identical query vectors for pure-ASCII `MCP`, `LangGraph`, `RAG` and `FAISS`. Qwen adoption resolved this collapse without adding rewrite or translation.
10. Standalone subtitle regeneration and favorite-folder title editing are `Not Currently Implemented`; Stage 3 did not create those Product features.

## 10. Internal Decisions

1. Raw subtitle segments are the authoritative V3 timestamp evidence source.
2. Cleaned transcript and Summary chapter content may contribute to Video-level search, but are not precise Evidence Units.
3. SQLite remains the primary local-first retrieval storage boundary.
4. SQLite FTS5 availability is a runtime prerequisite, not an existing product capability.
5. Taxonomy Workflow, Resume, Reviewer and Single-flight assets will not be directly reused as Product Search runtime.
6. Removed content is excluded by default.
7. Ignored content is excluded by default but may be explicitly included.
8. Archived content remains searchable by default.
9. No current condition requires Main-session escalation.
10. Video units may index title, uploader, description, summary, cleaned transcript, notes and active folder titles; only raw subtitle chunks provide precise timestamp evidence.
11. Chunking targets 800 characters, caps normal multi-segment chunks at 1,200 characters or 120 seconds, and overlaps one complete trailing segment.
12. `INDEX_VERSION` is `v3-stage1-lexical-v1`; rebuild metadata records the tokenizer and logical unit counts.
13. Index Meta counts represent current indexed rows, while `rebuilt_at` represents full-rebuild history and `updated_at` represents the latest count refresh.
14. Dense index version is `v3-dense-qwen3-0.6b-mrl512-v1`; projection version is `v3-dense-projection-qwen-v1`.
15. Hybrid fusion is unweighted RRF with `rrf_k=60`, `candidate_k=max(50, top_k*5)` and version `v3-stage2-rrf-v1`.
16. Long-context Embedding does not imply longer Evidence Chunks.
17. Video-level vectors represent global topic and high-value metadata.
18. Transcript Chunk vectors preserve short timestamped evidence windows.
19. Dense is intended primarily for Chinese or mixed natural-language semantic retrieval under the current model; Pure ASCII technical entities depend primarily on Lexical Retrieval.
20. Hybrid remains non-default before formal Retrieval Eval.
21. Timestamp Anchor Error is deferred to Retrieval Eval / Product Surface validation.
22. Product mutations invoke Retrieval synchronization only after their own database/artifact mutation returns; automatic hooks use a failure-isolated boundary.
23. Eligible synchronization order is Lexical replace then Dense replace; Lexical failure leaves Dense stale and unattempted.
24. Reconciliation enumerates current Videos and does not consume historical Events.
25. Qwen adoption replaced the prior BGE Pure ASCII entity-collapse baseline; Stage 4A nevertheless routes short ASCII entities to Lexical by explicit product policy.
26. Search mode defaults to `lexical`; `auto` is opt-in until formal Retrieval Eval evidence authorizes any default change.
27. `auto` routes `exact_entity` to Lexical and `mixed_entity`, `semantic_question` and `keyword_phrase` to Hybrid.
28. Only `auto`-planned Hybrid may fallback, and only for Dense-not-ready, Dense-rebuild-required or local-model-not-ready errors.
29. Stage 4A returns raw units only and does not group, reorder after retrieval, expand temporal context, create chapters or add jump behavior.
30. Stage 4B Product groups preserve the best Raw rank; Chunk count and summed scores never improve cross-Video rank.
31. Temporal windows merge only overlap or gaps up to 20 seconds and retain every component Unit ID/rank.
32. Exact/mixed/keyword anchors may use matching raw subtitle Segment starts; semantic questions always use best Chunk start fallback.
33. AI Chapters are auxiliary labels with derived boundaries; they do not affect retrieval, ranking, merging or jump time.
34. Raw Trace remains authoritative and Product Presentation Trace is additive, bounded and linked by the same `trace_id`.
35. ASCII technical entities require external ASCII letter/digit boundaries in both high-confidence anchor paths; generic `\b` and plain substring containment are not used.
36. `.NET` may match within `ASP.NET`, and `C++` may match `C++20`; these are explicit product semantics fixed by tests.
37. Chinese full-phrase and CJK keyword substring semantics remain unchanged by the ASCII boundary closure.
38. Stage 5 search UI consumes `POST /api/search` without client-side regrouping, window recomputation, ranking, or anchor calculation.
39. Stage 5 defaults remain `mode=lexical`, `scope=all`, `archived=false`, and `ignored=false`; Auto is optional and Hybrid remains non-default.
40. Product display metadata is loaded once per Product response after group selection and does not alter group or window order.
41. Exact/mixed/keyword anchor sources use precise play wording; `chunk_start_fallback` uses explicitly approximate related-window wording.
42. Raw and Product Presentation Trace data remain internal and are not exposed as a Web debug surface.
43. Stage 6 evaluation uses snapshot `20260720T094346Z_c7663365`; Live database pooling is forbidden.
44. `shiliu_eval.db` is the read-only corpus authority; `pool_work.db` is its trace-isolated writable derivative.
45. Stage 6 Gold is pooled/judged and must not be described as exhaustive judgment of every Product video.
46. Auto is a routing policy, not a fourth base retriever; its fixed oracle-gap definition is recorded in `research/v3_eval/V3_EVAL_PROTOCOL.md`.
47. The amended Human Decision Ledger is the authoritative Stage 6B judgment input; the original ledger remains immutable provenance.
48. Stage 6B formal metrics use the derived Eval work database only; Snapshot corpus rows and Live Product data remain unchanged.
49. V3 Closeout is not started and requires a separate Version Session decision.

## 11. Stage 6B Closure

```text
Stage 6B is Delivered and ready for Version Session review with follow-up.

Formal result:
- amended Human Ledger validation passed with 452 judgments and no out-of-scope changes;
- Gold Lock completed for 24 queries, including 104 R_evidence, 6 R_title, 337 N and 5 U_title judgments;
- Snapshot-only Lexical, Dense, Hybrid and Auto evaluation completed with stable repeated rankings;
- Dense and Hybrid materially exceeded Lexical discovery recall on the judged pool;
- negative-control nearest-neighbor behavior, broad evidence windows, weak anchor precision,
  Dense truncation causality and cross-language coverage remain follow-up evidence or product decisions;
- 12 focused Stage 6B tests and the 518-test standard full suite passed;
- Snapshot and Live Product/Index/Trace integrity remained unchanged.
```

No default-mode, Router, Retriever, Chunk, Embedding or Query change was made.
`V3_CLOSEOUT.md` has not been generated.

## 12. Stage 5 Closure

```text
Stage 5 is Delivered and ready for Version Session review.

Formal result:
- `/search` is reachable from shared navigation and uses the existing Product Search API;
- URL state, explicit modes/scopes, real Product filters, Back/Forward and refresh restoration passed;
- one backend result maps to one ordered video card with unchanged evidence windows;
- local detail navigation and real Bilibili timestamp navigation passed;
- safe rendering, stale-request protection, complete UI states and narrow layout passed;
- 14 focused Stage 5 tests passed;
- 499-test controlled full suite passed after removing invalid proxy environment variables;
- 1,555 Retrieval / FTS / Dense rows remain aligned;
- after the existing LaunchAgent startup sync settled, `/search` plus Product Search retained all Product Source hashes;
- the initial pre-launch hash comparison is separately disclosed because the existing LaunchAgent automatically synchronized favorite sources at startup;
- SQLite integrity_check is ok and foreign_key_check is empty;
- six real browser screenshots were captured.
```

Recommended classification is Accepted with Follow-up. Remaining follow-up is
limited to minor visual polish and Stage 6-only relevance, long-window and
Timestamp Anchor Error evaluation.

Default mode remains Lexical. Auto remains optional. Hybrid remains non-default.
Raw and Presentation Traces remain internal. Stage 6A and Stage 6B were subsequently delivered.

## 13. Stage 4B Closure

```text
Stage 4B is Accepted with Follow-up. Stage 5 was subsequently delivered.

Formal result:
- both `exact_query_phrase` and `exact_entity_term` use shared ASCII technical-entity boundary semantics;
- required negative, positive, symbol-ending and mixed-query integration fixtures passed;
- formal corpus probe found and rejected 7 embedded RAG, 398 embedded AI and 3 embedded MCP occurrences;
- RAG, AI, MCP, GPT-5, C++ and C# Product Search boundary smokes completed;
- 24 Product Presentation Traces are linked to Raw Trace IDs after the six allowed closure smokes;
- 1,555 Retrieval / FTS / Dense rows remain aligned;
- Product Source hashes unchanged;
- SQLite integrity_check ok and foreign_key_check empty;
- 75 enrichment tests passed;
- 485-test controlled full suite passed after removing an invalid environment-provided IPv6 `NO_PROXY` value.
```

Default mode remains Lexical. Auto remains optional. Hybrid remains non-default.
Search Web UI was delivered in Stage 5; formal Retrieval Eval was subsequently delivered in Stage 6B.

Remaining Stage 4B follow-up is limited to Timestamp Anchor Error evaluation,
long-duration Evidence Window presentation, and formal relevance evaluation.

## 14. Stage 4A Closure

```text
Stage 4A is Delivered and ready for Version Session review.

Default behavior:
- omitted mode -> lexical;
- explicit lexical/dense/hybrid -> exact requested retriever;
- auto exact ASCII entity -> lexical without constructing the Dense Provider;
- auto other supported types -> hybrid;
- approved Dense availability failure in auto hybrid -> lexical with fallback reason.

Formal result:
- 1,547 Retrieval / FTS / Dense rows remain aligned;
- 25-query formal routing/scope/filter matrix completed;
- real HTTP raw search and Trace lookup completed;
- real CLI auto search with Trace completed;
- 29 formal Search Traces persisted: 27 success and 2 bounded planning errors;
- Product Source hashes unchanged;
- SQLite integrity_check ok and foreign_key_check empty.
```

Stage 4B later added post-retrieval grouping, evidence windows, deterministic jump
anchors and auxiliary Chapter enrichment without changing this Raw Search boundary.

## 15. Stage 3 Lifecycle Closure

```text
Stage 3 is Delivered and ready for Version Session review.

Sync State semantics:
- desired `indexed` resolves to Lexical replace followed by Dense replace;
- desired `absent` removes Lexical, FTS, Dense, folder and metadata rows;
- failures retain explicit lexical/dense state and bounded error metadata;
- automatic hooks do not turn Retrieval failure into Product mutation failure.

Reconciliation behavior:
- enumerates all current Videos;
- repairs missing/stale rows without Event consumption or full Dense rebuild;
- repeats idempotently and reuses unchanged embeddings.

Formal result:
- 143 Videos examined;
- 142 indexed and 1 absent;
- 1,547 Retrieval / FTS / Dense rows;
- second unchanged reconcile embedded 0 and reused 1,547;
- no remaining sync failures.
```

Delivered Product Hook coverage includes:

* new favorite Video completed;
* subtitle-only completion;
* ASR completion;
* summary refinement;
* Note create/update/delete;
* Membership add/remove;
* last active Membership removal;
* subtitle regeneration;
* removed Video cleanup.

Not Currently Implemented Product mutation paths:

* standalone subtitle regeneration action;
* favorite-folder title editing action.

## 16. Deviations

1. FTS5 `trigram` cannot match one- or two-character queries, so Stage 1 provides an explicit case-insensitive substring fallback with retrieval method `lexical_substring_fallback` and score `0.0`.
2. Whole-segment provenance takes precedence over hard splitting; an indivisible oversized upstream segment may exceed normal chunk bounds.
3. First formal Hybrid request included Qwen lazy load and took approximately 4.65 seconds; subsequent formal Hybrid requests were approximately 48–83 ms in the observed run.

## 17. Escalations

None.

## 18. Remaining Time Budget

```text
Original target: 18–24 effective hours
Estimated Phase 0 use: approximately 1–1.5 hours
Estimated Stage 1 use: approximately 2–2.5 effective hours
Estimated Closure Fix use: approximately 1–1.5 effective hours
Estimated Stage 3 use: approximately 3–4 effective hours
Estimated remaining V3 target budget: approximately 8.5–17 hours
```
