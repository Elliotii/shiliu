# P9 F1A Candidate Builder Decision Restart

## Decision

```yaml
execution_status: complete
acceptance_status: pending_v3_5_b_review
p9_status: decision_execution_candidate_ready
f1a_decision_candidate: execute
f1a_authorized_by_codex: false
component_behavior_changed: false
f1b_authorized: false
next_stage_started: false
```

Codex recommends one bounded Major Repair Cycle for review. This is a decision
candidate, not authorization and not an implementation.

## Identity and reconstruction

- Restart Task SHA-256:
  `3b7d5d90bd1d082096aa539ed19604d93379a54001dc4aad6312d608ef3252b5`.
- Restart Ledger SHA-256:
  `2e92fe85d5ef6ede8c3a4746ab8e7270dd4329e33152d8fea385d9b2b429ce1a`.
- P8 Scoring version: `P8_SCORING_AMENDMENT_V1`.
- P8 Scoring Hash Root:
  `54bc35083f4410ace027452b64fc2d22432111be5a2036c0ce245e6319849795`.
- Checkpoint 1 Amendment authority status: `complete_and_accepted`.
- Candidate Builder version: `stage3b-acronym-w3.5-v1`.
- Mechanically reproduced Builder Failure IDs:
  `PQS_V1_Q003`, `PQS_V1_Q004`, `PQS_V1_Q005`, `PQS_V1_Q008`,
  `PQS_V1_Q015`, and `PQS_V1_Q018`.
- Reproduced failure count: `6`.
- `PQS_V1_Q017` is excluded and remains
  `gold_defined_evidence_absent`.

Every reproduced case has `retrieval_success=true`,
`authoritative_source_reviewable=true`, at least one acceptable evidence group,
constructible material evidence, and no complete Candidate Builder group.

## Per-case finding

| Query | Builder candidates | Covered required spans | Missing required spans | Raw mapped Gold segments | Primary mechanism |
|---|---:|---|---|---|---|
| Q003 | 235 total; 32 on acceptable video | S1 | final segment of S2 | 26/26 | bounded pruning loses adjacent tail |
| Q004 | 249 total; 32 on primary acceptable video | convergence | first segment of verifiable goal | 29/29 | bounded pruning loses complementary boundary |
| Q005 | 259 total; 32 on acceptable video | S1 | final 7 segments of S2 | 30/30 | candidate budget starvation |
| Q008 | 264 total; 32 on acceptable video | S2 | 5 segments of S1; 11 of S3 | 42/42 | aspect coverage displaced under fixed budget |
| Q015 | 292 total; 32 on acceptable video | S1, S3 | 4 internal segments of S2 | 96/96 | pruning/dedup leaves internal holes |
| Q018 | 299 total; 32 on acceptable video | none complete | all seven required spans incomplete | 236/236 | broad multi-section demand exceeds bounded coverage |

Retrieval is not the cause: each acceptable video is present within the
retrieval cutoff, and all required Gold segment identities occur in the
eligible raw transcript-chunk union supplied to the Builder. Source is not the
cause: every source is reviewable and the required evidence is constructible.
Scoring is not the cause: all six satisfy the amended Builder eligibility rule.
Selector is downstream: for all six,
`complete_group_available_but_not_selected=false`.

## Generic mechanism

The dominant mechanism is `candidate_budget_starvation`: the Builder generates
legal bounded windows, then the lexical/anchor-region allocation and
near-duplicate filtering stop at 32 candidates per video. Relevant
complementary segments can be present in the retrieved raw mapping but absent
from the retained candidate union.

This mechanism is supported by all six failures across Harness evaluation,
Loop Engineering, Harness optimization, coding specifications, Agent memory,
and industrial RAG. It is not a synonym for “Gold was missed”: the raw mapped
segment check proves that construction inputs contained every required segment,
and the persisted CandidateSet proves the loss occurred after that boundary.

The relevant implementation is
`src/shiliu/evidence/stage3a.py`:

- lines 349–369 enumerate legal windows under the 6-segment, 60-second and
  500-character limits;
- lines 398–475 compute lexical, neighbourhood and region scores;
- lines 480–511 allocate, deduplicate and stop at the per-video budget;
- `src/shiliu/eval_v3_5/stage3b.py` lines 49–56 set the current Builder ID and
  32-candidate cap.

`candidate_dedup_suppresses_complement` is a secondary contributor for Q003,
Q004 and Q015. It does not explain Q005, Q008 or Q018, whose retained target
candidates have no duplicate segment memberships. That counterexample is why
the candidate design targets coverage-aware bounded pruning rather than merely
changing the dedup threshold.

Q018 is also the capacity counterexample. Its acceptable group requires 236
distinct segment identities and approximately 633.341 seconds of Gold spans.
That cannot be completely represented under the current nominal 192-segment
and 600-second bounds. Q018 is not promised as addressable by this cycle.

## Single bounded Candidate Design

Design: `bounded_coverage_reserve_v1`.

Keep every existing construction and safety bound. Fill the first 28 of the
existing 32 per-video slots with the current relevance/region allocation.
Reserve the final four slots for one deterministic pass that selects legal
candidates with the greatest marginal uncovered segment coverage inside
query-supported anchor regions. The reserve uses the same pre-Gold candidates,
the same relevance signals, and the existing dedup, character, duration and
union-duration constraints. If no eligible coverage candidate exists, the
slots revert to the current ranking. No Case ID, Video ID, Gold span, correction
dictionary, new index, reranker or unbounded window is permitted.

Expected addressable failures:
`PQS_V1_Q003`, `PQS_V1_Q004`, `PQS_V1_Q005`, `PQS_V1_Q008`, and
`PQS_V1_Q015` (`5`). Q018 is a non-goal.

The candidate count remains at most 32, each candidate remains at most 6
segments, 60 seconds and 500 characters, total characters remain at most 6000,
and total union duration remains at most 600 seconds. Selector input count is
therefore unchanged. The main risk is that up to four candidates have lower
lexical relevance and add noise; the deterministic reserve adds a small
bounded pruning cost but no model call.

## Before metrics and one-cycle acceptance

Before:

- Builder complete-group coverage: `6/13`;
- Builder primary failures: `6`;
- Builder required-span recall: `65.38%`;
- Builder required-aspect coverage: `65.38%`;
- Selector bundle hit: `1/13`;
- Stress v2 complete-group candidate coverage: `11/20`.

Accept the cycle only if all of the following hold in one formal comparison:

- Builder complete-group coverage is at least `8/13`;
- Builder primary failures are at most `4`;
- Builder required-span recall and required-aspect coverage are each at least
  `69.23%`;
- none of the six current complete-group hits
  (`Q006/Q007/Q011/Q012/Q013/Q019`) regress;
- candidate/window/character/union-duration caps remain unchanged;
- Stress v2 complete-group candidate coverage is at least `11/20`, with no new
  empty or identity/runtime failure;
- no Case ID, Video ID, Gold-derived feature, heavy architecture or Selector
  change is introduced.

After exactly one Major Cycle, F1A closes regardless of result. If every
acceptance condition is not met, retain `stage3b-acronym-w3.5-v1`. No second
variant or tuning cycle is authorized by this decision candidate.

## Stop boundary

No Builder or production code was changed. Predictions and scoring were not
rerun. Query, Split and Gold were unchanged. Frozen Gold was not opened. F1A
implementation, F1B, Stage 4 and P10 were not started.
