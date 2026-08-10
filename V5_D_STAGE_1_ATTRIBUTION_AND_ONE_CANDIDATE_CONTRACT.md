# Shiliu V5-D Stage 1 Contract — Attribution and One Candidate

> Status: completed_and_accepted_by_main
> Stage: Stage 1 — Attribution + One Candidate Contract
> Authorized at: 2026-08-11
> Owner: persistent V5-D Version Session
> Execution branch: `codex/v5-d`
> Stage 0 accepted execution head: `fbf7a0d56816797d0ad481b2381b6d5aba81657c`
> Governing acceptance: `V5_D_STAGE_0_MAIN_SESSION_ACCEPTANCE_DECISION.md`
> Product runtime behavior change authorized: false
> Provider runs authorized: false
> Reserve open authorized: false
> Stage 2 execution authorized: false
> Accepted execution head: `900953df64676a5d1438743918ac806961dfff14`
> Main acceptance: `V5_D_STAGE_1_MAIN_SESSION_ACCEPTANCE_DECISION.md`

---

# 1. Goal and Accepted Input

Stage 1 的唯一目标是：

```text
Accepted Failure Family
→ Trace-level Attribution
→ First Actionable Failure
→ Alternative Cause Review
→ Falsifiable Improvement Hypothesis
→ One Candidate Search/Research Policy Contract
```

必须遵守 `Attribution first, Candidate second`。不得因 termination reason 是 `repeated_search`，预设
“重复 N 次后换 Query/Stop”等 heuristic，再反向解释 Trace。

```yaml
accepted_input:
  failure_family: non_progress_search_repetition_without_recovery
  initial_surface: follow_up_strategy
  supporting_discovery_cases:
    - D02
    - D04
  candidate_effectiveness: unproven
  active_skill_or_policy: none
```

# 2. Entry Gate

```yaml
entry_gate:
  stage_0_accepted_by_main: true
  failure_family_qualified: true
  execution_head_clean: true
  discovery_trace_evidence_available: true
  reserve_ciphertext_and_key_seal_intact: true
  reserve_runs: 0
  post_freeze_reserve_access: 0
```

Session 开始前须核验实际 branch 为 `codex/v5-d`、HEAD 为 `fbf7a0d`、working tree clean，并记录
reserve ciphertext hash、key mode 与 access log 未变化。材料性不一致时停止，不自行修复 custody。

# 3. Authorized Inputs and Prohibited Inputs

允许读取：

- Stage 0 已授权 discovery-side Trace、projection、Experience/EvidenceUse、outer audit、Provider receipts
  和 qualification artifact；
- D02/D04 supporting artifacts，以及 D01/D03 为 alternative-cause/control 所必需的 bounded evidence；
- V5-A/B 已有 Trace、Progress/No-progress、Goal Audit、Experience lifecycle、authority、receipt、provenance
  和 durability 源码/测试；
- 当前 Charter、Program State、Decision Ledger、Stage 0 Report 与 Main Acceptance。

禁止读取或推断：

```yaml
sealed_reserve:
  task_count: 4
  runs: 0
  body_access: prohibited
  gold_access: prohibited
  evidence_reference_access: prohibited
  result_access: prohibited
  key_read_or_permission_change: prohibited
  decrypt: prohibited
```

Stage 1 只能使用 reserve 的既有 redacted ID/hash/archetype/access state 做 custody 核验和 split method
占位；不得使用其语义内容形成或调整 Attribution、Hypothesis、Candidate、trigger、procedure、stop rule
或 applicability。

# 4. Mandatory Work Order

```text
Freeze authorized source artifact identities
→ reconstruct D02 and D04 trace timelines
→ identify earliest actionable divergence per case
→ compare common and differing mechanisms
→ review alternative causes
→ decide attribution confidence or reclassify
→ freeze one falsifiable hypothesis
→ only then define one proposed non-active Candidate
→ prepare Stage 2 frozen paired-evaluation design
→ validate package and custody
→ submit one Stage 1 closeout/evidence package
```

Candidate 字段在 Attribution 和 Hypothesis 冻结前不得定稿。分析过程中可以记录多个 alternative
explanations，但最终最多形成一个 Candidate family。

# 5. Failure Attribution Contract

Attribution 必须明确：

```yaml
failure_attribution:
  failure_family:
  source_trace_ids:
  source_trace_hashes:
  first_actionable_step_per_case:
  earliest_common_failure_mechanism:
  responsible_policy_surface:
  observed_no_progress_signal:
  expected_but_missing_policy_decision:
  grounded_outcome_impact:
  alternative_causes:
  exclusions_and_evidence:
  attribution_confidence:
  unresolved_uncertainties:
```

至少显式比较：

- Follow-up query/action 是否没有形成信息增量；
- Runtime 是否已观察 no-progress，但未选择合适 recovery/follow-up strategy；
- Outer Audit / missing aspect 是否未映射为下一 Search target；
- Continue/Stop 是否错误，本应 honest partial stop 却继续重复；
- corpus/data coverage、retrieval/index implementation、Runtime implementation、Provider、evaluator 或
  infrastructure 是否更可能负责。

`first actionable step` 必须是 Trace 中最早可由 Search/Research Policy 改变、且可能改变 grounded
outcome 的决策点，不能只引用最后的 deterministic guard。不能排除的 alternative cause 必须保留为
uncertainty；若主要原因被重新归类到 Provider/Infrastructure/Retrieval/Corpus，结果必须是
`failure_reclassified` 并停止 Candidate 创建。

# 6. Falsifiable Improvement Hypothesis

只有 Attribution 足够时才能冻结：

```yaml
improvement_hypothesis:
  target_component:
  failure_pattern:
  causal_hypothesis:
  applicable_scope:
  non_applicable_scope:
  expected_behavior_change:
  expected_grounded_outcome_change:
  risks:
  falsification_conditions:
  evidence_that_would_reclassify_the_failure:
```

Hypothesis 必须能由 Stage 2 的 frozen baseline/treatment comparison 证明错误。不得使用“更会反思”、
“搜索更智能”或“输出更完整”等不可测描述。

# 7. One Candidate Contract

本 Stage 最多形成一个 domain-specific Search/Research Policy Candidate：

```yaml
candidate:
  candidate_id:
  candidate_type:
  version:
  lifecycle_status: proposed_non_active
  applicability:
  trigger:
  required_preconditions:
  procedure:
  stop_conditions:
  forbidden_behavior:
  baseline_fallback:
  source_experience:
  attribution_identity:
  hypothesis_identity:
  protected_boundaries:
  expected_cost_delta:
  expected_tool_provider_delta:
  rollback_or_rejection_behavior:
```

Candidate 必须解释为什么它针对 first actionable mechanism，而不是围绕 `repeated_search` termination
reason 的计数补丁。它不得修改 Evidence/Citation currentness、Verifier、held-out split、Evaluator、
Promotion authority 或用户控制权。

允许创建一个 versioned declarative Candidate package 和必要的机械 validator/tests，但它必须：

- 不注册到 active/shadow Runtime；
- 不改变当前 No-Skill 产品行为、Prompt 或 Provider route；
- 不创建通用 Skill Repository、curator、ranking、retrieval 或 learning platform；
- 不包含第二个 Candidate family 或自动变体生成；
- 在 package 缺失、无效或不适用时确定性回到既有 No-Skill baseline。

# 8. Stage 2 Frozen Evaluation Design — Plan Only

Stage 1 必须形成可审阅、尚未执行的 Stage 2 plan：

```text
Frozen No-Skill Baseline
vs
Frozen Candidate Treatment
```

至少冻结或明确冻结方法：

- source/diagnosis cases 与其非泛化地位；
- 真正 held-out related 与 unrelated regression 的 assignment methodology、minimum counts 与不足时
  的 honest-stop rule；
- Candidate freeze、split assignment、Gold/Evidence/evaluator access 的严格先后顺序；
- experiment ID、scaffold/code/candidate/baseline fingerprints；
- evaluator/judge、required-aspect coverage、grounded Evidence/Citation、no-progress recovery、
  counterexample preservation、source diversity、stop correctness；
- cost/tool/Provider overhead 和不得用更多文字/搜索次数替代质量的规则；
- invalid/provider/infrastructure run classification、replacement 和 accounting；
- related-task generalization、unrelated regression、negative-transfer thresholds；
- contamination、Candidate modification 后 held-out 失效、rollback/reject 规则；
- 精确 Provider/tool/token/USD 预算提案。

Stage 1 不得打开 reserve 来完成 assignment。只可冻结由未来受隔离 Custodian 在 Candidate 完全冻结后
执行的 assignment rule；若 sealed pool 无法满足所需 split，应在 Stage 2 启动前诚实停止。Environment
Shift 仅在 Candidate applicability 必需时提出，不是 Portfolio-ready 硬门。

# 9. Reuse and Complexity Boundary

优先复用：

```text
V5-A Trace / Progress / Goal Audit / receipt / durability
V5-B Experience / append-only lifecycle / provenance
V5-C explicit authority and rollback patterns where applicable
```

不得复制第二套 Trace、Experience、Eval、Harness、Skill Repository 或 Promotion authority。Stage 1 默认
不需要上游下载或新 adoption；只有出现现有本地机制无法回答的具体缺口时，先记录 JIT research question
和 bounded proposal，不自行下载、接入或扩张平台。

# 10. Tests and Mutation Boundary

允许：

- docs/evidence package；
- versioned proposed Candidate definition；
- 只验证 schema、identity、lineage、protected boundaries、inactive status、baseline fallback、custody 和
  Stage 2 plan completeness 的定向机械 tests；
- execution branch 上的本地 commit。

不允许：

```yaml
provider_or_keychain_access: false
provider_evaluation_runs: false
reserve_open_or_run: false
stage_2_execution: false
candidate_product_activation: false
candidate_shadow_runtime: false
candidate_promotion: false
live_database_write_or_migration: false
product_prompt_or_provider_route_change: false
generic_skill_eval_or_harness_platform: false
push_merge_tag: false
```

若归因必须新增 Provider run，Session 只能提交包含理由、scaffold、预算和 contamination 影响的 Contract
Amendment proposal，然后停止等待用户授权。

# 11. Exit Results and Gate

Stage 1 只能输出一个：

```yaml
stage_1_result:
  - candidate_contract_ready
  - attribution_insufficient
  - failure_reclassified
  - blocked_by_infrastructure_or_data
```

`candidate_contract_ready` 必须同时满足：

- first actionable failure 有 Trace/hash 支撑；
- 主要 alternative causes 已审查；
- Attribution 与 confidence 明确；
- 一个 causal Hypothesis 可证伪；
- 一个 Candidate 为 versioned、proposed、non-active；
- applicability、stop、forbidden behavior 和 baseline fallback 明确；
- Stage 2 paired evaluation plan 可执行且未运行；
- reserve ciphertext/key/access log 仍完整且 runs 0；
- Provider、live DB、active/shadow Runtime 和产品行为 mutation 均为 0。

任一关键条件不满足时不得为推进路线强行产生 Candidate。

# 12. Required Submission

默认保持精简：

1. 一个完整 `V5_D_STAGE_1_CLOSEOUT_AND_EVIDENCE_PACKAGE.md`，包含 Attribution、alternative causes、
   Hypothesis、Candidate Contract、为何不是简单 heuristic、Stage 2 frozen design、custody、成本/mutation、
   known limits 和 Stage 2 建议；
2. 若机械验证需要，可增加一个 versioned structured Candidate artifact 与最小定向 test；
3. 更新 `V5_D_CURRENT_STATE.md` 与 `V5_D_DECISION_LEDGER.md`；
4. 创建一个清晰的本地 Stage 1 commit，并保持 working tree clean。

Stage 1 已完成并由 Main 接受，结果为 `candidate_contract_ready`。唯一 Candidate 保持
`proposed_non_active`，Stage 2、reserve 解封、Provider、treatment 与产品激活仍未授权。
