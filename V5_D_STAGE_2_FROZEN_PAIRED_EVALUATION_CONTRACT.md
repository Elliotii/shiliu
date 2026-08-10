# Shiliu V5-D Stage 2 Contract — Frozen Paired Evaluation

> Status: completed_and_main_accepted_rejected
> Stage: Stage 2 — Frozen Paired Evaluation
> Authorized at: 2026-08-11
> Owner: persistent V5-D Version Session with isolated Reserve Custodian boundary
> Execution branch: `codex/v5-d`
> Stage 1 accepted execution head: `900953df64676a5d1438743918ac806961dfff14`
> Candidate: `V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001` v1.0.0
> Candidate artifact SHA-256: `6bcda6e5c5428c304807f067570c9acb7977cbd991c355edaeb9346d3d13cdbe`
> Active/shadow product registration authorized: false
> Live database write authorized: false
> Stage 3 authorized: false
> Effective freeze: `0c72277e7b30bac68800ef27acc9e8d52222efd6`
> Accepted execution head: `254d72a03a1251ee0d08cac49d100b91b5de7593`
> Exact verdict: `rejected`

---

# 1. Goal and Claim Boundary

Stage 2 的唯一目标是验证：

> 冻结 Candidate 相比冻结 No-Skill Baseline，是否在一个未参与 Candidate 设计的 Related Task 上改善
> 真实 Research Outcome，同时在两个 Unrelated Tasks 上保持零材料性负迁移。

本 Stage 不是 Candidate 优化或调参阶段。即使 verdict 为 `validated`，Candidate 仍不得成为 Active 或
Shadow Product Policy。

```yaml
claim_scope:
  bounded_demo: true
  broad_generalization_claim: false
  statistical_generalization_claim: false
  environment_shift_required: false
```

# 2. Accepted Input and Entry Gate

```yaml
accepted_input:
  failure_family: non_progress_search_repetition_without_recovery
  attribution_id: V5D-S1-ATTRIBUTION-20260811-A
  hypothesis_id: V5D-S1-HYPOTHESIS-20260811-A
  candidate_id: V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001
  candidate_version: 1.0.0
  candidate_status: proposed_non_active
entry_gate:
  stage_1_accepted_by_main: true
  execution_head_clean: true
  candidate_artifact_hash_verified: true
  reserve_ciphertext_and_key_seal_intact: true
  reserve_runs_before_stage_2: 0
  post_freeze_reserve_access_before_stage_2: 0
```

Session 开始前须核验实际 branch、HEAD `900953d`、clean tree、Candidate hash 与 reserve seal。材料性不一致
时停止，不自行改变 Candidate 或 custody。

# 3. Mandatory Phase Order

```text
A. implement minimal non-product Treatment + directed mechanical tests
→ B. freeze Candidate/Treatment/Baseline/Scaffold/Evaluator/Assignment Rule/Budget in a clean local commit
→ C. run frozen D02/D04 source diagnosis pairs
→ D. if source mechanism gate passes, isolated Custodian opens and assigns reserve
→ E. freeze split/access manifest without exposing held-out semantics to Candidate designer
→ F. run counterbalanced held-out baseline/treatment pairs under custody
→ G. evaluate Research Outcome, regression, negative transfer, invalid runs and contamination
→ H. issue one exact Candidate verdict
→ I. submit Stage 2 Closeout and stop
```

如果 frozen Candidate 在 D02/D04 source gate 已不能改变预期 first-actionable mechanism，或造成 protected
boundary violation，应直接 `rejected`，不打开 reserve。Source improvement 永不计入 generalization。

# 4. Minimal Treatment Implementation Boundary

允许在 `codex/v5-d` 创建最小 Candidate Treatment 和定向测试，但必须满足：

- 只能由显式 Stage 2 experiment runner/flag 选择；默认产品路径不可发现、不可自动加载；
- 不注册为 Active/Shadow Candidate，不创建 product active pointer；
- 不修改 live Prompt/Provider route、Evidence/Citation/Verifier/currentness、tool permission 或用户 authority；
- 不创建通用 Skill Repository、generic Eval/Harness/Learning platform；
- Candidate 缺失、身份不符、不适用、rejected 或 rolled back 时回到完全未改的 No-Skill Baseline；
- 只实现 `V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001`，不创建第二 Candidate 或变体生成器；
- treatment-specific Context/Prompt instruction 如确有必要，必须在 freeze manifest 中逐项哈希并受 Candidate
  modification rule 约束。

允许的测试只覆盖 treatment plumbing、Candidate identity、applicability、Evidence-delta semantics、
materially-different-target、one-recovery bound、honest stop、No-Skill fallback 与 protected boundaries。

# 5. Candidate and Experiment Freeze

任何 reserve body/result 对 Candidate designer 可见之前，必须创建一个 clean local freeze commit，并冻结：

```yaml
candidate_freeze:
  candidate_id:
  version:
  artifact_hash:
  trigger:
  applicability:
  required_preconditions:
  procedure:
  materially_different_target_definition:
  recovery_rule:
  recovery_count:
  stop_rule:
  forbidden_behavior:
  baseline_fallback:
  protected_boundaries:
experiment_freeze:
  experiment_id: V5D-S2-PAIRED-EVAL-001
  baseline_version:
  treatment_version:
  control_logic_commit:
  source_and_tests_tree:
  prompt_versions:
  provider_configuration:
  retrieval_version:
  corpus_snapshot:
  source_version_set:
  evaluator_version: v5-d-stage2-paired-grounded-outcome-evaluator-v1
  dataset_assignment_rule:
  invalid_run_policy:
  arm_order_rule:
  budget_policy:
```

Freeze 后以下均为 Candidate modification：trigger/applicability/material target/recovery procedure 或次数/stop/
fallback/Candidate-specific Prompt 或 Context instruction 的改变，以及根据 held-out behavior 修复 Candidate
路径。任何 modification 都关闭当前实验；已打开 held-out 不得作为新版本独立泛化证据。

# 6. Source Diagnosis Gate

冻结后先对 D02、D04 执行各一组 Baseline/Treatment pair，用于：

- treatment plumbing 与 identity；
- first actionable mechanism 是否真的改变；
- Research Outcome 而非仅 termination reason 是否改善；
- protected boundaries 与 per-case overhead。

两项 source treatment 都必须：

- 消除已归因的 non-incremental follow-up；
- 相对 valid baseline 至少增加 1 个 frozen required aspect 和 1 个 current grounded citation；
- 不以更长答案、更多 hits 或更多搜索代替 outcome；
- 保持 currentness、lineage、stop correctness 与预算门禁。

任一 valid source pair 失败则 Candidate verdict 为 `rejected`；若必要 arm 在一次合法 identical-scaffold
replacement 后仍 invalid，则为 `insufficient_evidence`。两者均不打开 reserve。

# 7. Reserve Custody and Assignment

仅在 Candidate、Treatment、Baseline、Scaffold、Evaluator、assignment rule 与 budget 全部冻结，且 source
gate 通过后，允许隔离 Custodian：

1. 验证 ciphertext/key/access identity；
2. 在不向 Candidate designer 暴露 body/Gold/Evidence refs 的边界内解封；
3. 只依据冻结任务语义而非任何运行结果分配：`1 related + 2 unrelated + 1 spare`；
4. 生成 split IDs/hashes/access manifest，重新隔离 bodies/Gold/Evidence/evaluator inputs；
5. 执行 held-out paired runs 与 frozen evaluation；
6. 只向 Version Session 返回 redacted identities、metrics、invalid/contamination state 和 verdict evidence。

如果不能形成该无污染 split，必须在 Provider held-out run 前输出
`insufficient_uncontaminated_split`，对应 Candidate verdict `insufficient_evidence`。不得重定义 Related/
Unrelated 或临时增加 Case。

Spare 只能替换 pre-run contamination/eligibility failure，不能按结果替换。Custody access log 必须记录每次
decrypt/assignment/run/evaluation/reseal；原 Candidate designer 不得读取 held-out body、Gold、Evidence refs、
raw Provider response 或 arm-level semantic output。

# 8. Held-out Contamination Boundary

一旦 reserve assignment 或 held-out run 开始，禁止：

- 修改 Candidate、Trigger、Procedure、Stop、applicability、material-target definition；
- 修改 evaluator、metric weight、promotion threshold 或 success condition；
- 根据 held-out failure 修复 Candidate-only logic 后重跑相同 Case；
- 让 treatment 读取 split label、Gold、Evidence refs、Evaluator 或 reserve metadata semantics；
- opportunity resampling、best-of rollout 或因结果不好而删除 valid arm。

若需要 Candidate v1.1，当前实验立即关闭；已暴露 held-out 只能降级为 development evidence。

# 9. Frozen Paired Design

```yaml
experiment:
  experiment_id: V5D-S2-PAIRED-EVAL-001
  source_diagnosis_pairs: 2
  heldout_related_pairs: 1
  heldout_unrelated_pairs: 2
  sealed_spare: 1
  source_cases_are_generalization_evidence: false
  valid_arm_cap: 10
  outer_attempt_cap_including_replacements: 20
  replacement_per_arm: 1
  arm_order: sha256_experiment_id_plus_case_id_parity
  provider: current_product_DeepSeek_only
  provider_switch_allowed: false
  model_prompt_retrieval_corpus_evaluator_environment_shift: frozen
```

每个 arm 仅在 Provider/Infrastructure/Evaluation invalid 且 Candidate/scaffold/code/evaluator 完全未变时允许
一次 replacement。Candidate-caused failure、低质量 valid result 或无改善不得重跑。

# 10. Provider, Tool, Token and Cost Budget

```yaml
budget:
  valid_arms: 10
  outer_attempts_including_invalid_replacements: 20
  logical_provider_calls: 260
  HTTP_attempts: 520
  input_tokens: 2750000
  output_tokens: 350000
  deep_tool_calls: 250
  wall_time_seconds: 14400
  paid_cost_hard_stop_usd: 0.50
  paid_cost_reserve_stop_usd: 0.40
  unresolved_reservations_accounted: true
```

任一 cap 先到即停止，不得拆包规避。允许现有 Keychain credential 的 Runtime-only 只读访问，但不得显示、
复制或记录值。Calls/tokens/HTTP/tool/USD 必须按 arm、pair 和 whole experiment 独立入账；unknown reservation
按 worst case 保留。不得无限 rollout 或选择最好结果。

# 11. Frozen Evaluator and Success Gates

Evaluator 使用 deterministic contract checks + isolated manual frozen-aspect review；不使用 model judge。
Candidate/treatment 不得读取 Gold、aspect refs、Evidence refs、split 或 thresholds 的私有部分。

每个 arm 至少评估：

- frozen required-aspect coverage；
- current grounded Evidence/Citation validity；
- materially new recovery 与 current Evidence delta；
- source target/diversity（任务要求时）；
- counterexample/limitation preservation；
- final answer status 与 partial/insufficient stop correctness；
- Provider/tool/token/USD overhead；
- invalid-run 与 protected-boundary state。

Candidate `validated` 必须同时满足：

1. D02、D04 每项满足 source gate；
2. held-out related 相对 valid baseline 至少增加 1 个 frozen required aspect 和 1 个 current grounded
   citation，并且 recovery/stop correctness 通过；
3. 两个 unrelated 在 answer status、required aspects、grounded citations、counterexample preservation、
   source diversity 与 stop correctness 上均无材料性回归，negative transfer 为 `0/2`；
4. 每项 treatment 相对 paired baseline 不超过 `+2` logical calls、`+4` HTTP attempts、`+25,000` input、
   `+5,000` output、`+1` executed tool call，Provider route/permission delta 为 0；
5. currentness、lineage、identity、contamination、invalid-run 与总预算全部通过。

以下直接 `rejected`：任何 valid source/related 不能改善 grounded outcome；任何 unrelated 材料性负迁移；
Candidate-caused boundary violation；Candidate-caused budget overrun；只减少 repetition/更早 stop 却降低
Evidence coverage 或 answer quality。

以下为 `insufficient_evidence`：无法形成 clean split；必要 arm 经一次合法 replacement 后仍 invalid；总预算
或基础设施在不能归责 Candidate 时阻止完整证据；实验身份或 contamination 失效但尚无 Candidate-caused
rejection evidence。

# 12. Verdict and Report

最终必须给出一个：

```yaml
candidate_verdict:
  - validated
  - rejected
  - insufficient_evidence
```

若 operational exit 是 `invalid_run` 或 `insufficient_uncontaminated_split`，Candidate verdict 映射为
`insufficient_evidence`。不得输出“基本有效”。

`V5_D_STAGE_2_CLOSEOUT_AND_EVALUATION_REPORT.md` 至少包含：

- freeze commit、Candidate/Treatment/Baseline/Scaffold/Evaluator/Corpus/Provider identities；
- source diagnosis pair results（明确非泛化）；
- reserve assignment/custody/access/reseal；
- held-out related result；
- unrelated regression 与 negative transfer；
- Research Outcome metrics 与 one-recovery/stop 风险；
- per-arm/pair/total Provider、token、tool、cost 和 unknown reservation；
- invalid/replacement、contamination audit；
- exact Candidate verdict、claim boundary、known limits 与 Stage 3 recommendation。

Raw held-out bodies、Gold、Evidence refs、Provider responses、credentials、private evaluator inputs 和 temp DB
不得提交 Git。允许一个 freeze commit 与一个 closeout/evidence commit，最终 working tree 必须 clean。

# 13. Non-authorizations and Stop

```yaml
active_product_registration: false
shadow_product_registration: false
production_promotion: false
stage_3_execution: false
generic_skill_platform: false
generic_eval_platform: false
generic_agent_learning_platform: false
live_database_write_or_migration: false
push: false
merge: false
tag: false
```

Stage 2 完成后停止并等待 Main 有限验收。即使 Candidate 为 `validated`，也不得进入 Stage 3。

## Closeout Status

Stage 2 已按本 Contract 停止于第一个决定性有效 source-pair failure。D02 Treatment 有局部 grounded
Citation 增量，但 required-aspect、source-diversity 与 recovery/stop gates 未通过，因此 exact verdict 为
`rejected`。D04 和 reserve/held-out 未运行；reserve 始终 sealed。Main 已在
`V5_D_STAGE_2_MAIN_SESSION_ACCEPTANCE_DECISION.md` 接受该实验与拒绝判定。Stage 3 Entry Gate 未满足。
