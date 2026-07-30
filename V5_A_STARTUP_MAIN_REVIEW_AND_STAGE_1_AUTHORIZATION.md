# Shiliu V5-A Startup Main Session Review and Stage 1 Authorization

```yaml
reviewed_by: Shiliu V5 Main Codex Session
reviewed_at: 2026-07-31T01:08:24+08:00
execution_branch: codex/v5-a
startup_commit: 2feccbccaa288f67071d22460eb220d50b19d871
first_reconnaissance_commit: f6a2d7ee0d3a96a750886e879f89d4d419916810
final_reviewed_commit: 0fd038effc321a0b2ec964c9628ba379924c4643
decision: accept
version_charter_status: accepted
stage_1_contract_status: authorized
stage_1_implementation_authorized: true
product_implementation_started: false
provider_runs_authorized: false
provider_runs_performed: false
live_database_migration_authorized: false
```

---

## 1. Review Scope and Evidence

主 Session 独立检查了：

- `2feccbc..0fd038e` 的提交与文件范围；
- Version Charter、Current State、V5-A Decision Ledger 与 Stage 1 Contract；
- DeerFlow 与 AREX 两份有界研究报告；
- V4 Evidence/Citation、共享 finalization、Deep state、DecisionView、进程内 trace 与无 checkpointer graph 的源码事实；
- V4.1 Harness 的 checkpoint、WAL-before-provider、dedupe、unknown in-flight fail-closed 与故障测试；
- live SQLite、索引与 corpus 的只读现场状态；
- 固定上游身份、License、源码/测试存在性及未执行边界。

执行分支只新增或修改六份 V5-A 研究/治理文档，没有修改产品源码、测试、Migration、Prompt、Tool Contract、UI 或配置。最终工作树干净，未 Push、Merge 或 Tag。

主 Session 独立重跑报告对应的 122 项无 Provider 定向测试：

```text
122 passed
0 failed
1 existing Starlette/httpx deprecation warning
```

---

## 2. Accepted Baseline

2026-07-31 的主 Session 只读复核接受以下现场基线：

```yaml
database:
  schema_version: 6
  videos: 157
  completed: 140
  research_task_like_tables: 0
corpus:
  BV_artifact_directories: 155
  distinct_nonempty_artifact_dir: 155
lexical:
  eligible_videos: 154
  video_units: 154
  chunks: 1479
dense:
  units: 1633
  vectors: 1633
```

Program 文件中的 150 个内容目录属于文档漂移；155 已成为当前接受的 live baseline。这不是 V5-A 产品改动，也不证明 corpus 是冻结 Eval snapshot。

---

## 3. Version Charter Decision

接受 V5-A Version Charter 及其五阶段依赖序列：

1. Durable Task Kernel and Safety Envelope
2. Evidence-backed Inner Research Loop
3. Outer Goal Audit and Recursive Continuation
4. HITL and Operational Control
5. Product Completion, Trace, and Reliability Evaluation

该接受冻结版本使命、用户可见目标、阶段依赖、不变量、非目标和验收边界；不冻结具体表名、文件结构、内部框架、Commit 数量或未来 Stage Contract 的实现细节。

Stage 2/3 的 Provider 接线与验证范围由各自 Contract 决定。任何真实 Provider 运行仍需单独授权，Charter 接受本身不授权 Provider。

---

## 4. Upstream Adoption Decisions

### 4.1 DeerFlow

```yaml
adoption_status: adopted
adoption_type: pattern_only_reimplementation
usage_level: design_reference
recommended_modes:
  - reimplement_pattern
  - test_reference
direct_dependency: false
source_copy: false
prompt_copy: false
upstream_tests_executed: false
```

接受为设计与失败测试参考的范围：

- typed blocker / continuable subset；
- continuation 前 durable receipt；
- expected-version/checkpoint mutation guard；
- strict checkpoint lineage；
- durable idempotent cancel；
- owner lease、epoch fence 与 orphan/stale-owner failure cases。

Stage 1 只授权与当前 Contract 对应的拾流原生独立实现，不授权 DeerFlow 依赖、源码复制、Prompt 复制或整体框架接入。

### 4.2 AREX

```yaml
adoption_status: adopted
adoption_type: training_independent_patterns_only
usage_level: design_reference
model_adoption: false
weights_adoption: false
prompt_copy: false
code_copy: false
confidence_gate_adoption: false
stage_1_implementation_authorized: false
```

接受 Inner Research、Outer Constraint Audit、Targeted Follow-up 与 Compact Improvement State 作为后续 Stage 的设计参考。Stage 1 不实现 AREX 模式；未来采用仍须保持确定性 Evidence/Citation gate、显式 `valid_partial` / `valid_insufficient`、有界预算和 durable lineage。

---

## 5. Required Corrections and Resolution

第一轮主审要求的修订均已完成：

- Task、Attempt 与 Result 生命周期已分离；
- terminal Task 不可复活，终态后的 retry/revision 创建 `parent_task_id` child Task；
- `answer_status`、`termination_reason` 与 `failure_class` 已正交化；
- single-active-owner lease/epoch fence 已成为 Stage 1 必选项；
- CommandReceipt/DeduplicationRecord 已具有持久、事务化语义；
- SideEffect 唯一键已限定为 `(task_id, effect_kind, idempotency_key)`；
- unknown in-flight 只有在旧 owner 被 fence 后才可进入 blocked/unknown；
- 对应 crash、race、stale owner、payload mismatch、child Task 与跨 Task idempotency 测试要求已补齐；
- Registry `adoption_status`、`usage_level` 与 Program failure taxonomy 已归一化。

没有剩余的材料性 Contract 歧义。

---

## 6. Stage 1 Authorization

接受 `V5_A_STAGE_1_CONTRACT.md`，并授权 V5-A 子版本 Session 开始 Stage 1 产品实施。

允许：

- 新增 Research Task kernel 产品模块；
- 新增 SQLite schema/migration 源码；
- 只对临时数据库运行 migration tests；
- 实现无 Provider deterministic adapter；
- 实现最小 task create/get/command/status/trace API；
- 实现 Task/Goal/Attempt/Checkpoint/Event/Trace/Result/CommandReceipt/SideEffectRecord；
- 实现 transaction、idempotency、mutation guard、owner lease/epoch fence 与 lineage；
- 添加 Contract 要求的机械、故障注入和现有 `/search`、`/ask`、Evidence/Citation 回归测试。

继续禁止：

- 对 live DB 执行 Migration；
- 运行 Provider、付费服务或读取凭据；
- 新研究 Prompt、model choice 或 Tool Contract；
- Evidence-backed inner loop、outer audit 或 recursive Provider continuation；
- 正式 HITL UI、完整 branch/replay 控制面或最终研究 UI；
- 复制 DeerFlow/AREX 代码、Prompt、模型或新增其依赖；
- Push、Merge、Tag 或自行宣布 Stage 1 接受。

本授权只允许实施，不构成 Stage 1 完成或验收。

---

## 7. Required Stage 1 Handoff

V5-A 完成实施后必须提交：

- Stage 1 Implementation Report；
- 实际 Commit、完整 Diff 与 Working Tree 状态；
- Contract 逐条满足矩阵；
- migration、restart、crash、race、idempotency、ownership、lineage 与 regression 测试证据；
- live DB 未变、Provider 未运行、凭据未访问的证据；
- `not_exercised` 与 `unproven` 项；
- 请求主 Session 作出 `accept / partial_accept / rework / pause / reject`。

V5-A 不得自我接受 Stage 1。

---

## 8. Final Decision

```yaml
startup_review:
  status: accepted
  reconnaissance_evidence_accepted: true
  live_baseline_155_accepted: true
  version_charter_accepted: true
  deerflow_pattern_reference_adopted: true
  arex_training_independent_reference_adopted: true
stage_1:
  contract_status: authorized
  implementation_authorized: true
  implementation_started: false
  provider_runs_authorized: false
  live_database_migration_authorized: false
program:
  active_subversion: V5_A
  active_formal_stage: V5_A_STAGE_1
  next_action: V5_A_session_implements_stage_1_under_accepted_contract
```
