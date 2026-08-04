# 拾流 V5-B Stage 3 Implementation Report

```yaml
report_status: submitted_pending_v5_main_acceptance
version: V5-B
stage: 3
title: Artifact Retrieval, Reuse and Research Continuation
date: 2026-08-04
branch: codex/v5-b
accepted_stage_2_commit: f879c80c0f547195a40d6804b6057debd077d11a
stage_3_contract_commit: 70ba2b2c22f642ac52ddce0d3d30184d3b3235d6
stage_3_acceptance_and_authorization_record: 8c198db_on_codex_v5_main_not_cherry_picked
contract_status: accepted_by_v5_main
implementation_authorized: true
implementation_status: implemented_pending_v5_main_acceptance
schema_source_version: 13
provider_runs_performed: false
provider_cost_usd: 0
new_dependencies: false
live_database_migrated_or_mutated_by_this_session: false
self_accepted: false
stage_4_started: false
```

## 1. 提交结论

Stage 3已在accepted Contract与Main lean clarification内完成：

```text
Query
→ bounded Artifact retrieval + independent open-corpus lane
→ scope/currentness/citation/source-version/completeness observations
→ durable explainable route
→ explicit confirmation
   ├─ direct reuse
   ├─ incremental refresh
   └─ research seed
```

direct返回exact existing ArtifactRevision；incremental只研究可枚举缺口，新结果仍经Candidate review后生成有parent/contribution lineage的new ArtifactRevision；seed创建independent child ResearchTask，旧Artifact只是candidate context。所有路径保留FactRevision→current L1 Evidence/Citation→transcript drill-down，都不自动改Fact或Page。

## 2. Authority与边界遵循

- 实施依据accepted Contract `70ba2b2c22f642ac52ddce0d3d30184d3b3235d6`与Main record `codex/v5-main@8c198db`；Program-only commit未merge/cherry-pick。
- DeepTutor `44fa7a1552b88f9d8ce2c22259128a15ae2eb0c8` (Apache-2.0)与WeKnora `fcc4cd6a9f29a94818e481b3a604f44ce51c55e2` (MIT + listed third-party)继续只是已接受reference-only evidence；未新增upstream research、checkout、copy或dependency。
- SQLite是route identity/state/lineage/snapshot/receipt唯一authority；Stage 2 filesystem export不参与retrieval或route判定。
- Artifact score只排序inspection，不授予reuse；open-corpus retrieval每次独立执行，不以Artifact hit硬过滤alternative/counter-evidence。
- Provider、用户选择和旧Artifact都不是verifier；current Fact head、L1 Evidence/Citation和observed SourceVersion才是外部事实authority。
- 未修改V5-A compound-query known limitation，未实施Stage 4/5、V5-C/V5-D、enterprise/RBAC/Connector/RAG replacement。

## 3. Lean implementation shape

### 3.1 One append-only aggregate

schema source从12升至13，只新增`research_artifact_routes`一张表：

- `assessment / proceed / outcome`为同一route的immutable versions，update/delete trigger阻止原地改写；
- canonical JSON/hash保存query intent/explicit aspects、Artifact candidates/open summary、gate observations、recommended/final route、expected authority fence、continuation/outcome refs和reused/new/dropped contribution；
- 现有Event/CommandReceipt保存append-only audit、payload hash与exact replay；不为每个概念新建表。

### 3.2 Bounded retrieval and fail-closed gate

- 从每个Artifact family的latest canonical revision做最多5个candidate的small lexical/structured selection；score/reason只是inspection order。
- 同时独立调用现有`RetrievalService.search`，持久化最多5个open result的bounded summary/hash/reference；不建第二个index/product。
- gate机械检查explicit aspects、deterministic scope/coverage、Artifact current Fact heads、Fact lifecycle/currentness、server-owned `PersistentEvidenceAuthority.observe`、SourceVersion和citation completeness、limitations/unresolved。
- direct要求`scope=exact`、`completeness=complete`、Artifact所有Fact current、citations pass、无blocker；无法证明就fail closed。
- incremental要求current reusable core、`bounded_partial`且missing aspects可枚举并最多2个；其他情况为seed。

### 3.3 Existing continuation and lifecycle reuse

- assess创建version 1 route；proceed使用expected version、payload receipt与current authority/content/latest-revision fence；用户只能选同等或更保守route。
- direct不创建Task、Artifact或Page revision，直接指向exact existing ArtifactRevision。
- incremental/seed在同一transaction内复用V5-A `ResearchTask.parent_task_id`/Goal/Event/Receipt创建child，不新建scheduler、queue、lease、recovery或generic continuation framework。
- incremental child的objective/evidence policy只指向persisted gaps；新Research output仍是Candidate Delta，只有经Stage 1/2 review成为current-grounded child Fact后才能finalize。
- finalize再校验parent authority fence、child terminal/boundary、gap与new Fact一对一coverage，然后在parent family追加new immutable ArtifactRevision和Fact links；published Page不变。
- seed child是independent lineage；old Artifact在evidence policy中明示`candidate_only_not_verifier`且`open_retrieval_required=true`。

### 3.4 Compact API and UI

- `POST .../knowledge/routes/assess`：返回candidates、open summary、gates与recommendation。
- `POST .../knowledge/routes/{route_id}/proceed`：确认route或finalize continuation outcome。
- `GET .../knowledge/routes/{route_id}`：返回immutable versions、continuation/outcome、contribution与citations。
- Research UI只增加一个query/aspects form和route card，显示scope/currentness/citation/completeness、safer route、continuation/outcome、contribution与L1 transcript link；未创建workspace/dashboard/route CRUD console。

## 4. Mechanical acceptance evidence

### 4.1 Compact Stage 3 matrix

`tests/test_v5_b_stage3_artifact_reuse.py` 共6 cases / `6 passed`：

1. temp-DB schema/reentry/one-table/immutable，direct happy path，independent open lane，API/UI/read/proceed，Fact→L1 citation drill-down，duplicate，no auto mutation；
2. ambiguous/stale/late SourceVersion or Fact-head authority fail closed，safer seed，payload mismatch；
3. bounded incremental gap、child restart、Candidate intake/review、new ArtifactRevision、reused/new/dropped与citations，Page unchanged；
4. child fault rollback、cross-task Fact rejection、late authority fence、no orphan Task/revision/contribution；
5. no-hit/scope mismatch/substantial gap seed，candidate-only context/open retrieval required，no Fact/Page mutation；
6. assessment fault rollback，不留route/Event/Receipt。

### 4.2 Directed and affected regression

```text
Stage 1 + Stage 2 + Stage 3 directed:
23 passed

Affected V5-A Search/Ask/Research + V5-B Stage 1–3:
160 passed
```

Affected command files:

```text
tests/test_v5_a_stage1_research_api.py
tests/test_v5_a_stage1_research_kernel.py
tests/test_v5_a_stage2_inner_loop.py
tests/test_v5_a_stage3_outer_audit.py
tests/test_v5_a_stage4_operational_control.py
tests/test_v5_b_stage1_knowledge_workspace.py
tests/test_v5_b_stage2_knowledge_lifecycle.py
tests/test_v5_b_stage3_artifact_reuse.py
```

### 4.3 Default no-provider submission run

```text
PYTHONPATH=src <project-venv>/python -m pytest
1709 passed, 4 deselected, 7 warnings in 159.18s
```

`pyproject.toml` default filter排除`external_artifact`和`live_provider`；此为Stage 3提交边界唯一次default full-suite run。warnings为已有Starlette/httpx deprecation与multiprocessing fork warning，无test failure。

### 4.4 Static validation

- Python `py_compile`：passed。
- `node --check src/shiliu/static/research.js`：passed。
- `git diff --check`：passed。
- JSONL/YAML-fence和docs validation在commit前通过。

## 5. Live DB non-action evidence

live DB：`/Users/elliot/Library/Application Support/Shiliu/shiliu.db`。本Session只读hash/schema/integrity，不调用`Database.initialize()`。

1. full-suite窗口开始hash为`49bf8ab85cf17bc75822a1ff90133ad555b984a9cbe10c9c781c886324aaaa95`；期间已有`app.shiliu.sync`进程完成同步，结束hash为`1411d83ea22ebcd0d24dfca3ff1d52300de485772c62c773327ec2ec2210b1c6`。该窗口按`infrastructure-invalid`分类，不宣称为unchanged证据。
2. 前后只读检查均表明live DB为schema 10、`research_artifact_routes` table count 0、integrity ok，故无Stage 3 migration。
3. sync退出后，在Stage 3全6 directed tests前后hash均为`1411d83ea22ebcd0d24dfca3ff1d52300de485772c62c773327ec2ec2210b1c6`。这是本提交的clean temp-DB/no-live-action sentinel window。

## 6. Honest limits classification

### Bounded limitation

- Artifact selector仅检查latest revisions，最多5个candidates；aspect coverage使用deterministic normalized containment。语义改写、复合scope或无法证明coverage会保守转seed，不冒充direct/incremental。
- incremental gap最多2个；更大或无法隔离的缺口转seed。
- V5-A no-provider child不接受任意free-text success constraints；Stage 3把gap写入child Goal objective和evidence policy，不修改已知compound-query limitation。

### Not exercised

- Provider/DeepSeek：未调用，cost USD 0；mechanical acceptance不依赖Provider。
- live DB migration/content mutation：未授权且未执行。
- 浏览器人工视觉、键盘可访问性和多设备UI验证：未运行；public API/UI fixture与JS syntax已机械验证。

### Unproven

- 多进程高并发assess/confirm/finalize压力与长时间崩溃恢复；已有SQLite transaction、immutable versions、expected version、receipt、fault rollback和authority fence的有界mechanical evidence。
- 大corpus的语义retrieval quality/latency和Provider产品比较；属于Stage 5 evaluation closure，不是Stage 3 mechanical Gate。

### No core / implementation / provider failure

提交时无core failure、implementation failure或provider failure。唯一异常证据窗口已如实分类为external sync造成的`infrastructure-invalid`，并由后续clean sentinel关闭。

## 7. Explicit non-actions

- 未live DB migration/content mutation，未访问credential/Keychain，未调用Provider/付费服务。
- 未新增dependency，未复制upstream source/test/UI，未建通用vector/graph/memory/queue/multi-agent平台。
- 未更新Program authority/Registry/Research Log，未push/merge/tag/self-accept。
- 未启动Stage 4/5或V5-C/V5-D。

## 8. Limited Main acceptance request

```yaml
stage_3_contract_status: accepted_by_v5_main_at_8c198db
stage_3_implementation_status: implemented_pending_v5_main_acceptance
schema_source_version: 13
new_tables: 1
public_endpoints: 3
provider_runs_performed: false
live_db_clean_window_sha256: 1411d83ea22ebcd0d24dfca3ff1d52300de485772c62c773327ec2ec2210b1c6_unchanged
self_accepted: false
stage_4_started: false
requested_review:
  - one_aggregate_lean_shape_and_sqlite_authority
  - independent_open_retrieval_and_fail_closed_gates
  - direct_exact_revision_and_l1_drill_down
  - incremental_candidate_review_and_contribution_lineage
  - seed_candidate_only_and_no_automatic_mutation
  - duplicate_restart_fault_late_fence_and_regression_evidence
decision_requested: accept_or_return_one_bounded_stage_3_correction
```

请V5 Main进行一次limited Stage 3 implementation acceptance review。V5-B Session不自我接受；在Main明确决策前不启动Stage 4。
