# 拾流 V5-A Stage 3 Contract

```yaml
stage: V5-A Stage 3
title: Outer Goal Audit and Recursive Continuation
contract_status: draft_pending_main_review
proposal_authority: V5-A execution session
acceptance_authority: V5 main session
created_at: 2026-07-31
version_charter: V5_A_VERSION_CHARTER.md
execution_branch: codex/v5-a
planning_head: fafcf48cf3c8703e9d665992da96c8b74de20fff
stage_2_submission_head: fafcf48cf3c8703e9d665992da96c8b74de20fff
stage_2_formal_acceptance_record_present: false
implementation_authorized: false
implementation_started: false
provider_wiring_proposed: true
provider_runs_authorized: false
provider_runs_performed: false
live_database_migration_authorized: false
live_database_migration_performed: false
stage_3_self_accepted: false
```

> 本 Contract 是待 V5 主 Session 审阅的实施边界草案，不构成 Stage 2 接受、
> Stage 3 实施授权、真实 Provider 运行授权或 live migration 授权。

## 1. 入口门槛与使命

Stage 3 实施前必须同时满足：

1. V5 主 Session 已正式接受 Stage 2，并给出接受记录和集成 baseline；
2. `codex/v5-a` 已安全同步到该 baseline，工作树干净；
3. Stage 2 schema、artifact、budget 与 evidence authority 的接受语义没有被
   后续主审修改；
4. V5 主 Session 接受本 Contract 并明确授权实施。

当前仓库尚无 Stage 2 正式接受记录，因此本轮只能准备 Contract 与
Just-in-time 计划。

Stage 3 的唯一使命是：对已经 citation-valid、可重新校验的 provisional
artifact 逐项审计当前 Goal objective 和 success constraints；仅在存在具体、
可恢复且有预算的新缺口时创建 targeted continuation；否则以准确分类完成、
停止或阻塞。

```text
Stage 2 provisional artifact
  → source/currentness revalidation
  → constraint-by-constraint outer audit
  → deterministic gate
      ├─ all required constraints satisfied → terminal valid_success
      ├─ recoverable scoped gap → targeted child Attempt
      ├─ honest partial/insufficient stop
      └─ blocked / needs user / failure
```

模型输出、自报 confidence、候选答案、文字变化或“inner run 已完成”均不能直接
通过 Goal gate。

## 2. 最小纵向产品切片

Stage 3 完成后，受控 `/research` 产品入口至少能够：

1. 对 current owner 持有的非终态 Task、active Goal 和 running Attempt，读取
   最新完整 Stage 2 artifact/checkpoint。
2. 冻结该 Goal revision 的 objective、显式 success constraints 和 evidence
   policy 为稳定 ConstraintSpecSnapshot。
3. 在 audit commit 前重新校验 artifact 实际引用的每个 EvidenceUse；stale、
   missing、invalid 或跨 Attempt 引用不能被判 satisfied。
4. 逐约束持久化 typed audit observation，并将“候选审计”与“有权威的最终
   constraint status”分开。
5. 从 audit facts 派生 bounded CompactImprovementState、typed blocker、
   progress fingerprint 和 continuation decision。
6. 所有 required constraints 均由允许的 evaluator 判 satisfied 时，原子提交
   audit、checkpoint、Event、CommandReceipt 和 Task terminal Result。
7. 有具体可恢复缺口时，原子终结父 Attempt、保存非 Task-terminal Result，并
   创建一个带 parent lineage 的 targeted child Attempt；不覆盖父历史。
8. child Attempt 只针对一个 canonical targeted objective 运行 Stage 2 inner
   loop；原 Goal revision 不被暗中改写。
9. 跨 Attempt 保留有效发现时，只携带 immutable evidence identity references；
   child 必须重新建立自己的 EvidenceUse、provenance/currentness，不能借用父
   Attempt 的 use 或 allowlist。
10. outer budget、continuation count、semantic no-progress 与 blocker history
    跨 child Attempts 持久累计；restart、replay 或 takeover 不重置。
11. 暴露最小 audit/advance/status JSON API；不实现正式 UI、完整 HITL 或
    branch/replay 控制面。

## 3. Starting Baseline 与 JIT 审计

```yaml
baseline:
  risk_level: 2
  branch: codex/v5-a
  planning_commit: fafcf48cf3c8703e9d665992da96c8b74de20fff
  working_tree_clean_at_planning_start: true
  stage_1_status: accepted
  stage_2_status: submitted_for_main_acceptance
  stage_2_source_schema_version: 8
  live_db_schema_observed: 7
  live_db_sha256: 248deb86dd9b32b8ff4bac52ebb3b7e00fdde0c311f421c073310418376d9f24
  live_db_size: 94588928
  live_db_mtime: 2026-07-31T03:25:48+0800
  provider_status: not_exercised
  evidence_authority_mode: live_current_exact_replay
```

### 3.1 可直接继承

- Stage 1：Task/Goal/Attempt/Checkpoint/Event/Trace/Result、single-active-owner
  lease/epoch、CAS、CommandReceipt、SideEffect 和 terminal history。
- Stage 2：immutable EvidenceIdentity、Attempt-scoped EvidenceUse、
  append-only provenance/currentness、ProvisionalArtifact、BudgetLedger、
  citation allowlist 和 grounded validation。
- `retry_attempt` 已要求同 Task terminal parent，适合作为 targeted child
  Attempt 的底层 lineage primitive。
- Goal objective、success constraints 和 evidence policy 已按 Goal revision
  不可变保存。
- 已接受 AREX reference boundary 允许独立重实现 Outer Constraint Audit、
  Targeted Follow-up 和 Compact Improvement State；DeerFlow 只提供 typed
  blocker、durable receipt、no-progress 与 mutation-guard 测试参考。

### 3.2 当前必须补齐

- `success_constraints_json` 仍是 opaque strings，没有稳定 constraint identity、
  evaluator policy 或逐项状态。
- ProvisionalArtifact 只证明 inner grounding，不证明 objective/constraints 满足。
- 没有 OuterAudit、ConstraintObservation、CompactImprovementState、
  ContinuationDecision 或 outer aggregate budget。
- `InnerResearchState.phase=complete/stopped` 不可复活；直接重置同一 state 会
  破坏 Stage 2 budget 和 action identity。
- `complete_attempt` 与 `retry_attempt` 是两个 transaction；不能用于需要
  exact-once 的“audit 后终结父 Attempt 并创建 child Attempt”。
- Stage 2 EvidenceUse 以 Attempt 隔离；跨 Attempt 直接借用 use/currentness 会
  违反已接受 Contract。
- 现有 `get_task` 没有 outer audit/continuation 聚合视图。

### 3.3 明确不继承

- 不把模型 audit、critic、confidence 或 provisional answer 当 verifier。
- 不把相同/不同答案文本 hash 当 semantic progress。
- 不把一个新 segment ID、query 或 child Attempt 本身计作进展。
- 不把 AREX 的 restart 实现为删除历史或原地重置。
- 不把 DeerFlow 的 visible-assistant-text fingerprint 作为拾流 no-progress。
- 不把 V4/V4.1 进程内 trace、一次性 graph 或 Harness checkpoint 当产品状态。

本阶段不需要新增上游研究、Clone、依赖或 Adoption Decision。

## 4. 冻结语义模型

具体表名、模块布局和索引由 V5-A 自主决定；以下身份与关系不能合并或丢失。

### 4.1 ConstraintSpecSnapshot

每个 active Goal revision 的 audit constraint set 必须稳定、不可变，至少包含：

- `constraint_id`、schema version、Goal ID/revision、ordinal；
- exact original text、bounded normalized text、canonical payload hash；
- constraint kind：registered deterministic kind 或 `natural_language`;
- required/optional 标志和 evaluator policy/version；
- objective 本身作为 required constraint，不因 success constraints 为空而消失。

`constraint_id` 不含 Attempt、artifact、audit time 或模型输出。相同 Goal
revision 重放必须得到同一 snapshot；Goal revision 产生新的 constraint set。
不得让 provider candidate 改写、删除或降低 required constraint。

### 4.2 AuditCandidate 与 ConstraintAuditObservation

两者必须分离：

- `AuditCandidate` 是 deterministic fake 或未来 Provider 产生的有界建议，可包含
  proposed status、evidence refs、gap 和 targeted objective；它没有 gate 权威。
- `ConstraintAuditObservation` 是 append-only 的最终审计事实，绑定 Task、Goal、
  parent Attempt、source artifact/checkpoint、constraint、evaluator policy、
  currentness observations、evidence refs、owner epoch 和 observed time。

最终 constraint status 固定为：

```text
satisfied | unsatisfied | unknown | invalid
```

recoverability 单独记录：

```text
recoverable | irrecoverable | needs_user | not_applicable
```

只有 registered deterministic evaluator 的成功结果，或未来 Stage 4 明确记录的
human decision，才能产生 `satisfied`。Stage 3 默认产品路径对无法由已注册规则
判断的 natural-language constraint 必须返回 `unknown`；citation presence 只能
证明 grounding，不能自行证明语义蕴含。

### 4.3 OuterAuditRecord

每轮 audit 是 immutable record，至少绑定：

- audit ID/schema/policy version；
- Task/Goal/Attempt、source inner checkpoint 和 ProvisionalArtifact；
- constraint snapshot 与 observation IDs；
- commit-time EvidenceValidationObservation IDs；
- artifact/evidence/progress fingerprints；
- overall outcome、typed blocker 和 reason codes；
- outer BudgetLedger before/after；
- candidate/Provider SideEffect reference（若适用）；
- owner epoch、created time。

旧 audit 不因新证据、source drift 或后续结论而修改；新的事实追加新 audit 或
currentness observation。

### 4.4 CompactImprovementState

CompactImprovementState 是 versioned、bounded、不可变的续作投影，至少保存：

- verified evidence identity refs；
- satisfied、unsatisfied、unknown constraint IDs；
- rejected direction fingerprints 与 typed rejection reasons；
- conflict/currentness flags；
- blocker；
- 单一 targeted objective 与 canonical fingerprint；
- outer aggregate budget/no-progress；
- parent audit/checkpoint/artifact/Attempt 和 proposed child Attempt lineage。

它只保存稳定引用和派生状态，不内嵌 raw transcript、自由文本 memory、credential、
完整 trace 或未收据化响应，也不能成为 Evidence Authority。

### 4.5 ContinuationDecision 与 Attempt lineage

decision 枚举：

```text
accept | targeted_continue | stop_partial | stop_insufficient | blocked
```

`targeted_continue` 必须同时满足：

1. 存在至少一个 required、unsatisfied/unknown 且 `recoverable` 的 constraint；
2. 生成一个非空、bounded、直接指向该 gap 的 canonical targeted objective；
3. target fingerprint 未在相同 progress fingerprint 下执行过；
4. source audit/checkpoint/artifact 可寻址且 current；
5. 没有 unresolved `in_flight/unknown` SideEffect；
6. outer 和 Stage 2 per-Attempt budgets 都允许；
7. current owner/state/checkpoint fence 有效；
8. 未达到 semantic no-progress 阈值。

targeted continuation 是“由 audit 授权的专用 retry”：

- 父 Attempt 必须在同一 transaction 内提交 immutable non-Task-terminal Result
  并变为 terminal；
- child Attempt 使用既有 `cause=retry`、`parent_attempt_id=父 Attempt`；
- 独立 ContinuationDecision/Seed 必须绑定 child Attempt，表达
  `outer_targeted_followup`，不能只靠 `cause=retry` 猜测；
- child Attempt 获得新的 identity、trace、Stage 2 per-Attempt budget 和 scoped
  EvidenceUse；Goal ID保持不变；
- 普通 public retry 不得伪造 audit/seed，也不得冒充 targeted continuation。

这不会扩张或重解释 Stage 1 AttemptCause 枚举。restart/resume 保持同一非终态
Attempt；goal revision 仍只能走专用 `revise_goal`；Task terminal 后的任何后续
工作仍必须创建 `parent_task_id` child Task。

`blocked` 不创建 child，也不终结 Task：同一 Attempt 进入 `blocked` 或
`waiting_user` 并保存完整 outer checkpoint，供 Stage 4 的显式用户输入/恢复协议
处理。`accept`、`stop_partial` 和 `stop_insufficient` 才终结 Task；
`targeted_continue` 才原子终结父 Attempt并创建 child。专用 continuation
transaction 不修改或放宽既有 public `complete_attempt` / `retry_attempt`
校验，只在单一事务中组合等价的终态、lineage 和 single-active-Attempt 不变量。

### 4.6 Result 与最终 artifact

Task terminal success 必须引用：

- current ProvisionalArtifact；
- accepted OuterAuditRecord；
- all-required-satisfied constraint fingerprint；
- exact evidence/currentness observations；
- generation/audit/evaluator policy versions。

可用 linkage record 或 additive result extension 实现；不得只把自由文本 reason
写进 Result。Stage 2 artifact 保持 immutable，不原地“升级”为 final。

## 5. Authority、状态机与原子提交

### 5.1 Deterministic gate

最终 gate 只接受：

- immutable Goal/ConstraintSpecSnapshot；
- current、Attempt-scoped、可重建 EvidenceUse；
- shared citation/grounding validator；
- registered constraint evaluator 的 typed result；
- runtime budget、lineage、ownership 和 SideEffect safety facts。

Provider 可在另获授权后提出 candidate audit 或 targeted objective，但不能：

- 直接写 final ConstraintAuditObservation；
- 将 confidence 转为 satisfied；
- 创建或修改 evidence/citation identity；
- 降低 constraint required/evaluator policy；
- 绕过 deterministic gate。

### 5.2 Outer state machine

```text
awaiting_audit
  → auditing
  → accepted
  → targeted_continuation_committed
  → stopped
  → blocked
  → failed
```

公开 command 每次只提交一个可解释语义转换。相同 command/payload replay 返回
同一 receipt；同 command/different payload fail closed。

### 5.3 Atomic publication

audit/decision commit transaction 至少包含：

- Task 非终态、active Goal/Attempt、expected state/checkpoint；
- current owner/epoch/lease；
- source artifact/currentness/constraint snapshot guard；
- audit observations、OuterAudit、CompactImprovementState；
- outer budget/progress；
- outer checkpoint；
- Result 与父 Attempt terminalization（若决定结束本 Attempt）；
- targeted child Attempt、Trace 和 ContinuationSeed（若继续）；
- Event、Task state version 和 CommandReceipt。

任何 fault 必须回滚全部半提交。targeted child 不得在没有 audit/parent Result/
seed 的情况下出现；父 Attempt 也不得在 child 创建失败时单独终结。

Provider 或其他外部动作继续遵守：

```text
SideEffect reserve/commit → external call → receipt → guarded audit commit
```

旧 epoch、未知 in-flight、stale checkpoint 或 payload mismatch 不能提交 audit、
Result、child Attempt、seed、Event 或 receipt。

## 6. Budget、Progress 与停止条件

初始 acceptance profile：

```yaml
budget_profile: v5-a-stage3-outer-v1
max_outer_audits_per_goal: 3
max_targeted_continuations_per_goal: 2
max_consecutive_semantic_no_progress: 2
max_distinct_targeted_objectives_per_goal: 2
max_total_inner_actions_across_attempt_lineage: 24
max_total_evidence_uses_across_attempt_lineage: 48
max_outer_context_characters: 8000
max_total_outer_runtime_seconds: 900
provider_logical_calls_without_separate_authorization: 0
```

Stage 2 per-Attempt budgets 继续生效；Stage 3 outer aggregate budget 跨所有
targeted child Attempts 单调累计。创建 child Attempt 可以获得新的 Stage 2
per-Attempt ledger，但不能重置 outer ledger 或绕过 aggregate cap。

有效 outer ProgressDelta 至少满足一项：

- 新 required constraint 由允许 evaluator 从非 satisfied 变为 satisfied；
- unresolved required constraint 数量减少；
- 与具体 unresolved constraint 绑定的新 current evidence group 被验证；
- evidence conflict/currentness gap 被解除；
- audited answer status 实质改善。

新文本、新 query、新 segment ID、新 child Attempt、重复 evidence、candidate
confidence 或 target wording 改写均不单独算 progress。

progress fingerprint 至少包含：

- sorted constraint statuses/recoverability；
- current evidence identity set；
- conflict/currentness flags；
- audited answer status；
- normalized blocker。

相同 gap/progress fingerprint 连续两轮出现，或相同 target 在同一 fingerprint
下重复，必须 durable stop；不得 opportunistic rerun。

必须停止或阻塞：

- 任一 outer hard budget 耗尽；
- no-progress/repeated target 达阈值；
- 没有具体 recoverable gap；
- artifact/evidence stale、missing、invalid 且无安全 rematerialization；
- 没有 registered gap policy 的 unsupported natural-language constraint 只能
  等待用户/未来授权 evaluator；
- needs user input；
- unresolved external SideEffect；
- owner/checkpoint/lineage 冲突；
- Provider 或 implementation failure。

其中，natural-language constraint 若有 registered deterministic gap policy，
可以在“不宣称 satisfied”的前提下判定为 `unknown + recoverable` 并允许一次
targeted evidence follow-up；若没有该策略，或 follow-up 后仍没有权威 evaluator
可判定满足，则进入 `needs_user`，不能循环搜索来伪造成功。

## 7. Result Classification

| 情形 | answer_status | termination_reason | failure_class | Task |
| --- | --- | --- | --- | --- |
| 所有 required constraints 权威满足 | `valid_success` | `answer_ready` | `none` | terminal |
| 创建 targeted child Attempt | 保留 `valid_partial`/`valid_insufficient` | `targeted_continuation`（新增） | `none` | running |
| 有有效部分答案但 outer budget 耗尽 | `valid_partial` | `budget_exhausted` | `none` | terminal |
| 无足够答案且 outer budget 耗尽 | `valid_insufficient` | `budget_exhausted` | `none` | terminal |
| 连续无语义进展 | 保留有效 answer status | `no_new_evidence` | `none` | terminal |
| required constraint 不可恢复地未满足 | `valid_partial`/`valid_insufficient` | `constraint_unsatisfied`（新增） | `none` | terminal |
| 需要用户或无已授权 evaluator | 保留有效 answer status | `needs_user_input` | `none` | waiting_user |
| current evidence 不可用 | `valid_insufficient` 或保留 partial | `evidence_unavailable` | `none` | terminal/blocked，按 recoverability |
| Provider candidate/audit 失败 | 保留已有有效 answer status | `provider_error` | `provider_failure` | blocked |
| 代码/事务不变量失败 | 保留已有有效 answer status或 `not_produced` | `implementation_error` | `implementation_failure` | blocked |
| fixture/环境无效 | 保留可恢复事实 | 精确 reason | `infrastructure_invalid_run` | 不计产品结论 |
| evaluator/判分基础无效 | 保留可恢复事实 | 精确 reason | `evaluation_invalid_run` | 不计产品结论 |

`targeted_continuation` 与 `constraint_unsatisfied` 需要 additive enum/schema
migration source 和回归测试。不得把它们塞入 failure class 或仅写在 reason text。
`blocked`/`waiting_user` 行的三个正交维度保存在 outer checkpoint/Event；在
Attempt/Task 尚未终结时不得伪造 terminal Result。

## 8. 允许与禁止范围

### 8.1 建议授权

```yaml
allowed_changes:
  source:
    - src/shiliu/research/**
    - additive Stage-3-specific integration under src/shiliu/**
    - minimal /research outer audit/advance/status API
  tests:
    - Stage 3 deterministic unit/integration/fault tests
    - directly caused Stage 1/2 regression fixes
  schema:
    - additive constraint/audit/improvement/continuation/result-link state
    - additive termination reason values
    - versioned migration source
  migration_execution:
    temporary_databases_only: true
    live_database: false
  prompts:
    new_versioned_stage_3_candidate_roles: wiring_only
    existing_v4_fast_deep_prompts: protected
  provider:
    candidate_adapter_and_side_effect_wiring: allowed
    real_calls: false
  ui: false
  dependencies:
    new_upstream_dependencies: false
```

### 8.2 明确禁止

- 在 Stage 2 正式接受和本 Contract 授权前开始实施；
- live DB migration，或把 schema 9 source 合入会自动 initialize live DB 的活跃
  runtime；
- 真实 Provider、付费服务、credential/Keychain；
- 修改既有 V4 Prompt、model choice、Tool Contract 或正式 UI；
- 把 provider/model candidate、confidence、answer text 当 final gate；
- 完整 HITL/input/interrupt/cancel、branch/replay 控制面（Stage 4）；
- Stage 5 产品完成、正式 trace UI、held-out quality eval；
- 复制 DeerFlow/AREX 源码、Prompt、模型、权重或新增其依赖；
- Program Current State、Program Decision Ledger、Registry、Research Log、
  长期路线、Push、Merge 或 Tag。

## 9. Provider 与数据边界

```yaml
runs:
  deterministic_tests: allowed_after_contract_authorization
  temporary_sqlite_migration_tests: allowed_after_contract_authorization
  no_provider_product_cases: allowed_after_contract_authorization
  provider:
    allowed: false
    maximum_logical_calls: 0
    maximum_transport_attempts: 0
    retries: 0
  heldout:
    allowed: false
  live_database_migration: false
```

若主 Session 后续单独授权 Provider 验证，必须另行冻结 provider/model roles、
versioned prompt、最大 logical/transport calls、retry policy、发送数据、SideEffect
identity、失败分类和有效 Run 证据。接受本 Contract 本身不授予调用权限。

## 10. 定向测试矩阵

### 10.1 Constraint 与 authority

- Goal revision 产生稳定 constraint IDs；重放收敛，payload mismatch fail closed。
- objective 必须存在 required constraint；空 success constraints 不自动通过。
- candidate/model/confidence 不能直接写 satisfied；unsupported natural-language
  constraint 为 unknown/needs_user。
- registered deterministic evaluator 只能引用当前 artifact allowlist；forged、
  stale、跨 Attempt evidence 拒绝。
- audit commit 前 source drift 追加 observation，旧 identity/artifact 不改写，
  该 constraint 不得 satisfied。
- 跨 Task/Goal/Attempt 的 audit、budget、constraint observation 和 seed 隔离。

### 10.2 Continuation lineage

- all-required-satisfied 原子提交 accepted audit、final linkage 和 Task terminal
  Result；terminal Task 不可复活。
- recoverable gap 原子提交 parent Result、parent terminal、ContinuationDecision、
  child `cause=retry`、Trace、Seed、Event、receipt；任一 fault 全量回滚。
- child Goal 与 parent 相同，targeted objective 只存在于 seed/execution scope，
  不修改 Goal objective。
- 普通 retry 无法伪造 audit continuation；非法 source audit/checkpoint/artifact
  组合无状态漂移。
- carry-forward identity 在 child 重新创建 scoped EvidenceUse/currentness；
  parent use/provenance/allowlist 不被借用。
- restart 从 child seed 恢复；resume 保持 child Attempt identity。

### 10.3 Budget、no-progress、race

- outer budgets 跨 retry child、restart、replay、takeover 单调且不重置。
- evidence/inner-action aggregate cap 与 Stage 2 per-Attempt cap 同时执行。
- 相同 constraint/evidence/status blocker 连续两轮停止；文字改写不算进展。
- 新 evidence 只有映射到 unresolved constraint 并通过 evaluator 才计 progress。
- same command race 只产生一个 audit/Result/child/receipt；payload mismatch
  fail closed。
- takeover 后旧 owner candidate/response 不得提交；新 owner从同一 budget 和
  audit lineage 继续。
- unresolved `in_flight/unknown` 阻止 audit finalization 和 child creation。
- audit/constraint/checkpoint/result/child/seed/Event/receipt 每个 fault point
  都有 rollback 测试。

### 10.4 API、migration 与回归

- public service/API 对抗覆盖 invalid phase、非最新 artifact、terminal Attempt、
  stale checkpoint、unsupported constraint、unauthorized provider。
- get/status 能按稳定顺序返回 constraint/audit/continuation lineage，重启一致。
- schema migration 只在临时 SQLite 执行，含 backup/idempotence/integrity/
  foreign-key/fault tests；live DB 指纹不变。
- Stage 1、Stage 2、Evidence/Citation、`/search`、Fast/Deep `/ask` 与默认无
  Provider 回归通过。

## 11. 可验收证据

Implementation Report 至少提供：

1. Stage 2 正式接受记录、同步 baseline、实际 commits、diff 和 clean tree；
2. Contract 逐项矩阵；
3. schema/migration source 与临时 DB tests；
4. constraint authority、candidate/gate separation、artifact currentness；
5. parent Result + child Attempt 原子 lineage、carry-forward isolation；
6. outer budget/no-progress/restart/replay/takeover/race/fault tests；
7. Stage 3 suite、Stage 1/2 联合定向和默认无 Provider回归；
8. live DB SHA/size/mtime/schema 前后证据；
9. Provider logical/transport calls 为 0，credential/Keychain 未访问；
10. Prompt/Tool Contract/UI/Program 权威文件未改的 diff 证据；
11. `not_exercised`、`unproven`、失败、warning 与 residual risks。

## 12. 明确未证明项

即使 deterministic Stage 3 实施通过，也不证明：

- 任意自然语言 objective/constraint 的语义满足可由现有规则判定；
- 真实 Provider audit/target generation 的正确性、成本、延迟或稳定性；
- 模型 candidate 能可靠识别全部 constraint gap；
- live DB schema 9 migration；
- 完整 user-input/HITL、cancel、branch/replay control plane；
- 真实断电、多主机长期 lease soak、production-scale retention/performance；
- Stage 5 held-out product quality 与最终用户体验。

这些必须保持 `not_exercised` 或 `unproven`，不能由 deterministic fake 或
citation validity 外推。

## 13. Just-in-time 实施计划

本计划只在 Stage 2 正式接受、本 Contract 被授权后执行；内部 Commit 不要求
主 Session 逐个审批。

1. **Accepted baseline sync**：fast-forward/rebase 到主 Session 接受 baseline，
   复核 Stage 2 acceptance delta、schema 和完整无 Provider基线。
2. **Schema and codecs**：先实现 ConstraintSpec、AuditCandidate/Observation、
   OuterAudit、CompactImprovementState、ContinuationDecision/Seed、outer
   aggregate budget 和 result linkage；只在临时 DB migration。
3. **Deterministic gate**：实现 registered evaluator registry、artifact
   currentness/citation guard 和 unknown/unsupported fail-closed；先写 candidate
   越权、stale/cross-Attempt tests。
4. **Atomic continuation kernel**：实现专用 audit/advance transaction，原子
   parent Result/terminalization + child retry Attempt/Trace/Seed，接入 owner、
   expected state/checkpoint、receipt 和 SideEffect guard。
5. **Targeted inner integration**：让 child Stage 2 run 从 Seed 读取 bounded
   targeted objective，重新 materialize carry-forward identity 为 child-scoped
   use；不重置 outer budget。
6. **Progress and stops**：实现 constraint/evidence/status fingerprint、typed
   blocker、aggregate budgets、no-progress 和 honest partial/insufficient stop。
7. **Provider wiring only**：如 Contract 接受，仅增加 versioned candidate
   adapter 与 SideEffect wiring；真实调用继续 fail closed。
8. **Minimal API and regression**：接入 outer audit/advance/status JSON API，
   跑 fault/race/restart、Stage 1/2 联合定向和默认无 Provider回归。
9. **Implementation Report**：记录 commits、证据、未证明项与 live DB 指纹，
   提交 V5 主 Session 正式验收；不自行开始 Stage 4。

## 14. 请求主 Session 的少量边界决定

1. 先决定 Stage 2 Round 2：`accept / partial_accept / rework / pause / reject`；
   没有正式接受时 Stage 3 保持 Draft。
2. 若 Stage 2 接受，再决定本 Contract：
   `accept / partial_accept / rework / pause / reject`。
3. 若接受，授权第 8.1 节产品源码、schema/migration source、临时 DB tests、
   deterministic gate、targeted continuation 和 Provider wiring-only 范围。
4. 确认真实 Provider runs、live migration、Prompt/Tool Contract/UI 与 Stage 4/5
   仍未授权。

```yaml
stage_3_contract_status: draft_pending_main_review
stage_3_implementation_authorized: false
stage_3_implementation_started: false
stage_3_provider_runs_authorized: false
stage_3_live_database_migration_authorized: false
next_action: V5_main_session_stage_2_acceptance_then_stage_3_contract_review
```
