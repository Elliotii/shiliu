# V5-D Post-treatment Re-attribution R1

> Re-attribution ID: `V5D-R1-REATTRIBUTION-20260811-A`
> Parent Candidate: `V5D-CANDIDATE-EVIDENCE-DELTA-FOLLOWUP-001` v1.0.0
> Evidence role: consumed D02 source/diagnosis evidence only
> Provider runs used for this analysis: 0
> Reserve access: 0
> Confidence: moderate-high

## 1. Question and evidence identity

This review asks why the D02 v1.0 Treatment still failed after its first materially new recovery added current
transcript Evidence. It uses only the accepted Stage 2 D02 Treatment Trace, durable projection, Task Trace,
Provider receipts, frozen source review and v1.0 experiment-only implementation.

| Evidence | SHA-256 / identity |
| --- | --- |
| v1.0 Candidate | `6bcda6e5c5428c304807f067570c9acb7977cbd991c355edaeb9346d3d13cdbe` |
| effective Stage 2 freeze | `0c72277e7b30bac68800ef27acc9e8d52222efd6` |
| D02 Treatment deep Trace | `22a7caa30604cf7a7d6ed70e99511b628028634adf1d20e7ef146e873e7bce57` |
| D02 source-pair evaluation | `0518795a65ee02134f742b3f2ca972a28702c610fd6424527c1210275b26d74a` |
| Stage 2 run manifest | `a2f2173da7e6f51564523adc7ff76d39296368948a22edc2168f5d45acbf8e9a` |

Private task bodies, action text, Evidence and raw Provider responses remain outside Git.

## 2. Observed post-recovery sequence

The redacted sequence is mechanically sufficient:

1. Decision rounds 1 and 2 performed routing navigation; neither produced grounded Evidence.
2. Round 3 performed a one-source transcript search and added zero current transcript Evidence.
3. v1.0 became applicable before round 4 and replaced the proposed action with one materially different,
   one-source transcript recovery. The recovery added 60 new segments and 6 current Evidence spans.
4. Because Evidence increased, v1.0 immediately became non-applicable and returned control to the unchanged
   Baseline. It did not preserve a post-recovery coverage obligation or completion decision.
5. Round 5 selected the exact same normalized transcript action key as round 3. The deterministic guard then
   terminated the run as `repeated_search`.
6. Final synthesis produced two current citations, but both resolved to one source. Therefore the frozen
   two-source comparison aspects remained at 0/5, source diversity failed and stop correctness failed.

The guard is downstream evidence of the failure, not its first cause.

## 3. Re-attribution

```yaml
re_attribution:
  first_actionable_post_recovery_step: D02_treatment_decision_round_5_before_guard
  failure_mechanism: evidence_only_recovery_success_handoff_loses_objective_coverage_obligation
  supporting_evidence:
    - round_4_recovery_added_6_current_evidence_spans_and_60_segments
    - candidate_audit_round_5_fell_back_to_baseline
    - round_5_selected_the_same_action_key_as_round_3
    - final_two_current_citations_resolved_to_one_source
    - frozen_required_aspect_coverage_remained_zero
  remaining_mechanism:
    - v1_0_treats_any_positive_evidence_delta_as_sufficient_to_release_candidate_control
    - v1_0_recovery_target_is_one_untried_document_or_one_provider_proposal_not_an_objective_coverage_bundle
    - v1_0_has_no_post_recovery_completion_gate_for_explicit_source_or_aspect_obligations
  confidence: moderate_high
```

The earliest policy-changeable post-recovery step is the handoff before round 5. At that point the system has
current Evidence, prior action keys, routing observations, the original objective and remaining budget. A
Search/Research Policy can therefore either make an objective-derived completion decision or honestly stop; it
need not change retrieval, Evidence authority, Provider routing or the guard.

## 4. Alternative cause review

| Alternative | Judgment | Evidence |
| --- | --- | --- |
| Corpus lacks authoritative Evidence | rejected as primary | D02 answerability was frozen over two current transcript sources; recovery materialized current Evidence. |
| Retrieval/index failure | rejected as primary | schema/index/source health passed; the recovery returned 60 segments and 6 Evidence spans. Retrieval quality may affect yield but does not explain the round-5 exact action recurrence. |
| Provider failure | rejected | all 7 Treatment receipts succeeded, unknown receipts were 0, and no Provider error terminated the run. |
| Evaluator defect | rejected | the frozen evaluator credited +2 current citations and +1 grounded source, but correctly withheld two-source comparison aspects because citation lineage resolved to one source. |
| Outer Audit / continuation blocker | downstream, not causal | Outer Audit ran after Deep finalization; it cannot cause the round-5 decision or guard. |
| Preliminary QueryPlan / model choice | possible amplifier | The model selected the repeated action, but the policy-visible action history and unresolved objective made the handoff actionable. |
| v1.0 experiment execution defect | rejected | the observed behavior matches the frozen v1.0 rule: one recovery, then Baseline continuation after positive Evidence delta. The deficiency is in the Candidate contract/mechanism, not an invalid execution. |
| Too few allowed recoveries | rejected | the first recovery succeeded. The failure occurred because positive Evidence was mistaken for objective completion, not because a second recovery was forbidden. |
| Earlier stop alone | rejected | stopping before collecting the explicitly required source coverage would merely hide `repeated_search` and still fail the grounded outcome gate. |

## 5. Frozen remaining mechanism and Hypothesis

```yaml
remaining_mechanism_id: V5D-R1-MECHANISM-COVERAGE-HANDOFF-001
mechanism: >-
  After a successful Evidence-delta recovery, control is released without comparing current grounded source
  coverage against explicit objective-derived coverage obligations. The unchanged Baseline can therefore
  re-enter a previously non-incremental action while required source/aspect work remains unresolved.
hypothesis_id: V5D-R1-HYPOTHESIS-COVERAGE-BUNDLE-HANDOFF-001
hypothesis: >-
  For applicable multi-source research tasks, replacing v1.0's one-target recovery with one bounded,
  objective-derived coverage-bundle Evidence action and retaining control for a deterministic post-recovery
  completion/partial-stop gate will prevent non-progress re-entry and improve grounded required-aspect and
  current-citation coverage without adding a second recovery.
falsification: >-
  The Hypothesis is false for R1 if either valid frozen D02 or D04 pair fails any hard Source Gate, including
  +1 required aspect, +1 current grounded citation, required source diversity, recovery quality, stop
  correctness, no material regression, protected boundaries or overhead.
```

This is not “retry one more time.” v1.1 still permits at most one Candidate recovery action. The changed causal
surface is the unit of that action (an explicit objective-coverage bundle rather than one arbitrary source) and
the post-recovery handoff (completion gate rather than unconditional Baseline return).

## 6. Boundary

- D02 and D04 are consumed source cases, not generalization evidence.
- No reserve body, Gold, Evidence ref, semantic split, result or key was accessed.
- No new Provider call, Keychain access, live DB write, product `src` change or Candidate activation occurred
  during re-attribution.
- The conclusion supports one falsifiable v1.1 proposal; it does not prove effectiveness.
