# Shiliu V5-D Current State

> Updated at: 2026-08-11T01:33:06+08:00
> Updated by: Shiliu V5-D Version Session
> Authority: Stage 1 execution submission; pending V5 Main acceptance

```yaml
resume_anchor:
  version: V5-D
  formal_stage: Stage_1_Attribution_and_One_Candidate
  stage_status: candidate_contract_ready_pending_main_acceptance
  execution_branch: codex/v5-d
  stage_1_entry_head: fbf7a0d56816797d0ad481b2381b6d5aba81657c
  main_authority_commit: e53fa410682691bfa86000c768f60e99cd459547
  stage_0_status: accepted
  accepted_failure_family: non_progress_search_repetition_without_recovery
  responsible_policy_surface: follow_up_strategy
  stage_1_result: candidate_contract_ready
  stage_1_formal_acceptance: pending_V5_Main
  stage_2_authorized: false
```

## Attribution and Hypothesis

```yaml
attribution:
  attribution_id: V5D-S1-ATTRIBUTION-20260811-A
  confidence: moderate_high
  supporting_cases: [D02, D04]
  first_actionable_failure: >-
    after an evidence-seeking action produced zero current transcript-Evidence delta while user-objective work
    remained unresolved, the next follow-up decision failed to choose a materially new evidence-bearing target
    or an honest stop
  final_repeated_search_guard_is_first_cause: false
  failure_reclassified: false
  bounded_controls:
    D03: same_environment_valid_partial
    D01: provider_domain_exclusion
hypothesis:
  hypothesis_id: V5D-S1-HYPOTHESIS-20260811-A
  status: frozen
  causal_claim: >-
    an objective-coverage and current-Evidence-delta follow-up policy can replace non-incremental continuation
    with one bounded evidence-bearing target or honest stop, improving grounded outcomes without unrelated
    regression
  effectiveness: unproven
```

The complete redacted attribution, alternatives and falsification conditions are in
`V5_D_STAGE_1_CLOSEOUT_AND_EVIDENCE_PACKAGE.md`. Full DecisionView messages were not persisted; action outputs,
trace hashes/summaries, receipts and unchanged source identities remain. Preliminary Evidence/QueryPlan handoff
is retained as a possible amplifier, not accepted as the primary cause.

## One proposed/non-active Candidate

```yaml
candidate:
  candidate_id: V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001
  candidate_file: V5_D_CANDIDATE_EVIDENCE_DELTA_FOLLOWUP_V1.json
  candidate_file_sha256: 6bcda6e5c5428c304807f067570c9acb7977cbd991c355edaeb9346d3d13cdbe
  candidate_type: domain_specific_search_research_policy
  version: 1.0.0
  lifecycle_status: proposed_non_active
  runtime_registration: none
  active: false
  shadow: false
  trigger_depends_on_termination_reason_or_repeat_count: false
  baseline_fallback: existing_No-Skill_unchanged
  product_behavior_delta: 0
```

The Candidate triggers before follow-up only when the last evidence-seeking action adds zero current transcript
Evidence and user-objective work remains unresolved. It selects at most one materially different evidence-bearing
target derived from the objective/open questions and routing observations, then re-evaluates or honestly stops.
It cannot read Gold/evaluator/reserve, change Evidence/Citation/Verifier/currentness, expand Provider/permission or
register into active/shadow Runtime.

## Stage 2 plan and custody

```yaml
stage_2_plan:
  experiment_id: V5D-S2-PAIRED-EVAL-001
  status: planned_not_authorized_not_run
  source_pairs: 2
  heldout_related_pairs_minimum: 1
  heldout_unrelated_pairs_minimum: 2
  sealed_spare_minimum: 1
  valid_run_cap: 10
  outer_attempt_cap_including_invalid_replacements: 20
  logical_call_cap: 260
  HTTP_attempt_cap: 520
  input_token_cap: 2750000
  output_token_cap: 350000
  tool_call_cap: 250
  paid_cost_hard_cap_usd: 0.50
  paid_cost_reserve_stop_usd: 0.40
reserve:
  ciphertext_sha256: d06ef1bbd7c7155cada19a2aa6f3b8bfc0316785990e2d6987504c3eb8d3710c
  key_mode: "000"
  plaintext_present: false
  access_log_entries: 4
  post_freeze_access_entries: 0
  reserve_runs: 0
```

Stage 2 assignment is methodology only. A future isolated Custodian may open reserve only after Main accepts Stage
1, the user authorizes Stage 2, and Candidate/scaffold/evaluator/budget are frozen. Stage 1 did not read or infer
reserve bodies, Gold, Evidence refs, results or key.

```yaml
stage_1_non_actions:
  Provider_or_Keychain_access: false
  paid_cost_usd: 0
  product_code_test_prompt_or_route_change: false
  live_DB_write_or_migration: false
  reserve_open_or_run: false
  candidate_active_shadow_or_promotion: false
  generic_skill_eval_or_harness_platform: false
  upstream_download_or_adoption: false
  stage_2_execution: false
  push_merge_tag: false
next_action: stop_and_request_V5_Main_limited_Stage_1_acceptance
```
