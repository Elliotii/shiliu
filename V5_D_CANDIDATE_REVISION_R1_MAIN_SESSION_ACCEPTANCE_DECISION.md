# Shiliu V5-D Candidate Revision R1 Main Session Acceptance Decision

> Cycle: Candidate Revision Cycle R1
> Decision: accept_exact_invalid_run
> Accepted by: Shiliu V5 Main Codex Session
> Accepted at: 2026-08-11T04:20:26+08:00
> Execution branch: `codex/v5-d`
> Accepted execution head: `ae3367548943098904d88623b9a3d132936563ac`
> R1 freeze commit: `789cf176adcc8c7a66dccbf0c507e875537bcc1a`
> Candidate v1.1 effectiveness: unproven
> Source Gate reached: false
> Reserve / held-out / Stage 3 authorized: false

---

# 1. Accepted Exact Result

```yaml
R1:
  decision: accept
  exact_result: invalid_run
  execution_closed: true
  candidate_quality_judgment: unavailable
candidate_v1_1:
  id: V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001
  version: 1.1.0
  status: proposed_non_active
  effectiveness: unproven
  source_gate: not_reached
  active: false
  shadow: false
```

Main 接受 R1 的 `invalid_run`，不把它改写为 `candidate_v1_1_rejected`、`source_gate_passed` 或
`insufficient_evidence`。R1 的 Attribution/Candidate/freeze 准备已完成，但 D02 Treatment 在 Candidate 或
Provider 执行前被确定性的 Runtime envelope validation 拒绝，因此不存在 v1.1 Research Outcome 证据。

# 2. Accepted Re-attribution and Candidate Boundary

Main 接受 re-attribution `V5D-R1-REATTRIBUTION-20260811-A` 作为 `moderate_high` 的新评测输入：

> v1.0 recovery 已取得 current Evidence 后，只因 Evidence delta 为正就释放 Candidate control，没有继续
> 检查显式 objective/source coverage obligation；随后 Baseline 再次选择旧 action，最终仍由
> `repeated_search` guard 终止。

该判断有 D02 v1.0 Treatment Trace 支撑：一次 recovery 新增 60 segments / 6 current Evidence spans，随后
round 5 重选 round 3 的 action；最终两条 Citation 只来自一个 source，required-aspect coverage 仍为 0。
Corpus/index、Provider、Evaluator 和 Outer Audit alternatives 已分开审查；preliminary planning/model choice
保留为可能的 amplifier，而不是被过度排除。

Main 接受 Candidate v1.1 artifact SHA-256
`c40c4df488c15801eb521530f16833158028cef076ba348ce811f3a8794d4efc` 作为同一 Failure Family 的
`proposed_non_active`、可证伪包。它没有增加第二次 recovery，而是把一次 recovery 改为 objective-derived
coverage bundle，并加入 post-recovery completion/deficit gate。该接受只证明定义有因果连续性且可机械
测试，不证明有效、泛化或产品收益。

# 3. Independently Confirmed Invalid-run Cause

有效 freeze 在 `789cf17`，其 Treatment scaffold 冻结：

```yaml
per_arm_max_input_tokens: 175000
```

accepted Product Runtime `ReceiptBoundResearchProductOrchestrator.run_to_boundary` 明确要求：

```yaml
per_arm_max_input_tokens_maximum: 140000
```

D02 Baseline A1 已先形成有效结果；D02 Treatment A1 随后在 Provider dispatch 和 Candidate execution 之前
抛出 `ResearchValidationError`。Treatment 使用 0 calls/tokens/tools/USD。frozen-identical replacement 必然
重复失败；把 175,000 改为兼容值则会在观察有效 Baseline 后修改 Scaffold。Session 因而停止而不是热修
继续，符合 R1 freeze 与 anti-resampling 约束。

这是窄的 `implementation_failure_frozen_scaffold_runtime_envelope`。它不消耗另一个 Candidate major
revision，但当前合同也不授权自行修改并重跑。

# 4. Independent Limited Verification

Main 独立核验：

- R1 entry `254d72a`、freeze `789cf17`、closeout `ae33675` 的父子关系与 clean worktree 正确；
- freeze 后只增加/修改 Closeout、Current State 和 Ledger，Candidate/Treatment/Runner/Evaluator 未变；
- 产品 `src` tree `41ccf576…` 未改变，默认 Product Runtime 不导入或注册 R1 Treatment；
- Candidate、re-attribution、freeze manifest、Treatment、Runner、Evaluator 和四项 test 的实际 SHA-256
  与 freeze manifest/receipt 相符；
- Main 复跑四项 R1 定向 suite：`18 passed`；现有测试未覆盖“冻结 per-arm cap 必须先通过 accepted
  Product Runtime envelope validation”，这是本次具体 test gap；
- isolated DB schema 14、`integrity_check=ok`、FK 0；R1 新增 5 个 Provider side effects，全部
  `succeeded`；
- R1 总计 1 valid arm、2 attempt records、5 logical / 5 HTTP calls、8,893 input / 549 output tokens、
  3 tool calls、USD 0.000646613，unknown reservations 0；
- 未 Push、Merge、Tag，未修改 live DB/index。

# 5. D02 Baseline and Unproven Source Gate

```yaml
D02_baseline_A1:
  valid: true
  answer_status: valid_insufficient
  termination_reason: repeated_search
  current_grounded_citations: 0
  grounded_sources: 0
  logical_http_calls: [5, 5]
  input_output_tokens: [8893, 549]
  cost_usd: 0.000646613
D02_treatment_A1:
  valid: false
  provider_dispatch: false
  candidate_executed: false
D02_valid_pair: false
D04_runs: 0
source_gate_judgment: unavailable
```

D02 Baseline A1 是有效且已经观察的实验结果，不能在后续 amendment 中悄然删除或当作未发生。当前没有
required-aspect/Citation/source-diversity/recovery/stop pair delta，不能对 v1.1 作任何正负效果判断。

# 6. Reserve and Authority Integrity

```yaml
reserve:
  ciphertext_sha256: d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c
  key_mode: "000"
  access_log_entries: 4
  post_freeze_access_entries: 0
  runs: 0
  opened_or_split: false
heldout_runs: 0
candidate_v1_2_created: false
active_shadow_or_promotion: false
stage_3_execution: false
```

Reserve custody、contamination 和 non-action 边界通过。

# 7. Non-material Documentation Correction

Execution freeze manifest、private receipt 与实际 Treatment 文件一致，正确 SHA-256 为：

```text
cdb52593fec31876df2a8fe73ea67cbccbc21d0fd22ef83466aa486927f4254f
```

Execution Closeout Report 与 `V5_D_CURRENT_STATE.md` 各少写了中间的 `bc`，形成 62 字符显示值。该笔误
不改变 freeze identity、代码或 invalid-run 判定，但必须在任何后续 R1 execution amendment 的首个
docs-only correction 中修正；Main 本决定记录正确值。

# 8. Authorization After Acceptance

```yaml
R1:
  status: accepted_invalid_run
  current_execution_closed: true
candidate_v1_1:
  proposed_non_active: true
  effectiveness_unproven: true
R1_execution_amendment:
  authorized: false
provider_runs_authorized: false
reserve_open_assignment_or_run: false
heldout_evaluation_authorized: false
candidate_v1_2_authorized: false
stage_3_authorized: false
live_database_write_or_migration_authorized: false
merge_push_tag_authorized: false
active_formal_stage_after_acceptance: none
```

# 9. Recommended Next Authorization

Main 建议用户可授权一个 `R1-E1 mechanical execution amendment`，它不是第二次 major Candidate revision。
该 amendment 应仅允许：

1. 修正两处 Treatment hash 显示笔误；
2. 把 Treatment per-arm input cap 降到 accepted Runtime 的 `<=140000`，并增加一个在 freeze 前调用精确
   Product boundary validation 的机械测试；
3. 保持 Candidate v1.1、Treatment logic、Evaluator、success gates、D02/D04、Provider、Corpus 和
   Reserve identity不变；
4. 将已观察的 D02 Baseline A1 作为固定 carried-forward arm 绑定到新 freeze，禁止重跑或替换；
5. 只运行剩余 D02 Treatment 与 D04 Treatment/Baseline，且累计用量继续受原 R1 hard caps 约束；
6. Source Gate 完成后再次停止等待 Main，仍不打开 reserve。

当前 Main 只提出该建议，没有执行或授权它。用户也可以不再运行，以 `accepted_invalid_run` 保留 v1.1
unproven 状态并关闭该 Candidate effort。
