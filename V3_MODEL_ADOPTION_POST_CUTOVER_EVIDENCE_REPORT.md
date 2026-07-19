# Shiliu V3 Model Adoption — Post-cutover Evidence Report

## 1. Report Boundary

This report contains only evidence produced after the user authorized the formal
Qwen Cutover.

It deliberately excludes the content already recorded before authorization:

```text
Read-only Adoption Map
Model Selection timing correction
formal Provider implementation details
Experimental/Formal parity smoke
Projection comparison
pre-cutover dependency and automated-test evidence
database backup creation
Shadow Build
Candidate build and validation
manual Cutover readiness checkpoint
```

The evidence window begins with writer shutdown and ends with service
restoration. Stage 4 was not entered.

## 2. Authorization and Writer Shutdown

The user authorized formal Qwen Cutover after requiring `app.shiliu.web` and
other writers to stop first.

Before Cutover:

```text
app.shiliu.web: unloaded
app.shiliu.sync: unloaded
matching Shiliu serve/sync processes: 0
open shiliu.db handles reported by lsof: 0
sync_runs with status=running: 0
```

Both LaunchAgents returned `launchctl print` status `113`, meaning they were not
loaded in the user launchd domain at the final pre-transaction check.

## 3. Immediate Pre-transaction Revalidation

The following evidence was recomputed immediately before calling the Atomic
Cutover primitive:

```text
Candidate build_id: qwen-20260720-adoption-v2
Candidate status: ready
Candidate valid: true
Candidate rows: 1547
Current corpus fingerprint:
b7dfee25f76bcfa2ba96aa97d46b3b5358f9a1d48a256033dbb9633cd9db154c

Current formal model:
BAAI/bge-small-zh-v1.5

Current formal Dense version:
v3-stage2-dense-bge-small-zh-v1

Current formal fingerprint:
2efd810b46ed00510034138b096a418a70e46be4924dc0b68d74a2ae4a3977c6

Active writers: 0
Active sync_runs: 0
```

The Candidate fingerprint/corpus identity and complete formal BGE identity
matched the expected values. Cutover would have been rejected if any of these
checks differed.

## 4. Atomic Cutover Result

Cutover committed at:

```text
2026-07-19T18:28:37+00:00
```

The single `BEGIN IMMEDIATE` transaction completed all three state changes:

```text
1. replaced the formal Dense rows with the validated Candidate rows;
2. updated the complete formal Dense Meta identity to Qwen;
3. changed Candidate status from ready to cutover.
```

No model inference occurred inside the transaction.

Committed formal identity:

```text
model_id: Qwen/Qwen3-Embedding-0.6B
model_revision: 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3
provider_version: v3-qwen3-embedding-provider-v1
embedding_dimension: 512
embedding_dtype: float32
normalized: 1
embedding_mode: mrl-first-512-normalized
projection_version: v3-dense-projection-qwen-v1
query_instruction_version: v3-qwen-query-instruction-v1
input_policy_version: v3-qwen-input-512-v1
dense_index_version: v3-dense-qwen3-0.6b-mrl512-v1
```

Post-cutover formal fingerprint:

```text
21d6ccf1b37bdda3997b62c1dac7b16e87b3be864a28d3211dcfd44004db7cc2
```

Candidate final state:

```text
build_id: qwen-20260720-adoption-v2
status: cutover
row_count: 1547
```

## 5. Formal Index Verification

Final logical counts:

```text
Retrieval Units: 1547
FTS rows: 1547
Qwen Dense rows: 1547
Video Dense rows: 142
Transcript Chunk Dense rows: 1405
```

Correct `unit_id`-based consistency queries returned:

```text
metadata without FTS: 0
FTS without metadata: 0
Retrieval Units without Dense: 0
Dense without Retrieval Units: 0
duplicate Retrieval Unit IDs: 0
dimension mismatch: 0
damaged vectors: 0
non-finite vectors: 0
norm violations: 0
```

The first attempted FTS audit used an invalid `rowid` association and was
discarded. `retrieval_units_fts.unit_id` is the stable association used by the
corrected evidence above.

SQLite checks:

```text
PRAGMA integrity_check: ok
PRAGMA foreign_key_check: []
```

## 6. Formal Dense and Hybrid Search

Formal runtime searches were executed with the Application-scoped
`QwenEmbeddingProvider`, not the Model Selection experimental Adapter.

Queries:

```text
MCP
LangGraph
RAG
FAISS
Agent 多轮运行后怎样控制上下文增长
```

All five Dense searches and all five Hybrid searches completed successfully.
Representative Dense top results included:

| Query | Top result | Score |
| --- | --- | ---: |
| `MCP` | `分享我转 AI 方向的学习路径和工作转变` timestamped Chunk | 0.644566 |
| `LangGraph` | `[开源] RAG 项目框架及源码详解` Video | 0.640199 |
| `RAG` | `[开源] RAG 项目框架及源码详解` timestamped Chunk | 0.802475 |
| `FAISS` | `手把手教你从零学会看Github项目，以MemoryOS为例【代码精读】` Chunk | 0.640600 |
| Chinese semantic query | `近年AI应用技术串讲与优质文档分享…` Chunk | 0.647640 |

Runtime observations from this process:

```text
Provider load count: 1
active device: mps
first Dense search including lazy load: 4.125866 seconds
subsequent Dense/Hybrid calls: approximately 0.047 to 0.083 seconds
```

## 7. Formal Stage 3 Lifecycle Regression

Two full formal reconciliations were executed after Cutover:

| Metric | Reconcile 1 | Reconcile 2 |
| --- | ---: | ---: |
| attempted | 143 | 143 |
| succeeded | 143 | 143 |
| failed | 0 | 0 |
| desired indexed | 142 | 142 |
| desired absent | 1 | 1 |
| new embeddings | 0 | 0 |
| reused Qwen vectors | 1547 | 1547 |
| Dense failures | 0 | 0 |
| not ready | 0 | 0 |
| rebuild required | 0 | 0 |
| duration | 4.087733 s | 3.527157 s |

One unchanged eligible Video was then synchronized directly:

```text
video_id: 1
desired state: indexed
lexical state: current
dense state: current
Video units: 1
Transcript Chunk units: 3
new embeddings: 0
reused Qwen vectors: 4
measured duration: 0.012565 seconds
```

Final Retrieval sync-state groups:

```text
142: desired=indexed, lexical=current, dense=current
1: desired=absent, lexical=absent, dense=absent
```

## 8. Post-cutover Automated Regression

Commands executed after formal Cutover:

```text
.venv/bin/python -m pytest tests/test_retrieval_lifecycle.py -q
Result: 13 passed

.venv/bin/python -m pytest tests/test_qwen_embedding_provider.py tests/test_dense_adoption.py -q
Result: 14 passed

.venv/bin/python -m pytest -q
Result: 346 passed
```

Warnings were limited to the existing Starlette/httpx deprecation warning and
six multiprocessing `fork()` deprecation warnings. There were no test failures
or skips reported.

The temporary-database lifecycle suite covers Product-owner paths for Note and
Library state changes, Pipeline completion/refinement, subtitle/ASR replacement,
Membership removal, Video removal, reconcile and Product mutation failure
isolation.

## 9. Product Source Integrity After Cutover

The five protected Product Source table hashes remained equal to their
pre-Cutover baselines after Cutover, formal searches and lifecycle regression:

| Table | Rows | SHA-256 |
| --- | ---: | --- |
| `videos` | 143 | `81fc4068762457fd554b6d5a0b185e2613e7c6c2b028e597816bc62cd6b83be9` |
| `video_notes` | 1 | `4acacc0cd3723d2698e9af4a1646953b09a2697baa565f894e6b85c1ad43077f` |
| `favorite_sources` | 2 | `36544248f5fdb32b349d2a648561e77da2f1b6022c53435e1620b31781f6686c` |
| `video_source_memberships` | 145 | `3fa7a410c693fc8a85b32c1c715bb22b07f003696ec06d269a63947a6b6d4efc` |
| `events` | 271 | `275036e4304cce1090fa4fc51d43e207a26c756a13e383e89625387cbb8ca1b2` |

All 271 Events remain `pending` with no evidence of consumption.

## 10. Operational Restoration

After all database and lifecycle evidence completed, the original LaunchAgents
were restored:

```text
app.shiliu.sync:
registered
RunAtLoad=false
state=not running
hourly schedule restored without an immediate sync

app.shiliu.web:
registered
state=running
http://127.0.0.1:18520/ = HTTP 200
```

## 11. Final Classification and Stop Boundary

```text
Selected formal Dense model:
Qwen/Qwen3-Embedding-0.6B
revision 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3

Model Adoption:
Delivered
Ready for Version Session Review

Recommended classification:
Accepted with Follow-up

Hybrid default:
unchanged; lexical remains default

Formal Retrieval Eval:
pending

Stage 4:
Not Started
```

Execution stopped after post-cutover verification and service restoration.
