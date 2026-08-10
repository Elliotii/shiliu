# Shiliu V5-D Current State

> Updated at: 2026-08-11T03:06:06+08:00
> Updated by: Shiliu V5-D Version Session
> Authority: Stage 2 execution submission; pending V5 Main limited acceptance

```yaml
resume_anchor:
  version: V5-D
  formal_stage: Stage_2_Frozen_Paired_Evaluation
  stage_status: rejected_pending_main_acceptance
  candidate_verdict: rejected
  execution_branch: codex/v5-d
  stage_2_entry_head: 900953df64676a5d1438743918ac806961dfff14
  main_authority_commit: 7ef5dc7ec12689222d3bd277935cbeb586389d38
  valid_freeze_commit: 0c72277e7b30bac68800ef27acc9e8d52222efd6
  closeout_commit_binding: commit_containing_this_state_and_report
  accepted_failure_family: non_progress_search_repetition_without_recovery
  candidate_id: V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001
  candidate_version: 1.0.0
  candidate_artifact_status: proposed_non_active_unchanged
  candidate_evaluation_status: rejected
  stage_3_authorized: false
```

## Stage 2 result

The frozen D02 source pair produced a valid source failure. The treatment changed the first actionable decision
and added two current citations, but both citations came from one source. It added zero frozen required aspects,
failed the required source-diversity and stop gates, and later still reached `repeated_search`. Under the frozen
Contract, one valid source failure fixes the exact verdict as `rejected`; D04 and all held-out work were stopped
without additional paid runs.

```yaml
source_gate:
  D02:
    baseline_status: valid_insufficient
    treatment_status: valid_partial
    required_aspect_delta: 0
    current_grounded_citation_delta: 2
    grounded_source_delta: 1
    candidate_material_recovery: true
    final_repeated_search_eliminated: false
    overhead_pass: true
    pair_pass: false
  D04:
    status: not_run_after_decisive_valid_D02_source_failure
    provider_calls: 0
  source_cases_are_generalization_evidence: false
heldout:
  split_created: false
  related_run: false
  unrelated_runs: 0
  negative_transfer: unproven_not_run
```

The Candidate JSON remains byte-identical and non-active. Rejection is recorded by Stage 2 evidence and this
state/ledger; it does not mutate the frozen Candidate package or register it in Product Runtime.

## Freeze identity

```yaml
freeze:
  experiment_id: V5D-S2-PAIRED-EVAL-001
  commit: 0c72277e7b30bac68800ef27acc9e8d52222efd6
  experiment_manifest_sha256: 0679c93e1cbaedefdeb419b992c12b47d55c9822261b66604aa32eec616dfa56
  candidate_sha256: 6bcda6e5c5428c304807f067570c9acb7977cbd991c355edaeb9346d3d13cdbe
  treatment_sha256: 09d8ef4fc50001e499bfd2afa01337220e4cc16fa4f98790d09184fcf90eb3f0
  runner_sha256: 10f343123f05c5ffd4c767d425dee6ad1c1a4adf5f06c30a4f044b7691e57e47
  evaluator_sha256: 6efc8a0f6118dad39b56b87c675fe5ffa3d8781c316fe0d26889013782177966
  evaluator_version: v5-d-stage2-paired-grounded-outcome-evaluator-v1
  product_source_tree: 41ccf576cdd6ce6282b0eb8d35a31b75bc0cad01
  isolated_db_sha256_before_runs: a6497202263bdc318783a0efc35394dbbb53f282af034a76cbf648fc79172b8f
  artifact_snapshot_manifest_sha256: 5da478bc2a91945f0f6c17e4516865db75508641b361286163866f4805cd1b21
```

Freeze commit `b384531db3d0d84ccc2c7a40d4d17ffc56de7669` was closed before any Provider dispatch after a durable budget
membership setup failure. It consumed zero Provider/tool/token/USD budget and zero held-out access. Its private
root and invalid evidence are preserved; the corrected membership allocation was re-frozen at `0c72277` before
any outcome existed.

## Provider, budget and custody

```yaml
stage_2_accounting:
  valid_arms: 2
  outer_attempts_with_provider_execution: 2
  pre_provider_implementation_failures: 1
  logical_provider_calls: 12
  http_attempts: 12
  input_tokens: 25799
  output_tokens: 4200
  executed_deep_tool_calls: 7
  paid_cost_usd: 0.008692373
  unknown_reservations: 0
  active_reserved_cost_usd: 0
  hard_caps_reached: false
reserve:
  ciphertext_sha256: d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c
  key_mode: "000"
  plaintext_present: false
  access_log_entries: 4
  post_stage0_freeze_access_entries: 0
  semantic_assignment_created: false
  decrypt_or_key_read: false
  reserve_runs: 0
  reseal_required: false_already_continuously_sealed
```

## Stop boundary

```yaml
non_actions:
  D04_provider_run: false
  reserve_open_assignment_or_run: false
  heldout_related_or_unrelated_evaluation: false
  candidate_change_after_freeze: false
  product_default_path_change: false
  active_shadow_or_promotion: false
  live_DB_write_or_migration: false
  generic_skill_eval_harness_or_learning_platform: false
  upstream_download_or_adoption: false
  stage_3_execution: false
  push_merge_tag: false
next_action: stop_and_request_V5_Main_limited_Stage_2_acceptance_of_rejected_verdict
```
