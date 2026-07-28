# Shiliu V3 Stage 6A Recovery, Corpus Freeze, and Gold Candidate Report

## 1. Scope and Stop Boundary

**[Fact]** This execution performed only Stage 6A recovery, corpus freezing, protocol definition, candidate-query construction, three-mode pooling, non-authoritative relevance/interval suggestions, review rendering, and verification. It did not calculate final Recall/MRR/Hit metrics, lock Gold, compare retriever quality, change routing/retrieval/product behavior, create `V3_CLOSEOUT.md`, or enter Stage 6B.

## 2. Deleted-session Recovery Method

State was recovered only from the current repository, Git working tree, formal database/artifacts, `V3_CURRENT_STATE.md`, landed evidence reports, source, tests, LaunchAgent state, and runtime checks. No deleted Codex conversation was reconstructed. The two authority files were absent during the initial recovery search and were added by the user mid-execution; both were then read completely before closure.

**[Decision]** The added Brief/Contract do not change the more recent Stage 6A stop boundary. Their original version-level Query Rewrite aspiration is superseded for this stage by the later accepted Stage 4A deterministic Planner and the explicit prohibition on modifying it.

## 3. Git and Working-tree Audit

Starting repository facts:

```text
root: /Users/elliot/new-systems/agent-job-prep/Shiliu
branch: codex/v3-domain-completion
HEAD: 8287c8d feat: deliver V3 retrieval through stage 4B
upstream relation: ahead 1
working tree: dirty
cached diff: empty
```

Pre-existing changes were the Stage 5 work in `V3_CURRENT_STATE.md`, Retrieval Product metadata, Web/template/static files, Stage 5 tests/evidence, and related untracked files. The user later added `00_V3_RETRIEVAL_VERSION_BRIEF.md` and `01_V3_SESSION_OPERATING_CONTRACT.md`. All were preserved. No checkout, reset, restore, clean, stash, commit, or branch switch was performed.

Stage 6A additions are confined to `src/shiliu/eval/`, four `tests/test_eval_*.py` files, `research/v3_eval/`, this report, and the authorized current-state update.

## 4. Required Reading and Recovered State

Read in the required order, using actual repository names: `AGENTS.md`, `V3_CURRENT_STATE.md`, the two authority files when supplied, Stage 5, Stage 4B closure, Stage 4B implementation, and Stage 4A reports. Model Selection, Model Adoption, post-cutover, and Stage 3 reports were read only to verify model/lifecycle facts.

Recovered accepted state: Phase 0 through Stage 5 are accepted with their recorded follow-ups; Qwen is the formal Dense model; lexical remains default; Auto remains optional; Hybrid remains non-default; formal retrieval quality metrics and locked Gold do not exist.

## 5. Existing Eval Asset Audit

- `eval/private_reference/candidate_videos_snapshot_2.jsonl` has 131 rows and belongs to frozen Taxonomy Silver evaluation, not Retrieval Eval.
- `silver_eval_set_40.jsonl`, the Silver taxonomy/protocol, disagreements, generator, and freeze scripts explicitly deny Gold/Ground-Truth status and remain isolated from Product Search.
- `research/v3_model_selection/qwen_retrieval_comparison.md` contains a prior single-Codex model-selection comparison, not a locked Retrieval Eval query/gold set.
- Existing search traces can be read through `GET /api/search/traces/{trace_id}` and CLI trace output; no pre-existing bulk Retrieval Eval exporter existed.
- Existing metric code concerns Taxonomy/Silver workflows; no formal Retrieval Recall/MRR/Hit implementation or Retrieval Gold existed.

No existing asset was overwritten or reclassified as Retrieval Gold.

## 6. Current Retrieval Identity

```text
Lexical index: shiliu_lexical / v3-stage1-lexical-v1
FTS tokenizer: trigram
Dense model: Qwen/Qwen3-Embedding-0.6B
Revision: 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3
Provider: v3-qwen3-embedding-provider-v1
Dimension/dtype: 512 / normalized float32
Embedding mode: mrl-first-512-normalized
Projection: v3-dense-projection-qwen-v1
Query instruction: v3-qwen-query-instruction-v1
Input policy: v3-qwen-input-512-v1
Dense index: v3-dense-qwen3-0.6b-mrl512-v1
Fusion: v3-stage2-rrf-v1; rrf_k=60; candidate_k=max(50,top_k*5)
```

Database Meta and source constants agree.

## 7. Current Corpus and Product Surface

Settled Live baseline:

```text
videos: 144
indexed videos: 143
absent videos: 1
retrieval units: 1,555
video units: 143
transcript chunks: 1,412 across 129 videos
FTS rows: 1,555
Dense rows: 1,555
sync-state rows: 144
Raw Search Traces: 82
Presentation Traces: 52
raw subtitle paths declared: 130
summary paths declared: 103
integrity_check: ok
foreign_key_check: 0 rows
```

The audited Product surface exists at `POST /api/search/raw`, `POST /api/search`, `GET /search`, and `GET /api/search/traces/{trace_id}`. `ProductSearchService`, `SearchResultConsolidator`, and `EvidenceEnricher` remain the shared Product composition. Stage 6A changed none of them.

## 8. Runtime Writer Map

`app.shiliu.sync` is an enabled hourly LaunchAgent (`StartInterval=3600`) invoking `python -m shiliu sync --scheduled`. `app.shiliu.web` is an enabled/running LaunchAgent whose Web routes can start manual sync, refinement, ASR, source lifecycle, and Library mutations. `SyncService` and `PipelineService` can change Product rows/artifacts and invoke `RetrievalIndexCoordinator`. No separate worker/pipeline process was running. `sync_runs` had no active row and the process lock was available.

## 9. Corpus Freeze Procedure

The required sequence was followed:

1. record loaded/enabled/running state and process IDs;
2. do not restart Web;
3. disable only the scheduled Sync LaunchAgent;
4. suspend the existing Web PID with `SIGSTOP` so writer endpoints cannot execute;
5. confirm no active sync, no sync process, and acquire/release the sync lock;
6. compute settled Live counts/hashes;
7. use Python SQLite Backup API to create the snapshot;
8. copy bounded lightweight artifacts and rebind only the snapshot;
9. validate integrity, foreign keys, counts, hashes, and path isolation;
10. resume the same Web PID with `SIGCONT` and re-enable scheduled Sync;
11. use only the snapshot-derived `pool_work.db` for all subsequent search.

## 10. Service State Before/During/After

| Service | Before | During | After |
|---|---|---|---|
| Web | enabled, running PID 39119, run count 5 | same PID suspended | same PID resumed, no restart, run count 5 |
| Sync | enabled, loaded, not running, run count 11 | disabled, not running | enabled, loaded, not running, run count 11 |
| Active sync | none | none; lock available | none |

Restoration matched the starting state.

## 11. SQLite Snapshot

```text
snapshot_id: 20260720T094346Z_c7663365
base DB: /Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/shiliu_eval.db
writable trace copy: /Users/elliot/Documents/Shiliu/eval/v3_stage6/20260720T094346Z_c7663365/pool_work.db
base SHA-256: 61589a5b64e9c9e6e5356d33baa6054aa435722e186066501a3213e8e9a6c4e1
```

`shiliu_eval.db` is read-only at the filesystem level. `pool_work.db` was also created through Backup API and contains all candidate-pool/reproducibility traces. Live trace counts stayed 82/52. The immutable snapshot contains no Live artifact absolute path references.

## 12. Artifact Snapshot

Only JSON required by Stage 6 Product evidence was copied:

```text
authoritative raw subtitles: 129 ok; 14 not declared
active summary JSON: 102 ok; 41 not declared
metadata JSON: 141 ok; 2 not declared
missing or malformed copied artifacts: 0
```

The undeclared raw-subtitle rows are Video-only indexed items and have no transcript chunks. No video, audio, cover, model weight, or historical summary revision was copied. Snapshot `raw_subtitle_path`, `summary_path`, and `artifact_dir` point into the frozen artifact root; transcript/cover paths were cleared, and the one non-indexed Product row had all Live artifact paths cleared.

## 13. Corpus Manifest

`research/v3_eval/corpus_manifest.json` records snapshot/Git/model/retrieval identities, counts, Live protected-table hashes, artifact counts, path-rebinding status, and service states. `artifact_manifest.jsonl` contains one bounded record per indexed-video artifact type with Live path, snapshot path, SHA-256, size, and status; it contains no subtitle or summary body.

## 14. Snapshot Integrity and Reproducibility

Snapshot checks passed: `integrity_check=ok`, zero foreign-key violations, and `1,555 = 1,555 = 1,555` Retrieval/FTS/Dense alignment.

Repeated cases on one snapshot returned identical ordered Product video IDs, Raw unit IDs, plans, and executed modes:

| Query | Mode | Product count | Raw unit count | Stable |
|---|---|---:|---:|---|
| MCP | lexical | 20 | 75 | yes |
| RAG | dense | 20 | 100 | yes |
| 为什么复杂 Agent 使用 DAG Workflow 而不是 ReAct 循环？ | hybrid | 20 | 100 | yes |
| vibe coding + `marked=true` | lexical | 1 | 1 | yes |

## 15. Eval Protocol

`research/v3_eval/V3_EVAL_PROTOCOL.md` fixes the snapshot-only corpus, Pooled/Judged Gold disclaimer, three explicit base retrievers, Auto separation, 24-query gate, metrics, intervals, warm-runtime controls, and no-tuning rule. Stage 6A generated no final metric values.

## 16. Metric Definitions

The protocol precisely defines Pooled/Judged Video Recall@5/@10, MRR@10, Hit@1/@5/@10, Zero-result Rate, warm P50/P95, duplicate occupancy count/rate @10/@20/@50, Unique Video Recall@10, Grouping Gain@10, Relevant Window Found@1/@2, duration distribution, overbreadth, precise-anchor error, semantic chunk-navigation error, filter violations, and a fixed two-component Auto Oracle Gap based on lexicographic `(Recall@10, MRR@10)`.

## 17. Candidate Query Design

The 24 candidates cover exact entities, mixed entity intent, natural questions, evidence lookup, real structured metadata filters, and favorite-time filters. Only four are non-held-out anchors. No natural-language filter parsing or unsupported filter was introduced.

## 18. Query Distribution

| Category | Count |
|---|---:|
| Exact Entity | 5 |
| Mixed Entity | 4 |
| Semantic Topic / Question | 5 |
| Evidence Lookup | 4 |
| Metadata Filter | 3 |
| Temporal Filter | 3 |
| Total | 24 |

## 19. Held-out and Negative-control Queries

Twenty queries are held out. Negative controls are Q14 (quantum error-correction surface-code threshold) and Q18 (Kubernetes Pod `CrashLoopBackOff` troubleshooting). Corpus search found zero units containing `量子纠错`, `表面码`, or `CrashLoopBackOff`. One general Kubernetes mention was manually inspected and rejected because it discusses orchestration/scale/failure recovery, not Pod troubleshooting. Final negative status still requires human approval.

## 20. Candidate Pooling Method

Each query ran explicit Lexical, Dense, and Hybrid with `result_limit=20`, `max_windows_per_video=5`, identical scope/filters, and the same snapshot-derived DB. The union was deduplicated by `query_id + video_id`; mode ranks, mode overlap, matched-unit/window counts, and at most two 300-character evidence windows were retained. No candidate was removed before the complete JSONL was written.

## 21. Candidate Pool Statistics

```text
requests: lexical 24, dense 24, hybrid 24
fallbacks: 0
complete pooled query/video rows: 452
per-query range: 1–32 candidates
pool build duration: 7.358 s
cold Qwen load: 4,073.452 ms (operational only)
provider loads: 1; device: MPS
warm lexical P50/P95: 8.536 / 73.048 ms
warm dense P50/P95: 129.148 / 354.711 ms
warm hybrid P50/P95: 120.737 / 187.199 ms
```

These are preparation observations, not final quality metrics or an SLA.

## 22. Gold Candidate Suggestions

`eval_gold_candidates.jsonl` has 24 `candidate_review_required` rows. `eval_pool_candidates.jsonl` labels are limited to `likely_relevant`, `possibly_relevant`, `likely_not_relevant`, or `uncertain`, with explicit non-authoritative rationales. No `relevant_video_ids` lock and no `eval_gold.locked.jsonl` exists.

## 23. Interval Gold Candidates

Ten queries (Q01–Q04, Q06–Q08, Q10, Q15, Q17) have interval candidates. Every interval records video ID, raw segment index range, exact raw `from/to` boundary, bounded evidence, `source=authoritative_raw_subtitle`, and `status=candidate`. AI chapter starts and summary-derived times were not used.

## 24. Gold Review Packet

`V3_GOLD_REVIEW_PACKET.md` contains 24 query sections. Each main table is capped at 15 candidates, states how many are hidden, and points to the complete 452-row JSONL. Evidence is bounded and Gold status is explicitly not locked.

## 25. Auto Router Preparation

Every query records actual Planner query type, planned mode, routing reason, and candidate agreement with expected type. Twenty-three agree. Q06 (`MCP 与 Function Calling 的区别`) was expected as `mixed_entity` but the current Planner classifies it `semantic_question`; this is recorded for Stage 6B routing evaluation and did not trigger a Planner change.

## 26. Dense Truncation Audit

```text
Transcript chunks: 1,412
Original Qwen input >512 tokens: 28
Rate: 1.983%
Maximum original tokens: 547
Affected videos: 13
Truncated chunks present in formal pool Raw hits: 17
Affected candidate queries: 17
```

The full top-20 longest list and query intersections are retained in the snapshot directory's `dense_truncation_audit.json`. This is a read-only observation; Chunking, Projection, Provider, and embeddings were not modified.

## 27. Automated Tests

| Exact command | Exit | Passed | Failed | Skipped | Warnings |
|---|---:|---:|---:|---:|---:|
| `.venv/bin/python -m pytest tests/test_eval_snapshot.py -q` | 0 | 2 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest tests/test_eval_query_schema.py -q` | 0 | 2 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest tests/test_eval_candidate_pool.py -q` | 0 | 2 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest tests/test_eval_review_packet.py -q` | 0 | 1 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest tests/test_product_search_api.py -q` | 0 | 11 | 0 | 0 | 1 |
| `.venv/bin/python -m pytest tests/test_search_enrichment.py -q` | 0 | 75 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest tests/test_search_consolidation.py -q` | 0 | 10 | 0 | 0 | 0 |
| `.venv/bin/python -m pytest -q` | 0 | 506 | 0 | 0 | 7 |

The unmodified full-suite command passed without `PYTHONPATH` and without proxy-environment correction. Warnings were the existing Starlette/httpx deprecation plus six multiprocessing/fork deprecations. `git diff --check` and Python compilation also passed.

## 28. Live Data Integrity

Settled baseline and post-restoration hashes match for `videos`, `video_notes`, `favorite_sources`, `video_source_memberships`, `events`, `retrieval_units`, FTS, Dense vectors/meta, and sync state. Stage 6A caused no Live Product/index mutation. Live Raw/Presentation traces remained 82/52 after all 72 formal pool searches and reproducibility checks.

## 29. Remaining Unknowns

- Human reviewers have not accepted the 24-query set, suggested relevant videos, negative controls, uncertain candidates, or intervals.
- Pooled Gold coverage and unjudged-item treatment await Stage 6B execution under the locked protocol.
- Q06 Planner-type disagreement awaits routing review; changing Planner is outside Stage 6A.
- The quality impact of the 28 truncated chunks is unknown; no retrieval-quality conclusion is authorized.
- Fourteen indexed Video-only items have no declared raw subtitle and cannot receive interval Gold without new authoritative evidence.

## 30. Exact Human Review Required

Reviewers must approve/reject: all 24 query wordings and filters; every suggested/possible relevant video; the prioritized uncertain items; both negative-control absence assessments; all ten raw-segment interval candidates; and the Q06 expected/actual query-type interpretation. Only then may a separate `eval_gold.locked.jsonl` be created and Stage 6B metrics run.

## 31. Recommended Classification

**Ready for Gold Review with Follow-up**

All preparation, freeze, snapshot, manifest, pooling, evidence, protocol, review, isolation, restoration, and test gates are met. Follow-up is limited to mandatory human Gold review, Q06 routing interpretation, and Stage 6B evaluation of truncation/relevance effects. This is not Stage acceptance or a retrieval-quality conclusion.

## 32. Stop Boundary

Stage 6A stops here. Default mode remains lexical, Auto remains optional, Hybrid remains non-default, Gold is not locked, formal metrics and failure analysis are unavailable, `V3_CLOSEOUT.md` is not generated, and Stage 6B/V3.5 are not started.
