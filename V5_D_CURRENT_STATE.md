# Shiliu V5-D Current State

> Updated at: 2026-08-11T04:10:37+08:00
> Updated by: Shiliu V5-D Version Session
> Authority: Candidate Revision Cycle R1 execution submission; pending V5 Main limited acceptance

```yaml
resume_anchor:
  version: V5-D
  active_cycle: Candidate_Revision_Cycle_R1
  exact_result: invalid_run
  cycle_status: closed_pending_main_acceptance
  execution_branch: codex/v5-d
  R1_entry_head: 254d72a03a1251ee0d08cac49d100b91b5de7593
  main_authority_commit: 5aab85ef5412c36df02b18c60cec591b66cd9199
  R1_freeze_commit: 789cf176adcc8c7a66dccbf0c507e875537bcc1a
  closeout_commit_binding: commit_containing_this_state_ledger_and_report
  accepted_failure_family: non_progress_search_repetition_without_recovery
  candidate_id: V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001
  candidate_v1_0_evaluation_status: rejected_accepted
  candidate_v1_1_version: 1.1.0
  candidate_v1_1_status: proposed_non_active
  candidate_v1_1_effectiveness: unproven
  source_gate_status: not_reached_due_invalid_run
  heldout_or_reserve_authorized: false
  stage_3_authorized: false
```

## R1 result

Offline D02 post-treatment re-attribution completed at moderate-high confidence. v1.0 gained current Evidence
with its first recovery, then lost the explicit objective-coverage obligation when it returned to Baseline; the
next decision repeated an earlier action. v1.1 therefore changes one recovery into one objective-derived
coverage-bundle action and retains control for a post-recovery completion/deficit stop. It does not add a second
recovery.

Candidate v1.1, the experiment-only Treatment, evaluator, D02/D04 order, eight A1/A2 Task identities, Provider,
corpus/index, budget and contamination rule were frozen at `789cf17`; 18 mechanical tests passed. Product `src`
remained unchanged.

D02 Baseline A1 completed validly. D02 Treatment A1 failed before Provider dispatch because its frozen 175,000
per-arm input-token cap exceeded the accepted Gate B envelope. A frozen-identical replacement would repeat the
same failure; lowering the cap would change the frozen Scaffold after a valid outcome. The Cycle therefore
closed as exact `invalid_run`, not Candidate rejection. D04 and evaluator execution did not occur.

```yaml
R1_execution:
  D02_baseline:
    valid: true
    answer_status: valid_insufficient
    termination_reason: repeated_search
    current_citations: 0
    grounded_sources: 0
    logical_http_calls: 5
    input_output_tokens: [8893, 549]
    deep_tool_calls: 3
    cost_usd: 0.000646613
  D02_treatment:
    valid: false
    classification: implementation_failure_frozen_scaffold_runtime_envelope
    provider_dispatch: false
    calls_tokens_tools_cost: 0
    replacement: not_eligible
  D02_valid_pair: false
  D04_runs: 0
  valid_source_pairs: 0
  candidate_v1_1_source_outcome: unproven
```

## Freeze and evidence identity

```yaml
freeze:
  experiment_id: V5D-R1-SOURCE-GATE-001
  commit: 789cf176adcc8c7a66dccbf0c507e875537bcc1a
  manifest_sha256: 230989ebc8c8437b56edd051ebe2d810cc6f38d80adfd9de089a79c0509d0d9c
  private_receipt_sha256: b24b05d94d741e48e82d62ff2a9b46271451f88aeb8a607c9df53dfcc3b766f4
  candidate_v1_1_sha256: c40c4df488c15801eb521530f16833158028cef076ba348ce811f3a8794d4efc
  treatment_sha256: cdb52593fec31876df2a8fe73ea67cbcc21d0fd22ef83466aa486927f4254f
  runner_sha256: caf739bd95ae279f5021589e5865276f754e7f7be9147f64188deea81bbd144d
  evaluator_sha256: 4227dafd04e2d0e8fb6909f144a853919105bf7f50a3a25e2b3932d4c5d51c08
  product_src_tree: 41ccf576cdd6ce6282b0eb8d35a31b75bc0cad01
evidence:
  run_manifest_sha256: 41bd4d7feacca3440e6f7759fe27d69665b76346f921f57fe186353e80dce680
  D02_baseline_deep_trace_sha256: 1cce5577d33faf6e57015682b1ce3f08590417b5b0a54e8f111c974d33d66538
  D02_treatment_invalid_sha256: 8401a9375566b2289319e1d9f84a14fba5192be4acb8c358b5ae3e450b637cbf
  final_isolated_db_sha256: d7ce1000f1a0c95de69211db3b69a2f779a58125e36c27a86f1b3ff07678425b
```

## Provider and custody

```yaml
R1_accounting:
  valid_arms: 1
  outer_attempt_records: 2
  invalid_attempts: 1
  logical_provider_calls: 5
  http_attempts: 5
  input_tokens: 8893
  output_tokens: 549
  executed_deep_tool_calls: 3
  paid_cost_usd: 0.000646613
  unknown_reservations: 0
  active_reserved_cost_usd: 0
  credential_reference_accessed: true
  credential_value_recorded: false
reserve:
  ciphertext_sha256: d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c
  key_mode: "000"
  access_log_entries: 4
  post_freeze_access_entries: 0
  reserve_runs: 0
  decrypt_key_or_semantic_split: false
```

## Stop boundary

```yaml
non_actions:
  D02_treatment_provider_dispatch: false
  D02_pair_evaluator: false
  D04_provider_runs: false
  candidate_change_after_freeze: false
  reserve_open_assignment_or_run: false
  heldout_related_or_unrelated_evaluation: false
  v1_2_candidate: false
  product_default_path_change: false
  active_shadow_or_promotion: false
  live_DB_write_or_migration: false
  generic_skill_eval_harness_or_learning_platform: false
  stage_3_execution: false
  push_merge_tag: false
next_action: stop_and_request_V5_Main_limited_acceptance_of_exact_invalid_run
```
