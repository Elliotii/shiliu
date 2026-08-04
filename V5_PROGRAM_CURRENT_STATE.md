# Shiliu V5 Program Current State

> Updated at: 2026-08-04T22:55:49+08:00
> Updated by: Shiliu V5 Main Codex Session
> Authority status: current

---

```yaml
resume_anchor:
  current_subversion: V5_B
  last_completed_subversion: V5_A
  last_completed_status: accepted_with_known_retrieval_limitation
  current_formal_stage: V5_B_STAGE_3_IMPLEMENTATION
  active_execution_session: 019fcb6c-0f37-70c3-be68-9d39f1b69112
  accepted_code_head: 04e5c5bbb94311a00f6efafa142908fd7b2b97de
  V5_B_startup_governance_head: b85340540cb92c2e46bfb8619598e7aa987171d4
  V5_B_accepted_startup_head: 4efaed413cb2fd9d2eeabe411da96f5132ce6276
  V5_B_accepted_stage_1_head: abe002ab95025b38565464e69ca8b3abe651f1ae
  V5_B_accepted_stage_2_contract_head: a931e2863f3ae245205c1f64bad7e45d25f03225
  V5_B_accepted_stage_2_head: f879c80c0f547195a40d6804b6057debd077d11a
  V5_B_accepted_stage_3_contract_head: 70ba2b2c22f642ac52ddce0d3d30184d3b3235d6
  branch: codex/v5-main
  pending_decision: V5_B_stage_3_implementation_submission
  next_action: V5_B_session_implements_stage_3_under_accepted_contract
  roadmap_reconsideration_open: false
```

# 1. Program status

```yaml
program:
  V5_A:
    goal: Durable Recursive Research Runtime
    status: accepted_with_known_retrieval_limitation
  V5_B:
    goal: Evidence-backed Personal Knowledge and Corpus Workspace
    status: stage_2_accepted_stage_3_implementation_active
  V5_C:
    goal: Personalized Research Agent
    status: not_started
  V5_D:
    goal: Controlled Experience-driven Search Policy Improvement
    status: not_started
  Post_V5:
    status: conditional_long_term_direction
```

长期路线与功能目标未改变。V5-B/C/D 的具体 Schema、框架、Commit、Goal 数量和版本内
顺序仍未冻结，也没有提前实施。

# 2. Repository and runtime

```yaml
repository:
  root: /Users/elliot/new-systems/agent-job-prep/Shiliu
  branch: codex/v5-main
  V5_A_fast_forward_head: 04e5c5bbb94311a00f6efafa142908fd7b2b97de
  V5_B_startup_governance_head: b85340540cb92c2e46bfb8619598e7aa987171d4
  V5_B_accepted_startup_head: 4efaed413cb2fd9d2eeabe411da96f5132ce6276
  V5_B_accepted_stage_1_head: abe002ab95025b38565464e69ca8b3abe651f1ae
  V5_B_accepted_stage_2_contract_head: a931e2863f3ae245205c1f64bad7e45d25f03225
  V5_B_accepted_stage_2_head: f879c80c0f547195a40d6804b6057debd077d11a
  V5_B_accepted_stage_3_contract_head: 70ba2b2c22f642ac52ddce0d3d30184d3b3235d6
  V5_B_execution_schema_source: 12
  V5_B_execution_branch: codex/v5-b
  V5_B_execution_worktree: /Users/elliot/.codex/worktrees/ec16/Shiliu
  merge_conflicts: 0
  pushed: false
  tagged: false
live_runtime:
  database: /Users/elliot/Library/Application Support/Shiliu/shiliu.db
  schema: 10
  integrity_check: ok
  foreign_key_violations: 0
  videos: 157
  completed_videos: 140
  sync_runs: 376
  research_tasks: 0
  web_launch_agent: running
  scheduled_sync_launch_agent: loaded
```

Gate C 的两份可恢复 schema 9 备份、迁移指纹、测试和 HTTP smoke 记录见
`V5_A_GATE_C_AND_CLOSEOUT_REPORT.md`。

# 3. Accepted technical baseline

```yaml
accepted_results:
  V4:
    status: complete
    capabilities:
      - /search
      - fast_grounded_answer
      - deep_grounded_answer
      - shared_grounding_and_stable_citation
  V4_1:
    status: partial_closed_and_archived
    harness_is_product_runtime: false
  V5_A:
    status: accepted_with_known_retrieval_limitation
    capabilities:
      - durable_task_goal_attempt_checkpoint_result
      - ownership_lease_epoch_and_idempotent_commands
      - fail_closed_external_side_effects
      - evidence_backed_inner_research
      - outer_constraint_audit_and_targeted_continuation
      - hitl_interrupt_resume_cancel_and_input_control
      - durable_trace_product_page_and_api
      - provider_receipt_usage_cost_and_honest_stop
  V5_B_STAGE_1:
    status: accepted
    capabilities:
      - durable_knowledge_candidate_intake_and_review
      - server_current_evidence_gated_fact_promotion
      - immutable_initial_fact_artifact_and_topic_page_revisions
      - synchronous_durable_deterministic_build_runs
      - publish_or_return_page_review
      - transcript_citation_drilldown
  V5_B_STAGE_2:
    status: accepted
    capabilities:
      - append_only_evidence_revalidation_and_visible_staleness
      - explicit_fact_correction_retire_supersede_and_conflict_lineage
      - immutable_artifact_and_topic_page_revision_lifecycle
      - durable_refresh_recovery_retry_dead_letter_and_late_result_fence
      - revision_hash_addressed_export_with_observable_safe_retry
      - minimal_lifecycle_api_and_ui
```

# 4. Known limitation carried forward

V5-A 没有证明任意长复合查询都能完成 grounded answer。最终代表性 smoke 在 dense
model not ready 时降级到 lexical 并得到 0 个命中，因此 EvidenceUse/citation 为 0。
主 Session 将此接受为明确的检索边界，而不是继续扩大 V5-A 的 bounded rework。

```yaml
known_retrieval_limitation:
  durable_runtime_regression: false
  representative_grounded_completion_proven: false
  candidate_future_owners:
    - V5_C
    - V5_D
  must_not_be_reported_as_success: true
```

# 5. Governance and upstream boundary

```yaml
session_limits:
  active_subversion_limit: 1
  active_formal_stage_or_goal_limit: 1
current_usage:
  active_subversions: 1
  active_formal_stages: 1
upstream:
  deer_flow:
    adoption: pattern_only_reimplementation
    dependency_or_source_copy: false
  arex:
    adoption: training_independent_patterns_only
    model_weight_prompt_or_code_adopted: false
  youtu_agent:
    status: deferred
  V5_B_JIT_research:
    DeepTutor: adopted_reference_only_at_44fa7a1
    WeKnora: adopted_reference_only_at_fcc4cd6
download_equals_adoption: false
research_equals_implementation_authorization: false
```

# 6. Next action boundary

V5-B Stage 3 Contract `70ba2b2` 已通过主 Session 的目标、authority、依赖顺序与 Gates A-E
有限审阅。现有 fixed-commit DeepTutor/WeKnora 报告和本地 Stage 2 实现足以支持本 Stage；没有
为了装饰 Contract 而新增上游研究、依赖或 Provider 语义。

同一 V5-B Session 已获准自主实施独立 Artifact/open-corpus 双 lane 检索，以及
`direct reuse | incremental refresh | research seed` 三路 durable、可解释、fail-closed 判定。
direct reuse 必须 exact/complete/current；incremental 只覆盖可隔离的小缺口；否则走 seed。
旧 Artifact 永远不是 verifier，用户只能选择更保守路线，不能强制绕过 Gate。普通 projection、
fixture、harness 与低风险实现错误继续由 V5-B Session 自行修复和有界复跑。

当前不授权 live DB migration、Stage 4/5、V5-C/D、通用 vector/graph/memory 平台、push/merge/tag
或自我验收。Provider 不是 Stage 3 mechanical acceptance 前提；若确有必要，DeepSeek 等连续预算包
预计不超过 2 美元时视为用户已默认授权，超过 2 美元前必须暂停请求确认。
