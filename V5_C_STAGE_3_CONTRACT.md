# 拾流 V5-C Stage 3 Contract

```yaml
stage: V5-C Stage 3
title: Personalized Routing
contract_status: proposed_pending_v5_main_acceptance
proposal_authority: V5-C Version Session
acceptance_authority: V5 Main Session
created_at: 2026-08-10
execution_branch: codex/v5-c
accepted_stage_2_execution_head: 95749a1d557dbbb51383b58821519e0524227566
main_stage_2_acceptance_authority: cd2eda1a116ca3308daba3e72b8018133b0c00b0
main_stage_2_decision: V5D-20260810-026
schema_source_at_contract: 14
implementation_authorized: false
implementation_started: false
provider_runs_authorized: false
live_database_access_authorized: false
stage_4_entered: false
self_acceptance: forbidden
```

> 本 Contract 只冻结一个 user-visible、advisory-only 的 route recommendation vertical slice。V5 Main
> 明确接受并授权前不得实施；V5-C Session 不能接受自己的 Contract 或 Stage。

## 1. Stage 使命与唯一纵切

在现有 Research Task surface 增加一个 task-scoped “Next path recommendation” panel。它只读取用户确认的
默认路径偏好和既有 capability/gate state，给出可解释的推荐或保持 baseline；它不改任何 radio/button
当前选择，不提交 Ask、ArtifactRoute、Research 或 ASR 请求，也不创建后台任务。

```text
explicit current choice / request-local permission / cost ceiling ────────────┐
                                                                              │
task-scoped confirmed default-path preference ── advisory presentation only ─┤
                                                                              │
existing capability state                                                    │
  ├── ArtifactRoute direct / incremental / seed + late authority fence       │
  ├── Ask Fast / Deep                                                        │
  ├── durable Research                                                       ├─→ recommendation panel
  └── exact-video manual ASR prerequisite                                    │       (never auto-executes)
                                                                              │
Corpus / Current Focus / candidate / Experience ── no route authority ───────┘
```

Stage 3 的产品效果只允许：显示一个推荐卡、原因、被 gate 排除的路径、当前显式选择、permission/cost 状态，
以及通向现有 control 的 inert link/button。只有用户再次明确点击既有 control，真实路径才可能执行。

## 2. 真实 capability catalog

Contract 只承认以下已经存在的能力，不创建抽象 Tool registry：

| Capability | 当前真实入口与 authority | Stage 3 可做什么 | 绝对禁止 |
| --- | --- | --- | --- |
| Artifact reuse | `ArtifactRoute` 的 `direct_reuse`；exact scope、complete coverage、current Facts/citations | 在 exact current assessment 可重验时推荐查看/确认 direct reuse | Profile 改成 direct；绕过 gate 或 late hash fence |
| Artifact refresh | `ArtifactRoute.incremental_refresh`；compatible core、current cited reuse、最多两个 isolatable gaps | 原 gate 允许且 cost permission 允许时推荐 existing continuation control | 扩大 gap、把旧 Artifact 当 Verifier |
| Research seed | `ArtifactRoute.research_seed` 或 existing durable Research Task | 推荐用户显式创建/继续 Research | 自动 create/run、自动扩大 budget、后台启动 |
| Fast | existing `AskRequest.mode=fast` | 推荐预填 existing Ask page；保持用户 radio selection | 自动提交、调用 Provider、改变 query/filter |
| Deep | existing `AskRequest.mode=deep` + bounded decision/tool budgets | permission/cost 允许时推荐预填 existing Ask page | 自动切 mode、调用 Provider、改变 budget |
| Manual ASR | exact video 的 existing `/api/videos/{video_id}/asr` durable Provider-backed job | 只在 exact video 缺 transcript、capability 可验证且用户明确允许时显示 manual prerequisite | 自动 POST、读 credential、把 ASR 当回答 route |

Fast/Deep 最终仍只能引用 current transcript/ASR Evidence；title/description/summary 仍只是 navigation。
Research 仍是独立 durable path，ArtifactRoute 仍只决定 direct/incremental/seed，不升级为 general router。

当前不存在 distinct Translation service/table/API/route。英文字幕在 existing transcript cleanup 中输出中文
整理结果是组合能力，不得显示为“Translation route”。独立 Translation 若未来成为材料性需求，必须另行
冻结 Provider、permission、budget、idempotency/recovery 与 source authority，Stage 3 首片不实现或推荐它。

## 3. 个性化输入与 authority

### 3.1 唯一 preference key

首片只消费一个 exact semantic key：

```text
research.routing.default_path = fast | deep | research
```

只有 task-scoped `explicit_memory + user_authored + current`、exact payload
`{"key":"research.routing.default_path","value":...}` 可进入 recommendation projection。该 preference 的
authority 只是“推荐展示理由”，不是 route、budget、permission、Citation、Verifier 或事实 authority。

Stage 3 不新增 behavioral route inference，也不扩展 Feedback candidate schema。`inferred_candidate`、
unconfirmed Focus、Corpus observation、System Experience、watch/search history 和 unrelated Profile key 即使
存在，也不能改变 recommendation。以后若要从隐式信号形成 route candidate，仍必须先有 exact sources、
用户 review/confirm 与 Main 接受的窄 Contract；不能在本 Stage 偷渡。

多个有效同 key records 值不同、payload malformed、unknown value、expired/terminal、principal/task mismatch
或 revision/content/source drift 时，整个 personalized treatment fail closed，不按 timestamp 猜测。

### 3.2 Current Focus 与 Corpus

Confirmed Current Focus 可在 panel 中原样显示为 context，但 Stage 3 首片不做 query-topic relevance 推断，
也不改变推荐。Stage 2 Corpus context 不进入 recommender；Corpus/Profile/Focus 均不能绕过 ArtifactRoute、
permission、cost、currentness、citation、Evidence 或 explicit-choice gates。

## 4. 显式选择、permission 与 cost precedence

实现若获授权，只允许 request/session-local 的严格输入；不建立 durable budget store 或 policy engine：

```yaml
current_explicit_path: null | artifact_route | fast | deep | research | manual_asr
allow_provider_answer: false | true
allow_high_cost_or_durable: false | true
allow_manual_asr: false | true
routing_personalization_enabled: false | true
```

默认 permission 全为 false。推荐决策按以下优先级固定：

1. 用户当次已经显式选择 path/mode/route：保持该选择，panel 标记 `explicit_override`；不得改 DOM selection
   或 request payload。若 permission/cost 不满足，只解释 denial，不偷偷改选其他路径；
2. `routing_personalization_enabled=false`：baseline；零 Workspace write；
3. exact current ArtifactRoute context：先只读重验 existing scope/currentness/citation/open-corpus/authority hash；
   direct/incremental/seed 只能保持现有 gate 或更安全路径，profile 不能降低 `ROUTE_ORDER`；
4. 无有效 ArtifactRoute 时，confirmed default-path preference 才能形成 advisory recommendation；
5. Fast 需要 `allow_provider_answer=true`；Deep 还需要 `allow_high_cost_or_durable=true`；Research 与
   incremental/seed 需要 `allow_high_cost_or_durable=true`；denial 返回 baseline/blocked explanation；
6. manual ASR 不是默认 path preference。只有 exact `video_id`、缺 current transcript、现有 ASR wiring 可
   验证、无冲突 active job、`allow_manual_asr=true` 时，才能显示为 prerequisite；仍必须由用户点击既有
   endpoint。任何不确定性都不推荐；
7. 没有能机械证明比 baseline 更合适的 path 时，`status=baseline`，保持当前产品选择。

“推荐”从不等于“执行许可”。现有 endpoint 自己的 validation、permission、budget、currentness、
idempotency 与 recovery 仍是最终 authority。

## 5. User-visible explanation 与控制

复用现有 Research Task/Workspace surface，panel 至少显示：

- `baseline|recommended|disabled|overridden|blocked|fail_closed`；
- Task ID、projection policy/context hash；
- preference record/revision/version/content hash 与 exact value；
- current explicit path 及“未被改写”；
- 每个真实 capability 的 `available|inapplicable|permission_denied|cost_denied|unsafe|stale|not_implemented`；
- ArtifactRoute route/version/expected authority hash、currentness/citation/coverage/open-lane gate；
- recommendation reason 与 rejected alternatives；
- `execution_authority=false`、`citation_authority=false`、`verifier_authority=false`、
  `fact_authority=false`、`budget_authority=false`、`permission_authority=false`；
- Translation：`not_a_distinct_route`。

推荐按钮只能预填/聚焦 existing control，不触发 network、Provider、Research run、ArtifactRoute proceed、ASR
POST 或 background work。用户点击 existing control 后，request 必须仍包含用户实际选择，而不是隐藏的
profile override。

当次/session off 只关闭 recommendation projection，不写 DB。持久 rollback 继续使用 existing Workspace
correct/expire/tombstone；恢复旧值必须 append 新 revision，不能复活终态 revision。

## 6. Paired acceptance matrix

每个 case 使用相同 temp DB/task/capability fixture，比对 selection/request payload、recommendation、
ArtifactRoute gates、provider/task/job call counts 与 Workspace history：

| Case | 必要结果 |
| --- | --- |
| cold start / no preference | 当前 UI selection 与产品 baseline 不变；无 recommendation |
| valid confirmed recommendation | exact user-authored default path 只改变 panel/highlight；不执行 path |
| candidate / unconfirmed | baseline；candidate 不进入 consumer |
| disabled | baseline；Workspace durable writes 为 0 |
| unrelated / Current Focus / Corpus | baseline；三者不获得 route authority |
| malformed / conflict / drift | deterministic fail closed；selection/request 不变 |
| explicit override | 用户 mode/route 始终保留；panel=`overridden` |
| current safe ArtifactRoute | 只显示既有 direct/incremental/seed gate；profile 不能选择更不安全 route |
| stale/unsafe Artifact | direct/incremental 不得被推荐；existing research-seed/baseline 保持 |
| provider permission denial | Fast/Deep 不推荐、不调用 Provider |
| cost/durable denial | Deep/Research/incremental/seed 不自动升级或启动 |
| ASR denial/uncertain | 不显示可执行 recommendation；ASR jobs/provider calls 为 0 |
| exact manual ASR prerequisite | 只显示 manual CTA；未点击时 jobs/provider/background calls 为 0 |
| restart/duplicate | context hash/reason/order 稳定，无双份 recommendation/authority/write |
| non-interference | Fast/Deep request、Research task、ASR job、ArtifactRoute、Stage 1 answer、Stage 2 Search 均不变 |

fixture 只证明 mechanics。live cold start 与真实用户路径收益必须继续分开报告。

## 7. 实现复杂度与禁止项

默认 implementation budget：

```yaml
schema_table_index_migration_delta: 0
new_authority_store: 0
new_endpoint_types: 0
new_dependencies: 0
new_prompt_or_provider_calls: 0
new_background_worker_or_scheduler: 0
new_generic_router_rules_policy_telemetry_eval_budget_platform: 0
read_only_route_recommendation_projection_adapters_max: 1
```

优先把 projection 作为 existing task Workspace response 的 additive context，并复用 Research surface；不得
修改 Ask/Research/ASR/ArtifactRoute execution contracts。实现测试只允许 temp DB/no-provider；不得访问
live DB、credential/Keychain 或 Provider。不得自动触发任何付费/后台动作，不得修改 Prompt、schema、
ASR/Translation pipeline、ArtifactRoute gates、Stage 1/2 consumers，也不得进入 Stage 4。

若 implementation 发现 existing endpoint/surface 无法在不破坏 explicit-choice invariant 的情况下承载
projection，必须返回 Main 做 bounded Contract clarification；不能自行建立 general router 或新平台。

## 8. Material JIT 判断

本地 accepted evidence 已覆盖本 Contract 的具体问题：

- `knowledge_reuse.py` 与 V5-B Stage 3 tests 冻结 direct/incremental/seed、currentness/citation/coverage、
  independent open lane、same-or-safer override 与 late authority fence；
- `AskRequest`/`AskService`/Deep budget tests 冻结 Fast/Deep 显式 mode、Provider 与 bounded budget；
- V5-A product Research contracts 冻结 explicit create/run、durable control 与 background boundary；
- `asr.py`/`pipeline.py`/Web/API tests 冻结 manual/automatic durable ASR、Provider、retry/review 与 explicit endpoint；
- Stage 1/2 已接受 projection、confirmed-only、off/rollback、Corpus no-route-authority 与 non-interference。

本 Contract round 使用 temp DB/no-provider 复跑 ArtifactRoute、Fast Ask、Deep Search 与 ASR 四组既有测试，
结果 `42 passed`；唯一输出为既有 Starlette/httpx deprecation warning。该复跑只验证 capability mechanics，
没有产生个性化收益证据。

因此没有影响 Contract 的材料性上游缺口：不做外部研究，不新增 upstream report/adoption proposal，结论为
`reimplement_shiliu_native_from_local_accepted_contracts`。本轮未浏览网络、未下载/checkout 上游、未新增
依赖，也未复制 source/test/Prompt/UI。

独立 Translation route、外部 route authority、learned routing、Provider evaluation、新 dependency 或
自动 cost optimization 均明确留待以后；它们若被提出才触发 fixed official source/Commit/version/License/
source-test 的 material JIT，而不是先实现。

## 9. Main 有限决策请求

请 V5 Main 只决定：

1. 是否接受 task-scoped confirmed `research.routing.default_path` 的 advisory-only authority；
2. 是否接受 unchanged explicit selection + capability/gate-first recommendation precedence；
3. 是否接受 ArtifactRoute/permission/cost/ASR manual prerequisite 与 Translation exclusion；
4. 是否接受 panel-only effect、paired matrix、零 schema/dependency/Provider/platform 增量；
5. 是否接受“无材料性外部 JIT”判断并授权同一 V5-C Session 实施 Stage 3。

本提交不请求自我接受、Stage 3 实施、live DB、Provider、mainline/push/merge/tag 或 Stage 4。提交后停止，
等待 Main 有限审阅。
