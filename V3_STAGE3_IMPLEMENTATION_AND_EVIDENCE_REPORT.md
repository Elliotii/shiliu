# Shiliu V3 Stage 3 Implementation and Evidence Report

## 1. Scope and Integrity

**Confirmed Fact** — This execution implemented only Stage 3 Product Mutation Lifecycle / Index Consistency. It did not change the embedding model, Projection V2, chunking, timestamp boundaries, FTS tokenizer, RRF, Product Search API/UI, or consume historical Events.

**Confirmed Fact** — Work was performed on `codex/v3-domain-completion` at baseline HEAD `4673a8f`. Pre-existing Stage 1/2 changes and reports were preserved.

**Confirmed Fact** — Formal Product content tables and source state were not changed. SHA-256 snapshots before and after formal reconciliation were identical:

| Table | Rows | SHA-256 |
| --- | ---: | --- |
| `videos` | 143 | `58f2832addddff3c134513f16a88686046c438a77750013c4b91e2c8acb206ec` |
| `video_notes` | 1 | `a9632c951c83bdc9ba9013a419bd733f50cad29e520d1ea6bf345930d3a4a7c9` |
| `favorite_sources` | 2 | `370ffccb18020fbfed20fa9f7c0e8868bbf7df55aedbc8ef7f4c2f940162532d` |
| `video_source_memberships` | 145 | `2f10d9abb273b6d5757fa214f6792c8fd047d8fd90174100eec83523210b118e` |
| `events` | 271 | `26afafa8edae6ce32f8983c9c571e76ac6d1996d8b92dbe85bb68cca715af5ec` |

## 2. Read-only Mutation Map

The required Mutation Map was completed before Stage 3 code edits.

| Product mutation | Actual owner / function | Commit boundary observed | Retrieval consequence |
| --- | --- | --- | --- |
| New source subtitle / metadata | `src/shiliu/pipeline.py` · `PipelineService._fetch_source` | Artifact writes and `Database.update_video()` complete before return | Replace Video and subtitle Chunk units |
| Subtitle-only completion | `PipelineService.process_video` | `videos.status=completed` committed first | Ensure eligible Video is indexed |
| Clean transcript | `PipelineService._run_transcript_stage` | transcript artifact, stage row and Video row complete first | Replace Video projection |
| Summary completion | `PipelineService._run_summary_stage` | summary artifact, stage, Video and Event writes complete first | Replace Video projection |
| Summary refinement | `PipelineService._run_refinement_review_stage` | refined artifacts, stage, Video and Event writes complete first | Replace Video projection |
| ASR subtitle completion | `src/shiliu/asr.py` · `ASRService._complete` | ASR/raw-subtitle artifacts, ASR job and Video update complete first | Replace Video and Chunk units |
| Note CRUD / reading / mark / archive | `src/shiliu/library.py` · `LibraryService` methods | corresponding `Database` method returns first | Replace Video metadata/projection |
| Ignore / restore | `LibraryService.set_ignored`, called by Web | Video state committed first | Replace visibility metadata |
| Membership baseline / snapshot / history materialization | `src/shiliu/sync.py` · `SyncService` | membership operation returns first | Sync affected Video IDs |
| Source add / pause / resume / removal | `src/shiliu/web.py` handlers | source or membership mutation returns first | Sync affected Video IDs; cleanup last membership |
| Legacy current-item reconciliation | `SyncService._sync_legacy` | Product reconciliation returns first | Sync affected current Videos |

**Confirmed Fact** — Product database mutations commit through separate `Database.connect()` scopes. Artifact and database writes do not share one transaction. Hooks were therefore installed after the last successful Product mutation in each current owner.

**Not Currently Implemented** — There is no standalone subtitle-regeneration Product action and no favorite-folder title editing Product action. Stage 3 did not invent either feature.

## 3. Coordinator Architecture

**Confirmed Fact** — `src/shiliu/retrieval/coordinator.py:61` adds `RetrievalIndexCoordinator` with:

```text
sync_video(video_id, trigger)
safe_sync_video(video_id, trigger)
remove_video(video_id, trigger)
reconcile_video(video_id, trigger)
reconcile_all()
retry_failed()
status()
```

Eligible order is:

```text
Product state already committed
→ lexical.replace_video(video_id)
→ dense.replace_video(video_id)
→ retrieval_sync_state update
→ bounded structured log/result
```

Absent order is Lexical/FTS/folder cleanup followed by Dense metadata refresh and sync-state recording.

**Confirmed Fact** — `RetrievalService.replace_video` now upserts stable `unit_id` rows and deletes only stale IDs. This prevents the Dense foreign-key rows for unchanged units from being needlessly cascade-deleted and makes embedding reuse real rather than nominal.

## 4. Sync State Schema

**Confirmed Fact** — Additive table `retrieval_sync_state` has one row per Video and a foreign key to `videos(id) ON DELETE CASCADE`. Key fields are:

```text
video_id PRIMARY KEY
sync_state_version = v3-stage3-sync-state-v1
desired_state = indexed | absent
lexical_state
dense_state
last_trigger
last_attempt_at
last_success_at
last_error_stage
last_error_message
updated_at
```

Error text is limited to 500 characters. Subtitle bodies, Note bodies, Summary bodies, credentials and vectors are never stored in sync state or logs.

## 5. Hook Coverage Matrix

| Product mutation | Actual owner | Hook installed | Test | Result |
| ---------------- | ------------ | -------------: | ---- | ------ |
| New Video source/subtitle completion | `PipelineService._fetch_source` | Yes, line 292 | lifecycle Pipeline test | Pass |
| Subtitle-only completion | `PipelineService.process_video` | Yes, line 113 | lifecycle subtitle-only test | Pass |
| Clean transcript completion | `PipelineService._run_transcript_stage` | Yes, line 440 | lifecycle Pipeline test | Pass |
| Summary completion | `PipelineService._run_summary_stage` | Yes, line 531 | lifecycle Pipeline test | Pass |
| Summary refinement | `PipelineService._run_refinement_review_stage` | Yes, line 694 | lifecycle refinement test | Pass |
| ASR completion | `ASRService._complete` | Yes, line 330 | lifecycle ASR replacement test | Pass |
| Note create/update/delete | `LibraryService` | Yes | lifecycle Library mutation test | Pass |
| Reading / mark / archive / ignore | `LibraryService` and Web | Yes | lifecycle Library mutation test | Pass |
| Membership baseline/snapshot | `SyncService._sync_sources` | Yes, lines 199/211 | full suite plus source lifecycle test | Pass |
| History membership materialization | `SyncService._process_history_backlog` | Yes, line 336 | full suite | Pass |
| Source add/pause/resume/remove | Web handlers | Yes, lines 505/525/534/573 | lifecycle Web source test | Pass |
| Last active Membership removal | Sync/Web + coordinator eligibility | Yes | lifecycle cleanup/source test | Pass |
| Legacy current-items reconciliation | `SyncService._sync_legacy` | Yes, line 440 | full suite | Pass |
| Standalone subtitle regeneration | No current Product owner | No | Not Currently Implemented | N/A |
| Favorite-folder title editing | No current Product owner | No | Not Currently Implemented | N/A |

## 6. Post-commit and Failure Semantics

**Confirmed Fact** — Automatic Product owners call `safe_sync_video` only after their Product write returns. This boundary catches unexpected Retrieval exceptions and preserves the Product result.

**Confirmed Fact** — Failure state rules are implemented and tested:

| Failure | Lexical state | Dense state | Dense attempted |
| --- | --- | --- | ---: |
| Lexical exception | `error` | `stale` | No |
| Dense not initialized | `current` | `not_ready` | Yes |
| Dense version/config mismatch | `current` | `rebuild_required` | Yes |
| Other Dense/provider exception | `current` | `error` | Yes |

**Confirmed Fact** — Runtime logs contain Video ID, trigger, desired state, Lexical/Dense status, duration, index versions and error stage. They exclude user content and vectors.

## 7. Reconciliation and CLI

Delivered commands:

```text
shiliu retrieval sync-video <video_id>
shiliu retrieval sync-status
shiliu retrieval retry-failed
shiliu retrieval reconcile
```

`retry-failed` retries only Lexical `error` or Dense `error`/`stale`; it does not silently perform a full Dense rebuild. `reconcile` enumerates current Videos and derives desired state from Product tables, not Events.

Formal CLI demonstrations:

* `sync-status`: exit 0, initial state count 0 before reconciliation.
* `reconcile`: exit 0 twice.
* `sync-video 1`: exit 0; 1 Video unit + 3 Chunk units; embedded 0; reused 4.
* `retry-failed`: exit 0; attempted 0 after clean reconciliation.

## 8. Stable Model Cache

**Confirmed Fact** — Formal default cache path is:

```text
/Users/elliot/Library/Caches/Shiliu/fastembed
```

The existing 91 MB `BAAI/bge-small-zh-v1.5` cache was copied from the prior macOS temporary cache. No model was downloaded, switched or rebuilt. Custom/test `AppPaths` use `<state_dir>/fastembed-cache`, and `SHILIU_FASTEMBED_CACHE_DIR` can explicitly override it.

**Confirmed Fact** — `Application` construction and Lexical-only rebuild/search paths do not construct the FastEmbed model. `FastEmbedEmbeddingProvider._get_model` remains lazy.

## 9. Automated Tests

Required command results:

| Exact command | Exit | Passed | Failed | Skipped | Warnings |
| --- | ---: | ---: | ---: | ---: | --- |
| `.venv/bin/python -m pytest tests/test_retrieval.py -q` | 0 | 13 | 0 | 0 | none |
| `.venv/bin/python -m pytest tests/test_dense_retrieval.py -q` | 0 | 9 | 0 | 0 | none |
| `.venv/bin/python -m pytest tests/test_retrieval_lifecycle.py -q` | 0 | 13 | 0 | 0 | one existing Starlette/httpx deprecation warning |
| `.venv/bin/python -m pytest -q` | 0 | 323 | 0 | 0 | Starlette/httpx deprecation plus six multiprocessing fork deprecations |

The lifecycle suite uses temporary SQLite, temporary artifacts, a deterministic fake embedding provider and temporary/overridden cache paths. It performs no network call or model download.

## 10. Formal Reconcile Evidence

Before formal schema initialization, SQLite backup was created from the required read-only URI:

```text
file:/Users/elliot/Library/Application Support/Shiliu/shiliu.db?mode=ro
```

On the copy, additive schema initialization left all prior Retrieval counts and both metadata rows byte-for-byte logically unchanged:

```text
Retrieval Units: 1547 → 1547
FTS rows:        1547 → 1547
Dense rows:      1547 → 1547
Lexical version: v3-stage1-lexical-v1
Dense version:   v3-stage2-dense-bge-small-zh-v1
Projection:      v3-dense-projection-v2
integrity_check: ok
foreign_key_check: []
```

Formal first reconciliation:

```text
Videos examined: 143
desired indexed: 142
desired absent/not eligible: 1
successful syncs: 143
failed: 0
lexical failures: 0
dense failures: 0
not_ready: 0
rebuild_required: 0
new embeddings: 0
reused embeddings: 1547
duration: 3.392756 seconds
```

Formal second unchanged reconciliation:

```text
Videos examined: 143
successful syncs: 143
failed: 0
new embeddings: 0
reused embeddings: 1547
duration: 3.409713 seconds
```

Final consistency:

```text
Retrieval Units: 1547
FTS rows: 1547
Dense rows: 1547
duplicates: 0
metadata without FTS: 0
FTS without metadata: 0
Retrieval Units without Dense: 0
Dense rows without Retrieval Units: 0
damaged vectors: 0
integrity_check: ok
foreign_key_check: []
```

Sync-state distribution after the two reconciliations:

```text
indexed / current / current: 142
absent / absent / absent: 1
```

## 11. Partial-failure Demonstrations

**Confirmed Fact** — Automated controlled failures demonstrate:

* Lexical exception prevents Dense execution and records `error/stale`.
* Dense provider exception leaves Lexical current and records Dense `error`.
* Dense-not-ready and rebuild-required remain distinct states.
* Error text is truncated to 500 characters.
* Product Library mutation values remain committed when Retrieval uses its failure-isolated boundary.
* Reconciliation repairs intentionally deleted FTS and Dense rows without duplicates or damaged vectors.
* ASR subtitle replacement deletes stale Chunk IDs and creates new deterministic Chunk IDs.

## 12. Remaining Limitations

**Risk** — Direct ad hoc calls to low-level `Database` mutation methods outside the identified Product owners can bypass hooks. Current application owners are covered; Stage 3 did not add a generic workflow or database callback framework.

**Not Currently Implemented** — Standalone subtitle regeneration and favorite-folder title editing have no Product path to hook.

**Observation** — Current Dense model has Pure ASCII entity collapse. Model Selection Gate follows Stage 3, remains Not Started, and no model experiment was performed here.

**Observation** — Hybrid remains non-default. Timestamp Evidence Chunk boundaries remain frozen.

## 13. Version State

```text
Stage 2: Accepted with Follow-up
Stage 3: Delivered
Ready for Version Session Review
Model Selection Gate: Not Started
```

Recorded Stage 3 effort is estimated at approximately 3–4 effective hours; no independent task timer was available. Estimated remaining V3 target budget is approximately 8.5–17 hours.

## 14. Recommended Classification

**Recommendation — Accepted for Stage.** Stage 3 implementation and formal evidence meet the controller requirements. This Codex recommendation does not represent final Version Session acceptance.

## 15. Stop Boundary

**Confirmed Fact** — Work stops here. Model Selection Gate, Qwen/e5 experiments, Stage 4, formal Retrieval Eval, Query Understanding, Search API/UI and timestamp-anchor refinement were not started.
