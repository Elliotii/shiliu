# Shiliu V5-D Current State

> Updated at: 2026-08-11T00:49:20+08:00
> Updated by: Shiliu V5-D Version Session
> Authority: execution-session submission; pending V5 Main acceptance

```yaml
resume_anchor:
  version: V5-D
  formal_stage: Stage_0_Entry_Calibration
  stage_status: report_submitted_pending_main_acceptance
  execution_branch: codex/v5-d
  startup_authorization_head: 98ee944a5fdca19c962953b5d71250c7b6dea508
  actual_start_head: 98ee944a5fdca19c962953b5d71250c7b6dea508
  accepted_product_code_head: 8904e27df07becebae13110f9be17cd829373b20
  product_source_tree: 55dc6da8b47c7c46c357dbbeb53e896c9607c138
  startup_docs_commit: ca944e14b5a72565bd8dbd15ddcfe4dfe1d90976
  working_tree_at_start: clean
  exit_decision: qualified_failure_family_found
  failure_family: non_progress_search_repetition_without_recovery
  first_actionable_surface: follow_up_strategy
  formal_acceptance: pending_V5_Main
  stage_1_authorized: false
```

## Frozen identity

```yaml
baseline:
  db_schema: 14
  live_db_access: read_only_identity_and_copy_only
  live_db_sha256_at_copy: 85d706a40f4f8bcad20d3ea373e17b4fd7021ddc738b90eac09a1dd702c25453
  isolated_db_sha256_after_path_isolation: 9cd12c6ef27ca128476a28fb973f4b9b78bae2b5841a2b6a5eb6a2ed1877dc67
  videos: 157
  completed_videos: 140
  evidence_backed_indexed_videos: 138
  lexical_index: v3-stage1-lexical-v1
  lexical_units: 1633
  dense_index: v3-dense-qwen3-0.6b-mrl512-v1
  dense_units: 1633
  corpus_source_boundary_hash: bf6a345d47aeb5152353d99c9f754c4a1a486c692c31af5d69df0a37520a1f0a
  source_version_set_hash: d7092edf4cece5fa54b574469740b5cdaef86275c993226d8d3f63eabacf4b9b
  retrieval_unit_manifest_hash: afbdeeb2274b407b939cedbfc1216c4174757fa1adc5948d81a6c854fe52ac5b
  provider_endpoint: https://api.deepseek.com/v1
  provider_model: deepseek-v4-pro
  active_skill_repository: none
  candidate_version: none
  no_skill_baseline: true
```

One scheduled sync occurred during execution, raising `sync_runs` from 451 to 452. The post-run read-only audit
found no material corpus/index drift: all 1,633 retrieval units and folder mappings remained equal; only sync and
index clock fields changed. Live identity remained schema 14, 157/140 videos, integrity `ok`, FK 0 and zero active
sync. V5-D did not write the live DB.

```yaml
case_and_scaffold_freeze:
  rubric_sha256: 8b4e29665c2b05d9897c2c577bd43bf6e764d96084b7b2eb6ba8874ce07eadfa
  case_manifest_id: V5D-S0-CASE-MANIFEST-20260811-A
  case_manifest_sha256: 4850f8f194741623eb0687140b01926012ac6ed169725e76c5f91b606654804f
  access_policy_sha256: 151b7bcbf705a9e09bd243c60db57c6809f048b0a241d8c80e52bd69312441b9
  discovery_cases: 4
  sealed_reserve_cases: 4
  reserve_seal_id: V5D-S0-RESERVE-SEAL-20260811-A
  reserve_ciphertext_sha256: d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c
  reserve_key_mode: "000"
  reserve_plaintext_present: false
  reserve_bodies_seen_by_V5_D: false
  reserve_runs: 0
  scaffold_id: V5D-S0-NO-SKILL-SCAFFOLD-20260811-A
  scaffold_fingerprint: e877a03aa5aee94f440eef294a109470c51c1f3210da3f835619420d752f0dcc
  run_id: V5D-S0-DISCOVERY-20260811-A
```

## Stage 0 outcome

```yaml
execution:
  product_outer_attempts: 5
  valid_discovery_outcomes: 4
  invalid_product_attempts: 1
  pre_run_launcher_invalid_events: 1
  valid_results:
    D01: product_quality_failure_provider_grounding
    D02: product_quality_failure_search_or_research_policy
    D03: valid_partial_no_failure
    D04: product_quality_failure_search_or_research_policy
  committed_logical_calls: 29
  accounted_logical_calls: 30
  committed_input_tokens: 87322
  accounted_input_tokens: 110358
  committed_output_tokens: 12793
  accounted_output_tokens: 16889
  deep_tool_calls: 18
  committed_cost_usd: 0.034427524
  accounted_cost_usd: 0.088764244
```

D02 and D04 independently ended at `repeated_search`, with zero grounded citations/answer blocks and all frozen
required aspects missing despite current authoritative Evidence and healthy case-local Runtime/index/Provider.
Their shared first actionable surface is `follow_up_strategy`. D01's dispatch-unknown invalid run and replacement
grounded-citation validation failure are segregated as Provider-domain evidence. D03 produced a grounded
`valid_partial` in the same envelope.

```yaml
submission:
  report: V5_D_STAGE_0_ENTRY_CALIBRATION_REPORT.md
  qualification_artifact_id: V5D-S0-QUALIFICATION-20260811-A
  qualification_artifact_sha256: 76f3a3effcc685d426ad387c4fb50a2069467916f6e291a19d149d553f408896
  private_artifact_root: /Users/elliot/.codex/private/Shiliu/V5-D/stage0-20260811-MAoyel
  candidate_hypothesis_frozen: false
  product_or_test_changes: false
  live_db_writes: false
  reserve_unsealed_or_run: false
  push_merge_tag: false
  next_action: stop_and_request_V5_Main_limited_acceptance
```
