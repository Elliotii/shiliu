# Shiliu V5-D Candidate Revision R1-E1 Mechanical Execution Amendment Contract

> Status: authorized_for_execution
> Authorized at: 2026-08-11
> Owner: persistent V5-D Version Session
> Execution branch: `codex/v5-d`
> Entry execution head: `ae3367548943098904d88623b9a3d132936563ac`
> Main acceptance authority head: `e0dbf8e620853e0e3dab529a205978708e9e8776`
> Candidate: `V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001` v1.1.0
> Amendment kind: mechanical_execution_only
> Reserve open/assignment/run authorized: false
> Held-out evaluation authorized: false
> Stage 3 authorized: false

---

# 1. Exact Purpose and Result Carried Forward

Main 与用户接受 R1 的精确结论：

```yaml
R1:
  result: invalid_run
candidate_v1_1:
  effectiveness: unproven
  source_gate: not_reached
failure_class: implementation_failure_frozen_scaffold_runtime_envelope
major_candidate_revision_budget_consumed_by_R1_E1: false
```

R1-E1 不是 Candidate v1.2、第二次 major revision 或 Stage 2/3 重开。它只修复冻结 Scaffold 的 Treatment
per-arm input cap 超过 accepted Product Runtime 上限的问题，并完成 R1 尚未完成的 D02/D04 Source Gate。

# 2. Immutable Scientific Identity

以下内容必须与 R1 freeze 完全相同，不得根据已观察的 D02 Baseline 或任何 E1 新结果修改：

- Candidate v1.1 trigger、applicability、coverage bundle、procedure、recovery logic、completion/deficit gate、
  stop conditions 与 fallback；
- Treatment logic、No-Skill Baseline、Evaluator、success gates 与 success thresholds；
- Provider/model/configuration、Prompt/tool authority、Corpus/index/source snapshot；
- D02/D04 identity、Source Gate semantics、Reserve identity；
- Candidate active/shadow/product-registration 状态。

```yaml
immutable_hashes:
  candidate_v1_1_sha256: c40c4df488c15801eb521530f16833158028cef076ba348ce811f3a8794d4efc
  treatment_logic_sha256: cdb52593fec31876df2a8fe73ea67cbccbc21d0fd22ef83466aa486927f4254f
  evaluator_sha256: 4227dafd04e2d0e8fb6909f144a853919105bf7f50a3a25e2b3932d4c5d51c08
  reattribution_sha256: 9c4b6a5ccaf3e5e887a6bcaf2db151a7aecfc1cbd8ec723971d149f6fcf4d750
reserve_identity:
  ciphertext_sha256: d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c
  key_mode: "000"
  access_log_entries: 4
  post_freeze_access_entries: 0
  runs: 0
```

如任一 immutable identity 不一致，停止并报告，不得通过改 Candidate 或重新建立实验来消除不一致。

# 3. Permitted Mechanical Changes

只允许：

1. 修正 `V5_D_CANDIDATE_REVISION_R1_CLOSEOUT_AND_SOURCE_GATE_REPORT.md` 与
   `V5_D_CURRENT_STATE.md` 中两处 Treatment SHA-256 显示笔误，使其显示本合同记录的 64 字符实际值；
2. 将 Treatment `per_arm_max_input_tokens` 从 `175000` 改为 `140000`，不得高于 accepted Product Runtime
   上限；
3. 更新由 cap 变化机械派生的 runner/freeze hash 与预算字段；
4. 在 E1 freeze 前增加并通过针对真实 accepted Product Runtime validation boundary 的机械 regression test。

该测试必须实际到达 Product Runtime 对 per-arm envelope 的同一验证入口，证明 Baseline 与 amended Treatment
配置均不会因 cap 超界而抛出 `ResearchValidationError`；测试必须 mock/阻止 Provider dispatch，不得消费
Provider、读取凭据值或改变产品语义。仅验证本地 helper 而未到达该 Runtime boundary 不满足本 Gate。

旧 R1 freeze、private receipt、invalid attempt 和 closeout 历史证据不得改写或删除。E1 必须形成独立的增量
freeze manifest 与 freeze commit，显式记录 old freeze → amendment → carried-forward Baseline provenance。

# 4. D02 Baseline A1 Carried-forward Provenance

D02 Baseline A1 已有效观察，固定 carried forward：

```yaml
D02_baseline_A1:
  rerun: forbidden
  replace: forbidden
  resample: forbidden
  outcome: valid_insufficient
  termination_reason: repeated_search
  current_grounded_citations: 0
  current_grounded_sources: 0
  logical_provider_calls: 5
  http_attempts: 5
  input_tokens: 8893
  output_tokens: 549
  deep_tool_calls: 3
  paid_cost_usd: 0.000646613
  unknown_reservations: 0
  deep_trace_sha256: 1cce5577d33faf6e57015682b1ce3f08590417b5b0a54e8f111c974d33d66538
```

其实际 input usage `8893` 远低于原 Baseline cap `125000`，也低于 amended Product Runtime maximum
`140000`；本次 cap 修改只使原 `175000` Treatment cap 合法收敛，因此对该 Baseline 为 non-binding。

新 E1 freeze/report 必须绑定：

- old R1 freeze commit `789cf176adcc8c7a66dccbf0c507e875537bcc1a`；
- old experiment manifest SHA-256 `230989ebc8c8437b56edd051ebe2d810cc6f38d80adfd9de089a79c0509d0d9c`；
- old private freeze receipt SHA-256 `b24b05d94d741e48e82d62ff2a9b46271451f88aeb8a607c9df53dfcc3b766f4`；
- old private run manifest SHA-256 `41bd4d7feacca3440e6f7759fe27d69665b76346f921f57fe186353e80dce680`；
- old final isolated DB SHA-256 `d7ce1000f1a0c95de69211db3b69a2f779a58125e36c27a86f1b3ff07678425b`；
- old invalid D02 Treatment evidence SHA-256
  `8401a9375566b2289319e1d9f84a14fba5192be4acb8c358b5ae3e450b637cbf`。

旧 invalid D02 Treatment 记录必须保留；E1 Treatment 使用新的预注册 Task/Attempt identity，不伪装成旧 attempt。

# 5. Remaining Execution Order

只允许运行尚未完成的三个 arms，顺序保持原冻结的 counterbalance：

```text
1. D02 Treatment
2. D04 Treatment
3. D04 Baseline
4. evaluate exact Source Gate result
5. stop for Main limited acceptance
```

每个 arm 只允许 R1 合同原有的一个 scaffold-identical invalid replacement，且仅限 Provider、infrastructure
或 evaluation execution invalid；不得替换 Candidate quality failure、valid insufficient/partial、不利结果或
Source Gate failure。D02 Baseline 不属于可运行或 replacement 的 arm。

# 6. Cumulative R1 Budget

R1-E1 不获得新预算。所有 R1 与 E1 usage 必须合并计入原 R1 hard caps：

```yaml
original_R1_hard_caps:
  valid_arms: 4
  outer_attempts_including_replacements: 8
  logical_provider_calls: 104
  http_attempts: 208
  input_tokens: 1060000
  output_tokens: 140000
  deep_tool_calls: 100
  wall_time_seconds: 5760
  paid_cost_reserve_stop_usd: 0.16
  paid_cost_hard_stop_usd: 0.20
consumed_before_E1:
  valid_arms: 1
  outer_attempt_records: 2
  logical_provider_calls: 5
  http_attempts: 5
  input_tokens: 8893
  output_tokens: 549
  deep_tool_calls: 3
  wall_time_seconds: 40.933
  paid_cost_usd: 0.000646613
maximum_remaining_for_E1:
  valid_arms: 3
  outer_attempts_including_replacements: 6
  logical_provider_calls: 99
  http_attempts: 203
  input_tokens: 1051107
  output_tokens: 139451
  deep_tool_calls: 97
  wall_time_seconds: 5719
  paid_cost_reserve_stop_usd: 0.159353387
  paid_cost_hard_stop_usd: 0.199353387
```

E1 runner 必须 enforce residual caps；closeout 必须同时报告 E1 incremental usage 与 R1+E1 cumulative usage。
Unknown reservation 继续按 worst case 计入。原 per-pair Treatment overhead hard gate 与 Candidate 更精确
expected delta 保持不变。

# 7. Source Gate and Exact Exit

D02 与 D04 每个有效 pair 必须通过原 R1 Contract 第 8 节全部硬门。任何有效 pair 失败，exact result 为
`candidate_v1_1_rejected`，不得修改 Candidate、Evaluator、threshold 或启动 v1.2。

R1-E1 只允许：

```yaml
- source_gate_passed
- candidate_v1_1_rejected
- invalid_run
- blocked_by_infrastructure_or_data
```

如果再次出现纯 implementation/infrastructure invalid run，精确记录原因并停止，不得自行扩大 amendment。
如果出现 Candidate-effectiveness failure，按冻结合同正常判定为 rejected，不得再称为 mechanical amendment。
`source_gate_passed` 也只允许停止并向 Main 提交；不授权打开 Reserve 或运行 Held-out。

# 8. Required Artifacts and Git

至少提交：

- `V5_D_CANDIDATE_REVISION_R1_E1_EXPERIMENT_FREEZE.json`；
- 新增/更新的 Runtime-envelope regression test；
- `V5_D_CANDIDATE_REVISION_R1_E1_CLOSEOUT_AND_SOURCE_GATE_REPORT.md`；
- 更新 `V5_D_CURRENT_STATE.md` 与 `V5_D_DECISION_LEDGER.md`；
- 两处显示 hash 的文档修正。

允许一个 E1 freeze commit 与一个 closeout/evidence commit。产品 `src` 不得修改；raw private evidence、
Provider response、私人 Query/Evidence、Gold、credential 与 temp DB 不进入 Git。最终 branch 必须 clean。

# 9. Explicit Non-authorizations

```yaml
candidate_v1_2: false
reserve_open_assignment_or_run: false
heldout_related_or_unrelated_run: false
stage_3_execution: false
candidate_active_or_shadow_registration: false
candidate_promotion: false
live_database_write_or_migration: false
product_source_modification: false
candidate_or_treatment_logic_change: false
evaluator_or_success_gate_change: false
provider_corpus_D02_D04_or_reserve_identity_change: false
generic_skill_eval_harness_or_learning_platform: false
push: false
merge: false
tag: false
```

完成 Source Gate 或任一 exact exit 后停止，等待 Main Session 有限验收。
