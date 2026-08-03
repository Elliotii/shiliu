# 拾流 V5-A Stage 5 Gate B Mechanical Entry Report

```yaml
stage: V5-A Stage 5
gate: B_real_provider_product_quality_evaluation
scope: minimal_receipt_bound_provider_wiring_and_no_network_mechanics
report_status: submitted_for_main_review
gate_B_self_accepted: false
plan_accepted_head: 3ebec9aa3d9cc10697bd3766841a9a1b94ad8cff
implementation_commit: a25d007
hard_cap_test_commit: 7241c3b
provider_run_authorized: false
provider_calls_performed: 0
credentials_accessed: false
keychain_accessed: false
formal_evaluation_root_created: false
live_database_accessed: false
live_database_migration_performed: false
gate_C_authorized: false
```

## 1. 本轮结果

Gate B 首次付费调用前的最小 receipt-bound wiring 与 no-network 机械部分已实现。新增
`ReceiptBoundProviderService` 提供与既有
`provider_factory(role).generate_structured(...)` 相同的调用形状，因此冻结的
`QueryAnalyzer`、`AgentDecisionService`、`GroundedAnswerService` 无需改写即可通过
durable wrapper 执行。

默认 `provider_dispatch_authorized=False`；未显式授权时在 Provider factory 被访问前即
fail closed，且不产生 SideEffect、Action 或调用。V5-A 本轮只在临时测试数据库中以显式
test authorization 注入纯内存 mock，没有接入 `Application.provider`、`load_api_key()`、
Keychain 或任何网络 client。

## 2. 持久协议

每个 logical structured call 使用确定性的 Task-scoped operation key，并按下列边界执行：

1. 对 provider、model、role、messages、response schema、output cap 和 timeout 做 canonical
   request hash；持久 SideEffect 只保存该 hash、schema hash、价格表与预算，不保存 Prompt
   全文；
2. 在同一事务校验 Task/Attempt、owner lease/epoch、state version、current checkpoint 与
   control generation，计算 committed cost 加所有 active reservation；通过后写
   `reserved`；
3. 再次 fenced transition 到 `in_flight` 后才允许调用注入的 Provider factory；
4. 成功响应在单一事务写 SideEffect receipt、append-only InnerAction usage/cost ledger、
   Task/Attempt-scoped Event/Trace projection、CommandReceipt 和 state version；
5. receipt binding 固定 exact provider/model/role/request hash、schema hash、规范化 usage、
   cost、transport attempts、provider operation ID、output hash 与 result reference；
6. exact command replay 从 CommandReceipt 重建 typed response，不访问 Provider factory；同
   operation 不同 payload fail closed；
7. dispatch exception 或 receipt 不可计价形成 `unknown + blocked`；crash/rollback 后遗留
   `in_flight`，均禁止自动重放。已确认收到内容且 usage 完整的 invalid structured output
   则写 `failed` receipt，并保留既有一次 bounded repair 语义。

Usage/cost ledger 不新增 schema：它由 `research_inner_actions` 中
`v5-a-gate-b-provider-call-v1` append-only observation 派生；`reserved|in_flight|unknown`
SideEffect 的最坏费用保持 active reservation。重启后重新从 SQLite 派生，不依赖进程内
计数器。

## 3. 价格与服务端上限

```yaml
provider: deepseek_openai_compatible
model: deepseek-v4-pro
query_analysis_output_cap: 1200
agent_action_output_cap: 1200
grounded_answer_output_cap: 4096
input_cache_hit_usd_per_1m: 0.003625
input_cache_miss_usd_per_1m: 0.435
output_usd_per_1m: 0.87
reservation_peak_multiplier: 2
reservation_transport_attempts: 2
absolute_max_cost_usd: 0.50
```

Pre-call reservation 由服务端根据 canonical request UTF-8 byte upper bound、固定 role output
cap、2×峰时因子和最多两次 transport attempts 计算，调用方不能直接提交费用值。测试用
默认 US$0.50 配置和 300,000 字符输入稳定证明：预留会在 Provider factory access 前拒绝，
Provider call count、SideEffect 和 Action 都保持 0。

## 4. No-network 定向证据

新增 `tests/test_v5_a_stage5_gate_b_provider_wiring.py`，当前 10 项：

| 不变量 | 机械证据 |
| --- | --- |
| 默认授权边界 | 未启用 dispatch flag 时 factory access=0，DB 无漂移 |
| 三角色接线 | 通过实际 `QueryAnalyzer`、`AgentDecisionService`、`GroundedAnswerService` 各提交一次 mock structured call |
| receipt binding | 三条 SideEffect/Action/Event 均固定 provider/model/role/request hash/usage/cost/result reference/receipt hash |
| restart budget | 新 Service 实例从 SQLite 恢复相同 ledger；费用不重置 |
| exact replay | 重建 wrapper 后相同 operation/payload 返回原 typed result，第二次 transport call=0 |
| payload mismatch | 相同 operation、不同 messages 在 Provider access 前拒绝 |
| unknown fail closed | 模拟 ambiguous dispatch 后持久 `unknown + blocked`；replay 和新 operation 均不调用 Provider |
| crash/rollback | `after_provider_dispatch` 与 `after_provider_receipt` fault 均无半提交 receipt/action，遗留 `in_flight` 禁止重放 |
| owner/state/control fence | public Stage 4 interrupt 在 dispatch/commit race 中递增 generation/epoch、清除 owner 并把 effect 置 unknown；旧 worker commit 被拒绝 |
| bounded repair | content-received 且 usage 完整的 invalid output exact-once 记为 failed，第二个 logical call 才执行既有 repair |
| absolute cost cap | 默认 US$0.50 下超限 reservation durable rejection，factory access=0 |

验证结果：

```yaml
gate_B_provider_wiring_targeted: 10_passed
stage_1_to_5_joint_targeted: 156_passed
warnings:
  - existing Starlette/httpx deprecation warning only
compileall: pass
diff_check: pass
provider_calls_performed: 0
```

Stage 1–5 联合范围为两项 Stage 1、Stage 2、Stage 3、Stage 4、Gate A 与本 Gate B
mechanical test 文件。schema 10 migration/preflight 只由该联合 suite 在 pytest 临时数据库
执行；未读取或迁移 live DB。

## 5. Gate A frozen blob 核验

实现前后 `git hash-object` 均为：

```yaml
query_analysis_py: 2eb00bf0553bf4f173b22101351788c96665b7f5
agent_action_py: b93777b6dde1bf834604fe01a6fa0c2f08c5a240
grounded_answer_py: ee23019f255b8772bff5beaf142ed5c0bad37bd0
inner_tools_py: 396e3433254d08117b763e4b91e8daa56dad5172
ask_contracts_py: 4ed333410287d25094f327f1c13bec098b367b02
```

本轮未修改 Prompt、Tool Contract、response schema、model selection 或 evaluation cases。

## 6. Mechanical Entry Gate 状态

| Entry 项 | 状态 | 边界 |
| --- | --- | --- |
| 独立 receipt-bound wiring commit | pass | `a25d007`；默认 dispatch disabled |
| no-network reserve/in_flight/receipt/fence/cost/restart/unknown/replay tests | pass | 10 项 mock/临时 SQLite |
| Gate A blob freeze | pass | 五个 hash 完全一致 |
| 临时 schema 10 migration/preflight | pass | pytest temp DB only |
| plan price table/caps | pass | 与 accepted plan 一致 |
| formal eval DB copy、材料性 baseline、eval SHA 与 artifact SHA | not_exercised_not_authorized | 没有创建 formal evaluation root |
| runtime manifest 与 exact case/run authorization | not_exercised_not_authorized | Provider run 与 credentials 均未授权 |

因此本轮只关闭机械子门：`mechanical_wiring_ready_for_main_review`。完整首次付费 Entry Gate
仍是 `closed`，必须等待 formal eval root/snapshot、exact run、credential 与 Provider 调用的
后续书面授权；本 Session 不自我接受 Gate B。

## 7. 未证明项与停止点

- 真实 DeepSeek request/response、usage 字段、费用、latency、transport retry 与模型质量均
  为 `not_exercised`；
- formal eval DB copy、eval SHA、artifact copy、run manifest 和人工 rubric 未形成；
- 真实 Provider 下的 grounded/insufficient/HITL cases 未运行；
- live DB 未访问、未迁移，Gate C 未开始；
- 多进程真实网络 dispatch 后的外部 reconciliation 仍未证明。

```yaml
gate_B_plan_status: accepted
gate_B_mechanical_wiring_status: submitted_for_main_review
gate_B_self_accepted: false
provider_run_authorized: false
provider_calls_performed: 0
credentials_accessed: false
formal_evaluation_root_created: false
live_database_migration_performed: false
gate_C_authorized: false
next_action: V5_main_session_gate_B_mechanical_entry_review
```

## 8. Main review bounded rework Round 1

V5 主 Session 对 HEAD `fbfda06` 的有限复核要求补齐 actual Provider identity 与
operation ID binding。本轮只修改 wiring、no-network tests 与这份精简证据：

- descriptor、canonical request hash 与成功/失败 receipt 现在绑定授权 endpoint、实际
  model、role、thinking mode 和 reasoning effort；只有 factory 返回对象的 runtime identity
  与固定策略逐字段、逐类型一致时，才允许调用 `generate_structured()`；
- 错误 model、endpoint 或 role thinking 配置会在 transport call=0 时提交 fenced
  `provider_identity_rejected` Event、rejected Action、failed SideEffect 和 terminal
  CommandReceipt。Exact replay 复用该失败 receipt，不重新访问 transport；
- Provider 返回有效 output/usage 但缺少真实 response/operation ID 时，不再以本地 hash
  伪造 ID，而是提交 `unknown + blocked` 与 terminal unknown receipt；replay 禁止第二次
  transport；
- Gate A 五个冻结 blob 未修改。

```yaml
bounded_rework_round_1_local_status: pass
gate_B_provider_wiring_targeted: 14_passed
stage_1_to_5_joint_targeted: 160_passed
warnings:
  - existing Starlette/httpx deprecation warning only
provider_calls_performed: 0
credentials_accessed: false
live_database_accessed: false
next_action: create_formal_eval_snapshot_and_run_full_entry_gate
```

用户已书面允许在这次返工全部通过后，继续 accepted plan 内的 formal Gate B；该连续授权
不构成 Gate B 结果接受。任何 Entry Gate、snapshot、价格、credential、endpoint/model、
unknown dispatch 或基础设施异常仍要求立即停止。
