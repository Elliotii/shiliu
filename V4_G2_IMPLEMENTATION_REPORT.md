# Shiliu V4 Goal 2 Implementation Report

```yaml
goal: Goal 2 — Independent Agentic Search
implementation_status: complete
integration_review: accepted
date: 2026-07-29
branch: codex/v4-main
starting_commit: 0152e6f
```

## A. Outcome

Goal 2 — Independent Agentic Search 已完成实施和 Goal Session 验证，并已
通过主 Session 第二次 Integration Review。

用户现在可以通过同一个 `POST /api/ask` 和同一个 `AskRequest` 提交
`mode=deep`，获得：

- 从原始用户问题开始的独立视频导航；
- 指定视频范围或全库的权威原字幕检索；
- 当前 Source Version、同一 Timeline 内的相邻字幕窗口读取；
- 基于 Observation 改变后续 Action 的 Planning / Replanning；
- 由代码执行的 Round、Tool、Repeat、No-new、Context 和 Deadline 边界；
- 与 Fast 完全相同的 `AskResponse`、Answer Block 和 Citation 合同；
- 共享 Grounded Answer、一次 Same-context Repair 和最终 Source Revalidation；
- 同一个 `/api/ask/traces/{run_id}` 下的有界 Deep Trace。

不存在 Blocking Finding。真实运行保留了一次严格 Agent Action Schema 失败，
详见 D、F 节。

## B. Code Changes

### Deep Domain 与确定性 Runtime

- `src/shiliu/ask/deep/contracts.py`
  - 严格 discriminated-union Agent Action；
  - Deep State、Navigation Document、Tool Observation 和工作清单合同。
- `src/shiliu/ask/deep/budget.py`
  - 冻结并验证 6 Round、12 Tool、8 Video、2 No-new、
    12k Context、360/150/210 秒包络。
- `src/shiliu/ask/deep/decision.py`
  - `agent_action` Structured Provider 调用；
  - 有界 Navigation/Evidence/Visited/Budget Decision Context。
- `src/shiliu/ask/deep/reducer.py`
  - 统一维护计数、Visited、Worklist、Evidence、Trace 和停止原因。
- `src/shiliu/ask/deep/service.py`
  - 框架无关 Deep Facade、状态初始化、共享 Finalization 和 Response 组装。

### Navigation、Transcript 与 Evidence

- `src/shiliu/ask/deep/navigation.py`
  - 复用 `scope=video` 召回；
  - 从 DB/Artifact 重新投影标题、简介、AI 总结、整理稿、Notes 和元数据；
  - 所有字段显式 `navigation_only / citation_allowed=false` 和优先级。
- `src/shiliu/ask/deep/transcript.py`
  - 全库与 Focused Transcript Search；
  - 每次 SearchExecution 只物化一次；
  - 单 Tool 6 Span / 半数最终 Context 字符的确定性 Observation 包络；
  - 当前版本、同 Video、同 Timeline、原始 Ordinal 的 Window Reader。
- `src/shiliu/retrieval/models.py`
- `src/shiliu/retrieval/service.py`
- `src/shiliu/retrieval/orchestrator.py`
- `src/shiliu/retrieval/product_search.py`
- `src/shiliu/evidence/search.py`
- `src/shiliu/ask/evidence.py`
  - 增加内部 `video_ids` Retrieval Filter；
  - Filter 在 Lexical SQL、Dense SQL 和 Hybrid 两路召回前生效；
  - Focus Scope 随 `SearchExecution` 和 Retrieval Provenance 保留；
  - Fast 公共过滤合同保持兼容。

### LangGraph Thin Adapter

- `src/shiliu/ask/deep/graph.py`
  - 仅使用低层 `StateGraph`、普通边、条件边和有界循环；
  - 拓扑为 Decision → Guard → Tool → Reducer → Replan / Finalize；
  - 编译时无 Checkpointer；
  - Finalize Node 只记录搜索终态，不实现 Answer。
- `pyproject.toml`
  - 增加 `langgraph>=1.2.10,<1.3`；
  - 实际解析为 `langgraph==1.2.10`；
  - 只使用 `langgraph.graph.StateGraph`，不导入其 Prebuilt、Checkpoint、
    SDK 或 LangSmith 能力。

### 共享 Goal 1 重构与 Provider 薄适配

- `src/shiliu/ask/finalize.py`
  - 抽取 Fast/Deep 共用的 Transcript Context、Grounded Answer、
    Citation Validation、Repair、Source Revalidation 和结果组装。
- `src/shiliu/ask/service.py`
  - Fast/Deep Facade 分派；
  - Fast 和 Deep 使用同一个 `AnswerFinalizer` 实例。
- `src/shiliu/ask/contracts.py`
  - 仅给 `TraceSummary` 增加具有默认值的 Deep 指标。
- `src/shiliu/ask/answer.py`
- `src/shiliu/llm.py`
  - 增加 `agent_action` 角色；
  - 增加单次 Structured Invocation 的剩余 Deadline Timeout；
  - Transport Retry 和 Answer Repair 继续分开计数；
  - 历史 Provider 默认调用语义不变。
- `src/shiliu/app.py`
  - 给现有 Ask Facade 接入 ArtifactStore 和 Deep Runtime。

### 验证资产

- `tests/test_v4_deep_search.py`
  - 新增 10 个按职责组织的 Deep 测试。
- `tests/test_v4_fast_ask_api.py`
  - 将原 Deep 501 断言替换为真实 Deep API 行为。
- `scripts/run_v4_goal2_vertical_slice.py`
  - 临时 DB 快照、真实字幕、真实 DeepSeek 的只读 Vertical Slice；
  - 输出脱敏 Action、预算、Usage 和 Citation 复验指标。

## C. Tests

### 修改前真实基线

```text
branch: codex/v4-main
commit: 0152e6f
working_tree: clean
langgraph: not installed
115 passed
1 existing Starlette/httpx deprecation warning
```

基线覆盖 Prompt 指定的 Goal 1、Retrieval、Evidence 和历史 API 文件。

### Goal 2 与相关定向

```text
130 passed
1 existing Starlette/httpx deprecation warning
```

新增覆盖包括：

- Action Schema、未知字段、Query/Video/Window 上界；
- Source-aware Navigation 和 Navigation/Fact 隔离；
- Lexical、Dense、Hybrid 的 Retrieval-stage Video Filter；
- Focused Search 单次执行与 Provenance；
- Window 当前版本、Source Identity、Timeline 和 Stale Anchor；
- Segment/Evidence 去重与 Worklist Citation Binding；
- Round、Tool、Repeat、No-new、Context 和 Fake Clock Deadline；
- 360/150/210 秒以及 Answer Repair 共享剩余 Deadline；
- Malformed Agent Action 的 `provider_error`；
- Stale-only 的 `evidence_unavailable`；
- 动态 Navigation → Transcript → Window → Finish；
- Graph 无 Checkpointer；
- Candidate Builder 不在调用链；
- Fast/Deep 共享 Finalizer 和同一 API 合同。

### Goal 1 与默认全套

最终全套结果见本报告生成后的最终验证记录：

```text
1438 passed
4 deselected
1 existing Starlette/httpx deprecation warning
```

同时通过：

```text
python compileall
pip check: No broken requirements found
git diff --check
```

默认排除项仍仅为既有 `external_artifact` 和 `live_provider` Marker；真实 Provider
由 D 节单独执行。

## D. Real Runs

运行使用：

- 当前本机真实 DeepSeek 配置；
- 本机真实数据库的临时 SQLite 快照；
- 当前真实字幕和 Source Version；
- 真实本机 Qwen Retrieval；
- 非 Eval Gold 的普通问题；
- 不输出 API Key 或私人字幕正文。

### D.1 首轮三条真实运行与保留失败

| Query 类别 | Status / Termination | Round / Tool | Action | Evidence / Citation | Latency |
|---|---|---:|---|---:|---:|
| MCP 直接事实 | `partial / budget_exhausted` | 2 / 2 | Navigation → Focused Transcript | 48 / 2 | 57.9s |
| 跨视频上下文管理 | `partial / budget_exhausted` | 2 / 2 | Navigation → Focused Transcript | 41 / 5 | 35.7s |
| 不存在的协议 | `insufficient / budget_exhausted` | 2 / 2 | Navigation → Focused Transcript | 50 / 0 | 12.6s |

三条返回 Citation 均通过当前 Source Version、Segment、Quote、Time 和 Jump URL
重建。首轮同时暴露真实问题：一次 Transcript Tool 把 41–50 个 Span 全部加入
State，立即触发 12k Context Budget，阻止 Window/Replanning。

最小修正为单 Tool Observation 的确定性 6 Span / 6000 字符包络；没有增加
Reranker、Independent Index 或 Context Compaction Agent。

### D.2 修正后的 Window / Replanning Case

```yaml
query_category: MCP navigation, focused transcript, adjacent window
status: partial
termination_reason: answer_ready
decision_rounds: 4
tool_calls: 3
actions:
  - search_navigation
  - search_transcripts (4 focused videos)
  - read_transcript_window (before=2, after=2)
  - finish
visited_video_count: 8
visited_segment_count: 231
evidence_count: 7
evidence_candidate_dropped_count: 42
answer_calls: 1
repair_calls: 0
transport_retry_count: 0
latency_ms: 48010
context_truncated: false
citations: 2
citation_validation: passed
```

Usage：

```yaml
agent_action_total_tokens: 58396
grounded_answer_total_tokens: 4683
```

该 Case 证明 Observation 后 Action 真实变化、Focused Video Scope、生效的
Window Reader、共享 Grounded Answer 和最终 Citation Revalidation。

### D.3 当前无证据 / Provider Failure Case

```yaml
query_category: nonexistent protocol
status: insufficient
termination_reason: provider_error
decision_rounds: 3
tool_calls: 2
successful_actions:
  - search_navigation
  - search_transcripts (8 focused videos)
evidence_count: 6
evidence_candidate_dropped_count: 44
answer_calls: 1
repair_calls: 0
latency_ms: 17816
citations: 0
```

第三轮真实 Agent Action 提议了一个空 `citation_ids` 的 resolved question，
违反严格 Schema。Runtime 没有发起 Action Repair，也没有伪造 Resolution；
它按冻结边界记录并终止为 `provider_error`。共享 Answer 根据现有噪声证据返回
`insufficient`，没有 Answer Block 或 Citation。该失败被保留，未通过放宽
Schema、增加 Repair 或扩大 Provider 平台隐藏。

## E. Scope Audit

```yaml
goal_3_started: false
ask_page_implemented: false
candidate_builder_dependency: false
navigation_in_fact_context: false
non_transcript_citation_source: false
second_answer_or_citation_backend: false
native_tool_calling: false
prebuilt_create_agent: false
checkpointer_or_persistence: false
memory_or_hitl_or_interrupt: false
subgraph_or_multi_agent: false
langgraph_cloud_or_langsmith_runtime: false
independent_navigation_index: false
runtime_semantic_judge: false
automatic_context_compaction: false
token_streaming: false
new_provider_tool_trace_eval_platform: false
```

Fast 不执行 Graph；Deep Graph 仅控制顺序、条件分支和循环。Navigation
Observation 永远不会加入 `evidence_spans`，最终 Answer Context 只由当前原字幕
`TranscriptEvidenceSpan` 构建。

基础 `langgraph==1.2.10` 的官方传递依赖包含 checkpoint、prebuilt、SDK 和
LangSmith 包；这是基础包的解析结果。项目代码没有导入、配置或调用这些能力，
因此未形成禁止边界的实质冲突。

## F. Risks and Open Issues

### Blocking

无。

### Goal 3 输入

1. 真实 Window Case 的四次 Agent Decision 共消耗 58,396 Tokens；虽然仍在
   时间预算内，但 Decision Context 的成本需要在轻量 Eval 中观察。
2. 确定性单 Tool 包络在两个当前真实 Case 中分别丢弃 42、44 个候选 Span。
   当前 Citation 和回答仍可用，但应评估是否反复把相关证据排到包络之外。
3. 真实无证据 Case 出现一次严格 Agent Action Schema 漂移。当前 Fail-closed
   行为正确；需要通过后续真实 Case 观察发生频率。
4. Window Case 总延迟约 48 秒，Provider 仍是主要延迟来源。

### Deferred 触发信号

- 当前没有材料性 Navigation Recall 失败，不触发 Independent Navigation Index。
- 当前没有证据证明 Reranker、Native Tool Calling 或 Automatic Context
  Compaction 是完成 Goal 2 的必要条件。
- 如果后续轻量 Eval 反复证明被确定性包络丢弃的 Span 包含关键证据，再由主
  Session 讨论 Reranker；本 Goal 不自行启用。

## G. Suggested Master State Update（已由 I 节正式验收结论取代）

建议主 Session 在 Integration Review 后记录：

```yaml
goal_2:
  implementation: complete
  deterministic_tests: passed
  full_test_suite: passed
  real_vertical_slice:
    navigation_first: passed
    focused_transcript: passed
    dynamic_replanning: passed
    transcript_window: passed
    current_citation_revalidation: passed
    retained_failure: malformed_agent_action_provider_error
  scope_audit: passed
  integration_repair: completed
  integration_review: accepted
```

正式验收后的下一步：

```text
Goal 2 Integration Review Accepted
→ 更新 V4 Master State
→ 与用户讨论 Goal 3 有界计划
→ 经授权后形成 Goal 3 Execution Prompt
```

本 Goal Session 不修改 `V4_MASTER_STATE.md`、`V4_DECISION_LEDGER.md` 或
`V4_DESIGN_PROPOSAL.md`，也不自行宣布整个 V4 完成。

## H. Main Session Integration Repair

主 V4 Session 的首次 Integration Review 发现一个 Blocking Finding：
Deep Finalization 直接使用 360 秒 Total Deadline，导致已经冻结的 210 秒
Final Answer Reserve 没有实际约束运行时。该 Finding 已完成有界修复。

### 210 秒 Answer Reserve

Deep Search 结束后现在记录 `finalization_started`，并使用：

```text
answer_deadline = min(
    total_deadline,
    finalization_started + final_answer_reserve_seconds,
)
```

Initial Answer 与一次 Same-context Repair 共用同一个 `answer_deadline`：

- 搜索接近 0 秒时 Initial Answer Timeout 最多为 210 秒；
- 搜索消耗 149 秒时 Initial Answer Timeout 仍最多为 210 秒；
- Initial Answer 消耗 100 秒后 Repair 最多获得约 110 秒；
- `total_deadline` 继续作为整体硬上界；
- Fast 模式继续不传 Deadline，现有 Timeout 行为不变。

### Deadline Timeout 与 Provider Network Error

V4 Structured Provider 现在为单次有 Deadline 的 Invocation 计算明确的
Invocation Deadline。若调用开始前已经耗尽，或 httpx Timeout/Network/
Retryable Provider Error 返回时 Deadline 已耗尽，则返回：

```yaml
code: deadline_exhausted
retryable: false
```

Deadline 尚未耗尽的普通 `httpx` 网络故障仍保持：

```yaml
code: provider_network
retryable: true
```

Agent Decision 的 `deadline_exhausted` 由 Reducer 映射为
`budget_exhausted`；Grounded Answer/Repair 的相同错误由共享 Finalizer 映射为
`budget_exhausted`。普通 Provider Network Error 仍映射为 `provider_error`。

Transport Retry 只在捕获错误后仍有 Invocation Deadline 时执行。Logical Call
与实际执行的 Transport Retry 继续分别计数；Deadline 在第一次请求中耗尽时
`retry_count=0`。

### Finish / Stop 最终语义

```yaml
FinishAction:
  with_evidence: answer_ready
  without_evidence: evidence_unavailable
StopAction:
  with_evidence: no_new_evidence
  without_evidence: evidence_unavailable
```

Stop 有 Evidence 时，共享 Finalizer 可使用已有权威字幕证据回答，并将原本的
`complete` 降级为 `partial`。Agent Action Schema 仍不允许 Agent 指定任意
Termination Reason。

### 新增与修改测试

新增 8 个确定性测试，并更新原有 Deadline 断言：

- 真实模拟第一次请求抛出 `httpx.ReadTimeout` 并耗尽 Deadline；
- 普通可重试网络错误且仍有剩余时间时执行一次 Retry；
- 第一次网络请求耗尽 Deadline 后不得 Retry；
- Agent Action 的真实模拟 httpx Deadline 最终映射为
  `budget_exhausted`；
- Grounded Answer 的真实模拟 httpx Deadline 最终映射为
  `budget_exhausted`；
- StopAction 有 Evidence 独立测试；
- StopAction 无 Evidence 独立测试；
- FinishAction 无 Evidence 测试；
- 210/210 和 210/110 Initial/Repair Timeout 断言。

验证结果：

```yaml
goal_2_directed:
  passed: 24
  warnings: 1 existing Starlette/httpx deprecation warning
goal_1_fast:
  passed: 17
  warnings: 1 existing Starlette/httpx deprecation warning
retrieval_evidence:
  passed: 97
  warnings: 1 existing Starlette/httpx deprecation warning
default_full_suite:
  passed: 1446
  deselected: 4
  warnings: 1 existing Starlette/httpx deprecation warning
pip_check: passed
compileall: passed
git_diff_check: passed
```

### Repair Outcome

```yaml
normal_success_path_changed: false
real_provider_rerun_required: false
remaining_blocking_finding: none
```

正常 Agent/Search/Answer 内容路径没有改变；变化只涉及 Answer Deadline 上界、
Deadline 错误分类/Retry 边界以及 Stop 的冻结终止语义。因此本次不重复真实
DeepSeek Vertical Slice，并保留 D 节全部原始真实运行记录。

## I. Main Session Integration Acceptance

主 V4 Session 于 2026-07-29 完成第二次 Integration Review，并确认：

- 首次 Review 发现的 210 秒 Final Answer Reserve Blocking Finding 已修正；
- Deep Finalization 使用
  `min(total_deadline, finalization_started + final_answer_reserve_seconds)`；
- Initial Answer 与一次 Same-context Repair 共用同一 Answer Deadline；
- Deadline Exhaustion 与普通 Provider Network Error 已正确区分；
- Deadline 耗尽不再触发无意义 Transport Retry，并稳定映射为
  `budget_exhausted`；
- `FinishAction` 与 `StopAction` 已按冻结语义分离；
- Fast 模式、历史 Provider API 和正常 Deep 内容路径未发生语义回归；
- Goal 2 仍保持 Navigation/Fact Context 隔离、Candidate Builder 独立性、
  共享 Answer/Citation 后端和薄 LangGraph 边界；
- 主 Session 独立复跑 24 项 Goal 2/Repair 定向测试、12 项 Fast Ask API
  测试、75 项 Retrieval/Evidence 定向测试，全部通过；
- 主 Session 独立复跑默认全套：

```text
1446 passed，4 deselected
1 existing Starlette/httpx deprecation warning
```

- `pip check`、`compileall` 与 `git diff --check` 均通过；
- 修正没有改变真实 Vertical Slice 的正常 Search/Answer 内容路径，因此接受
  D 节已有的真实 DeepSeek 运行证据，无需重复付费调用；
- 没有进入 Goal 3，也没有引入新的 Agent、Provider、Navigation、Trace 或
  Eval 平台。

正式结论：

```yaml
goal_2:
  implementation: complete
  integration_repair: completed
  integration_review: accepted
  blocking_findings_remaining: 0
  real_provider_rerun_required: false
```

Goal 2 已完成并正式关闭。后续真实质量、Token、Navigation Context 和
Evidence Candidate 包络观察进入 Goal 3 的轻量 Eval 输入，不在 Goal 2
继续扩建基础设施。
