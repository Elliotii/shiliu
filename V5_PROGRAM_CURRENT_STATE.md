# Shiliu V5 Program Current State

> Updated at: 2026-08-05T00:09:36+08:00
> Updated by: Shiliu V5 Main Codex Session
> Authority status: current

---

```yaml
resume_anchor:
  current_subversion: V5_B
  last_completed_subversion: V5_A
  last_completed_status: accepted_with_known_retrieval_limitation
  current_formal_stage: V5_B_STAGE_4_IMPLEMENTATION
  active_execution_session: 019fcb6c-0f37-70c3-be68-9d39f1b69112
  accepted_code_head: 04e5c5bbb94311a00f6efafa142908fd7b2b97de
  V5_B_startup_governance_head: b85340540cb92c2e46bfb8619598e7aa987171d4
  V5_B_accepted_startup_head: 4efaed413cb2fd9d2eeabe411da96f5132ce6276
  V5_B_accepted_stage_1_head: abe002ab95025b38565464e69ca8b3abe651f1ae
  V5_B_accepted_stage_2_contract_head: a931e2863f3ae245205c1f64bad7e45d25f03225
  V5_B_accepted_stage_2_head: f879c80c0f547195a40d6804b6057debd077d11a
  V5_B_accepted_stage_3_contract_head: 70ba2b2c22f642ac52ddce0d3d30184d3b3235d6
  V5_B_accepted_stage_3_head: 2d4d3397085dd9fe1b6d01533ce5743536b23740
  V5_B_accepted_stage_4_contract_head: 560293da5987478eea822197582beb3829dfa9ae
  branch: codex/v5-main
  pending_decision: V5_B_stage_4_implementation_submission
  next_action: V5_B_session_implements_lean_stage_4
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
    status: stage_3_accepted_stage_4_implementation_authorized
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
  V5_B_accepted_stage_3_head: 2d4d3397085dd9fe1b6d01533ce5743536b23740
  V5_B_accepted_stage_4_contract_head: 560293da5987478eea822197582beb3829dfa9ae
  V5_B_execution_schema_source: 13
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
  sync_runs: 382
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
  V5_B_STAGE_3:
    status: accepted
    capabilities:
      - bounded_artifact_and_independent_open_corpus_retrieval
      - fail_closed_direct_incremental_seed_route
      - exact_current_l1_citation_gated_direct_reuse
      - targeted_incremental_research_and_contribution_lineage
      - candidate_only_research_seed_and_safer_user_override
      - lean_append_only_route_aggregate_and_minimal_api_ui
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

V5-B Stage 3 实现 `2d4d339` 已通过有限验收。实现按用户的复杂度约束收敛为一张 append-only
ArtifactRoute 聚合表、一个独立 service、三个公共端点和六个风险导向 Case；没有建设第二套队列、
索引或工作台。主 Session 独立复跑 Stage 1–3 directed tests `23 passed`，live DB SHA-256 在窗口
前后均为 `1411d83e...`，仍为 schema 10、Stage 3 表为 0、integrity `ok`。Session 报告的
affected `160 passed` 和 default `1709 passed, 4 deselected`作为支持证据接受。

Stage 4 Contract `560293d` 已通过有限审查并授权同一 V5-B Session 实施。Contract 将 Explicit
Memory、inferred candidate、Current Focus/Knowledge Progress、Corpus soft prior 与
SystemExperienceRecord 收敛为一条 append-only/revisioned WorkspaceRecord 管线：默认一张 aggregate
table，只有具体 FK/query invariant 证明必要时才允许一张窄 supporting table；公共面限定为三类 API
与一个 Workspace surface，不拆 4A/4B，也不建设 MemoryOS、推断引擎、Corpus/Experience 平台、
vector memory、rules engine 或 background scheduler。

实施必须保持 authority 分离、append-only correction/tombstone、deterministic expiry 和 old-boundary
no-resurrection。所有 inferred/behavioral 内容先保持 candidate-only，Corpus 只是 versioned soft prior，
Experience 不升级 Skill/Policy；必须用 seeded-vs-empty Workspace 机械证明 Search/Ask/Research/
ArtifactRoute 行为不受影响。当前仍不授权 live migration、Stage 5、V5-C/D、push/merge/tag 或自我验收；
Provider 不构成机械验收前置，DeepSeek 等连续预算包预计不超过 2 美元时视为用户已默认授权，超过
2 美元前必须暂停请求确认。
