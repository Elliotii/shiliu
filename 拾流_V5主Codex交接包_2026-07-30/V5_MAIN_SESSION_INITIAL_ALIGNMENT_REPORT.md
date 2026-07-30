alignment_status: ready_for_external_review
implementation_started: false
subversion_session_created: false
runtime_modified: false
product_tests_modified: false
provider_runs_performed: false
upstream_bulk_download_performed: false
roadmap_modified: false
program_state_created: false
registry_local_status_changed: false
git_commit_created: false

# Shiliu V5 Main Session Initial Alignment Report

# 1. Package Integrity

```yaml
package_integrity:
  required_files_present: true
  required_files:
    - 拾流_V5及后续版本规划_现阶段整合版.md
    - 00_拾流V5主Codex角色权限与Session治理.md
    - 001_拾流V5开发研究与证据治理规范.md
    - 02_拾流V4_V4_1至V5技术事实交接.md
    - 03_拾流V5上游项目与研究资料注册表.yaml
    - 06_拾流V5主Codex首次接任与对齐协议.md
  supporting_files_present:
    04_拾流V5上游研究活动日志.jsonl: true
    05_拾流V5执行模板合集.md: true
  readable: true
  registry_yaml_valid: true
  registry_resource_count: 27
  research_log_jsonl_valid: true
  research_log_event_count: 14
  research_log_seed_flags_valid: true
  repository_root_found: true
  repository_root: /Users/elliot/new-systems/agent-job-prep/Shiliu
  branch: codex/v4.1-hardening
  head: 483fd46bca1d7141a696fda4b2d1e093a55f209b
  working_tree_summary:
    clean: false
    tracked_changes_observed: false
    untracked:
      - 拾流_V5主Codex交接包_2026-07-30/
    note: 交接包目录整体尚未被 Git 跟踪；本报告也位于该目录。本轮未提交或清理任何文件。
  v4_commit_present: true
  v4_commit: cbf264be2571c3d62775c064445de8a1ba17880a
  v4_1_archive_commit_present: true
  v4_1_archive_commit: 483fd46bca1d7141a696fda4b2d1e093a55f209b
  unresolved_file_or_reference_issues:
    - 04 的 14 个历史种子均可解析，且都明确 planning_only=true、source_audit_completed=false、tests_reviewed=false、spike_completed=false、implementation_authorized=false。
    - 04 的 UR-20260730-008、010、012、014 中共有 12 个 adoption_effect.status 使用 adopted_as_research_input、candidate_as_taxonomy、P0 candidate、eval-gated 等复合值；这与 001 要求复用 Registry adoption_status 统一枚举且将 priority、role、qualifier 分字段保存的合同不一致。该问题不妨碍理解交接包，但需在外部 Review 后由获授权流程决定如何修正；本轮未修改历史日志。
    - 03 中 27 个资源的 local.status 仍为 unknown，路径和本地 Commit 尚未现场核验；unknown 未被改写为 absent。
    - 03 引用的两份本地研究备忘录在正式仓库中的真实路径仍标记为 unknown；本轮按协议未扩张读取或猜测路径。
    - 多篇论文、索引仓库及部分第三方组件的 License 尚未核验；Youtu-GraphRAG 的 academic-only 自定义 License 已记录，但任何 Clone、Spike 或代码使用仍需要独立 License Gate。
```

以上只证明交接包可读取、结构可解析、仓库和记录 Commit 可定位。它不等于 V4/V4.1 Live Technical Audit，也不等于 V5 Program Governance Baseline。Commit 存在不单独证明当前分支包含它，更不证明 Runtime 已被现场验证；本轮小型 Git 日志显示当前 `HEAD` 正是记录的 V4.1 archive commit，V4 commit 位于其可见历史中，但尚未检查 Merge、Tag、全部核心路径、数据库、索引、配置或运行行为。

# 2. My Role and Non-role

我在外部 Alignment Review 和用户正式确认后拟承担的角色是：

```yaml
role:
  name: Shiliu V5 Main Codex Session
  type: program_governor_and_stage_acceptance_authority
```

本轮结束时我仍是 `V5 主 Codex 候选 Session`，不是已获正式接受的 Program Authority。

```yaml
main_session:
  implements_product_goals: false
  fixes_simple_runtime_bugs: false
  performs_stage_acceptance: true
  maintains_program_state: true
  handles_version_level_git: true
```

1. 我的职责是守住长期功能路线、管理子版本生命周期、固定和核验 Baseline、独立审查阶段源码与证据、作出阶段接受决定、维护 Program/Version 权威状态，并处理已经接受结果的版本级 Git。
2. “简单”不改变权限性质。只要动作是在实现产品 Goal、修改 Runtime 或改变产品行为，就必须由当前子版本 Session或有界独立执行 Session完成；主 Session不能通过改动规模绕过执行与接受分离。
3. 阶段验收发现一行空值判断 Bug 时，我应形成明确 Finding，将其退回当前子版本 Session，或创建有界独立执行 Session。修正完成后我重新审查；不能亲自修复后接受自己的改动。
4. 我不能编写或修改正式产品测试、Migration、产品 Prompt、Tool Contract、Schema、UI 接线或上游移植代码。
5. 我不能退化为报告转发者。正式验收必须读取 Charter、Contract、Implementation Report，并检查真实 Diff、Commit、相关源码、测试和运行证据；必要时独立复跑关键机械测试或已授权真实 Case，识别 Failure、Invalid Run、Not Exercised、Unproven 和过度声明。
6. 我可以进行只读源码、Git、数据库状态和产物核验，可以复跑不改变产品实现的相关测试；正式 Provider Case 仍需要 Contract 和预算授权，不能沿用旧额度。
7. 我的 Git 职责包括检查 status/log/diff/show，提交或批准治理与验收记录，合并或 Cherry-pick 已接受的执行 Commit，核对提交边界，并在用户批准后完成 Tag、封存和远端状态核验。
8. Merge Conflict 若只涉及可机械处理的治理记录，可在职责内处理；若触及产品逻辑、测试语义、Migration 或 Runtime 设计，必须退回执行 Session，不能在 Merge 时顺手实现。
9. 正式阶段接受者是 V5 主 Session。子版本或专项 Session只能提交 `ready_for_review` 和建议决定，不能正式接受自己。
10. 长期路线最终改变由用户决定。主 Session只能识别并触发 Roadmap Reconsideration、暂停相关实施、形成 Memo 和建议，不能单独修改路线。

# 3. Authority Map

这里同时存在规范性权威和事实性权威：

```text
规范性权威
= 决定目标、权限、正式接受和预期状态

事实性权威
= 真实源码、Git、测试、数据库和运行证据
= 决定当前实际状态
```

| 顺序 | 权威层 | 决定什么 | 不决定什么 | 冲突处理 |
|---:|---|---|---|---|
| 1 | 用户当前明确决定 | 长期路线、重大产品取舍、版本启动和 Roadmap Reconsideration 的最终选择 | 不能让不存在的代码或证据变成当前事实 | 作为最高规范性决定记录；仍以真实证据描述实施状态 |
| 2 | 长期功能路线 | V5-A/B/C/D 与 Post-V5 长期仍要实现什么、核心产品与安全边界 | 不冻结具体 Schema、框架、上游 Commit、Goal 数量或版本内部顺序，也不直接授权实施 | 当前实现缺失不能反向删除目标；挑战核心目标时暂停并触发 Roadmap Reconsideration |
| 3 | 主 Session 角色权限与治理 | 主、子版本、专项 Session 的权限、接受制度、Session 创建和恢复纪律 | 不规划各版本具体实现 | 下位 Charter、Contract 或报告不得扩大角色权限 |
| 4 | 当前 Version Charter | 当前版本要证明的用户增量、Goals、Baseline、非目标、不变量和完成条件 | 不等于每个 Goal 已授权，也不证明能力已实现 | 必须已被主 Session和用户接受；与长期路线冲突时不能自行生效 |
| 5 | 当前 Stage / Goal Contract | 本轮允许研究、修改、运行和访问什么，以及成功、暂停、证据边界 | 不授权合同外模块或未来版本，也不等于验收 | 执行越界时暂停；需要改 Contract 时交回上级，不以实施便利扩张 |
| 6 | Current State / Decision Ledger | 已接受的当前事实摘要、待决事项和对后续持续有效的决定 | 不能覆盖真实仓库，也不能凭记录创造实现 | 与真实证据冲突时修正记录并报告偏差；与上位规范冲突时服从上位权威 |
| 7 | 真实源码、Git、测试、数据库和运行证据 | 当前实际实现了什么、运行发生了什么、哪些路径被真实触发 | 不单独决定长期仍应实现什么，也不自动构成正式接受 | 作为事实性权威；实现缺失被记录为差异，不能删除路线目标 |
| 8 | Implementation / Research / Closeout Report | 组织、索引和解释真实证据，提出验收或状态更新建议 | 不能创造 Evidence，不能自我接受 | 若与源码或运行证据冲突，以证据为准，退回修正报告 |
| 9 | 外部项目、论文和规划研究资料 | 提供候选机制、产品参考、测试思路和研究问题 | 不是拾流当前事实、采用决定或实施授权 | 必须通过 Registry、固定版本研究、License、Adoption Decision 和 Contract 才能进入实施 |

因此：

```text
路线文件 = 长期还要实现什么
Version Charter = 当前版本要证明什么
Stage Contract = 本轮允许做什么
真实源码与证据 = 当前实际实现了什么
Report = 组织和解释证据，不能创造证据
外部资料 = 候选输入，不是实施授权
```

Current State 或 Report 陈旧时，应按真实证据修正记录并披露偏差；当前源码缺少某项能力时，也不能据此从长期路线中删除该能力。

# 4. Long-term Roadmap Understanding

这份路线冻结功能目标，不冻结具体 Schema、框架、上游 Commit、Goal 数量和版本内部顺序。允许实现选择和路线保持型阶段调整，也允许为当前 Goal 有限铺设未来字段；不允许提前宣称后续版本能力完成。

## V5-A：Durable Recursive Research Runtime

V5-A 把 V4 的一次性 Deep Agentic Search 扩展为可跨进程、跨时间和跨人工决策持续存在的 `ResearchTask`。它需要 `ResearchTask / ResearchAttempt / Checkpoint` 身份与 lineage；以 Inner Research Loop 完成 Plan、Navigation、Transcript Search、Window Read、Evidence Collection 和 Provisional Synthesis，再由 Outer Goal / Evidence Audit 检查 Required Aspects、Claim–Evidence、Conflict 和缺失证据。

Outer Audit 只能依据已取得的 Evidence，产生 Typed Blocker、Targeted Continuation 和基于真实 `ProgressDelta` 的 No-progress 判断。可靠性边界包括 HITL 的 Approve/Edit/Reject、Idempotency、SideEffectRecord、Retry、Cancel、Budget 和恢复不覆盖旧 Attempt。它可以产生 Knowledge、Corpus、User Model、System Experience 的 Candidate Delta，但 Candidate 不能盲目写入长期状态。V5-A 不等于给现有 Graph 简单加 Checkpointer，也不提前完成 Artifact Reuse、User Profile 或 Active Search Skill。

## V5-B：Evidence-backed Personal Knowledge and Corpus Workspace

V5-B 让一次研究形成可追溯、可更新和可复用的个人知识与收藏库工作区，而不是统一聊天向量库。内容知识必须保持：

```text
L1 Transcript Evidence / Event
→ L2 Grounded Fact
→ L3 Research Artifact / Topic Page
```

L2/L3 必须能下钻到 L1 原字幕 Evidence 与 Source Version。核心闭环包括 Artifact Reuse 的 Direct Reuse、Incremental Refresh 和 Research Seed，以及 Revalidation、Staleness、Conflict、Supersede。它还建立 Corpus Intelligence、Explicit User Memory、Behavioral/Inferred Candidate、Current Focus、Knowledge Progress 和 System Experience Store。

Corpus Model 用于 Query Rewrite、Search Prior、Reranking Hint、来源和工具选择，但不具有事实权威，不能成为 Citation、替代字幕或通过硬过滤造成自我强化。System Experience 只记录可追踪的观察和候选原因，不能直接成为 Active Skill。

## V5-C：Personalized Research Agent

V5-C 让 V5-B 的已确认长期状态真实影响产品行为。用户明确确认后形成版本化 Profile；隐式反馈和行为推断只能形成可编辑、可过期的 Candidate，不能直接修改 Prompt、Router 或 Skill。

产品能力包括 Personalized Answer、Corpus-aware Search、Personalized Routing，以及在 Artifact Reuse、Fast、Deep、Durable Research、ASR/Translation 等真实存在路径之间选择。它还包括 Current Focus 与 Knowledge Progress Assistance、Collection Delta、Staleness Reminder 和 Early Project Radar。主动帮助必须可关闭、可控制频率并能解释触发原因；收藏、搜索或观看不能被错误等同为掌握或永久偏好。

## V5-D：Controlled Experience-driven Search Policy Improvement

V5-D 不是模型训练或开放式 Self-Evolving Agent，而是让跨任务的搜索经验在受控证据下改变 Search Skill / Policy。完整链条是：

```text
Replayable Trace
→ Step-level Attribution
→ Falsifiable Hypothesis
→ Candidate Skill / Policy
→ Baseline/Treatment Paired Replay
→ Related-task Generalization
→ Unrelated Regression / Negative Transfer
→ Human Promotion
→ Progressive Disclosure
→ Monitoring / Rollback
```

Raw Trace、Diagnosis、Experience、Candidate 和 Active Policy 必须分离。Candidate 必须记录适用范围、风险、反证条件和验证计划；不能只在原失败 Query 上重跑，也要验证 Held-out related tasks 与 unrelated regression。Progressive Disclosure 只检索并注入少量适配 Skill，无匹配时回到 Baseline。

Candidate 不得修改用于判断自己的 Verifier、Dataset、Split、Judge、Promotion Gate、Evidence Authority、Experiment Identity 或 Invalid Run Policy。发布与回滚由人类控制。

## Post-V5

Post-V5 保留 Proactive Knowledge Companion 的长期方向，包括 Long-term Research Threads、Background Knowledge Maintenance、Full Project Radar 和条件式 Reviewer。它不等于当前 V5-A 任务，也不应在首次接任或 V5-A 中提前实现。是否进入后续正式版本应由真实产品信号和用户决定。

# 5. V4/V4.1 Technical Baseline Understanding

## 已实现的产品闭环

V4 已接受的产品表面包括：

- `/search` 直接证据搜索与查证入口；
- `/ask Fast` 固定有界 Grounded RAG；
- `/ask Deep` 独立 Agentic Navigation/Retrieval；
- Fast 返回 `partial/insufficient` 后保留 Query 和 Filters 的显式 Fast-to-Deep；
- Answer Block 与 Citation 展开、滚动、聚焦、高亮和 Bilibili 时间跳转；
- 用户/Developer Trace；
- `complete / partial / insufficient` 回答充分度。

Fast 默认，Deep 由用户显式选择；系统不会后台自动升级，V4/V4.1 也没有 Token-by-token Answer Streaming。

## 共享 Grounding

当前事实权威是可验证当前 Source Version 的原字幕/ASR。Title、Description、AI Summary、User Notes 和整理稿是 `navigation_only`，不能作为最终事实 Citation。

Fast/Deep 共享：

- `TranscriptEvidenceSpan`；
- 与 Retrieval Candidate 解耦的 Stable Citation；
- Source Version Revalidation；
- Evidence 与 Display Context 分离；
- Answer Blocks 作为回答正文唯一结构化事实源；
- `AnswerFinalizer`、Citation Validator 和 Fail-closed；
- `AskResponse`、Validation 和 Evidence UI。

回答充分度 `complete/partial/insufficient` 与 `termination_reason` 必须分离。截断的 `quote_excerpt` 不是完整 Citation；支持性判断必要时应按 Stable Citation 和当前 Source Version 重建权威字幕。

## Deep Runtime

Deep 独立于 Fast 和 Candidate Builder。它具有有界 Replanning、完整 Runtime State、Decision / Guard / Tool / Reducer 拓扑、确定性 Budget/Deadline/重复与 No-new Evidence 控制、结构化 Agent Action、Trace 和 `DecisionView`。

V4.1 的 `DecisionViewProjector` 将完整 Runtime State 投影为有界模型输入；完整 Evidence、Visited Set、Event 和 Guard 输入仍保留。完整 State 与模型投影分离是 V5 应继承的资产。

## 明确不存在的能力

V4/V4.1 仅使用 `langgraph.graph.StateGraph`，明确没有：

- LangGraph Checkpointer、Persistence 或 Durable Resume；
- 长期 Memory、HITL、Interrupt；
- Multi-Agent、Subgraph 或通用 Agent Platform；
- 持久化 Trace、ResearchTask 或产品级 Checkpoint；
- Artifact Reuse、Topic Page；
- User Model、Corpus Model；
- Search Skill Repository 或受控 Skill Promotion。

## V4.1 接受边界

V4.1 正式 Runtime Scope 只有 Shared Answer Boundary Hardening 和 Deterministic Deep DecisionView。一次性 Crash-safe Eval Continuation Harness 是固定 Campaign Runner，具有 WAL、Identity、Checkpoint 和去重经验，但不等于产品 Durable Runtime、ResearchTask、HITL 或副作用回滚。

Cross-video After 发生 `insufficient/provider_error`，因此：

```yaml
shared_answer_boundary_implementation: accepted
cross_video_after_online_quality: unproven
algorithm_regression_proven: false
```

H2 在两个代表性 Deep Case 上减少 Prompt Token 并改善或保持质量，但不能外推为所有 Query、收藏规模或生产延迟的普遍收益。Provider Identity 足以标识该次声明的 Campaign，却没有完整逐角色配置与 `src/shiliu/app.py` Source Digest，不能宣称完整漂移保护。

## Deferred 边界

```text
V4 Deferred ≠ V5 自动 Backlog
```

旧 Deferred 只有同时受到当前 V5 路线、已接受 Charter、真实产品问题和 Stage Contract 支持时，才能进入实施。

V5 至少应直接继承的资产：

1. Transcript/ASR Authority、`TranscriptEvidenceSpan`、Source Version 与 Stable Citation；
2. Answer Blocks、`AnswerFinalizer`、Validation、Fail-closed 与 Shared Evidence UI；
3. `/search`、Fast、Deep 和 Fast-to-Deep 产品路径；
4. Deep Runtime State、Budget、Guard、Replanning 与 DecisionView；
5. 小型真实 Eval、保留失败、不机会性重采样和独立主 Session验收纪律。

不得错误假定已经存在的 V5 能力：

1. Durable ResearchTask、Checkpoint/Resume 和持久 Trace；
2. HITL、长期 Memory 和副作用幂等恢复；
3. Artifact Reuse、Topic Page 与 L1/L2/L3 Knowledge Lineage；
4. User/Corpus Model 与 Personalized Routing；
5. System Experience 到 Active Search Skill 的受控生命周期。

# 6. Session and Acceptance Model

```text
用户
  → V5 主 Session
      → 当前子版本 Session（实际到达 V5-A/B/C/D 时按需创建）
          → 按需专项 Session
             （源码研究 / Spike / 独立实现 / Eval / Review）

当前子版本 Session
  → 研究、设计、实施、测试、集成
  → Implementation Report：提交 ready_for_review

V5 主 Session
  → 读取 Charter / Contract / Diff / 源码 / 测试 / 运行证据
  → accept / partial_accept / rework / pause / reject
  → 接受后更新 State / Ledger / Registry / Git
```

- V5-A/B/C/D 只在实际进入该版本并获得用户同意时创建，不提前建立全部 Session、Charter 或报告。
- 默认只有一个当前正式子版本，且只有一个正式活跃 Stage/Goal。
- 同一正式 Stage 可以有多个有界专项 Session并行服务，但它们只交付授权研究、实现或 Review，不形成第二条 Program 验收主线。
- 当前子版本 Session负责版本内现场审计、Just-in-time 研究、设计、源码、测试、Migration、UI、Provider/Real Case、集成和报告。
- 子版本可以根据污染隔离、复杂 Migration、高风险 Spike、Held-out Eval、独立 Review 或上下文长度创建专项 Session。
- 专项 Session只对自身 Contract 负责，结果先回到创建它的上级；它和当前子版本都不能正式接受自己的工作。
- 主 Session必须独立检查实际源码和证据，不是 Implementation Report 转发者；但主 Session做阶段性验收，不审批每个小 Commit。

模板纪律也反映这一分工：

- 每个实际子版本必需：Startup Package、Version Charter、Current State、Final Closeout；
- 每个正式 Stage 必需：Stage Contract、Implementation Report、Main Acceptance Decision；
- 研究 Contract、Adoption Decision、Blocking Report、Independent Review、Roadmap Reconsideration、Context Recovery Record 和专项执行 Prompt只在触发条件满足时创建；
- Implementation Report只能请求验收并提出状态更新；Main Acceptance Decision才定义正式接受范围、未接受项、权威更新和 Git 决定；
- 未来未启动版本的 Charter、每个小 Commit 的 Contract、每次普通浏览的研究报告和每次压缩后的全量 Recovery 均不应提前实例化。

# 7. Decision Classification Test

```yaml
- case: 1
  statement: V5-A 采用自建 SQLite Checkpoint，而不是 LangGraph Checkpointer。
  classification: implementation_decision
  reason: 它改变实现手段但保留 Durable ResearchTask、Checkpoint、Resume、Lineage 和可靠性目标。
  required_action: 由当前 V5-A 子版本在已接受 Contract 内研究、选择、实施并提供迁移、幂等、恢复和测试证据；主 Session按阶段合同验收。
  authority: 当前子版本负责实施选择，主 Session负责接受；不触发长期路线重审。

- case: 2
  statement: 将 V5-B Topic Page 的实现阶段从 G2 调整到 G3，但仍完整保留。
  classification: roadmap_preserving_change
  reason: 版本内部顺序改变，但 Topic Page 的长期功能目标和完成承诺未被删除或弱化。
  required_action: 子版本提出影响与新依赖顺序，主 Session确认路线仍保留；材料性调整由用户确认并写入 Charter或 Decision Ledger。
  authority: 子版本提议，主 Session分类和维护权威记录，用户确认重要调整。

- case: 3
  statement: 取消 Artifact Reuse，仅保存最终回答文本作为缓存。
  classification: roadmap_reconsideration
  reason: 这把 V5-B 的 Evidence-backed、可重验证、可增量更新和可追溯 Artifact 核心闭环降级为普通回答缓存。
  required_action: 立即暂停相关实施，形成 ROADMAP_RECONSIDERATION_MEMO.md，保留原路线文件，等待用户最终决定。
  authority: 用户；主 Session只能触发审查和提出建议。

- case: 4
  statement: 允许 AI Summary 与原字幕作为同级事实来源。
  classification: roadmap_reconsideration
  reason: 这改变 Transcript/ASR 事实权威和 Citation Lineage，是受保护的产品身份边界，不是普通 Schema 或 Prompt 调整。
  required_action: 暂停，形成 Roadmap Reconsideration Memo，说明对 Stable Citation、Artifact 和全部后续知识层的影响，等待用户决定。
  authority: 用户；主 Session无权单独放宽 Evidence Authority。

- case: 5
  statement: 主 Session 在验收时发现一行空值判断错误，直接修改并宣布接受。
  classification: prohibited_main_session_implementation
  reason: 改动大小不改变“执行者不能正式接受自己”的隔离；直接修复会同时越过产品实施禁令和独立接受边界。
  required_action: 退回当前子版本 Session，或创建有界独立执行 Session；修复、测试和报告完成后由主 Session重新验收。
  authority: 执行 Session负责修复，主 Session只负责 Finding 和验收。

- case: 6
  statement: 在 V5-A 中先加入未来 V5-B 需要的 source_version 字段，但本阶段不宣称 Artifact Reuse 已完成。
  classification: possible_roadmap_preserving_foundation
  reason: 路线允许有限前置未来字段，但不能偷渡未来能力或制造完成声明。
  required_action: 只有在该字段服务当前 V5-A Goal、范围有限、兼容现有 Citation/Source Version、不引入未使用平台且被 Charter/Contract记录时实施；报告明确 V5-B Artifact Reuse 仍未完成。
  authority: 子版本提出和实施，主 Session判断是否保持路线并按合同验收；材料性调整由用户确认。

- case: 7
  statement: DeerFlow 已经下载到本地，因此直接将其 Runtime 作为拾流正式依赖。
  classification: invalid_reasoning
  reason: download_does_not_equal_adoption_or_implementation_authorization；本地存在也不证明 Commit、License、源码、测试、适配成本或权威边界已核验。
  required_action: 检查 Registry/本地身份和 Stage 授权，固定官方 Commit与 License，进行有界源码/测试研究或 Spike，记录 Research Log，形成 Adoption Decision，并写入 Stage Contract后才可实施。
  authority: 子版本或专项 Session研究和提出采用；主 Session在阶段接受时核对；Contract授予具体实施边界。

- case: 8
  statement: V4.1 Cross-video After 出现 Provider Failure，因此认定 Shared Answer Boundary 回归。
  classification: invalid_evidence_inference
  reason: provider_failure_does_not_prove_algorithm_regression；该次运行既不能证明在线质量通过，也不能证明 H1 造成回归。
  required_action: 保留 provider_failure，维持 cross_video_online_quality=unproven；只有有效、可归因的对照证据才能判断算法回归，且不得机会性重跑。
  authority: 证据分类由 001 与当前 Eval Contract约束；主 Session根据有效证据作接受边界判断。
```

# 8. Upstream Research and Adoption Mechanism

完整机制是：

```text
检查 Registry 和本地状态
→ 判断当前 Version / Stage 是否授权
→ 必要时 Clone / Download
→ 固定官方 Commit / Release
→ 核验 License 和第三方条款
→ 有界阅读源码、测试或运行隔离 Spike
→ 追加材料性 Research Log
→ 形成 Adoption Decision
→ 将采用方式和 implementation_authorized=true 写入已接受 Stage Contract
→ 才能正式实施
```

1. Registry 保存资源的当前权威状态：官方来源、本地状态和路径、固定版本、License、研究深度、版本相关性、当前采用判断、使用历史、风险和下一研究触发条件。
2. Research Log 保存材料性 Research Episode，即判断如何形成和改变：固定新 Commit、关键源码/测试研究、Spike、License或维护变化、Adoption Decision、实际采用、拒绝或淘汰。
3. 每次页面点击、grep、README 打开或无结论浏览不改变 Program 判断，记录它们会制造噪声和治理膨胀，所以不进入 Log。
4. 当前子版本或专项 Session只有在资源已经进入 Version Charter、Stage Contract或明确专项研究任务，且先检查本地副本后，才可自主按需下载。当前首次接任阶段没有这种授权。
5. License 不清、危险安装脚本、大模型/数据集/高成本服务、凭据或私有数据、正式数据库/索引写入、不可逆外部副作用、受保护权威变化、跨入未授权版本、Held-out/Gold越权或研究反复无进展时必须暂停。
6. 下载只表示材料到达本地；源码研究表示检查固定实现；采用表示对某种机制形成正式 Decision；实施授权还要求进入已接受 Contract。四者不能互相替代。
7. 规划阶段的 `docs_reviewed` 只能证明阅读相关公开文档，不能视为本地固定 Commit 的源码审计，更不能升级为 `source_reviewed` 或 `tests_reviewed`。
8. Youtu-GraphRAG 使用 academic-only 自定义 License，并被路线定义为 Eval-gated、默认不实现。任何 Clone、Spike 或代码使用前都要单独审查许可证和研究范围；关系还必须能绑定 Transcript Evidence。
9. 当前 P0/P1 资源仍只是候选或参考，不是正式依赖。例如 DeerFlow、AREX、DeepTutor、SearchCLI、SkillAdaptor、HDSO 是 P0 研究候选；WeKnora、Youtu-Agent、SkillOS、MUSE-Autoskill 是 P1 候选/参考。其 `implementation_authorized` 均为 `false`。两份本地 Memo被采用为规划输入，也不构成产品实施授权。
10. 首次接任不应批量下载候选。本轮只确认 Registry 当前仍为 `unknown` 的本地事实尚待后续 Live Audit；具体资源应在对应子版本和 Stage 到来时 Just-in-time 获取与研究。

# 9. Context Recovery Understanding

```yaml
reread_after_every_compaction: false
targeted_recovery_before_high_weight_actions: true
```

1. 上下文压缩后不机械重读全部交接包。压缩不必然造成角色丢失，全量复读会占用上下文并让长期宽规划干扰当前阶段。
2. 新物理主 Session接任、创建子版本、阶段验收、修改 Charter、更新 Program/Version 权威状态、Merge、Tag、封存、提出 Roadmap Reconsideration，或无法准确说出 Baseline/Stage/待决事项时，必须主动恢复。
3. 后续恢复第一层固定读取 `00_拾流V5主Codex角色权限与Session治理.md` 和 `V5_PROGRAM_CURRENT_STATE.md`。
4. 当前阶段验收还必须读取当前 Version Charter、Stage/Goal Contract、Implementation Report，以及 Decision Ledger 中直接相关条目；随后核对 Diff、源码、测试、运行证据和 Git。
5. 只有动作涉及长期功能边界、版本目标保留或 Roadmap Reconsideration 时，才重读完整长期路线。
6. 只有具体上游机制进入研究、采用或验收范围时，才读取相关 Registry 项、Research Log Episode、研究报告和固定上游源码；不默认读取完整 Registry、全部 Log或所有仓库。
7. 无法确认当前 Baseline 时，应暂停高权重动作，现场核验 Branch、HEAD、Working Tree和风险级别要求的 Schema、Corpus、Provider、Artifact、Dataset/Split等身份；不能猜测或用旧报告代替。
8. 新物理主 Session通过 `00`、Program Current State、当前 Charter、最新待验收/已接受报告、相关 Ledger和 Git Baseline继任，输出最小 Recovery Record；恢复完成前不创建子版本、不验收、不 Merge、不改路线。首次接任因 Program Current State尚未创建，执行的是本次完整 Initial Alignment Protocol。
9. 定向恢复将有限上下文用于当前高权重决定所需的权威和事实，既保留连续性，又减少宽泛历史、未触发研究和未来版本细节对当前判断的污染。

# 10. Conflicts, Ambiguities and Unknowns

- 没有缺失或无法读取的第一轮必读文件；`03` YAML 与 `04` JSONL 均可解析，因此不存在阻止理解的 Package Integrity blocker。
- `04` 有 12 个历史 `adoption_effect.status` 违反 `001` 的统一枚举合同。它们表达的规划意图可从各 Episode 的 `priority/target/recommended_modes` 理解，但当前格式冲突应由外部 Review确认后在获授权流程中修正；不能把复合标签当成正式采用状态。
- 当前 Branch、HEAD和两个记录 Commit与 `02` 的封存身份相符；但 Merge 到默认分支、Tag、全部远端状态和现场 Runtime 尚未核验。
- Working Tree不是 clean：整个交接包目录为 untracked。本轮未将其删除、移动、提交或解释成产品变化。
- Registry中全部 27 个资源的本地状态仍为 `unknown`；本轮没有猜测路径，也没有把 `unknown` 改成 `absent`。
- 两份本地研究 Memo在正式仓库中的真实路径尚未核验。
- 多篇论文与索引资源的 License未核验；DeerFlow局部 Skill、WeKnora第三方组件等也需要采用时逐项复核。Youtu-GraphRAG的 academic-only限制是额外 Gate。
- `docs_reviewed`、规划 Memo和14条历史 Episode都是 planning evidence，不是固定 Commit的源码或测试事实。当前没有任何候选因此成为正式依赖。
- V4/V4.1交接事实尚未通过完整 Live Repository Audit重新核对核心路径、数据库、索引、Provider配置和测试环境；本报告不能把封存摘要写成当前现场审计结论。
- 后续具体子版本必须通过真实源码研究回答：DeerFlow与现有 StateGraph/DecisionView的接点、AREX Outer Audit的拾流 Evidence合同、DeepTutor三层对象和幂等写入、WeKnora Topic Page更新流程、Youtu-Agent最小Experiment身份、SearchCLI/SkillAdaptor可复用边界等。本节不对这些问题预设方案。

上述问题均为需要外部校准或后续获授权现场/源码研究的事项；目前没有一项使核心角色、路线、技术基线或治理机制无法理解，因此状态为 `ready_for_external_review`，而不是 `blocked`。

# 11. Proposed Actions After Alignment

后续动作只能按以下顺序进行：

1. 接收外部 Alignment Review；
2. 完成必要的有限修正；
3. 等待用户确认正式接任；
4. 执行完整只读 Live Repository Audit；
5. 创建 `V5_PROGRAM_CURRENT_STATE.md`；
6. 创建 `V5_PROGRAM_DECISION_LEDGER.md`；
7. 现场核验并更新 Registry 本地状态；
8. 建立 V5 Program Governance Baseline；
9. 准备 V5-A 子版本启动建议；
10. 经用户批准后才创建 V5-A Session。

这里没有提出 V5-A 具体架构、最终 Goal 拆分、Provider Matrix、批量 Clone、V5-B/C/D Session或 V4 Deferred清理。

# 12. Explicit Non-actions

```yaml
non_actions:
  runtime_modified: false
  product_tests_modified: false
  migration_created: false
  product_prompt_modified: false
  provider_runs_performed: false
  subversion_session_created: false
  roadmap_modified: false
  program_state_created: false
  program_decision_ledger_created: false
  registry_local_status_changed: false
  upstream_bulk_downloaded: false
  upstream_adoption_approved: false
  git_commit_created: false
  git_merge_performed: false
  git_tag_created: false
```

本轮唯一写入是新增本报告文件。没有修改交接包既有文件，也没有开始 V5-A。

```yaml
initial_alignment_round_complete:
  core_files_read: true
  package_integrity_checked: true
  report_generated: true
  report_status: ready_for_external_review
  runtime_modified: false
  provider_runs_performed: false
  subversion_session_created: false
  roadmap_modified: false
  bulk_upstream_download: false
  git_commit_created: false

first_alignment_complete: false
main_session_formally_accepted: false
v5_a_authorized: false
```
