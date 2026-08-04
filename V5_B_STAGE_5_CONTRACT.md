# 拾流 V5-B Stage 5 Contract

```yaml
stage: V5-B Stage 5
title: Product Completion, Relations and Evaluation
contract_status: draft_pending_v5_main_acceptance
proposal_authority: V5-B execution session
acceptance_authority: V5 main session
created_at: 2026-08-05
branch: codex/v5-b
accepted_stage_4_commit: ccfd8d9729eb5093ded5d397e5d5fd942fdab755
stage_4_main_acceptance_record: a483f2db81ee8b9434eadbf0fac09c4b07e1e15e_on_codex_v5_main_not_cherry_picked
schema_baseline: 14
contract_preparation_authorized: true
implementation_authorized: false
provider_evaluation_authorized_by_this_contract: false
provider_runs_performed_this_action: false
provider_cost_usd: 0
live_database_migration_authorized: false
```

> V5 Main已接受Stage 4 implementation commit `ccfd8d9729eb5093ded5d397e5d5fd942fdab755`，本次只授权Stage 5 Contract准备。本文不授权Stage 5 product/schema/API/UI/test实施或Provider评价，不构成V5-B自我验收。

## 1. Version-closeout user outcome

Stage 5把已接受的Stage 1–4收口为一条用户可理解的Topic/Knowledge Workspace闭环，而不是再建一个平台：

```text
open Topic/Knowledge Workspace
→ inspect a published Page, currentness, limitations and bounded related Pages
→ ask a query and inspect route explanation
→ direct reuse with current L1 citation
  or bounded incremental refresh / research seed
→ review Candidate and explicitly publish any new Page revision
→ record minimal feedback against the exact PageRevision or ArtifactRoute
→ inspect durable Event / Trace / Receipt / operation outcome
```

用户获得两个可比较的产品路径：

- **Reuse-first path**：现有Artifact/Page在scope、completeness、currentness与citation Gates全部通过时直接复用，不创建新Fact/Page revision；
- **Research-change path**：bounded gap进入incremental refresh，unsafe/no-hit/substantial gap进入research seed；所有新产出仍经过Candidate review并显式publish，保留old/new contribution lineage。

比较不是让旧Artifact成为verifier，而是回答“何时安全复用、何时必须重新研究，以及用户为何能相信该决定”。

## 2. Frozen authority and cross-version boundary

直接引用accepted Charter与Stage 1–4 invariants，不重新证明：SQLite sole authority、L1 Evidence/Citation、immutable Fact/Artifact/Page revisions、Candidate-only promotion、durable operation/Receipt、open retrieval、Workspace non-interference。

Stage 5不得：

- 让Explicit Memory、focus/progress、Corpus observation或Experience改变Search/Ask/Research/ArtifactRoute、prompt、budget或proactive behavior；这是V5-C；
- 把System Experience或Feedback提升为Skill/Policy、修改tool/prompt/retrieval/runtime；这是V5-D；
- 把relation当Citation、verifier、hard filter、route authority或Fact promotion authority；
- 自动修改Fact、Artifact或Page；任何内容变化继续走Stage 1–3 review/publish路径。

## 3. Bounded inter-page relations

### 3.1 Core relation projection

默认不新增relation存储。只从现有immutable/current lineage按需派生两种有明确用户价值的Page-to-Page导航关系：

1. `shared_current_fact`：两个当前可见PageRevision精确引用同一个current FactRevision；
2. `confirmed_conflict`：两个当前可见PageRevision分别引用一对由accepted lifecycle decision形成、且`resolution=confirmed_conflict`的current FactRevision。

每条投影必须返回：source/target Page与PageRevision、relation kind、支撑的FactRevision ID、可解释reason、currentness/head snapshot、`navigation_only=true`及Fact→L1 citation drill-down。自环去除、pair canonicalize、backlink对称派生；每页默认最多8条，超限返回`truncated=true`与总数，不做全图传输。

“当前可见”默认指published revision；若实现证明draft review必须预览关系，可作为同一projection的明确`preview=true`非权威视图，不改变core current projection。

### 3.2 Relation fail-closed rules

- Page revision、Fact head、currentness或confirmed-conflict observation不再匹配时，不投影该current relation；
- stale/retired/superseded Fact、pending/rejected conflict Candidate、lexical similarity、shared keyword、Corpus prior或embedding score不能产生core relation；
- relation只解释导航；Fact/Evidence authority仍从目标PageRevision逐级下钻；
- ordering只允许typed relation priority、确定性Page identity与标题排序，不做learned ranking。

现有`research_topic_page_fact_links`、`research_knowledge_fact_states`与`research_knowledge_conflict_observations`足以实现core。只有实现期具体FK/query invariant证明无法用现有lineage保证determinism/idempotency时，才允许最多一张窄append-only relation snapshot/support table，并须在Stage 5报告说明证据；不得借此引入graph store。

### 3.3 Explicitly rejected relation scope

不实现GraphRAG、自动知识图谱、generic graph store、embedding relation engine、graph traversal/ranking、graph dashboard、corpus-wide link rebuild或LLM link generation。手工related-page annotation与Markdown link parsing为optional/non-gating；若需要新authority/storage，不进入core。

## 4. Product integration, observability and Feedback Event

### 4.1 One integrated Workspace surface

在现有Research/Knowledge product surface内整合，不新增dashboard/workspace product：

- Page current/published revision、currentness、limitations/unresolved；
- bounded related Pages与relation reason；
- latest ArtifactRoute recommendation/final route、reused/new/dropped lineage；
- current operation/build status、retry/dead-letter/needs-user；
- L1 transcript citation drill-down；
- minimal feedback action与durable trace link。

### 4.2 Derived observability

复用Event、Trace、CommandReceipt、BuildRun、Stage 2 operation、ArtifactRoute和review decisions，形成一个bounded per-Task/per-Page projection：last durable outcome、pending/needs-user/failure count、latest route、last review/publish、feedback count和trace/receipt href。polling/live region仅改善体验，不成为authority；不得建设telemetry platform、event bus或第二套operation state。

### 4.3 Minimal Feedback Event

Feedback core只追加现有Research Event并使用CommandReceipt，不默认新增table：

- target：`topic_page_revision`或`artifact_route`；
- decision：`helpful | needs_fix`；
- small reason code：`answer_quality | citation | currentness | route | usability | other`；
- optional note（bounded）、expected target content/authority hash、principal、command ID和timestamp；
- duplicate返回同一receipt，payload mismatch fail closed，fault不留Event/Receipt orphan。

Feedback不自动触发research、update、relation、Workspace promotion或Experience/Skill变更。它只是可审计产品观察；任何后续内容修正仍需用户显式进入accepted lifecycle。

## 5. Dependency-ordered core

1. **Composition projection**：定义一份current Topic Workspace projection，组合accepted Page/Fact/Evidence/Route/operation/Workspace status，但Workspace仍只展示不消费。
2. **Relations**：在current published Page/Fact/conflict lineage上派生两种bounded relation，提供backlink与L1 drill-down。
3. **Feedback and observability**：以Event/Receipt追加minimal feedback，并把已有durable status投影到同一surface。
4. **Two-path closeout journey**：贯通reuse-first与research-change；新增内容必须完成Candidate review、immutable revision和explicit publish。
5. **Version evidence**：完成cross-Stage integration、fault/race/restart与Search/Ask/Research compatibility，生成单一Stage 5 report并请求V5-B version closeout review。

后一步不得成为前一步authority的替代品；relation/feedback/observability失败不能伪报Page、route或operation成功。

## 6. Lean complexity budget

| Surface | Default | Hard upper bound for Stage 5 core |
|---|---:|---:|
| new SQLite tables | 0 | 1 narrow append-only support table only with proven invariant |
| new services | 0–1 composition/projection adapter | 1; no platform split |
| new public endpoint types | 1 feedback command; relations/observability extend one existing/read projection | 2 total |
| new UI surfaces | extend current Topic/Knowledge Workspace | 1 integrated surface/card group |
| new schedulers/queues/indexes/graph engines | 0 | 0 |
| new dependencies/upstream code/UI/test copy | 0 | 0 |

API不得为relation、observation、metric或feedback每个noun建立CRUD。若现有Knowledge Workspace read可承载relations/observability，则只新增feedback command。

## 7. Compact mechanical acceptance matrix

只验证cross-Stage integration与Stage 5新增failure modes：

1. **Reuse-first closeout**：current/complete/exact Artifact direct reuse；同一published PageRevision、L1 citation与route explanation；helpful Feedback Event/Receipt duplicate/restart；无新Fact/Page mutation。
2. **Incremental closeout**：一个bounded gap只研究gap，保留reused/new/dropped lineage；Candidate review后产生new immutable Artifact/Page revision并显式publish；old revision/history可见。
3. **Seed fail-closed**：scope mismatch/no-hit/substantial stale/conflict进入seed；old Artifact仅作candidate context，open retrieval仍运行；unsafe direct override拒绝。
4. **Bounded relations**：shared-current-Fact与confirmed-conflict各一例；backlink对称、limit/truncated、reason与Fact→L1下钻；stale head/pending conflict/keyword similarity不产生relation。
5. **Observability/feedback safety**：projection来自durable Event/Trace/Receipt/operation/route；duplicate/payload mismatch/expected-hash/cross-task/fault/late UI response；无orphan或false success。
6. **Compatibility and closeout**：seeded-vs-empty Workspace下Search/Ask/Research/ArtifactRoute仍不变；Stage 1–5 directed、affected public journey、restart/race/fault、default no-provider和live DB non-action sentinel。

不做relation type、feedback reason、route enum的笛卡尔积；只在关闭独立failure mode时增加case。

## 8. Mechanical versus product/provider evaluation

### 8.1 Mechanical Gate（core）

Provider-independent、temporary-DB/no-provider fixtures为唯一Stage 5 acceptance authority。至少冻结：case ID、query、explicit aspects、expected safe route class、required lineage/citation assertions、expected mutation/no-mutation和failure class。机械Gate失败不得被Provider输出覆盖。

两条路径的deterministic比较至少记录：是否复用、是否新开Research Task、用户显式决策数、新revision数、current L1 citation通过率、route reason、restart/duplicate/fault结果。它证明产品路径差异，不声称证明主观质量。

### 8.2 Optional product/provider evaluation（non-gating）

只有Main接受本Contract及此评价边界后，Stage 5 implementation才可选择运行一个连续总预算不超过USD 2的existing DeepSeek integration package。运行前必须冻结并持久报告：

- 4–6个case，至少覆盖direct、bounded incremental、seed/no-hit与conflict/currentness；
- A路径=`route-guided V5-B Workspace`，B路径=`fresh V5-A Research baseline`，相同query/evidence snapshot；
- exact provider/model ID、integration/config hash、sampling/reasoning设置、prompt/template version、case manifest hash；
- budget cap `USD 2`、预测与实际tokens/cost、每次receipt；预计累计超过cap前停止并请求授权；
- credential只通过现有integration引用，不读取/显示值，不直接访问Keychain；
- rubric：scope satisfaction、citation usefulness/currentness、limitations honesty、route explanation、time/cost；Provider结果不授予Fact/Page authority。

失败分类固定为：`core_failure | bounded_limitation | implementation_failure | provider_failure | infrastructure_invalid | not_exercised | unproven`。Provider unavailable、rate limit或预算停止归Provider/not-exercised，不污染mechanical Gate；sync/hash外部变化归infrastructure-invalid并需新clean window。

本次docs-only不调用Provider、不检查credential，不把未来Provider评价设为V5-B mechanical completion gate。

## 9. Test and submission cadence

开发期只跑Stage 5 targeted temp-DB/no-provider tests；ordinary fixture/projection bugs有界修复。正式提交边界：

1. Stage 5 compact matrix；
2. Stage 1–5 directed integration；
3. affected Search/Ask/Research/ArtifactRoute/Page/Workspace public API/UI regression；
4. restart/duplicate/race/fault与migration/reentry；
5. default filtered no-provider suite只跑一次；
6. live DB只做获准的hash/stat non-action sentinel，不建立SQLite连接、不调用`Database.initialize()`；若Main要求schema/table/integrity检查，由Main在独立窗口执行；
7. Python/JS/static/docs/JSONL validation与clean working tree。

所有schema/migration测试只用temporary DB。Stage 5报告必须分开列出mechanical、optional Provider、not-exercised/unproven与任何infrastructure-invalid evidence。

## 10. Core, optional and non-gating

### Core acceptance

- one integrated Topic/Knowledge Workspace journey；
- two bounded derived relation kinds with explainability/L1 drill-down；
- derived observability + minimal Feedback Event/Receipt；
- reuse-first与research-change两条closeout路径；
- compact cross-Stage risk matrix、compatibility与version closeout evidence。

### Optional / non-gating

- Main接受边界后的USD 2以内Provider product comparison；
- manual related-page annotation、richer relation explanation/history、feedback note UX、static closeout export；
- draft relation preview、bounded product metrics summary。

### Explicitly not Stage 5

GraphRAG/knowledge graph/vector relation/graph dashboard；generic evaluation/telemetry/feedback platform；new queue/scheduler；Workspace personalization；Skill/Policy promotion；automatic correction/publish；enterprise multi-tenancy/RBAC/Connector/RAG replacement；V5-A compound-query修复；V5-C/V5-D。

## 11. Compound-query and JIT research decision

Program Registry/Research Log、`V5_B_UPSTREAM_DEEPTUTOR_RESEARCH_REPORT.md`、`V5_B_UPSTREAM_WEKNORA_RESEARCH_REPORT.md`与本地Stage 1–4 code足以定义Contract：

- WeKnora已提供bounded overview/ego、in/out links、truncated metadata、issues/stats/revision UI参考，同时明确GraphRAG/enterprise scope应拒绝；
- 本地PageRevision→FactRevision、Fact current state、accepted conflict、ArtifactRoute、Event/Trace/Receipt已经给出relations/observability/feedback的Shiliu-native authority；
- DeepTutor对Stage 5没有尚未解决的relation/evaluation authority机制。

因此不新增upstream checkout/research report/dependency或源码/UI/test复制，不调用Provider。若实现发现上述两类derived relation无法在现有lineage上确定性成立，才对已注册官方来源做bounded fixed-commit inspection并先向Main提出adoption evidence。

V5-A compound-query known limitation不进入Stage 5。只有frozen Stage 5 case在open retrieval与route均按Contract正确执行后，仍可重复证明该单一limitation直接阻塞version closeout，才在报告中列为bounded owner并请求Main决定；不得在Stage 5自行修复或扩张V5-A scope。

## 12. Version closeout ownership and limited review request

Stage 5 implementation完成后，V5-B Session只提交一个integrated implementation/closeout report与单一acceptance request，不自我接受。V5 Main负责：

- Stage 5与V5-B version-level acceptance；
- Program Current State/Decision Ledger及Registry/Research Log权威更新；
- merge、live migration/content action、version tag/release或其他version-level Git；
- 是否启动V5-C/V5-D及任何Provider扩大预算。

```yaml
stage_4_status: accepted_by_v5_main_at_a483f2db81ee8b9434eadbf0fac09c4b07e1e15e
stage_5_contract_status: draft_pending_v5_main_acceptance
stage_5_implementation_authorized: false
jit_research: existing_fixed_commit_reports_and_local_stage_1_to_4_code_sufficient
provider_runs_performed: false
requested_review:
  - version_closeout_user_journey_and_two_path_comparison
  - bounded_derived_relation_authority_and_complexity_budget
  - observability_feedback_event_and_non_interference
  - compact_mechanical_matrix_and_provider_evaluation_boundary
  - closeout_and_main_owned_version_actions
decision_requested: accept_or_return_one_bounded_contract_correction
```

请求V5 Main只审查Stage 5 target、relations/feedback authority、lean complexity budget、mechanical/provider evaluation boundary与version closeout ownership。在Main明确接受并授权前，不实施Stage 5，不启动V5-C/V5-D。
