# 拾流 V5-B Version Charter

```yaml
document_status: draft_pending_v5_main_acceptance
version_session: Shiliu V5-B Version Session
proposal_authority: V5-B execution session
acceptance_authority: V5 main session
created_at: 2026-08-04
limited_main_review: mission_boundaries_and_stage_sequence_accepted_in_principle_bounded_scope_correction_applied
starting_branch: codex/v5-b
starting_commit: b85340540cb92c2e46bfb8619598e7aa987171d4
accepted_v5_a_code_baseline: 04e5c5bbb94311a00f6efafa142908fd7b2b97de
implementation_authorized: false
product_implementation_started: false
provider_runs_authorized: false
provider_runs_performed: false
live_database_migration_authorized: false
```

> 本文件是 V5-B Session 的技术提案，不是 Program 权威，也不构成自我验收。只有 V5 Main 接受本 Charter 和具体 Stage Contract 后，才可在相应范围内实施。

## 1. 版本使命

V5-B 把 V5-A 的一次 Research Task 结果转化为可审查、可修正、可再验证、可复用的个人知识与收藏库工作空间：

```text
Research Task
→ Candidate Delta
→ Evidence Review
→ L2 Grounded Fact
→ L3 Research Artifact / Topic Page
→ Revalidation / Conflict / Staleness / Supersede
→ Direct Reuse / Incremental Refresh / Research Seed
→ Explicit User Memory / Current Focus / Knowledge Progress / Corpus Model
→ SystemExperienceRecord（不升级 Active Skill）
```

V5-B 不替换 V5-A Research Runtime，也不把普通聊天历史、模型摘要、Wiki Markdown 或向量索引提升为事实权威。

## 2. 已确认起始 Baseline

### 2.1 Git 与产品代码

- 执行分支：`codex/v5-b`。
- 本轮起始 Commit：`b85340540cb92c2e46bfb8619598e7aa987171d4`。
- 已接受 V5-A 产品代码 Commit：`04e5c5bbb94311a00f6efafa142908fd7b2b97de`。
- `04e5c5b..b853405` 只包含 V5-A closeout、Program 状态和 V5-B 启动文档变化，没有产品源码变化。
- 当前 schema version 10；V5-A Gate C 已通过，最终状态为 `accepted_with_known_retrieval_limitation`。
- V5-A 代表性长 compound query 的 grounded completion 未证明；该 retrieval limitation 不是 V5-B 自动 backlog。

### 2.2 可直接复用的 V5-A 权威

- `ResearchTask/Goal/Attempt/Checkpoint/Result/Event/CommandReceipt/SideEffect/HumanDecision/Derivation` 的持久 identity、lineage、CAS、owner lease/epoch 与故障语义；
- `EvidenceIdentity` 的全局稳定引用身份；
- `EvidenceUse` 的 task/attempt 作用域；
- append-only provenance/currentness validation；
- immutable provisional artifact；
- V5-A Stage 5 Candidate Delta snapshot：Event + CommandReceipt，同一 boundary exact-once、candidate-only；
- API/UI 中可下钻引用、durable trace 和 candidate-only 投影。

### 2.3 明确缺失

- Candidate 没有独立长期 review lifecycle；当前只是 Event payload snapshot；
- 没有 GroundedFact/FactRevision、ResearchArtifact family/revision、TopicPage/PageRevision；
- 没有 fact-level conflict/stale/supersede、Artifact reuse/refresh/seed；
- 没有 Explicit User Memory、TopicState/KnowledgeProgress、CorpusModel、SystemExperienceRecord；
- 没有 V5-B 用户 review/inbox/workspace。

## 3. 冻结不变量

1. 原字幕/ASR artifact 仍是事实权威；L2/L3 只能引用 L1，不能覆盖或修改 L1。
2. L1 由 V5-A EvidenceIdentity/EvidenceUse/Provenance/Validation 和 durable Event 承担；filesystem JSONL、模型 trace 或 Page Markdown 不能取代它。
3. 每个 GroundedFact revision 必须能沿明确 link 回到 EvidenceIdentity、原始 EvidenceUse、SourceVersion 和用于 promotion 的 current validation。
4. Artifact/Page 的每个事实性块必须回到允许的 FactRevision，再回到 L1；页面关系只是导航，不是 Citation。
5. V5-A Candidate Delta 始终是 candidate-only；不得自动 promotion。
6. accept/edit/reject/correct/retire/supersede/revert 在其获授权 Stage 中都必须是显式命令与 append-only Decision/Event；不得静默覆盖历史。
7. 用户确认只能授予“用户选择/偏好/审核决定”的权威，不能单独证明外部事实。
8. V5-B 不以 physical delete、overwrite history 或 reset 表达权威变化；Stage 1 只实现 Candidate reject/edit lineage，Fact/Page correction/retire/supersede/revert 产品命令进入 Stage 2。
9. 所有重复命令使用 CommandReceipt + payload hash；payload mismatch fail closed；跨 Task/Evidence/owner/version 引用 fail closed。
10. SQLite 是身份、状态、lineage 和 canonical body 的唯一权威；filesystem 是按 revision/hash 寻址、可重建的不可变导出/缓存。
11. 构建/刷新状态必须持久；process lock、Redis flag、SSE/polling 只可作为投影或唤醒机制。
12. Corpus Model 是无 citation authority 的 soft prior，不能替代字幕、硬排除来源或自我强化缩窄搜索。
13. Explicit User Memory 与 behavioral/inferred candidate 必须分离；candidate 需可确认、编辑、拒绝、过期，拒绝后不得被旧事件静默恢复。
14. SystemExperienceRecord 只能记录 observed/diagnosed/candidate_source/invalidated，不得在 V5-B 晋升 Active Skill/Policy。
15. V5-B 不实现 V5-C Personalized Answer/Search/Routing/Proactive behavior，不实现 V5-D Active Skill promotion。
16. 不把多租户、RBAC、Connector、企业 Wiki、通用 RAG 平台或 GraphRAG 作为 V5-B 默认范围。
17. `/search`、`/ask` Fast/Deep 与 `/research` 的既有权威/行为保持兼容；任何材料性变化需相应 Stage Contract。

## 4. 领域层级的正式定义

### L1 — Evidence / Event authority

沿用 V5-A：Transcript Evidence span、Stable Citation、SourceVersion、EvidenceUse、Validation、ResearchTask Event、UserDecision/Feedback Event。L1 是不可被 L2/L3 改写的证据与审计根。

### L2 — Grounded Knowledge

`GroundedFact` 是稳定 lineage；`FactRevision` 是不可变 assertion revision，至少包含 normalized claim、temporal/viewpoint scope、verification state、Evidence links、来源 Candidate/Task、创建 Decision 和 supersedes link。

“当前、stale、conflicted、retired”由追加 observation/decision 和 current projection 派生，不回写旧 revision 内容。

### L3 — Research Synthesis and Topic Page

- `ResearchArtifact` 是可检索的研究综合 family；不可变 ArtifactRevision 引用 FactRevision，并保存 scope、limitations、unresolved questions、corpus/source snapshot。
- `TopicPage` 是稳定用户入口；不可变 PageRevision 引用 ArtifactRevision/FactRevision，展示不同观点、时间演化、冲突、局限、未解决问题和字幕下钻。
- Artifact/Page 的 current head 是投影；Stage 2 的 edit/revert 必须产生新 revision。

## 5. 架构选择

### 5.1 Candidate intake 不直接复用 Event 为可变 review row

V5-A snapshot 保持不可变来源。V5-B 建立长期 Candidate intake identity，以 `(source_event_id, candidate_kind, candidate_hash)` 去重，保存 source task/attempt/checkpoint/result/artifact/boundary hash。Review status/版本是 V5-B 自己的受控 lifecycle。

Stage 1 只允许 `KnowledgeDelta` 进入 Fact promotion；CorpusDelta/UserModelDelta/SystemExperienceDelta 继续 candidate-only，分别在后续 Stage 处理。

### 5.2 Revision-first，而非 in-place overwrite

Fact、Artifact、Page 都使用 stable family ID + immutable revision ID + append-only decisions/observations。Stage 1 只创建初始 immutable revisions，并为未来 lineage 保留 hook；Stage 2 才交付 Fact correction/retire/supersede、Page edit/history/diff/revert 与后续 revisions。用户可见 change 使用 expected version/revision guard，旧历史保持可查询。

### 5.3 Durable BuildRun

页面/Artifact build、未来 refresh/rebuild 使用持久 BuildRun。Stage 1 只同步执行 deterministic no-provider artifact/page build，并证明 receipt、terminal 结果和重启稳定；Stage 2 才引入 update/rebuild pending operation、后台唤醒、retry/dead-letter、needs-user 和 async late-result fencing。

### 5.4 Storage split

- SQLite：Candidate、Decision、Fact/Revision、evidence links、Artifact/Page revision、BuildRun、current projection、CommandReceipt。
- Filesystem：revision/hash 定址的 Markdown/JSON export 和 render cache。
- 导出文件永不参与 citation/current-head 判定。Stage 1 只保留可选 addressing hook；export command 与 failure/retry 验收进入 Stage 2。

## 6. 上游采用边界

| 上游 | 固定身份 | 建议采用 | 明确拒绝 |
| --- | --- | --- | --- |
| DeepTutor | `HKUDS/DeepTutor@44fa7a1552b88f9d8ce2c22259128a15ae2eb0c8`, Apache-2.0 | 分层、稳定 Entry ID、refs-required、batch preflight、ID-set incremental、preview/apply、可编辑产品行为的独立重实现/测试参考 | L1 JSONL authority、物理 delete/overwrite/reset、process-only run/undo、surface-level L3 refs、源码依赖/复制 |
| WeKnora | `Tencent/WeKnora@fcc4cd6a9f29a94818e481b3a604f44ce51c55e2`, 主项目 MIT + listed third-party | Topic Page/browser/revision UI；optimistic version、atomic snapshot、revert-as-new；durable pending/recovery/dead-letter 的独立重实现/测试参考 | 企业平台、RBAC/Connector、RAG replacement、GraphRAG 默认、Redis active authority、rebuild failure log-and-drain、源码依赖/复制 |

上游采用状态在 Main 接受前均为 proposal；本 Charter 不授予代码复制或依赖引入权限。

## 7. 拟议 Stage 序列

### Stage 1 — Evidence-backed Topic Page Vertical Slice

完成最早端到端价值：

```text
Research Task → KnowledgeDelta Candidate intake → Evidence review
→ accept/reject（edit 形成新 candidate revision）
→ accepted Grounded Fact → deterministic Research Artifact
→ first Topic Page revision → publish-or-return review → transcript drill-down
```

建立 stable family/revision identity、append-only foundation、同步 durable BuildRun、receipt、expected-version review guard、最小 API/UI 和字幕下钻；无 Provider、临时 DB 验证，live migration 不授权。Page edit/history/diff/revert、Fact correction/retire/supersede、filesystem export gate 和 async late-result fencing 不属于 Stage 1 验收。

### Stage 2 — Knowledge Lifecycle, Revalidation and Durable Refresh

加入 source-version revalidation、stale/conflict/viewpoint/temporal scope；交付 Fact correction/retire/supersede、Artifact/Page 后续 revision、Page edit/history/diff/revert；交付 filesystem export command/failure/retry，以及持久 update/rebuild pending operation、restart recovery、retry/dead-letter/needs-user 和 async late-result fencing。新 Evidence 只生成 update candidate，不自动改 current Page。

### Stage 3 — Artifact Retrieval, Reuse and Research Continuation

实现 Artifact retrieval、scope/source-version/currentness gate：`direct reuse | incremental refresh | research seed`；保留开放检索与反例发现。旧 Artifact 不是 verifier，stale/partial 不伪装为直接复用。

### Stage 4 — Personal and Corpus Workspace

实现 Explicit User Memory、Behavioral/Inferred candidate、TopicState/Current Focus、KnowledgeProgress、CorpusModel soft prior、SystemExperienceRecord 与 correction UI。它们不改变 V5-C 产品行为，也不晋升 V5-D Skill。

### Stage 5 — Product Completion, Relations and Evaluation

收口 Topic workspace、bounded inter-page relations、observability、Feedback Event、两条可比较产品路径、restart/duplicate/race/fault、Search/Ask/Research regression，以及经单独授权的 Provider/product evaluation。Graph 只按产品证据 JIT 采用，不是默认目标。

## 8. Version 能力目标

### G1：L1/L2/L3 lineage 与 correction

- Candidate → FactRevision → ArtifactRevision/PageRevision → Evidence 可双向追踪；
- accept/edit/reject/correct/retire/supersede/revert 可审计、幂等、重启稳定；
- forged/cross-task/cross-evidence 引用 fail closed。

### G2：Topic Page 产品闭环

- Topic Page 展示事实、观点差异/演化、冲突、限制、未解决问题和原字幕时间戳；
- 页面 history/diff/review 状态可理解；
- build/update/rebuild 有 durable status 和失败解释。

### G3：Revalidation / Conflict / Reuse

- 新 source version/evidence 可使 Fact/Artifact/Page 进入 stale/conflict/update-candidate；
- direct reuse 只在 scope/currentness/completeness gate 通过时发生；
- partial/stale 走 incremental refresh；scope mismatch 只作 Research Seed。

### G4：Personal/Corpus workspace

- Explicit User Memory 与推测分离；
- Current Focus/Knowledge Progress 可确认和修正；
- Corpus Model 可读、可版本化、只作 soft prior；
- SystemExperienceRecord 有 trace/outcome/environment lineage，不成为 Active Skill。

### G5：可靠性与兼容性

- duplicate、payload mismatch、restart、race、stale writer、fault rollback、export failure、rebuild failure 有机械证据；
- 现有 Evidence/Citation、Fast/Deep/Research contract 和 no-provider baseline 回归；
- 未运行/未证明项保持显式。

## 9. 非目标

- 不修复或重开 V5-A compound-query retrieval limitation，除非后续 JIT 证据证明它阻塞某个 V5-B Stage。
- 不建设企业 Wiki、多租户/RBAC/Connector/通用任务平台。
- 不替换拾流 Retrieval、Fast/Deep 或 Research Runtime。
- 不采用 DeepTutor/WeKnora 数据库、队列、前端或文件布局作为直接依赖。
- 不做 GraphRAG 默认架构、自动知识图谱、外部 Web corpus authority。
- 不自动把 Candidate、user confirmation、CorpusModel 或模型输出提升为事实。
- 不实现 Personalized Answer/Search/Routing 或 Active Skill/Policy promotion。
- 不在未单独授权时运行 Provider、读取凭据或执行 live migration。

## 10. Version 完成条件（由 V5 Main 验收）

1. 五个 Stage 各自有被接受的 Contract、实现报告和 Main acceptance record。
2. L1→L2→L3 lineage、revision/correction/delete semantics 有 schema/API/UI 和故障测试证据。
3. Topic Page vertical path、stale/conflict/update candidate、reuse/refresh/seed、personal/corpus workspace 均有实际产品路径。
4. Corpus Model 无 citation/hard-filter 权威；User inferred state 可拒绝且不会静默复活；Experience 不升级 Skill。
5. durable build/refresh/rebuild 不依赖 process-only state，并能解释 terminal/retry/needs-user。
6. no-provider/default regression 通过；任何 Provider 结果与机械证据分开报告。
7. Program Current State、Program Decision Ledger、Registry 与 Research Log 由 V5 Main 更新。

## 11. 暂停与升级条件

遇到以下材料性问题暂停并请求 V5 Main：

- 需要放宽 L1 authority、candidate-only、CorpusModel soft-prior 或跨版本边界；
- 需要复制上游代码/Prompt/UI、引入正式依赖或出现高风险 License/Data 边界；
- 需要 live migration、Provider、凭据、付费服务或破坏性数据动作；
- Stage 1 无法在不自动 promotion 或不伪造 grounding 的情况下完成 vertical path；
- 需要修改 V5-A 权威语义、修复其 known retrieval limitation 或影响 Fast/Deep/Research contract；
- 需要提前实现 V5-C/V5-D 能力。

## 12. 当前请求

```yaml
charter_status: draft_pending_v5_main_acceptance
stage_sequence_status: proposed
upstream_adoption_status: proposed
stage_1_contract_status: draft_pending_v5_main_acceptance
stage_1_implementation_authorized: false
provider_runs_authorized: false
next_action: limited_v5_main_review_and_stage_1_authorization_decision
```

请求 V5 Main 仅审查版本目标/边界、五 Stage 依赖、上游采用方式、SQLite/filesystem authority 和 Stage 1 Contract；V5-B Session 不自我接受。
