# 拾流 V5-A Stage 2 Implementation Report

```yaml
stage: V5-A Stage 2
title: Evidence-backed Inner Research Loop
report_status: submitted_for_main_acceptance
acceptance_authority: V5 main session
baseline_branch: codex/v5-a
accepted_contract_commit: 2037f39a9ec610d84ad4306a4f6c5fb693fdc3e7
implementation_commit: 022c0813f63bf5cad6419c81c817d9f9b85a72bf
stage_2_self_accepted: false
provider_runs_authorized: false
provider_runs_performed: false
credential_or_keychain_accessed: false
stage_2_live_database_migration_performed: false
outer_goal_audit_implemented: false
next_action: V5_main_session_stage_2_acceptance
```

## 1. 提交结论

Stage 2 最小纵向切片已完成并提交主 Session 验收：

```text
Durable Task / Goal / Attempt
→ one-action continue
→ local navigation candidate
→ authoritative transcript search/window
→ immutable global EvidenceIdentity
→ Attempt-scoped EvidenceUse + append-only provenance/currentness
→ bounded citation-valid provisional artifact
→ checkpoint + Event + CommandReceipt
```

实现保持 Task 与 Attempt 非终态，不执行 Outer Goal Audit，不把 provisional
synthesis 当作 Goal 已完成。真实 Provider、credential/Keychain 和 Stage 2
live migration 均未运行。

## 2. Diff 与产品范围

实现提交 `022c081`：

- 14 files changed，3443 insertions，7 deletions。
- 新增：
  - `src/shiliu/research/inner_contracts.py`
  - `src/shiliu/research/inner_evidence.py`
  - `src/shiliu/research/inner_service.py`
  - `src/shiliu/research/inner_tools.py`
  - `tests/test_v5_a_stage2_inner_loop.py`
- 修改：
  - schema version 7 → 8 与 additive research tables/triggers；
  - Stage 1 get/response 对 Stage 2 records 的只读聚合；
  - `Application` 的 lazy、无 Provider inner service wiring；
  - `/research` continue/status/revalidate JSON API；
  - 只受 schema version 影响的既有测试断言。

未修改 V4 Prompt、model choice、Tool Contract、正式 UI、Program Current
State、Program Decision Ledger、Registry、Research Log 或长期路线；未加入新依赖。

## 3. 持久模型与不变量

| 合同对象 | 实现证据 | 状态 |
| --- | --- | --- |
| InnerResearchState | versioned checkpoint payload 保存 phase、ID refs、budget、semantic progress、evidence fingerprint 与正交结果维度 | pass |
| InnerActionRecord | Attempt-scoped canonical action key、request hash、owner epoch、retrieval refs、bounded observation/error | pass |
| EvidenceIdentity | 全局 immutable content identity；citation/source/version/timeline/ordered segments/quote hash；trigger 禁止 update/delete | pass |
| EvidenceUse | `(task_id, attempt_id, evidence_id)` 唯一；绑定 Goal/Attempt/action/checkpoint/owner epoch | pass |
| Provenance | 每次发现 append-only；`(use, provenance_hash)` 去重；不覆盖旧 query/rank/trace | pass |
| ValidationObservation | current/stale/missing/invalid/error append-only；绑定 Task/Goal/Attempt/checkpoint/owner epoch | pass |
| ProvisionalArtifact | immutable；绑定 Task/Goal/Attempt/checkpoint/use/evidence/validation IDs 和 policy versions | pass |
| Atomic publication | action、use/provenance/observation、artifact、budget、checkpoint、Event、receipt 同事务 | pass |
| Owner/checkpoint fence | commit 前后二次校验 current owner/epoch/lease/state version/parent checkpoint/Attempt lineage | pass |
| SideEffect guard | `in_flight`/`unknown` 阻止 checkpoint/artifact；复用已接受 Stage 1 SideEffect protocol | pass |

EvidenceIdentity 不含 Task、Goal、Attempt、query、rank、validation time 或
current/stale。当前性只能由 scoped append-only observation 或明确的只读
derived view 表达。artifact 后 source drift 必须通过显式 revalidation command
追加新 observation；历史 identity、use、provenance、observation 和 artifact
均不改写。

## 4. Contract 满足矩阵

| Contract 要求 | 实现/测试证据 | 结论 |
| --- | --- | --- |
| Durable one-action continuation | 每次 `continue_run` 只产生一个 action 和一个完整 checkpoint；restart 从 checkpoint codec 恢复 | pass |
| Evidence authority | 复用 V4 exact materialization；提交前从 raw source/version/timeline/ordered segments 重建，不信任 preview/navigation | pass |
| 跨 Task/Attempt identity 与隔离 | global identity 收敛；每个 Attempt 独立 use/provenance/validation/allowlist/budget | pass |
| Provisional grounding | bounded context + citation allowlist + shared grounded-answer validator；无证据时 `valid_insufficient` | pass |
| 正交结果维度 | checkpoint 保存 `answer_status`、`termination_reason`、`failure_class`；insufficient/budget/implementation failure 不丢信息 | pass |
| Budget/progress/stop | 服务端 action/round/window/evidence/context/time limits；content identity 而非 segment-only 判 progress；stop 持久化 | pass |
| Idempotency/crash/race | command payload hash、action key、unique constraints、fault rollback、same-command race 与 cross-Task identity race | pass |
| Ownership/lease | takeover/stale owner/late tool response 均在 commit 前被 fence；无 mutation/receipt 漂移 | pass |
| Product API | `POST inner/continue`、`GET inner`、`POST inner/revalidate`；provider mode 未授权时 fail closed | pass |
| Stage 1/V4 regression | 131 项联合定向与 1560 项默认无 Provider回归通过 | pass |
| Provider | real mode 禁用；logical calls/transport attempts 0；Stage 1 deterministic SideEffect tests 继续通过 | not_exercised |
| Live schema 8 migration | 只在临时 SQLite 执行；live DB 保持 schema 7 | not_exercised |
| Outer audit/recursive continuation | 未实现 | correctly_out_of_scope |

## 5. 定向机械测试证据

Stage 2 suite：`21 passed`。

关键测试：

- `test_schema_8_adds_stage2_tables_only_in_temporary_database`
- `test_durable_inner_loop_runs_one_action_per_checkpoint_and_stays_nonterminal`
- `test_inner_command_replay_is_idempotent_and_payload_mismatch_fails_closed`
- `test_conflicting_global_evidence_identity_payload_fails_closed_via_service`
- `test_global_identity_dedupes_but_task_attempt_use_and_provenance_are_isolated`
- `test_stale_source_appends_observation_without_rewriting_identity_or_artifact`
- `test_post_commit_source_drift_keeps_artifact_immutable_and_view_not_current`
- `test_evidence_identity_use_provenance_validation_and_artifact_are_immutable`
- `test_inner_fault_rolls_back_action_identity_use_checkpoint_event_and_receipt`
- `test_artifact_fault_rolls_back_action_checkpoint_observations_and_artifact`
- `test_takeover_fences_old_inner_worker_before_tool_or_mutation`
- `test_late_tool_response_is_rejected_when_takeover_happens_during_action`
- `test_unresolved_side_effect_blocks_inner_checkpoint_without_state_drift`
- `test_budget_stop_is_persisted_and_survives_restart`
- `test_local_action_failure_persists_orthogonal_failure_dimensions`
- `test_same_task_retry_attempt_gets_new_use_without_rewriting_identity`
- `test_api_exposes_durable_inner_continue_and_rejects_provider_mode`
- `test_terminal_task_cannot_start_inner_run_and_has_no_state_drift`
- `test_concurrent_cross_task_materialization_converges_on_one_identity`
- `test_concurrent_same_command_commits_one_action_checkpoint_and_receipt`
- `test_live_db_sentinel_is_not_touched_by_stage2_temp_migration`

联合定向 suite：`131 passed`，包括：

| 范围 | 数量 |
| --- | ---: |
| Stage 1 kernel | 37 |
| Stage 1 API | 4 |
| Stage 2 inner loop | 21 |
| Evidence contracts | 10 |
| V3.5 evidence mechanics | 10 |
| V4 context/citations | 4 |
| V4 Deep | 17 |
| V4 Fast API | 14 |
| retrieval | 14 |

fault injection 覆盖 evidence use 前后、provenance、validation、checkpoint、
artifact 和 receipt publication；异常后 action/evidence/checkpoint/Event/receipt
计数与 Task state version 不漂移。Stage 1 已接受 suite 继续覆盖 SideEffect
reserve → in-flight → receipt、reserve/receipt fault、takeover rebind、
unknown recovery、hash mismatch 和 concurrent replay。

## 6. 默认无 Provider 回归

最终稳定运行：

```text
1560 passed, 4 deselected, 7 warnings in 19.57s
```

默认 pytest marker 排除 `external_artifact` 与 `live_provider`。warnings：

- 1 类既有 Starlette/httpx TestClient deprecation；
- 6 条既有 multiprocessing `fork()` deprecation。

`compileall`、`git diff --check` 均通过。没有失败、xfailed 或新增 warning 类。

## 7. Live DB 证据与外部并发事件

目标文件：
`/Users/elliot/Library/Application Support/Shiliu/shiliu.db`

### 7.1 最终稳定测试窗口

| 字段 | 测试前 | 测试后 |
| --- | --- | --- |
| SHA-256 | `248deb86dd9b32b8ff4bac52ebb3b7e00fdde0c311f421c073310418376d9f24` | 相同 |
| size | 94,588,928 | 94,588,928 |
| mtime | `2026-07-31T03:25:48+0800` | 相同 |
| schema | 7 | 7 |
| videos | 157 | 157 |
| integrity | ok | 未发生写入，前置检查为 ok |

Stage 2 schema 8 migration 未对 live DB 执行。

### 7.2 首次测试窗口的材料性环境事件

第一次全量回归前快照为：

```text
SHA-256 0cf51178b2ddd1c80ed8a763b7aef07f7513cf93a2f11c4c732278e3b2874b61
size 94588928
mtime 2026-07-31T02:21:46+0800
```

回归结束时，用户环境中既有的
`/Users/elliot/new-systems/agent-job-prep/Shiliu/.venv/bin/python3.12
-m shiliu sync --scheduled` 独立进程恰于 `03:21` 启动。只读检查确认该外部进程
将 live DB 从 schema 6 升至已接受的 Stage 1 schema 7，并创建
`shiliu.pre-v7.backup.db`；随后继续执行既有同步/索引工作，至约 `03:25:48`
自然结束。

V5-A 没有启动、终止、修改或借用该进程，没有调用 live `Database.initialize()`，
也没有对 live DB 执行 schema 8 migration。因为外部写入确实发生，不能把第一次
窗口声称为 live DB 不变；本报告保留该事实，并以外部进程结束后的第二次完整回归
作为稳定窗口证据。

## 8. Provider、凭据与产品边界

```yaml
stage_2_provider_logical_calls: 0
stage_2_provider_transport_attempts: 0
credential_values_read: false
keychain_accessed: false
paid_services_invoked: false
live_schema_8_migration_performed: false
v4_prompt_modified: false
model_choice_modified: false
tool_contract_modified: false
formal_ui_modified: false
outer_goal_audit_implemented: false
stage_3_started: false
new_upstream_dependency_added: false
push_merge_tag_performed: false
```

Provider execution mode 在没有独立授权时 fail closed。Stage 2 复用 Stage 1
SideEffect safety envelope，但本轮没有连接或调用真实 Provider，也不据
deterministic adapter 推导 Provider quality。

## 9. 未证明项与残余风险

- 真实 Provider 的正确性、稳定性、成本、延迟、response schema 与产品质量：
  `not_exercised`。
- live DB schema 8 upgrade/rollback：`not_exercised`；仅临时 DB migration、
  backup、idempotence、integrity 与 foreign-key checks 已验证。
- 真实断电/SIGKILL、多主机长期 lease soak、真实 external reconciliation：
  `unproven`。
- production-scale retention、query diversity、long-running no-progress 与性能：
  `unproven`。
- Outer Goal Audit、recursive continuation、HITL/interrupt、branch/replay
  control plane 和最终 UI/Eval：未实现，属于后续 Stage。
- 第一次回归期间发生的外部 scheduled sync/schema 7 migration 是环境噪声；
  第二次稳定窗口证明本实现/测试未写 live DB，但不能反向声称整个会话期间文件
  从未变化。

## 10. 请求主 Session 决定

请 V5 主 Session 对 Stage 2 作出：

```text
accept / partial_accept / rework / pause / reject
```

V5-A 建议基于 `022c081`、21 项 Stage 2 定向测试、131 项联合定向回归、
1560 项默认无 Provider回归和最终稳定 live DB 窗口进行独立轻量验收。外部
scheduled sync 事件需作为环境事实保留，但不应被表述为 V5-A 执行了 Stage 2
live migration。

```yaml
stage_2_status: submitted_for_main_acceptance
stage_2_self_accepted: false
provider_runs_performed: false
stage_2_live_database_migration_performed: false
external_live_database_change_observed: true
next_action: V5_main_session_stage_2_acceptance
```
