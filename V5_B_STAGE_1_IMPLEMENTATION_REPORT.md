# 拾流 V5-B Stage 1 Implementation Report

```yaml
report_status: accepted_by_v5_main
version: V5-B
stage: 1
title: Evidence-backed Topic Page Vertical Slice
date: 2026-08-04
branch: codex/v5-b
version_starting_commit: b85340540cb92c2e46bfb8619598e7aa987171d4
stage_1_starting_commit: 4efaed413cb2fd9d2eeabe411da96f5132ce6276
accepted_v5_a_code_baseline: 04e5c5bbb94311a00f6efafa142908fd7b2b97de
stage_1_authorization_record: e73ddd2_on_codex_v5_main_not_cherry_picked
stage_1_acceptance_record: 2f4dabf_on_codex_v5_main_not_cherry_picked
charter_status: accepted_by_v5_main
contract_status: accepted_by_v5_main
implementation_authorized: true
implementation_status: accepted_by_v5_main
implementation_commit: abe002ab95025b38565464e69ca8b3abe651f1ae
main_independent_verification: 81_stage_1_plus_affected_tests_passed
main_verified_live_db_sha256: fc828d4cba9c9320c6dbeb1a345b1c8a604a9018b8f062f5ca4f43f8754191cd
provider_runs_performed: false
live_database_migrated_or_mutated: false
self_accepted: false
```

## 1. 结论

已实现 corrected Stage 1 Contract 的完整 no-provider vertical path：

```text
Research Task
→ immutable KnowledgeDelta Candidate source/intake
→ Accept / Reject / Edit-as-new-candidate review
→ server-owned current Evidence validation
→ accepted initial Fact revision
→ deterministic initial Artifact revision
→ deterministic first Topic Page revision
→ expected-version publish-or-return review
→ transcript/video timestamp citation drill-down
```

Candidate 不会自动 promotion；edited claim 没有 server validator 时不能 Accept；Fact/Artifact/Page content revision 不可原地修改或删除；Page 只提供首版 review，不提供 Stage 2 lifecycle 命令。

## 2. Authority 与范围遵循

- 执行依据是 V5 Main 消息对 Charter、五 Stage、上游边界与 `4efaed4` Contract 的接受/授权；`codex/v5-main@e73ddd2` 仅作为 Program record，未 merge/cherry-pick。
- DeepTutor `44fa7a1552b88f9d8ce2c22259128a15ae2eb0c8`（Apache-2.0）和 WeKnora `fcc4cd6a9f29a94818e481b3a604f44ce51c55e2`（MIT + listed third-party）仅作为已接受 reference-only pattern；实现没有 upstream dependency，也没有复制 upstream source/test/UI。
- 没有引入新依赖。
- 没有 Provider/paid-service 调用，没有 credential/Keychain 访问。
- 没有 live DB migration/read-write 或 live content mutation；schema 11 只在 temp DB 初始化/迁移测试中执行。
- 没有 push、merge、tag，没有实现或声明 Stage 2–5、V5-C 或 V5-D。

## 3. Concrete implementation

### 3.1 Schema 11 与 immutable foundations

新增 13 个 Stage 1 tables：

- `research_knowledge_candidates`
- `research_knowledge_review_decisions`
- `research_grounded_facts`
- `research_fact_revisions`
- `research_fact_evidence_links`
- `research_knowledge_artifacts`
- `research_knowledge_artifact_revisions`
- `research_artifact_fact_links`
- `research_topic_pages`
- `research_topic_page_revisions`
- `research_topic_page_fact_links`
- `research_topic_page_review_decisions`
- `research_knowledge_build_runs`

关键约束：

- Candidate 持久保存 V5-A source Event/snapshot/kind/boundary/delta/item hash 和 Task/Goal/Attempt/Checkpoint/Result/ProvisionalArtifact lineage；只有 status/state version/updated time 可变，source lineage 与 claim 不可变且不能 delete。
- Candidate Delta source Event 增加针对该 event type 的 update/delete trigger，防止长期来源被事后改写。
- Fact/Artifact stable family 与初始 revision 分离；revision、Evidence/fact links、review decisions 均有 update/delete trigger。
- Fact revision 有 temporal/viewpoint 与 parent/supersedes hooks，但 Stage 1 没有 correction/retire/supersede command。
- Artifact revision 保存 source result IDs、boundary hashes、Evidence source-version corpus snapshot 和 content hash。
- Topic Page family 保存唯一 slug、current version 1 和 review projection；PageRevision content immutable。
- BuildRun 保存 deterministic input hash/JSON、status/attempt/output/error/timestamps；identity/input 不可修改或删除。

既有 schema-version assertions 更新为 11；旧 V5-A schema/migration tests 仍执行其原始 migration scenario、backup、integrity 和 FK checks。

### 3.2 Candidate intake 与 promotion

`ResearchKnowledgeService.intake_candidates`：

1. 要求 Task 已有 V5-A `candidate_deltas_materialized` durable boundary；
2. 验证 schema version、task/attempt、candidate-only authority、snapshot hash、每个 delta hash及 source CommandReceipt；
3. 只选择 `KnowledgeDelta`；
4. server-side 将 citation EvidenceIdentity 映射回同一 task/attempt 且属于 snapshot 的 EvidenceUse；
5. 以 source Event + item hash 形成 deterministic Candidate ID，并与 Event/Receipt 同事务提交。

Candidate review：

- Reject：append Decision/Event/Receipt并转换为 `rejected`，不删除 source。
- Edit：创建 child Candidate，parent 转为 `superseded`；child 固定 `needs_revalidation`，不创建 Fact。
- Accept：逐条调用 `PersistentEvidenceAuthority.observe` 从 filesystem source artifact 重建 current Evidence；追加 promotion-time EvidenceValidation。只有所有 EvidenceUse/Identity lineage正确、引用非空且 outcome 全为 `current`，才在同事务创建 Fact family/revision/evidence links、Decision/Event/Receipt并转换 Candidate。
- `stale/missing/invalid/error` 共用 fail-closed branch：Candidate 进入 `needs_revalidation`，Fact 不产生。

### 3.3 Deterministic Artifact / Topic Page BuildRun

Artifact build 只接受本 Task 的 `accepted_current` FactRevision，且 origin Candidate 必须为 accepted、promotion EvidenceValidation 必须非空且全部 current。Canonical body 包含 Fact blocks、citations、limitations/unresolved 与 source task/result/boundary/corpus snapshot。

Page build 只接受本 Task ArtifactRevision；创建 stable Page family、deterministic slug、immutable version-1 PageRevision 和 exact Fact links。

同步 BuildRun 使用两个受控事务：

1. deterministic `(task, kind, input_hash)` reservation 先以 `running` 持久；
2. output revision + links + BuildRun `succeeded` + Event + CommandReceipt 同事务 terminalize。

因此 reservation 后 simulated crash 留下可重启的同一 BuildRun；output 或 receipt 前 fault 会 rollback 整个 finalize transaction，不留下 orphan revision/terminal state。Stage 1 不包含 background recovery、通用 retry/dead-letter 或 async late-result fencing。

### 3.4 API 与 UI

新增 API：

- `GET /api/research/product/tasks/{task_id}/knowledge`
- `POST /api/research/product/tasks/{task_id}/knowledge/intake`
- `POST /api/research/product/tasks/{task_id}/knowledge/candidates/{candidate_id}/review`
- `POST /api/research/product/tasks/{task_id}/knowledge/artifacts`
- `POST /api/research/product/tasks/{task_id}/knowledge/pages`
- `POST /api/research/product/tasks/{task_id}/knowledge/pages/{page_id}/review`

现有 `/research/{task_id}` 增加最小 Stage 1 panel：

- receive KnowledgeDelta；
- Candidate currentness/source/status 与 Accept/Reject/Edit-as-new；
- accepted Fact citation state、video timestamp 和 subtitle source drill-down；
- deterministic Artifact/Page build；
- Page version-1 publish-or-return review；
- persisted BuildRun projection。

UI 不提供 Page edit/history/diff/revert/archive、Fact lifecycle、filesystem export 或 async update/rebuild。

## 4. Reliability / fault matrix evidence

| Contract behavior | Mechanical evidence |
| --- | --- |
| Candidate intake exact-once | second command reuses deterministic Candidate; row count remains one |
| Command replay/payload hash | identical Candidate/Artifact/Page review command returns receipt response; mismatched payload raises typed conflict |
| Source snapshot integrity | snapshot/delta hash + source receipt checks; Candidate Delta Event update rejected by trigger |
| Current-only Fact | real current path succeeds; stale/missing/invalid/error each produce `needs_revalidation` and zero Fact |
| Edit-as-new | child lineage retained; edited child cannot Accept without validator; Reject creates no Fact |
| Cross-task/forged Fact | Artifact build rejects Fact revision not accepted/current-grounded in target Task |
| Accept atomicity | fault after initial FactRevision rolls back Fact, Candidate transition, Decision/Event/Receipt; same command then succeeds once |
| Durable BuildRun restart | crash after reservation leaves `running` attempt 1 and no output; retry reaches `succeeded` attempt 2 with one revision |
| Build output rollback | fault after initial PageRevision leaves zero revisions and running BuildRun; retry creates one version-1 revision |
| Page review guard | fault after Decision leaves draft and zero decisions; retry succeeds; late different review conflicts and creates no orphan decision |
| Immutability | FactRevision, Candidate lineage and source Candidate Delta Event update attempts abort |
| Restart projection | new service/Application reads Candidate/Fact/Artifact/Page/BuildRun from SQLite; no process-only state authority |
| FK/integrity | temp-DB `PRAGMA foreign_key_check` empty; old migration/default checks green |

## 5. Tests executed

### Stage 1 directed

```text
PYTHONPATH=src /Users/elliot/new-systems/agent-job-prep/Shiliu/.venv/bin/python -m pytest -q \
  tests/test_v5_b_stage1_knowledge_workspace.py
```

Result: `8 passed`（包含完整 public API vertical path）。

### Accepted V5-A affected set

```text
PYTHONPATH=src /Users/elliot/new-systems/agent-job-prep/Shiliu/.venv/bin/python -m pytest -q \
  tests/test_v5_a_stage2_inner_loop.py \
  tests/test_v5_a_stage4_operational_control.py \
  tests/test_v5_a_stage5_product_completion.py
```

Result: `73 passed`.

### Default suite

```text
PYTHONPATH=src /Users/elliot/new-systems/agent-job-prep/Shiliu/.venv/bin/python -m pytest
```

Repository filter: `not external_artifact and not live_provider`.

Final result: `1694 passed, 4 deselected, 7 warnings in 111.24s`.

### Static/bounded checks

- `node --check src/shiliu/static/research.js` — pass.
- Python `py_compile` for Stage 1 service/contracts/schema — pass.
- `git diff --check` — pass.
- Exploratory no-provider `TemporaryDirectory` journey — terminal Task → accepted Fact → Artifact → Page → published; `PRAGMA foreign_key_check=[]`.

Warnings are existing FastAPI TestClient/httpx deprecation and multiprocessing fork deprecation; no Stage 1 warning/error was suppressed.

## 6. Live DB non-action evidence

- Every test `Application` received `tests/conftest.py::app_paths`, whose database is under pytest temporary state; the exploratory journey used Python `TemporaryDirectory`.
- No command ran `Application()` against default paths, the Shiliu CLI/server, or a live content directory.
- No live DB file was named, opened, migrated, copied or mutated by this session.
- No `provider()` path was called; no credential/Keychain command or network model request was executed.
- The only external project path used at runtime was the existing project `.venv` Python interpreter; test imports were forced to this worktree via `PYTHONPATH=src`.

## 7. Files

### Product/schema/runtime

- `src/shiliu/db.py`
- `src/shiliu/research/schema.py`
- `src/shiliu/research/knowledge_contracts.py`
- `src/shiliu/research/knowledge_service.py`
- `src/shiliu/app.py`
- `src/shiliu/web.py`
- `src/shiliu/templates/research.html`
- `src/shiliu/static/research.js`
- `src/shiliu/static/research.css`

### Tests

- `tests/test_v5_b_stage1_knowledge_workspace.py`
- schema-version/backup expectation updates in `tests/test_library.py`, `tests/test_taxonomy_phase01.py`, and V5-A Stage 1–4 migration tests.

### Authority/session docs

- `V5_B_VERSION_CHARTER.md`
- `V5_B_STAGE_1_CONTRACT.md`
- `V5_B_CURRENT_STATE.md`
- `V5_B_DECISION_LEDGER.md`
- `V5_B_STAGE_1_IMPLEMENTATION_REPORT.md` (only new report)

No Program authority, Registry/Research Log, upstream checkout/dependency or extra amendment/recovery report was modified/created.

## 8. Honest unproven items

1. Live schema-10 migration/backup/content behavior is not authorized and not proven; schema 11 is proven only on temporary databases and existing synthetic migration cases.
2. Multi-process concurrent Candidate/Page review and concurrent BuildRun finalization were not separately stress-tested. SQLite `BEGIN IMMEDIATE`, unique constraints, receipts, expected-version checks and a process lock exist, but that is not claimed as a dedicated race evaluation.
3. Edited Candidate grounding is intentionally unimplemented; edited children remain `needs_revalidation` until a later accepted server-owned validator/lifecycle design.
4. UI was covered by HTTP/static contract tests and JS syntax, not browser visual/accessibility testing.
5. No Provider/product-quality evaluation or upstream full-suite runtime was executed.
6. Stage 2 lifecycle/revalidation propagation/export/async update mechanics and all later Stage capabilities remain unimplemented and unauthorized.
7. The accepted V5-A compound-query retrieval limitation remains unchanged.

## 9. Main acceptance record

```yaml
decision: stage_1_implementation_accepted
acceptance_authority: V5_main
acceptance_record: 2f4dabf_on_codex_v5_main_not_cherry_picked
charter_accepted: true
contract_accepted: true
implementation_authorized: true
implementation_complete: true
self_accepted: false
main_accepted: true
main_independent_verification:
  stage_1_plus_affected_tests: 81_passed
  live_db_sha256_before_and_after: fc828d4cba9c9320c6dbeb1a345b1c8a604a9018b8f062f5ca4f43f8754191cd
supporting_default_suite: 1694_passed_4_deselected
known_unproven_items: accepted_as_honest_limits_not_stage_1_rework
next_authorized_action: stage_2_contract_preparation_only
stage_2_implementation_authorized: false
```

V5 Main 已正式接受 commit `abe002ab95025b38565464e69ca8b3abe651f1ae`。已知未证明项继续作为诚实边界，不触发 Stage 1 rework。当前只准备 Stage 2 Contract；不实施 Stage 2，也不请求 live migration、Provider 或跨版本能力。
