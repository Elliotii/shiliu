# Shiliu V3.5 Stage 3R — Expanded Development Re-run Report

## Outcome

**Stage 3R is blocked; the predictions and derived metrics are not accepted.**

The 31 Track A and 27 applicable Track B predictions were frozen before the
Scoring Projection was opened, and those frozen bytes remain unchanged.
Post-freeze audit then found a scoring identity defect: the final Development
Gold expresses Segment IDs as logical `BV..._seg_000NNN` identities, while the
frozen Runtime Candidates express the same timeline segments as physical
`segment_<sha256>` identities. The scorer compared these namespaces directly
instead of applying the deterministic timeline/ordinal mapping. This forced
every Gold coverage comparison to zero and invalidates the metrics, Failure
Attribution, and the initially emitted Stage 3R-F1 recommendation.

Per the Prediction Freeze Barrier, this run preserves the frozen predictions,
does not repair or rescore them in place, does not rerun any Case, and stops as
`Stage 3R Blocked / Requires Rerun`. No existing Builder, Selector, Retrieval,
Source Snapshot, Gold, or Held-out asset was modified.

All numeric metrics below are retained as invalidated diagnostic output only and
must not be used for Runtime or bounded-fix decisions.

## Input and isolation

1. Provided Corpus: `/tmp/shiliu-v3-5-stage2r-c4-review-v1/finalize_and_lock/corpus_lock/development_gold.executable_31.jsonl`.
2. Resolved realpath: `/private/tmp/shiliu-v3-5-stage2r-c4-review-v1/finalize_and_lock/corpus_lock/development_gold.executable_31.jsonl`.
3. Corpus and frozen-copy SHA-256: `a337b52ef83c69a844425f673990b2fbe0f42307e3934b7f746e2c6a0af9f148`; byte-identical: true.
4. Records / unique IDs: 31 / 31; labels: 11 sufficient, 9 partial, 7 insufficient, 4 unverifiable.
5. Runtime Projection / Scoring Projection: 31 / 31.
6. Runtime Gold semantic/evidence/human leakage: 0 / 0 / 0.
7. Held-out accessed: false (payloads 0, Gold records 0, queries 0).
8. Prediction frozen before scoring: true.
9. Predictions modified after freeze: false.

## Frozen runtime

10. Candidate Builder: `stage3b-acronym-w3.5-v1`.
11. acronym/ASR policy: `v3.5-stage3b-asr-acronym-anchor-v1`.
12. Fine Selector: `v3.5-deterministic-fine-selector-v1`.
13. Structured LLM Selector enabled: false; disposition: rejected_after_stage3b.
14. Runtime files unchanged: true.
15. V3 Retrieval modified: false.
16. External model/network calls: 0.
17. Local embedding: model/provider not loaded; load_count 0, query_count 0, cold-load and inference latency 0 ms (frozen lexical request).

## Execution

18. Track A cases: 31; all typed terminal: true.
19. Track B applicable cases: 27; all typed terminal: true.
20. Track A terminals: `{'selector_abstained': 31}`. Track B terminals: `{'bundle_created': 27}`.
21. Silently skipped: 0.
22. Unattributed exceptions: 0.

## Evidence-bearing metrics

23. Track A target-video recall: `{'count': 0, 'total': 20, 'rate': 0.0}`.
24. Track A complete Gold Group Candidate coverage: `{'count': 0, 'total': 20, 'rate': 0.0}`.
25. Track A Required Span Recall @1/@3/@5: `{'mean': 0.0, 'total': 20}`, `{'mean': 0.0, 'total': 20}`, `{'mean': 0.0, 'total': 20}`.
26. Track A deterministic Bundle Hit@1: `{'count': 0, 'total': 20, 'rate': 0.0}`.
27. Track B complete Gold Group Candidate coverage: `{'count': 0, 'total': 20, 'rate': 0.0}`.
28. Track B Required Span Recall @1/@3/@5: `{'mean': 0.0, 'total': 20}`, `{'mean': 0.0, 'total': 20}`, `{'mean': 0.0, 'total': 20}`.
29. Track B deterministic Bundle Hit@1: `{'count': 0, 'total': 20, 'rate': 0.0}`.
30. Track B conditional Bundle Hit: `{'count': 0, 'total': 0, 'rate': None}`.
31. Median start/end error and union-duration ratio — Track A: `None`, `None`, `None`; Track B: `30.099999999999994`, `30.38000000000001`, `1.2564625841326713`.

Gold Group semantics are unchanged: spans within a group are AND; alternative groups are OR. An arbitrary single-span overlap is not a Bundle hit.

## Insufficient and unverifiable diagnostics

32–33. Insufficient Track A: `{'cases': 7, 'valid_search_candidate_set': 0, 'valid_candidate_builder_output': 0, 'bundle_created': 0, 'selector_abstained': 7, 'typed_failure': 0, 'bundle_segment_count': 0, 'bundle_duration_seconds': 0, 'bundle_union_duration_seconds': 0, 'near_support_concentration': 'unavailable'}`. Track B: `{'cases': 7, 'valid_search_candidate_set': 7, 'valid_candidate_builder_output': 7, 'bundle_created': 7, 'selector_abstained': 0, 'typed_failure': 0, 'bundle_segment_count': 40, 'bundle_duration_seconds': 793.430701, 'bundle_union_duration_seconds': 758.7807009999999, 'near_support_concentration': 'unavailable'}`. A created Bundle is an operational result, not a Sufficiency claim; near-support concentration is unavailable because the Gold schema supplies no such marker.
34–35. Unverifiable Track A: `{'cases': 4, 'correct_source_authority_terminal': 0, 'incorrect_bundle_created': 0, 'incorrect_regular_selector_failure': 0, 'other_typed_terminal': 4}`. Track B has zero applicable unverifiable cases by source authority.

## Failure attribution

36–43. Every miss/failure is recorded in `failure_analysis/case_failure_attribution.jsonl` and summarized by stage, Query Family, Source Type, Source Language, Evidence Structure, and label role. Repeated signatures are `{'no_complete_gold_group_in_candidate_set': {'affected_cases': 20, 'affected_case_ids': ['C2C_16019b3c36a8945b', 'C2C_a1c0207a1bc56a91', 'C3C_41cfa020e8d664c5', 'C3C_56b2c368638a31c3', 'C3C_62e28b33eec87c37', 'C3C_98e93af3d9519c76', 'C3C_f57e1f0cc83cd5dd', 'V2C_C0C_0492bb2ae33b5cec', 'V2C_C0C_185d322d5f9a00b3', 'V2C_C0C_2b331035debc8160', 'V2C_C0C_53862aba0bd0bfcb', 'V2C_C0C_5725899059df795c', 'V2C_C0C_593dade03883828e', 'V2C_C0C_8228254ff69d7b3b', 'V2C_C0C_958161474678bd3f', 'V2C_C0C_9618a83c9df4f059', 'V2C_C0C_9a49204f52a114c8', 'V2C_C0C_9d9b5b9460d0ce51', 'V2C_C0C_a48a04ab33a1ad95', 'V2C_C0C_c72788577931ce36'], 'affected_query_families': ['comparison', 'definition_or_explanation', 'method_or_process', 'multi-part_question', 'result_or_effect'], 'primary_stages': ['candidate_builder']}, 'selector_abstained': {'affected_cases': 11, 'affected_case_ids': ['C2C_0371a3c17753fda6', 'C2C_9ccf0f6c9e3d2f01', 'C2C_ee3fac675fc7d408', 'C3C_213343d4c5fab153', 'C3C_58fa1788f33d747e', 'C3C_e3a6085ddf6c6b60', 'U0C_27e259b9a502a406', 'U0C_8701ec36a53f837c', 'U0C_893af60d7b43c3b5', 'U0C_a36aa59754f94bc1', 'V2C_C0C_5b3932df62f1ca76'], 'affected_query_families': ['comparison', 'definition_or_explanation', 'method_or_process', 'result_or_effect'], 'primary_stages': ['bundle_validation']}}`. The bounded-fix threshold evaluation produced the final decision below; no Case-ID or video-ID special rule was introduced.

## Historical comparison

44. Mechanically extracted old metrics: Track A had 4 evidence-bearing Cases, 2/4 target-video reachability, 2/4 complete Candidate Groups, and 1/2 eligible deterministic Bundle hits. Track B had 3/4 Builder-complete Cases, 6/7 Required Spans, and 1/4 deterministic hits.
45–46. The expanded results should be interpreted from the exact rates above: they replace, rather than extrapolate, the old four-case denominators.
47. Structured LLM Selector remains disabled because Stage 3B recorded very low initial structural validity, repair instability, and no basis to reverse the frozen deterministic preference; Stage 3R made zero provider calls.

## Final decision

48. Frozen Builder/Selector: `stage3b-acronym-w3.5-v1` / `v3.5-deterministic-fine-selector-v1`.
49. `stage3r_decision: stage3r_blocked_scoring_identity_mapping_invalid`.
50–52. Stage 3R-F1 is not authorized. Its initially emitted recommendation is invalidated because its failure counts came from the scoring identity defect. The only permitted next engineering change is a separately authorized Stage 3R scoring-orchestration fix that deterministically maps Gold logical Segment IDs to Runtime physical Segment IDs by Source Artifact, Source Version, Timeline Run, and ordinal; it is not a Builder/Selector fix.
53. Largest current risk: accepting false-zero metrics or changing the Runtime in response to an evaluation-identity bug.
54. Next action: Main-session review of the preserved frozen predictions and the blocked-rerun handoff. This run does not enter Stage 3R-F1 or Stage 4A-R.
55. This Codex session can close after Main-session review accepts the blocked disposition.

## Stop state

Stage 3R Blocked  
Execution Identity or Evaluation Isolation Invalid  
Predictions Not Accepted  
Awaiting Main-session Review
