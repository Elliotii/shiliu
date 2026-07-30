# Shiliu V5-A Subversion Startup Package

> Status: approved
> Created by: Shiliu V5 Main Codex Session
> Approved by: User
> Approved at: 2026-07-30
> Starting repository: `/Users/elliot/new-systems/agent-job-prep/Shiliu`
> Starting product commit: `483fd46bca1d7141a696fda4b2d1e093a55f209b`
> Starting governance commit: `1db3c2c9cc119a5c050b63f2ddab3e73cc5ff82e`
> Execution branch: `codex/v5-a`
> Execution starting commit: governance commit containing this approved startup package

---

# 1. Subversion Mission

V5-A 让用户可以创建一个长程研究任务，在进程退出、失败或等待人工决策后继续运行；任务基于已持久化的 Transcript Evidence 审核目标覆盖、Claim 支持、冲突和缺口，定向继续或诚实停止，并形成可审计的最终研究结果。

V5-A 不是给 V4 Deep Graph 简单增加 Checkpointer，也不是重写现有 Search、Answer 或 Citation。

---

# 2. Binding Roadmap Scope

## 2.1 Relevant Roadmap Sections

- `拾流_V5及后续版本规划_现阶段整合版.md` 第 2、3、4、5、6、7、39、40、41、42 节。
- `00_拾流V5主Codex角色权限与Session治理.md`。
- `001_拾流V5开发研究与证据治理规范.md`。
- `02_拾流V4_V4_1至V5技术事实交接.md`。

## 2.2 Functional Goals That Must Be Preserved

- 新增 `/research` 与 Durable `ResearchTask` 产品路径。
- Task、Goal、Attempt、Checkpoint 和 Event 具有持久身份与 Lineage。
- ResearchTask 可以跨真实进程中断恢复。
- Inner Research Loop 复用现有 Retrieval、Evidence、Citation 和 Deep Runtime 资产。
- Outer Goal Audit 只能使用当前可见 Evidence。
- Typed Blocker、Targeted Continuation、ProgressDelta 和 No-progress 具有明确合同。
- HITL 至少支持 Approve、Edit、Reject。
- Retry、Cancel、Budget、Failure 和 Side Effect 具有可审计语义。
- Resume 不重复已经确认的关键副作用。
- 有可展示、可审计且不暴露隐藏推理的 Task Trace。
- V5-A 产生的 Knowledge、Corpus、User Model 和 System Experience Delta 只保持为 Candidate。

## 2.3 Implementation Details Not Frozen

- Framework 和 Checkpointer 选型。
- Database Schema 和 Migration 细节。
- 内部对象字段和文件布局。
- 正式 Stage 数量与内部顺序。
- 上游采用方式。
- Prompt、Provider 和 Tool 的具体接点。
- UI 结构。

路线文件中的 G1–G4 是功能覆盖建议，不机械冻结为实施顺序。

---

# 3. Starting Baseline

```yaml
baseline:
  risk_level: 2
  repository: /Users/elliot/new-systems/agent-job-prep/Shiliu
  governance_branch: codex/v5-main
  governance_commit_before_startup_package: 1db3c2c9cc119a5c050b63f2ddab3e73cc5ff82e
  execution_branch: codex/v5-a
  accepted_product_commit: 483fd46bca1d7141a696fda4b2d1e093a55f209b
  working_tree_at_authorization: clean
  v4_v4_1_live_audit: completed_without_material_difference
  database:
    path: /Users/elliot/Library/Application Support/Shiliu/shiliu.db
    schema_version: 6
  index: shiliu_live_current
  corpus:
    videos: 157
    completed_videos: 140
    content_video_directories: 150
  provider_configuration: existing_local_configuration_not_exposed
  provider_runs_authorized_in_startup_batch: false
  relevant_authority_files:
    - V5_PROGRAM_CURRENT_STATE.md
    - V5_PROGRAM_DECISION_LEDGER.md
    - 拾流_V5主Codex交接包_2026-07-30/拾流_V5及后续版本规划_现阶段整合版.md
    - 拾流_V5主Codex交接包_2026-07-30/00_拾流V5主Codex角色权限与Session治理.md
    - 拾流_V5主Codex交接包_2026-07-30/001_拾流V5开发研究与证据治理规范.md
    - 拾流_V5主Codex交接包_2026-07-30/02_拾流V4_V4_1至V5技术事实交接.md
    - 拾流_V5主Codex交接包_2026-07-30/03_拾流V5上游项目与研究资料注册表.yaml
    - 拾流_V5主Codex交接包_2026-07-30/04_拾流V5上游研究活动日志.jsonl
    - 拾流_V5主Codex交接包_2026-07-30/05_拾流V5执行模板合集.md
```

启动前机械核验：

```yaml
directed_v4_v4_1_tests:
  result: 68_passed
  warning: StarletteDeprecationWarning_from_test_dependency
provider_calls: 0
```

---

# 4. Frozen Invariants

- Transcript / ASR 继续是事实权威。
- Stable Citation Identity、Source Version 和 Revalidation 不得降低。
- Evidence 与 Display Context 必须继续分离。
- 现有 `/search`、`/ask Fast` 和 `/ask Deep` 产品路径不得静默回归。
- Fast/Deep 必须继续共享 Grounding 底座。
- DecisionView 与完整 Runtime State 必须分离。
- Provider Failure 不得直接解释为算法失败。
- 不得机会性重跑或丢弃失败样本。
- Candidate 不得修改 Evidence Authority、Verifier 或 Completion Gate。
- Task、Attempt、Checkpoint、Event、Trace、Result 和 SideEffect 必须保持语义分离。
- Goal Edit、Retry 和 Resume 不得覆盖旧 Attempt 或历史 Goal。
- 不确定的外部 `in_flight` 动作必须 Fail-closed。
- 任何长期 Profile、Grounded Knowledge 或 Active Skill Promotion 不属于 V5-A。

---

# 5. Initial Research Scope

## 5.1 Priority Upstreams

| Resource ID | Research Question | Current Status | Expected Depth |
|---|---|---|---|
| `deer_flow` | Goal、Blocker、Continuation、No-progress、Checkpoint Lineage、Mutation Guard 和 Branch/Replay 的真实源码与失败测试是什么？ | `candidate`; local `absent`; docs reviewed | source + tests；必要时有界 Spike |
| `arex_paper` | Inner Research、Outer Constraint Audit、Targeted Follow-up 与 Compact Improvement State 哪些可脱离训练方案映射到拾流？ | `candidate`; local `absent`; initial reconnaissance | full method + limitations + official code/license check |
| `youtu_agent` | Experiment Identity、restart_step 和 Trajectory Record 是否适合 V5-A Reliability Eval？ | `candidate`; local `absent`; docs reviewed | deferred until Trace/Replay/Eval Stage |

DeepTutor、WeKnora、SearchCLI、SkillAdaptor、SkillOS、HDSO、MUSE-Autoskill 和 Youtu-GraphRAG 不进入初始 V5-A 研究范围。

## 5.2 Autonomous Download Permission

```yaml
upstream_download:
  allowed_within_scope: true
  allowed_resources:
    - deer_flow
    - arex_paper
  official_sources_only: true
  check_registry_and_local_first: true
  fixed_commit_required_for_source_review: true
  license_recheck_required: true
  large_upstream_mirror_committed: false
  implementation_authorized_by_download: false
  paid_services_allowed: false
```

## 5.3 Mandatory Pause Cases

- 官方来源、Commit 或 License 不明确。
- 主仓库和局部组件许可证冲突。
- 需要大型模型、数据集、付费服务或凭据。
- 上游文档、源码和测试发生材料冲突。
- 研究问题扩张为完整 Agent Framework 审计。
- 触及 Transcript Authority、Stable Citation、Source Version 或 Fast/Deep 既有产品路径。
- 需要修改长期路线或进入 V5-B/C/D。

---

# 6. Expected Version Artifacts

Version 级最小文件：

- `V5_A_VERSION_CHARTER.md`
- `V5_A_CURRENT_STATE.md`
- `V5_A_DECISION_LEDGER.md`
- `V5_A_FINAL_CLOSEOUT.md`

正式 Stage 的最小文件：

- Stage Contract
- Implementation Report
- Main Session Acceptance Decision

按需文件：

- Bounded Research Contract / Report
- Upstream Adoption Decision
- Blocking Report
- Independent Review

不为每次浏览、小 Commit 或普通测试创建正式治理文件。

---

# 7. Session Authority

```yaml
subversion_session:
  may_research: true
  may_download_authorized_upstreams: true
  may_design: true
  may_implement_after_charter_and_stage_authorization: true
  may_test_within_contract: true
  may_create_bounded_sessions: true
  may_commit_to_execution_branch: true
  may_submit_for_review: true

  may_implement_in_startup_batch: false
  may_run_provider_in_startup_batch: false
  may_execute_migration_in_startup_batch: false
  may_copy_upstream_code_in_startup_batch: false
  may_self_accept: false
  may_modify_long_term_roadmap: false
  may_update_program_authority_files: false
  may_start_next_subversion: false
  may_merge_without_main_acceptance: false
```

主 Session只负责治理、研究证据审查、阶段验收和版本级 Git，不实施产品目标。

---

# 8. First Required Output

V5-A Session 首批只需：

1. 核验真实 Branch、HEAD、Working Tree、DB、索引、Provider 和权威文件。
2. 审计 V5-A 相关源码和 V4.1 Harness，列出可继承资产与不可继承假设。
3. 完成 DeerFlow 有界源码/测试研究。
4. 完成 AREX 方法、限制、官方代码和 License 核验。
5. 提出 Registry / Research Log 更新建议和 Adoption Decision Proposal。
6. 创建 `V5_A_VERSION_CHARTER.md` Draft。
7. 创建精简的 `V5_A_CURRENT_STATE.md` 和 `V5_A_DECISION_LEDGER.md`。
8. 提出非机械的阶段划分。
9. 创建 `V5_A_STAGE_1_CONTRACT.md` Draft。
10. 提交研究与规划结果供主 Session审查。

Charter 与 Stage 1 Contract 被主 Session接受前，不得开始产品实现。

---

# 9. Recommended Formal Stages

```yaml
recommended_stages:
  - durable_task_kernel_and_safety_envelope
  - evidence_backed_inner_research_loop
  - outer_goal_audit_and_recursive_continuation
  - HITL_and_operational_control
  - product_completion_trace_and_reliability_evaluation
```

关键规划修正：

- Idempotency、SideEffectRecord 和不确定 `in_flight` 处理必须从 Stage 1 建立安全边界。
- 每个 Stage 优先形成用户可观察的纵向闭环。
- Crash/Resume、Retry、Cancel、HITL、Conflict 和 No-progress 必须在相关 Contract 内实际触发。
- `/research` 是新增路径，不重写 `/ask`。
- V5-A 四类 Delta 只保存 Candidate。

具体 Stage 数量和边界由 V5-A Session根据真实源码研究后起草，主 Session接受后冻结。

---

# 10. Explicit Non-goals

- 产品 Runtime、Test、Migration、Prompt、Tool Contract 或 UI 的首批实施。
- Provider 或付费服务运行。
- 上游正式依赖、代码复制或产品接入。
- 重写 Search、Fast、Deep、Evidence、Citation 或 AnswerFinalizer。
- 通用 Multi-Agent Platform、Agent Harness、MemoryOS 或 Eval SaaS。
- GraphRAG。
- 模型训练、RL 或参数更新。
- V5-B Topic Page、长期 Memory 或 Artifact Promotion。
- V5-C 个性化行为。
- V5-D Skill Promotion。
- 自动修改 Runtime、Verifier 或 Promotion Gate。
- V5-B/C/D Session 创建。
- Merge、Tag 或 Version Seal。

---

# 11. Stop Conditions

- Baseline 无法核验。
- Authority 文件冲突。
- Entry Gate 发生材料变化。
- 需要 Roadmap Reconsideration。
- 上游 License、数据或安全边界不明确。
- 首批研究要求产品实施、Migration、Provider 或付费服务。
- Stage 1 Contract 无法形成可验证的纵向结果。
- 上下文或任务范围扩张到无法有界审查。

首批完成后必须停止在：

```yaml
checkpoint:
  charter_status: draft_pending_main_review
  stage_1_contract_status: draft_pending_main_review
  product_implementation_started: false
  provider_runs_performed: false
  next_action: main_session_charter_and_stage_1_review
```
