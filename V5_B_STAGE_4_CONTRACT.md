# 拾流 V5-B Stage 4 Contract

```yaml
stage: V5-B Stage 4
title: Personal and Corpus Workspace
contract_status: draft_pending_v5_main_acceptance
proposal_authority: V5-B execution session
acceptance_authority: V5 main session
created_at: 2026-08-04
branch: codex/v5-b
accepted_stage_3_commit: 2d4d3397085dd9fe1b6d01533ce5743536b23740
stage_3_main_acceptance_record: 65706f4_on_codex_v5_main_not_cherry_picked
schema_baseline: 13
contract_preparation_authorized: true
implementation_authorized: false
implementation_started: false
provider_runs_performed: false
provider_cost_usd: 0
live_database_migration_authorized: false
```

> V5 Main已接受Stage 3，并只授权本次Stage 4 Contract准备。本文不授权schema/runtime/API/UI/test实施，不构成V5-B自我验收。

## 1. User outcome and one journey

Stage 4交付一个可审计的Personal and Corpus Workspace：

```text
inspect workspace
→ explicitly create a record or inspect a candidate/observation
→ inspect kind, authority, provenance, confidence/expiry and history
→ confirm | correct | reject | expire | tombstone
→ restart-stable projection with no silent resurrection
→ verify Search / Ask / Research / ArtifactRoute behavior remains unchanged
```

用户能看见并管理Explicit User Memory、inferred/behavioral candidates、Current Focus/Knowledge Progress、Corpus observations和System Experience。它们在Stage 4只被存储、解释和修正；不会改变Search、Answer、Research、Artifact route、prompt、budget或主动行为。

## 2. Frozen authority boundary

复用accepted Charter与Stage 1–3 invariants：SQLite sole authority、immutable/revision lineage、Event/CommandReceipt idempotency、current Evidence与Candidate-only promotion boundary。

| Record family | Stage 4 authority | Forbidden interpretation |
|---|---|---|
| Explicit User Memory | 用户直接创建或明确确认后才是user-state authority | 不是外部事实Citation，不自动个性化 |
| Behavioral/Inferred Candidate | 来源Event/Trace、evidence set、confidence、expiry与candidate status | 行为不得静默变成用户事实 |
| Focus / Progress | 用户明确状态，或对已发生Event/Artifact/Fact的可解释observation | watched != learned; searched != understood; one action != stable preference |
| Corpus Observation | 对指定collection/taxonomy snapshot的versioned observation，只是future soft prior | 不是Citation、allowlist、hard filter或closed-world authority |
| System Experience | Trace/outcome/environment lineage上的observed/diagnosed/candidate_source/invalidated record | 不是Active Skill/Policy，不改runtime |

User confirmation只能授予“这是我的显式状态”，不能把Corpus observation、Experience或外部claim变成Grounded Fact。

## 3. Lean WorkspaceRecord aggregate

实施默认使用一个append-only/revisioned `WorkspaceRecord` aggregate和deterministic projection，不为五类概念分建五个存储/服务。每个revision至少保存：

- stable `record_id`、immutable `revision_id`、parent revision、owner/scope和canonical payload/hash；
- typed `record_kind`: `explicit_memory | inferred_candidate | focus_state | progress_observation | corpus_observation | system_experience`；
- `authority_class`: `user_authored | user_confirmed | behavioral_candidate | evidence_backed_observation | corpus_soft_prior | experience_candidate`；
- typed payload、status、confidence/quality note、`expires_at`、created/effective time；
- source references/hashes到UserDecision/Event、Research Task/Attempt/Trace/Result、Fact/Artifact，collection membership或frozen taxonomy snapshot；
- command ID/payload hash、principal、reason、policy/schema version。

`record_kind`的语义不得被单一status扁平化：

- explicit memory: `current | tombstoned | expired`；
- inferred/focus candidates: `candidate | confirmed | rejected | expired | tombstoned`；
- corpus observation: `current | superseded | invalidated | tombstoned`；
- experience: `observed | diagnosed | candidate_source | invalidated | tombstoned`。

具体表名可调整，但core默认一张aggregate table；只有具体FK/query invariant不能用bounded canonical source refs表达时，才允许一张窄supporting table。

## 4. Decisions, expiry and no resurrection

- create/confirm/correct/reject/expire/tombstone都是显式command，使用CommandReceipt/payload hash和expected latest revision；correction追加new revision，不原地改payload。
- “delete”的Stage 4语义是append-only tombstone；不物理删除record、source references或decision history。
- expiry在read/command projection时按persisted time和policy deterministic计算，不要求background scheduler；过期状态不再是current。
- 同一semantic key + source boundary/hash产生的old event重放必须deduplicate到原rejected/expired/tombstoned lineage，不得重建active candidate。
- 新evidence boundary可生成new candidate revision，但必须引用prior terminal decision、显示变化原因并重新review；不能静默恢复。
- 用户对candidate的confirm/correction保留candidate origin；projection同时显示“来源为推测”与“用户已确认”。

## 5. Capability semantics in one pipeline

### Explicit memory and inferred candidate

- user-authored memory可直接以`user_authored/current`创建；behavioral/inferred只能先为candidate。
- candidate必须列出supporting events、反例/限制、confidence、expiry和生成policy；不实施hidden inference loop或LLM consolidation。
- 用户可confirm、correct-as-new-revision、reject、expire或tombstone；拒绝后按第4节no-resurrection。

### Current Focus and Knowledge Progress

- focus可由用户显式设定，或以candidate引用多个实际Event；单次watch/search/click不足以confirm。
- progress只把已有事件投影为`discovered/reviewed/researched/supported/unresolved/conflicted/stale`等可验证observation；`familiar/understood/learned`只能来自用户明确声明。
- Fact/Artifact只是progress provenance，不会被复制成user preference或memory claim。

### Corpus observation

- 仅由explicit command针对指定frozen collection/taxonomy snapshot生成；不自动扫描全库或持续profile。
- 可记录folder/topic/uploader/series/source availability/search term/limitation observation、input snapshot hash/version、coverage/quality与limitations。
- 新snapshot产生new revision/observation，旧记录保留；Stage 4不把Corpus observation接入retrieval filters/ranking/prompts。

### System experience

- 只从显式选定的Task/Attempt/Trace/Result/Event创建`observed`，并保存outcome、environment/scaffold fingerprint、affected steps和limitations；不记录credential values。
- 用户/开发者通过显式command追加`diagnosed`或`invalidated`；`candidate_source`必须以latest diagnosed revision为parent，不自动归因、合并或推广。
- `candidate_source`只表示可供V5-D将来研究；不生成Skill/Policy，不改prompt/tool/retrieval/runtime。

## 6. Dependency-ordered core

1. **Aggregate foundation**：temp-DB migration/reentry，immutable revision/tombstone，source refs/hash，Receipt/CAS，projection/no-resurrection。
2. **Explicit + candidate review**：create/confirm/correct/reject/expire/tombstone，显示authority和history。
3. **Focus/progress projection**：复用Event/Fact/Artifact refs，机械阻止watched=learned等shortcut。
4. **Corpus observation**：explicit snapshot command、versioned observation，并证明Search/Route不读取它。
5. **Experience record**：Trace/outcome/environment lineage和observed→diagnosed/candidate_source/invalidated，无Skill mutation。
6. **Product closure**：一组compact API、一个Workspace surface、affected/default no-provider regression和live DB non-action。

不拆分4A/4B formal governance；不先建MemoryOS、inference/corpus/experience平台、vector memory index、rules engine或scheduler。

## 7. Compact public surface

建议最小API（具体path由实施确定）：

- `GET workspace`：按kind/status投影current records、candidates、history/provenance摘要；
- `POST workspace/records`：显式创建memory或由指定现有source refs生成bounded candidate/observation/experience；
- `POST workspace/records/{id}/decisions`：confirm/correct/reject/expire/tombstone/diagnose/candidate-source/invalidate，使用expected revision。

UI只提供一个Workspace surface：compact kind/status filters、authority badge、confidence/expiry、source/Trace drill-down、history和一套review controls。不分成Memory、Corpus、Experience多个dashboard，不建CRUD console。

## 8. Compact mechanical acceptance matrix

| Case | Core proof |
|---|---|
| Explicit memory | create/correct/tombstone，immutable history，duplicate/payload mismatch/restart/CAS |
| Inferred candidate | source refs/confidence/expiry，confirm/reject，old-event replay no resurrection，new evidence requires review |
| Focus/progress | explicit/evidence-backed projection，watched/search/single action不会变成learned/understood/stable preference |
| Corpus observation | frozen snapshot/hash versioning，supersede/invalidate，seeded vs empty Workspace下open retrieval/Search/Ask/Research/ArtifactRoute结果不变 |
| System experience | observed→diagnosed→candidate_source or invalidated，Trace/outcome/environment lineage，Skill/Policy/runtime table/config不变 |
| Public journey + safety | one API/UI journey，cross-task/source forging，fault rollback/no orphan，Stage 1–3 + affected/default no-provider + live sentinel |

只在关闭独立failure mode时增加测试，不做enum笛卡尔积。

## 9. JIT evidence decision

已检查Program Registry/Research Log、accepted DeepTutor/WeKnora fixed-commit reports、Charter/Stage 1–3，以及本地collection membership、frozen taxonomy snapshot、Event/Trace/Result/Receipt、Fact/Artifact lineage和现有UI/API。

- DeepTutor已提供stable preference ID、explicit edit和“不要推测”的产品参考；拾流继续拒绝其physical delete/overwrite、process-only authority和个性化事实语义。
- WeKnora revision/review UI pattern已被Stage 1–3吸收；其Wiki/RAG/企业平台对Stage 4 authority/expiry/no-resurrection没有新的必需语义。
- local taxonomy frozen snapshot与membership已能定义versioned Corpus input；Research Event/Trace/Result已能定义Experience provenance；Stage 1–3已提供append-only correction、Receipt、fault和projection基础。

因此现有证据足以定义Contract；不新增upstream episode/report/checkout，不调用Provider。如实施发现authority/expiry/no-resurrection/soft-prior无法用上述本地边界实现，再按Registry trigger做bounded official-source fixed-commit JIT。

## 10. Optional / non-gating and implementation choices

Optional/non-gating：batch import/export、richer history diff、manual corpus comparison、Provider-assisted candidate wording、background expiry notification。它们不得成为authority或core前置。

Main接受Contract后，V5-B Session可在不改变边界的前提下确定：

- aggregate/supporting table具体名称与schema version；
- record semantic key、confidence scale、expiry projection和snapshot source-ref的bounded canonical shape；
- 是否需要一张source-ref supporting table；默认不需要；
- existing taxonomy/Research projection的最小adapter与Workspace UI的compact layout。

如需要让Workspace影响Search/Ask/Research/Route/prompt/budget，自动生成或promote Skill/Policy，引入new dependency/Provider机械Gate，或建设generic memory/corpus/experience platform，必须停止并升级V5 Main。

## 11. Explicit exclusions and limited review request

排除：V5-C personalized Search/Answer/Route/proactive behavior/prompts/budgets；V5-D Skill/Policy promotion/runtime mutation；Stage 5 relations/product evaluation；inter-page graph/GraphRAG；MemoryOS/inference engine/vector memory/rules engine/general scheduler；continuous profiling/corpus scan/LLM consolidation；enterprise multi-tenancy/RBAC/Connector；live DB/Provider/credentials/upstream copy/new dependency/push/merge/tag/self-acceptance。

```yaml
stage_3_status: accepted_by_v5_main_at_65706f4
stage_4_contract_status: draft_pending_v5_main_acceptance
stage_4_implementation_authorized: false
jit_research: existing_fixed_commit_reports_and_local_models_sufficient
provider_runs_performed: false
requested_review:
  - workspace_record_authority_and_typed_semantics
  - correction_expiry_tombstone_and_no_resurrection
  - corpus_soft_prior_and_behavior_non_interference
  - experience_candidate_and_no_skill_mutation
  - lean_api_ui_and_cross_version_boundary
decision_requested: accept_or_return_one_bounded_contract_correction
```

请求V5 Main只审查Stage 4 target、authority boundary、lean aggregate、dependency order和compact acceptance matrix。在Main明确接受并授权前，不实施Stage 4，不启动Stage 5。
