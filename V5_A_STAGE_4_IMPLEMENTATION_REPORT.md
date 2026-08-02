# 拾流 V5-A Stage 4 Implementation Report

```yaml
stage: V5-A Stage 4
title: HITL and Operational Control
report_status: resubmitted_for_main_acceptance
contract: V5_A_STAGE_4_CONTRACT.md
contract_status: accepted_with_bounded_preimplementation_sync
execution_branch: codex/v5-a
implementation_start_baseline: 9b2725f6ebe3db25828c72174f34bd1b91388368
docs_sync_commit: f0c8775
implementation_commit: 8021c15
main_acceptance_round_1: rework_bounded_control_lineage_and_input_lifecycle
rework_round_1_commit: 1259993
source_schema_version: 10
live_schema_observed: 9
live_schema_10_migration_performed: false
provider_runs_performed: false
credentials_or_keychain_accessed: false
formal_ui_modified: false
prompt_or_tool_contract_modified: false
stage_4_self_accepted: false
```

## 1. 结论

Stage 4 最小纵向切片已实现并自测完成：研究 Task 现在具有独立于 worker lease
的 durable control fence、typed HITL、safe interrupt/resume、cancel-pending、
append-only SideEffect resolution，以及 source/sibling-isolated branch/replay。
所有权限由服务端 principal registry 派生；payload 自报 actor/role/capability
不能授予权限。

本报告只提交 V5 主 Session 验收，不自我接受 Stage 4，也不开始 Stage 5。

主 Session Round 1 已确认整体模型、schema 10、authority、cancel-pending、
resolution、derivation 与 API，不重开这些范围。提交 `1259993` 仅关闭当前 pause
lineage 与 InputRequest lifecycle 两项 bounded 缺口。

## 2. 实现范围

主要新增：

- `control_generation` CAS fence；control admission 原子清空 lease、递增 owner
  epoch，并拒绝旧 worker mutation。
- immutable `ControlRequest` / append-only `ControlDisposition`。
- immutable `InputRequest`、`HumanDecision` 与 human constraint observation；
  clarification 原子终结旧 Attempt 并创建 Goal revision + child Attempt。
- cancel 对 reserved effect 阻止执行；in-flight 转 unknown 并进入 cancel-pending；
  解析完成后唯一终结。
- immutable `SideEffectResolution`；confirmed success 强制 receipt/result refs，
  不自动重放 unknown external action。
- immutable `TaskDerivation`；branch/replay 创建隔离 child Task/Goal/Attempt/
  Checkpoint/Trace/Receipt，source 与 sibling 不变，EvidenceUse 不跨 Task 共享。
- `/api/research/tasks/{task_id}` 下 control/status、input/decision、resolution、
  derivation 最小 JSON API。
- additive schema 10 源码及 schema 9→10 临时数据库 migration tests。

未修改 Prompt、model choice、Tool Contract、正式 UI 或 Program 权威文件。

## 3. Contract 满足矩阵

| Contract 项 | 状态 | 实现与证据 |
| --- | --- | --- |
| Server-derived authority | pass | `ControlAuthorizationPolicy` 注册 principal/capability；API principal 来自 server app state；extra actor/role 422，restricted principal 即使伪造审计 metadata 仍 403、无状态漂移 |
| Independent control fence | pass | `control_generation` 与 `owner_epoch` 分离；BEGIN IMMEDIATE + state/generation CAS；旧 owner checkpoint/receipt 被拒绝 |
| Immutable request / append-only disposition | pass | schema trigger 禁止 update/delete；所有 applied control/input 具 Event + CommandReceipt |
| Safe interrupt/resume | pass_after_rework | resume 只消费绑定当前 active Attempt/latest checkpoint/current generation 的未消费 interrupt、resolved input 或 interrupt→unknown→resolution lineage；消费后追加 superseded disposition；历史 pause 不可复用 |
| Durable cancel | pass | no-effect/partial/reserved/unknown 路径；partial answer 保留；cancel/result race 仅一个 terminal winner |
| Unknown SideEffect resolution | pass | immutable human resolution、owner/control fence、success receipt guard；resolution/cancel terminal 衔接；无 external replay |
| Typed HITL | pass_after_rework | waiting-user open request exact-once；expired 经 response/status/replacement 入口持久 superseded，cancel 原子关闭 open request；两个 Input kind 使用 server canonical typed schema，schema/decision mismatch fail closed |
| Human Evidence Authority | pass | 任意 factual constraint 不能创建 authorized choice；只有 server-registry exact `human_decidable` options 可写 human observation；不写 transcript EvidenceIdentity |
| Retry | pass | 继承并回归 Stage 1 same-Task terminal Attempt retry 与 terminal Task child lineage；公共 command/API 不变 |
| Branch/replay isolation | pass | immutable source manifest/hash；deterministic child identity/receipt；source/sibling 不变；child EvidenceUse/SideEffect 为空；无 tool/Provider replay |
| Bounds/fail closed | pass | reason 1000、prompt 2000、response 4000、choices 32、manifest 8000、lineage 256；oversize/stale checkpoint 在持久 mutation 前拒绝 |
| Atomicity/fault safety | pass | control fence、HumanDecision、resolution、derivation fault points 均由 guarded transaction 全量回滚 |
| Minimal API/status | pass_after_rework | strict Pydantic `extra=forbid`；status 投影给出 current/open input，并仅在真实 current pause lineage 可执行且无 unresolved effect 时声明 resume |
| Temporary migration only | pass | schema 9→10 backup/idempotence/integrity/FK 测试只用 pytest temp DB；live 保持 schema 9 |
| No Provider/UI/Prompt | pass | Provider logical/transport calls 0；未访问凭据/Keychain；未改正式 UI、Prompt 或 Tool Contract |

## 4. Race、fault 与进程边界证据

- 实际 `multiprocessing spawn` 两进程以同 state/generation 竞争 interrupt：一个
  applied，一个 stale-state error；只产生一个 ControlRequest，generation=1。
- interrupt 后旧 owner 的 checkpoint mutation 被 `stale owner fence` 拒绝；
  新 service 实例从 DB 恢复并以同 Attempt resume。
- cancel 与 success Result 线程竞争只有一个 Task-terminal Result。
- 两个 SideEffect resolution 线程竞争只提交一个 immutable resolution。
- fault 注入 `after_control_fence`、`after_side_effect_resolution_apply`、
  `after_task_derivation_apply` 后，fence、状态、request/resolution/child/receipt
  全量回滚。
- replay 返回原 Receipt；同 command 不同 payload 记录 rejection Event 并 fail
  closed，不重复执行 mutation。

## 5. 测试与机械核验

```yaml
stage_4_targeted:
  result: 27_passed
  file: tests/test_v5_a_stage4_operational_control.py
stage_1_to_4_joint:
  result: 137_passed
default_no_provider_regression:
  result: 1635_passed_4_deselected
  deselected: external_artifact_or_live_provider
warnings:
  count: 7
  detail:
    - existing_Starlette_httpx_TestClient_deprecation
    - six_multiprocessing_fork_deprecations_in_existing_provider_single_flight_tests
compileall: pass
diff_check: pass
temporary_schema_10_integrity: ok
temporary_schema_10_foreign_key_violations: 0
```

完整回归中的 provider single-flight tests 使用机械 fake，不是 live Provider；
真实 Provider、付费服务、凭据和 Keychain 均未调用。

## 6. Live DB 稳定性

主 Session 给出的 implementation-start live baseline 是 schema 9、SHA-256
`2ff0eb91569a81b8a0e244db1238faffd6311236339707b2a9c7273cd317068f`、
mtime `2026-08-03T00:58:14+0800`。在本次全回归前只读复核时，外部 scheduled
sync run 351 已于 `02:04:10–02:05:13+0800` 完成，并把指纹更新为：

```yaml
stable_regression_window:
  schema: 9
  sha256: 4f1a27ce8d4a0a62884ac197d0ef035b89fdf723ba51483dd13ba6dd49c4f735
  size: 94588928
  mtime: 2026-08-03T02:05:13+0800
  videos: 157
  completed: 140
  foreign_key_violations: 0
  integrity: ok
  before_full_regression_equals_after: true
  migrated_or_written_by_v5_a: false
```

V5-A 未启动、终止或干预该 scheduled sync。测试和 compile 均未实例化 live
schema 10；live migration 明确为 `not_performed`。

## 6.1 Main Acceptance Round 1 bounded rework

修复后实际证明：

- old interrupt → resume → later unrelated waiting_user 时，新 resume 无 current
  authority，fail closed 且 state/checkpoint/receipt 不漂移；
- current interrupt resume exact-once，source disposition 从 applied 追加
  superseded；current resolved input 严格绑定 Attempt/checkpoint/generation；
- interrupt 导致 unknown 后，在全部绑定 SideEffectResolution 持久完成且无更新的
  control/human decision 时，仍可沿同一当前 lineage resume；
- `allowed_operations` 与同一 admission helper 共用判定，不再由 blocked/
  waiting_user 状态猜测；
- expired InputRequest 形成 `superseded(reason=expired)`，随后可创建 replacement；
  durable cancel 形成 `cancelled`，terminal status 的 open projection 为空；
- caller schema 只可为空或精确匹配 server canonical schema；decision kind、required
  field、extra field 均在 fence/mutation 前验证。

本轮未修改 schema、长期路线、Provider、UI、Prompt 或 Tool Contract。完整回归
稳定窗口前后 live 指纹继续为 `4f1a27c...`，schema 9 未迁移。

## 7. 未证明与限制

- live schema 10 migration、rollback 与生产 backup 恢复未执行。
- 真实 Provider/network call 的 cooperative cancellation、SIGKILL 中断和
  SideEffect reconciliation 未证明。
- 多主机长期 lease/control-generation soak、正式认证/RBAC、跨设备协作与审计
  retention 未证明；当前 authority 是 trusted local server principal boundary。
- 人工决定的事实正确性不由系统保证；只证明 authority、identity 与审计边界。
- branch/replay 的真实研究质量、跨版本长期 replay 和大规模 lineage 性能未证明。
- 正式 HITL UI、Stage 5 trace/product reliability eval 未实施。

## 8. 请求与停止点

请求 V5 主 Session 对 Stage 4 作一次有限阶段验收：
`accept / partial_accept / rework / pause / reject`。

```yaml
stage_4_status: resubmitted_for_main_acceptance
stage_4_self_accepted: false
stage_5_started: false
provider_runs_performed: false
live_database_migration_performed: false
next_action: V5_main_session_stage_4_rework_round_1_review
```
