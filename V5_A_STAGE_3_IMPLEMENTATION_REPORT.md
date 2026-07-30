# 拾流 V5-A Stage 3 Implementation Report

```yaml
stage: V5-A Stage 3
title: Outer Goal Audit and Recursive Continuation
report_status: resubmitted_for_main_acceptance
acceptance_authority: V5 main session
contract: V5_A_STAGE_3_CONTRACT.md
contract_authorization: accepted_by_user_for_implementation
planning_commit: a8080054308c75405d096333fc2b885c1f3370f9
implementation_commit: 788d01c
main_acceptance_round_1: rework
rework_round_1_commit: this_bounded_rework_commit
implementation_completed: true
stage_3_self_accepted: false
provider_runs_authorized: false
provider_runs_performed: false
credential_or_keychain_accessed: false
live_database_migration_performed: false
stage_4_started: false
next_action: V5_main_session_stage_3_rework_review
```

## 1. 提交结论

Stage 3 最小纵向切片与 Main Acceptance Round 1 的两项限定返工均已实现，
现重新提交 V5 主 Session 验收：

```text
Stage 2 current provisional artifact
→ stable Goal-revision ConstraintSpec snapshot
→ append-only currentness + constraint observations
→ deterministic authority gate
   ├─ accept → immutable final Result linkage + terminal Task
   ├─ recoverable gap → atomic parent Result + retry child + Seed
   ├─ honest partial/insufficient terminal stop
   └─ needs-user / implementation blocker
→ outer checkpoint + Event + CommandReceipt
```

实现不把 candidate、confidence、citation presence、答案文字变化、新 query、
segment ID 或新 Attempt 当作 Goal 满足或语义进展。真实 Provider、凭据/Keychain、
live schema 9 migration、Prompt、Tool Contract、正式 UI 与 Stage 4 均未运行或修改。

Round 1 未重开已通过的持久模型、atomic continuation、ownership/SideEffect
fence、migration 或 API 主体。限定返工只关闭：

1. 调用方 `evidence_policy` 可伪造 deterministic evaluator authority；
2. accept 等非 continuation 路径可绕过 outer context hard budget，且 candidate
   缺少有界输入边界。

## 2. Commit 与 Diff 范围

产品与测试提交：

```text
788d01c feat(v5-a): implement durable outer audit continuation
15 files changed, 3416 insertions, 21 deletions
```

Main Acceptance Round 1 bounded rework（本报告所在提交）仅修改：

- `src/shiliu/research/outer_contracts.py`
- `src/shiliu/research/outer_service.py`
- `tests/test_v5_a_stage3_outer_audit.py`
- `V5_A_STAGE_3_IMPLEMENTATION_REPORT.md`
- `V5_A_CURRENT_STATE.md`

新增：

- `src/shiliu/research/outer_contracts.py`
- `src/shiliu/research/outer_service.py`
- `tests/test_v5_a_stage3_outer_audit.py`

修改：

- schema version 8 → 9、Result termination enum migration 和 additive Stage 3
  tables/triggers；
- Stage 1 task aggregate view 与 termination enum；
- Stage 2 child Attempt 从 ContinuationSeed 读取 targeted execution objective；
- `Application` lazy outer service 与最小 outer advance/status JSON API；
- 仅因 schema version 变化而受影响的既有测试断言。

未修改 Program Current State、Program Decision Ledger、Registry、Research Log、
长期路线、V4 Prompt、model choice、Tool Contract 或正式 UI；未增加依赖。

## 3. 持久模型与权威边界

| 合同对象 | 实现证据 | 状态 |
| --- | --- | --- |
| ConstraintSpecSnapshot | Goal revision-scoped stable ID、ordinal、原文/normalized text、required 标志、registered kind、versioned evaluator policy；immutable trigger | pass |
| AuditCandidate | deterministic/provider proposal 与最终 observation 分表；candidate/confidence 不参与 authority write | pass |
| ConstraintAuditObservation | append-only status/recoverability/evidence/currentness/reason；绑定 Task/Goal/Attempt/artifact/audit/owner epoch | pass |
| OuterAuditRecord | immutable source checkpoint/artifact、snapshot/observation/currentness refs、fingerprints、decision、blocker、before/after budget | pass |
| CompactImprovementState | bounded evidence identity、constraint buckets、currentness flags、blocker、target、budget 与 parent/child lineage refs | pass |
| ContinuationDecision/Seed | `outer_targeted_followup` 与普通 retry 分离；seed 绑定 parent audit/checkpoint/artifact、child 与 canonical target | pass |
| Final Result linkage | Result 绑定 accepted/stopped audit、artifact、constraint fingerprint、currentness IDs 与 policy versions | pass |
| Schema 9 migration | 临时 SQLite 重建 Result CHECK constraint，不改写既有 Result；additive tables/indexes/triggers；backup/idempotence/integrity/FK 通过 | pass |

Round 1 后 evaluator authority 不再读取 Task 创建请求中的任意
`evidence_policy.outer_audit`。服务启动时注入的 server-owned registry 以
`constraint_scope + normalized exact text` 绑定 evaluator kind、policy version、
required 标志和参数；ConstraintSpec snapshot 持久记录 registration identity。
registry 缺失或与已持久 snapshot 不一致时 fail closed。
修订后的 audit policy、evaluator registry 与 candidate schema 分别显式升为
`v2`，避免把旧的 caller-selected/unbounded 语义误认成同一版本。

只有上述精确注册且与约束语义相符的 `grounded_answer`、
`minimum_current_evidence` 或 `answer_status` evaluator 可以写 `satisfied`。
客户端 policy、provider candidate、confidence、citation presence 和 evidence
数量都不能为任意 objective/自然语言约束授予语义权威。未注册自然语言约束
固定为 `unknown + needs_user`；显式注册的 `targeted_evidence_once` 也只能授权
一次 bounded follow-up，不能宣称 satisfied。optional constraint 仍保存观察，
但不阻断所有 required constraints 已满足的 gate。

`AuditCandidateInput` 使用 strict typed schema，字段数、列表长度、单字段字符数
和 confidence 范围均由 API/model 校验；服务再执行 4,000 canonical serialized
characters 总上限。总量超限在 transaction 前 fail closed，不创建 candidate、
audit、checkpoint、Event 或 receipt。

## 4. 原子 continuation 与 Stage 2 衔接

`targeted_continue` 在一个 `BEGIN IMMEDIATE` transaction 内完成：

1. 复核 active Task/Goal/running Attempt、state version、latest inner checkpoint、
   owner ID/epoch/lease 和 unresolved SideEffect；
2. 追加 commit-time EvidenceValidationObservation；
3. 提交 immutable audit、constraint observations、improvement state 和 outer
   checkpoint；
4. 以 `termination_reason=targeted_continuation` 提交父 Attempt 的
   non-Task-terminal Result，并终结父 Attempt/Trace；
5. 创建同 Goal、`cause=retry`、带 parent/source lineage 的 child Attempt/Trace；
6. 创建专用 ContinuationDecision/Seed；
7. 对 current carry identities 创建新的 child-scoped EvidenceUse、provenance 与
   currentness observation，并以 child inner checkpoint 保存独立预算；
8. 更新 Task state version，提交 Event 与 CommandReceipt。

任一 fault 全量回滚。child 不修改 Goal objective；Stage 2 使用 Seed 的 bounded
targeted objective 作为执行 scope，后续 inner checkpoint 持久恢复该 objective。
父/child EvidenceUse ID 不复用，EvidenceIdentity 可稳定收敛。

## 5. Contract 逐项满足矩阵

| Contract 要求 | 实现/测试证据 | 结论 |
| --- | --- | --- |
| Stage 1/2 安全衔接 | 复用 owner fence、CAS、Checkpoint/Event/Trace/Result/Receipt/SideEffect 与 current artifact；不复活 complete inner state | pass |
| Constraint identity/authority | objective 永远 required；只有 server registry exact binding 可授权 evaluator；伪造 client policy、candidate 越权、unknown evaluator、optional constraint 对抗测试 | pass_after_round_1_rework |
| Evidence authority/currentness | audit commit 时从 immutable identity 重新观察 live-current source；stale/missing/跨 Attempt use fail closed；历史 identity 不改写 | pass |
| Accept path | all-required-satisfied 原子提交 audit、outer checkpoint、Result linkage、Attempt/Trace/Task terminal、Event/receipt | pass |
| Targeted continuation | parent Result + terminalization、child retry lineage、Trace、Decision/Seed、child-scoped carry use/currentness 同事务 | pass |
| Honest stop/block | budget/no-progress/repeated target/source drift 形成准确 terminal classification；无 evaluator 进入 waiting_user 且不伪造 Result | pass |
| Aggregate budgets | context 在 candidate/currentness/gate 前计算并对 accept/continue/stop/block 一致 hard-stop；ledger 跨 child/restart/replay/takeover 单调 | pass_after_round_1_rework |
| Semantic progress | fingerprint 仅含 constraint status/recoverability、EvidenceIdentity currentness、answer status 与 blocker；不含 use/query/segment/Attempt identity | pass |
| Idempotency/race | same command/payload exact replay；different payload fail closed；concurrent command 仅一个 audit/result/receipt | pass |
| Ownership/SideEffect | stale owner 与 takeover fence；`in_flight/unknown` 阻止 audit/child；failure commit 也重新校验 fence | pass |
| Crash/failure | 10 个 publication fault point及 context-stop receipt fault 全量 rollback；internal error 独立 fenced durable failure；SimulatedCrash 不误分类 | pass |
| Product API | `POST /outer/advance`、`GET /outer`；typed/bounded candidate；伪造 evaluator policy 与 accept-context overflow API 对抗；provider mode 未授权 fail closed | pass_after_round_1_rework |
| Provider | logical/transport calls 0；candidate provider path 未启用 | not_exercised |
| Live migration | schema 9 仅临时 DB；live DB 仍为 schema 7 | not_exercised |
| Stage 4/5 | HITL/interrupt/branch/replay UI、最终 UI/Eval 未实施 | correctly_out_of_scope |

## 6. 定向与回归证据

Stage 3 suite：

```text
36 passed
```

覆盖：

- schema 8 → 9 临时 migration、backup、idempotence、integrity、FK 与新 enum；
- accepted gate、terminal Task、immutable result linkage；
- candidate/confidence 无 authority，natural language needs-user；
- direct service 与 public API 均证明伪造 policy 在 current evidence +
  `valid_partial` artifact 下不能使虚假自然语言约束通过；合法 server registry
  exact binding 仍可通过；
- accept path context overflow 在 gate 前形成 durable budget stop；覆盖 service、
  API、replay、takeover/stale owner 与 receipt fault rollback/restart；
- schema-valid 但 canonical 总量超限的 candidate 在 service/API boundary
  fail closed，且无任何 Stage 3 状态或 receipt 漂移；
- atomic parent Result/child retry/Trace/Seed 与 child EvidenceUse isolation；
- replay、payload mismatch、same-command concurrency；
- 10 个 audit/observation/checkpoint/result/child/seed/Event/receipt fault point；
- stale owner、takeover、unresolved SideEffect；
- source drift append-only invalid observation；
- runtime/evidence/context hard budget；
- repeated target/no semantic progress 与跨 child aggregate ledger；
- optional unknown constraint；
- internal evaluator failure durable classification/replay；
- SimulatedCrash exclusion 与 failure-commit stale-owner race；
- minimal service/API 与 unauthorized provider。

Stage 1/2/3、V4 Fast/Deep ask、Evidence/Citation 与 retrieval 联合定向：

```text
180 passed
```

最终默认无 Provider 回归：

```text
1608 passed, 4 deselected, 7 warnings in 38.58s
```

默认 marker 排除 `external_artifact` 和 `live_provider`。warnings 为 1 类既有
Starlette/httpx TestClient deprecation 与 6 条既有 multiprocessing `fork()`
deprecation；无新增 warning 类。`compileall` 与 `git diff --check` 通过。

## 7. Live DB 稳定窗口

只读目标：
`/Users/elliot/Library/Application Support/Shiliu/shiliu.db`

使用文件指纹和 SQLite immutable URI；未调用 `Application` 或
`Database.initialize()`：

| 字段 | 完整回归前 | 完整回归后 |
| --- | --- | --- |
| SHA-256 | `ff8bc543d116e1d354d446686bcc56adaf4513941163ddce2ee645ad4d1c3eaa` | 相同 |
| size | 94,588,928 | 相同 |
| mtime | `2026-07-31T05:29:51+0800` | 相同 |
| schema | 7 | 7 |
| videos/completed | 157 / 140 | 相同 |
| integrity | ok | ok |

本轮第一次全回归后的只读复核恰逢既有外部
`shiliu sync --scheduled` 进程（PID 11856，run 322）运行；该进程从
2026-07-31 05:27:15+08:00 运行至 05:29:51+08:00，并将文件指纹从
`a6e2d883...` 改为 `ff8bc543...`，schema/size/videos/completed 均未变。
V5-A 未启动、终止或干预该进程。待它完成后，以 `ff8bc543...` 为前置基线
重新执行上述 1608 项完整回归，回归后 SHA/size/mtime 完全一致。本稳定窗口
证明测试未执行 live schema 9 migration 或写该 DB。

## 8. Provider、凭据与禁止范围

```yaml
stage_3_provider_logical_calls: 0
stage_3_provider_transport_attempts: 0
credential_values_read: false
keychain_accessed: false
paid_services_invoked: false
live_schema_9_migration_performed: false
v4_prompt_modified: false
model_choice_modified: false
tool_contract_modified: false
formal_ui_modified: false
stage_4_started: false
new_upstream_dependency_added: false
push_merge_tag_performed: false
```

## 9. 未证明项与残余风险

- 任意 natural-language objective/constraint 的语义满足：`unproven`；无注册
  evaluator 时产品诚实进入 needs-user。
- 真实 Provider audit/target generation 的正确性、response schema、成本、延迟、
  稳定性和 SideEffect recovery：`not_exercised`。
- live DB schema 9 upgrade/rollback：`not_exercised`；只有临时 migration 通过。
- 真实断电/SIGKILL、多主机长期 lease soak、production-scale retention/
  performance：`unproven`。
- 完整 HITL/input/interrupt/cancel 与 branch/replay 控制面：未实施，属于 Stage 4。
- held-out product-quality eval、正式 trace UI 与最终体验：未实施，属于 Stage 5。
- deterministic fixture 证明机制安全与准确分类，不外推真实研究答案质量。

## 10. 请求主 Session 决定

请 V5 主 Session 基于 Contract、初始实现提交 `788d01c`、本 bounded rework
提交、36 项 Stage 3 定向测试、180 项联合定向、1608 项默认无 Provider回归与
live DB 稳定窗口，作出：

```text
accept / partial_accept / rework / pause / reject
```

```yaml
stage_3_status: resubmitted_for_main_acceptance
stage_3_self_accepted: false
provider_runs_performed: false
live_database_migration_performed: false
stage_4_started: false
next_action: V5_main_session_stage_3_rework_review
```
