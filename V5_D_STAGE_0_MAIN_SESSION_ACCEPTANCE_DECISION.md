# Shiliu V5-D Stage 0 Main Session Acceptance Decision

> Stage: Stage 0 — Bounded Entry Calibration
> Decision: accept
> Accepted by: Shiliu V5 Main Codex Session
> Accepted at: 2026-08-11T01:03:11+08:00
> Execution branch: `codex/v5-d`
> Accepted execution head: `fbf7a0d56816797d0ad481b2381b6d5aba81657c`
> Stage 1 authorized: false
> Product implementation started: false

---

# 1. Accepted Outcome

Main Session 接受 Stage 0 的退出判断：

```yaml
stage_0:
  decision: accept
  exit_decision: qualified_failure_family_found
  qualified_failure_family: non_progress_search_repetition_without_recovery
  initial_surface: follow_up_strategy
  supporting_discovery_cases:
    - D02
    - D04
  empirical_entry_gate_met: true
```

该接受只表示：两个不同的有效 discovery tasks 在健康的 case-local corpus、index、Runtime、Provider
与 evaluator 边界内，呈现了同一 `follow_up_strategy` surface 上可重放、可归因的 non-progress
repetition，并以 `repeated_search` 结束。它足以允许未来 Stage 1 研究一个可证伪 Hypothesis；不表示
Candidate 已定义、有效或可进入产品。

# 2. Limited Evidence Review

Main Session 完成了 Contract 要求的有限抽查：

- `98ee944..fbf7a0d` 仅增加或更新三个 V5-D Stage 0 文档，未修改产品代码、测试、Schema、Prompt 或 UI；
- 四个有效 discovery outcomes 与一个 Provider-invalid replacement 均被诚实记录；一个 pre-run launcher
  event 发生在 Task、Keychain 和 Provider 之前；
- D02、D04 的 redacted Trace/projection hashes、first-actionable evidence 和替代原因排除与 qualification
  artifact 一致；D01 Provider failure/quality events 与 Search Policy family 隔离，D03 作为同环境下的
  `valid_partial` 对照；
- committed usage 为 29 logical calls、87,322 input tokens、12,793 output tokens、USD 0.034427524；
  包含 unresolved reservation 的 accounted usage 为 30 calls、110,358 input、16,889 output、
  USD 0.088764244，低于 USD 2 用户上限与 USD 0.50 Runtime 上限；
- 隔离数据库为 schema 14，`integrity_check=ok`、FK violations 0；30 个 Provider side effects 中
  29 `succeeded`、1 `unknown`，与报告一致；现有 Runtime records 停在预期的
  `authorized_evaluator_required`/fail-closed 边界，Main 未人为终结或改写产品状态；
- live scheduled sync 在窗口内自然推进一次，但 post-run corpus/index identity、157 videos、140 completed、
  1,633 retrieval units、integrity 与 FK 均未出现材料性漂移；Stage 0 未写 live DB。

Main 未重跑 Provider，也未读取 raw Task bodies、Gold、完整 Evidence、raw Provider response 或凭据。

# 3. Reserve and Contamination Decision

```yaml
sealed_reserve:
  reserve_case_count: 4
  reserve_runs: 0
  post_freeze_access_events: 0
  plaintext_present: false
  candidate_context_received_reserve_body: false
  ciphertext_sha256: d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c
  key_mode: "000"
  remains_sealed: true
```

Main 只核对 redacted manifest、custody/access policy、seal receipt、access log 和 ciphertext/hash；没有
解密 reserve manifest、读取 key 或查看 reserve bodies/Gold/results。报告中的 potential related/unrelated
slots 只作为预注册结构可行性，不被本次验收接受为最终 semantic split。任何 reserve 解封仍需后续
明确 Stage Contract 和用户授权。

# 4. Accepted Boundary and Known Limits

```yaml
accepted:
  repeated_failure_family_qualification: true
  first_actionable_surface_for_future_attribution: follow_up_strategy
  stage_1_entry_evidence_available: true
not_accepted_or_not_proven:
  candidate_hypothesis: not_created
  trigger_procedure_stop_rule: not_created
  candidate_effectiveness: unproven
  related_task_generalization: unproven
  unrelated_task_regression: unproven
  negative_transfer: unproven
  progressive_disclosure: not_started
  active_skill_or_policy: none
  V5_A_compound_query_classification: unchanged_unclassified
```

D01 的 Provider-domain failures 不构成本 Failure Family 的支持证据；Stage 0 也没有选择或运行 V5-A
compound-query case。后续不得把 infrastructure/retrieval defect 包装为 Search Policy Improvement。

# 5. Authorization After Acceptance

```yaml
stage_0:
  status: accepted
  execution_closed: true
stage_1:
  contract_preparation_authorized: false
  execution_authorized: false
provider_runs_authorized: false
product_code_modification_authorized: false
candidate_skill_creation_authorized: false
reserve_open_authorized: false
merge_push_tag_authorized: false
```

持续 V5-D Version Session 保留为版本执行主体，但当前应保持停止。下一步只能由用户再次明确授权
Stage 1 后，围绕已接受 Failure Family 准备归因与单一 Candidate Contract；不得自动进入 Stage 1。
