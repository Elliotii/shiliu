# Shiliu V5-D Current State

> Updated at: 2026-08-11T00:23:44+08:00
> Updated by: Shiliu V5-D Version Session
> Authority: execution-session status; pending V5 Main acceptance

```yaml
resume_anchor:
  version: V5-D
  formal_stage: Stage_0_Entry_Calibration
  stage_status: case_and_reserve_freeze_complete_scaffold_freeze_pending
  execution_branch: codex/v5-d
  startup_authorization_head: 98ee944a5fdca19c962953b5d71250c7b6dea508
  actual_start_head: 98ee944a5fdca19c962953b5d71250c7b6dea508
  accepted_product_code_head: 8904e27df07becebae13110f9be17cd829373b20
  working_tree_at_start: clean
  product_source_tree_matches_accepted_head: true
  current_exit_decision: pending
  stage_1_authorized: false
```

## Startup baseline

```yaml
baseline:
  db_schema: 14
  live_db_access: read_only_identity_and_copy_only
  live_db_sha256_at_copy: 85d706a40f4f8bcad20d3ea373e17b4fd7021ddc738b90eac09a1dd702c25453
  isolated_db_sha256_after_path_isolation: 9cd12c6ef27ca128476a28fb973f4b9b78bae2b5841a2b6a5eb6a2ed1877dc67
  integrity_check: ok
  foreign_key_violations: 0
  videos: 157
  completed_videos: 140
  evidence_backed_indexed_videos: 138
  lexical_index: v3-stage1-lexical-v1
  lexical_units: 1633
  dense_index: v3-dense-qwen3-0.6b-mrl512-v1
  dense_units: 1633
  dense_identity_healthy: true
  corpus_source_boundary_hash: bf6a345d47aeb5152353d99c9f754c4a1a486c692c31af5d69df0a37520a1f0a
  source_version_set_hash: d7092edf4cece5fa54b574469740b5cdaef86275c993226d8d3f63eabacf4b9b
  retrieval_unit_manifest_hash: afbdeeb2274b407b939cedbfc1216c4174757fa1adc5948d81a6c854fe52ac5b
  provider: deepseek_openai_compatible
  provider_endpoint: https://api.deepseek.com/v1
  provider_model: deepseek-v4-pro
  credential_reference_present: true
  credential_value_read_or_recorded: false
  active_skill_repository: none
  candidate_version: none
  no_skill_baseline: true
```

`V5_PROGRAM_CURRENT_STATE.md` 记录的 `sync_runs=447` 在现场为 451；视频、完成态、Evidence
源、lexical/dense index 与 Provider 身份未漂移，因此分类为 scheduled-sync 运行计数的非材料变化。
154 个 indexed videos 中 16 个没有当前 raw subtitle；它们只保留 metadata index，不进入 Stage 0
answerability 或 task selection pool。

## Authorization and next action

```yaml
case_freeze:
  rubric_hash: 8b4e29665c2b05d9897c2c577bd43bf6e764d96084b7b2eb6ba8874ce07eadfa
  case_manifest_id: V5D-S0-CASE-MANIFEST-20260811-A
  case_manifest_hash: 4850f8f194741623eb0687140b01926012ac6ed169725e76c5f91b606654804f
  access_policy_hash: 151b7bcbf705a9e09bd243c60db57c6809f048b0a241d8c80e52bd69312441b9
  discovery_cases: 4
  sealed_reserve_cases: 4
  reserve_seal_id: V5D-S0-RESERVE-SEAL-20260811-A
  reserve_ciphertext_sha256: d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c
  reserve_key_mode: "000"
  reserve_plaintext_present: false
  reserve_bodies_seen_by_V5_D: false
  reserve_runs: 0
  private_artifact_root: /Users/elliot/.codex/private/Shiliu/V5-D/stage0-20260811-MAoyel
```

```yaml
authorized_now:
  - candidate_independent_case_freeze
  - encrypted_sealed_reserve_custody
  - four_valid_no_skill_discovery_runs_maximum
  - execution_docs_private_artifacts_and_stage_0_report
not_authorized:
  - product_or_test_change
  - candidate_or_skill_creation
  - live_database_write_or_migration
  - index_rebuild
  - provider_switch
  - stage_1_2_3
  - push_merge_tag
next_action: commit_startup_state_then_freeze_clean_head_no_skill_scaffold
```
