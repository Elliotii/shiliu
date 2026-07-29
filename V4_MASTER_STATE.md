# Shiliu V4 Master State

```yaml
document_role: current_state_authority
status: goal_2_complete
implementation_status: goal_2_complete
current_phase: goal_3_planning_ready
last_updated: 2026-07-29
```

本文件只维护拾流 V4 的当前真实状态、已确认边界、已知风险和下一步动作。产品与架构细节以 `V4_DESIGN_PROPOSAL.md` 为准；关键取舍及其理由以 `V4_DECISION_LEDGER.md` 为准。

## 1. V4 当前使命

```text
Complete Grounded RAG
+
Independent Agentic Search
+
Shared Grounded Answer / Timestamp Citation
+
Lightweight Trace / Eval
```

V4 继承 V0–V3.5 的真实 Retrieval、Evidence、Identity、Sufficiency 和字幕资产，但不继承其重型 Eval 与审批治理。

## 2. 当前已确认产品形态

- 新增 `/ask`，显式提供“快速回答”和“深入搜索”两种模式。
- 保留 `/search`，用于直接搜索证据库、手动查证、Debug 和 Demo 对比。
- `/ask` 复用现有字幕证据卡、证据展开和 B 站时间点跳转能力。
- Fast 与 Deep 使用同一个 Ask 输出合同、Answer/Citation 规则和 Evidence 展示层。
- Fast 使用普通 Service Pipeline；Deep 使用最薄的 LangGraph `StateGraph`。
- 最终事实证据默认只能来自当前 Source Version 可验证的原字幕 `TranscriptEvidenceSpan`。
- 标题、简介、AI 总结、User Notes 和整理稿只用于导航、查询扩展与视频选择，不能作为首版 Citation 事实来源。

## 3. 共享 Ask 输出合同

```yaml
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

约束：

- `answer_blocks` 是答案正文的唯一结构化事实源，不同时维护自由正文和独立 Claims。
- Goal 1 首版所有非空 Answer Block 都必须绑定本次 Evidence Context 中已有的 Citation ID。
- `status` 表示回答充分度；`termination_reason` 表示运行停止原因，两者不得混用。
- 在线验证只做确定性的 Citation、Identity、Source Version 和 Segment 检查。
- Goal 1 的 Stable Citation 使用显式 Identity Version，并按权威 Segment Ordinal 规范化。
- 事实 Evidence Span 与 UI 展示扩窗分离；纯展示上下文不改变 Citation Identity。
- Answer 最多 Repair 一次；Repair 后仍无效则整体 Fail-closed，不做首版 Block Salvage。
- 首版答案一次性返回；搜索进度事件可做但不阻塞核心闭环。

## 4. 当前执行预算

### Fast Grounded RAG

```yaml
query_analysis_calls: 1
answer_calls: 1
repair_calls: max_1
iterative_search: false
```

### Deep Search

```yaml
agent_decision_rounds: max_6
tool_calls: max_12
answer_calls: 1
repeated_query_stop: true
no_new_evidence_stop: true
focused_video_limit: 8
consecutive_no_new_evidence_limit: 2
window_default_each_side: 2
window_max_each_side: 4
final_evidence_context_chars: 12000
total_runtime_seconds: 360
search_phase_cutoff_seconds: 150
final_answer_reserve_seconds: 210
```

此外，Deep Search 必须由确定性代码执行重复 Segment、Context Budget 和总运行时间限制。上述数字是第一版安全包络，Vertical Slice 后依据真实质量、延迟和成本调整。

## 5. 三个纵向 Goal

| Goal | 当前状态 | 目标 |
|---|---|---|
| Goal 1 — Complete Grounded RAG | `complete` | 从 Query Analysis、单次 Retrieval 物化、Evidence Context 到 Grounded Answer/Citation，完成 Fast 闭环 |
| Goal 2 — Independent Agentic Search | `complete` | 从用户 Query 独立导航视频并渐进读取字幕，用有界 StateGraph 完成 Deep 闭环 |
| Goal 3 — Product Integration、Lightweight Eval 与 Demo | `not_started` | 完成 `/ask`、共享证据展示、轻量离线 Eval、Trace 摘要和可演示闭环 |

不得新增独立的 Navigation、Provider、Citation、Trace、Eval、Framework 或 Persistence Goal。相关薄适配随上述纵向链完成。

## 6. 工作范围状态

### `must_build`

- Fast Grounded RAG 用户闭环。
- Independent Agentic Search 用户闭环。
- 共享 Ask Contract、Grounded Answer、Stable Citation 与 Evidence 展示。
- `/ask` 双模式入口及与现有 `/search` 的产品分工。
- 确定性预算、停止条件、Citation/Identity/Version/Segment 验证。
- 能验证核心质量与边界的轻量离线 Eval 和 Demo。

### `in_goal_support`

- `SearchExecution` 与消费既有检索结果的薄 Evidence Materializer，避免同一 Query 重复召回。
- Navigation Projection、Window Reader、Stable Citation Adapter。
- 仅服务 DeepSeek V4 Runtime 的 Provider 薄扩展。
- LangGraph 薄 Node 包装、状态进度事件和 Trace Summary。
- 复用现有字幕证据卡、展开和 B 站跳转所需的前后端适配。

### `deferred`

- Token-by-token Answer Streaming。
- Native Tool Calling。
- Independent Navigation Index；仅在现有 Projection 真实失败后重新考虑。
- Runtime Semantic Judge。
- Automatic Context Compaction。
- LangGraph Checkpointer、Persistence、Durable Resume、Memory、HITL、Interrupt、Subgraph、Multi-agent。
- LangGraph Cloud 与 LangSmith Runtime Dependency。
- 通用 LLM SDK 或 Provider Platform。
- User Notes 与整理稿作为 Citation 来源；二者首版导航优先级也较低。

## 7. 已完成工作

- 完成 V4 Startup、根 README、V0–V3.5 Final Closeout 的渐进式阅读。
- 完成仓库根目录、主要代码入口、测试入口和数据入口检查。
- 完成 P0 源码审计，覆盖 Retrieval、Product Search、Evidence 物化、Source Version/Identity、AI 总结/字幕路径和 DeepSeek Provider。
- 确认当前 `EvidenceSearchService.search_library()` 会自行执行检索；V4 设计已要求拆出消费 `SearchExecution` 的 Materializer。
- 确认现有 Candidate Identity 不适合作为 Stable Citation；设计已定义与 Retrieval Strategy 解耦的稳定标识方向。
- 完成 V4 产品入口、Answer/Citation 合同、LangGraph 边界、预算和停止条件的讨论与决策。
- 完成 Goal 1 外部设计校验研究及主 Session 源码复核。
- 确认 `source_version` 是权威原字幕文件字节的 SHA-256；字幕文本或时间变化会使旧 Segment/Citation 失效。
- 完成 Goal 1 的 Citation Version、Canonical Segment Ordering、Evidence/Display Context 分离和 Repair Fail-closed 决策。
- 已形成：
  - `V4_DESIGN_PROPOSAL.md`
  - `V4_MASTER_STATE.md`
  - `V4_DECISION_LEDGER.md`
  - `V4_G1_EXECUTION_PROMPT.md`
  - `V4_G2_EXECUTION_PROMPT.md`
- Goal 1 — Complete Grounded RAG 已实现并通过主 Session Integration Review：
  - `POST /api/ask` Fast 模式；
  - Query Analysis 与最多两个 bounded rewrites；
  - 每个不同 Query 一次 Retrieval，Materializer 不自行搜索；
  - 当前原字幕 Evidence、Stale Skip 与 Transcript-only Context；
  - Versioned Stable Citation、Answer Blocks、一次 Repair 和最终 Source Version 复验；
  - `complete / partial / insufficient` 与类型化停止原因；
  - V4 Structured Provider 的一次传输重试，且不改变历史 Provider 调用语义；
  - 真实 DeepSeek Vertical Slice 与主 Session 独立回归验证。
- Goal 1 Integration Review 的正式实现报告为：
  - `V4_G1_IMPLEMENTATION_REPORT.md`
- Goal 2 — Independent Agentic Search 已实现并通过主 Session 第二次
  Integration Review：
  - `POST /api/ask` Deep 模式；
  - 从原始用户 Query 独立执行 Navigation、Focused Transcript Search 和
    Transcript Window Read；
  - Source-aware `NavigationDocument` 与 Transcript-only Fact Context 隔离；
  - 内部 `video_ids` Filter 在 Lexical、Dense 和 Hybrid 召回阶段生效；
  - 当前 Source Version、Timeline 和 Segment Identity 约束的权威
    `TranscriptEvidenceSpan`；
  - 结构化 DeepSeek Agent Action、运行时问题工作清单和 Evidence
    Accumulation；
  - 最薄 LangGraph `StateGraph`、条件分支和有界动态循环；
  - 6 Round、12 Tool、Repeat、No-new、Context 与 360/150/210 秒确定性边界；
  - Fast/Deep 共享 `AnswerFinalizer`、Answer Block、Citation、Validation 和
    AskResponse；
  - 真实 DeepSeek Vertical Slice、保留的 malformed Action 失败和主 Session
    独立回归验证；
  - 首次 Integration Review 的 Answer Reserve、Deadline 分类和 Finish/Stop
    Blocking Finding 已完成有界修正。
- Goal 2 Integration Review 的正式实现报告为：
  - `V4_G2_IMPLEMENTATION_REPORT.md`

## 8. 尚未完成

- 尚未创建正式 `/ask` 页面；当前共享 Ask API 的 Fast 与 Deep 模式均已完成。
- 尚未建立 V4 轻量离线 Eval 与端到端 Demo。

## 9. 验证基线

Goal 2 主 Session 第二次 Integration Review 独立复跑：

```text
24 passed（Goal 2 与 Integration Repair 定向）
12 passed（Fast Ask API）
75 passed（Retrieval / Evidence 定向）
1446 passed，4 deselected（默认全套）
1 existing Starlette/httpx deprecation warning
```

Goal 1 Session 使用真实 DeepSeek、真实字幕和本机数据库只读快照完成三条
Fast Query Vertical Slice，实测延迟约 37.6–112.1 秒。Goal 2 Session 使用
真实 DeepSeek、真实字幕、本机数据库临时只读快照和真实 Retrieval 完成
Navigation-first、Focused Transcript、Window/Replanning 与失败路径运行。
Goal 2 修正只改变 Deadline 和 Stop 边界，主 Session 已确认无需重复真实
Provider 调用。

## 10. 当前已知风险与待实测项

- 视频级 Navigation Projection 已在 Goal 2 真实 Query 中成功工作，当前未发现
  材料性 Recall 失败；仍需在 Goal 3 轻量 Eval 中扩大观察，失败后才考虑独立
  Navigation Index。
- Source Version 变化后的 Stale Skip 已实现并测试；真实产品运行中的发生频率仍未知。
- Goal 1 Vertical Slice 实测 Provider 延迟约 37.6–112.1 秒，Provider 是主要成本。
- 三条真实 Fast Query 均发生 Context Truncation，Grounded Answer Prompt 约 7.7k Tokens。
- Block 级 Citation 是否足够、是否需要更细的句子级结构，必须依据 Goal 1 真实失败决定。
- 真实跨视频 Query 使用一次 Repair 后成功；Repair 频率和整体 Fail-closed 对有效回答保留率的影响仍需轻量 Eval。
- Goal 2 Window/Replanning 真实 Case 的四次 Agent Decision 共消耗 58,396
  Tokens；Navigation Context 和 Policy 的成本效益需要在 Goal 3 轻量 Eval 中
  观察。
- Goal 2 当前单 Tool Evidence 包络在两个真实 Case 中分别丢弃 42、44 个
  Candidate Span；只有反复证明关键证据被排除时，才重新考虑选择策略或
  Reranker。
- 真实无证据 Case 出现一次严格 Agent Action Schema 漂移；当前
  Fail-closed 行为正确，发生频率仍需 Goal 3 观察。
- LangGraph `1.2.10` 已与项目依赖共同通过完整测试；项目代码只使用低层
  `StateGraph`，没有接入 Checkpointer、Persistence、Memory、HITL、
  Prebuilt Agent、LangGraph Cloud 或 LangSmith Runtime。
- 轻量 Eval 的具体 Case、指标和阈值尚未冻结，应由已实现的纵向闭环反推，而非预建平台。

这些均不改变当前三 Goal 架构。

## 11. 当前下一步

```text
Goal 1 已完成并通过 Integration Review
→ Goal 2 已完成并通过第二次 Integration Review
→ 与用户讨论 Goal 3 的有界产品、轻量 Eval 与 Demo 计划
→ 形成 V4 Goal 3 Execution Prompt
→ 再启动独立 Goal 3 Execution Session
```

在用户确认 Goal 3 计划前不创建 Goal 3 Execution Prompt，也不开始 Goal 3
实现。Goal 3 必须以已接受的 Fast/Deep 后端为基础，完成 `/ask` 产品入口、
共享 Evidence 展示、轻量 Eval、Trace 摘要和 Demo；不得把 Policy、Tool、
Navigation、Trace 或 Eval 拆成新平台。
