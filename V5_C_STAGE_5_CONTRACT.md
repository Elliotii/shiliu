# 拾流 V5-C Stage 5 Contract

```yaml
stage: V5-C Stage 5
title: Integrated Personalized Research Journey and Evaluation
contract_status: proposed_pending_v5_main_acceptance
proposal_authority: V5-C Version Session
acceptance_authority: V5 Main Session
created_at: 2026-08-10
execution_branch: codex/v5-c
starting_commit: b9a07004267b2131121d558f5343063e5293db24
accepted_stage_1_baseline: 9e83ff078dee0ad038f012d197d812ff0e87a6f5
accepted_stage_2_baseline: 95749a1d557dbbb51383b58821519e0524227566
accepted_stage_3_baseline: 68e704e56bc0ba99de0506e9e2b93176b5c978a9
accepted_stage_4_baseline: b9a07004267b2131121d558f5343063e5293db24
main_stage_4_acceptance: 31f4075da06626ba4251aa7375919f676bf98bf9
main_stage_4_decision: V5D-20260810-030
schema_source_at_contract: 14
implementation_authorized: false
implementation_started: false
version_closeout_started: false
provider_runs_authorized: false
live_database_access_authorized: false
self_acceptance: forbidden
```

> 本 Contract 只冻结最终集成、一个窄 Answer presentation behavior、版本级机械证据与 closeout 形态。
> Main 接受并明确授权前，不得实施 Stage 5、运行 Provider、访问 live DB/凭据、执行版本收口/mainline/live
> migration，或修改 Program authority。

## 1. Stage 使命与完成定义

Stage 5 不是第五个平台；它把四个已接受 consumer 组合为 existing Research Task/Workspace 上的一条可见 journey：

```text
Research Task
  ├─ Answer：confirmed presentation preferences
  ├─ Search：explicit query on existing Product Search + task-scoped Corpus soft prior
  ├─ Next path：advisory-only existing capability recommendation
  └─ Progress & Assistance：pull-only progress/staleness/delta/radar
          ↓
combined explanation / per-consumer off / session all-off / existing correct & rollback
          ↓
version-level mechanical matrix + evidence-tiered closeout request
```

完成必须同时满足：

1. 不重新实现 Stage 1–4 projection/consumer；
2. existing Research page 显示一条 task-scoped journey rail，组合已有 context 与 inert links/actions；
3. Personalized Answer 有明确、用户可见且可关闭/回滚的最终 bounded boundary；
4. 各 consumer 的 authority、baseline、explicit-choice 与 fail-closed invariant 保持；
5. Stage 5 implementation 完成一次完整 default no-provider suite；
6. 用单一 implementation/closeout 文件请求 Main 验收与版本 closeout，V5-C 不自我接受。

## 2. Integrated Journey：组合展示，不建 truth store

### 2.1 Existing surface 与步骤

Stage 5 只扩展 existing Research Task page；可在 existing Workspace GET response 增加一个纯组合
`integrated_journey` view，输入仅为同 response 已有的 Stage 1、3、4 contexts 与 immutable Task identity：

| Step | Existing consumer/surface | Journey 中的可见状态 | 用户动作 |
| --- | --- | --- | --- |
| Answer | Research answer + `personalization_context` | baseline/treatment/off/fail-closed、applied effect/revision/hash | 聚焦现有 Answer/Workspace control |
| Search | existing `/search` + `corpus_task_id` | `explicit_query_required`；不得宣称 Search 已执行或有效 | inert deep-link 到 `/search?corpus_task_id=<task>&corpus_aware=true|false`，用户显式输入/提交 query |
| Next path | existing `route_recommendation` | baseline/recommended/blocked/overridden/fail-closed | 复用现有 inert CTA；真实执行仍需用户操作 |
| Progress & Assistance | existing `knowledge_assistance` | baseline/ready/fail-closed/disabled 与 lane counts | 聚焦现有 panel/dismiss/Workspace decisions |

Search context 只有用户在 existing Search surface 显式提交 query 后，才由 accepted Stage 2 projection 计算并展示。
Journey rail 不预跑 Search、不缓存 result、不创建 Search-completed 状态，也不复制 Corpus projection rule。

### 2.2 允许的组合 view

最低 additive output：

```json
{
  "policy_version": "v5-c-stage5-integrated-journey-v1",
  "task_id": "...",
  "principal_id": "...",
  "enabled": true,
  "steps": {
    "answer": {"status": "treatment", "context_hash": "...", "href": "#research-answer"},
    "search": {"status": "explicit_query_required", "href": "/search?corpus_task_id=..."},
    "routing": {"status": "recommended", "context_hash": "...", "href": "#research-routing"},
    "assistance": {"status": "ready", "context_hash": "...", "href": "#research-assistance"}
  },
  "reason_codes": [],
  "journey_hash": "server-owned deterministic composition hash",
  "authority": {
    "truth_store": false,
    "execution": false,
    "citation_or_verifier": false,
    "telemetry_or_evaluation": false
  }
}
```

`journey_hash` 只覆盖 Task/principal、composition policy、enabled flag、已有 context hashes/status 与 link mode；不写
DB，不成为 Profile/Journey/Eval identity。禁止新建 Journey table、event stream、completion state、funnel、score、
telemetry 或第二个 Profile/Rules store。

可在 existing Workspace GET 增加 request-local `journey_enabled=true|false`；`false` 只改变组合 view/status/hash，
并由页面同步传给已有 per-consumer toggles，不写持久状态、不新增 endpoint type。

## 3. Personalized Answer 最终功能边界

Stage 1 limitations placement 已证明 authority/off/rollback，但不足以单独表达 Charter 中“用户可选择回答阅读方式”的
最终可见边界。Stage 5 只允许再增加下列一个 presentation behavior：

```yaml
semantic_key: answer.presentation.detail_level
allowed_values:
  - standard
  - compact
default_without_confirmed_record: standard
effect_scope: research_answer_presentation_only
prompt_delta: 0
provider_delta: 0
```

### 3.1 `standard` baseline

保持所有 existing answer blocks 按 API 顺序展开显示；现有 limitations position preference 独立生效。没有 exact
confirmed preference、candidate/unconfirmed、unknown、conflict、expiry、terminal、wrong principal 或 off 时均为
`standard`。

### 3.2 `compact` treatment

只有 exact current-principal `explicit_memory:user_authored/current` 或
`inferred_candidate:user_confirmed/confirmed` 才可应用：

- 第一个 existing answer block 继续展开；
- 第二个及之后的 existing blocks 按原顺序放入一个 `<details>`，默认折叠且用户可立即展开；
- block text、block count/order、citation IDs/buttons、answer status、limitations 内容与位置规则不变；
- authoritative Evidence/Citation section 始终完整展开，不进入 compact container；
- 0–1 个 block 时返回 `no_secondary_blocks`，DOM 与 standard baseline 等价；
- UI 不能截断、概括、改写、删除或重新生成答案。

Mechanical comparison 必须证明 Product/API 的 `answer_blocks`、`limitations`、`citations`、Evidence identities、
currentness、Verifier/termination/budget 字段在 standard/compact/off/rollback 间相同；唯一允许变化是 presentation
context metadata 与 DOM container/expanded state。

### 3.3 Existing context 的窄扩展

实现只能扩展 existing Stage 1 `PersonalizationContextProjection`，不能新建 Answer Profile/projection store：

- policy version 精确升级为 `v5-c-stage5-personalized-answer-context-v2`；
- 保留 existing limitations-position fields/behavior compatibility；
- additive 返回 detail-level preference 的 record/revision/version/content hash、applied/status/reasons；
- 两个 semantic key 分别按 exact whitelist 解码并分别 fail closed；一个 key 的 conflict 不授予另一个 key authority；
- structured Feedback optional preference enum 可窄扩展到该 exact key/value，继续要求 two distinct same-Task、exact
  target/hash/key/value、current principal Events，仍只创建 candidate，绝不自动确认。

本 Stage 不修改 Prompt。若实施发现纯 DOM composition 无法维持 block/citation invariant，必须停止并报告具体 failing
invariant；不得改用 Prompt 或通用 personalization prompt engine。任何未来 Prompt proposal 都需单独 Contract，固定
exact prompt version、authority、baseline、回退与 Provider budget，不属于本 Stage 默认授权。

## 4. Shared explain、off、correct 与 rollback

Shared controls 只是现有控制的组合入口：

- journey explanation 显示各 step 的已有 status/context hash/reason/authority，不重新解释或裁决 consumer；
- `Personalization all off for this session` 只在当前页面切换 existing answer/routing/assistance toggles，并将 Search
  deep-link 设为 `corpus_aware=false`；不写 Workspace/Event/Receipt/local durable store；
- 用户可逐项重新打开，显式 Search query/mode/filter、route、permission、budget 始终保留；
- correct/expire/tombstone/restore-as-new 只聚焦 existing Workspace record/actions，不建立 Journey decision endpoint；
- rollback 继续是 append-only new revision；不得物理删除、覆盖历史或重启 terminal old boundary；
- journey rail 不能 `.click()` existing action、自动提交 fetch、创建 Research/ASR、执行 ArtifactRoute 或 Search。

## 5. Integrated authority invariants

Stage 5 必须同时保持：

1. Answer preference 只改变 frozen presentation fields；事实文本、Evidence、Citation、Verifier/currentness 不变；
2. Corpus observation 仍是 task/principal/snapshot-bound soft prior，raw retrieval/baseline pool 不变，至少一半 open
   slots 与最高 nonmatching counterexample 保留；
3. Profile/Focus/Corpus 不获得 route authority；用户 explicit path、permission/cost 与 ArtifactRoute late gates 优先；
4. progress mastery 只来自 explicit assertion；watched/searched/collected/transcript/research activity 永不升级 mastery；
5. Radar 仍需 confirmed Focus + verified added delta + current transcript/index identity，且不自动 Research；
6. candidate/unconfirmed、unrelated、wrong principal、expired/terminal、conflict、malformed、source/snapshot drift 分别在
   原 consumer baseline/fail closed；journey 不能“多数投票”恢复 treatment；
7. Stage 1–4 context hashes、source refs、boundary/version explanation 保留；composition hash 不替代它们；
8. Ask Fast/Deep、durable Research、ArtifactRoute、ASR、Search execution、Prompt、Provider、Fact/Page/Skill 均不被
   journey 自动调用或修改。

## 6. Frozen mechanical matrix

Stage 5 implementation 必须在一个 integrated temp-DB/no-provider Task journey 中冻结以下配对，并继续运行各 consumer
directed risk set：

| Case | Required comparison |
| --- | --- |
| cold baseline | 无 Workspace/Profile/Corpus/Progress 输入；Answer standard、Search explicit-query、Routing/Assistance baseline；零写 |
| confirmed treatment | limitations placement + compact Answer、Corpus Search composition、route recommendation、Progress/Assistance 各只改变 Contract fields |
| all off | Answer standard、Search link `corpus_aware=false`、route/assistance disabled；explicit query/path/permission 不变；零写 |
| per-consumer off | 只关闭目标 consumer，其他 accepted contexts/hash/visible effects不变 |
| rollback | Workspace append-only correct/tombstone/restore 后目标 behavior baseline/旧值的新 revision；journey 指向新 hash |
| unrelated | 无关 semantic key、Corpus cue、Focus/topic 不影响对应 consumer |
| candidate | Feedback/Profile/Focus candidate 未确认前所有 product behavior baseline |
| conflict | 每个 consumer 独立 fail closed；journey 只组合 status，不授予 fallback authority |
| drift | content/source/snapshot/ArtifactRoute/transcript drift 由原 consumer fail closed；不跨 consumer补偿 |
| explicit override | Search query/mode/filters 与 route/permission/budget 保持用户值 |
| restart/dedup | Task/record/context/journey hashes 与 DOM order 稳定；无 duplicate authority/write |
| non-interference | Answer API/Evidence/Citation、Search raw pool/open lane、route gates、mastery、Radar、Fast/Deep/Research/ASR 不漂移 |

Answer detail-level 另需 `standard vs compact vs off vs rollback vs unrelated/candidate/conflict` DOM test，逐一断言 block
texts/order/citation markers 与 Evidence section 不变。

## 7. Evidence 分层与版本 closeout 测试

Closeout 必须分层，禁止把 fixture 写成真实收益：

```yaml
cold_start_evidence:
  meaning: absence/fail-closed/no-write behavior
  may_claim_real_user_benefit: false
seeded_fixture_evidence:
  meaning: deterministic mechanics, paired visible effect, authority and non-interference
  may_claim_real_user_benefit: false
real_user_evidence:
  meaning: only explicitly authorized live observation or user feedback
  absent_is_reported_as_unproven: true
  absent_blocks_mechanical_closeout: false
```

Implementation evidence minimum：

1. Stage 5 integrated directed journey + answer DOM tests；
2. affected Stage 1–4、Workspace/Feedback、Product Search、Research Web/API、ArtifactRoute、Fast/Deep/ASR risk set；
3. 一次完整 default no-provider suite，报告 passed/deselected/warnings 与任何 bounded harness fix；
4. `py_compile`、Node tests/check、`git diff --check`；
5. schema/dependency/Prompt/Provider/background/platform delta audit；
6. Program authority unchanged、worktree clean、未访问 live DB/credential 的 authority report。

此前 Stage 的 full suite 不补跑、不伪造成 Stage 5 evidence；Stage 5 implementation 的一次完整 suite 是 V5-C version
closeout mechanical evidence。Main 后续仍只做风险导向复跑和其独立 integration/live smoke。

## 8. Lean implementation envelope

```yaml
schema_table_index_migration_delta: 0
new_authority_or_truth_stores: 0
new_endpoint_types: 0
new_dependencies: 0
new_prompt_versions_or_provider_calls: 0
new_background_workers_schedulers_notifications: 0
new_graph_rules_journey_telemetry_eval_platform: 0
existing_personalization_projection_extensions_max: 1
new_answer_behavior_max: 1
integrated_journey_composition_views_max: 1
existing_surfaces_only:
  - Research Task/Workspace
  - Product Search deep-link and existing explicit query
  - existing Workspace create/decision actions
```

默认实现只允许 existing strict preference enum/projection 的窄扩展、Research response/UI composition、Search inert
deep-link、DOM helper/tests 与版本内 docs。不得增加 generic journey engine、cross-page telemetry、evaluation DB、Profile
service、Rules engine 或 notification system。

## 9. Material JIT 与 Provider 判断

本地 accepted Stage 1–4 contracts/implementations/tests 已回答最终 Contract 的 authority、surface、rollback、delta、route
与 evidence-tier 问题。Answer detail-level 可由 existing answer blocks 做 deterministic DOM composition；无需外部机制、
依赖、Prompt 或 Provider。因此：

```yaml
external_material_JIT: not_required
upstream_report_or_adoption_proposal: none
provider_comparison: not_proposed
reason: no_concrete_product_question_remains_that_local_mechanical_evidence_cannot_answer
implementation_strategy: reimplement_shiliu_native_from_local_accepted_contracts
```

本 Contract round 不浏览网络、不下载上游、不复制 source/test/Prompt/UI、不访问 Provider/credential。未来只有 Main
明确提出一个机械证据无法回答的产品问题时，才可另提 fixed cases、budget、stop rule 与 non-gating Provider comparison；
它不自动属于 Stage 5 implementation。

Contract round 只做本地源码/accepted report 审计与 docs/JSONL/diff 静态校验，不重复产品测试；Main 的 Stage 1–4
独立 `16 passed` 是 accepted baseline，不冒充 Stage 5 evidence。完整 default suite 明确保留到获授权后的 Stage 5
implementation，且只运行一次作为 version closeout 机械证据。

## 10. 单一 closeout artifact

若 Main 接受并授权 implementation，Stage 5 不新增多条 Gate/A-B-C 报告线。实现与 V5-C closeout 请求合并为：

```text
V5_C_FINAL_CLOSEOUT.md
```

该文件同时承担 Stage 5 integrated implementation report 与 V5-C final closeout report，必须报告实际 implementation
commit、diff scope、paired matrix、完整 default suite、evidence tiers、live/Provider authority、unproven 与 Main 决策请求。
它不能宣布 Stage 5/版本 accepted；Main 决定最终 acceptance、mainline integration、live smoke/migration 与 Program
authority 更新。

## 11. Main 有限决策请求

请 V5 Main 只决定：

1. 是否接受 existing Research Task/Workspace 上的四-step composition journey；
2. 是否接受 `answer.presentation.detail_level=standard|compact` 为唯一新增 Answer behavior；
3. 是否接受 shared explain/all-off/correct/rollback 仅组合 existing controls、零 truth store；
4. 是否接受 integrated authority/non-interference 与 frozen mechanical matrix；
5. 是否接受一次完整 default no-provider suite 和 cold/fixture/real-user 分层作为 closeout evidence；
6. 是否接受无材料性外部 JIT、无 Provider comparison、零 schema/dependency/background/eval-platform；
7. 是否授权同一 V5-C Session 实施 Stage 5，并用单一 `V5_C_FINAL_CLOSEOUT.md` 请求 Stage 5/版本有限验收。

本提交不请求自我接受、Stage 5 产品实施、版本收口执行、live DB/Provider/credential、Program authority 修改、
mainline/live migration、push/merge/tag 或 V5-D。提交后停止，等待 Main 有限审阅。
