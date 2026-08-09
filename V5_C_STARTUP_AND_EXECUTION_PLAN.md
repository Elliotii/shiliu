# Shiliu V5-C Startup and Execution Plan

> Prepared by: Shiliu V5 Main Codex Session
> User decision: startup_execution_authorized
> Plan status: active_startup
> Product implementation authorized: false
> V5-C Version Session creation authorized: true
> V5-C Charter created: false

---

# 1. Version objective

V5-C 的正式目标是：

> 让 V5-B 中经过确认、可修正的用户状态、收藏库模型和知识资产，以可解释、
> 可关闭、可回滚的方式真实影响拾流的回答、搜索、路径选择和有限主动帮助。

主产品形态：

```text
Personalized Research Agent
```

目标用户闭环：

```text
Explicit Input / Feedback
→ Candidate Preference or Current Focus
→ User Confirmation
→ Versioned Profile
→ Personalized Answer / Corpus-aware Search / Route Recommendation
→ Explain, Correct, Disable or Roll Back
→ Progress / Staleness / Collection Delta Assistance
```

V5-B 让知识和用户状态可以长期存在；V5-C 让这些受控状态开始改变产品行为。

# 2. Starting baseline

```yaml
starting_baseline:
  repository_branch: codex/v5-main
  repository_head: 7cb5a8c0a716900e073aa519efe289dfe887531a
  working_tree_at_planning: clean
  live_schema: 14
  V5_A_status: accepted_with_known_retrieval_limitation
  V5_B_status: accepted_with_known_limits
  V5_C_status: startup_planning_active
  active_subversion: V5_C
  V5_C_entry_mechanics: satisfied
  live_personalization_inputs: cold_start
```

现场核验：

```yaml
live_runtime:
  integrity_check: ok
  foreign_key_violations: 0
  videos: 157
  completed_videos: 140
  sync_runs: 435
  active_sync_runs: 0
  research_tasks: 0
  research_events: 0
  workspace_records: 0
  artifact_routes: 0
  topic_pages: 0
  feedback_events: 0
  web_launch_agent: running
  scheduled_sync_launch_agent: running
  readonly_http_smoke: 5_of_5_200
startup_directed_tests:
  selected: 61
  passed: 61
  failed: 0
  provider_runs: 0
  live_database_hash_unchanged: true
```

V5-C 的机械入口已经具备：Artifact reuse、Feedback Event、可确认/修正的 Workspace
记录、可读取的 Corpus soft prior，以及多条实际产品路径均已存在。真实 Research、Feedback、
Workspace 数据尚未积累。这不阻止启动和确定性实现，但禁止把 fixture 或设计假设写成真实
个性化收益。

# 3. Explicit non-goals

V5-C 不负责：

- 将搜索经验晋升为 Active Skill 或自动修改 Search Policy；这些属于 V5-D；
- 模型训练、微调、RL、开放式自进化或自动修改 Prompt/Verifier；
- 通用 MemoryOS、社交画像、心理推断、广告画像或跨用户数据平台；
- 将收藏、搜索、观看、停留时间直接等同为掌握、偏好或长期事实；
- 用 Corpus prior 排除开放搜索、反例或较低排名证据；
- 让 Profile、Memory、Topic Page 或 Artifact 取得 Citation/Verifier 权威；
- 为主动帮助先建设通用 scheduler、notification、rules 或 agent platform；
- 默认建设 corpus-wide GraphRAG；
- 自动把 V5-A 的复合查询召回限制升级为 V5-C Backlog；
- 提前实施 V5-D 或 Post-V5 Full Project Radar。

# 4. V5-A/V5-B lessons applied

## 4.1 One Version Session owns V5-C

```text
V5 Main Session
→ one persistent V5-C Version Session
→ optional bounded specialist Sessions
```

V5-C Session 主导版本内部研究、Stage 设计、实现、普通 Bug 修复、测试和集成。主 Session
只审阅 Charter/Stage 目标边界、进行有限阶段验收，并负责 mainline、live migration 和版本收口。

## 4.2 Prefer vertical user-visible slices

首个正式 Stage 应尽早证明至少一条完整且低风险的个性化闭环，而不是先建设宽泛 Profile、
Memory、Rules 和 Telemetry 平台。优先考虑：

```text
explicit preference
→ confirmation
→ versioned profile
→ one visible product effect
→ explanation / disable / rollback
```

具体效果由 V5-C Session 在审计后定约，不能在 Charter 前先实现。

## 4.3 Cold start is an evaluation boundary

- 早期机械测试允许使用确定性 fixture；
- fixture 不得进入 live DB，也不得冒充用户历史；
- 隐式或行为信号默认只能形成 Candidate；
- 没有 confirmed profile 时必须退回非个性化基线；
- 版本报告必须区分 mechanical correctness、paired fixture benefit、real-user signal 和 unproven；
- 版本收口前应规划最小真实产品旅程，但不得为了制造数据运行未授权 Provider。

## 4.4 Personalization must be paired and reversible

每个正式个性化行为至少证明：

1. no-profile baseline；
2. confirmed-profile treatment；
3. disabled/rolled-back behavior 回到 baseline；
4. 不相关偏好不造成行为变化；
5. Corpus prior 不抑制开放搜索和反例；
6. 触发原因和使用的 Profile/Corpus 版本可解释。

## 4.5 Avoid governance and architecture inflation

- 默认不拆 1A/1B 或 Gate A/B/C；
- 普通返工进入同一 Stage Report 或 Git 历史；
- 不为每个个性化维度建设独立 service/table；
- 优先复用 V5-B WorkspaceRecord、Feedback、Event/Receipt、ArtifactRoute 与现有产品路径；
- 只有新 invariant 无法由现有结构表达时才新增持久对象；
- Provider Eval、live migration 和 mainline integration 保持独立授权边界。

# 5. Session and authority model

```yaml
main_session:
  owns:
    - startup_boundary
    - stage_acceptance
    - program_state
    - mainline_merge
    - live_migration
    - version_closeout
  implements_product: false

V5_C_session:
  owns:
    - live_code_reconnaissance
    - JIT_research
    - charter_draft
    - stage_design
    - implementation
    - ordinary_bug_fixes
    - tests_and_eval
    - stage_integration
  may_formally_accept_own_stage: false
  may_start_V5_D: false

specialist_sessions:
  optional: true
  report_to: V5_C_session
  create_second_acceptance_line: false

concurrency:
  active_subversion_limit: 1
  active_formal_stage_or_goal_limit: 1
```

普通 projection、fixture、UI、test harness 和低风险实现错误由 V5-C Session 在当前
Contract 内自主修复和有界复跑。只有材料性产品取舍、路线改变、显著费用、高风险 License/
Data 边界或破坏性操作才升级。

# 6. Phase 0 — Startup and JIT planning

Owner: V5-C Version Session.

执行：

1. 核对分支、HEAD、工作树和 V5-B accepted baseline；
2. 审阅 WorkspaceRecord、Feedback、ArtifactRoute、Fast/Deep/Research path 和产品 UI/API；
3. 映射每类 personalization input、authority、consumer、explanation 和 rollback；
4. 验证 cold-start、no-profile 和 seeded fixture 的非干扰边界；
5. 先阅读 Registry、本地研究备忘录和既有 fixed-commit 报告；
6. 只在本地证据不足以定约时开展材料性的 JIT 外部研究；
7. 形成精简 Version Charter、Stage 序列、Stage 1 Contract、Current State 和 Ledger；
8. 提交一个 startup report 请求主 Session 有限审阅。

本 Phase 不实施产品、不迁移 live DB、不调用 Provider、不访问凭据。

# 7. JIT research policy

V5-C 当前 Registry 的优先输入是：

- `local_memo_self_evolution`：只用于 Trace/Experience/Feedback 与 authority 分离；
- `survey_what_when_how_self_evolving`：只用于 retention/generalization/regression 检查表；
- V5-B 的 DeepTutor/WeKnora fixed-commit 报告和本地实现证据；
- 当前 Shiliu WorkspaceRecord、Feedback、Search/Ask/Research/ArtifactRoute 源码与测试。

这些输入不直接导出 V5-C 架构。若 Version Session 判断需要新的外部项目，必须先说明具体
缺口，再完成官方来源、固定 Commit、License、相关源码/测试和 adopt/reimplement/reject
结论。不得为了“有上游报告”而下载或研究项目；不得批量下载；研究不等于采用或实施授权。

# 8. Recommended lean stage envelope

下列是启动约束，不是冻结实现：

## Stage 1 — Confirmed personalization vertical slice

- Structured Feedback/Candidate Preference；
- user-confirmed versioned profile/current focus；
- reject/correct/expire/disable/rollback；
- 一个可见、可解释、低风险的 personalized product effect；
- no-profile、unconfirmed、unrelated 和 rollback paired tests。

## Stage 2 — Corpus-aware search

- Folder semantics、topic aliases、uploader/series/source availability 等作为 soft prior；
- 独立 open-corpus lane 和 counterexample discovery 保留；
- 不以 Corpus Model 充当 Citation、Verifier 或 hard filter；
- paired baseline/treatment、narrowing 和 negative-case 测试。

## Stage 3 — Personalized route recommendation

- 在真实存在的 Artifact/Fast/Deep/Research/ASR-Translation 路径间给出可解释建议；
- 用户可覆盖，预算/新鲜度/证据覆盖和权限边界保持有效；
- 冷启动或不确定时保持现有显式选择，不自动升级高成本路径。

## Stage 4 — Progress and bounded proactive assistance

- Current Focus、Knowledge Progress、staleness、collection delta；
- Early Project Radar 仅为有证据、用户可见、可关闭的候选提醒；
- 不建设无人值守的通用后台 Agent；
- 触发原因、频率、dismiss/rollback 和 no-resurrection 可验证。

## Stage 5 — Product completion and evaluation

- 完整用户旅程和跨路径 non-interference；
- baseline/treatment/rollback 机械矩阵；
- cold-start 与真实用户信号分层报告；
- 必要时再提出一个冻结、低预算 Provider 产品比较，不作为机械 Gate。

V5-C Session 可以合并或调整 Stage，但不能删除 Personalized Answer、Corpus-aware Search、
Personalized Routing、Current Focus/Progress、Collection Delta、Staleness、Early Project Radar、
用户确认和 Rollback 等长期功能目标。

# 9. Compact artifacts

默认只维护：

```text
V5_C_VERSION_CHARTER.md
V5_C_CURRENT_STATE.md
V5_C_DECISION_LEDGER.md
V5_C_STAGE_N_CONTRACT.md
V5_C_STAGE_N_IMPLEMENTATION_REPORT.md
V5_C_FINAL_CLOSEOUT.md
```

启动阶段另有：

```text
V5_C_STARTUP_REPORT.md
```

只有材料性 JIT 研究才新增 `V5_C_UPSTREAM_*_RESEARCH_REPORT.md`。

# 10. Startup authorization boundary

当前授权：

```yaml
authorized:
  - read_only_live_repository_and_database_audit
  - local_source_and_test_review
  - bounded_JIT_research
  - temporary_database_no_provider_tests
  - V5_C_charter_and_stage_1_contract
  - compact_V5_C_state_and_ledger
  - commit_docs_to_V5_C_execution_branch
```

当前不授权：

```yaml
not_authorized:
  - product_implementation
  - provider_or_paid_service_runs
  - credential_or_keychain_access
  - live_database_migration
  - bulk_upstream_download
  - dependency_or_source_copy
  - V5_D_or_Post_V5_implementation
  - mainline_merge
  - push_or_tag
  - self_acceptance
```

Startup Report 只请求 Charter、Stage 序列、Stage 1 Contract、材料性上游 adoption proposal
和 Stage 1 实施授权。
