# Shiliu V4.1 Continuation Execution Prompt

你当前从：

```text
Shiliu V4.1 H0 Investigation Session
```

转为同一分支上的：

```text
Shiliu V4.1 Bounded Continuation Execution Session
```

本 Session 连续负责：

```text
H0 Closeout Correction
→ H1 Fast Answer Hardening
→ H2 Deep Decision Context Hardening
→ H3 Paired Validation、Integration 与 V4.1 Closeout
```

用户授权在明确包络和停止条件内连续工作，正常阶段转换不需要返回 Main Session
逐项审批。任何停止条件触发时，必须立即停止相关 Provider 调用和正式实现，保留
可恢复状态并向用户报告。

---

# 1. 权威输入

开始前完整复核：

```text
V4_1_H0_INVESTIGATION_REPORT.md
V4_1_H0_INVESTIGATION_PROMPT.md
V4_MASTER_STATE.md
V4_DESIGN_PROPOSAL.md
V4_DECISION_LEDGER.md
V4_G1_IMPLEMENTATION_REPORT.md
V4_G2_IMPLEMENTATION_REPORT.md
V4_G3_IMPLEMENTATION_REPORT.md
```

外部规划输入仍为：

```text
/Users/elliot/Downloads/SHILIU_V4_1_RUNTIME_AND_CONTEXT_HARDENING_PLAN.md
```

该规划不是不可修改的实施 Spec。H0 新证据优先于其中未验证的候选判断。

冻结基线：

```yaml
v4_branch: codex/v4-main
v4_commit: cbf264be2571c3d62775c064445de8a1ba17880a
v4_1_branch: codex/v4.1-hardening
```

必须保留当前工作区全部用户和 Main Session 文件，不得 Reset、Clean、Stash、
Rebase 或覆盖无关文件。

---

# 2. 已冻结的 H0 决策

## 2.1 Provider

H0 新 Fixed Replay：

```yaml
logical_trials: 24
logical_provider_invocations: 26
transport_http_attempts: 26
matrix_complete: true
```

冻结结论：

```yaml
formal_grounded_answer_configuration: baseline
adopt_thinking_off: false
reduced_reasoning: unavailable
new_provider_selection: forbidden
```

Thinking Off 配置组合的延迟显著更低，但伴随材料性错误拒答和 Unknown Citation
Repair。不得把低延迟单独视为可采用结果，也不得声称差异只由 Thinking 引起。

## 2.2 H1 证据

H0 已证明：

- 当前 Baseline 在 Single-topic 上总体可用；
- No-direct-support Case 的范围诚实行为正确；
- Universal/Partial-support 六次均错误返回 `insufficient`；
- Baseline Cross-video 存在覆盖不足、错误拒答和一次
  `output_budget_exhausted`；
- 当前问题集中在 Grounded Answer 的全称命题/反例语义、跨视频综合和输出纪律，
  不足以触发 Retrieval、Reranker 或 Context Selection 改写。

## 2.3 H2 证据

H0 已证明 Deep Decision Payload 的主要增长源为：

1. Evidence Metadata 中完整 `segment_ids`；
2. 重复 Navigation Projection；
3. 最近 60 个 Visited Segment IDs；
4. 有界 Evidence Quote。

H2 采用 Deterministic DecisionView，保留完整 Runtime State 和全部确定性 Guard。

## 2.4 Context Selection

```yaml
reranker: deferred
diversity_selector: deferred
automatic_context_compaction: forbidden
context_budget_change: not_authorized
```

六例发生 Truncation 本身不构成 Selection 改写依据。

---

# 3. H0 报告关闭修正

在任何新 Provider 调用或正式 Runtime 修改前，修正
`V4_1_H0_INVESTIGATION_REPORT.md` 的内部不一致：

- 将“Thinking Off 配置组合在本次小样本中延迟更低”记录为已观察关联；
- 同时明确该组合因质量退化被拒绝，且不能隔离 Thinking 单变量因果；
- 将 Universal/Partial-support 的重复错误拒答列为 H1 已证明问题；
- 将 Cross-video 综合不稳定列为 H1 有界调查/修正范围；
- No-evidence Short Path 继续 Deferred；
- 删除事故段落中的重复句；
- 不改写第一次失败 Campaign 的未知调用消耗；
- 不修改 H0 原始测量、评分或 Hash。

---

# 4. 连续执行的阶段顺序

严格按以下顺序：

```text
Phase 0：H0 Report Correction + E2E Harness Hardening
Phase 1：Current Fast Baseline E2E
Phase 2：H1 Fast Answer Hardening
Phase 3：Post-H1 Fast E2E
Phase 4：Current Deep Baseline E2E
Phase 5：H2 Deterministic DecisionView
Phase 6：Post-H2 Deep E2E
Phase 7：H3 Integration、State/Ledger、Closeout
```

不得在对应 Before Snapshot 完成前修改该路径的正式 Runtime。

---

# 5. Phase 0 — E2E Harness Hardening

现有 H0 `run_end_to_end()` 只在进程结束时返回聚合行，没有事故后的 WAL、
Crash Recovery 或完整质量复核，因此不得直接用于授权 E2E。

先在无 Provider 调用条件下补齐：

- 每个 E2E Run 前的 `in_flight` WAL；
- 每个 Run 后的有界原子 Checkpoint；
- Phase/Query/Mode/Code-state Identity；
- 已完成 Run 不重复调用；
- 不确定 `in_flight` 一律 Block；
- 逐 Run 完整 Citation 当前版本复验；
- Supportedness、Usefulness、Coverage、Status Honesty 质量复核；
- 只持久化指标、评分、有界理由和 Hash；
- 不持久化 Query 正文以外的私人 Prompt、Answer 正文、Transcript、
  Navigation 正文、API Key 或 Raw Provider Response；
- Checkpoint 必须位于已 Git Ignore 的 `.h0/`；
- Checkpoint 文件权限 `0600`；
- Provider 返回后、质量复核前和复核中崩溃测试；
- Campaign Identity 不匹配时拒绝混用。

可以复用 H0 Checkpoint 的薄 Helper，但不得建设通用 Experiment、Eval 或
Observability Platform。

完成定向测试和默认全套测试后，才可进入已授权 E2E。

---

# 6. 已授权的 Provider 包络

本 Prompt 对下列四个 Paired E2E Phase 提供一次性、有上限的授权。

## 6.1 Fast Before

```yaml
mode: fast
code_state: before_H1
queries:
  - no_evidence_quantum_protocol
  - single_topic_context_compression
  - cross_video_context_management
  - partial_universal_claim
configuration: baseline_only
runs: 4
max_query_analysis_logical_calls: 4
max_answer_initial_logical_calls: 4
max_answer_repair_logical_calls: 4
max_logical_provider_invocations: 12
max_transport_http_attempts: 24
```

## 6.2 Fast After

```yaml
mode: fast
code_state: after_H1
queries: same_as_fast_before
configuration: baseline_only
runs: 4
max_query_analysis_logical_calls: 4
max_answer_initial_logical_calls: 4
max_answer_repair_logical_calls: 4
max_logical_provider_invocations: 12
max_transport_http_attempts: 24
```

## 6.3 Deep Before

在 H1 已冻结、H2 尚未修改前执行：

```yaml
mode: deep
code_state: before_H2
queries:
  - contextual_tool_failure
  - cross_video_context_management
runs: 2
max_agent_decision_rounds_per_run: 6
max_answer_initial_calls_per_run: 1
max_answer_repair_calls_per_run: 1
max_logical_provider_invocations: 16
max_transport_http_attempts: 32
```

## 6.4 Deep After

```yaml
mode: deep
code_state: after_H2
queries: same_as_deep_before
runs: 2
max_agent_decision_rounds_per_run: 6
max_answer_initial_calls_per_run: 1
max_answer_repair_calls_per_run: 1
max_logical_provider_invocations: 16
max_transport_http_attempts: 32
```

## 6.5 总授权

```yaml
total_product_e2e_runs_max: 12
total_logical_provider_invocations_max: 56
total_transport_http_attempts_max: 112
automatic_resampling: false
thinking_off_calls: 0
new_fixed_replay_calls: 0
```

该总授权不包含 H0 已执行或失败 Campaign 的历史消耗。

真实调用会向当前配置的 DeepSeek Provider 发送普通 Query、当前有界
Navigation/Transcript Context、Prompt 和 JSON Schema。不得发送 User Notes 或
Cleaned Transcript 作为 Citation 事实输入。

每个 Phase 连续两次 Provider Failure、任何未知 `in_flight`、Checkpoint
Identity 冲突或调用上限不足时，立即停止，不得补跑或扩容。

未经新授权不得：

- 增加 Query；
- 增加 Trial；
- 重采样；
- 执行额外 Fixed Replay；
- 调用 Thinking Off；
- 改用其他 Provider；
- 超过上述任一 Phase 或总上限。

---

# 7. H1 — Fast Answer Hardening

## 7.1 必须实现

只在共享 Grounded Answer 层做有界修正：

1. 区分：
   - 用有限样本证明全库/全称命题；
   - 用一个有权威字幕支持的直接反例否定全称命题。
2. 对直接反例允许生成：
   - 有引用的有限结论；
   - `partial` 状态；
   - 明确不能外推为完整全库审计的 Limitation。
3. 改善跨视频综合指令：
   - 只综合当前 Transcript Evidence；
   - 不因不能覆盖全库而拒绝回答可支持的有限比较；
   - 不强制把不足证据写成完整结论。
4. 强化输出纪律：
   - Answer Block 必须材料性、去重、简洁；
   - 避免无意义长 Completion；
   - 保持现有 Pydantic Schema、Citation Allowlist 和 Validation。

## 7.2 可修改范围

- Grounded Answer Prompt/Message 构造；
- 与上述语义直接相关的确定性 Validation；
- Fast Trace 中已有指标的薄补充；
- 必要单元、集成、回归测试。

## 7.3 禁止

- 修改正式 Provider 配置；
- 增加或切换模型；
- 修改 Retrieval、Rewrite、Evidence、Context Selection；
- 修改 Shared Ask Contract；
- 引入 Runtime Semantic Judge；
- 增加 Sufficiency Pipeline；
- 增加 Reranker 或 Context Compaction；
- 增加自动 Router；
- 修改 `max_tokens`，除非停止并获得 Main Session 新授权。

## 7.4 H1 验收

Fast After 必须满足：

- No-direct-support 继续诚实 `insufficient`；
- Single-topic Supportedness 不退化；
- Universal/Partial-support 产生有 Citation 的有限反例/限制回答；
- 不声称完成全库审计；
- Cross-video 至少返回诚实且有用的有限综合，或有材料性 Limitation；
- Citation、Identity、Source Version、Finalizer 不回归；
- Schema First-pass/Repair 不恶化；
- Provider 配置仍为 Baseline。

若一次 Fast After 暴露材料性回归：

- 不得额外 Provider 重跑；
- 允许基于已有证据进行本地修正和确定性测试；
- 没有剩余已授权同 Query Run 可验证时，停止并报告，不得自增调用。

---

# 8. H2 — Deep Decision Context Hardening

## 8.1 实现形态

实现框架无关的：

```text
DeepRuntimeState
→ Deterministic DecisionViewProjector
→ existing AgentAction Provider
```

LangGraph Node 只消费投影结果，不持有 Domain 逻辑。

## 8.2 第一版投影

必须保留：

- Original Query；
- 当前优先 Open Question；
- 有界 Open/Resolved Questions；
- Latest Action/Observation；
- Evidence Inventory；
- 合法 Window Anchors；
- Previous Query/Visited 摘要；
- 精确剩余 Budget；
- 固定 Action Schema/Policy。

优先移除：

1. 每个 Evidence 的完整 `segment_ids`；
2. 重复长 Navigation Summary Sections；
3. 最近 60 个逐项 Visited Segment IDs。

完整 Runtime State、Evidence Spans、Visited Sets、Events 和 Guard 输入不得删除。

## 8.3 禁止

- LLM Rolling Summary；
- Memory、Persistence、Checkpointer、HITL；
- Multi-Agent/Subgraph；
- Native Tool Calling；
- 修改 LangGraph 拓扑；
- 修改 Tool 或 Budget；
- 修改 Shared Answer/Finalizer；
- 修改 Citation Identity；
- 把 Navigation 内容作为 Fact Context；
- 为 DecisionView 建设通用 Context Platform。

## 8.4 H2 验收

必须证明：

- Navigation → Transcript → Window → Replan → Finish 仍成立；
- Observation 后 Action 仍可改变；
- Window Anchor 始终来自完整 Runtime 的合法 Segment；
- Repeated Query/Segment、No-new Evidence、Round/Tool/Deadline Guard 不变；
- Stable Citation 与 Source Version Revalidation 不变；
- Scripted 高成本轮 Decision Payload 有材料性下降；
- 约 40% Token/字符下降是方向目标，不得以质量换数字；
- Deep After 的 Replanning、Evidence Coverage、回答质量不低于 Deep Before。

若 Deep After 出现 Replanning、Evidence Coverage、Citation 或 Answer 质量回归：

- 不得额外 Provider 重跑；
- 回退到更保守的投影；
- 只做确定性验证；
- 若无法在现有证据下确认修复，停止并报告。

---

# 9. H3 — Integration and Closeout

在 H1/H2 均满足或被诚实回退后：

1. 运行 H0/H1/H2 定向测试；
2. 运行默认完整测试套件；
3. 运行 Compileall、Pip Check、Diff Check；
4. 核验 `/ask`、`/search`、Fast/Deep、Evidence Card 和 B 站跳转不回归；
5. 对照 Before/After：
   - Fast Provider/总延迟、Schema、Repair、质量四维；
   - Deep 每轮 Prompt Tokens、Decision Rounds、Tool Calls、Replanning、质量四维；
6. 更新：
   - `V4_MASTER_STATE.md`；
   - `V4_DECISION_LEDGER.md`；
7. 创建一份：
   - `V4_1_IMPLEMENTATION_AND_CLOSEOUT_REPORT.md`。

不要创建独立 H1/H2 Prompt、Gate、Readiness、Eval Platform 或多 Reviewer 文件。

最终状态只能是：

```yaml
v4_1_status: complete | partial | blocked
```

`complete` 只在：

- H1/H2 接受的正式改动均有测试和 Paired Evidence；
- 无 Citation/Evidence/Contract 回归；
- 所有 Provider 调用在授权内；
- 状态与决策文件已更新；
- 没有未披露事故或恢复状态；

时使用。

若 H1 或 H2 因质量回归被回退，但其余硬化完成，可使用 `partial`，不得伪装为
Complete。

---

# 10. Git

允许在 `codex/v4.1-hardening` 上创建有界本地 Phase Commit，以防长 Session
丢失工作，但必须：

- 只 Stage 明确属于 V4.1 的文件；
- 不 Stage `.h0/`；
- 不 Stage `SHILIU_V4_WEBGPT_PROJECT_HANDOFF.md`；
- 不修改 V0–V4 冻结报告；
- 每次 Commit 前测试通过；
- 不 Rebase、Reset、Clean 或 Force；
- 不 Push、Merge 或创建 PR。

最终由 Main Session 审查并决定 Push。

---

# 11. 强制停止条件

触发任一项立即停止并返回用户：

- 需要采用 Thinking Off、Reduced Reasoning 或新 Provider；
- 需要修改 `max_tokens`；
- 需要修改 Retrieval、Context Selection、Ask Contract、Citation Identity、
  Source Authority、Tool、Budget、Graph 拓扑或产品入口；
- 需要引入 Reranker、Runtime Judge、LLM Summary、Memory、Persistence、
  Multi-Agent、Streaming 或新平台；
- Provider Phase 出现连续两次失败；
- 任一 Checkpoint 存在未知 `in_flight`；
- 发现重复 Provider 调用或调用上限可能超出；
- 私人 Prompt、答案、字幕、密钥或 Raw Response 被持久化；
- Paired Corpus Identity 或关键 Source Version 发生变化；
- H1 造成 No-evidence/Supportedness/Citation 回归；
- H2 造成 Replanning/Evidence/Citation/Answer 回归；
- 无法用确定性测试和剩余授权 Run 验证修正；
- 默认完整测试出现无法归因的新失败；
- 用户文件冲突；
- 需要新增依赖；
- 需要扩大到 V5。

普通源码实现、测试修正、文档同步和有界本地 Commit 不需要停下。

---

# 12. 最终返回

正常情况下，不在 H1/H2 阶段之间请求 Main Session 审批。全部完成后一次性返回：

1. V4.1 最终状态；
2. H1 实现与 Fast Before/After；
3. H2 实现与 Deep Before/After；
4. Provider 实际调用与 HTTP Attempt；
5. 所有停止/恢复事件；
6. 测试和产品验证；
7. 正式文件清单；
8. Local Commit；
9. 是否建议 Main Session 接受并 Push；
10. `V4_1_IMPLEMENTATION_AND_CLOSEOUT_REPORT.md` 路径。

如果触发停止条件，只返回已完成的有界事实、Checkpoint 状态、剩余授权和明确
阻塞原因；不得继续尝试。
