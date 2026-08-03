# 拾流 V5-A Gate B Bounded Rework Round 1 Report

```yaml
stage: V5-A Stage 5
gate: B_real_provider_product_quality_evaluation
rework_round: 1
status: submitted_for_main_review
self_accepted: false
original_formal_run: GB-20260803T081500Z-be96740
original_run_disposition: accepted_immutable_diagnostic_evidence
provider_calls_this_rework: 0
credential_or_keychain_access_this_rework: false
live_database_migration_performed: false
gate_C_started: false
```

## 1. 关闭的缺口

原正式 runner 只把 V4 Deep structured calls 接到 receipt-bound SideEffect，未把输出提交到
长期 Research product lineage。本轮新增独立的、默认禁用的
`ReceiptBoundResearchProductOrchestrator`，执行顺序为：

1. 复用 Gate A `ResearchProductService`，以单步持久 runner 把当前 Attempt 推进到 Stage 2
   `provisional_synthesis` 边界；
2. 由 `ReceiptBoundProviderService` 执行未改动的 `query_analysis`、`agent_action` 与按 Deep
   证据状态实际需要的 `grounded_answer`；
3. 从 typed Citation 对固定 source artifact/segment 做 exact replay 与 currentness 校验；
4. 仅当实际 SideEffect、CommandReceipt、provider/model/endpoint/role/thinking、operation ID、
   request/output hash、Attempt 与 owner epoch 全部匹配时，原子提交 Stage 2 EvidenceUse、
   validation observation、provider-backed provisional artifact、checkpoint、Event 与 receipt；
5. 再复用 Stage 3 deterministic outer audit，形成 terminal Result、honest waiting_user，或
   受现有 budget 限制的 targeted child Attempt；不授予 Provider/candidate evaluator authority；
6. waiting_user 继续使用 Stage 4 current InputRequest → exact-once HumanDecision → goal-revision
   child Attempt。后续 Provider run 使用新的 command lineage，历史 InputRequest 不能复用。

Provider artifact 的 `answer_status` 在 Outer Audit 前最多为 `valid_partial`；只有 Stage 3
server-owned evaluator 全部满足时，terminal Result 才可派生为 `valid_success`。无证据时
Deep 可确定性跳过 grounded generation，此时 `valid_insufficient` artifact 仍必须绑定本轮
已回执的 query/action lineage，不能伪造 grounded receipt。

## 2. 安全与不可变边界

- Provider product orchestration 需要三重显式 authority：receipt dispatch enabled、inner
  Provider ingest enabled、product orchestration enabled；Gate A public API 默认均不获得。
- ingest 前后重验 Task state、active Attempt、checkpoint、owner epoch 与 control generation；
  stale owner/control/checkpoint 不能提交 artifact。
- successful receipt set 必须与同一 operation prefix 的持久 Provider Action 完全相等；已知
  invalid-output/repair 的持久 logical calls 计入 Stage 2 ledger，cross-run receipt 拒绝。
- 非 insufficient artifact 的 draft hash 必须等于 grounded_answer receipt `output_hash`；
  Citation 必须可从当前 artifact/segments 重建并通过既有 grounded validator。
- unresolved `in_flight|unknown` SideEffect 继续阻止 checkpoint；unknown replay 不产生第二次
  transport call。
- 原 formal root、manifest、case outputs 与人工 review 未读写；冻结 Prompt、Tool、Schema、
  model 与 case text 均未修改。

## 3. 无网络测试证据

新增 `tests/test_v5_a_stage5_gate_b_provider_product.py`，全部使用 pytest 临时 SQLite、固定
artifact 与 no-network Provider：

| 路径 | 结果 |
| --- | --- |
| grounded product path | Stage 2 provider artifact + EvidenceUse/currentness，Stage 3 audit 后 terminal `valid_success`，Result/Trace lineage 完整 |
| insufficient product path | Stage 2 `valid_insufficient`，Stage 3 honest `waiting_user`，Task 不遗留 running |
| HITL continuation | current InputRequest → fixed HumanDecision exact-once → goal-revision child Attempt → Provider artifact → terminal；历史 input fail closed |
| unknown dispatch | Task blocked、SideEffect unknown；同 orchestration command 不产生第二次 transport |
| unchanged Deep executor | 真实 V4 Deep service 通过 receipt factory 进入 durable insufficient/waiting boundary；无证据时不伪造 grounded call |
| replay/cost | terminal command replay 返回同一 orchestration receipt，Provider call 与 durable cost snapshot 不增加 |
| ingest fault rollback | artifact 事务中 fault 全回滚；同 command 只重放已持久 Provider receipt，transport/cost 不增加，随后 exact-once artifact/audit |
| call cap | 达到 logical-call cap 后，下一次 structured call 在 transport 前拒绝；重启/重放不增加调用 |

验证结果：

```yaml
new_provider_product_tests: 7_passed
provider_wiring_plus_product_tests: 21_passed
stage_4_gate_A_gate_B_related_tests: 57_passed
stage_1_to_5_joint_targeted_tests: 167_passed
compileall: pass
diff_check: pass
warnings: 1_existing_starlette_httpx_deprecation
network_calls: 0
provider_calls: 0
live_db_schema: 9
live_db_sha256_stable_window: 227b587d105ce0b2b69cc1109cb3bc7d8519031c8bb4f0ea37ddf9bdd21c1e84
live_db_size_bytes: 94588928
live_db_integrity: ok
live_db_foreign_key_violations: 0
live_db_counts: 157_videos / 140_completed
```

## 4. 文件范围

- `src/shiliu/research/provider_product.py`：默认禁用的 receipt-bound durable product
  orchestrator 与 unchanged Deep executor；
- `src/shiliu/research/inner_service.py`：fenced Provider synthesis ingest、receipt/output/evidence
  binding 与 Stage 2 ledger；
- `src/shiliu/research/provider_wiring.py`：同一 factory 成功 receipt 集合；
- `src/shiliu/ask/evidence.py`：typed Citation 的 source-artifact exact replay；
- `src/shiliu/research/product_service.py`：新增 Provider product trace labels；
- `tests/test_v5_a_stage5_gate_b_provider_product.py`：五条无网络产品路径测试。

## 5. 未证明项与停止点

- 修复后的组合路径尚未运行真实 Provider；本轮不构成完整 Gate B 接受证据。
- 真实 Provider 下的 post-fix latency、cost、model output 与 HITL continuation 均为
  `not_exercised`；需另行接受 amendment 并书面授权后才能运行。
- 没有执行 live schema 10 migration、mainline integration、Gate C、真实 crash/SIGKILL 或
  多进程长时 soak。
- 原 run 保持有效诊断证据，但不能被解释为修复后 product orchestration 证据。

```yaml
gate_B_bounded_rework_round_1: submitted_for_main_review
gate_B_self_accepted: false
postfix_provider_run_authorized: false
gate_C_authorized_for_v5_a: false
next_action: V5_main_session_bounded_rework_review
```
