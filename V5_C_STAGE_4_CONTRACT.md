# 拾流 V5-C Stage 4 Contract

```yaml
stage: V5-C Stage 4
title: Knowledge Progress and Bounded Assistance
contract_status: proposed_pending_v5_main_acceptance
proposal_authority: V5-C Version Session
acceptance_authority: V5 Main Session
created_at: 2026-08-10
execution_branch: codex/v5-c
accepted_stage_3_execution_head: 68e704e56bc0ba99de0506e9e2b93176b5c978a9
main_stage_3_acceptance_authority: ba167b3c9b9309df244b3770b347e22698c2187c
main_stage_3_decision: V5D-20260810-028
schema_source_at_contract: 14
implementation_authorized: false
implementation_started: false
provider_runs_authorized: false
live_database_access_authorized: false
stage_5_entered: false
self_acceptance: forbidden
```

> 本 Contract 只冻结一个 existing Research Task/Workspace surface 上、request-time 的 “Knowledge Progress &
> bounded assistance” panel。V5 Main 明确接受并授权前不得实施；V5-C Session 不能接受自己的 Contract 或
> Stage。

## 1. Stage 使命与唯一纵切

Stage 4 把四类能力收敛到一个 pull-only panel，而不是建立四个平台：

```text
task-scoped explicit/evidence-backed progress ────────────────┐
existing Fact / Artifact / Page currentness ─────────────────┤
explicit baseline + current frozen taxonomy snapshots ───────┤
confirmed Current Focus + current transcript/ASR Evidence ───┤
                                                               ↓
                  one read-only bounded projection
                                                               ↓
 Progress summary + Staleness + Collection Delta + at most one Radar candidate
      explain / off / dismiss control / append-only correction and rollback
```

首片只允许读取一个显式 Research Task、当前 principal、可选的两个用户显式选择的 taxonomy snapshot ID 和
existing Workspace state。它不轮询、不定时执行、不创建 notification，不自动写 Workspace、Page、Fact、
Profile、Prompt、Route 或 Skill。

Panel 是既有 Research/Workspace 的 additive response/surface。一次 response 最多显示：5 条 progress、2 条
staleness、3 条 collection delta 和 1 条 Early Project Radar candidate；每类稳定排序并返回被截断数量。
“低频”由 user-pull + 每次最多一条 Radar 实现，不建立时间调度或 frequency store。

## 2. Authority catalog

| Input | 可接受 authority | Stage 4 consumer/effect | 绝对禁止 |
| --- | --- | --- | --- |
| Explicit progress | current principal 的 `progress_observation:user_authored|user_confirmed/current` | 只显示用户明确自述的 topic/state | 从 watch/search/collection 推断掌握 |
| Activity observation | task-scoped `progress_observation:evidence_backed_observation/current` + current source refs | 显示 watched/searched/collected/transcript/research activity observation | 升级为 learned/understood/mastered/familiar |
| Staleness | existing current Fact state、Artifact/Page fact lineage 与 currentness/state version | 显示 bounded stale/conflict/revalidation card | 自动 revalidate、改 Fact/Page 或宣称旧结论为假 |
| Collection Delta | same-scope immutable baseline/current taxonomy snapshots，且 current snapshot 与 read-only current preview 相符 | 显示 added/removed/changed observation | 把收藏变化当用户兴趣、掌握或事实 |
| Early Project Radar | confirmed Current Focus + Collection Delta 中 added item 的 current transcript/ASR Evidence | 最多一条“可检查”candidate | 心理兴趣推断、标题/简介/summary 单独触发、自动 Research |
| Dismiss control | 用户显式写入的 exact `progress_observation` control revision | 抑制同一 candidate boundary 或按 expiry 恢复 | 自动创建、物理删除、跨 boundary 永久屏蔽 |

Workspace revision 继续是唯一 durable user-state authority；Stage 4 projection 是可重建的只读 view，不是
Citation、Verifier、Fact 或 Profile。Corpus snapshot、title/description/summary 只能证明 collection/navigation
boundary，不能证明 Radar 内容；Radar 必须额外绑定 current transcript/ASR Evidence identity/hash。

## 3. Knowledge Progress：mastery 与 observation 分离

### 3.1 用户自述 mastery

首片承认以下 self-assessment states：

```text
learned | understood | mastered | familiar
```

它们只有在 payload exact topic/state、`user_asserted=true`、零 inferred source refs、当前 principal、authority 为
`user_authored|user_confirmed` 且 effective status 为 `current` 时才进入 mastery display。现有 validator 已承认
learned/understood/familiar；实现若获授权，只把 `mastered` 加入同一个 `PROGRESS_STATES` /
`SELF_ASSESSMENT_STATES` 白名单和现有错误文案，不改 schema/table/index/API type。

### 3.2 Evidence-linked observation

watch/search/collection/transcript presence/research activity 只能用 evidence-backed progress observation 展示。
consumer 白名单为：

```yaml
observation_type:
  - watched
  - searched
  - collected
  - transcript_available
  - research_activity
  - fact_status
non_mastery_state:
  - discovered
  - reviewed
  - researched
  - supported
  - unresolved
  - conflicted
  - stale
```

这类记录必须有可重验 source refs、authority=`evidence_backed_observation`、task/principal match；即使多次出现，
也永远不转换成 learned/understood/mastered/familiar。unknown payload、cross-task ref、content/source hash drift、
conflict 或 expiry 均不猜测，返回该 lane 的 fail-closed explanation。

## 4. Staleness 与 Collection Delta

### 4.1 Staleness

Projection 直接只读查询 existing `research_knowledge_fact_states` 与当前 Fact/Artifact/Page lineage；不得调用会
补写 initial heads 的 lifecycle projection。只有 persisted currentness 为 `stale|potential_conflict|conflicted`、
或 current revision/lifecycle fence 不满足时才形成 card。每张 card 带：Task、Fact current revision、state
version/currentness、affected Artifact/Page revision/content hash、更新时间与 candidate boundary hash。

Card 只说明“需要检查/重验”，不能成为 Verifier 结论，不调用 revalidation，不创建 update operation，不改
published Page 或 current Fact。

### 4.2 Collection Delta

用户必须显式给出 `baseline_snapshot_id` 与 `current_snapshot_id`。Projection 必须重验：

1. 两个 snapshot 均存在、immutable row/card JSON/hash 可重建；
2. selected source IDs 完全相同，避免把 scope change 当 collection change；
3. 以 current snapshot 的 source IDs 执行 read-only taxonomy `preview`，其 schema/source/card hash 与 frozen
   current snapshot 完全相同；不调用 `freeze`；
4. added/removed/changed 只按 content key + stored/discovery/card hash 比较，稳定排序并有界截断；
5. snapshot/card malformed、scope mismatch、current preview drift 或无法读取 summary artifact 时 fail closed，
   不退化为“可能新增”。

Delta 是 collection observation，不自动改 Topic Page、Fact、Profile、Prompt、Router、Skill、Corpus prior 或
search filter。removed 不等于用户不感兴趣，added 不等于用户想学，changed 不等于事实变化。

## 5. Bounded Early Project Radar

Radar 不是独立扫描器；它只从本次已验证的 `added` delta 中选最多一条 candidate，并同时要求：

- 恰好一个 current principal 的 confirmed/user-authored Current Focus；multiple/expired/candidate/malformed focus
  返回 Radar baseline；
- added item 有 current raw transcript/ASR Evidence 与 current revision/index identity；标题、简介、summary 或
  taxonomy membership 单独不够；
- Focus topic 与 current Evidence excerpt 仅做 deterministic NFKC/casefold exact phrase/token overlap；不使用
  embedding、LLM、alias 扩展、history aggregation 或心理兴趣推断；
- candidate explanation 包含 focus record/revision/content hash、snapshot pair/hash、content key、video/current
  evidence identity/hash、matched term、candidate hash 和 `execution_authority=false`；
- tie 按 baseline snapshot ordinal/content key 稳定排序；无法证明 relevance 时无 Radar card。

CTA 只能聚焦 existing transcript/Research control；不自动创建或运行 Research、不调用 Provider、不改 route/
budget，也不启动 background task。

## 6. Explain、控制与 no-resurrection

整个 panel 支持 request/session `assistance_enabled=false`；关闭后不写 DB并保持 Stage 1–3 和非个性化 consumer
baseline。每个 card 显示 kind、why-now、source refs、old/new boundary、currentness、candidate/context hash、
authority false fields 与 fallback reason。

Projected card 默认不持久化。session dismiss 只隐藏当前页面 session；若用户选择 durable dismiss，复用
existing Workspace create/decision endpoint，显式写一个 exact control record：

```yaml
record_kind: progress_observation
semantic_key: assistance.control.<candidate_id>
derived_authority: user_authored_or_user_confirmed
payload:
  topic: <exact focus/topic>
  state: reviewed
  user_asserted: true
  control: dismiss
  dismissed: true
  candidate_id: <deterministic id>
  candidate_kind: staleness | collection_delta | early_project_radar
  boundary_hash: <exact candidate boundary>
source_refs: <exact fact/artifact or taxonomy snapshot refs>
```

Projection 只对白名单 exact payload、principal、content/source hash 和 matching candidate boundary 应用 control：

- current/unexpired dismiss control 抑制该 exact boundary；optional expiry 到期后可重新显示，并解释 expiry；
- tombstoned dismiss history 继续阻止同一 old boundary 被自动重新创建；恢复显示必须由用户 `correct` 成
  `dismissed=false` 的新 revision；
- correction、temporary expiry、tombstone、restore-as-new 都复用 existing append-only decision；不得删除或
  覆盖历史；
- 新 source/snapshot/focus boundary 产生新 candidate ID，不被旧 control 静默屏蔽；若要继续 dismiss，用户须
  对新 candidate 明确操作；
- exact duplicate/restart 返回同一 candidate/context hash；现有 same-boundary semantic dedup/no-resurrection
  继续生效。

durable dismiss 是唯一由本 panel 发起的可选写入，必须有用户明确点击；projection 本身、page load、refresh、
off 和 session dismiss 均为零写入。该 exact control 不计入 mastery/progress，不获得其他 product authority。

## 7. Paired acceptance matrix

| Case | 必要结果 |
| --- | --- |
| cold baseline | 无 progress/delta/stale/radar 输入时 empty baseline；零写入 |
| explicit progress | user-asserted learned/understood/mastered/familiar 可见且 explanation 完整 |
| watched-not-learned | watched/searched/collected 只显示 observation；mastery 集合不变 |
| valid staleness | current persisted stale/conflict boundary 形成最多两张 revalidation candidate；不改 Fact/Page |
| valid collection delta | same-scope current snapshot pair 形成 bounded added/removed/changed observation |
| stale/drift | snapshot preview、source ref、Fact/Artifact/Page、content hash drift deterministic fail closed |
| radar treatment | confirmed Focus + added item + current L1 Evidence 只形成一条 candidate |
| no-focus/candidate/unrelated | Radar baseline；progress/staleness lanes 不借此升级 authority |
| dismiss/expiry | session dismiss 零写；durable exact control only；expiry 按明确时间恢复 |
| tombstone/no-resurrection | old boundary 不复活；restore 必须 append `dismissed=false` 新 revision |
| disabled | 整个 assistance panel baseline；零 Workspace write |
| restart/dedup | card order/IDs/context hash 稳定，无 duplicate authority/revision |
| non-interference | Stage 1 answer、Stage 2 Search、Stage 3 routing、Ask/Research/ArtifactRoute/ASR/Citation/Verifier 不变 |

所有 fixture/temp DB 只证明 mechanics，不证明 live 用户掌握、兴趣或帮助收益。

## 8. Lean implementation budget

若 Main 接受并授权，默认 implementation budget：

```yaml
schema_table_index_migration_delta: 0
new_record_kind_or_authority_store: 0
new_endpoint_types: 0
new_dependencies: 0
new_prompt_or_provider_calls: 0
new_background_worker_scheduler_notification_agent_loop: 0
new_generic_inbox_rules_policy_telemetry_eval_platform: 0
read_only_knowledge_assistance_projection_adapters_max: 1
existing_progress_self_assessment_enum_additions: [mastered]
```

优先把 projection 作为 existing task Workspace GET 的 additive context，复用 Research surface 和 existing
Workspace create/decision。不得修改 Search/Ask/Research/ArtifactRoute/ASR execution contracts，也不得让
high-level read path 产生 initial-head write。

若 implementation 发现 immutable snapshot/current Evidence identity 或 exact durable dismiss 无法在上述零
schema预算内机械维持，必须返回 Main 给出具体 failing invariant 和最窄增量；不得预建通用 inbox、scheduler、
notification、rules、telemetry 或 Agent platform。

## 9. Material JIT 与测试纪律

本地 accepted evidence 已覆盖 Contract 的材料问题：

- `personal_workspace.py` / V5-B Stage 4 tests：typed progress、user assertion、watched-not-learned、expiry、
  append-only correction/tombstone、same-boundary no-resurrection；
- `taxonomy/corpus.py`、`taxonomy/repository.py` / taxonomy phase-01 tests：read-only current preview、immutable
  frozen snapshot、stable source/card hashes与变化后新 snapshot；
- `knowledge_lifecycle.py`、`knowledge_service.py` / V5-B Stage 2 tests：Fact currentness、Artifact/Page affected
  lineage、stale candidate 与 published Page non-mutation；
- accepted Stage 1–3：principal/content fail-closed、off/explanation、Corpus/Route non-authority 与 existing
  Research/Workspace surface。

Contract round 只复跑四项材料相关 temp-DB/no-provider tests，结果 `4 passed`；未重复完整 default suite，符合
Main 从本 Stage 起的 directed + affected discipline。该证据不构成 Stage 4 implementation 测试或真实帮助收益。

没有影响 Contract 的外部材料缺口，因此不做 external JIT、不新增 upstream report/adoption proposal，不浏览
网络、不下载上游、不引入依赖或复制 source/test/Prompt/UI。结论为
`reimplement_shiliu_native_from_local_accepted_contracts`。

只有 distinct external notification/provider、new dependency、learned interest model、background frequency
optimization 或跨设备 durable inbox 被未来正式提出时，才触发 fixed official source/Commit/version/License/
source-test 的 material JIT；这些均不在 Stage 4 首片。

Implementation 若获授权，默认只运行 Stage 4 directed + affected Stage 1–3/non-personalized risk set；只有改动
共享核心出现材料风险才运行完整 default no-provider，否则留到 V5-C closeout。

## 10. Main 有限决策请求

请 V5 Main 只决定：

1. 是否接受四类能力收敛为一个 pull-only bounded panel；
2. 是否接受 mastery/user assertion 与 activity observation 的严格分离及 `mastered` enum 窄增量；
3. 是否接受 Fact/Artifact/Page currentness 与 same-scope current taxonomy snapshot delta authority；
4. 是否接受 confirmed Focus + current L1 Evidence 的最多一条 Radar candidate；
5. 是否接受 exact durable dismiss control、expiry/tombstone/correct/restore/no-resurrection；
6. 是否接受零 schema/dependency/Provider/background/platform、一个只读 projection 和无材料性外部 JIT；
7. 是否授权同一 V5-C Session 实施 Stage 4。

本提交不请求自我接受、Stage 4 实施、live DB、Provider、mainline/push/merge/tag 或 Stage 5。提交后停止，
等待 Main 有限审阅。
