# 拾流 V5-C Current State

```yaml
document_status: proposed_startup_state_pending_v5_main_review
version: V5-C
updated_at: 2026-08-09
execution_branch: codex/v5-c
required_starting_ref: codex/v5-main
starting_commit: 5fbe1641ecf52aa8d09c5f838d41a7d1bad7c084
accepted_code_baseline_merge: 7d9af9009926c13cd94e149b9e54c87cdf2ffc9d
active_formal_stage: startup_and_JIT_docs_only
stage_1_status: proposed_not_active
charter_status: proposed_pending_v5_main_acceptance
implementation_authorized: false
product_files_changed: false
schema_source_version: 14
live_schema_observed: 14
provider_runs_performed: false
credentials_or_keychain_accessed: false
live_database_mutated: false
external_JIT_research_performed: false
```

## 1. Git 与 authority 状态

启动现场最初为 detached HEAD，实际 HEAD 是要求的
`5fbe1641ecf52aa8d09c5f838d41a7d1bad7c084`，工作树 clean，`codex/v5-main` 指向同一 Commit。
`codex/v5-c` 当时不存在，已在任何编辑前显式创建并切换；起始 Commit 未改变。

`5fbe164` 是本次用户指定的真实 V5-C startup planning 起点；早期 V5-C planning 文档中的旧 hash 只作
历史规划观察，不替代本轮起点。V5-B 已接受产品代码通过 merge `7d9af900` 进入该祖先链，live schema
已由 Main 迁移到 14。

当前唯一 active formal Stage 是 `startup_and_JIT_docs_only`。Stage 1 只是提案，未激活、未接受、
未授权实施。V5-C Session 未修改 Program Current State/Decision Ledger，也未自我接受任何材料。

## 2. Live schema 14 只读观测

观测对象：`/Users/elliot/Library/Application Support/Shiliu/shiliu.db`。

使用 SQLite URI `mode=ro&immutable=1`、`PRAGMA query_only=ON` 做只读查询，并在窗口前后核对文件
SHA-256、size、mtime。观测窗口内结果：

| 项目 | 观测值 |
| --- | ---: |
| schema version | 14 |
| integrity_check | `ok` |
| foreign_key_check rows | 0 |
| videos / completed | 157 / 140 |
| sync_runs / active sync | 436 / 0 |
| research_tasks | 0 |
| research_events | 0 |
| WorkspaceRecord revisions | 0 |
| ArtifactRoute records | 0 |
| TopicPage revisions | 0 |
| `v5b_product_feedback_recorded` events | 0 |
| frozen taxonomy snapshots | 2 |
| latest snapshot hash | `1143f0999c569db30b2184a0129e446d3301c0c84e53a34a2807ac9f39db02a2` |
| latest snapshot memberships / content rows | 131 / 131 |
| latest discovery eligible / trial assignment | 128 / 3 |
| file size | 94,588,928 bytes |
| observed SHA-256 before/after | `50a56953d5d3da3afa80a72f3aa070a6fd197ce656a4fb7cc02f8a69a7c5b697` / same |

两次 exploratory taxonomy 查询使用了不属于当前 schema 的候选列名，SQLite 均在对应 `SELECT` 的
prepare 阶段拒绝；此前合法只读查询不受影响。随后读取 `PRAGMA table_info`，用真实列名
`id/trial_assignment_only_count` 做有界复跑，得到上表 snapshot 结果。复跑前后 hash/size/mtime 均未
变化；这是侦察 harness field mismatch，不是产品 Bug，也未新增 Gate/Amendment。

live `sync_runs=436` 高于历史 closeout 记录的 434/435，说明正常产品运行曾继续写入；本 Session
没有把它归因于 V5-C。上述数值是 2026-08-09 的只读现场观测，不是冻结业务 snapshot。

## 3. Cold-start 结论

```text
live Research = cold start
live Feedback = cold start
live Workspace/Profile/Current Focus = cold start
live ArtifactRoute/TopicPage = cold start
```

两份 frozen taxonomy snapshot 是真实的现有 corpus state，但当前没有任何
`corpus_observation` WorkspaceRecord 将其转化为 personalization input。因此 live corpus 不是“空语料”，
却仍是“零个性化输入”。测试 fixture/seeded temp DB 只证明 authority 和 non-interference，不能冒充用户
历史、真实偏好或收益。

## 4. 当前真实数据与产品路径

### 4.1 WorkspaceRecord

- 物理权威：schema 14 的单表 immutable append-only aggregate；update/delete triggers 拒绝原地变化；
- kinds：explicit memory、inferred candidate、focus、progress、corpus observation、system experience；
- authority：user-authored/user-confirmed、behavioral candidate、evidence-backed observation、corpus soft
  prior、experience candidate；
- inferred candidate 至少两个 distinct Research Event refs；focus 可用户明确或候选；
- learned/understood/familiar 只接受 `user_asserted`，观看/收藏不等于掌握；
- corpus observation 恰好绑定 frozen taxonomy snapshot，仍是 soft prior；
- system experience 绑定同 task Trace+Result，不修改 Skill/Policy；
- read projection 已解释 authority/status/expiry/allowed actions，但明确
  `product_behavior_effect=false`；当前没有 Search/Ask/Research/Route consumer。

### 4.2 Feedback

- 当前唯一产品反馈是 `SubmitKnowledgeFeedbackRequest` →
  `v5b_product_feedback_recorded` Event + CommandReceipt；
- target 只能是同 task 的 exact immutable TopicPageRevision content hash 或 ArtifactRoute expected
  authority hash；
- decision 仅 `helpful|needs_fix`，reason 是 answer_quality/citation/currentness/route/usability/other；
- advisory only、automatic false，具备 cross-task/hash/payload mismatch/idempotency/fault rollback；
- 当前无 consumer 将它自动变成 Profile、Prompt、Router、Skill、Fact 或 Page mutation。

### 4.3 Corpus soft prior

- corpus authority 是 frozen taxonomy snapshot，不是 Workspace fixture；
- V5-B 测试证明 seeded corpus observation 与 empty baseline 对 Search/Ask/Research/ArtifactRoute 完全
  non-interfering；
- 当前 Product Search 由 query type 和显式 mode 决定 lexical/hybrid，folder/topic state 不作个性化；
- V5-C Stage 2 才可提出 bounded soft-prior consumer，且必须保留 independent open lane/counterexample。

### 4.4 ArtifactRoute

- assess 只允许 terminal Research task；Artifact candidate 是 bounded lexical/structured inspection；
- open retrieval 独立执行，标记 `independent_lane=true`、`hard_filter=false`；
- direct reuse 需要 exact scope、完整 aspects、current Facts 与 current citations；
- incremental 只允许 compatible usable core + 最多两个 isolatable gaps；否则 research seed；
- proceed 需要用户明确选择且只能相同或更安全，late authority hash fence 会重新验证；
- old Artifact 只能是 candidate context，不能成为 Verifier 或 hard filter；
- 它不决定 Fast/Deep/Research/ASR/Translation 的通用路线。

### 4.5 Fast / Deep / Research

- Fast：query analysis → Product Search/transcript evidence → provider answer → current-evidence finalizer；
- Deep：bounded decision graph，Navigation 只导航，最终仍只引用 current transcript/ASR evidence；
- `AskRequest.mode` 是用户 `fast|deep` 显式选择；当前没有 Profile/Workspace consumer；
- Product Search planner 按 query type 选择 lexical/hybrid，显式 mode 优先，无 Profile/Corpus consumer；
- Research 使用 durable Task/Attempt/Checkpoint/Event/Result/Receipt runner；product wiring 固定
  `provider_runs_authorized=false`，当前默认 deterministic no-provider；
- Candidate Delta 和 Workspace/Feedback 都不会改变 Research Prompt、budget 或 route。

### 4.6 ASR / Translation

- ASR 是真实 Paraformer provider path，使用 durable `asr_jobs`、manual/automatic trigger、retry/
  needs-review，并把完成的 raw ASR 作为 current transcript evidence source；
- 当前 pipeline 对缺字幕短视频有 bounded automatic ASR（每次 sync 最多一个），也有显式 manual API；
- V5-C personalization 不得自动触发 ASR 或访问 credential，Stage 3 只能在权限/预算边界内推荐；
- 没有独立 Translation service/table/API/route。英文字幕在现有 `transcript_cleanup` Prompt 中保留 raw
  English、整理结果输出 Chinese；这是付费 transcript processing 的组合能力，不是独立路由。

## 5. Startup 设计状态

提议复用 WorkspaceRecord 作为唯一状态 authority，以只读、可重建、consumer-whitelisted
`PersonalizationContext` 投影向产品暴露 confirmed state。Stage 1 只消费一个 preference key：

```text
answer.presentation.limitations_position = before_answer | after_answer
```

只允许 user-authored/current 或 user-confirmed/confirmed 生效；candidate、expired、rejected、tombstoned、
malformed、unknown 和 unrelated records 均 fail closed。效果仅是 Research UI 对既有 limitations panel 的
前/后位置，不改变答案文本、引用、证据、状态、检索、route、Prompt、budget 或 Provider。

Current Focus 在 Stage 1 进入 versioned context 和 explanation，但不改事实答案。结构化 Feedback 仍是
advisory Event；至少两个一致来源只允许形成 candidate，必须再由用户确认。

完整 Stage 序列和边界见 `V5_C_VERSION_CHARTER.md`；可执行 Contract 见
`V5_C_STAGE_1_CONTRACT.md`。

## 6. JIT 研究状态

本地 accepted evidence 足以约束 Charter/Stage 1，因此未访问外部网络、未下载/checkout 上游、未新增
依赖，也未创建 upstream report。DeepTutor/WeKnora 只延续 V5-B accepted reference-only 身份；本轮
没有新 adopt/reimplement/copy proposal。若未来 Stage 出现具体材料缺口，再按官方来源、固定 Commit、
License、相关源码/测试和明确 adopt/reimplement/reject 开新 episode。

## 7. 未证明项与下一动作

未证明：

- 真实用户 Profile/Feedback/Current Focus 是否提升答案、搜索、路由或帮助质量；
- distinct Translation route 与其 budget/recovery/authority；
- Corpus soft-prior 在真实集合上的 recall/counterexample/latency；
- personalized route 推荐的真实成本收益和用户 override 质量；
- Progress/Staleness/Delta/Radar 的频率、长期 no-resurrection 和 UX；
- large Workspace、multi-process UI ordering、Provider 主观质量；
- V5-A compound long-query grounded completion。

下一动作仅是等待 V5 Main 对 Charter、Stage 序列、Stage 1 Contract、无材料性 upstream adoption
proposal 和 Stage 1 implementation authorization 做有限决定。未授权前不开始产品实施。
