# 拾流 V5-A Stage 4 Contract

```yaml
stage: V5-A Stage 4
title: HITL and Operational Control
contract_status: draft_pending_main_review
proposal_authority: V5-A execution session
acceptance_authority: V5 main session
created_at: 2026-07-31
version_charter: V5_A_VERSION_CHARTER.md
execution_branch: codex/v5-a
planning_head: 9b2725f6ebe3db25828c72174f34bd1b91388368
stage_3_acceptance_basis: user_confirmed_complete_pass
stage_3_formal_acceptance_record_present: false
implementation_authorized: false
implementation_started: false
provider_runs_authorized: false
provider_runs_performed: false
live_database_migration_authorized: false
live_database_migration_performed: false
formal_ui_authorized: false
stage_4_self_accepted: false
```

> 本文件只请求 Contract 审阅。实施、Provider、live migration、Prompt、
> Tool Contract 和正式 UI 均未授权。实施前必须补齐 Stage 3 主 Session 接受记录
> 与同步 baseline。

## 1. 使命与最小产品切片

唯一使命：在不改写历史、不绕过 owner fence、不自动重放未知外部动作的前提下，
为 `/research` 增加可跨进程恢复的用户输入与操作控制协议。

```text
running / waiting_user / blocked
  → durable request
  → controller fences stale worker
  → typed decision / resolution
  → resume | retry | cancel | isolated branch/replay
  → checkpoint + Event + CommandReceipt
```

受控 JSON API 至少支持：

1. 查询 control state、open input、unresolved SideEffect 和允许操作。
2. 为 Stage 3 `waiting_user` 创建持久 InputRequest，并以 typed HumanDecision
   exact-once 回答。
3. Goal clarification 原子创建新 Goal revision/Attempt，不原地编辑 Goal。
4. safe-point interrupt 和 same-Attempt resume，不重置 checkpoint lineage/预算。
5. durable cancel；存在不确定外部动作时先进入 cancel-pending，解析后终结。
6. append-only 人工 SideEffect resolution，不自动重放。
7. 显式 retry；terminal Task 的后续工作创建 child Task。
8. branch/replay 从 immutable source checkpoint 创建隔离派生 Task，不修改
   source 或 sibling。

本阶段不交付正式 UI、多用户权限系统或调度平台。

## 2. Starting Baseline 与 JIT 审计

```yaml
baseline:
  risk_level: 2
  branch: codex/v5-a
  planning_commit: 9b2725f6ebe3db25828c72174f34bd1b91388368
  working_tree_clean_at_planning_start: true
  source_schema_version: 9
  live_db_schema_observed: 7
  live_db_sha256: ff8bc543d116e1d354d446686bcc56adaf4513941163ddce2ee645ad4d1c3eaa
  live_db_size: 94588928
  live_db_mtime: 2026-07-31T05:29:51+0800
  videos_completed: 157/140
  evidence_authority_mode: live_current_exact_replay
  provider_status: not_exercised
  planning_mechanical_tests: 77_passed
```

可继承：

- Stage 1 的 Task/Goal/Attempt/Checkpoint/Event/Trace/Result、state version、
  CommandReceipt、owner lease/epoch、SideEffect 和低层 lineage validation。
- Stage 2 的 typed checkpoint、provisional artifact、EvidenceUse/currentness 和
  正交结果分类。
- Stage 3 的 waiting/blocked outer checkpoint、ConstraintSpec、human-authority
  预留边界和 immutable audit/decision lineage。
- DeerFlow 已接受的 pattern/test reference：durable idempotent cancel、
  expected-checkpoint guard、interrupt serialization、stale-owner fence。

必须补齐：

- 当前只有 worker owner，没有独立、受限、可审计的 control actor。
- waiting_user 没有 InputRequest/HumanDecision identity 或 response schema。
- `cancel_task()` 固定 `not_produced`、未自动绑定 latest checkpoint，也没有
  interrupt/cancel-pending。
- unknown SideEffect resolution 没有 immutable human resolution provenance。
- branch/replay 只有低层 Attempt 验证，没有 source/sibling-isolated 派生 Task。
- 通用 resume 不能无类型地重写 Stage 2/3 checkpoint。

不继承：

- browser abort、连接断开、进程信号或内存 flag 等同 durable control；
- caller 自报 actor/role 等同认证；
- approve/edit/reject 等同事实 Evidence；
- checkpoint restore 等同 external SideEffect rollback；
- branch/replay 删除、回滚或改写 source history；
- DeerFlow 依赖、源码、Prompt 或 chat-thread identity。

## 3. 冻结持久模型

表名和模块布局由 V5-A 决定，但身份必须分离：

| 对象 | 不可丢失的语义 |
| --- | --- |
| ControlRequest | immutable request ID/kind/Task/Attempt、bounded payload/hash、actor audit metadata、expected state/checkpoint/control generation、command/time |
| ControlDisposition | append-only `accepted/applied/rejected/superseded`、observed generation/fence、reason 与 resulting references |
| InputRequest | immutable Task/Goal/Attempt/source checkpoint/audit、kind、bounded prompt/choices、response schema、constraint/SideEffect refs、expiry |
| InputDisposition | append-only `open/resolved/cancelled/superseded` 派生状态 |
| HumanDecision | immutable request/actor/typed response/hash、decision kind、applied action、result refs、command/generation/time |
| SideEffectResolution | immutable unknown source、`confirmed_succeeded/confirmed_failed`、reason、receipt/result refs、actor/command/time |
| TaskDerivation | immutable branch/replay source and child lineage、source fingerprints、Goal delta 或 exact replay manifest、policy/time |

冻结规则：

1. Request 内容不可回写；current status 只由 append-only disposition 派生。
2. 一个 InputRequest 最多一个 applied HumanDecision；late/different response
   fail closed。
3. HumanDecision 不是 EvidenceIdentity。只有 server-declared
   `human_decidable` constraint 与精确绑定的允许选项可追加 human observation；
   任意 factual natural-language constraint 继续 unknown。
4. 原 `in_flight → unknown` 事实必须保留。resolution 不改变 request hash、
   不创建第二个 effect、不触发 replay。
5. branch/replay source 可保持 active；用独立 TaskDerivation 表达 read-only
   ancestry，不滥用 terminal-successor `parent_task_id`。

## 4. 状态、Authority 与原子提交

### 4.1 Control fence

- `control_generation`（或等价 CAS token）与 worker `owner_epoch` 分离。
- control admission 检查 expected task/checkpoint/generation，并原子 fence 当前
  worker；旧 epoch 后续 checkpoint/result/receipt 拒绝。
- 同时最多一个 pending control request。cancel 可 supersede 尚未 applied 的
  interrupt/resume；其他冲突 fail closed；terminal Result 永不可逆转。
- controller 不能绕过 evidence、SideEffect 或 terminal gate；worker 不能伪造
  HumanDecision。

### 4.2 Interrupt / resume

```text
running → interrupt_requested → interrupted → resumed
```

- 无 external call in flight 时，control service 从 latest complete checkpoint
  提交 domain-compatible interrupt checkpoint。
- action commit 与 interrupt CAS 只能有一个获胜；late worker response 被 fence。
- 已开始的 external call 先转 unknown/blocked，不能宣称安全暂停。
- resume 只消费 applied interrupt 或 resolved input，保持 Attempt identity，
  checkpoint schema 与已消耗预算。

### 4.3 Cancel / SideEffect resolution

```text
cancel_requested
  ├─ no unresolved effect → terminal cancelled Result
  └─ in_flight/unknown → cancel_pending → human resolution → terminal Result
```

- cancel 持久、幂等、独立于 worker 存活；admission fence 旧 worker。
- reserved 且未开始的 effect 不得执行；in-flight/unknown 在解析前不得终结或重放。
- cancel Result 保留最新已提交的 `valid_partial/valid_insufficient`；无答案才用
  `not_produced`，并记录 `termination_reason=cancelled/failure_class=none`。
- confirmed success 必须有 receipt/result reference；confirmed failure 不触发
  replay。resolution 与恢复/终结同事务或由 guarded next action 唯一衔接。
- cancel 与 success Result race 只有一个 terminal winner。

### 4.4 Input / retry / branch / replay

- clarification 原子提交旧 Attempt Result (`goal_revised`) 和新 Goal/Attempt/
  Trace/checkpoint/Event/receipt。
- “接受部分结果”只产生 partial/insufficient，不能升级 valid_success。
- same-Task retry 要求 terminal parent Attempt；terminal Task retry 创建 child。
- terminal source 的 command/receipt/derivation 落在确定性 child，source aggregate
  不变。
- branch 显式应用 bounded Goal delta并重新校验 current evidence。
- replay 只物化已提交 record/receipt 的 exact input/config/checkpoint manifest；
  不重新执行检索、Provider、付费动作或未知 SideEffect。
- source 不可重建、checkpoint 不完整、lineage cycle/missing parent、版本不匹配
  均 fail closed；child EvidenceUse/currentness 重新建立。

所有 mutation 必须在 guarded transaction 中提交相应 checkpoint、Event、
CommandReceipt、control/input disposition 和 state version；任一 fault 全量回滚。
stale control、invalid input、payload mismatch 和 lineage conflict 是 rejection，
不伪造产品 Result或 implementation failure。

## 5. Bounds、结果分类与停止

```yaml
control_profile: v5-a-stage4-control-v1
max_pending_control_requests_per_task: 1
max_open_input_requests_per_attempt: 1
max_input_prompt_characters: 2000
max_input_response_characters: 4000
max_input_choices: 32
max_control_reason_characters: 1000
max_derivation_manifest_characters: 8000
max_lineage_depth: 256
provider_logical_calls: 0
```

waiting/interrupted 墙钟时间不扣 inner/outer runtime budget；resume、retry、
branch/replay 不得重置适用预算。Stage 4 不授权任意 budget increase。

| 情形 | answer_status | termination_reason | failure_class |
| --- | --- | --- | --- |
| cancel，有部分答案 | `valid_partial/valid_insufficient` | `cancelled` | `none` |
| cancel，无答案 | `not_produced` | `cancelled` | `none` |
| waiting input | 保留现值 | `needs_user_input` | `none` |
| interrupt 可恢复 | 保留现值，不建 terminal Result | control checkpoint | `none` |
| unknown effect | 保留现值 | `external_side_effect_unknown` | `none` |
| control implementation error | 保留现值或 `not_produced` | `implementation_error` | `implementation_failure` |
| Provider | 本阶段不运行 | `provider_error` | `not_exercised` |

## 6. 允许与禁止范围

```yaml
allowed_after_contract_authorization:
  source:
    - src/shiliu/research/**
    - additive Stage-4 integration under src/shiliu/**
    - minimal typed /research control/input/derivation JSON API
  tests:
    - deterministic Stage 4 unit/integration/race/fault tests
    - directly caused Stage 1/2/3 regression fixes
  schema:
    - additive request/disposition/decision/resolution/derivation state
    - necessary status/check changes and versioned migration source
  migration_execution: temporary_databases_only
  no_provider_product_cases: true
  prompts: false
  tool_contract: false
  formal_ui: false
  new_upstream_dependencies: false
```

禁止：

- Contract 接受和明确授权前实施；
- live DB migration，或把 schema 10 source 合入会自动迁移 live DB 的活跃分支；
- Provider、付费服务、凭据/Keychain、held-out；
- V4 Prompt、model choice、Tool Contract、正式 UI；
- 通用调度/队列、多租户 RBAC、跨设备协作或工作流平台；
- human/candidate/confidence 获得 transcript Evidence Authority；
- unknown external action 自动重放；
- Stage 5 trace UI、product-quality eval；
- Program 权威文件、长期路线、Push、Merge、Tag。

数据只允许临时测试 DB/fixture；live DB 仅做 read-only fingerprint，live corpus
不得写入。

## 7. 定向测试与验收证据

必须实际触发：

- Input：waiting-user request、restart/takeover、exact replay、payload/schema/
  task/attempt mismatch、expired/superseded、Goal clarification rollback。
- Human authority：任意 approve/free text 不能满足 factual constraint；合法
  human-decidable choice 可追加明确 human observation。
- Interrupt：before-action、action-commit race、late worker、restart、
  same-Attempt resume、stale owner writes rejected。
- Cancel：无/有 checkpoint、partial artifact、duplicate/mismatch、terminal race、
  reserved not executed、in-flight/unknown cancel-pending。
- Resolution：fenced `in_flight → unknown`、receipt requirement、no replay、
  duplicate/race/takeover 和 fault rollback，原 uncertainty history 可查询。
- Retry/derivation：terminal child、source/sibling isolation、invalid lineage/
  source/version、Goal delta、exact manifest、child EvidenceUse/currentness、
  no Provider/unknown-effect replay。
- API/migration：strict public service/API、stable status ordering、schema 9→10
  temporary backup/idempotence/integrity/FK/fault tests。
- Regression：Stage 1/2/3、Evidence/Citation、`/search`、Fast/Deep `/ask` 和默认
  无 Provider回归；live DB 稳定窗口。

验收包必须证明：

1. 真实进程边界或等价多进程测试中，另一 worker 可观察 durable request，旧
   worker 被 fence，restart 后恢复。
2. 一个 waiting-user case 完整恢复，一个越权 factual approve 被拒绝。
3. cancel race、cancel-pending、unknown resolution 和 branch/replay isolation
   均实际发生。
4. 每项 mutation 有 generation/checkpoint/Event/receipt 与 fault rollback 证据。
5. Provider logical/transport calls 为 0；凭据、live migration、Prompt、
   Tool Contract、正式 UI、Program 文件未触碰。
6. Implementation Report 给出 commits/diff、Contract 矩阵、测试、失败/警告、
   `not_exercised`、`unproven` 和 clean tree。

## 8. 未证明与 Pause Conditions

即使通过，仍不证明：多用户认证/RBAC、跨设备协作、正式 UI、OS 级终止第三方
网络调用、人工 resolution 正确性、Provider interrupt/replay、live schema 10、
生产调度/retention/长期多机 soak，以及 Stage 5 产品质量和 trace 体验。

出现以下任一情况暂停：

- 需要改变 Stage 1–3 已接受 identity/evidence/terminal semantics；
- control admission 无法可靠 fence active worker；
- external in-flight 无法保持 unknown 且不自动重放；
- branch/replay 需要改写 source 或共享 mutable EvidenceUse；
- 需要 Provider、live migration、凭据、正式 UI、Prompt/Tool Contract；
- scope 扩张为平台、Stage 5 或长期路线变化；
- 正式接受 baseline 与真实 Git/schema materially 冲突。

## 9. Just-in-time 实施顺序

仅在本 Contract 获接受和明确授权后执行：

1. 同步 Stage 3 正式接受 baseline，复核 acceptance delta/schema 9/完整回归。
2. 实现 request/disposition/decision/resolution/derivation schema 与 codecs；
   只在临时数据库 migration。
3. 实现 control generation、out-of-band fence、safe-point interrupt/cancel 和
   race/fault tests。
4. 接入 waiting-user typed response、Goal revision 与 human-decidable authority。
5. 接入 append-only unknown resolution 和 cancel-pending，不自动重放。
6. 实现 explicit retry 与 isolated branch/replay child Task。
7. 接入 minimal status/command API，跑联合/完整回归，形成 Implementation Report。

## 10. 当前停止点

```yaml
stage_3_status: accepted_by_user_pending_main_record
stage_4_contract_status: draft_pending_main_review
stage_4_implementation_authorized: false
stage_4_implementation_started: false
provider_runs_performed: false
live_database_migration_performed: false
next_action: V5_main_session_stage_4_contract_review
```
