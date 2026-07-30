# 拾流 V5-A Stage 1 Contract（Revised Draft）

```yaml
stage: V5-A Stage 1
title: Durable Task Kernel and Safety Envelope
contract_status: pending_final_main_acceptance
proposal_authority: V5-A execution session
acceptance_authority: V5 main session
created_at: 2026-07-30
revised_at: 2026-07-31
main_review_round_1: completed
product_baseline_commit: 483fd46bca1d7141a696fda4b2d1e093a55f209b
implementation_authorized: false
implementation_started: false
provider_runs_authorized: false
provider_runs_performed: false
live_database_migration_authorized: false
```

> 本文件已根据 V5 主 Session 第一轮独立审查修订，现等待最终验收。它不授权当前 Session 立即实施，也不接受自身结果。

## 1. Stage 使命

建立一个无 Provider、可机械验证的持久研究任务内核和安全边界，使后续 Evidence-backed Inner Loop、Outer Goal Audit、HITL、branch/replay 都能建立在明确的身份、lineage、transaction、mutation guard 和副作用语义上。

Stage 1 不做“聪明的研究”；它先证明系统能正确记住自己是谁、走到哪里、发生过什么，以及何时绝对不能自动重做。

## 2. 最小产品结果

在隔离的测试数据库和经主 Session 明确授权的产品实现中，调用方应能：

1. 创建一个 ResearchTask 和不可变的初始 Goal revision。
2. 启动一个不访问 Provider 的 deterministic Attempt。
3. 查询 Task、Goal、Attempt、Checkpoint、Event、Trace、Result、CommandReceipt 和 SideEffect 状态。
4. 在进程退出后重新打开数据库，从最后一个完整 checkpoint 继续。
5. 重复发送同一 command 时得到同一语义结果，不创建重复 Attempt、Event 或 SideEffect。
6. 对 stale writer、并发 goal edit 和非当前 checkpoint mutation 明确拒绝。
7. 在模拟外部副作用写入 `in_flight` 后崩溃时，将其恢复为需要解析的未知状态；不自动重放。
8. 对 clean retry、goal revision、cancel 和 resume 保留完整 lineage。
9. 通过持久 owner lease/epoch fence 拒绝失去 ownership 的旧 worker。
10. Task 一旦提交不可变 terminal Result，任何 retry 或 goal revision 都创建带 `parent_task_id` 的新 Task，不复活旧 Task。

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
- 最小持久 single-active-owner lease/epoch fence。
- 持久 CommandReceipt/DeduplicationRecord。
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
| `parent_task_id` | 新 Task 从已终态 Task retry/revision 时的 lineage；根 Task 为空 |
| `owner_id` | 当前 active owner；无 owner 时为空 |
| `owner_epoch` | 每次首次 claim 或 takeover 单调递增的 fence token |
| `lease_until` | 当前 owner 的持久租约截止时间 |
| `created_at` / `updated_at` | 数据库持久时间 |
| `terminal_result_id` | 仅 `terminal` 状态可指向不可变 Result |

Task lifecycle 状态集合只表达任务是否仍可变，不编码答案有效性或失败类型：

`ready`、`running`、`blocked`、`waiting_user`、`terminal`

允许边：

- `ready → running | terminal`
- `running → blocked | waiting_user | terminal`
- `blocked | waiting_user → running | terminal`
- `terminal` 无出边

规则：

1. `ready`、`running`、`blocked`、`waiting_user` 是非终态；在 guard、owner fence 和业务前置条件满足时可转换。
2. `terminal` 是唯一 Task 终态；进入时必须在同一事务写入不可变 `terminal_result_id`。
3. Task 一旦 `terminal`，永远不得回到 `ready` / `running`，也不得改写 active Goal、Attempt 或 terminal Result。
4. 同一 Task 内 retry 或 goal revision 只允许在 Task 尚未 `terminal` 且 `terminal_result_id IS NULL` 时发生。
5. 已终态 Task 的后续 retry/revision 必须创建新的 child Task，设置 `parent_task_id`，并以只读 reference 指向原 Task/Result/Checkpoint；父 Task 保持不变。
6. 用户看到的 success/partial/insufficient/failure 是由 terminal Result 的独立维度派生，不塞入 Task lifecycle `status`。

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
| `status` | Attempt lifecycle 状态 |
| `owner_epoch` | 创建/继续该 Attempt 时绑定的 Task owner fence |
| `result_id` | Attempt 终止时可指向不可变 Result；不必成为 Task terminal Result |
| `started_at` / `ended_at` | 生命周期 |

Attempt lifecycle 状态集合：

`pending`、`running`、`blocked`、`waiting_user`、`terminal`

允许边：

- `pending → running | terminal`
- `running → blocked | waiting_user | terminal`
- `blocked | waiting_user → running | terminal`
- `terminal` 无出边

规则：

1. `resume` 可以继续同一安全、非终态 Attempt；`retry` 必须创建新的 Attempt。实现不能把二者都折叠成“重新 invoke”。
2. Attempt `terminal` 只说明这次尝试不再可变，不自动使 Task 终态。
3. recoverable Attempt 可提交自身不可变 Result 后，让 Task 保持 `blocked` 或回到 `ready`；随后在同一非终态 Task 中创建 retry Attempt。
4. 只有显式的 Task terminal commit 才把某个 Result 写入 `Task.terminal_result_id` 并将 Task 变为 `terminal`。
5. Attempt 的所有写入必须携带并校验当前 Task `owner_epoch`；旧 epoch 永远不得提交。

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
| `owner_epoch` | 提交该 checkpoint 的 owner fence |
| `created_at` | 持久时间 |

只有满足以下条件的 checkpoint 才能作为 continuation/resume receipt：

- `is_complete=true`；
- 没有 unresolved `in_flight` / `unknown` SideEffect；
- parent lineage 可完整解析且无 cycle；
- checkpoint 属于当前 Task/Attempt/Goal；
- 写入时 expected task version、expected parent checkpoint 与当前 owner fence 均匹配。

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
- `owner_epoch`
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
- `answer_status`
- `termination_reason`
- `failure_class`
- `reason_detail`
- `is_task_terminal`
- 可空 `checkpoint_id`
- `created_at`

三个正交维度不得折叠成单个 `classification`：

1. `answer_status`：`valid_success`、`valid_partial`、`valid_insufficient`、`not_produced`。
2. `termination_reason`：至少包括 `answer_ready`、`budget_exhausted`、`no_new_evidence`、`repeated_action`、`evidence_unavailable`、`needs_user_input`、`cancelled`、`goal_revised`、`external_side_effect_unknown`、`provider_error`、`implementation_error`。
3. `failure_class`：`none`、`implementation_failure`、`provider_failure`、`product_quality_failure`、`infrastructure_failure`、`evaluation_invalid`。

Program taxonomy 必须可无损派生。例如：

- `valid_partial + provider_error + provider_failure` 表示已有有效部分答案，但本轮因 Provider 失败停止；不能丢掉任一事实。
- `not_produced + implementation_error + implementation_failure` 表示没有有效答案且实现失败。
- `valid_insufficient + evidence_unavailable + none` 表示系统正确、诚实地判定证据不足，不是故障。

Result 一经提交不可变。Attempt Result 可终结一个 Attempt 而不终结 Task；只有 `is_task_terminal=true` 且被同一事务写入 `Task.terminal_result_id` 的 Result 才终结 Task。

Stage 1 不调用 Provider，因此 `provider_failure` 只验证 schema 可表达与派生规则；真实 Provider 行为仍为 `not_exercised`，不能用 fake adapter 冒充。

### 4.8 CommandReceipt / DeduplicationRecord

每个可变 command 必须有最小持久 receipt：

| 字段 | 要求 |
| --- | --- |
| `task_id` / `command_id` | 共同形成 Task 内唯一 command identity |
| `command_type` | 稳定操作类型 |
| `payload_hash` | 对规范化输入的稳定 hash |
| `status` | `accepted`、`committed` 或 `rejected` |
| `outcome_reference` | 指向产生的 Task/Goal/Attempt/Checkpoint/Result/Event |
| `response_reference` | 可重建响应的稳定引用或受治理的小型响应 |
| `owner_epoch` | 执行该 command 的 owner fence |
| `created_at` / `completed_at` | 持久时间 |

规则：

1. `(task_id, command_id)` 唯一；同一 Task 中相同 command 只能有一个 canonical receipt。
2. 首次 command 的 receipt 与其状态变更、Event 在同一事务提交。
3. 相同 command、相同 payload hash 重放时返回已存 receipt/response reference，不重复产生语义对象。
4. 相同 command、不同 payload hash 必须 fail closed，不能覆盖旧 receipt；冲突另记 append-only Event。
5. `committed` receipt 不可回退。若 command 跨 external boundary，只能以 receipt 引用已持久 SideEffectRecord，不能把未确认 Provider response 填成 committed outcome。

### 4.9 SideEffectRecord

任何可能离开当前数据库事务的操作都必须先有独立 SideEffectRecord，即使 Stage 1 只使用 deterministic fake adapter。

最小字段：

- `side_effect_id`
- `task_id` / `attempt_id`
- `command_id`
- `idempotency_key`
- `effect_kind`
- `request_hash`
- `status`
- `owner_epoch`
- 可空 `provider_operation_id` / `receipt_hash`
- 可空 `result_reference`
- `created_at` / `updated_at`

状态：

`reserved → in_flight → succeeded | failed | unknown`

规则：

1. 唯一键固定为 `(task_id, effect_kind, idempotency_key)`；不同 Task 合法复用同一业务 key 不冲突。
2. reservation 必须在外部调用前提交，并绑定当时的 current `owner_epoch`。
3. reserve、转 `in_flight`、成功/失败 receipt 提交都必须验证当前 owner、未过期 lease 与相同 epoch。
4. 进程在 `in_flight` 后、receipt 前退出时，不允许任何 worker直接把它恢复为 `reserved` 或重放。
5. 只有旧 lease 已过期/释放、新 owner 通过 CAS takeover 并递增 `owner_epoch`、从而 fence 旧 owner 后，新 owner 才能在同一受保护事务把遗留 `in_flight` 转成 `unknown`，同时让 Task `blocked` 并追加 Event。
6. `unknown` 不得自动变为 `reserved`，也不得自动重放。
7. 人工/外部解析必须追加 Event，保留原未知记录；Stage 1 只需实现 fail-closed 和 deterministic 测试解析接口，完整 HITL 属于 Stage 4。

## 5. Ownership、Command 与 Mutation Guard

### 5.1 最小持久 Ownership Fence

Stage 1 必须实现 single-active-owner lease/epoch，不再是可选项：

1. claim/takeover 使用 Task `state_version` 与观察到的 `owner_epoch` 做 CAS。
2. 首次 claim 和每次合法 takeover 都递增 `owner_epoch`；epoch 永不复用或回退。
3. takeover 只允许在无 owner、明确释放或 lease 已过期时发生。
4. lease renewal 必须由当前 `owner_id + owner_epoch` CAS 完成。
5. 所有可变 command、Event 状态提交、Checkpoint/Result commit、SideEffect reserve/in-flight/receipt 都校验当前 `owner_id`、未过期 `lease_until` 与 `owner_epoch`。
6. 失去 lease 或 epoch 已落后的 worker 即使仍在运行，也不得提交任何 mutation；拒绝必须返回稳定 conflict。若需要持久拒绝 Event，只能由 current owner/control transaction 写入，不能让 stale worker 借记录错误绕过 fence。
7. Stage 1 只实现安全 ownership/fencing，不实现完整调度、队列、人工接管 UI 或跨节点运营控制；这些仍属于 Stage 4。

### 5.2 Command 与 Mutation Guard

每个可变请求必须携带：

- 稳定 `command_id`
- `task_id`
- `expected_state_version`
- 需要时携带 `expected_checkpoint_id`
- `owner_id` 与 `owner_epoch`
- 调用语义的幂等 key

服务必须：

1. 首次命令在同一事务写入 CommandReceipt、Event 和状态变更。
2. 相同 command 重放返回既有 receipt，不重复产生语义对象。
3. 相同 command ID 但 payload hash 不同必须拒绝。
4. expected version/checkpoint 不匹配必须返回明确 conflict，不能 last-write-wins。
5. owner/lease/epoch 不匹配必须拒绝，不能以 command dedupe 绕过 fence。
6. goal edit、cancel、resume、retry、Task terminal commit 与 child Task create 使用同一 guard 原则。
7. 在写 checkpoint/result 前重新读取当前 Task/Goal/Attempt/ownership，防止评价或慢任务覆盖新用户输入或 takeover。

## 6. 事务和崩溃边界

### 数据库内部事务

以下组合必须原子：

- Task create + initial Goal + creation Event。
- ownership claim/takeover + owner epoch increment + Task version + Event。
- Attempt create/start + Task status/version + CommandReceipt + Event。
- checkpoint payload + parent link + state hash + owner epoch + CommandReceipt + Event + Task version。
- Attempt Result + Attempt terminal status + CommandReceipt + Event。
- Task terminal Result + `terminal_result_id` + Task terminal status + CommandReceipt + Event。
- terminal parent Task 后的 child Task + `parent_task_id` + initial Goal + CommandReceipt + Event。
- goal revision + active goal switch + Event。
- CommandReceipt + 对应状态变更。

### 外部边界

数据库事务不得跨真实 Provider/网络调用保持打开。流程必须是：

1. transaction A：校验 Task/command/owner guard，创建/读取幂等 SideEffectRecord，绑定 owner epoch 并提交 `reserved`。
2. transaction B：再次校验 owner fence，标记 `in_flight` 并提交。
3. transaction 外：执行外部调用。
4. transaction C：再次校验相同 current owner fence，依据稳定 receipt 提交 `succeeded` 或 `failed`。
5. 崩溃恢复：先由合法 takeover 递增 fence；新 owner 才可把旧 epoch 的遗留 `in_flight` 原子转为 `unknown` + Task `blocked`；不自动调用。

Stage 1 用 deterministic fake external adapter 和可控 crash point 证明该协议，不调用 Provider。

## 7. Resume、Retry、Goal Revision、Cancel、Branch/Replay

### Resume

- 仅从完整、可寻址、无未知副作用的当前 checkpoint 继续。
- 只允许非终态 Task；保持同一 Task、Goal 与非终态 Attempt identity。
- 新 checkpoint 必须以该 checkpoint 为 parent。
- 必须持有 current owner lease/epoch。
- 无安全 receipt 时拒绝并阻塞。

### Retry

- 同一 Task 内 retry 只对已终态 Attempt 生效，并且 Task 必须仍非终态、`terminal_result_id IS NULL`。
- 创建新 Attempt，记录 `parent_attempt_id` 和 `cause=retry`。
- 可引用旧 checkpoint 作为只读 seed，但不得把新写入挂入旧 Attempt。
- 未知 side effect 未解析时禁止 retry。
- 若父 Task 已 `terminal`，retry 必须创建带 `parent_task_id` 的新 child Task；不得在父 Task 中创建 Attempt 或改写 Result。

### Goal Revision

- Task 非终态时：创建新的不可变 Goal revision，并创建新 Attempt 绑定新 Goal。
- Task 已终态时：创建新的 child Task 和其初始 Goal，以 `parent_task_id` 保留来源；不得修改父 Task active Goal。
- 旧 Task、Goal、Attempt、Checkpoint、Result 保持可查询。
- 慢任务在 revision 或 child Task 创建后尝试提交旧 goal/owner epoch 结果，必须被 expected-version/owner-fence guard 拒绝。

### Cancel

- cancel request 是持久 Event/状态，不只依赖进程信号。
- 重复 cancel 幂等。
- cancel 与 Task terminal result 竞争时由 state version、owner fence 与 transaction 决定唯一合法提交。
- cancel 如终结 Task，必须提交不可变 terminal Result，使用独立 answer/termination/failure 三维信息。
- Stage 1 可在 safe checkpoint 应用 cancel；跨进程主动中断属于 Stage 4。

### Branch / Replay

Stage 1 只建立身份和 lineage contract，不要求完整产品能力：

- branch 必须创建新 Attempt 并记录 source checkpoint。
- replay 必须创建新 Attempt，记录 replay source 和输入版本。
- 若 source Task 已 terminal，branch/replay 必须落入带 `parent_task_id` 的新 Task。
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
- single-active-owner lease/epoch fence 与 takeover tests。
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
- 完整调度、正式 branch/replay 控制面或 ownership/HITL UI。

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
2. Task/Goal/Attempt/Checkpoint/Event/Trace/Result/CommandReceipt/SideEffect ID 不可互换。
3. schema upgrade 在临时 DB 上可重复启动；第二次不重复迁移。
4. live DB 文件在测试前后 hash/mtime 不受影响。
5. terminal Task 无任何合法转换可回到 `ready` / `running`。
6. terminal Task 上的 retry/revision 创建新 child Task，`parent_task_id` 正确，父 Task/Result bit-for-bit 不变。

### B. Command idempotency

1. 同一 create/start/resume/retry/cancel command 重放只产生一次语义变更。
2. 相同 `(task_id, command_id)` + 相同 payload 返回相同 receipt/response reference。
3. 相同 `(task_id, command_id)` + 不同 payload hash fail closed，既有 receipt 不变。
4. receipt、状态变更与 Event 在 crash/race 下仍是同一事务事实。

### C. Ownership / mutation guard

1. stale `expected_state_version` 被拒绝。
2. stale `expected_checkpoint_id` 不能提交 checkpoint/result。
3. 首次 claim 与 takeover 都递增 owner epoch；非过期 lease 不能被夺取。
4. takeover 后旧 owner 无法提交 Event mutation、checkpoint、Attempt/Task Result 或 SideEffect reserve/receipt。
5. lease renewal 必须由 current owner/epoch CAS；stale renewal 被拒绝。
6. goal revision 后旧 worker 不能写终态。
7. cancel 与 Task terminal result race 只能有一个有效终态。

### D. Crash / restart

分别在以下边界强制退出并重新启动：

1. command receipt 前。
2. Task 状态与 Event 原子事务中。
3. checkpoint payload 写入前/后。
4. SideEffect `reserved` 后。
5. `in_flight` 后、fake call 前。
6. fake call 返回后、receipt 提交前。
7. terminal Result transaction 前/后。
8. owner lease 过期、takeover CAS 前/后。

验证：

- 无半条 checkpoint/event/result。
- 已提交命令可去重。
- `in_flight` 在旧 owner 被 fence 前保持原状；takeover 后只转 `unknown`/blocked，不自动重放。
- 恢复结果与数据库事实一致。

### E. Lineage

1. clean resume 生成正确 child checkpoint。
2. retry 生成新 Attempt 并指向 parent Attempt。
3. goal revision 绑定新 Goal，旧历史不变。
4. missing parent、cycle、wrong-task parent、wrong-attempt write 全部 fail closed。
5. branch/replay seed 只读，不向祖先写入。
6. terminal Task 后 retry/revision 的 child Task lineage 可完整遍历且不改写父历史。

### F. Result taxonomy

1. deterministic success 记录 `answer_status=valid_success`、明确 termination reason、`failure_class=none`。
2. 无可执行工作记录 `answer_status=valid_insufficient` 与 evidence-related termination reason，不记 success/failure。
3. 内核异常记录 `failure_class=implementation_failure`，同时保留 `answer_status` 是否已有有效部分答案。
4. `valid_partial + provider_error + provider_failure` 等组合能序列化、查询并无损派生 Program taxonomy。
5. Attempt Result 与 Task terminal Result 的 commit 语义可区分。
6. Provider 相关行为标记 `not_exercised`，不得用 fake 结果冒充真实 Provider 验证。

### G. SideEffect idempotency / fence

1. 同一 Task 内并发相同 `(effect_kind, idempotency_key)` 只能有一个 SideEffectRecord。
2. 不同 Task 可合法复用同一 `effect_kind + idempotency_key`，互不冲突。
3. reserve、in-flight、receipt 均拒绝 stale owner epoch。
4. 遗留 in-flight 只有在旧 owner 已被 takeover fence 后才可转 unknown/blocked。
5. unknown SideEffect 不自动重放。

### H. Regression

- 现有 `/search` 与 `/ask` Fast/Deep 无 Provider 机械测试通过。
- Evidence/Citation reconstruction/revalidation 测试通过。
- 未修改既有产品语义时，不得更新 goldens 来掩盖回归。

## 12. Stage 1 成功标准

主 Session 只能在收到实现、测试和证据后验收；本 Contract 草案本身不满足这些标准。

1. 所有最小语义实体具有独立持久身份和约束。
2. Task、Attempt、Result 状态机分离；terminal Task 不可复活，后续操作产生 child Task lineage。
3. answer status、termination reason、failure class 正交持久且可无损派生 Program taxonomy。
4. retry/resume/goal revision/cancel 语义有机械测试。
5. single-active-owner lease/epoch 必须实现，takeover 后 stale owner 的所有写入被拒绝。
6. CommandReceipt 的 payload mismatch、事务一致性和 dedupe 有机械测试。
7. expected version/checkpoint guard 能稳定拒绝 stale mutation。
8. SideEffect 的 Task-scoped 唯一键、owner fence、reservation、in-flight、receipt、unknown 恢复有 crash tests。
9. 重启后能从完整 checkpoint 恢复，无进程内事实依赖。
10. branch/replay lineage 的非法 parent 情况 fail closed。
11. 没有 Provider 运行、live DB migration 或凭据访问。
12. 现有 Fast/Deep、Evidence/Citation 定向回归通过。
13. 实现报告明确三维 Result、Program 派生分类、`not_exercised` 和 `unproven`。
14. V5 主 Session 正式接受；V5-A 不自我验收。

## 13. 本 Stage 结果分类模板

```yaml
mechanical_contract_tests: unproven_until_implemented
restart_recovery: unproven_until_implemented
ownership_fence: unproven_until_implemented
command_receipt_deduplication: unproven_until_implemented
unknown_in_flight_fail_closed: unproven_until_implemented
provider_behavior: not_exercised
product_quality: not_exercised
live_migration: not_exercised
stage_result: revised_contract_pending_final_main_acceptance
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

1. 是否最终接受修订后的 Task/Attempt/Result 终态模型与 child Task lineage。
2. 是否最终接受 answer status、termination reason、failure class 三维 Result contract。
3. 是否最终接受 Stage 1 强制 single-active-owner lease/epoch fence。
4. 是否最终接受 CommandReceipt 与 Task-scoped SideEffect idempotency contract。
5. 是否接受“Stage 1 提供最小 API、最终 UI 延后”的产品切片。
6. 是否接受 branch/replay 在 Stage 1 仅完成 lineage contract 与失败测试、完整控制面延后到 Stage 4。
7. 是否授权 schema/migration 源码与临时 DB 测试；live DB migration 继续禁止。
8. 是否授权 V5-A 在最终接受后开始产品实现。

```yaml
charter_status: pending_final_main_acceptance
stage_1_contract_status: pending_final_main_acceptance
product_implementation_started: false
provider_runs_performed: false
next_action: main_session_final_document_review
```
