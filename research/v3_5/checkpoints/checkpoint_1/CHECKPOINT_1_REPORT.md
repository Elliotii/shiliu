# Shiliu V3.5-B Checkpoint 1 Report

## Result

```yaml
execution_status: complete
acceptance_status: pending_v3_5_b_review
checkpoint_1_status: execution_candidate_ready
next_formal_step: P9_F1A_CANDIDATE_BUILDER_DECISION
```

Checkpoint 1 mechanically verified and consolidated the formally accepted P7
Product Gold package and P8 Attempt 3 Product Initial Baseline. No Prediction,
Trace, Scoring, or Stress Regression was rerun. No Frozen Gold content was
opened.

## Input Identity

| Input | Verified identity |
|---|---|
| P7 | `complete_and_accepted`; package `PQS_V1_PRODUCT_GOLD_V1`; aggregate manifest SHA-256 `afad8112a6667fc465f7d8a1c7fc44cb22fca93759b425ef9f83203f1ed515df` |
| P8 | `complete_and_accepted`; unique formal attempt `P8_PRODUCT_INITIAL_BASELINE_ATTEMPT_3` |
| P8 Prediction Seal | `069fcf9e3ec70cf28d23674a2752033e608bf46937c990176dd6fb52f9e04617`; 14 Predictions and 14 Traces |
| P8 manifest | `64241190018e694d7004be7fd0e52bc313d6e6122389c8bced23497e1acf9be7` |
| P8 report | `4e0cd6a87303561fb09700580837d12fef09a6fc65ab315253e56c00dbfd08c6` |
| P8 execution decision | `b479fb053ad364fa9f06cb448752541a49ddb0069bd32e3428566072fbd646e1` |
| P8 completion response | `c279db2af3e8b496c3ac36f36df28b6274fc8037506d9150c3c70df395d036f7` |
| P8 file hash manifest | `af3291a9e5e1a4a1567943fc311896cda54f4692c1970719ab4c4776c4c5e646`; 33/33 referenced files verified |

Attempts 1 and 2 remain invalid historical safety-block records. Attempt 2's
nine partial Predictions and Traces were not read into, combined with, or used
by this checkpoint. Attempt 3 is the only formal Product Initial Baseline.

## Frozen Baseline Findings

### Retrieval

```yaml
hit_at_1: 71.43%
hit_at_3: 92.86%
hit_at_5: 92.86%
hit_at_10: 100%
empty_results: 0
primary_retrieval_failures: 0
governance_conclusion: do_not_reopen_retrieval_or_router_by_default
```

### Candidate Builder

```yaml
complete_group_coverage: 6/14
required_span_recall: 65.38%
required_aspect_coverage: 60.71%
primary_failures: 7
governance_conclusion: clear_F1A_entry_signal
```

### Deterministic Selector

```yaml
bundle_hit: 1/14
complete_group_available_but_not_selected: 5
required_span_recall: 12.18%
required_aspect_coverage: 11.31%
primary_failures: 5
governance_conclusion: strong_F1B_candidate_signal
```

### Mechanical Gate

```yaml
judge_eligible: 13
terminal_unverifiable: 1
invalid_decisions: 0
governance_conclusion: no_current_gate_repair_signal
```

### Primary Failure Attribution and Unjudged

```yaml
primary_failure_distribution:
  candidate_builder_failure: 7
  deterministic_selector_failure: 5
  source_unverifiable: 1
  end_to_end_bundle_hit: 1
unjudged:
  pairs: 109
  decision_sensitive: 0
  determinate_queries: 14
  indeterminate_queries: 0
  additional_user_adjudication_required_for_P8: false
```

## Governance Updates

The following existing authorities were updated:

- `V3_5_CURRENT_STATE.md`
- `03_V3_5_DECISION_AND_ARTIFACT_INDEX.md`
- the Decision Ledger section inside `03_V3_5_DECISION_AND_ARTIFACT_INDEX.md`
- `02_PRODUCT_QUERY_SET_AND_REMAINING_V3_5_PLAN.md`

The formal Remaining Plan was recovered byte-for-byte from its consistent
handoff copy before applying this checkpoint's bounded status update. The
remaining route is:

```text
P9 F1A Candidate Builder Decision
→ P10 F1B Deterministic Selector Decision
→ Checkpoint 2
→ Stage 4A-R Mechanical Gate Revalidation
→ Stage 4B Semantic Sufficiency Development
→ Checkpoint 3
→ Minimal API/UI/Trace Integration
→ Frozen Evaluation
→ V3.5 Final Closeout
```

## Authorization Boundary

```yaml
P9_ready_for_authorization: true
F1A_entry_signal: true
F1A_authorized: false
F1B_candidate_signal: true
F1B_authorized: false
Stage4A_R_authorized: false
Stage4B_authorized: false
```

This checkpoint does not select or implement a Builder or Selector repair and
does not authorize P9. It stops at the Checkpoint 1 execution candidate.

## Scope Audit

```yaml
predictions_rerun: false
traces_rerun: false
scoring_rerun: false
stress_regression_rerun: false
functional_components_changed: false
query_split_gold_changed: false
frozen_gold_opened: false
F1A_started: false
F1B_started: false
Stage4_started: false
P9_started: false
```

## Test Verification

The Checkpoint 1 contract suite and the accepted P7/P8-related regression suite
completed with `202 passed`:

```text
.venv/bin/python -m pytest -q
  tests/test_v3_5_checkpoint_1_contract.py
  tests/test_pqs_v1_p8_product_initial_baseline_contract.py
  tests/test_pqs_v1_p5_split_r2_contract.py
  tests/test_pqs_v1_p6_gold_protocol_contract.py
  tests/test_pqs_v1_development_gold_seal_contract.py
  tests/test_pqs_v1_p7_final_closeout_contract.py
  tests/test_product_search_api.py
  tests/test_v3_5_stage3b_selector.py
  tests/test_v3_5_stage4a_gate.py
  tests/test_stage3r_track_a_auto_refresh_contracts.py
```
