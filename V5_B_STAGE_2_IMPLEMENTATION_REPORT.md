# 拾流 V5-B Stage 2 Implementation Report

```yaml
report_status: accepted_by_v5_main
version: V5-B
stage: 2
title: Knowledge Lifecycle, Revalidation and Durable Refresh
date: 2026-08-04
branch: codex/v5-b
accepted_stage_1_commit: abe002ab95025b38565464e69ca8b3abe651f1ae
stage_2_contract_commit: a931e2863f3ae245205c1f64bad7e45d25f03225
stage_2_acceptance_and_authorization_record: c6317a5_on_codex_v5_main_not_cherry_picked
stage_2_implementation_acceptance_record: 2d89dfc_on_codex_v5_main_not_cherry_picked
contract_status: accepted_by_v5_main
implementation_authorized: true
implementation_status: accepted_by_v5_main
accepted_implementation_commit: f879c80c0f547195a40d6804b6057debd077d11a
main_independent_verification: 17_stage_1_plus_stage_2_core_tests_passed
main_verified_live_db_sha256: b156448d688c37efbf496948d6ebfc43a685858cac54398fe1e05a9787ffe55d
schema_source_version: 12
provider_runs_performed: false
provider_cost_usd: 0
new_dependencies: false
live_database_migrated_or_mutated_by_this_session: false
self_accepted: false
```

## 1. 结论

V5 Main 已正式接受 commit `f879c80c0f547195a40d6804b6057debd077d11a`。已完成的 accepted Stage 2 Contract no-provider/temp-DB 产品闭环为：

```text
changed Evidence → append-only revalidation → visible stale projection
→ reviewed update Candidate → new immutable FactRevision
→ durable refresh intent/claim/fence → ArtifactRevision + PageRevision draft
→ Page edit/history/diff/revert-as-new → explicit publish-or-return
→ preserved Fact → current L1 Evidence → transcript timestamp drill-down
```

新 Evidence、用户建议和 late worker result 都不能静默改写 Fact 或 published Page。Stage 1 authority 和兼容性保持。Stage 2 acceptance record为Program-only `codex/v5-main@2d89dfc`，未merge/cherry-pick；Stage 3仍未实施。

## 2. Authority 与边界遵循

- 实施依据为 accepted Contract commit `a931e2863f3ae245205c1f64bad7e45d25f03225` 与 Main record `codex/v5-main@c6317a5`；Program-only commit 未 merge/cherry-pick。
- DeepTutor `44fa7a1552b88f9d8ce2c22259128a15ae2eb0c8`（Apache-2.0）与 WeKnora `fcc4cd6a9f29a94818e481b3a604f44ce51c55e2`（MIT + listed third-party）只作为已接受 reference-only patterns；没有 upstream source/test/UI copy、dependency 或 additional checkout。
- 没有新 dependency、Provider/paid service、credential/Keychain 访问、live DB migration/content mutation、push/merge/tag。
- 没有 general queue、Redis authority、enterprise Wiki/RAG/RBAC/Connector、Artifact retrieval/reuse/seed、personal/corpus workspace、relations/product eval、V5-C/V5-D。

## 3. Concrete implementation

### 3.1 Schema 12 与 lifecycle authority

schema source 12 新增：

- `research_knowledge_fact_states`
- `research_knowledge_revalidation_observations`
- `research_knowledge_update_candidates`
- `research_knowledge_lifecycle_decisions`
- `research_knowledge_conflict_observations`
- `research_knowledge_update_operations`
- `research_topic_page_revision_decisions`
- `research_knowledge_exports`

schema 11 Topic Page family 被 temp-DB migration 扩展为 latest working version + independently published version；Page review支持后续 revision decision，revision保存 source kind/revert lineage。Observation、Decision、Fact/Artifact/Page revision和links保持 append-only/immutable；可变 head/state只存在于明确 projection/operation row。

### 3.2 Revalidation、stale/conflict 与 update Candidate

- revalidation使用现有 `PersistentEvidenceAuthority` 重新 materialize当前 source artifact，追加既有 `EvidenceValidation` 与 Stage 2 observation；required Evidence任一 stale/missing/invalid/error 即投影为 stale。
- revalidation不修改旧 Evidence、FactRevision、ArtifactRevision、PageRevision或 published pointer。source-rebind candidate按同一 boundary去重；恢复 current 时关闭未审查的 stale candidate。
- temporal/viewpoint 空值为 `unknown`并保守 overlap；明确不相交的 scope不符合 conflict eligibility。confirmed conflict需要两个不同 Fact family、current-grounded Evidence、scope overlap与显式用户决定。
- `user_correction / retire / supersede / potential_conflict` 均先形成 durable Candidate；Accept/Reject/Edit使用 expected version和CommandReceipt。改写 claim若没有 deterministic current Evidence quote支持则保持 `needs_revalidation`。

### 3.3 Fact、Artifact 与 Page immutable revisions

- accepted correction/supersede在expected Fact head/state CAS下创建新 FactRevision/evidence links与lifecycle Decision；旧 revision永久可读。retire只追加 Decision/state，不物理删除。
- accepted lifecycle change先持久 refresh intent；运行后只从current accepted Fact head构建new ArtifactRevision和Page draft revision，并保留exact L1 links。
- Page edit只允许presentation fields与既有eligible Fact blocks；history读取immutable revisions/decisions，diff为deterministic unified line projection，revert复制历史内容为`max(version)+1`新 draft。
- latest working与published pointer分离；只有explicit publish更新published pointer，return/failure保留旧published revision。

### 3.4 Durable update/rebuild operation

专用 `research_knowledge_update_operations`（非通用 queue）在执行前保存 canonical input/hash、dedup key、expected Fact/Artifact/Page heads、source boundary、claim generation/lease、attempt/limit与状态。

- same command/payload回放，same command/different payload fail closed；dedup不重复创建intent。
- explicit bounded recovery扫描pending/retry_wait/expired running；restart后的新 `Application`实例可恢复持久 intent。
- transient `OSError`进入bounded retry，耗尽为dead-letter；semantic/data blocker进入needs-user并可显式resolve；cancel/superseded有可解释terminal state。
- finalize前复核claim generation、owner lease、expected heads/source boundary；stale/late result进入superseded且不产生revision/head。
- output revisions + links + working head + terminal operation + Event + Receipt同事务；fault injection证明不留orphan或假success。

### 3.5 Filesystem export closure

Main clarification已在Stage 2交付，而非转移Stage 5：

- 按 Topic Page revision ID + content hash生成immutable Markdown/JSON；路径和SQLite export record均记录revision/hash。
- temp file写入、flush/fsync后replace；SQLite仍是唯一canonical authority。
- export是独立observable operation；filesystem failure不回滚revision、不改变head/publish、不污染canonical state。
- 同一command/revision/hash failure后可安全重试并产生相同addressed output；无batch export/general file pipeline。

### 3.6 API / minimal UI

新增public API覆盖 revalidate、propose/review Fact update、run/recover/resolve operation、Page edit/history/diff/revert和export。`/research` minimal UI展示Fact/Page currentness、stale/conflict/update badges、old/new update review、operation attempts/errors/安全下一步、Page draft/published/history/diff/revert/export，并保留citation drill-down。

## 4. Gates A–E evidence

| Gate | 实施结果 |
| --- | --- |
| A — Revalidation authority | current→stale→current append-only observations、affected projection、dedup/mismatch/fault、no-auto-mutation通过 |
| B — User lifecycle | correction/retire/supersede、eligibility、unsupported edit、scope/conflict、CAS/rollback/history通过 |
| C — Page revision product | new Artifact/Page lineage、edit/history/diff/revert-as-new、draft/published separation、publish guard通过 |
| D — Durable refresh/fencing | durable intent、restart recovery、claim fence、retry/dead-letter/needs-user、fault atomicity通过 |
| E — Compatibility/non-actions | public API/UI journey、Stage 1/affected/default no-provider regression通过；live hash equality窗口因外部sync为infrastructure-invalid，见§6 |

## 5. Tests 与静态验证

### Stage 1 + Stage 2 directed

```text
PYTHONPATH=src <project-venv>/python -m pytest -q \
  tests/test_v5_b_stage1_knowledge_workspace.py \
  tests/test_v5_b_stage2_knowledge_lifecycle.py
```

结果：`17 passed`。Stage 2的9项测试覆盖 schema/reentry/v11 migration、revalidation/no-auto-mutation、correction/retire/supersede/conflict、Page history/diff/revert/publish、rollback、crash/restart recovery/late fence/retry/dead-letter/needs-user、export failure/retry和public API/UI journey。最后将recovery改为新 `Application`实例后，该单例再次通过。

### Affected Search / Ask / Research regression

```text
PYTHONPATH=src <project-venv>/python -m pytest -q \
  tests/test_v5_a_stage1_research_api.py \
  tests/test_v5_a_stage1_research_kernel.py \
  tests/test_v5_a_stage2_inner_loop.py \
  tests/test_v5_a_stage3_outer_audit.py \
  tests/test_v5_a_stage4_operational_control.py \
  tests/test_v5_b_stage1_knowledge_workspace.py \
  tests/test_v5_b_stage2_knowledge_lifecycle.py
```

结果：`154 passed`。该集合覆盖受影响的 V5-A Research/Search/Ask public API、kernel/inner loop/outer audit/operational control和Stage 1/2 knowledge workspace；无Provider。

### Submission-boundary default suite（只运行一次）

```text
PYTHONPATH=src <project-venv>/python -m pytest -q
```

结果：`1703 passed, 4 deselected, 7 warnings in 144.74s`；repository default filter为`not external_artifact and not live_provider`。warnings为既有FastAPI TestClient/httpx与multiprocessing fork deprecation。

静态检查：相关Python `py_compile`、`node --check src/shiliu/static/research.js`、`git diff --check`通过。最后只补强一个test restart实例化，未改产品代码，按cadence未重复完整套件。

## 6. Live DB sentinel / non-action evidence

### 结论

本Session没有对live DB执行Stage 2 migration或content mutation；但提交窗口内存在测试外的定时sync，因此before/after hash equality无法作为有效机械证据，分类为`infrastructure-invalid`而不是伪报pass。

### 只读证据

- suite前 SHA-256：`fc828d4cba9c9320c6dbeb1a345b1c8a604a9018b8f062f5ca4f43f8754191cd`；size `94588928`。
- suite后 SHA-256：`b156448d688c37efbf496948d6ebfc43a685858cac54398fe1e05a9787ffe55d`；size未变，mtime为本地`2026-08-04 16:58:37`。
- live DB仍为schema version 10；没有Stage 2 tables，没有`pre-v12` backup。
- 已运行的`app.shiliu.sync`在本地16:57:18–16:58:37写入live `sync_runs` id 376并更新video/retrieval state；时间与hash变化吻合。
- 所有测试Application均显式使用pytest `app_paths`/temporary DB；代码搜索没有默认 `Application()` / default `create_web_app()`测试路径。

没有停止、恢复或改写外部service/live DB，也没有为了制造sentinel相等而做破坏性动作。

## 7. Produced files

产品：

- `src/shiliu/research/knowledge_lifecycle.py`（new）
- `src/shiliu/research/schema.py`
- `src/shiliu/research/knowledge_contracts.py`
- `src/shiliu/research/knowledge_service.py`
- `src/shiliu/db.py`, `src/shiliu/app.py`, `src/shiliu/web.py`
- `src/shiliu/templates/research.html`, `src/shiliu/static/research.js`

测试：

- `tests/test_v5_b_stage2_knowledge_lifecycle.py`（new）
- Stage 1/V5-A/library/taxonomy schema-version expectations更新为12。

治理：

- 更新 `V5_B_VERSION_CHARTER.md`, `V5_B_STAGE_2_CONTRACT.md`, `V5_B_CURRENT_STATE.md`, `V5_B_DECISION_LEDGER.md`
- 新建且仅新建本 `V5_B_STAGE_2_IMPLEMENTATION_REPORT.md`

## 8. Honest limits classification

| Classification | Item |
| --- | --- |
| not exercised | live schema-10→12 migration；未授权 |
| unproven | multi-process Stage 2 claim/head race stress；当前为SQLite transaction/CAS/claim-generation mechanics |
| not exercised | browser visual/accessibility专项 |
| not exercised | Provider validator与生成质量；cost为USD 0 |
| bounded limitation | 无自动semantic conflict suggestion；仅deterministic scope + explicit user decision |
| bounded limitation | 无常驻background worker；durable intent + explicit bounded recovery满足Contract core |
| infrastructure-invalid | live hash equality window被外部`app.shiliu.sync`干扰；正向no-migration证据仍成立 |
| excluded | Stage 3–5、V5-C/V5-D与V5-A compound-query known limitation |

没有已知 `core failure`、`implementation failure` 或 `provider failure`。

## 9. Main acceptance 与下一 Gate

V5 Main的独立验收结果：

1. Stage 1 + Stage 2 core：`17 passed`；
2. Main独立测试窗口live DB SHA-256前后均为`b156448d688c37efbf496948d6ebfc43a685858cac54398fe1e05a9787ffe55d`；
3. live schema仍为10、Stage 2 table count为0、integrity ok；
4. reported `154 passed` affected与`1703 passed, 4 deselected` default no-provider结果被接受为supporting evidence；
5. 先前sync污染窗口的`infrastructure-invalid`分类被接受，后续独立window已补齐non-action evidence；
6. revision/hash export clarification已交付，known honest limits不触发Stage 2 rework。

```yaml
stage_2_status: accepted_by_v5_main_at_2d89dfc
stage_2_accepted_commit: f879c80c0f547195a40d6804b6057debd077d11a
stage_3_contract_preparation_authorized: true
stage_3_implementation_authorized: false
next_action: limited_v5_main_stage_3_target_boundary_review
```
