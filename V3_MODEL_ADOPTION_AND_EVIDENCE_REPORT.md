# Shiliu V3 Model Adoption and Evidence Report

## 1. Scope and Integrity

**Confirmed Fact** — The first execution implemented the formal offline Qwen
Provider, compatibility guard and validated Shadow Candidate, then stopped at
the mandatory checkpoint. After explicit user authorization and verified writer
shutdown, the resumed execution completed Atomic Cutover and lifecycle validation.

**Confirmed Fact** — No model was downloaded. The only model path used was:

```text
/Users/elliot/Library/Caches/Shiliu/model-selection/Qwen3-Embedding-0.6B
revision 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3
```

`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` and
`local_files_only=True` were enforced. E5, FTS, BM25, RRF, Chunk boundaries,
timestamps, Hybrid default, Query Understanding, API/UI and Stage 4 were not
changed.

## 2. Read-only Adoption Map

| Required map item | Actual module / function | Current behavior and Adoption change | Risk if unchanged |
| --- | --- | --- | --- |
| Provider interface | `src/shiliu/retrieval/dense.py:55` · `EmbeddingProvider` | Existing document/query/token/truncate contract retained; `model_identity()` added | 512-d BGE/Qwen could be treated as compatible |
| Previous formal Provider | `dense.py:97` · `FastEmbedEmbeddingProvider`; former `Application.dense_retrieval` construction | Lazy BGE adapter remains available for rollback; Application now constructs Qwen | Product runtime would continue querying BGE |
| Dense obtains Provider | `src/shiliu/app.py:189` · `Application.dense_retrieval` | One lazy `SQLiteExactDenseIndex` owns one Qwen Provider | Per-call construction could reload 1.1 GiB model |
| Application reuse | `app.py:189-195` | Property caches the Dense service and Provider for Application lifetime | Hooks/search could repeatedly load models |
| CLI construction | `src/shiliu/cli.py:234-280` | All Dense rebuild/search/sync commands resolve through one `Application` | CLI could use a different model identity |
| Stage 3 construction | `src/shiliu/retrieval/coordinator.py:61-74` | `dense_factory=lambda: self.dense_retrieval` reuses Application-scoped service | Incremental writes could mix vector spaces |
| Dense Meta / guard | `dense.py:244`, `dense.py:595` | Meta now covers revision, provider, embedding mode, instruction and input policy in addition to existing fields | Same dimension could bypass compatibility |
| Vector schema | `dense.py:249-261` | Formal vectors remain one row per `retrieval_units.unit_id`; Candidate is additive and build-scoped | Direct overwrite could leave partial formal state |
| Replace/rebuild transaction | `dense.py:296`, `dense.py:413` | Provider inference precedes short replacement transactions | Long inference transaction would block writers |
| Experimental Adapter | `research/v3_model_selection/harness.py:95` · `QwenLocalEmbeddingProvider` | Exact local load/encode/query formatting was copied into formal Provider | Provider parity could drift from accepted Gate |
| Projection tokenizer | `dense.py:201-229` · `project_embedding_text`; `dense.py:231` · `prepare_embedding_document` | Video packing and final Document truncation use the active Provider tokenizer | Hash could describe text not submitted to Qwen |
| Paths/environment | `src/shiliu/config.py:21` · `AppPaths`; `src/shiliu/app.py:68-75` | Explicit Qwen local path, overrideable only by an absolute local path; offline flags set before lazy load | Runtime might resolve a Hub ID or wrong cache |
| Process lifetime | `src/shiliu/web.py:104` and `src/shiliu/launchd.py:12-24` | Web owns a persistent Application; CLI/launchd sync are short-lived processes | Cold load repeats across separate processes, but not within an Application |

## 3. Model Selection Report Correction

`V3_MODEL_SELECTION_REPORT.md` now distinguishes:

```text
Baseline full embedding build: 25.013624 seconds
Baseline unchanged reuse rebuild: 0.766059 seconds
Qwen full embedding build (Gate): 569.049285 seconds
```

The Adoption decision is unchanged. The report no longer compares Qwen full
embedding with BGE unchanged-vector reuse as if they were equivalent work.

## 4. Formal Qwen Provider

**Confirmed Fact** — `src/shiliu/retrieval/qwen.py:64` implements
`QwenEmbeddingProvider` with:

```text
model: Qwen/Qwen3-Embedding-0.6B
revision: 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3
device: MPS when available, otherwise CPU
pooling: model-defined last-token pooling
truncate_dim: 512
batch_size: 8
output: normalized finite float32
```

The constructor is lazy. `_load()` uses a process-local initialization lock;
encoding uses a process-local encode lock. The real smoke reported
`provider_load_count=1`.

Missing files, revision mismatch, missing dependencies, remote/relative paths
and missing offline flags raise structured `LocalModelNotReadyError` or a
direct path validation error. Runtime never installs dependencies.

## 5. Experimental/Formal Parity

The explicit real-model parity command compared the experimental Adapter and
formal Provider on:

```text
MCP
LangGraph
RAG
FAISS
MCP 协议
Agent 多轮运行后怎样控制上下文增长
```

Results:

```text
dimension: 512
dtype: float32
formal/experimental cosine range: 0.999999881 to 1.000000119
maximum absolute difference for every probe: 0.0
small-corpus top-k ordering equal: 6 / 6
ASCII identical pairs among MCP/LangGraph/RAG/FAISS: 0 / 6
formal model load count: 1
active device: mps
```

This exceeds the required cosine threshold of `0.99999`.

## 6. Query and Document Semantics

Query input is exactly:

```text
Instruct: Given a Chinese or English AI and software engineering knowledge retrieval query, retrieve the most relevant evidence passages.
Query: <whitespace-normalized query>
```

Documents receive no query instruction and preserve Projection formatting.
Long query bodies are deterministically truncated while retaining the complete
fixed instruction. There is no translation, rewrite or dynamic instruction.

## 7. Token and Dimension Policy

```text
model maximum: 512 tokens
Video content budget: 480 tokens
final dimension: 512
embedding mode: first 512 Matryoshka dimensions, then L2 normalization
```

**Confirmed Fact** — Qwen Projection hashes differed from the active BGE
Projection hashes for `127 / 142` formal Video units. Therefore the formal
Projection identity is correctly new:

```text
v3-dense-projection-qwen-v1
```

Candidate v1 exposed an oversized Transcript Chunk (`3149` tokenizer tokens)
and failed safely after 80 Candidate rows. The corrected formal path explicitly
truncates only the final text sent to the Document Encoder to `<=512` tokens;
`embedding_text_hash` is computed from that final text. Retrieval Unit IDs,
Chunk boundaries, timestamps and source text remain unchanged.

## 8. Runtime Dependency Packaging

`pyproject.toml` contains the formal optional extra:

```toml
[project.optional-dependencies]
qwen = [
  "sentence-transformers>=2.7,<6",
  "torch>=2.6,<3",
  "transformers>=4.51,<6",
]
```

Lexical-only imports do not load Qwen. Exact dependency check:

```text
.venv/bin/python -m pip check
exit 0
No broken requirements found.
```

## 9. Provider/Index Compatibility Guard

`SQLiteExactDenseIndex._assert_configuration_compatible()` compares all of:

```text
model_id
model_revision
provider_version
embedding_dimension
embedding_mode / pooling-truncation identity
projection_version
query_instruction_version
input_policy_version
dense_index_version
normalized
```

Qwen Provider + active BGE Meta is rejected as `rebuild_required`, so Stage 3
Lexical may remain current while Dense refuses an incremental mixed-space write.
Tests cover Qwen/BGE cross-pairs, same-dimension model mismatch, revision,
provider, instruction and Projection mismatch.

## 10. Version Identities

```text
provider_version: v3-qwen3-embedding-provider-v1
model_id: Qwen/Qwen3-Embedding-0.6B
model_revision: 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3
embedding_dimension: 512
embedding_mode: mrl-first-512-normalized
projection_version: v3-dense-projection-qwen-v1
query_instruction_version: v3-qwen-query-instruction-v1
input_policy_version: v3-qwen-input-512-v1
dense_index_version: v3-dense-qwen3-0.6b-mrl512-v1
```

## 11. Shadow Build Architecture

`src/shiliu/retrieval/adoption.py:45` implements one scoped Candidate, not a
general model registry:

```text
retrieval_dense_candidate_meta
retrieval_dense_vectors_candidate
```

Candidate inference runs without an open write transaction. Each batch of 8 is
written in a short transaction. Formal BGE rows are never updated during build.

## 12. Corpus Fingerprint

The stable corpus digest covers, in unit-ID order:

```text
unit_id
unit_type
embedding_text_hash of the final Qwen document text
source content_hash
```

Recorded and post-build fingerprints are identical:

```text
b7dfee25f76bcfa2ba96aa97d46b3b5358f9a1d48a256033dbb9633cd9db154c
```

## 13. Pre-cutover Tests

| Exact command | Exit | Result |
| --- | ---: | --- |
| `.venv/bin/python -m pytest tests/test_retrieval.py -q` | 0 | 13 passed |
| `.venv/bin/python -m pytest tests/test_dense_retrieval.py -q` | 0 | 9 passed |
| `.venv/bin/python -m pytest tests/test_retrieval_lifecycle.py -q` | 0 | 13 passed; 1 Starlette warning |
| `.venv/bin/python -m pytest tests/test_qwen_embedding_provider.py -q` | 0 | 7 passed |
| `.venv/bin/python -m pytest tests/test_dense_adoption.py -q` | 0 | 7 passed |
| `.venv/bin/python -m pytest -q` | 0 | 346 passed; 1 Starlette and 6 multiprocessing fork deprecation warnings |

The final full-suite command used no `PYTHONPATH` override. Default tests use
temporary databases, temporary artifacts and fake Providers; the real 1.1 GiB
smoke was a separate explicit offline command.

## 14. Manual Cutover Checkpoint

```text
=== QWEN FORMAL CUTOVER CHECKPOINT ===

Current formal model:
BAAI/bge-small-zh-v1.5
revision 46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59
v3-stage2-dense-bge-small-zh-v1

Candidate model:
Qwen/Qwen3-Embedding-0.6B
revision 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3
v3-qwen3-embedding-provider-v1
v3-dense-qwen3-0.6b-mrl512-v1

Formal vectors:
1547
fingerprint 2efd810b46ed00510034138b096a418a70e46be4924dc0b68d74a2ae4a3977c6

Candidate vectors:
1547
fingerprint 2583cfbc99c100acca9e010593f7d72e320aa3943b7d637a5afb66870eab70c9

Corpus fingerprint:
b7dfee25f76bcfa2ba96aa97d46b3b5358f9a1d48a256033dbb9633cd9db154c

Candidate validation:
ready; missing/extra/duplicate/damaged/non-finite/norm/FK = 0; identity valid

Database backup:
/Users/elliot/Library/Application Support/Shiliu/backups/shiliu.pre-qwen-cutover.20260719T174309Z.db
SHA-256 860d946e51e1be07ae1a1a2551e3b0b99df540e901c4a386927962d83c8a0e78

Product source tables unchanged:
yes; all five row counts and SHA-256 values match the pre-build baseline

Expected cutover operation:
revalidate writer/corpus/formal identity, then one BEGIN IMMEDIATE transaction
replaces formal vectors from the ready Candidate, updates complete Qwen Meta,
marks Candidate cutover, and commits

Rollback method:
stop writers, restore the verified pre-cutover SQLite backup, select BGE Provider,
then rerun integrity, identity and retrieval smoke checks

Known operational metrics:
Gate cold load 47.257571 s; adoption warm query about 32-33 ms;
formal Shadow Build 1340.796817 s; peak RSS 799342592 B; model disk 1.1 GiB

Blocking issues at checkpoint:
none in Candidate data. app.shiliu.web was a potential writer and was stopped
before Cutover; app.shiliu.sync was also unloaded.

Authorization outcome:
user authorized Qwen formal Cutover after requiring all writers to stop
```

## 15. Atomic Cutover Evidence

**Confirmed Fact** — `DenseAdoptionManager.atomic_cutover()` is implemented at
`src/shiliu/retrieval/adoption.py:253`. It rechecks Candidate validity, formal
fingerprint and complete expected formal identity before and again inside
`BEGIN IMMEDIATE`. Model inference is not performed in the transaction.

Automated forced failures after vector insertion and after Meta update both
roll back to byte-identical formal vectors and unchanged formal Meta.

**Confirmed Fact** — Real Cutover committed at `2026-07-19T18:28:37+00:00`
after these preconditions were revalidated:

```text
launchd web loaded: no
launchd sync loaded: no
Shiliu writer processes: 0
active sync_runs: 0
Candidate: ready and valid
corpus fingerprint: b7dfee25f76bcfa2ba96aa97d46b3b5358f9a1d48a256033dbb9633cd9db154c
formal BGE fingerprint: 2efd810b46ed00510034138b096a418a70e46be4924dc0b68d74a2ae4a3977c6
backup SHA-256: 860d946e51e1be07ae1a1a2551e3b0b99df540e901c4a386927962d83c8a0e78
```

The committed formal Qwen fingerprint is:

```text
21d6ccf1b37bdda3997b62c1dac7b16e87b3be864a28d3211dcfd44004db7cc2
```

## 16. Formal Index Verification

Final post-cutover state:

```text
Retrieval Units: 1547
FTS rows: 1547
formal Dense rows: 1547 Qwen
Candidate build: qwen-20260720-adoption-v2, status=cutover, rows=1547
metadata without FTS: 0
FTS without metadata: 0
Retrieval Units without Dense: 0
Dense without Retrieval Units: 0
dimension mismatch: 0
damaged/non-finite/norm violations: 0 / 0 / 0
PRAGMA integrity_check: ok
PRAGMA foreign_key_check: []
```

Formal Dense and Hybrid searches passed for `MCP`, `LangGraph`, `RAG`, `FAISS`
and `Agent 多轮运行后怎样控制上下文增长`. The runtime Provider identity is
the formal Qwen Provider, not the experimental Adapter or BGE.

## 17. Stage 3 Lifecycle Regression

Temporary-database real Product-owner tests pass for Library/Note state,
Pipeline summary/refinement, subtitle completion, ASR replacement, Membership
removal, Video removal, failure isolation and reconcile.

Formal Qwen results:

```text
reconcile 1: attempted 143, succeeded 143, embedded 0, reused 1547, failures 0, 4.087733 s
reconcile 2: attempted 143, succeeded 143, embedded 0, reused 1547, failures 0, 3.527157 s
unchanged sync-video 1: 1 Video + 3 Chunks, embedded 0, reused 4, 0.012565 s
Provider load count across search and lifecycle: 1
```

## 18. Failure Isolation

Automated coverage confirms missing local model, missing dependency, offline
flag failure, initialization/encode failure, non-finite output, identity
mismatch, stale corpus, failed Candidate, damaged vector and forced Cutover
rollback do not partially alter the formal index.

The real Candidate v1 boundary failure is additional evidence: it stopped after
80 isolated Candidate rows and left the formal BGE fingerprint unchanged.

## 19. Runtime Characteristics

```text
model disk: 1.1 GiB
BGE cache: 91 MiB and retained
Gate cold load: 47.257571 seconds
warm query: 0.032391 to 0.033411 seconds in adoption smoke
Shadow Build: 1340.796817 seconds
peak RSS: 799342592 bytes
Candidate SQLite pages: 6688768 bytes at build completion
Provider load count during build/probes: 1
active device: mps
first formal post-cutover Dense search including lazy load: 4.125866 seconds
subsequent formal Dense/Hybrid searches: approximately 0.047 to 0.083 seconds
unchanged formal reconcile: 4.087733 seconds then 3.527157 seconds
unchanged formal sync-video: 0.012565 seconds
```

These are informational Runtime Characteristics, not Adoption risk gates.
Post-cutover per-mutation metrics remain pending.

## 20. Product Source Integrity

Pre-build and post-build values match exactly:

| Table | Rows | SHA-256 |
| --- | ---: | --- |
| `videos` | 143 | `81fc4068762457fd554b6d5a0b185e2613e7c6c2b028e597816bc62cd6b83be9` |
| `video_notes` | 1 | `4acacc0cd3723d2698e9af4a1646953b09a2697baa565f894e6b85c1ad43077f` |
| `favorite_sources` | 2 | `36544248f5fdb32b349d2a648561e77da2f1b6022c53435e1620b31781f6686c` |
| `video_source_memberships` | 145 | `3fa7a410c693fc8a85b32c1c715bb22b07f003696ec06d269a63947a6b6d4efc` |
| `events` | 271 | `275036e4304cce1090fa4fc51d43e207a26c756a13e383e89625387cbb8ca1b2` |

All 271 events remain `pending`; none was consumed.

## 21. Rollback Evidence

Retained assets:

```text
backup: /Users/elliot/Library/Application Support/Shiliu/backups/shiliu.pre-qwen-cutover.20260719T174309Z.db
backup SHA-256: 860d946e51e1be07ae1a1a2551e3b0b99df540e901c4a386927962d83c8a0e78
BGE cache: /Users/elliot/Library/Caches/Shiliu/fastembed
expected restored Dense version: v3-stage2-dense-bge-small-zh-v1
```

Rollback steps, not executed:

```text
1. launchctl bootout gui/$(id -u)/app.shiliu.web
2. confirm no shiliu/uvicorn writer and no running sync_run
3. restore the verified backup with SQLite Backup API
4. resolve Application Dense Provider back to FastEmbedEmbeddingProvider
5. run:
   .venv/bin/python -m shiliu retrieval dense-stats
   .venv/bin/python -m shiliu retrieval search MCP --mode dense --top-k 5
   .venv/bin/python -m shiliu retrieval search MCP --mode hybrid --top-k 5
   PRAGMA integrity_check;
   PRAGMA foreign_key_check;
```

## 22. Remaining Limitations

* Formal Retrieval Eval, Search API/UI, result grouping and temporal consolidation remain pending and outside this stage.
* Some long Transcript Chunk document text is explicitly truncated for Qwen input; Chunk identity and timestamp evidence remain unchanged.

## 23. Recommended Classification

```text
Accepted with Follow-up
```

The Adoption implementation and evidence are delivered. Version Session review,
formal Retrieval Eval and later product work remain separate decisions.

## 24. Stop Boundary

```text
Model Selection Gate: Accepted with Follow-up
Model Adoption: Delivered — Ready for Version Session Review
Selected formal Dense model: Qwen/Qwen3-Embedding-0.6B revision 97b0c614...
Formal Dense version: v3-dense-qwen3-0.6b-mrl512-v1
Hybrid default: unchanged (lexical remains default)
Transcript Chunk boundaries: frozen
Formal Retrieval Eval: pending
Stage 4: Not Started
```

Execution stops here. Stage 4 was not started.

Operational restoration after all evidence completed:

```text
app.shiliu.sync: registered, RunAtLoad=false, state not running, hourly schedule restored
app.shiliu.web: registered and running
http://127.0.0.1:18520/: HTTP 200
```
