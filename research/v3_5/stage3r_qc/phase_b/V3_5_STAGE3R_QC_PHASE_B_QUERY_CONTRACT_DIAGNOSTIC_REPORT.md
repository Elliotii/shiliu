# V3.5 Stage 3R-QC Phase B Query Contract Diagnostic

## Status

Stage 3R-QC Phase B Complete

Ready for Human Diagnostic Review

## Input and runtime

- Approved file: `/Users/elliot/Downloads/stage3r_qc_query_decisions.approved.jsonl`
- SHA-256: `d8e60a5525556a02b454508bc8a6f0915fd6402724713389e7a2d34264484f9a`; byte-preserved freeze: `true`
- Records: `10`; exact Phase A case alignment: `true`; hard query leakage: `0`
- Frozen V3 runtime identity: `780efbb6ca5238f7923431ebf896b7293d6b422c487746e5ed79f13d050d2f41`
- Retrieval parameters modified: `false`; Q0 rerun: `false`; held-out accessed: `false`
- Q1 actual calls: `10`
- Q2 logical intents / actual new calls / Q1 reuse: `29 / 29 / 0`
- Local query embedding calls: `0`; external calls: `0` (frozen mode was lexical)

## Evidence-bearing results (n=9)

- Q0 recall: `0/9`
- Q1 recall: `0/9`
- Q2 recall: `0/9`
- Q1 incremental recovery: `0`
- Q2 additional recovery: `0`
- Persistent misses: `9`
- Class counts: already `0`, single-intent `0`, decomposition `0`, persistent `9`

## Query type

- `actual_result_verification`: cases 2, Q0/Q1/Q2 hits 0/0/0; classifications `{'persistent_retrieval_gap': 2}`
- `advanced_evidence_audit`: cases 1, Q0/Q1/Q2 hits 0/0/0; classifications `{'persistent_retrieval_gap': 1}`
- `comparison`: cases 2, Q0/Q1/Q2 hits 0/0/0; classifications `{'persistent_retrieval_gap': 2}`
- `definition`: cases 1, Q0/Q1/Q2 hits 0/0/0; classifications `{'persistent_retrieval_gap': 1}`
- `how_to_or_process`: cases 1, Q0/Q1/Q2 hits 0/0/0; classifications `{'persistent_retrieval_gap': 1}`
- `natural_multi_aspect`: cases 1, Q0/Q1/Q2 hits 0/0/0; classifications `{'persistent_retrieval_gap': 1}`
- `purpose_or_use_case`: cases 2, Q0/Q1/Q2 hits 0/0/0; classifications `{'persistent_retrieval_gap': 2}`

## Empty and non-empty misses

- Empty results: `{'q0_empty_result_rate': {'numerator': 9, 'denominator': 9, 'rate': 1.0}, 'q1_empty_result_rate': {'numerator': 9, 'denominator': 9, 'rate': 1.0}, 'q2_all_intents_empty_rate': {'numerator': 9, 'denominator': 9, 'rate': 1.0}, 'per_intent_empty_result_rate': {'numerator': 26, 'denominator': 26, 'rate': 1.0}}`
- Non-empty target misses: `{'q0': {'wrong_video_nonempty_miss_count': 0, 'wrong_video_nonempty_miss_rate': 0.0}, 'q1': {'wrong_video_nonempty_miss_count': 0, 'wrong_video_nonempty_miss_rate': 0.0}, 'q2': {'wrong_video_nonempty_miss_count': 0, 'wrong_video_nonempty_miss_rate': 0.0}}`

## Insufficient diagnostic (excluded from recall)

- `C2C_ee3fac675fc7d408` Q0/Q1/Q2: `False/False/False`
- Natural Discovery Query found the topic target video: `false`

## Interpretation boundary

- This is a descriptive 9-case diagnostic, not a statistical-generalization claim.
- Q2 is a multi-query diagnostic upper bound and is not a current product automation capability.
- This run does not authorize changing V3, starting Product Query Set, or starting F1A/F1B.
- Return to the main session for human review; close this Codex session after handoff.
