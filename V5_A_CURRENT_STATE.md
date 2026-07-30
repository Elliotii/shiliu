# 拾流 V5-A Current State

```yaml
as_of: 2026-07-30
version_session: Shiliu V5-A Version Session
state_authority: V5-A execution-session observation
formal_acceptance_authority: V5 main session
branch: codex/v5-a
startup_head: 2feccbccaa288f67071d22460eb220d50b19d871
product_baseline_commit: 483fd46bca1d7141a696fda4b2d1e093a55f209b
artifact_commit: reported_in_main_session_handoff
charter_status: draft_pending_main_review
stage_1_contract_status: draft_pending_main_review
product_implementation_started: false
provider_runs_performed: false
```

## 1. 本轮范围状态

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| 十份必读治理/交接材料 | completed | 已完整读取；Program 级文件未修改 |
| Git/Working Tree 现场 | completed | 启动时工作树干净，已在 `codex/v5-a`，HEAD 为 `2feccbc...`，无需切换 |
| DB/Index/Corpus/Provider 配置核验 | completed_read_only | 未执行 migration、未访问 secret 值、未访问 Keychain、未发 Provider 请求 |
| V4 产品源码审计 | completed_bounded | Deep、DecisionView、Evidence/Citation、Trace、DB 与路由已核验 |
| V4.1 Harness 审计 | completed_bounded | continuation 与 H0 checkpoint/failure tests 已核验 |
| DeerFlow 研究 | source_and_tests_reviewed_not_executed | 官方提交与 License 固定；定向源码和测试审阅；未采用 |
| AREX 研究 | paper_and_limited_official_source_reviewed | 论文 v2、官方最小推理源码和 License 固定；无测试可审 |
| youtu_agent | deferred | 未 Clone、未深研 |
| 产品实现 | not_started | 本轮没有 Runtime、测试、Migration、Prompt、Tool Contract 或 UI 修改 |

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
- Program Current State 记录的 150 已发生漂移；V5-A 只报告，不修改 Program 文件。

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
- Adoption 状态：`pattern_only_reimplementation_proposed_pending_main_review`。

### AREX

- 论文：arXiv `2607.21461v2`
- 官方模型/最小推理仓库：`https://huggingface.co/BAAI/AREX-Turbo`
- 固定提交：`129812742df4a5de27980ed07bda78d9d27c7370`
- 论文发布许可：arXiv perpetual non-exclusive license。
- 官方仓库代码/模型许可：Apache-2.0。
- 官方代码只提供最小单轮 action generation 与 prompts；没有完整 outer loop、工具执行器、训练管线、评估 Harness 或测试。
- Adoption 状态：`training_independent_patterns_only_proposed_pending_main_review`。

### youtu_agent

- `deferred_no_clone_no_deep_research`。

## 8. 本轮无 Provider 验证

使用当前工作树 `src` 和既有共享 Python 3.12 环境执行两组定向机械测试：

1. V4 Ask contracts、Evidence/Citation、Fast/Deep、V4.1 continuation/H0：81 passed。
2. DB/schema/sync、Evidence contract/snapshot、产品 search API、V4 search execution：41 passed。

合计：122 passed，0 failed。

测试命令显式使用当前工作树的 `PYTHONPATH=src`。仓库默认 pytest 配置排除 `external_artifact` 与 `live_provider`，所选文件也未发起 Provider。唯一 warning 是既有 FastAPI TestClient 的 Starlette/httpx deprecation warning。

工作树本身没有 `.venv`；首次尝试在测试收集前因 `.venv/bin/python` 不存在退出，随后使用主仓库既有共享环境完成上述测试。没有联网安装依赖。

## 9. 当前未证明项

- Stage 1 产品 schema 与 API 尚未被主 Session 接受。
- 没有产品 ResearchTask Runtime、持久 checkpoint 或 SideEffectRecord 实现。
- 没有执行 DeerFlow 上游测试或完整依赖集成。
- AREX 公开仓库不能复现论文的完整递归系统或训练结论。
- 没有运行 Provider，因此没有 V5-A 产品质量结论。
- 没有证明 branch/replay 与拾流现有 live corpus 的集成行为。
- 没有证明跨进程 cancel、lease takeover 或未知 external side effect 的产品实现。

## 10. 下一动作

V5 主 Session 应先审阅：

1. `V5_A_VERSION_CHARTER.md`
2. `V5_A_STAGE_1_CONTRACT.md`
3. 两份上游研究报告中的 Registry / Research Log 更新建议与 Adoption Decision Proposal
4. 155 内容目录的现场 baseline update

未经主 Session 决定，V5-A 不开始产品实现。

```yaml
charter_status: draft_pending_main_review
stage_1_contract_status: draft_pending_main_review
product_implementation_started: false
provider_runs_performed: false
next_action: main_session_charter_and_stage_1_review
```
