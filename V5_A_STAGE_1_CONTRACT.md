# 拾流 V5-A Stage 1 Contract（Draft）

```yaml
stage: V5-A Stage 1
title: Durable Task Kernel and Safety Envelope
contract_status: draft_pending_main_review
proposal_authority: V5-A execution session
acceptance_authority: V5 main session
created_at: 2026-07-30
product_baseline_commit: 483fd46bca1d7141a696fda4b2d1e093a55f209b
implementation_authorized: false
implementation_started: false
provider_runs_authorized: false
provider_runs_performed: false
live_database_migration_authorized: false
```

> 本文件定义“若经 V5 主 Session 接受后，Stage 1 可以实施什么、必须证明什么”。它不授权当前 Session 立即实施，也不接受自身结果。

## 1. Stage 使命

建立一个无 Provider、可机械验证的持久研究任务内核和安全边界，使后续 Evidence-backed Inner Loop、Outer Goal Audit、HITL、branch/replay 都能建立在明确的身份、lineage、transaction、mutation guard 和副作用语义上。

Stage 1 不做“聪明的研究”；它先证明系统能正确记住自己是谁、走到哪里、发生过什么，以及何时绝对不能自动重做。

## 2. 最小产品结果

在隔离的测试数据库和经主 Session 明确授权的产品实现中，调用方应能：

1. 创建一个 ResearchTask 和不可变的初始 Goal revision。
2. 启动一个不访问 Provider 的 deterministic Attempt。
3. 查询 Task、Goal、Attempt、Checkpoint、Event、Trace、Result 和 SideEffect 状态。
4. 在进程退出后重新打开数据库，从最后一个完整 checkpoint 继续。
5. 重复发送同一 command 时得到同一语义结果，不创建重复 Attempt、Event 或 SideEffect。
6. 对 stale writer、并发 goal edit 和非当前 checkpoint mutation 明确拒绝。
7. 在模拟外部副作用写入 `in_flight` 后崩溃时，将其恢复为需要解析的未知状态；不自动重放。
8. 对 clean retry、goal revision、cancel 和 resume 保留完整 lineage。

Stage 1 的产品可见性可以首先是受控 API 和持久 trace 查询；不要求本 Stage 完成最终研究 UI。若主 Session 要求同时提供 UI，必须先修订本 Contract。

## 3. 起始 Baseline

### 已有

- SQLite schema version 6 与 migration 基础设施。
- V4 Evidence/Citation contract、Fast/Deep finalizer 和显式 answer status。
- V4 Deep typed state、纯 reducer、DecisionView、预算与 termination reason。
- V4.1 Harness 的原子 checkpoint、WAL-before-provider、completed dedupe、未知 in-flight fail closed 和故障注入案例。

### 缺失

- 产品 ResearchTask/Goal/Attempt/Checkpoint/Event/Trace/Result/SideEffectRecord schema。
- 产品 durable command、resume、retry、cancel、goal revision、branch/replay 语义。
- 产品 checkpointer 和持久 trace。
- general external side-effect reservation/receipt。
- 跨进程 owner/lease 或明确的单 owner fence。
- `/research` 产品入口。

### 不能冒充 Baseline 的资产

- 进程内 AskService trace。
- 未配置 checkpointer 的 Deep graph。
- V4.1 Harness JSON checkpoint。
- 浏览器 AbortController。
- DeerFlow 或 AREX 的已下载/已阅读材料。

## 4. Stage 1 最小语义模型

下列字段名是 Contract 级要求；实现可在主 Session 审阅后调整命名，但不得合并其语义身份。

### 4.1 ResearchTask

| 字段 | 要求 |
| --- | --- |
| `task_id` | 稳定、全局唯一、不可复用 |
| `status` | 任务级状态 |
| `active_goal_id` | 指向当前 Goal revision，不覆盖旧 Goal |
| `state_version` | 每次可变状态提交单调增加，用于 CAS |
| `created_at` / `updated_at` | 数据库持久时间 |
| `terminal_result_id` | 仅终态可指向 Result |

拟议状态：

`ready → running → blocked | waiting_user | succeeded | partial | insufficient | failed | cancelled`

允许从 `blocked` 或 `waiting_user` 在显式命令和 guard 通过后回到 `running`。终态不得被原地改回 running；retry 必须创建新 Attempt，goal change 必须创建新 Goal revision。

### 4.2 ResearchGoal

| 字段 | 要求 |
| --- | --- |
| `goal_id` | 稳定 Goal revision ID |
| `task_id` | 所属 Task |
| `revision` | 同一 Task 内单调增加 |
| `parent_goal_id` | 修订 lineage |
| `objective` | 用户目标 |
| `success_constraints` | 显式、可审计的完成约束 |
| `evidence_policy` | 固定引用/证据不变量引用 |
| `created_by_event_id` | 由哪个命令/事件产生 |

Goal revision 不得原地重写。修改目标必须先提交新 Goal，再切换 `active_goal_id`，两者处于同一事务。

### 4.3 ResearchAttempt

| 字段 | 要求 |
| --- | --- |
| `attempt_id` | 稳定 Attempt ID |
| `task_id` / `goal_id` | 绑定 Task 与具体 Goal revision |
| `ordinal` | 同一 Task 内单调序号 |
| `cause` | `initial`、`resume`、`retry`、`goal_revision`、`branch`、`replay` |
| `parent_attempt_id` | retry/branch/replay lineage |
| `status` | Attempt 状态 |
| `owner_token` / `lease_until` | 若实现跨进程 owner，则必须持久化并受 fence 保护 |
| `started_at` / `ended_at` | 生命周期 |

`resume` 可以继续同一安全 Attempt；`retry` 必须创建新的 Attempt。实现不能把二者都折叠成“重新 invoke”。

### 4.4 ResearchCheckpoint

| 字段 | 要求 |
| --- | --- |
| `checkpoint_id` | 不可变 ID |
| `task_id` / `attempt_id` | 所属身份 |
| `parent_checkpoint_id` | 直接 parent |
| `sequence` | Attempt 内单调序号 |
| `state_schema_version` | 状态 schema 版本 |
| `state_hash` | materialized state 的稳定 hash |
| `state_payload` | 经治理允许的持久状态，不含 secret |
| `is_complete` | 仅完整提交后可作为 resume receipt |
| `created_at` | 持久时间 |

只有满足以下条件的 checkpoint 才能作为 continuation/resume receipt：

- `is_complete=true`；
- 没有 unresolved `in_flight` / `unknown` SideEffect；
- parent lineage 可完整解析且无 cycle；
- checkpoint 属于当前 Task/Attempt/Goal；
- 写入时 expected task version 和 expected parent checkpoint 均匹配。

### 4.5 ResearchEvent

Event 是 append-only 审计事实，不是可变状态快照。

最小字段：

- `event_id`
- `task_id`
- 可空 `goal_id`、`attempt_id`、`checkpoint_id`
- Task 内单调 `sequence`
- `event_type`
- schema-versioned、隐私过滤后的 `payload`
- `command_id`
- `created_at`

最小事件类型应覆盖：

- task/goal/attempt created
- attempt started/resumed/retried/terminated
- checkpoint committed
- command deduplicated/rejected
- stale mutation rejected
- side effect reserved/started/succeeded/failed/marked_unknown/resolved
- cancel requested/applied
- blocked/waiting/terminal result committed

### 4.6 ResearchTrace

Trace 与 Event 分离：

- Event 是持久控制事实。
- Trace 是可诊断执行观察，可按隐私和容量策略截断。
- Trace 丢失不能改变 Task 真值。

最小字段：

- `trace_id`
- `task_id` / `attempt_id`
- `trace_schema_version`
- `started_at` / `ended_at`
- `termination_reason`
- `retention_class`

Stage 1 可只记录 deterministic kernel trace；不得把 V4 进程内 trace 直接宣称为 durable。

### 4.7 ResearchResult

最小字段：

- `result_id`
- `task_id` / `goal_id` / `attempt_id`
- `classification`
- `reason`
- 可空 `checkpoint_id`
- `created_at`

Stage 1 支持的分类至少包括：

- `valid_success`
- `partial`
- `insufficient`
- `implementation_failure`
- `provider_failure`
- `cancelled`

Stage 1 不调用 Provider，因此 `provider_failure` 只能在 schema/状态机中存在，实际测试结果应标记 `not_exercised`，不能模拟后宣称 Provider 已验证。

### 4.8 SideEffectRecord

任何可能离开当前数据库事务的操作都必须先有独立 SideEffectRecord，即使 Stage 1 只使用 deterministic fake adapter。

最小字段：

- `side_effect_id`
- `task_id` / `attempt_id`
- `command_id`
- `idempotency_key`
- `effect_kind`
- `request_hash`
- `status`
- 可空 `provider_operation_id` / `receipt_hash`
- 可空 `result_reference`
- `created_at` / `updated_at`

状态：

`reserved → in_flight → succeeded | failed | unknown`

规则：

1. `(effect_kind, idempotency_key)` 唯一。
2. reservation 必须在外部调用前提交。
3. 成功/失败收据必须单独持久化。
4. 进程在 `in_flight` 后、收据前退出，恢复时状态必须是 `unknown` 或等价显式阻塞。
5. `unknown` 不得自动变为 `reserved`，也不得自动重放。
6. 人工/外部解析必须追加 Event，保留原未知记录；Stage 1 只需实现 fail-closed 和测试解析接口，完整 HITL 属于 Stage 4。

## 5. Command 与 Mutation Guard

每个可变请求必须携带：

- 稳定 `command_id`
- `task_id`
- `expected_state_version`
- 需要时携带 `expected_checkpoint_id`
- 调用语义的幂等 key

服务必须：

1. 首次命令在同一事务写入 dedupe receipt、Event 和状态变更。
2. 相同 command 重放返回既有 receipt，不重复产生语义对象。
3. 相同 command ID 但 payload hash 不同必须拒绝。
4. expected version/checkpoint 不匹配必须返回明确 conflict，不能 last-write-wins。
5. goal edit、cancel、resume、retry 与 result commit 使用同一 guard 原则。
6. 在写 checkpoint/result 前重新读取当前 Task/Goal/Attempt，防止评价或慢任务覆盖新用户输入。

## 6. 事务和崩溃边界

### 数据库内部事务

以下组合必须原子：

- Task create + initial Goal + creation Event。
- Attempt create/start + Task status/version + Event。
- checkpoint payload + parent link + state hash + Event + Task version。
- terminal Result + Attempt/Task terminal status + Event。
- goal revision + active goal switch + Event。
- command dedupe receipt + 对应状态变更。

### 外部边界

数据库事务不得跨真实 Provider/网络调用保持打开。流程必须是：

1. transaction A：校验 guard，创建/读取幂等 SideEffectRecord，提交 `reserved`。
2. transaction B：标记 `in_flight` 并提交。
3. transaction 外：执行外部调用。
4. transaction C：依据稳定 receipt 提交 `succeeded` 或 `failed`。
5. 崩溃恢复：任何遗留 `in_flight` 进入 `unknown`/blocked；不自动调用。

Stage 1 用 deterministic fake external adapter 和可控 crash point 证明该协议，不调用 Provider。

## 7. Resume、Retry、Goal Revision、Cancel、Branch/Replay

### Resume

- 仅从完整、可寻址、无未知副作用的当前 checkpoint 继续。
- 保持同一 Task、Goal 与 Attempt identity。
- 新 checkpoint 必须以该 checkpoint 为 parent。
- 无安全 receipt 时拒绝并阻塞。

### Retry

- 只对明确终止/失败的 Attempt 生效。
- 创建新 Attempt，记录 `parent_attempt_id` 和 `cause=retry`。
- 可引用旧 checkpoint 作为只读 seed，但不得把新写入挂入旧 Attempt。
- 未知 side effect 未解析时禁止 retry。

### Goal Revision

- 创建新的不可变 Goal revision。
- 创建新 Attempt，绑定新 Goal。
- 旧 Goal、Attempt、Checkpoint、Result 保持可查询。
- 慢任务在 revision 后尝试提交旧 goal 结果必须被 expected-version guard 拒绝。

### Cancel

- cancel request 是持久 Event/状态，不只依赖进程信号。
- 重复 cancel 幂等。
- cancel 与 terminal result 竞争时由 version/transaction 决定唯一合法提交。
- Stage 1 可在 safe checkpoint 应用 cancel；跨进程主动中断属于 Stage 4。

### Branch / Replay

Stage 1 只建立身份和 lineage contract，不要求完整产品能力：

- branch 必须创建新 Attempt 并记录 source checkpoint。
- replay 必须创建新 Attempt，记录 replay source 和输入版本。
- 分支不可向祖先 Attempt 写入。
- lineage traversal 必须检测 cycle、missing parent、wrong task/attempt。
- 老格式无 parent 的 checkpoint 不得凭时间顺序猜测为安全祖先。

## 8. Allowed Implementation Scope（仅在主 Session 接受后）

主 Session 可选择授权以下 Stage 1 工作：

- 产品 Research Task kernel 的新模块。
- SQLite schema/migration 源码及只针对临时数据库的 migration tests。
- 无 Provider 的 deterministic adapter。
- 最小 task create/get/command/status/trace API。
- 状态机、repository、transaction、idempotency、mutation guard 与 lineage tests。
- 现有 `/search`、`/ask` 的机械回归测试。
- 必要的内部类型和错误码。

即使本 Contract 被接受，执行 live DB migration 仍需单独明确授权。

## 9. Disallowed in Stage 1

- Provider、付费服务、凭据或真实外部研究调用。
- 新研究 Prompt、model choice、Tool Contract。
- Evidence-backed research loop、outer model audit 或 recursive provider continuation。
- 正式 HITL UI、完整 branch/replay UI。
- 复制 DeerFlow/AREX 代码，新增其正式依赖或模型权重。
- 修改 V5-B/C/D 路线。
- 把 V4.1 Harness 文件格式直接设为产品 schema。
- 把 candidate、critic、自报 confidence 设为 verifier。
- 对 live DB 执行 migration。
- opportunistic rerun。

## 10. 必须继承与必须隔离

### 必须继承

- SQLite migration 的 forward-only discipline 与临时 DB 测试。
- V4 稳定 evidence/citation identity 作为后续 checkpoint 中证据引用的契约。
- 显式 status/termination reason 和 Fast/Deep 兼容性。
- V4.1 的 reserve-before-provider、completed dedupe、unknown-in-flight fail closed 原则。

### 必须隔离

- V4 AskService 进程内 trace 与新 durable trace。
- V4 Deep State/DecisionView 与完整 ResearchTask runtime state。
- Harness checkpoint 与产品 Checkpoint。
- Provider response 与 verified Result。
- Event audit 与可裁剪 Trace。
- clean resume 与 retry/new Attempt。

## 11. 定向失败案例与机械测试

所有 Stage 1 测试必须无 Provider，使用临时目录/临时 SQLite。

### A. Identity / schema

1. 新建 Task 同时产生唯一 Goal revision 和 creation Event。
2. Task/Goal/Attempt/Checkpoint/Event/Trace/Result/SideEffect ID 不可互换。
3. schema upgrade 在临时 DB 上可重复启动；第二次不重复迁移。
4. live DB 文件在测试前后 hash/mtime 不受影响。

### B. Command idempotency

1. 同一 create/start/resume/retry/cancel command 重放只产生一次语义变更。
2. 相同 command ID + 不同 payload 被拒绝。
3. 并发相同幂等 key 只能有一个 SideEffectRecord。

### C. Mutation guard

1. stale `expected_state_version` 被拒绝。
2. stale `expected_checkpoint_id` 不能提交 checkpoint/result。
3. goal revision 后旧 worker 不能写终态。
4. cancel 与 result race 只能有一个有效终态。

### D. Crash / restart

分别在以下边界强制退出并重新启动：

1. command receipt 前。
2. Task 状态与 Event 原子事务中。
3. checkpoint payload 写入前/后。
4. SideEffect `reserved` 后。
5. `in_flight` 后、fake call 前。
6. fake call 返回后、receipt 提交前。
7. terminal Result transaction 前/后。

验证：

- 无半条 checkpoint/event/result。
- 已提交命令可去重。
- `in_flight` 不自动重放。
- 恢复结果与数据库事实一致。

### E. Lineage

1. clean resume 生成正确 child checkpoint。
2. retry 生成新 Attempt 并指向 parent Attempt。
3. goal revision 绑定新 Goal，旧历史不变。
4. missing parent、cycle、wrong-task parent、wrong-attempt write 全部 fail closed。
5. branch/replay seed 只读，不向祖先写入。

### F. Result taxonomy

1. deterministic success 记为 `valid_success`。
2. 无可执行工作记为 `insufficient`，不记 success。
3. 内核异常记为 `implementation_failure`。
4. Provider 相关项标记 `not_exercised`，不得用 fake 结果冒充真实 Provider 验证。

### G. Regression

- 现有 `/search` 与 `/ask` Fast/Deep 无 Provider 机械测试通过。
- Evidence/Citation reconstruction/revalidation 测试通过。
- 未修改既有产品语义时，不得更新 goldens 来掩盖回归。

## 12. Stage 1 成功标准

主 Session 只能在收到实现、测试和证据后验收；本 Contract 草案本身不满足这些标准。

1. 所有最小语义实体具有独立持久身份和约束。
2. 状态转换、retry/resume/goal revision/cancel 语义有机械测试。
3. expected version/checkpoint guard 能稳定拒绝 stale mutation。
4. SideEffect reservation、in-flight、receipt、unknown 恢复有 crash tests。
5. 重启后能从完整 checkpoint 恢复，无进程内事实依赖。
6. branch/replay lineage 的非法 parent 情况 fail closed。
7. 没有 Provider 运行、live DB migration 或凭据访问。
8. 现有 Fast/Deep、Evidence/Citation 定向回归通过。
9. 实现报告明确 `valid_success`、`partial`、`insufficient`、`implementation_failure`、`not_exercised` 和 `unproven`。
10. V5 主 Session 正式接受；V5-A 不自我验收。

## 13. 本 Stage 结果分类模板

```yaml
mechanical_contract_tests: unproven_until_implemented
restart_recovery: unproven_until_implemented
unknown_in_flight_fail_closed: unproven_until_implemented
provider_behavior: not_exercised
product_quality: not_exercised
live_migration: not_exercised
stage_result: draft_contract_only
```

## 14. 暂停条件

实施中出现以下情况必须停止：

- 需要依靠 Provider 才能证明 kernel 语义。
- SQLite 无法在要求的原子边界实现而需要改变产品存储方向。
- 需要合并 Task/Attempt/Checkpoint 身份才能推进。
- external in-flight 无法 fail closed。
- 需要修改 V4 Evidence/Citation 冻结不变量。
- 需要对 live DB 执行 migration。
- baseline 漂移改变成功标准。
- 需要采用上游代码/依赖、修改长期路线或跨版本协调。

## 15. 请求 V5 主 Session 决定

1. 是否接受本 Stage 的最小实体和状态机。
2. 是否接受“Stage 1 提供最小 API、最终 UI 延后”的产品切片。
3. 是否要求 Stage 1 实现 owner lease，或先限制为单 owner + durable fence。
4. 是否接受 branch/replay 在 Stage 1 仅完成 lineage contract 与失败测试、完整控制面延后到 Stage 4。
5. 是否授权 schema/migration 源码与临时 DB 测试；live DB migration 继续禁止。
6. 是否授权 V5-A 在接受后开始产品实现。

```yaml
charter_status: draft_pending_main_review
stage_1_contract_status: draft_pending_main_review
product_implementation_started: false
provider_runs_performed: false
next_action: main_session_charter_and_stage_1_review
```
