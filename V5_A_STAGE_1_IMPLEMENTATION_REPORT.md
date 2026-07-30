# 拾流 V5-A Stage 1 Implementation Report

```yaml
report_date: 2026-07-31
version_session: Shiliu V5-A Version Session
branch: codex/v5-a
accepted_base_commit: a8dae62a9796d8d9d70afb883ab5f2c1a707403f
implementation_commit: c8a3f9f054b6793dade3e353fbf61fd8a583ec06
stage: 1
stage_name: Durable Task Kernel and Safety Envelope
stage_1_status: submitted_for_main_acceptance
stage_1_self_accepted: false
provider_runs_performed: false
live_database_migration_performed: false
credentials_accessed: false
next_action: V5_main_session_stage_1_acceptance
```

## 1. Outcome

V5-A 已在 `codex/v5-a` 实施 `V5_A_STAGE_1_CONTRACT.md` 的产品
Research Task kernel、安全围栏、SQLite schema 7、无 Provider deterministic
adapter、最小 JSON API 与机械测试。实现提交基于 V5 主 Session 的正式接受/授权
提交 `a8dae62`，没有 merge commit。

本报告只提交事实与 V5-A 自测结论，不构成 Stage 1 正式接受。请求 V5 主
Session 在独立复核后选择：

```yaml
requested_main_decision:
  - accept
  - partial_accept
  - rework
  - pause
  - reject
```

## 2. Implementation Scope

### 产品代码

- `src/shiliu/research/schema.py`
  - 新增 Task、Goal、Attempt、Checkpoint、Event、Trace、Result、
    CommandReceipt、SideEffectRecord 九类持久实体。
  - SideEffect 唯一键为
    `(task_id, effect_kind, idempotency_key)`。
  - schema、枚举、foreign key、单 active Attempt、顺序与恢复索引均有约束。
- `src/shiliu/research/contracts.py`
  - 独立 Task/Attempt/Result/SideEffect 枚举和严格 API request contracts。
  - Result 保持 `answer_status`、`termination_reason`、`failure_class` 三维正交。
- `src/shiliu/research/service.py`
  - `BEGIN IMMEDIATE` 事务边界、expected-version/checkpoint mutation guard。
  - terminal Task 不可复活；终态后 retry/revision 生成 child Task。
  - clean resume、同 Task retry、Goal revision、cancel、最小 branch/replay lineage。
  - single-active-owner lease/epoch、takeover CAS、stale owner 写拒绝。
  - CommandReceipt payload hash、响应重放、payload mismatch fail-closed 与
    append-only rejection Event。
  - SideEffect reserve → in-flight → succeeded/failed，以及 takeover 后
    unknown/blocked 恢复和显式 deterministic resolution。
- `src/shiliu/research/adapter.py`
  - 纯本地、无网络、无 Provider 的 deterministic effect adapter。
- `src/shiliu/app.py`、`src/shiliu/web.py`
  - 接入 ResearchTaskService。
  - 新增最小 create/get/command/status/trace JSON API；未新增或修改正式 UI。
- `src/shiliu/db.py`
  - 产品 schema version 从 6 前向提升到 7。
  - 复用既有 migration backup discipline，并创建 Research kernel schema。

### 测试代码

- `tests/test_v5_a_stage1_research_kernel.py`
  - 34 项 kernel/schema/migration/crash/race/lineage/idempotency 定向测试。
- `tests/test_v5_a_stage1_research_api.py`
  - 3 项 create/get/command/status/trace API 与 conflict/child Task 测试。
- 既有 schema version assertions 同步到 7；未修改 golden 或放宽既有断言。

## 3. Contract Satisfaction Matrix

| Contract 项 | 实现与证据 | V5-A 状态 |
| --- | --- | --- |
| 九类独立持久身份 | 九表、独立主键、FK/unique/check constraints；全实体 ID 测试 | implemented_mechanically_verified |
| Task/Attempt/Result 分离 | terminal Task 不可复活；Attempt 可独立 terminal；Result 不可变提交 | implemented_mechanically_verified |
| 终态后 child Task | retry/revision API 创建稳定 child，保留 `parent_task_id`，父历史不变 | implemented_mechanically_verified |
| 三维 Result | 三列合法枚举；success/insufficient/implementation/provider 组合可查询 | implemented_mechanically_verified |
| transaction/mutation guard | `BEGIN IMMEDIATE`、state version、latest checkpoint、owner fence | implemented_mechanically_verified |
| durable ownership fence | owner lease + monotonic epoch；claim/takeover/renew；stale 写拒绝 | implemented_mechanically_verified |
| CommandReceipt | Task-scoped command identity、payload hash、status/time/response reference | implemented_mechanically_verified |
| command mismatch | 既有 receipt 不变、fail closed、追加 rejection Event | implemented_mechanically_verified |
| SideEffect 协议 | Task-scoped reserve/in-flight/receipt；事务不跨 adapter call | implemented_mechanically_verified |
| ambiguous in-flight | takeover 前保持；旧 owner 被 fence 后转 unknown + Task blocked；不自动重放 | implemented_mechanically_verified |
| checkpoint/restart | 完整 payload/hash/schema/parent/owner epoch；新 service 实例恢复 | implemented_mechanically_verified |
| retry/resume/revision/cancel | distinct semantics、幂等重放、race winner、历史不可变 | implemented_mechanically_verified |
| branch/replay Stage 1 边界 | 只实现 identity/source lineage；source 仅当前 Task/祖先且已终态 | implemented_mechanically_verified |
| 最小 API | create/get/command/status/trace JSON endpoints | implemented_mechanically_verified |
| 既有产品回归 | 默认无 Provider suite 全过 | mechanically_verified |
| 正式 Stage 接受 | 只由 V5 主 Session 决定 | pending_main_acceptance |

## 4. Test Evidence

### 4.1 Stage 1 targeted suite

```text
PYTHONPATH=src <shared-python> -m pytest -q \
  tests/test_v5_a_stage1_research_kernel.py \
  tests/test_v5_a_stage1_research_api.py

37 passed
```

定向证据包括：

- 临时 schema 6 → 7 migration、pre-v7 backup、重复 initialize、integrity check、
  foreign-key check；
- create/Attempt/checkpoint/Result/owner takeover 的 fault rollback；
- restart 后 checkpoint lineage 与 reserved SideEffect 继续；
- external call 返回后、receipt commit 前 crash 导致持久 `in_flight`；
- takeover 前不转 unknown，takeover 后只转 unknown/blocked，不自动重放；
- 两线程 owner claim、cancel/result、相同 SideEffect key race；
- same command replay、payload mismatch、stale version/checkpoint/owner；
- terminal Task 不可复活、child Task lineage、Goal revision、retry/resume；
- branch/replay 当前或祖先 source checkpoint，以及 unrelated source fail-closed；
- 三维 Result 的 `valid_success`、`valid_insufficient`、
  `valid_partial + provider_error + provider_failure` 和
  `not_produced + implementation_error + implementation_failure` 表达。

### 4.2 Full default no-Provider regression

```text
PYTHONPATH=src <shared-python> -m pytest

1535 passed, 4 deselected, 7 warnings in 31.17s
```

默认 pytest 配置排除 `external_artifact` 和 `live_provider`。该执行覆盖既有
`/search`、`/ask` Fast/Deep、Evidence/Citation reconstruction/revalidation、
数据库、同步和历史机械回归。

### 4.3 Warnings

- 1 条既有 Starlette TestClient/httpx deprecation warning。
- 6 条 multiprocessing `fork()` deprecation warnings，来自既有
  provider single-flight 的本地 fake/mechanical tests。
- 无测试失败；未通过改 golden 或放宽断言消除失败。

## 5. Live DB and Provider Safety Evidence

live DB 在本轮实施前后保持：

```yaml
path: /Users/elliot/Library/Application Support/Shiliu/shiliu.db
sha256_before: 7e3de301cf43628cc564d79776fbd73c899d4055e13749e328b35d31c3297fa7
sha256_after: 7e3de301cf43628cc564d79776fbd73c899d4055e13749e328b35d31c3297fa7
size_before_and_after: 94588928
mtime_before_and_after: 2026-07-31T01:16:12+0800
live_database_migration_performed: false
```

所有 migration tests 使用 pytest 临时目录和临时 SQLite。没有初始化 live DB。

```yaml
provider_runs_performed: false
paid_services_used: false
credentials_accessed: false
keychain_accessed: false
network_required_by_stage_1_tests: false
```

deterministic adapter 只生成本地 hash/receipt，不是 Provider 模拟结论。

## 6. Commits and Diff

```yaml
accepted_base:
  sha: a8dae62a9796d8d9d70afb883ab5f2c1a707403f
  subject: docs(v5-a): accept charter and authorize stage 1
implementation:
  sha: c8a3f9f054b6793dade3e353fbf61fd8a583ec06
  subject: feat(v5-a): implement durable research task kernel
  files_changed: 13
  insertions: 4256
  deletions: 3
```

实现提交只包括：

- `src/shiliu/research/**`
- `src/shiliu/app.py`
- `src/shiliu/db.py`
- `src/shiliu/web.py`
- `tests/test_v5_a_stage1_research_*.py`
- 两个既有 schema version assertion

没有 Prompt、model choice、Tool Contract、UI、正式 migration execution、Program
权威文件或上游依赖变更。

## 7. Not Exercised / Unproven

```yaml
not_exercised:
  - live_database_migration
  - real_provider_behavior
  - provider_failure_runtime_behavior
  - paid_service_or_credentials
  - external_artifact_suite
  - Stage_2_evidence_backed_inner_loop
  - Stage_3_outer_audit_and_recursive_continuation
  - Stage_4_full_HITL_branch_replay_control_plane
  - Stage_5_product_completion_UI_and_eval
unproven:
  - real_power_loss_or_SIGKILL_at_each_transaction_instruction
  - long_duration_multi_process_or_multi_host_lease_soak
  - live_corpus_schema_7_upgrade
  - production_scale_performance_and_retention_policy
  - real_external_side_effect_reconciliation
```

故障注入证明的是 SQLite 事务与 deterministic adapter 边界，不把异常注入等同
真实断电、Provider 或分布式运行证明。

## 8. Submission

```yaml
stage_1_status: submitted_for_main_acceptance
stage_1_self_accepted: false
provider_runs_performed: false
live_database_migration_performed: false
next_action: V5_main_session_stage_1_acceptance
```
