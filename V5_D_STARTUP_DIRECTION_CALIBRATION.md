# Shiliu V5-D Startup Direction — Pre-planning Roadmap Calibration

> Date: 2026-08-10
> Authority: Shiliu V5 Main Codex Session
> Document role: bounded pre-planning roadmap calibration
> Status: accepted
> Accepted by: user
> Accepted at: 2026-08-10
> V5-D Version Session created: false
> Product implementation started: false
> Candidate Skill implementation authorized: false
> Provider runs authorized: false

---

# 1. Final Calibration Decision

```yaml
core_route: retained
material_roadmap_change: false

entry_readiness:
  mechanical_foundation_ready: true
  empirical_entry_gate_met: false
  bounded_entry_calibration_required: true
  candidate_skill_implementation_ready: false

initial_scope:
  domain_specific_search_and_research_policy: true
  generic_agent_learning_platform: false
```

V5-A、V5-B、V5-C 的实际落地没有出现足以推翻 V5-D 核心路线的新事实。原来的：

```text
Trace
→ Attribution
→ Hypothesis
→ Candidate
→ Paired Replay
→ Generalization
→ Negative Transfer
→ Human Promotion
→ Gated Use
→ Rollback
```

应完整保留。

真正需要调整的是进入顺序和当前 Candidate Surface，而不是重构 V5-D。

## 1.1 User-accepted calibration constraints

以下三条在用户接受后成为 V5-D Charter、Stage Contract 和 Eval 的强制边界：

1. Stage 0 的代表性任务必须先按候选无关的产品覆盖规则完成选择与冻结，之后才允许冻结具体
   Failure Family 或 Candidate Hypothesis。不得反向挑选容易证明某个预设 Search Skill 的任务。
2. Held-out Related Tasks 必须保持真正 held-out。任何参与 Candidate 设计，或参与 Trigger、
   Procedure、Stop Rule 及其他调参的 Case，立即失去该 Candidate 的 held-out 资格。
3. Environment Shift 不属于 Portfolio-ready 的硬性要求。Related-task Generalization、Unrelated
   Regression 和 Negative Transfer 是核心要求；Environment Shift 只在 Candidate 的适用性合同
   确实依赖环境变化时进入后续验证，或作为 Version Complete 的条件性证据。

---

# 2. Original V5-D Design Retained

以下内容全部保留：

- `Controlled Experience-driven Search Policy Improvement` 定位；
- Trace、Experience、Attribution、Hypothesis、Candidate、Active Skill 分离；
- 找到 first actionable failure step，而不是泛化 Reflection；
- 假设必须可证伪；
- Candidate 不能修改 Dataset、Judge、Promotion Gate 或 Verifier；
- Baseline/Treatment 配对；
- Related-task generalization；
- Unrelated regression 和 Negative Transfer；
- Experiment Identity 和 Scaffold Fingerprint；
- Human promotion；
- Progressive Disclosure；
- Deprecation 和 Rollback；
- Provider、预算和 invalid-run 独立记账；
- 不使用训练、RL、自动改源码或无人工批准的 Skill 发布。

这些仍然是 V5-D 的技术价值核心。

---

# 3. Candidate Adjustment Decisions

| 候选调整 | 判断 | 结论 |
| --- | --- | --- |
| 薄 Entry Calibration | **accept with modification** | 必须增加，但作为 V5-D 的第一个有界 Entry Stage，不建立 Candidate Skill |
| 限定 Candidate Surface | **modify** | 当前只允许 domain-specific Search/Research Policy；原长期候选不删除，但部分 deferred |
| 不引入通用 Harness 自改进 | **accept** | 拾流保留自己的 domain replay/eval，但不建设 generic Agent Learning Platform |
| Portfolio-first、一个强 Candidate | **accept with modification** | 一个完整 Candidate 闭环足够，不要求人为凑第二类；但必须完成完整 promote/use/rollback |
| Progressive Disclosure 后置 | **accept** | 先证明 Candidate 有效，再建设最小 applicability gate；无 validated Skill 就不建 Skill Platform |
| 重新分类 V5-A limitation | **accept；case deferred** | 目前不能直接算 V5-D Search Policy Case，必须先区分 policy 与 retrieval/infrastructure |

没有必要删除长期路线，也没有必要降低 Attribution、Generalization、Negative Transfer 或 Rollback 的质量要求。

---

# 4. Current V5-D Entry Readiness

现场数据表明，基础设施已经准备好，但经验数据尚不足以启动 Candidate Skill。

## 4.1 Available foundations

- 157 个 videos，140 completed；
- 154 个视频进入当前 lexical/dense index；
- lexical 为 154 video units、1479 chunks；
- dense 为 1633 units/vectors，状态 current；
- V5-A 已有 durable Task/Attempt/Checkpoint/Trace/Outer Audit/HITL 机制；
- V5-B 已有 `system_experience` candidate lineage；
- V5-C 已有 Feedback、Workspace 和 confirmed/candidate authority；
- 当前 Runtime 没有 Active Skill，可作为逻辑上的 No-Skill baseline；
- 现有测试已证明 Trace/Experience 不会自动修改 Skill 或 Runtime。

## 4.2 Missing empirical entry evidence

```yaml
live_research_tasks: 0
live_research_attempts: 0
live_research_traces: 0
live_research_inner_actions: 0
live_research_outer_audits: 0
live_workspace_records: 0
live_experience_candidates: 0
live_feedback_population: 0
qualified_repeated_failure_family: false
formal_related_unrelated_split: false
negative_transfer_stream: false
```

live DB 中存在：

```yaml
retrieval_search_traces: 145
distinct_queries: 30
successful_traces: 143
zero_hit_traces: 49
repeated_zero_hit_query_groups: 6
```

但这些 trace 形成于 2026-07-19 至 2026-07-27，属于 retrieval-level 历史记录：

- 没有绑定当前 durable Research Task/Attempt；
- 没有用户结果判定；
- 没有 Goal Audit 或最终 answer quality；
- 没有 Failure Attribution；
- 没有冻结为 Related/Unrelated case；
- 零命中可能是问题不在语料中，并不自动等于 Search Policy Failure。

它们可以作为 Entry Calibration 的任务选择线索，不能直接升级为重复 Failure Family。

因此当前准确状态是：

```yaml
V5_D_entry_gate: not_met
V5_D_calibration_readiness: ready
V5_D_candidate_implementation: not_authorized
```

---

# 5. Bounded Entry Calibration

建议把 Entry Calibration 设置为 V5-D Version Session 启动后的第一个 Stage，但只授权 baseline calibration，不授权 Candidate 实现。

推荐边界：

```text
真实收藏语料
+ 当前健康 lexical/dense index
+ 当前 Durable Research Runtime
+ 代表性真实研究任务
+ No-Skill Baseline
→ replayable traces
→ failure classification
→ repeated failure-family qualification
```

默认可以选择约 4–6 个代表性任务，但具体数量应在 Stage Contract 中根据成本冻结，不作为路线硬编码。

任务应包含：

- 复合研究任务；
- 需要反例的任务；
- 需要来源多样性的任务；
- 简单任务作为非退化对照；
- 至少两个不同任务可能暴露同一 failure family。

每次运行必须冻结：

- corpus/source snapshot；
- lexical/dense index version；
- model/provider configuration；
- Prompt/DecisionView/tool contract；
- control logic commit；
- no-skill state；
- 预算和 Provider usage；
- invalid-run 分类。

Failure Family 只有在以下条件下才可进入 Candidate：

1. Runtime、index、Provider 和数据均健康；
2. 语料中确实存在可支持 Evidence；
3. 同类错误出现在至少两个不同任务，而不是同一 Query 重跑；
4. 能定位 first actionable step；
5. 该 step 属于允许修改的 Search/Research Policy；
6. 至少能预留一个 held-out related task；
7. 能定义 unrelated regression 和 falsification condition。

Calibration 允许三种诚实结果：

```yaml
result:
  - qualified_failure_family_found
  - no_candidate_qualified
  - blocked_by_infrastructure_or_data
```

若没有合格 Failure Family，停止，不建设 Candidate、SkillRepo 或 Progressive Disclosure 平台。

---

# 6. Current Candidate Surface

## 6.1 Accepted initial surface

```yaml
initial_candidate_surface:
  - Search Skill
  - Query Decomposition Policy
  - Query Rewrite Policy
  - Counterexample Search Policy
  - Source Diversity Policy
  - Follow-up Strategy
  - Stop / Continue Policy
```

首次只应选择其中一个真实 Failure Family，不要求同时实现全部类型。

## 6.2 Deferred from initial V5-D scope

```yaml
deferred_from_initial_V5_D:
  - Answer Presentation Policy
  - Generic Context Projection Policy
  - Generic Tool Budget Policy
  - Generic Workflow Policy
```

理由：

- Answer Presentation 已由 V5-C 持有明确产品责任；
- generic Context/Tool/Workflow 很容易演化成通用 Agent Harness；
- 如果未来出现具体的 search-specific Context 或 Budget 假设，可以重新进入 V5-D JIT 审查；
- deferred 不等于从长期路线永久删除。

## 6.3 Human-only boundaries

以下对象永远保持 human-only：

- Runtime Source Patch；
- Evidence Authority；
- Verifier；
- Dataset/Split；
- Promotion Logic；
- Tool Permission Boundary。

---

# 7. Recommended Goal and Stage Structure

建议使用四个 Stage，不再拆大量 Gate。

## Stage 0 — Entry Calibration

- 真实语料、真实 Runtime、No-Skill baseline；
- 生成 replayable traces；
- 区分 product、policy、provider、data、retrieval infrastructure failure；
- 资格化一个重复 Failure Family，或者诚实停止。

## Stage 1 — Attribution and Candidate Contract

- first actionable step attribution；
- Experience/Hypothesis ledger；
- falsification condition；
- applicable scope；
- protected boundaries；
- 一个 versioned Candidate package；
- Candidate 不能进入 active runtime。

## Stage 2 — Paired Evaluation

- frozen baseline/treatment；
- source cases；
- held-out related cases；
- unrelated regression；
- environment shift；
- negative-transfer check；
- invalid-run exclusion；
- Candidate 输出只能是 validated、rejected 或需要补证据。

## Stage 3 — Controlled Use and Closeout

只在 Candidate validated 后进入：

- 最小 applicability gate；
- progressive disclosure；
- shadow；
- human promote；
- baseline fallback；
- deprecate/rollback；
- UI/API、observability、restart/recovery；
- final closeout。

如果 Stage 0 没找到合格 failure，后面三个 Stage 均不启动。

---

# 8. Portfolio-ready Minimum Evidence Loop

一个强 Candidate 足够，最低闭环是：

```text
真实失败
→ first actionable trace step
→ 可证伪假设
→ 一个 Candidate
→ frozen no-skill baseline
→ treatment
→ 新的 related held-out task 改善
→ unrelated task 无明显退化
→ negative-transfer check
→ human promotion
→ applicability-gated injection
→ baseline fallback
→ rollback demo
```

指标必须衡量真正的研究结果，例如：

- required aspects 覆盖；
- grounded Evidence/Citation；
- counterexample preservation；
- source diversity；
- no-progress/stop correctness；
- 成本和额外 tool/provider calls。

不能只比较：

- 返回文字更多；
- hit 数量更多；
- 原始失败 Query 上单次分数更高。

一个 Candidate 达成以上闭环，即足够构成很强的简历和 Demo 证据。不强制第二类 Skill。

---

# 9. Portfolio-ready versus Version Complete

## 9.1 Portfolio-ready

- 一个真实 Failure Family；
- 一个 validated Candidate；
- 有 held-out related improvement；
- 无明显 unrelated regression；
- promotion、gated use 和 rollback 可稳定演示；
- 有完整 Trace 和实验报告。

## 9.2 Version Complete

Version Complete 还需要：

- durable Experience/Hypothesis/Candidate lifecycle；
- experiment identity 与 scaffold fingerprint；
- invalid-run 和 Provider accounting；
- restart/recovery/idempotency；
- promotion/deprecation/rollback 权威边界；
- active-skill version 与 baseline fallback；
- 完整回归、mainline、live smoke、closeout；
- 所有 known limits 诚实记录。

Version Complete 不要求多个 Candidate family，但要求这个 Candidate 的完整生命周期成为可靠产品能力。

---

# 10. Boundary with the Pi Project

原规划中的边界仍正确。

拾流继续负责：

- 视频 Research Agent；
- Transcript Evidence 和 Citation；
- Durable Research Task；
- domain-specific Trace Attribution；
- Search/Research Failure Family；
- Search Skill；
- related/unrelated research replay；
- applicability gate、human promotion 和 rollback。

Pi 继续负责：

- 通用 Coding Agent Runtime；
- File/Shell/Git/Test Tool；
- Context/Tool/Session Reliability；
- Environment Outcome；
- alternative-path recovery；
- generic Harness Trace/Replay；
- generic Policy Regression。

需要防止两种误解：

- 拾流仍然必须建设完成自身 Search Skill 证明所需的最小 replay/eval/promotion 机制，不能因为 Pi 存在就删除技术闭环；
- 拾流不建设通用 best-of runtime、Context optimizer、Tool reliability framework 或 Workflow evolution platform。

两者可以共享：

```text
Experience → Candidate → Eval → Promote
```

但不共享核心学习对象，也不共享核心实现责任。

---

# 11. V5-A Compound-query Retrieval Limitation

目前该 case 不应直接进入 V5-D。

当时的事实包括：

- dense model not ready；
- lexical fallback 召回不足；
- 最终 0 hits；
- 无 EvidenceUse/Citation；
- 代表性 grounded completion 未证明。

这更像“未分类的 retrieval availability/fallback 问题”，目前没有证据证明 Query Decomposition 或 Search Skill 可以稳定改善。

后续分类规则：

```text
如果 index/model/source unavailable
→ Infrastructure / Retrieval Implementation

如果语料根本不存在目标 Evidence
→ Data / Corpus Coverage

如果 Evidence 存在、retrieval 健康，
但 Query Decomposition / Rewrite / Search Strategy
在多个任务上稳定漏掉它
→ V5-D Search Policy Candidate
```

当前应记录为：

```yaml
V5_A_compound_query_case:
  classification: unclassified_policy_vs_infrastructure
  V5_D_candidate_authorized: false
  reassess_during_entry_calibration: true
```

---

# 12. Required Document Updates after Acceptance

用户已正式接受本次 calibration。后续规划轮应更新：

## 12.1 V5_PROGRAM_CURRENT_STATE.md

将 V5-D 从单纯 `not_started` 细化为：

```yaml
status: entry_calibration_required
candidate_implementation_authorized: false
```

同时把 V5-A limitation 改成 conditional classification，而不是默认归 V5-D 解决。

## 12.2 V5_PROGRAM_DECISION_LEDGER.md

记录本次路线校准、Candidate Surface 和 Pi 边界判断。

## 12.3 Original integrated roadmap

原总体路线文件不需要重写。核心 V5-D 路线没有改变；Answer/Generic Policy 的当前 deferred 状态应由 V5-D Charter 和 Program Decision Ledger 表达。

## 12.4 V5-D startup documents

正式启动时新建：

```text
V5_D_VERSION_CHARTER.md
V5_D_STARTUP_AND_EXECUTION_PLAN.md
V5_D_STAGE_0_ENTRY_CALIBRATION_CONTRACT.md
```

Stage 0 接受前不创建 Candidate Skill、Skill Repository 或通用 Eval/Harness 平台。

---

# 13. Planning-round Actions and Explicit Non-actions

```yaml
planning_actions:
  calibration_status_updated_to_accepted: true
  V5_D_VERSION_CHARTER_created: true
  V5_D_STARTUP_AND_EXECUTION_PLAN_created: true
  V5_D_STAGE_0_ENTRY_CALIBRATION_CONTRACT_created: true
  V5_PROGRAM_CURRENT_STATE_modified: true
  V5_PROGRAM_DECISION_LEDGER_modified: true

non_actions:
  V5_D_session_created: false
  product_code_modified: false
  product_tests_modified: false
  schema_or_migration_modified: false
  provider_runs_performed: false
  credentials_accessed: false
  live_database_modified: false
  candidate_skill_created: false
  skill_repository_created: false
  generic_eval_platform_created: false
  generic_harness_created: false
  active_skill_promoted: false
  original_roadmap_modified: false
  git_merge_or_tag_performed: false
```

---

# 14. Final Status

```yaml
final_calibration:
  decision: retain_v5_d_with_bounded_entry_calibration
  core_loop_preserved: true
  entry_gate_met: false
  calibration_stage_required: true
  initial_candidate_count_target: 1
  generic_agent_learning_platform: prohibited
  candidate_skill_implementation_authorized: false
  provider_runs_authorized: false
  V5_D_session_created: false
  product_code_modified: false
  accepted_by_user: true
  awaiting_user_acceptance: false
```

最合适的下一步不是直接实现 V5-D，而是更新 Program Current State 与 Decision Ledger，形成精简
Charter、Startup Plan 和 Stage 0 Entry Calibration Contract，再由用户审查执行预授权。执行预授权前
不创建或启动持续的 V5-D Version Session，也不运行 Stage 0。
