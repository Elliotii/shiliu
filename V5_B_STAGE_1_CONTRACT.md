# 拾流 V5-B Stage 1 Contract

```yaml
stage: V5-B Stage 1
title: Evidence-backed Topic Page Vertical Slice
contract_status: accepted_by_v5_main
proposal_authority: V5-B execution session
acceptance_authority: V5 main session
created_at: 2026-08-04
main_acceptance_record: e73ddd2_on_codex_v5_main_message_is_execution_authority
accepted_contract_commit: 4efaed413cb2fd9d2eeabe411da96f5132ce6276
starting_commit: b85340540cb92c2e46bfb8619598e7aa987171d4
accepted_v5_a_code_baseline: 04e5c5bbb94311a00f6efafa142908fd7b2b97de
implementation_authorized: true
implementation_started: true
implementation_status: implemented_pending_v5_main_acceptance
provider_runs_authorized: false
provider_runs_performed: false
live_database_migration_authorized: false
```

> V5 Main 已接受 commit `4efaed4` 的本 Contract 并授权实施；Program 接受记录位于 `codex/v5-main@e73ddd2`，未合并或 cherry-pick 到执行分支。当前实现证据集中在 `V5_B_STAGE_1_IMPLEMENTATION_REPORT.md`，本 Contract 仍不构成 Stage 自我验收。

## 1. Stage 使命

用一条最短、无 Provider、可机械验证的产品路径证明 V5-B 的核心权威链：

```text
V5-A Research Task
→ immutable Candidate Delta snapshot
→ durable Knowledge Candidate Inbox
→ Evidence review
→ user Accept / Reject / Edit-as-new-candidate
→ immutable Grounded Fact revision
→ immutable Research Artifact revision
→ immutable Topic Page revision
→ page user review + transcript citation drill-down
```

Stage 1 不解决完整 lifecycle/reuse/workspace；它先证明 Candidate 不会自动晋升，首个 Fact/Artifact/Page revision 能回到 L1，Candidate edit 不覆盖来源历史，重复/故障/重启不会产生双份资产。

## 2. 用户可见最小结果

当前实现须使用户能够：

1. 从完成/等待边界上的 V5-A Research Task 打开 Candidate Inbox；
2. 看到 Candidate 来源 Task/Attempt/Artifact、claim、引用、currentness 与 candidate-only 标识；
3. 对一条 `KnowledgeDelta` 执行 Accept、Reject 或 Edit；
4. Accept 前重新验证所有引用仍为 `current`，否则进入 `needs_revalidation`，不生成 Fact；
5. 从已接受 Fact 生成一份 Artifact 和 Topic Page draft；
6. 在 Page 上看到 fact blocks、limitations/unresolved、来源视频与时间戳并下钻字幕；
7. 以 expected-version guard review Page，并 publish 或退回；
8. 重启后看到相同 Candidate、Fact、Artifact、首个 Page revision、review 与 build 状态；重复命令不创建重复对象。

## 3. 起始资产与不可冒充项

### 可复用

- schema 10 migration/transaction/trigger 模式；
- V5-A Task/Goal/Attempt/Checkpoint/Event/Result/CommandReceipt/HumanDecision；
- EvidenceIdentity/EvidenceUse/Provenance/Validation 与 `InnerEvidenceService` currentness 重建；
- immutable `ResearchProvisionalArtifact`；
- Stage 5 Candidate Delta snapshot schema `v5-a-stage5-candidate-delta-v1`；
- deterministic candidate hash/snapshot ID/boundary hash 与 Event+Receipt exact-once；
- Research product API/UI、citation presentation、durable trace；
- ArtifactStore temp + replace 写入模式。

### 不能冒充 Stage 1 Baseline

- Candidate Delta Event payload 不是长期可变 review row；
- provisional artifact 不是 V5-B ResearchArtifact；
- V5-A Candidate-only 卡片不是 Inbox lifecycle；
- Transcript summary、candidate text、user approval 或 Page Markdown 本身不是 grounding verifier；
- DeepTutor Markdown Memory / WeKnora WikiPage 不是拾流 authority；
- live database 不用于 Stage 1 实施或测试，除非 Main 另行授权 migration。

## 4. Stage 1 语义模型

字段名可在实现 review 中调整，但身份、唯一性和边界不得合并。

### 4.1 KnowledgeCandidate

| 语义 | 最低要求 |
| --- | --- |
| identity | 稳定 `candidate_id`；唯一 `(source_event_id, candidate_kind, candidate_hash)` |
| source boundary | task/goal/attempt/checkpoint/result/provisional_artifact/source event/snapshot/boundary hash |
| payload | claim/summary、EvidenceIdentity IDs、EvidenceUse IDs、原 candidate payload hash |
| lifecycle | `pending_review / needs_revalidation / accepted / rejected / superseded` |
| revision | edit 不原地改 payload；创建新 candidate revision/child，保留 parent |
| guard | `state_version` 或 expected current revision；CommandReceipt payload hash |
| authority | 永远显示来源是 candidate；只有 successful promotion command 创建 Fact |

Stage 1 只 intake `KnowledgeDelta`。其他三类 delta 可在来源 snapshot 中显示，但不能写入 V5-B long-term state 或 promotion target。

### 4.2 KnowledgeReviewDecision

Append-only，至少保存 decision ID、candidate/revision、kind（accept/reject/edit/page approve/page return）、reason、principal/用户来源、expected state、selected evidence、command ID/receipt、created time。

- Reject 终结该 candidate revision，不删除来源 snapshot。
- Edit 创建新 candidate revision，旧 revision superseded；edited claim 不因用户输入自动成为 GroundedFact。
- Accept 只有在 server-side eligibility/currentness validation 全部通过时，才可与 Fact creation 同事务提交。

### 4.3 GroundedFact / FactRevision

| 对象 | 最低语义 |
| --- | --- |
| `fact_id` | 稳定 lineage/family ID |
| `fact_revision_id` | 不可变 assertion revision；全局唯一 |
| claim | normalized claim + display claim；Stage 1 有界长度 |
| scope | temporal/viewpoint scope 可空但字段存在；不能把缺失推断为 universal |
| origin | source candidate revision、Task、Decision |
| evidence links | 每项绑定 EvidenceIdentity、source EvidenceUse、promotion-time Validation |
| lifecycle hooks | 可空 parent/supersedes/currentness/conflict/retire lineage hook；Stage 1 不提供对应产品命令 |

Stage 1 promotion eligibility：

1. 来源是允许的 V5-A `KnowledgeDelta` item；
2. source task/artifact/boundary 与 snapshot 一致；
3. EvidenceUse 属于 source task/attempt，并指向 candidate 声明的 EvidenceIdentity；
4. 逐条重新 materialize/validate，结果均为 `current`；
5. 引用集合非空且在 Contract 上限内；
6. 未编辑 candidate 使用来源 artifact answer block/summary 的已绑定 claim；
7. edited candidate 只有在实现了同等 server-owned grounded validator 时才能 accept，否则保持 `needs_revalidation`。

用户 approval 不是第 6/7 条的替代品。

### 4.4 ResearchArtifact / ArtifactRevision

- `artifact_id` 是 stable family；`artifact_revision_id` 不可变。
- 保存 topic/scope、fact revision links、answer blocks、limitations、unresolved questions、source task/result/corpus snapshot、content hash。
- 只允许引用已 accepted 且 promotion-time current 的 FactRevision。
- canonical body 在 SQLite；filesystem 未来可保存按 revision/hash 寻址的派生导出，但 Stage 1 不要求 export command 或 failure/retry matrix。
- 同一 build input boundary + policy version exact-once；Stage 1 只创建首个 immutable ArtifactRevision。

### 4.5 TopicPage / PageRevision

- `page_id` 稳定；`slug` 在个人 workspace 内唯一且 server-normalized。
- `page_revision_id` 不可变；首个 revision 的 `version=1`，并保留未来单调递增的 schema/lineage foundation。
- immutable content revision 与 review status projection 分离；Stage 1 review 状态为 `draft / published / returned`，由 append-only PageReviewDecision 派生。
- body blocks 引用 ArtifactRevision/FactRevision；保存 limitations/unresolved/currentness projection。
- publish/return 使用 expected page version/review state guard；失败不改变 immutable revision 或留下孤立 Decision。
- Stage 1 不提供 Page content edit、history/diff/revert、archive 或后续 revision 创建命令；这些进入 Stage 2。

### 4.6 KnowledgeBuildRun

最小字段：run ID、kind（artifact_build/page_build）、input boundary/hash、status（queued/running/succeeded/failed）、attempt、error class/message、output revision、command receipt、created/started/finished time。

Stage 1 同步执行 deterministic build，不引入通用 worker/Redis/asynq；但 run 状态必须先持久、terminal 结果可重放、crash gap 可由 receipt/transaction 恢复。SSE/polling 不是权威。异步 late-result fencing、通用 update/rebuild 和后台恢复属于 Stage 2。

## 5. 命令与原子边界

以下命令必须有 task/workspace scope、command ID、payload hash、expected version/revision 和 CommandReceipt：

- `intake_candidate_snapshot`
- `review_candidate_accept`
- `review_candidate_reject`
- `review_candidate_edit`
- `build_research_artifact`
- `build_topic_page`
- `review_topic_page`

### 必须同事务提交

1. Candidate intake + source links + Event + Receipt；
2. Accept Decision + Fact/FactRevision + evidence links + Candidate transition + Event + Receipt；
3. Reject Decision + Candidate transition + Event + Receipt；
4. Edit Decision + child Candidate revision + parent supersede + Event + Receipt；
5. ArtifactRevision + fact links + BuildRun terminal + Event + Receipt；
6. 首个 PageRevision/current head + artifact/fact links + BuildRun terminal + Event + Receipt；
7. PageReviewDecision + review status projection + expected-version guard + Event + Receipt。

Stage 1 只建立 SQLite authority 与未来 filesystem 派生导出的 addressing hook；不实现或验收 export command、export failure/retry。该产品面进入 Stage 2。

## 6. Read / Update / Delete 语义

### Read

- 默认返回本 Stage 创建的 current head 与 review/currentness projection；
- 可查询本 Stage 创建的 Candidate parent、Fact/Artifact/Page origin lineage；
- 每个事实性 block 可下钻 FactRevision → Evidence → transcript；
- cross-task evidence use 不因共享 EvidenceIdentity 而失去来源隔离。

### Update

- Candidate edit 创建 child candidate；Fact/Artifact/Page 在 Stage 1 没有 correction/edit 产品命令。
- Page publish/return 的 stale expected version/review state 返回 typed conflict，不做 last-write-wins。
- Fact correction/retire/supersede、Artifact/Page subsequent revision 与 async late-result fencing 进入 Stage 2。

### Delete

- Candidate 只支持 reject 或因 Edit 被 child candidate supersede。
- Fact/Artifact/Page 在 Stage 1 没有 delete、retire、supersede、archive 或 correction 产品命令；只保留未来 lineage hook。
- 测试临时数据库 teardown 不属于产品删除语义。

## 7. API 与 UI 最小范围

### API

- 从 Research Task 查询/intake eligible KnowledgeDelta；
- Candidate Inbox list/detail；
- review accept/reject/edit；
- Fact/Artifact/Page detail 与 lineage/citation drill-down；
- deterministic build/status；
- Page publish-or-return review；
- 所有 mutation 复用 server-owned principal、authorization、receipt 和 typed conflict/error。

### UI

在现有 Research 产品附近提供最小入口，而非另建通用 Wiki：

- Candidate-only badge、source task/artifact、claim 和 evidence currentness；
- Accept/Reject/Edit；edited candidate 的 `needs revalidation` 明示；
- Topic Page draft、fact/limitation/unresolved 分区；
- Page review/publish/return；
- 原视频/时间戳 citation drill-down；
- build failed/pending/succeeded 状态，不用无限 spinner 冒充状态。

## 8. Bounds 与安全限制

实现时必须在持久 mutation 前 fail closed：

- 单次 snapshot/item/evidence/fact/page block 数量和字符串/JSON 大小有 server constants；
- 只允许已知 schema/kind/status/edit source；
- slug、ID、hash 和 JSON 使用 canonical validation；
- source event/task/artifact/evidence ownership 与 boundary 全部 server-side 重建；
- client 不能声明 candidate eligibility、Evidence current、Fact accepted 或 Page published；
- no-provider mode 是 Stage 1 唯一授权模式；Provider 字段即使存在也必须被拒绝。

具体常量可在实现 review 中基于既有 V5-A bounds 定义，不允许无限 payload。

## 9. 必须测试的机械证据

### Schema / migration（临时 DB only）

- schema 从 10 到 Stage 1 新版本；只迁移临时 DB；live sentinel 不变；
- FK/integrity；表、索引、unique 和 immutability triggers；
- 旧 V5-A schema/data 可读，V5-A candidate event 不改写。

### Candidate / Evidence / Fact

- snapshot intake exact-once；payload mismatch fail closed；
- 只 intake KnowledgeDelta；其他 delta 不 promotion；
- cross-task/cross-attempt EvidenceUse、伪造 artifact/boundary/hash 拒绝；
- current evidence accept success；stale/missing/invalid/error 不创建 Fact；
- accept atomic fault rollback 后重启只创建一个 Fact；
- reject 幂等且不删除来源；edit 产生 child candidate，不自动 Fact；
- 初始 Fact/links/Decision/Event 不可变；可空 correction/supersede lineage hook 不授予产品命令。

### Artifact / Page / BuildRun

- 同一 input boundary exact-once；fact set mismatch fails closed；
- Artifact/Page 只引用 accepted Fact；forged fact/revision 拒绝；
- Page review expected-version conflict，失败不留下孤立 Decision 或错误 status；
- Artifact/Page 首个 revision 与 BuildRun crash/fault rollback/restart/replay；
- duplicate build/review command exact-once；payload mismatch fail closed。

### Product / compatibility

- 一条完整 no-provider UI/API journey：Task → Candidate → Evidence → Fact → Artifact → Page → review；
- transcript citation drill-down 与 source version currentness；
- restart 后 Inbox、首个 Page revision、review 与 BuildRun status 稳定；
- `/search`、`/ask` Fast/Deep、`/research` 和 default suite affected regression；
- 无 Keychain、Provider、live DB、live content 访问。

## 10. 验收条件

Stage 1 只有在 V5 Main 看到以下证据后才可接受：

1. schema/API/service/UI 只实现本 Contract，未进入后续 Stage；
2. no-provider vertical journey 真实可用；
3. Candidate 不自动 promotion，edited claim 不越过 grounding；
4. Fact/Page 可下钻 L1，currentness fail closed；
5. duplicate/restart/fault rollback 与 Page review expected-version conflict 有机械证据；
6. 现有产品回归通过，未修改 live DB；
7. 实现报告列出未证明项和下一 Stage 触发器。

## 11. 明确非目标

- 自动 conflict detection、source-version background revalidation、incremental refresh queue；
- Fact correction/retire/supersede 产品命令（schema/lineage hook 除外）；
- Page content edit、history/diff/revert、archive 与后续 revision 产品命令；
- filesystem export command 及 export failure/retry 验收矩阵；
- async late-result race/fencing、通用 update/rebuild 与后台恢复；
- Artifact retrieval/direct reuse/research seed；
- CorpusDelta/UserModelDelta/SystemExperienceDelta promotion；
- Explicit User Memory、Current Focus、KnowledgeProgress、CorpusModel；
- SystemExperienceRecord；
- 完整 graph/Auto-Wiki/enterprise workspace；
- Provider generation/evaluation、live migration；
- V5-C personalization 或 V5-D Active Skill。

Stage 1 可以铺设 lineage/status 字段，但不得声称完成以上能力。

## 12. 实现验收请求

```yaml
contract_status: accepted_by_v5_main
implementation_authorized: true
implementation_status: implemented_pending_v5_main_acceptance
provider_runs_authorized: false
live_database_migration_authorized: false
implemented_authority:
  - stage_1_schema_and_temporary_migration_tests
  - stage_1_no_provider_runtime_and_api
  - stage_1_minimal_review_ui
  - stage_1_directed_affected_and_default_regression_tests
still_excluded:
  - live_database_migration
  - provider_or_paid_service
  - credentials_or_keychain
  - upstream_code_copy_or_new_dependency
  - stage_2_through_stage_5_capabilities
```

请求 V5 Main 对照本已接受 Contract 审查 `V5_B_STAGE_1_IMPLEMENTATION_REPORT.md` 和提交内容，接受 Stage 1 或要求有界修正；不请求 Stage 2–5、Provider 或 live migration 授权。
