# Shiliu V5-D Version Charter

> Version: V5-D
> Goal: Controlled Experience-driven Search Policy Improvement
> Prepared by: Shiliu V5 Main Codex Session
> Prepared at: 2026-08-10
> Status: candidate_v1_1_rejected_pending_version_direction
> Planning authority: user-authorized
> Execution authority: none_pending_user_direction
> Accepted by: user
> Accepted at: 2026-08-11
> V5-D Version Session created: true
> Product implementation started: false

---

# 1. Product Mission

让拾流能够从多个真实研究任务的可重放 Trace 中识别重复的 Search / Research Policy Failure，
形成一个可证伪的 Candidate，并且只有在相关任务泛化、无关任务回归、负迁移检查和人工批准均
成立后，才允许该搜索方法以适用性门控方式持续影响后续研究；任何时候均可回到 No-Skill
Baseline。

```text
Real Research Failure
→ Step-level Attribution
→ Falsifiable Hypothesis
→ Candidate Search Policy
→ Frozen Paired Evaluation
→ Human Promotion
→ Applicability-gated Use
→ Deprecation / Rollback
```

V5-D 不宣传为开放式 Self-Evolving Agent，也不建设通用 Agent Learning / Harness Platform。

---

# 2. User-visible Product Delta

V5-D 完成后，用户可以：

- 查看一个搜索方法从哪些真实失败、Trace step 和 Evidence 形成；
- 查看 Baseline 与 Candidate 在 source、held-out related、unrelated Case 上的对照结果；
- 明确批准、拒绝、停用或回滚一个 Search Policy；
- 看到某次 Research 是否注入了哪个已批准 Policy、为什么适用、额外成本是多少；
- 在 Candidate 不适用、失效或被回滚时自动使用原始 No-Skill Baseline。

版本不承诺自动产生很多 Skill。一个真正有效、可泛化、可回滚的 Candidate 闭环即可满足核心
产品命题。

---

# 3. Starting Facts

## 3.1 Inherited accepted baseline

- V5-A：durable Task / Goal / Attempt / Checkpoint / Trace / Outer Audit、HITL、预算、Provider
  receipt、fail-closed side effect 和 restart/resume；
- V5-B：Evidence-backed Artifact、Workspace、`system_experience` candidate lineage、Feedback 与
  durable observability；
- V5-C：可确认和回滚的个人状态、Corpus-aware Search、advisory route 与非干扰边界；
- V4：`/search`、Fast、Deep、Shared Grounding、Stable Citation、DecisionView 与预算机制；
- mainline accepted code head：`8904e27df07becebae13110f9be17cd829373b20`；
- 当前治理 head：`f85d504`；live schema 14，157 videos、140 completed；
- 当前没有 Active Skill，构成逻辑上的 No-Skill Baseline。

## 3.2 Entry limitations

```yaml
live_research_tasks: 0
live_research_traces: 0
live_experience_candidates: 0
live_feedback_population: 0
qualified_repeated_failure_family: false
frozen_related_unrelated_split: false
negative_transfer_evidence: false
```

历史 retrieval trace 只能帮助了解数据形态，不能直接证明 Policy Failure。V5-A compound-query
limitation 仍是 `unclassified_policy_vs_infrastructure`，不自动成为 V5-D Candidate。

## 3.3 Entry readiness

```yaml
mechanical_foundation_ready: true
empirical_entry_gate_met: true
bounded_stage_0_status: accepted
candidate_product_integration_authorized: false
experiment_only_treatment_implementation_authorized: false
stage_2_status: accepted_rejected
candidate_evaluation_status: rejected
```

---

# 4. Formal Version Stages

V5-D 只保留一条正式 Stage 主线。Stage 数量固定为四个，但 Version Session 可以在同一 Stage
内部调整实现切片，不为小修复新增正式 Gate。

| Stage | Title | Depends on | Formal outcome |
| --- | --- | --- | --- |
| 0 | Bounded Entry Calibration | accepted A/B/C baseline | 一个真实重复 Policy Failure 被资格化，或诚实停止 |
| 1 | Attribution and Candidate Contract | Stage 0 accepted with qualified family | first actionable attribution、冻结 Hypothesis、一个 inactive Candidate |
| 2 | Frozen Paired Evaluation | Stage 1 accepted | validated / rejected / inconclusive Candidate judgment |
| 3 | Controlled Use and Version Closeout | Candidate validated and Stage 2 accepted | 最小 gated use、人工 promotion、fallback、rollback 与 closeout |

如果 Stage 0 结果为 `no_candidate_qualified` 或 `blocked_by_infrastructure_or_data`，Stage 1–3
不自动启动。修复基础设施缺陷必须另行定约；不得将其包装为 Search Skill 增益。

## 4.1 Stage 0 — Bounded Entry Calibration

产品/研究结果：在真实收藏语料、真实 Research Runtime 和候选无关的代表性任务上，生成有效
No-Skill baseline Trace，区分 policy、retrieval infrastructure、data、provider、implementation
和 invalid run，并尝试资格化一个重复 Failure Family。

正式 Exit 只有三类：

```yaml
- qualified_failure_family_found
- no_candidate_qualified
- blocked_by_infrastructure_or_data
```

本 Stage 不创建 Candidate、Skill Repository、通用 Eval Platform 或 Active Skill。

## 4.2 Stage 1 — Attribution and Candidate Contract

产品/工程结果：对已资格化 Failure Family 定位 first actionable step，形成 Experience / Attribution /
Hypothesis 的独立 lineage，冻结可证伪条件、适用范围和验证计划，并产出一个 versioned、inactive、
不可被 Runtime 自动使用的 Candidate package。

Stage 1 只允许一个 initial Candidate。若证据不支持 Hypothesis，结果是 `falsified` 或
`inconclusive`，不为完成版本而更换到未资格化的新 Skill 类型。

## 4.3 Stage 2 — Frozen Paired Evaluation

产品/评测结果：在固定 Scaffold 下比较 No-Skill Baseline 与 Candidate Treatment。Source Case
用于解释原失败；真正 held-out related Case 证明泛化；unrelated Case 检查回归和负迁移。

核心硬门：

- Related-task Generalization；
- Unrelated Regression；
- Negative Transfer；
- Invalid Run 排除；
- Experiment Identity、成本和调用完整。

Environment Shift 不是 Portfolio-ready 硬门。仅当 Candidate 声称跨特定环境适用时，才由
Stage 2 Contract 加入；否则可在 Version Complete 前记录为条件性证据或 known limit。

## 4.4 Stage 3 — Controlled Use and Version Closeout

只在 Candidate 被 Stage 2 证明为 `validated` 后进入。Stage 3 实现最小 Candidate repository、
applicability gate、progressive disclosure、shadow/active 状态、人工 promotion、baseline fallback、
deprecation 和 rollback，并提供最小 UI/API/observability。

它不建设通用 Skill Retrieval、Curator、自动 Workflow Evolution 或跨项目平台。没有 validated
Candidate 时，本 Stage 不启动。

---

# 5. Candidate Surface

## 5.1 Initial allowed surface

```yaml
allowed:
  - search_skill
  - query_decomposition_policy
  - query_rewrite_policy
  - counterexample_search_policy
  - source_diversity_policy
  - follow_up_strategy
  - stop_continue_policy
```

这些只是允许的对象集合，不是待实现列表。实际 Candidate 必须来自 Stage 0 资格化的单一真实
Failure Family。

## 5.2 Deferred

```yaml
deferred:
  - answer_presentation_policy
  - generic_context_projection_policy
  - generic_tool_budget_policy
  - generic_workflow_policy
```

Search-specific context 或 budget 假设只有在真实 Trace 明确归因且不扩张为通用 Harness 时，才可
通过 Charter amendment 重新进入。Answer Presentation 的当前产品所有权属于 V5-C。

## 5.3 Human-only

```yaml
human_only:
  - runtime_source_patch
  - evidence_authority
  - verifier
  - dataset_and_split
  - promotion_logic
  - tool_permission_boundary
```

---

# 6. Frozen Invariants

```yaml
protected_invariants:
  - transcript_source_authority
  - stable_citation_identity
  - source_version_validation
  - evidence_and_artifact_lineage
  - dataset_and_split_identity
  - deterministic_judge_or_frozen_evaluator
  - promotion_gate
  - invalid_run_policy
  - experiment_identity
  - provider_usage_and_cost_accounting
  - tool_permission_boundary
  - user_confirmation_for_promotion
  - explicit_user_choice_and_V5_C_authority
  - no_skill_baseline_fallback
  - candidate_cannot_modify_its_own_evaluator
```

Candidate 不保存视频事实，不成为 Citation，不得读取 Gold，不得修改 Verifier、Split、Promotion Gate
或 Evidence Authority。

---

# 7. Lifecycle Contract

```text
Trace
→ Experience Record
→ Failure Attribution
→ Improvement Hypothesis
→ Candidate Package
→ Experiment Plan / Run
→ Validation Decision
→ Human Promotion Decision
→ Shadow / Active / Deprecated / Rolled Back
```

这些对象必须拥有独立 ID、版本、来源和状态，不能把一段 Reflection 直接升级为 Active Skill。

最低状态模型：

```yaml
hypothesis_status: [draft, frozen, supported, falsified, inconclusive, superseded]
candidate_status: [proposed, testable, evaluating, validated, rejected, shadow, active, deprecated, rolled_back]
experiment_status: [planned, frozen, running, completed_valid, completed_invalid, superseded]
promotion_status: [not_requested, pending_human, approved, rejected, rolled_back]
```

只有人类明确批准可以使 Candidate 进入 `active`。Stage Acceptance 不等于 promotion；promotion
也不允许修改历史实验或删除失败证据。

---

# 8. Evaluation and Contamination Contract

1. Stage 0 代表性任务在具体 Failure Family / Candidate Hypothesis 冻结前按候选无关规则选择、
   冻结和哈希；
2. Source/Development Case 可用于 Attribution 和 Candidate 设计，必须标明已消耗；
3. Held-out Related Case 不得参与 Candidate、Trigger、Procedure、Stop Rule 或其他调参；
4. 一旦发生上述访问或使用，该 Case 立即降级为 development，不得再出现在 held-out 结论中；
5. 只能从 Stage 0 已冻结且未打开的 reserve pool 补位；reserve pool 耗尽则该 Candidate 的泛化
   结论失败，不得事后挑新题修补；
6. Gold、Judge、Split 和 Promotion Gate 对 Candidate 执行上下文不可见；
7. Provider、infrastructure、evaluation invalid run 不进入质量汇总，不触发机会性调参；
8. Related improvement 不能以 unrelated 明显退化为代价；负迁移越过 Contract 阈值即拒绝 promotion。

---

# 9. Upstream Research Boundary

当前 Registry 和本地 A/B/C 实现足以形成 Charter 与 Stage 0 Contract，无需本轮下载上游。

| Resource | Current status | JIT trigger | Current decision |
| --- | --- | --- | --- |
| SearchCLI | docs reviewed, absent locally | Stage 1/2 experiment workflow has a concrete gap | conditional source/test review |
| SkillAdaptor | docs reviewed, absent locally | Stage 1 attribution mapping has a concrete gap | conditional bounded spike |
| HDSO paper | reconnaissance | freezing Hypothesis/paired eval semantics | conditional primary-paper review |
| Youtu-Agent | docs reviewed, absent locally | existing experiment identity is insufficient | conditional source/test review |
| SkillOS / MUSE | reconnaissance | only after a Candidate is validated and lifecycle gap exists | deferred |

任何材料性 JIT 研究必须遵循 Registry → local check → fixed Commit/primary paper → License → source/test
or spike → Research Log → Adoption Decision → Stage Contract。下载、论文阅读或 pattern 参考均不构成
实施授权；不批量下载，不复制通用 Skill Framework。

---

# 10. Baseline and Evidence Risk

| Stage | Risk level | Required identity |
| --- | ---: | --- |
| 0 | 3 | code/scaffold/corpus/index/source/model/provider/no-skill/case manifest/access policy |
| 1 | 2→3 | accepted failure family、Trace/Experience IDs、Hypothesis/Candidate version、protected boundary |
| 2 | 3 | frozen experiment manifest、split hash、evaluator、paired runs、usage/cost、invalid ledger |
| 3 | 3 | validated Candidate、active repo version、promotion authority、fallback/rollback、live-safe plan |

证据至少区分 Source、Mechanical、Product Runtime、Evaluation 与 Human Decision。Report 只索引
Commit、Run ID、Trace ID、Artifact ID、hash 和用户决定，不能补写不存在的 Evidence。

---

# 11. Portfolio-ready Milestone

```yaml
portfolio_ready:
  real_repeated_failure_family: true
  first_actionable_attribution: true
  falsifiable_hypothesis: true
  one_validated_candidate: true
  heldout_related_generalization: true
  unrelated_regression_acceptable: true
  negative_transfer_gate_passed: true
  human_promotion_demonstrated: true
  applicability_gated_use_demonstrated: true
  baseline_fallback_and_rollback_demonstrated: true
  replayable_trace_and_experiment_report: true
  environment_shift_required: false
```

一个 Candidate 足够；不以 Candidate 数量、平台宽度或自动化程度作为 Portfolio-ready 指标。

---

# 12. Version Complete

```yaml
version_complete:
  all_started_formal_stages_accepted: true
  durable_lifecycle_and_lineage: true
  experiment_identity_and_scaffold_fingerprint: true
  invalid_run_and_provider_accounting: true
  restart_recovery_and_idempotency: true
  promotion_deprecation_rollback_authority: true
  active_version_and_no_skill_fallback: true
  relevant_regressions_passed: true
  mainline_integration_and_live_safe_smoke: true
  known_limits_disclosed: true
  final_closeout_and_git_seal: true
```

若 Stage 0 诚实得出 `no_candidate_qualified`，可关闭 calibration effort，但不能宣称 V5-D
Portfolio-ready 或上述 product Version Complete。是否将这种结果记为 `paused`、`closed_no_candidate`
或等待真实数据，由用户根据作品集目标决定。

---

# 13. Non-goals

- 通用 Agent Learning、Coding Harness、Context/Tool/Session reliability 平台；
- best-of-N runtime、模型微调、RL、参数更新或 Curator 训练；
- 自动修改源码、Verifier、Judge、Promotion Gate 或权限；
- 无人工批准的自动 promotion；
- 为架构完整度预建通用 Skill Repository / Retrieval / Eval SaaS；
- 把 V5-C Answer Presentation 迁回 V5-D；
- 把 retrieval/infrastructure defect 包装为 Policy improvement；
- 为展示效果制造 Failure、挑选迎合预设 Candidate 的题目或事后改 held-out；
- 多 Candidate family、GraphRAG、Post-V5 或 Pi 项目能力。

---

# 14. Session, Git and Acceptance Governance

```text
V5 Main Session
→ one persistent V5-D Version Session
→ optional bounded upstream / held-out / eval specialist Sessions
```

- Version Session 主导版本内研究、Stage Contract、实现、普通 Bug 修复、测试和报告；
- Main Session 只做目标/边界审阅、阶段有限验收、Program authority 和版本级 Git；
- 专项 Session 只服务当前正式 Stage，结果先回到 V5-D Session；
- `active_subversion_limit=1`，`active_formal_stage_or_goal_limit=1`；
- V5-D 使用独立 `codex/v5-d` branch/worktree，本轮不创建；
- Stage 内小 Commit 和有界修复不需要新 Gate；
- 子版本 Session 不能自我接受、merge mainline、Push 或 Tag；
- Main 只合并已接受结果，不直接修产品代码。

---

# 15. Pause Conditions

- Stage 0 case freeze 发生在预设 Candidate 之后或存在反向选题；
- held-out 泄漏、Gold/Verifier/Split/Promotion Gate 被 Candidate 访问或修改；
- 找不到至少两个不同 discovery tasks 的同类 first-actionable Policy Failure；
- Failure 更像 data、retrieval implementation、provider 或 infrastructure；
- Candidate 需要进入 deferred/generic/human-only surface；
- 需要新 Provider、凭据、预算、live DB 写入、migration 或不可逆数据操作；
- 上游 License 不明、需要复制代码或下载高成本资产；
- 负迁移越界、Experiment Identity 不完整或连续 invalid/no-progress；
- 工作变成通用 Agent Platform、跨入 Post-V5/Pi，或要求材料性路线改变。

---

# 16. Allowed Roadmap-preserving Adjustments

V5-D Session 可提议调整 Stage 内部切片、schema、模块、测试入口、Candidate package 表达和 JIT
上游选择。Main 可在不改变核心闭环的前提下接受这些调整。以下变化必须交用户：删除任何核心
泛化/负迁移/人工 promotion/rollback Gate，扩大到通用平台，增加材料性成本，或改变产品/作品集目标。

---

# 17. Expected Final Artifacts

- `V5_D_CURRENT_STATE.md`、`V5_D_DECISION_LEDGER.md`（执行 Session 启动后）；
- 每个已启动 Stage 的 Contract、Implementation/Evaluation Report 和 Main Acceptance Decision；
- 受保护的 Case/Experiment manifest hash 与污染/invalid-run ledger；
- 必要的 JIT upstream report、Research Log/Registry proposal 和 Adoption Decision；
- 一个 Candidate 的 Trace → Attribution → Hypothesis → Eval → Promotion → Rollback 证据链；
- `V5_D_FINAL_CLOSEOUT.md`；
- Program Current State、Decision Ledger、mainline merge 与版本级 Git 记录。

Raw Provider response、私人 Query/Evidence、凭据、完整上游仓库和大型 Trace 不进入 Git。

---

# 18. Current Authorization Status

```yaml
planning_complete: true
charter_accepted_by_user: true
V5_D_session_creation_authorized: true
V5_D_session_created: true
stage_0_status: accepted
stage_0_execution_authorized: closed_completed
product_implementation_authorized: false
provider_runs_authorized: false
candidate_contract_status: accepted_proposed_non_active
candidate_evaluation_status: rejected
candidate_revision_R1_authorized: closed_completed
candidate_revision_R1_target_version: 1.1.0
candidate_revision_R1_status: accepted_invalid_run
candidate_v1_1_effectiveness: rejected
candidate_v1_1_source_gate: reached_failed_on_valid_D02_pair
candidate_revision_R1_E1_authorized: closed_completed
candidate_revision_R1_E1_kind: mechanical_execution_only
candidate_revision_R1_E1_status: accepted_candidate_v1_1_rejected
further_major_revision_default_authorized: false
experiment_only_treatment_implementation_authorized: false
reserve_open_authorized: false
skill_repository_authorized: false
promotion_authorized: false
stage_1_execution_authorized: closed_completed
stage_2_execution_authorized: closed_completed
stage_2_acceptance_status: accepted_rejected
stage_3_execution_authorized: false
```

本 Charter 是持续 V5-D Version Session 的上位合同。R1 本身曾以 exact `invalid_run` 完成并由 Main 有限
验收；在该历史 checkpoint，Candidate v1.1 Source Gate 未达到、effectiveness unproven。
R1-E1 已由 Main 有限验收为 exact `candidate_v1_1_rejected`：有效 D02 Treatment 改变了局部 recovery/stop
行为，但没有改善 required-aspect、grounded Citation 或 source outcome，因此 Source Gate 失败并按合同停止
D04。Candidate v1.0/v1.1 均 rejected，唯一 major revision budget 已使用。当前没有 execution authority；
Reserve、held-out、Stage 3、active/shadow registration、promotion、live DB 与版本集成均未授权，v1.2 也
未授权。下一步等待用户决定诚实 closeout 或材料性重新授权新方向。
