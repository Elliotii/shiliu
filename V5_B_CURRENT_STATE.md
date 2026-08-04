# 拾流 V5-B Current State

```yaml
document_status: stage_4_contract_submission_pending_v5_main_review
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
stage_3_accepted_commit: 2d4d3397085dd9fe1b6d01533ce5743536b23740
stage_3_acceptance_record: 65706f4_on_codex_v5_main_not_cherry_picked
charter_status: accepted_by_v5_main
stage_1_implementation_status: accepted_by_v5_main
stage_2_implementation_status: accepted_by_v5_main
stage_3_implementation_status: accepted_by_v5_main
stage_4_contract_preparation_authorized: true
stage_4_contract_status: draft_pending_v5_main_acceptance
stage_4_implementation_authorized: false
schema_source_version: 13
provider_runs_performed_this_action: false
provider_cost_usd: 0
credentials_or_keychain_accessed: false
live_database_accessed_or_mutated_this_action: false
stage_5_authorized: false
```

## 1. 当前状态

V5 Main已以Program-only `codex/v5-main@65706f4`接受Stage 3 commit `2d4d3397085dd9fe1b6d01533ce5743536b23740`；Main独立验证`23 passed`，live DB SHA-256前后均为`1411d83ea22ebcd0d24dfca3ff1d52300de485772c62c773327ec2ec2210b1c6`，schema 10、Stage 3 table count 0、integrity ok。reported `160 passed`受影响回归和`1709 passed, 4 deselected`默认套件被接受为supporting evidence；known limits不触发rework。

当前唯一授权动作是准备compact `V5_B_STAGE_4_CONTRACT.md`。Contract已起草，Stage 4产品/schema/API/UI/tests未实施且未获授权。

## 2. Stage 4 target

```text
inspect Personal and Corpus Workspace
→ explicit create or review a typed candidate/observation
→ inspect authority, provenance, confidence/expiry and history
→ confirm | correct | reject | expire | tombstone
→ restart-stable projection with no silent resurrection
```

Capability families在一条auditable pipeline中保留不同authority：

- Explicit User Memory：只有user-authored或explicitly confirmed才是user-state authority；
- Behavioral/Inferred Candidate：必须有source events/evidence、confidence、expiry和review，不静默promotion；
- Current Focus/Knowledge Progress：区分显式状态与evidence-backed observation，机械阻止watched=learned等shortcut；
- Corpus Observation：对frozen collection/taxonomy snapshot做versioned folder/topic/uploader/series/source/search-term/limitation observation，只是future soft prior；
- System Experience：保存Trace/outcome/environment lineage和observed→diagnosed→candidate_source/invalidated，不成为Active Skill/Policy。

## 3. Lean Contract shape

- 默认一张append-only/revisioned `WorkspaceRecord` aggregate，使用`record_kind`、`authority_class`、typed status、confidence/expiry、source refs/hash和user decision保留语义差异；最多一张由具体FK/query invariant证明必需的supporting table。
- 复用Event、CommandReceipt、Research Trace/Result、Fact/Artifact lineage、collection membership、frozen taxonomy snapshot和现有API/UI foundation。
- correction/reject/expire/tombstone追加revision/decision，不原地改写或物理删除；old source boundary重放不得恢复rejected/deleted candidate。
- expiry在projection/command time deterministic计算，不新建background scheduler；不建MemoryOS、inference/corpus/experience平台、vector memory或rules engine。
- public surface默认为Workspace read、record create、record decision三类API和一个compact Workspace UI。

## 4. Strict cross-version boundary

Stage 4只存储和展示Workspace state，不让它影响Search/Ask/Research/ArtifactRoute、prompt、budget、proactive behavior或Provider调用。Corpus不得hard-filter/citation/self-reinforce；Experience不得改Skill/Policy/runtime。V5-C personalized behavior、V5-D promotion、Stage 5 relations/product evaluation全部排除。

## 5. JIT evidence decision

已检查Registry/Research Log、accepted DeepTutor/WeKnora fixed-commit reports、Charter/Stage 1–3以及本地collection/taxonomy/Event/Trace/Result/Receipt/Fact/Artifact实现。

- DeepTutor已覆盖stable explicit preference/edit reference和拾流拒绝physical delete/overwrite的边界。
- frozen taxonomy snapshot/membership提供versioned Corpus input，Research Event/Trace/Result提供Experience provenance，Stage 1–3提供revision/Receipt/projection/fault基础。
- WeKnora没有Stage 4必需的新authority/expiry/no-resurrection语义。

因此不新增upstream research/report/checkout/dependency，不调用Provider，cost USD 0。

## 6. Docs-only non-actions and current gate

未改产品/schema/API/UI/tests，未访问live DB/content、credential/Keychain或Provider，未更新Program authority/Registry/Research Log，未push/merge/tag/self-accept，未启动Stage 5。

```yaml
stage_3_main_acceptance: accepted_at_65706f4
stage_4_contract_preparation_authorized: true
stage_4_contract_status: draft_pending_v5_main_acceptance
stage_4_implementation_authorized: false
stage_4_self_accepted: false
next_action: limited_v5_main_stage_4_target_boundary_review
```
