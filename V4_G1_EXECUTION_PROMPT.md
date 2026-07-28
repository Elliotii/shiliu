# Shiliu V4 Goal 1 Execution Prompt

```yaml
session_type: bounded_goal_execution
goal: Goal 1 — Complete Grounded RAG
status: ready_to_execute
date: 2026-07-29
repository: Shiliu
expected_branch: codex/v4-main
```

你正在启动一个新的：

```text
Shiliu V4 Goal 1 Execution Session
拾流 V4 Goal 1 执行 Session
```

本 Session 只负责实现和验证 Goal 1：

```text
Complete Grounded RAG
```

不得扩展到 Goal 2、Goal 3、第二项目或 V0–V3.5 历史治理任务。

---

# 1. 角色与职责

你在本 Session 中担任：

```text
Goal 1 Implementation Owner
Fast Grounded RAG Engineer
Evidence Integration Engineer
Test and Vertical Slice Owner
```

主 V4 Session 仍然负责：

- 跨 Goal 架构；
- 产品范围；
- `V4_MASTER_STATE.md`；
- `V4_DECISION_LEDGER.md`；
- Goal 结果的 Integration Review；
- 是否接受新的重大设计变更。

本 Goal Session 不得自行改变 V4 总体使命、共享 Ask Contract 或三 Goal 结构。

---

# 2. 必读文件与阅读顺序

开始工作前，按以下顺序完整阅读：

```text
1. V4_G1_EXECUTION_PROMPT.md
2. V4_MASTER_STATE.md
3. V4_DESIGN_PROPOSAL.md
4. V4_DECISION_LEDGER.md
5. README.md
```

然后只检查 Goal 1 直接相关的当前源码：

```text
src/shiliu/llm.py
src/shiliu/app.py
src/shiliu/web.py
src/shiliu/retrieval/product_search.py
src/shiliu/retrieval/planner.py
src/shiliu/retrieval/models.py
src/shiliu/evidence/contracts.py
src/shiliu/evidence/source.py
src/shiliu/evidence/authority.py
src/shiliu/evidence/mapping.py
src/shiliu/evidence/search.py
src/shiliu/bilibili.py
```

以及直接相关测试：

```text
tests/test_product_search_api.py
tests/test_evidence_contracts.py
tests/test_evidence_stage1b.py
tests/test_search_enrichment.py
tests/test_v1.py
tests/test_boundaries_and_web.py
```

只有遇到具体实现阻塞时，才继续读取其他文件。

不得重新进行：

- 全仓库审计；
- V0–V3.5 历史材料全文审计；
- Eval Gold 审计；
- Candidate Builder / Selector / Stage4 / Stage5 全面审计；
- 新一轮框架选型；
- 开放式 Web Research。

---

# 3. 开始前的仓库检查

在修改代码前：

1. 确认当前分支和工作区状态；
2. 不覆盖用户已有修改；
3. 确认 V4 四份正式文件存在；
4. 运行与 Goal 1 直接相关的现有测试，建立本 Session 基线；
5. 记录已有失败和 Warning，但不要因无关历史问题扩大范围。

当前主 Session 的定向基线是：

```text
136 passed
1 existing Starlette/httpx deprecation warning
```

这只是参考；Goal Session 必须以自己开始时的真实测试结果为准。

---

# 4. Goal 1 用户结果

Goal 1 完成后，Fast Ask API 必须支持：

```text
用户提交问题
→ 系统搜索现有字幕库
→ 将命中绑定到当前原字幕
→ 构造纯字幕事实 Context
→ 生成结构化自然语言答案
→ 验证每个 Citation
→ 返回可跳转的视频时间点证据
```

用户输出至少包括：

- 自然语言 Answer Blocks；
- 段落级 Citation；
- 原字幕 Quote；
- 视频起止时间；
- B 站跳转 URL；
- `complete / partial / insufficient`；
- `limitations`；
- `termination_reason`；
- 轻量 `trace_summary`。

---

# 5. 共享 Ask Contract

实现或等价表达：

```yaml
AskRequest:
  query: string
  mode: fast
  filters:

AskResponse:
  run_id: string
  mode: fast
  status: complete | partial | insufficient

  answer_blocks:
    - text: string
      citation_ids: [string]

  citations:
    - citation_id: string
      citation_identity_version: string
      video_id: integer
      bvid: string
      title: string
      source_type: human | ai | asr | unknown
      source_language: string
      source_artifact_id: string
      source_version: string
      timeline_run_id: string
      segment_ids: [string]
      start_time: number
      end_time: number
      quote_text: string
      jump_url: string

  limitations: [string]

  termination_reason:
    answer_ready |
    provider_error |
    evidence_unavailable

  trace_summary:
```

共享 V4 合同仍保留 Deep 所需的其他停止原因，但 Goal 1 Fast Runtime 正常只产生：

```text
answer_ready
provider_error
evidence_unavailable
```

硬约束：

- `answer_blocks` 是最终正文的唯一结构化事实源；
- 不增加自由 `answer`；
- 不增加平行 `claims`；
- Goal 1 每个非空 Answer Block 至少有一个 Citation ID；
- 标题由 UI 生成；
- 状态解释由 `status` 表达；
- 未支持或未覆盖内容由 `limitations` 表达。

---

# 6. Fast Runtime 预算

```yaml
query_analysis_calls: 1
answer_calls: 1
repair_calls: max_1
iterative_search: false
```

初始 Query 包络：

```yaml
original_query_required: true
rewrite_queries: max_2
distinct_search_queries_total: max_3
```

这些是第一版安全配置，不是永久 SLA。不得因为某个真实 Query 表现不佳而在本 Goal 内增加迭代 Agent Loop。

---

# 7. 目标流水线

实现一个普通 Service Pipeline：

```text
AskRequest(mode=fast)
→ Query Analysis
→ Original Query + bounded rewrites
→ normalize and deduplicate queries
→ one SearchExecution per distinct query
→ Evidence Materialization
→ stale skip
→ Evidence deduplication and lightweight rank-only fusion
→ Transcript-only Context construction
→ Grounded Answer
→ Schema Validation
→ Citation / Identity / Version / Segment Validation
→ optional one same-context Repair
→ repeat complete validation
→ final Source Version revalidation
→ AskResponse
```

不得使用 LangGraph。

---

# 8. 建议代码边界

可以新增轻量包：

```text
src/shiliu/ask/
├── __init__.py
├── contracts.py
├── query_analysis.py
├── context.py
├── answer.py
├── validation.py
└── service.py
```

这是建议边界，不要求机械创建每个文件。如果更少的文件能保持职责清楚，可以合并。

不得创建：

- Provider Platform；
- Citation Platform；
- Trace Platform；
- Eval Platform；
- Agent Framework；
-新的通用 Repository Layer。

领域 Service 不应依赖未来的 LangGraph。

---

# 9. Query Analysis

Query Analysis 使用 DeepSeek 一次结构化调用，输出或等价表达：

```yaml
normalized_intent:
search_queries:
entities:
language:
```

规则：

- 原始 Query 始终保留；
- Rewrite 最多两个；
- 去除空 Query；
- 对 Unicode、空白和大小写做稳定标准化；
- 标准化后重复 Query 只搜索一次；
- 所有 Query 继承用户 Filters；
- Query Analysis 不生成预期答案；
- 不判断 Evidence 充分度；
- 不读取 Eval Gold。

如果 Query Analysis 格式错误、为空、超时或 Provider 失败：

```text
记录内部错误
→ 退化为只搜索原始 Query
→ 继续 Fast Pipeline
```

Query Analysis 不消耗 Answer Repair 预算。

---

# 10. 单次 Retrieval Execution

实现薄内部值：

```yaml
SearchExecution:
  execution_id:
  request:
  raw_response:
  product_response:
```

使用现有：

```text
ProductSearchService.search_with_raw()
```

每个标准化后不同的 Query 只能调用一次。

Evidence Materializer：

- 接收 `SearchExecution` 或其中的权威 Raw Hit；
- 不接收自由 Query；
- 不调用 Product Search；
- 不调用 Raw Search；
- 不隐式重试 Retrieval。

现有：

```text
EvidenceSearchService.search_library(request)
```

可以保留为兼容包装：

```text
request
→ search_with_raw
→ materialize existing execution
```

新的 Ask 主路径必须显式传递同一次 Search Execution。

测试必须用 Spy 或等价机制证明：

```text
N 个 distinct queries
→ exactly N retrieval executions
```

---

# 11. Evidence Materialization

直接复用已有：

- `SourceArtifactReference`；
- `SourceVersionBinding`；
- `load_source_artifact()`；
- Exact Chunk Replay；
- `map_retrieval_chunk()`；
- Timeline Run；
- Segment Identity；
- Source Version Authority；
- B 站 Jump URL。

不得使用 Product Search 展示 Excerpt 作为事实 Evidence。

目标合同或等价表达：

```yaml
TranscriptEvidenceSpan:
  citation_id:
  citation_identity_version:
  video_id:
  bvid:
  title:
  source_type:
  source_language:
  source_artifact_id:
  source_version:
  source_version_authority:
  timeline_run_id:
  segment_ids:
  segment_ordinals:
  start_time:
  end_time:
  quote_text:
  jump_url:
  parent_chunk_ids:
  retrieval_provenance:
```

只有满足现有 Authority、Mapping 和 Timeline 合同的 Segment 才能生成 Span。

---

# 12. Stable Citation

定义：

```text
CITATION_IDENTITY_VERSION = "v4-citation-identity-v1"
```

Hash Preimage：

```yaml
citation_identity_version:
source_artifact_id:
source_version:
timeline_run_id:
ordered_segment_ids:
```

建议输出：

```text
citation_v1_<sha256>
```

Canonicalization：

1. 所有 Segment 属于同一 Source Artifact；
2. 所有 Segment 属于同一 Source Version；
3. 所有 Segment 属于同一 Timeline Run；
4. 根据权威 Segment Ordinal 排序；
5. Ordinal 必须严格递增；
6. 重复 Segment 被拒绝；
7. 声明连续的 Span 必须保持连续；
8. 使用已有 `canonical_json()`；
9. 不得按不透明 Segment ID 字符串排序。

Citation Identity 禁止包含：

- Query；
- Rewrite；
- Rank；
- Raw Score；
- Retrieval Method；
- Product Rank；
- Parent Chunk Rank；
- Candidate Builder；
- Selector；
- UI Citation Number。

至少测试：

- Retrieval Method 改变不改变同一 Evidence Citation；
- Rank 改变不改变 Citation；
- Source Version 改变会改变 Citation；
- Segment 顺序非法会被拒绝；
-同一 Canonical Span 重复计算得到同一 Citation。

---

# 13. 事实 Span 与展示 Context

明确区分：

```yaml
factual_support_segments:
  included_in_model_context: true
  included_in_citation_identity: true

display_context_before_after:
  included_in_model_context: false
  included_in_citation_identity: false
```

如果相邻 Segment 确实进入模型事实 Context，它们属于 factual support span。

如果只是用户展开字幕卡时显示的前后文，它们不改变 Citation Identity。

Goal 1 API 可以返回前端未来需要的显示字段，但不实现正式 `/ask` 页面。

---

# 14. Stale Evidence

如果 Retrieval Hit 无法绑定当前 Source Version：

```text
不得生成 Citation
→ 记录 stale reason
→ 跳过 Hit
→ 继续处理其他 Hit
```

Stale Evidence 禁止进入：

- `TranscriptEvidenceSpan`；
- Context；
- Answer；
- Citation Display。

如果没有任何有效 Evidence：

```yaml
status: insufficient
answer_blocks: []
termination_reason: evidence_unavailable
limitations:
  - 没有找到可绑定当前字幕版本的有效证据
```

Ask Runtime 不自动修复或重建索引。

最终响应序列化前，再验证一次所有使用中的 Source Version。不要为极小 TOCTOU 窗口新增锁平台、Checkpoint 或持久化事务系统。

---

# 15. Multi-query Deduplication and Fusion

每个 Query 独立完成：

```text
SearchExecution
→ Evidence Materialization
```

随后按权威 Evidence Identity 去重。

初始融合采用确定性的 Rank-only 方法：

- 不比较不同 Execution 的不可比 Raw Score；
- 同一 Evidence 的多 Query Provenance 合并；
- 重复命中可以提高 Context Selection 优先级；
- 同一 Evidence 只进入 Context 一次；
- 可以复用现有 RRF 思路；
- 不增加 Learned Reranker；
- 不增加 MMR；
- 不预设视频配额。

融合只影响 Context Selection，不影响 Citation Identity。

---

# 16. Transcript-only Context

事实模型输入只包含：

- 用户原始 Query；
- 必要的 normalized intent；
- 已验证的 `TranscriptEvidenceSpan`；
- Stable Citation ID；
- Citation Allowlist；
- Answer Schema；
-明确的 Grounding 约束。

禁止进入事实 Context：

- AI Summary；
- Description；
- User Notes；
- Cleaned Transcript；
- AI Chapter Summary；
- Stale Hit；
- Product Search Display Excerpt；
-未映射 Raw Hit；
- Eval Gold。

标题、BVID 等仅可作为 Citation 展示元数据，不能被包装成事实段落。

Context Builder 负责：

- Evidence Identity 去重；
-重叠 Span 合并；
-同 Source/Version/Timeline 的有界连续合并；
-每 Span Budget；
-总 Context Budget；
-确定性排序；
-截断记录；
-最终 Citation Allowlist。

首版不做自动迭代 Context Compaction。

---

# 17. Grounded Answer

使用 DeepSeek 逻辑角色：

```text
grounded_answer
```

一次 Answer Call 输出：

```yaml
status:
answer_blocks:
limitations:
```

Prompt 必须要求：

-只使用 Evidence Context；
-只使用允许的 Citation ID；
-每个 Answer Block 至少有一个 Citation；
-不同证据集支持的独立事实优先拆成不同 Block；
-证据不足时输出 `partial` 或 `insufficient`；
-不得使用模型记忆补足；
-不得引用 Navigation 内容；
-不得生成自由 Answer；
-不得生成平行 Claims。

Runtime 可以确定性降级状态，但不能把无效结果升级为 `complete`。

---

# 18. 两层确定性 Validation

## 18.1 Schema Validation

检查：

- JSON 可解析；
- Pydantic/Schema 合法；
-字段完整；
- Enum 合法；
- Answer Block 类型合法；
- Citation ID 列表合法；
- Limitations 类型合法；
-没有额外自由 `answer` 或 `claims`。

## 18.2 Citation and Evidence Validation

检查：

-每个非空 Answer Block 至少有一个 Citation；
- Citation ID 位于当前 Allowlist；
- Citation 无重复；
- Source Version 当前有效；
- Segment 全部存在；
- Segment 属于同一 Artifact/Version/Timeline；
- Ordinal 顺序合法；
- Quote Text 能从 Segment 重建；
-时间范围能从 Segment 重建；
- Jump URL 对应 Citation Start Time；
-没有 Navigation-only Citation。

不在线判断：

-语义是否完全支持；
-答案是否覆盖问题所有方面；
-文风是否最佳。

这些进入轻量离线 Eval。

---

# 19. One Repair and Fail-closed

第一次 Answer 未通过验证时，最多 Repair 一次。

Repair 输入：

-相同 Query；
-相同 Evidence Context；
-相同 Citation Allowlist；
-相同 Schema；
-确定性错误代码和字段路径。

Repair 禁止：

-重新 Retrieval；
-获取新 Evidence；
-引入新 Citation；
-把未知 ID 随意替换为允许 ID；
-增加 Context 中不存在的事实；
-绕过完整验证。

Repair 后重新运行全部验证。

若仍然失败：

```yaml
status: insufficient
answer_blocks: []
termination_reason: provider_error
```

首版不自动删除非法 Block 后保留其他 Block，不做 Partial Block Salvage。

---

# 20. Status and Termination

```text
status
→ answer sufficiency

termination_reason
→ runtime stop cause
```

`complete`：

-有有效 Evidence；
-所有 Block 合法；
-模型声明主要问题已覆盖；
-没有显式材料性缺口。

`partial`：

-至少一个合法 Answer Block；
-只回答了问题的一部分；
- `limitations` 明确剩余缺口；
-所有返回 Block 仍然完整通过验证。

`insufficient`：

-没有有效 Evidence；
-所有相关 Evidence stale；
- Answer/Repair 最终失败；
-无法返回任何合法 Block。

`partial` 不是格式错误后的垃圾回收状态。

---

# 21. DeepSeek Provider 薄扩展

复用现有 `OpenAICompatibleProvider`。

只增加 Goal 1 所需能力，例如：

```text
generate_structured(
    role,
    messages,
    response_schema
)
```

逻辑角色：

```text
query_analysis
grounded_answer
```

支持：

-一般 Messages；
- Pydantic Structured Output；
-角色化 Prompt/Timeout/Output Budget；
-必要的 Thinking/Sampling 参数；
-响应 Usage、Latency、Finish Reason；
-有界 Retryable Transport Retry；
-类型化 Provider Error。

不建设通用 Provider SDK，不要求 Native Tool Calling。

不得在日志、测试快照或提交中暴露 API Key。

---

# 22. API

增加：

```text
POST /api/ask
```

Goal 1 只接受：

```yaml
mode: fast
```

`mode: deep` 返回明确的类型化未实现错误；不能静默回退到 Fast。

不创建最终 `/ask` 页面。正式 Fast/Deep 页面和 Search Evidence Card 复用属于 Goal 3。

现有：

```text
GET /search
POST /api/search
```

必须保持兼容。

---

# 23. Lightweight Trace

实现薄 `AskRunTrace` 或等价结构，以 `run_id` 关联已有 Retrieval Trace。

用户 `trace_summary` 只包含有帮助的有界字段，例如：

```yaml
query_count:
retrieval_count:
valid_evidence_count:
stale_evidence_count:
context_span_count:
context_truncated:
repair_used:
latency_ms:
termination_reason:
```

开发者结构化事件可以包含：

- Query Analysis 摘要；
- Rewrite；
- Search Execution ID；
- Retrieval Trace ID；
-命中和 Mapping 计数；
- Stale Reasons；
- Evidence Dedup/Fusion；
- Context Drop/Truncation；
- Provider Usage；
- Repair Error；
- Citation Validation Error；
-内部错误分类。

首版使用：

-内存 Run Trace；
-响应 Trace Summary；
-结构化日志；
-已有 Retrieval Trace。

不增加 OTel、Langfuse、LangSmith 或独立 Trace Platform。

---

# 24. 实施阶段与退出条件

## Phase 1 — Contracts

完成：

- Ask Request/Response；
- Answer Block；
- Citation；
- Status；
- Termination Reason；
- Query Analysis Schema；
- Citation Identity Version。

退出条件：

-合同可稳定序列化；
-非法 Enum/字段可确定性拒绝；
-不存在自由 Answer/Claims 双事实源。

## Phase 2 — SearchExecution and Materializer

完成：

-单次 Search Execution；
- Materializer 拆分；
-兼容 Wrapper；
- Stale Skip；
- Stable Citation。

退出条件：

-一次 Raw Retrieval 能直接生成当前字幕 Evidence；
-每个 Query 恰好一次 Retrieval；
- Stale Hit 不能进入 Citation。

## Phase 3 — Query Analysis and Multi-query

完成：

-一次 Query Analysis；
-原 Query 保留；
- Rewrite 上限；
-标准化去重；
-失败退化；
- Rank-only Fusion。

退出条件：

-最多一次分析调用；
-最多三个不同 Query；
-同一 Evidence 只进入 Context 一次。

## Phase 4 — Context Builder

完成：

- Transcript-only Context；
- Evidence 合并和预算；
-事实/展示 Context 分离；
- Citation Allowlist；
-截断 Trace。

退出条件：

- Navigation 内容无法进入事实 Context；
-所有 Context Citation 可重建。

## Phase 5 — Answer, Repair, Validation

完成：

- Grounded Answer；
- Schema Validation；
- Citation Validation；
-最多一次 Repair；
- Repair Failure Fail-closed；
-最终 Source Version Revalidation。

退出条件：

-非法 Citation 不可能进入用户响应；
-所有返回 Block 均有 Citation；
- Complete/Partial/Insufficient 均有测试。

## Phase 6 — Fast Ask API

完成：

- Application Wiring；
- `POST /api/ask`；
- Fast-only Mode；
-类型化错误；
- Trace Summary。

退出条件：

-真实 HTTP 请求完成整条 Pipeline；
-现有 Search API 不回归。

## Phase 7 — Vertical Slice

完成：

-全量相关测试；
-真实语料运行；
-真实 DeepSeek 运行；
-延迟、Usage、Citation、Repair 和失败记录。

退出条件：

-达到本文件第 27 节完成条件；
-已知限制明确返回主 Session。

---

# 25. 测试要求

新增测试应按职责组织，避免复制大型历史 Eval Harness。

至少覆盖：

```text
Ask contracts
Stable Citation identity
Canonical Segment ordering
Source mutation invalidation
Single Retrieval execution
Stale Evidence skip
Navigation/fact Context isolation
Multi-query deduplication
Context budgets
Answer Block citation requirement
Unknown Citation rejection
One-repair budget
Repair failure fail-closed
Final Source Version revalidation
Complete / partial / insufficient
Fast Ask API
Existing Search regression
```

建议测试文件可以是：

```text
tests/test_v4_ask_contracts.py
tests/test_v4_search_execution.py
tests/test_v4_context_and_citations.py
tests/test_v4_grounded_answer.py
tests/test_v4_fast_ask_api.py
```

具体拆分可以根据代码规模调整。

必须重跑此前相关基线测试，并运行所有新增 V4 测试。

在影响范围允许时运行全套测试；如果全套测试耗时或环境依赖过大，至少运行覆盖改动路径的完整定向集合，并在结果中明确未运行部分。

---

# 26. 真实 Vertical Slice

使用少量真实问题覆盖：

-单视频直接事实；
-跨视频综合；
-同义改写；
-无相关 Evidence；
-部分可回答；
-多 Query 重复命中；
-长 Context；
- Stale Evidence；
-模型格式错误或非法 Citation 的可控测试。

记录：

```yaml
query:
status:
termination_reason:
answer_block_count:
citation_count:
query_analysis_calls:
retrieval_executions:
answer_calls:
repair_calls:
latency_ms:
token_usage:
limitations:
observed_failure:
```

不得读取或暴露历史 Case-level Eval Gold、Expected Label、Gold Span 或密封结果。

如果真实 DeepSeek 配置、Keychain 权限或网络不可用：

1. 完成所有确定性和 Mock Provider 测试；
2. 明确记录真实运行阻塞；
3. 返回主 Session/用户请求授权或环境处理；
4. 不得声称 Goal 1 已完整完成。

---

# 27. Goal 1 完成条件

只有以下条件全部满足，才能报告 Goal 1 完成：

- Fast Ask API 可以真实运行；
- Query Analysis、Retrieval、Evidence、Context、Answer 完整接通；
-每个不同 Query 只执行一次 Retrieval；
- Materializer 不会自行搜索；
-事实 Context 只包含当前版本原字幕；
- Stale Evidence 无法进入 Citation；
- Citation 使用版本化 Canonical Identity；
-事实 Span 与展示 Context 分离；
-所有 Answer Blocks 都有允许的 Citation；
-最终正文完全由 Answer Blocks 生成；
-最多一次 Repair；
- Repair 后仍失败整体 Fail-closed；
- Complete、Partial、Insufficient 均有测试；
- Citation 可还原字幕文本、时间和 B 站跳转；
-现有 `/search` 与 Evidence 基线保持通过；
-完成少量真实 Query Vertical Slice；
-记录延迟、调用数、Usage 和已知限制；
-没有引入 LangGraph、Agent、Runtime Semantic Judge 或新平台。

不得仅因：

-代码已写完；
- Mock 测试通过；
-预算接近耗尽；
-真实运行暂时不可用；

就声称 Goal 1 完成。

---

# 28. Escalation 条件

遇到以下情况，停止相关扩展并返回主 Session：

-需要改变共享 Ask Contract；
-需要改变 `status` 或 `termination_reason` 语义；
-需要允许 AI Summary/Notes/Cleaned Transcript 进入事实 Context；
-发现每 Query 单次 Retrieval 无法成立；
-需要引入新框架或大型依赖；
-需要 Runtime Semantic Judge；
-需要改变 Citation Authority；
-需要让 Repair 新增 Retrieval；
-需要实现 Agentic Loop；
-需要开始 Goal 2；
-发现现有 Source Version/Segment Identity 与本 Prompt 的源码事实冲突；
-用户已有修改与 Goal 1 代码范围发生不可安全合并的冲突。

以下内容不需要 Escalation：

-模块或函数的具体命名；
-在建议 `ask/` 包内合并或拆分小文件；
-测试文件组织；
- Prompt 文案迭代；
-不改变合同的内部类型；
-基于真实运行调整非永久的 Context 字符预算或 Timeout；
-修复 Goal 1 直接暴露的小型兼容问题。

---

# 29. 禁止事项

本 Goal Session 不得：

-实现 Goal 2；
-引入 LangGraph；
-实现 `/ask` 最终页面；
-重做 `/search`；
-建立独立 Navigation Index；
-增加 Reranker 或 MMR 作为默认前置；
-引入 Native Tool Calling；
-增加 Runtime Semantic Judge；
-复活 Candidate Builder/Selector 作为 Ask 主路径；
-建立 Provider/Citation/Trace/Eval Platform；
-建立大型 V3.5 式治理文件；
-读取 Eval Gold；
-创建新的 Goal；
-擅自修改 `V4_MASTER_STATE.md` 或 `V4_DECISION_LEDGER.md`；
-重写无关历史代码；
-提交或输出 API Key、Token、Cookie 或本地秘密。

---

# 30. 工作方式

- 先完成可运行的纵向最小链，再增加非阻塞优化；
- 保持现有公开行为兼容；
-优先复用已有 Source/Evidence 资产；
-每个阶段都先写或更新相应测试；
-不要用 Prompt 代替确定性预算和验证；
-不要把外部框架示例直接复制成拾流架构；
-发现真实失败时记录证据，不凭假设扩展范围；
-保持工作区中的用户修改；
-使用非破坏性 Git 操作。

---

# 31. 最终返回主 Session 的报告

完成或遇到真实阻塞时，必须返回：

## A. Outcome

- Goal 是否完成；
-用户实际获得什么能力；
-哪些完成条件未满足。

## B. Code Changes

-新增和修改的核心文件；
-关键合同；
-主要数据流；
-兼容处理。

## C. Tests

-运行的命令；
-通过、失败、跳过数量；
-现有 Warning；
-未运行测试及原因。

## D. Real Runs

-真实 Query 类型；
-状态和停止原因；
- Citation 结果；
-延迟和模型用量；
-成功与失败案例；
-不得暴露任何历史 Eval Gold。

## E. Scope Audit

分别列出：

```yaml
must_build_completed:
in_goal_support_completed:
deferred_untouched:
```

## F. Risks and Open Issues

只列出有真实证据的问题：

- Block 粒度；
- Repair 成功率；
- Context 冗余；
- Stale 频率；
-延迟和成本；
-需要主 Session 决策的冲突。

## G. Suggested Master State Update

只提出建议，不直接修改主 Session 的 State 或 Ledger。

---

# 32. 启动指令

完成必读文件、定向源码检查和基线测试后，直接开始 Goal 1 实施。

不要重新讨论已经接受的产品和架构决定。不要创建新平台。不要扩大到 Goal 2。

```text
完成 Fast Grounded RAG 纵向闭环
→ 用真实字幕和真实 DeepSeek 验证
→ 将代码、测试、运行结果和限制返回主 Session
```
