# Shiliu V5-D Current State

> Updated at: 2026-08-11T04:54:30+08:00
> Updated by: Shiliu V5-D Version Session
> Authority: R1-E1 execution submission; pending V5 Main limited acceptance

```yaml
resume_anchor:
  version: V5-D
  active_cycle: Candidate_Revision_R1_E1
  exact_result: candidate_v1_1_rejected
  cycle_status: closed_pending_main_acceptance
  execution_branch: codex/v5-d
  E1_entry_head: ae3367548943098904d88623b9a3d132936563ac
  main_authority_commit: 1dab08972ecb4c70524be8d93b9b5c9a5c127ebd
  E1_freeze_commit: cbc8917aaa625897ae7e718e7d15e784aeeb0705
  closeout_commit_binding: commit_containing_this_state_ledger_and_report
  candidate_id: V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001
  candidate_v1_0_evaluation_status: rejected_accepted
  candidate_v1_1_version: 1.1.0
  candidate_v1_1_status: proposed_non_active
  candidate_v1_1_evaluation_status: rejected
  source_gate_status: failed_on_valid_D02_pair
  D04_status: not_run_due_exact_rejection_stop
  heldout_or_reserve_authorized: false
  stage_3_authorized: false
```

## R1-E1 result

The mechanical amendment changed only Treatment `per_arm_max_input_tokens` from 175,000 to 140,000 and fixed
two Treatment-hash display typos. A regression reached the actual Product Runtime envelope boundary for Baseline
125,000 and Treatment 140,000 while blocking Provider dispatch; the directed suite passed 22 tests.

D02 Baseline A1 was carried forward without rerun, replacement or resampling. E1 D02 Treatment A1 completed
validly after one user-authorized Keychain permission pause. It performed one material coverage-bundle recovery
but gained no Evidence, produced zero Citations/sources/required aspects and did not reach its post-recovery gate.
The frozen D02 pair failed with all grounded outcome deltas equal to zero. Exact result is
`candidate_v1_1_rejected`; D04 and all later work stopped.

```yaml
D02_pair:
  baseline:
    valid: true
    answer_status: valid_insufficient
    termination_reason: repeated_search
    required_aspects: 0
    current_citations: 0
    grounded_sources: 0
    logical_http_calls: [5, 5]
    input_output_tokens: [8893, 549]
    deep_tool_calls: 3
    cost_usd: 0.000646613
    carried_forward: true
  treatment:
    valid: true
    answer_status: valid_insufficient
    termination_reason: no_new_evidence
    required_aspects: 0
    current_citations: 0
    grounded_sources: 0
    candidate_material_recoveries: 1
    candidate_coverage_bundles: 1
    candidate_post_recovery_gates: 0
    coverage_satisfied: false
    logical_http_calls: [3, 3]
    input_output_tokens: [2774, 393]
    deep_tool_calls: 3
    cost_usd: 0.000665144
  delta:
    required_aspects: 0
    current_citations: 0
    grounded_sources: 0
  pair_pass: false
D04_runs: 0
```

## Freeze and evidence identity

```yaml
freeze:
  experiment_id: V5D-R1-E1-SOURCE-GATE-001
  commit: cbc8917aaa625897ae7e718e7d15e784aeeb0705
  tree: ccead23d0edeb00bc24228474eed6b367a3a1c04
  manifest_sha256: b25e2b14337d214b25d59afd031339a08887c999632c298784cdf5da04ecdb68
  private_receipt_sha256: 7ceb6cd7cda7149df8cacda71c6e70b66c0f695bf224490aa419de77489d7544
  candidate_v1_1_sha256: c40c4df488c15801eb521530f16833158028cef076ba348ce811f3a8794d4efc
  treatment_sha256: cdb52593fec31876df2a8fe73ea67cbccbc21d0fd22ef83466aa486927f4254f
  runner_sha256: f6a45d7ca5220f079d2788e2914c5d023eb098e94e2fa017ea30c1fdc88ab957
  evaluator_sha256: 4227dafd04e2d0e8fb6909f144a853919105bf7f50a3a25e2b3932d4c5d51c08
  product_src_tree: 41ccf576cdd6ce6282b0eb8d35a31b75bc0cad01
evidence:
  old_R1_run_manifest_sha256: 41bd4d7feacca3440e6f7759fe27d69665b76346f921f57fe186353e80dce680
  old_invalid_D02_treatment_sha256: 8401a9375566b2289319e1d9f84a14fba5192be4acb8c358b5ae3e450b637cbf
  carried_D02_baseline_trace_sha256: 1cce5577d33faf6e57015682b1ce3f08590417b5b0a54e8f111c974d33d66538
  E1_D02_treatment_trace_sha256: 839509e0036c59d9a67bab3ebe05969d55363883aba6e401fc1a82df96b96cec
  D02_pair_evaluation_sha256: 9eaeb5c4382b9ef7a67bb0ee7bbfcf80081e4379110d01149a0d291a3e7f1afc
  E1_run_manifest_sha256: 55f186ae76f64cf715847aed336656b6f3497e139c13bf69615d0206daf43bf6
  E1_final_isolated_db_sha256: 122b84a93e449a71c687165d297b57befc24839f5086d2783c1fe2735d58dc78
  E1_closeout_receipt_sha256: 572e0249924e67739c8c39e17718f8225ec8de253782bf7ef43b62f1a1ebf1cc
```

## Provider, budget and custody

```yaml
E1_incremental:
  valid_arms: 1
  outer_attempt_records: 1
  logical_provider_calls: 3
  http_attempts: 3
  input_tokens: 2774
  output_tokens: 393
  deep_tool_calls: 3
  wall_time_seconds: 465.066
  paid_cost_usd: 0.000665144
  unknown_reservations: 0
R1_plus_E1_cumulative:
  valid_arms: 2
  outer_attempt_records: 3
  logical_provider_calls: 8
  http_attempts: 8
  input_tokens: 11667
  output_tokens: 942
  deep_tool_calls: 6
  wall_time_seconds: 505.999
  paid_cost_usd: 0.001311757
  unknown_reservations: 0
reserve:
  ciphertext_sha256: d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c
  key_mode: "000"
  access_log_entries: 4
  post_freeze_access_entries: 0
  reserve_runs: 0
```

## Stop boundary

```yaml
non_actions:
  D04_treatment_or_baseline_run: false
  candidate_v1_1_change_after_freeze: false
  candidate_v1_2: false
  reserve_open_assignment_or_run: false
  heldout_related_or_unrelated_evaluation: false
  product_src_or_default_path_change: false
  active_shadow_or_promotion: false
  live_DB_write_or_migration: false
  generic_skill_eval_harness_or_learning_platform: false
  stage_3_execution: false
  push_merge_tag: false
next_action: stop_and_request_V5_Main_limited_acceptance_of_exact_candidate_v1_1_rejected
```
