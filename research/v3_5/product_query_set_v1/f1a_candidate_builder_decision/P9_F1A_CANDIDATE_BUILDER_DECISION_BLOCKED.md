# P9 F1A Candidate Builder Decision — Blocked

## 1. Blocking reason

P9 is blocked by the Task Contract stop rule:

> If the persisted P8 primary attribution does not hold for any of the seven
> cases, record `identity_or_scoring_defect` and block P9; do not silently
> relabel the case.

`PQS_V1_Q017` is persisted as `candidate_builder_failure`, but its sealed
Development Evidence Gold contains:

- zero `acceptable_evidence_groups`;
- one material aspect, `PQS_V1_Q017_A1`, explicitly missing;
- one supporting aspect, `PQS_V1_Q017_A2`, with the only registered span;
- Evidence Gold reason code `EG_MATERIAL_ASPECT_MISSING`;
- Sufficiency Gold status `insufficient`, with
  `SG_NO_USABLE_MATERIAL_SUPPORT`.

Consequently, no complete acceptable evidence group exists for the Candidate
Builder to construct. The proposition “an acceptable video was delivered but
the Builder failed to construct a complete acceptable group” is not defined
for this case. The persisted attribution is therefore not a real Builder
failure that can enter the P9 generic-mechanism denominator.

The scoring path confirms the defect mechanism. It computes
`builder_groups = _complete_groups(evidence, builder_covered)` and then assigns
`candidate_builder_failure` whenever `not builder_groups`. It does not first
distinguish “the Gold defines no acceptable group” from “the Gold defines a
group that the Builder failed to cover.” For `PQS_V1_Q017`, the former is
mechanically converted into the latter.

No replacement attribution is asserted in this P9 execution. Correcting or
re-scoring P8 is outside the authorized scope.

## 2. Failed identity or failure-reconstruction check

The following input identity checks passed:

- Task Contract SHA-256:
  `e78d3a9d8f462dd7d0fd1c4d95e79eb14d706eb34677bb72d579beced0e70ab8`
- Decision Ledger SHA-256:
  `7e38f214ee86441b0965e3e62403defc6fe9b23997d4509dee8725e4328070d4`
- P8 formal attempt:
  `P8_PRODUCT_INITIAL_BASELINE_ATTEMPT_3`
- Candidate Builder version:
  `stage3b-acronym-w3.5-v1`
- Candidate Builder implementation SHA-256:
  `8a2ed841efdf42f048347bf23ed1170a67ce7be0f3b03823eabef31847a80458`
- P8 predictions SHA-256:
  `b34f173ac99208f4adb72966880ab7e9cf97d3e27157084792502f103e709038`
- P8 scores SHA-256:
  `30cce533265015cfcc5fd35992e43583d9f2a968928d2e012a9f49ee6c07466d`
- P8 per-query SHA-256:
  `0c91f361c2ea2091e796960dc2d7a1995336f14a548034263d13635accda892d`
- P8 failure attribution SHA-256:
  `75924ba07023825a44fe7d0d2ab78a22798edb680eb5251238f61afe25292865`
- Frozen access guard exists; no Frozen Query-level Gold, Evidence, or result
  content was opened.

Exactly seven persisted `candidate_builder_failure` labels were mechanically
reproduced:

1. `PQS_V1_Q003`
2. `PQS_V1_Q004`
3. `PQS_V1_Q005`
4. `PQS_V1_Q008`
5. `PQS_V1_Q015`
6. `PQS_V1_Q017`
7. `PQS_V1_Q018`

The failed check is:

```yaml
seven_real_builder_failures_reconstructed: false
failed_query_id: PQS_V1_Q017
persisted_primary_attribution: candidate_builder_failure
reconstruction_finding: identity_or_scoring_defect
primary_attribution_overwritten: false
```

Retrieval is not the reason for the conflict: the P8 persisted record reports
`determinate_success`, acceptable video at rank 2, and Hit@10 true. The trace
also contains exact-mapped transcript units for `bilibili:BV1vQwJzTEdz`.
Source identity is consistent with the Development Gold
(`source_version=c2928145...83f44`,
`timeline_run_id=timeline_run_6b8a...d1dfcbf`).

## 3. Analysis progress

- Checkpoint 1 / P8 Attempt 3 / current Builder identity checked.
- Seven persisted primary-failure labels reproduced from the frozen P8
  artifacts.
- Development Retrieval, Evidence, and Sufficiency Gold inspected only for
  the authorized Development split.
- Per-query Predictions, Trace, Scoring, and Failure Attribution inspected.
- `PQS_V1_Q017` Retrieval, Source, Gold, identity, and scoring-path confounds
  isolated.
- Failure taxonomy, genericity gate, bounded design, and closed-enum decision
  candidate were not completed because the mandatory stop rule fired.
- Stress Regression was not used; it cannot cure the Product Development
  attribution defect.

No `execute`, `skip`, `reject`, or `record_as_limitation` decision candidate is
valid until the authoritative seven-case input is corrected or re-authorized
by V3.5-B.

## 4. Scope audit

```yaml
code_changed: false
predictions_rerun: false
scoring_rerun: false
retrieval_router_changed: false
selector_gate_changed: false
query_split_gold_changed: false
frozen_gold_opened: false
f1a_implementation_started: false
f1b_started: false
next_stage_started: false
component_behavior_changed: false
```

The only created artifact is this blocking report under the authorized P9
analysis output root.

## 5. Required resolution

V3.5-B must resolve the P8/Gold attribution inconsistency outside this P9
execution. A future P9 attempt must receive an authoritative Builder-failure
set whose every member has at least one Gold-defined acceptable evidence group
and whose primary attribution is mechanically valid. This session must not
repair P8, modify Gold, or continue into an F1A design.
