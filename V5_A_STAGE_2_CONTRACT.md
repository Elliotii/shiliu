# 拾流 V5-A Stage 2 Contract

```yaml
stage: V5-A Stage 2
title: Evidence-backed Inner Research Loop
contract_status: draft_pending_main_review
proposal_authority: V5-A execution session
acceptance_authority: V5 main session
created_at: 2026-07-31
revised_at: 2026-07-31
main_review_round_1: rework_evidence_record_semantics
version_charter: V5_A_VERSION_CHARTER.md
stage_1_acceptance_record: V5_A_STAGE_1_MAIN_SESSION_ACCEPTANCE_DECISION.md
baseline_branch: codex/v5-a
baseline_commit: fc4708eacb93e9b6b3d479d50e096cc95dd6be31
implementation_authorized: false
implementation_started: false
provider_wiring_proposed: true
provider_runs_authorized: false
provider_runs_performed: false
live_database_migration_authorized: false
```

> 本文件是 Stage 2 的实施边界草案，不是实施提交，也不构成自我验收。只有
> V5 主 Session 接受本 Contract 后，V5-A 才能开始本阶段产品实现。即使
> Contract 被接受，也不自动授权真实 Provider 运行或 live DB migration。

## 1. Stage 使命

在已接受的 Durable Task Kernel 上建立一个可恢复、有硬预算、以当前字幕版本为
事实权威的 Inner Research Loop：

```text
Plan
→ Navigation
→ Transcript Search
→ Authoritative Window Read
→ Evidence Collection
→ Provisional Synthesis
→ Durable Checkpoint
```

本阶段证明“内层研究步骤可以在 Task / Goal / Attempt 身份内持久推进，并产生
可重建、可校验引用的 provisional synthesis”。本阶段不判断整个 Goal 已满足，
不做 Outer Goal Audit 或 recursive continuation，也不把模型自信当 verifier。

## 2. 最小纵向产品切片

Stage 2 完成后，受控 `/research` 产品入口至少能够：

1. 对已取得有效 ownership 的非终态 Task/Attempt 启动或继续一次 bounded inner run。
2. 从当前 Goal 构造 schema-versioned、可重建的 compact planning state。
3. 执行 navigation、transcript search 和 transcript window read；navigation
   只缩小搜索空间，不成为事实证据。
4. 将 transcript candidate 经 exact chunk replay/materialization 绑定到当前
   `source_artifact_id`、`source_version`、`timeline_run_id` 和有序 segment identity。
5. 在数据库中分别持久化 immutable evidence identity、Task-scoped use/provenance
   关联和 append-only validation observation，以及 action receipt、预算消耗和
   语义进展，而不是只保存在 graph 内存中。
6. 从持久 evidence set 构造 bounded DecisionView，并可在完整 checkpoint 后
   进程重启继续；不会重复已收据化的动作。
7. 生成或由 deterministic adapter 模拟生成 provisional synthesis；每个事实
   block 只允许引用当前 evidence allowlist。
8. 在 synthesis/artifact 提交前再次校验实际使用的 source version；版本漂移时
   fail closed，不返回伪装成当前证据的结果。
9. 原子提交 immutable provisional artifact reference、完整 checkpoint、Event
   和 command receipt；Task 不得仅因 inner loop 产出 provisional synthesis
   而进入 terminal success。
10. 在预算耗尽、重复动作、无语义进展、证据不可用、stale source、ownership
    丢失或 side effect 不确定时，保存准确状态并安全停止。

Stage 2 可以增加最小 create/get/continue/status/trace 表达，但不做正式 UI、
完整 HITL、可视化 branch/replay 控制面或最终产品评估。

## 3. 起始 Baseline 与风险

```yaml
baseline:
  risk_level: 2
  branch: codex/v5-a
  commit: fc4708eacb93e9b6b3d479d50e096cc95dd6be31
  working_tree_clean_at_contract_start: true
  db_schema_source_version: 7
  live_db_schema_observed: 6
  live_db_migration_status: not_exercised
  stage_1_kernel_status: accepted
  provider_status: not_exercised
  corpus_runtime_identity: shiliu-live-current
  evidence_authority_mode: live_current_exact_replay
```

### 3.1 已接受的基础

- Stage 1 的 Task、Goal、Attempt、Checkpoint、Event、Trace、Result、
  CommandReceipt、SideEffectRecord。
- Task state-version CAS、single-active-owner lease/epoch fence、checkpoint
  lineage、command dedupe、side-effect fail-closed。
- V4 的 source artifact/version identity、exact chunk replay、timeline-run
  boundary、stable citation identity。
- `EvidenceSearchService` 的 raw/product execution 与 candidate materialization。
- `TranscriptEvidenceMaterializer` 的 authoritative reconstruction 和
  `validate_current`。
- Fast/Deep 共用的 evidence fusion、bounded transcript context、citation
  allowlist、grounded output validation 和返回前 source revalidation。
- V4 Deep 的严格类型 action、确定性 DecisionView、预算 guard 和纯 reducer
  设计方式。

### 3.2 本阶段必须补齐

- durable inner-loop state schema 与 checkpoint codec；
- Research Task 与 retrieval/evidence provenance 的持久关联；
- immutable EvidenceIdentityRecord、Task-scoped EvidenceUse/Provenance、
  append-only EvidenceValidationObservation 和 provisional synthesis artifact；
- action-level receipt/dedupe、预算 ledger 和语义 progress fingerprint；
- Stage 1 ownership/checkpoint/SideEffect 与 inner actions 的集成；
- restart/crash/race/stale-source 下的恢复与 fail-closed；
- 最小研究继续 API 与无 Provider deterministic runner。

## 4. Just-in-time 源码审计结论

### 4.1 可继承资产

| 现有资产 | Stage 2 使用方式 | 证据边界 |
| --- | --- | --- |
| `evidence/source.py` | 生成 source/version/segment/timeline identity | raw subtitle bytes 是事实权威 |
| `evidence/mapping.py` | exact replay retrieval chunk | mapping 失败或跨 timeline 不可升级为证据 |
| `evidence/authority.py` | 绑定 live-current source version | index current 是前置条件，不替代 source bytes |
| `evidence/search.py` | 保存 execution/candidate provenance | candidate 仍不是 evidence |
| `ask/evidence.py` | materialize 与 commit 前 revalidate | stale/missing source 必须 fail closed |
| `ask/citations.py` | stable citation identity | identity 包含版本和有序 segments |
| `ask/context.py` | fusion、bounded context、citation allowlist | navigation metadata 不进入 factual context |
| `ask/validation.py` / `finalize.py` | grounded block validation 与共享 finalization | provisional output 仍不是 Goal verifier |
| `ask/deep/contracts.py` | strict bounded action shape | 只继承语义，不把当前 TypedDict 当持久 schema |
| `ask/deep/decision.py` | deterministic DecisionView projection | DecisionView 不是真实 Runtime state |
| `ask/deep/reducer.py` | 纯状态转换与 typed stop 的设计方式 | 重写 progress 判据 |
| Stage 1 `research/*` | identity、transaction、fence、checkpoint、receipt | 所有 mutation 继续受当前 owner fence 保护 |

### 4.2 明确不可继承的假设

1. V4 `run_id` 不能替代 Task/Goal/Attempt identity。
2. `DeepSearchGraph.compiled.invoke(...)` 的一次性进程内执行不是 durable resume。
3. `DeepSearchState.events`、AskService 内存 trace 或 retrieval trace 不能成为
   Research Task 的唯一状态权威。
4. `TranscriptEvidenceSpan.segments` 当前被排除在序列化外；不能直接把该对象
   dump 成持久 evidence 并假设重启后仍完整。
5. DecisionView 是 bounded projection；不得反向成为 checkpoint 或完整 Runtime state。
6. navigation document、summary、description、user note、matched excerpt 和模型
   provisional text 都不是 citation authority。
7. “出现新的 segment ID”只能表示检索集合变化，不能单独证明语义进展。
8. 一次性 graph 顺利结束、模型输出 `finish` 或 answer status `complete` 都不能
   证明整个 Research Goal 已完成。
9. retrieval trace 的持久成功不证明 evidence 已 materialize，也不证明返回时
   source version 仍当前。
10. V4 prompt、tool contract 和 Deep API 行为保持兼容；Stage 2 不原地改造成
    新持久协议。

不需要新增上游研究或依赖。已接受的 DeerFlow/AREX 仍只提供设计参考，Stage 2
不复制其源码、Prompt、模型或依赖。

## 5. 冻结语义模型

以下是 Contract 级逻辑对象。具体表名、类名、文件布局、索引和拆表方式由 V5-A
在实施中自主决定，但这些语义不能合并或丢失。

### 5.1 InnerResearchState

完整 checkpoint 的 payload 至少包含：

- `state_schema_version`
- `task_id` / `goal_id` / `attempt_id`
- `phase`
- `pending_action` 或明确为空
- 已提交 action/evidence/artifact 的稳定 ID 引用
- open research questions / scoped query keys
- rejected/repeated direction fingerprints
- `BudgetLedger`
- 最近和累计 `ProgressDelta`
- consecutive no-progress 计数
- current evidence-set fingerprint
- last complete checkpoint identity
- typed stop/block reason

checkpoint 只保存重建所需的小型状态和稳定引用，不内嵌完整 raw transcript、
secret、Provider credential、无限 trace 或未提交的外部响应。

恢复时必须从完整 checkpoint 读取，并重新查询 immutable records；不得从
DecisionView、最后一个 Event 文本或客户端请求体猜测真实状态。

### 5.2 InnerActionRecord

每个 research action 至少绑定：

- `action_id`
- Task / Goal / Attempt / originating checkpoint
- action kind 与 schema version
- canonical request hash / scoped action key
- owner epoch
- 状态：planned、reserved、running、succeeded、failed、unknown 或 rejected
- retrieval execution/trace reference 或 SideEffect reference
- bounded observation/artifact reference
- created/started/completed timestamps

同一 Attempt 中相同 canonical action key 的 replay 必须返回同一已提交语义
结果或被 repetition guard 拒绝，不能静默重新搜索/调用 Provider。

纯本地只读 retrieval 可以在单个受保护 command 中执行并提交 action receipt；
任何离开 SQLite transaction、可能计费或无法由本地状态证明 exactly-once 的
动作必须使用 Stage 1 SideEffectRecord。

### 5.3 Evidence Identity、Task Use 与 Currentness Observation

Stage 2 明确拆分三类事实，不能合并成一个可变 `EvidenceRecord`。

#### 5.3.1 EvidenceIdentityRecord

`EvidenceIdentityRecord` 是全局稳定、不可变、可重建的内容身份，至少持久化：

- `evidence_id` 与 citation identity version
- video/source identity
- `source_artifact_id`
- `source_version`
- `timeline_run_id`
- ordered `segment_ids` 与 `segment_ordinals`
- start/end time
- quote hash；可选受限 preview 只能用于展示，不能成为 authority
- canonical identity payload hash
- created time

`evidence_id` 只由 source/version/timeline/ordered segments 等内容身份决定，不含
Task、Goal、Attempt、query、rank、owner epoch、validation time 或 current/stale
状态。相同内容可由不同 Task 安全复用这一只读 identity；任何调用方都不得修改、
换绑或删除其历史身份。

并发创建相同 identity 必须由 canonical unique key/CAS（或等价数据库约束）
收敛到同一行。冲突行的 canonical payload/hash 必须完全一致；若相同
`evidence_id` 对应不同 payload，必须 fail closed，不能 last-write-wins。

#### 5.3.2 EvidenceUseRecord 与 EvidenceProvenanceRecord

`EvidenceUseRecord` 是不可变关联，将全局内容身份绑定到一次具体研究使用，
至少包含：

- `evidence_use_id`
- `evidence_id`
- Task / Goal / Attempt
- first producing action / originating checkpoint
- owner epoch
- fixed use purpose
- canonical use payload hash
- created time

隔离范围固定为 Attempt：同一 `(task_id, attempt_id, evidence_id)` 只有一个
canonical EvidenceUseRecord。同一 Task 的后续 Attempt、不同 Task 或 child Task
必须创建各自的 use record；不得借用另一 Task/Attempt 的 provenance、validation
或 citation allowlist membership。

每次检索发现该 identity 的来源单独写入 append-only
`EvidenceProvenanceRecord`，至少包含：

- `provenance_id` / `evidence_use_id`
- producing action、execution ID、search trace
- query fingerprint、rank、method、index identity
- parent retrieval chunk IDs
- `source_version_authority`
- materialization/mapping policy versions
- observed/materialized time
- canonical provenance hash

同一 query 或 replay 的重复 provenance 以
`(evidence_use_id, canonical_provenance_hash)` 去重；不同 query 的 provenance
追加新行，不更新或“合并覆盖”旧行。读取层可按稳定顺序派生聚合视图，但聚合视图
不是新的事实权威。

#### 5.3.3 EvidenceValidationObservation

每次 exact materialization 成功、checkpoint 使用或 artifact commit 前对现有
identity/use 的校验都追加不可变 `EvidenceValidationObservation`，至少包含：

- `observation_id`
- `evidence_use_id` / `evidence_id`
- Task / Goal / Attempt / checkpoint（适用时）
- validation policy/version 与 authority mode
- expected source version / observed source version
- outcome：current、stale、missing、invalid 或 typed error
- reason code
- owner epoch
- observed time

初始 materialization 若未通过 exact mapping/authority validation，不创建
EvidenceIdentity、EvidenceUse 或 current observation；失败只进入对应
InnerActionRecord/Event。已存在 identity/use 在后续校验中才可能产生 stale、
missing 或 invalid observation。

`current` / `stale` 是“在某个 authority、policy 和 observed time 下”的观察，
不是 EvidenceIdentityRecord 的可变属性。新的 stale observation 不修改旧 identity、
旧 provenance 或旧 observation，也不得把 identity 原地换绑到新 source version。
需要新版本证据时，必须 materialize 新的 `EvidenceIdentityRecord` 和当前
Task/Attempt-scoped use。

用于 checkpoint、ProgressDelta 或 synthesis commit 的 currentness，必须由同一
guarded command 为该 Task/Attempt、目标 checkpoint 和 exact evidence use 新产生
的 observation 派生；不能使用另一 Task/Attempt 的 observation，也不能仅依赖
缓存字段。读取“现在是否 current”时也必须从 scoped append-only observations
派生，并在需要作新提交时重新校验。stale/invalid use 不进入当前 citation
allowlist，不计入有效 progress。

共同规则：

1. identity 只有 exact materialization 成功后才能创建；candidate 不能创建
   evidence identity。
2. 使用时从 authoritative source 重建或验证 quote/timing/citation；DB preview
   与 retrieval excerpt 不能覆盖 source。
3. global identity dedupe 只复用不可变内容；Task isolation、ownership、
   provenance、budget、progress 和 currentness 全部留在 scoped association/
   observation 层。
4. identity insertion、use/provenance/observation append 仍受 current owner
   fence、expected state/checkpoint 和事务 guard 保护。

### 5.4 ProvisionalSynthesisArtifact

Stage 2 必须提交 immutable provisional artifact，至少包含：

- artifact ID / schema version
- Task / Goal / Attempt / checkpoint lineage
- normalized user objective reference
- answer status
- ordered answer blocks与每个 block 的 citation IDs
- limitations
- evidence-set fingerprint、实际使用的 EvidenceUseRecord IDs 与对应
  EvidenceIdentityRecord IDs
- generation/validator policy version
- provider SideEffect/response reference（若未来另获运行授权）
- commit-time EvidenceValidationObservation IDs
- created time

它是可审计的内层产物，不是 Evidence，不是 outer GoalAudit，也不是自动的
Task terminal Result。若 Stage 2 提交 Attempt Result，其
`answer_status / termination_reason / failure_class` 仍须保持正交，并且
`is_task_terminal=false`；仅有 provisional artifact 不得把 Task 置为 terminal。

### 5.5 BudgetLedger 与 ProgressDelta

预算必须持久、单调消耗并由服务端执行。初始 acceptance profile：

```yaml
budget_profile: v5-a-stage2-inner-v1
max_decision_rounds: 6
max_research_actions: 12
max_focused_videos_per_action: 8
max_window_each_side: 4
max_consecutive_no_progress: 2
max_materialized_evidence_uses_per_attempt: 24
max_synthesis_context_characters: 12000
max_total_runtime_seconds: 360
provider_logical_calls_when_not_separately_authorized: 0
```

实施中可在不减弱“服务端硬上限、持久计数、恢复后不重置”的前提下调整具体
数值；最终 Implementation Report 必须记录实际 profile 和测试边界。

有效 `ProgressDelta` 至少满足一项：

- 新增当前版本有效且 identity 不重复的 evidence group；
- 新增不同事实覆盖范围，而不只是同一 source 的重复窗口；
- 用更直接/更高权威的 transcript evidence 替代弱候选；
- 解决一个明确 open question；
- 解除一个证据冲突或减少一个明确 evidence gap；
- citation-valid provisional answer status 实质改善。

新增文本、新 segment ID、重复 query 的另一个 rank、模型更长输出或
navigation result 增加，单独都不算有效 progress。连续两次无有效
ProgressDelta 必须以 `no_new_evidence` 或更精确 typed reason 停止。

## 6. Evidence Authority 与提交协议

### 6.1 Authority pipeline

```text
Navigation / retrieval hit
  = candidate
        ↓ exact replay + current source binding
Materialized transcript span
  = eligible evidence
        ↓ immutable EvidenceIdentity + Task-scoped EvidenceUse
        ↓ append-only currentness observation
Citation allowlist
  = synthesis may reference
        ↓ pre-commit source revalidation
Provisional synthesis artifact
  = citation-valid inner result
```

任一步失败都不能越级。尤其：

- summary、description、note、cleaned transcript projection 只可导航；
- raw/product search trace 只证明执行，不证明事实；
- 模型不能创建 citation ID；
- block 引用必须是本次持久 evidence set 的 allowlist 子集；
- `valid_insufficient` 是合法、可接受的产品结果，不得为“总要有答案”而降低
  evidence threshold。

### 6.2 原子提交边界

每个可变 research command 必须在一个 SQLite transaction 中提交：

- mutation guard / current owner fence 检查；
- action/evidence/artifact 的持久记录；
- BudgetLedger 与 progress state；
- Event；
- complete checkpoint；
- CommandReceipt；
- Task state version 更新。

若 action 涉及外部 SideEffect，外部调用不能与 SQLite transaction 跨界假装
原子。必须遵循：

```text
reserve + commit receipt
→ external call
→ durable external receipt
→ materialize/validate
→ checkpoint commit
```

存在 `in_flight` 或 `unknown` SideEffect 时不得提交声称安全续作的 checkpoint。
旧 epoch 的 `reserved` 只按 Stage 1 已接受的 takeover/rebind 协议接管；
旧 `in_flight` 仍只能在 fence 后转 `unknown + blocked`，不得自动重放。

### 6.3 Ownership

所有 inner-loop mutation、EvidenceIdentity insertion、EvidenceUse/Provenance/
ValidationObservation append、artifact commit、budget update、checkpoint 和
SideEffect transition 都校验：

- Task 非 terminal；
- expected Task state version；
- current owner ID；
- current owner epoch；
- lease 未过期；
- expected parent checkpoint；
- Attempt/Goal lineage 一致。

失去 lease 的旧 worker即使拿到迟到 retrieval/provider 响应，也不得写入
EvidenceUse、provenance、validation observation、artifact、checkpoint 或 receipt；
也不得借全局 identity 的幂等插入绕过 scoped owner fence。

## 7. Provider、Prompt、Migration 与产品边界

### 7.1 Stage 2 实施建议授权

```yaml
allowed_changes:
  product_source:
    - src/shiliu/research/**
    - additive Stage-2-specific integration modules under src/shiliu/**
    - minimal /research API wiring
  tests:
    - Stage 2 deterministic unit/integration/fault tests
    - existing no-provider regression fixes caused directly by Stage 2
  schema:
    - additive Stage 2 evidence/action/artifact state
    - versioned migration source
  migration_execution:
    temporary_databases_only: true
    live_database: false
  prompts:
    new_stage_2_versioned_roles: allowed_for_wiring_only
    existing_v4_fast_deep_prompts: protected
  provider:
    abstraction_and_side_effect_wiring: allowed
    real_calls: false
  ui: false
  dependencies:
    new_upstream_dependencies: false
```

是否使用表或 artifact file 存放较大 immutable payload，由 V5-A 自主决定；
SQLite 必须保存稳定 identity、hash、lineage 与可恢复引用。artifact file 写入若
进入正式路径，必须使用 SideEffect/atomic publication 语义，不能只依赖临时文件名。

### 7.2 明确禁止

- live DB migration；
- 真实 Provider、付费服务、credential/Keychain 访问；
- 修改既有 V4 Fast/Deep Prompt、model choice 或 Tool Contract；
- 修改正式 UI；
- Outer Goal Audit、recursive continuation、完整 HITL/interrupt、
  branch/replay 控制面；
- 把 provisional synthesis 当 Final Synthesis 或 Goal verifier；
- 复制 DeerFlow/AREX 源码、Prompt、模型、权重，或增加其依赖；
- 改 Program Current State、Program Decision Ledger、Registry、Research Log
  或长期路线；
- Push、Merge、Tag。

真实 Provider 运行必须由单独、显式、带调用预算和数据边界的授权记录开启；
不能由 Contract 接受、provider wiring 完成或 deterministic adapter 通过推导。

## 8. 停止、失败与结果分类

### 8.1 必须停止的运行条件

- hard budget 任一维度耗尽；
- 连续 no-progress 达到上限；
- canonical action 重复；
- 无可 materialize 的 evidence；
- source/version/index authority 不满足；
- evidence 在 artifact commit 前变 stale；
- ownership/lease/epoch/checkpoint guard 失败；
- unresolved external SideEffect；
- cancel、needs-user-input 或实现错误。

### 8.2 正交分类

| 情形 | answer_status | termination_reason | failure_class |
| --- | --- | --- | --- |
| 有 citation-valid provisional answer，正常停 | `valid_success` 或 `valid_partial` | `answer_ready` | `none` |
| 正确判断证据不足 | `valid_insufficient` | `evidence_unavailable` | `none` |
| 有部分有效答案后预算耗尽 | `valid_partial` | `budget_exhausted` | `none` |
| 无实质进展但已有部分答案 | `valid_partial` | `no_new_evidence` | `none` |
| Provider 未形成有效输出 | `not_produced` 或保留已有 `valid_partial` | `provider_error` | `provider_failure` |
| 代码/事务不变量失败 | `not_produced` 或保留已有有效维度 | `implementation_error` | `implementation_failure` |
| 环境/fixture 使运行无效 | 依可恢复事实记录 | 精确 reason | `infrastructure_invalid_run` |
| evaluator/判分本身无效 | 依可恢复事实记录 | 精确 reason | `evaluation_invalid_run` |

Stage 2 deterministic adapter 不能证明 provider success 或 provider quality；
这些保持 `not_exercised`。Provisional `valid_success` 也不等于 Task terminal
success 或 Goal 已满足。

## 9. 定向测试矩阵

### 9.1 Evidence 与 citation

- 同 source/version/timeline/ordered segments 在跨 Task/Attempt 并发命中时只形成
  一个 immutable EvidenceIdentityRecord；canonical payload mismatch fail closed。
- 每个 Task/Attempt 形成独立 EvidenceUseRecord；另一 Task/Attempt 的 provenance、
  validation observation、allowlist membership 和 budget/progress 均不可见、不可复用。
- 同 Attempt 多 query 命中同一 identity 只形成一个 use；不同 provenance
  append-only 保存，重复 provenance hash 去重，读取聚合顺序稳定。
- retrieval candidate、navigation snippet、summary/note 均不能进入 citation allowlist。
- exact mapping mismatch、cross-timeline、missing source、index not current fail closed。
- source version 在 search 后、materialize 前和 artifact commit 前发生漂移；
  追加 stale EvidenceValidationObservation，不改写 identity/use/provenance 历史，
  artifact 不得引用该 stale use。
- artifact commit 后 source 才漂移时，旧 artifact 与其 commit-time observation
  保持不可变审计历史；追加新的 stale observation，当前产品视图不得把旧 artifact
  继续表示为 current。
- 同一 identity 的 current/stale observations 并发提交时各自 append；提交边界只
  使用本 Task/Attempt、正确 owner epoch 和对应 checkpoint 的 observation 派生状态。
- forged/unknown citation、无 citation factual block、重复 citation、不足结果带
  answer block 均被 deterministic validation 拒绝。
- restart 后从持久 identity 重建 quote/timing/jump URL，与原 authoritative
  segments 一致；不依赖序列化排除的内存 `segments`。

### 9.2 Checkpoint、crash 与 replay

- 每个成功 action 与 EvidenceUse/Provenance/ValidationObservation、budget、
  Event、checkpoint、receipt 同事务；任一 fault point 回滚无半提交。全局
  immutable identity 如已由并发事务存在，只能复用相同 canonical payload。
- 完整 checkpoint 后进程重启，pending action、budget、evidence set 和
  no-progress counter 不重置。
- crash 发生在 retrieval 完成但 commit 前：重放不产生重复 action/evidence。
- crash 发生在 provisional artifact publish 各阶段：不存在无 lineage 的孤儿
  artifact，或可由明确 recovery 规则安全清理/续作。
- stale expected checkpoint/state version 不能提交。
- DecisionView 丢失或改变不能改变 checkpoint 真值。

### 9.3 Ownership 与 SideEffect

- takeover 后旧 worker的迟到 retrieval/provider response 被 fence。
- `reserved` SideEffect 只按已接受协议重绑定一次；`in_flight` 不自动重放。
- same task/kind/key + same hash dedupe；hash mismatch fail closed；跨 Task key
  不冲突。
- unresolved `in_flight/unknown` 阻止完整 checkpoint 与 provisional artifact commit。
- provider deterministic adapter 覆盖 reserve→in-flight→receipt→checkpoint、
  reserve fault、receipt fault 和 concurrent replay；不发网络请求。

### 9.4 Budget 与 progress

- round/action/window/evidence/context/time 上限均由服务端执行。
- restart、retry command replay 和 owner takeover 不重置已消耗预算。
- 新 segment 但同一 evidence identity、重复 window、重复 navigation、模型
  改写不计 progress。
- 新有效 evidence group、解决 open question 或 citation-valid status 改善计 progress。
- 连续 no-progress、repeated action、budget exhaustion 均产生准确 Event、
  checkpoint 和结果维度。

### 9.5 Product slice 与回归

- 公共 service/API 对抗测试覆盖非法 phase/action/identity 组合，无状态漂移。
- provisional artifact 始终绑定 Task/Goal/Attempt/checkpoint/evidence set。
- inner success 不可把 Task 置 terminal；terminal Task 不能启动 inner run。
- `/research` get/status/trace 能在重启后重建状态，Trace 丢失不改变 Task truth。
- 既有 `/search`、Fast `/ask`、Deep `/ask`、Evidence/Citation、Stage 1 kernel
  默认无 Provider回归通过。
- migration 只在临时 SQLite 测试，live DB hash/size/mtime 前后不变。

## 10. 可验收证据

Implementation Report 必须提供：

1. baseline、实际 commits、diff 范围和 clean working tree；
2. Contract 逐项满足矩阵；
3. schema/migration source 与临时 DB upgrade/rollback/fault 证据；
4. evidence identity/use/provenance/currentness isolation、source drift、
   citation validation、restart、crash、race、idempotency、ownership、budget、
   no-progress 的测试名称与结果；
5. 完整 Stage 2 定向 suite 与默认无 Provider回归结果；
6. live DB 前后 SHA-256、size、mtime；
7. Provider logical calls/transport attempts 为 0，credential/Keychain 未访问；
8. Prompt/Tool Contract/UI/Program 权威文件未改的 diff 证据；
9. `not_exercised`、`unproven`、失败、warning 和 residual risks；
10. 若产生新的材料性上游结论，只提出 Registry/Research Log 更新建议，不直接修改。

### 10.1 Stage 2 成功标准

```yaml
success:
  durable_inner_state: pass
  evidence_authority_and_reconstruction: pass
  provisional_synthesis_grounding: pass
  checkpoint_restart_and_replay: pass
  ownership_and_side_effect_safety: pass
  bounded_progress_and_stop: pass
  public_api_adversarial_tests: pass
  existing_no_provider_regression: pass
  live_database_unchanged: pass
  provider_runs: not_exercised
  outer_goal_audit: not_implemented
```

## 11. 明确未证明项

Stage 2 即使通过也不证明：

- Outer Goal Audit、claim/conflict completeness 或 recursive continuation；
- provisional synthesis 满足整个用户 Goal；
- 真实 Provider 的正确性、稳定性、成本、延迟或产品质量；
- live DB migration；
- 真实断电、多主机长期 lease soak、真实 external reconciliation；
- 完整 HITL、branch/replay UI 或 production-scale retention/performance；
- Stage 5 最终产品体验与 held-out quality eval。

这些项目不能由无 Provider测试或现有 V4 Deep 表现外推。

## 12. 暂停条件

出现以下任一情况，V5-A 必须停止并向主 Session提交事实、选项与建议：

- 需要执行 live DB migration 或读取真实 credential；
- 需要真实 Provider 运行但没有独立授权；
- 无法保持 transcript/source-version/citation authority；
- 需要修改既有 Fast/Deep Prompt、model choice、Tool Contract 或正式 UI；
- Stage 1 已接受的 terminal、ownership、checkpoint 或 SideEffect 语义需要材料性改变；
- 需要新增上游依赖、复制上游代码，或 License/数据边界发生材料变化；
- 目标实质扩张到 Outer Audit、HITL、Stage 5 Eval 或长期路线变更；
- baseline/working tree/Program authority 出现冲突。

普通 schema 命名、模块布局、索引、transaction helper、测试拆分和内部 API
选择不触发暂停，由 V5-A 自主负责。

## 13. Just-in-time 实施计划

Contract 获接受后按以下依赖顺序实施；这些是执行工作包，不是主 Session
逐步审批点：

1. **Persistent state first**：定义 versioned inner state codec、BudgetLedger、
   Action、immutable EvidenceIdentity、scoped EvidenceUse/Provenance、
   append-only ValidationObservation、Artifact records 和临时 DB migration tests。
2. **Authority adapter**：将现有 EvidenceSearch/Materializer/Citation 包装成
   Task-scoped、可收据化的纯输入输出边界，先完成 stale/mapping 对抗测试。
3. **Durable action engine**：接入 Stage 1 owner fence、command receipt、
   checkpoint 与 deterministic actions，完成 restart/crash/replay。
4. **Progress and stop**：实现 semantic fingerprint、ProgressDelta、repetition
   和 hard budgets，替代 segment-ID-only progress。
5. **Provisional synthesis**：接入 shared grounding/finalization 语义和
   deterministic provider adapter，提交 immutable artifact；真实 Provider 仍禁用。
6. **Minimal API and regression**：接入受控 `/research` continue/status/trace，
   跑 Stage 2 suite、Stage 1 suite 和默认无 Provider回归。
7. **Implementation Report**：记录证据、未证明项和 diff，提交主 Session
   进行正式 Stage 2 验收。

## 14. 请求主 Session 的边界决定

只请求以下 Stage 边界决定，不请求逐字段设计审批：

1. `accept / partial_accept / rework / pause / reject` 本 Contract。
2. 若接受，是否按第 7.1 节授权 Stage 2 产品实现、临时 DB migration tests、
   新的 Stage-2-specific versioned prompt/Provider wiring；建议接受。
3. 确认真实 Provider runs 与 live DB migration 仍保持未授权；建议确认。

```yaml
stage_2_contract_status: draft_pending_main_review
stage_2_implementation_authorized: false
stage_2_product_implementation_started: false
provider_runs_authorized: false
provider_runs_performed: false
live_database_migration_authorized: false
live_database_migration_performed: false
next_action: V5_main_session_stage_2_contract_review
```
