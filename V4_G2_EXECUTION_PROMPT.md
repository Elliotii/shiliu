# Shiliu V4 Goal 2 Execution Prompt

```yaml
session_type: bounded_goal_execution
goal: Goal 2 — Independent Agentic Search
status: ready_to_execute
date: 2026-07-29
repository: Shiliu
expected_branch: codex/v4-main
upstream_goal: Goal 1 — Complete Grounded RAG
```

你正在启动一个新的：

```text
Shiliu V4 Goal 2 Execution Session
拾流 V4 Goal 2 执行 Session
```

本 Session 只负责实现和验证：

```text
Goal 2 — Independent Agentic Search
```

不得扩展到 Goal 3、第二项目、V0–V3.5 历史治理任务或通用 Agent
基础设施建设。

---

# 1. 角色与职责

你在本 Session 中担任：

```text
Goal 2 Implementation Owner
Independent Agentic Search Engineer
LangGraph Thin-Orchestration Engineer
Deep Search Vertical Slice Owner
```

主 V4 Session 仍然负责：

- 跨 Goal 架构；
- 产品范围；
- `V4_MASTER_STATE.md`；
- `V4_DECISION_LEDGER.md`；
- Goal 结果的 Integration Review；
- 是否接受新的重大设计变更；
- 是否进入 Goal 3。

本 Goal Session 不得自行改变：

- V4 三个纵向 Goal；
- Fast/Deep 共享 Ask、Answer、Citation 和 Evidence 合同；
- 原字幕/ASR 的最终事实权威；
- Navigation 与事实 Context 隔离；
- LangGraph 的允许与禁止边界；
- 用户已经批准的运行预算。

---

# 2. 必读文件与渐进式阅读

开始工作前，按以下顺序完整阅读：

```text
1. V4_G2_EXECUTION_PROMPT.md
2. V4_MASTER_STATE.md
3. V4_DESIGN_PROPOSAL.md
4. V4_DECISION_LEDGER.md
5. V4_G1_IMPLEMENTATION_REPORT.md
6. README.md
```

然后检查 Goal 2 直接相关的当前源码：

```text
pyproject.toml

src/shiliu/app.py
src/shiliu/web.py
src/shiliu/llm.py
src/shiliu/db.py
src/shiliu/artifacts.py

src/shiliu/ask/contracts.py
src/shiliu/ask/service.py
src/shiliu/ask/query_analysis.py
src/shiliu/ask/evidence.py
src/shiliu/ask/context.py
src/shiliu/ask/answer.py
src/shiliu/ask/citations.py
src/shiliu/ask/validation.py

src/shiliu/retrieval/models.py
src/shiliu/retrieval/planner.py
src/shiliu/retrieval/service.py
src/shiliu/retrieval/lexical.py
src/shiliu/retrieval/dense.py
src/shiliu/retrieval/hybrid.py
src/shiliu/retrieval/orchestrator.py
src/shiliu/retrieval/product_search.py

src/shiliu/evidence/search.py
src/shiliu/evidence/source.py
src/shiliu/evidence/authority.py
src/shiliu/evidence/mapping.py
src/shiliu/evidence/contracts.py
```

直接相关测试：

```text
tests/test_v4_ask_contracts.py
tests/test_v4_fast_ask_api.py
tests/test_product_search_api.py
tests/test_retrieval.py
tests/test_dense_retrieval.py
tests/test_retrieval_lifecycle.py
tests/test_evidence_contracts.py
tests/test_evidence_stage1b.py
tests/test_boundaries_and_web.py
tests/test_v1.py
```

只有遇到具体实现阻塞时，才继续读取其他文件。

不得重新进行：

- 全仓库审计；
- V0–V3.5 历史材料全文审计；
- Candidate Builder、Selector、Stage4 或 Stage5 全面审计；
- Eval Gold 审计；
- 新一轮 Agent 框架选型；
- 开放式 Web Research；
- 通用 Provider、Tool、Trace 或 Eval 平台设计。

---

# 3. 开始前仓库检查

修改代码前：

1. 确认当前分支和工作区状态；
2. 不覆盖用户已有修改；
3. 确认本 Prompt 所列 V4 正式文件存在；
4. 确认 Goal 1 实现与报告存在；
5. 运行 Goal 1/V4 定向测试，建立当前 Session 基线；
6. 记录已有失败和 Warning，但不要因无关历史问题扩大范围；
7. 检查当前 Python 与依赖解析是否满足 LangGraph 要求。

主 Session 最近一次确认的基线：

```text
branch: codex/v4-main
commit: e3a5da0 feat: complete V4 grounded RAG goal
159 passed（Goal 1 定向与历史回归）
1428 passed，4 deselected（默认全套）
1 existing Starlette/httpx deprecation warning
```

这些只是参考。Goal Session 必须记录开始时的真实 Git 状态和真实测试结果。

---

# 4. Goal 2 用户结果

Goal 2 完成后，`POST /api/ask` 的 Deep 模式必须支持：

```text
用户提交问题并选择 deep
→ 系统从用户 Query 独立开始
→ 使用标题、简介、AI 总结和元数据导航候选视频
→ 对选定视频或全库搜索原字幕
→ 按需读取权威字幕窗口
→ 根据观察结果 Planning / Replanning
→ 在确定性预算内停止
→ 用累积的 TranscriptEvidenceSpan 调用共享 Grounded Answer
→ 返回与 Fast 完全相同的 Answer/Citation 产品合同
```

必须证明：

- Deep Search 不依赖 Candidate Builder；
- Agent 的后续 Action 会根据 Observation 改变；
- Navigation 内容不会成为最终事实证据；
- Citation 只绑定当前 Source Version 的权威字幕；
- Deep 与 Fast 不形成两套 Answer、Citation 或 API 合同；
- 所有预算和停止条件由代码执行，而不是只依赖 Prompt。

Goal 2 不负责正式 `/ask` 页面。页面、证据卡复用、最终 Trace 展示和完整 Demo
属于 Goal 3。

---

# 5. 本 Goal 的范围分类

## 5.1 `must_build`

- Independent Agentic Search Deep 用户闭环；
- 显式 Deep Search State；
- 结构化 DeepSeek Agent Action；
- 动态 Navigation、字幕搜索和字幕窗口读取；
- Evidence Accumulation 与 Replanning；
- 薄 LangGraph `StateGraph`；
- 确定性预算和停止；
- `POST /api/ask` 的 `mode=deep`；
- 共享 Grounded Answer、Citation Validation 和 AskResponse 复用；
- 能证明动态循环和停止边界的测试与真实 Vertical Slice。

## 5.2 `in_goal_support`

- Source-aware Navigation Projection；
- 内部受控 `video_ids` Retrieval Filter；
- `TranscriptWindowReader`；
- `agent_action` Provider 角色；
- Deadline-aware V4 Structured Provider 调用；
- LangGraph 薄 Node Adapter；
- Deep Trace Event 和共享 `TraceSummary` 的兼容扩展；
- App/Web 的必要接线。

## 5.3 `deferred`

- `/ask` 产品页面和最终前端；
- Answer Token Streaming；
- Native Tool Calling；
- Independent Navigation Index；
- Runtime Semantic Judge；
- Automatic Context Compaction；
- Reranker；
- 通用 LLM SDK；
- 通用 Tool Registry；
- Trace/Observability Platform；
- Eval Platform；
- Checkpointer、Persistence、Durable Resume；
- Memory、HITL、Interrupt；
- Subgraph、Multi-Agent；
- LangGraph Cloud；
- LangSmith 服务、追踪或 Runtime 集成；
- `create_agent` 和其他 Prebuilt Agent；
- User Notes、整理稿或 AI 总结成为 Citation 来源。

不得把 `in_goal_support` 中的任何项目拆成独立 Goal。

---

# 6. 共享 Ask Contract

Goal 2 必须继续使用已经落地的：

```yaml
AskRequest:
  query:
  mode: fast | deep
  filters:

AskResponse:
  run_id:
  mode: fast | deep
  status: complete | partial | insufficient
  answer_blocks:
    - text:
      citation_ids: []
  citations: []
  limitations: []
  termination_reason:
  trace_summary:
```

Deep 所需停止原因已经存在：

```text
answer_ready
budget_exhausted
no_new_evidence
repeated_search
provider_error
evidence_unavailable
```

硬约束：

- `answer_blocks` 仍是最终正文唯一结构化事实源；
- 不增加平行自由 `answer`；
- 不增加独立 `claims`；
- 每个非空 Answer Block 至少绑定一个当前 Context Citation ID；
- `status` 表示回答充分度；
- `termination_reason` 表示搜索/运行为什么停止；
- 有可用证据但因预算或搜索停止时，仍可生成 `partial` 回答；
- `insufficient` 不得带 Answer Block；
- 不创建 `DeepAskResponse`、`DeepCitation` 或第二套 UI 合同。

允许向现有 `TraceSummary` 添加向后兼容、具有默认值的 Deep 指标，例如：

```yaml
decision_rounds:
tool_calls:
visited_video_count:
visited_segment_count:
navigation_result_count:
```

Fast 的现有返回和测试必须保持兼容。

---

# 7. 框架边界

Deep Search 使用底层 LangGraph `StateGraph` 作为最薄外层编排器。

允许：

```yaml
- state
- nodes
- normal_edges
- conditional_edges
- bounded_loop
- state_progress_events
```

禁止：

```yaml
- checkpointer
- persistence
- durable_resume
- memory
- HITL
- interrupt
- subgraph
- multi_agent
- LangGraph Cloud
- LangSmith service/runtime integration
- prebuilt create_agent
- prebuilt Agent Executor
```

要求：

- Graph 只能控制节点顺序、条件分支和循环；
- Node 只能把 Graph State 转为领域 Service 输入并返回 State Delta；
- Retrieval、Navigation、Transcript、Evidence、Budget、Answer 和 Validation
  不能依赖 LangGraph 类型；
- Domain 单元测试无需编译 Graph；
- Graph 编译时不提供 Checkpointer；
- 不使用高层 `create_agent`；
- 不为展示技术而增加 Command、Subgraph 或其他非必要特性。

依赖目标：

```toml
langgraph >= 1.2.10, < 1.3
```

只安装基础 `langgraph`。不要增加 `langchain` 高层包或 LangSmith 接线。
实施前检查解析后的依赖树；如果基础 LangGraph 的实际依赖与当前禁止边界产生
实质冲突，停止并报告，不要自行换框架或放宽范围。

---

# 8. 建议代码边界

允许根据现有风格小幅调整文件名，但必须保持以下职责分离：

```text
src/shiliu/ask/
  contracts.py              # 共享 Ask/Evidence 合同
  service.py                # Fast/Deep 分派或共享 Facade
  answer.py                 # 共享 Grounded Answer
  context.py                # 共享事实 Context Builder
  evidence.py               # 当前字幕 Evidence Materializer

  deep/
    contracts.py            # State、Action、Observation、NavigationDocument
    navigation.py           # Navigation Projection/Search
    transcript.py           # Focused search 与 Window Reader
    decision.py             # DeepSeek Agent Action
    budget.py               # 确定性 Guard/Deadline
    reducer.py              # Worklist、Evidence、Visited 状态更新
    service.py              # 框架无关 Deep Search Runtime/Facade
    graph.py                # 仅薄 StateGraph 和 Node Adapter
```

可以采用等价组织，但不得：

- 把全部逻辑塞进 `graph.py`；
- 复制 Goal 1 的 Answer/Validation；
- 把 LangGraph State 当成领域模型到处传递；
- 将 Navigation、Provider 或 Citation 建成新平台。

---

# 9. Deep Search State

State 至少表达：

```yaml
run_id:
query:
filters:

open_questions: []
resolved_questions: []

evidence_spans: []
visited_video_ids: []
visited_segment_ids: []
previous_queries: []

decision_rounds: 0
tool_calls: 0
consecutive_no_new_evidence: 0

started_at:
search_deadline:
total_deadline:
last_action:
last_observation_summary:
errors: []
termination_reason:
```

要求：

- 使用 TypedDict、dataclass 或普通 Pydantic Domain Model 均可；
- Pydantic 合同必须 `extra="forbid"`；
- State 不得包含 Provider、DB Connection 或其他不可序列化服务对象；
- Evidence 在 State 中保持 `TranscriptEvidenceSpan` 权威合同；
- Navigation Observation 与 Evidence 明确使用不同类型；
- Reducer 决定 State 更新，Node 不得任意覆盖计数和 Visited Set；
- State 是单次请求内存状态，不持久化、不恢复。

`open_questions` / `resolved_questions` 是运行时工作清单，不是 Gold Aspect、
Eval Gate 或新的标注体系。

初始工作清单包含用户原问题。Agent 可以提出少量子问题，但：

- 新问题必须规范化和去重；
- 工作清单必须有硬上界；
- “已解决”必须附带当前 State 已存在的 Citation ID；
- Runtime 只验证 ID/Identity 存在性，不做语义 Judge；
- Agent 不能通过声明“已解决”绕过 Evidence 要求。

---

# 10. 结构化 Agent Action

DeepSeek 通过 Pydantic discriminated union 返回结构化 Action。

首版 Action 集：

```yaml
search_navigation:
  query:

search_transcripts:
  query:
  video_ids: []

read_transcript_window:
  anchor_segment_id:
  before:
  after:

finish:
  summary:

stop:
  summary:
```

Action 可以附带有界的工作清单更新建议，但最终更新必须经过 Reducer 校验。

约束：

- 未知 Action 或额外字段拒绝；
- 空 Query 拒绝；
- `video_ids` 去重并限制最多 8 个；
- Window 默认前后各 2 个 Segment；
- Window 每侧最多 4 个 Segment；
- 负数 Window、未知 Segment、跨 Source/Version/Timeline 读取拒绝；
- `finish` 不能凭空产生 Answer；
- `stop` 不能直接指定任意最终 `termination_reason`；
- Runtime 根据实际状态映射停止原因。

首版：

```yaml
agent_action_repair_calls: 0
```

Transport Failure 可沿用 V4 Structured Runtime 的一次底层重试；收到内容但
无法通过 Agent Action JSON/Pydantic 校验时，结束为 `provider_error`。不得
偷偷发起第二次 Decision 或把 Schema Repair 计成普通 Tool Call。

---

# 11. Agent Decision Context

每轮 Decision 输入包含有界、明确分区的信息：

```text
原始用户问题
当前 open/resolved questions
最近 Action 与 Observation 摘要
候选 Navigation Documents
当前 Evidence 的 Citation ID、视频、时间和有界 Quote
Visited Video/Segment
已执行的规范化 Query Key
剩余 Round、Tool、Search Time、Total Time 和 Context Budget
允许的 Action Schema
```

不得：

- 把完整字幕库放进 Agent Prompt；
- 把 Navigation 内容标成事实 Evidence；
- 通过模型自动压缩形成新的事实来源；
- 隐藏剩余预算；
- 让 Prompt 代替 Runtime Guard。

如果对 Agent 输入进行长度控制，只能做确定性的选择、截断和有界摘要；不得
增加 Automatic Context Compaction Agent。

---

# 12. Navigation Projection

现有 `scope="video"` 的 `video_composite` 已包含标题、Uploader、简介、
AI 总结、整理稿、User Notes 和收藏夹信息。它可以用于候选召回，但其混合
Excerpt 不能直接进入事实 Context。

实现薄 `NavigationService`：

```text
ProductSearchService(scope="video")
→ 获得候选 video_id
→ 从 Database / ArtifactStore 重新读取当前字段
→ 生成 Source-aware NavigationDocument
```

`NavigationDocument` 至少表达：

```yaml
video_id:
bvid:
title:
uploader:
description:
summary_sections:
metadata:
matched_excerpt:
matched_sources:
authority: navigation_only
```

User Notes 和整理稿：

```yaml
navigation_allowed: true
citation_allowed: false
initial_priority: low
```

AI 总结：

```yaml
navigation_allowed: true
citation_allowed: false
```

要求：

- 所有字段有明确 Source Label；
- 文本有确定性长度上限；
- 不把混合 `video_composite` 原文直接伪装成权威 Document；
- Navigation 结果只影响 Query、视频选择和 Replanning；
- 不建设独立 Navigation Index；
- 记录真实召回失败，留待主 Session 判断是否触发重新考虑。

---

# 13. Focused Transcript Search

Agent 必须既能全库搜索字幕，也能在选定视频集合内搜索字幕。

不得采用：

```text
全库 Top-K
→ 结果返回后才按 video_id 过滤
```

因为其他视频可能占满 Top-K。

应实现薄的内部 Retrieval Filter，使允许的 `video_ids` 在 Lexical、Dense 和
Hybrid 的真实召回阶段生效。要求：

- 复用现有 Retrieval Orchestrator；
- 复用现有 Product Search/Evidence Search；
- 不建设第二套搜索引擎；
- 对 Fast 公共过滤合同的改动保持向后兼容；
- Lexical、Dense、Hybrid 对同一视频范围具有一致语义；
- 仍然遵守每个不同 Query 只执行一次 Retrieval；
- `TranscriptEvidenceMaterializer` 消费已有 `SearchExecution`，不得再次召回；
- Stale Hit 跳过、记录并继续搜索。

重复 Query Key 必须至少包含：

```text
action kind
+ normalized query
+ sorted unique video_ids
```

所以相同文字先用于 Navigation、后用于 Transcript Search 是合法的不同动作。

---

# 14. Authoritative Transcript Window Reader

实现薄 `TranscriptWindowReader`，根据已知权威 Segment Anchor 直接读取相邻
字幕，而不是再次做语义召回。

流程：

```text
anchor_segment_id
→ 找到所属 video/source artifact/source version/timeline
→ 重新绑定当前 Source Version
→ 验证 anchor 仍存在
→ 按 original_ordinal 读取 bounded neighbors
→ 构造 TranscriptEvidenceSpan
```

硬约束：

- 只能读取当前 Source Version；
- 只能在同一 Video；
- 只能在同一 `timeline_run_id`；
- 必须使用权威 `original_ordinal`；
- 不得跨越不连续的 Timeline Run；
- 进入模型事实 Context 的相邻 Segment 必须进入该 Span 的 Citation Identity；
- 仅 UI 展示扩窗不得改变 Citation Identity；
- Stale、缺失或不一致 Anchor 不得进入 Evidence；
- Window Reader 是薄 Adapter，不发展成 Transcript Platform。

直接重复相同 Anchor 与相同 Window 的 Action 必须被 Guard 拒绝。不同检索
结果间自然出现的部分 Segment 重叠由 Evidence Deduplication 处理，不应仅因
重叠就错误终止整个运行。

---

# 15. Evidence Accumulation 与 Context Budget

State 只累积 `TranscriptEvidenceSpan`。Navigation Observation 永远不能加入
`evidence_spans`。

复用 Goal 1：

- `stable_citation_id`；
- Canonical Segment Ordering；
- `fuse_evidence` 或等价 Rank-only Fusion；
- `TranscriptContextBuilder`；
- `TranscriptEvidenceMaterializer.validate_current()`；
- Grounded Answer Validation。

初始事实 Context 包络：

```yaml
final_evidence_context_chars: 12000
```

要求：

- 按 Citation/Segment Identity 去重；
- 新 Evidence 必须真正增加新的权威 Segment 才算进展；
- 新 Retrieval Provenance 可以合并，但不能伪装成新事实 Evidence；
- Context 达到包络后由确定性代码停止或拒绝继续扩张；
- 不增加模型式 Automatic Context Compaction；
- Final Answer 前重新构建共享 Transcript Context；
- 返回前再次验证实际引用 Span 的当前 Source Version。

---

# 16. 确定性预算

冻结的第一版包络：

```yaml
agent_decision_rounds: max_6
tool_calls: max_12
answer_calls: 1
agent_action_repair_calls: 0

focused_video_limit: 8
consecutive_no_new_evidence_limit: 2
window_default_each_side: 2
window_max_each_side: 4
final_evidence_context_chars: 12000

total_runtime_seconds: 360
search_phase_cutoff_seconds: 150
final_answer_reserve_seconds: 210
```

计数语义：

- 每次逻辑 Agent Decision 尝试消耗一个 `decision_round`；
- 同一逻辑调用的底层 Transport Retry 不增加 Round；
- 只有实际获准执行的 Navigation/Search/Window Tool 消耗一个 `tool_call`；
- 被 Guard 拒绝的重复/越界 Action 不消耗 Tool Call，但已经产生的 Decision
  Round 仍保留；
- Final Grounded Answer 是一个逻辑 Answer Call；
- 共享 Answer 的一次受控 Repair 继续按 Goal 1 的独立 Repair 语义记录。

Deadline 语义：

- `started_at` 使用 monotonic clock；
- 150 秒后不得开始新的 Decision 或 Tool；
- 有可用 Evidence 时立即进入共享 Final Answer；
- 没有 Evidence 时返回类型化不足结果；
- 所有 Provider 调用的超时必须被当前剩余 Deadline 上限约束；
- 360 秒是整个 Deep 请求的硬上界，不只是搜索循环上界；
- Final Answer 和可能的一次 Answer Repair 共用剩余的最多 210 秒；
- 不得通过后台继续运行或返回后补写结果绕过 Deadline。

为满足 Deadline，可以给 V4 Structured Provider 增加可选的 per-invocation
timeout/deadline 参数，但：

- Fast 现有默认行为保持不变；
- 历史 `complete_json()`、`complete_raw()` 和 `test_connection()` 保持原语义；
- 不建设通用 Provider SDK；
- Provider Timeout 与 Agent/Answer Repair 的逻辑计数仍然分开。

---

# 17. 停止规则与优先级

确定性 Runtime 必须处理：

| 条件 | `termination_reason` |
|---|---|
| Worklist 已可回答且有有效 Evidence | `answer_ready` |
| Round、Tool、Search Time、Total Time 或 Context Budget 达限 | `budget_exhausted` |
| 连续 2 次 Evidence-capable Tool 没有增加新 Evidence | `no_new_evidence` |
| 相同 scoped Query 或相同 Window Action 重复且无进展 | `repeated_search` |
| Agent Decision Provider 无法继续 | `provider_error` |
| 只有 Stale/缺失/不可读 Evidence | `evidence_unavailable` |

补充语义：

- Navigation 不产生事实 Evidence，因此不增加
  `consecutive_no_new_evidence`；
- `search_transcripts` 和 `read_transcript_window` 才是
  Evidence-capable Tool；
- 一旦 Evidence-capable Tool 增加新权威 Segment，连续无新 Evidence 归零；
- Agent 的 `finish`/`stop` 只是建议，Runtime 根据 State 映射原因；
- 搜索停止后，只要仍有有效 Evidence，就调用共享 Final Answer；
- 此时最终 `status` 可以是 `partial`，而 `termination_reason` 保留真实停止原因；
- Final Answer Provider 自身失败时返回 `provider_error`；
- 返回前 Source Revalidation 失败且无其他可用 Evidence 时返回
  `evidence_unavailable`；
- 不使用 Runtime Semantic Judge 判断“足够”。

---

# 18. DeepSeek `agent_action` 角色

最小扩展当前 `OpenAICompatibleProvider.generate_structured()`：

```yaml
role: agent_action
thinking: off
temperature: 0
structured_output: Pydantic AgentDecision
transport_retries: max_1
schema_repair: 0
timeout: bounded_by_remaining_search_deadline
```

必须沿用 D-018：

- Retryable Network/Timeout/部分 Server Failure 才可执行一次 Transport Retry；
- Authentication、Balance、Forbidden、Model Not Found、Bad Config、
  Context Too Large 等直接失败；
- Transport Retry 不等于第二次 Agent Decision；
- 没有结构化内容的故障不能进入 Answer Repair；
- 不改变历史 Provider 调用路径。

Trace 至少记录：

- logical role；
- finish reason；
- usage；
- latency；
- response ID；
- retry count；
- provider error code；
- Action Schema Validation Error 的有界摘要。

---

# 19. StateGraph 拓扑

建议最小拓扑：

```text
START
  → decide_action
  → guard_action
  → conditional:
      search_navigation
      search_transcripts
      read_transcript_window
      finalize
  → reduce_observation
  → decide_action
  → ...
  → finalize
  → END
```

允许等价命名，但必须保持：

- Decision、Guard、Tool、Reducer、Finalizer 可分别测试；
- Guard 在每次 Tool 前执行；
- Tool 不能直接决定终止；
- Reducer 统一维护计数、Visited、Worklist、Evidence 和 Trace；
- Finalizer 不重新实现 Answer；
- Graph 使用条件边表达循环和停止；
- 编译时不设置 Checkpointer；
- 不使用 `create_agent`。

如 LangGraph API 细节要求极小的 Adapter 调整，可以调整图形实现，但不得
改变领域边界或引入禁止能力。

---

# 20. Shared Grounded Answer 复用

Goal 2 不得复制 Goal 1 `AskService` 的回答和 Citation 组装逻辑。

实施时应进行最小重构，使 Fast/Deep 可以共享：

```text
TranscriptEvidenceSpan[]
→ TranscriptContextBuilder
→ GroundedAnswerService
→ deterministic validation
→ optional one same-context Answer Repair
→ final source revalidation
→ AskResponse assembly
```

可抽取：

- `AnswerFinalizer`；
- 共享 Response Assembler；
- 或等价的小型框架无关 Service。

要求：

- Fast 行为和测试不变；
- Deep 传入自己的 `termination_reason` 和 Trace 数据；
- Final Answer 不看到 Navigation Context；
- Final Answer 一次性返回；
- 不增加 Deep 专用 Prompt 事实规则；
- Repair 仍只能使用同一 Transcript Evidence Context；
- Repair 后完整重跑 Citation/Identity/Version/Segment Validation。

---

# 21. Lightweight Trace

维护单次请求内存 Trace 即可。不得建设持久化 Trace Platform。

Developer Trace 至少记录：

```yaml
run_id:
query:
mode: deep
started_at:
budget:
events:
  - event_type:
    decision_round:
    tool_call:
    action:
    bounded_observation_summary:
    new_video_ids:
    new_segment_ids:
    evidence_count:
    guard_decision:
    latency_ms:
    usage:
stale_reasons:
errors:
termination_reason:
total_latency_ms:
```

要求：

- 不记录 API Key；
- 不无限复制完整字幕；
- Observation 和错误文本有长度上限；
- Navigation 与 Evidence 在 Trace 中清楚区分；
- `/api/ask/traces/{run_id}` 继续使用同一个入口；
- Fast Trace 兼容；
- State Progress Events 可作为内部事件存在，但不要求本 Goal 完成 SSE/UI。

---

# 22. API 与 App 接线

当前 `POST /api/ask` 对 `mode=deep` 返回类型化 501。Goal 2 应改为：

```text
AskService / Ask Facade
  ├─ mode=fast → 现有 Fast Pipeline
  └─ mode=deep → DeepSearchService
```

要求：

- 同一个 `AskRequest`；
- 同一个 `AskResponse`；
- 同一个 Trace 查询入口；
- 保留现有请求校验和错误形态；
- Deep 成功不再返回 501；
- Fast 不经过 LangGraph；
- Deep 不要求 `/ask` 页面已存在；
- 不实现 Token Streaming；
- 不增加第二个 `/api/deep-search` 产品 API。

---

# 23. 实施阶段与退出条件

以下是一个 Goal 内的纵向阶段，不是新的 Goal 或审批 Gate。

## Phase 1 — Dependency and Contracts

完成：

- LangGraph 基础依赖；
- State、Action、Observation、NavigationDocument 合同；
- 依赖与禁止能力检查；
- 合同单元测试。

退出条件：

- Action 严格校验；
- Graph 可无 Checkpointer 编译；
- Fast 合同无回归。

## Phase 2 — Navigation and Focused Retrieval

完成：

- Source-aware Navigation Projection；
- Video Candidate Search；
- `video_ids` 内部过滤；
- 全库/指定视频字幕搜索；
- 一次 Retrieval 到 Evidence Materialization。

退出条件：

- Navigation 不能进入 `evidence_spans`；
- Lexical/Dense/Hybrid 的 Video Filter 生效；
- Materializer 不重复召回；
- Stale Hit 跳过。

## Phase 3 — Window Reader and Accumulator

完成：

- 当前版本 Anchor 解析；
- 同 Timeline 邻居读取；
- Stable Citation Span；
- Evidence 去重和 Context Budget。

退出条件：

- 跨版本、跨 Timeline 和未知 Segment Fail-closed；
- Window Citation Identity 正确；
- 重复 Segment/Window 行为可测试。

## Phase 4 — Decision, Guard, and Reducer

完成：

- `agent_action` Provider Role；
- Worklist 更新；
- Round/Tool/Repeat/No-new/Context/Deadline Guard；
- Trace Event。

退出条件：

- 所有上界可使用 Fake Provider/Clock 精确测试；
- Prompt 无法绕过 Guard；
- malformed Action 类型化为 `provider_error`。

## Phase 5 — Thin StateGraph

完成：

- 最小节点；
- 条件边；
- 有界循环；
- Finalize 路径。

退出条件：

- 至少一个脚本化测试证明 Observation 改变后选择不同 Action；
- Candidate Builder 不在调用链；
- Graph 不含任何禁止能力。

## Phase 6 — Shared Finalization and API

完成：

- 抽取共享 Answer Finalizer；
- Deep 接入 `/api/ask`；
- 共享 Response/Trace；
- Fast 回归。

退出条件：

- Fast/Deep 返回同一 Pydantic 合同；
- Deep Citation 全部来自权威 Transcript；
- Deep 501 被真实实现替代。

## Phase 7 — Real Vertical Slice

完成：

- 使用真实 DeepSeek、真实本机库和只读数据运行普通 Query；
- 覆盖 Navigation-first、Focused Transcript、跨视频或 Replanning；
- 覆盖一个无 Evidence、重复或预算停止路径；
- 记录失败而不是隐藏失败。

退出条件：

- 至少证明一次真实动态 Action 变化；
- 记录 Round、Tool、Latency、Token、Termination、Evidence 和 Citation；
- 所有返回 Citation 通过最终 Source Revalidation；
- 不根据个别失败临时扩建新平台。

---

# 24. 测试要求

新增测试应按职责拆分，建议覆盖：

```text
Agent Action schema and strict validation
Navigation projection and authority isolation
Focused lexical/dense/hybrid video filtering
SearchExecution single-execution materialization
Window Reader same-version/same-timeline behavior
Stable Citation for adjacent factual segments
Evidence deduplication
Worklist normalization and citation-bound resolution
Round limit
Tool-call limit
Scoped repeated-query detection
Repeated-window detection
No-new-evidence threshold
Context budget
Search cutoff and total deadline using fake clock
Provider error and malformed action
Stale-only evidence
Graph dynamic action/replanning
Graph compilation without checkpointer
Candidate Builder independence
Shared Answer finalization
Deep API success/partial/insufficient
Fast Ask regression
Search and Evidence regression
```

禁止：

- 依赖真实网络的默认测试；
- 用 Sleep 测 150/360 秒 Deadline；
- 只测试 Happy Path；
- 用 Snapshot 掩盖关键停止逻辑；
- 将旧的 Deep 501 测试直接删除而不替换为新行为测试。

使用 Fake Clock、Scripted Agent Provider、Fake Tools 和真实领域 Service 的
组合，既验证确定性逻辑，也验证集成边界。

完成前运行：

1. Goal 2 新增定向测试；
2. Goal 1/V4 定向回归；
3. Retrieval/Evidence 直接相关回归；
4. 默认完整测试套件；
5. `git diff --check`；
6. 适用的静态或导入检查。

---

# 25. 真实 Vertical Slice

真实运行必须使用：

- 当前配置的真实 DeepSeek Provider；
- 本机真实数据库；
- 当前真实字幕和 Source Version；
- 只读或可回滚的数据使用方式；
- 正常用户 Query，而不是 Eval Gold 或密封答案。

代表性行为应包含：

- 先 Navigation 再选择视频；
- 指定视频范围搜索原字幕；
- 根据首轮证据改写或继续搜索；
- 读取相邻字幕窗口；
- 跨视频问题或多子问题；
- 无有效 Evidence 或可解释停止。

每次保留：

```yaml
query:
status:
termination_reason:
decision_rounds:
tool_calls:
actions:
visited_video_count:
visited_segment_count:
evidence_count:
stale_evidence_count:
answer_calls:
repair_calls:
transport_retry_count:
latency_ms:
usage:
context_truncated:
limitations:
citation_validation:
```

Case 数量保持轻量，以覆盖行为为准，不建立新的 Frozen Eval。

如果真实运行失败：

- 先判断是实现 Bug、Prompt、Provider、Retrieval、Navigation Projection、
  Evidence 或预算问题；
- 保留真实失败；
- 只做本 Goal 内最小修正；
- Independent Navigation Index、Reranker、Native Tool Calling 和 Context
  Compaction 只有在记录到对应触发条件后，才提交主 Session 讨论；
- Goal Session 不得自行启用这些 Deferred 能力。

---

# 26. Goal 2 完成条件

以下条件全部满足才可报告完成：

- `POST /api/ask` 的 `mode=deep` 可用；
- 从原始用户 Query 独立运行，不调用 Candidate Builder；
- 至少一次真实或高保真集成路径表现出动态 Action/Replanning；
- Navigation 只用于导航；
- 最终事实 Context 只包含权威 `TranscriptEvidenceSpan`；
- Focused Transcript Search 在 Retrieval 阶段应用 Video Filter；
- Window Reader 严格绑定当前 Version/Timeline；
- Stale Evidence 不进入 Citation；
- Round、Tool、Repeat、Segment、No-new、Context 和 Deadline 均由代码执行；
- 360/150/210 秒包络可通过 Fake Clock 与 Provider Timeout 证明；
- Deep 复用 Goal 1 Grounded Answer、Citation 和最终 Validation；
- Fast 与 Deep 使用相同 AskResponse；
- Fast Pipeline 不使用 LangGraph；
- Deep Graph 使用低层 `StateGraph` 且无 Checkpointer；
- 没有 Persistence、Memory、HITL、Multi-Agent 或 Prebuilt Agent；
- 定向与完整回归通过；
- 真实 DeepSeek Vertical Slice 完成并保留结果；
- 生成 `V4_G2_IMPLEMENTATION_REPORT.md`；
- 没有扩大到 Goal 3 或新平台。

---

# 27. Escalation 条件

遇到以下情况时暂停相关方向并向主 Session 报告：

- 基础 LangGraph 依赖与项目 Python/依赖发生不可安全解决的冲突；
- 实现必须使用被禁止的 LangGraph 能力；
- 现有 Retrieval 无法在不建设第二套引擎的情况下支持 Video Filter；
- Navigation Projection 在真实运行中出现材料性、可复现召回失败，可能触发
  Independent Navigation Index；
- 需要让 AI 总结、Notes 或整理稿成为事实 Citation；
- 需要 Native Tool Calling；
- 需要 Runtime Semantic Judge；
- 需要超过已批准的 6 Round、12 Tool、360 秒包络；
- 需要改变 Stable Citation Identity；
- 需要改变 Fast/Deep 共享 Ask Contract；
- 需要开始 Goal 3；
- 需要破坏历史 Provider 调用语义；
- 发现用户已有修改与本 Goal 文件冲突且无法安全绕开。

普通实现细节、文件命名、内部类拆分和测试组织不需要向主 Session逐项审批。

---

# 28. 禁止事项

本 Goal 禁止：

- 实现 `/ask` 最终页面；
- 启动 Goal 3；
- 建设独立 Navigation Index；
- 把 Candidate Builder 当成 Deep 入口；
- 让 Navigation 内容进入 Answer Fact Context；
- 引用 AI 总结、Notes 或整理稿；
- 复制 Answer/Citation 后端；
- 使用 Native Tool Calling；
- 使用 `create_agent`；
- 使用 Checkpointer、Persistence、Memory、HITL、Interrupt、Subgraph 或
  Multi-Agent；
- 接入 LangGraph Cloud 或 LangSmith Runtime；
- 建设通用 Provider/Tool/Trace/Eval Platform；
- 增加 Runtime Semantic Judge；
- 增加 Automatic Context Compaction；
- 实现 Token-by-token Answer Streaming；
- 为每个内部步骤创建 Gate、Readiness 或 Audit 文档；
- 扩大历史治理；
- 修改 V0–V3.5 冻结材料；
- 接触或反推历史 Case 级 Eval Query/Gold/答案。

---

# 29. 工作方式

- 先建立真实基线，再修改；
- 使用小而可审查的提交；
- 优先先写确定性合同和测试；
- 每完成一个纵向阶段就运行相关测试；
- 真实 Provider 调用前先用 Scripted Provider 验证循环；
- 不覆盖用户已有工作；
- 不将无关文件加入提交；
- 不因测试通过就跳过真实 Vertical Slice；
- 不因真实失败就扩大产品范围；
- 如需网络安装依赖，按环境权限规则请求授权；
- Push 前确认分支、Diff、测试和报告；
- 未经用户或主 Session授权，不自行 Merge。

---

# 30. 最终返回主 Session 的报告

创建：

```text
V4_G2_IMPLEMENTATION_REPORT.md
```

报告只包含：

## A. Outcome

- Goal 是否完成；
- 用户可见能力；
- 是否存在 Blocking Finding。

## B. Code Changes

- 按领域职责列出关键文件；
- LangGraph Thin Adapter；
- 共享 Goal 1 重构；
- API/Provider 薄适配。

## C. Tests

- 修改前基线；
- Goal 2 定向；
- Goal 1/历史回归；
- 默认全套；
- Warning 和失败。

## D. Real Runs

- Query 类别；
- Action/Tool 序列；
- Round/Tool/Latency/Token；
- Status/Termination；
- Citation/Stale/Context；
- 成功与保留失败。

## E. Scope Audit

- 确认没有 Goal 3；
- 确认没有 Candidate Builder 依赖；
- 确认 Navigation/Fact 隔离；
- 确认没有禁止的 LangGraph 能力；
- 确认没有新平台。

## F. Risks and Open Issues

- 只列真实观察；
- 区分 Blocking、Goal 3 输入和 Deferred 触发信号。

## G. Suggested Master State Update

- 建议状态；
- Integration Review 尚需检查的事项；
- 不得自行宣布整个 V4 完成。

---

# 31. 启动指令

现在开始 Goal 2。

先完整阅读正式文件并建立测试基线，然后按一个纵向 Goal 实现：

```text
Independent Navigation
→ Authoritative Transcript Search/Window
→ Dynamic Bounded StateGraph
→ Shared Grounded Answer/Citation
→ Deep Ask API
→ Deterministic Tests
→ Real Vertical Slice
```

不要重新讨论已经接受的产品和架构决定。不要创建新平台。不要扩大到 Goal 3。
