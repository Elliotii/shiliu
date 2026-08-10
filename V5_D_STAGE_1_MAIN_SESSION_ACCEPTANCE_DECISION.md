# Shiliu V5-D Stage 1 Main Session Acceptance Decision

> Stage: Stage 1 — Attribution + One Candidate Contract
> Decision: accept
> Accepted by: Shiliu V5 Main Codex Session
> Accepted at: 2026-08-11T01:56:08+08:00
> Execution branch: `codex/v5-d`
> Accepted execution head: `900953df64676a5d1438743918ac806961dfff14`
> Stage 2 authorized: false
> Product implementation started: false

---

# 1. Accepted Result

```yaml
stage_1:
  decision: accept
  result: candidate_contract_ready
  attribution_id: V5D-S1-ATTRIBUTION-20260811-A
  attribution_confidence: moderate_high
  hypothesis_id: V5D-S1-HYPOTHESIS-20260811-A
  candidate_id: V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001
  candidate_version: 1.0.0
  candidate_status: proposed_non_active
```

Main 接受 Stage 1 已满足其合同：它在冻结 Candidate 之前先完成 Trace-level Attribution、first
actionable failure 与 alternative-cause review，随后形成一个可证伪 Hypothesis、一个非 active Candidate
Contract，以及只规划未执行的 Stage 2 paired-evaluation design。

# 2. Accepted Attribution

Main 接受以下 first actionable mechanism 作为进入 Stage 2 验证的 `moderate_high` Attribution：

> 在 evidence-seeking action 已产生零 current transcript-Evidence 增量、用户目标仍有未完成 Evidence
> 工作、历史 action keys 与剩余预算均可见时，下一 follow-up decision 没有选择 materially new
> evidence-bearing target，也没有 honest stop。

D02 与 D04 的 first actionable step 都位于最终 `repeated_search` guard 之前；guard 是后果，不是首因。
D02 在一次失败的 scoped transcript search 后重选早先 navigation，D04 在 empty navigation/fallback 后
立即重选同一 navigation。D03 的同环境 grounded partial success 与 D01 Provider-domain failures 支持把
整体 Runtime/Provider 不健康排除为共同主因。

Main 同时保留报告中的不确定性：完整 DecisionView message 未持久化，preliminary Evidence/QueryPlan
handoff 可能是放大因素，两个 supporting cases 数量有限，Provider choice 与 Policy constraint 的因果份额
仍需 paired treatment 才能区分。因此该 Attribution 足以接受 Stage 1，但不是最终因果证明。

# 3. Accepted Hypothesis and Candidate Boundary

Main 接受 `V5D-S1-HYPOTHESIS-20260811-A` 为可证伪 Hypothesis，并接受唯一 Candidate：

```yaml
candidate:
  id: V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001
  sha256: 6bcda6e5c5428c304807f067570c9acb7977cbd991c355edaeb9346d3d13cdbe
  lifecycle_status: proposed_non_active
  runtime_registration: none
  active: false
  shadow: false
  baseline_fallback: existing_No-Skill_unchanged
  effectiveness: unproven
```

该 Candidate 不是“重复 N 次后换 Query/Stop”的计数补丁：它在 termination 之前依据 current Evidence
delta、未完成用户目标和 materially different target 作一次 bounded recovery 决策；若无合法 target 或
recovery 无 Evidence 增量，则 honest partial/insufficient stop。它不依赖 termination reason 或 repeat count。

Candidate 的适用性仍可能过宽、一次 recovery 后停止仍可能过早，这些不是文档返工理由，而是 Stage 2
必须用 held-out related、unrelated regression、negative transfer 与成本门禁实际证伪的风险。

# 4. Independent Mechanical Review

Main 独立核验：

- `fbf7a0d..900953d` 只修改四个 V5-D 文档/声明式 artifact，没有产品源码或测试变更；
- `src` tree `41ccf576…` 与 `tests` tree `4579751d…` 在 Stage 1 前后完全一致；
- Candidate JSON 可解析，文件 SHA-256 与报告一致，只有一个 Candidate，状态为
  `proposed_non_active`，runtime registration 为 null，active/shadow 均 false；
- Candidate 明确 No-Skill fallback、protected boundaries、source Trace lineage 与 Provider/tool/cost delta；
- V5-D Ledger 12 条 JSONL 可解析且 ID 唯一；
- isolated Stage 0 DB 仍为 30 side effects（29 succeeded、1 unknown）、integrity ok、FK 0，没有 Stage 1
  Provider activity；
- execution branch clean，未 Push、Merge 或 Tag。

# 5. Reserve and Eval Integrity

```yaml
reserve:
  ciphertext_sha256: d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c
  key_mode: "000"
  plaintext_present: false
  access_log_entries: 4
  post_freeze_access_entries: 0
  runs: 0
  remains_sealed: true
```

Stage 1 没有读取或运行 reserve。报告中的 `1 related + 2 unrelated + 1 spare` 只是未来 Custodian 在完整
Candidate/scaffold/evaluator freeze 后应用的 assignment methodology，不是已完成 semantic split。

# 6. Stage 2 Plan Status and Known Limits

Main 接受 `V5D-S2-PAIRED-EVAL-001` 作为后续授权审查的计划，而不是执行授权或预算批准。其核心门禁
完整覆盖：source diagnosis 不算泛化、held-out related、两项 unrelated regression、negative transfer 0/2、
grounded aspect/citation 改善、stop correctness、invalid-run separation、contamination、experiment identity、
成本和 protected boundaries。

```yaml
known_limits:
  candidate_effectiveness: unproven
  heldout_related_generalization: unproven
  unrelated_regression: unproven
  negative_transfer: unproven
  provider_reproducibility: unproven
  product_integration: not_started
  heldout_related_case_count: 1
  statistical_strength: bounded_demo_not_broad_claim
  treatment_implementation: not_created_or_frozen
```

单个 held-out related case 是当前 sealed pool 在保留两项 unrelated 与一个 spare 时的最小可行证据；若
未来无法按冻结 methodology 形成该 split，Stage 2 必须在任何运行前以
`insufficient_uncontaminated_split` 停止。

# 7. Authorization After Acceptance

```yaml
stage_1:
  status: accepted
  execution_closed: true
stage_2:
  contract_preparation_authorized: false
  treatment_implementation_authorized: false
  reserve_open_authorized: false
  provider_runs_authorized: false
  paired_evaluation_authorized: false
candidate:
  product_activation_authorized: false
  shadow_authorized: false
  promotion_authorized: false
live_database_write_or_migration_authorized: false
merge_push_tag_authorized: false
```

持续 V5-D Version Session 保留但应停止。Stage 2 必须由用户再次明确授权后才能准备或执行；Main 本次
没有批准 USD 0.50 预算、reserve assignment、treatment implementation 或 paired runs。
