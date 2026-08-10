# Shiliu V5-D Stage 2 Main Session Acceptance Decision

> Stage: Stage 2 — Frozen Paired Evaluation
> Decision: accept_exact_rejected_verdict
> Accepted by: Shiliu V5 Main Codex Session
> Accepted at: 2026-08-11T03:25:50+08:00
> Execution branch: `codex/v5-d`
> Accepted execution head: `254d72a03a1251ee0d08cac49d100b91b5de7593`
> Effective experiment freeze: `0c72277e7b30bac68800ef27acc9e8d52222efd6`
> Candidate verdict: `rejected`
> Stage 3 authorized: false

---

# 1. Accepted Result

```yaml
stage_2:
  decision: accept
  exact_candidate_verdict: rejected
  operational_exit: source_gate_failed_on_valid_D02_pair
  execution_closed: true
candidate:
  id: V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001
  version: 1.0.0
  artifact_status: proposed_non_active_unchanged
  evaluation_status: rejected
  active: false
  shadow: false
```

Main 接受 Stage 2 的实验完整性、D02 valid paired result、冻结 evaluator 输出和 `rejected` 精确判定。
这不是执行失败，也不是 Candidate validation：实验成功地证伪了 Candidate v1.0 的完整效果主张。

# 2. Accepted Source-pair Evidence

D02 的 Baseline 与 Treatment 均为有效 arm，未使用 replacement：

| Metric | Baseline | Treatment | Main judgment |
| --- | ---: | ---: | --- |
| Answer status | `valid_insufficient` | `valid_partial` | 局部改善，不单独构成成功 |
| Frozen required aspects | 0 | 0 | 硬门失败 |
| Current grounded citations | 0 | 2 | 改善 |
| Grounded sources | 0 | 1 | 两来源比较要求失败 |
| Material Candidate recovery | 0 | 1 | first action 被改变 |
| Final repeated-search guard | yes | yes | recovery/stop 硬门失败 |
| Stop correctness | fail | fail | 硬门失败 |
| Logical / HTTP calls | 5 / 5 | 7 / 7 | 在预算内 |
| Input / output tokens | 8,892 / 476 | 16,907 / 3,724 | 在预算内 |
| Cost | USD 0.001190044 | USD 0.007502329 | 在预算内 |

Treatment 确实产生一次 materially new recovery，并得到两条 current、lineage-valid Citation；但两条 Citation
只来自一个 source，冻结 required-aspect coverage 仍为 0，且后续仍由 `repeated_search` 结束。冻结 evaluator
因此给出 `pair_pass=false`，没有把更长 answer、更多 search 或更多 block 当作成功代理。

合同要求每个有效 source pair 都通过 grounded improvement 与 recovery/stop gate。D02 已形成决定性的有效
失败，D04 和后续 held-out 无法恢复 Candidate v1.0 的唯一 verdict；及时停止属于正确的预算纪律，不是
opportunity resampling。

# 3. Freeze and Pre-provider Correction

Main 接受 `0c72277` 为唯一有效 Stage 2 freeze。首次 freeze `b384531` 在任何 Provider dispatch、Candidate
执行或 held-out access 前，被 accepted Runtime 的 durable budget membership fail-closed 检查拒绝；其
Provider/tool/token/USD 消耗均为 0，private root 与 invalid evidence 已保留。

修正仅把 source 与未来 held-out 的 Task membership 预注册和 additive phase budget 表达调整为 Runtime
可执行形式。Candidate、Treatment、Baseline、Evaluator、success threshold、Provider configuration 与
assignment rule 未改变。两个 artifact snapshot 各有 1,391 条记录，内容 hash multiset 相同；manifest hash
变化来自隔离 root 路径变化，不是 corpus 内容漂移。

# 4. Independent Limited Verification

Main 独立核验：

- `codex/v5-d` 位于 clean execution head `254d72a`；closeout commit 相对有效 freeze 只修改
  `V5_D_CURRENT_STATE.md`、`V5_D_DECISION_LEDGER.md` 和 Stage 2 report；
- Stage 2 从 entry head 到 closeout 的 `src` tree 未改变，产品 Runtime 不导入或注册 experiment-only
  Treatment；
- Candidate、Treatment、runner、evaluator 和两项 test 的实际 SHA-256 与 freeze receipt 完全一致；
- 复跑 `tests/test_v5_d_stage2_treatment.py` 与 `tests/test_v5_d_stage2_evaluator.py`：`12 passed`；
- isolated schema 为 14，`integrity_check=ok`、FK violations 0；Stage 2 的 12 个 Provider side effects 全部
  `succeeded`，active unknown reservations 为 0；
- 总有效 arm 为 2，12 logical / 12 HTTP calls、25,799 input / 4,200 output tokens、7 tool calls，实际成本
  USD 0.008692373，远低于冻结 hard stop；
- execution branch 未 Push、Merge 或 Tag，live DB 未写入或迁移。

# 5. Reserve and Held-out Integrity

```yaml
reserve:
  ciphertext_sha256: d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c
  key_mode: "000"
  access_log_entries: 4
  post_freeze_access_entries: 0
  reserve_runs: 0
  plaintext_present: false
  split_assigned: false
heldout:
  related_run: false
  unrelated_runs: 0
  generalization_proven: false
  unrelated_regression_proven: false
  negative_transfer_proven: false
```

Source gate 未通过，因此 Custodian 未打开或分配 reserve。四个 reserve tasks 仍保持真正 sealed，可在未来
全新、明确授权且保持污染边界的实验合同中继续使用，但当前不得声称任何 held-out 结果。

# 6. Claim Boundary

本次接受正式证明：

- Stage 0 的真实 Failure Family 和 Stage 1 Attribution 可以驱动一个可执行、可证伪的 bounded Treatment；
- Candidate v1.0 能改变一次 first-actionable follow-up 并带来有限 grounded Evidence 增量；
- Candidate v1.0 不能稳定满足冻结的多来源 Research Outcome 与 recovery/stop correctness，因此被拒绝；
- V5-D 当前尚未达到 Portfolio-ready 的 validated Candidate 闭环，也未达到 Version Complete。

它不证明 Candidate 泛化、无关任务无回归、无负迁移、可 active/shadow 使用或对用户有稳定收益。

# 7. Authorization After Acceptance

```yaml
stage_2:
  status: accepted_rejected
  execution_closed: true
stage_3:
  entry_gate_met: false
  execution_authorized: false
candidate_v1_0:
  evaluation_status: rejected
  active_authorized: false
  shadow_authorized: false
  promotion_authorized: false
provider_runs_authorized: false
reserve_open_authorized: false
live_database_write_or_migration_authorized: false
merge_push_tag_authorized: false
active_formal_stage_after_acceptance: none
```

Stage 3 只能由 validated Candidate 进入，本次不得授权。持续 V5-D Version Session 保留但应停止。

# 8. Recommended Next Decision

Main 建议下一步由用户在以下两条路线中作一次产品/作品集方向决定：

1. 授权同一 V5-D Session 在新的有界合同下，回到 Attribution/Candidate design，形成同一 Failure Family
   的 Candidate v1.1；D02 作为已消费 source evidence，reserve 继续 sealed，之后重新冻结并评测；
2. 以 `closed_candidate_rejected` 诚实关闭当前 V5-D effort，保留完整 falsification evidence，但不宣称
   V5-D Portfolio-ready 或 Version Complete。

当前没有任何后续执行授权；Main 不自行启动 Candidate revision、Stage 3 或版本集成。
