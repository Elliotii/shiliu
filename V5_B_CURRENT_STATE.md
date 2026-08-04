# 拾流 V5-B Current State

```yaml
document_status: stage_3_implementation_submission_pending_v5_main_acceptance
version: V5-B
version_session: Shiliu V5-B Version Session
updated_at: 2026-08-04
branch: codex/v5-b
version_starting_commit: b85340540cb92c2e46bfb8619598e7aa987171d4
accepted_v5_a_code_baseline: 04e5c5bbb94311a00f6efafa142908fd7b2b97de
stage_1_accepted_commit: abe002ab95025b38565464e69ca8b3abe651f1ae
stage_1_acceptance_record: 2f4dabf_on_codex_v5_main_not_cherry_picked
stage_2_accepted_commit: f879c80c0f547195a40d6804b6057debd077d11a
stage_2_acceptance_record: 2d89dfc_on_codex_v5_main_not_cherry_picked
stage_3_contract_commit: 70ba2b2c22f642ac52ddce0d3d30184d3b3235d6
stage_3_authorization_record: 8c198db_on_codex_v5_main_not_cherry_picked
charter_status: accepted_by_v5_main
stage_1_implementation_status: accepted_by_v5_main
stage_2_implementation_status: accepted_by_v5_main
stage_3_contract_status: accepted_by_v5_main
stage_3_implementation_status: implemented_pending_v5_main_acceptance
schema_source_version: 13
provider_runs_performed_this_action: false
provider_cost_usd: 0
credentials_or_keychain_accessed: false
live_database_migrated_or_mutated_by_this_session: false
stage_4_authorized: false
```

## 1. 当前一句话状态

V5 Main已接受Stage 3 Contract commit `70ba2b2c22f642ac52ddce0d3d30184d3b3235d6`，并以Program-only `codex/v5-main@8c198db`授权实施。Stage 3已在`codex/v5-b`完成lean no-provider/temp-DB实施，现等待V5 Main有限验收；未启动Stage 4。

## 2. 已实施产品路径

```text
Query
→ bounded Artifact candidate retrieval + independent open-corpus lane
→ scope/currentness/citation/source-version/completeness observations
→ durable explainable recommendation
→ explicit proceed
   ├─ direct reuse: exact existing ArtifactRevision + current L1 drill-down
   ├─ incremental refresh: bounded gap Task → Candidate review → new ArtifactRevision
   └─ research seed: independent Task, old Artifact candidate-only
```

- direct只在explicit aspects全部由current Fact heads和current L1 Evidence/Citations覆盖、scope exact、无blocking limitation/conflict、authority snapshot未变时允许。
- incremental只在存在current material core且缺口可枚举且最多2个时允许；新Research仍经V5-A Candidate Delta和Stage 1/2 review，新Artifact保存parent与reused/new/dropped逐Fact lineage。
- mismatch、no hit、substantial gap/stale/conflict/citation不完整或ambiguity都fail closed到seed；Artifact不是verifier。
- 用户只能选择recommended或更保守route，不能override unsafe direct；任何route都不自动改Fact或Page。

## 3. Lean concrete architecture

- schema source升至13，只新增一张immutable/append-only `research_artifact_routes`聚合表；query、candidate/open summary、gates、route、expected authority fence、continuation/outcome与contribution使用canonical JSON/hash。
- 继续使用现有`research_events`和`research_command_receipts`做append-only audit和exact replay；不增加通用queue、scheduler、lease、recovery、vector、graph或memory平台。
- Artifact lane是最新canonical ArtifactRevision上最多5个candidate的small lexical/structured selector；每次assessment独立运行现有open retrieval，排名只定义inspection order。
- incremental/seed复用V5-A `ResearchTask/Goal/Event/Receipt`和Stage 1/2 Candidate/Fact/Artifact lifecycle，不新建continuation平台。
- public surface为assess/proceed/read三条API和Research page内一张route card；UI显示gates、safer choices、continuation、contribution和Fact→L1 transcript drill-down。

## 4. Verification state

- Stage 1–3 directed temp-DB/no-provider：`23 passed`。
- affected Search/Ask/Research + Stage 1–3：`160 passed`。
- Stage 3 compact acceptance matrix：`6 passed`，覆盖direct happy path、stale/ambiguous/late fail-closed、bounded incremental lineage、seed mismatch/no-hit/substantial gap、duplicate/restart/cross-task/fault/orphan rollback、open lane不被Artifact hit抑制。
- default filtered no-provider submission run：`1709 passed, 4 deselected`。
- static：Python compile、`node --check`、`git diff --check`通过。
- 首次full-suite live hash窗口遇到外部`app.shiliu.sync`完成同步，hash `49bf8a… → 1411d8…`，按`infrastructure-invalid`处理；其间live DB仍为schema 10、Stage 3 table count 0、integrity ok。
- sync退出后的Stage 3 directed clean window前后hash均为`1411d83ea22ebcd0d24dfca3ff1d52300de485772c62c773327ec2ec2210b1c6`；证明本Session测试未live migration/content mutation。

## 5. Honest limits

- **bounded limitation**：Stage 3使用deterministic lexical/aspect containment，语义改写或无法证明的scope/coverage保守路由到seed；未建设embedding或Provider verifier。
- **bounded limitation**：incremental gap child使用Goal objective和evidence policy持久化target aspects，避免扩大V5-A已知的free-text success-constraint限制；未修改compound-query retrieval。
- **not exercised**：Provider/DeepSeek，cost USD 0；浏览器人工视觉/可访问性检查；live DB migration（未授权）。
- **unproven**：多进程高并发confirm/finalize压力和长时间语义质量评估；已有expected version、receipt、transaction和authority fence的mechanical tests，但未作Stage 5级产品评估。

## 6. Non-actions与当前Gate

未调用Provider/付费服务，未访问credential/Keychain，未引入dependency或upstream source/test/UI copy，未live migration/content mutation，未push/merge/tag，未实施Stage 4/5或V5-C/V5-D。

```yaml
charter_accepted: true
stage_1_main_acceptance: accepted_at_2f4dabf
stage_2_main_acceptance: accepted_at_2d89dfc
stage_3_contract_acceptance: accepted_at_8c198db
stage_3_implementation_status: implemented_pending_v5_main_acceptance
stage_3_self_accepted: false
stage_4_authorized: false
next_action: limited_v5_main_stage_3_implementation_acceptance_review
```
