# Shiliu V3 Stage 4A Implementation and Evidence Report

## 1. Scope and Read-only Integrity Baseline

**[Confirmed Fact]** 本轮只实现 Stage 4A：Search Planning、Mode Routing、Raw Unit
Retrieval API 与持久化 Search Trace。未实现 Stage 4B 的 grouping、temporal
expansion、jump behavior、chapter、UI、reranker、query rewrite 或正式 Retrieval
Eval。

开始时执行：

```bash
pwd
git status --short
git diff --stat
git diff --cached --stat
git status -sb
```

工作目录为 `/Users/elliot/new-systems/agent-job-prep/Shiliu`，分支为
`codex/v3-domain-completion`。既有 V3 未提交实现与报告均被保留；本轮未清理、
覆盖或提交用户已有变更。

## 2. Read-only Search Map

**[Confirmed Fact]** 实现前的最小调用图如下：

| 边界 | 既有位置 | 复用点 |
| --- | --- | --- |
| CLI Search | `src/shiliu/cli.py` | 原先直接选择 Lexical/Dense/Hybrid |
| Lexical | `src/shiliu/retrieval/service.py`, `RetrievalService.search` | FTS5/BM25、scope、filter allowlist |
| Dense | `src/shiliu/retrieval/dense.py`, `SQLiteExactDenseIndex.search` | 正式 Qwen exact cosine search |
| Hybrid | `src/shiliu/retrieval/hybrid.py`, `HybridRetrievalService.search` | 既有 unweighted RRF 排序 |
| Composition | `src/shiliu/app.py`, `Application` | Lazy Lexical/Dense/Hybrid services |
| Web API | `src/shiliu/web.py`, `create_web_app` | FastAPI + structured JSON errors |
| Index identity | `retrieval_index_meta`, `retrieval_dense_index_meta` | Lexical/Dense/Provider/Projection identity |

**[Confirmed Fact]** Stage 4A 没有复制已有检索器，也没有修改 FTS、Dense 投影或
RRF 排名算法。

## 3. Implemented Architecture

**[Confirmed Fact]** CLI 与 API 现在共享同一路径：

```text
SearchRequest
  -> SearchPlanner (normalize, classify, route)
  -> SearchPlan
  -> SearchOrchestrator
  -> existing Lexical / Dense / Hybrid retriever
  -> ordered RawSearchHit list
  -> best-effort persistent Search Trace
```

主要实现位置：

- `src/shiliu/retrieval/planner.py:30-167`
- `src/shiliu/retrieval/orchestrator.py:41-455`
- `src/shiliu/retrieval/hybrid.py:15-93`
- `src/shiliu/app.py:208-216`

## 4. Search Request Contract

**[Confirmed Fact]** `SearchRequest` 位于
`src/shiliu/retrieval/planner.py:80`，字段为：

```text
query: string
mode: lexical | dense | hybrid | auto       default lexical
scope: all | video | transcript_chunk       default all
raw_top_k: integer 1..100                    default 20
filters: SearchFilterRequest
```

Pydantic 使用 `extra="forbid"`；未知字段、非法枚举、越界 top-k 在进入检索前被拒绝。

## 5. Query Normalization

**[Confirmed Fact]** `normalize_query` 位于
`src/shiliu/retrieval/planner.py:140`。它执行 Unicode NFKC、折叠首尾及连续空白，
保留原始 query 到 Plan/Trace，并拒绝空 query 与超过 500 字符的 normalized query。

**[Confirmed Fact]** 自动测试覆盖全角字符、混合空白、原文保留、空白 query 和长度边界。

## 6. Deterministic Query Classification

**[Confirmed Fact]** `classify_query` 位于
`src/shiliu/retrieval/planner.py:149`，输出严格限定为：

```text
exact_entity
mixed_entity
semantic_question
keyword_phrase
```

判定是纯本地确定性的：显式问号/中英文疑问词及长度边界优先判为语义问题；ASCII
与 CJK 同时出现判为 mixed entity；不超过 64 字符、最多 6 token 且字符符合
allowlist 的纯 ASCII 短实体判为 exact entity；其余为 keyword phrase。

**[Inference]** 这是可测试的产品路由启发式，不是相关性质量结论；边界质量仍需正式 Eval。

## 7. Search Modes and Routing

**[Confirmed Fact]** `SearchPlanner.plan` 位于
`src/shiliu/retrieval/planner.py:108`：

| Requested mode | Query type | Planned mode |
| --- | --- | --- |
| lexical / dense / hybrid | 任意 | 保持显式选择 |
| auto | exact_entity | lexical |
| auto | mixed_entity | hybrid |
| auto | semantic_question | hybrid |
| auto | keyword_phrase | hybrid |

**[Confirmed Fact]** 默认仍为 Lexical；没有把 Auto 或 Hybrid 改为产品默认。

## 8. Fallback Policy

**[Confirmed Fact]** allowlist 位于
`src/shiliu/retrieval/orchestrator.py:392`。只有 `auto` 计划为 Hybrid 时，以下错误
才允许回退 Lexical：

```text
DenseIndexNotReadyError        -> dense_not_ready / HTTP 503 when explicit
DenseIndexRebuildRequiredError -> dense_rebuild_required / HTTP 409 when explicit
LocalModelNotReadyError        -> local_model_not_ready / HTTP 503 when explicit
```

Auto 回退响应和 Trace 均记录 `executed_mode=lexical`、`fallback=true` 和具体原因。
显式 Dense/Hybrid 不回退；未知异常也不回退。

## 9. Scope and Filter Semantics

**[Confirmed Fact]** Stage 4A 仅暴露已有 Product Retrieval 语义：

```text
scope: all | video | transcript_chunk
filters:
  source_db_id
  folder_id
  favorite_time_from
  favorite_time_to
  reading_state
  marked
  uploader
  archived
  ignored
```

`SearchFilterRequest.retrieval_filters` 位于
`src/shiliu/retrieval/planner.py:55`，映射到既有 `RetrievalFilters`；过滤继续在各
retriever 的候选查询内执行，不做 top-k 后置过滤。

## 10. Raw Unit Result Contract

**[Confirmed Fact]** `RawSearchHit` 位于
`src/shiliu/retrieval/orchestrator.py:41`。返回字段包含稳定 unit/video identity、
unit type、rank、最终和组件分数/排名、retrieval method、title/uploader/source、
timestamp bounds 与最多 300 字符 excerpt。

**[Confirmed Fact]** 这是 raw unit list；未做视频聚合、chunk collapse、temporal
expansion、chapter composition 或二次重排。

## 11. Ranking Preservation

**[Confirmed Fact]** Lexical 与 Dense 结果保持既有服务返回顺序。Hybrid 继续使用
`src/shiliu/retrieval/hybrid.py:37` 的既有 RRF 语义：`rrf_k=60`、候选数
`max(50, top_k*5)`、排序键为 `(-rrf_score, best_component_rank, unit_id)`。

本轮对 Hybrid 的唯一改动是 `HybridExecution` 时序和候选数量观测；`search()` 委托
`search_with_trace()` 后返回同一 results。

## 12. Persistent Search Trace Schema

**[Confirmed Fact]** `SearchOrchestrator.initialize_schema` 位于
`src/shiliu/retrieval/orchestrator.py:138`，以 additive table 创建
`retrieval_search_traces`。关键字段覆盖：

- trace/version/created time；
- raw/normalized query、query type；
- requested/planned/executed mode 与 routing reason；
- scope、validated filters、top-k；
- Lexical/Dense candidate counts 与 raw hit count；
- planning/Lexical/Dense/fusion/total timing；
- Lexical/Dense/model/revision/provider/projection/instruction/input/fusion identity；
- fallback flag/reason；
- success/error status、code、stage 与有界 message；
- 有界 raw-hit ranking evidence。

持久化 hit 仅含 `unit_id, rank, score, lexical_rank, lexical_score, dense_rank,
dense_score, rrf_score`，不保存 excerpt 或字幕正文。

## 13. Trace Failure Isolation

**[Confirmed Fact]** 成功检索后的 Trace 写入若失败，搜索结果仍成功返回，并通过
`trace_persisted=false` 与 `trace_error` 显式暴露。检索失败时执行 best-effort error
Trace；error message 截断为 500 字符。

**[Confirmed Fact]** 自动测试覆盖成功 Trace、错误 Trace、持久化故障隔离、正文不入
Trace、错误长度边界与 Trace lookup。

## 14. Raw Search API

**[Confirmed Fact]** `src/shiliu/web.py:284-301` 新增：

```text
POST /api/search/raw
GET  /api/search/traces/{trace_id}
```

POST 与 CLI 使用同一个 `Application.search_orchestrator`。结构化错误包含 code、stage、
message、trace_id 和 trace_persisted；未知 trace 返回 404。

真实 HTTP smoke：

```text
POST MCP, mode=auto, top_k=3 -> HTTP 200
trace 923e6133-4b2b-407e-8c60-ce6d3f59c9f3
exact_entity -> lexical -> 3 raw hits
GET same trace -> HTTP 200, status=success

POST whitespace, mode=auto -> HTTP 400
trace a647fb39-1610-4932-9de7-9b65b8ce2870
code=invalid_search_request, stage=planning, trace_persisted=true
```

## 15. CLI Surface

**[Confirmed Fact]** `src/shiliu/cli.py:48-70,274-315` 支持：

```bash
.venv/bin/shiliu retrieval search QUERY \
  --mode lexical|dense|hybrid|auto \
  --scope video|transcript_chunk|all \
  --top-k N \
  --trace
```

`--level` 保留为 `--scope` 的兼容 alias；默认 mode 为 lexical，默认 top-k 为 20。

真实 CLI smoke：`MCP --mode auto --scope all --top-k 3 --trace` 成功，Trace
`4c862cc4-c2f8-4021-bf88-577009bd6506` 记录 exact_entity -> Lexical 和 3 hits。

## 16. Automated Test Evidence

**[Confirmed Fact]** 新增 43 个 Stage 4A 测试：

```text
.venv/bin/python -m pytest tests/test_search_planner.py -q
19 passed

.venv/bin/python -m pytest tests/test_search_orchestration.py -q
17 passed

.venv/bin/python -m pytest tests/test_search_api.py -q
7 passed
```

既有检索回归：

```text
tests/test_retrieval.py             13 passed
tests/test_dense_retrieval.py        9 passed
tests/test_retrieval_lifecycle.py   13 passed
```

完整标准测试：

```text
.venv/bin/python -m pytest -q
389 passed
```

仅出现既有 Starlette/httpx 和 multiprocessing fork deprecation warnings；无失败或跳过。

## 17. Formal Query Matrix Evidence

**[Confirmed Fact]** 单一 `Application` 实例执行了 25 条正式请求：

| 组 | Queries | 观察结果 |
| --- | --- | --- |
| Auto exact (6) | MCP, LangGraph, RAG, FAISS, OpenAI, Claude Code | 全部 exact_entity -> Lexical |
| Auto mixed (4) | MCP 协议, LangGraph 工作流, OpenAI API调用, FAISS 向量索引 | 全部 mixed_entity -> Hybrid |
| Auto semantic (3) | 中英文自然语言问题 | 全部 semantic_question -> Hybrid |
| Auto keyword (4) | 中英文关键词短语 | 全部 keyword_phrase -> Hybrid |
| Explicit override (3) | Dense / Lexical / Hybrid | 全部保持显式 mode |
| Scope (3) | 同 query 的 video/chunk/all | 返回类型符合 scope |
| Filter (2) | folder+unread；uploader+marked | 候选与 hit 均符合过滤条件 |

MCP 代表 Trace `53cde56c-6382-4c31-bab8-23c785bc49ee`：5 个 Lexical hits、
Dense candidates 为 0。MCP 协议代表 Trace
`8e0cde1c-a1f8-4850-b224-aab556659c81`：1 个 Lexical candidate、50 个 Dense
candidates，Hybrid 返回 5 raw hits。

**[Inference]** 该矩阵证明路径、路由、过滤和可追踪性，不等同于相关性验收。

## 18. Explicit Override Evidence

**[Confirmed Fact]** 正式矩阵分别执行 explicit Dense、Lexical 和 Hybrid；
requested/planned/executed mode 一致。自动测试进一步证明显式 Dense/Hybrid 遇到
Dense availability error 时返回结构化错误，不静默切换 Lexical。

## 19. Scope and Filter Evidence

**[Confirmed Fact]** `RAG 工作机制` 的三条 Trace：

| Scope | Trace | Top results 类型 |
| --- | --- | --- |
| video | `4ccd7e2e-e670-4303-8b66-938ade3fd017` | 全为 Video |
| transcript_chunk | `6253f227-0f44-47d1-b875-501597662d50` | 全为 Transcript Chunk |
| all | `4a9d5505-5027-45d2-af5d-7818f2508901` | 同时包含 Video 与 Chunk |

Filter Trace `d3f55942-0f91-4797-a5f1-b1e453b2ca82` 使用
`folder_id=3876418799, reading_state=unread`；Hybrid 候选受过滤后的语料约束。
Trace `b258e792-58d5-4392-9735-0ea26f3fd562` 使用
`uploader=chocpink_AI版, marked=true`，Lexical 返回 6/6 hits。

## 20. Fallback Evidence

**[Confirmed Fact]** 临时数据库自动测试逐一注入 Dense not ready、Dense rebuild
required 与 local model/provider initialization unavailable，Auto Hybrid 均回退 Lexical
并记录对应原因。显式模式对相同错误不回退；未知 Hybrid RuntimeError 也不回退。

**[Unknown]** 正式 Qwen 索引当前健康，因此没有破坏正式索引来制造一次 production
fallback；正式环境证据限于正常路径，故障语义由隔离测试证明。

## 21. Runtime Characteristics

**[Confirmed Fact]** 25-query 正式矩阵中，首次 Hybrid 请求包含 Qwen lazy load，耗时
约 4650 ms；随后 Hybrid 请求观测约 48–83 ms。16 条成功 Hybrid Trace 的中位 total
约 61.9 ms。真实 HTTP/CLI 的 MCP Lexical smoke 分别约 2.86 ms 和 2.09 ms。

**[Inference]** 这些是单机观测值，不是性能 SLA，也没有在本阶段做并发压测。

## 22. Product Source and Index Integrity

**[Confirmed Fact]** Stage 4A 后按稳定主键顺序、每行 compact JSON + newline 计算的
五张 Product Source 表与既有基线完全一致：

| Table | Rows | SHA-256 |
| --- | ---: | --- |
| videos | 143 | `81fc4068762457fd554b6d5a0b185e2613e7c6c2b028e597816bc62cd6b83be9` |
| video_notes | 1 | `4acacc0cd3723d2698e9af4a1646953b09a2697baa565f894e6b85c1ad43077f` |
| favorite_sources | 2 | `36544248f5fdb32b349d2a648561e77da2f1b6022c53435e1620b31781f6686c` |
| video_source_memberships | 145 | `3fa7a410c693fc8a85b32c1c715bb22b07f003696ec06d269a63947a6b6d4efc` |
| events | 271 | `275036e4304cce1090fa4fc51d43e207a26c756a13e383e89625387cbb8ca1b2` |

正式 Retrieval/FTS/Dense 数量仍为 `1547 / 1547 / 1547`；
`PRAGMA integrity_check` 为 `ok`，`PRAGMA foreign_key_check` 返回 0 条。

正式 Trace 当前为 29 条：27 success、2 个有界 planning error。成功路径分布包含
9 个 Auto Lexical、15 个 Auto Hybrid，以及显式 Lexical/Dense/Hybrid；没有正式环境
fallback。

## 23. Known Limitations and Remaining Unknowns

**[Unknown]** 正式 Retrieval Eval、相关性指标、失败 query analysis 与 timestamp anchor
error 尚未执行。

**[Unknown]** Stage 4B 的 per-Video grouping、temporal expansion、jump URL、chapter
composition 与 UI 尚未设计或实现。

**[Unknown]** 分类启发式在更大真实 query 分布上的误分率未知。

**[Confirmed Fact]** 本阶段没有实现 reranker、query rewrite/translation、LLM planner、
embedding mutation、FTS rebuild 或 Product Source mutation。

## 24. Acceptance Assessment

**[Confirmed Fact]** Stage 4A 实现满足本轮范围内的调用链、默认 Lexical、可选 Auto、
四类确定性分类、显式 mode override、Auto-only fallback、raw unit 返回、API/CLI 共用
orchestrator、持久化 Trace、故障隔离、正式 smoke 与回归测试要求。

**[Inference]** 结论为 **Accepted with Follow-up**。Follow-up 是正式 Retrieval Eval 与
未来单独授权的 Stage 4B，不是本轮必须修复项，也不授权自动继续。

## 25. Hard Stop

**[Confirmed Fact]** Stage 4A 到此停止。未开始 Stage 4B，未实现 grouping、temporal
expansion、jump behavior、chapters、UI、reranker、query rewrite 或 Dense/Hybrid 默认
切换。
