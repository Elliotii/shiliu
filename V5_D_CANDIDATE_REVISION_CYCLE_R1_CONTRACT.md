# Shiliu V5-D Candidate Revision Cycle R1 Contract

> Status: completed_and_main_accepted_invalid_run
> Authorized at: 2026-08-11
> Owner: persistent V5-D Version Session
> Execution branch: `codex/v5-d`
> Entry execution head: `254d72a03a1251ee0d08cac49d100b91b5de7593`
> Parent Candidate: `V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001` v1.0.0
> Parent verdict: `rejected`
> Target Candidate version: 1.1.0
> Reserve open/assignment/run authorized: false
> Held-out evaluation authorized: false
> Stage 3 authorized: false
> Freeze commit: `789cf176adcc8c7a66dccbf0c507e875537bcc1a`
> Accepted execution head: `ae3367548943098904d88623b9a3d132936563ac`
> Exact R1 result: `invalid_run`

---

# 1. Goal and Exact Boundary

本 Cycle 只完成：

```text
Rejected Candidate v1.0 Evidence
→ Post-treatment Trace Re-attribution
→ Remaining Failure Mechanism
→ New Falsifiable Hypothesis
→ Candidate v1.1
→ Frozen Experiment-only Treatment
→ D02 / D04 Source Gate Re-evaluation
→ Exact R1 Result
→ Stop for Main Acceptance
```

R1 不是第二个 Candidate family，不改变 V5-D 四 Stage 路线，也不进入 Stage 3。它是同一已接受 Failure
Family 的一次、且默认仅一次 major Candidate revision。Source Gate 通过也只获得申请真正 held-out
evaluation 的资格，不获得 reserve 或 promotion 权限。

```yaml
revision_budget:
  rejected_version: 1.0.0
  authorized_major_revision_cycles: 1
  target_version: 1.1.0
  v1_2_or_further_revision_authorized: false
```

# 2. Entry Gate and Source Identity

开始前核验：

```yaml
git:
  branch: codex/v5-d
  head: 254d72a03a1251ee0d08cac49d100b91b5de7593
  working_tree_clean: true
accepted_stage_2:
  effective_freeze: 0c72277e7b30bac68800ef27acc9e8d52222efd6
  candidate_v1_0_sha256: 6bcda6e5c5428c304807f067570c9acb7977cbd991c355edaeb9346d3d13cdbe
  exact_verdict: rejected
  D02_source_pair_valid: true
reserve:
  ciphertext_sha256: d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c
  key_mode: "000"
  access_log_entries: 4
  post_freeze_access_entries: 0
  runs: 0
```

材料性不一致时停止。不得通过读取 reserve 来解释不一致。

# 3. Mandatory Phase Order

```text
A. verify accepted Stage 2 and custody identities
→ B. offline post-treatment re-attribution from D02 v1.0 source evidence
→ C. compare alternative causes and freeze remaining failure mechanism
→ D. freeze one new falsifiable Hypothesis
→ E. define Candidate v1.1 and exact v1.0→v1.1 delta
→ F. implement minimal experiment-only Treatment and directed tests
→ G. freeze Candidate/Treatment/Baseline/Scaffold/Evaluator/Source cases/Order/Budget
→ H. run frozen D02/D04 source pairs without opportunity resampling
→ I. issue one exact R1 result
→ J. submit closeout commit and stop
```

Attribution、Hypothesis、Candidate 定义必须在任何 R1 Provider run 前完成。Freeze 后不得根据 D02/D04
结果修改 Candidate、Evaluator、Scaffold、success gates 或 order，并继续使用同一结果。

# 4. Attribution-first Requirement

先利用已消费的 D02 v1.0 Treatment Trace 回答：

> 第一次 materially-new recovery 已取得 grounded Evidence Delta 后，为什么系统仍未完成 required aspects /
> source requirement，并最终重新进入 repeated-search？

必须形成：

```yaml
re_attribution:
  first_actionable_post_recovery_step:
  failure_mechanism:
  supporting_evidence:
  alternative_causes:
  excluded_causes:
  confidence:
```

可以调查 recovery target 与 remaining aspects、Outer Audit/unresolved aspects handoff、source diversity、
ProgressDelta 解释、Stop/Continue 的目标完成语义、preliminary QueryPlan/DecisionView handoff 等，但不得预设
其中任何一项为结论。

以下做法不能代替 re-attribution：

- 直接把 recovery count 加一或持续增加；
- 看到单来源就无条件继续搜索；
- 仅围绕 D02 Gold/Outcome 设计规则；
- 以消除 `repeated_search` termination reason 作为唯一目标。

若 Trace 不足以支持新的 first-actionable mechanism，输出 `reattribution_insufficient` 并停止，不创建
Candidate v1.1。

# 5. Candidate v1.1 Contract

只有 re-attribution 完成后，才允许创建一个 v1.1 artifact。至少冻结：

```yaml
candidate_v1_1:
  id:
  parent_candidate: V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001
  version: 1.1.0
  source_failure_evidence:
  revised_causal_hypothesis:
  applicability:
  trigger:
  required_preconditions:
  procedure:
  recovery_logic:
  stop_conditions:
  forbidden_behavior:
  baseline_fallback:
  expected_behavior_change:
  falsification_conditions:
  expected_cost_delta:
  protected_boundaries:
  status: proposed_non_active
  active: false
  shadow: false
```

Candidate v1.1 必须保持同一 Failure Family 的因果连续性，继续属于 domain-specific Search / Research
Policy，不得改变 Evidence Authority、Citation/Verifier/currentness、Dataset、Evaluator、Promotion Gate、
Provider route、tool permission 或 Runtime authority。No-Skill fallback 必须保持不变。

# 6. D02 / D04 Evidence Role

```yaml
D02:
  diagnosis: consumed
  v1_0_falsification: consumed
  v1_1_design_evidence: allowed
  source_gate: allowed
  generalization_evidence: false
D04:
  stage_0_discovery: consumed
  source_gate: allowed
  generalization_evidence: false
```

D02/D04 只能作为 Source / Diagnosis Cases。其任何改善都不计入 held-out generalization、unrelated
regression 或 negative-transfer evidence。

# 7. Experiment-only Implementation and Freeze

允许在 `scripts/`、定向 `tests/`、V5-D docs/artifacts 和私有隔离 evidence root 中实现最小 R1
Treatment。默认产品 `src` 不得导入、发现、注册或调用它；runtime registration 保持 null，active/shadow
保持 false。

Provider 前必须在 clean local freeze commit 中绑定：

- re-attribution、Hypothesis、Candidate v1.1 artifact 与 v1.0→v1.1 delta；
- Treatment、No-Skill Baseline、Research Scaffold 与 Candidate-specific context；
- deterministic evaluator、manual frozen-aspect review boundary 与 success gates；
- D02/D04 source identities、arm order、Task/Attempt identities 与 invalid replacement identities；
- corpus/index/source snapshot、Provider/model/prompt/tool identities；
- whole-cycle budget、per-arm overhead cap 与 contamination rule；
- reserve seal/access identity，且明确没有 reserve semantic split。

推荐冻结顺序：

```yaml
D02: [baseline, treatment]
D04: [treatment, baseline]
```

若实现需要改变产品 `src`、accepted Runtime durability/trace/evaluator foundation 或 protected boundary，停止
并报告，不把该变化包装成 experiment-only plumbing。

# 8. Source Gate

D02 与 D04 每个有效 pair 都必须通过。Treatment 不仅要改变 first-actionable mechanism，还必须相对有效
Baseline 改善真实 Research Outcome：

```yaml
required_per_source_pair:
  common_arm_validity: true
  material_post_recovery_mechanism_change: true
  frozen_required_aspect_delta_min: 1
  current_grounded_citation_delta_min: 1
  required_source_diversity: pass
  currentness_and_lineage: pass
  recovery_quality: pass
  stop_correctness: pass
  final_answer_status: no_material_regression
  protected_boundaries: pass
  frozen_overhead_cap: pass
```

以下都不算成功：

- Evidence/Citation 更多但 required aspects 仍未改善；
- `repeated_search` 消失但只是更早停止；
- 依靠 answer length、navigation hit 或 search count；
- 只通过一个 source pair；
- 删除、替换或重跑不利的有效结果。

Candidate freeze 时可以根据 re-attribution 冻结更具体的 recovery/stop 指标，但不得降低上述硬门。
Treatment 相对 Baseline 的单 arm 额外开销上限不得超过：3 logical calls、6 HTTP attempts、50,000 input
tokens、20,000 output tokens、3 tool calls、USD 0.03；Candidate artifact 必须声明更精确的 expected delta。

# 9. Provider, Cost and Invalid-run Budget

复用原 Stage 2 source-phase 上限，不得借 R1 扩大：

```yaml
provider:
  route: current_product_DeepSeek_only
  credential: existing_Keychain_reference_runtime_read_only
  credential_value_recorded: false
whole_R1_source_gate_hard_caps:
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
```

每个 arm 只允许一次 scaffold-identical replacement，且仅限 provider、infrastructure 或 evaluation
execution invalid。Candidate quality failure、valid insufficient/partial、required-aspect failure、stop failure 或
不利 Outcome 不允许 replacement。Unknown reservation 按 worst case 计入；任一 cap 先到即停止。

如果必要 pair 在唯一合法 replacement 后仍无法形成有效结果，输出 `invalid_run`。不得 best-of、并发
resampling 或更换 Provider/Prompt/Scaffold。

# 10. Reserve Custody and Contamination

```yaml
reserve:
  open_authorized: false
  assignment_authorized: false
  run_authorized: false
  body_or_gold_access_authorized: false
  semantic_split_authorized: false
```

不得解密、查看、运行或利用 4 个 reserve tasks，不得用 reserve 调整 re-attribution、Candidate、trigger、
procedure、stop rule、Evaluator 或 Source Gate threshold。R1 `source_gate_passed` 后也必须先停止，由 Main
验收并重新向用户申请真正 held-out evaluation。

# 11. Exact Exit Results

R1 只允许：

```yaml
- source_gate_passed
- candidate_v1_1_rejected
- reattribution_insufficient
- failure_reclassified
- invalid_run
- blocked_by_infrastructure_or_data
```

任何有效 source pair 未通过硬门，exact result 为 `candidate_v1_1_rejected`，并默认关闭当前 Failure Family
的 revision attempt；不得自行创建 v1.2。只有能够证明属于 invalid run、implementation/infrastructure 或
evaluation execution defect、且不属于 Candidate effectiveness 时，才可向 Main 提交额外授权请求。

# 12. Required Closeout

至少提交：

- `V5_D_POST_TREATMENT_REATTRIBUTION_R1.md`；
- `V5_D_CANDIDATE_EVIDENCE_DELTA_FOLLOWUP_V1_1.json`；
- `V5_D_CANDIDATE_REVISION_R1_EXPERIMENT_FREEZE.json`；
- `V5_D_CANDIDATE_REVISION_R1_CLOSEOUT_AND_SOURCE_GATE_REPORT.md`；
- 更新 `V5_D_CURRENT_STATE.md` 与 `V5_D_DECISION_LEDGER.md`。

报告必须覆盖 re-attribution、alternative causes、v1.0→v1.1 delta、freeze identity、D02/D04 pair metrics、
required aspects/Citation/source diversity、recovery/stop、Provider/token/tool/USD、invalid/contamination、exact
result、reserve custody 与 held-out recommendation。Raw private Query/Evidence/Trace/Provider response、Gold、
credentials 和 temp DB 不进入 Git。

允许一个 freeze commit 与一个 closeout/evidence commit；最终 branch 必须 clean。完成后停止，不能自我
接受，不能自动进入 reserve/held-out 或 Stage 3。

# 13. Explicit Non-authorizations

```yaml
reserve_open_assignment_or_run: false
heldout_related_or_unrelated_run: false
stage_3_execution: false
candidate_active_or_shadow_registration: false
candidate_promotion: false
live_database_write_or_migration: false
product_source_modification: false
generic_skill_eval_harness_or_learning_platform: false
second_candidate_family: false
v1_2_candidate: false
push: false
merge: false
tag: false
```

# 14. Closeout Status

R1 已完成 Attribution、Candidate v1.1 与 freeze，但 Source Gate 因 frozen Treatment per-arm input cap
`175000` 超过 accepted Product Runtime `140000` 上限而在 Provider dispatch 前停止。Main 已接受 exact
`invalid_run`；Candidate v1.1 effectiveness 仍未证明。任何 corrected execution 必须由用户另行授权，并
处理已观察的有效 D02 Baseline；当前不得继续。
