# V3 Current Capability and Reuse Matrix

Date: 2026-07-19
Scope: local code and frozen research artifacts only. “Implemented” does not mean “available to product users.”

Allowed status vocabulary: `production-used`, `implemented-not-product-integrated`, `research-only`, `partial`, `planned-only`, `not-implemented`.

| Capability | Implementation / evidence | Status | Directly reusable | Modification required | Research-only boundary |
|---|---|---|---|---|---|
| Video synchronization | `src/shiliu/sync.py::SyncService`, `ProcessLock`; `src/shiliu/bilibili.py::BilibiliAdapter` | production-used | source discovery, membership updates, scheduling and locking | any new metadata flow needs explicit migration and UI policy | no |
| Subtitle input | `src/shiliu/bilibili.py`; subtitle stages in `src/shiliu/pipeline.py::PipelineService` | production-used | subtitle fetch and normalized pipeline input | provider/source-specific edge cases remain | no |
| ASR input | `src/shiliu/asr.py::ParaformerProvider`, `ASRService`; manual web entry in `src/shiliu/web.py` | production-used | asynchronous ASR submission, polling, language detection | automation policy and regional endpoint behavior remain operational concerns | no |
| Transcript cleanup | `src/shiliu/prompts.py::build_transcript_prompt`; transcript stages in `PipelineService` | production-used | structured transcript cleanup and Markdown rendering | no Taxonomy dependency is needed | no |
| Structured summary | `src/shiliu/prompts.py::build_summary_prompt`; `src/shiliu/artifacts.py::render_summary_markdown` | production-used | one-line conclusion, key points, detailed notes, entities/links | schema changes require backward-compatible migration | no |
| Classification Profile | `src/shiliu/taxonomy/profiles.py::ClassificationProfileService` | research-only | compact semantic representation and pollution checks | needs a product lifecycle, persistence policy, and incremental update contract | yes; generated for controlled research cohorts |
| Domain Discovery | `src/shiliu/taxonomy/discovery.py`, `domain_stability.py`, `domain_completion.py` | research-only | batching, candidate schemas, normalization and audit patterns | no published Taxonomy or incremental product path exists | yes |
| Controlled Facets | `src/shiliu/taxonomy/controlled_facets.py`, `controlled_facets_completion.py` | research-only | vocabulary schemas, assignment validation, dynamic faceting calculations | not connected to user data or front-end filters | yes |
| Entity / Topic structures | summary schema plus candidate/facet models under `src/shiliu/taxonomy/` | partial | entity extraction fields and research candidate types | no shared canonical product store, lifecycle, merge, or correction model | research artifacts exist; product semantics do not |
| Evidence Contract | `docs/adr/ADR_V3_DOMAIN_STABILITY.md`; M1/M2/M3 contracts and manifests | research-only | provenance, evidence maturity, non-Domain routing rules | must be simplified or adapted to whichever future product contract is chosen | yes |
| Taxonomy storage | `taxonomy_corpus_snapshots`, `taxonomy_classification_cards`, `taxonomy_runs`, `taxonomy_stage_runs` in `src/shiliu/db.py`; local runtime JSON artifacts | partial | snapshot, card, run and stage persistence | no product tables for published versions, nodes, edges, assignments, corrections, or migrations | Drafts remain local research artifacts |
| Assignment Schema | `src/shiliu/taxonomy/discovery.py::TrialAssignment`, `TrialAssignmentOutput`; controlled-facet assignment models | research-only | validation and batch prompt patterns | Run #24 M6 has not started; no final 131-card assignment or product persistence | yes |
| Search | no FTS5, dense index, reranker, transcript retrieval, or query service found in `src/shiliu` | not-implemented | none beyond existing SQL lookup and description URL display | a separate indexing/query contract would be required | no research implementation to promote |
| Front-end filtering | feed/Mark/notes/archive filters in `src/shiliu/db.py` and `src/shiliu/static/library.js`; snapshot UI in `taxonomy.js` | partial | current library-state filters and snapshot preview | no Domain, Topic, Entity, or semantic search filters | Taxonomy page only previews/freezes corpus snapshots |
| User modification records | `src/shiliu/library.py::LibraryService` for reading state, Mark, archive, ignore, and notes | partial | content-level user state and notes | no Taxonomy rename/merge/move/correction history or AI-vs-user precedence model | no taxonomy correction capability |
| Provider workflow | OpenAI-compatible Provider wiring in `src/shiliu/app.py`; production summary/transcript roles | production-used | settings, role routing, retries, structured output | research role count and reasoning policy should not be assumed as product defaults | taxonomy usage is research-only |
| Audit / trace | pipeline stages in DB; `src/shiliu/taxonomy/model_calls.py::AuditedJsonCaller`; raw-first artifacts and manifests | partial | usage, hashes, raw response, validation and repair evidence | two audit systems are not a single user-facing operational view; some historical usage is unknown | taxonomy trace is local research infrastructure |
| Resume | production pipeline retry stages; `src/shiliu/taxonomy/workflow.py`, `run_repository.py` | partial | completed-unit reuse and stage recovery | taxonomy resume is CLI/research workflow, not product UI | yes for Domain Completion |
| Single-flight / attempt lease | `src/shiliu/taxonomy/provider_single_flight.py` | implemented-not-product-integrated | atomic lease, heartbeat, immutable response ledger, conservative takeover | production summary pipeline has separate locking/retry semantics; cross-host takeover remains manual | built to protect research Provider calls |
| Eval foundation | `eval/ANTI_CONTAMINATION.md`, `eval/protocols/silver_eval_protocol_v1.yaml`, `eval/silver_generator.py`, `eval/freeze_silver_reference.py` | research-only | isolation contracts, protocol, generator, frozen-hash pattern | Silver is not Gold or true accuracy; no product acceptance loop exists | yes |
| Snapshot preview / freeze | `src/shiliu/taxonomy/corpus.py`, `repository.py`; `templates/taxonomy.html`, `static/taxonomy.js` | implemented-not-product-integrated | immutable corpus selection, A/B/C/D accounting, duplicate collapse | UI is an experiment control surface, not a browsing/classification feature | yes |
| Related-content retrieval | existing `related_links` only preserves URLs from video descriptions | not-implemented | URL extraction is reusable but is not semantic related content | retrieval/ranking/indexing would be new work | no |
| Published Taxonomy lifecycle | no published version, active node, migration, or rollback store found | not-implemented | frozen Draft/manifest patterns may inform it | full product data model required if ever authorized | current Draft A is not published |

## Reusable module boundaries

- **Stable product ingestion:** `BilibiliAdapter → SyncService → PipelineService → ArtifactStore`. Taxonomy experiments should consume frozen outputs rather than modify this chain implicitly.
- **User content state:** `LibraryService` and the existing video tables own reading, Mark, archive, ignore, and notes. These fields were intentionally excluded from semantic cards.
- **Frozen corpus boundary:** `taxonomy/corpus.py` and `taxonomy/repository.py` own snapshot/card creation. Stored cards and model-facing views are distinct.
- **Research workflow boundary:** `TaxonomyWorkflow`, `DomainCompletionService`, `TaxonomyRunRepository`, and local run artifacts own experiment stages and recovery. They do not publish product metadata.
- **Provider safety boundary:** `AuditedJsonCaller` handles raw-first structured calls; `ProviderSingleFlight` prevents duplicate requests for a specific run/stage/unit/attempt/request kind.
- **Eval isolation boundary:** `eval/` may read private Silver artifacts; Discovery runtime must not import or read them.

## Current engineering debt and constraints

1. Run #24 is recoverable, but no product authorization exists for M6. State-machine readiness must not be treated as a queue instruction.
2. Draft A is broad: 20 of 25 nodes are top-level, 0 are stable, and there is no full-assignment evidence. Any consumer must preserve that uncertainty.
3. Taxonomy outputs live primarily as local JSON/Markdown artifacts. There is no published-version or assignment persistence contract.
4. Research schemas overlap but do not form a canonical product metadata model for Domain, Topic, Entity, Object, and Use Context.
5. The current Taxonomy web page is only a snapshot control surface. No semantic browsing, correction, or filter UI exists.
6. Search, timestamp retrieval, related-content ranking, and recommendation are not implemented; description links must not be mistaken for them.
7. Silver evaluation infrastructure is isolated research tooling and must never be called Gold, ground truth, or true accuracy.
8. Historical Provider audit has one Draft A Repair response with unknown usage and a documented duplicate-call incident. The immutable ledger preserves rather than erases this fact.
9. Single-flight is local-filesystem based. If a lease is stale but owner liveness is unclear, recovery intentionally stops for manual audit.
10. Product and research pipelines share Provider configuration but not a unified operational dashboard or unified retry policy.

## Handoff statement

V3 产品形态与后续路线尚未决定，等待用户与规划 AI 在 Taxonomy 收口后重新讨论。
