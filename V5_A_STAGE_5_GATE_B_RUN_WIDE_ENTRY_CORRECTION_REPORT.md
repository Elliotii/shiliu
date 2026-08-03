# 拾流 V5-A Gate B Run-wide Entry Correction Report

```yaml
as_of: 2026-08-03
baseline: d567c5f78a5cff8573219ce727c88cae398f1109
correction_status: implemented_and_mechanically_verified
provider_calls_performed_this_correction: 0
credential_access_performed_this_correction: false
live_database_migration_performed: false
gate_C_started: false
```

## 1. 修正结果

Gate B post-fix 的总预算不再由三个 Task 各自获得一份。`ProviderRunBudgetPolicy` 冻结
run identity、exact Task 集合、开始时间与 logical / HTTP / input / output / wall / cost
总上限；相同 binding 以 revision-1 Goal evidence policy 持久记录。每个 Provider descriptor
同时绑定 run policy hash。

`ProviderRunBudgetSnapshot` 从 exact Task 集合的 durable Provider Action 与 active
SideEffect 无损聚合 committed usage/cost 和 active worst-case reservation。服务重启后从同一
eval DB 与冻结 policy 重建，不读取进程内计数器；terminal command replay 在聚合门之前返回
原 receipt，不增加 logical、transport、token 或 cost。

下一次 SideEffect reserve 的同一 SQLite 写事务同时重验：

- per-case logical、HTTP worst attempts、input/output token reservation 与 deadline；
- run-wide logical 17、HTTP 34、input 140000、output 31984、wall 34 分钟；
- run-wide `reserve_stop_usd=0.40` 与 `absolute_max_cost_usd=0.50`；
- durable run membership/policy hash、Task owner/state/control generation 与既有 SideEffect
  fence。

实际 Provider usage 若超过 pre-call token reservation，不能写完整 success receipt，而是
进入 unknown / unreconciled fail-closed，禁止自动重放。

## 2. 无网络机械证据

```yaml
provider_wiring_and_product_tests: 27_passed
stage_1_to_5_joint_targeted_tests: 173_passed
previous_joint_baseline: 167_passed
new_cross_task_budget_cases: 6
compileall: pass
diff_check: pass
warnings: 1_existing_starlette_httpx_deprecation
network_provider_calls: 0
credential_or_keychain_access: 0
```

对抗覆盖包括：两个/三个 Task 聚合后，即使当前 Task 未达到自身 cap，run-wide logical、
HTTP worst reservation、output token 或 cost 也会在 transport 前拒绝下一调用；wall cap 和
cost ledger 在 restart 后不重置；相同 terminal operation replay 不重复计数；篡改 policy 或
缺失 durable membership fail closed；rejection receipt exact-once。

## 3. 后续 Entry Gate

本报告只关闭付费前机械条件，不接受 Gate B。独立提交后才可建立新的隔离 post-fix root，
重新冻结原 schema-9 snapshot/artifact identity、schema-10 eval copy SHA、五个 blob、官方
price table 与 manifest。Entry Gate 任一失败时保持 credential access 与 Provider call count
为 0；通过后才执行获批的三个 exact case 各一次。原 formal root 保持不可变，Gate C 禁止。
