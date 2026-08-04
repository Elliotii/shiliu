# 拾流 V5-B Current State

```yaml
document_status: stage_2_contract_submission_pending_v5_main_review
version: V5-B
version_session: Shiliu V5-B Version Session
updated_at: 2026-08-04
branch: codex/v5-b
version_starting_commit: b85340540cb92c2e46bfb8619598e7aa987171d4
stage_1_starting_commit: 4efaed413cb2fd9d2eeabe411da96f5132ce6276
accepted_v5_a_code_baseline: 04e5c5bbb94311a00f6efafa142908fd7b2b97de
stage_1_authorization_record: e73ddd2_on_codex_v5_main_not_cherry_picked
stage_1_acceptance_record: 2f4dabf_on_codex_v5_main_not_cherry_picked
charter_status: accepted_by_v5_main
stage_1_contract_status: accepted_by_v5_main
stage_1_implementation_authorized: true
stage_1_implementation_status: accepted_by_v5_main
stage_1_accepted_commit: abe002ab95025b38565464e69ca8b3abe651f1ae
main_independent_stage_1_verification: 81_passed
main_verified_live_db_sha256: fc828d4cba9c9320c6dbeb1a345b1c8a604a9018b8f062f5ca4f43f8754191cd
stage_2_contract_preparation_authorized: true
stage_2_contract_status: draft_pending_v5_main_acceptance
stage_2_implementation_authorized: false
schema_source_version: 11
provider_runs_performed: false
credentials_or_keychain_accessed: false
live_database_mutated: false
```

## 1. 当前一句话状态

V5 Main 已正式接受 V5-B Stage 1 commit `abe002ab95025b38565464e69ca8b3abe651f1ae`；当前唯一授权动作是准备 compact Stage 2 Contract。Contract 已基于既有 accepted fixed-commit research 起草，Stage 2 产品/schema/API/UI/tests 尚未实施，也未获授权。

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

## 3. Stage 2 Contract preparation

`V5_B_STAGE_2_CONTRACT.md` 将 core 收窄为依赖顺序：

1. append-only source-version/current-Evidence revalidation 与 visible stale/conflict projection；
2. update Candidate而非automatic Fact/Page mutation；
3. user Fact correction/retire/supersede与new immutable FactRevision；
4. Artifact refresh与Page edit/history/diff/revert-as-new/publish；
5. single SQLite durable operation repository，覆盖intent/dedup/restart recovery/bounded retry/dead-letter/needs-user/late-result fence；
6. changed Evidence → stale visible → reviewed update → new Fact/Artifact/Page draft → explicit publish的最小产品闭环。

filesystem export boundary保持明确，但export command/failure matrix为optional non-gating；Artifact retrieval/reuse/Research Seed、personal/corpus workspace、relations/product eval继续分别留在Stage 3/4/5。既有DeepTutor/WeKnora reports已解决所需语义，本轮没有additional upstream checkout/research report。

### 明确仍未实现

- Page content edit/history/diff/revert/archive 和后续 revision 命令；
- Fact correction/retire/supersede 产品命令；
- filesystem export command/failure/retry gate；
- async late-result fencing、通用 update/rebuild、后台 recovery/dead-letter；
- Stage 2–5 的 revalidation propagation、conflict、reuse/refresh/seed、personal/corpus workspace；
- V5-C/V5-D 能力；
- Provider、paid service、credential/Keychain、live DB migration/content mutation；
- upstream source/test/UI copy、直接依赖或新依赖。

## 4. 验证状态

### Accepted Stage 1 directed

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

### Main independent acceptance verification

- Stage 1 + affected no-provider/temp-DB：`81 passed`；
- live DB SHA-256 before/after：`fc828d4cba9c9320c6dbeb1a345b1c8a604a9018b8f062f5ca4f43f8754191cd`；
- reported default filtered suite `1694 passed, 4 deselected`被接受为supporting evidence；
- known unproven items被接受为honest limits，不触发Stage 1 rework。

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
- Program-only `codex/v5-main@e73ddd2`（authorization）与 `codex/v5-main@2f4dabf`（Stage 1 acceptance）均未 merge/cherry-pick；未 push/merge/tag。

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
stage_1_main_acceptance: accepted_at_2f4dabf
stage_2_contract_preparation_authorized: true
stage_2_contract_status: draft_pending_v5_main_acceptance
stage_2_implementation_authorized: false
next_action: limited_v5_main_stage_2_target_boundary_review
```

Stage 1 acceptance以`V5_B_STAGE_1_IMPLEMENTATION_REPORT.md`为准；当前review target仅为`V5_B_STAGE_2_CONTRACT.md`。
