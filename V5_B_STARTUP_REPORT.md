# 拾流 V5-B Startup / JIT Research / Charter Consolidated Report

```yaml
report_status: submitted_for_limited_v5_main_review
version_session: Shiliu V5-B Version Session
report_date: 2026-08-04
branch: codex/v5-b
starting_head: b85340540cb92c2e46bfb8619598e7aa987171d4
submission_commit: git_commit_containing_this_report_set
accepted_v5_a_code_baseline: 04e5c5bbb94311a00f6efafa142908fd7b2b97de
startup_assignment_complete: true
bounded_main_review_correction: applied_docs_only
charter_accepted: false
stage_1_contract_accepted: false
stage_1_implementation_authorized: false
provider_runs_performed: false
live_database_mutated: false
```

## 1. 提交结果

V5-B Session 已完成本轮限定的启动、JIT research、Charter 与 Stage 1 Contract 工作，没有实施 V5-B 产品代码。提交包形成七份文件：

1. `V5_B_UPSTREAM_DEEPTUTOR_RESEARCH_REPORT.md`
2. `V5_B_UPSTREAM_WEKNORA_RESEARCH_REPORT.md`
3. `V5_B_VERSION_CHARTER.md`
4. `V5_B_STAGE_1_CONTRACT.md`
5. `V5_B_CURRENT_STATE.md`
6. `V5_B_DECISION_LEDGER.md`
7. `V5_B_STARTUP_REPORT.md`

## 2. Branch / HEAD / clean gate

启动核验的实际结果：

```text
initial branch: detached HEAD
initial HEAD: b85340540cb92c2e46bfb8619598e7aa987171d4
initial status: clean
required branch codex/v5-b: existed, not occupied by another worktree
action: git switch codex/v5-b
post-switch branch: codex/v5-b
post-switch HEAD: b85340540cb92c2e46bfb8619598e7aa987171d4
post-switch status: clean
```

Branch mismatch 可安全修复，因此没有触发停止条件。最终提交与 clean status 由本报告所在 Git commit 后的 final handoff 报告；本文件不能自引用其自身 commit hash。

## 3. Authority 与 Baseline 审计

### 3.1 Authority inputs

按任务要求先读并纳入：

- V5-B Startup Package / Startup and Execution Plan；
- V5 Program Current State / Decision Ledger；
- V5-A Current State / Gate C and Closeout；
- 现阶段 V5/后续版本规划中的 V5-B 与跨版本边界；
- V5 主 Session 角色权限/Session 治理与研究/证据治理规范；
- DeepTutor/WeKnora Registry 和 Research Log entries；
- V5-A research/evidence/candidate-delta implementation reports、source 和 tests。

### 3.2 V5-A accepted baseline

独立 Git diff 确认 `04e5c5bbb94311a00f6efafa142908fd7b2b97de..b85340540cb92c2e46bfb8619598e7aa987171d4` 没有产品源码变化。V5-B 可在 accepted V5-A code 上设计，不需要重开 Gate C。

关键可复用事实：

- schema 10；Research identity/lineage/receipt/owner fence 已接受；
- EvidenceIdentity global immutable；EvidenceUse task/attempt scoped；Provenance/Validation append-only；
- provisional artifact immutable，source drift 不回写旧对象；
- Candidate Delta 是 Event + CommandReceipt 的 bounded exact-once snapshot；
- four kinds 全是 `candidate_only_not_promoted`；没有长期 review/promotion store；
- KnowledgeDelta 从 artifact answer blocks/citations 派生；UserModelDelta 只来自显式 HumanDecision；
- 相关 API/UI 已能展示 candidate-only 和 citation/trace，但不是 V5-B Workspace。

已知 V5-A compound-query retrieval limitation 保持 `unproven`，不因 V5-B startup 自动转成实施范围。

## 4. 固定上游研究

### 4.1 DeepTutor P0

```yaml
official_repository: https://github.com/HKUDS/DeepTutor.git
pinned_commit: 44fa7a1552b88f9d8ce2c22259128a15ae2eb0c8
tag: v1.5.8
license: Apache-2.0
checkout: temporary_sparse_detached_clean_outside_product_tree
research_depth:
  - official_readme_release_license_third_party_notice
  - l1_l2_l3_paths_and_documents
  - trace_read_write_update_delete
  - idempotency_and_user_correction
  - incremental_consolidation_and_lineage
  - run_observability_and_undo
  - relevant_tests_source_review
tests_executed: false_collection_blocked_by_sparse_package_import_chain
```

结论：采用分层、stable entry ID、refs-required、batch preflight、ID-set incremental、preview/apply 与 correction 产品模式的独立重实现/测试参考；拒绝 JSONL L1 authority、物理 delete/overwrite、process-only runs/undo、surface-level L3 refs、依赖/源码复制。

### 4.2 WeKnora bounded P1

```yaml
official_repository: https://github.com/Tencent/WeKnora.git
pinned_commit: fcc4cd6a9f29a94818e481b3a604f44ce51c55e2
nearest_release_reviewed: v0.7.1@c64a48647cd6f7eb8b0fb020b2e8fec74ee375fb
license: MIT_main_project_with_listed_third_party_components
checkout: temporary_sparse_detached_clean_outside_product_tree
research_depth:
  - topic_page_revision_and_links
  - optimistic_update_atomic_snapshot_and_revert
  - durable_pending_ops_claim_retry_dead_letter
  - ingest_finalize_rebuild_and_startup_recovery
  - stats_issues_graph_revision_ui
  - relevant_go_and_frontend_tests_source_review
bounded_tests_executed: 2_passed
```

结论：采用 Topic Page/revision UI、optimistic version + atomic snapshot、revert-as-new、durable pending/recovery/dead-letter 的独立重实现/测试参考；拒绝企业 tenancy/RBAC/Connector、RAG replacement、GraphRAG default、Redis active authority、rebuild failure log-and-drain、依赖/源码复制。

## 5. 规划假设的定向验证

### 5.1 拾流 no-provider / temp-DB

执行：

```text
PYTHONPATH=<isolated-worktree>/src <existing-project-venv>/python -m pytest -q
  tests/test_v5_a_stage2_inner_loop.py
  tests/test_v5_a_stage4_operational_control.py
  tests/test_v5_a_stage5_product_completion.py
```

结果：`73 passed`。覆盖临时 schema、Evidence identity/use/validation/artifact immutability、source drift、task isolation、receipt/payload mismatch、fault rollback/takeover、HumanDecision/control、Candidate Delta exact-once 与 product journey。唯一 warning 是既有 FastAPI TestClient/httpx deprecation。

这些测试使用 fixture/temp DB；没有 live DB、Keychain 或 Provider。

### 5.2 WeKnora pure test

```text
node --test frontend/src/views/knowledge/wikiStatusRefresh.test.ts
2 passed, 0 failed
```

只证明 polling transition predicate，不证明 Wiki queue/generation。

### 5.3 DeepTutor bounded attempt

六个 Memory test files 在 collection 阶段因 sparse checkout 的包级 `deeptutor.runtime → deeptutor.core` 导入链缺失而停止。没有执行测试体；没有安装完整上游或扩展到非研究范围。报告状态为 `tests_source_reviewed / tests_not_executed`。

## 6. Charter 与架构提案

### 6.1 Authority chain

```text
L1 V5-A Evidence/Event authority
  ↓ exact evidence links + current validation
L2 GroundedFact family / immutable FactRevision
  ↓ exact fact revision links
L3 ResearchArtifact family / immutable ArtifactRevision
  ↓ exact artifact/fact links
TopicPage family / immutable PageRevision
```

Candidate snapshot 是不可变来源；V5-B 新建独立 durable review identity。只有 KnowledgeDelta 在 Stage 1 eligible，且 accept 前 server-side 重建 source boundary/current Evidence；Edit 形成新 candidate revision，不自动 grounded。

### 6.2 Storage

SQLite 是 candidate/decision/fact/artifact/page/build/receipt/canonical body 的唯一权威。Filesystem 只可保存 revision/hash-addressed immutable Markdown/JSON export/cache；Stage 1 不实现或验收 export command/failure/retry，相关产品面进入 Stage 2。

### 6.3 Durable build

Stage 1 建立并同步执行 artifact/page deterministic no-provider BuildRun。完整 durable pending operation、wakeup/recovery/retry/dead-letter、general update/rebuild 和 async late-result fencing 放 Stage 2，避免先造通用 queue platform。

## 7. Stage breakdown

| Stage | 目标 | 主要不进入项 |
| --- | --- | --- |
| 1 | Research Task → KnowledgeDelta intake/review → current Evidence validation → accepted Fact → deterministic Artifact → first Page revision → publish-or-return → transcript drill-down | Page edit/history/revert、Fact lifecycle、export gate、async refresh、reuse、user/corpus workspace |
| 2 | revalidation/stale/conflict + Fact correction/retire/supersede + Page edit/history/diff/revert + export + durable update/rebuild/late-result fencing | artifact reuse/personalization |
| 3 | direct reuse/incremental refresh/research seed | user/corpus state |
| 4 | Explicit Memory/inferred candidates/Focus/Progress/Corpus soft prior/Experience | V5-C behavior、V5-D Skill |
| 5 | product closure/relations/observability/eval/regression | enterprise Wiki/GraphRAG default |

该序列保留全部 V5-B capability goals，没有把 portfolio-ready 当停止点。

## 8. Stage 1 请求范围

若 Main 接受 Charter 与 Contract，请只授权：

- Stage 1 schema 与临时 migration tests；
- no-provider Candidate intake/review、current Evidence validation、初始 Fact/Artifact/Page runtime/API；
- synchronous durable artifact/page BuildRun；
- 最小 Candidate/Page publish-or-return review UI 和 transcript citation drill-down；
- receipt、expected-version review guard、duplicate/restart/fault rollback tests；
- Search/Ask/Research affected regression。

继续不授权：Page edit/history/diff/revert、Fact correction/retire/supersede 产品命令、filesystem export command/failure matrix、async late-result/update/rebuild、live migration、Provider/paid service、credentials/Keychain、upstream copy/new dependency、Stage 2–5、V5-C/V5-D。

## 9. Unproven / deferred

- Charter/Stage 1 尚未被 Main 接受；实现未开始。
- edited claim 的 server-owned grounded validator 未实现；没有 validator 时必须 `needs_revalidation`。
- exact schema/table/API/limits/UI layout 等待 Stage 1 implementation review，不能放宽 Contract identity/authority。
- Stage 1 只创建初始 immutable Fact/Artifact/Page revisions；Page edit/history/diff/revert、Fact correction/retire/supersede 与 filesystem export gate 已明确移至 Stage 2。
- DeepTutor tests 未执行；WeKnora Go tests 未执行；两者 Provider generation 未运行。
- conflict/stale propagation、async refresh、reuse/seed、personal/corpus workspace 未实现。
- default full Shiliu suite 本轮未运行；只运行足以验证 planning assumption 的 73 项 directed tests。
- live DB/content 未读写；Provider quality、live migration 和 production performance 未证明。

## 10. 未直接修改的 Program/Registry/Research Log：精确更新提案

以下只供 V5 Main 在接受/修订后写入权威文件。本 Session 未修改这些文件。

### 10.1 `V5_PROGRAM_CURRENT_STATE.md`

建议在 V5-B 状态段加入以下事实（Main 应把 `<reviewed_startup_commit>` 替换为其实际审阅的本提交 hash）：

```yaml
V5_B:
  startup_status: submitted_for_limited_main_review
  startup_commit: <reviewed_startup_commit>
  branch: codex/v5-b
  starting_commit: b85340540cb92c2e46bfb8619598e7aa987171d4
  accepted_v5_a_code_baseline: 04e5c5bbb94311a00f6efafa142908fd7b2b97de
  charter_status: pending_main_acceptance
  stage_1_contract_status: pending_main_acceptance
  implementation_authorized: false
  provider_runs_performed: false
  upstreams:
    deeptutor: 44fa7a1552b88f9d8ce2c22259128a15ae2eb0c8
    weknora: fcc4cd6a9f29a94818e481b3a604f44ce51c55e2
  proposed_next_action: limited_main_review_and_explicit_stage_1_authorization_decision
```

### 10.2 `V5_PROGRAM_DECISION_LEDGER.md`

在 Main 实际决定前不要记录为 accepted。建议先追加/转录一项 pending review，决定后改为实际结果：

```json
{"decision_id":"V5-PD-V5B-STARTUP","date":"2026-08-04","status":"pending_main_review","scope":"V5-B charter_stage_sequence_upstream_boundaries_and_stage_1_authority","proposal":"Review the five-stage V5-B Charter, DeepTutor/WeKnora reference-only adoption boundaries, SQLite-authority/filesystem-export mapping, and the Stage 1 Evidence-backed Topic Page vertical slice. No implementation is authorized until an explicit Main decision.","evidence":["V5_B_STARTUP_REPORT.md","V5_B_VERSION_CHARTER.md","V5_B_STAGE_1_CONTRACT.md","V5_B_DECISION_LEDGER.md"],"implementation_authorized":false}
```

### 10.3 Registry `deeptutor` entry

建议把对应字段更新为：

```yaml
local:
  status: absent
  path: null
  release_or_commit: 44fa7a1552b88f9d8ce2c22259128a15ae2eb0c8
  fetched_at: '2026-08-04'
  notes: Temporary sparse checkout was outside the product tree and is not a retained Registry resource.
research:
  status: tests_reviewed
  depth:
  - official_readme_release_license_third_party_notice
  - fixed_commit_source_symbols
  - l1_l2_l3_read_write_update_delete
  - idempotency_user_correction_incremental_lineage
  - relevant_tests_source_review
  last_reviewed_at: '2026-08-04'
  reviewed_by: [V5-B_version_session]
  source_reports: [V5_B_UPSTREAM_DEEPTUTOR_RESEARCH_REPORT.md]
current_assessment:
  adoption_status: candidate
  recommended_modes: [reimplement_pattern, test_reference, product_or_behavior_reference]
  summary: Reference-only adoption is proposed pending Main acceptance; dependency/source copy and weak authority mechanisms are rejected.
  implementation_authorized: false
  unresolved_questions:
  - upstream tests not executed because bounded sparse checkout could not complete package collection
  - recheck license only before any future code or test copy
```

### 10.4 Registry `weknora` entry

```yaml
local:
  status: absent
  path: null
  release_or_commit: fcc4cd6a9f29a94818e481b3a604f44ce51c55e2
  fetched_at: '2026-08-04'
  notes: Temporary sparse checkout was outside the product tree and is not a retained Registry resource.
research:
  status: tests_reviewed
  depth:
  - official_readme_release_license
  - page_revision_links_and_review_ui
  - durable_pending_retry_dead_letter_recovery
  - generation_finalize_rebuild_observability
  - relevant_go_and_frontend_tests_source_review
  - two_pure_frontend_tests_executed
  last_reviewed_at: '2026-08-04'
  reviewed_by: [V5-B_version_session]
  source_reports: [V5_B_UPSTREAM_WEKNORA_RESEARCH_REPORT.md]
current_assessment:
  adoption_status: candidate
  recommended_modes: [product_or_behavior_reference, reimplement_pattern, test_reference]
  summary: Bounded reference-only adoption is proposed pending Main acceptance; dependency/source copy and enterprise/RAG platform scope are rejected.
  implementation_authorized: false
  unresolved_questions:
  - Go wiki and queue tests were source-reviewed but not executed
  - recheck component licenses before any future code/UI/test copy
```

`local.status` 使用 Registry 允许值 `absent`，因为 checkout 在 `/tmp` 且不是应长期登记的仓库资源；固定 Commit 与研究深度仍记录在 `release_or_commit` / `research` 字段。

### 10.5 Research Log：DeepTutor episode

建议追加以下单行 JSONL，并保持 `implementation_authorized=false`，直到 Main 另有决定：

```json
{"event_id":"UR-20260804-017","recorded_at":"2026-08-04","event_time_precision":"date_only","event_type":"fixed_commit_source_and_test_review","stage":"V5-B startup","session_role":"V5-B_version_session","trigger":"V5-B Charter and Stage 1 require source-level evidence for L1/L2/L3, correction, idempotency and SQLite/filesystem mapping.","resource_ids":["deeptutor"],"research_scope":"Official fixed-commit sparse source audit of memory paths, document/ops/store, trace, consolidator/meta/update/references/runs, API/tools and relevant tests; no provider and no source copy.","source_strength":["official_source","official_tests","official_license","official_release"],"upstream_identities":[{"resource_id":"deeptutor","release_or_commit":"44fa7a1552b88f9d8ce2c22259128a15ae2eb0c8","tag":"v1.5.8"}],"inspected_artifacts":["V5_B_UPSTREAM_DEEPTUTOR_RESEARCH_REPORT.md","https://github.com/HKUDS/DeepTutor/tree/44fa7a1552b88f9d8ce2c22259128a15ae2eb0c8"],"verified_findings":["Stable entry IDs, refs-required batch preflight, ID-set incremental updates and editable review are useful independent reimplementation references.","JSONL trace, physical delete/overwrite, process-only run/undo and surface-level L3 refs do not meet Shiliu authority requirements.","SQLite must remain authority and filesystem should be immutable derived export only."],"corrected_prior_assumptions":["Remove copy_and_adapt from the recommended boundary; no source copy or dependency is needed.","DeepTutor L1 trace is not equivalent to Shiliu L1 Evidence authority."],"decision_effect":"Propose DeepTutor as reference-only for V5-B and define explicit reject boundaries.","adoption_effect":[{"resource_id":"deeptutor","status":"proposed_pending_main_acceptance","recommended_modes":["reimplement_pattern","test_reference","product_or_behavior_reference"],"rejected_modes":["dependency","source_copy"]}],"resulting_artifacts":["V5_B_UPSTREAM_DEEPTUTOR_RESEARCH_REPORT.md","V5_B_VERSION_CHARTER.md","V5_B_STAGE_1_CONTRACT.md"],"limitations":["Six selected memory test files were source-reviewed but did not execute because sparse package collection lacked non-memory imports.","No provider or full upstream install was performed."],"next_research_triggers":["before_any_upstream_code_test_or_ui_copy","if_stage_contract_needs_an_unreviewed_deeptutor_mechanism"],"planning_only":true,"source_audit_completed":true,"tests_reviewed":true,"tests_executed":false,"provider_runs_performed":false,"implementation_authorized":false}
```

### 10.6 Research Log：WeKnora episode

```json
{"event_id":"UR-20260804-018","recorded_at":"2026-08-04","event_time_precision":"date_only","event_type":"bounded_fixed_commit_source_and_test_review","stage":"V5-B startup","session_role":"V5-B_version_session","trigger":"V5-B Topic Page design requires bounded evidence for page revisions, async generation/update/rebuild state, observability and inter-page relationships.","resource_ids":["weknora"],"research_scope":"Official fixed-commit sparse source audit of Wiki page/revision/repository/service, durable task queue/recovery/ingest/finalize, frontend API/browser/revision/status tests; reject enterprise platform scope.","source_strength":["official_source","official_tests","official_license","official_release"],"upstream_identities":[{"resource_id":"weknora","release_or_commit":"fcc4cd6a9f29a94818e481b3a604f44ce51c55e2"},{"resource_id":"weknora_release","release_or_commit":"v0.7.1@c64a48647cd6f7eb8b0fb020b2e8fec74ee375fb"}],"inspected_artifacts":["V5_B_UPSTREAM_WEKNORA_RESEARCH_REPORT.md","https://github.com/Tencent/WeKnora/tree/fcc4cd6a9f29a94818e481b3a604f44ce51c55e2"],"verified_findings":["Optimistic page versioning plus atomic superseded snapshots and revert-as-new-version are useful Shiliu-native patterns.","Durable pending operations, dedup, failure count, dead letters and startup recovery are useful later refresh/rebuild references.","Enterprise tenancy/RBAC/connectors, RAG replacement, GraphRAG default, Redis active authority and rebuild failure log-and-drain are rejected."],"corrected_prior_assumptions":["No WeKnora source/UI copy is needed; product behavior and independent reimplementation references are sufficient.","Wiki SourceRefs/ChunkRefs do not satisfy Shiliu claim-level Evidence lineage."],"decision_effect":"Propose bounded reference-only WeKnora adoption and keep Stage 1 to durable BuildRun rather than a general async platform.","adoption_effect":[{"resource_id":"weknora","status":"proposed_pending_main_acceptance","recommended_modes":["product_or_behavior_reference","reimplement_pattern","test_reference"],"rejected_modes":["dependency","source_copy","enterprise_platform","rag_replacement"]}],"resulting_artifacts":["V5_B_UPSTREAM_WEKNORA_RESEARCH_REPORT.md","V5_B_VERSION_CHARTER.md","V5_B_STAGE_1_CONTRACT.md"],"limitations":["Only two pure frontend status tests were executed; Go tests were source-reviewed but not run.","No provider Wiki generation or production queue was exercised."],"next_research_triggers":["before_any_upstream_code_test_or_ui_copy","before_stage_2_async_refresh_if_contract_needs_unreviewed_mechanisms"],"planning_only":true,"source_audit_completed":true,"tests_reviewed":true,"tests_executed":true,"tests_executed_scope":"2 pure frontend status refresh tests","provider_runs_performed":false,"implementation_authorized":false}
```

## 11. 请求 V5 Main 的有限审查

请求 V5 Main 一次性审查并明确接受/修订/拒绝：

1. V5-B Charter 的使命、冻结边界和五 Stage 依赖；
2. DeepTutor / WeKnora 固定 Commit、License 与 reference-only adoption decisions；
3. L1 Evidence authority、revision-first L2/L3、Candidate promotion 和 SQLite/filesystem mapping；
4. Stage 1 Contract 的 vertical slice、无 Provider成功标准和实施排除项；
5. 是否授予 Stage 1 临时-DB/no-provider/runtime/API/minimal UI/test 的有限实施权限。

在 Main 明确决定前：

```yaml
charter: not_accepted
stage_1: not_accepted
stage_1_implementation: not_authorized
provider: not_authorized
live_migration: not_authorized
```
