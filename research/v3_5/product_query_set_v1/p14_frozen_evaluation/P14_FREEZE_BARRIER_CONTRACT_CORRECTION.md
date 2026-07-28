# P14 Freeze Barrier Contract Correction

## Scope

`correction_scope: orchestration_validation_only`

The prior validator incorrectly required every complete `component_versions`
object to be identical. The corrected barrier compares all stable formal
configuration fields globally and validates `semantic_model` against the
Mechanical Gate route:

- Judge called: `semantic_model: gpt-5.6-terra`.
- Judge not called: `semantic_model: null`.

All ten existing Case and Trace artifacts validate. No Retrieval, Builder,
Selector, Mechanical Gate, Semantic Judge, Prediction, EvidenceBundle,
SufficiencyDecision, Case, or Trace was rerun or modified. Frozen Gold remained
closed during correction.
