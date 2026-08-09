# Shiliu V5 Program Current State

> Updated at: 2026-08-09T15:49:03+08:00
> Updated by: Shiliu V5 Main Codex Session
> Authority status: current

---

```yaml
resume_anchor:
  current_subversion: V5_B
  last_completed_subversion: V5_A
  last_completed_status: accepted_with_known_retrieval_limitation
  current_formal_stage: V5_B_STAGE_5_IMPLEMENTATION
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
  V5_B_accepted_stage_4_head: ccfd8d9729eb5093ded5d397e5d5fd942fdab755
  V5_B_accepted_stage_5_contract_head: 5b7c96ca277fb303a4307e7a25b8f136c3d68ca1
  branch: codex/v5-main
  pending_decision: V5_B_stage_5_implementation_and_closeout_submission
  next_action: V5_B_session_implements_lean_stage_5_and_prepares_closeout_report
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
    status: stage_4_accepted_stage_5_implementation_authorized
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
  V5_B_accepted_stage_4_head: ccfd8d9729eb5093ded5d397e5d5fd942fdab755
  V5_B_accepted_stage_5_contract_head: 5b7c96ca277fb303a4307e7a25b8f136c3d68ca1
  V5_B_execution_schema_source: 14
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
  V5_B_STAGE_4:
    status: accepted
    capabilities:
      - typed_explicit_inferred_focus_progress_corpus_and_experience_records
      - append_only_decision_revision_expiry_and_tombstone
      - old_source_boundary_no_resurrection
      - frozen_corpus_snapshot_soft_prior
      - trace_result_lineage_experience_candidate_without_skill_mutation
      - product_behavior_non_interference_and_compact_workspace_ui
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

V5-B Stage 4 实现 `ccfd8d9` 已通过有限验收。实现按 Contract 收敛为一张 immutable
`research_workspace_records` aggregate、零 supporting table、一个 service、三类公共 API 和一个
Workspace surface；没有 scheduler、queue、inference/vector/rules engine 或平台拆分。Explicit Memory、
inferred/focus/progress、Corpus soft prior 与 System Experience 保持独立 authority；correction/decision/
expiry/tombstone 是 append-only revision，old source boundary replay 不复活 terminal lineage，Experience
不生成 Skill/Policy。

主 Session 独立复跑 Stage 1–4 directed tests `29 passed`，Python compile、JavaScript syntax、JSONL 与
whitespace 检查通过；live DB SHA-256 在测试窗口前后均为
`e6dd58b4fd115b4768694c0de4f9e84cb1cc62f12cfc228f39c5e06705c6740f`。Session 报告的 affected
`179 passed`、Search/Ask/API `56 passed` 与 default `1715 passed, 4 deselected`作为支持证据接受。

Stage 5 Contract `5b7c96c` 已通过有限审查并授权同一 V5-B Session 实施。现有
PageRevision→FactRevision、Fact current state 与 immutable `confirmed_conflict` observation 足以派生
`shared_current_fact` 和 `confirmed_conflict` 两类 navigation-only relation；Feedback 复用 Event 与
CommandReceipt。默认零新表，最多一张由具体 invariant 证明的窄 supporting table；最多一个 composition
adapter、两类 endpoint 和一个既有 Workspace surface 扩展，不建设 GraphRAG、通用 graph/eval/telemetry
平台、第二套 runtime、queue 或 scheduler。

Stage 5 必须完成 reuse-first 与 research-change 两条路径、minimal Feedback、derived observability、
cross-Stage fault/restart/compatibility 和 V5-B closeout evidence。Mechanical Gate 完全 no-provider；只有在
机械闭环通过且能回答具体产品问题时，V5-B Session 才可选择运行已冻结的 4–6 case DeepSeek 对照，连续
总预算不超过 USD 2，且结果始终 non-gating。当前仍不授权 live migration、merge/tag、自我验收或启动
V5-C/V5-D；这些属于 Stage 5 被接受后的 Main-owned version closeout。
