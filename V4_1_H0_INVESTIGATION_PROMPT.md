# Shiliu V4.1 H0 Investigation Execution Prompt

你正在启动一个独立的：

```text
Shiliu V4.1 H0 Investigation Session
拾流 V4.1 H0 有界工程调查 Session
```

本 Session 只执行：

```text
H0-A Provider Latency Attribution
+
H0-B Deep Decision Context Payload Audit
+
H0-C Fast Context Selection Diagnostics
```

H0 是 V4.1 的调查阶段，不是 H1/H2 实现阶段，不得直接修改正式 Fast/Deep
行为、选择 Provider 配置或实现完整 DecisionView。

---

# 1. Session Role

你在本 Session 中担任：

```text
V4.1 Investigation Engineer
Provider Experiment Owner
Decision Payload Auditor
Context Selection Diagnostics Owner
Evidence-preserving Measurement Reviewer
```

你向 Shiliu V4 Main Codex Session 返回调查证据和有界建议。你不能自行冻结 H1
或 H2 方案，也不能宣布某个候选配置进入正式 Runtime。

---

# 2. 权威输入

先完整阅读：

```text
SHILIU_V4_1_RUNTIME_AND_CONTEXT_HARDENING_PLAN.md
V4_MASTER_STATE.md
V4_DESIGN_PROPOSAL.md
V4_DECISION_LEDGER.md
V4_G1_IMPLEMENTATION_REPORT.md
V4_G2_IMPLEMENTATION_REPORT.md
V4_G3_IMPLEMENTATION_REPORT.md
```

其中：

- V4.1 Plan 是正式外部规划输入，但不是不可修改的实施 Spec；
- `V4_MASTER_STATE.md` 是当前 V4 状态权威；
- Design 和 Ledger 约束不能破坏的 V4 产品与架构边界；
- Implementation Report 只用于理解真实运行、已修复问题和验证基线。

不要读取或恢复 V0–V3.5 Case 级 Eval Gold、答案、失败详情或历史重型治理材料。

---

# 3. Baseline 与工作区

冻结 V4 Baseline：

```yaml
branch: codex/v4-main
commit: cbf264be2571c3d62775c064445de8a1ba17880a
remote: origin/codex/v4-main
v4_status: complete
```

开始时必须运行：

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git rev-parse origin/codex/v4-main
```

预期 Main Session 可能留下未跟踪的：

```text
SHILIU_V4_WEBGPT_PROJECT_HANDOFF.md
V4_1_H0_INVESTIGATION_PROMPT.md
```

这些文件属于 Main Session。必须保留，不得覆盖、删除或误判为 H0 实现产物。

在开始 H0 修改前：

1. 确认 `HEAD` 与冻结 Commit 完全一致；
2. 从该 Commit 创建并切换：

   ```text
   codex/v4.1-hardening
   ```

3. 不修改、Reset、Clean、Stash 或 Rebase 用户已有文件；
4. H0 Session 不 Stage、Commit、Push 或 Merge；
5. 最终由 Main Session 审查和处理 Git。

若分支已由 Main Session 创建，则复用，不得创建第二个分支。

---

# 4. V4.1 定位与不可破坏边界

V4.1 是：

```text
Minor Runtime and Context Hardening Release
```

不是：

- V5；
- 新产品版本；
- Provider 重选；
- Agent 架构重写；
- Deferred Backlog 清理。

H0 不得改变：

- `/ask` 与 `/search` 的产品分工；
- Fast 默认、Deep 显式选择；
- Fast 一轮式 Grounded RAG；
- Deep Independent Agentic Search；
- Fast/Deep 共享 Answer、Citation、Validation、Finalizer 和 Evidence UI；
- Transcript-only Fact Context；
- Navigation 不可 Citation；
- Stable Citation Identity；
- Source Version Final Revalidation；
- Deep 独立于 Candidate Builder；
- Fast 普通 Service Pipeline；
- Deep 薄 LangGraph `StateGraph`；
- 确定性预算和停止条件；
- Runtime 不使用 Semantic Judge。

---

# 5. 本轮源码事实

以下是 Main Session 已完成的 P0 源码核验。H0 必须独立复核，但不得回到未经
验证的假设。

## 5.1 Provider Role 事实

当前 `Application.provider()`：

```yaml
query_analysis:
  thinking: false
  reasoning_effort: null

agent_action:
  thinking: false
  reasoning_effort: null

grounded_answer:
  thinking: true
  reasoning_effort: high
```

`OpenAICompatibleProvider` 已能发送：

```yaml
thinking:
  type: enabled | disabled
reasoning_effort: high | max
```

当前 Provider Adapter 不接受 `low` 或 `medium`。因此：

- `thinking_off` 是当前可表达的真实候选；
- `reduced_reasoning` 不能因为规划文件提到就伪造；
- 只有在当前 Provider 的权威能力和本项目请求合同均证明存在稳定低档位时，
  才能纳入；
- H0 不得为了补一个实验 Variant 就先扩展正式 Provider Runtime。

## 5.2 Deep Decision Payload 事实

当前 `_decision_messages()` 已经是一个内嵌的、有上限的投影，不是把完整
`DeepSearchState` 直接序列化。

当前每轮主要发送：

```yaml
system:
  - DEEP_POLICY_INSTRUCTIONS
  - full AgentDecision JSON Schema

user:
  - question
  - open_questions
  - resolved_questions
  - last_action
  - last_observation_summary[:1000]
  - navigation_documents[-8:]
  - transcript_evidence[-12:]
  - visited_video_ids[-24:]
  - visited_segment_ids[-60:]
  - previous_queries[-24:]
  - remaining_budget
```

Navigation 中：

- `description[:400]`；
- `matched_excerpt[:400]`；
- `summary_sections[:4]`，但单 Section 当前没有显式字符上限。

Evidence 中：

- `quote[:500]`；
- 完整 `segment_ids` 列表；
- 最近最多 12 个 Span。

当前没有把：

- 完整历史 Observation 正文；
- 全部 Trace；
- 全部 247–357 个 Visited Segment；

直接发送给 Decision Provider。

H0 必须测量哪些现有上限仍造成膨胀，不能在报告中声称不存在的字段正在全文累积。

## 5.3 Fast Context 事实

当前 Fast：

```text
all materialized spans
→ fuse_evidence()
→ TranscriptContextBuilder
→ max 12 spans
→ max 2500 chars/span
→ max 12000 chars total
```

`fuse_evidence()` 已按 Stable Citation ID 去重，并累积 Retrieval Provenance；
Context Builder 还会合并同 Source/Version/Timeline 的 Overlap 或 Adjacent
Span。

因此 H0-C 必须区分：

- Raw Materialized Span；
- Fused Candidate Span；
- Fit/Merged Selected Span；
- Dropped/Truncated Span。

不得把所有 Truncation 都解释为简单 Top-K 截断。

---

# 6. 工作方式与 Phase 顺序

严格按：

```text
Phase 0：Baseline 与源码复核
→ Phase 1：Deterministic Instrumentation / Dry-run
→ Phase 2：H0-B Payload Audit
→ Phase 3：H0-C Context Diagnostics
→ Phase 4：冻结 H0-A Live Matrix 并请求授权
→ Phase 5：Fixed Request Replay
→ Phase 6：少量 End-to-End Validation
→ Phase 7：Report、Regression 与 Scope Audit
```

在所有不依赖 Provider 的代码、测试和 Dry-run 完成前，不得发起真实 Provider
调用。

---

# 7. H0-A — Provider Latency Attribution

## 7.1 Mission

H0-A 必须区分：

```yaml
latency_attribution:
  request_shape_effect:
  reasoning_effect:
  completion_effect:
  repair_effect:
  cache_effect:
  transport_or_service_variance:
  unresolved:
```

不得只给：

- “DeepSeek API 有问题”；
- “Thinking 必须关闭”；
- “Token 少所以配置更好”。

## 7.2 Fixed Request 类型

使用现有 `eval/v4_goal3_cases.json` 中普通 Query，选择四类：

```text
A. No-direct-support / Honest insufficient
B. Single-topic direct question
C. Cross-video complex question
D. Universal / Partial-support question
```

注意：

> A 类不是 `fused spans == 0`。

当前 Finalizer 在没有任何有效 Span 时会直接返回 `insufficient`，不会调用
Grounded Answer Provider。A 类应是：

```text
Context 中存在 Retrieval 样本
但没有能够直接支持目标问题的字幕 Evidence
```

这样才能真实测量 Answer Provider 的范围诚实、延迟和结构化行为。

不得创建 Gold Answer 或读取历史 Case 级 Gold。

## 7.3 固定请求的生成

Fixed Replay 必须固定：

- Model；
- Role；
- System/User Messages；
- Evidence Context；
- JSON Schema；
- `max_tokens`；
- Request Body 中除实验 Variant 外的其他字段；
- Source Version / Citation Allowlist；
- Prompt 顺序。

推荐在 H0 Runner 内：

1. 使用临时 SQLite Snapshot；
2. 使用现有普通 Query；
3. 使用确定性的 Scripted Query Analysis/Rewrite 计划；
4. 执行真实本地 Retrieval、Evidence Materialization 和 Context Builder；
5. 通过 Capture Provider 在发出网络请求前捕获 Grounded Answer Messages；
6. 将四个请求只保存在当前进程内；
7. 对相同内存请求执行 Variant Replay。

这样：

- 不需要为了生成 Fixed Request 先调用 Query Analysis Provider；
- 不受每次 Query Rewrite 波动影响；
- 请求仍来自当前 Retrieval/Evidence/Context/Answer 代码；
- 不把私人完整字幕 Prompt 写进仓库。

如果采用其他方式，必须证明：

- Fixed Request 在同一 Request ID 的所有 Trial 中字节级一致；
- 没有把此前 Response 中仅保留的 Citation 摘录误当成完整 Context；
- 没有因重新 Retrieval 使 Replay 失去可比性。

## 7.4 私有数据和结果边界

不得把以下内容写入 Git 工作区：

- 完整 Provider Messages；
- 完整 Evidence Context；
- 完整私人字幕；
- API Key；
- Authorization Header；
- Provider 原始隐藏推理；
- 无界 Raw Response。

Runner 只输出有界测量和哈希：

```yaml
request_id:
request_hash:
message_chars:
context_chars:
citation_allowlist_count:
source_version_hashes:
```

人工 Supportedness Review 如果需要完整 Citation，必须从当前 Source Version
临时重建，不把完整正文复制到报告。

## 7.5 Variant

第一层必选：

```yaml
baseline:
  thinking: true
  reasoning_effort: high

thinking_off:
  thinking: false
  reasoning_effort: null
  temperature: 0
```

条件候选：

```yaml
reduced_reasoning:
  include_only_if:
    - current provider has an authoritative stable lower setting
    - current adapter can express it without changing production behavior
    - a preflight confirms request acceptance
```

如果不满足，报告应写：

```yaml
reduced_reasoning:
  status: unavailable_in_current_provider_contract
```

不能把 `high → max` 叫做 Reduced Reasoning。

## 7.6 Trial 数和顺序

每个 Request / Variant：

```yaml
trials: 3
```

Variant 必须按轮次交错，避免所有 Baseline 先跑、Thinking Off 后跑造成：

- Cache Warm-up 偏差；
- Provider 时间段偏差；
- 服务负载偏差。

两 Variant 可采用：

```text
Round 1: baseline → thinking_off
Round 2: thinking_off → baseline
Round 3: baseline → thinking_off
```

三 Variant 使用轮转顺序。记录实际执行顺序和 UTC 时间。

不通过 Sleep 人为制造长等待。

## 7.7 必须使用当前 Answer 行为

每个 Trial 必须走当前：

```text
GroundedAnswerService.answer()
→ Initial Structured Call
→ Deterministic Validation
→ optional Same-context Repair
```

这样才能真实记录：

- First-pass Schema；
- Validation；
- Repair；
- Final Draft；
- Provider Invocation Count。

不得只调用裸 Chat Completion 后自行定义“成功”。

## 7.8 Provider Measurement

每个 Trial 记录：

```yaml
request_id:
sequence_index:
started_at_utc:
model:
role: grounded_answer
variant:
thinking:
reasoning_effort:
message_chars:
context_chars:
prompt_tokens:
cache_hit_tokens:
cache_miss_tokens:
completion_tokens:
reasoning_tokens:
latency_ms:
finish_reason:
schema_valid_first_try:
repair_required:
repair_succeeded:
provider_call_count:
retry_count:
status:
answer_block_count:
citation_count:
validation_error_codes:
provider_error_code:
```

Usage 字段缺失时记录 `null`，不得推测或填零冒充 Provider 数据。

## 7.9 质量复核

每个 Request / Variant 的三次 Trial 均保留确定性检查。

每个 Request / Variant 至少选择：

- 中位延迟 Trial；
- 最差质量或失败 Trial；

进行轻量人工：

```yaml
supportedness:
usefulness:
coverage:
status_honesty:
```

如果三次输出行为明显不同，应审阅全部三次。

人工审阅必须：

- 使用完整当前 Citation，而不是只看截断 excerpt；
- 不使用 Runtime Semantic Judge；
- 不创建 Gold Answer；
- 不把 `insufficient` 自动判为失败；
- 同时比较速度和质量。

## 7.10 分析方法

每个 Request / Variant 报告：

```yaml
latency_ms:
  min:
  median:
  max:
  range:
reasoning_tokens:
  min:
  median:
  max:
schema_first_pass_success:
repair_rate:
retry_rate:
```

分析：

- 同 Request、不同 Variant；
- 同 Variant、不同 Request Shape；
- Latency 与 Reasoning Tokens；
- Latency 与 Completion Tokens；
- Latency 与 Cache Miss；
- Repair 对总延迟；
- Retry/Network 对总延迟。

样本量很小，不做显著性检验，不声称 SLA 或因果已完全证明。

## 7.11 Live Provider 授权

真实 Provider 调用会发送：

- 四条普通 Query；
- 当前本机收藏中有界字幕 Evidence Context；
- JSON Schema 和 Grounded Answer Prompt；

到当前配置的 DeepSeek Provider。

在调用前必须向用户给出：

```yaml
fixed_requests: 4
variants:
trials_per_request_variant: 3
logical_trials:
max_provider_invocations_including_repair:
optional_reduced_reasoning:
data_sent:
result_files:
```

并获得显式授权。

默认两 Variant：

```yaml
logical_trials: 24
max_provider_invocations_including_repair: 48
```

如果加入 Reduced Reasoning：

```yaml
additional_logical_trials: 12
additional_max_provider_invocations_including_repair: 24
```

不得把“用户可以接受 Token 成本”解释成无限调用授权。

Provider Error 或网络失败必须保留。除每个 Variant 已批准的三次 Trial 外，不得
额外重采样。

## 7.12 End-to-End Validation

完成 Fixed Replay 并形成初步归因后：

1. 只选择 Baseline 和最多一个优选候选；
2. 使用相同四类 Query；
3. 运行完整 Fast：

   ```text
   Query Analysis
   → Retrieval
   → Evidence Materialization
   → Context Selection
   → Grounded Answer
   → Validation
   ```

4. 比较 Replay 优势能否转化为 `/ask` 改善。

End-to-End 是第二个独立授权点。执行前必须报告：

```yaml
candidate_variants:
end_to_end_runs:
max_query_analysis_calls:
max_grounded_answer_calls:
max_repair_calls:
data_sent:
```

最多：

```yaml
queries: 4
variants: 2
end_to_end_runs: 8
max_query_analysis_calls: 8
max_grounded_answer_initial_calls: 8
max_repair_calls: 8
```

若 Fixed Replay 没有安全优选候选，可以不执行候选 E2E，只保留 Baseline 或直接
结束 H0-A。不得为了完成矩阵强行选择候选。

---

# 8. H0-B — Deep Decision Context Payload Audit

## 8.1 Mission

解释：

```text
实际 agent_action Prompt
为什么从约 1k 增长到约 20k–28k Tokens
```

并提出一个候选：

```text
DeepRuntimeState
→ Deterministic DecisionViewProjector
→ AgentAction Provider
```

H0 只提出 Candidate DecisionView 和风险，不实施 H2。

## 8.2 不调用真实 Agent Provider 的优先方法

优先使用：

- 临时数据库 Snapshot；
- 真实本地 Navigation/Retrieval/Transcript Tool；
- Scripted AgentDecision；
- 当前 LangGraph/Reducer 状态流；
- Capture Provider；

构造至少：

```text
Navigation
→ Focused Transcript Search
→ Window Read
→ Replan
→ Finish
```

Capture Provider 必须捕获每轮实际传给 `agent_action` 的：

- System Message；
- User Payload；
- JSON Schema；
- Request 顺序。

它不发起网络请求。

必须明确标注：

```yaml
payload_source: scripted_actions_with_real_local_tools
```

并用现有 V4 Goal 2/3 真实 Usage 记录校准总 Prompt Token 数，不能把 Scripted
行为伪装成新的真实 Agent 运行。

只有 Scripted Capture 无法回答材料性问题时，才向 Main Session 说明需要多少
额外真实 Deep 调用；未经新授权不得调用。

## 8.3 字段分解

至少统计：

```yaml
static_policy:
action_schema:
tool_contracts:
original_query:
current_goal:
open_questions:
resolved_questions:
navigation_results:
evidence_text:
evidence_metadata:
latest_observation:
historical_observations:
visited_video_ids:
visited_segment_ids:
previous_queries:
budget_state:
trace_or_other:
```

当前没有独立 Tool Contract Message、Historical Observation List 或 Trace
Payload 时，应记录：

```yaml
chars: 0
content_count: 0
present_in_current_payload: false
```

不得为了填表虚构归属。

每个区块记录：

```yaml
chars:
estimated_tokens:
token_estimation_method:
repeated_from_previous_round:
content_count:
normalized_hash:
```

`repeated_from_previous_round` 必须通过规范化内容 Hash/Equality 得出，不得凭印象。

Provider Usage 的 `prompt_tokens` 是总量权威。字段 Estimated Tokens 只用于
相对分解，必须披露估算方法。不要仅为了估算增加重量依赖。

## 8.4 必须单独检查

- `summary_sections[:4]` 的实际单项字符数和总量；
- Evidence `quote[:500]` × Span Count；
- 每个 Evidence 的完整 `segment_ids` 长度；
- Navigation 描述和 Matched Excerpt；
- AgentDecision JSON Schema；
- 动态 `remaining.search_seconds / total_seconds`；
- Stable System Prefix 是否逐轮字节一致；
- Prompt Cache Hit 是否只覆盖固定 System Prefix；
- Resolved Question 是否只包含 Question/Citation IDs；
- Last Observation 是否已是 1000 字有界摘要；
- Visited Segment 是否确实只发送最近 60 个；
- Previous Query Key 是否只发送最近 24 个。

## 8.5 Cache 分析

记录：

- System Message Hash；
- User Payload Hash；
- 固定 System Prefix 字符；
- 每轮第一个动态字段位置；
- 历史真实 Agent Usage 中的 Cache Hit/Miss；
- Scripted Payload 中逐轮重复区块。

不得声称某动态字段“破坏全部 Prompt Cache”，除非 Provider Usage 和请求布局
支持该结论。

## 8.6 Candidate DecisionView

H0 报告必须提出一个字段级候选，但不实施：

```yaml
original_query:
current_search_goal:
open_questions:
resolved_questions:
latest_observation:
evidence_inventory:
previous_query_summary:
visited_summary:
budget_remaining:
available_actions:
```

每个候选字段说明：

- 来源 Runtime 字段；
- 是否无损；
- 截断或摘要规则；
- Runtime 中仍保留的完整数据；
- 信息损失风险；
- Guard 是否继续由确定性代码执行；
- H2 所需测试。

禁止在 H0 中：

- 新建完整 DecisionView Runtime；
- 修改 Agent Prompt；
- 删除当前字段；
- 加入 LLM Rolling Summary；
- 改 LangGraph 拓扑或 Tool。

---

# 9. H0-C — Fast Context Selection Diagnostics

## 9.1 Mission

只增加或计算无行为改变诊断，判断：

- Context Truncation 的真实来源；
- 是否存在重复召回；
- 单视频占用；
- Video Diversity；
- Overlap；
- Candidate/Selected/Dropped 字符；
- Query Rewrite 来源；
- 是否有材料性 Evidence 丢失信号。

H0 不引入：

- Reranker；
- Diversity-aware Selector；
- Automatic Context Compaction；
- 新 Context Platform。

## 9.2 字段定义

最低记录：

```yaml
raw_materialized_span_count:
candidate_span_count:
selected_span_count:
candidate_video_count:
selected_video_count:
candidate_per_video_span_count:
selected_per_video_span_count:
overlapping_span_count:
exact_citation_duplicate_count:
duplicate_content_count:
dropped_span_count:
dropped_video_count:
candidate_chars:
selected_chars:
dropped_chars:
selected_query_sources:
context_truncated:
```

规划文件中的字段含义冻结为：

```yaml
candidate_span_count:
  meaning: fuse_evidence 后进入 TranscriptContextBuilder 的 Span 数

selected_span_count:
  meaning: Fit/Merge/Budget 后进入 model_context 的 Span 数

overlapping_span_count:
  meaning: 同 Source Artifact、Version、Timeline 且 Segment Ordinal 相交的候选关系

exact_citation_duplicate_count:
  meaning: Raw Materialized Spans 中重复 Stable Citation ID 的额外数量

duplicate_content_count:
  meaning: 不同 Citation ID 但规范化 quote_text 完全相同的额外数量

dropped_video_count:
  meaning: Candidate 中出现但 Selected 中完全消失的唯一 Video 数

selected_query_sources:
  meaning: Selected Span Retrieval Provenance 中不同 query/query_index
```

`dropped_chars` 若因 Merge、Overlap 和 `_fit_span` 无法严格等于简单差值，必须：

- 给出确定义；
- 使用非负值；
- 在报告中说明是 Exact 还是 Approximation；
- 不制造虚假精度。

## 9.3 Instrumentation 边界

允许两种方式：

### 方式 A：Runner-only Audit

使用当前 Builder 输入/输出计算诊断，不修改正式 Runtime。

### 方式 B：Trace-only Instrumentation

如果 Runner-only 无法复用真实 Fast 路径，可增加：

- 纯 Diagnostics Helper；
- `ContextBuildResult` 的内部诊断；
- Finalizer Trace 字段。

必须证明：

- Selected Span Identity 不变；
- Model Context 字节不变；
- Citation Allowlist 不变；
- Status/Termination 不变；
- 没有新增 Provider 输入；
- 没有改变排序、合并、Fit 或 Budget。

优先 A；只有有充分理由才使用 B。

## 9.4 诊断样本

至少使用现有四类 Query，与 H0-A 对齐：

- No-direct-support；
- Single-topic；
- Cross-video；
- Universal/Partial-support。

可在不增加 Provider 调用的情况下运行全部六条 Goal 3 Fast Query 的本地
Retrieval/Context Diagnostics。

Query Analysis/Rewrite 使用确定性 Scripted Plan，避免为了诊断 Context Selection
引入外部变量。

## 9.5 必须回答

- 六条 Fast Truncation 是 Span 数、字符预算、Per-span Fit、Overlap 还是重复
  Rewrite 导致；
- 同一 Video 是否占据多数 Selected Span；
- 不同 Rewrite 是否反复召回相同 Citation；
- 跨视频 Case 是否在 Context 前失去 Video Diversity；
- Partial-support Case 的反例/限制证据是否进入 Candidate 但被 Dropped；
- 是否存在重复材料性失败，足以让 H1/H3 讨论 Selection 改动。

“`context_truncated=true`”本身不能触发 Reranker。

---

# 10. 允许的文件和代码改动

H0 必须创建：

```text
V4_1_H0_INVESTIGATION_REPORT.md
```

Main Session 已创建：

```text
V4_1_H0_INVESTIGATION_PROMPT.md
```

允许增加：

```text
scripts/run_v4_1_h0_investigation.py
tests/test_v4_1_h0_investigation.py
```

如果职责明显分离，可将 Runner 拆为最多两个文件，但不要为 A/B/C 各建一套
Framework。

允许修改：

- 仅测量所需的无行为变化 Instrumentation；
- H0 Runner/Test；
- H0 Report。

不得创建：

- `V4_1_MASTER_STATE.md`；
- H1/H2/H3 Prompt 或 Report；
- Readiness；
- Gate；
- 多 Reviewer 文件；
- 独立 Eval Governance；
- 每个实验单独报告；
- 单独 JSON 结果文件；
- 私有 Request/Response Dump；
- V4.1 Closeout。

所有有界实验行、统计和建议写入同一 H0 Report。

---

# 11. 确定性测试要求

真实 Provider 调用前，至少完成：

- Provider Variant Request Body 测试；
- Baseline 与 Thinking Off 除 Variant 字段外 Request 相同；
- Fixed Request Hash 在三次 Trial 中一致；
- Trial 顺序轮转；
- Usage 嵌套字段提取；
- First-pass Schema / Repair / Retry 计数；
- Provider Error 保留；
- Payload 字段 Breakdown 总字符可回算；
- Repeated Block Hash 判断；
- Current `_decision_messages()` 不被 Audit 改写；
- Context Diagnostics 字段定义；
- Model Context、Citation Allowlist 和 Selected Span 非回归；
- 无 Secrets、完整 Prompt 或无界字幕写入结果。

定向测试还必须覆盖现有：

- Goal 1 Fast；
- Goal 2 Deep；
- Goal 3 Ask/Eval；
- Provider Deadline/Retry；
- Citation/Context。

---

# 12. H0 Report

只创建：

```text
V4_1_H0_INVESTIGATION_REPORT.md
```

报告结构：

## A. Outcome

- H0 是否完成；
- 哪些部分有真实 Provider 证据；
- 哪些只有 Scripted/Local Audit；
- 是否存在外部阻塞；
- 是否建议进入 H1/H2。

## B. Baseline and Scope

- Branch/Commit；
- 初始工作区；
- V4 非回归边界；
- 修改文件；
- 确认未实施 H1/H2。

## C. H0-A Provider Latency Attribution

- Fixed Request 生成方式和 Hash；
- Variant 和授权；
- 每 Trial 完整有界测量；
- Min/Median/Max；
- Schema/Repair/Retry；
- 四维人工质量；
- Replay 与 E2E 分开；
- Attribution 七字段；
- 未解决变量。

## D. H0-B Deep Decision Payload Audit

- Current Context Diagram；
- Scripted/Real 数据来源；
- 每轮 Payload Breakdown；
- Top 5 Growth Sources；
- Cache Layout；
- 哪些规划假设被源码反证；
- Candidate DecisionView；
- Information Loss Risks；
- H2 建议。

## E. H0-C Fast Context Diagnostics

- 六 Case 或至少四类 Case；
- Raw/Fused/Selected/Dropped；
- Per-video；
- Overlap/Duplicate；
- Query Source；
- Truncation 来源；
- 是否有材料性丢失信号；
- 是否触发 Selection 改动讨论。

## F. H1/H2 Scope Recommendation

只分：

```yaml
proven_and_recommended:
not_proven:
rejected_or_deferred:
```

不得把每个发现拆成 Goal。

## G. Tests

- 修改前 Baseline；
- H0 定向；
- Goal 1/2/3 回归；
- 默认全套；
- Compileall、Pip、Diff；
- Warning/Failure。

## H. Data and Scope Audit

- Provider 调用次数；
- 授权；
- 数据发送；
- 无 Secrets；
- 无完整 Prompt/字幕入库；
- 无 Runtime 行为改变；
- 无新平台；
- 未修改正式 V4 状态文件；
- 未 Commit/Push。

## I. Main Session Decision Inputs

主 Session 必须能据此决定：

- H1 是否采用 Thinking Off、保持 Baseline 或继续小范围研究；
- 是否需要 No-evidence Short Path；
- Useful Partial 是否进入 H1；
- H2 是否实施 Deterministic DecisionView；
- H2 优先移除哪些重复区块；
- H0-C 是否有证据触发 Context Selection 改动；
- 哪些方向继续 Deferred。

---

# 13. H0 完成条件

H0 完成必须满足：

- Provider Replay 使用固定请求；
- Baseline/Thinking Off 各 3 Trial；
- Reduced Reasoning 只在真实支持时加入；
- Live 调用有明确授权和上限；
- Replay 与 E2E 不混淆；
- 同时比较性能和质量；
- Deep Payload 按字段和轮次量化；
- 报告反映当前没有完整历史 Observation/全部 Visited Segment 直传的事实；
- 提出 Candidate DecisionView，但未实现；
- Fast Context 只加诊断，没有改变选择；
- 没有引入 Reranker、Compaction、Judge、Streaming 或新平台；
- 定向和默认全套测试通过；
- 创建一份 H0 Report；
- 主 Session 获得足够证据决定 H1/H2 范围。

如果用户没有授权真实 Provider 调用：

```yaml
h0_status: blocked_pending_live_provider_authorization
```

但必须先完成全部可独立完成的源码审查、Instrumentation、Scripted Payload Audit、
Context Diagnostics 和测试。不要提前停止。

---

# 14. Escalation 条件

遇到以下情况时暂停相关方向并报告：

- 需要修改正式 Fast/Deep 行为才能完成测量；
- 需要扩展 Provider Adapter 才能伪造 Reduced Reasoning；
- 需要保存完整私人 Prompt/字幕到仓库；
- 需要真实 Deep Agent 调用才能完成 Payload Audit；
- 需要改变 Shared Ask Contract、Citation Identity 或 Fact Authority；
- 需要引入 Runtime Semantic Judge；
- 需要新增 Reranker、Compaction、Streaming 或 Cancellation；
- 需要改变 LangGraph 拓扑、Tool 或 Budget；
- 需要读取历史 Case 级 Gold；
- 用户文件与 H0 修改冲突；
- 已批准 Provider Call 上限不足。

普通 Runner、纯测量 Helper、测试组织和报告格式不需要逐项审批。

---

# 15. 禁止事项

H0 禁止：

- 直接把 Thinking Off 接入产品 Runtime；
- 修改 `Application.provider()` 的正式 Role 配置；
- 修改 Fast/Deep Prompt 以提高实验结果；
- 实施 Useful Partial；
- 实施 No-evidence Short Path；
- 实施完整 DecisionView；
- 删除 Navigation、Evidence、Question 或 Visited Runtime State；
- 改 LangGraph 拓扑；
- 改 Tool；
- 改 Deep Budget；
- 引入 Native Tool Calling；
- 引入 Runtime Semantic Judge；
- 引入 Reranker；
- 引入 Automatic Context Compaction；
- 引入 LLM Summary；
- 引入 Memory、Persistence、HITL 或 Multi-Agent；
- 引入 Token Streaming 或 Server Cancellation；
- 新建 Provider、Context、Eval 或 Observability Platform；
- 修改 `V4_MASTER_STATE.md`、`V4_DESIGN_PROPOSAL.md` 或
  `V4_DECISION_LEDGER.md`；
- 修改 V0–V4 冻结报告；
- Stage、Commit、Push 或 Merge；
- 扩大到 V5。

---

# 16. 最终返回 Main Session

最终只返回：

1. H0 是否完成；
2. Provider Replay/E2E 的实际授权和调用数；
3. Provider Latency Attribution 结论；
4. Deep Payload Top Growth Sources；
5. Candidate DecisionView 和主要信息损失风险；
6. Fast Context Truncation 的主要来源；
7. 是否有证据进入 H1/H2；
8. 测试结果；
9. 是否存在 Blocking Finding；
10. `V4_1_H0_INVESTIGATION_REPORT.md` 路径。

不要在聊天中复制完整 Prompt、私人字幕或 Raw Provider Response。

---

# 17. 启动指令

现在开始 H0。

先确认冻结 Baseline 和工作区，创建/复用 `codex/v4.1-hardening`，完成全部
Deterministic Instrumentation、Scripted Payload Audit、Fast Context Diagnostics
和测试。

然后向用户提交精确的 Provider Matrix、最大 Invocation 数和数据发送说明，
等待明确授权后再执行 H0-A Live Replay；Replay 完成后，再以独立授权决定是否
运行少量 End-to-End。

不要先修改正式 Runtime。不要把调查候选当成已接受方案。不要扩大到 V5。
