# Shiliu V4 Decision Ledger

```yaml
document_role: accepted_decision_record
status: active
last_updated: 2026-07-29
```

本文件只记录已经确认、会约束后续实现的 V4 决策。候选想法、纯实现细节和尚未到决策时点的问题不进入 Ledger。

## D-001 — 使用独立 `/ask` 双模式入口，保留 `/search`

```yaml
status: accepted
date: 2026-07-29
scope: product_entry
```

**决定**

- 新增 `/ask`，显式提供“快速回答”和“深入搜索”。
- 保留 `/search`，继续作为直接搜索证据库、手动查证、Debug 和 Demo 对比入口。
- `/ask` 复用现有字幕证据卡、证据展开和 B 站时间点跳转，不复制一套 Search UI 基础。

**理由**

回答型体验和检索型体验具有不同用户意图；明确分开入口可以保留现有调试与查证价值，同时让 V4 闭合面向用户的问答流程。

**未采用**

- 在 `/search` 内隐式混入回答模式。
- 用 Agentic Search 替换现有直接检索入口。

**影响**

Goal 3 需要增加 Ask 页面和共享展示适配，但现有 Search UI 基础继续作为可复用资产。

## D-002 — Fast 与 Deep 共享结构化 Answer Block 合同

```yaml
status: accepted
date: 2026-07-29
scope: answer_contract
```

**决定**

Fast 与 Deep 共享以下产品输出：

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

最终自然语言正文从 `answer_blocks` 直接生成。材料性段落必须绑定本次 Evidence Context 中已有的 Citation ID。

**理由**

结构化 Block 同时承载正文与引用关系，避免自由 `answer` 和独立 `claims` 漂移为两套事实源，也让 Fast/Deep 和前端证据卡保持同一合同。

**未采用**

- 自由 Answer 与独立 Claims 并存。
- Fast 和 Deep 分别定义 Answer/Citation API。

**影响**

Answer 生成、验证、序列化和 UI 渲染都必须以同一 Block 顺序工作；任何修复也必须回写结构化 Block，而不是只修改展示文本。

## D-003 — 回答充分度与运行停止原因分离

```yaml
status: accepted
date: 2026-07-29
scope: runtime_semantics
```

**决定**

```text
status
→ complete / partial / insufficient

termination_reason
→ answer_ready / budget_exhausted / no_new_evidence /
   repeated_search / provider_error / evidence_unavailable
```

**理由**

“已经找到了多少可回答内容”与“运行为何停止”是两个独立维度。分离后，用户展示、故障诊断和离线 Eval 都无需从一个混合状态反推含义。

**影响**

同一个 `termination_reason` 可以对应不同充分度；例如预算耗尽后仍可能产出 `partial`，Provider 失败也不能自动等同于无证据。

## D-004 — Deep Search 使用最薄的 LangGraph `StateGraph`

```yaml
status: accepted
date: 2026-07-29
scope: orchestration
```

**决定**

Deep Search 是有界但动态的多步状态工作流；LangGraph 用于显式状态、条件分支和可测试编排；Domain 与 Tool 保持框架无关；V4 不启用 Persistence、Memory、HITL 等非目标能力。

允许：

```yaml
- state
- nodes
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
- LangSmith runtime dependency
- prebuilt create_agent
```

Fast Grounded RAG 继续使用普通 Service Pipeline，不使用 LangGraph。Deep Search 使用底层 `StateGraph`，不使用高层 `create_agent`。

**理由**

Deep Search 需要 Planning/Replanning、动态 Tool 选择、Evidence Accumulation、Conditional Stop 和有界循环；低层 StateGraph 能显式表达这些控制流，同时保持可测试性。求职技术信号是附加价值，不是唯一采用原因。

**未采用**

- 为 Fast/Deep 全部引入 Graph。
- 高层预制 Agent。
- 在 V4 建设持久化 Agent Runtime。
- 当前直接冻结为自定义 Loop。

**影响**

LangGraph Node 只能薄包装框架无关 Service；未来替换编排器不应要求重写 Retrieval、Navigation、Transcript、Evidence 或 Answer 领域逻辑。

## D-005 — DeepSeek 使用结构化 JSON/Pydantic Action，不要求 Native Tool Calling

```yaml
status: accepted
date: 2026-07-29
scope: provider_and_agent_action
```

**决定**

- DeepSeek 继续通过现有 OpenAI-compatible Provider 路径工作。
- Agent Decision 输出首版采用结构化 JSON / Pydantic Action。
- Provider 只增加服务 V4 Runtime 所需的最小能力，不建设通用 LLM SDK。
- 首版不要求 Native Tool Calling。

**理由**

现有 Provider 已支持非流式 Chat Completion、JSON Prompt 和 Pydantic 解析。结构化 Action 足以驱动薄 StateGraph，能够减少与当前核心闭环无关的 Provider 平台工作。

**影响**

Goal 1/2 可随纵向链补足角色化请求、错误归类、超时和必要的上下文预算适配，但不能把 Provider 扩展拆为独立 Goal。

## D-006 — Navigation Context 与事实 Evidence Context 严格隔离

```yaml
status: accepted
date: 2026-07-29
scope: grounding_boundary
```

**决定**

- 标题、简介、AI 总结、User Notes 和整理稿只用于导航、Query 扩展和视频选择。
- 最终 Answer 的事实 Context 默认只包含权威 `TranscriptEvidenceSpan`。
- User Notes 和整理稿首版允许导航但禁止 Citation，初始优先级低。
- AI 总结不能作为最终事实证据。

**理由**

Navigation 内容有利于低成本缩小搜索范围，但其生成方式和可追溯性不足以替代原字幕/ASR。两类 Context 隔离可以兼顾 Agent 搜索效率与回答可验证性。

**影响**

Prompt、数据结构和 Tool 返回必须显式标注 Navigation 与 Evidence；Context Builder 不得把二者拼成同一事实输入。

## D-007 — 首版不建立独立 Navigation Index

```yaml
status: accepted
date: 2026-07-29
scope: navigation_retrieval
```

**决定**

先复用现有视频级混合索引、字段投影和必要的 Source Label/Post-filter。只有真实查询证明导航召回失败时，才重新考虑独立 Navigation Index。

**理由**

当前代码已有标题、简介、AI 总结与元数据的可检索投影，尚无证据表明独立索引是核心闭环的必要条件。

**影响**

Goal 2 必须记录并评估真实失败模式；不得仅因架构整洁性预建新索引基础设施。

## D-008 — 每个 Query 只执行一次 Retrieval，Evidence Materializer 消费既有结果

```yaml
status: accepted
date: 2026-07-29
scope: retrieval_evidence_boundary
```

**决定**

引入或等价表达：

```text
SearchExecution
  = request
  + raw retrieval response
  + product response
```

Evidence Materializer 接收 `SearchExecution` 或其中的权威 Raw Hit，不再自行调用 Retrieval。`ProductSearchService.search_with_raw()` 和 Evidence 物化不得对同一 Query 重复召回。

**理由**

单次检索结果必须能直接物化为带当前 Source Identity 的字幕 Evidence。重复检索会造成额外延迟，也可能让展示结果和最终 Citation 来自不同召回执行。

**影响**

现有 `EvidenceSearchService.search_library()` 的“检索并物化”耦合需要在 Goal 1 中做薄拆分；已有兼容入口可以保留，但新 Ask 主路径必须传递同一次执行结果。

## D-009 — Stable Citation 与 Retrieval Candidate Identity 解耦

```yaml
status: accepted
date: 2026-07-29
scope: citation_identity
```

**决定**

Stable Citation 由权威字幕证据身份派生，至少绑定：

```yaml
source_artifact_id:
source_version:
timeline:
ordered_segment_ids:
```

不得把 Retrieval Method、Parent Chunk 或排序策略等易变检索细节作为 Citation 稳定身份的必要部分。

在线只做确定性的 Citation ID、Evidence Identity、Source Version 和 Segment 检查；语义支持质量放入轻量离线 Eval，不增加 Runtime Semantic Judge。

**理由**

引用应随底层证据版本变化而失效，但不应因 Retrieval 策略或排名实现变化而无意义漂移。确定性检查适合在线 Fail-closed；语义 Judge 会引入高延迟、不可重复性和历史治理重量。

**影响**

Stable Citation 和 Runtime Validator 保持为薄 Adapter，不发展成 Citation Platform。

## D-010 — Stale Evidence 必须跳过，不能进入 Citation

```yaml
status: accepted
date: 2026-07-29
scope: stale_evidence
```

**决定**

当 Retrieval Hit 无法绑定当前 Source Version：

```text
不得进入 Citation
→ 记录 stale evidence
→ 跳过该 Hit
→ 在预算内继续搜索
```

只有没有其他可用 Evidence 时，才返回明确的 `evidence_unavailable`，并在 limitations/trace 中表达 Index Stale。

**理由**

陈旧索引命中不能被伪装成当前权威字幕证据；同时，单个陈旧 Hit 不应过早终止仍可能成功的搜索。

**影响**

Evidence Materializer、Agent Evidence Accumulation 和最终 Citation Validator 都必须执行版本检查。

## D-011 — Deep Search 使用运行时问题覆盖状态

```yaml
status: accepted
date: 2026-07-29
scope: replanning_state
```

**决定**

Agent State 至少表达：

```yaml
open_questions:
resolved_questions:
evidence_spans:
visited_video_ids:
visited_segment_ids:
previous_queries:
decision_rounds:
tool_calls:
consecutive_no_new_evidence:
termination_reason:
```

**理由**

这些字段支持 Replanning、去重、Evidence Accumulation 和确定性停止。它们是运行时工作清单，不是 Gold Aspect、Eval Gate 或新的治理对象。

**影响**

State 更新必须由可测试的确定性 Reducer/Service 控制；Prompt 可以提出动作，但不能自行绕过状态约束。

## D-012 — 预算与停止条件由确定性代码执行

```yaml
status: accepted
date: 2026-07-29
scope: runtime_budget
```

**决定**

Fast 首版预算：

```yaml
query_analysis_calls: 1
answer_calls: 1
repair_calls: max_1
iterative_search: false
```

Deep 首版预算：

```yaml
agent_decision_rounds: max_6
tool_calls: max_12
answer_calls: 1
```

Deep 还必须由代码检测：重复 Query、重复 Segment、连续无新 Evidence、Context Budget 和总运行时间。预算与停止不能只写进 Prompt。

**理由**

确定性执行才能保证成本上界、可复现测试和可解释的 `termination_reason`。

**影响**

这些数字是 Vertical Slice 的安全包络，不是永久 SLA；调整必须基于真实延迟、成本和回答质量数据。

## D-013 — 只设三个纵向 Goal，并采用三类范围分类

```yaml
status: accepted
date: 2026-07-29
scope: delivery_structure
```

**决定**

```text
Goal 1：Complete Grounded RAG
Goal 2：Independent Agentic Search
Goal 3：Product Integration、Lightweight Eval 与 Demo
```

所有缺口只分为：

```yaml
must_build:
in_goal_support:
deferred:
```

**理由**

V4 的价值来自完整的用户纵向闭环。Provider、Navigation、Citation、Trace 和 Eval 都应以薄适配嵌入核心链路，不能再次演化为独立平台或重型治理工程。

**未采用**

- Navigation Infrastructure Goal。
- Provider Platform Goal。
- Citation Platform Goal。
- Trace Platform Goal。
- Eval Platform Goal。
- Framework/Persistence Goal。

**影响**

Goal Execution Prompt 必须按用户可验证的端到端结果组织工作，并明确包含必要的随链适配。

## D-014 — 首版不要求 Answer Token Streaming

```yaml
status: accepted
date: 2026-07-29
scope: response_delivery
```

**决定**

最终答案一次性返回。搜索进度事件可以实现，但不得阻塞核心闭环。

**理由**

首版的首要风险是 Grounding、Citation 和有界搜索正确性，而不是逐 Token 展示。一次性结构化输出也更容易执行完整的确定性引用验证。

**影响**

Token-by-token Streaming 进入 `deferred`；State Progress Events 可作为 Goal 2/3 的薄支持。

## D-015 — Stable Citation 使用显式 Identity Version 和权威 Segment 顺序

```yaml
status: accepted
date: 2026-07-29
scope: citation_identity
```

**决定**

Goal 1 定义：

```text
CITATION_IDENTITY_VERSION = "v4-citation-identity-v1"
```

Citation Hash 至少绑定：

```yaml
citation_identity_version:
source_artifact_id:
source_version:
timeline_run_id:
ordered_segment_ids:
```

Segment 顺序必须来自权威 `segment_ordinal` 或 `run_local_ordinal`。不得按不透明的 Segment Hash 字符串排序。重复 Segment 被拒绝；声明连续的 Span 必须通过同一 Source、Version、Timeline 和连续 Ordinal 检查。

**理由**

拾流现有 Source Identity、Mapping 和 Replay 合同均显式版本化。Citation 算法同样需要迁移护栏，而稳定身份不能依赖 Query、Rank、Retriever 或 UI 编号。

**源码事实**

- `source_version` 是权威原字幕文件字节的 SHA-256。
- `segment_id` 包含 `source_artifact_id`、`source_version` 和原始 Ordinal。
- 字幕文本或时间变化会改变 Source Version，并使旧 Segment/Citation 失效。

**影响**

Goal 1 必须为 Citation Hash 提供固定 Canonical Serialization 和属性测试；Identity Version 是薄合同，不发展成 Citation Platform。

## D-016 — Citation 事实 Span 与 UI 展示扩窗分离

```yaml
status: accepted
date: 2026-07-29
scope: evidence_display_boundary
```

**决定**

Citation Identity 只绑定实际进入事实 Answer Context 的 Segment 集合。

```yaml
factual_support_segments:
  included_in_citation_identity: true

display_context_before_after:
  included_in_citation_identity: false
```

若 Window Reader 加入的相邻 Segment 实际进入模型事实 Context，则它们属于事实 Span；若仅在用户展开字幕卡时展示，则不能改变 Citation Identity。

**理由**

事实支持范围与阅读辅助上下文具有不同语义。UI 展开行为不能让同一事实引用发生身份漂移。

**影响**

Goal 1 的 `TranscriptEvidenceSpan`、Citation Adapter 和前端展示字段必须显式区分事实 Segment 与显示上下文。

## D-017 — Goal 1 所有 Answer Blocks 强制引用，Repair 失败整体关闭

```yaml
status: accepted
date: 2026-07-29
scope: grounded_answer_validation
```

**决定**

- Goal 1 首版每个非空 `answer_block` 都必须至少引用一个本次 Context Allowlist 中的 Citation ID。
- 标题、状态说明和限制不作为无引用 Answer Block；分别由 UI、`status` 和 `limitations` 表达。
- Answer 最多 Repair 一次，并且只能使用相同 Query、相同 Evidence Context 和相同 Citation Allowlist。
- Repair 后重新执行完整确定性验证。
- Repair 后仍然无效时，返回：

```yaml
status: insufficient
answer_blocks: []
termination_reason: provider_error
```

- 首版不自动删除非法 Block 后保留其余 Block，也不在运行时自动拆分“半支持 Block”。

**理由**

没有 Runtime Semantic Judge 时，代码无法可靠判断无引用文字是否“非材料性”，也无法确认删块后的剩余答案仍然连贯。更严格的全 Block 引用和整体 Fail-closed 能保持确定性边界。

**影响**

Block 原子性通过 Prompt 与轻量离线 Supportedness Eval 约束。是否需要句子级结构或部分 Block Salvage，只能依据 Vertical Slice 的真实失败重新决定。

## D-018 — Provider 传输重试只服务 V4 Structured Runtime，Answer Repair 不处理无输出故障

```yaml
status: accepted
date: 2026-07-29
scope: provider_and_repair_boundary
```

**决定**

- `query_analysis` 与 `grounded_answer` 的 V4 Structured Runtime 遇到可重试
  Transport Failure 时最多重试一次。
- 历史 `complete_json()`、`complete_raw()` 和 `test_connection()` 保持单次
  HTTP 请求语义。
- Answer Repair 只处理已经收到内容但未通过 JSON/Pydantic Schema 的输出，
  或已经形成 Draft 但未通过确定性 Answer/Citation Validation 的结果。
- Network、Timeout、Authentication、Balance、Forbidden、Model Not Found、
  Bad Config、Context Too Large、Output Budget Exhausted、Empty Output 及其他
  没有可修复结构化内容的 Provider Failure 直接返回
  `insufficient / provider_error`，不得消耗 Repair Call。
- Logical Provider Call 与底层 Transport Retry 分开计数。

**理由**

Repair 是同一 Evidence Context 内的结构化答案修复，不是第二套 Provider
重试机制。将无输出故障送入 Repair 会扩大延迟与调用成本，也会混淆
`provider_error` 和 Answer Validation Failure。将 Transport Retry 限定在
V4 Structured Runtime 可满足 Fast/Deep 的有界容错需求，同时不改变历史
Transcript、Summary、Taxonomy 和 Single-flight 链的行为。

**影响**

Goal 2 的结构化 Agent Action 和共享 Grounded Answer 必须沿用该边界。任何
更复杂的退避、熔断或 Provider 平台能力仍不属于 V4。

## D-019 — Deep Search 采用 360/150/210 秒确定性时间包络

```yaml
status: accepted
date: 2026-07-29
scope: deep_runtime_deadline
```

**决定**

Deep Search 第一版采用：

```yaml
total_runtime_seconds: 360
search_phase_cutoff_seconds: 150
final_answer_reserve_seconds: 210
```

- 360 秒覆盖完整 Deep 请求，不只是 Agent 搜索循环。
- 150 秒后不得开始新的 Agent Decision 或 Tool。
- 如果已有可用 Evidence，立即进入共享 Grounded Answer Finalization。
- Final Answer 与现有一次受控 Same-context Repair 共用最多 210 秒余额。
- Provider 调用必须被剩余 Monotonic Deadline 限制。

**理由**

Goal 1 的真实 DeepSeek Vertical Slice 已观察到约 37.6–112.1 秒延迟，且一次
Repair 可能成为完整回答的一部分。Deep Search 如果把全部时间用于搜索，会
在已经找到 Evidence 后仍无法可靠完成最终结构化回答。将搜索阶段和回答保留
时间显式分开，可以同时保持动态搜索价值、总成本上界和可解释停止。

**影响**

- Goal 2 必须使用 Fake Clock 和受控 Provider Timeout 测试整个包络。
- `budget_exhausted` 必须能表达 Search、Context 或总时间预算停止。
- 可以为 V4 Structured Provider 增加可选的 Per-invocation Timeout/Deadline，
  但 Fast 默认行为和历史 Provider API 语义必须保持不变。
- 该包络是 Vertical Slice 的第一版安全值，不是生产 SLA；调整必须依据真实
  延迟、成本与回答质量，并由主 Session 记录。
