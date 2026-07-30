# Shiliu V5 Program Current State

> Updated at: 2026-07-31T02:21:31+08:00
> Updated by: Shiliu V5 Main Codex Session
> Authority status: current

---

```yaml
resume_anchor:
  current_subversion: V5_A
  current_stage: V5_A_STAGE_2_CONTRACT_PREPARATION
  accepted_commit: cbfc7d1c571a2e2935df33c07cec94dd5f87ac78
  active_execution_session: 019fb35a-d022-7a32-b963-3327adda8135
  pending_decision: none
  next_action: V5_A_session_prepares_stage_2_contract
  roadmap_reconsideration_open: false
```

---

# 1. Repository

```yaml
repository:
  root: /Users/elliot/new-systems/agent-job-prep/Shiliu
  branch: codex/v5-main
  starting_product_baseline: 483fd46bca1d7141a696fda4b2d1e093a55f209b
  head_before_governance_baseline: 483fd46bca1d7141a696fda4b2d1e093a55f209b
  governance_baseline: commit_containing_this_record
  working_tree_at_live_audit:
    tracked: clean
    untracked:
      - 拾流_V5主Codex交接包_2026-07-30/
  remote:
    name: origin
    url: https://github.com/Elliotii/shiliu.git
    audited_starting_branch: origin/codex/v4.1-hardening
    audited_ahead: 0
    audited_behind: 0
  tags:
    v4: absent
    v4_1: absent
    historical_checkpoint_tags_present: 7
```

---

# 2. Program Status

```yaml
program:
  V5_A: active
  V5_B: not_started
  V5_C: not_started
  V5_D: not_started
  post_V5: conditional_long_term_direction
```

---

# 3. Current Subversion

```yaml
current:
  charter:
    path: V5_A_VERSION_CHARTER.md
    status: accepted
  stage_contract:
    path: V5_A_STAGE_1_CONTRACT.md
    status: fulfilled_and_accepted
  main_review:
    path: V5_A_STAGE_1_MAIN_SESSION_ACCEPTANCE_DECISION.md
    decision: accept
  execution_session:
    role: Shiliu V5-A Version Session
    thread_id: 019fb35a-d022-7a32-b963-3327adda8135
    execution_branch: codex/v5-a
    worktree: /Users/elliot/.codex/worktrees/3324/Shiliu
    assignment: V5_A_STAGE_2_contract_preparation_only
  baseline: cbfc7d1c571a2e2935df33c07cec94dd5f87ac78
  startup_report_accepted: true
  stage_1_implementation_started: true
  stage_1_status: accepted
  stage_1_report_pending: false
```

V5-A Stage 1 已完成一轮有界返工并由主 Session 正式接受。唯一活跃的 V5-A
子版本 Session 继续主导该子版本；当前只进入 Stage 2 Contract 与
Just-in-time 实施计划准备，不开始 Stage 2 产品实施。

---

# 4. Accepted Results

```yaml
accepted_results:
  V4:
    status: complete
    commit: cbf264be2571c3d62775c064445de8a1ba17880a
    capabilities:
      - /search
      - fast_grounded_answer
      - deep_grounded_answer
      - shared_grounding_and_stable_citation
  V4_1:
    status: partial_closed_and_archived
    archive_commit: 483fd46bca1d7141a696fda4b2d1e093a55f209b
    provider_configuration_changed: false
    known_provider_failure_proves_algorithm_regression: false
  V5_A_STAGE_1:
    status: accepted
    accepted_baseline: cbfc7d1c571a2e2935df33c07cec94dd5f87ac78
    implementation_commit: c8a3f9f054b6793dade3e353fbf61fd8a583ec06
    bounded_rework_commit: ecbea72b483487a4a64d46d286719e89d024e22f
    acceptance_record: V5_A_STAGE_1_MAIN_SESSION_ACCEPTANCE_DECISION.md
    capabilities:
      - durable_research_task_kernel
      - schema_7_source_and_temporary_database_migration_tests
      - ownership_lease_and_epoch_fence
      - command_receipt_and_payload_deduplication
      - task_scoped_side_effect_protocol
      - checkpoint_restart_and_lineage
      - minimal_research_JSON_API
```

---

# 5. Current Blockers

- 技术阻塞：无。
- Stage 2 Contract 尚未起草或接受；Stage 2 产品实施尚未授权。
- Provider 与 live DB Migration 仍未授权。

---

# 6. Upstream State Relevant Now

```yaml
V5_A_candidates:
  deer_flow:
    local_status: absent
    adoption_status: adopted
    adoption_type: pattern_only_reimplementation
    usage_level: design_reference
    stage_1_selected_patterns_implementation_authorized: true
    dependency_or_source_copy_authorized: false
  arex_paper:
    local_status: absent
    adoption_status: adopted
    adoption_type: training_independent_patterns_only
    usage_level: design_reference
    stage_1_implementation_authorized: false
    implementation_authorized: false
  youtu_agent:
    local_status: absent
    adoption_status: deferred
    implementation_authorized: false
historical_non_registry_reference:
  bilibili_cli:
    local_status: full_clone
    path: references/upstreams/bilibili-cli
    commit: dbe28551930df43b633baa52e9639832aeada967
    license: Apache-2.0
    working_tree: clean
```

Registry 的正式仓库存在性口径仍为 `absent`；V5-A 使用的临时有界研究 checkout 不进入产品树，也不构成依赖或源码采用。

---

# 7. Known Evidence Gaps

- DeerFlow 已完成固定 Commit 的有界源码/相关失败测试审阅，但上游测试未执行。
- AREX 已完成论文 v2 与官方最小推理仓库审阅；完整 outer loop、训练管线和测试不可由当前公开仓库复现。
- V5-A Version Charter 已接受；Stage 1 Contract 已履行并验收。
- Stage 1 已在临时 SQLite、进程重开、线程竞争和故障注入层面机械验证 ownership、
  unknown in-flight 和 child Task lineage；真实断电、长时间多进程/多主机 lease
  soak、真实 external SideEffect reconciliation 与 live schema 7 upgrade 仍为
  `unproven` 或 `not_exercised`。
- 本轮没有运行 Provider；V4.1 已归档的 Cross-video Provider Failure 不重跑、不改判。
- V4/V4.1 Commit 尚未合入本地 `main`，也没有 V4/V4.1 Tag；这是现场 Git 事实，不是产品回归。

---

# 8. V4/V4.1 Live Audit

```yaml
v4_v4_1_live_audit:
  audited_at: 2026-07-30
  repository_root: /Users/elliot/new-systems/agent-job-prep/Shiliu
  branch_at_audit: codex/v4.1-hardening
  governance_branch_created_after_audit: codex/v5-main
  head: 483fd46bca1d7141a696fda4b2d1e093a55f209b
  working_tree:
    tracked: clean
    untracked_handoff_package_only: true
  v4_commit_present: true
  v4_commit: cbf264be2571c3d62775c064445de8a1ba17880a
  v4_1_archive_commit_present: true
  v4_1_archive_commit: 483fd46bca1d7141a696fda4b2d1e093a55f209b
  merge_status:
    v4_merged_to_local_main: false
    v4_1_merged_to_local_main: false
    audited_branch_synced_with_remote: true
  tags:
    v4_or_v4_1_tag_present: false
  core_paths_present:
    result: true
    checked: 41
    missing: 0
  authoritative_files_present: true
  live_data:
    database_path: /Users/elliot/Library/Application Support/Shiliu/shiliu.db
    database_schema_version: 6
    database_size: 96M
    tables: 30
    videos: 157
    completed_videos: 140
    retrieval_search_traces: 145
    retrieval_search_presentations: 115
    content_video_directories: 155
    distinct_nonempty_artifact_directories_in_database: 155
    ask_or_research_task_persistence_tables_present: false
  runtime_boundary:
    ask_trace_storage: in_process_memory
    langgraph_product_checkpointer: none
    durable_research_task: absent
    product_HITL: absent
    V5_memory: absent
    cross_run_research_artifact_reuse: absent
  test_environment:
    python: 3.12.13
    pytest: 8.4.2
    langgraph: 1.2.10
    node: 24.15.0
    pip_check: passed
    directed_v4_v4_1: 68_passed
    default_non_provider_suite: 1498_passed_4_deselected
    javascript_syntax_checks: passed
    git_diff_check: passed
    warnings:
      - StarletteDeprecationWarning_from_test_dependency
  local_references:
    nested_git_repositories:
      - references/upstreams/bilibili-cli
    v5_registry_resources_present: 0
    v5_registry_resources_absent: 27
  provider_runs_authorized: false
  provider_runs_performed: false
  material_differences_from_handoff: []
```

---

# 9. Next Authorized Action

由唯一活跃的 V5-A 子版本 Session 基于已接受的 Stage 1 baseline 准备 Stage 2
Contract 和 Just-in-time 实施计划。V5-A 自主负责 Stage 2 的具体技术设计与拆分；
主 Session 只在正式边界进行轻量目标、证据和授权审阅。

当前允许只读源码核验、必要的有界研究和无 Provider 探索性机械测试；禁止 Stage 2
产品实施、Provider、live DB Migration、凭据访问、Push/Merge/Tag 和自我验收。
