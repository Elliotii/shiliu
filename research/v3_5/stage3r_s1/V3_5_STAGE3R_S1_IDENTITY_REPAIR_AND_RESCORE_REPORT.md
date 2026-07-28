# Shiliu V3.5 Stage 3R-S1 — Identity Repair and Frozen-Prediction Rescore

## Outcome

Stage 3R-S1 repaired only the Evaluation Scoring identity bridge. It did not call Retrieval, Candidate Builder, any Selector, model, embedding, or network service. The original frozen Prediction bytes were reused unchanged.

## Bug and repair

1. The invalid Stage 3R scorer compared human-readable Gold IDs (`BV..._seg_000NNN`) directly with physical Runtime IDs (`segment_<sha256>`).
2. They represent the same Raw Segment because both deterministically resolve to Source Artifact, Source Version, Timeline Run, and zero-based Raw ordinal.
3. The invalidated metrics were Candidate Group coverage, Span Recall@1/3/5, Bundle Hit, Conditional Hit, derived Failure Attribution, F1 recommendation, and readiness decision.
4. Bridge version: `v3.5-stage3r-segment-identity-bridge-v1`.
5. Canonical Key: `source_artifact_id + source_version + timeline_run_id + segment_ordinal`.
6. Strong checks: exact Stage 1 time epsilon and exact UTF-8 text digest.
7. Fuzzy text or nearest-time matching: false.
8. Case/video-specific mapping: false.

## Mapping completeness

9. Unique case-scoped Gold Segment references: 457.
10. Gold identities resolved: 457 / 457.
11. Exact Raw Runtime-universe mappings: 457.
12. Gold Segment references actually present in a frozen CandidateSet: 274; Runtime Candidate membership occurrences audited: 4503.
13. Missing identity / ambiguity / duplicate key: 0 / 0 / 0.
14. Cross-source / version / timeline: 0 / 0 / 0.
15. Start, end, and text digest matches: 457 / 457 / 457.

## Prediction preservation

16. Track A: 31, SHA-256 `6696f3a83449bdbb5df21f7b841bace705633b718a367dc549990238e9b3b4d4`.
17. Track B: 27, SHA-256 `2f188746ccd432e4fc634592e36cd2f0e04e4c27a2bfb8ce9210483d9b9f83fe`.
18. Retrieval / Builder / Selector reruns: 0 / 0 / 0.
19. Prediction hashes unchanged: true; per-case Stage 3R prediction files unchanged: true.

## Corrected metrics

20. Track A Target Video Recall: `{'numerator': 0, 'denominator': 20, 'rate': 0.0, 'excluded_cases': ['V2C_C0C_5b3932df62f1ca76', 'U0C_8701ec36a53f837c', 'U0C_a36aa59754f94bc1', 'U0C_893af60d7b43c3b5', 'U0C_27e259b9a502a406', 'C2C_0371a3c17753fda6', 'C2C_ee3fac675fc7d408', 'C2C_9ccf0f6c9e3d2f01', 'C3C_e3a6085ddf6c6b60', 'C3C_213343d4c5fab153', 'C3C_58fa1788f33d747e']}`.
21. Track A Complete Gold Group Candidate Coverage: `{'numerator': 0, 'denominator': 20, 'rate': 0.0, 'excluded_cases': ['V2C_C0C_5b3932df62f1ca76', 'U0C_8701ec36a53f837c', 'U0C_a36aa59754f94bc1', 'U0C_893af60d7b43c3b5', 'U0C_27e259b9a502a406', 'C2C_0371a3c17753fda6', 'C2C_ee3fac675fc7d408', 'C2C_9ccf0f6c9e3d2f01', 'C3C_e3a6085ddf6c6b60', 'C3C_213343d4c5fab153', 'C3C_58fa1788f33d747e']}`.
22. Track A Span Recall@1/@3/@5: `{'numerator': 0.0, 'denominator': 20, 'rate': 0.0, 'excluded_cases': ['V2C_C0C_5b3932df62f1ca76', 'U0C_8701ec36a53f837c', 'U0C_a36aa59754f94bc1', 'U0C_893af60d7b43c3b5', 'U0C_27e259b9a502a406', 'C2C_0371a3c17753fda6', 'C2C_ee3fac675fc7d408', 'C2C_9ccf0f6c9e3d2f01', 'C3C_e3a6085ddf6c6b60', 'C3C_213343d4c5fab153', 'C3C_58fa1788f33d747e']}`, `{'numerator': 0.0, 'denominator': 20, 'rate': 0.0, 'excluded_cases': ['V2C_C0C_5b3932df62f1ca76', 'U0C_8701ec36a53f837c', 'U0C_a36aa59754f94bc1', 'U0C_893af60d7b43c3b5', 'U0C_27e259b9a502a406', 'C2C_0371a3c17753fda6', 'C2C_ee3fac675fc7d408', 'C2C_9ccf0f6c9e3d2f01', 'C3C_e3a6085ddf6c6b60', 'C3C_213343d4c5fab153', 'C3C_58fa1788f33d747e']}`, `{'numerator': 0.0, 'denominator': 20, 'rate': 0.0, 'excluded_cases': ['V2C_C0C_5b3932df62f1ca76', 'U0C_8701ec36a53f837c', 'U0C_a36aa59754f94bc1', 'U0C_893af60d7b43c3b5', 'U0C_27e259b9a502a406', 'C2C_0371a3c17753fda6', 'C2C_ee3fac675fc7d408', 'C2C_9ccf0f6c9e3d2f01', 'C3C_e3a6085ddf6c6b60', 'C3C_213343d4c5fab153', 'C3C_58fa1788f33d747e']}`.
23. Track A Bundle Hit: `{'numerator': 0, 'denominator': 20, 'rate': 0.0, 'excluded_cases': ['V2C_C0C_5b3932df62f1ca76', 'U0C_8701ec36a53f837c', 'U0C_a36aa59754f94bc1', 'U0C_893af60d7b43c3b5', 'U0C_27e259b9a502a406', 'C2C_0371a3c17753fda6', 'C2C_ee3fac675fc7d408', 'C2C_9ccf0f6c9e3d2f01', 'C3C_e3a6085ddf6c6b60', 'C3C_213343d4c5fab153', 'C3C_58fa1788f33d747e']}`.
24. Track B Complete Gold Group Candidate Coverage: `{'numerator': 11, 'denominator': 20, 'rate': 0.55, 'excluded_cases': ['V2C_C0C_5b3932df62f1ca76', 'C2C_0371a3c17753fda6', 'C2C_ee3fac675fc7d408', 'C2C_9ccf0f6c9e3d2f01', 'C3C_e3a6085ddf6c6b60', 'C3C_213343d4c5fab153', 'C3C_58fa1788f33d747e']}`.
25. Track B Span Recall@1/@3/@5: `{'numerator': 1.0833333333333333, 'denominator': 20, 'rate': 0.05416666666666666, 'excluded_cases': ['V2C_C0C_5b3932df62f1ca76', 'C2C_0371a3c17753fda6', 'C2C_ee3fac675fc7d408', 'C2C_9ccf0f6c9e3d2f01', 'C3C_e3a6085ddf6c6b60', 'C3C_213343d4c5fab153', 'C3C_58fa1788f33d747e']}`, `{'numerator': 1.3333333333333333, 'denominator': 20, 'rate': 0.06666666666666667, 'excluded_cases': ['V2C_C0C_5b3932df62f1ca76', 'C2C_0371a3c17753fda6', 'C2C_ee3fac675fc7d408', 'C2C_9ccf0f6c9e3d2f01', 'C3C_e3a6085ddf6c6b60', 'C3C_213343d4c5fab153', 'C3C_58fa1788f33d747e']}`, `{'numerator': 2.25, 'denominator': 20, 'rate': 0.1125, 'excluded_cases': ['V2C_C0C_5b3932df62f1ca76', 'C2C_0371a3c17753fda6', 'C2C_ee3fac675fc7d408', 'C2C_9ccf0f6c9e3d2f01', 'C3C_e3a6085ddf6c6b60', 'C3C_213343d4c5fab153', 'C3C_58fa1788f33d747e']}`.
26. Track B Bundle Hit / Conditional Hit: `{'numerator': 2, 'denominator': 20, 'rate': 0.1, 'excluded_cases': ['V2C_C0C_5b3932df62f1ca76', 'C2C_0371a3c17753fda6', 'C2C_ee3fac675fc7d408', 'C2C_9ccf0f6c9e3d2f01', 'C3C_e3a6085ddf6c6b60', 'C3C_213343d4c5fab153', 'C3C_58fa1788f33d747e']}` / `{'numerator': 2, 'denominator': 11, 'rate': 0.18181818181818182, 'excluded_cases': ['V2C_C0C_5b3932df62f1ca76', 'C2C_0371a3c17753fda6', 'C2C_ee3fac675fc7d408', 'C2C_9ccf0f6c9e3d2f01', 'C3C_e3a6085ddf6c6b60', 'C3C_213343d4c5fab153', 'C3C_58fa1788f33d747e', 'V2C_C0C_a48a04ab33a1ad95', 'V2C_C0C_958161474678bd3f', 'V2C_C0C_593dade03883828e', 'V2C_C0C_9618a83c9df4f059', 'V2C_C0C_9d9b5b9460d0ce51', 'V2C_C0C_185d322d5f9a00b3', 'C3C_62e28b33eec87c37', 'C3C_56b2c368638a31c3', 'C3C_98e93af3d9519c76']}`.
27. Track A median start/end/union ratio: `{'numerator': None, 'denominator': 0, 'rate': None, 'excluded_cases': ['V2C_C0C_5b3932df62f1ca76', 'U0C_8701ec36a53f837c', 'U0C_a36aa59754f94bc1', 'U0C_893af60d7b43c3b5', 'U0C_27e259b9a502a406', 'C2C_0371a3c17753fda6', 'C2C_ee3fac675fc7d408', 'C2C_9ccf0f6c9e3d2f01', 'C3C_e3a6085ddf6c6b60', 'C3C_213343d4c5fab153', 'C3C_58fa1788f33d747e']}`, `{'numerator': None, 'denominator': 0, 'rate': None, 'excluded_cases': ['V2C_C0C_5b3932df62f1ca76', 'U0C_8701ec36a53f837c', 'U0C_a36aa59754f94bc1', 'U0C_893af60d7b43c3b5', 'U0C_27e259b9a502a406', 'C2C_0371a3c17753fda6', 'C2C_ee3fac675fc7d408', 'C2C_9ccf0f6c9e3d2f01', 'C3C_e3a6085ddf6c6b60', 'C3C_213343d4c5fab153', 'C3C_58fa1788f33d747e']}`, `{'numerator': None, 'denominator': 0, 'rate': None, 'excluded_cases': ['V2C_C0C_5b3932df62f1ca76', 'U0C_8701ec36a53f837c', 'U0C_a36aa59754f94bc1', 'U0C_893af60d7b43c3b5', 'U0C_27e259b9a502a406', 'C2C_0371a3c17753fda6', 'C2C_ee3fac675fc7d408', 'C2C_9ccf0f6c9e3d2f01', 'C3C_e3a6085ddf6c6b60', 'C3C_213343d4c5fab153', 'C3C_58fa1788f33d747e']}`.
28. Track B median start/end/union ratio: `{'numerator': None, 'denominator': 57, 'rate': 30.099999999999994, 'excluded_cases': ['V2C_C0C_5b3932df62f1ca76', 'C2C_0371a3c17753fda6', 'C2C_ee3fac675fc7d408', 'C2C_9ccf0f6c9e3d2f01', 'C3C_e3a6085ddf6c6b60', 'C3C_213343d4c5fab153', 'C3C_58fa1788f33d747e']}`, `{'numerator': None, 'denominator': 57, 'rate': 30.38000000000001, 'excluded_cases': ['V2C_C0C_5b3932df62f1ca76', 'C2C_0371a3c17753fda6', 'C2C_ee3fac675fc7d408', 'C2C_9ccf0f6c9e3d2f01', 'C3C_e3a6085ddf6c6b60', 'C3C_213343d4c5fab153', 'C3C_58fa1788f33d747e']}`, `{'numerator': None, 'denominator': 20, 'rate': 1.2564625841326713, 'excluded_cases': ['V2C_C0C_5b3932df62f1ca76', 'C2C_0371a3c17753fda6', 'C2C_ee3fac675fc7d408', 'C2C_9ccf0f6c9e3d2f01', 'C3C_e3a6085ddf6c6b60', 'C3C_213343d4c5fab153', 'C3C_58fa1788f33d747e']}`.

Every metric object includes numerator, denominator, rate, and excluded Cases. Gold Groups remain OR; Required Spans within a Group remain AND.

## Diagnostics and attribution

29. Insufficient operational diagnostics: `{'track_a': {'cases': 7, 'valid_search_candidate_set': 0, 'valid_candidate_builder_output': 0, 'bundle_created': 0, 'selector_abstained': 7, 'typed_failure': 0, 'bundle_segment_count': 0, 'bundle_union_duration_seconds': 0, 'near_support_concentration': 'unavailable'}, 'track_b': {'cases': 7, 'valid_search_candidate_set': 7, 'valid_candidate_builder_output': 7, 'bundle_created': 7, 'selector_abstained': 0, 'typed_failure': 0, 'bundle_segment_count': 40, 'bundle_union_duration_seconds': 758.7807009999999, 'near_support_concentration': 'unavailable'}}`.
30. Unverifiable diagnostics: `{'track_a': {'cases': 4, 'correct_source_authority_terminal': 0, 'incorrect_bundle_created': 0, 'incorrect_regular_selector_failure': 4, 'other_typed_terminal': 0}, 'track_b': {'cases': 0, 'correct_source_authority_terminal': 0, 'incorrect_bundle_created': 0, 'incorrect_regular_selector_failure': 0, 'other_typed_terminal': 0}}`.
31. Unverifiable Cases incorrectly creating a Bundle: `0`.
32. Rescored failure stages: `{'total': 42, 'counts': {'candidate_builder': 9, 'deterministic_selector': 9, 'source_authority': 4, 'v3_retrieval': 20}}`.
33. Failures by Query Family: `{'total': 42, 'counts': {'comparison': 9, 'definition_or_explanation': 7, 'method_or_process': 16, 'multi-part_question': 2, 'result_or_effect': 8}}`.
34. Failures by Evidence Structure: `{'total': 42, 'counts': {'multi_span_distant_regions': 14, 'multi_span_same_region': 14, 'multiple_alternative_groups': 4, 'single_span': 6, 'source_authority_unavailable': 4}}`.
35. Repeated signatures: `{'target_video_not_retrieved': {'affected_cases': 20, 'affected_case_ids': ['C2C_16019b3c36a8945b', 'C2C_a1c0207a1bc56a91', 'C3C_41cfa020e8d664c5', 'C3C_56b2c368638a31c3', 'C3C_62e28b33eec87c37', 'C3C_98e93af3d9519c76', 'C3C_f57e1f0cc83cd5dd', 'V2C_C0C_0492bb2ae33b5cec', 'V2C_C0C_185d322d5f9a00b3', 'V2C_C0C_2b331035debc8160', 'V2C_C0C_53862aba0bd0bfcb', 'V2C_C0C_5725899059df795c', 'V2C_C0C_593dade03883828e', 'V2C_C0C_8228254ff69d7b3b', 'V2C_C0C_958161474678bd3f', 'V2C_C0C_9618a83c9df4f059', 'V2C_C0C_9a49204f52a114c8', 'V2C_C0C_9d9b5b9460d0ce51', 'V2C_C0C_a48a04ab33a1ad95', 'V2C_C0C_c72788577931ce36'], 'affected_query_families': ['comparison', 'definition_or_explanation', 'method_or_process', 'multi-part_question', 'result_or_effect'], 'primary_stages': ['v3_retrieval']}, 'unverifiable_not_typed_as_source_authority_failure': {'affected_cases': 4, 'affected_case_ids': ['U0C_27e259b9a502a406', 'U0C_8701ec36a53f837c', 'U0C_893af60d7b43c3b5', 'U0C_a36aa59754f94bc1'], 'affected_query_families': ['definition_or_explanation', 'method_or_process'], 'primary_stages': ['source_authority']}, 'no_complete_gold_group_in_candidate_set': {'affected_cases': 9, 'affected_case_ids': ['C3C_56b2c368638a31c3', 'C3C_62e28b33eec87c37', 'C3C_98e93af3d9519c76', 'V2C_C0C_185d322d5f9a00b3', 'V2C_C0C_593dade03883828e', 'V2C_C0C_958161474678bd3f', 'V2C_C0C_9618a83c9df4f059', 'V2C_C0C_9d9b5b9460d0ce51', 'V2C_C0C_a48a04ab33a1ad95'], 'affected_query_families': ['comparison', 'definition_or_explanation', 'method_or_process', 'result_or_effect'], 'primary_stages': ['candidate_builder']}, 'complete_candidate_group_not_selected': {'affected_cases': 9, 'affected_case_ids': ['C2C_16019b3c36a8945b', 'C2C_a1c0207a1bc56a91', 'C3C_41cfa020e8d664c5', 'C3C_f57e1f0cc83cd5dd', 'V2C_C0C_0492bb2ae33b5cec', 'V2C_C0C_2b331035debc8160', 'V2C_C0C_53862aba0bd0bfcb', 'V2C_C0C_9a49204f52a114c8', 'V2C_C0C_c72788577931ce36'], 'affected_query_families': ['comparison', 'definition_or_explanation', 'method_or_process', 'multi-part_question', 'result_or_effect'], 'primary_stages': ['deterministic_selector']}}`.

## Historical relationship

36. Preserved: original predictions, SearchCandidateSets, Builder/Selector outputs, Bundles, terminals, Runtime hashes, and Prediction Freeze.
37. Superseded: original scoring metrics, Failure Attribution, readiness decision, and F1 recommendation.
38. The old “Builder全面失败” and “Selector全面失败” conclusions were artifacts of the namespace bug and are not retained; corrected per-track outcomes above are authoritative.

## Final decision

39. Stage 3R-S1 status: complete.
40. `stage3r_final_decision: authorize_one_bounded_generic_stage3r_fix`.
41. Stage 3R-F1: `{"affected_case_ids": ["C2C_16019b3c36a8945b", "C2C_a1c0207a1bc56a91", "C3C_41cfa020e8d664c5", "C3C_f57e1f0cc83cd5dd", "V2C_C0C_0492bb2ae33b5cec", "V2C_C0C_2b331035debc8160", "V2C_C0C_53862aba0bd0bfcb", "V2C_C0C_9a49204f52a114c8", "V2C_C0C_c72788577931ce36"], "affected_query_families": ["comparison", "definition_or_explanation", "method_or_process", "multi-part_question", "result_or_effect"], "affected_stage": "deterministic_selector", "allowed_files": ["the separately authorized existing affected Runtime stage", "Stage 3R-F1 tests and rerun artifacts"], "failure_signature": "complete_candidate_group_not_selected", "forbidden_case_specific_logic": true, "proposed_generic_mechanism": "one bounded generic multi-span coverage objective repair", "required_rerun_scope": "all frozen 31 Development Cases"}`.
42. Stage 3R accepted: false; the scoring repair is accepted, but Stage 3R-F1 is required before Stage 4A-R.
43. Next action: Main-session review, followed only by the handoff authorized by this decision.
44. This Codex session may close after Main-session review.

## Stop state

Stage 3R-S1 Complete  
Segment Identity Scoring Repair Accepted  
Frozen Predictions Rescored  
One Bounded Generic Runtime Fix Recommended  
Stage 3R-F1 Required Before Stage 4A-R  
No Runtime Fix Applied
