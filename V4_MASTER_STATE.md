# Shiliu V4 Master State

```yaml
document_role: current_state_authority
status: v4_complete_v4_1_partial_closed
implementation_status: goals_1_2_3_and_v4_1_implementation_complete
runtime_changes_status: v4_1_h1_h2_accepted
current_phase: v4_v4_1_formally_archived
archive_state: final
last_updated: 2026-07-30
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
- `/ask` 默认选择“快速回答”；V4 不做 Fast/Deep 自动路由。
- Fast 返回 `partial` 或 `insufficient` 时，提供保留原 Query 和筛选条件的
  “使用深入搜索继续”显式操作，不自动升级。
- Fast 与 Deep 使用同一个 Ask 输出合同、Answer/Citation 规则和 Evidence 展示层。
- 用户 Trace 摘要默认可见；开发者 Trace 默认折叠并按需读取。
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
| Goal 3 — Product Integration、Lightweight Eval 与 Demo | `complete` | 完成 `/ask`、共享证据展示、轻量离线 Eval、Trace 摘要和可演示闭环 |

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
- Search/Ask 共用的薄 Evidence Renderer、终止原因文案和 Deep Policy Version
  Trace 字段。
- 只服务 Goal 3 的小型 Eval Runner 与保留结果文件。

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
- Fast/Deep 自动路由、Trace 持久化、通用 Observability Dashboard。
- Fast/Deep 用户反馈记录与偏好比较；建议在 V5 早期以薄记录实现，不作为
  Runtime Judge、自动路由或离线 Eval 的替代。
- 新建 SSE/WebSocket 进度基础设施；只有现有事件可无阻塞复用时才作为薄增强。
- 通用 Skill/Policy Registry。

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
  - `V4_G3_EXECUTION_PROMPT.md`
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
- Goal 3 的产品入口、默认模式、显式 Deep 升级、Trace 两层投影、轻量 Eval、
  优化触发条件和四段 Demo 计划已讨论并批准。
- Goal 3 — Product Integration、Lightweight Eval 与 Demo 已实现并通过主
  Session 第二次 Integration Review：
  - 新增 `/ask` 页面，Fast 默认、Deep 显式选择，Fast `partial` /
    `insufficient` 可保留 Query 继续 Deep；
  - `/ask` 与 `/search` 共用薄 Evidence Renderer、权威字幕卡、折叠展开、
    Citation 定位和 Bilibili 时间跳转；
  - 用户 Trace 默认可见，Developer Trace 默认折叠并按需读取；
  - Deep Trace 保留 `v4-deep-policy-v1`、有界 Action、Observation、Usage、
    Budget 和 Stop 信息，不暴露隐藏推理或完整 Prompt；
  - 完成六条普通 Query、6 Fast + 4 Deep 的真实轻量 Eval、10/10 人工审阅和
    Search/Fast/Deep/Honest Failure 四段 Demo；
  - 主 Session 首次 Integration Review 发现有限样本被表述为全库否定，以及
    Eval Checker 硬编码/空洞通过两个 Blocking Findings；
  - 有界 Repair 收紧 Fast/Deep 共享 Answer Boundary，为 `insufficient`
    增加范围诚实保护，将 Checker 改为真实 Schema、Status/Termination、
    Citation Resolution 和当前字幕重建检查；
  - 经明确授权只复跑 3 Fast + 1 Deep，Fast/Deep 无证据 Case 均不再外推全库
    缺失，原 10 次结果保持不变；
  - Goal Session 对一条 Citation 的初审因 500 字 excerpt 截断产生误判；主
    Session 通过当前 Source Version 和 Stable Citation 重建确认完整字幕直接
    支持 Answer Block，未触发额外 Provider 调用；
  - 定向、默认全套、浏览器 Fixture、JavaScript、Compileall、Pip 和 Diff
    验证通过，无剩余 Blocking Finding。
- Goal 3 Integration Review 的正式实现报告和 Repair 结果为：
  - `V4_G3_IMPLEMENTATION_REPORT.md`
  - `eval/v4_goal3_repair_results.json`

## 8. 尚未完成

V4 三个纵向 Goal 和高层完成条件均已完成。以下不属于 V4 未完成项：

- Deferred 能力；
- 生产 SLA；
- 大规模质量评测；
- V5 个性化、主动行为或长期 Agent Runtime。

## 9. 验证基线

Goal 3 实现与有界 Repair 最终验证：

```text
97 passed（Goal 3 扩展定向）
1457 passed，4 deselected（默认全套）
1 existing Starlette/httpx deprecation warning
Compileall、Pip Check、三个 JavaScript Check、git diff --check passed
```

主 Session 第二次 Integration Review 另独立复跑 57 项 Goal 3 Repair、Ask、
Deep 和 Search 定向测试及默认完整测试集，结果通过。

真实验证历史：

- Goal 1 使用真实 DeepSeek、真实字幕和本机数据库只读快照完成三条 Fast
  Vertical Slice，实测延迟约 37.6–112.1 秒；
- Goal 2 使用真实 DeepSeek、真实字幕、本机数据库临时只读快照和真实
  Retrieval 完成 Navigation-first、Focused Transcript、Window/Replanning
  与失败路径运行；
- Goal 3 使用真实 DeepSeek 和临时数据库快照完成 6 Fast + 4 Deep 初始矩阵；
- Goal 3 Repair 在明确授权下只复跑 3 Fast + 1 Deep，没有重采样；
- 四条 Repair 结果的 10 项确定性检查全部通过，人工审阅完成 4/4；
- 原 `eval/v4_goal3_results.json` SHA-256 保持
  `65cc177742492459a5f3f3032f24b5d0495921dc7cc57b9a2fc4745c9e0d5b2e`。

## 10. 当前已知边界与后续观察项

- 视频级 Navigation Projection 在 Goal 2 Vertical Slice 和 Goal 3 轻量 Eval
  中均未出现材料性 Recall 失败，不触发 Independent Navigation Index。
- Source Version 变化后的 Stale Skip 已实现并测试；真实产品运行中的发生频率仍未知。
- Goal 1 Vertical Slice 实测总延迟约 37.6–112.1 秒；V4.1 没有证明 Fast
  整体延迟改善。H0 Thinking Off 配置组合的中位延迟显著降低，但同时改变
  Thinking、Reasoning Effort 和 Temperature，并伴随材料性质量退化，不能作
  单变量因果解释；正式 Runtime 保持 Baseline，也不能把全部波动归因于
  DeepSeek 服务端。
- Goal 3 六条真实 Fast 运行均发生 Context Truncation；当前没有重复证据证明
  关键事实稳定落在预算之外，不触发 Reranker 或 Automatic Context Compaction。
- V4 Goal 3 曾有一条 Fast 跨视频结果因 Provider 长度上限诚实返回
  `insufficient/provider_error`；V4.1 H1 已收紧跨视频综合边界，但 Fast After
  又因一次独立 Provider Failure 缺少成功在线样本。复杂跨视频问题仍适合用户
  显式选择 Deep。
- Goal 3 Repair 的 `partial_universal_claim` 曾安全但偏保守地返回
  `insufficient`；该历史问题已由 V4.1 H1 修正。当前权威字幕中的直接反例可以
  形成带 Citation、有限范围且明确非全库审计的 `partial` 回答，不再把该问题
  列为当前未解决项。
- V4 原始 Goal 2 Window/Replanning Case 的四次 Agent Decision 曾消耗 58,396
  Tokens。V4.1 H2 在两条 Paired Deep Case 中将累计 Prompt Tokens 分别降低
  55.7% 和 57.9%，合计降低 56.9%；总延迟降低约 20.1%，同时保留或改善
  Replanning、Evidence Coverage、Citation 和四维人工质量。两条 Case 尚不能
  证明所有 Deep Query 都获得相同比例收益。
- Goal 2 当前单 Tool Evidence 包络在两个真实 Case 中分别丢弃 42、44 个
  Candidate Span；Goal 3 未证明这造成重复材料性回答失败。
- 真实无证据 Case 出现一次严格 Agent Action Schema 漂移；当前
  `insufficient/provider_error` Fail-closed 行为正确。
- LangGraph `1.2.10` 已与项目依赖共同通过完整测试；项目代码只使用低层
  `StateGraph`，没有接入 Checkpointer、Persistence、Memory、HITL、
  Prebuilt Agent、LangGraph Cloud 或 LangSmith Runtime。
- Goal 3 Eval 的 `quote_excerpt` 是有界审阅材料而非完整 Citation；人工
  Supportedness 判断若涉及截断范围外内容，必须按 Stable Citation 重建当前
  权威字幕。
- 质量、延迟、Token 和成本阈值未冻结；六条轻量 Case 不支持生产 SLA 或大型
  总分 Gate。
- V4.1 Fast After 的 Cross-video Run 因一次 Provider Failure 没有生成可用
  Answer；Fail-closed 正确，但该样本的 `coverage/usefulness` 均为 fail，因此
  H1 Cross-video 在线质量仍未证明。没有通过重采样把它改写为通过。
- V4.1 E2E Campaign Identity 保存 Base URL Hash、三个角色 Model 和统一
  Baseline 标签，但没有逐角色表达 Thinking/Reasoning，也未把角色配置所在的
  `src/shiliu/app.py` 纳入 Source Digest；本次未发现实际配置漂移，但该 Harness
  不能声称完整的角色级 Provider Configuration 漂移保护。

这些均为已披露边界或后续产品观察项，不阻塞 V4 完成，也不自动授权 Deferred
能力。

## 11. 当前下一步

```text
Goal 1 已完成并通过 Integration Review
→ Goal 2 已完成并通过第二次 Integration Review
→ Goal 3 已完成有界 Repair 并通过第二次 Integration Review
→ V4 三个纵向 Goal 与高层完成条件全部完成
→ V4.1 Hardening 实现完成，以 partial 关闭一项未证明的 Fast Cross-video 在线质量
→ V4 / V4.1 正式封存
→ 可以开始讨论拾流后续版本
```

后续如需启动 V5、扩大 Eval、调整生产质量/延迟目标或重新考虑 Deferred 能力，
必须由用户另行讨论和授权；不得把这些事项倒写为 V4 未完成。

## 12. V4.1 Runtime and Context Hardening

```yaml
v4_1_status: partial
implementation_complete: true
runtime_changes_accepted: true
closeout_state: closed_with_known_evidence_gap
remaining_blocking_finding: none
date: 2026-07-30
branch: codex/v4.1-hardening
provider_configuration: baseline_unchanged
formal_runtime_scope:
  - shared_grounded_answer_boundary
  - deterministic_deep_decision_view
continuation_provider_e2e:
  completed_runs: 12
  logical_provider_invocations: 34
  transport_http_attempts: 34
  thinking_off_calls: 0
  fixed_replay_calls: 0
unproven_online_quality:
  - fast_cross_video_after
```

V4.1 在不改变 Retrieval、Context Selection、Ask Contract、Citation Identity、
Source Authority、Tool、Budget、Graph 拓扑、产品入口、Provider、模型或
`max_tokens` 的前提下完成实现并以 `partial` 关闭：

- H0 报告口径更正，以及独立于旧 H0 双配置路径的 crash-safe baseline-only
  E2E harness；
- H1 共享 Grounded Answer hardening：明确有限样本与直接反例的逻辑边界，
  支持带 Citation 的有限 `partial` 结论，改善当前字幕范围内的跨视频综合，并
  对完全重复 Answer Block 做确定性拒绝/一次既有 Repair；
- H2 `DeepRuntimeState → Deterministic DecisionViewProjector → existing
  AgentAction Provider`：完整 Runtime State 和 Guard 不变，模型投影移除完整
  Evidence `segment_ids`、重复长 Navigation Summary Sections 和最近 60 个
 逐项 Visited Segment IDs，同时保留合法 Window Anchor、Evidence Inventory、
  工作清单、最近观察和精确剩余预算。

Paired baseline-only E2E 使用相同 Manifest、Query Hash、Corpus SHA-256
`e3e803b9288755e8dd220efb0a21e345b49f9b1585765e592f2f178069614286`：

- Fast Before/After 各 4 Run；No-evidence、Single-topic 和 Universal/
  Partial-support 验收通过。Fast After 的 Cross-video Run 出现一次独立
  `provider_error`，诚实 fail-closed，未 Repair、未重跑、未错误归因给 H1；
  该 Run 的 Supportedness/Status Honesty 通过，但 Coverage/Usefulness 失败，
  因而不宣称 H1 Cross-video 在线质量已经验证；
- Deep Before/After 各 2 Run。两条 Deep Run 的累计 Prompt Tokens 分别从
  29,605 降至 13,128（55.7%）和从 36,149 降至 15,237（57.9%）；Decision
  Round 从 3 增至 4，但 Navigation/Transcript/Replanning、Evidence Coverage、
  Citation 与四维质量均保持或改善；
- 12 个 Run 均有 Provider 前 WAL、逐 Run 原子 Checkpoint、当前 Citation
  重建和进程内四维复核；所有 Checkpoint 终态完整，无未知 `in_flight`。

最终验证：

```text
68 passed（H0/H1/H2 定向）
61 passed（/ask、/search、Fast/Deep、Evidence UI 定向）
1498 passed，4 deselected（默认完整套件）
Compileall、Pip Check、ask.js、search.js、git diff --check passed
1 existing Starlette/httpx deprecation warning
```

正式 Closeout：

- `V4_1_IMPLEMENTATION_AND_CLOSEOUT_REPORT.md`
- `V4_V4_1_FINAL_ARCHIVE_CLOSEOUT.md`

接受边界：

- H1 的正式实现、确定性测试和 No-evidence、Single-topic、Universal/
  Partial-support 三类成功 Paired Evidence 被接受；
- H2 的正式实现和两类成功 Paired Evidence 被接受；
- H1 Cross-video 在线质量保留为未证明观察项，不回退代码，也不追加 Provider
  重采样；
- V4 三个纵向 Goal 和 V4 完成状态不受 V4.1 `partial` Closeout 影响。

V4.1 正式 Runtime 没有采用 Thinking Off、Reduced Reasoning、新 Provider、
Reranker、Runtime Judge、LLM Summary、Memory、Persistence、Multi-Agent、
Streaming、自动路由或新平台。H0 Fixed Replay 曾在调查包络内测试 Thinking
Off，但结论是不采用；该实验与消耗由 H0 报告单独披露。后续如需新的真实
Provider 调用或扩大范围，仍需 Main Session 独立授权。

## 13. Final Archive

```yaml
v4_status: complete
goal_1: complete
goal_2: complete
goal_3: complete
remaining_v4_blocking_finding: none
v4_1_status: partial
v4_1_implementation_complete: true
v4_1_runtime_changes_accepted: true
v4_1_closeout_state: closed_with_known_evidence_gap
remaining_v4_1_blocking_finding: none
archive_file: V4_V4_1_FINAL_ARCHIVE_CLOSEOUT.md
```

V4 / V4.1 已正式结束。`partial` 只保留 Fast Cross-video After 缺少成功在线
样本这一项证据缺口，不触发重采样或继续修复。后续版本必须围绕新的产品命题
重新讨论和授权，不得从 Deferred 清单自动生成 Backlog。
