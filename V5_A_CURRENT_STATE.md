# 拾流 V5-A Current State

> Updated at: 2026-08-04T13:48:28+08:00
> Updated by: Shiliu V5 Main Codex Session
> Authority: final main-session acceptance snapshot

---

```yaml
version: V5_A
goal: Durable Recursive Research Runtime
status: accepted_with_known_retrieval_limitation
formal_acceptance_authority: V5_main_session
source_branch: codex/v5-a
mainline_branch: codex/v5-main
mainline_code_head: 04e5c5bbb94311a00f6efafa142908fd7b2b97de
product_implementation_complete: true
gate_C_complete: true
active_formal_stage: none
next_program_action: prepare_V5_B_startup_plan_and_entry_audit
```

# 1. Stage disposition

```yaml
stages:
  stage_1_durable_task_kernel_and_safety: accepted
  stage_2_evidence_backed_inner_research: accepted
  stage_3_outer_goal_audit_and_recursive_continuation: accepted
  stage_4_hitl_and_operational_control: accepted
  stage_5_gate_A_mechanical_product_completion: accepted
  stage_5_gate_B_provider_evaluation: partial_accept_with_known_retrieval_limitation
  stage_5_gate_C_mainline_and_live_migration: passed
```

V5-A 已交付 durable Task/Goal/Attempt/Checkpoint/Result、owner lease/epoch fence、
CommandReceipt、SideEffect fail-closed、EvidenceUse/currentness、inner research、
outer constraint audit、targeted continuation、HITL/control、派生 lineage，以及可观察、
可恢复的 Research 产品页面和 API。

# 2. Gate B final boundary

Gate B 的真实运行证据保留并接受 Provider identity、receipt/usage/cost、hard cap、
故障分类和 honest stop。后续修复已把 receipt-bound Deep 输出接入 durable
artifact/checkpoint/audit/Result 或 current InputRequest 路径，并把首次空导航有界地转为
一次 global transcript search。

最终 grounded smoke 对一个代表性长复合查询仍得到 0 个检索命中；规划为 hybrid，
执行时因 dense local model not ready 降级为 lexical，因此没有 EvidenceUse/citation，
也没有证明 grounded completion。该事实不是 durable runtime 回归，不再触发 V5-A
返工循环。

```yaml
gate_B:
  durable_runtime_and_provider_accounting: accepted
  honest_failure_and_stop_semantics: accepted
  representative_grounded_completion: unproven
  known_limitation_owner:
    - V5_C_personalized_research_agent
    - V5_D_search_policy_improvement
  no_false_success_claim: true
```

# 3. Gate C evidence

```yaml
integration:
  method: fast_forward
  from: codex/v5-a
  into: codex/v5-main
  merged_code_head: 04e5c5bbb94311a00f6efafa142908fd7b2b97de
  conflicts: 0
live_migration:
  database: /Users/elliot/Library/Application Support/Shiliu/shiliu.db
  before_schema: 9
  after_schema: 10
  integrity_check: ok
  foreign_key_violations: 0
  videos_before_after: 157
  completed_videos_before_after: 140
  sync_runs_before_after: 373
  research_tasks_before_after: 0
  source_schema_10_control_generation_column: present
  source_schema_10_stage_4_tables: 8
backups:
  manual:
    path: /Users/elliot/Library/Application Support/Shiliu/backups/shiliu.gate-c-pre-v10-20260804T134024+0800.db
    schema: 9
    integrity_check: ok
    sha256: 8c31308dd03f63aa96afdb797e71d19ea1bdcdfd17d66b6953833aebc74aeb96
  automatic:
    path: /Users/elliot/Library/Application Support/Shiliu/shiliu.pre-v10.backup.db
    schema: 9
    integrity_check: ok
    sha256: 76f595c4fb1efe4a43594f51460f82de35086a784ca055a7e51f9eafff4e9ee8
verification:
  default_no_provider_suite: 1686_passed
  deselected_external_or_live_provider: 4
  warnings: 7_deprecation_only
  research_page_http: 200
  research_list_http: 200
  live_test_tasks_created: 0
  gate_C_provider_calls: 0
runtime:
  web_launch_agent: restored_and_running
  scheduled_sync_launch_agent: restored
```

# 4. Remaining unproven or deferred

- 长复合自然语言查询在 dense 不可用、lexical 严格匹配时的召回与 query relaxation。
- 更多真实 Provider/model/role 组合的质量、成本与延迟。
- 真实 SIGKILL/断电、多主机长时间 lease soak、production-scale retention/performance。
- Candidate Delta 向 V5-B 长期知识/Corpus authority 的受控晋升。
- V5-C personalized agent 与 V5-D experience-driven search policy。

这些项目不阻塞 V5-A 的 durable runtime 目标验收，也不得被描述为 V5-A 已证明能力。

# 5. Final acceptance

```yaml
final_acceptance:
  decision: accept_with_known_retrieval_limitation
  V5_A_successful: true
  durable_recursive_runtime_proven: true
  representative_grounded_completion_proven: false
  roadmap_changed: false
  V5_B_or_later_implemented_early: false
  push_performed: false
  tag_created: false
```

详细阶段证据继续以各 Stage Contract、Implementation/Evaluation Report、manifest 和
Git 历史为准；本文件只保留恢复工作所需的当前事实。
