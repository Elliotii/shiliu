# 拾流 V5-B Stage 3 Contract

```yaml
stage: V5-B Stage 3
title: Artifact Retrieval, Reuse and Research Continuation
contract_status: draft_pending_v5_main_acceptance
proposal_authority: V5-B execution session
acceptance_authority: V5 main session
created_at: 2026-08-04
branch: codex/v5-b
accepted_stage_2_commit: f879c80c0f547195a40d6804b6057debd077d11a
stage_2_main_acceptance_record: 2d89dfc_on_codex_v5_main_not_cherry_picked
schema_baseline: 12
contract_preparation_authorized: true
implementation_authorized: false
implementation_started: false
provider_runs_performed: false
provider_cost_usd: 0
live_database_migration_authorized: false
```

> V5 Main已接受Stage 2，并只授权本次Stage 3 Contract准备。本文不授权schema/runtime/API/UI/test实施，不构成V5-B自我验收。

## 1. Stage使命与用户结果

Stage 3让用户提出新问题时安全复用已有Research Artifact，同时保持开放检索和反证发现：

```text
Query
→ Artifact retrieval + open corpus retrieval（independent lanes）
→ scope / source-version / currentness / completeness gate
→ durable explainable route proposal
→ explicit proceed
   ├─ direct reuse
   ├─ incremental refresh
   └─ research seed
```

- `direct reuse`：返回现有immutable ArtifactRevision及其Fact→L1 citations，不伪造新revision。
- `incremental refresh`：只在旧Artifact仍有materially usable current core且缺口可有界隔离时，建立targeted Research continuation；新旧贡献逐Fact可解释。
- `research seed`：scope mismatch、substantial incomplete/stale或unsafe ambiguity时启动新Research；旧Artifact只提供候选Fact/source/unresolved/search terms，不是verifier。

任何route都不自动修改Fact、Artifact/Page head或published Page。

## 2. 起始Authority与冻结边界

### 必须复用

1. V5-A `ResearchTask/Goal/Attempt/Checkpoint/Result/Event/CommandReceipt`及开放corpus retrieval、current Evidence authority与candidate-only Delta。
2. Stage 1 stable Artifact family + immutable ArtifactRevision、exact Artifact→FactRevision→Evidence links、source result/boundary/corpus snapshot/content hash。
3. Stage 2 Fact lifecycle/currentness、append-only revalidation observations、Artifact/Page affected projection、durable operation/fence和explicit publish。
4. SQLite仍是query/route/candidate/gate/lineage/receipt的唯一authority；filesystem export不参与retrieval或route判定。

### 不得弱化

- Artifact、similarity score、用户route选择或Provider输出都不能验证外部事实；reuse必须回到current FactRevision与L1 Evidence/Citation。
- Candidate ranking只决定“检查顺序”，不授予route eligibility。
- Artifact retrieval不能替代现有开放视频/corpus retrieval，也不能把未命中Artifact的来源硬排除。
- 旧Artifact不能自动改Fact/Page，incremental/seed Research结果仍是Candidate Delta并经过Stage 1/2 review。
- Stage 3不实现Stage 4 personal/corpus model，不实现Stage 5 inter-page relations/product evaluation closure。

## 3. JIT证据决定

### 已检查输入

- Program Registry/Research Log中的DeepTutor、WeKnora规划条目及V5-B startup fixed-commit episodes；
- accepted `V5_B_UPSTREAM_DEEPTUTOR_RESEARCH_REPORT.md`与`V5_B_UPSTREAM_WEKNORA_RESEARCH_REPORT.md`；
- Stage 2实际schema/service：Artifact body、limitations/unresolved、Fact links、source boundary/corpus snapshot、currentness projection、L1 source version、CommandReceipt和durable fence。

### 结论：现有证据充分，无新增upstream episode

- DeepTutor的stable ID、refs-required与ID-set incremental pattern足以支持候选/贡献lineage边界，但其Memory consolidation不是拾流route verifier。
- WeKnora的revision/durable-operation pattern已在Stage 2落地；其Wiki/RAG retrieval不能替代拾流open retrieval或claim-level Evidence gate。
- Stage 3尚未解决的核心是拾流自己的query scope/completeness与L1 currentness组合，不存在Registry中已登记且能直接提供更强authority语义的候选。
- 因此不做decorative upstream search/checkout，不新增research report，不调用Provider；如实施时确有未审阅机制需求，按Registry trigger再做bounded fixed-commit JIT。

## 4. Core authority records

表名可在实施时小幅调整，但下列identity与append-only边界不可弱化。

### 4.1 QueryIntent

每次route request持久保存：

- stable query/route ID、原始query、normalized objective；
- explicit `required_aspects`；没有可验证aspect contract时禁止direct reuse；
- temporal/viewpoint/scope、freshness policy、request principal；
- command ID、canonical payload/hash、created time。

Provider可在未来非gating地提出aspect candidates，但不能直接形成authority；core acceptance使用显式aspects和versioned deterministic policy。

### 4.2 ArtifactCandidateSnapshot

候选快照至少保存：

- Artifact family/revision/content hash、retrieval policy/version、score与reason；
- topic/body/limitations/unresolved snapshot hash；
- exact FactRevision IDs、Fact current head/state versions；
- EvidenceIdentity/SourceVersion及route-time revalidation observation IDs；
- open corpus retrieval boundary/reference，证明Artifact lane未取代开放lane。

同一route的candidate snapshot不可原地改写；新检索产生new attempt/snapshot。

### 4.3 GateObservation与RouteDecision

每个candidate逐项保存append-only gate observation：

- `scope`: `exact / compatible / mismatch / ambiguous`；
- `currentness`: `current / bounded_stale / unsafe`；
- `completeness`: `complete / bounded_partial / substantial_gap / ambiguous`；
- citations/source versions: pass/fail及失败Fact/Evidence IDs；
- reused aspects/FactRevision IDs、gap/stale/conflict aspects；
- evaluator/policy version、input snapshot hash、reason codes。

RouteDecision保存`direct_reuse / incremental_refresh / research_seed`、selected ArtifactRevision、candidate set、gate observations、reason codes、expected authority snapshot与receipt。Decision不可改写；重新判定产生新revision/attempt。

### 4.4 Explicit proceed与safer override

route proposal不会自动启动Research或改head。`confirm_route`使用expected route version：

- 用户可接受recommended route；
- 用户可降级到更保守路线（direct→incremental/seed，incremental→seed）；
- 用户不得通过override强制绕过gate进入direct reuse；
- duplicate回放，payload mismatch/stale snapshot fail closed。

## 5. Scope、currentness与completeness gate

### 5.1 Scope

- `exact`：required aspects、temporal/viewpoint与Artifact scope完全满足versioned deterministic matcher；
- `compatible`：核心scope一致，但有明确可隔离的新增aspect/time slice；
- `mismatch`：主体、time/viewpoint或success constraints不同；
- `ambiguous`：deterministic policy不能证明exact/compatible。

`unknown`不等于universal；ambiguous不能direct reuse。

### 5.2 Currentness与citations

route必须对候选的可复用Fact执行或引用同一authority boundary上的Stage 2 server-owned revalidation：

- Fact必须是family current head且lifecycle=`current`；
- required EvidenceUse/Identity与route-time observation均current；
- observed SourceVersion匹配snapshot；
- Fact→Evidence→video/timestamp/citation drill-down完整；
- conflicted/retired/superseded Fact不可复用；stale Fact只能成为gap/seed candidate。

route过程中SourceVersion/head变化使snapshot失效并要求reroute，不能late commit。

### 5.3 Completeness

- `complete`：每个required aspect至少有一个eligible current-grounded Fact覆盖，无relevant unresolved/limitation或ambiguous mapping。
- `bounded_partial`：至少一个material core aspect可由current Fact复用，且missing/stale aspects可枚举、相互独立并低于small versioned bound；没有global scope mismatch或unresolved conflict。
- `substantial_gap`：缺少material core、gap超过bound、staleness影响主体或需要重新定义scope。
- `ambiguous`：不能机械证明aspect→Fact coverage或limitations影响。

用户可确认“某Fact是否回答我的aspect”这一relevance决定，但不能借此把stale/unsupported claim变current；user mapping必须保存Decision并仍经过server currentness/citation gate。

## 6. 三条route

### 6.1 Direct reuse

必须全部满足：scope=`exact`、completeness=`complete`、所有reused Fact/current Evidence/citations/source versions通过、无blocking conflict/limitation、authority snapshot未变化。

结果只记录ReuseDecision并返回exact ArtifactRevision/content hash、covered aspects和citation drill-down；不创建“内容相同”的新Artifact/Page revision，不运行Provider/完整Research。

### 6.2 Incremental refresh

只在scope=`exact|compatible`、completeness=`bounded_partial`且material reusable core通过currentness时允许：

1. 创建durable continuation intent，锁定parent ArtifactRevision、reused FactRevision set、gap aspects、open-retrieval boundary与expected authority snapshot；
2. 通过既有V5-A ResearchTask/Goal机制只研究gap aspects，但仍保留开放来源和counter-evidence discovery；
3. 新结果保持Candidate Delta，按Stage 1/2 review后才能成为Fact；
4. 新ArtifactRevision在同一compatible family中保存parent/supersedes lineage和逐项`reused`/`newly_researched`/`dropped_with_reason`贡献；
5. 旧Artifact/Page不改写，Page必须另行explicit refresh/review/publish。

若gap不能隔离、reused core在运行中stale、出现global conflict或source/head fence变化，operation转`needs_user/superseded`并要求reroute，不自动扩大Research。

### 6.3 Research seed

以下任一条件进入seed：scope mismatch/ambiguous、substantial gap、主体Evidence stale/conflicted、citation/source-version不完整、coverage unsafe或无合格Artifact。

seed package只能包含：候选Artifact/Fact/source IDs、unresolved/gap aspects、search terms、scope differences与reason codes。新ResearchTask拥有独立authority lineage；旧Artifact不是verifier，不预先满足Goal，不硬过滤alternatives。完成后通常创建new Artifact family；任何Fact/Page变化仍需显式review/publish。

## 7. Open retrieval与anti-closed-world

1. Artifact candidate retrieval与现有corpus/source retrieval是独立lane；route snapshot同时记录两者boundary。
2. Artifact score不得成为source allowlist、negative filter或Research stopping condition。
3. incremental/seed必须允许发现未被旧Artifact引用的新来源与counter-evidence。
4. direct reuse UI仍显示“基于哪个revision/currentness boundary”，并允许用户选择更保守的Research route。
5. CorpusModel、personal preference、inter-page graph均不得参与Stage 3 hard filtering。

## 8. Dependency-ordered implementation core

1. **Route foundation**：temp-DB migration、QueryIntent/candidate/gate/decision/receipt与immutable triggers。
2. **Bounded Artifact retrieval**：在SQLite canonical ArtifactRevision上实现小型lexical/structured candidate retrieval；并行保留open corpus lane，不预建vector/graph平台。
3. **Authority gate**：scope、route-time Stage 2 revalidation、current head/citation/source-version、aspect coverage observation。
4. **Direct reuse closure**：explicit confirm、exact Artifact response、citation drill-down、stale snapshot fence。
5. **Incremental continuation**：durable parent/gap/reuse intent、V5-A targeted task link、candidate-only return、new Artifact contribution lineage。
6. **Research seed closure**：safe seed package、新Task lineage、no-verifier/no-hard-filter保证。
7. **Minimal product closure**：一条public API/UI journey展示三route及reason，affected/default no-provider regression。

不得先建设generic vector store、graph、memory、queue或multi-agent research platform。

## 9. Commands与事务/fence边界

建议最小commands：

- `retrieve_artifact_candidates`
- `assess_artifact_route`
- `confirm_artifact_route`
- `run_research_continuation`（复用既有V5-A task command surface）
- `inspect_reuse_lineage`

必须具有CommandReceipt/payload hash、expected route/candidate/head/source versions、bounded payload与cross-task/family validation。

必须同事务提交：

1. QueryIntent + candidate snapshot + retrieval Event/Receipt；
2. gate observations + immutable RouteDecision + Event/Receipt；
3. confirm Decision + direct reuse outcome，或continuation/seed intent + V5-A Task link + Event/Receipt；
4. accepted incremental result的new ArtifactRevision + Fact links + contribution lineage + operation terminal state + Event/Receipt。

任何fault不得留下orphan task/revision、部分contribution map或假success；restart重放同command必须得到同outcome或明确stale/reroute。

## 10. Minimal API / UI

### API

- POST query/retrieve，返回Artifact candidates与open retrieval summary；
- POST route assessment，返回逐candidate scope/currentness/completeness/citation gates；
- POST confirm route，执行direct response或创建incremental/seed continuation intent；
- GET route/continuation/reuse lineage，支持Fact→L1 citation drill-down。

### UI

- 输入query、required aspects及可选temporal/viewpoint scope；
- 候选列表显示revision、score reason、currentness、coverage、limitations/unresolved，不只显示similarity；
- route卡片明确显示`direct / incremental / seed`、通过/失败gate、reused Fact、gap与source boundary；
- 用户可接受或选择safer route，不能强制unsafe direct；
- continuation显示parent、reused/new/gap、task status和needs-user/reroute reason；
- citation点击继续下钻video/timestamp/transcript。

## 11. Core acceptance gates

### Gate A — Retrieval openness与identity

- Artifact candidate exact/restart/dedup、cross-task/content-hash forging、empty/no-hit机械测试；
- Artifact hit存在时open corpus lane仍返回独立候选/counter-evidence boundary；
- ranking变化不改变authority，filesystem export缺失不影响retrieval。

### Gate B — Authority与route fail-closed

- scope exact/compatible/mismatch/ambiguous；temporal/viewpoint unknown保守处理；
- complete/bounded-partial/substantial-gap/ambiguous aspect cases；
- route-time current→stale/source drift/head change/citation缺失均阻止direct；
- duplicate/payload mismatch/stale snapshot/fault rollback/restart有机械证据。

### Gate C — Direct reuse

- exact+complete+current case返回原ArtifactRevision且逐Fact可下钻L1；
- 不创建new Artifact/Page、Provider call或ResearchTask；
- 用户不能override进入unsafe direct，能够选择safer route。

### Gate D — Incremental refresh lineage

- bounded gap只创建targeted durable continuation；reused与new aspects/Fact逐项可解释；
- existing Fact不作new Evidence verifier，新Delta仍candidate-only；
- new Artifact revision保存parent/contribution lineage，old revision/Page/published pointer不变；
- crash/restart/duplicate/late source-head fence不留orphan或自动扩大scope。

### Gate E — Research seed、compatibility与non-actions

- scope mismatch/substantial stale/ambiguity/no hit形成seed package与independent ResearchTask lineage；
- seed不预先满足Goal、不硬过滤open sources、不自动Fact/Page mutation；
- public API/UI三route journey，Stage 1/2与Search/Ask/Research/default no-provider regressions；
- live DB sentinel不变，无Provider/credential/Keychain/new dependency/upstream copy。

## 12. Required mechanical cases

- schema migration/reentry/FK/unique/immutable/CAS（temp DB only）；
- candidate retrieval ordering/dedup/no-hit/cross-task/content-hash fence；
- explicit aspects、scope和coverage policy versioning；
- direct pass，以及stale/missing citation/source drift/limitation/ambiguous fail-closed；
- incremental bounded gap、targeted task、candidate-only return、reuse/new/drop contribution map；
- seed mismatch/substantial gap/stale/conflict/ambiguity/no-hit；
- open retrieval counter-evidence不被Artifact candidate suppress；
- confirm safer override、expected version、payload mismatch；
- restart/fault/late result/orphan rollback；
- 三route public API/minimal UI与citation drill-down；
- Stage 1/2 directed、affected Search/Ask/Research、default filtered no-provider与live sentinel。

V5-A compound-query limitation只有在上述受控Stage 3 case明确阻塞route时，才可提出有界修复；不能预先吸收。

## 13. Optional / non-gating

- embedding/vector semantic rerank；lexical/structured candidate retrieval足够core；
- Provider-generated aspect/coverage candidates；必须显式review且不授予Fact authority；
- richer diff/side-by-side Artifact comparison；
- multi-Artifact merge、batch refresh或background suggestion；
- latency/cost/full-research comparative product evaluation（Stage 5 closure）；
- inter-page/knowledge graph relation retrieval（Stage 5）。

optional项不得成为hard filter、citation authority或implementation前置平台。

## 14. Honest unresolved implementation choices

Main接受Contract后，V5-B Session可在不改变gates的前提下自主确定：

- route/candidate/coverage/contribution具体表名与schema source version；
- bounded lexical/structured retrieval使用现有helper还是专用small SQLite projection；
- deterministic aspect normalization与small gap bound的具体versioned constants；
- V5-A continuation link放在existing Task lineage extension还是Stage 3专用link table；
- explicit route confirm UI的最小布局和polling方式。

若实现需要Provider作为mechanical gate、generic vector/graph platform、放宽current Evidence authority、自动Fact/Page mutation或修复非阻塞V5-A limitation，必须停止并升级Main。

## 15. Explicit exclusions

- Stage 4 Explicit User Memory、behavioral/inferred candidate、Current Focus、KnowledgeProgress、CorpusModel、SystemExperienceRecord；
- Stage 5 inter-page relations/graph、provider/product evaluation closure；
- V5-C personalized answer/search/routing/proactive behavior；
- V5-D Active Skill/Policy promotion；
- generic vector DB/GraphRAG/memory platform/general queue/multi-agent framework；
- enterprise multi-tenancy/RBAC/Connector/RAG replacement；
- live DB migration/content mutation、Provider evaluation、credentials/Keychain；
- upstream source/test/UI copy、direct/new dependency；
- push/merge/tag/self-acceptance。

## 16. Limited review request

```yaml
stage_2_status: accepted_by_v5_main_at_2d89dfc
stage_3_contract_status: draft_pending_v5_main_acceptance
stage_3_implementation_authorized: false
jit_research: existing_fixed_commit_reports_and_local_stage_2_code_sufficient
provider_runs_performed: false
requested_review:
  - route_authority_and_fail_closed_semantics
  - direct_reuse_completeness_and_currentness_gate
  - incremental_refresh_gap_and_contribution_lineage
  - research_seed_and_open_retrieval_boundary
  - stage_4_5_and_cross_version_exclusions
decision_requested: accept_or_return_one_bounded_contract_correction
```

请求V5 Main只审查Stage 3 target、authority boundary、dependency order与Gates A–E；在Main明确接受并授权前，不实施Stage 3 schema/runtime/API/UI/tests。
