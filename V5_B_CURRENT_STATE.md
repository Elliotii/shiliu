# 拾流 V5-B Current State

```yaml
document_status: stage_4_implementation_submission_pending_v5_main_review
version: V5-B
version_session: Shiliu V5-B Version Session
updated_at: 2026-08-05
branch: codex/v5-b
version_starting_commit: b85340540cb92c2e46bfb8619598e7aa987171d4
stage_1_accepted_commit: abe002ab95025b38565464e69ca8b3abe651f1ae
stage_2_accepted_commit: f879c80c0f547195a40d6804b6057debd077d11a
stage_3_accepted_commit: 2d4d3397085dd9fe1b6d01533ce5743536b23740
stage_4_contract_commit: 560293da5987478eea822197582beb3829dfa9ae
stage_4_acceptance_and_authorization_record: 9ff82483bf957f14315386621f9255b8c69ccedf_on_codex_v5_main_not_cherry_picked
charter_status: accepted_by_v5_main
stage_1_to_3_implementation_status: accepted_by_v5_main
stage_4_contract_status: accepted_by_v5_main
stage_4_implementation_authorized: true
stage_4_implementation_status: implemented_pending_v5_main_acceptance
schema_source_version: 14
provider_runs_performed_this_action: false
provider_cost_usd: 0
credentials_or_keychain_accessed: false
live_database_sqlite_accessed_or_mutated_this_action: false
live_database_hash_sentinel: e6dd58b4fd115b4768694c0de4f9e84cb1cc62f12cfc228f39c5e06705c6740f_unchanged
stage_5_authorized: false
```

## 1. 当前状态

V5 Main已接受Stage 4 Contract commit `560293da5987478eea822197582beb3829dfa9ae`并以Program-only `codex/v5-main@9ff82483bf957f14315386621f9255b8c69ccedf`授权实施；该Program commit未merge/cherry-pick。

Stage 4已在Contract内实现，当前等待Main有限验收：

```text
inspect one Personal and Corpus Workspace
→ explicit create or candidate/observation intake
→ typed authority + source boundary + confidence/expiry + immutable history
→ confirm | correct | reject | expire | tombstone | diagnose | invalidate
→ restart-stable projection with old-boundary no-resurrection
→ Search / Ask / Research / ArtifactRoute remain unchanged
```

## 2. Lean implementation shape

- schema source升至14，只新增一张`research_workspace_records` aggregate table与immutable update/delete triggers；没有supporting table。
- 一个`ResearchPersonalWorkspaceService`复用V5-A Research Task、Event、CommandReceipt和现有transaction/fault基础；没有scheduler、queue、vector index、inference/rules engine或平台拆分。
- `record_kind`、`authority_class`与typed status分离；source refs由服务器对真实Event/Trace/Result/Fact/Artifact/frozen taxonomy snapshot校验并hash。
- 三类public API：Workspace read、record create、record decision；一个Research页内compact Workspace surface。
- expiry按投影时间确定性计算；correction/reject/expire/tombstone/diagnose/invalidate均追加revision，不原地改写或物理删除。

## 3. Authority and cross-version boundary

- Explicit Memory只有`user_authored`或显式确认后的`user_confirmed`且状态current/confirmed时具user-state authority。
- inferred/focus behavioral material至少需要两个不同Research Event，先进入candidate；旧source boundary重放只写Event/Receipt，不新增revision或复活terminal lineage。
- learned/understood/familiar必须有`user_asserted=true`；watch/search/single event不能机械提升。
- Corpus observation必须引用一个frozen taxonomy snapshot，始终是`corpus_soft_prior`且`product_behavior_effect=false`。
- System Experience必须有同Task Trace与Result，只有observed→diagnosed→candidate_source/invalidated记录链；未创建或修改Skill/Policy/prompt/tool/retrieval/runtime。
- Personal Workspace未接入Search、Ask、Research knowledge projection、ArtifactRoute、prompt、budget或主动行为；V5-C/V5-D与Stage 5未启动。

## 4. Mechanical evidence

- Stage 4 compact matrix：`6 passed`。
- V5-B Stage 1–4 directed：`29 passed`。
- Stage 1–4、V5-A Research/migration、library/taxonomy affected set：`179 passed`。
- Search/Ask/public Research API affected set：`56 passed`。
- default no-provider submission suite：`1715 passed, 4 deselected, 7 warnings`。
- Python `py_compile`、`node --check`、`git diff --check`通过；docs/JSONL validation在commit前完成。
- full-suite前后只对live DB文件执行SHA-256，不建立SQLite连接；两端均为`e6dd58b4fd115b4768694c0de4f9e84cb1cc62f12cfc228f39c5e06705c6740f`，无迁移或content mutation。

## 5. Honest limits and current gate

- bounded limitation：record payload/source refs采用32 KiB/32 refs上限与结构化JSON；UI只提供compact typed create/review，不是批量管理或rich diff产品。
- not exercised：真实长期用户行为分布、大规模corpus profiling、Provider辅助候选措辞、多设备并发与后台expiry通知；均非Stage 4机械Gate。
- unproven：Workspace对未来V5-C个性化效果、Experience对未来V5-D Skill proposal质量、Stage 5 relations/product evaluation。
- Provider、credential/Keychain、新依赖/upstream copy、live SQLite连接/migration、push/merge/tag/self-accept均未发生。

```yaml
stage_4_contract_status: accepted_by_v5_main
stage_4_implementation_status: implemented_pending_v5_main_acceptance
stage_4_self_accepted: false
stage_5_authorized: false
next_action: limited_v5_main_stage_4_implementation_acceptance_review
```
