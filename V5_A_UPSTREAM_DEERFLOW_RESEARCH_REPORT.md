# V5-A 有界上游研究报告：DeerFlow

```yaml
report_status: draft_pending_main_review
research_scope: bounded_official_source_and_failure_test_review
registry_id: deer_flow
official_repository: https://github.com/bytedance/deer-flow
fixed_commit: 0d8e11ad492bfa1a15b4409cc744ee66d6d188c0
commit_time: 2026-07-30T15:54:15+08:00
commit_subject: "fix(frontend): persist artifact panel state (#4580)"
license: MIT
source_reviewed: true
tests_reviewed: true
tests_executed: false
provider_runs_performed: false
adoption_status: proposal_pending_main_review
adoption_type_proposed: pattern_only_reimplementation
implementation_authorized: false
```

## 1. Shiliu Problem

拾流 V5-A 需要证明以下问题，而不是寻找一个可直接替换产品的 agent framework：

- 目标、阻塞原因与 continuation 是否有显式、持久语义。
- continuation 前是否存在完整、可寻址的 durable receipt。
- no-progress 是否会诚实停止。
- checkpoint lineage 是否能拒绝 cycle、missing parent 和错误分支。
- 慢 worker、用户输入、goal edit、cancel 是否有 mutation guard。
- restart、owner 丢失和未知 in-flight 是否安全。
- branch/replay 是否保留 lineage，且不会污染 sibling。

本研究只检查与这些问题直接相关的官方源码和测试。

## 2. Local-first 与官方身份

### Local-first

- 产品仓库与既有研究目录中未发现 DeerFlow checkout、vendored source 或正式依赖。
- 因本轮需要达到 source/tests reviewed，随后从官方仓库获取稀疏、无产品写入的临时 checkout。
- 临时 checkout 位于 `/private/tmp/shiliu-v5a-deer-flow-sparse-20260730`，不属于产品树，不会随本提交进入仓库。

### Fixed official source

- Remote：`https://github.com/bytedance/deer-flow.git`
- Branch：`main`
- Commit：`0d8e11ad492bfa1a15b4409cc744ee66d6d188c0`
- Commit author：`qin-chenghan`
- Commit subject：`fix(frontend): persist artifact panel state (#4580)`

后续若上游 main 漂移，本报告仍只对上述 SHA 有效。

### License

固定提交根目录 `LICENSE` 是 MIT License：

- Copyright 2025 Bytedance Ltd. and/or its affiliates
- Copyright 2025–2026 DeerFlow Authors

License 核验不等于 Adoption。没有复制源码、模型、Prompt 或测试进入拾流，也没有添加 DeerFlow 依赖。

## 3. Inspected Upstream Evidence

### Goal / blocker / continuation

| 文件 | 已核验主题 |
| --- | --- |
| `backend/packages/harness/deerflow/agents/goal_state.py` | GoalState、状态、continuation/no-progress 计数、typed blocker |
| `backend/packages/harness/deerflow/runtime/goal.py` | goal evaluator、continuation gate、durable receipt、write conflict、visible conversation |
| `backend/packages/harness/deerflow/runtime/runs/worker.py` | worker 终态、goal evaluation、continuation、rollback/resume 交互 |

### Checkpoint / mutation / persistence

| 文件 | 已核验主题 |
| --- | --- |
| `backend/app/gateway/checkpoint_lineage.py` | parent traversal、cycle/addressability/depth、legacy fallback |
| `backend/packages/harness/deerflow/runtime/checkpoint_mode.py` | full/delta mode 与 fail-closed mismatch |
| `backend/packages/harness/deerflow/runtime/checkpoint_state.py` | checkpoint-aware state accessor 与写入 gate |
| `backend/packages/harness/deerflow/runtime/checkpointer/provider.py` | memory/SQLite/Postgres provider selection |
| `backend/packages/harness/deerflow/runtime/checkpointer/async_provider.py` | async provider behavior |
| `backend/packages/harness/deerflow/runtime/runs/manager.py` | run ownership、lease、cancel、orphan recovery |
| `backend/packages/harness/deerflow/runtime/runs/schemas.py` | run status/request contract |
| `backend/packages/harness/deerflow/runtime/runs/store/*` | durable/memory run store boundary |
| `backend/packages/harness/deerflow/persistence/run/model.py` | persisted run record |
| `backend/packages/harness/deerflow/persistence/run/sql.py` | CAS、owner、cancel 与 active-run persistence |
| `backend/packages/harness/deerflow/persistence/migrations/versions/0004_run_ownership.py` | ownership fields |
| `backend/packages/harness/deerflow/persistence/migrations/versions/0005_run_stop_reason.py` | stop reason |
| `backend/packages/harness/deerflow/persistence/migrations/versions/0010_run_cancel_request.py` | durable cancel request |

### User input / interrupt / branch / replay

| 文件 | 已核验主题 |
| --- | --- |
| `backend/packages/harness/deerflow/agents/human_input.py` | structured user input metadata |
| `backend/app/gateway/run_models.py` | run request、Command、checkpoint、interrupt controls |
| `backend/app/gateway/routers/runs.py` | run lifecycle/cancel endpoints |
| `backend/app/gateway/routers/thread_runs.py` | thread run、resume/regenerate/edit 路径 |
| `backend/packages/harness/deerflow/agents/middlewares/loop_detection_middleware.py` | repeated-call/no-progress-like cap 与 stop reason |

### 定向失败测试

以下测试文件已阅读相关 case 与断言：

- `backend/tests/test_goal_runtime.py`
- `backend/tests/test_goal_worker.py`
- `backend/tests/test_checkpoint_lineage.py`
- `backend/tests/test_checkpoint_mode.py`
- `backend/tests/test_checkpoint_state.py`
- `backend/tests/test_cancel_run_idempotent.py`
- `backend/tests/test_gateway_run_recovery.py`
- `backend/tests/test_interrupt_serialization.py`
- `backend/tests/test_assistant_payload_replay.py`
- `backend/tests/test_branch_history_seed.py`
- `backend/tests/test_replay_golden.py`
- `backend/tests/test_replay_provider.py`
- `backend/tests/test_loop_detection_config.py`
- `backend/tests/test_loop_detection_middleware.py`
- `backend/tests/test_loop_detection_stop_reason.py`
- `frontend/tests/e2e/branch-thread.spec.ts`

这里的 `tests_reviewed: true` 仅表示阅读了固定提交中的测试代码和失败断言。未安装 DeerFlow 依赖，未执行其测试，因此不能报告为 `tests_passed`。

## 4. Verified Behavior

### 4.1 Goal 与 blocker

`GoalState` 维护 objective、active/terminal status、时间、continuation count、no-progress count 和最后一次评价。检查到的 blocker 类别包括：

- `none`
- `missing_evidence`
- `needs_user_input`
- `run_failed`
- `external_wait`
- `goal_not_met_yet`

其中只有 `goal_not_met_yet` 被视为可自动 continuation。最大 continuation 为 8，最大 no-progress 为 2。

这证明 DeerFlow 有 typed blocker 和有界续作，而不是无条件递归。

### 4.2 Goal evaluator 的权威边界

- evaluator 在主 run 后由额外 non-thinking model 执行。
- 输入来自用户可见的 human/AI conversation，不包含完整工具/内部状态。
- 输出 JSON：是否满足、blocker、reason、evidence summary。
- 没有可见 assistant completion 时 fail closed。
- evaluator 异常时记录日志并不 continuation。

对拾流而言，这仍是 model-derived audit，不是 transcript citation verifier。它可以启发 outer audit 的结构，但不能获得最终完成门权威。

### 4.3 Durable receipt 与 continuation

continuation 前检查：

- 可寻址 checkpoint ID；
- 没有 pending writes；
- 存在 terminal visible AI response。

缺少 durable receipt 会转为 `run_failed`/停止，不继续生成。

goal write 使用 per-thread lock 与 expected checkpoint；提交前后重新读取 goal 与 conversation。若用户消息、goal clear 或新 checkpoint 已发生，旧 evaluation 不能覆盖新状态。这是可迁移的重要 mutation-guard 模式。

### 4.4 No-progress

DeerFlow 将 blocker 与最新可见 assistant 文本的 SHA-256 组合为 no-progress fingerprint。相同 fingerprint 连续出现达到阈值后停止。

优点：

- 比只比较 evaluator 自由文本稳定。
- 有显式阈值，不会无限 continuation。

限制：

- 可见答案文字变化可能掩盖“证据没有变化”。
- 文字相同也不等于所有约束进展相同。
- 没有稳定 transcript evidence delta 或 constraint-level progress record。

因此不能原样成为拾流 no-progress 定义。

### 4.5 Checkpoint lineage

parent traversal 会检查：

- cycle
- missing/unaddressable parent
- depth bound
- pending task checkpoint
- duration-only checkpoint

旧数据存在按时间顺序回退的 legacy 路径；源码注释也承认 sibling 情况下不安全。拾流新内核不应继承这种 permissive fallback：没有明确 parent 就 fail closed。

### 4.6 Checkpoint mode / mutation guard

- full/delta mode 是冻结配置。
- 运行态与 checkpoint mode 不匹配时 fail closed。
- state accessor 对读取和写入施加 checkpoint-aware gate。

这是“checkpoint mode mutation guard”，不是通用 external SideEffectRecord。它不能解决 Provider 调用在返回后、结果提交前崩溃的歧义。

### 4.7 Run ownership / recovery / cancel

持久 run 记录有：

- `pending`、`running`、`success`、`error`、`timeout`、`interrupted`
- owner/lease
- active-run 唯一约束
- durable cancel request
- start/claim CAS
- stale owner fence

启动和周期恢复会把 orphaned run 标为 error，不会静默从不明位置继续。cancel 可重复调用且幂等，跨 worker 通过持久请求协调。

这类 owner/fence/cancel 模式值得独立重实现，但 RunStatus 缺少拾流要求的 `partial` / `insufficient`。

### 4.8 User input / interrupt

- structured human input metadata 被校验。
- `__interrupt__` 序列化被测试。
- request 支持 interrupt-before/after、Command、checkpoint ID 与 multitask strategy。
- `stream_resumable=True` 明确不支持。

它证明 interrupt metadata 与 checkpoint 可以协作，但不证明一个完整的产品级 WaitingUser 生命周期。

### 4.9 Branch / replay

- regenerate/edit 受“最新消息”、source run 成功和 metadata 稳定性约束。
- active goal 会阻止不安全 edit。
- delta checkpoint 对旧 checkpoint 的继续会线性化到当前 head，避免 sibling 写入污染。
- rollback materializes snapshot，失败时 fail closed。
- workspace side effect 有 snapshot 机制，但没有拾流所需的通用 SideEffectRecord/unknown-in-flight 语义。
- frontend branch E2E 使用 mocked flow，不能替代 backend + persistence + Provider 集成证据。

### 4.10 Loop cap 与结果分类

loop middleware 对重复 tool call hash 设置 warning/hard threshold，并按单工具频次设 cap。hard stop 会剥离继续调用并输出 `stop_reason=loop_capped`。

但 run 仍可能记录为 `success`。这与拾流治理冲突：cap/无充分证据必须能成为 `partial` 或 `insufficient`，不能只靠 stop reason 修饰 success。

## 5. Shiliu Delta

### 可独立重实现的模式

1. Typed Blocker 与明确 continuable subset。
2. continuation 前检查 durable receipt。
3. 评价/慢 worker 提交前重读 current goal/checkpoint，并用 expected version 拒绝旧写入。
4. parent checkpoint traversal、cycle/missing-parent 检查。
5. checkpoint mode 不匹配 fail closed。
6. durable、幂等 cancel。
7. owner lease、stale-owner fence 与 orphan recovery。
8. 对 user message、goal clear、cancel race 的定向失败测试。

### 必须补齐

- 独立 ResearchTask/Goal revision/Attempt/Event/Trace/Result/SideEffectRecord。
- transcript evidence 与 constraint-level progress delta。
- `partial` / `insufficient` 与 failure taxonomy。
- external reservation/receipt/unknown 状态。
- 配置无关的 durability guarantee。
- branch/replay 的稳定产品 lineage，而非 chat-only 历史。

### 明确拒绝

- 直接依赖或复制 DeerFlow。
- 把 chat thread/run/checkpoint 等同拾流 Task/Attempt/Checkpoint。
- 默认 memory checkpointer。
- 用 visible assistant text hash 作为唯一 progress 事实。
- 用 model evaluator 作为完成 verifier。
- cap 后仍把结果算作成功。
- 新系统对 missing parent 使用 chronological legacy fallback。
- 把 workspace snapshot 当作通用 SideEffectRecord。

## 6. Adoption Decision Proposal

```yaml
upstream_id: deer_flow
decision_status: proposed_pending_main_review
proposed_decision: pattern_only_reimplementation
direct_dependency: false
source_copy: false
prompt_copy: false
test_copy: false
implementation_authorized: false
candidate_patterns:
  - typed_blocker_and_continuation_gate
  - durable_completion_receipt_before_continuation
  - reread_plus_expected_checkpoint_mutation_guard
  - strict_parent_checkpoint_lineage
  - fail_closed_checkpoint_mode
  - durable_idempotent_cancel
  - owner_lease_stale_writer_and_orphan_fencing
required_shiliu_overrides:
  - stable_transcript_evidence_authority
  - separate_task_goal_attempt_event_trace_result_side_effect_identity
  - semantic_progress_delta
  - explicit_partial_and_insufficient
  - unknown_external_in_flight_fail_closed
```

理由：适合吸收的是协议和失败测试思想，不是框架整体。正式 Adoption 决定必须由 V5 主 Session 写入 Program Decision Ledger。

## 7. Registry Update Proposal（未直接修改）

建议 V5 主 Session 复核并更新 `03_拾流V5上游项目与研究资料注册表.yaml` 中 `deer_flow` 条目：

```yaml
source_last_checked: 2026-07-30
official_repository: https://github.com/bytedance/deer-flow
pinned_commit: 0d8e11ad492bfa1a15b4409cc744ee66d6d188c0
license: MIT
review_evidence:
  source_reviewed: true
  related_failure_tests_reviewed: true
  tests_executed: false
  provider_run: false
research_scope:
  - goal
  - blocker
  - continuation
  - no_progress
  - checkpoint_lineage
  - mutation_guard
  - user_input_interrupt
  - branch_replay
  - run_ownership_recovery
adoption_status: candidate_pending_main_decision
adoption_proposal: pattern_only_reimplementation
implementation_authorized: false
```

字段枚举应由主 Session 按 Program Registry schema 归一化。

## 8. Research Log Update Proposal（未直接修改）

建议主 Session 追加一条类似事件：

```json
{"timestamp":"2026-07-30","session":"Shiliu V5-A Version Session","upstream_id":"deer_flow","event_type":"bounded_official_source_and_tests_review","official_repository":"https://github.com/bytedance/deer-flow","commit":"0d8e11ad492bfa1a15b4409cc744ee66d6d188c0","license":"MIT","scope":["goal","blocker","continuation","no_progress","checkpoint_lineage","mutation_guard","user_input_interrupt","branch_replay","ownership_recovery","related_failure_tests"],"tests_executed":false,"provider_runs":false,"outcome":"pattern_only_reimplementation_proposed_pending_main_review","implementation_authorized":false}
```

## 9. Tests / Evidence Classification

| 证据项 | 分类 |
| --- | --- |
| 官方仓库与固定 SHA | verified |
| MIT License | verified |
| 相关源码行为 | source_reviewed |
| 相关失败测试及断言 | tests_reviewed |
| DeerFlow 测试实际运行 | not_exercised |
| 拾流集成 | not_exercised |
| Provider 行为 | not_exercised |
| 性能、跨进程生产可靠性 | unproven_for_shiliu |

## 10. 限制与未证明项

- 稀疏研究没有审阅 DeerFlow 全仓库或全部测试。
- 没有安装上游依赖，也没有执行 upstream unit/E2E suite。
- 没有验证 SQLite/Postgres checkpointer 的生产部署行为。
- 没有运行 Provider，因此不评价 evaluator/model 质量。
- frontend mocked branch E2E 不能证明真实 persistence/Provider 集成。
- 上游模式能否在拾流 schema 与证据不变量下工作，须在被接受的 Stage Contract 中独立实现和测试。

```yaml
research_report_status: draft_pending_main_review
adoption_decision_status: proposal_pending_main_review
implementation_authorized: false
provider_runs_performed: false
```
