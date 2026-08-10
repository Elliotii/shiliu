# Shiliu V5-D Final Closeout

> Version: V5-D
> Goal: Controlled Experience-driven Search Policy Improvement
> Final status: `closed_no_validated_candidate`
> Authority: Shiliu V5 Main Codex Session
> Closed at: 2026-08-11
> Accepted execution head: `68fd655b3e54ba2529aee8395860ed876ee88c1a`
> Mainline evidence merge: `2d10844eee564af830bf38b4c792d2834381de63`
> Product Runtime policy registration delta: 0

---

# 1. Final Decision

```yaml
V5_D:
  final_status: closed_no_validated_candidate
  candidate_v1_0: rejected
  candidate_v1_1: rejected
  validated_candidate: false
  heldout_evaluation: not_reached
  active_policy: none
  shadow_policy: none
  stage_3: not_entered
  further_candidate_revision_authorized: false
```

V5-D 没有形成可晋升的 Search Skill / Policy。该负结果不被弱化或改写；V5-D 的正式价值是建立并实际
执行了一条可审计、可证伪、会拒绝失败 Candidate 的 improvement lifecycle。

# 2. Accepted Technical Result

V5-D 实际完成并保留：

```text
真实代表性 discovery tasks
→ Replayable Experience / Trace
→ Repeated Failure Family qualification
→ Step-level Failure Attribution
→ Falsifiable Hypothesis
→ Versioned non-active Candidate
→ Frozen Baseline / Treatment / Evaluator / Budget / Experiment identity
→ Provider execution and accounting
→ Invalid-run separation
→ Candidate falsification
→ Promotion protection
```

Stage 0 在候选定义前冻结 discovery/reserve identity，通过四个有效 discovery outcomes 在 D02/D04 上资格化
`non_progress_search_repetition_without_recovery` Failure Family。D01 Provider-domain failure 被隔离，D03
作为 same-environment valid partial control；这只满足 empirical entry，不证明 Candidate。

Stage 1 将 first actionable failure 定位在 final repeated-search guard 之前的 follow-up decision：zero
current Evidence delta 与未完成目标均已可见，但决策没有选择 materially new target 或 honest stop。由此
形成可证伪 Hypothesis 与 Candidate v1.0，Candidate 始终 `proposed_non_active`。

# 3. Candidate v1.0 Falsification

Stage 2 使用冻结 Source pair。有效 D02 Treatment 执行一次 materially-new recovery，并将 current grounded
Citations 从 0 增加到 2；但两条 Citation 只来自一个 source，required-aspect coverage 保持 0，后续仍由
`repeated_search` 结束。Grounded improvement、source diversity 与 recovery/stop gates 失败。

```yaml
candidate_v1_0:
  exact_verdict: rejected
  active_or_shadow: false
  reserve_opened: false
  heldout_run: false
```

D04 没有继续运行，因为冻结 all-source-pairs Gate 已不可恢复；该停止不形成 D04 行为声明。

# 4. Re-attribution and Candidate v1.1 Falsification

唯一一次 major revision R1 先对 v1.0 Treatment 后的 remaining failure 重新归因：一次 recovery 获得 Evidence
后，Candidate control 仅因 Evidence delta 为正而释放，没有继续检查 objective/source coverage obligation。
Candidate v1.1 保留一次 recovery 上限，将其改为 objective-derived coverage bundle，并增加 post-recovery
completion/deficit gate。

首次 R1 freeze 把 Treatment per-arm input cap 错冻为 `175000`，超过 accepted Product Runtime `140000`
上限。Treatment 在 Provider dispatch 与 Candidate execution 前被拒绝，精确分类为：

```text
implementation_failure_frozen_scaffold_runtime_envelope
```

该次 `invalid_run` 没有被伪装成 Candidate failure。R1-E1 mechanical amendment 只修正两处 hash 显示、把
cap 收敛到 `140000`、增加真实 Runtime boundary regression，并固定携带已观察的 D02 Baseline；Candidate、
Treatment logic、Evaluator、threshold、Provider、Corpus 与 case identity 均未改变。

有效 E1 D02 Treatment 触发一次 coverage-bundle recovery，并在没有新 Evidence 时以 `no_new_evidence`
诚实停止；但 Evidence、Citation、grounded source 与 required-aspect delta 全为 0，post-recovery gate 未
到达。因此：

```yaml
candidate_v1_1:
  exact_verdict: rejected
  local_behavior_change_observed: true
  grounded_research_outcome_improvement: false
  active_or_shadow: false
```

# 5. Experiment and Budget Integrity

关键冻结身份：

```yaml
stage_2_effective_freeze: 0c72277e7b30bac68800ef27acc9e8d52222efd6
R1_freeze: 789cf176adcc8c7a66dccbf0c507e875537bcc1a
R1_E1_freeze: cbc8917aaa625897ae7e718e7d15e784aeeb0705
candidate_v1_1_sha256: c40c4df488c15801eb521530f16833158028cef076ba348ce811f3a8794d4efc
treatment_v1_1_sha256: cdb52593fec31876df2a8fe73ea67cbccbc21d0fd22ef83466aa486927f4254f
evaluator_sha256: 4227dafd04e2d0e8fb6909f144a853919105bf7f50a3a25e2b3932d4c5d51c08
R1_E1_pair_evaluation_sha256: 9eaeb5c4382b9ef7a67bb0ee7bbfcf80081e4379110d01149a0d291a3e7f1afc
```

R1+E1 累计为 8 logical / 8 HTTP calls、11,667 input / 942 output tokens、6 tool calls、
USD `0.001311757`、unknown reservations 0。各阶段完整 Provider/budget accounting 继续以对应 freeze、private
receipt、run manifest 和 acceptance decision 为准；raw private Query/Evidence/Provider response 不进入 Git。

# 6. Reserve and Contamination Boundary

```yaml
reserve:
  ciphertext_sha256: d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c
  key_mode: "000"
  access_log_entries: 4
  post_freeze_access_entries: 0
  runs: 0
  semantic_assignment: none
heldout_related: not_run
unrelated_regression: not_run
negative_transfer: not_measured
```

四个 reserve tasks 始终 sealed，未参与 discovery、Attribution、Candidate 设计或调参，也未形成 semantic
held-out split。没有数据污染被拿来补足作品集结论。

# 7. Promotion Protection

两个 Candidate 均未注册进 Product Runtime；默认 No-Skill path 未改变。V5-D 没有 active/shadow policy、
Skill repository、Progressive Disclosure 产品层或 rollback target，因为这些都以 validated Candidate 为前提。

Stage 3 Entry Gate 未满足，不进入 Controlled Use、human promotion 或 product rollback demonstration。

# 8. Git and Verification

`codex/v5-d@68fd655` 只增加 V5-D experiment-only scripts/tests/artifacts/reports；相对共同基线的产品 `src`
delta 为 0，产品 `src` tree 始终为 `41ccf576cdd6ce6282b0eb8d35a31b75bc0cad01`。

Main 的 merge preflight 显示 Main/V5-D 分叉 `10/9` commits、修改文件重叠 0，preview tree
`1992bffe9cffaeba6356d53f4afd2544c5b504fa`。`--no-ff` merge commit
`2d10844eee564af830bf38b4c792d2834381de63` 的 tree 与 preview 相同。

合并后：

```yaml
V5_D_directed_tests: 34_passed
full_default_no_provider: 1775_passed
script_compile: passed
ledger_JSONL_and_whitespace: passed
provider_runs_during_closeout: 0
```

# 9. Explicitly Unproven

V5-D 不得被描述为已经证明：

- validated Search Skill / Policy；
- related-task generalization；
- unrelated-task regression safety；
- negative-transfer protection；
- active / shadow policy；
- stable user benefit；
- D04 Candidate behavior；
- V5-A compound-query limitation 属于 policy failure 或已经解决。

# 10. Final Status

```yaml
final_closeout:
  status: closed_no_validated_candidate
  technical_goal_of_controlled_falsification: achieved
  product_goal_of_validated_policy_improvement: not_achieved
  candidate_v1_0: rejected
  candidate_v1_1: rejected
  reserve_consumed: false
  stage_3_entered: false
  mainline_evidence_integrated: true
  further_execution_authorized: false
```
