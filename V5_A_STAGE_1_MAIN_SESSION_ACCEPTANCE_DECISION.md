# 拾流 V5-A Stage 1 主 Session 验收决定

```yaml
decision: accept
stage: V5-A Stage 1
stage_name: Durable Task Kernel and Safety Envelope
acceptance_authority: Shiliu V5 Main Codex Session
accepted_at: 2026-07-31T02:21:31+08:00
reviewed_contract: V5_A_STAGE_1_CONTRACT.md
reviewed_report: V5_A_STAGE_1_IMPLEMENTATION_REPORT.md
implementation_commit: c8a3f9f054b6793dade3e353fbf61fd8a583ec06
rework_commit: ecbea72b483487a4a64d46d286719e89d024e22f
final_submission_head: cbfc7d1c571a2e2935df33c07cec94dd5f87ac78
product_implementation_started: true
provider_runs_performed: false
live_database_migration_performed: false
```

## 1. 验收结论

V5-A Stage 1 在一轮有界返工后正式接受。

首轮提交已经实现 Durable Research Task kernel、schema 7 源码、无 Provider
deterministic adapter、最小 JSON API、持久 ownership fence、CommandReceipt、
SideEffect 协议和 lineage。主 Session 的独立对抗检查发现两项阻断问题：

1. 公共 `start_attempt` 可用不合法 cause/lineage 组合绕过专用命令语义。
2. owner takeover 后，旧 epoch 的 `reserved` SideEffect 缺少安全续作路径。

提交 `ecbea72b483487a4a64d46d286719e89d024e22f` 已关闭两项问题；独立复验未发现
新的 Stage 1 阻断项。因此验收决定从 `rework` 更新为 `accept`，无需继续修改
Stage 1。

## 2. 接受的产品结果

- 九类持久实体及独立身份：Task、Goal、Attempt、Checkpoint、Event、Trace、
  Result、CommandReceipt、SideEffectRecord。
- Task、Attempt、Result 的独立状态与不可逆 terminal Task 语义。
- 同 Task resume/retry/goal revision/cancel，以及 terminal 后 child Task lineage。
- Stage 1 范围内的 branch/replay identity 与只读 source lineage。
- `answer_status`、`termination_reason`、`failure_class` 三维 Result。
- SQLite 事务、expected version/checkpoint guard 和 append-only Event。
- single-active-owner lease/epoch fence、takeover CAS 与 stale owner 拒绝。
- command payload hash、transactional receipt、dedupe 与 mismatch fail-closed。
- Task-scoped SideEffect reserve/in-flight/receipt/unknown 协议。
- takeover 时仅对旧 epoch `reserved` record 做原子重绑定；旧 `in_flight` 继续
  fail closed。
- 最小 create/get/command/status/trace JSON API。

## 3. 独立验证证据

主 Session 在最终提交上完成：

```yaml
targeted_stage_1_suite:
  result: 41_passed
default_no_provider_regression:
  result: 1539_passed_4_deselected
  warnings: 7
custom_adversarial_checks:
  illegal_attempt_cause_and_lineage:
    result: fail_closed_without_state_drift
  reserved_side_effect_takeover:
    result: rebound_and_executed_exactly_once
live_database:
  sha256_before_and_after: 7e3de301cf43628cc564d79776fbd73c899d4055e13749e328b35d31c3297fa7
  size_before_and_after: 94588928
  mtime_before_and_after: 2026-07-31T01:16:12+0800
  modified: false
git_diff_check: passed
```

既有 warning 为测试依赖和 multiprocessing 的 deprecation warning，不构成本
Stage 阻断。

## 4. Contract 不变量判定

```yaml
identity_and_lineage: pass
terminal_task_immutability: pass
result_taxonomy: pass
transaction_and_mutation_guard: pass
ownership_fence: pass
command_receipt_deduplication: pass
side_effect_fail_closed: pass
restart_from_complete_checkpoint: pass
minimal_api: pass
existing_product_regression: pass
provider_and_live_database_boundaries: pass
```

## 5. 未纳入本次接受的结论

以下仍是 `not_exercised` 或 `unproven`，本次验收不将其升级为已证明：

- live DB schema 7 migration 与真实 live upgrade。
- 真实 Provider、Provider failure runtime 和产品研究质量。
- 真实断电或逐指令 SIGKILL。
- 长时间、多进程或多主机 lease soak。
- 真实外部 SideEffect reconciliation。
- 生产规模性能与 retention policy。
- Stage 2–5 的 Evidence loop、Outer Audit、HITL、完整 branch/replay 控制面、
  UI 和产品评估。

这些项目不阻断 Stage 1，因为本 Stage 的既定目标是无 Provider、临时数据库上的
机械安全内核；它们必须在后续适用 Contract 中重新取得证据，不能由本决定推导。

## 6. Git 与版本结果

```yaml
accepted_commits:
  implementation: c8a3f9f054b6793dade3e353fbf61fd8a583ec06
  bounded_rework: ecbea72b483487a4a64d46d286719e89d024e22f
reviewed_report_commits:
  initial_submission: 3a881853426d74cb5f22d9fcbdb219fc09c11d0f
  final_submission: cbfc7d1c571a2e2935df33c07cec94dd5f87ac78
integration:
  method: fast_forward_only
  branch: codex/v5-main
push_performed: false
tag_created: false
```

## 7. Session 与下一阶段边界

同一个 V5-A Version Session 继续主导 V5-A，并负责 Stage 2 的具体技术设计、
拆分、实施与自测。主 Session 只在正式阶段边界做必要的目标、证据和版本级验收，
不接管其日常 Stage 实现决策。

当前仅允许 V5-A 准备 Stage 2 Contract 和 Just-in-time 实施计划。Stage 2
产品实施、Provider 运行和 live DB migration 尚未由本决定授权。

## 8. 最终状态

```yaml
stage_1_acceptance:
  status: accepted
  blocking_findings_open: 0
  rework_rounds: 1
  contract_fulfilled: true
  product_implementation_started: true
  provider_runs_performed: false
  live_database_migration_performed: false
V5_A:
  status: active
  current_boundary: Stage_2_contract_preparation
  active_version_session_unchanged: true
next_action: V5_A_session_prepares_Stage_2_contract_for_lightweight_main_boundary_review
```
