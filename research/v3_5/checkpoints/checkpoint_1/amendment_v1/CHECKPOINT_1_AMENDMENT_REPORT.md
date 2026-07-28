# Checkpoint 1 Amendment Report

Checkpoint 1 is amended only for findings derived from P8 scoring. P7 remains
`complete_and_accepted`; the P8 Attempt 3 Prediction Set remains
`valid_and_frozen`.

The frozen Prediction identity remains 14 records with SHA-256
`b34f173ac99208f4adb72966880ab7e9cf97d3e27157084792502f103e709038`;
the Prediction Seal remains
`069fcf9e3ec70cf28d23674a2752033e608bf46937c990176dd6fb52f9e04617`.
DEVELOPMENT_GOLD_V1 remains unchanged with Seal SHA-256
`1010fb635680bacc72c9aac8cbd096494370cd0709ed1d746754a0eade90cb5a`.

The original P8 scoring is `superseded_by_scoring_amendment`. The current
version is `P8_SCORING_AMENDMENT_V1`, with Scoring Hash Root
`54bc35083f4410ace027452b64fc2d22432111be5a2036c0ce245e6319849795`.

The original Checkpoint 1 derived Builder denominator `14` and Builder primary
failure count `7` are superseded by Scoring Amendment v1. The amended Builder
complete-group coverage is `6/13`; required-span recall is
`0.6538461538461539`;
required-aspect coverage is
`0.6538461538461539`;
Builder primary failures are `6`.

Selector bundle hit is `1/13`; required-span recall is
`0.12179487179487179`; required-aspect coverage is
`0.12179487179487179`; Selector primary failures remain `5`.

The amended Primary Failure Distribution is
`{"candidate_builder_failure": 6, "deterministic_selector_failure": 5, "end_to_end_bundle_hit": 1, "gold_defined_evidence_absent": 1, "source_unverifiable": 1}`.
Q017's general terminal is `gold_defined_evidence_absent`.

Retrieval remains Hit@10 `14/14` with zero primary Retrieval failures. Selector
primary failures remain `5`; Gate predictions and derived counts remain
unchanged.

F1A entry signal remains true because real Builder failures remain. P9 is
`blocked_pending_v3_5_b_acceptance`; restart readiness is true, but P9 was not
restarted. F1A/F1B remain unauthorized and Stage 4 was not started.

No Prediction, Trace, Retrieval, Builder, Selector, Gate, Query, Split, Gold,
or Product Component was rerun or modified in completing this Checkpoint
Amendment. Scoring was not recomputed again. Frozen Gold was not opened.
