# 拾流 V5-B Current State

```yaml
document_status: stage_3_contract_submission_pending_v5_main_review
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
charter_status: accepted_by_v5_main
stage_1_implementation_status: accepted_by_v5_main
stage_2_implementation_status: accepted_by_v5_main
stage_3_contract_preparation_authorized: true
stage_3_contract_status: draft_pending_v5_main_acceptance
stage_3_implementation_authorized: false
schema_source_version: 12
provider_runs_performed_this_action: false
credentials_or_keychain_accessed: false
live_database_accessed_or_mutated_this_action: false
```

## 1. 当前一句话状态

V5 Main已在Program-only `codex/v5-main@2d89dfc`正式接受V5-B Stage 2 commit `f879c80c0f547195a40d6804b6057debd077d11a`；当前唯一授权动作是准备compact Stage 3 Contract。Contract已完成，Stage 3产品/schema/API/UI/tests尚未实施，也未获授权。

## 2. Stage 2 acceptance closure

- Main独立重跑Stage 1 + Stage 2 core：`17 passed`。
- Main独立窗口live DB SHA-256前后均为`b156448d688c37efbf496948d6ebfc43a685858cac54398fe1e05a9787ffe55d`。
- live DB仍为schema 10、Stage 2 table count 0、integrity ok。
- reported `154 passed` affected与`1703 passed, 4 deselected` default no-provider被接受为supporting evidence。
- 先前external sync污染的hash窗口已被接受为honest `infrastructure-invalid`，后续独立non-action window关闭该证据缺口。
- revision/hash export clarification已在Stage 2交付；known unproven/not-exercised items不触发Stage 2 rework。

Stage 2完整状态以`V5_B_STAGE_2_IMPLEMENTATION_REPORT.md`更新后的acceptance record为准。

## 3. Stage 3 Contract target

```text
Query
→ Artifact retrieval + independent open corpus retrieval
→ scope / source-version / currentness / completeness gate
→ durable explainable route proposal
→ explicit proceed
   ├─ direct reuse
   ├─ incremental refresh
   └─ research seed
```

Contract的最小core：

1. immutable QueryIntent、Artifact candidate snapshot、append-only gate observations与RouteDecision；
2. bounded SQLite/structured Artifact retrieval与独立open corpus lane；
3. route-time Stage 2 revalidation、current Fact head、citation/source-version、scope与aspect completeness gate；
4. exact+complete+current才direct reuse，并返回原ArtifactRevision及L1 drill-down；
5. materially usable core + isolatable bounded gaps才incremental refresh，持久记录parent、reused/new/dropped contribution lineage；
6. mismatch/substantial gap/stale/conflict/ambiguity/no hit走research seed，旧Artifact只作candidate source而非verifier；
7. explicit confirm允许选择safer route，但不能override成unsafe direct；duplicate/restart/fault/source-head drift fail closed。

Stage 3不自动改Fact/Artifact/Page head或published Page；incremental/seed结果仍经过V5-A Candidate Delta与Stage 1/2 review。

## 4. JIT evidence decision

已检查Program Registry/Research Log、accepted DeepTutor/WeKnora fixed-commit reports与Stage 2实际schema/service。

- DeepTutor stable ID/refs-required/ID-set incremental只作为lineage与candidate pattern；其Memory不是route verifier。
- WeKnora revision/durable patterns已由Stage 2吸收；其Wiki/RAG retrieval不满足拾流claim-level authority或open retrieval边界。
- 本地Artifact已有topic/body、limitations/unresolved、Fact links、source boundary/corpus snapshot/content hash；Stage 2已有Fact currentness、L1 source-version revalidation、receipt和late fence。
- 因此这些证据足以定义Stage 3 Contract；没有材料性未决语义要求新增upstream research、checkout、报告、dependency或Provider。

## 5. Explicit boundaries

- Artifact similarity只排序candidate，不授权reuse、不硬过滤alternative/counter-evidence。
- direct reuse必须scope exact、complete、current且citation/source-version全通过。
- incremental只处理可枚举的小gap；运行中authority drift要求reroute，不自动扩大scope。
- seed可携带candidate Facts/sources/unresolved/search terms，但不能预先满足Research Goal。
- Stage 4 personal/corpus workspace与Stage 5 relations/product evaluation不进入Stage 3。
- V5-A compound-query limitation只有在controlled Stage 3 acceptance case明确阻塞route时才可提出有界修复。
- 不预建generic vector/graph/memory/queue平台，不实现V5-C/V5-D。

## 6. 本次docs-only non-actions与验证

- 只新增`V5_B_STAGE_3_CONTRACT.md`，更新Current State、Decision Ledger与Stage 2 report acceptance status。
- 未改产品/schema/API/UI/tests，未运行Provider，cost USD 0。
- 未访问credential/Keychain、live DB/live content，未引入dependency或upstream copy。
- 未更新Program authority文件或handoff Registry/Research Log，未push/merge/tag。
- JSONL/YAML-fence/docs whitespace与Git范围将在提交前验证。

## 7. 当前Gate

```yaml
charter_accepted: true
stage_1_main_acceptance: accepted_at_2f4dabf
stage_2_main_acceptance: accepted_at_2d89dfc
stage_3_contract_preparation_authorized: true
stage_3_contract_status: draft_pending_v5_main_acceptance
stage_3_implementation_authorized: false
stage_3_self_accepted: false
next_action: limited_v5_main_stage_3_target_boundary_review
```
