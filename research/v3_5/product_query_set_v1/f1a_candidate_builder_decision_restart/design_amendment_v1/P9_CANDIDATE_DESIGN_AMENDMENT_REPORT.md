# P9 Candidate Design Amendment v1

## Status

```yaml
execution_status: complete
acceptance_status: pending_v3_5_b_review
p9_candidate_design_amendment_status: execution_candidate_ready
active_candidate_design: adaptive_bounded_coverage_swap_v1
p9_decision: execute
f1a_implementation_authorized: false
f1a_major_cycles_remaining: 1
f1b_authorized: false
stage4_started: false
```

This Amendment consolidates the implementation-entry design contract only. It
does not reopen the accepted P9 decision or mechanism analysis and does not
implement F1A.

## Preserved P9 authority

- P9 status: `complete_and_accepted`.
- Decision: `execute`.
- Primary mechanism: `bounded_candidate_pruning_coverage_gap`.
- Secondary mechanism: `dedup_below_threshold_leaves_complement_gap`.
- Addressable failures: `Q003`, `Q004`, `Q005`, `Q008`, `Q015` (`5`).
- Non-goal: `Q018`.
- Major Cycle maximum: `1`; used: `0`; remaining: `1`.
- Acceptance thresholds are unchanged.

## Supersession

The original `f1a_candidate_design.json` is preserved byte-for-byte.

```yaml
bounded_coverage_reserve_v1:
  status: superseded_before_implementation
  reason: fixed_slot_partition_creates_unnecessary_regression_risk
  implemented: false
  evaluated: false
```

The fixed `28 relevance + 4 coverage` partition is not an implementation
authority. It is replaced by one active implementation candidate:

```yaml
adaptive_bounded_coverage_swap_v1:
  status: implementation_candidate
```

## Amended design

The Builder first produces its complete original Top-32 using the current
`stage3b-acronym-w3.5-v1` rules. Nothing is pre-removed, and ranks 29–32 are not
default victims.

Outside candidates are limited to candidates ranked after Top-32 in the same
already-existing Builder Candidate Pool. They must retain valid source and
timeline identity, Retrieval Chunk Lineage, an existing Query/Acronym/Entity
Anchor or Retrieval Chunk Lineage support, current admission relevance or
anchor support, and every current window and total-budget constraint.
Development Gold is not a runtime signal.

Victims are ranked deterministically by:

1. higher redundancy with the current selected set;
2. lower exclusive interval or segment coverage;
3. lower original relevance;
4. stable Candidate identity.

Outside candidates are ranked deterministically by:

1. new query-supported anchor-region coverage;
2. new interval-union or segment coverage;
3. lower redundancy with the selected set;
4. higher original relevance;
5. shorter window and lower noise;
6. stable Candidate identity.

Each iteration pairs one eligible outside candidate with one replaceable
selected candidate. A swap is accepted only when the resulting set strictly
improves the complete lexicographic set objective, preserves query-support
guards, and preserves all budgets. The process performs zero to four swaps.
Swaps are never forced; if no strict improvement exists, the final set is the
original Top-32.

## Immutable budgets

```yaml
candidate_cap: 32
per_window_segment_limit: 6
per_window_seconds_limit: 60
per_window_character_limit: 500
total_seconds_limit: 600
total_character_limit: 6000
selector_candidate_count_budget: unchanged
```

No Retrieval, anchor discovery, candidate generation region, LLM/reranker,
segment dense index or Gold signal is added.

## Frozen implementation Trace Contract

The next implementation contract must persist:

```yaml
original_top_32:
outside_eligible_candidate_ids:
victim_candidates_ranked:
swap_iterations:
  - iteration:
    removed_candidate_id:
    added_candidate_id:
    removal_reason:
    addition_reason:
    coverage_before:
    coverage_after:
    redundancy_before:
    redundancy_after:
final_candidate_ids:
swap_count:
no_swap_reason:
```

Candidate IDs and ranking ties must use stable deterministic ordering. The same
input Candidate Pool, scores, identities and budgets must produce the same
output and trace.

## Unchanged acceptance boundary

- Builder complete-group coverage: before `6/13`, minimum after `8/13`.
- Builder primary failures: before `6`, maximum after `4`.
- Required-span recall: before `65.38%`, minimum after `69.23%`.
- Required-aspect coverage: before `65.38%`, minimum after `69.23%`.
- Existing complete-group hit regressions allowed: `0`.
- Stress acceptance uses the stricter of the frozen implementation Before and
  the accepted P9 absolute threshold.
- F1A closes after the single Major Cycle regardless of outcome; failed
  acceptance retains `stage3b-acronym-w3.5-v1`.

## Scope and stop

Candidate Builder and production code were not changed. Predictions and
scoring were not rerun. Query, Split and Gold were not changed. Frozen Gold was
not opened. No implementation task was generated. F1A implementation, F1B and
Stage 4 were not started.
