# Shiliu V4 / V4.1 Final Archive and Closeout

```yaml
document_role: final_archive_closeout
date: 2026-07-30
branch: codex/v4.1-hardening
v4: complete
v4_1: partial_closed
v4_1_implementation_complete: true
v4_1_runtime_changes_accepted: true
closeout_state: closed_with_known_evidence_gap
implementation_blocker: none
remaining_blocking_finding: none
next_version_allowed: true
unproven_online_quality:
  - fast_cross_video_after
```

`partial_closed` 的唯一含义是：Fast Cross-video After 因一次独立 Provider
Failure 返回 `insufficient/provider_error`，没有形成可评价的成功 Answer。
Fail-closed 行为正确；该结果既不能证明 H1 回归，也不能证明 H1 Cross-video
在线质量已经通过。本轮不追加重采样。

## 1. Final Product Baseline

V4 / V4.1 封存以下可运行产品基线：

- `/search`：直接搜索字幕证据，用于手动查证、Debug 和 Demo 对比；
- `/ask` Fast：Query Analysis、Bounded Rewrite、单次 Retrieval 物化、
  Transcript-only Context 和 Grounded Answer；
- `/ask` Deep：从用户 Query 独立执行 Navigation、Focused Transcript Search、
  Window Read、Replanning、Evidence Accumulation 和确定性停止；
- 当前 Source Version 可验证的原字幕/ASR 是最终事实权威；标题、简介、AI
  总结、User Notes 和整理稿只用于导航；
- Fast/Deep 共享 Answer Block、Stable Citation、Source Version/Segment
  Validation、Finalizer、Evidence Card 和 Bilibili 时间点跳转；
- 用户 Trace 默认可见，开发者 Trace 有界且默认折叠；
- Evidence 不足或 Provider 失败时诚实返回 `partial` / `insufficient` 和类型化
  `termination_reason`，不虚构答案。

V4 Goal 1、Goal 2、Goal 3 均为 `complete`，剩余 V4 Blocking Finding 为零。

## 2. V4.1 Accepted Changes

### H1 — Shared Grounded Answer Boundary

- 有限 Retrieval/Transcript Context 不能被表述为完整全库或全称证明；
- 当前权威字幕中的直接反例可以形成带 Citation、有限范围且明确非全库审计的
  `partial` 回答；
- Cross-video 只综合当前 Transcript Evidence 支持的材料；
- Answer Block 必须材料性、简洁且不重复；规范化后完全重复 Block 进入现有
  一次 Repair；
- H1 Runtime、确定性测试及 No-evidence、Single-topic、
  Universal/Partial-support 三类成功 Paired Evidence 被接受。

### H2 — Deterministic Deep DecisionView

正式路径为：

```text
DeepRuntimeState
→ Deterministic DecisionViewProjector
→ existing AgentAction Provider
```

完整 Runtime State、Evidence、Visited Set、Events 和确定性 Guard 保留。模型
投影移除完整 Evidence `segment_ids`、重复长 Navigation 内容和逐项 Visited
Segment，同时保留 Evidence Inventory、合法 Window Anchor、工作清单、最近
Observation 和精确剩余预算。LangGraph 拓扑、Tool、Budget、Citation 和
Finalizer 不变。

两条 Paired Deep Case 的累计 Prompt Tokens 分别下降 55.7% 和 57.9%，合计从
65,754 降至 28,365（下降 56.9%）；总延迟从 142.290 秒降至 113.641 秒
（下降约 20.1%）。Replanning、Evidence Coverage、Citation 和四维人工质量
保持或改善。

### Provider and Selection Decisions

```yaml
thinking_off:
  investigated: true
  adopted: false
fast_latency_improvement:
  status: not_proven
reranker_triggered: false
diversity_selector_triggered: false
automatic_context_compaction_triggered: false
```

H0 对照同时改变 Thinking、Reasoning Effort 和 Temperature，不能解释为
Thinking 单变量因果。Thinking Off 组合中位延迟显著降低，但同时出现材料性
错误拒答和 Unknown Citation Repair，因此正式 Provider 配置保持 Baseline。

六条 Fast Context Diagnostic 均发生截断，但 Multi-query 重复 Citation 已在
Fusion 阶段去重，Cross-video 和 Universal Case 仍保留多个视频；没有重复的
材料性证据证明关键 Evidence 稳定落在 Context 外，因此不触发 Selection 或
Compaction 改动。

## 3. Known Evidence Gaps

当前只保留以下证据边界：

1. Fast Cross-video After 缺少成功在线样本；
2. V4.1 没有证明 Fast 整体延迟改善；
3. Deep Token 与延迟改善只由两条 Paired Case 证明，尚未证明对所有 Deep
   Query 具有相同比例的泛化收益；
4. Provider 服务端、Cache、配置组合、Completion 长度和 Reasoning Token
   波动尚未被当前小样本完全归因。

这些是已披露的证据限制，不是 V4/V4.1 Implementation Blocker，也不阻止进入
新的版本规划。

## 4. Explicitly Closed Items

以下事项不再属于 V4 / V4.1 待办，也不自动获得后续授权：

- 为改变 `partial` 状态重跑 Fast Cross-video；
- 继续 Thinking / Reasoning / Temperature 校准；
- Reranker、Diversity Selector 或 Automatic Context Compaction；
- Runtime Semantic Judge；
- Native Tool Calling；
- Token Streaming 或 Server-side Cancellation；
- Memory、Persistence、HITL、Subgraph 或 Multi-Agent；
- 扩大 Eval、建立 Eval/Trace/Provider 平台；
- 继续建设或复用本次一次性 Crash-safe Harness；
- 从 Deferred 清单自动生成下一版本 Backlog。

## 5. Version Transition

```text
V4 / V4.1 正式结束
→ 下一步进入新的版本规划
→ 后续版本必须围绕新的产品命题
→ 不从 Deferred 清单自动生成 Backlog
```

V4.1 的 `partial_closed` 可以作为版本化代码与文档基线；它不表示所有在线质量
均已穷尽证明。Merge、Tag 和 Release 仍由用户单独决定，本封存不自动执行。

## 6. Authority Index

1. `V4_MASTER_STATE.md`
2. `V4_DECISION_LEDGER.md`
3. `V4_1_H0_INVESTIGATION_REPORT.md`
4. `V4_1_IMPLEMENTATION_AND_CLOSEOUT_REPORT.md`
5. `V4_V4_1_FINAL_ARCHIVE_CLOSEOUT.md`
6. `SHILIU_V4_WEBGPT_PROJECT_HANDOFF.md`

Goal 1/2/3 Implementation Report 和执行 Prompt 保留为下钻证据，不需要在首次
后续版本讨论中优先加载。
