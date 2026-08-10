# Shiliu V5 Program Current State

> Updated at: 2026-08-10T17:07:14+08:00
> Updated by: Shiliu V5 Main Codex Session
> Authority status: current

---

```yaml
resume_anchor:
  current_subversion: V5_C
  last_completed_subversion: V5_B
  last_completed_status: accepted_with_known_limits
  current_formal_stage: V5_C_STAGE_5_implementation_and_closeout_preparation
  active_execution_session: V5_C_version_session
  accepted_code_head: 7d9af9009926c13cd94e149b9e54c87cdf2ffc9d
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
  V5_B_accepted_stage_5_head: 27c8c30d2704dcb3d0a792e53bfc96f2e1a1c930
  V5_B_mainline_merge_head: 7d9af9009926c13cd94e149b9e54c87cdf2ffc9d
  V5_C_startup_governance_head: 5fbe1641ecf52aa8d09c5f838d41a7d1bad7c084
  V5_C_accepted_startup_head: 2429debf9be426d825c6847e80030a537cc991a9
  V5_C_accepted_stage_1_head: 9e83ff078dee0ad038f012d197d812ff0e87a6f5
  V5_C_accepted_stage_2_contract_head: 20aca5b726c0c5585f5066e72778b30dcc2f32b5
  V5_C_accepted_stage_2_head: 95749a1d557dbbb51383b58821519e0524227566
  V5_C_accepted_stage_3_contract_head: 4368f39c90767f29ffb38efcafe4533be3aa816f
  V5_C_accepted_stage_3_head: 68e704e56bc0ba99de0506e9e2b93176b5c978a9
  V5_C_accepted_stage_4_contract_head: 55d8e403bd19049534ddb8b4a6078f0ed1e4b457
  V5_C_accepted_stage_4_head: b9a07004267b2131121d558f5343063e5293db24
  V5_C_accepted_stage_5_contract_head: 68419dd822d2a3531155b16d75c6ca06c0e72c1b
  branch: codex/v5-main
  pending_decision: V5_C_STAGE_5_implementation_and_version_closeout_acceptance
  next_action: V5_C_version_session_autonomously_implements_stage_5_and_submits_V5_C_FINAL_CLOSEOUT
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
    status: accepted_with_known_limits
  V5_C:
    goal: Personalized Research Agent
    status: stage_4_accepted_stage_5_implementation_authorized
  V5_D:
    goal: Controlled Experience-driven Search Policy Improvement
    status: not_started
  Post_V5:
    status: conditional_long_term_direction
```

长期路线与功能目标未改变。V5-B 的实际 schema、实现与版本内顺序已随 closeout 固定；
V5-C/D 的具体 Schema、框架、Commit、Goal 数量和版本内顺序仍未冻结，也没有提前实施。

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
  V5_B_accepted_stage_5_head: 27c8c30d2704dcb3d0a792e53bfc96f2e1a1c930
  V5_B_mainline_merge_head: 7d9af9009926c13cd94e149b9e54c87cdf2ffc9d
  V5_C_startup_governance_head: 5fbe1641ecf52aa8d09c5f838d41a7d1bad7c084
  V5_C_accepted_startup_head: 2429debf9be426d825c6847e80030a537cc991a9
  V5_C_accepted_stage_1_head: 9e83ff078dee0ad038f012d197d812ff0e87a6f5
  V5_C_accepted_stage_2_contract_head: 20aca5b726c0c5585f5066e72778b30dcc2f32b5
  V5_C_accepted_stage_2_head: 95749a1d557dbbb51383b58821519e0524227566
  V5_C_accepted_stage_3_contract_head: 4368f39c90767f29ffb38efcafe4533be3aa816f
  V5_C_accepted_stage_3_head: 68e704e56bc0ba99de0506e9e2b93176b5c978a9
  V5_C_accepted_stage_4_contract_head: 55d8e403bd19049534ddb8b4a6078f0ed1e4b457
  V5_C_accepted_stage_4_head: b9a07004267b2131121d558f5343063e5293db24
  V5_C_accepted_stage_5_contract_head: 68419dd822d2a3531155b16d75c6ca06c0e72c1b
  V5_C_execution_branch: codex/v5-c
  V5_C_execution_worktree: /Users/elliot/.codex/worktrees/3bf8/Shiliu
  V5_B_execution_schema_source: 14
  V5_B_execution_branch: codex/v5-b
  V5_B_execution_worktree: /Users/elliot/.codex/worktrees/ec16/Shiliu
  merge_conflicts: 0
  pushed: false
  tagged: false
live_runtime:
  database: /Users/elliot/Library/Application Support/Shiliu/shiliu.db
  schema: 14
  integrity_check: ok
  foreign_key_violations: 0
  videos: 157
  completed_videos: 140
  sync_runs: 438
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
  V5_B:
    status: accepted_with_known_limits
    capabilities:
      - evidence_backed_topic_page_and_l1_l2_l3_lineage
      - append_only_knowledge_lifecycle_and_durable_refresh
      - explainable_artifact_reuse_incremental_refresh_and_research_seed
      - typed_personal_corpus_workspace_and_experience_candidate
      - bounded_related_pages_feedback_and_durable_observability
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
  V5_B_STAGE_5:
    status: accepted
    capabilities:
      - integrated_reuse_first_and_research_change_product_paths
      - bounded_shared_current_fact_and_confirmed_conflict_page_navigation
      - current_fact_to_l1_citation_relation_drilldown
      - exact_target_advisory_feedback_event_and_command_receipt
      - derived_existing_record_observability
      - zero_schema_delta_and_stage_1_to_5_product_non_interference
```

# 4. Known limitations carried forward

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

```yaml
V5_B_known_limits:
  relations_are_per_task_not_corpus_wide_graph: true
  relation_projection_limit_per_page: 8
  large_real_corpus_relation_latency_proven: false
  multi_process_UI_polling_order_proven: false
  subjective_provider_product_comparison_exercised: false
  live_research_feedback_workspace_population: cold_start
  goal_met_despite_limits: true
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

V5-B 已以 `accepted_with_known_limits` 完成。产品代码通过 merge commit `7d9af900` 集成到
`codex/v5-main`；live SQLite 在验证过的 schema 10 备份和副本演练后迁移到 schema 14。
迁移前后 157 videos、140 completed videos、434 sync runs 与 0 research tasks 无漂移，
`integrity_check=ok`、FK violations 0。

Main Session 在合并后运行 Stage 1–5 与 Search/Ask/Web/API 关键兼容集合 108 项；V5-B
Session 提交的 full default no-provider `1721 passed, 4 deselected`继续作为版本级支持证据。
Web/sync 已恢复，`/`、`/search`、`/ask`、`/research` 和 Research Task list API 均返回 200，
HTTP smoke 窗口未改变 DB hash。完整证据和恢复路径见 `V5_B_FINAL_CLOSEOUT.md`。

V5-C Entry 的机械前提已具备，但 live Research/Feedback/Workspace 数据仍为 cold start。
用户已授权进入 startup/JIT planning，并采用一个持续 V5-C Version Session 主导完整子版本、
主 Session 仅做阶段边界有限验收的模型。启动现场确认 schema 14、integrity ok、FK 0，相关
live 业务记录均为 0；61 项无 Provider 定向测试通过，五个只读页面/API 为 200。

V5-C Session 已在 `codex/v5-c` 以 `2429debf` 提交 docs-only startup/JIT package。Main 有限审阅
接受 Version Charter、五 Stage 依赖序列、无材料性新上游研究的判断与 Stage 1 Contract。Stage 1
只实现一个无 Provider 的 Confirmed Personalized Answer Presentation 纵切：确认态 preference 可改变
Research limitations panel 的前后位置；答案、证据、引用、检索、Prompt、route、budget 与 Provider
不得变化。

同一个 V5-C Session 已以 `9e83ff078dee0ad038f012d197d812ff0e87a6f5` 完成 Stage 1，Main 有限验收正式接受 Confirmed Personalized
Answer Presentation：确认态 preference 可以且只能改变 Research limitations panel 的前后位置；
Feedback→Candidate 在创建和确认时均重新验证 receipt、同 Task、exact target/hash、key/value 与
principal。实现保持 schema/table/index/migration/dependency/Prompt/Provider/background worker 增量为
0，只新增一个只读 projection adapter，完整默认无 Provider 回归 `1725 passed, 4 deselected`；Main
独立复跑 Stage 1 + Workspace/Feedback 16 项 Python 和 2 项 Node 测试通过，live DB hash 不变。

Stage 1 不证明完整 Personalized Answer 或真实用户收益。Main 已有限审阅并接受 Stage 2 Contract
`20aca5b726c0c5585f5066e72778b30dcc2f32b5`：只允许 task-scoped、current、snapshot-bound 的
`corpus_observation` 对既有 Product Search candidate pool 做 deterministic bounded presentation
composition；原 query、mode、filters、planner 和 raw retrieval 独立运行，至少一半展示槽保留 open lane，
并保留最高 baseline corpus-nonmatching counterexample。Corpus prior 不获得 Citation、Verifier、事实或
hard-filter authority，缺失、不确定、冲突或 snapshot drift 时回到 baseline。

同一个 V5-C Session 已以 `95749a1d557dbbb51383b58821519e0524227566` 完成 Stage 2，Main 有限验收
正式接受 task-scoped Corpus-aware Search：原 Search raw plan/hits/candidate pool 不变，Corpus 只在展示
阶段做 bounded deterministic composition，并保留 open lane 与最高排名非匹配反例。实现保持零
schema/table/index/migration/dependency/Prompt/Provider/background worker/platform 增量，只新增一个只读
projection adapter。Session 报告完整默认 no-provider `1729 passed, 4 deselected`；Main 独立复跑
Stage 2/Search/Stage 1 风险集合 33 项通过，live DB hash 在测试窗口不变。

Main 已有限审阅并接受 Stage 3 Contract `4368f39c90767f29ffb38efcafe4533be3aa816f`：只允许在
现有 Research Task/Workspace surface 显示 task-scoped、advisory-only 的 Next path recommendation。
显式 current choice、request-local permission/cost 与 ArtifactRoute currentness/citation/open-lane/late-hash
Gate 始终优先；Profile/Corpus/Focus 不获得 route authority，Fast、Deep、Research 与 manual ASR 不得被
自动提交。当前英文 transcript cleanup 不是独立 Translation route。

同一个 V5-C Session 已以 `68e704e56bc0ba99de0506e9e2b93176b5c978a9` 完成 Stage 3，Main 有限验收
正式接受 task-scoped advisory Personalized Routing：confirmed preference 只影响推荐面板，显式选择、
permission/cost 与 ArtifactRoute authority fence 始终优先，CTA 不自动执行 Provider、Research、ArtifactRoute
或 ASR。实现保持零 schema/migration/dependency/Prompt/Provider/background worker/router-policy-platform
增量，只新增一个只读 projection。Session 报告完整默认 no-provider `1733 passed, 4 deselected`；Main
按优化后的纪律只复跑 Stage 1–3 定向矩阵 12 项，全部通过且 live DB hash 不变。

Main 已有限审阅并接受 Stage 4 Contract `55d8e403bd19049534ddb8b4a6078f0ed1e4b457`：Knowledge Progress、
Staleness、Collection Delta 与 bounded Early Project Radar 被收敛为一个 request-time、pull-only panel。
Mastery 只来自用户明确自述；活动只形成 observation；Delta 必须重验同 scope snapshot，Radar 最多一条且
必须绑定 confirmed Focus 与 current transcript/ASR Evidence。durable dismiss 复用 append-only Workspace，
同 boundary 不复活；无 scheduler、notification、rules、generic inbox、telemetry 或 agent loop。

同一个 V5-C Session 已以 `b9a07004267b2131121d558f5343063e5293db24` 完成 Stage 4，Main 有限验收
正式接受 pull-only Knowledge Progress and Bounded Assistance：显式 mastery 与 activity observation 分离，
Staleness/Delta/Radar 均按 persisted boundary fail closed，Radar 最多一条，durable dismiss 复用 exact
append-only Workspace control 并保持 no-resurrection。实现保持零 schema/migration/dependency/Prompt/Provider/
background platform 增量，只新增一个只读 projection 与 `mastered` enum 窄扩展。Session 报告 directed +
affected 31 项通过且按规则未跑完整套件；Main 只复跑 Stage 1–4 定向矩阵 16 项，全部通过且 live DB hash
不变。

Main 已有限审阅并接受 Stage 5 Contract `68419dd822d2a3531155b16d75c6ca06c0e72c1b`：最终 Stage 只新增
一个组合 Stage 1–4 context 的 Research Journey rail，以及一个窄的
`answer.presentation.detail_level=standard|compact` DOM presentation behavior。Compact 只折叠第二个及
之后的现有 answer blocks，不能截断、改写或重排 answer/Citation/Evidence；Prompt 与 Provider 增量为零。
Journey 不建 truth store、telemetry 或 eval platform，不预跑 Search 或自动执行任何路径。

现授权同一 V5-C Version Session 自主实施 Stage 5，并以单一 `V5_C_FINAL_CLOSEOUT.md` 同时提交 Stage 5
implementation 与 V5-C closeout 请求。Stage 5 必须运行一次完整 default no-provider suite 作为版本级证据，
并保持 cold/fixture/real-user evidence 分层。不授权 Provider、live DB、凭据、Program authority、mainline/live
migration、Push、Merge、Tag、V5-D 或 Post-V5；最终版本接受与集成仍由 Main 决定。
