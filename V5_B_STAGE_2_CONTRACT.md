# 拾流 V5-B Stage 2 Contract

```yaml
stage: V5-B Stage 2
title: Knowledge Lifecycle, Revalidation and Durable Refresh
contract_status: accepted_by_v5_main
proposal_authority: V5-B execution session
acceptance_authority: V5 main session
created_at: 2026-08-04
branch: codex/v5-b
accepted_stage_1_commit: abe002ab95025b38565464e69ca8b3abe651f1ae
stage_1_main_acceptance_record: 2f4dabf_on_codex_v5_main_not_cherry_picked
schema_baseline: 11
contract_preparation_authorized: true
contract_commit: a931e2863f3ae245205c1f64bad7e45d25f03225
main_acceptance_and_authorization_record: c6317a5_on_codex_v5_main_not_cherry_picked
implementation_authorized: true
implementation_started: true
implementation_status: implemented_pending_v5_main_acceptance
schema_target: 12
provider_runs_authorized: bounded_optional_up_to_usd_2_not_used
live_database_migration_authorized: false
```

> V5 Main 已在 `codex/v5-main@c6317a5` 接受本 Contract 的 target、authority boundary、dependency order 与 Gates A–E，并授权在 `codex/v5-b` 实施；该 Program-only commit 未合并或 cherry-pick。本文件不构成 V5-B 自我验收，实施仍须 Main 审查。

## 1. Stage 使命与用户结果

Stage 2 让已经接受的知识在 Evidence 变化后仍可理解、可修正、可恢复：

```text
new/changed Evidence or explicit revalidation
→ append-only currentness observation
→ visible current / stale / potential-conflict projection
→ durable update candidate（never auto-applied）
→ user review / correct / retire / supersede
→ new immutable FactRevision
→ durable Artifact/Page refresh operation
→ new immutable ArtifactRevision + PageRevision draft
→ Page review/publish
→ preserved history/diff/revert and explainable terminal state
```

核心结果：旧的 published Page 可以继续存在，但必须显式显示 stale/conflict/update-available；任何新 Evidence、后台结果或用户 edit 都不能静默改写 Fact 或 published Page。

## 2. 起始 Authority 与冻结边界

### 必须保持

1. Stage 1 的 Candidate-only、L1 Evidence/Event authority、Fact/Artifact/Page stable family + immutable revision、exact links、CommandReceipt/payload hash、expected-version guard 全部继续有效。
2. 原字幕/ASR source artifact 是事实根；revalidation 追加 observation，不改旧 EvidenceIdentity、EvidenceUse、Validation、FactRevision 或 PageRevision。
3. SQLite 继续是 identity/state/lineage/canonical body/current-head/review/operation/receipt 的唯一权威。
4. 用户 correction 决定“我要修正/退役/选择哪一版”，不能单独证明新外部事实；新或修改后的 claim 必须经过 server-owned grounding eligibility。
5. Artifact/Page currentness 是由其固定 FactRevision links 推导的 projection；旧 revision 的正文和链接永不回写。
6. Stage 2 refresh 只更新已知 Fact/Artifact/Page lineage，不实现 Artifact retrieval、direct reuse、incremental-reuse decision 或 Research Seed；这些属于 Stage 3。

### 已接受上游证据

- DeepTutor fixed commit：stable entry ID、refs-required preflight、correction 产品形态、ID-set incremental/checkpoint、SQLite-authority/derived-export 映射的 reference-only 证据。
- WeKnora fixed commit：optimistic version、atomic revision、revert-as-new、durable pending intent、stale claim recovery、bounded retry/dead letter、pending/issues/history/diff UI 的 reference-only 证据。
- 现有报告已经解决本 Contract 的具体语义；本轮不追加 upstream checkout、依赖或研究报告。

## 3. Core 语义模型

字段/表名可在实施 review 中微调，但以下 identity、状态和原子边界不得弱化。

### 3.1 RevalidationObservation 与 currentness projection

每次 revalidation 必须保存 append-only observation：

- target FactRevision 与逐项 EvidenceIdentity/EvidenceUse；
- expected/observed SourceVersion、policy version、authority mode；
- outcome：`current / stale / missing / invalid / error`；
- trigger：source change、explicit user request、update operation、bounded recovery；
- input hash、CommandReceipt/Event、observed time。

同一 FactRevision + evidence set + observed source-version boundary + policy exact-once。重复 observation 可回放 receipt；payload mismatch fail closed。

FactRevision 的 derived knowledge state：

- `current`：所有 required evidence 最新 observation 均 current；
- `stale`：至少一项 stale/missing/invalid/error；这表示 grounding 不再当前，不等于 claim 已被证明为 false；
- `potential_conflict`：存在待用户审查的冲突 candidate；
- `conflicted`：存在 append-only confirmed ConflictObservation/Decision；
- `retired` 或 `superseded`：来自显式 lifecycle Decision，不由 currentness 自动产生。

ArtifactRevision/PageRevision 若链接任一 stale/conflicted/retired/superseded FactRevision，projection 必须显示 affected reason、Fact IDs、latest observation 和 update availability；不得修改旧 revision body。

### 3.2 Temporal / viewpoint / conflict

- temporal/viewpoint scope 是 FactRevision 内容；空值表示 `unknown`，不得解释为 universal。
- scope/claim/evidence link 任何变化都创建新 FactRevision。
- 不同时间或不同 viewpoint 的两个 current-grounded Fact 可以并存；scope 不重叠本身不是 conflict。
- `conflicted` 至少要求两个可追踪 FactRevision、各自 current-grounded Evidence、scope overlap 判定和显式 conflict relation observation。
- 自由文本相似或新 Evidence 出现不能自动证明 contradiction。没有 server-owned deterministic/registered evaluator 时只创建 `potential_conflict` candidate；用户可确认“在个人知识组织中视为冲突/不同 scope/可并存”，但不能借此授予某一 claim 外部事实真值。

### 3.3 KnowledgeUpdateCandidate

Stage 2 建立 durable update candidate，建议 kind：

- `source_rebind`：同一 claim 有新的 current EvidenceIdentity/Use；
- `new_evidence`：新的 V5-A KnowledgeDelta 或受支持 grounded source；
- `user_correction`：用户提出 claim/scope 变化；
- `potential_conflict`：两条可追踪 revision 可能冲突；
- `retire`：用户请求停止把该 Fact 作为 current knowledge。

Candidate 必须保存 source trigger/observation/Fact head、proposed claim/scope/evidence、affected Artifact/Page、validator status、state version 与 receipt。

- 新 Evidence/revalidation 只能创建 Candidate 或 projection，不自动移动 Fact/Artifact/Page head。
- edited claim 若没有 server-owned grounded validator，保持 `needs_revalidation`；Stage 1 的限制不因 Stage 2 用户 approval 被绕过。
- exact claim rebind 或来自已允许 KnowledgeDelta 的 correction，可以在当前 Evidence validation 全部通过后进入 reviewable eligibility。
- Accept/Reject/Edit 保留 parent lineage；Accept 仍需 expected candidate version。

### 3.4 Fact lifecycle

Core commands：`propose_fact_correction`、`review_fact_update`、`retire_fact`、`supersede_fact`。

- Correction/supersede 接受后，在同一 Fact family 创建单调 revision、绑定新的 current Evidence links、保存 parent/supersedes ID，并以 expected head CAS 更新 family projection。
- 旧 FactRevision 永久可读；旧 Evidence/Decision/observation 不删除。
- `retire_fact` 追加 lifecycle Decision 并更新 family projection；不物理删除 Fact/Revision/links，也不伪造替代 Fact。
- supersede 必须指向同一 task/workspace 内已通过 eligibility 的 new FactRevision；cross-task/cross-family merge 不是 core。
- correction/retire/supersede 必须产生受影响 Artifact/Page 列表和 durable refresh intent，但 published Page 在后续明确 publish 前保持原 revision并显示 stale/update-available。

### 3.5 Artifact / Page revisions and review

- Artifact refresh 只由 accepted current FactRevision set 构建新的 immutable ArtifactRevision；input fact set/source boundary/policy hash exact-once。
- Page family 至少区分 monotonic latest working revision 与 published revision。Stage 1 published Page migration 后不得丢失 published pointer；returned/draft Page 不伪造 published pointer。
- Page edit 创建新 draft PageRevision；Fact blocks 必须继续引用 eligible FactRevision。用户可以修改 title、顺序、limitations、unresolved、明确 user annotation 等 presentation fields，但不能把自由文本直接写成 grounded Fact block。
- history 读取 immutable revisions/Decision/editor/source/time；diff 是两个 canonical revision bodies 的 derived projection，不是 authority。
- revert 把选定历史内容复制成 `max(version)+1` 的新 draft revision，并保存 `revert_of_revision_id`；不得把 head/version 倒退或删除中间历史。
- publish/return 继续使用 expected latest version/review state；只有显式 publish 才更新 published pointer。

### 3.6 DurableUpdateOperation

Stage 2 可扩展 Stage 1 BuildRun或建立单一 SQLite operation repository；不得建设通用 queue platform。

每个 operation 至少保存：

- operation ID/kind/target family、dedup key、canonical input/hash；
- expected Fact/Artifact/Page head/version/source boundary；
- `pending / running / retry_wait / succeeded / needs_user / dead_letter / superseded / cancelled`；
- attempt/max attempts、error class/code/detail、next attempt time；
- claimant/lease/claim generation、created/claimed/updated/finished time；
- output revision、Event、CommandReceipt。

Core reliability：

1. SQLite intent 必须先于任何 ephemeral wakeup 持久；trigger/thread/polling 丢失不丢 operation。
2. dedup key + receipt 折叠 duplicate enqueue；相同 command/payload replay，相同 command/不同 payload conflict。
3. recovery 只扫描本产品 operation table：恢复 pending/retry_wait 和过期 running claim；不引入 Redis/asynq/多租户 lane/general scheduler。
4. retry 仅针对明确 transient class，max attempts 是小的 server constant；每次 error/next attempt 持久。permanent data/semantic blocker 进入 `needs_user`，耗尽 transient retry 进入 `dead_letter`，不得 log-and-drain 为 success。
5. worker finalize 必须同时验证 operation/claim generation、owner lease、expected input/head/version/source boundary。任何 fence 变化拒绝 late result，不创建 current revision；operation 进入 `superseded` 并追加 reason Event。
6. output revision + links + target working head + operation terminal state + Event/Receipt 同事务提交。crash/fault 不留下 orphan revision、错误 head 或假 success。
7. recovery 可以是 application startup + explicit bounded tick；常驻 background worker、SSE、rich polling 都不是 core authority。

### 3.7 SQLite / filesystem export boundary

- SQLite canonical commit 成功即定义知识/页面状态；filesystem file 不参与 head、currentness、citation、review 或 operation success 判定。
- 导出只能按 revision ID + content hash 生成 immutable Markdown/JSON，用 temp + fsync/replace；current pointer/cache 可重建。
- filesystem export command、retry UI 和 failure matrix **不是 Stage 2 core acceptance gate**，除非实施证明用户 lifecycle path 必须下载/打开该文件。
- 若本 Stage 顺带实现 export：它必须是独立可观察 operation；失败不回滚 SQLite revision、不阻止 Page publish、不删除历史，并可按同一 revision/hash安全重试。

## 4. Dependency-ordered implementation core

1. **Observation foundation**：temp-DB migration、append-only revalidation/conflict/lifecycle records、Fact/Page head projections。
2. **Visible staleness**：显式/source-change revalidation → Fact/Artifact/Page affected projection；不创建新 revision。
3. **Update review**：durable update Candidate → user review → correction/retire/supersede Fact revision/head CAS。
4. **Revision workspace**：Artifact refresh、Page edit/history/diff/revert、draft/published separation。
5. **Durable operation**：intent/dedup/claim/recovery/retry/dead-letter/needs-user/late fence。
6. **Minimal product closure**：changed Evidence → stale visible → reviewed update → new Fact/Artifact/Page draft → explicit publish，外加 affected/default regression。

不得先建设抽象 worker/queue/export/graph platform再寻找产品路径。

## 5. Commands 与事务边界

所有 mutation 使用 server-owned principal、bounded payload、CommandReceipt/payload hash、expected version/head；建议 command surface：

- `request_fact_revalidation`
- `review_update_candidate`
- `correct_fact` / `retire_fact` / `supersede_fact`
- `request_artifact_refresh` / `request_page_refresh`
- `edit_page` / `revert_page` / `review_page_revision`
- `retry_operation` / `resolve_operation_needs_user` / `cancel_operation`

必须同事务提交：

1. observation set + knowledge-state projection + affected/update candidate + Event/Receipt；
2. accepted update Decision + new FactRevision/evidence links + family head/lifecycle + refresh intent + Event/Receipt；
3. retire Decision + family projection + affected refresh intent + Event/Receipt；
4. Page edit/revert new revision + latest working head CAS + Decision/Event/Receipt；
5. operation terminal output + Artifact/Page revision/links + working head + Event/Receipt；
6. Page publish/return Decision + expected-version guard + published/review projection + Event/Receipt。

## 6. Minimal API / UI

### API

- 查询 Fact/Artifact/Page currentness、affected reasons、revision history和 update candidates；
- request/replay revalidation；
- review correction/retire/supersede；
- request/inspect/retry bounded refresh operation；
- Page edit/history/diff/revert/publish-or-return；
- transcript citation drill-down保持 Stage 1 精度。

### UI

- Fact/Page badge：current、stale、potential conflict、conflicted、retired、update available；
- stale/conflict detail 显示 source version、observation reason、affected Fact/Page，不只显示泛化 warning；
- update review 对比 old/new claim、scope、Evidence与影响面；
- Page current/published/draft、history/diff/revert和 operation timeline 可理解；
- `needs_user/dead_letter/superseded` 显示 error、attempt、blocked reason和安全下一步；无限 spinner、Redis active flag或进程布尔值不得冒充状态。

## 7. Core acceptance gates

### Gate A — Revalidation authority

- source-version change追加 observation并使 linked Fact/Artifact/Page visibly stale；旧 L1/L2/L3 records不变；
- duplicate/payload mismatch/cross-task/source drift/fault rollback mechanical tests；
- stale 不自动变 false，potential conflict 不自动变 confirmed conflict。

### Gate B — User lifecycle

- reviewed update创建一个新 FactRevision并原子移动 expected head；old revision/history可读；
- correction/scope change需要 current grounded Evidence；unsupported edited claim保持 needs_revalidation；
- retire/supersede不物理删除；stale expected head conflict且不留孤儿 Decision/revision；
- update Candidate 从不自动改变 published Page。

### Gate C — Page revision product

- new Artifact/Page revisions回到 accepted FactRevision/L1；
- Page edit atomically creates monotonic draft revision；history/diff正确；revert creates a fresh revision；
- published pointer只在显式 review publish后移动；失败/return不破坏旧 published Page。

### Gate D — Durable refresh and fencing

- durable intent before wakeup、restart recovery、dedup、bounded retry、dead-letter/needs-user均有 temp-DB evidence；
- expired claim recovery与late/stale result fence测试；旧 worker/result不能提交 revision/head；
- rebuild failure不得 log-and-drain success；fault gaps不留orphan output或错误 terminal projection。

### Gate E — Compatibility and non-actions

- 一条完整 no-provider/temp-DB public API/UI journey和 restart projection；
- Stage 1 directed/affected、`/research`、`/search`、`/ask`、default filtered suite回归；
- live DB hash/contents不变；无 Provider/credential/Keychain/upstream copy/new dependency。

## 8. Required mechanical tests

- schema migration/reentry/FK/unique/immutability/CAS（temporary DB only）；
- current→stale→current revalidation observations，missing/invalid/error，duplicate和fault；
- temporal/viewpoint overlap/non-overlap/unknown 与 potential/confirmed conflict；
- correction/retire/supersede exact-once、cross-task forging、stale head、rollback/restart；
- Artifact/Page affected projection和no-auto-mutation；
- Page edit/history/diff/revert-as-new/publish guard与revision retention；
- operation intent/dedup/claim/lease/recovery/retry/backoff/dead-letter/needs-user/cancel；
- operation expected-input/head/source fence、late result rejection、concurrent claim/duplicate trigger；
- full changed-Evidence lifecycle through public API/minimal UI；
- no-provider/default affected regression和live sentinel/hash non-action。

## 9. Optional / non-gating foundations

以下可在 core 完成后实现，但不阻塞 Stage 2 acceptance：

- richer filesystem download UI和batch export；Stage 2 已交付 revision-ID/content-hash addressed Markdown/JSON export、可观察失败与同 revision 安全重试；
- 常驻 background wakeup/SSE；startup/explicit bounded recovery已足够；
- rich semantic/word diff；deterministic line/block diff已足够；
- automatic semantic conflict suggestion或 Provider validator；没有时保持 potential/needs_revalidation；
- Page archive/retention policy；本 Stage禁止physical delete history；
- batch revalidation sweep beyond bounded affected lineage。

任何 optional foundation 都不得扩大为 general queue、Wiki/RAG/graph platform。

## 10. Explicit exclusions

- Artifact retrieval/direct reuse/incremental-refresh-vs-research-seed decision（Stage 3）；
- Explicit User Memory、behavioral/inferred candidate、Current Focus、KnowledgeProgress、CorpusModel、SystemExperienceRecord（Stage 4）；
- inter-page relations/graph、product/provider evaluation closure（Stage 5）；
- V5-C personalized answer/search/routing/proactive behavior；
- V5-D Active Skill/Policy promotion；
- enterprise multi-tenancy/RBAC/Connector、general RAG、GraphRAG default；
- live DB migration/content mutation、Provider/paid service、credentials/Keychain，除非 Main另行明确授权；
- upstream source/test/UI copy、direct/new dependency；
- push/merge/tag或self-acceptance。

## 11. 已采用的实施选择

实施在不改变 Gates A–E 的前提下采用：

- 建立 Stage 2 专用 SQLite `research_knowledge_update_operations`，不扩张为通用队列；
- explicit bounded recovery + expired-claim recovery，small bounded retry，常驻 worker 非 core；
- deterministic unified line diff；
- exact source-rebind/current Evidence validator；claim 改写若不能被当前 Evidence quote deterministic 支持则保持 `needs_revalidation`；
- immutable observations/decisions/revisions 加受事务保护的 Fact/Page head projection；
- revision-ID/content-hash addressed Markdown/JSON derived export，SQLite commit 与 publish 不依赖 export 成功。

若需要 Provider validator、live migration、general worker平台、放宽 Evidence authority或改变跨版本边界，必须停止并升级 Main。

## 12. 实施提交状态

```yaml
stage_1_status: accepted_by_v5_main
stage_2_contract_status: accepted_by_v5_main_at_c6317a5
stage_2_implementation_authorized: true
stage_2_implementation_status: implemented_pending_v5_main_acceptance
provider_runs_performed: false
live_database_migration_authorized: false
requested_review:
  - gates_a_through_e_implementation
  - sqlite_authority_and_derived_export
  - compatibility_and_honest_limits
decision_requested: limited_v5_main_stage_2_acceptance_or_bounded_return
```

实施证据集中在 `V5_B_STAGE_2_IMPLEMENTATION_REPORT.md`。请求 V5 Main 对已接受 Contract 做一次 limited Stage 2 acceptance review；V5-B Session 不自我接受，也不启动 Stage 3。
