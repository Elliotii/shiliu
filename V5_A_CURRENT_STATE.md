# 拾流 V5-A Current State

```yaml
as_of: 2026-08-03
version_session: Shiliu V5-A Version Session
state_authority: V5-A execution-session observation
formal_acceptance_authority: V5 main session
branch: codex/v5-a
startup_head: 2feccbccaa288f67071d22460eb220d50b19d871
first_recon_commit: f6a2d7ee0d3a96a750886e879f89d4d419916810
product_baseline_commit: 483fd46bca1d7141a696fda4b2d1e093a55f209b
artifact_commit: 0fd038effc321a0b2ec964c9628ba379924c4643
main_acceptance_record: V5_A_STARTUP_MAIN_REVIEW_AND_STAGE_1_AUTHORIZATION.md
accepted_implementation_base: a8dae62a9796d8d9d70afb883ab5f2c1a707403f
stage_1_implementation_commit: c8a3f9f054b6793dade3e353fbf61fd8a583ec06
stage_1_main_acceptance_round_1: rework
stage_1_rework_round_1_commit: ecbea72b483487a4a64d46d286719e89d024e22f
stage_1_final_submission_head: cbfc7d1c571a2e2935df33c07cec94dd5f87ac78
stage_1_acceptance_record: V5_A_STAGE_1_MAIN_SESSION_ACCEPTANCE_DECISION.md
stage_1_accepted_at: 2026-07-31T02:21:31+08:00
stage_1_main_acceptance_decision: accept
stage_2_planning_baseline: fc4708eacb93e9b6b3d479d50e096cc95dd6be31
stage_2_contract: V5_A_STAGE_2_CONTRACT.md
stage_2_contract_status: accepted_by_v5_main
stage_2_accepted_contract_commit: 2037f39a9ec610d84ad4306a4f6c5fb693fdc3e7
stage_2_main_review_round_1: rework_evidence_record_semantics
stage_2_implementation_authorized: true
stage_2_implementation_commit: 022c0813f63bf5cad6419c81c817d9f9b85a72bf
stage_2_main_acceptance_round_1: rework
stage_2_rework_round_1_commit: 0ad5823724913874fd72afdbf2808d9f274f1c8e
stage_2_main_acceptance_round_2: rework_budget_accounting_and_evidence_cap
stage_2_user_acceptance: accept
stage_2_status: accepted_by_user_pending_main_record
stage_2_self_accepted: false
stage_3_contract: V5_A_STAGE_3_CONTRACT.md
stage_3_contract_status: accepted_by_user_for_implementation
stage_3_planning_baseline: fafcf48cf3c8703e9d665992da96c8b74de20fff
stage_3_implementation_authorized: true
stage_3_implementation_started: true
stage_3_implementation_completed: true
stage_3_implementation_commit: 788d01c
stage_3_main_acceptance_round_1: rework_evaluator_authority_and_context_budget
stage_3_rework_round_1_commit: 9b2725f6ebe3db25828c72174f34bd1b91388368
stage_3_user_acceptance: complete_pass
stage_3_main_acceptance: accept
stage_3_main_integration_commit: 9b2725f6ebe3db25828c72174f34bd1b91388368
stage_3_status: accepted_and_integrated_by_v5_main
stage_3_self_accepted: false
stage_4_contract: V5_A_STAGE_4_CONTRACT.md
stage_4_contract_status: accepted_with_bounded_preimplementation_sync
stage_4_implementation_start_baseline: 9b2725f6ebe3db25828c72174f34bd1b91388368
stage_4_implementation_authorized_after_sync_commit: true
stage_4_implementation_authorized: true
stage_4_implementation_started: true
stage_4_implementation_completed: true
stage_4_docs_sync_commit: f0c8775
stage_4_implementation_commit: 8021c15
stage_4_main_acceptance_round_1: rework_bounded_control_lineage_and_input_lifecycle
stage_4_rework_round_1_commit: 1259993
stage_4_implementation_report: V5_A_STAGE_4_IMPLEMENTATION_REPORT.md
stage_4_main_acceptance_decision: accept
stage_4_accepted_head: 26d22cda779086681da69747fce4b97260988646
stage_4_status: accepted_by_v5_main
stage_4_self_accepted: false
stage_5_contract: V5_A_STAGE_5_CONTRACT.md
stage_5_contract_status: draft_pending_main_review
stage_5_implementation_authorized: false
stage_5_implementation_started: false
stage_5_mechanical_product_gate_authorized: false
stage_5_provider_quality_gate_authorized: false
stage_5_mainline_integration_authorized: false
stage_5_live_schema_10_migration_authorized: false
charter_status: accepted
stage_1_contract_status: fulfilled_and_accepted
stage_1_implementation_authorized: true
stage_1_status: accepted
stage_1_self_accepted: false
product_implementation_started: true
provider_runs_performed: false
stage_2_live_database_migration_performed: false
stage_3_live_database_migration_performed: false
stage_4_live_database_migration_performed: false
source_schema_version: 10
live_database_schema_observed: 9
live_database_schema_9_migrated_by: V5_main_session
external_live_database_change_observed: true
```

## 1. 本轮范围状态

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| 十份必读治理/交接材料 | completed | 已完整读取；Program 级文件未修改 |
| Git/Working Tree 现场 | completed | 启动时工作树干净，已在 `codex/v5-a`，HEAD 为 `2feccbc...`，无需切换 |
| DB/Index/Corpus/Provider 配置核验 | completed_read_only | 未执行 migration、未访问 secret 值、未访问 Keychain、未发 Provider 请求 |
| V4 产品源码审计 | completed_bounded | Deep、DecisionView、Evidence/Citation、Trace、DB 与路由已核验 |
| V4.1 Harness 审计 | completed_bounded | continuation 与 H0 checkpoint/failure tests 已核验 |
| DeerFlow 研究 | main_review_confirmed_reference_only | 固定提交、MIT 与证据边界通过；主 Session 接受为 pattern-only 设计/测试参考；未执行上游测试 |
| AREX 研究 | main_review_confirmed_reference_only | 论文 v2、官方最小推理仓库与证据边界通过；主 Session 接受为 training-independent patterns-only 设计参考 |
| youtu_agent | deferred | 未 Clone、未深研 |
| Stage 1 产品实现 | accepted | Durable Task kernel、schema 7 源码、deterministic adapter、最小 JSON API 与机械测试经一轮有界返工后已由主 Session 正式接受；未改 Prompt、Tool Contract 或 UI |
| Stage 2 产品实现 | accepted_by_user_pending_main_record | 用户已明确“正式接受完整 Stage 2”；本 Session 不代替 V5 主 Session 创建 Program 级验收记录 |
| Stage 3 产品实现 | accepted_and_integrated_by_v5_main | 主 Session 已正式接受并集成到 `codex/v5-main` / `9b2725f` |
| Stage 4 产品实现 | accepted_by_v5_main | 主 Session 已正式接受 `26d22cd`；Round 1 bounded rework 关闭 current resume lineage 与 Input expiry/cancel/schema lifecycle，主 Session 独立重跑 27 项通过；无需进一步返工 |
| Stage 5 Contract | draft_pending_main_review | 只读 JIT 审计后已起草 Product Completion、Trace、Reliability 合同；未开始产品实施，Provider quality 与 mainline/live migration 为独立 gate |

## 2. Git 与基线

- 工作目录：`/Users/elliot/.codex/worktrees/3324/Shiliu`
- 实际分支：`codex/v5-a`
- 启动 HEAD：`2feccbccaa288f67071d22460eb220d50b19d871`
- 启动时 `git status --short` 无输出。
- 提交关系：
  - `2feccbc`：V5-A startup reconnaissance authorization
  - `1db3c2c`：V5 program governance baseline
  - `483fd46`：正式产品 baseline
  - `768e11a`：V4.1 hardening
  - `cbf264b`：V4 product completion
- 本文件不会嵌入其自身提交 SHA；最终 handoff 报告给出实际研究提交。

## 2.1 V5 主 Session 第一轮独立审查

V5 主 Session 于 2026-07-31 确认：

- 五 Stage 依赖序列方向接受。
- live baseline 已独立只读复核并接受。
- 122 项无 Provider 定向测试独立重跑通过。
- DeerFlow 接受为 `pattern_only_reimplementation` 设计/测试参考。
- AREX 接受为 `training_independent_patterns_only` 设计参考；Stage 1 不实现其模式。
- 上述决定均不授予产品实现、Provider 运行或 live migration 权限。

主 Session 最终复核已接受修订后的 Charter、研究边界和 Stage 1 Contract，并授权按 Contract 开始 Stage 1 实施。V5-A 基于 `a8dae62` 完成 Stage 1 实施与自测，提交 `c8a3f9f`。主验收 Round 1 决定为 `rework`；两项 bounded 修复提交为 `ecbea72`。主 Session 独立复验 41 项 Stage 1 测试、1539 项默认无 Provider 回归和两条自定义对抗路径后，已正式接受 Stage 1。

## 3. Live DB / Index / Corpus

核验对象：

- DB：`/Users/elliot/Library/Application Support/Shiliu/shiliu.db`
- 只读核验方式：SQLite immutable URI；没有调用应用 initializer。
- 文件大小：94,588,928 bytes
- 核验时文件 mtime：2026-07-30 22:00:38（本地时区）

核验结果：

| 指标 | 现场值 |
| --- | ---: |
| schema version | 6 |
| SQLite schema table count（含 `sqlite_sequence`） | 31 |
| 产品/FTS table count（不含 `sqlite_sequence`） | 30 |
| videos | 157 |
| completed | 140 |
| needs_review | 1 |
| retry_wait | 2 |
| skipped_no_subtitle | 14 |
| retrieval_search_traces | 145 |
| retrieval_search_presentations | 115 |
| Research/Task/Attempt/Checkpoint-like tables | 0 |
| retrieval_units | 1633 |
| retrieval_dense_vectors | 1633 |

索引元数据：

| 层 | 物理名称 | 版本/模型 | 数量 |
| --- | --- | --- | --- |
| lexical | `shiliu_lexical` | `v3-stage1-lexical-v1` | 154 eligible videos / 154 video units / 1479 chunks |
| dense | `shiliu_dense` | `v3-dense-qwen3-0.6b-mrl512-v1`, `Qwen/Qwen3-Embedding-0.6B` | 1633 units/vectors |

语义说明：

- `src/shiliu/runtime_modes.py` 中产品 corpus identity 是 `shiliu-live-current`。
- `shiliu-live-current` 是运行逻辑身份；`shiliu_lexical` / `shiliu_dense` 是物理索引名称，不能混为一谈。
- 内容根目录有 155 个 `BV*` artifact 目录，数据库 `artifact_dir` 非空去重值也是 155。
- Program Current State 记录的 150 已发生漂移；V5 主 Session 已于 2026-07-31 独立复核并接受 155 baseline。V5-A 只同步版本文档，不修改 Program 文件。

## 4. Provider 配置边界

核验了 config 文件存在性、大小、hash 与字段名：

- 路径：`/Users/elliot/Library/Application Support/Shiliu/config.toml`
- 大小：712 bytes
- SHA-256：`8c3edb44f4e254b62c1c08892abb5462eed4e049f72e09c6dd3488b351447777`
- `[llm]` 字段包含 `base_url`、`model`、各角色模型、`formal_reasoning_effort`、`api_key_ref`。
- `[asr]` 字段包含 `base_url`、`model`、`api_key_ref`。

没有输出任何配置值，没有读取 credential/Keychain，没有调用 Provider 或付费服务。

## 5. V4 可继承资产

### Evidence/Citation/Finalization

- `TranscriptEvidenceSpan` 已绑定 source artifact/version、timeline 与有序 segment IDs。
- evidence reconstruction/revalidation 和 citation validation 可继续作为事实与引用基础。
- Fast/Deep 共用 finalization，能返回 `complete`、`partial`、`insufficient`。
- Query rewrite 保留原始 query 且有界。

### Deep inner-loop building blocks

- typed Deep state、纯 reducer、确定性 DecisionView 与显式 budget 可复用为内层构件。
- repetition guard、no-new-evidence 计数和显式 termination reason 可继承其“有界与可解释”原则。
- navigation 与 citation authority 分离的策略必须保留。

### DB 与测试工程

- schema versioning、migration helper、SQLite/WAL 测试习惯可复用。
- V4/V4.1 的失败注入和 deterministic fake 模式可作为 Stage 测试方法。

## 6. 不可继承假设

- `run_id` 不是 Durable Task / Goal / Attempt identity。
- AskService 进程内 `_traces` 不是持久 trace。
- 未配置 checkpointer 的一次性 LangGraph `invoke` 不是 resume。
- DecisionView 不是完整 Runtime state 或 checkpoint schema。
- “新增 segment ID”不能单独证明语义进展。
- 浏览器 `AbortController` 只表示客户端终止等待，不证明服务端 durable cancel。
- navigation snippet 不能成为 citation evidence。
- V4.1 Harness 的 JSON checkpoint、私有 review 流程、provider identity 和快照方式不能直接成为产品 schema/语义。
- Harness 的“安全跳过已完成项”和“未知 in-flight fail closed”可以继承为模式，但 Harness 本身不是产品 Runtime。

## 7. 上游研究状态

### DeerFlow

- 官方仓库：`https://github.com/bytedance/deer-flow.git`
- 固定提交：`0d8e11ad492bfa1a15b4409cc744ee66d6d188c0`
- License：MIT
- 相关 Goal、Blocker、Continuation、No-progress、Checkpoint Lineage、Mutation Guard、User Input/Interrupt、Branch/Replay、Run ownership/recovery 与失败测试已定向审阅。
- 上游测试未执行；没有安装依赖、复制源码或加入正式依赖。
- 主 Session 决定：接受为 `pattern_only_reimplementation` 的设计/测试参考；不采用依赖、源码或 Prompt；实现权限仍只能来自相应 Stage Contract。

### AREX

- 论文：arXiv `2607.21461v2`
- 官方模型/最小推理仓库：`https://huggingface.co/BAAI/AREX-Turbo`
- 固定提交：`129812742df4a5de27980ed07bda78d9d27c7370`
- 论文发布许可：arXiv perpetual non-exclusive license。
- 官方仓库代码/模型许可：Apache-2.0。
- 官方代码只提供最小单轮 action generation 与 prompts；没有完整 outer loop、工具执行器、训练管线、评估 Harness 或测试。
- 主 Session 决定：接受为 `training_independent_patterns_only` 的设计参考；不采用模型、权重、Prompt、代码或 confidence gate；Stage 1 不实现 AREX 模式。

### youtu_agent

- `deferred_no_clone_no_deep_research`。

## 8. 本轮无 Provider 验证

使用当前工作树 `src` 和既有共享 Python 3.12 环境执行两组定向机械测试：

1. V4 Ask contracts、Evidence/Citation、Fast/Deep、V4.1 continuation/H0：81 passed。
2. DB/schema/sync、Evidence contract/snapshot、产品 search API、V4 search execution：41 passed。

合计：122 passed，0 failed。

测试命令显式使用当前工作树的 `PYTHONPATH=src`。仓库默认 pytest 配置排除 `external_artifact` 与 `live_provider`，所选文件也未发起 Provider。唯一 warning 是既有 FastAPI TestClient 的 Starlette/httpx deprecation warning。

工作树本身没有 `.venv`；首次尝试在测试收集前因 `.venv/bin/python` 不存在退出，随后使用主仓库既有共享环境完成上述测试。没有联网安装依赖。

V5 主 Session 于 2026-07-31 独立重跑同一 122 项测试并确认全部通过；同样只有既有 Starlette/httpx warning。

## 8.1 Stage 1 实施验证

- Stage 1 kernel/API 定向 suite：41 passed。
- 默认无 Provider 全回归：1539 passed，4 deselected，7 warnings。
- 新增 schema 7 只在临时 SQLite migration tests 中执行；live DB 实施前后
  SHA-256、大小与 mtime 完全一致。
- Provider、付费服务、credential 和 Keychain 均未运行或访问。
- 详细矩阵与证据见 `V5_A_STAGE_1_IMPLEMENTATION_REPORT.md`。

## 8.2 Main Acceptance Rework Round 1

主 Session 在临时 SQLite 独立复现并要求修正：

1. 公共 `start_attempt` 的 cause/lineage 可绕过专用 resume/retry/revise/branch
   语义。
2. takeover 后旧 epoch `reserved` SideEffect 没有安全续作路径。

`ecbea72` 已完成：

- public command 与 service 双层 cause-specific guard；非法组合无
  Attempt/Trace/Receipt/Task state 漂移。
- takeover CAS 事务内只重绑定 `reserved` record，追加 rebound Event 并保留
  Task-scoped 唯一身份；旧 owner 仍被 fence。
- 旧 `in_flight` 不重绑定，仍按 unknown/blocked fail-closed 流程恢复。
- 增加 service/API 对抗、fault rollback、stale owner、hash mismatch、并发与
  replay 测试。

## 8.3 Stage 2 Contract 的 JIT 审计

- 定向读取了 Stage 1 acceptance/Contract/Report、Version Charter、Program
  Current State 和必要的 Stage/证据/Session 治理材料。
- 源码审计覆盖 Stage 1 research kernel/schema、V4 Evidence/Citation/shared
  finalization、retrieval execution/materialization、Deep typed action、
  DecisionView/reducer/budget 和 navigation/transcript boundaries。
- 复用边界、持久 Evidence/Artifact 语义、ownership/checkpoint/SideEffect
  交互、预算/停止条件和测试矩阵已冻结在 `V5_A_STAGE_2_CONTRACT.md` 草案。
- 主 Session 第一轮合同审阅总体方向通过，仅要求拆分全局 immutable evidence
  identity、Task/Attempt-scoped use/provenance 与 append-only currentness
  observation；限定修订已完成并等待复审。
- 无 Provider探索性机械测试：41 passed；覆盖 Evidence contracts、held-out
  evidence mechanics、shared Citation/Context 和 V4 Deep。唯一 warning 是既有
  Starlette/httpx deprecation warning。
- 未修改 Runtime、产品测试、Prompt、Tool Contract、UI 或 Program 权威文件；
  未下载新的上游源码/依赖。

## 8.4 Stage 2 实施与验证

- 产品实现提交：`022c0813f63bf5cad6419c81c817d9f9b85a72bf`。
- 新增 schema 8 源码与六类持久表：InnerAction、EvidenceIdentity、
  Attempt-scoped EvidenceUse、append-only Provenance/ValidationObservation
  和 immutable ProvisionalArtifact。
- `continue` 每次只提交一个 action；action、evidence、budget/progress、
  checkpoint、Event 与 CommandReceipt 在同一事务内发布。
- 当前字幕 raw source/version/timeline/ordered segments 是 citation authority；
  navigation 只做候选缩小。artifact 提交前重建并校验 evidence，提交后漂移通过
  显式 fenced revalidation command 追加 observation，不改写历史 identity/artifact。
- 版本化 checkpoint state 持久保存预算、semantic progress 与正交
  `answer_status / termination_reason / failure_class`；provisional answer 不终结
  Task 或 Attempt。
- Stage 2 定向 suite：29 passed；Stage 1 + Evidence/Citation + retrieval +
  Fast/Deep 联合定向回归：139 passed；最终默认无 Provider 回归：
  1568 passed、4 deselected、7 warnings。
- `diff --check` 与 `compileall` 通过。warning 仅为既有 Starlette/httpx
  deprecation，以及六条 multiprocessing `fork()` deprecation。
- Stage 2 migration 仅在临时数据库执行。最终稳定测试窗口内 live DB
  SHA-256/size/mtime 前后均为
  `248deb86dd9b32b8ff4bac52ebb3b7e00fdde0c311f421c073310418376d9f24` /
  94,588,928 bytes / `2026-07-31T03:25:48+0800`。
- 首次全量测试窗口恰逢用户环境中既有 `shiliu sync --scheduled` 独立进程启动；
  该外部进程把 live DB 从 schema 6 升至 Stage 1 schema 7 并创建
  `shiliu.pre-v7.backup.db`。V5-A 未启动、终止或干预该进程，也未对 live DB
  执行 Stage 2 schema 8 migration。该环境事件已保留为验收限制，不以第一次
  前后 hash 作为“不变”证据。
- Provider logical calls 与 transport attempts 为 0；未访问 credential/Keychain。
  详细矩阵见 `V5_A_STAGE_2_IMPLEMENTATION_REPORT.md`。

## 8.5 Stage 2 Main Acceptance Bounded Rework Round 1

V5 主 Session 第一轮正式验收决定为 `rework`，总体 Stage 2 方向通过，只要求
关闭两项持久停止缺口。`0ad5823` 已完成：

1. runtime、decision、window 等 pre-action hard budget exhaustion 统一走
   guarded durable-stop transaction；不执行被阻止的 tool/action，不创建伪 action，
   原子提交 stopped checkpoint、Event、CommandReceipt 与正交结果维度。
2. synthesis/context/validator 内部异常先使原 transaction 全量回滚，再以相同
   owner epoch、expected state/checkpoint 进入独立 failure transaction；提交唯一
   failed action、failure checkpoint、Event 与 receipt。

新增 public service/API 测试覆盖 runtime/decision/window、restart、takeover、
replay、payload mismatch、context/validator failure、stale-owner race 和
`SimulatedCrash` exclusion。Stage 2 29 项、联合定向 139 项及默认无 Provider
1568 项回归全部通过；最终稳定测试窗口 live DB 指纹仍为
`248deb86dd9b32b8ff4bac52ebb3b7e00fdde0c311f421c073310418376d9f24` /
94,588,928 bytes / `2026-07-31T03:25:48+0800`。

## 8.6 Stage 2 Main Acceptance Bounded Rework Round 2

V5 主 Session 已确认 Round 1 的两项原始修复通过，但继续发现两个同一预算
不变量缺口：成功 synthesis 的 context 消费未持久记账，以及 EvidenceUse 已达
上限后仍可调用 window tool。V5-A 保持已接受 Contract 不变，完成以下限定修复：

1. `synthesis_context_characters` 精确定义为最终 committed
   `ContextBuildResult.model_context` 的 Python 字符数。只有 synthesis、validator
   与 artifact transaction 成功时才在同一 checkpoint 单调扣账；Event 记录累计值。
   rollback、failure、replay、restart 和 takeover 不虚扣、不重置、不重复扣账；
   service 对注入 builder 的输出另行执行剩余额度上限。
2. durable EvidenceUse count 已达上限且当前 phase 将执行 transcript search/window
   时，在 action/tool 前进入既有 fenced durable-stop transaction；原子提交 stopped
   checkpoint、`inner_budget_exhausted` Event 与 CommandReceipt，分类为
   `termination_reason=budget_exhausted / failure_class=none`。

新增 public service/API 对抗覆盖 exact-once context accounting、server cap、
artifact fault rollback、evidence cap no-tool stop、restart、replay、payload
mismatch 与 takeover。Stage 2 suite 为 33 项，联合定向为 143 项，默认无
Provider 全回归为 1572 passed、4 deselected、7 warnings；`compileall` 与
`diff --check` 通过。稳定窗口 live DB 仍为 schema 7，SHA-256/size/mtime 保持：
`248deb86dd9b32b8ff4bac52ebb3b7e00fdde0c311f421c073310418376d9f24` /
94,588,928 bytes / `2026-07-31T03:25:48+0800`。

## 8.7 Stage 3 Contract 与 JIT 实施准备

当前分支 HEAD 为 Stage 2 Round 2 提交 `fafcf48`，工作树在规划开始时干净；
本地仓库在规划提交时尚无 V5 主 Session 的 Stage 2 正式接受记录，因此当时
`V5_A_STAGE_3_CONTRACT.md` 以 `draft_pending_main_review`、
`implementation_authorized=false` 提交。其后用户已直接接受完整 Stage 2 与
Stage 3 Contract，并授权本轮实施；当前状态见第 8.8 节。

JIT 源码审计确认：

- Stage 2 artifact、Attempt-scoped evidence/currentness 和 Stage 1 owner/receipt
  可直接作为 outer audit 输入与安全边界。
- 当前 Goal constraints 是 opaque strings；没有 constraint identity、逐项
  observation、OuterAudit、CompactImprovementState、ContinuationDecision 或
  outer aggregate budget。
- Stage 2 complete/stopped state 不得复活；targeted continuation 应由专用 audit
  transaction 原子终结父 Attempt，并创建 `cause=retry` 的 child Attempt。
  独立 ContinuationDecision/Seed 表达 `outer_targeted_followup`，避免扩张或滥用
  AttemptCause。
- child Attempt 保持原 Goal，但使用 bounded targeted execution objective；
  carried evidence identity 必须重新建立 child-scoped EvidenceUse/currentness。
- Candidate/model/confidence 没有 gate 权威。只有 registered deterministic
  evaluator（以及未来 Stage 4 明确 human decision）可以写 `satisfied`；无法判断
  的 natural-language constraint 保持 unknown。
- outer progress 按 constraint status、current evidence、conflict 与 audited
  answer status 计算；答案文字、query、segment ID 或新 Attempt 不单独算进展。

Contract 提议 schema/migration source、deterministic gate、atomic continuation、
minimal API 和 Provider wiring-only；真实 Provider、live migration、Prompt/
Tool Contract/UI、Stage 4/5 均继续未授权。当前无 Provider机械核验重跑 Stage 2
suite：33 passed，仅既有 Starlette/httpx warning；live DB 仍为 schema 7，
SHA-256/size/mtime 为
`248deb86dd9b32b8ff4bac52ebb3b7e00fdde0c311f421c073310418376d9f24` /
94,588,928 bytes / `2026-07-31T03:25:48+0800`。

## 8.8 Stage 3 实施与验证

用户已明确接受 `V5_A_STAGE_3_CONTRACT.md` 并授权实施。产品/测试提交
`788d01c` 完成：

- schema 9 migration source 与 ConstraintSpec、AuditCandidate、
  ConstraintAuditObservation、OuterAudit、CompactImprovementState、
  ContinuationDecision/Seed、Result linkage；
- registered deterministic evaluator gate，candidate/confidence 无权威，
  unsupported natural language 保持 unknown/needs-user；
- commit-time currentness guard 与 immutable EvidenceIdentity/Attempt-scoped
  EvidenceUse 边界；
- parent Result/terminalization + retry child/Trace/Seed + child-scoped carry
  use/currentness 的单事务 publication；
- outer aggregate budget、identity-based semantic progress、repeated target/
  no-progress、durable block/stop 与独立 fenced implementation-failure；
- 最小 outer advance/status API；未授权 provider mode fail closed。

验证结果：Stage 3 28 项、联合定向 155 项、默认无 Provider
`1600 passed, 4 deselected, 7 warnings`；`compileall` 与 `diff --check` 通过。
最终稳定窗口 live DB 保持 schema 7，SHA-256/size/mtime 为
`a6e2d883e9df563296d8fb147a17480374817e99d653d5ad4562e6ff0843c0e9` /
94,588,928 bytes / `2026-07-31T04:27:14+0800`。schema 9 只在 pytest 临时
SQLite 执行；Provider/凭据/Keychain/live migration 均未运行。

## 8.9 Stage 3 Main Acceptance Bounded Rework Round 1

V5 主 Session 已确认并不重开 Stage 3 的持久模型、candidate/observation 分离、
atomic continuation、child EvidenceUse isolation、fence、migration、最小 API 与
原 28 项定向测试。正式决定为 `rework`，仅要求关闭 evaluator authority 与
context/candidate budget 两项边界。

本轮限定修复完成：

1. `_constraint_snapshot()` 不再读取客户端可写的
   `evidence_policy.outer_audit` 来选择 evaluator。只有服务端注入 registry 中按
   constraint scope 与 normalized exact text 明确绑定的 evaluator 才具有
   `satisfied` 写权限；registration identity、policy/version 与参数进入 immutable
   ConstraintSpec。未注册 objective/constraint 固定为
   `natural_language + unknown/needs_user`。伪造 client policy 即使伴随 current
   EvidenceUse 和 `valid_partial` artifact，也不能提交 `valid_success`。
2. candidate 改为 strict typed/bounded schema，并增加 4,000 canonical
   serialized-character service cap；超限在 transaction 前 fail closed，不持久化
   payload 或 receipt。outer context 在 candidate/currentness/evaluator 执行前
   计算；投影超限时不执行 gate、不持久 candidate/currentness observation，原子
   提交 `budget_exhausted` audit/checkpoint/Event/receipt。该 guard 对 accept、
   targeted continuation、stop 与 block 全部一致，且保留 owner/checkpoint fence。

新增 direct service/public API 对抗测试覆盖虚假“月球由奶酪构成”约束、合法
server registration、accept-path context overflow、oversized candidate、replay、
payload mismatch、takeover/stale owner、receipt fault rollback 与 restart。
Stage 3 suite 为 36 项；Stage 1/2/3、Evidence/Citation、V4 Fast/Deep 与 retrieval
联合定向为 180 项；默认无 Provider 全回归为
`1608 passed, 4 deselected, 7 warnings`。最终稳定窗口 live DB 仍为 schema 7，
SHA-256/size/mtime 保持
`ff8bc543d116e1d354d446686bcc56adaf4513941163ddce2ee645ad4d1c3eaa` /
94,588,928 bytes / `2026-07-31T05:29:51+0800`。

此前一次回归后的只读核验与既有外部 `shiliu sync --scheduled`（PID 11856，
run 322，05:27:15–05:29:51+08:00）重叠，该外部进程把指纹从
`a6e2d883...` 改为 `ff8bc543...`，但未改变 schema/size/videos/completed。
V5-A 未启动、终止或干预它；待其结束后以新指纹为前置基线重新完成上述 1608
项全回归，回归后 SHA/size/mtime 不变。Provider、凭据/Keychain、live
migration 与 Stage 4 均未运行。

## 8.10 Stage 3 接受输入与 Stage 4 Contract 准备

用户确认 Stage 3 完整通过后，V5 主 Session 已正式接受并把 `codex/v5-main`
集成到 `9b2725f6ebe3db25828c72174f34bd1b91388368`。本文件只同步这一既有接受事实，
不另建重量级 Stage 3 接受报告，也不修改 Program 权威文件。

Stage 4 规划以干净分支 `codex/v5-a` / `9b2725f` 为代码基线。JIT 审计确认：

- 可继承 owner lease/epoch、state/checkpoint guard、CommandReceipt、SideEffect、
  retry/resume/cancel 和 source-checkpoint lineage 原语；
- `waiting_user` 尚无独立 InputRequest/HumanDecision，worker owner 与控制者权限
  也未分离；
- 当前 cancel 是同步 terminal helper，没有 cooperative interrupt 或
  cancel-pending/unknown-effect 协议；
- unknown SideEffect 解析缺少 immutable human resolution identity；
- branch/replay 只有低层 Attempt 验证，尚无不改写 source/sibling 的产品级派生
  Task 模型；
- 通用 resume 不能无类型地重写 Stage 2/3 checkpoint，恢复必须保持 domain
  checkpoint schema 与预算。

据此创建 `V5_A_STAGE_4_CONTRACT.md`，冻结最小 control plane：
immutable ControlRequest/InputRequest、append-only disposition/HumanDecision、
SideEffectResolution、TaskDerivation、control generation/fence、
interrupt/cancel、显式 retry 与隔离的 branch/replay。正式 UI、Provider、live
migration、Prompt/Tool Contract、通用调度与 Stage 5 Eval 继续禁止。

规划期只读 baseline 为 source schema 9、live schema 7、SHA-256
`ff8bc543d116e1d354d446686bcc56adaf4513941163ddce2ee645ad4d1c3eaa`、
94,588,928 bytes、mtime `2026-07-31T05:29:51+0800`、157/140 videos/completed、
integrity ok。Stage 1 控制原语与 Stage 3 gate 的 77 项无 Provider 定向测试通过，
仅既有 Starlette/httpx TestClient warning。没有执行 Provider、live migration
或产品 Runtime 改动。

V5 主 Session 随后有限接受 Stage 4 Contract，状态为
`accepted_with_bounded_preimplementation_sync`，并授权本次 docs-only 同步提交后
直接实施。implementation-start baseline 为 `codex/v5-main` / `9b2725f`。
主 Session 已把 live DB 从 schema 7 迁移到 schema 9；V5-A 没有执行该迁移。
2026-08-03 只读核验为 SHA-256
`2ff0eb91569a81b8a0e244db1238faffd6311236339707b2a9c7273cd317068f`、
94,588,928 bytes、mtime `2026-08-03T00:58:14+0800`、FK violations 0、
integrity ok、157/140 videos/completed。

Contract authority 边界同步明确：actor identity、role 与 control capability 只能由
服务端认证上下文/注册策略派生；payload 中自报 actor metadata 只用于不可信审计，
不得授予权限。Stage 4 验收矩阵相应加入伪造 actor/role/capability 的无状态漂移
对抗测试。

## 8.11 Stage 4 实施与提交

docs-only baseline 同步提交 `f0c8775` 后，按已接受 Contract 完成实施提交
`8021c15`。source schema 为 10，新增独立 `control_generation`、immutable
ControlRequest/InputRequest/HumanDecision/SideEffectResolution/TaskDerivation 与
append-only dispositions；控制操作原子 fence 旧 worker，interrupt/resume 保持
Attempt/checkpoint schema/预算，cancel 对 unknown external effect 进入
cancel-pending，branch/replay 创建 source/sibling-isolated child Task。

服务端 `ControlAuthorizationPolicy` 是唯一 capability authority；API payload 的
actor/role/capability extra field 被拒绝，audit metadata 不能升级 restricted
principal。最小 JSON API 已接入 control status/command、input/decision、unknown
resolution 与 derivation；正式 UI、Prompt、Tool Contract 未改。

Stage 4 定向测试 `19 passed`，Stage 1–4 联合定向 `129 passed`，默认无 Provider
回归
`1627 passed, 4 deselected, 7 warnings`；warnings 仅既有 Starlette/httpx
与 multiprocessing fork deprecation。真实 spawn 双进程 control CAS、线程
cancel/result 与 resolution race，以及 control/resolution/derivation fault rollback
均实际触发。

主 Session 给出的 live schema 9 baseline 之后，外部 scheduled sync run 351 于
`02:04:10–02:05:13+0800` 更新了 DB 指纹。V5-A 未启动或干预该进程。完整回归
稳定窗口前后均为 schema 9、SHA-256
`4f1a27ce8d4a0a62884ac197d0ef035b89fdf723ba51483dd13ba6dd49c4f735`、
94,588,928 bytes、mtime `2026-08-03T02:05:13+0800`、FK 0、integrity ok、
157/140 videos/completed。V5-A 未执行 live schema 10 migration。

## 8.12 Stage 4 Main Acceptance Round 1 bounded rework

主 Session 决定 `rework_bounded_control_lineage_and_input_lifecycle`，同时明确不重开
Stage 4 整体模型、schema 10、authority、cancel-pending、resolution、derivation、
API 与原 19 项测试。限定修复提交为 `1259993`，只改 control contracts/service
和 Stage 4 定向测试，没有 schema 变更。

resume admission 现在由一个 current-lineage helper 判定：必须绑定 active Attempt、
latest checkpoint、current control generation，以及仍未消费的 interrupt、resolved
input 或 interrupt→unknown→resolution。resume 原子追加 `superseded` disposition
消费该 authority；历史 interrupt/input 不再能授权后续 unrelated pause。status 的
`allowed_operations` 使用同一 helper，并在 unresolved effect 存在时隐藏 resume。

InputRequest 过期会经 response、status reconciliation 或 replacement admission
持久追加 `superseded(reason=expired)`；durable cancel 原子追加 `cancelled`，current
projection 不再显示 open。clarification/constraint-choice 只存 server canonical
typed schema；caller schema、decision kind、required/extra field mismatch 均在 fence
前 fail closed。

修复后 Stage 4 定向 `27 passed`，Stage 1–4 联合 `137 passed`，默认无 Provider
回归 `1635 passed, 4 deselected, 7 warnings`。live DB 在完整稳定窗口前后保持
schema 9、SHA-256
`4f1a27ce8d4a0a62884ac197d0ef035b89fdf723ba51483dd13ba6dd49c4f735`、
94,588,928 bytes、mtime `2026-08-03T02:05:13+0800`、FK 0、integrity ok、
157/140；V5-A 未执行 live migration 或 Provider。

## 8.13 Stage 4 正式接受与 Stage 5 Contract 准备

V5 主 Session 已对 bounded rework Round 1 作正式 `accept` 决定，接受 HEAD 为
`26d22cda779086681da69747fce4b97260988646`；implementation commit `8021c15`、
bounded rework commit `1259993`，独立重跑 Stage 4 定向测试 27 passed，不再要求
Stage 4 返工。本文件只轻量同步该接受事实，不另建重量级 Stage 4 acceptance 文件，
也不重新打开 Stage 4 范围。

Stage 5 JIT 只读审计确认：research create/get/status/trace、inner/outer 和 control
JSON API 已存在，但产品没有 Research 页面/导航入口；现有 status/trace 是持久原始
记录集合，尚未形成用户可理解的继续/停止原因、Evidence/Citation、Result 和 current
control 投影。`/search` 与 Fast/Deep `/ask` 已有可继承的 shared Evidence/Citation
展示资产；research authority 必须继续来自 durable checkpoint/event/evidence/control
lineage，不能继承进程内 ask trace 或一次性 graph 假设。inner/outer Provider path
仍默认 fail closed。

据此创建 `V5_A_STAGE_5_CONTRACT.md`，将 Stage 5 拆成三道互不自动授权的 gate：
mechanical product wiring/UI/trace/reliability、真实 Provider 与产品质量评价、最终
mainline integration/live schema migration。Contract 只冻结用户价值、权威边界、
可见完成条件和验收证据；内部实现由 V5-A 在获准后自主决定。

规划期无 Provider 探索性核验覆盖 Stage 4 control、`/ask` 页面和产品搜索 API，
`55 passed`，只有既有 Starlette/httpx TestClient warning。只读 live baseline 仍为
schema 9、SHA-256
`4f1a27ce8d4a0a62884ac197d0ef035b89fdf723ba51483dd13ba6dd49c4f735`、
94,588,928 bytes、mtime `2026-08-03T02:05:13+0800`、integrity ok、FK 0、
157/140；本次未执行 live migration、Provider 或凭据访问。

## 9. 当前未证明项

- Stage 1 机械安全内核已由 V5 主 Session 正式接受；接受记录见
  `V5_A_STAGE_1_MAIN_SESSION_ACCEPTANCE_DECISION.md`。
- V5-A 未执行任何 live migration。历史上外部 scheduled sync 升至 schema 7；
  本轮实施前 V5 主 Session 已正式迁移至 schema 9。source schema 10 的 live
  upgrade 仍为 `not_exercised`。
- 真实断电/SIGKILL、多主机长期 lease soak、真实 external side-effect reconciliation
  仍为 `unproven`。
- 没有执行 DeerFlow 上游测试或完整依赖集成。
- AREX 公开仓库不能复现论文的完整递归系统或训练结论。
- 没有运行 Provider，因此没有 V5-A 产品质量结论；Stage 5 Provider/product-quality
  gate 的用例、预算、模型与运行范围仍须单独授权。
- Stage 4 已证明最小完整控制面与 branch/replay isolation；正式 Research 产品入口、
  用户 trace/status projection 和真实 Provider/live corpus 产品质量仍未实施。
- Stage 2 未证明真实 Provider 的质量、成本、延迟或恢复语义；provider execution
  mode 明确 fail closed。
- Stage 2 schema 8 的 live migration、真实断电/SIGKILL、多主机长期 soak、
  production-scale retention/performance 仍未执行或证明。
- Stage 4 已机械证明 durable HITL/control fence、cancel-pending、unknown
  resolution 与隔离 derivation；正式认证/RBAC、多主机长期 soak、真实 Provider
  interrupt/reconciliation、live schema 10、正式 UI 与 held-out product quality
  仍为 `not_exercised` 或 `unproven`。
- 首次回归期间的外部 scheduled sync/live schema 7 migration 使“整个会话期间
  live DB 完全不变”不可成立；只有外部进程结束后的最终稳定测试窗口满足
  hash/size/mtime 不变。

## 10. 下一动作

Stage 4 已由 V5 主 Session 正式接受且不再返工。同一个 V5-A Version Session 已完成
Stage 5 JIT 只读审计并起草精简 Contract，当前只请求主 Session 做目标/边界级审阅；
Stage 5 产品实施、真实 Provider、mainline integration 与 live schema 10 migration
均未获授权、未执行。

```yaml
charter_status: accepted
stage_1_contract_status: fulfilled_and_accepted
stage_1_implementation_authorized: true
stage_1_status: accepted
stage_1_self_accepted: false
stage_2_contract_status: accepted_by_v5_main
stage_2_implementation_authorized: true
stage_2_status: accepted_by_user_pending_main_record
stage_2_self_accepted: false
stage_3_contract_status: accepted_by_user_for_implementation
stage_3_implementation_authorized: true
stage_3_implementation_started: true
stage_3_implementation_completed: true
stage_3_main_acceptance_round_1: rework_evaluator_authority_and_context_budget
stage_3_rework_round_1_commit: 9b2725f6ebe3db25828c72174f34bd1b91388368
stage_3_user_acceptance: complete_pass
stage_3_main_acceptance: accept
stage_3_status: accepted_and_integrated_by_v5_main
stage_3_self_accepted: false
stage_4_contract_status: accepted_with_bounded_preimplementation_sync
stage_4_implementation_start_baseline: 9b2725f6ebe3db25828c72174f34bd1b91388368
stage_4_implementation_authorized_after_sync_commit: true
stage_4_implementation_authorized: true
stage_4_implementation_started: true
stage_4_implementation_completed: true
stage_4_docs_sync_commit: f0c8775
stage_4_implementation_commit: 8021c15
stage_4_main_acceptance_round_1: rework_bounded_control_lineage_and_input_lifecycle
stage_4_rework_round_1_commit: 1259993
stage_4_implementation_report: V5_A_STAGE_4_IMPLEMENTATION_REPORT.md
stage_4_main_acceptance_decision: accept
stage_4_accepted_head: 26d22cda779086681da69747fce4b97260988646
stage_4_status: accepted_by_v5_main
stage_4_self_accepted: false
stage_5_contract: V5_A_STAGE_5_CONTRACT.md
stage_5_contract_status: draft_pending_main_review
stage_5_implementation_authorized: false
stage_5_implementation_started: false
stage_5_mechanical_product_gate_authorized: false
stage_5_provider_quality_gate_authorized: false
stage_5_mainline_integration_authorized: false
stage_5_live_schema_10_migration_authorized: false
product_implementation_started: true
provider_runs_performed: false
stage_2_live_database_migration_performed: false
stage_3_live_database_migration_performed: false
stage_4_live_database_migration_performed: false
live_database_schema_observed: 9
live_database_schema_9_migrated_by: V5_main_session
external_live_database_change_observed: true
next_action: V5_main_session_stage_5_contract_goal_boundary_review
```
