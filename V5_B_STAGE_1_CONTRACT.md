# 拾流 V5-B Stage 1 Contract

```yaml
stage: V5-B Stage 1
title: Evidence-backed Topic Page Vertical Slice
contract_status: draft_pending_v5_main_acceptance
proposal_authority: V5-B execution session
acceptance_authority: V5 main session
created_at: 2026-08-04
starting_commit: b85340540cb92c2e46bfb8619598e7aa987171d4
accepted_v5_a_code_baseline: 04e5c5bbb94311a00f6efafa142908fd7b2b97de
implementation_authorized: false
implementation_started: false
provider_runs_authorized: false
provider_runs_performed: false
live_database_migration_authorized: false
```

> 本 Contract 是待 V5 Main 接受的实施提案。本次启动 assignment 没有实施本 Stage 的 schema/runtime/API/UI/tests。

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

Stage 1 不解决全部 lifecycle/reuse/workspace；它先证明 Candidate 不会自动晋升，Fact/Page 能回到 L1，用户 correction 不抹掉历史，重复/故障/重启不会产生双份资产。

## 2. 用户可见最小结果

经授权实施后，用户应能：

1. 从完成/等待边界上的 V5-A Research Task 打开 Candidate Inbox；
2. 看到 Candidate 来源 Task/Attempt/Artifact、claim、引用、currentness 与 candidate-only 标识；
3. 对一条 `KnowledgeDelta` 执行 Accept、Reject 或 Edit；
4. Accept 前重新验证所有引用仍为 `current`，否则进入 `needs_revalidation`，不生成 Fact；
5. 从已接受 Fact 生成一份 Artifact 和 Topic Page draft；
6. 在 Page 上看到 fact blocks、limitations/unresolved、来源视频与时间戳并下钻字幕；
7. review/publish 或退回 Page；edit/revert 形成新 revision；
8. 重启后看到相同 review、build 和 lineage；重复命令不创建重复对象。

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
| state | currentness/conflict/retire 由 observations/decisions 派生，不改旧 revision body |
| supersede | parent/supersedes revision 明确；Stage 1 只铺设，不实现自动 conflict |

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
- canonical body 在 SQLite；filesystem Markdown/JSON 是按 revision/hash 寻址的派生导出。
- 同一 build input boundary + policy version exact-once；Fact 集合或内容改变创建新 revision。

### 4.5 TopicPage / PageRevision

- `page_id` 稳定；`slug` 在个人 workspace 内唯一且 server-normalized。
- `page_revision_id` 不可变；`version` 单调递增。
- status：`draft / published / archived`；Stage 1 不 hard delete。
- body blocks 引用 ArtifactRevision/FactRevision；保存 limitations/unresolved/currentness projection。
- user-visible change 用 expected version；更新与 superseded revision snapshot 同事务。
- metadata-only export/link/currentness refresh 不伪造内容 version，但必须有 observation/event。
- revert 作为新 revision，`edit_source=revert`，旧历史不改。

### 4.6 KnowledgeBuildRun

最小字段：run ID、kind（artifact_build/page_build/export）、input boundary/hash、status（queued/running/waiting_user/succeeded/failed/cancelled）、attempt、error class/message、output revision、command receipt、created/started/finished time。

Stage 1 可同步执行 deterministic build，不引入通用 worker/Redis/asynq；但 run 状态必须先持久、terminal 结果可重放、crash gap 可由 receipt/transaction 恢复。SSE/polling 不是权威。

## 5. 命令与原子边界

以下命令必须有 task/workspace scope、command ID、payload hash、expected version/revision 和 CommandReceipt：

- `intake_candidate_snapshot`
- `review_candidate_accept`
- `review_candidate_reject`
- `review_candidate_edit`
- `build_research_artifact`
- `build_topic_page`
- `review_topic_page`
- `edit_topic_page`
- `revert_topic_page`
- `export_revision`

### 必须同事务提交

1. Candidate intake + source links + Event + Receipt；
2. Accept Decision + Fact/FactRevision + evidence links + Candidate transition + Event + Receipt；
3. Reject Decision + Candidate transition + Event + Receipt；
4. Edit Decision + child Candidate revision + parent supersede + Event + Receipt；
5. ArtifactRevision + fact links + BuildRun terminal + Event + Receipt；
6. PageRevision/current head + artifact/fact links + BuildRun/review Event + Receipt；
7. Page user edit/revert + superseded snapshot + version guard + Event + Receipt。

filesystem export 不加入 SQLite 事务双主。SQLite 先成为权威；export 命令按 revision/hash 幂等，失败记录在 BuildRun/export observation，可安全重试。

## 6. Read / Update / Delete 语义

### Read

- 默认返回 current head + currentness/conflict projection；
- 可查询完整 candidate/fact/artifact/page revision lineage；
- 每个事实性 block 可下钻 FactRevision → Evidence → transcript；
- cross-task evidence use 不因共享 EvidenceIdentity 而失去来源隔离。

### Update

- Candidate edit、Fact correction、Artifact/Page edit 均创建 revision/new candidate；
- stale writer/version conflict 返回 typed conflict，不做 last-write-wins；
- old async response/build result 在 input head 改变后不得提交 current head。

### Delete

- Candidate：reject/supersede；
- Fact：retire/supersede/tombstone observation；
- Artifact/Page：archive/new revision；
- 本 Stage 没有 hard-delete authority API；测试临时数据库 teardown 不属于产品删除语义。

## 7. API 与 UI 最小范围

### API

- 从 Research Task 查询/intake eligible KnowledgeDelta；
- Candidate Inbox list/detail；
- review accept/reject/edit；
- Fact/Artifact/Page detail 与 lineage/citation drill-down；
- deterministic build/status；
- Page review/edit/history/revert；
- 所有 mutation 复用 server-owned principal、authorization、receipt 和 typed conflict/error。

### UI

在现有 Research 产品附近提供最小入口，而非另建通用 Wiki：

- Candidate-only badge、source task/artifact、claim 和 evidence currentness；
- Accept/Reject/Edit；edited candidate 的 `needs revalidation` 明示；
- Topic Page draft、fact/limitation/unresolved 分区；
- Page review/publish/return；
- revision history/diff/revert；
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
- Fact/links/Decision/Event 不可变；correction/supersede lineage 不覆盖。

### Artifact / Page / BuildRun

- 同一 input boundary exact-once；fact set mismatch fails closed；
- Artifact/Page 只引用 accepted Fact；forged fact/revision 拒绝；
- Page expected-version conflict，失败不留下幽灵 snapshot；
- metadata-only change 不 bump visible version；user edit/revert 创建新 revision；
- build crash/fault rollback/restart/replay；late result 被新 head fence；
- filesystem export temp/replace、hash verify、failure/retry 不改变 SQLite current head。

### Product / compatibility

- 一条完整 no-provider UI/API journey：Task → Candidate → Evidence → Fact → Artifact → Page → review；
- transcript citation drill-down 与 source version currentness；
- restart 后 Inbox/Page/history/status 稳定；
- `/search`、`/ask` Fast/Deep、`/research` 和 default suite affected regression；
- 无 Keychain、Provider、live DB、live content 访问。

## 10. 验收条件

Stage 1 只有在 V5 Main 看到以下证据后才可接受：

1. schema/API/service/UI 只实现本 Contract，未进入后续 Stage；
2. no-provider vertical journey 真实可用；
3. Candidate 不自动 promotion，edited claim 不越过 grounding；
4. Fact/Page 可下钻 L1，currentness fail closed；
5. duplicate/restart/race/fault/export/version conflict 有机械证据；
6. 现有产品回归通过，未修改 live DB；
7. 实现报告列出未证明项和下一 Stage 触发器。

## 11. 明确非目标

- 自动 conflict detection、source-version background revalidation、incremental refresh queue；
- Artifact retrieval/direct reuse/research seed；
- CorpusDelta/UserModelDelta/SystemExperienceDelta promotion；
- Explicit User Memory、Current Focus、KnowledgeProgress、CorpusModel；
- SystemExperienceRecord；
- 完整 graph/Auto-Wiki/enterprise workspace；
- Provider generation/evaluation、live migration；
- V5-C personalization 或 V5-D Active Skill。

Stage 1 可以铺设 lineage/status 字段，但不得声称完成以上能力。

## 12. 实施授权请求

```yaml
contract_status: draft_pending_v5_main_acceptance
implementation_authorized: false
provider_runs_authorized: false
live_database_migration_authorized: false
requested_authority_if_accepted:
  - stage_1_schema_and_temporary_migration_tests
  - stage_1_no_provider_runtime_and_api
  - stage_1_minimal_review_ui
  - stage_1_directed_and_affected_regression_tests
excluded_even_if_accepted:
  - live_database_migration
  - provider_or_paid_service
  - credentials_or_keychain
  - upstream_code_copy_or_new_dependency
  - stage_2_through_stage_5_capabilities
```

请求 V5 Main 接受或修订本 Contract，并在接受后明确授予上述有限 Stage 1 实施权限；在该决定前 V5-B Session 不开始实现。
