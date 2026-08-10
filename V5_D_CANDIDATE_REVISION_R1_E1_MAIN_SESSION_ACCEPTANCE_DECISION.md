# Shiliu V5-D Candidate Revision R1-E1 Main Session Acceptance Decision

> Amendment: R1-E1 Mechanical Execution Amendment
> Decision: accept_exact_candidate_v1_1_rejected
> Accepted by: Shiliu V5 Main Codex Session
> Accepted at: 2026-08-11T05:01:55+08:00
> Execution branch: `codex/v5-d`
> Accepted execution head: `68fd655b3e54ba2529aee8395860ed876ee88c1a`
> E1 freeze commit: `cbc8917aaa625897ae7e718e7d15e784aeeb0705`
> Candidate v1.1 effectiveness: rejected_at_source_gate
> Reserve / held-out / Stage 3 authorized: false

---

# 1. Accepted Exact Result

```yaml
R1_E1:
  decision: accept
  exact_result: candidate_v1_1_rejected
  execution_closed: true
  source_gate_reached: true
candidate_v1_1:
  id: V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001
  version: 1.1.0
  status: proposed_non_active_rejected
  active: false
  shadow: false
  promotion_eligible: false
```

Main 接受 D02 carried Baseline 与 E1 Treatment 为有效冻结 Source pair，并接受该 pair 的失败足以产生精确
`candidate_v1_1_rejected`。该结论不是 infrastructure/implementation invalid run，也不允许再用 mechanical
amendment 修改 Candidate。

# 2. Accepted Scientific Result

D02 Treatment 确实触发了一次 Candidate coverage-bundle recovery，并从 `repeated_search` 改为在 recovery
没有产生新 Evidence 后诚实以 `no_new_evidence` 停止；这说明 Candidate 改变了局部控制行为。

但冻结 Source Gate 要求的是 grounded Research Outcome 改善，而不是只消除重复搜索。实际有效 pair 为：

```yaml
D02:
  baseline:
    answer_status: valid_insufficient
    required_aspects: 0
    current_grounded_citations: 0
    grounded_sources: 0
    termination_reason: repeated_search
  treatment:
    answer_status: valid_insufficient
    required_aspects: 0
    current_grounded_citations: 0
    grounded_sources: 0
    candidate_material_recoveries: 1
    candidate_coverage_bundles: 1
    candidate_post_recovery_gates: 0
    coverage_satisfied: false
    termination_reason: no_new_evidence
  delta:
    required_aspects: 0
    current_grounded_citations: 0
    grounded_sources: 0
  pair_pass: false
```

因此 grounded improvement、source diversity、material post-recovery mechanism 与 recovery/stop gates 均
未通过。Candidate v1.1 effectiveness 已被有效证伪，不再是 `unproven`。

# 3. D04 Stop Accepted

Main 接受 D04 Treatment/Baseline 未运行。冻结合同要求每个有效 Source pair 全部通过，并规定任一有效 pair
失败即 exact `candidate_v1_1_rejected`；E1 又要求达到任一 exact exit 后立即停止。D02 已形成有效且不可逆
失败，D04 无法恢复 all-pairs Gate。继续运行只会消费 Provider，且不构成必要的 invalid replacement。

这不证明 D04 上的行为，也不允许把 D04 缺失写成泛化、回归或负迁移结论。

# 4. Independent Limited Verification

Main 独立确认：

- entry `ae33675` → freeze `cbc8917` → closeout `68fd655` 的历史连续，最终 worktree clean；
- E1 freeze 前只修正两处显示 hash、Treatment cap 与机械 runner/test，旧 R1 freeze/evidence 未改写；
- Candidate v1.1、Treatment logic、Evaluator 与 Re-attribution SHA-256 分别保持
  `c40c4df…`、`cdb52593…`、`4227dafd…`、`9c4b6a5c…`；
- 产品 `src` tree 在 entry 与 closeout 均为 `41ccf576…`；
- 新 regression 实际到达 `ReceiptBoundResearchProductOrchestrator.run_to_boundary` validation boundary，
  允许 125,000/140,000 并在 Provider dispatch 前拒绝旧 175,000；
- Main 使用配置工作区 Python 复跑五项定向 suite：`22 passed`；
- D02 Baseline deep Trace SHA-256 仍为 `1cce5577…`，没有重跑、替换或重新采样；
- 私有 pair evaluation SHA-256 `9eaeb5c4…` 与 frozen evaluator 输出一致；
- isolated DB `integrity_check=ok`、FK 0，E1 closeout DB SHA-256 `122b84a9…`；
- 两个 Git commits 之后没有产品代码、Reserve、Held-out 或 Stage 3 内容。

# 5. Budget and Provider Accounting Accepted

```yaml
E1_incremental:
  valid_arms: 1
  outer_attempt_records: 1
  logical_provider_calls: 3
  http_attempts: 3
  input_tokens: 2774
  output_tokens: 393
  deep_tool_calls: 3
  paid_cost_usd: 0.000665144
R1_plus_E1_cumulative:
  valid_arms: 2
  outer_attempt_records: 3
  logical_provider_calls: 8
  http_attempts: 8
  input_tokens: 11667
  output_tokens: 942
  deep_tool_calls: 6
  paid_cost_usd: 0.001311757
  unknown_reservations: 0
```

累计用量远低于原 R1 hard caps。Keychain 第一次 permission pause 发生在 arm record 与 Provider dispatch
之前，使用量为 0；用户授权恢复后只运行同一冻结 D02 Treatment A1。凭据值未显示或记录。

# 6. Reserve and Protected-boundary Integrity

```yaml
reserve:
  ciphertext_sha256: d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c
  key_mode: "000"
  access_log_sha256: a9d6a1872638c700d152ae6f0556112e380d77fa74a40e422103ec44023a1723
  access_log_entries: 4
  post_freeze_access_entries: 0
  runs: 0
  opened_or_split: false
heldout_runs: 0
candidate_v1_2_created: false
active_shadow_or_promotion: false
stage_3_execution: false
live_database_write_or_migration: false
push_merge_tag: false
```

Reserve custody、contamination、live/product 与 Git non-action 边界通过。

# 7. Claim Boundary

R1-E1 只证明：

- Candidate v1.1 在一个已消费 Source case 的有效 paired run 上未通过冻结 Source Gate；
- 它能改变局部 recovery/stop 行为，但没有改善 grounded Research Outcome；
- 因此它不应进入 Reserve、Held-out、active/shadow 或 promotion。

它没有形成 related-task generalization、unrelated regression、negative transfer、真实产品收益或
Portfolio-ready 证据。V5-D 当前也不是 Version Complete。

# 8. Authority After Acceptance

```yaml
R1_E1:
  status: accepted_candidate_v1_1_rejected
  execution_closed: true
candidate_v1_1:
  status: proposed_non_active_rejected
  further_mechanical_amendment_authorized: false
candidate_v1_2_authorized: false
further_major_candidate_revision_authorized: false
provider_runs_authorized: false
reserve_open_assignment_or_run: false
heldout_evaluation_authorized: false
stage_3_authorized: false
active_shadow_or_promotion_authorized: false
live_database_write_or_migration_authorized: false
merge_push_tag_authorized: false
active_formal_stage_after_acceptance: none
```

# 9. Program-level Next Decision

Candidate v1.0 与 v1.1 均已被有效 falsification；唯一授权的 major revision budget 已使用，R1-E1 也已关闭。
当前没有自动下一执行 Stage。Main 将等待用户决定是否：

1. 以 `no_validated_candidate` 诚实进行 V5-D 有界 closeout；或
2. 作为材料性新授权，重新审查 Failure Family/Candidate 方向和追加成本。

在该决定前，不创建新 Candidate、不打开 Reserve、不运行 Held-out、不进入 Stage 3，也不合并 V5-D。
