# Shiliu V4 Goal 1 Implementation Report

```yaml
goal: Goal 1 — Complete Grounded RAG
implementation_status: complete
integration_review: accepted
integration_repair: accepted
date: 2026-07-29
branch: codex/v4-main
```

## A. Outcome

Goal 1 — Complete Grounded RAG 已完成实施、验证和主 Session
Integration Review。

用户现在可以通过 `POST /api/ask` 获得：

- Fast Query Analysis 与最多两个 Rewrite；
- 每个不同 Query 恰好一次 Retrieval；
- 当前原字幕 Evidence 物化与 Stale Skip；
- Transcript-only Context；
- 结构化 Answer Blocks；
- 段落级 Stable Citation、原字幕、时间范围和 B 站跳转；
- `complete / partial / insufficient`；
- 最多一次同 Context Repair；
- 最终 Source Version 复验；
- 有界 Trace Summary。

`deep` 模式明确返回 HTTP 501 类型化错误，没有静默回退。

## B. Code Changes

### 核心实现

- `src/shiliu/ask/contracts.py`
- `src/shiliu/ask/service.py`
- `src/shiliu/ask/evidence.py`
- `src/shiliu/ask/citations.py`
- `src/shiliu/ask/context.py`
- `src/shiliu/ask/answer.py`
- `src/shiliu/ask/validation.py`
- `src/shiliu/ask/query_analysis.py`

### 接线与兼容

- `src/shiliu/evidence/search.py`
  - 增加 `SearchExecution`；
  - 拆分 `execute_search()` 与 `materialize_execution()`；
  - 保留 `search_library()` 兼容包装。
- `src/shiliu/llm.py`
  - 增加角色化 Structured Output；
  - Pydantic Schema 校验；
  - Usage、Latency、Finish Reason 和 Retry Count；
  - 一次有界 Retryable Transport Retry。
- `src/shiliu/app.py`
  - 增加惰性 `AskService` Wiring；
  - 增加 `query_analysis` 和 `grounded_answer` Provider 角色配置。
- `src/shiliu/web.py`
  - 增加 `POST /api/ask`；
  - 增加内存 Trace 查询；
  - `deep` 返回类型化未实现错误。
- `src/shiliu/retrieval/orchestrator.py`
  - 修复纯 Lexical 新数据库缺少 Dense Meta 表时的兼容问题。
- `scripts/run_v4_goal1_vertical_slice.py`
  - 使用本机数据库临时只读快照执行真实字幕、真实 Provider Vertical
    Slice；
  - 不修改真实产品数据库；
  - 不输出 API Key 或私人字幕正文。

没有修改：

- `V4_MASTER_STATE.md`
- `V4_DECISION_LEDGER.md`
- `V4_DESIGN_PROPOSAL.md`
- `V4_G1_EXECUTION_PROMPT.md`

当前改动尚未提交。

## C. Tests

### 修改前基线

```text
136 passed
1 existing Starlette/httpx deprecation warning
```

命令：

```bash
.venv/bin/python -m pytest \
  tests/test_product_search_api.py \
  tests/test_evidence_contracts.py \
  tests/test_evidence_stage1b.py \
  tests/test_search_enrichment.py \
  tests/test_v1.py \
  tests/test_boundaries_and_web.py
```

### V4 与原定向回归

```text
159 passed
1 existing Starlette/httpx deprecation warning
```

累计新增 23 个 V4 测试，覆盖：

- Ask Contract；
- Stable Citation Identity；
- Canonical Segment Ordering；
- Source Version Mutation；
- 每 Query 单次 Retrieval；
- Materializer 不执行搜索；
- Stale Evidence Skip；
- Navigation/Fact Context 隔离；
- Multi-query Deduplication；
- Context Budget；
- Answer Block Citation Requirement；
- Unknown Citation Rejection；
- One-repair Budget；
- Repair Failure Fail-closed；
- Final Source Version Revalidation；
- Complete、Partial、Insufficient；
- Fast Ask API；
- Deep 类型化未实现错误；
- 现有 Search 回归。

新增测试文件：

```text
tests/test_v4_ask_contracts.py
tests/test_v4_search_execution.py
tests/test_v4_context_and_citations.py
tests/test_v4_fast_ask_api.py
```

### 最终默认全套

```text
1428 passed
4 deselected
1 existing Starlette/httpx deprecation warning
```

命令：

```bash
.venv/bin/python -m pytest
```

同时通过：

```text
python compileall
git diff --check
```

未运行的四项由默认 Pytest Marker 排除：

```text
external_artifact
live_provider
```

真实 Provider 验证由本报告下一节所述 Vertical Slice 单独执行。

## D. Real Runs

执行命令：

```bash
.venv/bin/python scripts/run_v4_goal1_vertical_slice.py
```

运行使用：

- 本机产品数据库的临时只读快照；
- 当前原字幕资产；
- 本地 Qwen Retrieval Model；
- 当前配置的真实 DeepSeek Provider；
- 非 Eval Gold 的普通真实问题。

### 首轮观察

首轮三个请求均正确 Fail-closed 为：

```yaml
status: insufficient
termination_reason: provider_error
answer_blocks: []
citations: []
```

真实失败原因为 DeepSeek 输出了合同外字段或 Enum：

```text
citations
block_type
not_found
```

系统没有把这些非法字段或 Citation 返回给用户。随后根据真实失败：

- 在 Answer Prompt 中加入精确 JSON Schema；
- 明确 `citation_ids` 字段；
- 明确只允许 `complete / partial / insufficient`；
- 明确禁止 `citations / block_type / not_found / answer / claims`；
- 对 Repair 使用相同精确 Schema；
- 补记无效输出的 Provider Metadata。

### 第二轮结果

| Query 类型 | Status | Termination | Blocks | Citations | Repair | Latency |
|---|---|---|---:|---:|---:|---:|
| MCP 直接事实 | `partial` | `answer_ready` | 3 | 3 | 0 | 39.95s |
| 跨视频上下文管理 | `partial` | `answer_ready` | 8 | 7 | 1 | 112.12s |
| 不存在的协议 | `insufficient` | `answer_ready` | 0 | 0 | 0 | 37.56s |

每个请求均满足：

```yaml
query_analysis_calls: 1
retrieval_executions: 3
answer_calls: 1
repair_calls: 0_or_1
iterative_search: false
```

所有返回 Citation 均验证：

- Quote Text 可从当前原字幕 Segment 重建；
- Start/End Time 可重建；
- Jump URL 对应 Citation Start Time；
- Source Version 当前有效；
- Segment 属于同一 Artifact、Version 和 Timeline；
- Citation ID 位于当前 Context Allowlist。

### Provider Usage

#### MCP 直接事实

```yaml
query_analysis:
  prompt_tokens: 83
  completion_tokens: 77
  total_tokens: 160
grounded_answer:
  prompt_tokens: 7678
  completion_tokens: 2038
  total_tokens: 9716
  reasoning_tokens: 1577
```

#### 跨视频上下文管理

```yaml
query_analysis:
  prompt_tokens: 84
  completion_tokens: 77
  total_tokens: 161
successful_grounded_answer_response:
  prompt_tokens: 7773
  completion_tokens: 2817
  total_tokens: 10590
  reasoning_tokens: 1781
repair_used: true
```

该例的另一次 Provider 调用未返回完整 Usage Metadata。

#### 不存在的协议

```yaml
query_analysis:
  prompt_tokens: 88
  completion_tokens: 94
  total_tokens: 182
grounded_answer:
  prompt_tokens: 7871
  completion_tokens: 290
  total_tokens: 8161
  reasoning_tokens: 247
```

## E. Scope Audit

```yaml
must_build_completed:
  - Fast Grounded RAG 完整闭环
  - 共享 Ask Contract
  - Query Analysis 与 bounded rewrites
  - 每 Query 单次 Retrieval
  - 当前原字幕 Evidence Materialization
  - Stable Citation 与版本化身份
  - Transcript-only Context
  - Grounded Answer
  - One Repair and Fail-closed
  - Deterministic Citation Validation
  - Final Source Version Revalidation
  - POST /api/ask
  - Complete / Partial / Insufficient

in_goal_support_completed:
  - SearchExecution 与无搜索 Materializer
  - Multi-query Deduplication 和 Rank-only Fusion
  - Stale Evidence Trace
  - Context Budget 和 Truncation Trace
  - Provider Structured Output
  - Provider Usage、Latency、Finish Reason 和 Retry
  - 内存 Ask Trace 与响应 Trace Summary
  - 真实 Vertical Slice Runner

deferred_untouched:
  - Goal 2
  - LangGraph
  - Agentic Loop
  - 最终 /ask 页面
  - Independent Navigation Index
  - Reranker
  - MMR
  - Runtime Semantic Judge
  - Token Streaming
  - Context Compaction
  - Provider Platform
  - Citation Platform
  - Trace Platform
  - Eval Platform
```

## F. Risks and Open Issues

以下问题均有真实运行证据：

1. **Provider 延迟**

   实测总延迟约 37.6–112.1 秒，Provider 是主要成本。

2. **Context Budget**

   三个真实请求均发生 Context Truncation。Grounded Answer Prompt 约为
   7.7k Tokens。

3. **Block 粒度和 Context 冗余**

   跨视频问题产生 8 个 Answer Blocks 和 7 个 Citations，后续轻量 Eval
   应检查是否过度拆分或存在内容重复。

4. **Repair 稳定性**

   一个跨视频问题使用一次 Repair 后成功。首轮三个请求则证明 Provider
   Schema 漂移确实存在；精确 Schema 已显著改善，但仍需继续观察 Repair
   频率。

5. **无关查询的 Retrieval 噪声**

   不存在的协议仍可能召回语义噪声，最终由 Grounded Answer 返回
   `insufficient / answer_ready`。这与“没有任何当前有效 Evidence”导致的
   `evidence_unavailable` 不同，属于当前状态与停止语义的预期组合。

6. **Usage 完整性**

   Provider 在未形成正常响应时可能无法提供完整 Usage；Trace 已显式区分
   初次失败和 Repair 成功，但不能伪造缺失 Usage。

以上均不是 Goal 1 完成阻塞项，应进入 Goal 3 的轻量 Eval 与产品优化，而不应
在 Goal 1 扩展为新平台。

## G. Suggested Master State Update

建议主 Session 在 Integration Review 后更新：

```yaml
goal_1:
  implementation: complete
  deterministic_tests: passed
  full_test_suite: passed
  real_vertical_slice: passed_with_observed_latency_and_context_risks
  integration_review: pending
```

建议记录的下一步：

```text
Main Session Integration Review
→ 检查 Goal 1 合同与 Scope
→ 接受或要求小型修正
→ 再决定是否启动 Goal 2
```

本 Goal Session 不直接修改 Master State 或 Decision Ledger。

## H. Integration Repair

```yaml
review_result:
  implementation: functionally_complete
  integration_review: changes_requested
repair_status: implemented_pending_re_review
date: 2026-07-29
```

主 Session Integration Review 要求两个有界修正：

1. 修正 Provider Failure 与 Answer Repair 的边界；
2. 将 Transport Retry 限定在 V4 Structured Runtime。

本节记录修正后的最终行为和验证结果。未修改共享 Ask Contract、`status`、
`termination_reason`、Goal 2 或任何 Master State / Decision Ledger。

### H.1 Provider Failure 与 Repair 最终边界

`GroundedAnswerService` 现在显式区分可修复和不可修复结果。

#### Repairable

只有以下情况允许进入最多一次 Repair：

1. Provider 已返回实际内容，但内容无法解析为 JSON 或未通过
   `GroundedAnswerDraft` Pydantic Schema；
2. Provider 已形成 `GroundedAnswerDraft`，但 Draft 未通过确定性
   Answer/Citation 校验，例如：
   - Unknown Citation；
   - Block Citation 重复；
   - Citation 不在当前 Allowlist；
   - Citation Source Version 或 Segment 重建失败；
   - `partial` 缺少 Limitations。

Provider Schema Failure 只有同时满足以下条件才视为可修复：

```yaml
provider_error_code: invalid_model_output
content_received: true
```

Repair 仍然只使用：

- 相同 Query；
- 相同 Evidence Context；
- 相同 Citation Allowlist；
- 相同 JSON Schema；
- 确定性错误代码和字段路径。

#### Non-repairable

以下故障直接 Fail-closed，不进入 Repair：

- Provider Factory 初始化失败；
- Network / Timeout 在 V4 允许的传输重试耗尽后仍失败；
- Authentication；
- Insufficient Balance；
- Forbidden；
- Model / Endpoint Not Found；
- Bad Provider Config；
- Context Too Large；
- Output Budget Exhausted；
- Empty Model Output；
- Provider Envelope / Schema 故障，没有形成可修复内容；
- 其他没有实际结构化输出的 Provider/Transport Failure。

返回：

```yaml
status: insufficient
answer_blocks: []
citations: []
termination_reason: provider_error
repair_used: false
```

Provider 故障不再被记录为 `provider_output_invalid` 或 Answer Validation
Failure。

### H.2 Trace 语义

Grounded Answer Trace 现在显式记录：

```yaml
answer_calls:
repair_calls:
answer_provider_call_count:
transport_retry_count:
provider_error_code:
initial_provider_error_code:
repair_used:
```

典型 Provider/Transport Failure：

```yaml
answer_calls: 1
repair_calls: 0
answer_provider_call_count: 1
transport_retry_count: 0_or_1
repair_used: false
provider_error_code: provider_network_or_typed_provider_error
```

其中：

- `answer_calls` 表示 Grounded Answer Phase 的逻辑执行次数；
- `repair_calls` 表示结构化 Answer Repair 次数；
- `answer_provider_call_count` 表示逻辑 Provider 调用次数；
- `transport_retry_count` 单独表示底层 HTTP Transport Retry 次数。

Provider Factory 在逻辑 Provider 调用发生前失败时：

```yaml
answer_calls: 1
repair_calls: 0
answer_provider_call_count: 0
transport_retry_count: 0
repair_used: false
```

如果 Provider 返回了部分 Metadata，则保留：

- Error Code；
- Retry Count；
- Latency；
- Finish Reason；
- Response ID；
- Usage。

不存在的 Usage 保持缺失，不生成零值或伪造 Token 数。

### H.3 V4 与历史 Provider Retry 行为

`OpenAICompatibleProvider._generate_response()` 现在使用显式且默认关闭的：

```python
transport_retries: int = 0
```

只有：

```text
generate_structured(query_analysis / grounded_answer)
```

显式传入：

```text
transport_retries = 1
```

因此最终行为是：

| Provider 路径 | 逻辑行为 | 最大 HTTP 请求数 |
|---|---|---:|
| V4 `generate_structured()` | Retryable Transport Failure 可重试一次 | 2 |
| 历史 `complete_json()` | 保持原有单次请求 | 1 |
| 历史 `complete_raw()` | 保持原有单次请求 | 1 |
| 历史 `test_connection()` | 保持原有单次请求 | 1 |

没有重构历史 Transcript、Summary、Taxonomy 或 Single-flight / Recovery
Pipeline，也没有建设通用 Provider SDK。

### H.4 Integration Repair 新增测试

本轮新增 6 个测试，累计 V4 新增测试为 23 个。

新增覆盖：

1. Grounded Answer 网络故障不进入 Repair；
2. Authentication 非 Retryable Error 不进入 Repair；
3. Provider Factory Failure 不进入 Repair；
4. 上述失败返回 `insufficient / provider_error`；
5. `repair_used == false`；
6. Answer Call、Repair Call、Provider Call 和 Transport Retry Trace 精确；
7. V4 Structured Runtime 的 Retryable Failure 最多两次 HTTP 请求；
8. 历史 `complete_json()` 同类故障只请求一次；
9. 历史 `complete_raw()` 同类故障只请求一次；
10. 收到非法结构化输出仍允许一次 Repair；
11. Unknown Citation 仍允许一次 Repair；
12. Repair 后再次失败仍整体 Fail-closed。

### H.5 Integration Repair 验证

指定定向集合：

```text
159 passed
1 existing Starlette/httpx deprecation warning
```

命令：

```bash
.venv/bin/python -m pytest \
  tests/test_product_search_api.py \
  tests/test_evidence_contracts.py \
  tests/test_evidence_stage1b.py \
  tests/test_search_enrichment.py \
  tests/test_v1.py \
  tests/test_boundaries_and_web.py \
  tests/test_v4_ask_contracts.py \
  tests/test_v4_search_execution.py \
  tests/test_v4_context_and_citations.py \
  tests/test_v4_fast_ask_api.py
```

默认全套：

```text
1428 passed
4 deselected
1 existing Starlette/httpx deprecation warning
```

命令：

```bash
.venv/bin/python -m pytest
```

同时执行：

```bash
git diff --check
```

### H.6 Real Provider Smoke

本次 Integration Repair 没有改变正常成功路径：

- Query Analysis 正常成功路径未变；
- Grounded Answer 正常成功路径未变；
- Answer/Citation Contract 未变；
- Retrieval、Evidence、Context 和最终 Source Version Validation 未变。

因此本轮没有重新执行真实 Provider Smoke。此前三条真实 DeepSeek Vertical
Slice 仍作为 Goal 1 的真实运行证据，其结果已完整记录在本报告 D 节。

### H.7 当前非阻塞风险

以下既有风险未在本次有界修正中处理：

- Provider 总延迟；
- Context Truncation；
- Answer Block 粒度；
- Retrieval 语义噪声；
- Repair 的真实触发频率；
- Provider Failure 时可能缺失 Usage。

这些问题不属于本次 Integration Repair 范围，也未借本轮改动扩展实现。

当前状态仍为：

```yaml
goal_1:
  implementation: complete
  integration_review: accepted
  integration_repair: accepted
```

## I. Main Session Integration Acceptance

主 Session 于 2026-07-29 完成第二次 Integration Review，并确认：

- 两项 Provider/Repair Blocking Finding 均已按冻结边界修正；
- Repairable 与 Non-repairable Provider Failure 的实现和 Trace 语义一致；
- V4 Structured Transport Retry 不再改变历史 Provider 调用行为；
- 主 Session 独立复跑 159 项定向测试和 1428 项默认全套测试，全部通过；
- `git diff --check` 通过；
- 此次修正不改变正常成功路径，因此接受此前三条真实 DeepSeek Vertical
  Slice 作为 Goal 1 的真实运行证据；
- Goal 1 未扩展到 LangGraph、Goal 2、`/ask` 页面或任何新平台。

正式结论：

```yaml
goal_1:
  status: complete
  integration_review: accepted
  blocking_findings_remaining: 0
```
