# Shiliu V5 Program Current State

> Updated at: 2026-08-04T15:58:11+08:00
> Updated by: Shiliu V5 Main Codex Session
> Authority status: current

---

```yaml
resume_anchor:
  current_subversion: V5_B
  last_completed_subversion: V5_A
  last_completed_status: accepted_with_known_retrieval_limitation
  current_formal_stage: V5_B_STAGE_2_CONTRACT
  active_execution_session: 019fcb6c-0f37-70c3-be68-9d39f1b69112
  accepted_code_head: 04e5c5bbb94311a00f6efafa142908fd7b2b97de
  V5_B_startup_governance_head: b85340540cb92c2e46bfb8619598e7aa987171d4
  V5_B_accepted_startup_head: 4efaed413cb2fd9d2eeabe411da96f5132ce6276
  V5_B_accepted_stage_1_head: abe002ab95025b38565464e69ca8b3abe651f1ae
  branch: codex/v5-main
  pending_decision: V5_B_stage_2_contract_review
  next_action: V5_B_session_prepares_compact_stage_2_contract
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
    status: stage_1_accepted_stage_2_contract_preparation
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
  V5_B_execution_schema_source: 11
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
  sync_runs: 373
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

V5-B Stage 1 已在 `abe002a` 通过有限验收：Candidate → current Evidence → Fact →
deterministic Artifact → first Topic Page → publish-or-return 的无 Provider 纵切成立，live DB
仍为 schema 10。下一步由同一 V5-B Session 起草精简 Stage 2 Contract，范围聚焦知识生命周期、
revalidation 和 durable refresh；在主 Session 接受前不开始 Stage 2 产品实施。

当前无技术阻塞，也无待用户决定的材料性路线问题。
