# Shiliu V4 Project Review and WebGPT Handoff

```yaml
document_role: planning_session_handoff
audience: Shiliu main WebGPT planning session
scope: Shiliu V4 only
status: V4 implementation and integration accepted
date: 2026-07-29
branch: codex/v4-main
commit: cbf264be2571c3d62775c064445de8a1ba17880a
historical_scope: V4 completion baseline before V4.1
current_state_authority: V4_MASTER_STATE.md
```

> 后续状态说明：本文冻结 V4 完成基线，不承担 V4.1 Closeout 权威。V4.1
> Hardening 的当前状态为有界 `partial` Closeout；H1/H2 实现均保留，具体接受
> 边界以 `V4_MASTER_STATE.md`、`V4_DECISION_LEDGER.md` 和
> `V4_1_IMPLEMENTATION_AND_CLOSEOUT_REPORT.md` 为准。

## 1. 阅读目的

本文用于让参与拾流整体规划的主 WebGPT Session 快速掌握：

- V4 实际完成了什么；
- Fast Grounded RAG 与 Independent Agentic Search 如何实现；
- V4 与最初使命是否一致；
- 哪些能力是有意 Deferred，而不是遗漏；
- 真实测试、Eval 和 Integration Review 证明了什么；
- 当前主要产品与工程风险；
- 后续规划时应依据什么信号，而不是直接把 Deferred 列表变成新 Backlog。

本文是面向规划讨论的自包含复盘，不替代：

- `V4_MASTER_STATE.md`：当前状态权威；
- `V4_DESIGN_PROPOSAL.md`：产品与架构设计；
- `V4_DECISION_LEDGER.md`：已接受决策及理由；
- Goal 1/2/3 Implementation Report：实现和验证证据。

---

## 2. Executive Summary

V4 已完成一个真实用户闭环：

```text
已有 Bilibili 收藏、字幕与 Retrieval 资产
→ 用户提出自然语言问题
→ 选择快速回答或深入搜索
→ 系统搜索并物化当前版本权威字幕
→ 生成结构化 Grounded Answer
→ 提供时间戳 Citation、原字幕卡和 B 站跳转
→ 展示运行摘要与有界 Developer Trace
→ 证据不足时返回 partial / insufficient，而不是虚构
```

正式状态：

```yaml
goal_1_complete_grounded_rag: complete
goal_2_independent_agentic_search: complete
goal_3_product_integration_eval_demo: complete
v4_status: complete
main_session_integration_review: accepted
remaining_blocking_finding: none
```

V4 的完成含义是：

> 产品入口、核心架构、Fast/Deep 用户闭环、Grounding、Citation、Trace、
> 轻量真实 Eval 和 Demo 均已实现并通过 Integration Review。

V4 的完成不等于：

- 生产 SLA 已建立；
- 延迟已达到成熟交互产品水平；
- 大规模质量泛化已证明；
- 所有 Deferred 能力都应立即进入下一版本。

---

## 3. V4 最初使命与最终结果

V4 最初使命是：

```text
Complete Grounded RAG
+
Independent Agentic Search
+
Shared Grounded Answer / Timestamp Citation
+
Lightweight Trace / Eval
```

四部分均已落地。

核心原则也保持不变：

```text
继承技术资产
不继承治理重量
```

V4 继承了 V0–V3.5 的：

- Lexical、Dense、Hybrid Retrieval；
- 字幕/ASR 与 Source Artifact；
- Source Version、Timeline、Segment Identity；
- Evidence、Stale Detection 和 Retrieval Provenance；
- 系统级事实权威结论。

V4 没有把以下历史治理机制接入产品 Runtime：

- Candidate Builder 作为所有路径的必经入口；
- Runtime Semantic Judge；
- 大型 Frozen Eval；
- 多 Reviewer、密封运行或复杂审批链；
- 为每个内部判断创建独立 Gate、Audit 或 Closeout。

---

## 4. 用户现在拥有的产品

### 4.1 `/ask`

`/ask` 是统一问答入口，显式提供：

```text
快速回答 | 深入搜索
```

- Fast 默认；
- Deep 必须由用户显式选择；
- Fast 返回 `partial` 或 `insufficient` 时，可以保留 Query 和 Filters
  “使用深入搜索继续”；
- 系统不会后台自动升级到 Deep；
- 最终答案一次性返回，不做 Token Streaming。

### 4.2 `/search`

`/search` 被保留为：

- 直接搜索字幕证据；
- 手动查证；
- Debug；
- Demo 中与 Answer 路径对比。

`/ask` 和 `/search` 共用薄 Evidence Renderer、字幕来源、时间格式、Evidence
Card、折叠展开和 Bilibili 时间点跳转，但保留各自的页面状态机。

### 4.3 统一输出

Fast 与 Deep 共用：

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

`answer_blocks` 是答案正文的唯一事实源，不同时维护自由 Answer 和独立 Claims。

`status` 表示回答充分度：

```text
complete / partial / insufficient
```

`termination_reason` 表示运行停止原因：

```text
answer_ready
budget_exhausted
no_new_evidence
repeated_search
provider_error
evidence_unavailable
```

两者不能混用。

---

## 5. Goal 1：Complete Grounded RAG

### 5.1 用户结果

Fast 模式从用户 Query 完成：

```text
Query Analysis
→ 最多两个 Bounded Rewrites
→ 每个不同 Query 一次 Retrieval
→ 当前版本原字幕 Evidence
→ Transcript-only Context
→ Structured Answer Blocks
→ Stable Citation
→ 最终 Source Version Revalidation
```

### 5.2 核心实现

- `POST /api/ask`，`mode=fast`；
- 一次 Query Analysis；
- 最多两个 Rewrite；
- 每个不同 Query 恰好一次 Retrieval；
- `SearchExecution` 同时保留请求、Raw Retrieval 和 Product Projection；
- Evidence Materializer 消费既有执行结果，不自行重复召回；
- Stale Hit 跳过并记录；
- 只有当前 Source Version 的 `TranscriptEvidenceSpan` 能进入事实 Context；
- 标题、简介、AI 总结、Notes 和整理稿不能进入最终事实 Context；
- Answer 最多进行一次 Same-context Repair；
- Repair 后仍不合规则整体 Fail-closed；
- Answer 返回前再次验证 Source Version。

### 5.3 Stable Citation

Citation 与 Retrieval Candidate Identity 解耦，至少绑定：

```yaml
source_artifact_id:
source_version:
timeline_run_id:
ordered_segment_ids:
```

结果是：

- 更换 Retrieval Method 或排名策略不会无意义地改变 Citation；
- 字幕文本、时间或 Source Version 变化会正确使旧 Citation 失效；
- UI 展示扩窗不会改变事实 Citation Identity。

---

## 6. Goal 2：Independent Agentic Search

### 6.1 “独立”的准确含义

Deep 不会先执行 Fast RAG，也不依赖 Candidate Builder 作为入口。

它从原始用户 Query 独立开始：

```text
Navigation
→ Focused Transcript Search
→ Transcript Window Read
→ Observation
→ Planning / Replanning
→ Evidence Accumulation
→ Conditional Stop
→ Shared Grounded Answer
```

因此 Deep 的准确表达是：

> Agentic Navigation/Retrieval + 共享的 Transcript-grounded Answer。

Fast 和 Deep 拥有不同 Retrieval/Orchestration 路径，但共享最终 Evidence、
Answer、Citation、Validation 和 UI 合同。

### 6.2 Navigation 与事实隔离

Navigation 可以使用：

- 标题；
- 简介；
- AI 总结；
- 元数据；
- 低优先级 Notes 和整理稿投影。

这些内容全部标记为：

```yaml
authority: navigation_only
citation_allowed: false
```

最终事实 Context 仍只能包含当前版本原字幕/ASR。

### 6.3 LangGraph 使用边界

Deep 使用底层 LangGraph `StateGraph`，只承担：

- State；
- Node；
- Conditional Edge；
- Bounded Loop；
- 状态进度事件。

未使用：

- Checkpointer；
- Persistence；
- Durable Resume；
- Memory；
- HITL；
- Interrupt；
- Subgraph；
- Multi-Agent；
- LangGraph Cloud；
- LangSmith Runtime；
- Prebuilt `create_agent`。

LangGraph Node 只是框架无关 Service 的薄包装。

### 6.4 Agent Action

DeepSeek 使用结构化 JSON/Pydantic Action，不要求 Native Tool Calling。

Agent 可选择的行为包括：

- Navigation Search；
- Transcript Search；
- Transcript Window Read；
- Finish；
- Stop。

Runtime State 至少维护：

- Open/Resolved Questions；
- Evidence Spans；
- Visited Video IDs；
- Visited Segment IDs；
- Previous Queries；
- Decision Rounds；
- Tool Calls；
- Consecutive No-new Evidence；
- Termination Reason。

这些只是 Replanning 工作清单，不是 Gold Aspect 或 Eval Gate。

### 6.5 确定性预算

```yaml
decision_rounds: max_6
tool_calls: max_12
focused_video_limit: 8
consecutive_no_new_evidence: 2
final_context_chars: 12000
total_runtime_seconds: 360
search_phase_cutoff_seconds: 150
final_answer_reserve_seconds: 210
```

重复 Query、重复 Segment、No-new Evidence、Context 和总时间均由代码控制，
不能只依赖 Prompt。

---

## 7. Goal 3：Product Integration、Lightweight Eval 与 Demo

### 7.1 产品集成

Goal 3 完成：

- `/ask` Route、Template、JavaScript 和响应式样式；
- Fast 默认和 Deep 显式选择；
- Fast-to-Deep 继续操作；
- Answer Block 与 `[1][2]` Citation；
- 点击 Citation 后展开、滚动、聚焦和高亮 Evidence；
- Search/Ask 共用 Evidence Renderer；
- Loading、Network Error、Provider Error、Complete、Partial、Insufficient；
- Desktop 和 390px Mobile 浏览器验证。

### 7.2 Trace

用户 Trace 默认可见，展示：

- Mode；
- Latency；
- Evidence；
- Stop Reason；
- Deep Decision、Tool、Visited、Navigation 和 Dropped 指标。

Developer Trace 默认折叠，展开后按需读取：

```text
GET /api/ask/traces/{run_id}
```

它只展示有界 Action、Observation Summary、Usage、Guard、错误和静态 Policy
Version `v4-deep-policy-v1`。

Trace 当前只在进程内保存；进程重启后 404 不影响已经返回的 Answer/Citation。

### 7.3 轻量真实 Eval

初始 Eval 使用六条普通 Query：

- 两条直接事实/单主题；
- 一条上下文问题；
- 一条跨视频问题；
- 一条 Partial-support；
- 一条 No-evidence。

完成：

```yaml
fast_runs: 6
deep_runs: 4
manual_reviews: 10
dimensions:
  - supportedness
  - usefulness
  - coverage
  - status_honesty
```

结果逐 Case 保留，不计算生产 SLA 或误导性单一总分。

### 7.4 Demo

四段 Demo：

1. `/search` 直接搜索字幕 Evidence；
2. `/ask` Fast 生成 Grounded Answer；
3. `/ask` Deep 展示导航、字幕读取、Replanning 和共享 Answer；
4. Honest Failure 展示 `partial` / `insufficient`，不虚构。

---

## 8. Integration Review 中发现和修复的问题

### 8.1 Goal 2 Repair

首次 Goal 2 Review 发现：

- 210 秒 Final Answer Reserve 没有实际约束 Runtime；
- Deadline Timeout 与普通 Provider Network Error 分类不够准确；
- Finish/Stop 的有证据和无证据语义不够冻结。

修复后：

- Search 与 Answer 使用真实 Deadline；
- Initial Answer 与一次 Repair 共用 Answer Deadline；
- Deadline 耗尽映射为 `budget_exhausted`；
- 普通网络错误仍为 `provider_error`；
- Stop 有 Evidence 时可以使用已有证据返回 `partial`；
- 无 Evidence 时返回 `evidence_unavailable`。

### 8.2 Goal 3 Repair

真实 Eval 发现：

1. 有限 Retrieval/Context 被表述成整个收藏库不存在；
2. Eval Runner 的 `status_termination_valid` 曾硬编码为 `True`；
3. Navigation Citation 检查依赖通常为空的 Event 字段，可能空洞通过。

修复后：

- Initial Answer 和 Repair Prompt 同时明确“有限样本不能证明全库缺失”；
- 模型声明 `insufficient` 时，Finalizer 强制空 Answer/Citation；
- 使用范围诚实的无证据说明；
- Limitations 不能承载无 Citation 的材料性事实；
- Checker 真实验证 Schema、Response/Trace Termination、Answer Shape、
  Citation Resolution 和当前字幕重建；
- 新增能主动证明 Checker 会失败的负向测试。

经用户明确授权，只复跑：

```yaml
fast:
  - no_evidence_quantum_protocol
  - partial_universal_claim
  - single_topic_context_compression
deep:
  - no_evidence_quantum_protocol
```

没有重跑完整矩阵，没有重复采样。

### 8.3 一次人工 Eval 误判

Goal Session 曾只读取结果中前 500 字 `quote_excerpt`，将一条 Citation 误判为
不能支持“触发自动压缩造成性能下降”。

主 Session 使用：

- 当前 Source Version；
- 相同 Stable Citation ID；
- 完整 232.71–467.59 秒字幕；

重建后确认其中明确包含：

```text
一旦触发自动压缩，性能就直接下降
```

因此撤销误判，没有继续调 Prompt 或增加 Provider 调用。

该事件形成一个后续审阅规则：

> 有界 Quote Excerpt 不是完整 Citation。若支持内容可能位于截断范围之外，
> 必须按 Stable Citation 重建当前权威字幕后再判断 Supportedness。

---

## 9. 与最初目标有无出入

### 9.1 没有实质方向偏离

- Grounded RAG 已完成；
- Agentic Search 独立于 Candidate Builder；
- Fast/Deep 共用 Grounding；
- 原字幕/ASR 保持事实权威；
- `/ask` 和 `/search` 的产品分工保持；
- 使用薄 LangGraph，没有发展成 Agent Platform；
- Eval 保持轻量，没有回到 V3.5 治理模式；
- 三个纵向 Goal 没有被拆成多个基础设施 Goal。

### 9.2 发生的是有证据支持的实现收敛

- LangGraph 从候选变成了明确接受的最薄 StateGraph；
- Stable Citation Identity 在 Goal 1 中被进一步冻结；
- Deep 的 360/150/210 秒预算在真实延迟后得到明确约束；
- No-evidence Answer Boundary 在真实失败后得到收紧；
- Shared Evidence Renderer 在 Goal 3 中从现有 Search UI 薄提取。

这些改变强化了原目标，没有扩大 V4 产品边界。

---

## 10. 有意 Deferred 的能力

以下不是 V4 漏项：

- Token-by-token Answer Streaming；
- Native Tool Calling；
- Independent Navigation Index；
- Runtime Semantic Judge；
- Reranker；
- Automatic Context Compaction；
- Fast/Deep 自动路由；
- Trace 持久化；
- Server-side Cancellation；
- 通用 Observability Dashboard；
- LangGraph Checkpointer、Persistence、Memory、HITL、Subgraph、Multi-Agent；
- 通用 LLM SDK、Provider Platform、Eval Platform 或 Skill Registry；
- 生产 SLA；
- V5 个性化、主动行为和长期 Agent Runtime。

除非真实失败触发，否则不得把这些能力自动变成下一阶段任务。

---

## 11. 验证证据

最终记录：

```yaml
goal_3_extended_directed: 97_passed
default_full_suite: 1457_passed_4_deselected
existing_warning:
  - Starlette/httpx deprecation warning
compileall: passed
pip_check: passed
javascript_checks: passed
git_diff_check: passed
```

主 Session 第二次 Goal 3 Integration Review 另独立复跑：

```yaml
directed: 57_passed
default_full_suite: passed
repair_results: 4_verified
deterministic_checks: 10_of_10_true_per_result
original_eval_result_hash: unchanged
```

真实 Provider 验证包括：

- Goal 1 三条 Fast Vertical Slice；
- Goal 2 Navigation-first、Focused Transcript、Window/Replanning 和失败路径；
- Goal 3 6 Fast + 4 Deep；
- Goal 3 Repair 3 Fast + 1 Deep。

测试证明代码和边界可靠，但六条真实 Eval 不能证明生产质量泛化。

---

## 12. 当前主要风险

### 12.1 延迟

Goal 1 Fast Vertical Slice 实测约 37.6–112.1 秒。Goal 3 Fast 也出现约
20–90 秒运行。

“快速回答”表示相对 Deep 更简单，并不表示已经达到秒级交互。

当前：

- 无 Token Streaming；
- 无服务器端取消；
- 浏览器 Abort 只防止旧 Response 覆盖；
- Provider 调用可能在用户离开页面后继续运行。

### 12.2 Deep Token 与成本

一个 Goal 2 Window/Replanning Case 的四次 Agent Decision 使用约 58,396
Tokens。

Deep 有明确上界，但仍可能昂贵，因此应继续由用户显式选择。

### 12.3 Fast Context Truncation

Goal 3 六条真实 Fast 运行均发生 Context Truncation。

当前没有重复证据证明关键 Evidence 稳定落在预算之外，因此没有触发 Reranker
或 Automatic Context Compaction。但这是重要观察信号。

### 12.4 保守拒答

Repair 后的全称问题安全地返回 `insufficient`，但未充分利用已有反例生成更有用
的有限范围回答。

当前优先级是：

```text
范围诚实
>
无证据的高覆盖率
```

### 12.5 Provider 可靠性

真实运行观察到：

- Agent Action Schema 漂移；
- Answer 达到长度上限；
- Provider Error。

Runtime 会 Fail-closed，但外部模型格式遵循和网络状态仍影响可用性。

### 12.6 语义 Citation 质量

Runtime 可以确定性证明：

- Citation ID；
- Source Identity；
- Source Version；
- Segment；
- Quote；
- 时间跳转。

Runtime 不判断 Answer 与 Citation 的自然语言语义是否完全一致。该质量由轻量
离线人工 Eval 观察，V4 不引入 Runtime Semantic Judge。

### 12.7 Navigation Recall

现有 Navigation Projection 在当前 Vertical Slice 和轻量 Eval 中没有出现材料性
Recall 失败。

这不足以证明大规模 Recall 已解决，但也不足以支持现在建立独立 Navigation
Index。

### 12.8 Eval 覆盖

六条 Query 适合发现工程问题，不支持：

- 准确率 SLA；
- 延迟 SLA；
- 成本 SLA；
- Fast/Deep 模式胜率；
- 对不同收藏规模的质量泛化。

### 12.9 隐私

真实问答会把用户 Query 和有界字幕 Evidence Context 发送给当前配置的 DeepSeek
Provider。

如果未来从本地个人项目走向多用户或外部产品，该边界必须成为明确的产品与部署
决策。

### 12.10 发布状态

V4 已提交并推送：

```yaml
branch: codex/v4-main
commit: cbf264be2571c3d62775c064445de8a1ba17880a
remote: origin/codex/v4-main
```

如果默认分支承担正式发布角色，PR、Merge、Tag 和 Release 仍需单独决定。

---

## 13. 项目层面的主要判断

### 13.1 V4 最有价值的不是 LangGraph

最有长期价值的是 Fast/Deep 共享 Grounding 底座：

- 同一个 `TranscriptEvidenceSpan`；
- 同一个 `AnswerFinalizer`；
- 同一个 Answer Block；
- 同一个 Citation Validator；
- 同一个 AskResponse；
- 同一个 Evidence UI。

Fast/Deep 的差异被限制在 Retrieval/Orchestration 层，没有形成两套产品后端。

### 13.2 Citation Identity 是重要技术资产

Citation 与 Retrieval Strategy 解耦后：

- Retrieval 可以演化；
- UI 可以扩窗；
- 排名可以改变；
- Citation 仍保持稳定；
- 只有权威字幕变化才会使它正确失效。

这是 V4 可以继续演化而不破坏证据可追溯性的基础。

### 13.3 轻量真实 Eval 的方式有效

Goal 3 Eval 发现了单元测试难以发现的：

- 全库否定范围错误；
- Checker 空洞通过；
- Excerpt 截断导致人工误判。

因此后续应保留：

```text
小型真实 Eval
→ 保留成功与失败
→ 只对重复材料性失败做有界修正
```

但不应重新引入 V3.5 式大型治理体系。

### 13.4 主 Session / Goal Session 分工有效

Goal Session 负责纵向实现；主 Session 负责：

- 对照正式边界；
- 独立复跑；
- 检查报告自评；
- 判断失败是否阻塞；
- 更新最终状态与决策。

Goal 2 和 Goal 3 都由主 Session 发现过 Goal Session 未正确判断的问题，说明
Integration Review 具有真实价值。

---

## 14. 后续规划建议

不建议立即把 Deferred 能力全部变成 V5 Backlog。

下一阶段应先选择一个明确产品命题。

### 方向 A：质量、延迟和可靠性硬化

适用于目标：

> 让 V4 成为可以高频日常使用的工具。

优先观察：

- Fast / Deep P50、P90 Latency；
- Provider Error 和结构化失败率；
- Context Truncation 是否导致关键证据丢失；
- 用户从 Fast 继续 Deep 的频率；
- `partial / insufficient` 分布；
- Deep Round、Tool 和 Token 成本；
- 用户是否因等待而放弃。

只在真实信号出现后考虑：

- Streaming / Progress；
- Server-side Cancellation；
- Reranker；
- Context Compaction；
- Native Tool Calling；
- Adaptive Router。

### 方向 B：V5 个人视频知识产品

适用于目标：

> 从收藏问答升级为个人视频知识工作空间。

可能涉及：

- User Notes 与权威字幕 Evidence 协同；
- 跨会话研究；
- 视频和主题之间的关系；
- 个性化关注点；
- 主动发现、回顾或提醒；
- 更长期的 Workspace State。

该方向会改变产品边界，不能作为 V4 的普通维护继续推进。

### 推荐节奏

```text
冻结 V4 完成基线
→ 一段真实日常使用
→ 收集少量普通失败与体验信号
→ 判断主要瓶颈是质量/延迟，还是产品价值扩展
→ 再决定 V5 主题
```

V5 应围绕一个清晰的产品假设展开，而不是清空 V4 Deferred 列表。

---

## 15. 建议主 WebGPT 重点讨论的问题

1. 拾流下一阶段的核心目标是“提高当前问答可用性”，还是“扩展个人知识产品
   价值”？
2. 当前数十秒级 Fast 延迟对真实使用是否已经构成首要阻塞？
3. 用户愿意为 Deep 的更广搜索承担多少等待和 Token 成本？
4. Fast Context Truncation 是否在真实使用中反复造成关键事实遗漏？
5. User Notes 在未来应该继续作为导航材料，还是进入一种与字幕事实明确区分的
   用户自有证据体系？
6. V4 是否需要先进入默认分支、Tag 或可发布构建，再启动下一版本？

这些问题需要产品判断或真实使用信号，不能仅靠继续读取源码解决。

---

## 16. 权威文件索引

建议需要时按以下顺序查阅：

1. `SHILIU_V4_WEBGPT_PROJECT_HANDOFF.md`
   - 本文；面向规划讨论的总体复盘。
2. `V4_MASTER_STATE.md`
   - 当前状态、完成边界、风险与 Deferred 权威。
3. `V4_DECISION_LEDGER.md`
   - 关键产品和架构决策、理由与未采用方案。
4. `V4_DESIGN_PROPOSAL.md`
   - 完整产品与技术架构。
5. `V4_G1_IMPLEMENTATION_REPORT.md`
   - Fast Grounded RAG 实现和验证。
6. `V4_G2_IMPLEMENTATION_REPORT.md`
   - Independent Agentic Search、LangGraph 和预算实现。
7. `V4_G3_IMPLEMENTATION_REPORT.md`
   - `/ask`、UI、Trace、真实 Eval、Demo 和 Integration Repair。

`eval/v4_goal3_results.json` 与 `eval/v4_goal3_repair_results.json` 是真实运行证据，
但不建议在首次规划讨论时优先加载；只有需要逐 Case 检查质量、延迟、Token 或
人工审阅时再提供。
