# 拾流 V5-B Current State

```yaml
document_status: stage_1_implementation_submission_pending_v5_main_acceptance
version: V5-B
version_session: Shiliu V5-B Version Session
updated_at: 2026-08-04
branch: codex/v5-b
version_starting_commit: b85340540cb92c2e46bfb8619598e7aa987171d4
stage_1_starting_commit: 4efaed413cb2fd9d2eeabe411da96f5132ce6276
accepted_v5_a_code_baseline: 04e5c5bbb94311a00f6efafa142908fd7b2b97de
main_acceptance_record: e73ddd2_on_codex_v5_main_not_cherry_picked
charter_status: accepted_by_v5_main
stage_1_contract_status: accepted_by_v5_main
stage_1_implementation_authorized: true
stage_1_implementation_status: implemented_pending_v5_main_acceptance
schema_source_version: 11
provider_runs_performed: false
credentials_or_keychain_accessed: false
live_database_mutated: false
```

## 1. 当前一句话状态

V5-B Charter、五 Stage 顺序、DeepTutor/WeKnora reference-only 边界和 corrected Stage 1 Contract 已被 V5 Main 接受；Stage 1 已在 `codex/v5-b` 实现并通过 directed、affected 与 default no-provider/temp-DB 回归，现请求有限实现验收，不自我接受且不请求 Stage 2。

## 2. 已完成 Stage 1 产品路径

```text
V5-A Research Task
→ immutable KnowledgeDelta Event snapshot
→ durable Candidate intake
→ Accept / Reject / Edit-as-new-candidate
→ server-owned current Evidence validation
→ initial immutable Fact revision
→ synchronous deterministic Artifact BuildRun/revision
→ synchronous deterministic first Topic Page BuildRun/revision
→ expected-version publish-or-return review
→ Fact → EvidenceIdentity/EvidenceUse/Validation → video/timestamp/transcript drill-down
```

实现要点：

- schema 11 增加 Candidate/Decision、Fact family/revision/evidence link、Artifact family/revision/fact link、Topic Page family/revision/fact link/PageReviewDecision 与 KnowledgeBuildRun；
- V5-A Candidate Delta Event 继续是 candidate-only immutable source，V5-B intake 持久保存 kind、snapshot、boundary、item/hash 和完整 Task/Goal/Attempt/Checkpoint/Result/Artifact lineage；
- Accept 在同一事务中重新 materialize 当前 source artifact、追加 `research_evidence_validations`、创建首个 Fact revision/evidence links、转换 Candidate、追加 Decision/Event/Receipt；任一结果不是 `current` 都只进入 `needs_revalidation`；
- Edit 创建 child Candidate，保留 parent，edited claim 固定为 `needs_revalidation`；Stage 1 没有 edited-claim grounded validator；
- Artifact/Page 只接受本 Task 已 accepted 且 promotion validation 为 current 的 FactRevision；canonical body、source result/boundary/corpus snapshot、content hash 均在 SQLite；
- BuildRun 先以 deterministic identity 持久为 `running`，再在独立原子事务写 output revision、terminal state、Event 与 Receipt；reservation 后 crash 可由同一命令重启，output/receipt fault 整体 rollback；
- minimal API/UI 提供 intake、Candidate review、Artifact/Page build、Page publish-or-return、build status 和 transcript citation drill-down。

## 3. 明确仍未实现

- Page content edit/history/diff/revert/archive 和后续 revision 命令；
- Fact correction/retire/supersede 产品命令；
- filesystem export command/failure/retry gate；
- async late-result fencing、通用 update/rebuild、后台 recovery/dead-letter；
- Stage 2–5 的 revalidation propagation、conflict、reuse/refresh/seed、personal/corpus workspace；
- V5-C/V5-D 能力；
- Provider、paid service、credential/Keychain、live DB migration/content mutation；
- upstream source/test/UI copy、直接依赖或新依赖。

## 4. 验证状态

### Stage 1 directed

```text
PYTHONPATH=src <existing-project-venv>/python -m pytest -q \
  tests/test_v5_b_stage1_knowledge_workspace.py
```

结果：`8 passed`。覆盖 schema 11/reentrant temp DB、minimal UI、direct service 与完整 public API vertical paths、duplicate/payload mismatch、cross-task/forged Fact、source Event/revision immutability、Edit/Reject、stale/missing/invalid/error fail closed、accept rollback、BuildRun reservation/restart/output rollback、Page review rollback/expected-version guard、citation drill-down 与 FK check。

### Accepted V5-A affected set

```text
PYTHONPATH=src <existing-project-venv>/python -m pytest -q \
  tests/test_v5_a_stage2_inner_loop.py \
  tests/test_v5_a_stage4_operational_control.py \
  tests/test_v5_a_stage5_product_completion.py
```

结果：`73 passed`。

### Default no-provider suite

```text
PYTHONPATH=src <existing-project-venv>/python -m pytest
```

最终结果：`1694 passed, 4 deselected, 7 warnings in 111.24s`；filter 为 repository `not external_artifact and not live_provider`。

静态检查：`node --check src/shiliu/static/research.js`、相关 Python `py_compile`、`git diff --check` 通过。既有 warning 为 FastAPI TestClient/httpx deprecation 与 multiprocessing fork deprecation。

## 5. Live DB / Provider 非动作证据

- 所有 `Application` 实例均由 pytest `app_paths` 指向 pytest 临时 state/content/database；探索 journey 使用 `TemporaryDirectory`；没有调用 `AppPaths.defaults()` 初始化产品数据库。
- 未运行 CLI/server against default paths，未读取或写入 live database/live content。
- 未调用 `provider()`、未访问 Keychain/credential、未发起付费或网络模型请求。
- schema 11 仅作为 migration source 与 temp-DB tests 执行；live schema 10 未迁移。
- Program-only `codex/v5-main@e73ddd2` 未 merge/cherry-pick；未 push/merge/tag。

## 6. 当前未证明项

- actual live schema-10 database migration、backup size/time 与真实内容兼容性未授权、未执行；
- multi-process并发 review/build race 未单独压测；当前机械证据覆盖 command receipt、expected-version、single-process lock、transaction/unique constraint、fault/restart；
- Stage 1 没有 edited-claim server validator，因此 edited Candidate 不能 Accept；
- UI 通过 HTTP/static contract tests 与 JavaScript syntax check，未做浏览器视觉/可访问性专项验收；
- Provider 生成质量、真实长时间运行与 upstream full suites 未执行；
- V5-A accepted compound-query retrieval limitation 仍未解决且不自动属于 V5-B。

## 7. 当前 Gate

```yaml
charter_accepted: true
stage_1_contract_accepted: true
stage_1_implementation_authorized: true
stage_1_self_accepted: false
stage_1_main_acceptance: pending
stage_2_authorized: false
next_action: limited_v5_main_stage_1_implementation_acceptance_review
```

详细实现、文件和最终验证以 `V5_B_STAGE_1_IMPLEMENTATION_REPORT.md` 为准。
