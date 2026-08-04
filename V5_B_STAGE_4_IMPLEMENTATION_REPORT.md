# 拾流 V5-B Stage 4 Implementation Report

```yaml
report_status: submitted_pending_v5_main_acceptance
version: V5-B
stage: 4
title: Personal and Corpus Workspace
date: 2026-08-05
branch: codex/v5-b
accepted_stage_3_commit: 2d4d3397085dd9fe1b6d01533ce5743536b23740
stage_4_contract_commit: 560293da5987478eea822197582beb3829dfa9ae
stage_4_acceptance_and_authorization_record: 9ff82483bf957f14315386621f9255b8c69ccedf_on_codex_v5_main_not_cherry_picked
contract_status: accepted_by_v5_main
implementation_authorized: true
implementation_status: implemented_pending_v5_main_acceptance
schema_source_version: 14
new_tables: 1
supporting_tables: 0
new_dependencies: false
provider_runs_performed: false
provider_cost_usd: 0
credentials_or_keychain_accessed: false
live_database_sqlite_accessed_or_mutated: false
self_accepted: false
stage_5_started: false
```

## 1. Submission outcome

Stage 4在accepted Contract内完成一条Personal and Corpus Workspace pipeline：

```text
inspect Workspace
→ explicitly create typed state or review a candidate/observation
→ server validates authority, source boundary, confidence/expiry and lineage
→ append confirm | correct | reject | expire | tombstone | diagnose | invalidate
→ restart-stable projection and old-boundary no-resurrection
→ prove Search / Ask / Research / ArtifactRoute remain unchanged
```

本实现不把Workspace变成个性化产品输入，不生成Skill/Policy，不构建MemoryOS、inference/vector/rules engine、corpus platform或background scheduler。

## 2. Concrete lean architecture

### 2.1 One aggregate

schema source从13升至14，只新增`research_workspace_records`：

- stable `record_id` + immutable `record_revision_id` + monotonically increasing version/parent；
- typed `record_kind`、`authority_class`、status、semantic key、payload、confidence/expiry；
- canonical source refs/boundary hash、content hash、command payload hash；
- Task/CommandReceipt/Event lineage、principal/reason/policy/timestamp；
- immutable UPDATE/DELETE triggers与record/version、Task/command uniqueness。

没有supporting table。source refs以bounded canonical JSON保存在aggregate内，但服务器逐项验证真实FK identity与Task boundary；Corpus只接受frozen taxonomy snapshot。

### 2.2 One service and existing durability

新增一个`ResearchPersonalWorkspaceService`，复用：

- V5-A `ResearchTask`作为命令边界；
- existing transaction、Event与CommandReceipt做atomic audit/idempotency；
- payload hash mismatch fail-closed、expected-version CAS、restart read；
- existing Research Event/Trace/Result、Fact/Artifact与taxonomy snapshot作为provenance；
- bounded fault hooks验证record/revision/Event/Receipt一起rollback。

没有第二套scheduler、lease、queue、recovery或generic continuation system。

### 2.3 Compact public product surface

只有三类API：

1. `GET .../workspace`：typed projection/filter/history/allowed actions；
2. `POST .../workspace/records`：explicit create或candidate/observation intake；
3. `POST .../workspace/records/{record_id}/decisions`：append-only review/decision。

Research页面只新增一个compact Workspace section，含kind/status filter、一个typed create form和一个review flow；没有五套dashboard或CRUD console。

## 3. Authority semantics delivered

### Explicit Memory

- 无source refs的用户直接创建为`user_authored/current`；
- inferred material不能伪装成Explicit Memory；
- correction/expiry/tombstone追加revision，restart后完整保留history；
- 只有user-authored/user-confirmed且current/confirmed的投影标为user-state authority。

### Behavioral/Inferred, Focus and Progress

- behavioral candidate至少需要两个distinct Research Event refs，初始为`behavioral_candidate/candidate`；
- confirm才变成`user_confirmed`；reject/expire/tombstone不物理删除；
- 相同旧source boundary重放会返回terminal revision并写audit receipt，不新增revision、不复活；
- terminal lineage遇到新boundary必须显式提供`reopen_reason`并重新进入candidate；
- learned/understood/familiar要求`user_asserted=true`；watched/search/single action不能promotion。

### Corpus Observation

- 必须且只能引用一个immutable frozen taxonomy snapshot；
- 新snapshot形成new revision并保留旧snapshot lineage；
- 始终标为`corpus_soft_prior`、`soft_prior_only=true`、`product_behavior_effect=false`；
- 没有进入retrieval filters/ranking/citations/prompts。

### System Experience

- 必须引用同一Research Task的Trace与Result；
- 只允许observed→diagnosed→candidate_source或invalidated/tombstoned；
- 保存observed pattern、outcome、environment fingerprint与diagnosis；
- 不创建或修改Skill/Policy/prompt/tool/retrieval/runtime。

## 4. Mechanical acceptance evidence

### 4.1 Compact six-case matrix

`tests/test_v5_b_stage4_personal_workspace.py`：`6 passed`。

1. schema 14/reentry/one table/immutable、Explicit Memory create/correct/tombstone、duplicate/payload mismatch/restart、三API与一UI；
2. inferred candidate weak-source rejection、confirm/reject/expiry、old-boundary no-resurrection、新boundary explicit reopen；
3. focus/progress阻止single action与watched-is-learned shortcut，区分user assertion和evidence-backed observation；
4. frozen Corpus snapshot versioning，并机械比较seeded前后open retrieval、Search、Ask、Research、ArtifactRoute不变；
5. Experience Trace/Result/cross-task lineage、diagnose/candidate/invalidated，Skill/Policy schema与runtime non-mutation；
6. cross-task/source forging、create/decision fault rollback、no orphan revision/Event/Receipt、filtered projection。

### 4.2 Directed and affected regression

```text
V5-B Stage 1 + 2 + 3 + 4 directed: 29 passed
Stage 1–4 + V5-A Research/migration + library/taxonomy affected: 179 passed
Search/Ask/public Research API affected: 56 passed
```

Affected regression覆盖：

```text
tests/test_search_api.py
tests/test_product_search_api.py
tests/test_search_display_metadata.py
tests/test_v4_ask_page.py
tests/test_v4_fast_ask_api.py
tests/test_v5_a_stage1_research_api.py
tests/test_v5_a_stage1_research_kernel.py
tests/test_v5_a_stage2_inner_loop.py
tests/test_v5_a_stage3_outer_audit.py
tests/test_v5_a_stage4_operational_control.py
tests/test_v5_b_stage1_knowledge_workspace.py
tests/test_v5_b_stage2_knowledge_lifecycle.py
tests/test_v5_b_stage3_artifact_reuse.py
tests/test_v5_b_stage4_personal_workspace.py
tests/test_library.py
tests/test_taxonomy_phase01.py
```

### 4.3 Default no-provider submission run

```text
PYTHONPATH=src <project-venv>/python -m pytest
1715 passed, 4 deselected, 7 warnings in 144.50s
```

这是Stage 4提交边界唯一次default full-suite run。`pyproject.toml`默认过滤`external_artifact`与`live_provider`；warnings是已有Starlette/httpx deprecation与multiprocessing fork warning，无test failure。

### 4.4 Static and docs validation

- Python `py_compile`：passed；
- `node --check src/shiliu/static/research.js`：passed；
- `git diff --check`：passed；
- Decision Ledger JSONL、YAML fences与docs references：commit前验证。

## 5. Live DB non-action sentinel

live DB路径：`/Users/elliot/Library/Application Support/Shiliu/shiliu.db`。

- full-suite前SHA-256：`e6dd58b4fd115b4768694c0de4f9e84cb1cc62f12cfc228f39c5e06705c6740f`；
- full-suite后SHA-256：`e6dd58b4fd115b4768694c0de4f9e84cb1cc62f12cfc228f39c5e06705c6740f`；
- 两端未发现sync进程；
- 本Stage只执行文件hash sentinel，没有用SQLite连接打开live DB，没有调用`Database.initialize()`，没有migration、table inspection或content mutation。

所有schema/migration/reentry/fault测试只使用pytest temporary DB。

## 6. Honest limits classification

### Bounded limitation

- payload上限32 KiB、source refs上限32；这是compact local aggregate，不是arbitrary memory store。
- behavioral inference机械门槛是至少两个distinct Event refs，不声称已证明心理偏好；仍必须用户confirm。
- expiry是deterministic projection-time status，不提供后台通知；显式expire仍追加revision。
- UI只覆盖compact create/review flow；批量import/export、rich history diff和manual corpus comparison不是Gate。

### Not exercised

- 长期真实行为分布、大规模corpus profiling、多设备并发、background expiry notification；
- Provider辅助candidate wording或memory consolidation；Provider调用为0，cost USD 0；
- V5-C个性化消费、V5-D Skill proposal/promotion、Stage 5 relations/evaluation。

### Unproven

- Workspace state对未来V5-C Search/Ask/Route质量的增益；
- System Experience对未来V5-D可迁移Skill候选质量；
- 大规模Workspace query/retention/UX，需Stage 5或后续版本产品证据。

### Core/implementation/provider/infrastructure failure

无。所有authorized mechanical Gates与submission regression通过；没有Provider或infrastructure-invalid窗口。

## 7. Files and non-actions

主要实现：

- `src/shiliu/research/personal_workspace.py`
- `src/shiliu/research/knowledge_contracts.py`
- `src/shiliu/research/knowledge_service.py`
- `src/shiliu/research/schema.py`
- `src/shiliu/db.py`
- `src/shiliu/web.py`
- `src/shiliu/templates/research.html`
- `src/shiliu/static/research.js`
- `tests/test_v5_b_stage4_personal_workspace.py`及schema-version affected tests

治理更新仅限既有Charter/Contract/Current State/Decision Ledger/Stage 3 report与本integrated report。未创建amendment/recovery/proposal proliferation。

未访问credential/Keychain，未调用Provider/paid service，未引入dependency/upstream copy，未live DB migration/content mutation，未更新Program authority/Registry/Research Log，未push/merge/tag/self-accept，未启动Stage 5/V5-C/V5-D。

## 8. Limited Main acceptance request

```yaml
requested_review: limited_v5_main_stage_4_implementation_acceptance
review_targets:
  - one_aggregate_typed_authority_and_immutable_decisions
  - candidate_review_expiry_and_old_boundary_no_resurrection
  - frozen_corpus_soft_prior_and_product_non_interference
  - experience_lineage_and_no_skill_policy_runtime_mutation
  - three_api_one_ui_lean_shape
  - temp_db_fault_restart_and_regression_evidence
stage_4_self_accepted: false
stage_5_authorized_or_started: false
decision_requested: accept_or_return_one_bounded_implementation_correction
```

请求V5 Main有限审查并决定是否接受Stage 4实现。V5-B Version Session不自我验收，也不启动Stage 5。
