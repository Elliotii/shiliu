# F1A Preimplementation Recovery Amendment Report

```yaml
execution_date: 2026-07-27
role: Recovery State Consolidator
execution_status: complete
acceptance_status: pending_v3_5_b_review
recovery_amendment_status: execution_candidate_ready
```

## 1. Incident Verification

The authoritative Blocking Report records that an unscoped repository
discovery search entered the Frozen Gold tree. Search matching read bytes in
that tree, but no Frozen semantic record was displayed and no Frozen Gold file
was modified.

```yaml
blocking_report_sha256: 2585e89a48e11ebc9e4b8fbb9a232cd814a669e04a6e44a897487b43b48416b0
frozen_tree_files_read_for_search_matching: true
semantic_frozen_records_displayed: false
frozen_gold_modified: false
builder_or_design_influenced_by_frozen_content: false
prior_session_closed_or_marked_unusable: true
```

## 2. Preimplementation Finding

The same report confirms:

```yaml
builder_implementation_started: false
builder_code_changed: false
implementation_freeze_seal_generated: false
development_scored_runs: 0
stress_scored_runs: 0
```

The prior attempt therefore did not enter implementation, freeze, or formal
scoring and did not consume the sole F1A Major Cycle.

## 3. Authoritative Reclassification

```yaml
F1A:
  previous_attempt: invalid_preimplementation_attempt
  previous_attempt_reusable: false
  prior_session_must_close: true
  major_cycles_used: 0
  major_cycles_remaining: 1
  major_cycle_1_restart_authorized: true
  restart_is_second_cycle: false
  second_major_cycle_authorized: false
  implementation_authorized: true
  implementation_started: false
  next_execution_requires_new_session: true
```

This is authorization to begin the previously unconsumed Major Cycle 1 in a
new Session. It is not a second Major Cycle.

## 4. Unchanged Authorities

```yaml
P9_decision: execute
active_design: adaptive_bounded_coverage_swap_v1
current_builder: stage3b-acronym-w3.5-v1
design_changed: false
acceptance_thresholds_changed: false
F1B_authorized: false
Stage4_started: false
```

P8, Checkpoint 1, P9, and the Candidate Design Amendment were not rerun or
reopened.

## 5. Filesystem Isolation

`F1A_RECOVERY_FILESYSTEM_ACCESS_POLICY.json` is frozen as the access contract
for the next Session. Its default is deny. It allows only Seed Paths and exact
paths explicitly referenced by already allowed authority files. It forbids
repository-root recursive discovery, all listed Frozen path patterns, path
guessing, and parent-directory listing for Development Gold. A missing or
ambiguous exact path blocks execution.

## 6. Scope and Stop

No Builder, test behavior, Prediction, Scoring, Query, Split, Development Gold,
or Frozen Gold content changed. No Implementation Freeze Seal or scored run
was produced. F1B and Stage 4 remain unstarted.

```yaml
next_formal_step: F1A_MAJOR_CYCLE_1_RECOVERY_EXECUTION
next_execution_requires_new_session: true
current_codex_session_can_be_closed: true
```
