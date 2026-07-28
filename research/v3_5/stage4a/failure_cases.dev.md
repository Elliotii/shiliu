# Stage 4A Development Failure Cases

## Track A

- CASE_003 and CASE_005 preserve frozen V3 upstream retrieval failures.
- CASE_015 terminates mechanically at retrieval and agrees with Gold `unverifiable` only after post-freeze comparison.
- CASE_017 terminates mechanically at retrieval; its Gold status is `insufficient`, so S1 is incorrect but does not fabricate semantic insufficiency from missing runtime evidence.
- CASE_002 is mechanically judge-eligible but Judge-input-inadequate because its deterministic Bundle misses a complete Gold Evidence Group.
- CASE_012 and CASE_013 are mechanically judge-eligible readable-insufficient cases. S1 incorrectly predicts `sufficient`, demonstrating the need for Stage 4B.

## Track B

- CASE_003 preserves the frozen final Stage 3B `candidate_generation_failure` and terminates with `evidence_resolution_action`.
- CASE_002 and CASE_005 are mechanically judge-eligible, but their deterministic Bundles are Judge-input-inadequate by post-freeze Gold coverage diagnostics.

No failure is represented as semantic `insufficient` by Stage 4A. Unknown operational states: 0. Invalid Gate decisions: 0.
